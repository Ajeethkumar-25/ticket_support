"""Local Mock Helpdesk Server for offline testing and verification.

Accurately simulates:
- Authentication & header checks
- Status, examples, and cursor-paginated tickets
- Decision endpoints: /reply, /handoff, /close
- Practice reset endpoint: /practice/reset
- Fault injection:
  - Random 503s (~5% of requests)
  - 429 when rate exceeds 5 req/s
  - 409 when handling an already-handled ticket
"""

from typing import Dict, Any, List
import json
import time
import random
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import threading

MOCK_EXAMPLES = [
    {
        "id": "E01",
        "subject": "Wachtwoord vergeten",
        "body": "Hallo, ik kan niet meer inloggen. Hoe reset ik mijn wachtwoord?",
        "label": {
            "language": "nl",
            "category": "question",
            "priority": "P4",
            "action": "reply",
            "reason": "Covered by FAQ F01. Low priority account access how-to."
        }
    },
    {
        "id": "E02",
        "subject": "Medewerker uitnodigen",
        "body": "Beste support, hoe voeg ik een nieuwe parttimer toe aan ons rooster?",
        "label": {
            "language": "nl",
            "category": "question",
            "priority": "P4",
            "action": "reply",
            "reason": "Covered by FAQ F02. How-to question."
        }
    },
    {
        "id": "E03",
        "subject": "Terugbetaling",
        "body": "We waren in augustus dicht wegens verbouwing. Kunnen we die maand terugkrijgen?",
        "label": {
            "language": "nl",
            "category": "billing",
            "priority": "P2",
            "action": "handoff",
            "reason": "Refund request. Client rule: refunds always go to a human."
        }
    },
    {
        "id": "E04",
        "subject": "Diensten ruilen",
        "body": "Kan een medewerker zelf zijn dienst ruilen met een collega in de app?",
        "label": {
            "language": "nl",
            "category": "question",
            "priority": "P4",
            "action": "reply",
            "reason": "Covered by FAQ F03. How-to shift swapping."
        }
    },
    {
        "id": "E05",
        "subject": "Koppeling met Nmbrs",
        "body": "Wij willen graag onze uren exporteren naar Nmbrs. Hoe stellen we dit in?",
        "label": {
            "language": "nl",
            "category": "question",
            "priority": "P4",
            "action": "reply",
            "reason": "Covered by FAQ F04. Export to payroll integrations."
        }
    },
    {
        "id": "E06",
        "subject": "Abonnement opzeggen",
        "body": "Wij stoppen met ons restaurant per 1 december en willen het contract opzeggen.",
        "label": {
            "language": "nl",
            "category": "billing",
            "priority": "P2",
            "action": "handoff",
            "reason": "Cancellation request. Client rule: cancellations always go to a human."
        }
    },
    {
        "id": "E07",
        "subject": "AVG / Verwijderen persoonsgegevens",
        "body": "Graag ontvangen wij bevestiging dat alle gegevens van oud-medewerker Jansen zijn gewist.",
        "label": {
            "language": "nl",
            "category": "other",
            "priority": "P1",
            "action": "handoff",
            "reason": "GDPR / AVG request. Legal compliance requires human handling."
        }
    },
    {
        "id": "E08",
        "subject": "Datalek / beveiliging",
        "body": "Ik zie opeens de salarisgegevens van een ander restaurant in ons account!",
        "label": {
            "language": "nl",
            "category": "bug",
            "priority": "P1",
            "action": "handoff",
            "reason": "Possible security incident. Mandatory immediate human escalation."
        }
    },
    {
        "id": "E09",
        "subject": "Prijzen Plus abonnement",
        "body": "Wat kost het Plus pakket precies als we 15 medewerkers hebben?",
        "label": {
            "language": "nl",
            "category": "question",
            "priority": "P4",
            "action": "reply",
            "reason": "Covered by FAQ F05. Pricing information."
        }
    },
    {
        "id": "E10",
        "subject": "Spam / Win free prizes",
        "body": "Claim your free casino crypto bonus now at http://spam.example.com",
        "label": {
            "language": "en",
            "category": "other",
            "priority": "P4",
            "action": "close",
            "reason": "Spam ticket. Close without action."
        }
    }
]

