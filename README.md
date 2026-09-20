# markting_call_center — QEVION Voice Runtime

Provider-neutral realtime voice AI POC for QEVION (Egyptian Arabic restaurant voice agent).

## 📋 Governing Specification

**→ [`docs/QEVION_VOICE_RUNTIME_POC_SPEC_v2.md`](docs/QEVION_VOICE_RUNTIME_POC_SPEC_v2.md)** — Specification **v2.3** (SaaS-Ready, Security-Hardened, Evidence-First). This is the binding document for building the POC. It supersedes v1 in its entirety; v2.1/v2.2/v2.3 are additive revisions of v2.0 (see Appendix A).

Key principles:

- **Three hard domains:** QEVION Core / Provider Adapters / Transport Adapters (telephony deferred behind a contract slot).
- **Model output is never business truth** — tools, prices, confirmations, and state transitions are QEVION-owned.
- **Versioned, typed, negotiated contracts** (`provider.v1`, `transport.v1`, `event.v1`, `tool.v1`, `turndetection.v1`, `integration.v1`, …).
- **Deterministic state machines** — the model proposes, QEVION decides.
- **SaaS foundations from day one:** tenant isolation, privacy/recording policy (Egypt PDPL 151/2020 aware), cost metering, budget guards.
- **Explicit POC decision gate (v2.1):** GO / HOLD / CHANGE PROVIDER / CHANGE TOPOLOGY / STOP — thresholds fixed before evidence collection; provider changes require attribution evidence, not opinions.
- **External integration boundary (v2.1, design-only):** future QEVION products (social-media marketing, campaigns, CRM) consume voice capability via `integration.v1` without importing Core internals or provider SDKs — and never bypass the tool pipeline.
- **Operator Test Console (v2.2):** one browser cockpit for live manual sessions, the automated scenario suite, failure injection, replay, latency views, and evidence export — a control/view layer over the same test machinery, never the source of truth (§46).
- **Generic service & interaction primitives (v2.3):** opaque `service_id`, versioned ServiceConfig, provenance-tagged InteractionRecord, and a `route_requested` hook — raw material for future SaaS service lines, with zero SaaS machinery now (§47).
- **Evidence or it didn't happen** — every claim must point to an artifact.

Status: specification phase. Implementation follows the phased plan in spec §38.
