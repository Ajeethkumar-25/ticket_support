"""Unit tests for the SupportTicketAgent pipeline (src/agent.py).

All external I/O (helpdesk client, LLM, state, logger) is mocked so tests
run offline without any network calls or file I/O.
"""

import pytest
from unittest.mock import MagicMock, patch, call
from src.agent import SupportTicketAgent
from src.client import TicketAlreadyHandledError
from src.llm_client import TicketTriageDecision


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_decision(**overrides):
    """Return a TicketTriageDecision with sane defaults, partially overridable."""
    defaults = dict(
        language="nl",
        category="question",
        priority="P4",
        action="reply",
        reason="Covered by FAQ F01.",
        draft_reply="Gebruik de knop 'Wachtwoord vergeten' op het inlogscherm.",
        handoff_note=None,
        confidence=0.95,
    )
    defaults.update(overrides)
    return TicketTriageDecision(**defaults)


def _make_ticket(ticket_id="T001", subject="Wachtwoord vergeten", body="Hoe reset ik mijn wachtwoord?"):
    return {"id": ticket_id, "subject": subject, "body": body, "customer_plan": "Basis"}


def _make_agent(state_handled=False, decision=None, decision_side_effect=None):
    """Return a SupportTicketAgent with all external dependencies mocked."""
    client = MagicMock()
    llm = MagicMock()
    state = MagicMock()
    logger = MagicMock()

    state.is_handled.return_value = state_handled

    if decision_side_effect:
        llm.triage_ticket.side_effect = decision_side_effect
    else:
        llm.triage_ticket.return_value = decision or _make_decision()

    return SupportTicketAgent(
        helpdesk_client=client,
        llm_client=llm,
        state_manager=state,
        ticket_logger=logger,
    )


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

class TestIdempotency:
    def test_already_handled_ticket_is_skipped(self):
        """If state says ticket is handled, skip without calling LLM or posting."""
        agent = _make_agent(state_handled=True)
        result = agent.process_ticket(_make_ticket())
        assert result["status"] == "skipped"
        agent.llm.triage_ticket.assert_not_called()
        agent.client.post_reply.assert_not_called()

    def test_409_from_server_is_recorded_in_state(self):
        """A 409 on posting means the server already has the decision — record it locally."""
        agent = _make_agent(state_handled=False)
        agent.client.post_reply.side_effect = TicketAlreadyHandledError(409, "dupe")
        result = agent.process_ticket(_make_ticket())
        assert result["status"] == "already_handled"
        agent.state.mark_handled.assert_called_once()


# ---------------------------------------------------------------------------
# Reply path
# ---------------------------------------------------------------------------

class TestReplyPath:
    def test_faq_question_produces_reply(self):
        agent = _make_agent(decision=_make_decision(action="reply"))
        result = agent.process_ticket(_make_ticket())
        assert result["status"] == "success"
        assert result["action"] == "reply"
        agent.client.post_reply.assert_called_once()
        agent.client.post_handoff.assert_not_called()

    def test_state_marked_after_successful_reply(self):
        agent = _make_agent(decision=_make_decision(action="reply"))
        agent.process_ticket(_make_ticket("T002"))
        agent.state.mark_handled.assert_called_once()
        args = agent.state.mark_handled.call_args[0]
        assert args[0] == "T002"
        assert args[1] == "reply"

    def test_failed_dutch_verification_falls_back_to_handoff(self):
        """If the Dutch verifier rejects the draft, agent must escalate to handoff."""
        agent = _make_agent(decision=_make_decision(action="reply", draft_reply="hello please settings invoices"))
        result = agent.process_ticket(_make_ticket())
        # The 'hello please settings invoices' has 2+ English leakage words
        assert result["status"] == "success"
        assert result["action"] == "handoff"
        agent.client.post_handoff.assert_called_once()
        agent.client.post_reply.assert_not_called()


