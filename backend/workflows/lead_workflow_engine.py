"""
Lead Workflow Automation Engine - Pipeline 360
TL Development, LLC

Automatically processes lead status changes and triggers:
- Email/SMS communications
- Task creation for LOs
- Drip campaign activation
- Activity logging
- Time-based automation rules
"""

from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text
import json
import logging

logger = logging.getLogger(__name__)

# Lead stage definitions matching main.py
LEAD_STAGES = [
    "New",
    "Attempted Contact",
    "Prospect",
    "Application Started",
    "Application Complete",
    "Pre-Approved"
]

# Time-based rules (in hours)
TIME_RULES = {
    "new_no_contact": 1,           # Alert if New lead not contacted in 1 hour
    "new_escalate": 4,             # Escalate if no contact in 4 hours
    "attempted_reengagement": 72,  # Re-engagement after 3 days no response
    "prospect_stalled": 336,       # 14 days in Prospect with no progression
    "application_incomplete": 48,  # Reminder if application incomplete for 48 hours
    "preapproval_expiring": 720,   # 30 days before pre-approval expiration
}


class LeadStatusChange(BaseModel):
    lead_id: int
    lead_name: str
    lead_email: Optional[str] = None
    lead_phone: Optional[str] = None
    old_status: str
    new_status: str
    loan_officer_id: int
    loan_officer_name: str
    loan_officer_email: Optional[str] = None
    loan_type: Optional[str] = None
    loan_amount: Optional[float] = None
    changed_at: datetime = None

    class Config:
        from_attributes = True


class WorkflowAction(BaseModel):
    action_type: str  # email, sms, task, tag, drip, alert
    target: str  # lead, loan_officer, manager
    template: Optional[str] = None
    data: Dict[str, Any] = {}
    priority: str = "normal"
    scheduled_for: Optional[datetime] = None


