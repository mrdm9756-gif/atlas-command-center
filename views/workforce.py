"""Page 3: AI Workforce - agent cards, direct chat with every agent (and the CEO), assign task, reports."""
from __future__ import annotations

import datetime as dt

import streamlit as st

import agents as agent_registry
import database as dbm
import models
import ui_common as ui
import voice_service

VIEW_KEY = "wf_view"


def _view() -> dict:
    return st.session_state.setdefault(VIEW_KEY, {"mode": "grid", "agent": None})


def _set_view(mode: str, agent: str | None = None) -> None:
    st.session_state[VIEW_KEY] = {"mode": mode, "agent": agent}
    st.rerun()


def _meta(ctx, key: str) -> dict:
    if key == "ceo":
        return {"name": f"{ctx.ai_name} (AI CEO)", "role": "CEO Orchestrator - routes work, reviews results", "icon": "🧠"}
    ag = agent_registry.get_agent(key)
    return {"name": ag.name, "role": ag.role, "icon": ag.icon}


# --------------------------------------------------------------------------- #
def _grid(ctx) -> None:
    st.title("AI Workforce")
    st.caption("Chat with any agent directly, assign it a task, or read its reports.")
    ui.mode_banner(ctx)
    with st.container(border=True):
        ui.md_html(f"### 🧠 {ui.esc(ctx.ai_name)} - AI CEO")
        st.caption("Receives your instructions, picks the right agent, tracks status and reviews results.")
        if st.button(f"Chat with {ctx.ai_name} (CEO)", key="chat_ceo"):
            _set_view("chat", "ceo")

    states = dbm.list_agent_states(ctx.company_id)
    agents = agent_registry.all_agents()
    for start in range(0, len(agents), 3):
        cols = st.columns(3)
        for col, ag in zip(cols, agents[start:start + 3]):
            s = states.get(ag.key, {})
            with col:
                with st.container(border=True):
                    ui.md_html(f"### {ag.icon} {ui.esc(ag.name)}")
                    ui.md_html(f'<span class="muted">{ui.esc(ag.role)}</span>')
                    if not s.get("enabled", 1):
                        dot, label = "off", "Disabled"
                    elif s.get("status") == "working":
                        dot, label = "working", "Working"
                    else:
                        dot, label = "idle", "Idle"
                    ui.md_html(f'<span class="dot dot-{dot}"></span><b>{label}</b>')
                    st.caption(f"Current task: {s.get('current_task') or '-'}")
                    st.caption(f"Last report: {models.fmt_local(s.get('last_report_at'), ctx.company['timezone']) if s.get('last_report_at') else 'never'}")
                    if st.button("💬 Chat", key=f"chat_{ag.key}"):
                        _set_view("chat", ag.key)
                    if st.button("➕ Assign Task", key=f"assign_{ag.key}"):
                        _set_view("assign", ag.key)
                    if st.button("📄 View Reports", key=f"reports_{ag.key}"):
                        _set_view("reports", ag.key)


# --------------------------------------------------------------------------- #
def _chat(ctx, key: str) -> None:
    meta = _meta(ctx, key)
    orch = ctx.orch
    top = st.columns([1, 1, 3])
    with top[0]:
        if st.button("← Back to workforce", key="chat_back"):
            _set_view("grid")
    with top[1]:
        if key != "ceo" and st.button(f"Return to {ctx.ai_name} (CEO) chat", key="chat_to_ceo"):
            _set_view("chat", "ceo")
    st.title(f"{meta['icon']} {meta['name']}")
    st.caption(meta["role"])
    ui.mode_banner(ctx)

    delegate = True
    if key == "ceo":
        delegate = st.toggle("Delegate my message to the workforce (create and run a task)", value=True, key="ceo_delegate")
        st.caption("On: the CEO routes your message to the best agent, the agent works, and the CEO reviews the result. "
                   "Off: plain conversation with the CEO.")

    messages = dbm.get_messages(ctx.company_id, key)
    if not messages:
        ui.empty_state("No messages yet.", f"Say hello to {meta['name']}. History is saved per agent and per company workspace.")
    for m in messages:
        who = "user" if m["role"] == "owner" else "assistant"
        with st.chat_message(who):
            ui.md_html(ui.mode_badge(m["mode"]) + f'<span class="muted"> {ui.esc(models.fmt_local(m["created_at"], ctx.company["timezone"]))}</span>')
            st.markdown(m["content"])

    prefs = voice_service.get_prefs()
    speak_new = st.session_state.pop("speak_new", False)
    last = messages[-1] if messages else None
    if last and last["role"] == "agent" and prefs["speakEnabled"]:
        ui.render_component(voice_service.speak_html(last["content"], prefs, autoplay=bool(speak_new and prefs["autoSpeak"])), height=48)
    if not prefs["textOnly"]:
        ui.render_component(voice_service.dictation_html(prefs), height=52)

    prompt = st.chat_input(f"Message {meta['name']}...", key=f"chat_input_{key}")
    if prompt:
        with st.spinner(f"{meta['name']} is working..."):
            if key == "ceo":
                ok, out = ui.run_safely(orch.ceo_chat, prompt, delegate)
            else:
                ok, out = ui.run_safely(orch.chat_with_agent, key, prompt)
        if ok:
            st.session_state["speak_new"] = True
            st.rerun()

    st.divider()
    cols = st.columns(3)
    if key != "ceo":
        with cols[0]:
            if st.button("Create task from my last message", key="chat_mk_task"):
                ok, tid = ui.run_safely(orch.task_from_last_message, key)
                if ok:
                    st.success(f"Task #{tid} created (Queued). Run it from Task Center.")
        with cols[1]:
            if st.button("Create task and run it now", key="chat_mk_run"):
                ok, tid = ui.run_safely(orch.task_from_last_message, key)
                if ok:
                    ok2, out = ui.run_safely(orch.execute_task, tid)
                    if ok2:
                        st.success(f"Task #{tid}: {out['status']}.")
        with cols[2]:
            if st.button("View this agent's reports", key="chat_reports"):
                _set_view("reports", key)
    with st.expander("Delete conversation history"):
        st.warning("This permanently deletes every message in this conversation for this company workspace.")
        sure = st.checkbox("Yes, delete this conversation", key=f"del_ok_{key}")
        if st.button("Delete history", key=f"del_btn_{key}", disabled=not sure):
            dbm.clear_messages(ctx.company_id, key)
            dbm.log_audit(ctx.company_id, "owner", "history_deleted", f"conversation with {key}")
            st.rerun()


