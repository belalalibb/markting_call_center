"""Claim Governor (§23 QV-TRUTH) and Confirmation Interpreter (§25 QV-CONF).

Both delegate judgement to the `decision.v1` port (deterministic-first, ADR-0004) and apply the
Blueprint's policies. They never consult the model as an authority.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from qevion.contracts.common import Provenance
from qevion.contracts.outcome import ClaimDecisionEntry
from qevion.contracts.policy import Behavior, PolicyBlock
from qevion.contracts.ports import DecisionPort
from qevion.contracts.provider import DecisionKind, DecisionRequest, DecisionSource


@dataclass
class ClaimCheck:
    claim_type: str
    state: str  # allowed | blocked | rewritten | unknown
    action: str  # speak | suppress | apply:<Behavior>
    reason: str | None = None


@dataclass
class ClaimGovernor:
    """Gate for any assistant statement that asserts a business fact (QV-ACC-008)."""

    policies: PolicyBlock
    decision: DecisionPort
    log: list[ClaimDecisionEntry] = field(default_factory=list)

    def _allowed_map(self) -> dict[str, str | None]:
        return {c.claim_type: c.source_requirement for c in self.policies.allowed_claims}

    async def check(self, claim_type: str, provenance: Provenance, ts_ms: int) -> ClaimCheck:
        req = DecisionRequest(
            kind=DecisionKind.CHECK_CLAIM,
            inputs={
                "claim_type": claim_type,
                "provenance": provenance.value,
                "allowed": self._allowed_map(),
                "prohibited": [c.claim_type for c in self.policies.prohibited_claims],
            },
        )
        res = await self.decision.decide(req)
        if res.source is DecisionSource.UNKNOWN:
            check = ClaimCheck(
                claim_type, "unknown", f"apply:{self.policies.uncertainty_policy.ambiguous.value}", res.reason
            )
        elif res.value == "allowed":
            check = ClaimCheck(claim_type, "allowed", "speak")
        else:
            beh = self._miss_behavior(claim_type, provenance)
            check = ClaimCheck(claim_type, "blocked", f"apply:{beh.value}", res.reason)
        self.log.append(ClaimDecisionEntry(ts_ms=ts_ms, claim_type=claim_type, state=check.state, action=check.action))  # type: ignore[arg-type]
        return check

    def _miss_behavior(self, claim_type: str, provenance: Provenance) -> Behavior:
        if provenance in (Provenance.UNKNOWN, Provenance.UNVERIFIED):
            return self.policies.uncertainty_policy.missing
        for o in self.policies.unknown_question_policy.overrides:
            if o.topic_pattern.lower() in claim_type.lower():
                return o.behavior
        return self.policies.unknown_question_policy.default

    def behavior_for_unknown_topic(self, topic: str) -> Behavior:
        """Coverage miss → which configured behavior applies (QV-POL-004)."""
        for o in self.policies.unknown_question_policy.overrides:
            if o.topic_pattern.lower() in topic.lower():
                return o.behavior
        return self.policies.unknown_question_policy.default


@dataclass
class ConfirmationResult:
    value: bool | None  # True confirmed, False denied, None ambiguous
    confidence: float
    source: DecisionSource
    reason: str | None = None

    @property
    def ambiguous(self) -> bool:
        return self.value is None


@dataclass
class ConfirmationInterpreter:
    decision: DecisionPort
    yes_phrases: list[str] = field(default_factory=list)
    no_phrases: list[str] = field(default_factory=list)

    async def interpret(self, text: str, *, extra: dict[str, Any] | None = None) -> ConfirmationResult:
        req = DecisionRequest(
            kind=DecisionKind.INTERPRET_CONFIRMATION,
            inputs={"text": text, "yes_phrases": self.yes_phrases, "no_phrases": self.no_phrases, **(extra or {})},
        )
        res = await self.decision.decide(req)
        if res.source is DecisionSource.UNKNOWN or res.value is None:
            return ConfirmationResult(None, 0.0, DecisionSource.UNKNOWN, res.reason)
        return ConfirmationResult(bool(res.value), res.confidence, res.source, res.reason)
