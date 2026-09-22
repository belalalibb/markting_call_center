# QEVION Platform Specification

## v3.0 — "General Agent Activity Platform: Configuration Copilot + Provider-Neutral Realtime Voice Runtime"

| Field | Value |
|---|---|
| Document | QEVION Platform Specification (authoritative) |
| Version | 3.0 — supersedes `QEVION_VOICE_RUNTIME_POC_SPEC_v2.md` v2.3 in its entirety (archived at `docs/archive/`; change map in Appendix A) |
| Status | **Binding** for every implementing agent and reviewer |
| Date | 2026-09-22 |
| Owner | QEVION |
| Inputs consolidated | SPEC v2.3 · operator master prompt (`docs/inputs/important_rebuild_master_prompt.md`, X² + X³) · pre-approval inspection report (`recovery/analysis/pre_approval_inspection_2026-09-22.md`) · verified external references (`docs/registry/`) |
| Language | English normative; Arabic executive summary |

> **Why v3 exists.** v2.3 built a strong provider-neutral voice runtime, but its Core was shaped around one deployment (a restaurant order line): "order draft" as the only truth, an ORDERING→CONFIRMING task machine, menu tools, restaurant policies. The operator's direction is a **general Agent Activity Platform**: any organization designs an *Activity* (inbound or outbound) through an intelligent **Configuration Copilot**, gets a validated, simulated, versioned **Activity Blueprint**, and runs it on a **realtime voice runtime** whose providers (config-chat LLM, runtime LLM, ASR, TTS, realtime s2s, turn detection, typed decisions) are independently replaceable. v3 keeps every v2.3 guarantee about *runtime truth and safety* (deterministic state, tools own truth, versioned contracts, replay, tenancy, privacy, budget, evidence) and re-founds everything about *what a conversation is for* on generic primitives: Activity, Field, Policy, Knowledge, Tool, Outcome, Handoff, Line, Direction.

---

## ملخص تنفيذي (Arabic Executive Summary)

1. **QEVION ليس بوت مطعم.** منصة عامة: صاحب أي نشاط (مطعم، مصنع، اتصالات، مبيعات، دعم…) يصمّم **Activity** عبر حوار ذكي، تتحول إلى **Blueprint** مُتحقَّق منه، تُختبر بالمحاكاة، ثم تعمل على Runtime صوتي حقيقي.
2. **Configuration Copilot** جزء أساسي: اكتشاف ديناميكي بلا استبيان ثابت، تحليل ملفات حقيقي (Parse → Facts → Provenance → Gaps → Conflicts)، اكتشاف أسئلة العملاء واعتراضاتهم، ربط المتطلبات بقدرات المنصة، ولا يخترع أي قاعدة تجارية — يسأل صاحب النشاط.
3. **الـ Core عام:** لا `if restaurant` في النواة. الأنشطة تُضاف بالـ configuration والـ adapters فقط. معيار قبول قابل للقياس: ثلاث أنشطة مختلفة جوهريًا على نواة واحدة بدون تعديل.
4. **Providers منفصلة الأدوار:** شات التكوين ≠ المكالمات ≠ ASR ≠ TTS ≠ Turn ≠ Typed decisions. الـ Admin يختار كل دور مستقلًا.
5. **ناتج الموديل ليس حقيقة أعمال أبدًا.** الأسعار، الأهلية، التوفر، التأكيد، الانتقالات — مملوكة لأدوات ومنطق حتمي، مع **Claim Governance** و**Provenance**.
6. **Realtime حقيقي:** بث صوتي، VAD/endpointing/turn/interruption مفاهيم منفصلة، بروتوكول مقاطعة من 7 خطوات مُقاس زمنيًا، وليس "إيقاف صوت المتصفح".
7. **Outcome Engine** يُنتج نتائج منظمة قابلة للاستهلاك، لا ملخصات. **Handoff** حدث منظم بسياق كامل.
8. **Inbound وOutbound** مدعومان؛ Line/Endpoint وDirection مفاهيم أساسية؛ Campaign حدّ مستقبلي؛ Telephony خلف عقد transport مستقبلي.
9. **المصري العامي معيار جودة مُقاس** وليس حدًا معماريًا؛ اللغات واللهجات تُضاف بـ Locale Packs.
10. **الأمن والخصوصية والعزل والترخيص بوابات مُفرَضة:** tenant isolation، PDPL-aware، credential resolver بلا أسرار في الكود، بعد رخصة منفصل لكل كود/أوزان/بيانات/صوت/خدمة.
11. **الدليل أو لم يحدث:** كل قدرة لها evidence حقيقي؛ mocks تُثبت العقود فقط.
12. **Recovery دائم:** حالة العمل والـ checkpoints داخل المستودع؛ أي جلسة جديدة تستأنف من آخر نقطة مؤكدة.

---

## §0. How to Read and Apply This Specification

| ID | Rule |
|---|---|
| QV-META-001 | MUST / MUST NOT / SHOULD / MAY per RFC 2119/8174. |
| QV-META-002 | Every normative requirement carries a stable ID `QV-<AREA>-NNN`. Acceptance, ADRs, commits, tests, and failure reports MUST cite IDs. Prose without an ID is context. |
| QV-META-003 | Every non-trivial design choice is labeled **REQUIRED**, **EXISTING DIRECTION** (operator-approved), **RECOMMENDED**, **OPTIONAL**, **DEFERRED** (seam now, build later), or **UNVERIFIED**. Requirement, recommendation, assumption, and preference are never blurred. |
| QV-META-004 | Where v2.3 and v3.0 differ, v3.0 wins. Appendix A records the fate of every v2.3 ID. Where v3.0 is silent, v2.3 intent (provider-neutral, thin adapters, no telephony, evidence-first) carries over. |
| QV-META-005 | Deviating from a MUST requires an ADR (`docs/adr/`) citing the ID, deviation, justification, risk owner. Silent deviation is a defect. |
| QV-META-006 | An acceptance criterion is never weakened to make a test pass. If a criterion is wrong, amend the spec via ADR. |
| QV-META-007 | Evidence labels: **SPEC-DEFINED**, **PROVEN** (artifact in `evidence/`), **UNVERIFIED**, **NOT RUN** (with reason). Documentation and mocks are never PROVEN evidence of real behavior. |
| QV-META-008 | The recovery system (`QEVION_SESSION_RECOVERY_PROTOCOL.md`, `QEVION_WORK_STATE.md`, `recovery/`) is part of this specification's execution model and binding throughout the project. |

## Table of Contents

