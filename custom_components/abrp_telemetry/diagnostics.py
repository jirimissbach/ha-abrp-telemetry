"""Diagnostics with mandatory credential and location redaction."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import AbrpConfigEntry
from .redaction import redact


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: AbrpConfigEntry) -> dict[str, Any]:
    """Return only privacy-safe diagnostics for one vehicle."""
    manager = entry.runtime_data.manager
    return {
        "entry": redact({"title": entry.title, "data": dict(entry.data), "options": dict(entry.options)}),
        "endpoint": manager.client.endpoint,
        "runtime": manager.stats.as_dict(),
        "mapped_field_count": len(manager.mappings),
    }
