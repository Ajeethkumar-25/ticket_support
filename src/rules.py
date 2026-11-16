"""Roosterly Help Centre (FAQ) knowledge base and mandatory escalation rules.

Source: faq.md
"""

from typing import Optional, NamedTuple
import re

FAQ_KNOWLEDGE_BASE = """
# Roosterly Help Centre (FAQ)

F01 · Forgotten password
Go to app.roosterly.nl/login, click "Wachtwoord vergeten" (Forgot password) and enter your email address. The reset link is valid for 60 minutes. No email within 10 minutes? Check your spam folder.

F02 · Adding a new employee
Managers go to Team → Medewerker toevoegen (Add employee), enter name, email address and contract hours, and click Uitnodigen (Invite). The employee gets an email to install the app. You only pay for active employees.

F03 · Swapping shifts
Employees open the shift in the app and tap "Ruil aanbieden" (Offer swap). Colleagues with the same role can accept the swap. The manager approves it under Rooster → Verzoeken (Rota → Requests). Manager approval is on by default; you can turn it off under Instellingen → Rooster (Settings → Rota).

F04 · Export to payroll
Roosterly exports approved hours to Nmbrs, Loket.nl and AFAS, or as a CSV file. Set this up under Instellingen → Koppelingen → Salaris (Settings → Integrations → Payroll). Exports run per pay period (week, four weeks or month). The Nmbrs, Loket.nl and AFAS integrations are part of the Plus plan.

F05 · Plans and prices
Basis: €4 per active employee per month, one location. Plus: €6 per active employee per month, unlimited locations, API access and the payroll integrations. Prices exclude VAT. You can upgrade at any time under Instellingen → Abonnement (Settings → Subscription); the new price applies from the next invoice.

F06 · Invoices
Invoices are emailed on the 1st of every month and can be downloaded under Instellingen → Abonnement → Facturen (Settings → Subscription → Invoices). Change the company name, address or VAT number for future invoices under Instellingen → Bedrijfsgegevens (Settings → Company details).

F07 · Multiple locations
Locations are part of the Plus plan. Add one under Instellingen → Vestigingen → Nieuwe vestiging (Settings → Locations → New location). Employees can be linked to more than one location.

F08 · Languages
The web app and the mobile app are available in Dutch, English and German. Each user chooses their own language under Profiel → Taal (Profile → Language).

F09 · Where your data is stored
All data is stored in the EU (Frankfurt, Germany) and processed under a data processing agreement, which you can download under Instellingen → Juridisch (Settings → Legal).

F10 · Ideas and feature requests
We read every idea. Feature requests go on our public roadmap at roadmap.roosterly.nl, where you can vote on ideas. We cannot promise a delivery date for individual requests.

F11 · Outages and maintenance
See status.roosterly.nl for current outages and planned maintenance.

F12 · Mobile app requirements
The app works on iOS 16 and later and Android 10 and later. Clocking in with location requires location permission for the app.
""".strip()


class EscalationDecision(NamedTuple):
    category: str
    priority: str
    action: str
    reason: str
    handoff_note: str


# Regex rules for deterministic client-mandated escalations
# Client rules:
# 1. Refunds or disputed charges
# 2. Cancellations and contract changes
# 3. Personal data requests (GDPR / AVG)
# 4. Security incidents
# 5. Legal threats
# 6. Customers threatening to leave

REFUND_REGEX = re.compile(
    r"\b(terugbetaling|terugbetalen|geld terug|terugstorten|restitutie|refund|chargeback|dispute|gecompenseerd)\b",
    re.IGNORECASE
)

CANCELLATION_REGEX = re.compile(
    r"\b(opzeggen|opzegging|abonnement stopzetten|beëindigen van ons abonnement|contract beëindigen|cancel subscription|terminate contract)\b",
    re.IGNORECASE
)

