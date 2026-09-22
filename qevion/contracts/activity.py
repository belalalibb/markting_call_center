"""`qevion.activity.v1` — the Activity Blueprint (§9 QV-ACT). Business execution contract; Core-neutral."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, model_validator

from qevion.contracts.common import Channel, Direction, Provenance, QevionModel, Sensitivity
from qevion.contracts.policy import Decision, PolicyBlock


class ReadinessState(StrEnum):
    """§10 lifecycle (QV-LIFE)."""

    DRAFT = "DRAFT"
    DISCOVERY_IN_PROGRESS = "DISCOVERY_IN_PROGRESS"
    NEEDS_INFORMATION = "NEEDS_INFORMATION"
    NEEDS_CONFIGURATION = "NEEDS_CONFIGURATION"
    BLOCKED = "BLOCKED"
    READY_FOR_SIMULATION = "READY_FOR_SIMULATION"
    SIMULATION_FAILED = "SIMULATION_FAILED"
    READY_FOR_ACTIVATION = "READY_FOR_ACTIVATION"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    RETIRED = "RETIRED"


class Identity(QevionModel):
    tenant_id: str
    line_id: str | None = None
    activity_id: str
    name: str
    description: str = ""
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    status: ReadinessState = ReadinessState.DRAFT


class Pronunciation(QevionModel):
    term: str
    hint: str
    scope: str = "activity"


class Locale(QevionModel):
    language: str = Field(min_length=2, max_length=3)
    locale: str = Field(pattern=r"^[a-z]{2,3}-[A-Z]{2}$")
    dialect: str | None = None
    locale_pack_ref: str | None = None
    voice_profile_ref: str | None = None
    pronunciation: list[Pronunciation] = Field(default_factory=list)


class ObjectiveItem(QevionModel):
    kind: str
    description: str = ""


class OptimizationBounds(QevionModel):
    truthfulness: Literal["required"] = "required"
    no_invented_urgency: bool = True
    respect_opt_out: bool = True


class Objective(QevionModel):
    primary: ObjectiveItem
    secondary: list[ObjectiveItem] = Field(default_factory=list)
    optimization_bounds: OptimizationBounds = Field(default_factory=OptimizationBounds)


class FieldSpec(QevionModel):
    """A datum the Activity needs. Names are Activity data; Core never knows them (QV-ACT-004)."""

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    type: Literal["string", "integer", "number", "boolean", "date", "datetime", "enum", "entity_ref", "list"]
    validation: str | None = Field(default=None, description="expression or rule ref evaluated by decision port")
    enum_values: list[str] | None = None
    clarification_hint: str | None = None
    provenance_required: Provenance = Provenance.USER_STATED
    sensitivity: Sensitivity = Sensitivity.LOW


class DataBlock(QevionModel):
    required: list[FieldSpec] = Field(default_factory=list)
    optional: list[FieldSpec] = Field(default_factory=list)


class KnowledgeSourceRef(QevionModel):
    source_id: str
    kind: Literal["file", "structured", "api"]
    version: str | None = None
    priority: int = Field(default=100, ge=0)


class KnowledgeRequirement(QevionModel):
    domain: str
    description: str = ""
    status: Literal["SATISFIED", "MISSING", "PARTIAL"] = "MISSING"


class Freshness(QevionModel):
    max_age_days: int | None = None
    stale_behavior: str = "STATE_LIMITATION"


class KnowledgeBlock(QevionModel):
    sources: list[KnowledgeSourceRef] = Field(default_factory=list)
    requirements: list[KnowledgeRequirement] = Field(default_factory=list)
    source_priority: list[str] = Field(
        default_factory=lambda: ["live_api", "approved_structured", "approved_document", "historical"]
    )
    freshness: Freshness = Field(default_factory=Freshness)


class ToolRef(QevionModel):
    tool_id: str
    purpose: str = ""


class ToolPermission(QevionModel):
    impact: Literal["read", "write", "escalation"]
    confirmation: Literal["none", "confirm_before_execute"] = "none"
    authorization_scope: str = "activity"


class ToolsBlock(QevionModel):
    required: list[ToolRef] = Field(default_factory=list)
    optional: list[ToolRef] = Field(default_factory=list)
    permissions: dict[str, ToolPermission] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _every_tool_has_permission(self) -> ToolsBlock:
        ids = {t.tool_id for t in self.required + self.optional}
        missing = sorted(ids - set(self.permissions))
        if missing:
            raise ValueError(f"tools without permissions entry: {missing}")
        return self


class CoverageQuestion(QevionModel):
    id: str
    category: str
    entity_ref: str | None = None
    pattern: str
    handling: Literal["KNOWLEDGE", "TOOL", "CLARIFY", "LIMITATION", "HANDOFF"]
    answer_ref: str | None = None
    status: Literal["COVERED", "ASK_OWNER", "DECLINED"] = "ASK_OWNER"


class CoverageObjection(QevionModel):
    id: str
    pattern: str
    approved_response_ref: str | None = None
    allowed_alternatives: list[str] = Field(default_factory=list)
    status: Literal["COVERED", "ASK_OWNER", "DECLINED"] = "ASK_OWNER"


class CoverageException(QevionModel):
    id: str
    situation: str
    behavior: str


class CoverageBlock(QevionModel):
    questions: list[CoverageQuestion] = Field(default_factory=list)
    objections: list[CoverageObjection] = Field(default_factory=list)
    exceptions: list[CoverageException] = Field(default_factory=list)


class Completion(QevionModel):
    success_rules: list[str] = Field(default_factory=list)
    failure_rules: list[str] = Field(default_factory=list)
    exit_rules: list[str] = Field(default_factory=list)


class OutcomeField(QevionModel):
    name: str
    source_field: str | None = None
    required: bool = False


class OutcomeSchema(QevionModel):
    primary: list[str] = Field(min_length=1)
    secondary: list[str] = Field(default_factory=list)
    fields: list[OutcomeField] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=lambda: ["close"])


class HandoffRule(QevionModel):
    trigger: str
    destination_ref: str
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    context_projection: list[str] = Field(default_factory=list)


class ActivityMachineRef(QevionModel):
    table_ref: str | None = "generic_default_v1"
    inline: dict[str, Any] | None = None


class ConstrainedFlow(QevionModel):
    enabled: bool = False
    steps: list[str] = Field(default_factory=list)


class Evaluation(QevionModel):
    cases: list[str] = Field(default_factory=list)
    simulation_personas: list[str] = Field(default_factory=list)
    adversarial_cases: list[str] = Field(default_factory=list)


class Pinned(QevionModel):
    policy_versions: dict[str, str] = Field(default_factory=dict)
    knowledge_versions: dict[str, str] = Field(default_factory=dict)
    locale_pack: str | None = None
    voice_profile: str | None = None
    composition_config: str | None = None


class Readiness(QevionModel):
    state: ReadinessState = ReadinessState.DRAFT
    preflight_result_ref: str | None = None
    simulation_report_ref: str | None = None


class VersionMetadata(QevionModel):
    sources: list[str] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    rejected_suggestions: list[str] = Field(default_factory=list)
    pinned: Pinned = Field(default_factory=Pinned)
    readiness: Readiness = Field(default_factory=Readiness)


class ActivityBlueprint(QevionModel):
    """Top-level `qevion.activity.v1` (§9.1)."""

    schema_: Literal["qevion.activity.v1"] = Field(default="qevion.activity.v1", alias="schema")
    identity: Identity
    direction: Direction
    channels: list[Channel] = Field(min_length=1)
    locale: Locale
    objective: Objective
    data: DataBlock = Field(default_factory=DataBlock)
    knowledge: KnowledgeBlock = Field(default_factory=KnowledgeBlock)
    tools: ToolsBlock = Field(default_factory=ToolsBlock)
    policies: PolicyBlock
    coverage: CoverageBlock = Field(default_factory=CoverageBlock)
    completion: Completion = Field(default_factory=Completion)
    outcome_schema: OutcomeSchema
    handoff_rules: list[HandoffRule] = Field(default_factory=list)
    activity_machine: ActivityMachineRef = Field(default_factory=ActivityMachineRef)
    constrained_flow: ConstrainedFlow | None = None
    evaluation: Evaluation = Field(default_factory=Evaluation)
    version_metadata: VersionMetadata = Field(default_factory=VersionMetadata)

    @model_validator(mode="after")
    def _outbound_needs_contact_hooks(self) -> ActivityBlueprint:
        if self.direction == Direction.OUTBOUND and self.policies.contact_policy_hooks is None:
            raise ValueError("outbound activity requires policies.contact_policy_hooks (ADR-0003)")
        return self

    def unapproved_decisions(self) -> list[Decision]:
        return [d for d in self.version_metadata.decisions if d.approved_by is None]
