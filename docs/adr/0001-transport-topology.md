# ADR-0001 — Transport Topology, Web Stack and Preview Surface

- **Status:** Accepted (operator decisions D3, D5, D11 — 2026-09-22)
- **Spec:** §29 QV-TR, §43.7, §51–§52, Appendix C
- **Supersedes:** SPEC v2.3 §5 (FN-*) recommendation to build on Pipecat

## Context
v2.3 proposed adopting an open-source voice framework (Pipecat or LiveKit Agents) as the runtime foundation. The inspection (C3) found this conflicts with the master prompt's "no framework dogmatism" and "Core imports contracts only" rules, and adds a large dependency surface before a single real-provider session has been measured.

## Decision
1. **Topology A:** browser `AudioWorklet` captures/plays PCM16 @ 24 kHz → thin WebSocket (`qevion.contracts.transport.v1`) → QEVION runtime → provider adapter. No media server in the POC.
2. Pipecat and LiveKit Agents are **future transport adapters** behind the same transport port; never a foundation the Core depends on.
3. **Stack:** Python 3.12+, FastAPI, Pydantic v2, uvicorn; **one** TypeScript web app with three modes (Config Center · Operator Console · Admin).
4. **Preview surface:** the sandbox public service URL is the verified preview for every phase; Cloudflare/other hosting is post-POC.

## Consequences
- + Smallest possible latency path and full ownership of the 7-step interruption sequence (§31).
- + Provider swap and transport swap are independently testable (QV-ACC-004).
- − WebRTC/telephony media handling is deferred (ADR-0003).
- − We own reconnect/backpressure logic ourselves (§27 QV-ERR, §45 replay).

## Evidence required
QV-ACC-016, QV-ACC-017, QV-ACC-018 at CP-0006/0007.
