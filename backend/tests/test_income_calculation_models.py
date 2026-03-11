"""
Test Income Calculation Models

Comprehensive tests for IncomeCalculation, IncomeSource, and
IncomeVerificationTask models covering:
- Model creation for all income type scenarios
- DTI ratio storage and precision
- Qualifying income determination
- Multiple income sources per calculation
- Task assignment, status transitions, and completion workflows
- Income trending data storage and year-over-year analysis
- Override/adjustment tracking via review and approval workflows
- Edge cases (zero income, negative adjustments, very large values)

Uses pytest with in-memory SQLite via SQLAlchemy.
"""

import pytest
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session

from database import Base
from database.models.income_calculation import (
    IncomeCalculation,
    IncomeSource,
    IncomeVerificationTask,
    CalculationType,
    CalculationStatus,
    IncomeSourceType,
    TrendingDirection,
    VerificationStatus,
    VerificationTaskType,
    TaskPriority,
    TaskStatus,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(scope="module")
def engine():
    """Create an in-memory SQLite engine for the test module."""
    eng = create_engine("sqlite:///:memory:")

    # SQLite does not enforce CHECK constraints from SQLAlchemy enums by default.
    # Enable foreign key support for completeness.
    @event.listens_for(eng, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # Create only the three tables under test (plus any Base metadata needed).
    IncomeCalculation.__table__.create(eng, checkfirst=True)
    IncomeSource.__table__.create(eng, checkfirst=True)
    IncomeVerificationTask.__table__.create(eng, checkfirst=True)
    return eng


@pytest.fixture()
def db(engine) -> Session:
    """Provide a transactional database session that rolls back after each test."""
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection)()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


def _make_calculation(db: Session, **overrides) -> IncomeCalculation:
    """Helper to create and flush an IncomeCalculation with sensible defaults."""
    defaults = dict(
        loan_id=1,
        organization_id=100,
        borrower_id=200,
        calculation_type=CalculationType.INITIAL,
        status=CalculationStatus.PENDING,
        total_qualifying_monthly_income=Decimal("8500.00"),
        total_qualifying_annual_income=Decimal("102000.00"),
        calculation_method="standard",
        dti_front_end=Decimal("28.50"),
        dti_back_end=Decimal("36.75"),
        proposed_housing_expense=Decimal("2422.50"),
        total_monthly_obligations=Decimal("3123.75"),
        ai_confidence_score=85,
    )
    defaults.update(overrides)
    calc = IncomeCalculation(**defaults)
    db.add(calc)
    db.flush()
    return calc


def _make_source(db: Session, calculation_id: int, **overrides) -> IncomeSource:
    """Helper to create and flush an IncomeSource with sensible defaults."""
    defaults = dict(
        calculation_id=calculation_id,
        borrower_id=200,
        source_type=IncomeSourceType.W2_EMPLOYMENT,
        employer_name="Acme Corp",
        position_title="Software Engineer",
        employment_start_date=date(2020, 3, 15),
        employment_years=Decimal("4.5"),
        is_primary=True,
        base_monthly_income=Decimal("7000.00"),
        overtime_monthly=Decimal("500.00"),
        bonus_monthly=Decimal("250.00"),
        commission_monthly=Decimal("0.00"),
        other_monthly=Decimal("0.00"),
        total_monthly_income=Decimal("7750.00"),
        total_annual_income=Decimal("93000.00"),
        trending_direction=TrendingDirection.INCREASING,
        year1_income=Decimal("93000.00"),
        year2_income=Decimal("85000.00"),
        year_over_year_change_pct=Decimal("9.41"),
        verification_status=VerificationStatus.UNVERIFIED,
        ai_confidence=90,
    )
    defaults.update(overrides)
    source = IncomeSource(**defaults)
    db.add(source)
    db.flush()
    return source


def _make_task(db: Session, calculation_id: int, loan_id: int = 1, **overrides) -> IncomeVerificationTask:
    """Helper to create and flush an IncomeVerificationTask with sensible defaults."""
    defaults = dict(
        calculation_id=calculation_id,
        loan_id=loan_id,
        organization_id=100,
        task_type=VerificationTaskType.VERIFY_EMPLOYMENT,
        title="Verify employment at Acme Corp",
        description="Confirm current employment status and salary.",
        priority=TaskPriority.MEDIUM,
        status=TaskStatus.OPEN,
    )
    defaults.update(overrides)
    task = IncomeVerificationTask(**defaults)
    db.add(task)
    db.flush()
    return task


# ============================================================================
# 1. IncomeCalculation - Basic Creation
# ============================================================================

@pytest.mark.unit
class TestIncomeCalculationCreation:
    """IncomeCalculation model creation and field storage."""

    def test_create_initial_calculation(self, db: Session):
        """An initial calculation stores all core fields correctly."""
        calc = _make_calculation(db)
        assert calc.id is not None
        assert calc.loan_id == 1
        assert calc.organization_id == 100
        assert calc.borrower_id == 200
        assert calc.calculation_type == CalculationType.INITIAL
        assert calc.status == CalculationStatus.PENDING
        assert calc.calculation_method == "standard"
        assert calc.ai_confidence_score == 85
        assert calc.created_at is not None

    def test_create_recalculation(self, db: Session):
        """A recalculation type is stored correctly."""
        calc = _make_calculation(db, calculation_type=CalculationType.RECALCULATION)
        assert calc.calculation_type == CalculationType.RECALCULATION

    def test_create_final_verification(self, db: Session):
        """A final_verification type is stored correctly."""
        calc = _make_calculation(
            db,
            calculation_type=CalculationType.FINAL_VERIFICATION,
            status=CalculationStatus.COMPLETED,
        )
        assert calc.calculation_type == CalculationType.FINAL_VERIFICATION
        assert calc.status == CalculationStatus.COMPLETED

    def test_ai_metadata_stored(self, db: Session):
        """AI flags, recommendations, and model info are persisted as JSON/strings."""
        calc = _make_calculation(
            db,
            ai_flags=["declining_income", "employment_gap"],
            ai_recommendations=["Request 2-year VOE", "Verify gap explanation"],
            ai_model_used="gpt-4o-2025-01",
            calculation_duration_ms=1250,
        )
        assert calc.ai_flags == ["declining_income", "employment_gap"]
        assert len(calc.ai_recommendations) == 2
        assert calc.ai_model_used == "gpt-4o-2025-01"
        assert calc.calculation_duration_ms == 1250

    def test_source_documents_stored(self, db: Session):
        """Source document IDs are stored as a JSON list."""
        doc_ids = ["doc-001", "doc-002", "doc-003"]
        calc = _make_calculation(db, source_documents=doc_ids)
        assert calc.source_documents == doc_ids


# ============================================================================
# 2. IncomeSource - All Income Types
# ============================================================================

@pytest.mark.unit
class TestIncomeSourceTypes:
    """IncomeSource creation across all income type scenarios."""

    def test_w2_employment_source(self, db: Session):
        """W2 employment source stores base pay and extras."""
        calc = _make_calculation(db)
        src = _make_source(db, calc.id)
        assert src.source_type == IncomeSourceType.W2_EMPLOYMENT
        assert src.employer_name == "Acme Corp"
        assert src.is_primary is True
        assert float(src.base_monthly_income) == 7000.00
        assert float(src.total_monthly_income) == 7750.00

    def test_self_employment_source(self, db: Session):
        """Self-employment source with schedule C / K-1 income."""
        calc = _make_calculation(db, calculation_method="self_employed_avg")
        src = _make_source(
            db,
            calc.id,
            source_type=IncomeSourceType.SELF_EMPLOYMENT,
            employer_name="Smith Consulting LLC",
            position_title="Owner",
            employment_years=Decimal("6.0"),
            base_monthly_income=Decimal("12000.00"),
            overtime_monthly=Decimal("0.00"),
            bonus_monthly=Decimal("0.00"),
            commission_monthly=Decimal("0.00"),
            total_monthly_income=Decimal("12000.00"),
            total_annual_income=Decimal("144000.00"),
            trending_direction=TrendingDirection.VARIABLE,
            year1_income=Decimal("144000.00"),
            year2_income=Decimal("130000.00"),
            year_over_year_change_pct=Decimal("10.77"),
            verification_status=VerificationStatus.PENDING_VOE,
        )
        assert src.source_type == IncomeSourceType.SELF_EMPLOYMENT
        assert src.trending_direction == TrendingDirection.VARIABLE
        assert src.verification_status == VerificationStatus.PENDING_VOE

    def test_retirement_income_sources(self, db: Session):
        """Pension and Social Security retirement income sources."""
        calc = _make_calculation(db)
        pension = _make_source(
            db,
            calc.id,
            source_type=IncomeSourceType.PENSION,
            employer_name="State Teachers Retirement",
            base_monthly_income=Decimal("3200.00"),
            total_monthly_income=Decimal("3200.00"),
            total_annual_income=Decimal("38400.00"),
            is_primary=True,
        )
        ss = _make_source(
            db,
            calc.id,
            source_type=IncomeSourceType.SOCIAL_SECURITY,
            employer_name="SSA",
            base_monthly_income=Decimal("1800.00"),
            total_monthly_income=Decimal("1800.00"),
            total_annual_income=Decimal("21600.00"),
            is_primary=False,
        )
        assert pension.source_type == IncomeSourceType.PENSION
        assert ss.source_type == IncomeSourceType.SOCIAL_SECURITY
        assert float(pension.total_monthly_income) + float(ss.total_monthly_income) == pytest.approx(5000.00)

    def test_commission_income_source(self, db: Session):
        """Commission-heavy income with trending analysis."""
        calc = _make_calculation(db, calculation_method="variable_trending")
        src = _make_source(
            db,
            calc.id,
            source_type=IncomeSourceType.COMMISSION,
            employer_name="RE/MAX Realty",
            position_title="Real Estate Agent",
            base_monthly_income=Decimal("2000.00"),
            commission_monthly=Decimal("8500.00"),
            total_monthly_income=Decimal("10500.00"),
            total_annual_income=Decimal("126000.00"),
            trending_direction=TrendingDirection.DECLINING,
            year1_income=Decimal("126000.00"),
            year2_income=Decimal("155000.00"),
            year_over_year_change_pct=Decimal("-18.71"),
        )
        assert src.source_type == IncomeSourceType.COMMISSION
        assert float(src.commission_monthly) == 8500.00
        assert src.trending_direction == TrendingDirection.DECLINING
        assert float(src.year_over_year_change_pct) == pytest.approx(-18.71)

    def test_all_income_source_types_valid(self, db: Session):
        """Every IncomeSourceType enum value can be used to create a source."""
        calc = _make_calculation(db)
        for idx, stype in enumerate(IncomeSourceType):
            src = _make_source(
                db,
                calc.id,
                source_type=stype,
                employer_name=f"Source {stype.value}",
                is_primary=(idx == 0),
            )
            assert src.source_type == stype


# ============================================================================
# 3. IncomeVerificationTask - Creation and Status Transitions
# ============================================================================

@pytest.mark.unit
class TestVerificationTaskLifecycle:
    """IncomeVerificationTask creation, status transitions, and completion."""

    def test_create_open_task(self, db: Session):
        """A new task defaults to OPEN status."""
        calc = _make_calculation(db)
        task = _make_task(db, calc.id)
        assert task.status == TaskStatus.OPEN
        assert task.priority == TaskPriority.MEDIUM
        assert task.resolved_at is None
        assert task.resolved_by is None

    def test_status_transition_open_to_in_progress(self, db: Session):
        """Task can move from OPEN to IN_PROGRESS."""
        calc = _make_calculation(db)
        task = _make_task(db, calc.id)
        task.status = TaskStatus.IN_PROGRESS
        task.assigned_to_user_id = 42
        db.flush()

        refreshed = db.query(IncomeVerificationTask).get(task.id)
        assert refreshed.status == TaskStatus.IN_PROGRESS
        assert refreshed.assigned_to_user_id == 42

    def test_status_transition_to_completed(self, db: Session):
        """Task can be completed with resolution notes and resolver."""
        calc = _make_calculation(db)
        task = _make_task(db, calc.id)

        task.status = TaskStatus.IN_PROGRESS
        db.flush()

        now = datetime.now(timezone.utc)
        task.status = TaskStatus.COMPLETED
        task.resolution_notes = "Employment confirmed via verbal VOE with HR department."
        task.resolved_by = "jsmith"
        task.resolved_at = now
        db.flush()

        refreshed = db.query(IncomeVerificationTask).get(task.id)
        assert refreshed.status == TaskStatus.COMPLETED
        assert "verbal VOE" in refreshed.resolution_notes
        assert refreshed.resolved_by == "jsmith"
        assert refreshed.resolved_at is not None

    def test_status_transition_to_deferred(self, db: Session):
        """Task can be deferred for later review."""
        calc = _make_calculation(db)
        task = _make_task(db, calc.id, priority=TaskPriority.LOW)
        task.status = TaskStatus.DEFERRED
        task.resolution_notes = "Waiting for borrower to provide updated tax returns."
        db.flush()

        refreshed = db.query(IncomeVerificationTask).get(task.id)
        assert refreshed.status == TaskStatus.DEFERRED

    def test_all_task_types_can_be_created(self, db: Session):
        """Every VerificationTaskType enum value creates a valid task."""
        calc = _make_calculation(db)
        for vtype in VerificationTaskType:
            task = _make_task(
                db,
                calc.id,
                task_type=vtype,
                title=f"Task: {vtype.value}",
            )
            assert task.task_type == vtype


# ============================================================================
# 4. DTI Ratio Storage and Precision
# ============================================================================

@pytest.mark.unit
class TestDTIRatios:
    """DTI ratio calculation storage with correct precision."""

    def test_dti_ratios_stored_correctly(self, db: Session):
        """Front-end and back-end DTI ratios maintain 2-decimal precision."""
        calc = _make_calculation(
            db,
            dti_front_end=Decimal("28.50"),
            dti_back_end=Decimal("36.75"),
            proposed_housing_expense=Decimal("2422.50"),
            total_monthly_obligations=Decimal("3123.75"),
            total_qualifying_monthly_income=Decimal("8500.00"),
        )
        assert float(calc.dti_front_end) == pytest.approx(28.50)
        assert float(calc.dti_back_end) == pytest.approx(36.75)

    def test_dti_at_conventional_limits(self, db: Session):
        """DTI at conventional limit boundaries (28/36 guideline)."""
        calc = _make_calculation(
            db,
            dti_front_end=Decimal("28.00"),
            dti_back_end=Decimal("36.00"),
        )
        assert float(calc.dti_front_end) == 28.00
        assert float(calc.dti_back_end) == 36.00

    def test_dti_exceeding_limits(self, db: Session):
        """High DTI values are stored for flagging by AI."""
        calc = _make_calculation(
            db,
            dti_front_end=Decimal("42.15"),
            dti_back_end=Decimal("55.89"),
            ai_flags=["dti_exceeds_limit"],
        )
        assert float(calc.dti_front_end) == pytest.approx(42.15)
        assert float(calc.dti_back_end) == pytest.approx(55.89)
        assert "dti_exceeds_limit" in calc.ai_flags


# ============================================================================
# 5. Qualifying Income Determination
# ============================================================================

@pytest.mark.unit
class TestQualifyingIncome:
    """Qualifying income totals and monthly/annual consistency."""

    def test_qualifying_income_monthly_annual_consistency(self, db: Session):
        """Annual qualifying income should be 12x monthly (verified at insert)."""
        monthly = Decimal("8500.00")
        annual = monthly * 12
        calc = _make_calculation(
            db,
            total_qualifying_monthly_income=monthly,
            total_qualifying_annual_income=annual,
        )
        assert float(calc.total_qualifying_annual_income) == pytest.approx(
            float(calc.total_qualifying_monthly_income) * 12
        )

    def test_qualifying_income_from_multiple_sources(self, db: Session):
        """Total qualifying income aggregates across multiple sources."""
        calc = _make_calculation(
            db,
            total_qualifying_monthly_income=Decimal("12500.00"),
            total_qualifying_annual_income=Decimal("150000.00"),
        )
        w2 = _make_source(
            db, calc.id,
            source_type=IncomeSourceType.W2_EMPLOYMENT,
            total_monthly_income=Decimal("8000.00"),
            is_primary=True,
        )
        rental = _make_source(
            db, calc.id,
            source_type=IncomeSourceType.RENTAL,
            employer_name="123 Main St Rental",
            total_monthly_income=Decimal("2500.00"),
            is_primary=False,
        )
        ss = _make_source(
            db, calc.id,
            source_type=IncomeSourceType.SOCIAL_SECURITY,
            employer_name="SSA",
            total_monthly_income=Decimal("2000.00"),
            is_primary=False,
        )
        sources = db.query(IncomeSource).filter(
            IncomeSource.calculation_id == calc.id
        ).all()
        sum_monthly = sum(float(s.total_monthly_income) for s in sources)
        assert sum_monthly == pytest.approx(12500.00)
        assert float(calc.total_qualifying_monthly_income) == pytest.approx(sum_monthly)


# ============================================================================
# 6. Multiple Income Sources Per Calculation
# ============================================================================

@pytest.mark.unit
class TestMultipleIncomeSources:
    """Multiple IncomeSource records tied to a single IncomeCalculation."""

    def test_multiple_sources_created(self, db: Session):
        """Multiple sources with different types belong to one calculation."""
        calc = _make_calculation(db)
        types_and_amounts = [
            (IncomeSourceType.W2_EMPLOYMENT, Decimal("6000.00"), True),
            (IncomeSourceType.OVERTIME, Decimal("800.00"), False),
            (IncomeSourceType.BONUS, Decimal("500.00"), False),
            (IncomeSourceType.RENTAL, Decimal("1200.00"), False),
        ]
        for stype, amount, primary in types_and_amounts:
            _make_source(
                db, calc.id,
                source_type=stype,
                total_monthly_income=amount,
                is_primary=primary,
            )

        sources = db.query(IncomeSource).filter(
            IncomeSource.calculation_id == calc.id
        ).all()
        assert len(sources) == 4
        primaries = [s for s in sources if s.is_primary]
        assert len(primaries) == 1

    def test_sources_isolated_between_calculations(self, db: Session):
        """Sources for different calculations do not intermix."""
        calc_a = _make_calculation(db, loan_id=10)
        calc_b = _make_calculation(db, loan_id=20)
        _make_source(db, calc_a.id, employer_name="Employer A")
        _make_source(db, calc_a.id, employer_name="Employer A2", is_primary=False)
        _make_source(db, calc_b.id, employer_name="Employer B")

        sources_a = db.query(IncomeSource).filter(
            IncomeSource.calculation_id == calc_a.id
        ).all()
        sources_b = db.query(IncomeSource).filter(
            IncomeSource.calculation_id == calc_b.id
        ).all()
        assert len(sources_a) == 2
        assert len(sources_b) == 1


# ============================================================================
# 7. Task Assignment and Completion Workflows
# ============================================================================

@pytest.mark.unit
class TestTaskWorkflow:
    """End-to-end task assignment and completion workflows."""

    def test_task_assignment_and_due_date(self, db: Session):
        """Task can be assigned with a due date."""
        calc = _make_calculation(db)
        due = datetime.now(timezone.utc) + timedelta(days=3)
        task = _make_task(
            db,
            calc.id,
            assigned_to_user_id=42,
            due_date=due,
            priority=TaskPriority.HIGH,
        )
        assert task.assigned_to_user_id == 42
        assert task.due_date is not None
        assert task.priority == TaskPriority.HIGH

    def test_full_task_lifecycle(self, db: Session):
        """Task goes through OPEN -> IN_PROGRESS -> COMPLETED with all metadata."""
        calc = _make_calculation(db)
        task = _make_task(
            db, calc.id,
            task_type=VerificationTaskType.REVIEW_DECLINING_INCOME,
            priority=TaskPriority.CRITICAL,
            ai_recommendation="Income declined 18.7% YoY. Verify with most recent paystubs.",
        )
        assert task.status == TaskStatus.OPEN
        assert task.ai_recommendation is not None

        # Assign and start
        task.status = TaskStatus.IN_PROGRESS
        task.assigned_to_user_id = 99
        db.flush()
        assert task.status == TaskStatus.IN_PROGRESS

        # Complete
        task.status = TaskStatus.COMPLETED
        task.resolution_notes = "Borrower changed jobs in Q3. New salary confirmed at $85k."
        task.resolved_by = "manager1"
        task.resolved_at = datetime.now(timezone.utc)
        db.flush()

        final = db.query(IncomeVerificationTask).get(task.id)
        assert final.status == TaskStatus.COMPLETED
        assert "changed jobs" in final.resolution_notes

    def test_multiple_tasks_per_calculation(self, db: Session):
        """A single calculation can generate many verification tasks."""
        calc = _make_calculation(db)
        src = _make_source(db, calc.id, trending_direction=TrendingDirection.DECLINING)

        task_configs = [
            (VerificationTaskType.VERIFY_EMPLOYMENT, TaskPriority.HIGH),
            (VerificationTaskType.REVIEW_DECLINING_INCOME, TaskPriority.CRITICAL),
            (VerificationTaskType.REQUEST_VOE, TaskPriority.MEDIUM),
        ]
        for ttype, prio in task_configs:
            _make_task(
                db, calc.id,
                income_source_id=src.id,
                task_type=ttype,
                priority=prio,
                title=f"Task: {ttype.value}",
            )

        tasks = db.query(IncomeVerificationTask).filter(
            IncomeVerificationTask.calculation_id == calc.id
        ).all()
        assert len(tasks) == 3
        critical = [t for t in tasks if t.priority == TaskPriority.CRITICAL]
        assert len(critical) == 1


# ============================================================================
# 8. Income Trending Data Storage
# ============================================================================

@pytest.mark.unit
class TestIncomeTrending:
    """Year-over-year income trending analysis storage."""

    def test_increasing_trend(self, db: Session):
        """Increasing income trend is captured with positive YoY change."""
        calc = _make_calculation(db)
        src = _make_source(
            db, calc.id,
            trending_direction=TrendingDirection.INCREASING,
            year1_income=Decimal("100000.00"),
            year2_income=Decimal("85000.00"),
            year_over_year_change_pct=Decimal("17.65"),
        )
        assert src.trending_direction == TrendingDirection.INCREASING
        assert float(src.year_over_year_change_pct) > 0

    def test_declining_trend(self, db: Session):
        """Declining income trend is captured with negative YoY change."""
        calc = _make_calculation(db)
        src = _make_source(
            db, calc.id,
            trending_direction=TrendingDirection.DECLINING,
            year1_income=Decimal("72000.00"),
            year2_income=Decimal("90000.00"),
            year_over_year_change_pct=Decimal("-20.00"),
        )
        assert src.trending_direction == TrendingDirection.DECLINING
        assert float(src.year_over_year_change_pct) < 0

    def test_stable_trend(self, db: Session):
        """Stable income shows near-zero YoY change."""
        calc = _make_calculation(db)
        src = _make_source(
            db, calc.id,
            trending_direction=TrendingDirection.STABLE,
            year1_income=Decimal("80000.00"),
            year2_income=Decimal("79500.00"),
            year_over_year_change_pct=Decimal("0.63"),
        )
        assert src.trending_direction == TrendingDirection.STABLE
        assert abs(float(src.year_over_year_change_pct)) < 5.0

    def test_variable_trend(self, db: Session):
        """Variable income (commission/bonus heavy) is flagged appropriately."""
        calc = _make_calculation(db)
        src = _make_source(
            db, calc.id,
            source_type=IncomeSourceType.COMMISSION,
            trending_direction=TrendingDirection.VARIABLE,
            year1_income=Decimal("110000.00"),
            year2_income=Decimal("80000.00"),
            year_over_year_change_pct=Decimal("37.50"),
        )
        assert src.trending_direction == TrendingDirection.VARIABLE


# ============================================================================
# 9. Override / Adjustment Tracking (Review & Approval Workflow)
# ============================================================================

@pytest.mark.unit
class TestOverrideAdjustmentTracking:
    """Review and approval workflow for manual overrides."""

    def test_review_workflow(self, db: Session):
        """Calculation moves from COMPLETED to NEEDS_REVIEW to APPROVED."""
        calc = _make_calculation(db, status=CalculationStatus.COMPLETED)
        assert calc.status == CalculationStatus.COMPLETED

        # Send for review
        calc.status = CalculationStatus.NEEDS_REVIEW
        db.flush()

        # Reviewer acts
        calc.reviewed_by = "senior_uw_jones"
        calc.reviewed_at = datetime.now(timezone.utc)
        calc.review_notes = (
            "Adjusted commission income downward by 15% due to declining trend. "
            "Using 2-year average per guidelines."
        )
        calc.status = CalculationStatus.APPROVED
        calc.approved_by = "senior_uw_jones"
        calc.approved_at = datetime.now(timezone.utc)
        db.flush()

        refreshed = db.query(IncomeCalculation).get(calc.id)
        assert refreshed.status == CalculationStatus.APPROVED
        assert refreshed.reviewed_by == "senior_uw_jones"
        assert "15%" in refreshed.review_notes
        assert refreshed.approved_by is not None

    def test_rejection_workflow(self, db: Session):
        """Calculation can be rejected with notes requiring recalculation."""
        calc = _make_calculation(db, status=CalculationStatus.NEEDS_REVIEW)
        calc.status = CalculationStatus.REJECTED
        calc.reviewed_by = "mgr_smith"
        calc.reviewed_at = datetime.now(timezone.utc)
        calc.review_notes = "Missing VOE for secondary employment. Recalculate after receipt."
        db.flush()

        refreshed = db.query(IncomeCalculation).get(calc.id)
        assert refreshed.status == CalculationStatus.REJECTED
        assert "Missing VOE" in refreshed.review_notes

    def test_recalculation_after_override(self, db: Session):
        """A new recalculation can reference the same loan after rejection."""
        calc_v1 = _make_calculation(db, loan_id=50, status=CalculationStatus.REJECTED)
        calc_v2 = _make_calculation(
            db,
            loan_id=50,
            calculation_type=CalculationType.RECALCULATION,
            status=CalculationStatus.PENDING,
            total_qualifying_monthly_income=Decimal("7200.00"),
            total_qualifying_annual_income=Decimal("86400.00"),
        )
        calcs = db.query(IncomeCalculation).filter(
            IncomeCalculation.loan_id == 50
        ).all()
        assert len(calcs) == 2
        types = {c.calculation_type for c in calcs}
        assert CalculationType.INITIAL in types
        assert CalculationType.RECALCULATION in types


# ============================================================================
# 10. Edge Cases
# ============================================================================

@pytest.mark.unit
class TestEdgeCases:
    """Edge cases: zero income, negative adjustments, very large values, nulls."""

    def test_zero_income(self, db: Session):
        """Zero qualifying income is stored without error."""
        calc = _make_calculation(
            db,
            total_qualifying_monthly_income=Decimal("0.00"),
            total_qualifying_annual_income=Decimal("0.00"),
            dti_front_end=Decimal("0.00"),
            dti_back_end=Decimal("0.00"),
        )
        assert float(calc.total_qualifying_monthly_income) == 0.0
        assert float(calc.dti_front_end) == 0.0

    def test_zero_income_source(self, db: Session):
        """An income source with zero amounts is valid (e.g., unpaid internship on record)."""
        calc = _make_calculation(db)
        src = _make_source(
            db, calc.id,
            source_type=IncomeSourceType.OTHER,
            employer_name="Unpaid Internship",
            base_monthly_income=Decimal("0.00"),
            overtime_monthly=Decimal("0.00"),
            bonus_monthly=Decimal("0.00"),
            commission_monthly=Decimal("0.00"),
            other_monthly=Decimal("0.00"),
            total_monthly_income=Decimal("0.00"),
            total_annual_income=Decimal("0.00"),
        )
        assert float(src.total_monthly_income) == 0.0

    def test_negative_yoy_change(self, db: Session):
        """Negative year-over-year percentage is stored for declining income."""
        calc = _make_calculation(db)
        src = _make_source(
            db, calc.id,
            year1_income=Decimal("60000.00"),
            year2_income=Decimal("80000.00"),
            year_over_year_change_pct=Decimal("-25.00"),
            trending_direction=TrendingDirection.DECLINING,
        )
        assert float(src.year_over_year_change_pct) == -25.00

    def test_very_large_income_values(self, db: Session):
        """Very large dollar amounts (high-net-worth borrowers) are stored without overflow."""
        monthly = Decimal("250000.00")
        annual = Decimal("3000000.00")
        calc = _make_calculation(
            db,
            total_qualifying_monthly_income=monthly,
            total_qualifying_annual_income=annual,
            proposed_housing_expense=Decimal("45000.00"),
            total_monthly_obligations=Decimal("85000.00"),
        )
        assert float(calc.total_qualifying_monthly_income) == pytest.approx(250000.00)
        assert float(calc.total_qualifying_annual_income) == pytest.approx(3000000.00)

    def test_null_optional_fields(self, db: Session):
        """Optional fields can be null without breaking the model."""
        calc = _make_calculation(
            db,
            borrower_id=None,
            ai_flags=None,
            ai_recommendations=None,
            ai_model_used=None,
            calculation_duration_ms=None,
            source_documents=None,
            reviewed_by=None,
            approved_by=None,
        )
        assert calc.borrower_id is None
        assert calc.ai_flags is None
        assert calc.reviewed_by is None

    def test_source_with_null_trending(self, db: Session):
        """Income source with no trending data (new employment, single year)."""
        calc = _make_calculation(db)
        src = _make_source(
            db, calc.id,
            trending_direction=None,
            year1_income=Decimal("50000.00"),
            year2_income=None,
            year_over_year_change_pct=None,
        )
        assert src.trending_direction is None
        assert src.year2_income is None
        assert src.year_over_year_change_pct is None

    def test_repr_methods(self, db: Session):
        """__repr__ methods return useful strings without errors."""
        calc = _make_calculation(db)
        src = _make_source(db, calc.id)
        task = _make_task(db, calc.id)

        calc_repr = repr(calc)
        assert "IncomeCalculation" in calc_repr
        assert "loan_id=" in calc_repr

        src_repr = repr(src)
        assert "IncomeSource" in src_repr
        assert "Acme Corp" in src_repr

        task_repr = repr(task)
        assert "IncomeVerificationTask" in task_repr


# ============================================================================
# 11. Verification Status Transitions on IncomeSource
# ============================================================================

@pytest.mark.unit
class TestVerificationStatusTransitions:
    """IncomeSource verification status lifecycle."""

    def test_verification_lifecycle(self, db: Session):
        """Source goes through UNVERIFIED -> PENDING_VOE -> VOE_RECEIVED -> VERIFIED."""
        calc = _make_calculation(db)
        src = _make_source(db, calc.id, verification_status=VerificationStatus.UNVERIFIED)
        assert src.verification_status == VerificationStatus.UNVERIFIED

        src.verification_status = VerificationStatus.PENDING_VOE
        db.flush()
        assert src.verification_status == VerificationStatus.PENDING_VOE

        src.verification_status = VerificationStatus.VOE_RECEIVED
        src.verification_notes = "Written VOE received from HR at Acme Corp."
        db.flush()
        assert src.verification_status == VerificationStatus.VOE_RECEIVED

        src.verification_status = VerificationStatus.VERIFIED
        db.flush()
        refreshed = db.query(IncomeSource).get(src.id)
        assert refreshed.verification_status == VerificationStatus.VERIFIED
        assert "Written VOE" in refreshed.verification_notes

    def test_flagged_verification(self, db: Session):
        """Source can be flagged during verification for manual review."""
        calc = _make_calculation(db)
        src = _make_source(db, calc.id)
        src.verification_status = VerificationStatus.FLAGGED
        src.verification_notes = "Employer phone number disconnected. Unable to complete verbal VOE."
        src.ai_notes = "High risk - employer contact invalid."
        db.flush()

        refreshed = db.query(IncomeSource).get(src.id)
        assert refreshed.verification_status == VerificationStatus.FLAGGED
        assert "disconnected" in refreshed.verification_notes
