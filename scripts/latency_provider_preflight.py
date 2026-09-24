"""No-credit rule guard: open one Realtime session and send session.update. Exit 0 only if the provider accepts it.
Any refusal (insufficient_quota, auth, rate limit) → exit 1 and an INVALID record. Never performance evidence.

usage: OPENAI_API_KEY=… latency_provider_preflight.py OUT.json
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import sys
import time

import websockets


async def main() -> int:
    out = pathlib.Path(sys.argv[1])
    rec: dict[str, object] = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "valid": False}
    try:
        async with websockets.connect(
            "wss://api.openai.com/v1/realtime?model=gpt-realtime",
            additional_headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
            open_timeout=15,
        ) as ws:
            await ws.send(json.dumps({"type": "session.update", "session": {"type": "realtime"}}))
            for _ in range(10):
                m = json.loads(await asyncio.wait_for(ws.recv(), 10))
                if m["type"] == "session.updated":
                    rec["valid"] = True
                    break
                if m["type"] == "error":
                    rec["error"] = m.get("error", {}).get("code") or m.get("error", {}).get("type")
                    break
    except websockets.exceptions.ConnectionClosed as e:
        rec["error"] = f"closed {e.rcvd.code if e.rcvd else None}: {e.rcvd.reason if e.rcvd else ''}"
    except Exception as e:  # noqa: BLE001
        rec["error"] = f"{type(e).__name__}: {e}"
    out.write_text(json.dumps(rec, indent=1))
    print(json.dumps(rec))
    return 0 if rec["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
