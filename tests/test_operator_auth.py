"""F-07 regression (OPS 5.5 audit): operator-token guard + CORS allow-list.

Audit reproduction: unauthenticated `POST /api/admin/test-key` replaced the live provider key, `DELETE` cleared
it, and every response carried `Access-Control-Allow-Origin: *`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from qevion.main import build
from qevion.runtime.store import RuntimeStore
from starlette.websockets import WebSocketDisconnect

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "op-token-for-tests-1234"


def _client() -> TestClient:
    return TestClient(build(RuntimeStore(), seed_examples=True, web_dist=ROOT / "nonexistent"))


def test_token_unset_is_dev_mode_and_reports_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QEVION_ADMIN_TOKEN", raising=False)
    c = _client()
    assert c.get("/api/health").json()["auth"] == "disabled"
    assert c.get("/api/auth/status").json() == {"auth": "disabled", "authorized": True}
    assert c.get("/api/sessions").status_code == 200


def test_admin_key_hijack_is_refused_without_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QEVION_ADMIN_TOKEN", TOKEN)
    c = _client()
    r = c.post("/api/admin/test-key", json={"provider": "openai", "value": "ATTACKER-9999", "ttl_seconds": 60})
    assert r.status_code == 401
    assert c.delete("/api/admin/test-key").status_code == 401
    for path in ("/api/events", "/api/sessions", "/api/activities", "/api/compositions", "/api/admin/credentials/openai"):
        assert c.get(path).status_code == 401, path
    # open: health, auth status (so the UI can render the login prompt)
    assert c.get("/api/health").status_code == 200
    assert c.get("/api/auth/status").json() == {"auth": "enabled", "authorized": False}


def test_bearer_header_and_cookie_login_grant_access(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QEVION_ADMIN_TOKEN", TOKEN)
    c = _client()
    assert c.get("/api/sessions", headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 200
    assert c.get("/api/sessions", headers={"X-QEVION-Token": TOKEN}).status_code == 200
    assert c.get("/api/sessions", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert c.post("/api/auth/login", json={"token": "wrong"}).status_code == 401
    r = c.post("/api/auth/login", json={"token": TOKEN})
    assert r.status_code == 200 and "qevion_session" in r.cookies
    assert TOKEN not in r.headers.get("set-cookie", "")  # cookie carries an HMAC, never the token
    assert c.get("/api/sessions").status_code == 200  # cookie now sent by the client
    assert c.get("/api/auth/status").json()["authorized"] is True
    c.post("/api/auth/logout")
    c.cookies.clear()
    assert c.get("/api/sessions").status_code == 401


def test_websocket_requires_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QEVION_ADMIN_TOKEN", TOKEN)
    c = _client()
    with pytest.raises(WebSocketDisconnect) as ei, c.websocket_connect("/ws/sessions/act_order_intake@1.0.0"):
        pass
    assert ei.value.code == 4401
    with c.websocket_connect(
        "/ws/sessions/act_order_intake@1.0.0?channel=text", headers={"Authorization": f"Bearer {TOKEN}"}
    ) as ws:
        assert ws.receive_json()["schema"] == "qevion.transport.v1"
        ws.send_json({"type": "bye"})


def test_cors_foreign_origin_not_allowed_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QEVION_CORS_ORIGINS", raising=False)
    monkeypatch.delenv("QEVION_ADMIN_TOKEN", raising=False)
    c = _client()
    r = c.get("/api/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in {k.lower() for k in r.headers}


def test_cors_allow_list_is_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QEVION_CORS_ORIGINS", "https://console.example.com, *")
    monkeypatch.delenv("QEVION_ADMIN_TOKEN", raising=False)
    c = _client()
    ok = c.get("/api/health", headers={"Origin": "https://console.example.com"})
    assert ok.headers.get("access-control-allow-origin") == "https://console.example.com"
    bad = c.get("/api/health", headers={"Origin": "https://evil.example"})
    assert bad.headers.get("access-control-allow-origin") is None  # "*" in the env list is ignored on purpose
