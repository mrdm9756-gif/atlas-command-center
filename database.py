"""SQLite storage layer.

* Safe initialisation: every table uses CREATE TABLE IF NOT EXISTS and a simple
  numbered-migration list, so upgrading the app never destroys data.
* All business data is keyed by company_id (workspace). Every getter takes the
  company_id so one workspace can never read another workspace's rows.
* All SQL uses bound parameters (no string-formatted user input).
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterable

import config
import models

# --------------------------------------------------------------------------- #
# Connection helpers
# --------------------------------------------------------------------------- #


@contextmanager
def db():
    path = config.db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def query_all(sql: str, params: Iterable[Any] = ()) -> list[dict]:
    with db() as conn:
        return [dict(r) for r in conn.execute(sql, tuple(params)).fetchall()]


def query_one(sql: str, params: Iterable[Any] = ()) -> dict | None:
    with db() as conn:
        row = conn.execute(sql, tuple(params)).fetchone()
        return dict(row) if row else None


def execute(sql: str, params: Iterable[Any] = ()) -> int:
    """Run a write statement, return lastrowid."""
    with db() as conn:
        cur = conn.execute(sql, tuple(params))
        return cur.lastrowid


# --------------------------------------------------------------------------- #
# Schema + migrations
# --------------------------------------------------------------------------- #
MIGRATIONS: list[str] = [
    # ---- 1: initial schema -------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS app_settings (
        key TEXT PRIMARY KEY,
        value TEXT,
        updated_at TEXT
    );
    CREATE TABLE IF NOT EXISTS companies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        industry TEXT NOT NULL DEFAULT 'General Business',
        custom_industry TEXT DEFAULT '',
        language TEXT NOT NULL DEFAULT 'English',
        timezone TEXT NOT NULL DEFAULT 'Asia/Manila',
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS agents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
        agent_key TEXT NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 1,
        status TEXT NOT NULL DEFAULT 'idle',
        current_task TEXT DEFAULT '',
        last_report_at TEXT,
        allow_internal_tasks INTEGER NOT NULL DEFAULT 1,
        allow_external_requests INTEGER NOT NULL DEFAULT 1,
        UNIQUE(company_id, agent_key)
    );
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
        title TEXT NOT NULL,
        description TEXT DEFAULT '',
        agent_key TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'Draft',
        priority TEXT NOT NULL DEFAULT 'Normal',
        due_date TEXT,
        source TEXT NOT NULL DEFAULT 'owner',
        result TEXT DEFAULT '',
        result_mode TEXT DEFAULT '',
        error TEXT DEFAULT '',
        attempts INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        started_at TEXT,
        completed_at TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_tasks_company ON tasks(company_id, status);
    CREATE TABLE IF NOT EXISTS conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
        agent_key TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        mode TEXT NOT NULL DEFAULT 'system',
        created_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_conv ON conversations(company_id, agent_key, id);
    CREATE TABLE IF NOT EXISTS consolidated_reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
        report_type TEXT NOT NULL,
        title TEXT NOT NULL,
        period_start TEXT,
        period_end TEXT,
        content TEXT NOT NULL,
        mode TEXT NOT NULL DEFAULT 'demo',
        agents_included TEXT DEFAULT '[]',
        completed_count INTEGER DEFAULT 0,
        failed_count INTEGER DEFAULT 0,
        data_label TEXT DEFAULT 'none',
        delivery TEXT DEFAULT '',
        schedule_id INTEGER,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS agent_reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
        agent_key TEXT NOT NULL,
        task_id INTEGER,
        consolidated_id INTEGER,
        report_type TEXT NOT NULL DEFAULT 'adhoc',
        title TEXT NOT NULL,
        period_start TEXT,
        period_end TEXT,
        content TEXT DEFAULT '',
        status TEXT NOT NULL DEFAULT 'completed',
        mode TEXT NOT NULL DEFAULT 'demo',
        data_label TEXT DEFAULT 'none',
        source_data TEXT DEFAULT '',
        error TEXT DEFAULT '',
        created_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_reports ON agent_reports(company_id, agent_key, created_at);
    CREATE TABLE IF NOT EXISTS scheduled_reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
        kind TEXT NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 0,
        hour INTEGER NOT NULL DEFAULT 8,
        minute INTEGER NOT NULL DEFAULT 0,
        weekday INTEGER NOT NULL DEFAULT 0,
        day_of_month INTEGER NOT NULL DEFAULT 1,
        agent_keys TEXT NOT NULL DEFAULT 'all',
        include_tasks INTEGER NOT NULL DEFAULT 1,
        include_financials INTEGER NOT NULL DEFAULT 1,
        ceo_summary INTEGER NOT NULL DEFAULT 1,
        show_in_dashboard INTEGER NOT NULL DEFAULT 1,
        email_enabled INTEGER NOT NULL DEFAULT 0,
        email_to TEXT DEFAULT '',
        last_run_at TEXT,
        last_status TEXT DEFAULT '',
        UNIQUE(company_id, kind)
    );
    CREATE TABLE IF NOT EXISTS report_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        schedule_id INTEGER NOT NULL REFERENCES scheduled_reports(id) ON DELETE CASCADE,
        period_key TEXT NOT NULL,
        started_at TEXT NOT NULL,
        UNIQUE(schedule_id, period_key)
    );
    CREATE TABLE IF NOT EXISTS approval_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
        task_id INTEGER NOT NULL,
        action_type TEXT NOT NULL,
        target TEXT NOT NULL,
        amount TEXT DEFAULT '',
        scope TEXT NOT NULL,
        consequence TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        execution_status TEXT NOT NULL DEFAULT 'not_executed',
        execution_note TEXT DEFAULT '',
        requested_by TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        decided_at TEXT,
        decision_note TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER,
        actor TEXT NOT NULL,
        action TEXT NOT NULL,
        detail TEXT DEFAULT '',
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS datasets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        filename TEXT DEFAULT '',
        csv_text TEXT NOT NULL,
        row_count INTEGER DEFAULT 0,
        uploaded_at TEXT NOT NULL
    );
    """,
]

