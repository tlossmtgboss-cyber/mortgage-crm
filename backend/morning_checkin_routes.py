"""
Morning Check-in AI Routes
Captures daily business data and calculates referral partner ROI
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import text, func
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, date, timedelta
from decimal import Decimal
import logging

from database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/checkin", tags=["Morning Check-in"])


# ============================================================================
# Pydantic Models
# ============================================================================

class CheckinStart(BaseModel):
    date: Optional[str] = None  # YYYY-MM-DD, defaults to today


class LogHours(BaseModel):
    hours_worked: float


class AddLead(BaseModel):
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    partner_name: Optional[str] = None
    partner_id: Optional[int] = None
    loan_type: Optional[str] = None
    loan_amount: Optional[float] = None
    notes: Optional[str] = None


class LogPartnerInteraction(BaseModel):
    partner_id: Optional[int] = None
    partner_name: Optional[str] = None
    interaction_type: str  # call, meeting, event, lunch, email, text
    duration_minutes: int = 30
    notes: Optional[str] = None


class UpdatePartnerROI(BaseModel):
    partner_id: int
    active_loans_count: Optional[int] = None
    active_loans_value: Optional[float] = None
    closed_loans_12m: Optional[int] = None
    closed_volume_12m: Optional[float] = None
    total_revenue_12m: Optional[float] = None
    monthly_meeting_hours: Optional[float] = None
    monthly_followup_hours: Optional[float] = None
    monthly_event_hours: Optional[float] = None


class CheckinSettings(BaseModel):
    hourly_rate: Optional[float] = None
    checkin_reminder_time: Optional[str] = None
    checkin_enabled: Optional[bool] = None


# ============================================================================
# Helper Functions
# ============================================================================

async def get_current_user_id(
    request: Request,
    db: Session = Depends(get_db),
) -> int:
    """Extract authenticated user ID from JWT token."""
    from main import get_current_user_flexible
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        user = await get_current_user_flexible(token=token, request=request, db=db)
        return user.id
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Could not validate credentials")


def get_or_create_partner(db: Session, user_id: int, partner_name: str) -> int:
    """Get existing partner or create new one"""
    result = db.execute(text("""
        SELECT id FROM referral_partners
        WHERE LOWER(business_name) = LOWER(:name)
        LIMIT 1
    """), {"name": partner_name})
    row = result.fetchone()

    if row:
        return row[0]

    # Create new partner
    result = db.execute(text("""
        INSERT INTO referral_partners (created_by, business_name, contact_name, category, created_at)
        VALUES (:user_id, :name, :name, 'realtor', CURRENT_TIMESTAMP)
        RETURNING id
    """), {"user_id": user_id, "name": partner_name})
    db.commit()
    return result.fetchone()[0]


# ============================================================================
# Check-in Flow Endpoints
# ============================================================================

@router.post("/start")
async def start_checkin(
    request: CheckinStart,
    db: Session = Depends(get_db),
    _auth_user_id: int = Depends(get_current_user_id),
):
    """Start or get today's check-in session"""
    user_id = _auth_user_id
    checkin_date = date.fromisoformat(request.date) if request.date else date.today()

    # Check for existing check-in
    result = db.execute(text("""
        SELECT id, hours_worked, leads_added, partner_conversations, completed_at
        FROM daily_checkins
        WHERE user_id = :user_id AND checkin_date = :checkin_date
    """), {"user_id": user_id, "checkin_date": checkin_date})
    existing = result.fetchone()

    if existing:
        return {
            "checkin_id": existing[0],
            "date": str(checkin_date),
            "hours_worked": float(existing[1]) if existing[1] else None,
            "leads_added": existing[2],
            "partner_conversations": existing[3],
            "completed": existing[4] is not None,
            "is_new": False
        }

    # Create new check-in
    result = db.execute(text("""
        INSERT INTO daily_checkins (user_id, checkin_date)
        VALUES (:user_id, :checkin_date)
        RETURNING id
    """), {"user_id": user_id, "checkin_date": checkin_date})
    db.commit()
    checkin_id = result.fetchone()[0]

    return {
        "checkin_id": checkin_id,
        "date": str(checkin_date),
        "hours_worked": None,
        "leads_added": 0,
        "partner_conversations": 0,
        "completed": False,
        "is_new": True
    }


