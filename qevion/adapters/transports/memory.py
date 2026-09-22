"""In-memory `TransportSession` (test double for the browser WebSocket). Records everything sent."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from qevion.contracts.transport import ClientMessage, ServerMessage


@dataclass
class MemoryTransportSession:
    sent: list[ServerMessage] = field(default_factory=list)
    audio_sent: list[tuple[str, bytes]] = field(default_factory=list)
    _inbox: asyncio.Queue[ClientMessage | bytes | None] = field(default_factory=asyncio.Queue)
    closed: bool = False
    close_reason: str | None = None

    # test-side helpers -------------------------------------------------------------
    def client_sends(self, item: ClientMessage | bytes) -> None:
        self._inbox.put_nowait(item)

    def client_disconnects(self) -> None:
        self._inbox.put_nowait(None)

    def messages_of(self, type_: str) -> list[ServerMessage]:
        return [m for m in self.sent if m.type == type_]

    # TransportSession protocol ---------------------------------------------------------
    async def send(self, message: ServerMessage) -> None:
        if self.closed:
            raise ConnectionError("transport closed")
        self.sent.append(message)

    async def send_audio(self, response_id: str, pcm16: bytes) -> None:
        if self.closed:
            raise ConnectionError("transport closed")
        self.audio_sent.append((response_id, pcm16))

    async def incoming(self) -> AsyncIterator[ClientMessage | bytes]:
        while True:
            item = await self._inbox.get()
            if item is None:
                return
            yield item

    async def close(self, reason: str = "bye") -> None:
        self.closed = True
        self.close_reason = reason
        self._inbox.put_nowait(None)
