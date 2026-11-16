"""Roosterly Helpdesk API Client.

Production-grade client implementing:
- Proactive client-side rate limiting (< 5 requests/sec).
- 503 Service Unavailable: Exponential backoff + random jitter via tenacity.
- 429 Rate Limited: Dynamic wait based on Retry-After header.
- 409 Already Handled: Idempotency safety - never retries duplicate requests.
- Cursor-based ticket pagination.
"""

from typing import Dict, Any, List, Optional, Tuple, Iterator
import time
import random
import logging
import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential_jitter,
    retry_if_exception,
    before_sleep_log
)

from src.config import (
    HELPDESK_BASE_URL,
    HELPDESK_API_KEY,
    CANDIDATE_EMAIL,
    REQUEST_RATE_LIMIT,
    MAX_RETRIES,
    RETRY_INITIAL_DELAY
)

logger = logging.getLogger("helpdesk_client")


class HelpdeskAPIError(Exception):
    """Base exception for Helpdesk API interactions."""
    def __init__(self, status_code: int, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(f"Helpdesk API Error {status_code}: {message}")
        self.status_code = status_code
        self.message = message
        self.details = details or {}


class TicketAlreadyHandledError(HelpdeskAPIError):
    """409 Conflict: This ticket was already handled. Never retry."""
    pass


class RateLimitError(HelpdeskAPIError):
    """429 Too Many Requests: Exceeded 5 calls/second."""
    def __init__(self, retry_after: float, message: str = "Rate limited"):
        super().__init__(429, message)
        self.retry_after = retry_after


class ServiceUnavailableError(HelpdeskAPIError):
    """503 Service Unavailable: Simulated transient server failure."""
    pass


def is_transient_error(exception: BaseException) -> bool:
    """Predicate to determine if an error should trigger a tenacity retry."""
    if isinstance(exception, ServiceUnavailableError):
        return True
    if isinstance(exception, (httpx.ConnectError, httpx.ReadTimeout, httpx.NetworkError)):
        return True
    return False


class HelpdeskClient:
    """Robust client for interacting with the Roosterly Helpdesk API."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        email: Optional[str] = None,
        rate_limit: float = REQUEST_RATE_LIMIT
    ):
        self.base_url = (base_url or HELPDESK_BASE_URL).rstrip("/")
        self.api_key = api_key or HELPDESK_API_KEY
        self.email = email or CANDIDATE_EMAIL
        # Minimum time between requests to stay under 5 req/s (e.g. 1 / 4.5 = 0.222s)
        self.min_interval = 1.0 / rate_limit if rate_limit > 0 else 0.22
        self._last_request_time = 0.0

    def _headers(self) -> Dict[str, str]:
        """Constructs required authorization and candidate identification headers."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "X-Candidate-Email": self.email,
            "Content-Type": "application/json"
        }

    def _rate_limit_throttle(self) -> None:
        """Enforces client-side rate limiting to avoid triggering 429."""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self.min_interval:
            sleep_needed = self.min_interval - elapsed
            time.sleep(sleep_needed)
        self._last_request_time = time.time()

    def _send_request(
        self, 
        method: str, 
        endpoint: str, 
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None
    ) -> httpx.Response:
        """
        Executes a single HTTP request with rate limiting and status code dispatch.
        """
        self._rate_limit_throttle()
        url = f"{self.base_url}{endpoint}"

        with httpx.Client(timeout=15.0) as client:
            try:
                response = client.request(
                    method=method,
                    url=url,
                    headers=self._headers(),
                    params=params,
                    json=json_data
                )
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.NetworkError) as e:
                logger.warning("Network issue connecting to %s: %s", url, e)
                raise ServiceUnavailableError(503, f"Network transport error: {e}")

        # Check response status
        if response.status_code == 503:
            logger.warning("Helpdesk API returned 503 Service Unavailable for %s", endpoint)
            raise ServiceUnavailableError(503, "Service temporarily unavailable. Retryable.")

        if response.status_code == 429:
            retry_after_str = response.headers.get("Retry-After", "1.0")
            try:
                retry_after = float(retry_after_str)
            except ValueError:
                retry_after = 1.0
            logger.warning("Helpdesk API rate limit (429) hit. Retry-After: %.2fs", retry_after)
            time.sleep(retry_after)
            raise RateLimitError(retry_after, "Rate limit exceeded.")

        if response.status_code == 409:
            # Ticket was already handled - DO NOT retry
            logger.warning("Helpdesk API 409 Conflict: Ticket was already handled.")
            raise TicketAlreadyHandledError(409, "Ticket already handled.")

        if response.is_error:
            try:
                err_body = response.json()
            except Exception:
                err_body = {"raw": response.text}
            raise HelpdeskAPIError(
                response.status_code, 
                f"HTTP {response.status_code}: {response.text}",
                details=err_body
            )

        return response

    @retry(
        retry=retry_if_exception(is_transient_error),
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential_jitter(initial=RETRY_INITIAL_DELAY, max=4.0),
        before_sleep=before_sleep_log(logger, logging.WARNING)
    )
    def _execute_with_retry(
        self, 
        method: str, 
        endpoint: str, 
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Wraps request execution with tenacity exponential backoff for transient 503s."""
        # Loop for handling 429 specifically if caught
        max_429_retries = 3
        for attempt in range(max_429_retries + 1):
            try:
                response = self._send_request(method, endpoint, params, json_data)
                return response.json() if response.content else {}
            except RateLimitError as rle:
                if attempt == max_429_retries:
                    raise
                # Already slept in _send_request, retry next attempt
                continue

    # Public Endpoints
    def get_status(self) -> Dict[str, Any]:
        """GET /status: Returns mode and counts for open and handled tickets."""
        return self._execute_with_retry("GET", "/status")

    def get_examples(self) -> List[Dict[str, Any]]:
        """GET /examples: Returns 10 labelled reference examples with reasoning."""
        data = self._execute_with_retry("GET", "/examples")
        if isinstance(data, list):
            return data
        return data.get("examples", [])

    def reset_practice(self) -> Dict[str, Any]:
        """POST /practice/reset: Re-opens all practice tickets for a fresh run."""
        return self._execute_with_retry("POST", "/practice/reset")

    def get_ticket(self, ticket_id: str) -> Dict[str, Any]:
        """GET /tickets/{id}: Returns ticket details and handling status."""
        return self._execute_with_retry("GET", f"/tickets/{ticket_id}")

    def iter_open_tickets(self, limit: int = 10) -> Iterator[Dict[str, Any]]:
        """
        Paginates through all open tickets using cursor pagination.
        Yields tickets one by one until next_cursor is null.
        """
        cursor: Optional[str] = None
        while True:
            params: Dict[str, Any] = {
                "status": "open",
                "limit": limit
            }
            if cursor:
                params["cursor"] = cursor

            data = self._execute_with_retry("GET", "/tickets", params=params)
            tickets = data.get("tickets", [])
            for ticket in tickets:
                yield ticket

            cursor = data.get("next_cursor")
            if not cursor or not tickets:
                break

    def post_reply(self, ticket_id: str, decision_payload: Dict[str, Any]) -> Dict[str, Any]:
        """POST /tickets/{id}/reply: Sends draft answer in customer's language."""
        return self._execute_with_retry("POST", f"/tickets/{ticket_id}/reply", json_data=decision_payload)

    def post_handoff(self, ticket_id: str, decision_payload: Dict[str, Any]) -> Dict[str, Any]:
        """POST /tickets/{id}/handoff: Hands off ticket to human support with English note."""
        return self._execute_with_retry("POST", f"/tickets/{ticket_id}/handoff", json_data=decision_payload)

    def post_close(self, ticket_id: str, decision_payload: Dict[str, Any]) -> Dict[str, Any]:
        """POST /tickets/{id}/close: Closes empty or spam tickets."""
        return self._execute_with_retry("POST", f"/tickets/{ticket_id}/close", json_data=decision_payload)
