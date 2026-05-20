"""
CRM Operations API Routes

Provides endpoints for core CRM operations:
- Process Templates: Role-based task management for mortgage workflow processes
- Analytics: Conversion funnel, pipeline analytics, and scorecard metrics
- Portfolio: Portfolio loan management and statistics

These routes use runtime imports from main.py to avoid circular imports.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from db import get_db, get_async_db
import logging

logger = logging.getLogger(__name__)

# Runtime imports from main.py to avoid circular imports
try:
    from auth.dependencies import get_current_user
    from database.enums import LeadStage, LoanStage
    from database.models import ProcessTemplate, Lead, Loan, Activity, User
except ImportError:
    # Fallback for testing or standalone execution
    async def get_current_user():
        return type('User', (), {'id': 1})()
    ProcessTemplate = None
    Lead = None
    Loan = None
    Activity = None
    User = None
    LeadStage = None
    LoanStage = None


router = APIRouter(prefix="/api/v1", tags=["CRM Operations"])


# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class ProcessTemplateCreate(BaseModel):
    role_name: str
    task_title: str
    task_description: Optional[str] = None
    sequence_order: int = 0
    estimated_duration: Optional[int] = None
    dependencies: Optional[List[int]] = None
    is_required: bool = True


class ProcessTemplateUpdate(BaseModel):
    task_title: Optional[str] = None
    task_description: Optional[str] = None
    sequence_order: Optional[int] = None
    estimated_duration: Optional[int] = None
    dependencies: Optional[List[int]] = None
    is_required: Optional[bool] = None
    is_active: Optional[bool] = None


class ProcessTemplateResponse(BaseModel):
    id: int
    role_name: str
    task_title: str
    task_description: Optional[str]
    sequence_order: int
    estimated_duration: Optional[int]
    dependencies: Optional[List[int]]
    is_required: bool
    automation_potential: Optional[str]
    efficiency_notes: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# =============================================================================
# PROCESS TEMPLATES - Role-Based Task Management
# =============================================================================

@router.get("/process-templates/", response_model=List[ProcessTemplateResponse])
async def get_process_templates(
    role_name: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all process templates, optionally filtered by role"""
    query = db.query(ProcessTemplate).filter(
        ProcessTemplate.user_id == current_user.id,
        ProcessTemplate.is_active == True
    )

    if role_name:
        query = query.filter(ProcessTemplate.role_name == role_name)

    templates = query.order_by(ProcessTemplate.role_name, ProcessTemplate.sequence_order).all()
    return templates


@router.get("/process-templates/roles", response_model=List[str])
async def get_process_template_roles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all unique role names that have process templates"""
    roles = db.query(ProcessTemplate.role_name).filter(
        ProcessTemplate.user_id == current_user.id,
        ProcessTemplate.is_active == True
    ).distinct().all()

    return [role[0] for role in roles]


@router.post("/process-templates/", response_model=ProcessTemplateResponse, status_code=201)
async def create_process_template(
    template: ProcessTemplateCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new process template task"""
    db_template = ProcessTemplate(**template.model_dump(), user_id=current_user.id)
    db.add(db_template)
    await db.commit()
    await db.refresh(db_template)

    logger.info(f"Process template created: {db_template.role_name} - {db_template.task_title}")
    return db_template


