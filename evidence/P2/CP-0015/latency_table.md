# Live latency / transcription table (synthetic ar-EG clips, OpenAI Realtime)

Server-clock Core events. Synthetic TTS speech → lifecycle/latency evidence, not human-speech fidelity.

| trace | detector | transcription | health | clips | commits | EOT→first audio ms | barge-in t1→t3 ms (forced) | CER |
|---|---|---|---|---|---|---|---|---|
| trace_normal.json | silero | gpt-4o-transcribe | PASS | 3 | 3 | 99, 1993, 67 | 3, 4 | u1_order:0.019, u2_address:0.244, u3_yes:0.0 |
| trace_late_bargein.json | silero | gpt-4o-transcribe | PASS | 3 | 3 | 92, 1745, 1465 | 4, 2 | u1_order:0.0, u7_correction:0.0, u2_address:0.244 |
| trace_bargein_1.json | silero | gpt-4o-transcribe | PASS | 3 | 3 | - | 4, 6 | u1_order:0.0, u7_correction:0.0, u2_address:0.244 |
| trace_bargein_2.json | silero | gpt-4o-transcribe | PASS | 3 | 3 | - | 5, 4 | u1_order:0.0, u7_correction:0.0, u2_address:0.244 |
| trace_normal_whisper.json | silero | whisper-1 | PASS | 3 | 3 | 89, 2837, 1392 | 3, 5 | u1_order:0.019, u2_address:0.244, u3_yes:0.0 |

## Summary

```json
{
 "traces": 5,
 "turns_measured": 9,
 "eot_to_first_audio_ms": {
  "p50": 1392,
  "p95": 2837,
  "max": 2837
 },
 "barge_ins": 10,
 "barge_in_t1_t2_ms": {
  "p50": 2,
  "p95": 4
 },
 "barge_in_t1_t3_ms": {
  "p50": 4,
  "p95": 6,
  "max": 6
 },
 "forced_stops": 0,
 "cer_mean": 0.084,
 "split_turns": 0
}
```
