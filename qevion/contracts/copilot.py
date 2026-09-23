"""`qevion.copilot.v1` — Configuration Copilot outputs (§14 QV-COP-015): the machine-readable side.

The Copilot produces two outputs that are never conflated: (A) a human explanation and (B) this
`BlueprintProposal`. Deterministic components own state; the LLM (if any) never mutates the Blueprint.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field

from qevion.contracts.activity import ActivityBlueprint, ReadinessState
from qevion.contracts.common import QevionModel, utc_now
from qevion.contracts.composition import MappingResult
from qevion.contracts.control import PreflightFinding
from qevion.contracts.knowledge import Contradiction, GapClass, KnowledgeGap
from qevion.contracts.policy import Decision


class QuestionKind(StrEnum):
    """Why the Copilot is asking (drives prioritization and explanation, QV-COP-003)."""

    BLOCKING_GAP = "blocking_gap"  # REQUIRED_FOR_EXECUTION / preflight BLOCK
    POLICY_RISK = "policy_risk"
    DATA_CONFLICT = "data_conflict"
    BUSINESS_DECISION = "business_decision"  # ASK_OWNER: Copilot must never fill it (QV-COP-006/007)
    CAPABILITY_GAP = "capability_gap"  # REQUIRES_TOOL / UNSUPPORTED / UNVERIFIED
    QUALITY = "quality"
    OPTIONAL = "optional"


class AnswerType(StrEnum):
    FREE_TEXT = "free_text"
    CHOICE = "choice"
    YES_NO = "yes_no"
    NUMBER = "number"
    UPLOAD = "upload"
    CONFIRM_PROPOSAL = "confirm_proposal"


class CopilotQuestion(QevionModel):
    """One prioritized question. `target_path` says which Blueprint element the answer will fill."""

    question_id: str
    kind: QuestionKind
    priority: int = Field(ge=0, description="lower = ask sooner; computed deterministically")
    text: str
    why_it_matters: str
    target_path: str = Field(description="Blueprint JSON path the answer resolves, e.g. policies.opt_out")
    answer_type: AnswerType = AnswerType.FREE_TEXT
    options: list[str] = Field(default_factory=list)
    proposed_default: Any | None = Field(
        default=None, description="a suggestion the operator may accept; never auto-applied for business decisions"
    )
    source_refs: list[str] = Field(
        default_factory=list, description="gap ids / finding paths / mapping capabilities that produced this question"
    )
    blocking: bool = False


class IntegrationClass(StrEnum):
    """QV-COP-009."""

    NO_INTEGRATION_NEEDED = "no_integration_needed"
    CONFIGURATION_ONLY = "configuration_only"
    EXISTING_INTEGRATION_AVAILABLE = "existing_integration_available"
    NEW_INTEGRATION_REQUIRED = "new_integration_required"
    NEW_CORE_CAPABILITY_REQUIRED = "new_core_capability_required"


class CapabilityRequirement(QevionModel):
    requirement: str
    required_capability: str
    current_state: str
    action: MappingResult
    integration: IntegrationClass


class ReadinessFinding(QevionModel):
    """QV-COP-011 'what could go wrong' finding."""

    category: str
    description: str
    severity: Literal["BLOCK", "WARN", "INFO"] = "WARN"
    mitigation: str | None = None
    related_paths: list[str] = Field(default_factory=list)


class DiscoveryStatus(StrEnum):
    ASKING = "asking"
    REVIEW = "review"  # stop-asking reached (QV-COP-004); operator reviews proposal
    BLOCKED = "blocked"


class BlueprintProposal(QevionModel):
    """QV-COP-015 (B). Every business-decision element in `draft` carries a Decision in `decisions`."""

    schema_: Literal["qevion.copilot.v1"] = Field(default="qevion.copilot.v1", alias="schema")
    proposal_id: str
    config_session_id: str
    tenant_id: str
    draft: ActivityBlueprint | None = None
    draft_valid: bool = False
    validation_errors: list[str] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    gaps: list[KnowledgeGap] = Field(default_factory=list)
    contradictions: list[Contradiction] = Field(default_factory=list)
    capability_requirements: list[CapabilityRequirement] = Field(default_factory=list)
    preflight_findings: list[PreflightFinding] = Field(default_factory=list)
    readiness_findings: list[ReadinessFinding] = Field(default_factory=list)
    simulation_cases: list[str] = Field(default_factory=list)
    questions: list[CopilotQuestion] = Field(default_factory=list, description="prioritized; empty when status=review")
    status: DiscoveryStatus = DiscoveryStatus.ASKING
    readiness_state: ReadinessState = ReadinessState.DRAFT
    produced_at: datetime = Field(default_factory=utc_now)

    @property
    def unapproved_decisions(self) -> list[Decision]:
        return [d for d in self.decisions if d.approved_by is None]

    def gap_counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for g in self.gaps:
            out[g.gap_class.value] = out.get(g.gap_class.value, 0) + 1
        return out


BLOCKING_GAP_CLASSES = frozenset({GapClass.REQUIRED_FOR_EXECUTION, GapClass.POLICY_RISK, GapClass.DATA_CONFLICT})

__all__ = [
    "BLOCKING_GAP_CLASSES",
    "AnswerType",
    "BlueprintProposal",
    "CapabilityRequirement",
    "CopilotQuestion",
    "DiscoveryStatus",
    "IntegrationClass",
    "QuestionKind",
    "ReadinessFinding",
]