class LeadWorkflowEngine:
    """Main workflow engine for lead status automation"""

    def __init__(self, db: Session):
        self.db = db

    async def process_status_change(self, status_change: LeadStatusChange) -> Dict[str, Any]:
        """Process all workflows when a lead status changes"""
        results = []

        old = status_change.old_status
        new = status_change.new_status

        logger.info(f"Processing status change: {old} → {new} for lead {status_change.lead_id}")

        # ================================================================
        # TRANSITION: Any → NEW (Lead just entered system)
        # ================================================================
        if new == "New" and old != "New":
            results.extend(await self._handle_new_lead(status_change))

        # ================================================================
        # TRANSITION: NEW → ATTEMPTED CONTACT
        # ================================================================
        elif old == "New" and new == "Attempted Contact":
            results.extend(await self._handle_new_to_attempted(status_change))

        # ================================================================
        # TRANSITION: ATTEMPTED CONTACT → PROSPECT
        # ================================================================
        elif old == "Attempted Contact" and new == "Prospect":
            results.extend(await self._handle_attempted_to_prospect(status_change))

        # ================================================================
        # TRANSITION: PROSPECT → APPLICATION STARTED
        # ================================================================
        elif old == "Prospect" and new == "Application Started":
            results.extend(await self._handle_prospect_to_application(status_change))

        # ================================================================
        # TRANSITION: APPLICATION STARTED → APPLICATION COMPLETE
        # ================================================================
        elif old == "Application Started" and new == "Application Complete":
            results.extend(await self._handle_application_complete(status_change))

        # ================================================================
        # TRANSITION: APPLICATION COMPLETE → PRE-APPROVED
        # ================================================================
        elif old == "Application Complete" and new == "Pre-Approved":
            results.extend(await self._handle_pre_approved(status_change))

        # ================================================================
        # Log workflow execution
        # ================================================================
        await self._log_execution(status_change, results)

        return {
            "success": True,
            "lead_id": status_change.lead_id,
            "transition": f"{old} → {new}",
            "actions": results,
            "action_count": len(results)
        }

    async def _handle_new_lead(self, sc: LeadStatusChange) -> List[Dict]:
        """Handle brand new lead entering the system"""
        actions = []
        first_name = sc.lead_name.split()[0] if sc.lead_name else "there"

        # 1. Send welcome SMS to lead
        if sc.lead_phone:
            actions.append({
                "action_type": "sms",
                "target": "lead",
                "template": "welcome_new_lead",
                "data": {
                    "to": sc.lead_phone,
                    "message": f"Hi {first_name}! Thanks for reaching out about your mortgage needs. {sc.loan_officer_name} will contact you within 1 hour. Reply STOP to opt out."
                },
                "priority": "high"
            })

        # 2. Send welcome email to lead
        if sc.lead_email:
            actions.append({
                "action_type": "email",
                "target": "lead",
                "template": "welcome_new_lead",
                "data": {
                    "to": sc.lead_email,
                    "subject": f"Welcome to Pipeline 360 - {sc.loan_officer_name} Will Be In Touch",
                    "lead_name": sc.lead_name,
                    "loan_officer_name": sc.loan_officer_name
                },
                "priority": "high"
            })

        # 3. Alert loan officer
        actions.append({
            "action_type": "alert",
            "target": "loan_officer",
            "template": "new_lead_assigned",
            "data": {
                "loan_officer_id": sc.loan_officer_id,
                "message": f"🔔 NEW LEAD: {sc.lead_name} - Contact within 1 hour",
                "lead_id": sc.lead_id
            },
            "priority": "urgent"
        })

        # 4. Create initial contact task
        actions.append({
            "action_type": "task",
            "target": "loan_officer",
            "template": "initial_contact",
            "data": {
                "title": f"Initial contact with {first_name}",
                "description": f"Make first contact attempt with {sc.lead_name}. Lead received at {sc.changed_at.strftime('%I:%M %p') if sc.changed_at else 'now'}.",
                "due_hours": 1,
                "priority": "high",
                "lead_id": sc.lead_id,
                "assigned_to": sc.loan_officer_id
            },
            "priority": "high"
        })

        # 5. Start new lead drip campaign
        actions.append({
            "action_type": "drip",
            "target": "lead",
            "template": "new_lead_nurture",
            "data": {
                "lead_id": sc.lead_id,
                "campaign": "new_lead_nurture",
                "start_immediately": True
            },
            "priority": "normal"
        })

        logger.info(f"🆕 NEW LEAD workflow triggered: {len(actions)} actions for {sc.lead_name}")
        return actions

    async def _handle_new_to_attempted(self, sc: LeadStatusChange) -> List[Dict]:
        """Handle transition from New to Attempted Contact"""
        actions = []
        first_name = sc.lead_name.split()[0] if sc.lead_name else "there"

        # 1. Log contact attempt
        actions.append({
            "action_type": "activity",
            "target": "lead",
            "template": "contact_attempted",
            "data": {
                "lead_id": sc.lead_id,
                "activity_type": "status_change",
                "note": f"First contact attempt made by {sc.loan_officer_name}"
            }
        })

        # 2. Create follow-up task if no response
        actions.append({
            "action_type": "task",
            "target": "loan_officer",
            "template": "follow_up",
            "data": {
                "title": f"Follow-up attempt #{2} with {first_name}",
                "description": f"Second contact attempt. Try different channel (if called, try SMS/email).",
                "due_hours": 24,
                "priority": "medium",
                "lead_id": sc.lead_id,
                "assigned_to": sc.loan_officer_id
            }
        })

        # 3. Switch to attempted contact drip
        actions.append({
            "action_type": "drip",
            "target": "lead",
            "template": "attempted_contact_nurture",
            "data": {
                "lead_id": sc.lead_id,
                "campaign": "attempted_contact_nurture",
                "stop_campaign": "new_lead_nurture"
            }
        })

        logger.info(f"📞 NEW→ATTEMPTED workflow triggered: {len(actions)} actions for {sc.lead_name}")
        return actions

    async def _handle_attempted_to_prospect(self, sc: LeadStatusChange) -> List[Dict]:
        """Handle transition from Attempted Contact to Prospect"""
        actions = []
        first_name = sc.lead_name.split()[0] if sc.lead_name else "there"

        # 1. Celebration notification
        actions.append({
            "action_type": "alert",
            "target": "loan_officer",
            "template": "prospect_conversion",
            "data": {
                "loan_officer_id": sc.loan_officer_id,
                "message": f"🎉 {first_name} is now a Prospect! Keep the momentum going.",
                "lead_id": sc.lead_id
            },
            "priority": "normal"
        })

        # 2. Send "great connecting" email
        if sc.lead_email:
            actions.append({
                "action_type": "email",
                "target": "lead",
                "template": "great_connecting",
                "data": {
                    "to": sc.lead_email,
                    "subject": f"Great Connecting with You, {first_name}!",
                    "lead_name": sc.lead_name,
                    "loan_officer_name": sc.loan_officer_name,
                    "loan_type": sc.loan_type
                },
                "priority": "high"
            })

        # 3. Create qualification task
        actions.append({
            "action_type": "task",
            "target": "loan_officer",
            "template": "qualify_prospect",
            "data": {
                "title": f"Complete qualification for {first_name}",
                "description": f"Gather: income, credit estimate, down payment, timeline, loan type preference.",
                "due_hours": 48,
                "priority": "medium",
                "lead_id": sc.lead_id,
                "assigned_to": sc.loan_officer_id
            }
        })

        # 4. Send educational resources
        if sc.lead_email:
            actions.append({
                "action_type": "email",
                "target": "lead",
                "template": "educational_resources",
                "data": {
                    "to": sc.lead_email,
                    "subject": "Your Mortgage Journey - Helpful Resources",
                    "lead_name": sc.lead_name,
                    "loan_type": sc.loan_type or "purchase"
                },
                "scheduled_for": datetime.utcnow() + timedelta(hours=24)
            })

        # 5. Switch to prospect nurture
        actions.append({
            "action_type": "drip",
            "target": "lead",
            "template": "prospect_nurture",
            "data": {
                "lead_id": sc.lead_id,
                "campaign": "prospect_nurture",
                "stop_campaign": "attempted_contact_nurture"
            }
        })

        logger.info(f"🤝 ATTEMPTED→PROSPECT workflow triggered: {len(actions)} actions for {sc.lead_name}")
        return actions

    async def _handle_prospect_to_application(self, sc: LeadStatusChange) -> List[Dict]:
        """Handle transition from Prospect to Application Started"""
        actions = []
        first_name = sc.lead_name.split()[0] if sc.lead_name else "there"

        # 1. Send application started confirmation
        if sc.lead_email:
            actions.append({
                "action_type": "email",
                "target": "lead",
                "template": "application_started",
                "data": {
                    "to": sc.lead_email,
                    "subject": f"Your Mortgage Application Has Started, {first_name}!",
                    "lead_name": sc.lead_name,
                    "loan_officer_name": sc.loan_officer_name
                },
                "priority": "high"
            })

        # 2. SMS confirmation
        if sc.lead_phone:
            actions.append({
                "action_type": "sms",
                "target": "lead",
                "template": "application_started",
                "data": {
                    "to": sc.lead_phone,
                    "message": f"Hi {first_name}! Your mortgage application has started. Check your email for next steps and document checklist. Questions? Reply here!"
                }
            })

        # 3. Create document collection task
        actions.append({
            "action_type": "task",
            "target": "loan_officer",
            "template": "collect_documents",
            "data": {
                "title": f"Collect documents from {first_name}",
                "description": "Request: paystubs, W2s, bank statements, ID. Send document checklist.",
                "due_hours": 24,
                "priority": "high",
                "lead_id": sc.lead_id,
                "assigned_to": sc.loan_officer_id
            }
        })

        # 4. Application nurture campaign
        actions.append({
            "action_type": "drip",
            "target": "lead",
            "template": "application_nurture",
            "data": {
                "lead_id": sc.lead_id,
                "campaign": "application_nurture",
                "stop_campaign": "prospect_nurture"
            }
        })

        logger.info(f"📋 PROSPECT→APPLICATION workflow triggered: {len(actions)} actions for {sc.lead_name}")
        return actions

    async def _handle_application_complete(self, sc: LeadStatusChange) -> List[Dict]:
        """Handle transition to Application Complete"""
        actions = []
        first_name = sc.lead_name.split()[0] if sc.lead_name else "there"

        # 1. Congratulations email
        if sc.lead_email:
            actions.append({
                "action_type": "email",
                "target": "lead",
                "template": "application_complete",
                "data": {
                    "to": sc.lead_email,
                    "subject": f"Application Complete! Next Steps for {first_name}",
                    "lead_name": sc.lead_name,
                    "loan_officer_name": sc.loan_officer_name
                },
                "priority": "high"
            })

        # 2. SMS notification
        if sc.lead_phone:
            actions.append({
                "action_type": "sms",
                "target": "lead",
                "template": "application_complete",
                "data": {
                    "to": sc.lead_phone,
                    "message": f"🎉 {first_name}, your application is complete! We're submitting to underwriting. I'll keep you posted on every step. - {sc.loan_officer_name}"
                }
            })

        # 3. Create underwriting submission task
        actions.append({
            "action_type": "task",
            "target": "loan_officer",
            "template": "submit_underwriting",
            "data": {
                "title": f"Submit {first_name}'s file to underwriting",
                "description": "Review application completeness and submit to underwriting.",
                "due_hours": 4,
                "priority": "high",
                "lead_id": sc.lead_id,
                "assigned_to": sc.loan_officer_id
            }
        })

        logger.info(f"✅ APPLICATION COMPLETE workflow triggered: {len(actions)} actions for {sc.lead_name}")
        return actions

    async def _handle_pre_approved(self, sc: LeadStatusChange) -> List[Dict]:
        """Handle transition to Pre-Approved"""
        actions = []
        first_name = sc.lead_name.split()[0] if sc.lead_name else "there"

        # 1. Celebration email
        if sc.lead_email:
            actions.append({
                "action_type": "email",
                "target": "lead",
                "template": "pre_approved",
                "data": {
                    "to": sc.lead_email,
                    "subject": f"🎉 Congratulations {first_name} - You're Pre-Approved!",
                    "lead_name": sc.lead_name,
                    "loan_officer_name": sc.loan_officer_name,
                    "loan_amount": sc.loan_amount
                },
                "priority": "urgent"
            })

        # 2. Celebration SMS
        if sc.lead_phone:
            actions.append({
                "action_type": "sms",
                "target": "lead",
                "template": "pre_approved",
                "data": {
                    "to": sc.lead_phone,
                    "message": f"🎉 CONGRATULATIONS {first_name}! You're PRE-APPROVED! Check your email for your pre-approval letter. Let's find your home! - {sc.loan_officer_name}"
                },
                "priority": "urgent"
            })

        # 3. Alert LO
        actions.append({
            "action_type": "alert",
            "target": "loan_officer",
            "template": "pre_approval_issued",
            "data": {
                "loan_officer_id": sc.loan_officer_id,
                "message": f"🏆 Pre-approval issued for {sc.lead_name}!",
                "lead_id": sc.lead_id
            },
            "priority": "normal"
        })

        # 4. Create pre-approval follow-up task
        actions.append({
            "action_type": "task",
            "target": "loan_officer",
            "template": "pre_approval_followup",
            "data": {
                "title": f"Pre-approval follow-up with {first_name}",
                "description": "Send pre-approval letter, discuss property search, connect with realtor if needed.",
                "due_hours": 2,
                "priority": "high",
                "lead_id": sc.lead_id,
                "assigned_to": sc.loan_officer_id
            }
        })

        # 5. Pre-approved nurture campaign
        actions.append({
            "action_type": "drip",
            "target": "lead",
            "template": "pre_approved_nurture",
            "data": {
                "lead_id": sc.lead_id,
                "campaign": "pre_approved_nurture",
                "stop_campaign": "application_nurture"
            }
        })

        logger.info(f"🏆 PRE-APPROVED workflow triggered: {len(actions)} actions for {sc.lead_name}")
        return actions

    async def _log_execution(self, sc: LeadStatusChange, actions: List[Dict]):
        """Log workflow execution to database"""
        try:
            self.db.execute(text("""
                INSERT INTO workflow_executions
                (workflow_id, workflow_name, lead_id, trigger_event, execution_status, actions_completed)
                VALUES (:workflow_id, :workflow_name, :lead_id, :trigger_event, :status, :actions)
            """), {
                "workflow_id": f"lead_status_{sc.old_status}_{sc.new_status}".lower().replace(" ", "_"),
                "workflow_name": f"Lead Status Change: {sc.old_status} → {sc.new_status}",
                "lead_id": sc.lead_id,
                "trigger_event": "lead_status_change",
                "status": "success",
                "actions": json.dumps(actions)
            })
            self.db.commit()
        except Exception as e:
            logger.warning(f"Could not log workflow execution: {e}")
            self.db.rollback()


