# QEVION Work State (live)

> Read `QEVION_SESSION_RECOVERY_PROTOCOL.md` first. This file is updated at every checkpoint and before risky work.

| Field | Value |
|---|---|
| Project phase | P0 — Foundation |
| Current stage | P0.1 COMPLETE → P0.2 Scaffold + contracts (starting) |
| Current objective | pyproject, `qevion/contracts` (Pydantic v2) + JSON Schemas + round-trip tests, mocks for every port, import-linter, CI, `.env.example` → CP-0002/0003 |
| Last verified checkpoint | CP-0001 (P0.1 foundation) — `recovery/checkpoints/CP-0001.md`, tag `cp/CP-0001` |
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

## In progress
- CP-0001 record + tag + snapshot (this commit)

## Incidents
- 2026-09-22 #1: sandbox reset lost ~1h of uncommitted P0 work. Classified: test/environment. Countermeasure: protocol §8.1 commit-immediately. Redone in small increments.
- 2026-09-22 #2: two tool interruptions on large (>150-line) heredoc appends; §51–52 append lost once. Countermeasure: appends ≤ ~80 lines per commit, push immediately, verify with `grep -n "^## §"` before each append. No data lost after adoption.
- 2026-09-22 #3: verify.sh false positive (`sk-` pattern matched "risk-management"). Fixed with `\b` boundary — f0bc8ef.

## Known failures
- none open

## Known risks
- Sandbox: 2 vCPU / ~1 GB RAM / no GPU → local ASR/TTS candidates are stubs (A9).
- Real-provider evidence (QV-ACC-022) requires operator-supplied test key (A5) — Admin ephemeral UI lands in P3.

## Pending (ordered)
1. **P0.2** `pyproject.toml` (py3.12+, pydantic v2, fastapi, pytest, hypothesis, ruff, mypy, import-linter) + `.env.example` + `.importlinter` → commit
2. `qevion/contracts/` models for every v1 contract in spec §37 inventory; `scripts/gen_schemas.py` → `qevion/contracts/schemas/*.json`; round-trip tests → commit → CP-0002
3. `qevion/adapters/**/mocks` for s2s/llm/asr/tts/turn/decision/transport/tool/sink/telephony ports; `.github/workflows/ci.yml` (ruff, mypy, pytest, gitleaks, license scan) → commit → CP-0003
4. P1 generic Core per §51 → CP-0004
5. P2 → CP-0005 · P3 → CP-0006 · P4 → CP-0007 · P5 → CP-0008 · P6 → CP-0009

## Exact next action
`scripts/recovery/checkpoint.sh CP-0001 P0 "P0.1 foundation: recovery infra + spec v3 + registries + ADRs"` → fill record → commit → `tag_checkpoint.sh CP-0001` → `snapshot.sh CP-0001` → commit manifest → push. Then start P0.2 step 1.
