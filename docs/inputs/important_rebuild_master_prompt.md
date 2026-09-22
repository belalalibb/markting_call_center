MASTER SPEC REWRITE PROMPT
QEVION VOICE RUNTIME — CLEAN-REPO ARCHITECTURE REWRITE
X²-ALIGNED / ZERO-REGRESSION / EXECUTION-GRADE

ROLE

You are acting as the Principal Systems Architect, Voice AI Architect, Conversation Runtime Architect, Specification Engineer, Reliability Engineer, Security Reviewer, and Red-Team Reviewer for QEVION.

Your task in this phase is NOT to implement the QEVION product.

Your task is to completely rewrite and strengthen:

    QEVION_VOICE_RUNTIME_POC_SPEC_v2.md

starting from the clean repository state and using ONLY:

    1. QEVION_VOICE_RUNTIME_POC_SPEC_v2.md
    2. README.md

as repository-provided inputs.

You may conduct fresh external research to validate and expand the reference pool and current technology landscape.

You must produce ONE coherent authoritative specification.

Do not produce an amendment.
Do not append a patch section to the old document.
Do not preserve contradictions merely because they already exist.
Do not silently discard previously relevant requirements.
Do not implement application code.
Do not modify unrelated repository files.

The resulting document must be strong enough that a future implementation agent, starting from a clean repository and receiving this specification, can implement the system without needing hidden historical context, undocumented assumptions, or access to previous implementations.


======================================================================
0. INPUT AND EVIDENCE DISCIPLINE
======================================================================

You have only two repository artifacts:

A. QEVION_VOICE_RUNTIME_POC_SPEC_v2.md
B. README.md

Treat them differently.

QEVION_VOICE_RUNTIME_POC_SPEC_v2.md is the authoritative design source that must be rewritten.

README.md is contextual and historical material.

README claims are NOT automatically proof of implementation behavior.

You must NOT pretend to have inspected:

- old source code
- deleted code
- old ZIP archives
- old tests
- old commits
- old branches
- old logs
- old runtime traces
- old evidence artifacts
- old screenshots
- old implementation details
- historical executor behavior

unless those things are literally available in the two provided files.

In the rewritten specification explicitly distinguish, where needed:

    SPEC-DEFINED
    README-CLAIMED
    PROVEN
    UNVERIFIED

Do not retroactively declare a historical implementation failure proven when the evidence is unavailable.

Do not claim that a previous executor or agent caused a failure unless the available evidence actually proves it.

Instead ask the stronger architectural question:

    "Did the previous specification permit a superficially compliant but behaviorally weak implementation?"

The new specification must close those loopholes.

README may preserve useful historical context, terminology, naming, lessons, or previous requirements, but the rewritten specification must normalize everything into one authoritative architecture.


======================================================================
1. PRIMARY OBJECTIVE
======================================================================

Rewrite the specification so that it defines an implementation-grade foundation for a general-purpose QEVION Voice Runtime and Agent Activity Platform.

The specification must define:

- what the product is
- what the system owns
- what the system does not own
- its architectural boundaries
- its domain primitives
- its runtime behavior
- its voice behavior
- its conversational behavior
- its activity model
- its outcome model
- its knowledge model
- its tool model
- its policy model
- its provider abstraction
- its channel abstraction
- its multilingual architecture
- its human handoff model
- its versioning model
- its observability model
- its evaluation model
- its security model
- its future telephony seam
- its POC boundaries
- its acceptance criteria
- its evidence requirements
- its failure handling
- its testing and regression strategy

The specification must optimize for:

1. correctness
2. behavioral truth
3. implementability
4. generality
5. reliability
6. security
7. observability
8. maintainability
9. performance
10. future extensibility

Do NOT optimize for superficial architectural complexity.

Every subsystem must have a justified reason to exist.


======================================================================
2. QEVION PRODUCT IDENTITY
======================================================================

QEVION is NOT a restaurant bot.

Restaurants may be one example deployment.

The architecture must instead represent a general-purpose Agent Runtime + Agent Builder / Activity Designer capable of supporting different organizations and business activities.

Examples include:

- restaurant
- factory
- telecom company
- retail business
- clinic or service business where appropriate
- sales organization
- customer support
- retention
- lead qualification
- appointment workflows
- reorder campaigns
- customer follow-up
- offer announcement
- outbound sales campaigns
- service requests
- information services

Do not create a restaurant-shaped core and then claim that it is generic.

Generality must be structurally visible in the domain model, contracts, configuration, runtime, and acceptance criteria.


======================================================================
3. CORE PRODUCT IDEA
======================================================================

QEVION allows an organization to define a business Activity.

An Activity describes WHAT the organization wants the AI to accomplish.

The Activity must NOT be a rigid conversation script.

The business owner should be able to define things such as:

- organization identity
- Activity name
- inbound or outbound
- business objective
- primary objective
- secondary objectives
- required information
- optional information
- knowledge sources
- required tools
- optional tools
- allowed claims
- prohibited claims
- confirmation requirements
- eligibility rules
- escalation rules
- completion conditions
- failure conditions
- exit conditions
- outcome schema
- next-action rules
- language
- locale
- dialect
- voice profile
- communication style
- compliance/policy constraints

QEVION determines HOW to accomplish the objective within those declared constraints.

The runtime must therefore be capable of dynamic conversational planning rather than following a fixed linear script.

Do not define Activity as:

    "Say A, then ask B, then say C."

A valid Activity specification defines:

    objective + constraints + capabilities + knowledge + tools + data requirements + outcomes

and allows the agent runtime to dynamically determine conversational behavior.


======================================================================
4. GENERIC DOMAIN MODEL
======================================================================

The core architecture must be expressed using generic business and runtime primitives.

At minimum define and relate:

- Tenant
- Business Profile
- Customer / Contact
- Line / Endpoint
- Channel
- Activity
- Activity Version
- Objective
- Policy
- Knowledge
- Knowledge Version
- Capability
- Tool
- Conversation
- Session
- Interaction
- Customer Context
- Outcome
- Next Action
- Campaign
- Provider
- Model
- Voice Profile
- Locale
- Dialect
- Event
- Trace
- Evaluation
- Handoff

Do not allow restaurant-specific concepts to become universal primitives.

Restaurant menu concepts, for example, belong to a domain-specific knowledge structure or tenant data model, not the universal runtime core.

The architecture must support configuration-driven expansion.


======================================================================
5. CONFIGURATION-FIRST EXTENSIBILITY
======================================================================

One of the most important requirements:

New business activities should primarily be created through configuration and capability composition.

Adding a new business Activity should NOT require modifying QEVION Core business logic merely because the business objective changed.

Examples:

A restaurant can define:

    reorder_activity

A telecom company can define:

    competitor_switch_offer

A factory can define:

    maintenance_follow_up

A sales organization can define:

    lead_qualification

A support team can define:

    issue_resolution

The same runtime primitives should execute these Activities.

Core code changes may be required when introducing genuinely new platform capabilities.

Core code changes must NOT be required merely because one tenant or Activity has a different business objective.

Make this requirement measurable.

The acceptance criteria must include at least one test demonstrating that a materially different Activity can be introduced without changing core runtime business logic.


======================================================================
6. AGENT BUILDER / ACTIVITY DESIGNER
======================================================================

Agent Builder / Activity Designer is part of the intended end product.

The architecture must allow a business operator to define, at minimum:

    company
    -> line
    -> activity
    -> objective
    -> knowledge
    -> tools
    -> policies
    -> required data
    -> completion rules
    -> outcomes

without programming the core runtime.

The Builder must represent WHAT the business wants.

It must not force the operator to manually author the entire conversational dialogue.

The future UI/API may expose structured configuration.

Do not require a specific frontend framework.

Do not make the architecture dependent on one UI technology.


======================================================================
7. ACTIVITY MODEL
======================================================================

Define Activity as a versioned business execution contract.

It must support:

Identity:
- name
- description
- business owner / tenant
- version
- status

Direction:
- inbound
- outbound
- both where valid

Objective:
- primary objective
- secondary objectives
- measurable completion conditions

Data:
- required fields
- optional fields
- validation requirements
- provenance requirements

Knowledge:
- required knowledge domains
- preferred sources
- allowed sources
- freshness expectations

Tools:
- required tools
- optional tools
- authorization requirements
- confirmation requirements

Policies:
- allowed behavior
- prohibited behavior
- claim boundaries
- disclosure requirements
- escalation requirements
- opt-out handling

Conversation:
- language
- locale
- dialect
- voice
- tone/style
- contextual behavior

Outcomes:
- primary outcome
- secondary/compound outcomes
- required fields
- next actions
- escalation result

Lifecycle:
- draft
- validated
- ready
- active
- suspended
- retired

Do not define Activity as a finite intent list.

Do not define Activity as a fixed dialogue graph unless such a graph is explicitly introduced as an optional constrained mode for a business requirement.

Dynamic reasoning remains the default model.


======================================================================
8. ACTIVITY PREFLIGHT
======================================================================

Every Activity must have a preflight validation concept.

Before execution, QEVION must be able to determine whether the Activity is actually runnable.

Preflight must identify conditions such as:

- missing required knowledge
- missing required tool
- unsupported capability
- unsupported language/dialect/voice combination
- contradictory policies
- missing outcome schema
- impossible completion criteria
- unavailable provider capability
- incomplete required data definitions
- incompatible confirmation requirements
- unsafe or undefined escalation behavior
- invalid configuration
- unsupported channel assumptions

Preflight returns at least:

    READY
    BLOCKED

The implementation must expose reasons for BLOCKED.

Do not allow the runtime to silently attempt impossible Activities.


======================================================================
9. ACTIVITY OPTIMIZATION OBJECTIVES
======================================================================

Activities may have measurable optimization objectives.

Examples:

Primary:

- conversion
- qualification
- retention
- issue resolution
- order completion
- callback booking
- data collection

Secondary:

- data completeness
- customer satisfaction
- response efficiency
- successful handoff
- reduced repetition

Optimization must remain bounded by:

- truthfulness
- business policy
- safety
- legal/compliance constraints
- user autonomy
- explicit Activity rules

The runtime must never treat conversion optimization as permission to deceive.


======================================================================
10. OUTBOUND VOICE ACTIVITIES
======================================================================

Outbound calling is a first-class architectural use case.

Example:

A telecom organization wants QEVION to call customers and present an offer.

The agent may:

- initiate the interaction
- introduce the organization
- explain the offer
- answer questions
- handle objections
- clarify eligibility
- explain applicable terms
- collect required information
- determine interest
- determine acceptance/rejection
- offer callback where appropriate
- confirm the result
- create a structured outcome

Persuasion must be natural, commercially useful, and effective while remaining:

- truthful
- non-deceptive
- non-coercive
- transparent about material terms
- free of invented urgency
- free of invented discounts
- free of invented eligibility
- free of fabricated availability
- respectful of customer opt-out or do-not-contact policy

The system must not invent business claims just to improve conversion.

Do not make outbound logic hardcoded around telecom.

The same machinery must support other outbound Activities.


======================================================================
11. CAMPAIGN BOUNDARY
======================================================================

Define Campaign as a future orchestration boundary.

Campaign may eventually include:

- audience
- target contacts
- Activity version
- schedule
- retry policy
- maximum attempts
- contact policy
- throttling
- success criteria
- outcome handling
- suppression / opt-out rules

Current POC does not need a fully featured campaign-management platform unless the existing specification explicitly requires it.

However, the architecture must not make future outbound campaigns impossible.

Campaign must remain distinct from the core conversation runtime.


======================================================================
12. LINE / ENDPOINT MODEL
======================================================================

Line / Endpoint is a first-class domain primitive.

A company may have:

- Sales Line
- Support Line
- Retention Line
- Reservations Line
- Information Line
- Campaign Line
- General Line

Each line may have assigned Activities.

Direction must be independent of the Activity where possible.

The architecture must support:

- inbound line
- outbound line
- bidirectional line

Telephony transport must remain an adapter boundary.

Do not make a phone number itself equal to an Activity.


======================================================================
13. CHANNEL-INDEPENDENT CORE
======================================================================

The same Activity model should be capable of running over different channels.

Potential channels include:

- phone
- browser voice
- web app
- WhatsApp
- mobile app
- kiosk
- future channels

Channel and transport must be adapters.

