#!/usr/bin/env bash
# Mirror of .github/workflows/ci.yml python job. Run before every push: scripts/ci_local.sh
set -euo pipefail
cd "$(dirname "$0")/.."
V=.venv/bin
$V/ruff check qevion tests scripts
$V/ruff format --check qevion tests scripts
$V/mypy
$V/lint-imports
$V/python scripts/gen_schemas.py --check
mkdir -p evidence/ci
$V/pytest -q -p no:cacheprovider --junitxml=evidence/ci/junit.xml
bash scripts/recovery/verify.sh
$V/pip-licenses --format=json > evidence/ci/licenses.json
$V/python scripts/license_gate.py evidence/ci/licenses.json docs/registry/licenses.yaml
echo "CI_LOCAL: PASS"
