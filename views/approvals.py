"""Page 11: Approvals - every external/consequential action waits here."""
from __future__ import annotations

import streamlit as st

import agents as agent_registry
import database as dbm
import models
import ui_common as ui


def render(ctx) -> None:
    tz = ctx.company["timezone"]
    st.title("Approvals")
    ui.mode_banner(ctx)
    st.info("Agents only PREPARE work. Anything that affects the outside world waits here for your explicit decision, "
            "tied to one task and one defined action. **In this version approving only records your decision - no "
            "external integration is connected, so nothing is sent, published, bought or paid.** "
            "Actions involving money are blocked and can only be rejected.")

    pending = dbm.list_approvals(ctx.company_id, status=models.APPROVAL_PENDING)
    st.subheader(f"Waiting for you ({len(pending)})")
    if not pending:
        ui.empty_state("Nothing is waiting for approval.")
    for ap in pending:
        spec = models.EXTERNAL_ACTIONS[ap["action_type"]]
        task = dbm.get_task(ap["task_id"], ctx.company_id)
        with st.container(border=True):
            ui.md_html(f"**Approval #{ap['id']}: {ui.esc(spec['label'])}** " + ui.badge(f"Task #{ap['task_id']}", "info")
                       + (ui.badge("BLOCKED IN THIS VERSION", "error") if spec["blocked"] else ""))
            st.write(f"**Target:** {ap['target']}")
            st.write(f"**Amount:** {ap['amount'] or 'none stated'}")
            st.write(f"**Scope:** {ap['scope']}")
            st.write(f"**Expected consequence:** {ap['consequence']}")
            st.caption(f"Requested by {ap['requested_by'] or 'owner'} on {models.fmt_local(ap['created_at'], tz)}")
            if task and task["result"]:
                with st.expander("Prepared draft / agent result"):
                    ui.md_html(ui.mode_badge(task["result_mode"]))
                    st.markdown(task["result"])
            note = st.text_input("Note (optional)", key=f"note_{ap['id']}")
            c1, c2, _ = st.columns([1, 1, 3])
            with c1:
                if st.button("Approve", key=f"ok_{ap['id']}", type="primary", disabled=spec["blocked"]):
                    ok, _res = ui.run_safely(ctx.orch.decide, ap["id"], True, note)
                    if ok:
                        st.rerun()
            with c2:
                if st.button("Reject", key=f"no_{ap['id']}"):
                    ok, _res = ui.run_safely(ctx.orch.decide, ap["id"], False, note)
                    if ok:
                        st.rerun()

    with st.expander("Request an external action manually"):
        open_tasks = [t for t in dbm.list_tasks(ctx.company_id, limit=300) if t["status"] in models.OPEN_STATUSES + [models.COMPLETED]]
        if not open_tasks:
            st.caption("Create a task first - every approval must be tied to a task ID.")
        else:
            with st.form("manual_approval"):
                tid = st.selectbox("Task", [t["id"] for t in open_tasks],
                                   format_func=lambda i: next(f"#{t['id']} {t['title'][:60]}" for t in open_tasks if t["id"] == i))
                kinds = list(models.EXTERNAL_ACTIONS)
                action = st.selectbox("Action", kinds, format_func=lambda k: models.EXTERNAL_ACTIONS[k]["label"])
                target = st.text_input("Exact target (who/what/where)")
                amount = st.text_input("Amount (if any)")
                scope = st.text_area("Exact scope (what precisely would happen)", height=70)
                go = st.form_submit_button("Create approval request")
            if go:
                from orchestrator import CONSEQUENCES
                ok, aid = ui.run_safely(ctx.orch.request_approval, tid, action, target, scope, amount, CONSEQUENCES[action], "owner")
                if ok:
                    st.success(f"Approval #{aid} created for task #{tid}.")
                    st.rerun()

    st.subheader("History")
    done = [a for a in dbm.list_approvals(ctx.company_id) if a["status"] != models.APPROVAL_PENDING]
    if not done:
        st.caption("No decisions yet.")
    for ap in done:
        spec = models.EXTERNAL_ACTIONS[ap["action_type"]]
        kind = "ok" if ap["status"] == models.APPROVAL_APPROVED else "error"
        ui.md_html(f"#{ap['id']} {ui.esc(spec['label'])} - task #{ap['task_id']} {ui.badge(ap['status'].upper(), kind)}"
                   f'<div class="muted">{ui.esc(ap["execution_note"])} Decided {ui.esc(models.fmt_local(ap["decided_at"], tz))}.'
                   + (f" Note: {ui.esc(ap['decision_note'])}" if ap["decision_note"] else "") + "</div>")
