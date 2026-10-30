"""Page 5: Reports Center."""
from __future__ import annotations

import datetime as dt
import io

import pandas as pd
import streamlit as st

import agents as agent_registry
import database as dbm
import models
import scheduler_service as ss
import ui_common as ui


def _range_iso(start: dt.date | None, end: dt.date | None) -> tuple[str | None, str | None]:
    s = dt.datetime.combine(start, dt.time.min, tzinfo=dt.timezone.utc).isoformat() if start else None
    e = dt.datetime.combine(end, dt.time.max, tzinfo=dt.timezone.utc).isoformat() if end else None
    return s, e


def _csv(df: pd.DataFrame) -> str:
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue()


def render(ctx) -> None:
    tz = ctx.company["timezone"]
    st.title("Reports Center")
    ui.mode_banner(ctx)

    # ---- schedule summary ------------------------------------------------
    with st.expander("Scheduled reports status"):
        scheds = dbm.list_schedules(ctx.company_id)
        if not scheds:
            st.info("No schedules saved yet. Configure them in Owner Settings -> Scheduled Reports.")
        for s in scheds:
            nxt = ss.next_run(s, tz)
            state = ("enabled" if s["enabled"] else "disabled")
            st.write(f"**{s['kind'].title()}**: {ss.describe(s)} ({state}). Next run: "
                     f"{nxt.strftime('%Y-%m-%d %H:%M') if nxt else '-'}. Last result: {s['last_status'] or 'never run'}")
        st.caption("Reminder: scheduled reports run only while the app (or worker.py) is running. See System Health.")

    # ---- generate now ------------------------------------------------------
    with st.expander("Generate a consolidated CEO report now"):
        with st.form("gen_report"):
            kind = st.selectbox("Report type", ["daily", "weekly", "monthly", "adhoc"])
            enabled = ctx.orch.enabled_agent_keys()
            picks = st.multiselect("Agents to include", enabled, default=enabled,
                                   format_func=lambda k: agent_registry.get_agent(k).name)
            c1, c2, c3 = st.columns(3)
            inc_tasks = c1.checkbox("Include tasks", value=True)
            inc_fin = c2.checkbox("Include financial metrics when data exists", value=True)
            ceo_sum = c3.checkbox("CEO executive summary", value=True)
            go = st.form_submit_button("Generate report")
        if go:
            with st.spinner("The agents are preparing their reports..."):
                ok, cid = ui.run_safely(ctx.orch.generate_consolidated, kind, picks or None,
                                        include_tasks=inc_tasks, include_financials=inc_fin, ceo_summary=ceo_sum)
            if ok:
                st.success(f"Report #{cid} saved. Scroll down to read it.")

    # ---- filters -----------------------------------------------------------
    f1, f2, f3 = st.columns([2, 2, 3])
    start = f1.date_input("From", value=None, key="rep_from")
    end = f2.date_input("To", value=None, key="rep_to")
    search = f3.text_input("Search reports", key="rep_search")
    since, until = _range_iso(start if isinstance(start, dt.date) else None, end if isinstance(end, dt.date) else None)
    search = search.strip() or None

    tabs = st.tabs(["CEO reports", "Daily / Weekly / Monthly", "Agent reports", "Task summaries", "Failed logs", "Approval history"])

    # ---- consolidated ------------------------------------------------------
    with tabs[0]:
        rows = dbm.list_consolidated(ctx.company_id, None, since, until, search)
        _show_consolidated(ctx, rows, "all")
    with tabs[1]:
        kind = st.radio("Type", ["daily", "weekly", "monthly"], horizontal=True, key="rep_kind")
        rows = dbm.list_consolidated(ctx.company_id, kind, since, until, search)
        _show_consolidated(ctx, rows, kind)

    # ---- agent reports -----------------------------------------------------
    with tabs[2]:
        names = {a.name: a.key for a in agent_registry.all_agents()}
        pick = st.selectbox("Agent", ["All agents"] + list(names), key="rep_agent")
        reports = dbm.list_agent_reports(ctx.company_id, names.get(pick), None, since, until, search)
        if not reports:
            ui.empty_state("No agent reports match.")
        else:
            df = pd.DataFrame([{"ID": r["id"], "Agent": r["agent_key"], "Type": r["report_type"], "Title": r["title"],
                                "Status": r["status"], "Content type": r["mode"], "Data": r["data_label"],
                                "Created": models.fmt_local(r["created_at"], tz)} for r in reports])
            st.dataframe(df, hide_index=True)
            st.download_button("Download list (CSV)", _csv(df), file_name="agent_reports.csv", key="dl_agent_csv")
            for r in reports[:25]:
                with st.expander(f"#{r['id']} {r['title']} [{r['status']}]"):
                    ui.md_html(ui.mode_badge(r["mode"]) + ui.data_badge(r["data_label"]))
                    st.caption(f"Source data: {r['source_data'] or '-'} | Period: {models.fmt_local(r['period_start'], tz)} to {models.fmt_local(r['period_end'], tz)}")
                    st.error(r["error"]) if r["status"] == "failed" else st.markdown(r["content"])
                    if r["content"]:
                        st.download_button("Download (.txt)", r["content"], file_name=f"agent_report_{r['id']}.txt", key=f"dl_ar_{r['id']}")

    # ---- task summaries ----------------------------------------------------
    with tabs[3]:
        done = [t for t in dbm.list_tasks(ctx.company_id, status=models.COMPLETED, limit=500)
                if (not since or t["updated_at"] >= since) and (not until or t["updated_at"] <= until)
                and (not search or search.lower() in (t["title"] + t["result"]).lower())]
        if not done:
            ui.empty_state("No completed tasks in this range.")
        else:
            df = ui.tasks_dataframe(done, tz)
            st.dataframe(df, hide_index=True)
            st.download_button("Download task summary (CSV)", _csv(df), file_name="task_summary.csv", key="dl_tasks_csv")

    # ---- failed logs -------------------------------------------------------
    with tabs[4]:
        failed_tasks = dbm.list_tasks(ctx.company_id, status=models.FAILED, limit=300)
        failed_reports = dbm.list_agent_reports(ctx.company_id, status="failed", limit=300)
        rows = ([{"When": models.fmt_local(t["updated_at"], tz), "Kind": "Task", "Ref": f"#{t['id']} {t['title']}", "Error": t["error"]} for t in failed_tasks]
                + [{"When": models.fmt_local(r["created_at"], tz), "Kind": "Report", "Ref": r["title"], "Error": r["error"]} for r in failed_reports])
        if not rows:
            ui.empty_state("No failures recorded.", "Good news - or nothing has run yet.")
        else:
            df = pd.DataFrame(rows)
            st.dataframe(df, hide_index=True)
            st.download_button("Download failure log (CSV)", _csv(df), file_name="failed_log.csv", key="dl_failed_csv")

    # ---- approval history --------------------------------------------------
    with tabs[5]:
        aps = dbm.list_approvals(ctx.company_id)
        if not aps:
            ui.empty_state("No approval requests yet.")
        else:
            df = pd.DataFrame([{"ID": a["id"], "Task": a["task_id"], "Action": models.EXTERNAL_ACTIONS[a["action_type"]]["label"],
                                "Target": a["target"], "Amount": a["amount"], "Decision": a["status"],
                                "Executed externally?": "NO" if a["execution_status"] == "not_executed" else a["execution_status"],
                                "Requested": models.fmt_local(a["created_at"], tz),
                                "Decided": models.fmt_local(a["decided_at"], tz)} for a in aps])
            st.dataframe(df, hide_index=True)
            st.download_button("Download approval history (CSV)", _csv(df), file_name="approvals.csv", key="dl_appr_csv")


