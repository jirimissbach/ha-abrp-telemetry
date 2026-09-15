# ABRP Telemetry for Home Assistant

ABRP Telemetry is a generic, UI-configured bridge that forwards vehicle measurements already available as Home Assistant entities to A Better Routeplanner (ABRP). One config entry represents one ABRP vehicle, so credentials, mappings, freshness, scheduling, diagnostics, and failures stay isolated.

> This integration forwards telemetry already available in Home Assistant. It does not control how frequently your vehicle integration obtains new data. If your vehicle integration updates state of charge every three minutes, ABRP cannot receive genuinely new SOC measurements more frequently than that.

It never connects to Škoda, Volkswagen, Tesla, BMW, or another manufacturer, never asks a source integration to refresh, and never bypasses upstream rate limits.

```text
Vehicle integration → Home Assistant entities → mapping/conversion/freshness → ABRP
```

## Requirements and credentials

- Home Assistant 2026.9 or newer.
- An ABRP vehicle configured with the **Generic** live-data connection and its telemetry token.
- A self-managed ABRP API key with `post_data` permission, created at <https://abetterrouteplanner.com/home/app/api-keys/telemetry>.

The current official API requires both values. ABRP documents no safe, non-mutating endpoint that validates this credential pair, so setup checks that both values exist and ABRP validates them on the first real telemetry upload. A rejection stops further requests and creates a Home Assistant repair issue.

## Install

### HACS custom repository

1. In HACS, open **Custom repositories**.
2. Add this GitHub repository as category **Integration**.
3. Install **ABRP Telemetry** and restart Home Assistant.
4. Go to **Settings → Devices & services → Add integration → ABRP Telemetry**.

### Manual

Copy `custom_components/abrp_telemetry` into your Home Assistant configuration's `custom_components` directory, restart Home Assistant, and add it from **Devices & services**. YAML configuration is not supported or needed.

## Add a vehicle

1. Enter a friendly vehicle name, API key, and that vehicle's telemetry token.
2. Map one or more Home Assistant entities. SOC is highly recommended, but no individual measurement is forced.
3. If an entity has no recognizable unit, select its source unit.
4. Choose a transmission mode and maximum source-data age.
5. Finish. Add the integration again for each additional vehicle.

Mappings and settings can be changed from **Configure** without deleting the vehicle or restarting Home Assistant. Token fingerprints prevent accidentally configuring the same ABRP telemetry token twice.

## Supported mappings and ABRP units

The current API accepts SOC/SOH (fraction), range/elevation/odometer (m), speed (m/s), power (W), energy/capacity (Wh), temperatures (°C), location, charging and driving state, voltage, current, heading, HVAC setpoint/power, and session charging energy. Home Assistant values are converted from common alternatives including km, miles, km/h, mph, W/kW, Wh/kWh, and °C/°F.

Latitude and longitude must be mapped together. Unknown, unavailable, non-finite, incompatible, and implausible optional values are omitted without blocking valid fields. Remaining charge time is not offered because the current ABRP input schema does not contain it.

Common charging values are mapped automatically. The options flow also accepts comma-separated custom source values for AC, DC, unknown-type charging, plugged-in, and not-charging states. Charging power is independent of charging state. If vehicle power is mapped successfully it takes precedence; otherwise the charging-power mapping supplies the API's power measurement using the historical negative-during-charging convention. Current ABRP documentation does not define the sign, so this behavior is isolated and documented rather than presented as current ABRP fact.

## Transmission modes

- **Event driven:** mapped changes are coalesced for one second, then all current mapped states are read and one snapshot is sent.
- **Periodic:** sends the latest eligible snapshot at the configured interval (default 10 seconds).
- **Hybrid:** sends after coalesced changes and also periodically.

In periodic mode, the latest valid telemetry can be retransmitted at the configured interval for compatibility with ABRP live telemetry expectations. Repeating a value does not make the underlying measurement newer. Each field retains the time at which Home Assistant observed the source update—not the upload time.

ABRP's current OpenAPI does not state a recommended telemetry cadence, numeric rate limit, or online/offline timeout. The 10-second default is a documented compatibility assumption based on older calibration guidance and can be changed. HTTP 429 responses honor `Retry-After`; other failures use bounded per-vehicle exponential backoff.

## Freshness and restart safety

The default maximum source-data age is five minutes. Freshness is tracked per mapped entity:

- stale optional fields are omitted;
- if no meaningful fresh measurement remains, nothing is sent and status becomes `source_data_stale`;
- periodic transmission never replaces measurement timestamps with upload timestamps;
- states already present when the integration starts are not assumed fresh—they become eligible only after an observed meaningful update.

This conservative restart behavior may delay the first upload until the source integration next updates an entity. It prevents arbitrarily old restored states from appearing new.

## Example: Škoda Enyaq

Your exact entity IDs depend on the source integration and how Home Assistant names the vehicle. A plausible mapping could be:

| ABRP field | Example Home Assistant entity |
|---|---|
| SOC | `sensor.skoda_enyaq_battery_percentage` |
| Estimated range | `sensor.skoda_enyaq_range` |
| Charging state | `sensor.skoda_enyaq_charging_state` |
| Charging power | `sensor.skoda_enyaq_charging_power` |

These names are examples only and are never hard-coded. Manufacturer APIs commonly impose their own rate limits; if the Škoda integration retrieves new values only every few minutes, this bridge cannot make them update faster.

## Diagnostics, privacy, and security

The vehicle device exposes status and last-success diagnostics. Attempt time, source age, and runtime-only success/failure counters are disabled by default to avoid clutter. Status can report waiting for source data, transmitting, connected, stale source data, authentication error, rate limited, or API error.

Vehicle telemetry can be sensitive. The integration sends selected measurement values and their timestamps only to `https://api.iternio.com/app/tlm`. It has no analytics or external logging. Tokens and keys are header-only and never placed in URLs, logs, exceptions, entities, or diagnostics. Diagnostics centrally redact credentials and location. Debug logs describe categories and timing decisions but never payloads, precise coordinates, credentials, headers, or response bodies.

## Troubleshooting

- **Waiting for source:** mapped entities have not meaningfully updated since this entry loaded. Wait for the source integration's next real update.
- **Source data stale:** increase the source-age setting only if repeating older measurements is appropriate for your vehicle integration.
- **Authentication error:** make sure the API key has `post_data` and the telemetry token belongs to this ABRP vehicle, then replace credentials through reauthentication/reload.
- **Unsupported source unit:** set the correct source unit in Configure; do not rely on a bare number.
- **Rate limited/API error:** the vehicle backs off automatically. Other configured vehicles continue independently.
- **Location missing:** map both latitude and longitude to numeric entities.

Enable debug logging for `custom_components.abrp_telemetry` when reporting a problem. Exported diagnostics contain no credentials or precise GPS data.

## Remove

Remove the vehicle entry from **Settings → Devices & services → ABRP Telemetry**. Then uninstall it in HACS (or remove the directory manually) and restart Home Assistant. Removing one entry does not affect other vehicles or revoke credentials in ABRP; revoke them in ABRP if no longer needed.

## Development

Research decisions and authoritative links are recorded in [docs/technical-design.md](docs/technical-design.md). Tests mock ABRP and never contact the service.

```bash
python -m pip install -e '.[test]'
pytest
ruff check .
ruff format --check .
```

MIT licensed. ABRP and A Better Routeplanner are trademarks of their respective owner; this project is unofficial.

