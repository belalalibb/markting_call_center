"""`qevion.tool.v1` and `qevion.tool_backend.v1` (§24 QV-TOOL). Tool pipeline: 11 steps, all evented."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import Field

from qevion.contracts.common import Provenance, QevionModel


class ToolImpact(StrEnum):
    READ = "read"
    WRITE = "write"
    ESCALATION = "escalation"


class PlatformTool(StrEnum):
    """Generic platform tools (§24). Business tools are Blueprint data, resolved to a backend."""

    LOOKUP_KNOWLEDGE = "lookup_knowledge"
    GET_ENTITY = "get_entity"
    LIST_ENTITIES = "list_entities"
    COMPARE_ENTITIES = "compare_entities"
    RECOMMEND = "recommend"
    CHECK_RULE = "check_rule"
    COMPUTE_QUOTE = "compute_quote"
    RECORD_FIELD = "record_field"
    VERIFY_FIELD = "verify_field"
    CLARIFY = "clarify"
    REQUEST_HANDOFF = "request_handoff"
    SUBMIT_RECORD = "submit_record"
    SCHEDULE_CALLBACK = "schedule_callback"
    COLLECT_QUESTION = "collect_question"


class ToolDeclaration(QevionModel):
    """What the model/provider sees. Rendered per provider by adapters; source of truth is here."""

    schema_: Literal["qevion.tool.v1"] = Field(default="qevion.tool.v1", alias="schema")
    tool_id: str
    description: str
    parameters: dict[str, Any] = Field(description="JSON Schema for arguments")
    impact: ToolImpact
    confirmation: Literal["none", "confirm_before_execute"] = "none"
    idempotency_key_fields: list[str] = Field(default_factory=list)
    timeout_ms: int = Field(default=5000, ge=100, le=60000)
    result_provenance: Provenance = Provenance.TOOL_VERIFIED


class ToolPipelineStep(StrEnum):
    """§24 11-step pipeline; each step emits a tool.* event."""

    RECEIVED = "received"
    SCHEMA_VALIDATED = "schema_validated"
    PERMISSION_CHECKED = "permission_checked"
    POLICY_CHECKED = "policy_checked"
    BUDGET_CHECKED = "budget_checked"
    DEDUPLICATED = "deduplicated"
    CONFIRMATION = "confirmation"
    EXECUTING = "executing"
    RESULT_VALIDATED = "result_validated"
    PROVENANCE_TAGGED = "provenance_tagged"
    RETURNED = "returned"


class ToolInvocation(QevionModel):
    call_id: str
    tool_id: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    session_id: str
    tenant_id: str
    activity_id: str
    turn_id: str | None = None
    idempotency_key: str | None = None
    requested_at_ms: int


class ToolOutcomeStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED_ARGS = "rejected_args"
    REJECTED_POLICY = "rejected_policy"
    REJECTED_BUDGET = "rejected_budget"
    CONFIRMATION_DENIED = "confirmation_denied"
    DUPLICATE = "duplicate"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"  # executed but result unknown (network); never claim success


class ToolOutcome(QevionModel):
    call_id: str
    tool_id: str
    status: ToolOutcomeStatus
    output: dict[str, Any] = Field(default_factory=dict)
    provenance: Provenance = Provenance.TOOL_VERIFIED
    error: str | None = None
    latency_ms: int | None = None
    step_reached: ToolPipelineStep = ToolPipelineStep.RETURNED


# ---- tool_backend.v1 --------------------------------------------------------


class ToolBackendKind(StrEnum):
    IN_MEMORY = "in_memory"
    FILE = "file"
    HTTP = "http"  # future
    KNOWLEDGE = "knowledge"
    ENTITY_STORE = "entity_store"


class ToolBackendBinding(QevionModel):
    """Maps a tool_id to a backend for one tenant/activity (Admin plane)."""

    schema_: Literal["qevion.tool_backend.v1"] = Field(default="qevion.tool_backend.v1", alias="schema")
    tenant_id: str
    tool_id: str
    backend: ToolBackendKind
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
