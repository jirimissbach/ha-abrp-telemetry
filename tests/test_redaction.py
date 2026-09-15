"""Security redaction tests."""

from custom_components.abrp_telemetry.redaction import LOCATION_REDACTED, REDACTED, redact


def test_token_redaction_is_recursive_and_does_not_mutate():
    source = {"api_key": "secret", "nested": {"telemetry_token": "token"}}
    result = redact(source)
    assert result["api_key"] == REDACTED
    assert result["nested"]["telemetry_token"] == REDACTED
    assert source["api_key"] == "secret"


def test_gps_privacy():
    result = redact({"lat": 50.0, "long": 14.0, "location": {"latitude": 50}})
    assert result == {"lat": LOCATION_REDACTED, "long": LOCATION_REDACTED, "location": LOCATION_REDACTED}
