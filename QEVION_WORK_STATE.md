# QEVION Work State (live)

> Read `QEVION_SESSION_RECOVERY_PROTOCOL.md` first. This file is updated at every checkpoint and before risky work.

| Field | Value |
|---|---|
| Project phase | P2 — Knowledge + Blueprint + Preflight |
| Current stage | **P2 COMPLETE** (CP-0005) → P3 Copilot + Web (CP-0006) |
| Current objective | P3: `qevion/copilot/` (dynamic discovery engine: next-question from Blueprint state + gaps + capability mapping; ASK_OWNER escape hatch; Blueprint proposals with Decision records; stop-asking rule) + `qevion/runtime/` FastAPI app (REST for tenants/activities/knowledge/preflight/readiness; WS session endpoint on mocks) + `web/` single TypeScript app with 3 modes: Config Center, Operator Console, Admin (in-memory ephemeral test-key UI for Chat & Calls) → CP-0006 |
| Last verified checkpoint | CP-0005 (P2 Knowledge + Control) — `recovery/checkpoints/CP-0005.md`, tag `cp/CP-0005` |
| Last known good Git SHA | see `recovery/checkpoints/index.jsonl` last line (CP-0001) |
| Approval | Operator approved full plan + decisions D1–D15 on 2026-09-22 (see `recovery/analysis/pre_approval_inspection_2026-09-22.md`) |

## Completed (with evidence)
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
- CP-0005 record + tag + snapshot (this commit)

## Incidents
- 2026-09-22 #1: sandbox reset lost ~1h of uncommitted P0 work. Classified: test/environment. Countermeasure: protocol §8.1 commit-immediately. Redone in small increments.
- 2026-09-22 #2: two tool interruptions on large (>150-line) heredoc appends; §51–52 append lost once. Countermeasure: appends ≤ ~80 lines per commit, push immediately, verify with `grep -n "^## §"` before each append. No data lost after adoption.
- 2026-09-22 #6: CI run 35777148614 failed (ruff import order in a test appended after the lint pass). Class: process. Fix: `scripts/ci_local.sh` + protocol §8.2a gate-before-push.
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
1. **P3 (CP-0006)**: `qevion/copilot/` discovery engine (no fixed questionnaire; prioritized questions from gaps/mapping/preflight; proposals carry `Decision{proposed_by: copilot, approved_by: None}`; LLM port optional for phrasing only) · `qevion/runtime/` FastAPI (tenants, activities/versions, knowledge upload→report, preflight, readiness transitions, capability mapping, sessions over WS with mock composition; CredentialResolver wired; ephemeral in-memory test key endpoint) · `web/` TypeScript app: Config Center (copilot chat + Blueprint review + gaps + preflight), Operator Console (live state/events/handoff queue), Admin (tenants, providers, ephemeral test key for Chat & Calls) · preview via sandbox service URL.
2. P4 → CP-0007 · P5 → CP-0008 · P6 → CP-0009

## Exact next action
`checkpoint.sh CP-0005 P2 "Knowledge pipeline + Preflight + readiness + capability mapping"` → fill → commit → tag → snapshot; then P3 step 1: `qevion/copilot/discovery.py` (question generation from gaps + mapping + preflight findings, prioritization, stop rule) + tests.