SETTING_DEFAULTS: dict[str, str] = {
    "ai_name": config.DEFAULT_AI_NAME,
    "owner_name": config.DEFAULT_OWNER_NAME,
    "active_company_id": "",
    "voice_gender": "any",         # any | female | male
    "voice_lang": "en",
    "voice_rate": "1.0",
    "voice_pitch": "1.0",
    "speak_enabled": "0",
    "auto_speak": "0",
    "text_only": "0",
    "ui_theme": "atlas_core",
    "ui_custom": json.dumps({"color": "#22d3ee", "intensity": 60, "layout": "orb"}),
    "reduce_motion": "0",
    "pause_animation": "0",
    "notify_dashboard": "1",
    "notify_email": "0",
    "notify_email_to": "",
}


def init_db() -> None:
    """Create tables (idempotent) and make sure a default workspace exists."""
    with db() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
        row = conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
        current = row["v"] or 0
        for idx, script in enumerate(MIGRATIONS, start=1):
            if idx > current:
                conn.executescript(script)
                conn.execute("INSERT INTO schema_version(version) VALUES (?)", (idx,))
    if not list_companies():
        cid = create_company("My Company")
        set_setting("active_company_id", str(cid))
        log_audit(cid, "system", "workspace_created", "Default workspace created on first launch")


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #
def get_setting(key: str, default: str | None = None) -> str:
    row = query_one("SELECT value FROM app_settings WHERE key = ?", (key,))
    if row is not None and row["value"] is not None:
        return row["value"]
    if default is not None:
        return default
    return SETTING_DEFAULTS.get(key, "")


def set_setting(key: str, value: Any) -> None:
    execute(
        "INSERT INTO app_settings(key, value, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
        (key, str(value), models.utc_now_iso()),
    )


def get_bool(key: str) -> bool:
    return get_setting(key) in ("1", "true", "True")


def get_float(key: str, default: float = 1.0) -> float:
    try:
        return float(get_setting(key))
    except (TypeError, ValueError):
        return default


def all_settings() -> dict[str, str]:
    out = dict(SETTING_DEFAULTS)
    for r in query_all("SELECT key, value FROM app_settings"):
        out[r["key"]] = r["value"]
    return out


