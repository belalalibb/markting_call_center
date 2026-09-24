"""Real-browser browser_voice smoke of the Operator Console (Chromium via Playwright, fake microphone).

Loads `#/console`, selects activity + composition, turns the mic on (fake device), connects, watches the chat log
and the WebSocket for `--seconds`, sends a second user turn once the agent has spoken, then hangs up. Records the
header pill, the live status pill, session-ready facts, speaking→listening cycles, heartbeat pongs and the close
code (the field failure was `1011 keepalive ping timeout` mid-speech).

Usage: .venv/bin/python scripts/browser_voice_smoke.py [out.json] --base https://… [--composition comp_s2s_openai_v1]
       [--activity act_order_intake@1.0.0] [--seconds 70] [--inject-key-env OPENAI_API_KEY]
Exit 0 iff: connected, session ready, header pill shows the *actual* composition, ≥1 speaking→listening cycle,
second turn accepted, no close during the soak, final close 1000 after Hang up.
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import sys
import time
from datetime import UTC, datetime
from typing import Any
from urllib import request

from playwright.async_api import async_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from session_health import fetch_events, verdict  # noqa: E402

WS_SHIM = """
(() => {
  const Orig = window.WebSocket;
  window.__qevion_ws = [];
  const Wrapped = function(url, protocols) {
    const ws = protocols === undefined ? new Orig(url) : new Orig(url, protocols);
    const rec = { url: String(url), opened_at: Date.now(), close: null, text_types: {}, binary: 0, pings: 0, pongs_sent: 0 };
    window.__qevion_ws.push(rec);
    ws.addEventListener('close', (e) => { rec.close = { code: e.code, reason: e.reason, at: Date.now() }; });
    ws.addEventListener('message', (e) => {
      if (typeof e.data !== 'string') { rec.binary += 1; return; }
      try { const t = JSON.parse(e.data).type; rec.text_types[t] = (rec.text_types[t] || 0) + 1; if (t === 'ping') rec.pings += 1; } catch (_) {}
    });
    const send = ws.send.bind(ws);
    ws.__qevion_raw_send = send;
    ws.send = (d) => {
      if (typeof d === 'string' && d.includes('"pong"')) rec.pongs_sent += 1;
      if (typeof d !== 'string' && window.__qevion_mute_capture) return;  // scripted utterance owns the mic
      return send(d);
    };
    window.__qevion_last_ws = ws;
    return ws;
  };
  Wrapped.prototype = Orig.prototype;
  Object.assign(Wrapped, { CONNECTING: 0, OPEN: 1, CLOSING: 2, CLOSED: 3 });
  window.WebSocket = Wrapped;
})();
"""


# In-page "utterance": 20 ms PCM16@24k frames of a 180 Hz tone with a slow amplitude envelope for `ms`, sent on the
# live WebSocket exactly like the capture worklet does. Chromium's fake mic emits a beep pattern whose bursts are
# shorter than the turn plane's min_speech_ms (correctly classified as noise), so the smoke speaks deterministically.
# While the scripted utterance plays, the real capture path is muted (binary sends from the worklet are dropped) so
# the turn plane sees one contiguous utterance instead of tone frames interleaved with fake-mic silence/beeps.
# With real Silero (CP-0015) a pure tone is correctly rejected as non-speech, so when synthetic speech clips are
# available (voice_trace_live.py caches OpenAI TTS PCM in $TMP/qevion_tts) the smoke streams real speech instead.
SPEECH_JS = """
(async (b64) => {
  const ws = window.__qevion_last_ws; if (!ws || ws.readyState !== 1) return false;
  const raw = Uint8Array.from(atob(b64), c => c.charCodeAt(0)); const bytes = 960;
  window.__qevion_mute_capture = true;
  try {
    for (let i = 0; i + bytes <= raw.length; i += bytes) {
      ws.__qevion_raw_send(raw.slice(i, i + bytes).buffer);
      await new Promise(r => setTimeout(r, 20));
    }
    for (let k = 0; k < 50; k++) { ws.__qevion_raw_send(new Int16Array(480).buffer); await new Promise(r => setTimeout(r, 20)); }
  } finally { window.__qevion_mute_capture = false; }
  return true;
})
"""


def _speech_clip(name: str) -> str | None:
    import base64
    import tempfile

    d = pathlib.Path(os.environ.get("QEVION_TTS_CACHE", tempfile.gettempdir())) / "qevion_tts" / f"{name}.pcm"
    return base64.b64encode(d.read_bytes()).decode() if d.is_file() else None


SPEAK_JS = """
(async (ms) => {
  const ws = window.__qevion_last_ws; if (!ws || ws.readyState !== 1) return false;
  const rate = 24000, frame = rate / 50; let phase = 0;
  window.__qevion_mute_capture = true;
  try {
    for (let sent = 0; sent < ms; sent += 20) {
      const buf = new Int16Array(frame);
      for (let i = 0; i < frame; i++) { const env = 0.6 + 0.4 * Math.sin((sent / 1000) * 6.0); buf[i] = Math.round(9000 * env * Math.sin(2 * Math.PI * 180 * (phase + i) / rate)); }
      phase += frame; ws.__qevion_raw_send(buf.buffer);
      await new Promise(r => setTimeout(r, 20));
    }
    // trailing silence so end-of-turn (min_silence_ms) is reached with a clean gap
    for (let s = 0; s < 700; s += 20) { ws.__qevion_raw_send(new Int16Array(frame).buffer); await new Promise(r => setTimeout(r, 20)); }
  } finally { window.__qevion_mute_capture = false; }
  return true;
})
"""


def _arg(name: str, default: str) -> str:
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def _inject(base: str, key_env: str) -> str | None:
    val = os.environ.get(key_env, "")
    if not val:
        return None
    provider = key_env.lower().removesuffix("_api_key")
    body = json.dumps({"provider": provider, "value": val, "ttl_seconds": 900}).encode()
    req = request.Request(
        base + "/api/admin/test-key", data=body, headers={"content-type": "application/json"}, method="POST"
    )
    with request.urlopen(req, timeout=10):  # noqa: S310 - operator-run against own server
        pass
    return provider


async def main() -> int:
    out_path = next((a for a in sys.argv[1:] if a.endswith(".json")), None)
    base = _arg("--base", "http://localhost:8000").rstrip("/")
    composition = _arg("--composition", "comp_s2s_openai_v1")
    activity = _arg("--activity", "act_order_intake@1.0.0")
    seconds = float(_arg("--seconds", "70"))
    key_env = _arg("--inject-key-env", "")
    injected = _inject(base, key_env) if key_env else None

    t0 = time.monotonic()
    now = lambda: int((time.monotonic() - t0) * 1000)  # noqa: E731
    console_errors: list[str] = []
    chat_lines: list[tuple[int, str]] = []
    seen_chat: set[str] = set()
    header_samples: list[tuple[int, str]] = []
    ws_rec: dict[str, Any] = {}
    second_turn_sent = False
    soak_close: dict[str, Any] | None = None

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            args=[
                "--use-fake-device-for-media-stream",
                "--use-fake-ui-for-media-stream",
                "--autoplay-policy=no-user-gesture-required",
            ]
        )
        context = await browser.new_context(permissions=["microphone"])
        page = await context.new_page()
        page.on("console", lambda m: console_errors.append(m.text[:200]) if m.type == "error" else None)
        await page.add_init_script(WS_SHIM)
        await page.goto(f"{base}/#/console", wait_until="networkidle")
        await page.wait_for_selector("select", timeout=15000)
        selects = page.locator("select")
        await selects.nth(0).select_option(activity)
        await selects.nth(1).select_option(composition)
        await page.get_by_role("button", name="🎙 Mic off").click()
        await page.wait_for_timeout(1500)
        mic_on = await page.get_by_role("button", name="🎙 Mic on").count() > 0
        await page.get_by_role("button", name="Connect").click()

        async def poll() -> None:
            nonlocal ws_rec
            for line in await page.locator(".chat .msg").all_inner_texts():
                if line not in seen_chat:
                    seen_chat.add(line)
                    chat_lines.append((now(), line[:180]))
            hdr = (await page.locator("#health").inner_text()).strip()
            if not header_samples or header_samples[-1][1] != hdr:
                header_samples.append((now(), hdr))
            recs = await page.evaluate("window.__qevion_ws")
            if recs:
                ws_rec = recs[-1]

        deadline = time.monotonic() + seconds
        spoke_first = False
        spoken_turns = 0
        audio_ends_at_first = 0
        first_answer_ms = 0
        while time.monotonic() < deadline:
            await page.wait_for_timeout(1000)
            await poll()
            if ws_rec.get("close"):
                soak_close = ws_rec["close"]
                break
            tt_now: dict[str, int] = dict(ws_rec.get("text_types") or {})
            ready_seen = tt_now.get("ready", 0) >= 1
            audio_ends = int(tt_now.get("audio_end", 0))
            # first spoken user turn once the session is ready and the agent finished its opening (or after 8 s)
            if ready_seen and not spoke_first and (audio_ends >= 1 or now() > 8000):
                clip = _speech_clip("u1_order")
                await page.evaluate(f"({SPEECH_JS})", clip) if clip else await page.evaluate(f"({SPEAK_JS})(1400)")
                spoke_first = True
                spoken_turns += 1
                audio_ends_at_first = audio_ends
            if spoke_first and first_answer_ms == 0 and audio_ends > audio_ends_at_first:
                first_answer_ms = now()
            # second user turn (spoken) once the agent has answered the first (speaking → listening) and
            # at least 3 s have passed since that answer ended
            first_cycle_done = spoke_first and audio_ends >= 1
            if first_cycle_done and not second_turn_sent and first_answer_ms and now() - first_answer_ms >= 3000:
                clip = _speech_clip("u2_address")
                await page.evaluate(f"({SPEECH_JS})", clip) if clip else await page.evaluate(f"({SPEAK_JS})(1200)")
                spoken_turns += 1
                second_turn_sent = True
        if soak_close is None:
            await page.get_by_role(
                "button", name="Hang up"
            ).first.click()  # live-session card (outbound card has one too)
            for _ in range(12):
                await page.wait_for_timeout(500)
                await poll()
                if ws_rec.get("close"):
                    break
        await poll()
        status_pills = await page.locator(".pill").all_inner_texts()
        sessions: list[dict[str, Any]] = []
        try:
            with request.urlopen(base + "/api/sessions", timeout=10) as r:  # noqa: S310
                sessions = json.loads(r.read().decode())
        except Exception:  # noqa: BLE001
            pass
        await browser.close()

    tt: dict[str, int] = dict(ws_rec.get("text_types") or {})
    speaking_cycles = min(int(tt.get("audio_start", 0)), int(tt.get("audio_end", 0)))
    connected = any("connected →" in ln for _, ln in chat_lines)
    ready_line = next((ln for _, ln in chat_lines if ln.startswith("session ready")), None)
    header_live = any(composition in hdr and hdr.startswith("live") for _, hdr in header_samples)
    second_turn_ok = second_turn_sent and speaking_cycles >= 2  # agent answered both spoken turns
    final_close: dict[str, Any] = dict(ws_rec.get("close") or {})
    final_ok = final_close.get("code") == 1000
    pings = int(ws_rec.get("pings") or 0)
    pongs = int(ws_rec.get("pongs_sent") or 0)
    checks: dict[str, bool] = {
        "mic_on": mic_on,
        "connected": connected,
        "session_ready": ready_line is not None and composition in ready_line,
        "header_shows_actual_composition": header_live,
        "speaking_then_listening": speaking_cycles >= 1,
        "second_user_turn": second_turn_ok,
        "heartbeat_answered": pongs >= 1 and pongs == pings,
        "no_close_during_soak": soak_close is None,
        "final_close_1000": final_ok,
        "no_1011": (soak_close or {}).get("code") != 1011 and final_close.get("code") != 1011,
    }
    # F-11: the Core's own verdict on the session (provider errors, illegal transitions, BLOCKED, outcome)
    health: dict[str, Any] = {"passed": False, "checks": {"session_found": False}}
    sid = next((s.get("session_id") for s in reversed(sessions) if s.get("composition_id") == composition), None)
    if sid:
        health = verdict(fetch_events(base, str(sid)))
    for k, v in health["checks"].items():
        checks[f"core:{k}"] = bool(v)
    passed = all(checks.values())
    report = {
        "kind": "browser-voice-smoke",
        "produced_at": datetime.now(UTC).isoformat(),
        "base": base,
        "activity": activity,
        "composition": composition,
        "key_injected_for": injected,
        "target_seconds": seconds,
        "survived_ms": now(),
        "header_samples": header_samples[:10],
        "status_pills": status_pills[:8],
        "ready_line": ready_line,
        "chat": chat_lines[:60],
        "ws": {k: ws_rec.get(k) for k in ("text_types", "binary", "pings", "pongs_sent", "close")},
        "speaking_cycles": speaking_cycles,
        "spoken_user_turns": spoken_turns,
        "close_during_soak": soak_close,
        "console_errors": console_errors[:10],
        "sessions_after": [
            {
                k: s.get(k)
                for k in (
                    "session_id",
                    "composition_id",
                    "channel",
                    "credential_source",
                    "running",
                    "error",
                    "close_code",
                    "close_reason",
                    "heartbeat",
                )
            }
            for s in sessions
        ][-3:],
        "core_health": health,
        "checks": checks,
        "passed": passed,
    }
    text = json.dumps(report, ensure_ascii=False, indent=1)
    if out_path:
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    print(text)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
