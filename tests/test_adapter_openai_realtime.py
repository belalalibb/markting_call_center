"""P4 — OpenAI Realtime adapter: protocol translation verified offline against a fake socket (no key)."""

from __future__ import annotations

import asyncio
import base64
import json
from typing import Any

import pytest
from qevion.adapters.providers.openai_realtime import OpenAIRealtimeAdapter, render_tools
from qevion.contracts.provider import AudioFrameRef, S2SEventType, S2SSessionConfig, ToolCallResult


class FakeSocket:
    """Scriptable provider: records outbound JSON, replays inbound frames on demand."""

    def __init__(self) -> None:
        self.out: list[dict[str, Any]] = []
        self.inbox: asyncio.Queue[str | None] = asyncio.Queue()
        self.closed = False
        self.url = ""
        self.headers: dict[str, str] = {}

    async def send(self, text: str) -> None:
        self.out.append(json.loads(text))

    async def recv(self) -> str | None:
        return await self.inbox.get()

    async def close(self) -> None:
        self.closed = True
        self.inbox.put_nowait(None)

    def feed(self, **msg: Any) -> None:
        self.inbox.put_nowait(json.dumps(msg))

    def types(self) -> list[str]:
        return [m["type"] for m in self.out]


def make() -> tuple[OpenAIRealtimeAdapter, FakeSocket]:
    sock = FakeSocket()

    async def factory(url: str, headers: dict[str, str]) -> FakeSocket:
        sock.url, sock.headers = url, headers
        return sock

    return OpenAIRealtimeAdapter(factory), sock


CFG = S2SSessionConfig(
    provider="openai_realtime",
    model="gpt-realtime",
    voice="marin",
    tools=[{"tool_id": "record_field", "description": "d", "input_schema": {"type": "object"}}],
)


async def _drain(gen: Any, n: int, timeout: float = 1.0) -> list[Any]:
    out: list[Any] = []

    async def take() -> None:
        async for x in gen:
            out.append(x)
            if len(out) >= n:
                return

    await asyncio.wait_for(take(), timeout)
    return out


def test_capabilities_declare_unverified_languages_and_barge_in() -> None:
    caps = {c.name: c.state.value for c in OpenAIRealtimeAdapter().capabilities().capabilities}
    assert caps["language:ar-EG"] == "UNVERIFIED" and caps["feature:barge_in"] == "SUPPORTED"
    assert caps["feature:tool_calls"] == "SUPPORTED"


def test_render_tools_from_tool_v1() -> None:
    r = render_tools(
        [
            {
                "tool_id": "lookup",
                "description": "x",
                "input_schema": {"type": "object", "properties": {"q": {"type": "string"}}},
            },
            {"type": "function", "name": "already"},
        ]
    )
    assert r[0] == {
        "type": "function",
        "name": "lookup",
        "description": "x",
        "parameters": {"type": "object", "properties": {"q": {"type": "string"}}},
    }
    assert r[1]["name"] == "already"


@pytest.mark.asyncio
async def test_open_requires_credential_and_never_leaks_it() -> None:
    ad, sock = make()
    with pytest.raises(PermissionError):
        await ad.open(CFG, None)
    s = await ad.open(CFG, "KEYVALUE_NOT_LOGGED")
    assert sock.url.endswith("?model=gpt-realtime") and sock.headers["Authorization"].startswith("Bearer ")
    assert "KEYVALUE" not in json.dumps(s.sent)
    await s.close()


@pytest.mark.asyncio
async def test_outbound_mapping() -> None:
    ad, sock = make()
    s = await ad.open(CFG, "k")
    await s.update_instructions("Be brief.")
    await s.send_audio(b"\x00\x01" * 240, AudioFrameRef(frame_id="f", byte_length=480, duration_ms=10))
    await s.commit_input()
    await s.send_text("hello")
    await s.send_tool_result(ToolCallResult(call_id="c1", output={"ok": True}))
    await s.cancel_response("r1")
    t = sock.types()
    assert t == [
        "session.update",
        "input_audio_buffer.append",
        "input_audio_buffer.commit",
        "response.create",
        "conversation.item.create",
        "response.create",
        "conversation.item.create",
        "response.create",
        "response.cancel",
    ]
    su = sock.out[0]["session"]
    assert su["instructions"] == "Be brief." and su["turn_detection"] is None and su["voice"] == "marin"
    assert su["tools"][0]["name"] == "record_field"
    assert base64.b64decode(sock.out[1]["audio"]) == b"\x00\x01" * 240
    assert sock.out[4]["item"]["content"][0]["text"] == "hello"
    assert json.loads(sock.out[6]["item"]["output"]) == {"ok": True} and sock.out[6]["item"]["call_id"] == "c1"
    # diagnostics never contain audio payloads
    assert all("audio" not in json.dumps(x) or x["type"] != "input_audio_buffer.append" or "bytes" in x for x in s.sent)
    await s.close()


