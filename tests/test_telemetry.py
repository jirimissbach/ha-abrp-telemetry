"""Snapshot mapping, freshness, validation, and charging tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from custom_components.abrp_telemetry.telemetry import build_point, normalize_charging_state


@dataclass
class FakeState:
    state: str
    attributes: dict = field(default_factory=dict)


NOW = datetime(2026, 9, 15, 12, tzinfo=UTC)


def build(states, mappings, observed=None, overrides=None, stale_after=300):
    return build_point(
        states,
        mappings,
        overrides or {},
        dict.fromkeys(mappings.values(), NOW) if observed is None else observed,
        now=NOW,
        stale_after=stale_after,
    )


def test_complete_entity_mapping_and_units():
    mappings = {
        "soc": "sensor.soc",
        "estimated_range": "sensor.range",
        "speed": "sensor.speed",
        "vehicle_power": "sensor.power",
        "battery_temperature": "sensor.temp",
        "latitude": "sensor.lat",
        "longitude": "sensor.lon",
    }
    states = {
        "sensor.soc": FakeState("75", {"unit_of_measurement": "%"}),
        "sensor.range": FakeState("200", {"unit_of_measurement": "mi"}),
        "sensor.speed": FakeState("60", {"unit_of_measurement": "mph"}),
        "sensor.power": FakeState("12.5", {"unit_of_measurement": "kW"}),
        "sensor.temp": FakeState("68", {"unit_of_measurement": "°F"}),
        "sensor.lat": FakeState("50.1"),
        "sensor.lon": FakeState("14.4"),
    }
    result = build(states, mappings)
    assert result.invalid_fields == {}
    assert result.point["soc"]["frac"] == pytest.approx(0.75)
    assert result.point["estimatedBatteryRange"]["m"] == pytest.approx(321868.8)
    assert result.point["speed"]["ms"] == pytest.approx(26.8224)
    assert result.point["power"]["w"] == pytest.approx(12500)
    assert result.point["batteryTemperature"]["c"] == pytest.approx(20)
    assert result.point["location"]["long"] == pytest.approx(14.4)
    assert "Z" in result.point["soc"]["time"]


def test_unknown_unavailable_and_bad_optional_do_not_block_soc():
    mappings = {"soc": "sensor.soc", "speed": "sensor.speed", "odometer": "sensor.odo"}
    states = {
        "sensor.soc": FakeState("50", {"unit_of_measurement": "%"}),
        "sensor.speed": FakeState("unknown", {"unit_of_measurement": "km/h"}),
        "sensor.odo": FakeState("-3", {"unit_of_measurement": "km"}),
    }
    result = build(states, mappings)
    assert result.point["soc"]["frac"] == 0.5
    assert "speed" in result.invalid_fields
    assert "odometer" in result.invalid_fields


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("charging", "CHARGING_UNKNOWN"),
        ("charging_ac", "CHARGING_AC"),
        ("fast charging", "CHARGING_DC"),
        ("connected", "PLUGGED_IN"),
        ("complete", "PLUGGED_IN"),
        ("not_charging", "NOT_CHARGING"),
        ("off", "NOT_CHARGING"),
    ],
)
def test_charging_state_mapping(source, expected):
    assert normalize_charging_state(source) == expected


def test_custom_charging_state_mapping():
    assert normalize_charging_state("ladevorgang", {"ladevorgang": "CHARGING_AC"}) == "CHARGING_AC"


def test_charging_power_fallback_is_independent_and_negative():
    mappings = {"charging_state": "sensor.state", "charging_power": "sensor.power"}
    states = {
        "sensor.state": FakeState("charging"),
        "sensor.power": FakeState("84.2", {"unit_of_measurement": "kW"}),
    }
    result = build(states, mappings)
    assert result.point["chargingState"]["state"] == "CHARGING_UNKNOWN"
    assert result.point["power"]["w"] == pytest.approx(-84200)


def test_vehicle_power_takes_precedence_over_charging_power():
    mappings = {"vehicle_power": "sensor.vehicle", "charging_power": "sensor.charge"}
    states = {
        "sensor.vehicle": FakeState("20", {"unit_of_measurement": "kW"}),
        "sensor.charge": FakeState("84", {"unit_of_measurement": "kW"}),
    }
    assert build(states, mappings).point["power"]["w"] == 20000


def test_location_requires_valid_pair_and_protects_timestamp():
    mappings = {"latitude": "sensor.lat", "longitude": "sensor.lon"}
    states = {"sensor.lat": FakeState("91"), "sensor.lon": FakeState("14")}
    result = build(states, mappings)
    assert result.point is None
    assert "location" in result.invalid_fields


def test_device_tracker_location_attributes_are_supported():
    mappings = {"latitude": "device_tracker.car", "longitude": "device_tracker.car"}
    states = {"device_tracker.car": FakeState("not_home", {"latitude": 50.1, "longitude": 14.4})}
    result = build(states, mappings)
    assert result.point["location"]["lat"] == pytest.approx(50.1)
    assert result.point["location"]["long"] == pytest.approx(14.4)


def test_stale_data_suppression_and_restart_behavior():
    mappings = {"soc": "sensor.soc"}
    states = {"sensor.soc": FakeState("80", {"unit_of_measurement": "%"})}
    assert build(states, mappings, observed={}).point is None
    observed = {"sensor.soc": NOW - timedelta(seconds=301)}
    result = build(states, mappings, observed=observed)
    assert result.point is None
    assert result.stale_fields == ["soc"]


def test_unit_override_for_missing_metadata():
    mappings = {"estimated_range": "sensor.range"}
    result = build({"sensor.range": FakeState("10")}, mappings, overrides={"estimated_range": "km"})
    assert result.point["estimatedBatteryRange"]["m"] == 10000
