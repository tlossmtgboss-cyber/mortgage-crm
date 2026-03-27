"""
Smart Docs Cron Tasks — Tenant-Isolated

Periodic tasks for the document management system:
- Document follow-up processing
- Expiration checks
- Auto-renewal scheduling
- Integrity verification
- E-signature reminders
- SLA monitoring
- Cleanup tasks
- Call intelligence processing

CRITICAL: Every task processes data PER ORGANIZATION to prevent cross-tenant
data leakage. A failure in one org's processing does not affect other orgs.

Each task is a standalone async function that manages its own DB session.
"""

import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Configurable audit retention — 7 years default for mortgage compliance (TRID/RESPA).
# Override via AUDIT_RETENTION_DAYS env var.
DEFAULT_AUDIT_RETENTION_DAYS = 2555  # ~7 years
MINIMUM_AUDIT_RETENTION_DAYS = 2555  # Floor — never go below 7 years


def _get_audit_retention_days() -> int:
    """Get configurable audit retention period, enforcing 7-year minimum."""
    try:
        configured = int(os.environ.get("AUDIT_RETENTION_DAYS", str(DEFAULT_AUDIT_RETENTION_DAYS)))
    except (ValueError, TypeError):
        configured = DEFAULT_AUDIT_RETENTION_DAYS
    return max(configured, MINIMUM_AUDIT_RETENTION_DAYS)


# =============================================================================
# HELPERS
# =============================================================================

def _get_active_organizations(db) -> List[int]:
    """Return list of active organization IDs.

    Used by every cron task to iterate per-org.
    """
    from sqlalchemy import text as sa_text
    rows = db.execute(sa_text(
        "SELECT id FROM organizations WHERE is_active = true ORDER BY id"
    )).fetchall()
    return [row[0] for row in rows]


# =============================================================================
# Follow-up Processing (runs every 15 minutes)
# =============================================================================

def _process_org_followups(db, org_id: int) -> Dict:
    """Process follow-up campaigns for a single organization."""
    from sqlalchemy import text as sa_text

    now = datetime.now(timezone.utc)

    # Find due campaigns scoped to this org (campaigns have organization_id)
    campaigns = db.execute(sa_text("""
        SELECT id FROM document_followup_campaigns
        WHERE organization_id = :org_id
            AND status = 'ACTIVE'
            AND next_action_at <= :now
        ORDER BY next_action_at ASC
        LIMIT 100
    """), {"org_id": org_id, "now": now}).fetchall()

    if not campaigns:
        return {"org_id": org_id, "processed": 0, "succeeded": 0, "failed": 0}

    from services.smart_docs.followup_automation_service import get_followup_automation_service
    service = get_followup_automation_service(db)

    processed = 0
    succeeded = 0
    failed = 0

    for campaign_row in campaigns:
        try:
            step_result = service.execute_campaign_step(campaign_row[0])
            processed += 1
            if step_result.get("error"):
                failed += 1
            else:
                succeeded += 1
        except Exception as e:
            logger.exception(
                "Error processing campaign %d for org_id=%d: %s",
                campaign_row[0], org_id, e,
            )
            processed += 1
            failed += 1

    return {
        "org_id": org_id,
        "processed": processed,
        "succeeded": succeeded,
        "failed": failed,
    }


async def process_document_followups() -> Dict:
    """
    Process pending follow-up campaign actions, per organization.

    Finds campaigns with next_action_at <= now and executes the next step.
    This is the main heartbeat of the automated follow-up system.

    Schedule: Every 15 minutes
    """
    from database import SessionLocal, get_db_with_tenant

    # Get org list with an un-scoped session
    db = SessionLocal()
    try:
        org_ids = _get_active_organizations(db)
    finally:
        db.close()

    logger.info("Follow-up processing: found %d active organizations", len(org_ids))

    total = {"processed": 0, "succeeded": 0, "failed": 0, "orgs_processed": 0, "org_errors": 0}

    for org_id in org_ids:
        try:
            with get_db_with_tenant(org_id) as tenant_db:
                result = _process_org_followups(tenant_db, org_id)
                total["processed"] += result.get("processed", 0)
                total["succeeded"] += result.get("succeeded", 0)
                total["failed"] += result.get("failed", 0)
                total["orgs_processed"] += 1
                if result.get("processed", 0) > 0:
                    logger.info("Follow-up processing org_id=%d: %s", org_id, result)
                tenant_db.commit()
        except Exception as e:
            total["org_errors"] += 1
            logger.exception("Follow-up processing failed for org_id=%d: %s", org_id, e)

    logger.info("Follow-up processing complete: %s", total)
    return total


