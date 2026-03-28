"""
Smart Docs Delivery Workflow Routes

REST API endpoints for sending document needs lists, reminders, and portal links
to borrowers via email and/or SMS.

Endpoints:
- POST /delivery/send-needs-list     — Send full needs list to borrower
- POST /delivery/send-reminder       — Send reminder for overdue/open doc requests
- POST /delivery/send-batch          — Batch send to multiple borrowers
- POST /delivery/resend-portal-link  — Resend the portal upload URL
- GET  /delivery/history/{loan_id}   — Delivery log for a loan
"""

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from database import get_db
from auth.dependencies import get_current_user
from models.smart_docs_models import DocumentRequest, RequestStatus
from routes.smart_docs_models import _verify_loan_tenant

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/delivery",
    tags=["Smart Documents - Delivery"],
)

PORTAL_BASE_URL = "https://app.perenniaai.com/portal/docs"


# =============================================================================
# Pydantic Request / Response Models
# =============================================================================

class SendNeedsListRequest(BaseModel):
    loan_id: int
    channels: List[str] = ["email"]  # "email", "sms", or both
    message: Optional[str] = None  # Custom message from LO


class SendReminderRequest(BaseModel):
    loan_id: int
    channels: List[str] = ["email"]
    document_request_ids: Optional[List[int]] = None  # specific docs, or all open


class SendBatchRequest(BaseModel):
    loan_ids: List[int]
    channels: List[str] = ["email"]
    template: str = "needs_list"  # "needs_list" or "reminder"


class ResendPortalLinkRequest(BaseModel):
    loan_id: int
    channel: str = "email"  # "email" or "sms"


class DeliveryResult(BaseModel):
    success: bool
    loan_id: int
    channels_sent: List[str] = []
    channels_skipped: List[str] = []
    doc_count: int = 0
    portal_url: Optional[str] = None
    error: Optional[str] = None


class BatchDeliveryResult(BaseModel):
    sent: int = 0
    skipped: int = 0
    errors: int = 0
    details: List[DeliveryResult] = []


# =============================================================================
# Helpers
# =============================================================================

def _get_loan_details(db: Session, loan_id: int) -> dict:
    """Fetch borrower + LO info from the loans table."""
    row = db.execute(
        sa_text("""
            SELECT
                l.id, l.loan_number, l.borrower_name, l.borrower_email,
                l.borrower_phone, l.loan_officer_name, l.organization_id
            FROM loans l
            WHERE l.id = :loan_id
        """),
        {"loan_id": loan_id},
    ).first()
    if not row:
        return {}
    return dict(row._mapping)


def _find_workspace_slug(db: Session, loan_id: int, organization_id: int) -> Optional[str]:
    """Resolve workspace slug for a loan via purl_loans -> purl_workspaces."""
    row = db.execute(
        sa_text("""
            SELECT w.slug
            FROM purl_workspaces w
            JOIN purl_loans pl ON pl.workspace_id = w.id
            WHERE pl.main_loan_id = :loan_id
              AND w.organization_id = :org_id
            ORDER BY pl.created_at DESC
            LIMIT 1
        """),
        {"loan_id": loan_id, "org_id": organization_id},
    ).first()
    return row[0] if row else None


def _build_portal_url(workspace_slug: Optional[str]) -> Optional[str]:
    """Build the borrower portal URL for the needs list."""
    if not workspace_slug:
        return None
    return f"{PORTAL_BASE_URL}/{workspace_slug}/needs-list"


def _get_open_requests(db: Session, loan_id: int, request_ids: Optional[List[int]] = None) -> list:
    """Get open DocumentRequest objects for a loan."""
    query = db.query(DocumentRequest).filter(
        DocumentRequest.loan_id == loan_id,
        DocumentRequest.status.in_([RequestStatus.OPEN, RequestStatus.PENDING_REVIEW]),
        DocumentRequest.is_active.is_(True),
    )
    if request_ids:
        query = query.filter(DocumentRequest.id.in_(request_ids))
    return query.order_by(DocumentRequest.priority.asc(), DocumentRequest.created_at.asc()).all()


