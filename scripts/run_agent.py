"""Single-command entrypoint to run the Roosterly Support Ticket Agent on the live Helpdesk API."""

import argparse
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import is_live_api_ready, HELPDESK_BASE_URL
from src.client import HelpdeskClient
from src.agent import SupportTicketAgent
from src.state import StateManager


def main():
    parser = argparse.ArgumentParser(description="Run the Roosterly Support Ticket Agent against the live Helpdesk API.")
    parser.add_argument(
        "--reset", 
        action="store_true", 
        help="Re-open all practice tickets before running (calls POST /practice/reset and clears local state)."
    )
    args = parser.parse_args()

    if not is_live_api_ready():
        print("Error: Live Helpdesk credentials are not configured in .env.")
        print("Please ensure HELPDESK_API_KEY and CANDIDATE_EMAIL are set.")
        sys.exit(1)

    client = HelpdeskClient()
    state = StateManager()

    if args.reset:
        print("Resetting practice tickets in live Helpdesk API (POST /practice/reset)...")
        try:
            res = client.reset_practice()
            state.reset()
            print("Practice environment and local state reset successfully:", res)
        except Exception as e:
            print(f"Error resetting practice tickets: {e}")
            sys.exit(1)

    agent = SupportTicketAgent(helpdesk_client=client, state_manager=state)
    stats = agent.run()
    print("\n=== Agent Run Summary ===")
    print(f"Processed: {stats['processed']}")
    print(f"Replies:   {stats['reply']}")
    print(f"Handoffs:  {stats['handoff']}")
    print(f"Closed:    {stats['close']}")
    print(f"Skipped:   {stats['skipped']}")


if __name__ == "__main__":
    main()
