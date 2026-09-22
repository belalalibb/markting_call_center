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