# =============================================================================
# Document Expiration Check (runs daily at 6am)
# =============================================================================

def _process_org_expirations(db, org_id: int) -> Dict:
    """Check for expired and expiring documents for a single organization."""
    from sqlalchemy import text as sa_text

    expired_count = 0
    expiring_soon_count = 0
    campaigns_created = 0
    now = datetime.now(timezone.utc)

    # Find expired documents scoped to this org via loan join
    expired_docs = db.execute(sa_text("""
        SELECT sd.id, sd.loan_id, sd.borrower_id, sd.doc_type, sd.doc_expires_at,
               sr.id as request_id
        FROM smart_documents sd
        JOIN loans lo ON lo.id = sd.loan_id
        LEFT JOIN smart_document_requests sr ON sr.id = sd.request_id
        WHERE lo.organization_id = :org_id
            AND sd.doc_expires_at IS NOT NULL
            AND sd.doc_expires_at < :now
            AND sd.is_expired = false
            AND sd.status NOT IN ('DELETED', 'SUPERSEDED', 'EXPIRED')
    """), {"org_id": org_id, "now": now}).fetchall()

    for doc in expired_docs:
        # Mark as expired
        db.execute(sa_text("""
            UPDATE smart_documents SET is_expired = true, status = 'EXPIRED',
                updated_at = :now WHERE id = :doc_id
        """), {"now": now, "doc_id": doc.id})

        # Reset request to OPEN for re-upload
        if doc.request_id:
            db.execute(sa_text("""
                UPDATE smart_document_requests SET status = 'OPEN',
                    updated_at = :now WHERE id = :req_id
            """), {"now": now, "req_id": doc.request_id})

        expired_count += 1

        # Create follow-up campaign for expired doc
        try:
            if doc.request_id:
                from services.smart_docs.followup_automation_service import get_followup_automation_service
                service = get_followup_automation_service(db)
                service.create_campaign(
                    loan_id=doc.loan_id,
                    borrower_id=doc.borrower_id,
                    organization_id=org_id,
                    campaign_type="DOCUMENT_EXPIRED",
                    request_ids=[doc.request_id],
                )
                campaigns_created += 1
        except Exception as e:
            logger.warning(
                "Failed to create expiration campaign for doc %s org_id=%d: %s",
                doc.id, org_id, e,
            )

    # Find documents expiring within 7 days, scoped to org
    expiring_docs = db.execute(sa_text("""
        SELECT sd.id, sd.loan_id, sd.borrower_id, sd.doc_type, sd.doc_expires_at,
               sd.days_until_expiration
        FROM smart_documents sd
        JOIN loans lo ON lo.id = sd.loan_id
        WHERE lo.organization_id = :org_id
            AND sd.doc_expires_at IS NOT NULL
            AND sd.doc_expires_at BETWEEN :now AND :future
            AND sd.is_expired = false
            AND sd.status IN ('APPROVED', 'UPLOADED')
    """), {
        "org_id": org_id,
        "now": now,
        "future": now + timedelta(days=7),
    }).fetchall()

    for doc in expiring_docs:
        days_left = (doc.doc_expires_at - now).days
        db.execute(sa_text("""
            UPDATE smart_documents SET days_until_expiration = :days,
                updated_at = :now WHERE id = :doc_id
        """), {"days": days_left, "now": now, "doc_id": doc.id})
        expiring_soon_count += 1

    return {
        "org_id": org_id,
        "expired_count": expired_count,
        "expiring_soon_count": expiring_soon_count,
        "campaigns_created": campaigns_created,
    }


