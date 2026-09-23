"""Render a voice_trace_live.py report as a compact chronological text trace (for evidence/review)."""

from __future__ import annotations

import json
import sys

r = json.load(open(sys.argv[1]))
skip = {"latency.sample", "turn.started"}
rows = []
for t, ty, turn, p in r["core_events"]:
    if ty in skip:
        continue
    if ty == "state.changed":
        s = f"{p.get('machine')}:{p.get('from')}->{p.get('to')} [{p.get('trigger')}]"
    else:
        s = json.dumps({k: v for k, v in p.items() if k != "instructions_fp"}, ensure_ascii=False)[:120]
    rows.append(f"{t:>6} {ty:<32} {(turn or '')[-6:]:<6} {s}")
out = "\n".join(rows)
if len(sys.argv) > 2:
    open(sys.argv[2], "w").write(out + "\n")
print(len(rows), "rows")
