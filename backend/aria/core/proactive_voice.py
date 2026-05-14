"""
aria/core/proactive_voice.py
Perennia AI — Proactive Voice Engine

Aria doesn't just respond -- she initiates. This engine checks for
urgent notifications, suggests next actions, and can auto-trigger
morning briefings when the LO connects.

All CRM access goes through the HTTP backend client.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from agents.aria_backend_client import call_backend_tool_safe

logger = logging.getLogger("aria.proactive_voice")

# Priority levels for proactive alerts
PRIORITY_CRITICAL = "critical"   # Must mention immediately
PRIORITY_HIGH = "high"           # Mention within first response
PRIORITY_MEDIUM = "medium"       # Mention if natural opening
PRIORITY_LOW = "low"             # Save for end-of-day or briefing


class ProactiveAlert:
    """A single proactive notification Aria should surface."""

    def __init__(
        self,
        priority: str,
        category: str,
        spoken_text: str,
        data: Optional[Dict] = None,
    ):
        self.priority = priority
        self.category = category
        self.spoken_text = spoken_text
        self.data = data or {}
        self.created_at = datetime.now(timezone.utc)

    def __repr__(self):
        return f"<ProactiveAlert priority={self.priority} category={self.category}>"


class ProactiveVoiceEngine:
    """Aria proactively alerts LOs about important events via voice."""

    def __init__(self, session_data: Dict[str, Any]):
        self._session_data = session_data
        self._org_id = session_data.get("organization_id")
        self._user_id = session_data.get("user_id")
        self._surfaced_alerts: List[str] = []  # Track what we've already said

    def _inject_context(self, payload: dict) -> dict:
        if self._org_id:
            payload["organization_id"] = self._org_id
        if self._user_id and "user_id" not in payload:
            payload["user_id"] = self._user_id
        return payload

    async def _call_backend(self, endpoint: str, payload: dict) -> dict:
        return await call_backend_tool_safe(endpoint, self._inject_context(payload))

    async def _execute_tool(self, tool_name: str, params: dict) -> dict:
        return await self._call_backend(
            "/internal/aria/tool/execute",
            {"tool_name": tool_name, "params": self._inject_context(params)},
        )

    # ─── Main Check ──────────────────────────────────────────────────

    async def check_urgent_notifications(self) -> List[ProactiveAlert]:
        """Check for urgent items Aria should proactively mention.

        Called when the LO first connects or during natural pauses.
        Returns alerts sorted by priority (critical first).
        """
        alerts: List[ProactiveAlert] = []

        # Run all checks concurrently
        import asyncio
        results = await asyncio.gather(
            self._check_rate_lock_expiring(),
            self._check_sla_breaches(),
            self._check_overdue_tasks(),
            self._check_high_value_leads(),
            self._check_borrower_replies(),
            return_exceptions=True,
        )

        for result in results:
            if isinstance(result, Exception):
                logger.warning("Proactive check failed: %s", result)
                continue
            if isinstance(result, list):
                alerts.extend(result)

        # Sort by priority and filter out already-surfaced alerts
        priority_order = {PRIORITY_CRITICAL: 0, PRIORITY_HIGH: 1, PRIORITY_MEDIUM: 2, PRIORITY_LOW: 3}
        alerts.sort(key=lambda a: priority_order.get(a.priority, 99))

        # Deduplicate
        unique_alerts = []
        for alert in alerts:
            key = f"{alert.category}:{alert.spoken_text[:50]}"
            if key not in self._surfaced_alerts:
                unique_alerts.append(alert)
                self._surfaced_alerts.append(key)

        return unique_alerts

    async def suggest_next_action(self) -> Optional[str]:
        """After completing a task, suggest what to do next.

        Based on priority, time of day, and pipeline state.
        """
        now = datetime.now(timezone.utc)
        hour = now.hour

        # Get pending tasks
        tasks = await self._execute_tool("get_task_queue", {
            "user_id": str(self._user_id),
            "status": "pending",
            "limit": 5,
        })
        task_data = tasks.get("result", {}).get("data", {}) if isinstance(tasks.get("result"), dict) else {}
        task_list = task_data.get("tasks", [])

        # Morning: suggest briefing if early
        if hour < 10 and not self._has_surfaced("morning_briefing"):
            self._surfaced_alerts.append("morning_briefing")
            return "Want me to run through your morning briefing?"

        # Has overdue tasks
        overdue = [t for t in task_list if t.get("status") == "overdue"]
        if overdue and not self._has_surfaced("overdue_tasks"):
            self._surfaced_alerts.append("overdue_tasks")
            title = overdue[0].get("title", "a task")
            return f"By the way, you've got an overdue task: {title}. Want me to handle it?"

        # Has upcoming tasks
        if task_list:
            top_task = task_list[0]
            title = top_task.get("title", "something")
            return f"Next up on your list is {title}. Want to tackle that?"

        # End of day
        if hour >= 17:
            return "Getting late. Want me to wrap up with an end-of-day recap?"

        return None

    async def morning_auto_briefing(self) -> Optional[str]:
        """Auto-triggered at start of LO's workday.

        Returns a briefing string if it's morning and we haven't briefed yet,
        or None if already briefed or not morning.
        """
        now = datetime.now(timezone.utc)
        if now.hour < 7 or now.hour > 11:
            return None

        if self._has_surfaced("auto_morning_briefing"):
            return None

        self._surfaced_alerts.append("auto_morning_briefing")

        # Import workflow engine to run the briefing
        from aria.core.voice_workflows import VoiceWorkflowEngine
        engine = VoiceWorkflowEngine(self._session_data)
        return await engine.handle_morning_briefing()

    # ─── Individual Checks ───────────────────────────────────────────

    async def _check_rate_lock_expiring(self) -> List[ProactiveAlert]:
        """Check for rate locks expiring today or tomorrow."""
        alerts = []
        try:
            result = await self._execute_tool("get_loans_by_status", {
                "status": "all_active",
                "user_id": str(self._user_id),
            })
            loans = result.get("result", {}).get("data", {}).get("loans", []) if isinstance(result.get("result"), dict) else []

            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")

            for loan in loans:
                lock_exp = loan.get("lock_expiration_date", "")
                borrower = loan.get("borrower_name", "a borrower")
                if lock_exp == today:
                    alerts.append(ProactiveAlert(
                        priority=PRIORITY_CRITICAL,
                        category="rate_lock",
                        spoken_text=f"Urgent: {borrower}'s rate lock expires today. You need to extend or close.",
                        data={"loan_id": loan.get("id"), "borrower": borrower},
                    ))
                elif lock_exp == tomorrow:
                    alerts.append(ProactiveAlert(
                        priority=PRIORITY_HIGH,
                        category="rate_lock",
                        spoken_text=f"Heads up, {borrower}'s rate lock expires tomorrow.",
                        data={"loan_id": loan.get("id"), "borrower": borrower},
                    ))
        except Exception as e:
            logger.debug("Rate lock check failed: %s", e)
        return alerts

    async def _check_sla_breaches(self) -> List[ProactiveAlert]:
        """Check for SLA deadlines approaching or breached."""
        alerts = []
        try:
            result = await self._execute_tool("get_task_queue", {
                "user_id": str(self._user_id),
                "status": "pending",
                "limit": 50,
            })
            tasks = result.get("result", {}).get("data", {}).get("tasks", []) if isinstance(result.get("result"), dict) else []

            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            for task in tasks:
                due = task.get("due_date", "")
                if due and due < today:
                    alerts.append(ProactiveAlert(
                        priority=PRIORITY_HIGH,
                        category="sla_breach",
                        spoken_text=f"You've got an overdue task: {task.get('title', 'untitled')}. It was due {due}.",
                        data={"task_id": task.get("id")},
                    ))
        except Exception as e:
            logger.debug("SLA breach check failed: %s", e)
        return alerts

    async def _check_overdue_tasks(self) -> List[ProactiveAlert]:
        """Check for tasks that are past due."""
        # Already covered by SLA breach check above
        return []

    async def _check_high_value_leads(self) -> List[ProactiveAlert]:
        """Check for new high-value leads that just came in."""
        alerts = []
        try:
            result = await self._execute_tool("find_clients_for_outreach", {
                "loan_stage": "new",
                "days_since_contact": 0,
                "limit": 5,
                "has_phone": "true",
                "user_id": str(self._user_id),
            })
            clients = result.get("result", {}).get("data", {}).get("clients", []) if isinstance(result.get("result"), dict) else []

            for client in clients:
                name = client.get("name", "New lead")
                amount = client.get("loan_amount")
                if amount and float(amount) > 500000:
                    alerts.append(ProactiveAlert(
                        priority=PRIORITY_HIGH,
                        category="high_value_lead",
                        spoken_text=f"You've got a new high-value lead: {name}, looking at ${float(amount):,.0f}.",
                        data={"lead_id": client.get("id")},
                    ))
        except Exception as e:
            logger.debug("High-value lead check failed: %s", e)
        return alerts

    async def _check_borrower_replies(self) -> List[ProactiveAlert]:
        """Check for recent borrower SMS or email replies."""
        alerts = []
        try:
            result = await self._call_backend(
                "/internal/aria/tool/execute",
                {"tool_name": "get_recent_replies", "params": {
                    "user_id": str(self._user_id),
                    "limit": 5,
                }},
            )
            replies = result.get("result", {}).get("data", {}).get("replies", []) if isinstance(result.get("result"), dict) else []

            for reply in replies:
                name = reply.get("contact_name", "A borrower")
                channel = reply.get("channel", "message")
                alerts.append(ProactiveAlert(
                    priority=PRIORITY_MEDIUM,
                    category="borrower_reply",
                    spoken_text=f"{name} replied to your {channel}. Want me to read it?",
                    data={"reply_id": reply.get("id"), "contact_name": name},
                ))
        except Exception as e:
            logger.debug("Borrower reply check failed: %s", e)
        return alerts

    # ─── Helpers ─────────────────────────────────────────────────────

    def _has_surfaced(self, key: str) -> bool:
        """Check if we've already surfaced this alert category."""
        return key in self._surfaced_alerts

    def get_greeting_context(self, alerts: List[ProactiveAlert]) -> str:
        """Build a context string to inject into Aria's greeting.

        Called during on_enter to make the greeting proactive.
        """
        if not alerts:
            return ""

        critical = [a for a in alerts if a.priority == PRIORITY_CRITICAL]
        high = [a for a in alerts if a.priority == PRIORITY_HIGH]

        parts = []
        if critical:
            parts.append("URGENT ITEMS TO MENTION FIRST:")
            for a in critical:
                parts.append(f"- {a.spoken_text}")
        if high:
            parts.append("IMPORTANT ITEMS TO MENTION SOON:")
            for a in high[:3]:
                parts.append(f"- {a.spoken_text}")

        return "\n".join(parts)