- **PART I — MISSION, SCOPE, PRINCIPLES:** §1 Mission & Product Identity · §2 Goals / Non-Goals · §3 Architectural Principles · §4 Glossary
- **PART II — ARCHITECTURE:** §5 Planes & Boundaries · §6 Generic Domain Model · §7 Tenant / Business / Customer · §8 Line / Endpoint / Channel / Direction
- **PART III — ACTIVITY:** §9 Activity Model & Blueprint · §10 Lifecycle & Readiness · §11 Preflight · §12 Objective & Policy Model · §13 Coverage Model
- **PART IV — CONFIGURATION PLANE:** §14 Configuration Copilot · §15 Knowledge Ingestion · §16 Capability Registry & Mapping · §17 Simulation & Adversarial Simulation · §18 Operator Approval & Activity Versioning
- **PART V — CONVERSATION RUNTIME CORE:** §19 Runtime & State Machines · §20 Context, Memory, Reference Resolution · §21 Conversation Intelligence · §22 Business Truth, Claim Governance, Provenance · §23 Tools · §24 Confirmation · §25 Human Handoff · §26 Outcome Engine · §27 Error & Recovery Model
- **PART VI — VOICE:** §28 Voice Architecture & Media Topology · §29 Transport · §30 Turn Plane · §31 Interruption · §32 Provider Ports · §33 Composition & Router Boundary · §34 Language, Locale, Dialect, Pronunciation, Egyptian Benchmark · §35 Telephony Future Seam · §36 Outbound Activities & Campaign Boundary
- **PART VII — CONTRACTS:** §37 Event Model & Contract Design · §38 Versioning
- **PART VIII — SAAS FOUNDATIONS:** §39 Security, Privacy, Tenancy, Credentials · §40 Observability & Audit · §41 Performance & Latency · §42 Cost & Resource Model
- **PART IX — VERIFICATION:** §43 Testing · §44 Evaluation · §45 Replay & Regression · §46 Red-Team Matrix · §47 Risk Register · §48 Self-Improvement & Operator Control
- **PART X — EXECUTION:** §49 Reference Registry & License Gate · §50 POC Scope · §51 Implementation Gates & Phases · §52 Acceptance Criteria · §53 Evidence Model · §54 Example Activities · §55 Assumptions Ledger · §56 Traceability Matrix
- **APPENDICES:** A v2.3→v3.0 change map · B master-prompt traceability · C repository structure · D ID prefix index · E example Blueprint

---

# PART I — MISSION, SCOPE, PRINCIPLES

## §1. Mission and Product Identity

### 1.1 What QEVION is

QEVION is a **general-purpose Agent Activity Platform** with two product halves sharing one contracts package:

1. **Design / Configuration Plane** — a Configuration Copilot that converts vague business intent ("عايز خط استقبال", "عايز خط outbound للمبيعات") plus uploaded business material into an explicit, validated, simulated, versioned **Activity Blueprint**.
2. **Execution Plane (Runtime)** — a provider-neutral, channel-neutral conversation runtime with a true realtime voice path that executes Activity versions, owns all business-consequential state, produces structured **Outcomes**, and hands off to humans when required.

Restaurant, telecom, factory, retail, clinic/service, sales, support, retention, lead qualification, appointments, reorder, follow-up, offer announcement, information services are **deployments**, not architecture. Egyptian Arabic is the **first quality benchmark**, not a boundary.

| ID | Requirement |
|---|---|
| QV-MISSION-001 | The Core MUST NOT contain business-domain assumptions (products, menus, offers, plans, equipment) or business-branching (`if restaurant`, `if telecom`, `if activity == "..."`). Generality MUST be structurally visible in contracts, configuration, runtime, and acceptance tests (QV-ACC-001). |
| QV-MISSION-002 | The platform MUST support inbound and outbound Activities with the same runtime primitives (§36). |
| QV-MISSION-003 | Configuration Copilot and Runtime are separate planes with separately selectable providers; the Copilot is never the production agent and never a source of business truth (§14). |
| QV-MISSION-004 | This POC exists to obtain **engineering evidence** — for the runtime, for the Copilot, and for the seams — before investing in telephony, campaigns, and SaaS machinery. STOP is a legitimate outcome (§51). |

### 1.2 Conceptual flow

```text
 DESIGN                                              EXECUTION
 Operator ──chat/files──▶ Configuration Copilot       Customer voice ──▶ Transport ──▶ Turn Plane ──▶ CORE
            ◀──questions/gaps/proposals──              ▲                                             │ activity engine, policies,
 Knowledge Ingestion ─▶ Facts + Provenance             │ audio out                                   │ tools, claims, outcome
 Capability Registry ─▶ "Can QEVION do this?"          │                                             ▼
 Blueprint Proposal ─▶ Validation ─▶ Preflight ─▶ Simulation ─▶ Approval ─▶ ActivityVersion ──▶ runtime pins version
                                                                 Provider Ports (s2s | asr+llm+tts | turn | decision)
                                                                 Outcome ─▶ sinks · Handoff ─▶ sinks
```

## §2. Goals and Non-Goals

### 2.1 In scope (POC v3)

| ID | Scope item |
|---|---|
| QV-SCOPE-001 | Contracts package: all `qevion.contracts.*.v1` types + generated JSON Schemas + round-trip tests (§37). |
| QV-SCOPE-002 | Generic Core: activity engine, dialog + activity machines (data-driven), FieldStore with provenance, policy engine, claim governor, tool pipeline, confirmation, handoff, outcome engine, interaction record, budget guard, event log, replay (§19–§27). |
| QV-SCOPE-003 | Knowledge ingestion for CSV/XLSX/TXT/PDF/DOCX/JSON with facts, provenance, source priority, gap/conflict/ambiguity detection (§15). |
| QV-SCOPE-004 | Activity Blueprint schema, validator, preflight, readiness lifecycle, versioning, operator approval (§9–§11, §18). |
| QV-SCOPE-005 | Configuration Copilot: dynamic discovery, question prioritization, customer-question & objection discovery, capability mapping, coverage model, two-output contract, copilot evaluation (§14). |
| QV-SCOPE-006 | Capability Registry (machine-readable) consumed by Copilot and Preflight (§16). |
| QV-SCOPE-007 | Simulation (personas) and adversarial simulation through the same runtime (§17). |
| QV-SCOPE-008 | Realtime voice path: browser AudioWorklet PCM16 ↔ WebSocket ↔ runtime; OpenAI Realtime adapter (external-turn + provider-VAD modes); Gemini Live stub with fixtures; mocks for every port (§28–§32). |
| QV-SCOPE-009 | Turn Plane: Silero VAD default, Smart Turn (semantic) candidate, provider-delegated mode; unified `TurnEvent` taxonomy (§30). |
| QV-SCOPE-010 | Seven-step interruption protocol with per-level timing (§31). |
| QV-SCOPE-011 | Provider role ports `s2s`, `llm`, `asr`, `tts`, `turn`, `decision` (+ `transport`, `tool_backend`, `knowledge_source`, `handoff_sink`, `outcome_sink`), each independently selectable by Admin (§32–§33). |
| QV-SCOPE-012 | Locale Packs (`ar-EG` first), Language Capability Registry, Pronunciation layer, Egyptian benchmark rubric (§34). |
| QV-SCOPE-013 | Outbound direction semantics + contact-policy hooks + simulated dial; three materially different example Activities (§36, §54). |
| QV-SCOPE-014 | One web application (TypeScript) with three modes: Configuration Center, Operator Console (live/scenario/replay), Admin (provider registry, limits, **temporary test-credential UI**) (§14.5, §39.6, §43.7). |
| QV-SCOPE-015 | Multi-tenant isolation, privacy posture (Egypt PDPL 151/2020 aware), metering, budget guards, security controls (§39–§42). |
| QV-SCOPE-016 | Observability with trace hierarchy, metrics records, scrubbing; evaluation harness (runtime + copilot); replay regression; evidence pack; final report with decision record (§40, §43–§45, §51–§53). |
| QV-SCOPE-017 | Reference & license registries; ADRs; traceability matrix; recovery system (§49, §56, QV-META-008). |

