"""Central redaction helpers."""

from __future__ import annotations

from typing import Any

from .const import LOCATION_KEYS, SECRET_KEYS

REDACTED = "**REDACTED**"
LOCATION_REDACTED = "**LOCATION REDACTED**"


def redact(value: Any) -> Any:
    """Recursively redact credentials and precise location without mutating input."""
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if key in SECRET_KEYS or lowered in {item.lower() for item in SECRET_KEYS}:
                result[key] = REDACTED
            elif lowered in LOCATION_KEYS:
                result[key] = LOCATION_REDACTED
            else:
                result[key] = redact(item)
        return result
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    return value