async def check_document_expirations() -> Dict:
    """
    Check for expiring and expired documents, per organization.

    For expiring documents (within 7 days):
    - Update days_until_expiration
    For expired documents:
    - Mark as EXPIRED
    - Reset associated request to OPEN
    - Start urgent follow-up campaign

    Schedule: Daily at 6:00 AM
    """
    from database import SessionLocal, get_db_with_tenant

    db = SessionLocal()
    try:
        org_ids = _get_active_organizations(db)
    finally:
        db.close()

    logger.info("Expiration check: found %d active organizations", len(org_ids))

    total = {
        "expired_count": 0, "expiring_soon_count": 0,
        "campaigns_created": 0, "orgs_processed": 0, "org_errors": 0,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }

    for org_id in org_ids:
        try:
            with get_db_with_tenant(org_id) as tenant_db:
                result = _process_org_expirations(tenant_db, org_id)
                total["expired_count"] += result["expired_count"]
                total["expiring_soon_count"] += result["expiring_soon_count"]
                total["campaigns_created"] += result["campaigns_created"]
                total["orgs_processed"] += 1
                if result["expired_count"] or result["expiring_soon_count"]:
                    logger.info("Expiration check org_id=%d: %s", org_id, result)
                tenant_db.commit()
        except Exception as e:
            total["org_errors"] += 1
            logger.exception("Expiration check failed for org_id=%d: %s", org_id, e)

    logger.info("Expiration check complete: %s", total)
    return total


# =============================================================================
# Auto-Renewal Processing (runs daily at 7am)
# =============================================================================

def _process_org_auto_renewals(db, org_id: int) -> Dict:
    """Process auto-renewal requests for a single organization."""
    from sqlalchemy import text as sa_text

    now = datetime.now(timezone.utc)
    renewed_count = 0

    # Find requests due for auto-renewal, scoped to org via loan join
    due_renewals = db.execute(sa_text("""
        SELECT sdr.id, sdr.loan_id, sdr.borrower_id, sdr.doc_type,
               sdr.title, sdr.freshness_days, sdr.payroll_frequency,
               sdr.next_expected_available_at
        FROM smart_document_requests sdr
        JOIN loans lo ON lo.id = sdr.loan_id
        WHERE lo.organization_id = :org_id
            AND sdr.auto_renew = true
            AND sdr.is_active = true
            AND sdr.status = 'ACCEPTED'
            AND sdr.next_expected_available_at IS NOT NULL
            AND sdr.next_expected_available_at <= :now
    """), {"org_id": org_id, "now": now}).fetchall()

    for req in due_renewals:
        # Deactivate old request
        db.execute(sa_text("""
            UPDATE smart_document_requests SET is_active = false,
                updated_at = :now WHERE id = :req_id
        """), {"now": now, "req_id": req.id})

        # Calculate next expected date based on payroll frequency
        freq_days = {
            "WEEKLY": 7, "BIWEEKLY": 14,
            "SEMIMONTHLY": 15, "MONTHLY": 30
        }
        next_days = freq_days.get(req.payroll_frequency, 30)
        next_expected = now + timedelta(days=next_days)

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
            "now": now,
        })

        renewed_count += 1

    return {"org_id": org_id, "renewed_count": renewed_count}


async def process_auto_renewals() -> Dict:
    """
    Process auto-renewal requests for documents like paystubs, per organization.

    When a paystub's freshness expires (30 days), and auto_renew is True,
    automatically create a new request for a fresh paystub.

    Schedule: Daily at 7:00 AM
    """
    from database import SessionLocal, get_db_with_tenant

    db = SessionLocal()
    try:
        org_ids = _get_active_organizations(db)
    finally:
        db.close()

    logger.info("Auto-renewal: found %d active organizations", len(org_ids))

    total = {"renewed_count": 0, "orgs_processed": 0, "org_errors": 0}

    for org_id in org_ids:
        try:
            with get_db_with_tenant(org_id) as tenant_db:
                result = _process_org_auto_renewals(tenant_db, org_id)
                total["renewed_count"] += result["renewed_count"]
                total["orgs_processed"] += 1
                if result["renewed_count"] > 0:
                    logger.info("Auto-renewal org_id=%d: %s", org_id, result)
                tenant_db.commit()
        except Exception as e:
            total["org_errors"] += 1
            logger.exception("Auto-renewal failed for org_id=%d: %s", org_id, e)

    logger.info("Auto-renewal complete: %s", total)
    return total


# =============================================================================
# E-Signature Reminders (runs every 4 hours)
# =============================================================================