### 2.2 Explicitly out of scope (anti-scope)

| ID | Prohibition |
|---|---|
| QV-ANTI-001 | No SIP/PSTN/GSM/SIM gateway/PBX/carrier/phone-number provisioning/telecom billing. Telephony = contract slot only (§35). |
| QV-ANTI-002 | No custom WebRTC/media engine or codec work; browser WebSocket PCM16 is the POC transport; WebRTC via a foundation is a future transport adapter. |
| QV-ANTI-003 | No microservices; one runtime process + one web app. Logical boundaries are mechanically enforced instead. |
| QV-ANTI-004 | No production databases/clusters; SQLite/JSONL behind storage interfaces. |
| QV-ANTI-005 | No voice model training or cloning; no payments (PCI scope zero). |
| QV-ANTI-006 | No automatic provider failover implementation (design only, §33). |
| QV-ANTI-007 | No campaign execution engine, CRM/ERP integrations, billing/invoicing, RBAC platform, OAuth developer platform, or webhook infrastructure beyond a local stub. |
| QV-ANTI-008 | No production-readiness or compliance-certification claims. |
| QV-ANTI-009 | No vector database unless a measured retrieval need justifies it (§15). |
| QV-ANTI-010 | No live GPU-hosted local ASR/TTS in the sandbox POC; local candidates ship as registry entries + fixture-only adapters (§49) unless a GPU host is provided. |

### 2.3 Deferred but designed-for (seam now, build later)

Telephony transport · additional providers · failover/circuit breaker · summarizer-based context compaction · recording pipeline · per-tenant BYOK · billing · PII redaction service · vision/multimodal input · human-agent console · campaign orchestration · router engine (model classes / auto-routing) · semantic retrieval · HTTP/webhook tool backends · CRM/webhook handoff & outcome sinks · learning loop · hosted deployment · RBAC · integration API surface (`integration.v1`).

## §3. Architectural Principles (Golden Rules)

| ID | Principle |
|---|---|
| QV-PRIN-001 | **Planes with hard boundaries.** Admin · Design/Configuration · Control · Runtime Core · Transport · Turn · Provider Ports · Tool Backends · Contracts · Evaluation. Core imports only contracts. Boundaries are CI-enforced (import-linter) — a violation is a build failure. |
| QV-PRIN-002 | **QEVION owns state, policy, tools, outcomes, events.** Providers, transports, and the Copilot's LLM are replaceable peripherals. |
| QV-PRIN-003 | **Model output is never business truth.** Prices, availability, eligibility, confirmations, state transitions, outcomes, and fact provenance are owned by tools, approved knowledge, and deterministic Core logic. |
| QV-PRIN-004 | **Configuration over code.** A new Activity, language, policy, voice, or provider selection never requires Core changes. Adding a genuinely new *platform capability* may. |
| QV-PRIN-005 | **Contracts are versioned, typed, negotiated.** Nothing untyped crosses a boundary. |
| QV-PRIN-006 | **The Copilot proposes; the operator decides; the Core executes.** No silent business-policy creation, anywhere. |
| QV-PRIN-007 | **True realtime or nothing.** Streaming audio, incremental processing, runtime-controlled turns, output cancellation, measured interruption. Browser speech APIs are never the architecture. |
| QV-PRIN-008 | **Evidence or it didn't happen.** Every capability claim points to an artifact; mocks prove contracts only; documentation is not evidence. |
| QV-PRIN-009 | **Spend, agency, and data egress are bounded by default.** |
| QV-PRIN-010 | **Failures are classified before fixed; uncertainty is stated, not hidden.** |
| QV-PRIN-011 | **Design for extension, implement only what the POC proves.** No architectural theater. |
| QV-PRIN-012 | **Open source ≠ commercially usable.** Every code/model/weights/data/voice/service license is gated separately. |

## §4. Glossary

| Term | Meaning |
|---|---|
| **Tenant** | Security and data-isolation boundary; an organization/customer of QEVION. |
| **Business Profile** | Tenant's identity, sector descriptor (free text/tag, never Core-branching), locales, brand terms. |
| **Line / Endpoint** | First-class addressable entry point (sales line, support line, campaign line) with direction, channels, assigned Activities. Never equal to a phone number or an Activity. |
| **Direction** | `inbound` · `outbound` · `bidirectional` — property of Line and Session. |
| **Channel** | browser_voice · text · simulated · phone (future) · whatsapp (future). Transport adapters implement channels. |
| **Activity** | Versioned business execution contract: objective + constraints + capabilities + knowledge + tools + data requirements + policies + coverage + outcomes. WHAT, not a script. |
| **Activity Blueprint** | The canonical machine-readable Activity definition (`qevion.activity.v1`), produced by the Copilot and approved by the operator. |
| **Activity Version** | Immutable approved Blueprint + pinned knowledge/policy/locale/provider-config versions. What sessions run. |
| **Field** | A named datum the Activity collects, with type, validation, clarification hint, required provenance. |
| **Provenance** | `USER_STATED` · `TOOL_VERIFIED` · `SYSTEM_DERIVED` · `KNOWLEDGE_APPROVED` · `UNVERIFIED` · `UNKNOWN`. |
| **Claim** | A statement with business consequence (price, eligibility, availability, guarantee, timing). Governed as allowed / verified / uncertain / prohibited / unsupported. |
| **Knowledge Fact** | Extracted datum with source ref, location, extraction status (`stated`/`inferred`/`ambiguous`/`conflicting`/`unverified`), approval state. |
| **Coverage Model** | Structured sets of expected customer questions, objections, exceptions, escalations, and their approved handling. |
| **Preflight** | Deterministic check that an Activity Version is runnable: `READY` / `BLOCKED(reasons[])`. |
| **Session / Conversation / Interaction Record** | Session = one runtime execution; Conversation = dialogue content; Interaction Record = business-grade structured record generated by the Core. |
| **Outcome** | Structured, versioned result (`qevion.outcome.v1`): primary + secondary outcomes, fields with provenance, next actions. |
| **Handoff** | Core-decided transfer to a human/destination with a structured context snapshot. |
| **VAD / Endpointing / Turn Detection / Semantic Turn / Interruption** | Distinct concepts (§30). |
| **Provider Port** | Role-specific versioned contract (`s2s`, `llm`, `asr`, `tts`, `turn`, `decision`, …). An adapter implements a port. |
| **Composition** | How ports are wired for a session: `s2s` or `cascade{asr,llm,tts}`, plus `turn` and optional `decision`. |
| **Locale Pack** | Data + pure library for a language/dialect: numerals, quantity words, time expressions, affirm/negate/backchannel sets, normalization, pronunciation lexicon. |
| **Capability Registry** | Machine-readable inventory of what platform, enabled providers, tools, locales, and channels can do, with states `SUPPORTED / PARTIAL / UNSUPPORTED / UNVERIFIED`. |
| **Simulated Customer** | Persona-driven transport that plays the customer through the real runtime for pre-activation testing. |
| **Checkpoint** | Verified project state record (`recovery/checkpoints/`) tied to a Git SHA. |
| **Evidence Pack** | `evidence/` — every claim → artifact. |
| **PDPL** | Egypt Personal Data Protection Law 151/2020 + Executive Regulations 816/2025. |

