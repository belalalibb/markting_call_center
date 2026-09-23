"""Discovery engine (§14 QV-COP-001..007): questions are *derived from state*, never a fixed questionnaire.

Sources of questions, in order of authority:
  1. structural holes in the draft Blueprint (what the schema needs and the operator has not said)
  2. knowledge gaps (`KnowledgeGap`) — REQUIRED_FOR_EXECUTION / POLICY_RISK / DATA_CONFLICT block
  3. unresolved contradictions (`Contradiction.resolution == "pending"`)
  4. preflight findings (`PreflightFinding`) — BLOCK → blocking question
  5. capability mapping rows (`RequirementMapping`) — REQUIRES_* / UNSUPPORTED / UNVERIFIED

Every question carries `target_path` (which Blueprint element it fills) and `why_it_matters`. Business
decisions (`QuestionKind.BUSINESS_DECISION`) never carry a free-text `proposed_default` (QV-COP-007): the
Copilot may propose *structure*, never *business truth*.

Prioritization is deterministic (QV-COP-004): kind band → blocking → progressive-disclosure stage → order
of generation. Stop rule (QV-COP-005): discovery is complete when no *blocking* question remains.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from qevion.contracts.composition import MappingResult
from qevion.contracts.control import PreflightFinding, PreflightReason
from qevion.contracts.copilot import BLOCKING_GAP_CLASSES, AnswerType, CopilotQuestion, QuestionKind
from qevion.contracts.knowledge import Contradiction, GapClass, KnowledgeGap
from qevion.contracts.policy import Behavior

_BAND: dict[QuestionKind, int] = {
    QuestionKind.BLOCKING_GAP: 0,
    QuestionKind.DATA_CONFLICT: 10,
    QuestionKind.POLICY_RISK: 20,
    QuestionKind.BUSINESS_DECISION: 30,
    QuestionKind.CAPABILITY_GAP: 40,
    QuestionKind.QUALITY: 60,
    QuestionKind.OPTIONAL: 80,
}

# Progressive disclosure (QV-COP-004): earlier stages are asked first when bands tie.
_STAGE_ORDER: list[str] = [
    "objective",
    "direction",
    "channels",
    "locale",
    "knowledge",
    "data",
    "coverage",
    "tools",
    "policies",
    "outcome_schema",
    "completion",
    "handoff_rules",
    "evaluation",
]

_GAP_KIND: dict[GapClass, QuestionKind] = {
    GapClass.REQUIRED_FOR_EXECUTION: QuestionKind.BLOCKING_GAP,
    GapClass.POLICY_RISK: QuestionKind.POLICY_RISK,
    GapClass.DATA_CONFLICT: QuestionKind.DATA_CONFLICT,
    GapClass.IMPORTANT_FOR_QUALITY: QuestionKind.QUALITY,
    GapClass.OPTIONAL_IMPROVEMENT: QuestionKind.OPTIONAL,
    GapClass.UNKNOWN: QuestionKind.QUALITY,
}

# Preflight reasons whose fix is a business decision by the operator (Copilot must not fill them).
_BUSINESS_REASONS: frozenset[PreflightReason] = frozenset(
    {
        PreflightReason.UNAPPROVED_BUSINESS_DECISION,
        PreflightReason.CONTRADICTORY_POLICIES,
        PreflightReason.UNDEFINED_ESCALATION,
        PreflightReason.UNDEFINED_UNKNOWN_QUESTION_POLICY,
        PreflightReason.CONTACT_POLICY_MISSING_FOR_OUTBOUND,
        PreflightReason.IMPOSSIBLE_COMPLETION_CRITERIA,
        PreflightReason.MISSING_OUTCOME_SCHEMA,
    }
)
_CAPABILITY_REASONS: frozenset[PreflightReason] = frozenset(
    {
        PreflightReason.UNSUPPORTED_CAPABILITY,
        PreflightReason.UNSUPPORTED_LOCALE_COMBINATION,
        PreflightReason.VOICE_UNAVAILABLE,
        PreflightReason.PROVIDER_CAPABILITY_UNAVAILABLE,
        PreflightReason.UNSUPPORTED_CHANNEL,
        PreflightReason.MISSING_REQUIRED_TOOL,
        PreflightReason.TOOL_NOT_AUTHORIZED_FOR_TENANT,
        PreflightReason.LICENSE_BLOCKED_COMPONENT,
    }
)

# Blueprint paths where a suggested value would be *business truth*, not structure (QV-COP-007).
_BUSINESS_PATH_PREFIXES: tuple[str, ...] = (
    "objective",
    "policies.allowed_claims",
    "policies.prohibited_claims",
    "policies.escalation",
    "policies.contact_policy_hooks",
    "coverage",
    "completion",
    "handoff_rules",
    "knowledge.gaps",
)

_PERSUASIVE_HINTS: tuple[str, ...] = ("sale", "sell", "convert", "upsell", "renew", "collect", "persuad", "book")


@dataclass
class DiscoveryInputs:
    """Everything the engine looks at. `draft` is a plain dict (partial Blueprint, may be invalid)."""

    draft: dict[str, Any] = field(default_factory=dict)
    gaps: list[KnowledgeGap] = field(default_factory=list)
    contradictions: list[Contradiction] = field(default_factory=list)
    mapping: list[Any] = field(default_factory=list)  # RequirementMapping rows (duck-typed: control→copilot ok)
    preflight: list[PreflightFinding] = field(default_factory=list)
    answered_paths: set[str] = field(default_factory=set)
    deferred_paths: set[str] = field(default_factory=set)


def _get(d: dict[str, Any], path: str) -> Any:
    cur: Any = d
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _present(d: dict[str, Any], path: str) -> bool:
    v = _get(d, path)
    if v is None:
        return False
    if isinstance(v, str | list | dict):
        return len(v) > 0
    return True


def question_id_for(path: str, text: str) -> str:
    """Deterministic across processes (no `hash()`; PYTHONHASHSEED-independent)."""
    digest = hashlib.sha256(f"{path}\x00{text}".encode()).hexdigest()
    return f"q_{digest[:12]}"


class QuestionPrioritizer:
    """Deterministic ranking: band → blocking → stage → generation order (QV-COP-004)."""

    @staticmethod
    def _stage_bonus(path: str) -> int:
        head = path.split(".", 1)[0]
        try:
            return _STAGE_ORDER.index(head)
        except ValueError:
            return len(_STAGE_ORDER)

    def rank(self, questions: list[CopilotQuestion]) -> list[CopilotQuestion]:
        ranked: list[CopilotQuestion] = []
        for i, q in enumerate(questions):
            prio = _BAND[q.kind] + (0 if q.blocking else 5) + self._stage_bonus(q.target_path)
            ranked.append(q.model_copy(update={"priority": prio * 1000 + i}))
        return sorted(ranked, key=lambda q: (q.priority, q.question_id))


class DiscoveryEngine:
    """Generates the next questions from state. Stateless; the config session owns memory."""

    def __init__(self, prioritizer: QuestionPrioritizer | None = None) -> None:
        self._prio = prioritizer or QuestionPrioritizer()

    # ------------------------------------------------------------------ public
    def all_questions(self, inp: DiscoveryInputs) -> list[CopilotQuestion]:
        raw: list[CopilotQuestion] = []
        raw += self._structural(inp.draft)
        raw += self._from_gaps(inp.gaps)
        raw += self._from_contradictions(inp.contradictions)
        raw += self._from_preflight(inp.preflight)
        raw += self._from_mapping(inp.mapping)
        seen: set[str] = set()
        deduped: list[CopilotQuestion] = []
        for q in raw:
            if q.target_path in seen:
                continue
            seen.add(q.target_path)
            if q.target_path in inp.answered_paths or q.target_path in inp.deferred_paths:
                continue
            deduped.append(q)
        return self._prio.rank(deduped)

    def next_questions(self, inp: DiscoveryInputs, *, limit: int = 3) -> list[CopilotQuestion]:
        return self.all_questions(inp)[: max(0, limit)]

    # ------------------------------------------------------------ generators
    def _structural(self, d: dict[str, Any]) -> list[CopilotQuestion]:
        qs: list[CopilotQuestion] = []
        if not _present(d, "objective.primary.kind"):
            qs.append(
                self._q(
                    QuestionKind.BUSINESS_DECISION,
                    "objective.primary",
                    "What is the primary objective of this Activity — what counts as success for you?",
                    "Everything else (data, completion rules, outcome schema) is derived from the objective.",
                    blocking=True,
                )
            )
        if not _present(d, "direction"):
            qs.append(
                self._q(
                    QuestionKind.BUSINESS_DECISION,
                    "direction",
                    "Does the agent receive contacts (inbound), initiate them (outbound), or both?",
                    "Outbound requires consent/contact-window policies; inbound does not.",
                    answer_type=AnswerType.CHOICE,
                    options=["inbound", "outbound", "bidirectional"],
                    blocking=True,
                )
            )
        if not _present(d, "channels"):
            qs.append(
                self._q(
                    QuestionKind.BLOCKING_GAP,
                    "channels",
                    "Which channels should this Activity run on?",
                    "Channel choice decides which capabilities and compositions are needed.",
                    answer_type=AnswerType.CHOICE,
                    options=["browser_voice", "text", "telephony"],
                    proposed_default=["browser_voice", "text"],
                    blocking=True,
                )
            )
        if not _present(d, "locale.locale"):
            qs.append(
                self._q(
                    QuestionKind.QUALITY,
                    "locale",
                    "Which language and dialect should the agent speak?",
                    "Locale selects the locale pack, voice profile and pronunciation rules.",
                    answer_type=AnswerType.CHOICE,
                    options=["ar-EG", "ar-SA", "en-US", "en-GB"],
                    proposed_default="ar-EG",
                )
            )
        if _get(d, "direction") in ("outbound", "bidirectional") and not _present(d, "policies.contact_policy_hooks"):
            qs.append(
                self._q(
                    QuestionKind.POLICY_RISK,
                    "policies.contact_policy_hooks",
                    "For outbound contact: is prior consent required, what is the attempt limit, and the contact window?",
                    "Outbound without a contact policy is a compliance risk and is blocked by preflight.",
                    blocking=True,
                )
            )
        if not _present(d, "data.required"):
            qs.append(
                self._q(
                    QuestionKind.BUSINESS_DECISION,
                    "data.required",
                    "Which pieces of information must the agent collect from the person to achieve the objective?",
                    "Required fields drive the dialog: the agent asks, validates and confirms only what you list.",
                    blocking=True,
                )
            )
        if not _present(d, "knowledge.sources"):
            qs.append(
                self._q(
                    QuestionKind.BLOCKING_GAP,
                    "knowledge.sources",
                    "Upload the documents or data the agent may rely on (menu, price list, FAQ, schedule…).",
                    "The agent answers only from approved knowledge; without sources it can only state limitations.",
                    answer_type=AnswerType.UPLOAD,
                    blocking=True,
                )
            )
        if not _present(d, "policies.unknown_question_policy.default"):
            qs.append(
                self._q(
                    QuestionKind.POLICY_RISK,
                    "policies.unknown_question_policy.default",
                    "When asked something not covered by approved knowledge, what should the agent do by default?",
                    "'The model decides' is not an option; an explicit behavior prevents fabricated answers.",
                    answer_type=AnswerType.CHOICE,
                    options=[b.value for b in Behavior],
                    proposed_default=Behavior.STATE_LIMITATION.value,
                    blocking=True,
                )
            )
        if not _present(d, "policies.opt_out"):
            qs.append(
                self._q(
                    QuestionKind.POLICY_RISK,
                    "policies.opt_out",
                    "How should the agent react when the person asks to stop or not be contacted?",
                    "Opt-out handling is mandatory for respectful, compliant conversations.",
                    answer_type=AnswerType.CHOICE,
                    options=[Behavior.CLOSE_GRACEFULLY.value, Behavior.OFFER_HUMAN_HANDOFF.value],
                    proposed_default=Behavior.CLOSE_GRACEFULLY.value,
                )
            )
        if not _present(d, "outcome_schema.primary"):
            qs.append(
                self._q(
                    QuestionKind.BUSINESS_DECISION,
                    "outcome_schema.primary",
                    "Which outcomes should each conversation be classified into?",
                    "Outcome labels feed reporting and next actions; they must be yours, not guessed.",
                    answer_type=AnswerType.CONFIRM_PROPOSAL,
                    proposed_default=["completed", "not_completed", "opted_out", "handed_off"],
                    blocking=True,
                )
            )
        if not _present(d, "completion.success_rules"):
            qs.append(
                self._q(
                    QuestionKind.BUSINESS_DECISION,
                    "completion.success_rules",
                    "When exactly is a conversation successfully complete?",
                    "Without success rules the agent cannot know when to stop or how to classify the result.",
                    blocking=True,
                )
            )
        uq = _get(d, "policies.unknown_question_policy.default")
        if uq == Behavior.OFFER_HUMAN_HANDOFF.value and not _present(d, "handoff_rules"):
            qs.append(
                self._q(
                    QuestionKind.BUSINESS_DECISION,
                    "handoff_rules",
                    "Where should human handoffs go, and with what priority?",
                    "You chose 'offer human handoff' but no destination is defined.",
                    blocking=True,
                )
            )
        kind = str(_get(d, "objective.primary.kind") or "").lower()
        desc = str(_get(d, "objective.primary.description") or "").lower()
        if any(h in kind or h in desc for h in _PERSUASIVE_HINTS) and not _present(d, "coverage.objections"):
            qs.append(
                self._q(
                    QuestionKind.BUSINESS_DECISION,
                    "coverage.objections",
                    "What objections do people typically raise, and what responses are you comfortable approving?",
                    "Persuasive objectives need approved objection handling; the agent will not improvise claims.",
                )
            )
        return qs

    def _from_gaps(self, gaps: list[KnowledgeGap]) -> list[CopilotQuestion]:
        qs: list[CopilotQuestion] = []
        for g in gaps:
            if g.resolved:
                continue
            kind = _GAP_KIND[g.gap_class]
            qs.append(
                self._q(
                    kind,
                    f"knowledge.gaps.{g.gap_id}",
                    g.question_for_operator,
                    g.description,
                    source_refs=[g.gap_id, *g.related_fact_ids],
                    blocking=g.gap_class in BLOCKING_GAP_CLASSES,
                )
            )
        return qs

    def _from_contradictions(self, cs: list[Contradiction]) -> list[CopilotQuestion]:
        qs: list[CopilotQuestion] = []
        for c in cs:
            if c.resolution != "pending":
                continue
            qs.append(
                self._q(
                    QuestionKind.DATA_CONFLICT,
                    f"knowledge.contradictions.{c.contradiction_id}",
                    f"Your sources disagree: {c.description}. Which fact is correct?",
                    "The agent will not state a fact while its sources conflict.",
                    answer_type=AnswerType.CHOICE,
                    options=list(c.fact_ids),
                    source_refs=[c.contradiction_id, *c.fact_ids],
                    blocking=True,
                )
            )
        return qs

    def _from_preflight(self, findings: list[PreflightFinding]) -> list[CopilotQuestion]:
        qs: list[CopilotQuestion] = []
        for f in findings:
            if f.reason in _BUSINESS_REASONS:
                kind = QuestionKind.BUSINESS_DECISION
            elif f.reason in _CAPABILITY_REASONS:
                kind = QuestionKind.CAPABILITY_GAP
            elif f.severity == "BLOCK":
                kind = QuestionKind.BLOCKING_GAP
            else:
                kind = QuestionKind.QUALITY
            qs.append(
                self._q(
                    kind,
                    f.path,
                    f.fix_hint or f.message,
                    f"Preflight {f.severity}: {f.reason.value} — {f.message}",
                    source_refs=[f"preflight:{f.reason.value}:{f.path}"],
                    blocking=f.severity == "BLOCK",
                )
            )
        return qs

    def _from_mapping(self, rows: list[Any]) -> list[CopilotQuestion]:
        qs: list[CopilotQuestion] = []
        for r in rows:
            action = MappingResult(str(r.action))
            req = str(r.requirement)
            cap = str(r.required_capability)
            state = str(r.current_state)
            path = f"capabilities.{cap}"
            refs = [f"mapping:{cap}"]
            if action == MappingResult.REQUIRES_KNOWLEDGE:
                qs.append(
                    self._q(
                        QuestionKind.BLOCKING_GAP,
                        path,
                        f"'{req}' needs approved knowledge. Upload or point to the source.",
                        "The requirement cannot be met without knowledge the agent is allowed to use.",
                        answer_type=AnswerType.UPLOAD,
                        source_refs=refs,
                        blocking=True,
                    )
                )
            elif action == MappingResult.REQUIRES_HUMAN:
                qs.append(
                    self._q(
                        QuestionKind.BUSINESS_DECISION,
                        "handoff_rules",
                        f"'{req}' requires a human. Who receives it and how urgent is it?",
                        "A handoff destination must exist for requirements the agent may not fulfil alone.",
                        source_refs=refs,
                        blocking=True,
                    )
                )
            elif action == MappingResult.REQUIRES_TOOL:
                qs.append(
                    self._q(
                        QuestionKind.CAPABILITY_GAP,
                        path,
                        f"'{req}' needs a tool ({cap}). How should it be provided?",
                        "Without the tool the requirement is unreachable; this decides the integration class.",
                        answer_type=AnswerType.CHOICE,
                        options=[
                            "existing_integration_available",
                            "new_integration_required",
                            "handle_by_human",
                            "defer",
                        ],
                        source_refs=refs,
                        blocking=True,
                    )
                )
            elif action == MappingResult.UNSUPPORTED:
                qs.append(
                    self._q(
                        QuestionKind.CAPABILITY_GAP,
                        path,
                        f"'{req}' is not supported by the selected composition ({cap}).",
                        "Either the composition changes or the requirement is dropped.",
                        answer_type=AnswerType.CHOICE,
                        options=["change_composition", "drop_requirement"],
                        source_refs=refs,
                        blocking=True,
                    )
                )
            elif action == MappingResult.UNVERIFIED or state == "UNVERIFIED":
                qs.append(
                    self._q(
                        QuestionKind.CAPABILITY_GAP,
                        path,
                        f"'{req}' relies on an unverified capability ({cap}).",
                        "Unverified capabilities may fail live; verify or accept for simulation only.",
                        answer_type=AnswerType.CHOICE,
                        options=["run_capability_test", "choose_other_provider", "accept_for_simulation_only"],
                        source_refs=refs,
                    )
                )
        return qs

    # ------------------------------------------------------------------ util
    @staticmethod
    def _q(
        kind: QuestionKind,
        path: str,
        text: str,
        why: str,
        *,
        answer_type: AnswerType = AnswerType.FREE_TEXT,
        options: list[str] | None = None,
        proposed_default: Any | None = None,
        source_refs: list[str] | None = None,
        blocking: bool = False,
    ) -> CopilotQuestion:
        # QV-COP-007: never suggest business truth. Structure (CHOICE over enum values, CONFIRM_PROPOSAL of
        # outcome *labels*) is allowed; free-text defaults on business paths are stripped.
        if kind == QuestionKind.BUSINESS_DECISION and answer_type == AnswerType.FREE_TEXT:
            proposed_default = None
        if path.startswith(_BUSINESS_PATH_PREFIXES) and answer_type == AnswerType.FREE_TEXT:
            proposed_default = None
        return CopilotQuestion(
            question_id=question_id_for(path, text),
            kind=kind,
            priority=0,
            text=text,
            why_it_matters=why,
            target_path=path,
            answer_type=answer_type,
            options=options or [],
            proposed_default=proposed_default,
            source_refs=source_refs or [],
            blocking=blocking,
        )


def discovery_complete(questions: list[CopilotQuestion]) -> bool:
    """QV-COP-005 stop rule: no blocking question remains (optional/quality questions may remain)."""
    return not any(q.blocking for q in questions)


__all__ = [
    "DiscoveryEngine",
    "DiscoveryInputs",
    "QuestionPrioritizer",
    "discovery_complete",
    "question_id_for",
]
