"""
HR Management Routes
====================
Endpoints for HR/people management including:
- Job Description management
- Skills Library
- Responsibilities
- Goals & OKRs
- Skills Assessment

These routes handle employee development, performance tracking, and skill assessments.
"""

import logging
from datetime import datetime, timezone, date as dt_date
from typing import Dict, Any, List, Optional
from html.parser import HTMLParser

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from db import get_db

# Import from main.py
from auth.dependencies import get_current_user
from database.models import (
    User,
    UserJobDescription,
    Skill,
    UserResponsibility,
    ResponsibilitySkill,
    UserGoal,
    GoalKeyResult,
    GoalEmployeeAssessment,
    GoalManagerAssessment,
    GoalResponsibility,
    UserSkillAssessment,
)
from schemas.core import (
    UpdateJobDescriptionRequest,
    JobDescriptionResponse,
    SkillCreate,
    SkillResponse,
    CreateResponsibilityRequest,
    UpdateResponsibilityRequest,
    ReorderResponsibilitiesRequest,
)

logger = logging.getLogger(__name__)

# ============================================================================
# FEATURE TIER: EXPERIMENTAL
# This module is in the experimental tier -- frozen, no SLA.
# See backend/config/feature_tiers.py for tier definitions.
# ============================================================================

router = APIRouter(prefix="/api/v1", tags=["HR Management"])


# =============================================================================
# HTML Stripper Utility
# =============================================================================

class MLStripper(HTMLParser):
    """Strip HTML tags for character counting."""
    def __init__(self):
        super().__init__()
        self.reset()
        self.strict = False
        self.convert_charrefs = True
        self.fed = []

    def handle_data(self, d):
        self.fed.append(d)

    def get_data(self):
        return ''.join(self.fed)


# =============================================================================
# JOB DESCRIPTION ENDPOINTS
# =============================================================================

