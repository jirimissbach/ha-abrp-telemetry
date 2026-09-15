"""Unit conversion and validation tests."""

from __future__ import annotations

import math

import pytest

from custom_components.abrp_telemetry.conversion import (
    ConversionError,
    current_to_a,
    distance_to_m,
    energy_to_wh,
    finite_float,
    percentage_to_fraction,
    power_to_w,
    speed_to_ms,
    temperature_to_c,
    voltage_to_v,
)


@pytest.mark.parametrize(
    ("value", "unit", "expected"),
    [(1, "km", 1000), (123, "m", 123), (1, "mi", 1609.344)],
)
def test_distance_conversions(value, unit, expected):
    assert distance_to_m(value, unit) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("value", "unit", "expected"),
    [(36, "km/h", 10), (10, "m/s", 10), (60, "mph", 26.8224)],
)
def test_speed_conversions(value, unit, expected):
    assert speed_to_ms(value, unit) == pytest.approx(expected)


def test_power_and_energy_conversions():
    assert power_to_w(84.2, "kW") == pytest.approx(84200)
    assert power_to_w(84200, "W") == pytest.approx(84200)
    assert energy_to_wh(77, "kWh") == pytest.approx(77000)


def test_temperature_conversion():
    assert temperature_to_c(68, "°F") == pytest.approx(20)
    assert temperature_to_c(20, "°C") == pytest.approx(20)


def test_electrical_unit_conversion():
    assert voltage_to_v(400_000, "mV") == pytest.approx(400)
    assert current_to_a(3500, "mA") == pytest.approx(3.5)


def test_soc_validation():
    assert percentage_to_fraction(80, "%") == pytest.approx(0.8)
    assert percentage_to_fraction(0.8, None) == pytest.approx(0.8)
    with pytest.raises(ConversionError):
        percentage_to_fraction(101, "%")


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, True, "invalid"])
def test_invalid_numeric_values(value):
    with pytest.raises(ConversionError):
        finite_float(value)


def test_unknown_or_incompatible_unit():
    with pytest.raises(ConversionError, match="unsupported distance unit"):
        distance_to_m(1, "yards")
