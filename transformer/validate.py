"""Output validation.

Validates a projected output dict against the requested config schema:
  - required fields are present and non-null
  - declared types match (string, string[], number, object, boolean)

Returns a list of human-readable errors ([] == valid). Validation never raises;
the caller decides whether errors are fatal.
"""
from __future__ import annotations

from typing import Any

_TYPE_CHECKS = {
    "string": lambda v: isinstance(v, str),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "object": lambda v: isinstance(v, dict),
    "string[]": lambda v: isinstance(v, list) and all(isinstance(x, str) for x in v),
    "number[]": lambda v: isinstance(v, list) and all(
        isinstance(x, (int, float)) and not isinstance(x, bool) for x in v),
    "object[]": lambda v: isinstance(v, list) and all(isinstance(x, dict) for x in v),
}


def validate_output(out: dict, config: dict) -> list[str]:
    """Return a list of validation error strings ([] means valid)."""
    errors: list[str] = []
    fields = config.get("fields")
    if not fields:
        return errors  # default schema: nothing custom to enforce

    for spec in fields:
        path = spec["path"]
        present = path in out
        value = out.get(path)

        if spec.get("required") and (not present or value is None):
            errors.append(f"required field '{path}' is missing or null")
            continue

        declared = spec.get("type")
        if declared and present and value is not None:
            check = _TYPE_CHECKS.get(declared)
            if check is None:
                errors.append(f"field '{path}': unknown type '{declared}'")
            elif not check(value):
                errors.append(
                    f"field '{path}': expected {declared}, got {type(value).__name__}"
                )
    return errors


def validate_all(outputs: list[dict], config: dict) -> dict[int, list[str]]:
    """Validate each output; return {index: errors} only for records with errors."""
    report: dict[int, list[str]] = {}
    for i, out in enumerate(outputs):
        errs = validate_output(out, config)
        if errs:
            report[i] = errs
    return report
