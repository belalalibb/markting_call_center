"""Long-lived browser_voice WS soak against a running QEVION server (QV-INT keepalive regression).

Simulates the browser: streams 20 ms PCM16 @ 24 kHz frames at realtime pace for `--seconds`, mostly silence with
short "speech" bursts so the turn plane produces user turns while the agent speaks. Watches for any close code
(the field failure was `1011 keepalive ping timeout` while the provider was speaking).

Usage:
    .venv/bin/python scripts/ws_keepalive_soak.py [out.json] [--base http://localhost:8000]
        [--composition comp_mock_s2s_v1] [--activity act_order_intake@1.0.0] [--seconds 90]
Exit 0 iff the socket stayed open for the whole soak and closed 1000 on our `bye`; 1 otherwise; 2 unreachable.
"""

from __future__ import annotations

import asyncio
import json
import struct
import sys
import time
from datetime import UTC, datetime
from math import sin
from typing import Any

import websockets

RATE = 24000
FRAME_MS = 20
FRAME_SAMPLES = RATE * FRAME_MS // 1000


def _frame(amplitude: int, phase: int) -> bytes:
    if amplitude == 0:
        return b"\x00\x00" * FRAME_SAMPLES
    vals = [int(amplitude * sin((phase + i) * 2 * 3.14159 * 220 / RATE)) for i in range(FRAME_SAMPLES)]
    return struct.pack(f"<{FRAME_SAMPLES}h", *vals)


def _arg(name: str, default: str) -> str:
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


async def main() -> int:
    out_path = next(
        (a for a in sys.argv[1:] if not a.startswith("--") and not sys.argv[sys.argv.index(a) - 1].startswith("--")),
        None,
    )
    base = _arg("--base", "http://localhost:8000")
    composition = _arg("--composition", "comp_mock_s2s_v1")
    activity = _arg("--activity", "act_order_intake@1.0.0")
    seconds = float(_arg("--seconds", "90"))
    ws_base = base.replace("http://", "ws://").replace("https://", "wss://")
    url = f"{ws_base}/ws/sessions/{activity}?channel=browser_voice&composition={composition}"

    t0 = time.monotonic()
    now = lambda: int((time.monotonic() - t0) * 1000)  # noqa: E731
    msgs: dict[str, int] = {}
    audio_frames_in = 0
    audio_bytes_in = 0
    frames_out = 0
    events: list[tuple[int, str]] = []
    states: list[tuple[int, str]] = []
    pongs = 0
    close_code: int | None = None
    close_reason = ""
    max_recv_gap_ms = 0
    session_id: str | None = None
    error: str | None = None
    ready_ms: int | None = None
    first_audio_ms: int | None = None

    async def reader(ws: Any) -> None:
        nonlocal audio_frames_in, audio_bytes_in, pongs, close_code, close_reason, max_recv_gap_ms
        nonlocal session_id, ready_ms, first_audio_ms
        last = time.monotonic()
        try:
            async for raw in ws:
                gap = int((time.monotonic() - last) * 1000)
                max_recv_gap_ms = max(max_recv_gap_ms, gap)
                last = time.monotonic()
                if isinstance(raw, bytes):
                    audio_frames_in += 1
                    audio_bytes_in += len(raw)
                    if first_audio_ms is None:
                        first_audio_ms = now()
                    continue
                m = json.loads(raw)
                t = str(m.get("type"))
                msgs[t] = msgs.get(t, 0) + 1
                session_id = session_id or m.get("session_id")
                if t == "ready":
                    ready_ms = now()
                elif t == "pong":
                    pongs += 1
                elif t == "state":
                    ds = str((m.get("payload") or {}).get("dialog_state"))
                    if not states or states[-1][1] != ds:
                        states.append((now(), ds))
                elif t == "event":
                    et = str(((m.get("payload") or {}).get("type")))
                    events.append((now(), et))
        except websockets.exceptions.ConnectionClosed as e:
            close_code = e.rcvd.code if e.rcvd else (e.sent.code if e.sent else None)
            close_reason = (e.rcvd.reason if e.rcvd else (e.sent.reason if e.sent else "")) or ""

    try:
        async with websockets.connect(url, open_timeout=15, max_size=None, ping_interval=20, ping_timeout=20) as ws:
            rd = asyncio.create_task(reader(ws))
            await ws.send(json.dumps({"type": "hello"}))
            deadline = time.monotonic() + seconds
            phase = 0
            next_tick = time.monotonic()
            while time.monotonic() < deadline and not rd.done():
                # speak ~1.2 s every 12 s, otherwise silence — realtime-paced 20 ms frames like the browser worklet
                elapsed = time.monotonic() - t0
                speaking = (elapsed % 12.0) < 1.2 and elapsed > 4.0
                await ws.send(_frame(6000 if speaking else 0, phase))
                phase += FRAME_SAMPLES
                frames_out += 1
                if frames_out % 250 == 0:  # every 5 s: app-level ping too (mirrors console heartbeat)
                    await ws.send(json.dumps({"type": "ping"}))
                next_tick += FRAME_MS / 1000
                await asyncio.sleep(max(0.0, next_tick - time.monotonic()))
            if not rd.done():
                await ws.send(json.dumps({"type": "bye"}))
                try:
                    await asyncio.wait_for(rd, timeout=6)
                except TimeoutError:
                    pass
            else:
                await rd
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {str(exc)[:200]}"

    survived_ms = now()
    stayed_open = close_code == 1000 and survived_ms >= int(seconds * 1000) and error is None
    report = {
        "kind": "ws-keepalive-soak",
        "produced_at": datetime.now(UTC).isoformat(),
        "base": base,
        "activity": activity,
        "composition": composition,
        "channel": "browser_voice",
        "target_seconds": seconds,
        "survived_ms": survived_ms,
        "session_id": session_id,
        "ready_ms": ready_ms,
        "first_audio_ms": first_audio_ms,
        "frames_out": frames_out,
        "audio_in": {"frames": audio_frames_in, "bytes": audio_bytes_in},
        "server_message_counts": msgs,
        "app_pongs": pongs,
        "max_recv_gap_ms": max_recv_gap_ms,
        "dialog_states": states[:60],
        "event_types": sorted({e for _, e in events}),
        "close": {"code": close_code, "reason": close_reason},
        "error": error,
        "passed": stayed_open,
    }
    text = json.dumps(report, ensure_ascii=False, indent=1)
    if out_path:
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    print(text)
    return 0 if stayed_open else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
