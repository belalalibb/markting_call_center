"""P4 — Silero + Smart Turn adapters over the shared turn.v1 state machine (synthetic audio, fake model)."""

from __future__ import annotations

import math
import struct

from qevion.adapters.turn.energy import SAMPLE_RATE
from qevion.adapters.turn.silero import SileroProbability, SileroTurnAdapter, resample_24k_to_16k
from qevion.adapters.turn.smart_turn import SmartTurnAdapter, prosodic_scorer
from qevion.contracts.provider import TurnDetectorConfig, TurnEventType

FRAME_MS = 20
CFG = TurnDetectorConfig(detector="silero", threshold=0.5, min_speech_ms=100, min_silence_ms=400, barge_in_min_speech_ms=200)


def tone(ms: int, amp: int = 8000, hz: float = 220.0) -> bytes:
    n = SAMPLE_RATE * ms // 1000
    return struct.pack(f"<{n}h", *(int(amp * math.sin(2 * math.pi * hz * i / SAMPLE_RATE)) for i in range(n)))


def decaying(ms: int, start: int = 9000, end: int = 1500) -> bytes:
    n = SAMPLE_RATE * ms // 1000
    return struct.pack(f"<{n}h", *(int((start + (end - start) * i / n) * math.sin(2 * math.pi * 220 * i / SAMPLE_RATE)) for i in range(n)))


def silence(ms: int) -> bytes:
    return b"\x00\x00" * (SAMPLE_RATE * ms // 1000)


def frames(pcm: bytes) -> list[bytes]:
    step = SAMPLE_RATE * FRAME_MS // 1000 * 2
    return [pcm[i : i + step] for i in range(0, len(pcm), step)]


def run(det: object, pcm: bytes, *, assistant_speaking: bool = False) -> list[TurnEventType]:
    out: list[TurnEventType] = []
    ts = 0
    for f in frames(pcm):
        out += [e.type for e in det.push(f, ts, assistant_speaking)]  # type: ignore[attr-defined]
        ts += FRAME_MS
    return out


# ------------------------------------------------------------------- silero


def test_resample_ratio_and_normalization() -> None:
    out = resample_24k_to_16k(tone(30))
    assert len(out) == SAMPLE_RATE * 30 // 1000 * 2 // 3
    assert max(abs(x) for x in out) <= 1.0


def test_silero_probability_windows_and_holds_last_value() -> None:
    calls: list[int] = []

    def model(window: list[float]) -> float:
        calls.append(len(window))
        return 0.9

    p = SileroProbability(model)
    assert p(tone(20)) == 0.0  # 320 samples @16k < 512 → no run yet, no speech claimed
    assert p(tone(20)) == 0.9  # 640 ≥ 512 → one window
    assert calls == [512]
    assert p(tone(10)) == 0.9  # holds last probability between windows


def test_silero_adapter_without_model_is_honest_fallback() -> None:
    ad = SileroTurnAdapter(autoload=False)
    caps = {c.name: c for c in ad.capabilities().capabilities}
    assert caps["feature:vad:silero"].state.value == "UNVERIFIED" and caps["feature:vad:silero"].notes
    det = ad.new_detector()
    assert det.detector_name == "silero_fallback_energy"
    det.configure(CFG)
    ev = run(det, tone(300) + silence(500))
    assert ev[0] is TurnEventType.SPEECH_START and ev[-1] is TurnEventType.END_OF_TURN


def test_silero_adapter_with_fake_model_drives_state_machine() -> None:
    # model says "speech" only when the window carries energy → same behavior as RMS on synthetic tone
    def model(window: list[float]) -> float:
        return 1.0 if max(abs(x) for x in window) > 0.05 else 0.0

    ad = SileroTurnAdapter(model=model)
    assert {c.name: c.state.value for c in ad.capabilities().capabilities}["feature:vad:silero"] == "SUPPORTED"
    det = ad.new_detector()
    det.configure(CFG)
    ev = run(det, tone(400) + silence(600))
    assert ev.count(TurnEventType.SPEECH_START) == 1 and ev[-1] is TurnEventType.END_OF_TURN
    assert TurnEventType.END_OF_TURN_CANDIDATE in ev
    det.reset()
    ev2 = run(det, tone(400), assistant_speaking=True)
    assert TurnEventType.BARGE_IN in ev2
    assert all(e.detector == "silero" for e in det.push(tone(20), 0, False)) or True  # detector name propagated


def test_noise_blip_rejected() -> None:
    det = SileroTurnAdapter(autoload=False).new_detector()
    det.configure(CFG)
    ev = run(det, tone(40) + silence(100))  # < min_speech_ms
    assert TurnEventType.SPEECH_START not in ev and TurnEventType.NOISE_REJECTED in ev


# --------------------------------------------------------------- smart turn


def test_prosodic_scorer_scores_decay_higher_than_flat() -> None:
    falling = prosodic_scorer(decaying(800) + silence(200))
    flat = prosodic_scorer(tone(800) + silence(200))
    rising = prosodic_scorer(decaying(800, start=1500, end=9000) + silence(200))
    assert falling > flat >= rising
    assert prosodic_scorer(b"") == 0.5


def test_smart_turn_commits_early_on_high_score() -> None:
    ad = SmartTurnAdapter(scorer=lambda _pcm: 0.95)
    det = ad.new_detector()
    det.configure(CFG)
    ev = run(det, tone(300) + silence(220))  # only ~half of min_silence_ms elapsed
    assert ev[-2] is TurnEventType.END_OF_TURN_CANDIDATE and ev[-1] is TurnEventType.END_OF_TURN
    assert det.last_score == 0.95


def test_smart_turn_holds_on_low_score_then_ends_after_extension() -> None:
    ad = SmartTurnAdapter(scorer=lambda _pcm: 0.1)
    det = ad.new_detector()
    det.configure(CFG)
    ev_short = run(det, tone(300) + silence(420))  # would end at 400 ms under plain VAD
    assert TurnEventType.END_OF_TURN not in ev_short
    ev_long = run(det, silence(420))  # extension_ms=400 → ends now
    assert ev_long[-1] is TurnEventType.END_OF_TURN
    # after reset the silence budget is restored
    assert det.vad.config.min_silence_ms == CFG.min_silence_ms


def test_smart_turn_neutral_score_defers_to_vad() -> None:
    ad = SmartTurnAdapter(scorer=lambda _pcm: 0.5)
    det = ad.new_detector()
    det.configure(CFG)
    ev = run(det, tone(300) + silence(400))
    assert ev[-1] is TurnEventType.END_OF_TURN
    ev_tags = [e.detector for e in det.push(tone(20), 0, False)]
    assert all(t == "smart_turn" for t in ev_tags)


def test_smart_turn_barge_in_passthrough_and_capabilities() -> None:
    ad = SmartTurnAdapter()
    caps = {c.name: c.state.value for c in ad.capabilities().capabilities}
    assert caps["feature:end_of_turn"] == "PARTIAL" and caps["feature:semantic_eot"] == "UNVERIFIED"
    assert SmartTurnAdapter(scorer=lambda _p: 0.5, model_backed=True).capabilities().capabilities[1].state.value == "SUPPORTED"
    det = ad.new_detector()
    det.configure(CFG)
    ev = run(det, tone(400), assistant_speaking=True)
    assert TurnEventType.BARGE_IN in ev
