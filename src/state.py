"""State manager for crash-resilience and idempotency.

Ensures that after a crash, the agent continues where it stopped,
and no customer ever gets two answers (avoiding 409 already_handled errors).
"""

from typing import Dict, Any, Optional
import json
from pathlib import Path
from datetime import datetime, timezone
import tempfile
import os

from src.config import STATE_FILE


class StateManager:
    """Manages persistent ticket handling state."""

    def __init__(self, state_file: Optional[Path] = None):
        self.state_file = state_file or STATE_FILE
        self._state: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        """Loads state from disk if present."""
        if not self.state_file.exists():
            return {}
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save(self) -> None:
        """Atomically saves state to disk."""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        # Write to temporary file in the same directory, then atomic rename
        temp_file = tempfile.NamedTemporaryFile(
            "w", 
            dir=str(self.state_file.parent), 
            delete=False, 
            encoding="utf-8"
        )
        try:
            json.dump(self._state, temp_file, indent=2)
            temp_file.flush()
            os.fsync(temp_file.fileno())
            temp_file.close()
            # On Windows, replace works cleanly in Python 3.3+
            os.replace(temp_file.name, str(self.state_file))
        except Exception:
            if os.path.exists(temp_file.name):
                os.remove(temp_file.name)
            raise

    def is_handled(self, ticket_id: str) -> bool:
        """Check if a ticket has already been handled."""
        return ticket_id in self._state

    def mark_handled(
        self, 
        ticket_id: str, 
        action: str, 
        reason: str,
        category: str,
        priority: str
    ) -> None:
        """Records a ticket as handled and commits atomically."""
        self._state[ticket_id] = {
            "action": action,
            "category": category,
            "priority": priority,
            "reason": reason,
            "handled_at": datetime.now(timezone.utc).isoformat()
        }
        self._save()

    def get_handled_count(self) -> int:
        """Returns the number of handled tickets in local state."""
        return len(self._state)

    def reset(self) -> None:
        """Resets local state (used when resetting the practice environment)."""
        self._state = {}
        if self.state_file.exists():
            try:
                self.state_file.unlink()
            except Exception:
                pass
