"""P6 — deterministic replay on the same Core (QV-ACC-019).

Record a simulation CaseRun (Activity A/B/C via default_cases), replay it from the recording alone and
assert an identical canonical event stream + outcome. A changed Blueprint must surface as divergence.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from qevion.contracts.activity import ActivityBlueprint
from qevion.contracts.event import EventType
from qevion.replay.player import diff_events, replay
from qevion.replay.recorder import SessionRecording, canonical_payload, record
from qevion.simulation.cases import default_cases
from qevion.simulation.runner import ScenarioRunner

ROOT = Path(__file__).resolve().parents[1]


def _bp(name: str) -> ActivityBlueprint:
    return ActivityBlueprint.model_validate(yaml.safe_load((ROOT / "config/examples" / f"{name}.yaml").read_text()))


@pytest.mark.parametrize("name", ["activity_a_restaurant", "activity_b_clinic", "activity_c_survey"])
async def test_record_then_replay_is_deterministic(name: str) -> None:
    bp = _bp(name)
    cases = default_cases(bp)
    assert cases
    runner = ScenarioRunner(bp)
    for case in cases[:4]:
        run = await runner.run_case(case)
        rec = record(run, bp)
        assert rec.event_count > 0
        assert any(e["type"] == EventType.SESSION_STARTED for e in rec.events)
        res = await replay(rec, bp)
        assert res.fingerprint_match
        assert res.divergences == [], res.summary()
        assert res.outcome_match
        assert res.deterministic
        assert res.recorded_digest == res.replayed_digest
        assert res.lifecycle == ["replay.started", "replay.completed"]


async def test_blueprint_change_is_detected_as_divergence() -> None:
    bp = _bp("activity_c_survey")
    case = default_cases(bp)[0]
    run = await ScenarioRunner(bp).run_case(case)
    rec = record(run, bp)
    changed = bp.model_copy(update={"identity": bp.identity.model_copy(update={"version": "9.9.9"})})
    res = await replay(rec, changed)
    assert not res.fingerprint_match
    assert not res.deterministic
    assert res.divergences[0].field == "blueprint_fingerprint"
    assert res.lifecycle == ["replay.started", "replay.diverged"]


async def test_recording_json_roundtrip() -> None:
    bp = _bp("activity_a_restaurant")
    case = default_cases(bp)[0]
    run = await ScenarioRunner(bp).run_case(case)
    rec = record(run, bp, store_seed={"entities": [], "fail_next": []})
    text = rec.to_json()
    back = SessionRecording.from_json(text)
    assert back.recording_id == rec.recording_id
    assert back.events == rec.events
    assert back.outcome == rec.outcome
    assert back.case == rec.case
    assert back.events_digest() == rec.events_digest()
    res = await replay(back, bp)
    assert res.deterministic, res.summary()


def test_canonical_payload_normalises_ids_and_drops_volatile_keys() -> None:
    raw = {
        "session_id": "ses_0123456789abcdef",
        "latency_ms": 42,
        "nested": {"ref": "memory://outcome/out_fedcba9876543210", "ts": "2026-01-01T00:00:00Z", "n": 1},
        "list": ["resp_0000000000000000", 3],
    }
    canon = canonical_payload(raw)
    assert canon == {
        "list": ["resp_<id>", 3],
        "nested": {"n": 1, "ref": "memory://outcome/out_<id>"},
        "session_id": "ses_<id>",
    }


def test_diff_events_reports_field_level_divergence() -> None:
    a = [{"seq": 1, "kind": "lifecycle", "type": "x", "source": "core", "payload": {"a": 1}}]
    b = [{"seq": 1, "kind": "lifecycle", "type": "x", "source": "core", "payload": {"a": 2}}, {"seq": 2}]
    d = diff_events(a, b)
    assert [(x.index, x.field) for x in d] == [(0, "payload"), (1, "<missing in recording>")]
