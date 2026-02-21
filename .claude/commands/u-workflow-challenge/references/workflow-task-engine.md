# Workflow Task Engine — Generating Tasks from SLA Dates

## Overview

The Workflow Task Engine is the piece that actually CREATES tasks for users. It reads the
Important Dates from the client profile, determines what day the loan is on within its current
workflow, and generates the appropriate tasks based on the workflow day configuration.

**If tasks aren't being created, this is the engine that's broken — or more likely, the data
feeding into it is incomplete.**

---

## Database Schema

```sql
-- =====================================================
-- WORKFLOW CONFIGURATIONS
-- Templates that define what happens for each milestone
-- =====================================================

CREATE TABLE IF NOT EXISTS workflow_configurations (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NOT NULL REFERENCES organizations(id),
    
    name VARCHAR(100) NOT NULL,                -- "Prospect Nurture Workflow"
    description TEXT,
    
    -- Which milestone(s) this workflow covers
    -- Multiple milestones can share one workflow
    milestone_type VARCHAR(50) NOT NULL,        -- "NEW_LEAD", "IN_PROCESSING", etc.
    
    -- Is this the default or a custom override?
    is_system_default BOOLEAN DEFAULT false,
    is_active BOOLEAN DEFAULT true,
    
    -- Workflow scope
    applies_to VARCHAR(20) DEFAULT 'all',      -- 'all', 'lead', 'loan'
    
    -- Lead source override (e.g., "Lead Purchase" has its own workflow)
    lead_source_filter VARCHAR(100),            -- NULL = all sources
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_by BIGINT REFERENCES users(id)
);

CREATE INDEX idx_workflow_config_milestone 
    ON workflow_configurations(organization_id, milestone_type, is_active)
    WHERE is_active = true;

-- =====================================================
-- WORKFLOW DAY CONFIGURATIONS
-- What tasks get created on each day of the workflow
-- =====================================================

CREATE TABLE IF NOT EXISTS workflow_day_configs (
    id BIGSERIAL PRIMARY KEY,
    workflow_id BIGINT NOT NULL REFERENCES workflow_configurations(id) ON DELETE CASCADE,
    
    -- Which day in the workflow (1 = Day 1, 2 = Day 2, etc.)
    -- Can also be: 30 = Month 1, 60 = Month 2, 90 = Month 3, etc.
    day_number INTEGER NOT NULL,
    
    -- Human-readable label
    day_label VARCHAR(100),                    -- "First 24 Hours", "Day 2", "Month 2"
    
    -- Communication methods to execute on this day
    -- Each checked method = one separate task
    phone_enabled BOOLEAN DEFAULT false,
    email_enabled BOOLEAN DEFAULT false,
    text_enabled BOOLEAN DEFAULT false,
    realtor_enabled BOOLEAN DEFAULT false,     -- Notify realtor partner
    ai_enabled BOOLEAN DEFAULT false,          -- AI auto-execute
    
    -- Role responsible for this day's tasks
    -- Looks up loan_team_members to find the specific user
    responsible_role VARCHAR(50) NOT NULL,      -- 'LO', 'AA', 'CON', 'JLO', 'PA', 'PRO', etc.
    
    -- Task completion rule
    completion_rule VARCHAR(20) DEFAULT 'all',  -- 'all' = complete every task, 'any' = completing one cancels siblings
    
    -- Priority
    priority VARCHAR(10) DEFAULT 'medium',      -- 'low', 'medium', 'high', 'urgent'
    
    -- Optional: custom task title/description templates
    task_title_template VARCHAR(200),
    task_description_template TEXT,
    
    -- Ordering within same day (if multiple configs for one day)
    sort_order INTEGER DEFAULT 0,
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    CONSTRAINT uq_workflow_day UNIQUE (workflow_id, day_number, responsible_role)
);

CREATE INDEX idx_day_config_lookup 
    ON workflow_day_configs(workflow_id, day_number);

-- =====================================================
-- WORKFLOW INSTANCES
-- Active workflow per loan/lead (links entity to config)
-- =====================================================

CREATE TABLE IF NOT EXISTS workflow_instances (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NOT NULL REFERENCES organizations(id),
    
    -- What entity is this workflow for?
    loan_id BIGINT REFERENCES loans(id) ON DELETE CASCADE,
    lead_id BIGINT REFERENCES leads(id) ON DELETE CASCADE,
    
    -- Which workflow template
    workflow_id BIGINT NOT NULL REFERENCES workflow_configurations(id),
    
    -- State
    status VARCHAR(20) NOT NULL DEFAULT 'active',  -- 'active', 'completed', 'cancelled', 'paused'
    
    -- When did this workflow start? (from Important Dates)
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    cancelled_at TIMESTAMPTZ,
    
    -- Current progress
    current_day INTEGER DEFAULT 0,                  -- Last day that was processed
    last_task_generated_at TIMESTAMPTZ,            -- For idempotency checking
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Only one active workflow per entity per milestone
    CONSTRAINT uq_active_workflow UNIQUE (loan_id, lead_id, workflow_id, status)
);

CREATE INDEX idx_workflow_instance_active 
    ON workflow_instances(organization_id, status)
    WHERE status = 'active';
CREATE INDEX idx_workflow_instance_loan 
    ON workflow_instances(loan_id, status);
CREATE INDEX idx_workflow_instance_lead 
    ON workflow_instances(lead_id, status);

-- =====================================================
-- WORKFLOW TASK INSTANCES
-- Individual generated tasks (the actual work items)
-- =====================================================

CREATE TYPE workflow_task_status AS ENUM (
    'pending', 'completed', 'archived', 'cancelled', 'paused'
);

CREATE TYPE workflow_task_type AS ENUM (
    'phone', 'email', 'text', 'realtor', 'ai', 'internal'
);

CREATE TYPE workflow_route AS ENUM (
    'power_dialer', 'task_screen', 'ai_queue'
);

CREATE TABLE IF NOT EXISTS workflow_task_instances (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NOT NULL REFERENCES organizations(id),
    
    -- Links back to workflow
    workflow_instance_id BIGINT NOT NULL REFERENCES workflow_instances(id) ON DELETE CASCADE,
    day_config_id BIGINT NOT NULL REFERENCES workflow_day_configs(id),
    
    -- Links to entity
    loan_id BIGINT REFERENCES loans(id) ON DELETE CASCADE,
    lead_id BIGINT REFERENCES leads(id) ON DELETE CASCADE,
    
    -- Task details
    title VARCHAR(200) NOT NULL,
    description TEXT,
    task_type workflow_task_type NOT NULL,
    priority VARCHAR(10) DEFAULT 'medium',
    
    -- Assignment
    assigned_role VARCHAR(50) NOT NULL,            -- Role name from day config
    assigned_to_user_id BIGINT REFERENCES users(id),  -- Resolved user
    
    -- Routing
    routed_to workflow_route NOT NULL,
    
    -- Scheduling
    due_at TIMESTAMPTZ NOT NULL,
    day_number INTEGER NOT NULL,                   -- Which workflow day
    
    -- Status tracking
    status workflow_task_status NOT NULL DEFAULT 'pending',
    completed_at TIMESTAMPTZ,
    completed_by_user_id BIGINT REFERENCES users(id),
    archived_at TIMESTAMPTZ,
    archive_reason VARCHAR(50),                    -- 'day_advanced', 'milestone_changed', 'sibling_completed'
    
    -- Sibling task grouping (for "any one" completion rule)
    task_group_key VARCHAR(100),                   -- Same key = sibling tasks
    
    -- AI tracking
    ai_confidence DECIMAL(5,4),                    -- 0.0000 to 1.0000
    ai_auto_completed BOOLEAN DEFAULT false,
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Idempotency: prevent duplicate task generation
    CONSTRAINT uq_workflow_task_generation UNIQUE (
        workflow_instance_id, day_config_id, due_at, task_type, assigned_role
    )
);

CREATE INDEX idx_task_instance_user 
    ON workflow_task_instances(assigned_to_user_id, status, due_at)
    WHERE status = 'pending';
CREATE INDEX idx_task_instance_workflow 
    ON workflow_task_instances(workflow_instance_id, status);
CREATE INDEX idx_task_instance_route 
    ON workflow_task_instances(routed_to, status, organization_id)
    WHERE status = 'pending';
CREATE INDEX idx_task_instance_group 
    ON workflow_task_instances(task_group_key)
    WHERE task_group_key IS NOT NULL AND status = 'pending';
```

