"""Knowledge ingestion pipeline (§15 QV-KNOW-003, normative order), deterministic and generic.

Parse → Normalize → Identify Entities → Extract Facts → Identify Relationships → Detect Missing Information →
Detect Contradictions → Detect Ambiguity → Identify Customer-Facing Questions → Identify Operational Requirements.

No domain vocabulary: an "entity" is any row with an identifier-like column (`id`, `sku`, `code`, `name`, …) or a
section heading; the remaining columns are attributes. Facts carry source_id + locator + provenance and start
UNVERIFIED unless the source is APPROVED structured data (QV-KNOW-004). Contradictions are never merged
(QV-KNOW-005). Gaps are classified against the Activity's declared needs (QV-KNOW-006).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from qevion.contracts.common import Provenance
from qevion.contracts.knowledge import (
    Contradiction,
    EntityRecord,
    Fact,
    FactStatus,
    KnowledgeGap,
    KnowledgeSource,
)
from qevion.knowledge.parsers import Row

_ID_KEYS = ("entity_id", "id", "sku", "code", "name", "title", "item", "service", "product", "plan")
_LIMIT_WORDS = re.compile(r"(?i)\b(not|never|only|cannot|can't|no longer|except|unless|غير|فقط|ممنوع|مش)\b|(^|\s)لا\s")
_PROC_WORDS = re.compile(r"(?i)\b(must|should|required|first|then|before|after|step|لازم|يجب|أولاً|بعد)\b")
_AMBIG_WORDS = re.compile(
    r"(?i)\b(maybe|usually|sometimes|approximately|about|around|varies|depends|تقريبا|أحيانا|حسب)\b|~"
)
_QUESTION_ATTRS = {
    "price": "How much does {e} cost?",
    "cost": "How much does {e} cost?",
    "duration": "How long does {e} take?",
    "available": "Is {e} available now?",
    "availability": "Is {e} available now?",
    "hours": "When are you open?",
    "closing": "When do you close?",
    "opening": "When do you open?",
    "delivery": "Do you deliver to my area?",
    "location": "Where are you located?",
    "address": "Where are you located?",
    "warranty": "What warranty comes with {e}?",
    "requires": "What do I need for {e}?",
    "eligibility": "Am I eligible for {e}?",
}
_DESCRIPTIVE = ("price", "cost", "duration", "available", "availability", "description")


@dataclass
class CustomerQuestion:
    question: str
    category: str
    entity_ref: str | None
    answerable_from: list[str]  # fact ids; empty → ASK_OWNER candidate


@dataclass
class OperationalRequirement:
    kind: str  # tool | verification | handoff | disclosure
    description: str
    derived_from: list[str]


@dataclass
class IngestionReport:
    source: KnowledgeSource
    entities: list[EntityRecord] = field(default_factory=list)
    facts: list[Fact] = field(default_factory=list)
    relationships: list[Fact] = field(default_factory=list)
    contradictions: list[Contradiction] = field(default_factory=list)
    gaps: list[KnowledgeGap] = field(default_factory=list)
    ambiguous_fact_ids: list[str] = field(default_factory=list)
    customer_questions: list[CustomerQuestion] = field(default_factory=list)
    operational_requirements: list[OperationalRequirement] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    injection_flags: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, int]:
        return {
            "entities": len(self.entities),
            "facts": len(self.facts),
            "relationships": len(self.relationships),
            "contradictions": len(self.contradictions),
            "gaps": len(self.gaps),
            "ambiguous": len(self.ambiguous_fact_ids),
            "customer_questions": len(self.customer_questions),
            "operational_requirements": len(self.operational_requirements),
        }


def _slug(s: str) -> str:
    return re.sub(r"[^\w]+", "_", s.lower()).strip("_")


def _entity_key(row: Row) -> tuple[str, str] | None:
    """(entity_type, entity_name) if the row describes an entity."""
    for k in _ID_KEYS:
        if k in row.values and row.values[k] not in (None, ""):
            generic = k in ("id", "entity_id", "sku", "code", "name", "title")
            etype = row.section or ("item" if generic else k)
            return _slug(str(etype)) or "item", str(row.values[k]).strip()
    return None


class KnowledgeStore:
    """Tenant-scoped in-memory store; the structured retriever (QV-KNOW-007) reads from here."""

    def __init__(self) -> None:
        self.sources: dict[str, KnowledgeSource] = {}
        self.facts: dict[str, Fact] = {}
        self.entities: dict[str, EntityRecord] = {}
        self.contradictions: dict[str, Contradiction] = {}
        self.gaps: dict[str, KnowledgeGap] = {}

    def approved_facts(self, tenant_id: str) -> list[Fact]:
        return [f for f in self.facts.values() if f.tenant_id == tenant_id and f.status is FactStatus.APPROVED]

    def approve_fact(self, fact_id: str, by: str) -> Fact:
        f = self.facts[fact_id]
        upd = f.model_copy(
            update={"status": FactStatus.APPROVED, "approved_by": by, "provenance": Provenance.KNOWLEDGE_APPROVED}
        )
        self.facts[fact_id] = upd
        return upd

    def resolve_contradiction(self, cid: str, winning_fact_id: str, *, by: str) -> Contradiction:
        c = self.contradictions[cid]
        if winning_fact_id not in c.fact_ids:
            raise ValueError("winner must be one of the conflicting facts")
        for fid in c.fact_ids:
            f = self.facts[fid]
            if fid == winning_fact_id:
                upd = {"status": FactStatus.APPROVED, "approved_by": by, "provenance": Provenance.KNOWLEDGE_APPROVED}
            else:
                upd = {"status": FactStatus.SUPERSEDED}
            self.facts[fid] = f.model_copy(update=upd)
        res = c.model_copy(update={"resolution": "operator_decided", "winning_fact_id": winning_fact_id})
        self.contradictions[cid] = res
        return res

    def unresolved_conflicts(self, tenant_id: str) -> list[Contradiction]:
        return [c for c in self.contradictions.values() if c.tenant_id == tenant_id and c.resolution == "pending"]


__all__ = ["CustomerQuestion", "IngestionReport", "KnowledgeStore", "OperationalRequirement"]
