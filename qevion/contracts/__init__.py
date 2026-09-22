"""Versioned, typed contracts shared by every QEVION plane.

Rules (QV-VERS, ADR-0002):
- This package imports only the standard library and pydantic.
- Every contract carries a `schema` literal like ``qevion.<name>.v1``.
- JSON Schemas are generated into ``qevion/contracts/schemas/`` by ``scripts/gen_schemas.py``
  and round-trip tested (QV-ACC-003).
"""

from qevion.contracts.common import (
    Provenance,
    QevionModel,
    Sensitivity,
    new_id,
    utc_now,
)

__all__ = ["Provenance", "QevionModel", "Sensitivity", "new_id", "utc_now"]
