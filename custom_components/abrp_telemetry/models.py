"""Data models for ABRP Telemetry."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class MappingConfig:
    """An entity mapping and its optional source-unit override."""

    entity_id: str
    source_unit: str | None = None


@dataclass(slots=True)
class TransmissionStats:
    """Runtime-only transmission diagnostics for one vehicle."""

    status: str = "waiting_for_source"
    last_attempt: datetime | None = None
    last_success: datetime | None = None
    last_error_category: str | None = None
    successful_transmissions: int = 0
    failed_transmissions: int = 0
    newest_source_age: float | None = None
    oldest_source_age: float | None = None
    invalid_fields: dict[str, str] = field(default_factory=dict)
    stale_fields: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable, privacy-safe representation."""
        return {
            "status": self.status,
            "last_attempt": self.last_attempt.isoformat() if self.last_attempt else None,
            "last_success": self.last_success.isoformat() if self.last_success else None,
            "last_error_category": self.last_error_category,
            "successful_transmissions": self.successful_transmissions,
            "failed_transmissions": self.failed_transmissions,
            "newest_source_age": self.newest_source_age,
            "oldest_source_age": self.oldest_source_age,
            "invalid_fields": dict(self.invalid_fields),
            "stale_fields": list(self.stale_fields),
        }


@dataclass(slots=True)
class RuntimeData:
    """Runtime data attached to one Home Assistant config entry."""

    client: Any
    manager: Any
