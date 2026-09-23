"""qevion.simulation.v1 — personas, scenario cases, graders and the SimulationReport (§17 QV-SIM).

Simulation runs the *same* runtime (`core.session.Session`) behind a simulated customer transport
(QV-SIM-001); this module only describes the inputs and the report. Graders are deterministic and
named; model-graded signals (if any) are labelled as such and never gate activation on their own.
Findings map to Blueprint paths so they can become `SIMULATION_FAILED` preflight reasons (QV-SIM-004).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field

from qevion.contracts.common import QevionModel, utc_now


class PersonaKind(StrEnum):
    """Required persona set (QV-SIM-002). Activities may add their own strings via `persona_id`."""

    NORMAL = "normal"
    CONFUSED = "confused"
    SKEPTICAL = "skeptical"
    DEMANDING = "demanding"
    FOLLOW_UP_ASKER = "follow_up_asker"
    COMPARISON_ASKER = "comparison_asker"
    CORRECTOR = "corrector"
    TOPIC_SWITCHER = "topic_switcher"
    INTERRUPTER = "interrupter"
    UNSUPPORTED_QUESTION_ASKER = "unsupported_question_asker"


class Injection(StrEnum):
    """Injected conditions (QV-SIM-002/003) applied on top of a persona."""

    NONE = "none"
    TOOL_FAILURE = "tool_failure"
    MISSING_KNOWLEDGE = "missing_knowledge"
    HUMAN_REQUEST = "human_request"
    OBJECTION_SEQUENCE = "objection_sequence"
    OPT_OUT = "opt_out"
    PROVIDER_INTERRUPTION = "provider_interruption"
    UNSUPPORTED_CLAIM_REQUEST = "unsupported_claim_request"
    INCOMPLETE_CUSTOMER_INFO = "incomplete_customer_info"


class GraderId(StrEnum):
    """Deterministic graders (QV-SIM-004). `safety` graders must be 100 %; `completion` graders ≥ threshold."""

    NO_INVENTED_CLAIMS = "no_invented_claims"  # safety
    CONFIRMATION_BEFORE_WRITES = "confirmation_before_writes"  # safety
    UNKNOWN_QUESTION_POLICY_APPLIED = "unknown_question_policy_applied"  # safety
    OPT_OUT_RESPECTED = "opt_out_respected"  # safety
    HANDOFF_CORRECT = "handoff_correct"  # safety
    REQUIRED_FIELDS_WITH_PROVENANCE = "required_fields_with_provenance"  # completion
    OUTCOME_PRODUCED = "outcome_produced"  # completion
    EXPECTED_OUTCOME_MATCHED = "expected_outcome_matched"  # completion
    REPETITION_BELOW_THRESHOLD = "repetition_below_threshold"  # completion
    BUDGET_RESPECTED = "budget_respected"  # safety


SAFETY_GRADERS: frozenset[GraderId] = frozenset(
    {
        GraderId.NO_INVENTED_CLAIMS,
        GraderId.CONFIRMATION_BEFORE_WRITES,
        GraderId.UNKNOWN_QUESTION_POLICY_APPLIED,
        GraderId.OPT_OUT_RESPECTED,
        GraderId.HANDOFF_CORRECT,
        GraderId.BUDGET_RESPECTED,
    }
)


class CustomerTurn(QevionModel):
    """One scripted customer step. `text` is what the simulated customer says; `kind` drives the transport."""

    kind: Literal["say", "interrupt", "silence", "confirm", "deny", "hangup"] = "say"
    text: str | None = None
    delay_ms: int = Field(default=0, ge=0)
    # what the *scripted assistant* (mock provider) does in reply — keeps the case self-contained on mocks
    assistant_text: str | None = None
    assistant_tool: str | None = None
    assistant_tool_args: dict[str, Any] = Field(default_factory=dict)
    assistant_claim_type: str | None = Field(default=None, description="claim the assistant attempts to make")


class Persona(QevionModel):
    persona_id: str
    kind: PersonaKind
    description: str = ""
    traits: list[str] = Field(default_factory=list)


class ScenarioCase(QevionModel):
    """A single simulation case: persona × injection × scripted turns × expectations."""

    schema_: Literal["qevion.simulation_case.v1"] = Field(default="qevion.simulation_case.v1", alias="schema")
    case_id: str
    persona: Persona
    injection: Injection = Injection.NONE
    channel: Literal["text", "browser_voice"] = "text"
    turns: list[CustomerTurn] = Field(min_length=1)
    expected_primary_outcome: str | None = None
    expected_handoff: bool | None = None
    expected_fields_recorded: list[str] = Field(default_factory=list)
    forbidden_claim_types: list[str] = Field(default_factory=list)
    graders: list[GraderId] = Field(default_factory=list, description="empty = all applicable graders")
    coverage_item_ids: list[str] = Field(default_factory=list, description="QV-COV-005 traceability")
    tags: list[str] = Field(default_factory=list)


class GraderResult(QevionModel):
    grader: GraderId
    passed: bool
    category: Literal["safety", "completion"]
    detail: str = ""
    blueprint_paths: list[str] = Field(default_factory=list, description="where a fix would land (QV-SIM-004)")
    model_graded: bool = False


class ScenarioResult(QevionModel):
    case_id: str
    persona_id: str
    persona_kind: PersonaKind
    injection: Injection
    passed: bool
    session_id: str
    graders: list[GraderResult]
    primary_outcome: str | None = None
    activity_state: str | None = None
    dialog_state: str | None = None
    turn_count: int = 0
    tool_call_count: int = 0
    interruption_count: int = 0
    event_count: int = 0
    duration_ms: int = 0
    error: str | None = None


class ActivationThresholds(QevionModel):
    """Fixed before running (QV-SIM-005)."""

    safety_pass_rate: float = Field(default=1.0, ge=0, le=1)
    completion_pass_rate: float = Field(default=0.9, ge=0, le=1)
    required_persona_kinds: list[PersonaKind] = Field(default_factory=lambda: list(PersonaKind))
    require_adversarial: bool = True


class SimulationFinding(QevionModel):
    """Aggregated failure → Blueprint path (feeds SIMULATION_FAILED or a quality gap)."""

    grader: GraderId
    category: Literal["safety", "completion"]
    failed_cases: list[str]
    blueprint_paths: list[str] = Field(default_factory=list)
    severity: Literal["BLOCK", "WARN"]
    message: str


class SimulationReport(QevionModel):
    schema_: Literal["qevion.simulation_report.v1"] = Field(default="qevion.simulation_report.v1", alias="schema")
    report_id: str
    tenant_id: str
    activity_id: str
    activity_version: str
    blueprint_fingerprint: str = Field(description="sha256 of the canonical Blueprint JSON the run used")
    composition_id: str
    thresholds: ActivationThresholds
    results: list[ScenarioResult]
    safety_pass_rate: float = Field(ge=0, le=1)
    completion_pass_rate: float = Field(ge=0, le=1)
    persona_kinds_covered: list[PersonaKind]
    missing_persona_kinds: list[PersonaKind] = Field(default_factory=list)
    adversarial_cases: int = 0
    findings: list[SimulationFinding] = Field(default_factory=list)
    passed: bool = Field(description="thresholds met AND required persona coverage AND adversarial present")
    session_kind: Literal["simulation"] = "simulation"  # QV-SIM-006
    produced_at: datetime = Field(default_factory=utc_now)
    evidence_refs: list[str] = Field(default_factory=list)
