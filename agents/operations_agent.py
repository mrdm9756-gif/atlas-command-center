from agents.base_agent import BaseAgent


class OperationsAgent(BaseAgent):
    key = "operations"
    name = "Operations Agent"
    role = "Operations, workflows and task tracking"
    icon = "⚙️"
    description = "Checklists, workflow analysis, inventory/process monitoring, task tracking."
    keywords = ["operation", "workflow", "process", "checklist", "inventory", "stock", "supply", "schedule",
                "logistics", "project", "milestone", "delay", "capacity", "procedure", "sop"]
    instructions = (
        "Create operational checklists, analyse workflows, monitor inventory and processes when "
        "connected data is available, and track tasks. If no inventory or process data is connected, "
        "say so plainly and provide a template instead of inventing numbers. You cannot modify "
        "production systems - propose changes for owner approval."
    )
    demo_outline = ["Map the current workflow step by step", "Identify bottlenecks and risks",
                    "Draft an operational checklist", "Propose improvements ranked by effort and impact"]
    demo_needs = ["Description of the current process", "Inventory or task data (CSV)", "Team size and shifts"]
