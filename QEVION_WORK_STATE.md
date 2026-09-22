# QEVION Work State (live)

> Read `QEVION_SESSION_RECOVERY_PROTOCOL.md` first. This file is updated at every checkpoint and before risky work.

| Field | Value |
|---|---|
| Project phase | P1 — Generic Core |
| Current stage | **P1 COMPLETE** (CP-0004) → P2 Knowledge + Blueprint + Preflight (CP-0005) |
| Current objective | P2: `qevion/knowledge/` ingestion pipeline (parse→normalize→entities→facts→relationships→gaps→contradictions→ambiguity→customer questions→operational requirements) with provenance; `qevion/control/` Blueprint validator, Preflight READY/BLOCKED with reason codes, readiness lifecycle, Capability Registry mapping, versioning/pinning → CP-0005 |
| Last verified checkpoint | CP-0004 (P1 Generic Core) — `recovery/checkpoints/CP-0004.md`, tag `cp/CP-0004` |
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

## In progress
- **P2 (CP-0005 prep)** landed: `qevion/control/preflight.py` (13 checks, 20 reason codes; 31 tests), `readiness.py` (lifecycle machine, ActivationGates, BFS legal path; QV-ACC-013), `capabilities.py` (registry builder + RequirementMapping). CI_LOCAL PASS @ d08e6f2 (137 tests). Remaining: `qevion/knowledge/` ingestion pipeline + gap/contradiction classes (QV-ACC-012), Blueprint cross-field validator is covered by Preflight; version pinning/diff; evidence + CP-0005.

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
1. **P2 (CP-0005)**: `qevion/knowledge/` (models already in contracts/knowledge.py): parsers (txt/md/csv/yaml/json; pdf via optional dep), normalizer, entity/fact extraction (structured-first, deterministic; LLM port optional & never business truth), relationships, gap classifier (REQUIRED_FOR_EXECUTION/IMPORTANT_FOR_QUALITY/OPTIONAL_IMPROVEMENT/POLICY_RISK/DATA_CONFLICT/UNKNOWN), contradiction + ambiguity detection, customer-question mining, operational-requirements derivation; `qevion/control/`: Blueprint validator (cross-field), Preflight (reason codes §11), readiness lifecycle machine, Capability Registry + mapping (SUPPORTED_WITH_CONFIGURATION/REQUIRES_TOOL/…), version pinning/diff; tests + evidence.
2. P3 → CP-0006 · P4 → CP-0007 · P5 → CP-0008 · P6 → CP-0009

## Exact next action
`qevion/knowledge/pipeline.py`: parsers (csv/yaml/json/md/txt) → normalize → entities/facts with provenance+locator → contradictions (same subject/predicate, different value; priority resolution) → gaps (per Activity requirement/field) → customer-question mining; `tests/test_knowledge_pipeline.py` with seeded fixtures (QV-ACC-012) → ci_local → CP-0005.
