"""Agent registry.

Built-in agents are registered below. To add a NEW agent without writing Python, add an entry
to agents/custom_agents.json:

    [{"key": "legal", "name": "Legal Assistant Agent", "role": "Contract drafting support",
      "instructions": "Draft contract outlines. Not a lawyer...", "icon": "⚖️",
      "keywords": ["contract", "legal", "nda"]}]

For custom behaviour, subclass BaseAgent in a new file and add it to _BUILTIN below.
"""
from __future__ import annotations

import json
from pathlib import Path

from agents.base_agent import BaseAgent, GenericAgent
from agents.customer_service_agent import CustomerServiceAgent
from agents.data_analyst_agent import DataAnalystAgent
from agents.finance_agent import FinanceAgent
from agents.hr_agent import HRAgent
from agents.marketing_agent import MarketingAgent
from agents.operations_agent import OperationsAgent
from agents.product_agent import ProductAgent
from agents.research_agent import ResearchAgent
from agents.sales_agent import SalesAgent

_BUILTIN = [MarketingAgent, SalesAgent, FinanceAgent, OperationsAgent, ResearchAgent,
            CustomerServiceAgent, HRAgent, ProductAgent, DataAnalystAgent]

CUSTOM_FILE = Path(__file__).with_name("custom_agents.json")


def _load() -> dict[str, BaseAgent]:
    registry: dict[str, BaseAgent] = {cls.key: cls() for cls in _BUILTIN}
    try:
        entries = json.loads(CUSTOM_FILE.read_text(encoding="utf-8")) if CUSTOM_FILE.exists() else []
    except Exception:
        entries = []
    for e in entries if isinstance(entries, list) else []:
        try:
            key = str(e["key"]).strip().lower()
            if not key.replace("_", "").isalnum() or key in registry or key == "ceo":
                continue
            registry[key] = GenericAgent(
                key=key, name=str(e["name"])[:60], role=str(e["role"])[:100],
                instructions=str(e["instructions"])[:3000], icon=str(e.get("icon", "🧩"))[:4],
                description=str(e.get("description", ""))[:200], keywords=list(e.get("keywords", [])),
            )
        except Exception:
            continue          # a bad custom entry must never stop the app
    return registry


AGENTS: dict[str, BaseAgent] = _load()


def get_agent(key: str) -> BaseAgent | None:
    return AGENTS.get(key)


def all_agents() -> list[BaseAgent]:
    return list(AGENTS.values())


def agent_keys() -> list[str]:
    return list(AGENTS.keys())
