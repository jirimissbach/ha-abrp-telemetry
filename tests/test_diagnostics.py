"""Diagnostics privacy tests."""

from __future__ import annotations

from types import SimpleNamespace

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.abrp_telemetry.const import CONF_API_KEY, CONF_MAPPINGS, CONF_TOKEN, DOMAIN
from custom_components.abrp_telemetry.diagnostics import async_get_config_entry_diagnostics
from custom_components.abrp_telemetry.models import RuntimeData, TransmissionStats


async def test_diagnostics_redact_credentials_and_never_include_gps(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Car",
        data={
            CONF_API_KEY: "secret-key",
            CONF_TOKEN: "secret-token",
            CONF_MAPPINGS: {"latitude": "sensor.lat"},
        },
    )
    manager = SimpleNamespace(
        client=SimpleNamespace(endpoint="https://api.iternio.com/app/tlm"),
        stats=TransmissionStats(),
        mappings={"latitude": "sensor.lat"},
    )
    entry.runtime_data = RuntimeData(manager.client, manager)
    result = await async_get_config_entry_diagnostics(hass, entry)
    dumped = str(result)
    assert "secret-key" not in dumped
    assert "secret-token" not in dumped
    assert "50.0" not in dumped
    assert result["entry"]["data"][CONF_API_KEY] == "**REDACTED**"