---

# PART II — ARCHITECTURE

## §5. Planes and Boundaries

### 5.1 Plane map

```text
┌────────────────────────── WEB APP (TypeScript · one app · no secrets · no policy) ──────────────────────────┐
│  Configuration Center (operator)  │  Operator Console (live · scenarios · replay · evidence)  │  Admin      │
└───────────────────────────────────┴───────────────────────────────────────────────────────────┴─────────────┘
                              │ HTTPS/WSS · server-minted short-TTL single-session tokens
┌──────────────────────────────────────── RUNTIME PROCESS (Python) ───────────────────────────────────────────┐
│ ADMIN PLANE          │ DESIGN / CONFIGURATION PLANE         │ CONTROL PLANE          │ EVALUATION PLANE     │
│ provider registry    │ copilot/ discovery · prioritizer ·   │ blueprint store        │ eval/ graders·corpus │
│ credential resolver  │   coverage · capability mapper ·     │ validator · preflight  │ simulation/ personas │
│ limits · flags       │   composer · explainer               │ readiness lifecycle    │   · adversarial      │
│ capability registry  │ knowledge/ ingest · facts · conflicts│ approval · versioning  │ replay/ harness      │
│                      │                                      │ activation             │ evidence/ index      │
├──────────────────────┴──────────────────────────────────────┴────────────────────────┴──────────────────────┤
│ RUNTIME CORE (qevion.core): activity engine · dialog machine · activity machine (data tables) · FieldStore  │
│  · context & reference resolution · policy engine · claim governor · tool orchestrator · confirmation ·      │
│  handoff · outcome engine · interaction record · budget guard · event bus · locale-pack consumer            │
├─────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ TURN PLANE silero · smart_turn · provider_delegated · mock      TRANSPORT browser_ws · text · simulated · mock│
│ PROVIDER PORTS s2s{openai_realtime, gemini_live_stub, mock} · llm{openai_chat, mock} · asr{mock, local_stub} │
│   · tts{mock, local_stub} · decision{deterministic, structured_llm, typesafe(optional)}                      │
│ TOOL BACKENDS in_memory_tenant_data · http_stub(deferred)     KNOWLEDGE SOURCES file · structured · api(def.) │
│ SINKS handoff{console, jsonl, webhook_stub} · outcome{jsonl, webhook_stub}                                   │
├─────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ CONTRACTS (qevion.contracts.*.v1) — types + JSON Schemas only, zero behavior, imported by all planes         │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 Boundary rules

| ID | Requirement |
|---|---|
| QV-ARCH-001 | `qevion.core` MUST import only `qevion.contracts` (+ stdlib / approved pure utilities). No provider SDK, transport SDK, copilot, knowledge ingestion, web, or storage driver — not even transitively. |
| QV-ARCH-002 | `qevion.copilot` and `qevion.knowledge` MUST NOT import Core runtime internals or write runtime state. Their only output toward execution is a `BlueprintProposal` that passes Control-Plane validation → preflight → approval → `ActivityVersion`. |
| QV-ARCH-003 | Adapters (providers, transports, turn detectors, tool backends, sinks) MUST be thin: auth, session creation, translation, capability declaration, error normalization, provider-specific config. Zero business logic, prompts, policy, or state machines. |
| QV-ARCH-004 | `qevion.contracts` contains types/schemas only — no I/O, no behavior. |
| QV-ARCH-005 | Boundaries MUST be enforced by import-linter contracts in CI plus a grep gate rejecting business-domain terms in `core/` (`scripts/recovery/verify.sh` step 3 and CI). |
| QV-ARCH-006 | `qevion.runtime` (wiring) is the ONLY package that knows concrete implementations; it composes Core + adapters from Admin configuration and the session's ActivityVersion. |
| QV-ARCH-007 | The web app MUST NOT contain provider keys, master tokens, tenant secrets, policy logic, or business truth. It is media + UI shell + API client. |
| QV-ARCH-008 | Physical deployment is a modular monolith; logical separation is mandatory, physical separation optional later. |
| QV-ARCH-009 | Storage is per responsibility behind interfaces: config/blueprints · knowledge facts · session/event log (append-only) · usage ledger (append-only) · evaluation data. No single-database mandate. |
| QV-ARCH-010 | Copilot provider failure MUST be isolated from the runtime and from canonical Activity data (§14). |

### 5.3 Ownership matrix

| Concern | Owner |
|---|---|
| Activity semantics, fields, policies, coverage, outcome schema | **Activity Version (data)** authored via Copilot + operator |
| Conversation state, activity state, field values + provenance, tool orchestration, confirmation, claim governance, handoff decision, outcome determination, events, metrics, budget | **Runtime Core** |
| Discovery, gap/conflict detection, question prioritization, coverage construction, capability mapping, blueprint proposal | **Configuration Plane** |
| Validation, preflight, readiness, approval, versioning, activation | **Control Plane** |
| Provider selection per role, credentials, limits, flags, capability registry | **Admin Plane** |
| Audio movement; VAD/turn signals | **Transport / Turn Plane** |
| Intelligence, speech synthesis/recognition, typed decisions | **Providers** (measured, never trusted) |
| Business truth data (catalog, plans, equipment, prices, hours) | **Tenant data + approved knowledge** via tools |
| Graders, corpus, simulation, replay, evidence | **Evaluation Plane** |
| Telephony, campaigns, billing, RBAC, CRM | **Deferred** (seams only) |

## §6. Generic Domain Model

| ID | Requirement |
|---|---|
| QV-DOM-001 | The domain model MUST define and relate at least: Tenant, BusinessProfile, Customer/Contact, Line, Channel, Direction, Activity, ActivityVersion, Objective, Policy, PolicyVersion, Knowledge, KnowledgeVersion, Capability, Tool, Conversation, Session, InteractionRecord, CustomerContext, Field, Claim, Outcome, NextAction, Campaign (boundary), Provider, Model, VoiceProfile, LocalePack, Event, Trace, Evaluation, Handoff, Checkpoint. |
| QV-DOM-002 | No domain-specific concept (menu item, plan, machine, appointment) is a Core primitive. They live in tenant data / knowledge schemas and are referenced through generic **Entity** records (`entity_type`, `entity_id`, attributes map, source ref). |
| QV-DOM-003 | Relationships: Tenant 1..n Line; Line 1..n ActivityAssignment; Activity 1..n ActivityVersion; Session → exactly one ActivityVersion, Line, Direction, Channel; Session 1..n Turn; Session → 1 InteractionRecord → 1 Outcome; ActivityVersion → pinned PolicyVersion(s), KnowledgeVersion(s), LocalePack version, VoiceProfile version, Composition config version. |

## §7. Tenant / Business / Customer Model

| ID | Requirement |
|---|---|
| QV-TEN-001 | `tenant_id` is bound at session creation from authenticated server context (never client claims or model arguments) and stamped on every event, field, tool call, usage record, log line, knowledge fact, and blueprint. |
| QV-TEN-002 | All tenant data is stored and accessed tenant-scoped in **both planes**; cross-tenant access is impossible by construction and proven by tests in runtime AND copilot/knowledge paths. |
| QV-TEN-003 | Exactly one provider session per QEVION session; no pooling across tenants. Context assembly includes only the session's tenant content; caches never mix tenants. |
| QV-TEN-004 | BusinessProfile: display name, sector descriptor (informational, never branched on), default locales, brand terminology, pronunciation lexicon refs, source-priority defaults. |
| QV-TEN-005 | Customer/Contact is an opaque reference with optional attributes and consent/contact-policy state. Persistent customer context sits behind `customer_context.v1` (DEFERRED: interface + in-memory store only). Session context, customer profile, learned preferences, evidence/confidence are separate stores. |
| QV-TEN-006 | Per-tenant provider credentials (BYOK) supported by schema as secret **references** (DEFERRED). |
| QV-TEN-007 | Operator identity recorded on every authored decision (`proposed_by`, `approved_by`) so a future RBAC layer has data (RBAC DEFERRED). |

## §8. Line / Endpoint / Channel / Direction

| ID | Requirement |
|---|---|
| QV-LINE-001 | `Line` (`qevion.line.v1`) is first-class: `line_id, tenant_id, display_name, direction ∈ {inbound, outbound, bidirectional}, channels[], activity_assignments[]{activity_id, activity_version, routing_rule}, contact_policy_ref, status`. |
| QV-LINE-002 | Direction is independent of Activity where possible; a Line may host several Activities routed by rule (default, time window, contact attribute, explicit selection in POC UI). |
| QV-LINE-003 | A phone number, WebSocket path, or WhatsApp ID is a **channel address** attached to a Line, never an Activity. |
| QV-LINE-004 | Channel and transport are adapters; Core has no channel-specific business logic. Activity, Objective, Policy, Knowledge, Tools, Outcome, Conversation State are reusable across channels. POC channels: `browser_voice`, `text`, `simulated`. |
| QV-LINE-005 | Sessions record `line_id`, `direction`, `channel`, `channel_address_ref` on `session.created` and in the InteractionRecord. |

---

# PART III — ACTIVITY

## §9. Activity Model and Blueprint (`qevion.activity.v1`)

An Activity is a **versioned business execution contract**: WHAT the organization wants accomplished and within which constraints; the runtime determines HOW conversationally. Not a finite intent list, not a fixed dialogue graph (constrained-flow mode exists only as an optional explicit configuration).

### 9.1 Blueprint structure (normative shape; JSON Schema generated from the typed model)

```yaml
schema: qevion.activity.v1
identity: { tenant_id, line_id?, activity_id, name, description, version, status }
direction: inbound | outbound | bidirectional
channels: [browser_voice, text, ...]
locale: { language, locale, dialect, locale_pack_ref, voice_profile_ref, pronunciation: [ {term, hint, scope} ] }
objective:
  primary: { kind, description }                 # kind = free text + optional metric tag
  secondary: [ ... ]
  optimization_bounds: { truthfulness: required, no_invented_urgency: true, respect_opt_out: true }
