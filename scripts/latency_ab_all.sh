#!/usr/bin/env bash
# Baseline → A → A+B, same build; commits+pushes each result as soon as it exists (reset-safe).
set -uo pipefail
cd "$(dirname "$0")/.."
run() {
  local out="$1" ack="$2" par="$3"
  [ -s "$out" ] && python3 -c "import json,sys;d=json.load(open('$out'));sys.exit(0 if 'summary' in d else 1)" && return 0
  bash scripts/latency_ab.sh "$out" "$ack" "$par" 2 >> .cache_ab.log 2>&1
  git add "$out" && git commit -qm "evidence(latency-ab): $(basename "$out") ack=$ack parallel=$par" && git push -q origin main
}
run evidence/latency/ab_baseline.json 0 0
run evidence/latency/ab_A.json 1 0
run evidence/latency/ab_AB.json 1 1
echo ALL_DONE >> .cache_ab.log
