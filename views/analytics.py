"""Page 6: Analytics - upload CSV data, real analysis and charts, workforce statistics."""
from __future__ import annotations

import pandas as pd
import streamlit as st

import data_tools
import database as dbm
import demo_data
import industries
import models
import ui_common as ui


def render(ctx) -> None:
    cid = ctx.company_id
    st.title("Analytics")
    st.caption("Upload your own CSV exports for REAL analysis. Numbers here are computed by Python, not guessed by an AI.")
    ui.mode_banner(ctx)

    st.subheader("Your data")
    with st.form("csv_form", clear_on_submit=True):
        up = st.file_uploader("Upload a CSV file (max 5 MB)", type=["csv"])
        name = st.text_input("Dataset name (optional)")
        saved = st.form_submit_button("Save dataset")
    if saved:
        if up is None:
            st.error("Choose a CSV file first.")
        else:
            try:
                df, text = data_tools.parse_csv_bytes(up.getvalue())
                if str(name or up.name).startswith(data_tools.DEMO_PREFIX):
                    raise models.ValidationError(f"Names starting with '{data_tools.DEMO_PREFIX}' are reserved for sample data.")
                dbm.add_dataset(cid, name or up.name, up.name, text, len(df))
                dbm.log_audit(cid, "owner", "dataset_uploaded", f"{up.name} ({len(df)} rows)")
                st.success(f"Saved '{name or up.name}' with {len(df):,} rows.")
            except models.ValidationError as exc:
                st.error(str(exc))

    if st.button("Load DEMO DATA sample (simulated, for trying the app)", key="load_demo"):
        label = f"{data_tools.DEMO_PREFIX} - {industries.display_name(ctx.company)} sample"
        csv_text = demo_data.demo_csv_text(ctx.company["industry"])
        dbm.add_dataset(cid, label, "demo.csv", csv_text, csv_text.count("\n") - 1)
        st.success("Sample loaded. It is labelled DEMO DATA everywhere it is used.")
        st.rerun()

    datasets = dbm.list_datasets(cid)
    if not datasets:
        ui.empty_state("No datasets yet.", "Upload a CSV above, or load the DEMO DATA sample to see how charts and analysis look.")
    else:
        ds_id = st.selectbox("Dataset", [d["id"] for d in datasets],
                             format_func=lambda i: next(f"{d['name']} ({d['row_count']:,} rows)" for d in datasets if d["id"] == i))
        ds = dbm.get_dataset(ds_id, cid)
        demo = data_tools.is_demo_dataset(ds)
        ui.md_html(ui.badge("DEMO DATA - simulated", "demo") if demo else ui.badge("REAL - your uploaded data", "live")
                   + ui.badge("COMPUTED BY PYTHON", "computed"))
        try:
            df = data_tools.df_from_dataset(ds)
        except Exception:
            st.error("This dataset could not be read.")
            return
        st.dataframe(df.head(200), hide_index=True)
        with st.expander("Summary statistics", expanded=True):
            st.text(data_tools.summarize_df(df, ds["name"]))
            anomalies = data_tools.detect_anomalies(df)
            if anomalies:
                st.warning("Possible anomalies (|z-score| > 3):")
                st.dataframe(pd.DataFrame(anomalies), hide_index=True)
            else:
                st.caption("No numeric outliers detected (needs at least 8 rows).")

        numeric = list(df.select_dtypes("number").columns)
        if numeric:
            st.subheader("Chart")
            c1, c2, c3 = st.columns([2, 3, 1])
            x = c1.selectbox("X axis", list(df.columns), index=0)
            ys = c2.multiselect("Y values", numeric, default=numeric[:2])
            kind = c3.radio("Type", ["Line", "Bar"])
            if ys:
                plot = df[[x] + [y for y in ys if y != x]].copy()
                try:
                    plot[x] = pd.to_datetime(plot[x])
                except Exception:
                    pass
                plot = plot.set_index(x)
                (st.line_chart if kind == "Line" else st.bar_chart)(plot)
        else:
            st.info("This dataset has no numeric columns to chart.")

        b1, b2 = st.columns(2)
        with b1:
            if st.button("Ask the Data Analyst Agent to analyse it", key="ask_analyst"):
                with st.spinner("Analysing..."):
                    ok, out = ui.run_safely(ctx.orch.submit_request,
                                            f"Data Analyst Agent, analyse the dataset '{ds['name']}' and highlight patterns and anomalies.",
                                            "data_analyst")
                if ok:
                    st.success(f"Task #{out['task_id']}: {out['status']}. Read it in Task Center.")
        with b2:
            sure = st.checkbox("Yes, delete this dataset", key=f"del_ds_ok_{ds_id}")
            if st.button("Delete dataset", key=f"del_ds_{ds_id}", disabled=not sure):
                dbm.delete_dataset(ds_id, cid)
                dbm.log_audit(cid, "owner", "dataset_deleted", ds["name"])
                st.rerun()

    st.subheader("Workforce analytics (real, from your task list)")
    tasks = dbm.list_tasks(cid, limit=2000)
    if not tasks:
        ui.empty_state("No tasks yet.", "Task statistics appear after you create tasks.")
        return
    by_status = pd.Series([t["status"] for t in tasks]).value_counts().reindex(models.TASK_STATUSES, fill_value=0)
    by_agent = pd.Series([t["agent_key"] for t in tasks]).value_counts()
    c1, c2 = st.columns(2)
    c1.caption("Tasks by status")
    c1.bar_chart(by_status)
    c2.caption("Tasks by agent")
    c2.bar_chart(by_agent)
