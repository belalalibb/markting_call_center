"""Live E2E: a real QEVION session on the OpenAI Realtime S2S composition through the running server (QV-ACC-022).

Key from ``OPENAI_API_KEY`` (env only) → injected via Admin ephemeral test-key (memory only). The report holds a
fingerprint, timings, event types and byte counts — never the key, never audio, transcripts only as lengths.

Flow: WS `/ws/sessions/{activity}?channel=text&composition=comp_s2s_openai_v1` → hello → a short ar-EG survey
turn → collect audio frames (binary), forwarded events, state changes → bye → REST session detail.

Usage: OPENAI_API_KEY=... .venv/bin/python scripts/openai_realtime_live_ws.py [out.json] [--base http://localhost:8000]
Exit 0 iff session ran on openai_realtime with credential_source != none, ≥1 audio frame, ≥1 response.done,
no provider error; 2 when key/server missing.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import UTC, datetime
from typing import Any
from urllib import request

import websockets

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from session_health import fetch_events, verdict  # noqa: E402

ACTIVITY = "act_csat_survey@1.0.0"
COMPOSITION = "comp_s2s_openai_v1"
TURNS = ["أهلا", "الخدمة كانت كويسة، أديها أربعة من خمسة", "لا شكرا، مع السلامة"]


def _fingerprint(key: str) -> str:
    return f"…{key[-4:]}" if len(key) >= 4 else "…"


def _post(base: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
    req = request.Request(
        base + path, data=json.dumps(body).encode(), headers={"content-type": "application/json"}, method="POST"
    )
    with request.urlopen(req, timeout=10) as resp:  # noqa: S310 - local server, operator-run script
        return dict(json.loads(resp.read().decode()))


def _get(base: str, path: str) -> dict[str, Any]:
    with request.urlopen(base + path, timeout=10) as resp:  # noqa: S310 - local server
        return dict(json.loads(resp.read().decode()))


async def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    base = sys.argv[sys.argv.index("--base") + 1] if "--base" in sys.argv else "http://localhost:8000"
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key:
        print("OPENAI_API_KEY not set", file=sys.stderr)
        return 2
    try:
        _post(base, "/api/admin/test-key", {"provider": "openai", "value": key, "ttl_seconds": 600})
        cred = _get(base, "/api/admin/credentials/openai")
    except Exception as exc:  # noqa: BLE001
        print(f"server unreachable: {exc}", file=sys.stderr)
        return 2

    ws_base = base.replace("http://", "ws://").replace("https://", "wss://")
    url = f"{ws_base}/ws/sessions/{ACTIVITY}?channel=text&composition={COMPOSITION}"
    t0 = time.monotonic()
    detail: dict[str, Any] = {}
    outcome_primary: str | None = None
    session_id: str | None = None
    audio_frames = 0
    audio_bytes = 0
    events: list[dict[str, Any]] = []
    server_msgs: dict[str, int] = {}
    errors: list[str] = []
    turn_timings: list[dict[str, Any]] = []

    def now() -> int:
        return int((time.monotonic() - t0) * 1000)

    async def drain(ws: Any, until: set[str], timeout: float) -> dict[str, Any]:
        nonlocal session_id, audio_frames, audio_bytes, outcome_primary
        seen: dict[str, Any] = {"first_audio_ms": None, "response_done_ms": None}
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=max(0.05, deadline - time.monotonic()))
            except TimeoutError:
                break
            except websockets.exceptions.ConnectionClosed:
                break
            if isinstance(raw, bytes):
                audio_frames += 1
                audio_bytes += len(raw)
                if seen["first_audio_ms"] is None:
                    seen["first_audio_ms"] = now()
                continue
            msg = json.loads(raw)
            mtype = str(msg.get("type"))
            server_msgs[mtype] = server_msgs.get(mtype, 0) + 1
            session_id = session_id or msg.get("session_id")
            if mtype == "error":
                errors.append(str(msg.get("text"))[:200])
            if mtype == "event":
                env = msg.get("payload") or {}
                et = str(env.get("type"))
                payload = env.get("payload") or {}
                events.append({"t_ms": now(), "type": et, "keys": sorted(payload)[:8]})
                if et.startswith("provider.error") or et == "session.failed" or et == "failure.classified":
                    errors.append(f"{et}:{payload.get('code') or payload.get('class')}")
                if et == "outcome.produced":
                    outcome_primary = payload.get("primary")
                if et in ("s2s.response_done", "provider.response_done", "response.done"):
                    seen["response_done_ms"] = now()
                if et in until:
                    break
        return seen

    try:
        async with websockets.connect(url, open_timeout=15, max_size=None) as ws:
            await ws.send(json.dumps({"type": "hello"}))
            await drain(ws, {"session.started"}, 8.0)
            for text in TURNS:
                sent = now()
                await ws.send(json.dumps({"type": "text", "text": text}))
                seen = await drain(ws, set(), 9.0)
                turn_timings.append(
                    {
                        "text_len": len(text),
                        "sent_ms": sent,
                        "first_audio_ms": seen["first_audio_ms"],
                        "ttfa_ms": (seen["first_audio_ms"] - sent) if seen["first_audio_ms"] else None,
                    }
                )
            # session detail is read while the session is still alive (finished sessions are pruned from the store)
            if session_id:
                try:
                    detail = _get(base, f"/api/sessions/{session_id}")
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"detail: {exc}")
            await ws.send(json.dumps({"type": "bye"}))
            await drain(ws, {"outcome.produced"}, 6.0)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"{type(exc).__name__}: {str(exc)[:200]}")

    event_types = sorted({e["type"] for e in events})
    provider_ok = detail.get("composition_id") == COMPOSITION and (detail.get("credential_source") or "none") != "none"
    health: dict[str, Any] = verdict(fetch_events(base, session_id)) if session_id else {"passed": False}
    passed = provider_ok and audio_frames > 0 and not errors and not detail.get("error") and bool(health["passed"])
    report = {
        "core_health": health,
        "kind": "openai-realtime-live-ws-e2e",
        "produced_at": datetime.now(UTC).isoformat(),
        "base": base,
        "activity": ACTIVITY,
        "composition": COMPOSITION,
        "key_fingerprint": _fingerprint(key),
        "admin_credential_source": cred.get("source"),
        "session_id": session_id,
        "session_detail": {
            k: detail.get(k)
            for k in (
                "composition_id",
                "credential_source",
                "decision_credential_source",
                "running",
                "dialog_state",
                "activity_state",
                "error",
                "interruptions",
            )
        },
        "outcome": outcome_primary,
        "session_events_seen": len(detail.get("events") or []),
        "tool_calls": [
            (e.get("payload") or {}).get("tool_id")
            for e in (detail.get("events") or [])
            if e.get("type") == "tool.execution_completed"
        ],
        "turns": turn_timings,
        "audio": {"frames": audio_frames, "bytes": audio_bytes, "ms_pcm16_24k": int(audio_bytes / 2 / 24000 * 1000)},
        "server_message_counts": server_msgs,
        "event_types": event_types,
        "events": events[:80],
        "errors": errors,
        "passed": passed,
    }
    out = json.dumps(report, ensure_ascii=False, indent=1)
    if args:
        with open(args[0], "w", encoding="utf-8") as fh:
            fh.write(out + "\n")
    print(out)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