# --------------------------------------------------------------------------- #
# Companies / workspaces
# --------------------------------------------------------------------------- #
def create_company(name: str, industry: str = "General Business", custom_industry: str = "",
                   language: str = config.DEFAULT_LANGUAGE,
                   timezone_name: str = config.DEFAULT_TIMEZONE) -> int:
    name = models.clean_name(name, field="Company name", max_len=80)
    if not models.valid_timezone(timezone_name):
        raise models.ValidationError("Unknown time zone.")
    return execute(
        "INSERT INTO companies(name, industry, custom_industry, language, timezone, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (name, industry, custom_industry, language, timezone_name, models.utc_now_iso()),
    )


def list_companies() -> list[dict]:
    return query_all("SELECT * FROM companies ORDER BY id")


def get_company(company_id: int) -> dict | None:
    return query_one("SELECT * FROM companies WHERE id = ?", (company_id,))


def update_company(company_id: int, **fields) -> None:
    allowed = {"name", "industry", "custom_industry", "language", "timezone"}
    _update("companies", "id", company_id, None, fields, allowed)


def active_company() -> dict:
    """Return the active workspace, repairing the setting if it is stale."""
    raw = get_setting("active_company_id")
    company = get_company(int(raw)) if raw.isdigit() else None
    if company is None:
        companies = list_companies()
        company = companies[0]
        set_setting("active_company_id", str(company["id"]))
    return company


# --------------------------------------------------------------------------- #
# Generic safe UPDATE (column names come from an allow-list, never from users)
# --------------------------------------------------------------------------- #
def _update(table: str, id_col: str, row_id: int, company_id: int | None,
            fields: dict, allowed: set[str]) -> None:
    sets, params = [], []
    for k, v in fields.items():
        if k not in allowed:
            raise ValueError(f"Column '{k}' cannot be updated on {table}.")
        sets.append(f"{k} = ?")
        params.append(v)
    if not sets:
        return
    sql = f"UPDATE {table} SET {', '.join(sets)} WHERE {id_col} = ?"
    params.append(row_id)
    if company_id is not None:
        sql += " AND company_id = ?"
        params.append(company_id)
    execute(sql, params)


# --------------------------------------------------------------------------- #
# Agents (per-company runtime state)
# --------------------------------------------------------------------------- #
def ensure_agents(company_id: int, agent_keys: list[str]) -> None:
    with db() as conn:
        for key in agent_keys:
            conn.execute(
                "INSERT OR IGNORE INTO agents(company_id, agent_key) VALUES (?, ?)",
                (company_id, key),
            )


def list_agent_states(company_id: int) -> dict[str, dict]:
    return {r["agent_key"]: r for r in
            query_all("SELECT * FROM agents WHERE company_id = ?", (company_id,))}


def update_agent_state(company_id: int, agent_key: str, **fields) -> None:
    allowed = {"enabled", "status", "current_task", "last_report_at",
               "allow_internal_tasks", "allow_external_requests"}
    sets, params = [], []
    for k, v in fields.items():
        if k not in allowed:
            raise ValueError(f"Column '{k}' cannot be updated on agents.")
        sets.append(f"{k} = ?")
        params.append(v)
    if sets:
        execute(f"UPDATE agents SET {', '.join(sets)} WHERE company_id = ? AND agent_key = ?",
                (*params, company_id, agent_key))


# --------------------------------------------------------------------------- #
# Tasks
# --------------------------------------------------------------------------- #
_TASK_FIELDS = {"title", "description", "agent_key", "status", "priority", "due_date",
                "result", "result_mode", "error", "attempts", "started_at", "completed_at",
                "updated_at"}


def create_task(company_id: int, title: str, agent_key: str, description: str = "",
                status: str = models.QUEUED, priority: str = "Normal",
                due_date: str | None = None, source: str = "owner") -> int:
    title = models.clean_text(title, field="Task title", max_len=200, required=True)
    description = models.clean_text(description, field="Task description")
    if status not in models.TASK_STATUSES:
        raise models.ValidationError("Unknown task status.")
    if priority not in models.PRIORITIES:
        priority = "Normal"
    now = models.utc_now_iso()
    return execute(
        "INSERT INTO tasks(company_id, title, description, agent_key, status, priority, due_date, "
        "source, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (company_id, title, description, agent_key, status, priority, due_date, source, now, now),
    )


