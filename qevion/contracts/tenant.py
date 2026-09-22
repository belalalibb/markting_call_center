"""Tenant, `qevion.line.v1` (§7–§8), `qevion.locale_pack.v1` (§34), `qevion.voice_profile.v1` (§28)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field

from qevion.contracts.common import Channel, Direction, QevionModel, utc_now


class TenantStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class BudgetGuards(QevionModel):
    """Defaults per D14 (QV-COST)."""

    usd_per_day: float = Field(default=10.0, ge=0)
    max_session_seconds: int = Field(default=300, ge=10)
    max_sessions_per_day: int = Field(default=20, ge=1)
    warn_at_fraction: float = Field(default=0.8, ge=0, le=1)


class PrivacyPosture(QevionModel):
    """QV-PRIV defaults: no audio retention, redacted transcripts."""

    retain_audio: bool = False
    redact_transcripts: bool = True
    transcript_retention_days: int = Field(default=0, ge=0)
    pii_fields_encrypted: bool = True
    consent_disclosure_required: bool = True
    jurisdiction: str = "EG-PDPL-151/2020"


class Tenant(QevionModel):
    schema_: Literal["qevion.tenant.v1"] = Field(default="qevion.tenant.v1", alias="schema")
    tenant_id: str
    name: str
    status: TenantStatus = TenantStatus.ACTIVE
    default_locale: str = "ar-EG"
    budget: BudgetGuards = Field(default_factory=BudgetGuards)
    privacy: PrivacyPosture = Field(default_factory=PrivacyPosture)
    enabled_providers: list[str] = Field(default_factory=lambda: ["mock"])
    created_at: datetime = Field(default_factory=utc_now)


class Line(QevionModel):
    """An endpoint where sessions arrive/originate; binds an ACTIVE activity version (§8)."""

    schema_: Literal["qevion.line.v1"] = Field(default="qevion.line.v1", alias="schema")
    line_id: str
    tenant_id: str
    name: str
    channel: Channel
    direction: Direction
    activity_id: str | None = None
    activity_version: str | None = None
    composition_id: str | None = None
    enabled: bool = True
    external_address: str | None = Field(default=None, description="phone number / URL slug; telephony seam only")


class LexiconEntry(QevionModel):
    term: str
    pronunciation: str
    scope: str = "global"


class LocalePack(QevionModel):
    """Language/dialect assets the Core's instruction composer and adapters consume (§34 QV-LANG)."""

    schema_: Literal["qevion.locale_pack.v1"] = Field(default="qevion.locale_pack.v1", alias="schema")
    locale_pack_id: str
    language: str
    locale: str
    dialect: str | None = None
    register: Literal["formal", "neutral", "casual"] = "neutral"
    greeting_refs: list[str] = Field(default_factory=list)
    confirmation_phrases: list[str] = Field(default_factory=list)
    negation_phrases: list[str] = Field(default_factory=list)
    opt_out_phrases: list[str] = Field(default_factory=list)
    filler_policy: Literal["none", "minimal", "natural"] = "minimal"
    number_style: Literal["spoken_words", "digits"] = "spoken_words"
    lexicon: list[LexiconEntry] = Field(default_factory=list)
    version: str = "1"


class VoiceProfile(QevionModel):
    schema_: Literal["qevion.voice_profile.v1"] = Field(default="qevion.voice_profile.v1", alias="schema")
    voice_profile_id: str
    display_name: str
    provider_voice_map: dict[str, str] = Field(description="adapter name → provider voice id, e.g. {openai_realtime: 'marin'}")
    speaking_rate: float = Field(default=1.0, ge=0.5, le=2.0)
    persona_notes: str = ""
    locale: str = "ar-EG"
    version: str = "1"
