# Contributing

Bug reports and focused pull requests are welcome. Never include credentials or precise vehicle location in an issue, log excerpt, fixture, screenshot, or commit.

Before opening a pull request:

1. Explain any ABRP API behavior with a current authoritative source. If it is undocumented, isolate and document the assumption.
2. Add or update tests. ABRP must always be mocked.
3. Run `ruff check .`, `ruff format --check .`, and `pytest` on the supported Python/Home Assistant version.
4. Keep each config entry independent and preserve cleanup, backoff, redaction, and per-field measurement timestamps.

Do not add manufacturer-specific polling or entity IDs. Source integrations own vehicle data acquisition.

