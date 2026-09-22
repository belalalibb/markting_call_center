"""Outcome engine — deterministic Outcome + InteractionRecord (§26 QV-OUT, QV-ACC-010).

Rules of the house:
* Outcomes are derived from *facts* (FieldStore, tool history, machine states, completion rules), never from
  what the model said (QV-OUT-001/002). `summary_text` is carried as an opaque, non-authoritative string.
* Completion rules are Blueprint data evaluated through the `decision.v1` port (deterministic-first, ADR-0004).
  A rule the port cannot evaluate yields UNKNOWN and is surfaced as an observation — never guessed.
* The primary outcome must be one of `outcome_schema.primary`; the vocabulary is `BaseOutcome` plus
  Activity-defined strings. Core only knows the generic precedence below, never business meaning.

Exit rule grammar extension (config, not code): `"<rule> => <outcome_value>"` maps a matched exit rule to an
explicit outcome value; without `=>` the rule text itself is used as the value.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from qevion.contracts.activity import ActivityBlueprint
from qevion.contracts.common import Channel
from qevion.contracts.control import ActivityState
from qevion.contracts.outcome import (
    BaseOutcome,
    ClaimDecisionEntry,
    CoverageMissEntry,
    InteractionRecord,
    Outcome,
    OutcomeTimestamps,
    RouteEntry,
    ToolProvenanceEntry,
)
from qevion.contracts.ports import DecisionPort
from qevion.contracts.provider import DecisionKind, DecisionRequest, DecisionSource
from qevion.contracts.tool import ToolOutcome, ToolOutcomeStatus
from qevion.core.field_store import FieldStore

_B = BaseOutcome


def _dt(ms: int | None) -> datetime | None:
    return None if ms is None else datetime.fromtimestamp(ms / 1000, tz=UTC)


@dataclass
class SessionFacts:
    """Everything the engine needs that is not already in the FieldStore. Filled by the session orchestrator."""

    session_id: str
    channel: Channel
    started_at_ms: int
    ended_at_ms: int | None = None
    first_user_turn_ms: int | None = None
    last_user_turn_ms: int | None = None
    turn_count: int = 0
    interruption_count: int = 0
    event_count: int = 0
    activity_state: ActivityState = ActivityState.OPENING
    handoff_ref: str | None = None
    handoff_ids: list[str] = field(default_factory=list)
    flags: set[str] = field(default_factory=set)  # session-level facts: opt_out, wrong_person, … (Activity data)
    routing_history: list[RouteEntry] = field(default_factory=list)
    coverage_misses: list[CoverageMissEntry] = field(default_factory=list)
    claim_decisions: list[ClaimDecisionEntry] = field(default_factory=list)
    summary_text: str | None = None
    event_log_ref: str | None = None
    evidence_refs: list[str] = field(default_factory=list)
    policy_versions: dict[str, str] = field(default_factory=dict)
    knowledge_versions: dict[str, str] = field(default_factory=dict)


@dataclass
class CompletionVerdict:
    success: bool | None  # None = at least one success rule UNKNOWN
    failure: bool | None
    exit_rule: str | None  # first matched exit rule (raw text)
    exit_value: str | None  # mapped value (after `=>`), or the rule text
    unknown_rules: list[str] = field(default_factory=list)


def flags_from_tools(history: list[ToolOutcome]) -> set[str]:
    """Generic tool facts usable by rules: `<tool>_completed`, `<tool>_accepted` (when output.accepted is true)."""
    flags: set[str] = set()
    for o in history:
        if o.status is ToolOutcomeStatus.COMPLETED:
            flags.add(f"{o.tool_id}_completed")
            if o.output.get("accepted") is True:
                flags.add(f"{o.tool_id}_accepted")
    return flags


def _split_exit(rule: str) -> tuple[str, str]:
    if "=>" in rule:
        lhs, rhs = rule.split("=>", 1)
        return lhs.strip(), rhs.strip()
    return rule.strip(), rule.strip()


@dataclass
class OutcomeEngine:
    blueprint: ActivityBlueprint
    decision: DecisionPort

    # ------------------------------------------------------------------ rules
    async def _eval(self, rules: list[str], store: FieldStore, flags: set[str]) -> tuple[bool | None, list[str]]:
        """AND over rules; returns (verdict, unknown_rules). Empty rule list → (None, []) — 'no rule defined'."""
        if not rules:
            return None, []
        req = DecisionRequest(
            kind=DecisionKind.EVALUATE_RULE,
            inputs={"fields": store.values(), "recorded": sorted(store.recorded_names()), "flags": sorted(flags)},
            rules=rules,
        )
        res = await self.decision.decide(req)
        if res.source is DecisionSource.UNKNOWN or res.value is None:
            return None, list(rules)
        return bool(res.value), []

    async def completion(self, store: FieldStore, flags: set[str]) -> CompletionVerdict:
        comp = self.blueprint.completion
        success, unk_s = await self._eval(comp.success_rules, store, flags)
        failure, unk_f = await self._eval(comp.failure_rules, store, flags)
        exit_rule: str | None = None
        exit_value: str | None = None
        unknown = [*unk_s, *unk_f]
        for raw in comp.exit_rules:
            expr, value = _split_exit(raw)
            hit, unk = await self._eval([expr], store, flags)
            if unk:
                unknown.extend(unk)
                continue
            if hit:
                exit_rule, exit_value = raw, value
                break
        return CompletionVerdict(success, failure, exit_rule, exit_value, unknown)

    # ------------------------------------------------------------------ primary
    def _pick(self, *candidates: str) -> str:
        """First candidate the Activity's outcome_schema allows; else first allowed primary (never invent)."""
        allowed = self.blueprint.outcome_schema.primary
        for c in candidates:
            if c in allowed:
                return c
        return allowed[0]

    def primary_for(self, verdict: CompletionVerdict, facts: SessionFacts, store: FieldStore) -> tuple[str, list[str]]:
        """Generic precedence: technical failure > handoff > explicit exit > failure rule > success > state-derived."""
        obs: list[str] = []
        st = facts.activity_state
        if st is ActivityState.BLOCKED:
            return self._pick(_B.TECHNICAL_FAILURE), ["activity blocked"]
        if st is ActivityState.ESCALATED or facts.handoff_ref:
            return self._pick(_B.HUMAN_REQUIRED), ["handoff requested"]
        if verdict.exit_rule is not None and verdict.exit_value is not None:
            obs.append(f"exit rule matched: {verdict.exit_rule}")
            return self._pick(verdict.exit_value, _B.REJECTED, _B.ABANDONED), obs
        if verdict.failure:
            return self._pick(_B.REJECTED, _B.NOT_ELIGIBLE), ["failure rule matched"]
        if verdict.success:
            return self._pick(_B.COMPLETED, _B.ACCEPTED), ["success rule matched"]
        if verdict.unknown_rules:
            obs.append(f"rules not evaluable: {verdict.unknown_rules}")
        if st is ActivityState.ABANDONED:
            return self._pick(_B.ABANDONED), [*obs, "user left"]
        if facts.first_user_turn_ms is None:
            return self._pick(_B.NO_ANSWER, _B.ABANDONED), [*obs, "no user turn"]
        if store.recorded_names():
            return self._pick(_B.PARTIALLY_COMPLETED, _B.ABANDONED), [*obs, "fields recorded but rules unmet"]
        return self._pick(_B.ABANDONED, _B.PARTIALLY_COMPLETED), [*obs, "nothing collected"]

    # ------------------------------------------------------------------ build
    async def build(
        self,
        *,
        store: FieldStore,
        tool_history: list[ToolOutcome],
        facts: SessionFacts,
        outcome_id: str,
        record_id: str,
    ) -> InteractionRecord:
        flags = facts.flags | flags_from_tools(tool_history)
        verdict = await self.completion(store, flags)
        primary, observations = self.primary_for(verdict, facts, store)

        secondary = [s for s in self.blueprint.outcome_schema.secondary if s in flags]
        for name, need, got in store.unsatisfied_required():
            observations.append(f"field {name} requires {need.value}, has {got.value if got else 'nothing'}")

        tool_prov = [
            ToolProvenanceEntry(
                call_id=o.call_id,
                tool_id=o.tool_id,
                status=o.status.value,
                fields_affected=[f.name for f in store.all() if f.tool_call_id == o.call_id],
            )
            for o in tool_history
        ]
        next_actions = self._next_actions(primary, facts)
        started = _dt(facts.started_at_ms)
        assert started is not None  # noqa: S101 — started_at_ms is required by SessionFacts
        ident = self.blueprint.identity
        outcome = Outcome(
            outcome_id=outcome_id,
            session_id=facts.session_id,
            tenant_id=ident.tenant_id,
            line_id=ident.line_id,
            activity_id=ident.activity_id,
            activity_version=ident.version,
            direction=self.blueprint.direction,
            channel=facts.channel,
            primary=primary,
            secondary=secondary,
            collected_fields=store.all(),
            verified_fields=store.verified_names(),
            inferred_fields=store.inferred_names(),
            rejected_fields=store.rejected_names(),
            observations=observations,
            next_actions=next_actions,
            handoff_ref=facts.handoff_ref,
            policy_versions=facts.policy_versions,
            knowledge_versions=facts.knowledge_versions,
            tool_provenance=tool_prov,
            timestamps=OutcomeTimestamps(
                session_started=started,
                session_ended=_dt(facts.ended_at_ms),
                first_user_turn=_dt(facts.first_user_turn_ms),
                last_user_turn=_dt(facts.last_user_turn_ms),
            ),
            evidence_refs=list(facts.evidence_refs),
            summary_text=facts.summary_text,
        )
        return InteractionRecord(
            record_id=record_id,
            outcome=outcome,
            routing_history=list(facts.routing_history),
            handoff_ids=list(facts.handoff_ids),
            coverage_misses=list(facts.coverage_misses),
            claim_decisions=list(facts.claim_decisions),
            turn_count=facts.turn_count,
            interruption_count=facts.interruption_count,
            tool_call_count=len(tool_history),
            event_count=facts.event_count,
            event_log_ref=facts.event_log_ref,
            evidence_refs=list(facts.evidence_refs),
        )

    def _next_actions(self, primary: str, facts: SessionFacts) -> list[str]:
        allowed = self.blueprint.outcome_schema.next_actions
        wanted: list[str] = []
        if primary == _B.HUMAN_REQUIRED or facts.handoff_ref:
            wanted.append("handoff")
        if primary == _B.CALLBACK_REQUESTED:
            wanted.append("schedule_callback")
        wanted.append("close")
        picked = [a for a in wanted if a in allowed]
        return picked or allowed[:1]


def snapshot_dict(record: InteractionRecord) -> dict[str, Any]:
    """Stable JSON-able projection for sinks/evidence (by_alias so `schema` keys serialize correctly)."""
    return record.model_dump(mode="json", by_alias=True)
