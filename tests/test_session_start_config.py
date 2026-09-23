"""F-01 regression (OPS 5.5 audit): the session configuration reaches a live S2S provider before any audio.

Field failure: in browser_voice, 54 `input_audio_buffer.append` frames reached OpenAI before the first
`session.update`, so the provider ran on its defaults (voice alloy, default persona, server VAD auto-responses, no
tools) for the whole first utterance and then rejected QEVION's commit/response.create.
"""

from __future__ import annotations

import asyncio
import json
import math
import struct
from typing import Any

import pytest
from qevion.adapters.providers.openai_realtime import OpenAIRealtimeAdapter
from qevion.adapters.transports.memory import MemoryTransportSession
from qevion.contracts.common import Channel
from qevion.contracts.transport import ClientMessage
from qevion.main import _seed
from qevion.runtime.store import RuntimeStore


class FakeSock:
    def __init__(self) -> None:
        self.out: list[dict[str, Any]] = []
        self.inbox: asyncio.Queue[str | None] = asyncio.Queue()

    async def send(self, text: str) -> None:
        self.out.append(json.loads(text))

    async def recv(self) -> str | None:
        return await self.inbox.get()

    async def close(self) -> None:
        self.inbox.put_nowait(None)


def _tone() -> bytes:
    return struct.pack("<480h", *[int(9000 * math.sin(2 * math.pi * 180 * j / 24000)) for j in range(480)])


async def _run(channel: Channel, feed: Any) -> list[dict[str, Any]]:
    store = RuntimeStore()
    _seed(store)
    sock = FakeSock()

    async def factory(url: str, headers: dict[str, str]) -> FakeSock:
        return sock

    store.s2s_adapters["openai_realtime"] = OpenAIRealtimeAdapter(socket_factory=factory)  # type: ignore[arg-type]
    store.credentials.set_ephemeral("openai", "FAKE-KEY-0000", ttl_seconds=60)
    tr = MemoryTransportSession()
    key = next(k for k in store.activities if k.startswith("act_order_intake"))
    # frames queued BEFORE the session even starts — the worst case (browser mic already streaming)
    feed(tr)
    live = store.build_session(
        activity_key=key, transport=tr, session_id="ses_t", channel=channel, composition_id="comp_s2s_openai_v1"
    )
    task = asyncio.create_task(live.session.run())
    await asyncio.sleep(0.3)
    tr.client_sends(ClientMessage.model_validate({"type": "bye"}))
    await asyncio.sleep(0.2)
    task.cancel()
    return sock.out


@pytest.mark.asyncio
async def test_voice_first_provider_message_is_full_session_update() -> None:
    def feed(tr: MemoryTransportSession) -> None:
        for _ in range(30):
            tr.client_sends(_tone())

    out = await _run(Channel.BROWSER_VOICE, feed)
    types = [m["type"] for m in out]
    assert types, "nothing sent to provider"
    assert types[0] == "session.update", types[:5]
    su = out[0]["session"]
    assert su["type"] == "realtime"
    assert su["audio"]["output"]["voice"] == "marin"  # the configured voice, not the provider default
    assert su["audio"]["input"]["turn_detection"] is None  # QEVION's turn plane owns endpointing
    assert {t["name"] for t in su["tools"]} >= {"record_field", "submit_record"}
    assert "egyptian" in su["instructions"].lower()
    first_audio = types.index("input_audio_buffer.append")
    assert first_audio > 0 and "session.update" in types[:first_audio]


@pytest.mark.asyncio
async def test_text_first_provider_message_is_session_update() -> None:
    out = await _run(Channel.TEXT, lambda tr: tr.client_sends(ClientMessage.model_validate({"type": "text", "text": "hi"})))
    assert [m["type"] for m in out][0] == "session.update"
