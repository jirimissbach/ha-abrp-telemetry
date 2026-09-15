"""Diagnostic sensors for one ABRP vehicle."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import AbrpConfigEntry
from .const import CONF_VEHICLE_NAME, DOMAIN


@dataclass(frozen=True, kw_only=True)
class AbrpSensorDescription(SensorEntityDescription):
    """Describe a runtime diagnostic."""

    value_fn: Callable[[Any], Any]


DESCRIPTIONS = (
    AbrpSensorDescription(key="status", translation_key="status", value_fn=lambda s: s.status),
    AbrpSensorDescription(
        key="last_success",
        translation_key="last_success",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda s: s.last_success,
    ),
    AbrpSensorDescription(
        key="last_attempt",
        translation_key="last_attempt",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_registry_enabled_default=False,
        value_fn=lambda s: s.last_attempt,
    ),
    AbrpSensorDescription(
        key="newest_source_age",
        translation_key="newest_source_age",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        entity_registry_enabled_default=False,
        value_fn=lambda s: round(s.newest_source_age, 1) if s.newest_source_age is not None else None,
    ),
    AbrpSensorDescription(
        key="successful_transmissions",
        translation_key="successful_transmissions",
        entity_registry_enabled_default=False,
        value_fn=lambda s: s.successful_transmissions,
    ),
    AbrpSensorDescription(
        key="failed_transmissions",
        translation_key="failed_transmissions",
        entity_registry_enabled_default=False,
        value_fn=lambda s: s.failed_transmissions,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: AbrpConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Add diagnostic sensors."""
    async_add_entities(AbrpDiagnosticSensor(entry, description) for description in DESCRIPTIONS)


class AbrpDiagnosticSensor(SensorEntity):
    """A diagnostic entity backed by runtime-only statistics."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: AbrpConfigEntry, description: AbrpSensorDescription) -> None:
        self.entity_description = description
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data[CONF_VEHICLE_NAME],
            manufacturer="Iternio",
            model="ABRP telemetry bridge",
        )

    @property
    def native_value(self) -> str | int | float | datetime | None:
        return self.entity_description.value_fn(self._entry.runtime_data.manager.stats)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._entry.runtime_data.manager.async_add_listener(self._handle_update))

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()
