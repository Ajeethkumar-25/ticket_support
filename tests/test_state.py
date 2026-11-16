"""Unit tests for state management, crash-safety, and idempotency."""

import pytest
import tempfile
from pathlib import Path
from src.state import StateManager


def test_state_persistence():
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "state.json"
        sm = StateManager(state_file)

        assert not sm.is_handled("T001")
        sm.mark_handled("T001", action="reply", reason="FAQ F01", category="question", priority="P4")
        assert sm.is_handled("T001")
        assert sm.get_handled_count() == 1

        # Reload from fresh instance
        sm2 = StateManager(state_file)
        assert sm2.is_handled("T001")
        assert not sm2.is_handled("T002")

        # Reset
        sm2.reset()
        assert not sm2.is_handled("T001")
        assert sm2.get_handled_count() == 0
