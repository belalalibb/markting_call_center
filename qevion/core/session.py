"""Session orchestrator — wires the Core primitives to ports, via contracts only (§27–§31, QV-RT, QV-INT).

Authority model (QV-RT-003): the dialog machine moves on normalized transport/provider/turn events; the activity
machine moves only on Core-validated facts (tool outcomes, FieldStore completion, decision-port verdicts,
confirmation interpreter). Model text never transitions anything and is never business truth.

Interruption protocol (§31, QV-INT-001) is implemented here, identically for every provider:
  1 DETECT → 2 CANCEL (provider.cancel_response + transport.stop_playout, 300 ms force path) → 3 RECONCILE
  (truncate to what was heard; unheard remainder never persists) → 4 ACCEPT → 5 COMMIT → 6 COHERE
  (FieldStore untouched by construction) → 7 RESPOND. Watermarks t0..t4 are recorded per interruption.

Events never carry raw audio, secrets or full transcripts (QV-EVT-003): text is summarized as length + digest.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from qevion.contracts.activity import ActivityBlueprint
from qevion.contracts.common import Channel, Provenance, new_id
from qevion.contracts.control import ActivityState, DialogState
from qevion.contracts.event import Event, EventKind, EventType
from qevion.contracts.outcome import (
    ConversationSnapshotRef,
    CoverageMissEntry,
    HandoffProposer,
    HandoffRequest,
    InteractionRecord,
    RouteEntry,
)
from qevion.contracts.ports import (
    DecisionPort,
    HandoffSink,
    OutcomeSink,
    S2SPort,
    S2SSession,
    ToolBackend,
    TransportSession,
    TurnDetector,
)
from qevion.contracts.provider import (
    AudioFrameRef,
    DecisionKind,
    DecisionRequest,
    DecisionSource,
    S2SEvent,
    S2SEventType,
    S2SSessionConfig,
    ToolCallRequest,
    ToolCallResult,
    TurnEvent,
    TurnEventType,
)
from qevion.contracts.telemetry import LatencySample, Watermark
from qevion.contracts.tenant import LocalePack, VoiceProfile
from qevion.contracts.tool import PlatformTool, ToolDeclaration, ToolInvocation, ToolOutcome, ToolOutcomeStatus
from qevion.contracts.transport import ClientMessage, ClientMessageType, ServerMessage, ServerMessageType
from qevion.core.activity_machine import ActivityMachine, ActivityTrigger
from qevion.core.context import EntityFocusStack, ObjectiveKind, PendingObjectives
from qevion.core.dialog_machine import DialogMachine, Transition
from qevion.core.field_store import FieldStore
from qevion.core.governance import ClaimGovernor, ConfirmationInterpreter
from qevion.core.instruction_composer import InstructionComposer, RuntimeSnapshot
from qevion.core.outcome_engine import OutcomeEngine, SessionFacts, flags_from_tools
from qevion.core.tool_pipeline import BudgetGuard, ToolPipeline

EventSink = Callable[[Event], Awaitable[None]]
Clock = Callable[[], int]  # ms since session start (injected for replay determinism, QV-RT-008)

_CANCEL_FORCE_MS = 300
# F-02 safety net: a done response is considered audible for its audio duration (+grace) after playout start
# when the client never reports playout_stopped (old clients, lost message).
_AUDIBLE_GRACE_MS = 400


def _digest(text: str) -> dict[str, Any]:
    """Redacted text summary for events — never the text itself (QV-PRIV / QV-EVT-003)."""
    return {"text_len": len(text), "text_sha256_12": hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]}


def _monotonic_clock() -> Clock:
    t0 = time.monotonic()
    return lambda: int((time.monotonic() - t0) * 1000)


@dataclass
class SessionDeps:
    """Everything a session needs, all behind contracts. Built by the runtime composition layer (P4), by tests here."""

    blueprint: ActivityBlueprint
    s2s: S2SPort
    s2s_config: S2SSessionConfig
    transport: TransportSession
    turn: TurnDetector
    decision: DecisionPort
    tool_declarations: dict[str, ToolDeclaration]
    tool_backends: dict[str, ToolBackend]
    outcome_sink: OutcomeSink
    handoff_sink: HandoffSink | None = None
    credential: str | None = None
    locale_pack: LocalePack | None = None
    voice_profile: VoiceProfile | None = None
    tenant_allowed_tools: set[str] | None = None
    channel: Channel = Channel.TEXT
    clock: Clock | None = None
    event_sink: EventSink | None = None
    budget: BudgetGuard = field(default_factory=BudgetGuard)
    confirmation_timeout_ms: int = 30_000


@dataclass
class InterruptionRecord:
    """The §31 watermarks (ms since session start) for one interruption."""

    response_id: str
    t0_user_speech_onset: int
    t1_barge_in_detected: int
    t2_cancel_sent: int | None = None
    t3_playout_stopped: int | None = None
    t4_state_reconciled: int | None = None
    forced: bool = False
    played_ms: int = 0
    heard_text_len: int = 0
    unheard_text_len: int = 0


@dataclass
class ResponseTrack:
    response_id: str
    started_ms: int
    text: str = ""
    audio_ms_sent: int = 0
    cancelled: bool = False
    done: bool = False
    playout_started_ms: int | None = None  # F-02: client-reported start of audible playout


class SessionCore:
    """State + events + machines. `Session` (below) adds I/O handling on top."""

    def __init__(self, deps: SessionDeps, *, session_id: str | None = None) -> None:
        self.deps = deps
        bp = deps.blueprint
        self.session_id = session_id or new_id("ses")
        self.clock: Clock = deps.clock or _monotonic_clock()
        self.events: list[Event] = []
        self._seq = 0
        self.dialog = DialogMachine()
        self.activity = ActivityMachine.from_blueprint_ref(bp.activity_machine.table_ref, bp.activity_machine.inline)
        self.fields = FieldStore.from_specs(bp.data.required, bp.data.optional)
        self.focus = EntityFocusStack()
        self.objectives = PendingObjectives()
        self.governor = ClaimGovernor(bp.policies, deps.decision)
        lp = deps.locale_pack
        self.confirmer = ConfirmationInterpreter(
            deps.decision,
            yes_phrases=list(lp.confirmation_phrases) if lp else [],
            no_phrases=list(lp.negation_phrases) if lp else [],
        )
        self.composer = InstructionComposer(bp, deps.tool_declarations, deps.locale_pack, deps.voice_profile)
        self.outcome_engine = OutcomeEngine(bp, deps.decision)
        self.pipeline = ToolPipeline(
            declarations=deps.tool_declarations,
            tools_block=bp.tools,
            backends=deps.tool_backends,
            emit=self._emit_tool,
            budget=deps.budget,
            confirm=self._confirm_tool,
            tenant_allowed_tools=deps.tenant_allowed_tools,
        )
        self.facts = SessionFacts(session_id=self.session_id, channel=deps.channel, started_at_ms=0)
        self.interruptions: list[InterruptionRecord] = []
        self.latency: list[LatencySample] = []
        self.record: InteractionRecord | None = None
        self.turn_id: str | None = None
        self._turn_no = 0
        self._provider: S2SSession | None = None
        self._responses: dict[str, ResponseTrack] = {}
        self._current_response: str | None = None
        self._audible: str | None = None  # F-02: response currently audible at the client (may outlive generation)
        self._speech_onset_ms: int | None = None
        self._pending_confirm: dict[str, asyncio.Future[bool | None]] = {}
        self._playout_stopped = asyncio.Event()
        self._closed = False
        self._instructions_fp: str | None = None

    # ------------------------------------------------------------------ events
    async def emit(
        self,
        type_: str,
        payload: dict[str, Any] | None = None,
        *,
        source: str = "core",
        kind: EventKind = EventKind.RUNTIME,
    ) -> Event:
        bp = self.deps.blueprint
        ev = Event(
            seq=self._seq,
            tenant_id=bp.identity.tenant_id,
            session_id=self.session_id,
            line_id=bp.identity.line_id,
            activity_id=bp.identity.activity_id,
            activity_version=bp.identity.version,
            turn_id=self.turn_id,
            kind=kind,
            type=type_,
            source=source,
            payload={"ts_ms": self.clock(), **(payload or {})},
        )
        self._seq += 1
        self.events.append(ev)
        self.facts.event_count = len(self.events)
        if self.deps.event_sink:
            await self.deps.event_sink(ev)
        return ev

    async def _emit_tool(self, type_: str, payload: dict[str, Any]) -> None:
        await self.emit(type_, payload, source=f"tool:{payload.get('tool_id', '?')}")

    async def _confirm_tool(self, inv: ToolInvocation) -> bool | None:  # overridden in Session
        return None

    async def _transition(self, t: Transition, *, push_state: bool = True) -> None:
        await self.emit(
            EventType.STATE_CHANGED,
            {
                "machine": t.machine,
                "from": t.from_state,
                "to": t.to_state,
                "trigger": t.trigger,
                "reason": t.reason,
                "authority": t.authority,
            },
        )
        if t.machine == "activity":
            self.facts.activity_state = ActivityState(t.to_state)
        if push_state:
            await self._send_state()

    async def dialog_fire(self, trigger: str, reason: str | None = None) -> bool:
        if not self.dialog.can(trigger):
            await self.emit(
                EventType.FAILURE_CLASSIFIED,
                {"class": "illegal_dialog_transition", "trigger": trigger, "state": self.dialog.state.value},
            )
            return False
        await self._transition(self.dialog.fire(trigger, self.clock(), reason))
        return True

    async def activity_fire(self, trigger: ActivityTrigger, reason: str, *, authority: str) -> bool:
        """Only Core-validated authorities may call this (QV-RT-003)."""
        t = self.activity.fire_if_possible(trigger, self.clock(), reason)
        if t is None:
            return False
        t.authority = authority
        await self._transition(t)
        return True

    # ------------------------------------------------------------------ transport helpers
    async def _send(self, type_: ServerMessageType, **kw: Any) -> None:
        if self._closed:
            return
        try:
            await self.deps.transport.send(
                ServerMessage(type=type_, session_id=self.session_id, server_ts_ms=self.clock(), **kw)
            )
        except ConnectionError:
            await self.emit(EventType.TRANSPORT_DISCONNECTED, {"reason": "send failed"})

    async def _send_state(self) -> None:
        await self._send(
            ServerMessageType.STATE,
            payload={
                "dialog": self.dialog.state.value,
                "activity": self.activity.state.value,
                "missing_required": self.fields.missing_required(),
                "recorded": sorted(self.fields.recorded_names()),
                "turn_id": self.turn_id,
            },
        )

    # ------------------------------------------------------------------ instructions (QV-RT-006)
    def _snapshot(self) -> RuntimeSnapshot:
        return RuntimeSnapshot(
            activity_state=self.activity.state,
            missing_required=self.fields.missing_required(),
            unsatisfied=[(n, need) for n, need, _ in self.fields.unsatisfied_required()],
            focus_ambiguous=self.focus.is_ambiguous(),
            pending_confirmation=next(iter(self._pending_confirm), None),
        )

    async def refresh_instructions(self) -> bool:
        """Re-render and push instructions if anything changed. Returns True when pushed."""
        composed = self.composer.compose(self._snapshot())
        if composed.fingerprint == self._instructions_fp:
            return False
        self._instructions_fp = composed.fingerprint
        if self._provider:
            await self._provider.update_instructions(composed.text)
        return True

    def _all_flags(self) -> set[str]:
        return self.facts.flags | flags_from_tools(self.pipeline.history)

    def _latency(self, segment: str, a: Watermark, b: Watermark, value_ms: int) -> None:
        self.latency.append(
            LatencySample(
                session_id=self.session_id,
                segment=segment,
                watermark_from=a,
                watermark_to=b,
                value_ms=max(0, value_ms),
                turn_id=self.turn_id,
                provider=self.deps.s2s_config.provider,
            )
        )


class SessionLifecycle(SessionCore):
    """start / close / completion evaluation."""

    async def start(self) -> None:
        self.facts.started_at_ms = self.clock()
        await self.emit(EventType.SESSION_CREATED, {"channel": self.deps.channel.value})
        composed = self.composer.compose(self._snapshot())
        self._instructions_fp = composed.fingerprint
        cfg = self.deps.s2s_config.model_copy(
            update={"instructions": composed.text, "tools": self.composer.provider_tools()}
        )
        self._provider = await self.deps.s2s.open(cfg, self.deps.credential)
        # F-01 (OPS 5.5 audit): push the full session configuration (instructions, tools, voice, formats, turn
        # detection) *before* any client audio can reach the provider. Without this, a live S2S provider runs on its
        # own defaults (different voice/persona, provider VAD auto-responses, no tools) for the whole first
        # utterance, and QEVION's first commit/response.create collide with the provider's own responses.
        # `run()` only starts pumping client frames after `start()` returns, so this ordering is guaranteed.
        await self._provider.update_instructions(composed.text)
        await self.emit(
            EventType.PROVIDER_SESSION_CREATED,
            {"provider": cfg.provider, "model": cfg.model, "instructions_fp": composed.static_fingerprint},
            source=f"provider:s2s:{cfg.provider}",
        )
        await self.dialog_fire("session_started")
        await self.emit(EventType.SESSION_STARTED)
        await self._send(ServerMessageType.READY, payload={"activity_id": self.deps.blueprint.identity.activity_id})
        await self.activity_fire(ActivityTrigger.OPENED, "session started", authority="core")

    async def close(self, reason: str = "closed") -> InteractionRecord:
        if self.record is not None:
            return self.record
        self._closed = True
        self.facts.ended_at_ms = self.clock()
        for fut in self._pending_confirm.values():
            if not fut.done():
                fut.set_result(None)
        if self.dialog.state is not DialogState.CLOSED and self.dialog.can("close"):
            await self._transition(self.dialog.fire("close", self.clock(), reason), push_state=False)
        if not self.activity.terminal:
            await self._finalize_activity(reason)
        if self._provider:
            await self._provider.close()
            await self.emit(EventType.PROVIDER_SESSION_CLOSED)
        self.record = await self.outcome_engine.build(
            store=self.fields,
            tool_history=self.pipeline.history,
            facts=self.facts,
            outcome_id=new_id("out"),
            record_id=new_id("rec"),
        )
        await self.emit(
            EventType.OUTCOME_PRODUCED,
            {"primary": self.record.outcome.primary, "secondary": self.record.outcome.secondary},
        )
        ref = await self.deps.outcome_sink.write_record(self.record)
        await self.emit(EventType.INTERACTION_RECORD_PRODUCED, {"ref": ref})
        await self.emit(EventType.SESSION_ENDED, {"reason": reason, "turns": self.facts.turn_count})
        try:
            await self.deps.transport.close(reason)
        except ConnectionError:
            pass
        return self.record

    async def _finalize_activity(self, reason: str) -> None:
        """Drive the activity machine to a terminal state from facts (never from model text)."""
        verdict = await self.outcome_engine.completion(self.fields, self._all_flags())
        if verdict.exit_rule is not None:
            trig = ActivityTrigger.EXIT_RULE_MET
        elif verdict.failure:
            trig = ActivityTrigger.FAILURE_RULE_MET
        elif verdict.success:
            trig = ActivityTrigger.SUCCESS_RULE_MET
        else:
            trig = ActivityTrigger.USER_LEFT
        for step in (trig, ActivityTrigger.CLOSED):
            t = self.activity.fire_if_possible(step, self.clock(), reason)
            if t:
                t.authority = "core:completion_rules"
                await self._transition(t, push_state=False)
            if self.activity.terminal:
                break

    async def evaluate_completion(self) -> None:
        """Evaluate completion rules from facts after each assistant response (QV-RT-004)."""
        if self.activity.terminal or self._closed:
            return
        verdict = await self.outcome_engine.completion(self.fields, self._all_flags())
        auth = "core:completion_rules"
        if verdict.exit_rule is not None:
            await self.activity_fire(ActivityTrigger.EXIT_RULE_MET, verdict.exit_rule, authority=auth)
        elif verdict.failure:
            await self.activity_fire(ActivityTrigger.FAILURE_RULE_MET, "failure rule", authority=auth)
        elif verdict.success:
            await self.activity_fire(ActivityTrigger.SUCCESS_RULE_MET, "success rule", authority=auth)
        elif self.fields.ready_for_execution() and self.activity.state in (
            ActivityState.COLLECTING,
            ActivityState.ENGAGED,
        ):
            await self.activity_fire(
                ActivityTrigger.FIELDS_COMPLETE, "all required satisfied", authority="core:field_store"
            )
        await self.refresh_instructions()


class SessionTools(SessionLifecycle):
    """Tool round-trips and the only code path that mutates Core state from tool results."""

    async def run_tool(self, call_id: str, tool_id: str, arguments: dict[str, Any]) -> ToolOutcome:
        bp = self.deps.blueprint
        out = await self.pipeline.run(
            ToolCallRequest(call_id=call_id, tool_id=tool_id, arguments=arguments),
            session_id=self.session_id,
            tenant_id=bp.identity.tenant_id,
            activity_id=bp.identity.activity_id,
            turn_id=self.turn_id,
            ts_ms=self.clock(),
        )
        await self._apply_tool_outcome(out, arguments)
        if self._provider and out.error != "confirmation pending":
            await self._provider.send_tool_result(
                ToolCallResult(call_id=call_id, output={**out.output, "status": out.status.value}, error=out.error)
            )
        if self.dialog.state is DialogState.WAITING_TOOL:
            await self.dialog_fire("tool_returned" if out.status is ToolOutcomeStatus.COMPLETED else "tool_failed")
        return out

    async def _apply_tool_outcome(self, out: ToolOutcome, args: dict[str, Any]) -> None:
        """Step 6 COHERE holds by construction: nothing but validated tool outcomes touch the FieldStore."""
        now = self.clock()
        if out.status is not ToolOutcomeStatus.COMPLETED:
            failed = out.status in (ToolOutcomeStatus.FAILED, ToolOutcomeStatus.TIMEOUT, ToolOutcomeStatus.UNKNOWN)
            if failed and self.activity.state is ActivityState.EXECUTING:
                await self.activity_fire(
                    ActivityTrigger.EXECUTION_FAILED, out.status.value, authority="core:tool_pipeline"
                )
            return
        match out.tool_id:
            case PlatformTool.RECORD_FIELD:
                await self._record_field(str(args.get("name", "")), args.get("value"), out)
            case PlatformTool.VERIFY_FIELD:
                name = str(args.get("name", ""))
                if out.output.get("verified") is True and name in self.fields.specs and self.fields.get(name):
                    self.fields.verify(name, tool_call_id=out.call_id, ts_ms=now)
                    await self.emit(EventType.FIELD_VERIFIED, {"name": name, "call_id": out.call_id})
            case PlatformTool.CLARIFY:
                await self.activity_fire(ActivityTrigger.AMBIGUITY, "clarify tool", authority="core:tool_pipeline")
            case PlatformTool.REQUEST_HANDOFF:
                await self.request_handoff(
                    str(args.get("reason", "requested")),
                    str(args.get("destination_ref", "default")),
                    HandoffProposer.MODEL,
                )
            case PlatformTool.COLLECT_QUESTION:
                topic = str(args.get("topic", ""))
                self.facts.coverage_misses.append(
                    CoverageMissEntry(ts_ms=now, topic=topic, behavior_applied="COLLECT_QUESTION")
                )
                await self.emit(EventType.COVERAGE_MISS, {"topic": topic})
            case PlatformTool.SCHEDULE_CALLBACK:
                self.facts.flags.add("callback_scheduled")
            case _:
                pass
        if (
            self.activity.state is ActivityState.EXECUTING
            and out.provenance is Provenance.TOOL_VERIFIED
            and out.output.get("accepted") is True
        ):
            await self.activity_fire(ActivityTrigger.EXECUTED, out.tool_id, authority="core:tool_pipeline")

    async def _record_field(self, name: str, value: Any, out: ToolOutcome) -> None:
        spec = self.fields.specs.get(name)
        if spec is None:
            await self.emit(EventType.FAILURE_CLASSIFIED, {"class": "unknown_field", "name": name})
            return
        res = await self.deps.decision.decide(
            DecisionRequest(
                kind=DecisionKind.VALIDATE_FIELD,
                inputs={
                    "value": value,
                    "type": spec.type,
                    "validation": spec.validation,
                    "enum_values": spec.enum_values,
                },
            )
        )
        await self.emit(
            EventType.DECISION_MADE,
            {"kind": "validate_field", "field": name, "source": res.source.value, "ok": res.value is not None},
        )
        if res.source is DecisionSource.UNKNOWN or res.value is None:
            self.objectives.add(ObjectiveKind.COLLECT_FIELD, name, priority=1, ts_ms=self.clock(), note=res.reason)
            await self.activity_fire(
                ActivityTrigger.FIELD_NEEDED, f"{name} invalid: {res.reason}", authority="core:decision"
            )
            return
        fv = self.fields.record(
            name, res.value, out.provenance, turn_id=self.turn_id, tool_call_id=out.call_id, ts_ms=self.clock()
        )
        self.objectives.complete(ObjectiveKind.COLLECT_FIELD, name)
        if fv.corrected_from is not None:
            await self.emit(EventType.FIELD_CORRECTED, {"name": name, "provenance": fv.provenance.value})
            await self.emit(EventType.USER_CORRECTION, {"field": name})
        else:
            await self.emit(EventType.FIELD_RECORDED, {"name": name, "provenance": fv.provenance.value})
        if spec.type == "entity_ref":
            self.focus.push(str(res.value), name, self.clock(), source="user")
        if self.fields.missing_required():
            await self.activity_fire(ActivityTrigger.FIELD_NEEDED, "more required fields", authority="core:field_store")

    async def request_handoff(self, reason: str, destination_ref: str, proposed_by: HandoffProposer) -> str | None:
        hid = new_id("ho")
        req = HandoffRequest(
            handoff_id=hid,
            session_id=self.session_id,
            tenant_id=self.deps.blueprint.identity.tenant_id,
            activity_id=self.deps.blueprint.identity.activity_id,
            reason=reason,
            proposed_by=proposed_by,
            destination_ref=destination_ref,
            context=ConversationSnapshotRef(
                transcript_digest=_digest("".join(t.text for t in self._responses.values()))["text_sha256_12"],
                fields=self.fields.all(),
                activity_state=self.activity.state.value,
                dialog_state=self.dialog.state.value,
                entity_focus=[e.entity_id for e in self.focus.candidates()],
                turn_count=self.facts.turn_count,
            ),
        )
        await self.emit(
            EventType.HANDOFF_REQUESTED, {"handoff_id": hid, "reason": reason, "destination": destination_ref}
        )
        accepted = True
        if self.deps.handoff_sink:
            res = await self.deps.handoff_sink.handoff(req)
            accepted = res.accepted
            await self.emit(EventType.HANDOFF_ACKNOWLEDGED, {"handoff_id": hid, "accepted": accepted})
        if not accepted:
            return None
        self.facts.handoff_ref = hid
        self.facts.handoff_ids.append(hid)
        self.facts.routing_history.append(
            RouteEntry(ts_ms=self.clock(), target="human", ref=destination_ref, reason=reason)
        )
        await self.emit(EventType.ROUTE_REQUESTED, {"target": "human", "ref": destination_ref})
        await self.activity_fire(ActivityTrigger.HANDOFF, reason, authority="core:handoff")
        return hid


class SessionInterruption(SessionTools):
    """§31 seven-step interruption protocol + confirmation gate (QV-CONF)."""

    def audible_response(self) -> str | None:
        """F-02: the response the user can *currently hear*. A live provider generates audio faster than realtime,
        so `response.done` arrives long before playout ends; the response stays audible until the client reports
        `playout_stopped` (drained / stopped) or, as a safety net for clients that never report, until the
        wall-clock duration of the audio sent (+ grace) has elapsed since playout started."""
        rid = self._audible
        if rid is None:
            return None
        tr = self._responses.get(rid)
        if tr is None or tr.cancelled:
            self._audible = None
            return None
        start = tr.playout_started_ms if tr.playout_started_ms is not None else tr.started_ms
        if tr.done and self.clock() > start + tr.audio_ms_sent + _AUDIBLE_GRACE_MS:
            self._audible = None
            return None
        return rid

    async def interrupt(self, *, onset_ms: int, detected_ms: int | None = None) -> InterruptionRecord | None:
        rid = self._current_response
        late = False
        if self.dialog.state is not DialogState.SPEAKING or rid is None:
            # F-02: barge-in during the audible tail after provider response.done (dialog already LISTENING)
            rid = self.audible_response()
            late = rid is not None
        if rid is None or not self._provider:
            return None
        tr = self._responses[rid]
        rec = InterruptionRecord(
            response_id=rid, t0_user_speech_onset=onset_ms, t1_barge_in_detected=detected_ms or self.clock()
        )
        # 1 DETECT
        await self.emit(
            EventType.INTERRUPTION_DETECTED,
            {"response_id": rid, "audio_ms_sent": tr.audio_ms_sent, "after_generation": late},
        )
        if not late:
            await self.dialog_fire("barge_in", "user speech during assistant response")
        # 2 CANCEL (provider generation only if still running; client playout always)
        self._playout_stopped.clear()
        if not tr.done:
            await self._provider.cancel_response(rid)
        await self._send(ServerMessageType.STOP_PLAYOUT, response_id=rid)
        rec.t2_cancel_sent = self.clock()
        await self.emit(EventType.ASSISTANT_RESPONSE_CANCELLED, {"response_id": rid, "t2_ms": rec.t2_cancel_sent})
        try:
            await asyncio.wait_for(self._playout_stopped.wait(), timeout=_CANCEL_FORCE_MS / 1000)
        except TimeoutError:
            rec.forced = True
            await self.emit(
                EventType.FAILURE_CLASSIFIED, {"class": "playout_stop_timeout", "response_id": rid, "forced": True}
            )
        rec.t3_playout_stopped = self.clock()
        # 3 RECONCILE — keep only what the user plausibly heard; the unheard tail never persists as context.
        tr.cancelled = True
        self._audible = None
        # heard = wall-clock playout time (from client playout_started when known), capped by audio actually sent
        start = tr.playout_started_ms if tr.playout_started_ms is not None else tr.started_ms
        played = max(0, min(tr.audio_ms_sent, rec.t1_barge_in_detected - start))
        rec.played_ms = played
        heard_ratio = 1.0 if tr.audio_ms_sent == 0 else played / tr.audio_ms_sent
        heard_len = int(len(tr.text) * heard_ratio)
        rec.heard_text_len, rec.unheard_text_len = heard_len, len(tr.text) - heard_len
        tr.text = tr.text[:heard_len]
        # F-06: the provider must forget the unheard tail too (text + audio), not only our local copy
        if tr.audio_ms_sent:
            await self._provider.truncate_response(rid, played)
            await self.emit(EventType.ASSISTANT_RESPONSE_TRUNCATED, {"response_id": rid, "audio_end_ms": played})
        rec.t4_state_reconciled = self.clock()
        self.facts.interruption_count += 1
        self.interruptions.append(rec)
        t1 = rec.t1_barge_in_detected
        self._latency(
            "barge_in_to_cancel",
            Watermark.T1_BARGE_IN_DETECTED,
            Watermark.T2_CANCEL_SENT_TO_PROVIDER,
            rec.t2_cancel_sent - t1,
        )
        self._latency(
            "barge_in_to_playout_stop",
            Watermark.T1_BARGE_IN_DETECTED,
            Watermark.T3_PLAYOUT_STOPPED_CLIENT,
            rec.t3_playout_stopped - t1,
        )
        self._latency(
            "barge_in_to_reconciled",
            Watermark.T1_BARGE_IN_DETECTED,
            Watermark.T4_STATE_RECONCILED,
            rec.t4_state_reconciled - t1,
        )
        await self.emit(
            EventType.LATENCY_SAMPLE,
            {
                "segment": "interruption",
                "response_id": rid,
                "t0": rec.t0_user_speech_onset,
                "t1": t1,
                "t2": rec.t2_cancel_sent,
                "t3": rec.t3_playout_stopped,
                "t4": rec.t4_state_reconciled,
                "forced": rec.forced,
                "heard_len": heard_len,
                "unheard_len": rec.unheard_text_len,
            },
        )
        self._current_response = None
        # 4 ACCEPT → caller commits the new turn (5); FieldStore untouched by construction (6); provider responds (7).
        return rec

    async def _provider_cancel(self, rid: str) -> None:
        if self._provider:
            await self._provider.cancel_response(rid)

    def heard_context(self) -> list[str]:
        """What the user actually heard (QV-INT-002) — reconciled assistant text per response."""
        return [t.text for t in self._responses.values() if t.text]

    # ------------------------------------------------------------------ confirmation gate
    async def _confirm_tool(self, inv: ToolInvocation) -> bool | None:
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[bool | None] = loop.create_future()
        self._pending_confirm[inv.call_id] = fut
        await self.activity_fire(
            ActivityTrigger.CONFIRM_NEEDED, f"tool {inv.tool_id}", authority="core:confirmation_gate"
        )
        await self.dialog_fire("confirmation_needed")
        await self._send(
            ServerMessageType.CONFIRMATION_REQUEST,
            payload={"call_id": inv.call_id, "tool_id": inv.tool_id, "arguments": inv.arguments},
        )
        try:
            result = await asyncio.wait_for(fut, timeout=self.deps.confirmation_timeout_ms / 1000)
        except TimeoutError:
            result = None
        finally:
            self._pending_confirm.pop(inv.call_id, None)
        auth = "core:confirmation_interpreter"
        if result is True:
            await self.activity_fire(ActivityTrigger.CONFIRMED, "user confirmed", authority=auth)
            await self.dialog_fire("confirmed")
        elif result is False:
            await self.activity_fire(ActivityTrigger.DENIED, "user denied", authority=auth)
            await self.dialog_fire("denied")
        elif self.dialog.state is DialogState.WAITING_CONFIRMATION:
            await self.dialog_fire("end_of_turn", "confirmation timeout")
        return result

    def resolve_confirmation(self, call_id: str, granted: bool | None) -> bool:
        fut = self._pending_confirm.get(call_id)
        if fut is None or fut.done():
            return False
        fut.set_result(granted)
        return True

    async def resolve_confirmation_from_text(self, text: str) -> bool:
        """Interpret a spoken/typed answer to a pending confirmation. Ambiguous → re-ask, never guess."""
        if not self._pending_confirm:
            return False
        res = await self.confirmer.interpret(text)
        await self.emit(
            EventType.DECISION_MADE,
            {
                "kind": "interpret_confirmation",
                "source": res.source.value,
                "value": res.value,
                "confidence": res.confidence,
            },
        )
        call_id = next(iter(self._pending_confirm))
        if res.ambiguous:
            await self.activity_fire(
                ActivityTrigger.AMBIGUITY, "ambiguous confirmation", authority="core:confirmation_interpreter"
            )
            await self.emit(EventType.USER_SPEECH_DISCARDED, {"reason": "ambiguous confirmation; re-ask"})
            return True
        return self.resolve_confirmation(call_id, res.value)


class Session(SessionInterruption):
    """The public orchestrator. Drive with `run()` (full loop) or the granular `handle_*` methods (tests/replay)."""

    # ------------------------------------------------------------------ user input
    def _new_turn(self) -> str:
        self._turn_no += 1
        self.turn_id = f"turn_{self._turn_no}"
        self.facts.turn_count = self._turn_no
        now = self.clock()
        if self.facts.first_user_turn_ms is None:
            self.facts.first_user_turn_ms = now
        self.facts.last_user_turn_ms = now
        return self.turn_id

    async def _begin_user_turn(self, channel: str, extra: dict[str, Any]) -> str:
        if self.dialog.state is DialogState.INTERRUPTED:
            await self.dialog_fire("reconciled")
        tid = self._new_turn()
        await self.emit(EventType.TURN_STARTED, {"channel": channel})
        await self.emit(EventType.USER_SPEECH_COMMITTED, {"turn_id": tid, **extra})
        return tid

    async def _after_user_turn(self) -> None:
        await self.activity_fire(ActivityTrigger.USER_ENGAGED, "user turn", authority="core")
        if self.fields.missing_required() and self.activity.state is ActivityState.ENGAGED:
            await self.activity_fire(ActivityTrigger.FIELD_NEEDED, "required fields missing", authority="core")
        await self.refresh_instructions()

    async def handle_text(self, text: str) -> None:
        """Text channel input == a committed user turn."""
        if self._closed or not self._provider:
            return
        if self.dialog.state is DialogState.SPEAKING or self.audible_response() is not None:
            await self.interrupt(onset_ms=self.clock())
        if self.dialog.state is DialogState.WAITING_CONFIRMATION and self._pending_confirm:
            await self.resolve_confirmation_from_text(text)
            return
        tid = await self._begin_user_turn("text", _digest(text))
        await self.dialog_fire("text_received")
        await self._after_user_turn()
        await self._provider.send_text(text)
        await self.emit(EventType.TURN_ENDED, {"turn_id": tid})

    async def handle_audio(self, pcm16: bytes, ref: AudioFrameRef) -> None:
        """Audio frame from transport: turn plane first (authoritative), then forward to provider."""
        if self._closed or not self._provider:
            return
        # F-02: the turn plane must know the user can still *hear* the agent after provider generation ended
        speaking = self.dialog.state is DialogState.SPEAKING or self.audible_response() is not None
        for tev in self.deps.turn.push(pcm16, self.clock(), speaking):
            await self.handle_turn_event(tev)
        await self._provider.send_audio(pcm16, ref)

    async def handle_turn_event(self, tev: TurnEvent) -> None:
        src = f"turn:{tev.detector}"
        match tev.type:
            case TurnEventType.SPEECH_START:
                self._speech_onset_ms = tev.ts_ms
                await self.emit(EventType.USER_SPEECH_STARTED, {"detector": tev.detector}, source=src)
            case TurnEventType.BARGE_IN:
                await self.emit(EventType.USER_SPEECH_STARTED, {"detector": tev.detector, "barge_in": True}, source=src)
                await self.interrupt(onset_ms=self._speech_onset_ms or tev.ts_ms, detected_ms=tev.ts_ms)
            case TurnEventType.END_OF_TURN:
                if self._speech_onset_ms is not None:
                    self._latency(
                        "speech_onset_to_commit",
                        Watermark.T0_USER_SPEECH_ONSET,
                        Watermark.USER_SPEECH_END,
                        tev.ts_ms - self._speech_onset_ms,
                    )
                self._speech_onset_ms = None
                await self._begin_user_turn("audio", {"speech_ms": tev.speech_ms})
                await self.dialog_fire("end_of_turn")
                await self._after_user_turn()
                if self._provider:
                    await self._provider.commit_input()
            case TurnEventType.NOISE_REJECTED:
                await self.emit(EventType.USER_SPEECH_DISCARDED, {"reason": "noise"}, source=src)
                self._speech_onset_ms = None
            case _:
                pass

    async def handle_client_message(self, msg: ClientMessage) -> None:
        match msg.type:
            case ClientMessageType.TEXT:
                await self.handle_text(msg.text or "")
            case ClientMessageType.CONFIRM:
                if msg.call_id:
                    self.resolve_confirmation(msg.call_id, msg.granted)
            case ClientMessageType.PLAYOUT_STOPPED:
                self._playout_stopped.set()
                await self.emit(
                    EventType.TRANSPORT_PLAYOUT_STOPPED,
                    {"response_id": msg.response_id, "client_ts_ms": msg.client_ts_ms},
                )
                # F-02: client finished (drained) or stopped playout → the agent is no longer audible
                if self._audible is not None and (msg.response_id in (None, self._audible)):
                    ended = self._audible
                    self._audible = None
                    await self.emit(EventType.ASSISTANT_PLAYOUT_ENDED, {"response_id": ended})
            case ClientMessageType.PLAYOUT_STARTED:
                tr0 = self._responses.get(msg.response_id or "")
                if tr0 is not None and tr0.playout_started_ms is None:
                    tr0.playout_started_ms = self.clock()
                await self.emit(EventType.TRANSPORT_PLAYOUT_STARTED, {"response_id": msg.response_id})
            case ClientMessageType.AUDIO_COMMIT:
                await self.handle_turn_event(
                    TurnEvent(type=TurnEventType.END_OF_TURN, ts_ms=self.clock(), detector="client")
                )
            case ClientMessageType.BYE:
                await self.close("user_bye")
            case ClientMessageType.PING:
                await self._send(ServerMessageType.PONG)
            case _:
                pass

    # ------------------------------------------------------------------ provider events
    async def handle_provider_event(self, ev: S2SEvent) -> None:
        src = f"provider:s2s:{self.deps.s2s_config.provider}"
        rid = ev.response_id or ""
        match ev.type:
            case S2SEventType.RESPONSE_STARTED:
                rid = rid or new_id("resp")
                if self.dialog.state is DialogState.INTERRUPTED:
                    # F-04: the provider started a response while we are still reconciling a barge-in (the user is
                    # mid-utterance). Its audio would contradict the dialog state; cancel it and never forward it.
                    self._responses[rid] = ResponseTrack(response_id=rid, started_ms=self.clock(), cancelled=True)
                    await self._provider_cancel(rid)
                    await self.emit(
                        EventType.ASSISTANT_RESPONSE_CANCELLED,
                        {"response_id": rid, "reason": "started_while_interrupted"},
                        source=src,
                    )
                    return
                self._responses[rid] = ResponseTrack(response_id=rid, started_ms=self.clock())
                self._current_response = rid
                self._audible = rid
                self._playout_stopped.clear()
                await self.emit(EventType.ASSISTANT_RESPONSE_STARTED, {"response_id": rid}, source=src)
                await self.dialog_fire("response_started")
                await self._send(ServerMessageType.AUDIO_START, response_id=rid)
            case S2SEventType.RESPONSE_TEXT_DELTA:
                tr = self._responses.get(rid)
                if tr and not tr.cancelled:
                    tr.text += ev.text or ""
            case S2SEventType.RESPONSE_AUDIO_DELTA:
                tr = self._responses.get(rid)
                if tr and not tr.cancelled and ev.audio:
                    tr.audio_ms_sent += ev.audio.duration_ms
            case S2SEventType.RESPONSE_TOOL_CALL:
                trc = self._responses.get(rid)
                if trc is not None and trc.cancelled:
                    # F-04: never execute tools requested by a response we cancelled / refused
                    await self.emit(
                        EventType.FAILURE_CLASSIFIED,
                        {"class": "tool_call_from_cancelled_response", "response_id": rid},
                    )
                    return
                if ev.tool_call:
                    await self.dialog_fire("tool_requested")
                    await self.run_tool(ev.tool_call.call_id, ev.tool_call.tool_id, ev.tool_call.arguments)
            case S2SEventType.RESPONSE_DONE:
                tr = self._responses.get(rid)
                if tr and tr.cancelled and rid != self._current_response:
                    # F-04: a response we refused (started while INTERRUPTED) / already cancelled — no client
                    # messages, no dialog transitions (it never owned the dialog)
                    tr.done = True
                    return
                if tr:
                    tr.done = True
                    if tr.audio_ms_sent == 0 and self._audible == rid:
                        self._audible = None  # silent (tool-only) response: nothing is audible
                    await self.emit(
                        EventType.ASSISTANT_RESPONSE_ENDED,
                        {"response_id": tr.response_id, "audio_ms": tr.audio_ms_sent, **_digest(tr.text)},
                        source=src,
                    )
                    await self._send(ServerMessageType.AUDIO_END, response_id=tr.response_id)
                if self._current_response == rid:
                    self._current_response = None
                if self.dialog.state is DialogState.SPEAKING:
                    await self.dialog_fire("response_done")
                elif self.dialog.state is DialogState.THINKING:
                    await self.dialog_fire("nothing_to_say")
                await self.evaluate_completion()
            case S2SEventType.RESPONSE_CANCELLED:
                tr = self._responses.get(rid)
                if tr:
                    tr.cancelled = True
                self._playout_stopped.set()
            case S2SEventType.INPUT_TRANSCRIPT:
                await self.emit(
                    EventType.USER_SPEECH_COMMITTED, {"transcript": True, **_digest(ev.text or "")}, source=src
                )
            case S2SEventType.ERROR:
                err = ev.error
                fatal = err.fatal if err else True
                await self.emit(
                    EventType.PROVIDER_ERROR,
                    {
                        "code": err.code if err else "unknown",
                        "provider_code": err.provider_code if err else None,
                        "retryable": bool(err and err.retryable),
                        "fatal": fatal,
                        # provider protocol text only (never user content / secrets); bounded
                        "message": (err.message if err else "")[:200],
                    },
                    source=src,
                )
                # F-05: a rejected single request (protocol race) must not block the Activity or turn the outcome
                # into technical_failure; only errors the adapter marks fatal do.
                if fatal and not (err and err.retryable):
                    await self.activity_fire(ActivityTrigger.BLOCKED, "provider error", authority="core")
                else:
                    await self.emit(
                        EventType.FAILURE_CLASSIFIED,
                        {"class": "provider_request_rejected", "provider_code": err.provider_code if err else None},
                    )
            case S2SEventType.CLOSED:
                if not self._closed:
                    await self.close("provider_closed")
            case _:
                pass

    # ------------------------------------------------------------------ run loop
    async def run(self) -> InteractionRecord:
        await self.start()
        provider = self._provider
        assert provider is not None  # noqa: S101 — start() always opens the provider

        async def pump_provider() -> None:
            async for ev in provider.events():
                await self.handle_provider_event(ev)
                if self._closed:
                    return

        async def pump_audio_out() -> None:
            async for _ref, pcm in provider.audio_out():
                rid = self._current_response
                if rid and not self._responses[rid].cancelled:
                    try:
                        await self.deps.transport.send_audio(rid, pcm)
                    except ConnectionError:
                        return

        async def pump_client() -> None:
            fmt = self.deps.s2s_config.input_format
            async for item in self.deps.transport.incoming():
                if isinstance(item, bytes):
                    dur = int(len(item) / 2 / fmt.sample_rate_hz * 1000)
                    ref = AudioFrameRef(frame_id=new_id("frm"), byte_length=len(item), duration_ms=dur, fmt=fmt)
                    await self.handle_audio(item, ref)
                else:
                    await self.handle_client_message(item)
                if self._closed:
                    return
            if not self._closed:
                await self.emit(EventType.TRANSPORT_DISCONNECTED, {"reason": "client eof"})
                await self.close("client_disconnected")

        tasks = [
            asyncio.create_task(pump_provider()),
            asyncio.create_task(pump_audio_out()),
            asyncio.create_task(pump_client()),
        ]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            if not self._closed:
                await self.close("pump_finished")
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        assert self.record is not None  # noqa: S101 — close() always sets the record
        return self.record


__all__ = ["InterruptionRecord", "Session", "SessionDeps"]
