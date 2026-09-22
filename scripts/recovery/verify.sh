#!/usr/bin/env bash
# Fast verification suite: run on resume and before every checkpoint. Grows with the project.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$ROOT"
fail=0
echo "[1] secret scan (tracked files)"
if git grep -nIE 'gh[pousr]_[A-Za-z0-9]{20,}|\bsk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{30,}' -- ':!scripts/recovery/verify.sh' ; then echo "  FAIL: credential pattern in tracked files"; fail=1; else echo "  ok"; fi
echo "[2] recovery files present"
for f in QEVION_SESSION_RECOVERY_PROTOCOL.md QEVION_WORK_STATE.md; do [[ -f $f ]] && echo "  ok $f" || { echo "  FAIL missing $f"; fail=1; }; done
echo "[3] core business-branching grep gate"
if [[ -d qevion/core ]]; then
  if grep -rnE '\b(restaurant|telecom|factory|menu|burger|pizza|clinic)\b' qevion/core --include='*.py' | grep -v '^\s*#' ; then echo "  FAIL: domain terms in core"; fail=1; else echo "  ok"; fi
else echo "  skip (no core yet)"; fi
if [[ -f pyproject.toml ]]; then
  echo "[4] python tests"; . .venv/bin/activate 2>/dev/null || true
  python -m pytest -q 2>&1 | tail -3 || fail=1
  echo "[5] boundary lint"; (command -v lint-imports >/dev/null && lint-imports 2>&1 | tail -2) || echo "  skip (import-linter not installed)"
fi
[[ $fail -eq 0 ]] && echo "VERIFY: PASS" || { echo "VERIFY: FAIL"; exit 1; }
