# Roosterly Support Ticket Agent

Automated triage, FAQ resolution, and human escalation agent for Roosterly customer support.

---

## How to run

From a fresh clone:

```bash
# 1. Install dependencies
python -m venv venv
# Windows: venv\Scripts\activate | Unix: source venv/bin/activate
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env and supply your HELPDESK_API_KEY, CANDIDATE_EMAIL, and GROQ_API_KEY (or GEMINI_API_KEY)

# 3. Run unit tests
python -m pytest

# 4. Run the benchmark evaluation across the 10 labelled reference examples
python scripts/run_eval.py

# 5. Run the agent against the live helpdesk (single command)
python scripts/run_agent.py

# Optional: To re-open practice tickets and run fresh:
python scripts/run_agent.py --reset
```

---

## Decisions

1. **Hybrid Deterministic Guardrails + Fast Multilingual LLM:** To uphold the *"safety first"* client mandate, deterministic regex filters intercept non-negotiable human escalations (refunds, GDPR/AVG deletions, contract cancellations, legal threats, security incidents, churn threats) before invoking the LLM. FAQ questions and edge cases are routed to **Qwen 2.5 / 3 via Groq** (with Gemini fallback) in structured JSON mode. This ensures 0% hallucination risk on legal/financial policies while keeping response latency sub-second.
2. **Handling Dutch without Speaking Dutch:** Customer tickets and FAQ answers are processed natively in Dutch. To guarantee correctness without manual fluency, the agent uses a dual-verification strategy:
   - Grounding check verifying that draft replies strictly cite official Dutch menu paths (e.g., `Team → Medewerker toevoegen`, `Instellingen → Koppelingen → Salaris`).
   - Leakage and sentiment filters ensuring no English leakage in customer replies, while handoff notes are strictly formatted in English for support staff. If verification detects any anomaly, the ticket safely degrades to human handoff.
3. **Assumptions & AI Tooling:** Where ambiguous, an "unsure" classification always defaults to human handoff (P2/P3) rather than guessing. Ticket bodies are treated as untrusted data (`<ticket_data>` boundary) to prevent prompt injection. The system was designed and prototyped with Antigravity agentic workflows, using strict Pydantic schemas and test-driven development.

---

## Reliability

* **503 Service Unavailable:** Handled via `tenacity` exponential backoff with random jitter (initial 0.5s, max 4s, 5 attempts). Transient server outages resolve without dropping tickets.
* **429 Rate Limiting:** Client enforces proactive request spacing (< 4.5 calls/sec). If a 429 occurs, the client extracts the `Retry-After` header, dynamically pauses, and retries.
* **409 Conflict Prevention & Crash Recovery:** Atomic state checkpointing (`data/state.json`) tracks every handled ticket ID. If restarted after a crash, the agent queries `status=open` and cross-references local state to resume exactly where it stopped, ensuring no customer receives duplicate answers. If a 409 is received, it is recorded without failing the run.
* **Security & Privacy:** A dedicated regex scrubber (`src/scrubber.py`) masks Dutch/EU IBANs (`NL\d{2}...`), credit cards, and CVVs from prompt context and logs. Sensitive credentials are read strictly from environment variables.

---

## Eval and fix

* **Baseline Evaluation (Before Fix):** Running the pure model without deterministic guardrails (`python scripts/run_eval.py --without-guardrails`) scored **90.0% Exact Match**. The failure occurred on example **E08** ("Datalek / beveiliging: Ik zie salarisgegevens van een ander restaurant!"), where the model categorized the incident as `category="other"` instead of `category="bug"`.
* **The Fix:** Implemented a targeted security incident rule (`SECURITY_REGEX` in `src/rules.py`) that strictly maps data leaks and vulnerability reports to `category="bug"`, `priority="P1"`, `action="handoff"`.
* **Post-Fix Evaluation (After):** Running with guardrails enabled (`python scripts/run_eval.py`) achieved **100.0% Exact Match**, **100.0% Action Accuracy**, and **100.0% Category Accuracy** across all 10 reference examples.
* **Cost Calculation per 100 tickets:**
  - Average prompt: 650 input tokens per ticket.
  - Average completion: 85 output tokens per ticket.
  - Pricing ($0.075 / 1M input, $0.30 / 1M output):
  $$\text{Cost} = 100 \times \left(\frac{650}{10^6} \times \$0.075 + \frac{85}{10^6} \times \$0.30\right) = \$0.00743 \text{ per 100 tickets (approx } €0.0068\text{)}$$
  Well within the €1 threshold for the entire assignment.

---

## What I would improve

1. **Next Step:** Implement automated back-translation into English saved in local logs alongside the Dutch customer reply so English-speaking support leads can audit automated responses in real-time.
2. **Rule/Brief Change:** Clarify `category` guidelines for data privacy and security incidents: currently a data leak is labelled `bug` (E08) while a GDPR deletion request is labelled `other` (E07). Creating a dedicated `compliance_security` category would eliminate ambiguity between operational software bugs and legal/privacy obligations.
