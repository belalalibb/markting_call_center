"""P1 Core primitives — FieldStore, machines, context, governance, tool pipeline.

Evidence for QV-ACC-007 (provenance), QV-ACC-008 (claim governance), QV-ACC-009 (tool pipeline gates).
Core is exercised only through contracts + mock adapters; no business vocabulary lives here.
"""

from __future__ import annotations

from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st
from qevion.adapters.decision.rules import RulesDecisionAdapter
from qevion.adapters.tools.memory_backend import MemoryStore, MemoryToolBackend
from qevion.contracts.activity import FieldSpec, ToolPermission, ToolRef, ToolsBlock
from qevion.contracts.common import Provenance
from qevion.contracts.control import ActivityState, DialogState
from qevion.contracts.policy import (
    Behavior,
    BehaviorOverride,
    ClaimRule,
    PolicyBlock,
    UncertaintyPolicy,
    UnknownQuestionPolicy,
)
from qevion.contracts.provider import DecisionSource, ToolCallRequest
from qevion.contracts.tool import PlatformTool, ToolDeclaration, ToolImpact, ToolOutcomeStatus, ToolPipelineStep
from qevion.core.activity_machine import GENERIC_DEFAULT_V1, ActivityMachine, ActivityTrigger, validate_table
from qevion.core.context import EntityFocusStack, ObjectiveKind, PendingObjectives
from qevion.core.dialog_machine import DialogMachine, IllegalTransitionError
from qevion.core.field_store import FieldStore, satisfies
from qevion.core.governance import ClaimGovernor, ConfirmationInterpreter
from qevion.core.tool_pipeline import BudgetGuard, ToolPipeline, validate_args

# ---------------------------------------------------------------- FieldStore (QV-ACC-007)

_PROV = list(Provenance)


def _specs() -> tuple[list[FieldSpec], list[FieldSpec]]:
    req = [
        FieldSpec(name="alpha", type="string"),
        FieldSpec(name="beta", type="integer", provenance_required=Provenance.TOOL_VERIFIED),
    ]
    opt = [FieldSpec(name="gamma", type="string")]
    return req, opt


def test_field_store_record_correct_verify_reject() -> None:
    store = FieldStore.from_specs(*_specs())
    assert store.missing_required() == ["alpha", "beta"]
    assert store.next_required() == "alpha"

    fv = store.record("alpha", "x", Provenance.USER_STATED, turn_id="t1", ts_ms=1)
    assert fv.value == "x" and fv.corrected_from is None
    assert store.missing_required() == ["beta"]

    # correction keeps the previous value
    fv2 = store.record("alpha", "y", Provenance.USER_STATED, turn_id="t2", ts_ms=2)
    assert fv2.value == "y" and fv2.corrected_from == "x"

    # weaker provenance re-stating the same value is a no-op
    store.record("alpha", "y", Provenance.UNVERIFIED, ts_ms=3)
    assert store.get("alpha") is not None and store.get("alpha").provenance is Provenance.USER_STATED  # type: ignore[union-attr]

    # beta requires TOOL_VERIFIED: user statement records but does not satisfy
    store.record("beta", 7, Provenance.USER_STATED, ts_ms=4)
    assert store.missing_required() == []
    assert not store.ready_for_execution()
    assert store.unsatisfied_required() == [("beta", Provenance.TOOL_VERIFIED, Provenance.USER_STATED)]

    store.verify("beta", tool_call_id="c1", ts_ms=5)
    assert store.ready_for_execution()
    assert store.verified_names() == ["beta"]
    assert store.get("beta").tool_call_id == "c1"  # type: ignore[union-attr]

    store.reject("alpha", ts_ms=6)
    assert "alpha" in store.rejected_names()
    assert not store.ready_for_execution()
    assert len(store.history) >= 4


def test_satisfies_ordering() -> None:
    assert satisfies(Provenance.TOOL_VERIFIED, Provenance.USER_STATED)
    assert satisfies(Provenance.KNOWLEDGE_APPROVED, Provenance.SYSTEM_DERIVED)
    assert not satisfies(Provenance.USER_STATED, Provenance.TOOL_VERIFIED)
    assert not satisfies(Provenance.UNVERIFIED, Provenance.UNVERIFIED)
    assert not satisfies(Provenance.UNKNOWN, Provenance.UNKNOWN)