def _process_org_esign_reminders(db, org_id: int) -> Dict:
    """Process e-signature reminders for a single organization."""
    from sqlalchemy import text as sa_text

    now = datetime.now(timezone.utc)
    reminders_sent = 0
    expired_count = 0

    # Expire old envelopes for this org
    expired_result = db.execute(sa_text("""
        UPDATE esignature_envelopes
        SET status = 'EXPIRED', updated_at = :now
        WHERE organization_id = :org_id
            AND status IN ('SENT', 'VIEWED', 'PARTIALLY_SIGNED')
            AND expires_at < :now
        RETURNING id
    """), {"now": now, "org_id": org_id})
    expired_count = len(expired_result.fetchall())

    # Find envelopes needing reminders for this org
    pending = db.execute(sa_text("""
        SELECT id, envelope_uuid, title, reminder_frequency_hours,
               last_reminder_sent_at, sent_at
        FROM esignature_envelopes
        WHERE organization_id = :org_id
            AND status IN ('SENT', 'VIEWED', 'PARTIALLY_SIGNED')
            AND expires_at > :now
            AND (
                (last_reminder_sent_at IS NULL
                 AND sent_at < :reminder_threshold)
                OR
                (last_reminder_sent_at IS NOT NULL
                 AND last_reminder_sent_at < :now - (reminder_frequency_hours || ' hours')::interval)
            )
    """), {
        "org_id": org_id,
        "now": now,
        "reminder_threshold": now - timedelta(hours=48),
    }).fetchall()

    for envelope in pending:
        try:
            from services.smart_docs.esignature_envelope_service import get_esignature_envelope_service
            service = get_esignature_envelope_service(db)
            service.send_reminder(envelope.envelope_uuid)
            reminders_sent += 1
        except Exception as e:
            logger.warning(
                "Failed to send reminder for envelope %s org_id=%d: %s",
                envelope.envelope_uuid, org_id, e,
            )

    return {
        "org_id": org_id,
        "reminders_sent": reminders_sent,
        "expired_count": expired_count,
    }


async def send_esignature_reminders() -> Dict:
    """
    Send reminders for pending e-signature envelopes, per organization.

    Schedule: Every 4 hours
    """
    from database import SessionLocal, get_db_with_tenant

    db = SessionLocal()
    try:
        org_ids = _get_active_organizations(db)
    finally:
        db.close()

    logger.info("E-sign reminders: found %d active organizations", len(org_ids))

    total = {"reminders_sent": 0, "expired_count": 0, "orgs_processed": 0, "org_errors": 0}

    for org_id in org_ids:
        try:
            with get_db_with_tenant(org_id) as tenant_db:
                result = _process_org_esign_reminders(tenant_db, org_id)
                total["reminders_sent"] += result["reminders_sent"]
                total["expired_count"] += result["expired_count"]
                total["orgs_processed"] += 1
                if result["reminders_sent"] or result["expired_count"]:
                    logger.info("E-sign reminders org_id=%d: %s", org_id, result)
                tenant_db.commit()
        except Exception as e:
            total["org_errors"] += 1
            logger.exception("E-sign reminders failed for org_id=%d: %s", org_id, e)

    logger.info("E-sign reminders complete: %s", total)
    return total


# =============================================================================
# Document Integrity Verification (runs daily at 2am)
# =============================================================================

def _process_org_integrity(db, org_id: int) -> Dict:
    """Verify document integrity for a single organization."""
    from sqlalchemy import text as sa_text

    now = datetime.now(timezone.utc)
    checked = 0
    tampered = 0
    errors = 0

    # Get a sample of approved documents for this org (via loan join)
    sample = db.execute(sa_text("""
        SELECT sd.id, sd.storage_key, sd.file_size
        FROM smart_documents sd
        JOIN loans lo ON lo.id = sd.loan_id
        WHERE lo.organization_id = :org_id
            AND sd.status = 'APPROVED'
            AND sd.storage_key IS NOT NULL
        ORDER BY RANDOM()
        LIMIT 50
    """), {"org_id": org_id}).fetchall()

    if not sample:
        return {"org_id": org_id, "checked": 0, "tampered": 0, "errors": 0}

    from services.smart_docs.s3_storage_service import get_smart_docs_s3_service
    s3 = get_smart_docs_s3_service()

    for doc in sample:
        try:
            if s3.is_available:
                exists = s3.file_exists(doc.storage_key)
                if not exists:
                    tampered += 1
                    logger.warning(
                        "Document %s missing from S3 org_id=%d: %s",
                        doc.id, org_id, doc.storage_key,
                    )

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
                        "now": now,
                    })

                checked += 1
        except Exception as e:
            errors += 1
            logger.warning(
                "Integrity check failed for doc %s org_id=%d: %s",
                doc.id, org_id, e,
            )

    return {"org_id": org_id, "checked": checked, "tampered": tampered, "errors": errors}


