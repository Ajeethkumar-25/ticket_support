"""
Roosterly Support Ticket Agent — single-file entrypoint.

Usage:
    python main.py              # Run agent on all open tickets
    python main.py --reset      # Reset all 30 practice tickets, then run
    python main.py --eval       # Run eval on 10 labelled examples only
    python main.py --reset --eval  # Reset → eval → run agent
"""

import argparse
import sys
from pathlib import Path

# Ensure project root is on the import path when run directly
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.config import is_live_api_ready, HELPDESK_BASE_URL, GROQ_MODEL
from src.client import HelpdeskClient
from src.agent import SupportTicketAgent
from src.state import StateManager


# ---------------------------------------------------------------------------
# Eval
# ---------------------------------------------------------------------------

def run_eval(client: HelpdeskClient) -> None:
    """Fetch the 10 labelled examples and score the agent against them."""
    from src.llm_client import LLMClient
    from src.rules import check_deterministic_rules
    from src.scrubber import scrub_payment_details

    print("\n=== Eval: scoring against 10 labelled Nordavo examples ===\n")

    examples = client.get_examples()
    if not examples:
        print("No examples returned from GET /examples — skipping eval.")
        return

    llm = LLMClient()
    fields = ["action", "category", "priority", "language"]
    totals = {f: 0 for f in fields}
    n = 0

    for ex in examples:
        ex_id   = ex.get("id", "?")
        subject = ex.get("subject", "")
        body    = ex.get("body", "")
        label   = ex.get("label", {})
        plan    = ex.get("customer_plan", "Basis")

        clean_subj, _ = scrub_payment_details(subject)
        clean_body, _ = scrub_payment_details(body)

        rule_hit = check_deterministic_rules(clean_subj, clean_body)
        if rule_hit:
            pred = {
                "action":   rule_hit.action,
                "category": rule_hit.category,
                "priority": rule_hit.priority,
                "language": "nl",
            }
        else:
            decision = llm.triage_ticket(clean_subj, clean_body, plan)
            pred = {
                "action":   decision.action,
                "category": decision.category,
                "priority": decision.priority,
                "language": decision.language,
            }

        row_ok = {}
        for f in fields:
            match = str(pred.get(f, "")).lower() == str(label.get(f, "")).lower()
            row_ok[f] = "✓" if match else f"✗ (pred={pred.get(f)} label={label.get(f)})"
            if match:
                totals[f] += 1

        n += 1
        print(f"  {ex_id:>4}  action:{row_ok['action']}  "
              f"cat:{row_ok['category']}  pri:{row_ok['priority']}  "
              f"lang:{row_ok['language']}")

    print(f"\n  Overall  action:{totals['action']}/{n}  "
          f"category:{totals['category']}/{n}  "
          f"priority:{totals['priority']}/{n}  "
          f"language:{totals['language']}/{n}")
    overall = sum(1 for i in range(n)
                  if all(totals[f] >= i + 1 for f in fields)) 
    pct = round(100 * sum(totals.values()) / (len(fields) * n), 1) if n else 0
    print(f"  Average accuracy: {pct}%\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Roosterly Support Ticket Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Call POST /practice/reset to reopen all 30 practice tickets before running.",
    )
    parser.add_argument(
        "--eval",
        action="store_true",
        help="Run the benchmark eval on the 10 labelled examples (GET /examples).",
    )
    args = parser.parse_args()

    # ── Pre-flight checks ──────────────────────────────────────────────────
    if not is_live_api_ready():
        print("\n[ERROR] Missing credentials. Create a .env file with:")
        print("  HELPDESK_API_KEY=<your key>")
        print("  CANDIDATE_EMAIL=<your email>")
        print("  GROQ_API_KEY=<your Groq key>")
        print("\nCopy .env.example → .env and fill in the values.\n")
        sys.exit(1)

    print(f"\n  Helpdesk : {HELPDESK_BASE_URL}")
    print(f"  LLM model: {GROQ_MODEL}")

    client = HelpdeskClient()
    state  = StateManager()

    # ── Optional reset ─────────────────────────────────────────────────────
    if args.reset:
        print("\n[RESET] Calling POST /practice/reset ...")
        try:
            res = client.reset_practice()
            state.reset()
            print(f"[RESET] Done: {res}\n")
        except Exception as exc:
            print(f"[RESET] Failed: {exc}")
            sys.exit(1)

    # ── Optional eval ──────────────────────────────────────────────────────
    if args.eval:
        try:
            run_eval(client)
        except Exception as exc:
            print(f"[EVAL] Error during eval: {exc}")

    # ── Run agent ─────────────────────────────────────────────────────────
    print("[AGENT] Processing all open tickets ...\n")
    agent = SupportTicketAgent(helpdesk_client=client, state_manager=state)
    stats = agent.run()

    print("\n=== Run Summary ===")
    print(f"  Processed : {stats['processed']}")
    print(f"  Replies   : {stats['reply']}")
    print(f"  Handoffs  : {stats['handoff']}")
    print(f"  Closed    : {stats['close']}")
    print(f"  Skipped   : {stats['skipped']}")
    print()


if __name__ == "__main__":
    main()
