#!/usr/bin/env bash
# Fetch optional local models (not tracked). Silero VAD v5 ONNX — MIT licence (snakers4/silero-vad).
# Usage: bash scripts/fetch_models.sh   → models/silero_vad.onnx (+ needs `pip install onnxruntime`)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; mkdir -p "$ROOT/models"
OUT="$ROOT/models/silero_vad.onnx"
URL="https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx"
[[ -s "$OUT" ]] || curl -fsSL -o "$OUT" "$URL"
sha256sum "$OUT"
