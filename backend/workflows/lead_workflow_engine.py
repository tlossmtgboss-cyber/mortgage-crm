"""
Lead Workflow Automation Engine - Perennia AI
TL Development, LLC

Automatically processes lead status changes and triggers:
- Email/SMS communications
- Task creation for LOs
- Drip campaign activation
- Activity logging
- Time-based automation rules
"""

from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Any
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text
import json
import logging

logger = logging.getLogger(__name__)

# Lead stage definitions matching database/enums.py LeadStage
LEAD_STAGES = [
    "New",
    "Attempted Contact",
    "Prospect",
    "Application",
    "Document Fulfillment",
    "Pre-Qualified",
    "Pre-Approved",
    "Under Contract",
    "Disclosed",
    "Long-Term Nurture",
    "Does Not Qualify",
    "Closed",
    "AMR",
    "Referral Source",
    "Withdrawn",
]

# Valid state transitions: source_status -> [allowed_target_statuses]
# None key = initial state (no prior status)
VALID_TRANSITIONS = {
    None: ["New"],
    "New": ["Attempted Contact", "Prospect", "Withdrawn", "Does Not Qualify"],
    "Attempted Contact": ["Prospect", "New", "Long-Term Nurture", "Withdrawn", "Does Not Qualify"],
    "Prospect": ["Application", "Attempted Contact", "Long-Term Nurture", "Withdrawn", "Does Not Qualify"],
    "Application": ["Document Fulfillment", "Pre-Qualified", "Prospect", "Withdrawn", "Does Not Qualify"],
    "Document Fulfillment": ["Pre-Qualified", "Application", "Withdrawn"],
    "Pre-Qualified": ["Pre-Approved", "Application", "Does Not Qualify", "Withdrawn"],
    "Pre-Approved": ["Under Contract", "Disclosed", "Long-Term Nurture", "Withdrawn"],
    "Under Contract": ["Disclosed", "Pre-Approved", "Withdrawn"],
    "Disclosed": ["Closed", "Long-Term Nurture", "Withdrawn", "Does Not Qualify"],
    "Long-Term Nurture": ["Prospect", "Application", "Withdrawn"],
    "Does Not Qualify": ["Prospect", "Application"],
    "Closed": ["AMR"],
    "AMR": ["Referral Source"],
    "Referral Source": [],
    "Withdrawn": ["New"],
}

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

    def _check_active_sla_workflow(self, lead_id: int) -> bool:
        """Check if lead has an active SLA-driven workflow instance."""
        try:
            existing = self.db.execute(text("""
                SELECT id FROM workflow_instances
                WHERE lead_id = :lid AND status = 'active'
                LIMIT 1
            """), {"lid": lead_id}).fetchone()
            return existing is not None
        except Exception as e:
            logger.warning(f"Error checking active SLA workflow for lead {lead_id}: {e}")
            return False

    async def process_status_change(self, status_change: LeadStatusChange) -> Dict[str, Any]:
        """Process all workflows when a lead status changes"""
        results = []

        old = status_change.old_status
        new = status_change.new_status

        logger.info(f"Processing status change: {old} → {new} for lead {status_change.lead_id}")

        # Validate transition against state machine
        allowed = VALID_TRANSITIONS.get(old, [])
        if new not in allowed:
            logger.warning(
                f"Invalid transition: {old} → {new} for lead {status_change.lead_id}. "
                f"Allowed targets: {allowed}. Continuing with best-effort handling."
            )

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
        # TRANSITION: Any → UNDER CONTRACT
        # ================================================================
        elif new == "Under Contract":
            results.extend(await self._handle_to_under_contract(status_change))

        # ================================================================
        # TRANSITION: Any → LONG-TERM NURTURE
        # ================================================================
        elif new == "Long-Term Nurture":
            results.extend(await self._handle_to_long_term_nurture(status_change))

        # ================================================================
        # TRANSITION: Any → DOES NOT QUALIFY
        # ================================================================
        elif new == "Does Not Qualify":
            results.extend(await self._handle_to_does_not_qualify(status_change))

        # ================================================================
        # TRANSITION: Any → WITHDRAWN
        # ================================================================
        elif new == "Withdrawn":
            results.extend(await self._handle_to_withdrawn(status_change))

        # ================================================================
        # TRANSITION: Any → DISCLOSED (lead-to-loan handoff)
        # ================================================================
        elif new == "Disclosed":
            results.extend(await self._handle_to_disclosed(status_change))

        # ================================================================
        # TRANSITION: Closed → AMR
        # ================================================================
        elif new == "AMR":
            results.extend(await self._handle_to_amr(status_change))

        # ================================================================
        # TRANSITION: AMR → REFERRAL SOURCE
        # ================================================================
        elif new == "Referral Source":
            results.extend(await self._handle_to_referral_source(status_change))

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
                    "subject": f"Welcome to Perennia AI - {sc.loan_officer_name} Will Be In Touch",
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
                "scheduled_for": datetime.now(timezone.utc) + timedelta(hours=24)
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

        # 3. Send team contact card via MMS
        if sc.lead_phone:
            actions.append({
                "action_type": "team_contact_card",
                "target": "lead",
                "template": "team_vcard",
                "data": {
                    "to": sc.lead_phone,
                    "lead_id": sc.lead_id,
                    "loan_officer_name": sc.loan_officer_name,
                },
                "priority": "normal"
            })

        # 4. Create underwriting submission task
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

    async def _handle_to_under_contract(self, sc: LeadStatusChange) -> List[Dict]:
        """Handle transition to Under Contract"""
        actions = []
        first_name = sc.lead_name.split()[0] if sc.lead_name else "there"

        # Defer to SLA workflow if active
        if self._check_active_sla_workflow(sc.lead_id):
            logger.info(f"Lead {sc.lead_id} in SLA workflow, skipping legacy under_contract actions")
            return actions

        # 1. Notify referral partner
        actions.append({
            "action_type": "alert",
            "target": "referral_partner",
            "template": "under_contract_notification",
            "data": {
                "lead_id": sc.lead_id,
                "message": f"{sc.lead_name} is now Under Contract! Document collection begins.",
            },
            "priority": "high"
        })

        # 2. Create document collection task
        actions.append({
            "action_type": "task",
            "target": "loan_officer",
            "template": "contract_doc_collection",
            "data": {
                "title": f"Collect contract documents from {first_name}",
                "description": "Collect: purchase contract, earnest money receipt, HOA docs, inspection reports.",
                "due_hours": 24,
                "priority": "high",
                "lead_id": sc.lead_id,
                "assigned_to": sc.loan_officer_id
            }
        })

        # 3. Start under_contract drip
        actions.append({
            "action_type": "drip",
            "target": "lead",
            "template": "under_contract_updates",
            "data": {
                "lead_id": sc.lead_id,
                "campaign": "under_contract_updates",
                "stop_campaign": "pre_approved_nurture"
            }
        })

        logger.info(f"🏠 UNDER CONTRACT workflow triggered: {len(actions)} actions for {sc.lead_name}")
        return actions

    async def _handle_to_long_term_nurture(self, sc: LeadStatusChange) -> List[Dict]:
        """Handle transition to Long-Term Nurture"""
        actions = []

        # Defer to SLA workflow if active
        if self._check_active_sla_workflow(sc.lead_id):
            logger.info(f"Lead {sc.lead_id} in SLA workflow, skipping legacy nurture actions")
            return actions

        # 1. Cancel active drip campaigns
        actions.append({
            "action_type": "drip",
            "target": "lead",
            "template": "nurture_long_term",
            "data": {
                "lead_id": sc.lead_id,
                "campaign": "nurture_long_term",
                "stop_all_campaigns": True
            }
        })

        # 2. Log activity
        actions.append({
            "action_type": "activity",
            "target": "lead",
            "template": "moved_to_nurture",
            "data": {
                "lead_id": sc.lead_id,
                "activity_type": "status_change",
                "note": f"Moved to Long-Term Nurture from {sc.old_status}"
            }
        })

        logger.info(f"🌱 LONG-TERM NURTURE workflow triggered for {sc.lead_name}")
        return actions

    async def _handle_to_does_not_qualify(self, sc: LeadStatusChange) -> List[Dict]:
        """Handle transition to Does Not Qualify"""
        actions = []
        first_name = sc.lead_name.split()[0] if sc.lead_name else "there"

        # Defer to SLA workflow if active
        if self._check_active_sla_workflow(sc.lead_id):
            logger.info(f"Lead {sc.lead_id} in SLA workflow, skipping legacy DNQ actions")
            return actions

        # 1. Send DNQ notification email
        if sc.lead_email:
            actions.append({
                "action_type": "email",
                "target": "lead",
                "template": "does_not_qualify",
                "data": {
                    "to": sc.lead_email,
                    "subject": f"{first_name}, Let's Work Together on Next Steps",
                    "lead_name": sc.lead_name,
                    "loan_officer_name": sc.loan_officer_name
                },
                "priority": "normal"
            })

        # 2. Enroll in credit repair workflow
        actions.append({
            "action_type": "drip",
            "target": "lead",
            "template": "credit_repair",
            "data": {
                "lead_id": sc.lead_id,
                "campaign": "credit_repair",
                "stop_all_campaigns": True
            }
        })

        # 3. Create credit improvement task
        actions.append({
            "action_type": "task",
            "target": "loan_officer",
            "template": "credit_improvement_plan",
            "data": {
                "title": f"Create credit improvement plan for {first_name}",
                "description": "Review credit report, identify improvement areas, set follow-up timeline.",
                "due_hours": 48,
                "priority": "medium",
                "lead_id": sc.lead_id,
                "assigned_to": sc.loan_officer_id
            }
        })

        logger.info(f"❌ DOES NOT QUALIFY workflow triggered for {sc.lead_name}")
        return actions

    async def _handle_to_withdrawn(self, sc: LeadStatusChange) -> List[Dict]:
        """Handle transition to Withdrawn"""
        actions = []

        # 1. Cancel all active workflows and drip campaigns
        actions.append({
            "action_type": "drip",
            "target": "lead",
            "template": "cancel_all",
            "data": {
                "lead_id": sc.lead_id,
                "stop_all_campaigns": True
            }
        })

        # 2. Log withdrawal reason
        actions.append({
            "action_type": "activity",
            "target": "lead",
            "template": "withdrawal",
            "data": {
                "lead_id": sc.lead_id,
                "activity_type": "withdrawal",
                "note": f"Lead withdrawn from {sc.old_status}. Reason: pending review."
            }
        })

        logger.info(f"🚫 WITHDRAWN workflow triggered for {sc.lead_name} (from {sc.old_status})")
        return actions

    async def _handle_to_disclosed(self, sc: LeadStatusChange) -> List[Dict]:
        """Handle transition to Disclosed (lead-to-loan handoff)"""
        actions = []
        first_name = sc.lead_name.split()[0] if sc.lead_name else "there"

        # Defer to SLA workflow if active
        if self._check_active_sla_workflow(sc.lead_id):
            logger.info(f"Lead {sc.lead_id} in SLA workflow, skipping legacy disclosed actions")
            return actions

        # 1. Alert LO about loan handoff
        actions.append({
            "action_type": "alert",
            "target": "loan_officer",
            "template": "disclosed_handoff",
            "data": {
                "loan_officer_id": sc.loan_officer_id,
                "message": f"📋 {sc.lead_name} is now Disclosed - loan processing begins.",
                "lead_id": sc.lead_id
            },
            "priority": "high"
        })

        # 2. Copy role assignments from lead to loan
        actions.append({
            "action_type": "task",
            "target": "loan_officer",
            "template": "disclosed_setup",
            "data": {
                "title": f"Set up loan file for {first_name}",
                "description": "Verify disclosures sent, set up loan pipeline, assign processor.",
                "due_hours": 4,
                "priority": "high",
                "lead_id": sc.lead_id,
                "assigned_to": sc.loan_officer_id
            }
        })

        # 3. Stop lead drip, start active loan updates
        actions.append({
            "action_type": "drip",
            "target": "lead",
            "template": "active_loan_updates",
            "data": {
                "lead_id": sc.lead_id,
                "campaign": "active_loan_updates",
                "stop_all_campaigns": True
            }
        })

        # 4. Auto-enroll the linked loan in the SLA workflow
        try:
            loan_row = self.db.execute(text("""
                SELECT lo.id AS loan_id
                FROM leads ld
                JOIN loans lo ON lo.loan_number = ld.loan_number
                WHERE ld.id = :lead_id
                  AND ld.loan_number IS NOT NULL
                LIMIT 1
            """), {"lead_id": sc.lead_id}).fetchone()

            if loan_row:
                from services.workflow_sla_service import WorkflowSLAService
                sla_service = WorkflowSLAService(self.db)
                result = sla_service.enroll_loan(
                    loan_id=loan_row.loan_id,
                    workflow_key="under_contract",
                    trigger_status="Disclosed",
                    user_id=sc.loan_officer_id,
                )
                if result.get("success"):
                    logger.info(f"Auto-enrolled loan {loan_row.loan_id} in under_contract SLA workflow")
                else:
                    logger.warning(f"Loan SLA enrollment skipped for lead {sc.lead_id}: {result.get('error')}")
            else:
                logger.info(f"No linked loan found for lead {sc.lead_id} — skipping loan SLA enrollment")
        except Exception as e:
            logger.warning(f"Loan SLA enrollment failed for lead {sc.lead_id}: {e}")

        logger.info(f"📋 DISCLOSED workflow triggered for {sc.lead_name}")
        return actions

    async def _handle_to_amr(self, sc: LeadStatusChange) -> List[Dict]:
        """Handle transition to Annual Mortgage Review"""
        actions = []
        first_name = sc.lead_name.split()[0] if sc.lead_name else "there"

        # 1. Schedule annual review task
        actions.append({
            "action_type": "task",
            "target": "loan_officer",
            "template": "annual_mortgage_review",
            "data": {
                "title": f"Annual Mortgage Review with {first_name}",
                "description": "Review current rate, equity position, and refinance opportunities.",
                "due_hours": 168,  # 7 days
                "priority": "medium",
                "lead_id": sc.lead_id,
                "assigned_to": sc.loan_officer_id
            }
        })

        # 2. Send AMR email
        if sc.lead_email:
            actions.append({
                "action_type": "email",
                "target": "lead",
                "template": "annual_review_intro",
                "data": {
                    "to": sc.lead_email,
                    "subject": f"{first_name}, Time for Your Annual Mortgage Review",
                    "lead_name": sc.lead_name,
                    "loan_officer_name": sc.loan_officer_name
                },
                "priority": "normal"
            })

        logger.info(f"📅 AMR workflow triggered for {sc.lead_name}")
        return actions

    async def _handle_to_referral_source(self, sc: LeadStatusChange) -> List[Dict]:
        """Handle transition to Referral Source (Circle of Cash Flow)"""
        actions = []
        first_name = sc.lead_name.split()[0] if sc.lead_name else "there"

        # 1. Create referral outreach task
        actions.append({
            "action_type": "task",
            "target": "loan_officer",
            "template": "referral_outreach",
            "data": {
                "title": f"Referral outreach with {first_name}",
                "description": "Thank client, request referrals, set up referral partner relationship.",
                "due_hours": 48,
                "priority": "medium",
                "lead_id": sc.lead_id,
                "assigned_to": sc.loan_officer_id
            }
        })

        # 2. Enroll in referral nurture campaign
        actions.append({
            "action_type": "drip",
            "target": "lead",
            "template": "referral_source_nurture",
            "data": {
                "lead_id": sc.lead_id,
                "campaign": "referral_source_nurture",
                "stop_all_campaigns": True
            }
        })

        logger.info(f"🤝 REFERRAL SOURCE workflow triggered for {sc.lead_name}")
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
        now = datetime.now(timezone.utc)

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
