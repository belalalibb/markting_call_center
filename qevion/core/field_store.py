"""FieldStore (§20 QV-FLD): every value carries provenance; corrections are kept; readiness for EXECUTING is
computed from the Blueprint's `provenance_required`, never from the model's say-so.

Core rule: imports `qevion.contracts` + stdlib only. Knows no field names.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from qevion.contracts.activity import FieldSpec
from qevion.contracts.common import Provenance
from qevion.contracts.outcome import FieldValue

# Strength order: higher index = more trustworthy. UNKNOWN/UNVERIFIED never satisfy a requirement.
_STRENGTH: dict[Provenance, int] = {
    Provenance.UNKNOWN: 0,
    Provenance.UNVERIFIED: 1,
    Provenance.USER_STATED: 2,
    Provenance.SYSTEM_DERIVED: 3,
    Provenance.KNOWLEDGE_APPROVED: 4,
    Provenance.TOOL_VERIFIED: 5,
}


def satisfies(actual: Provenance, required: Provenance) -> bool:
    if actual in (Provenance.UNKNOWN, Provenance.UNVERIFIED):
        return False
    return _STRENGTH[actual] >= _STRENGTH[required]


@dataclass
class FieldStore:
    specs: dict[str, FieldSpec]
    required_names: list[str]
    _values: dict[str, FieldValue] = field(default_factory=dict)
    history: list[FieldValue] = field(default_factory=list)  # append-only, incl. corrections

    @classmethod
    def from_specs(cls, required: list[FieldSpec], optional: list[FieldSpec]) -> FieldStore:
        specs = {s.name: s for s in [*required, *optional]}
        return cls(specs=specs, required_names=[s.name for s in required])

    # ---- writes ---------------------------------------------------------------------------
    def record(
        self,
        name: str,
        value: Any,
        provenance: Provenance,
        *,
        turn_id: str | None = None,
        tool_call_id: str | None = None,
        ts_ms: int | None = None,
        confidence: float = 1.0,
    ) -> FieldValue:
        """Record or correct. A weaker provenance never overwrites a stronger one for the same value;
        a *different* value is always a correction (user changed their mind) and is kept with `corrected_from`."""
        if name not in self.specs:
            raise KeyError(f"unknown field: {name}")
        prev = self._values.get(name)
        corrected_from = None
        if prev is not None:
            if prev.value == value and _STRENGTH[provenance] < _STRENGTH[prev.provenance]:
                return prev  # nothing new
            if prev.value != value:
                corrected_from = prev.value
        fv = FieldValue(
            name=name,
            value=value,
            provenance=provenance,
            confidence=confidence,
            turn_id=turn_id,
            tool_call_id=tool_call_id,
            corrected_from=corrected_from,
            recorded_at_ms=ts_ms,
        )
        self._values[name] = fv
        self.history.append(fv)
        return fv

    def verify(self, name: str, *, tool_call_id: str, ts_ms: int | None = None, value: Any = ...) -> FieldValue:
        """Promote to TOOL_VERIFIED (optionally normalising the value from the tool)."""
        cur = self._values.get(name)
        if cur is None and value is ...:
            raise KeyError(f"cannot verify unrecorded field: {name}")
        v = cur.value if value is ... else value
        return self.record(name, v, Provenance.TOOL_VERIFIED, tool_call_id=tool_call_id, ts_ms=ts_ms)

    def reject(self, name: str, *, ts_ms: int | None = None) -> None:
        """Mark a value as not usable (e.g. validation failed) without deleting history."""
        cur = self._values.get(name)
        if cur is not None:
            self._values[name] = cur.model_copy(update={"provenance": Provenance.UNVERIFIED, "recorded_at_ms": ts_ms})
            self.history.append(self._values[name])

    # ---- reads ----------------------------------------------------------------------------
    def get(self, name: str) -> FieldValue | None:
        return self._values.get(name)

    def value(self, name: str, default: Any = None) -> Any:
        fv = self._values.get(name)
        return default if fv is None else fv.value

    def values(self) -> dict[str, Any]:
        return {k: v.value for k, v in self._values.items()}

    def all(self) -> list[FieldValue]:
        return list(self._values.values())

    def recorded_names(self) -> set[str]:
        return {k for k, v in self._values.items() if v.provenance not in (Provenance.UNKNOWN, Provenance.UNVERIFIED)}

    def missing_required(self) -> list[str]:
        return [n for n in self.required_names if n not in self.recorded_names()]

    def unsatisfied_required(self) -> list[tuple[str, Provenance, Provenance | None]]:
        """(name, required, actual|None) for required fields not meeting `provenance_required`."""
        out = []
        for n in self.required_names:
            req = self.specs[n].provenance_required
            fv = self._values.get(n)
            if fv is None or not satisfies(fv.provenance, req):
                out.append((n, req, None if fv is None else fv.provenance))
        return out

    def ready_for_execution(self) -> bool:
        """QV-ACC-007: UNVERIFIED/UNKNOWN or under-provenanced required fields never reach EXECUTING."""
        return not self.unsatisfied_required()

    def next_required(self) -> str | None:
        m = self.missing_required()
        return m[0] if m else None

    # ---- projections for Outcome (§26) -------------------------------------------------
    def verified_names(self) -> list[str]:
        return [k for k, v in self._values.items() if v.provenance is Provenance.TOOL_VERIFIED]

    def inferred_names(self) -> list[str]:
        return [k for k, v in self._values.items() if v.provenance is Provenance.SYSTEM_DERIVED]

    def rejected_names(self) -> list[str]:
        return [k for k, v in self._values.items() if v.provenance in (Provenance.UNVERIFIED, Provenance.UNKNOWN)]
