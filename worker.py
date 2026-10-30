"""Dedicated scheduler worker for always-on deployments.

Run it next to (or instead of) the web app:

    python worker.py

It loads every saved schedule from the same database and fires reports on time, even when
nobody has the web page open. Duplicate protection means it is safe to run alongside the app.
"""
from __future__ import annotations

import database as dbm
import scheduler_service as ss


def main() -> None:
    dbm.init_db()
    if not ss.APSCHEDULER_AVAILABLE:
        raise SystemExit("APScheduler is not installed. Run: pip install -r requirements.txt")
    service = ss.SchedulerService(blocking=True)
    print("ATLAS worker started. Press Ctrl+C to stop.")
    try:
        service.start()
    except (KeyboardInterrupt, SystemExit):
        print("ATLAS worker stopped.")


if __name__ == "__main__":
    main()
