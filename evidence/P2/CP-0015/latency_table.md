# Live latency / transcription table (synthetic ar-EG clips, OpenAI Realtime)

Server-clock Core events. Synthetic TTS speech → lifecycle/latency evidence, not human-speech fidelity.

| trace | detector | transcription | health | clips | commits | EOT→first audio ms | barge-in t1→t3 ms (forced) | CER |
|---|---|---|---|---|---|---|---|---|
| trace_normal.json | silero | gpt-4o-transcribe | PASS | 3 | 3 | 99, 1993, 67 | 3, 4 | u1_order:0.019, u2_address:0.244, u3_yes:0.0 |
| trace_bargein.json | silero | gpt-4o-transcribe | PASS | 3 | 3 | - | 6, 5 | u1_order:0.038, u7_correction:0.0, u2_address:0.244 |
| trace_late_bargein.json | silero | gpt-4o-transcribe | PASS | 3 | 3 | 92, 1745, 1465 | 4, 2 | u1_order:0.0, u7_correction:0.0, u2_address:0.244 |

## Summary

```json
{
 "traces": 3,
 "turns_measured": 6,
 "eot_to_first_audio_ms": {
  "p50": 99,
  "p95": 1993,
  "max": 1993
 },
 "barge_ins": 6,
 "barge_in_t1_t2_ms": {
  "p50": 2,
  "p95": 3
 },
 "barge_in_t1_t3_ms": {
  "p50": 4,
  "p95": 6,
  "max": 6
 },
 "forced_stops": 0,
 "cer_mean": 0.088,
 "split_turns": 0
}
```
