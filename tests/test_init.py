"""Config entry lifecycle integration tests."""

from __future__ import annotations

from unittest.mock import patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.abrp_telemetry.const import (
    CONF_API_KEY,
    CONF_INTERVAL,
    CONF_MAPPINGS,
    CONF_MODE,
    CONF_STALE_AFTER,
    CONF_TOKEN,
    CONF_UNIT_OVERRIDES,
    CONF_VEHICLE_NAME,
    DOMAIN,
)


async def test_entry_loads_and_unloads_cleanly(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Enyaq",
        data={
            CONF_VEHICLE_NAME: "Enyaq",
            CONF_API_KEY: "api-key",
            CONF_TOKEN: "token",
            CONF_MAPPINGS: {"soc": "sensor.soc"},
            CONF_UNIT_OVERRIDES: {},
            CONF_MODE: "event",
            CONF_INTERVAL: 10,
            CONF_STALE_AFTER: 300,
        },
    )
    entry.add_to_hass(hass)
    with patch("custom_components.abrp_telemetry.api.AbrpClient.async_send"):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    manager = entry.runtime_data.manager
    assert manager._stopped is False
    assert hass.states.get("sensor.enyaq_status") is not None
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert manager._stopped is True
