#!/usr/bin/env bash
# Controlled A/B window: fresh baseline → A → B → A+B, same build/clips/corpus/server config/harness, consecutive.
# Each result is committed + pushed to the experiment branch as soon as it exists (reset-safe).
# usage: OPENAI_API_KEY=… bash scripts/latency_ab_all.sh [WINDOW_ID]
set -uo pipefail
cd "$(dirname "$0")/.."
# Experiment evidence must never land on main.
BR="$(git rev-parse --abbrev-ref HEAD)"
if [ "$BR" != "latency-ab-experiment" ]; then
  echo "REFUSED: run only on branch latency-ab-experiment (current: $BR)" >&2; exit 3
fi
# Safety gate: dependency / barrier / missing-result tests must pass on this exact build before any live run.
if ! .venv/bin/python -m pytest -q tests/test_latency_b_dependency_safety.py tests/test_latency_option_b.py \
     tests/test_latency_option_a.py >/dev/null 2>&1; then
  echo "REFUSED: offline A/B safety tests fail on this build" >&2; exit 5
fi
WIN="${1:-w$(date -u +%Y%m%dT%H%M)}"
DIR="evidence/latency/ab/$WIN"
mkdir -p "$DIR"
BUILD="$(git rev-parse HEAD)"
echo "{\"window\":\"$WIN\",\"build\":\"$BUILD\",\"started\":\"$(date -u +%FT%TZ)\"}" > "$DIR/window.json"

# No-credit rule: a provider refusal is an INVALID run, never performance evidence. Probe before each mode.
preflight() {
  .venv/bin/python scripts/latency_provider_preflight.py "$DIR/preflight_$1.json"
}
run() {
  local mode="$1" ack="$2" par="$3" out="$DIR/$1.json"
  [ -s "$out" ] && python3 -c "import json,sys;d=json.load(open('$out'));sys.exit(0 if 'summary' in d else 1)" && return 0
  if ! preflight "$mode"; then
    echo "INVALID: provider refused before mode $mode (see $DIR/preflight_$mode.json) — stopping window" | tee -a .cache_ab.log
    git add "$DIR" && git commit -qm "evidence(latency-ab/$WIN): INVALID window — provider refused before $mode" && git push -q origin HEAD:latency-ab-experiment
    exit 4
  fi
  bash scripts/latency_ab.sh "$out" "$ack" "$par" 2 >> .cache_ab.log 2>&1
  git add "$DIR" && git commit -qm "evidence(latency-ab/$WIN): $mode ack=$ack parallel=$par" && git push -q origin HEAD:latency-ab-experiment
}
run baseline 0 0
run A 1 0
run B 0 1
run AB 1 1
echo "{\"window\":\"$WIN\",\"build\":\"$BUILD\",\"finished\":\"$(date -u +%FT%TZ)\"}" > "$DIR/window_done.json"
.venv/bin/python scripts/latency_ab_eval.py "$DIR" >> .cache_ab.log 2>&1
git add "$DIR" && git commit -qm "evidence(latency-ab/$WIN): verdict" && git push -q origin HEAD:latency-ab-experiment
echo ALL_DONE >> .cache_ab.log
