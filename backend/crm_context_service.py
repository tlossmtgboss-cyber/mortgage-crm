"""
CRM Context Service
Provides full CRM data context for AI assistant
"""

from sqlalchemy.orm import Session
from sqlalchemy import func, text
from datetime import datetime, timedelta, date
from typing import Dict, Any, List
import logging

# Import CRM context cache for Redis caching
try:
    from services.crm_context_cache import crm_context_cache
    CRM_CACHE_AVAILABLE = True
except ImportError:
    crm_context_cache = None
    CRM_CACHE_AVAILABLE = False

# Import MUM calculation utilities for amortization
try:
    from utils_mum import calculate_current_balance, calculate_property_value
except ImportError:
    # Fallback if utils_mum not available
    import math
    def calculate_current_balance(original_amount, annual_rate, first_payment_date, loan_term_years=30):
        if isinstance(first_payment_date, str):
            first_payment_date = datetime.strptime(first_payment_date, '%Y-%m-%d').date()
        today = date.today()
        months_diff = (today.year - first_payment_date.year) * 12 + (today.month - first_payment_date.month)
        if today.day >= first_payment_date.day:
            months_diff += 1
        payments_made = max(0, months_diff)
        total_payments = loan_term_years * 12
        if payments_made >= total_payments:
            return 0
        if annual_rate == 0:
            return original_amount - (original_amount / total_payments * payments_made)
        monthly_rate = (annual_rate / 100) / 12
        balance = original_amount * (math.pow(1 + monthly_rate, total_payments) - math.pow(1 + monthly_rate, payments_made)) / (math.pow(1 + monthly_rate, total_payments) - 1)
        return max(0, round(balance, 2))

    def calculate_property_value(original_value, first_payment_date, annual_appreciation_rate=4.0):
        if isinstance(first_payment_date, str):
            first_payment_date = datetime.strptime(first_payment_date, '%Y-%m-%d').date()
        today = date.today()
        years_diff = (today - first_payment_date).days / 365.25
        current_value = original_value * math.pow(1 + (annual_appreciation_rate / 100), years_diff)
        return round(current_value, 2)

logger = logging.getLogger(__name__)


