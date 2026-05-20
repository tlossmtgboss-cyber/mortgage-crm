"""
Support Tickets Routes
Handles IT support ticket submission and management for the platform.
Master admin can view all tickets, regular users see only their own.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, text, JSON, select
from pydantic import BaseModel
from typing import Optional, List, Callable
from datetime import datetime, timezone, timedelta
import logging

from database import Base, get_db as db_get_db, engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_async_db

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


from auth.dependencies import get_current_user  # dedup: was local wrapper
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

# Add attachments column if missing (table predates this column)
try:
    with engine.connect() as conn:
        conn.execute(text(
            "ALTER TABLE support_tickets ADD COLUMN IF NOT EXISTS attachments JSON"
        ))
        conn.commit()
except Exception as e:
    logger.info(f"Note: support_tickets attachments column: {e}")


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
    """Check if user is a platform admin or site admin"""
    admin_roles = ['admin', 'super_admin', 'platform_admin', 'site_admin', 'master_admin']
    user_role = getattr(user, 'role', None)
    permission_role = getattr(user, 'permission_role', None)
    if user_role and user_role.lower() in admin_roles:
        return True
    if permission_role and permission_role.lower() in admin_roles:
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
        logger.error(f"Error fetching tickets: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/tickets")
async def create_ticket(
    ticket: TicketCreate,
    db: AsyncSession = Depends(get_async_db),
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
            result = await db.execute(text("SELECT name FROM organizations WHERE id = :org_id"), {"org_id": organization_id}).fetchone()
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
        await db.commit()
        await db.refresh(new_ticket)

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
    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(f"Error creating ticket: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


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
        logger.error(f"Error fetching ticket: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


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
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error updating ticket: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


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
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error completing ticket: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


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
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error deleting ticket: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/metrics")
async def get_ticket_metrics(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get ticket metrics summary (admin only)"""
    # Default metrics to return on error
    default_metrics = {
        "avg_per_day": 0,
        "turn_time_display": "N/A",
        "turn_time_hours": 0,
        "tickets_this_month": 0,
        "open_tickets": 0,
        "resolved_tickets": 0,
        "total_tickets": 0,
    }

    try:
        # Only admin can view metrics
        if not is_platform_admin(current_user):
            raise HTTPException(status_code=403, detail="Only administrators can view metrics")

        # Check if table exists first
        try:
            table_check = db.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'support_tickets'
                )
            """)).scalar()
            if not table_check:
                logger.warning("support_tickets table does not exist, returning default metrics")
                return default_metrics
        except Exception as table_err:
            logger.warning(f"Could not check for support_tickets table: {table_err}")
            return default_metrics

        # Get current month start
        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # Get 30 days ago for average calculation
        thirty_days_ago = now - timedelta(days=30)

        # Total tickets this month
        tickets_this_month = db.query(SupportTicket).filter(
            SupportTicket.created_at >= month_start
        ).count()

        # Tickets in last 30 days for average
        tickets_last_30_days = db.query(SupportTicket).filter(
            SupportTicket.created_at >= thirty_days_ago
        ).count()
        avg_per_day = round(tickets_last_30_days / 30, 1)

        # Average turn time (time to complete) for resolved tickets in last 90 days
        ninety_days_ago = now - timedelta(days=90)
        resolved_tickets = db.execute(text("""
            SELECT AVG(EXTRACT(EPOCH FROM (resolved_at - created_at)) / 3600) as avg_hours
            FROM support_tickets
            WHERE status IN ('resolved', 'closed')
            AND resolved_at IS NOT NULL
            AND created_at >= :start_date
        """), {"start_date": ninety_days_ago}).fetchone()

        avg_turn_time_hours = resolved_tickets[0] if resolved_tickets and resolved_tickets[0] else 0

        # Convert to days and hours
        if avg_turn_time_hours:
            avg_turn_days = int(avg_turn_time_hours // 24)
            avg_turn_hours = int(avg_turn_time_hours % 24)
            turn_time_display = f"{avg_turn_days}d {avg_turn_hours}h" if avg_turn_days > 0 else f"{avg_turn_hours}h"
        else:
            turn_time_display = "N/A"

        # Open vs resolved counts
        open_count = db.query(SupportTicket).filter(
            SupportTicket.status.in_(['open', 'in_progress'])
        ).count()

        resolved_count = db.query(SupportTicket).filter(
            SupportTicket.status.in_(['resolved', 'closed'])
        ).count()

        return {
            "avg_per_day": avg_per_day,
            "turn_time_display": turn_time_display,
            "turn_time_hours": round(avg_turn_time_hours, 1) if avg_turn_time_hours else 0,
            "tickets_this_month": tickets_this_month,
            "open_tickets": open_count,
            "resolved_tickets": resolved_count,
            "total_tickets": open_count + resolved_count,
        }
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Error fetching support metrics: {e}")
        # Return default metrics instead of 500 error
        return default_metrics


@router.get("/analytics")
async def get_ticket_analytics(
    months: int = 6,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user)
):
    """Get monthly ticket analytics for charts (admin only)"""
    try:
        # Only admin can view analytics
        if not is_platform_admin(current_user):
            raise HTTPException(status_code=403, detail="Only administrators can view analytics")

        # Get monthly submission data
        monthly_submissions = await db.execute(text("""
            SELECT
                DATE_TRUNC('month', created_at) as month,
                COUNT(*) as submissions,
                COUNT(CASE WHEN status IN ('resolved', 'closed') THEN 1 END) as resolved
            FROM support_tickets
            WHERE created_at >= NOW() - INTERVAL ':months months'
            GROUP BY DATE_TRUNC('month', created_at)
            ORDER BY month ASC
        """.replace(':months', str(months)))).fetchall()

        # Get monthly average turn time
        monthly_turn_time = await db.execute(text("""
            SELECT
                DATE_TRUNC('month', created_at) as month,
                AVG(EXTRACT(EPOCH FROM (resolved_at - created_at)) / 3600) as avg_hours
            FROM support_tickets
            WHERE status IN ('resolved', 'closed')
            AND resolved_at IS NOT NULL
            AND created_at >= NOW() - INTERVAL ':months months'
            GROUP BY DATE_TRUNC('month', created_at)
            ORDER BY month ASC
        """.replace(':months', str(months)))).fetchall()

        # Format monthly data
        submissions_data = []
        for row in monthly_submissions:
            month_str = row[0].strftime("%b %Y") if row[0] else "Unknown"
            submissions_data.append({
                "month": month_str,
                "submissions": row[1] or 0,
                "resolved": row[2] or 0,
            })

        turn_time_data = []
        for row in monthly_turn_time:
            month_str = row[0].strftime("%b %Y") if row[0] else "Unknown"
            hours = row[1] or 0
            turn_time_data.append({
                "month": month_str,
                "hours": round(hours, 1),
                "days": round(hours / 24, 1) if hours else 0,
            })

        return {
            "monthly_submissions": submissions_data,
            "monthly_turn_time": turn_time_data,
            "period_months": months,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching analytics: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