The business/runtime core must not contain channel-specific business logic.

A future implementation should be able to reuse:

    Activity
    Objective
    Policy
    Knowledge
    Tools
    Outcome
    Conversation State

across different channels.


======================================================================
14. VOICE ARCHITECTURE
======================================================================

Voice must be architecturally decomposed.

Separate logical responsibilities:

    Audio Input
    Transport
    VAD
    Endpointing
    Turn Detection
    Interruption Detection
    ASR
    Language / Dialect Handling
    Conversation State
    Reasoning / LLM
    Tool Orchestration
    Policy Enforcement
    Response Planning
    TTS / Voice
    Audio Output
    Observability

Even when using a provider that bundles several functions together, preserve these logical boundaries internally.

The architecture must permit a future composition such as:

    ASR A
    +
    LLM B
    +
    TTS C
    +
    VAD D
    +
    Transport E

without redesigning QEVION Core.

Do not allow a bundled provider API to become the actual core architecture.


======================================================================
15. TRUE REALTIME REQUIREMENT
======================================================================

Do not define "voice" as:

    microphone -> browser speech recognition -> text -> backend -> browser speech synthesis

and then claim the platform has a realtime voice runtime.

A future implementation claiming realtime voice must demonstrate an actual streaming architecture with:

- streaming audio input
- incremental processing
- streaming or incremental ASR where supported
- conversational state continuity
- incremental response generation where appropriate
- low-latency output
- server/runtime controlled turn handling
- output cancellation
- interruption handling
- timing instrumentation

Browser-native speech APIs may be used as development conveniences or compatibility layers only if they do not become the architectural definition of the QEVION Voice Runtime.


======================================================================
16. INTERRUPTION / BARGE-IN
======================================================================

Realtime interruption is a first-class behavior.

When the user begins speaking while QEVION is speaking:

1. detect interruption
2. stop or cancel current output
3. reconcile runtime state
4. preserve valid context
5. capture the new user turn
6. continue from the updated state
7. avoid replaying stale output

Measure interruption latency separately.

Define:

- interruption detected timestamp
- cancellation requested timestamp
- audio stop timestamp
- new input start timestamp
- next response start timestamp

Do not consider interruption support complete merely because a UI button can stop audio playback.


======================================================================
17. VAD / ENDPOINTING / TURN DETECTION
======================================================================

These are separate concepts.

Define:

- voice activity detection
- endpointing
- turn detection
- semantic turn detection
- interruption detection

Do not collapse them into one generic "VAD" feature.

The runtime must be able to reason about:

- speech started
- speech continuing
- likely turn complete
- interruption
- accidental short utterance
- silence
- overlap
- background/noise behavior

The architecture may use different implementations over time.


======================================================================
18. CONVERSATION-FIRST INTELLIGENCE
======================================================================

Do not make a finite intent classifier the complete conversational understanding system.

Conversation should support:

- information requests
- follow-up questions
- contextual references
- recommendations
- comparisons
- corrections
- clarification
- topic switching
- multi-intent requests
- customer preferences
- objections
- casual conversational turns where relevant
- confirmation
- contradiction
- incomplete information
- ambiguous language

Intent may exist as one runtime signal.

Intent must not define the full mental model.


======================================================================
19. CONTEXTUAL REFERENCE RESOLUTION
======================================================================

The system must resolve references across turns.

Example:

User:
    "البرجر الكلاسيك بكام؟"

User:
    "طب مكوناته إيه؟"

The second request should resolve "مكوناته" to the relevant burger entity where context makes that interpretation justified.

This applies to:

- products
- services
- people
- offers
- appointments
- previous questions
- previous selections
- previous tool results
- previous entities

Context resolution must be explicit in the runtime architecture.


======================================================================
20. RECOMMENDATIONS
======================================================================

The agent must be capable of making grounded recommendations.

Examples:

    "ترشحلي إيه؟"
    "إيه أحسن حاجة عندكم؟"
    "أنا بحب الحاجات الحارة."

Recommendations should be grounded in available:

- tenant knowledge
- customer preferences
- activity objective
- eligibility
- current availability
- offers
- policies

Do not manufacture product facts.

Do not force a recommendation if available information is insufficient.


======================================================================
21. COMPARISON
======================================================================

The conversation engine must support comparisons.

Examples:

- "إيه الفرق بينهم؟"
- "أنهي أنسب ليا؟"
- "إيه الاختلاف بين العرضين؟"

Comparison must use available business truth.

The system should distinguish:

- factual difference
- inferred preference
- recommendation

Do not silently convert a factual comparison into an unsupported business claim.


======================================================================
22. MULTI-INTENT
======================================================================

Support compound user requests.

Example:

    "عايز اتنين تشيكن برجر، وهو فيهم جبنة؟"

This may require:

- order intent
- quantity
- entity resolution
- product information lookup

The runtime must preserve all relevant objectives and subrequests rather than dropping one because another was detected first.


======================================================================
23. TOPIC SWITCHING
======================================================================

Users may change topics without resetting the entire conversation.

Example:

    product question
    -> order
    -> delivery question
    -> recommendation
    -> return to original item

The runtime must preserve enough context to return to earlier topics when appropriate.

Topic switching must not cause:

- state corruption
- duplicated questions
- accidental reset
- forgotten requirements


======================================================================
24. CORRECTION HANDLING
======================================================================

Corrections are first-class interaction events.

Examples:

    "لا، مش قصدي ده."
    "أنا بس بسأل."
    "لا، قصدي المنتج التاني."
    "مش ده اللي طلبته."

The runtime must support:

- correction detection
- rollback/reconciliation where necessary
- state repair
- entity correction
- intent correction
- user confirmation
- continued conversation without unnecessary restart


======================================================================
25. NATURAL HUMAN-LIKE CONVERSATION
======================================================================

The goal is natural conversational behavior, not theatrical imitation of a human.

Human-like quality should come from:

- accurate understanding
- contextual relevance
- continuity
- timing
- natural turn-taking
- appropriate acknowledgement
- concise responses where appropriate
- fuller responses when complexity requires
- natural clarification
- natural correction
- natural recovery
- natural topic transitions
- controlled variation
- avoiding repetition

Do NOT simulate humanity with:

- random filler
- meaningless "aha"
- scripted sympathy on every turn
- exaggerated friendliness
- unnecessary pauses
- repetitive empathy templates
- fake emotional performance

Naturalness must be behaviorally evaluated.


======================================================================
26. REPETITION AND ROOT-CAUSE ANALYSIS
======================================================================

Repeated behavior must be diagnosable.

Possible root causes include:

- missing capability
- missing knowledge
- context failure
- state failure
- entity resolution failure
- provider limitation
- prompt/configuration issue
- hardcoded fallback
- tool failure
- memory failure
- language/dialect handling failure
- interruption/state reconciliation failure

The runtime must generate sufficient structured evidence to identify the most likely root-cause category.

Do not merely log:

    "agent repeated itself."

Record enough state to determine WHY.


======================================================================
27. KNOWLEDGE ARCHITECTURE
======================================================================

Knowledge must be generic.

A restaurant example may include:

- product description
- ingredients
- allergens
- sauces
- toppings
- variants
- sizes
- modifiers
- availability
- preparation notes
- dietary information
- nutrition when verified
- offers
- pairings
- FAQs
- pronunciation hints

But these are examples.

The knowledge architecture must also support:

- telecom plans
- factory services
- product catalogs
- FAQs
- policies
- eligibility rules
- support procedures
- organization information
- locations
- operating hours
- service limitations
- structured business data

Knowledge sources may eventually include:

- structured tenant data
- database
- API
- documents
- RAG
- external approved sources

Do NOT introduce a vector database merely because vector databases are fashionable.

The architecture should allow relational/structured retrieval where sufficient and semantic retrieval where actually useful.


======================================================================
28. BUSINESS TRUTH
======================================================================

Model output is NOT authoritative business truth.

Business truth must come from:

- validated tenant data
- approved knowledge
- authorized tools
- verified provider responses
- system state

The LLM may reason over business truth.

It must not become the source of business truth merely because it generated a confident statement.


======================================================================
29. CLAIM GOVERNANCE
======================================================================

The runtime must distinguish:

- allowed claims
- verified claims
- uncertain claims
- prohibited claims
- unsupported claims

A claim requiring external/business verification must not be treated as verified solely because the model generated it.

Define how the runtime handles:

- missing information
- conflicting sources
- stale information
- ambiguous information
- unauthorized assumptions

The specification must include an explicit uncertainty policy.


======================================================================
30. DATA PROVENANCE
======================================================================

Structured data used in outcomes or decisions must support provenance.

At minimum define categories such as:

    USER_STATED
    TOOL_VERIFIED
    SYSTEM_DERIVED
    UNVERIFIED
    UNKNOWN

The implementation must be able to distinguish facts obtained from the customer from facts verified through tools and facts inferred by the system.


======================================================================
31. TOOLS
======================================================================

Tools are first-class runtime capabilities.

A Tool contract must define at least:

- name
- description
- typed input
- runtime input validation
- typed output
- tenant scope
- authorization
- policy requirements
- confirmation requirements
- idempotency behavior
- request ID
- structured result
- timeout
- retry semantics where appropriate
- error classification
- observability metadata

Tool execution must be controlled by QEVION runtime policy.

Provider/tool adapters must not contain business-specific conversation logic.


======================================================================
32. CONFIRMATION
======================================================================

Certain actions require explicit confirmation.

Examples may include:

- final order
- sensitive changes
- irreversible actions
- appointment booking
- high-impact transactions
- certain outbound commitments

Define:

- when confirmation is required
- who/what determines this
- how confirmation is represented
- how confirmation is logged
- what happens if the user changes their mind
- how confirmation interacts with interruption


======================================================================
33. HUMAN HANDOFF
======================================================================

Human handoff is a first-class capability.

Handoff may be triggered by:

- explicit user request
- repeated misunderstanding
- unresolved ambiguity
- tool failure
- unsupported request
- policy restriction
- complaint
- operational problem
- escalation rule
- business-defined condition

The current POC does not need a complete PSTN transfer subsystem.

However, it must be able to emit a normalized handoff event and structured handoff context.

Future integrations may route that handoff to:

- human inbox
- dashboard ticket
- CRM
- webhook
- API
- queue
- phone transfer adapter


======================================================================
34. OUTCOME ENGINE
======================================================================

Outcome is not merely a transcript summary.

The runtime must produce machine-readable structured outcomes.

Possible outcomes include:

- accepted
- rejected
- callback_requested
- not_eligible
- completed
- partially_completed
- human_required
- no_answer
- abandoned
- unsupported
- technical_failure

Do not restrict the system to this exact enumeration if the architecture benefits from extensibility.

Compound outcomes must be supported.

Examples:

    accepted + callback_requested

or

    partially_completed + human_required

An outcome should support fields such as:

- primary outcome
- secondary outcomes
- collected data
- verified data
- inferred data
- rejected data
- next action
- handoff requirement
- Activity identity
- Activity version
- policy version
- knowledge/version provenance
- tool provenance
- conversation/session identity
- timestamps

Possible next actions include:

- schedule_callback
- create_lead
- handoff
- retry
- send_followup
- close
- request_more_information

The system must make outcomes consumable by future:

- dashboards
- CRM
- ERP
- webhooks
- APIs
- queues
- automation systems
- human operators


======================================================================
35. CONVERSATION MEMORY AND CUSTOMER CONTEXT
======================================================================

Separate:

- current Conversation State
- Session State
- Customer Profile
- Customer Context
- Project/Workspace Context where applicable
- Learned Preferences
- Evidence and Confidence

Do not collapse every kind of memory into one store.

Customer personalization should eventually combine:

    tenant configuration
    +
    current session context
    +
    authorized persistent customer context

Persistent memory must remain behind an abstraction boundary.


======================================================================
36. VERSIONING
======================================================================

The system must support versioned:

- Activities
- Policies
- Knowledge
- Voice Profiles
- Providers
- Provider Models
- Event Contracts
- Tool Contracts
- relevant configuration

Every execution/session must be traceable to the versions used.

A future system must be able to answer:

    Which Activity version ran?
    Which policy version governed it?
    Which knowledge version was consulted?
    Which model/provider handled reasoning?
    Which ASR/TTS/VAD components were used?
    Which tool versions were invoked?
    Which outcome was produced?


