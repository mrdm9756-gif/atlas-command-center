"""ATLAS Command Center - entry point.   Run with:  streamlit run app.py"""
from __future__ import annotations

import importlib

import streamlit as st

st.set_page_config(page_title="ATLAS Command Center", page_icon="🧠", layout="wide",
                   initial_sidebar_state="expanded")

import auth  # noqa: E402
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


def _login_screen(state: str) -> None:
    """Shown instead of the app until the owner signs in. Fails closed when no password is set."""
    name = ui.esc(dbm.get_setting("ai_name"))
    st.markdown(f"## 🔒 {name} Command Center")
    if state in (auth.NOT_CONFIGURED, auth.WEAK):
        if state == auth.WEAK:
            st.error(f"The ATLAS_PASSWORD you set is too short (minimum {auth.MIN_PASSWORD_LENGTH} characters).")
        else:
            st.warning("The app is locked because no owner password has been set yet.")
        st.markdown(
            "**Set your password (one time):**\n"
            "1. Streamlit Cloud: open your app -> **Manage app -> Settings -> Secrets**.\n"
            f"2. Add this line, using your own password of at least {auth.MIN_PASSWORD_LENGTH} characters:\n"
            "   `ATLAS_PASSWORD = \"your-secret-password\"`\n"
            "3. Save, then reload this page.\n\n"
            "Running on your own computer? Put `ATLAS_PASSWORD=...` in the `.env` file instead "
            "(or `ATLAS_DISABLE_LOGIN=1` to turn login off for local use only).")
        return
    left = auth.lock_seconds_left()
    if left:
        st.error(f"Too many wrong attempts. Try again in {left // 60 + 1} minute(s).")
        return
    with st.form("login_form"):
        pw = st.text_input("Owner password", type="password", max_chars=200)
        go = st.form_submit_button("Log in", type="primary")
    if go:
        ok, msg = auth.check_password(pw)
        if ok:
            auth.sign_in(st.session_state)
            st.rerun()
        else:
            st.error(msg)


def main() -> None:
    try:
        boot = _boot()
    except Exception as exc:
        st.error("ATLAS could not start its database. "
                 f"Details: {config.redact(type(exc).__name__ + ': ' + str(exc))}")
        st.info("Check that the data/ folder is writable, then restart. See README -> Troubleshooting.")
        return

    ui.inject_css()

    if not auth.is_authenticated(st.session_state):
        _login_screen(auth.status())
        return

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
        if auth.login_required():
            st.divider()
            st.caption("Signed in as owner")
            if st.button("🚪 Log out", key="logout_btn"):
                auth.sign_out(st.session_state)
                st.rerun()
        else:
            ui.md_html(ui.badge("LOGIN OFF (local only)", "warn"))

    page = st.session_state.get("nav", "Voice Interface")
    if page not in PAGE_MODULES:
        page = "Voice Interface"
    try:
        module = importlib.import_module(PAGE_MODULES[page])
        module.render(ctx)
    except Exception as exc:   # one broken page must never take the whole app down
        msg = config.redact(f"{type(exc).__name__}: {exc}")
        dbm.log_audit(ctx.company_id, "ui", "page_error", f"{page}: {msg}")
        st.error(f"The '{page}' page hit an error: {msg}")
        st.info("The rest of the app still works. Use the sidebar to open another page.")


main()
