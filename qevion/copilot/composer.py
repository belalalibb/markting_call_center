"""BlueprintComposer (§14 QV-COP-006/008/010/015-B): deterministic merge of operator answers into a draft.

Rules:
  * Answers are written to `target_path` of the question they answer. The composer never invents business
    values; the only defaults it applies are *structural* (schema-required scaffolding: identity, machine ref,
    uncertainty policy mirroring the unknown-question default).
  * Every business-decision element written gets a `Decision(proposed_by=..., approved_by=None)` unless the
    operator answered it directly (then `approved_by = operator_id`, `proposed_by = OPERATOR`).
  * Output is (draft dict, validated ActivityBlueprint | None, validation errors, decisions). Validity is
    reported, never assumed (QV-COP-015).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from qevion.contracts.activity import ActivityBlueprint
from qevion.contracts.copilot import AnswerType, CopilotQuestion
from qevion.contracts.policy import Behavior, Decision, ProposedBy

# Paths whose values are business truth → need a Decision record (QV-ACT-002).
BUSINESS_DECISION_PATHS: tuple[str, ...] = (
    "objective",
    "data.required",
    "data.optional",
    "policies.allowed_claims",
    "policies.prohibited_claims",
    "policies.escalation",
    "policies.contact_policy_hooks",
    "policies.unknown_question_policy",
    "policies.opt_out",
    "coverage",
    "completion",
    "outcome_schema",
    "handoff_rules",
    "tools.permissions",
)

_SLUG = re.compile(r"[^a-z0-9_]+")


def _slug(s: str) -> str:
    return _SLUG.sub("_", s.strip().lower()).strip("_") or "x"


def _set(d: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    cur = d
    for p in parts[:-1]:
        nxt = cur.get(p)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[p] = nxt
        cur = nxt
    cur[parts[-1]] = value


def _get(d: dict[str, Any], path: str) -> Any:
    cur: Any = d
    for p in path.split("."):
        if not isinstance(cur, dict) or p not in cur:
            return None
        cur = cur[p]
    return cur


def is_business_path(path: str) -> bool:
    return any(path == p or path.startswith(p + ".") for p in BUSINESS_DECISION_PATHS)


@dataclass
class Answer:
    question: CopilotQuestion
    value: Any
    operator_id: str


@dataclass
class ComposeResult:
    draft: dict[str, Any]
    blueprint: ActivityBlueprint | None
    valid: bool
    errors: list[str]
    decisions: list[Decision] = field(default_factory=list)


class BlueprintComposer:
    """Stateless; the config session keeps the accumulated draft and decisions."""

    def __init__(self, *, tenant_id: str, activity_id: str, name: str, version: str = "0.1.0") -> None:
        self._tenant = tenant_id
        self._activity = activity_id
        self._name = name
        self._version = version

    # --------------------------------------------------------------- answers
    def apply(self, draft: dict[str, Any], decisions: list[Decision], answer: Answer) -> list[Decision]:
        """Write one answer into `draft` (mutating) and return the updated decisions list."""
        q = answer.question
        path = q.target_path
        value = self._coerce(q, answer.value)
        if path.startswith(("knowledge.gaps.", "knowledge.contradictions.", "capabilities.")):
            # Not blueprint fields: recorded as decisions/notes only; knowledge plane resolves them.
            return self._record(decisions, path, ProposedBy.OPERATOR, answer.operator_id, rationale=str(value))
        if path == "locale":
            _set(draft, "locale", self._locale(str(value)))
        elif path == "objective.primary":
            _set(draft, "objective.primary", self._objective(value))
        elif path == "data.required":
            _set(draft, "data.required", self._fields(value))
        elif path == "knowledge.sources":
            _set(draft, "knowledge.sources", self._sources(value))
        elif path == "policies.opt_out":
            _set(draft, "policies.opt_out", {"phrases_ref": "optout_default", "action": str(value)})
        elif path == "policies.contact_policy_hooks":
            _set(
                draft,
                path,
                value if isinstance(value, dict) else {"consent_required": True, "contact_window": str(value)},
            )
        elif path == "outcome_schema.primary":
            _set(draft, path, [_slug(str(v)) for v in self._as_list(value)])
        elif path in ("completion.success_rules", "completion.failure_rules", "completion.exit_rules"):
            _set(draft, path, [str(v) for v in self._as_list(value)])
        elif path == "handoff_rules":
            _set(draft, path, self._handoffs(value))
        elif path == "coverage.objections":
            _set(draft, path, self._objections(value))
        elif path == "channels":
            _set(draft, path, [str(v) for v in self._as_list(value)])
        else:
            _set(draft, path, value)
        if is_business_path(path):
            return self._record(decisions, path, ProposedBy.OPERATOR, answer.operator_id)
        return decisions

    def accept_proposal(
        self, draft: dict[str, Any], decisions: list[Decision], q: CopilotQuestion, operator_id: str
    ) -> list[Decision]:
        """Operator accepts the Copilot's structural proposal → value applied, Decision proposed_by=copilot,
        approved_by=operator (explicit acceptance is approval)."""
        if q.proposed_default is None:
            return decisions
        decisions = self.apply(draft, decisions, Answer(q, q.proposed_default, operator_id))
        return self._record(decisions, q.target_path, ProposedBy.COPILOT, operator_id, replace=True)

    # ------------------------------------------------------------ composition
    def compose(self, draft: dict[str, Any], decisions: list[Decision]) -> ComposeResult:
        d = self._scaffold(dict(draft))
        decisions = list(decisions)
        try:
            bp = ActivityBlueprint.model_validate(d)
            d_out = bp.model_dump(mode="json", by_alias=True)
            d_out["version_metadata"]["decisions"] = [x.model_dump(mode="json") for x in decisions]
            bp = ActivityBlueprint.model_validate(d_out)
            return ComposeResult(d, bp, True, [], decisions)
        except ValidationError as e:
            errs = [f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}" for err in e.errors()]
            return ComposeResult(d, None, False, errs, decisions)

    # ---------------------------------------------------------------- helpers
    def _scaffold(self, d: dict[str, Any]) -> dict[str, Any]:
        """Structural defaults only — never business values."""
        d.setdefault("schema", "qevion.activity.v1")
        ident = d.setdefault("identity", {})
        ident.setdefault("tenant_id", self._tenant)
        ident.setdefault("activity_id", self._activity)
        ident.setdefault("name", self._name)
        ident.setdefault("version", self._version)
        pol = d.setdefault("policies", {})
        uq = _get(pol, "unknown_question_policy.default")
        if uq is not None and "uncertainty_policy" not in pol:
            # mirror: missing/conflicting/stale follow the declared default unless the operator says otherwise
            pol["uncertainty_policy"] = {"missing": uq, "conflicting": Behavior.STATE_LIMITATION.value, "stale": uq}
        d.setdefault("activity_machine", {"table_ref": "generic_default_v1"})
        return d

    @staticmethod
    def _record(
        decisions: list[Decision],
        path: str,
        proposed_by: ProposedBy,
        approved_by: str | None,
        *,
        rationale: str | None = None,
        replace: bool = False,
    ) -> list[Decision]:
        out = [x for x in decisions if x.item_path != path] if replace else list(decisions)
        if not replace and any(x.item_path == path for x in out):
            out = [x for x in out if x.item_path != path]
        out.append(Decision(item_path=path, proposed_by=proposed_by, approved_by=approved_by, rationale=rationale))
        return out

    @staticmethod
    def _coerce(q: CopilotQuestion, value: Any) -> Any:
        if q.answer_type is AnswerType.YES_NO and isinstance(value, str):
            return value.strip().lower() in {"yes", "y", "true", "1", "نعم", "ايوه", "أيوه"}
        if q.answer_type is AnswerType.NUMBER and isinstance(value, str):
            try:
                return float(value) if "." in value else int(value)
            except ValueError:
                return value
        if q.answer_type is AnswerType.CHOICE and q.options and isinstance(value, str) and value not in q.options:
            low = {o.lower(): o for o in q.options}
            return low.get(value.strip().lower(), value)
        return value

    @staticmethod
    def _as_list(value: Any) -> list[Any]:
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            return [p.strip() for p in re.split(r"[,\n;،]+", value) if p.strip()]
        return [value]

    @staticmethod
    def _locale(v: str) -> dict[str, Any]:
        if "-" in v:
            lang, region = v.split("-", 1)
            return {"language": lang.lower(), "locale": f"{lang.lower()}-{region.upper()}"}
        return {"language": v.lower(), "locale": f"{v.lower()}-{v.upper()}"}

    @staticmethod
    def _objective(v: Any) -> dict[str, Any]:
        if isinstance(v, dict):
            return {"kind": _slug(str(v.get("kind", "objective"))), "description": str(v.get("description", ""))}
        text = str(v)
        return {"kind": _slug(text[:40]), "description": text}

    @staticmethod
    def _fields(v: Any) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for item in BlueprintComposer._as_list(v):
            if isinstance(item, dict):
                out.append(
                    {
                        "name": _slug(str(item.get("name", "field"))),
                        "type": item.get("type", "string"),
                        **{k: x for k, x in item.items() if k not in ("name", "type")},
                    }
                )
            else:
                out.append({"name": _slug(str(item)), "type": "string"})
        return out

    @staticmethod
    def _sources(v: Any) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for item in BlueprintComposer._as_list(v):
            if isinstance(item, dict):
                out.append(
                    {
                        "source_id": str(item.get("source_id", "src")),
                        "kind": item.get("kind", "file"),
                        **{k: x for k, x in item.items() if k not in ("source_id", "kind")},
                    }
                )
            else:
                out.append({"source_id": _slug(str(item)), "kind": "file"})
        return out

    @staticmethod
    def _handoffs(v: Any) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for item in BlueprintComposer._as_list(v):
            if isinstance(item, dict):
                out.append(
                    {
                        "trigger": str(item.get("trigger", "human_requested")),
                        "destination_ref": str(item.get("destination_ref", "default_queue")),
                        "priority": item.get("priority", "normal"),
                    }
                )
            else:
                out.append({"trigger": "human_requested", "destination_ref": _slug(str(item))})
        return out

    @staticmethod
    def _objections(v: Any) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for i, item in enumerate(BlueprintComposer._as_list(v)):
            if isinstance(item, dict):
                out.append(
                    {
                        "id": str(item.get("id", f"obj_{i}")),
                        "pattern": str(item.get("pattern", "")),
                        "status": item.get("status", "ASK_OWNER"),
                        **{k: x for k, x in item.items() if k not in ("id", "pattern", "status")},
                    }
                )
            else:
                out.append({"id": f"obj_{i}", "pattern": str(item), "status": "ASK_OWNER"})
        return out


__all__ = ["BUSINESS_DECISION_PATHS", "Answer", "BlueprintComposer", "ComposeResult", "is_business_path"]
