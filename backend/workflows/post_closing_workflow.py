"""
Post-Closing Referral Workflow Engine - Perennia AI
TL Development, LLC

Automatically processes loans when they close and triggers:
- Referral scoring and tagging
- Ambassador Program enrollment
- Workplace opportunity detection
- Strategic employer identification
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text
import json

logger = logging.getLogger(__name__)

# Configuration
HIGH_REFERRAL_SCORE = 80
MEDIUM_REFERRAL_SCORE = 50

# High-referral industries
HIGH_REFERRAL_INDUSTRIES = [
    "Real Estate", "Financial Services", "Education", "Healthcare",
    "Technology", "Insurance", "Legal", "Accounting"
]


class WorkflowTrigger(BaseModel):
    loan_id: int
    lead_id: int
    loan_status: str
    closed_date: datetime
    loan_officer_id: int
    organization_id: Optional[int] = None


class LeadWorkflowData(BaseModel):
    id: int
    name: str
    referral_source_score: int = 0
    leadership_level: Optional[str] = None
    employees_managed: int = 0
    referral_industry_flag: Optional[str] = None
    company_size: Optional[int] = None
    employer_name: Optional[str] = None
    industry: Optional[str] = None

    @property
    def first_name(self) -> str:
        return self.name.split()[0] if self.name else "Client"


class PostClosingWorkflowEngine:
    """Main workflow engine for post-closing automation"""

    def __init__(self, db: Session):
        self.db = db

    async def process_loan_closing(self, trigger: WorkflowTrigger, lead: LeadWorkflowData) -> Dict[str, Any]:
        """Process all workflows when a loan closes"""
        results: List[Dict[str, Any]] = []

        # ================================================================
        # WORKFLOW 1: HIGH REFERRAL SOURCE (Score >= 80)
        # ================================================================
        if lead.referral_source_score >= HIGH_REFERRAL_SCORE:
            logger.info(f"HIGH REFERRAL: {lead.first_name} (Score: {lead.referral_source_score})")
            results.append({
                "workflow": "high_referral",
                "action": "add_tags",
                "tags": ["High Referral Source", "Ambassador Candidate"]
            })
            results.append({
                "workflow": "high_referral",
                "action": "create_task",
                "title": f"Call {lead.first_name} - Invite to Ambassador Program",
                "due_days": 2,
                "priority": "high"
            })

        # ================================================================
        # WORKFLOW 2: MEDIUM REFERRAL SOURCE (Score 50-79)
        # ================================================================
        elif lead.referral_source_score >= MEDIUM_REFERRAL_SCORE:
            logger.info(f"MEDIUM REFERRAL: {lead.first_name} (Score: {lead.referral_source_score})")
            results.append({
                "workflow": "medium_referral",
                "action": "add_tags",
                "tags": ["Warm Referral Source"]
            })
            results.append({
                "workflow": "medium_referral",
                "action": "create_task",
                "title": f"Send thank-you + 'Who do you know?' to {lead.first_name}",
                "due_days": 7,
                "priority": "medium"
            })

        # ================================================================
        # WORKFLOW 3: LOW REFERRAL SOURCE (Score < 50)
        # ================================================================
        else:
            logger.info(f"LOW REFERRAL: {lead.first_name} (Score: {lead.referral_source_score})")
            results.append({
                "workflow": "low_referral",
                "action": "add_tags",
                "tags": ["Standard Referral Source"]
            })

        # ================================================================
        # WORKFLOW 4: WORKPLACE OPPORTUNITY (Managers with teams)
        # ================================================================
        is_manager = lead.employees_managed >= 5 or lead.leadership_level in ["Executive", "Manager", "Team Lead", "Director", "VP"]
        if is_manager:
            logger.info(f"WORKPLACE OPPORTUNITY: {lead.first_name} manages {lead.employees_managed} people")
            results.append({
                "workflow": "workplace_opportunity",
                "action": "add_tags",
                "tags": ["Workplace Opportunity"]
            })
            if lead.employer_name:
                results.append({
                    "workflow": "workplace_opportunity",
                    "action": "create_employer_record",
                    "company_name": lead.employer_name,
                    "employee_count": lead.company_size,
                    "champion_lead_id": lead.id
                })
            results.append({
                "workflow": "workplace_opportunity",
                "action": "create_task",
                "title": f"Discuss workplace mortgage benefit with {lead.first_name}",
                "due_days": 10,
                "priority": "high"
            })

        # ================================================================
        # WORKFLOW 5: HIGH-REFERRAL INDUSTRY
        # ================================================================
        if lead.industry and lead.industry in HIGH_REFERRAL_INDUSTRIES:
            logger.info(f"HIGH-REFERRAL INDUSTRY: {lead.first_name} works in {lead.industry}")
            results.append({
                "workflow": "high_referral_industry",
                "action": "add_tags",
                "tags": ["High-Referral Industry", "Ambassador Prospect"]
            })
            results.append({
                "workflow": "high_referral_industry",
                "action": "create_recurring_task",
                "title": f"Quarterly check-in with {lead.first_name} about coworkers",
                "interval_days": 90,
                "priority": "medium",
                "category": "Ambassador Check-In"
            })

        # ================================================================
        # WORKFLOW 6: STRATEGIC EMPLOYER (Large companies)
        # ================================================================
        is_strategic = (lead.company_size and lead.company_size >= 200) or (lead.employees_managed >= 20)
        if is_strategic:
            company = lead.employer_name or "Unknown Company"
            logger.info(f"STRATEGIC EMPLOYER: {company} ({lead.company_size or lead.employees_managed} employees)")
            results.append({
                "workflow": "strategic_employer",
                "action": "add_tags",
                "tags": ["Strategic Employer"]
            })
            results.append({
                "workflow": "strategic_employer",
                "action": "create_opportunity",
                "type": "Employer Mortgage Benefit Program",
                "company_name": company,
                "champion_name": lead.name,
                "estimated_employee_count": lead.company_size or lead.employees_managed
            })
            results.append({
                "workflow": "strategic_employer",
                "action": "create_task",
                "title": f"Set partnership meeting with {lead.first_name} at {company}",
                "due_days": 5,
                "priority": "urgent"
            })

        # ================================================================
        # LOG EXECUTION TO DATABASE
        # ================================================================
        try:
            self.db.execute(text("""
                INSERT INTO workflow_executions
                (workflow_id, workflow_name, lead_id, loan_id, trigger_event, execution_status, actions_completed, organization_id)
                VALUES (:workflow_id, :workflow_name, :lead_id, :loan_id, :trigger_event, :status, :actions, :org_id)
            """), {
                "workflow_id": "post_closing_referral",
                "workflow_name": "Post-Closing Referral Automation",
                "lead_id": lead.id,
                "loan_id": trigger.loan_id,
                "trigger_event": "loan_closed",
                "status": "success",
                "actions": json.dumps(results),
                "org_id": trigger.organization_id,
            })
            self.db.commit()
        except Exception as e:
            logger.warning(f"Could not log workflow execution: {e}")

        return {
            "success": True,
            "lead_id": lead.id,
            "loan_id": trigger.loan_id,
            "actions": results,
            "action_count": len(results)
        }


def calculate_referral_score(lead) -> int:
    """
    Calculate referral score (0-100) based on:
    - Industry (20 pts)
    - Leadership level (25 pts)
    - Network/team size (20 pts)
    - Company size (15 pts)
    - Social presence (20 pts) - placeholder
    """
    score = 0

    # Industry score (20 points)
    industry = getattr(lead, 'industry', None)
    if industry in HIGH_REFERRAL_INDUSTRIES:
        score += 20
    elif industry:
        score += 10

    # Leadership score (25 points)
    leadership = getattr(lead, 'leadership_level', None)
    if leadership == "Executive":
        score += 25
    elif leadership == "Director":
        score += 22
    elif leadership == "VP":
        score += 22
    elif leadership == "Manager":
        score += 18
    elif leadership == "Team Lead":
        score += 15
    elif leadership == "Senior":
        score += 10
    elif leadership:
        score += 5

    # Network/team size score (20 points)
    employees = getattr(lead, 'employees_managed', 0) or 0
    if employees >= 50:
        score += 20
    elif employees >= 20:
        score += 15
    elif employees >= 10:
        score += 10
    elif employees >= 5:
        score += 5

    # Company size score (15 points)
    company_size = getattr(lead, 'company_size', 0) or 0
    if company_size >= 500:
        score += 15
    elif company_size >= 200:
        score += 12
    elif company_size >= 100:
        score += 8
    elif company_size >= 50:
        score += 5

    # Base score for having any data (placeholder for social presence)
    if industry or leadership or employees or company_size:
        score += 5

    return min(score, 100)
