"""Deterministic rules `DecisionPort` — the default and authoritative decision adapter (ADR-0004).

No LLM. Pure functions over Blueprint-supplied rules. Replayable. When it cannot decide it returns
``source=UNKNOWN`` so Core applies `uncertainty_policy`; it never guesses.
"""

from __future__ import annotations

import re
from typing import Any

from qevion.contracts.composition import AdapterCapabilities, Capability, CapabilityState
from qevion.contracts.provider import DecisionKind, DecisionRequest, DecisionResult, DecisionSource, ProviderRole

_RANGE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*\.\.\s*(-?\d+(?:\.\d+)?)\s*$")
_MAXLEN = re.compile(r"^\s*max\s+(\d+)\s+chars?\s*$", re.I)

# Locale-neutral seed lexicons; LocalePack phrases are passed in `inputs["yes_phrases"]` / `["no_phrases"]`.
_YES = {
    "yes",
    "yeah",
    "yep",
    "correct",
    "right",
    "ok",
    "okay",
    "sure",
    "confirm",
    "confirmed",
    "أيوه",
    "ايوه",
    "نعم",
    "تمام",
    "صح",
    "ماشي",
    "اه",
    "آه",
}
_NO = {"no", "nope", "wrong", "incorrect", "cancel", "not", "لا", "لأ", "غلط", "مش", "ما", "لاء"}


def _tokens(text: str) -> list[str]:
    return re.findall(r"[\w\u0600-\u06FF']+", text.lower())


