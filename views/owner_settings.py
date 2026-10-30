"""Page 10: Owner Settings - names, company, industry, agents/permissions, schedules, notifications."""
from __future__ import annotations

import datetime as dt

import streamlit as st

import agents as agent_registry
import config
import database as dbm
import emailer
import industries
import models
import scheduler_service as ss
import ui_common as ui
import voice_service


def render(ctx) -> None:
    st.title("Owner Settings")
    ui.mode_banner(ctx)
    tabs = st.tabs(["General", "Agents and permissions", "Scheduled reports", "Notifications", "Workspaces"])
    with tabs[0]:
        _general(ctx)
    with tabs[1]:
        _agents(ctx)
    with tabs[2]:
        _schedules(ctx)
    with tabs[3]:
        _notifications(ctx)
    with tabs[4]:
        _workspaces(ctx)


# --------------------------------------------------------------------------- #
def _general(ctx) -> None:
    company = ctx.company
    langs = ["English", "Filipino / Tagalog", "Spanish", "French", "German", "Portuguese", "Japanese",
             "Korean", "Chinese", "Hindi", "Arabic", "Indonesian", "Italian", "Russian"]
    zones = models.all_timezones()
    with st.form("general_form"):
        st.markdown("**Names** (saved once, used everywhere: greetings, chats, reports)")
        c1, c2 = st.columns(2)
        ai_name = c1.text_input("AI CEO display name", value=ctx.ai_name, max_chars=40)
        owner_name = c2.text_input("Your display name", value=ctx.owner_name, max_chars=40)
        st.markdown("**Company**")
        name = st.text_input("Company name", value=company["name"], max_chars=80)
        inds = industries.INDUSTRY_NAMES
        industry = st.selectbox("Industry", inds, index=inds.index(company["industry"]) if company["industry"] in inds else 0)
        custom_ind = st.text_input("Custom industry name (used when Industry = Custom Industry)", value=company["custom_industry"], max_chars=60)
        c3, c4 = st.columns(2)
        language = c3.selectbox("Preferred language for AI replies", langs, index=langs.index(company["language"]) if company["language"] in langs else 0)
        tz_default = company["timezone"] if company["timezone"] in zones else config.DEFAULT_TIMEZONE
        tz = c4.selectbox("Time zone", zones, index=zones.index(tz_default) if tz_default in zones else 0)
        saved = st.form_submit_button("Save settings")
    if saved:
        try:
            ai_clean = models.clean_name(ai_name, field="AI CEO name", max_len=40)
            owner_clean = models.clean_name(owner_name, field="Your name", max_len=40)
            if industry == industries.CUSTOM and not custom_ind.strip():
                raise models.ValidationError("Enter a name for your custom industry.")
            dbm.update_company(ctx.company_id, name=models.clean_name(name, field="Company name", max_len=80),
                               industry=industry, custom_industry=models.clean_text(custom_ind, max_len=60),
                               language=language, timezone=tz)
            dbm.set_setting("ai_name", ai_clean)
            dbm.set_setting("owner_name", owner_clean)
            dbm.log_audit(ctx.company_id, "owner", "settings_saved", f"ai_name={ai_clean}")
            sync_scheduler()
            st.success("Saved. The new names appear everywhere immediately.")
            st.rerun()
        except models.ValidationError as exc:
            st.error(str(exc))


def sync_scheduler() -> None:
    svc = ss.get_service()
    if svc.running:
        svc.sync()


