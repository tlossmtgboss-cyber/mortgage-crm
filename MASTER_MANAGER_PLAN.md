# Master Manager Platform - Implementation Plan

## Executive Summary

The Master Manager Platform is a comprehensive Talent & Capacity OS for mortgage operations. It governs human capital allocation, performance tracking, and talent acquisition through a unified command-and-control interface.

**Core Principle:** People belong to systems. Managers oversee systems. The platform enforces standards.

---

## Phase 1: Foundation (Core Infrastructure)

### 1.1 New Database Models

#### `talent_capacity` table - Capacity & Workload Tracking
```python
class TalentCapacity(Base):
    __tablename__ = "talent_capacity"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)

    # Capacity Configuration
    max_files_concurrent = Column(Integer, default=25)  # Max files this person can handle
    max_leads_concurrent = Column(Integer, default=50)  # Max leads
    max_tasks_daily = Column(Integer, default=30)       # Max daily tasks

    # Current State (updated by triggers/jobs)
    current_file_count = Column(Integer, default=0)
    current_lead_count = Column(Integer, default=0)
    current_task_count = Column(Integer, default=0)

    # Derived Metrics
    capacity_percentage = Column(Float, default=0.0)    # 0-100%
    capacity_status = Column(String(20), default="available")  # available, near_capacity, at_capacity, over_capacity

    # Risk Indicators
    burnout_risk_score = Column(Float, default=0.0)     # 0-100
    attrition_risk_score = Column(Float, default=0.0)   # 0-100

    # Availability
    is_available = Column(Boolean, default=True)
    availability_status = Column(String(20), default="active")  # active, on_leave, training, suspended
    return_date = Column(Date, nullable=True)

    # Timestamps
    last_calculated_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
```

#### `talent_performance` table - Performance Metrics
```python
class TalentPerformance(Base):
    __tablename__ = "talent_performance"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    period_type = Column(String(20))  # daily, weekly, monthly, quarterly

    # Volume Metrics
    files_processed = Column(Integer, default=0)
    files_funded = Column(Integer, default=0)
    leads_handled = Column(Integer, default=0)
    tasks_completed = Column(Integer, default=0)

    # Quality Metrics
    error_rate = Column(Float, default=0.0)
    rework_rate = Column(Float, default=0.0)
    borrower_satisfaction = Column(Float)  # NPS or CSAT
    lo_satisfaction = Column(Float)        # Internal satisfaction

    # Efficiency Metrics
    avg_task_duration = Column(Float)      # Minutes
    avg_file_cycle_time = Column(Float)    # Days
    sla_compliance_rate = Column(Float)    # Percentage

    # Communication Metrics
    response_time_avg = Column(Float)      # Minutes
    communication_score = Column(Float)    # 0-100

    # Composite Scores
    overall_score = Column(Float)          # Weighted composite
    performance_grade = Column(String(2))  # A, B, C, D, F

    # Comparison
    vs_benchmark_pct = Column(Float)       # % vs team average
    percentile_rank = Column(Integer)      # 1-100

    created_at = Column(DateTime, default=datetime.utcnow)
```

#### `role_definitions` table - Role Intelligence
```python
class RoleDefinition(Base):
    __tablename__ = "role_definitions"

    id = Column(Integer, primary_key=True)
    role_name = Column(String(100), unique=True)
    role_category = Column(String(50))  # revenue, operations, specialized

    # Capacity Standards
    default_max_files = Column(Integer)
    default_max_leads = Column(Integer)
    default_max_tasks = Column(Integer)

    # Performance Expectations
    expected_throughput = Column(JSON)     # {files_per_month: 8, etc}
    error_tolerance = Column(Float)        # Max acceptable error rate
    learning_curve_days = Column(Integer)  # Expected ramp time

    # Risk Profile
    replacement_difficulty = Column(Integer)  # 1-10
    single_point_failure_risk = Column(Boolean, default=False)

    # Skills & Requirements
    required_skills = Column(JSON)         # ["LOS", "compliance", etc]
    certifications_required = Column(JSON)

    # Failure Patterns
    common_failure_modes = Column(JSON)    # ["overwhelm", "accuracy", etc]

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
```

