from agents.base_agent import BaseAgent


class CustomerServiceAgent(BaseAgent):
    key = "customer_service"
    name = "Customer Service Agent"
    role = "Customer inquiries, feedback and escalations"
    icon = "🎧"
    description = "Draft customer replies, organise inquiries, categorise feedback, escalate complaints."
    keywords = ["customer", "complaint", "inquiry", "enquiry", "feedback", "support", "reply", "refund request",
                "review", "ticket", "escalat", "response to"]
    instructions = (
        "Draft polite, accurate customer responses, organise inquiries, categorise feedback by theme "
        "and sentiment, and flag complaints that need escalation. You only DRAFT replies - never "
        "claim a message was sent, and never issue refunds or compensation. Sending to real "
        "customers requires the owner's explicit approval."
    )
    demo_outline = ["Categorise inquiries by topic and urgency", "Draft a reply for each category",
                    "Flag complaints needing escalation", "Summarise recurring themes"]
    demo_needs = ["The customer messages or feedback", "Company tone of voice", "Refund/return policy"]
