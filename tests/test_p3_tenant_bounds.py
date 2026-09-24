"""OPS 5.5 P3: F-08 tenant-scoped read access to sessions/events; F-12 bounded event log + session pruning."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from qevion.adapters.transports.memory import MemoryTransportSession
from qevion.contracts.common import Channel
from qevion.contracts.event import Event, EventKind
from qevion.main import _seed, build
from qevion.runtime.store import RuntimeStore

ROOT = Path(__file__).resolve().parents[1]
OP = "op-token-for-tests-1234"
TA = "tenant-a-token-123456"


def _ev(tenant: str, seq: int) -> Event:
    return Event(seq=seq, tenant_id=tenant, kind=list(EventKind)[0], type="test.event", source="core")


def test_event_ring_buffer_keeps_absolute_offsets() -> None:
    s = RuntimeStore()
    s.max_events = 5
    for i in range(8):
        s.log_event(_ev("t", i))
    assert len(s.event_log) == 5 and s.event_log_base == 3
    assert [e.seq for e in s.events_since(0, 100)] == [3, 4, 5, 6, 7]
    assert [e.seq for e in s.events_since(6, 100)] == [6, 7]


def test_finished_sessions_are_pruned_live_ones_kept() -> None:
    s = RuntimeStore()
    _seed(s)
    s.max_sessions = 2
    key = next(k for k in s.activities if k.startswith("act_order_intake"))
    lives = []
    for i in range(3):
        lv = s.build_session(
            activity_key=key, transport=MemoryTransportSession(), session_id=f"ses_{i}", channel=Channel.TEXT
        )
        lives.append(lv)
    assert len(s.sessions) == 3  # none finished → nothing evicted
    lives[0].session.record = object()  # type: ignore[assignment]
    s.prune_sessions()
    assert list(s.sessions) == ["ses_1", "ses_2"]


def _client(store: RuntimeStore) -> TestClient:
    return TestClient(build(store, seed_examples=True, web_dist=ROOT / "nonexistent"))


def test_tenant_token_reads_only_own_tenant_and_cannot_write(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QEVION_ADMIN_TOKEN", OP)
    monkeypatch.setenv("QEVION_TENANT_TOKENS", f"t_a:{TA}")
    store = RuntimeStore()
    c = _client(store)
    store.log_event(_ev("t_a", 1))
    store.log_event(_ev("t_b", 2))
    ta: dict[str, Any] = {"Authorization": f"Bearer {TA}"}
    op: dict[str, Any] = {"Authorization": f"Bearer {OP}"}
    mine = c.get("/api/events", params={"limit": 1000}, headers=ta).json()
    assert {e["tenant_id"] for e in mine} == {"t_a"}
    # a tenant cannot widen its scope with ?tenant=
    assert {e["tenant_id"] for e in c.get("/api/events?tenant=t_b", headers=ta).json()} <= {"t_a"}
    allv = {e["tenant_id"] for e in c.get("/api/events", params={"limit": 100000}, headers=op).json()}
    assert {"t_a", "t_b"} <= allv
    assert c.get("/api/sessions", headers=ta).status_code == 200
    assert c.get("/api/activities", headers=ta).status_code == 403
    r = c.post("/api/admin/test-key", json={"provider": "openai", "value": "x" * 20, "ttl_seconds": 60}, headers=ta)
    assert r.status_code == 403
    assert c.get("/api/events", headers={"Authorization": "Bearer wrong-token-xxxxxxxx"}).status_code == 401
