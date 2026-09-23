"""F-07/F-08 live security probe against a running server (OPS 5.5 audit reproduction, now a regression check).

usage: QEVION_ADMIN_TOKEN=… security_probe.py OUT.json [--base URL]
Replays the audit's attacks without the token (key hijack / delete, event log, sessions, WS, foreign-origin CORS)
and confirms the same calls succeed with the token. Writes no secrets (token never echoed).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

import websockets

BASE = sys.argv[sys.argv.index("--base") + 1] if "--base" in sys.argv else "http://localhost:8000"
TOKEN = os.environ.get("QEVION_ADMIN_TOKEN", "")


def call(method: str, path: str, body: Any = None, headers: dict[str, str] | None = None) -> tuple[int, dict[str, str]]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE + path, data=data, method=method, headers={"content-type": "application/json", **(headers or {})}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:  # noqa: S310
            return r.status, {k.lower(): v for k, v in r.headers.items()}
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in e.headers.items()}


async def ws_code(headers: dict[str, str] | None) -> int | None:
    url = BASE.replace("http", "ws", 1) + "/ws/sessions/act_order_intake@1.0.0?channel=text"
    try:
        async with websockets.connect(url, additional_headers=headers or {}) as ws:
            await ws.send(json.dumps({"type": "hello"}))
            try:
                await asyncio.wait_for(ws.recv(), 3)
            except Exception:  # noqa: BLE001
                pass
            await ws.send(json.dumps({"type": "bye"}))
            await asyncio.sleep(0.3)
            return ws.close_code or 0
    except websockets.exceptions.ConnectionClosed as e:
        return e.rcvd.code if e.rcvd else None
    except websockets.exceptions.InvalidStatus as e:
        return e.response.status_code


def main() -> int:
    auth = {"Authorization": f"Bearer {TOKEN}"}
    res: dict[str, Any] = {"base": BASE, "token_configured": bool(TOKEN)}
    res["no_token"] = {
        "POST /api/admin/test-key": call(
            "POST", "/api/admin/test-key", {"provider": "openai", "value": "ATTACKER-9999"}
        )[0],
        "DELETE /api/admin/test-key": call("DELETE", "/api/admin/test-key")[0],
        "GET /api/events": call("GET", "/api/events")[0],
        "GET /api/sessions": call("GET", "/api/sessions")[0],
        "GET /api/admin/credentials/openai": call("GET", "/api/admin/credentials/openai")[0],
        "WS /ws/sessions": asyncio.run(ws_code(None)),
        "GET /api/health": call("GET", "/api/health")[0],
    }
    res["with_token"] = {
        "GET /api/sessions": call("GET", "/api/sessions", headers=auth)[0],
        "GET /api/admin/credentials/openai": call("GET", "/api/admin/credentials/openai", headers=auth)[0],
        "WS /ws/sessions": asyncio.run(ws_code(auth)),
    }
    _, h = call("GET", "/api/health", headers={"Origin": "https://evil.example"})
    res["cors_foreign_origin_allowed"] = h.get("access-control-allow-origin")
    nt, wt = res["no_token"], res["with_token"]
    res["checks"] = {
        "admin_write_refused": nt["POST /api/admin/test-key"] == 401 and nt["DELETE /api/admin/test-key"] == 401,
        "reads_refused": all(
            nt[k] == 401 for k in ("GET /api/events", "GET /api/sessions", "GET /api/admin/credentials/openai")
        ),
        "ws_refused": nt["WS /ws/sessions"] in (4401, 403),  # uvicorn maps a pre-accept close to HTTP 403
        "health_open": nt["GET /api/health"] == 200,
        "token_grants_access": wt["GET /api/sessions"] == 200
        and wt["GET /api/admin/credentials/openai"] == 200
        and wt["WS /ws/sessions"] in (1000, 0),
        "cors_not_wildcard": res["cors_foreign_origin_allowed"] in (None, ""),
    }
    res["passed"] = all(res["checks"].values())
    text = json.dumps(res, indent=1)
    if len(sys.argv) > 1 and sys.argv[1].endswith(".json"):
        open(sys.argv[1], "w").write(text + "\n")
    print(text)
    return 0 if res["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
