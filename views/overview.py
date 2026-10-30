"""Page 2: Overview dashboard."""
from __future__ import annotations

import streamlit as st

import agents as agent_registry
import database as dbm
import integrations
import models
import ui_common as ui
from views import industry


def render(ctx) -> None:
    orch = ctx.orch
    st.title(f"{ctx.ai_name} Command Center")
    st.caption(ctx.greeting())
    ui.mode_banner(ctx)

    snap = orch.snapshot()
    c = snap["counts"]
    cols = st.columns(6)
    cols[0].metric("Queued", c[models.QUEUED])
    cols[1].metric("In progress", c[models.IN_PROGRESS])
    cols[2].metric("Awaiting approval", c[models.WAITING_APPROVAL])
    cols[3].metric("Completed", c[models.COMPLETED])
    cols[4].metric("Failed", c[models.FAILED])
    cols[5].metric("Overdue", len(snap["overdue"]))

    tasks = dbm.list_tasks(ctx.company_id, limit=1000)
    live_n = sum(1 for t in tasks if t["status"] == models.COMPLETED and t["result_mode"] == models.MODE_LIVE)
    demo_n = sum(1 for t in tasks if t["status"] == models.COMPLETED and t["result_mode"] == models.MODE_DEMO)
    connected, total = integrations.connected_count()
    with st.expander("What am I looking at? (real vs. simulated)", expanded=False):
        ui.md_html(
            f'{ui.badge("AI-GENERATED", "live")} results from a live AI model: <b>{live_n}</b><br>'
            f'{ui.badge("DEMO - SIMULATED", "demo")} template results, no AI model used: <b>{demo_n}</b><br>'
            f'{ui.badge("IN PROGRESS", "info")} tasks being worked on right now: <b>{c[models.IN_PROGRESS]}</b><br>'
            f'{ui.badge("COMPLETED", "ok")} internal tasks finished: <b>{c[models.COMPLETED]}</b><br>'
            f'{ui.badge("WAITING", "warn")} external actions awaiting YOUR approval: <b>{c[models.WAITING_APPROVAL]}</b><br>'
            f'{ui.badge("INTEGRATIONS", "system")} connected: <b>{connected}</b> of {total} (see System Health)')

    left, right = st.columns([3, 2])
    with left:
        st.subheader(f"Give {ctx.ai_name} an instruction")
        with st.form("quick_command", clear_on_submit=True):
            text = st.text_area("What should the team work on?", height=90,
                                placeholder="e.g. Marketing Agent, prepare a 7-day campaign for my restaurant")
            run_now = st.checkbox("Run it now", value=True)
            sent = st.form_submit_button("Send to the AI CEO")
        if sent:
            with st.spinner(f"{ctx.ai_name} is routing your request..."):
                ok, out = ui.run_safely(orch.submit_request, text, None, run=run_now)
            if ok:
                ag = agent_registry.get_agent(out["agent_key"])
                st.info(f"Routed to **{ag.name}** as task #{out['task_id']}. {out['reason']}")
                if out["status"] == models.FAILED:
                    st.error(f"The task failed: {out.get('error', '')}")
                elif out["status"] == models.WAITING_APPROVAL:
                    st.warning("This involves an external action. Review it in **Approvals** - nothing has been done externally.")
                else:
                    st.success(f"Status: {out['status']}. Open Task Center to read the result.")

        st.subheader("Task queue")
        open_tasks = [t for t in tasks if t["status"] in models.OPEN_STATUSES][:10]
        if open_tasks:
            st.dataframe(ui.tasks_dataframe(open_tasks, ctx.company["timezone"]), hide_index=True)
        else:
            ui.empty_state("No open tasks.", "Send an instruction above to create one.")

        st.subheader("Report activity")
        reports = dbm.list_consolidated(ctx.company_id, limit=5)
        if reports:
            for r in reports:
                ui.md_html(f"**{ui.esc(r['title'])}** {ui.mode_badge(r['mode'])} "
                           f'<span class="muted">{ui.esc(models.fmt_local(r["created_at"], ctx.company["timezone"]))} | '
                           f'{r["completed_count"]} ok, {r["failed_count"]} failed | {ui.esc(r["delivery"])}</span>')
        else:
            ui.empty_state("No reports yet.", "Generate one in Reports Center or schedule reports in Owner Settings.")

    with right:
        st.subheader("Agents")
        states = dbm.list_agent_states(ctx.company_id)
        for ag in agent_registry.all_agents():
            s = states.get(ag.key, {})
            if not s.get("enabled", 1):
                dot, label = "off", "disabled"
            elif s.get("status") == "working":
                dot, label = "working", "working"
            else:
                dot, label = "idle", "idle"
            ui.md_html(f'<span class="dot dot-{dot}"></span>{ag.icon} {ui.esc(ag.name)} '
                       f'<span class="muted">{label}</span>')
        if snap["pending_approvals"]:
            st.warning(f"{len(snap['pending_approvals'])} action(s) need your approval.")
            if st.button("Open Approvals", key="ov_open_appr"):
                ui.goto("Approvals")
        if snap["overdue"]:
            st.error(f"{len(snap['overdue'])} overdue task(s).")

        st.subheader("Integrations")
        for row in integrations.integration_status()[:6]:
            kind = {"Connected": "ok", "Disconnected": "warn"}.get(row["status"], "system")
            ui.md_html(f"{ui.esc(row['name'])} {ui.badge(row['status'], kind)}")

        st.subheader("Recent activity")
        for a in dbm.list_audit(ctx.company_id, limit=8):
            ui.md_html(f'<span class="muted">{ui.esc(models.fmt_local(a["created_at"], ctx.company["timezone"]))}</span> '
                       f'{ui.esc(a["actor"])}: {ui.esc(a["action"])} {ui.esc(a["detail"])[:70]}')

    st.subheader("Industry KPIs")
    industry.render_kpis(ctx, "overview")