async def verify_document_integrity() -> Dict:
    """
    Periodic integrity check on a sample of documents, per organization.

    Checks a random sample of documents to ensure they haven't been tampered with.

    Schedule: Daily at 2:00 AM
    """
    from database import SessionLocal, get_db_with_tenant

    db = SessionLocal()
    try:
        org_ids = _get_active_organizations(db)
    finally:
        db.close()

    logger.info("Integrity verification: found %d active organizations", len(org_ids))

    total = {"checked": 0, "tampered": 0, "errors": 0, "orgs_processed": 0, "org_errors": 0}

    for org_id in org_ids:
        try:
            with get_db_with_tenant(org_id) as tenant_db:
                result = _process_org_integrity(tenant_db, org_id)
                total["checked"] += result["checked"]
                total["tampered"] += result["tampered"]
                total["errors"] += result["errors"]
                total["orgs_processed"] += 1
                if result["checked"] > 0:
                    logger.info("Integrity verification org_id=%d: %s", org_id, result)
                tenant_db.commit()
        except Exception as e:
            total["org_errors"] += 1
            logger.exception("Integrity verification failed for org_id=%d: %s", org_id, e)

    logger.info("Integrity verification complete: %s", total)
    return total


# =============================================================================
# Call Intelligence Processing (runs every 30 minutes)
# =============================================================================

def _process_org_call_intelligence(db, org_id: int) -> Dict:
    """Process call intelligence for document needs for a single organization."""
    from sqlalchemy import text as sa_text

    now = datetime.now(timezone.utc)
    analyzed = 0
    needs_detected = 0
    requests_created = 0

    from services.smart_docs.call_intel_extractor import get_call_intel_extractor
    extractor = get_call_intel_extractor(db)

    # Find recent calls scoped to this org via activities.organization_id
    unprocessed = db.execute(sa_text("""
        SELECT DISTINCT a.id, a.content, a.lead_id,
               l.id as loan_id
        FROM activities a
        LEFT JOIN leads ld ON ld.id = a.lead_id
        LEFT JOIN loans l ON l.loan_number = ld.loan_number
        WHERE a.organization_id = :org_id
            AND a.type = 'Call'
            AND a.content IS NOT NULL
            AND LENGTH(a.content) > 100
            AND a.created_at >= :since
            AND a.id NOT IN (
                SELECT COALESCE(call_id, 0) FROM call_intel_document_needs
                WHERE call_id IS NOT NULL
            )
        ORDER BY a.created_at DESC
        LIMIT 20
    """), {"org_id": org_id, "since": now - timedelta(hours=24)}).fetchall()

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
            logger.warning(
                "Call analysis failed for call %s org_id=%d: %s",
                call.id, org_id, e,
            )

    return {
        "org_id": org_id,
        "analyzed": analyzed,
        "needs_detected": needs_detected,
        "requests_created": requests_created,
    }


