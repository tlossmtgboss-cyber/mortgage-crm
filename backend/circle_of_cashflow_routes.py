"""
Circle of Cashflow - API Routes
Referral ecosystem management for Perennia AI CRM
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timedelta
from typing import List, Optional
from pydantic import BaseModel
from routes.auth_deps import require_auth
import re

# Whitelist of allowed columns for referral_partners updates
_ALLOWED_PARTNER_COLUMNS = {
    'name', 'email', 'phone', 'company', 'role', 'status', 'notes',
    'partner_type', 'relationship_strength', 'last_contact_date',
    'address', 'city', 'state', 'zip_code', 'website', 'license_number',
    'specialty', 'commission_rate', 'referral_count', 'total_revenue',
}


def _safe_column_name(col: str) -> str:
    """Validate column name contains only safe characters for SQL interpolation."""
    if re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', col):
        return col
    return ''

# ============================================================================
# FEATURE TIER: EXPERIMENTAL
# This module is in the experimental tier -- frozen, no SLA.
# See backend/config/feature_tiers.py for tier definitions.
# ============================================================================

router = APIRouter(prefix="/api/v1/circle-of-cashflow", tags=["circle-of-cashflow"], dependencies=[Depends(require_auth)])

# Pydantic Models
class QuestionnaireCreate(BaseModel):
    contact_id: int
    name: str
    email: str
    phone: str = ""
    is_veteran: bool = False
    owned_home_before: Optional[bool] = None
    current_housing_status: str = ""
    previous_mortgage_type: str = ""
    current_monthly_payment: Optional[float] = None
    mortgage_priority: str = ""
    personal_goals: List[str] = []
    move_timeline: str = ""
    financial_philosophy: str = ""
    has_financial_planner: bool = False
    financial_planner_rating: str = ""
    has_accountant: bool = False
    accountant_rating: str = ""
    has_life_insurance_agent: bool = False
    life_insurance_agent_rating: str = ""
    has_estate_planner: bool = False
    estate_planner_rating: str = ""
    has_tax_deferred_retirement: bool = False

class PartnerCreate(BaseModel):
    business_name: str
    contact_name: str
    category: str
    email: str
    phone: str = ""
    website: str = ""
    calendar_link: str = ""
    service_area: List[str] = []
    specialties: List[str] = []
    license_number: str = ""
    partnership_start_date: Optional[str] = None

class OpportunityAcknowledge(BaseModel):
    acknowledgment_message: str
    client_response: str = ""

class ReferralCreate(BaseModel):
    direction: str
    contact_id: int
    partner_id: int
    category: str
    reason: str = ""
    introduction_method: str = "email"
    opportunity_id: Optional[int] = None

# Database dependency
def get_db():
    from database import engine
    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ============================================
# QUESTIONNAIRE ENDPOINTS
# ============================================

@router.post("/questionnaires")
async def submit_questionnaire(data: QuestionnaireCreate, db: Session = Depends(get_db)):
    """Submit a new mortgage questionnaire and detect referral opportunities"""

    # Insert questionnaire
    result = db.execute(text("""
        INSERT INTO mortgage_questionnaires (
            contact_id, name, email, phone, is_veteran, owned_home_before,
            current_housing_status, previous_mortgage_type, current_monthly_payment,
            mortgage_priority, personal_goals, move_timeline, financial_philosophy,
            has_financial_planner, financial_planner_rating, has_accountant, accountant_rating,
            has_life_insurance_agent, life_insurance_agent_rating, has_estate_planner,
            estate_planner_rating, has_tax_deferred_retirement
        ) VALUES (
            :contact_id, :name, :email, :phone, :is_veteran, :owned_home_before,
            :current_housing_status, :previous_mortgage_type, :current_monthly_payment,
            :mortgage_priority, :personal_goals, :move_timeline, :financial_philosophy,
            :has_financial_planner, :financial_planner_rating, :has_accountant, :accountant_rating,
            :has_life_insurance_agent, :life_insurance_agent_rating, :has_estate_planner,
            :estate_planner_rating, :has_tax_deferred_retirement
        ) RETURNING id
    """), {
        **data.dict(),
        "personal_goals": data.personal_goals
    })

    questionnaire_id = result.fetchone()[0]
    db.commit()

    # Detect referral opportunities
    opportunities = detect_opportunities(db, questionnaire_id, data)

    return {
        "questionnaire_id": questionnaire_id,
        "detected_opportunities": opportunities,
        "message": f"Questionnaire submitted. {len(opportunities)} referral opportunities detected."
    }

@router.get("/questionnaires/{questionnaire_id}")
async def get_questionnaire(questionnaire_id: int, db: Session = Depends(get_db)):
    """Get a questionnaire by ID"""
    result = db.execute(text("SELECT * FROM mortgage_questionnaires WHERE id = :id"), {"id": questionnaire_id})
    questionnaire = result.fetchone()
    if not questionnaire:
        raise HTTPException(status_code=404, detail="Questionnaire not found")
    return {"questionnaire": dict(questionnaire._mapping)}

def detect_opportunities(db: Session, questionnaire_id: int, data: QuestionnaireCreate):
    """AI-powered opportunity detection based on questionnaire responses"""
    opportunities = []

    # Financial Planner Detection
    if not data.has_financial_planner:
        wealth_goals = ['build_net_worth', 'financial_freedom', 'retirement_planning']
        if any(goal in data.personal_goals for goal in wealth_goals):
            opp = create_opportunity(db, data.contact_id, questionnaire_id,
                'financial_advisor', 'high',
                f"Client wants to {', '.join([g for g in data.personal_goals if g in wealth_goals])} "
                f"but has no financial planner. {data.financial_philosophy.capitalize()} philosophy "
                "suggests professional guidance would be valuable."
            )
            opportunities.append(opp)

    # Accountant Detection
    if not data.has_accountant:
        if data.owned_home_before or data.has_tax_deferred_retirement or 'investment_property' in data.personal_goals:
            priority = 'high' if 'investment_property' in data.personal_goals else 'medium'
            opp = create_opportunity(db, data.contact_id, questionnaire_id,
                'accountant', priority,
                "Homeowner with retirement contributions and potential investment goals needs tax planning support."
            )
            opportunities.append(opp)

    # Estate Planner Detection
    if not data.has_estate_planner:
        if data.current_housing_status == 'own' and any(g in data.personal_goals for g in ['financial_freedom', 'build_net_worth']):
            opp = create_opportunity(db, data.contact_id, questionnaire_id,
                'estate_attorney', 'medium',
                "Homeowner focused on long-term wealth building should have estate plan in place."
            )
            opportunities.append(opp)

    # Insurance Agent Detection (poor rating)
    if data.has_life_insurance_agent and data.life_insurance_agent_rating in ['poor', 'fair']:
        opp = create_opportunity(db, data.contact_id, questionnaire_id,
            'insurance_agent', 'low',
            f"Client rated current insurance agent as '{data.life_insurance_agent_rating}' - potential upgrade opportunity."
        )
        opportunities.append(opp)

    db.commit()
    return opportunities

def create_opportunity(db: Session, contact_id: int, questionnaire_id: int, category: str, priority: str, reasoning: str):
    """Create a referral opportunity"""
    result = db.execute(text("""
        INSERT INTO referral_opportunities (contact_id, questionnaire_id, category, priority, ai_reasoning)
        VALUES (:contact_id, :questionnaire_id, :category, :priority, :ai_reasoning)
        RETURNING id, category, priority, ai_reasoning, status
    """), {
        "contact_id": contact_id,
        "questionnaire_id": questionnaire_id,
        "category": category,
        "priority": priority,
        "ai_reasoning": reasoning
    })

    row = result.fetchone()
    return {
        "id": row[0],
        "category": row[1],
        "priority": row[2],
        "ai_reasoning": row[3],
        "status": row[4]
    }

@router.get("/questionnaires/contact/{contact_id}")
async def get_contact_questionnaires(contact_id: int, db: Session = Depends(get_db)):
    """Get all questionnaires for a contact"""
    result = db.execute(text("""
        SELECT * FROM mortgage_questionnaires WHERE contact_id = :contact_id ORDER BY submission_date DESC
    """), {"contact_id": contact_id})

    questionnaires = [dict(row._mapping) for row in result.fetchall()]
    return {"questionnaires": questionnaires}

# ============================================
# REFERRAL PARTNER ENDPOINTS
# ============================================

@router.post("/partners")
async def create_partner(data: PartnerCreate, db: Session = Depends(get_db)):
    """Create a new referral partner"""
    result = db.execute(text("""
        INSERT INTO referral_partners (
            business_name, contact_name, category, email, phone, website,
            calendar_link, service_area, specialties, license_number, partnership_start_date
        ) VALUES (
            :business_name, :contact_name, :category, :email, :phone, :website,
            :calendar_link, :service_area, :specialties, :license_number, :partnership_start_date
        ) RETURNING id
    """), {
        **data.dict(),
        "service_area": data.service_area,
        "specialties": data.specialties,
        "partnership_start_date": data.partnership_start_date or datetime.now().date().isoformat()
    })

    partner_id = result.fetchone()[0]
    db.commit()

    return {"id": partner_id, "message": "Partner created successfully"}

@router.get("/partners")
async def list_partners(
    category: Optional[str] = None,
    status: str = "active",
    min_trust_score: int = 0,
    db: Session = Depends(get_db)
):
    """List all referral partners with filtering"""
    query = """
        SELECT * FROM referral_partners
        WHERE relationship_status = :status AND trust_score >= :min_trust_score
    """
    params = {"status": status, "min_trust_score": min_trust_score}

    if category:
        query += " AND category = :category"
        params["category"] = category

    query += " ORDER BY trust_score DESC"

    result = db.execute(text(query), params)
    partners = [dict(row._mapping) for row in result.fetchall()]

    return {"partners": partners, "total": len(partners)}

@router.get("/partners/{partner_id}")
async def get_partner(partner_id: int, db: Session = Depends(get_db)):
    """Get partner details with stats"""
    result = db.execute(text("""
        SELECT * FROM referral_partners WHERE id = :partner_id
    """), {"partner_id": partner_id})

    partner = result.fetchone()
    if not partner:
        raise HTTPException(status_code=404, detail="Partner not found")

    # Get recent referrals
    referrals = db.execute(text("""
        SELECT * FROM referrals WHERE partner_id = :partner_id ORDER BY created_at DESC LIMIT 10
    """), {"partner_id": partner_id})

    return {
        "partner": dict(partner._mapping),
        "recent_referrals": [dict(r._mapping) for r in referrals.fetchall()]
    }

@router.patch("/partners/{partner_id}")
async def update_partner(partner_id: int, data: dict, db: Session = Depends(get_db)):
    """Update partner details"""
    # Build dynamic update query with column whitelist validation
    updates = []
    params = {"partner_id": partner_id}

    for key, value in data.items():
        safe_key = _safe_column_name(key)
        if not safe_key or safe_key not in _ALLOWED_PARTNER_COLUMNS:
            continue
        updates.append(f"{safe_key} = :{safe_key}")
        params[safe_key] = value

    if updates:
        query = f"UPDATE referral_partners SET {', '.join(updates)}, updated_at = NOW() WHERE id = :partner_id"
        db.execute(text(query), params)
        db.commit()

    return {"message": "Partner updated successfully"}

# ============================================
# OPPORTUNITY ENDPOINTS
# ============================================

@router.get("/opportunities")
async def list_opportunities(
    status: Optional[str] = None,
    contact_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """List referral opportunities with filtering"""
    query = "SELECT o.*, l.name as contact_name, l.email as contact_email FROM referral_opportunities o LEFT JOIN leads l ON o.contact_id = l.id WHERE 1=1"
    params = {}

    if status:
        query += " AND o.status = :status"
        params["status"] = status

    if contact_id:
        query += " AND o.contact_id = :contact_id"
        params["contact_id"] = contact_id

    query += " ORDER BY o.created_at DESC"

    result = db.execute(text(query), params)
    opportunities = [dict(row._mapping) for row in result.fetchall()]

    return {"opportunities": opportunities, "total": len(opportunities)}

@router.post("/opportunities/{opportunity_id}/acknowledge")
async def acknowledge_opportunity(opportunity_id: int, data: OpportunityAcknowledge, db: Session = Depends(get_db)):
    """Acknowledge an opportunity - client wants the referral"""
    db.execute(text("""
        UPDATE referral_opportunities
        SET status = 'acknowledged',
            acknowledged_date = NOW(),
            client_acknowledgment_message = :message,
            client_response = :response,
            client_requested = TRUE
        WHERE id = :id
    """), {
        "id": opportunity_id,
        "message": data.acknowledgment_message,
        "response": data.client_response
    })
    db.commit()

    return {"message": "Opportunity acknowledged", "status": "acknowledged"}

@router.post("/opportunities/{opportunity_id}/ready-to-send")
async def mark_ready_to_send(opportunity_id: int, loan_id: int, db: Session = Depends(get_db)):
    """Mark opportunity as ready to send (triggered by loan closing)"""
    db.execute(text("""
        UPDATE referral_opportunities
        SET status = 'ready_to_send',
            ready_to_send_date = NOW(),
            loan_id = :loan_id
        WHERE id = :id
    """), {"id": opportunity_id, "loan_id": loan_id})
    db.commit()

    return {"message": "Opportunity ready to send", "status": "ready_to_send"}

@router.post("/opportunities/{opportunity_id}/send")
async def send_introduction(opportunity_id: int, partner_id: int, introduction_method: str = "email", db: Session = Depends(get_db)):
    """Send the referral introduction"""
    # Update opportunity
    db.execute(text("""
        UPDATE referral_opportunities
        SET status = 'sent', sent_date = NOW(), assigned_partner_id = :partner_id
        WHERE id = :id
    """), {"id": opportunity_id, "partner_id": partner_id})

    # Get opportunity details
    opp = db.execute(text("SELECT * FROM referral_opportunities WHERE id = :id"), {"id": opportunity_id}).fetchone()

    # Create referral record
    db.execute(text("""
        INSERT INTO referrals (direction, contact_id, partner_id, opportunity_id, category, introduction_method)
        VALUES ('outbound', :contact_id, :partner_id, :opportunity_id, :category, :method)
    """), {
        "contact_id": opp.contact_id,
        "partner_id": partner_id,
        "opportunity_id": opportunity_id,
        "category": opp.category,
        "method": introduction_method
    })

    # Update partner stats
    db.execute(text("""
        UPDATE referral_partners
        SET total_referrals_sent = total_referrals_sent + 1, last_referral_sent_date = NOW()
        WHERE id = :id
    """), {"id": partner_id})

    db.commit()

    return {"message": "Introduction sent", "status": "sent"}

@router.get("/opportunities/{opportunity_id}/suggest-partner")
async def suggest_partner(opportunity_id: int, db: Session = Depends(get_db)):
    """AI-suggest the best partner for an opportunity"""
    opp = db.execute(text("SELECT * FROM referral_opportunities WHERE id = :id"), {"id": opportunity_id}).fetchone()
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    # Get eligible partners
    partners = db.execute(text("""
        SELECT * FROM referral_partners
        WHERE category = :category AND relationship_status = 'active' AND auto_referral_eligible = TRUE
        ORDER BY trust_score DESC
    """), {"category": opp.category})

    partners_list = [dict(p._mapping) for p in partners.fetchall()]

    if not partners_list:
        return {"recommended_partner": None, "message": "No eligible partners found for this category"}

    return {
        "recommended_partner": partners_list[0],
        "alternative_partners": partners_list[1:4],
        "reasoning": f"Selected based on highest trust score ({partners_list[0]['trust_score']}) in {opp.category} category"
    }

# ============================================
# REFERRAL TRACKING ENDPOINTS
# ============================================

@router.post("/referrals")
async def create_referral(data: ReferralCreate, db: Session = Depends(get_db)):
    """Create a manual referral (inbound or outbound)"""
    result = db.execute(text("""
        INSERT INTO referrals (direction, contact_id, partner_id, category, reason, introduction_method, opportunity_id)
        VALUES (:direction, :contact_id, :partner_id, :category, :reason, :introduction_method, :opportunity_id)
        RETURNING id
    """), data.dict())

    referral_id = result.fetchone()[0]

    # Update partner stats
    if data.direction == 'outbound':
        db.execute(text("""
            UPDATE referral_partners SET total_referrals_sent = total_referrals_sent + 1, last_referral_sent_date = NOW()
            WHERE id = :id
        """), {"id": data.partner_id})
    else:
        db.execute(text("""
            UPDATE referral_partners SET total_referrals_received = total_referrals_received + 1, last_referral_received_date = NOW()
            WHERE id = :id
        """), {"id": data.partner_id})

    db.commit()

    return {"id": referral_id, "message": "Referral created successfully"}

@router.get("/referrals")
async def list_referrals(
    direction: Optional[str] = None,
    status: Optional[str] = None,
    partner_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """List all referrals with filtering"""
    query = """
        SELECT r.*, l.name as contact_name, p.business_name as partner_name
        FROM referrals r
        LEFT JOIN leads l ON r.contact_id = l.id
        LEFT JOIN referral_partners p ON r.partner_id = p.id
        WHERE 1=1
    """
    params = {}

    if direction:
        query += " AND r.direction = :direction"
        params["direction"] = direction
    if status:
        query += " AND r.status = :status"
        params["status"] = status
    if partner_id:
        query += " AND r.partner_id = :partner_id"
        params["partner_id"] = partner_id

    query += " ORDER BY r.created_at DESC"

    result = db.execute(text(query), params)
    referrals = [dict(row._mapping) for row in result.fetchall()]

    return {"referrals": referrals, "total": len(referrals)}

@router.patch("/referrals/{referral_id}/status")
async def update_referral_status(referral_id: int, status: str, outcome: str = None, db: Session = Depends(get_db)):
    """Update referral status"""
    updates = ["status = :status", "updated_at = NOW()"]
    params = {"referral_id": referral_id, "status": status}

    if outcome:
        updates.append("outcome = :outcome")
        params["outcome"] = outcome

    if status == 'completed':
        updates.append("completed_date = NOW()")

    query = f"UPDATE referrals SET {', '.join(updates)} WHERE id = :referral_id"
    db.execute(text(query), params)
    db.commit()

    return {"message": "Referral updated"}

@router.get("/referrals/analytics")
async def get_referral_analytics(db: Session = Depends(get_db)):
    """Get referral analytics"""
    # Total counts
    totals = db.execute(text("""
        SELECT
            COUNT(*) FILTER (WHERE direction = 'outbound') as sent,
            COUNT(*) FILTER (WHERE direction = 'inbound') as received,
            COUNT(*) FILTER (WHERE outcome = 'converted') as converted
        FROM referrals
    """)).fetchone()

    # By category
    by_category = db.execute(text("""
        SELECT category, COUNT(*) as count, direction
        FROM referrals
        GROUP BY category, direction
        ORDER BY count DESC
    """))

    # Top partners
    top_partners = db.execute(text("""
        SELECT p.business_name, p.category, p.trust_score, p.total_referrals_sent, p.total_referrals_received
        FROM referral_partners p
        WHERE p.relationship_status = 'active'
        ORDER BY (p.total_referrals_sent + p.total_referrals_received) DESC
        LIMIT 10
    """))

    return {
        "total_sent": totals[0],
        "total_received": totals[1],
        "total_converted": totals[2],
        "by_category": [dict(row._mapping) for row in by_category.fetchall()],
        "top_partners": [dict(row._mapping) for row in top_partners.fetchall()]
    }

# ============================================
# PARTNER TOUCHPOINT ENDPOINTS
# ============================================

@router.post("/touchpoints")
async def create_touchpoint(partner_id: int, touchpoint_type: str, subject: str, message: str, method: str = "email", db: Session = Depends(get_db)):
    """Create a partner touchpoint"""
    result = db.execute(text("""
        INSERT INTO partner_touchpoints (partner_id, touchpoint_type, subject, message, method)
        VALUES (:partner_id, :touchpoint_type, :subject, :message, :method)
        RETURNING id
    """), {
        "partner_id": partner_id,
        "touchpoint_type": touchpoint_type,
        "subject": subject,
        "message": message,
        "method": method
    })

    touchpoint_id = result.fetchone()[0]
    db.commit()

    return {"id": touchpoint_id, "message": "Touchpoint created"}

@router.get("/touchpoints/partner/{partner_id}")
async def get_partner_touchpoints(partner_id: int, db: Session = Depends(get_db)):
    """Get touchpoint history for a partner"""
    result = db.execute(text("""
        SELECT * FROM partner_touchpoints WHERE partner_id = :partner_id ORDER BY touchpoint_date DESC
    """), {"partner_id": partner_id})

    touchpoints = [dict(row._mapping) for row in result.fetchall()]
    return {"touchpoints": touchpoints}

# Register router in main.py
def register_routes(app):
    app.include_router(router)
