"""P3 — runtime REST + WS + copilot HTTP surface (composition root `qevion.main`)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient
from qevion.main import build
from qevion.runtime.store import RuntimeStore

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def client() -> TestClient:
    return TestClient(build(RuntimeStore(), seed_examples=True, web_dist=ROOT / "nonexistent"))


def _load_example(name: str) -> dict[str, Any]:
    """YAML → JSON-safe dict (yaml parses timestamps into datetime, which `json=` cannot send)."""
    raw = yaml.safe_load((ROOT / "config/examples" / f"{name}.yaml").read_text())
    return json.loads(json.dumps(raw, default=str))


def _key(client: TestClient, activity_id: str) -> str:
    return next(a["key"] for a in client.get("/api/activities").json() if a["activity_id"] == activity_id)


# --------------------------------------------------------------------- basics


def test_health_and_seed(client: TestClient) -> None:
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and h["activities"] == 3 and h["composition"] == "comp_mock_s2s_v1"
    assert {a["readiness"] for a in client.get("/api/activities").json()} == {"DRAFT"}
    assert client.get("/api/registry").json()["schema"] == "qevion.capability_registry.v1"


def test_tenant_crud_and_validation(client: TestClient) -> None:
    r = client.post("/api/tenants", json={"tenant_id": "t2", "name": "Two"})
    assert r.status_code == 201 and r.json()["schema"] == "qevion.tenant.v1"
    assert client.post("/api/tenants", json={"name": "no id"}).status_code == 422
    assert any(t["tenant_id"] == "t2" for t in client.get("/api/tenants").json())


def test_activity_upload_yaml_and_json(client: TestClient) -> None:
    body = _load_example("activity_a_restaurant")
    body["identity"]["version"] = "1.1.0"
    r = client.post("/api/activities", json=body)
    assert r.status_code == 201 and r.json()["key"].endswith("@1.1.0")
    body["identity"]["version"] = "1.2.0"
    r = client.post("/api/activities/yaml", files={"file": ("a.yaml", yaml.safe_dump(body), "application/x-yaml")})
    assert r.status_code == 201 and r.json()["version"] == "1.2.0"
    bad = client.post("/api/activities", json={"identity": {"tenant_id": "t"}})
    assert bad.status_code == 422 and any("objective" in e for e in bad.json()["detail"])
    assert client.get("/api/activities/nope@0.0.0").status_code == 404
    detail = client.get(f"/api/activities/{r.json()['key']}").json()
    assert detail["blueprint"]["schema"] == "qevion.activity.v1" and detail["history"] == []


# --------------------------------------------------------------- control plane


def test_preflight_capabilities_and_readiness_flow(client: TestClient) -> None:
    key = _key(client, "act_csat_survey")
    r = client.post(f"/api/activities/{key}/preflight").json()
    assert r["result"]["schema"] == "qevion.preflight.v1"
    assert r["readiness"] in {"READY_FOR_SIMULATION", "NEEDS_INFORMATION", "BLOCKED", "NEEDS_CONFIGURATION"}
    if r["result"]["status"] == "READY":
        assert r["readiness"] == "READY_FOR_SIMULATION"
    else:
        assert all("fix_hint" in f and f["path"] for f in r["result"]["findings"])
    caps = client.post(f"/api/activities/{key}/capabilities").json()
    assert caps["rows"] and all({"requirement", "required_capability", "action"} <= set(row) for row in caps["rows"])
    # illegal transition is rejected with 409 and legal history is recorded
    assert client.post(f"/api/activities/{key}/transition", json={"to": "ACTIVE"}).status_code == 409
    hist = client.get(f"/api/activities/{key}").json()["history"]
    assert hist and hist[-1]["to"] == r["readiness"]


def test_transition_endpoint_legal_path(client: TestClient) -> None:
    key = _key(client, "act_order_intake")
    r = client.post(f"/api/activities/{key}/transition", json={"to": "DISCOVERY_IN_PROGRESS", "reason": "start"})
    assert r.status_code == 200 and r.json()["readiness"] == "DISCOVERY_IN_PROGRESS"
    assert r.json()["change"]["from"] == "DRAFT"


# ------------------------------------------------------------------ knowledge


def test_knowledge_upload_report_and_conflict_resolution(client: TestClient) -> None:
    key = _key(client, "act_order_intake")
    csv1 = "item_id,name,price\nm1,Koshari,45\nm2,Molokhia,60\n"
    csv2 = "item_id,name,price\nm1,Koshari,50\n"
    r1 = client.post(
        "/api/knowledge/upload",
        data={"tenant_id": "t_demo", "activity_key": key, "priority": "10"},
        files={"file": ("menu_v1.csv", csv1, "text/csv")},
    )
    assert r1.status_code == 201, r1.text
    rep = r1.json()
    assert rep["summary"]["entities"] == 2 and rep["summary"]["facts"] >= 4
    assert rep["source"]["kind"] == "structured"
    r2 = client.post(
        "/api/knowledge/upload",
        data={"tenant_id": "t_demo", "activity_key": key, "priority": "10"},
        files={"file": ("menu_v2.csv", csv2, "text/csv")},
    )
    assert r2.status_code == 201
    conflicts = client.get("/api/knowledge/t_demo/conflicts").json()
    assert len(conflicts) >= 1 and conflicts[0]["resolution"] == "pending"
    cid, winner = conflicts[0]["contradiction_id"], conflicts[0]["fact_ids"][0]
    res = client.post(f"/api/knowledge/contradictions/{cid}/resolve", params={"winner": winner, "by": "op"}).json()
    assert res["resolution"] == "operator_decided" and res["winning_fact_id"] == winner
    assert client.get("/api/knowledge/t_demo/conflicts").json() == []
    assert client.get(f"/api/knowledge/reports/{rep['source']['source_id']}").json()["summary"] == rep["summary"]
    assert client.get("/api/knowledge/reports/nope").status_code == 404
    approved = client.get("/api/knowledge/t_demo/facts").json()
    assert approved and all(f["status"] == "APPROVED" for f in approved)


def test_knowledge_upload_rejects_oversize(client: TestClient) -> None:
    big = b"a" * (5 * 1024 * 1024 + 1)
    r = client.post("/api/knowledge/upload", data={"tenant_id": "t"}, files={"file": ("x.txt", big, "text/plain")})
    assert r.status_code == 422


# ---------------------------------------------------------------------- admin


def test_ephemeral_test_key_never_echoed(client: TestClient) -> None:
    secret = "EPHEMERAL_TEST_VALUE_ABCDEFGHIJKLMNOP"  # deliberately not key-shaped: verify.sh scans tracked files
    r = client.post("/api/admin/test-key", json={"provider": "testprov", "value": secret, "ttl_seconds": 60})
    assert r.status_code == 200
    body = r.text
    assert secret not in body and r.json()["source"] == "ephemeral_ui"
    st = client.get("/api/admin/credentials/testprov").json()
    assert st["source"] == "ephemeral_ui" and secret not in json.dumps(st)
    assert client.delete("/api/admin/test-key", params={"provider": "testprov"}).json()["cleared"] == 1
    assert client.get("/api/admin/credentials/testprov").json()["source"] != "ephemeral_ui"


# ---------------------------------------------------------------------- copilot


def _start(client: TestClient, **kw: Any) -> dict[str, Any]:
    body = {"tenant_id": "t_demo", "activity_id": "act_new", "name": "New", **kw}
    r = client.post("/api/copilot/sessions", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_copilot_session_loop_over_http(client: TestClient) -> None:
    v = _start(client)
    sid = v["config_session_id"]
    assert v["status"] == "asking" and not v["draft_valid"] and v["questions"] and v["blocking_total"] > 0
    assert "# Proposal" in v["explanation"] and all(
        q["question_id"] in v["question_explanations"] for q in v["questions"]
    )
    q = v["questions"][0]
    v2 = client.post(
        f"/api/copilot/sessions/{sid}/answer",
        json={"question_id": q["question_id"], "value": ["text"] if q["target_path"] == "channels" else "faq_v1"},
    ).json()
    assert q["question_id"] not in {x["question_id"] for x in v2["questions"]}
    assert v2["blocking_total"] == v["blocking_total"] - 1
    # bad ids / illegal defer
    assert (
        client.post(f"/api/copilot/sessions/{sid}/answer", json={"question_id": "q_x", "value": 1}).status_code == 404
    )
    blocking = next(x for x in v2["questions"] if x["blocking"])
    assert (
        client.post(
            f"/api/copilot/sessions/{sid}/answer", json={"question_id": blocking["question_id"], "mode": "defer"}
        ).status_code
        == 409
    )
    assert client.get("/api/copilot/sessions/nope").status_code == 404
    assert client.post(f"/api/copilot/sessions/{sid}/publish").status_code == 409
    assert any(s["config_session_id"] == sid for s in client.get("/api/copilot/sessions").json())


def test_copilot_seeded_from_example_publishes_activity(client: TestClient) -> None:
    seed = _load_example("activity_a_restaurant")
    seed["identity"]["version"] = "2.0.0"
    v = _start(client, activity_id=seed["identity"]["activity_id"], seed=seed, operator_id="op_1")
    assert v["draft_valid"], v["validation_errors"]
    assert v["blocking_total"] == 0 and v["status"] in {"review", "blocked"}
    assert v["unapproved"] == []
    sid = v["config_session_id"]
    pub = client.post(f"/api/copilot/sessions/{sid}/publish")
    assert pub.status_code == 200, pub.text
    key = pub.json()["activity_key"]
    assert key.endswith("@2.0.0")
    detail = client.get(f"/api/activities/{key}").json()
    assert detail["blueprint"]["version_metadata"]["decisions"]  # decisions travelled with the blueprint
    evs = client.get("/api/events", params={"limit": 500}).json()
    kinds = {e["type"] for e in evs}
    assert "config.session_started" in kinds
    assert all(e["source"] == "copilot" for e in evs if e["type"].startswith("config."))


def test_copilot_seeded_partial_knowledge_asks_blocking_question(client: TestClient) -> None:
    """Activity B declares a PARTIAL knowledge requirement → mapping REQUIRES_KNOWLEDGE → blocking upload question."""
    seed = _load_example("activity_b_clinic")
    v = _start(client, activity_id=seed["identity"]["activity_id"], seed=seed, operator_id="op_1")
    assert v["draft_valid"] and v["status"] == "asking"
    blocking = [q for q in v["questions"] if q["blocking"]]
    assert blocking and blocking[0]["target_path"] == "capabilities.knowledge:visit_preparation"
    assert blocking[0]["answer_type"] == "upload"
    assert any(c["action"] == "REQUIRES_KNOWLEDGE" for c in v["capability_requirements"])
    r = client.post(f"/api/copilot/sessions/{v['config_session_id']}/publish")
    assert r.status_code == 409 and r.json()["detail"]["reason"] == "blocking_questions_open"


# ------------------------------------------------------------------------- WS


def test_ws_session_text_roundtrip(client: TestClient) -> None:
    key = _key(client, "act_csat_survey")
    with client.websocket_connect(f"/ws/sessions/{key}?channel=text") as ws:
        first = json.loads(ws.receive_text())
        assert first["schema"] == "qevion.transport.v1" and first["type"] in {"ready", "state", "event"}
        ws.send_text(json.dumps({"type": "text", "text": "hello"}))
        got_types: set[str] = set()
        for _ in range(30):
            m = ws.receive()
            if "text" in m and m["text"]:
                got_types.add(json.loads(m["text"])["type"])
            elif "bytes" in m and m["bytes"]:
                got_types.add("<audio>")
            if "audio_end" in got_types or "transcript" in got_types:
                break
        assert got_types & {"audio_start", "transcript", "state", "event", "<audio>"}, got_types
        ws.send_text(json.dumps({"type": "bye"}))
    sessions = client.get("/api/sessions").json()
    assert len(sessions) == 1
    s = sessions[0]
    assert s["running"] is False and s["events"] > 0
    detail = client.get(f"/api/sessions/{s['session_id']}").json()
    assert detail["events"] and all(e["schema"] == "qevion.event.v1" for e in detail["events"])
    assert [e["seq"] for e in detail["events"]] == sorted(e["seq"] for e in detail["events"])
    assert client.get("/api/health").json()["sessions_live"] == 0


def test_ws_unknown_activity_closes(client: TestClient) -> None:
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect) as ei, client.websocket_connect("/ws/sessions/nope@0") as ws:
        ws.receive_text()
    assert ei.value.code == 4404


def test_ws_invalid_client_message_reports_error(client: TestClient) -> None:
    key = _key(client, "act_csat_survey")
    with client.websocket_connect(f"/ws/sessions/{key}") as ws:
        ws.receive_text()
        ws.send_text("{not json")
        for _ in range(20):
            m = ws.receive()
            if m.get("text") and json.loads(m["text"])["type"] == "error":
                break
        else:
            raise AssertionError("no error message")
        ws.send_text(json.dumps({"type": "bye"}))


# ------------------------------------------------------------- compositions (P4)


def test_compositions_listed_with_credential_source(client: TestClient) -> None:
    comps = {c["composition_id"]: c for c in client.get("/api/compositions").json()}
    assert comps["comp_mock_s2s_v1"]["default"] is True
    assert comps["comp_s2s_openai_v1"]["bindings"][0]["adapter"] == "openai_realtime"
    assert comps["comp_s2s_openai_v1"]["credential_source"] in {"none", "env", "admin_store", "ephemeral_ui"}


def test_ws_unknown_composition_closes_4400(client: TestClient) -> None:
    from starlette.websockets import WebSocketDisconnect

    key = _key(client, "act_csat_survey")
    with (
        pytest.raises(WebSocketDisconnect) as ei,
        client.websocket_connect(f"/ws/sessions/{key}?composition=nope") as ws,
    ):
        ws.receive_text()
    assert ei.value.code == 4400


def test_ws_real_provider_without_credential_reports_error_not_crash(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    store: RuntimeStore = client.app.state.store  # type: ignore[attr-defined]
    monkeypatch.setattr(store.credentials, "env", {})  # hide any sandbox OPENAI_API_KEY
    store.credentials.admin_store.clear()
    key = _key(client, "act_csat_survey")
    with client.websocket_connect(f"/ws/sessions/{key}?composition=pinned") as ws:
        got: list[dict[str, Any]] = []
        for _ in range(10):
            try:
                m = ws.receive()
            except Exception:  # noqa: BLE001 — closed by server
                break
            if m.get("text"):
                got.append(json.loads(m["text"]))
            if any(g["type"] == "error" for g in got):
                break
        err = next(g for g in got if g["type"] == "error")
        assert err["payload"]["code"] == "provider_credential_missing"
    s = client.get("/api/sessions").json()[-1]
    assert s["composition_id"] == "comp_s2s_openai_v1" and s["credential_source"] == "none" and s["error"]
    assert s["running"] is False


def test_ws_silero_composition_runs_on_mock_provider(client: TestClient) -> None:
    """A composition can mix silero/smart_turn turn detection with the mock provider."""
    store: RuntimeStore = client.app.state.store  # type: ignore[attr-defined]
    from qevion.contracts.composition import Composition

    store.compositions["comp_mock_smart_v1"] = Composition.model_validate(
        {
            "composition_id": "comp_mock_smart_v1",
            "mode": "s2s",
            "bindings": [
                {"role": "s2s", "adapter": "mock"},
                {"role": "turn", "adapter": "smart_turn"},
                {"role": "decision", "adapter": "rules"},
            ],
        }
    )
    key = _key(client, "act_order_intake")
    with client.websocket_connect(f"/ws/sessions/{key}?composition=comp_mock_smart_v1") as ws:
        first = json.loads(ws.receive_text())
        assert first["type"] in {"ready", "state"}
        ws.send_text(json.dumps({"type": "bye"}))
    s = client.get("/api/sessions").json()[-1]
    assert s["composition_id"] == "comp_mock_smart_v1" and s["error"] is None


# ------------------------------------------------------- voice binary path (P4)


def _pcm_frame(ms: int = 20, amplitude: int = 0, rate: int = 24000) -> bytes:
    """PCM16 mono frame: constant-amplitude square-ish tone (or silence when amplitude=0)."""
    import struct

    n = rate * ms // 1000
    return struct.pack(f"<{n}h", *([amplitude, -amplitude] * (n // 2)))


def test_ws_voice_binary_roundtrip_barge_in_records_t0_t4(client: TestClient) -> None:
    """Browser-voice channel: binary PCM16 in → provider audio out (binary) → loud frames during playout
    trigger the §31 interruption (stop_playout) and the session records t0..t4 watermarks (QV-INT)."""
    key = _key(client, "act_csat_survey")
    with client.websocket_connect(f"/ws/sessions/{key}?channel=browser_voice&composition=comp_mock_s2s_v1") as ws:
        ws.receive_text()
        ws.send_text(json.dumps({"type": "hello"}))
        # Client-side end-of-turn (the browser's "start talking" gesture) → provider greets with audio.
        ws.send_text(json.dumps({"type": "audio_commit"}))
        audio_in = 0
        response_id: str | None = None
        for _ in range(60):
            m = ws.receive()
            if m.get("bytes"):
                audio_in += len(m["bytes"])
                if response_id:
                    break
            elif m.get("text"):
                j = json.loads(m["text"])
                if j["type"] == "audio_start":
                    response_id = j["response_id"]
        assert response_id is not None and audio_in > 0, "no provider audio reached the transport"
        # Barge in: 20 loud frames (400 ms) while the assistant is speaking → BARGE_IN → stop_playout.
        for _ in range(20):
            ws.send_bytes(_pcm_frame(20, amplitude=6000))
        got_stop = False
        interruption: dict[str, Any] | None = None
        for _ in range(200):
            m = ws.receive()
            if not m.get("text"):
                continue
            j = json.loads(m["text"])
            if j["type"] == "stop_playout":
                got_stop = True
                ws.send_text(json.dumps({"type": "playout_stopped", "response_id": j["response_id"], "client_ts_ms": 1}))
            elif j["type"] == "event":
                ev = j["payload"]
                if ev.get("type") == "latency.sample" and ev["payload"].get("segment") == "interruption":
                    interruption = ev["payload"]
                    break
        assert got_stop, "stop_playout never sent"
        assert interruption is not None, "interruption latency.sample never emitted"
        assert interruption["response_id"] == response_id
        assert interruption["t0"] <= interruption["t1"] <= interruption["t2"] <= interruption["t3"] <= interruption["t4"]
        assert interruption["forced"] is False
        # Then silence → END_OF_TURN → provider commit (next response).
        for _ in range(30):
            ws.send_bytes(_pcm_frame(20, amplitude=0))
        ws.send_text(json.dumps({"type": "bye"}))
    s = client.get("/api/sessions").json()[-1]
    detail = client.get(f"/api/sessions/{s['session_id']}").json()
    assert detail["interruptions"] and detail["interruptions"][0]["response_id"] == response_id
    rec = detail["interruptions"][0]
    assert rec["t1_to_t3_ms"] is not None and rec["t1_to_t4_ms"] is not None and rec["t1_to_t4_ms"] >= rec["t1_to_t3_ms"]
    types = {e["type"] for e in detail["events"]}
    assert {"interruption.detected", "transport.playout_stopped", "user.speech_started"} <= types, types
