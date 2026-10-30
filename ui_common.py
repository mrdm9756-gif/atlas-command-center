"""Shared Streamlit helpers: styling, badges, context, navigation, safe actions."""
from __future__ import annotations

import html
from dataclasses import dataclass

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import ai_provider
import config
import database as dbm
import models
from orchestrator import Orchestrator

PAGES = [
    "Voice Interface", "Overview", "AI Workforce", "Task Center", "Reports Center", "Analytics",
    "Industry Workspace", "Interface Studio", "Voice Settings", "Owner Settings", "Approvals", "System Health",
]
PAGE_ICONS = {
    "Voice Interface": "🎙️", "Overview": "📊", "AI Workforce": "🤖", "Task Center": "✅",
    "Reports Center": "📑", "Analytics": "📈", "Industry Workspace": "🏭", "Interface Studio": "🎨",
    "Voice Settings": "🔊", "Owner Settings": "⚙️", "Approvals": "🛡️", "System Health": "🩺",
}

CSS = """
<style>
.stApp{background:linear-gradient(180deg,#0b1220 0%,#0d1526 100%);color:#e5edf7}
section[data-testid="stSidebar"]{background:#0a111f;border-right:1px solid #1b2a47}
h1,h2,h3{letter-spacing:.01em}
div[data-testid="stMetric"]{background:#0f1a2e;border:1px solid #1f2f4d;border-radius:12px;padding:10px 14px}
div[data-testid="stMetricValue"]{color:#7dd3fc}
.badge{display:inline-block;padding:2px 9px;border-radius:999px;font-size:11.5px;font-weight:600;border:1px solid;margin-right:4px;white-space:nowrap}
.b-live{color:#34d399;border-color:#1f7a5a;background:#0b2a22}
.b-demo{color:#fbbf24;border-color:#7a5a12;background:#2a2108}
.b-computed{color:#60a5fa;border-color:#27508f;background:#0b1c36}
.b-error{color:#f87171;border-color:#8f2b2b;background:#2a0e0e}
.b-system{color:#9fb3cf;border-color:#2b4268;background:#101b2f}
.b-ok{color:#34d399;border-color:#1f7a5a;background:#0b2a22}
.b-warn{color:#fbbf24;border-color:#7a5a12;background:#2a2108}
.b-info{color:#22d3ee;border-color:#17697a;background:#082229}
.atlas-card{background:#0f1a2e;border:1px solid #1f2f4d;border-radius:14px;padding:14px 16px;margin-bottom:10px}
.muted{color:#8da2c0;font-size:13px}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px}
.dot-idle{background:#34d399}.dot-working{background:#22d3ee;box-shadow:0 0 8px #22d3ee}.dot-off{background:#64748b}
</style>
"""


def esc(value) -> str:
    """HTML-escape anything that is user- or AI-supplied before putting it in unsafe HTML."""
    return html.escape(str(value if value is not None else ""))


def badge(text: str, kind: str = "system") -> str:
    return f'<span class="badge b-{kind}">{esc(text)}</span>'


_MODE_BADGE = {
    models.MODE_LIVE: ("AI-GENERATED", "live"),
    models.MODE_DEMO: ("DEMO - SIMULATED", "demo"),
    models.MODE_COMPUTED: ("COMPUTED FROM YOUR DATA", "computed"),
    models.MODE_ERROR: ("ERROR", "error"),
    models.MODE_SYSTEM: ("SYSTEM", "system"),
    "owner": ("YOU", "system"),
}


def mode_badge(mode: str) -> str:
    text, kind = _MODE_BADGE.get(mode, (str(mode).upper() or "-", "system"))
    return badge(text, kind)


_STATUS_KIND = {
    models.DRAFT: "system", models.QUEUED: "info", models.IN_PROGRESS: "info",
    models.WAITING_APPROVAL: "warn", models.COMPLETED: "ok", models.FAILED: "error", models.CANCELLED: "system",
}


def status_badge(status: str) -> str:
    return badge(status, _STATUS_KIND.get(status, "system"))


def data_badge(label: str) -> str:
    kind = {"real": "live", "estimated": "demo", "simulated": "demo", "none": "system"}.get(label, "system")
    return badge(models.DATA_LABELS.get(label, label), kind)


def md_html(html_str: str) -> None:
    st.markdown(html_str, unsafe_allow_html=True)


def render_component(html_str: str, height: int = 400) -> None:
    """Show an HTML/JS component. If it cannot load, the rest of the app keeps working."""
    try:
        components.html(html_str, height=height, scrolling=False)
    except Exception:  # pragma: no cover - depends on the Streamlit version
        st.warning("The animated/voice component could not load in this browser or Streamlit version. "
                   "Everything is still available in text mode.")


def tasks_dataframe(tasks: list[dict], tz_name: str = config.DEFAULT_TIMEZONE) -> pd.DataFrame:
    import agents as agent_registry
    rows = []
    for t in tasks:
        ag = agent_registry.get_agent(t["agent_key"])
        rows.append({"ID": t["id"], "Title": t["title"], "Agent": ag.name if ag else t["agent_key"],
                     "Status": t["status"], "Priority": t["priority"], "Due": t["due_date"] or "-",
                     "Result type": models.MODE_LABELS.get(t["result_mode"], "-") if t["result_mode"] else "-",
                     "Updated": models.fmt_local(t["updated_at"], tz_name)})
    return pd.DataFrame(rows, columns=["ID", "Title", "Agent", "Status", "Priority", "Due", "Result type", "Updated"])


def empty_state(message: str, hint: str = "") -> None:
    md_html(f'<div class="atlas-card"><b>{esc(message)}</b>'
            + (f'<div class="muted">{esc(hint)}</div>' if hint else "") + "</div>")


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# Context + navigation
# --------------------------------------------------------------------------- #
@dataclass
class AppContext:
    company: dict
    orch: Orchestrator
    ai_name: str
    owner_name: str
    provider: dict

    @property
    def company_id(self) -> int:
        return self.company["id"]

    def greeting(self) -> str:
        return (f"Hello, {self.owner_name}. {self.ai_name} is online. Your AI workforce is ready. "
                "What would you like us to work on today?")


def build_context() -> AppContext:
    company = dbm.active_company()
    return AppContext(
        company=company,
        orch=Orchestrator(company["id"]),
        ai_name=dbm.get_setting("ai_name"),
        owner_name=dbm.get_setting("owner_name"),
        provider=ai_provider.provider_status(),
    )


def goto(page: str) -> None:
    """Switch page on the next run (safe to call from any view)."""
    st.session_state["goto"] = page
    st.rerun()


def run_safely(fn, *args, success: str | None = None, **kwargs):
    """Run an action; show friendly errors; never crash the page. Returns (ok, result)."""
    try:
        result = fn(*args, **kwargs)
        if success:
            st.success(success)
        return True, result
    except models.ValidationError as exc:
        st.error(str(exc))
    except Exception as exc:  # pragma: no cover - last-resort guard
        msg = config.redact(f"{type(exc).__name__}: {exc}")
        dbm.log_audit(None, "ui", "unexpected_error", msg)
        st.error(f"Something went wrong: {msg}")
    return False, None


def mode_banner(ctx: AppContext) -> None:
    if ctx.provider["live"]:
        md_html(badge("LIVE AI: Gemini", "live") + f'<span class="muted"> model {esc(ctx.provider["model"])}</span>')
    else:
        md_html(badge("DEMO MODE", "demo")
                + '<span class="muted"> No live AI model is connected, so all AI text is simulated and labelled. '
                  'See System Health to add an API key.</span>')