@given(actual=st.sampled_from(_PROV), required=st.sampled_from(_PROV))
def test_unverified_never_satisfies(actual: Provenance, required: Provenance) -> None:
    """UNKNOWN / UNVERIFIED can never satisfy any requirement — even themselves (QV-FLD)."""
    if actual in (Provenance.UNKNOWN, Provenance.UNVERIFIED):
        assert not satisfies(actual, required)


# ---------------------------------------------------------------- Dialog machine


def test_dialog_machine_happy_path_and_barge_in() -> None:
    dm = DialogMachine()
    assert dm.state.value == "IDLE"  # (.value avoids mypy narrowing across mutating fire() calls)
    dm.fire("session_started", 1)
    dm.fire("end_of_turn", 2)
    assert dm.state == DialogState.THINKING
    dm.fire("tool_requested", 3)
    dm.fire("tool_returned", 4)
    dm.fire("response_started", 5)
    assert dm.state.value == "SPEAKING"
    t = dm.fire("barge_in", 6, reason="user spoke")
    assert t.to_state == DialogState.INTERRUPTED and t.reason == "user spoke" and t.authority == "core"
    assert t.machine == "dialog" and t.from_state == DialogState.SPEAKING
    dm.fire("reconciled", 7)
    assert dm.state == DialogState.LISTENING
    assert not dm.can("response_done")
    with pytest.raises(IllegalTransitionError):
        dm.fire("response_done", 8)
    dm.fire("close", 9)
    assert dm.state == DialogState.CLOSED and not dm.can("session_started")


def test_dialog_machine_provider_chains_response_after_tool_from_listening() -> None:
    """Real S2S providers speak again (or call another tool) right after a tool result without a new user turn."""
    dm = DialogMachine()
    dm.fire("session_started", 1)
    dm.fire("text_received", 2)
    dm.fire("tool_requested", 3)
    dm.fire("tool_returned", 4)
    dm.fire("nothing_to_say", 5)  # response.done of the tool-call response arrives while THINKING
    assert dm.state == DialogState.LISTENING
    dm.fire("response_started", 6)  # follow-up spoken response, no user turn in between
    assert dm.state.value == "SPEAKING"
    dm.fire("response_done", 7)
    dm.fire("tool_requested", 8)  # or a chained second tool call straight from LISTENING
    assert dm.state == DialogState.WAITING_TOOL
    assert not dm.can("response_done")


# ---------------------------------------------------------------- Activity machine (data-driven)


def test_generic_table_is_valid_and_terminal_states_absorb() -> None:
    assert validate_table(GENERIC_DEFAULT_V1) == []
    am = ActivityMachine.from_blueprint_ref("generic_default_v1", None)
    am.fire(ActivityTrigger.OPENED, 1)
    am.fire(ActivityTrigger.FIELD_NEEDED, 2)
    assert am.state.value == "COLLECTING"
    am.fire(ActivityTrigger.FIELDS_COMPLETE, 3)
    am.fire(ActivityTrigger.CONFIRMED, 4)
    assert am.state == ActivityState.EXECUTING
    am.fire(ActivityTrigger.EXECUTED, 5)
    am.fire(ActivityTrigger.CLOSED, 6)
    assert am.terminal
    assert am.fire_if_possible(ActivityTrigger.OPENED, 7) is None


def test_inline_table_validation_reports_errors() -> None:
    bad: dict[str, dict[str, str]] = {ActivityState.OPENING: {"opened": "NOWHERE"}}
    errs = validate_table(bad)
    assert errs and any("NOWHERE" in e for e in errs)


# ---------------------------------------------------------------- Context: focus stack + objectives


def test_entity_focus_stack() -> None:
    fs = EntityFocusStack(max_depth=3)
    assert fs.current() is None and not fs.is_ambiguous()
    fs.push("e1", "item", 1, source="user")
    fs.push("e2", "item", 2, source="user")
    fs.push("p1", "person", 3, source="tool")
    assert fs.current().entity_id == "p1"  # type: ignore[union-attr]
    assert fs.current("item").entity_id == "e2"  # type: ignore[union-attr]
    assert fs.nth(2, "item").entity_id == "e1"  # type: ignore[union-attr]  # 1-based: 'the second one'
    assert fs.nth(3, "item") is None
    assert fs.is_ambiguous("item")
    assert not fs.is_ambiguous("person")
    fs.push("e3", "item", 4, source="user")  # depth cap evicts oldest
    assert len(fs.candidates()) == 3
    fs.clear()
    assert fs.current() is None


