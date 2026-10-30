from agents.base_agent import BaseAgent


class FinanceAgent(BaseAgent):
    key = "finance"
    name = "Finance Agent"
    role = "Finance, budgets and cash flow"
    icon = "💰"
    description = "Revenue/expense analysis, budgets, cash-flow projections, financial risk alerts."
    keywords = ["finance", "financial", "budget", "cash flow", "cash-flow", "expense", "profit", "margin",
                "invoice", "revenue", "cost", "forecast", "payroll", "tax", "p&l"]
    instructions = (
        "Analyse revenue and expenses using ONLY the provided data, prepare budget summaries, "
        "cash-flow projections and financial risk alerts. Every projection must list its "
        "assumptions and be labelled ESTIMATE. You are not a licensed accountant or financial "
        "adviser - recommend professional review for tax or legal decisions. You can NEVER move "
        "money, pay invoices, buy or trade."
    )
    demo_outline = ["Collect revenue and expense data for the period", "Calculate margins and trends",
                    "Project cash flow for 30 days with stated assumptions", "List financial risks and alerts"]
    demo_needs = ["Revenue and expense data (CSV)", "Current cash balance", "Upcoming large payments"]
