"""Outcome engine — deterministic Outcome + InteractionRecord (§26 QV-OUT, QV-ACC-010).

Rules of the house:
* Outcomes are derived from *facts* (FieldStore, tool history, machine states, completion rules), never from
  what the model said (QV-OUT-001/002). `summary_text` is carried as an opaque, non-authoritative string.
* Completion rules are Blueprint data evaluated through the `decision.v1` port (deterministic-first, ADR-0004).
  A rule the port cannot evaluate yields UNKNOWN and is surfaced as an observation — never guessed.
* The primary outcome must be one of `outcome_schema.primary`; the vocabulary is `BaseOutcome` plus
  Activity-defined strings. Core only knows the generic precedence below, never business meaning.

Exit rule grammar extension (config, not code): `"<rule> => <outcome_value>"` maps a matched exit rule to an
explicit outcome value; without `=>` the rule text itself is used as the value.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from qevion.contracts.activity import ActivityBlueprint
from qevion.contracts.common import Channel
from qevion.contracts.control import ActivityState
from qevion.contracts.outcome import (
    BaseOutcome,
    ClaimDecisionEntry,
    CoverageMissEntry,
    InteractionRecord,
    Outcome,
    OutcomeTimestamps,
    RouteEntry,
    ToolProvenanceEntry,
)
from qevion.contracts.ports import DecisionPort
from qevion.contracts.provider import DecisionKind, DecisionRequest, DecisionSource
from qevion.contracts.tool import ToolOutcome, ToolOutcomeStatus
from qevion.core.field_store import FieldStore

_B = BaseOutcome


def _dt(ms: int | None) -> datetime | None:
    return None if ms is None else datetime.fromtimestamp(ms / 1000, tz=UTC)


@dataclass
class SessionFacts:
    """Everything the engine needs that is not already in the FieldStore. Filled by the session orchestrator."""

    session_id: str
    channel: Channel
    started_at_ms: int
    ended_at_ms: int | None = None
    first_user_turn_ms: int | None = None
    last_user_turn_ms: int | None = None
    turn_count: int = 0
    interruption_count: int = 0
    event_count: int = 0
    activity_state: ActivityState = ActivityState.OPENING
    handoff_ref: str | None = None
    handoff_ids: list[str] = field(default_factory=list)
    flags: set[str] = field(default_factory=set)  # session-level facts: opt_out, wrong_person, … (Activity data)
    routing_history: list[RouteEntry] = field(default_factory=list)
    coverage_misses: list[CoverageMissEntry] = field(default_factory=list)
    claim_decisions: list[ClaimDecisionEntry] = field(default_factory=list)
    summary_text: str | None = None
    event_log_ref: str | None = None
    evidence_refs: list[str] = field(default_factory=list)
    policy_versions: dict[str, str] = field(default_factory=dict)
    knowledge_versions: dict[str, str] = field(default_factory=dict)


@dataclass
class CompletionVerdict:
    success: bool | None  # None = at least one success rule UNKNOWN
    failure: bool | None
    exit_rule: str | None  # first matched exit rule (raw text)
    exit_value: str | None  # mapped value (after `=>`), or the rule text
    unknown_rules: list[str] = field(default_factory=list)


def flags_from_tools(history: list[ToolOutcome]) -> set[str]:
    """Generic tool facts usable by rules: `<tool>_completed`, `<tool>_accepted` (when output.accepted is true)."""
    flags: set[str] = set()
    for o in history:
        if o.status is ToolOutcomeStatus.COMPLETED:
            flags.add(f"{o.tool_id}_completed")
            if o.output.get("accepted") is True:
                flags.add(f"{o.tool_id}_accepted")
    return flags


def _split_exit(rule: str) -> tuple[str, str]:
    if "=>" in rule:
        lhs, rhs = rule.split("=>", 1)
        return lhs.strip(), rhs.strip()
    return rule.strip(), rule.strip()


# --- part 2 ---