def get_task(task_id: int, company_id: int) -> dict | None:
    return query_one("SELECT * FROM tasks WHERE id = ? AND company_id = ?", (task_id, company_id))


def list_tasks(company_id: int, status: str | None = None, agent_key: str | None = None,
               limit: int = 500) -> list[dict]:
    sql = "SELECT * FROM tasks WHERE company_id = ?"
    params: list[Any] = [company_id]
    if status:
        sql += " AND status = ?"
        params.append(status)
    if agent_key:
        sql += " AND agent_key = ?"
        params.append(agent_key)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(int(limit))
    return query_all(sql, params)


def update_task(task_id: int, company_id: int, **fields) -> None:
    if "status" in fields and fields["status"] not in models.TASK_STATUSES:
        raise models.ValidationError("Unknown task status.")
    fields["updated_at"] = models.utc_now_iso()
    _update("tasks", "id", task_id, company_id, fields, _TASK_FIELDS)


# --------------------------------------------------------------------------- #
# Conversations
# --------------------------------------------------------------------------- #
def add_message(company_id: int, agent_key: str, role: str, content: str, mode: str = "system") -> int:
    content = models.clean_text(content, field="Message", max_len=20000, required=True)
    return execute(
        "INSERT INTO conversations(company_id, agent_key, role, content, mode, created_at) "
        "VALUES (?,?,?,?,?,?)",
        (company_id, agent_key, role, content, mode, models.utc_now_iso()),
    )


def get_messages(company_id: int, agent_key: str, limit: int = 200) -> list[dict]:
    rows = query_all(
        "SELECT * FROM conversations WHERE company_id = ? AND agent_key = ? ORDER BY id DESC LIMIT ?",
        (company_id, agent_key, int(limit)),
    )
    return list(reversed(rows))


def clear_messages(company_id: int, agent_key: str) -> None:
    execute("DELETE FROM conversations WHERE company_id = ? AND agent_key = ?", (company_id, agent_key))


# --------------------------------------------------------------------------- #
# Reports
# --------------------------------------------------------------------------- #
def add_agent_report(company_id: int, agent_key: str, title: str, content: str, *,
                     report_type: str = "adhoc", status: str = "completed", mode: str = "demo",
                     data_label: str = "none", source_data: str = "", error: str = "",
                     task_id: int | None = None, consolidated_id: int | None = None,
                     period_start: str | None = None, period_end: str | None = None) -> int:
    rid = execute(
        "INSERT INTO agent_reports(company_id, agent_key, task_id, consolidated_id, report_type, title, "
        "period_start, period_end, content, status, mode, data_label, source_data, error, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (company_id, agent_key, task_id, consolidated_id, report_type, title, period_start, period_end,
         content, status, mode, data_label, source_data, config.redact(error), models.utc_now_iso()),
    )
    if status == "completed":
        update_agent_state(company_id, agent_key, last_report_at=models.utc_now_iso())
    return rid


def attach_reports_to_consolidated(company_id: int, report_ids: list[int], consolidated_id: int) -> None:
    for rid in report_ids:
        execute("UPDATE agent_reports SET consolidated_id = ? WHERE id = ? AND company_id = ?",
                (consolidated_id, rid, company_id))


def list_agent_reports(company_id: int, agent_key: str | None = None, report_type: str | None = None,
                       since: str | None = None, until: str | None = None,
                       search: str | None = None, status: str | None = None,
                       limit: int = 300) -> list[dict]:
    sql = "SELECT * FROM agent_reports WHERE company_id = ?"
    params: list[Any] = [company_id]
    if agent_key:
        sql += " AND agent_key = ?"; params.append(agent_key)
    if report_type:
        sql += " AND report_type = ?"; params.append(report_type)
    if status:
        sql += " AND status = ?"; params.append(status)
    if since:
        sql += " AND created_at >= ?"; params.append(since)
    if until:
        sql += " AND created_at <= ?"; params.append(until)
    if search:
        sql += " AND (title LIKE ? OR content LIKE ?)"
        like = f"%{search}%"; params += [like, like]
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(int(limit))
    return query_all(sql, params)