async def process_call_intelligence_for_documents() -> Dict:
    """
    Process recent call transcripts to extract document needs, per organization.

    Finds calls that haven't been analyzed for document needs yet,
    runs the call intelligence extractor, and creates document requests.

    Schedule: Every 30 minutes
    """
    from database import SessionLocal, get_db_with_tenant

    db = SessionLocal()
    try:
        org_ids = _get_active_organizations(db)
    finally:
        db.close()

    logger.info("Call intel processing: found %d active organizations", len(org_ids))

    total = {
        "analyzed": 0, "needs_detected": 0,
        "requests_created": 0, "orgs_processed": 0, "org_errors": 0,
    }

    for org_id in org_ids:
        try:
            with get_db_with_tenant(org_id) as tenant_db:
                result = _process_org_call_intelligence(tenant_db, org_id)
                total["analyzed"] += result["analyzed"]
                total["needs_detected"] += result["needs_detected"]
                total["requests_created"] += result["requests_created"]
                total["orgs_processed"] += 1
                if result["analyzed"] > 0:
                    logger.info("Call intel processing org_id=%d: %s", org_id, result)
                tenant_db.commit()
        except Exception as e:
            total["org_errors"] += 1
            logger.exception("Call intel processing failed for org_id=%d: %s", org_id, e)

    logger.info("Call intel processing complete: %s", total)
    return total


# =============================================================================
# SLA Monitoring (runs hourly)
# =============================================================================

def _process_org_sla_monitoring(db, org_id: int) -> Dict:
    """Monitor document SLAs for a single organization."""
    from sqlalchemy import text as sa_text

    now = datetime.now(timezone.utc)

    # Find requests approaching SLA (within 4 hours), scoped to org via loan
    approaching = db.execute(sa_text("""
        SELECT sdr.id, sdr.loan_id, sdr.title, sdr.sla_due_at
        FROM smart_document_requests sdr
        JOIN loans lo ON lo.id = sdr.loan_id
        WHERE lo.organization_id = :org_id
            AND sdr.status = 'OPEN'
            AND sdr.is_active = true
            AND sdr.sla_due_at IS NOT NULL
            AND sdr.sla_due_at BETWEEN :now AND :warning_threshold
    """), {
        "org_id": org_id,
        "now": now,
        "warning_threshold": now + timedelta(hours=4),
    }).fetchall()

    # Find breached SLAs, scoped to org via loan
    breached = db.execute(sa_text("""
        SELECT sdr.id, sdr.loan_id, sdr.title, sdr.sla_due_at
        FROM smart_document_requests sdr
        JOIN loans lo ON lo.id = sdr.loan_id
        WHERE lo.organization_id = :org_id
            AND sdr.status = 'OPEN'
            AND sdr.is_active = true
            AND sdr.sla_due_at IS NOT NULL
            AND sdr.sla_due_at < :now
    """), {"org_id": org_id, "now": now}).fetchall()

    return {
        "org_id": org_id,
        "sla_warnings": len(approaching),
        "sla_breaches": len(breached),
    }


async def monitor_document_slas() -> Dict:
    """
    Monitor document request SLAs and create alerts for breaches, per organization.

    Schedule: Every hour
    """
    from database import SessionLocal, get_db_with_tenant

    # Get org list with an un-scoped session
    db = SessionLocal()
    try:
        org_ids = _get_active_organizations(db)
    finally:
        db.close()

    logger.info("SLA monitoring: found %d active organizations", len(org_ids))

    total = {"sla_breaches": 0, "sla_warnings": 0, "orgs_processed": 0, "org_errors": 0}

    for org_id in org_ids:
        try:
            with get_db_with_tenant(org_id) as tenant_db:
                result = _process_org_sla_monitoring(tenant_db, org_id)
                total["sla_breaches"] += result["sla_breaches"]
                total["sla_warnings"] += result["sla_warnings"]
                total["orgs_processed"] += 1
                if result["sla_breaches"] or result["sla_warnings"]:
                    logger.info("SLA monitoring org_id=%d: %s", org_id, result)
                tenant_db.commit()
        except Exception as e:
            total["org_errors"] += 1
            logger.exception("SLA monitoring failed for org_id=%d: %s", org_id, e)

    logger.info("SLA monitoring complete: %s", total)
    return total


# =============================================================================
# Cleanup Task (runs daily at 3am)
# =============================================================================

