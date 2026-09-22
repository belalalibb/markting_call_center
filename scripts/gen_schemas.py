#!/usr/bin/env python3
"""Generate JSON Schema (2020-12) for every registered contract into qevion/contracts/schemas/.

Usage: python scripts/gen_schemas.py [--check]
  --check  exit 1 if any generated schema differs from the committed one (CI drift gate, QV-EVT-005).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pydantic.json_schema import GenerateJsonSchema

from qevion.contracts.registry import CONTRACTS, schema_filename

OUT = Path(__file__).resolve().parents[1] / "qevion" / "contracts" / "schemas"


class _Gen(GenerateJsonSchema):
    schema_dialect = "https://json-schema.org/draft/2020-12/schema"


def render(schema_id: str) -> str:
    model = CONTRACTS[schema_id]
    schema = model.model_json_schema(by_alias=True, schema_generator=_Gen, mode="validation")
    schema["$id"] = f"https://qevion.dev/schemas/{schema_filename(schema_id)}"
    schema["$schema"] = _Gen.schema_dialect
    schema["x-qevion-schema-id"] = schema_id
    return json.dumps(schema, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main(check: bool) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    drift: list[str] = []
    for sid in sorted(CONTRACTS):
        path = OUT / schema_filename(sid)
        text = render(sid)
        if check:
            if not path.exists() or path.read_text() != text:
                drift.append(path.name)
        else:
            path.write_text(text)
    index = {sid: schema_filename(sid) for sid in sorted(CONTRACTS)}
    idx_text = json.dumps(index, indent=2) + "\n"
    idx_path = OUT / "index.json"
    if check:
        if not idx_path.exists() or idx_path.read_text() != idx_text:
            drift.append("index.json")
        if drift:
            print("SCHEMA DRIFT:", ", ".join(drift))
            return 1
        print(f"schemas up to date ({len(CONTRACTS)})")
        return 0
    idx_path.write_text(idx_text)
    print(f"wrote {len(CONTRACTS)} schemas + index.json -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main("--check" in sys.argv))
