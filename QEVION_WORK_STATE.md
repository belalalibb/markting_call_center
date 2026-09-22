# QEVION Work State (live)

> Read `QEVION_SESSION_RECOVERY_PROTOCOL.md` first. This file is updated at every checkpoint and before risky work.

| Field | Value |
|---|---|
| Project phase | P0 — Foundation |
| Current stage | P0.1 Recovery infrastructure + authoritative spec v3 |
| Current objective | Land recovery system, archive v2.3, write `QEVION_PLATFORM_SPEC_v3.md`, registries, ADRs, README; then scaffold + contracts (P0.2) |
| Last verified checkpoint | none yet (CP-0001 pending) |
| Last known good Git SHA | 8f722d5 (recovery protocol + .gitignore, pushed) |
| Approval | Operator approved full plan + decisions D1–D15 on 2026-09-22 (see `recovery/analysis/pre_approval_inspection_2026-09-22.md`) |

## Completed (with evidence)
- Pre-approval inspection & approval — evidence: `recovery/analysis/pre_approval_inspection_2026-09-22.md`
- `QEVION_SESSION_RECOVERY_PROTOCOL.md`, `.gitignore` — commit 8f722d5 on origin/main

## In progress
- Recovery scripts (`scripts/recovery/*.sh`), this file, inspection report copy → commit next
- `QEVION_PLATFORM_SPEC_v3.md` (written in committed parts: Part I → … → Appendices)

## Incidents
- 2026-09-22: sandbox reset lost ~1h of uncommitted P0 work (recovery files, archive moves, spec Part I–IV draft). Classified: test/environment. Countermeasure: protocol §8.1 commit-immediately rule. Work is being redone in small committed increments.

## Known failures
- none

## Known risks
- Sandbox: 2 vCPU / ~1 GB RAM / no GPU → local ASR/TTS candidates fixture-only.
- Real-provider evidence requires an operator-supplied test key (UI credential boundary, P3).

## Pending (ordered)
1. Commit scripts + work state + inspection copy
2. Archive v2.3 spec → `docs/archive/`; move master prompt → `docs/inputs/`
3. Write spec v3 Part I; commit. Parts II–IV; commit. Parts V–VI; commit. Parts VII–X + appendices; commit.
4. `docs/registry/{references,licenses}.yaml`, `docs/adr/0001-0004`, traceability matrix (in spec §56)
5. README update; CP-0001 record; tag; snapshot manifest; push
6. P0.2 scaffold: pyproject, `qevion/contracts`, schemas, mocks, import-linter, CI, gitleaks

## Exact next action
`git add -A && git commit -m "chore(recovery): scripts, work state, inspection report" && git push origin main`, then archive moves.
