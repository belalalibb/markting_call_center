"""A/B evaluator gates: one dropped or duplicate business write fails B (order irrelevant); the acknowledgement
filter rejects numbers/prices/availability/success claims but not neutral words that merely contain them."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from latency_ab_eval import _ACK_BAD, compare_writes  # noqa: E402


def _w(*sessions: dict[str, int]) -> dict[str, object]:
    return {"sessions": [{"plan": ["u"], "record_writes": s, "final_fields": sorted(s)} for s in sessions]}


def test_identical_state_different_order_is_exact() -> None:
    assert compare_writes(_w({"items": 1, "address": 1}), _w({"address": 1, "items": 1}))["exact"]


def test_single_dropped_write_fails() -> None:
    r = compare_writes(_w({"items": 1, "address": 1}), _w({"items": 1}))
    assert not r["exact"] and any("dropped write address" in i for i in r["issues"])


def test_duplicate_write_fails() -> None:
    r = compare_writes(_w({"items": 1}), _w({"items": 2}))
    assert not r["exact"] and any("duplicate write items" in i for i in r["issues"])


def test_ack_filter_rejects_claims_and_numbers() -> None:
    for bad in (
        "تمام، سجلت الطلب",
        "لحظة، اتنين بيتزا",
        "one moment, 3 items",
        "it is available",
        "تم",
        "ثانية واحدة",
        "ست دقايق",
        "خلاص اتحجز",
        "done",
        "والسعر",
    ):
        assert _ACK_BAD.search(bad), bad


def test_ack_filter_accepts_neutral_acknowledgements() -> None:
    for ok in ("تمام", "لحظة", "ماشي، ثانية", "طيب، استنى ثانية", "ستني شوية", "حاضر، ثواني", "okay, just a sec"):
        assert not _ACK_BAD.search(ok), ok
