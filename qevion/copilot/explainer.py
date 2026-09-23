"""Explainer (QV-COP-015-A) and readiness findings (QV-COP-011 "what could go wrong").

Deterministic text; an optional `phrase` port may *rephrase* it but can never add facts or change the
proposal (LLM ≠ business truth). Output is plain text with stable section headers so tests can assert it.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from qevion.contracts.copilot import BlueprintProposal, CopilotQuestion, QuestionKind, ReadinessFinding

Phraser = Callable[[str], str]


def readiness_findings(draft: dict[str, Any], proposal_gaps: int, unresolved_conflicts: int) -> list[ReadinessFinding]:
    """Structural 'what could go wrong' analysis over the draft dict (no business judgement)."""
    out: list[ReadinessFinding] = []

    def g(path: str) -> Any:
        cur: Any = draft
        for p in path.split("."):
            if not isinstance(cur, dict) or p not in cur:
                return None
            cur = cur[p]
        return cur

    direction = g("direction")
    channels = g("channels") or []
    if direction in ("outbound", "bidirectional") and not g("policies.contact_policy_hooks"):
        out.append(
            ReadinessFinding(
                category="compliance",
                description="Outbound contact without consent/attempt-limit/contact-window policy.",
                severity="BLOCK",
                mitigation="Define policies.contact_policy_hooks before activation.",
                related_paths=["policies.contact_policy_hooks"],
            )
        )
    if not g("knowledge.sources"):
        out.append(
            ReadinessFinding(
                category="knowledge",
                description="No approved knowledge sources: the agent can only state limitations.",
                severity="WARN",
                mitigation="Upload at least one source and approve its facts.",
                related_paths=["knowledge.sources"],
            )
        )
    if proposal_gaps:
        out.append(
            ReadinessFinding(
                category="knowledge",
                description=f"{proposal_gaps} open knowledge gap(s) — customers may ask what the agent cannot answer.",
                severity="WARN",
                mitigation="Answer gap questions or accept STATE_LIMITATION for those topics.",
                related_paths=["knowledge.gaps"],
            )
        )
    if unresolved_conflicts:
        out.append(
            ReadinessFinding(
                category="data_integrity",
                description=f"{unresolved_conflicts} unresolved source contradiction(s).",
                severity="BLOCK",
                mitigation="Choose the winning fact per contradiction.",
                related_paths=["knowledge.contradictions"],
            )
        )
    uq = g("policies.unknown_question_policy.default")
    if uq == "OFFER_HUMAN_HANDOFF" and not g("handoff_rules"):
        out.append(
            ReadinessFinding(
                category="escalation",
                description="Handoff is promised but no destination exists — the agent would offer help it cannot deliver.",
                severity="BLOCK",
                mitigation="Add at least one handoff rule.",
                related_paths=["handoff_rules"],
            )
        )
    if "browser_voice" in channels or "telephony" in channels:
        if not g("locale.voice_profile_ref"):
            out.append(
                ReadinessFinding(
                    category="voice",
                    description="Voice channel selected without a pinned voice profile.",
                    severity="WARN",
                    mitigation="Select a voice profile so pronunciation/persona are reproducible.",
                    related_paths=["locale.voice_profile_ref"],
                )
            )
        out.append(
            ReadinessFinding(
                category="interruption",
                description="Callers interrupt; provider latency spikes cut sentences mid-word.",
                severity="INFO",
                mitigation="Runtime barge-in path (7-step) covers this; verify in simulation with interruption cases.",
                related_paths=["evaluation.cases"],
            )
        )
    req = g("data.required") or []
    if len(req) > 6:
        out.append(
            ReadinessFinding(
                category="dialog_length",
                description=f"{len(req)} required fields — long collections raise abandonment.",
                severity="WARN",
                mitigation="Move rarely-needed fields to data.optional.",
                related_paths=["data.required"],
            )
        )
    for f in req:
        if isinstance(f, dict) and f.get("sensitivity") in ("HIGH", "high") and not g("policies.disclosures"):
            out.append(
                ReadinessFinding(
                    category="privacy",
                    description=f"Sensitive field '{f.get('name')}' collected without a disclosure.",
                    severity="WARN",
                    mitigation="Add a disclosure at OPENING.",
                    related_paths=["policies.disclosures", "data.required"],
                )
            )
            break
    if not g("completion.failure_rules") and g("completion.success_rules"):
        out.append(
            ReadinessFinding(
                category="completion",
                description="Success is defined but failure is not — abandoned sessions will be classified by default rules.",
                severity="INFO",
                mitigation="Add failure/exit rules for explicit classification.",
                related_paths=["completion.failure_rules"],
            )
        )
    return out


class Explainer:
    """Human output (A). Never claims validity the proposal does not have."""

    def __init__(self, phrase: Phraser | None = None) -> None:
        self._phrase = phrase or (lambda s: s)

    def explain_question(self, q: CopilotQuestion) -> str:
        kind = {
            QuestionKind.BLOCKING_GAP: "Required before activation",
            QuestionKind.DATA_CONFLICT: "Your sources disagree",
            QuestionKind.POLICY_RISK: "Policy / compliance",
            QuestionKind.BUSINESS_DECISION: "Your decision (I will not guess this)",
            QuestionKind.CAPABILITY_GAP: "Capability",
            QuestionKind.QUALITY: "Quality",
            QuestionKind.OPTIONAL: "Optional",
        }[q.kind]
        lines = [f"[{kind}] {q.text}", f"Why: {q.why_it_matters}"]
        if q.options:
            lines.append("Options: " + ", ".join(q.options))
        if q.proposed_default is not None:
            lines.append(f"Suggested (structure only, needs your confirmation): {q.proposed_default}")
        return self._phrase("\n".join(lines))

    def explain_proposal(self, p: BlueprintProposal) -> str:
        s: list[str] = []
        s.append(f"# Proposal {p.proposal_id} — status: {p.status.value}, readiness: {p.readiness_state.value}")
        s.append("## Draft")
        s.append("valid" if p.draft_valid else "NOT valid yet: " + "; ".join(p.validation_errors[:5]))
        s.append("## Decisions")
        un = p.unapproved_decisions
        s.append(f"{len(p.decisions)} recorded, {len(un)} awaiting your approval")
        for d in un[:10]:
            s.append(f"- {d.item_path} (proposed by {d.proposed_by.value})")
        s.append("## Knowledge")
        gc = p.gap_counts()
        s.append(", ".join(f"{k}: {v}" for k, v in sorted(gc.items())) if gc else "no open gaps")
        pend = [c for c in p.contradictions if c.resolution == "pending"]
        s.append(f"{len(pend)} unresolved contradiction(s)")
        s.append("## Capabilities")
        for c in p.capability_requirements:
            s.append(f"- {c.requirement}: {c.action.value} → {c.integration.value}")
        if not p.capability_requirements:
            s.append("nothing beyond the selected composition")
        s.append("## Preflight")
        blk = [f for f in p.preflight_findings if f.severity == "BLOCK"]
        s.append(f"{len(blk)} blocking, {len(p.preflight_findings) - len(blk)} warnings")
        for f in blk[:10]:
            s.append(f"- {f.reason.value} @ {f.path}: {f.message}")
        s.append("## What could go wrong")
        for r in p.readiness_findings:
            s.append(f"- [{r.severity}] {r.category}: {r.description}" + (f" → {r.mitigation}" if r.mitigation else ""))
        if not p.readiness_findings:
            s.append("no structural risks detected")
        s.append("## Next questions")
        for q in p.questions[:5]:
            s.append(f"- ({q.kind.value}{', blocking' if q.blocking else ''}) {q.text}")
        if not p.questions:
            s.append("none — ready for your review")
        return self._phrase("\n".join(s))


__all__ = ["Explainer", "Phraser", "readiness_findings"]