@router.get("/users/{user_id}/job-description", response_model=JobDescriptionResponse)
async def get_user_job_description(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get job description for a user."""
    try:
        # Authorization: Only allow managers or the user themselves
        if current_user.id != user_id and current_user.permission_role != 'management':
            raise HTTPException(status_code=403, detail="Insufficient permissions")

        # Get the most recent job description
        job_desc = db.query(UserJobDescription).filter(
            UserJobDescription.user_id == user_id
        ).order_by(UserJobDescription.updated_at.desc()).first()

        if not job_desc:
            raise HTTPException(status_code=404, detail="Job description not found")

        # Get updated_by user info
        updated_by_user = None
        if job_desc.updated_by_id:
            updated_by = db.query(User).filter(User.id == job_desc.updated_by_id).first()
            if updated_by:
                updated_by_user = {
                    "id": updated_by.id,
                    "name": updated_by.full_name or updated_by.email
                }

        return {
            "description": job_desc.description,
            "last_updated": job_desc.updated_at,
            "updated_by": updated_by_user
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get job description error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/users/{user_id}/job-description")
async def update_user_job_description(
    user_id: int,
    body: UpdateJobDescriptionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update job description for a user."""
    try:
        # Authorization: Only allow managers
        if current_user.permission_role != 'management':
            raise HTTPException(status_code=403, detail="Only managers can update job descriptions")

        # Validate description length (5000 characters)
        # Strip HTML for character count
        stripper = MLStripper()
        stripper.feed(body.description)
        plain_text = stripper.get_data()

        if len(plain_text) > 5000:
            raise HTTPException(status_code=400, detail="Description exceeds 5000 character limit")

        # Check if job description exists
        existing = db.query(UserJobDescription).filter(
            UserJobDescription.user_id == user_id
        ).order_by(UserJobDescription.updated_at.desc()).first()

        if existing:
            # Update existing
            existing.description = body.description
            existing.updated_by_id = current_user.id
            existing.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(existing)
            job_desc = existing
        else:
            # Create new
            job_desc = UserJobDescription(
                user_id=user_id,
                description=body.description,
                updated_by_id=current_user.id
            )
            db.add(job_desc)
            db.commit()
            db.refresh(job_desc)

        return {
            "success": True,
            "updated_at": job_desc.updated_at
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update job description error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# SKILLS LIBRARY ENDPOINTS
# =============================================================================

@router.get("/skills/library", response_model=List[SkillResponse])
async def get_skills_library(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all skills from the company-wide skills library."""
    try:
        skills = db.query(Skill).order_by(Skill.name).all()

        return [
            {
                "id": skill.id,
                "name": skill.name,
                "category": skill.category,
                "description": skill.description
            }
            for skill in skills
        ]

    except Exception as e:
        logger.error(f"Get skills library error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/skills/library", response_model=SkillResponse)
async def create_skill(
    body: SkillCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Add a new skill to the company-wide library."""
    try:
        # Authorization: Only allow managers
        if current_user.permission_role != 'management':
            raise HTTPException(status_code=403, detail="Only managers can add skills to the library")

        # Check if skill already exists
        existing = db.query(Skill).filter(Skill.name == body.name).first()
        if existing:
            raise HTTPException(status_code=400, detail="Skill with this name already exists")

        # Create new skill
        skill = Skill(
            name=body.name,
            category=body.category,
            description=body.description
        )
        db.add(skill)
        db.commit()
        db.refresh(skill)

        return {
            "id": skill.id,
            "name": skill.name,
            "category": skill.category,
            "description": skill.description
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create skill error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# RESPONSIBILITIES ENDPOINTS
# =============================================================================

@router.get("/users/{user_id}/responsibilities")
async def get_user_responsibilities(
    user_id: int,
    include_archived: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all responsibilities for a user."""
    try:
        # Authorization: Only allow managers or the user themselves
        if current_user.id != user_id and current_user.permission_role != 'management':
            raise HTTPException(status_code=403, detail="Insufficient permissions")

        # Build query
        query = db.query(UserResponsibility).filter(
            UserResponsibility.user_id == user_id
        )

        if not include_archived:
            query = query.filter(UserResponsibility.archived == False)

        responsibilities = query.order_by(UserResponsibility.display_order).all()

        # Get archived count
        archived_count = db.query(UserResponsibility).filter(
            UserResponsibility.user_id == user_id,
            UserResponsibility.archived == True
        ).count()

        # Calculate total time allocation
        total_allocation = sum(r.time_allocation or 0 for r in responsibilities if not r.archived)

        # Format response with skills populated
        resp_list = []
        for resp in responsibilities:
            # Get skills for this responsibility
            skills_query = db.query(Skill).join(
                ResponsibilitySkill,
                ResponsibilitySkill.skill_id == Skill.id
            ).filter(
                ResponsibilitySkill.responsibility_id == resp.id
            ).all()

            resp_list.append({
                "id": resp.id,
                "title": resp.title,
                "description": resp.description,
                "ownership": resp.ownership,
                "time_allocation": resp.time_allocation,
                "priority": resp.priority,
                "effective_date": resp.effective_date.isoformat() if resp.effective_date else None,
                "end_date": resp.end_date.isoformat() if resp.end_date else None,
                "archived": resp.archived,
                "display_order": resp.display_order,
                "required_skills": [
                    {
                        "id": skill.id,
                        "name": skill.name,
                        "category": skill.category,
                        "description": skill.description
                    }
                    for skill in skills_query
                ]
            })

        return {
            "responsibilities": resp_list,
            "total_allocation": total_allocation,
            "archived_count": archived_count
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get responsibilities error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/users/{user_id}/responsibilities")
async def create_responsibility(
    user_id: int,
    body: CreateResponsibilityRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new responsibility for a user."""
    try:
        # Authorization: Only allow managers
        if current_user.permission_role != 'management':
            raise HTTPException(status_code=403, detail="Only managers can create responsibilities")

        # Validate
        if not body.title:
            raise HTTPException(status_code=400, detail="Title is required")

        if body.time_allocation is not None and (body.time_allocation < 0 or body.time_allocation > 100):
            raise HTTPException(status_code=400, detail="Time allocation must be between 0 and 100")

        if body.ownership not in ['primary', 'secondary', 'shared']:
            raise HTTPException(status_code=400, detail="Ownership must be primary, secondary, or shared")

        if body.priority not in ['critical', 'high', 'medium', 'low']:
            raise HTTPException(status_code=400, detail="Priority must be critical, high, medium, or low")

        # Parse dates
        effective_date = dt_date.fromisoformat(body.effective_date) if body.effective_date else None
        end_date = dt_date.fromisoformat(body.end_date) if body.end_date else None

        # Get next display_order
        max_order = db.query(func.max(UserResponsibility.display_order)).filter(
            UserResponsibility.user_id == user_id,
            UserResponsibility.archived == False
        ).scalar() or 0

        # Create responsibility
        responsibility = UserResponsibility(
            user_id=user_id,
            title=body.title,
            description=body.description,
            ownership=body.ownership,
            time_allocation=body.time_allocation,
            priority=body.priority,
            effective_date=effective_date,
            end_date=end_date,
            archived=False,
            display_order=max_order + 1,
            created_by_id=current_user.id
        )
        db.add(responsibility)
        db.flush()  # Get the ID

        # Add skills
        if body.required_skills:
            for skill_id in body.required_skills:
                resp_skill = ResponsibilitySkill(
                    responsibility_id=responsibility.id,
                    skill_id=skill_id
                )
                db.add(resp_skill)

        db.commit()
        db.refresh(responsibility)

        # Get skills for response
        skills_query = db.query(Skill).join(
            ResponsibilitySkill,
            ResponsibilitySkill.skill_id == Skill.id
        ).filter(
            ResponsibilitySkill.responsibility_id == responsibility.id
        ).all()

        return {
            "id": responsibility.id,
            "title": responsibility.title,
            "description": responsibility.description,
            "ownership": responsibility.ownership,
            "time_allocation": responsibility.time_allocation,
            "priority": responsibility.priority,
            "effective_date": responsibility.effective_date.isoformat() if responsibility.effective_date else None,
            "end_date": responsibility.end_date.isoformat() if responsibility.end_date else None,
            "archived": responsibility.archived,
            "display_order": responsibility.display_order,
            "required_skills": [
                {
                    "id": skill.id,
                    "name": skill.name,
                    "category": skill.category,
                    "description": skill.description
                }
                for skill in skills_query
            ]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create responsibility error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/users/{user_id}/responsibilities/{resp_id}")
async def update_responsibility(
    user_id: int,
    resp_id: int,
    body: UpdateResponsibilityRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a responsibility."""
    try:
        # Authorization: Only allow managers
        if current_user.permission_role != 'management':
            raise HTTPException(status_code=403, detail="Only managers can update responsibilities")

        # Get responsibility
        responsibility = db.query(UserResponsibility).filter(
            UserResponsibility.id == resp_id,
            UserResponsibility.user_id == user_id
        ).first()

        if not responsibility:
            raise HTTPException(status_code=404, detail="Responsibility not found")

        # Update fields
        if body.title is not None:
            responsibility.title = body.title

        if body.description is not None:
            responsibility.description = body.description

        if body.ownership is not None:
            if body.ownership not in ['primary', 'secondary', 'shared']:
                raise HTTPException(status_code=400, detail="Invalid ownership value")
            responsibility.ownership = body.ownership

        if body.time_allocation is not None:
            if body.time_allocation < 0 or body.time_allocation > 100:
                raise HTTPException(status_code=400, detail="Time allocation must be between 0 and 100")
            responsibility.time_allocation = body.time_allocation

        if body.priority is not None:
            if body.priority not in ['critical', 'high', 'medium', 'low']:
                raise HTTPException(status_code=400, detail="Invalid priority value")
            responsibility.priority = body.priority

        if body.effective_date is not None:
            responsibility.effective_date = dt_date.fromisoformat(body.effective_date)

        if body.end_date is not None:
            responsibility.end_date = dt_date.fromisoformat(body.end_date) if body.end_date else None

        # Update skills if provided
        if body.required_skills is not None:
            # Remove existing skills
            db.query(ResponsibilitySkill).filter(
                ResponsibilitySkill.responsibility_id == resp_id
            ).delete()

            # Add new skills
            for skill_id in body.required_skills:
                resp_skill = ResponsibilitySkill(
                    responsibility_id=resp_id,
                    skill_id=skill_id
                )
                db.add(resp_skill)

        responsibility.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(responsibility)

        # Get skills for response
        skills_query = db.query(Skill).join(
            ResponsibilitySkill,
            ResponsibilitySkill.skill_id == Skill.id
        ).filter(
            ResponsibilitySkill.responsibility_id == resp_id
        ).all()

        return {
            "id": responsibility.id,
            "title": responsibility.title,
            "description": responsibility.description,
            "ownership": responsibility.ownership,
            "time_allocation": responsibility.time_allocation,
            "priority": responsibility.priority,
            "effective_date": responsibility.effective_date.isoformat() if responsibility.effective_date else None,
            "end_date": responsibility.end_date.isoformat() if responsibility.end_date else None,
            "archived": responsibility.archived,
            "display_order": responsibility.display_order,
            "required_skills": [
                {
                    "id": skill.id,
                    "name": skill.name,
                    "category": skill.category,
                    "description": skill.description
                }
                for skill in skills_query
            ]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update responsibility error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/users/{user_id}/responsibilities/{resp_id}")
async def archive_responsibility(
    user_id: int,
    resp_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Archive a responsibility (soft delete)."""
    try:
        # Authorization: Only allow managers
        if current_user.permission_role != 'management':
            raise HTTPException(status_code=403, detail="Only managers can archive responsibilities")

        # Get responsibility
        responsibility = db.query(UserResponsibility).filter(
            UserResponsibility.id == resp_id,
            UserResponsibility.user_id == user_id
        ).first()

        if not responsibility:
            raise HTTPException(status_code=404, detail="Responsibility not found")

        # Archive it
        responsibility.archived = True
        responsibility.updated_at = datetime.now(timezone.utc)
        db.commit()

        return {
            "success": True,
            "message": "Responsibility archived successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Archive responsibility error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/users/{user_id}/responsibilities/archived")
async def get_archived_responsibilities(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get archived responsibilities for a user."""
    try:
        # Authorization: Only allow managers or the user themselves
        if current_user.id != user_id and current_user.permission_role != 'management':
            raise HTTPException(status_code=403, detail="Insufficient permissions")

        archived = db.query(UserResponsibility).filter(
            UserResponsibility.user_id == user_id,
            UserResponsibility.archived == True
        ).order_by(UserResponsibility.updated_at.desc()).all()

        resp_list = []
        for resp in archived:
            # Get skills
            skills_query = db.query(Skill).join(
                ResponsibilitySkill,
                ResponsibilitySkill.skill_id == Skill.id
            ).filter(
                ResponsibilitySkill.responsibility_id == resp.id
            ).all()

            resp_list.append({
                "id": resp.id,
                "title": resp.title,
                "description": resp.description,
                "ownership": resp.ownership,
                "time_allocation": resp.time_allocation,
                "priority": resp.priority,
                "effective_date": resp.effective_date.isoformat() if resp.effective_date else None,
                "end_date": resp.end_date.isoformat() if resp.end_date else None,
                "archived": resp.archived,
                "display_order": resp.display_order,
                "required_skills": [
                    {
                        "id": skill.id,
                        "name": skill.name,
                        "category": skill.category,
                        "description": skill.description
                    }
                    for skill in skills_query
                ]
            })

        return resp_list

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get archived responsibilities error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/users/{user_id}/responsibilities/{resp_id}/restore")
async def restore_responsibility(
    user_id: int,
    resp_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Restore an archived responsibility."""
    try:
        # Authorization: Only allow managers
        if current_user.permission_role != 'management':
            raise HTTPException(status_code=403, detail="Only managers can restore responsibilities")

        # Get responsibility
        responsibility = db.query(UserResponsibility).filter(
            UserResponsibility.id == resp_id,
            UserResponsibility.user_id == user_id
        ).first()

        if not responsibility:
            raise HTTPException(status_code=404, detail="Responsibility not found")

        # Restore it
        responsibility.archived = False
        responsibility.updated_at = datetime.now(timezone.utc)
        db.commit()

        return {
            "success": True,
            "message": "Responsibility restored successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Restore responsibility error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/users/{user_id}/responsibilities/reorder")
async def reorder_responsibilities(
    user_id: int,
    body: ReorderResponsibilitiesRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Reorder responsibilities by updating display_order."""
    try:
        # Authorization: Only allow managers
        if current_user.permission_role != 'management':
            raise HTTPException(status_code=403, detail="Only managers can reorder responsibilities")

        # Update display_order for each responsibility in the new order
        for index, resp_id in enumerate(body.order):
            responsibility = db.query(UserResponsibility).filter(
                UserResponsibility.id == resp_id,
                UserResponsibility.user_id == user_id
            ).first()

            if responsibility:
                responsibility.display_order = index
                responsibility.updated_at = datetime.now(timezone.utc)

        db.commit()

        return {
            "success": True,
            "message": "Responsibilities reordered successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Reorder responsibilities error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# GOALS & OKRs ENDPOINTS
# =============================================================================

@router.get("/users/{user_id}/goals")
async def get_user_goals(
    user_id: int,
    period: Optional[str] = None,
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all goals for a user with key results, assessments, and linked responsibilities."""
    try:
        # Authorization: Only allow managers or the user themselves
        if current_user.id != user_id and current_user.permission_role != 'management':
            raise HTTPException(status_code=403, detail="Insufficient permissions")

        # Build query
        query = db.query(UserGoal).filter(UserGoal.user_id == user_id)

        # Filter by period if provided
        if period and period != 'all':
            from datetime import date
            today = date.today()

            if period == 'current':
                # Goals that are currently active
                query = query.filter(
                    UserGoal.start_date <= today,
                    or_(UserGoal.end_date >= today, UserGoal.end_date == None)
                )
            elif period.startswith('q'):
                # Quarter filter like "q4_2025"
                parts = period.split('_')
                if len(parts) == 2:
                    quarter = int(parts[0][1])  # Extract quarter number
                    year = int(parts[1])
                    # Calculate quarter date range
                    q_start = date(year, (quarter-1)*3 + 1, 1)
                    if quarter == 4:
                        q_end = date(year, 12, 31)
                    else:
                        q_end = date(year, quarter*3, 28)  # Approximate
                    query = query.filter(
                        UserGoal.start_date <= q_end,
                        UserGoal.end_date >= q_start
                    )
            elif period.isdigit():
                # Year filter like "2025"
                year = int(period)
                query = query.filter(
                    func.extract('year', UserGoal.start_date) == year
                )

        # Filter by status if provided
        if status and status != 'all':
            if status == 'active':
                query = query.filter(UserGoal.status.in_(['not_started', 'on_track', 'at_risk', 'blocked']))
            elif status == 'completed':
                query = query.filter(UserGoal.status == 'completed')
            else:
                query = query.filter(UserGoal.status == status)

        goals = query.order_by(UserGoal.start_date.desc()).all()

        # Format response with all related data
        goals_list = []
        for goal in goals:
            # Get key results
            key_results = db.query(GoalKeyResult).filter(
                GoalKeyResult.goal_id == goal.id
            ).all()

            # Get employee assessment
            employee_assessment = db.query(GoalEmployeeAssessment).filter(
                GoalEmployeeAssessment.goal_id == goal.id
            ).first()

            # Get manager assessment
            manager_assessment = db.query(GoalManagerAssessment).filter(
                GoalManagerAssessment.goal_id == goal.id
            ).first()

            # Get linked responsibilities
            linked_resp = db.query(UserResponsibility).join(
                GoalResponsibility,
                GoalResponsibility.responsibility_id == UserResponsibility.id
            ).filter(
                GoalResponsibility.goal_id == goal.id
            ).all()

            goals_list.append({
                "id": goal.id,
                "objective": goal.objective,
                "start_date": goal.start_date.isoformat() if goal.start_date else None,
                "end_date": goal.end_date.isoformat() if goal.end_date else None,
                "status": goal.status,
                "created_by_id": goal.created_by_id,
                "created_at": goal.created_at.isoformat() if goal.created_at else None,
                "updated_at": goal.updated_at.isoformat() if goal.updated_at else None,
                "key_results": [
                    {
                        "id": kr.id,
                        "metric": kr.metric,
                        "target": kr.target,
                        "current": kr.current,
                        "unit": kr.unit,
                        "status": kr.status
                    }
                    for kr in key_results
                ],
                "employee_assessment": {
                    "progress_percent": employee_assessment.progress_percent,
                    "status": employee_assessment.status,
                    "achievements": employee_assessment.achievements,
                    "challenges": employee_assessment.challenges,
                    "support_needed": employee_assessment.support_needed,
                    "updated_at": employee_assessment.updated_at.isoformat() if employee_assessment.updated_at else None
                } if employee_assessment else None,
                "manager_assessment": {
                    "notes": manager_assessment.notes,
                    "updated_by_id": manager_assessment.updated_by_id,
                    "updated_at": manager_assessment.updated_at.isoformat() if manager_assessment.updated_at else None
                } if manager_assessment else None,
                "linked_responsibilities": [
                    {
                        "id": resp.id,
                        "title": resp.title
                    }
                    for resp in linked_resp
                ]
            })

        return {"goals": goals_list}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get goals error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/users/{user_id}/goals")
async def create_goal(
    user_id: int,
    body: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a new goal with key results.
    Body: {
        "objective": str,
        "start_date": str (ISO),
        "end_date": str (ISO),
        "key_results": [{"metric": str, "target": float, "unit": str}],
        "linked_responsibilities": [int] (optional)
    }
    """
    try:
        # Authorization: Only managers can create goals
        if current_user.permission_role != 'management':
            raise HTTPException(status_code=403, detail="Only managers can create goals")

        # Validate required fields
        if not body.get('objective'):
            raise HTTPException(status_code=400, detail="Objective is required")
        if not body.get('start_date'):
            raise HTTPException(status_code=400, detail="Start date is required")
        if not body.get('end_date'):
            raise HTTPException(status_code=400, detail="End date is required")
        if not body.get('key_results') or len(body.get('key_results', [])) == 0:
            raise HTTPException(status_code=400, detail="At least 1 key result is required")
        if len(body.get('key_results', [])) > 5:
            raise HTTPException(status_code=400, detail="Maximum 5 key results allowed")

        # Parse dates
        from datetime import datetime as dt
        start_date = dt.fromisoformat(body['start_date'].replace('Z', '+00:00')).date()
        end_date = dt.fromisoformat(body['end_date'].replace('Z', '+00:00')).date()

        if start_date >= end_date:
            raise HTTPException(status_code=400, detail="Start date must be before end date")

        # Create goal
        goal = UserGoal(
            user_id=user_id,
            objective=body['objective'],
            start_date=start_date,
            end_date=end_date,
            status='not_started',
            created_by_id=current_user.id
        )
        db.add(goal)
        db.flush()  # Get the goal ID

        # Create key results
        for kr_data in body['key_results']:
            if not kr_data.get('metric') or kr_data.get('target') is None:
                raise HTTPException(status_code=400, detail="Each key result must have metric and target")

            kr = GoalKeyResult(
                goal_id=goal.id,
                metric=kr_data['metric'],
                target=float(kr_data['target']),
                current=float(kr_data.get('current', 0)),
                unit=kr_data.get('unit'),
                status='not_started'
            )
            db.add(kr)

        # Link responsibilities if provided
        if body.get('linked_responsibilities'):
            for resp_id in body['linked_responsibilities']:
                # Verify responsibility exists and belongs to user
                resp = db.query(UserResponsibility).filter(
                    UserResponsibility.id == resp_id,
                    UserResponsibility.user_id == user_id
                ).first()
                if resp:
                    link = GoalResponsibility(
                        goal_id=goal.id,
                        responsibility_id=resp_id
                    )
                    db.add(link)

        db.commit()
        db.refresh(goal)

        return {
            "success": True,
            "goal_id": goal.id,
            "message": "Goal created successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create goal error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/users/{user_id}/goals/{goal_id}")
async def update_goal(
    user_id: int,
    goal_id: int,
    body: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a goal's objective, dates, or status."""
    try:
        # Authorization: Only managers can update goals
        if current_user.permission_role != 'management':
            raise HTTPException(status_code=403, detail="Only managers can update goals")

        # Get goal
        goal = db.query(UserGoal).filter(
            UserGoal.id == goal_id,
            UserGoal.user_id == user_id
        ).first()

        if not goal:
            raise HTTPException(status_code=404, detail="Goal not found")

        # Update fields
        if 'objective' in body:
            goal.objective = body['objective']

        if 'start_date' in body:
            from datetime import datetime as dt
            goal.start_date = dt.fromisoformat(body['start_date'].replace('Z', '+00:00')).date()

        if 'end_date' in body:
            from datetime import datetime as dt
            goal.end_date = dt.fromisoformat(body['end_date'].replace('Z', '+00:00')).date()

        if 'status' in body:
            if body['status'] not in ['not_started', 'on_track', 'at_risk', 'blocked', 'completed']:
                raise HTTPException(status_code=400, detail="Invalid status")
            goal.status = body['status']

        goal.updated_at = datetime.now(timezone.utc)
        db.commit()

        return {
            "success": True,
            "message": "Goal updated successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update goal error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/users/{user_id}/goals/{goal_id}")
async def delete_goal(
    user_id: int,
    goal_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a goal (hard delete with cascade)."""
    try:
        # Authorization: Only managers can delete goals
        if current_user.permission_role != 'management':
            raise HTTPException(status_code=403, detail="Only managers can delete goals")

        # Get goal
        goal = db.query(UserGoal).filter(
            UserGoal.id == goal_id,
            UserGoal.user_id == user_id
        ).first()

        if not goal:
            raise HTTPException(status_code=404, detail="Goal not found")

        # Delete goal (cascade will delete key results and assessments)
        db.delete(goal)
        db.commit()

        return {
            "success": True,
            "message": "Goal deleted successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete goal error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/users/{user_id}/goals/{goal_id}/key-results/{kr_id}")
async def update_key_result(
    user_id: int,
    goal_id: int,
    kr_id: int,
    body: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update key result progress.
    Body: { "current": float }
    Auto-calculates status based on progress.
    """
    try:
        # Authorization: Managers or the user can update
        if current_user.id != user_id and current_user.permission_role != 'management':
            raise HTTPException(status_code=403, detail="Insufficient permissions")

        # Verify goal exists and belongs to user
        goal = db.query(UserGoal).filter(
            UserGoal.id == goal_id,
            UserGoal.user_id == user_id
        ).first()
        if not goal:
            raise HTTPException(status_code=404, detail="Goal not found")

        # Get key result
        kr = db.query(GoalKeyResult).filter(
            GoalKeyResult.id == kr_id,
            GoalKeyResult.goal_id == goal_id
        ).first()

        if not kr:
            raise HTTPException(status_code=404, detail="Key result not found")

        # Update current value
        if 'current' in body:
            kr.current = float(body['current'])

            # Auto-calculate status based on progress
            if kr.target > 0:
                progress_pct = (kr.current / kr.target) * 100
                if progress_pct >= 100:
                    kr.status = 'completed'
                elif progress_pct >= 90:
                    kr.status = 'ahead'
                elif progress_pct >= 50:
                    kr.status = 'on_track'
                elif progress_pct >= 25:
                    kr.status = 'at_risk'
                else:
                    kr.status = 'not_started' if progress_pct == 0 else 'at_risk'

        db.commit()

        return {
            "success": True,
            "current": kr.current,
            "status": kr.status,
            "message": "Key result updated successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update key result error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/users/{user_id}/goals/{goal_id}/self-assess")
async def employee_self_assess(
    user_id: int,
    goal_id: int,
    body: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create or update employee self-assessment.
    Body: {
        "progress_percent": int (0-100),
        "status": str,
        "achievements": str,
        "challenges": str,
        "support_needed": str
    }
    """
    try:
        # Authorization: Only the employee can self-assess
        if current_user.id != user_id:
            raise HTTPException(status_code=403, detail="You can only assess your own goals")

        # Verify goal exists and belongs to user
        goal = db.query(UserGoal).filter(
            UserGoal.id == goal_id,
            UserGoal.user_id == user_id
        ).first()
        if not goal:
            raise HTTPException(status_code=404, detail="Goal not found")

        # Validate progress_percent
        if 'progress_percent' in body:
            pct = body['progress_percent']
            if pct < 0 or pct > 100:
                raise HTTPException(status_code=400, detail="Progress percent must be between 0 and 100")

        # Check if assessment exists
        assessment = db.query(GoalEmployeeAssessment).filter(
            GoalEmployeeAssessment.goal_id == goal_id
        ).first()

        if assessment:
            # Update existing assessment
            if 'progress_percent' in body:
                assessment.progress_percent = body['progress_percent']
            if 'status' in body:
                if body['status'] not in ['on_track', 'at_risk', 'blocked']:
                    raise HTTPException(status_code=400, detail="Invalid status")
                assessment.status = body['status']
            if 'achievements' in body:
                assessment.achievements = body['achievements']
            if 'challenges' in body:
                assessment.challenges = body['challenges']
            if 'support_needed' in body:
                assessment.support_needed = body['support_needed']
            assessment.updated_at = datetime.now(timezone.utc)
        else:
            # Create new assessment
            assessment = GoalEmployeeAssessment(
                goal_id=goal_id,
                progress_percent=body.get('progress_percent'),
                status=body.get('status', 'on_track'),
                achievements=body.get('achievements'),
                challenges=body.get('challenges'),
                support_needed=body.get('support_needed')
            )
            db.add(assessment)

        db.commit()

        return {
            "success": True,
            "message": "Self-assessment saved successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Self-assess error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/users/{user_id}/goals/{goal_id}/manager-assess")
async def manager_assess(
    user_id: int,
    goal_id: int,
    body: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create or update manager assessment.
    Body: { "notes": str }
    """
    try:
        # Authorization: Only managers can assess
        if current_user.permission_role != 'management':
            raise HTTPException(status_code=403, detail="Only managers can provide assessments")

        # Verify goal exists and belongs to user
        goal = db.query(UserGoal).filter(
            UserGoal.id == goal_id,
            UserGoal.user_id == user_id
        ).first()
        if not goal:
            raise HTTPException(status_code=404, detail="Goal not found")

        # Check if assessment exists
        assessment = db.query(GoalManagerAssessment).filter(
            GoalManagerAssessment.goal_id == goal_id
        ).first()

        if assessment:
            # Update existing assessment
            assessment.notes = body.get('notes', '')
            assessment.updated_by_id = current_user.id
            assessment.updated_at = datetime.now(timezone.utc)
        else:
            # Create new assessment
            assessment = GoalManagerAssessment(
                goal_id=goal_id,
                notes=body.get('notes', ''),
                updated_by_id=current_user.id
            )
            db.add(assessment)

        db.commit()

        return {
            "success": True,
            "message": "Manager assessment saved successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Manager assess error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# SKILLS ASSESSMENT ENDPOINTS
# =============================================================================

@router.get("/users/{user_id}/skills")
async def get_user_skills(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all skill assessments for a user with summary statistics."""
    try:
        # Authorization: Only allow managers or the user themselves
        if current_user.id != user_id and current_user.permission_role != 'management':
            raise HTTPException(status_code=403, detail="Insufficient permissions")

        # Get all skill assessments for the user
        assessments = db.query(UserSkillAssessment).filter(
            UserSkillAssessment.user_id == user_id
        ).all()

        # Format response with skill details
        skills_list = []
        for assessment in assessments:
            # Get skill details
            skill = db.query(Skill).filter(Skill.id == assessment.skill_id).first()
            if not skill:
                continue

            # Calculate gap (negative means skill gap, positive means exceeding)
            gap = assessment.current_proficiency - assessment.required_proficiency

            skills_list.append({
                "id": assessment.id,
                "skill_id": assessment.skill_id,
                "skill_name": skill.name,
                "skill_category": skill.category,
                "required_proficiency": assessment.required_proficiency,
                "current_proficiency": assessment.current_proficiency,
                "gap": gap,
                "assessment_notes": assessment.assessment_notes,
                "training_recommendations": assessment.training_recommendations or [],
                "assessed_by_id": assessment.assessed_by_id,
                "assessed_at": assessment.assessed_at.isoformat() if assessment.assessed_at else None,
                "next_assessment_date": assessment.next_assessment_date.isoformat() if assessment.next_assessment_date else None,
                "created_at": assessment.created_at.isoformat() if assessment.created_at else None,
                "updated_at": assessment.updated_at.isoformat() if assessment.updated_at else None
            })

        # Calculate summary statistics
        total_skills = len(skills_list)
        assessed_skills = len([s for s in skills_list if s['current_proficiency'] > 0])
        meeting_requirements = len([s for s in skills_list if s['gap'] >= 0 and s['current_proficiency'] > 0])
        with_gaps = len([s for s in skills_list if s['gap'] < 0])

        average_proficiency = 0
        if assessed_skills > 0:
            total_current = sum(s['current_proficiency'] for s in skills_list if s['current_proficiency'] > 0)
            average_proficiency = total_current / assessed_skills

        summary = {
            "total_skills": total_skills,
            "assessed_skills": assessed_skills,
            "meeting_requirements": meeting_requirements,
            "with_gaps": with_gaps,
            "average_proficiency": round(average_proficiency, 2)
        }

        return {
            "skills": skills_list,
            "summary": summary
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get user skills error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/users/{user_id}/skills")
async def add_user_skill(
    user_id: int,
    body: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Add a skill to user's assessment matrix.
    Body: { "skill_id": int, "required_proficiency": int (1-5) }
    """
    try:
        # Authorization: Only managers can add skills
        if current_user.permission_role != 'management':
            raise HTTPException(status_code=403, detail="Only managers can add skills")

        # Validate required fields
        if not body.get('skill_id'):
            raise HTTPException(status_code=400, detail="skill_id is required")
        if not body.get('required_proficiency'):
            raise HTTPException(status_code=400, detail="required_proficiency is required")

        skill_id = int(body['skill_id'])
        required_proficiency = int(body['required_proficiency'])

        # Validate proficiency level
        if required_proficiency < 1 or required_proficiency > 5:
            raise HTTPException(status_code=400, detail="required_proficiency must be between 1 and 5")

        # Verify skill exists
        skill = db.query(Skill).filter(Skill.id == skill_id).first()
        if not skill:
            raise HTTPException(status_code=404, detail="Skill not found")

        # Check if assessment already exists
        existing = db.query(UserSkillAssessment).filter(
            UserSkillAssessment.user_id == user_id,
            UserSkillAssessment.skill_id == skill_id
        ).first()

        if existing:
            raise HTTPException(status_code=400, detail="This skill is already in the assessment matrix")

        # Create new assessment
        assessment = UserSkillAssessment(
            user_id=user_id,
            skill_id=skill_id,
            required_proficiency=required_proficiency,
            current_proficiency=0  # Not assessed yet
        )
        db.add(assessment)
        db.commit()
        db.refresh(assessment)

        return {
            "success": True,
            "assessment_id": assessment.id,
            "message": "Skill added to assessment matrix"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Add user skill error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/users/{user_id}/skills/{skill_id}/assess")
async def assess_skill(
    user_id: int,
    skill_id: int,
    body: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Assess a user's skill proficiency.
    Body: {
        "current_proficiency": int (1-5),
        "assessment_notes": str (optional),
        "training_recommendations": list (optional),
        "next_assessment_date": str (ISO date, optional)
    }
    """
    try:
        # Authorization: Only managers can assess
        if current_user.permission_role != 'management':
            raise HTTPException(status_code=403, detail="Only managers can assess skills")

        # Get the assessment
        assessment = db.query(UserSkillAssessment).filter(
            UserSkillAssessment.user_id == user_id,
            UserSkillAssessment.skill_id == skill_id
        ).first()

        if not assessment:
            raise HTTPException(status_code=404, detail="Skill not found in assessment matrix")

        # Validate current_proficiency
        if 'current_proficiency' in body:
            current_prof = int(body['current_proficiency'])
            if current_prof < 1 or current_prof > 5:
                raise HTTPException(status_code=400, detail="current_proficiency must be between 1 and 5")
            assessment.current_proficiency = current_prof

        # Update assessment details
        if 'assessment_notes' in body:
            assessment.assessment_notes = body['assessment_notes']

        if 'training_recommendations' in body:
            assessment.training_recommendations = body['training_recommendations']

        if 'next_assessment_date' in body and body['next_assessment_date']:
            from datetime import datetime as dt
            assessment.next_assessment_date = dt.fromisoformat(body['next_assessment_date'].replace('Z', '+00:00')).date()

        # Update assessment metadata
        assessment.assessed_by_id = current_user.id
        assessment.assessed_at = datetime.now(timezone.utc)
        assessment.updated_at = datetime.now(timezone.utc)

        db.commit()

        return {
            "success": True,
            "message": "Skill assessment saved successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Assess skill error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/users/{user_id}/skills/{skill_id}")
async def remove_user_skill(
    user_id: int,
    skill_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Remove a skill from user's assessment matrix."""
    try:
        # Authorization: Only managers can remove skills
        if current_user.permission_role != 'management':
            raise HTTPException(status_code=403, detail="Only managers can remove skills")

        # Get the assessment
        assessment = db.query(UserSkillAssessment).filter(
            UserSkillAssessment.user_id == user_id,
            UserSkillAssessment.skill_id == skill_id
        ).first()

        if not assessment:
            raise HTTPException(status_code=404, detail="Skill not found in assessment matrix")

        # Delete the assessment
        db.delete(assessment)
        db.commit()

        return {
            "success": True,
            "message": "Skill removed from assessment matrix"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Remove user skill error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")
