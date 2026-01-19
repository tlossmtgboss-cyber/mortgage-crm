"""
Support Tickets Routes
Handles IT support ticket submission and management for the platform.
Master admin can view all tickets, regular users see only their own.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, text, JSON
from pydantic import BaseModel
from typing import Optional, List, Callable
from datetime import datetime, timezone
import logging

from database import Base, get_db as db_get_db, engine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/support", tags=["support"])

# Master admin email
MASTER_ADMIN_EMAIL = "admin@perenniaai.com"

# Dependency injection placeholders
_get_current_user: Optional[Callable] = None


def set_dependencies(get_current_user_func: Callable):
    """Set dependencies at runtime from main.py."""
    global _get_current_user
    _get_current_user = get_current_user_func


def get_db():
    """Get database session wrapper."""
    yield from db_get_db()


async def get_current_user(request: Request, db: Session = Depends(get_db)):
    """Get current user - wrapper that works at request time."""
    if _get_current_user is None:
        raise HTTPException(status_code=500, detail="Auth dependency not configured")
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    return await _get_current_user(token=token, request=request, db=db)


# ============================================================================
# DATABASE MODEL
# ============================================================================

class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)

    subject = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    category = Column(String(50), nullable=False)  # technical, billing, feature, integration, training, other
    priority = Column(String(20), default="normal")  # low, normal, high, urgent
    status = Column(String(20), default="open")  # open, in_progress, resolved, closed

    # Admin notes
    admin_notes = Column(Text, nullable=True)
    assigned_to = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    resolved_at = Column(DateTime, nullable=True)

    # User info snapshot (for display without joins)
    user_email = Column(String(255), nullable=True)
    user_name = Column(String(255), nullable=True)
    organization_name = Column(String(255), nullable=True)

    # Attachments (screenshots)
    attachments = Column(JSON, nullable=True)  # List of {name, type, data}


# Create table if not exists
try:
    SupportTicket.__table__.create(engine, checkfirst=True)
    logger.info("✅ Support tickets table created/verified")
except Exception as e:
    logger.info(f"Note: support_tickets table creation: {e}")


# ============================================================================
# PYDANTIC SCHEMAS
# ============================================================================

class AttachmentData(BaseModel):
    name: str
    type: str
    data: str  # base64 encoded


class TicketCreate(BaseModel):
    subject: str
    description: str
    category: str
    priority: str = "normal"
    attachments: Optional[List[AttachmentData]] = None


class TicketUpdate(BaseModel):
    status: Optional[str] = None
    admin_notes: Optional[str] = None
    assigned_to: Optional[int] = None


class TicketResponse(BaseModel):
    id: int
    subject: str
    description: str
    category: str
    priority: str
    status: str
    user_email: Optional[str] = None
    user_name: Optional[str] = None
    organization_name: Optional[str] = None
    admin_notes: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def is_master_admin(user) -> bool:
    """Check if user is the master admin"""
    return user.email and user.email.lower() == MASTER_ADMIN_EMAIL.lower()


def is_platform_admin(user) -> bool:
    """Check if user is a platform admin"""
    admin_roles = ['admin', 'super_admin', 'platform_admin']
    user_role = getattr(user, 'role', None)
    if user_role and user_role.lower() in admin_roles:
        return True
    return is_master_admin(user)


# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.get("/tickets")
async def get_tickets(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Get support tickets.
    - Master admin/platform admin: Gets ALL tickets from all users
    - Regular users: Gets only their own tickets
    """
    try:
        query = db.query(SupportTicket)

        # Filter by user unless admin
        if not is_platform_admin(current_user):
            query = query.filter(SupportTicket.user_id == current_user.id)

        # Filter by status if provided
        if status:
            query = query.filter(SupportTicket.status == status)

        # Order by created_at descending (newest first)
        tickets = query.order_by(SupportTicket.created_at.desc()).all()

        return {
            "tickets": [
                {
                    "id": t.id,
                    "subject": t.subject,
                    "description": t.description,
                    "category": t.category,
                    "priority": t.priority,
                    "status": t.status,
                    "user_email": t.user_email,
                    "user_name": t.user_name,
                    "organization_name": t.organization_name,
                    "admin_notes": t.admin_notes if is_platform_admin(current_user) else None,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                    "updated_at": t.updated_at.isoformat() if t.updated_at else None,
                    "resolved_at": t.resolved_at.isoformat() if t.resolved_at else None,
                    "attachment_count": len(t.attachments) if t.attachments else 0,
                    "attachments": t.attachments if t.attachments else [],
                }
                for t in tickets
            ],
            "total": len(tickets),
            "is_admin": is_platform_admin(current_user)
        }
    except Exception as e:
        print(f"Error fetching tickets: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tickets")
