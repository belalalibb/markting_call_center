"""In-memory runtime state for the P3 POC (A7). Everything here is replaceable by a DB adapter later.

The runtime imports core/control/knowledge/adapters — never copilot (import-linter: Copilot ≠ runtime).
Copilot is exposed via a *separate* app module (`qevion.copilot.api`) mounted by the composition root.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from qevion.adapters.decision.rules import RulesDecisionAdapter
from qevion.adapters.decision.typesafe import LayeredDecisionAdapter, TypeSafeDecisionAdapter
from qevion.adapters.providers.mocks import MockS2SAdapter, MockScriptStep
from qevion.adapters.providers.openai_realtime import OpenAIRealtimeAdapter
from qevion.adapters.sinks.memory import MemoryHandoffSink, MemoryOutcomeSink
from qevion.adapters.telephony.simulated import SimCallState, SimulatedTelephonyAdapter
from qevion.adapters.tools.memory_backend import MemoryStore, memory_backends
from qevion.adapters.turn.energy import EnergyTurnAdapter, MockTurnAdapter
from qevion.adapters.turn.silero import SileroTurnAdapter
from qevion.adapters.turn.smart_turn import SmartTurnAdapter
from qevion.admin.credentials import EnvAdminEphemeralResolver
from qevion.contracts.activity import ActivityBlueprint, ReadinessState
from qevion.contracts.common import Channel, Direction, new_id
from qevion.contracts.composition import Composition
from qevion.contracts.control import PreflightResult
from qevion.contracts.event import Event
from qevion.contracts.knowledge import KnowledgeSource, SourceKind
from qevion.contracts.provider import ProviderRole, S2SSessionConfig, ToolCallRequest
from qevion.contracts.simulation import ActivationThresholds, ScenarioCase, SimulationReport
from qevion.contracts.tenant import LocalePack, Tenant, VoiceProfile
from qevion.contracts.transport import ServerMessage, ServerMessageType
from qevion.control.capabilities import CapabilityMapper, RequirementMapping, build_registry
from qevion.control.contact_policy import ContactDecision, ContactState, evaluate_contact
from qevion.control.preflight import Preflight, PreflightContext
from qevion.control.readiness import (
    ActivationGates,
    IllegalReadinessTransitionError,
    ReadinessChange,
    ReadinessMachine,
)
from qevion.core.platform_tools import declarations_for_blueprint_permissions, platform_declarations
from qevion.core.session import Session, SessionDeps
from qevion.knowledge.pipeline import IngestionReport, KnowledgePipeline, KnowledgeStore
from qevion.simulation.cases import default_cases
from qevion.simulation.runner import ScenarioRunner, SimulationDeps

ROOT = Path(__file__).resolve().parents[2]


@dataclass
class OutboundAttempt:
    """One outbound contact attempt: hook decision → (dial → session) — auditable even when refused."""

    attempt_id: str
    activity_key: str
    contact_ref: str
    decision: ContactDecision
    call_id: str | None = None
    call_state: str | None = None
    session_id: str | None = None
    created_at: float = field(default_factory=time.time)

    def payload(self) -> dict[str, Any]:
        return {
            "attempt_id": self.attempt_id,
            "activity_key": self.activity_key,
            "contact_ref": self.contact_ref,
            "contact_decision": self.decision.payload(),
            "call_id": self.call_id,
            "call_state": self.call_state,
            "session_id": self.session_id,
        }


@dataclass
class ActivityRecord:
    blueprint: ActivityBlueprint
    readiness: ReadinessMachine
    preflight: PreflightResult | None = None
    simulation: SimulationReport | None = None
    preflight_ref: str | None = None
    mapping: list[RequirementMapping] = field(default_factory=list)
    changes: list[ReadinessChange] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.blueprint.identity.activity_id}@{self.blueprint.identity.version}"


@dataclass
class LiveSession:
    session_id: str
    activity_key: str
    session: Session
    events: list[Event] = field(default_factory=list)
    task: asyncio.Task[Any] | None = None
    handoffs: MemoryHandoffSink = field(default_factory=MemoryHandoffSink)
    outcomes: MemoryOutcomeSink = field(default_factory=MemoryOutcomeSink)
    composition_id: str = ""
    credential_source: str = "none"
    decision_credential_source: str = "none"
    turn_detector: str = ""
    error: str | None = None
    outbound_attempt_id: str | None = None
    close_code: int | None = None  # WS close code observed by the server pump (1000 = clean; 1011 = keepalive)
    close_reason: str = ""
    heartbeat: dict[str, Any] = field(default_factory=dict)  # sent / last_rtt_ms / dropped_audio_frames
    tenant_id: str = ""


class RuntimeStore:
    """Composition root state. Single process, in-memory."""

    def __init__(self) -> None:
        # F-13: live transcripts to the operator console (connected client only, never persisted). Default ON in
        # development; set QEVION_OPERATOR_TRANSCRIPTS=0 for deployments where operators must not see caller text.
        self.operator_transcripts = os.environ.get("QEVION_OPERATOR_TRANSCRIPTS", "1") != "0"
        self.mock_fast_generation = False
        self.tenants: dict[str, Tenant] = {}
        self.activities: dict[str, ActivityRecord] = {}
        self.knowledge = KnowledgeStore()
        self.pipeline = KnowledgePipeline(self.knowledge)
        self.reports: dict[str, IngestionReport] = {}
        self.credentials = EnvAdminEphemeralResolver()
        self.sessions: dict[str, LiveSession] = {}
        # F-12: bounded in-memory telemetry. `event_log` is a ring buffer addressed by an absolute offset
        # (`event_log_base` = number of events already dropped) so `/api/events?since=` stays monotonic.
        self.event_log: list[Event] = []
        self.event_log_base = 0
        self.max_events = int(os.environ.get("QEVION_MAX_EVENTS", "50000"))
        self.max_sessions = int(os.environ.get("QEVION_MAX_SESSIONS", "200"))
        self.max_session_events = int(os.environ.get("QEVION_MAX_SESSION_EVENTS", "5000"))
        self.compositions: dict[str, Composition] = _load_dir(
            ROOT / "config/compositions", Composition, "composition_id"
        )
        self.telephony = SimulatedTelephonyAdapter()
        self.contacts: dict[str, ContactState] = {}
        self.outbound_attempts: list[OutboundAttempt] = []
        self.default_composition_id = "comp_mock_s2s_v1"
        self.composition = self.compositions[self.default_composition_id]
        self._s2s = MockS2SAdapter([])
        self._turn = EnergyTurnAdapter()
        self._decision = RulesDecisionAdapter()
        # adapter registry by (role, name) — compositions bind by these names
        self.s2s_adapters: dict[str, Any] = {"mock": self._s2s, "openai_realtime": OpenAIRealtimeAdapter()}
        self.turn_adapters: dict[str, Any] = {
            "energy": self._turn,
            "mock": MockTurnAdapter(),
            "silero": SileroTurnAdapter(),
            "smart_turn": SmartTurnAdapter(),
        }
        self._typesafe = TypeSafeDecisionAdapter()  # credential injected per session from the resolver
        self.decision_adapters: dict[str, Any] = {
            "rules": self._decision,
            "typesafe": self._typesafe,
            "rules+typesafe": LayeredDecisionAdapter(self._decision, self._typesafe),
        }
        self.locale_packs: dict[str, LocalePack] = _load_dir(ROOT / "config/locale_packs", LocalePack, "locale_pack_id")
        self.voice_profiles: dict[str, VoiceProfile] = _load_dir(
            ROOT / "config/voice_profiles", VoiceProfile, "voice_profile_id"
        )
        self.tool_declarations = platform_declarations()
        self.registry = build_registry(
            [*self.s2s_adapters.values(), *self.turn_adapters.values(), *self.decision_adapters.values()],
            tool_declarations=self.tool_declarations,
            locale_packs=self.locale_packs,
            voice_profiles=self.voice_profiles,
            channels=[Channel.TEXT, Channel.BROWSER_VOICE],
        )
        self.tool_store = MemoryStore()

    # ---------------------------------------------------------------- tenants
    def upsert_tenant(self, t: Tenant) -> Tenant:
        self.tenants[t.tenant_id] = t
        return t

    # ------------------------------------------------------------- activities
    def put_activity(self, bp: ActivityBlueprint) -> ActivityRecord:
        rec = ActivityRecord(blueprint=bp, readiness=ReadinessMachine.from_blueprint(bp))
        self.activities[rec.key] = rec
        return rec

    def get_activity(self, key: str) -> ActivityRecord:
        try:
            return self.activities[key]
        except KeyError as e:
            raise KeyError(f"activity {key} not found") from e

    def preflight_ctx(self, bp: ActivityBlueprint, *, strict: bool) -> PreflightContext:
        tenant = self.tenants.get(bp.identity.tenant_id)
        return PreflightContext(
            registry=self.registry,
            composition=self.composition,
            tenant=tenant,
            tool_declarations=declarations_for_blueprint_permissions(bp.tools.permissions),
            locale_packs=self.locale_packs,
            voice_profiles=self.voice_profiles,
            knowledge_conflicts=[
                c.contradiction_id for c in self.knowledge.unresolved_conflicts(bp.identity.tenant_id)
            ],
            strict_capabilities=strict,
        )

    def run_preflight(self, key: str, *, strict: bool = False, actor: str = "api") -> ActivityRecord:
        rec = self.get_activity(key)
        result = Preflight(self.preflight_ctx(rec.blueprint, strict=strict)).run(rec.blueprint)
        rec.preflight = result
        ref = f"preflight:{hashlib.sha256(result.model_dump_json().encode()).hexdigest()[:12]}"
        rec.preflight_ref = ref
        try:
            change = rec.readiness.apply_preflight(result, ref=ref, actor=actor)
        except IllegalReadinessTransitionError as e:
            # e.g. ACTIVE version re-checked: result is stored, lifecycle untouched (immutability)
            rec.notes.append(f"preflight_not_applied: {e}")
            change = None
        if change is not None:
            rec.changes.append(change)
        return rec

    def map_capabilities(self, key: str) -> list[RequirementMapping]:
        rec = self.get_activity(key)
        rec.mapping = CapabilityMapper(self.registry, self.composition).map_requirements(rec.blueprint)
        return rec.mapping

    # -------------------------------------------------------------- simulation + activation (P5)
    async def run_simulation(
        self,
        key: str,
        *,
        cases: list[ScenarioCase] | None = None,
        thresholds: ActivationThresholds | None = None,
        actor: str = "api",
    ) -> ActivityRecord:
        """QV-SIM: same Core on the mock composition; report drives READY_FOR_ACTIVATION / SIMULATION_FAILED."""
        rec = self.get_activity(key)
        bp = rec.blueprint
        runner = ScenarioRunner(bp, SimulationDeps(composition_id=self.default_composition_id))
        report = await runner.run(cases or default_cases(bp), thresholds=thresholds)
        rec.simulation = report
        ref = f"simulation:{report.report_id}"
        try:
            change = rec.readiness.apply_simulation(report.passed, ref=ref, actor=actor)
        except IllegalReadinessTransitionError as e:
            rec.notes.append(f"simulation_not_applied: {e}")
            change = None
        if change is not None:
            rec.changes.append(change)
        return rec

    # -------------------------------------------------------------- outbound seam (P5, QV-OUT-DIR)
    def contact_state(self, contact_ref: str) -> ContactState:
        return self.contacts.setdefault(contact_ref, ContactState(contact_ref=contact_ref))

    def check_contact(self, key: str, contact_ref: str) -> ContactDecision:
        bp = self.get_activity(key).blueprint
        return evaluate_contact(bp.policies.contact_policy_hooks, self.contact_state(contact_ref))

    async def outbound_attempt(
        self, key: str, contact_ref: str, *, transport: Any, session_id: str | None = None
    ) -> OutboundAttempt:
        """QV-OUT-DIR-001/002: hooks first (a refusal is a recorded attempt, no dial), then dial via the
        telephony seam, then a normal Session on the default composition — same Core, direction=outbound."""
        rec = self.get_activity(key)
        bp = rec.blueprint
        if bp.direction is Direction.INBOUND:
            raise ValueError("activity is inbound-only")
        state = self.contact_state(contact_ref)
        decision = evaluate_contact(bp.policies.contact_policy_hooks, state)
        attempt = OutboundAttempt(
            attempt_id=new_id("att"), activity_key=key, contact_ref=contact_ref, decision=decision
        )
        self.outbound_attempts.append(attempt)
        if not decision.allowed:
            return attempt
        state.attempts += 1
        call_id = await self.telephony.dial(bp.identity.tenant_id, contact_ref, bp.identity.activity_id)
        attempt.call_id = call_id
        attempt.call_state = self.telephony.state(call_id).value
        if self.telephony.state(call_id) is not SimCallState.ANSWERED:
            return attempt
        sid = session_id or new_id("ses")
        live = self.build_session(activity_key=key, transport=transport, session_id=sid, channel=Channel.BROWSER_VOICE)
        live.outbound_attempt_id = attempt.attempt_id
        attempt.session_id = sid
        return attempt

    def activation_gates(self, key: str) -> ActivationGates:
        rec = self.get_activity(key)
        bp = rec.blueprint
        return ActivationGates(
            schema_valid=True,  # a stored ActivityBlueprint already passed contract validation
            preflight=rec.preflight,
            simulation_passed=None if rec.simulation is None else rec.simulation.passed,
            all_decisions_approved=not bp.unapproved_decisions(),
            version_frozen=rec.readiness.state.value in ("READY_FOR_ACTIVATION", "ACTIVE", "SUSPENDED"),
        )

    def activate(self, key: str, *, actor: str) -> ReadinessChange:
        """QV-LIFE-002: refuses unless every gate is satisfied; the refusal names the unmet gates."""
        rec = self.get_activity(key)
        gates = self.activation_gates(key)
        change = rec.readiness.activate(
            gates,
            actor=actor,
            preflight_ref=rec.preflight_ref or "",
            simulation_ref=f"simulation:{rec.simulation.report_id}" if rec.simulation else "",
        )
        rec.changes.append(change)
        return change

    def transition(self, key: str, dst: ReadinessState, *, reason: str, actor: str) -> ReadinessChange:
        rec = self.get_activity(key)
        change = rec.readiness.transition(dst, reason=reason, actor=actor)
        rec.changes.append(change)
        return change

    # -------------------------------------------------------------- knowledge
    def ingest(
        self,
        *,
        tenant_id: str,
        name: str,
        data: bytes,
        mime_type: str | None,
        activity_key: str | None,
        priority: int = 100,
    ) -> IngestionReport:
        sid = f"src_{hashlib.sha256(data).hexdigest()[:10]}"
        kind = (
            SourceKind.STRUCTURED
            if (mime_type or "").split("/")[-1] in {"csv", "json", "yaml", "x-yaml"}
            else SourceKind.FILE
        )
        src = KnowledgeSource(
            source_id=sid,
            tenant_id=tenant_id,
            kind=kind,
            name=name,
            mime_type=mime_type,
            priority=priority,
            sha256=hashlib.sha256(data).hexdigest(),
        )
        bp = self.get_activity(activity_key).blueprint if activity_key else None
        report = self.pipeline.ingest(src, data, activity=bp)
        self.reports[sid] = report
        return report

    # ------------------------------------------------------------ compositions
    def composition_for(self, bp: ActivityBlueprint, override: str | None = None) -> Composition:
        """Resolution: explicit id → `"pinned"` (blueprint's `version_metadata.pinned.composition_config`) →
        runtime default. The pin is *not* applied implicitly: a pinned real provider must be an explicit
        operator choice per session (and needs a resolved credential), never a side effect of a test run."""
        cid = override or self.default_composition_id
        if cid == "pinned":
            cid = bp.version_metadata.pinned.composition_config or self.default_composition_id
        comp = self.compositions.get(cid)
        if comp is None:
            raise KeyError(f"composition {cid!r} not found")
        return comp

    # ---------------------------------------------------------------- sessions
    def build_session(
        self,
        *,
        activity_key: str,
        transport: Any,
        session_id: str,
        channel: Channel,
        script: list[MockScriptStep] | None = None,
        composition_id: str | None = None,
    ) -> LiveSession:
        rec = self.get_activity(activity_key)
        bp = rec.blueprint
        live = LiveSession(session_id=session_id, activity_key=activity_key, session=None)  # type: ignore[arg-type]
        live.tenant_id = bp.identity.tenant_id

        async def sink(ev: Event) -> None:
            live.events.append(ev)
            if len(live.events) > self.max_session_events:
                del live.events[: len(live.events) - self.max_session_events]
            self.log_event(ev)
            if ev.type in FORWARDED_EVENT_TYPES:
                # Filtered mirror to the client (ServerMessageType.EVENT): operator-facing telemetry only,
                # never transcripts/audio/secrets (QV-EVT-003). Transport failures must not break the session.
                try:
                    await transport.send(
                        ServerMessage(
                            type=ServerMessageType.EVENT,
                            session_id=session_id,
                            server_ts_ms=int(time.time() * 1000),
                            payload={"seq": ev.seq, "type": ev.type, "source": ev.source, "payload": ev.payload},
                        )
                    )
                except (ConnectionError, RuntimeError):
                    pass

        comp = self.composition_for(bp, composition_id)
        s2s_b = next(b for b in comp.bindings if b.role is ProviderRole.S2S)
        turn_b = next((b for b in comp.bindings if b.role is ProviderRole.TURN), None)
        dec_b = next((b for b in comp.bindings if b.role is ProviderRole.DECISION), None)
        s2s = self.s2s_adapters.get(s2s_b.adapter)
        if s2s is None:
            raise KeyError(f"s2s adapter {s2s_b.adapter!r} not registered")
        if s2s_b.adapter == "mock":
            # Voice channels get realtime-paced mock audio so playout/interruption behave like a live provider.
            # `mock_fast_generation` (tests / audit probes) mimics a live provider that generates audio faster than
            # realtime, so provider `response.done` arrives while the client is still playing (F-02).
            s2s = MockS2SAdapter(
                script or _default_script(bp),
                realtime=channel is Channel.BROWSER_VOICE and not self.mock_fast_generation,
            )
        turn_ad = self.turn_adapters.get(turn_b.adapter if turn_b else "energy", self._turn)
        decision = self.decision_adapters.get(dec_b.adapter if dec_b else "rules", self._decision)
        credential, cred_src = self.credentials.resolve(s2s_b.adapter, bp.identity.tenant_id)
        live.composition_id = comp.composition_id
        live.credential_source = cred_src.value
        if dec_b is not None and "typesafe" in dec_b.adapter:
            # decision-provider credential is resolved separately from the s2s one; never logged
            ts_cred, ts_src = self.credentials.resolve("typesafe", bp.identity.tenant_id)
            self._typesafe.set_credential(ts_cred)
            if dec_b.model:
                self._typesafe.model = dec_b.model
            live.decision_credential_source = ts_src.value
        voice = None
        if bp.locale.voice_profile_ref and bp.locale.voice_profile_ref in self.voice_profiles:
            voice = self.voice_profiles[bp.locale.voice_profile_ref].provider_voice_map.get(s2s_b.adapter)
        turn_det = turn_ad.new_detector()
        turn_det.configure(comp.turn)
        live.turn_detector = str(getattr(turn_det, "detector_name", type(turn_det).__name__))
        deps = SessionDeps(
            blueprint=bp,
            s2s=s2s,
            s2s_config=S2SSessionConfig(
                provider=s2s_b.adapter,
                model=s2s_b.model or "mock-1",
                voice=voice,
                language_hint=bp.locale.locale,
                extra={k: v for k, v in s2s_b.config.items() if k in ("transcription_model",)},
                tools=[
                    d.model_dump(mode="json")
                    for d in declarations_for_blueprint_permissions(bp.tools.permissions).values()
                ],
            ),
            transport=transport,
            turn=turn_det,
            decision=decision,
            tool_declarations=declarations_for_blueprint_permissions(bp.tools.permissions),
            tool_backends=dict(memory_backends(self.tool_store)),
            outcome_sink=live.outcomes,
            handoff_sink=live.handoffs,
            credential=credential,
            locale_pack=self.locale_packs.get(bp.locale.locale_pack_ref or ""),
            voice_profile=self.voice_profiles.get(bp.locale.voice_profile_ref or ""),
            channel=channel,
            event_sink=sink,
            operator_transcripts=self.operator_transcripts,
        )
        # Same id on the wire (ServerMessage.session_id), in events, and in the REST registry — otherwise a client
        # cannot look up its own session (found live 2026-09-23: WS id != /api/sessions id).
        live.session = Session(deps, session_id=session_id)
        self.sessions[session_id] = live
        self.prune_sessions()
        return live

    def log_event(self, ev: Event) -> None:
        self.event_log.append(ev)
        over = len(self.event_log) - self.max_events
        if over > 0:
            del self.event_log[:over]
            self.event_log_base += over

    def events_since(self, since: int, limit: int, tenant_id: str | None = None) -> list[Event]:
        """Absolute-offset read of the ring buffer; `tenant_id` filters (F-08)."""
        start = max(0, since - self.event_log_base)
        if tenant_id is None:
            return self.event_log[start : start + limit]
        out: list[Event] = []
        for ev in self.event_log[start:]:
            if ev.tenant_id == tenant_id:
                out.append(ev)
                if len(out) >= limit:
                    break
        return out

    def prune_sessions(self) -> None:
        """F-12: keep at most `max_sessions`; only finished sessions are evicted (oldest first), never live ones."""
        excess = len(self.sessions) - self.max_sessions
        if excess <= 0:
            return
        for sid in list(self.sessions):
            if excess <= 0:
                break
            s = self.sessions[sid]
            finished = s.session is not None and s.session.record is not None and (s.task is None or s.task.done())
            if finished:
                del self.sessions[sid]
                excess -= 1


def _load_dir(path: Path, model: type[Any], key: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if not path.is_dir():
        return out
    for f in sorted(path.glob("*.yaml")):
        obj = model.model_validate(yaml.safe_load(f.read_text()))
        out[getattr(obj, key)] = obj
    return out


# Event types mirrored to the client as ServerMessageType.EVENT (§37.2 subset; interruption + turn telemetry).
FORWARDED_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "user.speech_started",
        "user.speech_discarded",
        "turn.ended",
        "interruption.detected",
        "assistant.response_cancelled",
        "transport.playout_started",
        "transport.playout_stopped",
        "latency.sample",
        "failure.classified",
        "handoff.requested",
        "handoff.acknowledged",
        # decision + tool lifecycle: source/confidence/tool_id only (no text) — lets the console show which
        # decision port answered (RULE vs LLM_VALIDATED) and the confirmation gate in real time
        "decision.made",
        "tool.confirmation_requested",
        "tool.confirmation_granted",
        "tool.confirmation_denied",
        "tool.execution_completed",
        "tool.execution_failed",
        "tool.policy_rejected",
        # P1: interruption lifecycle + provider errors (codes/messages only)
        "assistant.response_truncated",
        "assistant.playout_ended",
        "provider.error",
        # session close: primary/secondary outcome codes only (no record fields)
        "outcome.produced",
        "session.ended",
    }
)


def _callback_script(bp: ActivityBlueprint) -> list[MockScriptStep]:
    """Mock script that asks to schedule a callback (confirm_before_execute) on the 2nd user turn — exercises the
    confirmation gate and the decision port with a *spoken* customer reply (live decision-provider smokes)."""
    steps = [MockScriptStep(text=f"Hello, this is {bp.identity.name}. How can I help?")]
    steps.append(
        MockScriptStep(
            text="I can arrange a callback.",
            tool_call=ToolCallRequest(call_id="live_cb_1", tool_id="schedule_callback", arguments={"when": "tomorrow"}),
        )
    )
    steps.append(MockScriptStep(text="Done. Anything else?"))
    steps.append(MockScriptStep(text="Goodbye."))
    return steps


NAMED_SCRIPTS: dict[str, Callable[[ActivityBlueprint], list[MockScriptStep]]] = {"callback": _callback_script}


def _default_script(bp: ActivityBlueprint) -> list[MockScriptStep]:
    """Mock provider script: greet, then acknowledge each required field, then close. Text is generic."""
    steps = [MockScriptStep(text=f"Hello, this is {bp.identity.name}. How can I help?")]
    for f in bp.data.required:
        steps.append(MockScriptStep(text=f"Noted your {f.name.replace('_', ' ')}."))
    steps.append(MockScriptStep(text="Thank you. Is there anything else?"))
    steps.append(MockScriptStep(text="Goodbye."))
    return steps


__all__ = ["ActivityRecord", "LiveSession", "RuntimeStore"]