======================================================================
37. EXPERIMENTATION
======================================================================

The architecture should permit future experimentation such as:

- A/B testing
- prompt variants
- voice variants
- model variants
- policy-safe optimization experiments
- Activity variants

Experiments must remain versioned and observable.

Do not build an unnecessarily large experiment platform into the current POC.


======================================================================
38. MULTILINGUAL / MULTIDIALECT ARCHITECTURE
======================================================================

The architecture must be globally extensible.

Separate:

    language
    locale
    dialect
    voice
    provider
    model
    capabilities

Egyptian Arabic is a high-priority benchmark.

It is NOT the architectural boundary.

The Core must not contain:

    if Egyptian then ...

as its fundamental architecture.

Adding another language or dialect must not require rewriting QEVION Core.


======================================================================
39. LANGUAGE CAPABILITY REGISTRY
======================================================================

Define a registry or equivalent capability model describing supported combinations.

At minimum consider:

- language
- locale
- dialect
- ASR capability
- TTS capability
- streaming
- realtime capability
- interruption
- code-switching
- pronunciation support
- voice availability
- provider
- model
- known limitations
- latency characteristics
- hardware requirements
- license status

Use capability states such as:

    SUPPORTED
    PARTIAL
    UNSUPPORTED
    UNVERIFIED

Do not equate:

    ar-EG

with proven high-quality Egyptian spoken-language support.

A locale code is metadata.

Language quality is an evaluated capability.


======================================================================
40. PRONUNCIATION / LEXICON LAYER
======================================================================

Define a pronunciation/lexicon abstraction.

It should eventually support:

- company names
- brands
- product names
- branch names
- people names where authorized
- places
- abbreviations
- foreign words
- technical terms

Tenant-specific pronunciation overrides must be possible.

The architecture must permit pronunciation hints to flow into ASR/TTS or relevant provider mechanisms without contaminating business logic.


======================================================================
41. EGYPTIAN ARABIC QUALITY BAR
======================================================================

Egyptian Arabic must be explicitly evaluated for:

- comprehension
- vocabulary
- sentence construction
- pronunciation
- rhythm
- naturalness
- MSA drift
- Gulf/Levantine drift
- slang handling
- code-switching
- numbers
- prices
- names
- product names
- fast speech
- slow speech
- interruptions
- corrections
- ambiguous utterances
- contextual references

Do not claim "Egyptian Arabic support" merely because an engine accepts an Egyptian locale code.

The specification must define how Egyptian quality is measured.


======================================================================
42. CURRENT EGYPTIAN TTS CANDIDATE REFERENCES
======================================================================

The specification should maintain an explicit reference registry containing candidate open-source/open-weight technologies.

Potential Egyptian-focused candidates to investigate include:

- VoiceTuT-TTS
- Lahgtna / OmniVoice Egyptian variants
- KemeTone
- suitable Egyptian Chatterbox fine-tunes

These are NOT mandatory implementation choices.

They are candidates for evaluation.

Do not assume that:

    open source
    =
    commercially usable
    =
    unrestricted model weights
    =
    unrestricted voice usage

All such assumptions require license verification.


======================================================================
43. SPEECH DATASET REFERENCES
======================================================================

Candidate evaluation/dataset references may include:

- FLEURS, including Egyptian Arabic where available
- Mozilla Common Voice
- MADAR
- other validated Arabic/Egyptian speech corpora
- additional relevant open datasets discovered during research

For every dataset, the rewritten specification must require verification of:

- availability
- language/dialect coverage
- data quality
- speaker diversity
- license
- redistribution rights
- training rights
- commercial-use rights
- current accessibility

Do not present a dataset as commercially safe merely because it is downloadable.


======================================================================
44. OPEN-SOURCE / OPEN-WEIGHT REFERENCE POOL
======================================================================

Maintain a reference pool, but DO NOT turn it into a rigid technology mandate.

Candidate categories:

REALTIME / AGENT RUNTIME
- LiveKit Agents
- LiveKit Server
- Pipecat

ASR
- faster-whisper
- whisper.cpp
- FunASR
- additional verified Arabic/Egyptian-capable engines discovered during research

VAD / TURN DETECTION
- Silero VAD
- mature semantic turn detection implementations
- additional validated open implementations

TTS
- VoiceTuT-TTS
- Lahgtna / OmniVoice Egyptian variants
- KemeTone
- Egyptian Chatterbox fine-tunes
- Piper-family projects where language coverage is relevant
- Kokoro-family projects where language/voice/license coverage is relevant
- additional open TTS candidates discovered through research

LOCAL LLM / INFERENCE
- llama.cpp
- additional mature local inference runtimes

DATA / KNOWLEDGE / RETRIEVAL
- PostgreSQL
- pgvector
- Qdrant
- other justified storage/retrieval technologies

TESTING / EVALUATION
- pytest
- Hypothesis
- promptfoo
- DeepEval
- custom deterministic evaluation harnesses

OBSERVABILITY
- OpenTelemetry
- Langfuse
- structured logs
- traces
- metrics systems

SECURITY
- Bandit
- Gitleaks
- Trivy
- Semgrep
- OWASP guidance
- dependency/license/security scanning

AUDIO
- FFmpeg

FUTURE TELEPHONY SEAM REFERENCES
- FreeSWITCH
- Asterisk
- Kamailio
- SIP-based integrations
- PBX integrations
- 4G/LTE gateway concepts where appropriate

The agent must search for additional high-value references.

The list is intentionally open-ended.

The agent must also reject:

- obsolete projects
- abandoned projects
- low-quality forks
- poorly maintained projects
- projects with incompatible licenses
- projects whose model licenses make them unsuitable
- projects that do not actually satisfy the required capability
- projects that create unjustified architectural coupling


======================================================================
45. REFERENCE EVALUATION RULE
======================================================================

For every serious candidate, evaluate:

- maintenance
- latest relevant release/activity
- maturity
- architecture fit
- Python compatibility
- streaming capability
- realtime behavior
- quality
- Arabic/Egyptian quality where relevant
- latency
- hardware requirements
- scalability
- deployment complexity
- observability
- security
- ecosystem
- licensing
- model-weight licensing
- dataset licensing where applicable
- commercial suitability

The final specification must not say:

    "Use X"

unless X is genuinely an architecture requirement.

Instead describe:

    required capability
    selection criteria
    acceptable adapters
    verification expectations

An implementation agent may select among valid technologies based on measured evidence.


======================================================================
46. LICENSE GATE
======================================================================

Every dependency/model/dataset/voice source must be evaluated across separate licensing dimensions:

- source-code license
- model license
- model-weight license
- dataset license
- voice license
- commercial restrictions
- redistribution restrictions
- derivative-work restrictions
- attribution obligations
- hosted-service limitations where relevant

Explicitly state:

    Open source is not automatically equivalent to free commercial use.

The implementation phase must not silently adopt an asset whose license is unsuitable for the intended use.

Where license status is unclear:

    UNVERIFIED

must be used.


======================================================================
47. PROVIDER ARCHITECTURE
======================================================================

Provider adapters must be thin integration boundaries.

Providers may expose:

- ASR
- TTS
- VAD
- realtime
- LLM
- tool integration
- voice
- model hosting

But provider adapters must NOT own:

- business logic
- Activity logic
- outcome decisions
- tenant policies
- canonical conversation state
- business truth

QEVION Core remains authoritative.

Provider-specific peculiarities must be normalized through contracts.

Provider failure must not corrupt canonical business state.


======================================================================
48. CORE RESPONSIBILITIES
======================================================================

QEVION Core owns or governs:

- conversation state
- business/activity state
- tenant context
- customer context
- policy enforcement
- knowledge selection/access
- tool orchestration
- confirmation
- ambiguity handling
- correction handling
- context resolution
- outcome determination
- handoff decisions
- normalized events
- observability
- audit metadata
- version traceability

Do not allow the LLM provider to become the actual orchestration engine unless wrapped by QEVION contracts.


======================================================================
49. TRANSPORT ARCHITECTURE
======================================================================

Transport adapters may support:

- browser/WebRTC
- local audio
- websocket-style transports
- future telephony
- other media channels

Transport must move data.

Transport must not decide business outcomes.

Future telephony should be attachable through an external Telephony Adapter boundary.


======================================================================
50. TELEPHONY — EXPLICITLY FUTURE SCOPE
======================================================================

Do NOT implement as part of the current POC:

- SIP carrier
- PSTN carrier integration
- SIM gateway
- GSM call stack
- phone-number provisioning
- PBX replacement
- carrier billing
- telecom network management

The current POC should create architectural seams for these future capabilities.

Potential future adapters may include:

- SIP
- PBX
- Asterisk
- FreeSWITCH
- Kamailio
- 4G/LTE gateway
- carrier adapter

The long-term design should allow a customer's existing phone line/number infrastructure to connect to QEVION through an external telephony boundary rather than forcing a single vendor-dependent architecture.


======================================================================
51. SECURITY AND PRIVACY
======================================================================

The rewritten specification must define security requirements including:

- tenant isolation
- authorization
- authentication boundaries
- secret management
- provider credential handling
- tool authorization
- sensitive-data minimization
- audit logging
- access control
- input validation
- output validation where required
- prompt-injection resistance
- tool abuse resistance
- data leakage prevention
- secure defaults
- dependency security
- supply-chain considerations
- retention controls
- privacy boundaries

Never place credentials into source code.

Never allow untrusted model output to directly perform privileged actions without policy/tool validation.

Security requirements must be testable.


======================================================================
52. OBSERVABILITY
======================================================================

Observability is a core architectural capability.

Capture normalized evidence for:

- session
- Activity
- Activity version
- tenant
- line
- channel
- language
- dialect
- provider
- model
- ASR
- VAD
- TTS
- turn events
- interruption
- tool calls
- tool results
- policy decisions
- knowledge access
- state transitions
- outcome
- handoff
- errors
- latency
- retries

Do not log sensitive content unnecessarily.

Where possible distinguish:

- operational logs
- metrics
- traces
- audit events
- evaluation evidence


======================================================================
53. LATENCY AND PERFORMANCE
======================================================================

Voice quality cannot be evaluated purely by textual correctness.

Define measurable latency components such as:

- audio input latency
- VAD/endpoint latency
- ASR latency
- reasoning latency
- tool latency
- TTS first-byte/start latency
- total response latency
- interruption cancellation latency

Define how these are measured.

Do not invent numerical performance targets without evidence.

Where exact values cannot yet be fixed, define:

- measurement method
- percentile reporting
- test conditions
- hardware/environment
- network conditions
- model/provider versions

Performance claims must be evidence-backed.


======================================================================
54. COST ARCHITECTURE
======================================================================

The specification should support future cost analysis.

Track resource-consuming operations such as:

- ASR compute
- TTS compute
- LLM inference
- provider API calls
- storage
- bandwidth
- concurrency
- tool usage

Do not hardcode pricing assumptions into the core architecture.

Pricing must remain environment/provider-specific configuration.


======================================================================
55. EVALUATION AND VERIFICATION FABRIC
======================================================================

Evaluation must be a first-class subsystem or clearly defined boundary.

Support:

- deterministic graders
- model-based graders
- optional counter-evaluation
- aggregation
- verification
- evidence
- regression datasets
- golden cases
- replay

Evaluation must distinguish:

    functional correctness
    conversational quality
    voice quality
    policy compliance
    business outcome correctness
    tool correctness
    state correctness
    language quality
    interruption quality
    latency quality

Do not let "the test passed" mean only that a mocked endpoint returned HTTP 200.


======================================================================
56. REPLAY
======================================================================

The architecture must support deterministic or controlled replay of conversations where practical.

Replay should allow analysis of:

- conversation state
- events
- provider versions
- Activity version
- policies
- tool results
- outcome

Where true deterministic replay is impossible because of external systems, document the replay boundary and use recorded evidence/references.


======================================================================
57. REGRESSION TESTING
======================================================================

Regression testing must cover behavior, not just structure.

Include test categories for:

- simple questions
- follow-ups
- references
- recommendations
- comparisons
- multi-intent
- corrections
- topic switching
- ambiguity
- repeated questions
- tool failure
- knowledge failure
- provider failure
- interruption
- language switching
- Egyptian Arabic
- unsupported requests
- handoff
- outcome generation
- outbound Activities
- policy restrictions

