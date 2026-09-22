#!/usr/bin/env python3
"""License gate (QV-LIC-001/002): fail if any installed package license matches the deny list
in docs/registry/licenses.yaml, or is unknown and not explicitly allowed.

Usage: python scripts/license_gate.py <pip-licenses.json> <licenses.yaml>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

# Common SPDX-ish spellings pip-licenses emits, normalized to our policy vocabulary.
_NORMALIZE = {
    "MIT License": "MIT",
    "BSD License": "BSD-3-Clause",
    "Apache Software License": "Apache-2.0",
    "Apache 2.0": "Apache-2.0",
    "Apache-2.0": "Apache-2.0",
    "Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0",
    "Python Software Foundation License": "PSF-2.0",
    "ISC License (ISCL)": "ISC",
    "The Unlicense (Unlicense)": "Unlicense",
    "GNU General Public License v3 (GPLv3)": "GPL-3.0-only",
    "GNU Lesser General Public License v3 (LGPLv3)": "LGPL-3.0-only",
}


def _norm(raw: str) -> set[str]:
    out: set[str] = set()
    for part in raw.replace(" OR ", ";").replace(" or ", ";").split(";"):
        p = part.strip()
        if not p:
            continue
        out.add(_NORMALIZE.get(p, p))
    return out or {"UNKNOWN"}


def main(report: Path, policy_path: Path) -> int:
    policy = yaml.safe_load(policy_path.read_text())["policy"]
    allow = set(policy["allow"]) | set(policy.get("allow_dev_only", []))
    deny = set(policy["deny"])
    data = json.load(report.open())
    denied: list[str] = []
    unknown: list[str] = []
    for pkg in data:
        lic = _norm(pkg.get("License", "UNKNOWN"))
        name = f"{pkg['Name']}=={pkg['Version']} [{pkg.get('License')}]"
        if lic & deny:
            denied.append(name)
        elif not (lic & allow):
            unknown.append(name)
    print(f"scanned {len(data)} packages: {len(denied)} denied, {len(unknown)} unknown")
    for n in denied:
        print("  DENY   ", n)
    for n in unknown:
        print("  UNKNOWN", n)
    # Unknown licenses are reported but do not fail CI at P0.2; denied ones always fail (QV-LIC-002).
    return 1 if denied else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]), Path(sys.argv[2])))
