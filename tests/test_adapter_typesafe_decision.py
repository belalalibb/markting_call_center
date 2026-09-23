"""TypeSafe (Jev) typed-decision adapter — offline with a fake HTTP; rules stay authoritative (ADR-0004)."""

from __future__ import annotations

from typing import Any

import pytest
from qevion.adapters.decision.rules import RulesDecisionAdapter
from qevion.adapters.decision.typesafe import LayeredDecisionAdapter, TypeSafeDecisionAdapter
from qevion.contracts.composition import CapabilityState
from qevion.contracts.provider import DecisionKind, DecisionRequest, DecisionSource


class FakeHttp:
    def __init__(self, choice: str, confidence: float, *, fail: Exception | None = None) -> None:
        self.choice, self.confidence, self.fail = choice, confidence, fail
        self.calls: list[dict[str, Any]] = []
        self.headers: list[dict[str, str]] = []

    def __call__(self, url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
        self.calls.append({"url": url, **body})
        self.headers.append(headers)
        if self.fail:
            raise self.fail
        qid = next(iter(body["questions"]))
        return {
            "model": "jev-1.13.0",
            "answers": {
                qid: {"type": "choice", "choice": self.choice, "confidence": self.confidence, "probabilities": {}}
            },
            "usage": {"input_tokens": 10, "output_tokens": 2},
        }


def _confirm(text: str) -> DecisionRequest:
    return DecisionRequest(kind=DecisionKind.INTERPRET_CONFIRMATION, inputs={"text": text})


async def test_confirmation_yes_with_confidence_is_llm_validated() -> None:
    http = FakeHttp("yes", 0.97)
    ad = TypeSafeDecisionAdapter("k", http=http)
    res = await ad.decide(_confirm("أيوه تمام ماشي"))
    assert res.value is True and res.source is DecisionSource.LLM_VALIDATED and res.confidence == 0.97
    assert http.calls[0]["url"].endswith("/v1/systemone") and http.calls[0]["state"] == "أيوه تمام ماشي"
    assert http.headers[0]["Authorization"] == "Bearer k"
    assert ad.last_model == "jev-1.13.0" and ad.calls == 1
    assert any(r.startswith("typesafe:jev") for r in res.evidence_refs)


async def test_low_confidence_or_ambiguous_is_unknown_never_guess() -> None:
    ad = TypeSafeDecisionAdapter("k", http=FakeHttp("ambiguous", 0.9))
    assert (await ad.decide(_confirm("هاه؟"))).is_unknown
    ad2 = TypeSafeDecisionAdapter("k", http=FakeHttp("yes", 0.51), min_confidence=0.6)
    r = await ad2.decide(_confirm("mm"))
    assert r.is_unknown and "low confidence" in (r.reason or "")


async def test_no_credential_and_network_failure_degrade_to_unknown() -> None:
    assert (await TypeSafeDecisionAdapter(None, http=FakeHttp("yes", 0.9)).decide(_confirm("yes"))).is_unknown
    r = await TypeSafeDecisionAdapter("k", http=FakeHttp("yes", 0.9, fail=OSError("down"))).decide(_confirm("yes"))
    assert r.is_unknown and "typesafe error" in (r.reason or "")


async def test_rules_only_kinds_are_refused_and_declared_unsupported() -> None:
    ad = TypeSafeDecisionAdapter("k", http=FakeHttp("yes", 0.99))
    for kind in (DecisionKind.VALIDATE_FIELD, DecisionKind.CHECK_CLAIM, DecisionKind.EVALUATE_RULE):
        r = await ad.decide(DecisionRequest(kind=kind, inputs={"text": "x"}))
        assert r.is_unknown and "rules-only" in (r.reason or "")
    caps = ad.capabilities()
    assert caps.state_of("decision:check_claim") is CapabilityState.UNSUPPORTED
    assert caps.state_of("decision:interpret_confirmation") is CapabilityState.SUPPORTED


async def test_classify_intent_uses_closed_options_only() -> None:
    http = FakeHttp("complaint", 0.88)
    ad = TypeSafeDecisionAdapter("k", http=http)
    req = DecisionRequest(
        kind=DecisionKind.CLASSIFY_INTENT,
        inputs={"text": "الأكل وصل بارد", "patterns": {"complaint": ["cold", "late"], "order": ["want"]}},
        options=["complaint", "order"],
    )
    r = await ad.decide(req)
    assert r.value == "complaint" and r.source is DecisionSource.LLM_VALIDATED
    crit = http.calls[0]["questions"]["intent"]["criteria"]
    assert set(crit) == {"complaint", "order", "none_of_these"}
    r2 = await TypeSafeDecisionAdapter("k", http=FakeHttp("refund", 0.99)).decide(req)
    assert r2.is_unknown  # an answer outside the closed set is never accepted
    # intents carry a higher floor than confirmations (live smoke: opt-out misread as order @0.69)
    r3 = await TypeSafeDecisionAdapter("k", http=FakeHttp("order", 0.69)).decide(req)
    assert r3.is_unknown and "0.75" in (r3.reason or "")


async def test_layered_rules_first_then_fallback_only_on_unknown() -> None:
    http = FakeHttp("no", 0.93)
    layered = LayeredDecisionAdapter(RulesDecisionAdapter(), TypeSafeDecisionAdapter("k", http=http))
    r = await layered.decide(_confirm("yes"))
    assert r.value is True and r.source is DecisionSource.RULE and http.calls == []
    r2 = await layered.decide(_confirm("خلاص بلاش"))
    assert r2.value is False and r2.source is DecisionSource.LLM_VALIDATED and len(http.calls) == 1
    assert layered.fallback_hits == 1
    r3 = await layered.decide(
        DecisionRequest(kind=DecisionKind.VALIDATE_FIELD, inputs={"value": "x", "validation": "weird"})
    )
    assert r3.is_unknown and len(http.calls) == 1  # rules-only kind never delegated


@pytest.mark.parametrize("name", ["decision:interpret_confirmation", "language:ar-EG"])
def test_layered_capabilities_merge(name: str) -> None:
    caps = LayeredDecisionAdapter(RulesDecisionAdapter(), TypeSafeDecisionAdapter(None)).capabilities()
    assert caps.adapter == "rules+typesafe"
    assert caps.state_of(name) in (CapabilityState.SUPPORTED, CapabilityState.PARTIAL)
