"""`qevion.policy.v1` — behaviors, decisions and policy blocks shared by Blueprint and Core (§11 QV-POL)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field

from qevion.contracts.common import QevionModel, utc_now


class Behavior(StrEnum):
    """QV-POL-004 unknown-question / uncertainty behaviors. 'The model decides' is NOT a value."""

    ANSWER_FROM_APPROVED_KNOWLEDGE = "ANSWER_FROM_APPROVED_KNOWLEDGE"
    ASK_CLARIFYING_QUESTION = "ASK_CLARIFYING_QUESTION"
    STATE_LIMITATION = "STATE_LIMITATION"
    USE_AUTHORIZED_TOOL = "USE_AUTHORIZED_TOOL"
    ASK_OPERATOR_SOURCE = "ASK_OPERATOR_SOURCE"
    OFFER_HUMAN_HANDOFF = "OFFER_HUMAN_HANDOFF"
    COLLECT_QUESTION = "COLLECT_QUESTION"
    REQUEST_ADDITIONAL_INFORMATION = "REQUEST_ADDITIONAL_INFORMATION"
    CLOSE_GRACEFULLY = "CLOSE_GRACEFULLY"
    DECLINE_UNSUPPORTED_REQUEST = "DECLINE_UNSUPPORTED_REQUEST"


class ProposedBy(StrEnum):
    COPILOT = "copilot"
    OPERATOR = "operator"
    SOURCE_DOC = "source_doc"


class Decision(QevionModel):
    """QV-ACT-002: every business-decision element carries who proposed and who approved it."""

    item_path: str
    proposed_by: ProposedBy
    approved_by: str | None = Field(default=None, description="operator id; None = unapproved → blocks activation")
    ts: datetime = Field(default_factory=utc_now)
    rationale: str | None = None


class ClaimRule(QevionModel):
    claim_type: str
    scope: str = "activity"
    source_requirement: Literal["KNOWLEDGE_APPROVED", "TOOL_VERIFIED", "ANY_APPROVED"] | None = None


class Disclosure(QevionModel):
    when: str = Field(description="dialog/activity state name or trigger, e.g. OPENING")
    text_ref: str


class BehaviorOverride(QevionModel):
    topic_pattern: str
    behavior: Behavior


class UnknownQuestionPolicy(QevionModel):
    default: Behavior
    overrides: list[BehaviorOverride] = Field(default_factory=list)


class UncertaintyPolicy(QevionModel):
    missing: Behavior
    conflicting: Behavior
    stale: Behavior
    ambiguous: Behavior


class EscalationRule(QevionModel):
    trigger: str
    action: str
    priority: Literal["low", "normal", "high", "urgent"] = "normal"


class OptOutPolicy(QevionModel):
    phrases_ref: str
    action: Behavior = Behavior.CLOSE_GRACEFULLY


class ContactPolicyHooks(QevionModel):
    """Outbound-only hooks (ADR-0003)."""

    consent_required: bool = True
    attempt_limit: int = Field(default=2, ge=1, le=10)
    contact_window: str | None = Field(default=None, description='e.g. "10:00-20:00 Africa/Cairo"')
    suppression_ref: str | None = None


class PolicyBlock(QevionModel):
    schema_: Literal["qevion.policy.v1"] = Field(default="qevion.policy.v1", alias="schema")
    allowed_claims: list[ClaimRule] = Field(default_factory=list)
    prohibited_claims: list[ClaimRule] = Field(default_factory=list)
    disclosures: list[Disclosure] = Field(default_factory=list)
    clarification_policy: Literal["always_when_ambiguous", "when_high_impact"] = "always_when_ambiguous"
    unknown_question_policy: UnknownQuestionPolicy
    uncertainty_policy: UncertaintyPolicy
    escalation: list[EscalationRule] = Field(default_factory=list)
    opt_out: OptOutPolicy | None = None
    contact_policy_hooks: ContactPolicyHooks | None = None
