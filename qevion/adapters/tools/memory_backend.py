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

    entities: list[dict[str, Any]] = field(
        default_factory=list
    )  # approved entities: {entity_id, entity_type, name, ...}
    facts: list[dict[str, Any]] = field(default_factory=list)  # approved facts: {domain, key, value, source_id}
    verify_reject: set[str] = field(default_factory=set)  # field names verify_field should reject (fixture control)
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
            case PlatformTool.LOOKUP_KNOWLEDGE:
                out = _ok(invocation, self._lookup(args), Provenance.KNOWLEDGE_APPROVED)
            case PlatformTool.GET_ENTITY:
                ent = self._find_entity(args)
                out = _ok(invocation, {"found": ent is not None, "entity": ent}, Provenance.KNOWLEDGE_APPROVED)
            case PlatformTool.LIST_ENTITIES:
                ents = self._filter_entities(args.get("entity_type"), args.get("filters") or {})
                lim = args.get("limit")
                ents = ents[: int(lim)] if isinstance(lim, int) and lim > 0 else ents
                out = _ok(invocation, {"count": len(ents), "entities": ents}, Provenance.KNOWLEDGE_APPROVED)
            case PlatformTool.COMPARE_ENTITIES:
                ids = [str(i) for i in args.get("entity_ids", [])]
                ents = [e for e in self.store.entities if e.get("entity_id") in ids]
                attrs = args.get("attributes") or sorted({k for e in ents for k in e} - {"entity_id"})
                table = {a: {e["entity_id"]: e.get(a) for e in ents} for a in attrs}
                out = _ok(
                    invocation,
                    {
                        "entities": [e["entity_id"] for e in ents],
                        "missing": [i for i in ids if i not in {e["entity_id"] for e in ents}],
                        "table": table,
                    },
                    Provenance.KNOWLEDGE_APPROVED,
                )
            case PlatformTool.RECOMMEND:
                ents = self._filter_entities(args.get("entity_type"), args.get("constraints") or {})
                lim = args.get("limit")
                ents = ents[: int(lim)] if isinstance(lim, int) and lim > 0 else ents[:3]
                out = _ok(
                    invocation, {"recommendations": ents, "basis": "constraints_only"}, Provenance.KNOWLEDGE_APPROVED
                )
            case PlatformTool.COMPUTE_QUOTE:
                out = self._quote(invocation, args)
            case PlatformTool.RECORD_FIELD:
                # Recording is a user statement, not verification.
                out = _ok(invocation, {"name": args.get("name"), "value": args.get("value")}, Provenance.USER_STATED)
            case PlatformTool.VERIFY_FIELD:
                # Mock verification: accepts anything non-empty; real backends call business systems.
                name = str(args.get("name"))
                ok = args.get("value") not in (None, "") and name not in self.store.verify_reject
                out = _ok(invocation, {"name": name, "verified": ok})
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

    # -- generic read helpers (no business meaning; pure data plumbing) ------------------------------
    def _find_entity(self, args: dict[str, Any]) -> dict[str, Any] | None:
        eid, name, etype = args.get("entity_id"), args.get("name"), args.get("entity_type")
        for e in self.store.entities:
            if etype and e.get("entity_type") != etype:
                continue
            if eid and e.get("entity_id") == eid:
                return e
            if name and str(e.get("name", "")).lower() == str(name).lower():
                return e
        return None

    def _filter_entities(self, etype: Any, filters: dict[str, Any]) -> list[dict[str, Any]]:
        out = []
        for e in self.store.entities:
            if etype and e.get("entity_type") != etype:
                continue
            if all(e.get(k) == v for k, v in filters.items()):
                out.append(e)
        return out

    def _lookup(self, args: dict[str, Any]) -> dict[str, Any]:
        q = str(args.get("query", "")).lower()
        domain = args.get("domain")
        hits = [
            f
            for f in self.store.facts
            if (not domain or f.get("domain") == domain)
            and (q in str(f.get("key", "")).lower() or q in str(f.get("value", "")).lower())
        ]
        ents = [e for e in self.store.entities if q and q in str(e.get("name", "")).lower()]
        return {"found": bool(hits or ents), "facts": hits, "entities": ents}

    def _quote(self, invocation: ToolInvocation, args: dict[str, Any]) -> ToolOutcome:
        """Total = Σ unit_value × quantity from *approved entities only*; unknown items make the quote UNKNOWN."""
        lines: list[dict[str, Any]] = []
        unknown: list[str] = []
        by_id = {e.get("entity_id"): e for e in self.store.entities}
        by_name = {str(e.get("name", "")).lower(): e for e in self.store.entities}
        for it in args.get("items") or []:
            ref = it.get("entity_id") or it.get("name") if isinstance(it, dict) else it
            qty = int(it.get("quantity", 1)) if isinstance(it, dict) else 1
            ent = by_id.get(ref) or by_name.get(str(ref).lower())
            if ent is None or "unit_value" not in ent:
                unknown.append(str(ref))
                continue
            lines.append({"entity_id": ent["entity_id"], "quantity": qty, "line_total": ent["unit_value"] * qty})
        if unknown:
            return ToolOutcome(
                call_id=invocation.call_id,
                tool_id=self.tool_id,
                status=ToolOutcomeStatus.UNKNOWN,
                output={"unknown_items": unknown, "lines": lines},
                error="items not in approved catalog",
            )
        return _ok(invocation, {"lines": lines, "total": sum(x["line_total"] for x in lines)})


def memory_backends(store: MemoryStore, tool_ids: list[str] | None = None) -> dict[str, MemoryToolBackend]:
    ids = tool_ids or [
        PlatformTool.LOOKUP_KNOWLEDGE,
        PlatformTool.GET_ENTITY,
        PlatformTool.LIST_ENTITIES,
        PlatformTool.COMPARE_ENTITIES,
        PlatformTool.RECOMMEND,
        PlatformTool.COMPUTE_QUOTE,
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
