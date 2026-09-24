# QEVION — Latency Root-Cause Investigation (2026-09-24)

Baseline: CP-0017 (`9c68d24`, 299 tests). No behaviour was changed. The only additions are opt-in, observation-only
latency marks (`QEVION_LATENCY_TRACE=1`, off by default) plus diagnostic harnesses. CI still PASS 299.

## 1. Executive conclusion

**Classification: CONFIRMED PROVIDER BOTTLENECK on tool turns + UX OPTIMIZATION OPPORTUNITY on endpointing.**
**NO CONFIRMED QEVION DEFECT. NO browser/network bottleneck in the measured environment.**

* **No-tool turns are within the spec envelope.** Last user speech → first agent audio at the client:
  **p50 1011 ms, p95 1308 ms, max 1389 ms** (n=20). Spec §41 E2E target is p50 ≤ 1200 ms. That is met at p50,
  but p95 is above 1200.
* **Tool turns are the slow ones:** p50 2614 ms, p95 3216 ms, max 3673 ms (n=13). **All** of the extra time is
  spent in extra provider generation cycles. OpenAI Realtime answers a tool-using turn with 2–3 *silent*
  function-call responses before the spoken one, and each cycle costs ~450–750 ms of provider time. QEVION's
  part of each cycle is ≈ 2 ms (tool dispatch 0.6 ms + execution 1.0 ms + result submit). This was reproduced
  **directly against OpenAI without QEVION**, with the same config and the same clips: first audio p50 371 ms when
  the model does not call a tool, versus 1986 ms (min 1508, max 2193) when it does.
* **The largest single fixed cost is the endpointing silence window:** a deliberate 500 ms `min_silence_ms`
  (measured T1→T3 p50 504 ms, p95 544 ms). It works as configured; it is not a bug. It is the only fixed
  QEVION-owned cost of any size.
* **QEVION runtime/orchestration adds ≈ 3–4 ms per turn** (commit 1.9 ms + forward 1.1 ms + WS 0.5 ms), well
  inside the spec target "QEVION-added total p50 < 60 ms".
* **The browser adds ≈ 75 ms** (Chromium: WS receive → worklet 0 ms, render 35 ms, device output estimate
  40 ms), within the §41 "playout → audible p95 < 80 ms" target. Firefox delivers in the same ≤ 2 ms. Its
  headless build did not render real audio, so its audible time is **UNPROVEN**.
* **TypeSafe was never on the critical path.** The composition under test uses `rules` only. 316 decision calls:
  p50 0.0 ms, max 0.4 ms, source RULE in 100 %.

## 2. Is there a real performance defect?

| Question | Verdict |
|---|---|
| QEVION Core/runtime adds meaningful latency | **NOT A DEFECT** — PROVEN (≈3–4 ms/turn) |
| Endpointing too slow / broken | **NOT A DEFECT, UX OPPORTUNITY** — PROVEN it is the configured 500 ms, nothing more |
| Tool turns slow because of QEVION | **NOT A DEFECT** — PROVEN (QEVION ≈2 ms per cycle; the delay reproduces without QEVION) |
| Tool turns slow because of the provider | **CONFIRMED PROVIDER BOTTLENECK** — PROVEN (direct probe) |
| Browser/playback | **NOT A DEFECT** in the measured environment — PROVEN for Chromium (≈75 ms); Firefox audible time UNPROVEN |
| Network | **NOT A BOTTLENECK** here — PROVEN (sandbox↔OpenAI commit ack p50 60 ms; server↔browser < 2 ms, localhost) |
| TypeSafe | **NOT INVOLVED** — PROVEN (rules-only composition) |
| User's own browser/device/network | **UNPROVEN** — this sandbox cannot see the user's machine; see §17 for how to measure it |

## 3–5. Measured timeline (server path, 33 turns, 6 sessions, 2 independent runs, 0 failed runs)

Single host clock (client and server in the same sandbox). ms.

| Segment | Owner | no-tool p50 / p95 / max (n=20) | tool p50 / p95 / max (n=13) |
|---|---|---|---|
| T1→T3 last speech → END_OF_TURN | turn plane (config) | 503 / 543 / 544 | 523 / 544 / 544 |
| T3→T4 EOT → provider commit sent | QEVION | 1.9 / 2.7 / 2.9 | 1.8 / 2.8 / 6.7 |
| T4→T5 commit → provider ack | network + provider | 61 / 74 / 76 | 59 / 64 / 67 |
| T4→T6 commit → response.created | network + provider | 69 / 80 / 82 | 67 / 72 / 76 |
| T6→T7 response.created → first audio | **provider** | 441 / 705 / 791 | **2005 / 2617 / 3122** |
| T7→T8 provider audio → QEVION sends to client | QEVION | 1.1 / 1.5 / 1.6 | 1.2 / 1.4 / 1.6 |
| T8→T9 QEVION send → client receives | WS (localhost) | 0.6 / 0.7 / 0.7 | 0.5 / 0.7 / 0.8 |
| **T1→T9 last speech → first audio at client** | all | **1011 / 1308 / 1389** | **2614 / 3216 / 3673** |
| T13→T14 tool execution | QEVION | — | 1.0 / 1.2 / 1.4 |
| T15→T17 tool result submitted → next audio | provider | — | 471 / 532 / 697 |
| T3→T18 EOT → last response done (incl. speaking) | all | 2588 / 4571 / 4623 | 4258 / 5561 / 5849 |

