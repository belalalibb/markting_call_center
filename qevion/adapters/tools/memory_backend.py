"""In-memory tool backends for the generic platform tools (§24). No business logic — pure data plumbing.

`record_field`, `verify_field`, `submit_record`, `schedule_callback`, `collect_question`, `request_handoff`,
`clarify` are Core-owned semantics; these backends only persist/echo so the pipeline can be exercised on mocks.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from qevion.contracts.common import Provenance
from qevion.contracts.tool import PlatformTool, ToolInvocation, ToolOutcome, ToolOutcomeStatus


@dataclass
class MemoryStore:
    """Shared tenant-scoped store; one instance per test/session bundle."""

    records: list[dict[str, Any]] = field(default_factory=list)
    callbacks: list[dict[str, Any]] = field(default_factory=list)
    questions: list[dict[str, Any]] = field(default_factory=list)
    handoffs: list[dict[str, Any]] = field(default_factory=list)
    fail_next: set[str] = field(default_factory=set)  # tool_ids that should fail on next call (fault injection)
    unknown_next: set[str] = field(default_factory=set)  # tool_ids that should return UNKNOWN (network-ambiguity)


def _ok(inv: ToolInvocation, output: dict[str, Any], provenance: Provenance = Provenance.TOOL_VERIFIED) -> ToolOutcome:
    return ToolOutcome(
        call_id=inv.call_id,
        tool_id=inv.tool_id,
        status=ToolOutcomeStatus.COMPLETED,
        output=output,
        provenance=provenance,
    )


@dataclass
class MemoryToolBackend:
    tool_id: str
    store: MemoryStore

    async def execute(self, invocation: ToolInvocation) -> ToolOutcome:
        t0 = time.perf_counter()
        if self.tool_id in self.store.fail_next:
            self.store.fail_next.discard(self.tool_id)
            return ToolOutcome(
                call_id=invocation.call_id,
                tool_id=self.tool_id,
                status=ToolOutcomeStatus.FAILED,
                error="injected failure",
            )
        if self.tool_id in self.store.unknown_next:
            self.store.unknown_next.discard(self.tool_id)
            return ToolOutcome(
                call_id=invocation.call_id,
                tool_id=self.tool_id,
                status=ToolOutcomeStatus.UNKNOWN,
                error="injected ambiguity",
            )
        args = invocation.arguments
        base = {
            "tenant_id": invocation.tenant_id,
            "session_id": invocation.session_id,
            "activity_id": invocation.activity_id,
        }
        match self.tool_id:
            case PlatformTool.RECORD_FIELD:
                # Recording is a user statement, not verification.
                out = _ok(invocation, {"name": args.get("name"), "value": args.get("value")}, Provenance.USER_STATED)
            case PlatformTool.VERIFY_FIELD:
                # Mock verification: accepts anything non-empty; real backends call business systems.
                ok = args.get("value") not in (None, "")
                out = _ok(invocation, {"name": args.get("name"), "verified": ok})
            case PlatformTool.SUBMIT_RECORD:
                rec = {
                    **base,
                    "record_type": args.get("record_type", "generic"),
                    "fields": args.get("fields", {}),
                    "id": f"rec_{len(self.store.records) + 1}",
                }
                self.store.records.append(rec)
                out = _ok(invocation, {"accepted": True, "record_id": rec["id"]})
            case PlatformTool.SCHEDULE_CALLBACK:
                cb = {
                    **base,
                    "when": args.get("when"),
                    "reason": args.get("reason"),
                    "id": f"cb_{len(self.store.callbacks) + 1}",
                }
                self.store.callbacks.append(cb)
                out = _ok(invocation, {"scheduled": True, "callback_id": cb["id"]})
            case PlatformTool.COLLECT_QUESTION:
                q = {**base, "question": args.get("question"), "topic": args.get("topic")}
                self.store.questions.append(q)
                out = _ok(invocation, {"collected": True}, Provenance.SYSTEM_DERIVED)
            case PlatformTool.REQUEST_HANDOFF:
                h = {**base, "reason": args.get("reason"), "destination_ref": args.get("destination_ref")}
                self.store.handoffs.append(h)
                out = _ok(invocation, {"requested": True}, Provenance.SYSTEM_DERIVED)
            case PlatformTool.CLARIFY:
                out = _ok(invocation, {"question": args.get("question")}, Provenance.SYSTEM_DERIVED)
            case PlatformTool.CHECK_RULE:
                out = _ok(
                    invocation,
                    {"rule": args.get("rule"), "result": None, "note": "evaluate via decision port"},
                    Provenance.SYSTEM_DERIVED,
                )
            case _:
                return ToolOutcome(
                    call_id=invocation.call_id,
                    tool_id=self.tool_id,
                    status=ToolOutcomeStatus.FAILED,
                    error=f"no memory backend for {self.tool_id}",
                )
        out.latency_ms = int((time.perf_counter() - t0) * 1000)
        return out


def memory_backends(store: MemoryStore, tool_ids: list[str] | None = None) -> dict[str, MemoryToolBackend]:
    ids = tool_ids or [
        PlatformTool.RECORD_FIELD,
        PlatformTool.VERIFY_FIELD,
        PlatformTool.SUBMIT_RECORD,
        PlatformTool.SCHEDULE_CALLBACK,
        PlatformTool.COLLECT_QUESTION,
        PlatformTool.REQUEST_HANDOFF,
        PlatformTool.CLARIFY,
        PlatformTool.CHECK_RULE,
    ]
    return {str(t): MemoryToolBackend(tool_id=str(t), store=store) for t in ids}
