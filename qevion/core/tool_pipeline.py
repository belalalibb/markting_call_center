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
    return hashlib.sha256(json.dumps([inv.session_id, inv.tool_id, payload], sort_keys=True, default=str).encode()).hexdigest()


# --- part 2 (ToolPipeline) appended below ---
