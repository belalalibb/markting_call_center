"""Latency option A (tool acknowledgement): off by default, reversible, content-free by instruction."""

from __future__ import annotations

import pytest
from qevion.core.instruction_composer import InstructionComposer
from qevion.main import _seed
from qevion.runtime.store import RuntimeStore, _instruction_options


def _bp():  # type: ignore[no-untyped-def]
    s = RuntimeStore()
    _seed(s)
    return next(r.blueprint for k, r in s.activities.items() if k.startswith("act_order_intake"))


def test_off_by_default_instructions_unchanged() -> None:
    bp = _bp()
    base = InstructionComposer(bp).compose()
    assert "tool_ack" not in base.sections
    assert InstructionComposer(bp, options=frozenset()).compose().fingerprint == base.fingerprint


def test_on_adds_content_free_ack_section_only() -> None:
    bp = _bp()
    base = InstructionComposer(bp).compose()
    on = InstructionComposer(bp, options=frozenset({"tool_ack"})).compose()
    ack = on.sections["tool_ack"]
    assert "NO facts" in ack and "recorded, confirmed" in ack and "after the tool results" in ack
    # every other section is byte-identical → the change is isolated to one section
    assert {k: v for k, v in on.sections.items() if k != "tool_ack"} == base.sections


def test_flag_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QEVION_TOOL_ACK", raising=False)
    assert _instruction_options({}) == frozenset()
    assert _instruction_options({"tool_ack": True}) == {"tool_ack"}
    monkeypatch.setenv("QEVION_TOOL_ACK", "0")
    assert _instruction_options({"tool_ack": True}) == frozenset()
    monkeypatch.setenv("QEVION_TOOL_ACK", "1")
    assert _instruction_options({}) == {"tool_ack"}