@router.post("/log-hours")
async def log_hours_worked(
    request: LogHours,
    db: Session = Depends(get_db),
    _auth_user_id: int = Depends(get_current_user_id),
):
    """Log hours worked for today's check-in"""
    user_id = _auth_user_id
    today = date.today()

    db.execute(text("""
        UPDATE daily_checkins
        SET hours_worked = :hours, updated_at = CURRENT_TIMESTAMP
        WHERE user_id = :user_id AND checkin_date = :date
    """), {"hours": request.hours_worked, "user_id": user_id, "date": today})
    db.commit()

    return {"success": True, "hours_logged": request.hours_worked}


@router.post("/add-lead")
async def add_lead_from_checkin(
    request: AddLead,
    db: Session = Depends(get_db),
    _auth_user_id: int = Depends(get_current_user_id),
):
    """Add a new lead during morning check-in"""
    user_id = _auth_user_id
    today = date.today()

    # Get or create referral partner
    partner_id = None
    if request.partner_id:
        partner_id = request.partner_id
    elif request.partner_name:
        partner_id = get_or_create_partner(db, user_id, request.partner_name)

    # Create lead
    result = db.execute(text("""
        INSERT INTO leads (
            name, phone, email, owner_id, referral_partner_id,
            loan_type, loan_amount, notes, stage, created_at
        ) VALUES (
            :name, :phone, :email, :owner_id, :partner_id,
            :loan_type, :loan_amount, :notes, 'New', CURRENT_TIMESTAMP
        )
        RETURNING id, name
    """), {
        "name": request.name,
        "phone": request.phone,
        "email": request.email,
        "owner_id": user_id,
        "partner_id": partner_id,
        "loan_type": request.loan_type,
        "loan_amount": request.loan_amount,
        "notes": request.notes
    })
    lead_row = result.fetchone()

    # Update check-in lead count
    db.execute(text("""
        UPDATE daily_checkins
        SET leads_added = leads_added + 1, updated_at = CURRENT_TIMESTAMP
        WHERE user_id = :user_id AND checkin_date = :date
    """), {"user_id": user_id, "date": today})

    db.commit()

    return {
        "success": True,
        "lead_id": lead_row[0],
        "lead_name": lead_row[1],
        "partner_id": partner_id,
        "message": f"Lead '{request.name}' added successfully"
    }


@router.post("/log-partner-interaction")
async def log_partner_interaction(
    request: LogPartnerInteraction,
    db: Session = Depends(get_db),
    _auth_user_id: int = Depends(get_current_user_id),
):
    """Log a conversation/interaction with a referral partner"""
    user_id = _auth_user_id
    today = date.today()

    # Get partner ID
    partner_id = request.partner_id
    if not partner_id and request.partner_name:
        partner_id = get_or_create_partner(db, user_id, request.partner_name)

    if not partner_id:
        raise HTTPException(status_code=400, detail="Partner ID or name required")

    # Get today's check-in ID
    result = db.execute(text("""
        SELECT id FROM daily_checkins
        WHERE user_id = :user_id AND checkin_date = :date
    """), {"user_id": user_id, "date": today})
    checkin_row = result.fetchone()
    checkin_id = checkin_row[0] if checkin_row else None

    # Create interaction record
    db.execute(text("""
        INSERT INTO partner_interactions (
            partner_id, user_id, interaction_date, interaction_type,
            duration_minutes, notes, checkin_id
        ) VALUES (
            :partner_id, :user_id, :date, :type,
            :duration, :notes, :checkin_id
        )
    """), {
        "partner_id": partner_id,
        "user_id": user_id,
        "date": today,
        "type": request.interaction_type,
        "duration": request.duration_minutes,
        "notes": request.notes,
        "checkin_id": checkin_id
    })

    # Update check-in conversation count
    if checkin_id:
        db.execute(text("""
            UPDATE daily_checkins
            SET partner_conversations = partner_conversations + 1, updated_at = CURRENT_TIMESTAMP
            WHERE id = :checkin_id
        """), {"checkin_id": checkin_id})

    db.commit()

    return {
        "success": True,
        "partner_id": partner_id,
        "interaction_type": request.interaction_type,
        "duration_minutes": request.duration_minutes
    }


