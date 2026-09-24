"""Latency root-cause corpus (server path). Streams synthetic Egyptian-Arabic clips over the browser_voice WS of a
running QEVION server started with QEVION_LATENCY_TRACE=1, behaves like the console (reports playout start/stop,
waits for realistic playback before the next utterance) and joins client + server epoch-ms marks per turn.

Client and server run on the same host → one clock; no skew correction needed.

T1  last voiced frame of the clip sent (offline Silero on the clip, prob ≥ 0.5)
T2/T3 core:end_of_turn (detector decision == accepted END_OF_TURN in this Core)
T4  sent:input_audio_buffer.commit           T5 recv:input_audio_buffer.committed
T4b sent:response.create                     T6 recv:response.created (first response of the turn)
T7  recv:first_audio_delta (first *voiced* response of the turn)
T8  core:first_audio_to_client               T9 client: first binary frame received
T12 recv:response.function_call_arguments.done  T13/T14 core:tool_start/done  T15 core:tool_result_submit
T16 recv:response.created after T15          T17 recv:first_audio_delta after T15
T18 recv:response.done of the last response of the turn
decision:start/end (per decide() call, with source RULE / LLM / UNKNOWN)

usage: OPENAI_API_KEY=… latency_corpus.py OUT.json [--base URL] [--repeat 2] [--composition comp_s2s_openai_v1]
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import statistics
import sys
import tempfile
import time
import urllib.request
from typing import Any

import websockets

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PHRASES = {
    "u_short": "ازيك؟",
    "u1_order": "السلام عليكم، عايز أطلب اتنين بيتزا مارجريتا كبيرة وواحد بيبسي.",
    "u_long": (
        "بص يا سيدي، أنا عايز أطلب أوردر كبير شوية: اتنين بيتزا مارجريتا كبيرة، وواحدة بيبروني وسط، "
        "وتلات علب بيبسي، ولو فيه أي عرض على الحلويات قولي عليه لو سمحت."
    ),
    "u_follow": "طب والتوصيل هياخد قد إيه؟",
    "u2_address": "العنوان تلاتة وعشرين شارع التحرير، الدقي، الدور الخامس.",
    "u3_yes": "أيوه تمام كده، اتفقنا.",
    "u7_correction": "لا استنى، مش اتنين، خليهم تلاتة بيتزا.",
    "u_ambig": "يعني ممكن، مش عارف، شوف انت.",
    "u_multi": "العنوان تلاتة وعشرين شارع التحرير الدقي، واسمي أحمد، ورقمي صفر واحد صفر واحد اتنين تلاتة أربعة خمسة.",
}
SESSIONS = [
    ["u_short", "u1_order", "u_follow", "u2_address", "u3_yes", "u1_order"],
    ["u_long", "u7_correction", "u_ambig", "u_multi", "u3_yes"],
]


def arg(n: str, d: str) -> str:
    return sys.argv[sys.argv.index(n) + 1] if n in sys.argv else d


BASE = arg("--base", "http://localhost:8000").rstrip("/")
COMP = arg("--composition", "comp_s2s_openai_v1")
REPEAT = int(arg("--repeat", "2"))
ACT = "act_order_intake@1.0.0"


def tts(name: str) -> bytes:
    d = pathlib.Path(os.environ.get("QEVION_TTS_CACHE", tempfile.gettempdir())) / "qevion_tts"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{name}.pcm"
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


def last_voiced_frame(pcm: bytes) -> int:
    """Index of the last 20 ms frame Silero scores ≥ 0.5 (same model/wrapper as the server turn plane)."""
    from qevion.adapters.turn.silero import SileroProbability, SileroTurnAdapter

    ad = SileroTurnAdapter()
    if ad._model is None:  # noqa: SLF001
        raise SystemExit("Silero model missing: bash scripts/fetch_models.sh")
    prob = SileroProbability(ad._model)  # noqa: SLF001
    last = 0
    for k, i in enumerate(range(0, len(pcm), 960)):
        if prob(pcm[i : i + 960]) >= 0.5:
            last = k
    return last


def http(method: str, path: str, body: dict[str, Any] | None = None) -> Any:
    r = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"content-type": "application/json"},
    )
    return json.loads(urllib.request.urlopen(r, timeout=15).read())  # noqa: S310


def now_ms() -> float:
    return time.time() * 1000


async def run_session(plan: list[str], clips: dict[str, bytes], lastv: dict[str, int]) -> dict[str, Any]:
    url = BASE.replace("http", "ws", 1) + f"/ws/sessions/{ACT}?channel=browser_voice&composition={COMP}"
    marks: list[tuple[float, str, str]] = []
    st: dict[str, Any] = {"sid": None, "rid": None, "first_bin": set(), "bytes": {}, "last_bin": 0.0}
    t_open = now_ms()
    silence = b"\x00\x00" * 480
    turns: list[dict[str, Any]] = []
    async with websockets.connect(url, max_size=None) as ws:
        marks.append((now_ms(), "client:ws_open", ""))

        async def reader() -> None:
            try:
                async for raw in ws:
                    t = now_ms()
                    if isinstance(raw, bytes):
                        rid = st["rid"] or ""
                        if rid not in st["first_bin"]:
                            st["first_bin"].add(rid)
                            marks.append((t, "client:first_audio_frame", rid))
                        st["bytes"][rid] = st["bytes"].get(rid, 0) + len(raw)
                        st["last_bin"] = t
                        continue
                    m = json.loads(raw)
                    ty = m["type"]
                    st["sid"] = st["sid"] or m.get("session_id")
                    if ty == "ping":
                        await ws.send(json.dumps({"type": "pong"}))
                    elif ty == "ready":
                        marks.append((t, "client:ready", ""))
                    elif ty == "audio_start":
                        st["rid"] = m.get("response_id")
                        await ws.send(json.dumps({"type": "playout_started", "response_id": st["rid"]}))
                    elif ty == "stop_playout":
                        await ws.send(json.dumps({"type": "playout_stopped", "response_id": m.get("response_id")}))
            except websockets.exceptions.ConnectionClosed:
                pass

        rd = asyncio.create_task(reader())
        await ws.send(json.dumps({"type": "hello"}))

        async def silence_for(sec: float) -> None:
            nxt = time.monotonic()
            for _ in range(int(sec / 0.02)):
                await ws.send(silence)
                nxt += 0.02
                await asyncio.sleep(max(0.0, nxt - time.monotonic()))

        await silence_for(1.5)
        for name in plan:
            pcm = clips[name]
            t_start = now_ms()
            t1 = None
            nxt = time.monotonic()
            for k, i in enumerate(range(0, len(pcm), 960)):
                await ws.send(pcm[i : i + 960])
                if k == lastv[name]:
                    t1 = now_ms()
                nxt += 0.02
                await asyncio.sleep(max(0.0, nxt - time.monotonic()))
            # keep the mic "open" with silence (like a real client) until the agent has spoken and the audio it
            # sent has had time to play out, then a short human pause
            first_seen = len(st["first_bin"])
            waited = 0.0
            while waited < 20.0:
                await silence_for(0.2)
                waited += 0.2
                if len(st["first_bin"]) > first_seen and now_ms() - st["last_bin"] > 1500:
                    rid = st["rid"] or ""
                    play_ms = st["bytes"].get(rid, 0) / 48.0  # 24 kHz pcm16 mono
                    first_t = next((m[0] for m in reversed(marks) if m[1] == "client:first_audio_frame"), now_ms())
                    remain = first_t + play_ms - now_ms()
                    if remain > 0:
                        await silence_for(min(remain / 1000, 15))
                    await ws.send(json.dumps({"type": "playout_stopped", "response_id": rid}))
                    break
            turns.append({"clip": name, "t_clip_start": t_start, "t1": t1, "t_clip_end": now_ms()})
            await silence_for(0.8)
        await ws.send(json.dumps({"type": "bye"}))
        try:
            await asyncio.wait_for(rd, 8)
        except Exception:  # noqa: BLE001
            pass
    await asyncio.sleep(1.0)
    sid = st["sid"]
    srv = http("GET", f"/api/sessions/{sid}/latency-trace")
    detail = http("GET", f"/api/sessions/{sid}")
    return {
        "session_id": sid,
        "t_ws_connect_start": t_open,
        "turns": turns,
        "client_marks": marks,
        "server_marks": srv["marks"],
        "error": detail.get("error"),
        "outcome": (detail.get("outcome") or {}).get("primary"),
    }


def first_after(marks: list[list[Any]], kind: str, t: float, until: float | None = None) -> float | None:
    for m in marks:
        if m[1] == kind and m[0] >= t and (until is None or m[0] < until):
            return float(m[0])
    return None


def reanalyse(path: str) -> None:
    """Recompute rows/summary from a saved raw run (analysis-only changes never need a new live run)."""
    d = json.loads(pathlib.Path(path).read_text())
    finish(path, d["sessions"], sum(1 for s in d["sessions"] if s.get("error")))


def analyse(sess: dict[str, Any]) -> list[dict[str, Any]]:
    allm = sorted([list(m) for m in sess["server_marks"]] + [list(m) for m in sess["client_marks"]], key=lambda m: m[0])
    out = []
    turns = sess["turns"]
    for i, tu in enumerate(turns):
        t1 = tu["t1"]
        until = turns[i + 1]["t_clip_start"] if i + 1 < len(turns) else None
        w = [m for m in allm if m[0] >= tu["t_clip_start"] and (until is None or m[0] < until)]
        g = lambda k, after=tu["t_clip_start"], w=w: first_after(w, k, after)  # noqa: E731
        eots = [m for m in w if m[1] == "core:end_of_turn"]
        # the accepted END_OF_TURN for the utterance = the first one at/after the last voiced frame; earlier ones
        # are premature commits inside the utterance (fragmentation, reported separately)
        final = [m for m in eots if t1 is not None and m[0] >= t1]
        premature = [m for m in eots if t1 is not None and m[0] < t1]
        t3 = final[0][0] if final else (eots[-1][0] if eots else None)
        t4 = g("sent:input_audio_buffer.commit", t3 or 0)
        t5 = g("recv:input_audio_buffer.committed", t4 or 0)
        t4b = g("sent:response.create", t4 or 0)
        t6 = g("recv:response.created", t4b or 0)
        t7 = g("recv:first_audio_delta", t4b or 0)
        t8 = g("core:first_audio_to_client", t7 or 0) if t7 else None
        t9 = g("client:first_audio_frame", t8 or 0) if t8 else None
        tools = [m for m in w if m[1] == "core:tool_start"]
        t12 = g("recv:response.function_call_arguments.done", t4b or 0)
        t13 = tools[0][0] if tools else None
        t14 = g("core:tool_done", t13) if t13 else None
        subs = [m[0] for m in w if m[1] == "core:tool_result_submit"]
        t15 = subs[-1] if subs else None
        t16 = g("recv:response.created", t15) if t15 else None
        t17 = g("recv:first_audio_delta", t15) if t15 else None
        dones = [m[0] for m in w if m[1] == "recv:response.done"]
        t18 = dones[-1] if dones else None
        decs = []
        starts = [m for m in w if m[1] == "decision:start"]
        for s0 in starts:
            e = next((m for m in w if m[1] == "decision:end" and m[0] >= s0[0]), None)
            if e:
                decs.append({"kind": s0[2], "ms": round(e[0] - s0[0], 1), "source": e[2].split(":")[-1]})
        n_resp = sum(1 for m in w if m[1] == "recv:response.created")

        def d(a: float | None, b: float | None) -> float | None:
            return None if a is None or b is None else round(b - a, 1)

        out.append(
            {
                "session": sess["session_id"],
                "clip": tu["clip"],
                "tool_calls": len(tools),
                "provider_responses": n_resp,
                "eot_commits": len(eots),
                "premature_eot": len(premature),
                "premature_eot_at_ms": [round(m[0] - tu["t_clip_start"]) for m in premature],
                "cancelled_responses": sum(1 for m in w if m[1] == "sent:response.cancel"),
                "T1_T3_endpoint": d(t1, t3),
                "T3_T4_commit": d(t3, t4),
                "T4_T5_provider_ack": d(t4, t5),
                "T4_T6_response_created": d(t4, t6),
                "T6_T7_first_audio": d(t6, t7),
                "T4_T7_provider_ttfa": d(t4, t7),
                "T7_T8_qevion_forward": d(t7, t8),
                "T8_T9_ws_delivery": d(t8, t9),
                "T1_T9_user_to_first_audio_client": d(t1, t9),
                "T12_T13_tool_dispatch": d(t12, t13),
                "T13_T14_tool_exec": d(t13, t14),
                "T15_T16_post_tool_created": d(t15, t16),
                "T15_T17_post_tool_ttfa": d(t15, t17),
                "T3_T18_turn_total": d(t3, t18),
                "first_audio_after_tool": bool(t15 and t7 and t7 >= t15),
                "decisions": decs,
            }
        )
    return out


def stats(xs: list[float]) -> dict[str, Any]:
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return {"n": 0}

    def pct(p: float) -> float:
        return xs[min(len(xs) - 1, max(0, round(p / 100 * (len(xs) - 1))))]

    q1, q3 = pct(25), pct(75)
    outl = [x for x in xs if x > q3 + 1.5 * (q3 - q1)]
    return {
        "n": len(xs),
        "min": xs[0],
        "p50": pct(50),
        "p95": pct(95),
        "max": xs[-1],
        "mean": round(statistics.mean(xs), 1),
        "outliers": len(outl),
    }


async def main() -> int:
    out = sys.argv[1]
    names = sorted({n for p in SESSIONS for n in p})
    clips = {n: tts(n) for n in names}
    lastv = {n: last_voiced_frame(clips[n]) for n in names}
    http(
        "POST",
        "/api/admin/test-key",
        {"provider": "openai", "value": os.environ["OPENAI_API_KEY"], "ttl_seconds": 3600},
    )
    sessions, failed = [], 0
    for _r in range(REPEAT):
        for plan in SESSIONS:
            try:
                s = await run_session(plan, clips, lastv)
                sessions.append(s)
                if s.get("error"):
                    failed += 1
            except Exception as e:  # noqa: BLE001
                failed += 1
                sessions.append({"error": f"{type(e).__name__}: {e}"})
            pathlib.Path(out).write_text(json.dumps({"sessions": sessions}, ensure_ascii=False))
    finish(out, sessions, failed)
    return 0


def finish(out: str, sessions: list[dict[str, Any]], failed: int) -> None:
    rows = [r for s in sessions if "turns" in s for r in analyse(s)]
    keys = [k for k in rows[0] if k.startswith("T")] if rows else []
    buckets = {
        "all": rows,
        "no_tool": [r for r in rows if r["tool_calls"] == 0],
        "one_tool": [r for r in rows if r["tool_calls"] == 1],
        "multi_tool": [r for r in rows if r["tool_calls"] >= 2],
    }
    summary = {b: {k: stats([r[k] for r in rs if r[k] is not None]) for k in keys} for b, rs in buckets.items()}
    summary["counts"] = {b: len(rs) for b, rs in buckets.items()}
    summary["fragmented_turns"] = sum(1 for r in rows if r["premature_eot"])
    summary["premature_eot_total"] = sum(r["premature_eot"] for r in rows)
    summary["failed_sessions"] = failed
    dec_all = [d for r in rows for d in r["decisions"]]
    summary["decisions"] = {
        "count": len(dec_all),
        "by_source": {s: stats([d["ms"] for d in dec_all if d["source"] == s]) for s in {d["source"] for d in dec_all}},
    }
    pathlib.Path(out).write_text(
        json.dumps({"summary": summary, "rows": rows, "sessions": sessions}, ensure_ascii=False, indent=1)
    )
    print(json.dumps({"counts": summary["counts"], "failed": failed}, ensure_ascii=False))
    for k in keys:
        s = summary["all"][k]
        if s.get("n"):
            print(f"{k:36} n={s['n']:>2} min={s['min']:>7} p50={s['p50']:>7} p95={s['p95']:>7} max={s['max']:>7}")
    print("fragmented_turns", summary["fragmented_turns"], "premature_eot_total", summary["premature_eot_total"])


if __name__ == "__main__":
    if "--reanalyse" in sys.argv:
        reanalyse(sys.argv[1])
    else:
        raise SystemExit(asyncio.run(main()))
