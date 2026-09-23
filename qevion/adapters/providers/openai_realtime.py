"""OpenAI Realtime S2S adapter (P4). Translates the provider-neutral `S2SSession` port to the OpenAI
Realtime WebSocket protocol. The socket is injectable (`SocketFactory`) so the translation layer is
verified offline with a fake socket; the real `websockets` client is used only when a credential exists.

Protocol mapping (client → provider):
  update_instructions   → session.update {instructions, tools, turn_detection: None|server_vad, formats}
  send_audio            → input_audio_buffer.append {audio: b64 pcm16}
  commit_input          → input_audio_buffer.commit + response.create (QEVION turn plane owns endpointing)
  send_text             → conversation.item.create(message/user/input_text) + response.create
  send_tool_result      → conversation.item.create(function_call_output) + response.create
  cancel_response       → response.cancel (barge-in step 3, §31)
Provider → neutral (`S2SEventType`):
  session.created/updated                 → SESSION_READY (first only)
  input_audio_buffer.speech_started/stopped → INPUT_SPEECH_STARTED/STOPPED
  conversation.item.input_audio_transcription.completed → INPUT_TRANSCRIPT
  response.created                        → RESPONSE_STARTED
  response.audio.delta / response.output_audio.delta → RESPONSE_AUDIO_DELTA (+ audio_out queue)
  response.audio_transcript.delta / response.output_audio_transcript.delta / response.text.delta → RESPONSE_TEXT_DELTA
  response.function_call_arguments.done   → RESPONSE_TOOL_CALL
  response.done                           → RESPONSE_DONE, or RESPONSE_CANCELLED when status == "cancelled"
  error                                   → ERROR
Never logs the credential; never stores audio beyond the in-flight queue (QV-PRIV).
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Protocol

from qevion.contracts.composition import AdapterCapabilities, Capability, CapabilityState
from qevion.contracts.provider import (
    AudioFormat,
    AudioFrameRef,
    ProviderError,
    ProviderRole,
    S2SEvent,
    S2SEventType,
    S2SSessionConfig,
    ToolCallRequest,
    ToolCallResult,
)

DEFAULT_URL = "wss://api.openai.com/v1/realtime"


class Socket(Protocol):
    """Minimal duplex text socket. `recv()` returns None on close."""

    async def send(self, text: str) -> None: ...
    async def recv(self) -> str | None: ...
    async def close(self) -> None: ...


SocketFactory = Callable[[str, dict[str, str]], Awaitable[Socket]]


class _WebsocketsSocket:
    def __init__(self, ws: Any) -> None:
        self._ws = ws

    async def send(self, text: str) -> None:
        await self._ws.send(text)

    async def recv(self) -> str | None:
        try:
            msg = await self._ws.recv()
        except Exception:  # noqa: BLE001 — any close/failure ends the stream
            return None
        return msg if isinstance(msg, str) else msg.decode()

    async def close(self) -> None:
        await self._ws.close()


async def websockets_factory(url: str, headers: dict[str, str]) -> Socket:
    import websockets  # local import: optional at import time, required at connect time

    ws = await websockets.connect(url, additional_headers=headers, max_size=8 * 1024 * 1024)
    return _WebsocketsSocket(ws)


def _rate(fmt: AudioFormat) -> str:
    return {24000: "pcm16", 16000: "pcm16", 8000: "g711_ulaw", 48000: "pcm16"}.get(fmt.sample_rate_hz, "pcm16")


def _ga_format(fmt: AudioFormat) -> dict[str, Any]:
    """GA Realtime audio format object (beta used flat strings). pcm16 carries an explicit rate."""
    kind = _rate(fmt)
    if kind == "pcm16":
        return {"type": "audio/pcm", "rate": 24000}
    return {"type": "audio/pcmu"}


# F-05: OpenAI Realtime reports many *per-request* rejections as `invalid_request_error` while the session stays
# perfectly usable (verified live 2026-09-23). Only these classes end the conversation.
_FATAL_ERROR_TYPES = {"authentication_error", "permission_error", "insufficient_quota"}
_FATAL_ERROR_CODES = {
    "invalid_api_key",
    "insufficient_quota",
    "session_expired",
    "model_not_found",
    "session_not_found",
    "invalid_model",
}


def _is_fatal(error_type: str, code: object) -> bool:
    return error_type in _FATAL_ERROR_TYPES or (isinstance(code, str) and code in _FATAL_ERROR_CODES)


def render_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """tool.v1 declarations → Realtime function tools. Accepts either already-rendered functions or tool.v1."""
    out: list[dict[str, Any]] = []
    for t in tools:
        if t.get("type") == "function" and "name" in t:
            out.append(t)
            continue
        out.append(
            {
                "type": "function",
                "name": str(t.get("tool_id") or t.get("name")),
                "description": str(t.get("description") or t.get("purpose") or ""),
                "parameters": t.get("input_schema") or t.get("parameters") or {"type": "object", "properties": {}},
            }
        )
    return out


class OpenAIRealtimeSession:
    def __init__(self, config: S2SSessionConfig, sock: Socket) -> None:
        self.config = config
        self._sock = sock
        self._events: asyncio.Queue[S2SEvent | None] = asyncio.Queue()
        self._audio: asyncio.Queue[tuple[AudioFrameRef, bytes] | None] = asyncio.Queue()
        self._ready_sent = False
        self._closed = False
        self._pump: asyncio.Task[None] | None = None
        self.sent: list[dict[str, Any]] = []  # outbound message types + sizes only (diagnostics; no audio bytes)
        self._current_response: str | None = None

    # ------------------------------------------------------------- lifecycle
    def start(self) -> None:
        self._pump = asyncio.create_task(self._pump_loop())

    async def _send(self, obj: dict[str, Any]) -> None:
        if self._closed:
            return
        self.sent.append({"type": obj["type"], "bytes": len(json.dumps(obj))})
        await self._sock.send(json.dumps(obj))

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._sock.close()
        if self._pump:
            self._pump.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._pump
        self._events.put_nowait(S2SEvent(type=S2SEventType.CLOSED, raw_type="closed"))
        self._events.put_nowait(None)
        self._audio.put_nowait(None)

    # ------------------------------------------------------------- port: out
    async def update_instructions(self, instructions: str) -> None:
        """GA Realtime session shape (the beta shape — flat formats/modalities/voice, `OpenAI-Beta` header —
        was retired by the provider; verified live 2026-09-23). Audio config is nested under `audio.input/output`,
        `turn_detection` lives in `audio.input`, and `turn_detection` is set to None so QEVION's turn plane owns
        endpointing unless `server_vad` is requested."""
        cfg = self.config
        transcription: dict[str, Any] = {"model": "whisper-1"}
        if cfg.language_hint is not None:
            transcription["language"] = cfg.language_hint[:2]
        audio_in: dict[str, Any] = {
            "format": _ga_format(cfg.input_format),
            "transcription": transcription,
            "turn_detection": {"type": "server_vad"} if cfg.server_vad else None,
        }
        audio_out: dict[str, Any] = {"format": _ga_format(cfg.output_format)}
        if cfg.voice:
            audio_out["voice"] = cfg.voice
        session: dict[str, Any] = {
            "type": "realtime",
            "instructions": instructions,
            "output_modalities": ["audio"],
            "audio": {"input": audio_in, "output": audio_out},
            "tools": render_tools(cfg.tools),
            "tool_choice": "auto",
        }
        session.update(cfg.extra.get("session", {}))
        await self._send({"type": "session.update", "session": session})

    async def send_audio(self, pcm16: bytes, ref: AudioFrameRef) -> None:
        await self._send({"type": "input_audio_buffer.append", "audio": base64.b64encode(pcm16).decode()})

    async def commit_input(self) -> None:
        await self._send({"type": "input_audio_buffer.commit"})
        if not self.config.server_vad:
            await self._send({"type": "response.create"})

    async def send_text(self, text: str) -> None:
        await self._send(
            {
                "type": "conversation.item.create",
                "item": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": text}]},
            }
        )
        await self._send({"type": "response.create"})

    async def send_tool_result(self, result: ToolCallResult) -> None:
        output = result.output if result.error is None else {"error": result.error, **result.output}
        await self._send(
            {
                "type": "conversation.item.create",
                "item": {"type": "function_call_output", "call_id": result.call_id, "output": json.dumps(output)},
            }
        )
        await self._send({"type": "response.create"})

    async def cancel_response(self, response_id: str | None = None) -> None:
        await self._send({"type": "response.cancel"})
        # Also clear any audio queued but not yet pumped to the transport (barge-in step 4, §31).
        drained = 0
        while not self._audio.empty():
            try:
                item = self._audio.get_nowait()
            except asyncio.QueueEmpty:
                break
            if item is None:
                self._audio.put_nowait(None)
                break
            drained += 1
        self.sent.append({"type": "_audio_drained", "bytes": drained})

    # -------------------------------------------------------------- port: in
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

    # --------------------------------------------------------------- pumping
    async def _pump_loop(self) -> None:
        try:
            while not self._closed:
                raw = await self._sock.recv()
                if raw is None:
                    break
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                self.handle_provider_message(msg)
        finally:
            if not self._closed:
                self._closed = True
                self._events.put_nowait(S2SEvent(type=S2SEventType.CLOSED, raw_type="socket_eof"))
                self._events.put_nowait(None)
                self._audio.put_nowait(None)

    def handle_provider_message(self, msg: dict[str, Any]) -> S2SEvent | None:
        """Pure translation (sync, testable). Enqueues neutral events/audio; returns the event or None."""
        t = str(msg.get("type", ""))
        rid = msg.get("response_id") or (msg.get("response") or {}).get("id")
        ev: S2SEvent | None = None
        if t in ("session.created", "session.updated"):
            if not self._ready_sent:
                self._ready_sent = True
                ev = S2SEvent(type=S2SEventType.SESSION_READY, raw_type=t, provider_event_id=msg.get("event_id"))
        elif t == "input_audio_buffer.speech_started":
            ev = S2SEvent(type=S2SEventType.INPUT_SPEECH_STARTED, raw_type=t)
        elif t == "input_audio_buffer.speech_stopped":
            ev = S2SEvent(type=S2SEventType.INPUT_SPEECH_STOPPED, raw_type=t)
        elif t == "conversation.item.input_audio_transcription.completed":
            ev = S2SEvent(
                type=S2SEventType.INPUT_TRANSCRIPT, raw_type=t, text=msg.get("transcript"), item_id=msg.get("item_id")
            )
        elif t == "response.created":
            self._current_response = rid
            ev = S2SEvent(type=S2SEventType.RESPONSE_STARTED, raw_type=t, response_id=rid)
        elif t in ("response.audio.delta", "response.output_audio.delta"):
            pcm = base64.b64decode(msg.get("delta", ""))
            fmt = self.config.output_format
            ref = AudioFrameRef(
                frame_id=f"{rid}:{msg.get('event_id', len(self.sent))}",
                byte_length=len(pcm),
                duration_ms=int(len(pcm) / 2 / fmt.sample_rate_hz * 1000),
                fmt=fmt,
            )
            self._audio.put_nowait((ref, pcm))
            ev = S2SEvent(type=S2SEventType.RESPONSE_AUDIO_DELTA, raw_type=t, response_id=rid, audio=ref)
        elif t in ("response.audio_transcript.delta", "response.output_audio_transcript.delta", "response.text.delta"):
            ev = S2SEvent(type=S2SEventType.RESPONSE_TEXT_DELTA, raw_type=t, response_id=rid, text=msg.get("delta"))
        elif t == "response.function_call_arguments.done":
            try:
                args = json.loads(msg.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {"_raw": msg.get("arguments")}
            ev = S2SEvent(
                type=S2SEventType.RESPONSE_TOOL_CALL,
                raw_type=t,
                response_id=rid,
                item_id=msg.get("item_id"),
                tool_call=ToolCallRequest(
                    call_id=str(msg.get("call_id")), tool_id=str(msg.get("name")), arguments=args
                ),
            )
        elif t == "response.done":
            status = (msg.get("response") or {}).get("status")
            kind = S2SEventType.RESPONSE_CANCELLED if status == "cancelled" else S2SEventType.RESPONSE_DONE
            ev = S2SEvent(type=kind, raw_type=t, response_id=rid)
            if rid == self._current_response:
                self._current_response = None
        elif t == "error":
            e = msg.get("error") or {}
            etype = str(e.get("type") or "provider_error")
            pcode = e.get("code")
            ev = S2SEvent(
                type=S2SEventType.ERROR,
                raw_type=t,
                error=ProviderError(
                    code=etype,
                    message=str(e.get("message") or "")[:500],
                    retryable=etype in {"rate_limit_error", "server_error"},
                    provider_code=pcode,
                    fatal=_is_fatal(etype, pcode),
                ),
            )
        if ev is not None:
            self._events.put_nowait(ev)
        return ev


class OpenAIRealtimeAdapter:
    name = "openai_realtime"

    def __init__(self, socket_factory: SocketFactory | None = None, *, url: str = DEFAULT_URL) -> None:
        self._factory = socket_factory or websockets_factory
        self._url = url
        self.sessions: list[OpenAIRealtimeSession] = []

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            adapter=self.name,
            role=ProviderRole.S2S,
            capabilities=[
                Capability(name="language:ar-EG", state=CapabilityState.UNVERIFIED, notes="verify with operator key"),
                Capability(name="language:en-US", state=CapabilityState.UNVERIFIED, notes="verify with operator key"),
                Capability(name="audio:pcm16_24k", state=CapabilityState.SUPPORTED),
                Capability(name="feature:tool_calls", state=CapabilityState.SUPPORTED),
                Capability(name="feature:barge_in", state=CapabilityState.SUPPORTED, notes="response.cancel"),
                Capability(
                    name="feature:server_vad",
                    state=CapabilityState.SUPPORTED,
                    notes="disabled by default; turn plane owns endpointing",
                ),
                Capability(name="feature:input_transcript", state=CapabilityState.SUPPORTED),
            ],
        )

    async def open(self, config: S2SSessionConfig, credential: str | None) -> OpenAIRealtimeSession:
        if not credential:
            raise PermissionError("openai_realtime: no credential resolved (env / admin store / ephemeral UI)")
        headers = {"Authorization": f"Bearer {credential}"}  # GA endpoint: no OpenAI-Beta header
        sock = await self._factory(f"{self._url}?model={config.model}", headers)
        s = OpenAIRealtimeSession(config, sock)
        s.start()
        self.sessions.append(s)
        return s


__all__ = ["OpenAIRealtimeAdapter", "OpenAIRealtimeSession", "Socket", "SocketFactory", "render_tools"]
