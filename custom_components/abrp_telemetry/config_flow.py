"""UI configuration for ABRP Telemetry."""

from __future__ import annotations

import hashlib
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_API_KEY,
    CONF_CHARGING_AC_VALUES,
    CONF_CHARGING_DC_VALUES,
    CONF_CHARGING_VALUES,
    CONF_INTERVAL,
    CONF_MAPPINGS,
    CONF_MODE,
    CONF_NOT_CHARGING_VALUES,
    CONF_PLUGGED_VALUES,
    CONF_STALE_AFTER,
    CONF_TOKEN,
    CONF_UNIT_OVERRIDES,
    CONF_VEHICLE_NAME,
    DEFAULT_INTERVAL,
    DEFAULT_STALE_AFTER,
    DOMAIN,
    FIELD_KEYS,
    MAX_INTERVAL,
    MAX_STALE_AFTER,
    MIN_INTERVAL,
    MIN_STALE_AFTER,
    MODES,
)
from .conversion import FIELD_VALID_UNITS, normalize_unit

UNIT_OPTIONS: dict[str, list[str]] = {
    "soc": ["%", "fraction"],
    "estimated_range": ["km", "m", "mi"],
    "charging_power": ["W", "kW"],
    "vehicle_power": ["W", "kW"],
    "speed": ["km/h", "mph", "m/s"],
    "elevation": ["m", "km", "mi"],
    "battery_temperature": ["°C", "°F"],
    "ambient_temperature": ["°C", "°F"],
    "odometer": ["km", "m", "mi"],
    "hvac_power": ["W", "kW"],
    "hvac_setpoint": ["°C", "°F"],
    "cabin_temperature": ["°C", "°F"],
    "battery_capacity": ["Wh", "kWh"],
    "energy_remaining": ["Wh", "kWh"],
    "state_of_health": ["%", "fraction"],
    "charging_energy_added": ["Wh", "kWh"],
    "voltage": ["V", "mV"],
    "current": ["A", "mA"],
}


def _entity_selector() -> selector.EntitySelector:
    # Deliberately allow any entity: template/helper entities are valid sources too.
    return selector.EntitySelector(selector.EntitySelectorConfig(multiple=False))


def _number_selector(minimum: int, maximum: int, unit: str) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=minimum,
            max=maximum,
            step=1,
            mode=selector.NumberSelectorMode.BOX,
            unit_of_measurement=unit,
        )
    )


def _mapping_schema(defaults: dict[str, Any]) -> vol.Schema:
    schema: dict[Any, Any] = {}
    mappings = defaults.get(CONF_MAPPINGS, {})
    for field in FIELD_KEYS:
        marker = vol.Optional(field, default=mappings[field]) if field in mappings else vol.Optional(field)
        schema[marker] = _entity_selector()
    schema[vol.Required(CONF_MODE, default=defaults.get(CONF_MODE, "event"))] = selector.SelectSelector(
        selector.SelectSelectorConfig(options=list(MODES), translation_key="transmission_mode")
    )
    schema[vol.Required(CONF_INTERVAL, default=defaults.get(CONF_INTERVAL, DEFAULT_INTERVAL))] = (
        _number_selector(MIN_INTERVAL, MAX_INTERVAL, "s")
    )
    schema[vol.Required(CONF_STALE_AFTER, default=defaults.get(CONF_STALE_AFTER, DEFAULT_STALE_AFTER))] = (
        _number_selector(MIN_STALE_AFTER, MAX_STALE_AFTER, "s")
    )
    return vol.Schema(schema)


def _credentials_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_VEHICLE_NAME, default=defaults.get(CONF_VEHICLE_NAME, "")): str,
            vol.Required(CONF_API_KEY, default=defaults.get(CONF_API_KEY, "")): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
            vol.Required(CONF_TOKEN, default=defaults.get(CONF_TOKEN, "")): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
        }
    )


def _charging_map(data: dict[str, Any]) -> dict[str, str]:
    targets = {
        CONF_CHARGING_AC_VALUES: "CHARGING_AC",
        CONF_CHARGING_DC_VALUES: "CHARGING_DC",
        CONF_CHARGING_VALUES: "CHARGING_UNKNOWN",
        CONF_PLUGGED_VALUES: "PLUGGED_IN",
        CONF_NOT_CHARGING_VALUES: "NOT_CHARGING",
    }
    result: dict[str, str] = {}
    for key, target in targets.items():
        for raw in str(data.get(key, "")).split(","):
            if value := raw.strip().lower():
                result[value] = target
    return result


class AbrpTelemetryConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure one ABRP vehicle per entry."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Collect a friendly name and both currently documented credentials."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input[CONF_API_KEY].strip() or not user_input[CONF_TOKEN].strip():
                errors["base"] = "invalid_credentials"
            else:
                token_fingerprint = hashlib.sha256(user_input[CONF_TOKEN].encode()).hexdigest()[:24]
                await self.async_set_unique_id(token_fingerprint)
                self._abort_if_unique_id_configured()
                self._data.update(user_input)
                return await self.async_step_mappings()
        return self.async_show_form(step_id="user", data_schema=_credentials_schema(), errors=errors)

    async def async_step_mappings(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Collect entity mappings and scheduling settings."""
        errors: dict[str, str] = {}
        if user_input is not None:
            mappings = {field: user_input[field] for field in FIELD_KEYS if user_input.get(field)}
            if not mappings:
                errors["base"] = "mapping_required"
            elif bool(mappings.get("latitude")) != bool(mappings.get("longitude")):
                errors["base"] = "location_pair_required"
            else:
                self._data.update(
                    {
                        CONF_MAPPINGS: mappings,
                        CONF_MODE: user_input[CONF_MODE],
                        CONF_INTERVAL: int(user_input[CONF_INTERVAL]),
                        CONF_STALE_AFTER: int(user_input[CONF_STALE_AFTER]),
                    }
                )
                return await self.async_step_units()
        return self.async_show_form(
            step_id="mappings", data_schema=_mapping_schema(self._data), errors=errors
        )

    def _unknown_units(self) -> list[str]:
        unknown: list[str] = []
        for field, entity_id in self._data.get(CONF_MAPPINGS, {}).items():
            if field not in UNIT_OPTIONS:
                continue
            state = self.hass.states.get(entity_id)
            unit = normalize_unit(state.attributes.get("unit_of_measurement")) if state else None
            if unit not in FIELD_VALID_UNITS[field]:
                unknown.append(field)
        return unknown

    async def async_step_units(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Ask only for units that cannot be determined from entity metadata."""
        unknown = self._unknown_units()
        if user_input is not None or not unknown:
            self._data[CONF_UNIT_OVERRIDES] = dict(user_input or {})
            return self.async_create_entry(title=self._data[CONF_VEHICLE_NAME], data=self._data)
        fields: dict[Any, Any] = {}
        for field in unknown:
            fields[vol.Required(field)] = selector.SelectSelector(
                selector.SelectSelectorConfig(options=UNIT_OPTIONS[field])
            )
        return self.async_show_form(step_id="units", data_schema=vol.Schema(fields))

    async def async_step_reauth(self, _entry_data: dict[str, Any]) -> FlowResult:
        """Start credential replacement after an authentication issue."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Replace credentials and reload the affected vehicle only."""
        entry = self._get_reauth_entry()
        if user_input is not None:
            new_data = {
                **entry.data,
                CONF_API_KEY: user_input[CONF_API_KEY],
                CONF_TOKEN: user_input[CONF_TOKEN],
            }
            self.hass.config_entries.async_update_entry(entry, data=new_data)
            await self.hass.config_entries.async_reload(entry.entry_id)
            return self.async_abort(reason="reauth_successful")
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_API_KEY): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                    ),
                    vol.Required(CONF_TOKEN): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                    ),
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> AbrpOptionsFlow:
        return AbrpOptionsFlow(config_entry)


class AbrpOptionsFlow(config_entries.OptionsFlow):
    """Update mappings, freshness, modes, and custom charging values."""

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self.entry = entry
        self._data: dict[str, Any] = {**entry.data, **entry.options}

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Edit mappings and scheduling."""
        errors: dict[str, str] = {}
        if user_input is not None:
            mappings = {field: user_input[field] for field in FIELD_KEYS if user_input.get(field)}
            if not mappings:
                errors["base"] = "mapping_required"
            elif bool(mappings.get("latitude")) != bool(mappings.get("longitude")):
                errors["base"] = "location_pair_required"
            else:
                self._data.update(
                    {
                        CONF_MAPPINGS: mappings,
                        CONF_MODE: user_input[CONF_MODE],
                        CONF_INTERVAL: int(user_input[CONF_INTERVAL]),
                        CONF_STALE_AFTER: int(user_input[CONF_STALE_AFTER]),
                    }
                )
                return await self.async_step_charging_states()
        return self.async_show_form(step_id="init", data_schema=_mapping_schema(self._data), errors=errors)

    async def async_step_charging_states(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Allow unusual source integrations to define charging vocabulary."""
        if user_input is not None:
            self._data["charging_state_map"] = _charging_map(user_input)
            return await self.async_step_units()
        return self.async_show_form(
            step_id="charging_states",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_CHARGING_AC_VALUES, default=""): str,
                    vol.Optional(CONF_CHARGING_DC_VALUES, default=""): str,
                    vol.Optional(CONF_CHARGING_VALUES, default=""): str,
                    vol.Optional(CONF_PLUGGED_VALUES, default=""): str,
                    vol.Optional(CONF_NOT_CHARGING_VALUES, default=""): str,
                }
            ),
        )

    def _unknown_units(self) -> list[str]:
        unknown: list[str] = []
        for field, entity_id in self._data.get(CONF_MAPPINGS, {}).items():
            if field not in UNIT_OPTIONS:
                continue
            state = self.hass.states.get(entity_id)
            unit = normalize_unit(state.attributes.get("unit_of_measurement")) if state else None
            if unit not in FIELD_VALID_UNITS[field]:
                unknown.append(field)
        return unknown

    async def async_step_units(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Update only unit overrides that are necessary."""
        unknown = self._unknown_units()
        if user_input is not None or not unknown:
            self._data[CONF_UNIT_OVERRIDES] = dict(user_input or {})
            options = {
                key: value
                for key, value in self._data.items()
                if key not in (CONF_API_KEY, CONF_TOKEN, CONF_VEHICLE_NAME)
            }
            return self.async_create_entry(title="", data=options)
        current = self._data.get(CONF_UNIT_OVERRIDES, {})
        fields: dict[Any, Any] = {}
        for field in unknown:
            default = current.get(field, UNIT_OPTIONS[field][0])
            fields[vol.Required(field, default=default)] = selector.SelectSelector(
                selector.SelectSelectorConfig(options=UNIT_OPTIONS[field])
            )
        return self.async_show_form(step_id="units", data_schema=vol.Schema(fields))
