"""Page 4: Task Center."""
from __future__ import annotations

import datetime as dt

import streamlit as st

import agents as agent_registry
import database as dbm
import models
import orchestrator as orch_mod
import ui_common as ui

AUTO = "Auto-route (the CEO decides)"


def render(ctx) -> None:
    orch = ctx.orch
    st.title("Task Center")
    st.caption("Owner request -> CEO routing -> specialised agent -> saved result -> your review.")
    ui.mode_banner(ctx)

    with st.expander("➕ New task", expanded=False):
        with st.form("new_task_form", clear_on_submit=True):
            text = st.text_area("Describe the task", height=100)
            enabled = [agent_registry.get_agent(k) for k in orch.enabled_agent_keys()]
            names = {a.name: a.key for a in enabled}
            choice = st.selectbox("Assign to", [AUTO] + list(names))
            c1, c2, c3 = st.columns(3)
            priority = c1.selectbox("Priority", models.PRIORITIES, index=1)
            use_due = c2.checkbox("Set a due date")
            due = c3.date_input("Due date", value=dt.date.today() + dt.timedelta(days=3))
            run_now = st.checkbox("Run it now", value=True)
            submit = st.form_submit_button("Create task")
        if submit:
            key = None if choice == AUTO else names[choice]
            with st.spinner("Working..."):
                ok, out = ui.run_safely(orch.submit_request, text, key, run=run_now, priority=priority,
                                        due_date=due.isoformat() if use_due else None)
            if ok:
                ag = agent_registry.get_agent(out["agent_key"])
                st.info(f"Task #{out['task_id']} -> {ag.name}. {out['reason']}")
                if out["status"] == models.FAILED:
                    st.error(f"Failed: {out.get('error', '')}")
                elif out["status"] == models.WAITING_APPROVAL:
                    st.warning("External action detected. Nothing was done externally - review it in Approvals.")
                else:
                    st.success(f"Status: {out['status']}")

    tasks_all = dbm.list_tasks(ctx.company_id, limit=1000)
    counts = {s: sum(1 for t in tasks_all if t["status"] == s) for s in models.TASK_STATUSES}
    cols = st.columns(len(models.TASK_STATUSES))
    for col, s in zip(cols, models.TASK_STATUSES):
        col.metric(s, counts[s])

    c1, c2, c3 = st.columns([3, 2, 2])
    status_filter = c1.multiselect("Filter by status", models.TASK_STATUSES, default=[])
    agent_names = {a.name: a.key for a in agent_registry.all_agents()}
    agent_filter = c2.selectbox("Filter by agent", ["All agents"] + list(agent_names))
    with c3:
        st.write("")
        if st.button(f"Run all queued tasks ({counts[models.QUEUED]})", key="run_all_q", disabled=counts[models.QUEUED] == 0):
            with st.spinner("Running queued tasks..."):
                outcomes = orch.run_queued()
            for o in outcomes:
                (st.error if o["status"] in (models.FAILED, "skipped") else st.success)(
                    f"Task #{o['task_id']}: {o['status']} {o.get('error', '')}")

    shown = [t for t in tasks_all
             if (not status_filter or t["status"] in status_filter)
             and (agent_filter == "All agents" or t["agent_key"] == agent_names[agent_filter])]
    if not shown:
        ui.empty_state("No tasks match.", "Create a task above, or clear the filters.")
        return
    st.dataframe(ui.tasks_dataframe(shown, ctx.company["timezone"]), hide_index=True)

    st.subheader("Task details")
    chosen = st.selectbox("Open task", [t["id"] for t in shown],
                          format_func=lambda i: next(f"#{t['id']} - {t['title'][:70]}" for t in shown if t["id"] == i))
    task = dbm.get_task(chosen, ctx.company_id)
    if task is None:
        return
    ag = agent_registry.get_agent(task["agent_key"])
    ui.md_html(f"**{ui.esc(task['title'])}** {ui.status_badge(task['status'])} "
               + (ui.mode_badge(task["result_mode"]) if task["result_mode"] else "")
               + f'<div class="muted">Assigned to {ui.esc(ag.name if ag else task["agent_key"])} | priority {ui.esc(task["priority"])} | '
                 f'due {ui.esc(task["due_date"] or "-")} | source {ui.esc(task["source"])} | attempts {task["attempts"]}/{orch_mod.MAX_TASK_ATTEMPTS}</div>')
    if task["description"]:
        st.markdown("**Request**")
        st.write(task["description"])
    if task["error"]:
        st.error(f"Error: {task['error']}")
    if task["result"]:
        st.markdown("**Result**")
        st.markdown(task["result"])
        st.download_button("Download result (.txt)", task["result"], file_name=f"task_{task['id']}.txt", key=f"dl_task_{task['id']}")
    if task["status"] == models.WAITING_APPROVAL:
        st.warning("This task is waiting for your approval of an external action.")
        if st.button("Go to Approvals", key="task_to_appr"):
            ui.goto("Approvals")

    b1, b2, b3 = st.columns(3)
    can_run = task["status"] in (models.QUEUED, models.DRAFT, models.FAILED) and task["attempts"] < orch_mod.MAX_TASK_ATTEMPTS
    with b1:
        label = "Retry" if task["status"] == models.FAILED else "Run now"
        if st.button(label, key=f"run_{task['id']}", disabled=not can_run):
            with st.spinner("Working..."):
                ok, out = ui.run_safely(orch.execute_task, task["id"])
            if ok:
                st.rerun()
    with b2:
        if st.button("Cancel task", key=f"cancel_{task['id']}", disabled=task["status"] not in models.OPEN_STATUSES):
            ok, _ = ui.run_safely(orch.cancel_task, task["id"])
            if ok:
                st.rerun()
    with b3:
        if task["status"] == models.FAILED and task["attempts"] >= orch_mod.MAX_TASK_ATTEMPTS:
            st.caption("Retry limit reached. Create a new task to try again.")
