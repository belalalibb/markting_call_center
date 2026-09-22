# ADR-0003 — Telephony Seam and Outbound Semantics

- **Status:** Accepted (operator decisions D7, D10 — 2026-09-22)
- **Spec:** §35 QV-TEL / QV-OUT-DIR, §36 QV-CAMP, §11 contact_policy_hooks

## Context
Both v2.3 and the master prompt (X² §50) declare telephony **future scope**, yet outbound Activities (surveys, reminders, follow-ups) must be designable and testable now. Mixing PSTN/SIP concerns into the POC would block the exit gates without adding evidence about the Core.

## Decision
1. **Telephony seam only:** define `qevion.contracts.telephony.v1` (dial request, call events, DTMF, transfer) and a `TelephonyPort` with a **simulated** adapter. No SIP/WebRTC-to-PSTN implementation in the POC.
2. **Outbound = direction semantic:** `direction: outbound` changes the dialog machine's opening (identity check, consent, purpose disclosure) and enables `contact_policy_hooks` (consent_required, attempt_limit, contact_window, suppression list). Everything else in the Core is identical to inbound.
3. **Simulated dial:** the Operator Console can "place" an outbound call that opens a browser voice session against the simulated telephony adapter, producing the same events a real dial would.
4. **Campaigns are out of scope** (§36): no scheduling, list management, or pacing in the POC. Hooks exist so a campaign layer can call `start_session(direction=outbound, contact_ref)`.

## Consequences
- + Activity C (§54) exercises outbound semantics end-to-end without carrier integration.
- + Consent/PDPL behaviour is tested early.
- − No evidence about real call audio quality/jitter until a carrier adapter exists.

## Evidence required
QV-ACC-006 (Activity C), QV-ACC-020 at CP-0008.
