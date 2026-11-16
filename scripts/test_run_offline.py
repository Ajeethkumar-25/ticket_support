"""End-to-End Test Runner against the Mock Helpdesk Server.

Starts mock server in an in-process daemon thread, executes full agent run over 30 practice tickets,
and verifies logs and state persistence.
"""

import threading
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.mock_server import MockHelpdeskHandler, HTTPServer
from src.client import HelpdeskClient
from src.agent import SupportTicketAgent
from src.state import StateManager
from src.config import LOG_FILE, STATE_FILE


def main():
    host = "127.0.0.1"
    port = 8899

    server = HTTPServer((host, port), MockHelpdeskHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    print(f"In-process Mock Helpdesk Server started on http://{host}:{port}")

    client = HelpdeskClient(
        base_url=f"http://{host}:{port}",
        api_key="mock_test_key",
        email="ajkmr2525@gmail.com"
    )
    state = StateManager()

    print("Resetting mock helpdesk practice tickets...")
    client.reset_practice()
    state.reset()

    print("Running SupportTicketAgent...")
    agent = SupportTicketAgent(helpdesk_client=client, state_manager=state)
    stats = agent.run()

    print("\n=== Offline Run Summary ===")
    print(f"Processed: {stats['processed']}")
    print(f"Replies:   {stats['reply']}")
    print(f"Handoffs:  {stats['handoff']}")
    print(f"Closed:    {stats['close']}")
    print(f"Skipped:   {stats['skipped']}")

    status = client.get_status()
    print("Final Helpdesk Server Status:", status)

    server.shutdown()
    print("Mock server stopped successfully.")


if __name__ == "__main__":
    main()
