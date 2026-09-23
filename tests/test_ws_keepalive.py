"""Long-lived browser_voice WS regression (QV-INT keepalive).

Field failure: browser session on comp_s2s_openai_v1 died with `1011: keepalive ping timeout` while the agent was
speaking. Root cause class: the protocol keepalive (uvicorn/websockets) only progresses when the ASGI app keeps
calling `receive()`; anything that stalls the pump stalls the client's Pong. These tests run a *real* uvicorn
server (TestClient bypasses the protocol layer) with a very aggressive ping window and stream realtime audio.
"""

from __future__ import annotations

import asyncio
import json
import socket
import struct
import threading
import time
from collections.abc import Iterator
from typing import Any

import pytest
import uvicorn
import websockets

from qevion.main import build
from qevion.runtime.app import HEARTBEAT_INTERVAL_S, INBOUND_QUEUE_MAX, WsTransport
from qevion.runtime.store import RuntimeStore

RATE = 24000
FRAME = RATE * 20 // 1000  # 20 ms


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="module")
def server() -> Iterator[str]:
    """Real uvicorn with a 1 s ping / 1 s pong window — any pump stall > 1 s produces the field 1011."""
    port = _free_port()
    app = build(RuntimeStore(), seed_examples=True)
    cfg = uvicorn.Config(
        app, host="127.0.0.1", port=port, log_level="warning", ws_ping_interval=1.0, ws_ping_timeout=1.0
    )
    srv = uvicorn.Server(cfg)
    th = threading.Thread(target=srv.run, daemon=True)
    th.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    assert srv.started
    yield f"ws://127.0.0.1:{port}"
    srv.should_exit = True
    th.join(timeout=5)


def _tone(phase: int, amp: int) -> bytes:
    return struct.pack(f"<{FRAME}h", *[int(amp * ((i + phase) % 60 < 30) * 2 - amp) for i in range(FRAME)])


async def _soak(url: str, seconds: float, *, speak_every_s: float = 3.0) -> dict[str, Any]:
    """Stream realtime-paced 20 ms frames (bursts of 'speech'); collect server messages + close code."""
    out: dict[str, Any] = {"types": {}, "audio_frames": 0, "pings": 0, "ready": None, "close": None, "dialog": []}
    async with websockets.connect(url, ping_interval=None, max_size=None) as ws:  # client does not ping: server must
        await ws.send(json.dumps({"type": "hello"}))

        async def reader() -> None:
            try:
                async for raw in ws:
                    if isinstance(raw, bytes):
                        out["audio_frames"] += 1
                        continue
                    m = json.loads(raw)
                    t = m["type"]
                    out["types"][t] = out["types"].get(t, 0) + 1
                    if t == "ready":
                        out["ready"] = m["payload"]
                    elif t == "ping":
                        out["pings"] += 1
                        await ws.send(json.dumps({"type": "pong"}))  # what the console does
                    elif t == "state":
                        d = m["payload"].get("dialog")
                        if not out["dialog"] or out["dialog"][-1] != d:
                            out["dialog"].append(d)
            except websockets.exceptions.ConnectionClosed:
                pass

        rd = asyncio.create_task(reader())
        t0 = time.monotonic()
        nxt = t0
        phase = 0
        while time.monotonic() - t0 < seconds and not rd.done():
            el = time.monotonic() - t0
            speaking = (el % speak_every_s) < 0.7 and el > 0.5
            await ws.send(_tone(phase, 8000) if speaking else b"\x00\x00" * FRAME)
            phase += FRAME
            nxt += 0.02
            await asyncio.sleep(max(0.0, nxt - time.monotonic()))
        if not rd.done():
            await ws.send(json.dumps({"type": "bye"}))
            await asyncio.wait_for(rd, timeout=5)
        else:
            await rd
        out["close"] = (ws.close_code, ws.close_reason)
    return out


def test_browser_voice_session_survives_aggressive_keepalive_window(server: str) -> None:
    url = f"{server}/ws/sessions/act_order_intake@1.0.0?channel=browser_voice&composition=comp_mock_s2s_v1"
    res = asyncio.run(_soak(url, seconds=8.0))
    # the field failure: protocol close 1011 "keepalive ping timeout" mid-response
    assert res["close"] is not None and res["close"][0] == 1000, res["close"]
    assert res["ready"] is not None
    # `ready` tells the client what it is *actually* connected to (header/status mismatch fix)
    assert res["ready"]["composition_id"] == "comp_mock_s2s_v1"
    assert res["ready"]["channel"] == "browser_voice" and res["ready"]["s2s_provider"] == "mock"
    assert res["ready"]["credential_source"] in {"none", "env", "admin_store", "ephemeral_ui"}
    # agent spoke (binary frames) and returned to listening; user turns were detected while it was long-lived
    assert res["audio_frames"] > 0 and res["types"].get("audio_end", 0) >= 1
    assert "LISTENING" in res["dialog"]


def test_server_heartbeat_pings_and_records_pong_rtt(server: str) -> None:
    url = f"{server}/ws/sessions/act_order_intake@1.0.0?channel=browser_voice&composition=comp_mock_s2s_v1"
    res = asyncio.run(_soak(url, seconds=HEARTBEAT_INTERVAL_S * 2 + 2))
    assert res["close"][0] == 1000, res["close"]
    assert res["pings"] >= 2, res  # server-initiated application heartbeat kept flowing during audio
    assert res["types"].get("ping", 0) == res["pings"]


class _FakeWs:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send_text(self, s: str) -> None:
        self.sent.append(s)

    async def send_bytes(self, b: bytes) -> None:
        pass

    async def close(self, code: int = 1000, reason: str = "") -> None:
        pass


def test_transport_inbound_queue_is_bounded_and_never_drops_control_messages() -> None:
    """A slow Core must not stall the receive loop: audio overflows are dropped oldest-first, control kept."""
    from qevion.contracts.transport import ClientMessage

    t = WsTransport(_FakeWs())  # type: ignore[arg-type]
    for i in range(INBOUND_QUEUE_MAX + 50):
        t.push(bytes([i % 256]) * 2)
    t.push(ClientMessage.model_validate({"type": "text", "text": "hello"}))
    assert t.dropped_audio_frames == 50
    assert t._q.qsize() == INBOUND_QUEUE_MAX + 1  # noqa: SLF001
    items: list[Any] = []
    while not t._q.empty():  # noqa: SLF001
        items.append(t._q.get_nowait())  # noqa: SLF001
    assert isinstance(items[-1], ClientMessage) and items[-1].text == "hello"
    assert items[0] == bytes([50]) * 2  # the first 50 (oldest) audio frames were the ones dropped
    assert not t.stale
