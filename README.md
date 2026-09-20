# markting_call_center — QEVION Voice Runtime

Provider-neutral realtime voice AI POC for QEVION (Egyptian Arabic restaurant voice agent).

## 📋 Governing Specification

**→ [`docs/QEVION_VOICE_RUNTIME_POC_SPEC_v2.md`](docs/QEVION_VOICE_RUNTIME_POC_SPEC_v2.md)** — Specification v2.0 (SaaS-Ready, Security-Hardened, Evidence-First). This is the binding document for building the POC. It supersedes v1 in its entirety.

Key principles:

- **Three hard domains:** QEVION Core / Provider Adapters / Transport Adapters (telephony deferred behind a contract slot).
- **Model output is never business truth** — tools, prices, confirmations, and state transitions are QEVION-owned.
- **Versioned, typed, negotiated contracts** (`provider.v1`, `transport.v1`, `event.v1`, `tool.v1`, `turndetection.v1`, …).
- **Deterministic state machines** — the model proposes, QEVION decides.
- **SaaS foundations from day one:** tenant isolation, privacy/recording policy (Egypt PDPL 151/2020 aware), cost metering, budget guards.
- **Evidence or it didn't happen** — every claim must point to an artifact.

Status: specification phase. Implementation follows the phased plan in spec §38.