@router.post("/complete")
async def complete_checkin(
    db: Session = Depends(get_db),
    _auth_user_id: int = Depends(get_current_user_id),
):
    """Mark today's check-in as complete"""
    user_id = _auth_user_id
    today = date.today()

    db.execute(text("""
        UPDATE daily_checkins
        SET completed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
        WHERE user_id = :user_id AND checkin_date = :date
    """), {"user_id": user_id, "date": today})
    db.commit()

    # Calculate and update ROI for partners with new interactions
    await calculate_partner_roi(db, user_id)

    return {"success": True, "message": "Check-in completed!"}


# ============================================================================
# Partner ROI Endpoints
# ============================================================================

@router.get("/partners/roi")
async def get_all_partners_roi(
    db: Session = Depends(get_db),
    _auth_user_id: int = Depends(get_current_user_id),
):
    """Get ROI metrics for all referral partners"""
    user_id = _auth_user_id

    result = db.execute(text("""
        SELECT
            rp.id,
            rp.business_name,
            rp.contact_name,
            rp.category,

            -- Lead metrics
            COUNT(DISTINCT l.id) as total_leads,
            COUNT(DISTINCT CASE WHEN l.created_at > NOW() - INTERVAL '12 months' THEN l.id END) as leads_12m,
            COUNT(DISTINCT CASE WHEN l.stage::text = 'Pre-Approved' THEN l.id END) as converted,

            -- Conversion rate
            CASE WHEN COUNT(DISTINCT l.id) > 0
                THEN ROUND(100.0 * COUNT(DISTINCT CASE WHEN l.stage::text = 'Pre-Approved' THEN l.id END) / COUNT(DISTINCT l.id), 1)
                ELSE 0 END as conversion_rate,

            -- Active pipeline
            COUNT(DISTINCT CASE WHEN l.stage::text != 'Pre-Approved' THEN l.id END) as active_leads,
            COALESCE(SUM(CASE WHEN l.stage::text != 'Pre-Approved' THEN l.loan_amount END), 0) as pipeline_value,

            -- Revenue (1% commission estimate)
            COALESCE(SUM(CASE WHEN l.stage::text = 'Pre-Approved' AND l.created_at > NOW() - INTERVAL '12 months'
                THEN l.loan_amount * 0.01 END), 0) as revenue_12m,

            -- Time investment
            COALESCE((SELECT SUM(duration_minutes) / 60.0 FROM partner_interactions pi
                WHERE pi.partner_id = rp.id AND pi.interaction_date > NOW() - INTERVAL '12 months'), 0) as hours_invested,

            -- Last contact
            (SELECT MAX(interaction_date) FROM partner_interactions pi WHERE pi.partner_id = rp.id) as last_contact

        FROM referral_partners rp
        LEFT JOIN leads l ON l.referral_partner_id = rp.id
        GROUP BY rp.id, rp.business_name, rp.contact_name, rp.category
        ORDER BY revenue_12m DESC
    """))

    partners = []
    for row in result:
        revenue = float(row[10]) if row[10] else 0
        hours = float(row[11]) if row[11] else 0
        hourly_rate = 150  # Default hourly rate
        time_cost = hours * hourly_rate
        net_profit = revenue - time_cost
        roi_pct = (net_profit / time_cost * 100) if time_cost > 0 else 0
        rev_per_hour = revenue / hours if hours > 0 else 0

        partners.append({
            "id": row[0],
            "name": row[1] or row[2],  # business_name or contact_name
            "company": row[1],  # business_name as company
            "partner_type": row[3],  # category
            "total_leads": row[4],
            "leads_12m": row[5],
            "converted": row[6],
            "conversion_rate": float(row[7]),
            "active_leads": row[8],
            "pipeline_value": float(row[9]),
            "revenue_12m": revenue,
            "hours_invested": hours,
            "time_cost": time_cost,
            "net_profit": net_profit,
            "roi_percentage": round(roi_pct, 1),
            "revenue_per_hour": round(rev_per_hour, 2),
            "last_contact": str(row[12]) if row[12] else None
        })

    # Sort by revenue per hour (most actionable metric)
    partners.sort(key=lambda x: x['revenue_per_hour'], reverse=True)

    return {
        "partners": partners,
        "count": len(partners),
        "summary": {
            "total_partners": len(partners),
            "top_performer": partners[0]["name"] if partners else None,
            "total_revenue_12m": sum(p["revenue_12m"] for p in partners),
            "total_hours_invested": sum(p["hours_invested"] for p in partners)
        }
    }


