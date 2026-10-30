"""Optional email delivery of reports. Only used when SMTP is genuinely configured."""
from __future__ import annotations

import re
import smtplib
import ssl
from email.message import EmailMessage

import config

_EMAIL_RE = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")


def valid_email(addr: str) -> bool:
    return bool(_EMAIL_RE.match((addr or "").strip()))


def parse_recipients(raw: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"[,;\s]+", raw or "") if p.strip()]
    return parts


def send_report_email(recipients: list[str], subject: str, body: str) -> tuple[bool, str]:
    """Returns (ok, message). Never claims success unless the SMTP server accepted the message."""
    if not config.smtp_configured():
        return False, "Email NOT sent: SMTP is not configured (see README, 'Email delivery')."
    recipients = [r for r in recipients if valid_email(r)]
    if not recipients:
        return False, "Email NOT sent: no valid recipient address."
    s = config.smtp_settings()
    msg = EmailMessage()
    msg["Subject"] = subject[:200]
    msg["From"] = s["sender"]
    msg["To"] = ", ".join(recipients)
    msg.set_content(body)
    try:
        if s["port"] == 465:
            with smtplib.SMTP_SSL(s["host"], s["port"], timeout=30, context=ssl.create_default_context()) as srv:
                if s["user"]:
                    srv.login(s["user"], s["password"])
                srv.send_message(msg)
        else:
            with smtplib.SMTP(s["host"], s["port"], timeout=30) as srv:
                srv.starttls(context=ssl.create_default_context())
                if s["user"]:
                    srv.login(s["user"], s["password"])
                srv.send_message(msg)
    except Exception as exc:
        return False, config.redact(f"Email NOT sent: {type(exc).__name__}")
    return True, f"Email sent to {len(recipients)} recipient(s)."
