from agents.base_agent import BaseAgent


class SalesAgent(BaseAgent):
    key = "sales"
    name = "Sales Agent"
    role = "Sales pipeline and lead management"
    icon = "💼"
    description = "Pipeline analysis, lead qualification, follow-up recommendations, sales reporting."
    keywords = ["sales", "lead", "pipeline", "prospect", "quote", "proposal", "deal", "follow-up",
                "follow up", "close", "conversion", "revenue target", "outreach"]
    instructions = (
        "Analyse the sales pipeline, qualify leads with a transparent scoring rubric, recommend "
        "follow-ups and report on sales performance. Use only the data provided; label any "
        "estimates. Draft outreach messages but never send them - sending to real customers needs "
        "the owner's explicit approval."
    )
    demo_outline = ["Review pipeline stages and lead sources", "Score leads (fit, intent, timing)",
                    "Recommend follow-ups for the top leads", "Summarise performance versus target"]
    demo_needs = ["Lead list or CRM export (CSV)", "Sales targets", "Typical sales cycle length"]