Golden conversations must be versioned.

A future implementation must be able to prove that improvements do not silently break earlier capabilities.


======================================================================
58. RED-TEAM REQUIREMENT
======================================================================

Before finalizing the specification, perform an internal red-team pass.

Search for ways an implementation agent could technically satisfy wording while avoiding the intended behavior.

At minimum attempt to exploit:

1. "realtime" by using browser speech APIs
2. "voice AI" by returning text and playing static audio
3. "multilingual" by simply accepting locale strings
4. "Egyptian Arabic" by relabeling a generic Arabic model
5. "provider abstraction" while hardcoding one provider internally
6. "Activity configuration" while hardcoding business flows
7. "knowledge" by embedding a few constants
8. "tools" by using unvalidated arbitrary calls
9. "handoff" by emitting fake logs only
10. "outcome engine" by generating prose summaries
11. "interruption" by stopping UI audio only
12. "conversation intelligence" by implementing a tiny intent enum
13. "memory" by storing arbitrary unstructured text
14. "testing" by overusing mocks
15. "open source" by ignoring model/data/voice licenses
16. "observability" by logging only generic errors
17. "scalability" by describing future work without a seam
18. "security" by listing OWASP terms without enforceable controls
19. "general-purpose" by keeping restaurant-specific architecture
20. "self-improvement" by allowing unreviewed autonomous policy changes

For EVERY identified loophole, add an explicit countermeasure to the specification.

Maintain explicit traceability:

    Exploit
    -> Intended Requirement
    -> Failure Mode
    -> Countermeasure
    -> Verification Method


======================================================================
59. SELF-IMPROVEMENT
======================================================================

QEVION may eventually learn from execution outcomes.

The architecture should support a future loop conceptually similar to:

    Execution / Experience
        ->
    Evaluation
        ->
    Lesson / Knowledge Extraction
        ->
    Candidate
        ->
    Replay & Verification
        ->
    GOLD
        ->
    Retrieval / Student Learning
        ->
    Capability Re-test
        ->
    Learning Gap Discovery

However:

The learning system must remain separate from the authoritative Platform Core.

Do NOT allow autonomous learning to silently alter business policy.

Any change affecting:

- policies
- business rules
- Activity objectives
- prohibited claims
- eligibility
- outcomes

must pass operator approval and versioning.

Self-improvement may recommend.

Operators approve changes.

Approved changes create new versions.


======================================================================
60. HUMAN AGENCY AND OPERATOR CONTROL
======================================================================

Business owners must remain in control of business policy.

The AI may:

- recommend
- analyze
- detect patterns
- identify gaps
- suggest Activity changes
- suggest knowledge improvements
- suggest experiments

The AI must not silently rewrite authoritative business policies.

Policy-affecting changes must have:

- proposed change
- evidence
- rationale
- review
- approval
- version
- audit trail


======================================================================
61. EVENT AND CONTRACT DESIGN
======================================================================

Define normalized event contracts.

Examples may include:

- session.started
- session.ended
- user.speech.started
- user.speech.finalized
- assistant.response.started
- assistant.response.cancelled
- interruption.detected
- tool.requested
- tool.completed
- tool.failed
- policy.checked
- handoff.requested
- outcome.produced
- activity.blocked
- provider.failed

These are examples, not a mandatory immutable enum.

The important requirement is:

consistent normalized contracts

across providers and channels.

Contracts must be versioned.


======================================================================
62. ERROR MODEL
======================================================================

Define meaningful error classes.

At minimum distinguish:

- user-input problem
- ambiguity
- unsupported request
- knowledge unavailable
- tool failure
- provider failure
- transport failure
- audio failure
- ASR failure
- TTS failure
- policy restriction
- configuration error
- Activity blocked
- timeout
- authentication/authorization error
- internal system error

Do not reduce every failure to:

    "something went wrong."

The system must know which layer failed and whether recovery is possible.


======================================================================
63. FAILURE RECOVERY
======================================================================

The runtime should define recovery strategies for:

- ASR uncertainty
- provider timeout
- TTS failure
- interruption
- tool timeout
- conflicting tool result
- missing knowledge
- state corruption detection
- unsupported request
- invalid data
- customer correction

Recovery must preserve state integrity.

Do not silently continue with fabricated data.


======================================================================
64. BUSINESS / CONVERSATION STATE SEPARATION
======================================================================

Separate:

    conversational state

from:

    business/task state

and from:

    transport state

For example:

- the user speaking is transport/conversation state
- what the user wants is conversational/task state
- whether an order is confirmed is business state
- whether audio is being streamed is transport/media state

Do not create one giant state object containing unrelated concerns.


======================================================================
65. SECURITY AGAINST MODEL AUTHORITY
======================================================================

Treat the model as a reasoning component, not an authority.

A model may propose:

- action
- tool call
- interpretation
- response

QEVION validates:

- policy
- authorization
- data
- business state
- tool permissions
- confirmation
- outcome conditions

before accepting consequential actions.


======================================================================
66. GENERIC EXAMPLES
======================================================================

The rewritten specification must include concrete examples proving generality.

Example A — Restaurant inbound:

    customer calls
    -> asks product price
    -> asks ingredients
    -> asks whether cheese is included
    -> requests recommendation
    -> confirms order
    -> structured outcome

Example B — Telecom outbound:

    customer receives an outbound call
    -> agent introduces company
    -> presents offer
    -> handles objection
    -> answers eligibility question
    -> explains material terms
    -> customer accepts
    -> required data collected
    -> confirmation
    -> structured outcome

Example C — Factory follow-up:

    outbound follow-up
    -> customer describes maintenance problem
    -> system gathers required information
    -> tool verifies equipment/service data
    -> determines whether human intervention is required
    -> creates structured handoff/outcome

Example D — Support:

    customer starts with an issue
    -> changes topic
    -> corrects previous statement
    -> returns to issue
    -> tool fails
    -> agent recovers
    -> human handoff

The examples exist to demonstrate that the same architecture supports different business objectives.


======================================================================
67. CURRENT POC SCOPE
======================================================================

The rewritten specification must be explicit about what the POC proves.

The POC should primarily prove the real conversational voice runtime and architecture seams.

It must avoid unnecessary scope such as:

- full carrier system
- full telecom stack
- full enterprise CRM
- enterprise campaign management suite
- massive billing platform
- unnecessary distributed infrastructure
- speculative features without evaluation value

However, future boundaries must be clear enough that POC architecture does not block the intended product.


======================================================================
68. NO FAKE COMPLETENESS
======================================================================

Never use vague wording such as:

    "enterprise-ready"
    "production-grade"
    "scalable"
    "secure"
    "multilingual"
    "realtime"
    "AI-powered"
    "modular"

without defining:

- what the term means in this specification
- what mechanism provides it
- what evidence verifies it
- what is out of scope

Do not permit marketing language to substitute for engineering requirements.


======================================================================
69. NO HARD-CODED DEMO LOGIC
======================================================================

The specification must explicitly forbid implementations where business behavior is hidden in:

- condition chains
- hardcoded product names
- hardcoded prices
- restaurant-specific prompts
- single-company assumptions
- fixed dialogue branches
- hidden provider instructions
- static response templates masquerading as intelligence

Demo seed data is acceptable.

Demo logic embedded in Core is not.


======================================================================
70. NO PROVIDER LOCK-IN
======================================================================

Do not architect around one vendor's API shape.

Provider-specific adapters may translate between:

    QEVION contracts
    and
    provider contracts

Provider replacement must not require rewriting:

- Activity
- business rules
- outcome engine
- tenant model
- knowledge model
- conversation state


======================================================================
71. NO FRAMEWORK DOGMATISM
======================================================================

Do not force specific frameworks unless the existing authoritative requirements demand them.

The architecture should remain implementation-selectable.

Known project direction includes strong Python/FastAPI/Pydantic alignment.

Do not reinterpret "TypeSafe" as a TypeScript requirement.

TypeSafe refers to the project's decision/intent/type-safe execution concept, not a mandate to switch the platform to TypeScript.

Where implementation choices are necessary, choose based on:

- correctness
- maturity
- maintainability
- interoperability
- ecosystem
- latency
- hardware
- licensing
- security
- implementation cost


======================================================================
72. ARCHITECTURE DECISION RECORDS
======================================================================

Every significant architectural decision in the rewritten specification should include enough context to answer:

- What problem does this decision solve?
- What boundary does it enforce?
- What alternatives were considered?
- Why is it not merely a technology preference?
- What future changes remain possible?

Do not create fake historical ADRs.

Use "proposed architecture" where historical evidence is absent.


======================================================================
73. ASSUMPTIONS LEDGER
======================================================================

Before finalizing, create an internal assumptions ledger.

For every unresolved assumption record:

- assumption
- why it matters
- whether it is safe
- what evidence would validate it
- what happens if it is false

Do not silently turn assumptions into facts.

The final specification should either:

- resolve the assumption through research
- explicitly record it
- convert it into an implementation/evaluation gate


======================================================================
74. TESTABILITY REQUIREMENT
======================================================================

Every major requirement must answer:

    How will the future implementation prove this works?

Avoid requirements that cannot be tested.

For every major subsystem define relevant:

- unit tests
- contract tests
- integration tests
- behavioral tests
- failure tests
- performance tests
- security tests
- evaluation tests

Where human-perception quality is required, define a measurable evaluation protocol rather than pretending it can be reduced to a compile check.


======================================================================
75. ACCEPTANCE CRITERIA
======================================================================

The rewritten specification must contain explicit acceptance criteria.

Acceptance criteria must distinguish:

A. Structural acceptance
    contracts, boundaries, interfaces, configuration

B. Behavioral acceptance
    actual runtime behavior

C. Evidence acceptance
    logs, traces, recordings, metrics, replay evidence, evaluation results

An implementation must not pass solely through static structure if the requirement is behavioral.


======================================================================
76. EVIDENCE MODEL
======================================================================

Define what counts as evidence for major capabilities.

Examples:

Realtime voice:
    actual streaming audio evidence
    + interruption evidence
    + latency measurement

Egyptian Arabic:
    evaluated conversation cases
    + speech recognition quality
    + TTS evaluation
    + dialect-specific cases

Activity generality:
    materially different Activities executed
    + no Core business-code modification

Provider abstraction:
    more than one implementation or a contract-level test proving substitution

Outcome Engine:
    structured machine-readable outputs
    + downstream consumption test

Handoff:
    normalized event
    + structured context

Tool safety:
    authorization/validation/error tests


======================================================================
77. IMPLEMENTATION-GATE DESIGN
======================================================================

The future implementation process should be gate-driven.

The rewritten spec should define gates such as:

Architecture Gate
    contracts and boundaries are coherent

Configuration Gate
    Activities can be declared without hardcoding

Runtime Gate
    conversation lifecycle works

Voice Gate
    actual voice streaming works

Interruption Gate
    barge-in works

Language Gate
    Egyptian benchmark is real

Intelligence Gate
    contextual conversation works

Business Truth Gate
    claims are grounded

Tool Gate
    tools are validated and authorized

Outcome Gate
    machine-readable business outcomes exist

Security Gate
    critical controls pass

Observability Gate
    sufficient evidence exists

Evaluation Gate
    behavior is verified

No gate should be considered passed by documentation alone.


======================================================================
78. X² QUALITY CONTROL — INTERNAL QA
======================================================================

Before writing the final document, run a structured X² review internally.

Score the rewritten specification across ten dimensions:

1. Requirement completeness
2. Logical consistency
3. Testability
4. Implementation executability
5. Architectural generality
6. Behavioral verifiability
7. Provider/channel neutrality
8. Security and failure resilience
9. Performance/operability clarity
10. Maintainability/future extensibility

Use a 0–10 scale.

Target:

    >= 8/10 overall

No critical dimension may be accepted merely because the average is high.

Any score below the threshold requires revision.

Do NOT output the score unless useful.

The document itself matters more than the score.


======================================================================
79. X² EXPLOIT → COUNTERMEASURE TRACEABILITY
======================================================================

Before finalizing, ensure the document contains or is derivable into a traceable matrix:

    Requirement
    -> Potential loophole
    -> Required countermeasure
    -> Verification evidence

At least the major loophole categories listed in the Red-Team section must be covered.

No known exploit may remain intentionally unresolved without an explicit reason.


