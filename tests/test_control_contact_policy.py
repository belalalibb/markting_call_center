"""QV-OUT-DIR-002 — contact-policy hooks evaluated before any outbound dial (ADR-0003)."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from qevion.contracts.policy import ContactPolicyHooks
from qevion.control.contact_policy import ContactRefusal, ContactState, evaluate_contact

HOOKS = ContactPolicyHooks(
    consent_required=True, attempt_limit=2, contact_window="10:00-20:00 Africa/Cairo", suppression_ref="sup_default"
)
CAIRO = ZoneInfo("Africa/Cairo")
NOON_CAIRO = datetime(2026, 9, 23, 12, 0, tzinfo=CAIRO)
MIDNIGHT_CAIRO = datetime(2026, 9, 24, 0, 0, tzinfo=CAIRO)


def test_allowed_when_every_hook_satisfied() -> None:
    d = evaluate_contact(HOOKS, ContactState("c1", consent=True), now=NOON_CAIRO)
    assert d.allowed and d.refusals == ()
    assert d.payload()["allowed"] is True


def test_unknown_consent_is_refused_conservatively() -> None:
    d = evaluate_contact(HOOKS, ContactState("c1"), now=NOON_CAIRO)
    assert not d.allowed and ContactRefusal.NO_CONSENT in d.refusals


def test_every_failing_hook_is_reported_not_just_the_first() -> None:
    st = ContactState("c1", consent=False, opted_out=True, suppressed=True, attempts=2)
    d = evaluate_contact(HOOKS, st, now=MIDNIGHT_CAIRO)
    assert set(d.refusals) == {
        ContactRefusal.NO_CONSENT,
        ContactRefusal.OPTED_OUT,
        ContactRefusal.SUPPRESSED,
        ContactRefusal.ATTEMPT_LIMIT,
        ContactRefusal.OUTSIDE_WINDOW,
    }


def test_suppression_via_tag_matches_suppression_ref() -> None:
    d = evaluate_contact(HOOKS, ContactState("c1", consent=True, tags={"sup_default"}), now=NOON_CAIRO)
    assert d.refusals == (ContactRefusal.SUPPRESSED,)


def test_attempt_limit_boundary() -> None:
    assert evaluate_contact(HOOKS, ContactState("c", consent=True, attempts=1), now=NOON_CAIRO).allowed
    assert not evaluate_contact(HOOKS, ContactState("c", consent=True, attempts=2), now=NOON_CAIRO).allowed


def test_contact_window_edges_and_overnight_and_unparseable() -> None:
    at_open = datetime(2026, 9, 23, 10, 0, tzinfo=CAIRO)
    at_close = datetime(2026, 9, 23, 20, 0, tzinfo=CAIRO)
    assert evaluate_contact(HOOKS, ContactState("c", consent=True), now=at_open).allowed
    assert evaluate_contact(HOOKS, ContactState("c", consent=True), now=at_close).allowed
    overnight = HOOKS.model_copy(update={"contact_window": "22:00-06:00 Africa/Cairo"})
    assert evaluate_contact(overnight, ContactState("c", consent=True), now=MIDNIGHT_CAIRO).allowed
    assert not evaluate_contact(overnight, ContactState("c", consent=True), now=NOON_CAIRO).allowed
    broken = HOOKS.model_copy(update={"contact_window": "whenever"})
    d = evaluate_contact(broken, ContactState("c", consent=True), now=NOON_CAIRO)
    assert d.refusals == (ContactRefusal.OUTSIDE_WINDOW,)  # unparseable → conservative refusal


def test_missing_hooks_refuse_outbound() -> None:
    d = evaluate_contact(None, ContactState("c", consent=True), now=datetime.now(UTC))
    assert not d.allowed and d.refusals == (ContactRefusal.HOOKS_MISSING,)


def test_no_consent_requirement_allows_unknown_consent() -> None:
    relaxed = HOOKS.model_copy(update={"consent_required": False, "contact_window": None})
    assert evaluate_contact(relaxed, ContactState("c")).allowed
