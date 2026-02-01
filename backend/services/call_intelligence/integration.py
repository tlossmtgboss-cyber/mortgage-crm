"""
Call Intelligence Integration

Integrates Call Intelligence with existing call infrastructure (Retell, Vapi, Twilio).
Automatically processes call transcripts when calls end.
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any
import asyncio

from sqlalchemy.orm import Session
from sqlalchemy import text

from .processor import CallIntelligenceProcessor
from .data_contracts import (
    CallIntelligenceRequest,
    CallIntelligenceResponse,
    CallType,
)
from .pii_utils import mask_pii_for_logging
from services.application_engine import (
    ApplicationEngineOrchestrator,
    ApplicationAuditRequest,
    CallTranscriptData,
)

logger = logging.getLogger(__name__)


class CallIntelligenceIntegration:
    """
    Integration layer that connects Call Intelligence to the call infrastructure.

    Handles:
    - Processing call transcripts after calls end
    - Triggering Application Engine audits
    - Saving results to database
    - Creating tasks in the task system
    """

    def __init__(self, db_session: Session):
        self.db = db_session
        self.ci_processor = CallIntelligenceProcessor(db_session)
        self.app_engine = ApplicationEngineOrchestrator(db_session)

    async def process_completed_call(
        self,
        call_id: str,
        loan_id: Optional[int],
        organization_id: int,
        transcript: str,
        call_type: str = "initial_intake",
        call_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Process a completed call through Call Intelligence and Application Engine.

        This is the main entry point called after a call ends.

        Args:
            call_id: Unique call identifier (required, max 255 chars)
            loan_id: Associated loan ID (may be None for new leads)
            organization_id: Organization ID (required, must be positive)
            transcript: Full call transcript (required, max 500KB)
            call_type: Type of call (initial_intake, follow_up, etc.)
            call_metadata: Additional call metadata

        Returns:
            Dict with processing results

        Raises:
            ValueError: If required parameters are invalid
        """
        # Input validation
        if not call_id or not isinstance(call_id, str):
            return {
                "success": False,
                "stage": "validation",
                "error": "call_id is required and must be a non-empty string",
            }

        if len(call_id) > 255:
            return {
                "success": False,
                "stage": "validation",
                "error": "call_id exceeds maximum length of 255 characters",
            }

        if not isinstance(organization_id, int) or organization_id <= 0:
            return {
                "success": False,
                "stage": "validation",
                "error": "organization_id must be a positive integer",
            }

        if loan_id is not None and (not isinstance(loan_id, int) or loan_id <= 0):
            return {
                "success": False,
                "stage": "validation",
                "error": "loan_id must be a positive integer or None",
            }

        if not transcript or not isinstance(transcript, str):
            return {
                "success": False,
                "stage": "validation",
                "error": "transcript is required and must be a non-empty string",
            }

        # Limit transcript size to prevent memory issues (500KB)
        max_transcript_size = 500 * 1024
        if len(transcript) > max_transcript_size:
            return {
                "success": False,
                "stage": "validation",
                "error": f"transcript exceeds maximum size of {max_transcript_size} bytes",
            }

        logger.info(f"Processing completed call: {call_id}")
        metadata = call_metadata or {}

        try:
            # Step 1: Run Call Intelligence extraction
            ci_request = CallIntelligenceRequest(
                call_id=call_id,
                loan_id=loan_id,
                organization_id=organization_id,
                transcript=transcript,
            )

            ci_response = await self.ci_processor.process_transcript(ci_request)

            if not ci_response.success:
                # Mask PII in error messages before logging
                safe_errors = [mask_pii_for_logging(str(e)) for e in ci_response.errors]
                logger.warning(f"Call Intelligence failed for {call_id}: {safe_errors}")
                return {
                    "success": False,
                    "stage": "call_intelligence",
                    "errors": ci_response.errors,
                }

            # Step 2: If loan_id exists, run Application Engine audit
            audit_response = None
            if loan_id:
                call_data = CallTranscriptData(
                    call_id=call_id,
                    call_type=call_type,
                    identity_extractions=ci_response.identity_extractions,
                    address_extractions=ci_response.address_extractions,
                    employment_extractions=ci_response.employment_extractions,
                    income_extractions=ci_response.income_extractions,
                    assets_extractions=ci_response.assets_extractions,
                    liabilities_extractions=ci_response.liabilities_extractions,
                    reo_extractions=ci_response.reo_extractions,
                    declarations_extractions=ci_response.declarations_extractions,
                )

                audit_request = ApplicationAuditRequest(
                    loan_id=loan_id,
                    organization_id=organization_id,
                    call_data=call_data,
                    loan_type=metadata.get("loan_type"),
                    generate_tasks=True,
                    include_guideline_recommendations=True,
                )

                audit_response = self.app_engine.audit(audit_request)

                # Step 3: Create tasks in the system
                if audit_response.all_tasks:
                    await self._create_tasks(
                        loan_id=loan_id,
                        organization_id=organization_id,
                        tasks=audit_response.all_tasks,
                    )

            # Step 4: Save call intelligence results
            await self._save_call_results(
                call_id=call_id,
                loan_id=loan_id,
                organization_id=organization_id,
                ci_response=ci_response,
                audit_response=audit_response,
                metadata=metadata,
            )

            return {
                "success": True,
                "call_id": call_id,
                "loan_id": loan_id,
                "extractions_count": ci_response.total_extractions,
                "high_confidence_count": ci_response.high_confidence_count,
                "application_status": audit_response.overall_status.value if audit_response else None,
                "application_completion": audit_response.overall_completion if audit_response else None,
                "tasks_created": len(audit_response.all_tasks) if audit_response else 0,
            }

        except Exception as e:
            # Mask PII in exception message before logging
            safe_error = mask_pii_for_logging(str(e))
            logger.exception(f"Error processing call {call_id}: {safe_error}")
            return {
                "success": False,
                "stage": "processing",
                "error": safe_error,
            }

    async def _create_tasks(
        self,
        loan_id: int,
        organization_id: int,
        tasks: list,
    ) -> None:
        """Create tasks in the task system."""
        try:
            from datetime import timedelta

            for task in tasks:
                # Calculate due date
                due_date = datetime.utcnow() + timedelta(days=task.days_until_due)

                # Map assignee to user
                assigned_to_id = None
                if task.assignee.value == "pa":
                    # Get production assistant for the loan
                    result = self.db.execute(
                        text("""
                            SELECT processor_id FROM loans WHERE id = :loan_id
                        """),
                        {"loan_id": loan_id}
                    ).fetchone()
                    if result:
                        assigned_to_id = result[0]
                elif task.assignee.value == "lo":
                    # Get loan officer for the loan
                    result = self.db.execute(
                        text("""
                            SELECT loan_officer_id FROM loans WHERE id = :loan_id
                        """),
                        {"loan_id": loan_id}
                    ).fetchone()
                    if result:
                        assigned_to_id = result[0]

                # Create task
                self.db.execute(
                    text("""
                        INSERT INTO tasks
                        (organization_id, title, description, status, priority,
                         due_date, loan_id, owner_id, related_type, created_at, updated_at)
                        VALUES
                        (:org_id, :title, :description, 'pending', :priority,
                         :due_date, :loan_id, :owner_id, :related_type, :created_at, :updated_at)
                    """),
                    {
                        "org_id": organization_id,
                        "title": task.title,
                        "description": task.description,
                        "priority": task.priority.value,
                        "due_date": due_date,
                        "loan_id": loan_id,
                        "owner_id": assigned_to_id,
                        "related_type": f"application_engine_{task.module.value}",
                        "created_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow(),
                    }
                )

            self.db.commit()
            logger.info(f"Created {len(tasks)} tasks for loan {loan_id}")

        except Exception as e:
            safe_error = mask_pii_for_logging(str(e))
            logger.exception(f"Error creating tasks for loan {loan_id}: {safe_error}")
            try:
                self.db.rollback()
            except Exception:
                pass  # Rollback failed, but we already logged the original error

    async def _save_call_results(
        self,
        call_id: str,
        loan_id: Optional[int],
        organization_id: int,
        ci_response: CallIntelligenceResponse,
        audit_response,
        metadata: Dict[str, Any],
    ) -> None:
        """Save call processing results to database."""
        try:
            import json

            # Save to call_intelligence_results table
            self.db.execute(
                text("""
                    INSERT INTO call_intelligence_results
                    (call_id, loan_id, organization_id, extractions,
                     total_extractions, high_confidence_count, low_confidence_count,
                     processing_time_ms, application_status, application_completion,
                     created_at)
                    VALUES
                    (:call_id, :loan_id, :org_id, :extractions,
                     :total, :high_conf, :low_conf,
                     :processing_time, :app_status, :app_completion,
                     :created_at)
                    ON CONFLICT (call_id) DO UPDATE SET
                        extractions = :extractions,
                        total_extractions = :total,
                        high_confidence_count = :high_conf,
                        low_confidence_count = :low_conf,
                        application_status = :app_status,
                        application_completion = :app_completion,
                        updated_at = :created_at
                """),
                {
                    "call_id": call_id,
                    "loan_id": loan_id,
                    "org_id": organization_id,
                    "extractions": json.dumps(ci_response.to_application_engine_format()),
                    "total": ci_response.total_extractions,
                    "high_conf": ci_response.high_confidence_count,
                    "low_conf": ci_response.low_confidence_count,
                    "processing_time": ci_response.processing_time_ms,
                    "app_status": audit_response.overall_status.value if audit_response else None,
                    "app_completion": audit_response.overall_completion if audit_response else None,
                    "created_at": datetime.utcnow(),
                }
            )
            self.db.commit()

        except Exception as e:
            safe_error = mask_pii_for_logging(str(e))
            logger.warning(f"Error saving call results for {call_id}: {safe_error}")
            try:
                self.db.rollback()
            except Exception:
                pass  # Rollback failed, but we already logged the original error


