"""Evaluation report model (QV-EVAL-001 attribution, QV-EVAL-006 JSON + Markdown with evidence pointers)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class Attribution(StrEnum):
    """QV-EVAL-001: every score is attributed to one layer."""

    A = "A_provider"
    B = "B_qevion_runtime"
    C = "C_end_to_end"
    D = "D_configuration_copilot"


@dataclass
class GraderOutcome:
    grader: str
    passed: bool
    detail: str = ""
    attribution: Attribution = Attribution.B
    model_graded: bool = False  # QV-EVAL-002: deterministic first; model graders are labeled
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class CaseReport:
    case_id: str
    track: str  # "copilot" | "runtime"
    tags: list[str] = field(default_factory=list)
    graders: list[GraderOutcome] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return all(g.passed for g in self.graders)

    @property
    def failed_graders(self) -> list[str]:
        return [g.grader for g in self.graders if not g.passed]


@dataclass
class EvalReport:
    report_id: str
    cases: list[CaseReport]
    evidence_refs: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.cases)

    def by_track(self, track: str) -> list[CaseReport]:
        return [c for c in self.cases if c.track == track]

    def by_attribution(self) -> dict[str, dict[str, int]]:
        out: dict[str, dict[str, int]] = {}
        for c in self.cases:
            for g in c.graders:
                row = out.setdefault(str(g.attribution), {"passed": 0, "failed": 0})
                row["passed" if g.passed else "failed"] += 1
        return out

    def aggregate(self) -> dict[str, Any]:
        tracks = sorted({c.track for c in self.cases})
        return {
            "report_id": self.report_id,
            "passed": self.passed,
            "cases": len(self.cases),
            "cases_passed": sum(1 for c in self.cases if c.passed),
            "graders": sum(len(c.graders) for c in self.cases),
            "graders_passed": sum(1 for c in self.cases for g in c.graders if g.passed),
            "model_graded": sum(1 for c in self.cases for g in c.graders if g.model_graded),
            "tracks": {
                t: {"cases": len(self.by_track(t)), "passed": sum(1 for c in self.by_track(t) if c.passed)}
                for t in tracks
            },
            "by_attribution": self.by_attribution(),
            "failed": {c.case_id: c.failed_graders for c in self.cases if not c.passed},
            "evidence_refs": list(self.evidence_refs),
            "meta": dict(self.meta),
        }

    def to_json(self) -> str:
        return json.dumps(
            {"schema": "qevion.eval_report.v1", "aggregate": self.aggregate(), "cases": [asdict(c) for c in self.cases]},
            indent=2,
            sort_keys=True,
            default=str,
        )

    def to_markdown(self) -> str:
        agg = self.aggregate()
        lines = [
            f"# QEVION Evaluation Report `{self.report_id}`",
            "",
            f"**Result:** {'PASS' if agg['passed'] else 'FAIL'} — {agg['cases_passed']}/{agg['cases']} cases, "
            f"{agg['graders_passed']}/{agg['graders']} graders (model-graded: {agg['model_graded']})",
            "",
            "## Attribution (QV-EVAL-001)",
            "",
            "| layer | passed | failed |",
            "|---|---|---|",
        ]
        for layer, row in sorted(agg["by_attribution"].items()):
            lines.append(f"| {layer} | {row['passed']} | {row['failed']} |")
        lines += ["", "## Cases", "", "| track | case | result | failed graders |", "|---|---|---|---|"]
        for c in self.cases:
            lines.append(
                f"| {c.track} | `{c.case_id}` | {'PASS' if c.passed else 'FAIL'} | {', '.join(c.failed_graders) or '—'} |"
            )
        lines += ["", "## Grader detail", ""]
        for c in self.cases:
            lines.append(f"### `{c.case_id}` ({c.track})")
            lines.append("")
            for g in c.graders:
                mark = "✔" if g.passed else "✘"
                lines.append(f"- {mark} `{g.grader}` [{g.attribution}] {g.detail}")
            lines.append("")
        if self.evidence_refs:
            lines += ["## Evidence", ""] + [f"- `{r}`" for r in self.evidence_refs] + [""]
        return "\n".join(lines)
