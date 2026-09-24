"""Mechanical verdict for one controlled A/B window (docs/audit/LATENCY_AB_CRITERIA_2026-09-24.md, v2).

usage: latency_ab_eval.py evidence/latency/ab/<window>
Reads baseline.json, A.json, B.json, AB.json (+ preflight_*.json) and writes verdict.json.

* A vs baseline, B vs baseline (independent); A+B only if A and B both KEEP and A+B adds no regression.
* INVALID (not REVERT, not KEEP) when a mode is missing or the provider refused (no-credit rule): no performance
  conclusion is drawn from a refused run. Thresholds are fixed here and never change with results.
"""

from __future__ import annotations

import json
import pathlib
import re
import statistics
import sys
from collections import Counter
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from latency_corpus import stats  # noqa: E402

# Content-free acknowledgement check (A): digits, number words used by the corpus domain, prices/currency,
# availability, and success/record claims (ar-EG + en). ≤ 8 words.
_ACK_BAD_TOKENS = {
    # quantities / numbers (ar-EG, MSA, en)
    "واحد",
    "واحدة",
    "اتنين",
    "إتنين",
    "اثنين",
    "تلاتة",
    "ثلاثة",
    "تلات",
    "اربعة",
    "أربعة",
    "خمسة",
    "ستة",
    "سبعة",
    "تمانية",
    "ثمانية",
    "تسعة",
    "عشرة",
    "مية",
    "ميه",
    "ألف",
    "الف",
    "صفر",
    "ست",
    "خمس",
    "سبع",
    "تسع",
    "عشر",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    # prices / availability
    "جنيه",
    "سعر",
    "السعر",
    "متاح",
    "متوفر",
    "موجود",
    "price",
    "pound",
    "pounds",
    "available",
    "availability",
    # success / record claims
    "سجلت",
    "سجّلت",
    "اتسجل",
    "اتسجلت",
    "تم",
    "أكدت",
    "اتأكد",
    "حجزت",
    "اتحجز",
    "نجح",
    "خلاص",
    "recorded",
    "confirmed",
    "booked",
    "done",
    "success",
    "saved",
}
_DIGIT = re.compile(r"[0-9٠-٩]")
_TOKEN = re.compile(r"[\w\u0600-\u06FF]+", re.UNICODE)


class _AckFilter:
    """Whole-token match (so 'تمام' is not 'تم', 'ستني' is not 'ست'); digits anywhere; leading Arabic 'و' stripped."""

    def search(self, text: str) -> bool:
        if _DIGIT.search(text):
            return True
        for tok in _TOKEN.findall(text.lower()):
            if tok in _ACK_BAD_TOKENS or (tok.startswith("و") and tok[1:] in _ACK_BAD_TOKENS):
                return True
        return False


_ACK_BAD = _AckFilter()

T1T9 = "T1_T9_user_to_first_audio_client"
T1T9A = "T1_T9a_user_to_answer_audio_client"


def load(d: pathlib.Path, mode: str) -> dict[str, Any] | None:
    p = d / f"{mode}.json"
    if not p.exists():
        return None
    x = json.loads(p.read_text())
    return x if "summary" in x else None


def refused(d: pathlib.Path, mode: str) -> bool:
    p = d / f"preflight_{mode}.json"
    return p.exists() and not json.loads(p.read_text()).get("valid", False)