def _log_delivery(db: Session, loan_id: int, delivery_type: str, channels: list, doc_count: int, user_id: int):
    """Insert a delivery audit record into doc_policy_events."""
    try:
        db.execute(
            sa_text("""
                INSERT INTO doc_policy_events (loan_id, event_type, payload, created_at)
                VALUES (:loan_id, :event_type, :payload::jsonb, :now)
            """),
            {
                "loan_id": loan_id,
                "event_type": "EXPIRATION_REMINDER_SENT",  # Re-use existing enum value for delivery audit
                "payload": f'{{"delivery_type": "{delivery_type}", "channels": {channels}, "doc_count": {doc_count}, "sent_by": {user_id}}}',
                "now": datetime.utcnow(),
            },
        )
        db.commit()
    except Exception as e:
        logger.warning(f"Failed to log delivery event for loan {loan_id}: {e}")
        db.rollback()


def _send_email_notification(
    db: Session,
    requests: list,
    borrower_email: str,
    borrower_name: str,
    lo_name: str,
    portal_url: Optional[str],
) -> bool:
    """Send email via SmartDocsNotificationService."""
    try:
        from services.smart_docs.notification_service import SmartDocsNotificationService
        svc = SmartDocsNotificationService(db)
        if len(requests) == 1:
            return svc.send_document_request_notification(
                request=requests[0],
                borrower_email=borrower_email,
                borrower_name=borrower_name,
                loan_officer_name=lo_name,
                portal_url=portal_url,
            )
        else:
            return svc.send_bulk_request_notification(
                requests=requests,
                borrower_email=borrower_email,
                borrower_name=borrower_name,
                loan_officer_name=lo_name,
                portal_url=portal_url,
            )
    except Exception as e:
        logger.error(f"Email notification failed: {e}")
        return False


def _send_sms_notification(
    borrower_phone: str,
    borrower_name: str,
    doc_count: int,
    portal_url: str,
) -> bool:
    """Send SMS via NotificationService."""
    try:
        from services.notification_service import NotificationService
        svc = NotificationService()
        result = svc.send_document_request_sms(
            borrower_phone=borrower_phone,
            borrower_name=borrower_name,
            doc_count=doc_count,
            upload_link=portal_url or "your loan officer",
        )
        return result.get("success", False)
    except Exception as e:
        logger.error(f"SMS notification failed: {e}")
        return False


def _send_portal_link_email(
    borrower_email: str,
    borrower_name: str,
    lo_name: str,
    portal_url: str,
) -> bool:
    """Send a simple portal-link email."""
    try:
        from email_service import EmailService
        svc = EmailService()
        subject = "Your Document Upload Portal"
        html_body = f'''
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"></head>
        <body style="margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f9fafb;">
            <div style="max-width:600px;margin:0 auto;padding:24px;">
                <div style="background:white;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.1);">
                    <div style="background:#1e3a5f;padding:24px;text-align:center;">
                        <h1 style="margin:0;color:white;font-size:24px;">Document Portal</h1>
                    </div>
                    <div style="padding:24px;">
                        <p style="margin:0 0 16px;color:#374151;">Hi {borrower_name},</p>
                        <p style="margin:0 0 20px;color:#4b5563;">
                            Use the link below to securely upload documents for your mortgage application.
                        </p>
                        <div style="text-align:center;margin:24px 0;">
                            <a href="{portal_url}" style="display:inline-block;padding:14px 28px;background:#2563eb;color:white;text-decoration:none;border-radius:8px;font-weight:600;">
                                Open Document Portal
                            </a>
                        </div>
                        <p style="margin:24px 0 0;color:#6b7280;font-size:14px;">
                            If you have any questions, please reply to this email or contact your loan officer.
                        </p>
                        <p style="margin:16px 0 0;color:#374151;">
                            Best regards,<br><strong>{lo_name}</strong>
                        </p>
                    </div>
                    <div style="background:#f9fafb;padding:16px 24px;text-align:center;border-top:1px solid #e5e7eb;">
                        <p style="margin:0;color:#9ca3af;font-size:12px;">
                            This is an automated message from your loan processing team.
                        </p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        '''
        return svc.send_html_email(to_email=borrower_email, subject=subject, html_body=html_body)
    except Exception as e:
        logger.error(f"Portal link email failed: {e}")
        return False


def _send_portal_link_sms(
    borrower_phone: str,
    borrower_name: str,
    portal_url: str,
) -> bool:
    """Send a portal-link SMS."""
    try:
        from services.notification_service import NotificationService
        svc = NotificationService()
        message = (
            f"Hi {borrower_name}, here is the link to upload your mortgage documents: {portal_url}"
        )
        result = svc.send_sms(to_phone=borrower_phone, message=message)
        return result.get("success", False)
    except Exception as e:
        logger.error(f"Portal link SMS failed: {e}")
        return False


