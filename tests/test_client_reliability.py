"""Unit tests for Helpdesk API client error handling and reliability."""

import pytest
from unittest.mock import patch, MagicMock
import httpx
from src.client import (
    HelpdeskClient, 
    TicketAlreadyHandledError, 
    ServiceUnavailableError, 
    RateLimitError
)


def test_409_already_handled_raises_specific_error():
    client = HelpdeskClient(base_url="http://mock.test", api_key="k", email="e@test.com")
    
    mock_resp = MagicMock()
    mock_resp.status_code = 409
    mock_resp.is_error = True
    mock_resp.text = '{"error": "already_handled"}'

    with patch("httpx.Client.request", return_value=mock_resp):
        with pytest.raises(TicketAlreadyHandledError):
            client._send_request("POST", "/tickets/T001/reply", json_data={})


def test_429_rate_limited_sleeps_and_raises():
    client = HelpdeskClient(base_url="http://mock.test", api_key="k", email="e@test.com")

    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_resp.headers = {"Retry-After": "0.1"}
    mock_resp.is_error = True
    mock_resp.text = '{"error": "rate_limited"}'

    with patch("httpx.Client.request", return_value=mock_resp):
        with patch("time.sleep") as mock_sleep:
            with pytest.raises(RateLimitError):
                client._send_request("GET", "/tickets")
            mock_sleep.assert_called_with(0.1)


def test_503_service_unavailable_raises_retryable_error():
    client = HelpdeskClient(base_url="http://mock.test", api_key="k", email="e@test.com")

    mock_resp = MagicMock()
    mock_resp.status_code = 503
    mock_resp.is_error = True
    mock_resp.text = '{"error": "service_unavailable"}'

    with patch("httpx.Client.request", return_value=mock_resp):
        with pytest.raises(ServiceUnavailableError):
            client._send_request("GET", "/tickets")
