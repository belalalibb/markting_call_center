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


# --- part 2 ---
