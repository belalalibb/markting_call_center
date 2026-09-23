"""Session player — re-runs a SessionRecording through the same Core and diffs canonical events (QV-ACC-019).

Determinism claim: same Blueprint fingerprint + same ScenarioCase + same store seed ⇒ identical canonical
event stream and outcome. Any divergence is reported field-by-field; a fingerprint mismatch is a hard divergence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from qevion.adapters.tools.memory_backend import MemoryStore
from qevion.contracts.activity import ActivityBlueprint
from qevion.replay.recorder import SessionRecording, record
from qevion.simulation.runner import ScenarioRunner, SimulationDeps, blueprint_fingerprint

_SEED_FIELDS = ("entities", "facts", "records", "callbacks", "questions", "handoffs")
_SEED_SETS = ("verify_reject", "fail_next", "unknown_next")


@dataclass(frozen=True)
class EventDivergence:
    index: int
    field: str
    recorded: Any
    replayed: Any


@dataclass
class ReplayResult:
    recording_id: str
    blueprint_fingerprint: str
    fingerprint_match: bool
    recorded_events: int
    replayed_events: int
    divergences: list[EventDivergence] = field(default_factory=list)
    outcome_match: bool = True
    recorded_digest: str = ""
    replayed_digest: str = ""
    lifecycle: list[str] = field(default_factory=list)
    replayed: SessionRecording | None = None

    @property
    def deterministic(self) -> bool:
        return self.fingerprint_match and not self.divergences and self.outcome_match

    def summary(self) -> dict[str, Any]:
        return {
            "recording_id": self.recording_id,
            "blueprint_fingerprint": self.blueprint_fingerprint,
            "fingerprint_match": self.fingerprint_match,
            "recorded_events": self.recorded_events,
            "replayed_events": self.replayed_events,
            "divergence_count": len(self.divergences),
            "divergences": [
                {"index": d.index, "field": d.field, "recorded": d.recorded, "replayed": d.replayed}
                for d in self.divergences[:50]
            ],
            "outcome_match": self.outcome_match,
            "recorded_digest": self.recorded_digest,
            "replayed_digest": self.replayed_digest,
            "deterministic": self.deterministic,
            "lifecycle": list(self.lifecycle),
        }


def diff_events(recorded: list[dict[str, Any]], replayed: list[dict[str, Any]]) -> list[EventDivergence]:
    out: list[EventDivergence] = []
    n = max(len(recorded), len(replayed))
    for i in range(n):
        if i >= len(recorded):
            out.append(EventDivergence(i, "<missing in recording>", None, replayed[i].get("type")))
            continue
        if i >= len(replayed):
            out.append(EventDivergence(i, "<missing in replay>", recorded[i].get("type"), None))
            continue
        a, b = recorded[i], replayed[i]
        for key in ("seq", "kind", "type", "source", "payload"):
            if a.get(key) != b.get(key):
                out.append(EventDivergence(i, key, a.get(key), b.get(key)))
    return out


def _seed_store(seed: dict[str, Any]) -> MemoryStore:
    kwargs: dict[str, Any] = {}
    for name in _SEED_FIELDS:
        if name in seed:
            kwargs[name] = [dict(x) for x in seed[name]]
    for name in _SEED_SETS:
        if name in seed:
            kwargs[name] = set(seed[name])
    return MemoryStore(**kwargs)


async def replay(
    recording: SessionRecording, bp: ActivityBlueprint, composition_id: str = "comp_mock_s2s_v1"
) -> ReplayResult:
    fp = blueprint_fingerprint(bp)
    lifecycle = ["replay.started"]
    result = ReplayResult(
        recording_id=recording.recording_id,
        blueprint_fingerprint=fp,
        fingerprint_match=fp == recording.blueprint_fingerprint,
        recorded_events=recording.event_count,
        replayed_events=0,
        recorded_digest=recording.events_digest(),
        lifecycle=lifecycle,
    )
    if not result.fingerprint_match:
        result.divergences.append(EventDivergence(-1, "blueprint_fingerprint", recording.blueprint_fingerprint, fp))
        result.outcome_match = False
        lifecycle.append("replay.diverged")
        return result

    seed = dict(recording.store_seed)
    deps = SimulationDeps(store_factory=lambda: _seed_store(seed), composition_id=composition_id)
    runner = ScenarioRunner(bp, deps)
    run = await runner.run_case(recording.case)
    again = record(run, bp, store_seed=seed)

    result.replayed = again
    result.replayed_events = again.event_count
    result.replayed_digest = again.events_digest()
    result.divergences = diff_events(recording.events, again.events)
    result.outcome_match = recording.outcome == again.outcome
    lifecycle.append("replay.diverged" if not result.deterministic else "replay.completed")
    return result