def add_consolidated_report(company_id: int, report_type: str, title: str, content: str, *,
                            mode: str, agents_included: list[str], completed_count: int,
                            failed_count: int, data_label: str, period_start: str | None = None,
                            period_end: str | None = None, schedule_id: int | None = None,
                            delivery: str = "") -> int:
    return execute(
        "INSERT INTO consolidated_reports(company_id, report_type, title, period_start, period_end, content, "
        "mode, agents_included, completed_count, failed_count, data_label, delivery, schedule_id, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (company_id, report_type, title, period_start, period_end, content, mode,
         json.dumps(agents_included), completed_count, failed_count, data_label, delivery,
         schedule_id, models.utc_now_iso()),
    )


def update_consolidated_delivery(company_id: int, report_id: int, delivery: str) -> None:
    execute("UPDATE consolidated_reports SET delivery = ? WHERE id = ? AND company_id = ?",
            (config.redact(delivery), report_id, company_id))


def list_consolidated(company_id: int, report_type: str | None = None, since: str | None = None,
                      until: str | None = None, search: str | None = None,
                      limit: int = 200) -> list[dict]:
    sql = "SELECT * FROM consolidated_reports WHERE company_id = ?"
    params: list[Any] = [company_id]
    if report_type:
        sql += " AND report_type = ?"; params.append(report_type)
    if since:
        sql += " AND created_at >= ?"; params.append(since)
    if until:
        sql += " AND created_at <= ?"; params.append(until)
    if search:
        sql += " AND (title LIKE ? OR content LIKE ?)"
        like = f"%{search}%"; params += [like, like]
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(int(limit))
    rows = query_all(sql, params)
    for r in rows:
        try:
            r["agents_included"] = json.loads(r["agents_included"] or "[]")
        except Exception:
            r["agents_included"] = []
    return rows


# --------------------------------------------------------------------------- #
# Scheduled reports
# --------------------------------------------------------------------------- #
_SCHEDULE_FIELDS = {"enabled", "hour", "minute", "weekday", "day_of_month", "agent_keys",
                    "include_tasks", "include_financials", "ceo_summary", "show_in_dashboard",
                    "email_enabled", "email_to", "last_run_at", "last_status"}


def get_schedule(company_id: int, kind: str) -> dict | None:
    return query_one("SELECT * FROM scheduled_reports WHERE company_id = ? AND kind = ?",
                     (company_id, kind))


def get_schedule_by_id(schedule_id: int) -> dict | None:
    return query_one("SELECT * FROM scheduled_reports WHERE id = ?", (schedule_id,))


def list_schedules(company_id: int | None = None) -> list[dict]:
    if company_id is None:
        return query_all("SELECT * FROM scheduled_reports ORDER BY id")
    return query_all("SELECT * FROM scheduled_reports WHERE company_id = ? ORDER BY id", (company_id,))


def upsert_schedule(company_id: int, kind: str, **fields) -> int:
    if kind not in models.SCHEDULE_KINDS:
        raise models.ValidationError("Unknown schedule type.")
    existing = get_schedule(company_id, kind)
    if existing is None:
        execute("INSERT INTO scheduled_reports(company_id, kind) VALUES (?, ?)", (company_id, kind))
        existing = get_schedule(company_id, kind)
    _update("scheduled_reports", "id", existing["id"], company_id, fields, _SCHEDULE_FIELDS)
    return existing["id"]


def claim_report_run(schedule_id: int, period_key: str) -> bool:
    """Duplicate-run protection. Returns True only for the first caller per period."""
    with db() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO report_runs(schedule_id, period_key, started_at) VALUES (?,?,?)",
            (schedule_id, period_key, models.utc_now_iso()),
        )
        return cur.rowcount == 1


