"""ATLAS Command Center - entry point.   Run with:  streamlit run app.py"""
from __future__ import annotations

import importlib

import streamlit as st

st.set_page_config(page_title="ATLAS Command Center", page_icon="🧠", layout="wide",
                   initial_sidebar_state="expanded")

import config  # noqa: E402
import database as dbm  # noqa: E402
import scheduler_service as ss  # noqa: E402
import ui_common as ui  # noqa: E402

PAGE_MODULES = {
    "Voice Interface": "views.voice_interface",
    "Overview": "views.overview",
    "AI Workforce": "views.workforce",
    "Task Center": "views.tasks",
    "Reports Center": "views.reports",
    "Analytics": "views.analytics",
    "Industry Workspace": "views.industry",
    "Interface Studio": "views.interface_studio",
    "Voice Settings": "views.voice_settings",
    "Owner Settings": "views.owner_settings",
    "Approvals": "views.approvals",
    "System Health": "views.system_health",
}


@st.cache_resource(show_spinner=False)
def _boot() -> dict:
    """Runs once per server process: create tables, recover stuck tasks, start the scheduler."""
    dbm.init_db()
    from orchestrator import Orchestrator
    recovered = 0
    for c in dbm.list_companies():
        recovered += Orchestrator(c["id"]).recover_stale_tasks()
    started = ss.get_service().start()
    return {"scheduler_started": started, "recovered": recovered}


def main() -> None:
    try:
        boot = _boot()
    except Exception as exc:
        st.error("ATLAS could not start its database. "
                 f"Details: {config.redact(type(exc).__name__ + ': ' + str(exc))}")
        st.info("Check that the data/ folder is writable, then restart. See README -> Troubleshooting.")
        return

    ui.inject_css()

    # Page requested by a button elsewhere (must be applied BEFORE the radio is created)
    if "goto" in st.session_state:
        st.session_state["nav"] = st.session_state.pop("goto")
    st.session_state.setdefault("nav", "Voice Interface")

    ctx = ui.build_context()

    with st.sidebar:
        st.markdown(f"## 🧠 {ui.esc(ctx.ai_name)}")
        st.caption(f"{ctx.company['name']}")
        companies = dbm.list_companies()
        if len(companies) > 1:
            ids = [c["id"] for c in companies]
            picked = st.selectbox("Workspace", ids, index=ids.index(ctx.company_id),
                                  format_func=lambda i: next(c["name"] for c in companies if c["id"] == i))
            if picked != ctx.company_id:
                dbm.set_setting("active_company_id", str(picked))
                st.session_state.pop("wf_view", None)
                st.rerun()
        st.radio("Navigation", ui.PAGES, key="nav",
                 format_func=lambda p: f"{ui.PAGE_ICONS[p]}  {p}", label_visibility="collapsed")
        st.divider()
        if ctx.provider["live"]:
            ui.md_html(ui.badge("LIVE AI", "live"))
        else:
            ui.md_html(ui.badge("DEMO MODE", "demo"))
        svc = ss.get_service()
        ui.md_html(ui.badge("SCHEDULER ON" if svc.running else "SCHEDULER OFF", "ok" if svc.running else "warn"))
        pend = len(dbm.list_approvals(ctx.company_id, status="pending"))
        if pend and dbm.get_bool("notify_dashboard"):
            ui.md_html(ui.badge(f"{pend} APPROVAL(S) WAITING", "warn"))

    page = st.session_state["nav"]
    try:
        module = importlib.import_module(PAGE_MODULES[page])
        module.render(ctx)
    except Exception as exc:   # one broken page must never take the whole app down
        msg = config.redact(f"{type(exc).__name__}: {exc}")
        dbm.log_audit(ctx.company_id, "ui", "page_error", f"{page}: {msg}")
        st.error(f"The '{page}' page hit an error: {msg}")
        st.info("The rest of the app still works. Use the sidebar to open another page.")


main()
