"""
Onboarding Routes - Endpoints for user onboarding, team management, and impersonation
"""
import json
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from db import get_db

logger = logging.getLogger(__name__)


def _extract_token(request) -> str:
    """Extract Bearer token from Authorization header."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    from fastapi import HTTPException
    raise HTTPException(status_code=401, detail="Not authenticated")


router = APIRouter(prefix="/api/v1/onboarding", tags=["Onboarding"])

# Secondary router for team endpoints
team_router = APIRouter(prefix="/api/v1/team", tags=["Team"])

# Secondary router for impersonation endpoints
impersonation_router = APIRouter(prefix="/api/v1/impersonation", tags=["Impersonation"])

# Public router for invite validation (no prefix - frontend expects /api/invite/{token})
invite_router = APIRouter(tags=["Invites"])


def get_current_user_dep():
    """Get current user dependency - imports from main at runtime to avoid circular imports"""
    import main
    return main.get_current_user


def get_models():
    """Get models at runtime to avoid circular imports"""
    import main
    return {
        'User': main.User,
        'OnboardingStep': main.OnboardingStep,
        'OnboardingProgress': main.OnboardingProgress,
        'ProcessRole': main.ProcessRole,
        'ProcessMilestone': main.ProcessMilestone,
        'ProcessTask': main.ProcessTask,
        'ImpersonationSession': main.ImpersonationSession,
    }


def get_schemas():
    """Get Pydantic schemas at runtime to avoid circular imports"""
    import main
    return {
        'DocumentParseRequest': main.DocumentParseRequest,
        'ProcessRoleResponse': main.ProcessRoleResponse,
        'ProcessMilestoneResponse': main.ProcessMilestoneResponse,
        'ProcessTaskResponse': main.ProcessTaskResponse,
        'TeamMemberCreate': main.TeamMemberCreate,
        'TeamMemberUpdate': main.TeamMemberUpdate,
        'ImpersonationStart': main.ImpersonationStart,
        'ImpersonationResponse': main.ImpersonationResponse,
    }


def get_openai_client():
    """Get OpenAI client at runtime"""
    import main
    return getattr(main, 'openai_client', None)


def get_password_hash_func():
    """Get password hash function at runtime"""
    import main
    return main.get_password_hash


def parse_document_basic(document_content: str, document_name: str = None):
    """
    Basic text-based document parser (fallback when OpenAI is not available).
    Extracts roles, milestones, and tasks using keyword matching.
    """
    lines = document_content.split('\n')

    # Extract role from document name or content
    role_name = "application_analyst" if "application" in document_content.lower()[:500] else "loan_specialist"
    role_title = role_name.replace('_', ' ').title()

    # Look for role indicators in first 1000 chars
    content_start = document_content[:1000].lower()
    if "application analysis" in content_start:
        role_name = "application_analyst"
        role_title = "Application Analyst"
    elif "loan officer" in content_start:
        role_name = "loan_officer"
        role_title = "Loan Officer"
    elif "processor" in content_start:
        role_name = "loan_processor"
        role_title = "Loan Processor"

    # Extract milestones (sections with "Checklist" or major headings)
    milestones = []
    milestone_pattern = r'(Pre-Call|During|Post-Call|Before|After|Step \d+|Phase \d+).*?(Checklist|Process|Stage|Milestone)'

    for i, line in enumerate(lines):
        if re.search(milestone_pattern, line, re.IGNORECASE) or (line.isupper() and len(line) > 5 and len(line) < 50):
            milestone_name = line.strip()
            if milestone_name and len(milestone_name) > 3:
                milestones.append({
                    "name": milestone_name[:50],  # Limit length
                    "description": f"Milestone extracted from document",
                    "sequence_order": len(milestones),
                    "estimated_duration": 2
                })

    # If no milestones found, create default ones
    if not milestones:
        milestones = [
            {"name": "Preparation", "description": "Initial preparation phase", "sequence_order": 0, "estimated_duration": 1},
            {"name": "Execution", "description": "Main execution phase", "sequence_order": 1, "estimated_duration": 2},
            {"name": "Follow-up", "description": "Follow-up and completion", "sequence_order": 2, "estimated_duration": 1}
        ]

    # Extract tasks (numbered items or items starting with verbs)
    tasks = []
    task_pattern = r'^\s*(\d+\.|\d+\)|-|•|[a-z]\.|[a-z]\))\s*(.+)$'
    current_milestone = milestones[0]["name"] if milestones else "General"

    for line in lines:
        # Check if line is a milestone header
        for milestone in milestones:
            if milestone["name"].lower() in line.lower() and len(line) < 100:
                current_milestone = milestone["name"]
                break

        # Extract tasks
        match = re.match(task_pattern, line.strip())
        if match and len(match.group(2)) > 10:
            task_text = match.group(2).strip()
            # Only include substantial tasks
            if len(task_text) > 15 and not task_text.endswith(':'):
                tasks.append({
                    "milestone": current_milestone,
                    "role": role_name,
                    "task_name": task_text[:100],  # First 100 chars as name
                    "task_description": task_text,
                    "sequence_order": len([t for t in tasks if t["milestone"] == current_milestone]),
                    "estimated_duration": 15,
                    "sla": 24,
                    "ai_automatable": False,
                    "is_required": True
                })

    # Ensure we have at least some tasks
    if not tasks:
        tasks = [
            {
                "milestone": milestones[0]["name"],
                "role": role_name,
                "task_name": "Review document requirements",
                "task_description": "Review all requirements from the uploaded document",
                "sequence_order": 0,
                "estimated_duration": 30,
                "sla": 24,
                "ai_automatable": False,
                "is_required": True
            }
        ]

    return {
        "roles": [{
            "role_name": role_name,
            "role_title": role_title,
            "responsibilities": f"Responsibilities extracted from {document_name or 'uploaded document'}",
            "skills_required": ["Document Analysis", "Process Management", "Attention to Detail"],
            "key_activities": ["Document review", "Process execution", "Quality control"]
        }],
        "milestones": milestones,
        "tasks": tasks
    }


# ============================================================================
# ONBOARDING ENDPOINTS
# ============================================================================

@router.get("/steps")
async def get_onboarding_steps(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get onboarding step templates (customized or default)"""
    models = get_models()
    User = models['User']
    OnboardingStep = models['OnboardingStep']

    # Import get_current_user at runtime
    import main
    current_user = await main.get_current_user(_extract_token(request), request, db)

    try:
        # Check if user has customized steps
        custom_steps = db.query(OnboardingStep).filter(
            OnboardingStep.user_id == current_user.id,
            OnboardingStep.is_active == True
        ).order_by(OnboardingStep.step_number).all()

        if custom_steps:
            return {
                "steps": [
                    {
                        "id": step.id,
                        "step_number": step.step_number,
                        "title": step.title,
                        "description": step.description,
                        "icon": step.icon,
                        "required": step.required,
                        "fields": step.fields or []
                    }
                    for step in custom_steps
                ],
                "is_custom": True
            }

        # Return default onboarding steps
        default_steps = [
            {
                "step_number": 1,
                "title": "Welcome to Your CRM",
                "description": "Let's get you set up with everything you need to manage your mortgage pipeline effectively.",
                "icon": "wave",
                "required": True,
                "fields": []
            },
            {
                "step_number": 2,
                "title": "Upload Your Documents",
                "description": "Upload important documents like rate sheets, guidelines, or templates you frequently use.",
                "icon": "document",
                "required": False,
                "fields": [
                    {"name": "documents", "type": "file", "label": "Upload Documents", "multiple": True}
                ]
            },
            {
                "step_number": 3,
                "title": "Connect Your Integrations",
                "description": "Connect your email, calendar, and other tools to streamline your workflow.",
                "icon": "link",
                "required": False,
                "fields": [
                    {"name": "connect_email", "type": "button", "label": "Connect Outlook", "action": "email_oauth"},
                    {"name": "connect_calendar", "type": "button", "label": "Connect Calendar", "action": "calendar_oauth"}
                ]
            },
            {
                "step_number": 4,
                "title": "Add Team Members",
                "description": "Invite processors, assistants, or team members who will work with you.",
                "icon": "users",
                "required": False,
                "fields": [
                    {"name": "team_member_email", "type": "email", "label": "Team Member Email"},
                    {"name": "team_member_role", "type": "select", "label": "Role", "options": ["Processor", "Assistant", "Loan Officer"]}
                ]
            },
            {
                "step_number": 5,
                "title": "You're All Set!",
                "description": "Your CRM is ready to go. Start adding leads and let AI help you close more deals!",
                "icon": "celebration",
                "required": True,
                "fields": []
            }
        ]

        return {"steps": default_steps, "is_custom": False}

    except Exception as e:
        logger.error(f"Get onboarding steps error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/steps")