#### `talent_state` table - Human State Machine
```python
class TalentState(Base):
    __tablename__ = "talent_state"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)

    # Current State
    state = Column(String(30), nullable=False, default="active")
    # States: active, near_capacity, over_capacity, bench_warm, bench_training,
    #         promotion_ready, at_risk, exit_likely, on_leave, suspended

    # State Metadata
    state_reason = Column(String(255))
    state_changed_at = Column(DateTime)
    state_changed_by = Column(Integer, ForeignKey("users.id"))

    # Flags
    is_new_hire = Column(Boolean, default=True)
    is_in_ramp = Column(Boolean, default=True)
    ramp_day = Column(Integer, default=0)
    ramp_completion_date = Column(Date)

    # Promotion Track
    promotion_eligible = Column(Boolean, default=False)
    promotion_readiness_score = Column(Float)
    last_promotion_at = Column(Date)

    # Risk Flags
    has_active_pip = Column(Boolean, default=False)
    pip_start_date = Column(Date)
    pip_end_date = Column(Date)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
```

### 1.2 Capacity Calculation Service

```python
# backend/services/capacity_service.py

class CapacityService:
    """Real-time capacity calculation and workload distribution"""

    async def calculate_user_capacity(self, user_id: int) -> TalentCapacity:
        """Calculate current capacity for a user"""
        # Count active files
        active_files = await self.count_active_loans(user_id)
        active_leads = await self.count_active_leads(user_id)
        active_tasks = await self.count_pending_tasks(user_id)

        # Get user's limits
        capacity = await self.get_or_create_capacity(user_id)

        # Calculate percentage
        file_pct = (active_files / capacity.max_files_concurrent) * 100
        lead_pct = (active_leads / capacity.max_leads_concurrent) * 100
        task_pct = (active_tasks / capacity.max_tasks_daily) * 100

        # Weighted capacity (files matter most)
        overall_pct = (file_pct * 0.5) + (lead_pct * 0.3) + (task_pct * 0.2)

        # Determine status
        if overall_pct >= 100:
            status = "over_capacity"
        elif overall_pct >= 90:
            status = "at_capacity"
        elif overall_pct >= 75:
            status = "near_capacity"
        else:
            status = "available"

        return capacity

    async def get_available_users_for_role(
        self,
        role_name: str,
        min_capacity_pct: float = 25
    ) -> List[dict]:
        """Get users with available capacity for a role"""
        pass

    async def suggest_optimal_assignment(
        self,
        entity_type: str,  # lead, loan, task
        entity_id: int,
        role_needed: str
    ) -> dict:
        """Suggest the best person to assign based on capacity and performance"""
        pass
```

### 1.3 Backend Routes

```python
# backend/routes/master_manager_routes.py

router = APIRouter(prefix="/api/v1/master-manager", tags=["Master Manager"])

# Capacity Command Center
@router.get("/capacity/overview")
async def get_capacity_overview() -> CapacityOverview

@router.get("/capacity/by-role")
async def get_capacity_by_role() -> List[RoleCapacity]

@router.get("/capacity/user/{user_id}")
async def get_user_capacity(user_id: int) -> TalentCapacity

@router.put("/capacity/user/{user_id}")
async def update_user_capacity_limits(user_id: int, limits: CapacityLimits)

# Org Graph
@router.get("/org/graph")
async def get_org_graph() -> OrgGraph

@router.get("/org/coverage-gaps")
async def get_coverage_gaps() -> List[CoverageGap]

@router.get("/org/single-points-of-failure")
async def get_spof_risks() -> List[SPOFRisk]

# Talent State
@router.get("/talent/readiness-board")
async def get_readiness_board() -> ReadinessBoard

@router.get("/talent/bench")
async def get_talent_bench() -> List[BenchMember]

@router.put("/talent/{user_id}/state")
async def update_talent_state(user_id: int, state: TalentStateUpdate)

# Performance
@router.get("/performance/dashboard")
async def get_performance_dashboard() -> PerformanceDashboard

@router.get("/performance/user/{user_id}")
async def get_user_performance(user_id: int, period: str = "monthly")

# Alerts & Risk
@router.get("/alerts")
async def get_master_manager_alerts() -> List[MMAlert]

@router.get("/risk/burnout")
async def get_burnout_risks() -> List[BurnoutRisk]

@router.get("/risk/attrition")
async def get_attrition_risks() -> List[AttritionRisk]
```

