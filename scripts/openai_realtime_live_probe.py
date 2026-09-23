"""Raw live probe of the OpenAI Realtime WS through *our* adapter (QV-ACC-022, S2S role).

Key is read from ``OPENAI_API_KEY`` (env only). Output never contains the key or transcripts beyond
short redacted lengths; a fingerprint (last 4 chars) is written for evidence.

Steps: open (adapter.open) -> wait SESSION_READY -> update_instructions -> send_text("...") -> collect
RESPONSE_STARTED / AUDIO_DELTA / TEXT_DELTA / TOOL_CALL / DONE / ERROR with timings -> close.

Usage: OPENAI_API_KEY=... .venv/bin/python scripts/openai_realtime_live_probe.py [out.json] [--model gpt-realtime]
Exit 0 iff SESSION_READY and a RESPONSE_DONE with >0 audio bytes were observed; 2 if no key.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import UTC, datetime
from typing import Any

from qevion.adapters.providers.openai_realtime import OpenAIRealtimeAdapter
from qevion.contracts.provider import S2SEventType, S2SSessionConfig


def _fingerprint(key: str) -> str:
    return f"…{key[-4:]}" if len(key) >= 4 else "…"


async def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    model = sys.argv[sys.argv.index("--model") + 1] if "--model" in sys.argv else "gpt-realtime"
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key:
        print("OPENAI_API_KEY not set", file=sys.stderr)
        return 2
    adapter = OpenAIRealtimeAdapter()
    cfg = S2SSessionConfig(
        provider="openai_realtime", model=model, language_hint="ar-EG", voice="alloy", server_vad=False
    )
    t0 = time.monotonic()
    timeline: list[dict[str, Any]] = []
    audio_bytes = 0
    text_chars = 0
    errors: list[dict[str, Any]] = []
    ready = False
    done = False
    error_txt: str | None = None

    def mark(kind: str, **extra: Any) -> None:
        timeline.append({"t_ms": int((time.monotonic() - t0) * 1000), "event": kind, **extra})

    try:
        sess = await adapter.open(cfg, key)
        mark("open")
        events = sess.events()
        # wait for session.created
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            ev = await asyncio.wait_for(events.__anext__(), timeout=15)
            if ev.type is S2SEventType.SESSION_READY:
                ready = True
                mark("session_ready", raw=ev.raw_type)
                break
            if ev.type is S2SEventType.ERROR:
                errors.append(
                    {"code": ev.error.code if ev.error else None, "msg": (ev.error.message if ev.error else "")[:200]}
                )
                mark("error", code=errors[-1]["code"])
                break
        if ready:
            await sess.update_instructions(
                "You are a concise Egyptian-Arabic voice assistant for a customer-satisfaction survey. "
                "Reply in one short sentence."
            )
            mark("session_update_sent")
            await sess.send_text("أهلا، عايز أقيم خدمتكم")
            mark("text_sent")
            deadline = time.monotonic() + 40
            first_audio_ms: int | None = None
            while time.monotonic() < deadline:
                try:
                    ev = await asyncio.wait_for(events.__anext__(), timeout=max(0.1, deadline - time.monotonic()))
                except (TimeoutError, StopAsyncIteration):
                    break
                if ev.type is S2SEventType.RESPONSE_STARTED:
                    mark("response_started")
                elif ev.type is S2SEventType.RESPONSE_AUDIO_DELTA and ev.audio:
                    if first_audio_ms is None:
                        first_audio_ms = int((time.monotonic() - t0) * 1000)
                        mark("first_audio", bytes=ev.audio.byte_length)
                    audio_bytes += ev.audio.byte_length
                elif ev.type is S2SEventType.RESPONSE_TEXT_DELTA:
                    text_chars += len(ev.text or "")
                elif ev.type is S2SEventType.RESPONSE_TOOL_CALL:
                    mark("tool_call", tool=ev.tool_call.tool_id if ev.tool_call else None)
                elif ev.type is S2SEventType.ERROR:
                    errors.append(
                        {
                            "code": ev.error.code if ev.error else None,
                            "msg": (ev.error.message if ev.error else "")[:200],
                        }
                    )
                    mark("error", code=errors[-1]["code"])
                elif ev.type in (S2SEventType.RESPONSE_DONE, S2SEventType.RESPONSE_CANCELLED):
                    done = ev.type is S2SEventType.RESPONSE_DONE
                    mark("response_done", audio_bytes=audio_bytes, text_chars=text_chars)
                    break
        await sess.close()
        mark("closed")
    except Exception as exc:  # noqa: BLE001 - probe reports, never raises
        error_txt = f"{type(exc).__name__}: {str(exc)[:200]}"
        mark("exception", error=error_txt)

    # session.update echo (session.updated) is folded into SESSION_READY only once; record raw errors verbatim (no key)
    passed = ready and done and audio_bytes > 0 and not errors
    report = {
        "kind": "openai-realtime-live-probe",
        "produced_at": datetime.now(UTC).isoformat(),
        "model_requested": model,
        "key_fingerprint": _fingerprint(key),
        "session_ready": ready,
        "response_done": done,
        "audio_bytes": audio_bytes,
        "audio_ms_pcm16_24k": int(audio_bytes / 2 / 24000 * 1000),
        "text_chars": text_chars,
        "errors": errors,
        "exception": error_txt,
        "timeline": timeline,
        "passed": passed,
    }
    out = json.dumps(report, ensure_ascii=False, indent=1)
    if args:
        with open(args[0], "w", encoding="utf-8") as fh:
            fh.write(out + "\n")
    print(out)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
