"""Live smoke against TypeSafe AI (Jev) — real-provider evidence for the decision port (QV-ACC-022, decision role).

Key comes ONLY from env `TYPESAFE_API_KEY` (never from files, never printed; evidence stores a fingerprint).
(1) models list, (2) Egyptian-Arabic / Arabizi / English confirmation + intent utterances through the raw
`TypeSafeDecisionAdapter`, (3) the confirmations again through `LayeredDecisionAdapter` (rules first) to
measure how often the fallback is consulted and whether it ever contradicts rules.

Usage: TYPESAFE_API_KEY=... .venv/bin/python scripts/typesafe_live_smoke.py [out.json]
Exit 0 when every accepted answer matches the label; 1 on mismatches; 2 when no key (A5).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import statistics
import sys
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from qevion.adapters.decision.rules import RulesDecisionAdapter
from qevion.adapters.decision.typesafe import DEFAULT_BASE_URL, LayeredDecisionAdapter, TypeSafeDecisionAdapter
from qevion.contracts.provider import DecisionKind, DecisionRequest

CONFIRMATIONS: list[tuple[str, bool | None]] = [
    ("أيوه تمام ماشي", True),
    ("اه يا باشا اتفقنا", True),
    ("تمام كده صح", True),
    ("لأ استنى خلّيهم تلاتة", False),
    ("لا مش عايز", False),
    ("خلاص بلاش", False),
    ("mashy tamam", True),
    ("la2 msh 3ayez", False),
    ("yes please go ahead", True),
    ("no, cancel that", False),
    ("هو ده بكام؟", None),
    ("ممكن تعيد تاني؟", None),
]
INTENTS: list[tuple[str, str]] = [
    ("الأكل وصل بارد ومتأخر", "complaint"),
    ("عايز أطلب اتنين برجر", "order"),
    ("ممكن أكلم حد من الإدارة؟", "human_request"),
    ("السعر غالي هفكر", "objection"),
    ("شيلني من القايمة", "opt_out"),
    ("3ayez 2 burger w pepsi", "order"),
]
INTENT_PATTERNS = {
    "order": ["wants to buy / order items"],
    "complaint": ["problem with a past order or service"],
    "human_request": ["asks to speak with a person / manager"],
    "objection": ["pushes back on price or hesitates"],
    "opt_out": ["asks not to be contacted / remove from list"],
}


def _models(key: str) -> list[str]:
    req = urllib.request.Request(f"{DEFAULT_BASE_URL}/v1/models", headers={"Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310 — https constant
        data = json.loads(r.read().decode())
    return [str(m["name"]) for m in data.get("models", [])]


async def _case(ad: TypeSafeDecisionAdapter, req: DecisionRequest, text: str, expected: Any) -> dict[str, Any]:
    t0 = time.monotonic()
    r = await ad.decide(req)
    ms = int((time.monotonic() - t0) * 1000)
    got: Any = None if r.is_unknown else r.value
    return {
        "kind": req.kind.value,
        "text": text,
        "expected": expected,
        "got": got,
        "ok": got == expected,
        "source": r.source.value,
        "confidence": r.confidence,
        "reason": r.reason,
        "latency_ms": ms,
        "model": ad.last_model,
    }


async def main(argv: list[str]) -> int:
    key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    out_path = Path(argv[0]) if argv else Path("evidence/live/typesafe_smoke.json")
    if not key:
        print("TYPESAFE_API_KEY not set — skipping live smoke (A5).")
        return 2
    ts = TypeSafeDecisionAdapter(key)
    layered = LayeredDecisionAdapter(RulesDecisionAdapter(), TypeSafeDecisionAdapter(key))
    rows: list[dict[str, Any]] = []
    for text, exp in CONFIRMATIONS:
        rows.append(
            await _case(ts, DecisionRequest(kind=DecisionKind.INTERPRET_CONFIRMATION, inputs={"text": text}), text, exp)
        )
    for text, exp_i in INTENTS:
        req = DecisionRequest(
            kind=DecisionKind.CLASSIFY_INTENT,
            inputs={"text": text, "patterns": INTENT_PATTERNS},
            options=list(INTENT_PATTERNS),
        )
        rows.append(await _case(ts, req, text, exp_i))
    layered_rows: list[dict[str, Any]] = []
    for text, exp in CONFIRMATIONS:
        r = await layered.decide(DecisionRequest(kind=DecisionKind.INTERPRET_CONFIRMATION, inputs={"text": text}))
        layered_rows.append(
            {
                "text": text,
                "expected": exp,
                "got": None if r.is_unknown else bool(r.value),
                "source": r.source.value,
                "confidence": r.confidence,
            }
        )
    lat = sorted(x["latency_ms"] for x in rows)
    mismatches = sum(1 for x in rows if not x["ok"])
    report: dict[str, Any] = {
        "provider": "typesafe",
        "base_url": DEFAULT_BASE_URL,
        "key_fingerprint": hashlib.sha256(key.encode()).hexdigest()[:12],
        "ran_at": datetime.now(UTC).isoformat(),
        "models": _models(key),
        "cases": rows,
        "layered": {
            "rows": layered_rows,
            "fallback_hits": layered.fallback_hits,
            "rules_decided": sum(1 for x in layered_rows if x["source"] == "RULE"),
            "unknown_after_fallback": sum(1 for x in layered_rows if x["source"] == "UNKNOWN"),
            "contradictions": sum(1 for x in layered_rows if x["got"] is not None and x["got"] != x["expected"]),
        },
        "summary": {
            "cases": len(rows),
            "matches": len(rows) - mismatches,
            "mismatches": mismatches,
            "provider_calls": ts.calls + layered.fallback.calls,
            "latency_ms": {"p50": int(statistics.median(lat)), "p95": lat[max(0, int(len(lat) * 0.95) - 1)], "max": lat[-1]},
            "last_usage": ts.last_usage,
        },
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    brief = {"out": str(out_path), **report["summary"], "layered": {k: v for k, v in report["layered"].items() if k != "rows"}}
    print(json.dumps(brief, ensure_ascii=False, indent=2))
    return 0 if mismatches == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
