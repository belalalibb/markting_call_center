"""Memory + JSONL sinks for outcomes/interaction records and handoffs (outcome_sink.v1 / handoff_sink.v1)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from qevion.contracts.outcome import HandoffRequest, HandoffResult, InteractionRecord, Outcome


@dataclass
class MemoryOutcomeSink:
    outcomes: list[Outcome] = field(default_factory=list)
    records: list[InteractionRecord] = field(default_factory=list)

    async def write_outcome(self, outcome: Outcome) -> str:
        self.outcomes.append(outcome)
        return f"memory://outcome/{outcome.outcome_id}"

    async def write_record(self, record: InteractionRecord) -> str:
        self.records.append(record)
        return f"memory://record/{record.record_id}"


@dataclass
class JsonlOutcomeSink:
    """Append-only JSONL files; the POC's downstream-consumption surface (QV-OUT-003)."""

    directory: Path

    def __post_init__(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)

    def _append(self, name: str, payload: dict[str, object]) -> str:
        path = self.directory / name
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
        return str(path)

    async def write_outcome(self, outcome: Outcome) -> str:
        return self._append("outcomes.jsonl", outcome.model_dump(mode="json", by_alias=True))

    async def write_record(self, record: InteractionRecord) -> str:
        return self._append("interaction_records.jsonl", record.model_dump(mode="json", by_alias=True))


@dataclass
class MemoryHandoffSink:
    """console_state semantics: accepts everything, keeps the queue for the Operator Console."""

    requests: list[HandoffRequest] = field(default_factory=list)
    reject_destinations: set[str] = field(default_factory=set)

    async def handoff(self, request: HandoffRequest) -> HandoffResult:
        self.requests.append(request)
        if request.destination_ref in self.reject_destinations:
            return HandoffResult(handoff_id=request.handoff_id, accepted=False, destination=request.destination_ref, message="destination unavailable")
        return HandoffResult(
            handoff_id=request.handoff_id,
            accepted=True,
            destination=request.destination_ref,
            sink_ref=f"memory://handoff/{request.handoff_id}",
        )