def split(r: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return [x for x in r["rows"] if x["tool_calls"] == 0], [x for x in r["rows"] if x["tool_calls"] > 0]


def st(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    return stats([x[key] for x in rows if x.get(key) is not None])


def improvement(ref: dict[str, Any], new: dict[str, Any]) -> float | None:
    a, b = ref.get("p50"), new.get("p50")
    return None if not a or b is None else round((a - b) / a * 100, 1)


def health(r: dict[str, Any]) -> dict[str, Any]:
    sess = r["sessions"]
    ev = [e for s in sess for e in s.get("core_events", [])]
    return {
        "session_errors": [s.get("error") for s in sess if s.get("error")],
        "provider_errors": sum(1 for s in sess for m in s.get("server_marks", []) if m[1] == "recv:error")
        + sum(1 for e in ev if e["type"] == "provider.error"),
        "illegal_transitions": sum(
            1
            for e in ev
            if e["type"] == "failure.classified" and e["payload"].get("class") == "illegal_dialog_transition"
        ),
        "clips_not_heard": sum(1 for x in r["rows"] if x["T1_T3_endpoint"] is None),
        "tool_errors": sum(
            1 for e in ev if e["type"] in ("tool.execution_failed", "tool.execution_unknown", "tool.rejected")
        ),
        "unresolved_tool_results": sum(
            1 for s in sess for m in s.get("server_marks", []) if m[1] == "recv:error" and "tool" in str(m[2])
        ),
        "turns": len(r["rows"]),
    }


def health_ok(h: dict[str, Any]) -> bool:
    return (
        not h["session_errors"]
        and h["provider_errors"] == 0
        and h["illegal_transitions"] == 0
        and h["clips_not_heard"] == 0
    )


def writes(r: dict[str, Any]) -> dict[str, Any]:
    """Semantic business state per session position: executed record_field counts per field + final field set."""
    out = []
    for s in r["sessions"]:
        ev = s.get("core_events", [])
        rec = Counter(e["payload"].get("name") for e in ev if e["type"] in ("field.recorded", "field.corrected"))
        out.append(
            {
                "plan": [t["clip"] for t in s.get("turns", [])],
                "record_writes": dict(rec),
                "final_fields": sorted(rec),
                "outcome": s.get("outcome"),
            }
        )
    return {"sessions": out}


def compare_writes(ref: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Exact semantic preservation for equivalent turns (same session plan position). Ordering is ignored;
    the resulting field state and per-field write counts must match. Any dropped or duplicate write fails."""
    issues = []
    pairs = list(zip(ref["sessions"], new["sessions"], strict=False))
    if len(ref["sessions"]) != len(new["sessions"]):
        issues.append(f"session count {len(ref['sessions'])} vs {len(new['sessions'])}")
    for i, (a, b) in enumerate(pairs):
        if a["plan"] != b["plan"]:
            issues.append(f"s{i}: plan differs")
            continue
        if a["final_fields"] != b["final_fields"]:
            issues.append(f"s{i}: final fields {a['final_fields']} vs {b['final_fields']}")
        for f in set(a["record_writes"]) | set(b["record_writes"]):
            ca, cb = a["record_writes"].get(f, 0), b["record_writes"].get(f, 0)
            if cb < ca:
                issues.append(f"s{i}: dropped write {f} ({ca}→{cb})")
            elif cb > ca:
                issues.append(f"s{i}: duplicate write {f} ({ca}→{cb})")
    return {"exact": not issues, "issues": issues}


def ack_check(r: dict[str, Any]) -> dict[str, Any]:
    texts, bad = [], []
    for x in r["rows"]:
        for t in x.get("ack_texts") or []:
            texts.append(t)
            if t is None or _ACK_BAD.search(t) or not (1 <= len(t.split()) <= 8):
                bad.append(t)
    return {"acks": texts, "violations": bad}


def no_tool_ok(ref: dict[str, Any], new: dict[str, Any]) -> bool:
    a, b = ref.get("p50"), new.get("p50")
    return a is not None and b is not None and b - a <= max(100.0, 0.10 * a)


def main() -> int:
    d = pathlib.Path(sys.argv[1])
    modes = {m: load(d, m) for m in ("baseline", "A", "B", "AB")}
    out: dict[str, Any] = {"window": d.name, "invalid": {}}
    for m, r in modes.items():
        if r is None:
            out["invalid"][m] = "refused by provider (no-credit rule)" if refused(d, m) else "missing"
    base = modes["baseline"]
    if base is None:
        out["A"] = out["B"] = out["AB"] = "INVALID"
        (d / "verdict.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 0
    bn, bt = split(base)
    bw = writes(base)
    out["baseline"] = {
        "no_tool_T1T9": st(bn, T1T9),
        "tool_T1T9": st(bt, T1T9),
        "tool_T1T9a": st(bt, T1T9A),
        "median_tool_cycles": statistics.median([x["tool_cycles"] for x in bt]) if bt else None,
        "health": health(base),
    }

    def judge_a(r: dict[str, Any]) -> dict[str, Any]:
        n, t = split(r)
        s_t, s_bt = st(t, T1T9), st(bt, T1T9)
        ack = ack_check(r)
        h = health(r)
        crit = {
            "tool_T1T9_p50_>=30%": (improvement(s_bt, s_t) or -999) >= 30,
            "tool_T1T9_p95_not_worse": s_t.get("p95", 1e9) <= s_bt.get("p95", 0),
            "no_tool_not_regressed": no_tool_ok(st(bn, T1T9), st(n, T1T9)),
            "ack_content_free": not ack["violations"],
            "health": health_ok(h),
        }
        return {
            "tool_T1T9": s_t,
            "delta_p50_pct": improvement(s_bt, s_t),
            "no_tool_T1T9": st(n, T1T9),
            "ack": ack,
            "health": h,
            "criteria": crit,
            "verdict": "KEEP" if all(crit.values()) else "REVERT",
        }

    def judge_b(
        r: dict[str, Any],
        ref: dict[str, Any],
        ref_tool: list[dict[str, Any]],
        ref_nt: list[dict[str, Any]],
        ref_w: dict[str, Any],
    ) -> dict[str, Any]:
        n, t = split(r)
        s_t, s_rt = st(t, T1T9A), st(ref_tool, T1T9A)
        cyc_ref = statistics.median([x["tool_cycles"] for x in ref_tool]) if ref_tool else None
        cyc = statistics.median([x["tool_cycles"] for x in t]) if t else None
        w = compare_writes(ref_w, writes(r))
        h = health(r)
        crit = {
            "answer_T1T9a_p50_>=15%": (improvement(s_rt, s_t) or -999) >= 15,
            "answer_p95_not_worse": s_t.get("p95", 1e9) <= s_rt.get("p95", 0),
            "median_tool_cycles_decrease": cyc is not None and cyc_ref is not None and cyc < cyc_ref,
            "exact_semantic_writes": w["exact"],
            "zero_tool_errors": h["tool_errors"] == 0,
            "no_unresolved_results": h["unresolved_tool_results"] == 0,
            "no_tool_not_regressed": no_tool_ok(st(ref_nt, T1T9), st(n, T1T9)),
            "health": health_ok(h),
            # dependency/barrier/missing-result safety is proven offline (tests/test_latency_b_dependency_safety.py)
            # and must be green on the same build; the runner refuses to start otherwise.
        }
        return {
            "answer_T1T9a": s_t,
            "delta_p50_pct": improvement(s_rt, s_t),
            "tool_cycles": {"ref": cyc_ref, "new": cyc},
            "writes": w,
            "health": h,
            "criteria": crit,
            "verdict": "KEEP" if all(crit.values()) else "REVERT",
        }

    out["A"] = judge_a(modes["A"]) if modes["A"] else "INVALID"
    out["B"] = judge_b(modes["B"], base, bt, bn, bw) if modes["B"] else "INVALID"
    ab = modes["AB"]
    if ab is None:
        out["AB"] = "INVALID"
    else:
        a_ok = isinstance(out["A"], dict) and out["A"]["verdict"] == "KEEP"
        b_ok = isinstance(out["B"], dict) and out["B"]["verdict"] == "KEEP"
        ja = judge_a(ab)
        jb = judge_b(ab, base, bt, bn, bw)
        crit = {
            "A_independently_KEEP": a_ok,
            "B_independently_KEEP": b_ok,
            "AB_ack_safe": ja["criteria"]["ack_content_free"],
            "AB_writes_exact": jb["criteria"]["exact_semantic_writes"],
            "AB_health": ja["criteria"]["health"],
            "AB_no_tool_not_regressed": ja["criteria"]["no_tool_not_regressed"],
        }
        if modes["A"]:
            _, at = split(modes["A"])
            crit["AB_answer_not_worse_than_A"] = st(split(ab)[1], T1T9A).get("p50", 1e9) <= st(at, T1T9A).get("p50", 0)
        out["AB"] = {
            "vs_baseline_A": ja,
            "vs_baseline_B": jb,
            "criteria": crit,
            "verdict": "KEEP" if all(crit.values()) else "REVERT",
        }
    for k in ("A", "B", "AB"):
        v = out[k] if isinstance(out[k], str) else out[k]["verdict"]
        out.setdefault("final", {})[k] = f"{v} {k.replace('AB', 'A+B')}" if v != "INVALID" else f"INVALID {k}"
    (d / "verdict.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(json.dumps(out["final"], ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