# --------------------------------------------------------------------------- #
def _assign(ctx, key: str) -> None:
    meta = _meta(ctx, key)
    if st.button("← Back to workforce", key="assign_back"):
        _set_view("grid")
    st.title(f"Assign a task to {meta['name']}")
    ui.mode_banner(ctx)
    with st.form(f"assign_form_{key}"):
        title = st.text_input("Short title (optional)")
        details = st.text_area("What should the agent do?", height=140)
        c1, c2, c3 = st.columns(3)
        priority = c1.selectbox("Priority", models.PRIORITIES, index=1)
        use_due = c2.checkbox("Set a due date")
        due = c3.date_input("Due date", value=dt.date.today() + dt.timedelta(days=3))
        run_now = st.checkbox("Run it now", value=True)
        submit = st.form_submit_button("Create task")
    if submit:
        ok, res = ui.run_safely(ctx.orch.create_task, details, key, title or None, priority,
                                due.isoformat() if use_due else None)
        if ok:
            tid = res[0]
            if run_now:
                with st.spinner("Working..."):
                    ok2, out = ui.run_safely(ctx.orch.execute_task, tid)
                if ok2:
                    if out["status"] == models.FAILED:
                        st.error(f"Task #{tid} failed: {out.get('error', '')}")
                    else:
                        st.success(f"Task #{tid}: {out['status']}. Read the result in Task Center.")
            else:
                st.success(f"Task #{tid} created and queued.")


def _reports(ctx, key: str) -> None:
    meta = _meta(ctx, key)
    cols = st.columns([1, 1, 3])
    with cols[0]:
        if st.button("← Back to workforce", key="rep_back"):
            _set_view("grid")
    with cols[1]:
        if key != "ceo" and st.button("💬 Chat", key="rep_chat"):
            _set_view("chat", key)
    st.title(f"Reports - {meta['name']}")
    ui.mode_banner(ctx)
    if key == "ceo":
        st.info("The CEO's consolidated reports are in Reports Center.")
        if st.button("Open Reports Center", key="rep_center"):
            ui.goto("Reports Center")
        return
    if st.button("Generate a new report now", key="rep_new"):
        with st.spinner("Preparing report..."):
            ok, out = ui.run_safely(ctx.orch.generate_agent_report, key, "adhoc")
        if ok:
            st.success("Report saved.") if out["ok"] else st.error(f"Report failed: {out.get('error', '')}")
    reports = dbm.list_agent_reports(ctx.company_id, agent_key=key, limit=50)
    if not reports:
        ui.empty_state("No reports yet for this agent.")
    for r in reports:
        with st.expander(f"{r['title']} - {models.fmt_local(r['created_at'], ctx.company['timezone'])} [{r['status']}]"):
            ui.md_html(ui.mode_badge(r["mode"]) + ui.data_badge(r["data_label"]))
            st.caption(f"Source data: {r['source_data'] or '-'}")
            if r["status"] == "failed":
                st.error(r["error"] or "Report failed.")
            else:
                st.markdown(r["content"])


def render(ctx) -> None:
    v = _view()
    mode, key = v["mode"], v["agent"]
    if mode != "grid" and key and key != "ceo" and agent_registry.get_agent(key) is None:
        _set_view("grid")
        return
    if mode == "chat" and key:
        _chat(ctx, key)
    elif mode == "assign" and key:
        _assign(ctx, key)
    elif mode == "reports" and key:
        _reports(ctx, key)
    else:
        _grid(ctx)
