"""Report scheduler.

IMPORTANT HOSTING LIMITATION
----------------------------
APScheduler runs INSIDE the application process. Scheduled reports only fire while that process is
alive. Free hosts (including Streamlit Community Cloud) put idle apps to sleep, and a sleeping app
runs nothing. For reliable production scheduling run `python worker.py` as an always-on process
(a small VPS, Railway/Render worker, Docker container or systemd service). The app and the worker
can both run: duplicate protection in the database guarantees each period is generated once.

What this module guarantees:
* Schedules live in SQLite, so they survive restarts (jobs are rebuilt from the DB by sync()).
* One report per (schedule, period): a UNIQUE row in report_runs blocks duplicates.
* An agent failure is recorded and the remaining agents still report.
* Email is only reported as sent when the SMTP server accepted it.
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import config
import database as dbm
import emailer
import models
from orchestrator import Orchestrator

try:  # APScheduler is a normal dependency, but the app must still start without it
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger
    APSCHEDULER_AVAILABLE = True
except Exception:  # pragma: no cover
    APSCHEDULER_AVAILABLE = False


# --------------------------------------------------------------------------- #
# Pure helpers (no APScheduler needed - also used by the UI and the tests)
# --------------------------------------------------------------------------- #
def period_key(kind: str, local_now: datetime) -> str:
    if kind == "daily":
        return local_now.strftime("%Y-%m-%d")
    if kind == "weekly":
        iso = local_now.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    return local_now.strftime("%Y-%m")


def next_run(schedule: dict, tz_name: str, now: datetime | None = None) -> datetime | None:
    """Next local fire time for a schedule row (None if disabled)."""
    if not schedule.get("enabled"):
        return None
    tz = ZoneInfo(tz_name if models.valid_timezone(tz_name) else config.DEFAULT_TIMEZONE)
    now = (now or datetime.now(tz)).astimezone(tz)
    for offset in range(0, 400):
        day = (now + timedelta(days=offset)).date()
        cand = datetime(day.year, day.month, day.day, schedule["hour"], schedule["minute"], tzinfo=tz)
        if cand <= now:
            continue
        kind = schedule["kind"]
        if kind == "weekly" and cand.weekday() != schedule["weekday"]:
            continue
        if kind == "monthly" and cand.day != schedule["day_of_month"]:
            continue
        return cand
    return None


def describe(schedule: dict) -> str:
    t = f"{schedule['hour']:02d}:{schedule['minute']:02d}"
    if schedule["kind"] == "daily":
        return f"Every day at {t}"
    if schedule["kind"] == "weekly":
        return f"Every {models.WEEKDAYS[schedule['weekday']]} at {t}"
    return f"On day {schedule['day_of_month']} of every month at {t}"


# --------------------------------------------------------------------------- #
# The job itself
# --------------------------------------------------------------------------- #
def run_scheduled_report(schedule_id: int, manual: bool = False, provider=None) -> dict:
    """Generate the consolidated report for one schedule. Safe to call from any thread."""
    sched = dbm.get_schedule_by_id(schedule_id)
    if sched is None:
        return {"ran": False, "reason": "Schedule no longer exists."}
    company_id = sched["company_id"]
    if not sched["enabled"] and not manual:
        return {"ran": False, "reason": "Schedule is disabled."}
    company = dbm.get_company(company_id)
    tz = ZoneInfo(company["timezone"] if models.valid_timezone(company["timezone"]) else config.DEFAULT_TIMEZONE)
    local_now = datetime.now(tz)
    key = period_key(sched["kind"], local_now)
    if not manual and not dbm.claim_report_run(schedule_id, key):
        dbm.log_audit(company_id, "scheduler", "duplicate_skipped", f"{sched['kind']} {key}")
        return {"ran": False, "reason": f"Report for period {key} was already generated."}

    try:
        keys = None if sched["agent_keys"] == "all" else [k for k in sched["agent_keys"].split(",") if k]
        orch = Orchestrator(company_id, provider)
        cid = orch.generate_consolidated(
            sched["kind"], keys, include_tasks=bool(sched["include_tasks"]),
            include_financials=bool(sched["include_financials"]), ceo_summary=bool(sched["ceo_summary"]),
            schedule_id=schedule_id)
        delivery = "Dashboard only (not emailed)" if sched["show_in_dashboard"] else "Saved (hidden dashboard option off)"
        if sched["email_enabled"]:
            report = dbm.list_consolidated(company_id, limit=1)[0]
            ok, msg = emailer.send_report_email(emailer.parse_recipients(sched["email_to"]), report["title"], report["content"])
            delivery = msg if not ok else f"{msg} Also saved in the dashboard."
        dbm.update_consolidated_delivery(company_id, cid, delivery)
        dbm.upsert_schedule(company_id, sched["kind"], last_run_at=models.utc_now_iso(),
                            last_status=f"OK - report #{cid}. {delivery}")
        dbm.log_audit(company_id, "scheduler", "scheduled_report_ok", f"{sched['kind']} report #{cid}")
        return {"ran": True, "report_id": cid, "delivery": delivery}
    except Exception as exc:
        msg = config.redact(f"{type(exc).__name__}: {exc}")
        dbm.upsert_schedule(company_id, sched["kind"], last_run_at=models.utc_now_iso(), last_status=f"FAILED - {msg}")
        dbm.log_audit(company_id, "scheduler", "scheduled_report_failed", msg)
        return {"ran": False, "reason": msg}


# --------------------------------------------------------------------------- #
# APScheduler wrapper
# --------------------------------------------------------------------------- #
class SchedulerService:
    JOB_PREFIX = "report:"

    def __init__(self, blocking: bool = False):
        self.blocking = blocking
        self._sched = None
        self._lock = threading.Lock()

    @property
    def available(self) -> bool:
        return APSCHEDULER_AVAILABLE

    @property
    def running(self) -> bool:
        return bool(self._sched and self._sched.running)

    def start(self) -> bool:
        """Start the scheduler and load jobs from the database. Returns False if unavailable."""
        if not APSCHEDULER_AVAILABLE:
            return False
        with self._lock:
            if self._sched is None:
                cls = BlockingScheduler if self.blocking else BackgroundScheduler
                self._sched = cls(timezone=ZoneInfo(config.DEFAULT_TIMEZONE))
            self.sync()
            if not self._sched.running and not self.blocking:
                self._sched.start()
        if self.blocking:
            self._sched.start()      # blocks (used by worker.py)
        return True

    def sync(self) -> int:
        """Rebuild jobs from the saved schedules. Call after every schedule change."""
        if not APSCHEDULER_AVAILABLE or self._sched is None:
            return 0
        for job in list(self._sched.get_jobs()):
            if job.id.startswith(self.JOB_PREFIX):
                job.remove()
        count = 0
        for s in dbm.list_schedules():
            if not s["enabled"]:
                continue
            company = dbm.get_company(s["company_id"])
            if company is None:
                continue
            tz = ZoneInfo(company["timezone"] if models.valid_timezone(company["timezone"]) else config.DEFAULT_TIMEZONE)
            kwargs = {"hour": s["hour"], "minute": s["minute"], "timezone": tz}
            if s["kind"] == "weekly":
                kwargs["day_of_week"] = s["weekday"]
            elif s["kind"] == "monthly":
                kwargs["day"] = s["day_of_month"]
            self._sched.add_job(
                run_scheduled_report, CronTrigger(**kwargs), args=[s["id"]],
                id=f"{self.JOB_PREFIX}{s['id']}", replace_existing=True, coalesce=True,
                max_instances=1, misfire_grace_time=3600)
            count += 1
        return count

    def jobs(self) -> list[dict]:
        if not self._sched:
            return []
        out = []
        for job in self._sched.get_jobs():
            nrt = getattr(job, "next_run_time", None)
            out.append({"id": job.id, "next_run": nrt.strftime("%Y-%m-%d %H:%M %Z") if nrt else "-"})
        return out

    def shutdown(self) -> None:
        if self._sched and self._sched.running:
            self._sched.shutdown(wait=False)


_SERVICE: SchedulerService | None = None
_SERVICE_LOCK = threading.Lock()


def get_service() -> SchedulerService:
    """Process-wide singleton so Streamlit reruns never start a second scheduler."""
    global _SERVICE
    with _SERVICE_LOCK:
        if _SERVICE is None:
            _SERVICE = SchedulerService()
        return _SERVICE
