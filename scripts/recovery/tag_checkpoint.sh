#!/usr/bin/env bash
# Tag HEAD as the verified commit of a checkpoint (run AFTER committing the record).
set -euo pipefail
ID="${1:?checkpoint id}"
git tag -f "cp/${ID}" HEAD
if git push -f -q origin "cp/${ID}" 2>/dev/null; then echo "tag cp/${ID} -> $(git rev-parse --short HEAD) pushed"; else echo "tag cp/${ID} local only (push failed)"; fi
