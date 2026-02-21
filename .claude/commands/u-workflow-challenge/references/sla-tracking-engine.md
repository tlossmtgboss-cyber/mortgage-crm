# SLA Tracking Engine — Reading Dates & Calculating Compliance

## Overview

The SLA Tracking Engine reads the Important Dates from the client profile, compares them against
configured SLA targets, and produces compliance statuses. It feeds its calculations into the
Workflow Engine so tasks can be generated proactively (before SLA deadlines) and reactively
(when SLAs are missed).

**SLA and Workflow operate independently but are coordinated:**
- SLA tracks whether milestones are being completed on time
- Workflow generates the tasks that help users meet those SLAs
- Completing a workflow task can satisfy an SLA requirement
- But an overdue SLA creates ADDITIONAL escalation tasks beyond the standard workflow

---

## Database Schema

```sql
-- =====================================================
-- SLA CONFIGURATIONS
-- Per-user/team/company targets for each milestone
-- =====================================================

CREATE TABLE IF NOT EXISTS sla_configurations (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NOT NULL REFERENCES organizations(id),
    
    -- Scope: who does this SLA apply to?
    -- NULL = org-wide default. Set user_id or team_id for overrides.
    user_id BIGINT REFERENCES users(id),
    team_id BIGINT REFERENCES teams(id),
    
    -- What milestone
    milestone_type VARCHAR(50) NOT NULL,
    
    -- SLA targets (in business days)
    target_days INTEGER NOT NULL,                  -- Must complete within this many business days
    warning_threshold_days INTEGER DEFAULT 2,      -- Alert this many days BEFORE deadline
    
    -- Escalation settings
    escalation_enabled BOOLEAN DEFAULT true,
    escalation_after_days INTEGER,                 -- Escalate if overdue by this many days
    escalation_to_role VARCHAR(50),                -- Who gets escalation (e.g., 'manager')
    
    -- Task generation flags
    create_proactive_task BOOLEAN DEFAULT true,    -- Create task X days before deadline
    create_overdue_task BOOLEAN DEFAULT true,      -- Create task when SLA is missed
    
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Priority: user > team > org. Most specific wins.
    CONSTRAINT uq_sla_config UNIQUE (organization_id, user_id, team_id, milestone_type)
);

CREATE INDEX idx_sla_config_lookup 
    ON sla_configurations(organization_id, milestone_type, is_active)
    WHERE is_active = true;

-- =====================================================
-- COMPANY HOLIDAYS (for business day calculations)
-- =====================================================

CREATE TABLE IF NOT EXISTS company_holidays (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NOT NULL REFERENCES organizations(id),
    holiday_date DATE NOT NULL,
    holiday_name VARCHAR(100),
    is_recurring BOOLEAN DEFAULT false,  -- Same date every year?
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    CONSTRAINT uq_holiday UNIQUE (organization_id, holiday_date)
);

CREATE INDEX idx_holidays_lookup 
    ON company_holidays(organization_id, holiday_date);
```

---

## SLA Configuration Resolution

When the engine needs the SLA target for a specific milestone on a specific loan, it resolves
the most specific configuration:

