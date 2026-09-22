"""Knowledge parsers (§15 QV-KNOW-002/003 step Parse → Normalize). Deterministic, no LLM.

Every parser yields `Row`s: a flat mapping plus a `locator` (line/row/path) so each Fact can cite where it came
from (QV-KNOW-004). Uploads are untrusted (QV-KNOW-009): size caps, no code execution, YAML via safe_load only.
"""

from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass, field
from typing import Any

import yaml

MAX_BYTES = 5 * 1024 * 1024  # QV-KNOW-009 size limit for POC uploads
_INJECTION = re.compile(r"(?i)\b(ignore (all |previous |all previous )?instructions|system prompt|you are now|disregard)\b")


class ParseError(ValueError):
    pass


@dataclass
class Row:
    values: dict[str, Any]
    locator: str
    section: str | None = None  # heading / sheet / top-level key context


@dataclass
class ParsedSource:
    rows: list[Row] = field(default_factory=list)
    kind: str = "table"  # table | document | structured
    warnings: list[str] = field(default_factory=list)
    injection_flags: list[str] = field(default_factory=list)  # locators of suspicious text (logged, never executed)


def _norm_key(k: Any) -> str:
    s = re.sub(r"[^\w]+", "_", str(k).strip().lower()).strip("_")
    return s or "value"


def _norm_val(v: Any) -> Any:
    if isinstance(v, str):
        s = v.strip()
        if s == "":
            return None
        if re.fullmatch(r"-?\d+", s):
            return int(s)
        if re.fullmatch(r"-?\d+\.\d+", s):
            return float(s)
        if s.lower() in ("true", "yes", "نعم", "ايوه", "أيوه"):
            return True
        if s.lower() in ("false", "no", "لا", "لأ"):
            return False
        return s
    return v


def _check_size(data: bytes) -> None:
    if len(data) > MAX_BYTES:
        raise ParseError(f"upload exceeds {MAX_BYTES} bytes")


def _flag(parsed: ParsedSource, text: str, locator: str) -> None:
    if _INJECTION.search(text):
        parsed.injection_flags.append(locator)


def parse_csv(data: bytes, *, delimiter: str | None = None) -> ParsedSource:
    _check_size(data)
    text = data.decode("utf-8-sig", errors="replace")
    sniff = delimiter or (csv.Sniffer().sniff(text[:2048], delimiters=",;\t|").delimiter if text.strip() else ",")
    reader = csv.DictReader(io.StringIO(text), delimiter=sniff)
    out = ParsedSource(kind="table")
    for i, raw in enumerate(reader, start=2):  # header is line 1
        vals = {_norm_key(k): _norm_val(v) for k, v in raw.items() if k is not None}
        if not any(v is not None for v in vals.values()):
            continue
        loc = f"row:{i}"
        out.rows.append(Row(vals, loc))
        _flag(out, " ".join(str(v) for v in vals.values() if isinstance(v, str)), loc)
    if not out.rows:
        out.warnings.append("no data rows")
    return out


def _walk(obj: Any, path: str, out: ParsedSource, section: str | None) -> None:
    if isinstance(obj, list):
        if obj and all(isinstance(x, dict) for x in obj):
            for i, item in enumerate(obj):
                loc = f"{path}[{i}]"
                vals = {_norm_key(k): _norm_val(v) for k, v in item.items() if not isinstance(v, dict | list)}
                if vals:
                    out.rows.append(Row(vals, loc, section))
                    _flag(out, " ".join(str(v) for v in vals.values() if isinstance(v, str)), loc)
                for k, v in item.items():
                    if isinstance(v, dict | list):
                        _walk(v, f"{loc}.{k}", out, section or _norm_key(k))
        else:
            vals = {"value": [_norm_val(x) for x in obj]}
            out.rows.append(Row(vals, path, section))
    elif isinstance(obj, dict):
        scalars = {_norm_key(k): _norm_val(v) for k, v in obj.items() if not isinstance(v, dict | list)}
        if scalars:
            out.rows.append(Row(scalars, path, section))
            _flag(out, " ".join(str(v) for v in scalars.values() if isinstance(v, str)), path)
        for k, v in obj.items():
            if isinstance(v, dict | list):
                _walk(v, f"{path}.{k}" if path != "$" else f"$.{k}", out, section or _norm_key(k))
    else:
        out.rows.append(Row({"value": _norm_val(obj)}, path, section))


def parse_json(data: bytes) -> ParsedSource:
    _check_size(data)
    try:
        obj = json.loads(data.decode("utf-8-sig"))
    except json.JSONDecodeError as e:
        raise ParseError(f"invalid JSON: {e.msg}") from e
    out = ParsedSource(kind="structured")
    _walk(obj, "$", out, None)
    return out


def parse_yaml(data: bytes) -> ParsedSource:
    _check_size(data)
    try:
        obj = yaml.safe_load(data.decode("utf-8-sig"))
    except yaml.YAMLError as e:
        raise ParseError(f"invalid YAML: {e}") from e
    out = ParsedSource(kind="structured")
    _walk(obj, "$", out, None)
    return out


_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*)$")
_KV = re.compile(r"^\s*[-*]?\s*([^:：]{1,80})\s*[:：]\s*(.+?)\s*$")
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{2,}")


def parse_text(data: bytes) -> ParsedSource:
    """TXT/MD/DOCX-text: headings become sections; `key: value` lines and pipe tables become rows; other
    lines become `statement` rows so nothing is silently dropped (they extract as LIMITATION/PROCEDURE candidates)."""
    _check_size(data)
    text = data.decode("utf-8-sig", errors="replace")
    out = ParsedSource(kind="document")
    section: str | None = None
    table_header: list[str] | None = None
    for n, line in enumerate(text.splitlines(), start=1):
        loc = f"line:{n}"
        if not line.strip():
            table_header = None
            continue
        _flag(out, line, loc)
        if m := _HEADING.match(line):
            section = m.group(1).strip()
            table_header = None
            continue
        if line.strip().startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if _TABLE_SEP.match(line):
                continue
            if table_header is None:
                table_header = [_norm_key(c) for c in cells]
                continue
            vals = {h: _norm_val(c) for h, c in zip(table_header, cells, strict=False)}
            out.rows.append(Row(vals, loc, section))
            continue
        table_header = None
        if m := _KV.match(line):
            out.rows.append(Row({_norm_key(m.group(1)): _norm_val(m.group(2))}, loc, section))
            continue
        out.rows.append(Row({"statement": line.strip()}, loc, section))
    return out


PARSERS = {
    "text/csv": parse_csv,
    "application/json": parse_json,
    "application/x-yaml": parse_yaml,
    "application/yaml": parse_yaml,
    "text/yaml": parse_yaml,
    "text/plain": parse_text,
    "text/markdown": parse_text,
}
_EXT = {
    ".csv": "text/csv",
    ".json": "application/json",
    ".yaml": "application/yaml",
    ".yml": "application/yaml",
    ".txt": "text/plain",
    ".md": "text/markdown",
}


def mime_for(name: str) -> str | None:
    for ext, mime in _EXT.items():
        if name.lower().endswith(ext):
            return mime
    return None


def parse(data: bytes, *, mime_type: str | None = None, name: str = "") -> ParsedSource:
    mime = mime_type or mime_for(name)
    if mime is None or mime not in PARSERS:
        raise ParseError(f"unsupported upload type: {mime or name!r} (supported: {sorted(PARSERS)})")
    return PARSERS[mime](data)


__all__ = ["MAX_BYTES", "PARSERS", "ParseError", "ParsedSource", "Row", "mime_for", "parse"]
