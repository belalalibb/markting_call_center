"""Shared primitives for all contracts."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class QevionModel(BaseModel):
    """Base for every contract: strict, immutable-by-default, enum values serialized as strings."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        use_enum_values=False,
        populate_by_name=True,
        str_strip_whitespace=True,
    )


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


class Provenance(StrEnum):
    """Where a fact/field value came from (QV-FLD, §20)."""

    USER_STATED = "USER_STATED"
    TOOL_VERIFIED = "TOOL_VERIFIED"
    SYSTEM_DERIVED = "SYSTEM_DERIVED"
    KNOWLEDGE_APPROVED = "KNOWLEDGE_APPROVED"
    UNVERIFIED = "UNVERIFIED"
    UNKNOWN = "UNKNOWN"


class Sensitivity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    RESTRICTED = "restricted"


class Direction(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"
    BIDIRECTIONAL = "bidirectional"


class Channel(StrEnum):
    BROWSER_VOICE = "browser_voice"
    TEXT = "text"
    TELEPHONY = "telephony"  # seam only (ADR-0003)
