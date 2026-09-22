#!/usr/bin/env bash
# Restore sandbox state needed to continue work (idempotent). Extended by later phases.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$ROOT"
echo "== QEVION restore =="; git status --short | head -20
echo "HEAD: $(git rev-parse --short HEAD)  last cp tag: $(git tag --list 'cp/*' | sort -V | tail -1)"
if [[ -f pyproject.toml ]]; then
  [[ -d .venv ]] || python3 -m venv .venv
  . .venv/bin/activate && (pip install -q -e '.[dev]' 2>/dev/null || pip install -q -e .) && echo "python deps ok"
fi
if [[ -f web/package.json ]]; then (cd web && ([[ -d node_modules ]] || npm ci --silent)) && echo "web deps ok"; fi
git ls-remote origin main >/dev/null 2>&1 && echo "remote: reachable" || echo "remote: UNREACHABLE — apply credential per protocol §6"
echo "Next: QEVION_WORK_STATE.md -> 'Exact next action'"