# =============================================================================
# Webhook Handlers for Retell/Vapi Integration
# =============================================================================

async def handle_retell_call_ended(
    db: Session,
    call_id: str,
    call_data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Handle Retell call ended webhook.

    Called when a Retell AI call ends. Processes the transcript through
    Call Intelligence and Application Engine.
    """
    transcript = call_data.get("transcript", "")
    if not transcript:
        logger.warning(f"No transcript in Retell call {call_id}")
        return {"success": False, "error": "No transcript"}

    # Extract loan_id and org_id from call metadata
    metadata = call_data.get("call_analysis", {}).get("custom_analysis_data", {})
    loan_id = metadata.get("loan_id") or call_data.get("metadata", {}).get("loan_id")
    org_id = metadata.get("organization_id") or call_data.get("metadata", {}).get("organization_id")

    if not org_id:
        logger.warning(f"No organization_id in Retell call {call_id}")
        return {"success": False, "error": "No organization_id"}

    integration = CallIntelligenceIntegration(db)

    return await integration.process_completed_call(
        call_id=call_id,
        loan_id=int(loan_id) if loan_id else None,
        organization_id=int(org_id),
        transcript=transcript,
        call_type="initial_intake",
        call_metadata={
            "source": "retell",
            "duration": call_data.get("duration_ms"),
            "agent_id": call_data.get("agent_id"),
        },
    )


async def handle_vapi_call_ended(
    db: Session,
    call_id: str,
    call_data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Handle Vapi call ended webhook.

    Called when a Vapi AI call ends. Processes the transcript through
    Call Intelligence and Application Engine.
    """
    # Vapi format: messages array contains transcript
    messages = call_data.get("messages", [])
    transcript = "\n".join([
        f"{m.get('role', 'unknown')}: {m.get('message', '')}"
        for m in messages
        if m.get('message')
    ])

    if not transcript:
        logger.warning(f"No transcript in Vapi call {call_id}")
        return {"success": False, "error": "No transcript"}

    # Extract metadata
    metadata = call_data.get("assistant", {}).get("metadata", {})
    loan_id = metadata.get("loan_id")
    org_id = metadata.get("organization_id")

    if not org_id:
        logger.warning(f"No organization_id in Vapi call {call_id}")
        return {"success": False, "error": "No organization_id"}

    integration = CallIntelligenceIntegration(db)

    return await integration.process_completed_call(
        call_id=call_id,
        loan_id=int(loan_id) if loan_id else None,
        organization_id=int(org_id),
        transcript=transcript,
        call_type="initial_intake",
        call_metadata={
            "source": "vapi",
            "duration": call_data.get("duration"),
            "assistant_id": call_data.get("assistant", {}).get("id"),
        },
    )


def create_call_intelligence_tables(db: Session) -> None:
    """
    Create database tables for Call Intelligence if they don't exist.

    This should be called during application startup or migration.
    """
    try:
        # Check if table exists
        result = db.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'call_intelligence_results'
        """))

        if not result.fetchone():
            logger.info("Creating call_intelligence_results table...")
            db.execute(text("""
                CREATE TABLE call_intelligence_results (
                    id SERIAL PRIMARY KEY,
                    call_id VARCHAR(255) UNIQUE NOT NULL,
                    loan_id INTEGER REFERENCES loans(id),
                    organization_id INTEGER REFERENCES organizations(id),
                    extractions JSONB,
                    total_extractions INTEGER DEFAULT 0,
                    high_confidence_count INTEGER DEFAULT 0,
                    low_confidence_count INTEGER DEFAULT 0,
                    processing_time_ms INTEGER DEFAULT 0,
                    application_status VARCHAR(50),
                    application_completion FLOAT,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                );

                CREATE INDEX idx_ci_results_loan_id ON call_intelligence_results(loan_id);
                CREATE INDEX idx_ci_results_org_id ON call_intelligence_results(organization_id);
                CREATE INDEX idx_ci_results_created_at ON call_intelligence_results(created_at);
            """))
            db.commit()
            logger.info("call_intelligence_results table created")

        # Check for application_audit_logs table
        result = db.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'application_audit_logs'
        """))

        if not result.fetchone():
            logger.info("Creating application_audit_logs table...")
            db.execute(text("""
                CREATE TABLE application_audit_logs (
                    id SERIAL PRIMARY KEY,
                    loan_id INTEGER REFERENCES loans(id),
                    overall_status VARCHAR(50),
                    overall_completion FLOAT,
                    total_fields INTEGER DEFAULT 0,
                    complete_fields INTEGER DEFAULT 0,
                    missing_fields INTEGER DEFAULT 0,
                    tasks_generated INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT NOW()
                );

                CREATE INDEX idx_audit_logs_loan_id ON application_audit_logs(loan_id);
                CREATE INDEX idx_audit_logs_created_at ON application_audit_logs(created_at);
            """))
            db.commit()
            logger.info("application_audit_logs table created")

    except Exception as e:
        logger.exception(f"Error creating Call Intelligence tables: {e}")
        try:
            db.rollback()
        except Exception:
            pass  # Rollback failed, but we already logged the original error
