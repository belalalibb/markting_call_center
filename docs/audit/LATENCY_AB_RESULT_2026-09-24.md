# Latency options A / B — result: NOT PROVEN → REVERTED on `main` (parked on branch `latency-ab-experiment`)

Criteria were pre-registered before any measurement: `docs/audit/LATENCY_AB_CRITERIA_2026-09-24.md`.

## What was built (isolated, opt-in, off by default)
* **A (tool acknowledgement):** one optional instruction section `tool_ack` — a 2–4-word, fact-free
  acknowledgement before tool calls (no numbers, names, prices, availability, and no "recorded/confirmed/succeeded").
  Every other instruction section was byte-identical (test). Flag `QEVION_TOOL_ACK` / binding `tool_ack`.
* **B (dependency-aware batching):** an instruction section `parallel_tools` (independent calls in one response;
  confirmation-gated / non-read tools other than `record_field` are barriers, always called alone). The OpenAI
  adapter sends **one** continuation per batch, only after `response.done` and after every call in it has a result,
  with a 1.5 s guard so an unanswered (confirmation-pending) call cannot stall. Flag `QEVION_PARALLEL_TOOLS` /
  binding `parallel_tools`. Core tool pipeline, governance and state machines were untouched.
* Offline tests: 8 (default path unchanged; batch ordering; results-after-done; stall guard; sections isolated).
  CI PASS 307 on the experiment branch.

## What was measured
| Run | Flags | Result |
|---|---|---|
| baseline | ack=0 parallel=0 | **valid**: 22 turns, 4/4 sessions, 0 errors (`evidence/latency/ab_baseline.json`) |
| A | ack=1 parallel=0 | **no data**: 4/4 sessions refused by OpenAI at connect |
| A+B | ack=1 parallel=1 | **no data**: 4/4 sessions refused by OpenAI at connect |

The provider refusal is `1013 insufficient_quota.credit_balance_exhausted`: the OpenAI account ran out of credit
immediately after the baseline run. It was reproduced with a single manual connection. This is not a code defect.
The baseline itself is consistent with the earlier investigation (tool turns T1→T9 p50 2684 ms, p95 3515 ms;
no-tool p50 1117 ms, p95 1552 ms; tool cycles median 3).

## Verdict (per the rule "prove the improvement with numbers, otherwise revert")
* **A: NOT PROVEN → REVERTED on `main`.**
* **B: NOT PROVEN → REVERTED on `main`.**
* `main` runtime code is byte-identical to the investigation baseline `b4edb95` (Core, runtime store, OpenAI
  adapter, instruction composer); CI PASS 299.
* The full implementation, tests and harness are preserved on branch **`latency-ab-experiment`**, ready to
  re-measure. Nothing was merged on belief.

## To finish the gate (once OpenAI credit is restored)
```
git checkout latency-ab-experiment
OPENAI_API_KEY=… bash scripts/latency_ab_all.sh      # baseline is reused if present; runs A, then A+B
.venv/bin/python scripts/latency_ab_eval.py          # applies the pre-registered criteria mechanically
```
Merge A and/or B to `main` only if `ab_verdict.json` says `KEEP` for it.
