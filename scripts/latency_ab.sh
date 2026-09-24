#!/usr/bin/env bash
# Run the latency corpus against a fresh server with the given flags. Same code, same clips, same harness.
# usage: OPENAI_API_KEY=… bash scripts/latency_ab.sh OUT.json TOOL_ACK(0|1) PARALLEL(0|1) [REPEAT]
set -euo pipefail
cd "$(dirname "$0")/.."
OUT="$1"; ACK="$2"; PAR="$3"; REP="${4:-2}"
PID=$(ss -ltnp | grep ":8000 " | grep -oP 'pid=\K[0-9]+' | head -1 || true); [ -n "$PID" ] && kill "$PID" && sleep 2
env -u OPENAI_API_KEY -u QEVION_ADMIN_TOKEN QEVION_LATENCY_TRACE=1 QEVION_TOOL_ACK="$ACK" QEVION_PARALLEL_TOOLS="$PAR" \
  nohup .venv/bin/python -m qevion.main > .cache_server.log 2>&1 &
for _ in $(seq 30); do curl -sf localhost:8000/api/health >/dev/null && break; sleep 1; done
QEVION_TOOL_ACK="$ACK" QEVION_PARALLEL_TOOLS="$PAR" QEVION_TTS_CACHE="${QEVION_TTS_CACHE:-$PWD/.cache_tts}" \
  .venv/bin/python scripts/latency_corpus.py "$OUT" --repeat "$REP"
