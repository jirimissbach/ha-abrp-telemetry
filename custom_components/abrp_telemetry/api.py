"""Async client for ABRP's current telemetry endpoint."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

from aiohttp import ClientError, ClientResponse, ClientSession, ClientTimeout

from .const import API_BASE_URL, API_TIMEOUT_SECONDS, TELEMETRY_PATH


class AbrpError(Exception):
    """Base exception that deliberately never includes response bodies or secrets."""

    category = "api_error"


class AbrpConnectionError(AbrpError):
    """Network or timeout failure."""

    category = "connection_error"


class AbrpAuthenticationError(AbrpError):
    """Invalid or unauthorized credentials."""

    category = "authentication_error"


class AbrpRateLimitError(AbrpError):
    """ABRP rate-limited this vehicle."""

    category = "rate_limited"

    def __init__(self, retry_after: float | None) -> None:
        super().__init__("ABRP rate limited the request")
        self.retry_after = retry_after


class AbrpServerError(AbrpError):
    """ABRP server failure."""

    category = "server_error"


class AbrpRequestError(AbrpError):
    """Rejected or malformed request."""

    category = "request_error"


class AbrpResponseError(AbrpError):
    """Malformed or unexpected successful response."""

    category = "response_error"


@dataclass(frozen=True, slots=True)
class AbrpResponse:
    """Privacy-safe subset of an ABRP response."""

    map_info_received: bool = False
    elevation_received: bool = False


def parse_retry_after(value: str | None, *, now: datetime | None = None) -> float | None:
    """Parse Retry-After seconds or an HTTP date, bounded by the scheduler."""
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            target = parsedate_to_datetime(value)
            if target.tzinfo is None:
                target = target.replace(tzinfo=UTC)
            return max(0.0, (target - (now or datetime.now(UTC))).total_seconds())
        except TypeError, ValueError, OverflowError:
            return None


class AbrpClient:
    """Small client using Home Assistant's shared aiohttp session."""

    def __init__(
        self,
        session: ClientSession,
        api_key: str,
        telemetry_token: str,
        *,
        base_url: str = API_BASE_URL,
    ) -> None:
        if not base_url.startswith("https://"):
            raise ValueError("ABRP base URL must use HTTPS")
        self._session = session
        self._api_key = api_key
        self._token = telemetry_token
        self._url = f"{base_url.rstrip('/')}{TELEMETRY_PATH}"

    @property
    def endpoint(self) -> str:
        """Return the credential-free endpoint for diagnostics."""
        return self._url

    async def async_send(self, point: Mapping[str, Any]) -> AbrpResponse:
        """Send one point using the token-authenticated batch endpoint."""
        headers = {
            "X-API-KEY": self._api_key,
            "X-TLM-TOKEN": self._token,
            "Accept": "application/json",
        }
        try:
            async with asyncio.timeout(API_TIMEOUT_SECONDS):
                response = await self._session.post(
                    self._url,
                    headers=headers,
                    json=[dict(point)],
                    timeout=ClientTimeout(total=API_TIMEOUT_SECONDS),
                )
                return await self._handle_response(response)
        except TimeoutError as err:
            raise AbrpConnectionError("ABRP request timed out") from err
        except ClientError as err:
            raise AbrpConnectionError("ABRP connection failed") from err

    async def _handle_response(self, response: ClientResponse) -> AbrpResponse:
        status = response.status
        if status in (401, 403):
            response.release()
            raise AbrpAuthenticationError("ABRP rejected the credentials")
        if status == 429:
            retry_after = parse_retry_after(response.headers.get("Retry-After"))
            response.release()
            raise AbrpRateLimitError(retry_after)
        if 500 <= status <= 599:
            response.release()
            raise AbrpServerError(f"ABRP server returned HTTP {status}")
        if status < 200 or status >= 300:
            response.release()
            raise AbrpRequestError(f"ABRP rejected telemetry with HTTP {status}")
        content_type = response.headers.get("Content-Type", "").lower()
        if "application/json" not in content_type:
            response.release()
            raise AbrpResponseError("ABRP returned an unexpected content type")
        try:
            data = await response.json()
        except (ValueError, ClientError) as err:
            raise AbrpResponseError("ABRP returned malformed JSON") from err
        if not isinstance(data, dict):
            raise AbrpResponseError("ABRP returned an unexpected JSON shape")
        return AbrpResponse("mapInfo" in data, "elevation" in data)