@router.get("/partners/{partner_id}/roi")
async def get_partner_roi_detail(
    partner_id: int,
    db: Session = Depends(get_db),
    _auth_user_id: int = Depends(get_current_user_id),
):
    """Get detailed ROI metrics for a specific partner"""
    user_id = _auth_user_id

    # Get partner info
    result = db.execute(text("""
        SELECT id, business_name, contact_name, category, email, phone
        FROM referral_partners
        WHERE id = :id
    """), {"id": partner_id})
    partner = result.fetchone()

    if not partner:
        raise HTTPException(status_code=404, detail="Partner not found")

    # Get lead breakdown
    leads_result = db.execute(text("""
        SELECT
            stage,
            COUNT(*) as count,
            COALESCE(SUM(loan_amount), 0) as total_value
        FROM leads
        WHERE referral_partner_id = :partner_id
        GROUP BY stage
    """), {"partner_id": partner_id})

    leads_by_stage = {row[0]: {"count": row[1], "value": float(row[2])} for row in leads_result}

    # Get recent interactions
    interactions_result = db.execute(text("""
        SELECT interaction_date, interaction_type, duration_minutes, notes
        FROM partner_interactions
        WHERE partner_id = :partner_id
        ORDER BY interaction_date DESC
        LIMIT 10
    """), {"partner_id": partner_id})

    interactions = [{
        "date": str(row[0]),
        "type": row[1],
        "duration_minutes": row[2],
        "notes": row[3]
    } for row in interactions_result]

    # Calculate totals
    total_leads = sum(s["count"] for s in leads_by_stage.values())
    converted = leads_by_stage.get("Pre-Approved", {}).get("count", 0)
    total_hours = sum(i["duration_minutes"] for i in interactions) / 60

    return {
        "partner": {
            "id": partner[0],
            "name": partner[1] or partner[2],  # business_name or contact_name
            "company": partner[1],  # business_name
            "type": partner[3],  # category
            "email": partner[4],
            "phone": partner[5]
        },
        "metrics": {
            "total_leads": total_leads,
            "converted_leads": converted,
            "conversion_rate": round(100 * converted / total_leads, 1) if total_leads > 0 else 0,
            "total_hours_invested": round(total_hours, 1)
        },
        "leads_by_stage": leads_by_stage,
        "recent_interactions": interactions
    }