def _process_org_cleanup(db, org_id: int, retention_days: int) -> Dict:
    """Cleanup old/orphaned data for a single organization."""
    from sqlalchemy import text as sa_text

    now = datetime.now(timezone.utc)
    cleaned = {}

    # Expire old signing tokens for this org's envelopes
    result = db.execute(sa_text("""
        UPDATE esignature_recipients er
        SET status = 'EXPIRED'
        FROM esignature_envelopes ee
        WHERE er.envelope_id = ee.id
            AND ee.organization_id = :org_id
            AND er.signing_token_expires_at < :now
            AND er.status IN ('PENDING', 'SENT', 'DELIVERED')
    """), {"now": now, "org_id": org_id})
    cleaned["expired_signing_tokens"] = result.rowcount

    # Count archivable follow-up events for this org (audit only, no deletion).
    # REGULATORY: TRID requires minimum 3-year retention (12 CFR 1026.25).
    # Default is 7 years per IRS guidance. Never delete — only count for
    # archival by the decision_audit_service.archive_expired_records() task.
    old_events = db.execute(sa_text("""
        SELECT COUNT(*) FROM document_followup_events
        WHERE organization_id = :org_id
            AND created_at < :cutoff
    """), {
        "org_id": org_id,
        "cutoff": now - timedelta(days=retention_days),
    }).scalar()
    cleaned["archivable_followup_events"] = old_events or 0
    cleaned["retention_days"] = retention_days

    return {"org_id": org_id, **cleaned}


async def cleanup_smart_docs() -> Dict:
    """
    Cleanup old/orphaned data per organization:
    - Remove expired signing tokens
    - Count archivable follow-up events (7-year retention, configurable)

    Schedule: Daily at 3:00 AM
    """
    from database import SessionLocal, get_db_with_tenant

    retention_days = _get_audit_retention_days()

    # Get org list with an un-scoped session
    db = SessionLocal()
    try:
        org_ids = _get_active_organizations(db)
    finally:
        db.close()

    logger.info(
        "Cleanup: found %d active organizations, retention=%d days",
        len(org_ids), retention_days,
    )

    total = {
        "expired_signing_tokens": 0,
        "archivable_followup_events": 0,
        "retention_days": retention_days,
        "orgs_processed": 0,
        "org_errors": 0,
    }

    for org_id in org_ids:
        try:
            with get_db_with_tenant(org_id) as tenant_db:
                result = _process_org_cleanup(tenant_db, org_id, retention_days)
                total["expired_signing_tokens"] += result.get("expired_signing_tokens", 0)
                total["archivable_followup_events"] += result.get("archivable_followup_events", 0)
                total["orgs_processed"] += 1
                if result.get("expired_signing_tokens", 0) > 0:
                    logger.info("Cleanup org_id=%d: %s", org_id, result)
                tenant_db.commit()
        except Exception as e:
            total["org_errors"] += 1
            logger.exception("Cleanup failed for org_id=%d: %s", org_id, e)

    logger.info("Cleanup complete: %s", total)
    return total


# =============================================================================
# Task Registry (for scheduler integration)
# =============================================================================

SMART_DOCS_CRON_TASKS = {
    "process_document_followups": {
        "func": process_document_followups,
        "schedule": "*/15 * * * *",  # Every 15 minutes
        "description": "Process pending follow-up campaign actions (per org)",
    },
    "check_document_expirations": {
        "func": check_document_expirations,
        "schedule": "0 6 * * *",  # Daily at 6am
        "description": "Check for expiring and expired documents (per org)",
    },
    "process_auto_renewals": {
        "func": process_auto_renewals,
        "schedule": "0 7 * * *",  # Daily at 7am
        "description": "Process auto-renewal document requests (per org)",
    },
    "send_esignature_reminders": {
        "func": send_esignature_reminders,
        "schedule": "0 */4 * * *",  # Every 4 hours
        "description": "Send e-signature reminders (per org)",
    },
    "verify_document_integrity": {
        "func": verify_document_integrity,
        "schedule": "0 2 * * *",  # Daily at 2am
        "description": "Verify document integrity (per org)",
    },
    "process_call_intelligence_for_documents": {
        "func": process_call_intelligence_for_documents,
        "schedule": "*/30 * * * *",  # Every 30 minutes
        "description": "Process call transcripts for document needs (per org)",
    },
    "monitor_document_slas": {
        "func": monitor_document_slas,
        "schedule": "0 * * * *",  # Every hour
        "description": "Monitor document request SLAs (per org)",
    },
    "cleanup_smart_docs": {
        "func": cleanup_smart_docs,
        "schedule": "0 3 * * *",  # Daily at 3am
        "description": "Cleanup old/orphaned data (per org)",
    },
}