======================================================================
80. X² COMPRESSION GATE
======================================================================

The specification may be large.

Do not reduce content merely to make it shorter.

However, after drafting, eliminate:

- duplicated requirements
- contradictory statements
- circular definitions
- redundant prose
- marketing language
- empty architectural adjectives
- repeated examples that do not add new meaning

Preserve every unique requirement.

The goal is:

    maximum information density
    without losing executable meaning


======================================================================
81. TARGET EXECUTOR CALIBRATION
======================================================================

Assume a future implementation agent is technically capable but will naturally exploit ambiguity when a requirement is underspecified.

Therefore:

Whenever wording could permit a weak implementation, replace it with measurable acceptance criteria.

Examples:

WEAK:
    "Support realtime voice."

STRONGER:
    Define streaming audio path, interruption behavior, cancellation, state reconciliation, latency measurement, and evidence requirements.

WEAK:
    "Support Egyptian Arabic."

STRONGER:
    Define dialect quality dimensions and benchmark cases.

WEAK:
    "Support custom Activities."

STRONGER:
    Require configuration-only creation of materially different Activities without modification of Core business logic.

WEAK:
    "Have an outcome engine."

STRONGER:
    Require versioned structured outcome contracts and downstream consumption evidence.

Do this throughout the specification.


======================================================================
82. CONTRADICTION RESOLUTION
======================================================================

During rewrite:

1. detect contradictions
2. identify the higher-level objective
3. preserve the stronger requirement
4. remove weaker contradictory wording
5. make the resulting rule explicit

Do not leave two incompatible versions of a requirement in the document.


======================================================================
83. ARCHITECTURAL SEPARATION
======================================================================

The specification must clearly separate:

Core
Business Domain
Conversation Runtime
Voice Runtime
Knowledge
Tools
Policies
Providers
Channels
Transport
Telephony
Observability
Evaluation
Learning
Administration
Campaigns

Not every module must become a separate microservice.

Logical separation is required.

Physical deployment separation can remain flexible.


======================================================================
84. DEPLOYMENT PHILOSOPHY
======================================================================

Do not prematurely mandate microservices.

The architecture should support:

- local development
- single-process POC where justified
- modular monolith
- later distributed deployment

The important property is strong logical boundaries.

Do not introduce infrastructure merely for architectural theater.


======================================================================
85. DATA STORAGE PHILOSOPHY
======================================================================

Separate data by responsibility.

Possible categories:

- transactional state
- configuration
- knowledge
- session state
- event/audit state
- evaluation data
- customer context
- analytics

Do not force one database technology for every data type.

Storage choices should be justified by access pattern and correctness requirements.


======================================================================
86. ADMINISTRATION BOUNDARY
======================================================================

Future administration must be capable of governing:

- tenants
- Activities
- Activity versions
- policies
- knowledge
- tools
- provider configuration
- voice configuration
- limits
- operator approvals
- evaluation
- audit

Do not require full enterprise admin UI in current POC.

Do require clean architectural boundaries for it.


======================================================================
87. TENANCY
======================================================================

Tenant must be a first-class security and data-isolation boundary.

The specification must define:

- tenant context
- tenant authorization
- tenant-scoped data
- tenant-scoped tools
- tenant-scoped knowledge
- tenant-scoped Activities
- tenant-scoped customer context
- tenant-aware observability

No request should be able to accidentally operate outside its authorized tenant scope.


======================================================================
88. POLICY ENGINE
======================================================================

Policies should be first-class and versioned.

Policies may govern:

- claims
- tools
- data access
- confirmation
- handoff
- outbound behavior
- opt-out
- escalation
- channel restrictions
- model/provider restrictions

Policy enforcement must occur independently of model intent where necessary.

Do not assume prompt instructions alone are an adequate enforcement mechanism.


======================================================================
89. CUSTOMER CONSENT / CONTACT POLICY HOOKS
======================================================================

Outbound architecture must include policy hooks for:

- consent
- opt-out
- do-not-contact
- attempt limits
- permitted contact windows
- suppression

Current POC need not implement complete jurisdiction-specific compliance software.

But the architecture must not make these controls impossible.


======================================================================
90. DATA SAFETY
======================================================================

The specification must address:

- personal data
- sensitive data
- minimization
- retention
- redaction
- audit
- access control
- export/deletion boundaries
- provider-sharing boundaries

Never assume that because a conversation is audio, it is exempt from privacy concerns.


======================================================================
91. MODEL AGNOSTICISM
======================================================================

The system should support multiple model classes.

Conceptually, models may later be categorized as:

- Max
- Medium
- Fast
- Auto routing

The exact names are not architecturally important.

The architecture should allow QEVION to route requests based on:

- task requirements
- latency
- cost
- quality
- language capability
- tool requirements
- context size
- availability
- policy

Router decisions must remain observable.


======================================================================
92. ROUTER BOUNDARY
======================================================================

Define a future Router Engine boundary.

It may select:

- provider
- model
- voice
- ASR
- TTS
- capability combination

based on a policy/configuration/optimization layer.

Router must not become business logic.

Routing decisions must be traceable.


======================================================================
93. LOCAL VS REMOTE EXECUTION
======================================================================

Architecture must permit:

- local inference
- remote provider inference
- hybrid inference

without changing Activity semantics.

Provider and model location must be deployment concerns.


======================================================================
94. HARDWARE AWARENESS
======================================================================

Runtime capability selection should eventually consider:

- CPU
- GPU
- memory
- concurrency
- model size
- quantization
- latency

Do not hardcode current developer hardware assumptions into the product architecture.

Hardware-specific optimization belongs to deployment/runtime configuration.


======================================================================
95. OPEN-SOURCE RESEARCH PROTOCOL
======================================================================

When researching technologies, do not merely search for popularity.

For every candidate ask:

    Does it actually solve the required problem?
    Is it maintained?
    Is its architecture suitable?
    Is its license acceptable?
    Are model weights licensed appropriately?
    Is it practical under target hardware?
    Does it support the needed language/dialect?
    Is its latency appropriate?
    Can it be replaced later?
    Does it introduce vendor lock-in?
    Does it provide real evidence of capability?

Search official repositories and primary documentation first.

Use third-party sources for comparison only when needed.

Treat forks as separate candidates.

Do not mistake a fork's README for the upstream project's status.


======================================================================
96. REFERENCE REGISTRY FORMAT
======================================================================

The rewritten specification must include a compact but useful registry with fields such as:

    Reference
    Category
    Purpose
    Relevant Capability
    Status
    License to verify
    Model/Weights License to verify
    Risks
    Evaluation Criteria
    Decision Status

Decision Status may be:

    CANDIDATE
    VERIFIED CANDIDATE
    SELECTED
    REJECTED
    DEFERRED
    UNVERIFIED

Do not mark a technology SELECTED merely because it is listed here.


======================================================================
97. POC IMPLEMENTATION FREEDOM
======================================================================

The future implementation agent must be free to choose concrete frameworks/providers/models from the valid candidate set.

The spec defines:

    WHAT
    WHY
    BOUNDARIES
    CONSTRAINTS
    ACCEPTANCE

The future implementation agent decides:

    HOW

unless the architecture explicitly requires a specific mechanism.


======================================================================
98. SPECIFICATION STRUCTURE
======================================================================

The final QEVION_VOICE_RUNTIME_POC_SPEC_v2.md should be organized as one coherent document.

At minimum include sections equivalent to:

1. Executive Summary
2. Mission and Product Identity
3. Goals / Non-Goals
4. Architectural Principles
5. System Boundaries
6. Generic Domain Model
7. Tenant / Business / Customer Model
8. Line / Endpoint / Channel Model
9. Activity Model
10. Activity Builder Model
11. Activity Preflight
12. Objective and Policy Model
13. Conversation Runtime
14. Context and Memory
15. Knowledge
16. Tools
17. Business Truth and Claim Governance
18. Outcome Engine
19. Human Handoff
20. Voice Runtime
21. Audio / Transport
22. VAD / Turn / Endpoint / Interruption
23. ASR
24. Reasoning / LLM
25. TTS / Voice
26. Language / Locale / Dialect
27. Pronunciation
28. Egyptian Arabic Benchmark
29. Multilingual Capability Registry
30. Provider Architecture
31. Router Boundary
32. Telephony Future Seam
33. Outbound Activities
34. Campaign Boundary
35. Versioning
36. Events / Contracts
37. Error and Recovery Model
38. Security / Privacy / Tenant Isolation
39. Observability / Audit
40. Performance / Latency
41. Cost / Resource Model
42. Testing
43. Evaluation / Verification
44. Replay / Regression
45. Red-Team / Risk Register
46. Self-Improvement / Learning Boundary
47. Operator Approval
48. Open-Source Reference Registry
49. License Gate
50. POC Scope
51. Implementation Gates
52. Acceptance Criteria
53. Evidence Requirements
54. Example Activities
55. Assumptions Ledger
56. Final Traceability Matrix
57. Appendices


======================================================================
99. TRACEABILITY MATRIX
======================================================================

The final specification should contain a requirement traceability mechanism.

Every high-value requirement should be traceable to:

    Requirement ID
    Description
    Architectural owner
    Acceptance criterion
    Evidence type
    Verification method
    Dependency
    Risk

Use stable identifiers such as:

    QV-ARCH-001
    QV-ACT-001
    QV-VOICE-001
    QV-LANG-001
    QV-OUTCOME-001
    QV-SEC-001

Do not create IDs merely for decoration.

They must make the document easier to implement and test.


======================================================================
100. RISK REGISTER
======================================================================

Include a practical risk register.

At minimum cover:

- ASR quality
- Egyptian dialect quality
- TTS naturalness
- latency
- interruption
- provider outages
- provider lock-in
- hallucinated claims
- stale knowledge
- tool failures
- policy bypass
- tenant leakage
- privacy leakage
- over-hardcoded Activities
- weak outcome extraction
- ambiguous requirements
- incomplete observability
- misleading "realtime" claims
- license incompatibility
- hardware limitations
- scaling bottlenecks

For each risk define:

    risk
    impact
    detection
    mitigation
    residual risk
    verification


======================================================================
101. NO SILENT DECISIONS
======================================================================

Do not silently introduce architectural choices merely because they seem reasonable.

Every non-trivial choice must be categorized as one of:

    REQUIRED BY SPEC
    EXISTING PROJECT DIRECTION
    RECOMMENDED
    OPTIONAL
    DEFERRED
    UNVERIFIED

This is essential.

The rewritten spec must not blur:

    requirement
    recommendation
    assumption
    implementation preference


======================================================================
102. HISTORICAL FAILURE INTERPRETATION
======================================================================

Because you have no historical implementation repository, do not write:

    "the old implementation failed because X"

unless X is directly proven by the provided files.

You MAY write:

    "the previous specification was insufficiently explicit about X"

when the specification wording demonstrably permits ambiguity.

You MAY write:

    "the README claims X"

when README states it.

You MAY write:

    "implementation evidence is unavailable"

when it is unavailable.

The goal is to prevent repetition of previous weaknesses without inventing historical facts.


======================================================================
103. READ ME AS CONTEXT
======================================================================

Extract from README:

- project identity
- terminology
- stated capabilities
- stated historical goals
- useful constraints
- project direction

But audit those statements against the new architecture.

README is not allowed to override a stronger architectural requirement merely because it uses stronger language.


======================================================================
104. REFERENCE RESEARCH REQUIREMENT
======================================================================

Before finalizing the specification, research current relevant open-source technologies and primary references.

At minimum investigate:

- LiveKit Agents
- LiveKit Server
- Pipecat
- faster-whisper
- whisper.cpp
- FunASR
- Silero VAD
- VoiceTuT-TTS
- Lahgtna / OmniVoice Egyptian variants
- KemeTone
- Chatterbox
- Piper-related projects
- Kokoro-related projects
- FLEURS
- Common Voice
- MADAR
- llama.cpp
- PostgreSQL
- pgvector
- Qdrant
- pytest
- Hypothesis
- promptfoo
- DeepEval
- OpenTelemetry
- Langfuse
- FFmpeg
- FreeSWITCH
- Asterisk
- Kamailio

Then search for additional relevant projects.

Do not assume the list is complete.


======================================================================
105. RESEARCH OUTPUT REQUIREMENT
======================================================================

Do not turn research into a blog post.

