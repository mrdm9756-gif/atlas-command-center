"""Central configuration for ATLAS Command Center.

Secrets (API keys, SMTP passwords) are read from environment variables, a local
.env file, or Streamlit Secrets. They are NEVER stored in the database and are
never displayed in the UI.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

try:  # python-dotenv is optional; .env is just a convenience
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
except Exception:  # pragma: no cover - dotenv missing is fine
    pass

APP_NAME = "ATLAS Command Center"
APP_VERSION = "1.0.0-mvp"

DEFAULT_AI_NAME = "ATLAS"
DEFAULT_OWNER_NAME = "Boss"
DEFAULT_TIMEZONE = "Asia/Manila"
DEFAULT_LANGUAGE = "English"

# Limits / safety
AI_TIMEOUT_SECONDS = 45
AI_MAX_RETRIES = 2            # retries on top of the first attempt; never infinite
TASK_STALE_MINUTES = 15       # "In Progress" tasks older than this are marked Failed
MAX_TEXT_LENGTH = 8000        # max length of any single free-text input
MAX_CSV_BYTES = 5 * 1024 * 1024


def db_path() -> Path:
    """Location of the SQLite file. Override with ATLAS_DB_PATH."""
    override = os.environ.get("ATLAS_DB_PATH")
    if override:
        return Path(override)
    return BASE_DIR / "data" / "atlas.db"


def get_secret(name: str, default: str = "") -> str:
    """Read a secret from env vars first, then Streamlit Secrets. Never logged."""
    value = os.environ.get(name)
    if value:
        return value.strip()
    try:  # pragma: no cover - only works inside a running Streamlit app
        import streamlit as st

        if name in st.secrets:
            return str(st.secrets[name]).strip()
    except Exception:
        pass
    return default


def gemini_api_key() -> str:
    return get_secret("GEMINI_API_KEY") or get_secret("GOOGLE_API_KEY")


def gemini_model() -> str:
    return get_secret("GEMINI_MODEL", "gemini-2.5-flash")


def force_demo_mode() -> bool:
    return get_secret("ATLAS_FORCE_DEMO", "").lower() in {"1", "true", "yes"}


def smtp_settings() -> dict:
    return {
        "host": get_secret("SMTP_HOST"),
        "port": int(get_secret("SMTP_PORT", "587") or 587),
        "user": get_secret("SMTP_USER"),
        "password": get_secret("SMTP_PASSWORD"),
        "sender": get_secret("SMTP_FROM") or get_secret("SMTP_USER"),
    }


def smtp_configured() -> bool:
    s = smtp_settings()
    return bool(s["host"] and s["sender"])


_SECRET_PATTERNS = [
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),          # Google API keys
    re.compile(r"(?i)(api[_-]?key|password|token)\s*[=:]\s*\S+"),
]


def redact(text: str) -> str:
    """Remove anything that looks like a secret from text before logging/showing."""
    out = str(text)
    for pat in _SECRET_PATTERNS:
        out = pat.sub("[REDACTED]", out)
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "SMTP_PASSWORD"):
        val = os.environ.get(name)
        if val and len(val) > 6:
            out = out.replace(val, "[REDACTED]")
    return out