# --------------------------------------------------------------------------- #
# Approvals
# --------------------------------------------------------------------------- #
def create_approval(company_id: int, task_id: int, action_type: str, target: str, scope: str,
                    consequence: str, amount: str = "", requested_by: str = "") -> int:
    if action_type not in models.EXTERNAL_ACTIONS:
        raise models.ValidationError("Unknown external action type.")
    if get_task(task_id, company_id) is None:
        raise models.ValidationError("An approval must be tied to an existing task ID.")
    target = models.clean_text(target, field="Target", max_len=300, required=True)
    scope = models.clean_text(scope, field="Scope", max_len=600, required=True)
    consequence = models.clean_text(consequence, field="Expected consequence", max_len=600, required=True)
    amount = models.clean_text(amount, field="Amount", max_len=60)
    return execute(
        "INSERT INTO approval_requests(company_id, task_id, action_type, target, amount, scope, "
        "consequence, requested_by, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (company_id, task_id, action_type, target, amount, scope, consequence, requested_by,
         models.utc_now_iso()),
    )


def get_approval(approval_id: int, company_id: int) -> dict | None:
    return query_one("SELECT * FROM approval_requests WHERE id = ? AND company_id = ?",
                     (approval_id, company_id))


def list_approvals(company_id: int, status: str | None = None, limit: int = 300) -> list[dict]:
    sql = "SELECT * FROM approval_requests WHERE company_id = ?"
    params: list[Any] = [company_id]
    if status:
        sql += " AND status = ?"; params.append(status)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(int(limit))
    return query_all(sql, params)


def decide_approval(approval_id: int, company_id: int, status: str, execution_status: str,
                    execution_note: str, decision_note: str = "") -> None:
    execute(
        "UPDATE approval_requests SET status = ?, execution_status = ?, execution_note = ?, "
        "decided_at = ?, decision_note = ? WHERE id = ? AND company_id = ? AND status = 'pending'",
        (status, execution_status, execution_note, models.utc_now_iso(),
         models.clean_text(decision_note, max_len=500), approval_id, company_id),
    )


# --------------------------------------------------------------------------- #
# Audit log
# --------------------------------------------------------------------------- #
def log_audit(company_id: int | None, actor: str, action: str, detail: str = "") -> None:
    try:
        execute(
            "INSERT INTO audit_logs(company_id, actor, action, detail, created_at) VALUES (?,?,?,?,?)",
            (company_id, actor, action, config.redact(detail)[:2000], models.utc_now_iso()),
        )
    except Exception:  # auditing must never crash the app
        pass


def list_audit(company_id: int, limit: int = 200) -> list[dict]:
    return query_all(
        "SELECT * FROM audit_logs WHERE company_id = ? OR company_id IS NULL ORDER BY id DESC LIMIT ?",
        (company_id, int(limit)),
    )


# --------------------------------------------------------------------------- #
# Datasets (user-uploaded CSV files)
# --------------------------------------------------------------------------- #
def add_dataset(company_id: int, name: str, filename: str, csv_text: str, row_count: int) -> int:
    name = models.clean_name(name, field="Dataset name", max_len=100)
    if len(csv_text.encode("utf-8", errors="ignore")) > config.MAX_CSV_BYTES:
        raise models.ValidationError("CSV is too large (max 5 MB).")
    return execute(
        "INSERT INTO datasets(company_id, name, filename, csv_text, row_count, uploaded_at) VALUES (?,?,?,?,?,?)",
        (company_id, name, models.clean_text(filename, max_len=200), csv_text, row_count,
         models.utc_now_iso()),
    )


def list_datasets(company_id: int) -> list[dict]:
    return query_all(
        "SELECT id, company_id, name, filename, row_count, uploaded_at FROM datasets "
        "WHERE company_id = ? ORDER BY id DESC", (company_id,))


def get_dataset(dataset_id: int, company_id: int) -> dict | None:
    return query_one("SELECT * FROM datasets WHERE id = ? AND company_id = ?", (dataset_id, company_id))


def delete_dataset(dataset_id: int, company_id: int) -> None:
    execute("DELETE FROM datasets WHERE id = ? AND company_id = ?", (dataset_id, company_id))
