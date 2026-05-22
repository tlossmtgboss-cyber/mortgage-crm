"""
Client Profile Routes

Handles Client Management Profile (CMP) API endpoints including:
- Client profile CRUD operations
- Team roles management
- Process flow document management
- AI tasks management
- Unified tasks API
- Referral partners management
- Loan team members management
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Body, Request
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, text
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
import logging
import json
import random
import uuid

from utils.background_tasks import tenant_task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Client Profile"])

# Dependency injection placeholders
User = None
_get_current_user = None
_get_db = None


def set_dependencies(user_model, current_user_func, db_func):
    """Set dependencies for this router."""
    global User, _get_current_user, _get_db
    User = user_model
    _get_current_user = current_user_func
    _get_db = db_func


def get_db():
    """Get database session - wrapper that works at request time."""
    if _get_db is None:
        raise HTTPException(status_code=500, detail="Database dependency not configured")
    yield from _get_db()


async def get_current_user(request: Request, db: Session = Depends(get_db)):
    """Get current user - wrapper that works at request time."""
    if _get_current_user is None:
        raise HTTPException(status_code=500, detail="Auth dependency not configured")

    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""

    return await _get_current_user(token=token, request=request, db=db)


def get_main_module():
    """Import main module at runtime to avoid circular imports."""
    import main
    return main


# ============================================================================
# CLIENT MANAGEMENT PROFILE (CMP) API ENDPOINTS
# ============================================================================

@router.post("/profile/", status_code=201)
async def create_client_profile(
    profile_data: Any = Body(...),
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user)
):
    """Create a new Client Management Profile for the current user"""
    main = get_main_module()
    ClientProfile = main.ClientProfile
    ClientProfileCreate = main.ClientProfileCreate

    # Validate input using Pydantic model
    if not isinstance(profile_data, main.ClientProfileCreate):
        profile_data = ClientProfileCreate(**profile_data)

    # Check if user already has a profile
    existing_profile = db.query(ClientProfile).filter(ClientProfile.primary_user_id == current_user.id).first()
    if existing_profile:
        raise HTTPException(status_code=400, detail="User already has a client profile")

    # Generate unique account ID
    account_id = str(uuid.uuid4())

    # Create profile
    db_profile = ClientProfile(
        account_id=account_id,
        account_type=profile_data.account_type,
        primary_user_id=current_user.id,
        company_name=profile_data.company_name,
        nmls_number=profile_data.nmls_number,
        business_address=profile_data.business_address,
        team_size=profile_data.team_size or 1,
        user_profile=profile_data.user_profile.model_dump() if profile_data.user_profile else None,
        subscription_plan=profile_data.subscription_plan or "Solo",
        billing_status="active",
        # Initialize empty JSON fields
        integration_settings={},
        branding_settings={},
        automation_settings={"coach_intensity": "medium", "auto_task_creation": True},
        reconciliation_settings={"auto_update_threshold": 0.8},
        pipeline_settings={"follow_up_model": "balanced"},
        kpi_targets={},
        portfolio_settings={"rate_drop_alerts": True, "equity_alerts": True},
        advanced_settings={}
    )

    db.add(db_profile)
    db.commit()
    db.refresh(db_profile)

    logger.info(f"Client profile created for user {current_user.id}: {account_id}")
    return db_profile


@router.get("/profile/")
async def get_client_profile(
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user)
):
    """Get the current user's Client Management Profile"""
    main = get_main_module()
    ClientProfile = main.ClientProfile

    profile = db.query(ClientProfile).filter(ClientProfile.primary_user_id == current_user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Client profile not found. Create one first.")

    return profile


@router.patch("/profile/")
async def update_client_profile(
    profile_update: Any = Body(...),
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user)
):
    """Update the current user's Client Management Profile"""
    main = get_main_module()
    ClientProfile = main.ClientProfile
    ClientProfileUpdate = main.ClientProfileUpdate

    # Validate input
    if not isinstance(profile_update, main.ClientProfileUpdate):
        profile_update = ClientProfileUpdate(**profile_update)

    profile = db.query(ClientProfile).filter(ClientProfile.primary_user_id == current_user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Client profile not found")

    # Update fields if provided
    _protected = {'id', 'primary_user_id', 'organization_id', 'created_at', 'updated_at'}
    update_data = profile_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        if field in _protected:
            continue
        if field == "user_profile" and value:
            setattr(profile, field, value.model_dump())
        elif field in ["integration_settings", "branding_settings", "automation_settings",
                       "reconciliation_settings", "pipeline_settings", "kpi_targets",
                       "portfolio_settings", "advanced_settings"] and value:
            setattr(profile, field, value.model_dump())
        else:
            setattr(profile, field, value)

    profile.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(profile)

    logger.info(f"Client profile updated for user {current_user.id}")
    return profile


@router.delete("/profile/", status_code=204)
async def delete_client_profile(
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user)
):
    """Delete the current user's Client Management Profile"""
    main = get_main_module()
    ClientProfile = main.ClientProfile

    profile = db.query(ClientProfile).filter(ClientProfile.primary_user_id == current_user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Client profile not found")

    db.delete(profile)
    db.commit()

    logger.info(f"Client profile deleted for user {current_user.id}")
    return None


# ============================================================================
# TEAM ROLES MANAGEMENT
# ============================================================================

@router.post("/profile/team-roles/", status_code=201)
async def create_team_role(
    role_data: Any = Body(...),
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user)
):
    """Create a new team role for the current user's profile"""
    main = get_main_module()
    ClientProfile = main.ClientProfile
    TeamRole = main.TeamRole
    TeamRoleCreate = main.TeamRoleCreate

    if not isinstance(role_data, main.TeamRoleCreate):
        role_data = TeamRoleCreate(**role_data)

    profile = db.query(ClientProfile).filter(ClientProfile.primary_user_id == current_user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Client profile not found")

    db_role = TeamRole(
        profile_id=profile.id,
        **role_data.model_dump()
    )

    db.add(db_role)
    db.commit()
    db.refresh(db_role)

    logger.info(f"Team role created: {db_role.role_name}")
    return db_role


@router.get("/profile/team-roles/")
async def get_team_roles(
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user)
):
    """Get all team roles for the current user's profile"""
    main = get_main_module()
    ClientProfile = main.ClientProfile
    TeamRole = main.TeamRole

    profile = db.query(ClientProfile).filter(ClientProfile.primary_user_id == current_user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Client profile not found")

    roles = db.query(TeamRole).filter(TeamRole.profile_id == profile.id, TeamRole.is_active == True).all()
    return roles


@router.patch("/profile/team-roles/{role_id}")
async def update_team_role(
    role_id: int,
    role_update: Any = Body(...),
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user)
):
    """Update a team role"""
    main = get_main_module()
    ClientProfile = main.ClientProfile
    TeamRole = main.TeamRole
    TeamRoleUpdate = main.TeamRoleUpdate

    if not isinstance(role_update, main.TeamRoleUpdate):
        role_update = TeamRoleUpdate(**role_update)

    profile = db.query(ClientProfile).filter(ClientProfile.primary_user_id == current_user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Client profile not found")

    role = db.query(TeamRole).filter(TeamRole.id == role_id, TeamRole.profile_id == profile.id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Team role not found")

    _protected = {'id', 'profile_id', 'organization_id', 'created_at', 'updated_at'}
    update_data = role_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        if field not in _protected:
            setattr(role, field, value)

    role.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(role)

    logger.info(f"Team role updated: {role.role_name}")
    return role


@router.delete("/profile/team-roles/{role_id}", status_code=204)
async def delete_team_role(
    role_id: int,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user)
):
    """Delete (deactivate) a team role"""
    main = get_main_module()
    ClientProfile = main.ClientProfile
    TeamRole = main.TeamRole

    profile = db.query(ClientProfile).filter(ClientProfile.primary_user_id == current_user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Client profile not found")

    role = db.query(TeamRole).filter(TeamRole.id == role_id, TeamRole.profile_id == profile.id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Team role not found")

    role.is_active = False
    db.commit()

    logger.info(f"Team role deactivated: {role.role_name}")
    return None


# ============================================================================
# PROCESS FLOW MANAGEMENT
# ============================================================================

def _parse_process_flow_async(document_id: int, *, db=None, organization_id: int = None):
    """Background task to parse a process flow document using AI.

    When invoked via tenant_task, receives a tenant-scoped db session.
    Falls back to tenant-scoped session via set_tenant_context when org_id is available.
    """
    main = get_main_module()
    ProcessFlowDocument = main.ProcessFlowDocument
    SessionLocal = main.SessionLocal
    parse_document_basic = main.parse_document_basic
    import requests

    _owns_session = False
    if db is None:
        db = SessionLocal()
        _owns_session = True
        # TENANT-017: Set RLS context if org_id is known
        if organization_id:
            try:
                from database.tenant_mixin import set_tenant_context
                set_tenant_context(db, organization_id)
            except Exception:
                pass
    try:
        # Get the document
        document = db.query(ProcessFlowDocument).filter(ProcessFlowDocument.id == document_id).first()
        if not document:
            logger.error(f"Process flow document {document_id} not found for parsing")
            return

        # Update status to processing
        document.ai_parsing_status = "processing"
        db.commit()

        try:
            # Fetch document content from file_url
            document_content = ""
            if document.file_url:
                try:
                    from urllib.parse import urlparse
                    import ipaddress as _ipaddress
                    parsed_url = urlparse(document.file_url)
                    _hostname = parsed_url.hostname or ""
                    _blocked = {"localhost", "127.0.0.1", "0.0.0.0", "[::1]",
                                "169.254.169.254", "metadata.google.internal"}
                    _is_private_ip = False
                    try:
                        _ip = _ipaddress.ip_address(_hostname)
                        _is_private_ip = _ip.is_private or _ip.is_loopback or _ip.is_link_local or _ip.is_reserved
                    except ValueError:
                        pass
                    if parsed_url.scheme not in ("https", "http"):
                        logger.warning(f"Rejected non-HTTP URL scheme: {parsed_url.scheme}")
                    elif _hostname in _blocked or _is_private_ip:
                        logger.warning(f"Rejected internal URL for document {document_id}")
                    else:
                        response = requests.get(document.file_url, timeout=30, allow_redirects=False)
                        response.raise_for_status()
                        document_content = response.text
                except Exception as fetch_err:
                    logger.warning(f"Could not fetch document from URL: {fetch_err}")
                    # Fall back to empty content - parse_document_basic will handle it

            # Parse the document
            parsed_content = parse_document_basic(document_content, document.document_name)

            # Update with parsed content
            document.ai_parsed_content = parsed_content
            document.ai_parsing_status = "completed"
            db.commit()

            logger.info(f"Successfully parsed process flow document {document_id}: {document.document_name}")

        except Exception as parse_err:
            logger.error(f"Failed to parse process flow document {document_id}: {parse_err}")
            document.ai_parsing_status = "failed"
            document.ai_parsed_content = {"error": str(parse_err)}
            db.commit()

    except Exception as e:
        logger.error(f"Background task error for document {document_id}: {e}")
    finally:
        if _owns_session:
            db.close()


@router.post("/profile/process-flows/", status_code=201)
async def upload_process_flow(
    document_data: Any = Body(...),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user)
):
    """Upload a process flow document for AI parsing"""
    main = get_main_module()
    ClientProfile = main.ClientProfile
    ProcessFlowDocument = main.ProcessFlowDocument
    ProcessFlowDocumentCreate = main.ProcessFlowDocumentCreate

    if not isinstance(document_data, main.ProcessFlowDocumentCreate):
        document_data = ProcessFlowDocumentCreate(**document_data)

    profile = db.query(ClientProfile).filter(ClientProfile.primary_user_id == current_user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Client profile not found")

    db_document = ProcessFlowDocument(
        profile_id=profile.id,
        **document_data.model_dump(),
        ai_parsing_status="pending"
    )

    db.add(db_document)
    db.commit()
    db.refresh(db_document)

    # Trigger AI parsing job asynchronously
    if background_tasks:
        org_id = getattr(current_user, "organization_id", None)
        if org_id:
            background_tasks.add_task(tenant_task, _parse_process_flow_async, org_id, db_document.id)
        else:
            background_tasks.add_task(_parse_process_flow_async, db_document.id)
    logger.info(f"Process flow document uploaded: {db_document.document_name}, parsing queued")
    return db_document


@router.get("/profile/process-flows/")
async def get_process_flows(
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user)
):
    """Get all process flow documents for the current user's profile"""
    main = get_main_module()
    ClientProfile = main.ClientProfile
    ProcessFlowDocument = main.ProcessFlowDocument

    profile = db.query(ClientProfile).filter(ClientProfile.primary_user_id == current_user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Client profile not found")

    documents = db.query(ProcessFlowDocument).filter(ProcessFlowDocument.profile_id == profile.id).all()
    return documents


# ============================================================================
# AI TASKS CRUD (COMPLETE)
# ============================================================================

@router.post("/tasks", status_code=201)
async def create_task(
    task: Any = Body(...),
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user)
):
    main = get_main_module()
    AITask = main.AITask
    TaskCreate = main.TaskCreate

    if not isinstance(task, main.TaskCreate):
        task = TaskCreate(**task)

    db_task = AITask(
        **task.model_dump(),
        assigned_to_id=current_user.id,
        ai_confidence=random.randint(70, 95)
    )

    db.add(db_task)
    db.commit()
    db.refresh(db_task)

    logger.info(f"Task created: {db_task.title}")
    return db_task


@router.get("/tasks")
async def get_tasks(
    skip: int = 0,
    limit: int = 100,
    type: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user)
):
    main = get_main_module()
    AITask = main.AITask
    TaskType = main.TaskType
    from services.dre_helpers import get_entity_name, classify_email_intent, generate_recommended_action

    try:
        query = db.query(AITask).filter(
            AITask.assigned_to_id == current_user.id,
            AITask.type != TaskType.COMPLETED
        )
        if type:
            try:
                type_enum = TaskType(type)
                query = query.filter(AITask.type == type_enum)
            except ValueError:
                pass

        tasks = query.order_by(AITask.created_at.desc()).offset(skip).limit(limit).all()

        # Enhance tasks with AI intelligence
        enhanced_tasks = []
        for task in tasks:
            task_dict = {
                "id": task.id,
                "title": task.title,
                "description": task.description,
                "type": task.type.value if task.type else None,
                "category": task.category,
                "priority": task.priority,
                "ai_confidence": task.ai_confidence,
                "ai_reasoning": task.ai_reasoning,
                "suggested_action": task.suggested_action,
                "completed_action": task.completed_action,
                "borrower_name": task.borrower_name,
                "lead_id": task.lead_id,
                "loan_id": task.loan_id,
                "assigned_to_id": task.assigned_to_id,
                "due_date": task.due_date,
                "completed_at": task.completed_at,
                "estimated_time": task.estimated_time,
                "feedback": task.feedback,
                "user_metadata": task.user_metadata,
                "created_at": task.created_at,
                "updated_at": task.updated_at
            }

            # Add entity name
            entity_name = None
            entity_type = None
            if task.loan_id:
                entity_type = "loan"
                entity_name = get_entity_name("loan", task.loan_id, db)
            elif task.lead_id:
                entity_type = "lead"
                entity_name = get_entity_name("lead", task.lead_id, db)

            task_dict["entity_name"] = entity_name
            task_dict["entity_type"] = entity_type

            # Classify task intent if description is available
            if task.description:
                email_intent = classify_email_intent(
                    task.title or "",
                    task.description or "",
                    {}
                )
                task_dict["task_intent"] = email_intent.get("intent")
                task_dict["task_intent_description"] = email_intent.get("description")
            else:
                task_dict["task_intent"] = None
                task_dict["task_intent_description"] = None

            # Generate recommended action if not already set
            if not task.suggested_action and task.description:
                email_intent = classify_email_intent(task.title or "", task.description or "", {})
                if email_intent.get("confidence", 0) > 0.60:
                    recommended_action = generate_recommended_action(
                        email_intent,
                        entity_type,
                        {}
                    )
                    task_dict["recommended_action"] = recommended_action
                else:
                    task_dict["recommended_action"] = None
            else:
                # Use existing suggested_action
                if task.suggested_action:
                    task_dict["recommended_action"] = {
                        "title": "Suggested Action",
                        "description": task.suggested_action,
                        "action_type": "manual",
                        "learning_status": "AI suggestion based on task analysis"
                    }
                else:
                    task_dict["recommended_action"] = None

            enhanced_tasks.append(task_dict)

        return enhanced_tasks
    except Exception as e:
        logger.error(f"Error fetching tasks: {e}")
        # Return empty list on error (table might not exist)
        return []


@router.get("/tasks/{task_id}")
async def get_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user)
):
    main = get_main_module()
    AITask = main.AITask
    Task = main.Task

    task = db.query(AITask).filter(AITask.id == task_id, AITask.assigned_to_id == current_user.id).first()
    if task:
        return task

    wf_task = db.query(Task).filter(Task.id == task_id, Task.owner_id == current_user.id).first()
    if wf_task:
        return {
            "id": wf_task.id,
            "title": wf_task.title,
            "description": wf_task.description,
            "type": wf_task.status,
            "priority": wf_task.priority,
            "due_date": wf_task.due_date.isoformat() if wf_task.due_date else None,
            "created_at": wf_task.created_at.isoformat() if wf_task.created_at else None,
            "updated_at": wf_task.updated_at.isoformat() if wf_task.updated_at else None,
            "lead_id": wf_task.lead_id,
            "loan_id": wf_task.loan_id,
            "source": "workflow",
            "related_contact_name": wf_task.related_contact_name,
            "status": wf_task.status,
        }

    raise HTTPException(status_code=404, detail="Task not found")


