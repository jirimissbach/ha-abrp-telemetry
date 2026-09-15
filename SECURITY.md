# Security policy

Do not open a public issue containing ABRP API keys, telemetry tokens, vehicle identifiers, or precise location. Report a suspected credential leak privately through GitHub's security-advisory feature. Revoke exposed credentials in ABRP immediately.

Supported releases receive security fixes on the latest release line. The integration stores credentials in Home Assistant config entries, sends them only in HTTPS headers to `api.iternio.com`, and centrally redacts secrets and location from diagnostics.

