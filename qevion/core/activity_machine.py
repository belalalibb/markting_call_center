"""Activity machine — data-driven (§19 QV-RT, D1). A transition *table* (state → trigger → state).

The generic default table ships here; a Blueprint may supply its own via `activity_machine.inline`
or `table_ref`. The Core raises only these generic triggers; Blueprints map their completion semantics
onto them via rules evaluated by the decision port.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from qevion.contracts.control import TERMINAL_ACTIVITY_STATES, ActivityState
from qevion.core.dialog_machine import IllegalTransition, Transition


class ActivityTrigger(StrEnum):
    OPENED = "opened"
    USER_ENGAGED = "user_engaged"
    FIELD_NEEDED = "field_needed"
    FIELDS_COMPLETE = "fields_complete"
    QUESTION_ASKED = "question_asked"
    QUESTION_RESOLVED = "question_resolved"
    AMBIGUITY = "ambiguity"
    CLARIFIED = "clarified"
    CONFIRM_NEEDED = "confirm_needed"
    CONFIRMED = "confirmed"
    DENIED = "denied"
    EXECUTED = "executed"
    EXECUTION_FAILED = "execution_failed"
    SUCCESS_RULE_MET = "success_rule_met"
    FAILURE_RULE_MET = "failure_rule_met"
    EXIT_RULE_MET = "exit_rule_met"
    HANDOFF = "handoff"
    USER_LEFT = "user_left"
    BLOCKED = "blocked"
    CLOSED = "closed"


T = ActivityTrigger
S = ActivityState
_COMMON_EXITS = {T.HANDOFF: S.ESCALATED, T.USER_LEFT: S.ABANDONED, T.BLOCKED: S.BLOCKED, T.EXIT_RULE_MET: S.CLOSING}

GENERIC_DEFAULT_V1: dict[str, dict[str, str]] = {
    S.OPENING: {T.OPENED: S.ENGAGED, **_COMMON_EXITS},
    S.ENGAGED: {
        T.FIELD_NEEDED: S.COLLECTING,
        T.QUESTION_ASKED: S.RESOLVING,
        T.AMBIGUITY: S.CLARIFYING,
        T.FIELDS_COMPLETE: S.CONFIRMING,
        T.SUCCESS_RULE_MET: S.CLOSING,
        T.FAILURE_RULE_MET: S.CLOSING,
        **_COMMON_EXITS,
    },
    S.COLLECTING: {
        T.FIELDS_COMPLETE: S.CONFIRMING,
        T.FIELD_NEEDED: S.COLLECTING,
        T.QUESTION_ASKED: S.RESOLVING,
        T.AMBIGUITY: S.CLARIFYING,
        T.USER_ENGAGED: S.ENGAGED,
        T.FAILURE_RULE_MET: S.CLOSING,
        **_COMMON_EXITS,
    },
    S.RESOLVING: {
        T.QUESTION_RESOLVED: S.ENGAGED,
        T.FIELD_NEEDED: S.COLLECTING,
        T.AMBIGUITY: S.CLARIFYING,
        **_COMMON_EXITS,
    },
    S.CLARIFYING: {T.CLARIFIED: S.ENGAGED, T.FIELD_NEEDED: S.COLLECTING, **_COMMON_EXITS},
    S.CONFIRMING: {
        T.CONFIRMED: S.EXECUTING,
        T.DENIED: S.COLLECTING,
        T.AMBIGUITY: S.CLARIFYING,
        T.FIELD_NEEDED: S.COLLECTING,
        **_COMMON_EXITS,
    },
    S.EXECUTING: {
        T.EXECUTED: S.CLOSING,
        T.SUCCESS_RULE_MET: S.CLOSING,
        T.EXECUTION_FAILED: S.ENGAGED,
        T.HANDOFF: S.ESCALATED,
        T.BLOCKED: S.BLOCKED,
    },
    S.CLOSING: {T.CLOSED: S.ENDED, T.USER_ENGAGED: S.ENGAGED, T.HANDOFF: S.ESCALATED, T.USER_LEFT: S.ENDED},
    S.ENDED: {},
    S.ESCALATED: {},
    S.ABANDONED: {},
    S.BLOCKED: {},
}

TABLES: dict[str, dict[str, dict[str, str]]] = {"generic_default_v1": GENERIC_DEFAULT_V1}


def validate_table(table: dict[str, dict[str, str]]) -> list[str]:
    """Structural validation for Blueprint-supplied tables (Preflight uses this in P2)."""
    errors: list[str] = []
    states = {s.value for s in ActivityState}
    triggers = {t.value for t in ActivityTrigger}
    if S.OPENING not in table:
        errors.append("missing OPENING state")
    for st, row in table.items():
        if st not in states:
            errors.append(f"unknown state {st}")
            continue
        for trig, nxt in row.items():
            if trig not in triggers:
                errors.append(f"{st}: unknown trigger {trig}")
            if nxt not in states:
                errors.append(f"{st}/{trig}: unknown target {nxt}")
        if ActivityState(st) in TERMINAL_ACTIVITY_STATES and row:
            errors.append(f"terminal state {st} must have no transitions")
    if not any(nxt in TERMINAL_ACTIVITY_STATES for row in table.values() for nxt in row.values()):
        errors.append("no path to a terminal state")
    return errors


@dataclass
class ActivityMachine:
    table: dict[str, dict[str, str]] = field(default_factory=lambda: GENERIC_DEFAULT_V1)
    state: ActivityState = ActivityState.OPENING
    transitions: list[Transition] = field(default_factory=list)

    @classmethod
    def from_blueprint_ref(cls, table_ref: str | None, inline: dict[str, dict[str, str]] | None) -> ActivityMachine:
        if inline:
            errs = validate_table(inline)
            if errs:
                raise ValueError("invalid activity_machine.inline: " + "; ".join(errs))
            return cls(table=inline)
        return cls(table=TABLES[table_ref or "generic_default_v1"])

    @property
    def terminal(self) -> bool:
        return self.state in TERMINAL_ACTIVITY_STATES

    def can(self, trigger: str) -> bool:
        return trigger in self.table.get(self.state.value, {})

    def fire(self, trigger: str, ts_ms: int, reason: str | None = None) -> Transition:
        nxt = self.table.get(self.state.value, {}).get(trigger)
        if nxt is None:
            raise IllegalTransition(f"activity: {self.state.value} --{trigger}--> ?")
        t = Transition("activity", self.state.value, nxt, trigger, ts_ms, reason)
        self.state = ActivityState(nxt)
        self.transitions.append(t)
        return t

    def fire_if_possible(self, trigger: str, ts_ms: int, reason: str | None = None) -> Transition | None:
        return self.fire(trigger, ts_ms, reason) if self.can(trigger) else None
