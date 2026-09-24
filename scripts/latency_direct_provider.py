"""Provider-isolation probe: the same synthetic clips sent DIRECTLY to OpenAI Realtime (no QEVION server, no
browser), using the exact session.update QEVION sends (same instructions/tools/voice/transcription), committing
at the same moment QEVION's turn plane would (last voiced frame + min_silence_ms 500 ms).

Two variants per clip:
  * tools  = the activity's real tool set (the model may call tools; tool results are answered immediately with
             the in-memory backend output shape `{"status":"completed"}` so the provider continues as in QEVION)
  * notools = same instructions, `tools: []` (pure speech-in → speech-out generation latency)

Reports, per turn: commit→response.created, commit→first audio delta, # responses, # tool calls.

usage: OPENAI_API_KEY=… latency_direct_provider.py OUT.json [--repeat 2]
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import pathlib
import sys
import time
from typing import Any

import websockets

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from latency_corpus import SESSIONS, last_voiced_frame, stats, tts  # noqa: E402

REPEAT = int(sys.argv[sys.argv.index("--repeat") + 1]) if "--repeat" in sys.argv else 2
URL = "wss://api.openai.com/v1/realtime?model=gpt-realtime"


def qevion_session_update() -> dict[str, Any]:
    """Build the exact provider config QEVION would send for act_order_intake on comp_s2s_openai_v1."""
    from qevion.adapters.transports.memory import MemoryTransportSession
    from qevion.contracts.common import Channel
    from qevion.main import _seed
    from qevion.runtime.store import RuntimeStore

    store = RuntimeStore()
    _seed(store)
    key = next(k for k in store.activities if k.startswith("act_order_intake"))
    live = store.build_session(
        activity_key=key,
        transport=MemoryTransportSession(),
        session_id="ses_probe",
        channel=Channel.BROWSER_VOICE,
        composition_id="comp_s2s_openai_v1",
    )
    sess = live.session
    composed = sess.composer.compose(sess._snapshot())  # noqa: SLF001
    from qevion.adapters.providers.openai_realtime import OpenAIRealtimeSession

    cap: list[dict[str, Any]] = []

    class _S:
        async def send(self, t: str) -> None:
            cap.append(json.loads(t))

        async def recv(self) -> None:
            return None

        async def close(self) -> None:
            return None

    rs = OpenAIRealtimeSession(sess.deps.s2s_config, _S())  # type: ignore[arg-type]
    asyncio.run(rs.update_instructions(composed.text))
    return next(m for m in cap if m["type"] == "session.update")


async def one_session(
    plan: list[str], clips: dict[str, bytes], lastv: dict[str, int], upd: dict[str, Any]
) -> list[Any]:
    hdr = {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"}
    rows: list[dict[str, Any]] = []
    async with websockets.connect(URL, additional_headers=hdr, max_size=None) as ws:
        await ws.send(json.dumps(upd))
        # wait for session.updated
        while True:
            m = json.loads(await ws.recv())
            if m["type"] in ("session.updated", "error"):
                break
        for name in plan:
            pcm = clips[name]
            cut = (lastv[name] + 1) * 960
            nxt = time.monotonic()
            for i in range(0, cut, 960):  # realtime-paced upload like the browser/server path
                await ws.send(
                    json.dumps(
                        {"type": "input_audio_buffer.append", "audio": base64.b64encode(pcm[i : i + 960]).decode()}
                    )
                )
                nxt += 0.02
                await asyncio.sleep(max(0.0, nxt - time.monotonic()))
            silence = base64.b64encode(b"\x00\x00" * 480).decode()
            for _ in range(25):  # 500 ms of silence = the turn plane's min_silence_ms before commit
                await ws.send(json.dumps({"type": "input_audio_buffer.append", "audio": silence}))
                nxt += 0.02
                await asyncio.sleep(max(0.0, nxt - time.monotonic()))
            t4 = time.time() * 1000
            await ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
            await ws.send(json.dumps({"type": "response.create"}))
            r: dict[str, Any] = {
                "clip": name,
                "tools": bool(upd["session"].get("tools")),
                "responses": 0,
                "tool_calls": 0,
            }
            pending_done = 1
            audio_ms = 0.0
            while pending_done > 0:
                m = json.loads(await asyncio.wait_for(ws.recv(), 30))
                t = time.time() * 1000
                ty = m["type"]
                if ty == "response.created":
                    r["responses"] += 1
                    r.setdefault("T4_T6_created", round(t - t4, 1))
                elif ty in ("response.output_audio.delta", "response.audio.delta"):
                    r.setdefault("T4_T7_first_audio", round(t - t4, 1))
                    audio_ms += len(base64.b64decode(m.get("delta", ""))) / 48.0
                elif ty == "response.function_call_arguments.done":
                    r["tool_calls"] += 1
                    await ws.send(
                        json.dumps(
                            {
                                "type": "conversation.item.create",
                                "item": {
                                    "type": "function_call_output",
                                    "call_id": m["call_id"],
                                    "output": json.dumps({"status": "completed"}),
                                },
                            }
                        )
                    )
                    await ws.send(json.dumps({"type": "response.create"}))
                    pending_done += 1
                elif ty == "response.done":
                    pending_done -= 1
                elif ty == "error":
                    r["error"] = m.get("error", {}).get("code")
                    if "active_response" not in str(r["error"]):
                        pending_done -= 1
            r["audio_ms"] = round(audio_ms)
            rows.append(r)
            await asyncio.sleep(audio_ms / 1000 + 0.8)  # the "user" listens, then pauses
    return rows


async def main() -> int:
    out = sys.argv[1]
    names = sorted({n for p in SESSIONS for n in p})
    clips = {n: tts(n) for n in names}
    lastv = {n: last_voiced_frame(clips[n]) for n in names}
    upd = qevion_session_update()
    upd_nt = json.loads(json.dumps(upd))
    upd_nt["session"]["tools"] = []
    rows: list[dict[str, Any]] = []
    for _ in range(REPEAT):
        for plan in SESSIONS:
            for u in (upd, upd_nt):
                try:
                    rows += await one_session(plan, clips, lastv, u)
                except Exception as e:  # noqa: BLE001
                    rows.append({"error": f"{type(e).__name__}: {e}"})
                pathlib.Path(out).write_text(json.dumps({"rows": rows}, ensure_ascii=False))
    ok = [r for r in rows if "error" not in r or r.get("T4_T7_first_audio")]
    summary: dict[str, Any] = {}
    for label, sel in (
        ("tools_all", [r for r in ok if r.get("tools")]),
        ("tools_no_call", [r for r in ok if r.get("tools") and r["tool_calls"] == 0]),
        ("tools_with_call", [r for r in ok if r.get("tools") and r["tool_calls"] > 0]),
        ("notools", [r for r in ok if not r.get("tools")]),
    ):
        summary[label] = {
            "n": len(sel),
            "T4_T6_created": stats([r["T4_T6_created"] for r in sel if "T4_T6_created" in r]),
            "T4_T7_first_audio": stats([r["T4_T7_first_audio"] for r in sel if "T4_T7_first_audio" in r]),
        }
    summary["errors"] = [r for r in rows if "error" in r]
    pathlib.Path(out).write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1))
    print(json.dumps({k: v for k, v in summary.items() if k != "errors"}, indent=1)[:3000])
    print("errors", len(summary["errors"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
