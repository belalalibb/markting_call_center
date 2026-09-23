"""Silero VAD turn adapter (P4). Probability source = Silero ONNX model; state machine = energy.py's.

Design (A9: 2 vCPU / no GPU):
  * The ONNX model + onnxruntime are optional. If either is missing, the adapter still constructs, but
    `capabilities()` declares `feature:vad:silero` UNVERIFIED and `new_detector()` falls back to the RMS
    probability with `detector="silero_fallback_energy"` so downstream events remain honest (QV-CAP).
  * Silero expects 16 kHz mono windows of 512 samples; frames arriving at 24 kHz are decimated 3:2 (linear).
  * `ProbFn` protocol is preserved so the shared detector can be unit-tested with a fake model.
"""

from __future__ import annotations

import struct
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from qevion.adapters.turn.energy import EnergyTurnDetector, rms_probability
from qevion.contracts.composition import AdapterCapabilities, Capability, CapabilityState
from qevion.contracts.provider import ProviderRole

SILERO_RATE = 16000
SILERO_WINDOW = 512  # samples @16k = 32 ms
DEFAULT_MODEL = Path(__file__).resolve().parents[3] / "models" / "silero_vad.onnx"

ModelFn = Callable[[list[float]], float]  # 16 kHz float32 window → speech probability


def resample_24k_to_16k(pcm16: bytes) -> list[float]:
    """Linear 3:2 decimation, output normalized floats in [-1, 1]."""
    n = len(pcm16) // 2
    if n == 0:
        return []
    s = struct.unpack(f"<{n}h", pcm16[: n * 2])
    out: list[float] = []
    m = (n * 2) // 3
    for i in range(m):
        pos = i * 1.5
        j = int(pos)
        frac = pos - j
        a = s[j]
        b = s[j + 1] if j + 1 < n else a
        out.append((a + (b - a) * frac) / 32768.0)
    return out


@dataclass
class SileroProbability:
    """Stateful windowed probability: buffers 16 kHz samples, runs the model per 512-sample window,
    returns the max probability seen in the frame (barge-in must not miss a short burst)."""

    model: ModelFn
    _buf: list[float] = field(default_factory=list)
    _last: float = 0.0

    def __call__(self, pcm16: bytes) -> float:
        self._buf.extend(resample_24k_to_16k(pcm16))
        best = 0.0
        ran = False
        while len(self._buf) >= SILERO_WINDOW:
            window, self._buf = self._buf[:SILERO_WINDOW], self._buf[SILERO_WINDOW:]
            best = max(best, float(self.model(window)))
            ran = True
        if ran:
            self._last = best
        return self._last


class _OnnxModel:
    """Silero VAD v5 ONNX wrapper (input, state, sr) → (output, state)."""

    def __init__(self, path: Path) -> None:
        import numpy as np  # noqa: PLC0415 — optional heavy import
        import onnxruntime as ort  # noqa: PLC0415

        self._np = np
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 1
        opts.inter_op_num_threads = 1
        self._sess = ort.InferenceSession(str(path), sess_options=opts, providers=["CPUExecutionProvider"])
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._sr = np.array(SILERO_RATE, dtype=np.int64)

    def __call__(self, window: list[float]) -> float:
        np = self._np
        x = np.asarray(window, dtype=np.float32).reshape(1, -1)
        out, self._state = self._sess.run(None, {"input": x, "state": self._state, "sr": self._sr})
        return float(out[0][0])


def load_model(path: Path | None = None) -> ModelFn | None:
    p = path or DEFAULT_MODEL
    if not p.is_file():
        return None
    try:
        return _OnnxModel(p)
    except Exception:  # noqa: BLE001 — missing onnxruntime / incompatible model → fallback
        return None


class SileroTurnAdapter:
    name = "silero"

    def __init__(self, model: ModelFn | None = None, *, model_path: Path | None = None, autoload: bool = True) -> None:
        self._model: ModelFn | None = model
        if self._model is None and autoload:
            self._model = load_model(model_path)
        self.model_available = self._model is not None

    def capabilities(self) -> AdapterCapabilities:
        vad_state = CapabilityState.SUPPORTED if self.model_available else CapabilityState.UNVERIFIED
        return AdapterCapabilities(
            adapter=self.name,
            role=ProviderRole.TURN,
            capabilities=[
                Capability(name="feature:barge_in", state=CapabilityState.SUPPORTED),
                Capability(
                    name="feature:end_of_turn",
                    state=CapabilityState.PARTIAL,
                    notes="VAD silence-based; pair with smart_turn",
                ),
                Capability(
                    name="feature:vad:silero",
                    state=vad_state,
                    notes=None
                    if self.model_available
                    else "models/silero_vad.onnx or onnxruntime missing → energy fallback",
                ),
                Capability(name="language:any", state=CapabilityState.SUPPORTED, notes="language-agnostic VAD"),
            ],
        )

    def new_detector(self) -> EnergyTurnDetector:
        if self._model is None:
            return EnergyTurnDetector(prob_fn=rms_probability, detector_name="silero_fallback_energy")
        return EnergyTurnDetector(prob_fn=SileroProbability(self._model), detector_name=self.name)


def describe(adapter: SileroTurnAdapter) -> dict[str, Any]:
    return {"adapter": adapter.name, "model_available": adapter.model_available, "model_path": str(DEFAULT_MODEL)}


__all__ = ["SileroProbability", "SileroTurnAdapter", "describe", "load_model", "resample_24k_to_16k"]
