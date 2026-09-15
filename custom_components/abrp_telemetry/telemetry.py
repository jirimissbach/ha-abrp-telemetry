"""Build privacy-safe, validated ABRP telemetry points from HA states."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from .const import PROVIDER
from .conversion import (
    ConversionError,
    current_to_a,
    distance_to_m,
    energy_to_wh,
    finite_float,
    identity,
    percentage_to_fraction,
    power_to_w,
    speed_to_ms,
    temperature_to_c,
    validate_range,
    voltage_to_v,
)


class StateLike(Protocol):
    """Minimal State protocol used by the builder and unit tests."""

    state: str
    attributes: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class BuildResult:
    """Result of constructing a point."""

    point: dict[str, Any] | None
    invalid_fields: dict[str, str]
    stale_fields: list[str]
    source_ages: list[float]


CHARGING_STATES = {
    "charging": "CHARGING_UNKNOWN",
    "on": "CHARGING_UNKNOWN",
    "true": "CHARGING_UNKNOWN",
    "charging_ac": "CHARGING_AC",
    "ac_charging": "CHARGING_AC",
    "charging_dc": "CHARGING_DC",
    "dc_charging": "CHARGING_DC",
    "fast_charging": "CHARGING_DC",
    "connected": "PLUGGED_IN",
    "plugged_in": "PLUGGED_IN",
    "paused": "PLUGGED_IN",
    "complete": "PLUGGED_IN",
    "not_charging": "NOT_CHARGING",
    "disconnected": "NOT_CHARGING",
    "off": "NOT_CHARGING",
    "false": "NOT_CHARGING",
    "idle": "NOT_CHARGING",
}

DRIVING_STATES = {
    "park": "PARK",
    "parked": "PARK",
    "p": "PARK",
    "reverse": "REVERSE",
    "r": "REVERSE",
    "neutral": "NEUTRAL",
    "n": "NEUTRAL",
    "drive": "DRIVE",
    "driving": "DRIVE",
    "d": "DRIVE",
}

UNAVAILABLE_STATES = {"unknown", "unavailable", "none", "null", ""}


def normalize_charging_state(value: object, custom: Mapping[str, str] | None = None) -> str:
    """Map common HA charging representations to ABRP's documented enum."""
    key = str(value).strip().lower().replace(" ", "_").replace("-", "_")
    mapping = {**CHARGING_STATES, **{k.lower(): v for k, v in (custom or {}).items()}}
    if result := mapping.get(key):
        if result not in {"CHARGING_AC", "CHARGING_DC", "CHARGING_UNKNOWN", "NOT_CHARGING", "PLUGGED_IN"}:
            raise ConversionError("custom charging-state target is invalid")
        return result
    raise ConversionError("unrecognized charging state")


def normalize_driving_state(value: object) -> str:
    """Map common gear representations to ABRP's documented enum."""
    key = str(value).strip().lower().replace(" ", "_").replace("-", "_")
    if result := DRIVING_STATES.get(key):
        return result
    raise ConversionError("unrecognized driving state")


def _iso_time(timestamp: datetime) -> str:
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    return timestamp.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _numeric_payload(
    value: object,
    unit: str | None,
    converter: Callable[[object, str | None], float],
    child_key: str,
    timestamp: datetime,
    bounds: tuple[float, float, str] | None = None,
) -> dict[str, Any]:
    converted = converter(value, unit)
    if bounds:
        converted = validate_range(converted, *bounds)
    return {"time": _iso_time(timestamp), child_key: converted}


NUMERIC_FIELDS: dict[
    str, tuple[str, str, Callable[[object, str | None], float], tuple[float, float, str] | None]
] = {
    "soc": ("soc", "frac", percentage_to_fraction, (0, 1, "SOC")),
    "estimated_range": ("estimatedBatteryRange", "m", distance_to_m, (0, 2_000_000, "range")),
    "vehicle_power": ("power", "w", power_to_w, (-2_000_000, 2_000_000, "power")),
    "speed": ("speed", "ms", speed_to_ms, (0, 150, "speed")),
    "elevation": ("elevation", "m", distance_to_m, (-500, 10_000, "elevation")),
    "battery_temperature": ("batteryTemperature", "c", temperature_to_c, (-80, 150, "battery temperature")),
    "ambient_temperature": ("externalTemperature", "c", temperature_to_c, (-100, 100, "ambient temperature")),
    "odometer": ("odometer", "m", distance_to_m, (0, 10_000_000_000, "odometer")),
    "hvac_power": ("hvacPower", "w", power_to_w, (-100_000, 100_000, "HVAC power")),
    "hvac_setpoint": ("cabinSetPoint", "c", temperature_to_c, (5, 40, "HVAC setpoint")),
    "cabin_temperature": ("cabinTemperature", "c", temperature_to_c, (-80, 100, "cabin temperature")),
    "battery_capacity": ("batteryCapacity", "wh", energy_to_wh, (0, 1_000_000, "battery capacity")),
    "energy_remaining": ("soe", "wh", energy_to_wh, (0, 1_000_000, "energy remaining")),
    "state_of_health": ("soh", "frac", percentage_to_fraction, (0, 1, "state of health")),
    "voltage": ("voltage", "v", voltage_to_v, (0, 2000, "voltage")),
    "current": ("current", "a", current_to_a, (-5000, 5000, "current")),
    "heading": ("heading", "degrees", identity, (-360, 360, "heading")),
    "charging_energy_added": ("chargingEnergyAdded", "wh", energy_to_wh, (0, 1_000_000, "charging energy")),
}


