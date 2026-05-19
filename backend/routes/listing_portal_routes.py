"""
Listing Agent Portal Routes
API endpoints for the transaction-scoped listing agent portal.
"""

import os
import logging
from typing import Optional, Callable

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status, Header
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr

from utils.responses import success_response, error_response
from sqlalchemy.exc import SQLAlchemyError
from db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/listing-portal", tags=["listing-portal"])

# Dependency injection placeholders
_get_current_user: Optional[Callable] = None


def set_dependencies(get_db_func: Callable, get_current_user_func: Callable):
    """Set dependencies at runtime from main.py.
    get_db_func is accepted for API compatibility but ignored; get_db is imported from db.py.
    """
    global _get_current_user
    _get_current_user = get_current_user_func


from auth.dependencies import get_current_user  # dedup: was local wrapper
# =============================================================================
# REQUEST MODELS
# =============================================================================

class CreateTransactionRequest(BaseModel):
    loan_id: int
    property_address: str
    property_city: Optional[str] = None
    property_state: Optional[str] = None
    property_zip: Optional[str] = None
    purchase_price: Optional[float] = None
    contract_date: Optional[str] = None
    target_close_date: Optional[str] = None


class AddPartyRequest(BaseModel):
    role: str = "listing_agent"
    email: EmailStr
    first_name: str
    last_name: str
    phone: Optional[str] = None
    company_name: Optional[str] = None
    license_number: Optional[str] = None
    notify_weekly_updates: bool = True
    notify_milestone_changes: bool = True
    notify_messages: bool = True


class UpdateMilestoneRequest(BaseModel):
    status: str
    completed_at: Optional[str] = None
    target_date: Optional[str] = None


class SendMessageRequest(BaseModel):
    content: str


class MagicLinkAuthRequest(BaseModel):
    token: str


# =============================================================================
# ADMIN ROUTES (Authenticated LO access)
# =============================================================================

@router.post("/transactions")
async def create_transaction(
    request: CreateTransactionRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new listing transaction from a loan"""
    from services.listing_portal_service import listing_portal_service

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)
    org_id = current_user.get("organization_id") if isinstance(current_user, dict) else getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=403, detail="Organization context required")

    transaction = listing_portal_service.create_transaction(
        db=db,
        organization_id=org_id,
        loan_id=request.loan_id,
        property_address=request.property_address,
        property_city=request.property_city,
        property_state=request.property_state,
        property_zip=request.property_zip,
        purchase_price=request.purchase_price,
        contract_date=request.contract_date,
        target_close_date=request.target_close_date
    )

    if not transaction:
        raise HTTPException(status_code=400, detail="Failed to create transaction")

    return success_response("Transaction created successfully", transaction)


@router.get("/transactions")
async def list_transactions(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all transactions for the current organization"""
    from sqlalchemy import text

    org_id = current_user.get("organization_id") if isinstance(current_user, dict) else getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=403, detail="Organization context required")

    result = db.execute(text("""
        SELECT
            t.id, t.loan_id, t.property_address, t.property_city, t.property_state,
            t.purchase_price, t.target_close_date, t.current_status, t.is_active,
            t.created_at,
            (SELECT COUNT(*) FROM transaction_parties p WHERE p.transaction_id = t.id AND p.is_active = true) as party_count
        FROM listing_transactions t
        WHERE t.organization_id = :org_id AND t.is_active = true
        ORDER BY t.created_at DESC
    """), {"org_id": org_id})

    transactions = [
        {
            "id": row.id,
            "loan_id": row.loan_id,
            "property_address": row.property_address,
            "property_city": row.property_city,
            "property_state": row.property_state,
            "purchase_price": float(row.purchase_price) if row.purchase_price else None,
            "target_close_date": row.target_close_date,
            "current_status": row.current_status,
            "is_active": row.is_active,
            "created_at": row.created_at,
            "party_count": row.party_count
        }
        for row in result.fetchall()
    ]

    return success_response("Transactions retrieved successfully", {"transactions": transactions})


