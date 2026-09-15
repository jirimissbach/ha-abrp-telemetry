"""ABRP Telemetry integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AbrpClient
from .const import CONF_API_KEY, CONF_TOKEN
from .manager import TelemetryManager
from .models import RuntimeData

PLATFORMS = [Platform.SENSOR]
type AbrpConfigEntry = ConfigEntry[RuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: AbrpConfigEntry) -> bool:
    """Set up one independently authenticated ABRP vehicle."""
    config: dict[str, Any] = {**entry.data, **entry.options}
    client = AbrpClient(
        async_get_clientsession(hass),
        config[CONF_API_KEY],
        config[CONF_TOKEN],
    )
    manager = TelemetryManager(hass, entry.entry_id, client, config)
    entry.runtime_data = RuntimeData(client, manager)
    await manager.async_start()
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: AbrpConfigEntry) -> bool:
    """Unload one vehicle without affecting any other entry."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    await entry.runtime_data.manager.async_stop()
    return True


async def _async_update_listener(hass: HomeAssistant, entry: AbrpConfigEntry) -> None:
    """Apply mapping/settings changes without a Home Assistant restart."""
    await hass.config_entries.async_reload(entry.entry_id)
