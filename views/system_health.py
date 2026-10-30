"""Page 12: System Health."""
from __future__ import annotations

import platform
import sys

import streamlit as st

import config
import database as dbm
import integrations
import models
import scheduler_service as ss
import ui_common as ui


def render(ctx) -> None:
    st.title("System Health")
    ui.mode_banner(ctx)
    p = ctx.provider

    st.subheader("AI provider")
    if p["live"]:
        st.success(f"Live AI connected: {p['provider']} (model {p['model']}). The API key is configured and is never displayed.")
    else:
        st.warning("Demo mode: no live AI. All AI text is simulated and labelled DEMO.")
        if p["forced_demo"]:
            st.caption("ATLAS_FORCE_DEMO is set, so the API key (if any) is ignored.")
        st.markdown("**Add a Gemini API key securely**\n"
                    "1. Create a key at Google AI Studio.\n"
                    "2. Local run: copy `.env.example` to `.env` and put `GEMINI_API_KEY=your-key` in it.\n"
                    "3. Streamlit Community Cloud: App settings -> Secrets -> `GEMINI_API_KEY = \"your-key\"`.\n"
                    "4. Restart the app. Never paste the key into chat or commit `.env`.")

    st.subheader("Scheduler")
    svc = ss.get_service()
    if not svc.available:
        st.error("APScheduler is not installed. Schedules cannot fire automatically.")
    elif svc.running:
        st.success("Scheduler running inside this app process.")
        jobs = svc.jobs()
        if jobs:
            st.table(jobs)
        else:
            st.caption("No enabled schedules.")
    else:
        st.error("Scheduler is not running.")
    st.warning("**Hosting limitation:** this scheduler lives inside the app process. If the app sleeps, restarts or is "
               "stopped, scheduled reports do not run. For reliable production schedules run `python worker.py` on an "
               "always-on machine (VPS, Docker, Railway/Render worker, or a systemd service) pointed at the same database.")

    st.subheader("Integrations")
    for row in integrations.integration_status():
        kind = {"Connected": "ok", "Disconnected": "warn"}.get(row["status"], "system")
        ui.md_html(f"**{ui.esc(row['name'])}** {ui.badge(row['status'], kind)} "
                   f'<span class="muted">{ui.esc(row["detail"])}</span>')

    st.subheader("Database")
    path = config.db_path()
    size = path.stat().st_size / 1024 if path.exists() else 0
    st.write(f"SQLite file: `{path}` ({size:,.0f} KB). Back this file up regularly.")
    counts = {}
    for table in ("companies", "tasks", "conversations", "agent_reports", "consolidated_reports",
                  "scheduled_reports", "approval_requests", "audit_logs", "datasets"):
        row = dbm.query_one(f"SELECT COUNT(*) AS n FROM {table}")
        counts[table] = row["n"] if row else 0
    st.table(counts)
    st.caption("Streamlit Community Cloud has an ephemeral disk: the SQLite file can be wiped on restart. "
               "Use a persistent host or PostgreSQL for real use (see README).")

    st.subheader("Maintenance")
    if st.button("Fix stuck tasks (mark old 'In Progress' tasks as Failed)", key="fix_stale"):
        n = ctx.orch.recover_stale_tasks()
        st.success(f"{n} stuck task(s) recovered.")

    st.subheader("Recent audit log")
    rows = dbm.list_audit(ctx.company_id, limit=40)
    if rows:
        st.dataframe([{"When": models.fmt_local(r["created_at"], ctx.company["timezone"]), "Who": r["actor"],
                       "Action": r["action"], "Detail": r["detail"]} for r in rows], hide_index=True)
    else:
        ui.empty_state("No audit entries yet.")

    st.caption(f"{config.APP_NAME} {config.APP_VERSION} | Python {sys.version.split()[0]} on {platform.system()} | Streamlit {st.__version__}")
