"""Apply the pre-registered criteria (docs/audit/LATENCY_AB_CRITERIA_2026-09-24.md) to the A/B runs. Mechanical:
no judgement calls. Writes evidence/latency/ab_verdict.json and prints the verdict per option.

usage: latency_ab_eval.py  (reads evidence/latency/ab_baseline.json, ab_A.json, ab_AB.json)
"""

from __future__ import annotations

import json
import pathlib
import re
import statistics
import sys
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from latency_corpus import stats  # noqa: E402

D = pathlib.Path("evidence/latency")
# Number words that appear in the corpus clips / answers (quantities, address, phone) + generic digits.
_NUM = re.compile(
    r"[0-9٠-٩]|واحد|اتنين|إتنين|تلات|ثلاث|اربع|أربع|خمس|ست|سبع|تمان|ثمان|تسع|عشر|مية|ميه|ألف|الف|صفر"
    r"|جنيه|pound|\bone\b|\btwo\b|\bthree\b"
)


def load(name: str) -> dict[str, Any] | None:
    p = D / f"{name}.json"
    if not p.exists():
        return None
    d = json.loads(p.read_text())
    return d if "summary" in d else None


def med(xs: list[float]) -> float | None:
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def split(d: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows = d["rows"]
    return [r for r in rows if r["tool_calls"] == 0], [r for r in rows if r["tool_calls"] > 0]


def health(d: dict[str, Any]) -> dict[str, Any]:
    errs = [s.get("error") for s in d["sessions"] if s.get("error")]
    perr = sum(1 for s in d["sessions"] for m in s.get("server_marks", []) if m[1] == "recv:error")
    unheard = sum(1 for r in d["rows"] if r["T1_T3_endpoint"] is None)
    return {
        "session_errors": errs,
        "provider_error_events": perr,
        "turns_without_eot": unheard,
        "turns": len(d["rows"]),
    }


def recorded_fields(d: dict[str, Any]) -> int:
    return sum(
        1
        for s in d["sessions"]
        for m in s.get("server_marks", [])
        if m[1] == "core:tool_done" and "record_field" in m[2]
    )


def ack_violations(d: dict[str, Any]) -> list[str]:
    bad = []
    for r in d["rows"]:
        for t in r.get("ack_texts") or []:
            if t is None:
                bad.append("<no transcript available>")
            elif _NUM.search(t) or len(t.split()) > 8:
                bad.append(t)
    return bad


def pct(a: float | None, b: float | None) -> float | None:
    return None if a is None or b is None or a == 0 else round((a - b) / a * 100, 1)


def main() -> int:
    base, a, ab = load("ab_baseline"), load("ab_A"), load("ab_AB")
    out: dict[str, Any] = {}
    if base and a:
        bn, bt = split(base)
        an, at = split(a)
        s_bt, s_at = (
            stats([r["T1_T9_user_to_first_audio_client"] for r in bt]),
            stats([r["T1_T9_user_to_first_audio_client"] for r in at]),
        )
        s_bn, s_an = (
            stats([r["T1_T9_user_to_first_audio_client"] for r in bn]),
            stats([r["T1_T9_user_to_first_audio_client"] for r in an]),
        )
        viol = ack_violations(a)
        acks = sum(1 for r in at if r.get("ack_spoken"))
        h = health(a)
        c1 = (pct(s_bt.get("p50"), s_at.get("p50")) or -999) >= 30 and s_at.get("p95", 1e9) <= s_bt.get("p95", 0)
        c2 = s_an.get("p50", 1e9) - s_bn.get("p50", 0) <= max(100.0, 0.10 * s_bn.get("p50", 0))
        c3 = not viol
        c4 = not h["session_errors"] and h["provider_error_events"] == 0 and h["turns_without_eot"] == 0
        out["A"] = {
            "tool_T1_T9": {"baseline": s_bt, "A": s_at, "p50_improvement_pct": pct(s_bt.get("p50"), s_at.get("p50"))},
            "no_tool_T1_T9": {"baseline": s_bn, "A": s_an},
            "tool_turns_with_spoken_ack": f"{acks}/{len(at)}",
            "ack_texts": [t for r in at for t in (r.get("ack_texts") or [])],
            "ack_violations": viol,
            "health": h,
            "criteria": {
                "C1_tool_p50>=30%_and_p95_not_worse": c1,
                "C2_no_tool_not_regressed": c2,
                "C3_ack_content_free": c3,
                "C4_health": c4,
            },
        }
        out["A"]["verdict"] = "KEEP" if all(out["A"]["criteria"].values()) else "REVERT"
    if a and ab:
        an, at = split(a)
        bn2, bt2 = split(ab)
        s_at, s_bt2 = (
            stats([r["T1_T9a_user_to_answer_audio_client"] for r in at]),
            stats([r["T1_T9a_user_to_answer_audio_client"] for r in bt2]),
        )
        s_an, s_bn2 = (
            stats([r["T1_T9_user_to_first_audio_client"] for r in an]),
            stats([r["T1_T9_user_to_first_audio_client"] for r in bn2]),
        )
        cyc_a, cyc_b = med([r["tool_cycles"] for r in at]), med([r["tool_cycles"] for r in bt2])
        rec_a, rec_b = recorded_fields(a), recorded_fields(ab)
        tool_err = sum(1 for s in ab["sessions"] for m in s.get("server_marks", []) if m[1] == "recv:error")
        h = health(ab)
        c1 = (pct(s_at.get("p50"), s_bt2.get("p50")) or -999) >= 15 and s_bt2.get("p95", 1e9) <= s_at.get("p95", 0)
        c2 = cyc_b is not None and cyc_a is not None and cyc_b < cyc_a
        c3 = rec_b >= 0.8 * rec_a and tool_err == 0
        c4 = (not h["session_errors"] and h["turns_without_eot"] == 0) and (
            s_bn2.get("p50", 1e9) - s_an.get("p50", 0) <= max(100.0, 0.10 * s_an.get("p50", 0))
        )
        out["B"] = {
            "tool_T1_T9a_answer": {
                "A": s_at,
                "A+B": s_bt2,
                "p50_improvement_pct": pct(s_at.get("p50"), s_bt2.get("p50")),
            },
            "no_tool_T1_T9": {"A": s_an, "A+B": s_bn2},
            "median_tool_cycles": {"A": cyc_a, "A+B": cyc_b},
            "record_field_executions": {"A": rec_a, "A+B": rec_b},
            "provider_errors": tool_err,
            "health": h,
            "criteria": {
                "C1_answer_p50>=15%_and_p95_not_worse": c1,
                "C2_fewer_cycles": c2,
                "C3_no_dropped_writes": c3,
                "C4_health_and_no_tool": c4,
            },
        }
        out["B"]["verdict"] = "KEEP" if all(out["B"]["criteria"].values()) else "REVERT"
    (D / "ab_verdict.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(json.dumps(out, ensure_ascii=False, indent=1)[:6000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
