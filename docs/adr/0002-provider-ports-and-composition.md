# ADR-0002 — Generic Core, Provider Role Ports, Composition, Credentials and Guards

- **Status:** Accepted (operator decisions D1, D2, D4, D9, D12, D13, D14, D15 — 2026-09-22)
- **Spec:** §5–§8, §15, §19–§24, §32–§33, §39.6, §42, §49

## Context
v2.3 modelled a single `provider.v1` contract and a restaurant-shaped `tenant_config.v1`. The master prompt demands a Core that executes any Activity unchanged and a provider layer where speech-to-speech and cascaded (ASR→LLM→TTS) compositions are interchangeable.

## Decision
1. **Generic Core (D1):** domain model is Activity / Field / Policy / Outcome only. The dialog machine is fixed; the activity machine is a data-driven table from the Blueprint. Core imports `qevion.contracts` + stdlib only (import-linter, QV-ACC-004) and contains no domain vocabulary (grep gate, QV-ACC-005).
2. **Terminology (D4):** `tenant_id`, `line_id`, `activity_id`, `activity_version`.
3. **Provider role ports (D2):** `s2s`, `llm`, `asr`, `tts`, `turn`, `decision`. A `composition.v1` config selects `s2s | cascade` and binds one adapter per role. Every port has a mock adapter.
4. **Tools (D12):** platform tools are generic (`lookup_knowledge`, `get_entity`, `record_field`, `verify_field`, `submit_record`, …); `submit_record` is the single generic write primitive; business tools are Blueprint data.
5. **Knowledge (D13):** structured retrieval only (facts/entities/rules with provenance); no vector RAG in the POC.
6. **CredentialResolver (D9):** resolution order `env → admin store → in-memory ephemeral UI key`; keys never persisted to disk by the UI path, never logged, never in Git.
7. **Budget guards (D14):** defaults $10 / 5 min per session / 20 sessions per day, enforced in runtime, emitting `budget.*` events.
8. **edge-tts REJECTED (D15)**; XTTS-v2 rejected (CPML). See `docs/registry/licenses.yaml`.

## Consequences
- + Three materially different Activities (§54) become the regression fixture for Core neutrality.
- + Provider outages or price changes are adapter-level concerns.
- − Composition adds config surface; mitigated by Preflight capability checks (§12, §16).
- − Deterministic decision logic must be written by us (ADR-0004).

## Evidence required
QV-ACC-004..010, QV-ACC-021.