@router.patch("/tasks/{task_id}")
async def update_task(
    task_id: int,
    task_update: Any = Body(...),
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user)
):
    main = get_main_module()
    AITask = main.AITask
    TaskUpdate = main.TaskUpdate
    TaskType = main.TaskType

    if not isinstance(task_update, main.TaskUpdate):
        task_update = TaskUpdate(**task_update)

    Task = main.Task

    task = db.query(AITask).filter(AITask.id == task_id, AITask.assigned_to_id == current_user.id).first()
    is_workflow = False

    if not task:
        task = db.query(Task).filter(Task.id == task_id, Task.owner_id == current_user.id).first()
        is_workflow = True

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if is_workflow:
        update_data = task_update.dict(exclude_unset=True)
        if update_data.get("type") == "Completed" or update_data.get("status") == "completed":
            task.status = "completed"
            task.completed_at = datetime.now(timezone.utc)
        elif "status" in update_data:
            task.status = update_data["status"]
        if "priority" in update_data:
            task.priority = update_data["priority"]
        task.updated_at = datetime.now(timezone.utc)
    else:
        _protected = {'id', 'organization_id', 'created_at', 'updated_at', 'user_id'}
        for key, value in task_update.dict(exclude_unset=True).items():
            if key not in _protected:
                setattr(task, key, value)

        if task_update.type == TaskType.COMPLETED:
            task.completed_at = datetime.now(timezone.utc)

        task.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(task)

    logger.info(f"Task updated: {task.title}")
    return task


