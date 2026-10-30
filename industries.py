"""Industry profiles: terminology, KPIs, workflows, recommended agents, report templates.

Adding an industry = adding one entry to INDUSTRIES. KPI *values* are never stored here;
they come from user-provided datasets, or from demo_data (always labelled DEMO DATA).
"""
from __future__ import annotations

CUSTOM = "Custom Industry"

_STD_AGENTS = ["marketing", "sales", "finance", "operations", "research",
               "customer_service", "hr", "product", "data_analyst"]


def _ind(customer, sale, kpis, workflows, agents, template, unit="orders"):
    return {
        "terms": {"customer": customer, "sale": sale, "unit": unit},
        "kpis": kpis,
        "workflows": workflows,        # (title, agent_key, prompt)
        "recommended_agents": agents,
        "report_template": template,
    }


INDUSTRIES: dict[str, dict] = {
    "General Business": _ind(
        "customer", "sale", ["Revenue", "Expenses", "Net Profit", "New Customers", "Open Tasks", "Overdue Tasks"],
        [("Weekly business review", "operations", "Review the past week for this business and list wins, risks and next actions."),
         ("Cash-flow outlook", "finance", "Prepare a 30-day cash-flow outlook with clearly labelled assumptions."),
         ("Growth ideas", "marketing", "Suggest five low-cost customer acquisition ideas for this business.")],
        _STD_AGENTS,
        "Executive summary; Sales & revenue; Costs; Customers; Operations; Risks; Decisions needed"),
    "Restaurant and Food Service": _ind(
        "diner", "order", ["Daily Sales", "Order Count", "Average Order Value", "Food Cost %", "Low-Stock Items", "Customer Rating"],
        [("7-day promo campaign", "marketing", "Prepare a 7-day promotional campaign for the restaurant with daily post ideas and offers."),
         ("Food cost analysis", "finance", "Analyse food cost percentage by menu category and suggest ways to reduce it."),
         ("Inventory check", "operations", "Create a daily inventory and par-level checklist for the kitchen."),
         ("Staff schedule support", "hr", "Draft a weekly staff schedule template balancing peak hours."),
         ("Customer feedback review", "customer_service", "Categorise recent customer feedback and highlight complaints needing escalation.")],
        ["marketing", "finance", "operations", "hr", "customer_service", "data_analyst", "research"],
        "Sales & orders; Inventory; Food cost; Customer feedback; Staffing; Risks", "orders"),
    "Real Estate": _ind(
        "client", "deal", ["Active Leads", "Hot Leads", "Listings", "Viewings Scheduled", "Follow-ups Due", "Marketing Cost per Lead"],
        [("Lead scoring", "sales", "Create a lead-scoring rubric for real-estate buyers and sellers."),
         ("Follow-up reminders", "sales", "Draft a follow-up cadence for leads at each stage of the pipeline."),
         ("Listing marketing plan", "marketing", "Prepare a marketing plan for a new property listing."),
         ("Property inventory review", "operations", "Outline a property-inventory tracking checklist.")],
        ["sales", "marketing", "research", "finance", "customer_service", "operations", "data_analyst"],
        "Lead pipeline; Property inventory; Viewings; Marketing performance; Follow-ups; Risks", "listings"),
    "E-commerce and Online Retail": _ind(
        "shopper", "order", ["Revenue", "Orders", "Return Rate", "Conversion Rate", "Low-Stock SKUs", "Ad Spend / ROAS"],
        [("Product performance review", "data_analyst", "Analyse product performance and highlight best and worst sellers."),
         ("Returns analysis", "operations", "Analyse return reasons and recommend fixes."),
         ("Campaign report", "marketing", "Summarise campaign performance and recommend budget changes."),
         ("Customer inquiry triage", "customer_service", "Categorise customer inquiries and draft replies.")],
        ["marketing", "sales", "operations", "customer_service", "data_analyst", "finance", "product"],
        "Revenue & orders; Products; Returns; Inventory; Campaigns; Customer inquiries; Risks", "orders"),
    "Construction": _ind(
        "client", "contract", ["Active Projects", "% Complete", "Budget Variance", "Delayed Tasks", "Material Orders Due", "Safety Incidents"],
        [("Project progress report", "operations", "Prepare a project progress report with milestones, delays and next steps."),
         ("Budget monitoring", "finance", "Compare planned versus actual cost and flag variances."),
         ("Material planning", "operations", "Prepare a material requirement plan for the next two weeks."),
         ("Risk and delay report", "research", "List the main schedule and cost risks and mitigation options.")],
        ["operations", "finance", "hr", "research", "data_analyst", "sales"],
        "Project progress; Tasks; Budget; Materials; Risks and delays; Decisions needed", "projects"),
    "Manufacturing": _ind(
        "buyer", "order", ["Units Produced", "Defect Rate", "On-time Delivery", "Machine Downtime", "Inventory Days", "Cost per Unit"],
        [("Production review", "operations", "Review production output, bottlenecks and downtime causes."),
         ("Quality report", "data_analyst", "Summarise defect data and likely root causes."),
         ("Supplier risk scan", "research", "List supplier and supply-chain risks and mitigations.")],
        ["operations", "finance", "research", "hr", "data_analyst", "product"],
        "Production; Quality; Supply chain; Cost; Safety; Risks", "units"),
    "Logistics and Transportation": _ind(
        "shipper", "shipment", ["Shipments", "On-time %", "Cost per Km", "Fleet Utilisation", "Delays", "Claims"],
        [("Route efficiency review", "operations", "Review route efficiency and suggest improvements."),
         ("Delay analysis", "data_analyst", "Analyse delivery delays and their causes."),
         ("Fleet cost report", "finance", "Summarise fleet operating costs and savings ideas.")],
        ["operations", "finance", "data_analyst", "customer_service", "research", "hr"],
        "Shipments; On-time performance; Costs; Fleet; Claims; Risks", "shipments"),
    "Healthcare Administration": _ind(
        "patient", "appointment", ["Appointments", "No-show Rate", "Wait Time", "Claims Pending", "Staff Coverage", "Patient Satisfaction"],
        [("Scheduling review", "operations", "Review appointment scheduling and no-show reduction ideas (administrative only, no medical advice)."),
         ("Staff coverage plan", "hr", "Draft a staff coverage plan for the coming week."),
         ("Patient feedback summary", "customer_service", "Categorise patient feedback by theme (administrative topics only).")],
        ["operations", "hr", "finance", "customer_service", "data_analyst", "research"],
        "Appointments; Staffing; Billing/claims; Feedback; Compliance reminders; Risks. Administrative use only - no clinical advice.",
        "appointments"),
    "Education": _ind(
        "student", "enrolment", ["Enrolments", "Attendance %", "Retention", "Fees Collected", "Staff Count", "Inquiries"],
        [("Enrolment campaign", "marketing", "Prepare an enrolment campaign plan."),
         ("Training plan", "hr", "Draft a staff training plan for the term."),
         ("Inquiry handling", "customer_service", "Organise student and parent inquiries and draft replies.")],
        ["marketing", "hr", "operations", "finance", "customer_service", "research", "product"],
        "Enrolment; Attendance; Finance; Staff; Inquiries; Risks", "students"),
    "Finance and Accounting": _ind(
        "client", "engagement", ["Billable Hours", "Invoices Outstanding", "Collections", "Close Progress", "Audit Items", "Client Count"],
        [("Month-end checklist", "finance", "Prepare a month-end close checklist."),
         ("Receivables review", "finance", "Analyse outstanding receivables and prioritise collections."),
         ("Client onboarding", "operations", "Outline a client onboarding workflow.")],
        ["finance", "operations", "sales", "data_analyst", "research", "hr"],
        "Billing; Receivables; Close status; Compliance; Clients; Risks", "engagements"),
    "Hospitality and Tourism": _ind(
        "guest", "booking", ["Occupancy %", "ADR", "RevPAR", "Bookings", "Guest Rating", "Cancellations"],
        [("Seasonal promo plan", "marketing", "Prepare a seasonal promotion plan."),
         ("Guest feedback review", "customer_service", "Categorise guest reviews and flag complaints."),
         ("Housekeeping workflow", "operations", "Draft a housekeeping and turnover checklist.")],
        ["marketing", "operations", "customer_service", "hr", "finance", "research"],
        "Occupancy; Revenue; Guest feedback; Staffing; Promotions; Risks", "bookings"),
    "Agriculture": _ind(
        "buyer", "harvest sale", ["Yield", "Input Cost", "Price per Unit", "Weather Risk", "Equipment Uptime", "Storage Level"],
        [("Seasonal plan", "operations", "Draft a seasonal planting/harvest plan with assumptions."),
         ("Market price scan", "research", "Summarise market and price considerations for main crops (label estimates)."),
         ("Cost review", "finance", "Review input costs and savings options.")],
        ["operations", "research", "finance", "sales", "data_analyst", "hr"],
        "Production; Inputs and costs; Market; Weather and risk; Equipment; Decisions needed", "harvests"),
    "Retail Stores": _ind(
        "customer", "sale", ["Daily Sales", "Transactions", "Basket Size", "Stock-outs", "Shrinkage", "Foot Traffic"],
        [("Stock replenishment", "operations", "Create a replenishment checklist."),
         ("Promo plan", "marketing", "Prepare a weekly in-store promotion plan."),
         ("Sales review", "data_analyst", "Analyse sales by category and identify trends.")],
        ["marketing", "sales", "operations", "finance", "customer_service", "data_analyst", "hr"],
        "Sales; Inventory; Promotions; Staff; Customer feedback; Risks", "transactions"),
    "Professional Services": _ind(
        "client", "engagement", ["Active Clients", "Utilisation %", "Pipeline Value", "Invoices Outstanding", "Proposals Sent", "Satisfaction"],
        [("Proposal drafting", "sales", "Draft a proposal outline for a prospective client."),
         ("Utilisation review", "operations", "Review team utilisation and capacity."),
         ("Thought-leadership plan", "marketing", "Prepare a content plan to attract clients.")],
        ["sales", "marketing", "operations", "finance", "hr", "research"],
        "Pipeline; Delivery; Utilisation; Billing; Clients; Risks", "engagements"),
    "Information Technology": _ind(
        "customer", "subscription", ["MRR", "Churn", "Open Tickets", "Uptime", "Release Cadence", "Cloud Cost"],
        [("Release plan", "product", "Draft a release plan with milestones."),
         ("Ticket triage", "customer_service", "Categorise support tickets and recommend priorities."),
         ("Cloud cost review", "finance", "Review cloud costs and suggest savings.")],
        ["product", "operations", "customer_service", "finance", "marketing", "data_analyst", "hr", "research"],
        "Product; Support; Reliability; Cost; Pipeline; Risks", "subscriptions"),
    "Marketing Agencies": _ind(
        "client", "retainer", ["Active Clients", "Campaigns Live", "Retainer Revenue", "Utilisation %", "Client ROAS", "Churn"],
        [("Client report pack", "marketing", "Prepare a client campaign performance report outline."),
         ("New business pipeline", "sales", "Draft an outbound plan for new agency clients."),
         ("Capacity planning", "operations", "Plan team capacity for the next month.")],
        ["marketing", "sales", "operations", "finance", "hr", "data_analyst", "research"],
        "Clients; Campaigns; Revenue; Capacity; Pipeline; Risks", "campaigns"),
    "Automotive": _ind(
        "customer", "sale", ["Vehicles Sold", "Service Appointments", "Parts Stock", "Lead Conversion", "Warranty Claims", "CSI Score"],
        [("Service reminders", "customer_service", "Draft service-reminder message templates (do not send)."),
         ("Parts inventory", "operations", "Prepare a parts inventory checklist."),
         ("Lead follow-up", "sales", "Draft a lead follow-up plan.")],
        ["sales", "operations", "customer_service", "marketing", "finance", "data_analyst"],
        "Sales; Service; Parts; Leads; Customer satisfaction; Risks", "vehicles"),
    "Beauty and Wellness": _ind(
        "client", "booking", ["Bookings", "No-show Rate", "Rebooking Rate", "Retail Sales", "Staff Utilisation", "Reviews"],
        [("Rebooking campaign", "marketing", "Prepare a rebooking and loyalty campaign."),
         ("Staff schedule", "hr", "Draft a staff schedule template."),
         ("Review responses", "customer_service", "Draft polite replies to client reviews.")],
        ["marketing", "customer_service", "hr", "operations", "finance", "product"],
        "Bookings; Retention; Retail; Staff; Reviews; Risks", "bookings"),
    "Entertainment and Media": _ind(
        "audience member", "ticket", ["Audience", "Engagement Rate", "Revenue", "Content Published", "Subscribers", "Sponsorships"],
        [("Content calendar", "marketing", "Prepare a 4-week content calendar."),
         ("Audience analysis", "data_analyst", "Analyse audience and engagement patterns."),
         ("Sponsorship pipeline", "sales", "Draft a sponsorship outreach plan.")],
        ["marketing", "product", "sales", "data_analyst", "finance", "research"],
        "Audience; Content; Revenue; Sponsorships; Production; Risks", "tickets"),
    "Nonprofit Organizations": _ind(
        "supporter", "donation", ["Donations", "Donors", "Retention", "Program Reach", "Volunteer Hours", "Cost per Dollar Raised"],
        [("Fundraising campaign", "marketing", "Prepare a fundraising campaign plan."),
         ("Volunteer plan", "hr", "Draft a volunteer recruitment and training plan."),
         ("Impact report", "research", "Outline an impact report with measurable outcomes.")],
        ["marketing", "hr", "finance", "operations", "research", "data_analyst"],
        "Fundraising; Programs; Volunteers; Finance; Impact; Risks", "donations"),
    CUSTOM: _ind(
        "customer", "sale", ["Revenue", "Expenses", "Customers", "Open Tasks", "Overdue Tasks", "Key Metric 1"],
        [("Business review", "operations", "Review the business in its custom industry context and list risks and actions."),
         ("Market scan", "research", "Research the custom industry's main trends and competitors (label estimates).")],
        _STD_AGENTS,
        "Executive summary; Sales; Costs; Customers; Operations; Risks"),
}

INDUSTRY_NAMES = list(INDUSTRIES.keys())


def profile(industry: str) -> dict:
    return INDUSTRIES.get(industry) or INDUSTRIES["General Business"]


def display_name(company: dict) -> str:
    """The industry name shown to the owner (custom name when 'Custom Industry')."""
    if company.get("industry") == CUSTOM and company.get("custom_industry"):
        return company["custom_industry"]
    return company.get("industry") or "General Business"
