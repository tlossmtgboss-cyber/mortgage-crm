"""
aria/core/voice_workflows.py
Perennia AI — Voice-Driven Workflow Engine

End-to-end workflows triggered entirely by voice commands.
Each workflow orchestrates multiple backend calls into a single
conversational response that Aria speaks back to the LO.

All CRM access goes through the HTTP backend client — this module
never imports from db, database.models, or services directly.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from agents.aria_backend_client import call_backend_tool_safe

logger = logging.getLogger("aria.voice_workflows")


class VoiceWorkflowEngine:
    """End-to-end workflows triggered entirely by voice commands."""

    def __init__(self, session_data: Dict[str, Any]):
        self._session_data = session_data
        self._org_id = session_data.get("organization_id")
        self._user_id = session_data.get("user_id")

    def _inject_context(self, payload: dict) -> dict:
        """Inject organization_id and user_id into every backend call."""
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

    # ─── Morning Briefing ────────────────────────────────────────────

    async def handle_morning_briefing(self) -> str:
        """'Hey Aria, give me my morning briefing'
        Pipeline status, today's appointments, urgent tasks, rate changes.
        Returns a spoken summary suitable for TTS."""
        pipeline = await self._execute_tool("get_pipeline_metrics", {
            "user_id": str(self._user_id),
        })
        tasks = await self._execute_tool("get_task_queue", {
            "user_id": str(self._user_id),
            "status": "pending",
            "limit": 10,
        })
        # Fetch today's appointments
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        schedule = await self._call_backend("/internal/aria/tool/execute", {
            "tool_name": "get_availability",
            "params": {
                "user_id": str(self._user_id),
                "date": today_str,
            },
        })

        # Build spoken summary
        parts = []

        # Pipeline
        pipe_data = pipeline.get("result", {}).get("data", {}) if isinstance(pipeline.get("result"), dict) else {}
        active = pipe_data.get("active_count", 0)
        volume = pipe_data.get("total_volume")
        if active:
            vol_str = f", about {_format_money(volume)} in volume" if volume else ""
            parts.append(f"You've got {active} active loans in your pipeline{vol_str}.")

        # Tasks
        task_data = tasks.get("result", {}).get("data", {}) if isinstance(tasks.get("result"), dict) else {}
        task_list = task_data.get("tasks", [])
        overdue = [t for t in task_list if t.get("status") == "overdue" or (t.get("due_date") and t["due_date"] < today_str)]
        due_today = [t for t in task_list if t.get("due_date", "").startswith(today_str)]

        if overdue:
            parts.append(f"Heads up, you've got {len(overdue)} overdue task{'s' if len(overdue) != 1 else ''}.")
        if due_today:
            parts.append(f"{len(due_today)} task{'s' if len(due_today) != 1 else ''} due today.")
            if len(due_today) <= 3:
                for t in due_today:
                    parts.append(f"  {t.get('title', 'Untitled task')}.")

        # Schedule
        sched_data = schedule.get("result", {}).get("data", {}) if isinstance(schedule.get("result"), dict) else {}
        appointments = sched_data.get("appointments", [])
        if appointments:
            parts.append(f"You've got {len(appointments)} appointment{'s' if len(appointments) != 1 else ''} today.")
            for apt in appointments[:3]:
                time_str = apt.get("time", apt.get("start", ""))
                title = apt.get("title", "meeting")
                parts.append(f"  {title} at {time_str}.")
        else:
            parts.append("Your calendar's clear today.")

        if not parts:
            return "Looks like a quiet morning. No urgent items, no appointments. You're all caught up."

        return " ".join(parts)

    # ─── Loan Status Check ───────────────────────────────────────────

    async def handle_loan_status_check(self, borrower_name: str) -> str:
        """'Aria, where are we with the Johnson loan?'
        Full status: stage, conditions, next steps, timeline."""
        contact = await self._execute_tool("find_contact_phone", {
            "name": borrower_name,
            "user_id": str(self._user_id),
        })

        contacts = (contact.get("result", {}).get("data", {}).get("contacts", [])
                    if isinstance(contact.get("result"), dict) else [])
        if not contacts:
            return f"I couldn't find anyone named {borrower_name} in the system."

        lead_id = contacts[0].get("id")
        if not lead_id:
            return f"Found {borrower_name} but couldn't get their lead ID."

        loan_status = await self._call_backend(
            "/internal/aria/loan-status",
            {"borrower_id": lead_id},
        )

        if loan_status.get("spoken_summary"):
            return loan_status["spoken_summary"]

        # Build from raw data
        stage = loan_status.get("stage", "unknown")
        amount = loan_status.get("loan_amount")
        parts = [f"The {borrower_name} file is in {stage.replace('_', ' ').lower()}."]
        if amount:
            parts.append(f"Loan amount is {_format_money(amount)}.")

        conditions = loan_status.get("pending_conditions", [])
        if conditions:
            parts.append(f"There are {len(conditions)} pending condition{'s' if len(conditions) != 1 else ''}: {', '.join(conditions[:3])}.")

        next_steps = loan_status.get("next_steps")
        if next_steps:
            parts.append(f"Next step is {next_steps}.")

        return " ".join(parts)

    # ─── Quick Task Create ───────────────────────────────────────────

    async def handle_quick_task_create(
        self, description: str, due_date: Optional[str] = None
    ) -> str:
        """'Aria, remind me to call Sarah Johnson tomorrow at 2pm'
        Creates task, confirms, sets notification."""
        params = {
            "title": description,
            "description": description,
            "priority": "medium",
            "user_id": str(self._user_id),
        }
        if due_date:
            params["due_date"] = due_date

        result = await self._execute_tool("create_task", params)
        if result.get("error"):
            return f"I couldn't create that task. {result.get('spoken_fallback', 'Want me to try again?')}"

        task_data = result.get("result", {}).get("data", {}) if isinstance(result.get("result"), dict) else {}
        task_id = task_data.get("id", "")
        date_conf = f" for {due_date}" if due_date else ""
        return f"Done, task created{date_conf}. I'll make sure you don't forget."

    # ─── Rate Quote ──────────────────────────────────────────────────

    async def handle_rate_quote(
        self,
        fico: Optional[int] = None,
        ltv: Optional[float] = None,
        loan_type: str = "conventional",
        loan_amount: Optional[float] = None,
    ) -> str:
        """'Aria, what's the best rate for a 750 FICO, 80% LTV conventional?'
        Real-time rate lookup with program comparison."""
        params: Dict[str, Any] = {"loan_type": loan_type}
        if fico:
            params["fico"] = fico
        if ltv:
            params["ltv"] = ltv
        if loan_amount:
            params["loan_amount"] = loan_amount

        result = await self._execute_tool("get_rate_quote", params)
        if result.get("error"):
            # Provide a conversational fallback
            parts = ["I don't have live rate data right now."]
            if fico and ltv:
                parts.append(
                    f"For a {fico} FICO at {ltv}% LTV on a {loan_type}, "
                    "you'd want to check the rate sheet. Want me to pull that up?"
                )
            return " ".join(parts)

        rate_data = result.get("result", {}).get("data", {}) if isinstance(result.get("result"), dict) else {}
        rate = rate_data.get("rate")
        apr = rate_data.get("apr")
        if rate:
            parts = [f"Best rate I'm seeing is {rate}%"]
            if apr:
                parts.append(f"with an APR of {apr}%")
            parts.append(f"on a {loan_type}.")
            if fico:
                parts.append(f"That's for a {fico} FICO")
            if ltv:
                parts.append(f"at {ltv}% LTV.")
            return " ".join(parts)

        return "I couldn't get a rate quote right now. Want me to flag this for you?"

    # ─── Document Chase ──────────────────────────────────────────────

    async def handle_document_chase(
        self, borrower_name: str, document_types: Optional[str] = None
    ) -> str:
        """'Aria, chase the Smiths for their bank statements'
        Sends SMS/email to borrower requesting specific docs."""
        contact = await self._execute_tool("find_contact_phone", {
            "name": borrower_name,
            "user_id": str(self._user_id),
        })
        contacts = (contact.get("result", {}).get("data", {}).get("contacts", [])
                    if isinstance(contact.get("result"), dict) else [])
        if not contacts:
            return f"I couldn't find {borrower_name} in the system."

        c = contacts[0]
        phone = c.get("phone")
        name = c.get("name", borrower_name)
        first_name = name.split()[0] if name else borrower_name

        doc_desc = document_types or "the outstanding documents"
        message = (
            f"Hi {first_name}, just following up on your loan file. "
            f"We still need {doc_desc}. "
            f"You can upload them through your portal or reply to this text if you have questions."
        )

        if phone:
            sms_result = await self._execute_tool("send_sms_message", {
                "to_phone": phone,
                "message": message,
                "user_id": str(self._user_id),
            })
            if not sms_result.get("error"):
                return f"Done, I texted {first_name} about {doc_desc}. They should have it now."
            return f"The text to {first_name} didn't go through. Want me to try email instead?"

        # Try email if no phone
        email = c.get("email")
        if email:
            email_result = await self._execute_tool("send_email", {
                "to_email": email,
                "subject": f"Documents Needed — {name}",
                "body": message,
                "user_id": str(self._user_id),
            })
            if not email_result.get("error"):
                return f"No phone on file, so I emailed {first_name} about {doc_desc}."

        return f"I couldn't reach {first_name} — no phone or email on file."

    # ─── End of Day Recap ────────────────────────────────────────────

    async def handle_end_of_day_recap(self) -> str:
        """'Aria, how did today go?'
        Tasks completed, calls made, leads contacted, tomorrow's priorities."""
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        tomorrow_str = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")

        # Get completed tasks today
        completed = await self._execute_tool("get_task_queue", {
            "user_id": str(self._user_id),
            "status": "completed",
            "limit": 50,
        })
        # Get tomorrow's tasks
        upcoming = await self._execute_tool("get_task_queue", {
            "user_id": str(self._user_id),
            "status": "pending",
            "limit": 10,
        })

        parts = ["Here's how today went."]

        completed_data = completed.get("result", {}).get("data", {}) if isinstance(completed.get("result"), dict) else {}
        completed_tasks = completed_data.get("tasks", [])
        today_completed = [t for t in completed_tasks if t.get("completed_at", "").startswith(today_str)]

        if today_completed:
            parts.append(f"You knocked out {len(today_completed)} task{'s' if len(today_completed) != 1 else ''}.")
        else:
            parts.append("No tasks marked complete today.")

        upcoming_data = upcoming.get("result", {}).get("data", {}) if isinstance(upcoming.get("result"), dict) else {}
        upcoming_tasks = upcoming_data.get("tasks", [])
        tomorrow_tasks = [t for t in upcoming_tasks if t.get("due_date", "").startswith(tomorrow_str)]

        if tomorrow_tasks:
            parts.append(f"For tomorrow, you've got {len(tomorrow_tasks)} thing{'s' if len(tomorrow_tasks) != 1 else ''} on deck.")
            for t in tomorrow_tasks[:3]:
                parts.append(f"  {t.get('title', 'Task')}.")
        else:
            parts.append("Nothing scheduled for tomorrow yet.")

        return " ".join(parts)

    # ─── Compliance Check ────────────────────────────────────────────

    async def handle_compliance_check(
        self, borrower_name: Optional[str] = None, loan_id: Optional[int] = None
    ) -> str:
        """'Aria, are we compliant on the Williams file?'
        TRID deadlines, disclosure status, SLA tracking."""
        if borrower_name:
            contact = await self._execute_tool("find_contact_phone", {
                "name": borrower_name,
                "user_id": str(self._user_id),
            })
            contacts = (contact.get("result", {}).get("data", {}).get("contacts", [])
                        if isinstance(contact.get("result"), dict) else [])
            if not contacts:
                return f"I couldn't find {borrower_name} in the system."
            lead_id = contacts[0].get("id")
        else:
            lead_id = loan_id

        if not lead_id:
            return "I need a borrower name or loan ID to check compliance."

        loan_info = await self._call_backend("/internal/aria/loan-info", {
            "lead_id": int(lead_id),
        })

        if loan_info.get("error"):
            return f"I couldn't pull the loan details for that file."

        parts = []
        stage = loan_info.get("stage", "")
        borrower = loan_info.get("borrower_name", borrower_name or "this borrower")
        parts.append(f"The {borrower} file is in {stage.replace('_', ' ').lower()}.")

        # Check for SLA/compliance data
        sla = loan_info.get("sla_status")
        if sla:
            parts.append(f"SLA status: {sla}.")

        disclosure = loan_info.get("disclosure_status")
        if disclosure:
            parts.append(f"Disclosures: {disclosure}.")

        lock_exp = loan_info.get("lock_expiration_date")
        if lock_exp:
            parts.append(f"Rate lock expires {lock_exp}.")

        if len(parts) == 1:
            parts.append("I don't see any compliance flags on this file right now. Looks clean.")

        return " ".join(parts)

    # ─── Pipeline Overview ───────────────────────────────────────────

    async def handle_pipeline_overview(self) -> str:
        """'Aria, give me my pipeline'
        Active loans by stage, projected closings, at-risk files."""
        pipeline = await self._execute_tool("get_pipeline_metrics", {
            "user_id": str(self._user_id),
        })

        pipe_data = pipeline.get("result", {}).get("data", {}) if isinstance(pipeline.get("result"), dict) else {}
        if not pipe_data or pipeline.get("error"):
            return "I'm having trouble pulling your pipeline right now. Want me to try again?"

        active = pipe_data.get("active_count", 0)
        volume = pipe_data.get("total_volume")
        by_stage = pipe_data.get("by_stage", {})

        parts = [f"You've got {active} active loan{'s' if active != 1 else ''} in the pipeline"]
        if volume:
            parts[0] += f", {_format_money(volume)} total volume."
        else:
            parts[0] += "."

        if by_stage:
            stage_parts = []
            for stage, count in sorted(by_stage.items(), key=lambda x: x[1], reverse=True):
                stage_parts.append(f"{count} in {stage.replace('_', ' ').lower()}")
            parts.append("Breakdown: " + ", ".join(stage_parts[:5]) + ".")

        funded = pipe_data.get("funded_this_month", 0)
        if funded:
            parts.append(f"You've funded {funded} this month.")

        return " ".join(parts)

    # ─── Lead Qualification ──────────────────────────────────────────

    async def handle_lead_qualification(
        self,
        credit_score: Optional[int] = None,
        loan_amount: Optional[float] = None,
        property_state: Optional[str] = None,
        loan_type: Optional[str] = None,
        source: Optional[str] = None,
    ) -> str:
        """'Aria, I just got a lead from Zillow — 720 score, looking at 500K in Austin'
        Instant qualification, program eligibility, rate options."""
        parts = ["Let me run through the quick numbers."]

        if credit_score:
            if credit_score >= 740:
                parts.append(f"A {credit_score} score is excellent. They'll qualify for the best rates.")
            elif credit_score >= 680:
                parts.append(f"A {credit_score} score is solid. Good rates across the board.")
            elif credit_score >= 620:
                parts.append(f"A {credit_score} score qualifies for conventional and FHA.")
            elif credit_score >= 580:
                parts.append(f"A {credit_score} score limits them to FHA with 3.5% down.")
            else:
                parts.append(f"A {credit_score} score is below FHA minimums. They may need a non-QM program or credit repair.")

        if loan_amount:
            conforming_limit = 766550  # 2024 conforming limit
            if loan_amount > conforming_limit:
                parts.append(f"At {_format_money(loan_amount)}, that's a jumbo loan. Higher credit requirements apply.")
            else:
                parts.append(f"At {_format_money(loan_amount)}, that's within conforming limits.")

        if source:
            parts.append(f"Lead source is {source}.")
            if source.lower() in ("zillow", "realtor.com", "redfin"):
                parts.append("Online portal leads typically convert best with a call within 5 minutes.")

        parts.append("Want me to create the lead and start the file?")

        return " ".join(parts)

    # ─── Coaching Moment ─────────────────────────────────────────────

    async def handle_coaching_moment(self, topic: str) -> str:
        """'Aria, how should I handle a rate objection?'
        Sales coaching with mortgage-specific objection handling."""
        coaching_tips = {
            "rate objection": (
                "Here's what works. Don't lead with rate, lead with total cost. "
                "Show them the monthly payment difference between your rate and the competitor's. "
                "Usually it's twenty or thirty bucks. Then ask if they'd switch their whole loan "
                "process for thirty dollars a month. Most won't."
            ),
            "closing cost": (
                "When they push back on closing costs, break it down. "
                "Show the lender credits versus seller credits versus rolling into the loan. "
                "Give them options, not just a number."
            ),
            "follow up": (
                "The magic number is five to seven touches. Most LOs give up after two. "
                "Mix your channels: call, text, email, then call again. "
                "Each touch should add value, not just say 'checking in.' "
                "Share a rate update, a market insight, or a relevant article."
            ),
            "pre-approval": (
                "Get the pre-approval out fast. Within 24 hours of first contact. "
                "A borrower with a pre-approval letter in hand is three times more likely to convert. "
                "Make it easy: send them the portal link, walk them through it on the phone."
            ),
            "referral": (
                "Best referral strategy: do great work and ask at closing. "
                "Say something like 'If you know anyone buying or refinancing, I'd love to help them too.' "
                "Simple, no pressure. Then follow up with a thank-you card."
            ),
        }

        topic_lower = topic.lower()
        for key, tip in coaching_tips.items():
            if key in topic_lower:
                return tip

        # Generic coaching response
        return (
            f"Good question about {topic}. The key is to always lead with value, "
            "not features. Listen first, understand their situation, then position "
            "your recommendation as the solution to their specific problem. "
            "Want me to dig deeper on a specific angle?"
        )

    # ─── Schedule Callback ───────────────────────────────────────────

    async def handle_schedule_callback(
        self, contact_name: str, time: str, reason: Optional[str] = None
    ) -> str:
        """'Aria, schedule a callback with Sarah at 3pm tomorrow'
        Looks up contact, books appointment, sends confirmation."""
        contact = await self._execute_tool("find_contact_phone", {
            "name": contact_name,
            "user_id": str(self._user_id),
        })
        contacts = (contact.get("result", {}).get("data", {}).get("contacts", [])
                    if isinstance(contact.get("result"), dict) else [])
        if not contacts:
            return f"I couldn't find {contact_name} in the system. Can you spell that for me?"

        c = contacts[0]
        contact_id = c.get("id", "")

        result = await self._execute_tool("book_appointment", {
            "user_id": str(self._user_id),
            "contact_id": str(contact_id),
            "datetime_str": time,
            "duration_minutes": 30,
            "appointment_type": "callback",
            "title": f"Callback — {contact_name}" + (f" — {reason}" if reason else ""),
            "notes": reason or f"Scheduled callback with {contact_name}",
        })

        if result.get("error"):
            return f"I couldn't book that callback. {result.get('spoken_fallback', 'Want me to try again?')}"

        return f"All set, callback with {contact_name} scheduled for {time}. I'll remind you beforehand."


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _format_money(amount) -> str:
    """Format a dollar amount for spoken delivery."""
    if amount is None:
        return "$0"
    try:
        amt = float(amount)
        if amt >= 1_000_000:
            return f"${amt / 1_000_000:.1f} million"
        if amt >= 1_000:
            return f"${amt / 1_000:.0f}K"
        return f"${amt:,.0f}"
    except (ValueError, TypeError):
        return str(amount)
