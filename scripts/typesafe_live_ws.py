"""Live WS end-to-end probe for the TypeSafe decision role (rules+typesafe composition).

Runs three sessions against a *running* QEVION server on the mock S2S ``callback`` script:

* affirmative (Egyptian Arabic, not in rules lexicon)  -> expect LLM_VALIDATED -> confirmation granted -> tool executed
* negative   (rules lexicon hit)                        -> expect RULE, no provider call -> confirmation denied
* ambiguous question                                    -> expect UNKNOWN -> neither granted nor denied

The key is taken from ``TYPESAFE_API_KEY`` (env only) and injected through the Admin ephemeral test-key path
(memory only). Nothing secret is written: the report contains a key fingerprint (last 4 chars) only.

Usage:
    TYPESAFE_API_KEY=... .venv/bin/python scripts/typesafe_live_ws.py [out.json] [--base http://localhost:8000]
Exit codes: 0 all expectations met, 1 expectation failed, 2 missing key / server unreachable.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import UTC, datetime
from typing import Any
from urllib import request

import websockets

ACTIVITY = "act_csat_survey@1.0.0"
COMPOSITION = "comp_mock_s2s_typesafe_v1"
SCRIPT = "callback"

PHRASES: list[dict[str, Any]] = [
    {
        "id": "yes_ar_eg",
        "text": "خلاص يا عم اتفقنا كده",
        "expect_source": {"LLM_VALIDATED"},
        "expect_value": True,
        "expect_tool": "tool.confirmation_granted",
        "expect_executed": True,
    },
    {
        "id": "no_ar_eg",
        "text": "لا يا عم بلاش سيبها",
        "expect_source": {"RULE"},
        "expect_value": False,
        "expect_tool": "tool.confirmation_denied",
        "expect_executed": False,
    },
    {
        "id": "ambiguous_ar_eg",
        "text": "هو ده هيكون امتى بالظبط؟",
        "expect_source": {"UNKNOWN"},
        "expect_value": None,
        "expect_tool": None,
        "expect_executed": False,
    },
]


def _fingerprint(key: str) -> str:
    return f"…{key[-4:]}" if len(key) >= 4 else "…"


def _post(base: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
    req = request.Request(
        base + path, data=json.dumps(body).encode(), headers={"content-type": "application/json"}, method="POST"
    )
    with request.urlopen(req, timeout=10) as resp:  # noqa: S310 - local server, operator-run script
        return json.loads(resp.read().decode())


def _get(base: str, path: str) -> dict[str, Any]:
    with request.urlopen(base + path, timeout=10) as resp:  # noqa: S310 - local server
        return json.loads(resp.read().decode())


async def _run_phrase(ws_base: str, phrase: dict[str, Any]) -> dict[str, Any]:
    url = f"{ws_base}/ws/sessions/{ACTIVITY}?channel=text&composition={COMPOSITION}&script={SCRIPT}"
    decisions: list[dict[str, Any]] = []
    tool_events: list[str] = []
    outcome: str | None = None
    session_id: str | None = None
    t0 = time.monotonic()

    async def drain(ws: Any, until_types: set[str], timeout: float) -> None:
        nonlocal outcome, session_id
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=max(0.05, deadline - time.monotonic()))
            except TimeoutError:
                return
            msg = json.loads(raw)
            mtype = msg.get("type")
            session_id = session_id or msg.get("session_id")
            if mtype == "event":
                env = msg.get("payload") or {}
                et = env.get("type")
                payload = env.get("payload") or {}
                if et == "decision.made":
                    decisions.append(
                        {
                            "ts_ms": int((time.monotonic() - t0) * 1000),
                            "kind": payload.get("kind"),
                            "source": payload.get("source"),
                            "value": payload.get("value"),
                            "confidence": payload.get("confidence"),
                        }
                    )
                if et and et.startswith("tool."):
                    tool_events.append(et)
                if et == "outcome.produced":
                    outcome = payload.get("primary")
                if et in until_types:
                    return

    async with websockets.connect(url, open_timeout=10) as ws:
        await ws.send(json.dumps({"type": "hello"}))
        await drain(ws, {"session.started"}, 3.0)
        await ws.send(json.dumps({"type": "text", "text": "أهلا"}))  # consumes opening step
        await drain(ws, set(), 1.5)
        await ws.send(json.dumps({"type": "text", "text": "call me tomorrow"}))  # tool step -> confirmation request
        await drain(ws, {"tool.confirmation_requested"}, 4.0)
        await ws.send(json.dumps({"type": "text", "text": phrase["text"]}))
        await drain(ws, {"tool.execution_completed", "tool.confirmation_denied"}, 6.0)
        await ws.send(json.dumps({"type": "bye"}))
        await drain(ws, {"outcome.produced"}, 3.0)

    conf = [d for d in decisions if d["kind"] == "interpret_confirmation"]
    last = conf[-1] if conf else None
    ok_source = last is not None and last["source"] in phrase["expect_source"]
    ok_value = last is not None and last["value"] == phrase["expect_value"]
    ok_tool = (phrase["expect_tool"] in tool_events) if phrase["expect_tool"] else (
        "tool.confirmation_granted" not in tool_events and "tool.confirmation_denied" not in tool_events
    )
    executed = "tool.execution_completed" in tool_events
    ok_exec = executed == phrase["expect_executed"]
    return {
        "id": phrase["id"],
        "text": phrase["text"],
        "session_id": session_id,
        "confirmation_decision": last,
        "tool_events": tool_events,
        "outcome": outcome,
        "checks": {"source": ok_source, "value": ok_value, "tool_event": ok_tool, "executed": ok_exec},
        "passed": ok_source and ok_value and ok_tool and ok_exec,
    }


async def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    base = "http://localhost:8000"
    if "--base" in sys.argv:
        base = sys.argv[sys.argv.index("--base") + 1]
    key = os.environ.get("TYPESAFE_API_KEY", "")
    if not key:
        print("TYPESAFE_API_KEY not set", file=sys.stderr)
        return 2
    try:
        _post(base, "/api/admin/test-key", {"provider": "typesafe", "value": key, "ttl_seconds": 600})
        cred = _get(base, "/api/admin/credentials/typesafe")
    except Exception as exc:  # noqa: BLE001
        print(f"server unreachable: {exc}", file=sys.stderr)
        return 2
    ws_base = base.replace("http://", "ws://").replace("https://", "wss://")
    results = [await _run_phrase(ws_base, p) for p in PHRASES]
    report = {
        "kind": "typesafe-live-ws-e2e",
        "produced_at": datetime.now(UTC).isoformat(),
        "base": base,
        "activity": ACTIVITY,
        "composition": COMPOSITION,
        "script": SCRIPT,
        "key_fingerprint": _fingerprint(key),
        "credential_source": cred.get("source"),
        "phrases": results,
        "summary": {
            "passed": all(r["passed"] for r in results),
            "n": len(results),
            "n_passed": sum(1 for r in results if r["passed"]),
        },
    }
    out = json.dumps(report, ensure_ascii=False, indent=1)
    if args:
        with open(args[0], "w", encoding="utf-8") as fh:
            fh.write(out + "\n")
    print(out)
    return 0 if report["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
