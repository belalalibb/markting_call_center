"""`qevion.transport.v1` (§29 QV-TR) — thin WS message protocol between browser AudioWorklet and runtime.

Binary frames carry PCM16 audio; JSON frames carry these messages. Topology A (ADR-0001).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import Field

from qevion.contracts.common import QevionModel
from qevion.contracts.provider import AudioFormat


class ClientMessageType(StrEnum):
    HELLO = "hello"  # capabilities, formats, activity ref
    AUDIO_COMMIT = "audio_commit"  # client-side end marker (optional; turn plane is authoritative)
    TEXT = "text"  # text channel input
    PLAYOUT_STARTED = "playout_started"  # timestamp for interruption measurement
    PLAYOUT_STOPPED = "playout_stopped"
    CONFIRM = "confirm"  # UI confirmation for confirm_before_execute tools
    BYE = "bye"
    PING = "ping"


class ServerMessageType(StrEnum):
    READY = "ready"
    AUDIO_START = "audio_start"  # next binary frames belong to response_id
    AUDIO_END = "audio_end"
    STOP_PLAYOUT = "stop_playout"  # interruption step 2 (§31)
    TRANSCRIPT = "transcript"  # redacted per QV-PRIV; DEBUG only
    STATE = "state"  # dialog/activity state for Operator Console
    EVENT = "event"  # forwarded qevion.event.v1 (filtered)
    CONFIRMATION_REQUEST = "confirmation_request"
    ERROR = "error"
    BYE = "bye"
    PONG = "pong"


class ClientHello(QevionModel):
    schema_: Literal["qevion.transport.v1"] = Field(default="qevion.transport.v1", alias="schema")
    type: Literal[ClientMessageType.HELLO] = ClientMessageType.HELLO
    tenant_id: str
    activity_id: str
    activity_version: str | None = None
    line_id: str | None = None
    direction: Literal["inbound", "outbound"] = "inbound"
    channel: Literal["browser_voice", "text"] = "browser_voice"
    input_format: AudioFormat = Field(default_factory=AudioFormat)
    output_format: AudioFormat = Field(default_factory=AudioFormat)
    client_capabilities: list[str] = Field(default_factory=lambda: ["audioworklet", "playout_timestamps"])
    operator_mode: bool = Field(default=False, description="Operator Console session (extra state messages)")


class ClientMessage(QevionModel):
    schema_: Literal["qevion.transport.v1"] = Field(default="qevion.transport.v1", alias="schema")
    type: ClientMessageType
    client_ts_ms: int | None = None
    text: str | None = None
    response_id: str | None = None
    call_id: str | None = None
    granted: bool | None = None


class ServerMessage(QevionModel):
    schema_: Literal["qevion.transport.v1"] = Field(default="qevion.transport.v1", alias="schema")
    type: ServerMessageType
    session_id: str
    server_ts_ms: int
    response_id: str | None = None
    text: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class TransportStats(QevionModel):
    frames_in: int = 0
    frames_out: int = 0
    bytes_in: int = 0
    bytes_out: int = 0
    reconnects: int = 0
    last_rtt_ms: int | None = None
