"""`make eval` — run both evaluation tracks and write JSON + Markdown reports (QV-EVAL-006).

Usage: .venv/bin/python scripts/run_eval.py [out_dir] [--no-holdout]
Exit code 0 = all graders passed, 1 = at least one failure (report still written).
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from qevion.eval.harness import run_eval, write_reports


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    out = Path(args[0]) if args else Path("evidence/eval/latest")
    include_holdout = "--no-holdout" not in argv
    report = asyncio.run(run_eval(include_holdout=include_holdout, report_id=out.name))
    paths = write_reports(report, out)
    print(json.dumps({**paths, "aggregate": report.aggregate()}, ensure_ascii=False, indent=2, default=str))
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