def test_pending_objectives_priority_and_exhaustion() -> None:
    po = PendingObjectives(max_attempts=2)
    po.add(ObjectiveKind.COLLECT_FIELD, "alpha", priority=5, ts_ms=1)
    po.add(ObjectiveKind.ANSWER_QUESTION, "q1", priority=1, ts_ms=2)
    assert len(po) == 2
    assert po.peek().ref == "q1"  # type: ignore[union-attr]
    po.attempt()
    po.attempt()
    assert [o.ref for o in po.exhausted()] == ["q1"]
    assert po.complete(ObjectiveKind.ANSWER_QUESTION, "q1")
    assert not po.has(ObjectiveKind.ANSWER_QUESTION)
    assert po.has(ObjectiveKind.COLLECT_FIELD, "alpha")
    assert po.snapshot()[0][1] == "alpha"


# ---------------------------------------------------------------- Governance (QV-ACC-008)


def _policies() -> PolicyBlock:
    return PolicyBlock(
        allowed_claims=[
            ClaimRule(claim_type="availability", source_requirement="TOOL_VERIFIED"),
            ClaimRule(claim_type="hours", source_requirement="ANY_APPROVED"),
            ClaimRule(claim_type="greeting"),
        ],
        prohibited_claims=[ClaimRule(claim_type="legal_advice")],
        unknown_question_policy=UnknownQuestionPolicy(
            default=Behavior.STATE_LIMITATION,
            overrides=[BehaviorOverride(topic_pattern="price", behavior=Behavior.COLLECT_QUESTION)],
        ),
        uncertainty_policy=UncertaintyPolicy(
            missing=Behavior.ASK_OPERATOR_SOURCE,
            conflicting=Behavior.OFFER_HUMAN_HANDOFF,
            stale=Behavior.STATE_LIMITATION,
            ambiguous=Behavior.ASK_CLARIFYING_QUESTION,
        ),
    )


async def test_claim_governor_blocks_unverified_and_prohibited() -> None:
    gov = ClaimGovernor(_policies(), RulesDecisionAdapter())
    ok = await gov.check("availability", Provenance.TOOL_VERIFIED, 1)
    assert ok.state == "allowed" and ok.action == "speak"

    weak = await gov.check("availability", Provenance.USER_STATED, 2)
    assert weak.state == "blocked" and weak.action == f"apply:{Behavior.STATE_LIMITATION.value}"

    unknown = await gov.check("hours", Provenance.UNVERIFIED, 3)
    assert unknown.action == f"apply:{Behavior.ASK_OPERATOR_SOURCE.value}"

    price = await gov.check("price_quote", Provenance.KNOWLEDGE_APPROVED, 4)
    assert price.state == "blocked" and price.action == f"apply:{Behavior.COLLECT_QUESTION.value}"

    bad = await gov.check("legal_advice", Provenance.TOOL_VERIFIED, 5)
    assert bad.state == "blocked" and bad.reason == "prohibited claim"

    approved = await gov.check("hours", Provenance.KNOWLEDGE_APPROVED, 6)
    assert approved.state == "allowed"
    assert gov.behavior_for_unknown_topic("what is the price?") is Behavior.COLLECT_QUESTION
    assert gov.behavior_for_unknown_topic("weather") is Behavior.STATE_LIMITATION
    assert [e.claim_type for e in gov.log] == [
        "availability",
        "availability",
        "hours",
        "price_quote",
        "legal_advice",
        "hours",
    ]


async def test_confirmation_interpreter_deterministic_and_ambiguous() -> None:
    ci = ConfirmationInterpreter(RulesDecisionAdapter(), yes_phrases=["tamam"], no_phrases=["la"])
    yes = await ci.interpret("tamam")
    assert yes.value is True and yes.source is DecisionSource.RULE and not yes.ambiguous
    no = await ci.interpret("la la")
    assert no.value is False and no.confidence >= 0.7
    amb = await ci.interpret("tamam la")
    assert amb.ambiguous and amb.source is DecisionSource.UNKNOWN and amb.value is None
    silent = await ci.interpret("hmm")
    assert silent.ambiguous


# ---------------------------------------------------------------- Tool pipeline (QV-ACC-009)

_SUBMIT = PlatformTool.SUBMIT_RECORD.value
_VERIFY = PlatformTool.VERIFY_FIELD.value
_CALLBACK = PlatformTool.SCHEDULE_CALLBACK.value
_RECORD = PlatformTool.RECORD_FIELD.value


