"""ConfigSession — the Copilot's stateful loop (§14): discover → ask → answer → compose → propose.

Deterministic components own the state. Events (`config.session_started` / `config.question_asked` /
`config.answer_received`) are appended via an `event_sink` callable; payloads carry ids and paths only —
never free-text answers (QV-EVT-003 spirit: no business data in the event log).

The session may consult the control plane (Preflight, CapabilityMapper) when a valid draft exists and the
caller supplies a `PreflightContext` / `CapabilityMapper`; both are optional so the Copilot is testable
without any provider registry.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from qevion.contracts.activity import ReadinessState
from qevion.contracts.common import new_id
from qevion.contracts.composition import MappingResult
from qevion.contracts.control import PreflightFinding
from qevion.contracts.copilot import (
    BlueprintProposal,
    CapabilityRequirement,
    CopilotQuestion,
    DiscoveryStatus,
    IntegrationClass,
)
from qevion.contracts.event import Event, EventKind, EventType
from qevion.contracts.knowledge import Contradiction, KnowledgeGap
from qevion.contracts.policy import Decision
from qevion.control.capabilities import CapabilityMapper
from qevion.control.preflight import Preflight, PreflightContext
from qevion.copilot.composer import Answer, BlueprintComposer
from qevion.copilot.discovery import DiscoveryEngine, DiscoveryInputs, discovery_complete
from qevion.copilot.explainer import Explainer, readiness_findings

EventSink = Callable[[Event], None]

_INTEGRATION: dict[MappingResult, IntegrationClass] = {
    MappingResult.SUPPORTED: IntegrationClass.NO_INTEGRATION_NEEDED,
    MappingResult.SUPPORTED_WITH_CONFIGURATION: IntegrationClass.CONFIGURATION_ONLY,
    MappingResult.REQUIRES_KNOWLEDGE: IntegrationClass.CONFIGURATION_ONLY,
    MappingResult.REQUIRES_HUMAN: IntegrationClass.CONFIGURATION_ONLY,
    MappingResult.REQUIRES_TOOL: IntegrationClass.NEW_INTEGRATION_REQUIRED,
    MappingResult.UNSUPPORTED: IntegrationClass.NEW_CORE_CAPABILITY_REQUIRED,
    MappingResult.UNVERIFIED: IntegrationClass.CONFIGURATION_ONLY,  # verify or pick another provider
}


@dataclass
class ConfigSessionState:
    config_session_id: str
    tenant_id: str
    activity_id: str
    draft: dict[str, Any] = field(default_factory=dict)
    decisions: list[Decision] = field(default_factory=list)
    answered_paths: set[str] = field(default_factory=set)
    deferred_paths: set[str] = field(default_factory=set)
    asked: dict[str, CopilotQuestion] = field(default_factory=dict)  # question_id → question
    gaps: list[KnowledgeGap] = field(default_factory=list)
    contradictions: list[Contradiction] = field(default_factory=list)
    seq: int = 0
    proposal_count: int = 0


class ConfigSession:
    def __init__(
        self,
        *,
        tenant_id: str,
        activity_id: str,
        name: str,
        version: str = "0.1.0",
        preflight_ctx: PreflightContext | None = None,
        mapper: CapabilityMapper | None = None,
        event_sink: EventSink | None = None,
        engine: DiscoveryEngine | None = None,
        explainer: Explainer | None = None,
        session_id: str | None = None,
    ) -> None:
        self.state = ConfigSessionState(session_id or new_id("cfg"), tenant_id, activity_id)
        self._composer = BlueprintComposer(tenant_id=tenant_id, activity_id=activity_id, name=name, version=version)
        self._engine = engine or DiscoveryEngine()
        self._explainer = explainer or Explainer()
        self._preflight_ctx = preflight_ctx
        self._mapper = mapper
        self._sink = event_sink
        self._emit(EventType.CONFIG_SESSION_STARTED, {"activity_id": activity_id})

    # ---------------------------------------------------------------- inputs
    def seed_draft(self, draft: dict[str, Any], *, operator_id: str | None = None) -> None:
        """Start from an existing (partial) blueprint dict, e.g. an uploaded YAML."""
        self.state.draft = dict(draft)
        if operator_id:
            for path in _leaf_business_paths(draft):
                self.state.decisions = self._composer._record(  # noqa: SLF001 — same package
                    self.state.decisions, path, _operator(), operator_id
                )

    def set_knowledge(self, gaps: list[KnowledgeGap], contradictions: list[Contradiction]) -> None:
        self.state.gaps = list(gaps)
        self.state.contradictions = list(contradictions)

    # ---------------------------------------------------------------- loop
    def next_questions(self, *, limit: int = 3) -> list[CopilotQuestion]:
        qs = self._engine.next_questions(self._inputs(), limit=limit)
        for q in qs:
            if q.question_id not in self.state.asked:
                self.state.asked[q.question_id] = q
                self._emit(
                    EventType.CONFIG_QUESTION_ASKED,
                    {
                        "question_id": q.question_id,
                        "kind": q.kind.value,
                        "target_path": q.target_path,
                        "blocking": q.blocking,
                    },
                )
        return qs

    def answer(self, question_id: str, value: Any, *, operator_id: str) -> None:
        q = self._require(question_id)
        self.state.decisions = self._composer.apply(
            self.state.draft, self.state.decisions, Answer(q, value, operator_id)
        )
        self.state.answered_paths.add(q.target_path)
        self._emit(
            EventType.CONFIG_ANSWER_RECEIVED,
            {"question_id": question_id, "target_path": q.target_path, "mode": "answer"},
        )

    def accept(self, question_id: str, *, operator_id: str) -> None:
        q = self._require(question_id)
        if q.proposed_default is None:
            raise ValueError(f"question {question_id} has no proposal to accept")
        self.state.decisions = self._composer.accept_proposal(self.state.draft, self.state.decisions, q, operator_id)
        self.state.answered_paths.add(q.target_path)
        self._emit(
            EventType.CONFIG_ANSWER_RECEIVED,
            {"question_id": question_id, "target_path": q.target_path, "mode": "accept"},
        )

    def defer(self, question_id: str) -> None:
        q = self._require(question_id)
        if q.blocking:
            raise ValueError(f"blocking question {question_id} cannot be deferred")
        self.state.deferred_paths.add(q.target_path)
        self._emit(
            EventType.CONFIG_ANSWER_RECEIVED,
            {"question_id": question_id, "target_path": q.target_path, "mode": "defer"},
        )

    def approve_decision(self, item_path: str, *, operator_id: str) -> None:
        for i, d in enumerate(self.state.decisions):
            if d.item_path == item_path:
                self.state.decisions[i] = d.model_copy(update={"approved_by": operator_id})
                return
        raise KeyError(item_path)

    # ---------------------------------------------------------------- outputs
    def propose(self) -> BlueprintProposal:
        st = self.state
        st.proposal_count += 1
        composed = self._composer.compose(st.draft, st.decisions)
        findings: list[PreflightFinding] = []
        mapping_rows: list[Any] = []
        caps: list[CapabilityRequirement] = []
        readiness = ReadinessState.DRAFT
        if composed.blueprint is not None:
            if self._mapper is not None:
                mapping_rows = self._mapper.map_requirements(composed.blueprint)
                caps = [
                    CapabilityRequirement(
                        requirement=r.requirement,
                        required_capability=r.required_capability,
                        current_state=str(r.current_state),
                        action=r.action,
                        integration=_INTEGRATION[r.action],
                    )
                    for r in mapping_rows
                    if r.action is not MappingResult.SUPPORTED
                ]
            if self._preflight_ctx is not None:
                findings = Preflight(self._preflight_ctx).run(composed.blueprint).findings
        questions = self._engine.all_questions(self._inputs(preflight=findings, mapping=mapping_rows))
        for q in questions:
            st.asked.setdefault(q.question_id, q)
        pending = [c for c in st.contradictions if c.resolution == "pending"]
        open_gaps = [g for g in st.gaps if not g.resolved]
        rf = readiness_findings(st.draft, len(open_gaps), len(pending))
        if not composed.valid or not discovery_complete(questions):
            status = DiscoveryStatus.ASKING
            readiness = ReadinessState.DISCOVERY_IN_PROGRESS if st.draft else ReadinessState.DRAFT
        elif any(f.severity == "BLOCK" for f in findings) or any(r.severity == "BLOCK" for r in rf):
            status = DiscoveryStatus.BLOCKED
            readiness = ReadinessState.BLOCKED
        else:
            status = DiscoveryStatus.REVIEW
            unapproved = any(d.approved_by is None for d in composed.decisions)
            # REVIEW with a preflight-clean draft: READY_FOR_SIMULATION only if preflight actually ran clean
            if unapproved:
                readiness = ReadinessState.NEEDS_CONFIGURATION
            elif self._preflight_ctx is not None and not findings:
                readiness = ReadinessState.READY_FOR_SIMULATION
            else:
                readiness = ReadinessState.NEEDS_CONFIGURATION
        return BlueprintProposal(
            proposal_id=f"{st.config_session_id}-p{st.proposal_count}",
            config_session_id=st.config_session_id,
            tenant_id=st.tenant_id,
            draft=composed.blueprint,
            draft_valid=composed.valid,
            validation_errors=composed.errors,
            decisions=list(composed.decisions),
            gaps=open_gaps,
            contradictions=pending,
            capability_requirements=caps,
            preflight_findings=findings,
            readiness_findings=rf,
            simulation_cases=_simulation_cases(st.draft),
            questions=questions,
            status=status,
            readiness_state=readiness,
        )

    def explain(self, proposal: BlueprintProposal | None = None) -> str:
        return self._explainer.explain_proposal(proposal or self.propose())

    def explain_question(self, question_id: str) -> str:
        return self._explainer.explain_question(self._require(question_id))

    # ---------------------------------------------------------------- internals
    def _inputs(
        self, *, preflight: list[PreflightFinding] | None = None, mapping: list[Any] | None = None
    ) -> DiscoveryInputs:
        st = self.state
        return DiscoveryInputs(
            draft=st.draft,
            gaps=st.gaps,
            contradictions=st.contradictions,
            mapping=mapping or [],
            preflight=preflight or [],
            answered_paths=set(st.answered_paths),
            deferred_paths=set(st.deferred_paths),
        )

    def _require(self, question_id: str) -> CopilotQuestion:
        try:
            return self.state.asked[question_id]
        except KeyError as e:
            raise KeyError(f"unknown question {question_id}; call next_questions() first") from e

    def _emit(self, etype: str, payload: dict[str, Any]) -> None:
        if self._sink is None:
            return
        st = self.state
        self._sink(
            Event(
                seq=st.seq,
                tenant_id=st.tenant_id,
                session_id=st.config_session_id,
                activity_id=st.activity_id,
                kind=EventKind.CONFIG,
                type=etype,
                source="copilot",
                payload=payload,
            )
        )
        st.seq += 1


def _operator() -> Any:
    from qevion.contracts.policy import ProposedBy

    return ProposedBy.OPERATOR


def _leaf_business_paths(draft: dict[str, Any]) -> list[str]:
    from qevion.copilot.composer import BUSINESS_DECISION_PATHS

    out: list[str] = []
    for p in BUSINESS_DECISION_PATHS:
        cur: Any = draft
        ok = True
        for part in p.split("."):
            if not isinstance(cur, dict) or part not in cur:
                ok = False
                break
            cur = cur[part]
        if ok and cur not in (None, [], {}, ""):
            out.append(p)
    return out


def _simulation_cases(draft: dict[str, Any]) -> list[str]:
    """Structural simulation case list derived from the draft (QV-COP-012); personas are added in P5."""
    cases = ["happy_path_all_required_collected", "unknown_question_policy_applied", "interruption_mid_sentence"]
    if draft.get("direction") in ("outbound", "bidirectional"):
        cases += ["opt_out_requested", "consent_declined"]
    pol = draft.get("policies") or {}
    uq = ((pol.get("unknown_question_policy") or {}).get("default")) if isinstance(pol, dict) else None
    if uq == "OFFER_HUMAN_HANDOFF" or draft.get("handoff_rules"):
        cases.append("handoff_triggered_with_context")
    if (draft.get("tools") or {}).get("required"):
        cases += ["tool_failure_fallback", "confirmation_before_write"]
    if (draft.get("coverage") or {}).get("objections"):
        cases.append("objection_raised_approved_response_only")
    return cases


__all__ = ["ConfigSession", "ConfigSessionState", "EventSink"]
