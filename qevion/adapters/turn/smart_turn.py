"""Smart Turn adapter (P4): semantic end-of-turn on top of a VAD probability source.

VAD alone ends a turn after `min_silence_ms` of silence. Smart Turn shortens or extends that decision:
at `END_OF_TURN_CANDIDATE` it scores the recent audio with an `EndOfTurnScorer` (model or heuristic):
  * score ≥ `commit_threshold`   → emit END_OF_TURN immediately (faster response, §30 QV-TURN-003)
  * score ≤ `hold_threshold`     → extend silence budget once by `extension_ms` (user is mid-thought)
  * otherwise                    → defer to the VAD silence rule
The default scorer is a deterministic prosodic heuristic (energy decay + trailing pause pattern) so the
adapter is testable on 2 vCPU without a model (A9); an ONNX/torch scorer can be injected later. Capability
`feature:end_of_turn` is declared PARTIAL with the heuristic and SUPPORTED only when a model scorer is set.
"""

from __future__ import annotations

import struct
from collections.abc import Callable
from dataclasses import dataclass, field

from qevion.adapters.turn.energy import SAMPLE_RATE, EnergyTurnDetector, ProbFn, rms_probability
from qevion.contracts.composition import AdapterCapabilities, Capability, CapabilityState
from qevion.contracts.provider import ProviderRole, TurnDetectorConfig, TurnEvent, TurnEventType

EndOfTurnScorer = Callable[[bytes], float]  # recent PCM16 (≤ 8 s) → P(turn complete)


def prosodic_scorer(pcm16: bytes, *, tail_ms: int = 600) -> float:
    """Deterministic heuristic: a turn is likely complete when the last `tail_ms` before silence shows
    falling energy (declarative cadence) and the utterance was not cut mid-burst. Returns [0,1]."""
    n = len(pcm16) // 2
    if n < SAMPLE_RATE // 10:  # < 100 ms of context
        return 0.5
    samples = struct.unpack(f"<{n}h", pcm16[: n * 2])
    win = SAMPLE_RATE // 50  # 20 ms
    rms = []
    for i in range(0, n - win, win):
        seg = samples[i : i + win]
        rms.append((sum(s * s for s in seg) / win) ** 0.5)
    if len(rms) < 6:
        return 0.5
    voiced = [r for r in rms if r > 250]
    if not voiced:
        return 0.5
    tail_n = max(3, tail_ms // 20)
    tail = [r for r in rms[-tail_n * 2 :] if r > 250][-tail_n:]
    if len(tail) < 3:
        return 0.5
    first, last = (
        sum(tail[: len(tail) // 2]) / (len(tail) // 2),
        sum(tail[len(tail) // 2 :]) / (len(tail) - len(tail) // 2),
    )
    decay = (first - last) / max(first, 1.0)  # >0 falling
    score = 0.5 + 0.5 * max(-1.0, min(1.0, decay * 2))
    return float(max(0.0, min(1.0, score)))


@dataclass
class SmartTurnDetector:
    """Wraps the shared VAD state machine; intercepts END_OF_TURN_CANDIDATE to apply the semantic scorer."""

    vad: EnergyTurnDetector
    scorer: EndOfTurnScorer
    detector_name: str = "smart_turn"
    commit_threshold: float = 0.75
    hold_threshold: float = 0.3
    extension_ms: int = 400
    context_ms: int = 8000
    _ctx: bytearray = field(default_factory=bytearray)
    _extended: bool = False
    _base_silence: int | None = None
    last_score: float | None = None

    def configure(self, config: TurnDetectorConfig) -> None:
        self.vad.configure(config)
        self._base_silence = config.min_silence_ms
        self.reset()

    def reset(self) -> None:
        self.vad.reset()
        self._ctx.clear()
        self._extended = False
        if self._base_silence is not None:
            self.vad.config = self.vad.config.model_copy(update={"min_silence_ms": self._base_silence})

    def push(self, pcm16: bytes, ts_ms: int, assistant_speaking: bool) -> list[TurnEvent]:
        self._ctx.extend(pcm16)
        max_bytes = self.context_ms * SAMPLE_RATE // 1000 * 2
        if len(self._ctx) > max_bytes:
            del self._ctx[: len(self._ctx) - max_bytes]
        out: list[TurnEvent] = []
        for ev in self.vad.push(pcm16, ts_ms, assistant_speaking):
            ev = ev.model_copy(update={"detector": self.detector_name})
            if ev.type is TurnEventType.END_OF_TURN_CANDIDATE:
                score = float(self.scorer(bytes(self._ctx)))
                self.last_score = score
                out.append(ev.model_copy(update={"confidence": round(score, 3)}))
                if score >= self.commit_threshold:
                    out.append(
                        TurnEvent(
                            type=TurnEventType.END_OF_TURN,
                            ts_ms=ts_ms,
                            confidence=round(score, 3),
                            detector=self.detector_name,
                            speech_ms=ev.speech_ms,
                            silence_ms=ev.silence_ms,
                        )
                    )
                    self.reset()
                    return out
                if score <= self.hold_threshold and not self._extended:
                    self._extended = True
                    cfg = self.vad.config
                    self.vad.config = cfg.model_copy(update={"min_silence_ms": cfg.min_silence_ms + self.extension_ms})
                continue
            if ev.type is TurnEventType.END_OF_TURN:
                self.reset()
            out.append(ev)
        return out


class SmartTurnAdapter:
    name = "smart_turn"

    def __init__(
        self, *, prob_fn: ProbFn = rms_probability, scorer: EndOfTurnScorer | None = None, model_backed: bool = False
    ) -> None:
        self._prob_fn = prob_fn
        self._scorer = scorer or prosodic_scorer
        self._model_backed = model_backed and scorer is not None

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            adapter=self.name,
            role=ProviderRole.TURN,
            capabilities=[
                Capability(name="feature:barge_in", state=CapabilityState.SUPPORTED),
                Capability(
                    name="feature:end_of_turn",
                    state=CapabilityState.SUPPORTED if self._model_backed else CapabilityState.PARTIAL,
                    notes=None if self._model_backed else "prosodic heuristic scorer (no model on 2 vCPU)",
                ),
                Capability(
                    name="feature:semantic_eot",
                    state=CapabilityState.SUPPORTED if self._model_backed else CapabilityState.UNVERIFIED,
                ),
                Capability(name="language:any", state=CapabilityState.SUPPORTED),
            ],
        )

    def new_detector(self) -> SmartTurnDetector:
        return SmartTurnDetector(
            vad=EnergyTurnDetector(prob_fn=self._prob_fn, detector_name="vad"), scorer=self._scorer
        )


__all__ = ["EndOfTurnScorer", "SmartTurnAdapter", "SmartTurnDetector", "prosodic_scorer"]
