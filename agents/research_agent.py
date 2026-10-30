from agents.base_agent import BaseAgent


class ResearchAgent(BaseAgent):
    key = "research"
    name = "Research Agent"
    role = "Industry, competitor and market research"
    icon = "🔎"
    description = "Industry research, competitor analysis, market opportunities, research summaries."
    keywords = ["research", "competitor", "market", "trend", "industry", "benchmark", "opportunity",
                "analysis of the market", "swot", "survey", "study"]
    instructions = (
        "Prepare industry research, competitor analyses, market-opportunity assessments and research "
        "summaries. You do NOT have live internet access in this application: work from general "
        "knowledge and any data provided, state that your knowledge may be out of date, label "
        "all market figures as ESTIMATES, and recommend how the owner can verify them. Never "
        "fabricate sources, URLs or statistics."
    )
    demo_outline = ["Define the research question and scope", "List the main competitors and segments",
                    "Summarise trends and opportunities (labelled as estimates)", "Recommend how to verify each finding"]
    demo_needs = ["Specific market or competitors", "Geography", "Decision this research should inform"]