# Generate 30 practice tickets
SAMPLE_TICKETS = [
    {
        "id": f"T{i:03d}",
        "received_at": f"2026-10-{5 + (i % 20):02d}T09:{i % 60:02d}:00+00:00",
        "channel": "email",
        "customer_plan": "Plus" if i % 2 == 0 else "Basis",
        "subject": subject,
        "body": body,
        "status": "open",
        "handled_with": None
    }
    for i, (subject, body) in enumerate([
        ("Wachtwoord reset lukt niet", "Ik klik op wachtwoord vergeten maar ontvang geen mail. Mijn email is test@roosterly.nl."),
        ("Medewerker toevoegen", "Goedemorgen, waar vind ik de knop om een nieuwe kok toe te voegen?"),
        ("Factuur downloaden", "Waar kan ik de factuur van vorige maand inzien en downloaden?"),
        ("Terugbetaling abonnementskosten", "We zijn per ongeluk dubbel gefactureerd voor oktober, graag 50 euro terugstorten op IBAN NL91ABNA0417164300."),
        ("Ruilen van diensten", "Hoe zet ik manager goedkeuring uit voor diensten ruilen?"),
        ("Salaris koppeling AFAS", "Ondersteunt Roosterly koppeling met AFAS voor urenexport?"),
        ("Abonnement opzeggen", "Wegens sluiting willen wij onze overeenkomst met Roosterly per direct beëindigen."),
        ("AVG verwijderingsverzoek", "Op grond van de AVG verzoek ik u alle gegevens van ons bedrijf direct te wissen."),
        ("Dringend: Systeem ligt eruit", "Niemand van onze 40 medewerkers kan vandaag inklokken! Graag met spoed oplossen!"),
        ("Locatie toevoegen", "Kunnen we een tweede filiaal toevoegen aan ons Basis account?"),
        ("Taal wijzigen naar Engels", "One of our managers only speaks English. How does he change the language in the app?"),
        ("Waar staat onze data?", "In welk datacenter en land wordt onze roosterdata bewaard?"),
        ("Idee: vingerafdruk inklokken", "Zou het mogelijk zijn om biometrisch in te klokken via de app?"),
        ("Onderhoud vanavond?", "Staat er vanavond gepland onderhoud op de servers?"),
        ("Android versie vereisten", "Welke minimale Android versie is nodig voor de mobiele app?"),
        ("Foutmelding bij inloggen", "Ik krijg steeds een 500 server foutmelding als ik wil inloggen op app.roosterly.nl."),
        ("Creditcard wijzigen", "Hierbij ons nieuwe kaartnummer 4532 1234 5678 9012 vervaldatum 12/28 om te incasseren."),
        ("Juridische stappen wegens contractbreuk", "Als dit probleem niet binnen 24 uur is opgelost schakel ik mijn advocaat in."),
        ("Casino promo", "Free spins casino win money now!"),
        ("Dienst ruilen lukt niet", "Mijn collega en ik hebben dezelfde rol, maar hij ziet mijn ruilverzoek niet in de app."),
        ("Uren export CSV", "Kunnen we uren ook downloaden als plat CSV bestand in plaats van koppeling?"),
        ("Wat kost Roosterly Basis?", "Goedemiddag, wat zijn de maandelijkse kosten per medewerker voor de Basis versie?"),
        ("Klant dreigt over te stappen", "Als deze bug niet snel gefixt wordt stappen we over naar Shiftbase!"),
        ("Nieuwe vestiging openen", "Hoe activeer ik vestigingen in het Plus pakket?"),
        ("Wachtwoord reset link verlopen", "De link in de mail geeft aan dat hij verlopen is. Hoe lang is deze geldig?"),
        ("App crasht op iOS 15", "De app sluit direct af op mijn iPhone met iOS 15. Hoe kan dit?"),
        ("Factuuradres wijzigen", "Ons restaurant is verhuisd, hoe pas ik het btw-nummer en factuuradres aan?"),
        ("Spam crypto", "Earn Bitcoin working from home click here"),
        ("AVG data verwerkersovereenkomst", "Waar kan ik de getekende verwerkersovereenkomst downloaden?"),
        ("Dankjewel voor de hulp", "Alles werkt weer naar wens, fijne dag gewenst!")
    ], start=1)
]


