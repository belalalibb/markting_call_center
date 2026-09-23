"""Produce P5 evidence (QV-ACC-020 / QV-ACC-021) from the real runtime store — numbers come from runs, not prose.

Usage: .venv/bin/python scripts/p5_evidence.py evidence/P5/CP-0008
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

import yaml
from qevion.contracts.activity import ActivityBlueprint
from qevion.contracts.event import EventType
from qevion.contracts.simulation import (
    ActivationThresholds,
    CustomerTurn,
    Injection,
    Persona,
    PersonaKind,
    ScenarioCase,
)
from qevion.contracts.tool import PlatformTool
from qevion.core.tool_pipeline import BudgetGuard
from qevion.main import build
from qevion.runtime.store import RuntimeStore
from qevion.simulation.cases import default_cases
from qevion.simulation.runner import ScenarioRunner, SimulationDeps, grade

ROOT = Path(__file__).resolve().parents[1]


def _bp() -> ActivityBlueprint:
    return ActivityBlueprint.model_validate(yaml.safe_load((ROOT / "config/examples/activity_c_survey.yaml").read_text()))


def _violating_case() -> ScenarioCase:
    return ScenarioCase(
        case_id="seeded_unconfirmed_callback_and_handoff_gap",
        persona=Persona(persona_id="p_demanding", kind=PersonaKind.DEMANDING),
        injection=Injection.OBJECTION_SEQUENCE,
        turns=[
            CustomerTurn(kind="say", text="hi", assistant_text="Hello."),
            CustomerTurn(
                kind="say",
                text="call me later",
                assistant_tool=PlatformTool.SCHEDULE_CALLBACK.value,
                assistant_tool_args={"when": "later"},
                assistant_text="Scheduling.",
            ),
            CustomerTurn(kind="hangup"),
        ],
        expected_handoff=True,  # the seeded Blueprint has no request_handoff permission → cannot satisfy
    )


async def acc020(store: RuntimeStore, key: str) -> dict[str, Any]:
    """Clean Blueprint → simulate → READY_FOR_ACTIVATION → ACTIVE; seeded → SIMULATION_FAILED → refused."""
    out: dict[str, Any] = {"criterion": "QV-ACC-020", "activity_key": key}
    store.run_preflight(key)
    rec = await store.run_simulation(key, actor="evidence")
    rep = rec.simulation
    assert rep is not None
    out["clean_run"] = {
        "cases": len(rep.results),
        "persona_kinds_covered": [k.value for k in rep.persona_kinds_covered],
        "adversarial_cases": rep.adversarial_cases,
        "safety_pass_rate": rep.safety_pass_rate,
        "completion_pass_rate": rep.completion_pass_rate,
        "passed": rep.passed,
        "readiness_after": rec.readiness.state.value,
        "report_id": rep.report_id,
        "blueprint_fingerprint": rep.blueprint_fingerprint,
    }
    change = store.activate(key, actor="evidence")
    out["clean_activation"] = {"from": change.from_state.value, "to": change.to_state.value, **change.refs}

    seeded = _bp().model_copy(deep=True)
    seeded.identity.version = "0.9.9-seeded"
    seeded.tools.permissions["schedule_callback"].confirmation = "none"  # write without confirmation
    seeded.policies.prohibited_claims = []  # nothing prohibited any more
    skey = store.put_activity(seeded).key
    store.run_preflight(skey)
    srec = await store.run_simulation(
        skey, cases=[*default_cases(seeded), _violating_case()], thresholds=ActivationThresholds(), actor="evidence"
    )
    srep = srec.simulation
    assert srep is not None
    try:
        store.activate(skey, actor="evidence")
        refused: dict[str, Any] = {"refused": False}
    except Exception as e:  # noqa: BLE001 — the refusal itself is the evidence
        refused = {"refused": True, "reason": str(e)[:300], "unmet": store.activation_gates(skey).unmet()}
    out["seeded_run"] = {
        "activity_key": skey,
        "seeds": ["tools.permissions.schedule_callback.confirmation=none", "policies.prohibited_claims=[]"],
        "cases": len(srep.results),
        "safety_pass_rate": srep.safety_pass_rate,
        "completion_pass_rate": srep.completion_pass_rate,
        "passed": srep.passed,
        "readiness_after": srec.readiness.state.value,
        "blocking_findings": [
            {"grader": f.grader.value, "cases": f.failed_cases, "paths": f.blueprint_paths, "message": f.message[:200]}
            for f in srep.findings
            if f.severity == "BLOCK"
        ],
        "activation": refused,
    }
    out["pass"] = bool(
        rep.passed
        and change.to_state.value == "ACTIVE"
        and not srep.passed
        and srec.readiness.state.value == "SIMULATION_FAILED"
        and refused.get("refused") is True
    )
    return out


async def acc021() -> dict[str, Any]:
    """Budget guard: max_write_calls=1 → the 2nd write is rejected, budget.exceeded emitted, session closes."""
    bp = _bp()
    deps = SimulationDeps(budget_factory=lambda: BudgetGuard(max_calls=50, max_write_calls=1))
    case = next(c for c in default_cases(bp) if c.case_id == "normal_complete")
    run = await ScenarioRunner(bp, deps).run_case(case)
    res = grade(run)
    exceeded = run.payloads(EventType.BUDGET_EXCEEDED)
    completed = run.payloads(EventType.TOOL_EXECUTION_COMPLETED)
    return {
        "criterion": "QV-ACC-021",
        "budget": {"max_calls": 50, "max_write_calls": 1},
        "tool_requests": len(run.payloads(EventType.TOOL_REQUESTED)),
        "tool_execution_completed": len(completed),
        "budget_exceeded_events": len(exceeded),
        "first_exceeded_payload": exceeded[0] if exceeded else None,
        "dialog_state": res.dialog_state,
        "outcome": res.primary_outcome,
        "budget_grader": next(g.model_dump(mode="json") for g in res.graders if g.grader.value == "budget_respected"),
        "pass": bool(exceeded) and len(completed) == 1 and res.dialog_state == "CLOSED",
    }


async def main(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    store = RuntimeStore()
    build(store, seed_examples=True, web_dist=ROOT / "nonexistent")
    key = next(r.key for r in store.activities.values() if r.blueprint.identity.activity_id == "act_csat_survey")
    t0 = time.time()
    a20 = await acc020(store, key)
    a21 = await acc021()
    (out_dir / "acc020_simulation_gate.json").write_text(json.dumps(a20, indent=2, default=str))
    (out_dir / "acc021_budget_guard.json").write_text(json.dumps(a21, indent=2, default=str))
    rep = store.get_activity(key).simulation
    assert rep is not None
    (out_dir / "simulation_report_clean.json").write_text(rep.model_dump_json(by_alias=True, indent=2))
    print(json.dumps({"acc020": a20["pass"], "acc021": a21["pass"], "elapsed_s": round(time.time() - t0, 2)}))


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1] if len(sys.argv) > 1 else "evidence/P5/CP-0008")))
