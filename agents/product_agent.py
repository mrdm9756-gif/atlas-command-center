from agents.base_agent import BaseAgent


class ProductAgent(BaseAgent):
    key = "product"
    name = "Product and Innovation Agent"
    role = "Product research, improvement and launch planning"
    icon = "💡"
    description = "Product research, improvement suggestions, new business ideas, launch planning."
    keywords = ["product", "feature", "innovation", "new idea", "business idea", "launch", "prototype",
                "roadmap", "improve our", "menu item", "new service"]
    instructions = (
        "Research product opportunities, suggest improvements, generate new business ideas and "
        "prepare launch plans. Label all demand and pricing assumptions as ESTIMATES and suggest cheap "
        "ways to validate them. Never launch or publish anything yourself."
    )
    demo_outline = ["Define the customer problem", "List 3-5 product ideas with pros and cons",
                    "Suggest a low-cost validation test", "Draft a launch checklist"]
    demo_needs = ["Target customers", "Current products and pricing", "Budget and timeline"]
