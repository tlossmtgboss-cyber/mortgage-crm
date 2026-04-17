# backend/tests/test_aria_backend_client.py
import pytest
import httpx
from unittest.mock import AsyncMock, patch
from agents.aria_backend_client import call_backend_tool, BACKEND_TIMEOUT


def _make_response(status_code: int, json_data=None):
    """Helper to build httpx.Response with a request attached (needed for raise_for_status)."""
    request = httpx.Request("POST", "http://localhost:8000/test")
    if json_data is not None:
        import json
        content = json.dumps(json_data).encode()
        return httpx.Response(status_code, content=content, request=request,
                              headers={"content-type": "application/json"})
    return httpx.Response(status_code, request=request)


@pytest.mark.asyncio
async def test_call_backend_tool_success():
    mock_response = _make_response(200, {"spoken_summary": "Your loan is in underwriting."})
    with patch("agents.aria_backend_client.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.post.return_value = mock_response
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        result = await call_backend_tool("/internal/aria/loan-status", {"borrower_id": 42})
        assert result == {"spoken_summary": "Your loan is in underwriting."}
        instance.post.assert_called_once()


@pytest.mark.asyncio
async def test_call_backend_tool_timeout():
    with patch("agents.aria_backend_client.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.post.side_effect = httpx.TimeoutException("timeout")
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        with pytest.raises(httpx.TimeoutException):
            await call_backend_tool("/internal/aria/test", {})


@pytest.mark.asyncio
async def test_call_backend_tool_retries_on_500():
    error_response = _make_response(500)
    success_response = _make_response(200, {"ok": True})

    with patch("agents.aria_backend_client.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.post.side_effect = [
            httpx.HTTPStatusError("500", request=httpx.Request("POST", "http://test"), response=error_response),
            success_response,
        ]
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        result = await call_backend_tool("/internal/aria/test", {})
        assert result == {"ok": True}
        assert instance.post.call_count == 2


def test_backend_timeout_is_3_seconds():
    assert BACKEND_TIMEOUT == 3.0
