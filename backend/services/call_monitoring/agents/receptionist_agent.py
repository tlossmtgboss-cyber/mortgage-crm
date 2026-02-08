"""
Call Scheduling Agent (formerly Receptionist Agent) - Calendar & Scheduling

AI agent that listens to calls and handles scheduling:
- Detects when appointments are agreed upon
- Creates calendar appointments
- Sends calendar invites
- Schedules follow-up calls
- Coordinates schedules between parties

Works with the Production Assistant to manage the LO's calendar.

Note: Renamed from ReceptionistAgent to avoid collision with the
specialized ReceptionistAgent (interactive voice/chat handler).
This agent does passive post-call analysis; the specialized one
handles real-time interactions.
"""

import logging
from typing import Dict, List, Any
import json
from datetime import datetime, timedelta

from .base_agent import BaseCallAgent, AgentResult

logger = logging.getLogger(__name__)


class CallSchedulingAgent(BaseCallAgent):
    """
    Call Scheduling Agent for calendar management and scheduling.

    Capabilities:
    - Detects when parties agree on a meeting time
    - Extracts appointment details (date, time, participants, purpose)
    - Creates calendar appointments for the LO
    - Schedules follow-up calls
    - Coordinates with Production Assistant
    - Sends calendar invites to all parties

    Knows all the transaction participants so it can:
    - Include the right people on invites
    - Schedule calls with specific team members
    - Understand who is being referenced
    """

    @property
    def agent_type(self) -> str:
        return "receptionist"

    @property
    def system_prompt(self) -> str:
        return """You are an expert AI receptionist and scheduling coordinator for a mortgage loan officer. You listen to calls and handle all calendar and scheduling tasks.

## YOUR RESPONSIBILITIES:

1. **Detect Scheduling Agreements**
   - When the LO and borrower agree on a time to talk again
   - When appointments are scheduled (application calls, document review, etc.)
   - When meetings are set up with other parties

2. **Extract Complete Details**
   - Exact date and time (or relative like "tomorrow at 2pm")
   - Who should attend
   - Purpose of the meeting
   - How long it should be
   - Whether it's a call, video meeting, or in-person

3. **Coordinate Participants**
   You'll know everyone involved in the transaction:
   - Loan Officer (LO) - Primary calendar owner
   - Production Assistant (PA) - May need to attend or be notified
   - Borrower(s) - Main participants
   - Real estate agents - Sometimes need to join
   - Other parties as relevant

4. **Handle Follow-Up Scheduling**
   - "Let's talk next week" → Schedule follow-up
   - "I'll call you after you get the documents" → Create reminder
   - "Can we set up a time for the application?" → Schedule application call

## SCHEDULING PATTERNS TO RECOGNIZE:

**Explicit Agreements:**
- "Let's schedule that for Tuesday at 3"
- "How about we meet on Friday morning?"
- "I can do 10am tomorrow"
- "Put me down for next Wednesday at 2pm"

**Implicit Agreements:**
- "Tuesday works" (after time was proposed)
- "That time is perfect"
- "See you then"
- "I'll block that off"

**Follow-Up Triggers:**
- "Let's talk again once you have those documents"
- "I'll call you next week to check in"
- "We should schedule an application call"
- "Let's set up a time to review the numbers"

## TRANSACTION TEAM CONTEXT:

You'll receive information about everyone involved:
- Their names and roles
- Contact information
- Who needs to be on which meetings

Use this to:
- Know who "my assistant" or "the agent" refers to
- Include the right people on invites
- Route scheduling to the PA when appropriate

## OUTPUT FORMAT:

```json
{
    "appointments_detected": [
        {
            "appointment_type": "follow_up_call/application_call/document_review/pre_approval_call/closing_prep/general_meeting",
            "title": "Brief descriptive title",
            "description": "What will be discussed",
            "proposed_datetime": "2024-01-15T14:00:00 or relative like 'tomorrow at 2pm'",
            "duration_minutes": 30,
            "participants": [
                {
                    "role": "loan_officer/borrower/co_borrower/realtor/pa/etc",
                    "name": "Name if mentioned",
                    "required": true
                }
            ],
            "meeting_type": "phone/video/in_person",
            "confirmation_status": "confirmed/tentative/needs_confirmation",
            "who_will_send_invite": "LO/PA/receptionist_agent",
            "notes": "Any additional context"
        }
    ],
    "follow_up_reminders": [
        {
            "trigger": "What should trigger this follow-up",
            "action": "What call/meeting to schedule",
            "suggested_timing": "When to follow up",
            "participants": ["Who should be involved"]
        }
    ],
    "calendar_actions": [
        {
            "action_type": "create_event/send_invite/block_time/cancel_event",
            "details": "Specific details for this action",
            "priority": "high/medium/low",
            "assign_to": "LO/PA/auto"
        }
    ],
    "scheduling_summary": "Brief summary of what was scheduled or needs scheduling"
}
```

## IMPORTANT GUIDELINES:

1. **Be Precise**: Get exact times when possible
2. **Default Duration**: 30 minutes for calls, 60 minutes for meetings
3. **Time Zone Awareness**: Note if time zone is mentioned
4. **Don't Over-Schedule**: Only create appointments for clear agreements
5. **PA Coordination**: Flag things the PA should handle
6. **Confirm Ambiguity**: Note when details need confirmation"""

    def build_user_prompt(self, context: Dict[str, Any]) -> str:
        transcript = context.get('transcript', '')
        transcript = self._truncate_transcript(transcript, max_words=5000)

        participants = self._format_participants(context.get('participants', []))
        transaction_team = self._format_transaction_team(context.get('transaction_team', {}))
        loan_context = self._format_loan_context(context.get('loan'))

        # Get current date/time context
        now = datetime.now()
        date_context = f"""
## Current Date/Time Context:
- Today is: {now.strftime('%A, %B %d, %Y')}
- Current time: {now.strftime('%I:%M %p')}
- Tomorrow is: {(now + timedelta(days=1)).strftime('%A, %B %d')}
- Next week starts: {(now + timedelta(days=(7-now.weekday()))).strftime('%A, %B %d')}"""

        # Check for existing appointments
        upcoming = context.get('upcoming_appointments', [])
        upcoming_context = ""
        if upcoming:
            upcoming_context = "\n## Existing Upcoming Appointments:\n"
            for apt in upcoming[:5]:
                upcoming_context += f"- {apt.get('date')}: {apt.get('title')}\n"

        prompt = f"""Listen to this call and identify any scheduling needs or appointments that were agreed upon.

## Call Participants
{participants}

## Full Transaction Team (So You Know Who's Who)
{transaction_team}

## Loan Context
{loan_context if context.get('loan') else 'New inquiry - no active loan file'}
{date_context}
{upcoming_context}

## Call Transcript
{transcript}

---

As you analyze this call:
1. Listen for any agreed-upon meeting times or appointments
2. Identify follow-up calls that need to be scheduled
3. Note who should be included on each appointment
4. Determine if the PA should handle the scheduling
5. Flag any calendar conflicts or coordination needed

When you hear references like "my assistant," "the realtor," or "your agent," use the transaction team context to identify who they mean.

Provide your analysis in the JSON format. Only create appointments for clear agreements - don't schedule speculatively."""

        return prompt

    def _format_transaction_team(self, team: Dict[str, Any]) -> str:
        """Format transaction team members for context."""
        if not team:
            return "Transaction team details not provided"

        lines = []

        # Loan Officer
        if team.get('loan_officer'):
            lo = team['loan_officer']
            lines.append(f"**Loan Officer (LO):** {lo.get('name', 'Unknown')}")
            if lo.get('email'):
                lines.append(f"  - Email: {lo['email']}")
            if lo.get('phone'):
                lines.append(f"  - Phone: {lo['phone']}")
            if lo.get('calendar_link'):
                lines.append(f"  - Has calendar booking link")

        # Production Assistant
        if team.get('production_assistant'):
            pa = team['production_assistant']
            lines.append(f"**Production Assistant (PA):** {pa.get('name', 'Unknown')}")
            if pa.get('email'):
                lines.append(f"  - Email: {pa['email']}")
            lines.append("  - Handles: Scheduling, follow-ups, document requests")

        # Processor
        if team.get('processor'):
            proc = team['processor']
            lines.append(f"**Processor:** {proc.get('name', 'Unknown')}")
            if proc.get('email'):
                lines.append(f"  - Email: {proc['email']}")

        # Borrower(s)
        if team.get('borrowers'):
            for i, borrower in enumerate(team['borrowers'], 1):
                label = "Primary Borrower" if i == 1 else f"Co-Borrower"
                lines.append(f"**{label}:** {borrower.get('name', 'Unknown')}")
                if borrower.get('email'):
                    lines.append(f"  - Email: {borrower['email']}")
                if borrower.get('phone'):
                    lines.append(f"  - Phone: {borrower['phone']}")
                if borrower.get('preferred_contact_time'):
                    lines.append(f"  - Preferred time: {borrower['preferred_contact_time']}")

        # Real Estate Agent(s)
        if team.get('buyer_agent'):
            agent = team['buyer_agent']
            lines.append(f"**Buyer's Realtor:** {agent.get('name', 'Unknown')}")
            if agent.get('email'):
                lines.append(f"  - Email: {agent['email']}")
            if agent.get('phone'):
                lines.append(f"  - Phone: {agent['phone']}")

        if team.get('listing_agent'):
            agent = team['listing_agent']
            lines.append(f"**Listing Agent:** {agent.get('name', 'Unknown')}")

        # Other parties
        if team.get('title_company'):
            tc = team['title_company']
            lines.append(f"**Title Company:** {tc.get('name', 'Unknown')}")
            if tc.get('contact_name'):
                lines.append(f"  - Contact: {tc['contact_name']}")

        if team.get('insurance_agent'):
            ia = team['insurance_agent']
            lines.append(f"**Insurance Agent:** {ia.get('name', 'Unknown')}")

        return "\n".join(lines) if lines else "Transaction team not yet defined"

    def parse_response(self, response_text: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse Receptionist agent response into artifacts."""
        artifacts = []

        parsed = self._extract_json_from_response(response_text)

        if not parsed:
            logger.warning("Receptionist agent: Could not parse JSON response")
            return artifacts

        # Create appointment artifacts
        for apt in parsed.get('appointments_detected', []):
            if not apt.get('title'):
                continue

            # Determine if this is confirmed or needs confirmation
            needs_confirmation = apt.get('confirmation_status') != 'confirmed'

            artifact = {
                'type': 'scheduled_appointment',
                'title': apt.get('title', 'Appointment'),
                'content': apt.get('description', ''),
                'structured_data': {
                    'appointment_type': apt.get('appointment_type'),
                    'proposed_datetime': apt.get('proposed_datetime'),
                    'duration_minutes': apt.get('duration_minutes', 30),
                    'participants': apt.get('participants', []),
                    'meeting_type': apt.get('meeting_type', 'phone'),
                    'confirmation_status': apt.get('confirmation_status'),
                    'who_will_send_invite': apt.get('who_will_send_invite', 'PA'),
                    'notes': apt.get('notes'),
                    'needs_calendar_event': True,
                },
                'priority': 'high' if not needs_confirmation else 'medium',
                'confidence': 0.90 if not needs_confirmation else 0.75,
            }
            artifacts.append(artifact)

        # Create follow-up call artifacts
        for followup in parsed.get('follow_up_reminders', []):
            artifact = {
                'type': 'follow_up_call',
                'title': f"Follow-Up: {followup.get('action', 'Call')}",
                'content': followup.get('trigger', ''),
                'structured_data': {
                    'trigger': followup.get('trigger'),
                    'action': followup.get('action'),
                    'suggested_timing': followup.get('suggested_timing'),
                    'participants': followup.get('participants', []),
                },
                'priority': 'medium',
                'confidence': 0.80,
            }
            artifacts.append(artifact)

        # Create calendar action artifacts
        for action in parsed.get('calendar_actions', []):
            artifact = {
                'type': 'calendar_action',
                'title': f"Calendar: {action.get('action_type', 'Action').replace('_', ' ').title()}",
                'content': action.get('details', ''),
                'structured_data': {
                    'action_type': action.get('action_type'),
                    'details': action.get('details'),
                    'assign_to': action.get('assign_to', 'PA'),
                },
                'priority': action.get('priority', 'medium'),
                'confidence': 0.85,
            }
            artifacts.append(artifact)

        # Create a meeting summary artifact if appointments were detected
        if parsed.get('scheduling_summary') and parsed.get('appointments_detected'):
            summary_artifact = {
                'type': 'meeting_summary',
                'title': 'Scheduling Summary',
                'content': parsed.get('scheduling_summary', ''),
                'structured_data': {
                    'appointments_count': len(parsed.get('appointments_detected', [])),
                    'follow_ups_count': len(parsed.get('follow_up_reminders', [])),
                    'summary': parsed.get('scheduling_summary'),
                },
                'confidence': 0.85,
            }
            artifacts.append(summary_artifact)

        # Create stacked note for chronological view
        appointments = parsed.get('appointments_detected', [])
        if appointments:
            note_lines = ["**Scheduling Notes:**"]
            for apt in appointments:
                status = "CONFIRMED" if apt.get('confirmation_status') == 'confirmed' else "TENTATIVE"
                note_lines.append(f"• [{status}] {apt.get('title', 'Appointment')}")
                if apt.get('proposed_datetime'):
                    note_lines.append(f"  Time: {apt['proposed_datetime']}")

            stacked_note = {
                'type': 'stacked_note',
                'title': f"Receptionist Notes - {len(appointments)} Appointment(s)",
                'content': '\n'.join(note_lines),
                'structured_data': {
                    'source': 'receptionist',
                    'key_points': [apt.get('title', '') for apt in appointments],
                    'appointments_scheduled': len(appointments),
                },
                'confidence': 0.85,
            }
            artifacts.append(stacked_note)

        # Create task for PA if needed
        pa_actions = [a for a in parsed.get('calendar_actions', []) if a.get('assign_to') == 'PA']
        if pa_actions or any(apt.get('who_will_send_invite') == 'PA' for apt in appointments):
            task_content = "Calendar actions needed:\n"
            for apt in appointments:
                if apt.get('who_will_send_invite') == 'PA':
                    task_content += f"• Send invite for: {apt.get('title')}\n"
            for action in pa_actions:
                task_content += f"• {action.get('details', action.get('action_type', ''))}\n"

            pa_task = {
                'type': 'task',
                'title': 'PA: Calendar Actions Needed',
                'content': task_content,
                'structured_data': {
                    'priority': 'high',
                    'owner_role': 'production_assistant',
                    'source': 'receptionist_agent',
                    'task_type': 'scheduling',
                },
                'priority': 'high',
                'confidence': 0.90,
            }
            artifacts.append(pa_task)

        return artifacts
