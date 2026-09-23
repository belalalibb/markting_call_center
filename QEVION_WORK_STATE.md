# QEVION Work State (live)

> Read `QEVION_SESSION_RECOVERY_PROTOCOL.md` first. This file is updated at every checkpoint and before risky work.

| Field | Value |
|---|---|
| Project phase | P4 — Voice Runtime |
| Current stage | **P4 COMPLETE** (CP-0007) → P5 Simulation + Activation + Outbound (CP-0008) |
| Current objective | P5: `qevion/simulation/` scenario runner (scripted caller personas drive `core.session.Session` on the mock composition from Blueprint `simulation_cases`; SimulationReport contract with per-case pass/fail + outcome diff), Activation gates (strict preflight + simulation pass → READY, evidence attached to the readiness transition), Outbound seam (`telephony/simulated` dial → session with `outbound` channel; consent/opt-out invariants) → CP-0008. (Prev P4: OpenAI Realtime + Silero/SmartTurn adapters, compositions + credential source per session, browser voice console with AudioWorklet + VoiceClient, §31 t0..t4 measured E2E over public WSS → CP-0007) |
| Last verified checkpoint | CP-0007 (P4 Voice Runtime) — `recovery/checkpoints/CP-0007.md`, tag `cp/CP-0007` |
| Last known good Git SHA | see `recovery/checkpoints/index.jsonl` last line (CP-0007 = bc9e060) |
| Approval | Operator approved full plan + decisions D1–D15 on 2026-09-22 (see `recovery/analysis/pre_approval_inspection_2026-09-22.md`) |

## Completed (with evidence)
- **CP-0007 (P4):** `qevion/adapters/providers/openai_realtime.py` (S2S over WS, injectable socket, session.update/input_audio_buffer/response.cancel/function calls; PermissionError without credential), `qevion/adapters/turn/{silero,smart_turn}.py` (honest fallback capabilities), `runtime/store.py` compositions + adapter registries + `composition_for` + credential source per session + realtime mock for voice + filtered event mirror, `runtime/app.py` `/api/compositions`, `?composition=`, guarded provider failures, `interruptions[]` in session detail; `web/src/audio/{worklet,client}.ts` + voice-wired Operator Console (composition selector, mic + meter, playout, QV-INT metrics card; dist rebuilt); `scripts/e2e_voice_probe.py`. Tests: 219 (+23) — **CI_LOCAL PASS**; evidence `evidence/P4/CP-0007/` (junit, licenses, latency_table ×10 runs over public WSS, e2e_voice_preview); QV-ACC-017/018 accepted (first audio p50 5 ms; all t0..t4 recorded, t1→t3 p95 2 ms server / 11 ms wall), QV-ACC-019 → P6.
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
- none (CP-0007 closed: record bc9e060, tag cp/CP-0007, snapshot manifest)

## Incidents
- 2026-09-23 #12: sandbox resets #12–#15 during P4 (venv/node_modules wiped 4×; one interrupted checkpoint step). Zero committed work lost; index.json + CP-0007.md redone after verifying actual state (not blindly re-run). Rule held: commit before first test/build.
- 2026-09-23 #13: voice WS test hung under TestClient — classified: design (mock provider streamed inline in the provider pump, so client frames were never consumed mid-response; events also not mirrored to client). Fix: realtime mock streams in a background task; runtime sink mirrors a filtered event subset. Not a Core change.
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
- Real-provider evidence (QV-ACC-022) requires operator-supplied test key (A5); Admin ephemeral UI exists. ACC-017/018 currently measured on the mock provider only.
- Browser mic path not exercised headless (no mic in Playwright); WS/binary contract covered by `scripts/e2e_voice_probe.py`.

## Pending (ordered)
1. **P5 (CP-0008)**: `qevion/contracts/simulation.py` (`qevion.simulation.v1`: Persona, ScenarioCase, SimulationReport) + schema; `qevion/simulation/runner.py` (drives Session on mock composition with scripted caller turns incl. interruptions/off-topic/opt-out; asserts expected outcome + fields + no forbidden claims); Activation gates wired into readiness (strict preflight + simulation pass + approvals → READY; evidence refs on the transition); Outbound seam (`outbound` channel via `telephony/simulated`, consent/DNC/opt-out invariants, attempt record); REST + Config Center "Simulate"/"Activate" actions; QV-ACC-020/021.
2. P6 → CP-0009 (Evaluation harness + deterministic replay QV-ACC-019 + Evidence pack + verified Preview URL; real-provider smoke if A5 key present).

## Exact next action
P5 step 1: create `qevion/contracts/simulation.py` + register in `qevion/contracts/registry.py` → `scripts/gen_schemas.py` (42 schemas) → round-trip test → commit; then `qevion/simulation/runner.py` skeleton (commit before first test run).
