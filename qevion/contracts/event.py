"""`qevion.event.v1` — the only thing that crosses plane boundaries (§37, QV-EVT)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field

from qevion.contracts.common import QevionModel, new_id, utc_now


class EventKind(StrEnum):
    RUNTIME = "runtime"
    CONFIG = "config"
    CONTROL = "control"
    ADMIN = "admin"
    EVAL = "eval"


class Event(QevionModel):
    """Append-only, seq-ordered envelope. Never contains secrets, raw audio, or full transcripts (QV-EVT-003)."""

    schema_: Literal["qevion.event.v1"] = Field(default="qevion.event.v1", alias="schema")
    event_id: str = Field(default_factory=lambda: new_id("evt"))
    seq: int = Field(ge=0, description="Strictly increasing per session (QV-EVT-001)")
    ts: datetime = Field(default_factory=utc_now)
    trace_id: str | None = None
    tenant_id: str
    session_id: str | None = None
    line_id: str | None = None
    activity_id: str | None = None
    activity_version: str | None = None
    turn_id: str | None = None
    kind: EventKind
    type: str = Field(pattern=r"^[a-z_]+(\.[a-z_]+)+$", description="Dotted type from the §37.2 catalog")
    source: str = Field(
        description="core | transport:<name> | turn:<name> | provider:<role>:<name> | tool:<id> | copilot | control"
    )
    payload: dict[str, Any] = Field(default_factory=dict)


# Catalog constants (not an exhaustive enum; extensible per QV-EVT).
class EventType:
    SESSION_CREATED = "session.created"
    SESSION_STARTED = "session.started"
    SESSION_DEGRADED = "session.degraded"
    SESSION_RESUMED = "session.resumed"
    SESSION_ENDED = "session.ended"
    SESSION_LIMIT_ENFORCED = "session.limit_enforced"
    OUTBOUND_CONTACT_CHECKED = "outbound.contact_checked"  # QV-OUT-DIR-002 hook result (allowed/refusals)
    OUTBOUND_DIAL_STARTED = "outbound.dial_started"
    OUTBOUND_DIAL_RESULT = "outbound.dial_result"  # answered | no_answer | busy
    TRANSPORT_CONNECTED = "transport.connected"
    TRANSPORT_DISCONNECTED = "transport.disconnected"
    TRANSPORT_PLAYOUT_STARTED = "transport.playout_started"
    TRANSPORT_PLAYOUT_STOPPED = "transport.playout_stopped"
    USER_SPEECH_STARTED = "user.speech_started"
    USER_SPEECH_COMMITTED = "user.speech_committed"
    USER_SPEECH_DISCARDED = "user.speech_discarded"
    USER_CORRECTION = "user.correction"
    TURN_STARTED = "turn.started"
    TURN_ENDED = "turn.ended"
    ASSISTANT_RESPONSE_STARTED = "assistant.response_started"
    ASSISTANT_RESPONSE_ENDED = "assistant.response_ended"
    ASSISTANT_RESPONSE_CANCELLED = "assistant.response_cancelled"
    INTERRUPTION_DETECTED = "interruption.detected"
    STATE_CHANGED = "state.changed"
    FIELD_RECORDED = "field.recorded"
    FIELD_VERIFIED = "field.verified"
    FIELD_CORRECTED = "field.corrected"
    CLAIM_CHECKED = "claim.checked"
    POLICY_CHECKED = "policy.checked"
    COVERAGE_MISS = "coverage.miss"
    PROVIDER_SESSION_CREATED = "provider.session_created"
    PROVIDER_ERROR = "provider.error"
    PROVIDER_SESSION_CLOSED = "provider.session_closed"
    CAPABILITY_NEGOTIATED = "capability.negotiated"
    TOOL_REQUESTED = "tool.requested"
    TOOL_ARGS_INVALID = "tool.args_invalid"
    TOOL_POLICY_REJECTED = "tool.policy_rejected"
    TOOL_CONFIRMATION_REQUESTED = "tool.confirmation_requested"
    TOOL_CONFIRMATION_GRANTED = "tool.confirmation_granted"
    TOOL_CONFIRMATION_DENIED = "tool.confirmation_denied"
    TOOL_DUPLICATE_IGNORED = "tool.duplicate_ignored"
    TOOL_EXECUTION_STARTED = "tool.execution_started"
    TOOL_EXECUTION_COMPLETED = "tool.execution_completed"
    TOOL_EXECUTION_FAILED = "tool.execution_failed"
    TOOL_EXECUTION_UNKNOWN = "tool.execution_unknown"
    HANDOFF_REQUESTED = "handoff.requested"
    HANDOFF_ACKNOWLEDGED = "handoff.acknowledged"
    ROUTE_REQUESTED = "route.requested"
    OUTCOME_PRODUCED = "outcome.produced"
    INTERACTION_RECORD_PRODUCED = "interaction_record.produced"
    USAGE_RECORDED = "usage.recorded"
    BUDGET_WARNING = "budget.warning"
    BUDGET_EXCEEDED = "budget.exceeded"
    LATENCY_SAMPLE = "latency.sample"
    FAILURE_CLASSIFIED = "failure.classified"
    DECISION_MADE = "decision.made"
    CONFIG_SESSION_STARTED = "config.session_started"
    CONFIG_QUESTION_ASKED = "config.question_asked"
    CONFIG_ANSWER_RECEIVED = "config.answer_received"
    KNOWLEDGE_UPLOADED = "knowledge.uploaded"
    KNOWLEDGE_FACT_EXTRACTED = "knowledge.fact_extracted"
    KNOWLEDGE_CONFLICT_DETECTED = "knowledge.conflict_detected"
    KNOWLEDGE_GAP_DETECTED = "knowledge.gap_detected"
    BLUEPRINT_PROPOSED = "blueprint.proposed"
    BLUEPRINT_VALIDATED = "blueprint.validated"
    BLUEPRINT_VALIDATION_FAILED = "blueprint.validation_failed"
    ACTIVITY_READINESS_CHANGED = "activity.readiness_changed"
    CREDENTIAL_SCOPE_OPENED = "credential.scope_opened"
    CREDENTIAL_SCOPE_CLOSED = "credential.scope_closed"
    SIMULATION_STARTED = "simulation.started"
    SIMULATION_SCENARIO_RESULT = "simulation.scenario_result"
    SIMULATION_REPORT_PRODUCED = "simulation.report_produced"
    REPLAY_STARTED = "replay.started"
    REPLAY_DIVERGED = "replay.diverged"
    REPLAY_COMPLETED = "replay.completed"