@router.post("/tasks/{task_id}/delegate")
async def delegate_task(
    task_id: int,
    delegate_data: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user)
):
    """Delegate a task to another team member - removes from current user's list"""
    main = get_main_module()
    AITask = main.AITask
    Task = main.Task
    User = main.User

    try:
        new_owner_id = delegate_data.get("delegate_to_id")
        if not new_owner_id:
            raise HTTPException(status_code=400, detail="delegate_to_id is required")

        # Find the task - check AITask first
        task = db.query(AITask).filter(
            AITask.id == task_id,
            AITask.assigned_to_id == current_user.id
        ).first()

        if not task:
            # Also check regular Task table
            regular_task = db.query(Task).filter(
                Task.id == task_id,
                Task.owner_id == current_user.id
            ).first()
            if regular_task:
                regular_task.owner_id = new_owner_id
                regular_task.updated_at = datetime.now(timezone.utc)
                db.commit()
                return {"success": True, "message": "Task delegated successfully"}
            raise HTTPException(status_code=404, detail="Task not found or not owned by you")

        # Get the new owner's info for logging — must be in same org
        new_owner = db.query(User).filter(User.id == new_owner_id, User.organization_id == current_user.organization_id).first()
        new_owner_name = new_owner.full_name if new_owner else f"User {new_owner_id}"

        # Update the task assignment
        old_owner_id = task.assigned_to_id
        task.assigned_to_id = new_owner_id
        task.updated_at = datetime.now(timezone.utc)

        # Add delegation note to metadata if exists
        if hasattr(task, 'metadata') and task.metadata:
            try:
                meta = json.loads(task.metadata) if isinstance(task.metadata, str) else task.metadata
            except (json.JSONDecodeError, TypeError):
                meta = {}
            meta['delegated_from'] = current_user.id
            meta['delegated_from_name'] = current_user.full_name
            meta['delegated_at'] = datetime.now(timezone.utc).isoformat()
            task.metadata = json.dumps(meta)

        db.commit()

        logger.info(f"Task {task_id} delegated from user {old_owner_id} to user {new_owner_id}")
        return {
            "success": True,
            "message": f"Task delegated to {new_owner_name}",
            "task_id": task_id,
            "new_owner_id": new_owner_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delegate task error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/tasks/{task_id}/complete-sla")
async def complete_sla_task(
    task_id: int,
    completion_data: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user)
):
    """
    Complete an SLA milestone task with a date.
    This endpoint:
    1. Marks the task as completed
    2. Stores the milestone date
    3. Updates the loan's Important Dates field (if mapped)
    4. Completes the SLA milestone

    Request body:
    {
        "milestone_date": "2024-01-15T00:00:00Z"  // ISO format date
    }
    """
    _cmp_org_id = getattr(current_user, 'organization_id', None)
    if not _cmp_org_id:
        raise HTTPException(status_code=403, detail="Organization context required")

    try:
        from crud.sla_tracking import complete_sla_task_with_date

        milestone_date_str = completion_data.get("milestone_date")
        if not milestone_date_str:
            raise HTTPException(status_code=400, detail="milestone_date is required")

        # Parse the date
        try:
            if isinstance(milestone_date_str, str):
                # Try ISO format first
                if "T" in milestone_date_str:
                    milestone_date = datetime.fromisoformat(milestone_date_str.replace("Z", "+00:00"))
                else:
                    # Try simple date format
                    milestone_date = datetime.strptime(milestone_date_str, "%Y-%m-%d")
                    milestone_date = milestone_date.replace(tzinfo=timezone.utc)
            else:
                milestone_date = milestone_date_str
        except ValueError as e:
            raise HTTPException(status_code=400, detail="Invalid date format")

        # Complete the SLA task
        result = complete_sla_task_with_date(
            db=db,
            task_id=task_id,
            milestone_date=milestone_date,
            user_id=current_user.id,
            organization_id=_cmp_org_id
        )

        if not result["success"]:
            raise HTTPException(status_code=400, detail=result.get("error", "Failed to complete SLA task"))

        return {
            "success": True,
            "message": "SLA task completed successfully",
            **result
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Complete SLA task error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/tasks/sla")
async def get_sla_tasks(
    include_completed: bool = False,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user)
):
    """
    Get all SLA milestone warning tasks for the current user.
    These are tasks created when SLA milestones hit warning or overdue status.
    """
    try:
        from crud.sla_tracking import get_sla_tasks_for_user

        tasks = get_sla_tasks_for_user(
            db=db,
            user_id=current_user.id,
            include_completed=include_completed
        )

        return {
            "success": True,
            "count": len(tasks),
            "tasks": tasks
        }

    except Exception as e:
        logger.error(f"Get SLA tasks error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/tasks/{task_id}", status_code=204)
