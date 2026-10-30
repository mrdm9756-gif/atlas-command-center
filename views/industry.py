"""Page 7: Industry Workspace - KPIs, terminology, workflows, recommended agents, report template."""
from __future__ import annotations

import streamlit as st

import agents as agent_registry
import industries
import kpis
import models
import ui_common as ui


def render_kpis(ctx, key_prefix: str = "ind") -> None:
    show_demo = st.checkbox("Show DEMO DATA sample values (not real)", key=f"{key_prefix}_demo", value=False)
    items = kpis.compute_kpis(ctx.company, show_demo)
    cols = st.columns(3)
    for i, item in enumerate(items):
        with cols[i % 3]:
            st.metric(item["name"], item["value"])
            kind = {"database": "live", "data": "live", "demo": "demo", "none": "system"}[item["source"]]
            label = {"database": "REAL (task list)", "data": "REAL (your CSV)", "demo": "DEMO DATA", "none": "NO DATA"}[item["source"]]
            ui.md_html(ui.badge(label, kind) + f'<span class="muted"> {ui.esc(item["note"])}</span>')
    if not any(i["source"] in ("data",) for i in items):
        st.caption("KPI values appear here once you upload a CSV with columns such as revenue, cost or orders "
                   "(Analytics page). Until then they are blank - nothing is invented.")


def render(ctx) -> None:
    company = ctx.company
    name = industries.display_name(company)
    prof = industries.profile(company["industry"])
    st.title(f"Industry Workspace: {name}")
    st.caption(f"Workspace: {company['name']}. Change the industry in Owner Settings.")
    ui.mode_banner(ctx)

    st.subheader("Key performance indicators")
    render_kpis(ctx, "industry_page")

    left, right = st.columns(2)
    with left:
        st.subheader("Terminology")
        t = prof["terms"]
        st.write(f"In this workspace we say **{t['customer']}** for customers, **{t['sale']}** for a sale, "
                 f"and count volume in **{t['unit']}**.")
        st.subheader("Recommended agents")
        states = ctx.orch.enabled_agent_keys()
        for key in prof["recommended_agents"]:
            ag = agent_registry.get_agent(key)
            if ag:
                on = key in states
                ui.md_html(f"{ag.icon} **{ui.esc(ag.name)}** " + ui.badge("enabled" if on else "disabled", "ok" if on else "system"))
    with right:
        st.subheader("Report template")
        st.write(prof["report_template"])
        st.caption("Scheduled and on-demand reports follow the structure of this template where the agents have data for it.")

    st.subheader("Ready-made workflows")
    st.caption("Each workflow creates a real task for the right agent and runs it. Results are labelled AI-generated or DEMO.")
    for idx, (title, agent_key, prompt) in enumerate(prof["workflows"]):
        ag = agent_registry.get_agent(agent_key)
        if ag is None:
            continue
        with st.container(border=True):
            c1, c2 = st.columns([4, 1])
            with c1:
                ui.md_html(f"**{ui.esc(title)}** " + ui.badge(ag.name, "info"))
                st.caption(prompt)
            with c2:
                if st.button("Run workflow", key=f"wf_{idx}"):
                    text = f"{prompt}\n\nBusiness: {company['name']} ({name})."
                    ok, out = ui.run_safely(ctx.orch.submit_request, text, agent_key, title=title)
                    if ok:
                        if out["status"] == models.FAILED:
                            st.error(f"Task #{out['task_id']} failed: {out.get('error', '')}")
                        else:
                            st.success(f"Task #{out['task_id']} -> {ag.name}: {out['status']}. See Task Center.")
