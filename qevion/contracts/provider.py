"""Provider role port contracts (§32 QV-PROV, ADR-0002): `s2s.v1 · llm.v1 · asr.v1 · tts.v1 · turn.v1 · decision.v1`.

These define the *messages* crossing each port. The Python `Protocol` interfaces live in
``qevion.contracts.ports``; adapters implement them; Core consumes them.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import Field

from qevion.contracts.common import QevionModel


class ProviderRole(StrEnum):
    S2S = "s2s"
    LLM = "llm"
    ASR = "asr"
    TTS = "tts"
    TURN = "turn"
    DECISION = "decision"


class AudioFormat(QevionModel):
    encoding: Literal["pcm16"] = "pcm16"
    sample_rate_hz: Literal[8000, 16000, 24000, 48000] = 24000
    channels: Literal[1] = 1


class AudioFrameRef(QevionModel):
    """Audio crosses ports as bytes out-of-band; events/logs carry only this reference (QV-EVT-003)."""

    frame_id: str
    byte_length: int = Field(ge=0)
    duration_ms: int = Field(ge=0)
    fmt: AudioFormat = Field(default_factory=AudioFormat)
    sha256: str | None = None


# ---- s2s.v1 ---------------------------------------------------------------


class S2SSessionConfig(QevionModel):
    schema_: Literal["qevion.s2s.v1"] = Field(default="qevion.s2s.v1", alias="schema")
    provider: str
    model: str
    voice: str | None = None
    input_format: AudioFormat = Field(default_factory=AudioFormat)
    output_format: AudioFormat = Field(default_factory=AudioFormat)
    instructions: str = Field(
        default="", description="rendered by Core instruction composer, regenerable from Blueprint"
    )
    tools: list[dict[str, Any]] = Field(default_factory=list, description="tool.v1 declarations rendered for provider")
    server_vad: bool = Field(default=False, description="False = QEVION turn plane owns endpointing")
    temperature: float | None = None
    language_hint: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class S2SEventType(StrEnum):
    SESSION_READY = "session_ready"
    INPUT_SPEECH_STARTED = "input_speech_started"
    INPUT_SPEECH_STOPPED = "input_speech_stopped"
    INPUT_TRANSCRIPT = "input_transcript"
    RESPONSE_STARTED = "response_started"
    RESPONSE_AUDIO_DELTA = "response_audio_delta"
    RESPONSE_TEXT_DELTA = "response_text_delta"
    RESPONSE_TOOL_CALL = "response_tool_call"
    RESPONSE_DONE = "response_done"
    RESPONSE_CANCELLED = "response_cancelled"
    ERROR = "error"
    CLOSED = "closed"


class S2SEvent(QevionModel):
    """Provider-neutral event emitted by an s2s adapter."""

    type: S2SEventType
    provider_event_id: str | None = None
    response_id: str | None = None
    item_id: str | None = None
    text: str | None = None
    audio: AudioFrameRef | None = None
    tool_call: ToolCallRequest | None = None
    error: ProviderError | None = None
    raw_type: str | None = Field(default=None, description="provider's native event name, for diagnostics")


class ToolCallRequest(QevionModel):
    call_id: str
    tool_id: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolCallResult(QevionModel):
    call_id: str
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class ProviderError(QevionModel):
    code: str
    message: str
    retryable: bool = False
    provider_code: str | None = None


# ---- llm.v1 ---------------------------------------------------------------


class LLMMessage(QevionModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_call_id: str | None = None


class LLMRequest(QevionModel):
    schema_: Literal["qevion.llm.v1"] = Field(default="qevion.llm.v1", alias="schema")
    model: str
    messages: list[LLMMessage]
    tools: list[dict[str, Any]] = Field(default_factory=list)
    temperature: float = 0.2
    max_tokens: int | None = None
    json_schema: dict[str, Any] | None = Field(default=None, description="structured output constraint")


class LLMResponse(QevionModel):
    text: str | None = None
    tool_calls: list[ToolCallRequest] = Field(default_factory=list)
    structured: dict[str, Any] | None = None
    usage: dict[str, int] = Field(default_factory=dict)
    finish_reason: str | None = None


# ---- asr.v1 / tts.v1 -------------------------------------------------------


class ASRRequest(QevionModel):
    schema_: Literal["qevion.asr.v1"] = Field(default="qevion.asr.v1", alias="schema")
    audio: AudioFrameRef
    language: str | None = None
    partial: bool = False


class ASRResult(QevionModel):
    text: str
    is_final: bool
    confidence: float | None = Field(default=None, ge=0, le=1)
    language: str | None = None
    words: list[dict[str, Any]] = Field(default_factory=list)


class TTSRequest(QevionModel):
    schema_: Literal["qevion.tts.v1"] = Field(default="qevion.tts.v1", alias="schema")
    text: str
    voice: str
    locale: str
    fmt: AudioFormat = Field(default_factory=AudioFormat)
    pronunciation_hints: list[dict[str, str]] = Field(default_factory=list)


class TTSChunk(QevionModel):
    audio: AudioFrameRef
    is_last: bool = False


# ---- turn.v1 ---------------------------------------------------------------


class TurnEventType(StrEnum):
    """§30 QV-TURN taxonomy."""

    SPEECH_START = "speech_start"
    SPEECH_CONTINUING = "speech_continuing"
    SPEECH_PAUSE = "speech_pause"
    END_OF_TURN_CANDIDATE = "end_of_turn_candidate"
    END_OF_TURN = "end_of_turn"
    BARGE_IN = "barge_in"
    NOISE_REJECTED = "noise_rejected"


class TurnEvent(QevionModel):
    schema_: Literal["qevion.turn.v1"] = Field(default="qevion.turn.v1", alias="schema")
    type: TurnEventType
    ts_ms: int = Field(ge=0, description="monotonic ms since session start")
    confidence: float = Field(default=1.0, ge=0, le=1)
    detector: str = Field(description="silero | smart_turn | provider_delegated | mock")
    speech_ms: int | None = None
    silence_ms: int | None = None


class TurnDetectorConfig(QevionModel):
    detector: str = "silero"
    threshold: float = Field(default=0.5, ge=0, le=1)
    min_speech_ms: int = 120
    min_silence_ms: int = 500
    barge_in_min_speech_ms: int = 200


# ---- decision.v1 (ADR-0004) -------------------------------------------------


class DecisionKind(StrEnum):
    VALIDATE_FIELD = "validate_field"
    INTERPRET_CONFIRMATION = "interpret_confirmation"
    CLASSIFY_INTENT = "classify_intent"
    CHECK_CLAIM = "check_claim"
    NEXT_ACTIVITY_STATE = "next_activity_state"
    EVALUATE_RULE = "evaluate_rule"


class DecisionRequest(QevionModel):
    schema_: Literal["qevion.decision.v1"] = Field(default="qevion.decision.v1", alias="schema")
    kind: DecisionKind
    inputs: dict[str, Any] = Field(default_factory=dict)
    rules: list[str] = Field(default_factory=list, description="rule refs / expressions from the Blueprint")
    options: list[str] = Field(default_factory=list, description="closed set of acceptable values, if any")
    allow_llm_proposal: bool = False


class DecisionSource(StrEnum):
    RULE = "RULE"
    LLM_VALIDATED = "LLM_VALIDATED"
    UNKNOWN = "UNKNOWN"


class DecisionResult(QevionModel):
    value: Any = None
    confidence: float = Field(default=1.0, ge=0, le=1)
    source: DecisionSource
    evidence_refs: list[str] = Field(default_factory=list)
    reason: str | None = None
    decided_at_ms: int | None = None

    @property
    def is_unknown(self) -> bool:
        return self.source == DecisionSource.UNKNOWN
