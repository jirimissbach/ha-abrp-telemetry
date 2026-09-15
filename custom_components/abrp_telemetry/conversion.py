"""Isolated numeric conversion and normalization helpers."""

from __future__ import annotations

import math
from typing import Final

from homeassistant.const import (
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfLength,
    UnitOfPower,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.util.unit_conversion import (
    DistanceConverter,
    ElectricCurrentConverter,
    ElectricPotentialConverter,
    EnergyConverter,
    PowerConverter,
    SpeedConverter,
    TemperatureConverter,
)


class ConversionError(ValueError):
    """A value cannot be safely converted."""


_UNIT_ALIASES: Final = {
    "km": "km",
    "m": "m",
    "mi": "mi",
    "mile": "mi",
    "miles": "mi",
    "km/h": "km/h",
    "kph": "km/h",
    "mph": "mph",
    "m/s": "m/s",
    "w": "W",
    "kw": "kW",
    "wh": "Wh",
    "kwh": "kWh",
    "°c": "°C",
    "c": "°C",
    "degc": "°C",
    "°f": "°F",
    "f": "°F",
    "degf": "°F",
    "%": "%",
    "v": "V",
    "a": "A",
    "ma": "mA",
    "mv": "mV",
    "s": "s",
    "min": "min",
    "h": "h",
    "°": "°",
    "deg": "°",
}

FIELD_VALID_UNITS: Final = {
    "soc": {"%", "fraction"},
    "estimated_range": set(DistanceConverter.VALID_UNITS),
    "charging_power": set(PowerConverter.VALID_UNITS),
    "vehicle_power": set(PowerConverter.VALID_UNITS),
    "speed": set(SpeedConverter.VALID_UNITS),
    "elevation": set(DistanceConverter.VALID_UNITS),
    "battery_temperature": set(TemperatureConverter.VALID_UNITS),
    "ambient_temperature": set(TemperatureConverter.VALID_UNITS),
    "odometer": set(DistanceConverter.VALID_UNITS),
    "hvac_power": set(PowerConverter.VALID_UNITS),
    "hvac_setpoint": set(TemperatureConverter.VALID_UNITS),
    "cabin_temperature": set(TemperatureConverter.VALID_UNITS),
    "battery_capacity": set(EnergyConverter.VALID_UNITS),
    "energy_remaining": set(EnergyConverter.VALID_UNITS),
    "state_of_health": {"%", "fraction"},
    "charging_energy_added": set(EnergyConverter.VALID_UNITS),
    "voltage": set(ElectricPotentialConverter.VALID_UNITS),
    "current": set(ElectricCurrentConverter.VALID_UNITS),
}


def finite_float(value: object) -> float:
    """Return a finite float, rejecting booleans and non-numeric values."""
    if isinstance(value, bool):
        raise ConversionError("boolean is not a numeric value")
    try:
        result = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as err:
        raise ConversionError("not numeric") from err
    if not math.isfinite(result):
        raise ConversionError("not finite")
    return result


def normalize_unit(unit: str | None) -> str | None:
    """Normalize common Home Assistant unit spellings."""
    if unit is None:
        return None
    compact = unit.strip().replace(" ", "")
    return _UNIT_ALIASES.get(compact.lower(), unit.strip())


def _require_unit(unit: str | None, valid: set[str], dimension: str) -> str:
    normalized = normalize_unit(unit)
    if normalized not in valid:
        raise ConversionError(f"unsupported {dimension} unit")
    return normalized


def distance_to_m(value: object, unit: str | None) -> float:
    """Convert distance to metres."""
    number = finite_float(value)
    source = _require_unit(unit, set(DistanceConverter.VALID_UNITS), "distance")
    return DistanceConverter.convert(number, source, UnitOfLength.METERS)


def speed_to_ms(value: object, unit: str | None) -> float:
    """Convert speed to metres per second."""
    number = finite_float(value)
    source = _require_unit(unit, set(SpeedConverter.VALID_UNITS), "speed")
    return SpeedConverter.convert(number, source, UnitOfSpeed.METERS_PER_SECOND)


def power_to_w(value: object, unit: str | None) -> float:
    """Convert power to watts."""
    number = finite_float(value)
    source = _require_unit(unit, set(PowerConverter.VALID_UNITS), "power")
    return PowerConverter.convert(number, source, UnitOfPower.WATT)


def energy_to_wh(value: object, unit: str | None) -> float:
    """Convert energy to watt-hours."""
    number = finite_float(value)
    source = _require_unit(unit, set(EnergyConverter.VALID_UNITS), "energy")
    return EnergyConverter.convert(number, source, UnitOfEnergy.WATT_HOUR)


def temperature_to_c(value: object, unit: str | None) -> float:
    """Convert temperature to Celsius."""
    number = finite_float(value)
    source = _require_unit(unit, set(TemperatureConverter.VALID_UNITS), "temperature")
    return TemperatureConverter.convert(number, source, UnitOfTemperature.CELSIUS)


def voltage_to_v(value: object, unit: str | None) -> float:
    """Convert electric potential to volts."""
    number = finite_float(value)
    source = _require_unit(unit, set(ElectricPotentialConverter.VALID_UNITS), "voltage")
    return ElectricPotentialConverter.convert(number, source, UnitOfElectricPotential.VOLT)


def current_to_a(value: object, unit: str | None) -> float:
    """Convert electric current to amperes."""
    number = finite_float(value)
    source = _require_unit(unit, set(ElectricCurrentConverter.VALID_UNITS), "current")
    return ElectricCurrentConverter.convert(number, source, UnitOfElectricCurrent.AMPERE)


def percentage_to_fraction(value: object, unit: str | None) -> float:
    """Convert a percentage/fraction to an ABRP fraction."""
    number = finite_float(value)
    source = normalize_unit(unit)
    if source == "%":
        number /= 100.0
    elif source not in (None, "fraction"):
        raise ConversionError("unsupported percentage unit")
    if not 0.0 <= number <= 1.0:
        raise ConversionError("outside 0–100%")
    return number


def identity(value: object, _unit: str | None = None) -> float:
    """Normalize a unitless numeric value."""
    return finite_float(value)


def validate_range(value: float, minimum: float, maximum: float, label: str) -> float:
    """Reject values outside conservative physical/schema limits."""
    if not minimum <= value <= maximum:
        raise ConversionError(f"{label} outside supported range")
    return value
