# Latency options A / B — pre-registered acceptance criteria v2 (supersedes v1; written before any v2 run)

Applied mechanically by `scripts/latency_ab_eval.py <window>`; thresholds are constants in that file and never
change with results.

## Controlled window (`scripts/latency_ab_all.sh`, branch `latency-ab-experiment` only)
Fresh baseline → A → B → A+B, consecutively, same build (commit recorded in `window.json`), same 9 synthetic ar-EG
clips, same 2 session plans ×2 (22 turns per mode), same server config, audio pipeline, provider/model
configuration and harness. The historical baseline (`evidence/latency/ab_baseline.json`) is kept and is **not**
used for the verdict. The runner refuses to start unless it is on `latency-ab-experiment` and the offline safety
tests (`tests/test_latency_b_dependency_safety.py`, `test_latency_option_a.py`, `test_latency_option_b.py`) pass
on that exact build. Evidence is pushed only to `HEAD:latency-ab-experiment`.

## No-credit rule
Before every mode, a provider preflight opens a Realtime session. Any refusal (quota, auth, rate) → the window is
**INVALID**, it stops, the refusal evidence is committed, and no performance conclusion is drawn: verdict `INVALID`,
not `REVERT` and not `KEEP`. No code or threshold changes follow from an invalid window.

## A — content-free acknowledgement (A vs fresh baseline). KEEP only if all hold:
1. tool-turn `T1→T9` p50 improves ≥ 30 %; 2. tool-turn p95 not worse;
3. no-tool p50 regression ≤ max(10 %, 100 ms); 4. every acknowledgement passes the whole-token filter (no digits,
number words, prices, availability, recorded/confirmed/booked/succeeded claims; 1–8 words); zero violations;
5. zero provider errors, zero illegal transitions, zero session failures, every clip heard.

## B — dependency-aware batching (B vs fresh baseline, independently of A). KEEP only if all hold:
1. answer-after-tools `T1→T9a` p50 improves ≥ 15 %; 2. its p95 not worse; 3. median tool cycles decrease;
4. **exact semantic write preservation** per equivalent session: identical final recorded-field set and identical
   per-field write count (order ignored) — one dropped **or** duplicate write fails B;
5. zero tool errors, zero unresolved tool results; 6. no no-tool regression (rule A.3); 7. health as A.5;
8. offline safety proofs green on the same build: independent calls batch; dependent calls stay sequential;
   confirmation-gated and barrier (write/escalation except `record_field`) calls are never combined; a missing
   result is sent as explicit `result_pending, executed:false` before any continuation (never implied success).

## A+B — KEEP only if A is KEEP **and** B is KEEP **and** A+B shows no new regression
(ack safety, exact writes, health, no-tool, and answer latency not worse than A). Never selected for being fastest.

## Merge rule
Only an option whose own verdict is `KEEP` may be merged to `main`. Otherwise `main` stays unchanged and the
branch remains experimental evidence.
