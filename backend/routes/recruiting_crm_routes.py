"""
Recruiting CRM API Routes
Multi-year relationship development for Loan Officers and Realtors.

Comprehensive CRM system with:
- Person (LO/Realtor) management
- Relationship intelligence and timing scores
- Signal detection and processing
- Mutual connection graph
- Objection tracking
- Cadence automation
- Playbook triggers
- Task and note management
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Path, Body
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime

from database import get_db
from services.recruiting_workflow_service import RecruitingWorkflowService
from models.recruiting_workflow_models import (
    PersonType, RelationshipStage, CommChannel, EventType,
    ObjectionCategory, SignalType, EdgeType, TaskPriority, TaskStatus,
    PersonCreate, PersonUpdate, Person, PersonSummary,
    SignalCreate, Signal, ObjectionCreate, ObjectionUpdate, Objection,
    CadenceEnrollmentCreate, CadenceEnrollment,
    TaskCreate, TaskUpdate, Task,
    NoteCreate, Note,
    MeetingCreate, MeetingUpdate, Meeting,
    CommOutcomeCreate, CommOutcomeUpdate, CommOutcome,
    PersonEdgeCreate, PersonEdge,
    OrgCreate, OrgUpdate, Org,
    NextBestActionResponse, TimingIntelligence, WorkflowStats
)

router = APIRouter(prefix="/api/v1/recruiting-crm", tags=["Recruiting CRM"])


# =============================================================================
# PERSON ENDPOINTS
# =============================================================================

@router.post("/people", response_model=dict)
async def create_person(
    data: PersonCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new person (LO or Realtor).

    This creates a new recruit profile with:
    - Basic contact information
    - Professional details
    - Initial relationship intelligence record
    - Contact preference record
    """
    service = RecruitingWorkflowService(db)
    return await service.create_person(data)


@router.get("/people", response_model=dict)
async def list_people(
    organization_id: Optional[int] = None,
    person_type: Optional[PersonType] = None,
    relationship_stage: Optional[RelationshipStage] = None,
    owner_user_id: Optional[int] = None,
    min_timing_score: Optional[int] = Query(None, ge=0, le=100),
    search: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    order_by: str = Query("timing_score DESC"),
    db: Session = Depends(get_db)
):
    """
    List people with filters.

    Supports filtering by:
    - person_type: LOAN_OFFICER or REALTOR
    - relationship_stage: DISCOVERED through ACTIVE_PARTNER
    - owner_user_id: Assigned recruiter
    - min_timing_score: Minimum timing score (0-100)
    - search: Search by name, email, or phone
    """
    service = RecruitingWorkflowService(db)
    return await service.list_people(
        organization_id=organization_id,
        person_type=person_type,
        relationship_stage=relationship_stage,
        owner_user_id=owner_user_id,
        min_timing_score=min_timing_score,
        search=search,
        limit=limit,
        offset=offset,
        order_by=order_by
    )