def _decls() -> dict[str, ToolDeclaration]:
    return {
        _SUBMIT: ToolDeclaration(
            tool_id=_SUBMIT,
            description="submit",
            parameters={"type": "object", "required": ["fields"], "properties": {"fields": {"type": "object"}}},
            impact=ToolImpact.WRITE,
            confirmation="confirm_before_execute",
            idempotency_key_fields=["fields"],
        ),
        _VERIFY: ToolDeclaration(
            tool_id=_VERIFY,
            description="verify",
            parameters={"type": "object", "required": ["name", "value"], "properties": {"name": {"type": "string"}}},
            impact=ToolImpact.READ,
            timeout_ms=100,
        ),
        _CALLBACK: ToolDeclaration(
            tool_id=_CALLBACK,
            description="callback",
            parameters={"type": "object"},
            impact=ToolImpact.WRITE,
        ),
        _RECORD: ToolDeclaration(
            tool_id=_RECORD,
            description="record",
            parameters={"type": "object"},
            impact=ToolImpact.READ,  # declared read; permission below says write → impact mismatch
            result_provenance=Provenance.USER_STATED,
        ),
    }


def _tools_block() -> ToolsBlock:
    return ToolsBlock(
        required=[ToolRef(tool_id=_SUBMIT), ToolRef(tool_id=_VERIFY)],
        optional=[ToolRef(tool_id=_RECORD)],
        permissions={
            _SUBMIT: ToolPermission(impact="write", confirmation="confirm_before_execute"),
            _VERIFY: ToolPermission(impact="read"),
            _RECORD: ToolPermission(impact="write"),
        },
    )


class _Recorder:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    async def __call__(self, name: str, payload: dict[str, Any]) -> None:
        self.events.append((name, payload))

    def names(self) -> list[str]:
        return [str(n) for n, _ in self.events]


def _build(
    confirm_answer: bool | None, *, tenant_allowed: set[str] | None = None
) -> tuple[ToolPipeline, _Recorder, MemoryStore]:
    store = MemoryStore()
    rec = _Recorder()

    async def confirm(_inv: Any) -> bool | None:
        return confirm_answer

    pipe = ToolPipeline(
        declarations=_decls(),
        tools_block=_tools_block(),
        backends={tid: MemoryToolBackend(tid, store) for tid in (_SUBMIT, _VERIFY, _RECORD)},
        emit=rec,
        budget=BudgetGuard(max_calls=6, max_write_calls=2),
        confirm=confirm,
        tenant_allowed_tools=tenant_allowed,
    )
    return pipe, rec, store


_CTX: dict[str, Any] = {"session_id": "s1", "tenant_id": "ten1", "activity_id": "act1", "turn_id": "t1", "ts_ms": 1000}