---

## Phase 2: Recruiting Engine

### 2.1 Candidate Models

#### `candidates` table
```python
class Candidate(Base):
    __tablename__ = "candidates"

    id = Column(Integer, primary_key=True)

    # Basic Info
    first_name = Column(String(100))
    last_name = Column(String(100))
    email = Column(String(255), unique=True)
    phone = Column(String(20))

    # Source
    source = Column(String(50))  # referral, career_page, linkedin, indeed
    referrer_user_id = Column(Integer, ForeignKey("users.id"))
    campaign_id = Column(String(100))

    # Target Role
    target_role_id = Column(Integer, ForeignKey("role_definitions.id"))

    # Status
    status = Column(String(30), default="new")
    # new, screening, phone_screen, interview, assessment, offer, hired, rejected, withdrawn

    # Talent Profile (intelligence layer)
    talent_profile = Column(JSON)  # Structured scoring

    # Experience
    years_experience = Column(Integer)
    previous_companies = Column(JSON)
    mortgage_experience = Column(Boolean, default=False)

    # Assessment Scores
    vetting_score = Column(Float)
    behavioral_score = Column(Float)
    technical_score = Column(Float)
    culture_fit_score = Column(Float)
    overall_score = Column(Float)

    # Application Behavior (predictive signals)
    time_to_complete_app = Column(Integer)  # Minutes
    instruction_following_score = Column(Float)

    # Timestamps
    applied_at = Column(DateTime, default=datetime.utcnow)
    last_activity_at = Column(DateTime)
    hired_at = Column(DateTime)

    # Soft delete
    is_active = Column(Boolean, default=True)
```

#### `candidate_assessments` table
```python
class CandidateAssessment(Base):
    __tablename__ = "candidate_assessments"

    id = Column(Integer, primary_key=True)
    candidate_id = Column(Integer, ForeignKey("candidates.id"))
    assessment_type = Column(String(50))  # lo_vetting, processor_vetting, behavioral

    # Scores
    total_score = Column(Float)
    passing_threshold = Column(Float)
    passed = Column(Boolean)

    # Detailed Results
    section_scores = Column(JSON)
    responses = Column(JSON)

    # Timing
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    duration_minutes = Column(Integer)

    # Evaluation
    evaluated_by = Column(Integer, ForeignKey("users.id"))
    evaluation_notes = Column(Text)
```

#### `job_postings` table
```python
class JobPosting(Base):
    __tablename__ = "job_postings"

    id = Column(Integer, primary_key=True)

    # Basic Info
    title = Column(String(200))
    slug = Column(String(100), unique=True)
    role_definition_id = Column(Integer, ForeignKey("role_definitions.id"))

    # Content
    description = Column(Text)
    requirements = Column(JSON)
    benefits = Column(JSON)

    # Settings
    is_published = Column(Boolean, default=False)
    is_internal = Column(Boolean, default=False)
    location = Column(String(100))
    employment_type = Column(String(30))  # full_time, part_time, contract

    # Visibility
    published_at = Column(DateTime)
    expires_at = Column(DateTime)

    # Metrics
    views = Column(Integer, default=0)
    applications = Column(Integer, default=0)
```

### 2.2 Recruiting Routes

```python
# backend/routes/recruiting_routes.py

router = APIRouter(prefix="/api/v1/recruiting", tags=["Recruiting"])

# Job Postings
@router.get("/jobs")
@router.post("/jobs")
@router.get("/jobs/{job_id}")
@router.put("/jobs/{job_id}")
@router.delete("/jobs/{job_id}")

# Candidates
@router.get("/candidates")
@router.post("/candidates")  # Apply
@router.get("/candidates/{candidate_id}")
@router.put("/candidates/{candidate_id}/status")

# Pipeline
@router.get("/pipeline")
@router.get("/pipeline/by-stage")

# Assessments
@router.get("/assessments/types")
@router.post("/candidates/{candidate_id}/assessments")
@router.get("/candidates/{candidate_id}/assessments")

# Referrals
@router.post("/referrals")
@router.get("/referrals/leaderboard")

# Public Career Page
@router.get("/public/jobs")
@router.post("/public/apply")
```

