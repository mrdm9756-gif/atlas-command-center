"""Shared constants, validators and small helpers (no database access here)."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, available_timezones

import config

# --------------------------------------------------------------------------- #
# Task statuses
# --------------------------------------------------------------------------- #
DRAFT = "Draft"
QUEUED = "Queued"
IN_PROGRESS = "In Progress"
WAITING_APPROVAL = "Waiting for Approval"
COMPLETED = "Completed"
FAILED = "Failed"
CANCELLED = "Cancelled"

TASK_STATUSES = [DRAFT, QUEUED, IN_PROGRESS, WAITING_APPROVAL, COMPLETED, FAILED, CANCELLED]
OPEN_STATUSES = [DRAFT, QUEUED, IN_PROGRESS, WAITING_APPROVAL]
CLOSED_STATUSES = [COMPLETED, FAILED, CANCELLED]
PRIORITIES = ["Low", "Normal", "High", "Urgent"]

# --------------------------------------------------------------------------- #
# Result "modes" - the honesty labels shown everywhere in the UI
# --------------------------------------------------------------------------- #
MODE_LIVE = "live"        # produced by a real call to the AI model
MODE_DEMO = "demo"        # simulated demonstration text, NOT from an AI model
MODE_COMPUTED = "computed"  # computed by Python from user-provided data
MODE_SYSTEM = "system"    # system/orchestrator message
MODE_ERROR = "error"

MODE_LABELS = {
    MODE_LIVE: "AI-GENERATED (live model)",
    MODE_DEMO: "DEMO - SIMULATED (no AI model used)",
    MODE_COMPUTED: "COMPUTED FROM YOUR DATA",
    MODE_SYSTEM: "SYSTEM",
    MODE_ERROR: "ERROR",
}

# Data provenance labels used in reports
DATA_REAL = "real"            # from user-provided datasets
DATA_ESTIMATED = "estimated"  # AI estimates / assumptions
DATA_SIMULATED = "simulated"  # DEMO DATA
DATA_NONE = "none"

DATA_LABELS = {
    DATA_REAL: "REAL (user-provided data)",
    DATA_ESTIMATED: "ESTIMATED (AI assumptions - verify before use)",
    DATA_SIMULATED: "SIMULATED (DEMO DATA)",
    DATA_NONE: "NO DATA CONNECTED",
}

# Report types
REPORT_TYPES = ["task", "adhoc", "daily", "weekly", "monthly"]
SCHEDULE_KINDS = ["daily", "weekly", "monthly"]
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# --------------------------------------------------------------------------- #
# External (consequential) actions - always need explicit owner approval
# --------------------------------------------------------------------------- #
# blocked=True means the MVP refuses to ever execute it (money movement).
EXTERNAL_ACTIONS = {
    "send_customer_message": {"label": "Send message to real customers", "blocked": False},
    "publish_content": {"label": "Publish content publicly", "blocked": False},
    "spend_ad_budget": {"label": "Spend advertising money", "blocked": True},
    "make_purchase": {"label": "Make a purchase", "blocked": True},
    "issue_refund": {"label": "Issue a refund", "blocked": True},
    "financial_transaction": {"label": "Make a financial transaction / trade", "blocked": True},
    "modify_production": {"label": "Modify a production system", "blocked": False},
}

APPROVAL_PENDING = "pending"
APPROVAL_APPROVED = "approved"
APPROVAL_REJECTED = "rejected"


# --------------------------------------------------------------------------- #
# Time helpers
# --------------------------------------------------------------------------- #
def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().replace(microsecond=0).isoformat()


def valid_timezone(name: str) -> bool:
    try:
        ZoneInfo(name)
        return True
    except Exception:
        return False


def all_timezones() -> list[str]:
    zones = sorted(available_timezones())
    return zones or [config.DEFAULT_TIMEZONE]


def to_local(iso: str | None, tz_name: str = config.DEFAULT_TIMEZONE) -> datetime | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ZoneInfo(tz_name if valid_timezone(tz_name) else config.DEFAULT_TIMEZONE))
    except Exception:
        return None


def fmt_local(iso: str | None, tz_name: str = config.DEFAULT_TIMEZONE) -> str:
    dt = to_local(iso, tz_name)
    return dt.strftime("%Y-%m-%d %H:%M") if dt else "-"


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
class ValidationError(ValueError):
    """Raised for invalid user input. The message is safe to show to the user."""


_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_text(value: str | None, *, field: str = "Text", max_len: int | None = None,
               required: bool = False) -> str:
    """Strip control characters, trim, enforce a length limit."""
    max_len = max_len or config.MAX_TEXT_LENGTH
    text = _CONTROL_CHARS.sub("", str(value or "")).strip()
    if required and not text:
        raise ValidationError(f"{field} is required.")
    if len(text) > max_len:
        raise ValidationError(f"{field} is too long (max {max_len} characters).")
    return text


def clean_name(value: str | None, *, field: str = "Name", max_len: int = 60) -> str:
    text = clean_text(value, field=field, max_len=max_len, required=True)
    if "\n" in text or "\r" in text:
        raise ValidationError(f"{field} must be a single line.")
    return text


def clamp(value, low, high, default=None):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default if default is not None else low
    return max(low, min(high, v))


def parse_hhmm(value: str) -> tuple[int, int]:
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", str(value or ""))
    if not m:
        raise ValidationError("Time must look like HH:MM (for example 08:30).")
    h, mi = int(m.group(1)), int(m.group(2))
    if not (0 <= h <= 23 and 0 <= mi <= 59):
        raise ValidationError("Time must be between 00:00 and 23:59.")
    return h, mi