GDPR_REGEX = re.compile(
    r"\b(avg|gdpr|persoonsgegevens verwijderen|recht op vergetelheid|data removal|delete my data|privacyverzoek)\b",
    re.IGNORECASE
)

SECURITY_REGEX = re.compile(
    r"\b(datalek|beveiligingsincident|gehackt|veiligheidslek|security breach|data breach|vulnerability)\b",
    re.IGNORECASE
)

LEGAL_REGEX = re.compile(
    r"\b(advocaat|rechtszaak|juridische stappen|dagvaarding|in gebreke|legal action|lawyer|lawsuit)\b",
    re.IGNORECASE
)

CHURN_REGEX = re.compile(
    r"\b(overstappen naar|klaar met roosterly|naar de concurrent|weggaan bij roosterly|switch to competitor|leaving roosterly)\b",
    re.IGNORECASE
)

SPAM_REGEX = re.compile(
    r"\b(casino|crypto|viagra|buy followers|fast money|seo service)\b",
    re.IGNORECASE
)


def check_deterministic_rules(subject: str, body: str) -> Optional[EscalationDecision]:
    """
    Evaluates customer subject and body against mandatory client rules.
    If a hard rule matches, returns an EscalationDecision immediately to guarantee safety.
    """
    combined = f"{subject} {body}".strip()

    # Empty or spam ticket
    if not combined or len(combined) < 4:
        return EscalationDecision(
            category="other",
            priority="P4",
            action="close",
            reason="Empty ticket. Closed automatically.",
            handoff_note=""
        )

    if SPAM_REGEX.search(combined):
        return EscalationDecision(
            category="other",
            priority="P4",
            action="close",
            reason="Spam detected. Closed automatically.",
            handoff_note=""
        )

    # 1. Security Incidents -> P1 handoff
    if SECURITY_REGEX.search(combined):
        return EscalationDecision(
            category="bug",
            priority="P1",
            action="handoff",
            reason="Possible security incident. Client rule: security incidents always go to a human.",
            handoff_note="Urgent security incident/breach reported by customer. Requires immediate investigation."
        )

    # 2. Legal Threats -> P1 handoff
    if LEGAL_REGEX.search(combined):
        return EscalationDecision(
            category="other",
            priority="P1",
            action="handoff",
            reason="Legal threat. Client rule: legal threats always go to a human.",
            handoff_note="Customer mentioning legal action or legal representation. Escalate to management/legal."
        )

    # 3. GDPR / AVG Requests -> P2 handoff (single customer data access/deletion)
    if GDPR_REGEX.search(combined):
        return EscalationDecision(
            category="other",
            priority="P2",
            action="handoff",
            reason="Personal data request (GDPR/AVG). Client rule: GDPR requests always go to a human.",
            handoff_note="Customer submitted a GDPR/AVG personal data inquiry. Process according to statutory guidelines."
        )

    # 4. Refunds or disputed charges -> P2 handoff
    if REFUND_REGEX.search(combined):
        return EscalationDecision(
            category="billing",
            priority="P2",
            action="handoff",
            reason="Refund request. Client rule: refunds always go to a human.",
            handoff_note="Customer is requesting a refund or disputing a charge. Please review billing history."
        )

    # 5. Cancellations and contract changes -> P2 handoff
    if CANCELLATION_REGEX.search(combined):
        return EscalationDecision(
            category="billing",
            priority="P2",
            action="handoff",
            reason="Cancellation / contract change request. Client rule: cancellations always go to a human.",
            handoff_note="Customer wants to cancel subscription or modify contract terms. Review account status."
        )

    # 6. Customer threatening to leave -> P2 handoff
    if CHURN_REGEX.search(combined):
        return EscalationDecision(
            category="other",
            priority="P2",
            action="handoff",
            reason="Customer threatening to leave. Client rule: churn risks always go to a human.",
            handoff_note="Customer is threatening to leave or switch to a competitor. Retention outreach recommended."
        )

    return None
