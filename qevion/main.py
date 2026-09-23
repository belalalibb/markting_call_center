"""Composition root (outside runtime/ and copilot/): runtime app + copilot routes + static web UI.
This is the only module allowed to import both `qevion.runtime` and `qevion.copilot` (import-linter).

Run: `uvicorn qevion.main:app --host 0.0.0.0 --port 8000`
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from qevion.contracts.activity import ActivityBlueprint
from qevion.contracts.event import Event
from qevion.contracts.knowledge import Contradiction, KnowledgeGap
from qevion.contracts.tenant import Tenant
from qevion.control.capabilities import CapabilityMapper
from qevion.control.preflight import PreflightContext
from qevion.copilot.api import CopilotContext, mount
from qevion.runtime.app import create_app
from qevion.runtime.store import ROOT, RuntimeStore

WEB_DIST = ROOT / "web" / "dist"


def build(store: RuntimeStore | None = None, *, seed_examples: bool = True, web_dist: Path | None = None) -> FastAPI:
    store = store or RuntimeStore()
    app = create_app(store)

    def _preflight_ctx() -> PreflightContext:
        return PreflightContext(
            registry=store.registry,
            composition=store.composition,
            tool_declarations=store.tool_declarations,
            locale_packs=store.locale_packs,
            voice_profiles=store.voice_profiles,
            strict_capabilities=False,
        )

    def _mapper() -> CapabilityMapper:
        return CapabilityMapper(store.registry, store.composition)

    def _knowledge(tenant_id: str) -> tuple[list[KnowledgeGap], list[Contradiction]]:
        gaps = [g for g in store.knowledge.gaps.values() if g.tenant_id == tenant_id and not g.resolved]
        return gaps, list(store.knowledge.unresolved_conflicts(tenant_id))

    def _publish(bp: ActivityBlueprint) -> str:
        if bp.identity.tenant_id not in store.tenants:
            store.upsert_tenant(Tenant(tenant_id=bp.identity.tenant_id, name=bp.identity.tenant_id))
        return store.put_activity(bp).key

    def _sink(ev: Event) -> None:
        store.event_log.append(ev)

    mount(app, CopilotContext(_preflight_ctx, _mapper, _knowledge, _publish, _sink))

    if seed_examples:
        _seed(store)

    dist = web_dist or WEB_DIST
    if dist.is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/", include_in_schema=False)
        async def index() -> FileResponse:
            return FileResponse(dist / "index.html")

        @app.get("/{path:path}", include_in_schema=False)
        async def spa(path: str) -> FileResponse:
            target = dist / path
            if target.is_file():
                return FileResponse(target)
            return FileResponse(dist / "index.html")

    return app


def _seed(store: RuntimeStore) -> None:
    store.upsert_tenant(Tenant(tenant_id="t_demo", name="Demo Tenant"))
    for name in ("activity_a_restaurant", "activity_b_clinic", "activity_c_survey"):
        p = ROOT / "config" / "examples" / f"{name}.yaml"
        if p.exists():
            bp = ActivityBlueprint.model_validate(yaml.safe_load(p.read_text()))
            if bp.identity.tenant_id not in store.tenants:
                store.upsert_tenant(Tenant(tenant_id=bp.identity.tenant_id, name=bp.identity.tenant_id))
            store.put_activity(bp)


app = build(seed_examples=os.environ.get("QEVION_SEED", "1") != "0")

# WebSocket keepalive tuning for browser_voice sessions (QV-INT). uvicorn defaults (20 s ping / 20 s timeout) are
# fine on a LAN but a proxied browser under audio load missed Pongs in the field (1011). Wider windows + a larger
# frame queue; the application heartbeat in runtime.app covers liveness. Used by `python -m qevion.main`.
UVICORN_WS_KWARGS: dict[str, object] = {
    "ws_ping_interval": float(os.environ.get("QEVION_WS_PING_INTERVAL_S", "25")),
    "ws_ping_timeout": float(os.environ.get("QEVION_WS_PING_TIMEOUT_S", "60")),
    "ws_max_queue": int(os.environ.get("QEVION_WS_MAX_QUEUE", "256")),
    "ws_max_size": 16 * 1024 * 1024,
}


def serve() -> None:
    """`python -m qevion.main` — uvicorn with the keepalive settings above (equivalent CLI flags in README)."""
    import uvicorn  # noqa: PLC0415 - composition root only

    uvicorn.run(
        "qevion.main:app",
        host=os.environ.get("QEVION_HOST", "0.0.0.0"),  # noqa: S104 - sandbox/container binding
        port=int(os.environ.get("QEVION_PORT", "8000")),
        log_level=os.environ.get("QEVION_LOG_LEVEL", "info").lower(),
        **UVICORN_WS_KWARGS,  # type: ignore[arg-type]
    )


if __name__ == "__main__":
    serve()

__all__ = ["UVICORN_WS_KWARGS", "app", "build", "serve"]
