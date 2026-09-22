"""P1 exit gate — end-to-end Session scenarios on mocks for Activities A, B and C (QV-ACC-006, -007, -009, -010).

The same `Session` code runs every Activity; only the Blueprint YAML and the scripted provider differ.
Nothing here branches on business vocabulary; field/tool names are read from the Blueprint under test.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
import yaml
from qevion.adapters.decision.rules import RulesDecisionAdapter
from qevion.adapters.providers.mocks import MockS2SAdapter, MockScriptStep
from qevion.adapters.sinks.memory import MemoryHandoffSink, MemoryOutcomeSink
from qevion.adapters.tools.memory_backend import MemoryStore, memory_backends
from qevion.adapters.transports.memory import MemoryTransportSession
from qevion.adapters.turn.energy import EnergyTurnAdapter
from qevion.contracts.activity import ActivityBlueprint
from qevion.contracts.common import Channel, Provenance
from qevion.contracts.control import ActivityState, DialogState
from qevion.contracts.event import EventType
from qevion.contracts.provider import S2SSessionConfig, ToolCallRequest
from qevion.contracts.tool import PlatformTool, ToolOutcomeStatus
from qevion.contracts.transport import ClientMessage, ClientMessageType
from qevion.core.platform_tools import declarations_for_blueprint_permissions
from qevion.core.session import Session, SessionDeps

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "config" / "examples"


def _bp(name: str) -> ActivityBlueprint:
    return ActivityBlueprint.model_validate(yaml.safe_load((EXAMPLES / f"{name}.yaml").read_text()))


class _Clock:
    def __init__(self) -> None:
        self.now = 0

    def __call__(self) -> int:
        self.now += 5  # every read advances 5 ms → deterministic, replayable timings
        return self.now


def _tc(call_id: str, tool: str, **args: Any) -> ToolCallRequest:
    return ToolCallRequest(call_id=call_id, tool_id=tool, arguments=args)


def _harness(
    bp: ActivityBlueprint, script: list[MockScriptStep], *, store: MemoryStore | None = None
) -> tuple[Session, MemoryTransportSession, MemoryOutcomeSink, MemoryHandoffSink, MemoryStore]:
    store = store or MemoryStore()
    transport = MemoryTransportSession()
    sink = MemoryOutcomeSink()
    hsink = MemoryHandoffSink()
    deps = SessionDeps(
        blueprint=bp,
        s2s=MockS2SAdapter(script),
        s2s_config=S2SSessionConfig(provider="mock", model="mock-1"),
        transport=transport,
        turn=EnergyTurnAdapter().new_detector(),
        decision=RulesDecisionAdapter(),
        tool_declarations=declarations_for_blueprint_permissions(bp.tools.permissions),
        tool_backends=memory_backends(store),
        outcome_sink=sink,
        handoff_sink=hsink,
        channel=Channel.TEXT,
        clock=_Clock(),
        confirmation_timeout_ms=500,
    )
    return Session(deps), transport, sink, hsink, store


async def _drive(session: Session, transport: MemoryTransportSession, user_turns: list[ClientMessage]) -> None:
    """Feed client messages one per scheduler tick, then hang up. `run()` returns the InteractionRecord."""
    for m in user_turns:
        transport.client_sends(m)
        for _ in range(40):  # let provider/tool round-trips settle between turns
            await asyncio.sleep(0)
    transport.client_sends(ClientMessage(type=ClientMessageType.BYE))


def _text(t: str) -> ClientMessage:
    return ClientMessage(type=ClientMessageType.TEXT, text=t)


def _types(session: Session) -> list[str]:
    return [e.type for e in session.events]


# ---------------------------------------------------------------- Activity A: inbound order intake


async def test_activity_a_happy_path_fields_confirmation_submit() -> None:
    bp = _bp("activity_a_restaurant")
    req = [f.name for f in bp.data.required]
    store = MemoryStore(
        entities=[{"entity_id": "e1", "entity_type": "item", "name": "Alpha", "unit_value": 10}],
    )
    script = [
        MockScriptStep(text="opening", audio_ms=100),
        MockScriptStep(tool_call=_tc("c1", PlatformTool.RECORD_FIELD, name=req[0], value=["e1"]), text="ok"),
        MockScriptStep(tool_call=_tc("c2", PlatformTool.RECORD_FIELD, name=req[1], value="2"), text="ok"),
        MockScriptStep(tool_call=_tc("c3", PlatformTool.RECORD_FIELD, name=req[2], value="somewhere"), text="ok"),
        MockScriptStep(tool_call=_tc("c4", PlatformTool.VERIFY_FIELD, name=req[2], value="somewhere"), text="ok"),
        MockScriptStep(tool_call=_tc("c5", PlatformTool.RECORD_FIELD, name=req[3], value="01012345678"), text="ok"),
        MockScriptStep(tool_call=_tc("c6", PlatformTool.COMPUTE_QUOTE, items=[{"entity_id": "e1", "quantity": 2}])),
        MockScriptStep(tool_call=_tc("c7", PlatformTool.SUBMIT_RECORD, fields={"x": 1}), text="submitted"),
    ]
    session, transport, sink, _, store = _harness(bp, script, store=store)
    task = asyncio.create_task(session.run())
    turns = [_text("hi"), *(_text(f"t{i}") for i in range(1, 8))]
    for m in turns:
        transport.client_sends(m)
        for _ in range(40):
            await asyncio.sleep(0)
    # submit_record is confirm_before_execute in Activity A → UI confirmation arrives
    confs = transport.messages_of("confirmation_request")
    assert confs, _types(session)[-12:]
    call_id = confs[-1].payload["call_id"]
    assert session.dialog.state is DialogState.WAITING_CONFIRMATION
    transport.client_sends(ClientMessage(type=ClientMessageType.CONFIRM, call_id=call_id, granted=True))
    for _ in range(60):
        await asyncio.sleep(0)
    transport.client_sends(ClientMessage(type=ClientMessageType.BYE))
    record = await asyncio.wait_for(task, 5)

    # provenance: address (required TOOL_VERIFIED) was upgraded by verify_field; others USER_STATED
    fv = {f.name: f for f in record.outcome.collected_fields}
    assert fv[req[2]].provenance is Provenance.TOOL_VERIFIED
    assert fv[req[1]].value == 2 and fv[req[1]].provenance is Provenance.USER_STATED  # coerced by decision port
    assert store.records and store.records[0]["fields"] == {"x": 1}
    assert record.outcome.primary == "accepted", record.outcome.observations
    assert record.outcome.activity_id == bp.identity.activity_id
    assert session.activity.state is ActivityState.ENDED
    assert sink.records == [record]
    ev = _types(session)
    assert EventType.TOOL_CONFIRMATION_GRANTED in ev and EventType.OUTCOME_PRODUCED in ev
    # no raw text in events (QV-EVT-003)
    for e in session.events:
        assert "text" not in e.payload and "transcript" not in e.payload or e.payload.get("transcript") is True


async def test_activity_a_invalid_field_never_recorded_and_quote_unknown_not_upgraded() -> None:
    bp = _bp("activity_a_restaurant")
    req = [f.name for f in bp.data.required]
    script = [
        MockScriptStep(text="opening", audio_ms=50),
        MockScriptStep(tool_call=_tc("c1", PlatformTool.RECORD_FIELD, name=req[3], value="123"), text="ok"),
        MockScriptStep(tool_call=_tc("c2", PlatformTool.COMPUTE_QUOTE, items=[{"name": "not-in-catalog"}]), text="ok"),
    ]
    session, transport, _, _, _ = _harness(bp, script)
    task = asyncio.create_task(session.run())
    await _drive(session, transport, [_text("hi"), _text("t1"), _text("t2")])
    record = await asyncio.wait_for(task, 5)
    assert req[3] not in {f.name for f in record.outcome.collected_fields}  # regex failed → never stored
    quote = [o for o in session.pipeline.history if o.tool_id == PlatformTool.COMPUTE_QUOTE][0]
    assert quote.status is ToolOutcomeStatus.UNKNOWN
    assert EventType.TOOL_EXECUTION_UNKNOWN in _types(session)
    assert record.outcome.primary in ("abandoned", "partially_completed")


async def test_activity_a_confirmation_denied_returns_to_collecting_and_nothing_submitted() -> None:
    bp = _bp("activity_a_restaurant")
    script = [
        MockScriptStep(text="opening", audio_ms=50),
        MockScriptStep(tool_call=_tc("c1", PlatformTool.SUBMIT_RECORD, fields={"x": 1}), text="?"),
    ]
    session, transport, _, _, store = _harness(bp, script)
    task = asyncio.create_task(session.run())
    transport.client_sends(_text("hi"))
    for _ in range(40):
        await asyncio.sleep(0)
    transport.client_sends(_text("submit"))
    for _ in range(40):
        await asyncio.sleep(0)
    call_id = transport.messages_of("confirmation_request")[-1].payload["call_id"]
    # spoken denial goes through the ConfirmationInterpreter (decision port), never guessed
    transport.client_sends(_text("no, that's wrong"))
    for _ in range(60):
        await asyncio.sleep(0)
    assert not store.records
    assert EventType.TOOL_CONFIRMATION_DENIED in _types(session)
    assert session.activity.state is ActivityState.COLLECTING
    transport.client_sends(ClientMessage(type=ClientMessageType.BYE))
    record = await asyncio.wait_for(task, 5)
    assert record.outcome.primary != "accepted"
    assert call_id not in session._pending_confirm


# ---------------------------------------------------------------- Activity B: appointment booking


async def test_activity_b_handoff_via_tool_produces_human_required_with_context_projection() -> None:
    bp = _bp("activity_b_clinic")
    req = [f.name for f in bp.data.required]
    dest = bp.handoff_rules[0].destination_ref
    script = [
        MockScriptStep(text="opening", audio_ms=50),
        MockScriptStep(tool_call=_tc("c1", PlatformTool.RECORD_FIELD, name=req[0], value="Someone"), text="ok"),
        MockScriptStep(tool_call=_tc("c2", PlatformTool.REQUEST_HANDOFF, reason="urgent", destination_ref=dest)),
    ]
    session, transport, _, hsink, _ = _harness(bp, script)
    task = asyncio.create_task(session.run())
    await _drive(session, transport, [_text("hi"), _text("name"), _text("urgent")])
    record = await asyncio.wait_for(task, 5)
    assert record.outcome.primary == "human_required"
    assert record.handoff_ids and hsink.requests[0].destination_ref == dest
    assert hsink.requests[0].context.fields[0].name == req[0]
    assert session.activity.state is ActivityState.ESCALATED
    assert "handoff" in record.outcome.next_actions


async def test_activity_b_list_entities_and_verify_reject_keeps_slot_unverified() -> None:
    bp = _bp("activity_b_clinic")
    slot = [f for f in bp.data.required if f.provenance_required is Provenance.TOOL_VERIFIED][0].name
    store = MemoryStore(
        entities=[{"entity_id": "s1", "entity_type": "slot", "name": "slot-1", "available": True}],
        verify_reject={slot},
    )
    script = [
        MockScriptStep(text="opening", audio_ms=50),
        MockScriptStep(tool_call=_tc("c1", PlatformTool.LIST_ENTITIES, entity_type="slot"), text="options"),
        MockScriptStep(tool_call=_tc("c2", PlatformTool.RECORD_FIELD, name=slot, value="2026-10-01T10:00"), text="ok"),
        MockScriptStep(tool_call=_tc("c3", PlatformTool.VERIFY_FIELD, name=slot, value="2026-10-01T10:00"), text="?"),
    ]
    session, transport, _, _, _ = _harness(bp, script, store=store)
    task = asyncio.create_task(session.run())
    await _drive(session, transport, [_text("hi"), _text("slots?"), _text("pick"), _text("verify")])
    record = await asyncio.wait_for(task, 5)
    lst = [o for o in session.pipeline.history if o.tool_id == PlatformTool.LIST_ENTITIES][0]
    assert lst.provenance is Provenance.KNOWLEDGE_APPROVED and lst.output["count"] == 1
    fv = {f.name: f for f in record.outcome.collected_fields}
    assert fv[slot].provenance is Provenance.USER_STATED  # verification rejected → never upgraded
    assert not session.fields.ready_for_execution()
    assert any(o.startswith(f"field {slot} requires TOOL_VERIFIED") for o in record.outcome.observations)


# ---------------------------------------------------------------- Activity C: outbound survey


async def test_activity_c_exit_rule_via_callback_flag() -> None:
    bp = _bp("activity_c_survey")
    script = [
        MockScriptStep(text="opening", audio_ms=50),
        MockScriptStep(tool_call=_tc("c1", PlatformTool.SCHEDULE_CALLBACK, when="tomorrow"), text="ok"),
    ]
    session, transport, _, _, store = _harness(bp, script)
    task = asyncio.create_task(session.run())
    transport.client_sends(_text("hi"))
    for _ in range(40):
        await asyncio.sleep(0)
    transport.client_sends(_text("call me tomorrow"))
    for _ in range(40):
        await asyncio.sleep(0)
    # schedule_callback is confirm_before_execute in Activity C
    call_id = transport.messages_of("confirmation_request")[-1].payload["call_id"]
    transport.client_sends(ClientMessage(type=ClientMessageType.CONFIRM, call_id=call_id, granted=True))
    for _ in range(60):
        await asyncio.sleep(0)
    transport.client_sends(ClientMessage(type=ClientMessageType.BYE))
    record = await asyncio.wait_for(task, 5)
    assert store.callbacks and "callback_scheduled" in session.facts.flags
    assert record.outcome.primary == "callback_requested", record.outcome.observations
    assert "schedule_callback" in record.outcome.next_actions


async def test_activity_c_failure_rule_consent_false() -> None:
    bp = _bp("activity_c_survey")
    consent = bp.data.required[0].name
    script = [
        MockScriptStep(text="opening", audio_ms=50),
        MockScriptStep(tool_call=_tc("c1", PlatformTool.RECORD_FIELD, name=consent, value="no"), text="bye"),
    ]
    session, transport, _, _, _ = _harness(bp, script)
    task = asyncio.create_task(session.run())
    await _drive(session, transport, [_text("hi"), _text("no")])
    record = await asyncio.wait_for(task, 5)
    # `must_be_true` validation rejects False → not recorded → failure rule can't fire; the field is re-asked.
    assert consent not in {f.name for f in record.outcome.collected_fields}
    assert session.objectives.has  # objective parked for re-ask
    assert record.outcome.primary in ("abandoned", "partially_completed")


# ---------------------------------------------------------------- Cross-activity invariants


@pytest.mark.parametrize("name", ["activity_a_restaurant", "activity_b_clinic", "activity_c_survey"])
async def test_every_activity_runs_on_identical_core_and_emits_envelope(name: str) -> None:
    bp = _bp(name)
    session, transport, sink, _, _ = _harness(bp, [MockScriptStep(text="opening", audio_ms=50)])
    task = asyncio.create_task(session.run())
    await _drive(session, transport, [_text("hi")])
    record = await asyncio.wait_for(task, 5)
    ev = _types(session)
    assert ev[0] == EventType.SESSION_CREATED and ev[-1] == EventType.SESSION_ENDED
    assert EventType.STATE_CHANGED in ev and EventType.INTERACTION_RECORD_PRODUCED in ev
    assert all(
        e.tenant_id == bp.identity.tenant_id and e.activity_version == bp.identity.version for e in session.events
    )
    assert [e.seq for e in session.events] == list(range(len(session.events)))
    assert record.outcome.primary in bp.outcome_schema.primary
    assert sink.records == [record]
    assert transport.closed


async def test_illegal_authority_cannot_move_activity_machine() -> None:
    """Model text never transitions the activity machine: only tool outcomes / rules did in the scenarios above."""
    bp = _bp("activity_a_restaurant")
    session, transport, _, _, _ = _harness(bp, [MockScriptStep(text="I have submitted your order", audio_ms=50)])
    task = asyncio.create_task(session.run())
    await _drive(session, transport, [_text("hi")])
    record = await asyncio.wait_for(task, 5)
    authorities = {e.payload["authority"] for e in session.events if e.type == EventType.STATE_CHANGED}
    assert all(a.startswith("core") for a in authorities)
    assert record.outcome.primary != "accepted"