class RulesDecisionAdapter:
    name = "rules"

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            adapter=self.name,
            role=ProviderRole.DECISION,
            capabilities=[Capability(name=f"decision:{k.value}", state=CapabilityState.SUPPORTED) for k in DecisionKind]
            + [
                Capability(
                    name="language:ar-EG", state=CapabilityState.PARTIAL, notes="seed lexicon; LocalePack extends"
                )
            ],
        )

    async def decide(self, request: DecisionRequest) -> DecisionResult:
        handler = getattr(self, f"_{request.kind.value}", None)
        if handler is None:
            return DecisionResult(value=None, confidence=0.0, source=DecisionSource.UNKNOWN, reason="unsupported kind")
        result: DecisionResult = handler(request)
        return result

    # ---- validate_field ------------------------------------------------------
    def _validate_field(self, req: DecisionRequest) -> DecisionResult:
        value = req.inputs.get("value")
        ftype = str(req.inputs.get("type", "string"))
        rule = req.inputs.get("validation") or (req.rules[0] if req.rules else None)
        enum_values = req.inputs.get("enum_values") or req.options

        coerced, ok = _coerce(value, ftype)
        if not ok:
            return DecisionResult(value=None, source=DecisionSource.RULE, reason=f"type mismatch: expected {ftype}")
        if ftype == "enum" and enum_values and coerced not in enum_values:
            return DecisionResult(value=None, source=DecisionSource.RULE, reason="not in enum")
        if rule in (None, "", "none"):
            return DecisionResult(value=coerced, source=DecisionSource.RULE, evidence_refs=["rule:none"])
        rule_s = str(rule)
        if m := _RANGE.match(rule_s):
            lo, hi = float(m.group(1)), float(m.group(2))
            if isinstance(coerced, int | float) and lo <= float(coerced) <= hi:
                return DecisionResult(value=coerced, source=DecisionSource.RULE, evidence_refs=[f"rule:{rule_s}"])
            return DecisionResult(value=None, source=DecisionSource.RULE, reason=f"out of range {rule_s}")
        if m := _MAXLEN.match(rule_s):
            if isinstance(coerced, str) and len(coerced) <= int(m.group(1)):
                return DecisionResult(value=coerced, source=DecisionSource.RULE, evidence_refs=[f"rule:{rule_s}"])
            return DecisionResult(value=None, source=DecisionSource.RULE, reason=f"violates {rule_s}")
        if rule_s.startswith("must_be_true"):
            ok2 = coerced is True
            return DecisionResult(
                value=coerced if ok2 else None,
                source=DecisionSource.RULE,
                reason=None if ok2 else "must be true",
                evidence_refs=[f"rule:{rule_s}"],
            )
        if rule_s.startswith("regex:"):
            pat = rule_s[len("regex:") :]
            if isinstance(coerced, str) and re.fullmatch(pat, coerced):
                return DecisionResult(value=coerced, source=DecisionSource.RULE, evidence_refs=[f"rule:{rule_s}"])
            return DecisionResult(value=None, source=DecisionSource.RULE, reason="regex mismatch")
        # Unknown rule grammar → cannot decide deterministically.
        return DecisionResult(
            value=None, confidence=0.0, source=DecisionSource.UNKNOWN, reason=f"unknown rule grammar: {rule_s}"
        )

    # ---- interpret_confirmation -------------------------------------------------
    def _interpret_confirmation(self, req: DecisionRequest) -> DecisionResult:
        text = str(req.inputs.get("text", ""))
        yes = _YES | {p.lower() for p in req.inputs.get("yes_phrases", [])}
        no = _NO | {p.lower() for p in req.inputs.get("no_phrases", [])}
        toks = _tokens(text)
        y = sum(t in yes for t in toks)
        n = sum(t in no for t in toks)
        if y and not n:
            return DecisionResult(value=True, confidence=min(1.0, 0.7 + 0.1 * y), source=DecisionSource.RULE)
        if n and not y:
            return DecisionResult(value=False, confidence=min(1.0, 0.7 + 0.1 * n), source=DecisionSource.RULE)
        return DecisionResult(
            value=None, confidence=0.0, source=DecisionSource.UNKNOWN, reason="ambiguous confirmation"
        )

    # ---- classify_intent (closed options, keyword match only) -----------------------
    def _classify_intent(self, req: DecisionRequest) -> DecisionResult:
        text = " ".join(_tokens(str(req.inputs.get("text", ""))))
        patterns: dict[str, list[str]] = req.inputs.get("patterns", {})
        hits = [
            (opt, sum(1 for kw in kws if kw.lower() in text))
            for opt, kws in patterns.items()
            if opt in req.options or not req.options
        ]
        hits = [h for h in hits if h[1] > 0]
        if len(hits) == 1 or (
            len(hits) > 1 and sorted(hits, key=lambda h: -h[1])[0][1] > sorted(hits, key=lambda h: -h[1])[1][1]
        ):
            best = max(hits, key=lambda h: h[1])
            return DecisionResult(
                value=best[0], confidence=0.8, source=DecisionSource.RULE, evidence_refs=[f"kw:{best[1]}"]
            )
        return DecisionResult(
            value=None, confidence=0.0, source=DecisionSource.UNKNOWN, reason="no/ambiguous keyword match"
        )

    # ---- check_claim ---------------------------------------------------------------
    def _check_claim(self, req: DecisionRequest) -> DecisionResult:
        claim_type = str(req.inputs.get("claim_type", ""))
        provenance = str(req.inputs.get("provenance", "UNKNOWN"))
        allowed: dict[str, str | None] = req.inputs.get("allowed", {})  # claim_type -> source_requirement
        prohibited: set[str] = set(req.inputs.get("prohibited", []))
        if claim_type in prohibited:
            return DecisionResult(value="blocked", source=DecisionSource.RULE, reason="prohibited claim")
        if claim_type not in allowed:
            return DecisionResult(value="blocked", source=DecisionSource.RULE, reason="claim type not allowed")
        need = allowed[claim_type]
        ok = (
            need is None
            or need == "ANY_APPROVED"
            and provenance in {"KNOWLEDGE_APPROVED", "TOOL_VERIFIED"}
            or need == provenance
        )
        return DecisionResult(
            value="allowed" if ok else "blocked",
            source=DecisionSource.RULE,
            reason=None if ok else f"needs {need}, got {provenance}",
        )

    # ---- evaluate_rule (tiny boolean grammar over fields) ------------------------------
    def _evaluate_rule(self, req: DecisionRequest) -> DecisionResult:
        fields: dict[str, Any] = req.inputs.get("fields", {})
        recorded: set[str] = set(req.inputs.get("recorded", fields.keys()))
        flags: set[str] = set(req.inputs.get("flags", []))
        results = []
        for rule in req.rules:
            v = _eval_rule(rule, fields, recorded, flags)
            if v is None:
                return DecisionResult(
                    value=None, confidence=0.0, source=DecisionSource.UNKNOWN, reason=f"cannot evaluate: {rule}"
                )
            results.append(v)
        return DecisionResult(
            value=all(results) if results else False,
            source=DecisionSource.RULE,
            evidence_refs=[f"rules:{len(results)}"],
        )

    # ---- next_activity_state -----------------------------------------------------------
    def _next_activity_state(self, req: DecisionRequest) -> DecisionResult:
        table: dict[str, dict[str, str]] = req.inputs.get("table", {})
        state = str(req.inputs.get("state", ""))
        trigger = str(req.inputs.get("trigger", ""))
        nxt = table.get(state, {}).get(trigger)
        if nxt is None:
            return DecisionResult(value=None, confidence=0.0, source=DecisionSource.UNKNOWN, reason="no transition")
        return DecisionResult(value=nxt, source=DecisionSource.RULE, evidence_refs=[f"table:{state}->{trigger}"])