async def update_onboarding_steps(
    request: Request,
    db: Session = Depends(get_db)
):
    """Update/customize onboarding step templates"""
    models = get_models()
    User = models['User']
    OnboardingStep = models['OnboardingStep']

    import main
    current_user = await main.get_current_user(_extract_token(request), request, db)

    try:
        body = await request.json()
        steps_data = body.get("steps", [])

        # Delete existing custom steps
        db.query(OnboardingStep).filter(
            OnboardingStep.user_id == current_user.id
        ).delete()

        # Create new custom steps
        for step_data in steps_data:
            step = OnboardingStep(
                user_id=current_user.id,
                step_number=step_data.get("step_number"),
                title=step_data.get("title"),
                description=step_data.get("description"),
                icon=step_data.get("icon", "document"),
                required=step_data.get("required", True),
                fields=step_data.get("fields", [])
            )
            db.add(step)

        db.commit()

        return {"message": "Onboarding steps updated successfully", "count": len(steps_data)}

    except Exception as e:
        db.rollback()
        logger.error(f"Update onboarding steps error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/progress")
async def get_onboarding_progress(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get current user's onboarding progress"""
    models = get_models()
    User = models['User']
    OnboardingProgress = models['OnboardingProgress']

    import main
    current_user = await main.get_current_user(_extract_token(request), request, db)

    try:
        progress = db.query(OnboardingProgress).filter(
            OnboardingProgress.user_id == current_user.id
        ).first()

        if not progress:
            # Create initial progress
            progress = OnboardingProgress(
                user_id=current_user.id,
                current_step=1,
                steps_completed=[]
            )
            db.add(progress)
            db.commit()
            db.refresh(progress)

        return {
            "current_step": progress.current_step,
            "steps_completed": progress.steps_completed or [],
            "is_complete": progress.is_complete,
            "completed_at": progress.completed_at.isoformat() if progress.completed_at else None,
            "uploaded_documents": progress.uploaded_documents or [],
            "team_members_added": progress.team_members_added,
            "workflows_generated": progress.workflows_generated
        }

    except Exception as e:
        logger.error(f"Get onboarding progress error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/progress")
async def update_onboarding_progress(
    request: Request,
    db: Session = Depends(get_db)
):
    """Update user's onboarding progress"""
    models = get_models()
    User = models['User']
    OnboardingProgress = models['OnboardingProgress']

    import main
    current_user = await main.get_current_user(_extract_token(request), request, db)

    try:
        body = await request.json()

        progress = db.query(OnboardingProgress).filter(
            OnboardingProgress.user_id == current_user.id
        ).first()

        if not progress:
            progress = OnboardingProgress(user_id=current_user.id)
            db.add(progress)

        # Update fields
        if "current_step" in body:
            progress.current_step = body["current_step"]

        if "steps_completed" in body:
            progress.steps_completed = body["steps_completed"]

        if "uploaded_documents" in body:
            progress.uploaded_documents = body["uploaded_documents"]

        if "team_members_added" in body:
            progress.team_members_added = body["team_members_added"]

        db.commit()

        return {"message": "Progress updated successfully"}

    except Exception as e:
        db.rollback()
        logger.error(f"Update onboarding progress error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/complete")
async def complete_onboarding(
    request: Request,
    db: Session = Depends(get_db)
):
    """Mark onboarding as complete for user"""
    models = get_models()
    User = models['User']
    OnboardingProgress = models['OnboardingProgress']

    import main
    current_user = await main.get_current_user(_extract_token(request), request, db)

    try:
        # Update progress
        progress = db.query(OnboardingProgress).filter(
            OnboardingProgress.user_id == current_user.id
        ).first()

        if progress:
            progress.is_complete = True
            progress.completed_at = datetime.now(timezone.utc)

        # Update user
        current_user.onboarding_completed = True

        db.commit()

        return {"message": "Onboarding completed!", "completed_at": datetime.now(timezone.utc).isoformat()}

    except Exception as e:
        db.rollback()
        logger.error(f"Complete onboarding error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/reset")
async def reset_onboarding(
    request: Request,
    db: Session = Depends(get_db)
):
    """Reset onboarding for current user"""
    models = get_models()
    User = models['User']
    OnboardingProgress = models['OnboardingProgress']

    import main
    current_user = await main.get_current_user(_extract_token(request), request, db)

    try:
        # Delete onboarding progress
        db.query(OnboardingProgress).filter(
            OnboardingProgress.user_id == current_user.id
        ).delete()

        # Reset user onboarding flag
        current_user.onboarding_completed = False

        db.commit()

        return {
            "message": "Onboarding reset successfully!",
            "user_id": current_user.id,
            "email": current_user.email
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Reset onboarding error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/parse-documents")
async def parse_onboarding_documents(
    request: Request,
    db: Session = Depends(get_db)
):
    """Parse uploaded documents and extract roles, milestones, and tasks using AI"""
    models = get_models()
    schemas = get_schemas()
    User = models['User']
    ProcessRole = models['ProcessRole']
    ProcessMilestone = models['ProcessMilestone']
    ProcessTask = models['ProcessTask']
    ProcessRoleResponse = schemas['ProcessRoleResponse']
    ProcessMilestoneResponse = schemas['ProcessMilestoneResponse']
    ProcessTaskResponse = schemas['ProcessTaskResponse']

    import main
    current_user = await main.get_current_user(_extract_token(request), request, db)
    openai_client = get_openai_client()

    try:
        # Parse the request body
        body = await request.json()
        document_content = body.get("document_content", "")
        document_name = body.get("document_name", "")

        # Clear existing parsed data for this user
        db.query(ProcessTask).filter(ProcessTask.user_id == current_user.id).delete()
        db.query(ProcessMilestone).filter(ProcessMilestone.user_id == current_user.id).delete()
        db.query(ProcessRole).filter(ProcessRole.user_id == current_user.id).delete()
        db.commit()

        # Use AI to analyze the document content
        analysis_prompt = f"""
        Analyze the following mortgage loan process document and extract:
        1. All unique roles/positions involved in the process
        2. All major milestones in the mortgage loan process
        3. All tasks for each milestone with role assignments

        For each role, provide:
        - role_name: Short identifier (e.g., "loan_officer", "processor")
        - role_title: Display name (e.g., "Loan Officer", "Loan Processor")
        - responsibilities: Brief description of their main responsibilities
        - skills_required: List of required skills
        - key_activities: List of their primary activities

        For each milestone, provide:
        - name: Milestone name
        - description: Brief description
        - sequence_order: Order in process (0, 1, 2...)
        - estimated_duration: Estimated hours to complete

        For each task, provide:
        - milestone: Which milestone it belongs to
        - role: Which role is responsible
        - task_name: Task name
        - task_description: Detailed description
        - sequence_order: Order within milestone
        - estimated_duration: Minutes to complete
        - sla: Service level agreement in hours
        - ai_automatable: Boolean if AI can automate this
        - is_required: Boolean if required

        Document content:
        {document_content[:10000]}  # Limit to 10k chars

        Return response as JSON with keys: roles, milestones, tasks
        """

        # Use OpenAI to actually parse the document, or fall back to basic parsing
        if openai_client:
            try:
                completion = openai_client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": "You are an expert at analyzing process documents and extracting structured information."},
                        {"role": "user", "content": analysis_prompt}
                    ],
                    response_format={"type": "json_object"}
                )
                ai_response = json.loads(completion.choices[0].message.content)

                # Validate response structure
                if not all(key in ai_response for key in ["roles", "milestones", "tasks"]):
                    raise HTTPException(status_code=500, detail="AI response missing required keys (roles, milestones, tasks)")

                if not ai_response["roles"]:
                    raise HTTPException(status_code=400, detail="No roles found in document. Please upload a document containing role and responsibility information.")

            except json.JSONDecodeError as e:
                logger.error(f"JSON parsing error: {e}")
                raise HTTPException(status_code=500, detail="AI returned invalid JSON")
            except Exception as e:
                logger.error(f"OpenAI parsing error: {e}")
                raise HTTPException(status_code=500, detail="AI parsing failed")
        else:
            # Fallback: Use basic text parsing when OpenAI is not available
            logger.info("Using fallback text-based parsing (no OpenAI API key configured)")
            ai_response = parse_document_basic(document_content, document_name)

        # Create ProcessRole records
        role_map = {}
        for role_data in ai_response["roles"]:
            role = ProcessRole(
                user_id=current_user.id,
                role_name=role_data["role_name"],
                role_title=role_data["role_title"],
                responsibilities=role_data.get("responsibilities"),
                skills_required=role_data.get("skills_required", []),
                key_activities=role_data.get("key_activities", [])
            )
            db.add(role)
            db.flush()
            role_map[role_data["role_name"]] = role.id

        # Create ProcessMilestone records
        milestone_map = {}
        for milestone_data in ai_response["milestones"]:
            milestone = ProcessMilestone(
                user_id=current_user.id,
                name=milestone_data["name"],
                description=milestone_data.get("description"),
                sequence_order=milestone_data.get("sequence_order", 0),
                estimated_duration=milestone_data.get("estimated_duration")
            )
            db.add(milestone)
            db.flush()
            milestone_map[milestone_data["name"]] = milestone.id

        # Create ProcessTask records
        for task_data in ai_response["tasks"]:
            milestone_id = milestone_map.get(task_data["milestone"])
            role_id = role_map.get(task_data["role"])

            if milestone_id and role_id:
                task = ProcessTask(
                    user_id=current_user.id,
                    milestone_id=milestone_id,
                    role_id=role_id,
                    task_name=task_data["task_name"],
                    task_description=task_data.get("task_description"),
                    sequence_order=task_data.get("sequence_order", 0),
                    estimated_duration=task_data.get("estimated_duration"),
                    sla=task_data.get("sla"),
                    sla_unit=task_data.get("sla_unit", "hours"),
                    ai_automatable=task_data.get("ai_automatable", False),
                    is_required=task_data.get("is_required", True)
                )
                db.add(task)

        db.commit()

        # Get created records
        roles = db.query(ProcessRole).filter(ProcessRole.user_id == current_user.id).all()
        milestones = db.query(ProcessMilestone).filter(ProcessMilestone.user_id == current_user.id).all()
        tasks = db.query(ProcessTask).filter(ProcessTask.user_id == current_user.id).all()

        return {
            "roles": [ProcessRoleResponse.model_validate(r) for r in roles],
            "milestones": [ProcessMilestoneResponse.model_validate(m) for m in milestones],
            "tasks": [ProcessTaskResponse.model_validate(t) for t in tasks],
            "summary": {
                "total_roles": len(roles),
                "total_milestones": len(milestones),
                "total_tasks": len(tasks),
                "document_name": document_name
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Parse documents error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/roles")
async def get_process_roles(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get all AI-extracted roles for current user"""
    models = get_models()
    schemas = get_schemas()
    User = models['User']
    ProcessRole = models['ProcessRole']
    ProcessRoleResponse = schemas['ProcessRoleResponse']

    import main
    current_user = await main.get_current_user(_extract_token(request), request, db)

    try:
        roles = db.query(ProcessRole).filter(
            ProcessRole.user_id == current_user.id,
            ProcessRole.is_active == True
        ).order_by(ProcessRole.role_name).all()

        return [ProcessRoleResponse.model_validate(role) for role in roles]

    except Exception as e:
        logger.error(f"Get roles error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/milestones")
async def get_process_milestones(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get all AI-extracted milestones for current user"""
    models = get_models()
    schemas = get_schemas()
    User = models['User']
    ProcessMilestone = models['ProcessMilestone']
    ProcessMilestoneResponse = schemas['ProcessMilestoneResponse']

    import main
    current_user = await main.get_current_user(_extract_token(request), request, db)

    try:
        milestones = db.query(ProcessMilestone).filter(
            ProcessMilestone.user_id == current_user.id,
            ProcessMilestone.is_active == True
        ).order_by(ProcessMilestone.sequence_order).all()

        return [ProcessMilestoneResponse.model_validate(milestone) for milestone in milestones]

    except Exception as e:
        logger.error(f"Get milestones error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/tasks")
async def get_process_tasks(
    request: Request,
    role_id: Optional[int] = None,
    milestone_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Get all AI-extracted tasks for current user, optionally filtered by role or milestone"""
    models = get_models()
    schemas = get_schemas()
    User = models['User']
    ProcessTask = models['ProcessTask']
    ProcessTaskResponse = schemas['ProcessTaskResponse']

    import main
    current_user = await main.get_current_user(_extract_token(request), request, db)

    try:
        query = db.query(ProcessTask).filter(
            ProcessTask.user_id == current_user.id,
            ProcessTask.is_active == True
        )

        if role_id:
            query = query.filter(ProcessTask.role_id == role_id)

        if milestone_id:
            query = query.filter(ProcessTask.milestone_id == milestone_id)

        tasks = query.order_by(ProcessTask.milestone_id, ProcessTask.sequence_order).all()

        return [ProcessTaskResponse.model_validate(task) for task in tasks]

    except Exception as e:
        logger.error(f"Get tasks error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# TEAM ENDPOINTS
# ============================================================================

@team_router.get("/members")
async def get_team_members(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get all team members with their assigned roles from onboarding

    Multi-tenancy: Only shows users from the current user's organization.
    Excludes the platform admin (admin@perenniaai.com).
    """
    models = get_models()
    User = models['User']
    ProcessRole = models['ProcessRole']
    ProcessTask = models['ProcessTask']

    import main
    current_user = await main.get_current_user(_extract_token(request), request, db)

    try:
        # Get all users in the same organization as current user
        # Exclude platform admin and current user (current user is added separately)
        query = db.query(User).filter(
            User.id != current_user.id,
            User.email != 'admin@perenniaai.com'  # Never show platform admin
        )

        # Filter by organization if user has one
        if current_user.organization_id:
            query = query.filter(User.organization_id == current_user.organization_id)

        all_users = query.all()

        # Get all process roles for the current user (the admin who completed onboarding)
        process_roles = db.query(ProcessRole).filter(
            ProcessRole.user_id == current_user.id,
            ProcessRole.is_active == True
        ).all()

        # Get tasks count for each role
        team_members = []

        for user in all_users:
            # Extract metadata
            metadata = user.user_metadata or {}

            # Try to find a matching role for this user (simplified - in production you'd have explicit user-role mapping)
            member_data = {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "first_name": metadata.get("first_name"),
                "last_name": metadata.get("last_name"),
                "phone": metadata.get("phone"),
                "role": user.role,
                "title": metadata.get("title"),
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "onboarding_completed": user.onboarding_completed,
                "tasks_count": 0
            }

            # Add to list
            team_members.append(member_data)

        # No sample/demo data - only show real users from the database

        # Also include current user
        current_metadata = current_user.user_metadata or {}
        current_member = {
            "id": current_user.id,
            "email": current_user.email,
            "full_name": current_user.full_name,
            "first_name": current_metadata.get("first_name"),
            "last_name": current_metadata.get("last_name"),
            "phone": current_metadata.get("phone"),
            "role": current_user.role or "Admin",
            "title": current_metadata.get("title"),
            "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
            "onboarding_completed": current_user.onboarding_completed,
            "tasks_count": 0,
            "is_current": True
        }

        team_members.insert(0, current_member)

        # Get role assignments and task counts
        roles_data = []
        for role in process_roles:
            tasks_count = db.query(ProcessTask).filter(
                ProcessTask.role_id == role.id,
                ProcessTask.is_active == True
            ).count()

            roles_data.append({
                "id": role.id,
                "role_name": role.role_name,
                "role_title": role.role_title,
                "responsibilities": role.responsibilities,
                "skills_required": role.skills_required,
                "key_activities": role.key_activities,
                "tasks_count": tasks_count
            })

        return {
            "team_members": team_members,
            "available_roles": roles_data
        }

    except Exception as e:
        logger.error(f"Get team members error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@team_router.get("/members/{user_id}")
async def get_team_member_detail(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Get detailed information about a specific team member"""
    models = get_models()
    User = models['User']

    import main
    current_user = await main.get_current_user(_extract_token(request), request, db)

    try:
        # Get the user - enforce organization isolation
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Verify the requested user belongs to the same organization
        current_org = getattr(current_user, 'organization_id', None) or getattr(current_user, 'tenant_account_id', None)
        target_org = getattr(user, 'organization_id', None) or getattr(user, 'tenant_account_id', None)
        if current_org and target_org and str(current_org) != str(target_org):
            raise HTTPException(status_code=403, detail="Not authorized to view this user")

        # Parse user_metadata if it exists
        user_metadata = {}
        if hasattr(user, 'user_metadata') and user.user_metadata:
            try:
                user_metadata = json.loads(user.user_metadata) if isinstance(user.user_metadata, str) else user.user_metadata
            except (json.JSONDecodeError, TypeError):
                user_metadata = {}

        # Split full_name into first_name and last_name if not in metadata
        first_name = user_metadata.get('first_name', '')
        last_name = user_metadata.get('last_name', '')

        if not first_name and not last_name and user.full_name:
            name_parts = user.full_name.split(' ', 1)
            first_name = name_parts[0] if len(name_parts) > 0 else ''
            last_name = name_parts[1] if len(name_parts) > 1 else ''

        # Return data structure expected by frontend
        return {
            "id": user.id,
            "email": user.email,
            "first_name": first_name,
            "last_name": last_name,
            "full_name": user.full_name or f"{first_name} {last_name}",
            "role": user.role or "employee",
            "phone": user_metadata.get('phone', user.phone if hasattr(user, 'phone') else ''),
            "photo_url": user_metadata.get('photo_url', user.photo_url if hasattr(user, 'photo_url') else None),
            "employee_id": user_metadata.get('employee_id', ''),
            "start_date": user_metadata.get('start_date', user.created_at.strftime('%Y-%m-%d') if user.created_at else ''),
            "department": user_metadata.get('department', getattr(user, 'department', '')),
            "manager": user_metadata.get('manager', ''),
            "title": user_metadata.get('title', ''),
            "disc_d": user_metadata.get('disc_d', 50),
            "disc_i": user_metadata.get('disc_i', 50),
            "disc_s": user_metadata.get('disc_s', 50),
            "disc_c": user_metadata.get('disc_c', 50),
            "disc_summary": user_metadata.get('disc_summary', ''),
            "birthday": user_metadata.get('birthday', ''),
            "anniversary": user_metadata.get('anniversary', ''),
            "spouse_name": user_metadata.get('spouse_name', ''),
            "children": user_metadata.get('children', ''),
            "hobbies": user_metadata.get('hobbies', ''),
            "emergency_contact": user_metadata.get('emergency_contact', ''),
            "emergency_phone": user_metadata.get('emergency_phone', ''),
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "onboarding_completed": user.onboarding_completed if hasattr(user, 'onboarding_completed') else False
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get team member detail error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@team_router.get("/members/{user_id}/work-hours")
async def get_team_member_work_hours(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Get a team member's work hours for scheduling"""
    models = get_models()
    User = models['User']

    import main
    current_user = await main.get_current_user(_extract_token(request), request, db)

    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            # Return default work hours for non-existent users
            return {
                "user_id": user_id,
                "work_hours_start": "09:00",
                "work_hours_end": "17:00",
                "work_days": ["monday", "tuesday", "wednesday", "thursday", "friday"]
            }

        # Verify organization isolation
        current_org = getattr(current_user, 'organization_id', None) or getattr(current_user, 'tenant_account_id', None)
        target_org = getattr(user, 'organization_id', None) or getattr(user, 'tenant_account_id', None)
        if current_org and target_org and str(current_org) != str(target_org):
            raise HTTPException(status_code=403, detail="Not authorized to view this user")

        # Parse business_hours JSON if it exists
        business_hours = getattr(user, 'business_hours', None) or {}

        return {
            "user_id": user.id,
            "full_name": user.full_name,
            "work_hours_start": business_hours.get('start', '09:00') if business_hours else '09:00',
            "work_hours_end": business_hours.get('end', '17:00') if business_hours else '17:00',
            "work_days": business_hours.get('days', ['monday', 'tuesday', 'wednesday', 'thursday', 'friday']) if business_hours else ['monday', 'tuesday', 'wednesday', 'thursday', 'friday']
        }

    except Exception as e:
        logger.error(f"Get team member work hours error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@team_router.post("/members")
async def create_team_member(
    request: Request,
    db: Session = Depends(get_db)
):
    """Create a new team member"""
    models = get_models()
    User = models['User']
    get_password_hash = get_password_hash_func()

    import main
    current_user = await main.get_current_user(_extract_token(request), request, db)

    try:
        # Parse request body
        body = await request.json()
        first_name = body.get("first_name", "")
        last_name = body.get("last_name", "")
        email = body.get("email")
        phone = body.get("phone")
        role = body.get("role", "employee")
        title = body.get("title")

        # Create a new user for the team member
        # Generate a random password (they can reset it later)
        temp_password = secrets.token_urlsafe(16)
        hashed_password = get_password_hash(temp_password)

        # Create full_name from first and last name
        full_name = f"{first_name} {last_name}"

        # Store additional data in user_metadata
        user_metadata = {
            "first_name": first_name,
            "last_name": last_name,
            "phone": phone,
            "title": title
        }

        new_user = User(
            email=email or f"{first_name.lower()}.{last_name.lower()}@temp.com",
            hashed_password=hashed_password,
            first_name=first_name,
            last_name=last_name,
            role=role,
            user_metadata=user_metadata,
            is_active=True,
            email_verified=False,
            onboarding_completed=False
        )

        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        return {
            "id": new_user.id,
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "phone": phone,
            "role": role,
            "title": title
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Create team member error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@team_router.patch("/members/{member_id}")
async def update_team_member(
    member_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Update a team member"""
    models = get_models()
    User = models['User']

    import main
    current_user = await main.get_current_user(_extract_token(request), request, db)

    try:
        user = db.query(User).filter(User.id == member_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Team member not found")

        # Verify organization isolation
        current_org = getattr(current_user, 'organization_id', None) or getattr(current_user, 'tenant_account_id', None)
        target_org = getattr(user, 'organization_id', None) or getattr(user, 'tenant_account_id', None)
        if current_org and target_org and str(current_org) != str(target_org):
            raise HTTPException(status_code=403, detail="Not authorized to modify this user")

        # Parse request body
        body = await request.json()
        first_name = body.get("first_name")
        last_name = body.get("last_name")
        email = body.get("email")
        phone = body.get("phone")
        role = body.get("role")
        title = body.get("title")

        # Update fields
        user_metadata = user.user_metadata or {}

        if first_name is not None:
            user_metadata["first_name"] = first_name
        if last_name is not None:
            user_metadata["last_name"] = last_name
        if phone is not None:
            user_metadata["phone"] = phone
        if title is not None:
            user_metadata["title"] = title

        # Update first_name/last_name if changed (full_name is a computed hybrid property)
        if first_name is not None:
            user.first_name = first_name
        if last_name is not None:
            user.last_name = last_name

        if email is not None:
            user.email = email
        if role is not None:
            user.role = role

        user.user_metadata = user_metadata

        db.commit()
        db.refresh(user)

        return {
            "id": user.id,
            "first_name": user_metadata.get("first_name"),
            "last_name": user_metadata.get("last_name"),
            "email": user.email,
            "phone": user_metadata.get("phone"),
            "role": user.role,
            "title": user_metadata.get("title")
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Update team member error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@team_router.delete("/members/{member_id}")
async def delete_team_member(
    member_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Delete a team member"""
    models = get_models()
    User = models['User']

    import main
    current_user = await main.get_current_user(_extract_token(request), request, db)

    try:
        user = db.query(User).filter(User.id == member_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Team member not found")

        # Verify organization isolation
        current_org = getattr(current_user, 'organization_id', None) or getattr(current_user, 'tenant_account_id', None)
        target_org = getattr(user, 'organization_id', None) or getattr(user, 'tenant_account_id', None)
        if current_org and target_org and str(current_org) != str(target_org):
            raise HTTPException(status_code=403, detail="Not authorized to delete this user")

        # Prevent self-deletion
        if current_user.id == member_id:
            raise HTTPException(status_code=400, detail="Cannot delete your own account")

        # Soft delete - just mark as inactive
        user.is_active = False
        db.commit()

        return {"message": "Team member deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Delete team member error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# INVITE VALIDATION ENDPOINTS (public, no auth required)
# ============================================================================

@invite_router.get("/api/invite/{token}")
async def get_invite_details(token: str, db: Session = Depends(get_db)):
    """Get invite details for employee invite acceptance page (public endpoint)."""
    try:
        from database.models.permission import EmployeeInvite, InviteStatus
    except ImportError:
        # Fallback: try importing from main
        try:
            import main
            EmployeeInvite = main.EmployeeInvite
            InviteStatus = main.InviteStatus
        except AttributeError:
            raise HTTPException(status_code=404, detail="Invite system not configured")

    invite = db.query(EmployeeInvite).filter(EmployeeInvite.invite_token == token).first()

    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found or has expired")

    if invite.status != InviteStatus.PENDING:
        raise HTTPException(status_code=400, detail=f"Invite has been {invite.status.value}")

    if invite.expires_at and invite.expires_at < datetime.now(timezone.utc):
        invite.status = InviteStatus.EXPIRED
        db.commit()
        raise HTTPException(status_code=400, detail="Invite has expired")

    return {
        "email": invite.email,
        "first_name": invite.first_name,
        "last_name": invite.last_name,
        "job_title": getattr(invite, 'job_title', None),
        "permission_role": invite.permission_role,
        "expires_at": invite.expires_at.isoformat() if invite.expires_at else None
    }


# ============================================================================
# EMPLOYEE IMPERSONATION ENDPOINTS
# ============================================================================

@impersonation_router.post("/start")
async def start_impersonation(
    request: Request,
    db: Session = Depends(get_db)
):
    """Start an impersonation session"""
    models = get_models()
    schemas = get_schemas()
    User = models['User']
    ImpersonationSession = models['ImpersonationSession']

    import main
    current_user = await main.get_current_user(_extract_token(request), request, db)

    try:
        # Parse request body
        body = await request.json()
        user_id = body.get("user_id")
        mode = body.get("mode", "view_only")
        reason = body.get("reason", "")
        duration_minutes = body.get("duration_minutes", 30)
        notify_employee = body.get("notify_employee", False)

        # Verify the user to be impersonated exists
        impersonated_user = db.query(User).filter(User.id == user_id).first()
        if not impersonated_user:
            raise HTTPException(status_code=404, detail="User not found")

        # Check authorization - only managers/admins/site_admins can impersonate
        allowed_roles = {'admin', 'site_admin', 'leadership', 'management'}
        user_role = getattr(current_user, 'permission_role', None) or getattr(current_user, 'role', None) or ''
        if user_role.lower() not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail="Only managers and administrators can impersonate other users"
            )

        # Prevent self-impersonation
        if current_user.id == user_id:
            raise HTTPException(status_code=400, detail="Cannot impersonate yourself")

        # Generate unique session token
        session_token = secrets.token_urlsafe(32)

        # Calculate expiration time
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=duration_minutes)

        # Create impersonation session
        session = ImpersonationSession(
            session_token=session_token,
            manager_id=current_user.id,
            impersonated_user_id=user_id,
            mode=mode,
            reason=reason,
            duration_minutes=duration_minutes,
            notify_employee=notify_employee,
            expires_at=expires_at,
            is_active=True
        )

        db.add(session)
        db.commit()
        db.refresh(session)

        # Get impersonated user metadata
        user_metadata = impersonated_user.user_metadata or {}

        # Return session info
        return {
            "session_token": session_token,
            "impersonated_user": {
                "id": impersonated_user.id,
                "email": impersonated_user.email,
                "full_name": impersonated_user.full_name,
                "first_name": user_metadata.get("first_name"),
                "last_name": user_metadata.get("last_name"),
                "role": impersonated_user.role
            },
            "expires_at": expires_at.isoformat(),
            "mode": mode
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Start impersonation error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@impersonation_router.post("/end")
async def end_impersonation(
    request: Request,
    db: Session = Depends(get_db)
):
    """End an impersonation session"""
    models = get_models()
    User = models['User']
    ImpersonationSession = models['ImpersonationSession']

    import main
    current_user = await main.get_current_user(_extract_token(request), request, db)

    try:
        # Get session token from header
        session_token = request.headers.get("X-Impersonation-Token")

        if not session_token:
            raise HTTPException(status_code=400, detail="No active impersonation session")

        # Find and deactivate the session
        session = db.query(ImpersonationSession).filter(
            ImpersonationSession.session_token == session_token,
            ImpersonationSession.is_active == True
        ).first()

        if not session:
            raise HTTPException(status_code=404, detail="Impersonation session not found")

        # Verify the current user is the manager who started the session
        if session.manager_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized to end this session")

        # End the session
        session.is_active = False
        session.ended_at = datetime.now(timezone.utc)
        db.commit()

        return {"message": "Impersonation session ended successfully"}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"End impersonation error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@impersonation_router.get("/current")
async def get_current_impersonation(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get current impersonation session info"""
    models = get_models()
    User = models['User']
    ImpersonationSession = models['ImpersonationSession']

    import main
    current_user = await main.get_current_user(_extract_token(request), request, db)

    try:
        # Get session token from header
        session_token = request.headers.get("X-Impersonation-Token")

        if not session_token:
            return {"is_impersonating": False}

        # Find active session
        session = db.query(ImpersonationSession).filter(
            ImpersonationSession.session_token == session_token,
            ImpersonationSession.is_active == True,
            ImpersonationSession.expires_at > datetime.now(timezone.utc)
        ).first()

        if not session:
            return {"is_impersonating": False}

        # Get impersonated user
        impersonated_user = db.query(User).filter(User.id == session.impersonated_user_id).first()
        if not impersonated_user:
            return {"is_impersonating": False}

        user_metadata = impersonated_user.user_metadata or {}

        # Calculate time remaining
        time_remaining = (session.expires_at - datetime.now(timezone.utc)).total_seconds()

        return {
            "is_impersonating": True,
            "impersonated_user": {
                "id": impersonated_user.id,
                "email": impersonated_user.email,
                "full_name": impersonated_user.full_name,
                "first_name": user_metadata.get("first_name"),
                "last_name": user_metadata.get("last_name"),
                "role": impersonated_user.role
            },
            "mode": session.mode,
            "expires_at": session.expires_at.isoformat(),
            "time_remaining_seconds": int(time_remaining)
        }

    except Exception as e:
        logger.error(f"Get current impersonation error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
