"""Copilot evaluation suite (QV-EVAL-004) — scripted operator personas + fixture uploads with planted
conflicts/gaps, driven through the real ConfigSession, graded deterministically.

Graders (all evidence-based, no model calls):
  requirements_gathered     every required business path answered/seeded before REVIEW
  unnecessary_questions     blocking questions asked for already-answered paths ≤ threshold
  gaps_detected             planted knowledge gaps surface as BLOCKING_GAP questions
  conflicts_surfaced        planted contradictions surface as DATA_CONFLICT questions + data_integrity finding
  facts_not_invented        every business decision traces to operator or copilot-with-operator-approval
  capability_mapping        a tool absent from the registry maps to REQUIRES_TOOL
  valid_blueprint           composed draft validates against qevion.activity.v1
  decisions_preserved       operator decisions survive re-proposal (count never shrinks, approvals kept)
  simulation_ready          preflight-clean proposal reaches READY_FOR_SIMULATION (or reports why not)
Attribution: D (configuration quality / Copilot) for all graders (QV-EVAL-001).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml

from qevion.adapters.decision.rules import RulesDecisionAdapter
from qevion.adapters.providers.mocks import MockS2SAdapter
from qevion.adapters.turn.energy import EnergyTurnAdapter
from qevion.contracts.activity import ActivityBlueprint, ReadinessState
from qevion.contracts.common import Channel
from qevion.contracts.composition import CapabilityRegistry, Composition, MappingResult
from qevion.contracts.copilot import BlueprintProposal, DiscoveryStatus, QuestionKind
from qevion.contracts.knowledge import Contradiction, GapClass, KnowledgeGap
from qevion.contracts.policy import ProposedBy
from qevion.contracts.tenant import LocalePack, VoiceProfile
from qevion.contracts.tool import ToolDeclaration
from qevion.control.capabilities import CapabilityMapper, build_registry
from qevion.control.preflight import PreflightContext
from qevion.copilot.session import ConfigSession
from qevion.core.platform_tools import platform_declarations
from qevion.eval.report import Attribution, CaseReport, GraderOutcome

ROOT = Path(__file__).resolve().parents[2]
OPERATOR = "eval_operator"


class OperatorPersonaKind(StrEnum):
    THOROUGH = "thorough"  # answers every blocking question first time
    MINIMAL = "minimal"  # defers everything optional
    UPLOADER = "uploader"  # seeds from a fixture blueprint, answers only what remains
    CONFLICTED = "conflicted"  # uploader + planted knowledge conflicts/gaps
    MISSING_TOOL = "missing_tool"  # requires a tool the registry does not have


@dataclass
class OperatorPersona:
    kind: OperatorPersonaKind
    answers: dict[str, Any]
    fixture: str | None = None  # config/examples/<name>.yaml
    planted_gaps: int = 0
    planted_conflicts: int = 0
    missing_tool_id: str | None = None
    unnecessary_threshold: int = 0


@dataclass
class CopilotEvalCase:
    case_id: str
    persona: OperatorPersona
    tags: list[str] = field(default_factory=list)


@dataclass
class CopilotRun:
    case: CopilotEvalCase
    session: ConfigSession
    proposals: list[BlueprintProposal]
    asked_paths: list[str]
    unnecessary_paths: list[str]
    decisions_before: int
    decisions_after: int
    error: str | None = None

    @property
    def final(self) -> BlueprintProposal:
        return self.proposals[-1]


_BASE_ANSWERS: dict[str, Any] = {
    "objective.primary": {"kind": "survey", "description": "collect satisfaction answers"},
    "direction": "inbound",
    "channels": ["text"],
    "locale": "ar-EG",
    "data.required": ["rating", "comment"],
    "knowledge.sources": ["faq_v1"],
    "policies.unknown_question_policy.default": "STATE_LIMITATION",
    "policies.opt_out": "CLOSE_GRACEFULLY",
    "outcome_schema.primary": ["completed", "not_completed", "opted_out"],
    "completion.success_rules": ["all_required_collected"],
    "handoff_rules": ["support_queue"],
    "coverage.objections": ["too long"],
}


def default_personas() -> list[OperatorPersona]:
    return [
        OperatorPersona(OperatorPersonaKind.THOROUGH, dict(_BASE_ANSWERS)),
        OperatorPersona(OperatorPersonaKind.MINIMAL, dict(_BASE_ANSWERS)),
        OperatorPersona(OperatorPersonaKind.UPLOADER, {}, fixture="activity_a_restaurant"),
        OperatorPersona(
            OperatorPersonaKind.CONFLICTED, {}, fixture="activity_b_clinic", planted_gaps=1, planted_conflicts=1
        ),
        OperatorPersona(
            OperatorPersonaKind.MISSING_TOOL, {}, fixture="activity_c_survey", missing_tool_id="crm_push_lead"
        ),
    ]


def default_copilot_cases() -> list[CopilotEvalCase]:
    return [CopilotEvalCase(f"cop_{p.kind.value}", p, tags=["copilot", p.kind.value]) for p in default_personas()]


def _fixture(name: str) -> dict[str, Any]:
    raw: dict[str, Any] = yaml.safe_load((ROOT / "config/examples" / f"{name}.yaml").read_text())
    return raw


def _plant_knowledge(s: ConfigSession, gaps: int, conflicts: int) -> None:
    s.set_knowledge(
        [
            KnowledgeGap(
                gap_id=f"gap_{i}",
                tenant_id=s.state.tenant_id,
                gap_class=GapClass.REQUIRED_FOR_EXECUTION,
                description=f"planted gap {i}",
                question_for_operator=f"Planted question {i}?",
            )
            for i in range(gaps)
        ],
        [
            Contradiction(
                contradiction_id=f"con_{i}",
                tenant_id=s.state.tenant_id,
                fact_ids=[f"f{i}a", f"f{i}b"],
                description=f"planted conflict {i}",
            )
            for i in range(conflicts)
        ],
    )


def _knowledge_plane_applies(
    session: ConfigSession, *, contradiction_id: str | None = None, winner: str = "", gap_id: str | None = None
) -> None:
    """Emulate the knowledge plane applying the operator decision (runtime: KnowledgePipeline.resolve_contradiction /
    gap fill) and re-feeding the Copilot, exactly as `copilot.api._view` does via `set_knowledge`."""
    gaps = [
        g.model_copy(update={"resolved": True, "resolution_fact_id": "fact_operator"}) if g.gap_id == gap_id else g
        for g in session.state.gaps
    ]
    cons = [
        c.model_copy(update={"resolution": "operator_decided", "winning_fact_id": winner})
        if c.contradiction_id == contradiction_id
        else c
        for c in session.state.contradictions
    ]
    session.set_knowledge(gaps, cons)


def _load_dir(path: Path, model: type[Any], key: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if path.is_dir():
        for f in sorted(path.glob("*.yaml")):
            obj = model.model_validate(yaml.safe_load(f.read_text()))
            out[getattr(obj, key)] = obj
    return out


@dataclass
class EvalEnvironment:
    """The same platform primitives the runtime hands to Preflight: mock composition, registry, packs, voices.
    Built from config/ only (no business data). `missing_tool_id` removes one platform tool to plant a gap."""

    registry: CapabilityRegistry
    composition: Composition
    locale_packs: dict[str, LocalePack]
    voice_profiles: dict[str, VoiceProfile]
    tool_declarations: dict[str, ToolDeclaration]

    @classmethod
    def build(cls, missing_tool_id: str | None = None) -> EvalEnvironment:
        decls = dict(platform_declarations())
        if missing_tool_id:
            decls.pop(missing_tool_id, None)
        comps = _load_dir(ROOT / "config/compositions", Composition, "composition_id")
        packs = _load_dir(ROOT / "config/locale_packs", LocalePack, "locale_pack_id")
        voices = _load_dir(ROOT / "config/voice_profiles", VoiceProfile, "voice_profile_id")
        registry = build_registry(
            [MockS2SAdapter([]), EnergyTurnAdapter(), RulesDecisionAdapter()],
            tool_declarations=decls,
            locale_packs=packs,
            voice_profiles=voices,
            channels=[Channel.TEXT, Channel.BROWSER_VOICE],
        )
        return cls(registry, comps["comp_mock_s2s_v1"], packs, voices, decls)

    def preflight_ctx(self) -> PreflightContext:
        return PreflightContext(
            registry=self.registry,
            composition=self.composition,
            tool_declarations=self.tool_declarations,
            locale_packs=self.locale_packs,
            voice_profiles=self.voice_profiles,
            strict_capabilities=False,
        )

    def mapper(self) -> CapabilityMapper:
        return CapabilityMapper(self.registry, self.composition)


def drive(case: CopilotEvalCase, *, max_rounds: int = 25) -> CopilotRun:
    p = case.persona
    env = EvalEnvironment.build(p.missing_tool_id)
    session = ConfigSession(
        tenant_id="eval",
        activity_id=f"act_{case.case_id}",
        name=case.case_id,
        preflight_ctx=env.preflight_ctx(),
        mapper=env.mapper(),
    )
    if p.fixture:
        raw = _fixture(p.fixture)
        if p.missing_tool_id:
            tools = raw.setdefault("tools", {})
            tools.setdefault("required", []).append({"tool_id": p.missing_tool_id, "purpose": "push lead to external CRM"})
            tools.setdefault("permissions", {})[p.missing_tool_id] = {
                "impact": "write",
                "confirmation": "confirm_before_execute",
                "authorization_scope": "activity",
            }
        session.seed_draft(raw, operator_id=OPERATOR)
    if p.planted_gaps or p.planted_conflicts:
        _plant_knowledge(session, p.planted_gaps, p.planted_conflicts)

    decisions_before = len(session.state.decisions)
    proposals: list[BlueprintProposal] = []
    asked: list[str] = []
    unnecessary: list[str] = []
    answered: set[str] = set()
    error: str | None = None
    try:
        for _ in range(max_rounds):
            prop = session.propose()
            proposals.append(prop)
            # operator works from the proposal's question list (includes preflight- and mapping-derived questions)
            qs = list(prop.questions)
            session.mark_asked(qs)
            if not qs or prop.status is DiscoveryStatus.REVIEW:
                break
            progressed = False
            for q in qs:
                asked.append(q.target_path)
                if q.blocking and q.target_path in answered:
                    unnecessary.append(q.target_path)
                if q.target_path.startswith("knowledge.contradictions."):
                    cid = q.target_path.rsplit(".", 1)[1]
                    winner = next((c.fact_ids[0] for c in session.state.contradictions if c.contradiction_id == cid), "")
                    session.answer(q.question_id, winner, operator_id=OPERATOR)
                    _knowledge_plane_applies(session, contradiction_id=cid, winner=winner)
                    progressed = True
                elif q.target_path.startswith("knowledge.gaps."):
                    gid = q.target_path.rsplit(".", 1)[1]
                    session.answer(q.question_id, "operator supplied value", operator_id=OPERATOR)
                    _knowledge_plane_applies(session, gap_id=gid)
                    progressed = True
                elif q.target_path.startswith("capabilities.knowledge:"):
                    # REQUIRES_KNOWLEDGE → operator uploads/points to a source (AnswerType.UPLOAD)
                    session.answer(q.question_id, f"upload://{q.target_path.split(':', 1)[1]}", operator_id=OPERATOR)
                    progressed = True
                elif q.target_path in p.answers:
                    session.answer(q.question_id, p.answers[q.target_path], operator_id=OPERATOR)
                    answered.add(q.target_path)
                    progressed = True
                elif not q.blocking:
                    session.defer(q.question_id)
                    progressed = True
                # MISSING_TOOL: blocking tools.* questions stay open by design (integration gap)
            if not progressed:
                break
        proposals.append(session.propose())
    except Exception as exc:  # noqa: BLE001 — recorded as evidence, not raised
        error = f"{type(exc).__name__}: {exc}"
        if not proposals:
            proposals.append(session.propose())
    return CopilotRun(
        case=case,
        session=session,
        proposals=proposals,
        asked_paths=asked,
        unnecessary_paths=unnecessary,
        decisions_before=decisions_before,
        decisions_after=len(session.state.decisions),
        error=error,
    )


# ---------------------------------------------------------------- graders

GraderFn = Callable[[CopilotRun], GraderOutcome]


def _g(name: str, passed: bool, detail: str, **evidence: Any) -> GraderOutcome:
    return GraderOutcome(grader=name, passed=passed, detail=detail, attribution=Attribution.D, evidence=evidence)


def g_requirements_gathered(run: CopilotRun) -> GraderOutcome:
    fin = run.final
    blocking_open = [q.target_path for q in fin.questions if q.blocking]
    expected_blocked = run.case.persona.kind is OperatorPersonaKind.MISSING_TOOL
    ok = fin.draft_valid and (not blocking_open or expected_blocked)
    return _g("requirements_gathered", ok, f"blocking_open={blocking_open}", blocking_open=blocking_open)


def g_unnecessary_questions(run: CopilotRun) -> GraderOutcome:
    n = len(run.unnecessary_paths)
    thr = run.case.persona.unnecessary_threshold
    return _g("unnecessary_questions", n <= thr, f"{n} ≤ {thr}", paths=run.unnecessary_paths)


def g_gaps_detected(run: CopilotRun) -> GraderOutcome:
    planted = run.case.persona.planted_gaps
    seen = sum(1 for p in run.proposals for q in p.questions if q.kind is QuestionKind.BLOCKING_GAP)
    ok = seen >= planted if planted else True
    return _g("gaps_detected", ok, f"planted={planted} surfaced={seen}", planted=planted, surfaced=seen)


def g_conflicts_surfaced(run: CopilotRun) -> GraderOutcome:
    planted = run.case.persona.planted_conflicts
    seen = sum(1 for p in run.proposals for q in p.questions if q.kind is QuestionKind.DATA_CONFLICT)
    integrity = any(
        r.category == "data_integrity" and r.severity == "BLOCK" for p in run.proposals for r in p.readiness_findings
    )
    ok = (seen >= planted and integrity) if planted else True
    return _g("conflicts_surfaced", ok, f"planted={planted} surfaced={seen} integrity_block={integrity}")


def g_facts_not_invented(run: CopilotRun) -> GraderOutcome:
    bad = [
        d.item_path
        for d in run.final.decisions
        if d.proposed_by is not ProposedBy.OPERATOR and d.approved_by is None and d.item_path.startswith(_BUSINESS)
    ]
    # copilot-proposed but unapproved business values must be surfaced as NEEDS_CONFIGURATION, never silently valid
    ok = not bad or run.final.readiness_state in (
        ReadinessState.NEEDS_CONFIGURATION,
        ReadinessState.DISCOVERY_IN_PROGRESS,
        ReadinessState.BLOCKED,
        ReadinessState.DRAFT,
    )
    return _g("facts_not_invented", ok, f"unapproved_copilot_business_values={bad}", paths=bad)


_BUSINESS = ("objective", "data", "knowledge", "policies", "outcome_schema", "completion", "handoff_rules", "coverage")


def g_capability_mapping(run: CopilotRun) -> GraderOutcome:
    tool = run.case.persona.missing_tool_id
    if not tool:
        return _g("capability_mapping", True, "no missing tool planted")
    rows = [c for c in run.final.capability_requirements if c.required_capability == f"tool:{tool}"]
    ok = any(c.action is MappingResult.REQUIRES_TOOL for c in rows)
    return _g("capability_mapping", ok, f"tool:{tool} → {[str(c.action) for c in rows]}")


def g_valid_blueprint(run: CopilotRun) -> GraderOutcome:
    fin = run.final
    ok = fin.draft_valid and fin.draft is not None
    if ok and fin.draft is not None:
        ActivityBlueprint.model_validate(fin.draft.model_dump(mode="json", by_alias=True))
    return _g("valid_blueprint", ok, f"errors={fin.validation_errors[:3]}")


def g_decisions_preserved(run: CopilotRun) -> GraderOutcome:
    counts = [len(p.decisions) for p in run.proposals]
    monotone = all(b >= a for a, b in zip(counts, counts[1:], strict=False))
    approved_kept = run.decisions_after >= run.decisions_before
    return _g("decisions_preserved", monotone and approved_kept, f"counts={counts}", counts=counts)


def g_simulation_ready(run: CopilotRun) -> GraderOutcome:
    fin = run.final
    kind = run.case.persona.kind
    if kind is OperatorPersonaKind.MISSING_TOOL:
        ok = fin.readiness_state is not ReadinessState.READY_FOR_SIMULATION
        return _g("simulation_ready", ok, f"blocked as expected: {fin.readiness_state}")
    ok = fin.status is DiscoveryStatus.REVIEW and fin.readiness_state in (
        ReadinessState.READY_FOR_SIMULATION,
        ReadinessState.NEEDS_CONFIGURATION,
    )
    why = [f"{f.reason}@{f.path}" for f in fin.preflight_findings if f.severity == "BLOCK"] if not ok else []
    return _g("simulation_ready", ok, f"status={fin.status} readiness={fin.readiness_state} why={why}")


GRADERS: tuple[GraderFn, ...] = (
    g_requirements_gathered,
    g_unnecessary_questions,
    g_gaps_detected,
    g_conflicts_surfaced,
    g_facts_not_invented,
    g_capability_mapping,
    g_valid_blueprint,
    g_decisions_preserved,
    g_simulation_ready,
)


def grade(run: CopilotRun) -> CaseReport:
    outcomes = [g(run) for g in GRADERS]
    if run.error:
        outcomes.append(_g("no_exception", False, run.error))
    return CaseReport(
        case_id=run.case.case_id,
        track="copilot",
        tags=list(run.case.tags),
        graders=outcomes,
        evidence={
            "proposals": len(run.proposals),
            "questions_asked": len(run.asked_paths),
            "final_status": str(run.final.status),
            "final_readiness": str(run.final.readiness_state),
            "decisions": run.decisions_after,
        },
    )


def run_copilot_eval(cases: list[CopilotEvalCase] | None = None) -> list[CaseReport]:
    return [grade(drive(c)) for c in cases or default_copilot_cases()]
