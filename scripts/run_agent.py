"""Single-command entrypoint to run the Roosterly Support Ticket Agent."""

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
    parser = argparse.ArgumentParser(description="Run the Roosterly Support Ticket Agent.")
    parser.add_argument(
        "--reset", 
        action="store_true", 
        help="Re-open all practice tickets before running (calls POST /practice/reset and clears local state)."
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Run against local mock server (http://127.0.0.1:8000)."
    )
    args = parser.parse_args()

    base_url = "http://127.0.0.1:8000" if args.mock else HELPDESK_BASE_URL
    api_key = "mock_key" if args.mock else None
    email = "test@example.com" if args.mock else None

    client = HelpdeskClient(base_url=base_url, api_key=api_key, email=email)
    state = StateManager()

    if args.reset:
        print("Resetting practice tickets in helpdesk...")
        try:
            client.reset_practice()
            state.reset()
            print("Practice environment and local state reset successfully.")
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
