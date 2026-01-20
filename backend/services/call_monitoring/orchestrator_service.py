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
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import uuid
import json

from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)


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


class CallMonitoringOrchestrator:
    """
    Central orchestrator for the call monitoring AI system.

    Coordinates three parallel AI agents:
    - Scribe: Summary, action items, follow-up drafts
    - Junior LO: Pricing scenarios, doc requests, intake fields
    - Underwriter: Risk flags, conditions, compliance checks
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

        self._agents = {
            'scribe': ScribeAgent(self.db),
            'junior_lo': JuniorLOAgent(self.db),
            'underwriter': UnderwriterAgent(self.db),
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

        self._log_event(session_id, 'processing_started', {
            'trigger': trigger,
            'agents': agent_types or ['scribe', 'junior_lo', 'underwriter'],
        })

        # Determine which agents to run
        agents_to_run = agent_types or ['scribe', 'junior_lo', 'underwriter']

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
            """), {"id": run_id, "error": str(e)})
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
        """Enrich context with loan/lead data."""
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

        return context

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
        # Auto-approve rules
        auto_approve_types = {'summary', 'uw_note'}

        if artifact_type in auto_approve_types:
            confidence = item.get('confidence', 0)
            if confidence and confidence >= 0.9:
                return False

        # Always require approval for
        always_approve_types = {'task', 'document_request', 'intake_field', 'risk_flag'}
        if artifact_type in always_approve_types:
            return True

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
            INSERT INTO risk_flags (
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
                    "result": json.dumps({"error": str(e)}),
                })

                results["failed"].append({
                    "artifact_id": artifact_id,
                    "artifact_type": artifact_type,
                    "error": str(e),
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
        else:
            # Non-actionable artifacts (summary, uw_note, etc.)
            return None

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
            FROM risk_flags
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
            UPDATE risk_flags SET condition_id = :condition_id WHERE id = :id
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
        """Log an event to the audit log."""
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
            "payload": json.dumps(payload),
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
