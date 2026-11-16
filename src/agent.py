"""Roosterly Support Ticket Agent Orchestrator.

Implements the complete processing loop:
1. Paginates through open tickets.
2. Applies idempotency checks (skips tickets handled in local state).
3. Evaluates deterministic escalation rules (refunds, GDPR, cancellations, security).
4. Invokes Groq with Qwen for triage and reply/handoff generation.
5. Verifies Dutch reply quality and grounding.
6. Posts decisions to the Helpdesk API with robust error handling.
7. Logs sanitized 1-line-per-ticket entries to logs/tickets.log.
"""

from typing import Dict, Any, Optional
import logging
import sys

from src.client import HelpdeskClient, TicketAlreadyHandledError, HelpdeskAPIError
from src.llm_client import LLMClient, TicketTriageDecision
from src.rules import check_deterministic_rules
from src.dutch_verifier import verify_dutch_reply
from src.state import StateManager
from src.logger import TicketLogger
from src.scrubber import scrub_payment_details

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("helpdesk_agent")


class SupportTicketAgent:
    """Production support agent for Roosterly."""

    def __init__(
        self,
        helpdesk_client: Optional[HelpdeskClient] = None,
        llm_client: Optional[LLMClient] = None,
        state_manager: Optional[StateManager] = None,
        ticket_logger: Optional[TicketLogger] = None
    ):
        self.client = helpdesk_client or HelpdeskClient()
        self.llm = llm_client or LLMClient()
        self.state = state_manager or StateManager()
        self.logger = ticket_logger or TicketLogger()

    def process_ticket(self, ticket: Dict[str, Any]) -> Dict[str, Any]:
        """Processes a single ticket from ingestion to resolution."""
        ticket_id = ticket["id"]
        subject = ticket.get("subject", "")
        body = ticket.get("body", "")
        customer_plan = ticket.get("customer_plan", "Basis")

        # 1. Idempotency check: Already handled locally?
        if self.state.is_handled(ticket_id):
            logger.info("Ticket %s already marked as handled in local state. Skipping.", ticket_id)
            return {"status": "skipped", "reason": "already_handled"}

        # 2. Scrub payment details from input text
        clean_subject, _ = scrub_payment_details(subject)
        clean_body, _ = scrub_payment_details(body)

        # 3. Check deterministic client escalation rules first (Refund, GDPR, Cancel, Security, Churn, Spam)
        deterministic_match = check_deterministic_rules(clean_subject, clean_body)

        if deterministic_match:
            action = deterministic_match.action
            category = deterministic_match.category
            priority = deterministic_match.priority
            reason = deterministic_match.reason
            confidence = 1.0
            language = "nl"  # Default to Dutch for customer context

            payload = {
                "language": language,
                "category": category,
                "priority": priority,
                "reason": reason,
                "confidence": confidence
            }
            if action == "handoff":
                payload["handoff_note"] = deterministic_match.handoff_note
            elif action == "reply":
                payload["draft_reply"] = ""
        else:
            # 4. Invoke LLM structured triage
            decision = self.llm.triage_ticket(
                subject=clean_subject,
                body=clean_body,
                customer_plan=customer_plan
            )
            action = decision.action
            category = decision.category
            priority = decision.priority
            reason = decision.reason
            confidence = decision.confidence
            language = decision.language

            payload = {
                "language": language,
                "category": category,
                "priority": priority,
                "reason": reason,
                "confidence": confidence
            }

            if action == "reply":
                draft = decision.draft_reply or ""
                # 5. Verify Dutch reply quality & grounding
                is_valid, issues = verify_dutch_reply(draft)
                if not is_valid:
                    logger.warning(
                        "Ticket %s Dutch reply failed verification (%s). Falling back safely to human handoff.",
                        ticket_id, ", ".join(issues)
                    )
                    action = "handoff"
                    payload["category"] = category
                    payload["priority"] = priority
                    payload["reason"] = f"Automated draft verification flagged issue: {issues[0]}. Escapated to human."
                    payload["handoff_note"] = f"Customer asked: '{clean_subject}'. Draft reply failed quality checks. Please assist."
                else:
                    payload["draft_reply"] = draft

            elif action == "handoff":
                payload["handoff_note"] = decision.handoff_note or f"Customer inquiry requires support agent review."

        # 6. Post decision to Helpdesk API
        try:
            if action == "reply":
                res = self.client.post_reply(ticket_id, payload)
            elif action == "handoff":
                res = self.client.post_handoff(ticket_id, payload)
            elif action == "close":
                res = self.client.post_close(ticket_id, payload)
            else:
                raise ValueError(f"Unknown action: {action}")

        except TicketAlreadyHandledError:
            logger.warning("Ticket %s was already handled on server (409 Conflict). Recording in local state.", ticket_id)
            self.state.mark_handled(ticket_id, action, reason, category, priority)
            return {"status": "already_handled", "ticket_id": ticket_id}

        # 7. Commit to local state for crash recovery
        self.state.mark_handled(ticket_id, action, reason, category, priority)

        # 8. Log single sanitized line
        preview = payload.get("draft_reply") or payload.get("handoff_note") or ""
        self.logger.log_ticket(
            ticket_id=ticket_id,
            language=language,
            category=category,
            priority=priority,
            action=action,
            reason=reason,
            confidence=confidence,
            note_or_reply_preview=preview
        )

        logger.info(
            "Ticket %s processed -> Action: %s | Cat: %s | Pri: %s | Lang: %s",
            ticket_id, action, category, priority, language
        )
        return {"status": "success", "ticket_id": ticket_id, "action": action}

    def run(self) -> Dict[str, int]:
        """Runs the agent through all open tickets."""
        logger.info("Starting Roosterly Support Ticket Agent run...")
        stats = {"processed": 0, "reply": 0, "handoff": 0, "close": 0, "skipped": 0}

        try:
            status = self.client.get_status()
            logger.info("Current Helpdesk Status: %s", status)
        except Exception as e:
            logger.warning("Could not fetch /status initially: %s", e)

        for ticket in self.client.iter_open_tickets(limit=10):
            result = self.process_ticket(ticket)
            if result.get("status") == "success":
                stats["processed"] += 1
                action = result.get("action", "unknown")
                if action in stats:
                    stats[action] += 1
            elif result.get("status") in ("skipped", "already_handled"):
                stats["skipped"] += 1

        logger.info(
            "Agent Run Completed. Total: %d | Replies: %d | Handoffs: %d | Closes: %d | Skipped: %d",
            stats["processed"], stats["reply"], stats["handoff"], stats["close"], stats["skipped"]
        )
        return stats
