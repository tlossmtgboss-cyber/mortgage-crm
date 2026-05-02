"""
Automated Call Summary Service

Generates AI-powered call summaries that are:
- Executive-ready with key takeaways
- Action-oriented with clear next steps
- Searchable and filterable
- Auto-generated on call completion

Features:
- One-click summary for any recorded call
- Batch summary generation for unprocessed calls
- Executive summary format for managers
- CRM integration with lead/loan updates
- Follow-up task auto-creation
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from enum import Enum

import anthropic
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

SUMMARY_MODEL = "claude-sonnet-4-6"


class SummaryType(str, Enum):
    """Types of summaries we can generate."""
    QUICK = "quick"           # 30-second read, 3-5 bullets
    STANDARD = "standard"     # 2-minute read, full analysis
    EXECUTIVE = "executive"   # Manager-focused, metrics + outcomes
    COACHING = "coaching"     # Training-focused with improvement areas


@dataclass
class FollowUpTask:
    """A follow-up task extracted from the call."""
    title: str
    description: str
    priority: str  # critical, high, medium, low
    assigned_to: str  # agent, manager, processor, underwriter
    due_within_days: int = 1
    related_to: Optional[str] = None  # lead_id, loan_id, etc.
    category: str = "general"  # document_request, callback, application_update, etc.


@dataclass
class CallInsight:
    """A key insight from the call."""
    category: str  # customer_need, objection, opportunity, risk, progress
    headline: str
    detail: str
    importance: str  # high, medium, low
    actionable: bool = False


@dataclass
class CallSummary:
    """Complete call summary."""
    # Core summary
    recording_id: str
    summary_type: str
    one_liner: str
    executive_summary: str
    key_points: List[str]

    # Call context
    call_duration_seconds: int = 0
    call_direction: str = ""  # inbound, outbound
    call_outcome: str = ""  # successful, callback_needed, escalation, no_answer

    # Customer insights
    customer_name: Optional[str] = None
    customer_sentiment: str = "neutral"
    customer_stage: str = ""  # shopping, applied, in_process, closing
    customer_urgency: str = "normal"  # urgent, normal, low

    # Key insights
    insights: List[CallInsight] = field(default_factory=list)
    objections_raised: List[Dict[str, str]] = field(default_factory=list)
    questions_asked: List[str] = field(default_factory=list)

    # Actions
    follow_up_tasks: List[FollowUpTask] = field(default_factory=list)
    immediate_actions: List[str] = field(default_factory=list)
    next_contact_date: Optional[str] = None

    # Metrics
    talk_time_agent_pct: float = 0.0
    talk_time_customer_pct: float = 0.0
    hold_time_seconds: int = 0

    # Loan/Lead context if available
    loan_id: Optional[int] = None
    lead_id: Optional[int] = None
    loan_status_update: Optional[str] = None

    # Metadata
    generated_at: str = ""
    model_used: str = SUMMARY_MODEL
    tokens_used: int = 0

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["insights"] = [asdict(i) for i in self.insights]
        result["follow_up_tasks"] = [asdict(t) for t in self.follow_up_tasks]
        return result


class CallSummaryService:
    """
    Service for generating automated call summaries.

    Usage:
        service = CallSummaryService(db)
        summary = await service.generate_summary(recording_id)
        await service.process_pending_summaries()  # Batch process
    """

    def __init__(self, db: Session):
        self.db = db
        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        self.client = anthropic.Anthropic(api_key=self.api_key) if self.api_key else None

    async def generate_summary(
        self,
        recording_id: str,
        summary_type: SummaryType = SummaryType.STANDARD,
        auto_create_tasks: bool = True
    ) -> CallSummary:
        """
        Generate a summary for a call recording.

        Args:
            recording_id: The call recording ID
            summary_type: Type of summary to generate
            auto_create_tasks: Whether to auto-create follow-up tasks

        Returns:
            CallSummary object
        """
        if not self.client:
            raise ValueError("ANTHROPIC_API_KEY not configured")

        # Get recording and transcription
        recording = self._get_recording(recording_id)
        if not recording:
            raise ValueError(f"Recording {recording_id} not found")

        transcript = self._get_transcript(recording_id)
        if not transcript:
            raise ValueError(f"No transcript found for recording {recording_id}")

        # Get context (lead/loan info)
        context = self._get_context(recording)

        # Build prompt based on summary type
        prompt = self._build_summary_prompt(transcript, summary_type, context, recording)

        # Call Claude
        try:
            response = self.client.messages.create(
                model=SUMMARY_MODEL,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
                system=self._get_system_prompt(summary_type)
            )

            # Parse response
            summary = self._parse_summary_response(
                response.content[0].text,
                recording_id,
                recording,
                summary_type
            )
            summary.tokens_used = response.usage.input_tokens + response.usage.output_tokens

            # Save summary to database
            self._save_summary(summary)

            # Create follow-up tasks if enabled
            if auto_create_tasks and summary.follow_up_tasks:
                self._create_follow_up_tasks(summary, recording)

            return summary

        except Exception as e:
            logger.error(f"Summary generation failed: {e}")
            raise

    async def process_pending_summaries(self, limit: int = 50) -> Dict[str, Any]:
        """
        Process all recordings that don't have summaries yet.

        Returns count of processed and any errors.
        """
        # Find recordings with transcripts but no summaries
        result = self.db.execute(text("""
            SELECT r.id
            FROM ci_call_recordings r
            INNER JOIN ci_call_transcriptions t ON t.recording_id = r.id
            LEFT JOIN ci_call_summaries s ON s.recording_id = r.id
            WHERE t.status = 'completed'
              AND s.id IS NULL
              AND r.status IN ('transcribed', 'analyzed', 'completed')
            ORDER BY r.created_at DESC
            LIMIT :limit
        """), {"limit": limit})

        pending_ids = [row[0] for row in result.fetchall()]

        processed = 0
        errors = []

        for recording_id in pending_ids:
            try:
                await self.generate_summary(recording_id)
                processed += 1
            except Exception as e:
                errors.append({"recording_id": recording_id, "error": "Internal server error"})
                logger.error(f"Failed to generate summary for {recording_id}: {e}")

        return {
            "total_pending": len(pending_ids),
            "processed": processed,
            "errors": errors
        }

    def get_summary(self, recording_id: str) -> Optional[CallSummary]:
        """Get existing summary for a recording."""
        result = self.db.execute(text("""
            SELECT id, recording_id, summary_type, one_liner, executive_summary,
                   key_points, call_outcome, customer_sentiment, customer_stage,
                   customer_urgency, insights, follow_up_tasks, immediate_actions,
                   next_contact_date, talk_time_agent_pct, talk_time_customer_pct,
                   loan_id, lead_id, generated_at, tokens_used
            FROM ci_call_summaries
            WHERE recording_id = :recording_id
            ORDER BY generated_at DESC
            LIMIT 1
        """), {"recording_id": recording_id})

        row = result.fetchone()
        if not row:
            return None

        return CallSummary(
            recording_id=str(row[1]),
            summary_type=row[2],
            one_liner=row[3] or "",
            executive_summary=row[4] or "",
            key_points=json.loads(row[5]) if row[5] else [],
            call_outcome=row[6] or "",
            customer_sentiment=row[7] or "neutral",
            customer_stage=row[8] or "",
            customer_urgency=row[9] or "normal",
            insights=[CallInsight(**i) for i in json.loads(row[10])] if row[10] else [],
            follow_up_tasks=[FollowUpTask(**t) for t in json.loads(row[11])] if row[11] else [],
            immediate_actions=json.loads(row[12]) if row[12] else [],
            next_contact_date=row[13],
            talk_time_agent_pct=float(row[14]) if row[14] else 0,
            talk_time_customer_pct=float(row[15]) if row[15] else 0,
            loan_id=row[16],
            lead_id=row[17],
            generated_at=str(row[18]) if row[18] else "",
            tokens_used=row[19] or 0
        )

    def get_recent_summaries(
        self,
        agent_id: Optional[int] = None,
        days: int = 7,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get recent call summaries."""
        params = {"days": days, "limit": limit}
        agent_filter = ""

        if agent_id:
            agent_filter = "AND r.agent_user_id = :agent_id"
            params["agent_id"] = agent_id

        sql = """
            SELECT s.id, s.recording_id, s.one_liner, s.call_outcome,
                   s.customer_sentiment, s.generated_at,
                   r.agent_user_id, r.duration_seconds, r.direction,
                   u.full_name as agent_name
            FROM ci_call_summaries s
            JOIN ci_call_recordings r ON r.id = s.recording_id
            LEFT JOIN users u ON u.id = r.agent_user_id
            WHERE s.generated_at >= CURRENT_DATE - :days
        """
        if agent_filter:
            sql += "            " + agent_filter + "\n"
        sql += """            ORDER BY s.generated_at DESC
            LIMIT :limit
        """
        result = self.db.execute(text(sql), params)

        summaries = []
        for row in result.fetchall():
            summaries.append({
                "id": str(row[0]),
                "recording_id": str(row[1]),
                "one_liner": row[2],
                "call_outcome": row[3],
                "customer_sentiment": row[4],
                "generated_at": str(row[5]) if row[5] else None,
                "agent_id": row[6],
                "duration_seconds": row[7],
                "direction": row[8],
                "agent_name": row[9]
            })

        return summaries

    def get_summary_stats(
        self,
        agent_id: Optional[int] = None,
        days: int = 30
    ) -> Dict[str, Any]:
        """Get aggregate summary statistics."""
        params = {"days": days}
        agent_filter = ""

        if agent_id:
            agent_filter = "AND r.agent_user_id = :agent_id"
            params["agent_id"] = agent_id

        stats_sql = """
            SELECT
                COUNT(*) as total_calls,
                COUNT(CASE WHEN s.call_outcome = 'successful' THEN 1 END) as successful,
                COUNT(CASE WHEN s.call_outcome = 'callback_needed' THEN 1 END) as callbacks_needed,
                COUNT(CASE WHEN s.customer_sentiment = 'positive' THEN 1 END) as positive_sentiment,
                COUNT(CASE WHEN s.customer_sentiment = 'negative' THEN 1 END) as negative_sentiment,
                AVG(r.duration_seconds) as avg_duration,
                AVG(s.talk_time_agent_pct) as avg_agent_talk_pct
            FROM ci_call_summaries s
            JOIN ci_call_recordings r ON r.id = s.recording_id
            WHERE s.generated_at >= CURRENT_DATE - :days
        """
        if agent_filter:
            stats_sql += "            " + agent_filter + "\n"
        result = self.db.execute(text(stats_sql), params)

        row = result.fetchone()
        if not row or not row[0]:
            return {
                "total_calls": 0,
                "successful_rate": 0,
                "callbacks_needed": 0,
                "positive_sentiment_rate": 0,
                "avg_duration_seconds": 0,
                "avg_agent_talk_pct": 0
            }

        total = row[0]
        return {
            "total_calls": total,
            "successful": row[1] or 0,
            "successful_rate": round((row[1] or 0) / total * 100, 1) if total > 0 else 0,
            "callbacks_needed": row[2] or 0,
            "positive_sentiment_rate": round((row[3] or 0) / total * 100, 1) if total > 0 else 0,
            "negative_sentiment_rate": round((row[4] or 0) / total * 100, 1) if total > 0 else 0,
            "avg_duration_seconds": round(float(row[5] or 0), 0),
            "avg_agent_talk_pct": round(float(row[6] or 0), 1)
        }

    # =========================================================================
    # PRIVATE METHODS
    # =========================================================================

    def _get_recording(self, recording_id: str) -> Optional[Dict[str, Any]]:
        """Get recording details."""
        result = self.db.execute(text("""
            SELECT id, loan_id, lead_id, agent_user_id, direction,
                   duration_seconds, status, phone_from, phone_to,
                   created_at
            FROM ci_call_recordings
            WHERE id = :id
        """), {"id": recording_id})

        row = result.fetchone()
        if not row:
            return None

        return {
            "id": str(row[0]),
            "loan_id": row[1],
            "lead_id": row[2],
            "agent_user_id": row[3],
            "direction": row[4],
            "duration_seconds": row[5] or 0,
            "status": row[6],
            "phone_from": row[7],
            "phone_to": row[8],
            "created_at": row[9]
        }

    def _get_transcript(self, recording_id: str) -> Optional[str]:
        """Get transcript text for a recording."""
        result = self.db.execute(text("""
            SELECT transcript_text
            FROM ci_call_transcriptions
            WHERE recording_id = :recording_id
              AND status = 'completed'
            ORDER BY created_at DESC
            LIMIT 1
        """), {"recording_id": recording_id})

        row = result.fetchone()
        return row[0] if row else None

    def _get_context(self, recording: Dict[str, Any]) -> Dict[str, Any]:
        """Get lead/loan context for the call."""
        context = {}

        # Get lead info
        if recording.get("lead_id"):
            result = self.db.execute(text("""
                SELECT id, first_name, last_name, email, phone, status,
                       loan_purpose, estimated_loan_amount, lead_score
                FROM leads
                WHERE id = :id
            """), {"id": recording["lead_id"]})

            row = result.fetchone()
            if row:
                context["lead"] = {
                    "id": row[0],
                    "name": f"{row[1]} {row[2]}".strip(),
                    "email": row[3],
                    "phone": row[4],
                    "status": row[5],
                    "loan_purpose": row[6],
                    "estimated_amount": float(row[7]) if row[7] else None,
                    "lead_score": row[8]
                }

        # Get loan info
        if recording.get("loan_id"):
            result = self.db.execute(text("""
                SELECT id, loan_number, borrower_name, loan_amount,
                       loan_type, status, stage
                FROM loans
                WHERE id = :id
            """), {"id": recording["loan_id"]})

            row = result.fetchone()
            if row:
                context["loan"] = {
                    "id": row[0],
                    "loan_number": row[1],
                    "borrower": row[2],
                    "amount": float(row[3]) if row[3] else None,
                    "loan_type": row[4],
                    "status": row[5],
                    "stage": row[6]
                }

        return context

    def _get_system_prompt(self, summary_type: SummaryType) -> str:
        """Get system prompt based on summary type."""
        base = """You are an expert mortgage call analyst. Generate concise, actionable call summaries for loan officers and managers.

Key focus areas:
1. What the customer wants/needs
2. Any objections or concerns raised
3. Clear next steps and follow-up actions
4. Customer sentiment and urgency level
5. Opportunities or risks identified

Always respond in valid JSON format."""

        if summary_type == SummaryType.QUICK:
            return base + """

For QUICK summaries:
- Maximum 5 bullet points
- Focus only on the most critical information
- 30-second read maximum"""

        elif summary_type == SummaryType.EXECUTIVE:
            return base + """

For EXECUTIVE summaries:
- Lead with outcomes and metrics
- Highlight any escalation needs
- Focus on pipeline impact
- Include conversion probability"""

        elif summary_type == SummaryType.COACHING:
            return base + """

For COACHING summaries:
- Focus on agent performance
- Identify specific improvement areas
- Note exemplary behaviors to reinforce
- Suggest training topics"""

        return base

    def _build_summary_prompt(
        self,
        transcript: str,
        summary_type: SummaryType,
        context: Dict[str, Any],
        recording: Dict[str, Any]
    ) -> str:
        """Build the summary generation prompt."""
        context_str = ""
        if context.get("lead"):
            lead = context["lead"]
            context_str += f"""
LEAD CONTEXT:
- Name: {lead.get('name')}
- Status: {lead.get('status')}
- Loan Purpose: {lead.get('loan_purpose')}
- Estimated Amount: ${lead.get('estimated_amount', 'Unknown'):,}
"""

        if context.get("loan"):
            loan = context["loan"]
            context_str += f"""
LOAN CONTEXT:
- Loan #: {loan.get('loan_number')}
- Borrower: {loan.get('borrower')}
- Amount: ${loan.get('amount', 0):,}
- Type: {loan.get('loan_type')}
- Stage: {loan.get('stage')}
"""

        prompt = f"""Analyze this mortgage call and generate a {summary_type.value.upper()} summary.

CALL METADATA:
- Direction: {recording.get('direction', 'unknown')}
- Duration: {recording.get('duration_seconds', 0)} seconds
{context_str}

TRANSCRIPT:
{transcript[:8000]}  # Limit transcript length

Generate a JSON response with this structure:
{{
    "one_liner": "Single sentence summary of call outcome",
    "executive_summary": "2-3 paragraph comprehensive summary",
    "key_points": [
        "Key point 1",
        "Key point 2",
        "Key point 3"
    ],
    "call_outcome": "successful | callback_needed | escalation | no_answer | voicemail | transferred",
    "customer_sentiment": "positive | neutral | negative | mixed",
    "customer_stage": "shopping | applied | in_process | closing | post_close | not_ready",
    "customer_urgency": "urgent | normal | low",
    "insights": [
        {{
            "category": "customer_need | objection | opportunity | risk | progress",
            "headline": "Brief headline",
            "detail": "Detailed explanation",
            "importance": "high | medium | low",
            "actionable": true
        }}
    ],
    "objections_raised": [
        {{"objection": "What they said", "response": "How agent responded", "resolved": true}}
    ],
    "questions_asked": ["Customer question 1", "Customer question 2"],
    "follow_up_tasks": [
        {{
            "title": "Task title",
            "description": "What needs to be done",
            "priority": "critical | high | medium | low",
            "assigned_to": "agent | manager | processor | underwriter",
            "due_within_days": 1,
            "category": "document_request | callback | application_update | pricing | other"
        }}
    ],
    "immediate_actions": ["Action 1", "Action 2"],
    "next_contact_date": "YYYY-MM-DD or null",
    "talk_time_agent_pct": 40.5,
    "talk_time_customer_pct": 59.5
}}

Important:
- Be specific and actionable
- Use actual quotes or paraphrases from the call when relevant
- Identify all follow-up tasks with clear ownership
- Flag any compliance or escalation concerns in insights
"""
        return prompt

    def _parse_summary_response(
        self,
        response_text: str,
        recording_id: str,
        recording: Dict[str, Any],
        summary_type: SummaryType
    ) -> CallSummary:
        """Parse Claude's response into CallSummary."""
        try:
            # Extract JSON from response
            json_text = response_text
            if "```json" in response_text:
                json_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                json_text = response_text.split("```")[1].split("```")[0]

            data = json.loads(json_text)

            summary = CallSummary(
                recording_id=recording_id,
                summary_type=summary_type.value,
                one_liner=data.get("one_liner", ""),
                executive_summary=data.get("executive_summary", ""),
                key_points=data.get("key_points", []),
                call_duration_seconds=recording.get("duration_seconds", 0),
                call_direction=recording.get("direction", ""),
                call_outcome=data.get("call_outcome", ""),
                customer_sentiment=data.get("customer_sentiment", "neutral"),
                customer_stage=data.get("customer_stage", ""),
                customer_urgency=data.get("customer_urgency", "normal"),
                objections_raised=data.get("objections_raised", []),
                questions_asked=data.get("questions_asked", []),
                immediate_actions=data.get("immediate_actions", []),
                next_contact_date=data.get("next_contact_date"),
                talk_time_agent_pct=data.get("talk_time_agent_pct", 0),
                talk_time_customer_pct=data.get("talk_time_customer_pct", 0),
                loan_id=recording.get("loan_id"),
                lead_id=recording.get("lead_id"),
                generated_at=datetime.now().isoformat()
            )

            # Parse insights
            for insight in data.get("insights", []):
                summary.insights.append(CallInsight(
                    category=insight.get("category", ""),
                    headline=insight.get("headline", ""),
                    detail=insight.get("detail", ""),
                    importance=insight.get("importance", "medium"),
                    actionable=insight.get("actionable", False)
                ))

            # Parse follow-up tasks
            for task in data.get("follow_up_tasks", []):
                summary.follow_up_tasks.append(FollowUpTask(
                    title=task.get("title", ""),
                    description=task.get("description", ""),
                    priority=task.get("priority", "medium"),
                    assigned_to=task.get("assigned_to", "agent"),
                    due_within_days=task.get("due_within_days", 1),
                    category=task.get("category", "other")
                ))

            return summary

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse summary JSON: {e}")
            # Return basic summary
            return CallSummary(
                recording_id=recording_id,
                summary_type=summary_type.value,
                one_liner="Summary generation partially failed - see executive summary",
                executive_summary=response_text[:1000],
                key_points=[],
                generated_at=datetime.now().isoformat()
            )

    def _save_summary(self, summary: CallSummary) -> None:
        """Save summary to database."""
        try:
            # Check if ci_call_summaries table exists, create if not
            self.db.execute(text("""
                CREATE TABLE IF NOT EXISTS ci_call_summaries (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    recording_id UUID NOT NULL REFERENCES ci_call_recordings(id),
                    summary_type VARCHAR(50) DEFAULT 'standard',
                    one_liner TEXT,
                    executive_summary TEXT,
                    key_points JSONB DEFAULT '[]',
                    call_outcome VARCHAR(50),
                    customer_sentiment VARCHAR(50),
                    customer_stage VARCHAR(50),
                    customer_urgency VARCHAR(50),
                    customer_name VARCHAR(255),
                    insights JSONB DEFAULT '[]',
                    follow_up_tasks JSONB DEFAULT '[]',
                    immediate_actions JSONB DEFAULT '[]',
                    objections_raised JSONB DEFAULT '[]',
                    questions_asked JSONB DEFAULT '[]',
                    next_contact_date DATE,
                    talk_time_agent_pct DECIMAL(5,2),
                    talk_time_customer_pct DECIMAL(5,2),
                    loan_id INTEGER,
                    lead_id INTEGER,
                    generated_at TIMESTAMP DEFAULT NOW(),
                    tokens_used INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """))

            # Insert summary
            self.db.execute(text("""
                INSERT INTO ci_call_summaries (
                    recording_id, summary_type, one_liner, executive_summary,
                    key_points, call_outcome, customer_sentiment, customer_stage,
                    customer_urgency, insights, follow_up_tasks, immediate_actions,
                    objections_raised, questions_asked, next_contact_date,
                    talk_time_agent_pct, talk_time_customer_pct, loan_id, lead_id,
                    generated_at, tokens_used
                ) VALUES (
                    :recording_id, :summary_type, :one_liner, :executive_summary,
                    :key_points, :call_outcome, :customer_sentiment, :customer_stage,
                    :customer_urgency, :insights, :follow_up_tasks, :immediate_actions,
                    :objections_raised, :questions_asked, :next_contact_date,
                    :talk_time_agent_pct, :talk_time_customer_pct, :loan_id, :lead_id,
                    :generated_at, :tokens_used
                )
            """), {
                "recording_id": summary.recording_id,
                "summary_type": summary.summary_type,
                "one_liner": summary.one_liner,
                "executive_summary": summary.executive_summary,
                "key_points": json.dumps(summary.key_points),
                "call_outcome": summary.call_outcome,
                "customer_sentiment": summary.customer_sentiment,
                "customer_stage": summary.customer_stage,
                "customer_urgency": summary.customer_urgency,
                "insights": json.dumps([asdict(i) for i in summary.insights]),
                "follow_up_tasks": json.dumps([asdict(t) for t in summary.follow_up_tasks]),
                "immediate_actions": json.dumps(summary.immediate_actions),
                "objections_raised": json.dumps(summary.objections_raised),
                "questions_asked": json.dumps(summary.questions_asked),
                "next_contact_date": summary.next_contact_date,
                "talk_time_agent_pct": summary.talk_time_agent_pct,
                "talk_time_customer_pct": summary.talk_time_customer_pct,
                "loan_id": summary.loan_id,
                "lead_id": summary.lead_id,
                "generated_at": summary.generated_at,
                "tokens_used": summary.tokens_used
            })

            self.db.commit()

        except SQLAlchemyError as e:
            logger.error(f"Failed to save summary: {e}")
            self.db.rollback()
            raise

    def _create_follow_up_tasks(
        self,
        summary: CallSummary,
        recording: Dict[str, Any]
    ) -> None:
        """Create follow-up tasks in the CRM from summary."""
        try:
            for task in summary.follow_up_tasks:
                # Calculate due date
                due_date = datetime.now() + timedelta(days=task.due_within_days)

                # Map priority
                priority_map = {
                    "critical": 1,
                    "high": 2,
                    "medium": 3,
                    "low": 4
                }
                priority = priority_map.get(task.priority, 3)

                # Create task
                self.db.execute(text("""
                    INSERT INTO tasks (
                        title, description, priority, status,
                        due_date, assigned_to, lead_id, loan_id,
                        source, source_id, created_at
                    ) VALUES (
                        :title, :description, :priority, 'pending',
                        :due_date, :assigned_to, :lead_id, :loan_id,
                        'call_summary', :source_id, NOW()
                    )
                """), {
                    "title": task.title,
                    "description": f"{task.description}\n\n[Auto-created from call summary]",
                    "priority": priority,
                    "due_date": due_date,
                    "assigned_to": recording.get("agent_user_id"),
                    "lead_id": summary.lead_id,
                    "loan_id": summary.loan_id,
                    "source_id": summary.recording_id
                })

            self.db.commit()
            logger.info(f"Created {len(summary.follow_up_tasks)} follow-up tasks from call summary")

        except SQLAlchemyError as e:
            logger.error(f"Failed to create follow-up tasks: {e}")
            # Don't fail the summary generation if task creation fails
            self.db.rollback()


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_summary_service(db: Session) -> CallSummaryService:
    """Get call summary service instance."""
    return CallSummaryService(db)
