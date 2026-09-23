"""Outbound contact-policy hooks (QV-OUT-DIR-002, ADR-0003) — evaluated BEFORE a session opens.

Hooks are data-driven from `policies.contact_policy_hooks` and a `ContactState` the host supplies
(consent, opt-out, suppression, prior attempts). No jurisdiction logic lives here (DEFERRED); this
is the enforcement seam every outbound dial must pass through. Every refusal names its reason so
the outcome/attempt record is auditable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from zoneinfo import ZoneInfo

from qevion.contracts.policy import ContactPolicyHooks


class ContactRefusal(StrEnum):
    NO_CONSENT = "no_consent"
    OPTED_OUT = "opted_out"
    SUPPRESSED = "suppressed"  # do-not-contact list
    ATTEMPT_LIMIT = "attempt_limit_reached"
    OUTSIDE_WINDOW = "outside_contact_window"
    HOOKS_MISSING = "contact_policy_hooks_missing"


@dataclass
class ContactState:
    """What the host knows about this contact (from CRM/DNC/etc.). Absence of data is treated conservatively."""

    contact_ref: str
    consent: bool | None = None  # None = unknown → refused when consent_required
    opted_out: bool = False
    suppressed: bool = False
    attempts: int = 0
    tags: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class ContactDecision:
    allowed: bool
    refusals: tuple[ContactRefusal, ...] = ()
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def payload(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "refusals": [r.value for r in self.refusals],
            "checked_at": self.checked_at.isoformat(),
        }


def _in_window(window: str | None, now: datetime) -> bool:
    """`"10:00-20:00 Africa/Cairo"` → True when `now` (converted) falls inside. Unparseable → conservative False."""
    if not window:
        return True
    try:
        span, tz = window.split(" ", 1)
        start_s, end_s = span.split("-")
        local = now.astimezone(ZoneInfo(tz.strip()))
        hh, mm = (int(x) for x in start_s.split(":"))
        eh, em = (int(x) for x in end_s.split(":"))
        start = local.replace(hour=hh, minute=mm, second=0, microsecond=0)
        end = local.replace(hour=eh, minute=em, second=0, microsecond=0)
        if end <= start:  # overnight window
            return local >= start or local <= end
        return start <= local <= end
    except (ValueError, KeyError):
        return False


def evaluate_contact(
    hooks: ContactPolicyHooks | None, state: ContactState, *, now: datetime | None = None
) -> ContactDecision:
    """All hooks are REQUIRED for outbound (QV-OUT-DIR-002): every failing hook is reported, not just the first."""
    now = now or datetime.now(UTC)
    if hooks is None:
        return ContactDecision(False, (ContactRefusal.HOOKS_MISSING,))
    refusals: list[ContactRefusal] = []
    if hooks.consent_required and state.consent is not True:
        refusals.append(ContactRefusal.NO_CONSENT)
    if state.opted_out:
        refusals.append(ContactRefusal.OPTED_OUT)
    if state.suppressed or (hooks.suppression_ref and hooks.suppression_ref in state.tags):
        refusals.append(ContactRefusal.SUPPRESSED)
    if state.attempts >= hooks.attempt_limit:
        refusals.append(ContactRefusal.ATTEMPT_LIMIT)
    if not _in_window(hooks.contact_window, now):
        refusals.append(ContactRefusal.OUTSIDE_WINDOW)
    return ContactDecision(not refusals, tuple(refusals), checked_at=now)