async def create_ticket(
    ticket: TicketCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Create a new support ticket"""
    try:
        # Get user and organization info
        user_email = getattr(current_user, 'email', None)
        user_name = f"{getattr(current_user, 'first_name', '')} {getattr(current_user, 'last_name', '')}".strip()
        if not user_name:
            user_name = getattr(current_user, 'name', user_email)

        organization_id = getattr(current_user, 'organization_id', None)
        organization_name = None

        if organization_id:
            # Use raw SQL to avoid circular import with main.py
            result = db.execute(text("SELECT name FROM organizations WHERE id = :org_id"), {"org_id": organization_id}).fetchone()
            if result:
                organization_name = result[0]

        # Process attachments - store metadata only, not full base64 data in DB
        attachments_data = None
        if ticket.attachments:
            attachments_data = [
                {"name": att.name, "type": att.type, "data": att.data}
                for att in ticket.attachments[:5]  # Limit to 5
            ]

        new_ticket = SupportTicket(
            user_id=current_user.id,
            organization_id=organization_id,
            subject=ticket.subject,
            description=ticket.description,
            category=ticket.category,
            priority=ticket.priority,
            status="open",
            user_email=user_email,
            user_name=user_name,
            organization_name=organization_name,
            attachments=attachments_data,
        )

        db.add(new_ticket)
        db.commit()
        db.refresh(new_ticket)

        return {
            "success": True,
            "message": "Ticket created successfully",
            "ticket": {
                "id": new_ticket.id,
                "subject": new_ticket.subject,
                "status": new_ticket.status,
                "created_at": new_ticket.created_at.isoformat() if new_ticket.created_at else None,
            }
        }
    except Exception as e:
        db.rollback()
        print(f"Error creating ticket: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tickets/{ticket_id}")
async def get_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get a specific ticket by ID"""
    try:
        ticket = db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()

        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")

        # Check access - admin can see all, users can only see their own
        if not is_platform_admin(current_user) and ticket.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")

        return {
            "ticket": {
                "id": ticket.id,
                "subject": ticket.subject,
                "description": ticket.description,
                "category": ticket.category,
                "priority": ticket.priority,
                "status": ticket.status,
                "user_email": ticket.user_email,
                "user_name": ticket.user_name,
                "organization_name": ticket.organization_name,
                "admin_notes": ticket.admin_notes if is_platform_admin(current_user) else None,
                "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
                "updated_at": ticket.updated_at.isoformat() if ticket.updated_at else None,
                "resolved_at": ticket.resolved_at.isoformat() if ticket.resolved_at else None,
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error fetching ticket: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/tickets/{ticket_id}")
async def update_ticket(
    ticket_id: int,
    update: TicketUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Update a ticket (admin only for most fields)"""
    try:
        ticket = db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()

        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")

        # Only admin can update tickets
        if not is_platform_admin(current_user):
            raise HTTPException(status_code=403, detail="Only administrators can update tickets")

        # Update fields
        if update.status:
            ticket.status = update.status
            if update.status in ["resolved", "closed"]:
                ticket.resolved_at = datetime.now(timezone.utc)

        if update.admin_notes is not None:
            ticket.admin_notes = update.admin_notes

        if update.assigned_to is not None:
            ticket.assigned_to = update.assigned_to

        ticket.updated_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(ticket)

        return {
            "success": True,
            "message": "Ticket updated successfully",
            "ticket": {
                "id": ticket.id,
                "status": ticket.status,
                "updated_at": ticket.updated_at.isoformat() if ticket.updated_at else None,
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"Error updating ticket: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/tickets/{ticket_id}/complete")
async def complete_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Mark a ticket as resolved/completed"""
    try:
        ticket = db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()

        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")

        # Only admin can complete tickets
        if not is_platform_admin(current_user):
            raise HTTPException(status_code=403, detail="Only administrators can complete tickets")

        ticket.status = "resolved"
        ticket.resolved_at = datetime.now(timezone.utc)
        ticket.updated_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(ticket)

        return {
            "success": True,
            "message": "Ticket marked as completed",
            "ticket": {
                "id": ticket.id,
                "status": ticket.status,
                "resolved_at": ticket.resolved_at.isoformat() if ticket.resolved_at else None,
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"Error completing ticket: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/tickets/{ticket_id}")
async def delete_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Delete a ticket (admin only)"""
    try:
        ticket = db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()

        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")

        # Only admin can delete tickets
        if not is_platform_admin(current_user):
            raise HTTPException(status_code=403, detail="Only administrators can delete tickets")

        db.delete(ticket)
        db.commit()

        return {
            "success": True,
            "message": "Ticket deleted successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"Error deleting ticket: {e}")
        raise HTTPException(status_code=500, detail=str(e))
