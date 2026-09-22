"""`qevion.metrics.v1`, `qevion.usage.v1` (§41–§42), `qevion.simulation_report.v1` (§17), latency watermarks (§31)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field

from qevion.contracts.common import QevionModel, utc_now


class Watermark(StrEnum):
    """The 5 interruption timestamps (§31 QV-INT) + core latency marks (§42 QV-PERF)."""

    T0_USER_SPEECH_ONSET = "t0_user_speech_onset"
    T1_BARGE_IN_DETECTED = "t1_barge_in_detected"
    T2_CANCEL_SENT_TO_PROVIDER = "t2_cancel_sent"
    T3_PLAYOUT_STOPPED_CLIENT = "t3_playout_stopped"
    T4_STATE_RECONCILED = "t4_state_reconciled"
    USER_SPEECH_END = "user_speech_end"
    PROVIDER_FIRST_AUDIO = "provider_first_audio"
    CLIENT_FIRST_PLAYOUT = "client_first_playout"
    TOOL_REQUESTED = "tool_requested"
    TOOL_RETURNED = "tool_returned"


class LatencySample(QevionModel):
    schema_: Literal["qevion.metrics.v1"] = Field(default="qevion.metrics.v1", alias="schema")
    session_id: str
    segment: str = Field(description="e.g. barge_in_to_playout_stop, speech_end_to_first_audio")
    watermark_from: Watermark
    watermark_to: Watermark
    value_ms: int = Field(ge=0)
    turn_id: str | None = None
    provider: str | None = None


class LatencyStats(QevionModel):
    segment: str
    count: int
    p50_ms: float
    p95_ms: float
    max_ms: int
    target_ms: int | None = None
    passed: bool | None = None


class UsageRecord(QevionModel):
    """Cost accounting per session (QV-COST). Estimated unless provider returns exact usage."""

    schema_: Literal["qevion.usage.v1"] = Field(default="qevion.usage.v1", alias="schema")
    session_id: str
    tenant_id: str
    provider: str
    role: str
    audio_in_seconds: float = 0
    audio_out_seconds: float = 0
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls: int = 0
    estimated_usd: float = 0
    exact: bool = False
    recorded_at: datetime = Field(default_factory=utc_now)


class FailureClass(StrEnum):
    """§27 QV-ERR / Recovery Protocol §9 classification."""

    TEST_ENVIRONMENT = "test_environment"
    PROVIDER = "provider"
    TRANSPORT = "transport"
    CONFIGURATION = "configuration"
    KNOWLEDGE = "knowledge"
    CORE_LOGIC = "core_logic"
    BUDGET = "budget"
    SECURITY = "security"
    UNKNOWN = "unknown"


class ScenarioResult(QevionModel):
    scenario_id: str
    passed: bool
    outcome_primary: str | None = None
    expected_primary: str | None = None
    turns: int = 0
    violations: list[str] = Field(default_factory=list)
    latency: list[LatencyStats] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    failure_class: FailureClass | None = None


class SimulationReport(QevionModel):
    schema_: Literal["qevion.simulation_report.v1"] = Field(default="qevion.simulation_report.v1", alias="schema")
    report_id: str
    tenant_id: str
    activity_id: str
    activity_version: str
    composition_id: str
    scenarios: list[ScenarioResult]
    passed: bool
    blocking_reasons: list[str] = Field(default_factory=list)
    produced_at: datetime = Field(default_factory=utc_now)
    extra: dict[str, Any] = Field(default_factory=dict)