```python
class SLAConfigResolver:
    """
    Resolves SLA configuration with specificity priority:
    1. User-level (most specific)
    2. Team-level
    3. Organization-level (default)
    
    Every user sets their SLA targets during onboarding.
    If they haven't, team defaults apply.
    If no team defaults, org defaults apply.
    If no org defaults, system defaults apply (hardcoded fallback).
    """
    
    # System-wide fallback defaults (used if nothing else configured)
    SYSTEM_DEFAULTS = {
        "NEW_LEAD":              {"target_days": 1,  "warning_days": 0},
        "ATTEMPTED_CONTACT":     {"target_days": 1,  "warning_days": 0},
        "PRE_QUAL":              {"target_days": 3,  "warning_days": 1},
        "PRE_APPROVAL":          {"target_days": 5,  "warning_days": 2},
        "APPLICATION_RECEIVED":  {"target_days": 3,  "warning_days": 1},
        "DISCLOSED":             {"target_days": 3,  "warning_days": 1},
        "IN_PROCESSING":         {"target_days": 14, "warning_days": 3},
        "UW_SUBMISSION":         {"target_days": 3,  "warning_days": 1},
        "CONDITIONAL_APPROVAL":  {"target_days": 7,  "warning_days": 2},
        "CLEAR_TO_CLOSE":        {"target_days": 5,  "warning_days": 2},
        "CLOSING_SCHEDULED":     {"target_days": 7,  "warning_days": 2},
        "FUNDED":                {"target_days": 3,  "warning_days": 1},
    }
    
    def get_sla_config(
        self,
        org_id: int,
        user_id: int = None,
        team_id: int = None,
        milestone_type: str = None
    ) -> SLAConfig:
        """
        Resolve SLA config with priority: user > team > org > system default.
        """
        # Try user-level first
        if user_id:
            config = self.db.query(SLAConfiguration).filter(
                SLAConfiguration.organization_id == org_id,
                SLAConfiguration.user_id == user_id,
                SLAConfiguration.milestone_type == milestone_type,
                SLAConfiguration.is_active == True
            ).first()
            if config:
                return config
        
        # Try team-level
        if team_id:
            config = self.db.query(SLAConfiguration).filter(
                SLAConfiguration.organization_id == org_id,
                SLAConfiguration.team_id == team_id,
                SLAConfiguration.user_id.is_(None),
                SLAConfiguration.milestone_type == milestone_type,
                SLAConfiguration.is_active == True
            ).first()
            if config:
                return config
        
        # Try org-level
        config = self.db.query(SLAConfiguration).filter(
            SLAConfiguration.organization_id == org_id,
            SLAConfiguration.user_id.is_(None),
            SLAConfiguration.team_id.is_(None),
            SLAConfiguration.milestone_type == milestone_type,
            SLAConfiguration.is_active == True
        ).first()
        if config:
            return config
        
        # Fall back to system defaults
        defaults = self.SYSTEM_DEFAULTS.get(milestone_type, {"target_days": 7, "warning_days": 2})
        return SLAConfig(
            target_days=defaults["target_days"],
            warning_threshold_days=defaults["warning_days"],
            milestone_type=milestone_type,
            is_system_default=True
        )
```

---

## Business Day Calculator

```python
class BusinessDayCalculator:
    """
    Calculates business days between two dates, excluding weekends and company holidays.
    This is used by BOTH the SLA tracker and the Workflow Engine.
    """
    
    def __init__(self, db):
        self.db = db
        self._holiday_cache = {}  # org_id → set of dates
    
    def business_days_between(
        self,
        start_date: datetime,
        end_date: datetime,
        org_id: int
    ) -> int:
        """
        Count business days between start and end (inclusive of start, exclusive of end).
        Excludes weekends (Saturday=5, Sunday=6) and company holidays.
        """
        holidays = self._get_holidays(org_id, start_date.year, end_date.year)
        
        count = 0
        current = start_date.date() if isinstance(start_date, datetime) else start_date
        end = end_date.date() if isinstance(end_date, datetime) else end_date
        
        while current < end:
            # Skip weekends
            if current.weekday() < 5:  # Monday=0 through Friday=4
                # Skip holidays
                if current not in holidays:
                    count += 1
            current += timedelta(days=1)
        
        return count
    
    def add_business_days(
        self,
        start_date: datetime,
        business_days: int,
        org_id: int
    ) -> datetime:
        """
        Add N business days to a start date.
        Used to calculate SLA deadlines from milestone start dates.
        """
        holidays = self._get_holidays(org_id, start_date.year, start_date.year + 1)
        
        current = start_date.date() if isinstance(start_date, datetime) else start_date
        days_added = 0
        
        while days_added < business_days:
            current += timedelta(days=1)
            if current.weekday() < 5 and current not in holidays:
                days_added += 1
        
        # Return as datetime with original time
        return datetime.combine(current, start_date.time() if isinstance(start_date, datetime) else time())
    
    def _get_holidays(self, org_id: int, start_year: int, end_year: int) -> set:
        """Get holidays for org, with caching."""
        cache_key = (org_id, start_year, end_year)
        
        if cache_key not in self._holiday_cache:
            holidays = self.db.query(CompanyHoliday.holiday_date).filter(
                CompanyHoliday.organization_id == org_id,
                extract('year', CompanyHoliday.holiday_date).between(start_year, end_year)
            ).all()
            
            self._holiday_cache[cache_key] = {h.holiday_date for h in holidays}
        
        return self._holiday_cache[cache_key]
```