data:
  required: [ { name, type, validation, clarification_hint, provenance_required: USER_STATED|TOOL_VERIFIED, sensitivity } ]
  optional: [ ... ]
knowledge:
  sources: [ { source_id, kind: file|structured|api, version, priority } ]
  requirements: [ { domain, description, status: SATISFIED|MISSING|PARTIAL } ]
  source_priority: [ live_api, approved_structured, approved_document, historical ]
  freshness: { max_age_days?, stale_behavior }
tools:
  required: [ { tool_id, purpose } ]
  optional: [ ... ]
  permissions: { <tool_id>: { impact: read|write|escalation, confirmation: none|confirm_before_execute, authorization_scope } }
policies:
  allowed_claims: [ { claim_type, scope, source_requirement } ]
  prohibited_claims: [ { claim_type, scope } ]
  disclosures: [ { when, text_ref } ]
  clarification_policy: always_when_ambiguous | when_high_impact
  unknown_question_policy: { default: <behavior>, overrides: [ {topic_pattern, behavior} ] }      # §12.3
  uncertainty_policy: { missing, conflicting, stale, ambiguous }                                    # each: <behavior>
  escalation: [ { trigger, action, priority } ]
  opt_out: { phrases_ref, action }
  contact_policy_hooks: { consent_required, attempt_limit, contact_window, suppression_ref }        # outbound
coverage:                                                                                           # §13
  questions:  [ { id, category, entity_ref?, pattern, handling: KNOWLEDGE|TOOL|CLARIFY|LIMITATION|HANDOFF, answer_ref?, status: COVERED|ASK_OWNER|DECLINED } ]
  objections: [ { id, pattern, approved_response_ref?, allowed_alternatives[], status } ]
  exceptions: [ { id, situation, behavior } ]