def _show_consolidated(ctx, rows: list[dict], tag: str) -> None:
    tz = ctx.company["timezone"]
    if not rows:
        ui.empty_state("No consolidated reports match.", "Generate one above, or enable a schedule in Owner Settings.")
        return
    df = pd.DataFrame([{"ID": r["id"], "Title": r["title"], "Type": r["report_type"], "Content type": r["mode"],
                        "Completed": r["completed_count"], "Failed": r["failed_count"], "Figures": r["data_label"],
                        "Delivery": r["delivery"], "Created": models.fmt_local(r["created_at"], tz)} for r in rows])
    st.dataframe(df, hide_index=True)
    st.download_button("Download list (CSV)", _csv(df), file_name=f"ceo_reports_{tag}.csv", key=f"dl_ceo_csv_{tag}")
    for r in rows[:15]:
        with st.expander(f"#{r['id']} {r['title']} - {models.fmt_local(r['created_at'], tz)}"):
            ui.md_html(ui.mode_badge(r["mode"]) + ui.data_badge(r["data_label"])
                       + ui.badge(f"{r['completed_count']} completed / {r['failed_count']} failed", "warn" if r["failed_count"] else "ok"))
            st.caption(f"Delivery: {r['delivery']}")
            st.markdown(r["content"])
            st.download_button("Download (.txt)", r["content"], file_name=f"ceo_report_{r['id']}.txt", key=f"dl_ceo_{tag}_{r['id']}")