class CRMContextService:
    """Fetches comprehensive CRM data for AI context"""

    @staticmethod
    def get_full_crm_context(db: Session, user_id: int) -> Dict[str, Any]:
        """Get complete CRM data context for AI"""
        # Clear any previous failed transaction state
        try:
            db.rollback()
        except Exception as e:
            logger.exception(f"Failed to rollback previous transaction state: {e}")

        try:
            context = {
                "leads": CRMContextService._get_leads_context(db, user_id),
                "loans": CRMContextService._get_loans_context(db, user_id),
                "tasks": CRMContextService._get_tasks_context(db, user_id),
                "mum_clients": CRMContextService._get_mum_context(db, user_id),
                "pipeline": CRMContextService._get_pipeline_stats(db, user_id),
                "activities": CRMContextService._get_recent_activities(db, user_id),
                "referral_partners": CRMContextService._get_referral_partners(db, user_id),
                "team_performance": CRMContextService._get_team_performance(db, user_id),
                "loan_officer_performance": CRMContextService._get_loan_officer_performance(db, user_id),
                "top_referral_borrowers": CRMContextService._get_top_referral_borrowers(db, user_id),
                "rate_lock_intelligence": CRMContextService._get_rate_lock_context(),
                "pipeline_efficiency": CRMContextService._get_pipeline_efficiency_context(db, user_id),
            }
            return context
        except Exception as e:
            logger.error(f"Error getting CRM context: {e}")
            try:
                db.rollback()
            except Exception as e2:
                logger.exception(f"Failed to rollback after CRM context error: {e2}")
            return {}

    @staticmethod
    async def get_full_crm_context_cached(db: Session, user_id: int) -> Dict[str, Any]:
        """
        Get complete CRM data context with Redis caching.

        This is the preferred entry point - uses caching for performance.
        Falls back to uncached database queries if Redis unavailable.

        Performance: 20-50x faster on cache hits (5-15ms vs 200-500ms)

        Args:
            db: SQLAlchemy database session
            user_id: User ID for scoping the context

        Returns:
            Dict containing all CRM context data
        """
        # Try to get from cache first
        if CRM_CACHE_AVAILABLE and crm_context_cache.enabled:
            try:
                cached_context = await crm_context_cache.get_full_context(user_id)
                if cached_context is not None:
                    return cached_context
            except Exception as e:
                logger.warning(f"CRM cache read error, falling back to DB: {e}")

        # Cache miss or cache unavailable - fetch from database
        context = CRMContextService.get_full_crm_context(db, user_id)

        # Cache the result for next request
        if CRM_CACHE_AVAILABLE and crm_context_cache.enabled and context:
            try:
                await crm_context_cache.set_full_context(user_id, context)
            except Exception as e:
                logger.warning(f"CRM cache write error: {e}")

        return context

    @staticmethod
    def _get_leads_context(db: Session, user_id: int) -> Dict[str, Any]:
        """Get leads summary and details"""
        try:
            # Get lead counts by stage (all leads, not filtered by owner)
            result = db.execute(text("""
                SELECT stage, COUNT(*) as count
                FROM leads
                GROUP BY stage
            """))
            status_counts = {str(row[0]): row[1] for row in result}

            # Get total leads
            total = sum(status_counts.values())

            # Get recent leads with comprehensive details (all leads, not filtered by owner)
            result = db.execute(text("""
                SELECT id, name, email, phone, co_applicant_name,
                       stage, source, loan_type, preapproval_amount,
                       credit_score, annual_income, property_value, down_payment,
                       loan_amount, ltv, dti, interest_rate,
                       address, city, state, zip_code, property_type,
                       employment_status, employer_name, job_title,
                       processor, underwriter, loan_officer,
                       lock_date, lock_expiration, closing_date,
                       referral_source_score, referral_source_rating,
                       ai_score, sentiment, notes, last_contact,
                       created_at
                FROM leads
                ORDER BY created_at DESC
                LIMIT 50
            """))

            leads = []
            for row in result:
                leads.append({
                    "id": row[0],
                    "name": row[1],
                    "email": row[2],
                    "phone": row[3],
                    "co_borrower": row[4],
                    "stage": row[5],
                    "source": row[6],
                    "loan_type": row[7],
                    "loan_amount": float(row[8]) if row[8] else 0,
                    "credit_score": row[9],
                    "annual_income": float(row[10]) if row[10] else 0,
                    "property_value": float(row[11]) if row[11] else 0,
                    "down_payment": float(row[12]) if row[12] else 0,
                    "loan_amount_calc": float(row[13]) if row[13] else 0,
                    "ltv": float(row[14]) if row[14] else 0,
                    "dti": float(row[15]) if row[15] else 0,
                    "interest_rate": float(row[16]) if row[16] else 0,
                    "property_address": f"{row[17] or ''}, {row[18] or ''}, {row[19] or ''} {row[20] or ''}".strip(", "),
                    "property_type": row[21],
                    "employment_status": row[22],
                    "employer": row[23],
                    "job_title": row[24],
                    "processor": row[25],
                    "underwriter": row[26],
                    "loan_officer": row[27],
                    "lock_date": row[28].isoformat() if row[28] else None,
                    "lock_expiration": row[29].isoformat() if row[29] else None,
                    "closing_date": row[30].isoformat() if row[30] else None,
                    "referral_score": row[31],
                    "referral_rating": row[32],
                    "ai_score": row[33],
                    "sentiment": row[34],
                    "notes": row[35],
                    "last_contact": row[36].isoformat() if row[36] else None,
                    "created_at": row[37].isoformat() if row[37] else None
                })

            return {
                "total": total,
                "by_status": status_counts,
                "recent_leads": leads
            }
        except Exception as e:
            logger.error(f"Error getting leads context: {e}")
            try:
                db.rollback()
            except Exception as e2:
                logger.exception(f"Failed to rollback after leads context error: {e2}")
            return {"total": 0, "by_status": {}, "recent_leads": []}

    @staticmethod
    def _get_loans_context(db: Session, user_id: int) -> Dict[str, Any]:
        """Get loans/deals summary and details"""
        try:
            # Get loan counts by stage
            result = db.execute(text("""
                SELECT stage, COUNT(*) as count
                FROM loans
                WHERE loan_officer_id = :user_id
                GROUP BY stage
            """), {"user_id": user_id})
            stage_counts = {row[0]: row[1] for row in result}

            # Get total volume
            result = db.execute(text("""
                SELECT COALESCE(SUM(amount), 0)
                FROM loans
                WHERE loan_officer_id = :user_id
            """), {"user_id": user_id})
            total_volume = float(result.scalar() or 0)

            # Get recent loans with comprehensive details
            result = db.execute(text("""
                SELECT id, loan_number, borrower_name, coborrower_name,
                       stage, program, loan_type, amount,
                       purchase_price, down_payment, rate, term,
                       property_address,
                       lock_date, closing_date, funded_date,
                       processor, underwriter, realtor_agent, title_company,
                       days_in_stage, sla_status, risk_score,
                       ai_insights, predicted_close_date,
                       created_at
                FROM loans
                WHERE loan_officer_id = :user_id
                ORDER BY created_at DESC
                LIMIT 50
            """), {"user_id": user_id})

            loans = []
            for row in result:
                # Calculate LTV if we have purchase price
                loan_amount = float(row[7]) if row[7] else 0
                purchase_price = float(row[8]) if row[8] else 0
                down_payment = float(row[9]) if row[9] else 0
                ltv = (loan_amount / purchase_price * 100) if purchase_price > 0 else 0

                loans.append({
                    "id": row[0],
                    "loan_number": row[1],
                    "borrower_name": row[2],
                    "co_borrower": row[3],
                    "stage": row[4],
                    "program": row[5],
                    "loan_type": row[6],
                    "loan_amount": loan_amount,
                    "purchase_price": purchase_price,
                    "down_payment": down_payment,
                    "ltv": round(ltv, 1),
                    "interest_rate": float(row[10]) if row[10] else 0,
                    "term_months": row[11],
                    "property_address": row[12],
                    "lock_date": row[13].isoformat() if row[13] else None,
                    "closing_date": row[14].isoformat() if row[14] else None,
                    "funded_date": row[15].isoformat() if row[15] else None,
                    "processor": row[16],
                    "underwriter": row[17],
                    "realtor": row[18],
                    "title_company": row[19],
                    "days_in_stage": row[20],
                    "sla_status": row[21],
                    "risk_score": row[22],
                    "ai_insights": row[23],
                    "predicted_close": row[24].isoformat() if row[24] else None,
                    "created_at": row[25].isoformat() if row[25] else None
                })

            return {
                "total": sum(stage_counts.values()),
                "total_volume": total_volume,
                "by_stage": stage_counts,
                "recent_loans": loans
            }
        except Exception as e:
            logger.error(f"Error getting loans context: {e}")
            return {"total": 0, "total_volume": 0, "by_stage": {}, "recent_loans": []}

    @staticmethod
    def _get_tasks_context(db: Session, user_id: int) -> Dict[str, Any]:
        """Get tasks summary"""
        try:
            today = datetime.now().date()

            # Get task counts by status
            result = db.execute(text("""
                SELECT status, COUNT(*) as count
                FROM tasks
                WHERE owner_id = :user_id
                GROUP BY status
            """), {"user_id": user_id})
            status_counts = {row[0]: row[1] for row in result}

            # Get overdue tasks
            result = db.execute(text("""
                SELECT COUNT(*)
                FROM tasks
                WHERE owner_id = :user_id
                AND status != 'completed'
                AND due_date < :today
            """), {"user_id": user_id, "today": today})
            overdue = result.scalar() or 0

            # Get today's tasks (includes overdue, today, and high-priority tasks)
            result = db.execute(text("""
                SELECT id, title, description, priority, due_date, status, lead_id
                FROM tasks
                WHERE owner_id = :user_id
                AND status != 'completed'
                AND (
                    DATE(due_date) <= :today
                    OR priority IN ('HIGH', 'URGENT')
                )
                ORDER BY
                    CASE
                        WHEN due_date < :today THEN 1
                        WHEN DATE(due_date) = :today THEN 2
                        ELSE 3
                    END,
                    priority DESC,
                    due_date ASC
                LIMIT 50
            """), {"user_id": user_id, "today": today})

            todays_tasks = []
            for row in result:
                todays_tasks.append({
                    "id": row[0],
                    "title": row[1],
                    "description": row[2],
                    "priority": row[3],
                    "due_date": row[4].isoformat() if row[4] else None,
                    "status": row[5],
                    "lead_id": row[6]
                })

            # Get upcoming tasks (next 7 days)
            result = db.execute(text("""
                SELECT id, title, priority, due_date, status
                FROM tasks
                WHERE owner_id = :user_id
                AND status != 'completed'
                AND due_date BETWEEN :today AND :week_later
                ORDER BY due_date ASC
                LIMIT 20
            """), {"user_id": user_id, "today": today, "week_later": today + timedelta(days=7)})

            upcoming = []
            for row in result:
                upcoming.append({
                    "id": row[0],
                    "title": row[1],
                    "priority": row[2],
                    "due_date": row[3].isoformat() if row[3] else None,
                    "status": row[4]
                })

            # Get pending reconciliation items that need review
            result = db.execute(text("""
                SELECT ed.id, ed.category, ed.subcategory, ed.fields, ed.match_confidence,
                       ide.subject, ide.sender_email, ide.created_at
                FROM extracted_data ed
                JOIN incoming_data_events ide ON ed.event_id = ide.id
                WHERE ed.status IN ('pending_review', 'needs_review')
                AND (ide.user_id = :user_id OR ide.user_id IS NULL)
                ORDER BY ide.created_at DESC
                LIMIT 20
            """), {"user_id": user_id})

            pending_reconciliation = []
            for row in result:
                fields = row[3] if row[3] else {}
                borrower_name = None
                if isinstance(fields, dict):
                    borrower_name = fields.get('borrower_name', {}).get('value') if isinstance(fields.get('borrower_name'), dict) else fields.get('borrower_name')

                pending_reconciliation.append({
                    "id": row[0],
                    "category": row[1],
                    "subcategory": row[2],
                    "borrower_name": borrower_name,
                    "match_confidence": row[4],
                    "subject": row[5],
                    "sender": row[6],
                    "received_at": row[7].isoformat() if row[7] else None
                })

            return {
                "total": sum(status_counts.values()),
                "by_status": status_counts,
                "overdue": overdue,
                "todays_tasks": todays_tasks,
                "upcoming": upcoming,
                "pending_reconciliation": pending_reconciliation,
                "pending_reconciliation_count": len(pending_reconciliation)
            }
        except Exception as e:
            logger.error(f"Error getting tasks context: {e}")
            return {"total": 0, "by_status": {}, "overdue": 0, "todays_tasks": [], "upcoming": [], "pending_reconciliation": [], "pending_reconciliation_count": 0}

    @staticmethod
    def _get_mum_context(db: Session, user_id: int) -> Dict[str, Any]:
        """Get Mortgages Under Management clients with comprehensive details and calculated LTV"""
        try:
            result = db.execute(text("""
                SELECT id, name, email, phone,
                       original_loan_amount, current_property_value, estimated_equity,
                       interest_rate, loan_type, original_loan_date,
                       next_review_date, last_contact_date,
                       engagement_score, lifecycle_stage, next_touchpoint_type,
                       loan_officer_name, status,
                       first_payment_date, loan_term, original_property_value
                FROM mum_clients
                WHERE user_id = :user_id OR loan_officer_name IS NOT NULL
                ORDER BY next_review_date ASC NULLS LAST
                LIMIT 50
            """), {"user_id": user_id})

            clients = []
            for row in result:
                original_loan = float(row[4]) if row[4] else 0
                stored_property_value = float(row[5]) if row[5] else 0
                interest_rate = float(row[7]) if row[7] else 0
                first_payment = row[17]
                loan_term_years = int(row[18]) if row[18] else 30
                original_property = float(row[19]) if row[19] else stored_property_value

                # Calculate current balance from amortization
                if first_payment and original_loan > 0:
                    current_balance = calculate_current_balance(
                        original_loan,
                        interest_rate,
                        first_payment,
                        loan_term_years
                    )
                    # Calculate payments made
                    if isinstance(first_payment, str):
                        fp_date = datetime.strptime(first_payment, '%Y-%m-%d').date()
                    else:
                        fp_date = first_payment
                    today = date.today()
                    payments_made = max(0, (today.year - fp_date.year) * 12 + (today.month - fp_date.month))
                else:
                    current_balance = original_loan * 0.95  # Fallback estimate
                    payments_made = 0

                # Calculate current property value with appreciation
                if first_payment and original_property > 0:
                    current_property_value = calculate_property_value(
                        original_property,
                        first_payment,
                        4.0  # 4% annual appreciation
                    )
                else:
                    current_property_value = stored_property_value

                # Calculate real-time LTV and equity
                current_ltv = (current_balance / current_property_value * 100) if current_property_value > 0 else 0
                current_equity = current_property_value - current_balance
                equity_pct = (current_equity / current_property_value * 100) if current_property_value > 0 else 0

                clients.append({
                    "id": row[0],
                    "name": row[1],
                    "email": row[2],
                    "phone": row[3],
                    "original_loan_amount": original_loan,
                    "current_balance": round(current_balance, 2),
                    "payments_made": payments_made,
                    "original_property_value": original_property,
                    "current_property_value": round(current_property_value, 2),
                    "current_equity": round(current_equity, 2),
                    "equity_percent": round(equity_pct, 1),
                    "current_ltv": round(current_ltv, 1),
                    "interest_rate": interest_rate,
                    "loan_type": row[8],
                    "loan_term_years": loan_term_years,
                    "first_payment_date": first_payment.isoformat() if first_payment else None,
                    "original_loan_date": row[9].isoformat() if row[9] else None,
                    "next_review_date": row[10].isoformat() if row[10] else None,
                    "last_contact_date": row[11].isoformat() if row[11] else None,
                    "engagement_score": row[12],
                    "lifecycle_stage": row[13],
                    "next_touchpoint": row[14],
                    "loan_officer": row[15],
                    "status": row[16]
                })

            # Get total count
            result = db.execute(text("""
                SELECT COUNT(*) FROM mum_clients WHERE user_id = :user_id
            """), {"user_id": user_id})
            total = result.scalar() or 0

            return {
                "total": total,
                "clients": clients
            }
        except Exception as e:
            logger.error(f"Error getting MUM context: {e}")
            return {"total": 0, "clients": []}

    @staticmethod
    def _get_pipeline_stats(db: Session, user_id: int) -> Dict[str, Any]:
        """Get pipeline statistics"""
        try:
            # Get closing this month
            result = db.execute(text("""
                SELECT COUNT(*), COALESCE(SUM(amount), 0)
                FROM loans
                WHERE loan_officer_id = :user_id
                AND DATE_TRUNC('month', closing_date) = DATE_TRUNC('month', CURRENT_DATE)
            """), {"user_id": user_id})
            row = result.fetchone()
            closing_this_month = {"count": row[0], "volume": float(row[1])}

            # Get conversion rates (all leads)
            result = db.execute(text("""
                SELECT
                    COUNT(*) FILTER (WHERE stage = 'Pre-Approved') as pre_approved,
                    COUNT(*) FILTER (WHERE stage = 'Application') as applications,
                    COUNT(*) FILTER (WHERE stage IN ('Closed Won', 'Funded')) as closed
                FROM leads
            """))
            row = result.fetchone()

            return {
                "closing_this_month": closing_this_month,
                "pre_approved": row[0] or 0,
                "applications": row[1] or 0,
                "closed": row[2] or 0
            }
        except Exception as e:
            logger.error(f"Error getting pipeline stats: {e}")
            return {"closing_this_month": {"count": 0, "volume": 0}}

    @staticmethod
    def _get_recent_activities(db: Session, user_id: int) -> List[Dict]:
        """Get recent activities"""
        try:
            result = db.execute(text("""
                SELECT id, activity_type, description, lead_id, created_at
                FROM activities
                WHERE user_id = :user_id
                ORDER BY created_at DESC
                LIMIT 20
            """), {"user_id": user_id})

            return [{
                "id": row[0],
                "type": row[1],
                "description": row[2],
                "lead_id": row[3],
                "created_at": row[4].isoformat() if row[4] else None
            } for row in result]
        except Exception as e:
            logger.error(f"Error getting activities: {e}")
            return []

    @staticmethod
    def _get_referral_partners(db: Session, user_id: int) -> Dict[str, Any]:
        """Get referral partners with performance metrics"""
        try:
            # First try to get partners with lead performance data
            result = db.execute(text("""
                SELECT
                    rp.id,
                    rp.name,
                    rp.company,
                    rp.email,
                    rp.phone,
                    COUNT(l.id) as total_leads,
                    COUNT(l.id) FILTER (WHERE l.stage = 'Closed Won') as closed_deals,
                    COALESCE(SUM(l.preapproval_amount) FILTER (WHERE l.stage = 'Closed Won'), 0) as total_revenue,
                    COALESCE(AVG(l.preapproval_amount) FILTER (WHERE l.stage = 'Closed Won'), 0) as avg_deal_size,
                    CASE
                        WHEN COUNT(l.id) > 0
                        THEN ROUND(COUNT(l.id) FILTER (WHERE l.stage = 'Closed Won')::numeric / COUNT(l.id) * 100, 1)
                        ELSE 0
                    END as close_rate_pct
                FROM referral_partners rp
                LEFT JOIN leads l ON l.source = rp.name AND l.owner_id = :user_id
                WHERE rp.user_id = :user_id
                GROUP BY rp.id, rp.name, rp.company, rp.email, rp.phone
                ORDER BY total_revenue DESC NULLS LAST, total_leads DESC
                LIMIT 20
            """), {"user_id": user_id})

            partners = []
            for row in result:
                partners.append({
                    "id": row[0],
                    "name": row[1],
                    "company": row[2],
                    "email": row[3],
                    "phone": row[4],
                    "total_leads": row[5] or 0,
                    "closed_deals": row[6] or 0,
                    "total_revenue": float(row[7]) if row[7] else 0,
                    "avg_deal_size": float(row[8]) if row[8] else 0,
                    "close_rate_pct": float(row[9]) if row[9] else 0
                })

            # Identify most profitable partner
            most_profitable = None
            if partners and partners[0]["total_revenue"] > 0:
                most_profitable = {
                    "name": partners[0]["name"],
                    "revenue": partners[0]["total_revenue"],
                    "deals": partners[0]["closed_deals"]
                }

            return {
                "total": len(partners),
                "partners": partners,
                "most_profitable": most_profitable
            }
        except Exception as e:
            logger.error(f"Error getting referral partners: {e}")
            try:
                db.rollback()
            except Exception as e2:
                logger.exception(f"Failed to rollback after referral partners error: {e2}")
            return {"total": 0, "partners": [], "most_profitable": None}

    @staticmethod
    def _get_team_performance(db: Session, user_id: int) -> Dict[str, Any]:
        """Get team member performance metrics (processors, underwriters, etc.)"""
        try:
            # Get all team members with their KPIs
            result = db.execute(text("""
                SELECT
                    id,
                    name,
                    email,
                    role,
                    loans_processed,
                    avg_close_time,
                    satisfaction_score,
                    volume,
                    status
                FROM team_member_profiles
                WHERE is_deleted = false
                AND status = 'active'
                ORDER BY role, loans_processed DESC
            """))

            team_members = []
            processors = []
            underwriters = []
            closers = []

            for row in result:
                member = {
                    "id": str(row[0]),
                    "name": row[1],
                    "email": row[2],
                    "role": row[3],
                    "loans_processed": row[4] or 0,
                    "avg_close_time": float(row[5]) if row[5] else None,
                    "satisfaction_score": float(row[6]) if row[6] else None,
                    "volume": float(row[7]) if row[7] else 0,
                    "status": row[8]
                }
                team_members.append(member)

                # Categorize by role
                if row[3] == 'processor':
                    processors.append(member)
                elif row[3] == 'underwriter':
                    underwriters.append(member)
                elif row[3] == 'closer':
                    closers.append(member)

            # Calculate averages for benchmarking
            def calc_avg(members, field):
                values = [m[field] for m in members if m[field] is not None]
                return sum(values) / len(values) if values else None

            # Identify under-performers (below average on key metrics)
            def identify_underperformers(members, role_name):
                if not members:
                    return []

                avg_loans = calc_avg(members, 'loans_processed')
                avg_time = calc_avg(members, 'avg_close_time')
                avg_satisfaction = calc_avg(members, 'satisfaction_score')

                underperformers = []
                for m in members:
                    issues = []
                    if avg_loans and m['loans_processed'] < avg_loans * 0.7:
                        issues.append(f"low volume ({m['loans_processed']} vs avg {avg_loans:.0f})")
                    if avg_time and m['avg_close_time'] and m['avg_close_time'] > avg_time * 1.3:
                        issues.append(f"slow turn time ({m['avg_close_time']:.1f} days vs avg {avg_time:.1f})")
                    if avg_satisfaction and m['satisfaction_score'] and m['satisfaction_score'] < avg_satisfaction * 0.8:
                        issues.append(f"low satisfaction ({m['satisfaction_score']:.1f} vs avg {avg_satisfaction:.1f})")

                    if issues:
                        underperformers.append({
                            "name": m['name'],
                            "role": role_name,
                            "issues": issues,
                            "loans_processed": m['loans_processed'],
                            "avg_close_time": m['avg_close_time'],
                            "satisfaction_score": m['satisfaction_score']
                        })

                return underperformers

            # Get underperformers by role
            underperforming_processors = identify_underperformers(processors, 'Processor')
            underperforming_underwriters = identify_underperformers(underwriters, 'Underwriter')
            underperforming_closers = identify_underperformers(closers, 'Closer')

            return {
                "total_team_members": len(team_members),
                "processors": {
                    "count": len(processors),
                    "members": processors,
                    "avg_loans_processed": calc_avg(processors, 'loans_processed'),
                    "avg_close_time": calc_avg(processors, 'avg_close_time'),
                    "avg_satisfaction": calc_avg(processors, 'satisfaction_score'),
                    "underperformers": underperforming_processors
                },
                "underwriters": {
                    "count": len(underwriters),
                    "members": underwriters,
                    "avg_loans_processed": calc_avg(underwriters, 'loans_processed'),
                    "avg_close_time": calc_avg(underwriters, 'avg_close_time'),
                    "avg_satisfaction": calc_avg(underwriters, 'satisfaction_score'),
                    "underperformers": underperforming_underwriters
                },
                "closers": {
                    "count": len(closers),
                    "members": closers,
                    "avg_loans_processed": calc_avg(closers, 'loans_processed'),
                    "avg_close_time": calc_avg(closers, 'avg_close_time'),
                    "avg_satisfaction": calc_avg(closers, 'satisfaction_score'),
                    "underperformers": underperforming_closers
                },
                "all_underperformers": underperforming_processors + underperforming_underwriters + underperforming_closers
            }
        except Exception as e:
            logger.error(f"Error getting team performance: {e}")
            try:
                db.rollback()
            except Exception as e2:
                logger.exception(f"Failed to rollback after team performance error: {e2}")
            return {
                "total_team_members": 0,
                "processors": {"count": 0, "members": [], "underperformers": []},
                "underwriters": {"count": 0, "members": [], "underperformers": []},
                "closers": {"count": 0, "members": [], "underperformers": []},
                "all_underperformers": []
            }

    @staticmethod
    def _get_loan_officer_performance(db: Session, user_id: int) -> Dict[str, Any]:
        """Get loan officer performance metrics for business impact analysis"""
        try:
            # Get all loan officers with their production metrics
            result = db.execute(text("""
                WITH lo_stats AS (
                    SELECT
                        u.id,
                        u.full_name,
                        u.email,
                        u.department,
                        u.role,
                        -- Funded loans (last 12 months)
                        COUNT(CASE WHEN l.stage = 'Funded'
                            AND l.funded_date >= CURRENT_DATE - INTERVAL '12 months'
                            THEN 1 END) as units_closed_12m,
                        COALESCE(SUM(CASE WHEN l.stage = 'Funded'
                            AND l.funded_date >= CURRENT_DATE - INTERVAL '12 months'
                            THEN l.amount END), 0) as volume_closed_12m,
                        -- Active pipeline
                        COUNT(CASE WHEN l.stage NOT IN ('Funded', 'Closed', 'Cancelled', 'Withdrawn')
                            THEN 1 END) as active_pipeline_count,
                        COALESCE(SUM(CASE WHEN l.stage NOT IN ('Funded', 'Closed', 'Cancelled', 'Withdrawn')
                            THEN l.amount END), 0) as active_pipeline_volume,
                        -- Average days to close (funded loans)
                        AVG(CASE WHEN l.stage = 'Funded'
                            AND l.funded_date >= CURRENT_DATE - INTERVAL '12 months'
                            AND l.funded_date IS NOT NULL
                            AND l.created_at IS NOT NULL
                            THEN EXTRACT(DAY FROM (l.funded_date - l.created_at))
                            END) as avg_days_to_close,
                        -- Total leads assigned
                        (SELECT COUNT(*) FROM leads WHERE owner_id = u.id) as total_leads,
                        -- Conversion rate (funded / total leads)
                        CASE WHEN (SELECT COUNT(*) FROM leads WHERE owner_id = u.id) > 0
                            THEN (COUNT(CASE WHEN l.stage = 'Funded'
                                AND l.funded_date >= CURRENT_DATE - INTERVAL '12 months'
                                THEN 1 END)::float /
                                (SELECT COUNT(*) FROM leads WHERE owner_id = u.id)::float * 100)
                            ELSE 0
                        END as conversion_rate
                    FROM users u
                    LEFT JOIN loans l ON l.loan_officer_id = u.id
                    WHERE u.role IN ('loan_officer', 'sales')
                    AND u.account_status = 'active'
                    GROUP BY u.id, u.full_name, u.email, u.department, u.role
                )
                SELECT
                    id, full_name, email, department, role,
                    units_closed_12m, volume_closed_12m,
                    active_pipeline_count, active_pipeline_volume,
                    avg_days_to_close, total_leads, conversion_rate
                FROM lo_stats
                ORDER BY volume_closed_12m DESC
            """))

            loan_officers = []
            for row in result:
                volume = float(row[6]) if row[6] else 0
                units = row[5] or 0
                avg_days = float(row[9]) if row[9] else 0
                conversion = float(row[11]) if row[11] else 0

                # Calculate revenue (assume 2% avg origination fee)
                revenue_12m = volume * 0.02

                # Calculate efficiency score (units per month worked)
                efficiency_score = round(units / 12.0, 2) if units > 0 else 0

                # Revenue per unit
                revenue_per_unit = revenue_12m / units if units > 0 else 0

                loan_officers.append({
                    "id": row[0],
                    "name": row[1],
                    "email": row[2],
                    "department": row[3],
                    "role": row[4],
                    "units_closed_12m": units,
                    "volume_closed_12m": volume,
                    "revenue_12m": revenue_12m,
                    "revenue_per_unit": revenue_per_unit,
                    "active_pipeline_count": row[7] or 0,
                    "active_pipeline_volume": float(row[8]) if row[8] else 0,
                    "avg_days_to_close": avg_days,
                    "total_leads": row[10] or 0,
                    "conversion_rate": conversion,
                    "efficiency_score": efficiency_score,
                    "units_per_month": efficiency_score
                })

            # Calculate team averages for benchmarking
            if loan_officers:
                total_los = len(loan_officers)
                avg_volume = sum(lo['volume_closed_12m'] for lo in loan_officers) / total_los
                avg_units = sum(lo['units_closed_12m'] for lo in loan_officers) / total_los
                avg_conversion = sum(lo['conversion_rate'] for lo in loan_officers) / total_los
                avg_efficiency = sum(lo['efficiency_score'] for lo in loan_officers) / total_los
                avg_days = sum(lo['avg_days_to_close'] for lo in loan_officers if lo['avg_days_to_close'] > 0) / len([lo for lo in loan_officers if lo['avg_days_to_close'] > 0]) if any(lo['avg_days_to_close'] > 0 for lo in loan_officers) else 0
            else:
                avg_volume = avg_units = avg_conversion = avg_efficiency = avg_days = 0

            # Identify high producers with low efficiency
            high_volume_low_efficiency = []
            for lo in loan_officers:
                is_high_producer = lo['volume_closed_12m'] > avg_volume * 1.2
                is_low_efficiency = lo['efficiency_score'] < avg_efficiency * 0.8

                if is_high_producer and is_low_efficiency:
                    # Calculate business impact of losing this LO
                    annual_revenue_loss = lo['revenue_12m']
                    pipeline_at_risk = lo['active_pipeline_volume'] * 0.02

                    high_volume_low_efficiency.append({
                        "name": lo['name'],
                        "volume_12m": lo['volume_closed_12m'],
                        "revenue_12m": lo['revenue_12m'],
                        "efficiency_score": lo['efficiency_score'],
                        "avg_efficiency": avg_efficiency,
                        "efficiency_gap": round((avg_efficiency - lo['efficiency_score']) / avg_efficiency * 100, 1),
                        "conversion_rate": lo['conversion_rate'],
                        "avg_days_to_close": lo['avg_days_to_close'],
                        "pipeline_at_risk": pipeline_at_risk,
                        "business_impact": {
                            "immediate_revenue_loss": annual_revenue_loss,
                            "pipeline_at_risk": pipeline_at_risk,
                            "total_potential_loss": annual_revenue_loss + pipeline_at_risk,
                            "replacement_cost": annual_revenue_loss * 0.5,  # Assume 6 months to replace production
                            "market_share_impact": round(lo['volume_closed_12m'] / sum(x['volume_closed_12m'] for x in loan_officers) * 100, 1) if sum(x['volume_closed_12m'] for x in loan_officers) > 0 else 0
                        }
                    })

            return {
                "total_loan_officers": len(loan_officers),
                "loan_officers": loan_officers,
                "team_averages": {
                    "avg_volume_12m": avg_volume,
                    "avg_units_12m": avg_units,
                    "avg_conversion_rate": avg_conversion,
                    "avg_efficiency_score": avg_efficiency,
                    "avg_days_to_close": avg_days
                },
                "high_volume_low_efficiency": high_volume_low_efficiency,
                "total_team_volume": sum(lo['volume_closed_12m'] for lo in loan_officers),
                "total_team_revenue": sum(lo['revenue_12m'] for lo in loan_officers)
            }
        except Exception as e:
            logger.error(f"Error getting loan officer performance: {e}")
            try:
                db.rollback()
            except Exception as e2:
                logger.exception(f"Failed to rollback after loan officer performance error: {e2}")
            return {
                "total_loan_officers": 0,
                "loan_officers": [],
                "team_averages": {},
                "high_volume_low_efficiency": [],
                "total_team_volume": 0,
                "total_team_revenue": 0
            }

    @staticmethod
    def _get_rate_lock_context() -> Dict[str, Any]:
        """Get rate lock intelligence and market conditions"""
        try:
            import asyncio
            from scrapers.orchestrator import get_orchestrator

            # Run async function synchronously
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                orchestrator = get_orchestrator()
                snapshot = loop.run_until_complete(orchestrator.get_market_snapshot())
                lock_context = loop.run_until_complete(orchestrator.get_rate_lock_context())

                # Get recommendation for typical 30-day close
                recommendation = loop.run_until_complete(orchestrator.should_lock(30))
            finally:
                loop.close()

            return {
                "market_snapshot": {
                    "treasury_10yr": snapshot.get('treasury_yields', {}).get('10_year'),
                    "treasury_2yr": snapshot.get('treasury_yields', {}).get('2_year'),
                    "mortgage_30yr": snapshot.get('mortgage_rates', {}).get('mortgage_30yr'),
                    "mortgage_15yr": snapshot.get('mortgage_rates', {}).get('mortgage_15yr'),
                    "spread_2s10s": snapshot.get('spreads', {}).get('2s10s'),
                    "market_score": snapshot.get('market_score', 50),
                    "is_market_open": snapshot.get('market_status', {}).get('is_open'),
                    "timestamp": snapshot.get('market_status', {}).get('timestamp')
                },
                "volatility": {
                    "vix": snapshot.get('volatility', {}).get('vix'),
                    "score": snapshot.get('volatility', {}).get('volatility_score'),
                    "level": snapshot.get('volatility', {}).get('interpretation', 'normal')
                },
                "rate_trend": {
                    "direction": snapshot.get('rate_trend', {}).get('trend', 'stable'),
                    "change_7d": snapshot.get('rate_trend', {}).get('change', 0)
                },
                "recommendation": {
                    "action": recommendation.get('recommendation', 'unknown'),
                    "urgency": recommendation.get('urgency', 'moderate'),
                    "lock_score": recommendation.get('lock_score', 50),
                    "reasons": recommendation.get('reasons', [])
                },
                "guidance": CRMContextService._generate_rate_lock_guidance(
                    snapshot, lock_context, recommendation
                )
            }
        except Exception as e:
            logger.error(f"Error getting rate lock context: {e}")
            return {
                "market_snapshot": {},
                "volatility": {"score": 5, "level": "normal"},
                "rate_trend": {"direction": "stable", "change_7d": 0},
                "recommendation": {"action": "cautious_lock", "urgency": "moderate"},
                "guidance": "Rate lock data temporarily unavailable. Check market conditions before making lock decisions.",
                "error": "Internal server error"
            }

    @staticmethod
    def _generate_rate_lock_guidance(snapshot: Dict, context: Dict, recommendation: Dict) -> str:
        """Generate human-readable rate lock guidance"""
        action = recommendation.get('recommendation', 'cautious_lock')
        reasons = recommendation.get('reasons', [])
        vol_level = snapshot.get('volatility', {}).get('interpretation', 'normal')
        trend = snapshot.get('rate_trend', {}).get('trend', 'stable')
        mortgage_rate = snapshot.get('mortgage_rates', {}).get('mortgage_30yr', 0)

        # Build guidance text
        if action == 'lock_now':
            guidance = "🔒 LOCK NOW: Market conditions strongly favor locking today."
        elif action == 'cautious_lock':
            guidance = "🔒 LEAN LOCK: Consider locking, but watch for better entry points."
        elif action == 'cautious_float':
            guidance = "⏸️ LEAN FLOAT: Conditions favor floating, but stay alert to changes."
        else:  # float
            guidance = "🌊 FLOAT: Market conditions favor waiting for better rates."

        # Add rate info
        if mortgage_rate:
            guidance += f" Current 30yr rate: {mortgage_rate:.3f}%."

        # Add trend context
        if trend == 'rising':
            guidance += " Rates trending UP - lock sooner rather than later."
        elif trend == 'falling':
            guidance += " Rates trending DOWN - floating may capture improvement."

        # Add volatility context
        if vol_level in ['high', 'elevated']:
            guidance += " HIGH volatility - market unpredictable."
        elif vol_level == 'low':
            guidance += " Low volatility - stable conditions."

        # Add specific reasons
        if reasons:
            guidance += " Key factors: " + "; ".join(reasons[:3]) + "."

        return guidance

    @staticmethod
    def _get_pipeline_efficiency_context(db: Session, user_id: int) -> Dict[str, Any]:
        """Get comprehensive pipeline efficiency metrics for AI analysis"""
        try:
            # Stage performance analysis
            stage_metrics = []
            stages = [
                ('Lead Generation', 'leads', 'New'),
                ('Pre-Qualification', 'leads', 'Prospect'),
                ('Application', 'leads', 'Application Started'),
                ('Processing', 'loans', 'Processing'),
                ('Underwriting', 'loans', 'Underwriting'),
                ('Clear to Close', 'loans', 'CTC'),
                ('Closing', 'loans', 'Closing')
            ]

            for stage_name, table, stage_value in stages:
                try:
                    if table == 'leads':
                        result = db.execute(text(f"""
                            SELECT
                                COUNT(*) as count,
                                AVG(EXTRACT(DAY FROM (CURRENT_TIMESTAMP - created_at))) as avg_days
                            FROM leads
                            WHERE stage = :stage
                        """), {"stage": stage_value})
                    else:
                        result = db.execute(text(f"""
                            SELECT
                                COUNT(*) as count,
                                AVG(days_in_stage) as avg_days
                            FROM loans
                            WHERE stage = :stage
                        """), {"stage": stage_value})

                    row = result.fetchone()
                    count = row[0] or 0
                    avg_days = float(row[1]) if row[1] else 0

                    # Calculate efficiency based on SLA targets
                    sla_targets = {
                        'Lead Generation': 2, 'Pre-Qualification': 5, 'Application': 7,
                        'Processing': 10, 'Underwriting': 5, 'Clear to Close': 3, 'Closing': 2
                    }
                    target = sla_targets.get(stage_name, 7)
                    efficiency = max(0, min(100, 100 - ((avg_days - target) / target * 50))) if avg_days > 0 else 85

                    stage_metrics.append({
                        "stage": stage_name,
                        "count": count,
                        "avg_days": round(avg_days, 1),
                        "sla_target_days": target,
                        "efficiency": round(efficiency, 1),
                        "is_bottleneck": avg_days > target * 1.5 and count > 2
                    })
                except Exception as e:
                    logger.debug(f"Could not get metrics for {stage_name}: {e}")
                    stage_metrics.append({
                        "stage": stage_name, "count": 0, "avg_days": 0,
                        "sla_target_days": 7, "efficiency": 85, "is_bottleneck": False
                    })

            # Employee performance by role with efficiency scores
            employee_performance = {
                "loan_officers": [],
                "processors": [],
                "underwriters": [],
                "closers": []
            }

            try:
                # Get team members with their loan performance
                result = db.execute(text("""
                    SELECT
                        tmp.id, tmp.name, tmp.role, tmp.email,
                        tmp.loans_processed, tmp.avg_close_time, tmp.satisfaction_score,
                        COUNT(DISTINCT l.id) as active_loans,
                        AVG(l.days_in_stage) as current_avg_days
                    FROM team_member_profiles tmp
                    LEFT JOIN loans l ON (
                        (tmp.role = 'processor' AND l.processor = tmp.name) OR
                        (tmp.role = 'underwriter' AND l.underwriter = tmp.name) OR
                        (tmp.role = 'closer' AND l.stage IN ('CTC', 'Closing'))
                    )
                    WHERE tmp.is_deleted = false AND tmp.status = 'active'
                    GROUP BY tmp.id, tmp.name, tmp.role, tmp.email,
                             tmp.loans_processed, tmp.avg_close_time, tmp.satisfaction_score
                    ORDER BY tmp.role, tmp.loans_processed DESC
                """))

                for row in result:
                    role = row[2] or 'processor'
                    loans_processed = row[4] or 0
                    avg_close = float(row[5]) if row[5] else 10.0
                    satisfaction = float(row[6]) if row[6] else 85.0
                    active_loans = row[7] or 0
                    current_avg = float(row[8]) if row[8] else 0

                    # Calculate efficiency score (0-100)
                    # Based on: volume (30%), speed (40%), satisfaction (30%)
                    volume_score = min(100, (loans_processed / 10) * 100)
                    speed_score = max(0, 100 - (avg_close - 7) * 10)
                    sat_score = satisfaction
                    efficiency = (volume_score * 0.3) + (speed_score * 0.4) + (sat_score * 0.3)

                    member = {
                        "id": str(row[0]),
                        "name": row[1],
                        "role": role,
                        "efficiency": round(efficiency, 1),
                        "loans_processed": loans_processed,
                        "avg_close_time": round(avg_close, 1),
                        "satisfaction_score": round(satisfaction, 1),
                        "active_loans": active_loans,
                        "current_avg_days": round(current_avg, 1),
                        "trend": round((efficiency - 75) / 75 * 100, 1)  # % above/below baseline
                    }

                    role_key = role + 's' if not role.endswith('s') else role
                    if role_key in employee_performance:
                        employee_performance[role_key].append(member)
                    elif role == 'processor':
                        employee_performance['processors'].append(member)
                    elif role == 'underwriter':
                        employee_performance['underwriters'].append(member)
                    elif role == 'closer':
                        employee_performance['closers'].append(member)

            except Exception as e:
                logger.debug(f"Could not get employee performance: {e}")

            # Identify bottlenecks
            bottlenecks = []

            # Stage bottlenecks
            for stage in stage_metrics:
                if stage["is_bottleneck"]:
                    bottlenecks.append({
                        "type": "stage",
                        "location": stage["stage"],
                        "severity": "high" if stage["avg_days"] > stage["sla_target_days"] * 2 else "medium",
                        "affected_count": stage["count"],
                        "avg_delay_days": round(stage["avg_days"] - stage["sla_target_days"], 1),
                        "recommendation": f"Review {stage['stage']} process - {stage['count']} items averaging {stage['avg_days']} days vs {stage['sla_target_days']} day target"
                    })

            # Employee bottlenecks (low efficiency workers with high volume)
            for role, members in employee_performance.items():
                for member in members:
                    if member["efficiency"] < 60 and member["active_loans"] > 2:
                        bottlenecks.append({
                            "type": "employee",
                            "location": f"{member['name']} ({role})",
                            "severity": "high" if member["efficiency"] < 50 else "medium",
                            "affected_count": member["active_loans"],
                            "efficiency": member["efficiency"],
                            "recommendation": f"{member['name']} has {member['efficiency']}% efficiency with {member['active_loans']} active loans. Consider workload redistribution or coaching."
                        })

            # Calculate overall pipeline health
            total_efficiency = sum(s["efficiency"] for s in stage_metrics) / len(stage_metrics) if stage_metrics else 75
            high_severity_bottlenecks = len([b for b in bottlenecks if b["severity"] == "high"])

            pipeline_health = "good" if total_efficiency >= 80 and high_severity_bottlenecks == 0 else \
                              "attention_needed" if total_efficiency >= 60 or high_severity_bottlenecks <= 2 else "critical"

            return {
                "overall_efficiency": round(total_efficiency, 1),
                "pipeline_health": pipeline_health,
                "stage_performance": stage_metrics,
                "employee_performance": employee_performance,
                "bottlenecks": bottlenecks,
                "bottleneck_count": len(bottlenecks),
                "high_severity_count": high_severity_bottlenecks,
                "recommendations": [b["recommendation"] for b in bottlenecks[:5]]
            }

        except Exception as e:
            logger.error(f"Error getting pipeline efficiency context: {e}")
            try:
                db.rollback()
            except Exception as e2:
                logger.exception(f"Failed to rollback after pipeline efficiency error: {e2}")
            return {
                "overall_efficiency": 75,
                "pipeline_health": "unknown",
                "stage_performance": [],
                "employee_performance": {},
                "bottlenecks": [],
                "bottleneck_count": 0,
                "recommendations": []
            }

    @staticmethod
    def _get_top_referral_borrowers(db: Session, user_id: int) -> Dict[str, Any]:
        """Get top borrowers by referral score"""
        try:
            # Get top 20 leads/borrowers by referral_source_score (all leads)
            result = db.execute(text("""
                SELECT
                    id,
                    name,
                    email,
                    phone,
                    stage,
                    loan_type,
                    preapproval_amount,
                    referral_source_score,
                    referral_source_rating,
                    employer_name,
                    job_title,
                    created_at
                FROM leads
                WHERE referral_source_score IS NOT NULL
                AND referral_source_score > 0
                ORDER BY referral_source_score DESC
                LIMIT 20
            """))

            borrowers = []
            for row in result:
                borrowers.append({
                    "id": row[0],
                    "name": row[1],
                    "email": row[2],
                    "phone": row[3],
                    "stage": row[4],
                    "loan_type": row[5],
                    "loan_amount": float(row[6]) if row[6] else 0,
                    "referral_score": row[7],
                    "referral_rating": row[8],
                    "employer": row[9],
                    "job_title": row[10],
                    "created_at": row[11].isoformat() if row[11] else None
                })

            # Categorize by score tiers
            strong = [b for b in borrowers if b["referral_score"] >= 80]
            good = [b for b in borrowers if 60 <= b["referral_score"] < 80]
            moderate = [b for b in borrowers if b["referral_score"] < 60]

            return {
                "total": len(borrowers),
                "borrowers": borrowers,
                "strong_referrers": len(strong),
                "good_referrers": len(good),
                "moderate_referrers": len(moderate),
                "top_5": borrowers[:5] if borrowers else []
            }
        except Exception as e:
            logger.error(f"Error getting top referral borrowers: {e}")
            try:
                db.rollback()
            except Exception as e2:
                logger.exception(f"Failed to rollback after top referral borrowers error: {e2}")
            return {
                "total": 0,
                "borrowers": [],
                "strong_referrers": 0,
                "good_referrers": 0,
                "moderate_referrers": 0,
                "top_5": []
            }

    @staticmethod
    def format_context_for_claude(context: Dict[str, Any]) -> str:
        """Format CRM context as text for Claude"""
        lines = []

        # Leads summary
        leads = context.get("leads", {})
        lines.append(f"LEADS: {leads.get('total', 0)} total")
        if leads.get("by_status"):
            for status, count in leads["by_status"].items():
                lines.append(f"  - {status}: {count}")

        # Detailed lead files
        lead_list = leads.get("recent_leads", [])
        if lead_list:
            lines.append("\n  LEAD DETAILS:")
            for lead in lead_list[:20]:  # Show top 20
                lines.append(f"\n  👤 {lead.get('name', 'Unknown')} - {lead.get('stage', 'N/A')}")
                lines.append(f"     Contact: {lead.get('email', 'N/A')} | {lead.get('phone', 'N/A')}")
                if lead.get('loan_amount') or lead.get('loan_amount_calc'):
                    amt = lead.get('loan_amount') or lead.get('loan_amount_calc', 0)
                    lines.append(f"     Loan: ${amt:,.0f} {lead.get('loan_type', '')} | Credit: {lead.get('credit_score', 'N/A')}")
                if lead.get('ltv') or lead.get('dti'):
                    lines.append(f"     LTV: {lead.get('ltv', 0):.1f}% | DTI: {lead.get('dti', 0):.1f}%")
                if lead.get('employer') or lead.get('job_title'):
                    lines.append(f"     Employment: {lead.get('job_title', '')} at {lead.get('employer', 'N/A')}")
                if lead.get('processor') or lead.get('underwriter'):
                    lines.append(f"     Processor: {lead.get('processor', 'Unassigned')} | UW: {lead.get('underwriter', 'Unassigned')}")
                if lead.get('property_address') and lead.get('property_address').strip(', '):
                    lines.append(f"     Property: {lead.get('property_address')}")
                if lead.get('referral_score'):
                    lines.append(f"     Referral Score: {lead.get('referral_score')}/100 ({lead.get('referral_rating', '')})")
                if lead.get('closing_date'):
                    lines.append(f"     Target Close: {lead.get('closing_date')}")

        # Loans summary
        loans = context.get("loans", {})
        lines.append(f"\nLOANS/DEALS: {loans.get('total', 0)} total, ${loans.get('total_volume', 0):,.0f} volume")
        if loans.get("by_stage"):
            for stage, count in loans["by_stage"].items():
                lines.append(f"  - {stage}: {count}")

        # Detailed loan files
        loan_list = loans.get("recent_loans", [])
        if loan_list:
            lines.append("\n  ACTIVE LOAN FILES:")
            for loan in loan_list:
                if loan.get("stage") not in ["Funded", "Closed"]:
                    lines.append(f"\n  📁 {loan.get('loan_number', 'N/A')} - {loan.get('borrower_name', 'Unknown')}")
                    lines.append(f"     Stage: {loan.get('stage')} | {loan.get('program', loan.get('loan_type', 'N/A'))}")
                    lines.append(f"     Amount: ${loan.get('loan_amount', 0):,.0f} | Rate: {loan.get('interest_rate', 0)}% | LTV: {loan.get('ltv', 0)}%")
                    if loan.get('processor') or loan.get('underwriter'):
                        lines.append(f"     Processor: {loan.get('processor', 'Unassigned')} | UW: {loan.get('underwriter', 'Unassigned')}")
                    if loan.get('closing_date'):
                        lines.append(f"     Closing: {loan.get('closing_date')} | Days in stage: {loan.get('days_in_stage', 0)}")
                    if loan.get('sla_status') and loan.get('sla_status') != 'on-track':
                        lines.append(f"     ⚠️ SLA Status: {loan.get('sla_status')}")
                    if loan.get('realtor'):
                        lines.append(f"     Realtor: {loan.get('realtor')} | Title: {loan.get('title_company', 'N/A')}")

        # Tasks summary
        tasks = context.get("tasks", {})
        lines.append(f"\nTASKS: {tasks.get('total', 0)} total, {tasks.get('overdue', 0)} overdue")
        lines.append(f"  - Today: {len(tasks.get('todays_tasks', []))} tasks")

        # MUM clients (portfolio) with calculated LTV
        mum = context.get("mum_clients", {})
        lines.append(f"\nMORTGAGES UNDER MANAGEMENT (PORTFOLIO): {mum.get('total', 0)} clients")

        # Detailed portfolio client information with amortization
        mum_list = mum.get("recent_clients", [])
        if mum_list:
            lines.append("\n  PORTFOLIO CLIENT DETAILS:")
            for client in mum_list[:15]:  # Show top 15
                lines.append(f"\n  🏠 {client.get('name', 'Unknown')}")
                lines.append(f"     Contact: {client.get('email', 'N/A')} | {client.get('phone', 'N/A')}")

                # Original loan info
                orig_loan = client.get('original_loan_amount', 0)
                rate = client.get('interest_rate', 0)
                term = client.get('loan_term_years', 30)
                lines.append(f"     Original: ${orig_loan:,.0f} at {rate}% ({term}-year {client.get('loan_type', 'N/A')})")

                # Current balance from amortization
                curr_bal = client.get('current_balance', 0)
                payments = client.get('payments_made', 0)
                if payments > 0:
                    lines.append(f"     Current Balance: ${curr_bal:,.0f} after {payments} payments")

                # Property value and equity
                orig_prop = client.get('original_property_value', 0)
                curr_prop = client.get('current_property_value', 0)
                equity = client.get('current_equity', 0)
                equity_pct = client.get('equity_percent', 0)
                if curr_prop > 0:
                    lines.append(f"     Property: ${orig_prop:,.0f} → ${curr_prop:,.0f} (current)")
                    lines.append(f"     Equity: ${equity:,.0f} ({equity_pct:.1f}%)")

                # Current LTV
                ltv = client.get('current_ltv', 0)
                if ltv > 0:
                    lines.append(f"     Current LTV: {ltv:.1f}%")

                # Engagement and next action
                engagement = client.get('engagement_score', 0)
                next_touch = client.get('next_touchpoint', '')
                if engagement or next_touch:
                    lines.append(f"     Engagement: {engagement}/100 | Next: {next_touch}")

        # Pipeline
        pipeline = context.get("pipeline", {})
        closing = pipeline.get("closing_this_month", {})
        lines.append(f"\nPIPELINE: {closing.get('count', 0)} closing this month (${closing.get('volume', 0):,.0f})")

        # Referral partners with performance metrics
        partners = context.get("referral_partners", {})
        lines.append(f"\nREFERRAL PARTNERS: {partners.get('total', 0)}")

        # Show most profitable partner prominently
        most_profitable = partners.get("most_profitable")
        if most_profitable:
            lines.append(f"  MOST PROFITABLE: {most_profitable['name']} - ${most_profitable['revenue']:,.0f} from {most_profitable['deals']} closed deals")

        # Show top partners with metrics
        partner_list = partners.get("partners", [])
        if partner_list:
            lines.append("  Top Partners by Revenue:")
            for p in partner_list[:5]:
                if p["total_revenue"] > 0:
                    lines.append(f"    - {p['name']}: ${p['total_revenue']:,.0f} revenue, {p['closed_deals']} deals, {p['close_rate_pct']:.0f}% close rate")

        # Loan Officer Performance (for business impact analysis)
        lo_perf = context.get("loan_officer_performance", {})
        if lo_perf.get("total_loan_officers", 0) > 0:
            lines.append(f"\nLOAN OFFICER PERFORMANCE: {lo_perf['total_loan_officers']} LOs")
            lines.append(f"  Team Total: ${lo_perf.get('total_team_volume', 0):,.0f} volume | ${lo_perf.get('total_team_revenue', 0):,.0f} revenue (12 months)")

            # Team averages
            avgs = lo_perf.get("team_averages", {})
            if avgs:
                lines.append(f"\n  TEAM AVERAGES:")
                lines.append(f"    Volume: ${avgs.get('avg_volume_12m', 0):,.0f}/LO | Units: {avgs.get('avg_units_12m', 0):.1f}/LO")
                lines.append(f"    Conversion: {avgs.get('avg_conversion_rate', 0):.1f}% | Efficiency: {avgs.get('avg_efficiency_score', 0):.2f} units/month")
                lines.append(f"    Avg Days to Close: {avgs.get('avg_days_to_close', 0):.0f} days")

            # All LO rankings
            los = lo_perf.get("loan_officers", [])
            if los:
                lines.append(f"\n  LO RANKINGS BY VOLUME:")
                for i, lo in enumerate(los[:10], 1):  # Top 10
                    efficiency_flag = "⚠️" if lo['efficiency_score'] < avgs.get('avg_efficiency_score', 0) * 0.8 else ""
                    lines.append(f"    {i}. {lo['name']}: ${lo['volume_closed_12m']:,.0f} | {lo['units_closed_12m']} units | {lo['efficiency_score']:.2f} eff {efficiency_flag}")
                    lines.append(f"       Revenue: ${lo['revenue_12m']:,.0f} | Pipeline: ${lo['active_pipeline_volume']:,.0f} ({lo['active_pipeline_count']} loans)")
                    lines.append(f"       Conversion: {lo['conversion_rate']:.1f}% | Avg Close: {lo['avg_days_to_close']:.0f} days")

            # High volume / low efficiency alert
            high_vol_low_eff = lo_perf.get("high_volume_low_efficiency", [])
            if high_vol_low_eff:
                lines.append(f"\n  ⚠️ HIGH VOLUME / LOW EFFICIENCY LOs ({len(high_vol_low_eff)}):")
                for lo in high_vol_low_eff:
                    lines.append(f"\n    🚨 {lo['name']}")
                    lines.append(f"       Production: ${lo['volume_12m']:,.0f} | ${lo['revenue_12m']:,.0f} revenue")
                    lines.append(f"       Efficiency: {lo['efficiency_score']:.2f} ({lo['efficiency_gap']:.1f}% below average)")
                    lines.append(f"       Conversion: {lo['conversion_rate']:.1f}% | Avg Close: {lo['avg_days_to_close']:.0f} days")

                    impact = lo.get('business_impact', {})
                    lines.append(f"\n       BUSINESS IMPACT IF TERMINATED:")
                    lines.append(f"         Annual Revenue Loss: ${impact.get('immediate_revenue_loss', 0):,.0f}")
                    lines.append(f"         Pipeline at Risk: ${impact.get('pipeline_at_risk', 0):,.0f}")
                    lines.append(f"         Total Potential Loss: ${impact.get('total_potential_loss', 0):,.0f}")
                    lines.append(f"         Replacement Cost (6 months): ${impact.get('replacement_cost', 0):,.0f}")
                    lines.append(f"         Market Share Impact: {impact.get('market_share_impact', 0):.1f}% of team volume")

        # Team performance summary
        team = context.get("team_performance", {})
        lines.append(f"\nTEAM PERFORMANCE (Operations): {team.get('total_team_members', 0)} team members")

        # Processors
        processors = team.get("processors", {})
        if processors.get("count", 0) > 0:
            lines.append(f"\n  PROCESSORS ({processors['count']}):")
            if processors.get("avg_loans_processed"):
                lines.append(f"    Avg loans processed: {processors['avg_loans_processed']:.0f}")
            if processors.get("avg_close_time"):
                lines.append(f"    Avg turn time: {processors['avg_close_time']:.1f} days")
            for m in processors.get("members", [])[:5]:
                lines.append(f"    - {m['name']}: {m['loans_processed']} loans, {m['avg_close_time'] or 'N/A'} days avg")

        # Underwriters
        underwriters = team.get("underwriters", {})
        if underwriters.get("count", 0) > 0:
            lines.append(f"\n  UNDERWRITERS ({underwriters['count']}):")
            if underwriters.get("avg_loans_processed"):
                lines.append(f"    Avg loans processed: {underwriters['avg_loans_processed']:.0f}")
            if underwriters.get("avg_close_time"):
                lines.append(f"    Avg turn time: {underwriters['avg_close_time']:.1f} days")
            for m in underwriters.get("members", [])[:5]:
                lines.append(f"    - {m['name']}: {m['loans_processed']} loans, {m['avg_close_time'] or 'N/A'} days avg")

        # Closers
        closers = team.get("closers", {})
        if closers.get("count", 0) > 0:
            lines.append(f"\n  CLOSERS ({closers['count']}):")
            for m in closers.get("members", [])[:5]:
                lines.append(f"    - {m['name']}: {m['loans_processed']} loans")

        # Underperformers alert
        all_underperformers = team.get("all_underperformers", [])
        if all_underperformers:
            lines.append(f"\n  ⚠️ UNDERPERFORMERS ({len(all_underperformers)}):")
            for up in all_underperformers:
                issues_str = ", ".join(up['issues'])
                lines.append(f"    - {up['name']} ({up['role']}): {issues_str}")

        # Top referral scoring borrowers
        referrals = context.get("top_referral_borrowers", {})
        if referrals.get("total", 0) > 0:
            lines.append(f"\nTOP REFERRAL SCORING BORROWERS: {referrals['total']} ranked")
            lines.append(f"  Strong Referrers (80+): {referrals.get('strong_referrers', 0)}")
            lines.append(f"  Good Referrers (60-79): {referrals.get('good_referrers', 0)}")
            lines.append(f"  Moderate (below 60): {referrals.get('moderate_referrers', 0)}")

            # Top 20 borrowers by referral score
            borrowers = referrals.get("borrowers", [])
            if borrowers:
                lines.append("\n  Top 20 by Referral Score:")
                for i, b in enumerate(borrowers, 1):
                    employer_info = f" at {b['employer']}" if b.get('employer') else ""
                    job_info = f" ({b['job_title']})" if b.get('job_title') else ""
                    lines.append(f"    {i}. {b['name']} - Score: {b['referral_score']}/100{employer_info}{job_info}")
                    if b.get('referral_rating'):
                        lines.append(f"       Rating: {b['referral_rating']}, Stage: {b['stage']}")

        # Pipeline Efficiency Analysis
        efficiency = context.get("pipeline_efficiency", {})
        if efficiency:
            lines.append(f"\n\n=== PIPELINE EFFICIENCY ANALYSIS ===")
            lines.append(f"Overall Efficiency: {efficiency.get('overall_efficiency', 0)}%")
            lines.append(f"Pipeline Health: {efficiency.get('pipeline_health', 'unknown').upper()}")
            lines.append(f"Active Bottlenecks: {efficiency.get('bottleneck_count', 0)} ({efficiency.get('high_severity_count', 0)} high severity)")

            # Stage performance
            stage_perf = efficiency.get("stage_performance", [])
            if stage_perf:
                lines.append(f"\n  STAGE PERFORMANCE:")
                for stage in stage_perf:
                    status = "🔴 BOTTLENECK" if stage.get("is_bottleneck") else "✅" if stage.get("efficiency", 0) >= 80 else "🟡"
                    lines.append(f"    {status} {stage['stage']}: {stage['efficiency']}% efficiency | {stage['count']} items | {stage['avg_days']} days avg (target: {stage['sla_target_days']})")

            # Employee performance by role
            emp_perf = efficiency.get("employee_performance", {})

            # Processors
            processors = emp_perf.get("processors", [])
            if processors:
                lines.append(f"\n  PROCESSOR EFFICIENCY:")
                for p in processors:
                    status = "🔴" if p['efficiency'] < 60 else "🟡" if p['efficiency'] < 80 else "✅"
                    lines.append(f"    {status} {p['name']}: {p['efficiency']}% | {p['active_loans']} active loans | {p['avg_close_time']} days avg | trend: {p['trend']:+.1f}%")

            # Underwriters
            underwriters = emp_perf.get("underwriters", [])
            if underwriters:
                lines.append(f"\n  UNDERWRITER EFFICIENCY:")
                for u in underwriters:
                    status = "🔴" if u['efficiency'] < 60 else "🟡" if u['efficiency'] < 80 else "✅"
                    lines.append(f"    {status} {u['name']}: {u['efficiency']}% | {u['active_loans']} active loans | {u['avg_close_time']} days avg | trend: {u['trend']:+.1f}%")

            # Closers
            closers = emp_perf.get("closers", [])
            if closers:
                lines.append(f"\n  CLOSER EFFICIENCY:")
                for c in closers:
                    status = "🔴" if c['efficiency'] < 60 else "🟡" if c['efficiency'] < 80 else "✅"
                    lines.append(f"    {status} {c['name']}: {c['efficiency']}% | {c['active_loans']} active loans | trend: {c['trend']:+.1f}%")

            # Bottlenecks
            bottlenecks = efficiency.get("bottlenecks", [])
            if bottlenecks:
                lines.append(f"\n  🚨 ACTIVE BOTTLENECKS:")
                for b in bottlenecks:
                    severity_icon = "🔴" if b['severity'] == 'high' else "🟡"
                    lines.append(f"    {severity_icon} [{b['type'].upper()}] {b['location']}")
                    lines.append(f"       Affected: {b['affected_count']} items | Severity: {b['severity']}")
                    lines.append(f"       Recommendation: {b['recommendation']}")

            # Top recommendations
            recs = efficiency.get("recommendations", [])
            if recs:
                lines.append(f"\n  💡 TOP RECOMMENDATIONS:")
                for i, rec in enumerate(recs[:5], 1):
                    lines.append(f"    {i}. {rec}")

        # Rate Lock Intelligence
        rate_lock = context.get("rate_lock_intelligence", {})
        if rate_lock:
            lines.append(f"\nRATE LOCK INTELLIGENCE:")

            # Today's guidance
            guidance = rate_lock.get("guidance", "")
            if guidance:
                lines.append(f"  {guidance}")

            # Market snapshot
            market = rate_lock.get("market_snapshot", {})
            if market.get("mortgage_30yr"):
                lines.append(f"\n  CURRENT RATES:")
                lines.append(f"    30yr Mortgage: {market.get('mortgage_30yr', 0):.3f}%")
                if market.get("mortgage_15yr"):
                    lines.append(f"    15yr Mortgage: {market.get('mortgage_15yr', 0):.3f}%")
                if market.get("treasury_10yr"):
                    lines.append(f"    10yr Treasury: {market.get('treasury_10yr', 0):.3f}%")

            # Volatility and trend
            vol = rate_lock.get("volatility", {})
            trend = rate_lock.get("rate_trend", {})
            if vol.get("vix") or trend.get("direction"):
                lines.append(f"\n  MARKET CONDITIONS:")
                if vol.get("vix"):
                    lines.append(f"    VIX: {vol.get('vix')} ({vol.get('level', 'normal')} volatility)")
                if trend.get("direction"):
                    change = trend.get('change_7d', 0)
                    direction = "↑" if change > 0 else "↓" if change < 0 else "→"
                    lines.append(f"    7-Day Trend: {trend.get('direction')} {direction} ({change:+.2f}%)")

            # Recommendation details
            rec = rate_lock.get("recommendation", {})
            if rec.get("action"):
                lines.append(f"\n  RECOMMENDATION: {rec.get('action', '').upper().replace('_', ' ')}")
                lines.append(f"    Lock Score: {rec.get('lock_score', 50)}/100 | Urgency: {rec.get('urgency', 'moderate')}")
                reasons = rec.get("reasons", [])
                if reasons:
                    lines.append("    Factors:")
                    for reason in reasons:
                        lines.append(f"      - {reason}")

        return "\n".join(lines)

    @staticmethod
    def get_schema_context() -> Dict[str, Any]:
        """Get database schema information for AI"""
        return {
            "tables": {
                "leads": {
                    "description": "Primary table for mortgage leads/opportunities",
                    "key_fields": {
                        "id": "Unique identifier",
                        "owner_id": "User who owns this lead",
                        "name": "Lead's full name",
                        "stage": "Current stage (New, Prospect, Application Started, Pre-Approved, Closed Won, Closed Lost)",
                        "loan_type": "FHA, VA, Conventional, USDA, Jumbo",
                        "preapproval_amount": "Requested loan amount in dollars",
                        "email": "Contact email",
                        "phone": "Contact phone",
                        "source": "Where lead came from (Website, Referral, etc.)",
                        "created_at": "When lead was created"
                    },
                    "valid_stages": ["New", "Prospect", "Application Started", "Pre-Approved", "Closed Won", "Closed Lost"],
                    "valid_loan_types": ["FHA", "VA", "Conventional", "USDA", "Jumbo", "Purchase", "Refinance"]
                },
                "loans": {
                    "description": "Active loans in pipeline",
                    "key_fields": {
                        "id": "Unique identifier",
                        "loan_officer_id": "Assigned loan officer",
                        "borrower_name": "Borrower's name",
                        "amount": "Loan amount",
                        "stage": "Pipeline stage (Processing, UW Received, Approved, CTC, Funded)",
                        "loan_type": "Loan program type",
                        "rate": "Interest rate",
                        "closing_date": "Expected closing date",
                        "property_address": "Property address"
                    },
                    "valid_stages": ["Processing", "UW Received", "Approved", "CTC", "Funded", "Closed"]
                },
                "tasks": {
                    "description": "Action items and follow-ups",
                    "key_fields": {
                        "id": "Unique identifier",
                        "owner_id": "Assigned user",
                        "lead_id": "Associated lead (optional)",
                        "title": "Task description",
                        "due_date": "When task is due",
                        "status": "pending, in_progress, completed",
                        "priority": "high, medium, low"
                    }
                },
                "mum_clients": {
                    "description": "Mortgages Under Management - past clients for retention",
                    "key_fields": {
                        "id": "Unique identifier",
                        "user_id": "Loan officer ID",
                        "borrower_name": "Client name",
                        "loan_amount": "Current loan balance",
                        "interest_rate": "Current rate",
                        "loan_type": "Loan type",
                        "next_review_date": "Next scheduled review"
                    }
                },
                "referral_partners": {
                    "description": "Realtors, builders, and other referral sources",
                    "key_fields": {
                        "id": "Unique identifier",
                        "name": "Partner name",
                        "company": "Company name",
                        "total_referrals": "Number of referrals sent",
                        "total_volume": "Total loan volume referred"
                    }
                },
                "team_member_profiles": {
                    "description": "Internal team members (processors, underwriters, closers)",
                    "key_fields": {
                        "id": "Unique identifier",
                        "name": "Team member name",
                        "email": "Email address",
                        "role": "processor, underwriter, closer, loan_officer, admin",
                        "loans_processed": "Number of loans processed",
                        "avg_close_time": "Average days to close",
                        "satisfaction_score": "Customer satisfaction score",
                        "volume": "Total loan volume processed",
                        "status": "active, inactive, on_leave"
                    },
                    "valid_roles": ["processor", "underwriter", "closer", "loan_officer", "admin"]
                }
            }
        }

    @staticmethod
    def get_business_rules() -> Dict[str, Any]:
        """Get business rules and workflows for AI"""
        return {
            "lead_lifecycle": {
                "description": "How leads move through the pipeline",
                "stages": [
                    {
                        "name": "New",
                        "description": "Just entered system, not yet contacted",
                        "typical_duration_days": 1,
                        "required_actions": ["Initial contact within 24 hours"],
                        "next_stages": ["Prospect", "Closed Lost"]
                    },
                    {
                        "name": "Prospect",
                        "description": "Initial contact made, qualifying borrower",
                        "typical_duration_days": 7,
                        "required_actions": ["Gather financial info", "Pre-qualification call"],
                        "next_stages": ["Application Started", "Closed Lost"]
                    },
                    {
                        "name": "Application Started",
                        "description": "Borrower has begun loan application",
                        "typical_duration_days": 14,
                        "required_actions": ["Collect documents", "Submit to underwriting"],
                        "next_stages": ["Pre-Approved", "Closed Lost"]
                    },
                    {
                        "name": "Pre-Approved",
                        "description": "Borrower approved pending property and conditions",
                        "typical_duration_days": 30,
                        "required_actions": ["Find property", "Lock rate", "Complete conditions"],
                        "next_stages": ["Closed Won", "Closed Lost"]
                    }
                ],
                "status_rules": {
                    "New_to_Prospect": "After first successful contact",
                    "Prospect_to_Application_Started": "When application form submitted",
                    "Application_Started_to_Pre_Approved": "When pre-approval issued",
                    "Pre_Approved_to_Closed_Won": "When loan funds and closes",
                    "any_to_Closed_Lost": "When lead explicitly declines or unresponsive 30+ days"
                }
            },
            "loan_pipeline": {
                "description": "How loans move through processing",
                "stages": [
                    {"name": "Processing", "description": "Collecting and verifying documents"},
                    {"name": "UW Received", "description": "Submitted to underwriting"},
                    {"name": "Approved", "description": "Underwriting approved with conditions"},
                    {"name": "CTC", "description": "Clear to Close - all conditions satisfied"},
                    {"name": "Funded", "description": "Loan has funded"},
                    {"name": "Closed", "description": "Transaction complete"}
                ]
            },
            "task_rules": {
                "auto_create_tasks": {
                    "New_lead": "Create 'Initial contact' task due within 24 hours",
                    "Application_Started": "Create 'Collect documents' task due in 7 days",
                    "Pre_Approved": "Create 'Rate lock check' task due in 3 days"
                },
                "priority_rules": {
                    "overdue": "HIGH priority",
                    "due_today": "HIGH priority",
                    "high_value_lead": "HIGH if loan amount > $500k"
                }
            },
            "validation_rules": {
                "loan_amount": {"min": 50000, "max": 5000000},
                "credit_score": {"min": 300, "max": 850}
            }
        }

    @staticmethod
    def get_knowledge_base() -> Dict[str, Any]:
        """Get CRM knowledge base for AI"""
        return {
            "common_questions": [
                {
                    "question": "How do I move a lead to the next stage?",
                    "answer": "Update the lead's stage field to the appropriate value. Valid stages are: New, Prospect, Application Started, Pre-Approved, Closed Won, Closed Lost."
                },
                {
                    "question": "What is a stale lead?",
                    "answer": "A lead with no activity for 14+ days that isn't in a closed status. These need immediate follow-up."
                },
                {
                    "question": "How do I track my pipeline value?",
                    "answer": "Pipeline value is the sum of all loan amounts for loans not yet closed. View this in the dashboard or ask for a pipeline report."
                },
                {
                    "question": "What is MUM?",
                    "answer": "Mortgages Under Management - these are past clients whose loans you originated. Important for retention and refinance opportunities."
                }
            ],
            "business_glossary": {
                "DTI": "Debt-to-Income ratio - monthly debt payments divided by gross monthly income",
                "LTV": "Loan-to-Value ratio - loan amount divided by property value",
                "Underwriting": "Process of evaluating borrower creditworthiness and property value",
                "Clear to Close (CTC)": "Final approval stage before loan funding",
                "Rate Lock": "Guaranteeing an interest rate for a specific period",
                "Pre-Approval": "Conditional loan approval before finding a property",
                "Closing Disclosure": "Final loan terms document provided 3 days before closing"
            },
            "workflow_examples": [
                {
                    "scenario": "New lead from website",
                    "steps": [
                        "1. Lead created with stage=New",
                        "2. Contact within 24 hours",
                        "3. After qualification, update to Prospect",
                        "4. When application submitted, update to Application Started",
                        "5. After pre-approval issued, update to Pre-Approved",
                        "6. When loan closes, update to Closed Won"
                    ]
                },
                {
                    "scenario": "Daily morning routine",
                    "steps": [
                        "1. Check overdue tasks",
                        "2. Review new leads needing contact",
                        "3. Check loans in pipeline for status updates",
                        "4. Follow up on stale prospects",
                        "5. Check rate lock expirations"
                    ]
                }
            ],
            "best_practices": [
                "Contact new leads within 24 hours - conversion rate drops 50% after that",
                "Always create follow-up tasks when changing lead status",
                "Check pipeline daily for loans approaching closing",
                "Review MUM clients quarterly for refinance opportunities",
                "Track referral partner performance monthly"
            ]
        }

    @staticmethod
    def format_complete_context_for_claude(context: Dict[str, Any]) -> str:
        """Format complete CRM context including schema, rules, and knowledge base"""
        lines = []

        # Basic context (existing)
        lines.append(CRMContextService.format_context_for_claude(context))

        # Add schema
        schema = CRMContextService.get_schema_context()
        lines.append("\n\n=== DATABASE SCHEMA ===")
        for table_name, table_info in schema["tables"].items():
            lines.append(f"\n{table_name.upper()}: {table_info['description']}")
            lines.append(f"  Key fields: {', '.join(table_info['key_fields'].keys())}")

        # Add business rules summary
        rules = CRMContextService.get_business_rules()
        lines.append("\n\n=== BUSINESS RULES ===")
        lines.append("Lead Stages: " + " → ".join([s["name"] for s in rules["lead_lifecycle"]["stages"]]))
        lines.append("Loan Pipeline: " + " → ".join([s["name"] for s in rules["loan_pipeline"]["stages"]]))

        # Add knowledge base highlights
        kb = CRMContextService.get_knowledge_base()
        lines.append("\n\n=== KEY TERMINOLOGY ===")
        for term, definition in list(kb["business_glossary"].items())[:5]:
            lines.append(f"- {term}: {definition}")

        lines.append("\n=== BEST PRACTICES ===")
        for practice in kb["best_practices"][:3]:
            lines.append(f"- {practice}")

        return "\n".join(lines)