@router.get("/people/hot-leads", response_model=List[dict])
async def get_hot_leads(
    organization_id: Optional[int] = None,
    person_type: Optional[PersonType] = None,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    Get hot leads (timing_score >= 70).

    These are people showing strong intent signals and should be prioritized
    for immediate outreach.
    """
    service = RecruitingWorkflowService(db)
    return await service.get_hot_leads(
        organization_id=organization_id,
        person_type=person_type,
        limit=limit
    )


@router.get("/people/{person_id}", response_model=dict)
async def get_person(
    person_id: str = Path(..., description="Person UUID"),
    db: Session = Depends(get_db)
):
    """Get a person by ID with full details including relationship intelligence."""
    service = RecruitingWorkflowService(db)
    result = await service.get_person(person_id)
    if not result:
        raise HTTPException(status_code=404, detail="Person not found")
    return result


@router.get("/people/{person_id}/summary", response_model=dict)
async def get_person_summary(
    person_id: str = Path(..., description="Person UUID"),
    db: Session = Depends(get_db)
):
    """
    Get person summary with relationship intelligence.

    Includes:
    - Timing score and grade
    - Open objections count
    - Pending tasks count
    - Last outreach date
    - Organization info
    """
    service = RecruitingWorkflowService(db)
    result = await service.get_person_summary(person_id)
    if not result:
        raise HTTPException(status_code=404, detail="Person not found")
    return result


@router.patch("/people/{person_id}", response_model=dict)
async def update_person(
    person_id: str = Path(..., description="Person UUID"),
    data: PersonUpdate = Body(...),
    db: Session = Depends(get_db)
):
    """
    Update a person.

    If relationship_stage is changed, a STAGE_CHANGED event is logged.
    """
    service = RecruitingWorkflowService(db)
    return await service.update_person(person_id, data)


# =============================================================================
# TIMING INTELLIGENCE ENDPOINTS
# =============================================================================

@router.get("/people/{person_id}/timing", response_model=dict)
async def get_timing_intelligence(
    person_id: str = Path(..., description="Person UUID"),
    db: Session = Depends(get_db)
):
    """
    Get timing intelligence for a person.

    Returns:
    - timing_score: 0-100 score indicating readiness
    - timing_grade: HOT (>=70), WARM (>=50), COOL (>=30), COLD (<30)
    - last_signal: Most recent signal detected
    - why_now: AI-generated reason they might switch
    - recent_signals: Last 10 detected signals
    """
    service = RecruitingWorkflowService(db)
    result = await service.get_timing_intelligence(person_id)
    if not result:
        raise HTTPException(status_code=404, detail="Person not found")
    return result


@router.get("/people/{person_id}/next-best-action", response_model=dict)
async def get_next_best_action(
    person_id: str = Path(..., description="Person UUID"),
    db: Session = Depends(get_db)
):
    """
    Get AI-powered next best action recommendation.

    Returns:
    - recommended_channel: Best channel to use
    - recommended_time: Best time to reach out
    - message_goal: What the message should accomplish
    - urgency: HIGH, MEDIUM, or LOW
    - reasoning: Bullets explaining the recommendation
    - open_objection: Current objection to address (if any)
    - top_connection: Mutual connection for warm intro (if any)
    """
    service = RecruitingWorkflowService(db)
    return await service.get_next_best_action(person_id)


@router.get("/people/{person_id}/best-contact-time", response_model=dict)
async def get_best_contact_time(
    person_id: str = Path(..., description="Person UUID"),
    db: Session = Depends(get_db)
):
    """
    Get the best time to contact a person.

    Uses:
    1. Explicit preferences (if set)
    2. Learned optimal times from response history
    3. Persona-based defaults (LO vs Realtor patterns)
    """
    service = RecruitingWorkflowService(db)
    return await service.get_best_contact_time(person_id)


# =============================================================================
# SIGNAL ENDPOINTS
# =============================================================================

@router.post("/signals", response_model=dict)
async def create_signal(
    data: SignalCreate,
    db: Session = Depends(get_db)
):
    """
    Create and process a signal.

    Signals indicate timing intent and affect the timing_score.

    Signal types include:
    - MEETING_INTENT: Clicked calendar, expressed availability
    - TECH_PAIN: Mentioned LOS/CRM issues
    - OPS_PAIN: Processing delays, conditions issues
    - BRANCH_INSTABILITY: Management changes, team issues
    - JOB_CHANGE: Changed roles or companies
    - LENDER_DISSATISFACTION: For Realtors - issues with current lender

    The signal is automatically processed and may trigger playbooks.
    """
    service = RecruitingWorkflowService(db)
    return await service.create_signal(data)


@router.post("/timing/decay", response_model=dict)
async def decay_timing_scores(
    db: Session = Depends(get_db)
):
    """
    Run daily timing score decay job.

    Applies 2% daily decay to all timing scores > 0.
    Should be called by a daily cron job.
    """
    service = RecruitingWorkflowService(db)
    count = await service.decay_timing_scores()
    return {"message": f"Decayed {count} timing scores"}


# =============================================================================
# CONNECTIONS ENDPOINTS
# =============================================================================

@router.post("/connections", response_model=dict)
async def create_person_edge(
    data: PersonEdgeCreate,
    db: Session = Depends(get_db)
):
    """
    Create a relationship edge between two people.

    Edge types include:
    - PAST_DEAL: Worked on a loan together
    - REFERRAL_SENT/RECEIVED: Referral relationship
    - CO_WORKED_WITH: Same team/company
    - SAME_ORG: Currently at same organization
    - INTRO_MADE: One introduced the other
    - SOCIAL_MUTUAL: Connected on social media

    Edges are used for finding warm intro pathways.
    """
    service = RecruitingWorkflowService(db)
    return await service.create_person_edge(
        from_person_id=data.from_person_id,
        to_person_id=data.to_person_id,
        edge_type=data.edge_type,
        strength=data.strength,
        evidence=data.evidence,
        occurred_at=data.occurred_at
    )


@router.get("/people/{person_id}/connections", response_model=List[dict])
async def get_top_connections(
    person_id: str = Path(..., description="Person UUID"),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db)
):
    """
    Get top connections for a person.

    Ordered by total relationship strength.
    Useful for finding warm intro opportunities.
    """
    service = RecruitingWorkflowService(db)
    return await service.get_top_connections(person_id, limit=limit)


@router.get("/connections/mutual", response_model=List[dict])
async def find_mutual_connections(
    person_a_id: str = Query(..., description="First person UUID"),
    person_b_id: str = Query(..., description="Second person UUID"),
    db: Session = Depends(get_db)
):
    """
    Find mutual connections between two people.

    Returns people connected to both person_a and person_b.
    Useful for requesting warm introductions.
    """
    service = RecruitingWorkflowService(db)
    return await service.find_mutual_connections(person_a_id, person_b_id)


# =============================================================================
# OBJECTION ENDPOINTS
# =============================================================================

@router.post("/objections", response_model=dict)
async def create_objection(
    data: ObjectionCreate,
    db: Session = Depends(get_db)
):
    """
    Log an objection for a person.

    Objection categories include:
    - COMPENSATION: Pay, split, commission concerns
    - TECH_STACK: LOS, CRM, tools concerns
    - OPERATIONS: Processing, support concerns
    - TIMING: Not the right time
    - LOYALTY: Happy where they are
    - And more...

    Severity is 1-5 (5 = most severe).
    Auto-sets next_revisit_at based on category.
    """
    service = RecruitingWorkflowService(db)
    return await service.create_objection(data)


@router.get("/people/{person_id}/objections", response_model=List[dict])
async def get_objections(
    person_id: str = Path(..., description="Person UUID"),
    status: Optional[str] = Query(None, description="Filter by status: OPEN, ADDRESSED, RESOLVED"),
    db: Session = Depends(get_db)
):
    """Get objections for a person."""
    service = RecruitingWorkflowService(db)
    return await service.get_objections(person_id, status=status)


@router.patch("/objections/{objection_id}", response_model=dict)
async def update_objection(
    objection_id: str = Path(..., description="Objection UUID"),
    data: ObjectionUpdate = Body(...),
    db: Session = Depends(get_db)
):
    """
    Update an objection.

    When status changes to ADDRESSED or RESOLVED, creates an
    OBJECTION_SOFTENED signal which boosts timing_score.
    """
    service = RecruitingWorkflowService(db)
    return await service.update_objection(
        objection_id,
        status=data.status,
        our_response=data.our_response,
        resolution_notes=data.resolution_notes
    )


@router.get("/objections/due-revisit", response_model=List[dict])
async def get_objections_due_for_revisit(
    organization_id: Optional[int] = None,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """
    Get objections due for revisit.

    Returns open objections where next_revisit_at has passed.
    """
    service = RecruitingWorkflowService(db)
    return await service.get_objections_due_for_revisit(organization_id, limit=limit)


# =============================================================================
# CADENCE ENDPOINTS
# =============================================================================

@router.post("/cadence-enrollments", response_model=dict)
async def enroll_in_cadence(
    data: CadenceEnrollmentCreate,
    db: Session = Depends(get_db)
):
    """
    Enroll a person in a cadence.

    Cadences are automated touch sequences.
    Only one enrollment per person per cadence at a time.
    """
    service = RecruitingWorkflowService(db)
    return await service.enroll_in_cadence(data)


@router.get("/cadences/due", response_model=List[dict])
async def get_cadences_due(
    organization_id: Optional[int] = None,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    """
    Get cadence enrollments that are due for execution.

    Returns enrollments where:
    - status = ACTIVE
    - next_step_due_at <= now
    - person.do_not_contact = false
    """
    service = RecruitingWorkflowService(db)
    return await service.get_cadences_due(organization_id, limit=limit)


@router.post("/cadence-enrollments/{enrollment_id}/advance", response_model=dict)
async def advance_cadence_step(
    enrollment_id: str = Path(..., description="Enrollment UUID"),
    db: Session = Depends(get_db)
):
    """
    Advance a cadence enrollment to the next step.

    If this was the last step, marks enrollment as COMPLETED.
    Otherwise, calculates next_step_due_at based on step timing.
    """
    service = RecruitingWorkflowService(db)
    return await service.advance_cadence_step(enrollment_id)


@router.post("/cadence-enrollments/{enrollment_id}/pause", response_model=dict)
async def pause_cadence(
    enrollment_id: str = Path(..., description="Enrollment UUID"),
    reason: Optional[str] = Body(None),
    pause_until: Optional[datetime] = Body(None),
    db: Session = Depends(get_db)
):
    """
    Pause a cadence enrollment.

    Typically done when:
    - Playbook is triggered (auto-pauses for 14 days)
    - Person replies (if pause_on_reply is set)
    - Meeting is scheduled (if pause_on_meeting is set)
    """
    service = RecruitingWorkflowService(db)
    return await service.pause_cadence(enrollment_id, reason=reason, pause_until=pause_until)


# =============================================================================
# PLAYBOOK ENDPOINTS
# =============================================================================

@router.get("/playbook-runs", response_model=List[dict])
async def get_playbook_runs(
    person_id: Optional[str] = None,
    status: Optional[str] = Query(None, description="Filter by status: STARTED, IN_PROGRESS, COMPLETED, FAILED"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """
    Get playbook runs.

    Playbooks are triggered by timing score thresholds or specific signals.
    They pause cadences and execute high-intent action sequences.
    """
    service = RecruitingWorkflowService(db)
    return await service.get_playbook_runs(person_id=person_id, status=status, limit=limit)


# =============================================================================
# TASK ENDPOINTS
# =============================================================================

@router.post("/tasks", response_model=dict)
async def create_task(
    data: TaskCreate,
    db: Session = Depends(get_db)
):
    """
    Create a task.

    Tasks can be created manually or automatically by playbooks/cadences.
    """
    service = RecruitingWorkflowService(db)
    return await service.create_task(data)


@router.get("/tasks", response_model=List[dict])
async def get_tasks(
    person_id: Optional[str] = None,
    assigned_to: Optional[int] = None,
    status: Optional[TaskStatus] = None,
    overdue_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """
    Get tasks with filters.

    Ordered by priority (URGENT first) then due date.
    """
    service = RecruitingWorkflowService(db)
    return await service.get_tasks(
        person_id=person_id,
        assigned_to=assigned_to,
        status=status,
        overdue_only=overdue_only,
        limit=limit
    )


@router.post("/tasks/{task_id}/complete", response_model=dict)
async def complete_task(
    task_id: str = Path(..., description="Task UUID"),
    outcome: Optional[str] = Body(None),
    outcome_notes: Optional[str] = Body(None),
    db: Session = Depends(get_db)
):
    """
    Complete a task.

    Logs a TASK_COMPLETED event.
    """
    service = RecruitingWorkflowService(db)
    return await service.complete_task(task_id, outcome=outcome, outcome_notes=outcome_notes)


# =============================================================================
# NOTE ENDPOINTS
# =============================================================================

@router.post("/notes", response_model=dict)
async def create_note(
    data: NoteCreate,
    db: Session = Depends(get_db)
):
    """
    Create a note.

    Note types include:
    - general: General notes
    - call_summary: Summary of a phone call
    - meeting_notes: Notes from a meeting
    - research: Research findings
    - objection: Objection-related notes
    """
    service = RecruitingWorkflowService(db)
    return await service.create_note(data)


@router.get("/people/{person_id}/notes", response_model=List[dict])
async def get_notes(
    person_id: str = Path(..., description="Person UUID"),
    note_type: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """Get notes for a person. Pinned notes appear first."""
    service = RecruitingWorkflowService(db)
    return await service.get_notes(person_id, note_type=note_type, limit=limit)


# =============================================================================
# COMMUNICATION OUTCOME ENDPOINTS
# =============================================================================

@router.post("/comm-outcomes", response_model=dict)
async def record_comm_outcome(
    data: CommOutcomeCreate,
    db: Session = Depends(get_db)
):
    """
    Record a communication outcome for learning.

    Call this when sending any outbound communication.
    The system learns optimal contact times from response patterns.
    """
    service = RecruitingWorkflowService(db)
    return await service.record_comm_outcome(data)


@router.patch("/comm-outcomes/{outcome_id}", response_model=dict)
async def update_comm_outcome(
    outcome_id: str = Path(..., description="Outcome UUID"),
    data: CommOutcomeUpdate = Body(...),
    db: Session = Depends(get_db)
):
    """
    Update a communication outcome with response data.

    Call this when:
    - Email is opened (opened_at)
    - Link is clicked (clicked_at)
    - Person replies (replied_at)
    - Meeting is booked (booked_meeting_at)

    Each update adds to the outcome_score and updates contact preference learning.
    """
    service = RecruitingWorkflowService(db)
    return await service.update_comm_outcome(
        outcome_id,
        opened_at=data.opened_at,
        clicked_at=data.clicked_at,
        replied_at=data.replied_at,
        booked_meeting_at=data.booked_meeting_at
    )


# =============================================================================
# EVENT LOG ENDPOINTS
# =============================================================================

@router.get("/events", response_model=List[dict])
async def get_events(
    person_id: Optional[str] = None,
    event_type: Optional[EventType] = None,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """
    Get CRM events.

    Events are the backbone of the orchestration system.
    Every significant action creates an event.
    """
    service = RecruitingWorkflowService(db)
    return await service.get_events(person_id=person_id, event_type=event_type, limit=limit)


# =============================================================================
# STATISTICS ENDPOINTS
# =============================================================================

@router.get("/stats", response_model=dict)
async def get_workflow_stats(
    organization_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """
    Get aggregate workflow statistics.

    Returns:
    - total_people: Total people in system
    - by_type: Count by LOAN_OFFICER/REALTOR
    - by_stage: Count by relationship stage
    - hot_leads: Count with timing_score >= 70
    - warm_leads: Count with timing_score 50-69
    - cadences_active: Active cadence enrollments
    - tasks_pending: Pending tasks
    - tasks_overdue: Overdue tasks
    - meetings_upcoming: Meetings in next 7 days
    - objections_open: Open objections
    - playbook_runs_active: Running playbooks
    """
    service = RecruitingWorkflowService(db)
    return await service.get_workflow_stats(organization_id)