completion: { success_rules: [ ... ], failure_rules: [ ... ], exit_rules: [ ... ] }
outcome_schema:
  primary:  [ accepted, rejected, callback_requested, not_eligible, completed, partially_completed, human_required, no_answer, abandoned, unsupported, technical_failure, <activity-defined…> ]
  secondary: [ ... ]
  fields: [ { name, source_field?, required } ]
  next_actions: [ schedule_callback, create_lead, handoff, retry, send_followup, close, request_more_information, <activity-defined…> ]
handoff_rules: [ { trigger, destination_ref, priority, context_projection } ]
activity_machine: { table_ref | inline }        # data-driven (§19); generic default table if omitted
constrained_flow?: { enabled: false, steps: [] } # OPTIONAL mode only
evaluation: { cases: [ ... ], simulation_personas: [ ... ], adversarial_cases: [ ... ] }
version_metadata:
  sources: [ upload refs ]
  decisions: [ { item_path, proposed_by, approved_by, ts, rationale } ]
  rejected_suggestions: [ ... ]
  pinned: { policy_versions, knowledge_versions, locale_pack, voice_profile, composition_config }
  readiness: { state, preflight_result_ref, simulation_report_ref }
```

| ID | Requirement |
|---|---|
| QV-ACT-001 | The Blueprint MUST be expressed in QEVION semantics only — never as a provider prompt format. Instruction rendering happens in the Core's instruction composer + adapters and is regenerable from the Blueprint. |
| QV-ACT-002 | Every element encoding a business decision (claims, prices, eligibility, refunds, delivery promises, escalation, contact permissions, objection responses) MUST carry `Decision{proposed_by: copilot\|operator\|source_doc, approved_by: operator_id, ts}`; unapproved elements block activation. |
| QV-ACT-003 | `unknown_question_policy` and `uncertainty_policy` are REQUIRED for activation; "the model decides" is not a valid value. |
| QV-ACT-004 | Field names, entity types, and outcome enums are Activity data; Core knows none of `customer_name`, `plan`, `menu_item`, etc. |
| QV-ACT-005 | A minimal informational Activity needs only identity, objective, knowledge, locale, channel, outcome_schema, unknown/uncertainty policies. Complexity is added only when the objective requires it (capability-driven, not field-driven). |
| QV-ACT-006 | Blueprints are validated against the versioned JSON Schema at load; invalid → fail fast with precise path errors. |

## §10. Lifecycle and Readiness

```text
DRAFT → DISCOVERY_IN_PROGRESS → NEEDS_INFORMATION ⇄ NEEDS_CONFIGURATION → (BLOCKED) → READY_FOR_SIMULATION
      → SIMULATION_FAILED ⇄ READY_FOR_SIMULATION → READY_FOR_ACTIVATION → ACTIVE → SUSPENDED → RETIRED
