"""
Call Monitoring Orchestrator Service

Central orchestrator that:
- Manages call sessions
- Routes transcripts to AI agents
- Runs agents in parallel
- Merges and deduplicates artifacts
- Handles approval workflow
- Executes approved artifacts
"""

import os
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import uuid
import json
import re

from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)

# PII patterns for log redaction
_PII_PATTERNS = [
    (re.compile(r'\b\d{3}-\d{2}-\d{4}\b'), '[SSN]'),                    # SSN
    (re.compile(r'\b\d{9}\b(?!\d)'), '[SSN]'),                            # SSN no dashes
    (re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'), '[EMAIL]'),  # Email
    (re.compile(r'\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b'), '[PHONE]'),  # Phone
    (re.compile(r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b'), '[CARD]'),  # Credit card
]

def _redact_pii(text_val: str) -> str:
    """Redact PII patterns from a string."""
    for pattern, replacement in _PII_PATTERNS:
        text_val = pattern.sub(replacement, text_val)
    return text_val

def _redact_payload(obj: Any) -> Any:
    """Recursively redact PII from a payload dict/list/string."""
    if isinstance(obj, str):
        return _redact_pii(obj)
    elif isinstance(obj, dict):
        return {k: _redact_payload(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_redact_payload(item) for item in obj]
    return obj


# =============================================================================
# CALL TYPE CLASSIFICATION FOR CONDITIONAL AGENT DISPATCH
# =============================================================================

# Map call types to the subset of agents that are relevant
CALL_TYPE_AGENTS = {
    # Purchase/refinance calls need all financial agents
    "purchase": ["scribe", "junior_lo", "underwriter", "calculator", "marketing", "receptionist"],
    "refinance": ["scribe", "junior_lo", "underwriter", "calculator", "marketing", "receptionist"],
    # Support/status calls only need scribe + junior LO
    "support": ["scribe", "junior_lo", "receptionist"],
    "status_check": ["scribe", "junior_lo"],
    # General inquiry calls need scribe + junior LO + receptionist
    "inquiry": ["scribe", "junior_lo", "receptionist"],
    # Default: run core agents
    "unknown": ["scribe", "junior_lo", "underwriter", "receptionist"],
}

# Keywords for fast call-type classification (avoids LLM call)
_PURCHASE_KEYWORDS = [
    "purchase", "buying", "buy a home", "new home", "offer", "contract",
    "down payment", "pre-approval", "pre-qualify", "house hunting",
    "first-time", "fha", "va loan", "conventional",
]
_REFINANCE_KEYWORDS = [
    "refinance", "refi", "cash out", "cash-out", "rate and term",
    "lower my rate", "lower payment", "streamline",
]
_SUPPORT_KEYWORDS = [
    "update", "status", "where are we", "what's happening", "when will",
    "condition", "document", "upload", "closing date", "timeline",
]
_INQUIRY_KEYWORDS = [
    "question", "wondering", "curious", "information", "how does",
    "what are", "can you explain", "rates today", "qualify",
]


def classify_call_type(transcript: str) -> str:
    """
    Fast keyword-based classification of call type from transcript.
    Runs in <1ms. No LLM call needed.

    Returns one of: purchase, refinance, support, status_check, inquiry, unknown
    """
    transcript_lower = transcript.lower()

    # Score each type by keyword matches
    scores = {
        "purchase": sum(1 for kw in _PURCHASE_KEYWORDS if kw in transcript_lower),
        "refinance": sum(1 for kw in _REFINANCE_KEYWORDS if kw in transcript_lower),
        "support": sum(1 for kw in _SUPPORT_KEYWORDS if kw in transcript_lower),
        "inquiry": sum(1 for kw in _INQUIRY_KEYWORDS if kw in transcript_lower),
    }

    # Get the highest scoring type
    best_type = max(scores, key=scores.get)
    best_score = scores[best_type]

    if best_score == 0:
        return "unknown"

    return best_type


@dataclass
class ProcessingResult:
    """Result from agent processing."""
    success: bool
    agent_type: str
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    tokens_used: int = 0
    processing_time_ms: int = 0


@dataclass
class MergedArtifacts:
    """Merged and deduplicated artifacts from all agents."""
    summaries: List[Dict[str, Any]] = field(default_factory=list)
    action_items: List[Dict[str, Any]] = field(default_factory=list)
    tasks: List[Dict[str, Any]] = field(default_factory=list)
    document_requests: List[Dict[str, Any]] = field(default_factory=list)
    risk_flags: List[Dict[str, Any]] = field(default_factory=list)
    intake_fields: List[Dict[str, Any]] = field(default_factory=list)
    uw_notes: List[Dict[str, Any]] = field(default_factory=list)
    follow_up_drafts: List[Dict[str, Any]] = field(default_factory=list)
    calculator_results: List[Dict[str, Any]] = field(default_factory=list)
    # Marketing Agent artifacts
    story_notes: List[Dict[str, Any]] = field(default_factory=list)
    story_themes: List[Dict[str, Any]] = field(default_factory=list)
    borrower_quotes: List[Dict[str, Any]] = field(default_factory=list)
    content_ideas: List[Dict[str, Any]] = field(default_factory=list)
    marketing_milestones: List[Dict[str, Any]] = field(default_factory=list)
    # Receptionist Agent artifacts
    scheduled_appointments: List[Dict[str, Any]] = field(default_factory=list)
    follow_up_calls: List[Dict[str, Any]] = field(default_factory=list)
    calendar_actions: List[Dict[str, Any]] = field(default_factory=list)
    meeting_summaries: List[Dict[str, Any]] = field(default_factory=list)
    # Stacked notes (from any agent)
    stacked_notes: List[Dict[str, Any]] = field(default_factory=list)


class CallMonitoringOrchestrator:
    """
    Central orchestrator for the call monitoring AI system.

    Coordinates six parallel AI agents:
    - Scribe: Summary, action items, follow-up drafts
    - Junior LO: Pricing scenarios, doc requests, intake fields, 5 C's analysis
    - Underwriter: Risk flags, conditions, compliance checks
    - Calculator: Mortgage calculations from conversation data
    - Marketing: Borrower story capture for testimonials and content
    - Receptionist: Calendar scheduling and appointment coordination
    """

    def __init__(self, db: Session):
        self.db = db
        self._agents = {}
        self._initialize_agents()

    def _initialize_agents(self):
        """Initialize AI agents."""
        from .agents.scribe_agent import ScribeAgent
        from .agents.junior_lo_agent import JuniorLOAgent
        from .agents.underwriter_agent import UnderwriterAgent
        from .agents.calculator_agent import CalculatorAgent
        from .agents.marketing_agent import MarketingAgent
        from .agents.receptionist_agent import CallSchedulingAgent

        self._agents = {
            'scribe': ScribeAgent(self.db),
            'junior_lo': JuniorLOAgent(self.db),
            'underwriter': UnderwriterAgent(self.db),
            'calculator': CalculatorAgent(self.db),
            'marketing': MarketingAgent(self.db),
            'receptionist': CallSchedulingAgent(self.db),
        }

    # =========================================================================
    # SESSION MANAGEMENT
    # =========================================================================

    def create_session(
        self,
        capture_mode: str,
        user_id: str,
        loan_id: Optional[str] = None,
        lead_id: Optional[str] = None,
        contact_id: Optional[str] = None,
        recording_id: Optional[str] = None,
        participants: Optional[List[Dict]] = None,
        metadata: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Create a new call session."""
        session_id = str(uuid.uuid4())
        now = datetime.utcnow()

        self.db.execute(text("""
            INSERT INTO call_sessions (
                id, capture_mode, user_id, loan_id, lead_id, contact_id,
                recording_id, participants, metadata, status, started_at
            ) VALUES (
                :id, :capture_mode, :user_id, :loan_id, :lead_id, :contact_id,
                :recording_id, :participants, :metadata, 'active', :started_at
            )
        """), {
            "id": session_id,
            "capture_mode": capture_mode,
            "user_id": user_id,
            "loan_id": loan_id,
            "lead_id": lead_id,
            "contact_id": contact_id,
            "recording_id": recording_id,
            "participants": json.dumps(participants or []),
            "metadata": json.dumps(metadata or {}),
            "started_at": now,
        })
        self.db.commit()

        # Log event
        self._log_event(session_id, 'session_created', {
            'capture_mode': capture_mode,
            'user_id': user_id,
        })

        return {
            "session_id": session_id,
            "status": "active",
            "started_at": now.isoformat(),
        }

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session details."""
        result = self.db.execute(text("""
            SELECT id, capture_mode, recording_id, loan_id, lead_id, contact_id,
                   user_id, status, transcript_state, full_transcript, participants,
                   metadata, tags, overall_confidence, started_at, ended_at,
                   duration_seconds, created_at
            FROM call_sessions
            WHERE id = :id
        """), {"id": session_id}).fetchone()

        if not result:
            return None

        return {
            "id": str(result[0]),
            "capture_mode": result[1],
            "recording_id": str(result[2]) if result[2] else None,
            "loan_id": str(result[3]) if result[3] else None,
            "lead_id": str(result[4]) if result[4] else None,
            "contact_id": str(result[5]) if result[5] else None,
            "user_id": str(result[6]) if result[6] else None,
            "status": result[7],
            "transcript_state": result[8],
            "full_transcript": result[9],
            "participants": result[10] if result[10] else [],
            "metadata": result[11] if result[11] else {},
            "tags": result[12] if result[12] else [],
            "overall_confidence": float(result[13]) if result[13] else None,
            "started_at": result[14].isoformat() if result[14] else None,
            "ended_at": result[15].isoformat() if result[15] else None,
            "duration_seconds": result[16],
            "created_at": result[17].isoformat() if result[17] else None,
        }

    def update_session(
        self,
        session_id: str,
        status: Optional[str] = None,
        ended_at: Optional[datetime] = None,
        metadata: Optional[Dict] = None,
    ) -> bool:
        """Update session details."""
        updates = []
        params = {"id": session_id}

        if status:
            updates.append("status = :status")
            params["status"] = status
        if ended_at:
            updates.append("ended_at = :ended_at")
            params["ended_at"] = ended_at
        if metadata:
            updates.append("metadata = metadata || :metadata")
            params["metadata"] = json.dumps(metadata)

        if not updates:
            return False

        self.db.execute(text(f"""
            UPDATE call_sessions
            SET {', '.join(updates)}, updated_at = NOW()
            WHERE id = :id
        """), params)
        self.db.commit()

        return True

    # =========================================================================
    # TRANSCRIPT PROCESSING
    # =========================================================================

    async def process_transcript_chunk(
        self,
        session_id: str,
        chunk: str,
        speaker: Optional[str] = None,
        timestamp_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Process a transcript chunk (for real-time processing)."""
        # Append to full transcript
        self.db.execute(text("""
            UPDATE call_sessions
            SET full_transcript = COALESCE(full_transcript, '') || :chunk,
                transcript_state = 'partial',
                transcript_word_count = COALESCE(transcript_word_count, 0) + :word_count,
                updated_at = NOW()
            WHERE id = :id
        """), {
            "id": session_id,
            "chunk": chunk + '\n',
            "word_count": len(chunk.split()),
        })
        self.db.commit()

        # Log event
        self._log_event(session_id, 'transcript_chunk', {
            'speaker': speaker,
            'timestamp_ms': timestamp_ms,
            'word_count': len(chunk.split()),
        }, transcript_timestamp_ms=timestamp_ms)

        return {"status": "received", "word_count": len(chunk.split())}

    def set_transcript(
        self,
        session_id: str,
        transcript: str,
        confidence: Optional[float] = None,
    ) -> bool:
        """Set the full transcript for a session."""
        self.db.execute(text("""
            UPDATE call_sessions
            SET full_transcript = :transcript,
                transcript_state = 'complete',
                transcript_word_count = :word_count,
                overall_confidence = :confidence,
                updated_at = NOW()
            WHERE id = :id
        """), {
            "id": session_id,
            "transcript": transcript,
            "word_count": len(transcript.split()),
            "confidence": confidence,
        })
        self.db.commit()

        self._log_event(session_id, 'transcript_complete', {
            'word_count': len(transcript.split()),
            'confidence': confidence,
        })

        return True

    def get_transcript(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get transcript for a session."""
        result = self.db.execute(text("""
            SELECT full_transcript, transcript_state, transcript_word_count, overall_confidence
            FROM call_sessions
            WHERE id = :id
        """), {"id": session_id}).fetchone()

        if not result:
            return None

        return {
            "transcript": result[0],
            "state": result[1],
            "word_count": result[2],
            "confidence": float(result[3]) if result[3] else None,
        }

    # =========================================================================
    # AGENT EXECUTION
    # =========================================================================

    async def run_agents(
        self,
        session_id: str,
        trigger: str = 'end_of_call',
        agent_types: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Run AI agents on the session transcript.

        Args:
            session_id: Call session ID
            trigger: What triggered the run (end_of_call, manual, periodic)
            agent_types: Specific agents to run, or None for all

        Returns:
            Processing results from all agents
        """
        # Get session and transcript
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        transcript = session.get('full_transcript')
        if not transcript:
            raise ValueError(f"No transcript for session {session_id}")

        # Update session status
        self.update_session(session_id, status='processing')
        self.db.execute(text("""
            UPDATE call_sessions SET processing_started_at = NOW() WHERE id = :id
        """), {"id": session_id})
        self.db.commit()

        # Determine which agents to run
        if agent_types:
            # Explicit agents requested — run exactly those
            agents_to_run = agent_types
        else:
            # Classify call type and run only relevant agents
            call_type = classify_call_type(transcript)
            agents_to_run = CALL_TYPE_AGENTS.get(call_type, CALL_TYPE_AGENTS["unknown"])
            logger.info(
                f"[CM_ORCHESTRATOR] Call type: {call_type} → "
                f"running {len(agents_to_run)}/{6} agents: {agents_to_run}"
            )

        self._log_event(session_id, 'processing_started', {
            'trigger': trigger,
            'agents': agents_to_run,
        })

        # Build context for agents
        context = {
            'session_id': session_id,
            'loan_id': session.get('loan_id'),
            'lead_id': session.get('lead_id'),
            'transcript': transcript,
            'participants': session.get('participants', []),
            'capture_mode': session.get('capture_mode'),
            'metadata': session.get('metadata', {}),
        }

        # Fetch additional context (loan/lead data)
        context = await self._enrich_context(context)

        # Run agents in parallel
        results = await self._run_agents_parallel(session_id, agents_to_run, context)

        # Merge artifacts
        merged = self._merge_artifacts(results)

        # Store artifacts
        artifact_ids = await self._store_artifacts(session_id, merged, results)

        # Update session status
        self.db.execute(text("""
            UPDATE call_sessions
            SET status = 'review_pending',
                processing_completed_at = NOW(),
                updated_at = NOW()
            WHERE id = :id
        """), {"id": session_id})
        self.db.commit()

        self._log_event(session_id, 'processing_completed', {
            'artifact_count': len(artifact_ids),
            'agents_run': agents_to_run,
        })

        return {
            "session_id": session_id,
            "status": "review_pending",
            "agents_run": agents_to_run,
            "artifact_count": len(artifact_ids),
            "results": {
                agent: {
                    "success": r.success,
                    "artifact_count": len(r.artifacts),
                    "tokens_used": r.tokens_used,
                }
                for agent, r in results.items()
            },
        }

    async def _run_agents_parallel(
        self,
        session_id: str,
        agent_types: List[str],
        context: Dict[str, Any],
    ) -> Dict[str, ProcessingResult]:
        """Run multiple agents in parallel."""
        tasks = []

        for agent_type in agent_types:
            if agent_type in self._agents:
                tasks.append(self._run_single_agent(session_id, agent_type, context))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Map results back to agent types
        result_map = {}
        for i, agent_type in enumerate(agent_types):
            if isinstance(results[i], Exception):
                result_map[agent_type] = ProcessingResult(
                    success=False,
                    agent_type=agent_type,
                    error=str(results[i]),
                )
            else:
                result_map[agent_type] = results[i]

        return result_map

    async def _run_single_agent(
        self,
        session_id: str,
        agent_type: str,
        context: Dict[str, Any],
    ) -> ProcessingResult:
        """Run a single agent and track the run."""
        run_id = str(uuid.uuid4())
        start_time = datetime.utcnow()

        # Create agent run record
        self.db.execute(text("""
            INSERT INTO agent_runs (
                id, session_id, agent_type, status, input_context, started_at
            ) VALUES (
                :id, :session_id, :agent_type, 'running', :context, :started_at
            )
        """), {
            "id": run_id,
            "session_id": session_id,
            "agent_type": agent_type,
            "context": json.dumps({k: v for k, v in context.items() if k != 'transcript'}),
            "started_at": start_time,
        })
        self.db.commit()

        self._log_event(session_id, 'agent_started', {
            'agent_type': agent_type,
            'run_id': run_id,
        })

        try:
            agent = self._agents[agent_type]
            result = await agent.process(context)

            end_time = datetime.utcnow()
            processing_time_ms = int((end_time - start_time).total_seconds() * 1000)

            # Update run record
            self.db.execute(text("""
                UPDATE agent_runs
                SET status = 'completed',
                    artifacts = :artifacts,
                    raw_output = :raw_output,
                    model_used = :model_used,
                    tokens_used = :tokens_used,
                    input_tokens = :input_tokens,
                    output_tokens = :output_tokens,
                    processing_time_ms = :processing_time_ms,
                    completed_at = :completed_at,
                    updated_at = NOW()
                WHERE id = :id
            """), {
                "id": run_id,
                "artifacts": json.dumps(result.artifacts),
                "raw_output": result.raw_output if hasattr(result, 'raw_output') else None,
                "model_used": result.model_used if hasattr(result, 'model_used') else None,
                "tokens_used": result.tokens_used,
                "input_tokens": result.input_tokens if hasattr(result, 'input_tokens') else None,
                "output_tokens": result.output_tokens if hasattr(result, 'output_tokens') else None,
                "processing_time_ms": processing_time_ms,
                "completed_at": end_time,
            })
            self.db.commit()

            self._log_event(session_id, 'agent_completed', {
                'agent_type': agent_type,
                'run_id': run_id,
                'artifact_count': len(result.artifacts),
                'tokens_used': result.tokens_used,
            })

            return ProcessingResult(
                success=True,
                agent_type=agent_type,
                artifacts=result.artifacts,
                tokens_used=result.tokens_used,
                processing_time_ms=processing_time_ms,
            )

        except Exception as e:
            logger.error(f"Agent {agent_type} failed: {e}")

            # Update run record with error
            self.db.execute(text("""
                UPDATE agent_runs
                SET status = 'failed',
                    error_message = :error,
                    completed_at = NOW(),
                    updated_at = NOW()
                WHERE id = :id
            """), {"id": run_id, "error": "Internal server error"})
            self.db.commit()

            self._log_event(session_id, 'agent_failed', {
                'agent_type': agent_type,
                'run_id': run_id,
                'error': str(e),
            })

            return ProcessingResult(
                success=False,
                agent_type=agent_type,
                error=str(e),
            )

    async def _enrich_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Enrich context with loan/lead data and transaction team."""
        if context.get('loan_id'):
            loan_data = self.db.execute(text("""
                SELECT id, loan_number, borrower_name, loan_amount, loan_type,
                       property_address, status, credit_score
                FROM loans
                WHERE id = :id
            """), {"id": context['loan_id']}).fetchone()

            if loan_data:
                context['loan'] = {
                    "id": str(loan_data[0]),
                    "loan_number": loan_data[1],
                    "borrower_name": loan_data[2],
                    "loan_amount": float(loan_data[3]) if loan_data[3] else None,
                    "loan_type": loan_data[4],
                    "property_address": loan_data[5],
                    "status": loan_data[6],
                    "credit_score": loan_data[7],
                }

        if context.get('lead_id'):
            lead_data = self.db.execute(text("""
                SELECT id, first_name, last_name, email, phone, stage, source
                FROM leads
                WHERE id = :id
            """), {"id": context['lead_id']}).fetchone()

            if lead_data:
                context['lead'] = {
                    "id": str(lead_data[0]),
                    "name": f"{lead_data[1]} {lead_data[2]}".strip(),
                    "email": lead_data[3],
                    "phone": lead_data[4],
                    "stage": lead_data[5],
                    "source": lead_data[6],
                }

        # Build transaction team context for Marketing and Receptionist agents
        context['transaction_team'] = await self._build_transaction_team_context(context)

        # Get prior story notes for Marketing agent continuity
        if context.get('loan_id') or context.get('lead_id'):
            context['prior_story_notes'] = await self._get_prior_story_notes(context)

        return context

    async def _build_transaction_team_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build transaction team context so agents know who is involved.

        This enables Marketing and Receptionist agents to understand references
        like "my assistant", "the realtor", "your agent", etc.
        """
        team = {}
        user_id = context.get('metadata', {}).get('user_id') or context.get('session', {}).get('user_id')
        loan_id = context.get('loan_id')
        lead_id = context.get('lead_id')

        # Get Loan Officer + Production Assistant in a single query (replaces 2 queries)
        if user_id:
            lo_pa_data = self.db.execute(text("""
                SELECT
                    lo.id, lo.name, lo.email, lo.phone, lo.calendar_link,
                    pa.id as pa_id, pa.name as pa_name, pa.email as pa_email, pa.phone as pa_phone
                FROM users lo
                LEFT JOIN user_assignments ua ON ua.loan_officer_id = lo.id AND ua.role = 'production_assistant'
                LEFT JOIN users pa ON pa.id = ua.assistant_id
                WHERE lo.id = :id
            """), {"id": user_id}).fetchone()

            if lo_pa_data:
                team['loan_officer'] = {
                    "id": str(lo_pa_data[0]),
                    "name": lo_pa_data[1],
                    "email": lo_pa_data[2],
                    "phone": lo_pa_data[3],
                    "calendar_link": lo_pa_data[4],
                }

                if lo_pa_data[5]:  # pa_id
                    team['production_assistant'] = {
                        "id": str(lo_pa_data[5]),
                        "name": lo_pa_data[6],
                        "email": lo_pa_data[7],
                        "phone": lo_pa_data[8],
                    }

        # Get Borrower(s) from loan or lead
        borrowers = []
        if loan_id:
            # Get primary borrower from loan
            borrower_data = self.db.execute(text("""
                SELECT c.id, c.first_name, c.last_name, c.email, c.phone,
                       c.preferred_contact_time
                FROM contacts c
                JOIN loans l ON l.borrower_id = c.id OR l.co_borrower_id = c.id
                WHERE l.id = :loan_id
            """), {"loan_id": loan_id}).fetchall()

            for i, bd in enumerate(borrower_data):
                borrowers.append({
                    "id": str(bd[0]),
                    "name": f"{bd[1]} {bd[2]}".strip(),
                    "email": bd[3],
                    "phone": bd[4],
                    "preferred_contact_time": bd[5],
                    "is_primary": i == 0,
                })

        elif lead_id:
            # Get lead contact info
            lead_data = self.db.execute(text("""
                SELECT id, first_name, last_name, email, phone, preferred_contact_time
                FROM leads
                WHERE id = :lead_id
            """), {"lead_id": lead_id}).fetchone()

            if lead_data:
                borrowers.append({
                    "id": str(lead_data[0]),
                    "name": f"{lead_data[1]} {lead_data[2]}".strip(),
                    "email": lead_data[3],
                    "phone": lead_data[4],
                    "preferred_contact_time": lead_data[5],
                    "is_primary": True,
                })

        if borrowers:
            team['borrowers'] = borrowers

        # Get loan team in a single JOIN query (replaces 5 separate queries)
        if loan_id:
            loan_team = self.db.execute(text("""
                SELECT
                    proc.id as proc_id, proc.name as proc_name, proc.email as proc_email,
                    tc.id as tc_id, tc.name as tc_name, tc.contact_name as tc_contact,
                    tc.email as tc_email, tc.phone as tc_phone,
                    ia.id as ia_id, ia.name as ia_name, ia.email as ia_email,
                    ia.phone as ia_phone, ia.company as ia_company,
                    ba.id as ba_id, ba.name as ba_name, ba.email as ba_email,
                    ba.phone as ba_phone, ba.brokerage as ba_brokerage,
                    la.id as la_id, la.name as la_name, la.email as la_email,
                    la.phone as la_phone, la.brokerage as la_brokerage
                FROM loans l
                LEFT JOIN users proc ON proc.id = l.processor_id
                LEFT JOIN title_companies tc ON tc.id = l.title_company_id
                LEFT JOIN insurance_agents ia ON ia.id = l.insurance_agent_id
                LEFT JOIN realtor_assignments ba ON ba.loan_id = l.id AND ba.role = 'buyer_agent'
                LEFT JOIN realtor_assignments la ON la.loan_id = l.id AND la.role = 'listing_agent'
                WHERE l.id = :loan_id
            """), {"loan_id": loan_id}).fetchone()

            if loan_team:
                if loan_team[0]:  # proc_id
                    team['processor'] = {
                        "id": str(loan_team[0]),
                        "name": loan_team[1],
                        "email": loan_team[2],
                    }
                if loan_team[3]:  # tc_id
                    team['title_company'] = {
                        "id": str(loan_team[3]),
                        "name": loan_team[4],
                        "contact_name": loan_team[5],
                        "email": loan_team[6],
                        "phone": loan_team[7],
                    }
                if loan_team[8]:  # ia_id
                    team['insurance_agent'] = {
                        "id": str(loan_team[8]),
                        "name": loan_team[9],
                        "email": loan_team[10],
                        "phone": loan_team[11],
                        "company": loan_team[12],
                    }
                if loan_team[13]:  # ba_id
                    team['buyer_agent'] = {
                        "id": str(loan_team[13]),
                        "name": loan_team[14],
                        "email": loan_team[15],
                        "phone": loan_team[16],
                        "brokerage": loan_team[17],
                    }
                if loan_team[18]:  # la_id
                    team['listing_agent'] = {
                        "id": str(loan_team[18]),
                        "name": loan_team[19],
                        "email": loan_team[20],
                        "phone": loan_team[21],
                        "brokerage": loan_team[22],
                    }

        return team

    async def _get_prior_story_notes(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get prior story notes from previous calls for Marketing agent continuity."""
        loan_id = context.get('loan_id')
        lead_id = context.get('lead_id')

        if not loan_id and not lead_id:
            return []

        # Get prior story notes from call_artifacts
        if loan_id:
            filter_clause = "cs.loan_id = :entity_id"
        else:
            filter_clause = "cs.lead_id = :entity_id"

        prior_notes = self.db.execute(text(f"""
            SELECT ca.content, ca.structured_data, ca.created_at
            FROM call_artifacts ca
            JOIN call_sessions cs ON cs.id = ca.session_id
            WHERE {filter_clause}
              AND ca.artifact_type IN ('borrower_story_note', 'story_theme', 'borrower_quote')
            ORDER BY ca.created_at DESC
            LIMIT 10
        """), {"entity_id": loan_id or lead_id}).fetchall()

        return [
            {
                "content": note[0],
                "structured_data": note[1] if note[1] else {},
                "created_at": note[2].isoformat() if note[2] else None,
            }
            for note in prior_notes
        ]

    # =========================================================================
    # ARTIFACT MANAGEMENT
    # =========================================================================

    def _merge_artifacts(self, results: Dict[str, ProcessingResult]) -> MergedArtifacts:
        """Merge and deduplicate artifacts from all agents."""
        merged = MergedArtifacts()

        for agent_type, result in results.items():
            if not result.success:
                continue

            for artifact in result.artifacts:
                artifact['source_agent'] = agent_type
                artifact_type = artifact.get('type', 'unknown')

                # Route to appropriate list
                if artifact_type == 'summary':
                    merged.summaries.append(artifact)
                elif artifact_type == 'action_item':
                    merged.action_items.append(artifact)
                elif artifact_type == 'task':
                    merged.tasks.append(artifact)
                elif artifact_type == 'document_request':
                    merged.document_requests.append(artifact)
                elif artifact_type == 'risk_flag':
                    merged.risk_flags.append(artifact)
                elif artifact_type == 'intake_field':
                    merged.intake_fields.append(artifact)
                elif artifact_type == 'uw_note':
                    merged.uw_notes.append(artifact)
                elif artifact_type == 'follow_up_draft':
                    merged.follow_up_drafts.append(artifact)
                elif artifact_type in ('calculator_result', 'calculator_recommendation'):
                    merged.calculator_results.append(artifact)
                # Marketing Agent artifacts
                elif artifact_type == 'borrower_story_note':
                    merged.story_notes.append(artifact)
                elif artifact_type == 'story_theme':
                    merged.story_themes.append(artifact)
                elif artifact_type == 'borrower_quote':
                    merged.borrower_quotes.append(artifact)
                elif artifact_type == 'content_idea':
                    merged.content_ideas.append(artifact)
                elif artifact_type == 'marketing_milestone':
                    merged.marketing_milestones.append(artifact)
                # Receptionist Agent artifacts
                elif artifact_type == 'scheduled_appointment':
                    merged.scheduled_appointments.append(artifact)
                elif artifact_type == 'follow_up_call':
                    merged.follow_up_calls.append(artifact)
                elif artifact_type == 'calendar_action':
                    merged.calendar_actions.append(artifact)
                elif artifact_type == 'meeting_summary':
                    merged.meeting_summaries.append(artifact)
                # Stacked notes (from any agent)
                elif artifact_type == 'stacked_note':
                    merged.stacked_notes.append(artifact)

        # Deduplicate similar items
        merged = self._deduplicate_artifacts(merged)

        return merged

    def _deduplicate_artifacts(self, merged: MergedArtifacts) -> MergedArtifacts:
        """Remove duplicate artifacts based on similarity."""
        # For now, simple deduplication based on title similarity
        # More sophisticated deduplication can be added later

        def dedupe_list(items: List[Dict]) -> List[Dict]:
            seen_titles = set()
            result = []
            for item in items:
                title = item.get('title', '').lower().strip()
                if title and title not in seen_titles:
                    seen_titles.add(title)
                    result.append(item)
                elif not title:
                    result.append(item)
            return result

        merged.action_items = dedupe_list(merged.action_items)
        merged.tasks = dedupe_list(merged.tasks)
        merged.document_requests = dedupe_list(merged.document_requests)

        return merged

    async def _store_artifacts(
        self,
        session_id: str,
        merged: MergedArtifacts,
        results: Dict[str, ProcessingResult],
    ) -> List[str]:
        """Store all artifacts in the database."""
        artifact_ids = []

        # Get run IDs for linking
        run_ids = {}
        runs = self.db.execute(text("""
            SELECT id, agent_type FROM agent_runs WHERE session_id = :session_id
        """), {"session_id": session_id}).fetchall()
        for run in runs:
            run_ids[run[1]] = str(run[0])

        # Store all artifact types
        all_artifacts = [
            ('summary', merged.summaries),
            ('action_item', merged.action_items),
            ('task', merged.tasks),
            ('document_request', merged.document_requests),
            ('risk_flag', merged.risk_flags),
            ('intake_field', merged.intake_fields),
            ('uw_note', merged.uw_notes),
            ('follow_up_draft', merged.follow_up_drafts),
            ('calculator_result', merged.calculator_results),
            # Marketing Agent artifacts
            ('borrower_story_note', merged.story_notes),
            ('story_theme', merged.story_themes),
            ('borrower_quote', merged.borrower_quotes),
            ('content_idea', merged.content_ideas),
            ('marketing_milestone', merged.marketing_milestones),
            # Receptionist Agent artifacts
            ('scheduled_appointment', merged.scheduled_appointments),
            ('follow_up_call', merged.follow_up_calls),
            ('calendar_action', merged.calendar_actions),
            ('meeting_summary', merged.meeting_summaries),
            # Stacked notes
            ('stacked_note', merged.stacked_notes),
        ]

        for artifact_type, items in all_artifacts:
            for item in items:
                artifact_id = str(uuid.uuid4())
                source_agent = item.get('source_agent', 'unknown')
                run_id = run_ids.get(source_agent)

                # Determine approval requirements
                requires_approval = self._requires_approval(artifact_type, item)
                approval_status = 'auto_approved' if not requires_approval else 'pending'

                self.db.execute(text("""
                    INSERT INTO call_artifacts (
                        id, session_id, run_id, artifact_type, title, content,
                        structured_data, approval_status, requires_approval,
                        confidence, source_evidence, source_timestamp_ms,
                        priority, metadata
                    ) VALUES (
                        :id, :session_id, :run_id, :artifact_type, :title, :content,
                        :structured_data, :approval_status, :requires_approval,
                        :confidence, :source_evidence, :source_timestamp_ms,
                        :priority, :metadata
                    )
                """), {
                    "id": artifact_id,
                    "session_id": session_id,
                    "run_id": run_id,
                    "artifact_type": artifact_type,
                    "title": item.get('title'),
                    "content": item.get('content'),
                    "structured_data": json.dumps(item.get('structured_data', {})),
                    "approval_status": approval_status,
                    "requires_approval": requires_approval,
                    "confidence": item.get('confidence'),
                    "source_evidence": item.get('evidence'),
                    "source_timestamp_ms": item.get('timestamp_ms'),
                    "priority": item.get('priority', 'medium'),
                    "metadata": json.dumps({
                        'source_agent': source_agent,
                        **item.get('metadata', {}),
                    }),
                })

                artifact_ids.append(artifact_id)

                # Store risk flags in dedicated table
                if artifact_type == 'risk_flag':
                    self._store_risk_flag(session_id, artifact_id, item)

                # Store intake fields in dedicated table
                if artifact_type == 'intake_field':
                    self._store_intake_field(session_id, artifact_id, item)

        self.db.commit()
        return artifact_ids

    def _requires_approval(self, artifact_type: str, item: Dict) -> bool:
        """Determine if an artifact requires human approval."""
        # Auto-approve rules - content capture and informational artifacts
        auto_approve_types = {
            'summary', 'uw_note', 'calculator_result',
            # Marketing artifacts are informational/content capture - auto-approve
            'borrower_story_note', 'story_theme', 'borrower_quote',
            'content_idea', 'marketing_milestone',
            # Meeting summaries are informational
            'meeting_summary',
            # Stacked notes are for historical record
            'stacked_note',
        }

        if artifact_type in auto_approve_types:
            confidence = item.get('confidence', 0)
            if confidence and confidence >= 0.75:
                return False

        # Always require approval for actions that modify data or create entities
        always_approve_types = {
            'task', 'document_request', 'intake_field', 'risk_flag',
            # Scheduling artifacts that create calendar events need approval
            'scheduled_appointment', 'calendar_action',
        }
        if artifact_type in always_approve_types:
            return True

        # Follow-up calls may need approval depending on confidence
        if artifact_type == 'follow_up_call':
            confidence = item.get('confidence', 0)
            return confidence < 0.85

        # Risk flags with high severity always need approval
        if artifact_type == 'risk_flag':
            severity = item.get('severity', 'medium')
            if severity in ('high', 'critical'):
                return True

        return True

    def _store_risk_flag(self, session_id: str, artifact_id: str, item: Dict):
        """Store a risk flag in the dedicated table."""
        # Get loan_id from session
        session = self.get_session(session_id)
        loan_id = session.get('loan_id') if session else None

        self.db.execute(text("""
            INSERT INTO call_risk_flags (
                id, session_id, artifact_id, risk_category, severity,
                title, description, evidence, recommended_action,
                condition_type, loan_id
            ) VALUES (
                gen_random_uuid(), :session_id, :artifact_id, :risk_category, :severity,
                :title, :description, :evidence, :recommended_action,
                :condition_type, :loan_id
            )
        """), {
            "session_id": session_id,
            "artifact_id": artifact_id,
            "risk_category": item.get('category', 'compliance'),
            "severity": item.get('severity', 'medium'),
            "title": item.get('title'),
            "description": item.get('content'),
            "evidence": item.get('evidence'),
            "recommended_action": item.get('recommended_action'),
            "condition_type": item.get('condition_type'),
            "loan_id": loan_id,
        })

    def _store_intake_field(self, session_id: str, artifact_id: str, item: Dict):
        """Store an intake field update in the dedicated table."""
        # Get entity info from session
        session = self.get_session(session_id)
        entity_type = 'loan' if session and session.get('loan_id') else 'lead'
        entity_id = session.get('loan_id') or session.get('lead_id') if session else None

        if not entity_id:
            return

        # Check for conflicts with current value
        current_value = item.get('current_value')
        proposed_value = item.get('proposed_value')
        has_conflict = current_value is not None and current_value != proposed_value

        self.db.execute(text("""
            INSERT INTO intake_field_updates (
                id, session_id, artifact_id, entity_type, entity_id,
                field_name, field_path, current_value, proposed_value,
                confidence, evidence_text, has_conflict
            ) VALUES (
                gen_random_uuid(), :session_id, :artifact_id, :entity_type, :entity_id,
                :field_name, :field_path, :current_value, :proposed_value,
                :confidence, :evidence_text, :has_conflict
            )
        """), {
            "session_id": session_id,
            "artifact_id": artifact_id,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "field_name": item.get('field_name'),
            "field_path": item.get('field_path'),
            "current_value": json.dumps(current_value),
            "proposed_value": json.dumps(proposed_value),
            "confidence": item.get('confidence'),
            "evidence_text": item.get('evidence'),
            "has_conflict": has_conflict,
        })

    # =========================================================================
    # APPROVAL WORKFLOW
    # =========================================================================

    def get_artifacts(
        self,
        session_id: str,
        artifact_type: Optional[str] = None,
        approval_status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get artifacts for a session."""
        filters = ["session_id = :session_id"]
        params = {"session_id": session_id}

        if artifact_type:
            filters.append("artifact_type = :artifact_type")
            params["artifact_type"] = artifact_type
        if approval_status:
            filters.append("approval_status = :approval_status")
            params["approval_status"] = approval_status

        where_clause = " AND ".join(filters)

        results = self.db.execute(text(f"""
            SELECT id, session_id, run_id, artifact_type, title, content,
                   structured_data, approval_status, requires_approval,
                   approved_by, approved_at, execution_status, executed_at,
                   linked_entity_type, linked_entity_id, confidence,
                   source_evidence, priority, metadata, created_at
            FROM call_artifacts
            WHERE {where_clause}
            ORDER BY created_at ASC
        """), params).fetchall()

        return [
            {
                "id": str(r[0]),
                "session_id": str(r[1]),
                "run_id": str(r[2]) if r[2] else None,
                "artifact_type": r[3],
                "title": r[4],
                "content": r[5],
                "structured_data": r[6] if r[6] else {},
                "approval_status": r[7],
                "requires_approval": r[8],
                "approved_by": str(r[9]) if r[9] else None,
                "approved_at": r[10].isoformat() if r[10] else None,
                "execution_status": r[11],
                "executed_at": r[12].isoformat() if r[12] else None,
                "linked_entity_type": r[13],
                "linked_entity_id": str(r[14]) if r[14] else None,
                "confidence": float(r[15]) if r[15] else None,
                "source_evidence": r[16],
                "priority": r[17],
                "metadata": r[18] if r[18] else {},
                "created_at": r[19].isoformat() if r[19] else None,
            }
            for r in results
        ]

    async def approve_artifacts(
        self,
        session_id: str,
        artifact_ids: List[str],
        user_id: str,
        action: str = 'approve',
        rejection_reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Approve or reject artifacts."""
        now = datetime.utcnow()

        if action == 'approve':
            self.db.execute(text("""
                UPDATE call_artifacts
                SET approval_status = 'approved',
                    approved_by = :user_id,
                    approved_at = :now,
                    updated_at = NOW()
                WHERE id = ANY(:ids) AND session_id = :session_id
            """), {
                "ids": artifact_ids,
                "session_id": session_id,
                "user_id": user_id,
                "now": now,
            })
        else:
            self.db.execute(text("""
                UPDATE call_artifacts
                SET approval_status = 'rejected',
                    rejection_reason = :reason,
                    updated_at = NOW()
                WHERE id = ANY(:ids) AND session_id = :session_id
            """), {
                "ids": artifact_ids,
                "session_id": session_id,
                "reason": rejection_reason,
            })

        self.db.commit()

        self._log_event(session_id, f'artifacts_{action}d', {
            'artifact_ids': artifact_ids,
            'user_id': user_id,
        })

        return {
            "action": action,
            "count": len(artifact_ids),
            "artifact_ids": artifact_ids,
        }

    async def execute_approved_artifacts(
        self,
        session_id: str,
        user_id: str,
    ) -> Dict[str, Any]:
        """Execute all approved artifacts (create tasks, doc requests, etc.)."""
        # Get approved artifacts that haven't been executed
        artifacts = self.db.execute(text("""
            SELECT id, artifact_type, title, content, structured_data, metadata
            FROM call_artifacts
            WHERE session_id = :session_id
              AND approval_status = 'approved'
              AND execution_status = 'pending'
        """), {"session_id": session_id}).fetchall()

        results = {
            "executed": [],
            "failed": [],
        }

        session = self.get_session(session_id)

        for artifact in artifacts:
            artifact_id = str(artifact[0])
            artifact_type = artifact[1]

            try:
                entity_id = await self._execute_artifact(
                    artifact_id=artifact_id,
                    artifact_type=artifact_type,
                    title=artifact[2],
                    content=artifact[3],
                    structured_data=artifact[4] or {},
                    metadata=artifact[5] or {},
                    session=session,
                    user_id=user_id,
                )

                # Update artifact with execution result
                self.db.execute(text("""
                    UPDATE call_artifacts
                    SET execution_status = 'executed',
                        executed_at = NOW(),
                        linked_entity_type = :entity_type,
                        linked_entity_id = :entity_id,
                        execution_result = :result,
                        updated_at = NOW()
                    WHERE id = :id
                """), {
                    "id": artifact_id,
                    "entity_type": artifact_type,
                    "entity_id": entity_id,
                    "result": json.dumps({"entity_id": entity_id}),
                })

                results["executed"].append({
                    "artifact_id": artifact_id,
                    "artifact_type": artifact_type,
                    "entity_id": entity_id,
                })

            except Exception as e:
                logger.error(f"Failed to execute artifact {artifact_id}: {e}")

                self.db.execute(text("""
                    UPDATE call_artifacts
                    SET execution_status = 'failed',
                        execution_result = :result,
                        updated_at = NOW()
                    WHERE id = :id
                """), {
                    "id": artifact_id,
                    "result": json.dumps({"error": "Internal server error"}),
                })

                results["failed"].append({
                    "artifact_id": artifact_id,
                    "artifact_type": artifact_type,
                    "error": "Internal server error",
                })

        self.db.commit()

        # Check if all artifacts are processed
        pending_count = self.db.execute(text("""
            SELECT COUNT(*) FROM call_artifacts
            WHERE session_id = :session_id AND approval_status = 'pending'
        """), {"session_id": session_id}).scalar()

        if pending_count == 0:
            self.update_session(session_id, status='completed')

        self._log_event(session_id, 'artifacts_executed', {
            'executed_count': len(results["executed"]),
            'failed_count': len(results["failed"]),
        })

        return results

    async def _execute_artifact(
        self,
        artifact_id: str,
        artifact_type: str,
        title: str,
        content: str,
        structured_data: Dict,
        metadata: Dict,
        session: Dict,
        user_id: str,
    ) -> Optional[str]:
        """Execute a single artifact and create the corresponding entity."""
        if artifact_type == 'task':
            return await self._create_task(title, content, structured_data, session, user_id)
        elif artifact_type == 'document_request':
            return await self._create_document_request(title, content, structured_data, session, user_id)
        elif artifact_type == 'intake_field':
            return await self._apply_intake_field(artifact_id, structured_data, session, user_id)
        elif artifact_type == 'risk_flag':
            return await self._create_loan_condition(artifact_id, structured_data, session, user_id)
        elif artifact_type == 'scheduled_appointment':
            return await self._create_calendar_event(title, content, structured_data, session, user_id)
        elif artifact_type == 'calendar_action':
            return await self._execute_calendar_action(title, content, structured_data, session, user_id)
        elif artifact_type == 'follow_up_call':
            return await self._create_follow_up_reminder(title, content, structured_data, session, user_id)
        elif artifact_type == 'follow_up_draft':
            return await self._create_email_draft(title, content, structured_data, session, user_id)
        else:
            # Non-actionable artifacts (summary, uw_note, marketing content, etc.)
            return None

    async def _create_calendar_event(
        self,
        title: str,
        content: str,
        structured_data: Dict,
        session: Dict,
        user_id: str,
    ) -> str:
        """Create a calendar event from a scheduled_appointment artifact.

        Uses SmartSchedulerService for LO auto-assignment and availability checking.
        Falls back to raw SQL INSERT if the scheduler service fails.
        """
        # Parse appointment details
        appointment_type = structured_data.get('appointment_type', 'general_meeting')
        proposed_datetime = structured_data.get('proposed_datetime')
        duration_minutes = structured_data.get('duration_minutes', 30)
        participants = structured_data.get('participants', [])
        meeting_type = structured_data.get('meeting_type', 'phone')

        # Direct ORM booking — replaces deprecated SmartSchedulerService
        try:
            from services.smart_scheduler_service import ScheduledAppointment, AppointmentStatus

            # Resolve contact info from lead/loan
            contact_name = structured_data.get('contact_name', '')
            contact_email = structured_data.get('contact_email', '')
            contact_phone = structured_data.get('contact_phone', '')
            contact_id = None

            lead_id = session.get('lead_id')
            if lead_id and (not contact_name or not contact_email):
                lead_row = self.db.execute(text(
                    "SELECT id, first_name, last_name, email, phone FROM leads WHERE id = :lid"
                ), {"lid": lead_id}).fetchone()
                if lead_row:
                    contact_id = lead_row[0]
                    contact_name = contact_name or f"{lead_row[1] or ''} {lead_row[2] or ''}".strip()
                    contact_email = contact_email or (lead_row[3] or '')
                    contact_phone = contact_phone or (lead_row[4] or '')

            # Parse proposed_datetime to a datetime object if it's a string
            if isinstance(proposed_datetime, str):
                from dateutil.parser import parse as parse_dt
                appointment_time = parse_dt(proposed_datetime)
            elif isinstance(proposed_datetime, datetime):
                appointment_time = proposed_datetime
            else:
                raise ValueError(f"Cannot parse proposed_datetime: {proposed_datetime}")

            end_time = appointment_time + timedelta(minutes=duration_minutes)
            appt_id = f"APPT-{str(uuid.uuid4())[:8].upper()}"

            lo_id = structured_data.get('loan_officer_id')
            org_id = session.get('organization_id')

            appointment = ScheduledAppointment(
                appointment_id=appt_id,
                loan_officer_id=lo_id,
                contact_id=contact_id,
                contact_name=contact_name or 'Unknown',
                contact_email=contact_email or '',
                contact_phone=contact_phone,
                appointment_type=appointment_type,
                start_time=appointment_time,
                end_time=end_time,
                duration_minutes=duration_minutes,
                status=AppointmentStatus.SCHEDULED.value,
                notes=content,
                conversation_id=session.get('id'),
                booked_via="call_monitoring",
                organization_id=org_id,
            )
            self.db.add(appointment)
            self.db.commit()

            logger.info(f"Direct ORM booked appointment {appt_id} for LO {lo_id} (org {org_id})")
            return appt_id

        except Exception as e:
            logger.warning(f"Direct ORM booking failed ({e}). Falling back to raw calendar_events INSERT.")

        # Fallback: raw SQL INSERT into calendar_events
        event_id = str(uuid.uuid4())

        self.db.execute(text("""
            INSERT INTO calendar_events (
                id, title, description, event_type, start_time, duration_minutes,
                meeting_type, participants, loan_id, lead_id,
                created_by, source, source_id, status
            ) VALUES (
                :id, :title, :description, :event_type, :start_time, :duration_minutes,
                :meeting_type, :participants, :loan_id, :lead_id,
                :created_by, 'call_monitoring', :source_id, 'scheduled'
            )
        """), {
            "id": event_id,
            "title": title,
            "description": content,
            "event_type": appointment_type,
            "start_time": proposed_datetime,
            "duration_minutes": duration_minutes,
            "meeting_type": meeting_type,
            "participants": json.dumps(participants),
            "loan_id": session.get('loan_id'),
            "lead_id": session.get('lead_id'),
            "created_by": user_id,
            "source_id": session.get('id'),
        })

        return event_id

    async def _execute_calendar_action(
        self,
        title: str,
        content: str,
        structured_data: Dict,
        session: Dict,
        user_id: str,
    ) -> Optional[str]:
        """Execute a calendar action (send invite, block time, etc.)."""
        action_type = structured_data.get('action_type')
        assign_to = structured_data.get('assign_to', 'PA')

        # If assigned to PA, create a task for them
        if assign_to == 'PA':
            return await self._create_pa_task(
                title=f"Calendar: {title}",
                content=content,
                session=session,
                user_id=user_id,
            )

        # For auto actions, log and return
        # (In a real implementation, this would integrate with calendar APIs)
        return None

    async def _create_follow_up_reminder(
        self,
        title: str,
        content: str,
        structured_data: Dict,
        session: Dict,
        user_id: str,
    ) -> str:
        """Create a follow-up reminder/task."""
        reminder_id = str(uuid.uuid4())

        trigger = structured_data.get('trigger', '')
        action = structured_data.get('action', '')
        suggested_timing = structured_data.get('suggested_timing', '')

        self.db.execute(text("""
            INSERT INTO tasks (
                id, title, description, loan_id, lead_id, assigned_to,
                created_by, status, priority, task_type, source, source_id
            ) VALUES (
                :id, :title, :description, :loan_id, :lead_id, :assigned_to,
                :created_by, 'open', 'medium', 'follow_up', 'call_monitoring', :source_id
            )
        """), {
            "id": reminder_id,
            "title": title,
            "description": f"Trigger: {trigger}\n\nAction: {action}\n\nTiming: {suggested_timing}\n\n{content}",
            "loan_id": session.get('loan_id'),
            "lead_id": session.get('lead_id'),
            "assigned_to": session.get('user_id'),
            "created_by": user_id,
            "source_id": session.get('id'),
        })

        return reminder_id

    async def _create_email_draft(
        self,
        title: str,
        content: str,
        structured_data: Dict,
        session: Dict,
        user_id: str,
    ) -> str:
        """Create an email draft from a follow_up_draft artifact."""
        draft_id = str(uuid.uuid4())

        # Resolve recipient info from lead
        recipient_email = structured_data.get('recipient_email', '')
        recipient_name = structured_data.get('recipient_name', '')

        lead_id = session.get('lead_id')
        if lead_id and (not recipient_email or not recipient_name):
            lead_row = self.db.execute(text(
                "SELECT first_name, last_name, email FROM leads WHERE id = :lid"
            ), {"lid": lead_id}).fetchone()
            if lead_row:
                recipient_name = recipient_name or f"{lead_row[0] or ''} {lead_row[1] or ''}".strip()
                recipient_email = recipient_email or (lead_row[2] or '')

        subject = structured_data.get('subject', title)
        body_html = structured_data.get('body_html', '')
        body_text = structured_data.get('body_text', content)

        self.db.execute(text("""
            INSERT INTO email_drafts (
                user_id, lead_id, loan_id, recipient_email, recipient_name,
                subject, body_html, body_text, source_type, source_id,
                status, created_at, updated_at
            ) VALUES (
                :user_id, :lead_id, :loan_id, :recipient_email, :recipient_name,
                :subject, :body_html, :body_text, 'call_recording', :source_id,
                'draft', NOW(), NOW()
            )
        """), {
            "user_id": session.get('user_id') or user_id,
            "lead_id": lead_id,
            "loan_id": session.get('loan_id'),
            "recipient_email": recipient_email,
            "recipient_name": recipient_name,
            "subject": subject,
            "body_html": body_html,
            "body_text": body_text,
            "source_id": session.get('id'),
        })

        return draft_id

    async def _create_pa_task(
        self,
        title: str,
        content: str,
        session: Dict,
        user_id: str,
    ) -> Optional[str]:
        """Create a task assigned to the Production Assistant."""
        # Find PA for this LO
        lo_id = session.get('user_id')
        if not lo_id:
            return None

        pa_data = self.db.execute(text("""
            SELECT u.id
            FROM users u
            JOIN user_assignments ua ON ua.assistant_id = u.id
            WHERE ua.loan_officer_id = :lo_id AND ua.role = 'production_assistant'
            LIMIT 1
        """), {"lo_id": lo_id}).fetchone()

        pa_id = str(pa_data[0]) if pa_data else lo_id  # Fallback to LO if no PA

        task_id = str(uuid.uuid4())

        self.db.execute(text("""
            INSERT INTO tasks (
                id, title, description, loan_id, lead_id, assigned_to,
                created_by, status, priority, task_type, source, source_id
            ) VALUES (
                :id, :title, :description, :loan_id, :lead_id, :assigned_to,
                :created_by, 'open', 'high', 'scheduling', 'call_monitoring', :source_id
            )
        """), {
            "id": task_id,
            "title": title,
            "description": content,
            "loan_id": session.get('loan_id'),
            "lead_id": session.get('lead_id'),
            "assigned_to": pa_id,
            "created_by": user_id,
            "source_id": session.get('id'),
        })

        return task_id

    async def _create_task(
        self,
        title: str,
        content: str,
        structured_data: Dict,
        session: Dict,
        user_id: str,
    ) -> str:
        """Create a task from an artifact."""
        task_id = str(uuid.uuid4())

        self.db.execute(text("""
            INSERT INTO tasks (
                id, title, description, loan_id, lead_id, assigned_to,
                created_by, status, priority, source, source_id
            ) VALUES (
                :id, :title, :description, :loan_id, :lead_id, :assigned_to,
                :created_by, 'open', :priority, 'call_monitoring', :source_id
            )
        """), {
            "id": task_id,
            "title": title,
            "description": content,
            "loan_id": session.get('loan_id'),
            "lead_id": session.get('lead_id'),
            "assigned_to": structured_data.get('assigned_to') or session.get('user_id'),
            "created_by": user_id,
            "priority": structured_data.get('priority', 'medium'),
            "source_id": session.get('id'),
        })

        return task_id

    async def _create_document_request(
        self,
        title: str,
        content: str,
        structured_data: Dict,
        session: Dict,
        user_id: str,
    ) -> str:
        """Create a document request from an artifact."""
        request_id = str(uuid.uuid4())

        # Create in smart_docs_requests or similar table
        self.db.execute(text("""
            INSERT INTO smart_docs_requests (
                id, loan_id, lead_id, document_type, description,
                status, requested_by, source, source_id
            ) VALUES (
                :id, :loan_id, :lead_id, :doc_type, :description,
                'requested', :requested_by, 'call_monitoring', :source_id
            )
        """), {
            "id": request_id,
            "loan_id": session.get('loan_id'),
            "lead_id": session.get('lead_id'),
            "doc_type": structured_data.get('document_type') or title,
            "description": content,
            "requested_by": user_id,
            "source_id": session.get('id'),
        })

        return request_id

    async def _apply_intake_field(
        self,
        artifact_id: str,
        structured_data: Dict,
        session: Dict,
        user_id: str,
    ) -> Optional[str]:
        """Apply an intake field update."""
        # Get the intake field update record
        field_update = self.db.execute(text("""
            SELECT id, entity_type, entity_id, field_path, proposed_value
            FROM intake_field_updates
            WHERE artifact_id = :artifact_id
        """), {"artifact_id": artifact_id}).fetchone()

        if not field_update:
            return None

        entity_type = field_update[1]
        entity_id = str(field_update[2])
        field_path = field_update[3]
        proposed_value = field_update[4]

        # Apply the update to the entity
        # This is simplified - real implementation would handle JSON paths properly
        if entity_type == 'loan' and field_path:
            self.db.execute(text(f"""
                UPDATE loans SET {field_path} = :value WHERE id = :id
            """), {"id": entity_id, "value": proposed_value})
        elif entity_type == 'lead' and field_path:
            self.db.execute(text(f"""
                UPDATE leads SET {field_path} = :value WHERE id = :id
            """), {"id": entity_id, "value": proposed_value})

        # Update intake field status
        self.db.execute(text("""
            UPDATE intake_field_updates
            SET status = 'applied', applied_by = :user_id, applied_at = NOW()
            WHERE id = :id
        """), {"id": str(field_update[0]), "user_id": user_id})

        return str(field_update[0])

    async def _create_loan_condition(
        self,
        artifact_id: str,
        structured_data: Dict,
        session: Dict,
        user_id: str,
    ) -> Optional[str]:
        """Create a loan condition from a risk flag."""
        if not session.get('loan_id'):
            return None

        condition_id = str(uuid.uuid4())

        # Get risk flag details
        risk_flag = self.db.execute(text("""
            SELECT id, title, description, risk_category, severity, condition_type
            FROM call_risk_flags
            WHERE artifact_id = :artifact_id
        """), {"artifact_id": artifact_id}).fetchone()

        if not risk_flag:
            return None

        # Create loan condition
        self.db.execute(text("""
            INSERT INTO loan_conditions (
                id, loan_id, condition_type, category, description,
                status, priority, created_by, source, source_id
            ) VALUES (
                :id, :loan_id, :condition_type, :category, :description,
                'open', :priority, :created_by, 'call_monitoring', :source_id
            )
        """), {
            "id": condition_id,
            "loan_id": session.get('loan_id'),
            "condition_type": risk_flag[5] or 'prior_to_docs',
            "category": risk_flag[3],
            "description": f"{risk_flag[1]}: {risk_flag[2]}",
            "priority": 'high' if risk_flag[4] in ('high', 'critical') else 'medium',
            "created_by": user_id,
            "source_id": session.get('id'),
        })

        # Update risk flag with condition link
        self.db.execute(text("""
            UPDATE call_risk_flags SET condition_id = :condition_id WHERE id = :id
        """), {"id": str(risk_flag[0]), "condition_id": condition_id})

        return condition_id

    # =========================================================================
    # REVIEW SCREEN
    # =========================================================================

    def get_review_data(self, session_id: str) -> Dict[str, Any]:
        """Get all data needed for the review screen."""
        session = self.get_session(session_id)
        if not session:
            return None

        # Get participants
        participants = self.db.execute(text("""
            SELECT id, role, name, phone, email, speaker_label, talk_time_seconds
            FROM call_participants
            WHERE session_id = :session_id
        """), {"session_id": session_id}).fetchall()

        # Get agent runs
        runs = self.db.execute(text("""
            SELECT id, agent_type, status, artifacts, tokens_used,
                   processing_time_ms, started_at, completed_at
            FROM agent_runs
            WHERE session_id = :session_id
        """), {"session_id": session_id}).fetchall()

        # Get artifacts
        artifacts = self.get_artifacts(session_id)

        # Count approvals
        pending_count = len([a for a in artifacts if a['approval_status'] == 'pending'])
        auto_approved_count = len([a for a in artifacts if a['approval_status'] == 'auto_approved'])

        # Get summary artifact
        summary = next((a for a in artifacts if a['artifact_type'] == 'summary'), None)

        return {
            "session": session,
            "participants": [
                {
                    "id": str(p[0]),
                    "role": p[1],
                    "name": p[2],
                    "phone": p[3],
                    "email": p[4],
                    "speaker_label": p[5],
                    "talk_time_seconds": p[6],
                }
                for p in participants
            ],
            "agent_runs": [
                {
                    "id": str(r[0]),
                    "agent_type": r[1],
                    "status": r[2],
                    "artifacts": r[3] or [],
                    "tokens_used": r[4],
                    "processing_time_ms": r[5],
                    "started_at": r[6].isoformat() if r[6] else None,
                    "completed_at": r[7].isoformat() if r[7] else None,
                }
                for r in runs
            ],
            "artifacts": artifacts,
            "transcript": session.get('full_transcript'),
            "summary": summary.get('structured_data') if summary else None,
            "pending_approvals": pending_count,
            "auto_approved": auto_approved_count,
        }

    # =========================================================================
    # EVENT LOGGING
    # =========================================================================

    def _log_event(
        self,
        session_id: str,
        event_type: str,
        payload: Dict[str, Any],
        run_id: Optional[str] = None,
        agent_type: Optional[str] = None,
        transcript_timestamp_ms: Optional[int] = None,
    ):
        """Log an event to the audit log with PII redaction."""
        redacted = _redact_payload(payload)
        self.db.execute(text("""
            INSERT INTO agent_events (
                session_id, run_id, event_type, agent_type, payload, transcript_timestamp_ms
            ) VALUES (
                :session_id, :run_id, :event_type, :agent_type, :payload, :timestamp_ms
            )
        """), {
            "session_id": session_id,
            "run_id": run_id,
            "event_type": event_type,
            "agent_type": agent_type,
            "payload": json.dumps(redacted),
            "timestamp_ms": transcript_timestamp_ms,
        })

    # =========================================================================
    # ADDITIONAL METHODS FOR API ROUTES
    # =========================================================================

    async def add_participant(
        self,
        session_id: str,
        role: str,
        name: Optional[str] = None,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        speaker_label: Optional[str] = None,
        contact_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Add a participant to a call session."""
        participant_id = str(uuid.uuid4())
        now = datetime.utcnow()

        self.db.execute(text("""
            INSERT INTO call_participants (
                id, session_id, role, name, phone, email,
                speaker_label, contact_id, user_id, joined_at
            ) VALUES (
                :id, :session_id, :role, :name, :phone, :email,
                :speaker_label, :contact_id, :user_id, :joined_at
            )
        """), {
            "id": participant_id,
            "session_id": session_id,
            "role": role,
            "name": name,
            "phone": phone,
            "email": email,
            "speaker_label": speaker_label,
            "contact_id": contact_id,
            "user_id": user_id,
            "joined_at": now,
        })

        # Also update session participants JSON
        self.db.execute(text("""
            UPDATE call_sessions
            SET participants = COALESCE(participants, '[]'::jsonb) || :participant::jsonb,
                updated_at = NOW()
            WHERE id = :session_id
        """), {
            "session_id": session_id,
            "participant": json.dumps([{
                "id": participant_id,
                "role": role,
                "name": name,
                "speaker_label": speaker_label,
            }]),
        })

        self.db.commit()

        self._log_event(session_id, 'participant_added', {
            'participant_id': participant_id,
            'role': role,
            'name': name,
        })

        # Return a simple object-like dict
        class ParticipantResult:
            def __init__(self, data):
                self.id = data['id']
                self.session_id = data['session_id']
                self.role = data['role']
                self.name = data['name']

        return ParticipantResult({
            "id": participant_id,
            "session_id": session_id,
            "role": role,
            "name": name,
        })

    async def reject_artifacts(
        self,
        session_id: str,
        artifact_ids: List[str],
        user_id: str,
        rejection_reason: Optional[str] = None,
    ) -> int:
        """Reject artifacts."""
        result = await self.approve_artifacts(
            session_id=str(session_id),
            artifact_ids=[str(aid) for aid in artifact_ids],
            user_id=str(user_id),
            action='reject',
            rejection_reason=rejection_reason,
        )
        return result.get('count', 0)