---

## Workflow Task Generator — The Cron Engine

```python
class WorkflowTaskGenerator:
    """
    Production-grade task generator.
    
    Runs every 5 minutes. For each organization that just crossed midnight:
    1. Find all active workflow instances
    2. Calculate days_elapsed from Important Dates
    3. Archive previous day's incomplete tasks
    4. Generate new tasks for the current day
    5. Route to power dialer / task screen / AI queue
    6. Assign to correct user via role resolution
    
    KEY DESIGN DECISIONS:
    - Runs every 5 min (not just midnight) to handle multi-timezone
    - Idempotent: safe to run multiple times (UNIQUE constraint prevents dupes)
    - Batched: processes loans in groups of 100 to avoid memory issues
    - Transaction-safe: uses row locking on workflow instances
    - Error-isolated: one loan's failure doesn't stop others
    """
    
    BATCH_SIZE = 100
    MIDNIGHT_WINDOW_MINUTES = 5
    
    def __init__(self, db, biz_day_calc: BusinessDayCalculator):
        self.db = db
        self.biz_day_calc = biz_day_calc
    
    # ─── Entry Point (Cron: every 5 minutes) ───
    
    @cron("*/5 * * * *")
    async def run(self):
        """Main cron entry point."""
        logger.info("WorkflowTaskGenerator: Starting cycle")
        
        orgs = self._get_orgs_needing_generation()
        
        for org in orgs:
            try:
                await self._process_organization(org)
            except Exception as e:
                logger.error(f"Failed to process org {org.id}: {e}", exc_info=True)
        
        logger.info(f"WorkflowTaskGenerator: Completed. Processed {len(orgs)} orgs.")
    
    def _get_orgs_needing_generation(self) -> list:
        """Find orgs where midnight just passed in their timezone."""
        orgs = self.db.query(Organization).filter(
            Organization.is_active == True,
            Organization.timezone.isnot(None)
        ).all()
        
        result = []
        for org in orgs:
            org_tz = pytz.timezone(org.timezone)
            org_now = datetime.now(org_tz)
            
            if org_now.hour == 0 and org_now.minute < self.MIDNIGHT_WINDOW_MINUTES:
                if not self._already_generated_today(org, org_now.date()):
                    result.append(org)
        
        return result
    
    def _already_generated_today(self, org, today) -> bool:
        """Idempotency check: did we already run for this org today?"""
        return self.db.query(WorkflowInstance).filter(
            WorkflowInstance.organization_id == org.id,
            WorkflowInstance.status == 'active',
            WorkflowInstance.last_task_generated_at >= datetime.combine(today, time.min)
        ).first() is not None
    
    # ─── Process One Organization ───
    
    async def _process_organization(self, org):
        """Process all active workflows for one organization."""
        offset = 0
        
        while True:
            instances = self.db.query(WorkflowInstance).filter(
                WorkflowInstance.organization_id == org.id,
                WorkflowInstance.status == 'active'
            ).order_by(
                WorkflowInstance.id
            ).offset(offset).limit(self.BATCH_SIZE).all()
            
            if not instances:
                break
            
            for instance in instances:
                try:
                    await self._process_workflow_instance(instance, org)
                except Exception as e:
                    logger.error(
                        f"Failed to process workflow instance {instance.id}: {e}",
                        exc_info=True
                    )
            
            offset += self.BATCH_SIZE
    
    # ─── Process One Workflow Instance ───
    
    async def _process_workflow_instance(self, instance: WorkflowInstance, org):
        """
        THE CORE LOGIC: Generate tasks for one workflow instance.
        
        This is where Important Dates → Task creation happens.
        """
        with self.db.begin():
            # Lock the instance to prevent concurrent processing
            instance = self.db.query(WorkflowInstance).filter(
                WorkflowInstance.id == instance.id
            ).with_for_update().first()
            
            if not instance or instance.status != 'active':
                return
            
            # ── Step 1: Get the entity (loan or lead) ──
            entity = (
                self.db.query(Loan).get(instance.loan_id) if instance.loan_id
                else self.db.query(Lead).get(instance.lead_id)
            )
            
            if not entity:
                logger.warning(f"Entity not found for workflow instance {instance.id}")
                instance.status = 'cancelled'
                return
            
            # ── Step 2: READ THE IMPORTANT DATES FIELD ──
            # THIS IS THE CRITICAL CONNECTION POINT
            milestone_start = get_milestone_start_date(entity, entity.current_milestone_status)
            
            if milestone_start is None:
                logger.error(
                    f"CANNOT GENERATE TASKS: Important Dates field is NULL "
                    f"for entity {entity.id}, milestone {entity.current_milestone_status}. "
                    f"The date must be stamped in the client profile before tasks can be created."
                )
                return  # STOP HERE — no date = no tasks
            
            # ── Step 3: Calculate days elapsed (business days) ──
            org_tz = pytz.timezone(org.timezone)
            now = datetime.now(org_tz)
            
            days_elapsed = self.biz_day_calc.business_days_between(
                milestone_start, now, org.id
            )
            
            # ── Step 4: Get workflow day config for today ──
            day_config = self.db.query(WorkflowDayConfig).filter(
                WorkflowDayConfig.workflow_id == instance.workflow_id,
                WorkflowDayConfig.day_number == days_elapsed
            ).all()
            
            if not day_config:
                # No tasks configured for this day — that's fine, not every day has tasks
                logger.debug(
                    f"No day config for workflow {instance.workflow_id}, day {days_elapsed}"
                )
                instance.current_day = days_elapsed
                instance.last_task_generated_at = now
                return
            
            # ── Step 5: Archive previous day's incomplete tasks ──
            self._archive_previous_day_tasks(instance, days_elapsed)
            
            # ── Step 6: Generate tasks for each communication method ──
            for config in day_config:
                tasks_to_create = self._expand_communication_methods(config)
                
                for task_def in tasks_to_create:
                    # Resolve the assigned user from the role
                    assigned_user = self._resolve_user_for_role(
                        entity, config.responsible_role
                    )
                    
                    # Determine routing
                    route = self._determine_route(task_def["task_type"])
                    
                    # Create the task (idempotency constraint prevents dupes)
                    try:
                        task = WorkflowTaskInstance(
                            organization_id=org.id,
                            workflow_instance_id=instance.id,
                            day_config_id=config.id,
                            loan_id=instance.loan_id,
                            lead_id=instance.lead_id,
                            title=self._generate_task_title(
                                entity, config, task_def["task_type"], days_elapsed
                            ),
                            description=self._generate_task_description(
                                entity, config, task_def["task_type"]
                            ),
                            task_type=task_def["task_type"],
                            priority=config.priority,
                            assigned_role=config.responsible_role,
                            assigned_to_user_id=assigned_user.id if assigned_user else None,
                            routed_to=route,
                            due_at=now,
                            day_number=days_elapsed,
                            status='pending',
                            task_group_key=(
                                f"{instance.id}_{days_elapsed}_{config.id}"
                                if config.completion_rule == 'any'
                                else None
                            )
                        )
                        self.db.add(task)
                        self.db.flush()
                        
                        logger.info(
                            f"Task created: {task_def['task_type']} for "
                            f"entity {entity.id}, day {days_elapsed}, "
                            f"assigned to {assigned_user.id if assigned_user else 'UNASSIGNED'}"
                        )
                    
                    except IntegrityError:
                        # Idempotency constraint caught a duplicate — this is expected
                        self.db.rollback()
                        logger.debug(f"Duplicate task prevented (idempotency working)")
            
            # ── Step 7: Update instance progress ──
            instance.current_day = days_elapsed
            instance.last_task_generated_at = now
            
            self.db.commit()
    
    # ─── Helper Methods ───
    
    def _archive_previous_day_tasks(self, instance, current_day):
        """
        Archive (not delete) incomplete tasks from previous days.
        When Day 3 arrives and Day 2 tasks weren't done, Day 2 tasks get archived.
        """
        self.db.query(WorkflowTaskInstance).filter(
            WorkflowTaskInstance.workflow_instance_id == instance.id,
            WorkflowTaskInstance.day_number < current_day,
            WorkflowTaskInstance.status == 'pending'
        ).update({
            "status": "archived",
            "archived_at": datetime.now(),
            "archive_reason": "day_advanced"
        })
    
    def _expand_communication_methods(self, config: WorkflowDayConfig) -> list:
        """
        Expand a day config's checked methods into individual task definitions.
        Each checked method = one separate task.
        """
        tasks = []
        
        if config.phone_enabled:
            tasks.append({"task_type": "phone"})
        if config.email_enabled:
            tasks.append({"task_type": "email"})
        if config.text_enabled:
            tasks.append({"task_type": "text"})
        if config.realtor_enabled:
            tasks.append({"task_type": "realtor"})
        if config.ai_enabled:
            tasks.append({"task_type": "ai"})
        
        return tasks
    
    def _determine_route(self, task_type: str) -> str:
        """
        Route tasks to the correct destination.
        Phone → Power Dialer
        Email/Text/Realtor/Internal → Task Screen
        AI → AI Queue (auto-execute at 95%+ confidence)
        """
        routing_map = {
            "phone":    "power_dialer",
            "email":    "task_screen",
            "text":     "task_screen",
            "realtor":  "task_screen",
            "internal": "task_screen",
            "ai":       "ai_queue",
        }
        return routing_map.get(task_type, "task_screen")
    
    def _resolve_user_for_role(self, entity, role: str):
        """
        Find the specific user assigned to this role on this loan/lead.
        
        Resolution order:
        1. loan_team_members: specific person assigned to this role on THIS loan
        2. Team default: default person for this role in the LO's team
        3. Organization default: org-level routing rules
        4. None: task created but unassigned (appears in role's shared queue)
        """
        # 1. Check loan team members
        team_member = self.db.query(LoanTeamMember).filter(
            LoanTeamMember.loan_id == entity.id,
            LoanTeamMember.role == role,
            LoanTeamMember.is_employee == True,
            LoanTeamMember.user_id.isnot(None)
        ).first()
        
        if team_member:
            return self.db.query(User).get(team_member.user_id)
        
        # 2. If the role is "LO", use the assigned LO on the loan
        if role in ("LO", "LOAN_OFFICER"):
            lo_id = getattr(entity, 'assigned_lo_id', None) or getattr(entity, 'user_id', None)
            if lo_id:
                return self.db.query(User).get(lo_id)
        
        # 3. Check team-level defaults
        # (Requires a team_role_defaults table — implement if needed)
        
        # 4. No user found — task will be unassigned
        logger.warning(
            f"No user found for role '{role}' on entity {entity.id}. "
            f"Task will be unassigned."
        )
        return None
    
    def _generate_task_title(self, entity, config, task_type, day_number):
        """Generate a human-readable task title."""
        if config.task_title_template:
            return config.task_title_template.format(
                client_name=self._get_client_name(entity),
                day=day_number,
                task_type=task_type
            )
        
        type_labels = {
            "phone": "📞 Call",
            "email": "📧 Email",
            "text":  "💬 Text",
            "realtor": "🏠 Contact Realtor for",
            "ai": "🤖 AI Action for",
        }
        
        label = type_labels.get(task_type, task_type.title())
        client = self._get_client_name(entity)
        
        return f"{label} {client} (Day {day_number})"
    
    def _generate_task_description(self, entity, config, task_type):
        """Generate task description with context."""
        if config.task_description_template:
            return config.task_description_template.format(
                client_name=self._get_client_name(entity),
                milestone=entity.current_milestone_status,
            )
        
        return (
            f"Workflow task: {task_type} for {self._get_client_name(entity)}\n"
            f"Current milestone: {entity.current_milestone_status}\n"
            f"Assigned role: {config.responsible_role}"
        )
    
    def _get_client_name(self, entity):
        """Get display name for the client."""
        if hasattr(entity, 'borrower_first_name'):
            return f"{entity.borrower_first_name} {entity.borrower_last_name}".strip()
        if hasattr(entity, 'first_name'):
            return f"{entity.first_name} {entity.last_name}".strip()
        return f"Record #{entity.id}"
```

