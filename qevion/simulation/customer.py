"""SimulatedCustomerTransport — a `TransportSession` driven by a persona script (QV-SIM-001).

It is the *customer side* of a normal session: it receives ServerMessages exactly like a browser
would, answers confirmation requests per script, times its own turns, and records every message so
graders can inspect what the customer actually heard. The runtime never knows it is simulated except
through `session.kind = simulation` on the report (QV-SIM-006).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from qevion.contracts.simulation import CustomerTurn
from qevion.contracts.transport import ClientMessage, ClientMessageType, ServerMessage, ServerMessageType


@dataclass
class SimulatedCustomerTransport:
    """Plays `turns` against the session; one scripted customer turn per settle window."""

    turns: list[CustomerTurn]
    settle_ticks: int = 60  # scheduler yields between turns so provider/tool round-trips finish
    sent: list[ServerMessage] = field(default_factory=list)
    audio_sent: list[tuple[str, bytes]] = field(default_factory=list)
    confirmations_seen: list[str] = field(default_factory=list)
    pending_confirmations: list[str] = field(default_factory=list)
    closed: bool = False
    close_reason: str | None = None
    _inbox: asyncio.Queue[ClientMessage | bytes | None] = field(default_factory=asyncio.Queue)
    _driver: asyncio.Task[None] | None = None
    _next_confirm: bool | None = None

    # -- TransportSession protocol --------------------------------------------------------
    async def send(self, message: ServerMessage) -> None:
        if self.closed:
            raise ConnectionError("transport closed")
        self.sent.append(message)
        if message.type is ServerMessageType.CONFIRMATION_REQUEST:
            call_id = str(message.payload.get("call_id", ""))
            self.confirmations_seen.append(call_id)
            if self._next_confirm is None:
                self.pending_confirmations.append(call_id)
            else:
                self._inbox.put_nowait(
                    ClientMessage(type=ClientMessageType.CONFIRM, call_id=call_id, granted=self._next_confirm)
                )
                self._next_confirm = None
        elif message.type is ServerMessageType.AUDIO_START:
            self._inbox.put_nowait(
                ClientMessage(type=ClientMessageType.PLAYOUT_STARTED, response_id=message.response_id)
            )
        elif message.type in (ServerMessageType.AUDIO_END, ServerMessageType.STOP_PLAYOUT):
            self._inbox.put_nowait(
                ClientMessage(type=ClientMessageType.PLAYOUT_STOPPED, response_id=message.response_id)
            )

    async def send_audio(self, response_id: str, pcm16: bytes) -> None:
        if self.closed:
            raise ConnectionError("transport closed")
        self.audio_sent.append((response_id, pcm16))

    async def incoming(self) -> AsyncIterator[ClientMessage | bytes]:
        if self._driver is None:
            self._driver = asyncio.create_task(self._drive())
        while True:
            item = await self._inbox.get()
            if item is None:
                return
            yield item

    async def close(self, reason: str) -> None:
        self.closed = True
        self.close_reason = reason
        if self._driver and not self._driver.done():
            self._driver.cancel()

    # -- script driver ---------------------------------------------------------------------
    async def _settle(self) -> None:
        for _ in range(self.settle_ticks):
            await asyncio.sleep(0)

    async def _drive(self) -> None:
        await self._settle()
        for turn in self.turns:
            if turn.delay_ms:
                await asyncio.sleep(turn.delay_ms / 1000)
            match turn.kind:
                case "say":
                    self._inbox.put_nowait(ClientMessage(type=ClientMessageType.TEXT, text=turn.text or ""))
                case "interrupt":
                    # Text-mode interruption: a new user turn while the assistant is (scripted) speaking.
                    self._inbox.put_nowait(ClientMessage(type=ClientMessageType.TEXT, text=turn.text or ""))
                case "silence":
                    pass
                case "confirm" | "deny":
                    granted = turn.kind == "confirm"
                    if self.pending_confirmations:
                        call_id = self.pending_confirmations.pop(0)
                        self._inbox.put_nowait(
                            ClientMessage(type=ClientMessageType.CONFIRM, call_id=call_id, granted=granted)
                        )
                    else:
                        self._next_confirm = granted
                case "hangup":
                    self._inbox.put_nowait(ClientMessage(type=ClientMessageType.BYE))
                    return
            await self._settle()
        # Script exhausted → the customer hangs up (never leave a session dangling).
        self._inbox.put_nowait(ClientMessage(type=ClientMessageType.BYE))

    # -- grader helpers --------------------------------------------------------------------
    def messages_of(self, type_: ServerMessageType) -> list[ServerMessage]:
        return [m for m in self.sent if m.type is type_]

    def assistant_texts(self) -> list[str]:
        return [m.text or "" for m in self.sent if m.type is ServerMessageType.TRANSCRIPT and m.payload.get("role") != "user"]
