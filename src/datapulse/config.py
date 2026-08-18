"""DataPulse configuration — loads from environment variables with safe defaults."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env file if it exists (no-op if missing)
load_dotenv()

# ── Database ────────────────────────────────────────────────────

# Default: SQLite in project root (works without Docker)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_SQLITE_URL = f"sqlite:///{_PROJECT_ROOT / 'datapulse.db'}"

DATABASE_URL: str = os.getenv("DATAPULSE_DATABASE_URL", _DEFAULT_SQLITE_URL)

# ── Logging ─────────────────────────────────────────────────────

LOG_LEVEL: str = os.getenv("DATAPULSE_LOG_LEVEL", "INFO")

# ── Environment ─────────────────────────────────────────────────

ENVIRONMENT: str = os.getenv("DATAPULSE_ENVIRONMENT", "development")

# ── API Server ──────────────────────────────────────────────────

API_HOST: str = os.getenv("DATAPULSE_API_HOST", "0.0.0.0")
API_PORT: int = int(os.getenv("DATAPULSE_API_PORT", "8000"))
