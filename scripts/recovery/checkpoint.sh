#!/usr/bin/env bash
# Create a checkpoint record + index line for the CURRENT HEAD. Refuses a dirty tree.
# Usage: scripts/recovery/checkpoint.sh CP-0001 "P0" "short title"
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$ROOT"
ID="${1:?checkpoint id}"; PHASE="${2:?phase}"; TITLE="${3:?title}"
[[ -z "$(git status --porcelain)" ]] || { echo "ERROR: working tree dirty; commit first" >&2; exit 2; }
SHA="$(git rev-parse HEAD)"; TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
REC="recovery/checkpoints/${ID}.md"
mkdir -p recovery/checkpoints
[[ ! -e "$REC" ]] || { echo "ERROR: $REC exists (append-only)" >&2; exit 3; }
PREV="$(git tag --list 'cp/*' | sort -V | tail -1)"; BASE="${PREV:-$(git rev-list --max-parents=0 HEAD)}"
cat > "$REC" <<MD
# ${ID} — ${TITLE}

| Field | Value |
|---|---|
| Checkpoint ID | ${ID} |
| Timestamp (UTC) | ${TS} |
| Phase | ${PHASE} |
| Git SHA (state described) | ${SHA} |
| Status | VERIFIED |

## Completed work
- (fill)

## Verified work (command → result)
- (fill)

## Unverified work
- none

## Files changed since ${BASE:0:12}
\`\`\`
$(git diff --stat "$BASE"..HEAD | tail -40)
\`\`\`

## Tests / evidence
- (paths)

## Known failures (classified)
- none

## Known risks
- (fill)

## Exact next step
- (one action)
MD
printf '{"id":"%s","ts":"%s","phase":"%s","git_sha":"%s","title":"%s","status":"VERIFIED"}\n' "$ID" "$TS" "$PHASE" "$SHA" "$TITLE" >> recovery/checkpoints/index.jsonl
echo "Created $REC — edit, commit, then scripts/recovery/tag_checkpoint.sh $ID"
