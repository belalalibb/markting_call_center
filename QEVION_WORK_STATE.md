# QEVION Work State (live)

> Read `QEVION_SESSION_RECOVERY_PROTOCOL.md` first. This file is updated at every checkpoint and before risky work.

| Field | Value |
|---|---|
| Project phase | P3 — Copilot + Web |
| Current stage | **P3 COMPLETE** (CP-0006) → P4 Voice Runtime (CP-0007) |
| Current objective | P4: `qevion/runtime/audio/` AudioWorklet PCM16 capture/playout in `web/`, WS binary framing, `qevion/adapters/providers/openai_realtime.py` (S2S over WebSocket, tool calls, barge-in cancel), turn adapters Silero VAD + Smart Turn (energy fallback on 2vCPU), 7-step interruption t0..t4 measured end-to-end, `comp_s2s_openai_v1` wired with CredentialResolver → CP-0007. (Prev P3: `qevion/copilot/` (dynamic discovery engine: next-question from Blueprint state + gaps + capability mapping; ASK_OWNER escape hatch; Blueprint proposals with Decision records; stop-asking rule) + `qevion/runtime/` FastAPI app (REST for tenants/activities/knowledge/preflight/readiness; WS session endpoint on mocks) + `web/` single TypeScript app with 3 modes: Config Center, Operator Console, Admin (in-memory ephemeral test-key UI for Chat & Calls) → CP-0006 |
| Last verified checkpoint | CP-0006 (P3 Copilot + Web) — `recovery/checkpoints/CP-0006.md`, tag `cp/CP-0006` |
| Last known good Git SHA | see `recovery/checkpoints/index.jsonl` last line (CP-0001) |
| Approval | Operator approved full plan + decisions D1–D15 on 2026-09-22 (see `recovery/analysis/pre_approval_inspection_2026-09-22.md`) |

## Completed (with evidence)
- **CP-0006 (P3):** `qevion/copilot/` — `discovery.py` (state-derived questions from draft holes + gaps + contradictions + preflight + capability mapping; deterministic band/blocking/stage prioritizer; sha256 question ids; stop rule), `composer.py` (answers→draft, Decision records `proposed_by/approved_by`, structural scaffold only), `explainer.py` (human output A + readiness 'what could go wrong'), `session.py` (ConfigSession loop, `config.*` events without business text), `api.py` (HTTP surface, publish gated on valid+approved+no blocking). `qevion/runtime/` — `store.py` (composition root state, registry from adapters + platform tools + locale packs + voice profiles), `app.py` (REST: tenants/activities/preflight/capabilities/transition/registry/knowledge/admin/sessions/events; WS `/ws/sessions/{key}` bridging core Session). `qevion/main.py` composition root (only module importing both runtime and copilot). `web/` Vite+TS (Config Center, Operator Console, Admin; `web/dist` tracked, served by FastAPI). `config/locale_packs`, `config/voice_profiles`. Tests: 196 (+46) — **CI_LOCAL PASS**; evidence `evidence/P3/CP-0006/` (junit, licenses, ACC-014 provenance diff, ACC-016 memory-only key, e2e over public URL); QV-ACC-014..016 accepted. Preview verified: 3 modes load with 0 console errors; WS text session round-trips audio_start/audio/audio_end.
- Pre-approval inspection & approval — `recovery/analysis/pre_approval_inspection_2026-09-22.md`
- Recovery Protocol, `.gitignore` — 8f722d5
- Recovery scripts `scripts/recovery/{checkpoint,tag_checkpoint,snapshot,restore,verify}.sh` — 3f4072c, f0bc8ef (regex fix)
- v2.3 archived → `docs/archive/`; master prompt → `docs/inputs/` — d5436f9
- **`QEVION_PLATFORM_SPEC_v3.md`** complete: §0–§56 + Appendices A–E (1543 lines) — 4572c93 … 4ce092c
- `docs/registry/{references,licenses,traceability}.yaml` — 431aedd, d5cd521, 021b8b7
- `docs/adr/0001–0004` — ef9533e, d3452f5
- README rewritten — b223765
- `scripts/recovery/verify.sh` → PASS (secret scan ok, recovery files ok, core gate skipped — no core yet)

- **P0.2:** `pyproject.toml`, `.importlinter` (5 contracts KEPT), `.env.example`, `qevion/contracts/*` (40 registered v1 contracts + port Protocols), `scripts/gen_schemas.py` → 40 JSON Schemas (2020-12) + drift check, 50 tests (round-trip + JSON Schema validation + blueprint fixtures + readiness), `config/examples/activity_c_survey.yaml`, `.github/workflows/ci.yml` (ruff, mypy strict, lint-imports, schema drift, pytest, verify.sh, license gate, gitleaks) — **CI green on main run 35775450363** — evidence `evidence/P0/CP-0002/`

- **CP-0003:** adapters — `decision/rules.py` (deterministic, ADR-0004), `providers/mocks.py` (scripted s2s w/ tool round-trip + cancel, llm, asr, tts), `turn/energy.py` (turn.v1 state machine + barge-in; mock alias), `transports/memory.py`, `tools/memory_backend.py` (fault injection), `sinks/memory.py` (memory+JSONL outcome, memory handoff), `admin/credentials.py` (env→admin→ephemeral, never logs), `telephony/simulated.py`; `config/compositions/*.yaml`; 67 tests; `scripts/ci_local.sh`; **CI green run 35777982470**; evidence `evidence/P0/CP-0003/`

- **CP-0004 (P1 Generic Core):** `qevion/core/` — `field_store.py` (provenance strength, corrections, execution readiness), `dialog_machine.py` (fixed), `activity_machine.py` (data-driven `generic_default_v1` + table validator), `context.py` (EntityFocusStack, PendingObjectives), `governance.py` (ClaimGovernor, ConfirmationInterpreter via decision port), `tool_pipeline.py` (11 steps, BudgetGuard, idempotency), `outcome_engine.py` (rules via decision port, generic primary precedence, InteractionRecord), `instruction_composer.py` (sectioned, fingerprinted), `platform_tools.py` (14 tool.v1 declarations), `session.py` (orchestrator; 7-step interruption with t0..t4; confirmation gate; authority model). Adapters: memory read-tool backends. Activities A (order intake) + B (appointment) YAML. Tests: 93 total incl. 12 end-to-end scenarios A/B/C on mocks — **CI_LOCAL PASS**; evidence `evidence/P1/CP-0004/`; QV-ACC-006..010 accepted.

- **CP-0005 (P2):** `qevion/control/preflight.py` (13 deterministic checks, all 20 §11 reason codes, path + fix_hint, approved-Decision waiver, strict/lenient UNVERIFIED), `readiness.py` (table-driven lifecycle, `ActivationGates`, BFS legal path, edit invalidation, immutability), `capabilities.py` (registry aggregated from adapter self-declarations + platform facts; `RequirementMapping`); `qevion/knowledge/parsers.py` (csv/json/yaml/txt/md, locators, size cap, injection flags) + `pipeline.py` (normative 10-step pipeline: entities, facts w/ provenance, relationships, cross-source contradictions with priority resolution or pending+DATA_CONFLICT, ambiguity, 6 gap classes vs Activity needs, customer questions, operational requirements; `StructuredRetriever` approved-only). Tests: 150 total (+57) — **CI_LOCAL PASS**; evidence `evidence/P2/CP-0005/`; QV-ACC-011..013 accepted.

## In progress
- CP-0006 record + tag + snapshot (this commit)

## Incidents
- 2026-09-22 #1: sandbox reset lost ~1h of uncommitted P0 work. Classified: test/environment. Countermeasure: protocol §8.1 commit-immediately. Redone in small increments.
- 2026-09-22 #2: two tool interruptions on large (>150-line) heredoc appends; §51–52 append lost once. Countermeasure: appends ≤ ~80 lines per commit, push immediately, verify with `grep -n "^## §"` before each append. No data lost after adoption.
- 2026-09-22 #6: CI run 35777148614 failed (ruff import order in a test appended after the lint pass). Class: process. Fix: `scripts/ci_local.sh` + protocol §8.2a gate-before-push.
- 2026-09-23 #11: sandbox resets #10/#11 mid-P3 wiped venv + (a) uncommitted `qevion/runtime/app.py` (Write ok, commit interrupted) and (b) four uncommitted edits (store wiring, mark_asked, publish gate, test fixes). Both recovered from session summary in one commit each. Countermeasure held: nothing committed was lost; ~10 min rework total.
- 2026-09-23 #10: sandbox reset #9 wiped venv + uncommitted `qevion/copilot/discovery.py` (Write succeeded, commit interrupted). Re-created from session summary in one step, committed before first test. Rule reaffirmed: commit new files before their first test run.
- 2026-09-22 #8: sandbox resets #7/#8 (after fa2a6d0, after 38afdb9); one uncommitted file (capabilities.py, ~5 min) re-created; GitHub transient `commit_refs` push error once — retry succeeded.
- 2026-09-22 #7: sandbox reset #6 after abcfbc6; resume < 3 min, zero loss.
- 2026-09-22 #5: sandbox resets #3/#4/#5 between sessions; each resume < 3 min, zero rebuild (protocol holding).
- 2026-09-22 #4: second sandbox reset after commit 1232994; lost only uncommitted skeletons/CI yaml (~5 min). Protocol worked: resume in <3 min, zero rebuild.
- 2026-09-22 #3: verify.sh false positive (`sk-` pattern matched "risk-management"). Fixed with `\b` boundary — f0bc8ef.

## Known failures
- none open

## Known risks
- Sandbox: 2 vCPU / ~1 GB RAM / no GPU → local ASR/TTS candidates are stubs (A9).
- Real-provider evidence (QV-ACC-022) requires operator-supplied test key (A5) — Admin ephemeral UI lands in P3.

## Pending (ordered)
1. **P4 (CP-0007)**: browser AudioWorklet PCM16 (24k) capture + playout with `playout_started/stopped` timestamps; WS binary frames end-to-end; `openai_realtime` S2S adapter (session.update instructions, input_audio_buffer, response.cancel on barge-in, function calls → ToolPipeline); Silero VAD + Smart Turn adapters behind `TurnDetector` (energy fallback); interruption metrics t0..t4 per §31 written to events; `comp_s2s_openai_v1` selectable per activity; real-provider smoke only with operator test key (A5).
2. P5 → CP-0008 (Simulation personas + Activation gates + Outbound seam) · P6 → CP-0009 (Evaluation + Evidence + verified Preview URL)

## Exact next action
`checkpoint.sh CP-0006 P3 "Copilot + runtime API + web app"` → fill record → commit → `tag_checkpoint.sh CP-0006` → `snapshot.sh CP-0006`; then P4 step 1: `web/src/audio/worklet.ts` + `web/src/audio/client.ts` (PCM16 capture/playout, binary WS) and `qevion/adapters/providers/openai_realtime.py` skeleton with capability declaration + contract tests on a recorded event fixture (no key needed).
