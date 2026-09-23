"""TypeSafe AI (Jev / System One) `DecisionPort` adapter — typed decisions with confidence, no text generation.

Jev answers closed questions (choice / score / yes-no probability) about a piece of text in one request, which
is exactly the shape of `qevion.decision.v1` (ADR-0004). It is **not** a language model and produces no
free text, so it can never become "business truth": it only classifies what the customer said.

Layering (QV-GOLD "LLM != business truth", ADR-0004):
* `RulesDecisionAdapter` stays authoritative. `TypeSafeDecisionAdapter` is consulted only for kinds it supports
  (`interpret_confirmation`, `classify_intent`); `check_claim` is never delegated — claim policy is data.
* Results carry `source=LLM_VALIDATED` + the reported confidence; below `min_confidence` -> `UNKNOWN`
  so Core applies `uncertainty_policy` instead of guessing.
* Credential comes from the resolver (env `TYPESAFE_API_KEY` / admin store / ephemeral UI) and is never logged.
* `validate_field`, `next_activity_state`, `evaluate_rule` are refused (UNKNOWN) — deterministic by design.

Wire protocol (verified live 2026-09-23): POST {base}/v1/systemone
  {"model": "jev-latest", "state": <text>, "questions": {<id>: {"type": "choice", "instructions": ..,
   "criteria": {<option>: <description>}}}}
  -> {"model": "jev-1.13.0", "answers": {<id>: {"type": "choice", "choice": .., "confidence": .., "probabilities": {..}}},
      "usage": {"input_tokens": .., "output_tokens": ..}}
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from qevion.contracts.composition import AdapterCapabilities, Capability, CapabilityState
from qevion.contracts.provider import DecisionKind, DecisionRequest, DecisionResult, DecisionSource, ProviderRole

DEFAULT_BASE_URL = "https://api.typesafe.ai"
DEFAULT_MODEL = "jev-latest"
PROVIDER_NAME = "typesafe"

HttpFn = Callable[[str, dict[str, str], dict[str, Any]], dict[str, Any]]  # (url, headers, body) -> json


def _urllib_http(url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 — https to a configured host
        data: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
        return data


class TypeSafeDecisionAdapter:
    """Typed-decision port over Jev. Supports interpret_confirmation + classify_intent; everything else UNKNOWN."""

    name = PROVIDER_NAME
    SUPPORTED_KINDS = frozenset({DecisionKind.INTERPRET_CONFIRMATION, DecisionKind.CLASSIFY_INTENT})

    def __init__(
        self,
        credential: str | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        min_confidence: float = 0.6,
        http: HttpFn | None = None,
    ) -> None:
        self._credential = credential
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.min_confidence = min_confidence
        self._http = http or _urllib_http
        self.calls = 0
        self.last_usage: dict[str, int] = {}
        self.last_model: str | None = None

    def capabilities(self) -> AdapterCapabilities:
        caps = [
            Capability(
                name=f"decision:{k.value}",
                state=CapabilityState.SUPPORTED if k in self.SUPPORTED_KINDS else CapabilityState.UNSUPPORTED,
                notes=None if k in self.SUPPORTED_KINDS else "deterministic by design; handled by rules",
            )
            for k in DecisionKind
        ]
        caps.append(
            Capability(
                name="language:ar-EG",
                state=CapabilityState.PARTIAL,
                notes="live probe 2026-09-23: Egyptian-Arabic confirmation -> yes @0.97",
            )
        )
        caps.append(Capability(name="language:any", state=CapabilityState.PARTIAL, notes="multilingual classifier"))
        return AdapterCapabilities(adapter=self.name, role=ProviderRole.DECISION, capabilities=caps)

    def set_credential(self, credential: str | None) -> None:
        self._credential = credential

    async def decide(self, request: DecisionRequest) -> DecisionResult:
        t0 = time.monotonic()
        if request.kind not in self.SUPPORTED_KINDS:
            return _unknown(f"{request.kind.value}: rules-only kind")
        if not self._credential:
            return _unknown("typesafe: no credential resolved")
        text = str(request.inputs.get("text", "")).strip()
        if not text:
            return _unknown("empty text")
        qid, question, mapping = self._question_for(request)
        if question is None:
            return _unknown("no closed options")
        body = {"model": self.model, "state": text, "questions": {qid: question}}
        headers = {"Authorization": f"Bearer {self._credential}", "Content-Type": "application/json"}
        try:
            data = self._http(f"{self.base_url}/v1/systemone", headers, body)
        except urllib.error.HTTPError as e:
            return _unknown(f"typesafe http {e.code}")
        except Exception as e:  # noqa: BLE001 — network failure degrades to UNKNOWN, never raises into Core
            return _unknown(f"typesafe error: {type(e).__name__}")
        self.calls += 1
        self.last_model = str(data.get("model") or self.model)
        self.last_usage = {k: int(v) for k, v in (data.get("usage") or {}).items()}
        ans = (data.get("answers") or {}).get(qid) or {}
        choice = ans.get("choice")
        confidence = float(ans.get("confidence") or 0.0)
        probabilities = ans.get("probabilities") or {}
        refs = [f"typesafe:{self.last_model}", f"probabilities:{json.dumps(probabilities, sort_keys=True)}"]
        decided_ms = int((time.monotonic() - t0) * 1000)
        value = mapping.get(str(choice)) if choice is not None else None
        if value is None or confidence < self.min_confidence:
            return DecisionResult(
                value=None,
                confidence=confidence,
                source=DecisionSource.UNKNOWN,
                reason=f"typesafe low confidence {confidence:.2f} < {self.min_confidence} (choice={choice})",
                evidence_refs=refs,
                decided_at_ms=decided_ms,
            )
        return DecisionResult(
            value=value,
            confidence=confidence,
            source=DecisionSource.LLM_VALIDATED,
            evidence_refs=refs,
            decided_at_ms=decided_ms,
        )

    def _question_for(self, req: DecisionRequest) -> tuple[str, dict[str, Any] | None, dict[str, Any]]:
        if req.kind is DecisionKind.INTERPRET_CONFIRMATION:
            q = {
                "type": "choice",
                "instructions": "Is the customer confirming (agreeing), denying (rejecting), or is the reply ambiguous?",
                "criteria": {
                    "yes": "agrees, confirms, accepts, says go ahead",
                    "no": "declines, rejects, corrects, says stop or wait",
                    "ambiguous": "unclear, a question, or unrelated to the confirmation",
                },
            }
            return "confirmation", q, {"yes": True, "no": False}
        options = list(req.options)
        patterns: dict[str, list[str]] = req.inputs.get("patterns", {}) or {}
        if not options:
            options = list(patterns.keys())
        if not options:
            return "intent", None, {}
        criteria = {opt: ", ".join(patterns.get(opt, [])) or opt.replace("_", " ") for opt in options}
        criteria["none_of_these"] = "does not match any listed intent"
        q = {"type": "choice", "instructions": "Which intent best matches what the customer said?", "criteria": criteria}
        return "intent", q, {opt: opt for opt in options}


def _unknown(reason: str) -> DecisionResult:
    return DecisionResult(value=None, confidence=0.0, source=DecisionSource.UNKNOWN, reason=reason)


class LayeredDecisionAdapter:
    """Rules first (authoritative); on UNKNOWN for a supported kind, ask the typed-decision fallback (ADR-0004)."""

    name = "rules+typesafe"

    def __init__(self, primary: Any, fallback: TypeSafeDecisionAdapter) -> None:
        self.primary = primary
        self.fallback = fallback
        self.fallback_hits = 0

    def capabilities(self) -> AdapterCapabilities:
        base = self.primary.capabilities()
        merged = list(base.capabilities)
        for c in self.fallback.capabilities().capabilities:
            if c.name.startswith("language:") and c.state is not CapabilityState.UNSUPPORTED:
                merged.append(Capability(name=c.name, state=c.state, notes=f"via {self.fallback.name}: {c.notes}"))
        return AdapterCapabilities(adapter=self.name, role=ProviderRole.DECISION, capabilities=merged)

    async def decide(self, request: DecisionRequest) -> DecisionResult:
        res: DecisionResult = await self.primary.decide(request)
        if not res.is_unknown or request.kind not in self.fallback.SUPPORTED_KINDS:
            return res
        fb = await self.fallback.decide(request)
        if fb.is_unknown:
            return res.model_copy(update={"reason": f"{res.reason}; fallback: {fb.reason}"})
        self.fallback_hits += 1
        return fb
