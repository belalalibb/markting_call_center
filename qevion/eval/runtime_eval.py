"""Runtime evaluation track — text-mode (QV-EVAL-005) cases run through the simulation runner on the same Core,
graded by the deterministic simulation graders (QV-EVAL-002) and attributed per QV-EVAL-001:
  provider-facing grader (repetition) → A_provider (mock here); budget → C_end_to_end
  Core behaviour graders (claims, confirmation, …)   → B_qevion_runtime
Determinism is additionally checked via replay (QV-REPLAY / QV-ACC-019) for every case.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from qevion.contracts.activity import ActivityBlueprint
from qevion.contracts.simulation import GraderId, ScenarioCase
from qevion.eval.corpus import CorpusCase, default_corpus
from qevion.eval.report import Attribution, CaseReport, GraderOutcome
from qevion.replay.player import replay
from qevion.replay.recorder import record
from qevion.simulation.runner import ScenarioRunner, grade

_ATTRIBUTION: dict[str, Attribution] = {
    GraderId.BUDGET_RESPECTED.value: Attribution.C,
    GraderId.REPETITION_BELOW_THRESHOLD.value: Attribution.A,
}


@dataclass
class RuntimeEvalCase:
    case_id: str
    blueprint: ActivityBlueprint
    scenario: ScenarioCase
    tags: list[str] = field(default_factory=list)
    corpus_ref: str | None = None


def cases_from_corpus(corpus: list[CorpusCase] | None = None) -> list[RuntimeEvalCase]:
    out: list[RuntimeEvalCase] = []
    for c in corpus or default_corpus():
        bp = c.blueprint()
        out.append(
            RuntimeEvalCase(
                case_id=c.corpus_id, blueprint=bp, scenario=c.scenario(bp), tags=list(c.tags), corpus_ref=c.corpus_id
            )
        )
    return out


async def run_runtime_case(case: RuntimeEvalCase) -> CaseReport:
    runner = ScenarioRunner(case.blueprint)
    run = await runner.run_case(case.scenario)
    result = grade(run)
    graders = [
        GraderOutcome(
            grader=str(g.grader.value),
            passed=g.passed,
            detail=g.detail,
            attribution=_ATTRIBUTION.get(str(g.grader.value), Attribution.B),
            model_graded=g.model_graded,
            evidence={"category": g.category, "blueprint_paths": list(g.blueprint_paths)},
        )
        for g in result.graders
    ]
    rec = record(run, case.blueprint)
    rep = await replay(rec, case.blueprint)
    graders.append(
        GraderOutcome(
            grader="replay_deterministic",
            passed=rep.deterministic,
            detail=f"events={rep.recorded_events} divergences={len(rep.divergences)}",
            attribution=Attribution.B,
            evidence={"recording_id": rec.recording_id, "digest": rep.recorded_digest},
        )
    )
    evidence: dict[str, Any] = {
        "session_id": result.session_id,
        "primary_outcome": result.primary_outcome,
        "activity_state": result.activity_state,
        "turn_count": result.turn_count,
        "tool_call_count": result.tool_call_count,
        "event_count": result.event_count,
        "corpus_ref": case.corpus_ref,
        "error": result.error,
    }
    return CaseReport(case_id=case.case_id, track="runtime", tags=list(case.tags), graders=graders, evidence=evidence)


async def run_runtime_eval(cases: list[RuntimeEvalCase] | None = None) -> list[CaseReport]:
    return [await run_runtime_case(c) for c in cases or cases_from_corpus()]
