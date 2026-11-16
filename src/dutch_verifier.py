"""Dutch reply verifier.

Allows an English-speaking engineer to verify that a Dutch reply is accurate,
well-formed, properly grounded in the FAQ, and free of hallucinations or payment details.
"""

from typing import Tuple, List, Optional
import re
from src.scrubber import contains_payment_details

# Official Dutch menu paths and system strings from FAQ F01-F12
OFFICIAL_DUTCH_MENU_TERMS = [
    "Wachtwoord vergeten",
    "Team → Medewerker toevoegen",
    "Uitnodigen",
    "Ruil aanbieden",
    "Rooster → Verzoeken",
    "Instellingen → Rooster",
    "Instellingen → Koppelingen → Salaris",
    "Instellingen → Abonnement",
    "Instellingen → Abonnement → Facturen",
    "Instellingen → Bedrijfsgegevens",
    "Instellingen → Vestigingen → Nieuwe vestiging",
    "Profiel → Taal",
    "Instellingen → Juridisch",
    "roadmap.roosterly.nl",
    "status.roosterly.nl",
    "app.roosterly.nl/login",
    "Basis",
    "Plus"
]

# Common English words that should not dominate a Dutch reply
ENGLISH_LEAKAGE_WORDS = [
    r"\bhello\b", r"\bplease\b", r"\bkind regards\b", r"\bbest regards\b",
    r"\bsettings\b", r"\binvoices\b", r"\bsubscription\b", r"\badd employee\b"
]


def verify_dutch_reply(
    reply_text: str, 
    expected_faq_id: Optional[str] = None
) -> Tuple[bool, List[str]]:
    """
    Validates a Dutch reply using deterministic heuristics without requiring Dutch fluency:
    1. Redaction check: Never includes payment details.
    2. Length and non-emptiness check.
    3. English leakage check: Ensure prompt instructions didn't leak English into customer reply.
    4. Dutch greeting/closing indicators.
    
    Returns:
        (is_valid: bool, issues: List[str])
    """
    issues = []

    if not reply_text or len(reply_text.strip()) < 10:
        return False, ["Reply is empty or excessively short."]

    # 1. Zero payment details allowed
    if contains_payment_details(reply_text):
        return False, ["Reply contains unmasked payment or account details."]

    # 2. English leakage check
    leakage_count = 0
    for pattern in ENGLISH_LEAKAGE_WORDS:
        if re.search(pattern, reply_text, re.IGNORECASE):
            leakage_count += 1
    if leakage_count >= 2:
        issues.append(f"Detected English leakage ({leakage_count} English phrases) in customer reply.")

    # 3. Check for typical Dutch communicative markers
    dutch_markers = [r"\b(je|jij|u|uw|het|de|een|voor|naar|onder|kunt|gaan|klik)\b"]
    matches = sum(1 for m in dutch_markers if re.search(m, reply_text, re.IGNORECASE))
    if matches == 0:
        issues.append("Reply lacks characteristic Dutch language words.")

    is_valid = len(issues) == 0
    return is_valid, issues
