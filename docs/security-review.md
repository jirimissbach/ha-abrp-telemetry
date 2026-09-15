# Security review

Review date: 2026-09-15. Scope: `custom_components/abrp_telemetry`, config storage/flows, diagnostics, logging, scheduling, HTTP handling, and tests.

## Results

- **Credential leakage:** API key and telemetry token are stored only in config-entry data and private client attributes. They are password selectors in the UI, header-only on the wire, absent from URLs, and centrally redacted from diagnostics.
- **Logs and exceptions:** logs contain only an internal config-entry ID, timing reason, or error category. Payloads, headers, response bodies, tokens, and precise GPS values are never logged. Public exception text is fixed or contains only an HTTP status.
- **Location privacy:** coordinates exist only in the transient request point. Diagnostics do not retain snapshots and redact location-shaped keys recursively.
- **Transport:** the production base URL is fixed to HTTPS; custom client base URLs are rejected unless HTTPS. Home Assistant's shared HTTP session is injected.
- **Retries and denial of service:** one send lock prevents overlap per vehicle; event changes have a one-second trailing debounce; failures use bounded exponential backoff; HTTP 429 honors bounded `Retry-After`; authentication failures halt the vehicle. There is no retry loop inside one request.
- **Task lifecycle:** listeners and timers have unsubscribe handles. Debounce timers and in-flight uploads are canceled/awaited during unload. A regression test covers an upload blocked at unload.
- **Malformed values:** unavailable states, booleans used as numbers, parse failures, NaN/infinity, unsupported units, incomplete/invalid coordinates, and conservative physical/schema bounds are handled before the HTTP client. A bad optional field is omitted.
- **Configuration:** credentials must be non-empty, tokens are identified in HA only by a one-way truncated SHA-256 fingerprint, coordinates must be mapped as a pair, and no YAML/raw JSON entry point is exposed.
- **Cross-vehicle isolation:** every config entry owns its client, credentials, freshness map, lock, timers, backoff, counters, and diagnostic state. Tests exercise one failing vehicle alongside one successful vehicle.

## Findings fixed during review

1. In-flight uploads were not initially tracked during unload. The manager now tracks, cancels, and awaits them.
2. Voltage/current originally assumed native units. They now use Home Assistant electric-potential/current converters and ask for a unit when metadata is insufficient.
3. Entity-registry lifecycle was incomplete. The manager now follows entity-ID renames and creates/removes an actionable repair for removed mappings.
4. Unsupported source units were only visible in exported diagnostics. They now create a non-transient repair issue while valid fields continue.

## Residual, documented constraints

- ABRP labels the current telemetry upload endpoints alpha and does not document numeric rate limits, an offline timeout, or power sign. The provider and charging-power compatibility choices are isolated constants/logic and described in the technical design.
- ABRP documents no non-mutating API-key + telemetry-token validation operation. Credentials are validated by ABRP on the first real snapshot; failures halt and launch reauthentication.
- A release must not be tagged until a maintainer smoke-tests a real ABRP Generic connection from a real Home Assistant instance. Automated tests never call ABRP.

No open critical or high-severity finding remains from this review.

