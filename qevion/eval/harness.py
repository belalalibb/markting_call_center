"""Evaluation harness — both tracks → one EvalReport (JSON + Markdown), QV-EVAL-004/005/006."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from qevion.eval.copilot_eval import CopilotEvalCase, run_copilot_eval
from qevion.eval.corpus import CorpusCase, corpus_manifest, default_corpus
from qevion.eval.report import EvalReport
from qevion.eval.runtime_eval import cases_from_corpus, run_runtime_eval


async def run_eval(
    *,
    copilot_cases: list[CopilotEvalCase] | None = None,
    corpus: list[CorpusCase] | None = None,
    include_holdout: bool = True,
    report_id: str = "eval_local",
) -> EvalReport:
    corpus_cases = corpus or default_corpus()
    if not include_holdout:
        corpus_cases = [c for c in corpus_cases if not c.holdout]
    cop = run_copilot_eval(copilot_cases)
    rt = await run_runtime_eval(cases_from_corpus(corpus_cases))
    manifest = corpus_manifest(corpus_cases)
    return EvalReport(
        report_id=report_id,
        cases=[*cop, *rt],
        meta={
            "corpus_version": manifest["version"],
            "corpus_count": manifest["count"],
            "holdout_included": include_holdout,
            "tracks": ["copilot", "runtime"],
            "mode": "text",  # audio-mode subset runs only with license-clean fixtures present (QV-EVAL-005)
        },
    )


def write_reports(report: EvalReport, out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    js = out_dir / "eval_report.json"
    md = out_dir / "eval_report.md"
    cm = out_dir / "corpus_manifest.json"
    js.write_text(report.to_json())
    md.write_text(report.to_markdown())
    cm.write_text(json.dumps(corpus_manifest(), ensure_ascii=False, indent=2, sort_keys=True))
    report.evidence_refs.extend(str(p) for p in (js, md, cm))
    return {"json": str(js), "markdown": str(md), "corpus_manifest": str(cm), "passed": report.passed}