@router.get("/transactions/{transaction_id}")
async def get_transaction(
    transaction_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get transaction details with parties and milestones"""
    from services.listing_portal_service import listing_portal_service

    transaction = listing_portal_service.get_transaction(db, transaction_id)
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    parties = listing_portal_service.get_transaction_parties(db, transaction_id)
    milestones = listing_portal_service.get_milestones(db, transaction_id)
    unread = listing_portal_service.get_unread_count(db, transaction_id, for_party=False)

    return success_response("Transaction details retrieved", {
        "transaction": transaction,
        "parties": parties,
        "milestones": milestones,
        "unread_messages": unread
    })


@router.post("/transactions/{transaction_id}/parties")
async def add_party(
    transaction_id: int,
    request: AddPartyRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Add a party (listing agent) to a transaction"""
    from services.listing_portal_service import listing_portal_service

    party = listing_portal_service.add_party(
        db=db,
        transaction_id=transaction_id,
        role=request.role,
        email=request.email,
        first_name=request.first_name,
        last_name=request.last_name,
        phone=request.phone,
        company_name=request.company_name,
        license_number=request.license_number,
        notify_weekly=request.notify_weekly_updates,
        notify_milestones=request.notify_milestone_changes,
        notify_messages=request.notify_messages
    )

    if not party:
        raise HTTPException(status_code=400, detail="Failed to add party")

    return success_response("Party added successfully", party)


@router.post("/transactions/{transaction_id}/parties/{party_id}/invite")
async def send_portal_invite(
    transaction_id: int,
    party_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Send portal invite email with magic link to a party"""
    from services.listing_portal_service import listing_portal_service
    from services.listing_update_email_service import listing_update_email_service

    # Create invite
    invite = listing_portal_service.create_portal_invite(db, party_id)
    if not invite:
        raise HTTPException(status_code=400, detail="Failed to create invite")

    # Get transaction for property address
    transaction = listing_portal_service.get_transaction(db, transaction_id)
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    # Get LO name
    user_name = current_user.get("name", "Your Loan Officer") if isinstance(current_user, dict) else getattr(current_user, "name", "Your Loan Officer")

    # Send email
    success = listing_update_email_service.send_portal_invite(
        to_email=invite["party_email"],
        party_name=invite["party_name"],
        property_address=transaction["property_address"],
        lo_name=user_name,
        portal_url=invite["portal_url"]
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to send invite email")

    return success_response("Portal invite sent successfully", invite)


@router.put("/transactions/{transaction_id}/milestones/{milestone_id}")
async def update_milestone(
    transaction_id: int,
    milestone_id: int,
    request: UpdateMilestoneRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a milestone status"""
    from services.listing_portal_service import listing_portal_service
    from services.notification_service import NotificationService
    from sqlalchemy import text

    milestone = listing_portal_service.update_milestone(
        db=db,
        milestone_id=milestone_id,
        status=request.status,
        completed_at=request.completed_at,
        target_date=request.target_date
    )

    if not milestone:
        raise HTTPException(status_code=400, detail="Failed to update milestone")

    # Send milestone notification to subscribed parties
    try:
        # Get parties subscribed to milestone changes
        result = db.execute(text("""
            SELECT p.id, p.email, p.first_name, p.last_name, p.role,
                   t.property_address
            FROM transaction_parties p
            JOIN listing_transactions t ON t.id = p.transaction_id
            WHERE p.transaction_id = :txn_id
              AND p.notify_milestone_changes = true
              AND p.is_active = true
              AND p.email IS NOT NULL
        """), {"txn_id": transaction_id})
        parties = result.fetchall()

        if parties:
            notification_service = NotificationService()
            status_text = "completed" if request.status == "completed" else f"updated to {request.status}"

            for party in parties:
                try:
                    notification_service.send_email(
                        to_email=party.email,
                        subject=f"Milestone Update: {milestone['milestone_name']}",
                        html_content=f"""
                        <p>Hi {party.first_name or 'there'},</p>
                        <p>A milestone has been {status_text} for the transaction at <strong>{party.property_address}</strong>.</p>
                        <p><strong>Milestone:</strong> {milestone['milestone_name']}</p>
                        <p><strong>Status:</strong> {milestone['status']}</p>
                        {f"<p><strong>Target Date:</strong> {milestone['target_date']}</p>" if milestone.get('target_date') else ""}
                        <p>Log in to your portal to view more details.</p>
                        <p>Best regards,<br>Your Loan Team</p>
                        """
                    )
                    logger.info(f"Milestone notification sent to {party.email} for milestone {milestone_id}")
                except Exception as email_err:
                    logger.warning(f"Failed to send milestone notification to {party.email}: {email_err}")

    except Exception as notify_err:
        logger.warning(f"Failed to send milestone notifications: {notify_err}")
        # Don't fail the request if notifications fail

    return success_response("Milestone updated", milestone)


@router.post("/transactions/{transaction_id}/messages")
async def send_message_as_lo(
    transaction_id: int,
    request: SendMessageRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Send a message as the loan officer"""
    from services.listing_portal_service import listing_portal_service

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

    message = listing_portal_service.send_message(
        db=db,
        transaction_id=transaction_id,
        content=request.content,
        sender_user_id=user_id
    )

    if not message:
        raise HTTPException(status_code=400, detail="Failed to send message")

    return success_response("Message sent", message)


@router.get("/transactions/{transaction_id}/messages")
async def get_messages(
    transaction_id: int,
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get messages for a transaction"""
    from services.listing_portal_service import listing_portal_service

    messages = listing_portal_service.get_messages(db, transaction_id, limit, offset)

    # Mark as read by LO
    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)
    listing_portal_service.mark_messages_read(db, transaction_id, reader_user_id=user_id)

    return success_response("Messages retrieved", {"messages": messages})


# =============================================================================
# PUBLIC PORTAL ROUTES (Magic link authentication)
# =============================================================================

@router.post("/auth/magic-link")
async def authenticate_magic_link(
    request: MagicLinkAuthRequest,
    db: Session = Depends(get_db)
):
    """Authenticate using a magic link token"""
    from services.listing_portal_service import listing_portal_service

    session_data, error = listing_portal_service.validate_magic_link(db, request.token)

    if error:
        raise HTTPException(status_code=401, detail=error)

    return success_response("Authentication successful", session_data)


@router.get("/auth/session")
async def validate_session(
    request: Request,
    db: Session = Depends(get_db)
):
    """Validate a session token (from cookie or header)"""
    from services.listing_portal_service import listing_portal_service

    # Try to get session token from header or cookie
    session_token = request.headers.get("X-Session-Token")
    if not session_token:
        session_token = request.cookies.get("listing_portal_session")

    if not session_token:
        raise HTTPException(status_code=401, detail="No session token provided")

    session_data = listing_portal_service.validate_session(db, session_token)

    if not session_data:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    return success_response("Session valid", session_data)


# Helper to get party from session
async def get_portal_party(request: Request, db: Session = Depends(get_db)):
    """Get party from portal session"""
    from services.listing_portal_service import listing_portal_service

    session_token = request.headers.get("X-Session-Token")
    if not session_token:
        session_token = request.cookies.get("listing_portal_session")

    if not session_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    session_data = listing_portal_service.validate_session(db, session_token)
    if not session_data:
        raise HTTPException(status_code=401, detail="Session expired")

    return session_data


@router.get("/portal/dashboard")
async def portal_dashboard(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get dashboard view for logged-in party"""
    session_data = await get_portal_party(request, db)
    from services.listing_portal_service import listing_portal_service

    party = session_data["party"]
    transaction = session_data["transaction"]

    # Get milestones
    milestones = listing_portal_service.get_milestones(db, transaction["id"])

    # Get unread count
    unread = listing_portal_service.get_unread_count(db, transaction["id"], for_party=True)

    # Get recent messages (preview)
    messages = listing_portal_service.get_messages(db, transaction["id"], limit=5)

    return success_response("Portal dashboard loaded", {
        "party": {
            "id": party["id"],
            "name": f"{party['first_name']} {party['last_name']}",
            "email": party["email"],
            "role": party["role"]
        },
        "transaction": {
            "id": transaction["id"],
            "property_address": transaction["property_address"],
            "property_city": transaction.get("property_city"),
            "property_state": transaction.get("property_state"),
            "purchase_price": transaction.get("purchase_price"),
            "target_close_date": transaction.get("target_close_date"),
            "current_status": transaction["current_status"]
        },
        "milestones": milestones,
        "unread_messages": unread,
        "recent_messages": messages
    })


@router.get("/portal/messages")
async def portal_get_messages(
    request: Request,
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """Get messages as a party"""
    session_data = await get_portal_party(request, db)
    from services.listing_portal_service import listing_portal_service

    party = session_data["party"]
    transaction = session_data["transaction"]

    messages = listing_portal_service.get_messages(db, transaction["id"], limit, offset)

    # Mark LO messages as read
    listing_portal_service.mark_messages_read(db, transaction["id"], reader_party_id=party["id"])

    return success_response("Messages retrieved", {"messages": messages})


@router.post("/portal/messages")
async def portal_send_message(
    request: Request,
    message_request: SendMessageRequest,
    db: Session = Depends(get_db)
):
    """Send a message as a party"""
    session_data = await get_portal_party(request, db)
    from services.listing_portal_service import listing_portal_service

    party = session_data["party"]
    transaction = session_data["transaction"]

    message = listing_portal_service.send_message(
        db=db,
        transaction_id=transaction["id"],
        content=message_request.content,
        sender_party_id=party["id"]
    )

    if not message:
        raise HTTPException(status_code=400, detail="Failed to send message")

    return success_response("Message sent", message)


# =============================================================================
# UNSUBSCRIBE ROUTES (Public)
# =============================================================================

@router.get("/unsubscribe")
async def unsubscribe_page(
    token: str = Query(..., description="Unsubscribe token"),
    db: Session = Depends(get_db)
):
    """Process unsubscribe (can be GET for email link clicks)"""
    from services.listing_portal_service import listing_portal_service

    success, message = listing_portal_service.process_unsubscribe(db, token)

    frontend_url = os.getenv("FRONTEND_URL", "https://www.perenniaai.com")

    if success:
        return RedirectResponse(url=f"{frontend_url}/listing-portal/unsubscribed?success=true")
    else:
        return RedirectResponse(url=f"{frontend_url}/listing-portal/unsubscribed?error={message}")


@router.post("/unsubscribe")
async def process_unsubscribe(
    token: str,
    db: Session = Depends(get_db)
):
    """Process unsubscribe via POST"""
    from services.listing_portal_service import listing_portal_service

    success, message = listing_portal_service.process_unsubscribe(db, token)

    if success:
        return success_response(message, {"unsubscribed": True})
    else:
        raise HTTPException(status_code=400, detail=message)


# =============================================================================
# ADMIN: RUN MIGRATION (for initial setup)
# =============================================================================

@router.get("/admin/run-migration")
async def run_migration(
    admin_key: str = Header(..., alias="X-Admin-Key", description="Admin API key"),
    db: Session = Depends(get_db)
):
    """Run the listing portal migration (admin only)"""
    expected_key = os.getenv("ADMIN_API_KEY", "")

    if admin_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    try:
        from migrations.add_listing_agent_portal import run_migration
        run_migration()
        return success_response("Migration completed successfully", {"migrated": True})
    except Exception as e:
        logger.error(f"Migration error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/admin/trigger-weekly-updates")
async def trigger_weekly_updates(
    admin_key: str = Header(..., alias="X-Admin-Key", description="Admin API key"),
    dry_run: bool = Query(False, description="If true, don't send emails"),
    organization_id: Optional[int] = Query(None, description="Filter by organization"),
    db: Session = Depends(get_db)
):
    """Manually trigger the weekly update job (admin only)"""
    expected_key = os.getenv("ADMIN_API_KEY", "")

    if admin_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    try:
        from jobs.listing_weekly_update_job import run_weekly_updates

        result = run_weekly_updates(
            organization_id=organization_id,
            dry_run=dry_run
        )

        return success_response("Weekly updates job completed", result)

    except Exception as e:
        logger.error(f"Weekly updates trigger error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/admin/scheduler-status")
async def get_scheduler_status(
    admin_key: str = Header(..., alias="X-Admin-Key", description="Admin API key")
):
    """Get the status of all scheduled jobs (admin only)"""
    expected_key = os.getenv("ADMIN_API_KEY", "")

    if admin_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    try:
        from services.scheduler_service import scheduler_service

        jobs = scheduler_service.get_job_status()

        # Filter to just listing-related jobs
        listing_jobs = [j for j in jobs if "listing" in j["id"].lower()]

        return success_response("Scheduler status retrieved", {
            "all_jobs": jobs,
            "listing_jobs": listing_jobs,
            "scheduler_running": scheduler_service.scheduler.running
        })

    except Exception as e:
        logger.error(f"Scheduler status error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