---

## Task Completion & Sibling Cancellation

When a task is completed, handle the "any one" completion rule:

```python
class TaskCompletionService:
    """
    Handles task completion logic including sibling cancellation.
    """
    
    def complete_task(self, task_id: int, completed_by_user_id: int):
        """Complete a workflow task and handle side effects."""
        with self.db.begin():
            task = self.db.query(WorkflowTaskInstance).filter(
                WorkflowTaskInstance.id == task_id
            ).with_for_update().first()
            
            if not task or task.status != 'pending':
                raise ValueError(f"Task {task_id} is not pending")
            
            # Mark complete
            task.status = 'completed'
            task.completed_at = datetime.now()
            task.completed_by_user_id = completed_by_user_id
            
            # Check for sibling cancellation ("any one" rule)
            if task.task_group_key:
                siblings = self.db.query(WorkflowTaskInstance).filter(
                    WorkflowTaskInstance.task_group_key == task.task_group_key,
                    WorkflowTaskInstance.id != task.id,
                    WorkflowTaskInstance.status == 'pending'
                ).all()
                
                for sibling in siblings:
                    sibling.status = 'cancelled'
                    sibling.archived_at = datetime.now()
                    sibling.archive_reason = 'sibling_completed'
                
                logger.info(
                    f"Task {task_id} completed. Cancelled {len(siblings)} sibling tasks."
                )
            
            self.db.commit()
```

