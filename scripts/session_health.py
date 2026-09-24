"""Shared session-health verdict for live smokes (F-11, OPS 5.5 audit).

The CP-0012 browser smoke passed 10/10 while the same session contained OpenAI protocol errors, illegal dialog
transitions and a `technical_failure` outcome. Every live smoke now also asserts the *Core's* view of the session
from the global event log: no provider errors, no illegal transitions, no BLOCKED activity, outcome is not
technical_failure, and (for S2S) the first thing the adapter did was configure the provider.
"""

from __future__ import annotations

import json
from typing import Any
from urllib import request


def fetch_events(base: str, session_id: str, headers: dict[str, str] | None = None) -> list[dict[str, Any]]:
    req = request.Request(base.rstrip("/") + f"/api/events?session_id={session_id}&limit=100000", headers=headers or {})
    with request.urlopen(req, timeout=15) as r:  # noqa: S310 - operator-run against own server
        evs = json.loads(r.read().decode())
    return [e for e in evs if e.get("session_id") == session_id]


def verdict(events: list[dict[str, Any]], *, fatal_only: bool = False) -> dict[str, Any]:
    types = [e["type"] for e in events]
    perrs = [e["payload"] for e in events if e["type"] == "provider.error"]
    if fatal_only:
        perrs = [p for p in perrs if p.get("fatal", True)]
    illegal = [
        e["payload"]
        for e in events
        if e["type"] == "failure.classified" and e["payload"].get("class") == "illegal_dialog_transition"
    ]
    blocked = [
        e
        for e in events
        if e["type"] == "state.changed"
        and e["payload"].get("machine") == "activity"
        and e["payload"].get("to") == "BLOCKED"
    ]
    outcome = next((e["payload"].get("primary") for e in reversed(events) if e["type"] == "outcome.produced"), None)
    checks = {
        "no_provider_error": not perrs,
        "no_illegal_dialog_transition": not illegal,
        "activity_never_blocked": not blocked,
        "outcome_not_technical_failure": outcome != "technical_failure",
        "session_started": "session.started" in types,
    }
    return {
        "checks": checks,
        "passed": all(checks.values()),
        "outcome": outcome,
        "provider_errors": [{k: p.get(k) for k in ("code", "provider_code", "fatal", "message")} for p in perrs][:5],
        "illegal_transitions": illegal[:5],
        "event_count": len(events),
    }


__all__ = ["fetch_events", "verdict"]
