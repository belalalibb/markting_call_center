"""Dialog machine (fixed, identical for every Activity) — §19 QV-RT. Owns turn-taking, not business."""

from __future__ import annotations

from dataclasses import dataclass, field

from qevion.contracts.control import DialogState


class IllegalTransition(Exception):
    pass


@dataclass
class Transition:
    machine: str
    from_state: str
    to_state: str
    trigger: str
    ts_ms: int
    reason: str | None = None
    authority: str = "core"


D = DialogState
_DIALOG: dict[DialogState, dict[str, DialogState]] = {
    D.IDLE: {"session_started": D.LISTENING, "assistant_opens": D.SPEAKING, "close": D.CLOSED},
    D.LISTENING: {"end_of_turn": D.THINKING, "text_received": D.THINKING, "timeout": D.THINKING, "close": D.CLOSED},
    D.THINKING: {
        "response_started": D.SPEAKING,
        "tool_requested": D.WAITING_TOOL,
        "confirmation_needed": D.WAITING_CONFIRMATION,
        "nothing_to_say": D.LISTENING,
        "close": D.CLOSED,
    },
    D.SPEAKING: {
        "barge_in": D.INTERRUPTED,
        "response_done": D.LISTENING,
        "tool_requested": D.WAITING_TOOL,
        "close": D.CLOSED,
    },
    D.INTERRUPTED: {"reconciled": D.LISTENING, "close": D.CLOSED},
    D.WAITING_TOOL: {
        "tool_returned": D.THINKING,
        "tool_failed": D.THINKING,
        "barge_in": D.INTERRUPTED,
        "close": D.CLOSED,
    },
    D.WAITING_CONFIRMATION: {
        "confirmed": D.THINKING,
        "denied": D.THINKING,
        "end_of_turn": D.THINKING,
        "barge_in": D.INTERRUPTED,
        "close": D.CLOSED,
    },
    D.CLOSED: {},
}


@dataclass
class DialogMachine:
    state: DialogState = DialogState.IDLE
    transitions: list[Transition] = field(default_factory=list)

    def can(self, trigger: str) -> bool:
        return trigger in _DIALOG[self.state]

    def fire(self, trigger: str, ts_ms: int, reason: str | None = None) -> Transition:
        nxt = _DIALOG[self.state].get(trigger)
        if nxt is None:
            raise IllegalTransition(f"dialog: {self.state.value} --{trigger}--> ?")
        t = Transition("dialog", self.state.value, nxt.value, trigger, ts_ms, reason)
        self.state = nxt
        self.transitions.append(t)
        return t
