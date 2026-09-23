"""OPS 5.5 P2: transcription model is a composition option (F-P2-1); the running turn detector is reported
honestly (F-09) — `silero_fallback_energy` when the ONNX model/onnxruntime is absent."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from qevion.adapters.providers.openai_realtime import DEFAULT_TRANSCRIPTION_MODEL, OpenAIRealtimeAdapter
from qevion.adapters.turn.silero import SileroTurnAdapter
from qevion.contracts.provider import S2SSessionConfig


class _Sock:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.closed = asyncio.Event()

    async def send(self, raw: str) -> None:
        self.sent.append(json.loads(raw))

    async def recv(self) -> str | None:
        await self.closed.wait()
        return None

    async def close(self) -> None:
        self.closed.set()


def _session_update(extra: dict[str, Any]) -> dict[str, Any]:
    sock = _Sock()

    async def factory(url: str, headers: dict[str, str]) -> _Sock:
        return sock

    async def go() -> dict[str, Any]:
        ad = OpenAIRealtimeAdapter(socket_factory=factory)
        cfg = S2SSessionConfig(provider="openai_realtime", model="gpt-realtime", language_hint="ar-EG", extra=extra)
        sess = await ad.open(cfg, credential="sk-test")
        await sess.update_instructions("x")
        await sess.close()
        return next(m for m in sock.sent if m["type"] == "session.update")

    return asyncio.run(go())


def test_transcription_model_default_and_override() -> None:
    d = _session_update({})["session"]["audio"]["input"]["transcription"]
    assert d == {"model": DEFAULT_TRANSCRIPTION_MODEL, "language": "ar"}
    o = _session_update({"transcription_model": "gpt-4o-transcribe"})["session"]["audio"]["input"]["transcription"]
    assert o["model"] == "gpt-4o-transcribe"


def test_silero_fallback_is_named_honestly() -> None:
    ad = SileroTurnAdapter(autoload=False)
    assert ad.model_available is False
    assert ad.new_detector().detector_name == "silero_fallback_energy"
    cap = {c.name: c.state.value for c in ad.capabilities().capabilities}
    assert cap["feature:vad:silero"] == "UNVERIFIED"


def test_silero_with_model_reports_silero() -> None:
    ad = SileroTurnAdapter(model=lambda w: 0.9)
    assert ad.new_detector().detector_name == "silero"


def test_runtime_reports_running_detector_and_transcription_model() -> None:
    from qevion.runtime.store import RuntimeStore

    store = RuntimeStore()
    comp = store.compositions["comp_s2s_openai_v1"]
    s2s_b = next(b for b in comp.bindings if b.role.value == "s2s")
    assert s2s_b.config.get("transcription_model") == "gpt-4o-transcribe"
    assert store.turn_adapters["silero"].new_detector().detector_name in ("silero", "silero_fallback_energy")
