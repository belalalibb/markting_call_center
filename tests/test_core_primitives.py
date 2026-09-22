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
    assert dm.state is DialogState.IDLE
    dm.fire("session_started", 1)
    dm.fire("end_of_turn", 2)
    assert dm.state is DialogState.THINKING
    dm.fire("tool_requested", 3)
    dm.fire("tool_returned", 4)
    dm.fire("response_started", 5)
    assert dm.state is DialogState.SPEAKING
    t = dm.fire("barge_in", 6, reason="user spoke")
    assert t.to_state is DialogState.INTERRUPTED and t.reason == "user spoke" and t.authority == "core"
    dm.fire("reconciled", 7)
    assert dm.state is DialogState.LISTENING
    assert not dm.can("response_done")
    with pytest.raises(IllegalTransitionError):
        dm.fire("response_done", 8)
    dm.fire("close", 9)
    assert dm.state is DialogState.CLOSED and not dm.can("session_started")


# ---------------------------------------------------------------- Activity machine (data-driven)


def test_generic_table_is_valid_and_terminal_states_absorb() -> None:
    assert validate_table(GENERIC_DEFAULT_V1) == []
    am = ActivityMachine.from_blueprint_ref("generic_default_v1", None)
    am.fire(ActivityTrigger.OPENED, 1)
    am.fire(ActivityTrigger.FIELD_NEEDED, 2)
    assert am.state is ActivityState.COLLECTING
    am.fire(ActivityTrigger.FIELDS_COMPLETE, 3)
    am.fire(ActivityTrigger.CONFIRMED, 4)
    assert am.state is ActivityState.EXECUTING
    am.fire(ActivityTrigger.EXECUTED, 5)
    am.fire(ActivityTrigger.CLOSED, 6)
    assert am.terminal
    assert am.fire_if_possible(ActivityTrigger.OPENED, 7) is None


def test_inline_table_validation_reports_errors() -> None:
    bad: dict[str, dict[str, str]] = {ActivityState.OPENING: {"opened": "NOWHERE"}}
    errs = validate_table(bad)
    assert errs and any("NOWHERE" in e for e in errs)


# --- part 2 ---
