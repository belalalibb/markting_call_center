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
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from qevion.contracts.activity import ActivityBlueprint
from qevion.contracts.common import Provenance, new_id
from qevion.contracts.knowledge import (
    Contradiction,
    EntityRecord,
    Fact,
    FactKind,
    FactStatus,
    GapClass,
    KnowledgeGap,
    KnowledgeSource,
    RetrievalQuery,
    RetrievalResult,
    SourceKind,
    SourceStatus,
)
from qevion.knowledge.parsers import ParsedSource, Row, parse

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
    """(entity_type, entity_name) if the row describes an entity. Identity comes from the identifier column,
    never from a document heading — otherwise the same item under two headings would look like two entities
    and cross-source contradictions would be missed. A heading is recorded as the `section` attribute."""
    for k in _ID_KEYS:
        if k in row.values and row.values[k] not in (None, ""):
            generic = k in ("id", "entity_id", "sku", "code", "name", "title", "item")
            return ("item" if generic else k), str(row.values[k]).strip()
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


@dataclass
class KnowledgePipeline:
    store: KnowledgeStore = field(default_factory=KnowledgeStore)

    # ------------------------------------------------------------------ entry points
    def ingest(
        self,
        source: KnowledgeSource,
        data: bytes,
        *,
        activity: ActivityBlueprint | None = None,
        approve_structured: bool = True,
    ) -> IngestionReport:
        parsed = parse(data, mime_type=source.mime_type, name=source.name)
        return self.ingest_parsed(source, parsed, activity=activity, approve_structured=approve_structured)

    def ingest_parsed(
        self,
        source: KnowledgeSource,
        parsed: ParsedSource,
        *,
        activity: ActivityBlueprint | None = None,
        approve_structured: bool = True,
    ) -> IngestionReport:
        rep = IngestionReport(
            source=source, warnings=list(parsed.warnings), injection_flags=list(parsed.injection_flags)
        )
        # QV-KNOW-004: only an operator-APPROVED structured/API source yields approved facts directly;
        # documents always start UNVERIFIED/EXTRACTED and need approval.
        auto_ok = (
            approve_structured
            and source.kind in (SourceKind.STRUCTURED, SourceKind.API)
            and source.status is SourceStatus.APPROVED
        )
        prov = Provenance.KNOWLEDGE_APPROVED if auto_ok else Provenance.UNVERIFIED
        status = FactStatus.APPROVED if auto_ok else FactStatus.EXTRACTED

        self._entities_and_facts(source, parsed, rep, prov, status)
        self._relationships(source, rep, prov, status)
        self._contradictions(source, rep)
        self._ambiguity(rep)
        self._gaps(source, rep, activity)
        self._customer_questions(rep)
        self._operational_requirements(rep, activity)

        final = SourceStatus.APPROVED if auto_ok else SourceStatus.EXTRACTED
        self.store.sources[source.source_id] = source.model_copy(update={"status": final})
        for f in [*rep.facts, *rep.relationships]:
            self.store.facts[f.fact_id] = f
        for e in rep.entities:
            self.store.entities[e.entity_id] = e
        for c in rep.contradictions:
            self.store.contradictions[c.contradiction_id] = c
        for g in rep.gaps:
            self.store.gaps[g.gap_id] = g
        return rep

    # ------------------------------------------------------------------ steps
    def _entities_and_facts(
        self, src: KnowledgeSource, parsed: ParsedSource, rep: IngestionReport, prov: Provenance, status: FactStatus
    ) -> None:
        by_entity: dict[str, EntityRecord] = {}
        for row in parsed.rows:
            key = _entity_key(row)
            if key is None:
                # statements / section key-values → RULE-like facts (LIMITATION / PROCEDURE / ATTRIBUTE)
                for k, v in row.values.items():
                    if v is None:
                        continue
                    text = str(v)
                    if _LIMIT_WORDS.search(text):
                        kind = FactKind.LIMITATION
                    elif _PROC_WORDS.search(text):
                        kind = FactKind.PROCEDURE
                    else:
                        kind = FactKind.ATTRIBUTE
                    subject = f"section:{_slug(row.section)}" if row.section else f"source:{src.source_id}"
                    rep.facts.append(self._fact(src, kind, subject, k, v, row.locator, prov, status))
                continue
            etype, name = key
            eid = f"{etype}:{_slug(name)}"
            ent = by_entity.get(eid) or EntityRecord(
                entity_id=eid, entity_type=etype, tenant_id=src.tenant_id, attributes={"name": name}, provenance=prov
            )
            by_entity[eid] = ent
            if row.section and "section" not in ent.attributes:
                ent.attributes["section"] = row.section
            for k, v in row.values.items():
                if v is None or (k in _ID_KEYS and str(v).strip() == name):
                    continue
                f = self._fact(src, FactKind.ATTRIBUTE, eid, k, v, row.locator, prov, status)
                rep.facts.append(f)
                ent.attributes[k] = v
                ent.fact_ids.append(f.fact_id)
        rep.entities = list(by_entity.values())

    def _relationships(self, src: KnowledgeSource, rep: IngestionReport, prov: Provenance, status: FactStatus) -> None:
        """An attribute whose value names another known entity is a relationship (e.g. plan.includes = 'Alpha')."""
        names = {str(e.attributes.get("name", "")).lower(): e.entity_id for e in rep.entities}
        for f in list(rep.facts):
            if f.kind is not FactKind.ATTRIBUTE or not isinstance(f.value, str):
                continue
            target = names.get(f.value.strip().lower())
            if target and target != f.subject:
                rep.relationships.append(
                    self._fact(
                        src, FactKind.RELATIONSHIP, f.subject, f.predicate, target, f.source_locator or "", prov, status
                    )
                )

    def _contradictions(self, src: KnowledgeSource, rep: IngestionReport) -> None:
        """Same subject+predicate, differing values — within this source and against stored facts (QV-KNOW-005)."""
        groups: dict[tuple[str, str], list[Fact]] = defaultdict(list)
        for f in rep.facts:
            if f.kind is FactKind.ATTRIBUTE and not f.subject.startswith("source:"):
                groups[(f.subject, f.predicate)].append(f)
        for f in self.store.facts.values():
            live = f.status not in (FactStatus.REJECTED, FactStatus.SUPERSEDED)
            if f.tenant_id == src.tenant_id and live and (f.subject, f.predicate) in groups:
                groups[(f.subject, f.predicate)].append(f)
        for (subject, predicate), facts in groups.items():
            distinct: dict[str, Fact] = {}
            for f in facts:
                distinct.setdefault(repr(f.value), f)
            if len(distinct) < 2:
                continue
            ids = [f.fact_id for f in distinct.values()]
            # explicit source_priority resolution (lower number = higher priority) when every value has its own source
            src_of = {
                f.fact_id: (src if f.source_id == src.source_id else self.store.sources.get(f.source_id))
                for f in distinct.values()
            }
            prios = sorted((s.priority, s.source_id, fid) for fid, s in src_of.items() if s is not None)
            resolution, winner = "pending", None
            if len(prios) == len(distinct) and len({p for p, _, _ in prios}) == len(prios):
                winner = prios[0][2]
                resolution = "prefer_higher_priority"
            desc = f"{subject}.{predicate} has {len(distinct)} different values: " + ", ".join(
                f"{f.value!r}@{f.source_id}:{f.source_locator}" for f in distinct.values()
            )
            c = Contradiction(
                contradiction_id=new_id("kc"),
                tenant_id=src.tenant_id,
                fact_ids=ids,
                description=desc,
                resolution=resolution,
                winning_fact_id=winner,
            )
            rep.contradictions.append(c)
            for f in facts:
                if resolution == "pending":
                    self._mark(rep, f.fact_id, FactStatus.CONFLICTED)
                elif f.fact_id != winner:
                    self._mark(rep, f.fact_id, FactStatus.SUPERSEDED)
            if resolution == "pending":
                rep.gaps.append(
                    KnowledgeGap(
                        gap_id=new_id("gap"),
                        tenant_id=src.tenant_id,
                        gap_class=GapClass.DATA_CONFLICT,
                        description=desc,
                        question_for_operator=f"Which value of '{predicate}' for '{subject}' is correct?",
                        related_fact_ids=ids,
                    )
                )

    def _ambiguity(self, rep: IngestionReport) -> None:
        for i, f in enumerate(rep.facts):
            if isinstance(f.value, str) and _AMBIG_WORDS.search(f.value):
                rep.ambiguous_fact_ids.append(f.fact_id)
                rep.facts[i] = f.model_copy(update={"confidence": min(f.confidence, 0.5)})

    def _gaps(self, src: KnowledgeSource, rep: IngestionReport, activity: ActivityBlueprint | None) -> None:
        """Missing information relative to what the Activity declares it needs (QV-KNOW-006)."""
        if activity is None:
            return
        all_facts = [*rep.facts, *self.store.approved_facts(src.tenant_id)]
        predicates = {f.predicate for f in all_facts}
        entity_types = {e.entity_type for e in [*rep.entities, *self.store.entities.values()]}
        seen: set[str] = set()

        def covers(token: str) -> bool:
            t = _slug(token)
            head = t.split("_")[0]
            return any(t in p or p in t or head in p for p in predicates) or any(t in e or e in t for e in entity_types)

        def gap(cls: GapClass, desc: str, q: str) -> None:
            if desc in seen:
                return
            seen.add(desc)
            rep.gaps.append(
                KnowledgeGap(
                    gap_id=new_id("gap"),
                    tenant_id=src.tenant_id,
                    activity_id=activity.identity.activity_id,
                    gap_class=cls,
                    description=desc,
                    question_for_operator=q,
                )
            )

        for kr in activity.knowledge.requirements:
            if kr.status == "MISSING" or not covers(kr.domain):
                gap(
                    GapClass.REQUIRED_FOR_EXECUTION,
                    f"knowledge requirement '{kr.domain}' not covered by any source",
                    f"Please provide: {kr.description or kr.domain}",
                )
        for spec in activity.data.required:
            needs_kb = spec.provenance_required is Provenance.KNOWLEDGE_APPROVED
            if needs_kb and spec.type not in ("entity_ref", "list", "enum") and not covers(spec.name):
                gap(
                    GapClass.REQUIRED_FOR_EXECUTION,
                    f"field '{spec.name}' must come from approved knowledge but no facts mention it",
                    f"Which approved values can '{spec.name}' take?",
                )
        for claim in activity.policies.allowed_claims:
            if not covers(claim.claim_type):
                gap(
                    GapClass.POLICY_RISK,
                    f"allowed claim '{claim.claim_type}' has no supporting facts — the agent could only guess",
                    f"What is the approved source for '{claim.claim_type}'?",
                )
        for q in activity.coverage.questions:
            if q.handling == "KNOWLEDGE" and q.status != "COVERED":
                gap(
                    GapClass.IMPORTANT_FOR_QUALITY,
                    f"coverage question '{q.id}' ({q.category}) expects knowledge that is not approved",
                    f"How should the agent answer: '{q.pattern}'?",
                )
        for e in rep.entities:
            if not any(k in e.attributes for k in _DESCRIPTIVE):
                gap(
                    GapClass.OPTIONAL_IMPROVEMENT,
                    f"entity '{e.entity_id}' has no descriptive attributes beyond its name",
                    f"Add price/duration/availability/description for '{e.attributes.get('name')}'.",
                )
        for fid in rep.ambiguous_fact_ids:
            f = next(x for x in rep.facts if x.fact_id == fid)
            gap(
                GapClass.UNKNOWN,
                f"fact {f.subject}.{f.predicate} is ambiguous ({f.value!r})",
                f"What is the exact value of '{f.predicate}' for '{f.subject}'?",
            )

    def _customer_questions(self, rep: IngestionReport) -> None:
        by_id = {f.fact_id: f for f in rep.facts}
        for e in rep.entities:
            name = str(e.attributes.get("name", e.entity_id))
            for attr, tmpl in _QUESTION_ATTRS.items():
                if attr in e.attributes:
                    fids = [fid for fid in e.fact_ids if by_id[fid].predicate == attr]
                    rep.customer_questions.append(CustomerQuestion(tmpl.format(e=name), attr, e.entity_id, fids))
            rep.customer_questions.append(
                CustomerQuestion(f"What is {name}?", "description", e.entity_id, list(e.fact_ids))
            )
            rep.customer_questions.append(
                CustomerQuestion(f"How does {name} compare to the alternatives?", "comparison", e.entity_id, [])
            )
        for f in rep.facts:
            if f.kind is FactKind.LIMITATION:
                rep.customer_questions.append(
                    CustomerQuestion(f"Is this true: '{f.value}'?", "limitation", None, [f.fact_id])
                )
            elif f.subject.startswith("section:") and f.predicate in _QUESTION_ATTRS:
                label = f.subject.split(":", 1)[1]
                rep.customer_questions.append(
                    CustomerQuestion(_QUESTION_ATTRS[f.predicate].format(e=label), f.predicate, None, [f.fact_id])
                )

    def _operational_requirements(self, rep: IngestionReport, activity: ActivityBlueprint | None) -> None:
        preds = {f.predicate for f in rep.facts}
        if preds & {"price", "cost"}:
            rep.operational_requirements.append(
                OperationalRequirement("tool", "compute_quote over approved prices", sorted(preds & {"price", "cost"}))
            )
        if preds & {"available", "availability", "stock"}:
            rep.operational_requirements.append(
                OperationalRequirement(
                    "verification",
                    "live availability check (verify_field / lookup_knowledge with freshness)",
                    sorted(preds & {"available", "availability", "stock"}),
                )
            )
        if preds & {"delivery", "zone", "area", "address"}:
            rep.operational_requirements.append(
                OperationalRequirement(
                    "verification",
                    "address/zone verification before execution",
                    sorted(preds & {"delivery", "zone", "area", "address"}),
                )
            )
        lims = [f.fact_id for f in rep.facts if f.kind is FactKind.LIMITATION]
        if lims:
            rep.operational_requirements.append(
                OperationalRequirement(
                    "disclosure", "state limitations proactively when relevant (STATE_LIMITATION)", lims[:5]
                )
            )
        if activity is not None:
            uqp = activity.policies.unknown_question_policy
            if any(b.value == "OFFER_HUMAN_HANDOFF" for b in [uqp.default, *(o.behavior for o in uqp.overrides)]):
                rep.operational_requirements.append(
                    OperationalRequirement("handoff", "human destination for OFFER_HUMAN_HANDOFF topics", [])
                )

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _fact(
        src: KnowledgeSource,
        kind: FactKind,
        subject: str,
        predicate: str,
        value: Any,
        locator: str,
        prov: Provenance,
        status: FactStatus,
    ) -> Fact:
        return Fact(
            fact_id=new_id("fact"),
            tenant_id=src.tenant_id,
            kind=kind,
            subject=subject,
            predicate=predicate,
            value=value,
            source_id=src.source_id,
            source_locator=locator,
            provenance=prov,
            status=status,
        )

    @staticmethod
    def _mark(rep: IngestionReport, fact_id: str, status: FactStatus) -> None:
        for i, f in enumerate(rep.facts):
            if f.fact_id == fact_id:
                rep.facts[i] = f.model_copy(update={"status": status})