@router.post("/partners/{partner_id}/roi-update")
async def update_partner_roi_data(
    partner_id: int,
    request: UpdatePartnerROI,
    db: Session = Depends(get_db),
    _auth_user_id: int = Depends(get_current_user_id),
):
    """Update ROI data for a partner (from AI conversation)"""
    user_id = _auth_user_id
    today = date.today()
    month_start = today.replace(day=1)

    # Update time investment
    if any([request.monthly_meeting_hours, request.monthly_followup_hours, request.monthly_event_hours]):
        db.execute(text("""
            INSERT INTO partner_time_investments (
                partner_id, user_id, month_year,
                meeting_hours, lead_followup_hours, event_hours, total_hours
            ) VALUES (
                :partner_id, :user_id, :month,
                :meeting, :followup, :events,
                COALESCE(:meeting, 0) + COALESCE(:followup, 0) + COALESCE(:events, 0)
            )
            ON CONFLICT (partner_id, user_id, month_year) DO UPDATE SET
                meeting_hours = COALESCE(EXCLUDED.meeting_hours, partner_time_investments.meeting_hours),
                lead_followup_hours = COALESCE(EXCLUDED.lead_followup_hours, partner_time_investments.lead_followup_hours),
                event_hours = COALESCE(EXCLUDED.event_hours, partner_time_investments.event_hours),
                total_hours = COALESCE(EXCLUDED.meeting_hours, partner_time_investments.meeting_hours) +
                              COALESCE(EXCLUDED.lead_followup_hours, partner_time_investments.lead_followup_hours) +
                              COALESCE(EXCLUDED.event_hours, partner_time_investments.event_hours),
                updated_at = CURRENT_TIMESTAMP
        """), {
            "partner_id": partner_id,
            "user_id": user_id,
            "month": month_start,
            "meeting": request.monthly_meeting_hours,
            "followup": request.monthly_followup_hours,
            "events": request.monthly_event_hours
        })

    db.commit()
    return {"success": True, "message": "Partner ROI data updated"}


@router.get("/settings")
async def get_checkin_settings(
    db: Session = Depends(get_db),
    _auth_user_id: int = Depends(get_current_user_id),
):
    """Get user's check-in settings"""
    user_id = _auth_user_id

    result = db.execute(text("""
        SELECT hourly_rate, checkin_reminder_time, checkin_enabled, auto_calculate_roi
        FROM user_checkin_settings
        WHERE user_id = :user_id
    """), {"user_id": user_id})
    settings = result.fetchone()

    if not settings:
        return {
            "hourly_rate": 150,
            "checkin_reminder_time": "08:00",
            "checkin_enabled": True,
            "auto_calculate_roi": True
        }

    return {
        "hourly_rate": float(settings[0]) if settings[0] else 150,
        "checkin_reminder_time": str(settings[1])[:5] if settings[1] else "08:00",
        "checkin_enabled": settings[2],
        "auto_calculate_roi": settings[3]
    }


@router.put("/settings")
async def update_checkin_settings(
    request: CheckinSettings,
    db: Session = Depends(get_db),
    _auth_user_id: int = Depends(get_current_user_id),
):
    """Update user's check-in settings"""
    user_id = _auth_user_id

    db.execute(text("""
        INSERT INTO user_checkin_settings (user_id, hourly_rate, checkin_reminder_time, checkin_enabled)
        VALUES (:user_id, :rate, :reminder_time, :enabled)
        ON CONFLICT (user_id) DO UPDATE SET
            hourly_rate = COALESCE(:rate, user_checkin_settings.hourly_rate),
            checkin_reminder_time = COALESCE(:reminder_time, user_checkin_settings.checkin_reminder_time),
            checkin_enabled = COALESCE(:enabled, user_checkin_settings.checkin_enabled),
            updated_at = CURRENT_TIMESTAMP
    """), {
        "user_id": user_id,
        "rate": request.hourly_rate,
        "reminder_time": request.checkin_reminder_time,
        "enabled": request.checkin_enabled
    })
    db.commit()

    return {"success": True, "message": "Settings updated"}