---

## Workflow Activation on Milestone Change

```python
class WorkflowEngine:
    """Manages workflow lifecycle."""
    
    def cancel_active_workflows(self, entity):
        """Cancel all active workflows for this entity (called on milestone change)."""
        active = self.db.query(WorkflowInstance).filter(
            (WorkflowInstance.loan_id == entity.id) | (WorkflowInstance.lead_id == entity.id),
            WorkflowInstance.status == 'active'
        ).all()
        
        for instance in active:
            instance.status = 'cancelled'
            instance.cancelled_at = datetime.now()
            
            # Cancel all pending tasks under this instance
            self.db.query(WorkflowTaskInstance).filter(
                WorkflowTaskInstance.workflow_instance_id == instance.id,
                WorkflowTaskInstance.status == 'pending'
            ).update({
                "status": "cancelled",
                "archived_at": datetime.now(),
                "archive_reason": "milestone_changed"
            })
    
    def activate_workflow_for_milestone(self, entity, milestone_type: str):
        """
        Find and activate the correct workflow(s) for a milestone.
        
        A milestone may have multiple workflows (e.g., standard + lead source override).
        """
        # Find matching workflow configurations
        workflows = self.db.query(WorkflowConfiguration).filter(
            WorkflowConfiguration.organization_id == entity.organization_id,
            WorkflowConfiguration.milestone_type == milestone_type,
            WorkflowConfiguration.is_active == True
        ).all()
        
        # If lead source filter exists, prioritize that
        lead_source = getattr(entity, 'lead_source', None)
        
        filtered = [
            w for w in workflows
            if w.lead_source_filter == lead_source or w.lead_source_filter is None
        ]
        
        # Prefer lead-source-specific workflow over generic
        source_specific = [w for w in filtered if w.lead_source_filter == lead_source]
        to_activate = source_specific if source_specific else [w for w in filtered if w.lead_source_filter is None]
        
        if not to_activate:
            logger.warning(
                f"No workflow configuration found for milestone {milestone_type} "
                f"in org {entity.organization_id}. No tasks will be generated."
            )
            return
        
        for workflow in to_activate:
            instance = WorkflowInstance(
                organization_id=entity.organization_id,
                loan_id=entity.id if isinstance(entity, Loan) else None,
                lead_id=entity.id if isinstance(entity, Lead) else None,
                workflow_id=workflow.id,
                status='active',
                started_at=entity.current_milestone_entered_at,
                current_day=0
            )
            self.db.add(instance)
            
            logger.info(
                f"Activated workflow '{workflow.name}' for entity {entity.id}, "
                f"milestone {milestone_type}"
            )
        
        self.db.commit()
```

