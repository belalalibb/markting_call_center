"""E2E over the public preview: browser_voice WS → binary audio out → barge-in → t0..t4 → REST interruptions."""

import asyncio
import json
import struct
import sys
import time
import urllib.request

import websockets

BASE = sys.argv[1]
WS = BASE.replace("https://", "wss://").replace("http://", "ws://")


def get(p):
    return json.load(urllib.request.urlopen(BASE + p, timeout=20))


def frame(a, n=480):
    return struct.pack(f"<{n}h", *([a, -a] * (n // 2)))


async def main():
    acts = get("/api/activities")
    key = next(a["key"] for a in acts if a["activity_id"] == "act_csat_survey")
    comps = get("/api/compositions")
    out = {
        "preview_url": BASE,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "activity_key": key,
        "compositions": [
            {"id": c["composition_id"], "credential_source": c["credential_source"], "default": c["default"]}
            for c in comps
        ],
    }
    async with websockets.connect(
        f"{WS}/ws/sessions/{key}?channel=browser_voice&composition=comp_mock_s2s_v1", max_size=None
    ) as ws:
        await ws.send(json.dumps({"type": "hello"}))
        await ws.send(json.dumps({"type": "audio_commit"}))
        rid = None
        audio_bytes = 0
        t_first_audio = None
        t_start = time.time()
        while True:
            m = await asyncio.wait_for(ws.recv(), 10)
            if isinstance(m, bytes):
                audio_bytes += len(m)
                t_first_audio = t_first_audio or round((time.time() - t_start) * 1000)
                if rid:
                    break
            else:
                j = json.loads(m)
                if j["type"] == "audio_start":
                    rid = j["response_id"]
        out["greeting_response_id"] = rid
        out["ms_to_first_audio_frame"] = t_first_audio
        t_barge = time.time()
        for _ in range(20):
            await ws.send(frame(6000))
        seen = []
        interruption = None
        stop_at = None
        while len(seen) < 300:
            m = await asyncio.wait_for(ws.recv(), 10)
            if isinstance(m, bytes):
                audio_bytes += len(m)
                continue
            j = json.loads(m)
            seen.append(j["type"] if j["type"] != "event" else f"event:{j['payload']['type']}")
            if j["type"] == "stop_playout":
                stop_at = round((time.time() - t_barge) * 1000)
                await ws.send(
                    json.dumps(
                        {
                            "type": "playout_stopped",
                            "response_id": j["response_id"],
                            "client_ts_ms": int(time.time() * 1000),
                        }
                    )
                )
            if (
                j["type"] == "event"
                and j["payload"]["type"] == "latency.sample"
                and j["payload"]["payload"].get("segment") == "interruption"
            ):
                interruption = j["payload"]["payload"]
                break
        out["wall_ms_barge_sent_to_stop_playout"] = stop_at
        out["interruption_sample"] = interruption
        out["messages_after_barge"] = seen
        for _ in range(30):
            await ws.send(frame(0))
        await ws.send(json.dumps({"type": "bye"}))
        try:
            while True:
                await asyncio.wait_for(ws.recv(), 3)
        except Exception:
            pass
        out["audio_bytes_received"] = audio_bytes
    sess = get("/api/sessions")[-1]
    det = get(f"/api/sessions/{sess['session_id']}")
    out["session"] = {
        k: det[k] for k in ("session_id", "composition_id", "credential_source", "running", "error", "interruptions")
    }
    out["event_types"] = sorted({e["type"] for e in det["events"]})
    ok = (
        interruption is not None
        and det["interruptions"]
        and det["interruptions"][0]["response_id"] == rid
        and not det["interruptions"][0]["forced"]
    )
    out["verdict"] = "PASS" if ok else "FAIL"
    print(json.dumps(out, indent=2))


asyncio.run(main())
