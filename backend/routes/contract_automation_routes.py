"""
Contract Portal Automation API Routes
Perennia AI - Mortgage CRM

Endpoints for managing automatic portal creation when contracts are received.
"""

import logging
from typing import Optional, List
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field, EmailStr
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


def _get_current_user():
    """Lazy import auth dependency for router-level protection."""
    from auth.dependencies import get_current_user_flexible
    return get_current_user_flexible

router = APIRouter(
    prefix="/api/v1/contract-automation", tags=["Contract Automation"],
    dependencies=[Depends(_get_current_user())],
)


# =============================================================================
# DEPENDENCY INJECTION
# =============================================================================

_get_db = None
_notification_service = None


def set_dependencies(get_db_func, notification_service=None):
    """Set dependencies from main.py."""
    global _get_db, _notification_service
    _get_db = get_db_func
    _notification_service = notification_service
    logger.info("Contract Automation routes dependencies set")


def get_db():
    """Get database session."""
    if _get_db is None:
        raise RuntimeError("Contract Automation routes not initialized")
    yield from _get_db()


def get_automation_service(db: AsyncSession):
    """Get configured automation service."""
    from services.contract_portal_automation_service import ContractPortalAutomationService
    return ContractPortalAutomationService(db, _notification_service)


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class TriggerAutomationRequest(BaseModel):
    """Request to manually trigger contract portal automation."""
    loan_id: int = Field(..., description="The loan ID to process")
    triggered_by: str = Field(default="manual", description="How this was triggered")


class TriggerAutomationResponse(BaseModel):
    """Response from automation trigger."""
    success: bool
    loan_id: int
    client_portal: Optional[dict] = None
    buyers_agent_portal: Optional[dict] = None
    listing_agent_portal: Optional[dict] = None
    tasks_created: List[dict] = []
    invitations_sent: List[dict] = []
    errors: List[str] = []


class AddRealtorRequest(BaseModel):
    """Request to add a realtor to a loan."""
    loan_id: int = Field(..., description="The loan ID")
    realtor_type: str = Field(..., description="'buyers_agent' or 'listing_agent'")
    name: str = Field(..., min_length=1)
    email: EmailStr
    phone: Optional[str] = None
    company: Optional[str] = None


class AddRealtorResponse(BaseModel):
    """Response from adding a realtor."""
    success: bool
    loan_id: int
    realtor_type: str
    portal_created: bool = False
    portal_url: Optional[str] = None
    invitation_sent: Optional[dict] = None
    task_completed: bool = False
    error: Optional[str] = None


class PendingPortalTask(BaseModel):
    """A pending task to enter realtor information."""
    task_id: int
    loan_id: int
    loan_number: Optional[str]
    borrower_name: Optional[str]
    property_address: Optional[str]
    realtor_type: str
    title: str
    created_at: str
    due_date: Optional[str]


# =============================================================================
# API ENDPOINTS
# =============================================================================