async def test_tool_pipeline_all_gates() -> None:
    pipe, rec, store = _build(confirm_answer=True)

    # 1 unknown tool → REJECTED_ARGS at schema step
    out = await pipe.run(ToolCallRequest(call_id="c1", tool_id="nope", arguments={}), **_CTX)
    assert out.status is ToolOutcomeStatus.REJECTED_ARGS and out.step_reached is ToolPipelineStep.SCHEMA_VALIDATED

    # 2 invalid args (missing required)
    out = await pipe.run(ToolCallRequest(call_id="c2", tool_id=_SUBMIT, arguments={}), **_CTX)
    assert out.status is ToolOutcomeStatus.REJECTED_ARGS and "fields" in (out.error or "")

    # 3 declared but not permitted for the Activity → REJECTED_POLICY
    out = await pipe.run(ToolCallRequest(call_id="c3", tool_id=_CALLBACK, arguments={}), **_CTX)
    assert out.status is ToolOutcomeStatus.REJECTED_POLICY and out.step_reached is ToolPipelineStep.PERMISSION_CHECKED

    # 4 impact mismatch between declaration and permission → REJECTED_POLICY at policy step
    out = await pipe.run(ToolCallRequest(call_id="c4", tool_id=_RECORD, arguments={}), **_CTX)
    assert out.status is ToolOutcomeStatus.REJECTED_POLICY and out.step_reached is ToolPipelineStep.POLICY_CHECKED

    # 5 happy write with confirmation granted → COMPLETED, provenance TOOL_VERIFIED, record persisted
    args = {"fields": {"alpha": "x"}}
    out = await pipe.run(ToolCallRequest(call_id="c5", tool_id=_SUBMIT, arguments=args), **_CTX)
    assert out.status is ToolOutcomeStatus.COMPLETED and out.provenance is Provenance.TOOL_VERIFIED
    assert out.output["accepted"] is True and len(store.records) == 1
    assert "tool.confirmation_granted" in " ".join(rec.names()) or any("granted" in n for n in rec.names())

    # 6 identical write again → DUPLICATE, no second record
    out = await pipe.run(ToolCallRequest(call_id="c6", tool_id=_SUBMIT, arguments=args), **_CTX)
    assert out.status is ToolOutcomeStatus.DUPLICATE and out.step_reached is ToolPipelineStep.DEDUPLICATED
    assert len(store.records) == 1

    # 7 UNKNOWN result preserved — never upgraded to success
    store.unknown_next.add(_VERIFY)
    out = await pipe.run(ToolCallRequest(call_id="c7", tool_id=_VERIFY, arguments={"name": "a", "value": "1"}), **_CTX)
    assert out.status is ToolOutcomeStatus.UNKNOWN
    assert any("unknown" in n for n in rec.names())

    # 8 injected failure → FAILED
    store.fail_next.add(_VERIFY)
    out = await pipe.run(ToolCallRequest(call_id="c8", tool_id=_VERIFY, arguments={"name": "a", "value": "1"}), **_CTX)
    assert out.status is ToolOutcomeStatus.FAILED

    # 9 second distinct write ok (write budget = 2) …
    out = await pipe.run(ToolCallRequest(call_id="c9", tool_id=_SUBMIT, arguments={"fields": {"alpha": "y"}}), **_CTX)
    assert out.status is ToolOutcomeStatus.COMPLETED and len(store.records) == 2

    # 10 … third write exceeds the write budget → REJECTED_BUDGET + budget.exceeded event
    out = await pipe.run(ToolCallRequest(call_id="c10", tool_id=_SUBMIT, arguments={"fields": {"alpha": "z"}}), **_CTX)
    assert out.status is ToolOutcomeStatus.REJECTED_BUDGET and out.step_reached is ToolPipelineStep.BUDGET_CHECKED
    assert any("budget" in n for n in rec.names())

    # every outcome that reached a terminal step is in history; each has step_reached
    assert len(pipe.history) == 10
    assert all(o.step_reached for o in pipe.history)
    assert rec.names()[0] == "tool.requested" or rec.names()[0].endswith("requested")


async def test_tool_pipeline_confirmation_pending_and_denied() -> None:
    pipe, rec, store = _build(confirm_answer=None)
    args = {"fields": {"alpha": "x"}}
    pending = await pipe.run(ToolCallRequest(call_id="p1", tool_id=_SUBMIT, arguments=args), **_CTX)
    assert pending.status is ToolOutcomeStatus.CONFIRMATION_DENIED and pending.error == "confirmation pending"
    assert pending.step_reached is ToolPipelineStep.CONFIRMATION
    assert len(pipe.history) == 0  # non-terminal: not recorded, so the same call can be retried after the user answers
    assert store.records == []

    pipe2, rec2, store2 = _build(confirm_answer=False)
    denied = await pipe2.run(ToolCallRequest(call_id="d1", tool_id=_SUBMIT, arguments=args), **_CTX)
    assert denied.status is ToolOutcomeStatus.CONFIRMATION_DENIED and denied.error == "user denied"
    assert len(pipe2.history) == 1 and store2.records == []
    assert any("denied" in n for n in rec2.names())


async def test_tool_pipeline_tenant_scope_and_timeout() -> None:
    pipe, _rec, _store = _build(confirm_answer=True, tenant_allowed={_VERIFY})
    out = await pipe.run(ToolCallRequest(call_id="t1", tool_id=_SUBMIT, arguments={"fields": {}}), **_CTX)
    assert out.status is ToolOutcomeStatus.REJECTED_POLICY and "tenant" in (out.error or "")

    class _Slow:
        async def execute(self, inv: Any) -> Any:
            import asyncio

            await asyncio.sleep(1)

    pipe.backends[_VERIFY] = _Slow()  # type: ignore[assignment]
    out = await pipe.run(ToolCallRequest(call_id="t2", tool_id=_VERIFY, arguments={"name": "a", "value": "1"}), **_CTX)
    assert out.status is ToolOutcomeStatus.TIMEOUT and out.step_reached is ToolPipelineStep.EXECUTING


def test_validate_args_basic_schema() -> None:
    schema = {
        "type": "object",
        "required": ["name"],
        "properties": {"name": {"type": "string"}, "n": {"type": "integer"}},
    }
    assert validate_args(schema, {"name": "x", "n": 1}) == []
    assert validate_args(schema, {}) != []
    assert validate_args(schema, {"name": 5}) != []
