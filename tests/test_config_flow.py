"""Config and options flow tests."""

from __future__ import annotations

import hashlib
from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.abrp_telemetry.const import (
    CONF_API_KEY,
    CONF_INTERVAL,
    CONF_MAPPINGS,
    CONF_MODE,
    CONF_STALE_AFTER,
    CONF_TOKEN,
    CONF_VEHICLE_NAME,
    DEFAULT_INTERVAL,
    DEFAULT_STALE_AFTER,
    DOMAIN,
)

CREDS = {CONF_VEHICLE_NAME: "Enyaq", CONF_API_KEY: "api-key", CONF_TOKEN: "vehicle-token"}
MAPPING = {
    "soc": "sensor.car_soc",
    CONF_MODE: "event",
    CONF_INTERVAL: DEFAULT_INTERVAL,
    CONF_STALE_AFTER: DEFAULT_STALE_AFTER,
}


async def test_config_flow(hass: HomeAssistant):
    hass.states.async_set("sensor.car_soc", "80", {"unit_of_measurement": "%"})
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDS)
    assert result["step_id"] == "mappings"
    with patch("custom_components.abrp_telemetry.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], MAPPING)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Enyaq"
    assert result["data"][CONF_MAPPINGS] == {"soc": "sensor.car_soc"}


async def test_credentials_are_required_without_network_side_effect(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_VEHICLE_NAME: "Car", CONF_API_KEY: "", CONF_TOKEN: ""}
    )
    assert result["errors"] == {"base": "invalid_credentials"}


async def test_config_flow_asks_for_unknown_unit(hass: HomeAssistant):
    hass.states.async_set("sensor.range", "100")
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDS)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_MODE: "event",
            CONF_INTERVAL: DEFAULT_INTERVAL,
            CONF_STALE_AFTER: DEFAULT_STALE_AFTER,
            "estimated_range": "sensor.range",
        },
    )
    assert result["step_id"] == "units"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"estimated_range": "mi"})
    assert result["data"]["unit_overrides"] == {"estimated_range": "mi"}


async def test_location_pair_validation(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDS)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_MODE: "event",
            CONF_INTERVAL: DEFAULT_INTERVAL,
            CONF_STALE_AFTER: DEFAULT_STALE_AFTER,
            "latitude": "sensor.lat",
        },
    )
    assert result["errors"] == {"base": "location_pair_required"}


async def test_multiple_vehicles_and_duplicate_token_isolation(hass: HomeAssistant):
    first = MockConfigEntry(domain=DOMAIN, unique_id="different", data=CREDS)
    first.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**CREDS, CONF_VEHICLE_NAME: "Second", CONF_TOKEN: "another-token"}
    )
    assert result["step_id"] == "mappings"


async def test_duplicate_vehicle_token_is_rejected(hass: HomeAssistant):
    fingerprint = hashlib.sha256(CREDS[CONF_TOKEN].encode()).hexdigest()[:24]
    MockConfigEntry(domain=DOMAIN, unique_id=fingerprint, data=CREDS).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDS)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_flow(hass: HomeAssistant):
    hass.states.async_set("sensor.car_soc", "80", {"unit_of_measurement": "%"})
    entry = MockConfigEntry(
        domain=DOMAIN, title="Enyaq", data={**CREDS, CONF_MAPPINGS: {"soc": "sensor.car_soc"}}
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["step_id"] == "init"
    result = await hass.config_entries.options.async_configure(result["flow_id"], MAPPING)
    assert result["step_id"] == "charging_states"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "charging_ac_values": "ladevorgang",
            "charging_dc_values": "",
            "charging_values": "",
            "plugged_values": "",
            "not_charging_values": "",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["charging_state_map"] == {"ladevorgang": "CHARGING_AC"}
