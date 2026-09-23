"""Copilot HTTP surface. Mounted by the composition root; the runtime package never imports this.

`mount(app, ctx)` receives duck-typed context callables so copilot stays independent of runtime internals:
  ctx.preflight_ctx(bp_draft_dict) -> PreflightContext | None
  ctx.mapper() -> CapabilityMapper | None
  ctx.knowledge(tenant_id) -> (gaps, contradictions)
  ctx.publish(blueprint) -> key   (stores the approved draft as an Activity version)
  ctx.event_sink(event)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from qevion.contracts.activity import ActivityBlueprint
from qevion.contracts.event import Event
from qevion.contracts.knowledge import Contradiction, KnowledgeGap
from qevion.control.capabilities import CapabilityMapper
from qevion.control.preflight import PreflightContext
from qevion.copilot.session import ConfigSession


@dataclass
class CopilotContext:
    preflight_ctx: Callable[[], PreflightContext | None]
    mapper: Callable[[], CapabilityMapper | None]
    knowledge: Callable[[str], tuple[list[KnowledgeGap], list[Contradiction]]]
    publish: Callable[[ActivityBlueprint], str]
    event_sink: Callable[[Event], None] | None = None


class StartBody(BaseModel):
    tenant_id: str
    activity_id: str
    name: str
    version: str = "0.1.0"
    seed: dict[str, Any] | None = None
    operator_id: str = "operator"


class AnswerBody(BaseModel):
    question_id: str
    value: Any = None
    operator_id: str = "operator"
    mode: str = "answer"  # answer | accept | defer


class ApproveBody(BaseModel):
    item_path: str
    operator_id: str = "operator"


def mount(app: FastAPI, ctx: CopilotContext) -> dict[str, ConfigSession]:
    sessions: dict[str, ConfigSession] = {}

    def _get(sid: str) -> ConfigSession:
        s = sessions.get(sid)
        if s is None:
            raise HTTPException(404, f"config session {sid} not found")
        return s

    def _view(s: ConfigSession, *, limit: int = 3) -> dict[str, Any]:
        gaps, contradictions = ctx.knowledge(s.state.tenant_id)
        s.set_knowledge(gaps, contradictions)
        proposal = s.propose()
        nxt = s.next_questions(limit=limit)
        return {
            "config_session_id": s.state.config_session_id,
            "tenant_id": s.state.tenant_id,
            "activity_id": s.state.activity_id,
            "status": proposal.status.value,
            "readiness_state": proposal.readiness_state.value,
            "draft_valid": proposal.draft_valid,
            "validation_errors": proposal.validation_errors,
            "draft": s.state.draft,
            "decisions": [d.model_dump(mode="json") for d in proposal.decisions],
            "unapproved": [d.item_path for d in proposal.unapproved_decisions],
            "questions": [q.model_dump(mode="json") for q in nxt],
            "questions_total": len(proposal.questions),
            "blocking_total": sum(1 for q in proposal.questions if q.blocking),
            "gap_counts": proposal.gap_counts(),
            "contradictions": [c.model_dump(mode="json") for c in proposal.contradictions],
            "capability_requirements": [c.model_dump(mode="json") for c in proposal.capability_requirements],
            "preflight_findings": [f.model_dump(mode="json") for f in proposal.preflight_findings],
            "readiness_findings": [r.model_dump(mode="json") for r in proposal.readiness_findings],
            "simulation_cases": proposal.simulation_cases,
            "explanation": s.explain(proposal),
            "question_explanations": {q.question_id: s.explain_question(q.question_id) for q in nxt},
        }

    @app.post("/api/copilot/sessions", status_code=201)
    async def start(body: StartBody) -> dict[str, Any]:
        s = ConfigSession(
            tenant_id=body.tenant_id,
            activity_id=body.activity_id,
            name=body.name,
            version=body.version,
            preflight_ctx=ctx.preflight_ctx(),
            mapper=ctx.mapper(),
            event_sink=ctx.event_sink,
        )
        if body.seed:
            s.seed_draft(body.seed, operator_id=body.operator_id)
        sessions[s.state.config_session_id] = s
        return _view(s)

    @app.get("/api/copilot/sessions")
    async def list_sessions() -> list[dict[str, Any]]:
        return [
            {"config_session_id": k, "tenant_id": s.state.tenant_id, "activity_id": s.state.activity_id}
            for k, s in sessions.items()
        ]

    @app.get("/api/copilot/sessions/{sid}")
    async def get_session(sid: str, limit: int = 3) -> dict[str, Any]:
        return _view(_get(sid), limit=limit)

    @app.post("/api/copilot/sessions/{sid}/answer")
    async def answer(sid: str, body: AnswerBody) -> dict[str, Any]:
        s = _get(sid)
        try:
            if body.mode == "accept":
                s.accept(body.question_id, operator_id=body.operator_id)
            elif body.mode == "defer":
                s.defer(body.question_id)
            else:
                s.answer(body.question_id, body.value, operator_id=body.operator_id)
        except KeyError as e:
            raise HTTPException(404, str(e)) from e
        except ValueError as e:
            raise HTTPException(409, str(e)) from e
        return _view(s)

    @app.post("/api/copilot/sessions/{sid}/approve")
    async def approve(sid: str, body: ApproveBody) -> dict[str, Any]:
        s = _get(sid)
        try:
            s.approve_decision(body.item_path, operator_id=body.operator_id)
        except KeyError as e:
            raise HTTPException(404, str(e)) from e
        return _view(s)

    @app.post("/api/copilot/sessions/{sid}/publish")
    async def publish(sid: str) -> dict[str, Any]:
        s = _get(sid)
        proposal = s.propose()
        if proposal.draft is None or not proposal.draft_valid:
            raise HTTPException(409, {"reason": "draft_invalid", "errors": proposal.validation_errors})
        if proposal.unapproved_decisions:
            raise HTTPException(
                409, {"reason": "unapproved_decisions", "paths": [d.item_path for d in proposal.unapproved_decisions]}
            )
        key = ctx.publish(proposal.draft)
        return {"activity_key": key, "readiness_state": proposal.readiness_state.value, "status": proposal.status.value}

    return sessions


__all__ = ["CopilotContext", "mount"]