---

## Phase 3: Performance & Risk Engine

### 3.1 Performance Calculation Service

```python
class PerformanceService:
    """Calculate and track performance metrics"""

    async def calculate_daily_performance(self, user_id: int, date: date):
        """Calculate daily performance snapshot"""
        pass

    async def calculate_weekly_rollup(self, user_id: int, week_start: date):
        """Roll up daily metrics to weekly"""
        pass

    async def calculate_monthly_rollup(self, user_id: int, month: date):
        """Roll up weekly metrics to monthly"""
        pass

    async def calculate_performance_grade(self, user_id: int) -> str:
        """Calculate A-F grade based on composite metrics"""
        pass

    async def identify_promotion_candidates(self) -> List[dict]:
        """Find users ready for promotion based on metrics"""
        pass
```

### 3.2 Risk Detection Service

```python
class RiskDetectionService:
    """Detect and flag risk conditions"""

    async def calculate_burnout_risk(self, user_id: int) -> float:
        """Calculate burnout risk based on workload patterns"""
        # Factors:
        # - Sustained high capacity (>85% for 2+ weeks)
        # - Increasing error rates
        # - Declining response times
        # - Overtime patterns
        pass

    async def calculate_attrition_risk(self, user_id: int) -> float:
        """Calculate attrition risk"""
        # Factors:
        # - Tenure (new hires more at risk)
        # - Performance decline
        # - Engagement signals
        # - Manager relationship
        pass

    async def identify_single_points_of_failure(self) -> List[dict]:
        """Find roles/people with no coverage"""
        pass

    async def get_key_person_dependencies(self) -> List[dict]:
        """Identify critical dependencies on individuals"""
        pass
```

---

## Phase 4: Frontend Implementation

### 4.1 Master Manager Dashboard Screens

#### Screen 1: Capacity Command Center
```
/master-manager/capacity

Features:
- Real-time capacity meters for each team member
- Bottleneck indicators (red/yellow/green)
- Surge risk warnings
- Auto-assignment recommendations
- Drill-down to individual workloads
```

#### Screen 2: Org Graph
```
/master-manager/org

Features:
- Interactive org chart (not static boxes)
- Live capacity overlay on each node
- Coverage gap highlighting
- SPOF (single point of failure) warnings
- Cross-training connections
- Manager span visualization
```

#### Screen 3: Talent Readiness Board
```
/master-manager/talent

Features:
- Kanban-style board with states:
  - Active | Near Capacity | Over Capacity
  - Bench (Warm) | Bench (Training)
  - Promotion Ready | At Risk | Exit Likely
- Drag-drop state changes
- State history timeline
- Action recommendations per person
```

#### Screen 4: Performance Dashboard
```
/master-manager/performance

Features:
- Team performance leaderboard
- Individual performance cards
- Trend charts (weekly/monthly)
- Benchmark comparisons
- Grade distribution
- Drill-down to detailed metrics
```

#### Screen 5: Risk & Alerts
```
/master-manager/alerts

Features:
- Alert feed (burnout, attrition, capacity, SLA)
- Risk heatmap by team/role
- Recommended actions
- Historical alerts
- Alert acknowledgment workflow
```

#### Screen 6: Recruiting Pipeline
```
/master-manager/recruiting

Features:
- Kanban pipeline by stage
- Candidate cards with scores
- Assessment results
- Interview scheduling
- Offer management
- Referral tracking
```

### 4.2 Component Structure

```
frontend/src/pages/
├── MasterManager/
│   ├── MasterManagerDashboard.js      # Main entry point
│   ├── CapacityCommandCenter.js       # Screen 1
│   ├── CapacityMeter.js               # Capacity visualization
│   ├── OrgGraph.js                    # Screen 2
│   ├── TalentReadinessBoard.js        # Screen 3
│   ├── PerformanceDashboard.js        # Screen 4
│   ├── RiskAlerts.js                  # Screen 5
│   ├── RecruitingPipeline.js          # Screen 6
│   └── MasterManager.css
│
├── components/master-manager/
│   ├── CapacityCard.js
│   ├── TeamMemberCapacity.js
│   ├── OrgNode.js
│   ├── TalentStateCard.js
│   ├── PerformanceCard.js
│   ├── RiskIndicator.js
│   ├── AlertItem.js
│   └── CandidateCard.js
```

