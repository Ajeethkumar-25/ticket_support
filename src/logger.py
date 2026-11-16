"""Sanitized structured logging for ticket decisions.

Requirement: Exactly one log line per ticket in logs/, without payment details.
"""

from typing import Optional
from datetime import datetime, timezone
import json
from pathlib import Path

from src.config import LOG_FILE
from src.scrubber import scrub_payment_details


class TicketLogger:
    """Appends sanitized single-line log entries per ticket."""

    def __init__(self, log_path: Optional[Path] = None):
        self.log_path = log_path or LOG_FILE
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def log_ticket(
        self,
        ticket_id: str,
        language: str,
        category: str,
        priority: str,
        action: str,
        reason: str,
        confidence: float,
        note_or_reply_preview: Optional[str] = None
    ) -> None:
        """
        Writes a single sanitized log line for a processed ticket.
        Guarantees that no payment details are recorded.
        """
        # Scrub reason and preview
        clean_reason, _ = scrub_payment_details(reason)
        clean_preview, _ = scrub_payment_details(note_or_reply_preview or "")
        # Truncate preview if long
        if len(clean_preview) > 80:
            clean_preview = clean_preview[:77] + "..."

        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        log_data = {
            "time": timestamp,
            "ticket_id": ticket_id,
            "lang": language,
            "category": category,
            "priority": priority,
            "action": action,
            "confidence": round(confidence, 2),
            "reason": clean_reason
        }
        if clean_preview:
            log_data["preview"] = clean_preview

        # Convert to single-line JSON
        line = json.dumps(log_data, ensure_ascii=False)

        # Final safety scrub
        safe_line, _ = scrub_payment_details(line)

        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(safe_line + "\n")