Research should directly improve engineering decisions.

For each useful reference document:

- what it solves
- where it fits
- what it cannot prove
- risks
- licensing questions
- whether it should remain a candidate

Do not blindly copy architecture diagrams from external projects.

QEVION architecture remains authoritative.


======================================================================
106. FINAL DOCUMENT QUALITY
======================================================================

The final specification should read like an implementation contract, not a marketing document.

A capable engineer should be able to read it and understand:

- what to build
- what not to build
- what interfaces to create
- what behaviors must exist
- what behaviors are forbidden
- what can remain flexible
- what must be measurable
- how correctness will be evaluated
- how failure is handled
- how future extensions fit

A weak executor should have very little room to "pass" while implementing a fake or superficial version.


======================================================================
107. ANTI-SUPERFICIAL-COMPLIANCE RULE
======================================================================

The following are explicitly not acceptable as substitutes for genuine capability:

- static demos
- hardcoded responses
- mocked business logic masquerading as real runtime behavior
- fixed dialogue scripts presented as dynamic intelligence
- browser speech APIs presented as the core realtime architecture
- text-only flows presented as voice runtime
- single-provider coupling hidden behind a fake adapter
- a locale code presented as dialect support
- a few seeded knowledge records presented as a knowledge architecture
- a transcript summary presented as an outcome engine
- a log entry presented as human handoff
- stopping browser playback presented as interruption support
- a fixed intent enum presented as general conversation understanding
- passing unit tests against mocks presented as system verification

The specification must define explicit evidence against these shortcuts.


======================================================================
108. FINAL SELF-REVIEW QUESTIONS
======================================================================

Before saving the rewritten document, internally answer:

A.
Can a future agent build a truly general Activity without changing QEVION Core?

B.
Can the same conversation runtime support restaurant, telecom, factory, support, and sales examples?

C.
Can the agent conduct dynamic conversation rather than only follow scripts?

D.
Can the runtime support inbound and outbound?

E.
Can outbound persuasion remain truthful and policy-bounded?

F.
Can the system represent structured outcomes rather than summaries?

G.
Can it support contextual follow-ups and corrections?

H.
Can it handle interruption correctly?

I.
Can Egyptian Arabic quality actually be evaluated?

J.
Can another language/dialect be added without Core redesign?

K.
Can ASR, LLM, TTS, VAD, and transport be replaced independently?

L.
Can future telephony be attached without making the POC a telephony stack?

M.
Can tools be typed, authorized, validated, confirmed, and traced?

N.
Can human handoff be represented structurally?

O.
Can all major behaviors be tested?

P.
Can failures be diagnosed rather than hidden?

Q.
Can provider/model choices be changed?

R.
Can Activity/policy/knowledge versions be reproduced?

S.
Can an operator approve policy-affecting learning?

T.
Can a future agent implement this without hidden historical knowledge?


======================================================================
109. FILE MODIFICATION RULE
======================================================================

Only modify:

    QEVION_VOICE_RUNTIME_POC_SPEC_v2.md

Do not modify:

- source code
- tests
- configuration
- package manifests
- README
- CI
- infrastructure
- unrelated files

Do not create implementation artifacts.

Do not implement any runtime subsystem in this phase.


======================================================================
110. OUTPUT RULE
======================================================================

The only required repository deliverable is:

    QEVION_VOICE_RUNTIME_POC_SPEC_v2.md

The document must be completely rewritten as the new authoritative specification.

Do not produce:

- implementation code
- pseudo-implementation pretending to be complete
- unrelated files
- migration code
- test code
- UI code

You may include architecture examples, contract examples, schemas, event examples, state diagrams in textual form, test examples, and acceptance criteria INSIDE THE SPECIFICATION.
======================================================================
X³ — ACTIVITY DESIGN & CONFIGURATION COPILOT
======================================================================

The QEVION product must include a dedicated conversational
configuration layer whose purpose is to help a business operator design,
validate, improve, and prepare an Activity before the runtime executes it.

This layer must be treated as a first-class product capability.

It is NOT the production voice agent.
It is NOT the business runtime.
It is NOT the source of authoritative business truth.
It is NOT allowed to directly invent business rules.

Its role is:

    Understand
    -> Discover
    -> Inspect
    -> Challenge
    -> Fill Gaps
    -> Map Capabilities
    -> Propose
    -> Simulate
    -> Validate
    -> Produce an Executable Activity Blueprint


======================================================================
1. PRODUCT EXPERIENCE
======================================================================

The business operator should be able to enter a simple conversational
workspace / chat center.

The first interaction should be intentionally simple and human.

The assistant may begin by understanding:

- what organization is being configured
- what the organization sells or provides
- which line is being created
- whether the line is inbound or outbound
- the primary business objective
- the expected customer
- what information the agent needs
- what information the customer may ask for
- what actions the agent is expected to perform
- what actions the agent must never perform
- how success should be defined

The operator should NOT be required to understand:

- agent architecture
- provider APIs
- ASR/TTS implementation
- state machines
- orchestration internals
- tool schemas
- model configuration
- prompt engineering
- event contracts

The configuration assistant converts natural business requirements into
structured QEVION configuration.


======================================================================
2. EXAMPLE INTERACTION MODEL
======================================================================

Example:

Operator:

    "عايز أعمل خط مبيعات outbound.
     عايز الأجنت يكلم العملاء ويعرض عليهم المنتج ده ويقنعهم."

The assistant should NOT immediately generate a generic prompt.

It should continue discovery.

It may determine:

- business identity
- product/service identity
- target audience
- objective
- offer
- eligibility
- pricing
- required customer information
- acceptable persuasion boundaries
- common objections
- required tools
- confirmation requirements
- completion criteria
- failure criteria
- handoff conditions
- outcome requirements
- contact policy
- supported language/dialect
- desired voice characteristics

Then it should explain what is already known and what is still missing.

Example:

    "تمام. عندي الهدف الأساسي: زيادة التحويل.
     لكن قبل ما نجهز الخط، محتاج أعرف:
     1. السعر الحالي؟
     2. مين المؤهل للعرض؟
     3. هل فيه مدة للعرض؟
     4. إيه الشروط اللي لازم العميل يعرفها؟
     5. لو العميل قال إن السعر غالي، إيه البدائل المسموح للأجنت يعرضها؟"

The purpose is NOT to ask a giant questionnaire.

Questions must be dynamically generated based on:

- objective
- Activity type
- known information
- uploaded material
- Core capabilities
- identified gaps
- predicted customer behavior
- risk
- business importance


======================================================================
3. DYNAMIC DISCOVERY — NO FIXED QUESTIONNAIRE
======================================================================

Do not implement the configuration assistant as a fixed list of questions.

The assistant must dynamically determine what it needs to know.

The next question must be influenced by:

- the current configuration state
- previous answers
- uploaded knowledge
- contradictions
- missing required fields
- likely customer questions
- business objective
- required tools
- policy requirements
- outcome requirements
- channel requirements
- provider capabilities
- detected uncertainty

The assistant should stop asking questions once sufficient information
exists for the Activity to be implemented and verified.

It should resume questioning only when a newly discovered dependency
creates a meaningful gap.


======================================================================
4. CORE-AWARE CONFIGURATION
======================================================================

The Configuration Copilot must understand the capabilities and
constraints exposed by QEVION Core.

It should know the available architectural primitives and capability
contracts, including where applicable:

- Activities
- Objectives
- Policies
- Knowledge
- Tools
- Outcomes
- Handoff
- Conversation State
- Customer Context
- Channels
- Voice capabilities
- ASR
- TTS
- VAD
- interruption
- provider adapters
- versioning
- observability
- evaluation

This knowledge must come from machine-readable capability metadata or
equivalent authoritative configuration.

Do NOT hardcode a copy of Core capabilities into conversational prompts
when a discoverable capability registry can be used.

The Copilot must be able to answer:

    "Can QEVION do this?"

with a capability-aware response.

Possible results:

    SUPPORTED
    SUPPORTED_WITH_CONFIGURATION
    REQUIRES_TOOL
    REQUIRES_PROVIDER_CAPABILITY
    REQUIRES_NEW_PLATFORM_CAPABILITY
    UNSUPPORTED
    UNVERIFIED


======================================================================
5. PROVIDER-AWARE CONFIGURATION
======================================================================

QEVION must distinguish between:

A. Configuration / Design Chat Provider
B. Runtime Reasoning Provider
C. Voice Provider(s)
D. ASR Provider
E. TTS Provider
F. Other specialized providers

The Configuration Copilot may be powered by a strong model/provider selected
by an administrator.

The business operator must NOT be required to configure this provider
manually at Activity level unless explicitly desired.

Administrators should be able to configure the provider used for the
configuration workspace through the Admin layer.

The configuration provider should be treated as replaceable.

Do not hardcode one model or vendor into the Builder architecture.


======================================================================
6. ADMIN PROVIDER CONTROL
======================================================================

The future Admin system must be able to define which provider/model is
responsible for the Configuration Copilot.

Separately, Admin may configure:

- runtime reasoning providers
- ASR providers
- TTS providers
- voice providers
- realtime providers
- other capability providers

These selections must remain independent.

The provider used to build an Activity does not automatically become the
provider used to execute the Activity.

This is an architectural requirement.

Example:

    Configuration Copilot:
        Provider A

    Runtime Reasoning:
        Provider B

    ASR:
        Provider C

    TTS:
        Provider D

    VAD:
        Provider E / local component

    Transport:
        Provider F / implementation

The configuration architecture must support this composition.


======================================================================
7. DOCUMENT / FILE INGESTION
======================================================================

The Configuration Copilot must support operator-supplied business
materials where the product channel permits them.

Examples include:

- Excel
- CSV
- TXT
- PDF
- DOC/DOCX
- structured exports
- knowledge files
- product catalogs
- price lists
- policy documents
- FAQ files
- service descriptions
- offer documents
- internal instructions
- other supported business references

The Copilot must not merely attach these documents to a prompt.

It must perform structured inspection.

The ingestion workflow should conceptually be:

    Upload
    ->
    Parse
    ->
    Normalize
    ->
    Identify Entities
    ->
    Extract Facts
    ->
    Identify Relationships
    ->
    Detect Missing Information
    ->
    Detect Contradictions
    ->
    Detect Ambiguity
    ->
    Identify Customer-Facing Questions
    ->
    Identify Operational Requirements
    ->
    Feed Findings into Activity Design


======================================================================
8. KNOWLEDGE GAP DETECTION
======================================================================

After inspecting supplied materials, the Copilot should identify gaps such
as:

- missing prices
- missing variants
- missing eligibility rules
- missing product descriptions
- unclear terminology
- missing availability information
- contradictory values
- stale-looking information
- undefined edge cases
- missing escalation rules
- missing business policies
- missing confirmation requirements
- unsupported claims
- missing customer-facing answers
- missing tool requirements

Each gap should be classified.

Example:

    REQUIRED_FOR_EXECUTION
    IMPORTANT_FOR_QUALITY
    OPTIONAL_IMPROVEMENT
    POLICY_RISK
    DATA_CONFLICT
    UNKNOWN


======================================================================
9. CUSTOMER QUESTION DISCOVERY
======================================================================

One of the most important responsibilities of the Copilot is to think from
the customer's perspective.

Given:

    Activity objective
    +
    Business knowledge
    +
    Product/service information
    +
    audience
    +
    channel

the Copilot should derive categories of questions and situations that may
occur during the conversation.

Do NOT attempt to enumerate literally every sentence a customer could say.

Instead construct a structured coverage model.

For each important entity, consider:

- price
- variants
- differences
- ingredients/materials/specifications
- compatibility
- eligibility
- availability
- timing
- location
- delivery/service limitations
- alternatives
- recommendation
- comparisons
- objections
- complaints
- cancellation/change
- follow-up
- clarification
- correction
- unrelated questions
- unsupported questions

This coverage model should become part of Activity readiness and evaluation.


======================================================================
10. OBJECTION DISCOVERY
======================================================================

For sales, retention, reorder, and other persuasive Activities, the Copilot
must proactively identify likely objections.

Examples:

    "السعر غالي"
    "مش محتاجه"
    "عندي بديل"
    "هفكر"
    "العرض متوفر لحد إمتى؟"
    "إيه الفرق بين ده والمنتج التاني؟"
    "هل أنا مؤهل؟"