---

## Phase 5: Integration Points

### 5.1 Existing System Integrations

1. **Loan Assignment** - When loans are created/assigned, update capacity
2. **Lead Assignment** - When leads are assigned, update capacity
3. **Task Completion** - When tasks complete, update performance metrics
4. **Workflow System** - Use capacity for smart routing
5. **SLA Tracking** - Feed into performance calculations
6. **User Onboarding** - Initialize capacity and state for new hires

### 5.2 Background Jobs

```python
# Scheduled jobs for Master Manager

# Every 15 minutes
@scheduler.scheduled_job('interval', minutes=15)
async def recalculate_capacities():
    """Recalculate all user capacities"""

# Every hour
@scheduler.scheduled_job('interval', hours=1)
async def detect_risks():
    """Run risk detection algorithms"""

# Daily at 6 AM
@scheduler.scheduled_job('cron', hour=6)
async def calculate_daily_performance():
    """Calculate previous day's performance"""

# Weekly on Sunday
@scheduler.scheduled_job('cron', day_of_week='sun')
async def calculate_weekly_rollups():
    """Roll up weekly performance metrics"""

# Monthly on 1st
@scheduler.scheduled_job('cron', day=1)
async def calculate_monthly_rollups():
    """Roll up monthly performance metrics"""
```

---

## Build Order

### Phase 1: Foundation (First)
1. Create database migration for capacity/performance/state tables
2. Implement CapacityService
3. Create capacity routes
4. Build Capacity Command Center UI
5. Add capacity calculation to loan/lead assignment

### Phase 2: Performance
1. Implement PerformanceService
2. Create performance routes
3. Build Performance Dashboard UI
4. Add performance calculation jobs

### Phase 3: Risk & Alerts
1. Implement RiskDetectionService
2. Create alert routes
3. Build Risk Alerts UI
4. Add risk detection jobs

### Phase 4: Org Graph
1. Build org graph data aggregation
2. Implement SPOF detection
3. Build Org Graph UI

### Phase 5: Talent State Machine
1. Implement state transitions
2. Build Talent Readiness Board UI

### Phase 6: Recruiting (Last)
1. Create candidate models
2. Implement recruiting routes
3. Build career page
4. Build recruiting pipeline UI
5. Implement assessment engines

---

## Key Metrics the Platform Will Track

### Capacity Metrics
- Current capacity utilization (%)
- Files per person
- Leads per person
- Tasks per person

### Performance Metrics
- Files funded per month
- Average cycle time
- Error rate
- SLA compliance
- Borrower satisfaction
- LO satisfaction

### Risk Metrics
- Burnout risk score
- Attrition risk score
- Single points of failure count
- Coverage gaps

### Recruiting Metrics
- Time to hire
- Quality of hire
- Source effectiveness
- Pipeline velocity
- Referral rate

---

## Questions Before Implementation

1. **Internal-only or Platform-first?**
   - Internal: Build for your practice only
   - Platform: Build as future SaaS product (different data isolation)

2. **Role Definitions**
   - Start with which roles? (LO, Processor, PA, etc.)
   - Custom role creation needed?

3. **Performance Benchmarks**
   - Use industry benchmarks or company-specific?
   - How to seed initial performance targets?

4. **Recruiting Scope**
   - Career page needed immediately?
   - Which assessments for which roles?

---

## Files to Create

### Backend
- `backend/models/master_manager_models.py` - All new models
- `backend/migrations/add_master_manager_tables.py` - Migration
- `backend/services/capacity_service.py` - Capacity logic
- `backend/services/performance_service.py` - Performance logic
- `backend/services/risk_detection_service.py` - Risk logic
- `backend/routes/master_manager_routes.py` - API routes
- `backend/routes/recruiting_routes.py` - Recruiting routes
- `backend/jobs/master_manager_jobs.py` - Background jobs

### Frontend
- `frontend/src/pages/MasterManager/` - All screens
- `frontend/src/components/master-manager/` - Components
- `frontend/src/services/masterManagerApi.js` - API service
- `frontend/src/hooks/useMasterManager.js` - React hooks

---

*This plan is ready for implementation. Awaiting confirmation to proceed.*