# --------------------------------------------------------------------------- #
def _agents(ctx) -> None:
    st.caption("Permissions are enforced by the app, not just by instructions to the AI. "
               "A disabled agent never runs. An agent without 'internal tasks' permission cannot start work on its own.")
    states = dbm.list_agent_states(ctx.company_id)
    with st.form("agents_form"):
        header = st.columns([3, 1, 2, 2])
        header[0].markdown("**Agent**")
        header[1].markdown("**Enabled**")
        header[2].markdown("**May run internal tasks**")
        header[3].markdown("**May request external actions**")
        values = {}
        for ag in agent_registry.all_agents():
            s = states.get(ag.key, {})
            row = st.columns([3, 1, 2, 2])
            row[0].write(f"{ag.icon} {ag.name}")
            values[ag.key] = (row[1].checkbox("on", value=bool(s.get("enabled", 1)), key=f"en_{ag.key}", label_visibility="collapsed"),
                              row[2].checkbox("internal", value=bool(s.get("allow_internal_tasks", 1)), key=f"int_{ag.key}", label_visibility="collapsed"),
                              row[3].checkbox("external", value=bool(s.get("allow_external_requests", 1)), key=f"ext_{ag.key}", label_visibility="collapsed"))
        saved = st.form_submit_button("Save agent permissions")
    st.caption("Even with 'external' ticked, an external action is only ever a REQUEST that waits for your approval.")
    if saved:
        if not any(v[0] for v in values.values()):
            st.error("Keep at least one agent enabled.")
        else:
            for key, (en, internal, external) in values.items():
                dbm.update_agent_state(ctx.company_id, key, enabled=int(en), allow_internal_tasks=int(internal),
                                       allow_external_requests=int(external))
            dbm.log_audit(ctx.company_id, "owner", "agent_permissions_saved", "")
            st.success("Agent permissions saved.")


# --------------------------------------------------------------------------- #
def _schedules(ctx) -> None:
    svc = ss.get_service()
    if not svc.available:
        st.error("APScheduler is not installed, so automatic scheduling is unavailable. "
                 "Run: pip install -r requirements.txt. You can still generate reports manually.")
    elif svc.running:
        ui.md_html(ui.badge("SCHEDULER RUNNING (inside this app)", "ok"))
    else:
        ui.md_html(ui.badge("SCHEDULER NOT RUNNING", "error"))
    st.warning("Schedules fire only while this app (or `python worker.py`) is running. If the app sleeps or is "
               "stopped, no report is generated. See System Health for always-on deployment advice.")
    tz = ctx.company["timezone"]
    enabled_agents = ctx.orch.enabled_agent_keys()
    for kind in models.SCHEDULE_KINDS:
        s = dbm.get_schedule(ctx.company_id, kind) or {}
        with st.expander(f"{kind.title()} report" + (" (enabled)" if s.get("enabled") else ""), expanded=kind == "daily"):
            with st.form(f"sched_{kind}"):
                on = st.checkbox("Enable", value=bool(s.get("enabled", 0)))
                c1, c2, c3 = st.columns(3)
                t = c1.time_input("Time", value=dt.time(s.get("hour", 8), s.get("minute", 0)), step=60)
                weekday = 0
                dom = 1
                if kind == "weekly":
                    weekday = c2.selectbox("Weekday", list(range(7)), index=int(s.get("weekday", 0)), format_func=lambda i: models.WEEKDAYS[i])
                if kind == "monthly":
                    dom = c2.number_input("Day of month (1-28 so every month has it)", min_value=1, max_value=28, value=min(28, int(s.get("day_of_month", 1))))
                all_agents = st.checkbox("All enabled agents report", value=s.get("agent_keys", "all") == "all")
                chosen = [k for k in (s.get("agent_keys") or "").split(",") if k in enabled_agents] if s.get("agent_keys", "all") != "all" else []
                picks = st.multiselect("...or only these agents", enabled_agents, default=chosen,
                                       format_func=lambda k: agent_registry.get_agent(k).name)
                d1, d2, d3, d4 = st.columns(4)
                inc_tasks = d1.checkbox("Completed and pending tasks", value=bool(s.get("include_tasks", 1)))
                inc_fin = d2.checkbox("Financial metrics (if data)", value=bool(s.get("include_financials", 1)))
                ceo = d3.checkbox("CEO executive summary", value=bool(s.get("ceo_summary", 1)))
                dash = d4.checkbox("Show in dashboard", value=bool(s.get("show_in_dashboard", 1)))
                email_on = st.checkbox("Also email this report (needs SMTP configured)", value=bool(s.get("email_enabled", 0)))
                email_to = st.text_input("Email recipients (comma separated)", value=s.get("email_to", ""))
                saved = st.form_submit_button(f"Save {kind} schedule")
            if saved:
                try:
                    if email_on:
                        if not config.smtp_configured():
                            st.warning("SMTP is not configured, so emails will NOT be sent. The report will still be saved in the dashboard.")
                        recips = emailer.parse_recipients(email_to)
                        if not recips or not all(emailer.valid_email(r) for r in recips):
                            raise models.ValidationError("Enter valid email addresses for email delivery.")
                    if not all_agents and not picks:
                        raise models.ValidationError("Choose at least one agent, or tick 'All enabled agents'.")
                    dbm.upsert_schedule(
                        ctx.company_id, kind, enabled=int(on), hour=t.hour, minute=t.minute, weekday=int(weekday),
                        day_of_month=int(dom), agent_keys="all" if all_agents else ",".join(picks),
                        include_tasks=int(inc_tasks), include_financials=int(inc_fin), ceo_summary=int(ceo),
                        show_in_dashboard=int(dash), email_enabled=int(email_on), email_to=models.clean_text(email_to, max_len=300))
                    dbm.log_audit(ctx.company_id, "owner", "schedule_saved", f"{kind} enabled={on}")
                    sync_scheduler()
                    st.success(f"{kind.title()} schedule saved." + ("" if svc.running else " (The scheduler is not running right now, so it will not fire yet.)"))
                except models.ValidationError as exc:
                    st.error(str(exc))
            saved_s = dbm.get_schedule(ctx.company_id, kind)
            if saved_s:
                nxt = ss.next_run(saved_s, tz)
                st.caption(f"{ss.describe(saved_s)} ({tz}). Next run: {nxt.strftime('%Y-%m-%d %H:%M') if nxt else 'disabled'}. "
                           f"Last result: {saved_s['last_status'] or 'never run'}")
                if st.button("Run this report now (test)", key=f"runnow_{kind}"):
                    with st.spinner("Generating..."):
                        res = ss.run_scheduled_report(saved_s["id"], manual=True)
                    st.success(f"Report #{res['report_id']} generated. {res['delivery']}") if res.get("ran") else st.error(res.get("reason", "Failed"))


