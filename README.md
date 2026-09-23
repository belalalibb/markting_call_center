# QEVION — Agent Activity Platform

Configuration Copilot + provider-neutral realtime voice runtime. A **generic Core** executes any configured business *Activity* (inbound or outbound, voice or text) without domain code; a **Copilot** turns operator intent and documents into a validated, simulated Activity Blueprint; **provider role ports** (`s2s · llm · asr · tts · turn · decision`) keep the platform independent of any single vendor.

Primary language target: Egyptian Arabic (`ar-EG`). Primary POC provider: OpenAI Realtime API.

## Governing documents

| Document | Role |
|---|---|
| **[`QEVION_PLATFORM_SPEC_v3.md`](QEVION_PLATFORM_SPEC_v3.md)** | **Authoritative specification v3.0** (§0–§56 + Appendices A–E). Unifies SPEC v2.3 and the platform master prompt. Every normative rule has a grep-able `QV-*` ID. |
| [`QEVION_SESSION_RECOVERY_PROTOCOL.md`](QEVION_SESSION_RECOVERY_PROTOCOL.md) | Permanent protocol for resuming work after any session loss (`تابع <token>` = restore → verify → resume, never restart). |
| [`QEVION_WORK_STATE.md`](QEVION_WORK_STATE.md) | Live work state: current phase, last verified commit, exact next action. |
| [`docs/adr/`](docs/adr/) | Architecture Decision Records ADR-0001..0004 freezing operator decisions D1–D15. |
| [`docs/registry/`](docs/registry/) | `references.yaml` (external components + verdicts), `licenses.yaml` (license gate), `traceability.yaml` (v2.3 → v3, decisions, acceptance status). |
| [`recovery/`](recovery/) | Checkpoint records (`CP-NNNN.md`, `index.jsonl`), snapshot manifests, inspection reports. |
| [`docs/archive/`](docs/archive/) | SPEC v2.3 — superseded, kept for traceability (Appendix A). |
| [`docs/inputs/`](docs/inputs/) | Master prompt input — non-normative source material (Appendix B). |

## Non-negotiable rules (from spec §0–§1)

- **Core imports contracts only.** No domain vocabulary in `qevion/core` (enforced by import-linter + grep gate).
- **LLM output is never business truth.** Claims, prices, eligibility, confirmations and state transitions are decided by QEVION-owned deterministic logic (ADR-0004).
- **Copilot ≠ runtime.** The Copilot produces Blueprints; it never sits in the call path.
- **No hard-coded business logic.** Activities are data (`qevion.activity.v1`); see Appendix E.
- **Credentials never touch Git, logs or tracked files.** `CredentialResolver`: env → admin store → in-memory ephemeral UI key.
- **Evidence or it didn't happen.** Every completion claim points to an artifact under `evidence/`.

## Phases and checkpoints

P0 foundations → P1 generic Core → P2 knowledge/blueprint/preflight → P3 Copilot + web (Config Center · Operator Console · Admin) → P4 voice runtime (AudioWorklet PCM16 → WS → OpenAI Realtime, Silero VAD, 7-step interruption) → P5 simulation/activation/outbound → P6 evaluation + evidence + verified preview URL. Exit gates and acceptance criteria: spec §51–§52. Each gate produces a `cp/CP-NNNN` tag.

## Working in this repository

```bash
scripts/recovery/verify.sh          # secret scan, recovery files, core grep gate, tests, import rules
scripts/recovery/checkpoint.sh CP-000N P<phase> "title"   # create checkpoint record (clean tree required)
scripts/recovery/tag_checkpoint.sh CP-000N                # git tag cp/CP-000N + push
scripts/recovery/snapshot.sh CP-000N                      # tarball + manifest (no secrets, no audio)
scripts/recovery/restore.sh                               # venv / deps after a fresh sandbox
```

## Running the runtime

```bash
python3.13 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m qevion.main            # uvicorn with WS keepalive tuned for browser_voice (ping 25 s / timeout 60 s)
# equivalent: .venv/bin/uvicorn qevion.main:app --host 0.0.0.0 --port 8000 --ws-ping-interval 25 --ws-ping-timeout 60
```

Provider keys never go into tracked files: export `OPENAI_API_KEY` / `TYPESAFE_API_KEY`, or inject a memory-only
key via `POST /api/admin/test-key {"provider": "openai", "value": "…", "ttl_seconds": 900}`.

Live checks (evidence carries key fingerprints only): `scripts/ws_keepalive_soak.py` (protocol soak),
`scripts/browser_voice_smoke.py --base <url> --composition comp_s2s_openai_v1 --inject-key-env OPENAI_API_KEY`
(real Chromium, fake mic), `scripts/openai_realtime_live_ws.py`, `scripts/typesafe_live_ws.py`.

See `QEVION_WORK_STATE.md` for the current stage and exact next action.
