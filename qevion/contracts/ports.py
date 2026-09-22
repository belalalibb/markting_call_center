"""Port interfaces (structural `Protocol`s). Adapters implement; Core/runtime consume (§32, ADR-0002).

Every port has a mock in ``qevion.adapters.**.mocks`` (QV-ACC-004 / P0.2 exit gate).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Protocol, runtime_checkable

from qevion.contracts.composition import AdapterCapabilities
from qevion.contracts.control import CredentialSource
from qevion.contracts.knowledge import RetrievalQuery, RetrievalResult
from qevion.contracts.outcome import HandoffRequest, HandoffResult, InteractionRecord, Outcome
from qevion.contracts.provider import (
    ASRRequest,
    ASRResult,
    AudioFrameRef,
    DecisionRequest,
    DecisionResult,
    LLMRequest,
    LLMResponse,
    S2SEvent,
    S2SSessionConfig,
    ToolCallResult,
    TTSChunk,
    TTSRequest,
    TurnDetectorConfig,
    TurnEvent,
)
from qevion.contracts.tool import ToolInvocation, ToolOutcome
from qevion.contracts.transport import ClientMessage, ServerMessage


@runtime_checkable
class CapabilityDescriber(Protocol):
    name: str

    def capabilities(self) -> AdapterCapabilities: ...


class S2SSession(Protocol):
    """One live provider session (speech-to-speech)."""

    async def send_audio(self, pcm16: bytes, ref: AudioFrameRef) -> None: ...
    async def commit_input(self) -> None: ...
    async def send_text(self, text: str) -> None: ...
    async def send_tool_result(self, result: ToolCallResult) -> None: ...
    async def cancel_response(self, response_id: str | None = None) -> None: ...
    async def update_instructions(self, instructions: str) -> None: ...
    def events(self) -> AsyncIterator[S2SEvent]: ...
    def audio_out(self) -> AsyncIterator[tuple[AudioFrameRef, bytes]]: ...
    async def close(self) -> None: ...


class S2SPort(CapabilityDescriber, Protocol):
    async def open(self, config: S2SSessionConfig, credential: str | None) -> S2SSession: ...


class LLMPort(CapabilityDescriber, Protocol):
    async def complete(self, request: LLMRequest, credential: str | None) -> LLMResponse: ...


class ASRPort(CapabilityDescriber, Protocol):
    async def transcribe(self, request: ASRRequest, pcm16: bytes, credential: str | None) -> ASRResult: ...


class TTSPort(CapabilityDescriber, Protocol):
    def synthesize(self, request: TTSRequest, credential: str | None) -> AsyncIterator[tuple[TTSChunk, bytes]]: ...


class TurnDetector(Protocol):
    """Fed PCM16 frames; yields TurnEvents. Stateful per session."""

    def configure(self, config: TurnDetectorConfig) -> None: ...
    def push(self, pcm16: bytes, ts_ms: int, assistant_speaking: bool) -> list[TurnEvent]: ...
    def reset(self) -> None: ...


class TurnPort(CapabilityDescriber, Protocol):
    def new_detector(self) -> TurnDetector: ...


class DecisionPort(CapabilityDescriber, Protocol):
    async def decide(self, request: DecisionRequest) -> DecisionResult: ...


class TransportSession(Protocol):
    async def send(self, message: ServerMessage) -> None: ...
    async def send_audio(self, response_id: str, pcm16: bytes) -> None: ...
    def incoming(self) -> AsyncIterator[ClientMessage | bytes]: ...
    async def close(self, reason: str = "bye") -> None: ...


class ToolBackend(Protocol):
    tool_id: str

    async def execute(self, invocation: ToolInvocation) -> ToolOutcome: ...


class KnowledgeRetriever(Protocol):
    async def retrieve(self, query: RetrievalQuery) -> RetrievalResult: ...


class OutcomeSink(Protocol):
    async def write_outcome(self, outcome: Outcome) -> str: ...
    async def write_record(self, record: InteractionRecord) -> str: ...


class HandoffSink(Protocol):
    async def handoff(self, request: HandoffRequest) -> HandoffResult: ...


class CredentialResolver(Protocol):
    """env → admin store → ephemeral UI (D9). Returns (value, source); value never logged."""

    def resolve(self, provider: str, tenant_id: str | None) -> tuple[str | None, CredentialSource]: ...


class TelephonyPort(Protocol):
    """Seam only (ADR-0003). Simulated adapter in POC."""

    async def dial(self, tenant_id: str, contact_ref: str, activity_id: str) -> str: ...
    async def hangup(self, call_id: str) -> None: ...


EventSink = Callable[[dict[str, Any]], Awaitable[None]]