class TimeBasedWorkflowEngine:
    """Engine for time-based automation rules"""

    def __init__(self, db: Session):
        self.db = db

    async def check_stale_leads(self) -> List[Dict]:
        """Check for leads that need time-based actions"""
        actions = []
        now = datetime.utcnow()

        # Check for New leads not contacted within 1 hour
        actions.extend(await self._check_new_no_contact(now))

        # Check for Attempted Contact leads needing re-engagement
        actions.extend(await self._check_attempted_reengagement(now))

        # Check for stalled Prospects
        actions.extend(await self._check_stalled_prospects(now))

        # Check for incomplete applications
        actions.extend(await self._check_incomplete_applications(now))

        return actions

    async def _check_new_no_contact(self, now: datetime) -> List[Dict]:
        """Find New leads without contact attempt after threshold"""
        actions = []
        threshold = now - timedelta(hours=TIME_RULES["new_no_contact"])
        escalate_threshold = now - timedelta(hours=TIME_RULES["new_escalate"])

        try:
            # Find stale new leads
            result = self.db.execute(text("""
                SELECT l.id, l.name, l.email, l.phone, l.owner_id, u.full_name as owner_name, l.created_at
                FROM leads l
                LEFT JOIN users u ON l.owner_id = u.id
                WHERE l.stage = 'New'
                AND l.created_at < :threshold
                AND l.created_at > :max_age
            """), {
                "threshold": threshold,
                "max_age": now - timedelta(hours=24)  # Don't process very old leads
            })

            for row in result.fetchall():
                lead_age_hours = (now - row.created_at).total_seconds() / 3600

                if row.created_at < escalate_threshold:
                    # Escalate to manager
                    actions.append({
                        "action_type": "alert",
                        "target": "manager",
                        "template": "escalate_no_contact",
                        "data": {
                            "message": f"⚠️ ESCALATION: {row.name} has been New for {lead_age_hours:.1f} hours with no contact",
                            "lead_id": row.id,
                            "loan_officer_id": row.owner_id,
                            "loan_officer_name": row.owner_name
                        },
                        "priority": "urgent"
                    })
                else:
                    # Alert loan officer
                    actions.append({
                        "action_type": "alert",
                        "target": "loan_officer",
                        "template": "no_contact_reminder",
                        "data": {
                            "loan_officer_id": row.owner_id,
                            "message": f"⏰ REMINDER: {row.name} waiting for first contact ({lead_age_hours:.1f} hours)",
                            "lead_id": row.id
                        },
                        "priority": "high"
                    })

        except Exception as e:
            logger.error(f"Error checking new leads without contact: {e}")

        return actions

    async def _check_attempted_reengagement(self, now: datetime) -> List[Dict]:
        """Find Attempted Contact leads needing re-engagement"""
        actions = []
        threshold = now - timedelta(hours=TIME_RULES["attempted_reengagement"])

        try:
            result = self.db.execute(text("""
                SELECT l.id, l.name, l.email, l.phone, l.owner_id, u.full_name as owner_name, l.updated_at
                FROM leads l
                LEFT JOIN users u ON l.owner_id = u.id
                WHERE l.stage = 'Attempted Contact'
                AND l.updated_at < :threshold
            """), {"threshold": threshold})

            for row in result.fetchall():
                first_name = row.name.split()[0] if row.name else "there"

                # Create re-engagement task
                actions.append({
                    "action_type": "task",
                    "target": "loan_officer",
                    "template": "reengagement",
                    "data": {
                        "title": f"Re-engagement needed: {first_name}",
                        "description": f"{row.name} has been in Attempted Contact for 3+ days. Try 'breakup email' or different approach.",
                        "due_hours": 24,
                        "priority": "medium",
                        "lead_id": row.id,
                        "assigned_to": row.owner_id
                    }
                })

        except Exception as e:
            logger.error(f"Error checking attempted contact re-engagement: {e}")

        return actions

    async def _check_stalled_prospects(self, now: datetime) -> List[Dict]:
        """Find Prospects stalled without progression"""
        actions = []
        threshold = now - timedelta(hours=TIME_RULES["prospect_stalled"])

        try:
            result = self.db.execute(text("""
                SELECT l.id, l.name, l.email, l.owner_id, u.full_name as owner_name, l.updated_at
                FROM leads l
                LEFT JOIN users u ON l.owner_id = u.id
                WHERE l.stage = 'Prospect'
                AND l.updated_at < :threshold
            """), {"threshold": threshold})

            for row in result.fetchall():
                first_name = row.name.split()[0] if row.name else "there"
                days_stalled = (now - row.updated_at).days

                actions.append({
                    "action_type": "task",
                    "target": "loan_officer",
                    "template": "barrier_identification",
                    "data": {
                        "title": f"Barrier identification call with {first_name}",
                        "description": f"{row.name} has been Prospect for {days_stalled} days. Identify what's blocking progression.",
                        "due_hours": 48,
                        "priority": "high",
                        "lead_id": row.id,
                        "assigned_to": row.owner_id
                    }
                })

        except Exception as e:
            logger.error(f"Error checking stalled prospects: {e}")

        return actions

    async def _check_incomplete_applications(self, now: datetime) -> List[Dict]:
        """Find incomplete applications needing follow-up"""
        actions = []
        threshold = now - timedelta(hours=TIME_RULES["application_incomplete"])

        try:
            result = self.db.execute(text("""
                SELECT l.id, l.name, l.email, l.phone, l.owner_id, u.full_name as owner_name, l.updated_at
                FROM leads l
                LEFT JOIN users u ON l.owner_id = u.id
                WHERE l.stage = 'Application Started'
                AND l.updated_at < :threshold
            """), {"threshold": threshold})

            for row in result.fetchall():
                first_name = row.name.split()[0] if row.name else "there"

                # Send reminder SMS
                if row.phone:
                    actions.append({
                        "action_type": "sms",
                        "target": "lead",
                        "template": "application_reminder",
                        "data": {
                            "to": row.phone,
                            "message": f"Hi {first_name}! Just checking in on your mortgage application. Need help with any documents? Reply with questions!"
                        }
                    })

                # Create follow-up task
                actions.append({
                    "action_type": "task",
                    "target": "loan_officer",
                    "template": "application_followup",
                    "data": {
                        "title": f"Application follow-up with {first_name}",
                        "description": f"Application incomplete for 48+ hours. Check for missing documents, offer assistance.",
                        "due_hours": 4,
                        "priority": "high",
                        "lead_id": row.id,
                        "assigned_to": row.owner_id
                    }
                })

        except Exception as e:
            logger.error(f"Error checking incomplete applications: {e}")

        return actions
