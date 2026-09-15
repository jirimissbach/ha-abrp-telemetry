"""Per-vehicle telemetry scheduling, freshness, and failure isolation."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import (
    async_track_entity_registry_updated_event,
    async_track_state_change_event,
    async_track_time_interval,
)

from .api import (
    AbrpAuthenticationError,
    AbrpClient,
    AbrpError,
    AbrpRateLimitError,
)
from .const import (
    CONF_INTERVAL,
    CONF_MAPPINGS,
    CONF_MODE,
    CONF_STALE_AFTER,
    CONF_UNIT_OVERRIDES,
    DEBOUNCE_SECONDS,
    DEFAULT_INTERVAL,
    DEFAULT_STALE_AFTER,
    DOMAIN,
    MODE_EVENT,
    MODE_HYBRID,
    MODE_PERIODIC,
    STATUS_API_ERROR,
    STATUS_AUTH_ERROR,
    STATUS_CONNECTED,
    STATUS_RATE_LIMITED,
    STATUS_STALE,
    STATUS_TRANSMITTING,
    STATUS_WAITING,
)
from .models import TransmissionStats
from .telemetry import build_point

_LOGGER = logging.getLogger(__name__)


class TelemetryManager:
    """Own all listeners, timers, backoff, and diagnostics for one config entry."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        client: AbrpClient,
        config: dict[str, Any],
    ) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.client = client
        self.config = config
        self.stats = TransmissionStats()
        self._observed: dict[str, datetime] = {}
        self._unsubscribers: list[Callable[[], None]] = []
        self._debounce_handle: asyncio.TimerHandle | None = None
        self._send_lock = asyncio.Lock()
        self._active_send_tasks: set[asyncio.Task[Any]] = set()
        self._stopped = False
        self._auth_halted = False
        self._consecutive_failures = 0
        self._next_allowed = datetime.min.replace(tzinfo=UTC)
        self._listeners: set[Callable[[], None]] = set()

    @property
    def mappings(self) -> dict[str, str]:
        return dict(self.config.get(CONF_MAPPINGS, {}))

    async def async_start(self) -> None:
        """Start without treating pre-existing/restored states as fresh."""
        entity_ids = set(self.mappings.values())
        if entity_ids:
            self._unsubscribers.append(
                async_track_state_change_event(self.hass, entity_ids, self._handle_state_event)
            )
            self._unsubscribers.append(
                async_track_entity_registry_updated_event(
                    self.hass, entity_ids, self._handle_entity_registry_event
                )
            )
        mode = self.config.get(CONF_MODE, MODE_EVENT)
        if mode in (MODE_PERIODIC, MODE_HYBRID):
            interval = int(self.config.get(CONF_INTERVAL, DEFAULT_INTERVAL))
            self._unsubscribers.append(
                async_track_time_interval(self.hass, self._handle_periodic, timedelta(seconds=interval))
            )

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.add(listener)

        @callback
        def remove() -> None:
            self._listeners.discard(listener)

        return remove

    @callback
    def _notify(self) -> None:
        for listener in tuple(self._listeners):
            listener()

    @callback
    def _handle_state_event(self, event: Event) -> None:
        if self._stopped:
            return
        entity_id = event.data["entity_id"]
        new_state: State | None = event.data.get("new_state")
        if new_state is None:
            return
        # A force-update with the same value can still represent a newly received
        # vehicle measurement, so the HA state event itself is the freshness signal.
        self._observed[entity_id] = new_state.last_reported
        if self.config.get(CONF_MODE, MODE_EVENT) in (MODE_EVENT, MODE_HYBRID):
            self._schedule_debounced_send()

    @callback
    def _handle_entity_registry_event(self, event: Event) -> None:
        """Follow entity-id renames and surface removals without losing mappings."""
        old_entity_id = event.data.get("old_entity_id", event.data["entity_id"])
        fields = [field for field, entity_id in self.mappings.items() if entity_id == old_entity_id]
        if not fields:
            return
        if event.data["action"] == "update" and "old_entity_id" in event.data:
            new_entity_id = event.data["entity_id"]
            mappings = self.mappings
            for field in fields:
                mappings[field] = new_entity_id
            entry = self.hass.config_entries.async_get_entry(self.entry_id)
            if entry is not None:
                if CONF_MAPPINGS in entry.options:
                    self.hass.config_entries.async_update_entry(
                        entry, options={**entry.options, CONF_MAPPINGS: mappings}
                    )
                else:
                    self.hass.config_entries.async_update_entry(
                        entry, data={**entry.data, CONF_MAPPINGS: mappings}
                    )
            return
        issue_id = f"missing_entity_{self.entry_id}"
        if event.data["action"] == "remove":
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="mapped_entity_removed",
            )
        elif event.data["action"] == "create":
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)

    @callback
    def _schedule_debounced_send(self) -> None:
        if self._debounce_handle:
            self._debounce_handle.cancel()
        self._debounce_handle = self.hass.loop.call_later(
            DEBOUNCE_SECONDS,
            lambda: self.hass.async_create_task(self.async_send_snapshot("entity_change")),
        )

    async def _handle_periodic(self, _now: datetime) -> None:
        await self.async_send_snapshot("periodic")

    async def async_send_snapshot(self, reason: str) -> bool:
        """Send a complete current snapshot if fresh data and backoff permit it."""
        task = asyncio.current_task()
        if task is not None:
            self._active_send_tasks.add(task)
        try:
            return await self._async_send_snapshot(reason)
        finally:
            if task is not None:
                self._active_send_tasks.discard(task)

    async def _async_send_snapshot(self, reason: str) -> bool:
        """Implement one tracked transmission attempt."""
        if self._stopped or self._auth_halted:
            return False
        now = datetime.now(UTC)
        if now < self._next_allowed:
            _LOGGER.debug("ABRP upload skipped during per-vehicle backoff (%s)", reason)
            return False
        async with self._send_lock:
            now = datetime.now(UTC)
            if now < self._next_allowed or self._auth_halted or self._stopped:
                return False
            states = {entity_id: self.hass.states.get(entity_id) for entity_id in self.mappings.values()}
            result = build_point(
                states,
                self.mappings,
                self.config.get(CONF_UNIT_OVERRIDES, {}),
                self._observed,
                now=now,
                stale_after=float(self.config.get(CONF_STALE_AFTER, DEFAULT_STALE_AFTER)),
                charging_state_map=self.config.get("charging_state_map", {}),
            )
            self.stats.invalid_fields = result.invalid_fields
            self.stats.stale_fields = result.stale_fields
            unit_issue_id = f"unsupported_unit_{self.entry_id}"
            if any("unsupported" in reason and "unit" in reason for reason in result.invalid_fields.values()):
                ir.async_create_issue(
                    self.hass,
                    DOMAIN,
                    unit_issue_id,
                    is_fixable=False,
                    severity=ir.IssueSeverity.WARNING,
                    translation_key="unsupported_source_unit",
                )
            else:
                ir.async_delete_issue(self.hass, DOMAIN, unit_issue_id)
            if result.source_ages:
                self.stats.newest_source_age = min(result.source_ages)
                self.stats.oldest_source_age = max(result.source_ages)
            else:
                self.stats.newest_source_age = self.stats.oldest_source_age = None
            if result.point is None:
                self.stats.status = STATUS_STALE if result.stale_fields else STATUS_WAITING
                self._notify()
                return False

            self.stats.status = STATUS_TRANSMITTING
            self.stats.last_attempt = now
            self._notify()
            try:
                await self.client.async_send(result.point)
            except AbrpAuthenticationError:
                self._record_failure(STATUS_AUTH_ERROR, "authentication_error")
                self._auth_halted = True
                ir.async_create_issue(
                    self.hass,
                    DOMAIN,
                    f"authentication_{self.entry_id}",
                    is_fixable=False,
                    is_persistent=True,
                    severity=ir.IssueSeverity.ERROR,
                    translation_key="authentication_error",
                )
                _LOGGER.error("ABRP rejected credentials for config entry %s", self.entry_id)
                if entry := self.hass.config_entries.async_get_entry(self.entry_id):
                    entry.async_start_reauth(self.hass)
            except AbrpRateLimitError as err:
                self._record_failure(STATUS_RATE_LIMITED, err.category)
                delay = err.retry_after if err.retry_after is not None else self._backoff_seconds()
                self._next_allowed = now + timedelta(seconds=min(max(delay, 5), 3600))
                _LOGGER.warning("ABRP rate limited a vehicle; uploads will resume after backoff")
            except AbrpError as err:
                self._record_failure(STATUS_API_ERROR, err.category)
                self._next_allowed = now + timedelta(seconds=self._backoff_seconds())
                _LOGGER.debug("ABRP upload failed (%s)", err.category)
            else:
                self._consecutive_failures = 0
                self._next_allowed = datetime.min.replace(tzinfo=UTC)
                self.stats.status = STATUS_CONNECTED
                self.stats.last_success = datetime.now(UTC)
                self.stats.last_error_category = None
                self.stats.successful_transmissions += 1
                ir.async_delete_issue(self.hass, DOMAIN, f"authentication_{self.entry_id}")
                self._notify()
                return True
            self._notify()
            return False

    def _record_failure(self, status: str, category: str) -> None:
        self._consecutive_failures += 1
        self.stats.status = status
        self.stats.last_error_category = category
        self.stats.failed_transmissions += 1

    def _backoff_seconds(self) -> float:
        """Return bounded exponential backoff: 5, 10, 20 … 300 seconds."""
        return float(min(300, 5 * 2 ** max(0, self._consecutive_failures - 1)))

    async def async_stop(self) -> None:
        """Remove all timers/listeners and prevent orphaned tasks."""
        self._stopped = True
        if self._debounce_handle:
            self._debounce_handle.cancel()
            self._debounce_handle = None
        for unsubscribe in self._unsubscribers:
            unsubscribe()
        self._unsubscribers.clear()
        current = asyncio.current_task()
        tasks = [task for task in self._active_send_tasks if task is not current]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._active_send_tasks.clear()
        self._listeners.clear()
