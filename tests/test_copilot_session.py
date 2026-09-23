"""P3 — BlueprintComposer + ConfigSession (QV-COP-006/008/010/011/012/015)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from qevion.contracts.activity import ActivityBlueprint, ReadinessState
from qevion.contracts.copilot import DiscoveryStatus, QuestionKind
from qevion.contracts.event import Event, EventType
from qevion.contracts.knowledge import Contradiction, GapClass, KnowledgeGap
from qevion.contracts.policy import ProposedBy
from qevion.control.preflight import PreflightContext
from qevion.copilot.composer import BlueprintComposer, is_business_path
from qevion.copilot.session import ConfigSession

ROOT = Path(__file__).resolve().parents[1]
OP = "op_1"


def _session(**kw: Any) -> tuple[ConfigSession, list[Event]]:
    events: list[Event] = []
    s = ConfigSession(tenant_id="t1", activity_id="act_x", name="X", event_sink=events.append, **kw)
    return s, events


def _find(s: ConfigSession, path: str) -> str:
    for q in s.next_questions(limit=50):
        if q.target_path == path:
            return q.question_id
    raise AssertionError(f"no question for {path}")


def _drive_to_review(s: ConfigSession) -> None:
    """Answer every blocking question the engine produces, using operator-provided values."""
    answers: dict[str, Any] = {
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
    for _ in range(20):
        qs = s.next_questions(limit=50)
        if not qs:
            return
        progressed = False
        for q in qs:
            if q.target_path in answers:
                s.answer(q.question_id, answers[q.target_path], operator_id=OP)
                progressed = True
            elif not q.blocking:
                s.defer(q.question_id)
                progressed = True
        if not progressed:
            raise AssertionError(f"stuck on {[q.target_path for q in qs]}")


# ------------------------------------------------------------------ composer


def test_composer_scaffold_is_structural_only() -> None:
    c = BlueprintComposer(tenant_id="t", activity_id="a", name="A")
    r = c.compose({}, [])
    assert not r.valid and r.blueprint is None
    assert r.draft["identity"]["activity_id"] == "a"
    assert "objective" not in r.draft and "outcome_schema" not in r.draft  # never invented
    assert any(e.startswith("objective") for e in r.errors)


def test_is_business_path() -> None:
    assert is_business_path("completion.success_rules")
    assert is_business_path("objective")
    assert not is_business_path("locale")
    assert not is_business_path("channels")


# ------------------------------------------------------------------ session loop


def test_events_and_no_free_text_in_payloads() -> None:
    s, ev = _session()
    qid = _find(s, "objective.primary")
    s.answer(qid, "secret business objective text", operator_id=OP)
    types = [e.type for e in ev]
    assert types[0] == EventType.CONFIG_SESSION_STARTED
    assert EventType.CONFIG_QUESTION_ASKED in types and types[-1] == EventType.CONFIG_ANSWER_RECEIVED
    assert [e.seq for e in ev] == list(range(len(ev)))
    assert all("secret" not in str(e.payload) for e in ev)
    assert ev[-1].payload["target_path"] == "objective.primary" and ev[-1].source == "copilot"


def test_answer_records_operator_decision_and_removes_question() -> None:
    s, _ = _session()
    qid = _find(s, "completion.success_rules")
    s.answer(qid, "all_required_collected", operator_id=OP)
    d = next(d for d in s.state.decisions if d.item_path == "completion.success_rules")
    assert d.proposed_by is ProposedBy.OPERATOR and d.approved_by == OP
    assert s.state.draft["completion"]["success_rules"] == ["all_required_collected"]
    assert all(q.target_path != "completion.success_rules" for q in s.next_questions(limit=50))


def test_accept_proposal_records_copilot_decision_approved_by_operator() -> None:
    s, _ = _session()
    qid = _find(s, "outcome_schema.primary")
    s.accept(qid, operator_id=OP)
    d = next(d for d in s.state.decisions if d.item_path == "outcome_schema.primary")
    assert d.proposed_by is ProposedBy.COPILOT and d.approved_by == OP
    assert s.state.draft["outcome_schema"]["primary"] == ["completed", "not_completed", "opted_out", "handed_off"]


def test_blocking_question_cannot_be_deferred_but_optional_can() -> None:
    s, _ = _session()
    blocking = _find(s, "objective.primary")
    try:
        s.defer(blocking)
        raise AssertionError("blocking deferred")
    except ValueError:
        pass
    optional = _find(s, "locale")
    s.defer(optional)
    assert all(q.target_path != "locale" for q in s.next_questions(limit=50))


def test_unknown_question_id_rejected() -> None:
    s, _ = _session()
    try:
        s.answer("q_nope", 1, operator_id=OP)
        raise AssertionError
    except KeyError:
        pass


def test_proposal_progression_to_review_and_valid_blueprint() -> None:
    s, _ = _session()
    p0 = s.propose()
    assert p0.status is DiscoveryStatus.ASKING and not p0.draft_valid and p0.draft is None
    assert p0.readiness_state is ReadinessState.DRAFT
    _drive_to_review(s)
    p = s.propose()
    assert p.draft_valid, p.validation_errors
    assert isinstance(p.draft, ActivityBlueprint)
    assert p.status is DiscoveryStatus.REVIEW and p.questions == [] or all(not q.blocking for q in p.questions)
    # every business element written has a Decision, all approved by the operator who answered
    paths = {d.item_path for d in p.decisions}
    assert {"objective.primary", "data.required", "outcome_schema.primary", "completion.success_rules"} <= paths
    assert p.unapproved_decisions == []
    assert p.draft.version_metadata.decisions  # decisions carried into the blueprint
    assert p.readiness_state is ReadinessState.NEEDS_CONFIGURATION  # no preflight ctx → cannot claim more
    assert "happy_path_all_required_collected" in p.simulation_cases
    assert p.draft.policies.uncertainty_policy.missing.value == "STATE_LIMITATION"  # mirrored structure


def test_proposal_with_preflight_ctx_reaches_ready_for_simulation_or_reports_findings() -> None:
    s, _ = _session(preflight_ctx=PreflightContext(strict_capabilities=False))
    _drive_to_review(s)
    p = s.propose()
    assert p.draft_valid
    if p.preflight_findings:
        assert p.status in (DiscoveryStatus.ASKING, DiscoveryStatus.BLOCKED)
        assert all(q.source_refs for q in p.questions if q.target_path.startswith(("tools", "knowledge", "locale")))
    else:
        assert p.readiness_state is ReadinessState.READY_FOR_SIMULATION


def test_knowledge_gaps_and_conflicts_flow_into_proposal() -> None:
    s, _ = _session()
    _drive_to_review(s)
    s.set_knowledge(
        [KnowledgeGap(gap_id="g1", tenant_id="t1", gap_class=GapClass.REQUIRED_FOR_EXECUTION, description="d", question_for_operator="Price of X?")],
        [Contradiction(contradiction_id="c1", tenant_id="t1", fact_ids=["f1", "f2"], description="hours differ")],
    )
    p = s.propose()
    assert p.status is DiscoveryStatus.ASKING  # blocking questions remain
    kinds = {q.kind for q in p.questions}
    assert QuestionKind.DATA_CONFLICT in kinds and QuestionKind.BLOCKING_GAP in kinds
    assert p.gap_counts() == {"REQUIRED_FOR_EXECUTION": 1} and len(p.contradictions) == 1
    assert any(r.category == "data_integrity" and r.severity == "BLOCK" for r in p.readiness_findings)
    # answering the conflict records an operator decision (knowledge plane applies it) and removes the question
    qid = next(q.question_id for q in p.questions if q.kind is QuestionKind.DATA_CONFLICT)
    s.answer(qid, "f1", operator_id=OP)
    assert any(d.item_path == "knowledge.contradictions.c1" and d.rationale == "f1" for d in s.state.decisions)
    assert all(q.kind is not QuestionKind.DATA_CONFLICT for q in s.propose().questions)


def test_readiness_findings_block_when_handoff_promised_without_destination() -> None:
    s, _ = _session()
    _drive_to_review(s)
    s.state.draft["policies"]["unknown_question_policy"]["default"] = "OFFER_HUMAN_HANDOFF"
    s.state.draft.pop("handoff_rules", None)
    s.state.answered_paths.discard("handoff_rules")
    p = s.propose()
    assert any(q.target_path == "handoff_rules" and q.blocking for q in p.questions)
    assert any(r.category == "escalation" and r.severity == "BLOCK" for r in p.readiness_findings)
    assert "handoff_triggered_with_context" in p.simulation_cases


def test_seed_from_example_blueprint_gives_review_or_targeted_questions() -> None:
    raw = yaml.safe_load((ROOT / "config/examples/activity_a_restaurant.yaml").read_text())
    s, _ = _session()
    s.seed_draft(raw, operator_id=OP)
    p = s.propose()
    assert p.draft_valid, p.validation_errors
    assert all(q.blocking is False for q in p.questions), [q.target_path for q in p.questions]
    assert p.status is DiscoveryStatus.REVIEW
    assert p.readiness_state in (ReadinessState.NEEDS_CONFIGURATION, ReadinessState.READY_FOR_SIMULATION)


def test_explainer_outputs_are_separate_from_proposal() -> None:
    s, _ = _session()
    qid = _find(s, "objective.primary")
    text = s.explain_question(qid)
    assert "I will not guess" in text and "Why:" in text
    p = s.propose()
    out = s.explain(p)
    for header in ("# Proposal", "## Draft", "## Decisions", "## Knowledge", "## Capabilities", "## Preflight", "## What could go wrong", "## Next questions"):
        assert header in out
    assert "NOT valid yet" in out
    # phrasing port may rephrase but the proposal object is untouched
    s2, _ = _session()
    from qevion.copilot.explainer import Explainer

    s2._explainer = Explainer(phrase=lambda t: t.upper())  # noqa: SLF001
    assert s2.explain(p).startswith("# PROPOSAL")
    assert p.model_dump() == s.propose().model_copy(update={"proposal_id": p.proposal_id, "produced_at": p.produced_at}).model_dump()
