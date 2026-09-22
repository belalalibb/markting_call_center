#!/usr/bin/env bash
# One snapshot archive + committed manifest for a checkpoint. No secrets.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$ROOT"
ID="${1:?checkpoint id}"; DATE="$(date -u +%Y-%m-%d)"
OUT="/tmp/qevion_snapshot_${ID}_${DATE}.tar.gz"
tar --exclude='.git' --exclude='node_modules' --exclude='.venv' --exclude='__pycache__' \
    --exclude='evidence/artifacts' --exclude='*.wav' -czf "$OUT" .
SHA256="$(sha256sum "$OUT" | cut -d' ' -f1)"
python3 - "$ID" "$OUT" "$SHA256" <<'PY'
import hashlib, json, os, subprocess, sys, datetime
cid, out, sha = sys.argv[1:4]
files = {}
for p in subprocess.check_output(["git","ls-files"], text=True).splitlines():
    if os.path.isfile(p):
        with open(p,"rb") as f: files[p] = hashlib.sha256(f.read()).hexdigest()
services = []
if os.path.exists("recovery/services.json"):
    services = json.load(open("recovery/services.json"))
manifest = {
  "checkpoint": cid,
  "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
  "git_sha": subprocess.check_output(["git","rev-parse","HEAD"], text=True).strip(),
  "archive": os.path.basename(out), "archive_sha256": sha,
  "python": subprocess.check_output(["python3","--version"], text=True).strip(),
  "node": subprocess.run(["node","--version"], capture_output=True, text=True).stdout.strip(),
  "tracked_file_count": len(files), "tracked_files_sha256": files,
  "required_env_var_names": sorted(k for k in os.environ if k.startswith("QEVION_")),  # names only
  "services": services,
}
os.makedirs("recovery/snapshots", exist_ok=True)
json.dump(manifest, open(f"recovery/snapshots/{cid}.manifest.json","w"), indent=2, ensure_ascii=False)
print(f"manifest -> recovery/snapshots/{cid}.manifest.json ({len(files)} tracked files)")
PY
if [[ -d /mnt/aidrive ]]; then cp "$OUT" /mnt/aidrive/ && echo "copied -> /mnt/aidrive/$(basename "$OUT")"; else echo "aidrive not mounted; archive at $OUT"; fi
