"""`qevion.composition.v1` (§33 QV-COMP) and `qevion.capability_registry.v1` (§16 QV-CAP)."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from qevion.contracts.common import QevionModel
from qevion.contracts.provider import ProviderRole, TurnDetectorConfig


class CompositionMode(StrEnum):
    S2S = "s2s"
    CASCADE = "cascade"


class AdapterBinding(QevionModel):
    role: ProviderRole
    adapter: str = Field(description="registered adapter name, e.g. openai_realtime, mock, silero")
    model: str | None = None
    config: dict[str, str | int | float | bool] = Field(default_factory=dict)


class Composition(QevionModel):
    """Which adapter fills each role. Pinned by the Blueprint (`version_metadata.pinned.composition_config`)."""

    schema_: Literal["qevion.composition.v1"] = Field(default="qevion.composition.v1", alias="schema")
    composition_id: str
    mode: CompositionMode
    bindings: list[AdapterBinding]
    turn: TurnDetectorConfig = Field(default_factory=TurnDetectorConfig)

    @model_validator(mode="after")
    def _roles_complete(self) -> Composition:
        roles = {b.role for b in self.bindings}
        if len(roles) != len(self.bindings):
            raise ValueError("duplicate role binding")
        need = (
            {ProviderRole.S2S}
            if self.mode == CompositionMode.S2S
            else {ProviderRole.ASR, ProviderRole.LLM, ProviderRole.TTS}
        )
        need |= {ProviderRole.TURN, ProviderRole.DECISION}
        missing = sorted(r.value for r in need - roles)
        if missing:
            raise ValueError(f"composition mode {self.mode} missing roles: {missing}")
        return self

    def binding(self, role: ProviderRole) -> AdapterBinding:
        return next(b for b in self.bindings if b.role == role)


# ---- capability registry ------------------------------------------------------


class CapabilityState(StrEnum):
    SUPPORTED = "SUPPORTED"
    PARTIAL = "PARTIAL"
    UNSUPPORTED = "UNSUPPORTED"
    UNVERIFIED = "UNVERIFIED"


class Capability(QevionModel):
    name: str = Field(description="e.g. language:ar-EG, feature:barge_in, feature:tool_calls, audio:pcm16_24k")
    state: CapabilityState
    evidence_ref: str | None = None
    notes: str | None = None


class AdapterCapabilities(QevionModel):
    adapter: str
    role: ProviderRole
    capabilities: list[Capability]

    def state_of(self, name: str) -> CapabilityState:
        for c in self.capabilities:
            if c.name == name:
                return c.state
        return CapabilityState.UNVERIFIED


class CapabilityRegistry(QevionModel):
    schema_: Literal["qevion.capability_registry.v1"] = Field(default="qevion.capability_registry.v1", alias="schema")
    adapters: list[AdapterCapabilities]

    def find(self, role: ProviderRole, adapter: str) -> AdapterCapabilities | None:
        return next((a for a in self.adapters if a.role == role and a.adapter == adapter), None)


class MappingResult(StrEnum):
    """Copilot capability-mapping outcomes (§16)."""

    SUPPORTED = "SUPPORTED"
    SUPPORTED_WITH_CONFIGURATION = "SUPPORTED_WITH_CONFIGURATION"
    REQUIRES_TOOL = "REQUIRES_TOOL"
    REQUIRES_KNOWLEDGE = "REQUIRES_KNOWLEDGE"
    REQUIRES_HUMAN = "REQUIRES_HUMAN"
    UNSUPPORTED = "UNSUPPORTED"
    UNVERIFIED = "UNVERIFIED"
