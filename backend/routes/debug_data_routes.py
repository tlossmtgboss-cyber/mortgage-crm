"""
Debug Data & Email Routes

Extracted from inline_legacy_routes.py.
Provides debug endpoints for email sync, reconciliation, Microsoft integration,
sample data creation, email testing, and Salesforce migration.
"""
from fastapi import Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timezone, timedelta
from typing import Any
import logging
import os
import asyncio
import requests
from utils.pii_mask import mask_email

from auth.dependencies import require_auth

logger = logging.getLogger(__name__)
_ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")

try:
    from routes.scheduler.constants import DEFAULT_ORGANIZER_EMAIL as _DEFAULT_ORGANIZER_EMAIL
except ImportError:
    _DEFAULT_ORGANIZER_EMAIL = os.environ.get("SCHEDULER_ORGANIZER_EMAIL", _DEFAULT_ORGANIZER_EMAIL)


def register_debug_data_routes(
    app, get_db, get_current_user, get_current_user_flexible,
    process_microsoft_email_to_dre, fetch_microsoft_emails, match_entity,
    decrypt_token=None, refresh_microsoft_token=None,
    **kwargs
):
    """Register debug data and email routes."""
    from database.models import (
        User,
        ExtractedData,
        IncomingDataEvent,
        MicrosoftOAuthToken,
        CalendarEvent,
        ReferralPartner,
        Task,
        Loan,
    )
    from schemas.core import ErrorFixRequest, MicrosoftSyncSettings
    from services.dre_helpers import get_entity_name, create_milestone_tasks

    @app.get("/api/v1/debug/email-sync-status", dependencies=[Depends(require_auth)])
    async def email_sync_status(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """
        Debug endpoint: Check email sync and reconciliation status
        """
        try:
            # Check incoming emails
            email_stats = db.execute(text("""
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN processed = true THEN 1 END) as processed,
                    COUNT(CASE WHEN processed = false THEN 1 END) as pending
                FROM incoming_data_events
                WHERE source = 'microsoft365'
            """)).fetchone()

            # Check reconciliation items
            recon_stats = db.execute(text("""
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending,
                    COUNT(CASE WHEN status = 'approved' THEN 1 END) as approved,
                    COUNT(CASE WHEN status = 'rejected' THEN 1 END) as rejected
                FROM reconciliation_items
            """)).fetchone()

            # Get recent emails
            recent_emails = db.execute(text("""
                SELECT subject, sender, received_at, processed
                FROM incoming_data_events
                WHERE source = 'microsoft365'
                ORDER BY received_at DESC
                LIMIT 5
            """)).fetchall()

            # Get recent reconciliation items
            recent_recon = db.execute(text("""
                SELECT entity_type, confidence_score, status, created_at
                FROM reconciliation_items
                ORDER BY created_at DESC
                LIMIT 5
            """)).fetchall()

            return {
                "success": True,
                "emails": {
                    "total": email_stats[0],
                    "processed": email_stats[1],
                    "pending": email_stats[2],
                    "recent": [
                        {
                            "subject": e[0],
                            "sender": e[1],
                            "received_at": e[2].isoformat() if e[2] else None,
                            "processed": e[3]
                        }
                        for e in recent_emails
                    ]
                },
                "reconciliation": {
                    "total": recon_stats[0],
                    "pending": recon_stats[1],
                    "approved": recon_stats[2],
                    "rejected": recon_stats[3],
                    "recent": [
                        {
                            "entity_type": r[0],
                            "confidence_score": float(r[1]) if r[1] else 0,
                            "status": r[2],
                            "created_at": r[3].isoformat() if r[3] else None
                        }
                        for r in recent_recon
                    ]
                }
            }
        except Exception as e:
            logger.error(f"Debug endpoint failed: {e}")
            return {
                "success": False,
                "error": "Internal server error"
            }

    @app.post("/api/v1/create-sample-tasks", dependencies=[Depends(require_auth)])
    async def create_sample_tasks(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """
        Create 5 sample reconciliation tasks from emails for testing
        """
        try:
            sample_emails = [
                {
                    "subject": "RE: Johnson Loan - Appraisal Scheduled for Next Week",
                    "sender": "appraisal@titleco.com",
                    "content": "The appraisal for the Johnson property at 123 Oak Street has been scheduled for next Tuesday at 2 PM. Loan amount: $450,000",
                    "category": "loan_update",
                    "subcategory": "appraisal_scheduled",
                    "fields": {
                        "borrower_name": {"value": "Johnson", "confidence": 0.85},
                        "property_address": {"value": "123 Oak Street", "confidence": 0.90},
                        "loan_amount": {"value": "$450,000", "confidence": 0.95}
                    }
                },
                {
                    "subject": "URGENT: Smith Closing - Title Issue Detected",
                    "sender": "title@escrow.com",
                    "content": "We've discovered a lien on the Smith property (456 Maple Avenue). Loan: $325,000. Outstanding HOA lien of $2,500",
                    "category": "loan_update",
                    "subcategory": "title_issue",
                    "fields": {
                        "borrower_name": {"value": "Smith", "confidence": 0.92},
                        "property_address": {"value": "456 Maple Avenue", "confidence": 0.95},
                        "loan_amount": {"value": "$325,000", "confidence": 0.98}
                    }
                },
                {
                    "subject": "Williams Pre-Approval Request - $600K Budget",
                    "sender": "sarah.williams@email.com",
                    "content": "Name: Sarah Williams, Phone: (555) 123-4567, Budget: $600,000, Property Type: Single Family Home",
                    "category": "lead_update",
                    "subcategory": "new_lead",
                    "fields": {
                        "borrower_name": {"value": "Sarah Williams", "confidence": 0.98},
                        "phone": {"value": "(555) 123-4567", "confidence": 0.95},
                        "loan_amount": {"value": "$600,000", "confidence": 0.92}
                    }
                },
                {
                    "subject": "RE: Martinez Loan - Rate Lock Expiring Soon",
                    "sender": "processor@lendingco.com",
                    "content": "Borrower: Carlos Martinez, Property: 789 Pine Boulevard, Loan: $280,000, Rate: 6.75%, Expires: December 1st",
                    "category": "loan_update",
                    "subcategory": "rate_lock_expiring",
                    "fields": {
                        "borrower_name": {"value": "Carlos Martinez", "confidence": 0.96},
                        "property_address": {"value": "789 Pine Boulevard", "confidence": 0.94},
                        "loan_amount": {"value": "$280,000", "confidence": 0.97}
                    }
                },
                {
                    "subject": "Thompson Family - Clear to Close!",
                    "sender": "underwriting@mortgage.com",
                    "content": "Borrower: Michael & Jennifer Thompson, Property: 321 Birch Lane, Loan: $525,000, Closing: November 20th, Status: APPROVED",
                    "category": "loan_update",
                    "subcategory": "clear_to_close",
                    "fields": {
                        "borrower_name": {"value": "Michael & Jennifer Thompson", "confidence": 0.97},
                        "property_address": {"value": "321 Birch Lane", "confidence": 0.95},
                        "loan_amount": {"value": "$525,000", "confidence": 0.98}
                    }
                }
            ]

            created_tasks = []

            for idx, email in enumerate(sample_emails, 1):
                # Create incoming data event
                db_event = IncomingDataEvent(
                    source="microsoft365",
                    external_message_id=f"sample_task_{idx}_{datetime.now().timestamp()}",
                    raw_text=email["content"],
                    subject=email["subject"],
                    sender=email["sender"],
                    received_at=datetime.now(timezone.utc),
                    user_id=current_user.id,
                    processed=True
                )
                db.add(db_event)
                db.flush()

                # Calculate average confidence
                confidences = [field["confidence"] for field in email["fields"].values()]
                avg_confidence = sum(confidences) / len(confidences)

                # Create extracted data (reconciliation item)
                extracted = ExtractedData(
                    event_id=db_event.id,
                    category=email["category"],
                    subcategory=email["subcategory"],
                    fields=email["fields"],
                    ai_confidence=avg_confidence,
                    status="pending_review"
                )
                db.add(extracted)
                db.flush()

                created_tasks.append({
                    "event_id": db_event.id,
                    "extracted_id": extracted.id,
                    "subject": email["subject"],
                    "category": email["category"]
                })

            db.commit()

            return {
                "success": True,
                "message": f"Created {len(created_tasks)} reconciliation tasks",
                "tasks": created_tasks
            }

        except Exception as e:
            logger.error(f"Failed to create sample tasks: {e}")
            db.rollback()
            return {
                "success": False,
                "error": "Internal server error"
            }

    @app.post("/api/v1/auto-fix-error", dependencies=[Depends(require_auth)])
    async def auto_fix_error(
        request: ErrorFixRequest,
        current_user: User = Depends(get_current_user)
    ):
        """
        AI-powered error analysis and fix recommendations
        Uses Claude AI to analyze frontend errors and provide fix suggestions
        """
        try:
            import json
            import anthropic
            anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")

            if not anthropic_api_key:
                logger.warning("Anthropic API key not configured for error fix")
                return {
                    "success": False,
                    "message": "AI error analysis is not configured. Please set ANTHROPIC_API_KEY.",
                    "analysis": None
                }

            # Initialize Anthropic client
            client = anthropic.Anthropic(api_key=anthropic_api_key)

            # Build the analysis prompt
            prompt = f"""You are an expert software engineer debugging a React application error.

    Error Details:
    - Error Message: {request.error_message}
    - URL: {request.url}
    - Attempt Number: {request.attempt_number}

    Error Stack:
    {request.error_stack if request.error_stack else "Not provided"}

    Component Stack:
    {request.component_stack if request.component_stack else "Not provided"}

    User Agent:
    {request.user_agent if request.user_agent else "Not provided"}

    Please analyze this error and provide:
    1. The root cause of the error
    2. A step-by-step fix strategy
    3. Which files are likely affected
    4. Your confidence level (High/Medium/Low)
    5. A recommendation for preventing similar errors

    Respond in JSON format with these keys:
    {{
      "root_cause": "description of what caused the error",
      "fix_strategy": "step-by-step plan to fix it",
      "files_affected": ["list", "of", "file", "paths"],
      "confidence": "High/Medium/Low",
      "recommendation": "how to prevent this in the future"
    }}"""

            # Call Claude API
            logger.info(f"Requesting error analysis from Claude for user {current_user.id}")

            message = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=2000,
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )

            # Parse the response
            response_text = message.content[0].text
            logger.info(f"Received analysis from Claude: {response_text[:200]}...")

            # Try to extract JSON from the response
            import re
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)

            if json_match:
                analysis = json.loads(json_match.group())
            else:
                # If no JSON found, structure the response manually
                analysis = {
                    "root_cause": response_text,
                    "fix_strategy": "See root cause analysis",
                    "files_affected": [],
                    "confidence": "Medium",
                    "recommendation": "Review the error analysis above"
                }

            return {
                "success": True,
                "message": "Error analysis completed successfully",
                "analysis": {
                    "root_cause": analysis.get("root_cause", "Analysis provided"),
                    "fix_strategy": analysis.get("fix_strategy", ""),
                    "files_affected": analysis.get("files_affected", []),
                    "confidence": analysis.get("confidence", "Medium"),
                    "recommendation": analysis.get("recommendation", "")
                },
                "fix_strategy": analysis.get("fix_strategy", ""),
                "files_affected": analysis.get("files_affected", []),
                "confidence": analysis.get("confidence", "Medium"),
                "recommendation": analysis.get("recommendation", "")
            }

        except Exception as e:
            logger.error(f"Error in auto_fix_error: {str(e)}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "message": "Failed to analyze error",
                "analysis": None
            }

    @app.post("/api/v1/microsoft/sync-now")
    async def sync_microsoft_emails_now(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """Manually trigger email sync from Microsoft 365"""
        try:
            # Log diagnostic info
            logger.info(f"Sync triggered by user {current_user.id}")
            logger.info(f"OpenAI API key set: {bool(os.getenv('OPENAI_API_KEY'))}")
            oauth_record = db.query(MicrosoftOAuthToken).filter(
                MicrosoftOAuthToken.user_id == current_user.id
            ).first()

            if not oauth_record:
                raise HTTPException(status_code=404, detail="Microsoft 365 not connected")

            if not oauth_record.sync_enabled:
                raise HTTPException(status_code=400, detail="Email sync is disabled")

            # Log which account/folder we're syncing from
            logger.info(f"Syncing from Microsoft account: {oauth_record.email_address}, folder: {oauth_record.sync_folder or 'Inbox'}")

            # Auto-populate known_client_emails table before sync for better identity resolution
            try:
                from sqlalchemy import text as sa_text
                # Batch-fetch leads and loans, then batch-insert (avoids N+1)
                leads = db.execute(sa_text("""
                    SELECT id, email, name FROM leads
                    WHERE email IS NOT NULL AND owner_id = :user_id
                """), {"user_id": current_user.id}).fetchall()
                lead_params = [
                    {"email": l[1].lower(), "lead_id": l[0], "name": l[2], "user_id": current_user.id}
                    for l in leads if l[1]
                ]
                if lead_params:
                    db.execute(sa_text("""
                        INSERT INTO known_client_emails (email_address, lead_id, client_name, source_type, user_id)
                        VALUES (:email, :lead_id, :name, 'lead', :user_id)
                        ON CONFLICT (email_address, user_id) DO UPDATE SET
                            lead_id = COALESCE(known_client_emails.lead_id, EXCLUDED.lead_id),
                            updated_at = CURRENT_TIMESTAMP
                    """), lead_params)

                loans = db.execute(sa_text("""
                    SELECT id, borrower_email, borrower_name FROM loans
                    WHERE borrower_email IS NOT NULL AND loan_officer_id = :user_id
                """), {"user_id": current_user.id}).fetchall()
                loan_params = [
                    {"email": l[1].lower(), "loan_id": l[0], "name": l[2], "user_id": current_user.id}
                    for l in loans if l[1]
                ]
                if loan_params:
                    db.execute(sa_text("""
                        INSERT INTO known_client_emails (email_address, loan_id, client_name, source_type, user_id)
                        VALUES (:email, :loan_id, :name, 'loan', :user_id)
                        ON CONFLICT (email_address, user_id) DO UPDATE SET
                            loan_id = COALESCE(known_client_emails.loan_id, EXCLUDED.loan_id),
                            updated_at = CURRENT_TIMESTAMP
                    """), loan_params)

                db.commit()
                logger.info(f"Auto-synced {len(leads)} leads and {len(loans)} loans to known_client_emails")
            except Exception as kce_error:
                logger.warning(f"Could not auto-sync known_client_emails: {kce_error}")
                db.rollback()

            # Fetch emails with timeout
            import asyncio
            try:
                result = await asyncio.wait_for(
                    fetch_microsoft_emails(oauth_record, db, limit=50),
                    timeout=60  # 60 second timeout for fetching emails
                )
            except asyncio.TimeoutError:
                logger.error(f"Microsoft email fetch timed out for user {current_user.id}")
                raise HTTPException(status_code=504, detail="Email fetch timed out - please try again")

            if "error" in result:
                # If token needs reauth, return specific status code so frontend can handle
                if result.get("needs_reauth"):
                    raise HTTPException(status_code=401, detail="needs_reauth")
                raise HTTPException(status_code=500, detail=result["error"])

            # Process each email through DRE with individual error handling
            emails = result.get("emails", [])
            processed_count = 0
            skipped_count = 0
            error_count = 0
            errors = []

            for idx, email_data in enumerate(emails):
                try:
                    # Process each email with a 45-second timeout
                    process_result = await asyncio.wait_for(
                        process_microsoft_email_to_dre(email_data, current_user.id, db),
                        timeout=45
                    )
                    if process_result.get("status") == "success":
                        processed_count += 1
                    elif process_result.get("status") == "skipped":
                        skipped_count += 1
                    else:
                        error_count += 1
                except asyncio.TimeoutError:
                    error_count += 1
                    subject = email_data.get("subject", "Unknown")[:50]
                    errors.append(f"Timeout processing email {idx+1}: {subject}")
                    logger.warning(f"Timeout processing email {idx+1}/{len(emails)}: {subject}")
                except Exception as e:
                    error_count += 1
                    subject = email_data.get("subject", "Unknown")[:50]
                    errors.append(f"Error processing email {idx+1}: {str(e)[:100]}")
                    logger.error(f"Error processing email {idx+1}/{len(emails)} ({subject}): {e}")
                    # Continue with next email instead of failing entire sync

            # Update last_sync_at timestamp
            oauth_record.last_sync_at = datetime.now(timezone.utc)
            db.commit()

            logger.info(f"Synced {processed_count}/{len(emails)} emails for user {current_user.id} (skipped: {skipped_count}, errors: {error_count})")

            # Build informative message
            if len(emails) == 0:
                message = f"No new emails in {oauth_record.sync_folder or 'Inbox'} from {oauth_record.email_address}"
            elif processed_count == 0 and skipped_count > 0:
                message = f"All {skipped_count} emails already synced from {oauth_record.email_address}"
            elif processed_count > 0:
                message = f"Synced {processed_count} new emails from {oauth_record.email_address}"
                if error_count > 0:
                    message += f" ({error_count} errors)"
            else:
                message = f"Synced {processed_count} emails from {oauth_record.email_address}"

            return {
                "status": "success",
                "email_account": oauth_record.email_address,
                "sync_folder": oauth_record.sync_folder or "Inbox",
                "fetched_count": len(emails),
                "processed_count": processed_count,
                "skipped_count": skipped_count,
                "error_count": error_count,
                "errors": errors[:5] if errors else [],  # Return first 5 errors
                "message": message
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Microsoft sync error: {e}")
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=500, detail="Sync error")

    @app.get("/api/v1/reconciliation/debug")
    async def debug_reconciliation(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """Debug endpoint to check email and extraction status"""
        try:
            from sqlalchemy import text

            # Count IncomingDataEvents
            events_count = db.execute(text("""
                SELECT COUNT(*) FROM incoming_data_events WHERE user_id = :user_id
            """), {"user_id": current_user.id}).scalar()

            # Count ExtractedData for user's events
            extracted_count = db.execute(text("""
                SELECT COUNT(*) FROM extracted_data ed
                JOIN incoming_data_events ide ON ed.event_id = ide.id
                WHERE ide.user_id = :user_id
            """), {"user_id": current_user.id}).scalar()

            # Get status breakdown
            status_breakdown = db.execute(text("""
                SELECT ed.status, COUNT(*) as count FROM extracted_data ed
                JOIN incoming_data_events ide ON ed.event_id = ide.id
                WHERE ide.user_id = :user_id
                GROUP BY ed.status
            """), {"user_id": current_user.id}).fetchall()

            # Get recent events
            recent_events = db.execute(text("""
                SELECT ide.id, ide.subject, ide.processed, ed.status, ed.category
                FROM incoming_data_events ide
                LEFT JOIN extracted_data ed ON ide.id = ed.event_id
                WHERE ide.user_id = :user_id
                ORDER BY ide.created_at DESC
                LIMIT 5
            """), {"user_id": current_user.id}).fetchall()

            return {
                "user_id": current_user.id,
                "incoming_events_count": events_count,
                "extracted_data_count": extracted_count,
                "status_breakdown": {row[0]: row[1] for row in status_breakdown},
                "recent_events": [
                    {"id": row[0], "subject": row[1][:50] if row[1] else None, "processed": row[2], "status": row[3], "category": row[4]}
                    for row in recent_events
                ]
            }
        except Exception as e:
            logger.error(f"Debug error: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")


    @app.get("/api/v1/debug/all-loans")
    async def debug_all_loans(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """Debug endpoint to see ALL loans in the database (bypasses permission filtering)"""
        try:
            from sqlalchemy import text

            # Get ALL loans regardless of loan_officer_id
            all_loans = db.execute(text("""
                SELECT id, loan_number, borrower_name, borrower_email, stage, loan_officer_id, created_at
                FROM loans
                ORDER BY created_at DESC
                LIMIT 50
            """)).fetchall()

            return {
                "total_loans": len(all_loans),
                "loans": [
                    {
                        "id": row[0],
                        "loan_number": row[1],
                        "borrower_name": row[2],
                        "borrower_email": row[3],
                        "stage": row[4],
                        "loan_officer_id": row[5],
                        "created_at": str(row[6]) if row[6] else None
                    }
                    for row in all_loans
                ]
            }
        except Exception as e:
            logger.error(f"Debug all loans error: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")


    @app.get("/api/v1/debug/dashboard-diagnosis")
    async def debug_dashboard_diagnosis(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """Debug endpoint to diagnose dashboard errors step by step"""
        import traceback
        from datetime import date, timedelta, datetime, timezone
        from sqlalchemy import func, extract, case, text
        from database.models import Lead, AIColleagueAction
        from database.enums import LeadStage, LoanStage

        results = {"user_id": current_user.id, "steps": []}

        try:
            # Step 1: Basic date setup
            today = date.today()
            start_of_month = today.replace(day=1)
            results["steps"].append({"step": "date_setup", "status": "ok", "today": str(today)})
        except Exception as e:
            results["steps"].append({"step": "date_setup", "status": "error", "error": "Internal server error"})
            return results

        try:
            # Step 2: User metadata
            user_metadata = current_user.user_metadata or {}
            goals = user_metadata.get('goals', {})
            results["steps"].append({"step": "user_metadata", "status": "ok", "has_goals": bool(goals)})
        except Exception as e:
            results["steps"].append({"step": "user_metadata", "status": "error", "error": "Internal server error"})
            return results

        try:
            # Step 3: Funded loans query with case statements
            funded_counts = db.query(
                func.count(case((extract('year', Loan.funded_date) == today.year, 1))).label('annual'),
                func.count(case((Loan.funded_date >= start_of_month, 1))).label('monthly')
            ).filter(
                Loan.loan_officer_id == current_user.id,
                Loan.stage == LoanStage.FUNDED
            ).first()
            results["steps"].append({"step": "funded_counts", "status": "ok", "annual": funded_counts.annual or 0})
        except Exception as e:
            results["steps"].append({"step": "funded_counts", "status": "error", "error": "Internal server error"})
            return results

        try:
            # Step 4: Lead counts query
            lead_counts = db.query(
                func.count(case((Lead.stage == LeadStage.NEW, 1))).label('new_leads'),
                func.count(case((Lead.stage == LeadStage.PRE_APPROVED, 1))).label('preapproved')
            ).filter(
                Lead.owner_id == current_user.id
            ).first()
            results["steps"].append({"step": "lead_counts", "status": "ok", "new_leads": lead_counts.new_leads or 0})
        except Exception as e:
            results["steps"].append({"step": "lead_counts", "status": "error", "error": "Internal server error"})
            return results

        try:
            # Step 5: Active loans query
            active_loans = db.query(Loan).filter(
                Loan.loan_officer_id == current_user.id,
                Loan.stage.in_([LoanStage.PROCESSING, LoanStage.UW_RECEIVED, LoanStage.CTC])
            ).all()
            results["steps"].append({"step": "active_loans", "status": "ok", "count": len(active_loans)})
        except Exception as e:
            results["steps"].append({"step": "active_loans", "status": "error", "error": "Internal server error"})
            return results

        try:
            # Step 6: Tasks query
            tasks_today = db.query(Task).filter(
                Task.owner_id == current_user.id,
                Task.status.in_(["pending", "in_progress"]),
                Task.due_date <= today + timedelta(days=1)
            ).limit(10).all()
            results["steps"].append({"step": "tasks_query", "status": "ok", "count": len(tasks_today)})
        except Exception as e:
            results["steps"].append({"step": "tasks_query", "status": "error", "error": "Internal server error"})
            return results

        try:
            # Step 7: Lead metrics with ai_score
            today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0)
            lead_metrics_query = db.query(
                func.count(Lead.id).label('total_leads'),
                func.count(case((Lead.created_at >= today_start, 1))).label('new_today'),
                func.count(case(((Lead.ai_score >= 80) & (Lead.stage.in_([LeadStage.NEW, LeadStage.ATTEMPTED_CONTACT])), 1))).label('hot_leads')
            ).filter(
                Lead.owner_id == current_user.id
            ).first()
            results["steps"].append({"step": "lead_metrics", "status": "ok", "total_leads": lead_metrics_query.total_leads or 0})
        except Exception as e:
            results["steps"].append({"step": "lead_metrics", "status": "error", "error": "Internal server error"})
            return results

        try:
            # Step 8: Referral partners query
            partners = db.query(ReferralPartner).filter(
                ReferralPartner.status == "active"
            ).limit(5).all()
            results["steps"].append({"step": "referral_partners", "status": "ok", "count": len(partners)})
        except Exception as e:
            results["steps"].append({"step": "referral_partners", "status": "error", "error": "Internal server error"})
            return results

        try:
            # Step 9: AI Colleague Actions table check
            thirty_days_ago = today - timedelta(days=30)
            ai_tasks_count = db.query(func.count(AIColleagueAction.id)).filter(
                AIColleagueAction.user_id == current_user.id,
                AIColleagueAction.created_at >= thirty_days_ago
            ).scalar() or 0
            results["steps"].append({"step": "ai_colleague_actions", "status": "ok", "count": ai_tasks_count})
        except Exception as e:
            results["steps"].append({"step": "ai_colleague_actions", "status": "error", "error": "Internal server error"})
            return results

        results["overall_status"] = "all_steps_passed"
        return results


    @app.post("/api/v1/microsoft/reprocess-emails")
    async def reprocess_unextracted_emails(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """Reprocess emails that were synced but not extracted (for fixing failed extractions)"""
        try:
            # Find all emails without extracted data for this user
            unextracted = db.execute(text("""
                SELECT ide.id, ide.subject, ide.sender, ide.raw_text, ide.raw_html, ide.received_at, ide.recipients
                FROM incoming_data_events ide
                LEFT JOIN extracted_data ed ON ide.id = ed.event_id
                WHERE ed.id IS NULL AND ide.user_id = :user_id
                ORDER BY ide.created_at DESC
            """), {"user_id": current_user.id}).fetchall()

            logger.info(f"Found {len(unextracted)} unextracted emails for user {current_user.id}")

            if len(unextracted) == 0:
                return {
                    "status": "success",
                    "reprocessed_count": 0,
                    "message": "No emails need reprocessing"
                }

            # Reprocess each email
            success_count = 0

            for email_id, subject, sender, raw_text, raw_html, received_at, recipients in unextracted:
                # Get the full event
                event = db.query(IncomingDataEvent).filter(IncomingDataEvent.id == email_id).first()

                if not event:
                    continue

                # Create email_data dict (mimicking Microsoft Graph format)
                email_data = {
                    "subject": subject,
                    "from": {"emailAddress": {"address": sender}},
                    "toRecipients": [{"emailAddress": {"address": r}} for r in (recipients or [])],
                    "receivedDateTime": received_at.isoformat() if received_at else None,
                    "body": {
                        "content": raw_text or raw_html or "",
                        "contentType": "text" if raw_text else "html"
                    }
                }

                # Delete old event to avoid duplicates
                db.delete(event)
                db.commit()

                # Reprocess with new extraction logic
                result = await process_microsoft_email_to_dre(email_data, current_user.id, db)

                if result.get("status") == "success":
                    success_count += 1

            logger.info(f"Reprocessed {success_count}/{len(unextracted)} emails for user {current_user.id}")

            return {
                "status": "success",
                "reprocessed_count": success_count,
                "total_found": len(unextracted),
                "message": f"Reprocessed {success_count} emails successfully"
            }

        except Exception as e:
            logger.error(f"Email reprocessing error: {e}")
            db.rollback()
            raise HTTPException(status_code=500, detail="Internal server error")


    @app.get("/api/v1/microsoft/synced-emails-status")
    async def get_synced_emails_status(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """Check status of synced emails - where did they go?"""
        try:
            from sqlalchemy import text

            # Get all incoming events for this user from Microsoft
            events = db.execute(text("""
                SELECT
                    ide.id, ide.subject, ide.sender, ide.received_at, ide.processed, ide.created_at,
                    ed.id as extracted_id, ed.status as extracted_status, ed.category
                FROM incoming_data_events ide
                LEFT JOIN extracted_data ed ON ide.id = ed.event_id
                WHERE ide.user_id = :user_id AND ide.source = 'microsoft365'
                ORDER BY ide.received_at DESC
                LIMIT 20
            """), {"user_id": current_user.id}).fetchall()

            results = []
            for e in events:
                results.append({
                    "event_id": e[0],
                    "subject": e[1][:50] if e[1] else None,
                    "sender": e[2],
                    "received_at": e[3].isoformat() if e[3] else None,
                    "processed": e[4],
                    "synced_at": e[5].isoformat() if e[5] else None,
                    "extracted_id": e[6],
                    "extracted_status": e[7],
                    "category": e[8]
                })

            # Summary stats
            total = len(results)
            with_extraction = len([r for r in results if r["extracted_id"]])
            pending_review = len([r for r in results if r["extracted_status"] == "pending_review"])

            return {
                "total_synced": total,
                "with_extraction": with_extraction,
                "pending_review": pending_review,
                "emails": results,
                "note": "If emails are synced but not in Reconciliation, they may have been classified as 'unrelated' or had extraction errors"
            }

        except Exception as e:
            logger.error(f"Synced emails status error: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")


    @app.post("/api/v1/microsoft/clear-sync-history")
    async def clear_sync_history(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """Clear sync history to allow re-syncing all emails (use with caution)"""
        try:
            from sqlalchemy import text

            # Delete extracted data first (foreign key constraint)
            deleted_extracted = db.execute(text("""
                DELETE FROM extracted_data
                WHERE event_id IN (
                    SELECT id FROM incoming_data_events
                    WHERE user_id = :user_id AND source = 'microsoft365'
                )
            """), {"user_id": current_user.id}).rowcount

            # Delete incoming events
            deleted_events = db.execute(text("""
                DELETE FROM incoming_data_events
                WHERE user_id = :user_id AND source = 'microsoft365'
            """), {"user_id": current_user.id}).rowcount

            db.commit()

            return {
                "status": "success",
                "deleted_events": deleted_events,
                "deleted_extractions": deleted_extracted,
                "message": f"Cleared {deleted_events} synced emails. Click 'Sync Emails Now' to re-sync."
            }

        except Exception as e:
            logger.error(f"Clear sync history error: {e}")
            db.rollback()
            raise HTTPException(status_code=500, detail="Internal server error")


    @app.post("/api/v1/reconciliation/reextract/{extracted_data_id}")
    async def reextract_email_data(
        extracted_data_id: int,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """Force re-extraction of a specific email using updated AI classification"""
        try:
            # Get the extracted data record
            extracted = db.query(ExtractedData).filter(
                ExtractedData.id == extracted_data_id
            ).first()

            if not extracted:
                raise HTTPException(status_code=404, detail="Extracted data not found")

            # Get the original email event
            event = db.query(IncomingDataEvent).filter(
                IncomingDataEvent.id == extracted.event_id
            ).first()

            if not event:
                raise HTTPException(status_code=404, detail="Original email not found")

            # Get the email content
            content = event.raw_text or event.raw_html or ""
            subject = event.subject or ""
            sender = event.sender or ""

            logger.info(f"Re-extracting email {extracted_data_id}: {subject[:50]}...")

            # Use Claude parser for re-extraction
            try:
                from ai_providers.claude_parser import get_claude_parser
                parser = get_claude_parser()

                claude_email_data = {
                    "subject": subject,
                    "body_text": content,
                    "sender": sender,
                    "received_at": event.received_at.isoformat() if event.received_at else None
                }

                # Re-classify the email type
                profile_type = parser.classify_email(claude_email_data)
                logger.info(f"Re-classified as: {profile_type}")

                # Re-parse with Claude
                parsed_result = await parser.parse_email(
                    claude_email_data,
                    profile_type,
                    None
                )

                extracted_fields = parsed_result.get('extracted_fields', {})
                confidence_scores = parsed_result.get('confidence_scores', {})

                # Build new fields dict
                new_fields = {}
                for field_name, field_value in extracted_fields.items():
                    if field_value is not None:
                        confidence = confidence_scores.get(field_name, 80)
                        new_fields[field_name] = {
                            "value": field_value,
                            "confidence": confidence / 100 if confidence > 1 else confidence
                        }

                # Update the extracted data record
                extracted.fields = new_fields
                extracted.match_confidence = parsed_result.get('overall_confidence', 0) / 100
                extracted.email_intent = parsed_result.get('email_summary', profile_type)
                extracted.updated_at = datetime.now(timezone.utc)

                db.commit()

                logger.info(f"✅ Re-extracted {len(new_fields)} fields for email {extracted_data_id}")

                return {
                    "status": "success",
                    "profile_type": profile_type,
                    "fields_extracted": len(new_fields),
                    "fields": new_fields,
                    "confidence": parsed_result.get('overall_confidence', 0)
                }

            except Exception as parse_error:
                logger.error(f"Claude parsing error: {parse_error}")
                raise HTTPException(status_code=500, detail="Parsing error")

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Re-extraction error: {e}")
            db.rollback()
            raise HTTPException(status_code=500, detail="Internal server error")


    @app.post("/api/v1/reconciliation/reextract-all-pending")
    async def reextract_all_pending_emails(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """Force re-extraction of ALL pending reconciliation items using updated AI"""
        try:
            # Get all pending items
            pending = db.query(ExtractedData).filter(
                ExtractedData.status == "pending_review"
            ).all()

            if not pending:
                return {
                    "status": "success",
                    "message": "No pending items to reprocess",
                    "reprocessed": 0
                }

            logger.info(f"Re-extracting {len(pending)} pending items...")

            success_count = 0
            errors = []

            from ai_providers.claude_parser import get_claude_parser
            parser = get_claude_parser()

            # Batch-fetch all related events in 1 query instead of N
            event_ids = [e.event_id for e in pending if e.event_id]
            events_map = {}
            if event_ids:
                events = db.query(IncomingDataEvent).filter(
                    IncomingDataEvent.id.in_(event_ids)
                ).all()
                events_map = {e.id: e for e in events}

            for extracted in pending:
                try:
                    # Look up pre-fetched event
                    event = events_map.get(extracted.event_id)

                    if not event:
                        continue

                    content = event.raw_text or event.raw_html or ""
                    subject = event.subject or ""
                    sender = event.sender or ""

                    claude_email_data = {
                        "subject": subject,
                        "body_text": content,
                        "sender": sender,
                        "received_at": event.received_at.isoformat() if event.received_at else None
                    }

                    # Re-classify and parse
                    profile_type = parser.classify_email(claude_email_data)
                    parsed_result = await parser.parse_email(claude_email_data, profile_type, None)

                    extracted_fields = parsed_result.get('extracted_fields', {})
                    confidence_scores = parsed_result.get('confidence_scores', {})

                    # Build new fields dict
                    new_fields = {}
                    for field_name, field_value in extracted_fields.items():
                        if field_value is not None:
                            confidence = confidence_scores.get(field_name, 80)
                            new_fields[field_name] = {
                                "value": field_value,
                                "confidence": confidence / 100 if confidence > 1 else confidence
                            }

                    # Update the record
                    extracted.fields = new_fields
                    extracted.match_confidence = parsed_result.get('overall_confidence', 0) / 100
                    extracted.email_intent = parsed_result.get('email_summary', profile_type)
                    extracted.updated_at = datetime.now(timezone.utc)

                    success_count += 1
                    logger.info(f"Re-extracted {extracted.id}: {len(new_fields)} fields as {profile_type}")

                except Exception as item_error:
                    errors.append(f"Item {extracted.id}: {str(item_error)}")
                    logger.error(f"Error re-extracting item {extracted.id}: {item_error}")

            db.commit()

            return {
                "status": "success",
                "total_pending": len(pending),
                "reprocessed": success_count,
                "errors": errors[:5] if errors else [],
                "message": f"Re-extracted {success_count}/{len(pending)} items"
            }

        except Exception as e:
            logger.error(f"Bulk re-extraction error: {e}")
            db.rollback()
            raise HTTPException(status_code=500, detail="Internal server error")


    @app.post("/api/v1/reconciliation/create-test-item")
    async def create_test_reconciliation_item(
        fields: dict[str, Any],
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """Create a test extracted data item for testing reconciliation approval flow.

        This endpoint is for development/testing purposes only.

        Example request:
        {
            "first_name": "Clarissa",
            "last_name": "Stansbury",
            "email": "claire.sumika@gmail.com",
            "phone": "(937) 789-9802"
        }
        """
        try:
            # First create a dummy incoming data event
            test_event = IncomingDataEvent(
                source="test",
                raw_text=f"Test data for {fields.get('first_name', '')} {fields.get('last_name', '')}",
                subject="Test Reconciliation Item",
                sender="test@example.com",
                user_id=current_user.id,
                processed=True
            )
            db.add(test_event)
            db.flush()

            # Build fields dict with confidence scores
            formatted_fields = {}
            for field_name, field_value in fields.items():
                if field_value is not None:
                    formatted_fields[field_name] = {
                        "value": field_value,
                        "confidence": 0.95
                    }

            # Create extracted data with no match (will trigger "No Matching Borrower" dialog)
            extracted = ExtractedData(
                event_id=test_event.id,
                category="lead_update",
                subcategory="new_borrower",
                fields=formatted_fields,
                match_entity_type=None,  # No match - will trigger create borrower dialog
                match_entity_id=None,
                match_confidence=0.0,
                ai_confidence=0.85,
                status="pending_review"
            )
            db.add(extracted)
            db.commit()
            db.refresh(extracted)

            logger.info(f"Created test extracted data item {extracted.id} for testing")

            return {
                "status": "success",
                "extracted_data_id": extracted.id,
                "event_id": test_event.id,
                "fields": formatted_fields,
                "message": f"Test item created successfully. Use extracted_data_id={extracted.id} for approval."
            }
        except Exception as e:
            logger.error(f"Error creating test item: {e}")
            db.rollback()
            raise HTTPException(status_code=500, detail="Internal server error")


    @app.post("/api/v1/reconciliation/test-match")
    async def test_entity_match(
        loan_number: str = None,
        borrower_name: str = None,
        email: str = None,
        phone: str = None,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """Test the entity matching logic with provided fields.

        This endpoint is for development/testing purposes to verify matching works.
        """
        try:
            # Build fields dict
            fields = {}
            if loan_number:
                fields["loan_number"] = {"value": loan_number, "confidence": 0.95}
            if borrower_name:
                fields["borrower_name"] = {"value": borrower_name, "confidence": 0.95}
            if email:
                fields["borrower_email"] = {"value": email, "confidence": 0.95}
            if phone:
                fields["borrower_phone"] = {"value": phone, "confidence": 0.95}

            if not fields:
                raise HTTPException(status_code=400, detail="At least one field required")

            # Run matching
            match_result = match_entity(fields, db, current_user.id)

            # Get entity name if matched
            entity_name = None
            if match_result.get("entity_type") and match_result.get("entity_id"):
                entity_name = get_entity_name(match_result["entity_type"], match_result["entity_id"], db)

            return {
                "status": "success",
                "input_fields": {k: v["value"] for k, v in fields.items()},
                "match_result": match_result,
                "entity_name": entity_name,
                "message": f"Match found: {match_result.get('entity_type', 'None')} ({entity_name})" if match_result.get("entity_type") else "No match found"
            }
        except Exception as e:
            logger.error(f"Error testing match: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")


    @app.post("/api/v1/reconciliation/rematch-all")
    async def rematch_all_pending(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """Re-run matching on all pending reconciliation items.

        This is useful after adding new matching logic (like ActiveLoanProfile)
        to update previously unmatched items.
        """
        try:
            from sqlalchemy import or_
            pending = db.query(ExtractedData).join(
                IncomingDataEvent,
                ExtractedData.event_id == IncomingDataEvent.id
            ).filter(
                or_(
                    IncomingDataEvent.user_id == current_user.id,
                    IncomingDataEvent.user_id == None
                ),
                ExtractedData.status.in_(["pending_review", "needs_review", "pending"])
            ).all()

            updated_count = 0
            for item in pending:
                # Re-run matching
                match_result = match_entity(item.fields or {}, db, current_user.id)

                if match_result.get("entity_type"):
                    # Update if we found a match
                    item.match_entity_type = match_result["entity_type"]
                    item.match_entity_id = str(match_result["entity_id"])
                    item.match_confidence = match_result.get("confidence", 0)
                    updated_count += 1
                    logger.info(f"Rematched item {item.id}: {match_result['entity_type']} - {match_result['entity_id']}")

            db.commit()

            return {
                "status": "success",
                "total_items": len(pending),
                "updated_count": updated_count,
                "message": f"Rematched {updated_count} of {len(pending)} pending items"
            }
        except Exception as e:
            logger.error(f"Error rematching: {e}")
            db.rollback()
            raise HTTPException(status_code=500, detail="Internal server error")


    @app.post("/api/v1/microsoft/sync-calendar")
    async def sync_microsoft_calendar(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """Sync calendar events from Microsoft 365"""
        try:
            oauth_record = db.query(MicrosoftOAuthToken).filter(
                MicrosoftOAuthToken.user_id == current_user.id
            ).first()

            if not oauth_record:
                raise HTTPException(status_code=404, detail="Microsoft 365 not connected")

            # Get access token
            access_token = decrypt_token(oauth_record.access_token)

            # Check if token needs refresh
            if oauth_record.token_expires_at:
                token_expiry = oauth_record.token_expires_at
                if token_expiry.tzinfo is None:
                    token_expiry = token_expiry.replace(tzinfo=timezone.utc)

                if token_expiry < datetime.now(timezone.utc) + timedelta(minutes=5):
                    refresh_result = await refresh_microsoft_token(oauth_record, db)
                    if not refresh_result.get("success"):
                        if refresh_result.get("needs_reauth"):
                            raise HTTPException(status_code=401, detail="needs_reauth")
                        raise HTTPException(status_code=401, detail="Failed to refresh token")
                    access_token = decrypt_token(oauth_record.access_token)

            # Fetch calendar events from Microsoft Graph API
            # Get events from next 30 days
            start_date = datetime.now(timezone.utc).isoformat()
            end_date = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }

            # Microsoft Graph API endpoint for calendar events
            graph_url = f"https://graph.microsoft.com/v1.0/me/calendar/calendarView?startDateTime={start_date}&endDateTime={end_date}&$top=100"

            response = await asyncio.to_thread(requests.get, graph_url, headers=headers)

            if response.status_code != 200:
                logger.error(f"Microsoft Calendar API error: {response.status_code} - {response.text}")
                raise HTTPException(status_code=500, detail=f"Microsoft Calendar API error: {response.status_code}")

            events_data = response.json()
            events = events_data.get("value", [])

            # Store events in database
            synced_count = 0
            for event_data in events:
                try:
                    # Parse event data
                    subject = event_data.get("subject", "No Subject")
                    start_dt = datetime.fromisoformat(event_data["start"]["dateTime"].replace('Z', '+00:00'))
                    end_dt = datetime.fromisoformat(event_data["end"]["dateTime"].replace('Z', '+00:00'))
                    location = event_data.get("location", {}).get("displayName", "")
                    body_content = event_data.get("body", {}).get("content", "")

                    # Check if event already exists (by microsoft event id in meta_data)
                    ms_event_id = event_data.get("id")
                    existing = db.query(CalendarEvent).filter(
                        CalendarEvent.user_id == current_user.id,
                        CalendarEvent.meta_data.contains({"microsoft_event_id": ms_event_id})
                    ).first()

                    if existing:
                        # Update existing event
                        existing.title = subject
                        existing.description = body_content[:500] if body_content else None
                        existing.start_time = start_dt
                        existing.end_time = end_dt
                        existing.location = location
                        existing.all_day = event_data.get("isAllDay", False)
                        existing.updated_at = datetime.now(timezone.utc)
                    else:
                        # Create new event
                        calendar_event = CalendarEvent(
                            title=subject,
                            description=body_content[:500] if body_content else None,
                            start_time=start_dt,
                            end_time=end_dt,
                            all_day=event_data.get("isAllDay", False),
                            location=location,
                            event_type="meeting",
                            user_id=current_user.id,
                            attendees=[att.get("emailAddress", {}).get("address") for att in event_data.get("attendees", [])],
                            status="scheduled",
                            meta_data={"microsoft_event_id": ms_event_id, "source": "microsoft365"}
                        )
                        db.add(calendar_event)

                    synced_count += 1

                except Exception as e:
                    logger.error(f"Error processing calendar event: {e}")
                    continue

            db.commit()
            logger.info(f"Synced {synced_count} calendar events for user {current_user.id}")

            return {
                "status": "success",
                "synced_count": synced_count,
                "total_events": len(events),
                "message": f"Synced {synced_count} calendar events successfully"
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Calendar sync error: {e}")
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=500, detail="Calendar sync error")

    @app.patch("/api/v1/microsoft/settings")
    async def update_microsoft_settings(
        settings: MicrosoftSyncSettings,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """Update Microsoft 365 sync settings"""
        try:
            oauth_record = db.query(MicrosoftOAuthToken).filter(
                MicrosoftOAuthToken.user_id == current_user.id
            ).first()

            if not oauth_record:
                raise HTTPException(status_code=404, detail="Microsoft 365 not connected")

            # Update settings
            if settings.sync_enabled is not None:
                oauth_record.sync_enabled = settings.sync_enabled

            if settings.sync_folder is not None:
                oauth_record.sync_folder = settings.sync_folder

            if settings.sync_frequency_minutes is not None:
                # Validate frequency (min 5 minutes, max 1440 = 24 hours)
                if settings.sync_frequency_minutes < 5 or settings.sync_frequency_minutes > 1440:
                    raise HTTPException(status_code=400, detail="Sync frequency must be between 5 and 1440 minutes")
                oauth_record.sync_frequency_minutes = settings.sync_frequency_minutes

            oauth_record.updated_at = datetime.now(timezone.utc)
            db.commit()

            logger.info(f"Updated Microsoft settings for user {current_user.id}")

            return {
                "status": "success",
                "message": "Settings updated successfully"
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Microsoft settings update error: {e}")
            db.rollback()
            raise HTTPException(status_code=500, detail="Internal server error")

    # Extracted to routes/health_routes.py
    # (/, /prd)

    @app.post("/api/v1/debug/test-task-creation")
    async def debug_test_task_creation(
        loan_id: int,
        trigger: str = "stage->CTC",
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user_flexible)
    ):
        """
        Debug endpoint to test task creation in isolation.
        Pass a loan_id and trigger (like "stage->CTC") to test if tasks are created.
        """
        import traceback
        debug_info = {
            "loan_id": loan_id,
            "trigger": trigger,
            "steps": [],
            "error": None,
            "tasks_created": [],
            "tasks_in_db": []
        }

        try:
            # Step 1: Get the loan
            loan = db.query(Loan).filter(Loan.id == loan_id).first()
            if not loan:
                debug_info["error"] = f"Loan {loan_id} not found"
                return debug_info

            debug_info["steps"].append(f"Found loan: {loan.loan_number}, stage={loan.stage}, loan_officer_id={loan.loan_officer_id}")

            # Step 2: Check Task model
            debug_info["steps"].append(f"Task model columns: {[c.name for c in Task.__table__.columns]}")

            # Step 3: Call create_milestone_tasks with the trigger
            updated_fields = [trigger]
            debug_info["steps"].append(f"Calling create_milestone_tasks with updated_fields={updated_fields}")

            tasks_created = create_milestone_tasks(loan, updated_fields, db)
            debug_info["tasks_created"] = tasks_created
            debug_info["steps"].append(f"create_milestone_tasks returned: {tasks_created}")

            # Step 4: Query tasks for this loan to verify
            tasks = db.query(Task).filter(Task.loan_id == loan_id).all()
            debug_info["tasks_in_db"] = [
                {"id": t.id, "title": t.title, "status": t.status, "priority": t.priority}
                for t in tasks
            ]
            debug_info["steps"].append(f"Found {len(tasks)} tasks in DB for loan {loan_id}")

        except Exception as e:
            debug_info["error"] = type(e).__name__
            debug_info["steps"].append(f"Exception: {type(e).__name__}")
            logger.error(f"Milestone tasks debug failed: {traceback.format_exc()}")

        return debug_info


    # /health extracted to routes/health_routes.py

    # Extracted to routes/health_routes.py and routes/admin_ops_routes.py
    # (admin/pool-status, admin/salesforce-*, admin/pool-reset,
    #  admin/update-telephony-config, /ping)

    @app.get("/admin/create-salesforce-tables")
    async def create_salesforce_tables(db: Session = Depends(get_db)):
        """Admin endpoint to create Salesforce integration tables"""
        results = []

        try:
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS oauth_states (
                    id SERIAL PRIMARY KEY,
                    state_token VARCHAR(255) UNIQUE NOT NULL,
                    user_id INTEGER NOT NULL,
                    provider VARCHAR(50) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    used BOOLEAN DEFAULT FALSE,
                    return_url TEXT,
                    state_metadata JSONB
                )
            """))
            db.commit()
            results.append("oauth_states: created/verified")
        except Exception as e:
            results.append(f"oauth_states: {str(e)}")
            db.rollback()

        try:
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS integration_profiles (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    provider VARCHAR(50) NOT NULL DEFAULT 'salesforce',
                    status VARCHAR(50) NOT NULL DEFAULT 'disconnected',
                    access_token_encrypted TEXT,
                    refresh_token_encrypted TEXT,
                    instance_url TEXT,
                    sf_org_id VARCHAR(100),
                    sf_user_id VARCHAR(100),
                    sf_username VARCHAR(255),
                    connected_at TIMESTAMP,
                    last_sync_at TIMESTAMP,
                    last_error TEXT,
                    field_map_version INTEGER DEFAULT 1,
                    sync_enabled BOOLEAN DEFAULT TRUE,
                    sync_interval_minutes INTEGER DEFAULT 15,
                    sync_direction VARCHAR(20) DEFAULT 'bidirectional',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, provider)
                )
            """))
            db.commit()
            results.append("integration_profiles: created/verified")
        except Exception as e:
            results.append(f"integration_profiles: {str(e)}")
            db.rollback()

        # Create sf_user_schemas table for Salesforce schema discovery
        try:
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS sf_user_schemas (
                    id SERIAL PRIMARY KEY,
                    integration_profile_id INTEGER NOT NULL REFERENCES integration_profiles(id) ON DELETE CASCADE,
                    object_name VARCHAR(100) NOT NULL,
                    fields JSONB NOT NULL,
                    record_types JSONB,
                    picklist_values JSONB,
                    discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_validated_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(integration_profile_id, object_name)
                )
            """))
            db.commit()
            results.append("sf_user_schemas: created/verified")
        except Exception as e:
            results.append(f"sf_user_schemas: {str(e)}")
            db.rollback()

        # Create field_mappings table
        try:
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS field_mappings (
                    id SERIAL PRIMARY KEY,
                    integration_profile_id INTEGER NOT NULL REFERENCES integration_profiles(id) ON DELETE CASCADE,
                    sf_object VARCHAR(100) NOT NULL,
                    sf_field VARCHAR(255) NOT NULL,
                    crm_entity VARCHAR(100) NOT NULL,
                    crm_field VARCHAR(255) NOT NULL,
                    transform_type VARCHAR(50) DEFAULT 'direct',
                    transform_config JSONB,
                    is_active BOOLEAN DEFAULT TRUE,
                    is_required BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(integration_profile_id, sf_object, sf_field)
                )
            """))
            db.commit()
            results.append("field_mappings: created/verified")
        except Exception as e:
            results.append(f"field_mappings: {str(e)}")
            db.rollback()

        # Create integration_events table for logging
        try:
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS integration_events (
                    id SERIAL PRIMARY KEY,
                    integration_profile_id INTEGER NOT NULL REFERENCES integration_profiles(id) ON DELETE CASCADE,
                    event_type VARCHAR(100) NOT NULL,
                    status VARCHAR(50) NOT NULL,
                    error_message TEXT,
                    duration_ms INTEGER,
                    event_data JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            db.commit()
            results.append("integration_events: created/verified")
        except Exception as e:
            results.append(f"integration_events: {str(e)}")
            db.rollback()

        return {"results": results}


    # Extracted to routes/health_routes.py
    # (/api/v1/health, /deploy-test, /debug/routers, /debug/scheduler-status)

    @app.post("/api/v1/debug/complete-onboarding-by-email")
    async def debug_complete_onboarding_by_email(
        email: str,
        db: Session = Depends(get_db)
    ):
        """Debug endpoint to mark a user's onboarding as complete by email"""
        user = db.query(User).filter(User.email == email).first()
        if not user:
            raise HTTPException(status_code=404, detail=f"User {email} not found")

        user.onboarding_completed = True
        db.commit()

        return {
            "success": True,
            "message": f"Onboarding marked complete for {email}",
            "user_id": user.id,
            "email": user.email
        }


    @app.post("/api/v1/admin/run-salesforce-migration")
    async def run_salesforce_migration(
        secret: str = Query(..., description="Admin secret key"),
        db: Session = Depends(get_db)
    ):
        """Run Salesforce sync fields migration - adds columns to loans and leads tables"""
        # Verify admin secret
        admin_secret = os.getenv("ADMIN_SECRET")
        if not admin_secret or secret != admin_secret:
            raise HTTPException(status_code=401, detail="Invalid admin secret")

        # Columns to add to LOANS table
        loan_columns = [
            # Property Details
            ("property_type", "VARCHAR"),
            ("occupancy_type", "VARCHAR"),
            ("property_county", "VARCHAR"),
            ("property_ownership_type", "VARCHAR"),
            ("property_units", "INTEGER"),
            # 1st Loan Financial Details
            ("rate_type", "VARCHAR"),
            ("monthly_payment", "FLOAT"),
            ("property_tax", "FLOAT"),
            ("hazard_insurance", "FLOAT"),
            ("mortgage_insurance", "FLOAT"),
            ("hoa_amount", "FLOAT"),
            ("origination_fee", "FLOAT"),
            ("estimated_prepaid_interest", "FLOAT"),
            ("points", "FLOAT"),
            ("index_rate", "FLOAT"),
            ("margin", "FLOAT"),
            # LTV/CLTV
            ("ltv", "FLOAT"),
            ("cltv", "FLOAT"),
            ("loan_purpose", "VARCHAR"),
            ("file_state", "VARCHAR"),
            # 2nd Loan Details
            ("second_loan_amount", "FLOAT"),
            ("second_loan_rate", "FLOAT"),
            ("second_loan_payment", "FLOAT"),
            # Present vs Proposed Housing
            ("present_housing_expense", "FLOAT"),
            ("proposed_housing_expense", "FLOAT"),
            ("present_monthly_payment", "FLOAT"),
            ("proposed_monthly_payment", "FLOAT"),
        ]

        # Columns to add to LEADS table
        lead_columns = [
            ("occupancy_type", "VARCHAR"),
            ("property_county", "VARCHAR"),
            ("property_ownership_type", "VARCHAR"),
            ("property_units", "INTEGER"),
            ("rate_type", "VARCHAR"),
            ("monthly_payment", "FLOAT"),
            ("property_tax", "FLOAT"),
            ("hazard_insurance", "FLOAT"),
            ("mortgage_insurance", "FLOAT"),
            ("hoa_amount", "FLOAT"),
            ("origination_fee", "FLOAT"),
            ("estimated_prepaid_interest", "FLOAT"),
            ("index_rate", "FLOAT"),
            ("margin", "FLOAT"),
            ("loan_purpose", "VARCHAR"),
            ("file_state", "VARCHAR"),
            ("second_loan_amount", "FLOAT"),
            ("second_loan_rate", "FLOAT"),
            ("second_loan_payment", "FLOAT"),
            ("present_housing_expense", "FLOAT"),
            ("proposed_housing_expense", "FLOAT"),
            ("present_monthly_payment", "FLOAT"),
            ("proposed_monthly_payment", "FLOAT"),
            ("cltv", "FLOAT"),
        ]

        results = {"loans_added": [], "loans_skipped": [], "leads_added": [], "leads_skipped": [], "errors": []}

        try:
            # Get existing columns for LOANS
            loan_cols_result = db.execute(text("""
                SELECT column_name FROM information_schema.columns WHERE table_name = 'loans'
            """))
            existing_loan_cols = {row[0] for row in loan_cols_result}

            # Add missing columns to LOANS
            # SEC-006: Validate column names against hardcoded whitelist
            _allowed_loan_cols = {c[0] for c in loan_columns}
            for col_name, col_type in loan_columns:
                if col_name in existing_loan_cols:
                    results["loans_skipped"].append(col_name)
                elif col_name not in _allowed_loan_cols or not col_name.isidentifier():
                    results["errors"].append(f"loans.{col_name}: invalid column name")
                else:
                    try:
                        alter_sql = "ALTER TABLE loans ADD COLUMN " + col_name + " " + col_type
                        db.execute(text(alter_sql))
                        results["loans_added"].append(col_name)
                    except Exception as e:
                        logger.error(f"loans.{col_name} migration failed: {e}")
                        results["errors"].append(f"loans.{col_name}: migration failed")

            # Get existing columns for LEADS
            lead_cols_result = db.execute(text("""
                SELECT column_name FROM information_schema.columns WHERE table_name = 'leads'
            """))
            existing_lead_cols = {row[0] for row in lead_cols_result}

            # Add missing columns to LEADS
            # SEC-006: Validate column names against hardcoded whitelist
            _allowed_lead_cols = {c[0] for c in lead_columns}
            for col_name, col_type in lead_columns:
                if col_name in existing_lead_cols:
                    results["leads_skipped"].append(col_name)
                elif col_name not in _allowed_lead_cols or not col_name.isidentifier():
                    results["errors"].append(f"leads.{col_name}: invalid column name")
                else:
                    try:
                        alter_sql = "ALTER TABLE leads ADD COLUMN " + col_name + " " + col_type
                        db.execute(text(alter_sql))
                        results["leads_added"].append(col_name)
                    except Exception as e:
                        logger.error(f"leads.{col_name} migration failed: {e}")
                        results["errors"].append(f"leads.{col_name}: migration failed")

            db.commit()

            return {
                "status": "success",
                "message": f"Migration complete: {len(results['loans_added'])} loan columns added, {len(results['leads_added'])} lead columns added",
                "results": results
            }

        except Exception as e:
            db.rollback()
            logger.error(f"Migration failed: {e}")
            raise HTTPException(status_code=500, detail="Migration failed")


    @app.post("/api/v1/debug/test-two-way-email")
    async def debug_test_two_way_email(
        to_email: str = "tloss@me.com",
        message: str = "Hi, I am interested in refinancing my home worth $500,000"
    ):
        """
        Debug endpoint to test the two-way email conversation system.
        Simulates receiving an email and generating an AI response.
        """
        try:
            from agents.qualification_agent import process_qualification_message
            from datetime import datetime

            # Generate unique conversation ID
            conv_id = f"test_email_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            # Process through the qualification agent
            result = process_qualification_message(
                conversation_id=conv_id,
                message=message,
                channel="email",
                sender_info={"email": to_email, "first_name": to_email.split("@")[0].title()}
            )

            return {
                "status": "success",
                "conversation_id": conv_id,
                "simulated_inbound": {
                    "from": to_email,
                    "message": message
                },
                "ai_response": {
                    "text": result["response"],
                    "type": result["response_type"],
                    "should_send": result["should_send"]
                },
                "qualification": {
                    "status": result["qualification"]["status"],
                    "completion": f"{result['qualification']['completion_percentage']:.0f}%",
                    "missing_fields": result["qualification"]["missing_fields"]
                },
                "tone_analysis": {
                    "emotion": result["tone_analysis"]["emotional_state"]["primary_emotion"],
                    "sentiment": result["tone_analysis"]["sentiment"]["sentiment_category"],
                    "urgency": result["tone_analysis"]["urgency"]["urgency_level"]
                },
                "next_action": result["next_action"],
                "note": "To send actual emails, configure SENDGRID_API_KEY or authenticate via Microsoft at /auth/microsoft/login"
            }

        except Exception as e:
            logger.error(f"Two-way email test error: {e}")
            import traceback
            return {
                "status": "error",
                "error": "Internal server error"
            }


    @app.post("/api/v1/debug/send-real-email")
    async def debug_send_real_email(
        to_email: str = "tloss@me.com",
        message: str = "Hi, I am interested in refinancing my home worth $500,000"
    ):
        """
        Actually send a real email via SendGrid demonstrating the two-way AI conversation.
        This processes the message through the AI agent and sends a real response.
        """
        try:
            from agents.qualification_agent import process_qualification_message
            from email_service import email_service
            from datetime import datetime

            # Generate unique conversation ID
            conv_id = f"email_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            sender_name = to_email.split("@")[0].replace(".", " ").title()

            # Process through the qualification agent
            result = process_qualification_message(
                conversation_id=conv_id,
                message=message,
                channel="email",
                sender_info={"email": to_email, "first_name": sender_name}
            )

            # Format the email HTML
            html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #c9a227 0%, #f4d03f 100%); color: white; padding: 20px; border-radius: 8px 8px 0 0; text-align: center; }}
            .content {{ background: #f9fafb; padding: 24px; border: 1px solid #e5e7eb; }}
            .message-box {{ background: white; padding: 16px; border-radius: 8px; border-left: 4px solid #c9a227; margin-bottom: 20px; }}
            .ai-response {{ background: white; padding: 16px; border-radius: 8px; border-left: 4px solid #3b82f6; }}
            .footer {{ text-align: center; padding: 16px; color: #6b7280; font-size: 12px; }}
            .badge {{ display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: bold; }}
            .badge-emotion {{ background: #fef3c7; color: #92400e; }}
            .badge-urgency {{ background: #dbeafe; color: #1e40af; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Perennia AI Mortgage Assistant</h1>
            <p>Your AI-Powered Loan Qualification Helper</p>
        </div>
        <div class="content">
            <h3>Hello {sender_name}!</h3>

            <p><strong>Your message:</strong></p>
            <div class="message-box">
                {message}
            </div>

            <p><strong>AI Assistant Response:</strong></p>
            <div class="ai-response">
                {result['response'].replace(chr(10), '<br>')}
            </div>

            <p style="margin-top: 20px;">
                <span class="badge badge-emotion">Tone: {result['tone_analysis']['emotional_state']['primary_emotion']}</span>
                <span class="badge badge-urgency">Urgency: {result['tone_analysis']['urgency']['urgency_level']}</span>
            </p>

            <p style="margin-top: 20px; color: #6b7280; font-size: 14px;">
                <strong>Qualification Progress:</strong> {result['qualification']['completion_percentage']:.0f}%<br>
                <strong>Conversation ID:</strong> {conv_id}
            </p>
        </div>
        <div class="footer">
            <p>This is a demonstration of Perennia AI's two-way email conversation system.</p>
            <p>Reply to this email to continue the conversation!</p>
        </div>
    </body>
    </html>
    """

            # Send the email with correct FROM address
            ai_from_email = os.getenv("AI_FROM_EMAIL", _DEFAULT_ORGANIZER_EMAIL)
            email_sent = email_service.send_html_email(
                to_email=to_email,
                subject=f"RE: Your Mortgage Inquiry - Perennia AI Assistant",
                html_body=html_body,
                plain_text_body=f"Hello {sender_name}!\n\nYour message: {message}\n\nAI Response:\n{result['response']}\n\nReply to continue the conversation.\n\n- Perennia AI",
                from_email=ai_from_email,
                reply_to=ai_from_email
            )

            return {
                "status": "success" if email_sent else "failed",
                "email_sent": email_sent,
                "to": to_email,
                "conversation_id": conv_id,
                "simulated_inbound_message": message,
                "ai_response": result["response"],
                "qualification_progress": f"{result['qualification']['completion_percentage']:.0f}%",
                "tone": {
                    "emotion": result["tone_analysis"]["emotional_state"]["primary_emotion"],
                    "sentiment": result["tone_analysis"]["sentiment"]["sentiment_category"],
                    "urgency": result["tone_analysis"]["urgency"]["urgency_level"]
                },
                "sendgrid_configured": bool(email_service.sendgrid_api_key)
            }

        except Exception as e:
            logger.error(f"Send real email error: {e}")
            import traceback
            return {
                "status": "error",
                "error": "Internal server error"
            }


    @app.post("/api/v1/webhook/sendgrid-inbound")
    async def sendgrid_inbound_webhook(request: Request):
        """
        SendGrid Inbound Parse webhook - receives incoming emails and responds with AI.

        To set up:
        1. Go to SendGrid Settings > Inbound Parse
        2. Add your domain (e.g., reply.perenniaai.com)
        3. Set the webhook URL to: https://your-server.com/api/v1/webhook/sendgrid-inbound
        4. Enable "POST the raw, full MIME message"
        """
        try:
            from agents.qualification_agent import process_qualification_message
            from email_service import email_service
            import re

            # Parse form data from SendGrid
            form_data = await request.form()

            # Log all form fields for debugging
            all_fields = {key: str(value)[:200] for key, value in form_data.items()}
            logger.info(f"SendGrid form fields: {list(all_fields.keys())}")
            logger.info(f"SendGrid form data: {all_fields}")

            # Extract email details
            from_email = form_data.get("from", "")
            to_email = form_data.get("to", "")
            subject = form_data.get("subject", "")
            text_body = form_data.get("text", "")
            html_body = form_data.get("html", "")

            # Also try 'email' field (raw MIME)
            raw_email = form_data.get("email", "")

            logger.info(f"from={from_email}, to={to_email}, subject={subject}")
            logger.info(f"text_body length={len(text_body)}, html_body length={len(html_body)}, raw_email length={len(raw_email)}")

            # If text/html are empty, parse from raw MIME email
            if not text_body and not html_body and raw_email:
                import email
                from email import policy
                msg = email.message_from_string(raw_email, policy=policy.default)

                # Extract body from MIME message
                if msg.is_multipart():
                    for part in msg.walk():
                        content_type = part.get_content_type()
                        if content_type == "text/plain":
                            text_body = part.get_content()
                            logger.info(f"Extracted text/plain from MIME: {len(text_body)} chars")
                        elif content_type == "text/html" and not text_body:
                            html_body = part.get_content()
                            logger.info(f"Extracted text/html from MIME: {len(html_body)} chars")
                else:
                    text_body = msg.get_content()
                    logger.info(f"Extracted single part content: {len(text_body)} chars")

            # Extract sender email address (SendGrid sends "Name <email@example.com>")
            email_match = re.search(r'<([^>]+)>', from_email)
            sender_email = email_match.group(1) if email_match else from_email
            sender_name = from_email.split('<')[0].strip().strip('"') if '<' in from_email else sender_email.split('@')[0]

            # Use text body, or strip HTML
            message_body = text_body or html_body
            if not text_body and html_body:
                # Simple HTML strip
                message_body = re.sub(r'<[^>]+>', ' ', html_body)
                message_body = re.sub(r'\s+', ' ', message_body)

            logger.info(f"Raw message body from {mask_email(sender_email)}: {message_body[:100]}...")

            # Clean up the message (remove quoted replies)
            lines = message_body.split('\n')
            clean_lines = []
            found_quote_start = False
            for line in lines:
                line_lower = line.lower().strip()
                # Stop at quoted content markers
                if line.strip().startswith('>'):
                    found_quote_start = True
                    break
                if 'wrote:' in line_lower and ('@' in line_lower or 'on ' in line_lower):
                    found_quote_start = True
                    break
                if line_lower.startswith('from:') and '@' in line_lower:
                    found_quote_start = True
                    break
                if '-------- original message --------' in line_lower:
                    found_quote_start = True
                    break
                if 'sent from my iphone' in line_lower or 'sent from my ipad' in line_lower:
                    break
                clean_lines.append(line)

            clean_message = '\n'.join(clean_lines).strip()

            # If still empty, just use the first 500 chars of raw message
            if not clean_message and message_body:
                clean_message = message_body[:500].strip()
                logger.info(f"Using raw message as fallback: {clean_message[:100]}...")

            if not clean_message:
                logger.warning(f"Empty message received from {sender_email}")
                return {"status": "ignored", "reason": "empty message"}

            # Generate conversation ID from sender email
            conv_id = f"email_{sender_email.replace('@', '_').replace('.', '_')}"

            logger.info(f"Inbound email from {sender_email}: {clean_message[:100]}...")

            # =====================================================================
            # INTELLIGENT EMAIL ROUTING
            # First identify sender and classify intent, then route appropriately
            # =====================================================================
            from services.intelligent_email_handler import get_intelligent_email_handler

            db = SessionLocal()
            try:
                intelligent_handler = get_intelligent_email_handler(db)
                result = intelligent_handler.process_email(
                    sender_email=sender_email,
                    sender_name=sender_name,
                    subject=subject,
                    message=clean_message,
                )

                # If handler says to use qualification agent, fall back to that
                if result.get("use_qualification_agent"):
                    logger.info(f"Routing to qualification agent for {result.get('sender_type', 'unknown')} sender")
                    result = process_qualification_message(
                        conversation_id=conv_id,
                        message=clean_message,
                        channel="email",
                        sender_info=result.get("sender_info", {"email": sender_email, "first_name": sender_name})
                    )
                else:
                    logger.info(f"Intelligent handler processed: sender_type={result.get('sender_type')}, action={result.get('action')}")

            finally:
                db.close()

            # Only send response if AI has one
            if result["should_send"] and result.get("response"):
                # Get conversation history for the email thread
                from services.conversation_intelligence import get_conversation_service, Channel
                conv_service = get_conversation_service()
                state = conv_service.get_or_create_conversation(conv_id, Channel.EMAIL)

                # Record user message in history
                state.message_history.append({
                    "role": "user",
                    "content": clean_message,
                    "timestamp": datetime.now().isoformat()
                })

                # Record AI response in history
                state.message_history.append({
                    "role": "assistant",
                    "content": result['response'],
                    "timestamp": datetime.now().isoformat()
                })

                # Build Outlook-style email thread
                thread_html = ""
                thread_plain = ""

                # Build thread from message history (oldest to newest, excluding current)
                if state.message_history and len(state.message_history) > 2:
                    thread_html = '<div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #cccccc;">'
                    thread_plain = "\n\n"

                    # Show previous messages in reverse chronological order (like Outlook)
                    prev_messages = state.message_history[:-2]  # Exclude current exchange
                    for i, msg in enumerate(reversed(prev_messages)):
                        sender_name_thread = "Sarah - Perennia AI" if msg["role"] == "assistant" else sender_name
                        sender_email_thread = "admin@perenniaai.com" if msg["role"] == "assistant" else sender_email
                        msg_time = msg.get("timestamp", "")[:16].replace("T", " ") if msg.get("timestamp") else ""

                        thread_html += f'''
    <div style="color: #1f497d; font-family: Calibri, sans-serif; font-size: 11pt;">
    <p style="margin: 0;"><b>From:</b> {sender_name_thread} &lt;{sender_email_thread}&gt;</p>
    <p style="margin: 0;"><b>Sent:</b> {msg_time}</p>
    <p style="margin: 0 0 10px 0;"><b>Subject:</b> Re: Quick question about your mortgage goals</p>
    <div style="margin: 10px 0; padding-left: 10px; border-left: 2px solid #1f497d;">
    {msg["content"].replace(chr(10), '<br>')}
    </div>
    </div>
    <hr style="border: none; border-top: 1px solid #cccccc; margin: 15px 0;">
    '''
                        thread_plain += f"\n________________________________________\nFrom: {sender_name_thread} <{sender_email_thread}>\nSent: {msg_time}\nSubject: Re: Quick question about your mortgage goals\n\n{msg['content']}\n"

                    thread_html += '</div>'

                # Format response email in Outlook style
                html_response = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Calibri, Arial, sans-serif; font-size: 11pt; color: #000000; margin: 0; padding: 20px; }}
        </style>
    </head>
    <body>
    <div style="font-family: Calibri, Arial, sans-serif; font-size: 11pt; color: #000000;">
    <p>Hi {sender_name},</p>

    <p>{result['response'].replace(chr(10), '<br>')}</p>

    <p>Best regards,<br>
    <b>Sarah</b><br>
    <span style="color: #666666;">AI Mortgage Assistant | Perennia AI</span></p>
    </div>

    {thread_html}

    <div style="margin-top: 20px; padding-top: 10px; border-top: 1px solid #cccccc; color: #1f497d; font-family: Calibri, sans-serif; font-size: 11pt;">
    <p style="margin: 0;"><b>From:</b> {sender_name} &lt;{sender_email}&gt;</p>
    <p style="margin: 0;"><b>Sent:</b> {datetime.now().strftime('%A, %B %d, %Y %I:%M %p')}</p>
    <p style="margin: 0 0 10px 0;"><b>Subject:</b> {subject}</p>
    <div style="margin: 10px 0; padding-left: 10px; border-left: 2px solid #c9a227;">
    {clean_message[:500]}{"..." if len(clean_message) > 500 else ""}
    </div>
    </div>
    </body>
    </html>
    """

                # Determine reply subject
                reply_subject = subject if subject.lower().startswith('re:') else f"Re: {subject}"

                # Build plain text version
                plain_text_response = f"""Hi {sender_name},

    {result['response']}

    Best regards,
    Sarah
    AI Mortgage Assistant | Perennia AI

    ________________________________________
    From: {sender_name} <{sender_email}>
    Sent: {datetime.now().strftime('%A, %B %d, %Y %I:%M %p')}
    Subject: {subject}

    {clean_message[:500]}
    {thread_plain}
    """

                # Check if there's an appointment booking - prepare ICS attachment
                attachments = None
                calendar_invite_sent = False
                lo_invite_sent = False
                lo_email_sent = False
                booking_result = result.get("booking_result")

                if booking_result and booking_result.get("success"):
                    try:
                        from utils.calendar_invite import generate_appointment_ics, generate_lo_appointment_ics
                        from datetime import datetime as dt

                        appt_time = dt.fromisoformat(booking_result["datetime"])

                        # Get loan officer info from booking result
                        lo_info = booking_result.get("loan_officer") or {}
                        lo_name = lo_info.get("name")
                        lo_email = lo_info.get("email")
                        lo_phone = lo_info.get("phone")

                        # Generate customer calendar invite (with LO info)
                        ics_content = generate_appointment_ics(
                            appointment_id=booking_result["appointment_id"],
                            contact_name=booking_result.get("contact_name", sender_name),
                            contact_email=sender_email,
                            start_time=appt_time,
                            duration_minutes=booking_result.get("duration_minutes", 30),
                            appointment_type=booking_result.get("type", "consultation"),
                            loan_officer_name=lo_name,
                            loan_officer_email=lo_email,
                        )

                        # Prepare attachment for main email to customer
                        attachments = [{
                            'content': ics_content.encode('utf-8'),
                            'filename': 'appointment.ics',
                            'type': 'text/calendar; method=REQUEST'
                        }]
                        calendar_invite_sent = True
                        logger.info(f"Customer ICS attachment prepared for {sender_email} (with LO: {lo_name})")

                        # Send calendar invite and email to loan officer
                        if lo_email:
                            try:
                                # Generate LO calendar invite
                                lo_ics_content = generate_lo_appointment_ics(
                                    appointment_id=booking_result["appointment_id"],
                                    contact_name=booking_result.get("contact_name", sender_name),
                                    contact_email=sender_email,
                                    contact_phone=None,  # May not have phone yet
                                    start_time=appt_time,
                                    duration_minutes=booking_result.get("duration_minutes", 30),
                                    appointment_type=booking_result.get("type", "consultation"),
                                    loan_officer_name=lo_name,
                                    loan_officer_email=lo_email,
                                    notes=f"New appointment booked via AI assistant. Contact: {sender_email}",
                                )

                                # Prepare LO email content
                                lo_subject = f"New Appointment: {booking_result.get('contact_name', sender_name)} - {appt_time.strftime('%b %d at %I:%M %p')}"
                                lo_html = f"""
                                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                                    <h2 style="color: #1e3a5f;">New Appointment Scheduled</h2>
                                    <p>A new consultation has been booked via AI assistant.</p>

                                    <div style="background: #f5f5f5; padding: 20px; border-radius: 8px; margin: 20px 0;">
                                        <h3 style="margin-top: 0; color: #333;">Appointment Details</h3>
                                        <p><strong>Client:</strong> {booking_result.get('contact_name', sender_name)}</p>
                                        <p><strong>Email:</strong> {sender_email}</p>
                                        <p><strong>Date:</strong> {appt_time.strftime('%A, %B %d, %Y')}</p>
                                        <p><strong>Time:</strong> {appt_time.strftime('%I:%M %p')}</p>
                                        <p><strong>Duration:</strong> {booking_result.get('duration_minutes', 30)} minutes</p>
                                        <p><strong>Type:</strong> {booking_result.get('type', 'Consultation').replace('_', ' ').title()}</p>
                                        <p><strong>Reference:</strong> {booking_result['appointment_id']}</p>
                                    </div>

                                    <p>A calendar invitation is attached. Please add it to your calendar.</p>

                                    <p style="color: #666; font-size: 12px; margin-top: 30px;">
                                        This appointment was scheduled by Sarah, your AI assistant.
                                    </p>
                                </div>
                                """

                                lo_attachments = [{
                                    'content': lo_ics_content.encode('utf-8'),
                                    'filename': 'appointment.ics',
                                    'type': 'text/calendar; method=REQUEST'
                                }]

                                # Send email to loan officer
                                ai_from_email_lo = os.getenv("AI_FROM_EMAIL", _DEFAULT_ORGANIZER_EMAIL)
                                lo_email_sent = email_service.send_html_email(
                                    to_email=lo_email,
                                    subject=lo_subject,
                                    html_body=lo_html,
                                    attachments=lo_attachments,
                                    from_email=ai_from_email_lo,
                                    reply_to=ai_from_email_lo
                                )
                                lo_invite_sent = lo_email_sent
                                logger.info(f"LO notification sent to {lo_email}: {lo_email_sent}")

                            except Exception as lo_err:
                                logger.warning(f"Could not send LO notification: {lo_err}")

                    except Exception as ics_err:
                        logger.warning(f"Could not generate ICS: {ics_err}")

                # Send the response (with ICS attachment if booking)
                ai_from_email = os.getenv("AI_FROM_EMAIL", _DEFAULT_ORGANIZER_EMAIL)
                email_sent = email_service.send_html_email(
                    to_email=sender_email,
                    subject=reply_subject,
                    html_body=html_response,
                    plain_text_body=plain_text_response,
                    attachments=attachments,
                    from_email=ai_from_email,
                    reply_to=ai_from_email
                )

                logger.info(f"AI response sent to {sender_email}: {email_sent} (with_ics={calendar_invite_sent})")

                # Log for training review
                try:
                    from routes.email_training_routes import EmailTrainingLog
                    training_db = SessionLocal()
                    training_log = EmailTrainingLog(
                        conversation_id=conv_id,
                        from_email=sender_email,
                        to_email=_DEFAULT_ORGANIZER_EMAIL,
                        subject=subject,
                        user_message=clean_message,
                        ai_response=result["response"],
                        detected_topics=result.get("metadata", {}).get("topics_addressed"),
                        conversation_stage=result.get("conversation_state", {}).get("stage"),
                        qualification_data=result.get("qualification", {}).get("data")
                    )
                    training_db.add(training_log)
                    training_db.commit()
                    training_log_id = training_log.id
                    training_db.close()
                    logger.info(f"Email logged for training: id={training_log_id}")
                except Exception as train_err:
                    logger.warning(f"Could not log email for training: {train_err}")
                    training_log_id = None

                # Note: Calendar invite (ICS) is now attached to main response email above

                return {
                    "status": "processed",
                    "email_sent": email_sent,
                    "conversation_id": conv_id,
                    "from": sender_email,
                    "ai_response": result["response"][:100] + "...",
                    "qualification_progress": f"{result['qualification']['completion_percentage']:.0f}%",
                    "should_escalate": result["should_escalate"],
                    "training_log_id": training_log_id,
                    "appointment_booked": booking_result is not None,
                    "calendar_invite_sent": calendar_invite_sent,
                    "lo_invite_sent": lo_invite_sent,
                    "lo_email_sent": lo_email_sent,
                    "assigned_lo": (booking_result.get("loan_officer") or {}).get("name") if booking_result else None
                }
            else:
                return {
                    "status": "no_response_needed",
                    "conversation_id": conv_id,
                    "reason": "AI determined no response needed or escalated"
                }

        except Exception as e:
            logger.error(f"SendGrid inbound webhook error: {e}")
            import traceback
            return {"status": "error", "error": "Internal server error"}


    @app.post("/api/v1/debug/simulate-email-reply")
    async def simulate_email_reply(
        conversation_id: str,
        reply_message: str,
        sender_email: str = "tloss@me.com"
    ):
        """
        Simulate receiving an email reply to test two-way conversation.
        Uses an existing conversation_id to continue the conversation.
        """
        try:
            from agents.qualification_agent import process_qualification_message
            from email_service import email_service

            sender_name = sender_email.split("@")[0].replace(".", " ").title()

            # Process the reply through AI
            result = process_qualification_message(
                conversation_id=conversation_id,
                message=reply_message,
                channel="email",
                sender_info={"email": sender_email, "first_name": sender_name}
            )

            # Send AI response
            if result["should_send"] and result.get("response"):
                html_response = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; }}
            .response {{ background: #f0f9ff; padding: 20px; border-radius: 8px; border-left: 4px solid #3b82f6; }}
            .your-message {{ background: #f9fafb; padding: 16px; border-radius: 8px; border-left: 4px solid #c9a227; margin-bottom: 16px; }}
            .footer {{ margin-top: 20px; padding-top: 16px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 12px; }}
            .progress {{ background: #ecfdf5; padding: 12px; border-radius: 6px; margin-top: 16px; }}
        </style>
    </head>
    <body>
        <p>Hi {sender_name},</p>

        <p><strong>You said:</strong></p>
        <div class="your-message">{reply_message}</div>

        <p><strong>AI Response:</strong></p>
        <div class="response">
            {result['response'].replace(chr(10), '<br>')}
        </div>

        <div class="progress">
            <strong>Qualification Progress:</strong> {result['qualification']['completion_percentage']:.0f}%
            {f"<br><strong>Missing:</strong> {', '.join(result['qualification']['missing_fields'][:3])}" if result['qualification']['missing_fields'] else ""}
        </div>

        <div class="footer">
            <p>Reply to continue the conversation.</p>
            <p style="color: #9ca3af;">Conversation ID: {conversation_id}</p>
        </div>
    </body>
    </html>
    """

                ai_from_email = os.getenv("AI_FROM_EMAIL", _DEFAULT_ORGANIZER_EMAIL)
                email_sent = email_service.send_html_email(
                    to_email=sender_email,
                    subject=f"Re: Your Mortgage Inquiry - Perennia AI",
                    html_body=html_response,
                    plain_text_body=f"Hi {sender_name},\n\nYou said: {reply_message}\n\nAI Response:\n{result['response']}\n\nQualification: {result['qualification']['completion_percentage']:.0f}%\n\n- Perennia AI",
                    from_email=ai_from_email,
                    reply_to=ai_from_email
                )

                return {
                    "status": "success",
                    "email_sent": email_sent,
                    "conversation_id": conversation_id,
                    "your_message": reply_message,
                    "ai_response": result["response"],
                    "qualification": {
                        "progress": f"{result['qualification']['completion_percentage']:.0f}%",
                        "status": result["qualification"]["status"],
                        "missing_fields": result["qualification"]["missing_fields"][:5]
                    },
                    "tone": {
                        "emotion": result["tone_analysis"]["emotional_state"]["primary_emotion"],
                        "urgency": result["tone_analysis"]["urgency"]["urgency_level"]
                    },
                    "conversation_state": result["conversation_state"]["stage"],
                    "should_escalate": result["should_escalate"]
                }
            else:
                return {
                    "status": "escalated",
                    "conversation_id": conversation_id,
                    "message": "Conversation escalated to human agent",
                    "escalation_reason": result.get("escalation_reason")
                }

        except Exception as e:
            logger.error(f"Simulate reply error: {e}")
            import traceback
            return {"status": "error", "error": "Internal server error"}


    @app.post("/api/v1/debug/start-ai-conversation")
    async def start_ai_conversation(to_email: str = "tloss@me.com"):
        """
        Send an initial AI outreach email to start a two-way conversation.
        The user can reply to this email to continue the conversation.
        """
        try:
            from email_service import email_service
            from datetime import datetime
            from services.conversation_intelligence import get_conversation_service, Channel, ConversationStage

            # Use consistent conversation ID format based on email (matches webhook)
            conv_id = f"email_{to_email.replace('@', '_').replace('.', '_')}"

            # Initialize conversation state and record the AI's first message
            conv_service = get_conversation_service()
            state = conv_service.get_or_create_conversation(conv_id, Channel.EMAIL)

            # Record AI's initial question in conversation history
            initial_ai_message = "Hi! I'm Sarah, your AI mortgage assistant. Are you looking to purchase a new home or refinance your current one?"
            state.message_history.append({
                "role": "assistant",
                "content": initial_ai_message,
                "timestamp": datetime.now().isoformat()
            })

            # Advance state past initial contact since we've sent the first question
            state.stage = ConversationStage.QUALIFICATION

            logger.info(f"Initialized conversation {conv_id} with {len(state.message_history)} messages, stage: {state.stage}")

            html_body = f"""<!DOCTYPE html>
    <html>
    <body style="font-family: Calibri, Arial, sans-serif; font-size: 11pt; color: #000000; margin: 0; padding: 20px;">
    <p>Hi there,</p>

    <p>I'm Sarah, a mortgage assistant at Perennia AI. I help people find the best mortgage options for their situation.</p>

    <p>Are you looking to purchase a new home or refinance your current mortgage?</p>

    <p>Just reply to this email and I'll guide you through the process.</p>

    <p>Best regards,<br>
    <b>Sarah</b><br>
    <span style="color: #666666;">AI Mortgage Assistant | Perennia AI</span></p>
    </body>
    </html>"""

            plain_text = f"""Hi there,

    I'm Sarah, a mortgage assistant at Perennia AI. I help people find the best mortgage options for their situation.

    Are you looking to purchase a new home or refinance your current mortgage?

    Just reply to this email and I'll guide you through the process.

    Best regards,
    Sarah
    AI Mortgage Assistant | Perennia AI"""

            # Use the reply subdomain for FROM address so replies come back to us
            import os
            ai_from_email = os.getenv("AI_FROM_EMAIL", _DEFAULT_ORGANIZER_EMAIL)

            email_sent = email_service.send_html_email(
                to_email=to_email,
                subject="Quick question about your mortgage goals - Perennia AI",
                html_body=html_body,
                plain_text_body=plain_text,
                from_email=ai_from_email,
                reply_to=ai_from_email
            )

            return {
                "status": "success" if email_sent else "failed",
                "email_sent": email_sent,
                "to": to_email,
                "from": ai_from_email,
                "reply_to": ai_from_email,
                "conversation_id": conv_id,
                "message": "Initial AI question sent! Reply to the email to continue.",
                "instruction": "Reply to this email and SendGrid will forward it to our webhook for AI response"
            }

        except Exception as e:
            logger.error(f"Start AI conversation error: {e}")
            import traceback
            return {"status": "error", "error": "Internal server error"}


    @app.post("/api/v1/debug/test-email-delivery")
    async def test_email_delivery(to_email: str, test_subject: str = "Email Delivery Test"):
        """
        Send a simple test email to diagnose delivery issues.
        Uses minimal formatting to avoid spam filters.
        """
        try:
            from email_service import email_service
            from datetime import datetime
            import os

            # Very simple plain text email
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            test_id = datetime.now().strftime('%H%M%S')

            html_body = f"""<!DOCTYPE html>
    <html>
    <body style="font-family: Arial, sans-serif; padding: 20px;">
    <p>This is a test email from Perennia AI.</p>
    <p><strong>Test ID:</strong> {test_id}</p>
    <p><strong>Timestamp:</strong> {timestamp}</p>
    <p><strong>Sent from:</strong> {email_service.from_email}</p>
    <p>If you received this, email delivery is working!</p>
    <p>- Perennia AI Team</p>
    </body>
    </html>"""

            plain_text = f"""This is a test email from Perennia AI.

    Test ID: {test_id}
    Timestamp: {timestamp}
    Sent from: {email_service.from_email}

    If you received this, email delivery is working!

    - Perennia AI Team"""

            ai_from_email = os.getenv("AI_FROM_EMAIL", _DEFAULT_ORGANIZER_EMAIL)
            email_sent = email_service.send_html_email(
                to_email=to_email,
                subject=f"{test_subject} - ID:{test_id}",
                html_body=html_body,
                plain_text_body=plain_text,
                from_email=ai_from_email,
                reply_to=ai_from_email
            )

            return {
                "status": "success" if email_sent else "failed",
                "email_sent": email_sent,
                "to_email": to_email,
                "from_email": email_service.from_email,
                "from_name": email_service.from_name,
                "test_id": test_id,
                "timestamp": timestamp,
                "subject": f"{test_subject} - ID:{test_id}",
                "note": "Check inbox, spam, junk, and all other folders"
            }

        except Exception as e:
            logger.error(f"Test email error: {e}")
            import traceback
            return {"status": "error", "error": "Internal server error"}


    @app.post("/api/v1/debug/test-appointment-confirmation-email", tags=["Debug"])
    async def test_appointment_confirmation_email(
        to_email: str = "tloss@me.com",
        contact_name: str = "Test User",
        lo_name: str = "Tim Loss",
        appointment_date: str = "Monday, December 30, 2025 at 02:00 PM"
    ):
        """
        Send a test appointment confirmation email to verify the email template works.
        """
        try:
            from services.notification_service import NotificationService
            from datetime import datetime

            notification_service = NotificationService()

            html_content = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <h2 style="color: #1e40af;">Appointment Confirmed!</h2>
                <p>Hi {contact_name},</p>
                <p>Your appointment has been scheduled:</p>

                <div style="background: #f3f4f6; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <p style="margin: 0;"><strong>Date & Time:</strong> {appointment_date}</p>
                    <p style="margin: 10px 0 0 0;"><strong>Duration:</strong> 30 minutes</p>
                    <p style="margin: 10px 0 0 0;"><strong>With:</strong> {lo_name}</p>
                </div>

                <p>{lo_name} will call you at the scheduled time to discuss your mortgage needs.</p>

                <p style="color: #6b7280; font-size: 14px; margin-top: 30px;">
                    Need to reschedule? Reply to this email or contact your loan officer.
                </p>
            </div>
            """

            result = notification_service.send_email(
                to_email=to_email,
                subject=f"Appointment Confirmed with {lo_name}",
                html_content=html_content
            )

            return {
                "status": "success" if result else "failed",
                "email_sent": result,
                "to_email": to_email,
                "subject": f"Appointment Confirmed with {lo_name}",
                "contact_name": contact_name,
                "appointment_date": appointment_date,
                "lo_name": lo_name,
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Test appointment confirmation email error: {e}")
            return {"status": "error", "error": "Internal server error"}


    @app.get("/debug/test-import")
    async def debug_test_import():
        """Test importing the smart scheduler modules"""
        results = {"errors": [], "success": []}

        try:
            import pytz
            results["success"].append("pytz")
        except Exception as e:
            logger.error(f"pytz import failed: {e}")
            results["errors"].append(f"pytz: import failed")

        try:
            from services.notification_service import notification_service
            results["success"].append("notification_service")
        except Exception as e:
            logger.error(f"notification_service import failed: {e}")
            results["errors"].append(f"notification_service: import failed")

        try:
            from smart_scheduler_models import create_smart_scheduler_models
            results["success"].append("smart_scheduler_models")
        except Exception as e:
            logger.error(f"smart_scheduler_models import failed: {e}")
            results["errors"].append(f"smart_scheduler_models: import failed")

        try:
            from smart_scheduler_routes import router as smart_scheduler_router
            results["success"].append("smart_scheduler_routes")
            results["router_routes"] = len(smart_scheduler_router.routes)
        except Exception as e:
            import traceback
            results["errors"].append(f"smart_scheduler_routes: {type(e).__name__}")
            logger.error(f"Smart scheduler debug failed: {traceback.format_exc()}")

        return results


    # Extracted to routes/health_routes.py
    # (health/detailed, health/ready, health/live, health/pool, health/cache)

    # Extracted to routes/cache_routes.py and routes/admin_ops_routes.py
    # (cache/status, cache/metrics, cache/clear, cache/invalidate/user,
    #  authentication/test, admin setup migrations, create-zapier-api-key)

    # Extracted to routes/email_management_routes.py
    # (user onboarding, email-signature, email-drafts, generate-call-summary)

    # Extracted to routes/api_key_routes.py and routes/admin_ops_routes.py
    # (contacts/search, api-keys CRUD, admin/stats, admin/users CRUD,
    #  debug/user-deletion-blockers, admin/cleanup-sample-users)


    logger.info("Debug data & email routes loaded")
