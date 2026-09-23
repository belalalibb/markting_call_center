"""Latency + transcription table from voice_trace_live.py reports (OPS 5.5 P2 corpus harness).

usage: latency_table.py OUT.md TRACE.json [TRACE.json ...]

Per trace it derives, from Core events only (server clock, ms):
  * eot_to_first_audio   user.speech_committed → next assistant.response_started with audio (turn latency)
  * barge_in t1→t2 / t1→t3 / t1→t4 from `latency.sample{segment: interruption}` (+ forced flag)
  * split_turns          audio commits per spoken clip (>1 means VAD committed mid-utterance)
  * CER per user transcript vs the synthetic phrase closest in position (character error rate, whitespace/
    punctuation-insensitive) — synthetic TTS speech, NOT a human-speech fidelity claim.
Writes a markdown table and a JSON sidecar (OUT.json) with the raw numbers.
"""

from __future__ import annotations

import json
import pathlib
import re
import statistics
import sys
from typing import Any

_PUNCT = re.compile(r"[\s\.,،؟?!:;\-\"'«»()]+")


def _norm(s: str) -> str:
    s = _PUNCT.sub("", s)
    return s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ة", "ه").replace("ى", "ي")


def cer(ref: str, hyp: str) -> float:
    r, h = _norm(ref), _norm(hyp)
    if not r:
        return 0.0 if not h else 1.0
    prev = list(range(len(h) + 1))
    for i, rc in enumerate(r, 1):
        cur = [i] + [0] * len(h)
        for j, hc in enumerate(h, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (rc != hc))
        prev = cur
    return prev[-1] / len(r)


def pct(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    xs = sorted(xs)
    k = min(len(xs) - 1, max(0, round(p / 100 * (len(xs) - 1))))
    return xs[k]


def analyse(path: str) -> dict[str, Any]:
    r = json.loads(pathlib.Path(path).read_text())
    ev = r["core_events"]
    audio_rids = {e[3].get("response_id") for e in ev if e[1] == "assistant.response_ended" and e[3].get("audio_ms")}
    commits = [e[0] for e in ev if e[1] == "user.speech_committed"]
    starts = [(e[0], e[3].get("response_id")) for e in ev if e[1] == "assistant.response_started"]
    ttfa: list[float] = []
    for c in commits:
        nxt = next((t for t, rid in starts if t >= c and rid in audio_rids), None)
        if nxt is not None:
            ttfa.append(nxt - c)
    inter = [e[3] for e in ev if e[1] == "latency.sample" and e[3].get("segment") == "interruption"]
    clips = [x for x in r.get("client_log", []) if x[1] == "cli:utterance_start"]
    phrases: dict[str, str] = r.get("phrases") or {}
    cers: list[dict[str, Any]] = []
    for _t, text in r.get("user_transcripts") or []:
        if not text or not phrases:
            continue
        best = min(phrases.items(), key=lambda kv: cer(kv[1], text))
        cers.append({"clip": best[0], "cer": round(cer(best[1], text), 3), "hyp": text})
    return {
        "trace": path,
        "mode": r.get("mode"),
        "facts": r.get("session_facts") or {},
        "health_passed": bool(r.get("health", {}).get("passed")),
        "clips": len(clips),
        "audio_commits": len(commits),
        "eot_to_first_audio_ms": ttfa,
        "barge_in": [
            {
                "t1_t2": i["t2"] - i["t1"],
                "t1_t3": i["t3"] - i["t1"],
                "t1_t4": i["t4"] - i["t1"],
                "forced": i.get("forced"),
            }
            for i in inter
        ],
        "cer": cers,
    }


def main() -> int:
    out = pathlib.Path(sys.argv[1])
    rows = [analyse(p) for p in sys.argv[2:]]
    ttfa = [x for r in rows for x in r["eot_to_first_audio_ms"]]
    t13 = [b["t1_t3"] for r in rows for b in r["barge_in"]]
    t12 = [b["t1_t2"] for r in rows for b in r["barge_in"]]
    forced = sum(1 for r in rows for b in r["barge_in"] if b["forced"])
    cers = [c["cer"] for r in rows for c in r["cer"]]
    summary = {
        "traces": len(rows),
        "turns_measured": len(ttfa),
        "eot_to_first_audio_ms": {"p50": pct(ttfa, 50), "p95": pct(ttfa, 95), "max": max(ttfa) if ttfa else None},
        "barge_ins": len(t13),
        "barge_in_t1_t2_ms": {"p50": pct(t12, 50), "p95": pct(t12, 95)},
        "barge_in_t1_t3_ms": {"p50": pct(t13, 50), "p95": pct(t13, 95), "max": max(t13) if t13 else None},
        "forced_stops": forced,
        "cer_mean": round(statistics.mean(cers), 3) if cers else None,
        "split_turns": sum(max(0, r["audio_commits"] - r["clips"]) for r in rows),
    }
    lines = [
        "# Live latency / transcription table (synthetic ar-EG clips, OpenAI Realtime)",
        "",
        "Server-clock Core events. Synthetic TTS speech → lifecycle/latency evidence, not human-speech fidelity.",
        "",
        "| trace | detector | transcription | health | clips | commits | EOT→first audio ms | barge-in t1→t3 ms"
        " (forced) | CER |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        bi = ", ".join(f"{b['t1_t3']}{'F' if b['forced'] else ''}" for b in r["barge_in"]) or "-"
        c = ", ".join(f"{x['clip']}:{x['cer']}" for x in r["cer"]) or "-"
        lines.append(
            f"| {pathlib.Path(r['trace']).name} | {r['facts'].get('turn_detector')} | "
            f"{r['facts'].get('transcription_model')} | {'PASS' if r['health_passed'] else 'FAIL'} | {r['clips']} | "
            f"{r['audio_commits']} | {', '.join(str(x) for x in r['eot_to_first_audio_ms']) or '-'} | {bi} | {c} |"
        )
    lines += ["", "## Summary", "", "```json", json.dumps(summary, indent=1), "```", ""]
    out.write_text("\n".join(lines))
    out.with_suffix(".json").write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1))
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
