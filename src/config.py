"""Configuration settings for Roosterly Support Ticket Agent."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Base project root
ROOT_DIR = Path(__file__).resolve().parent.parent

# Load .env file
load_dotenv(ROOT_DIR / ".env")

# Roosterly Helpdesk API
HELPDESK_BASE_URL = os.getenv(
    "HELPDESK_BASE_URL", 
    "https://nakywgkztvzkihdjnwbc.supabase.co/functions/v1/helpdesk"
).rstrip("/")

HELPDESK_API_KEY = os.getenv("HELPDESK_API_KEY", "")
CANDIDATE_EMAIL = os.getenv("CANDIDATE_EMAIL", "")

# Groq API Configuration
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")

# Operational Parameters
REQUEST_RATE_LIMIT = float(os.getenv("REQUEST_RATE_LIMIT", "4.5"))  # requests per second (< 5.0)
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "5"))
RETRY_INITIAL_DELAY = float(os.getenv("RETRY_INITIAL_DELAY", "0.5"))  # seconds

# Paths
LOGS_DIR = ROOT_DIR / "logs"
LOG_FILE = Path(os.getenv("LOG_FILE", str(LOGS_DIR / "tickets.log")))
DATA_DIR = ROOT_DIR / "data"
STATE_FILE = Path(os.getenv("STATE_FILE", str(DATA_DIR / "state.json")))

# Ensure directories exist
LOGS_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)


def is_live_api_ready() -> bool:
    """Check if valid Helpdesk API credentials are set."""
    return bool(
        HELPDESK_API_KEY 
        and HELPDESK_API_KEY != "placeholder_until_found" 
        and CANDIDATE_EMAIL
    )


def is_llm_ready() -> bool:
    """Check if the Groq LLM API key is configured."""
    return bool(GROQ_API_KEY)