By tool count: 2 tools (n=8) T1→T9 p50 2450 ms; 3 tools (n=5) p50 3180 ms. That is ≈ +700 ms per extra tool
round trip, all of it provider time.

Browser leg (Chromium, real console code, `evidence/latency/browser_chromium.json`): T8→T9 0.5 ms, T9→T10 0 ms,
T10→T11 render 35–38 ms, device output estimate 40 ms (`baseLatency` 10 ms + render quantum).
**T9→T11 ≈ 75–78 ms**, n=2 rendered samples out of 4 responses; the other 2 were cancelled by barge-in before any
sample rendered. Firefox (`browser_firefox.json`): T8→T9 0.7–1.9 ms, T9→T10 0–1 ms; the headless build rendered
no samples, so its audible time is UNPROVEN.

**User-perceived latency for no-tool turns ≈ T1→T9 + 75 ms ≈ 1.09 s p50 / 1.38 s p95.**
**For tool turns ≈ 2.7 s p50 / 3.3 s p95.**

## 6. Provider contribution — isolation (same clips, same session.update, same commit timing, no QEVION)

`evidence/latency/direct_provider.json` (`scripts/latency_direct_provider.py`):

| Direct to OpenAI | first audio after commit, p50 / p95 / max |
|---|---|
| real tool set, model made **no** tool call (n=7) | **371 / 391 / 391** |
| real tool set, model **called** tools (n=4; 2–3 calls, 3–4 responses) | **1986 / 2193 / 2193** (min 1508) |
| `tools: []` (n=8 with audio; 3 produced no audio) | 802 / 1075 / 1075 |

Through QEVION: no-tool first audio after commit p50 505 ms; tool turns p50 2081 ms. **The delay pattern is the
same with and without QEVION**, so it comes from the provider path. The server path is ~130 ms slower than direct
at p50 on no-tool turns, but the direct samples are few and the runs were at different times. Either way the gap
is not QEVION's ~3 ms. It is provider variance.

Why tool turns are slow: in every tool turn the model first emits a function-call-only response (no audio). It
waits for the result, emits another, and only then speaks. For example, u7_correction does `record_field` →
`lookup_knowledge` → `compute_quote`. Each cycle's `response.created → function_call_arguments.done` is 420–840
ms of model time. QEVION answers each call in ≈ 2 ms.

## 7. TypeSafe contribution

Not on the path. `comp_s2s_openai_v1` uses `decision: rules`. 316 decide() calls, all source RULE, p50 0.0 ms,
max 0.4 ms. The rules-only vs rules+TypeSafe comparison was **not run**: no slow turn involved TypeSafe, so it
cannot explain any measured delay. If the user's slow sessions used `comp_mock_s2s_typesafe_v1`, the earlier
TypeSafe live measurement (p50 202 ms, p95 292 ms, only when rules return UNKNOWN) applies.

## 8. QEVION/Core contribution

≈ 3–4 ms per turn on the critical path (T3→T4 + T7→T8 + T8→T9), plus ≈ 2 ms per tool cycle. The only non-trivial
QEVION-owned cost is the configured 500 ms endpoint silence (see §12). Also measured: an instruction
`session.update` sent just before commit. Turns with it had first audio p50 561 ms (n=3), without it 497 ms
(n=17). The samples overlap, so there is **no demonstrated effect**.

## 9. Browser contribution

Chromium ≈ 75 ms (within the §41 target of 80 ms). No queue growth: the first frame reaches the worklet in the same
event-loop tick. No batching. Two different engines deliver the first frame to the worklet in ≤ 2 ms. The user's
real browser/device (Bluetooth, OS mixer, extensions, CPU load) is **not measurable from here → UNPROVEN**.

## 10. Network contribution

Sandbox → OpenAI → sandbox: commit→ack p50 60 ms, p95 74 ms. QEVION ↔ browser: < 2 ms, but that is localhost.
**A remote user adds their own RTT twice** (upload of the last speech frames, download of the first audio). That
is not measured here: UNPROVEN for the user's network.

## 11. Audio pipeline contribution

Capture: 20 ms frames, sent immediately. Server: provider audio forwarded in 1.1 ms, no buffering. Browser:
direct post to the worklet, first sample rendered 35 ms later, which is one render quantum plus scheduling.
No stage buffers more than intended. **Nothing to change.**

## 12. Endpointing contribution

