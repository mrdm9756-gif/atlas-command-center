"""Deterministic SAMPLE data. Everything produced here MUST be shown with a DEMO DATA label.

Nothing here is real business data; it exists only so beginners can see the dashboards work.
"""
from __future__ import annotations

import hashlib
import random
from datetime import date, timedelta

import pandas as pd

import industries

DEMO_LABEL = "DEMO DATA"


def _rng(seed_text: str) -> random.Random:
    return random.Random(int(hashlib.sha256(seed_text.encode()).hexdigest(), 16) % (2 ** 32))


def demo_kpis(industry: str) -> dict[str, str]:
    """Return {kpi_name: formatted sample value} - SIMULATED."""
    rng = _rng("kpi:" + industry)
    out: dict[str, str] = {}
    for name in industries.profile(industry)["kpis"]:
        low = name.lower()
        if "%" in name or "rate" in low or "churn" in low or "retention" in low:
            out[name] = f"{rng.uniform(2, 96):.1f}%"
        elif any(w in low for w in ("revenue", "sales", "cost", "spend", "profit", "expenses", "fees",
                                    "value", "mrr", "donations", "collections")):
            out[name] = f"{rng.randint(12, 480) * 1000:,}"
        else:
            out[name] = f"{rng.randint(3, 240)}"
    return out


def demo_timeseries(industry: str, days: int = 30) -> pd.DataFrame:
    """Daily revenue / cost / orders for the last `days` days - SIMULATED."""
    rng = _rng("ts:" + industry)
    start = date.today() - timedelta(days=days - 1)
    base = rng.randint(8, 60) * 1000
    rows = []
    for i in range(days):
        d = start + timedelta(days=i)
        weekend_boost = 1.2 if d.weekday() >= 5 else 1.0
        revenue = round(base * weekend_boost * rng.uniform(0.75, 1.25), 2)
        cost = round(revenue * rng.uniform(0.45, 0.7), 2)
        orders = max(1, int(revenue / rng.uniform(300, 900)))
        rows.append({"date": d.isoformat(), "revenue": revenue, "cost": cost, "orders": orders})
    return pd.DataFrame(rows)


def demo_csv_text(industry: str) -> str:
    return demo_timeseries(industry).to_csv(index=False)
