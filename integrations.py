"""Honest integration status. Only things that are really implemented can show as connected."""
from __future__ import annotations

import config
import ai_provider

CONNECTED = "Connected"
DISCONNECTED = "Disconnected"
BROWSER = "Depends on your browser"
NOT_IMPLEMENTED = "Not implemented (disconnected)"


def integration_status() -> list[dict]:
    live = ai_provider.provider_status()["live"]
    rows = [
        {"name": "Gemini AI API", "status": CONNECTED if live else DISCONNECTED,
         "detail": "Live AI answers are active." if live else "No API key (or demo forced). Demo mode is on - answers are simulated."},
        {"name": "CSV data upload", "status": CONNECTED, "detail": "Built in. Upload files in Analytics."},
        {"name": "Email delivery (SMTP)", "status": CONNECTED if config.smtp_configured() else DISCONNECTED,
         "detail": "Reports can be emailed." if config.smtp_configured() else "Not configured. Reports stay in the dashboard."},
        {"name": "Browser speech output", "status": BROWSER, "detail": "Voices are detected in Voice Settings."},
        {"name": "Browser speech input", "status": BROWSER, "detail": "Needs a supporting browser and microphone permission."},
        {"name": "Premium cloud voice", "status": DISCONNECTED, "detail": "Optional adapter, none configured."},
    ]
    for name in ("CRM (HubSpot, Salesforce...)", "Accounting (QuickBooks, Xero...)", "POS / ordering systems",
                 "E-commerce stores (Shopify...)", "Social media publishing", "Advertising platforms",
                 "Calendars and messaging (Slack, WhatsApp...)"):
        rows.append({"name": name, "status": NOT_IMPLEMENTED,
                     "detail": "No connector exists in this version. Upload CSV exports instead."})
    return rows


def connected_count() -> tuple[int, int]:
    rows = integration_status()
    return sum(1 for r in rows if r["status"] == CONNECTED), len(rows)
