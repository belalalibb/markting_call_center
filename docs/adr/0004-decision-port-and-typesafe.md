# ADR-0004 — `decision.v1` Port: Deterministic-First, LLM-Assisted, TypeSafe Optional

- **Status:** Accepted (operator decisions D6, D8 — 2026-09-22)
- **Spec:** §23 QV-TRUTH, §24 QV-TOOL, §32 QV-PROV (decision role), §49 REF-010

## Context
The Core must decide things like "is this field value acceptable", "did the user confirm", "is this claim allowed", "which activity state comes next". The master prompt forbids letting the model be business truth (X² §28, §65). A third-party structured-decision library ("TypeSafe") was proposed but its licence and maintenance status are UNVERIFIED.

## Decision
1. **Deterministic-first:** every decision consulted by the Core goes through `DecisionPort.decide(DecisionRequest) -> DecisionResult` where the **default adapter is pure Python rules** driven by Blueprint data (validation expressions, enums, policy tables). It is replayable and unit-testable.
2. **LLM-assisted, never LLM-authoritative:** an `llm` role adapter may *propose* a classification (e.g. intent, confirmation polarity) but the result is accepted only if it passes the deterministic validator; otherwise the Core applies `uncertainty_policy` (ASK_CLARIFYING_QUESTION etc.).
3. **TypeSafe is optional/deferred (D8):** it may be wrapped as an alternative `decision` adapter after licence verification (`licenses.yaml` gate) and only if it beats the deterministic adapter on the evaluation set. Nothing in the Core may import it.
4. `DecisionResult` always carries `{value, confidence, source: RULE|LLM_VALIDATED|UNKNOWN, evidence_refs[]}` and is logged as `decision.made` events for replay.

## Consequences
- + Business truth stays in Blueprint data and rules; replay is deterministic (QV-ACC-019).
- + Claim Governor and ConfirmationInterpreter share one port.
- − Some nuanced Arabic confirmations may require the LLM proposal path; covered by evaluation corpus (§44).

## Evidence required
QV-ACC-007, QV-ACC-008, QV-ACC-019.