async def delete_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user)
):
    main = get_main_module()
    AITask = main.AITask
    Task = main.Task

    try:
        # Try to find in AITask first
        task = db.query(AITask).filter(AITask.id == task_id, AITask.assigned_to_id == current_user.id).first()
        task_type = "AITask"

        # If not found in AITask, try regular Task table
        if not task:
            task = db.query(Task).filter(Task.id == task_id, Task.owner_id == current_user.id).first()
            task_type = "Task"

        # If still not found, try without user filter (for admin cleanup) — still scoped to org
        # Only managers/admins can delete other users' tasks
        if not task:
            if not hasattr(current_user, 'role') or current_user.role not in ('admin', 'manager', 'platform_admin'):
                raise HTTPException(status_code=403, detail="Cannot delete other users' tasks")
            task = db.query(AITask).filter(AITask.id == task_id, AITask.organization_id == current_user.organization_id).first()
            task_type = "AITask (any user)"

        if not task:
            task = db.query(Task).filter(Task.id == task_id, Task.organization_id == current_user.organization_id).first()
            task_type = "Task (any user)"

        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        task_title = task.title
        db.delete(task)
        db.commit()
        logger.info(f"{task_type} deleted: {task_title} (ID: {task_id})")
        return None
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting task {task_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to delete task")


# ============================================================================
# UNIFIED TASKS API - Aggregates tasks, workflow items, and reconciliation
# ============================================================================

@router.get("/unified-tasks")
async def get_unified_tasks(
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get all actionable items from tasks, workflow, and reconciliation
    in a unified format with AI confidence scores.

    OPTIMIZED: Uses batch queries and caching to reduce response time from 12s to <1s.
    """
    main = get_main_module()
    AITask = main.AITask
    Task = main.Task
    TaskType = main.TaskType
    Loan = main.Loan
    Lead = main.Lead
    ExtractedData = main.ExtractedData
    IncomingDataEvent = main.IncomingDataEvent
    from services.dre_helpers import (
        detect_scheduling_intent,
        get_calendly_time_slots_for_user,
        generate_scheduling_email_draft,
    )

    from performance_cache import get_cached, set_cached, cache_key, DEFAULT_TTL

    try:

        # Check cache first (30 second TTL for task lists)
        cache_k = cache_key("unified_tasks", current_user.id)
        cached_result = get_cached(cache_k)
        if cached_result:
            return cached_result

        unified_tasks = []

        # Pre-fetch calendly slots once (expensive operation)
        calendly_slots = None
        user_name = current_user.full_name or current_user.email or "Your Loan Officer"

        # 1. Get pending AI Tasks with joined loan data (avoid N+1)
        loan_ids = set()
        lead_ids = set()
        loans_map = {}
        leads_map = {}
        try:
            ai_tasks = db.query(AITask).options(
                joinedload(AITask.loan)
            ).filter(
                AITask.assigned_to_id == current_user.id,
                AITask.type != TaskType.COMPLETED
            ).order_by(AITask.created_at.desc()).limit(50).all()

            # Collect all loan/lead IDs for batch lookup
            for task in ai_tasks:
                if task.loan_id:
                    loan_ids.add(task.loan_id)
                elif task.lead_id:
                    lead_ids.add(task.lead_id)

            # Batch fetch loans and leads for entity names
            if loan_ids:
                loans = db.query(Loan).filter(Loan.id.in_(loan_ids)).all()
                loans_map = {l.id: l for l in loans}
            if lead_ids:
                leads = db.query(Lead).filter(Lead.id.in_(lead_ids)).all()
                leads_map = {l.id: l for l in leads}

            for task in ai_tasks:
                # Get entity name from pre-fetched data
                entity_name = None
                loan_stage = None
                if task.loan_id and task.loan_id in loans_map:
                    loan = loans_map[task.loan_id]
                    entity_name = loan.borrower_name
                    loan_stage = str(loan.stage) if loan.stage else None
                elif task.lead_id and task.lead_id in leads_map:
                    lead = leads_map[task.lead_id]
                    entity_name = lead.name

                ai_response = task.suggested_action or task.ai_reasoning
                # Prefer entity name from loan/lead relationship for accuracy
                client_name = entity_name or task.borrower_name or "Client"
                has_scheduling = detect_scheduling_intent(task.title or "", task.description or "")

                # Only fetch calendly slots if needed (lazy load once)
                if has_scheduling:
                    if calendly_slots is None:
                        calendly_slots = await get_calendly_time_slots_for_user(current_user.id, db, num_slots=5)
                    ai_response = generate_scheduling_email_draft(
                        client_name=client_name,
                        calendly_slots=calendly_slots,
                        user_name=user_name
                    )

                unified_tasks.append({
                    "id": task.id,
                    "source": "task",
                    "title": task.title,
                    "description": task.description,
                    "client_name": client_name,
                    "ai_confidence": task.ai_confidence if task.ai_confidence is not None else 50,
                    "ai_suggested_response": ai_response,
                    "priority": task.priority or "medium",
                    "due_date": task.due_date.isoformat() if task.due_date else None,
                    "created_at": task.created_at.isoformat() if task.created_at else None,
                    "entity_type": "loan" if task.loan_id else "lead" if task.lead_id else None,
                    "entity_id": task.loan_id or task.lead_id,
                    "stage": loan_stage or "AI Suggested",
                    "owner": "Loan Officer",
                    "communication_count": 0,
                    "has_calendly_slots": has_scheduling
                })
        except Exception as e:
            logger.exception("unified-tasks: failed to load ai_tasks source: %s", e)

        # 2. Get pending workflow tasks with joined loan data
        try:
            # Increased limit to ensure workflow tasks (which may have later due dates) are included
            workflow_tasks = db.query(Task).options(
                joinedload(Task.loan)
            ).filter(
                Task.owner_id == current_user.id,
                Task.status.in_(["pending", "in_progress"])
            ).order_by(Task.due_date.asc()).limit(200).all()

            # Collect additional loan/lead IDs from workflow tasks
            for task in workflow_tasks:
                if task.loan_id:
                    loan_ids.add(task.loan_id)
                elif task.lead_id:
                    lead_ids.add(task.lead_id)

            # Fetch any additional loans/leads not yet in map
            additional_loan_ids = loan_ids - set(loans_map.keys())
            additional_lead_ids = lead_ids - set(leads_map.keys())
            if additional_loan_ids:
                additional_loans = db.query(Loan).filter(Loan.id.in_(additional_loan_ids)).all()
                for l in additional_loans:
                    loans_map[l.id] = l
            if additional_lead_ids:
                additional_leads = db.query(Lead).filter(Lead.id.in_(additional_lead_ids)).all()
                for l in additional_leads:
                    leads_map[l.id] = l

            for task in workflow_tasks:
                entity_name = None
                loan_stage = None
                if task.loan_id and task.loan_id in loans_map:
                    loan = loans_map[task.loan_id]
                    entity_name = loan.borrower_name
                    loan_stage = str(loan.stage) if loan.stage else None
                elif task.lead_id and task.lead_id in leads_map:
                    lead = leads_map[task.lead_id]
                    entity_name = lead.name

                ai_confidence = 50
                # Prefer loan/lead entity name over related_contact_name for accuracy
                client_name = entity_name or task.related_contact_name or "Client"
                ai_response = f"Complete task: {task.title}"
                has_calendly = detect_scheduling_intent(task.title or "", task.description or "")

                if has_calendly:
                    if calendly_slots is None:
                        calendly_slots = await get_calendly_time_slots_for_user(current_user.id, db, num_slots=5)
                    ai_response = generate_scheduling_email_draft(
                        client_name=client_name,
                        calendly_slots=calendly_slots,
                        user_name=user_name
                    )
                    ai_confidence = 85

                unified_tasks.append({
                    "id": task.id,
                    "source": "workflow",
                    "title": task.title,
                    "description": task.description,
                    "client_name": client_name,
                    "ai_confidence": ai_confidence,
                    "ai_suggested_response": ai_response,
                    "priority": task.priority or "medium",
                    "due_date": task.due_date.isoformat() if task.due_date else None,
                    "created_at": task.created_at.isoformat() if task.created_at else None,
                    "entity_type": "loan" if task.loan_id else "lead" if task.lead_id else None,
                    "entity_id": task.loan_id or task.lead_id,
                    "stage": loan_stage or "Workflow",
                    "owner": "Loan Officer",
                    "communication_count": 0,
                    "has_calendly_slots": has_calendly,
                    # SLA task fields
                    "sla_milestone_id": task.sla_milestone_id,
                    "sla_milestone_type": task.sla_milestone_type,
                    "sla_date_field": task.sla_date_field,
                    "related_type": task.related_type,
                    # SF Disposition fields
                    "sf_proposed_stage": getattr(task, 'sf_proposed_stage', None),
                    "sf_current_stage": getattr(task, 'sf_current_stage', None),
                    "is_disposition": getattr(task, 'related_type', None) == 'sf_disposition',
                })
        except Exception as e:
            logger.exception("unified-tasks: failed to load workflow tasks source: %s", e)

        # 3. Get pending reconciliation items (batch fetch events separately to avoid N+1)
        try:
            # Only show items assigned to current user - don't show unassigned items to everyone
            pending_reconciliation = db.query(ExtractedData).join(
                IncomingDataEvent,
                ExtractedData.event_id == IncomingDataEvent.id
            ).filter(
                IncomingDataEvent.user_id == current_user.id,
                ExtractedData.status.in_(["pending_review", "needs_review"])
            ).order_by(ExtractedData.created_at.desc()).limit(50).all()

            # Batch fetch all events for reconciliation items
            event_ids = [item.event_id for item in pending_reconciliation if item.event_id]
            events_map = {}
            if event_ids:
                events = db.query(IncomingDataEvent).filter(IncomingDataEvent.id.in_(event_ids)).all()
                events_map = {e.id: e for e in events}

            # Collect loan IDs from reconciliation items
            recon_loan_ids = set()
            for item in pending_reconciliation:
                if item.match_entity_type == "loan" and item.match_entity_id:
                    recon_loan_ids.add(item.match_entity_id)

            # Batch fetch additional loans
            new_loan_ids = recon_loan_ids - set(loans_map.keys())
            if new_loan_ids:
                new_loans = db.query(Loan).filter(Loan.id.in_(new_loan_ids)).all()
                for l in new_loans:
                    loans_map[l.id] = l

            for item in pending_reconciliation:
                event = events_map.get(item.event_id)  # Get from pre-fetched map

                entity_name = None
                if item.match_entity_type == "loan" and item.match_entity_id in loans_map:
                    entity_name = loans_map[item.match_entity_id].borrower_name
                elif item.match_entity_type == "lead" and item.match_entity_id in leads_map:
                    entity_name = leads_map[item.match_entity_id].name

                borrower_name = None
                if item.fields:
                    borrower_name = item.fields.get("borrower_name", {}).get("value")

                # Simplified email intent classification (skip expensive AI calls)
                ai_response = "Review and categorize this email"
                if event and event.subject:
                    subject_lower = event.subject.lower()
                    if "appraisal" in subject_lower:
                        ai_response = "Appraisal-related update: Review and add to loan file"
                    elif "rate" in subject_lower or "lock" in subject_lower:
                        ai_response = "Rate/Lock update: Verify pricing and update borrower"
                    elif "condition" in subject_lower or "document" in subject_lower:
                        ai_response = "Document request: Forward to borrower or upload to file"
                    elif "closing" in subject_lower:
                        ai_response = "Closing update: Verify dates and notify parties"

                loan_stage = None
                if item.match_entity_type == "loan" and item.match_entity_id in loans_map:
                    loan = loans_map[item.match_entity_id]
                    loan_stage = str(loan.stage) if loan.stage else None

                unified_tasks.append({
                    "id": item.id,
                    "source": "reconciliation",
                    "title": event.subject if event else "Email to Review",
                    "description": f"From: {event.sender if event else 'Unknown'}\n\n{(event.raw_text or '')[:300]}..." if event else "",
                    "client_name": borrower_name or entity_name or (event.sender if event else None),
                    "ai_confidence": int((item.ai_confidence or 0.5) * 100),
                    "ai_suggested_response": ai_response,
                    "priority": "high" if (item.ai_confidence or 0) < 0.7 else "medium",
                    "due_date": None,
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                    "entity_type": item.match_entity_type,
                    "entity_id": item.match_entity_id,
                    "email_from": event.sender if event else None,
                    "email_subject": event.subject if event else None,
                    "stage": loan_stage or "AI Engine",
                    "owner": "Loan Officer",
                    "communication_count": 0
                })
        except Exception as e:
            logger.exception("unified-tasks: failed to load reconciliation source: %s", e)

        # Sort by priority and due date
        priority_order = {"high": 0, "medium": 1, "low": 2}
        unified_tasks.sort(key=lambda x: (
            priority_order.get(x.get("priority", "medium"), 1),
            x.get("due_date") or "9999-12-31"
        ))

        result = {
            "status": "success",
            "total_count": len(unified_tasks),
            "tasks": unified_tasks,
            "counts_by_source": {
                "task": len([t for t in unified_tasks if t["source"] == "task"]),
                "workflow": len([t for t in unified_tasks if t["source"] == "workflow"]),
                "reconciliation": len([t for t in unified_tasks if t["source"] == "reconciliation"])
            }
        }

        # Cache for 30 seconds
        set_cached(cache_k, result, 30)

        return result

    except Exception as e:
        logger.error(f"Error fetching unified tasks: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/disposition-tasks/{task_id}/apply")
async def apply_disposition_task(
    task_id: int,
    body: dict = Body(default={}),
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Apply a Salesforce disposition task — updates loan stage and stamps SLA date.
    """
    main = get_main_module()
    Task = main.Task
    Loan = main.Loan

    task = db.query(Task).filter(Task.id == task_id, Task.organization_id == current_user.organization_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if not task.sf_proposed_stage:
        raise HTTPException(status_code=400, detail="Not a disposition task")
    if task.status != "pending":
        raise HTTPException(status_code=400, detail=f"Task already {task.status}")

    loan = db.query(Loan).filter(Loan.id == task.loan_id, Loan.organization_id == current_user.organization_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    # Parse optional disposition_date or default to now
    disposition_date_str = body.get("disposition_date")
    if disposition_date_str:
        try:
            disposition_dt = datetime.fromisoformat(disposition_date_str)
        except (ValueError, TypeError):
            disposition_dt = datetime.now(timezone.utc)
    else:
        disposition_dt = datetime.now(timezone.utc)

    old_stage = str(loan.stage) if loan.stage else None

    try:
        # 1. Update loan stage
        loan.stage = task.sf_proposed_stage
        loan.stage_changed_at = disposition_dt

        # 2. Stamp SLA date field
        sla_date_field = task.sla_date_field
        date_stamped = None
        if sla_date_field and hasattr(loan, sla_date_field):
            setattr(loan, sla_date_field, disposition_dt)
            date_stamped = sla_date_field

        # 3. Mark task as completed
        task.status = "completed"
        task.disposition_action = "applied"
        task.disposition_date = datetime.now(timezone.utc)
        task.disposition_by = current_user.id
        task.completed_at = datetime.now(timezone.utc)

        # 4. Write audit log
        try:
            db.execute(text("""
                INSERT INTO loan_state_audit_log (
                    loan_id, from_stage, to_stage, action,
                    is_backward_movement, warnings, metadata, created_at
                ) VALUES (
                    :loan_id, :from_stage, :to_stage, 'disposition_applied',
                    false, '[]',
                    :metadata, NOW()
                )
            """), {
                "loan_id": loan.id,
                "from_stage": old_stage,
                "to_stage": task.sf_proposed_stage,
                "metadata": json.dumps({
                    "task_id": task_id,
                    "applied_by": current_user.id,
                    "sla_date_field": sla_date_field,
                    "disposition_date": disposition_dt.isoformat(),
                }),
            })
        except Exception as audit_err:
            logger.warning(f"Could not write audit log for disposition apply: {audit_err}")

        # 5. Track SLA stage change
        try:
            from services.sla_tracking_service import track_loan_stage_change
            track_loan_stage_change(
                db=db,
                loan_id=loan.id,
                old_stage=old_stage,
                new_stage=task.sf_proposed_stage,
                user_id=current_user.id,
                loan_number=loan.loan_number,
                organization_id=getattr(loan, 'organization_id', None),
            )
        except Exception as sla_err:
            logger.warning(f"SLA tracking after disposition apply failed: {sla_err}")

        # 6. If FUNDED, trigger MUM promotion
        if task.sf_proposed_stage == "FUNDED":
            try:
                from services.mum_promotion_service import maybe_promote_loan_to_mum
                maybe_promote_loan_to_mum(db=db, loan_id=loan.id, user_id=current_user.id)
            except Exception as mum_err:
                logger.warning(f"MUM promotion after disposition apply failed: {mum_err}")

        db.commit()

        # Event-driven workflow enrollment (eliminates 60s polling delay)
        try:
            from services.workflow_scheduler import trigger_workflow_evaluation_for_loan
            trigger_workflow_evaluation_for_loan(
                db, loan.id, task.sf_proposed_stage,
                user_id=current_user.id,
            )
        except Exception as e:
            logger.warning(f"Workflow evaluation trigger failed for loan {loan.id} disposition: {e}")

        # Invalidate unified-tasks + dashboard cache
        try:
            from performance_cache import cache_key, invalidate_cache, invalidate_dashboard
            invalidate_cache(cache_key("unified_tasks", current_user.id))
            invalidate_dashboard(current_user.id)
        except Exception as e:
            logger.warning(f"Error invalidating cache after apply: {e}")

        return {
            "status": "applied",
            "task_id": task_id,
            "loan_id": loan.id,
            "new_stage": task.sf_proposed_stage,
            "old_stage": old_stage,
            "sla_date_field": date_stamped,
            "date_stamped": disposition_dt.isoformat() if date_stamped else None,
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Error applying disposition task {task_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/disposition-tasks/{task_id}/dismiss")
async def dismiss_disposition_task(
    task_id: int,
    body: dict = Body(default={}),
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Dismiss a Salesforce disposition task — stage stays unchanged, reason logged.
    """
    main = get_main_module()
    Task = main.Task

    task = db.query(Task).filter(Task.id == task_id, Task.organization_id == current_user.organization_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if not task.sf_proposed_stage:
        raise HTTPException(status_code=400, detail="Not a disposition task")
    if task.status != "pending":
        raise HTTPException(status_code=400, detail=f"Task already {task.status}")

    reason = body.get("reason", "")

    try:
        # Mark task as completed (dismissed)
        task.status = "completed"
        task.disposition_action = "dismissed"
        task.disposition_date = datetime.now(timezone.utc)
        task.disposition_by = current_user.id
        task.completed_at = datetime.now(timezone.utc)

        # Write audit log
        try:
            db.execute(text("""
                INSERT INTO loan_state_audit_log (
                    loan_id, from_stage, to_stage, action,
                    is_backward_movement, warnings, metadata, created_at
                ) VALUES (
                    :loan_id, :from_stage, :to_stage, 'disposition_dismissed',
                    false, '[]',
                    :metadata, NOW()
                )
            """), {
                "loan_id": task.loan_id,
                "from_stage": task.sf_current_stage,
                "to_stage": task.sf_proposed_stage,
                "metadata": json.dumps({
                    "task_id": task_id,
                    "dismissed_by": current_user.id,
                    "reason": reason,
                }),
            })
        except Exception as audit_err:
            logger.warning(f"Could not write audit log for disposition dismiss: {audit_err}")

        db.commit()

        # Invalidate unified-tasks + dashboard cache
        try:
            from performance_cache import cache_key, invalidate_cache, invalidate_dashboard
            invalidate_cache(cache_key("unified_tasks", current_user.id))
            invalidate_dashboard(current_user.id)
        except Exception as e:
            logger.warning(f"Error invalidating cache after dismiss: {e}")

        return {
            "status": "dismissed",
            "task_id": task_id,
            "loan_id": task.loan_id,
            "dismissed_stage": task.sf_proposed_stage,
            "current_stage": task.sf_current_stage,
            "reason": reason,
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Error dismissing disposition task {task_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/unified-tasks/{task_id}/approve")
async def approve_unified_task(
    task_id: int,
    approval: dict = Body(...),
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Approve a unified task and train AI with feedback.
    """
    main = get_main_module()
    AITask = main.AITask
    Task = main.Task
    TaskType = main.TaskType
    Lead = main.Lead
    ExtractedData = main.ExtractedData
    AITrainingEvent = main.AITrainingEvent

    try:
        from performance_cache import cache_key, invalidate_cache
        source = approval.get("source")
        approved_response = approval.get("approved_response")
        feedback = approval.get("feedback")
        communication_method = approval.get("communication_method")  # email, text, phone, voicemail
        contact_successful = approval.get("contact_successful", False)  # True if contact was made

        if source == "task":
            # Mark AI task as completed
            task = db.query(AITask).filter(
                AITask.id == task_id,
                AITask.assigned_to_id == current_user.id
            ).first()

            if not task:
                raise HTTPException(status_code=404, detail="Task not found")

            task.type = TaskType.COMPLETED
            task.completed_at = datetime.now(timezone.utc)
            task.completed_action = approved_response
            if feedback:
                task.feedback = feedback

            # Store training data for AI improvement
            training = AITrainingEvent(
                field_name="task_response",
                original_value=task.suggested_action or "",
                corrected_value=approved_response or task.suggested_action or "",
                label="approved",
                user_id=current_user.id
            )
            db.add(training)

        elif source == "workflow":
            # Mark workflow task as completed
            task = db.query(Task).filter(
                Task.id == task_id,
                Task.owner_id == current_user.id
            ).first()

            if not task:
                raise HTTPException(status_code=404, detail="Task not found")

            task.status = "completed"
            task.completed_at = datetime.now(timezone.utc)

            # Update lead milestone dates when workflow task is completed
            if task.lead_id:
                # Defense-in-depth: org_id filter to prevent cross-tenant access
                lead_query = db.query(Lead).filter(Lead.id == task.lead_id)
                _org_id = getattr(current_user, 'organization_id', None)
                if _org_id:
                    lead_query = lead_query.filter(Lead.organization_id == _org_id)
                lead = lead_query.first()
                if lead:
                    now = datetime.now(timezone.utc)

                    # If a communication method was used, this was a contact attempt
                    if communication_method or "Day" in (task.title or ""):
                        # Set first_contact_attempt_date if not already set
                        if not lead.first_contact_attempt_date:
                            lead.first_contact_attempt_date = now
                            logger.info(f"Set first_contact_attempt_date for lead {lead.id} from completed task {task_id}")

                        # If contact was successful, set first_contact_successful_date
                        if contact_successful and not lead.first_contact_successful_date:
                            lead.first_contact_successful_date = now
                            logger.info(f"Set first_contact_successful_date for lead {lead.id} from completed task {task_id}")

                    # If task title indicates specific milestone, update that date
                    task_title_lower = (task.title or "").lower()
                    if "application" in task_title_lower and "link" in task_title_lower and not lead.application_link_sent_date:
                        lead.application_link_sent_date = now
                        logger.info(f"Set application_link_sent_date for lead {lead.id}")
                    elif "credit" in task_title_lower and "pull" in task_title_lower and not lead.credit_pulled_date:
                        lead.credit_pulled_date = now
                        logger.info(f"Set credit_pulled_date for lead {lead.id}")
                    elif "qualif" in task_title_lower and not lead.lead_qualification_date:
                        lead.lead_qualification_date = now
                        logger.info(f"Set lead_qualification_date for lead {lead.id}")

            # Store training data
            if feedback:
                training = AITrainingEvent(
                    field_name="workflow_response",
                    original_value="",
                    corrected_value=feedback,
                    label="approved",
                    user_id=current_user.id
                )
                db.add(training)

        elif source == "reconciliation":
            # Mark reconciliation item as approved
            extracted = db.query(ExtractedData).filter(
                ExtractedData.id == task_id
            ).first()

            if not extracted:
                raise HTTPException(status_code=404, detail="Item not found")

            extracted.status = "approved"
            extracted.reviewed_by = current_user.id
            extracted.reviewed_at = datetime.now(timezone.utc)

            # Store training data
            for field_name, field_data in (extracted.fields or {}).items():
                training = AITrainingEvent(
                    extracted_data_id=extracted.id,
                    field_name=field_name,
                    original_value=str(field_data.get("value", "")),
                    corrected_value=str(field_data.get("value", "")),
                    label="approved",
                    user_id=current_user.id
                )
                db.add(training)

            if feedback:
                training = AITrainingEvent(
                    extracted_data_id=extracted.id,
                    field_name="user_feedback",
                    original_value="",
                    corrected_value=feedback,
                    label="feedback",
                    user_id=current_user.id
                )
                db.add(training)

        # Feed approval into the confidence graduation system
        confidence_result = None
        try:
            from services.autonomous.confidence_graduation import ConfidenceGraduationService
            org_id = getattr(current_user, "organization_id", None)
            if org_id:
                grad_service = ConfidenceGraduationService(db)
                action_type = f"task_{source}" if source else "task_general"
                confidence_result = grad_service.record_decision(
                    org_id=org_id, action_type=action_type, approved=True,
                )
        except Exception as e:
            logger.debug("Confidence graduation record skipped: %s", e)

        db.commit()

        # Invalidate the unified tasks cache so completed tasks don't reappear
        cache_k = cache_key("unified_tasks", current_user.id)
        invalidate_cache(cache_k)

        logger.info(f"Unified task approved: {source}/{task_id} by user {current_user.id}")

        return {
            "status": "success",
            "message": "Task approved and AI trained",
            "task_id": task_id,
            "source": source,
            "confidence": confidence_result,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving unified task: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/unified-tasks/{task_id}/reject")
async def reject_unified_task(
    task_id: int,
    rejection: dict = Body(...),
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Reject/skip a unified task and optionally train AI with feedback.
    """
    main = get_main_module()
    AITask = main.AITask
    Task = main.Task
    TaskType = main.TaskType
    ExtractedData = main.ExtractedData
    AITrainingEvent = main.AITrainingEvent

    try:
        from performance_cache import cache_key, invalidate_cache
        source = rejection.get("source")
        feedback = rejection.get("feedback", "Rejected by user")

        if source == "task":
            task = db.query(AITask).filter(
                AITask.id == task_id,
                AITask.assigned_to_id == current_user.id
            ).first()

            if not task:
                raise HTTPException(status_code=404, detail="Task not found")

            task.type = TaskType.COMPLETED
            task.completed_at = datetime.now(timezone.utc)
            task.feedback = feedback

            # Store rejection for training
            training = AITrainingEvent(
                field_name="task_response",
                original_value=task.suggested_action or "",
                corrected_value=feedback,
                label="rejected",
                user_id=current_user.id
            )
            db.add(training)

        elif source == "workflow":
            task = db.query(Task).filter(
                Task.id == task_id,
                Task.owner_id == current_user.id
            ).first()

            if not task:
                raise HTTPException(status_code=404, detail="Task not found")

            task.status = "completed"
            task.completed_at = datetime.now(timezone.utc)

        elif source == "reconciliation":
            extracted = db.query(ExtractedData).filter(
                ExtractedData.id == task_id
            ).first()

            if not extracted:
                raise HTTPException(status_code=404, detail="Item not found")

            extracted.status = "rejected"
            extracted.reviewed_by = current_user.id
            extracted.reviewed_at = datetime.now(timezone.utc)

            # Store rejection for training
            training = AITrainingEvent(
                extracted_data_id=extracted.id,
                field_name="rejection_reason",
                original_value="",
                corrected_value=feedback,
                label="rejected",
                user_id=current_user.id
            )
            db.add(training)

        db.commit()

        # Invalidate the unified tasks cache so rejected tasks don't reappear
        cache_k = cache_key("unified_tasks", current_user.id)
        invalidate_cache(cache_k)

        logger.info(f"Unified task rejected: {source}/{task_id} by user {current_user.id}")

        return {
            "status": "success",
            "message": "Task rejected",
            "task_id": task_id,
            "source": source
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rejecting unified task: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# REFERRAL PARTNERS CRUD
# ============================================================================

@router.post("/referral-partners", status_code=201)
async def create_referral_partner(
    partner: Any = Body(...),
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user)
):
    main = get_main_module()
    ReferralPartner = main.ReferralPartner
    ReferralPartnerCreate = main.ReferralPartnerCreate

    try:
        if not isinstance(partner, main.ReferralPartnerCreate):
            partner = ReferralPartnerCreate(**partner)

        partner_data = partner.model_dump()
        # Set required fields from available data (required by DB schema)
        partner_data['business_name'] = partner_data.get('company') or partner_data.get('name') or ""
        partner_data['contact_name'] = partner_data.get('name') or ""
        partner_data['category'] = partner_data.get('type') or "realtor"
        partner_data['owner_id'] = current_user.id  # Set owner to current user
        db_partner = ReferralPartner(**partner_data)
        db.add(db_partner)
        db.commit()
        db.refresh(db_partner)

        logger.info(f"Referral partner created: {db_partner.name}")
        return db_partner
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating referral partner: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create referral partner")


@router.get("/referral-partners")
async def get_referral_partners(
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user)
):
    try:
        main = get_main_module()
        ReferralPartner = main.ReferralPartner
        Lead = main.Lead

        # Filter referral partners by owner - each user sees only their own partners
        query = db.query(ReferralPartner).filter(
            ReferralPartner.owner_id == current_user.id
        )

        # Add search filter if provided
        if search:
            search_term = f"%{search}%"
            query = query.filter(
                or_(
                    ReferralPartner.name.ilike(search_term),
                    ReferralPartner.email.ilike(search_term),
                    ReferralPartner.company.ilike(search_term)
                )
            )

        partners = query.order_by(ReferralPartner.created_at.desc()).offset(skip).limit(limit).all()

        # Calculate actual referral counts from leads table
        result = []
        for partner in partners:
            # Count leads that have this partner as their referral_partner_id
            try:
                actual_referrals_in = db.query(Lead).filter(
                    Lead.referral_partner_id == partner.id
                ).count()
            except Exception as e:
                logger.warning(f"Failed to count referrals for partner {partner.id}: {e}")
                actual_referrals_in = partner.referrals_in or 0

            # Count closed loans and volume via loan_team_members (table may not exist)
            actual_closed_loans = 0
            actual_volume = 0.0
            try:
                closed_loans_result = db.execute(text("""
                    SELECT COUNT(DISTINCT ltm.loan_id)
                    FROM loan_team_members ltm
                    JOIN loans l ON l.id = ltm.loan_id
                    WHERE ltm.referral_partner_id = :partner_id
                    AND l.stage = 'Funded'
                """), {"partner_id": partner.id}).scalar()
                actual_closed_loans = closed_loans_result or 0

                volume_result = db.execute(text("""
                    SELECT COALESCE(SUM(l.amount), 0)
                    FROM loan_team_members ltm
                    JOIN loans l ON l.id = ltm.loan_id
                    WHERE ltm.referral_partner_id = :partner_id
                    AND l.stage = 'Funded'
                """), {"partner_id": partner.id}).scalar()
                actual_volume = float(volume_result) if volume_result else 0.0
            except Exception as e:
                logger.warning(f"Failed to query loan_team_members for partner {partner.id}: {e}")
                # Fall back to stored values on the partner record
                actual_closed_loans = partner.closed_loans or 0
                actual_volume = float(partner.volume) if partner.volume else 0.0
                # Rollback the failed statement so subsequent queries work
                db.rollback()

            result.append({
                "id": partner.id,
                "name": partner.name,
                "company": partner.company,
                "type": partner.type,
                "phone": partner.phone,
                "email": partner.email,
                "referrals_in": actual_referrals_in,
                "closed_loans": actual_closed_loans,
                "volume": actual_volume,
                "loyalty_tier": partner.loyalty_tier,
                "partner_category": partner.partner_category or "individual",
                "status": partner.status,
                "created_at": partner.created_at
            })

        return result
    except Exception as e:
        logger.error(f"Error fetching referral partners: {e}")
        db.rollback()
        return []


@router.get("/referral-partners/{partner_id}")
async def get_referral_partner(
    partner_id: int,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user)
):
    main = get_main_module()
    ReferralPartner = main.ReferralPartner

    partner = db.query(ReferralPartner).filter(
        ReferralPartner.id == partner_id,
        ReferralPartner.owner_id == current_user.id
    ).first()
    if not partner:
        raise HTTPException(status_code=404, detail="Referral partner not found")
    return partner


@router.patch("/referral-partners/{partner_id}")
async def update_referral_partner(
    partner_id: int,
    partner_update: Any = Body(...),
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user)
):
    main = get_main_module()
    ReferralPartner = main.ReferralPartner
    ReferralPartnerUpdate = main.ReferralPartnerUpdate

    if not isinstance(partner_update, main.ReferralPartnerUpdate):
        partner_update = ReferralPartnerUpdate(**partner_update)

    partner = db.query(ReferralPartner).filter(
        ReferralPartner.id == partner_id,
        ReferralPartner.owner_id == current_user.id
    ).first()
    if not partner:
        raise HTTPException(status_code=404, detail="Referral partner not found")

    _protected = {'id', 'organization_id', 'created_at', 'updated_at'}
    for key, value in partner_update.dict(exclude_unset=True).items():
        if key in _protected:
            continue
        setattr(partner, key, value)

    db.commit()
    db.refresh(partner)

    logger.info(f"Referral partner updated: {partner.name}")
    return partner


@router.delete("/referral-partners/{partner_id}", status_code=204)
async def delete_referral_partner(
    partner_id: int,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user)
):
    main = get_main_module()
    ReferralPartner = main.ReferralPartner

    partner = db.query(ReferralPartner).filter(
        ReferralPartner.id == partner_id,
        ReferralPartner.owner_id == current_user.id
    ).first()
    if not partner:
        raise HTTPException(status_code=404, detail="Referral partner not found")

    db.delete(partner)
    db.commit()
    logger.info(f"Referral partner deleted: {partner.name}")
    return None


@router.get("/referral-partners/{partner_id}/referrals")
async def get_partner_referrals(
    partner_id: int,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user)
):
    """
    Get all referrals for a partner including:
    1. Leads where referral_partner_id matches the partner
    2. Leads/Loans from applications where the borrower selected this partner as their realtor
    """
    main = get_main_module()
    ReferralPartner = main.ReferralPartner
    Lead = main.Lead

    from models.purl import PURLApplication, PURLWorkspace, PURLLoan

    partner = db.query(ReferralPartner).filter(
        ReferralPartner.id == partner_id,
        ReferralPartner.organization_id == current_user.organization_id
    ).first()
    if not partner:
        raise HTTPException(status_code=404, detail="Referral partner not found")

    referrals = []
    seen_ids = set()

    # 1. Get leads with referral_partner_id matching this partner
    leads_query = db.query(Lead).filter(Lead.referral_partner_id == partner_id).limit(500).all()
    for lead in leads_query:
        if lead.id not in seen_ids:
            seen_ids.add(lead.id)
            referrals.append({
                "id": lead.id,
                "name": lead.name,
                "email": lead.email,
                "phone": lead.phone,
                "stage": lead.stage.value if hasattr(lead.stage, 'value') else str(lead.stage) if lead.stage else None,
                "source": lead.source,
                "loan_purpose": lead.loan_type,
                "loan_amount": lead.loan_amount,
                "property_type": lead.property_type,
                "credit_score": lead.credit_score,
                "created_at": lead.created_at.isoformat() if lead.created_at else None,
                "updated_at": lead.updated_at.isoformat() if hasattr(lead, 'updated_at') and lead.updated_at else None,
                "referral_type": "direct",  # Direct referral partner assignment
                "loan_id": None
            })

    # 2. Get leads where source contains partner name
    if partner.name:
        source_leads = db.query(Lead).filter(
            Lead.source.ilike(f"%{partner.name}%"),
            Lead.referral_partner_id != partner_id  # Avoid duplicates
        ).limit(500).all()
        for lead in source_leads:
            if lead.id not in seen_ids:
                seen_ids.add(lead.id)
                referrals.append({
                    "id": lead.id,
                    "name": lead.name,
                    "email": lead.email,
                    "phone": lead.phone,
                    "stage": lead.stage.value if hasattr(lead.stage, 'value') else str(lead.stage) if lead.stage else None,
                    "source": lead.source,
                    "loan_purpose": lead.loan_type,
                    "loan_amount": lead.loan_amount,
                    "property_type": lead.property_type,
                    "credit_score": lead.credit_score,
                    "created_at": lead.created_at.isoformat() if lead.created_at else None,
                    "updated_at": lead.updated_at.isoformat() if hasattr(lead, 'updated_at') and lead.updated_at else None,
                    "referral_type": "source_match",
                    "loan_id": None
                })

    # 3. Get applications where agent_partner_id in declarations matches this partner
    try:
        # Query applications with agent_partner_id in data->declarations
        applications = db.execute(text("""
            SELECT
                pa.id as app_id,
                pa.workspace_id,
                pa.data,
                pw.display_name,
                pw.slug,
                pl.id as loan_id,
                pl.loan_number,
                pl.status as loan_status,
                pl.loan_amount,
                pl.property_address,
                pc.first_name,
                pc.last_name,
                pc.email,
                pc.phone,
                pw.created_at
            FROM purl_applications pa
            JOIN purl_workspaces pw ON pw.id = pa.workspace_id
            LEFT JOIN purl_loans pl ON pl.workspace_id = pa.workspace_id
            LEFT JOIN purl_contacts pc ON pc.workspace_id = pa.workspace_id AND pc.contact_type = 'borrower'
            WHERE pa.data IS NOT NULL
            AND pa.status IN ('submitted', 'in_progress')
        """)).fetchall()

        for app in applications:
            try:
                data = app.data if isinstance(app.data, dict) else json.loads(app.data) if app.data else {}
                declarations = data.get('declarations', {})
                agent_partner_id = declarations.get('agent_partner_id')

                # Check if this application selected this partner as their realtor
                if agent_partner_id and int(agent_partner_id) == partner_id:
                    # Use a unique key for deduplication
                    unique_key = f"app_{app.app_id}"
                    if unique_key not in seen_ids:
                        seen_ids.add(unique_key)

                        # Build borrower name
                        borrower_name = None
                        if app.first_name or app.last_name:
                            borrower_name = f"{app.first_name or ''} {app.last_name or ''}".strip()
                        if not borrower_name:
                            borrower_name = app.display_name

                        # Get loan status
                        loan_status = app.loan_status or 'Application'

                        referrals.append({
                            "id": app.app_id,
                            "name": borrower_name or "Borrower",
                            "email": app.email,
                            "phone": app.phone,
                            "stage": loan_status,
                            "source": "Application - Selected Realtor",
                            "loan_purpose": data.get('loanDetails', {}).get('loanPurpose'),
                            "loan_amount": float(app.loan_amount) if app.loan_amount else data.get('loanDetails', {}).get('loanAmount'),
                            "property_type": data.get('propertyDetails', {}).get('propertyType'),
                            "credit_score": None,
                            "created_at": app.created_at.isoformat() if app.created_at else None,
                            "updated_at": None,
                            "referral_type": "application_selected",  # Borrower selected this realtor in application
                            "loan_id": app.loan_id,
                            "workspace_slug": app.slug
                        })
            except Exception as e:
                logger.warning(f"Error processing application {app.app_id}: {e}")
                continue

    except Exception as e:
        logger.warning(f"Error querying applications for partner referrals: {e}")

    # Sort by created_at descending
    referrals.sort(key=lambda x: x.get('created_at') or '', reverse=True)

    return {
        "partner_id": partner_id,
        "partner_name": partner.name,
        "referrals": referrals,
        "total": len(referrals),
        "by_type": {
            "direct": len([r for r in referrals if r.get('referral_type') == 'direct']),
            "source_match": len([r for r in referrals if r.get('referral_type') == 'source_match']),
            "application_selected": len([r for r in referrals if r.get('referral_type') == 'application_selected'])
        }
    }


# ============================================================================
# LOAN TEAM MEMBERS CRUD
# ============================================================================

@router.get("/loans/{loan_id}/team-members")
async def get_loan_team_members(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user)
):
    """Get all team members for a loan"""
    main = get_main_module()
    Loan = main.Loan

    try:
        # Verify loan exists and belongs to current user's org before querying related data
        loan = db.query(Loan).filter(Loan.id == loan_id, Loan.organization_id == current_user.organization_id).first()
        if not loan:
            raise HTTPException(status_code=404, detail="Loan not found")

        # Get custom team members from the table
        result = db.execute(text("""
            SELECT ltm.*,
                   rp.business_name as partner_business_name,
                   rp.category as partner_category,
                   u.email as user_email,
                   u.first_name || ' ' || u.last_name as user_full_name
            FROM loan_team_members ltm
            LEFT JOIN referral_partners rp ON ltm.referral_partner_id = rp.id
            LEFT JOIN users u ON ltm.user_id = u.id
            WHERE ltm.loan_id = :loan_id
            ORDER BY ltm.created_at DESC
        """), {"loan_id": loan_id})

        team_members = [dict(row._mapping) for row in result.fetchall()]

        # Get standard loan team members from loan record

        standard_members = []
        if loan.loan_officer_name or loan.loan_officer_email:
            standard_members.append({
                "id": f"lo-{loan_id}",
                "name": loan.loan_officer_name or "Loan Officer",
                "role": "Loan Officer",
                "email": loan.loan_officer_email,
                "is_employee": True,
                "is_standard": True
            })
        if loan.processor or loan.processor_email:
            standard_members.append({
                "id": f"proc-{loan_id}",
                "name": loan.processor or "Processor",
                "role": "Processor",
                "email": loan.processor_email,
                "is_employee": True,
                "is_standard": True
            })
        if loan.underwriter or loan.underwriter_email:
            standard_members.append({
                "id": f"uw-{loan_id}",
                "name": loan.underwriter or "Underwriter",
                "role": "Underwriter",
                "email": loan.underwriter_email,
                "is_employee": True,
                "is_standard": True
            })
        if loan.closer or loan.closer_email:
            standard_members.append({
                "id": f"closer-{loan_id}",
                "name": loan.closer or "Closer",
                "role": "Closer",
                "email": loan.closer_email,
                "is_employee": True,
                "is_standard": True
            })

        return {
            "team_members": team_members,
            "standard_members": standard_members,
            "total": len(team_members) + len(standard_members)
        }
    except Exception as e:
        logger.error(f"Error fetching loan team members: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/loans/{loan_id}/team-members")
async def create_loan_team_member(
    loan_id: int,
    member: Any = Body(...),
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user)
):
    """Add a new team member to a loan"""
    main = get_main_module()
    Loan = main.Loan
    LoanTeamMember = main.LoanTeamMember
    LoanTeamMemberCreate = main.LoanTeamMemberCreate
    ReferralPartner = main.ReferralPartner

    try:
        if not isinstance(member, main.LoanTeamMemberCreate):
            member = LoanTeamMemberCreate(**member)

        # Verify loan exists and belongs to current user's org
        loan = db.query(Loan).filter(Loan.id == loan_id, Loan.organization_id == current_user.organization_id).first()
        if not loan:
            raise HTTPException(status_code=404, detail="Loan not found")

        referral_partner_id = None

        # If non-employee, create/link as referral partner
        if not member.is_employee and member.create_as_partner:
            # Check if partner already exists by email
            existing_partner = None
            if member.email:
                existing_partner = db.query(ReferralPartner).filter(
                    ReferralPartner.email == member.email
                ).first()

            if existing_partner:
                referral_partner_id = existing_partner.id
                logger.info(f"Linked existing referral partner: {existing_partner.name}")
            else:
                # Create new referral partner
                new_partner = ReferralPartner(
                    name=member.name,
                    business_name=member.company or member.name,
                    contact_name=member.name,
                    category=member.role.lower().replace(' ', '_'),
                    company=member.company,
                    type=member.role,
                    phone=member.phone,
                    email=member.email,
                    status="active"
                )
                db.add(new_partner)
                db.flush()  # Get the ID
                referral_partner_id = new_partner.id
                logger.info(f"Created new referral partner: {member.name} ({member.role})")

        # Create the team member
        db_member = LoanTeamMember(
            loan_id=loan_id,
            name=member.name,
            role=member.role,
            email=member.email,
            phone=member.phone,
            company=member.company,
            license_number=member.license_number,
            notes=member.notes,
            is_employee=member.is_employee,
            user_id=member.user_id,
            referral_partner_id=referral_partner_id,
            is_new=True,
            created_by=current_user.id
        )

        db.add(db_member)
        db.commit()
        db.refresh(db_member)

        logger.info(f"Team member added to loan {loan_id}: {member.name} ({member.role})")

        # TRIGGER: If this is a realtor role, check if portal automation should run
        portal_automation_result = None
        role_lower = member.role.lower() if member.role else ""
        is_realtor_role = any(keyword in role_lower for keyword in ['realtor', 'buyer', 'listing', 'agent', 'seller'])

        if is_realtor_role and member.email and not member.is_employee:
            try:
                from services.contract_portal_automation_service import ContractPortalAutomationService
                from services.notification_service import NotificationService

                # Determine realtor type
                if any(keyword in role_lower for keyword in ['listing', 'seller']):
                    realtor_type = "listing_agent"
                else:
                    realtor_type = "buyers_agent"

                notification_service = NotificationService()
                automation_service = ContractPortalAutomationService(db, notification_service)

                realtor_info = {
                    "name": member.name,
                    "email": member.email,
                    "phone": member.phone,
                    "company": member.company,
                    "partner_id": referral_partner_id
                }

                portal_automation_result = automation_service.on_realtor_added(
                    loan_id=loan_id,
                    realtor_type=realtor_type,
                    realtor_info=realtor_info
                )
                logger.info(f"Portal automation triggered for {realtor_type} on loan {loan_id}: {portal_automation_result}")
            except Exception as automation_error:
                logger.error(f"Portal automation failed for loan {loan_id}: {automation_error}")
                portal_automation_result = {"error": str(automation_error)}

        return {
            "success": True,
            "team_member": {
                "id": db_member.id,
                "loan_id": db_member.loan_id,
                "name": db_member.name,
                "role": db_member.role,
                "email": db_member.email,
                "phone": db_member.phone,
                "company": db_member.company,
                "is_employee": db_member.is_employee,
                "referral_partner_id": db_member.referral_partner_id,
                "is_new": db_member.is_new,
                "created_at": db_member.created_at.isoformat() if db_member.created_at else None
            },
            "referral_partner_created": referral_partner_id is not None and not member.is_employee,
            "portal_automation": portal_automation_result
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating loan team member: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.patch("/loans/{loan_id}/team-members/{member_id}")
async def update_loan_team_member(
    loan_id: int,
    member_id: int,
    member_update: Any = Body(...),
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user)
):
    """Update a team member"""
    main = get_main_module()
    LoanTeamMember = main.LoanTeamMember
    LoanTeamMemberUpdate = main.LoanTeamMemberUpdate
    ReferralPartner = main.ReferralPartner

    try:
        if not isinstance(member_update, main.LoanTeamMemberUpdate):
            member_update = LoanTeamMemberUpdate(**member_update)

        member = db.query(LoanTeamMember).filter(
            LoanTeamMember.id == member_id,
            LoanTeamMember.loan_id == loan_id
        ).first()

        if not member:
            raise HTTPException(status_code=404, detail="Team member not found")

        # Update fields
        update_data = member_update.dict(exclude_unset=True)
        for key, value in update_data.items():
            setattr(member, key, value)

        # Also update linked referral partner if exists
        if member.referral_partner_id and not member.is_employee:
            partner = db.query(ReferralPartner).filter(
                ReferralPartner.id == member.referral_partner_id
            ).first()
            if partner:
                if 'name' in update_data:
                    partner.name = update_data['name']
                    partner.contact_name = update_data['name']
                if 'email' in update_data:
                    partner.email = update_data['email']
                if 'phone' in update_data:
                    partner.phone = update_data['phone']
                if 'company' in update_data:
                    partner.company = update_data['company']
                    partner.business_name = update_data['company'] or partner.name

        db.commit()
        db.refresh(member)

        logger.info(f"Team member updated: {member.name}")

        return {
            "success": True,
            "team_member": {
                "id": member.id,
                "loan_id": member.loan_id,
                "name": member.name,
                "role": member.role,
                "email": member.email,
                "phone": member.phone,
                "company": member.company,
                "is_employee": member.is_employee,
                "referral_partner_id": member.referral_partner_id,
                "is_new": member.is_new
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating team member: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/loans/{loan_id}/team-members/{member_id}")
async def delete_loan_team_member(
    loan_id: int,
    member_id: int,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user)
):
    """Delete a team member (does not delete linked referral partner)"""
    main = get_main_module()
    LoanTeamMember = main.LoanTeamMember

    try:
        member = db.query(LoanTeamMember).filter(
            LoanTeamMember.id == member_id,
            LoanTeamMember.loan_id == loan_id
        ).first()

        if not member:
            raise HTTPException(status_code=404, detail="Team member not found")

        member_name = member.name
        db.delete(member)
        db.commit()

        logger.info(f"Team member deleted: {member_name}")

        return {"success": True, "message": f"Team member '{member_name}' removed"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting team member: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/loans/{loan_id}/team-members/{member_id}/mark-viewed")
async def mark_team_member_viewed(
    loan_id: int,
    member_id: int,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user)
):
    """Mark a team member as viewed (removes NEW badge)"""
    main = get_main_module()
    LoanTeamMember = main.LoanTeamMember

    try:
        member = db.query(LoanTeamMember).filter(
            LoanTeamMember.id == member_id,
            LoanTeamMember.loan_id == loan_id
        ).first()

        if member:
            member.is_new = False
            db.commit()

        return {"success": True}
    except Exception as e:
        logger.error(f"Error marking team member viewed: {e}")
        return {"success": False}
