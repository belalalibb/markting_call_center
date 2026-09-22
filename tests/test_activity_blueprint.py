"""Blueprint fixtures validate (QV-ACT-006); domain rules enforced by contract; readiness transitions (QV-ACC-013)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from qevion.contracts.activity import ActivityBlueprint, ReadinessState
from qevion.contracts.control import READINESS_TRANSITIONS, can_transition


@pytest.mark.req("QV-ACT-006")
def test_example_blueprints_validate_and_roundtrip(example_blueprint_dicts: dict[str, dict]) -> None:
    assert example_blueprint_dicts, "no example blueprints found"
    for name, data in example_blueprint_dicts.items():
        bp = ActivityBlueprint.model_validate(data)
        dumped = bp.model_dump(mode="json", by_alias=True)
        assert ActivityBlueprint.model_validate(dumped) == bp, name


@pytest.mark.req("QV-ACT-002")
def test_example_c_has_no_unapproved_decisions(example_blueprint_dicts: dict[str, dict]) -> None:
    bp = ActivityBlueprint.model_validate(example_blueprint_dicts["activity_c_survey"])
    assert bp.unapproved_decisions() == []
    assert bp.direction == "outbound"
    assert bp.policies.contact_policy_hooks is not None


def test_outbound_requires_contact_hooks(example_blueprint_dicts: dict[str, dict]) -> None:
    data = dict(example_blueprint_dicts["activity_c_survey"])
    data["policies"] = {k: v for k, v in data["policies"].items() if k != "contact_policy_hooks"}
    with pytest.raises(ValidationError, match="contact_policy_hooks"):
        ActivityBlueprint.model_validate(data)


def test_tools_require_permission_entries(example_blueprint_dicts: dict[str, dict]) -> None:
    data = dict(example_blueprint_dicts["activity_c_survey"])
    data["tools"] = {**data["tools"], "permissions": {}}
    with pytest.raises(ValidationError, match="permissions"):
        ActivityBlueprint.model_validate(data)


@pytest.mark.req("QV-ACT-003")
def test_policies_require_unknown_and_uncertainty(example_blueprint_dicts: dict[str, dict]) -> None:
    data = dict(example_blueprint_dicts["activity_c_survey"])
    data["policies"] = {k: v for k, v in data["policies"].items() if k != "uncertainty_policy"}
    with pytest.raises(ValidationError):
        ActivityBlueprint.model_validate(data)


@pytest.mark.req("QV-ACC-013")
def test_readiness_illegal_transitions() -> None:
    assert not can_transition(ReadinessState.DRAFT, ReadinessState.ACTIVE)
    assert not can_transition(ReadinessState.RETIRED, ReadinessState.DRAFT)
    assert not can_transition(ReadinessState.NEEDS_INFORMATION, ReadinessState.ACTIVE)
    assert can_transition(ReadinessState.READY_FOR_ACTIVATION, ReadinessState.ACTIVE)
    assert can_transition(ReadinessState.ACTIVE, ReadinessState.SUSPENDED)
    # every state has an entry; every state except RETIRED can reach RETIRED
    assert set(READINESS_TRANSITIONS) == set(ReadinessState)
    for s in ReadinessState:
        if s is not ReadinessState.RETIRED:
            assert ReadinessState.RETIRED in READINESS_TRANSITIONS[s], s


def test_composition_configs_validate() -> None:
    from pathlib import Path

    import yaml
    from qevion.contracts.composition import Composition

    files = sorted((Path(__file__).resolve().parents[1] / "config" / "compositions").glob("*.yaml"))
    assert files
    for f in files:
        c = Composition.model_validate(yaml.safe_load(f.read_text()))
        assert c.composition_id == f.stem