Measured T1→T3 = configured `min_silence_ms` 500 ms + ≤ 44 ms of frame alignment. This is 45–50 % of the
no-tool latency. It is **working as designed**. Fragmentation: 11/33 turns got a premature END_OF_TURN inside a
natural pause of a long utterance (u1_order at 1.9 s, u_long at 10.4 s, u_ambig at 2.1 s). That created a
response which was then correctly cancelled by barge-in, 12 cancellations in total. Fragmented and clean no-tool
turns have the same final latency (p50 1011 vs 1008 ms), so fragmentation **does not add latency**. It costs
provider tokens and risks a clipped early answer. Spec QV-TURN-002 already says Egyptian hesitant speech may need
a *longer* silence window, so lowering it is not automatically right.

## 13. Tool/orchestration contribution

No duplicate calls, no retries, no timeout waits, no empty tool loops caused by QEVION. Tool dispatch → result
submit ≈ 2 ms. The multi-cycle pattern (function-call-only response → result → next response) is how the
provider handles tools. The number of cycles is driven by the instructions and tool set, which let the model
chain `record_field` → `lookup_knowledge` → `compute_quote` before speaking.

## 14–15. Reproducibility / environment dependence

Reproducible: two independent server runs (11 + 22 turns) and one direct-provider run agree. The provider tool
bottleneck does not depend on the user's environment. The user's own browser/device/network share is unknown.

## 16. Technical fixes — proposals only, NONE implemented (the rule forbids optimising before a decision)

| # | Change | Where | Expected effect (from data) | Risk |
|---|---|---|---|---|
| A | Let the model **speak a short acknowledgement before/while calling tools** (instruction change; Blueprint-level, no Core change) | instruction composer / activity persona | tool turns: first audio from ~2.6 s → ≈ no-tool level (~1.0–1.1 s), because the first response would carry audio | medium: the model may speak before data is validated; must stay within ClaimGovernor rules |
| B | **Batch tool calls** (parallel function calls in one response) instead of 3 sequential cycles | instructions / tool descriptions | −450…−750 ms per avoided cycle (≈ −1.4 s on 3-tool turns) | low–medium: needs an eval run for correctness |
| C | Endpoint silence 500 → 400 ms (config only, `config/compositions`, QV-TURN-002 allows it) | composition `turn.min_silence_ms` | −100 ms on every turn | **raises fragmentation on hesitant Egyptian speech**; needs human-speech validation first. Not recommended without it |
| D | Semantic end-of-turn (smart_turn adapter already exists) | composition | could cut 200–400 ms *and* reduce fragmentation | medium: needs a model + evaluation |

Recommended order: **A and B** (they target the measured dominant cost; instruction/config only, reversible), then
evaluate D. Do not do C blindly.

## 17. User-side verification (only needed if the user's delay is larger than the numbers above)

With the server started with `QEVION_LATENCY_TRACE=1`, `/api/sessions/{sid}/latency-trace` gives the server
marks, and the console records `window.__qevionLatency` (WS receive / worklet / rendered / audible estimate).
If the user's T9→T11 is ≫ 80 ms, or T1→T9 ≫ the table above on no-tool turns, test in this order:
another browser or a clean profile, wired audio instead of Bluetooth (Bluetooth typically adds 150–300 ms of
output latency), a different network. Expected effect: T9→T11 back to ≈ 75 ms.

## 18–21. Decision

* **No change to Core, transport, keepalive, playback, state machines or provider selection is justified.**
* Replacing OpenAI is **not** justified. Its no-tool first audio (≈ 370–500 ms) is good. The tool-turn cost is a
  tool-usage pattern that proposals A/B address inside the same provider.
* Replacing TypeSafe is **not** justified (not involved).
* MUST NOT change: turn plane, barge-in path, audio forwarding, playout worklet, WS keepalive. All measured at
  ≤ 2 ms or within target.

## 22. Evidence

* `evidence/latency/corpus_server_r1.json`, `corpus_server_r2.json` — raw per-mark traces + per-turn rows
* `evidence/latency/combined_server_stats.json` — the tables above
* `evidence/latency/direct_provider.json` — provider isolation
* `evidence/latency/browser_chromium.json`, `browser_firefox.json` — browser leg
* Harnesses: `scripts/latency_corpus.py`, `scripts/latency_direct_provider.py`, `scripts/latency_browser.py`
* Instrumentation: `QEVION_LATENCY_TRACE=1` (Core `_lt`, OpenAI adapter `trace`, runtime `_TimedDecision`,
  console `latencyMark`) — off by default, observation only

Limitations: synthetic TTS speech; noiseless input; server and client share a host, so the user's RTT is not
included; Firefox headless audible time not measurable; direct-provider sample n=22 (one run).

## 23. Final classification

**CONFIRMED PROVIDER BOTTLENECK** (tool-using turns: sequential function-call cycles, ~2 s of provider time)
**+ UX OPTIMIZATION OPPORTUNITY** (fixed 500 ms endpoint window; acknowledgement-before-tools).
**NO CONFIRMED QEVION DEFECT.**
