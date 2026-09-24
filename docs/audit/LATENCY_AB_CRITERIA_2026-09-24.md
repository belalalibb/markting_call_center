# Latency options A / B — pre-registered acceptance criteria (written before any A/B measurement)

Same code, same clips (9 synthetic ar-EG clips, 2 session plans), same harness (`scripts/latency_corpus.py` via
`scripts/latency_ab.sh`), fresh server per run, `--repeat 2` (22 turns per run). Flags are env overrides of the
same build: baseline `QEVION_TOOL_ACK=0 QEVION_PARALLEL_TOOLS=0`, A `1 0`, A+B `1 1`.

Metrics (from Core/provider/client marks, one host clock):
* `T1_T9` last user speech → first agent audio at the client (what the caller hears first)
* `T1_T9a` last user speech → first audio of the *answer* (first audio after the last tool result)
* `tool_cycles` provider `response.create` sends per turn minus 1

## A — content-free acknowledgement before tools (compare A vs baseline)
KEEP only if all hold:
1. tool turns `T1_T9` p50 improves ≥ 30 % and p95 does not get worse;
2. no-tool turns `T1_T9` p50 does not regress by more than 10 % or 100 ms (whichever is larger);
3. **safety:** every spoken acknowledgement (operator transcript of audio spoken before the last tool result) contains
   no digit, no Arabic-Indic digit, no Arabic number word from the corpus vocabulary, and ≤ 8 words;
   0 violations allowed;
4. health: 0 provider errors, 0 illegal dialog transitions, 0 session errors, every clip heard.
Otherwise REVERT A (flag default stays off and the section is removed).

## B — dependency-aware batched/parallel tool execution (compare A+B vs A)
KEEP only if all hold:
1. tool turns `T1_T9a` p50 improves ≥ 15 % vs A and p95 does not get worse;
2. tool turns median `tool_cycles` decreases;
3. correctness: per-session number of `record_field` executions and final recorded field names are the same order
   of magnitude as A (no dropped writes: ≥ 80 % of A's recorded-field count), 0 tool errors caused by batching;
4. health as in A; no-tool turns not regressed (A.2 rule vs A).
Otherwise REVERT B.

If a result is inside noise (criteria not met), the option is reverted even if it "looks" faster.
