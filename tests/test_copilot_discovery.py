"""P3 — Copilot discovery engine (QV-COP-001..007)."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from typing import Any

from qevion.contracts.composition import MappingResult
from qevion.contracts.control import PreflightFinding, PreflightReason
from qevion.contracts.copilot import AnswerType, QuestionKind
from qevion.contracts.knowledge import Contradiction, GapClass, KnowledgeGap
from qevion.copilot.discovery import (
    DiscoveryEngine,
    DiscoveryInputs,
    QuestionPrioritizer,
    discovery_complete,
    question_id_for,
)

ENGINE = DiscoveryEngine()


@dataclass
class Row:
    requirement: str
    required_capability: str
    current_state: str
    action: MappingResult
    provider: str | None = None
    note: str | None = None


def _full_draft() -> dict[str, Any]:
    return {
        "objective": {"primary": {"kind": "run_survey", "description": "gather answers"}},
        "direction": "inbound",
        "channels": ["text"],
        "locale": {"locale": "ar-EG"},
        "data": {"required": [{"name": "answer_1", "type": "string"}]},
        "knowledge": {"sources": [{"source_id": "s1", "kind": "file"}]},
        "policies": {
            "unknown_question_policy": {"default": "STATE_LIMITATION"},
            "opt_out": {"phrases_ref": "p"},
        },
        "outcome_schema": {"primary": ["completed"]},
        "completion": {"success_rules": ["all_required_collected"]},
    }


# ----------------------------------------------------------------- no fixed questionnaire (QV-COP-001)


def test_empty_draft_asks_for_foundations_first() -> None:
    qs = ENGINE.next_questions(DiscoveryInputs(), limit=3)
    paths = [q.target_path for q in qs]
    assert paths[0] in {"channels", "knowledge.sources"}  # BLOCKING_GAP band beats BUSINESS_DECISION
    assert all(q.blocking for q in qs)


def test_questions_change_with_draft_state() -> None:
    q_empty = {q.target_path for q in ENGINE.all_questions(DiscoveryInputs())}
    q_full = {q.target_path for q in ENGINE.all_questions(DiscoveryInputs(draft=_full_draft()))}
    assert "objective.primary" in q_empty and "objective.primary" not in q_full
    assert "data.required" in q_empty and "data.required" not in q_full
    assert q_full == set()  # a complete, consistent draft → nothing to ask


def test_outbound_direction_triggers_contact_policy_question() -> None:
    d = _full_draft()
    d["direction"] = "outbound"
    qs = ENGINE.all_questions(DiscoveryInputs(draft=d))
    q = next(q for q in qs if q.target_path == "policies.contact_policy_hooks")
    assert q.kind is QuestionKind.POLICY_RISK and q.blocking
    d["direction"] = "inbound"
    assert not any(q.target_path == "policies.contact_policy_hooks" for q in ENGINE.all_questions(DiscoveryInputs(d)))


def test_handoff_question_only_when_policy_offers_handoff() -> None:
    d = _full_draft()
    assert not any(q.target_path == "handoff_rules" for q in ENGINE.all_questions(DiscoveryInputs(d)))
    d["policies"]["unknown_question_policy"]["default"] = "OFFER_HUMAN_HANDOFF"
    q = next(q for q in ENGINE.all_questions(DiscoveryInputs(d)) if q.target_path == "handoff_rules")
    assert q.kind is QuestionKind.BUSINESS_DECISION and q.blocking


def test_persuasive_objective_asks_for_objections() -> None:
    d = _full_draft()
    d["objective"]["primary"] = {"kind": "sales_conversion", "description": "sell the premium plan"}
    qs = ENGINE.all_questions(DiscoveryInputs(d))
    q = next(q for q in qs if q.target_path == "coverage.objections")
    assert q.kind is QuestionKind.BUSINESS_DECISION and not q.blocking and q.proposed_default is None


# --------------------------------------------------------------------------- sources


def test_gap_classes_map_to_kinds_and_blocking() -> None:
    gaps = [
        KnowledgeGap(
            gap_id="g1",
            tenant_id="t",
            gap_class=GapClass.REQUIRED_FOR_EXECUTION,
            description="d1",
            question_for_operator="q1",
        ),
        KnowledgeGap(
            gap_id="g2",
            tenant_id="t",
            gap_class=GapClass.OPTIONAL_IMPROVEMENT,
            description="d2",
            question_for_operator="q2",
        ),
        KnowledgeGap(
            gap_id="g3",
            tenant_id="t",
            gap_class=GapClass.POLICY_RISK,
            description="d3",
            question_for_operator="q3",
            resolved=True,
        ),
    ]
    qs = ENGINE.all_questions(DiscoveryInputs(draft=_full_draft(), gaps=gaps))
    by_path = {q.target_path: q for q in qs}
    assert by_path["knowledge.gaps.g1"].kind is QuestionKind.BLOCKING_GAP and by_path["knowledge.gaps.g1"].blocking
    assert by_path["knowledge.gaps.g2"].kind is QuestionKind.OPTIONAL and not by_path["knowledge.gaps.g2"].blocking
    assert "knowledge.gaps.g3" not in by_path  # resolved gaps are not re-asked
    assert by_path["knowledge.gaps.g1"].text == "q1" and "g1" in by_path["knowledge.gaps.g1"].source_refs


def test_pending_contradiction_becomes_blocking_choice() -> None:
    cs = [
        Contradiction(contradiction_id="c1", tenant_id="t", fact_ids=["f1", "f2"], description="price differs"),
        Contradiction(
            contradiction_id="c2",
            tenant_id="t",
            fact_ids=["f3", "f4"],
            description="x",
            resolution="operator_decided",
            winning_fact_id="f3",
        ),
    ]
    qs = ENGINE.all_questions(DiscoveryInputs(draft=_full_draft(), contradictions=cs))
    assert len(qs) == 1
    q = qs[0]
    assert q.kind is QuestionKind.DATA_CONFLICT and q.blocking
    assert q.answer_type is AnswerType.CHOICE and q.options == ["f1", "f2"]
    assert q.target_path == "knowledge.contradictions.c1"


def test_preflight_findings_classified() -> None:
    fs = [
        PreflightFinding(
            reason=PreflightReason.UNAPPROVED_BUSINESS_DECISION,
            path="completion.success_rules[0]",
            message="m",
            fix_hint="approve it",
        ),
        PreflightFinding(reason=PreflightReason.VOICE_UNAVAILABLE, path="locale.voice_profile_ref", message="m"),
        PreflightFinding(reason=PreflightReason.INCOMPLETE_FIELD_DEFINITION, path="data.required[0]", message="m"),
        PreflightFinding(reason=PreflightReason.INVALID_CONFIG, path="evaluation", message="m", severity="WARN"),
    ]
    qs = {q.target_path: q for q in ENGINE.all_questions(DiscoveryInputs(draft=_full_draft(), preflight=fs))}
    assert qs["completion.success_rules[0]"].kind is QuestionKind.BUSINESS_DECISION
    assert qs["completion.success_rules[0]"].text == "approve it"
    assert qs["locale.voice_profile_ref"].kind is QuestionKind.CAPABILITY_GAP
    assert qs["data.required[0]"].kind is QuestionKind.BLOCKING_GAP and qs["data.required[0]"].blocking
    assert qs["evaluation"].kind is QuestionKind.QUALITY and not qs["evaluation"].blocking


def test_mapping_rows_produce_capability_questions() -> None:
    rows = [
        Row("check stock", "tool:lookup", "UNSUPPORTED", MappingResult.REQUIRES_TOOL),
        Row("answer menu", "knowledge:menu", "UNSUPPORTED", MappingResult.REQUIRES_KNOWLEDGE),
        Row("refund", "human", "UNSUPPORTED", MappingResult.REQUIRES_HUMAN),
        Row("video", "channel:video", "UNSUPPORTED", MappingResult.UNSUPPORTED),
        Row("arabic", "language:ar-EG", "UNVERIFIED", MappingResult.SUPPORTED),
        Row("text", "channel:text", "SUPPORTED", MappingResult.SUPPORTED),
    ]
    qs = {q.target_path: q for q in ENGINE.all_questions(DiscoveryInputs(draft=_full_draft(), mapping=rows))}
    assert (
        qs["capabilities.tool:lookup"].kind is QuestionKind.CAPABILITY_GAP and qs["capabilities.tool:lookup"].blocking
    )
    assert "new_integration_required" in qs["capabilities.tool:lookup"].options
    assert qs["capabilities.knowledge:menu"].answer_type is AnswerType.UPLOAD
    assert qs["handoff_rules"].kind is QuestionKind.BUSINESS_DECISION
    assert qs["capabilities.channel:video"].options == ["change_composition", "drop_requirement"]
    assert not qs["capabilities.language:ar-EG"].blocking
    assert "capabilities.channel:text" not in qs


# --------------------------------------------------------------- prioritization (QV-COP-004)


def test_ranking_is_deterministic_and_band_ordered() -> None:
    inp = DiscoveryInputs(
        gaps=[
            KnowledgeGap(
                gap_id="g",
                tenant_id="t",
                gap_class=GapClass.IMPORTANT_FOR_QUALITY,
                description="d",
                question_for_operator="q",
            )
        ],
        contradictions=[Contradiction(contradiction_id="c", tenant_id="t", fact_ids=["a", "b"], description="x")],
    )
    a = ENGINE.all_questions(inp)
    b = ENGINE.all_questions(inp)
    assert [q.question_id for q in a] == [q.question_id for q in b]
    assert [q.priority for q in a] == sorted(q.priority for q in a)
    kinds = [q.kind for q in a]
    # blocking gaps (channels/knowledge) precede the data conflict, which precedes policy/business, then quality
    assert kinds.index(QuestionKind.BLOCKING_GAP) < kinds.index(QuestionKind.DATA_CONFLICT)
    assert kinds.index(QuestionKind.DATA_CONFLICT) < kinds.index(QuestionKind.BUSINESS_DECISION)
    assert kinds[-1] is QuestionKind.QUALITY or kinds[-1] is QuestionKind.OPTIONAL


def test_progressive_disclosure_within_band() -> None:
    qs = ENGINE.all_questions(DiscoveryInputs())
    bd = [q.target_path for q in qs if q.kind is QuestionKind.BUSINESS_DECISION and q.blocking]
    assert bd.index("objective.primary") < bd.index("direction") < bd.index("data.required")
    assert bd.index("data.required") < bd.index("outcome_schema.primary") < bd.index("completion.success_rules")


def test_prioritizer_blocking_beats_non_blocking_in_same_band() -> None:
    p = QuestionPrioritizer()
    qs = ENGINE.all_questions(
        DiscoveryInputs(
            draft=_full_draft(),
            gaps=[
                KnowledgeGap(
                    gap_id="opt",
                    tenant_id="t",
                    gap_class=GapClass.OPTIONAL_IMPROVEMENT,
                    description="d",
                    question_for_operator="q",
                ),
                KnowledgeGap(
                    gap_id="req",
                    tenant_id="t",
                    gap_class=GapClass.REQUIRED_FOR_EXECUTION,
                    description="d",
                    question_for_operator="q",
                ),
            ],
        )
    )
    ranked = p.rank(list(reversed(qs)))
    assert ranked[0].target_path == "knowledge.gaps.req"


def test_question_id_is_stable_across_processes() -> None:
    local = question_id_for("objective.primary", "hello")
    code = "from qevion.copilot.discovery import question_id_for as f; print(f('objective.primary','hello'))"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.strip()
    assert out == local and local.startswith("q_")


# ------------------------------------------------------------- business truth guard (QV-COP-007)


def test_business_decisions_never_carry_free_text_defaults() -> None:
    inp = DiscoveryInputs(
        preflight=[
            PreflightFinding(reason=PreflightReason.UNAPPROVED_BUSINESS_DECISION, path="completion.x", message="m")
        ],
        mapping=[Row("refund", "human", "UNSUPPORTED", MappingResult.REQUIRES_HUMAN)],
    )
    for q in ENGINE.all_questions(inp):
        if q.kind is QuestionKind.BUSINESS_DECISION and q.answer_type is AnswerType.FREE_TEXT:
            assert q.proposed_default is None, q.target_path
        assert q.why_it_matters and q.target_path


def test_structural_choices_may_propose_structure_not_truth() -> None:
    qs = {q.target_path: q for q in ENGINE.all_questions(DiscoveryInputs())}
    # enum/structure proposals are allowed
    assert qs["policies.unknown_question_policy.default"].proposed_default == "STATE_LIMITATION"
    assert qs["outcome_schema.primary"].answer_type is AnswerType.CONFIRM_PROPOSAL
    # business free-text has no default
    assert qs["objective.primary"].proposed_default is None
    assert qs["completion.success_rules"].proposed_default is None


# ------------------------------------------------------------ filtering, dedupe, stop rule


def test_answered_and_deferred_paths_are_filtered() -> None:
    inp = DiscoveryInputs(answered_paths={"objective.primary", "channels"}, deferred_paths={"locale"})
    paths = {q.target_path for q in ENGINE.all_questions(inp)}
    assert {"objective.primary", "channels", "locale"}.isdisjoint(paths)
    assert "direction" in paths


def test_dedupe_by_target_path_keeps_first_source() -> None:
    d = _full_draft()
    d["policies"]["unknown_question_policy"]["default"] = "OFFER_HUMAN_HANDOFF"  # structural handoff_rules question
    inp = DiscoveryInputs(draft=d, mapping=[Row("refund", "human", "UNSUPPORTED", MappingResult.REQUIRES_HUMAN)])
    qs = [q for q in ENGINE.all_questions(inp) if q.target_path == "handoff_rules"]
    assert len(qs) == 1


def test_limit_and_stop_rule() -> None:
    assert len(ENGINE.next_questions(DiscoveryInputs(), limit=2)) == 2
    assert ENGINE.next_questions(DiscoveryInputs(), limit=0) == []
    assert not discovery_complete(ENGINE.all_questions(DiscoveryInputs()))
    d = _full_draft()
    remaining = ENGINE.all_questions(
        DiscoveryInputs(
            draft=d,
            gaps=[
                KnowledgeGap(
                    gap_id="o",
                    tenant_id="t",
                    gap_class=GapClass.OPTIONAL_IMPROVEMENT,
                    description="d",
                    question_for_operator="q",
                )
            ],
        )
    )
    assert remaining and discovery_complete(remaining)  # only optional left → discovery complete
