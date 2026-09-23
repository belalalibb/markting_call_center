"""P1 regressions (OPS 5.5 audit): F-02 barge-in after provider response.done, F-04 response started while
INTERRUPTED, F-06 provider-side truncation to heard audio.

A live provider generates audio faster than realtime (audit trace: 25 s of audio delivered in ~4.9 s), so the
provider's `response.done` arrives long before the user stops hearing the agent. The non-realtime mock reproduces
that exactly: a whole response is generated instantly while the client is still "playing" it.
"""

from __future__ import annotations

import asyncio
import math
import struct
from typing import Any

import pytest
from qevion.adapters.providers.mocks import MockScriptStep
from qevion.adapters.transports.memory import MemoryTransportSession
from qevion.contracts.common import Channel
from qevion.contracts.provider import S2SEvent, S2SEventType
from qevion.contracts.transport import ClientMessage
from qevion.core.dialog_machine import DialogState
from qevion.main import _seed
from qevion.runtime.store import RuntimeStore


def _tone() -> bytes:
    return struct.pack("<480h", *[int(9000 * math.sin(2 * math.pi * 180 * j / 24000)) for j in range(480)])


async def _session(steps: list[MockScriptStep]) -> tuple[Any, MemoryTransportSession, Any, asyncio.Task[Any]]:
    store = RuntimeStore()
    _seed(store)
    store.mock_fast_generation = True  # live-provider-like: generation finishes long before playout
    tr = MemoryTransportSession()
    key = next(k for k in store.activities if k.startswith("act_order_intake"))
    live = store.build_session(
        activity_key=key,
        transport=tr,
        session_id="ses_b",
        channel=Channel.BROWSER_VOICE,
        composition_id="comp_mock_s2s_v1",
        script=steps,
    )
    task = asyncio.create_task(live.session.run())
    await asyncio.sleep(0.05)
    return live.session, tr, live.session._provider, task


def _sent_types(tr: MemoryTransportSession) -> list[str]:
    return [m.type.value for m in tr.sent]


async def _speak(tr: MemoryTransportSession, frames: int = 20) -> None:
    for _ in range(frames):
        tr.client_sends(_tone())
        await asyncio.sleep(0.005)
    await asyncio.sleep(0.05)


async def _bye(tr: MemoryTransportSession, task: asyncio.Task[Any]) -> None:
    tr.client_sends(ClientMessage.model_validate({"type": "bye"}))
    await asyncio.sleep(0.05)
    task.cancel()


@pytest.mark.asyncio
async def test_barge_in_after_response_done_while_audio_still_playing() -> None:
    s, tr, prov, task = await _session([MockScriptStep(text="a long answer " * 10, audio_ms=6000)])
    tr.client_sends(ClientMessage.model_validate({"type": "text", "text": "hello"}))
    await asyncio.sleep(0.1)
    rid = next(m.response_id for m in tr.sent if m.type.value == "audio_start")
    # provider finished generating; dialog is back to LISTENING, but the client is still playing 6 s of audio
    assert s.dialog.state is DialogState.LISTENING
    tr.client_sends(ClientMessage.model_validate({"type": "playout_started", "response_id": rid}))
    await asyncio.sleep(0.05)
    assert s.audible_response() == rid
    await _speak(tr, 20)  # 400 ms of speech > barge_in_min_speech_ms (200)
    # the memory transport has no client answering stop_playout → the 300 ms force-stop path completes reconcile
    for _ in range(100):
        if s.interruptions:
            break
        await asyncio.sleep(0.02)
    det = [e for e in s.events if e.type == "interruption.detected"]
    assert det and det[0].payload["after_generation"] is True
    assert "stop_playout" in _sent_types(tr)  # the client is told to stop the audible tail
    assert len(s.interruptions) == 1
    assert 0 < s.interruptions[0].played_ms < 6000  # heard ≈ wall-clock since playout start
    # F-06: provider context cut to what was heard
    assert any(x.startswith(f"truncate:{rid}:") for x in prov.log)
    assert any(e.type == "assistant.response_truncated" for e in s.events)
    assert s.audible_response() is None
    await _bye(tr, task)


