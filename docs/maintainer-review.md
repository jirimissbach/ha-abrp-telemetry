# External-maintainer readiness review

Review date: 2026-09-15.

## Acceptance assessment

The repository is suitable for an initial development branch and HACS custom-repository test. It has one integration, a valid custom-component layout and manifest, brand assets, UI-only configuration, independent multi-entry runtime state, options/reauth flows, unload support, translations, diagnostics, repairs, explicit API research, user documentation, security guidance, CI, Dependabot, and mocked tests.

Local validation against Home Assistant 2026.9.0 / Python 3.14.2:

- 61 tests passed; no real ABRP request was made.
- 86.06% branch-aware coverage (configured floor: 85%).
- Ruff lint passed.
- Ruff formatting check passed.
- Manifest, HACS JSON, translation parity, single-integration structure, and PNG signature checks passed.
- A full config entry loaded, created diagnostic entities, and unloaded cleanly in the HA test harness.

## Publication gates

- GitHub-hosted HACS validation depends on repository metadata (description, topics, issues, and brand discovery), so the included official HACS action must pass after the repository is pushed.
- The included hassfest action must pass in GitHub Actions; the PyPI Home Assistant package does not ship the hassfest runner for a fully equivalent local invocation.
- Confirm the inferred repository name `jirimissbach/ha-abrp-telemetry` or update manifest/documentation/issue links before pushing elsewhere.
- Smoke-test one real vehicle, including ABRP acceptance of `provider: APP_AUTO`, before creating the first tag/release. This is intentionally a release gate, not an automated-test dependency.

No merge or release has been performed.