@pytest.mark.asyncio
async def test_server_vad_mode_does_not_force_response_create() -> None:
    ad, sock = make()
    s = await ad.open(CFG.model_copy(update={"server_vad": True}), "k")
    await s.update_instructions("x")
    await s.commit_input()
    assert sock.types() == ["session.update", "input_audio_buffer.commit"]
    assert sock.out[0]["session"]["turn_detection"] == {"type": "server_vad"}
    await s.close()


@pytest.mark.asyncio
async def test_inbound_translation_events_and_audio() -> None:
    ad, sock = make()
    s = await ad.open(CFG, "k")
    pcm = b"\x10\x00" * 2400  # 100 ms @ 24k
    sock.feed(type="session.created", event_id="e1")
    sock.feed(type="session.updated", event_id="e2")  # second ready suppressed
    sock.feed(type="input_audio_buffer.speech_started")
    sock.feed(type="input_audio_buffer.speech_stopped")
    sock.feed(type="conversation.item.input_audio_transcription.completed", transcript="مرحبا", item_id="i1")
    sock.feed(type="response.created", response={"id": "r1"})
    sock.feed(type="response.audio.delta", response_id="r1", event_id="a1", delta=base64.b64encode(pcm).decode())
    sock.feed(type="response.audio_transcript.delta", response_id="r1", delta="Hel")
    sock.feed(
        type="response.function_call_arguments.done",
        response_id="r1",
        call_id="c9",
        name="record_field",
        arguments=json.dumps({"field": "name", "value": "x"}),
        item_id="i2",
    )
    sock.feed(type="response.done", response={"id": "r1", "status": "completed"})
    sock.feed(type="response.created", response={"id": "r2"})
    sock.feed(type="response.done", response={"id": "r2", "status": "cancelled"})
    sock.feed(type="error", error={"type": "rate_limit_error", "message": "slow down", "code": "429"})
    evs = await _drain(s.events(), 12)
    kinds = [e.type for e in evs]
    assert kinds == [
        S2SEventType.SESSION_READY,
        S2SEventType.INPUT_SPEECH_STARTED,
        S2SEventType.INPUT_SPEECH_STOPPED,
        S2SEventType.INPUT_TRANSCRIPT,
        S2SEventType.RESPONSE_STARTED,
        S2SEventType.RESPONSE_AUDIO_DELTA,
        S2SEventType.RESPONSE_TEXT_DELTA,
        S2SEventType.RESPONSE_TOOL_CALL,
        S2SEventType.RESPONSE_DONE,
        S2SEventType.RESPONSE_STARTED,
        S2SEventType.RESPONSE_CANCELLED,
        S2SEventType.ERROR,
    ]
    assert evs[3].text == "مرحبا"
    assert evs[5].audio is not None and evs[5].audio.duration_ms == 100 and evs[5].audio.byte_length == 4800
    assert (
        evs[7].tool_call is not None
        and evs[7].tool_call.tool_id == "record_field"
        and evs[7].tool_call.arguments == {"field": "name", "value": "x"}
    )
    assert evs[11].error is not None and evs[11].error.retryable and evs[11].error.provider_code == "429"
    audio = await _drain(s.audio_out(), 1)
    assert audio[0][1] == pcm and audio[0][0].fmt.sample_rate_hz == 24000
    await s.close()


@pytest.mark.asyncio
async def test_cancel_drains_pending_audio_and_socket_eof_closes() -> None:
    ad, sock = make()
    s = await ad.open(CFG, "k")
    for _ in range(5):
        sock.feed(type="response.audio.delta", response_id="r1", delta=base64.b64encode(b"\x00\x00" * 240).decode())
    await asyncio.sleep(0.05)
    await s.cancel_response("r1")
    assert s.sent[-1] == {"type": "_audio_drained", "bytes": 5}
    sock.inbox.put_nowait(None)  # provider closes
    evs = await _drain(s.events(), 6)
    assert evs[-1].type is S2SEventType.CLOSED
    # audio_out terminates
    assert await _drain(s.audio_out(), 1, timeout=0.5) == []


@pytest.mark.asyncio
async def test_malformed_frames_are_ignored() -> None:
    ad, sock = make()
    s = await ad.open(CFG, "k")
    sock.inbox.put_nowait("{not json")
    sock.feed(type="unknown.event")
    sock.feed(type="session.created")
    evs = await _drain(s.events(), 1)
    assert evs[0].type is S2SEventType.SESSION_READY
    await s.close()
