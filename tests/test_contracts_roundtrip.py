"""QV-ACC-003: every registered contract round-trips model → JSON → model and validates against its
committed JSON Schema; committed schemas match generated ones (no drift)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from pydantic import BaseModel
from qevion.contracts.registry import CONTRACTS, schema_filename

SCHEMAS = Path(__file__).resolve().parents[1] / "qevion" / "contracts" / "schemas"

# Minimal valid instances for models with required fields (kept tiny; hypothesis covers breadth elsewhere).
_MINIMAL: dict[str, dict[str, Any]] = {
    "qevion.event.v1": {
        "tenant_id": "t",
        "seq": 0,
        "kind": "runtime",
        "type": "session.created",
        "source": "core",
    },
    "qevion.policy.v1": {
        "unknown_question_policy": {"default": "STATE_LIMITATION"},
        "uncertainty_policy": {
            "missing": "ASK_CLARIFYING_QUESTION",
            "conflicting": "ASK_CLARIFYING_QUESTION",
            "stale": "STATE_LIMITATION",
            "ambiguous": "ASK_CLARIFYING_QUESTION",
        },
    },
    "qevion.tenant.v1": {"tenant_id": "t", "name": "T"},
    "qevion.line.v1": {
        "line_id": "l",
        "tenant_id": "t",
        "name": "L",
        "channel": "browser_voice",
        "direction": "inbound",
    },
    "qevion.locale_pack.v1": {"locale_pack_id": "lp", "language": "ar", "locale": "ar-EG"},
    "qevion.voice_profile.v1": {
        "voice_profile_id": "vp",
        "display_name": "V",
        "provider_voice_map": {"mock": "v"},
    },
    "qevion.capability_registry.v1": {"adapters": []},
    "qevion.composition.v1": {
        "composition_id": "c",
        "mode": "s2s",
        "bindings": [
            {"role": "s2s", "adapter": "mock"},
            {"role": "turn", "adapter": "mock"},
            {"role": "decision", "adapter": "rules"},
        ],
    },
    "qevion.s2s.v1": {"provider": "mock", "model": "m"},
    "qevion.s2s_event.v1": {"type": "session_ready"},
    "qevion.llm.v1": {"model": "m", "messages": [{"role": "user", "content": "hi"}]},
    "qevion.llm_response.v1": {},
    "qevion.asr.v1": {"audio": {"frame_id": "f", "byte_length": 0, "duration_ms": 0}},
    "qevion.asr_result.v1": {"text": "", "is_final": True},
    "qevion.tts.v1": {"text": "x", "voice": "v", "locale": "ar-EG"},
    "qevion.turn.v1": {"type": "speech_start", "ts_ms": 0, "detector": "mock"},
    "qevion.decision.v1": {"kind": "validate_field"},
    "qevion.decision_result.v1": {"source": "RULE"},
    "qevion.transport.hello.v1": {"tenant_id": "t", "activity_id": "a"},
    "qevion.transport.client.v1": {"type": "ping"},
    "qevion.transport.server.v1": {"type": "pong", "session_id": "s", "server_ts_ms": 0},
    "qevion.tool.v1": {
        "tool_id": "record_field",
        "description": "d",
        "parameters": {"type": "object"},
        "impact": "write",
    },
    "qevion.tool_invocation.v1": {
        "call_id": "c",
        "tool_id": "t",
        "session_id": "s",
        "tenant_id": "t",
        "activity_id": "a",
        "requested_at_ms": 0,
    },
    "qevion.tool_outcome.v1": {"call_id": "c", "tool_id": "t", "status": "completed"},
    "qevion.tool_backend.v1": {"tenant_id": "t", "tool_id": "t", "backend": "in_memory"},
    "qevion.knowledge_source.v1": {"source_id": "s", "tenant_id": "t", "kind": "file", "name": "n"},
    "qevion.knowledge_fact.v1": {
        "fact_id": "f",
        "tenant_id": "t",
        "kind": "attribute",
        "subject": "s",
        "predicate": "p",
        "value": 1,
        "source_id": "s",
    },
    "qevion.knowledge_gap.v1": {
        "gap_id": "g",
        "tenant_id": "t",
        "gap_class": "UNKNOWN",
        "description": "d",
        "question_for_operator": "q",
    },
    "qevion.knowledge_contradiction.v1": {
        "contradiction_id": "c",
        "tenant_id": "t",
        "fact_ids": ["a", "b"],
        "description": "d",
    },
    "qevion.handoff.v1": {
        "handoff_id": "h",
        "session_id": "s",
        "tenant_id": "t",
        "activity_id": "a",
        "reason": "r",
        "proposed_by": "policy",
        "destination_ref": "d",
        "context": {"transcript_digest": "x", "activity_state": "ENGAGED", "dialog_state": "IDLE"},
    },
    "qevion.handoff_result.v1": {"handoff_id": "h", "accepted": True, "destination": "d"},
    "qevion.sink.v1": {"schema": "qevion.outcome_sink.v1", "sink_id": "s", "kind": "memory"},
    "qevion.outcome.v1": {
        "outcome_id": "o",
        "session_id": "s",
        "tenant_id": "t",
        "activity_id": "a",
        "activity_version": "1.0.0",
        "direction": "inbound",
        "channel": "browser_voice",
        "primary": "completed",
        "timestamps": {"session_started": "2026-09-22T00:00:00Z"},
    },
    "qevion.preflight.v1": {"activity_id": "a", "activity_version": "1.0.0", "status": "READY"},
    "qevion.credential_scope.v1": {"provider": "mock", "source": "env"},
    "qevion.metrics.v1": {
        "session_id": "s",
        "segment": "x",
        "watermark_from": "t0_user_speech_onset",
        "watermark_to": "t1_barge_in_detected",
        "value_ms": 1,
    },
    "qevion.usage.v1": {"session_id": "s", "tenant_id": "t", "provider": "mock", "role": "s2s"},
    "qevion.simulation_report.v1": {
        "report_id": "r",
        "tenant_id": "t",
        "activity_id": "a",
        "activity_version": "1.0.0",
        "composition_id": "c",
        "scenarios": [],
        "passed": True,
    },
}
_MINIMAL["qevion.interaction_record.v1"] = {"record_id": "r", "outcome": _MINIMAL["qevion.outcome.v1"]}
_MINIMAL["qevion.copilot.v1"] = {"proposal_id": "p", "config_session_id": "c", "tenant_id": "t"}


def _blueprint_minimal() -> dict[str, Any]:
    return {
        "identity": {"tenant_id": "t", "activity_id": "a", "name": "A", "version": "1.0.0"},
        "direction": "inbound",
        "channels": ["browser_voice"],
        "locale": {"language": "ar", "locale": "ar-EG"},
        "objective": {"primary": {"kind": "inform"}},
        "policies": _MINIMAL["qevion.policy.v1"],
        "outcome_schema": {"primary": ["completed"]},
    }


_MINIMAL["qevion.activity.v1"] = _blueprint_minimal()


def test_every_contract_has_minimal_fixture() -> None:
    assert set(_MINIMAL) == set(CONTRACTS), set(CONTRACTS) ^ set(_MINIMAL)


@pytest.mark.req("QV-ACC-003")
@pytest.mark.parametrize("schema_id", sorted(CONTRACTS))
def test_roundtrip_and_schema(schema_id: str) -> None:
    jsonschema = pytest.importorskip("jsonschema")
    model = CONTRACTS[schema_id]
    obj: BaseModel = model.model_validate(_MINIMAL[schema_id])
    dumped = obj.model_dump(mode="json", by_alias=True)
    again = model.model_validate(dumped)
    assert again == obj
    assert again.model_dump(mode="json", by_alias=True) == dumped
    schema = json.loads((SCHEMAS / schema_filename(schema_id)).read_text())
    assert schema["x-qevion-schema-id"] == schema_id
    jsonschema.Draft202012Validator(schema).validate(dumped)


@pytest.mark.req("QV-EVT-005")
def test_no_schema_drift() -> None:
    import subprocess
    import sys

    r = subprocess.run([sys.executable, "scripts/gen_schemas.py", "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.req("QV-EVT-001")
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
@given(
    seq=st.integers(min_value=0, max_value=10**9),
    payload=st.dictionaries(st.text(min_size=1, max_size=8), st.integers()),
)
def test_event_roundtrip_property(seq: int, payload: dict[str, int]) -> None:
    from qevion.contracts.event import Event

    e = Event(tenant_id="t", seq=seq, kind="runtime", type="a.b", source="core", payload=payload)  # type: ignore[arg-type]
    assert Event.model_validate(e.model_dump(mode="json", by_alias=True)) == e


def test_event_rejects_bad_type_and_negative_seq() -> None:
    from pydantic import ValidationError
    from qevion.contracts.event import Event

    with pytest.raises(ValidationError):
        Event(tenant_id="t", seq=-1, kind="runtime", type="a.b", source="core")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        Event(tenant_id="t", seq=0, kind="runtime", type="NoDots", source="core")  # type: ignore[arg-type]
