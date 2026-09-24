"""OPS 5.5 P4 / F-14: compositions tell the UI what is simulated and what lacks a key; Admin only offers vendors
that a registered adapter consumes."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from qevion.main import build
from qevion.runtime.store import RuntimeStore

ROOT = Path(__file__).resolve().parents[1]


def _client() -> TestClient:
    return TestClient(build(RuntimeStore(), seed_examples=True, web_dist=ROOT / "nonexistent"))


def test_compositions_flag_simulated_and_missing_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("QEVION_ADMIN_TOKEN", raising=False)
    comps = {c["composition_id"]: c for c in _client().get("/api/compositions").json()}
    mock = comps["comp_mock_s2s_v1"]
    assert mock["simulated"] is True and mock["needs_credential"] is False and mock["ready"] is True
    real = comps["comp_s2s_openai_v1"]
    assert real["simulated"] is False and real["needs_credential"] is True and real["ready"] is False


def test_admin_vendor_list_has_no_dead_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QEVION_ADMIN_TOKEN", raising=False)
    vendors = _client().get("/api/credential-vendors").json()
    assert "openai" in vendors and "typesafe" in vendors
    assert not {"deepgram", "elevenlabs", "mock"} & set(vendors)