---

## SLA Status Calculator

This runs on every milestone for every active loan to determine current SLA compliance:

```python
class SLATracker:
    """
    Reads Important Dates from client profiles, calculates days elapsed,
    and determines SLA compliance status for each milestone.
    """
    
    def __init__(self, db, biz_day_calc: BusinessDayCalculator, config_resolver: SLAConfigResolver):
        self.db = db
        self.biz_day_calc = biz_day_calc
        self.config_resolver = config_resolver
    
    def calculate_sla_status(self, entity, milestone_type: str) -> dict:
        """
        Calculate the SLA status for a specific milestone on a loan/lead.
        
        Returns:
        {
            "milestone": "IN_PROCESSING",
            "started_at": "2026-02-15T10:30:00Z",
            "target_deadline": "2026-03-05T10:30:00Z",
            "days_elapsed": 3,
            "target_days": 14,
            "days_remaining": 11,
            "status": "ON_TRACK",           # ON_TRACK | APPROACHING | OVERDUE | COMPLETED
            "percentage_complete": 21.4,
            "needs_proactive_task": false,
            "needs_overdue_task": false
        }
        """
        # ── Read the date from Important Dates ──
        milestone_start = get_milestone_start_date(entity, milestone_type)
        
        if milestone_start is None:
            return {
                "milestone": milestone_type,
                "status": "NO_DATE",
                "error": f"Important Dates field for {milestone_type} is not populated. "
                         f"Cannot calculate SLA until date is stamped."
            }
        
        # ── Get SLA configuration ──
        sla_config = self.config_resolver.get_sla_config(
            org_id=entity.organization_id,
            user_id=getattr(entity, 'assigned_lo_id', None),
            team_id=getattr(entity, 'team_id', None),
            milestone_type=milestone_type
        )
        
        now = datetime.now(get_company_timezone(entity.organization_id))
        
        # ── Calculate business days elapsed ──
        days_elapsed = self.biz_day_calc.business_days_between(
            milestone_start, now, entity.organization_id
        )
        
        # ── Calculate deadline ──
        target_deadline = self.biz_day_calc.add_business_days(
            milestone_start, sla_config.target_days, entity.organization_id
        )
        
        days_remaining = self.biz_day_calc.business_days_between(
            now, target_deadline, entity.organization_id
        )
        
        # ── Determine status ──
        if days_remaining < 0:
            status = "OVERDUE"
        elif days_remaining <= sla_config.warning_threshold_days:
            status = "APPROACHING"
        else:
            status = "ON_TRACK"
        
        # ── Check if tasks need to be created ──
        needs_proactive = (
            sla_config.create_proactive_task 
            and status == "APPROACHING"
            and not self._has_active_sla_task(entity, milestone_type, "proactive")
        )
        
        needs_overdue = (
            sla_config.create_overdue_task
            and status == "OVERDUE"
            and not self._has_active_sla_task(entity, milestone_type, "overdue")
        )
        
        return {
            "milestone": milestone_type,
            "started_at": milestone_start.isoformat(),
            "target_deadline": target_deadline.isoformat(),
            "days_elapsed": days_elapsed,
            "target_days": sla_config.target_days,
            "days_remaining": max(days_remaining, 0),
            "status": status,
            "percentage_complete": round((days_elapsed / sla_config.target_days) * 100, 1) if sla_config.target_days > 0 else 0,
            "needs_proactive_task": needs_proactive,
            "needs_overdue_task": needs_overdue
        }
    
    def recalculate_all_for_entity(self, entity) -> list:
        """
        Recalculate SLA status for ALL milestones on a loan/lead.
        Called after milestone changes and on the SLA Tracking report page.
        """
        results = []
        
        # Calculate for current milestone
        if entity.current_milestone_status:
            current = self.calculate_sla_status(entity, entity.current_milestone_status)
            results.append(current)
            
            # If proactive or overdue task needed, create it
            if current.get("needs_proactive_task"):
                self._create_sla_task(entity, entity.current_milestone_status, "proactive", current)
            if current.get("needs_overdue_task"):
                self._create_sla_task(entity, entity.current_milestone_status, "overdue", current)
        
        # Also calculate for historical milestones (for reporting)
        history = self.db.query(LoanMilestoneHistory).filter(
            LoanMilestoneHistory.loan_id == entity.id,
            LoanMilestoneHistory.completed_at.isnot(None)
        ).all()
        
        for record in history:
            results.append({
                "milestone": record.milestone_type,
                "started_at": record.started_at.isoformat(),
                "completed_at": record.completed_at.isoformat(),
                "target_days": record.sla_target_days,
                "actual_days": record.actual_days,
                "status": record.sla_status,
            })
        
        return results
    
    def _create_sla_task(self, entity, milestone_type, task_kind, sla_data):
        """
        Create an SLA-driven task (proactive warning or overdue alert).
        These are SEPARATE from workflow tasks — they are exception/escalation tasks.
        """
        task_title = (
            f"⚠️ SLA Warning: {milestone_type} approaching deadline"
            if task_kind == "proactive"
            else f"🚨 SLA Overdue: {milestone_type} past deadline by {abs(sla_data['days_remaining'])} days"
        )
        
        # Assign to the LO on the loan, or escalate to manager if overdue
        assigned_to = entity.assigned_lo_id
        if task_kind == "overdue":
            sla_config = self.config_resolver.get_sla_config(
                entity.organization_id, entity.assigned_lo_id, None, milestone_type
            )
            if sla_config.escalation_enabled:
                # Also notify manager
                self._notify_manager(entity, milestone_type, sla_data)
        
        task = Task(
            loan_id=entity.id,
            organization_id=entity.organization_id,
            title=task_title,
            description=f"Milestone: {milestone_type}\n"
                       f"Started: {sla_data['started_at']}\n"
                       f"Deadline: {sla_data['target_deadline']}\n"
                       f"Days Elapsed: {sla_data['days_elapsed']} / {sla_data['target_days']}",
            task_type="internal",
            priority="high" if task_kind == "overdue" else "medium",
            assigned_to_user_id=assigned_to,
            due_at=datetime.now(),
            source="sla_tracker",
            source_reference=f"sla_{task_kind}_{milestone_type}",
            routed_to="task_screen",
            status="pending"
        )
        self.db.add(task)
        self.db.commit()
```

