"""FastAPI runtime (Appendix C): REST control-plane + WS session endpoint over the mock composition.

No business logic lives here — routes call control/knowledge/core through contracts. Copilot routes are
mounted by `qevion.copilot.api.mount(app, store)` from the composition root (`qevion.runtime.main`) so the
runtime package itself never imports copilot (import-linter: Copilot != runtime).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from typing import Any

import yaml
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ValidationError

from qevion.contracts.activity import ActivityBlueprint, ReadinessState
from qevion.contracts.common import Channel, new_id
from qevion.contracts.tenant import Tenant
from qevion.contracts.transport import ClientMessage, ServerMessage, ServerMessageType
from qevion.control.readiness import IllegalReadinessTransitionError
from qevion.runtime.store import LiveSession, RuntimeStore

START = time.time()


class WsTransport:
    """TransportSession over a FastAPI WebSocket: JSON text frames = ClientMessage, binary = PCM16."""

    def __init__(self, ws: WebSocket) -> None:
        self._ws = ws
        self._q: asyncio.Queue[ClientMessage | bytes | None] = asyncio.Queue()
        self.sent: list[ServerMessage] = []
        self.audio_bytes = 0
        self.closed = False

    def push(self, item: ClientMessage | bytes | None) -> None:
        self._q.put_nowait(item)

    async def send(self, message: ServerMessage) -> None:
        self.sent.append(message)
        if self.closed:
            raise ConnectionError("ws closed")
        try:
            await self._ws.send_text(message.model_dump_json(by_alias=True))
        except Exception as e:  # noqa: BLE001 — any socket failure is a transport disconnect
            self.closed = True
            raise ConnectionError(str(e)) from e

    async def send_audio(self, response_id: str, pcm16: bytes) -> None:
        self.audio_bytes += len(pcm16)
        if self.closed:
            raise ConnectionError("ws closed")
        try:
            await self._ws.send_bytes(pcm16)
        except Exception as e:  # noqa: BLE001
            self.closed = True
            raise ConnectionError(str(e)) from e

    async def incoming(self) -> AsyncIterator[ClientMessage | bytes]:
        while True:
            item = await self._q.get()
            if item is None:
                return
            yield item

    async def close(self, reason: str = "bye") -> None:
        if self.closed:
            return
        self.closed = True
        try:
            await self._ws.close(code=1000, reason=reason[:120])
        except Exception:  # noqa: BLE001, S110 — already closed by peer
            pass


class TransitionBody(BaseModel):
    to: ReadinessState
    reason: str = "operator"
    actor: str = "operator"


class TestKeyBody(BaseModel):
    provider: str
    value: str
    tenant_id: str | None = None
    ttl_seconds: int | None = None


def _errors(e: ValidationError) -> list[str]:
    return [f"{'.'.join(str(x) for x in er['loc'])}: {er['msg']}" for er in e.errors()]


def create_app(store: RuntimeStore | None = None) -> FastAPI:
    store = store or RuntimeStore()
    app = FastAPI(title="QEVION runtime", version="0.3.0")
    app.state.store = store
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    # ------------------------------------------------------------------ health
    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "uptime_s": round(time.time() - START, 1),
            "composition": store.composition.composition_id,
            "tenants": len(store.tenants),
            "activities": len(store.activities),
            "sessions_live": sum(1 for s in store.sessions.values() if s.task and not s.task.done()),
        }

    # ----------------------------------------------------------------- tenants
    @app.get("/api/tenants")
    async def list_tenants() -> list[dict[str, Any]]:
        return [t.model_dump(mode="json", by_alias=True) for t in store.tenants.values()]

    @app.post("/api/tenants", status_code=201)
    async def create_tenant(body: dict[str, Any]) -> dict[str, Any]:
        try:
            t = Tenant.model_validate(body)
        except ValidationError as e:
            raise HTTPException(422, _errors(e)) from e
        return store.upsert_tenant(t).model_dump(mode="json", by_alias=True)

    # -------------------------------------------------------------- activities
    def _summary(key: str) -> dict[str, Any]:
        rec = store.get_activity(key)
        bp = rec.blueprint
        pf = rec.preflight
        return {
            "key": key,
            "activity_id": bp.identity.activity_id,
            "version": bp.identity.version,
            "tenant_id": bp.identity.tenant_id,
            "name": bp.identity.name,
            "direction": bp.direction.value,
            "channels": [c.value for c in bp.channels],
            "readiness": rec.readiness.state.value,
            "preflight": None
            if pf is None
            else {"status": pf.status, "blocking": len(pf.blocking), "total": len(pf.findings)},
            "decisions_unapproved": sum(1 for d in bp.version_metadata.decisions if d.approved_by is None),
            "notes": rec.notes,
        }

    @app.get("/api/activities")
    async def list_activities(tenant_id: str | None = None) -> list[dict[str, Any]]:
        return [
            _summary(k)
            for k, r in store.activities.items()
            if tenant_id is None or r.blueprint.identity.tenant_id == tenant_id
        ]

    @app.post("/api/activities", status_code=201)
    async def put_activity(body: dict[str, Any]) -> dict[str, Any]:
        try:
            bp = ActivityBlueprint.model_validate(body)
        except ValidationError as e:
            raise HTTPException(422, _errors(e)) from e
        rec = store.put_activity(bp)
        if bp.identity.tenant_id not in store.tenants:
            store.upsert_tenant(Tenant(tenant_id=bp.identity.tenant_id, name=bp.identity.tenant_id))
        return _summary(rec.key)

    @app.post("/api/activities/yaml", status_code=201)
    async def put_activity_yaml(file: UploadFile = File(...)) -> dict[str, Any]:  # noqa: B008
        try:
            body = yaml.safe_load(await file.read())
        except yaml.YAMLError as e:
            raise HTTPException(422, f"yaml: {e}") from e
        if not isinstance(body, dict):
            raise HTTPException(422, "yaml: top-level mapping expected")
        return await put_activity(body)

    @app.get("/api/activities/{key}")
    async def get_activity(key: str) -> dict[str, Any]:
        try:
            rec = store.get_activity(key)
        except KeyError as e:
            raise HTTPException(404, str(e)) from e
        return {
            **_summary(key),
            "blueprint": rec.blueprint.model_dump(mode="json", by_alias=True),
            "history": [c.payload() for c in rec.changes],
        }

    @app.post("/api/activities/{key}/preflight")
    async def preflight(key: str, strict: bool = Query(default=False)) -> dict[str, Any]:
        try:
            rec = store.run_preflight(key, strict=strict)
        except KeyError as e:
            raise HTTPException(404, str(e)) from e
        assert rec.preflight is not None  # noqa: S101 — run_preflight always sets it
        return {**_summary(key), "result": rec.preflight.model_dump(mode="json", by_alias=True)}

    @app.post("/api/activities/{key}/capabilities")
    async def capabilities(key: str) -> dict[str, Any]:
        try:
            rows = store.map_capabilities(key)
        except KeyError as e:
            raise HTTPException(404, str(e)) from e
        blocking = [r for r in rows if r.note != "optional" and r.action.value.startswith(("REQUIRES", "UNSUPPORTED"))]
        return {"key": key, "rows": [r.as_dict() for r in rows], "blocking": len(blocking)}

    @app.post("/api/activities/{key}/transition")
    async def transition(key: str, body: TransitionBody) -> dict[str, Any]:
        try:
            change = store.transition(key, body.to, reason=body.reason, actor=body.actor)
        except KeyError as e:
            raise HTTPException(404, str(e)) from e
        except IllegalReadinessTransitionError as e:
            raise HTTPException(409, str(e)) from e
        return {**_summary(key), "change": change.payload()}

    @app.get("/api/registry")
    async def registry() -> dict[str, Any]:
        return store.registry.model_dump(mode="json", by_alias=True)

    # --------------------------------------------------------------- knowledge
    @app.post("/api/knowledge/upload", status_code=201)
    async def upload(
        tenant_id: str = Form(...),  # noqa: B008
        file: UploadFile = File(...),  # noqa: B008
        activity_key: str | None = Form(default=None),  # noqa: B008
        priority: int = Form(default=100),  # noqa: B008
    ) -> dict[str, Any]:
        data = await file.read()
        try:
            report = store.ingest(
                tenant_id=tenant_id,
                name=file.filename or "upload",
                data=data,
                mime_type=file.content_type,
                activity_key=activity_key,
                priority=priority,
            )
        except KeyError as e:
            raise HTTPException(404, str(e)) from e
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        return _report(report)

    @app.get("/api/knowledge/reports/{source_id}")
    async def report(source_id: str) -> dict[str, Any]:
        r = store.reports.get(source_id)
        if r is None:
            raise HTTPException(404, source_id)
        return _report(r)

    @app.get("/api/knowledge/{tenant_id}/facts")
    async def facts(tenant_id: str, approved: bool = True) -> list[dict[str, Any]]:
        if approved:
            fs = list(store.knowledge.approved_facts(tenant_id))
        else:
            fs = [f for f in store.knowledge.facts.values() if f.tenant_id == tenant_id]
        return [f.model_dump(mode="json", by_alias=True) for f in fs]

    @app.post("/api/knowledge/facts/{fact_id}/approve")
    async def approve_fact(fact_id: str, by: str = Query(default="operator")) -> dict[str, Any]:
        try:
            f = store.knowledge.approve_fact(fact_id, by)
        except KeyError as e:
            raise HTTPException(404, str(e)) from e
        return f.model_dump(mode="json", by_alias=True)

    @app.post("/api/knowledge/contradictions/{cid}/resolve")
    async def resolve(cid: str, winner: str = Query(...), by: str = Query(default="operator")) -> dict[str, Any]:
        try:
            c = store.knowledge.resolve_contradiction(cid, winner, by=by)
        except KeyError as e:
            raise HTTPException(404, str(e)) from e
        return c.model_dump(mode="json", by_alias=True)

    @app.get("/api/knowledge/{tenant_id}/conflicts")
    async def conflicts(tenant_id: str) -> list[dict[str, Any]]:
        return [c.model_dump(mode="json", by_alias=True) for c in store.knowledge.unresolved_conflicts(tenant_id)]

    # ------------------------------------------------------------------- admin
    @app.get("/api/admin/credentials/{provider}")
    async def cred_status(provider: str, tenant_id: str | None = None) -> dict[str, Any]:
        return store.credentials.status(provider, tenant_id).model_dump(mode="json")

    @app.post("/api/admin/test-key")
    async def set_test_key(body: TestKeyBody) -> dict[str, Any]:
        """Ephemeral, in-memory only (A5). Never persisted, never logged, never returned."""
        scope = store.credentials.set_ephemeral(body.provider, body.value, body.tenant_id, body.ttl_seconds)
        return scope.model_dump(mode="json")

    @app.delete("/api/admin/test-key")
    async def clear_test_key(provider: str | None = None, tenant_id: str | None = None) -> dict[str, int]:
        return {"cleared": store.credentials.clear_ephemeral(provider, tenant_id)}

    # ---------------------------------------------------------------- sessions
    @app.get("/api/sessions")
    async def sessions() -> list[dict[str, Any]]:
        return [_live(s) for s in store.sessions.values()]

    @app.get("/api/sessions/{sid}")
    async def session_detail(sid: str) -> dict[str, Any]:
        s = store.sessions.get(sid)
        if s is None:
            raise HTTPException(404, sid)
        return {**_live(s), "events": [e.model_dump(mode="json", by_alias=True) for e in s.events[-200:]]}

    @app.get("/api/events")
    async def events(since: int = 0, limit: int = 200) -> list[dict[str, Any]]:
        return [e.model_dump(mode="json", by_alias=True) for e in store.event_log[since : since + limit]]

    @app.websocket("/ws/sessions/{activity_key}")
    async def ws_session(ws: WebSocket, activity_key: str, channel: str = "text") -> None:
        await ws.accept()
        try:
            store.get_activity(activity_key)
        except KeyError:
            await ws.close(code=4404, reason="activity not found")
            return
        sid = new_id("ses")
        transport = WsTransport(ws)
        ch = Channel(channel) if channel in {c.value for c in Channel} else Channel.TEXT
        live = store.build_session(activity_key=activity_key, transport=transport, session_id=sid, channel=ch)
        live.task = asyncio.create_task(live.session.run())
        try:
            while not live.task.done():
                msg = await ws.receive()
                if msg.get("type") == "websocket.disconnect":
                    break
                if msg.get("bytes") is not None:
                    transport.push(msg["bytes"])
                elif msg.get("text") is not None:
                    try:
                        transport.push(ClientMessage.model_validate_json(msg["text"]))
                    except ValidationError:
                        err = ServerMessage(
                            type=ServerMessageType.ERROR,
                            session_id=sid,
                            server_ts_ms=int(time.time() * 1000),
                            text="invalid client message",
                        )
                        await ws.send_text(err.model_dump_json(by_alias=True))
        except WebSocketDisconnect:
            pass
        finally:
            transport.push(None)
            try:
                await asyncio.wait_for(live.task, timeout=5)
            except (TimeoutError, asyncio.CancelledError):
                live.task.cancel()
            await transport.close("session_ended")

    return app


def _live(s: LiveSession) -> dict[str, Any]:
    rec = s.session.record
    return {
        "session_id": s.session_id,
        "activity_key": s.activity_key,
        "running": bool(s.task and not s.task.done()),
        "dialog_state": s.session.dialog.state.value,
        "activity_state": s.session.activity.state.value,
        "events": len(s.events),
        "handoffs": len(s.handoffs.requests),
        "outcome": None if rec is None else rec.outcome.model_dump(mode="json", by_alias=True),
    }


def _report(r: Any) -> dict[str, Any]:
    return {
        "source": r.source.model_dump(mode="json", by_alias=True),
        "summary": r.summary(),
        "facts": [f.model_dump(mode="json", by_alias=True) for f in r.facts],
        "entities": [e.model_dump(mode="json", by_alias=True) for e in r.entities],
        "contradictions": [c.model_dump(mode="json", by_alias=True) for c in r.contradictions],
        "gaps": [g.model_dump(mode="json", by_alias=True) for g in r.gaps],
        "customer_questions": [q.__dict__ for q in r.customer_questions],
        "operational_requirements": [o.__dict__ for o in r.operational_requirements],
        "warnings": r.warnings,
        "injection_flags": r.injection_flags,
    }


__all__ = ["WsTransport", "create_app"]
