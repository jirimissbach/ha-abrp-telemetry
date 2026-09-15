"""ABRP HTTP client behavior tests; no real network is used."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.abrp_telemetry.api import (
    AbrpAuthenticationError,
    AbrpClient,
    AbrpConnectionError,
    AbrpRateLimitError,
    AbrpRequestError,
    AbrpResponseError,
    AbrpServerError,
)


def response(status=200, data=None, headers=None):
    result = Mock()
    result.status = status
    result.headers = headers or {"Content-Type": "application/json"}
    result.json = AsyncMock(return_value={} if data is None else data)
    result.release = Mock()
    return result


@pytest.mark.asyncio
async def test_success_uses_headers_and_body_not_query_string():
    session = Mock()
    session.post = AsyncMock(return_value=response(data={"elevation": {"m": 100}}))
    client = AbrpClient(session, "api-secret", "token-secret")
    result = await client.async_send({"provider": "APP_AUTO", "soc": {"frac": 0.5}})
    assert result.elevation_received
    url = session.post.call_args.args[0]
    kwargs = session.post.call_args.kwargs
    assert url == "https://api.iternio.com/2/app/tlm"
    assert "api-secret" not in url and "token-secret" not in url
    assert kwargs["headers"]["X-API-KEY"] == "api-secret"
    assert kwargs["headers"]["X-TLM-TOKEN"] == "token-secret"
    assert kwargs["json"] == [{"provider": "APP_AUTO", "soc": {"frac": 0.5}}]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403])
async def test_authentication_failure(status):
    session = Mock(post=AsyncMock(return_value=response(status)))
    with pytest.raises(AbrpAuthenticationError, match="credentials"):
        await AbrpClient(session, "key", "token").async_send({"provider": "APP_AUTO"})


@pytest.mark.asyncio
async def test_rate_limit_and_retry_after():
    session = Mock(post=AsyncMock(return_value=response(429, headers={"Retry-After": "42"})))
    with pytest.raises(AbrpRateLimitError) as exc:
        await AbrpClient(session, "key", "token").async_send({"provider": "APP_AUTO"})
    assert exc.value.retry_after == 42


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "error"), [(400, AbrpRequestError), (500, AbrpServerError), (503, AbrpServerError)]
)
async def test_http_errors(status, error):
    session = Mock(post=AsyncMock(return_value=response(status)))
    with pytest.raises(error):
        await AbrpClient(session, "key", "token").async_send({"provider": "APP_AUTO"})


@pytest.mark.asyncio
async def test_timeout():
    session = Mock(post=AsyncMock(side_effect=TimeoutError))
    with pytest.raises(AbrpConnectionError, match="timed out"):
        await AbrpClient(session, "key", "token").async_send({"provider": "APP_AUTO"})


@pytest.mark.asyncio
async def test_malformed_and_unexpected_responses():
    malformed = response()
    malformed.json = AsyncMock(side_effect=ValueError)
    session = Mock(post=AsyncMock(return_value=malformed))
    with pytest.raises(AbrpResponseError, match="malformed"):
        await AbrpClient(session, "key", "token").async_send({"provider": "APP_AUTO"})

    session.post = AsyncMock(return_value=response(headers={"Content-Type": "text/plain"}))
    with pytest.raises(AbrpResponseError, match="content type"):
        await AbrpClient(session, "key", "token").async_send({"provider": "APP_AUTO"})


def test_https_is_mandatory():
    with pytest.raises(ValueError, match="HTTPS"):
        AbrpClient(Mock(), "key", "token", base_url="http://example.test")
