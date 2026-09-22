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
            await self.activity_fire(ActivityTrigger.FIELDS_COMPLETE, "all required satisfied", authority="core:field_store")
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
                await self.activity_fire(ActivityTrigger.EXECUTION_FAILED, out.status.value, authority="core:tool_pipeline")
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
                    str(args.get("reason", "requested")), str(args.get("destination_ref", "default")), HandoffProposer.MODEL
                )
            case PlatformTool.COLLECT_QUESTION:
                topic = str(args.get("topic", ""))
                self.facts.coverage_misses.append(CoverageMissEntry(ts_ms=now, topic=topic, behavior_applied="COLLECT_QUESTION"))
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
                inputs={"value": value, "type": spec.type, "validation": spec.validation, "enum_values": spec.enum_values},
            )
        )
        await self.emit(
            EventType.DECISION_MADE,
            {"kind": "validate_field", "field": name, "source": res.source.value, "ok": res.value is not None},
        )
        if res.source is DecisionSource.UNKNOWN or res.value is None:
            self.objectives.add(ObjectiveKind.COLLECT_FIELD, name, priority=1, ts_ms=self.clock(), note=res.reason)
            await self.activity_fire(ActivityTrigger.FIELD_NEEDED, f"{name} invalid: {res.reason}", authority="core:decision")
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
        await self.emit(EventType.HANDOFF_REQUESTED, {"handoff_id": hid, "reason": reason, "destination": destination_ref})
        accepted = True
        if self.deps.handoff_sink:
            res = await self.deps.handoff_sink.handoff(req)
            accepted = res.accepted
            await self.emit(EventType.HANDOFF_ACKNOWLEDGED, {"handoff_id": hid, "accepted": accepted})
        if not accepted:
            return None
        self.facts.handoff_ref = hid
        self.facts.handoff_ids.append(hid)
        self.facts.routing_history.append(RouteEntry(ts_ms=self.clock(), target="human", ref=destination_ref, reason=reason))
        await self.emit(EventType.ROUTE_REQUESTED, {"target": "human", "ref": destination_ref})
        await self.activity_fire(ActivityTrigger.HANDOFF, reason, authority="core:handoff")
        return hid


# --- part 5 ---
