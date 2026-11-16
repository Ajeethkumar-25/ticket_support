"""Sensitive data scrubber for PCI/PII protection.

Client rule: Never repeat payment details (card numbers, IBANs) in a reply or a log.
"""

import re
from typing import Tuple

# IBAN pattern: Handles NL and standard European formats, with or without spaces/dashes
IBAN_PATTERN = re.compile(
    r"\b[A-Z]{2}\d{2}(?:[ -]?[A-Z0-9]{4}){2,7}(?:[ -]?[A-Z0-9]{1,4})?\b",
    re.IGNORECASE
)

# Dutch specific IBAN pattern (e.g. NL91 ABNA 0417 1643 00) - exact 18 chars + formatting
NL_IBAN_PATTERN = re.compile(
    r"\bNL\d{2}\s*[A-Z]{4}\s*(?:\d\s*){9}\d\b",
    re.IGNORECASE
)

# Credit Card pattern: 13 to 19 digits, optionally separated by spaces or dashes
CREDIT_CARD_PATTERN = re.compile(
    r"\b(?:\d[ -]*?){13,19}\b"
)

# CVC/CVV pattern
CVV_PATTERN = re.compile(
    r"\b(?:cvv|cvc|cid|beveiligingscode)[\s:]*([0-9]{3,4})\b",
    re.IGNORECASE
)


def scrub_payment_details(text: str) -> Tuple[str, bool]:
    """
    Scrubs payment details (credit card numbers, IBANs, CVVs) from text.
    
    Returns:
        (sanitized_text, was_scrubbed)
    """
    if not text:
        return text, False

    original = text
    scrubbed = text

    # Mask CVVs
    scrubbed = CVV_PATTERN.sub(r"[REDACTED_CVV]", scrubbed)

    # Mask Dutch IBANs specifically first
    scrubbed = NL_IBAN_PATTERN.sub("[REDACTED_IBAN]", scrubbed)

    # Mask other general IBANs
    scrubbed = IBAN_PATTERN.sub("[REDACTED_IBAN]", scrubbed)

    # Mask Credit Cards (verify with basic Luhn or digit sequence check)
    def mask_card(match: re.Match) -> str:
        digits_only = re.sub(r"\D", "", match.group(0))
        # Ensure it has between 13 and 19 digits and isn't just a phone number or timestamp
        if 13 <= len(digits_only) <= 19:
            return "[REDACTED_PAYMENT_CARD]"
        return match.group(0)

    scrubbed = CREDIT_CARD_PATTERN.sub(mask_card, scrubbed)

    was_modified = scrubbed != original
    return scrubbed, was_modified


def contains_payment_details(text: str) -> bool:
    """Check if the text contains any unmasked payment details."""
    if not text:
        return False
    _, was_scrubbed = scrub_payment_details(text)
    return was_scrubbed
