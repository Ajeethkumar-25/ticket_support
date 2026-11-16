"""Unit tests for Helpdesk API client error handling and reliability.

All tests use unittest.mock to simulate HTTP responses — no live network calls.
The HelpdeskClient constructor accepts base_url/api_key/email so we can test
against a fake URL without touching the real Supabase helpdesk.
"""

import pytest
from unittest.mock import patch, MagicMock, call
import httpx
from src.client import (
    HelpdeskClient,
    TicketAlreadyHandledError,
    ServiceUnavailableError,
    RateLimitError,
    is_transient_error,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_client():
    """Return a client pointed at a dummy URL so config defaults are bypassed."""
    return HelpdeskClient(
        base_url="http://mock.test",
        api_key="test-key",
        email="test@example.com",
        rate_limit=0,          # Disable throttle in unit tests
    )


def _mock_response(status_code: int, body: str = "{}", headers: dict = None):
    """Build a MagicMock that looks like an httpx.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = body
    resp.content = body.encode()
    resp.is_error = status_code >= 400
    resp.headers = headers or {}
    resp.json = MagicMock(return_value=__import__("json").loads(body) if body else {})
    return resp


# ---------------------------------------------------------------------------
# Error-code dispatch tests
# ---------------------------------------------------------------------------

class TestErrorDispatch:
    """_send_request must raise the right exception for each HTTP error code."""

    def test_409_already_handled_raises_specific_error(self):
        client = _make_client()
        resp = _mock_response(409, '{"error": "already_handled"}')
        with patch("httpx.Client.request", return_value=resp):
            with pytest.raises(TicketAlreadyHandledError):
                client._send_request("POST", "/tickets/T001/reply", json_data={})

    def test_429_rate_limited_sleeps_and_raises(self):
        client = _make_client()
        resp = _mock_response(429, '{"error": "rate_limited"}',
                              headers={"Retry-After": "0.1"})
        with patch("httpx.Client.request", return_value=resp):
            with patch("time.sleep") as mock_sleep:
                with pytest.raises(RateLimitError):
                    client._send_request("GET", "/tickets")
                # Must sleep for the Retry-After value
                mock_sleep.assert_called_with(0.1)

    def test_429_missing_retry_after_defaults_to_one_second(self):
        """When Retry-After header is absent, sleep 1.0 s."""
        client = _make_client()
        resp = _mock_response(429, '{"error": "rate_limited"}', headers={})
        with patch("httpx.Client.request", return_value=resp):
            with patch("time.sleep") as mock_sleep:
                with pytest.raises(RateLimitError):
                    client._send_request("GET", "/tickets")
                mock_sleep.assert_called_with(1.0)

    def test_503_service_unavailable_raises_retryable_error(self):
        client = _make_client()
        resp = _mock_response(503, '{"error": "service_unavailable"}')
        with patch("httpx.Client.request", return_value=resp):
            with pytest.raises(ServiceUnavailableError):
                client._send_request("GET", "/tickets")

    def test_200_returns_parsed_json(self):
        client = _make_client()
        body = '{"tickets": [], "next_cursor": null}'
        resp = _mock_response(200, body)
        with patch("httpx.Client.request", return_value=resp):
            result = client._send_request("GET", "/tickets")
        assert result.status_code == 200


# ---------------------------------------------------------------------------
# is_transient_error predicate
# ---------------------------------------------------------------------------

class TestIsTransientError:
    def test_service_unavailable_is_transient(self):
        assert is_transient_error(ServiceUnavailableError(503, "oops"))

    def test_connect_error_is_transient(self):
        assert is_transient_error(httpx.ConnectError("connect failed"))

    def test_rate_limit_is_not_transient(self):
        """429 is handled by its own retry loop, NOT tenacity."""
        assert not is_transient_error(RateLimitError(retry_after=1.0))

    def test_already_handled_is_not_transient(self):
        assert not is_transient_error(TicketAlreadyHandledError(409, "dupe"))

    def test_value_error_is_not_transient(self):
        assert not is_transient_error(ValueError("bad input"))


# ---------------------------------------------------------------------------
# Network transport errors become ServiceUnavailableError
# ---------------------------------------------------------------------------

class TestNetworkErrors:
    def test_connect_error_wrapped_as_service_unavailable(self):
        client = _make_client()
        with patch("httpx.Client.request", side_effect=httpx.ConnectError("refused")):
            with pytest.raises(ServiceUnavailableError):
                client._send_request("GET", "/status")

    def test_read_timeout_wrapped_as_service_unavailable(self):
        client = _make_client()
        with patch("httpx.Client.request", side_effect=httpx.ReadTimeout("timed out")):
            with pytest.raises(ServiceUnavailableError):
                client._send_request("GET", "/status")


# ---------------------------------------------------------------------------
# Idempotency: 409 is NOT retried
# ---------------------------------------------------------------------------

class TestIdempotency:
    def test_409_is_not_retried(self):
        """TicketAlreadyHandledError must propagate immediately — not retried."""
        client = _make_client()
        resp = _mock_response(409, '{"error": "already_handled"}')
        with patch("httpx.Client.request", return_value=resp) as mock_req:
            with pytest.raises(TicketAlreadyHandledError):
                client._send_request("POST", "/tickets/T001/handoff", json_data={})
        # Only one HTTP call must have been made
        assert mock_req.call_count == 1


# ---------------------------------------------------------------------------
# Public endpoint wiring
# ---------------------------------------------------------------------------

class TestPublicEndpoints:
    def _client_with_response(self, body: dict):
        """Return (client, mock_execute) patched so _execute_with_retry returns body."""
        client = _make_client()
        patcher = patch.object(client, "_execute_with_retry", return_value=body)
        return client, patcher

    def test_get_status_calls_correct_endpoint(self):
        client, patcher = self._client_with_response(
            {"mode": "practice", "open_tickets": 30, "handled_tickets": 0}
        )
        with patcher as mock_exec:
            result = client.get_status()
        mock_exec.assert_called_once_with("GET", "/status")
        assert result["mode"] == "practice"

    def test_get_examples_unwraps_nested_dict(self):
        """API returns {"examples": [...]} — client must unwrap the list."""
        examples = [{"id": "E01"}, {"id": "E02"}]
        client, patcher = self._client_with_response({"examples": examples})
        with patcher:
            result = client.get_examples()
        assert result == examples

    def test_get_examples_handles_bare_list(self):
        """If the API ever returns a bare list, it passes through unchanged."""
        examples = [{"id": "E01"}]
        client, patcher = self._client_with_response(examples)
        with patcher:
            result = client.get_examples()
        assert result == examples

    def test_reset_practice_calls_post(self):
        client, patcher = self._client_with_response({"status": "reset"})
        with patcher as mock_exec:
            client.reset_practice()
        mock_exec.assert_called_once_with("POST", "/practice/reset")

    def test_post_reply_sends_correct_endpoint(self):
        client, patcher = self._client_with_response({"status": "ok"})
        payload = {"language": "nl", "category": "question", "priority": "P4",
                   "action": "reply", "draft_reply": "Antwoord"}
        with patcher as mock_exec:
            client.post_reply("T042", payload)
        mock_exec.assert_called_once_with("POST", "/tickets/T042/reply", json_data=payload)

    def test_post_handoff_sends_correct_endpoint(self):
        client, patcher = self._client_with_response({"status": "ok"})
        payload = {"handoff_note": "Needs billing review"}
        with patcher as mock_exec:
            client.post_handoff("T099", payload)
        mock_exec.assert_called_once_with("POST", "/tickets/T099/handoff", json_data=payload)

    def test_post_close_sends_correct_endpoint(self):
        client, patcher = self._client_with_response({"status": "ok"})
        payload = {"reason": "spam"}
        with patcher as mock_exec:
            client.post_close("T007", payload)
        mock_exec.assert_called_once_with("POST", "/tickets/T007/close", json_data=payload)


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

class TestPagination:
    def test_iter_open_tickets_stops_on_null_cursor(self):
        """Single page with no next_cursor — iterator must stop after yielding its tickets."""
        client = _make_client()
        page = {"tickets": [{"id": "T001"}, {"id": "T002"}], "next_cursor": None}
        with patch.object(client, "_execute_with_retry", return_value=page):
            tickets = list(client.iter_open_tickets(limit=10))
        assert [t["id"] for t in tickets] == ["T001", "T002"]

    def test_iter_open_tickets_follows_cursor(self):
        """Two pages separated by a cursor — iterator must yield tickets from both."""
        client = _make_client()
        page1 = {"tickets": [{"id": "T001"}], "next_cursor": "cursor-abc"}
        page2 = {"tickets": [{"id": "T002"}], "next_cursor": None}
        with patch.object(client, "_execute_with_retry", side_effect=[page1, page2]):
            tickets = list(client.iter_open_tickets(limit=1))
        assert [t["id"] for t in tickets] == ["T001", "T002"]

    def test_iter_open_tickets_empty_page_stops(self):
        """Empty tickets list — iterator must not loop forever."""
        client = _make_client()
        page = {"tickets": [], "next_cursor": "some-cursor"}
        with patch.object(client, "_execute_with_retry", return_value=page):
            tickets = list(client.iter_open_tickets())
        assert tickets == []