@router.post("/trigger", response_model=TriggerAutomationResponse)
async def trigger_contract_automation(
    request: TriggerAutomationRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Manually trigger contract portal automation for a loan.

    Use this when:
    - A contract was received but automation didn't run
    - You want to re-process portal creation
    - Testing the automation flow
    """
    try:
        service = get_automation_service(db)
        result = service.process_contract_received(
            loan_id=request.loan_id,
            triggered_by=request.triggered_by
        )

        return TriggerAutomationResponse(
            success=len(result.get("errors", [])) == 0,
            loan_id=request.loan_id,
            client_portal=result.get("client_portal"),
            buyers_agent_portal=result.get("buyers_agent_portal"),
            listing_agent_portal=result.get("listing_agent_portal"),
            tasks_created=result.get("tasks_created", []),
            invitations_sent=result.get("invitations_sent", []),
            errors=result.get("errors", [])
        )

    except Exception as e:
        logger.error(f"Failed to trigger contract automation for loan {request.loan_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/add-realtor", response_model=AddRealtorResponse)
async def add_realtor_to_loan(
    request: AddRealtorRequest,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Add a realtor to a loan and automatically create their portal.

    This endpoint:
    1. Creates/links a referral partner record
    2. Creates the appropriate portal (buyer's agent or listing agent)
    3. Sends an invitation email
    4. Marks any pending "enter realtor" tasks as completed
    """
    try:
        service = get_automation_service(db)

        realtor_info = {
            "name": request.name,
            "email": request.email,
            "phone": request.phone,
            "company": request.company
        }

        result = service.on_realtor_added(
            loan_id=request.loan_id,
            realtor_type=request.realtor_type,
            realtor_info=realtor_info
        )

        if "error" in result:
            return AddRealtorResponse(
                success=False,
                loan_id=request.loan_id,
                realtor_type=request.realtor_type,
                error=result["error"]
            )

        return AddRealtorResponse(
            success=True,
            loan_id=request.loan_id,
            realtor_type=request.realtor_type,
            portal_created=result.get("portal_created", False),
            portal_url=result.get("portal_url"),
            invitation_sent=result.get("invitation_sent"),
            task_completed=result.get("task_completed", False)
        )

    except Exception as e:
        logger.error(f"Failed to add realtor to loan {request.loan_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/pending-tasks")
async def get_pending_realtor_tasks(
    owner_id: Optional[int] = Query(None, description="Filter by task owner"),
    limit: int = Query(50, le=100),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get pending tasks to enter realtor information.

    Returns tasks created when contracts were received but realtor info was missing.
    """
    try:
        params = {"limit": limit}
        filters = [
            "(t.title ILIKE '%buyer%agent%' OR t.title ILIKE '%listing%agent%')",
            "t.status = 'pending'"
        ]

        if owner_id:
            filters.append("t.owner_id = :owner_id")
            params["owner_id"] = owner_id

        where_sql = " AND ".join(filters)

        query = """
            SELECT
                t.id as task_id,
                t.loan_id,
                t.title,
                t.created_at,
                t.due_date,
                l.loan_number,
                l.property_address,
                l.borrower_name
            FROM tasks t
            LEFT JOIN loans l ON l.id = t.loan_id
            WHERE """ + where_sql + """
            ORDER BY t.due_date ASC NULLS LAST, t.created_at DESC
            LIMIT :limit
        """
        tasks = (await db.execute(text(query), params)).fetchall()

        return {
            "tasks": [
                {
                    "task_id": t[0],
                    "loan_id": t[1],
                    "title": t[2],
                    "realtor_type": "buyers_agent" if "buyer" in (t[2] or "").lower() else "listing_agent",
                    "created_at": t[3].isoformat() if t[3] else None,
                    "due_date": t[4].isoformat() if t[4] else None,
                    "loan_number": t[5],
                    "property_address": t[6],
                    "borrower_name": t[7]
                }
                for t in tasks
            ],
            "total": len(tasks)
        }

    except Exception as e:
        logger.error(f"Failed to get pending realtor tasks: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/loan/{loan_id}/portal-status")
async def get_loan_portal_status(
    loan_id: int,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get the status of all portals for a loan.

    Returns information about:
    - Client portal (PURL workspace)
    - Buyer's agent portal
    - Listing agent portal
    """
    try:
        # Get loan info
        loan = (await db.execute(text("""
            SELECT
                l.id,
                l.loan_number,
                l.borrower_name,
                l.realtor_agent
            FROM loans l
            WHERE l.id = :loan_id
        """), {"loan_id": loan_id})).fetchone()

        if not loan:
            raise HTTPException(status_code=404, detail=f"Loan {loan_id} not found")

        # Check client portal
        client_portal = (await db.execute(text("""
            SELECT id, slug, status FROM purl_workspaces
            WHERE loan_id = :loan_id
            LIMIT 1
        """), {"loan_id": loan_id})).fetchone()

        # Check buyer's agent portal - look for realtor in loan_team_members
        buyers_agent = None
        team_realtor = (await db.execute(text("""
            SELECT ltm.id, ltm.name, ltm.email, ltm.referral_partner_id
            FROM loan_team_members ltm
            WHERE ltm.loan_id = :loan_id
            AND (ltm.role ILIKE '%buyer%' OR ltm.role ILIKE '%realtor%')
            LIMIT 1
        """), {"loan_id": loan_id})).fetchone()

        if team_realtor and team_realtor[3]:  # Has referral_partner_id
            partner = (await db.execute(text("""
                SELECT id, name, email FROM referral_partners WHERE id = :partner_id
            """), {"partner_id": team_realtor[3]})).fetchone()
            if partner:
                buyers_agent = {
                    "exists": True,
                    "partner_id": partner[0],
                    "partner_name": partner[1],
                    "partner_email": partner[2],
                    "portal_url": f"/partner-portal/{partner[0]}/loan/{loan_id}"
                }
        elif team_realtor:
            buyers_agent = {
                "exists": True,
                "team_member_id": team_realtor[0],
                "name": team_realtor[1],
                "email": team_realtor[2],
                "portal_url": None,
                "needs_partner_setup": True
            }

        if not buyers_agent:
            # Check for pending task
            task = (await db.execute(text("""
                SELECT id, status FROM tasks
                WHERE loan_id = :loan_id AND title ILIKE '%buyer%agent%'
                ORDER BY id DESC LIMIT 1
            """), {"loan_id": loan_id})).fetchone()
            buyers_agent = {
                "exists": False,
                "pending_task_id": task[0] if task else None,
                "task_status": task[1] if task else None
            }

        # Check listing agent portal
        listing_tx = (await db.execute(text("""
            SELECT id, status FROM listing_transactions WHERE loan_id = :loan_id LIMIT 1
        """), {"loan_id": loan_id})).fetchone()

        listing_agent = None
        if listing_tx:
            parties = (await db.execute(text("""
                SELECT name, email FROM listing_transaction_parties
                WHERE transaction_id = :tx_id AND role = 'listing_agent'
            """), {"tx_id": listing_tx[0]})).fetchall()
            listing_agent = {
                "exists": True,
                "transaction_id": listing_tx[0],
                "status": listing_tx[1],
                "portal_url": f"/listing-portal/transaction/{listing_tx[0]}",
                "agents": [{"name": p[0], "email": p[1]} for p in parties]
            }
        else:
            task = (await db.execute(text("""
                SELECT id, status FROM tasks
                WHERE loan_id = :loan_id AND title ILIKE '%listing%agent%'
                ORDER BY id DESC LIMIT 1
            """), {"loan_id": loan_id})).fetchone()
            listing_agent = {
                "exists": False,
                "pending_task_id": task[0] if task else None,
                "task_status": task[1] if task else None
            }

        return {
            "loan_id": loan_id,
            "loan_number": loan[1],
            "borrower_name": loan[2],
            "realtor_agent": loan[3],
            "portals": {
                "client": {
                    "exists": client_portal is not None,
                    "workspace_id": client_portal[0] if client_portal else None,
                    "slug": client_portal[1] if client_portal else None,
                    "status": client_portal[2] if client_portal else None,
                    "portal_url": f"/portal/{client_portal[1]}" if client_portal else None
                },
                "buyers_agent": buyers_agent,
                "listing_agent": listing_agent
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get portal status for loan {loan_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/resend-invitation")
async def resend_portal_invitation(
    loan_id: int = Query(...),
    portal_type: str = Query(..., description="'buyers_agent' or 'listing_agent'"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Resend a portal invitation email.

    Use when the original invitation was missed or expired.
    """
    try:
        service = get_automation_service(db)
        loan_info = service._get_loan_info(loan_id)

        if not loan_info:
            raise HTTPException(status_code=404, detail=f"Loan {loan_id} not found")

        if portal_type == "buyers_agent":
            partner_id = loan_info.get("referral_partner_id")
            if not partner_id:
                raise HTTPException(status_code=400, detail="No buyer's agent assigned to this loan")

            partner = (await db.execute(text("""
                SELECT id, name, email FROM referral_partners WHERE id = :partner_id
            """), {"partner_id": partner_id})).fetchone()

            if not partner or not partner[2]:
                raise HTTPException(status_code=400, detail="Partner has no email address")

            invitation = service._send_realtor_invitation(
                loan_info=loan_info,
                realtor_name=partner[1],
                realtor_email=partner[2],
                realtor_type="buyers_agent",
                partner_id=partner[0]
            )

        elif portal_type == "listing_agent":
            tx = (await db.execute(text("""
                SELECT id FROM listing_transactions WHERE loan_id = :loan_id LIMIT 1
            """), {"loan_id": loan_id})).fetchone()

            if not tx:
                raise HTTPException(status_code=400, detail="No listing transaction exists for this loan")

            party = (await db.execute(text("""
                SELECT name, email FROM listing_transaction_parties
                WHERE transaction_id = :tx_id AND role = 'listing_agent'
                LIMIT 1
            """), {"tx_id": tx[0]})).fetchone()

            if not party or not party[1]:
                raise HTTPException(status_code=400, detail="Listing agent has no email address")

            invitation = service._send_realtor_invitation(
                loan_info=loan_info,
                realtor_name=party[0],
                realtor_email=party[1],
                realtor_type="listing_agent",
                transaction_id=tx[0]
            )

        else:
            raise HTTPException(status_code=400, detail="Invalid portal_type. Use 'buyers_agent' or 'listing_agent'")

        if invitation:
            return {
                "success": True,
                "message": f"Invitation resent to {invitation['email']}",
                "invitation": invitation
            }
        else:
            return {
                "success": False,
                "message": "Failed to send invitation (notification service may be unavailable)"
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to resend invitation for loan {loan_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
