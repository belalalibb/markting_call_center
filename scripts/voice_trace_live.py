"""Live voice lifecycle trace against a running QEVION server (OPS 5.5 audit harness, now tracked).

Streams speech clips (PCM16 24 kHz mono, 20 ms frames, realtime-paced, mic-style silence around them) over the
browser_voice WebSocket, mimics the console's playout reporting, and records the complete Core event trace plus the
F-11 health verdict. Clips are synthesized once per run with OpenAI TTS into a temp dir (Egyptian-Arabic phrases):
synthetic speech → lifecycle/regression evidence, NOT proof of human-speech fidelity.

usage: OPENAI_API_KEY=… voice_trace_live.py OUT.json [--base URL] [--plan u1_order,u2_address] [--bargein]
                                               [--late-bargein] [--token TOKEN]
  --bargein       start the next clip 0.6 s after the agent starts speaking (during generation)
  --late-bargein  start the next clip ~1 s after provider response.done while playout is still pending (F-02)
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import sys
import tempfile
import time
import urllib.request
from typing import Any

import websockets

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from session_health import fetch_events, verdict  # noqa: E402

PHRASES = {
    "u1_order": "السلام عليكم، عايز أطلب اتنين بيتزا مارجريتا كبيرة وواحد بيبسي.",
    "u2_address": "العنوان تلاتة وعشرين شارع التحرير، الدقي، الدور الخامس.",
    "u3_yes": "أيوه تمام كده، اتفقنا.",
    "u4_no": "لا لا، مش عايز ده خالص.",
    "u7_correction": "لا استنى، مش اتنين، خليهم تلاتة بيتزا.",
}


def arg(n: str, d: str) -> str:
    return sys.argv[sys.argv.index(n) + 1] if n in sys.argv else d


BASE = arg("--base", "http://localhost:8000").rstrip("/")
PLAN = arg("--plan", "u1_order,u2_address").split(",")
COMP = arg("--composition", "comp_s2s_openai_v1")
ACT = arg("--activity", "act_order_intake@1.0.0")
TOKEN = arg("--token", os.environ.get("QEVION_ADMIN_TOKEN", ""))
HDR = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}


def tts(dirp: pathlib.Path, name: str) -> bytes:
    p = dirp / f"{name}.pcm"
    if p.exists():
        return p.read_bytes()
    body = json.dumps(
        {
            "model": "gpt-4o-mini-tts",
            "voice": "alloy",
            "input": PHRASES[name],
            "response_format": "pcm",
            "instructions": "Speak in natural Egyptian Arabic, conversational pace.",
        }
    ).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/audio/speech",
        data=body,
        method="POST",
        headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310
        pcm = r.read()
    p.write_bytes(pcm)
    return pcm


def post(path: str, body: dict[str, Any]) -> Any:
    r = urllib.request.Request(
        BASE + path, data=json.dumps(body).encode(), method="POST", headers={"content-type": "application/json", **HDR}
    )
    return json.loads(urllib.request.urlopen(r, timeout=10).read())  # noqa: S310


def get(path: str) -> Any:
    return json.loads(urllib.request.urlopen(urllib.request.Request(BASE + path, headers=HDR), timeout=10).read())  # noqa: S310


async def main() -> int:
    out = sys.argv[1]
    clips_dir = pathlib.Path(os.environ.get("QEVION_TTS_CACHE", tempfile.gettempdir())) / "qevion_tts"
    clips_dir.mkdir(parents=True, exist_ok=True)
    clips = {n: tts(clips_dir, n) for n in PLAN}
    post("/api/admin/test-key", {"provider": "openai", "value": os.environ["OPENAI_API_KEY"], "ttl_seconds": 900})
    url = BASE.replace("http", "ws", 1) + f"/ws/sessions/{ACT}?channel=browser_voice&composition={COMP}"
    t0 = time.monotonic()

    def now() -> int:
        return int((time.monotonic() - t0) * 1000)

    log: list[Any] = []
    st: dict[str, Any] = {
        "speaking": False,
        "frames": 0,
        "sid": None,
        "starts": 0,
        "ends": 0,
        "voiced_ends": 0,
        "transcripts": [],
        "stops": 0,
        "last_end_ms": 0,
        "ready": None,
    }
    silence = b"\x00\x00" * 480
    async with websockets.connect(url, max_size=None, additional_headers=HDR) as ws:

        async def reader() -> None:
            try:
                async for raw in ws:
                    if isinstance(raw, bytes):
                        st["frames"] += 1
                        continue
                    m = json.loads(raw)
                    t = m["type"]
                    st["sid"] = st["sid"] or m.get("session_id")
                    if t == "ping":
                        await ws.send(json.dumps({"type": "pong"}))
                        continue
                    if t == "ready":
                        st["ready"] = m.get("payload")
                    if t == "audio_start":
                        st["speaking"], st["starts"] = True, st["starts"] + 1
                        await ws.send(json.dumps({"type": "playout_started", "response_id": m.get("response_id")}))
                    if t == "audio_end":
                        st["speaking"], st["ends"], st["last_end_ms"] = False, st["ends"] + 1, now()
                        if int((m.get("payload") or {}).get("audio_ms") or 0) > 0:
                            st["voiced_ends"] += 1
                    if t == "stop_playout":
                        st["speaking"], st["stops"] = False, st["stops"] + 1
                        await ws.send(json.dumps({"type": "playout_stopped", "response_id": m.get("response_id")}))
                    if t == "transcript" and (m.get("payload") or {}).get("role") == "user":
                        st["transcripts"].append((now(), m.get("text") or ""))
                    log.append((now(), t, m.get("response_id") or ""))
            except websockets.exceptions.ConnectionClosed as e:
                log.append((now(), "ws_closed", e.rcvd.code if e.rcvd else None))

        rd = asyncio.create_task(reader())
        await ws.send(json.dumps({"type": "hello"}))

        async def silence_for(sec: float) -> None:
            nxt = time.monotonic()
            for _ in range(int(sec / 0.02)):
                await ws.send(silence)
                nxt += 0.02
                await asyncio.sleep(max(0.0, nxt - time.monotonic()))

        async def stream(name: str) -> None:
            log.append((now(), "cli:utterance_start", name))
            pcm, nxt = clips[name], time.monotonic()
            for i in range(0, len(pcm), 960):
                await ws.send(pcm[i : i + 960])
                nxt += 0.02
                await asyncio.sleep(max(0.0, nxt - time.monotonic()))
            log.append((now(), "cli:utterance_end", name))

        await silence_for(2.0)
        voiced0 = 0
        for i, name in enumerate(PLAN):
            if i > 0 and "--bargein" in sys.argv:
                for _ in range(500):
                    if st["speaking"]:
                        break
                    await silence_for(0.02)
                await silence_for(0.6)
                log.append((now(), "cli:bargein", ""))
            elif i > 0 and "--late-bargein" in sys.argv:
                for _ in range(750):
                    if st["voiced_ends"] > voiced0:
                        break
                    await silence_for(0.02)
                await silence_for(1.0)
                log.append((now(), "cli:late_bargein", ""))
            await stream(name)
            seen, voiced0 = st["starts"], st["voiced_ends"]
            waited = 0.0
            while waited < 15.0:
                await silence_for(0.5)
                waited += 0.5
                if (
                    st["starts"] > seen
                    and not st["speaking"]
                    and waited > 2.0
                    and not ("--bargein" in sys.argv or "--late-bargein" in sys.argv)
                ):
                    await silence_for(1.5)
                    break
                if ("--bargein" in sys.argv and st["speaking"]) or (
                    "--late-bargein" in sys.argv and st["voiced_ends"] > voiced0
                ):
                    break
        await silence_for(2.5)
        detail: dict[str, Any] = {}
        try:
            detail = get(f"/api/sessions/{st['sid']}")
        except Exception as e:  # noqa: BLE001
            detail = {"error": str(e)}
        await ws.send(json.dumps({"type": "bye"}))
        try:
            await asyncio.wait_for(rd, 8)
        except Exception:  # noqa: BLE001
            pass
    await asyncio.sleep(1.0)  # let the server finish close() before reading the final session state
    try:
        detail = get(f"/api/sessions/{st['sid']}")
    except Exception as e:  # noqa: BLE001
        detail = {"error": str(e)}
    evs = fetch_events(BASE, st["sid"], HDR) if st["sid"] else []
    health = verdict(evs)
    # A session where nobody was heard is not healthy (P2: a broken VAD produced 0 turns yet passed all checks).
    n_commits = sum(1 for e in evs if e["type"] == "user.speech_committed")
    health["checks"]["every_clip_heard"] = n_commits >= len(PLAN)
    health["checks"]["no_session_error"] = not detail.get("error") and any(e["type"] == "outcome.produced" for e in evs)
    health["session_error"] = detail.get("error")
    health["checks"]["agent_spoke"] = st["voiced_ends"] > 0 or st["stops"] > 0
    health["passed"] = all(health["checks"].values())
    core = [
        (
            e["payload"].get("ts_ms"),
            e["type"],
            e.get("turn_id"),
            {k: v for k, v in e["payload"].items() if k != "ts_ms"},
        )
        for e in evs
        if e["type"] not in ("user.speech_discarded",)
    ]
    report = {
        "plan": PLAN,
        "mode": [a for a in sys.argv if a.startswith("--") and "bargein" in a],
        "session_id": st["sid"],
        "ready": st["ready"],
        "audio_frames": st["frames"],
        "audio_start": st["starts"],
        "audio_end": st["ends"],
        "stop_playout": st["stops"],
        "health": health,
        "interruptions": detail.get("interruptions"),
        "session_facts": {k: detail.get(k) for k in ("composition_id", "turn_detector", "transcription_model")},
        "user_transcripts": st["transcripts"],
        "phrases": {n: PHRASES[n] for n in PLAN},
        "client_log": log,
        "core_events": core,
    }
    pathlib.Path(out).write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print(
        json.dumps(
            {
                "health": health["checks"],
                "outcome": health["outcome"],
                "provider_errors": health["provider_errors"],
                "frames": st["frames"],
                "starts": st["starts"],
                "stops": st["stops"],
            },
            ensure_ascii=False,
        )
    )
    return 0 if health["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
