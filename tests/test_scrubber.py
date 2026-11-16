"""Unit tests for PCI/PII scrubber."""

import sys
from pathlib import Path

# Add project root to path so tests can run directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from src.scrubber import scrub_payment_details, contains_payment_details


def test_scrub_dutch_iban():
    raw = "Stort het geld a.u.b. terug naar NL91 ABNA 0417 1643 00."
    scrubbed, was_modified = scrub_payment_details(raw)
    assert was_modified is True
    assert "NL91" not in scrubbed
    assert "[REDACTED_IBAN]" in scrubbed
    assert "terug naar [REDACTED_IBAN]." in scrubbed


def test_scrub_credit_card():
    raw = "Mijn creditcardnummer is 4532 1234 5678 9012 met code cvc: 123."
    scrubbed, was_modified = scrub_payment_details(raw)
    assert was_modified is True
    assert "4532" not in scrubbed
    assert "[REDACTED_PAYMENT_CARD]" in scrubbed
    assert "[REDACTED_CVV]" in scrubbed


def test_clean_text_unchanged():
    raw = "Hoe voeg ik een nieuwe medewerker toe in het Basis pakket?"
    scrubbed, was_modified = scrub_payment_details(raw)
    assert was_modified is False
    assert scrubbed == raw
    assert contains_payment_details(raw) is False