# =============================================================================
# Background task wrappers
# =============================================================================

def _bg_send_needs_list(
    loan_id: int,
    channels: List[str],
    custom_message: Optional[str],
    user_id: int,
):
    """Background task: send needs list notifications."""
    from database import SessionLocal
    db = SessionLocal()
    try:
        loan = _get_loan_details(db, loan_id)
        if not loan:
            logger.error(f"BG send-needs-list: loan {loan_id} not found")
            return

        requests = _get_open_requests(db, loan_id)
        if not requests:
            logger.info(f"BG send-needs-list: no open requests for loan {loan_id}")
            return

        workspace_slug = _find_workspace_slug(db, loan_id, loan["organization_id"])
        portal_url = _build_portal_url(workspace_slug)
        borrower_name = loan.get("borrower_name") or "Borrower"
        lo_name = loan.get("loan_officer_name") or "Your Loan Officer"
        channels_sent = []

        if "email" in channels and loan.get("borrower_email"):
            ok = _send_email_notification(db, requests, loan["borrower_email"], borrower_name, lo_name, portal_url)
            if ok:
                channels_sent.append("email")

        if "sms" in channels and loan.get("borrower_phone"):
            ok = _send_sms_notification(loan["borrower_phone"], borrower_name, len(requests), portal_url)
            if ok:
                channels_sent.append("sms")

        if channels_sent:
            _log_delivery(db, loan_id, "needs_list", channels_sent, len(requests), user_id)
            logger.info(f"Needs list sent for loan {loan_id} via {channels_sent}")
    except Exception as e:
        logger.exception(f"BG send-needs-list failed for loan {loan_id}: {e}")
    finally:
        db.close()


def _bg_send_reminder(
    loan_id: int,
    channels: List[str],
    request_ids: Optional[List[int]],
    user_id: int,
):
    """Background task: send document reminder."""
    from database import SessionLocal
    db = SessionLocal()
    try:
        loan = _get_loan_details(db, loan_id)
        if not loan:
            return

        requests = _get_open_requests(db, loan_id, request_ids)
        if not requests:
            return

        workspace_slug = _find_workspace_slug(db, loan_id, loan["organization_id"])
        portal_url = _build_portal_url(workspace_slug)
        borrower_name = loan.get("borrower_name") or "Borrower"
        lo_name = loan.get("loan_officer_name") or "Your Loan Officer"
        channels_sent = []

        if "email" in channels and loan.get("borrower_email"):
            ok = _send_email_notification(db, requests, loan["borrower_email"], borrower_name, lo_name, portal_url)
            if ok:
                channels_sent.append("email")

        if "sms" in channels and loan.get("borrower_phone"):
            ok = _send_sms_notification(loan["borrower_phone"], borrower_name, len(requests), portal_url)
            if ok:
                channels_sent.append("sms")

        if channels_sent:
            _log_delivery(db, loan_id, "reminder", channels_sent, len(requests), user_id)
    except Exception as e:
        logger.exception(f"BG send-reminder failed for loan {loan_id}: {e}")
    finally:
        db.close()


def _bg_send_batch_item(
    loan_id: int,
    channels: List[str],
    template: str,
    user_id: int,
):
    """Background task: send one item in a batch."""
    from database import SessionLocal
    db = SessionLocal()
    try:
        loan = _get_loan_details(db, loan_id)
        if not loan:
            return

        requests = _get_open_requests(db, loan_id)
        if not requests:
            return

        workspace_slug = _find_workspace_slug(db, loan_id, loan["organization_id"])
        portal_url = _build_portal_url(workspace_slug)
        borrower_name = loan.get("borrower_name") or "Borrower"
        lo_name = loan.get("loan_officer_name") or "Your Loan Officer"
        channels_sent = []

        if "email" in channels and loan.get("borrower_email"):
            ok = _send_email_notification(db, requests, loan["borrower_email"], borrower_name, lo_name, portal_url)
            if ok:
                channels_sent.append("email")

        if "sms" in channels and loan.get("borrower_phone"):
            ok = _send_sms_notification(loan["borrower_phone"], borrower_name, len(requests), portal_url)
            if ok:
                channels_sent.append("sms")

        if channels_sent:
            _log_delivery(db, loan_id, f"batch_{template}", channels_sent, len(requests), user_id)
    except Exception as e:
        logger.exception(f"BG batch send failed for loan {loan_id}: {e}")
    finally:
        db.close()


