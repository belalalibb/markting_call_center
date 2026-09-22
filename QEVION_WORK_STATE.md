# QEVION Work State (live)

> Read `QEVION_SESSION_RECOVERY_PROTOCOL.md` first. This file is updated at every checkpoint and before risky work.

| Field | Value |
|---|---|
| Project phase | P0 — Foundation |
| Current stage | **P0 COMPLETE** (CP-0003) → P1 Generic Core (CP-0004) |
| Current objective | P1: dialog machine, data-driven activity machine, FieldStore+provenance, Entity Focus Stack, PendingObjectives, Claim Governor, ConfirmationInterpreter, 11-step tool pipeline, Outcome Engine, InteractionRecord; Activities A–C run on mocks unchanged → CP-0004 |
| Last verified checkpoint | CP-0003 (P0.2 mocks for every port) — `recovery/checkpoints/CP-0003.md`, tag `cp/CP-0003` |
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

## In progress
- P1 (CP-0004 prep): all core primitives + `session.py` orchestrator + Activities A/B YAML landed (84bdd82…abcfbc6). Remaining: platform tool declaration catalog, memory backends for read tools, end-to-end scenario tests A–C on mocks, CP-0004 record/tag/snapshot/evidence.

## Incidents
- 2026-09-22 #1: sandbox reset lost ~1h of uncommitted P0 work. Classified: test/environment. Countermeasure: protocol §8.1 commit-immediately. Redone in small increments.
- 2026-09-22 #2: two tool interruptions on large (>150-line) heredoc appends; §51–52 append lost once. Countermeasure: appends ≤ ~80 lines per commit, push immediately, verify with `grep -n "^## §"` before each append. No data lost after adoption.
- 2026-09-22 #6: CI run 35777148614 failed (ruff import order in a test appended after the lint pass). Class: process. Fix: `scripts/ci_local.sh` + protocol §8.2a gate-before-push.
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
1. **P1 Core (CP-0004)** in `qevion/core/`: `dialog_machine.py`, `activity_machine.py` (generic default table + Blueprint table_ref/inline), `field_store.py` (provenance, corrections), `focus_stack.py`, `pending_objectives.py`, `claim_governor.py`, `confirmation.py`, `tool_pipeline.py` (11 steps, events), `outcome_engine.py`, `interaction_record.py`, `instruction_composer.py`, `session.py` (orchestrates ports via contracts only); example Activities A (restaurant) + B (clinic) YAML; scenario tests on mocks; core grep gate; import-linter
2. P2 → CP-0005 · P3 → CP-0006 · P4 → CP-0007 · P5 → CP-0008 · P6 → CP-0009

## Exact next action
`qevion/core/platform_tools.py` (tool.v1 declarations for the 14 generic tools) → memory backends for lookup/get/list/compare/recommend/compute_quote → `tests/test_core_session_scenarios.py` (A/B/C on mocks) → ci_local → CP-0004.