@router.get("/history")
async def get_checkin_history(
    days: int = 30,
    db: Session = Depends(get_db),
    _auth_user_id: int = Depends(get_current_user_id),
):
    """Get check-in history for the past N days"""
    user_id = _auth_user_id

    result = db.execute(text("""
        SELECT
            checkin_date,
            hours_worked,
            leads_added,
            partner_conversations,
            completed_at IS NOT NULL as completed
        FROM daily_checkins
        WHERE user_id = :user_id
        AND checkin_date > CURRENT_DATE - :days
        ORDER BY checkin_date DESC
    """), {"user_id": user_id, "days": days})

    history = [{
        "date": str(row[0]),
        "hours_worked": float(row[1]) if row[1] else None,
        "leads_added": row[2],
        "partner_conversations": row[3],
        "completed": row[4]
    } for row in result]

    return {
        "history": history,
        "days": days,
        "total_checkins": len([h for h in history if h["completed"]]),
        "total_hours": sum(h["hours_worked"] or 0 for h in history),
        "total_leads": sum(h["leads_added"] for h in history)
    }


# ============================================================================
# AI Intelligence Endpoints
# ============================================================================

@router.get("/ai/insights")
async def get_ai_insights(
    db: Session = Depends(get_db),
    _auth_user_id: int = Depends(get_current_user_id),
):
    """Get AI-generated insights about partner performance"""
    user_id = _auth_user_id

    insights = []

    # Check for partners with declining conversion
    result = db.execute(text("""
        SELECT COALESCE(rp.business_name, rp.contact_name) as partner_name, COUNT(*) as recent_leads,
            COUNT(CASE WHEN l.stage::text = 'Pre-Approved' THEN 1 END) as recent_converted
        FROM referral_partners rp
        JOIN leads l ON l.referral_partner_id = rp.id
        WHERE l.created_at > NOW() - INTERVAL '3 months'
        GROUP BY rp.id, rp.business_name, rp.contact_name
        HAVING COUNT(*) >= 3
        AND COUNT(CASE WHEN l.stage::text = 'Pre-Approved' THEN 1 END)::float / COUNT(*) < 0.3
    """))

    for row in result:
        insights.append({
            "type": "warning",
            "title": f"Low conversion from {row[0]}",
            "message": f"{row[0]} has sent {row[1]} leads in the last 3 months but only {row[2]} converted. Consider discussing lead quality.",
            "action": "schedule_call"
        })

    # Check for inactive partners
    result = db.execute(text("""
        SELECT COALESCE(rp.business_name, rp.contact_name) as partner_name, MAX(l.created_at) as last_lead
        FROM referral_partners rp
        LEFT JOIN leads l ON l.referral_partner_id = rp.id
        GROUP BY rp.id, rp.business_name, rp.contact_name
        HAVING MAX(l.created_at) < NOW() - INTERVAL '45 days'
        OR MAX(l.created_at) IS NULL
    """))

    for row in result:
        insights.append({
            "type": "info",
            "title": f"No leads from {row[0]}",
            "message": f"You haven't received a lead from {row[0]} in over 6 weeks. Time to reconnect?",
            "action": "follow_up"
        })

    # Check for high performers to celebrate
    result = db.execute(text("""
        SELECT COALESCE(rp.business_name, rp.contact_name) as partner_name, COUNT(*) as leads_this_month
        FROM referral_partners rp
        JOIN leads l ON l.referral_partner_id = rp.id
        WHERE l.created_at > DATE_TRUNC('month', CURRENT_DATE)
        GROUP BY rp.id, rp.business_name, rp.contact_name
        HAVING COUNT(*) >= 3
        ORDER BY COUNT(*) DESC
        LIMIT 3
    """))

    for row in result:
        insights.append({
            "type": "success",
            "title": f"Great month with {row[0]}!",
            "message": f"{row[0]} has sent you {row[1]} leads this month. Consider sending a thank you note.",
            "action": "thank_you"
        })

    return {
        "insights": insights,
        "generated_at": datetime.now().isoformat()
    }


async def calculate_partner_roi(db: Session, user_id: int):
    """Calculate and store ROI snapshots for all partners"""
    # This would be called after check-in completion
    # For now, just log that it was called
    logger.info(f"Calculating partner ROI for user {user_id}")
