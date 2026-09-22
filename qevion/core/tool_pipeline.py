"""Tool pipeline — 11 steps, every step evented (§24 QV-TOOL, QV-ACC-009).

received → schema_validated → permission_checked → policy_checked → budget_checked → deduplicated →
confirmation → executing → result_validated → provenance_tagged → returned

Core-owned. The model proposes a tool call; this pipeline decides whether/how it runs.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from qevion.contracts.activity import ToolPermission, ToolsBlock
from qevion.contracts.common import Provenance
from qevion.contracts.event import EventType
from qevion.contracts.ports import ToolBackend
from qevion.contracts.provider import ToolCallRequest
from qevion.contracts.tool import ToolDeclaration, ToolInvocation, ToolOutcome, ToolOutcomeStatus, ToolPipelineStep

Emit = Callable[[str, dict[str, Any]], Awaitable[None]]
ConfirmFn = Callable[[ToolInvocation], Awaitable[bool | None]]  # True granted / False denied / None ask user

_STRENGTH: dict[Provenance, int] = {
    Provenance.UNKNOWN: 0,
    Provenance.UNVERIFIED: 1,
    Provenance.USER_STATED: 2,
    Provenance.SYSTEM_DERIVED: 3,
    Provenance.KNOWLEDGE_APPROVED: 4,
    Provenance.TOOL_VERIFIED: 5,
}


@dataclass
class BudgetGuard:
    """Per-session tool budget (QV-COST). Pure counters; $ estimation lives in usage accounting."""

    max_calls: int = 50
    max_write_calls: int = 20
    calls: int = 0
    write_calls: int = 0

    def allow(self, impact: str) -> bool:
        if self.calls >= self.max_calls:
            return False
        return not (impact == "write" and self.write_calls >= self.max_write_calls)

    def count(self, impact: str) -> None:
        self.calls += 1
        if impact == "write":
            self.write_calls += 1


def validate_args(schema: dict[str, Any], args: dict[str, Any]) -> list[str]:
    """Minimal JSON-Schema subset (required, type, additionalProperties). Full validation is adapter-side."""
    errs: list[str] = []
    for req in schema.get("required", []):
        if req not in args:
            errs.append(f"missing required argument '{req}'")
    props: dict[str, Any] = schema.get("properties", {})
    types: dict[str, type | tuple[type, ...]] = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "object": dict,
        "array": list,
    }
    for k, v in args.items():
        if k in props and "type" in props[k]:
            t = props[k]["type"]
            py = types.get(t)
            bad_bool = t in ("integer", "number") and isinstance(v, bool)
            if (py is not None and not isinstance(v, py)) or bad_bool:
                errs.append(f"argument '{k}' expected {t}")
        elif k not in props and schema.get("additionalProperties") is False:
            errs.append(f"unexpected argument '{k}'")
    return errs


def idempotency_key(decl: ToolDeclaration, inv: ToolInvocation) -> str | None:
    if decl.impact.value == "read":
        return None
    fields_ = decl.idempotency_key_fields or sorted(inv.arguments)
    payload = {k: inv.arguments.get(k) for k in fields_}
    return hashlib.sha256(
        json.dumps([inv.session_id, inv.tool_id, payload], sort_keys=True, default=str).encode()
    ).hexdigest()


@dataclass
class ToolPipeline:
    declarations: dict[str, ToolDeclaration]
    tools_block: ToolsBlock
    backends: dict[str, ToolBackend]
    emit: Emit
    budget: BudgetGuard = field(default_factory=BudgetGuard)
    confirm: ConfirmFn | None = None
    tenant_allowed_tools: set[str] | None = None  # None = all declared tools allowed for tenant
    _seen: dict[str, ToolOutcome] = field(default_factory=dict)
    history: list[ToolOutcome] = field(default_factory=list)

    def _permission(self, tool_id: str) -> ToolPermission | None:
        return self.tools_block.permissions.get(tool_id)

    async def run(
        self,
        call: ToolCallRequest,
        *,
        session_id: str,
        tenant_id: str,
        activity_id: str,
        turn_id: str | None,
        ts_ms: int,
    ) -> ToolOutcome:
        inv = ToolInvocation(
            call_id=call.call_id,
            tool_id=call.tool_id,
            arguments=call.arguments,
            session_id=session_id,
            tenant_id=tenant_id,
            activity_id=activity_id,
            turn_id=turn_id,
            requested_at_ms=ts_ms,
        )
        S = ToolPipelineStep  # noqa: N806
        await self.emit(EventType.TOOL_REQUESTED, {"call_id": inv.call_id, "tool_id": inv.tool_id, "step": S.RECEIVED})

        # 2 schema
        decl = self.declarations.get(inv.tool_id)
        if decl is None:
            return await self._reject(
                inv, ToolOutcomeStatus.REJECTED_ARGS, "unknown tool", EventType.TOOL_ARGS_INVALID, S.SCHEMA_VALIDATED
            )
        errs = validate_args(decl.parameters, inv.arguments)
        if errs:
            return await self._reject(
                inv, ToolOutcomeStatus.REJECTED_ARGS, "; ".join(errs), EventType.TOOL_ARGS_INVALID, S.SCHEMA_VALIDATED
            )

        # 3 permission (declared for this Activity + authorized for tenant)
        perm = self._permission(inv.tool_id)
        if perm is None or (self.tenant_allowed_tools is not None and inv.tool_id not in self.tenant_allowed_tools):
            return await self._reject(
                inv,
                ToolOutcomeStatus.REJECTED_POLICY,
                "tool not permitted for activity/tenant",
                EventType.TOOL_POLICY_REJECTED,
                S.PERMISSION_CHECKED,
            )

        # 4 policy (impact must match declaration)
        if perm.impact != decl.impact.value:
            return await self._reject(
                inv,
                ToolOutcomeStatus.REJECTED_POLICY,
                f"impact mismatch {perm.impact}!={decl.impact.value}",
                EventType.TOOL_POLICY_REJECTED,
                S.POLICY_CHECKED,
            )

        # 5 budget
        if not self.budget.allow(perm.impact):
            return await self._reject(
                inv,
                ToolOutcomeStatus.REJECTED_BUDGET,
                "tool budget exhausted",
                EventType.BUDGET_EXCEEDED,
                S.BUDGET_CHECKED,
            )

        # 6 dedup
        key = idempotency_key(decl, inv)
        if key and key in self._seen:
            prev = self._seen[key]
            await self.emit(
                EventType.TOOL_DUPLICATE_IGNORED,
                {"call_id": inv.call_id, "tool_id": inv.tool_id, "duplicate_of": prev.call_id},
            )
            dup = prev.model_copy(
                update={"call_id": inv.call_id, "status": ToolOutcomeStatus.DUPLICATE, "step_reached": S.DEDUPLICATED}
            )
            self.history.append(dup)
            return dup

        # 7 confirmation
        if perm.confirmation == "confirm_before_execute":
            await self.emit(EventType.TOOL_CONFIRMATION_REQUESTED, {"call_id": inv.call_id, "tool_id": inv.tool_id})
            granted = await self.confirm(inv) if self.confirm else None
            if granted is None:
                return ToolOutcome(
                    call_id=inv.call_id,
                    tool_id=inv.tool_id,
                    status=ToolOutcomeStatus.CONFIRMATION_DENIED,
                    error="confirmation pending",
                    step_reached=S.CONFIRMATION,
                )
            if not granted:
                await self.emit(EventType.TOOL_CONFIRMATION_DENIED, {"call_id": inv.call_id})
                return await self._reject(
                    inv, ToolOutcomeStatus.CONFIRMATION_DENIED, "user denied", None, S.CONFIRMATION
                )
            await self.emit(EventType.TOOL_CONFIRMATION_GRANTED, {"call_id": inv.call_id})

        # 8 execute
        backend = self.backends.get(inv.tool_id)
        if backend is None:
            return await self._reject(
                inv, ToolOutcomeStatus.FAILED, "no backend bound", EventType.TOOL_EXECUTION_FAILED, S.EXECUTING
            )
        self.budget.count(perm.impact)
        await self.emit(EventType.TOOL_EXECUTION_STARTED, {"call_id": inv.call_id, "tool_id": inv.tool_id})
        try:
            out = await asyncio.wait_for(backend.execute(inv), timeout=decl.timeout_ms / 1000)
        except TimeoutError:
            out = ToolOutcome(
                call_id=inv.call_id,
                tool_id=inv.tool_id,
                status=ToolOutcomeStatus.TIMEOUT,
                error="timeout",
                step_reached=S.EXECUTING,
            )
        except Exception as e:  # noqa: BLE001 — adapters must never crash the Core
            out = ToolOutcome(
                call_id=inv.call_id,
                tool_id=inv.tool_id,
                status=ToolOutcomeStatus.FAILED,
                error=f"{type(e).__name__}: {e}",
                step_reached=S.EXECUTING,
            )

        # 9 result validation — UNKNOWN is preserved, never upgraded to success
        if out.status is ToolOutcomeStatus.UNKNOWN:
            await self.emit(EventType.TOOL_EXECUTION_UNKNOWN, {"call_id": inv.call_id, "tool_id": inv.tool_id})
        elif out.status is not ToolOutcomeStatus.COMPLETED:
            await self.emit(
                EventType.TOOL_EXECUTION_FAILED,
                {"call_id": inv.call_id, "tool_id": inv.tool_id, "status": out.status, "error": out.error},
            )
        else:
            # 10 provenance tag — never stronger than the declaration allows
            prov = (
                out.provenance
                if _STRENGTH[out.provenance] <= _STRENGTH[decl.result_provenance]
                else decl.result_provenance
            )
            out = out.model_copy(update={"provenance": prov, "step_reached": S.RETURNED})
            await self.emit(
                EventType.TOOL_EXECUTION_COMPLETED,
                {"call_id": inv.call_id, "tool_id": inv.tool_id, "provenance": prov, "latency_ms": out.latency_ms},
            )
            if key:
                self._seen[key] = out
        # 11 returned
        self.history.append(out)
        return out

    async def _reject(
        self, inv: ToolInvocation, status: ToolOutcomeStatus, reason: str, event: str | None, step: ToolPipelineStep
    ) -> ToolOutcome:
        if event:
            await self.emit(event, {"call_id": inv.call_id, "tool_id": inv.tool_id, "reason": reason, "step": step})
        out = ToolOutcome(
            call_id=inv.call_id,
            tool_id=inv.tool_id,
            status=status,
            error=reason,
            provenance=Provenance.UNKNOWN,
            step_reached=step,
        )
        self.history.append(out)
        return out
