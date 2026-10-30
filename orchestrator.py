"""The AI CEO orchestrator.

Workflow (matches the spec):
    owner request -> classify -> assign to specialised agent -> agent works -> result + status saved
    -> CEO reviews -> consolidated report -> dashboard

Safety rules enforced here (not just in prompts):
* Agents only prepare INTERNAL work. If a request involves an external/consequential action
  (messaging real customers, publishing, ad spend, purchases, refunds, payments, production
  changes) the task moves to "Waiting for Approval" and an ApprovalRequest with the exact action,
  target, amount, scope and consequence is created, tied to that task ID.
* Money-moving actions are BLOCKED in this version and can only be rejected.
* Approving an action records the decision. Because no external integration is implemented,
  nothing is ever executed externally and the record says so plainly.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import agents as agent_registry
import ai_provider
import config
import data_tools
import database as dbm
import industries
import models
from agents.base_agent import SAFETY_BOUNDARIES

MAX_TASK_ATTEMPTS = 3

CONSEQUENCES = {
    "send_customer_message": "Real customers would receive the message. It cannot be unsent.",
    "publish_content": "The content would become publicly visible under the company's name.",
    "spend_ad_budget": "Advertising money would be spent. BLOCKED in this version.",
    "make_purchase": "A purchase would be made and money spent. BLOCKED in this version.",
    "issue_refund": "Money would be returned to a customer. BLOCKED in this version.",
    "financial_transaction": "Funds would move or a trade would execute. BLOCKED in this version.",
    "modify_production": "A live system would be changed, possibly affecting customers.",
}

_EXTERNAL_PATTERNS = {
    "send_customer_message": r"\b(send|email|e-mail|text|sms|blast|broadcast)\b[^.\n]{0,60}\b(customers?|clients?|subscribers?|leads?|everyone|mailing list|contacts?)\b",
    "publish_content": r"\b(publish|go live|post (it |this |that )?(to|on)|upload (it )?to|schedule (a )?post)\b",
    "spend_ad_budget": r"\b(spend|run ads?|launch ads?|boost (the |a )?post|pay for ads?|ad spend|increase (the )?ad budget)\b",
    "make_purchase": r"\b(buy|purchase|place an order|order (more )?(supplies|stock|inventory))\b",
    "issue_refund": r"\b(issue|process|give|approve)\b[^.\n]{0,25}\brefunds?\b",
    "financial_transaction": r"\b(transfer|wire|pay (the )?(invoice|supplier|salary|salaries|bill|vendor)|make a payment|trade|invest)\b",
    "modify_production": r"\b(deploy|modify|change|update|delete|restart)\b[^.\n]{0,40}\b(production|live (site|system|server|database))\b",
}
_AMOUNT_RE = re.compile(r"(?:₱|PHP|USD|\$|P)\s?\d[\d,]*(?:\.\d+)?", re.I)

CEO_INSTRUCTIONS = (
    "You are the CEO Orchestrator. You receive the owner's instructions, decide which specialised agent "
    "should handle each task, track status, review agent results, and write short executive summaries. "
    "Highlight overdue tasks, risks and decisions that need the owner's approval. Only state facts that "
    "appear in the provided status data or reports; never invent numbers."
)


def _utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


class Orchestrator:
    def __init__(self, company_id: int, provider: ai_provider.AIProvider | None = None):
        self.company_id = company_id
        self.provider = provider or ai_provider.get_provider()
        self.company = dbm.get_company(company_id)
        if self.company is None:
            raise models.ValidationError("Unknown workspace.")
        dbm.ensure_agents(company_id, agent_registry.agent_keys())

    # ------------------------------------------------------------------ #
    # Context
    # ------------------------------------------------------------------ #
    @property
    def tz(self) -> ZoneInfo:
        name = self.company["timezone"]
        return ZoneInfo(name if models.valid_timezone(name) else config.DEFAULT_TIMEZONE)

    def context(self) -> dict:
        return {
            "company_id": self.company_id,
            "company": self.company["name"],
            "industry": industries.display_name(self.company),
            "language": self.company["language"],
            "ai_name": dbm.get_setting("ai_name"),
            "owner_name": dbm.get_setting("owner_name"),
            "data_summary": data_tools.company_data_summary(self.company_id),
            "data_status": data_tools.data_status(self.company_id),
        }

    def enabled_agent_keys(self) -> list[str]:
        states = dbm.list_agent_states(self.company_id)
        return [k for k in agent_registry.agent_keys() if states.get(k, {}).get("enabled", 1)]

    def _data_label(self, mode: str) -> str:
        status = data_tools.data_status(self.company_id)
        if status == models.DATA_NONE:
            return models.DATA_ESTIMATED if mode == models.MODE_LIVE else models.DATA_NONE
        return status

    def _source_data(self) -> str:
        names = [d["name"] for d in dbm.list_datasets(self.company_id)[:5]]
        return ("Datasets: " + ", ".join(names)) if names else "No datasets connected - owner request and general knowledge only"

    # ------------------------------------------------------------------ #
    # Classification & external-action detection
    # ------------------------------------------------------------------ #
    def classify(self, text: str) -> tuple[str, str]:
        text_l = text.lower()
        enabled = self.enabled_agent_keys()
        if not enabled:
            raise models.ValidationError("No agents are enabled. Enable at least one agent in Owner Settings.")
        # 1. explicit mention ("Marketing Agent, ...")
        for key in enabled:
            ag = agent_registry.get_agent(key)
            if ag and (ag.name.lower() in text_l or ag.name.lower().replace(" agent", "") + " agent" in text_l):
                return key, f"You addressed the {ag.name} directly."
        # 2. keyword scoring
        scores = {}
        for key in enabled:
            ag = agent_registry.get_agent(key)
            scores[key] = sum(1 for kw in ag.keywords if kw in text_l) if ag else 0
        best = max(scores, key=lambda k: scores[k])
        if scores[best] > 0:
            return best, f"Matched {scores[best]} keyword(s) for the {agent_registry.get_agent(best).name}."
        # 3. ask the live model (only when a real provider is configured)
        if self.provider.is_live:
            options = ", ".join(enabled)
            res = self.provider.generate(
                "You route tasks. Reply with exactly one word: the best agent key.",
                f"Agent keys: {options}\nTask: {text[:500]}")
            pick = res.text.strip().lower().strip(".`'\" ") if res.ok else ""
            if pick in enabled:
                return pick, "Chosen by the AI model."
        fallback = "operations" if "operations" in enabled else enabled[0]
        return fallback, "No clear match; defaulted to a general-purpose agent. You can reassign it."

    def detect_external_actions(self, text: str) -> list[dict]:
        found = []
        for action_type, pattern in _EXTERNAL_PATTERNS.items():
            m = re.search(pattern, text, re.I)
            if m:
                found.append({"action_type": action_type, "matched": m.group(0)})
        return found

    # ------------------------------------------------------------------ #
    # Tasks
    # ------------------------------------------------------------------ #
    def create_task(self, text: str, agent_key: str | None = None, title: str | None = None,
                    priority: str = "Normal", due_date: str | None = None,
                    source: str = "owner", status: str = models.QUEUED) -> tuple[int, str]:
        text = models.clean_text(text, field="Task", required=True)
        reason = "Assigned manually."
        if not agent_key:
            agent_key, reason = self.classify(text)
        if agent_registry.get_agent(agent_key) is None:
            raise models.ValidationError("Unknown agent.")
        title = models.clean_text(title or text.splitlines()[0][:80], field="Title", max_len=200, required=True)
        tid = dbm.create_task(self.company_id, title, agent_key, description=text, status=status,
                              priority=priority, due_date=due_date or None, source=source)
        dbm.log_audit(self.company_id, "owner" if source != "schedule" else "scheduler", "task_created",
                      f"task #{tid} -> {agent_key}: {title}")
        return tid, reason

    def submit_request(self, text: str, agent_key: str | None = None, run: bool = True,
                       **kwargs) -> dict:
        """Owner request -> classified, queued and (optionally) executed task."""
        tid, reason = self.create_task(text, agent_key, **kwargs)
        task = dbm.get_task(tid, self.company_id)
        outcome = self.execute_task(tid) if run else {"status": models.QUEUED}
        return {"task_id": tid, "agent_key": task["agent_key"], "reason": reason, **outcome}

    def execute_task(self, task_id: int) -> dict:
        task = dbm.get_task(task_id, self.company_id)
        if task is None:
            raise models.ValidationError("Task not found in this workspace.")
        if task["status"] not in (models.QUEUED, models.DRAFT, models.FAILED):
            raise models.ValidationError(f"Task #{task_id} is '{task['status']}' and cannot be run.")
        if task["attempts"] >= MAX_TASK_ATTEMPTS:
            raise models.ValidationError(f"Task #{task_id} reached the retry limit ({MAX_TASK_ATTEMPTS}).")
        agent = agent_registry.get_agent(task["agent_key"])
        state = dbm.list_agent_states(self.company_id).get(task["agent_key"], {})
        if agent is None:
            raise models.ValidationError("The assigned agent no longer exists.")
        if not state.get("enabled", 1):
            raise models.ValidationError(f"{agent.name} is disabled. Enable it in Owner Settings.")
        if not state.get("allow_internal_tasks", 1):
            raise models.ValidationError(f"{agent.name} is not permitted to run tasks on its own.")

        dbm.update_task(task_id, self.company_id, status=models.IN_PROGRESS, error="",
                        attempts=task["attempts"] + 1, started_at=models.utc_now_iso())
        dbm.update_agent_state(self.company_id, agent.key, status="working", current_task=task["title"])
        dbm.log_audit(self.company_id, agent.key, "task_started", f"task #{task_id}")

        prompt = (f"TASK #{task_id}: {task['title']}\n\n{task['description']}\n\n"
                  "Prepare the deliverable now. If key details are missing, list what you need AND proceed "
                  "with clearly labelled assumptions.")
        try:
            result = agent.run(self.provider, prompt, self.context())
        except Exception as exc:  # an agent bug must never crash the app
            result = ai_provider.AIResult("", models.MODE_ERROR, config.redact(f"{type(exc).__name__}: {exc}"))

        fresh = dbm.get_task(task_id, self.company_id)
        if fresh and fresh["status"] == models.CANCELLED:      # cancelled while running -> discard
            self._agent_idle(agent.key)
            dbm.log_audit(self.company_id, "owner", "task_result_discarded", f"task #{task_id} was cancelled")
            return {"status": models.CANCELLED}

        now = models.utc_now_iso()
        if not result.ok:
            dbm.update_task(task_id, self.company_id, status=models.FAILED, error=result.error,
                            result_mode=models.MODE_ERROR, completed_at=now)
            dbm.add_agent_report(self.company_id, agent.key, f"Task #{task_id}: {task['title']}", "",
                                 report_type="task", status="failed", mode=models.MODE_ERROR,
                                 error=result.error, task_id=task_id)
            self._agent_idle(agent.key)
            dbm.log_audit(self.company_id, agent.key, "task_failed", f"task #{task_id}: {result.error}")
            return {"status": models.FAILED, "error": result.error}

        text = result.text
        external = self.detect_external_actions(f"{task['title']}\n{task['description']}")
        status = models.COMPLETED
        if external and not state.get("allow_external_requests", 1):
            text += ("\n\n[Note: this request involves an external action, but this agent is not permitted to "
                     "request external actions. Only the internal draft above was prepared.]")
            external = []
        dbm.update_task(task_id, self.company_id, result=text, result_mode=result.mode,
                        status=status, completed_at=now)
        dbm.add_agent_report(self.company_id, agent.key, f"Task #{task_id}: {task['title']}", text,
                             report_type="task", mode=result.mode, data_label=self._data_label(result.mode),
                             source_data=self._source_data(), task_id=task_id)
        self._agent_idle(agent.key)
        dbm.log_audit(self.company_id, agent.key, "task_completed", f"task #{task_id} ({result.mode})")

        if external:
            existing = [a for a in dbm.list_approvals(self.company_id) if a["task_id"] == task_id]
            if not existing:  # never create duplicate approvals when a task is re-run
                amount_m = _AMOUNT_RE.search(task["description"] or task["title"])
                for ext in external:
                    self.request_approval(
                        task_id, ext["action_type"],
                        target=f"As described in task #{task_id}: \"{(task['description'] or task['title'])[:160]}\"",
                        scope=f"One-time action. Draft prepared by {agent.name}; trigger phrase: \"{ext['matched']}\".",
                        amount=amount_m.group(0) if amount_m else "", requested_by=agent.key,
                        _set_status=False)
                dbm.update_task(task_id, self.company_id, status=models.WAITING_APPROVAL)
                status = models.WAITING_APPROVAL
        return {"status": status, "mode": result.mode}

    def run_queued(self, limit: int = 10) -> list[dict]:
        outcomes = []
        for t in reversed(dbm.list_tasks(self.company_id, status=models.QUEUED, limit=limit)):
            try:
                outcomes.append({"task_id": t["id"], **self.execute_task(t["id"])})
            except models.ValidationError as exc:
                outcomes.append({"task_id": t["id"], "status": "skipped", "error": str(exc)})
        return outcomes

    def cancel_task(self, task_id: int) -> None:
        task = dbm.get_task(task_id, self.company_id)
        if task is None:
            raise models.ValidationError("Task not found.")
        if task["status"] not in models.OPEN_STATUSES:
            raise models.ValidationError("Only open tasks can be cancelled.")
        dbm.update_task(task_id, self.company_id, status=models.CANCELLED, completed_at=models.utc_now_iso())
        for ap in dbm.list_approvals(self.company_id, status=models.APPROVAL_PENDING):
            if ap["task_id"] == task_id:
                dbm.decide_approval(ap["id"], self.company_id, models.APPROVAL_REJECTED, "not_executed",
                                    "Rejected automatically: the task was cancelled.")
        self._agent_idle(task["agent_key"])
        dbm.log_audit(self.company_id, "owner", "task_cancelled", f"task #{task_id}")

    def recover_stale_tasks(self) -> int:
        """Fail 'In Progress' tasks left behind by a crash/restart. Returns how many were fixed."""
        cutoff = models.utc_now() - timedelta(minutes=config.TASK_STALE_MINUTES)
        fixed = 0
        for t in dbm.list_tasks(self.company_id, status=models.IN_PROGRESS):
            started = models.to_local(t.get("started_at"), "UTC")
            if started is None or started < cutoff:
                dbm.update_task(t["id"], self.company_id, status=models.FAILED,
                                error=f"Interrupted: the app restarted or the task ran longer than "
                                      f"{config.TASK_STALE_MINUTES} minutes.")
                self._agent_idle(t["agent_key"])
                dbm.log_audit(self.company_id, "system", "task_recovered", f"task #{t['id']} marked Failed")
                fixed += 1
        return fixed

    def _agent_idle(self, agent_key: str) -> None:
        busy = [t for t in dbm.list_tasks(self.company_id, status=models.IN_PROGRESS, agent_key=agent_key)]
        if busy:
            dbm.update_agent_state(self.company_id, agent_key, status="working", current_task=busy[0]["title"])
        else:
            dbm.update_agent_state(self.company_id, agent_key, status="idle", current_task="")

    # ------------------------------------------------------------------ #
    # Approvals
    # ------------------------------------------------------------------ #
    def request_approval(self, task_id: int, action_type: str, target: str, scope: str,
                         amount: str = "", consequence: str | None = None,
                         requested_by: str = "owner", _set_status: bool = True) -> int:
        spec = models.EXTERNAL_ACTIONS.get(action_type)
        if spec is None:
            raise models.ValidationError("Unknown action type.")
        aid = dbm.create_approval(self.company_id, task_id, action_type, target, scope,
                                  consequence or CONSEQUENCES[action_type], amount, requested_by)
        if _set_status:
            task = dbm.get_task(task_id, self.company_id)
            if task and task["status"] in models.OPEN_STATUSES:
                dbm.update_task(task_id, self.company_id, status=models.WAITING_APPROVAL)
        dbm.log_audit(self.company_id, requested_by, "approval_requested",
                      f"approval #{aid} task #{task_id} {action_type}")
        return aid

    def decide(self, approval_id: int, approve: bool, note: str = "") -> dict:
        ap = dbm.get_approval(approval_id, self.company_id)
        if ap is None:
            raise models.ValidationError("Approval request not found in this workspace.")
        if ap["status"] != models.APPROVAL_PENDING:
            raise models.ValidationError("This request was already decided.")
        task = dbm.get_task(ap["task_id"], self.company_id)
        if task is None or task["status"] != models.WAITING_APPROVAL:
            raise models.ValidationError("The task tied to this approval is no longer waiting for approval.")
        blocked = models.EXTERNAL_ACTIONS[ap["action_type"]]["blocked"]
        if approve and blocked:
            raise models.ValidationError(
                "This action involves spending or moving money. It is blocked in this version and can only be rejected.")
        if approve:
            outcome = ("Approval recorded. NOT executed: no external integration is connected, so nothing "
                       "was sent, published or changed. Carry out the action yourself using the prepared draft.")
            dbm.decide_approval(approval_id, self.company_id, models.APPROVAL_APPROVED, "not_executed", outcome, note)
        else:
            dbm.decide_approval(approval_id, self.company_id, models.APPROVAL_REJECTED, "not_executed",
                                "Rejected by owner. Nothing was done.", note)
        dbm.log_audit(self.company_id, "owner", "approval_approved" if approve else "approval_rejected",
                      f"approval #{approval_id} task #{ap['task_id']} {ap['action_type']}")
        remaining = [a for a in dbm.list_approvals(self.company_id) if a["task_id"] == ap["task_id"]]
        if not any(a["status"] == models.APPROVAL_PENDING for a in remaining):
            any_ok = any(a["status"] == models.APPROVAL_APPROVED for a in remaining)
            dbm.update_task(ap["task_id"], self.company_id,
                            status=models.COMPLETED if any_ok else models.CANCELLED,
                            completed_at=models.utc_now_iso())
        return {"approved": approve, "executed": False}

    # ------------------------------------------------------------------ #
    # Executive snapshot (real facts from the database)
    # ------------------------------------------------------------------ #
    def snapshot(self) -> dict:
        tasks = dbm.list_tasks(self.company_id, limit=1000)
        today = datetime.now(self.tz).date().isoformat()
        counts = {s: 0 for s in models.TASK_STATUSES}
        for t in tasks:
            counts[t["status"]] = counts.get(t["status"], 0) + 1
        overdue = [t for t in tasks if t["due_date"] and t["due_date"] < today and t["status"] in models.OPEN_STATUSES]
        pending = dbm.list_approvals(self.company_id, status=models.APPROVAL_PENDING)
        failed = [t for t in tasks if t["status"] == models.FAILED]
        return {"counts": counts, "overdue": overdue, "pending_approvals": pending, "failed": failed,
                "total": len(tasks), "today": today}

    def snapshot_text(self) -> str:
        s = self.snapshot()
        c = s["counts"]
        lines = [f"Tasks: {s['total']} total; " + ", ".join(f"{k}: {v}" for k, v in c.items() if v),
                 f"Overdue tasks: {len(s['overdue'])}" + ("".join(f"\n  - #{t['id']} {t['title']} (due {t['due_date']})" for t in s['overdue'][:8])),
                 f"Pending approvals needing the owner: {len(s['pending_approvals'])}",
                 f"Failed tasks: {len(s['failed'])}"]
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # CEO + agent chat
    # ------------------------------------------------------------------ #
    def _history(self, agent_key: str, limit: int = 12) -> list[dict]:
        return [m for m in dbm.get_messages(self.company_id, agent_key, limit=limit)
                if m["role"] in ("owner", "agent") and m["mode"] in (models.MODE_LIVE, models.MODE_DEMO, "owner")]

    def _store_result(self, agent_key: str, res: ai_provider.AIResult) -> None:
        if res.ok:
            dbm.add_message(self.company_id, agent_key, "agent", res.text, res.mode)
        else:
            dbm.add_message(self.company_id, agent_key, "system",
                            f"Could not get a response: {res.error}", models.MODE_ERROR)

    def chat_with_agent(self, agent_key: str, message: str) -> ai_provider.AIResult:
        agent = agent_registry.get_agent(agent_key)
        if agent is None:
            raise models.ValidationError("Unknown agent.")
        message = models.clean_text(message, field="Message", required=True)
        history = self._history(agent_key)
        dbm.add_message(self.company_id, agent_key, "owner", message, "owner")
        try:
            res = agent.run(self.provider, message, self.context(), history)
        except Exception as exc:
            res = ai_provider.AIResult("", models.MODE_ERROR, config.redact(f"{type(exc).__name__}: {exc}"))
        self._store_result(agent_key, res)
        return res

    def task_from_last_message(self, agent_key: str) -> int:
        msgs = [m for m in dbm.get_messages(self.company_id, agent_key) if m["role"] == "owner"]
        if not msgs:
            raise models.ValidationError("Send a message first - the task is created from your last message.")
        tid, _ = self.create_task(msgs[-1]["content"], agent_key, source="chat")
        dbm.add_message(self.company_id, agent_key, "system",
                        f"Task #{tid} created from your last message (status: Queued).", models.MODE_SYSTEM)
        return tid

    def ceo_system_prompt(self) -> str:
        ctx = self.context()
        return (f"You are {ctx['ai_name']}, the AI CEO of {ctx['company']} ({ctx['industry']}). "
                f"You address the owner as {ctx['owner_name']}.\n{CEO_INSTRUCTIONS}\n\n"
                f"CURRENT STATUS (real data from the system):\n{self.snapshot_text()}\n\n"
                f"AVAILABLE DATA:\n{ctx['data_summary'] or 'No datasets uploaded.'}\n\n"
                f"{SAFETY_BOUNDARIES}")

    def _ceo_generate(self, prompt: str, history=None) -> ai_provider.AIResult:
        return self.provider.generate(
            self.ceo_system_prompt(), prompt, history,
            {"agent_name": dbm.get_setting("ai_name"), "role": "AI CEO", "outline": [
                "Route the work to the right specialist agent", "Track task status and deadlines",
                "Review the results and summarise them for you", "Ask for your approval before any external action"],
             "needs": ["What outcome you want", "Deadline", "Any real data you can upload"]})

    def ceo_chat(self, message: str, delegate: bool = True) -> dict:
        """Owner talks to the CEO. With delegate=True the request becomes a routed, executed task."""
        message = models.clean_text(message, field="Message", required=True)
        history = self._history("ceo")
        dbm.add_message(self.company_id, "ceo", "owner", message, "owner")
        info: dict = {}
        prompt = message
        if delegate:
            info = self.submit_request(message, source="owner")
            agent = agent_registry.get_agent(info["agent_key"])
            task = dbm.get_task(info["task_id"], self.company_id)
            routing = (f"Routed to {agent.name} as task #{info['task_id']}. {info['reason']} "
                       f"Status: {info['status']}.")
            if info.get("error"):
                routing += f" Error: {info['error']}"
            dbm.add_message(self.company_id, "ceo", "system", routing, models.MODE_SYSTEM)
            if info["status"] in (models.COMPLETED, models.WAITING_APPROVAL) and task:
                fresh = dbm.get_task(info["task_id"], self.company_id)
                prompt = (f"The owner asked: {message}\n\n{agent.name} produced this result for task "
                          f"#{info['task_id']} (result type: {fresh['result_mode']}):\n{(fresh['result'] or '')[:3500]}\n\n"
                          "Review it briefly: what was done, key points, risks, and any decision needed from the owner."
                          + (" Note: an external action is waiting for the owner's approval in the Approvals page."
                             if info["status"] == models.WAITING_APPROVAL else ""))
            else:
                self._store_result("ceo", ai_provider.AIResult("", models.MODE_ERROR, info.get("error", "The task did not complete.")))
                return info
        res = self._ceo_generate(prompt, history)
        self._store_result("ceo", res)
        info["reply_mode"] = res.mode
        return info

    # ------------------------------------------------------------------ #
    # Reports
    # ------------------------------------------------------------------ #
    @staticmethod
    def period_for(kind: str, now: datetime | None = None) -> tuple[str, str, str]:
        now = (now or models.utc_now()).astimezone(timezone.utc)
        days = {"daily": 1, "weekly": 7, "monthly": 30}.get(kind, 1)
        start = now - timedelta(days=days)
        return _utc(start), _utc(now), f"last {days} day(s)"

    def generate_agent_report(self, agent_key: str, report_type: str = "adhoc",
                              period_start: str | None = None, period_end: str | None = None,
                              include_tasks: bool = True, include_financials: bool = True,
                              consolidated_id: int | None = None) -> dict:
        agent = agent_registry.get_agent(agent_key)
        if agent is None:
            raise models.ValidationError("Unknown agent.")
        if period_start is None or period_end is None:
            period_start, period_end, _ = self.period_for(report_type if report_type in models.SCHEDULE_KINDS else "daily")
        ctx = self.context()
        if not include_financials and agent.key == "finance":
            ctx["data_summary"] = ""
        task_lines = []
        if include_tasks:
            for t in dbm.list_tasks(self.company_id, agent_key=agent_key, limit=200):
                if t["updated_at"] >= period_start:
                    task_lines.append(f"- #{t['id']} [{t['status']}] {t['title']}"
                                      + (f" (due {t['due_date']})" if t["due_date"] else ""))
        title = f"{agent.name} {report_type} report"
        prompt = (f"Prepare your {report_type} report covering {models.fmt_local(period_start, self.company['timezone'])} "
                  f"to {models.fmt_local(period_end, self.company['timezone'])} ({self.company['timezone']}).\n"
                  + ("Tasks in this period (real records):\n" + ("\n".join(task_lines[:25]) or "- none") + "\n"
                     if include_tasks else "Do not discuss tasks.\n")
                  + ("" if include_financials else "Do NOT include financial figures.\n")
                  + "Structure: Summary; Key findings; Risks/blockers; Recommended next actions. "
                    "Use only real data provided; label estimates.")
        try:
            res = agent.run(self.provider, prompt, ctx)
        except Exception as exc:
            res = ai_provider.AIResult("", models.MODE_ERROR, config.redact(f"{type(exc).__name__}: {exc}"))
        if res.ok:
            rid = dbm.add_agent_report(
                self.company_id, agent_key, title, res.text, report_type=report_type, mode=res.mode,
                data_label=self._data_label(res.mode), source_data=self._source_data(),
                consolidated_id=consolidated_id, period_start=period_start, period_end=period_end)
            return {"report_id": rid, "agent_key": agent_key, "ok": True, "mode": res.mode, "text": res.text}
        rid = dbm.add_agent_report(
            self.company_id, agent_key, title, "", report_type=report_type, status="failed",
            mode=models.MODE_ERROR, error=res.error, consolidated_id=consolidated_id,
            period_start=period_start, period_end=period_end, source_data=self._source_data())
        dbm.log_audit(self.company_id, agent_key, "report_failed", res.error)
        return {"report_id": rid, "agent_key": agent_key, "ok": False, "mode": models.MODE_ERROR,
                "error": res.error, "text": ""}

    def generate_consolidated(self, report_type: str = "adhoc", agent_keys: list[str] | None = None,
                              period_start: str | None = None, period_end: str | None = None,
                              include_tasks: bool = True, include_financials: bool = True,
                              ceo_summary: bool = True, schedule_id: int | None = None) -> int:
        if period_start is None or period_end is None:
            kind = report_type if report_type in models.SCHEDULE_KINDS else "daily"
            period_start, period_end, _ = self.period_for(kind)
        enabled = self.enabled_agent_keys()
        keys = [k for k in (agent_keys or enabled) if k in enabled]
        if not keys:
            raise models.ValidationError("No enabled agents selected for this report.")
        tzname = self.company["timezone"]

        results = []
        for k in keys:                                  # one failure never stops the rest
            try:
                results.append(self.generate_agent_report(k, report_type, period_start, period_end,
                                                          include_tasks, include_financials))
            except Exception as exc:
                results.append({"report_id": None, "agent_key": k, "ok": False,
                                "error": config.redact(f"{type(exc).__name__}: {exc}"), "text": "", "mode": models.MODE_ERROR})
        ok = [r for r in results if r["ok"]]
        bad = [r for r in results if not r["ok"]]

        summary_text, summary_mode = "", models.MODE_ERROR
        if ceo_summary:
            digest = "\n\n".join(f"### {agent_registry.get_agent(r['agent_key']).name}\n{r['text'][:1500]}" for r in ok)
            failures = "\n".join(f"- {agent_registry.get_agent(r['agent_key']).name}: {r.get('error', '')}" for r in bad) or "none"
            prompt = (f"Write the consolidated executive summary for the {report_type} report.\n"
                      f"Agent reports:\n{digest or '(none completed)'}\n\nFailed reports:\n{failures}\n\n"
                      "Include: top highlights, risks, overdue items, and decisions needing the owner. Be concise.")
            cres = self._ceo_generate(prompt)
            summary_text, summary_mode = (cres.text, cres.mode) if cres.ok else (
                f"Executive summary unavailable: {cres.error}", models.MODE_ERROR)

        # overall mode: 'live' only if EVERY generated component is live; any simulated part => demo
        modes = [r["mode"] for r in ok] + ([summary_mode] if ceo_summary and summary_mode != models.MODE_ERROR else [])
        if not modes:
            mode = models.MODE_ERROR
        elif all(m == models.MODE_LIVE for m in modes):
            mode = models.MODE_LIVE
        else:
            mode = models.MODE_DEMO
        data_label = self._data_label(models.MODE_LIVE if mode == models.MODE_LIVE else models.MODE_DEMO)

        label = {"daily": "Daily", "weekly": "Weekly", "monthly": "Monthly"}.get(report_type, "On-demand")
        title = f"{label} CEO Report - {models.fmt_local(period_end, tzname)[:10]}"
        names = [agent_registry.get_agent(r["agent_key"]).name for r in results]
        header = [
            f"# {title}",
            f"- Company: {self.company['name']} ({industries.display_name(self.company)})",
            f"- Created: {models.fmt_local(models.utc_now_iso(), tzname)} ({tzname})",
            f"- Reporting period: {models.fmt_local(period_start, tzname)} to {models.fmt_local(period_end, tzname)}",
            f"- Source data: {self._source_data()}",
            f"- Figures: {models.DATA_LABELS[data_label]}",
            f"- Content type: {models.MODE_LABELS[mode]}",
            f"- Agents included: {', '.join(names)}",
            f"- Components completed: {len(ok)} | failed: {len(bad)}",
            "", "## System facts (computed from the database)", self.snapshot_text(), "",
        ]
        body = list(header)
        if ceo_summary:
            body += [f"## Executive summary by {dbm.get_setting('ai_name')} "
                     f"({models.MODE_LABELS.get(summary_mode, summary_mode)})", summary_text, ""]
        for r in ok:
            ag = agent_registry.get_agent(r["agent_key"])
            body += [f"## {ag.name} ({models.MODE_LABELS[r['mode']]})", r["text"], ""]
        if bad:
            body += ["## Failed components"]
            body += [f"- {agent_registry.get_agent(r['agent_key']).name}: {r.get('error', 'unknown error')}" for r in bad]
        content = "\n".join(body)

        cid = dbm.add_consolidated_report(
            self.company_id, report_type, title, content, mode=mode, agents_included=[r["agent_key"] for r in results],
            completed_count=len(ok), failed_count=len(bad), data_label=data_label,
            period_start=period_start, period_end=period_end, schedule_id=schedule_id,
            delivery="Dashboard only (not emailed)")
        dbm.attach_reports_to_consolidated(self.company_id, [r["report_id"] for r in results if r["report_id"]], cid)
        dbm.log_audit(self.company_id, "scheduler" if schedule_id else "owner", "consolidated_report",
                      f"report #{cid} ({report_type}): {len(ok)} ok, {len(bad)} failed")
        return cid
