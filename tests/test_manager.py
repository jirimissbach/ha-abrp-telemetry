"""Per-vehicle event, periodic, stale, backoff, and cleanup tests."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.abrp_telemetry.api import (
    AbrpAuthenticationError,
    AbrpRateLimitError,
    AbrpServerError,
)
from custom_components.abrp_telemetry.const import (
    CONF_INTERVAL,
    CONF_MAPPINGS,
    CONF_MODE,
    CONF_STALE_AFTER,
    MODE_EVENT,
    MODE_PERIODIC,
    STATUS_AUTH_ERROR,
    STATUS_CONNECTED,
    STATUS_RATE_LIMITED,
    STATUS_STALE,
)
from custom_components.abrp_telemetry.manager import TelemetryManager


def config(entity="sensor.soc", mode=MODE_EVENT):
    return {
        CONF_MAPPINGS: {"soc": entity},
        CONF_MODE: mode,
        CONF_INTERVAL: 10,
        CONF_STALE_AFTER: 300,
    }


async def make_fresh(hass, manager, entity="sensor.soc", value="80"):
    hass.states.async_set(entity, value, {"unit_of_measurement": "%"})
    await hass.async_block_till_done()
    manager._observed[entity] = datetime.now(UTC)


async def test_event_driven_send_and_debounce_coalescing(hass: HomeAssistant):
    client = AsyncMock()
    manager = TelemetryManager(hass, "entry-a", client, config())
    await manager.async_start()
    hass.states.async_set("sensor.soc", "79", {"unit_of_measurement": "%"})
    await hass.async_block_till_done()
    first = manager._debounce_handle
    hass.states.async_set("sensor.soc", "78", {"unit_of_measurement": "%"})
    await hass.async_block_till_done()
    assert manager._debounce_handle is not None
    assert manager._debounce_handle is not first
    assert first.cancelled()
    assert client.async_send.await_count == 0
    manager._observed["sensor.soc"] = datetime.now(UTC)
    assert await manager.async_send_snapshot("test")
    assert client.async_send.await_count == 1
    assert client.async_send.await_args.args[0]["soc"]["frac"] == pytest.approx(0.78)
    assert manager.stats.status == STATUS_CONNECTED
    await manager.async_stop()


async def test_periodic_registration_and_send(hass: HomeAssistant):
    client = AsyncMock()
    manager = TelemetryManager(hass, "periodic", client, config(mode=MODE_PERIODIC))
    callbacks = []

    def track(_hass, callback, _interval):
        callbacks.append(callback)
        return lambda: None

    with patch("custom_components.abrp_telemetry.manager.async_track_time_interval", side_effect=track):
        await manager.async_start()
    await make_fresh(hass, manager)
    await callbacks[0](datetime.now(UTC))
    client.async_send.assert_awaited_once()
    await manager.async_stop()


async def test_stale_source_suppresses_periodic_upload(hass: HomeAssistant):
    client = AsyncMock()
    manager = TelemetryManager(hass, "stale", client, config())
    hass.states.async_set("sensor.soc", "80", {"unit_of_measurement": "%"})
    assert not await manager.async_send_snapshot("periodic")
    assert manager.stats.status == STATUS_STALE
    client.async_send.assert_not_awaited()


async def test_rate_limit_honors_retry_after_and_backoff(hass: HomeAssistant):
    client = AsyncMock()
    client.async_send.side_effect = AbrpRateLimitError(42)
    manager = TelemetryManager(hass, "rate", client, config())
    await make_fresh(hass, manager)
    assert not await manager.async_send_snapshot("test")
    assert manager.stats.status == STATUS_RATE_LIMITED
    assert manager._next_allowed > datetime.now(UTC)
    assert not await manager.async_send_snapshot("test")
    assert client.async_send.await_count == 1


async def test_server_error_uses_bounded_exponential_backoff(hass: HomeAssistant):
    client = AsyncMock()
    client.async_send.side_effect = AbrpServerError("down")
    manager = TelemetryManager(hass, "server", client, config())
    await make_fresh(hass, manager)
    await manager.async_send_snapshot("test")
    assert manager._backoff_seconds() == 5
    manager._consecutive_failures = 20
    assert manager._backoff_seconds() == 300


async def test_authentication_failure_halts_repeated_requests(hass: HomeAssistant):
    client = AsyncMock()
    client.async_send.side_effect = AbrpAuthenticationError("bad")
    manager = TelemetryManager(hass, "auth", client, config())
    await make_fresh(hass, manager)
    await manager.async_send_snapshot("test")
    await manager.async_send_snapshot("test")
    assert manager.stats.status == STATUS_AUTH_ERROR
    assert client.async_send.await_count == 1


async def test_config_entry_cleanup_cancels_all_resources(hass: HomeAssistant):
    client = AsyncMock()
    manager = TelemetryManager(hass, "cleanup", client, config())
    await manager.async_start()
    hass.states.async_set("sensor.soc", "80", {"unit_of_measurement": "%"})
    await hass.async_block_till_done()
    handle = manager._debounce_handle
    await manager.async_stop()
    assert manager._stopped
    assert handle.cancelled()
    assert manager._unsubscribers == []


async def test_unload_cancels_an_in_flight_upload(hass: HomeAssistant):
    started = asyncio.Event()

    async def hang(_point):
        started.set()
        await asyncio.Event().wait()

    client = AsyncMock()
    client.async_send.side_effect = hang
    manager = TelemetryManager(hass, "in-flight", client, config())
    await make_fresh(hass, manager)
    task = hass.async_create_task(manager.async_send_snapshot("test"))
    await started.wait()
    await manager.async_stop()
    assert task.cancelled()
    assert manager._active_send_tasks == set()


async def test_multiple_vehicles_are_isolated(hass: HomeAssistant):
    first_client = AsyncMock()
    first_client.async_send.side_effect = AbrpServerError("down")
    second_client = AsyncMock()
    first = TelemetryManager(hass, "first", first_client, config("sensor.first"))
    second = TelemetryManager(hass, "second", second_client, config("sensor.second"))
    await make_fresh(hass, first, "sensor.first", "20")
    await make_fresh(hass, second, "sensor.second", "90")
    assert not await first.async_send_snapshot("test")
    assert await second.async_send_snapshot("test")
    assert first.stats.failed_transmissions == 1
    assert second.stats.successful_transmissions == 1