The Copilot should ask the business owner how each important objection
should be handled when the answer is not derivable from approved knowledge.

It must never invent a discount, eligibility rule, guarantee, urgency,
benefit, or business claim.

The goal is to prepare the agent for objections while preserving business
truth.


======================================================================
11. UNSPECIFIED QUESTION HANDLING
======================================================================

The configuration process must explicitly ask:

    "What should the agent do when the customer asks something that is not
     covered by the supplied knowledge or Activity definition?"

This cannot remain an implicit decision.

The operator should be able to define behavior such as:

    ANSWER_FROM_APPROVED_KNOWLEDGE
    ASK_CLARIFYING_QUESTION
    STATE_LIMITATION
    OFFER_HUMAN_HANDOFF
    COLLECT_QUESTION
    REQUEST_ADDITIONAL_INFORMATION
    CLOSE_GRACEFULLY
    USE_AUTHORIZED_TOOL
    DECLINE_UNSUPPORTED_REQUEST

The final Activity must contain explicit unknown-question behavior.

Do NOT leave an open-ended "the model decides" hole for important business
scenarios.


======================================================================
12. CONVERSATION COVERAGE MODEL
======================================================================

The Copilot should build a structured coverage model rather than a rigid
script.

The model may include:

    Objective Coverage
    Knowledge Coverage
    Question Coverage
    Objection Coverage
    Tool Coverage
    Policy Coverage
    Exception Coverage
    Escalation Coverage
    Outcome Coverage
    Recovery Coverage

The purpose is to make the future runtime adaptable while reducing
behavioral blind spots.


======================================================================
13. CALL QUALITY OPTIMIZATION
======================================================================

The Copilot should proactively identify behaviors that may reduce call
quality.

Examples:

- repeated questions
- unnecessary information requests
- long explanations
- missing context
- redundant confirmations
- unnatural transitions
- abrupt topic changes
- repeated offer presentation
- asking for data already known
- asking for data that is not actually required
- poor objection handling
- missing customer concerns
- premature closing
- no clear next action
- excessive verbosity
- failure to acknowledge correction
- failure to recognize ambiguity

It should propose improvements.

These are recommendations until accepted by the operator or encoded by an
authorized policy/configuration mechanism.


======================================================================
14. CALL EFFICIENCY
======================================================================

The Copilot should optimize the Activity for useful completion rather than
maximum conversation length.

It should consider:

- what information is essential
- what can be deferred
- what can be inferred safely
- what must be verified
- what must be confirmed
- when enough information has been collected
- when to close
- when to escalate

Never optimize efficiency by skipping required disclosures or confirmation.


======================================================================
15. LEAD / OUTCOME QUALITY
======================================================================

For Activities that produce leads, orders, bookings, qualified contacts,
retention actions, or other outcomes, the Copilot should determine what
structured information is necessary to make the resulting outcome useful.

Example:

A sales Activity may require:

- contact identity
- product interest
- eligibility
- stated need
- objection
- disposition
- acceptance
- callback requirement
- next action

The Copilot should recommend outcome fields based on the Activity objective.

The operator can accept, reject, or modify the proposal.

Outcome schema remains explicit and versioned.


======================================================================
16. "WHAT COULD GO WRONG?" REVIEW
======================================================================

Before declaring an Activity ready, the Copilot should perform a
pre-execution challenge pass.

It should ask internally:

- What can the customer misunderstand?
- What could the agent misunderstand?
- What information is missing?
- Which claims are not verified?
- Which questions are unanswered?
- Which tools are missing?
- Which actions are unauthorized?
- Which policy conflicts exist?
- Which outcomes are impossible to distinguish?
- Where could repetition occur?
- Where could the conversation become stuck?
- What happens if the customer changes their mind?
- What happens if the customer asks an unrelated question?
- What happens if the customer interrupts?
- What happens if a provider fails?
- What happens if knowledge is unavailable?
- What happens if a tool returns an error?
- What happens if the customer requests a human?

The output must become structured readiness findings.


======================================================================
17. CAPABILITY MAPPING
======================================================================

The Copilot must map business requirements onto QEVION capabilities.

Example:

Operator says:

    "عايز الأجنت يعرف العميل هل المنتج متاح حاليا."

The Copilot may determine:

    Requirement:
        availability verification

    Required capability:
        authorized availability tool

    Current state:
        MISSING TOOL

    Action:
        ask operator to configure or connect an availability source

It must NOT pretend the feature exists simply because the LLM can talk
about availability.


======================================================================
18. INTEGRATION DISCOVERY
======================================================================

The configuration assistant should minimize integration burden.

It should first determine whether the required behavior can be achieved
through existing QEVION capabilities and configuration.

Only when necessary should it request:

- tool integration
- knowledge source
- provider capability
- external API
- specialized capability

The assistant should explicitly distinguish:

    no integration needed
    configuration only
    existing integration available
    new integration required
    new core capability required

This prevents unnecessary integrations and custom engineering.


======================================================================
19. PROVIDER/CAPABILITY FIT
======================================================================

The Copilot may inspect the configured provider capability registry.

It should determine whether the selected runtime stack can support:

- required language
- required dialect
- voice
- streaming
- interruption
- latency
- model requirements
- tool calling
- context requirements

If a required capability is unavailable, the Copilot must surface the gap.

It must never hide a provider limitation by generating an optimistic
configuration.


======================================================================
20. SIMULATION BEFORE ACTIVATION
======================================================================

The configuration workspace should support a pre-activation simulation mode.

After sufficient information is collected, the operator should be able to
test the Activity before putting it into production use.

Simulation should support representative scenarios such as:

- normal customer
- confused customer
- skeptical customer
- demanding customer
- customer asking follow-ups
- customer asking comparisons
- customer making corrections
- customer changing topic
- customer interrupting
- customer asking unsupported questions
- tool failure
- missing knowledge
- human handoff
- objection handling
- successful completion
- unsuccessful completion

The purpose is to expose configuration defects before real deployment.


======================================================================
21. ADVERSARIAL SIMULATION
======================================================================

The Copilot should be capable of generating test conversations intended to
stress the Activity.

This may include:

- unexpected questions
- ambiguous references
- contradictory information
- repeated objections
- rapid topic switching
- missing information
- customer corrections
- attempts to push the agent outside its policy
- requests for unsupported claims
- conflicting data
- tool failure
- provider interruption
- incomplete customer information

The test simulator is not the production agent.

Its job is to discover weaknesses.


======================================================================
22. ACTIVITY BLUEPRINT
======================================================================

At the end of the configuration process, the Copilot must produce a
machine-readable canonical Activity Blueprint.

The Blueprint should contain, where applicable:

    Tenant
    Business Profile
    Line
    Direction
    Channel
    Activity
    Objective
    Secondary Objectives
    Required Data
    Optional Data
    Knowledge Sources
    Knowledge Requirements
    Tools
    Tool Permissions
    Policies
    Allowed Claims
    Prohibited Claims
    Confirmation Rules
    Language
    Locale
    Dialect
    Voice Requirements
    Pronunciation Rules
    Conversation Guidance
    Question Coverage
    Objection Coverage
    Exception Handling
    Unknown Question Policy
    Handoff Rules
    Completion Criteria
    Failure Criteria
    Outcome Schema
    Next Actions
    Contact Policy Hooks
    Evaluation Cases
    Version Metadata

The Blueprint is the handoff artifact between the Configuration Copilot
and the authoritative QEVION runtime configuration system.


======================================================================
23. BLUEPRINT VALIDATION
======================================================================

The Blueprint must be validated independently of the Copilot's natural
language output.

The validation layer must check:

- schema validity
- required fields
- policy consistency
- capability availability
- provider compatibility
- tool availability
- outcome completeness
- unknown-question behavior
- escalation behavior
- contradiction
- version references

The LLM's statement:

    "Everything looks good."

is NOT validation evidence.


======================================================================
24. READINESS STATE
======================================================================

An Activity should have an explicit readiness state.

Possible states:

    DRAFT
    DISCOVERY_IN_PROGRESS
    NEEDS_INFORMATION
    NEEDS_CONFIGURATION
    BLOCKED
    READY_FOR_SIMULATION
    SIMULATION_FAILED
    READY_FOR_ACTIVATION
    ACTIVE
    SUSPENDED
    RETIRED

Do not allow an Activity to become active merely because the chat
conversation ended.


======================================================================
25. OPERATOR CONTROL
======================================================================

The Copilot proposes.

The operator owns authoritative business decisions.

The operator must be able to:

- accept
- reject
- edit
- add
- remove
- override
- request another suggestion

The system must preserve the difference between:

    AI suggestion

and:

    operator-approved configuration


======================================================================
26. NO SILENT BUSINESS POLICY CREATION
======================================================================

The Copilot must not silently create business rules such as:

- discounts
- prices
- guarantees
- eligibility
- refund rules
- availability
- delivery promises
- escalation policies
- contact permissions

unless such rules are explicitly supplied by the operator or authoritative
business sources.

The Copilot may identify that a rule is missing.

It must ask.


======================================================================
27. KNOWLEDGE GAP → QUESTION LOOP
======================================================================

A powerful design pattern should be used:

    Source Material
        ->
    Extracted Knowledge
        ->
    Detected Gap
        ->
    Business Question
        ->
    Operator Answer
        ->
    Validated Fact
        ->
    Activity Blueprint
        ->
    Simulation
        ->
    New Gap Detection
        ->
    Refinement

The system should be allowed to iterate through this loop until:

    READY

or:

    BLOCKED

The loop should be adaptive rather than a fixed number of rounds.


======================================================================
28. QUALITY IMPROVEMENT LOOP
======================================================================

After simulation or real executions, findings may feed back into the
Configuration Copilot.

Examples:

    repeated customer question
        ->
    knowledge gap detected
        ->
    operator asked for clarification
        ->
    knowledge updated
        ->
    Activity revalidated

or:

    repeated objection
        ->
    objection pattern identified
        ->
    business response missing
        ->
    operator decision requested
        ->
    Activity revision proposed

The learning must not silently change active business policy.


======================================================================
29. FEEDBACK FROM REAL CALL OUTCOMES
======================================================================

The future system should allow real outcomes and conversation analytics to
inform Activity improvement.

Possible signals:

- repeated questions
- abandonment point
- repeated clarification
- common objections
- failed tool calls
- unsupported questions
- handoff frequency
- incomplete outcomes
- missing data
- customer corrections
- excessive turn count
- repeated explanations

The Copilot may use these signals to recommend changes.

Recommendations require appropriate operator approval before policy-affecting
changes become active.


======================================================================
30. ACTIVITY VERSIONING
======================================================================

Every accepted Activity configuration must create or update a version.

The version must preserve:

- source inputs
- extracted knowledge
- operator decisions
- accepted suggestions
- rejected suggestions where useful
- policy versions
- knowledge versions
- tool versions
- provider configuration
- evaluation cases
- simulation findings
- readiness result

This creates an auditable path:

    Conversation with Builder
        ->
    Proposal
        ->
    Operator Decision
        ->
    Blueprint
        ->
    Validation
        ->
    Simulation
        ->
    Activity Version
        ->
    Activation


======================================================================
31. PROVIDER INDEPENDENCE OF BLUEPRINT
======================================================================

An Activity Blueprint must not encode one model's private prompt format
as the authoritative business definition.

The Blueprint must represent QEVION semantics.

Provider-specific formatting happens in adapters.

This guarantees that changing the Configuration Copilot provider does not
invalidate Activity definitions.


======================================================================
32. DOCUMENT-GROUNDED CONFIGURATION
======================================================================

When the operator provides business documents, the system must preserve
provenance.

Every extracted important fact should be traceable to:

- source document
- source version
- location where applicable
- extraction status
- confidence/verification state

Distinguish:

    directly stated
    inferred
    ambiguous
    conflicting
    unverified

Business-critical facts should not become authoritative merely because an
LLM extracted them.


======================================================================
33. CONFLICT DETECTION
======================================================================

The Copilot must detect conflicts in supplied materials.

Example:

    File A:
        product price = X

    File B:
        product price = Y

The system must NOT silently choose one.

It must surface:

    CONFLICT DETECTED

and ask the operator or authoritative data source to resolve it.


======================================================================
34. BUSINESS SOURCE PRIORITY
======================================================================

