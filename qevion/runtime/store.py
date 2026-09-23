"""In-memory runtime state for the P3 POC (A7). Everything here is replaceable by a DB adapter later.

The runtime imports core/control/knowledge/adapters — never copilot (import-linter: Copilot ≠ runtime).
Copilot is exposed via a *separate* app module (`qevion.copilot.api`) mounted by the composition root.
"""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from qevion.adapters.decision.rules import RulesDecisionAdapter
from qevion.adapters.providers.mocks import MockS2SAdapter, MockScriptStep
from qevion.adapters.sinks.memory import MemoryHandoffSink, MemoryOutcomeSink
from qevion.adapters.tools.memory_backend import MemoryStore, memory_backends
from qevion.adapters.turn.energy import EnergyTurnAdapter
from qevion.admin.credentials import EnvAdminEphemeralResolver
from qevion.contracts.activity import ActivityBlueprint, ReadinessState
from qevion.contracts.common import Channel
from qevion.contracts.composition import Composition
from qevion.contracts.control import PreflightResult
from qevion.contracts.event import Event
from qevion.contracts.knowledge import KnowledgeSource, SourceKind
from qevion.contracts.provider import S2SSessionConfig
from qevion.contracts.tenant import Tenant
from qevion.control.capabilities import CapabilityMapper, RequirementMapping, build_registry
from qevion.control.preflight import Preflight, PreflightContext
from qevion.control.readiness import IllegalReadinessTransitionError, ReadinessChange, ReadinessMachine
from qevion.core.platform_tools import declarations_for_blueprint_permissions
from qevion.core.session import Session, SessionDeps
from qevion.knowledge.pipeline import IngestionReport, KnowledgePipeline, KnowledgeStore

ROOT = Path(__file__).resolve().parents[2]


@dataclass
class ActivityRecord:
    blueprint: ActivityBlueprint
    readiness: ReadinessMachine
    preflight: PreflightResult | None = None
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


class RuntimeStore:
    """Composition root state. Single process, in-memory."""

    def __init__(self) -> None:
        self.tenants: dict[str, Tenant] = {}
        self.activities: dict[str, ActivityRecord] = {}
        self.knowledge = KnowledgeStore()
        self.pipeline = KnowledgePipeline(self.knowledge)
        self.reports: dict[str, IngestionReport] = {}
        self.credentials = EnvAdminEphemeralResolver()
        self.sessions: dict[str, LiveSession] = {}
        self.event_log: list[Event] = []
        self.composition = Composition.model_validate(
            yaml.safe_load((ROOT / "config/compositions/comp_mock_s2s_v1.yaml").read_text())
        )
        self._s2s = MockS2SAdapter([])
        self._turn = EnergyTurnAdapter()
        self._decision = RulesDecisionAdapter()
        self.registry = build_registry(
            [self._s2s, self._turn, self._decision],
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

    # ---------------------------------------------------------------- sessions
    def build_session(
        self,
        *,
        activity_key: str,
        transport: Any,
        session_id: str,
        channel: Channel,
        script: list[MockScriptStep] | None = None,
    ) -> LiveSession:
        rec = self.get_activity(activity_key)
        bp = rec.blueprint
        live = LiveSession(session_id=session_id, activity_key=activity_key, session=None)  # type: ignore[arg-type]

        async def sink(ev: Event) -> None:
            live.events.append(ev)
            self.event_log.append(ev)

        credential, _src = self.credentials.resolve("mock", bp.identity.tenant_id)
        deps = SessionDeps(
            blueprint=bp,
            s2s=MockS2SAdapter(script or _default_script(bp)),
            s2s_config=S2SSessionConfig(provider="mock", model="mock-1"),
            transport=transport,
            turn=self._turn.new_detector(),
            decision=self._decision,
            tool_declarations=declarations_for_blueprint_permissions(bp.tools.permissions),
            tool_backends=dict(memory_backends(self.tool_store)),
            outcome_sink=live.outcomes,
            handoff_sink=live.handoffs,
            credential=credential,
            channel=channel,
            event_sink=sink,
        )
        live.session = Session(deps)
        self.sessions[session_id] = live
        return live


def _default_script(bp: ActivityBlueprint) -> list[MockScriptStep]:
    """Mock provider script: greet, then acknowledge each required field, then close. Text is generic."""
    steps = [MockScriptStep(text=f"Hello, this is {bp.identity.name}. How can I help?")]
    for f in bp.data.required:
        steps.append(MockScriptStep(text=f"Noted your {f.name.replace('_', ' ')}."))
    steps.append(MockScriptStep(text="Thank you. Is there anything else?"))
    steps.append(MockScriptStep(text="Goodbye."))
    return steps


__all__ = ["ActivityRecord", "LiveSession", "RuntimeStore"]
