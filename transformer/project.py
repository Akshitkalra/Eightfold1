"""Projection layer: reshape a CanonicalRecord into the config-requested output.

This is the ONLY place runtime config touches the data. The engine upstream is
unchanged regardless of config. Supports:
  - select a subset of fields
  - rename / remap via a `from` path (e.g. "emails[0]", "skills[].name")
  - per-field normalization (E164 | canonical | lower | upper)
  - include/exclude provenance and confidence
  - on_missing policy: null | omit | error

A tiny path resolver understands dotted paths, "[i]" indexing, and "[].field"
list-projection.
"""
from __future__ import annotations

import re
from typing import Any

from .canonical import CanonicalRecord
from .normalize.phones import normalize_phone
from .normalize.skills import canonical_skill


class ProjectionError(ValueError):
    """Raised when on_missing == 'error' and a required field is absent."""


_MISSING = object()


def resolve_path(data: Any, path: str) -> Any:
    """Resolve a path like 'emails[0]', 'location.country', 'skills[].name'.

    Returns _MISSING if any step can't be resolved (vs None, which is a real value).
    """
    cur = data
    for token in _tokenize(path):
        if token == "[]":
            if not isinstance(cur, list):
                return _MISSING
            # list projection handled by the next token (a field name)
            cur = ("__LIST__", cur)
            continue
        if isinstance(cur, tuple) and cur and cur[0] == "__LIST__":
            lst = cur[1]
            out = []
            for item in lst:
                v = _get(item, token)
                if v is not _MISSING and v is not None:
                    out.append(v)
            cur = out
            continue
        cur = _get(cur, token)
        if cur is _MISSING:
            return _MISSING
    if isinstance(cur, tuple) and cur and cur[0] == "__LIST__":
        return cur[1]
    return cur


def _tokenize(path: str) -> list[str]:
    tokens: list[str] = []
    for part in path.split("."):
        # split "skills[].name" -> "skills", "[]" ; "emails[0]" -> "emails", "[0]"
        m = re.match(r"^([^\[]+)((?:\[[^\]]*\])*)$", part)
        if not m:
            tokens.append(part)
            continue
        name, brackets = m.group(1), m.group(2)
        if name:
            tokens.append(name)
        for b in re.findall(r"\[([^\]]*)\]", brackets):
            tokens.append("[]" if b == "" else f"[{b}]")
    return tokens


def _get(obj: Any, token: str) -> Any:
    if token.startswith("[") and token.endswith("]"):
        idx_str = token[1:-1]
        if not isinstance(obj, list):
            return _MISSING
        try:
            idx = int(idx_str)
        except ValueError:
            return _MISSING
        return obj[idx] if -len(obj) <= idx < len(obj) else _MISSING
    if isinstance(obj, dict):
        return obj.get(token, _MISSING)
    return _MISSING


def _apply_normalize(value: Any, kind: str) -> Any:
    if value is None:
        return None
    if kind == "E164":
        if isinstance(value, list):
            return [normalize_phone(v) for v in value]
        return normalize_phone(value)
    if kind == "canonical":
        if isinstance(value, list):
            return [canonical_skill(v) for v in value]
        return canonical_skill(value)
    if kind == "lower":
        return value.lower() if isinstance(value, str) else value
    if kind == "upper":
        return value.upper() if isinstance(value, str) else value
    return value


def project(record: CanonicalRecord, config: dict) -> dict:
    """Apply a projection config to one canonical record -> output dict."""
    base = record.to_dict()
    on_missing = config.get("on_missing", "null")
    fields = config.get("fields")

    # No field list -> emit the default full schema (optionally trimming meta).
    if not fields:
        out = base
        if not config.get("include_provenance", True):
            out.pop("provenance", None)
        if not config.get("include_confidence", True):
            out.pop("overall_confidence", None)
        return out

    out: dict[str, Any] = {}
    for spec in fields:
        out_path = spec["path"]
        from_path = spec.get("from", out_path)
        value = resolve_path(base, from_path)

        if value is _MISSING:
            if spec.get("required") and on_missing == "error":
                raise ProjectionError(f"required field missing: {out_path} (from {from_path})")
            if on_missing == "omit":
                continue
            value = None  # null policy (default)

        if value is not None and "normalize" in spec:
            value = _apply_normalize(value, spec["normalize"])

        out[out_path] = value

    if config.get("include_confidence"):
        out["overall_confidence"] = record.overall_confidence
    if config.get("include_provenance"):
        out["provenance"] = [p.__dict__ if hasattr(p, "__dict__") else p for p in record.provenance]
    return out


def project_all(records: list[CanonicalRecord], config: dict) -> list[dict]:
    return [project(r, config) for r in records]
