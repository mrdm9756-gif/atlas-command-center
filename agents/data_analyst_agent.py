"""Data Analyst Agent.

Unlike the other agents, this one runs REAL computation (pandas) on the owner's uploaded CSV
files first. The numbers in the "Computed from your data" section are real even in demo mode;
only the written interpretation depends on the AI provider.
"""
from __future__ import annotations

import ai_provider
import data_tools
import models
from agents.base_agent import BaseAgent


class DataAnalystAgent(BaseAgent):
    key = "data_analyst"
    name = "Data Analyst Agent"
    role = "Data analysis, charts and anomaly detection"
    icon = "📊"
    description = "Analyses uploaded CSV files: summaries, tables, charts, patterns and anomalies."
    keywords = ["data", "csv", "analy", "chart", "trend", "anomal", "statistics", "dataset", "report on the numbers",
                "spreadsheet", "correlation", "pattern"]
    instructions = (
        "Interpret the statistical summary computed from the owner's uploaded data. Explain patterns "
        "and anomalies in plain language, point out data-quality problems, and suggest follow-up "
        "analyses. Only discuss numbers that appear in the computed summary - never invent data."
    )
    demo_outline = ["Profile the dataset (rows, columns, missing values)", "Summarise key numeric columns",
                    "Flag unusual values", "Suggest charts and follow-up questions"]
    demo_needs = ["A CSV file uploaded in the Analytics page"]

    def run(self, provider: ai_provider.AIProvider, prompt: str, ctx: dict,
            history: list[dict] | None = None) -> ai_provider.AIResult:
        company_id = ctx.get("company_id")
        computed = data_tools.analysis_report(company_id) if company_id else ""
        if not computed:
            base = super().run(provider, prompt, ctx, history)
            if base.ok:
                base.text = ("[No dataset uploaded yet - nothing was computed. Upload a CSV in Analytics "
                             "for a real analysis.]\n\n" + base.text)
            return base
        enriched = (f"{prompt}\n\nCOMPUTED SUMMARY (real, from the owner's uploaded data):\n{computed}\n\n"
                    "Interpret this summary for the owner.")
        ai = super().run(provider, enriched, ctx, history)
        if not ai.ok:
            return ai
        header = "## Computed from your data (real figures, calculated by Python)\n"
        label = ("## Interpretation (AI-generated)\n" if ai.mode == models.MODE_LIVE
                 else "## Interpretation (DEMO - simulated, no AI model used)\n")
        return ai_provider.AIResult(f"{header}{computed}\n\n{label}{ai.text}", ai.mode)
