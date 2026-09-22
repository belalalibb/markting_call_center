"""`qevion.knowledge_source.v1` and `qevion.knowledge_fact.v1` (§15 QV-KNOW). Structured retrieval only (D13)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field

from qevion.contracts.common import Provenance, QevionModel, utc_now


class SourceKind(StrEnum):
    FILE = "file"
    STRUCTURED = "structured"
    API = "api"
    OPERATOR_ANSWER = "operator_answer"


class SourceStatus(StrEnum):
    UPLOADED = "UPLOADED"
    PARSED = "PARSED"
    NORMALIZED = "NORMALIZED"
    EXTRACTED = "EXTRACTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    STALE = "STALE"


class KnowledgeSource(QevionModel):
    schema_: Literal["qevion.knowledge_source.v1"] = Field(default="qevion.knowledge_source.v1", alias="schema")
    source_id: str
    tenant_id: str
    kind: SourceKind
    name: str
    version: str = "1"
    sha256: str | None = None
    mime_type: str | None = None
    priority: int = Field(default=100, ge=0)
    status: SourceStatus = SourceStatus.UPLOADED
    uploaded_at: datetime = Field(default_factory=utc_now)
    approved_by: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class FactKind(StrEnum):
    ENTITY = "entity"
    ATTRIBUTE = "attribute"
    RULE = "rule"
    RELATIONSHIP = "relationship"
    PROCEDURE = "procedure"
    LIMITATION = "limitation"


class FactStatus(StrEnum):
    EXTRACTED = "EXTRACTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CONFLICTED = "CONFLICTED"
    SUPERSEDED = "SUPERSEDED"


class Fact(QevionModel):
    """Atomic, provenance-tagged unit of business knowledge. Only APPROVED facts may be spoken (QV-TRUTH)."""

    schema_: Literal["qevion.knowledge_fact.v1"] = Field(default="qevion.knowledge_fact.v1", alias="schema")
    fact_id: str
    tenant_id: str
    kind: FactKind
    subject: str = Field(description="entity id or type, e.g. 'service:consultation'")
    predicate: str = Field(description="attribute/relationship name, e.g. 'price', 'requires'")
    value: Any
    unit: str | None = None
    source_id: str
    source_locator: str | None = Field(default=None, description="page/line/cell reference in the source")
    provenance: Provenance = Provenance.UNVERIFIED
    status: FactStatus = FactStatus.EXTRACTED
    confidence: float = Field(default=1.0, ge=0, le=1)
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    approved_by: str | None = None
    extracted_at: datetime = Field(default_factory=utc_now)


class GapClass(StrEnum):
    REQUIRED_FOR_EXECUTION = "REQUIRED_FOR_EXECUTION"
    IMPORTANT_FOR_QUALITY = "IMPORTANT_FOR_QUALITY"
    OPTIONAL_IMPROVEMENT = "OPTIONAL_IMPROVEMENT"
    POLICY_RISK = "POLICY_RISK"
    DATA_CONFLICT = "DATA_CONFLICT"
    UNKNOWN = "UNKNOWN"


class KnowledgeGap(QevionModel):
    gap_id: str
    tenant_id: str
    activity_id: str | None = None
    gap_class: GapClass
    description: str
    question_for_operator: str
    related_fact_ids: list[str] = Field(default_factory=list)
    resolved: bool = False
    resolution_fact_id: str | None = None


class Contradiction(QevionModel):
    contradiction_id: str
    tenant_id: str
    fact_ids: list[str] = Field(min_length=2)
    description: str
    resolution: Literal["pending", "prefer_higher_priority", "operator_decided", "both_rejected"] = "pending"
    winning_fact_id: str | None = None


class EntityRecord(QevionModel):
    """Materialized entity view built from APPROVED facts for `get_entity` / `list_entities`."""

    entity_id: str
    entity_type: str
    tenant_id: str
    attributes: dict[str, Any] = Field(default_factory=dict)
    fact_ids: list[str] = Field(default_factory=list)
    provenance: Provenance = Provenance.KNOWLEDGE_APPROVED


class RetrievalQuery(QevionModel):
    tenant_id: str
    activity_id: str | None = None
    subject: str | None = None
    predicate: str | None = None
    entity_type: str | None = None
    text: str | None = Field(default=None, description="keyword match against subject/predicate/value; no embeddings (D13)")
    approved_only: bool = True
    limit: int = Field(default=10, ge=1, le=100)


class RetrievalResult(QevionModel):
    facts: list[Fact] = Field(default_factory=list)
    entities: list[EntityRecord] = Field(default_factory=list)
    miss: bool = Field(default=False, description="True → Core applies unknown_question_policy")
