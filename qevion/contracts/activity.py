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


# --- part 2 appended below ---
