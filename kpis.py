"""Industry KPI values with honest provenance.

source = "database"  -> computed from this workspace's tasks
         "data"      -> computed from the newest REAL (non-demo) uploaded CSV
         "demo"      -> sample value, must be shown as DEMO DATA
         "none"      -> nothing connected, shown as a dash
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

import data_tools
import database as dbm
import demo_data
import industries
import models

_COLUMN_ALIASES = {"revenue": ("revenue", "sales", "amount"), "cost": ("cost", "expenses", "expense"),
                   "orders": ("orders", "order_count", "transactions")}


def _find_col(df: pd.DataFrame, key: str) -> str | None:
    lowered = {str(c).lower().strip(): c for c in df.columns}
    for alias in _COLUMN_ALIASES[key]:
        if alias in lowered and pd.api.types.is_numeric_dtype(df[lowered[alias]]):
            return lowered[alias]
    return None


def _latest_real_df(company_id: int):
    for ds in dbm.list_datasets(company_id):
        full = dbm.get_dataset(ds["id"], company_id)
        if full and not data_tools.is_demo_dataset(full):
            try:
                return data_tools.df_from_dataset(full), full["name"]
            except Exception:
                continue
    return None, ""


def compute_kpis(company: dict, show_demo: bool = False) -> list[dict]:
    cid = company["id"]
    names = industries.profile(company["industry"])["kpis"]
    demo = demo_data.demo_kpis(company["industry"]) if show_demo else {}
    tz = ZoneInfo(company["timezone"] if models.valid_timezone(company["timezone"]) else "Asia/Manila")
    today = datetime.now(tz).date().isoformat()
    tasks = dbm.list_tasks(cid, limit=1000)
    df, ds_name = _latest_real_df(cid)
    rev = _find_col(df, "revenue") if df is not None else None
    cost = _find_col(df, "cost") if df is not None else None
    orders = _find_col(df, "orders") if df is not None else None
    out = []
    for name in names:
        low = name.lower()
        value, source, note = None, "none", "No data connected"
        if low == "open tasks":
            value = str(sum(1 for t in tasks if t["status"] in models.OPEN_STATUSES)); source, note = "database", "From your task list"
        elif low == "overdue tasks":
            value = str(sum(1 for t in tasks if t["due_date"] and t["due_date"] < today and t["status"] in models.OPEN_STATUSES))
            source, note = "database", "From your task list"
        elif low in ("revenue", "daily sales") and rev:
            value, source, note = f"{df[rev].sum():,.2f}", "data", f"Sum of '{rev}' in {ds_name}"
        elif low == "expenses" and cost:
            value, source, note = f"{df[cost].sum():,.2f}", "data", f"Sum of '{cost}' in {ds_name}"
        elif low == "net profit" and rev and cost:
            value, source, note = f"{df[rev].sum() - df[cost].sum():,.2f}", "data", f"'{rev}' minus '{cost}' in {ds_name}"
        elif low in ("orders", "order count", "transactions") and orders:
            value, source, note = f"{df[orders].sum():,.0f}", "data", f"Sum of '{orders}' in {ds_name}"
        elif name in demo:
            value, source, note = demo[name], "demo", "DEMO DATA (sample value)"
        out.append({"name": name, "value": value if value is not None else "-", "source": source, "note": note})
    return out