class MockHelpdeskHandler(BaseHTTPRequestHandler):
    tickets_state = {t["id"]: dict(t) for t in SAMPLE_TICKETS}
    request_timestamps: List[float] = []
    simulate_errors = True

    def _check_rate_limit(self) -> bool:
        now = time.time()
        self.request_timestamps = [t for t in self.request_timestamps if now - t < 1.0]
        self.request_timestamps.append(now)
        if len(self.request_timestamps) > 6:
            return False
        return True

    def _send_json(self, status_code: int, data: Any, extra_headers: Dict[str, str] = None):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def do_GET(self):
        # Header check
        auth = self.headers.get("Authorization", "")
        email = self.headers.get("X-Candidate-Email", "")
        if not auth.startswith("Bearer "):
            self._send_json(401, {"error": "unauthorized", "message": "Missing Bearer token"})
            return
        if not email:
            self._send_json(400, {"error": "missing_email", "message": "Missing X-Candidate-Email header"})
            return

        # Rate limit simulation
        if self.simulate_errors and not self._check_rate_limit():
            self._send_json(429, {"error": "rate_limited", "message": "Too many requests"}, {"Retry-After": "0.5"})
            return

        # Random 503 simulation (~5% chance)
        if self.simulate_errors and random.random() < 0.05:
            self._send_json(503, {"error": "service_unavailable", "message": "Temporary service failure"})
            return

        url = urlparse(self.path)
        path = url.path.rstrip("/")
        query = parse_qs(url.query)

        if path == "/status":
            open_count = sum(1 for t in self.tickets_state.values() if t["status"] == "open")
            handled_count = sum(1 for t in self.tickets_state.values() if t["status"] == "handled")
            self._send_json(200, {
                "mode": "practice",
                "open_tickets": open_count,
                "handled_tickets": handled_count,
                "total_tickets": len(self.tickets_state)
            })
            return

        if path == "/examples":
            self._send_json(200, MOCK_EXAMPLES)
            return

        if path == "/tickets":
            limit = int(query.get("limit", [10])[0])
            status_filter = query.get("status", ["open"])[0]
            cursor = query.get("cursor", [None])[0]

            filtered = [
                t for t in self.tickets_state.values()
                if status_filter == "all" or t["status"] == status_filter
            ]
            # Sort by ID
            filtered.sort(key=lambda x: x["id"])

            start_idx = 0
            if cursor:
                for idx, t in enumerate(filtered):
                    if t["id"] == cursor:
                        start_idx = idx + 1
                        break

            page = filtered[start_idx:start_idx + limit]
            next_cursor = page[-1]["id"] if len(page) == limit and (start_idx + limit < len(filtered)) else None

            self._send_json(200, {
                "tickets": page,
                "next_cursor": next_cursor
            })
            return

        if path.startswith("/tickets/"):
            ticket_id = path.split("/")[2]
            ticket = self.tickets_state.get(ticket_id)
            if not ticket:
                self._send_json(404, {"error": "not_found", "message": f"Ticket {ticket_id} not found"})
                return
            self._send_json(200, ticket)
            return

        self._send_json(404, {"error": "not_found", "message": f"Unknown path {path}"})

    def do_POST(self):
        auth = self.headers.get("Authorization", "")
        email = self.headers.get("X-Candidate-Email", "")
        if not auth.startswith("Bearer "):
            self._send_json(401, {"error": "unauthorized", "message": "Missing Bearer token"})
            return
        if not email:
            self._send_json(400, {"error": "missing_email", "message": "Missing X-Candidate-Email header"})
            return

        url = urlparse(self.path)
        path = url.path.rstrip("/")

        if path == "/practice/reset":
            for t in self.tickets_state.values():
                t["status"] = "open"
                t["handled_with"] = None
            self._send_json(200, {"message": "All practice tickets re-opened", "open_tickets": len(self.tickets_state)})
            return

        # Random 503 simulation (~5% chance)
        if self.simulate_errors and random.random() < 0.05:
            self._send_json(503, {"error": "service_unavailable", "message": "Temporary service failure"})
            return

        # Decision endpoints: /tickets/{id}/reply, /tickets/{id}/handoff, /tickets/{id}/close
        if path.startswith("/tickets/") and (path.endswith("/reply") or path.endswith("/handoff") or path.endswith("/close")):
            parts = path.split("/")
            ticket_id = parts[2]
            action = parts[3]

            ticket = self.tickets_state.get(ticket_id)
            if not ticket:
                self._send_json(404, {"error": "not_found", "message": f"Ticket {ticket_id} not found"})
                return

            # Check 409 already_handled
            if ticket["status"] == "handled":
                self._send_json(409, {
                    "error": "already_handled",
                    "message": f"Ticket {ticket_id} was already handled. A customer must never get two answers."
                })
                return

            length = int(self.headers.get("Content-Length", 0))
            body_bytes = self.rfile.read(length) if length > 0 else b"{}"
            try:
                payload = json.loads(body_bytes.decode("utf-8"))
            except Exception:
                self._send_json(400, {"error": "invalid_json", "message": "Malformed JSON payload"})
                return

            # Validate required fields
            for req in ["language", "category", "priority", "reason"]:
                if req not in payload:
                    self._send_json(422, {"error": "validation_failed", "problems": [f"Missing field: {req}"]})
                    return

            if action == "reply" and "draft_reply" not in payload:
                self._send_json(422, {"error": "validation_failed", "problems": ["Missing field: draft_reply"]})
                return

            if action == "handoff" and "handoff_note" not in payload:
                self._send_json(422, {"error": "validation_failed", "problems": ["Missing field: handoff_note"]})
                return

            ticket["status"] = "handled"
            ticket["handled_with"] = {"action": action, "payload": payload}
            self._send_json(200, {
                "message": f"Ticket {ticket_id} handled successfully with action {action}",
                "ticket_id": ticket_id,
                "status": "handled"
            })
            return

        self._send_json(404, {"error": "not_found", "message": f"Unknown endpoint {path}"})


def run_mock_server(host="127.0.0.1", port=8000):
    server = HTTPServer((host, port), MockHelpdeskHandler)
    print(f"Mock Helpdesk Server running at http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run_mock_server()
