"""Deterministic mock adapters for the s2s / llm / asr / tts ports (P0.2 exit gate; QV-ACC-006 fixtures).

The mock S2S session is *scripted*: tests/simulations feed it `MockScript` steps and it emits the
corresponding provider-neutral events. It never calls the network, never needs credentials, and
produces a synthetic PCM16 "audio" stream (silence) with correct byte accounting.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from qevion.contracts.composition import AdapterCapabilities, Capability, CapabilityState
from qevion.contracts.provider import (
    ASRRequest,
    ASRResult,
    AudioFormat,
    AudioFrameRef,
    LLMRequest,
    LLMResponse,
    ProviderRole,
    S2SEvent,
    S2SEventType,
    S2SSessionConfig,
    ToolCallRequest,
    ToolCallResult,
    TTSChunk,
    TTSRequest,
)

_CAPS_COMMON = [
    Capability(name="language:ar-EG", state=CapabilityState.SUPPORTED, notes="mock"),
    Capability(name="language:en-US", state=CapabilityState.SUPPORTED, notes="mock"),
    Capability(name="audio:pcm16_24k", state=CapabilityState.SUPPORTED),
]


def frame_ref(pcm16: bytes, fmt: AudioFormat | None = None, frame_id: str | None = None) -> AudioFrameRef:
    fmt = fmt or AudioFormat()
    duration_ms = int(len(pcm16) / 2 / fmt.sample_rate_hz * 1000)
    return AudioFrameRef(
        frame_id=frame_id or hashlib.sha256(pcm16).hexdigest()[:16],
        byte_length=len(pcm16),
        duration_ms=duration_ms,
        fmt=fmt,
        sha256=hashlib.sha256(pcm16).hexdigest(),
    )


def silence(ms: int, fmt: AudioFormat | None = None) -> bytes:
    fmt = fmt or AudioFormat()
    return b"\x00\x00" * int(fmt.sample_rate_hz * ms / 1000)


@dataclass
class MockScriptStep:
    """One scripted assistant response. `text` is spoken; `tool_call` triggers a tool round-trip first."""

    text: str = ""
    audio_ms: int = 800
    tool_call: ToolCallRequest | None = None
    transcript_of_user: str | None = None


@dataclass
class MockS2SSession:
    config: S2SSessionConfig
    script: list[MockScriptStep] = field(default_factory=list)
    _events: asyncio.Queue[S2SEvent | None] = field(default_factory=asyncio.Queue)
    _audio: asyncio.Queue[tuple[AudioFrameRef, bytes] | None] = field(default_factory=asyncio.Queue)
    _response_counter: int = 0
    _current_response: str | None = None
    _cancelled: set[str] = field(default_factory=set)
    _pending_tool: ToolCallRequest | None = None
    bytes_in: int = 0
    closed: bool = False
    log: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._events.put_nowait(S2SEvent(type=S2SEventType.SESSION_READY, raw_type="mock.session.ready"))

    # -- inbound -----------------------------------------------------------------------
    async def send_audio(self, pcm16: bytes, ref: AudioFrameRef) -> None:
        self.bytes_in += len(pcm16)
        self.log.append(f"audio:{ref.duration_ms}ms")

    async def commit_input(self) -> None:
        """Turn plane says the user finished → play next scripted step."""
        self.log.append("commit")
        await self._play_next()

    async def send_text(self, text: str) -> None:
        self.log.append(f"text:{text}")
        await self._play_next()

    async def send_tool_result(self, result: ToolCallResult) -> None:
        self.log.append(f"tool_result:{result.call_id}")
        if self._pending_tool and self._pending_tool.call_id == result.call_id:
            self._pending_tool = None
            await self._start_speaking(self._current_step_text, self._current_step_audio_ms)

    async def cancel_response(self, response_id: str | None = None) -> None:
        rid = response_id or self._current_response
        if rid:
            self._cancelled.add(rid)
            self.log.append(f"cancel:{rid}")
            await self._events.put(S2SEvent(type=S2SEventType.RESPONSE_CANCELLED, response_id=rid))

    async def update_instructions(self, instructions: str) -> None:
        self.config = self.config.model_copy(update={"instructions": instructions})
        self.log.append("instructions_updated")

    # -- outbound ----------------------------------------------------------------------
    async def events(self) -> AsyncIterator[S2SEvent]:
        while True:
            ev = await self._events.get()
            if ev is None:
                return
            yield ev

    async def audio_out(self) -> AsyncIterator[tuple[AudioFrameRef, bytes]]:
        while True:
            item = await self._audio.get()
            if item is None:
                return
            yield item

    async def close(self) -> None:
        self.closed = True
        if self._speak_task and not self._speak_task.done():
            self._speak_task.cancel()
        await self._events.put(S2SEvent(type=S2SEventType.CLOSED))
        await self._events.put(None)
        await self._audio.put(None)

    # -- internals ---------------------------------------------------------------------
    _current_step_text: str = ""
    _current_step_audio_ms: int = 0
    realtime: bool = False
    _speak_task: asyncio.Task[None] | None = None

    async def _play_next(self) -> None:
        if not self.script:
            await self._speak("", 0)
            return
        step = self.script.pop(0)
        if step.transcript_of_user:
            await self._events.put(S2SEvent(type=S2SEventType.INPUT_TRANSCRIPT, text=step.transcript_of_user))
        self._current_step_text, self._current_step_audio_ms = step.text, step.audio_ms
        if step.tool_call:
            self._pending_tool = step.tool_call
            self._response_counter += 1
            rid = f"resp_{self._response_counter}"
            self._current_response = rid
            await self._events.put(S2SEvent(type=S2SEventType.RESPONSE_STARTED, response_id=rid))
            await self._events.put(
                S2SEvent(type=S2SEventType.RESPONSE_TOOL_CALL, response_id=rid, tool_call=step.tool_call)
            )
            return
        await self._start_speaking(step.text, step.audio_ms)

    async def _start_speaking(self, text: str, audio_ms: int) -> None:
        """Realtime mode streams in the background (like a live provider) so the caller's pump keeps
        consuming client frames — barge-in must be able to land mid-response. Non-realtime stays inline."""
        if self.realtime:
            self._speak_task = asyncio.create_task(self._speak(text, audio_ms))
        else:
            await self._speak(text, audio_ms)

    async def _speak(self, text: str, audio_ms: int) -> None:
        self._response_counter += 1
        rid = f"resp_{self._response_counter}"
        self._current_response = rid
        await self._events.put(S2SEvent(type=S2SEventType.RESPONSE_STARTED, response_id=rid))
        if text:
            await self._events.put(S2SEvent(type=S2SEventType.RESPONSE_TEXT_DELTA, response_id=rid, text=text))
        chunk_ms = 100
        sent = 0
        while sent < audio_ms:
            if rid in self._cancelled:
                return
            pcm = silence(min(chunk_ms, audio_ms - sent), self.config.output_format)
            ref = frame_ref(pcm, self.config.output_format, frame_id=f"{rid}_{sent}")
            await self._audio.put((ref, pcm))
            await self._events.put(S2SEvent(type=S2SEventType.RESPONSE_AUDIO_DELTA, response_id=rid, audio=ref))
            sent += chunk_ms
            # realtime=True paces chunks like a live provider (browser voice / interruption tests);
            # otherwise just yield so interruption can land mid-response.
            await asyncio.sleep(chunk_ms / 1000 if self.realtime else 0)
        await self._events.put(S2SEvent(type=S2SEventType.RESPONSE_DONE, response_id=rid, text=text))


class MockS2SAdapter:
    name = "mock"

    def __init__(self, script: list[MockScriptStep] | None = None, realtime: bool = False) -> None:
        self.script = script or []
        self.realtime = realtime
        self.sessions: list[MockS2SSession] = []

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            adapter=self.name,
            role=ProviderRole.S2S,
            capabilities=_CAPS_COMMON
            + [
                Capability(name="feature:tool_calls", state=CapabilityState.SUPPORTED),
                Capability(name="feature:barge_in", state=CapabilityState.SUPPORTED),
                Capability(
                    name="feature:server_vad", state=CapabilityState.UNSUPPORTED, notes="turn plane owns endpointing"
                ),
            ],
        )

    async def open(self, config: S2SSessionConfig, credential: str | None) -> MockS2SSession:
        s = MockS2SSession(config=config, script=list(self.script), realtime=self.realtime)
        self.sessions.append(s)
        return s


class MockLLMAdapter:
    """Echo/structured mock: returns canned `responses` in order, else echoes last user message."""

    name = "mock"

    def __init__(self, responses: list[LLMResponse] | None = None) -> None:
        self.responses = list(responses or [])
        self.requests: list[LLMRequest] = []

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            adapter=self.name,
            role=ProviderRole.LLM,
            capabilities=_CAPS_COMMON + [Capability(name="feature:json_schema", state=CapabilityState.SUPPORTED)],
        )

    async def complete(self, request: LLMRequest, credential: str | None) -> LLMResponse:
        self.requests.append(request)
        if self.responses:
            return self.responses.pop(0)
        last_user = next((m.content for m in reversed(request.messages) if m.role == "user"), "")
        return LLMResponse(
            text=f"[mock] {last_user}", usage={"input_tokens": len(last_user), "output_tokens": 8}, finish_reason="stop"
        )


class MockASRAdapter:
    """Returns transcripts from a queue; empty audio → empty final transcript."""

    name = "mock"

    def __init__(self, transcripts: list[str] | None = None) -> None:
        self.transcripts = list(transcripts or [])

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(adapter=self.name, role=ProviderRole.ASR, capabilities=_CAPS_COMMON)

    async def transcribe(self, request: ASRRequest, pcm16: bytes, credential: str | None) -> ASRResult:
        text = self.transcripts.pop(0) if self.transcripts else ""
        return ASRResult(
            text=text, is_final=not request.partial, confidence=0.95 if text else None, language=request.language
        )


class MockTTSAdapter:
    """~60 ms of silence per character, chunked at 200 ms."""

    name = "mock"

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(adapter=self.name, role=ProviderRole.TTS, capabilities=_CAPS_COMMON)

    async def synthesize(self, request: TTSRequest, credential: str | None) -> AsyncIterator[tuple[TTSChunk, bytes]]:
        total_ms = max(200, 60 * len(request.text))
        sent = 0
        while sent < total_ms:
            ms = min(200, total_ms - sent)
            pcm = silence(ms, request.fmt)
            sent += ms
            yield TTSChunk(audio=frame_ref(pcm, request.fmt), is_last=sent >= total_ms), pcm


def as_dict(obj: Any) -> dict[str, Any]:
    return obj.model_dump(mode="json", by_alias=True)  # type: ignore[no-any-return]
