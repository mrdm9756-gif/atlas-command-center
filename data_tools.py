"""Real data handling: CSV parsing and pandas-based analysis (no AI involved)."""
from __future__ import annotations

import io

import pandas as pd

import config
import database as dbm
import models

MAX_ROWS = 200_000
DEMO_PREFIX = "DEMO DATA"


def parse_csv_bytes(raw: bytes) -> tuple[pd.DataFrame, str]:
    """Validate and parse an uploaded CSV. Returns (dataframe, decoded_text)."""
    if not raw:
        raise models.ValidationError("The file is empty.")
    if len(raw) > config.MAX_CSV_BYTES:
        raise models.ValidationError("The file is too large (max 5 MB).")
    for enc in ("utf-8-sig", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:  # pragma: no cover
        raise models.ValidationError("Could not read the file as text.")
    try:
        df = pd.read_csv(io.StringIO(text))
    except Exception:
        raise models.ValidationError("That file is not a valid CSV (comma-separated) file.")
    if df.empty or len(df.columns) == 0:
        raise models.ValidationError("The CSV has no data rows.")
    if len(df) > MAX_ROWS:
        raise models.ValidationError(f"Too many rows (max {MAX_ROWS:,}).")
    return df, text


def df_from_dataset(dataset: dict) -> pd.DataFrame:
    return pd.read_csv(io.StringIO(dataset["csv_text"]))


def is_demo_dataset(dataset: dict) -> bool:
    return str(dataset.get("name", "")).startswith(DEMO_PREFIX)


def data_status(company_id: int) -> str:
    """Provenance label for this workspace's data."""
    sets = dbm.list_datasets(company_id)
    if not sets:
        return models.DATA_NONE
    if all(str(s["name"]).startswith(DEMO_PREFIX) for s in sets):
        return models.DATA_SIMULATED
    return models.DATA_REAL


def summarize_df(df: pd.DataFrame, name: str = "dataset") -> str:
    lines = [f"Dataset: {name} - {len(df):,} rows x {len(df.columns)} columns",
             "Columns: " + ", ".join(f"{c} ({df[c].dtype})" for c in df.columns[:30])]
    missing = df.isna().sum()
    missing = missing[missing > 0]
    if len(missing):
        lines.append("Missing values: " + ", ".join(f"{c}={int(n)}" for c, n in missing.items()))
    else:
        lines.append("Missing values: none")
    num = df.select_dtypes("number")
    if not num.empty:
        lines.append("Numeric columns (sum / mean / min / max):")
        for c in list(num.columns)[:12]:
            s = num[c].dropna()
            if s.empty:
                continue
            lines.append(f"  - {c}: {s.sum():,.2f} / {s.mean():,.2f} / {s.min():,.2f} / {s.max():,.2f}")
    cat = df.select_dtypes(exclude="number")
    for c in list(cat.columns)[:4]:
        top = cat[c].astype(str).value_counts().head(3)
        if 0 < cat[c].nunique() <= max(20, len(df) // 2):
            lines.append(f"Top values in {c}: " + ", ".join(f"{k} ({v})" for k, v in top.items()))
    return "\n".join(lines)


def detect_anomalies(df: pd.DataFrame, z: float = 3.0, max_items: int = 10) -> list[dict]:
    """Flag numeric outliers (|z-score| > z). Needs at least 8 rows to be meaningful."""
    found: list[dict] = []
    if len(df) < 8:
        return found
    for c in df.select_dtypes("number").columns:
        s = df[c].dropna()
        if s.std(ddof=0) == 0 or len(s) < 8:
            continue
        zs = (s - s.mean()) / s.std(ddof=0)
        for idx in zs[zs.abs() > z].index:
            found.append({"column": c, "row": int(idx), "value": float(df.loc[idx, c]),
                          "z_score": round(float(zs.loc[idx]), 2)})
    return found[:max_items]


def analysis_report(company_id: int, max_datasets: int = 3) -> str:
    """Real, computed text summary of the workspace's most recent datasets ('' when none)."""
    parts: list[str] = []
    for ds in dbm.list_datasets(company_id)[:max_datasets]:
        full = dbm.get_dataset(ds["id"], company_id)
        if not full:
            continue
        try:
            df = df_from_dataset(full)
        except Exception:
            continue
        tag = " [DEMO DATA - simulated]" if is_demo_dataset(full) else " [user-provided]"
        block = summarize_df(df, full["name"] + tag)
        anomalies = detect_anomalies(df)
        if anomalies:
            block += "\nPossible anomalies (|z| > 3): " + "; ".join(
                f"{a['column']} row {a['row']} = {a['value']:,.2f} (z={a['z_score']})" for a in anomalies)
        parts.append(block)
    return "\n\n".join(parts)


def company_data_summary(company_id: int) -> str:
    """Short context for non-analyst agents. Empty string when no data exists."""
    return analysis_report(company_id, max_datasets=2)[:3500]
