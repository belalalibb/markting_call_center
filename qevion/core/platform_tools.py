"""Platform tool catalog (§24 QV-TOOL): `tool.v1` declarations for the generic tools every Activity may reference.

Business tools are Blueprint data; these are the fixed, domain-neutral primitives the Core understands
(record/verify/submit/clarify/handoff/…). Adapters render them into provider shapes; backends execute them.
Argument names are generic on purpose (`name`, `value`, `fields`, `query`) — never business vocabulary.
"""

from __future__ import annotations

from typing import Any

from qevion.contracts.common import Provenance
from qevion.contracts.tool import PlatformTool, ToolDeclaration, ToolImpact

_OBJ: dict[str, Any] = {"type": "object"}


def _params(required: list[str], **props: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "required": required, "properties": props, "additionalProperties": True}


_S: dict[str, Any] = {"type": "string"}
_N: dict[str, Any] = {"type": "number"}
_I: dict[str, Any] = {"type": "integer"}
_ARR_S: dict[str, Any] = {"type": "array", "items": _S}

_DECLS: dict[str, ToolDeclaration] = {
    PlatformTool.LOOKUP_KNOWLEDGE: ToolDeclaration(
        tool_id=PlatformTool.LOOKUP_KNOWLEDGE,
        description="Look up an approved fact in the Activity's knowledge sources. Returns facts with provenance.",
        parameters=_params(["query"], query=_S, domain=_S, entity_id=_S),
        impact=ToolImpact.READ,
        result_provenance=Provenance.KNOWLEDGE_APPROVED,
    ),
    PlatformTool.GET_ENTITY: ToolDeclaration(
        tool_id=PlatformTool.GET_ENTITY,
        description="Fetch one approved entity by id or exact name.",
        parameters=_params([], entity_id=_S, name=_S, entity_type=_S),
        impact=ToolImpact.READ,
        result_provenance=Provenance.KNOWLEDGE_APPROVED,
    ),
    PlatformTool.LIST_ENTITIES: ToolDeclaration(
        tool_id=PlatformTool.LIST_ENTITIES,
        description="List approved entities of a type, optionally filtered.",
        parameters=_params([], entity_type=_S, filters=_OBJ, limit=_I),
        impact=ToolImpact.READ,
        result_provenance=Provenance.KNOWLEDGE_APPROVED,
    ),
    PlatformTool.COMPARE_ENTITIES: ToolDeclaration(
        tool_id=PlatformTool.COMPARE_ENTITIES,
        description="Compare approved entities attribute by attribute. Never invents attributes.",
        parameters=_params(["entity_ids"], entity_ids=_ARR_S, attributes=_ARR_S),
        impact=ToolImpact.READ,
        result_provenance=Provenance.KNOWLEDGE_APPROVED,
    ),
    PlatformTool.RECOMMEND: ToolDeclaration(
        tool_id=PlatformTool.RECOMMEND,
        description="Recommend among approved entities using stated constraints only.",
        parameters=_params([], entity_type=_S, constraints=_OBJ, limit=_I),
        impact=ToolImpact.READ,
        result_provenance=Provenance.KNOWLEDGE_APPROVED,
    ),
    PlatformTool.CHECK_RULE: ToolDeclaration(
        tool_id=PlatformTool.CHECK_RULE,
        description="Evaluate a named Activity rule against recorded facts. Returns true/false/unknown.",
        parameters=_params(["rule"], rule=_S, inputs=_OBJ),
        impact=ToolImpact.READ,
        result_provenance=Provenance.SYSTEM_DERIVED,
    ),
    PlatformTool.COMPUTE_QUOTE: ToolDeclaration(
        tool_id=PlatformTool.COMPUTE_QUOTE,
        description="Compute a price/total from approved unit values. Returns line items and total.",
        parameters=_params(["items"], items={"type": "array"}, options=_OBJ),
        impact=ToolImpact.READ,
        result_provenance=Provenance.TOOL_VERIFIED,
    ),
    PlatformTool.RECORD_FIELD: ToolDeclaration(
        tool_id=PlatformTool.RECORD_FIELD,
        description="Record a datum the user stated. Core validates it; a record is not verification.",
        parameters=_params(["name", "value"], name=_S, value={}),
        impact=ToolImpact.WRITE,
        idempotency_key_fields=["name", "value"],
        result_provenance=Provenance.USER_STATED,
    ),
    PlatformTool.VERIFY_FIELD: ToolDeclaration(
        tool_id=PlatformTool.VERIFY_FIELD,
        description="Verify a recorded datum against a business system. Only this upgrades provenance.",
        parameters=_params(["name", "value"], name=_S, value={}),
        impact=ToolImpact.READ,
        result_provenance=Provenance.TOOL_VERIFIED,
    ),
    PlatformTool.CLARIFY: ToolDeclaration(
        tool_id=PlatformTool.CLARIFY,
        description="Signal that the user's statement is ambiguous and ask the given clarifying question.",
        parameters=_params(["question"], question=_S, field=_S),
        impact=ToolImpact.READ,
        result_provenance=Provenance.SYSTEM_DERIVED,
    ),
    PlatformTool.REQUEST_HANDOFF: ToolDeclaration(
        tool_id=PlatformTool.REQUEST_HANDOFF,
        description="Request a human handoff with a reason. Core owns the decision and the context projection.",
        parameters=_params(["reason"], reason=_S, destination_ref=_S),
        impact=ToolImpact.ESCALATION,
        result_provenance=Provenance.SYSTEM_DERIVED,
    ),
    PlatformTool.SUBMIT_RECORD: ToolDeclaration(
        tool_id=PlatformTool.SUBMIT_RECORD,
        description="Persist the collected record. Executes only after Core readiness and any required confirmation.",
        parameters=_params(["fields"], record_type=_S, fields=_OBJ),
        impact=ToolImpact.WRITE,
        confirmation="confirm_before_execute",
        idempotency_key_fields=["record_type", "fields"],
        result_provenance=Provenance.TOOL_VERIFIED,
    ),
    PlatformTool.SCHEDULE_CALLBACK: ToolDeclaration(
        tool_id=PlatformTool.SCHEDULE_CALLBACK,
        description="Schedule a callback at the time the user asked for.",
        parameters=_params(["when"], when=_S, reason=_S),
        impact=ToolImpact.WRITE,
        idempotency_key_fields=["when"],
        result_provenance=Provenance.TOOL_VERIFIED,
    ),
    PlatformTool.COLLECT_QUESTION: ToolDeclaration(
        tool_id=PlatformTool.COLLECT_QUESTION,
        description="Store a question the line cannot answer so the operator can add coverage.",
        parameters=_params(["question"], question=_S, topic=_S),
        impact=ToolImpact.WRITE,
        idempotency_key_fields=["question"],
        result_provenance=Provenance.SYSTEM_DERIVED,
    ),
}


