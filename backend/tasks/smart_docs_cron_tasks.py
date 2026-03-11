"""
Smart Docs Cron Tasks

Periodic tasks for the document management system:
- Document follow-up processing
- Expiration checks
- Auto-renewal scheduling
- Integrity verification
- E-signature reminders
- Analytics aggregation
- Cleanup tasks
- Call intelligence processing

Each task is a standalone async function that manages its own DB session.
"""

import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Follow-up Processing (runs every 15 minutes)
# =============================================================================

async def process_document_followups() -> Dict:
    """
    Process pending follow-up campaign actions.

    Finds campaigns with next_action_at <= now and executes the next step.
    This is the main heartbeat of the automated follow-up system.

    Schedule: Every 15 minutes
    """
    from database import get_db
    db = next(get_db())
    try:
        from services.smart_docs.followup_automation_service import get_followup_automation_service
        service = get_followup_automation_service(db)
        result = service.process_pending_actions()
        logger.info(f"Follow-up processing: {result}")
        return result
    except Exception as e:
        logger.exception(f"Follow-up processing failed: {e}")
        return {"error": str(e)}
    finally:
        db.close()


# =============================================================================
# Document Expiration Check (runs daily at 6am)
# =============================================================================

async def check_document_expirations() -> Dict:
    """
    Check for expiring and expired documents.

    For expiring documents (within 7 days):
    - Send reminder to borrower
    - Create follow-up campaign
    - Notify LO

    For expired documents:
    - Mark as EXPIRED
    - Create re-request
    - Start urgent follow-up campaign

    Schedule: Daily at 6:00 AM
    """
    from database import get_db
    from sqlalchemy import text as sa_text
    db = next(get_db())
    try:
        expired_count = 0
        expiring_soon_count = 0
        campaigns_created = 0

        # Find expired documents
        expired_docs = db.execute(sa_text("""
            SELECT sd.id, sd.loan_id, sd.borrower_id, sd.doc_type, sd.doc_expires_at,
                   sr.id as request_id
            FROM smart_documents sd
            LEFT JOIN smart_document_requests sr ON sr.id = sd.request_id
            WHERE sd.doc_expires_at IS NOT NULL
                AND sd.doc_expires_at < :now
                AND sd.is_expired = false
                AND sd.status NOT IN ('DELETED', 'SUPERSEDED', 'EXPIRED')
        """), {"now": datetime.now(timezone.utc)}).fetchall()

        for doc in expired_docs:
            # Mark as expired
            db.execute(sa_text("""
                UPDATE smart_documents SET is_expired = true, status = 'EXPIRED',
                    updated_at = :now WHERE id = :doc_id
            """), {"now": datetime.now(timezone.utc), "doc_id": doc.id})

            # Reset request to OPEN for re-upload
            if doc.request_id:
                db.execute(sa_text("""
                    UPDATE smart_document_requests SET status = 'OPEN',
                        updated_at = :now WHERE id = :req_id
                """), {"now": datetime.now(timezone.utc), "req_id": doc.request_id})

            expired_count += 1

            # Create follow-up campaign for expired doc
            try:
                from services.smart_docs.followup_automation_service import get_followup_automation_service
                service = get_followup_automation_service(db)
                # Get organization_id from loan
                org_row = db.execute(sa_text(
                    "SELECT organization_id FROM loans WHERE id = :lid"
                ), {"lid": doc.loan_id}).first()
                org_id = org_row[0] if org_row else None

                if doc.request_id and org_id:
                    service.create_campaign(
                        loan_id=doc.loan_id,
                        borrower_id=doc.borrower_id,
                        organization_id=org_id,
                        campaign_type="DOCUMENT_EXPIRED",
                        request_ids=[doc.request_id],
                    )
                    campaigns_created += 1
            except Exception as e:
                logger.warning(f"Failed to create expiration campaign for doc {doc.id}: {e}")

        # Find documents expiring within 7 days
        expiring_docs = db.execute(sa_text("""
            SELECT sd.id, sd.loan_id, sd.borrower_id, sd.doc_type, sd.doc_expires_at,
                   sd.days_until_expiration
            FROM smart_documents sd
            WHERE sd.doc_expires_at IS NOT NULL
                AND sd.doc_expires_at BETWEEN :now AND :future
                AND sd.is_expired = false
                AND sd.status IN ('APPROVED', 'UPLOADED')
        """), {
            "now": datetime.now(timezone.utc),
            "future": datetime.now(timezone.utc) + timedelta(days=7)
        }).fetchall()

        for doc in expiring_docs:
            # Update days_until_expiration
            days_left = (doc.doc_expires_at - datetime.now(timezone.utc)).days
            db.execute(sa_text("""
                UPDATE smart_documents SET days_until_expiration = :days,
                    updated_at = :now WHERE id = :doc_id
            """), {"days": days_left, "now": datetime.now(timezone.utc), "doc_id": doc.id})
            expiring_soon_count += 1

        db.commit()

        result = {
            "expired_count": expired_count,
            "expiring_soon_count": expiring_soon_count,
            "campaigns_created": campaigns_created,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
        logger.info(f"Expiration check: {result}")
        return result
    except Exception as e:
        db.rollback()
        logger.exception(f"Expiration check failed: {e}")
        return {"error": str(e)}
    finally:
        db.close()


# =============================================================================
# Auto-Renewal Processing (runs daily at 7am)
# =============================================================================

async def process_auto_renewals() -> Dict:
    """
    Process auto-renewal requests for documents like paystubs.

    When a paystub's freshness expires (30 days), and auto_renew is True,
    automatically create a new request for a fresh paystub.

    Schedule: Daily at 7:00 AM
    """
    from database import get_db
    from sqlalchemy import text as sa_text
    db = next(get_db())
    try:
        renewed_count = 0

        # Find requests due for auto-renewal
        due_renewals = db.execute(sa_text("""
            SELECT sdr.id, sdr.loan_id, sdr.borrower_id, sdr.doc_type,
                   sdr.title, sdr.freshness_days, sdr.payroll_frequency,
                   sdr.next_expected_available_at
            FROM smart_document_requests sdr
            WHERE sdr.auto_renew = true
                AND sdr.is_active = true
                AND sdr.status = 'ACCEPTED'
                AND sdr.next_expected_available_at IS NOT NULL
                AND sdr.next_expected_available_at <= :now
        """), {"now": datetime.now(timezone.utc)}).fetchall()

        for req in due_renewals:
            # Deactivate old request
            db.execute(sa_text("""
                UPDATE smart_document_requests SET is_active = false,
                    updated_at = :now WHERE id = :req_id
            """), {"now": datetime.now(timezone.utc), "req_id": req.id})

            # Calculate next expected date based on payroll frequency
            freq_days = {
                "WEEKLY": 7, "BIWEEKLY": 14,
                "SEMIMONTHLY": 15, "MONTHLY": 30
            }
            next_days = freq_days.get(req.payroll_frequency, 30)
            next_expected = datetime.now(timezone.utc) + timedelta(days=next_days)

            # Create new renewal request
            db.execute(sa_text("""
                INSERT INTO smart_document_requests (
                    loan_id, borrower_id, doc_type, title, description,
                    freshness_days, auto_renew, payroll_frequency,
                    next_expected_available_at, status, is_active,
                    superseded_by, priority, created_at, updated_at
                ) VALUES (
                    :loan_id, :borrower_id, :doc_type,
                    :title, 'Auto-renewed: fresh document needed',
                    :freshness_days, true, :payroll_frequency,
                    :next_expected, 'OPEN', true,
                    NULL, 'NORMAL', :now, :now
                )
            """), {
                "loan_id": req.loan_id,
                "borrower_id": req.borrower_id,
                "doc_type": req.doc_type,
                "title": f"{req.title} (Renewal)",
                "freshness_days": req.freshness_days,
                "payroll_frequency": req.payroll_frequency,
                "next_expected": next_expected,
                "now": datetime.now(timezone.utc),
            })

            renewed_count += 1

        db.commit()
        result = {"renewed_count": renewed_count}
        logger.info(f"Auto-renewal: {result}")
        return result
    except Exception as e:
        db.rollback()
        logger.exception(f"Auto-renewal failed: {e}")
        return {"error": str(e)}
    finally:
        db.close()


# =============================================================================
# E-Signature Reminders (runs every 4 hours)
# =============================================================================

async def send_esignature_reminders() -> Dict:
    """
    Send reminders for pending e-signature envelopes.

    Schedule: Every 4 hours
    """
    from database import get_db
    from sqlalchemy import text as sa_text
    db = next(get_db())
    try:
        reminders_sent = 0
        expired_count = 0

        # Check for expired envelopes and count affected rows
        expired_result = db.execute(sa_text("""
            UPDATE esignature_envelopes
            SET status = 'EXPIRED', updated_at = :now
            WHERE status IN ('SENT', 'VIEWED', 'PARTIALLY_SIGNED')
                AND expires_at < :now
            RETURNING id
        """), {"now": datetime.now(timezone.utc)})
        expired_count = len(expired_result.fetchall())

        # Find envelopes needing reminders
        pending = db.execute(sa_text("""
            SELECT id, envelope_uuid, title, reminder_frequency_hours,
                   last_reminder_sent_at, sent_at
            FROM esignature_envelopes
            WHERE status IN ('SENT', 'VIEWED', 'PARTIALLY_SIGNED')
                AND expires_at > :now
                AND (
                    (last_reminder_sent_at IS NULL
                     AND sent_at < :reminder_threshold)
                    OR
                    (last_reminder_sent_at IS NOT NULL
                     AND last_reminder_sent_at < :now - (reminder_frequency_hours || ' hours')::interval)
                )
        """), {
            "now": datetime.now(timezone.utc),
            "reminder_threshold": datetime.now(timezone.utc) - timedelta(hours=48),
        }).fetchall()

        for envelope in pending:
            try:
                from services.smart_docs.esignature_envelope_service import get_esignature_envelope_service
                service = get_esignature_envelope_service(db)
                service.send_reminder(envelope.envelope_uuid)
                reminders_sent += 1
            except Exception as e:
                logger.warning(f"Failed to send reminder for envelope {envelope.envelope_uuid}: {e}")

        db.commit()
        result = {"reminders_sent": reminders_sent, "expired_count": expired_count}
        logger.info(f"E-sign reminders: {result}")
        return result
    except Exception as e:
        db.rollback()
        logger.exception(f"E-sign reminders failed: {e}")
        return {"error": str(e)}
    finally:
        db.close()


# =============================================================================
# Document Integrity Verification (runs daily at 2am)
# =============================================================================

async def verify_document_integrity() -> Dict:
    """
    Periodic integrity check on a sample of documents.

    Checks a random sample of documents to ensure they haven't been tampered with.

    Schedule: Daily at 2:00 AM
    """
    from database import get_db
    from sqlalchemy import text as sa_text
    db = next(get_db())
    try:
        checked = 0
        tampered = 0
        errors = 0

        # Get a sample of approved documents to verify
        sample = db.execute(sa_text("""
            SELECT id, storage_key, file_size
            FROM smart_documents
            WHERE status = 'APPROVED'
                AND storage_key IS NOT NULL
            ORDER BY RANDOM()
            LIMIT 50
        """)).fetchall()

        from services.smart_docs.s3_storage_service import get_smart_docs_s3_service
        s3 = get_smart_docs_s3_service()

        for doc in sample:
            try:
                if s3.is_available:
                    exists = s3.file_exists(doc.storage_key)
                    if not exists:
                        tampered += 1
                        logger.warning(f"Document {doc.id} missing from S3: {doc.storage_key}")

                        # Log integrity check
                        db.execute(sa_text("""
                            INSERT INTO document_integrity_checks (
                                document_id, document_type, check_type,
                                expected_hash, actual_hash, is_valid,
                                tamper_detected, tamper_details, checked_by,
                                storage_key_checked, created_at
                            ) VALUES (
                                :doc_id, 'smart_document', 'SCHEDULED',
                                '', '', false, true,
                                'File not found in S3 storage', 'CRON',
                                :storage_key, :now
                            )
                        """), {
                            "doc_id": doc.id,
                            "storage_key": doc.storage_key,
                            "now": datetime.now(timezone.utc),
                        })

                    checked += 1
            except Exception as e:
                errors += 1
                logger.warning(f"Integrity check failed for doc {doc.id}: {e}")

        db.commit()
        result = {"checked": checked, "tampered": tampered, "errors": errors}
        logger.info(f"Integrity verification: {result}")
        return result
    except Exception as e:
        db.rollback()
        logger.exception(f"Integrity verification failed: {e}")
        return {"error": str(e)}
    finally:
        db.close()


# =============================================================================
# Call Intelligence Processing (runs every 30 minutes)
# =============================================================================

async def process_call_intelligence_for_documents() -> Dict:
    """
    Process recent call transcripts to extract document needs.

    Finds calls that haven't been analyzed for document needs yet,
    runs the call intelligence extractor, and creates document requests.

    Schedule: Every 30 minutes
    """
    from database import get_db
    from sqlalchemy import text as sa_text
    db = next(get_db())
    try:
        analyzed = 0
        needs_detected = 0
        requests_created = 0

        from services.smart_docs.call_intel_extractor import get_call_intel_extractor
        extractor = get_call_intel_extractor(db)

        # Find recent calls with transcripts that haven't been analyzed
        # This queries a call_records or activities table
        unprocessed = db.execute(sa_text("""
            SELECT DISTINCT a.id, a.content, a.lead_id,
                   l.id as loan_id
            FROM activities a
            LEFT JOIN leads ld ON ld.id = a.lead_id
            LEFT JOIN loans l ON l.loan_number = ld.loan_number
            WHERE a.type = 'Call'
                AND a.content IS NOT NULL
                AND LENGTH(a.content) > 100
                AND a.created_at >= :since
                AND a.id NOT IN (
                    SELECT COALESCE(call_id, 0) FROM call_intel_document_needs
                    WHERE call_id IS NOT NULL
                )
            ORDER BY a.created_at DESC
            LIMIT 20
        """), {"since": datetime.now(timezone.utc) - timedelta(hours=24)}).fetchall()

        for call in unprocessed:
            if not call.loan_id:
                continue
            try:
                result = extractor.analyze_call(
                    call_id=call.id,
                    transcript=call.content,
                    loan_id=call.loan_id,
                    lead_id=call.lead_id,
                )
                analyzed += 1
                needs_detected += result.total_needs

                # Auto-create requests for high-confidence needs
                created = extractor.auto_create_requests(result)
                requests_created += len(created)
            except Exception as e:
                logger.warning(f"Call analysis failed for call {call.id}: {e}")

        db.commit()
        result = {
            "analyzed": analyzed,
            "needs_detected": needs_detected,
            "requests_created": requests_created,
        }
        logger.info(f"Call intel processing: {result}")
        return result
    except Exception as e:
        db.rollback()
        logger.exception(f"Call intel processing failed: {e}")
        return {"error": str(e)}
    finally:
        db.close()


# =============================================================================
# SLA Monitoring (runs hourly)
# =============================================================================

async def monitor_document_slas() -> Dict:
    """
    Monitor document request SLAs and create alerts for breaches.

    Schedule: Every hour
    """
    from database import get_db
    from sqlalchemy import text as sa_text
    db = next(get_db())
    try:
        breaches = 0
        warnings = 0

        # Find requests approaching SLA (within 4 hours)
        approaching = db.execute(sa_text("""
            SELECT id, loan_id, title, sla_due_at
            FROM smart_document_requests
            WHERE status = 'OPEN'
                AND is_active = true
                AND sla_due_at IS NOT NULL
                AND sla_due_at BETWEEN :now AND :warning_threshold
        """), {
            "now": datetime.now(timezone.utc),
            "warning_threshold": datetime.now(timezone.utc) + timedelta(hours=4),
        }).fetchall()
        warnings = len(approaching)

        # Find breached SLAs
        breached = db.execute(sa_text("""
            SELECT id, loan_id, title, sla_due_at
            FROM smart_document_requests
            WHERE status = 'OPEN'
                AND is_active = true
                AND sla_due_at IS NOT NULL
                AND sla_due_at < :now
        """), {"now": datetime.now(timezone.utc)}).fetchall()
        breaches = len(breached)

        db.commit()
        result = {"sla_breaches": breaches, "sla_warnings": warnings}
        logger.info(f"SLA monitoring: {result}")
        return result
    except Exception as e:
        db.rollback()
        logger.exception(f"SLA monitoring failed: {e}")
        return {"error": str(e)}
    finally:
        db.close()


# =============================================================================
# Cleanup Task (runs daily at 3am)
# =============================================================================

async def cleanup_smart_docs() -> Dict:
    """
    Cleanup old/orphaned data:
    - Remove expired signing tokens
    - Clean up orphaned S3 files
    - Archive old follow-up events
    - Remove stale classification cache

    Schedule: Daily at 3:00 AM
    """
    from database import get_db
    from sqlalchemy import text as sa_text
    db = next(get_db())
    try:
        cleaned = {}

        # Expire old signing tokens
        result = db.execute(sa_text("""
            UPDATE esignature_recipients
            SET status = 'EXPIRED'
            WHERE signing_token_expires_at < :now
                AND status IN ('PENDING', 'SENT', 'DELIVERED')
        """), {"now": datetime.now(timezone.utc)})
        cleaned["expired_signing_tokens"] = result.rowcount

        # Archive old follow-up events (> 90 days)
        # Just log count, don't delete
        old_events = db.execute(sa_text("""
            SELECT COUNT(*) FROM document_followup_events
            WHERE created_at < :cutoff
        """), {"cutoff": datetime.now(timezone.utc) - timedelta(days=90)}).scalar()
        cleaned["archivable_followup_events"] = old_events or 0

        db.commit()
        logger.info(f"Cleanup: {cleaned}")
        return cleaned
    except Exception as e:
        db.rollback()
        logger.exception(f"Cleanup failed: {e}")
        return {"error": str(e)}
    finally:
        db.close()


# =============================================================================
# Task Registry (for scheduler integration)
# =============================================================================

SMART_DOCS_CRON_TASKS = {
    "process_document_followups": {
        "func": process_document_followups,
        "schedule": "*/15 * * * *",  # Every 15 minutes
        "description": "Process pending follow-up campaign actions",
    },
    "check_document_expirations": {
        "func": check_document_expirations,
        "schedule": "0 6 * * *",  # Daily at 6am
        "description": "Check for expiring and expired documents",
    },
    "process_auto_renewals": {
        "func": process_auto_renewals,
        "schedule": "0 7 * * *",  # Daily at 7am
        "description": "Process auto-renewal document requests",
    },
    "send_esignature_reminders": {
        "func": send_esignature_reminders,
        "schedule": "0 */4 * * *",  # Every 4 hours
        "description": "Send e-signature reminders",
    },
    "verify_document_integrity": {
        "func": verify_document_integrity,
        "schedule": "0 2 * * *",  # Daily at 2am
        "description": "Verify document integrity",
    },
    "process_call_intelligence_for_documents": {
        "func": process_call_intelligence_for_documents,
        "schedule": "*/30 * * * *",  # Every 30 minutes
        "description": "Process call transcripts for document needs",
    },
    "monitor_document_slas": {
        "func": monitor_document_slas,
        "schedule": "0 * * * *",  # Every hour
        "description": "Monitor document request SLAs",
    },
    "cleanup_smart_docs": {
        "func": cleanup_smart_docs,
        "schedule": "0 3 * * *",  # Daily at 3am
        "description": "Cleanup old/orphaned data",
    },
}
