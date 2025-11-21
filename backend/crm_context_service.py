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
        # Clear any previous failed transaction state
        try:
            db.rollback()
        except:
            pass

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
            try:
                db.rollback()
            except:
                pass
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
            try:
                db.rollback()
            except:
                pass
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
            except:
                pass
            return {"total": 0, "partners": [], "most_profitable": None}

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
