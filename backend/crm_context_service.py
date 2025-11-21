"""
CRM Context Service
Provides full CRM data context for AI assistant
"""

from sqlalchemy.orm import Session
from sqlalchemy import func, text
from datetime import datetime, timedelta
from typing import Dict, Any, List
import logging

logger = logging.getLogger(__name__)


class CRMContextService:
    """Fetches comprehensive CRM data for AI context"""

    @staticmethod
    def get_full_crm_context(db: Session, user_id: int) -> Dict[str, Any]:
        """Get complete CRM data context for AI"""
        try:
            context = {
                "leads": CRMContextService._get_leads_context(db, user_id),
                "loans": CRMContextService._get_loans_context(db, user_id),
                "tasks": CRMContextService._get_tasks_context(db, user_id),
                "mum_clients": CRMContextService._get_mum_context(db, user_id),
                "pipeline": CRMContextService._get_pipeline_stats(db, user_id),
                "activities": CRMContextService._get_recent_activities(db, user_id),
                "referral_partners": CRMContextService._get_referral_partners(db, user_id),
            }
            return context
        except Exception as e:
            logger.error(f"Error getting CRM context: {e}")
            return {}

    @staticmethod
    def _get_leads_context(db: Session, user_id: int) -> Dict[str, Any]:
        """Get leads summary and details"""
        try:
            # Get lead counts by stage
            result = db.execute(text("""
                SELECT stage, COUNT(*) as count
                FROM leads
                WHERE owner_id = :user_id
                GROUP BY stage
            """), {"user_id": user_id})
            status_counts = {str(row[0]): row[1] for row in result}

            # Get total leads
            total = sum(status_counts.values())

            # Get recent leads (last 30 days)
            result = db.execute(text("""
                SELECT id, name, '', email, phone, stage,
                       loan_type, preapproval_amount, source, created_at
                FROM leads
                WHERE owner_id = :user_id
                ORDER BY created_at DESC
                LIMIT 50
            """), {"user_id": user_id})

            leads = []
            for row in result:
                leads.append({
                    "id": row[0],
                    "name": f"{row[1]} {row[2]}",
                    "email": row[3],
                    "phone": row[4],
                    "status": row[5],
                    "loan_type": row[6],
                    "loan_amount": float(row[7]) if row[7] else 0,
                    "source": row[8],
                    "created_at": row[9].isoformat() if row[9] else None
                })

            return {
                "total": total,
                "by_status": status_counts,
                "recent_leads": leads
            }
        except Exception as e:
            logger.error(f"Error getting leads context: {e}")
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

            # Get recent loans
            result = db.execute(text("""
                SELECT id, borrower_name, amount, loan_type, stage,
                       property_address, rate, closing_date, created_at
                FROM loans
                WHERE loan_officer_id = :user_id
                ORDER BY created_at DESC
                LIMIT 50
            """), {"user_id": user_id})

            loans = []
            for row in result:
                loans.append({
                    "id": row[0],
                    "borrower_name": row[1],
                    "loan_amount": float(row[2]) if row[2] else 0,
                    "loan_type": row[3],
                    "stage": row[4],
                    "property_address": row[5],
                    "interest_rate": float(row[6]) if row[6] else 0,
                    "estimated_close_date": row[7].isoformat() if row[7] else None,
                    "created_at": row[8].isoformat() if row[8] else None
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

            # Get today's tasks
            result = db.execute(text("""
                SELECT id, title, description, priority, due_date, status, lead_id
                FROM tasks
                WHERE owner_id = :user_id
                AND DATE(due_date) = :today
                ORDER BY priority DESC, due_date ASC
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

            return {
                "total": sum(status_counts.values()),
                "by_status": status_counts,
                "overdue": overdue,
                "todays_tasks": todays_tasks,
                "upcoming": upcoming
            }
        except Exception as e:
            logger.error(f"Error getting tasks context: {e}")
            return {"total": 0, "by_status": {}, "overdue": 0, "todays_tasks": [], "upcoming": []}

    @staticmethod
    def _get_mum_context(db: Session, user_id: int) -> Dict[str, Any]:
        """Get Mortgages Under Management clients"""
        try:
            result = db.execute(text("""
                SELECT id, first_name, last_name, email, phone,
                       current_loan_amount, interest_rate, loan_type,
                       next_review_date, last_contact_date
                FROM mum_clients
                WHERE user_id = :user_id
                ORDER BY next_review_date ASC
                LIMIT 50
            """), {"user_id": user_id})

            clients = []
            for row in result:
                clients.append({
                    "id": row[0],
                    "name": f"{row[1]} {row[2]}",
                    "email": row[3],
                    "phone": row[4],
                    "loan_amount": float(row[5]) if row[5] else 0,
                    "interest_rate": float(row[6]) if row[6] else 0,
                    "loan_type": row[7],
                    "next_review_date": row[8].isoformat() if row[8] else None,
                    "last_contact_date": row[9].isoformat() if row[9] else None
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

            # Get conversion rates
            result = db.execute(text("""
                SELECT
                    COUNT(*) FILTER (WHERE stage = 'pre-approved') as pre_approved,
                    COUNT(*) FILTER (WHERE stage = 'application') as applications,
                    COUNT(*) FILTER (WHERE stage = 'closed') as closed
                FROM leads
                WHERE owner_id = :user_id
            """), {"user_id": user_id})
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
        """Get referral partners"""
        try:
            result = db.execute(text("""
                SELECT id, name, company, email, phone, total_referrals, total_volume
                FROM referral_partners
                WHERE user_id = :user_id
                ORDER BY total_volume DESC
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
                    "total_referrals": row[5] or 0,
                    "total_volume": float(row[6]) if row[6] else 0
                })

            return {
                "total": len(partners),
                "partners": partners
            }
        except Exception as e:
            logger.error(f"Error getting referral partners: {e}")
            return {"total": 0, "partners": []}

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

        # Loans summary
        loans = context.get("loans", {})
        lines.append(f"\nLOANS/DEALS: {loans.get('total', 0)} total, ${loans.get('total_volume', 0):,.0f} volume")
        if loans.get("by_stage"):
            for stage, count in loans["by_stage"].items():
                lines.append(f"  - {stage}: {count}")

        # Tasks summary
        tasks = context.get("tasks", {})
        lines.append(f"\nTASKS: {tasks.get('total', 0)} total, {tasks.get('overdue', 0)} overdue")
        lines.append(f"  - Today: {len(tasks.get('todays_tasks', []))} tasks")

        # MUM clients
        mum = context.get("mum_clients", {})
        lines.append(f"\nMORTGAGES UNDER MANAGEMENT: {mum.get('total', 0)} clients")

        # Pipeline
        pipeline = context.get("pipeline", {})
        closing = pipeline.get("closing_this_month", {})
        lines.append(f"\nPIPELINE: {closing.get('count', 0)} closing this month (${closing.get('volume', 0):,.0f})")

        # Referral partners
        partners = context.get("referral_partners", {})
        lines.append(f"\nREFERRAL PARTNERS: {partners.get('total', 0)}")

        return "\n".join(lines)
