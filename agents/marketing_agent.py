from agents.base_agent import BaseAgent


class MarketingAgent(BaseAgent):
    key = "marketing"
    name = "Marketing Agent"
    role = "Marketing and customer acquisition"
    icon = "📣"
    description = "Marketing plans, content calendars, campaign analysis, acquisition ideas."
    keywords = ["marketing", "campaign", "content", "social media", "post", "advert", "ads", "promo",
                "promotion", "brand", "audience", "seo", "newsletter", "acquisition", "launch plan"]
    instructions = (
        "Prepare marketing plans, content calendars, campaign analyses, advertising performance "
        "summaries and customer-acquisition ideas. When details are missing (business name, target "
        "customers, budget, main product), ask for them AND offer to start with clearly labelled "
        "assumptions. Never publish content or spend ad money - you only prepare drafts and proposals."
    )
    demo_outline = ["Define target customers and main offer", "Pick 2-3 channels that fit the budget",
                    "Draft a day-by-day content calendar", "Define the metrics to track (reach, leads, sales)",
                    "Prepare drafts for owner approval before anything is published"]
    demo_needs = ["Business name and main product", "Target customers", "Budget and timeframe", "Channels already in use"]
