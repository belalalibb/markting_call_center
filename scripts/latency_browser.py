"""Browser-leg latency probe (Playwright; Chromium and Firefox). Measures, per agent response, inside the real
Operator Console code path (VoiceClient → AudioWorklet):

  T9  first_frame_ws_recv       console WS onmessage got the first binary frame of the response
  T10 first_frame_to_worklet    VoiceClient posted it to the playout worklet
  T11r first_sample_rendered    worklet rendered the first non-zero sample (audio clock → wall clock)
  T11a first_sample_audible_est T11r + AudioContext.outputLatency + baseLatency (device estimate)

and server marks T7 (provider first audio) / T8 (QEVION sent first audio) from /api/sessions/{sid}/latency-trace.
All clocks are the same host (browser and server in the same sandbox) → epoch ms comparable.

Speech is injected on the console's own WebSocket (same path the capture worklet uses) from cached synthetic clips.

usage: .venv/bin/python scripts/latency_browser.py OUT.json [--browser chromium|firefox] [--turns 6]
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import pathlib
import sys
import tempfile
import urllib.request
from typing import Any

from playwright.async_api import async_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from latency_corpus import stats  # noqa: E402

BASE = "http://localhost:8000"
BROWSER = sys.argv[sys.argv.index("--browser") + 1] if "--browser" in sys.argv else "chromium"
TURNS = int(sys.argv[sys.argv.index("--turns") + 1]) if "--turns" in sys.argv else 6
PLAN = ["u_short", "u_follow", "u3_yes", "u_ambig", "u_short", "u3_yes", "u_follow", "u_ambig"]

WRAP = """
(() => {
  const Orig = window.WebSocket;
  function Wrapped(url, protos) {
    const ws = protos ? new Orig(url, protos) : new Orig(url);
    const send = ws.send.bind(ws);
    ws.__raw = send;
    ws.send = (d) => { if (typeof d !== 'string' && window.__mute) return; return send(d); };
    window.__ws = ws;
    return ws;
  }
  Wrapped.prototype = Orig.prototype; Object.assign(Wrapped, Orig);
  window.WebSocket = Wrapped;
})();
"""
SPEAK = """
async (b64) => {
  const ws = window.__ws; const raw = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
  window.__mute = true;
  try {
    for (let i = 0; i + 960 <= raw.length; i += 960) { ws.__raw(raw.slice(i, i + 960).buffer); await new Promise(r => setTimeout(r, 20)); }
    for (let k = 0; k < 40; k++) { ws.__raw(new Int16Array(480).buffer); await new Promise(r => setTimeout(r, 20)); }
  } finally { window.__mute = false; }
  return Date.now();
}
"""


def clip(name: str) -> str:
    d = pathlib.Path(os.environ.get("QEVION_TTS_CACHE", tempfile.gettempdir())) / "qevion_tts" / f"{name}.pcm"
    return base64.b64encode(d.read_bytes()).decode()


def get(path: str) -> Any:
    return json.loads(urllib.request.urlopen(BASE + path, timeout=10).read())  # noqa: S310


async def main() -> int:
    out = sys.argv[1]
    async with async_playwright() as p:
        if BROWSER == "firefox":
            b = await p.firefox.launch(
                firefox_user_prefs={"media.navigator.streams.fake": True, "media.navigator.permission.disabled": True}
            )
            ctx = await b.new_context()
        else:
            b = await p.chromium.launch(
                args=[
                    "--use-fake-device-for-media-stream",
                    "--use-fake-ui-for-media-stream",
                    "--autoplay-policy=no-user-gesture-required",
                ]
            )
            ctx = await b.new_context(permissions=["microphone"])
        pg = await ctx.new_page()
        await pg.add_init_script(WRAP)
        await pg.goto(BASE + "/#/console")
        await pg.wait_for_selector("text=Live session", timeout=15000)
        await pg.select_option("select >> nth=1", "comp_s2s_openai_v1")
        await pg.click("button:has-text('Mic')")
        await pg.wait_for_timeout(800)
        await pg.click("button:has-text('Connect')")
        await pg.wait_for_function("window.__ws && window.__ws.readyState === 1", timeout=15000)
        await pg.wait_for_selector("text=session ready", timeout=20000)
        ua = await pg.evaluate("navigator.userAgent")
        audio_info = await pg.evaluate(
            "(() => { const c = new AudioContext(); const r = {sampleRate: c.sampleRate, baseLatency: c.baseLatency, outputLatency: c.outputLatency ?? null}; c.close(); return r; })()"
        )
        await pg.wait_for_timeout(1500)
        sends: list[float] = []
        for name in PLAN[:TURNS]:
            sends.append(await pg.evaluate(SPEAK, clip(name)))
            await pg.wait_for_timeout(9000)  # agent answers + plays
        marks = await pg.evaluate("window.__qevionLatency || []")
        sid = await pg.evaluate(
            "(() => { const l = [...document.querySelectorAll('.chat .msg')].map(e => e.textContent); return l.join('\\n'); })()"
        )
        await pg.click("button:has-text('Hang up')")
        await pg.wait_for_timeout(1500)
        await b.close()
    sessions = get("/api/sessions")
    live = [s for s in sessions if s.get("composition_id") == "comp_s2s_openai_v1"]
    srv = get(f"/api/sessions/{live[-1]['session_id']}/latency-trace")["marks"] if live else []
    by: dict[str, dict[str, float]] = {}
    for t, kind, ref in marks:
        by.setdefault(ref, {}).setdefault(kind, t)
    for t, kind, ref in srv:
        if kind in ("recv:first_audio_delta", "core:first_audio_to_client"):
            by.setdefault(ref, {}).setdefault(kind, t)
    rows = []
    for rid, m in by.items():
        if "first_frame_ws_recv" not in m:
            continue

        def d(a: str, z: str, m: dict[str, float] = m) -> float | None:
            return round(m[z] - m[a], 1) if a in m and z in m else None

        rows.append(
            {
                "response_id": rid,
                "T7_T8_server_forward": d("recv:first_audio_delta", "core:first_audio_to_client"),
                "T8_T9_ws_to_browser": d("core:first_audio_to_client", "first_frame_ws_recv"),
                "T9_T10_to_worklet": d("first_frame_ws_recv", "first_frame_to_worklet"),
                "T10_T11_render": d("first_frame_to_worklet", "first_sample_rendered"),
                "T11_device_output_est": d("first_sample_rendered", "first_sample_audible_est"),
                "T9_T11_browser_total_est": d("first_frame_ws_recv", "first_sample_audible_est"),
            }
        )
    keys = [k for k in (rows[0] if rows else {}) if k.startswith("T")]
    rep = {
        "browser": BROWSER,
        "user_agent": ua,
        "audio_context": audio_info,
        "responses": len(rows),
        "summary": {k: stats([r[k] for r in rows if r[k] is not None]) for k in keys},
        "rows": rows,
        "chat_tail": sid[-1500:],
    }
    pathlib.Path(out).write_text(json.dumps(rep, ensure_ascii=False, indent=1))
    print(json.dumps({"browser": BROWSER, "responses": len(rows), "audio": audio_info}, ensure_ascii=False))
    for k in keys:
        s = rep["summary"][k]
        if s.get("n"):
            print(f"{k:28} n={s['n']:>2} min={s['min']:>7} p50={s['p50']:>7} p95={s['p95']:>7} max={s['max']:>7}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