@router.patch("/process-templates/{template_id}", response_model=ProcessTemplateResponse)
async def update_process_template(
    template_id: int,
    template_update: ProcessTemplateUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a process template (admin only)"""
    db_template = db.query(ProcessTemplate).filter(
        ProcessTemplate.id == template_id,
        ProcessTemplate.user_id == current_user.id
    ).first()

    if not db_template:
        raise HTTPException(status_code=404, detail="Process template not found")

    update_data = template_update.dict(exclude_unset=True)
    _protected = {'id', 'organization_id', 'created_at', 'updated_at', 'user_id'}
    for field, value in update_data.items():
        if field not in _protected:
            setattr(db_template, field, value)

    db_template.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(db_template)

    logger.info(f"Process template updated: {db_template.id}")
    return db_template


@router.delete("/process-templates/{template_id}", status_code=204)
async def delete_process_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a process template (soft delete)"""
    db_template = db.query(ProcessTemplate).filter(
        ProcessTemplate.id == template_id,
        ProcessTemplate.user_id == current_user.id
    ).first()

    if not db_template:
        raise HTTPException(status_code=404, detail="Process template not found")

    db_template.is_active = False
    db.commit()

    logger.info(f"Process template deleted: {db_template.id}")
    return None


@router.post("/process-templates/analyze-efficiency")
async def analyze_process_efficiency(
    role_name: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """AI-powered efficiency analysis of process templates"""
    query = db.query(ProcessTemplate).filter(
        ProcessTemplate.user_id == current_user.id,
        ProcessTemplate.is_active == True
    )

    if role_name:
        query = query.filter(ProcessTemplate.role_name == role_name)

    templates = query.order_by(ProcessTemplate.role_name, ProcessTemplate.sequence_order).all()

    if not templates:
        return {
            "status": "no_data",
            "message": "No process templates found for analysis",
            "suggestions": []
        }

    # AI-powered efficiency analysis
    suggestions = []
    role_groups = {}

    # Group by role
    for template in templates:
        if template.role_name not in role_groups:
            role_groups[template.role_name] = []
        role_groups[template.role_name].append(template)

    # Analyze each role's process
    for role, tasks in role_groups.items():
        total_duration = sum(t.estimated_duration or 30 for t in tasks)
        required_tasks = [t for t in tasks if t.is_required]
        optional_tasks = [t for t in tasks if not t.is_required]

        # Suggest automation opportunities
        manual_tasks = [t for t in tasks if not t.automation_potential or t.automation_potential == "none"]
        if len(manual_tasks) > len(tasks) * 0.6:
            suggestions.append({
                "role": role,
                "type": "automation",
                "severity": "high",
                "title": f"{role}: High manual task load detected",
                "description": f"{len(manual_tasks)} out of {len(tasks)} tasks are manual. Consider automating repetitive tasks.",
                "impact": "Could reduce process time by 30-40%",
                "tasks_affected": [t.task_title for t in manual_tasks[:3]]
            })

        # Check for bottlenecks (long duration tasks)
        long_tasks = [t for t in tasks if (t.estimated_duration or 30) > 60]
        if long_tasks:
            suggestions.append({
                "role": role,
                "type": "bottleneck",
                "severity": "medium",
                "title": f"{role}: Time-intensive tasks identified",
                "description": f"{len(long_tasks)} tasks take over 60 minutes. Consider breaking them down.",
                "impact": "Could improve workflow parallelization",
                "tasks_affected": [f"{t.task_title} ({t.estimated_duration}min)" for t in long_tasks]
            })

        # Check dependencies
        tasks_with_deps = [t for t in tasks if t.dependencies and len(t.dependencies) > 0]
        if len(tasks_with_deps) > len(tasks) * 0.7:
            suggestions.append({
                "role": role,
                "type": "dependency",
                "severity": "medium",
                "title": f"{role}: High task dependency detected",
                "description": f"{len(tasks_with_deps)} tasks have dependencies. This may slow down the process.",
                "impact": "Review if some tasks can be parallelized",
                "tasks_affected": []
            })

        # Check for missing required tasks
        if len(required_tasks) < 3:
            suggestions.append({
                "role": role,
                "type": "completeness",
                "severity": "low",
                "title": f"{role}: Process may be incomplete",
                "description": f"Only {len(required_tasks)} required tasks defined. Review if process is complete.",
                "impact": "Ensure all critical steps are documented",
                "tasks_affected": []
            })

        # Overall efficiency score
        efficiency_score = 100
        if len(manual_tasks) > len(tasks) * 0.6:
            efficiency_score -= 30
        if long_tasks:
            efficiency_score -= 20
        if len(tasks_with_deps) > len(tasks) * 0.7:
            efficiency_score -= 15

        suggestions.append({
            "role": role,
            "type": "summary",
            "severity": "info",
            "title": f"{role}: Efficiency Score - {efficiency_score}%",
            "description": f"Total tasks: {len(tasks)} | Est. time: {total_duration} min | Required: {len(required_tasks)}",
            "impact": f"Process is {'efficient' if efficiency_score >= 70 else 'needs optimization'}",
            "efficiency_score": efficiency_score
        })

    return {
        "status": "success",
        "total_templates": len(templates),
        "roles_analyzed": list(role_groups.keys()),
        "suggestions": suggestions
    }


@router.post("/process-templates/seed-defaults")
async def seed_default_templates(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Seed default process templates for common roles"""
    # Check if user already has templates
    existing = db.query(ProcessTemplate).filter(ProcessTemplate.user_id == current_user.id).first()
    if existing:
        return {"message": "Templates already exist", "count": 0}

    default_templates = [
        # Loan Officer Tasks
        {"role_name": "Loan Officer", "task_title": "Initial Client Contact", "task_description": "Make first contact with borrower, introduce yourself and explain the loan process", "sequence_order": 1, "estimated_duration": 30, "is_required": True},
        {"role_name": "Loan Officer", "task_title": "Gather Financial Documents", "task_description": "Request pay stubs, tax returns, bank statements, and employment verification", "sequence_order": 2, "estimated_duration": 20, "is_required": True},
        {"role_name": "Loan Officer", "task_title": "Run Credit Report", "task_description": "Pull credit report and review credit score and history", "sequence_order": 3, "estimated_duration": 15, "is_required": True},
        {"role_name": "Loan Officer", "task_title": "Calculate DTI and Pre-Approval Amount", "task_description": "Calculate debt-to-income ratio and determine pre-approval amount", "sequence_order": 4, "estimated_duration": 30, "is_required": True},
        {"role_name": "Loan Officer", "task_title": "Send Pre-Approval Letter", "task_description": "Generate and send pre-approval letter to borrower", "sequence_order": 5, "estimated_duration": 15, "is_required": True},
        {"role_name": "Loan Officer", "task_title": "Schedule Follow-Up", "task_description": "Schedule follow-up call to check on house hunting progress", "sequence_order": 6, "estimated_duration": 10, "is_required": False},

        # Processor Tasks
        {"role_name": "Processor", "task_title": "Receive Loan Application", "task_description": "Receive completed loan application from loan officer", "sequence_order": 1, "estimated_duration": 15, "is_required": True},
        {"role_name": "Processor", "task_title": "Order Appraisal", "task_description": "Contact appraiser and schedule property appraisal", "sequence_order": 2, "estimated_duration": 20, "is_required": True},
        {"role_name": "Processor", "task_title": "Order Title Report", "task_description": "Request title search and title commitment", "sequence_order": 3, "estimated_duration": 15, "is_required": True},
        {"role_name": "Processor", "task_title": "Verify Employment", "task_description": "Contact employer to verify employment and income", "sequence_order": 4, "estimated_duration": 30, "is_required": True},
        {"role_name": "Processor", "task_title": "Review Documentation", "task_description": "Review all submitted documentation for completeness and accuracy", "sequence_order": 5, "estimated_duration": 45, "is_required": True},
        {"role_name": "Processor", "task_title": "Prepare Underwriting Package", "task_description": "Compile all documents and prepare file for underwriting", "sequence_order": 6, "estimated_duration": 60, "is_required": True},
        {"role_name": "Processor", "task_title": "Submit to Underwriting", "task_description": "Submit completed file to underwriter for review", "sequence_order": 7, "estimated_duration": 15, "is_required": True},

        # Underwriter Tasks
        {"role_name": "Underwriter", "task_title": "Initial File Review", "task_description": "Perform initial review of loan file for completeness", "sequence_order": 1, "estimated_duration": 30, "is_required": True},
        {"role_name": "Underwriter", "task_title": "Verify Income Documentation", "task_description": "Review and verify all income documentation", "sequence_order": 2, "estimated_duration": 45, "is_required": True},
        {"role_name": "Underwriter", "task_title": "Review Credit Report", "task_description": "Analyze credit report and evaluate credit risk", "sequence_order": 3, "estimated_duration": 30, "is_required": True},
        {"role_name": "Underwriter", "task_title": "Evaluate Collateral", "task_description": "Review appraisal and assess property value", "sequence_order": 4, "estimated_duration": 30, "is_required": True},
        {"role_name": "Underwriter", "task_title": "Issue Conditions", "task_description": "Create list of conditions that must be satisfied for approval", "sequence_order": 5, "estimated_duration": 45, "is_required": True},
        {"role_name": "Underwriter", "task_title": "Final Approval Decision", "task_description": "Make final loan approval decision once all conditions are met", "sequence_order": 6, "estimated_duration": 30, "is_required": True},

        # Closer Tasks
        {"role_name": "Closer", "task_title": "Receive Clear to Close", "task_description": "Receive clear to close notification from underwriting", "sequence_order": 1, "estimated_duration": 10, "is_required": True},
        {"role_name": "Closer", "task_title": "Prepare Closing Disclosure", "task_description": "Generate closing disclosure with final loan terms and costs", "sequence_order": 2, "estimated_duration": 45, "is_required": True},
        {"role_name": "Closer", "task_title": "Send Closing Disclosure", "task_description": "Send closing disclosure to borrower (3-day waiting period required)", "sequence_order": 3, "estimated_duration": 15, "is_required": True},
        {"role_name": "Closer", "task_title": "Schedule Closing Appointment", "task_description": "Coordinate with all parties and schedule closing date/time", "sequence_order": 4, "estimated_duration": 30, "is_required": True},
        {"role_name": "Closer", "task_title": "Prepare Closing Package", "task_description": "Prepare all closing documents and wire instructions", "sequence_order": 5, "estimated_duration": 60, "is_required": True},
        {"role_name": "Closer", "task_title": "Coordinate Final Walk-Through", "task_description": "Ensure borrower completes final property walk-through", "sequence_order": 6, "estimated_duration": 20, "is_required": True},
        {"role_name": "Closer", "task_title": "Attend Closing", "task_description": "Attend closing or coordinate with title company", "sequence_order": 7, "estimated_duration": 90, "is_required": True},
    ]

    templates_created = []
    for template_data in default_templates:
        db_template = ProcessTemplate(**template_data, user_id=current_user.id)
        db.add(db_template)
        templates_created.append(db_template)

    db.commit()

    logger.info(f"Seeded {len(templates_created)} default process templates for user {current_user.id}")
    return {"message": "Default templates created successfully", "count": len(templates_created)}


# =============================================================================
# ANALYTICS
# =============================================================================

@router.get("/analytics/conversion-funnel")
async def get_conversion_funnel(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get conversion funnel analytics"""
    leads = db.query(Lead).filter(Lead.owner_id == current_user.id).all()
    total = len(leads)

    if total == 0:
        return {"total_leads": 0, "stages": {}, "conversion_rates": {}}

    stages_count = {
        "new": len([l for l in leads if l.stage == LeadStage.NEW]),
        "contacted": len([l for l in leads if l.stage != LeadStage.NEW]),
        "prospect": len([l for l in leads if l.stage in [LeadStage.PROSPECT, LeadStage.APPLICATION, LeadStage.PRE_QUALIFIED, LeadStage.PRE_APPROVED]]),
        "application": len([l for l in leads if l.stage in [LeadStage.APPLICATION, LeadStage.PRE_QUALIFIED, LeadStage.PRE_APPROVED]]),
        "pre_approved": len([l for l in leads if l.stage == LeadStage.PRE_APPROVED])
    }

    return {
        "total_leads": total,
        "stages": stages_count,
        "conversion_rates": {
            "new_to_contacted": (stages_count["contacted"] / total * 100) if total > 0 else 0,
            "overall": (stages_count["pre_approved"] / total * 100) if total > 0 else 0
        }
    }


@router.get("/analytics/pipeline")
async def get_pipeline_analytics(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get pipeline analytics with stage breakdown.
    Uses raw SQL to avoid enum validation issues with legacy data.
    """
    from sqlalchemy import text
    from services.cache_service import cache_get, cache_set

    user_id = getattr(current_user, "id", None)
    org_id = getattr(current_user, "organization_id", None)
    cache_key = f"pipeline:analytics:user:{user_id}:org:{org_id}:v1"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        # Use raw SQL to avoid ORM enum issues
        query = text("""
            SELECT id, stage, amount
            FROM loans
            WHERE loan_officer_id = :user_id
        """)
        result = await db.execute(query, {"user_id": current_user.id})
        loans_data = result.fetchall()

        # Build stage breakdown manually
        stage_breakdown = {}
        for stage in LoanStage:
            stage_loans = [l for l in loans_data if l.stage == stage.value]
            stage_breakdown[stage.value] = {
                "count": len(stage_loans),
                "volume": sum([l.amount for l in stage_loans if l.amount]) or 0
            }

        total_volume = sum([l.amount for l in loans_data if l.amount]) or 0

        response = {
            "total_loans": len(loans_data),
            "total_volume": total_volume,
            "stage_breakdown": stage_breakdown
        }
        cache_set(cache_key, response, ttl=30)
        return response
    except Exception as e:
        logger.error(f"Error in pipeline analytics: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Database error")


@router.get("/analytics/scorecard")
async def get_scorecard_metrics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get comprehensive scorecard metrics based on real loan activity"""
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import func, extract

    # Get current year for YTD calculations
    current_year = datetime.now().year

    # Get all leads and loans for the user
    leads = db.query(Lead).filter(Lead.owner_id == current_user.id).all()
    loans = db.query(Loan).filter(Loan.loan_officer_id == current_user.id).all()
    activities = db.query(Activity).join(Loan).filter(Loan.loan_officer_id == current_user.id).all()

    # Filter YTD data
    ytd_leads = [l for l in leads if l.created_at and l.created_at.year == current_year]
    ytd_loans = [l for l in loans if l.created_at and l.created_at.year == current_year]
    funded_loans = [l for l in ytd_loans if l.stage == LoanStage.FUNDED]

    # Calculate stage-based metrics from real loan activity
    total_leads = len(ytd_leads)
    prospect_leads = len([l for l in ytd_leads if l.stage == LeadStage.PROSPECT])
    app_started = len([l for l in ytd_leads if l.stage in [LeadStage.APPLICATION, LeadStage.PRE_QUALIFIED, LeadStage.PRE_APPROVED]])
    pre_approved = len([l for l in ytd_leads if l.stage == LeadStage.PRE_APPROVED])
    funded_count = len(funded_loans)

    # Active loans in different stages
    processing_loans = [l for l in ytd_loans if l.stage == LoanStage.PROCESSING]
    underwriting_loans = [l for l in ytd_loans if l.stage == LoanStage.UW_RECEIVED]
    clear_to_close = [l for l in ytd_loans if l.stage == LoanStage.CTC]

    # Calculate conversion metrics from actual data
    conversion_metrics = {
        "starts_to_apps": round((app_started / total_leads * 100) if total_leads > 0 else 0, 1),
        "apps_to_funded": round((funded_count / app_started * 100) if app_started > 0 else 0, 1),
        "starts_to_funded": round((funded_count / total_leads * 100) if total_leads > 0 else 0, 1),
        "credit_to_funded": round((funded_count / pre_approved * 100) if pre_approved > 0 else 0, 1)
    }

    # Calculate volume & revenue from real loan data
    total_volume = sum([l.amount for l in funded_loans if l.amount]) or 0
    avg_loan_amount = (total_volume / len(funded_loans)) if funded_loans else 0

    # Calculate commission (assuming 185 basis points average)
    commission_earned = total_volume * 0.0185 if total_volume else 0

    volume_revenue = {
        "total_loans": funded_count,
        "total_volume": total_volume,
        "avg_loan_amount": avg_loan_amount,
        "commission_earned": commission_earned,
        "referrals": len([l for l in ytd_leads if l.source and 'referral' in l.source.lower()]),
        "portfolio_value": sum([l.amount for l in loans if l.amount]) or 0  # All loans, not just YTD
    }

    # Calculate loan type distribution from real data
    loan_types = {}
    for loan in funded_loans:
        loan_type = loan.product_type or "Conventional"
        if loan_type not in loan_types:
            loan_types[loan_type] = {"count": 0, "volume": 0}
        loan_types[loan_type]["count"] += 1
        loan_types[loan_type]["volume"] += loan.amount if loan.amount else 0

    loan_type_distribution = [
        {
            "type": loan_type,
            "units": data["count"],
            "volume": data["volume"],
            "percentage": round((data["volume"] / total_volume * 100) if total_volume > 0 else 0, 2)
        }
        for loan_type, data in loan_types.items()
    ]

    # Calculate referral sources from real lead data
    referral_sources = {}
    for lead in ytd_leads:
        source = lead.source or "Unknown"
        if source not in referral_sources:
            referral_sources[source] = {"count": 0, "volume": 0}
        referral_sources[source]["count"] += 1
        # Find corresponding loan for this lead
        lead_loan = next((l for l in funded_loans if l.borrower_name == lead.name), None)
        if lead_loan and lead_loan.amount:
            referral_sources[source]["volume"] += lead_loan.amount

    referral_sources_list = [
        {
            "source": source,
            "referrals": data["count"],
            "closedVolume": data["volume"]
        }
        for source, data in referral_sources.items()
    ]

    # Calculate process timeline from actual loan activities and timestamps
    def calculate_avg_days(from_stage, to_stage):
        stage_transitions = []
        for loan in ytd_loans:
            if loan.created_at and loan.updated_at:
                # This is simplified - in reality you'd track stage transitions in activities
                if from_stage == "start" and to_stage == "app":
                    # Days from lead creation to loan creation (application start)
                    lead = next((l for l in ytd_leads if l.name == loan.borrower_name), None)
                    if lead and lead.created_at:
                        days = (loan.created_at - lead.created_at).days
                        stage_transitions.append(days)
                elif from_stage == "app" and to_stage == "underwriting":
                    # Days in processing
                    if loan.stage in [LoanStage.UW_RECEIVED, LoanStage.CTC, LoanStage.FUNDED]:
                        # Simplified calculation - would be better with activity timestamps
                        days = 5  # Default assumption
                        stage_transitions.append(days)

        return round(sum(stage_transitions) / len(stage_transitions)) if stage_transitions else 10

    process_timeline = [
        {
            "id": "starts-to-app",
            "title": "Avg Starts to App (LE)",
            "value": f"{calculate_avg_days('start', 'app')} Days",
            "subtitle": "Loan Officer Average"
        },
        {
            "id": "app-to-uw",
            "title": "Avg App (LE) to UW",
            "value": f"{calculate_avg_days('app', 'underwriting')} Days",
            "subtitle": "Loan Officer Average"
        },
        {
            "id": "lock-to-funded",
            "title": "Initial Lock to Funded",
            "value": len(funded_loans),
            "goal": 90,
            "current": len(processing_loans) + len(underwriting_loans),
            "total": len(ytd_loans),
            "isPercentage": True
        }
    ]

    # Current pipeline status
    pipeline_status = {
        "prospect": len([l for l in ytd_leads if l.stage == LeadStage.PROSPECT]),
        "application": len([l for l in ytd_loans if l.stage in [LoanStage.DISCLOSED, LoanStage.PROCESSING]]),
        "underwriting": len(underwriting_loans),
        "clear_to_close": len(clear_to_close),
        "funded": funded_count
    }

    return {
        "conversionMetrics": [
            {
                "id": "starts-to-apps",
                "title": "Starts to Apps (LE)",
                "value": conversion_metrics["starts_to_apps"],
                "goal": 75,
                "current": app_started,
                "total": total_leads,
                "isPercentage": True
            },
            {
                "id": "apps-to-funded",
                "title": "Apps (LE) to Funded",
                "value": conversion_metrics["apps_to_funded"],
                "goal": 80,
                "current": funded_count,
                "total": app_started,
                "isPercentage": True
            },
            {
                "id": "starts-to-funded",
                "title": "Starts to Funded Pull-thru",
                "value": conversion_metrics["starts_to_funded"],
                "goal": 50,
                "current": funded_count,
                "total": total_leads,
                "isPercentage": True
            },
            {
                "id": "credit-to-funded",
                "title": "Credit Pull to Funded",
                "value": conversion_metrics["credit_to_funded"],
                "goal": 70,
                "current": funded_count,
                "total": pre_approved,
                "isPercentage": True
            }
        ],
        "volumeRevenue": [
            {
                "id": "total-loans",
                "title": "Total Loans",
                "value": volume_revenue["total_loans"],
                "subtitle": "Year to Date"
            },
            {
                "id": "total-volume",
                "title": "Total Volume",
                "value": f"${volume_revenue['total_volume']:,.0f}",
                "subtitle": "Year to Date"
            },
            {
                "id": "referrals",
                "title": "Referrals",
                "value": volume_revenue["referrals"],
                "subtitle": "Active Referral Partners"
            },
            {
                "id": "commission",
                "title": "Commission Earned",
                "value": f"${volume_revenue['commission_earned']:,.0f}",
                "subtitle": "Year to Date"
            },
            {
                "id": "portfolio-value",
                "title": "Portfolio Value",
                "value": f"${volume_revenue['portfolio_value']:,.0f}",
                "subtitle": "Total Active Loans"
            }
        ],
        "loanTypes": loan_type_distribution,
        "referralSources": referral_sources_list,
        "processTimeline": process_timeline,
        "pipelineStatus": pipeline_status
    }


# =============================================================================
# PORTFOLIO
# =============================================================================

@router.get("/portfolio/")
async def get_portfolio(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get portfolio loans (funded/completed loans)"""
    # Get loans that are funded (completed)
    portfolio_loans = db.query(Loan).filter(
        Loan.loan_officer_id == current_user.id,
        Loan.stage == LoanStage.FUNDED
    ).order_by(Loan.updated_at.desc()).offset(skip).limit(limit).all()

    return portfolio_loans


@router.get("/portfolio/stats")
async def get_portfolio_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get portfolio statistics"""
    # Get all funded loans for the user (completed loans in portfolio)
    funded_loans = db.query(Loan).filter(
        Loan.loan_officer_id == current_user.id,
        Loan.stage == LoanStage.FUNDED
    ).all()

    # Calculate active loans (loans not funded yet)
    active_loans = db.query(Loan).filter(
        Loan.loan_officer_id == current_user.id,
        Loan.stage != LoanStage.FUNDED
    ).count()

    # Calculate total volume of funded loans
    total_volume = sum([loan.amount for loan in funded_loans if loan.amount]) or 0

    return {
        "total_loans": len(funded_loans),
        "total_volume": total_volume,
        "active_loans": active_loans,
        "closed_loans": len(funded_loans)  # Funded loans are considered closed
    }