```

| ID | Requirement |
|---|---|
| QV-LIFE-001 | Readiness is an explicit Control-Plane state machine with a declared transition table; transitions are Control-authored events (`activity.readiness_changed`), never chat-inferred. |
| QV-LIFE-002 | `ACTIVE` requires ALL: schema-valid Blueprint · Preflight `READY` · simulation report meeting activation thresholds (§17) · every business decision approved · new immutable ActivityVersion. Ending a chat never activates anything. |
| QV-LIFE-003 | `SUSPENDED` stops new sessions immediately; live sessions finish on their pinned version. `RETIRED` versions remain replayable and auditable. |
| QV-LIFE-004 | Any edit after `READY_FOR_ACTIVATION` returns the draft to the appropriate earlier state; approved versions are never mutated. |

## §11. Preflight

| ID | Requirement |
|---|---|
| QV-PRE-001 | Preflight is deterministic Control-Plane code returning `READY` or `BLOCKED{reasons:[{code, path, detail, fix_hint}]}`. It runs before activation and (cheaply) before every real-provider session start. |
| QV-PRE-002 | Minimum reason codes: `MISSING_REQUIRED_KNOWLEDGE`, `MISSING_REQUIRED_TOOL`, `TOOL_NOT_AUTHORIZED_FOR_TENANT`, `UNSUPPORTED_CAPABILITY`, `UNSUPPORTED_LOCALE_COMBINATION`, `VOICE_UNAVAILABLE`, `CONTRADICTORY_POLICIES`, `MISSING_OUTCOME_SCHEMA`, `IMPOSSIBLE_COMPLETION_CRITERIA`, `PROVIDER_CAPABILITY_UNAVAILABLE`, `INCOMPLETE_FIELD_DEFINITION`, `INCOMPATIBLE_CONFIRMATION_RULE`, `UNDEFINED_ESCALATION`, `UNDEFINED_UNKNOWN_QUESTION_POLICY`, `UNAPPROVED_BUSINESS_DECISION`, `UNRESOLVED_KNOWLEDGE_CONFLICT`, `INVALID_CONFIG`, `UNSUPPORTED_CHANNEL`, `CONTACT_POLICY_MISSING_FOR_OUTBOUND`, `LICENSE_BLOCKED_COMPONENT`. |
| QV-PRE-003 | Preflight consumes the Capability Registry (§16) and Language Capability Registry (§34) — never hardcoded capability assumptions. |
| QV-PRE-004 | The runtime MUST refuse to start a session on a `BLOCKED` version and emit `activity.blocked` with reasons. |

## §12. Objective and Policy Model

| ID | Requirement |
|---|---|
| QV-OBJ-001 | Objectives are declared (primary + secondary) with optional measurable tags (conversion, qualification, retention, resolution, completion, callback, data_collection; secondary: completeness, satisfaction, efficiency, successful_handoff, reduced_repetition). Tags feed evaluation, never Core branching. |
| QV-OBJ-002 | Optimization is bounded by truthfulness, business policy, safety, legal/compliance, user autonomy, explicit Activity rules. Conversion pressure is never permission to deceive, invent urgency/discounts/eligibility/availability, or ignore opt-out. |
| QV-POL-001 | Policies are first-class versioned data (`qevion.policy.v1`) governing claims, tools, data access, confirmation, handoff, outbound behavior, opt-out, escalation, channel restrictions, provider/model restrictions, disclosures, retention. |
| QV-POL-002 | Enforcement occurs in the Core independently of model intent: prompt text is guidance; policy engine, claim governor, tool pipeline, and confirmation interpreter are the enforcement. A policy that exists only as prompt text is a defect. |
| QV-POL-003 | Every policy evaluation emits `policy.checked{policy_id, version, decision, reason}`. |
| QV-POL-004 | **Unknown-question / uncertainty behaviors (enum):** `ANSWER_FROM_APPROVED_KNOWLEDGE` · `ASK_CLARIFYING_QUESTION` · `STATE_LIMITATION` · `USE_AUTHORIZED_TOOL` · `ASK_OPERATOR_SOURCE` · `OFFER_HUMAN_HANDOFF` · `COLLECT_QUESTION` · `REQUEST_ADDITIONAL_INFORMATION` · `CLOSE_GRACEFULLY` · `DECLINE_UNSUPPORTED_REQUEST`. The runtime detects "not covered" via Core logic (knowledge miss + claim governor + decision-port signal), applies the configured behavior, and records `coverage.miss{topic, behavior_applied}` for the quality loop (§48). |

## §13. Coverage Model

| ID | Requirement |
|---|---|
| QV-COV-001 | The Copilot MUST build a structured coverage model — not a script, not a fixed FAQ: Objective, Knowledge, Question, Objection, Tool, Policy, Exception, Escalation, Outcome, Recovery coverage. |
| QV-COV-002 | Question discovery is entity- and category-driven: per important entity consider price, variants, differences, ingredients/materials/specs, compatibility, eligibility, availability, timing, location, delivery/service limits, alternatives, recommendation, comparison, objections, complaints, cancellation/change, follow-up, clarification, correction, unrelated, unsupported. Each generated question maps to handling and status (`COVERED / ASK_OWNER / DECLINED`). |
| QV-COV-003 | Objection discovery is REQUIRED for persuasive Activities (sales, retention, reorder, offers): likely objections (price, no need, has alternative, will think, offer duration, differences, eligibility…) each mapped to an approved response or `ASK_OWNER`. The Copilot never invents the commercial answer. |
| QV-COV-004 | Coverage status feeds readiness: `ASK_OWNER` items classified `REQUIRED_FOR_EXECUTION` or `POLICY_RISK` block activation; `IMPORTANT_FOR_QUALITY` warns; `OPTIONAL_IMPROVEMENT` informs. |
| QV-COV-005 | Coverage items become evaluation and simulation cases automatically (§17, §44). |

---

# PART IV — CONFIGURATION PLANE

## §14. Configuration Copilot

**Role:** Understand → Discover → Inspect → Challenge → Fill Gaps → Map Capabilities → Propose → Simulate → Validate → Produce an executable Activity Blueprint. **Non-role:** not the production agent, not the runtime, not a source of business truth, never invents business rules.

| ID | Requirement |
|---|---|
| QV-COP-001 | The operator starts with a natural statement ("عايز خط استقبال") and is never required to understand architecture, provider APIs, ASR/TTS, state machines, tool schemas, prompts, or event contracts. |
| QV-COP-002 | **Dynamic discovery, no fixed questionnaire.** The next question is computed from current Blueprint state, previous answers, ingested knowledge, contradictions, missing required fields, likely customer questions, objective, required tools, policy and outcome requirements, channel, provider capabilities, detected uncertainty. A static question list is a defect (§46). |
| QV-COP-003 | **Question prioritization** by blocking importance, business impact, safety/policy impact, frequency likelihood, outcome impact, dependency impact, uncertainty. Few high-value questions per turn; explain why a question matters. |
| QV-COP-004 | **Stop-asking intelligence.** Discovery concludes when required intent, knowledge, tools (or explicit deferral), coherent policies, unknown-question behavior, outcomes, critical gaps, required capabilities, and readiness conditions are satisfied → REVIEW → SIMULATION → VALIDATION. It resumes only for a newly discovered meaningful gap. |
| QV-COP-005 | **Progressive disclosure:** objective → direction → business context; then knowledge → expected questions → objections → tools → policies → outcomes → edge cases → simulation. |
| QV-COP-006 | **Ask-the-owner escape hatch.** Any business decision that cannot be safely derived becomes an explicit `ASK_OWNER` question; the Copilot never fills it. |
| QV-COP-007 | **No silent business policy creation** — discounts, prices, guarantees, eligibility, refund rules, availability, delivery promises, escalation, contact permissions come only from operator or authoritative sources, with provenance. |
| QV-COP-008 | **Capability-aware answers** from the Capability Registry: `SUPPORTED / SUPPORTED_WITH_CONFIGURATION / REQUIRES_TOOL / REQUIRES_PROVIDER_CAPABILITY / REQUIRES_NEW_PLATFORM_CAPABILITY / UNSUPPORTED / UNVERIFIED`. Never pretend a capability exists because the LLM can talk about it. |
| QV-COP-009 | **Integration discovery:** classify each requirement as `no integration needed / configuration only / existing integration available / new integration required / new core capability required`. |
| QV-COP-010 | **Provider/capability fit:** verify the selected composition supports required language, dialect, voice, streaming, interruption, latency class, tool calling, context size; surface gaps, never hide them. |
| QV-COP-011 | **"What could go wrong?" challenge pass** producing structured readiness findings (misunderstanding paths, missing info, unverified claims, unanswered questions, missing tools, unauthorized actions, policy conflicts, indistinguishable outcomes, repetition/stuck risks, mind-change, unrelated question, interruption, provider failure, knowledge unavailable, tool error, human request). |
| QV-COP-012 | **Call-quality and efficiency review:** flag repeated questions, unnecessary data requests, long explanations, redundant confirmations, asking known data, poor objection handling, premature closing, missing next action, verbosity; propose improvements as recommendations. Efficiency never skips required disclosures or confirmation. |
| QV-COP-013 | **Outcome design:** recommend outcome fields from objective; operator accepts/rejects/modifies; schema explicit and versioned. |
| QV-COP-014 | **Operator control:** accept / reject / edit / add / remove / override / request another suggestion; preserve *AI suggestion* vs *operator-approved*. |
| QV-COP-015 | **Two outputs, never conflated:** (A) human explanation — known / missing / detected / recommended / needs your decision / ready?; (B) machine-readable `BlueprintProposal` — Blueprint draft, provenance, classified gaps, risks, capability requirements, validation findings, simulation cases, readiness state. |
| QV-COP-016 | **No bypass:** proposal → schema validation → capability validation → policy validation → operator approval → versioned Activity → runtime. The Copilot has no write path to runtime state, tenant data, or tools. |
| QV-COP-017 | **Security:** operator messages and uploads are untrusted data; extraction is schema-only; document text delimited as data; injection patterns logged as security events; no tool execution from the Copilot; no cross-tenant knowledge; provider credentials never visible to the Copilot model. |
| QV-COP-018 | **Provider:** Admin-configured `llm` port role `config_chat`, independent of runtime providers, replaceable without invalidating Blueprints. |
| QV-COP-019 | **Failure isolation:** configuration session state persisted after every step; on provider failure preserve state, prevent partial corruption, allow retry or substitution, never lose canonical data. |
| QV-COP-020 | **Observability:** configuration session events — questions, answers, uploads, extracted facts, gaps, conflicts, proposals, decisions, validation failures, simulation findings, readiness transitions, provider/model/version, latency, errors — minimal retention of sensitive content; sessions replayable. |
| QV-COP-021 | **Evaluation** (§44) REQUIRED: gathers requirements, avoids unnecessary questions, detects missing info/contradictions, inspects uploads correctly, identifies questions/objections/tool needs/policy gaps, produces valid Blueprints, invents no facts, preserves decisions, detects unsupported capabilities, produces simulation-ready Activities, improves from evidence. |
| QV-COP-022 | **UX:** an experienced solution architect — concise or detailed as needed, contextual, remembers answers, proposes defaults, challenges inconsistencies, says "I don't know" / "requires another capability". |

**Loop (normative pattern):** Source Material → Extracted Knowledge → Detected Gap → Business Question → Operator Answer → Validated Fact → Blueprint → Simulation → New Gap → Refinement … until READY or BLOCKED (adaptive).

**Internal shape (RECOMMENDED; boundaries REQUIRED):** `DiscoveryEngine` (state → gaps) · `QuestionPrioritizer` (deterministic ranking) · `CoverageBuilder` (entity × category + LLM-proposed patterns, schema-validated) · `CapabilityMapper` (deterministic registry lookup) · `BlueprintComposer` (merges approved facts/decisions) · `Explainer`. LLM calls via `llm` port with JSON-schema outputs; `decision` port classifies gaps/questions/conflicts. Deterministic components own state; the LLM never mutates the Blueprint directly.

## §15. Knowledge Architecture and Ingestion

| ID | Requirement |
|---|---|
| QV-KNOW-001 | Knowledge is generic (catalogs, plans, equipment, FAQs, policies, eligibility, procedures, org info, locations, hours, limitations, offers, structured data). Domain shapes live in knowledge schemas/tenant data, never in Core. |
| QV-KNOW-002 | POC upload kinds: CSV, XLSX, TXT, PDF, DOCX, JSON/YAML. Parser set extensible via `knowledge_source.v1`. |
| QV-KNOW-003 | **Pipeline (normative order):** Upload → Parse → Normalize → Identify Entities → Extract Facts → Identify Relationships → Detect Missing Information → Detect Contradictions → Detect Ambiguity → Identify Customer-Facing Questions → Identify Operational Requirements → Feed Activity design. "Attach file to prompt" is a defect. |
| QV-KNOW-004 | Every Fact: `source_id, source_version, location, extraction_status ∈ {stated, inferred, ambiguous, conflicting, unverified}, confidence, approval ∈ {proposed, operator_approved, rejected}`. LLM-extracted facts start `proposed`; only operator approval (or an authoritative structured source with priority) makes them `KNOWLEDGE_APPROVED`. |
| QV-KNOW-005 | **Conflicts:** same entity+attribute with differing values across sources → `CONFLICT_DETECTED`; never silently merged; resolved by operator or explicit `source_priority`. |
| QV-KNOW-006 | **Gap classes:** `REQUIRED_FOR_EXECUTION`, `IMPORTANT_FOR_QUALITY`, `OPTIONAL_IMPROVEMENT`, `POLICY_RISK`, `DATA_CONFLICT`, `UNKNOWN`. |
| QV-KNOW-007 | Retrieval: structured lookup first (exact + alias + fuzzy with thresholds, locale-pack normalized); semantic retrieval OPTIONAL behind `retrieval.v1` when a measured need exists. |
| QV-KNOW-008 | Knowledge is versioned; Activity versions pin knowledge versions; sessions record them. |
| QV-KNOW-009 | Uploads are untrusted: size/type limits, delimiting, injection logging, tenant-scoped storage, retention policy. |
| QV-KNOW-010 | Facts consumed at runtime MUST be `KNOWLEDGE_APPROVED` or `TOOL_VERIFIED`; `proposed` facts are never spoken as truth. |

## §16. Capability Registry (`qevion.capability_registry.v1`)

| ID | Requirement |
|---|---|
| QV-CAP-001 | Machine-readable registry aggregating platform primitives, registered tools (impact/scope), enabled provider ports with negotiated capabilities, locale packs, voice profiles, channels, unknown-question behaviors, decision-port availability — states `SUPPORTED / PARTIAL / UNSUPPORTED / UNVERIFIED`. |
| QV-CAP-002 | Copilot and Preflight MUST read the registry; no duplicated hand-written capability list in prompts or code. |
| QV-CAP-003 | Capability mapping yields `RequirementMapping{requirement, required_capability, current_state, action}`. |
| QV-CAP-004 | Provider entries reflect verified negotiation results where available and `UNVERIFIED` otherwise; a locale code is metadata, never proof of quality. |

## §17. Simulation and Adversarial Simulation

| ID | Requirement |
|---|---|
| QV-SIM-001 | Simulation runs the **same runtime** with a `SimulatedCustomerTransport` (text-mode; optional TTS-audio mode) driven by persona scripts + a bounded LLM/decision-port "customer". Not a second engine. |
| QV-SIM-002 | Required personas: normal, confused, skeptical, demanding, follow-up asker, comparison asker, corrector, topic switcher, interrupter, unsupported-question asker; injected: tool failure, missing knowledge, human request, objection sequence, successful and unsuccessful completion. |
| QV-SIM-003 | Adversarial generator: unexpected questions, ambiguous references, contradictory info, repeated objections, rapid topic switching, missing info, corrections, policy-pushing, unsupported-claim requests, conflicting data, tool failure, provider interruption, incomplete customer info. |
| QV-SIM-004 | Output `simulation_report.v1`: per-scenario pass/fail on deterministic graders (no invented claims, required fields with correct provenance, confirmation before writes, unknown-question policy applied, handoff correctness, outcome produced, repetition below threshold) + labeled model-graded signals. Findings map to Blueprint paths → `SIMULATION_FAILED` reasons or quality gaps. |
| QV-SIM-005 | Happy-path-only simulation is a defect. Activation thresholds (default 100% safety graders, ≥ 90% completion graders over the required persona set) are fixed before running. |
| QV-SIM-006 | Simulation sessions carry `session.kind = simulation`, are budget-guarded, excluded from production metrics, included in evidence. |

## §18. Operator Approval and Activity Versioning

| ID | Requirement |
|---|---|
| QV-VER-001 | Every accepted configuration creates an immutable `ActivityVersion` preserving source refs, knowledge version, operator decisions, accepted/rejected suggestions, policy/knowledge/tool/locale/voice/composition versions, evaluation cases, simulation findings, preflight and readiness results. |
| QV-VER-002 | The audit path is reconstructible: conversation → proposal → decision → Blueprint → validation → simulation → version → activation. |
| QV-VER-003 | Approval is an explicit operator action with identity and timestamp; the Copilot cannot approve. |
| QV-VER-004 | Quality-loop recommendations (§48) create proposals against a new draft, never mutations of an active version. |
