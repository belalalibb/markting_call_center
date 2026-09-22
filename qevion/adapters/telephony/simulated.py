"""Simulated `TelephonyPort` (ADR-0003). Places no real calls; emits the same lifecycle a carrier would."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from qevion.contracts.common import new_id


class SimCallState(StrEnum):
    DIALING = "dialing"
    RINGING = "ringing"
    ANSWERED = "answered"
    NO_ANSWER = "no_answer"
    BUSY = "busy"
    HUNG_UP = "hung_up"


@dataclass
class SimCall:
    call_id: str
    tenant_id: str
    contact_ref: str
    activity_id: str
    state: SimCallState = SimCallState.DIALING
    history: list[SimCallState] = field(default_factory=list)

    def advance(self, to: SimCallState) -> None:
        self.history.append(self.state)
        self.state = to


@dataclass
class SimulatedTelephonyAdapter:
    name: str = "simulated"
    calls: dict[str, SimCall] = field(default_factory=dict)
    # contact_ref → scripted answer behaviour; default = answered
    script: dict[str, SimCallState] = field(default_factory=dict)

    async def dial(self, tenant_id: str, contact_ref: str, activity_id: str) -> str:
        call = SimCall(call_id=new_id("call"), tenant_id=tenant_id, contact_ref=contact_ref, activity_id=activity_id)
        self.calls[call.call_id] = call
        call.advance(SimCallState.RINGING)
        call.advance(self.script.get(contact_ref, SimCallState.ANSWERED))
        return call.call_id

    async def hangup(self, call_id: str) -> None:
        call = self.calls.get(call_id)
        if call and call.state not in {SimCallState.HUNG_UP, SimCallState.NO_ANSWER, SimCallState.BUSY}:
            call.advance(SimCallState.HUNG_UP)

    def state(self, call_id: str) -> SimCallState:
        return self.calls[call_id].state