def build_point(
    states: Mapping[str, StateLike | None],
    mappings: Mapping[str, str],
    unit_overrides: Mapping[str, str],
    observed: Mapping[str, datetime],
    *,
    now: datetime,
    stale_after: float,
    charging_state_map: Mapping[str, str] | None = None,
) -> BuildResult:
    """Build an ABRP InputPoint, omitting invalid, unavailable, and stale fields."""
    invalid: dict[str, str] = {}
    stale: list[str] = []
    ages: list[float] = []

    def get(field: str) -> tuple[StateLike, datetime, float] | None:
        entity_id = mappings.get(field)
        if not entity_id:
            return None
        state = states.get(entity_id)
        if state is None or state.state.strip().lower() in UNAVAILABLE_STATES:
            invalid[field] = "entity unavailable"
            return None
        timestamp = observed.get(entity_id)
        if timestamp is None:
            stale.append(field)
            return None
        age = max(0.0, (now - timestamp).total_seconds())
        if age > stale_after:
            stale.append(field)
            return None
        ages.append(age)
        return state, timestamp, age

    point: dict[str, Any] = {"provider": PROVIDER}
    for field, (parent, child, converter, bounds) in NUMERIC_FIELDS.items():
        item = get(field)
        if item is None:
            continue
        state, timestamp, _ = item
        unit = unit_overrides.get(field) or state.attributes.get("unit_of_measurement")
        try:
            point[parent] = _numeric_payload(state.state, unit, converter, child, timestamp, bounds)
        except ConversionError as err:
            invalid[field] = str(err)

    charging = get("charging_state")
    if charging:
        state, timestamp, _ = charging
        try:
            point["chargingState"] = {
                "time": _iso_time(timestamp),
                "state": normalize_charging_state(state.state, charging_state_map),
            }
        except ConversionError as err:
            invalid["charging_state"] = str(err)

    driving = get("driving_state")
    if driving:
        state, timestamp, _ = driving
        try:
            point["drivingState"] = {
                "time": _iso_time(timestamp),
                "state": normalize_driving_state(state.state),
            }
        except ConversionError as err:
            invalid["driving_state"] = str(err)

    latitude = get("latitude")
    longitude = get("longitude")
    if latitude and longitude:
        lat_state, lat_time, _ = latitude
        lon_state, lon_time, _ = longitude
        try:
            lat_raw = lat_state.attributes.get("latitude", lat_state.state)
            lon_raw = lon_state.attributes.get("longitude", lon_state.state)
            lat = validate_range(finite_float(lat_raw), -90, 90, "latitude")
            lon = validate_range(finite_float(lon_raw), -180, 180, "longitude")
            # Do not claim the pair is newer than its oldest coordinate.
            point["location"] = {"time": _iso_time(min(lat_time, lon_time)), "lat": lat, "long": lon}
        except ConversionError as err:
            invalid["location"] = str(err)
    elif latitude or longitude:
        invalid["location"] = "both latitude and longitude are required"

    # HA charging-power sensors conventionally expose positive draw. ABRP's current
    # schema has a single signed power field but does not document the sign. Preserve
    # the legacy API convention (charging negative) in this one isolated fallback.
    if "power" not in point and (charge_power := get("charging_power")):
        state, timestamp, _ = charge_power
        unit = unit_overrides.get("charging_power") or state.attributes.get("unit_of_measurement")
        try:
            watts = power_to_w(state.state, unit)
            point["power"] = {"time": _iso_time(timestamp), "w": -abs(watts)}
        except ConversionError as err:
            invalid["charging_power"] = str(err)

    if len(point) == 1:
        return BuildResult(None, invalid, stale, ages)
    return BuildResult(point, invalid, stale, ages)