# ---------------------------------------------------------------------------
# Handoff path
# ---------------------------------------------------------------------------

class TestHandoffPath:
    def test_refund_ticket_produces_handoff(self):
        """Deterministic rule for refund — LLM should not even be called."""
        agent = _make_agent()
        ticket = _make_ticket(
            subject="Terugbetaling",
            body="Wij willen een terugbetaling voor de afgelopen maand."
        )
        result = agent.process_ticket(ticket)
        assert result["action"] == "handoff"
        agent.llm.triage_ticket.assert_not_called()
        agent.client.post_handoff.assert_called_once()

    def test_gdpr_ticket_produces_p2_handoff(self):
        """GDPR access request must be P2, not P1 (corrected per live labels)."""
        agent = _make_agent()
        ticket = _make_ticket(
            subject="AVG inzageverzoek",
            body="Graag alle persoonsgegevens inzien conform AVG."
        )
        agent.process_ticket(ticket)
        post_kwargs = agent.client.post_handoff.call_args
        payload = post_kwargs[0][1]  # second positional arg is the payload
        assert payload["priority"] == "P2"

    def test_security_incident_produces_p1_handoff(self):
        """Data breach / salarisgegevens must be P1."""
        agent = _make_agent()
        ticket = _make_ticket(
            subject="Datalek",
            body="Ik zie salarisgegevens van een ander restaurant!"
        )
        agent.process_ticket(ticket)
        payload = agent.client.post_handoff.call_args[0][1]
        assert payload["priority"] == "P1"

    def test_llm_handoff_decision_respected(self):
        """LLM decides handoff (non-deterministic path) — must call post_handoff."""
        decision = _make_decision(
            action="handoff",
            handoff_note="Customer reports a bug not in FAQ.",
            draft_reply=None,
            category="bug",
            priority="P3",
        )
        agent = _make_agent(decision=decision)
        result = agent.process_ticket(_make_ticket(subject="Bug", body="De app werkt niet goed."))
        assert result["action"] == "handoff"
        agent.client.post_handoff.assert_called_once()


# ---------------------------------------------------------------------------
# Close path (spam)
# ---------------------------------------------------------------------------

class TestClosePath:
    def test_spam_ticket_is_closed(self):
        agent = _make_agent()
        ticket = _make_ticket(subject="Win crypto now", body="Free casino bonus claim here")
        result = agent.process_ticket(ticket)
        assert result["action"] == "close"
        agent.client.post_close.assert_called_once()
        agent.llm.triage_ticket.assert_not_called()


# ---------------------------------------------------------------------------
# PII scrubbing
# ---------------------------------------------------------------------------

class TestPIIScrubbing:
    def test_iban_in_ticket_body_is_scrubbed_before_llm(self):
        """IBAN in the body must be scrubbed; raw IBAN must NOT reach the LLM."""
        agent = _make_agent(decision=_make_decision(action="reply"))
        ticket = _make_ticket(
            subject="Factuur",
            body="Stort het geld naar NL91 ABNA 0417 1643 00 terug."
        )
        agent.process_ticket(ticket)
        # Inspect what body was passed to triage_ticket
        call_kwargs = agent.llm.triage_ticket.call_args[1]
        assert "NL91" not in call_kwargs.get("body", ""), \
            "Raw IBAN must be scrubbed before it reaches the LLM"
        assert "[REDACTED_IBAN]" in call_kwargs.get("body", "")


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

class TestLogging:
    def test_one_log_line_per_successful_ticket(self):
        agent = _make_agent(decision=_make_decision(action="reply"))
        agent.process_ticket(_make_ticket())
        agent.logger.log_ticket.assert_called_once()

    def test_skipped_ticket_produces_no_log(self):
        """Already-handled tickets must not write a log line."""
        agent = _make_agent(state_handled=True)
        agent.process_ticket(_make_ticket())
        agent.logger.log_ticket.assert_not_called()
