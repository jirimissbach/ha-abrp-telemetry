"""Constants for ABRP Telemetry."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "abrp_telemetry"
NAME: Final = "ABRP Telemetry"
PLATFORMS: Final = ["sensor"]

CONF_API_KEY: Final = "api_key"
CONF_TOKEN: Final = "telemetry_token"
CONF_VEHICLE_NAME: Final = "vehicle_name"
CONF_MAPPINGS: Final = "mappings"
CONF_UNIT_OVERRIDES: Final = "unit_overrides"
CONF_MODE: Final = "mode"
CONF_INTERVAL: Final = "interval"
CONF_STALE_AFTER: Final = "stale_after"
CONF_CHARGING_AC_VALUES: Final = "charging_ac_values"
CONF_CHARGING_DC_VALUES: Final = "charging_dc_values"
CONF_CHARGING_VALUES: Final = "charging_values"
CONF_PLUGGED_VALUES: Final = "plugged_values"
CONF_NOT_CHARGING_VALUES: Final = "not_charging_values"

MODE_EVENT: Final = "event"
MODE_PERIODIC: Final = "periodic"
MODE_HYBRID: Final = "hybrid"
MODES: Final = (MODE_EVENT, MODE_PERIODIC, MODE_HYBRID)

# ABRP's historical telemetry documentation recommends at least once per 10 seconds
# for consumption calibration. The current OpenAPI does not state a cadence.
DEFAULT_INTERVAL: Final = 10
MIN_INTERVAL: Final = 5
MAX_INTERVAL: Final = 300
DEFAULT_STALE_AFTER: Final = 300
MIN_STALE_AFTER: Final = 60
MAX_STALE_AFTER: Final = 86400
DEBOUNCE_SECONDS: Final = 1.0

API_BASE_URL: Final = "https://api.iternio.com"
TELEMETRY_PATH: Final = "/app/tlm"
API_TIMEOUT_SECONDS: Final = 15
PROVIDER: Final = "APP_AUTO"

STATUS_WAITING: Final = "waiting_for_source"
STATUS_CONNECTED: Final = "connected"
STATUS_TRANSMITTING: Final = "transmitting"
STATUS_STALE: Final = "source_data_stale"
STATUS_AUTH_ERROR: Final = "authentication_error"
STATUS_RATE_LIMITED: Final = "rate_limited"
STATUS_API_ERROR: Final = "api_error"

SECRET_KEYS: Final = frozenset({CONF_API_KEY, CONF_TOKEN, "X-API-KEY", "X-TLM-TOKEN"})
LOCATION_KEYS: Final = frozenset({"latitude", "longitude", "lat", "long", "location"})

# Public mapping keys. ABRP's current InputPoint schema supports every entry except
# charging_power, which is an HA-friendly source alias for the API's power field.
FIELD_KEYS: Final = (
    "soc",
    "estimated_range",
    "charging_state",
    "charging_power",
    "vehicle_power",
    "speed",
    "latitude",
    "longitude",
    "elevation",
    "battery_temperature",
    "ambient_temperature",
    "odometer",
    "hvac_power",
    "hvac_setpoint",
    "cabin_temperature",
    "battery_capacity",
    "energy_remaining",
    "state_of_health",
    "voltage",
    "current",
    "heading",
    "charging_energy_added",
    "driving_state",
)