---

## API Endpoints for Task Screen & Power Dialer

```python
@router.get("/api/tasks/my-tasks")
async def get_my_tasks(
    current_user = Depends(get_current_user),
    status: str = "pending",
    routed_to: str = None
):
    """
    Get tasks assigned to the current user.
    Filtered by status and optionally by routing destination.
    """
    query = db.query(WorkflowTaskInstance).filter(
        WorkflowTaskInstance.assigned_to_user_id == current_user.id,
        WorkflowTaskInstance.status == status
    )
    
    if routed_to:
        query = query.filter(WorkflowTaskInstance.routed_to == routed_to)
    
    tasks = query.order_by(
        WorkflowTaskInstance.priority.desc(),
        WorkflowTaskInstance.due_at.asc()
    ).all()
    
    return tasks


@router.get("/api/power-dialer/queue")
async def get_power_dialer_queue(current_user = Depends(get_current_user)):
    """
    Get phone tasks for the power dialer.
    Only returns tasks routed to power_dialer for the current user.
    """
    tasks = db.query(WorkflowTaskInstance).filter(
        WorkflowTaskInstance.assigned_to_user_id == current_user.id,
        WorkflowTaskInstance.routed_to == 'power_dialer',
        WorkflowTaskInstance.status == 'pending'
    ).order_by(
        WorkflowTaskInstance.priority.desc(),
        WorkflowTaskInstance.due_at.asc()
    ).all()
    
    return tasks
```

