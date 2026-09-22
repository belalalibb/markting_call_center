# QEVION Session Recovery Protocol

**Status:** Permanent operating rule for the entire project lifetime.
**Scope:** Every executor (human or agent), every session, every phase.
**Companion file:** `QEVION_WORK_STATE.md` (live state — always read it second).

This protocol exists so that the project can be resumed after any interruption
(session loss, sandbox reset, executor change) **without relying on chat memory
and without rebuilding verified work.**

> Incident 2026-09-22 (recorded, not hidden): the first P0 session lost ~1 hour of
> uncommitted work to a sandbox reset. Root cause: work held in the working tree
> without commits. Rule §8.1 below (commit every coherent increment, immediately) is
> the countermeasure.

---

## 1. Files that constitute the recovery system

| Path | Role | Update rule |
|---|---|---|
| `QEVION_SESSION_RECOVERY_PROTOCOL.md` | This procedure (stable) | Only when the procedure changes |
| `QEVION_WORK_STATE.md` | Live work state | Before any risky action and at every checkpoint |
| `recovery/checkpoints/CP-NNNN.md` | One record per checkpoint | Append-only; never rewrite a verified checkpoint |
| `recovery/checkpoints/index.jsonl` | Machine-readable checkpoint index | One line per checkpoint |
| `recovery/snapshots/CP-NNNN.manifest.json` | Sandbox state manifest (tracked files + sha256, versions, services/ports, env var *names*) | `scripts/recovery/snapshot.sh` |
| `recovery/analysis/` | Preserved analysis artifacts (pre-approval inspection, etc.) | Append-only |
| `evidence/` | Evidence pack (INDEX.md committed; heavy artifacts gitignored) | Per phase gate |
| Git tags `cp/CP-NNNN` | Immutable pointer to each verified checkpoint commit | `scripts/recovery/tag_checkpoint.sh` |

## 2. Definition of "complete"

```
Implemented + Validated + Tested + Evidenced + No known critical regression
```
Code that exists but is untested is **unverified**. Documentation is **not** evidence.
Mocks prove contract conformance only — never real behavior.

## 3. Checkpoint discipline

Each checkpoint record MUST contain: Checkpoint ID · timestamp (UTC) · phase · Git SHA ·
completed work (with evidence refs) · verified work (command → result) · unverified work ·
files changed · tests/evidence paths · known failures (classified, 8 classes) · known risks ·
**exact next step** (one executable action).

`scripts/recovery/checkpoint.sh` creates the record + index line; it refuses a dirty tree.

## 4. Resume procedure (any new session) — execute in order

```
 1. cd /home/user/webapp && git status && git log -1 --oneline && git tag --list 'cp/*' | sort -V | tail -3
 2. Read this file
 3. Read QEVION_WORK_STATE.md
 4. Identify "Last verified checkpoint" + Git SHA
 5. Compare HEAD to that SHA:
      HEAD == SHA, tree clean      → clean resume
      HEAD ahead, tree clean       → later commits are UNVERIFIED → re-run their tests
      tree dirty                   → every change is UNVERIFIED → inspect/stash before continuing
      HEAD behind / repo recreated → fetch origin; if work is lost, record the incident in WORK_STATE
 6. scripts/recovery/restore.sh      (deps, dirs, services per latest manifest)
 7. git ls-remote origin main         (connectivity)
 8. If a GitHub credential is provided: apply ONLY via git credential helper into a store
    OUTSIDE the repo (/home/user/.git-credentials, mode 600). Never into tracked files, logs, commits.
 9. scripts/recovery/verify.sh        (fast suite)
10. Resume from "Exact next action" in QEVION_WORK_STATE.md
11. NEVER rebuild work a verified checkpoint already covers
```

## 5. Operator shorthand

`تابع <credential>` means exactly:
```
Restore authentication → Verify repository connectivity → Read recovery state
→ Verify last checkpoint → Continue from the last verified state
```
Never "restart" or "rebuild".

## 6. Credential handling (binding)

- Git credentials: `git credential approve` → `/home/user/.git-credentials` (mode 600) or process env.
- MUST NOT appear in tracked files, commit messages, checkpoint records, manifests, evidence, logs, snapshots.
- Secret scan (`verify.sh` step 1; gitleaks in CI once toolchain lands) before every commit.
- Provider API keys follow the same rule; the UI "test key" is in-memory, TTL-bound, unlogged (spec §39.6).

## 7. Sandbox snapshot rule

After each phase gate: `scripts/recovery/snapshot.sh CP-NNNN` → ONE archive
`qevion_snapshot_CP-NNNN_YYYY-MM-DD.tar.gz` (copied to `/mnt/aidrive/` when mounted; never recursive
copies) + committed manifest. No secrets. The manifest is the source of truth for restoration.

## 8. Main-branch and commit rules

- **8.1 Commit immediately** after every coherent increment (a file, a module, a passing test group).
  Never hold more than ~20 minutes of work uncommitted. Push to `origin main` at least at every checkpoint
  and after any increment that would be expensive to recreate.
- 8.2 No intentionally broken state on main. Partial work lands behind flags or as verified partial increments.
- 8.3 Significant pushes reference a checkpoint ID in the commit message.

## 9. Failure discipline

Classify before fixing (provider limitation · transport limitation · QEVION core bug · adapter bug ·
configuration error · test/environment · external service failure · unknown). Never delete/skip/weaken a
failing test. After two failed attempts: record under Known failures, continue independent work; escalate only
for real business/architecture decisions.

## 10. Recovery drill

At least once per phase perform a cold resume (§4) and record the result in the checkpoint. If the state cannot
be reconstructed from repository + manifest alone, fix the recovery system before further feature work.