# =============================================================================
# Endpoints
# =============================================================================

@router.post("/send-needs-list", response_model=DeliveryResult)
async def send_needs_list(
    body: SendNeedsListRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Send the document needs list to a borrower via email and/or SMS.

    Validates tenant ownership, gathers open document requests, resolves the
    borrower portal URL, then dispatches notifications in the background.
    """
    _verify_loan_tenant(db, body.loan_id, current_user)

    loan = _get_loan_details(db, body.loan_id)
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    requests = _get_open_requests(db, body.loan_id)
    if not requests:
        raise HTTPException(status_code=400, detail="No open document requests for this loan")

    # Validate channels
    channels_sent = []
    channels_skipped = []
    for ch in body.channels:
        if ch not in ("email", "sms"):
            channels_skipped.append(ch)
            continue
        if ch == "email" and not loan.get("borrower_email"):
            channels_skipped.append("email")
            continue
        if ch == "sms" and not loan.get("borrower_phone"):
            channels_skipped.append("sms")
            continue
        channels_sent.append(ch)

    if not channels_sent:
        return DeliveryResult(
            success=False,
            loan_id=body.loan_id,
            channels_skipped=channels_skipped,
            doc_count=len(requests),
            error="No valid channels available (missing borrower contact info)",
        )

    workspace_slug = _find_workspace_slug(db, body.loan_id, loan["organization_id"])
    portal_url = _build_portal_url(workspace_slug)

    user_id = getattr(current_user, "id", 0)
    background_tasks.add_task(
        _bg_send_needs_list, body.loan_id, channels_sent, body.message, user_id,
    )

    return DeliveryResult(
        success=True,
        loan_id=body.loan_id,
        channels_sent=channels_sent,
        channels_skipped=channels_skipped,
        doc_count=len(requests),
        portal_url=portal_url,
    )


@router.post("/send-reminder", response_model=DeliveryResult)
async def send_reminder(
    body: SendReminderRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Send a document reminder to the borrower for specific or all open requests.
    """
    _verify_loan_tenant(db, body.loan_id, current_user)

    loan = _get_loan_details(db, body.loan_id)
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    requests = _get_open_requests(db, body.loan_id, body.document_request_ids)
    if not requests:
        raise HTTPException(status_code=400, detail="No open document requests to remind about")

    channels_sent = []
    channels_skipped = []
    for ch in body.channels:
        if ch not in ("email", "sms"):
            channels_skipped.append(ch)
            continue
        if ch == "email" and not loan.get("borrower_email"):
            channels_skipped.append("email")
            continue
        if ch == "sms" and not loan.get("borrower_phone"):
            channels_skipped.append("sms")
            continue
        channels_sent.append(ch)

    if not channels_sent:
        return DeliveryResult(
            success=False,
            loan_id=body.loan_id,
            channels_skipped=channels_skipped,
            doc_count=len(requests),
            error="No valid channels available (missing borrower contact info)",
        )

    workspace_slug = _find_workspace_slug(db, body.loan_id, loan["organization_id"])
    portal_url = _build_portal_url(workspace_slug)

    user_id = getattr(current_user, "id", 0)
    background_tasks.add_task(
        _bg_send_reminder, body.loan_id, channels_sent, body.document_request_ids, user_id,
    )

    return DeliveryResult(
        success=True,
        loan_id=body.loan_id,
        channels_sent=channels_sent,
        channels_skipped=channels_skipped,
        doc_count=len(requests),
        portal_url=portal_url,
    )


@router.post("/send-batch", response_model=BatchDeliveryResult)
async def send_batch(
    body: SendBatchRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Send document notifications to multiple borrowers in a single batch.
    Notifications are dispatched via background tasks for non-blocking execution.
    """
    if not body.loan_ids:
        raise HTTPException(status_code=400, detail="loan_ids list is empty")

    if len(body.loan_ids) > 100:
        raise HTTPException(status_code=400, detail="Batch limited to 100 loans")

    # Verify tenant for every loan
    for lid in body.loan_ids:
        _verify_loan_tenant(db, lid, current_user)

    sent = 0
    skipped = 0
    errors = 0
    details = []

    user_id = getattr(current_user, "id", 0)

    for lid in body.loan_ids:
        loan = _get_loan_details(db, lid)
        if not loan:
            errors += 1
            details.append(DeliveryResult(success=False, loan_id=lid, error="Loan not found"))
            continue

        requests = _get_open_requests(db, lid)
        if not requests:
            skipped += 1
            details.append(DeliveryResult(success=False, loan_id=lid, error="No open document requests"))
            continue

        channels_ok = []
        channels_skip = []
        for ch in body.channels:
            if ch == "email" and loan.get("borrower_email"):
                channels_ok.append("email")
            elif ch == "sms" and loan.get("borrower_phone"):
                channels_ok.append("sms")
            else:
                channels_skip.append(ch)

        if not channels_ok:
            skipped += 1
            details.append(DeliveryResult(
                success=False,
                loan_id=lid,
                channels_skipped=channels_skip,
                doc_count=len(requests),
                error="No valid channels",
            ))
            continue

        background_tasks.add_task(
            _bg_send_batch_item, lid, channels_ok, body.template, user_id,
        )
        sent += 1

        workspace_slug = _find_workspace_slug(db, lid, loan["organization_id"])
        portal_url = _build_portal_url(workspace_slug)
        details.append(DeliveryResult(
            success=True,
            loan_id=lid,
            channels_sent=channels_ok,
            channels_skipped=channels_skip,
            doc_count=len(requests),
            portal_url=portal_url,
        ))

    return BatchDeliveryResult(sent=sent, skipped=skipped, errors=errors, details=details)


@router.post("/resend-portal-link", response_model=DeliveryResult)
async def resend_portal_link(
    body: ResendPortalLinkRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Resend the borrower portal URL via email or SMS.
    """
    _verify_loan_tenant(db, body.loan_id, current_user)

    loan = _get_loan_details(db, body.loan_id)
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    workspace_slug = _find_workspace_slug(db, body.loan_id, loan["organization_id"])
    portal_url = _build_portal_url(workspace_slug)
    if not portal_url:
        raise HTTPException(status_code=400, detail="No portal workspace found for this loan")

    borrower_name = loan.get("borrower_name") or "Borrower"
    lo_name = loan.get("loan_officer_name") or "Your Loan Officer"

    channels_sent = []
    channels_skipped = []

    if body.channel == "email":
        if not loan.get("borrower_email"):
            channels_skipped.append("email")
        else:
            ok = _send_portal_link_email(loan["borrower_email"], borrower_name, lo_name, portal_url)
            if ok:
                channels_sent.append("email")
            else:
                channels_skipped.append("email")
    elif body.channel == "sms":
        if not loan.get("borrower_phone"):
            channels_skipped.append("sms")
        else:
            ok = _send_portal_link_sms(loan["borrower_phone"], borrower_name, portal_url)
            if ok:
                channels_sent.append("sms")
            else:
                channels_skipped.append("sms")
    else:
        channels_skipped.append(body.channel)

    user_id = getattr(current_user, "id", 0)
    if channels_sent:
        _log_delivery(db, body.loan_id, "resend_portal_link", channels_sent, 0, user_id)

    return DeliveryResult(
        success=len(channels_sent) > 0,
        loan_id=body.loan_id,
        channels_sent=channels_sent,
        channels_skipped=channels_skipped,
        portal_url=portal_url,
    )


@router.get("/history/{loan_id}")
async def get_delivery_history(
    loan_id: int,
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Get delivery notification history for a loan.

    Returns recent delivery events from the doc_policy_events audit log.
    """
    _verify_loan_tenant(db, loan_id, current_user)

    rows = db.execute(
        sa_text("""
            SELECT id, event_type, payload, created_at
            FROM doc_policy_events
            WHERE loan_id = :loan_id
              AND event_type = 'EXPIRATION_REMINDER_SENT'
            ORDER BY created_at DESC
            LIMIT :lim
        """),
        {"loan_id": loan_id, "lim": limit},
    ).fetchall()

    history = []
    for row in rows:
        r = dict(row._mapping)
        history.append({
            "id": r["id"],
            "event_type": r["event_type"],
            "payload": r.get("payload"),
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        })

    return {
        "loan_id": loan_id,
        "total": len(history),
        "history": history,
    }
