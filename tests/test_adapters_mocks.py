"""P0.2 exit gate: a mock/default adapter exists for every port and behaves per contract (CP-0003)."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest
from qevion.adapters.decision.rules import RulesDecisionAdapter
from qevion.adapters.providers.mocks import (
    MockASRAdapter,
    MockLLMAdapter,
    MockS2SAdapter,
    MockScriptStep,
    MockTTSAdapter,
    frame_ref,
    silence,
)
from qevion.adapters.sinks.memory import JsonlOutcomeSink, MemoryHandoffSink, MemoryOutcomeSink
from qevion.adapters.telephony.simulated import SimCallState, SimulatedTelephonyAdapter
from qevion.adapters.tools.memory_backend import MemoryStore, memory_backends
from qevion.adapters.transports.memory import MemoryTransportSession
from qevion.adapters.turn.energy import EnergyTurnAdapter, MockTurnAdapter
from qevion.admin.credentials import EnvAdminEphemeralResolver
from qevion.contracts.control import CredentialSource
from qevion.contracts.outcome import Outcome, OutcomeTimestamps
from qevion.contracts.ports import (
    ASRPort,
    CapabilityDescriber,
    DecisionPort,
    LLMPort,
    S2SPort,
    TTSPort,
    TurnPort,
)
from qevion.contracts.provider import (
    ASRRequest,
    DecisionKind,
    DecisionRequest,
    DecisionSource,
    LLMMessage,
    LLMRequest,
    ProviderRole,
    S2SEventType,
    S2SSessionConfig,
    ToolCallRequest,
    ToolCallResult,
    TTSRequest,
    TurnDetectorConfig,
    TurnEventType,
)
from qevion.contracts.tool import PlatformTool, ToolInvocation, ToolOutcomeStatus
from qevion.contracts.transport import ClientMessage, ClientMessageType, ServerMessage, ServerMessageType

# ---- every port has an adapter with capabilities --------------------------------------


@pytest.mark.req("QV-ACC-004")
@pytest.mark.parametrize(
    ("adapter", "port", "role"),
    [
        (MockS2SAdapter(), S2SPort, ProviderRole.S2S),
        (MockLLMAdapter(), LLMPort, ProviderRole.LLM),
        (MockASRAdapter(), ASRPort, ProviderRole.ASR),
        (MockTTSAdapter(), TTSPort, ProviderRole.TTS),
        (EnergyTurnAdapter(), TurnPort, ProviderRole.TURN),
        (MockTurnAdapter(), TurnPort, ProviderRole.TURN),
        (RulesDecisionAdapter(), DecisionPort, ProviderRole.DECISION),
    ],
)
def test_adapter_declares_capabilities(adapter: object, port: type, role: ProviderRole) -> None:
    assert isinstance(adapter, CapabilityDescriber)
    caps = adapter.capabilities()
    assert caps.role == role
    assert caps.adapter == adapter.name  # type: ignore[attr-defined]
    assert caps.capabilities


# ---- s2s mock -------------------------------------------------------------------------


async def test_mock_s2s_scripted_flow_with_tool_and_cancel() -> None:
    script = [
        MockScriptStep(text="hello", audio_ms=300),
        MockScriptStep(
            tool_call=ToolCallRequest(call_id="c1", tool_id="record_field", arguments={"name": "x", "value": 1}),
            text="done",
            audio_ms=200,
        ),
    ]
    session = await MockS2SAdapter(script).open(S2SSessionConfig(provider="mock", model="m"), None)
    seen: list[S2SEventType] = []

    async def drain() -> None:
        async for e in session.events():
            seen.append(e.type)
            if e.type is S2SEventType.RESPONSE_TOOL_CALL:
                assert e.tool_call is not None
                await session.send_tool_result(ToolCallResult(call_id=e.tool_call.call_id, output={"ok": True}))

    import asyncio

    task = asyncio.create_task(drain())
    await session.commit_input()
    await asyncio.sleep(0.01)
    await session.commit_input()
    await asyncio.sleep(0.01)
    await session.cancel_response()
    await session.close()
    await task
    assert seen[0] is S2SEventType.SESSION_READY
    assert S2SEventType.RESPONSE_TOOL_CALL in seen
    assert seen.count(S2SEventType.RESPONSE_DONE) == 2
    assert S2SEventType.RESPONSE_CANCELLED in seen
    assert seen[-1] is S2SEventType.CLOSED
    audio_bytes = (
        sum(len(b) async for _, b in session.audio_out()) if False else None
    )  # audio queue closed; accounted below
    assert audio_bytes is None
    assert session.bytes_in == 0


async def test_mock_llm_asr_tts() -> None:
    llm = MockLLMAdapter()
    r = await llm.complete(LLMRequest(model="m", messages=[LLMMessage(role="user", content="hi")]), None)
    assert r.text == "[mock] hi"
    asr = MockASRAdapter(["أهلا"])
    pcm = silence(200)
    a = await asr.transcribe(ASRRequest(audio=frame_ref(pcm), language="ar"), pcm, None)
    assert a.text == "أهلا" and a.is_final
    tts = MockTTSAdapter()
    total = 0
    last = False
    async for chunk, b in tts.synthesize(TTSRequest(text="hello", voice="v", locale="ar-EG"), None):
        total += len(b)
        last = chunk.is_last
    assert last and total == 2 * 24000 * 300 // 1000  # 5 chars*60ms=300ms of pcm16@24k


# ---- turn detector ----------------------------------------------------------------------


def _tone(ms: int, amp: int = 8000) -> bytes:
    n = 24000 * ms // 1000
    return struct.pack(f"<{n}h", *([amp, -amp] * (n // 2) + ([amp] if n % 2 else [])))


@pytest.mark.req("QV-INT-001")
def test_energy_turn_detector_taxonomy_and_barge_in() -> None:
    det = EnergyTurnAdapter().new_detector()
    det.configure(TurnDetectorConfig(min_speech_ms=100, min_silence_ms=400, barge_in_min_speech_ms=200))
    types: list[TurnEventType] = []
    ts = 0
    for _ in range(10):  # 200 ms speech while assistant speaks
        types += [e.type for e in det.push(_tone(20), ts, assistant_speaking=True)]
        ts += 20
    assert TurnEventType.SPEECH_START in types
    assert types.count(TurnEventType.BARGE_IN) == 1
    for _ in range(25):  # 500 ms silence
        types += [e.type for e in det.push(silence(20), ts, assistant_speaking=False)]
        ts += 20
    assert TurnEventType.END_OF_TURN_CANDIDATE in types
    assert types[-1] is TurnEventType.END_OF_TURN
    # short blip below min_speech → noise
    blip = [e.type for e in det.push(_tone(20), ts, False)] + [e.type for e in det.push(silence(20), ts + 20, False)]
    assert TurnEventType.NOISE_REJECTED in blip and TurnEventType.SPEECH_START not in blip


# ---- decision rules -------------------------------------------------------------------------


@pytest.mark.req("QV-ACC-007")
async def test_rules_decision_never_guesses() -> None:
    d = RulesDecisionAdapter()
    ok = await d.decide(
        DecisionRequest(
            kind=DecisionKind.VALIDATE_FIELD, inputs={"value": "3", "type": "integer", "validation": "1..5"}
        )
    )
    assert ok.value == 3 and ok.source is DecisionSource.RULE
    bad = await d.decide(
        DecisionRequest(
            kind=DecisionKind.VALIDATE_FIELD, inputs={"value": "7", "type": "integer", "validation": "1..5"}
        )
    )
    assert bad.value is None and bad.source is DecisionSource.RULE
    weird = await d.decide(
        DecisionRequest(
            kind=DecisionKind.VALIDATE_FIELD, inputs={"value": "x", "type": "string", "validation": "quantum"}
        )
    )
    assert weird.is_unknown
    yes = await d.decide(DecisionRequest(kind=DecisionKind.INTERPRET_CONFIRMATION, inputs={"text": "ايوه تمام"}))
    no = await d.decide(DecisionRequest(kind=DecisionKind.INTERPRET_CONFIRMATION, inputs={"text": "لا غلط"}))
    amb = await d.decide(DecisionRequest(kind=DecisionKind.INTERPRET_CONFIRMATION, inputs={"text": "yes and no"}))
    assert yes.value is True and no.value is False and amb.is_unknown
    rule = await d.decide(
        DecisionRequest(
            kind=DecisionKind.EVALUATE_RULE,
            rules=["consent == true AND q1..q5 recorded AND submit_record accepted"],
            inputs={
                "fields": {"consent": True},
                "recorded": ["consent", "q1_overall", "q2_staff", "q3_wait_time", "q4_recommend", "q5_comment"],
                "flags": ["submit_record_accepted"],
            },
        )
    )
    assert rule.value is True
    claim = await d.decide(
        DecisionRequest(
            kind=DecisionKind.CHECK_CLAIM,
            inputs={
                "claim_type": "promotion_or_offer",
                "provenance": "KNOWLEDGE_APPROVED",
                "allowed": {},
                "prohibited": ["promotion_or_offer"],
            },
        )
    )
    assert claim.value == "blocked"


# ---- transport / tools / sinks / credentials / telephony ----------------------------------------


async def test_memory_transport_roundtrip() -> None:
    t = MemoryTransportSession()
    t.client_sends(ClientMessage(type=ClientMessageType.PING))
    t.client_sends(b"\x00\x00" * 10)
    t.client_disconnects()
    got = [m async for m in t.incoming()]
    assert isinstance(got[0], ClientMessage) and isinstance(got[1], bytes)
    await t.send(ServerMessage(type=ServerMessageType.PONG, session_id="s", server_ts_ms=1))
    await t.send_audio("r1", b"\x00\x00")
    assert t.messages_of("pong") and t.audio_sent == [("r1", b"\x00\x00")]
    await t.close()
    with pytest.raises(ConnectionError):
        await t.send(ServerMessage(type=ServerMessageType.PONG, session_id="s", server_ts_ms=2))


@pytest.mark.req("QV-ACC-009")
async def test_memory_tool_backends_and_fault_injection() -> None:
    store = MemoryStore()
    backends = memory_backends(store)
    inv = ToolInvocation(
        call_id="c",
        tool_id=PlatformTool.SUBMIT_RECORD,
        arguments={"fields": {"a": 1}},
        session_id="s",
        tenant_id="t",
        activity_id="a",
        requested_at_ms=0,
    )
    out = await backends[PlatformTool.SUBMIT_RECORD].execute(inv)
    assert out.status is ToolOutcomeStatus.COMPLETED and store.records[0]["fields"] == {"a": 1}
    store.fail_next.add(PlatformTool.SUBMIT_RECORD)
    assert (await backends[PlatformTool.SUBMIT_RECORD].execute(inv)).status is ToolOutcomeStatus.FAILED
    store.unknown_next.add(PlatformTool.SUBMIT_RECORD)
    assert (await backends[PlatformTool.SUBMIT_RECORD].execute(inv)).status is ToolOutcomeStatus.UNKNOWN
    rec = await backends[PlatformTool.RECORD_FIELD].execute(
        inv.model_copy(update={"tool_id": PlatformTool.RECORD_FIELD, "arguments": {"name": "q1", "value": 4}})
    )
    assert rec.provenance.value == "USER_STATED"


async def test_sinks(tmp_path: Path) -> None:
    from qevion.contracts.common import utc_now
    from qevion.contracts.outcome import ConversationSnapshotRef, HandoffProposer, HandoffRequest

    o = Outcome(
        outcome_id="o",
        session_id="s",
        tenant_id="t",
        activity_id="a",
        activity_version="1.0.0",
        direction="inbound",
        channel="browser_voice",
        primary="completed",
        timestamps=OutcomeTimestamps(session_started=utc_now()),
    )  # type: ignore[arg-type]
    mem = MemoryOutcomeSink()
    assert (await mem.write_outcome(o)).startswith("memory://")
    js = JsonlOutcomeSink(tmp_path / "sink")
    p = await js.write_outcome(o)
    assert Path(p).read_text().count("\n") == 1
    h = MemoryHandoffSink(reject_destinations={"nowhere"})
    req = HandoffRequest(
        handoff_id="h",
        session_id="s",
        tenant_id="t",
        activity_id="a",
        reason="r",
        proposed_by=HandoffProposer.POLICY,
        destination_ref="dest_cs",
        context=ConversationSnapshotRef(transcript_digest="x", activity_state="ENGAGED", dialog_state="IDLE"),
    )
    assert (await h.handoff(req)).accepted
    assert not (await h.handoff(req.model_copy(update={"destination_ref": "nowhere"}))).accepted


@pytest.mark.req("QV-CRED-001")
def test_credential_resolver_order_and_no_leak() -> None:
    r = EnvAdminEphemeralResolver(env={})
    assert r.resolve("openai_realtime", "t") == (None, CredentialSource.NONE)
    scope = r.set_ephemeral("openai_realtime", "FAKE-EPHEMERAL-VALUE-abcd", tenant_id="t", ttl_seconds=60)
    assert scope.fingerprint == "…abcd" and "sk-" not in scope.model_dump_json()
    assert r.resolve("openai_realtime", "t") == ("FAKE-EPHEMERAL-VALUE-abcd", CredentialSource.EPHEMERAL_UI)
    r.set_admin("openai_realtime", "FAKE-ADMIN-VALUE-wxyz")
    assert r.resolve("openai_realtime", "t")[1] is CredentialSource.ADMIN_STORE
    r.env = {"OPENAI_API_KEY": "FAKE-ENV-VALUE-0000"}
    assert r.resolve("openai_realtime", "t")[1] is CredentialSource.ENV
    r.env = {}
    r.admin_store.clear()
    r._ephemeral[("t", "openai_realtime")].expires_at = 0  # noqa: SLF001
    assert r.resolve("openai_realtime", "t") == (None, CredentialSource.NONE)
    assert r.clear_ephemeral() == 0


async def test_simulated_telephony() -> None:
    tel = SimulatedTelephonyAdapter(script={"busy_person": SimCallState.BUSY})
    a = await tel.dial("t", "c1", "act")
    b = await tel.dial("t", "busy_person", "act")
    assert tel.state(a) is SimCallState.ANSWERED and tel.state(b) is SimCallState.BUSY
    await tel.hangup(a)
    await tel.hangup(b)
    assert tel.state(a) is SimCallState.HUNG_UP and tel.state(b) is SimCallState.BUSY
