"""Readiness lifecycle (§10, QV-ACC-013) and Capability Registry / mapping (§16 QV-CAP)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from qevion.adapters.decision.rules import RulesDecisionAdapter
from qevion.adapters.providers.mocks import MockS2SAdapter
from qevion.adapters.turn.energy import MockTurnAdapter
from qevion.contracts.activity import ActivityBlueprint
from qevion.contracts.activity import ReadinessState as S
from qevion.contracts.composition import CapabilityRegistry, CapabilityState, Composition, MappingResult
from qevion.contracts.control import (
    READINESS_TRANSITIONS,
    PreflightFinding,
    PreflightReason,
    PreflightResult,
)
from qevion.contracts.event import EventType
from qevion.contracts.tenant import LocalePack, VoiceProfile
from qevion.control.capabilities import PLATFORM_ROLE, CapabilityMapper, build_registry
from qevion.control.preflight import Preflight, PreflightContext
from qevion.control.readiness import ActivationGates, IllegalReadinessTransitionError, ReadinessMachine
from qevion.core.platform_tools import platform_declarations

ROOT = Path(__file__).resolve().parents[1]


def _bp(name: str) -> ActivityBlueprint:
    return ActivityBlueprint.model_validate(yaml.safe_load((ROOT / "config/examples" / f"{name}.yaml").read_text()))


def _comp() -> Composition:
    return Composition.model_validate(yaml.safe_load((ROOT / "config/compositions/comp_mock_s2s_v1.yaml").read_text()))


def _ready(bp: ActivityBlueprint) -> PreflightResult:
    return PreflightResult(activity_id=bp.identity.activity_id, activity_version=bp.identity.version, status="READY")


def _blocked(bp: ActivityBlueprint, *reasons: PreflightReason) -> PreflightResult:
    return PreflightResult(
        activity_id=bp.identity.activity_id,
        activity_version=bp.identity.version,
        status="BLOCKED",
        findings=[PreflightFinding(reason=r, path="x", message="seeded") for r in reasons],
    )


# ---------------------------------------------------------------- readiness (QV-ACC-013)


@pytest.mark.parametrize("dst", [S.ACTIVE, S.READY_FOR_ACTIVATION, S.READY_FOR_SIMULATION, S.SUSPENDED])
def test_illegal_transitions_from_draft_are_rejected(dst: S) -> None:
    m = ReadinessMachine.from_blueprint(_bp("activity_a_restaurant"))
    assert m.state is S.DRAFT
    with pytest.raises(IllegalReadinessTransitionError):
        m.transition(dst, reason="chat said so", actor="operator:x")
    assert m.state is S.DRAFT and not m.history


def test_transition_table_is_closed_and_retired_is_terminal() -> None:
    for src, dsts in READINESS_TRANSITIONS.items():
        m = ReadinessMachine("a", "1.0.0", src)
        for dst in S:
            assert m.can(dst) == (dst in dsts)
    assert READINESS_TRANSITIONS[S.RETIRED] == frozenset()


def test_full_lifecycle_happy_path_emits_control_authored_changes() -> None:
    bp = _bp("activity_a_restaurant")
    m = ReadinessMachine.from_blueprint(bp)
    ch = m.apply_preflight(_ready(bp), ref="pf://1")
    assert ch is not None and m.state is S.READY_FOR_SIMULATION
    # DRAFT could not jump directly; machine walked a legal path and recorded every hop
    assert [c.to_state for c in m.history][-1] is S.READY_FOR_SIMULATION
    assert all(c.actor.startswith("control:") for c in m.history)
    assert all(c.event_type == EventType.ACTIVITY_READINESS_CHANGED for c in m.history)
    assert m.history[-1].payload()["preflight_result_ref"] == "pf://1"

    m.apply_simulation(False, ref="sim://1")
    assert m.state is S.SIMULATION_FAILED
    m.transition(S.READY_FOR_SIMULATION, reason="fixed", actor="operator:o1")
    m.apply_simulation(True, ref="sim://2")
    assert m.state is S.READY_FOR_ACTIVATION

    # ACTIVE requires every gate (QV-LIFE-002)
    gates = ActivationGates(
        schema_valid=True, preflight=_ready(bp), simulation_passed=True, all_decisions_approved=True
    )
    with pytest.raises(IllegalReadinessTransitionError, match="version_frozen"):
        m.activate(gates, actor="operator:o1")
    with pytest.raises(IllegalReadinessTransitionError):
        m.transition(S.ACTIVE, reason="shortcut", actor="operator:o1")  # no gate proof → never
    gates.version_frozen = True
    m.activate(gates, actor="operator:o1", preflight_ref="pf://1", simulation_ref="sim://2")
    assert m.state is S.ACTIVE and m.accepts_new_sessions
    assert m.history[-1].refs == {"preflight_result_ref": "pf://1", "simulation_report_ref": "sim://2"}

    # approved versions are immutable (QV-LIFE-004)
    with pytest.raises(IllegalReadinessTransitionError, match="immutable"):
        m.edited(actor="operator:o1", what="tools")
    m.suspend(actor="operator:o1", reason="budget")
    assert m.state is S.SUSPENDED and not m.accepts_new_sessions
    m.activate(ActivationGates(), actor="operator:o1")  # resume from SUSPENDED needs no re-proof
    assert m.state is S.ACTIVE
    m.retire(actor="operator:o1", reason="replaced by 1.1.0")
    assert m.state is S.RETIRED and not m.can(S.ACTIVE)


def test_blocked_preflight_routes_to_needs_information_or_blocked() -> None:
    bp = _bp("activity_a_restaurant")
    m = ReadinessMachine.from_blueprint(bp)
    m.apply_preflight(_blocked(bp, PreflightReason.MISSING_REQUIRED_KNOWLEDGE), ref="pf://k")
    assert m.state is S.NEEDS_INFORMATION  # information the owner must supply
    m.apply_preflight(_blocked(bp, PreflightReason.UNSUPPORTED_CAPABILITY), ref="pf://c")
    assert m.state is S.BLOCKED  # configuration/capability problem
    assert m.apply_preflight(_blocked(bp, PreflightReason.UNSUPPORTED_CAPABILITY), ref="pf://c") is None  # idempotent
    with pytest.raises(IllegalReadinessTransitionError):
        m.transition(S.READY_FOR_SIMULATION, reason="nope", actor="operator:x")  # BLOCKED must go via configuration


def test_edit_after_ready_returns_to_needs_configuration() -> None:
    bp = _bp("activity_a_restaurant")
    m = ReadinessMachine.from_blueprint(bp)
    m.apply_preflight(_ready(bp), ref="pf://1")
    m.apply_simulation(True, ref="sim://1")
    assert m.state is S.READY_FOR_ACTIVATION
    ch = m.edited(actor="operator:o1", what="policies.allowed_claims")
    assert ch is not None and m.state is S.NEEDS_CONFIGURATION and "edited" in ch.reason
    assert m.edited(actor="operator:o1", what="again") is None  # already in an editable state


def test_real_preflight_drives_machine_on_example_blueprints() -> None:
    comp = _comp()
    reg = build_registry(
        [MockS2SAdapter(), MockTurnAdapter(), RulesDecisionAdapter()], tool_declarations=platform_declarations()
    )
    ctx = PreflightContext(
        registry=reg,
        composition=comp,
        tool_declarations=platform_declarations(),
        locale_packs={"lp_ar_eg_v1": LocalePack(locale_pack_id="lp_ar_eg_v1", language="ar", locale="ar-EG")},
        voice_profiles={
            v: VoiceProfile(voice_profile_id=v, display_name=v, provider_voice_map={"mock": "v"})
            for v in ("vp_warm_female_v1", "vp_professional_male_v1", "vp_neutral_v1")
        },
    )
    for name in ("activity_a_restaurant", "activity_b_clinic", "activity_c_survey"):
        bp = _bp(name)
        m = ReadinessMachine.from_blueprint(bp)
        res = Preflight(ctx).run(bp)
        m.apply_preflight(res, ref=f"pf://{name}")
        assert m.state is S.READY_FOR_SIMULATION, (name, [(f.reason, f.message) for f in res.blocking])


# ---------------------------------------------------------------- capability registry + mapping (QV-CAP)


def _registry() -> CapabilityRegistry:
    return build_registry(
        [MockS2SAdapter(), MockTurnAdapter(), RulesDecisionAdapter()],
        tool_declarations=platform_declarations(),
        locale_packs={"lp_ar_eg_v1": LocalePack(locale_pack_id="lp_ar_eg_v1", language="ar", locale="ar-EG")},
        voice_profiles={
            "vp_warm_female_v1": VoiceProfile(
                voice_profile_id="vp_warm_female_v1", display_name="w", provider_voice_map={"mock": "v"}
            )
        },
    )


def test_registry_aggregates_adapters_and_platform_facts_and_round_trips() -> None:
    reg = _registry()
    assert {a.adapter for a in reg.adapters} == {"mock", "rules", PLATFORM_ROLE}
    plat = next(a for a in reg.adapters if a.adapter == PLATFORM_ROLE)
    names = {c.name for c in plat.capabilities}
    assert {
        "tool:record_field",
        "tool:submit_record",
        "locale_pack:lp_ar_eg_v1",
        "voice_profile:vp_warm_female_v1",
    } <= names
    assert plat.state_of("channel:telephony") is CapabilityState.PARTIAL  # seam only, never claimed SUPPORTED
    assert plat.state_of("behavior:OFFER_HUMAN_HANDOFF") is CapabilityState.SUPPORTED
    assert plat.state_of("tool:not_registered") is CapabilityState.UNVERIFIED  # absence == UNVERIFIED (QV-CAP-004)
    assert CapabilityRegistry.model_validate(reg.model_dump(mode="json", by_alias=True)) == reg


def test_mapping_activity_a_is_fully_supported_on_mocks() -> None:
    mapper = CapabilityMapper(_registry(), _comp())
    rows = mapper.map_requirements(_bp("activity_a_restaurant"))
    assert rows and not mapper.blocking(), [r.as_dict() for r in mapper.blocking()]
    caps = {r.required_capability for r in rows}
    assert {
        "language:ar-EG",
        "feature:tool_calls",
        "tool:compute_quote",
        "behavior:STATE_LIMITATION",
        "handoff:destination",
    } <= caps
    assert mapper.summary()[MappingResult.SUPPORTED.value] >= 10
    # every row is a complete QV-CAP-003 tuple
    for r in rows:
        d = r.as_dict()
        assert d["requirement"] and d["required_capability"] and d["current_state"] and d["action"]


def test_mapping_reports_requires_tool_knowledge_human_and_unverified() -> None:
    reg = build_registry([MockTurnAdapter(), RulesDecisionAdapter()])  # no s2s adapter, no tools registered
    bp = _bp("activity_b_clinic")
    mapper = CapabilityMapper(reg, _comp())
    mapper.map_requirements(bp)
    actions = {r.required_capability: r.action for r in mapper.rows}
    assert actions["language:ar-EG"] is MappingResult.UNVERIFIED  # adapter absent → never assumed
    assert actions["tool:submit_record"] is MappingResult.REQUIRES_TOOL
    assert actions["knowledge:visit_preparation"] is MappingResult.REQUIRES_KNOWLEDGE  # PARTIAL
    assert actions["handoff:destination"] is MappingResult.SUPPORTED
    blocking = {r.required_capability for r in mapper.blocking()}
    assert "tool:collect_question" not in blocking  # optional tools never block
    assert {"language:ar-EG", "tool:submit_record", "knowledge:visit_preparation"} <= blocking


def test_mapping_without_composition_is_unverified_not_supported() -> None:
    mapper = CapabilityMapper(_registry(), None)
    mapper.map_requirements(_bp("activity_c_survey"))
    assert all(
        r.action is MappingResult.UNVERIFIED for r in mapper.rows if r.required_capability.startswith("language:")
    )