# --------------------------------------------------------------------------- #
def _notifications(ctx) -> None:
    st.caption("Notifications are in-app only unless email is configured. Nothing is pushed to your phone in this version.")
    with st.form("notif_form"):
        dash = st.checkbox("Show alerts (approvals waiting, failed tasks, overdue tasks) in the dashboard", value=dbm.get_bool("notify_dashboard"))
        email = st.checkbox("Email me when approvals are waiting (needs SMTP)", value=dbm.get_bool("notify_email"))
        to = st.text_input("Notification email", value=dbm.get_setting("notify_email_to"))
        saved = st.form_submit_button("Save notification settings")
    if saved:
        if email and not emailer.valid_email(to):
            st.error("Enter a valid email address.")
        else:
            dbm.set_setting("notify_dashboard", "1" if dash else "0")
            dbm.set_setting("notify_email", "1" if email else "0")
            dbm.set_setting("notify_email_to", to.strip())
            st.success("Saved.")
            if email and not config.smtp_configured():
                st.warning("SMTP is not configured, so notification emails cannot be sent yet.")
    st.info("Email-on-approval is stored as a preference only in this version; the dashboard alerts are what is active.")


def _workspaces(ctx) -> None:
    st.caption("Each workspace (company) has completely separate agents, tasks, chats, reports, schedules and data. "
               "Switch workspace from the sidebar.")
    for c in dbm.list_companies():
        marker = " (active)" if c["id"] == ctx.company_id else ""
        st.write(f"- **{c['name']}**{marker} - {industries.display_name(c)} - {c['timezone']}")
    with st.form("new_workspace"):
        name = st.text_input("New company/workspace name", max_chars=80)
        ind = st.selectbox("Industry", industries.INDUSTRY_NAMES, key="ws_ind")
        go = st.form_submit_button("Create workspace")
    if go:
        ok, cid = ui.run_safely(dbm.create_company, name, ind)
        if ok:
            dbm.set_setting("active_company_id", str(cid))
            dbm.log_audit(cid, "owner", "workspace_created", name)
            st.rerun()
