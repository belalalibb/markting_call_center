"""Session recorder — turns a finished simulation CaseRun into a canonical, diffable recording (QV-ACC-019).

Canonicalisation rules:
* random ids ``<prefix>_<16 hex>`` → ``<prefix>_<id>`` (ses_, evt_, out_, rec_, ho_, resp_, frm_, att_, call_, …)
* volatile timing keys (latency_ms, *_ts_ms, checked_at, produced_at, recorded_at) are dropped
* events keep only ``seq, kind, type, source, payload`` — timestamps/trace ids are not part of determinism.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any

from qevion.contracts.activity import ActivityBlueprint
from qevion.contracts.event import Event
from qevion.contracts.outcome import Outcome
from qevion.contracts.simulation import ScenarioCase
from qevion.simulation.runner import CaseRun, blueprint_fingerprint

_ID_RE = re.compile(r"\b([a-z]{2,8})_([0-9a-f]{16})\b")
_VOLATILE_KEYS = frozenset(
    {
        "latency_ms",
        "client_ts_ms",
        "server_ts_ms",
        "checked_at",
        "produced_at",
        "recorded_at",
        "ts",
        "t0",
        "t1",
        "t2",
        "t3",
        "t4",
    }
)


def _normalise_ids(text: str) -> str:
    return _ID_RE.sub(lambda m: f"{m.group(1)}_<id>", text)


def canonical_payload(value: Any) -> Any:
    """Recursively normalise ids and strip volatile keys."""
    if isinstance(value, dict):
        return {k: canonical_payload(v) for k, v in sorted(value.items()) if k not in _VOLATILE_KEYS}
    if isinstance(value, (list, tuple)):
        return [canonical_payload(v) for v in value]
    if isinstance(value, str):
        return _normalise_ids(value)
    if hasattr(value, "value") and not isinstance(value, (int, float, bool)):
        return canonical_payload(value.value)
    return value


def canonical_event(e: Event) -> dict[str, Any]:
    kind = e.kind.value if hasattr(e.kind, "value") else str(e.kind)
    return {
        "seq": e.seq,
        "kind": kind,
        "type": str(e.type),
        "source": str(e.source),
        "payload": canonical_payload(e.payload),
    }


def canonical_outcome(outcome: Outcome | None) -> dict[str, Any] | None:
    if outcome is None:
        return None
    data = outcome.model_dump(mode="json", by_alias=True)
    keep = ("primary", "secondary", "collected_fields", "next_actions", "observations", "flags")
    return {k: canonical_payload(data[k]) for k in keep if k in data}


def _digest(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


@dataclass
class SessionRecording:
    recording_id: str
    blueprint_fingerprint: str
    case: ScenarioCase
    store_seed: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    outcome: dict[str, Any] | None = None
    event_count: int = 0
    meta: dict[str, Any] = field(default_factory=dict)

    def events_digest(self) -> str:
        return _digest(self.events)

    def outcome_digest(self) -> str:
        return _digest(self.outcome)

    def to_json(self) -> str:
        return json.dumps(
            {
                "schema": "qevion.session_recording.v1",
                "recording_id": self.recording_id,
                "blueprint_fingerprint": self.blueprint_fingerprint,
                "case": self.case.model_dump(mode="json", by_alias=True),
                "store_seed": self.store_seed,
                "events": self.events,
                "outcome": self.outcome,
                "event_count": self.event_count,
                "meta": self.meta,
            },
            sort_keys=True,
            indent=2,
        )

    @classmethod
    def from_json(cls, text: str) -> SessionRecording:
        raw = json.loads(text)
        return cls(
            recording_id=raw["recording_id"],
            blueprint_fingerprint=raw["blueprint_fingerprint"],
            case=ScenarioCase.model_validate(raw["case"]),
            store_seed=dict(raw.get("store_seed") or {}),
            events=list(raw.get("events") or []),
            outcome=raw.get("outcome"),
            event_count=int(raw.get("event_count") or 0),
            meta=dict(raw.get("meta") or {}),
        )


def record(run: CaseRun, bp: ActivityBlueprint, store_seed: dict[str, Any] | None = None) -> SessionRecording:
    """Snapshot a finished CaseRun. ``store_seed`` is the MemoryStore seed used for the run (entities/facts/…)."""
    events = [canonical_event(e) for e in run.session.events]
    outcomes = run.outcome_sink.outcomes
    outcome = canonical_outcome(outcomes[-1] if outcomes else None)
    return SessionRecording(
        recording_id=f"rec_{_digest(events)[:16]}",
        blueprint_fingerprint=blueprint_fingerprint(bp),
        case=run.case,
        store_seed=dict(store_seed or {}),
        events=events,
        outcome=outcome,
        event_count=len(events),
        meta={
            "case_id": run.case.case_id,
            "persona_kind": str(
                run.case.persona.kind.value if hasattr(run.case.persona.kind, "value") else run.case.persona.kind
            ),
            "error": run.error,
        },
    )
