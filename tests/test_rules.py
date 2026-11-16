"""Unit tests for deterministic client rules and mandatory escalations."""

import pytest
from src.rules import check_deterministic_rules


def test_refund_escalation_rule():
    match = check_deterministic_rules(
        "Terugbetaling augustus", 
        "Kunnen we die maand terugkrijgen wegens verbouwing?"
    )
    assert match is not None
    assert match.action == "handoff"
    assert match.category == "billing"
    assert match.priority == "P2"


def test_cancellation_escalation_rule():
    match = check_deterministic_rules(
        "Abonnement opzeggen",
        "Wij stoppen met ons restaurant en willen het contract opzeggen."
    )
    assert match is not None
    assert match.action == "handoff"
    assert match.category == "billing"
    assert match.priority == "P2"


def test_gdpr_escalation_rule():
    match = check_deterministic_rules(
        "AVG verzoek",
        "Graag alle persoonsgegevens verwijderen."
    )
    assert match is not None
    assert match.action == "handoff"
    assert match.category == "other"
    assert match.priority == "P1"


def test_security_incident_rule():
    match = check_deterministic_rules(
        "Datalek geconstateerd",
        "Ik zie salarisgegevens van een ander restaurant!"
    )
    assert match is not None
    assert match.action == "handoff"
    assert match.category == "bug"
    assert match.priority == "P1"


def test_spam_detection():
    match = check_deterministic_rules(
        "Win crypto",
        "Free casino bonus claim here"
    )
    assert match is not None
    assert match.action == "close"
    assert match.category == "other"
    assert match.priority == "P4"


def test_regular_faq_not_intercepted():
    # Regular FAQ question should pass through to LLM
    match = check_deterministic_rules(
        "Medewerker toevoegen",
        "Hoe voeg ik een nieuwe parttimer toe?"
    )
    assert match is None
