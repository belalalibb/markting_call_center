"""Energy-based turn detector (deterministic; the mock and the CPU fallback).

Implements the `turn.v1` taxonomy (§30): speech_start → speech_continuing → speech_pause →
end_of_turn_candidate → end_of_turn, plus barge_in when the user speaks while the assistant speaks.
Silero (silero.py) swaps only the probability source; this state machine is shared.
"""

from __future__ import annotations

import struct
from collections.abc import Callable
from dataclasses import dataclass, field

from qevion.contracts.composition import AdapterCapabilities, Capability, CapabilityState
from qevion.contracts.provider import ProviderRole, TurnDetectorConfig, TurnEvent, TurnEventType

ProbFn = Callable[[bytes], float]
SAMPLE_RATE = 24000


def rms_probability(pcm16: bytes, threshold_rms: float = 500.0) -> float:
    """Map PCM16 RMS to [0,1]; threshold_rms ≈ speech floor for 16-bit audio."""
    n = len(pcm16) // 2
    if n == 0:
        return 0.0
    samples = struct.unpack(f"<{n}h", pcm16[: n * 2])
    rms = (sum(s * s for s in samples) / n) ** 0.5
    return float(max(0.0, min(1.0, rms / (2 * threshold_rms))))


@dataclass
class EnergyTurnDetector:
    prob_fn: ProbFn = rms_probability
    detector_name: str = "energy"
    config: TurnDetectorConfig = field(default_factory=TurnDetectorConfig)
    _in_speech: bool = False
    _speech_ms: int = 0
    _silence_ms: int = 0
    _candidate_emitted: bool = False
    _barge_emitted: bool = False

    def configure(self, config: TurnDetectorConfig) -> None:
        self.config = config
        self.reset()

    def reset(self) -> None:
        self._in_speech = False
        self._speech_ms = 0
        self._silence_ms = 0
        self._candidate_emitted = False
        self._barge_emitted = False

    def push(self, pcm16: bytes, ts_ms: int, assistant_speaking: bool) -> list[TurnEvent]:
        frame_ms = max(1, int(len(pcm16) / 2 / SAMPLE_RATE * 1000))
        p = self.prob_fn(pcm16)
        voiced = p >= self.config.threshold
        out: list[TurnEvent] = []

        def ev(t: TurnEventType, conf: float = 1.0) -> TurnEvent:
            return TurnEvent(
                type=t,
                ts_ms=ts_ms,
                confidence=round(conf, 3),
                detector=self.detector_name,
                speech_ms=self._speech_ms,
                silence_ms=self._silence_ms,
            )

        if voiced:
            self._silence_ms = 0
            self._speech_ms += frame_ms
            if not self._in_speech:
                if self._speech_ms >= self.config.min_speech_ms:
                    self._in_speech = True
                    self._candidate_emitted = False
                    out.append(ev(TurnEventType.SPEECH_START, p))
            else:
                out.append(ev(TurnEventType.SPEECH_CONTINUING, p))
            if (
                self._in_speech
                and assistant_speaking
                and not self._barge_emitted
                and self._speech_ms >= self.config.barge_in_min_speech_ms
            ):
                self._barge_emitted = True
                out.append(ev(TurnEventType.BARGE_IN, p))
        elif self._in_speech:
            self._silence_ms += frame_ms
            if self._silence_ms >= self.config.min_silence_ms:
                out.append(ev(TurnEventType.END_OF_TURN, 1.0))
                self.reset()
            elif self._silence_ms >= self.config.min_silence_ms // 2 and not self._candidate_emitted:
                self._candidate_emitted = True
                out.append(ev(TurnEventType.END_OF_TURN_CANDIDATE, 0.6))
            elif self._silence_ms == frame_ms:
                out.append(ev(TurnEventType.SPEECH_PAUSE, 0.5))
        else:
            if self._speech_ms:  # sub-threshold blip before min_speech_ms → noise
                out.append(ev(TurnEventType.NOISE_REJECTED, p))
            self._speech_ms = 0
        return out


class EnergyTurnAdapter:
    name = "energy"

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            adapter=self.name,
            role=ProviderRole.TURN,
            capabilities=[
                Capability(name="feature:barge_in", state=CapabilityState.SUPPORTED),
                Capability(name="feature:end_of_turn", state=CapabilityState.PARTIAL, notes="silence-based only"),
                Capability(name="language:any", state=CapabilityState.SUPPORTED, notes="language-agnostic energy"),
            ],
        )

    def new_detector(self) -> EnergyTurnDetector:
        return EnergyTurnDetector(detector_name=self.name)


class MockTurnAdapter(EnergyTurnAdapter):
    """Alias so compositions can bind `turn: mock` in tests."""

    name = "mock"
