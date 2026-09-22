"""Session orchestrator — wires the Core primitives to ports, via contracts only (§27–§31, QV-RT, QV-INT).

Authority model (QV-RT-003): the dialog machine moves on normalized transport/provider/turn events; the activity
machine moves only on Core-validated facts (tool outcomes, FieldStore completion, decision-port verdicts,
confirmation interpreter). Model text never transitions anything and is never business truth.

Interruption protocol (§31, QV-INT-001) is implemented here, identically for every provider:
  1 DETECT → 2 CANCEL (provider.cancel_response + transport.stop_playout, 300 ms force path) → 3 RECONCILE
  (truncate to what was heard; unheard remainder never persists) → 4 ACCEPT → 5 COMMIT → 6 COHERE
  (FieldStore untouched by construction) → 7 RESPOND. Watermarks t0..t4 are recorded per interruption.

Events never carry raw audio, secrets or full transcripts (QV-EVT-003): text is summarized as length + digest.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from qevion.contracts.activity import ActivityBlueprint
from qevion.contracts.common import Channel, Provenance, new_id
from qevion.contracts.control import ActivityState, DialogState
from qevion.contracts.event import Event, EventKind, EventType
from qevion.contracts.outcome import (
    ConversationSnapshotRef,
    CoverageMissEntry,
    HandoffProposer,
    HandoffRequest,
    InteractionRecord,
    RouteEntry,
)
from qevion.contracts.ports import (
    DecisionPort,
    HandoffSink,
    OutcomeSink,
    S2SPort,
    S2SSession,
    ToolBackend,
    TransportSession,
    TurnDetector,
)
from qevion.contracts.provider import (
    AudioFrameRef,
    DecisionKind,
    DecisionRequest,
    DecisionSource,
    S2SEvent,
    S2SEventType,
    S2SSessionConfig,
    ToolCallRequest,
    ToolCallResult,
    TurnEvent,
    TurnEventType,
)
from qevion.contracts.telemetry import LatencySample, Watermark
from qevion.contracts.tenant import LocalePack, VoiceProfile
from qevion.contracts.tool import PlatformTool, ToolDeclaration, ToolInvocation, ToolOutcome, ToolOutcomeStatus
from qevion.contracts.transport import ClientMessage, ClientMessageType, ServerMessage, ServerMessageType
from qevion.core.activity_machine import ActivityMachine, ActivityTrigger
from qevion.core.context import EntityFocusStack, ObjectiveKind, PendingObjectives
from qevion.core.dialog_machine import DialogMachine, Transition
from qevion.core.field_store import FieldStore
from qevion.core.governance import ClaimGovernor, ConfirmationInterpreter
from qevion.core.instruction_composer import InstructionComposer, RuntimeSnapshot
from qevion.core.outcome_engine import OutcomeEngine, SessionFacts, flags_from_tools
from qevion.core.tool_pipeline import BudgetGuard, ToolPipeline

EventSink = Callable[[Event], Awaitable[None]]
Clock = Callable[[], int]  # ms since session start (injected for replay determinism, QV-RT-008)

_CANCEL_FORCE_MS = 300


def _digest(text: str) -> dict[str, Any]:
    """Redacted text summary for events — never the text itself (QV-PRIV / QV-EVT-003)."""
    return {"text_len": len(text), "text_sha256_12": hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]}


def _monotonic_clock() -> Clock:
    t0 = time.monotonic()
    return lambda: int((time.monotonic() - t0) * 1000)


@dataclass
class SessionDeps:
    """Everything a session needs, all behind contracts. Built by the runtime composition layer (P4), by tests here."""

    blueprint: ActivityBlueprint
    s2s: S2SPort
    s2s_config: S2SSessionConfig
    transport: TransportSession
    turn: TurnDetector
    decision: DecisionPort
    tool_declarations: dict[str, ToolDeclaration]
    tool_backends: dict[str, ToolBackend]
    outcome_sink: OutcomeSink
    handoff_sink: HandoffSink | None = None
    credential: str | None = None
    locale_pack: LocalePack | None = None
    voice_profile: VoiceProfile | None = None
    tenant_allowed_tools: set[str] | None = None
    channel: Channel = Channel.TEXT
    clock: Clock | None = None
    event_sink: EventSink | None = None
    budget: BudgetGuard = field(default_factory=BudgetGuard)
    confirmation_timeout_ms: int = 30_000


@dataclass
class InterruptionRecord:
    """The §31 watermarks (ms since session start) for one interruption."""

    response_id: str
    t0_user_speech_onset: int
    t1_barge_in_detected: int
    t2_cancel_sent: int | None = None
    t3_playout_stopped: int | None = None
    t4_state_reconciled: int | None = None
    forced: bool = False
    played_ms: int = 0
    heard_text_len: int = 0
    unheard_text_len: int = 0


@dataclass
class ResponseTrack:
    response_id: str
    started_ms: int
    text: str = ""
    audio_ms_sent: int = 0
    cancelled: bool = False
    done: bool = False


# --- part 2 ---