The configuration system should allow source priority to be explicit.

Example:

    live operational API
        >
    approved database
        >
    approved knowledge document
        >
    historical material

The exact hierarchy is configurable.

The key requirement is that source authority is explicit rather than
implicitly determined by whichever text the model happens to see.


======================================================================
35. QUESTION PRIORITIZATION
======================================================================

Do not ask all detected questions.

Prioritize questions based on:

- blocking importance
- business impact
- safety/policy impact
- frequency likelihood
- outcome impact
- dependency impact
- uncertainty

The operator experience must remain simple.

The system should feel like an intelligent conversation, not a setup wizard
with hundreds of fields.


======================================================================
36. CONVERSATIONAL UX PRINCIPLE
======================================================================

The Configuration Copilot should feel like an experienced solution
architect talking to the business owner.

It should be:

- concise when possible
- detailed when needed
- contextual
- aware of previous answers
- capable of explaining why a question matters
- capable of proposing defaults
- capable of identifying missing information
- capable of challenging inconsistent requirements
- capable of saying "I don't know"
- capable of saying "this requires another capability"

It must not overwhelm the user with technical implementation details unless
asked.


======================================================================
37. PROGRESSIVE DISCLOSURE
======================================================================

Do not expose every configuration detail at once.

Start with:

    objective
    ->
    direction
    ->
    business context

Then progressively discover:

    knowledge
    ->
    expected questions
    ->
    objections
    ->
    tools
    ->
    policies
    ->
    outcomes
    ->
    edge cases
    ->
    simulation

Only surface complexity when the Activity actually requires it.


======================================================================
38. MINIMUM REQUIRED CONFIGURATION
======================================================================

The Copilot must understand that not every Activity needs every feature.

A simple informational Activity may require only:

    identity
    objective
    knowledge
    language
    channel
    outcome

A complex sales Activity may additionally require:

    tools
    eligibility
    objections
    confirmation
    contact policy
    next actions
    lead schema
    simulation coverage

The configuration process must therefore be capability-driven rather than
field-driven.


======================================================================
39. "STOP ASKING" INTELLIGENCE
======================================================================

The Copilot must know when enough information has been gathered.

It should not continue asking unnecessary questions simply because more
questions are possible.

The system should conclude discovery when:

- required business intent is defined
- required knowledge is available
- required tools exist or are explicitly deferred
- policies are coherent
- unknown-question behavior is defined
- outcomes are defined
- critical gaps are resolved
- required capabilities are available
- readiness conditions are satisfied

Then transition to:

    REVIEW
    ->
    SIMULATION
    ->
    VALIDATION


======================================================================
40. "ASK THE OWNER" ESCAPE HATCH
======================================================================

Whenever the system reaches a business decision that cannot safely be
derived, it must ask the operator.

Examples:

    "What should the agent say if the customer asks about refunds?"

    "Which offer should be presented if the customer is eligible for both?"

    "Can the agent promise same-day delivery?"

    "What should happen after three unsuccessful attempts?"

This mechanism prevents the LLM from filling business gaps with invented
assumptions.


======================================================================
41. CONFIGURATION COPILOT SECURITY
======================================================================

The Configuration Copilot must treat uploaded documents and operator
messages as potentially untrusted inputs.

Protect against:

- prompt injection in documents
- malicious instructions embedded in files
- unauthorized policy modification
- data exfiltration
- cross-tenant knowledge leakage
- arbitrary tool execution
- provider credential exposure

Document text must be treated as DATA unless explicitly promoted to an
authoritative configuration source through the defined workflow.


======================================================================
42. CONFIGURATION COPILOT DOES NOT BYPASS CORE
======================================================================

The Copilot must never directly write hidden business state bypassing
QEVION configuration contracts.

Its output must pass through canonical validation and persistence.

Conceptually:

    Copilot
        ->
    Proposed Configuration
        ->
    Schema Validation
        ->
    Capability Validation
        ->
    Policy Validation
        ->
    Operator Approval
        ->
    Versioned Activity
        ->
    Runtime


======================================================================
43. CONFIGURATION CHAT PROVIDER FAILURES
======================================================================

If the Configuration Copilot provider fails:

- preserve current configuration state
- preserve uploaded source metadata
- preserve operator decisions
- prevent partial corrupt configuration
- allow retry or provider substitution
- never lose canonical Activity data

Provider failure must be isolated from the runtime system.


======================================================================
44. COPILOT OBSERVABILITY
======================================================================

Observe the configuration process itself.

Track where appropriate:

- configuration session
- Activity draft version
- questions asked
- answers received
- uploaded sources
- extracted facts
- identified gaps
- conflicts
- proposed changes
- operator decisions
- validation failures
- simulation findings
- readiness transitions
- provider/model/version
- latency
- errors

Avoid unnecessary retention of sensitive conversational content.


======================================================================
45. CONFIGURATION EVALUATION
======================================================================

The Configuration Copilot itself must be evaluated.

Test whether it can:

- gather the necessary requirements
- avoid unnecessary questions
- detect missing information
- detect contradictions
- inspect uploaded materials correctly
- identify likely customer questions
- identify objections
- identify tool requirements
- identify policy gaps
- generate a valid Blueprint
- avoid inventing business facts
- preserve operator decisions
- detect unsupported capabilities
- produce simulation-ready Activities
- improve Activities based on evidence

A successful chat conversation is not sufficient proof.


======================================================================
46. SUPERFICIAL-COMPLIANCE ATTACKS
======================================================================

The specification must explicitly reject weak implementations such as:

- a chatbot with a fixed setup questionnaire
- a static list of Activity fields
- document upload that only dumps text into a prompt
- generic "AI suggestions" with no structured output
- fake capability awareness
- invented answers to missing business questions
- a single generated system prompt presented as an Activity
- automatic policy creation without operator approval
- simulation that only runs scripted happy paths
- provider metadata that is not actually checked
- readiness marked READY without validation
- uploaded files with no provenance
- document conflicts silently merged
- customer-question discovery implemented as a fixed FAQ list


======================================================================
47. REQUIRED OUTPUT CONTRACT
======================================================================

The Configuration Copilot must produce two different outputs:

A. Human-facing conversational explanation

    What we know
    What is missing
    What was detected
    What is recommended
    What requires your decision
    Whether the Activity is ready

B. Machine-readable proposed configuration

    Activity Blueprint
    Evidence/Provenance
    Gaps
    Risks
    Capability Requirements
    Validation Findings
    Simulation Cases
    Readiness State

These two outputs must not be conflated.


======================================================================
48. END-TO-END CONFIGURATION FLOW
======================================================================

The intended experience is:

    Operator Opens Configuration Center
        ->
    Select / Create Business
        ->
    Create / Select Line
        ->
    Choose Direction
        ->
    State Objective Naturally
        ->
    Copilot Discovers Requirements
        ->
    Operator Uploads Business Materials
        ->
    Source Ingestion
        ->
    Knowledge Extraction
        ->
    Gap Detection
        ->
    Question Discovery
        ->
    Operator Answers Missing Business Questions
        ->
    Capability Mapping
        ->
    Tool / Provider Requirement Discovery
        ->
    Policy & Unknown-Question Design
        ->
    Outcome Design
        ->
    Coverage Construction
        ->
    Draft Activity Blueprint
        ->
    Validation
        ->
    Simulation
        ->
    Adversarial Simulation
        ->
    Findings
        ->
    Refinement
        ->
    Operator Approval
        ->
    Versioned Activity
        ->
    READY FOR ACTIVATION


======================================================================
49. CORE ARCHITECTURAL PRINCIPLE
======================================================================

This Configuration Copilot exists to reduce implementation errors BEFORE
production execution.

Its purpose is not to make the user fill more configuration fields.

Its purpose is to convert:

    vague business intent

into:

    explicit business requirements
    +
    verified knowledge
    +
    capability requirements
    +
    policies
    +
    outcomes
    +
    coverage
    +
    test cases
    +
    validated Activity Blueprint

The stronger the configuration intelligence, the less ambiguity reaches the
runtime.

This should be treated as an architectural quality mechanism, not merely a
UI feature.


======================================================================
50. MASTER QUALITY OBJECTIVE
======================================================================

The configuration system should aim to detect problems BEFORE the voice
agent experiences them with a real customer.

The ideal flow is:

    Business Owner says:
        "I want this line to achieve X."

    QEVION asks:
        "What do we need to know to achieve X safely and reliably?"

    QEVION inspects:
        supplied business material,
        available capabilities,
        likely customer behavior,
        operational constraints.

    QEVION discovers:
        missing facts,
        missing tools,
        unsupported capabilities,
        likely questions,
        objections,
        policy gaps,
        outcome gaps,
        failure paths.

    QEVION asks:
        only the decisions the business owner must make.

    QEVION proposes:
        a complete Activity design.

    QEVION simulates:
        realistic and adversarial interactions.

    QEVION validates:
        whether the Activity can actually run.

    QEVION produces:
        a versioned, executable, evidence-backed Activity Blueprint.

This is the intended standard for the QEVION configuration experience.

======================================================================
111. FINAL CLOSURE CHECK
======================================================================

Before completion, verify all of the following:

[ ] The new document is coherent from beginning to end.
[ ] No contradictory legacy requirement remains unresolved.
[ ] README claims are not treated as proof.
[ ] No historical failure is invented.
[ ] All known QEVION architectural decisions are represented.
[ ] QEVION is generic rather than restaurant-specific.
[ ] Activity is configuration-first.
[ ] Activity defines WHAT rather than a fixed HOW.
[ ] Inbound is supported conceptually.
[ ] Outbound is supported conceptually.
[ ] Campaign remains a future boundary.
[ ] Line/Endpoint is first-class.
[ ] Outcome Engine is first-class.
[ ] Human handoff is first-class.
[ ] Knowledge is generic.
[ ] Tools are typed and governed.
[ ] Business truth is separated from model output.
[ ] Contextual conversation is first-class.
[ ] Recommendations are grounded.
[ ] Comparisons are grounded.
[ ] Multi-intent works architecturally.
[ ] Topic switching is supported.
[ ] Corrections are supported.
[ ] Repetition has root-cause evidence.
[ ] Voice is a genuine realtime architecture.
[ ] Browser speech APIs are not the architectural definition.
[ ] VAD is separated from turn detection.
[ ] Interruption is explicitly specified.
[ ] ASR/LLM/TTS/VAD/transport are logically separable.
[ ] Multilingual architecture is global.
[ ] Egyptian Arabic is a benchmark, not the architecture.
[ ] Pronunciation layer exists.
[ ] Language capability registry exists.
[ ] Provider abstraction is real.
[ ] Provider adapters remain thin.
[ ] Telephony is explicitly future scope.
[ ] Security is enforceable.
[ ] Tenant isolation is explicit.
[ ] Observability is sufficient.
[ ] Versioning is explicit.
[ ] Evaluation exists.
[ ] Replay/regression exists.
[ ] Self-improvement is bounded.
[ ] Operator approval exists.
[ ] Licensing is separately governed.
[ ] Reference pool is open-ended.
[ ] Reference selection is evidence-based.
[ ] Performance measurement is defined.
[ ] Cost concerns are architecturally visible.
[ ] Acceptance criteria are testable.
[ ] Evidence requirements exist.
[ ] Red-team loopholes have countermeasures.
[ ] X² quality bar has been applied.
[ ] The result is implementation-grade.


======================================================================
112. FINAL INSTRUCTION
======================================================================
مرجع مهم اريدك ان تختزل منه الخيارات المجانيه المتاحه لتضيفها مع السماح لي بتخصيصصها ادمجها مع المراجع الحاليه 
https://gist.github.com/pijsal1-tech/c3ccd4f6bf15b580e9442cc367d1a9d6

Do not optimize for how impressive the document sounds.

Optimize for whether an independent future engineering agent can build the intended system correctly from this specification alone.

The final document must be:

    explicit
    general
    measurable
    testable
    versionable
    provider-neutral
    channel-neutral
    security-conscious
    failure-aware
    implementation-oriented
    resistant to superficial compliance

Rewrite QEVION_VOICE_RUNTIME_POC_SPEC_v2.md now.
Do not implement QEVION.
Do not modify unrelated files.
Do not omit requirements simply because the document becomes large.

THE SPECIFICATION IS THE PRODUCT OF THIS PHASE.
