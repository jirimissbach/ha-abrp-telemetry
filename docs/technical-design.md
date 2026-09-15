# Technical design and research record

Research date: 2026-09-15. Authoritative sources were preferred; undocumented behavior is identified below.

## Resolved research questions

1. **Current endpoint:** `POST https://api.iternio.com/2/app/tlm`. The current Iternio Planning API OpenAPI declares `https://api.iternio.com/2` as its server and calls `/app/tlm` the legacy-v1-token batch telemetry endpoint. The older `/1/tlm/send` query-string endpoint is not used.
2. **Authentication:** `X-TLM-TOKEN` authorizes the vehicle write. `X-API-KEY` is also required, must carry `post_data`, and attributes points to an integration. Users can create a self-managed key at <https://abetterrouteplanner.com/home/app/api-keys/telemetry>. Both are sent only as headers.
3. **Supported input fields:** battery capacity, battery temperature, cabin setpoint, cabin temperature, charging state, driving state, elevation, estimated battery range, external temperature, HVAC power, charging energy added, location, odometer, power, SOC, state of energy, state of health, speed, voltage, heading, and current, plus the required provider identifier.
4. **Required fields:** the `InputPoint` schema requires only `provider`; every measurement is optional. This implementation nevertheless requires at least one mapped measurement before setup and labels SOC as highly recommended.
5. **Units:** current OpenAPI uses metres, metres/second, watts, watt-hours, degrees Celsius, volts, amperes, degrees, and fractional SOC/SOH. Each measurement contains its own RFC 3339 `time`. Location is a paired latitude/longitude object.
6. **Recommended interval:** not stated by the current OpenAPI. Ten seconds is retained as a configurable compatibility default because ABRP's historical telemetry guidance recommended at least one speed/power/charging sample per 10 seconds for calibration. This is an explicit assumption, not a claim about current online detection.
7. **Offline/stale interval:** not documented in the current API. The bridge makes no attempt to simulate online status. Its default *source* freshness limit is five minutes and is user-configurable.
8. **Measurement vs upload timestamp:** yes. Every input measurement carries its own `time`; upload time is not an input field. The integration uses the observed Home Assistant state-update time and never replaces it with the periodic upload time.
9. **Partial telemetry:** yes, structurally: all measurement properties are optional. Invalid/stale optional fields are omitted. An empty provider-only point is never sent.
10. **Rate limits:** no numeric telemetry rate limit is documented. The client handles any HTTP 429, honors `Retry-After`, and applies per-vehicle bounded backoff. The configured minimum interval is five seconds.
11. **Charging power sign:** the current `PowerW` schema documents watts but not sign. A dedicated charging-power mapping is therefore an HA-facing convenience fallback: when no vehicle-power mapping yielded a value, it applies the historical convention of negative charging power. That assumption is isolated in `telemetry.py`. A directly mapped vehicle-power value is preserved.
12. **HA unit APIs:** the conversion layer uses Home Assistant's current `DistanceConverter`, `SpeedConverter`, `PowerConverter`, `EnergyConverter`, and `TemperatureConverter` from `homeassistant.util.unit_conversion`, together with HA unit constants and a small controlled alias/validation layer.
13. **HACS:** one integration under `custom_components`, all runtime files inside its domain directory, a manifest with domain/documentation/issue tracker/code owners/name/version, repository `hacs.json`, and brand `icon.png`. Releases are preferred, not required. HACS validation is included.
14. **HA integration requirements:** a UI config flow declared in the manifest, custom-integration version, integration type, runtime data on `ConfigEntry.runtime_data`, unload support, translated entities/flows, shared web session injection, diagnostics redaction, and tests. This repository targets Home Assistant 2026.9.

Primary references:

- [Iternio Planning API v2 OpenAPI](https://api.iternio.com/swagger-ui/)
- [Home Assistant config flows](https://developers.home-assistant.io/docs/config_entries_config_flow_handler/)
- [Home Assistant integration manifest](https://developers.home-assistant.io/docs/creating_integration_manifest/)
- [Home Assistant quality scale](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/)
- [Home Assistant diagnostics](https://developers.home-assistant.io/docs/core/integration/diagnostics/)
- [HACS integration publishing requirements](https://www.hacs.xyz/docs/publish/integration/)
- [HACS validation action](https://www.hacs.xyz/docs/publish/action/)

## Architecture

Each config entry owns one `AbrpClient`, `TelemetryManager`, freshness map, backoff state, counters, listeners, and timers. Entries share only Home Assistant's managed HTTP session.

The manager listens only to mapped entities. It deliberately does not seed freshness from states already present at startup. A value becomes eligible after a meaningful state/unit event observed during the current runtime, preventing restored states from being presented as new measurements. Periodic sends retain the original per-field measurement timestamps.

The API requires a `provider` value but its input enum does not contain the generic `TLM_API` value shown elsewhere in the API's provider list. `APP_AUTO` is the closest accepted generic automatic-telemetry value and is isolated as the `PROVIDER` constant so it can be changed without touching mapping logic if Iternio clarifies the schema.

The snapshot builder reads all current mapped states, converts compatible units, validates values, pairs coordinates, omits invalid/stale optional fields, and refuses provider-only payloads. Network failures never escape into Home Assistant's event loop.

## Intentional exclusions

- OAuth and ABRP account sessions.
- Vehicle-manufacturer communication or refresh calls.
- Remaining charge time: absent from the current ABRP `InputPoint` schema.
- Numeric assumptions for ABRP offline detection or rate limits.
- Persisting counters: diagnostics are explicitly runtime-only.