def _coerce(value: Any, ftype: str) -> tuple[Any, bool]:
    try:
        match ftype:
            case "integer":
                if isinstance(value, bool):
                    return None, False
                if isinstance(value, int):
                    return value, True
                if isinstance(value, str) and re.fullmatch(r"-?\d+", value.strip()):
                    return int(value), True
                return None, False
            case "number":
                if isinstance(value, bool):
                    return None, False
                return float(value), True
            case "boolean":
                if isinstance(value, bool):
                    return value, True
                if isinstance(value, str) and value.strip().lower() in {"true", "yes", "1"}:
                    return True, True
                if isinstance(value, str) and value.strip().lower() in {"false", "no", "0"}:
                    return False, True
                return None, False
            case "list":
                return (list(value), True) if isinstance(value, list | tuple) else (None, False)
            case _:
                return (str(value), True) if value is not None else (None, False)
    except (TypeError, ValueError):
        return None, False


_CMP = re.compile(r"^\s*(\w+)\s*(==|!=|>=|<=|>|<)\s*(.+?)\s*$")


def _eval_rule(rule: str, fields: dict[str, Any], recorded: set[str], flags: set[str]) -> bool | None:
    """Grammar: `A AND B`, `field == literal`, `field recorded`, `a..b recorded` (prefix range), bare flag name."""
    if " AND " in rule:
        parts = [_eval_rule(p, fields, recorded, flags) for p in rule.split(" AND ")]
        return None if any(p is None for p in parts) else all(bool(p) for p in parts)
    r = rule.strip()
    if r.endswith(" recorded"):
        target = r[: -len(" recorded")].strip()
        if ".." in target:  # e.g. q1..q5 → any recorded field starting with the common prefix
            a, b = target.split("..", 1)
            prefix = re.match(r"^[a-z_]+?(?=\d)", a)
            pre = prefix.group(0) if prefix else a
            lo, hi = int(re.sub(r"\D", "", a) or 0), int(re.sub(r"\D", "", b) or 0)
            return all(any(f.startswith(f"{pre}{i}") for f in recorded) for i in range(lo, hi + 1))
        return target in recorded
    if r.endswith(" accepted"):
        return f"{r[: -len(' accepted')].strip()}_accepted" in flags
    if m := _CMP.match(r):
        name, op, lit = m.groups()
        if name not in fields:
            return False
        left = fields[name]
        right: Any = {"true": True, "false": False}.get(lit.lower(), lit.strip("'\""))
        if isinstance(left, int | float) and not isinstance(left, bool):
            try:
                right = float(right)
            except (TypeError, ValueError):
                return None
        return bool(
            {
                "==": left == right,
                "!=": left != right,
                ">": left > right,
                "<": left < right,
                ">=": left >= right,
                "<=": left <= right,
            }[op]
        )
    if re.fullmatch(r"[a-z_]+", r):
        return r in flags
    return None
