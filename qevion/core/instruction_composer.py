"""Instruction composer — renders provider-neutral instructions from a Blueprint (QV-ACT-001, QV-LANG-004/005).

Design constraints:
* Pure function of (Blueprint, LocalePack?, VoiceProfile?, runtime snapshot). Regenerable at any time; the rendered
  text is never the source of truth and is never edited by hand.
* Contains **no business vocabulary**. Every domain word comes from the Blueprint / Locale Pack / Voice Profile.
* The prose is deliberately terse, sectioned and stable so diffs are reviewable and instruction drift is detectable
  (`fingerprint()`).
* Governance is restated to the model as *behavioural constraints*, but enforcement remains in Core
  (ClaimGovernor, ToolPipeline). The model is told what it may not do; the Core makes sure of it.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from qevion.contracts.activity import ActivityBlueprint, FieldSpec
from qevion.contracts.common import Provenance
from qevion.contracts.control import ActivityState
from qevion.contracts.policy import Behavior
from qevion.contracts.tenant import LocalePack, VoiceProfile
from qevion.contracts.tool import ToolDeclaration

# Behaviour → neutral instruction phrasing. Generic platform semantics, not business content.
_BEHAVIOR_TEXT: dict[Behavior, str] = {
    Behavior.ANSWER_FROM_APPROVED_KNOWLEDGE: "answer only from approved knowledge returned by tools",
    Behavior.ASK_CLARIFYING_QUESTION: "ask one short clarifying question",
    Behavior.STATE_LIMITATION: "say plainly that you do not have that information",
    Behavior.USE_AUTHORIZED_TOOL: "use an authorized tool to find out",
    Behavior.ASK_OPERATOR_SOURCE: "say you will need to check and do not guess",
    Behavior.OFFER_HUMAN_HANDOFF: "offer to connect the user to a person",
    Behavior.COLLECT_QUESTION: "note the question for follow-up and say so",
    Behavior.REQUEST_ADDITIONAL_INFORMATION: "ask for the missing detail",
    Behavior.CLOSE_GRACEFULLY: "close the conversation politely",
    Behavior.DECLINE_UNSUPPORTED_REQUEST: "decline politely and say what you can help with",
}


@dataclass
class RuntimeSnapshot:
    """The small, changing part. Everything else is static per Blueprint version."""

    activity_state: ActivityState = ActivityState.OPENING
    missing_required: list[str] = field(default_factory=list)
    unsatisfied: list[tuple[str, Provenance]] = field(default_factory=list)  # (field, required provenance)
    focus_ambiguous: bool = False
    pending_confirmation: str | None = None  # tool_id awaiting user confirmation
    extra_notes: list[str] = field(default_factory=list)  # Core-derived, e.g. after interruption reconciliation


@dataclass
class ComposedInstructions:
    text: str
    sections: dict[str, str]
    fingerprint: str
    static_fingerprint: str  # excludes runtime snapshot → detects Blueprint-level drift only


def _field_line(f: FieldSpec) -> str:
    parts = [f"- {f.name} ({f.type}"]
    if f.enum_values:
        parts.append(f"; one of {', '.join(f.enum_values)}")
    parts.append(")")
    if f.clarification_hint:
        parts.append(f" — {f.clarification_hint}")
    if f.provenance_required in (Provenance.TOOL_VERIFIED, Provenance.KNOWLEDGE_APPROVED):
        parts.append(" [must be verified by a tool before it counts]")
    return "".join(parts)


def _tool_line(d: ToolDeclaration, confirmation: str) -> str:
    conf = " — ask the user to confirm before calling" if confirmation == "confirm_before_execute" else ""
    return f"- {d.tool_id}: {d.description} [{d.impact.value}]{conf}"


@dataclass
class InstructionComposer:
    blueprint: ActivityBlueprint
    tool_declarations: dict[str, ToolDeclaration] = field(default_factory=dict)
    locale_pack: LocalePack | None = None
    voice_profile: VoiceProfile | None = None

    # ------------------------------------------------------------------ static sections
    def _role(self) -> str:
        bp = self.blueprint
        lines = [
            f"You are the voice assistant for '{bp.identity.name}'.",
            f"Goal: {bp.objective.primary.description or bp.objective.primary.kind}.",
        ]
        for s in bp.objective.secondary:
            lines.append(f"Also: {s.description or s.kind}.")
        if bp.identity.description:
            lines.append(bp.identity.description)
        return "\n".join(lines)

    def _language(self) -> str:
        bp = self.blueprint
        loc = bp.locale
        lines = [f"Speak {loc.language} ({loc.locale}{', ' + loc.dialect if loc.dialect else ''})."]
        if self.locale_pack:
            lp = self.locale_pack
            lines.append(f"Register: {lp.speech_register}. Numbers: {lp.number_style.replace('_', ' ')}.")
            if lp.filler_policy == "none":
                lines.append("Do not use filler words.")
            if lp.lexicon:
                lines.append("Pronunciation: " + "; ".join(f"{e.term} → {e.pronunciation}" for e in lp.lexicon))
        if self.voice_profile and self.voice_profile.persona_notes:
            lines.append(f"Persona: {self.voice_profile.persona_notes}")
        if loc.pronunciation:
            lines.append("Say these terms as: " + "; ".join(f"{p.term} → {p.hint}" for p in loc.pronunciation))
        lines.append("Keep turns short (one idea per turn). Stop speaking immediately when the user talks.")
        return "\n".join(lines)

    def _data(self) -> str:
        d = self.blueprint.data
        if not d.required and not d.optional:
            return ""
        lines = ["Collect these details, one at a time, and repeat back what you heard:"]
        lines += [_field_line(f) for f in d.required]
        if d.optional:
            lines.append("Optional if the user offers them:")
            lines += [_field_line(f) for f in d.optional]
        return "\n".join(lines)

    def _tools(self) -> str:
        tb = self.blueprint.tools
        refs = [*tb.required, *tb.optional]
        if not refs:
            return ""
        lines = ["Tools you may call (the system validates every call; a call may be rejected):"]
        for r in refs:
            decl = self.tool_declarations.get(r.tool_id)
            perm = tb.permissions[r.tool_id]
            if decl:
                lines.append(_tool_line(decl, perm.confirmation))
            else:
                lines.append(f"- {r.tool_id}: {r.purpose or 'see declaration'} [{perm.impact}]")
        lines.append("Never claim an action succeeded unless the tool result says so. If a result is unknown, say so.")
        return "\n".join(lines)

    def _truth(self) -> str:
        p = self.blueprint.policies
        lines = ["Truthfulness rules:"]
        if p.allowed_claims:
            lines.append(
                "You may state facts about: "
                + ", ".join(f"{c.claim_type}" + (f" (only when {c.source_requirement})" if c.source_requirement else "")
                            for c in p.allowed_claims)
                + "."
            )
        if p.prohibited_claims:
            lines.append("Never make statements about: " + ", ".join(c.claim_type for c in p.prohibited_claims) + ".")
        uq = p.unknown_question_policy
        lines.append(f"If asked something you cannot answer from approved sources: {_BEHAVIOR_TEXT[uq.default]}.")
        for o in uq.overrides:
            lines.append(f"  - about '{o.topic_pattern}': {_BEHAVIOR_TEXT[o.behavior]}.")
        up = p.uncertainty_policy
        lines.append(f"If information is missing: {_BEHAVIOR_TEXT[up.missing]}.")
        lines.append(f"If sources conflict: {_BEHAVIOR_TEXT[up.conflicting]}.")
        lines.append(f"If the user is ambiguous: {_BEHAVIOR_TEXT[up.ambiguous]}.")
        ob = self.blueprint.objective.optimization_bounds
        if ob.no_invented_urgency:
            lines.append("Never invent urgency, scarcity or deadlines.")
        if ob.respect_opt_out:
            lines.append("If the user asks to stop or opt out, comply immediately and close politely.")
        return "\n".join(lines)

    def _coverage(self) -> str:
        cov = self.blueprint.coverage
        covered = [q for q in cov.questions if q.status == "COVERED"]
        declined = [q for q in cov.questions if q.status == "DECLINED"]
        if not covered and not declined and not cov.objections:
            return ""
        lines = ["Known question handling:"]
        for q in covered:
            lines.append(f"- '{q.pattern}': handle via {q.handling.lower()}" + (f" ({q.answer_ref})" if q.answer_ref else ""))
        for q in declined:
            lines.append(f"- '{q.pattern}': do not answer; {_BEHAVIOR_TEXT[Behavior.DECLINE_UNSUPPORTED_REQUEST]}")
        for ob in cov.objections:
            lines.append(f"- objection '{ob.pattern}': {ob.response_ref}")
        return "\n".join(lines)

    def _disclosures(self) -> str:
        ds = self.blueprint.policies.disclosures
        if not ds:
            return ""
        return "Required disclosures:\n" + "\n".join(f"- at {d.when}: read {d.text_ref}" for d in ds)

    def _flow(self) -> str:
        cf = self.blueprint.constrained_flow
        if not cf or not cf.enabled or not cf.steps:
            return ""
        return "Follow this order strictly:\n" + "\n".join(f"{i + 1}. {s}" for i, s in enumerate(cf.steps))

    # ------------------------------------------------------------------ runtime section
    def _runtime(self, snap: RuntimeSnapshot) -> str:
        lines = [f"Current stage: {snap.activity_state.value}."]
        if snap.missing_required:
            lines.append("Still needed: " + ", ".join(snap.missing_required) + ".")
        for name, need in snap.unsatisfied:
            lines.append(f"'{name}' is recorded but not yet {need.value}; do not treat it as confirmed.")
        if snap.focus_ambiguous:
            lines.append("The user may be referring to more than one item; ask which one before proceeding.")
        if snap.pending_confirmation:
            lines.append(f"Waiting for the user to confirm '{snap.pending_confirmation}'. Ask a yes/no question.")
        lines += snap.extra_notes
        return "\n".join(lines)

    # ------------------------------------------------------------------ compose
    def compose(self, snapshot: RuntimeSnapshot | None = None) -> ComposedInstructions:
        snap = snapshot or RuntimeSnapshot()
        static: dict[str, str] = {
            "role": self._role(),
            "language": self._language(),
            "data": self._data(),
            "tools": self._tools(),
            "truth": self._truth(),
            "coverage": self._coverage(),
            "disclosures": self._disclosures(),
            "flow": self._flow(),
        }
        static = {k: v for k, v in static.items() if v}
        static_text = "\n\n".join(f"## {k}\n{v}" for k, v in static.items())
        runtime = self._runtime(snap)
        sections = {**static, "runtime": runtime}
        text = f"{static_text}\n\n## runtime\n{runtime}"
        return ComposedInstructions(
            text=text,
            sections=sections,
            fingerprint=fingerprint(text),
            static_fingerprint=fingerprint(static_text),
        )

    def provider_tools(self) -> list[dict[str, Any]]:
        """tool.v1 declarations in neutral JSON; adapters translate to provider shapes."""
        tb = self.blueprint.tools
        out: list[dict[str, Any]] = []
        for r in [*tb.required, *tb.optional]:
            d = self.tool_declarations.get(r.tool_id)
            if d:
                out.append(d.model_dump(mode="json", by_alias=True))
        return out


def fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
