# QEVION Work State (live)

> Read `QEVION_SESSION_RECOVERY_PROTOCOL.md` first. This file is updated at every checkpoint and before risky work.

| Field | Value |
|---|---|
| Project phase | P0 — Foundation |
| Current stage | P0.2 contracts+CI COMPLETE (CP-0002) → mocks for every port (CP-0003) |
| Current objective | Mock adapters for every port (s2s/llm/asr/tts/turn/decision/transport/tool backend/sinks/telephony/credential resolver) + tests → CP-0003; then P1 generic Core |
| Last verified checkpoint | CP-0002 (P0.2 contracts + CI) — `recovery/checkpoints/CP-0002.md`, tag `cp/CP-0002` |
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

## In progress
- CP-0002 record + tag (this commit)

## Incidents
- 2026-09-22 #1: sandbox reset lost ~1h of uncommitted P0 work. Classified: test/environment. Countermeasure: protocol §8.1 commit-immediately. Redone in small increments.
- 2026-09-22 #2: two tool interruptions on large (>150-line) heredoc appends; §51–52 append lost once. Countermeasure: appends ≤ ~80 lines per commit, push immediately, verify with `grep -n "^## §"` before each append. No data lost after adoption.
- 2026-09-22 #4: second sandbox reset after commit 1232994; lost only uncommitted skeletons/CI yaml (~5 min). Protocol worked: resume in <3 min, zero rebuild.
- 2026-09-22 #3: verify.sh false positive (`sk-` pattern matched "risk-management"). Fixed with `\b` boundary — f0bc8ef.

## Known failures
- none open

## Known risks
- Sandbox: 2 vCPU / ~1 GB RAM / no GPU → local ASR/TTS candidates are stubs (A9).
- Real-provider evidence (QV-ACC-022) requires operator-supplied test key (A5) — Admin ephemeral UI lands in P3.

## Pending (ordered)
1. **CP-0003** mocks: `qevion/adapters/providers/mocks.py` (s2s/llm/asr/tts), `adapters/turn/mock.py`, `adapters/decision/rules.py` (deterministic default, ADR-0004), `adapters/transports/memory.py`, `adapters/tools/memory_backend.py`, `adapters/sinks/memory.py`, `admin/credentials.py` (CredentialResolver env→store→ephemeral), `adapters/telephony/simulated.py`; Protocol-conformance tests
2. **P1** generic Core → CP-0004 (dialog machine, activity machine table, FieldStore, focus stack, pending objectives, claim governor, confirmation, tool pipeline, outcome engine, interaction record; Activities A–C on mocks)
3. P2 → CP-0005 · P3 → CP-0006 · P4 → CP-0007 · P5 → CP-0008 · P6 → CP-0009

## Exact next action
`scripts/recovery/checkpoint.sh CP-0002 P0.2 "contracts + schemas + CI green"` → fill → commit → tag → snapshot → then write mock adapters (CP-0003 step 1).
