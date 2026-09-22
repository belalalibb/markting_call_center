"""Capability Registry builder and requirement mapping (§16 QV-CAP-001..004).

The registry is *aggregated from adapters' own declarations* plus platform facts (tools, locale packs, voice
profiles, behaviors). Nothing here is a hand-written capability list: an adapter that does not declare a
capability is UNVERIFIED for it (QV-CAP-004 — a locale code is metadata, never proof).

`CapabilityMapper.map_requirements()` turns an Activity Blueprint's needs into `RequirementMapping` rows the
Copilot and Config Center show verbatim: requirement → required_capability → current_state → action.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from qevion.contracts.activity import ActivityBlueprint
from qevion.contracts.common import Channel
from qevion.contracts.composition import (
    AdapterCapabilities,
    Capability,
    CapabilityRegistry,
    CapabilityState,
    Composition,
    CompositionMode,
    MappingResult,
)
from qevion.contracts.policy import Behavior
from qevion.contracts.provider import ProviderRole
from qevion.contracts.tenant import LocalePack, VoiceProfile
from qevion.contracts.tool import ToolDeclaration


class _HasCapabilities(Protocol):
    def capabilities(self) -> AdapterCapabilities: ...


PLATFORM_ROLE = "platform"  # pseudo-adapter row for non-provider facts

_BLOCKING_ACTIONS = frozenset(
    {
        MappingResult.UNSUPPORTED,
        MappingResult.UNVERIFIED,
        MappingResult.REQUIRES_TOOL,
        MappingResult.REQUIRES_KNOWLEDGE,
        MappingResult.REQUIRES_HUMAN,
    }
)


def build_registry(
    adapters: list[_HasCapabilities],
    *,
    tool_declarations: dict[str, ToolDeclaration] | None = None,
    locale_packs: dict[str, LocalePack] | None = None,
    voice_profiles: dict[str, VoiceProfile] | None = None,
    channels: list[Channel] | None = None,
) -> CapabilityRegistry:
    """Aggregate adapter self-declarations + platform primitives into one machine-readable registry."""
    rows = [a.capabilities() for a in adapters]
    plat: list[Capability] = []
    for tid, d in (tool_declarations or {}).items():
        plat.append(Capability(name=f"tool:{tid}", state=CapabilityState.SUPPORTED, notes=f"impact={d.impact.value}"))
    for lp_id, lp in (locale_packs or {}).items():
        plat.append(Capability(name=f"locale_pack:{lp_id}", state=CapabilityState.SUPPORTED, notes=lp.locale))
    for vp_id, vp in (voice_profiles or {}).items():
        plat.append(
            Capability(
                name=f"voice_profile:{vp_id}",
                state=CapabilityState.SUPPORTED,
                notes="adapters=" + ",".join(sorted(vp.provider_voice_map)),
            )
        )
    for ch in channels or [Channel.TEXT, Channel.BROWSER_VOICE]:
        plat.append(Capability(name=f"channel:{ch.value}", state=CapabilityState.SUPPORTED))
    if not any(c.name == "channel:telephony" for c in plat):
        plat.append(
            Capability(name="channel:telephony", state=CapabilityState.PARTIAL, notes="simulated seam only (ADR-0003)")
        )
    for b in Behavior:
        plat.append(Capability(name=f"behavior:{b.value}", state=CapabilityState.SUPPORTED))
    rows.append(AdapterCapabilities(adapter=PLATFORM_ROLE, role=ProviderRole.DECISION, capabilities=plat))
    return CapabilityRegistry(adapters=rows)


@dataclass
class RequirementMapping:
    """QV-CAP-003 row."""

    requirement: str
    required_capability: str
    current_state: CapabilityState
    action: MappingResult
    provider: str | None = None
    note: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "requirement": self.requirement,
            "required_capability": self.required_capability,
            "current_state": self.current_state.value,
            "action": self.action.value,
            "provider": self.provider,
            "note": self.note,
        }


def _platform_state(reg: CapabilityRegistry, name: str) -> CapabilityState:
    plat = next((a for a in reg.adapters if a.adapter == PLATFORM_ROLE), None)
    return plat.state_of(name) if plat else CapabilityState.UNVERIFIED


def _result_for(state: CapabilityState, *, partial_ok: bool = True) -> MappingResult:
    match state:
        case CapabilityState.SUPPORTED:
            return MappingResult.SUPPORTED
        case CapabilityState.PARTIAL:
            return MappingResult.SUPPORTED_WITH_CONFIGURATION if partial_ok else MappingResult.UNSUPPORTED
        case CapabilityState.UNSUPPORTED:
            return MappingResult.UNSUPPORTED
        case _:
            return MappingResult.UNVERIFIED


_KNOWLEDGE_STATE = {
    "SATISFIED": CapabilityState.SUPPORTED,
    "PARTIAL": CapabilityState.PARTIAL,
    "MISSING": CapabilityState.UNSUPPORTED,
}


@dataclass
class CapabilityMapper:
    registry: CapabilityRegistry
    composition: Composition | None = None
    rows: list[RequirementMapping] = field(default_factory=list)

    def _provider_state(self, role: ProviderRole, cap: str) -> tuple[CapabilityState, str | None]:
        if self.composition is None:
            return CapabilityState.UNVERIFIED, None
        b = next((x for x in self.composition.bindings if x.role == role), None)
        if b is None:
            return CapabilityState.UNVERIFIED, None
        ac = self.registry.find(role, b.adapter)
        if ac is None:
            return CapabilityState.UNVERIFIED, b.adapter
        st = ac.state_of(cap)
        if st is CapabilityState.UNVERIFIED and cap.startswith("language:"):
            st = ac.state_of("language:any")
        return st, b.adapter

    def _add(
        self,
        req: str,
        cap: str,
        state: CapabilityState,
        action: MappingResult,
        provider: str | None = None,
        note: str | None = None,
    ) -> None:
        self.rows.append(RequirementMapping(req, cap, state, action, provider, note))

    def _tool_row(self, tool_id: str, purpose: str, *, optional: bool) -> None:
        st = _platform_state(self.registry, f"tool:{tool_id}")
        action = _result_for(st) if st is not CapabilityState.UNVERIFIED else MappingResult.REQUIRES_TOOL
        label = f"optional tool {tool_id}" if optional else f"tool {tool_id}: {purpose or 'required'}"
        self._add(label, f"tool:{tool_id}", st, action, note="optional" if optional else None)

    def map_requirements(self, bp: ActivityBlueprint) -> list[RequirementMapping]:
        self.rows = []
        voice = any(ch in (Channel.BROWSER_VOICE, Channel.TELEPHONY) for ch in bp.channels)
        s2s = self.composition is None or self.composition.mode is CompositionMode.S2S
        speak_role = ProviderRole.S2S if s2s else ProviderRole.TTS
        hear_role = ProviderRole.S2S if s2s else ProviderRole.ASR
        think_role = ProviderRole.S2S if s2s else ProviderRole.LLM

        for ch in bp.channels:
            st = _platform_state(self.registry, f"channel:{ch.value}")
            self._add(f"channel {ch.value}", f"channel:{ch.value}", st, _result_for(st))

        lang = f"language:{bp.locale.locale}"
        dialect = f" ({bp.locale.dialect})" if bp.locale.dialect else ""
        for role in sorted({hear_role, speak_role}, key=lambda r: r.value):
            st, prov = self._provider_state(role, lang)
            self._add(f"{role.value}: understand/speak {bp.locale.locale}{dialect}", lang, st, _result_for(st), prov)

        if voice:
            for cap in ("audio:pcm16_24k", "feature:barge_in"):
                st, prov = self._provider_state(speak_role, cap)
                self._add(f"voice: {cap.split(':', 1)[1]}", cap, st, _result_for(st), prov)
            for cap in ("feature:barge_in", "feature:end_of_turn"):
                st, prov = self._provider_state(ProviderRole.TURN, cap)
                self._add(f"turn plane: {cap.split(':', 1)[1]}", cap, st, _result_for(st), prov)

        if bp.tools.required or bp.tools.optional:
            st, prov = self._provider_state(think_role, "feature:tool_calls")
            self._add("model can call tools", "feature:tool_calls", st, _result_for(st, partial_ok=False), prov)
        for ref in bp.tools.required:
            self._tool_row(ref.tool_id, ref.purpose, optional=False)
        for ref in bp.tools.optional:
            self._tool_row(ref.tool_id, ref.purpose, optional=True)

        for kr in bp.knowledge.requirements:
            st = _KNOWLEDGE_STATE[kr.status]
            action = MappingResult.SUPPORTED if kr.status == "SATISFIED" else MappingResult.REQUIRES_KNOWLEDGE
            self._add(f"knowledge: {kr.domain}", f"knowledge:{kr.domain}", st, action, note=kr.description or None)

        uqp, up = bp.policies.unknown_question_policy, bp.policies.uncertainty_policy
        behaviors = {
            uqp.default,
            *(o.behavior for o in uqp.overrides),
            up.missing,
            up.conflicting,
            up.stale,
            up.ambiguous,
        }
        for b in sorted(behaviors, key=lambda x: x.value):
            st = _platform_state(self.registry, f"behavior:{b.value}")
            self._add(f"behavior {b.value}", f"behavior:{b.value}", st, _result_for(st))
        if Behavior.OFFER_HUMAN_HANDOFF in behaviors or bp.handoff_rules:
            has_path = bool(bp.handoff_rules) and "request_handoff" in bp.tools.permissions
            self._add(
                "human handoff path",
                "handoff:destination",
                CapabilityState.SUPPORTED if has_path else CapabilityState.UNSUPPORTED,
                MappingResult.SUPPORTED if has_path else MappingResult.REQUIRES_HUMAN,
                note=None if has_path else "declare request_handoff + handoff_rules destination_ref",
            )

        lp_ref = bp.locale.locale_pack_ref or bp.version_metadata.pinned.locale_pack
        if lp_ref:
            st = _platform_state(self.registry, f"locale_pack:{lp_ref}")
            self._add(f"locale pack {lp_ref}", f"locale_pack:{lp_ref}", st, _result_for(st))
        vp_ref = bp.locale.voice_profile_ref or bp.version_metadata.pinned.voice_profile
        if voice and vp_ref:
            st = _platform_state(self.registry, f"voice_profile:{vp_ref}")
            self._add(f"voice profile {vp_ref}", f"voice_profile:{vp_ref}", st, _result_for(st))
        return self.rows

    def summary(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for r in self.rows:
            out[r.action.value] = out.get(r.action.value, 0) + 1
        return out

    def blocking(self) -> list[RequirementMapping]:
        return [r for r in self.rows if r.action in _BLOCKING_ACTIONS and r.note != "optional"]


__all__ = ["PLATFORM_ROLE", "CapabilityMapper", "RequirementMapping", "build_registry"]