class StructuredRetriever:
    """`KnowledgeRetriever` port over the store: exact/slug/substring match, approved-only by default (QV-KNOW-007/010)."""

    def __init__(self, store: KnowledgeStore) -> None:
        self.store = store

    async def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
        facts = [f for f in self.store.facts.values() if f.tenant_id == query.tenant_id]
        if query.approved_only:
            facts = [f for f in facts if f.status is FactStatus.APPROVED]
        if query.subject:
            sub = _slug(query.subject)
            facts = [f for f in facts if f.subject == query.subject or f.subject.endswith(":" + sub)]
        if query.predicate:
            pred = _slug(query.predicate)
            facts = [f for f in facts if f.predicate == pred]
        if query.text:
            t = query.text.lower()
            facts = [
                f for f in facts if t in f.subject.lower() or t in f.predicate.lower() or t in str(f.value).lower()
            ]
        subjects = {f.subject for f in facts}
        ents = [e for e in self.store.entities.values() if e.tenant_id == query.tenant_id]
        if query.entity_type:
            ents = [e for e in ents if e.entity_type == query.entity_type]
        if query.text:
            t = query.text.lower()
            ents = [e for e in ents if t in str(e.attributes.get("name", "")).lower() or e.entity_id in subjects]
        elif query.subject:
            ents = [e for e in ents if e.entity_id in subjects]
        if query.approved_only:
            ents = [
                e
                for e in ents
                if any(
                    self.store.facts[fid].status is FactStatus.APPROVED for fid in e.fact_ids if fid in self.store.facts
                )
            ]
        facts, ents = facts[: query.limit], ents[: query.limit]
        return RetrievalResult(facts=facts, entities=ents, miss=not facts and not ents)


__all__ = [
    "CustomerQuestion",
    "IngestionReport",
    "KnowledgePipeline",
    "KnowledgeStore",
    "OperationalRequirement",
    "StructuredRetriever",
]