---

## SLA Tracking Report API

```python
@router.get("/api/reports/sla/{loan_id}")
async def get_sla_report(loan_id: int, current_user = Depends(get_current_user)):
    """
    Returns SLA compliance data for the client profile's SLA section
    and the SLA Tracking report page.
    """
    loan = await db.get_loan(loan_id)
    
    sla_data = sla_tracker.recalculate_all_for_entity(loan)
    
    return {
        "loan_id": loan_id,
        "current_milestone": loan.current_milestone_status,
        "milestones": sla_data,
        "overall_compliance": calculate_overall_compliance(sla_data),
        "at_risk_count": sum(1 for m in sla_data if m.get("status") in ("APPROACHING", "OVERDUE")),
    }
```

---

## Integration with Workflow Engine

The SLA Tracker and Workflow Engine are independent but coordinated:

```
SLA Tracker                              Workflow Engine
──────────                               ───────────────
Reads Important Dates ──────────────────→ Reads Important Dates (SAME source)
Calculates days vs target                 Calculates days for task scheduling
Flags APPROACHING / OVERDUE               Generates daily communication tasks
Creates SLA warning/overdue tasks         Creates workflow-defined tasks
Reports compliance metrics                Archives old tasks, creates new ones

         ┌──────────────────────────────┐
         │   Completing a workflow task   │
         │   CAN satisfy an SLA          │
         │                                │
         │   Example:                     │
         │   SLA: "Contact lead within    │
         │         4 hours"               │
         │   Workflow Task: "Day 1 Phone  │
         │         Call"                  │
         │                                │
         │   Completing the Day 1 phone   │
         │   call satisfies both the      │
         │   workflow task AND the SLA.   │
         └──────────────────────────────┘
```

When a workflow task is completed that satisfies an SLA:
1. The task is marked complete in `workflow_task_instances`
2. The SLA tracker recalculates and sees the milestone was completed on time
3. Any proactive/overdue SLA tasks for that milestone are auto-cancelled
4. The milestone history record is updated with `actual_days`