def platform_declarations(overrides: dict[str, dict[str, Any]] | None = None) -> dict[str, ToolDeclaration]:
    """Fresh copies of every platform declaration, with optional per-tool field overrides (e.g. from a Blueprint's
    permissions: `{"submit_record": {"confirmation": "none"}}`)."""
    out: dict[str, ToolDeclaration] = {}
    for tid, decl in _DECLS.items():
        upd = (overrides or {}).get(str(tid), {})
        out[str(tid)] = decl.model_copy(update=upd) if upd else decl.model_copy()
    return out


def declarations_for_blueprint_permissions(permissions: dict[str, Any]) -> dict[str, ToolDeclaration]:
    """Align impact/confirmation of platform declarations with the Activity's permissions block so the pipeline's
    policy step (#4) compares like with like. Permission entries may be pydantic models or dicts."""
    overrides: dict[str, dict[str, Any]] = {}
    for tid, perm in permissions.items():
        if tid not in _DECLS:
            continue
        impact = getattr(perm, "impact", None) if not isinstance(perm, dict) else perm.get("impact")
        conf = getattr(perm, "confirmation", None) if not isinstance(perm, dict) else perm.get("confirmation")
        upd: dict[str, Any] = {}
        if impact:
            upd["impact"] = ToolImpact(impact)
        if conf:
            upd["confirmation"] = conf
        overrides[tid] = upd
    return platform_declarations(overrides)


__all__ = ["declarations_for_blueprint_permissions", "platform_declarations"]
