"""Readiness lifecycle (§10 QV-LIFE-001..004): an explicit Control-Plane state machine over `ReadinessState`.

Transitions are Control-authored events (`activity.readiness_changed`), never chat-inferred. `ACTIVE` requires
ALL activation gates (QV-LIFE-002); an edit after READY_FOR_ACTIVATION returns to an earlier state (QV-LIFE-004).
Approved versions are immutable: activation freezes a version record, never mutates the draft.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from qevion.contracts.activity import ActivityBlueprint, ReadinessState
from qevion.contracts.common import utc_now
from qevion.contracts.control import PreflightResult, can_transition
from qevion.contracts.event import EventType

S = ReadinessState


class IllegalReadinessTransitionError(Exception):
    def __init__(self, src: S, dst: S, why: str = "") -> None:
        self.src, self.dst, self.why = src, dst, why
        super().__init__(f"readiness: {src.value} -> {dst.value} rejected{': ' + why if why else ''}")


@dataclass
class ReadinessChange:
    """The `activity.readiness_changed` payload (QV-LIFE-001)."""

    activity_id: str
    version: str
    from_state: S
    to_state: S
    reason: str
    actor: str  # control:<component> | operator:<id>
    ts: datetime = field(default_factory=utc_now)
    refs: dict[str, str] = field(default_factory=dict)  # preflight_result_ref, simulation_report_ref, ...

    @property
    def event_type(self) -> str:
        return EventType.ACTIVITY_READINESS_CHANGED

    def payload(self) -> dict[str, Any]:
        return {
            "activity_id": self.activity_id,
            "version": self.version,
            "from": self.from_state.value,
            "to": self.to_state.value,
            "reason": self.reason,
            "actor": self.actor,
            **self.refs,
        }


@dataclass
class ActivationGates:
    """QV-LIFE-002 inputs. Every one must be satisfied; the machine reports *which* are not."""

    schema_valid: bool = False
    preflight: PreflightResult | None = None
    simulation_passed: bool | None = None  # None = no simulation report
    all_decisions_approved: bool = False
    version_frozen: bool = False

    def unmet(self) -> list[str]:
        out: list[str] = []
        if not self.schema_valid:
            out.append("schema_valid")
        if self.preflight is None or self.preflight.status != "READY":
            out.append("preflight_ready")
        if self.simulation_passed is not True:
            out.append("simulation_passed")
        if not self.all_decisions_approved:
            out.append("all_decisions_approved")
        if not self.version_frozen:
            out.append("version_frozen")
        return out


@dataclass
class ReadinessMachine:
    activity_id: str
    version: str
    state: S = S.DRAFT
    history: list[ReadinessChange] = field(default_factory=list)

    @classmethod
    def from_blueprint(cls, bp: ActivityBlueprint) -> ReadinessMachine:
        return cls(bp.identity.activity_id, bp.identity.version, bp.version_metadata.readiness.state)

    # ------------------------------------------------------------------ core
    def can(self, dst: S) -> bool:
        return can_transition(self.state, dst)

    def transition(self, dst: S, *, reason: str, actor: str, refs: dict[str, str] | None = None) -> ReadinessChange:
        if not self.can(dst):
            raise IllegalReadinessTransitionError(self.state, dst, "not in transition table")
        if dst is S.ACTIVE:
            raise IllegalReadinessTransitionError(
                self.state, dst, "use activate(gates=...) — ACTIVE requires gate proof"
            )
        ch = ReadinessChange(self.activity_id, self.version, self.state, dst, reason, actor, refs=refs or {})
        self.state = dst
        self.history.append(ch)
        return ch

    # ------------------------------------------------------------------ control-authored helpers
    def apply_preflight(
        self, result: PreflightResult, *, ref: str, actor: str = "control:preflight"
    ) -> ReadinessChange | None:
        """Preflight outcome drives NEEDS_CONFIGURATION/BLOCKED/READY_FOR_SIMULATION. Idempotent when already there."""
        if result.status == "READY":
            target = S.READY_FOR_SIMULATION
            reason = "preflight READY"
        else:
            reasons = sorted({f.reason.value for f in result.blocking})
            info_only = {"MISSING_REQUIRED_KNOWLEDGE", "UNRESOLVED_KNOWLEDGE_CONFLICT", "UNAPPROVED_BUSINESS_DECISION"}
            target = S.NEEDS_INFORMATION if set(reasons) <= info_only else S.BLOCKED
            reason = "preflight BLOCKED: " + ", ".join(reasons)
        if self.state is target:
            return None
        if not self.can(target):
            # e.g. DRAFT → READY_FOR_SIMULATION must pass through discovery/configuration first
            for step in (S.DISCOVERY_IN_PROGRESS, S.NEEDS_CONFIGURATION):
                if self.state is not step and self.can(step) and can_transition(step, target):
                    self.transition(step, reason=f"advancing toward {target.value}", actor=actor)
                    break
        if not self.can(target):
            raise IllegalReadinessTransitionError(self.state, target, "no legal path from current state")
        return self.transition(target, reason=reason, actor=actor, refs={"preflight_result_ref": ref})

    def apply_simulation(self, passed: bool, *, ref: str, actor: str = "control:simulation") -> ReadinessChange:
        target = S.READY_FOR_ACTIVATION if passed else S.SIMULATION_FAILED
        return self.transition(
            target,
            reason="simulation passed thresholds" if passed else "simulation below thresholds",
            actor=actor,
            refs={"simulation_report_ref": ref},
        )

    def activate(
        self, gates: ActivationGates, *, actor: str, preflight_ref: str = "", simulation_ref: str = ""
    ) -> ReadinessChange:
        """QV-LIFE-002: ACTIVE only with every gate satisfied and only from READY_FOR_ACTIVATION / SUSPENDED."""
        if not can_transition(self.state, S.ACTIVE):
            raise IllegalReadinessTransitionError(self.state, S.ACTIVE, "not in transition table")
        unmet = gates.unmet() if self.state is S.READY_FOR_ACTIVATION else []
        if unmet:
            raise IllegalReadinessTransitionError(self.state, S.ACTIVE, f"activation gates unmet: {unmet}")
        ch = ReadinessChange(
            self.activity_id,
            self.version,
            self.state,
            S.ACTIVE,
            "all activation gates satisfied" if self.state is S.READY_FOR_ACTIVATION else "resumed",
            actor,
            refs={
                k: v
                for k, v in (("preflight_result_ref", preflight_ref), ("simulation_report_ref", simulation_ref))
                if v
            },
        )
        self.state = S.ACTIVE
        self.history.append(ch)
        return ch

    def edited(self, *, actor: str, what: str) -> ReadinessChange | None:
        """QV-LIFE-004: an edit after READY_FOR_ACTIVATION (or during simulation states) invalidates readiness."""
        if self.state in (S.ACTIVE, S.SUSPENDED, S.RETIRED):
            raise IllegalReadinessTransitionError(
                self.state, S.NEEDS_CONFIGURATION, "approved versions are immutable; create a new version"
            )
        if self.state in (S.READY_FOR_ACTIVATION, S.READY_FOR_SIMULATION, S.SIMULATION_FAILED, S.BLOCKED):
            return self.transition(S.NEEDS_CONFIGURATION, reason=f"edited: {what}", actor=actor)
        return None

    def suspend(self, *, actor: str, reason: str) -> ReadinessChange:
        return self.transition(S.SUSPENDED, reason=reason, actor=actor)

    def retire(self, *, actor: str, reason: str) -> ReadinessChange:
        return self.transition(S.RETIRED, reason=reason, actor=actor)

    @property
    def accepts_new_sessions(self) -> bool:
        """QV-LIFE-003 / QV-PRE-004: only ACTIVE versions start sessions."""
        return self.state is S.ACTIVE


__all__ = ["ActivationGates", "IllegalReadinessTransitionError", "ReadinessChange", "ReadinessMachine"]