---

## Health Check Queries

Use these to diagnose task generation issues:

```sql
-- 1. Are tasks being generated at all?
SELECT DATE(created_at) as gen_date, COUNT(*) as tasks
FROM workflow_task_instances
WHERE created_at >= NOW() - INTERVAL '7 days'
GROUP BY DATE(created_at)
ORDER BY gen_date DESC;

-- 2. Are there active workflow instances?
SELECT wc.name, wi.status, COUNT(*)
FROM workflow_instances wi
JOIN workflow_configurations wc ON wi.workflow_id = wc.id
GROUP BY wc.name, wi.status;

-- 3. Do loans have milestone dates populated?
SELECT id, current_milestone_status, current_milestone_entered_at,
       CASE WHEN current_milestone_entered_at IS NULL THEN '❌ NO DATE' ELSE '✅' END as has_date
FROM loans
WHERE current_milestone_status IS NOT NULL
ORDER BY current_milestone_entered_at DESC NULLS FIRST
LIMIT 50;

-- 4. Task completion rate
SELECT status, COUNT(*), ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) as pct
FROM workflow_task_instances
GROUP BY status;

-- 5. Unassigned tasks (role resolution failed)
SELECT wti.id, wti.title, wti.assigned_role, wti.loan_id
FROM workflow_task_instances wti
WHERE wti.assigned_to_user_id IS NULL
  AND wti.status = 'pending';

-- 6. Scheduler health (is it running?)
SELECT MAX(last_task_generated_at) as last_run,
       NOW() - MAX(last_task_generated_at) as time_since
FROM workflow_instances
WHERE status = 'active';
```