@pytest.mark.asyncio
async def test_playout_stopped_ends_audibility_so_later_speech_is_a_normal_turn() -> None:
    s, tr, prov, task = await _session(
        [MockScriptStep(text="short", audio_ms=300), MockScriptStep(text="next", audio_ms=300)]
    )
    tr.client_sends(ClientMessage.model_validate({"type": "text", "text": "hello"}))
    await asyncio.sleep(0.1)
    rid = next(m.response_id for m in tr.sent if m.type.value == "audio_start")
    tr.client_sends(ClientMessage.model_validate({"type": "playout_started", "response_id": rid}))
    tr.client_sends(ClientMessage.model_validate({"type": "playout_stopped", "response_id": rid}))
    await asyncio.sleep(0.05)
    assert s.audible_response() is None
    assert any(e.type == "assistant.playout_ended" for e in s.events)
    await _speak(tr, 20)
    assert "interruption.detected" not in [e.type for e in s.events]
    await _bye(tr, task)


@pytest.mark.asyncio
async def test_audibility_safety_net_expires_without_client_report() -> None:
    s, tr, prov, task = await _session([MockScriptStep(text="short", audio_ms=100)])
    tr.client_sends(ClientMessage.model_validate({"type": "text", "text": "hello"}))
    await asyncio.sleep(0.1)
    assert s.audible_response() is not None
    await asyncio.sleep(0.6)  # 100 ms audio + 400 ms grace
    assert s.audible_response() is None
    await _bye(tr, task)


@pytest.mark.asyncio
async def test_response_started_while_interrupted_is_cancelled_not_played() -> None:
    s, tr, prov, task = await _session([MockScriptStep(text="answer", audio_ms=2000)])
    tr.client_sends(ClientMessage.model_validate({"type": "text", "text": "hello"}))
    await asyncio.sleep(0.05)
    s.dialog.state = DialogState.INTERRUPTED  # like the live trace: a barge-in still reconciling
    before = _sent_types(tr).count("audio_start")
    await s.handle_provider_event(S2SEvent(type=S2SEventType.RESPONSE_STARTED, response_id="resp_late"))
    await s.handle_provider_event(S2SEvent(type=S2SEventType.RESPONSE_DONE, response_id="resp_late"))
    assert _sent_types(tr).count("audio_start") == before  # never forwarded to the client
    classes = [e.payload.get("class") for e in s.events if e.type == "failure.classified"]
    assert "illegal_dialog_transition" not in classes
    assert "cancel:resp_late" in prov.log
    assert s.dialog.state is DialogState.INTERRUPTED  # the refused response did not move the dialog
    await _bye(tr, task)


@pytest.mark.asyncio
async def test_operator_transcripts_reach_client_but_never_the_event_log() -> None:
    """F-13 + F-10: user/agent text goes to the connected console only; events carry digests; the provider
    transcript is `user.transcript`, not a second `user.speech_committed`."""
    s, tr, prov, task = await _session([MockScriptStep(text="أهلا بيك، تحب تطلب إيه؟", audio_ms=300)])
    tr.client_sends(ClientMessage.model_validate({"type": "text", "text": "hello"}))
    await asyncio.sleep(0.15)
    await s.handle_provider_event(S2SEvent(type=S2SEventType.INPUT_TRANSCRIPT, text="عايز بيتزا", item_id="it1"))
    transcripts = [m for m in tr.sent if m.type.value == "transcript"]
    assert transcripts and transcripts[-1].text == "عايز بيتزا" and transcripts[-1].payload["role"] == "user"
    ends = [m for m in tr.sent if m.type.value == "audio_end"]
    assert ends and ends[0].text == "أهلا بيك، تحب تطلب إيه؟" and ends[0].payload["audio_ms"] == 300
    dumped = " ".join(e.model_dump_json() for e in s.events)
    assert "عايز بيتزا" not in dumped and "تحب تطلب" not in dumped  # QV-PRIV: digests only
    assert [e.type for e in s.events].count("user.transcript") == 1
    commits = [e for e in s.events if e.type == "user.speech_committed"]
    assert all("transcript" not in e.payload for e in commits)
    await _bye(tr, task)


@pytest.mark.asyncio
async def test_operator_transcripts_can_be_disabled() -> None:
    s, tr, prov, task = await _session([MockScriptStep(text="secret reply", audio_ms=100)])
    s.deps.operator_transcripts = False
    tr.client_sends(ClientMessage.model_validate({"type": "text", "text": "hello"}))
    await asyncio.sleep(0.15)
    await s.handle_provider_event(S2SEvent(type=S2SEventType.INPUT_TRANSCRIPT, text="caller words"))
    assert not [m for m in tr.sent if m.type.value == "transcript"]
    assert all(m.text is None for m in tr.sent if m.type.value == "audio_end")
    await _bye(tr, task)
