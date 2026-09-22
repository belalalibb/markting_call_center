"""Control-plane contracts: `qevion.preflight.v1` (§12 QV-PRE), readiness transitions (§10 QV-LIFE),
credential scopes (§39.6 QV-CRED), and the runtime state enums shared with Core (§19 QV-RT)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field

from qevion.contracts.activity import ReadinessState
from qevion.contracts.common import QevionModel, utc_now


class PreflightReason(StrEnum):
    """QV-PRE-002 minimum reason codes (20)."""

    MISSING_REQUIRED_KNOWLEDGE = "MISSING_REQUIRED_KNOWLEDGE"
    MISSING_REQUIRED_TOOL = "MISSING_REQUIRED_TOOL"
    TOOL_NOT_AUTHORIZED_FOR_TENANT = "TOOL_NOT_AUTHORIZED_FOR_TENANT"
    UNSUPPORTED_CAPABILITY = "UNSUPPORTED_CAPABILITY"
    UNSUPPORTED_LOCALE_COMBINATION = "UNSUPPORTED_LOCALE_COMBINATION"
    VOICE_UNAVAILABLE = "VOICE_UNAVAILABLE"
    CONTRADICTORY_POLICIES = "CONTRADICTORY_POLICIES"
    MISSING_OUTCOME_SCHEMA = "MISSING_OUTCOME_SCHEMA"
    IMPOSSIBLE_COMPLETION_CRITERIA = "IMPOSSIBLE_COMPLETION_CRITERIA"
    PROVIDER_CAPABILITY_UNAVAILABLE = "PROVIDER_CAPABILITY_UNAVAILABLE"
    INCOMPLETE_FIELD_DEFINITION = "INCOMPLETE_FIELD_DEFINITION"
    INCOMPATIBLE_CONFIRMATION_RULE = "INCOMPATIBLE_CONFIRMATION_RULE"
    UNDEFINED_ESCALATION = "UNDEFINED_ESCALATION"
    UNDEFINED_UNKNOWN_QUESTION_POLICY = "UNDEFINED_UNKNOWN_QUESTION_POLICY"
    UNAPPROVED_BUSINESS_DECISION = "UNAPPROVED_BUSINESS_DECISION"
    UNRESOLVED_KNOWLEDGE_CONFLICT = "UNRESOLVED_KNOWLEDGE_CONFLICT"
    INVALID_CONFIG = "INVALID_CONFIG"
    UNSUPPORTED_CHANNEL = "UNSUPPORTED_CHANNEL"
    CONTACT_POLICY_MISSING_FOR_OUTBOUND = "CONTACT_POLICY_MISSING_FOR_OUTBOUND"
    LICENSE_BLOCKED_COMPONENT = "LICENSE_BLOCKED_COMPONENT"


class PreflightFinding(QevionModel):
    reason: PreflightReason
    path: str = Field(description="JSON path into the Blueprint, e.g. tools.required[0]")
    message: str
    severity: Literal["BLOCK", "WARN"] = "BLOCK"
    fix_hint: str | None = None


class PreflightResult(QevionModel):
    schema_: Literal["qevion.preflight.v1"] = Field(default="qevion.preflight.v1", alias="schema")
    activity_id: str
    activity_version: str
    composition_id: str | None = None
    status: Literal["READY", "BLOCKED"]
    findings: list[PreflightFinding] = Field(default_factory=list)
    checked_at: datetime = Field(default_factory=utc_now)

    @property
    def blocking(self) -> list[PreflightFinding]:
        return [f for f in self.findings if f.severity == "BLOCK"]


# Legal readiness transitions (§10). Anything else → rejected (QV-ACC-013).
READINESS_TRANSITIONS: dict[ReadinessState, frozenset[ReadinessState]] = {
    ReadinessState.DRAFT: frozenset({ReadinessState.DISCOVERY_IN_PROGRESS, ReadinessState.RETIRED}),
    ReadinessState.DISCOVERY_IN_PROGRESS: frozenset(
        {
            ReadinessState.NEEDS_INFORMATION,
            ReadinessState.NEEDS_CONFIGURATION,
            ReadinessState.BLOCKED,
            ReadinessState.RETIRED,
        }
    ),
    ReadinessState.NEEDS_INFORMATION: frozenset(
        {
            ReadinessState.NEEDS_CONFIGURATION,
            ReadinessState.DISCOVERY_IN_PROGRESS,
            ReadinessState.BLOCKED,
            ReadinessState.RETIRED,
        }
    ),
    ReadinessState.NEEDS_CONFIGURATION: frozenset(
        {
            ReadinessState.NEEDS_INFORMATION,
            ReadinessState.BLOCKED,
            ReadinessState.READY_FOR_SIMULATION,
            ReadinessState.RETIRED,
        }
    ),
    ReadinessState.BLOCKED: frozenset(
        {ReadinessState.NEEDS_INFORMATION, ReadinessState.NEEDS_CONFIGURATION, ReadinessState.RETIRED}
    ),
    ReadinessState.READY_FOR_SIMULATION: frozenset(
        {
            ReadinessState.SIMULATION_FAILED,
            ReadinessState.READY_FOR_ACTIVATION,
            ReadinessState.BLOCKED,
            ReadinessState.RETIRED,
        }
    ),
    ReadinessState.SIMULATION_FAILED: frozenset(
        {ReadinessState.NEEDS_CONFIGURATION, ReadinessState.READY_FOR_SIMULATION, ReadinessState.RETIRED}
    ),
    ReadinessState.READY_FOR_ACTIVATION: frozenset(
        {ReadinessState.ACTIVE, ReadinessState.NEEDS_CONFIGURATION, ReadinessState.RETIRED}
    ),
    ReadinessState.ACTIVE: frozenset({ReadinessState.SUSPENDED, ReadinessState.RETIRED}),
    ReadinessState.SUSPENDED: frozenset({ReadinessState.ACTIVE, ReadinessState.RETIRED}),
    ReadinessState.RETIRED: frozenset(),
}


def can_transition(src: ReadinessState, dst: ReadinessState) -> bool:
    return dst in READINESS_TRANSITIONS.get(src, frozenset())


# ---- runtime state enums (§19) --------------------------------------------------


class DialogState(StrEnum):
    """Fixed dialog machine (QV-RT). Owns turn-taking, not business."""

    IDLE = "IDLE"
    LISTENING = "LISTENING"
    THINKING = "THINKING"
    SPEAKING = "SPEAKING"
    INTERRUPTED = "INTERRUPTED"
    WAITING_TOOL = "WAITING_TOOL"
    WAITING_CONFIRMATION = "WAITING_CONFIRMATION"
    CLOSED = "CLOSED"


class ActivityState(StrEnum):
    """Generic data-driven activity machine states (QV-RT)."""

    OPENING = "OPENING"
    ENGAGED = "ENGAGED"
    COLLECTING = "COLLECTING"
    RESOLVING = "RESOLVING"
    CLARIFYING = "CLARIFYING"
    CONFIRMING = "CONFIRMING"
    EXECUTING = "EXECUTING"
    CLOSING = "CLOSING"
    ENDED = "ENDED"
    ESCALATED = "ESCALATED"
    ABANDONED = "ABANDONED"
    BLOCKED = "BLOCKED"


TERMINAL_ACTIVITY_STATES = frozenset(
    {ActivityState.ENDED, ActivityState.ESCALATED, ActivityState.ABANDONED, ActivityState.BLOCKED}
)


# ---- credentials (§39.6, ADR-0002) ---------------------------------------------


class CredentialSource(StrEnum):
    ENV = "env"
    ADMIN_STORE = "admin_store"
    EPHEMERAL_UI = "ephemeral_ui"
    NONE = "none"


class CredentialScope(QevionModel):
    """What is logged/evented about a credential: NEVER the value (QV-CRED)."""

    provider: str
    source: CredentialSource
    tenant_id: str | None = None
    opened_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime | None = None
    fingerprint: str | None = Field(default=None, description="last-4 or hash prefix for support; never the key")
