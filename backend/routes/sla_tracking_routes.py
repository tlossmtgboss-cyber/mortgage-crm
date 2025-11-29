"""
SLA Tracking API Routes

Provides endpoints for:
- SLA Measure configuration (CRUD)
- Milestone history tracking
- Performance dashboards and trending
- Alert management
- Efficiency reports
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional, List
from datetime import date, datetime, timedelta, timezone
import logging

from database import get_db, Base, engine

from models.sla_tracking import (
    SLAMeasure,
    LoanMilestoneHistory,
    SLAPerformanceSnapshot,
    SLAAlert,
    SLAEfficiencyReport,
    TimeUnit,
    SLAStatus,
    MilestoneType,
    AlertStatus
)

from schemas.sla_tracking import (
    SLAMeasureCreate,
    SLAMeasureUpdate,
    SLAMeasureResponse,
    MilestoneStartRequest,
    MilestoneCompleteRequest,
    MilestoneWaiveRequest,
    MilestoneHistoryResponse,
    SLAAlertResponse,
    AlertAcknowledgeRequest,
    AlertResolveRequest,
    AlertEscalateRequest,
    AlertSnoozeRequest,
    SLADashboardResponse,
    SLADashboardSummary,
    PerformanceTrendResponse,
    PerformanceTrendPoint,
    TeamPerformanceResponse,
    TeamPerformanceItem,
    BottleneckAnalysisResponse,
    StageBottleneck,
    EfficiencyReportResponse,
    EfficiencyReportGenerateRequest,
    LoanSLAStatus,
    LoanSLAStatusListResponse,
    SLAConfigResponse,
    MilestoneTypeEnum,
    SLAStatusEnum
)

from crud.sla_tracking import (
    create_sla_measure,
    get_sla_measure,
    get_sla_measure_by_type,
    get_all_sla_measures,
    update_sla_measure,
    delete_sla_measure,
    create_milestone_history,
    get_milestone_history,
    get_loan_milestones,
    get_active_milestones,
    get_overdue_milestones,
    get_at_risk_milestones,
    complete_milestone,
    waive_milestone,
    update_milestone_statuses_batch,
    create_sla_alert,
    get_sla_alert,
    get_active_alerts,
    get_alerts_for_loan,
    acknowledge_alert,
    resolve_alert,
    escalate_alert,
    snooze_alert,
    get_performance_snapshots,
    create_efficiency_report,
    get_efficiency_reports,
    get_dashboard_summary,
    get_team_performance,
    get_bottleneck_analysis,
    seed_default_sla_measures
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/sla", tags=["sla-tracking"])


# ============================================================================
# Database Migration Endpoint
# ============================================================================

def ensure_sla_tables_exist():
    """Create SLA tables if they don't exist"""
    try:
        with engine.connect() as conn:
            # Check if tables exist first
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'sla_measures'
                )
            """))
            exists = result.scalar()

            if not exists:
                logger.info("Creating SLA tracking tables...")

                # Create sla_measures table
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS sla_measures (
                        id SERIAL PRIMARY KEY,
                        organization_id INTEGER NOT NULL DEFAULT 1,
                        milestone_type VARCHAR(50) NOT NULL,
                        name VARCHAR(100) NOT NULL,
                        description TEXT,
                        target_value FLOAT NOT NULL,
                        target_unit VARCHAR(20) NOT NULL DEFAULT 'hours',
                        warning_threshold_pct FLOAT DEFAULT 75,
                        critical_threshold_pct FLOAT DEFAULT 100,
                        applies_to_loan_types JSONB,
                        applies_to_channels JSONB,
                        business_hours_only BOOLEAN DEFAULT TRUE,
                        is_active BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    )
                """))

                # Create loan_milestone_history table
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS loan_milestone_history (
                        id SERIAL PRIMARY KEY,
                        organization_id INTEGER NOT NULL DEFAULT 1,
                        loan_id INTEGER,
                        lead_id INTEGER,
                        loan_number VARCHAR(50),
                        sla_measure_id INTEGER NOT NULL REFERENCES sla_measures(id),
                        milestone_type VARCHAR(50) NOT NULL,
                        started_at TIMESTAMP WITH TIME ZONE,
                        target_deadline TIMESTAMP WITH TIME ZONE,
                        completed_at TIMESTAMP WITH TIME ZONE,
                        status VARCHAR(20) DEFAULT 'not_started',
                        target_hours FLOAT,
                        actual_hours FLOAT,
                        variance_hours FLOAT,
                        variance_pct FLOAT,
                        assigned_to_id INTEGER,
                        completed_by_id INTEGER,
                        notes TEXT,
                        waive_reason TEXT,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    )
                """))

                # Create sla_performance_snapshots table
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS sla_performance_snapshots (
                        id SERIAL PRIMARY KEY,
                        organization_id INTEGER NOT NULL DEFAULT 1,
                        snapshot_date DATE NOT NULL,
                        period_type VARCHAR(20) DEFAULT 'daily',
                        scope_type VARCHAR(20) NOT NULL,
                        scope_id INTEGER,
                        milestone_type VARCHAR(50),
                        total_milestones INTEGER DEFAULT 0,
                        completed_on_time INTEGER DEFAULT 0,
                        completed_late INTEGER DEFAULT 0,
                        still_in_progress INTEGER DEFAULT 0,
                        overdue INTEGER DEFAULT 0,
                        on_time_rate FLOAT,
                        avg_completion_time_hours FLOAT,
                        avg_variance_hours FLOAT,
                        avg_variance_pct FLOAT,
                        p50_completion_hours FLOAT,
                        p90_completion_hours FLOAT,
                        p95_completion_hours FLOAT,
                        status_breakdown JSONB,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    )
                """))

                # Create sla_alerts table
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS sla_alerts (
                        id SERIAL PRIMARY KEY,
                        organization_id INTEGER NOT NULL DEFAULT 1,
                        milestone_history_id INTEGER NOT NULL REFERENCES loan_milestone_history(id),
                        loan_id INTEGER,
                        lead_id INTEGER,
                        alert_type VARCHAR(50) NOT NULL,
                        milestone_type VARCHAR(50) NOT NULL,
                        title VARCHAR(200) NOT NULL,
                        message TEXT,
                        status VARCHAR(20) DEFAULT 'active',
                        assigned_to_id INTEGER,
                        escalated_to_id INTEGER,
                        triggered_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        acknowledged_at TIMESTAMP WITH TIME ZONE,
                        resolved_at TIMESTAMP WITH TIME ZONE,
                        snooze_until TIMESTAMP WITH TIME ZONE,
                        resolution_notes TEXT,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    )
                """))

                # Create sla_efficiency_reports table
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS sla_efficiency_reports (
                        id SERIAL PRIMARY KEY,
                        organization_id INTEGER NOT NULL DEFAULT 1,
                        report_date DATE NOT NULL,
                        period_start DATE NOT NULL,
                        period_end DATE NOT NULL,
                        total_loans_processed INTEGER,
                        avg_days_to_close FLOAT,
                        avg_days_to_fund FLOAT,
                        overall_sla_compliance_rate FLOAT,
                        bottleneck_stages JSONB,
                        top_performers JSONB,
                        improvement_areas JSONB,
                        vs_prior_period JSONB,
                        recommendations JSONB,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    )
                """))

                # Create indexes
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_sla_measures_org ON sla_measures(organization_id)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_sla_measures_type ON sla_measures(milestone_type)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_milestone_history_org ON loan_milestone_history(organization_id)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_milestone_history_loan ON loan_milestone_history(loan_id)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_milestone_history_lead ON loan_milestone_history(lead_id)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_milestone_history_status ON loan_milestone_history(status)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_sla_alerts_org ON sla_alerts(organization_id)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_sla_alerts_status ON sla_alerts(status)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_performance_snapshots_date ON sla_performance_snapshots(snapshot_date)"))

                conn.commit()
                logger.info("SLA tracking tables created successfully")
            else:
                logger.info("SLA tracking tables already exist")

    except Exception as e:
        logger.warning(f"SLA tables check warning: {e}")


# Auto-create tables on module load
try:
    ensure_sla_tables_exist()
except Exception as e:
    logger.warning(f"Could not auto-create SLA tables: {e}")


# ============================================================================
# Migration Endpoint
# ============================================================================

@router.post("/migrate")
async def run_sla_migration(db: Session = Depends(get_db)):
    """
    Run SLA tracking database migrations and seed default measures.
    Call this once to set up the SLA system.
    """
    try:
        ensure_sla_tables_exist()

        # Seed default SLA measures
        created = seed_default_sla_measures(db)

        return {
            "status": "success",
            "message": "SLA tracking tables created/verified",
            "default_measures_created": len(created)
        }
    except Exception as e:
        logger.error(f"Migration error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# SLA Measure Configuration Routes
# ============================================================================

@router.get("/measures", response_model=List[SLAMeasureResponse])
async def list_sla_measures(
    active_only: bool = Query(True, description="Only return active measures"),
    db: Session = Depends(get_db)
):
    """Get all SLA measures for the organization."""
    measures = get_all_sla_measures(db, active_only=active_only)
    return measures


@router.get("/measures/{measure_id}", response_model=SLAMeasureResponse)
async def get_sla_measure_detail(
    measure_id: int,
    db: Session = Depends(get_db)
):
    """Get a specific SLA measure by ID."""
    measure = get_sla_measure(db, measure_id)
    if not measure:
        raise HTTPException(status_code=404, detail="SLA measure not found")
    return measure


@router.post("/measures", response_model=SLAMeasureResponse)
async def create_new_sla_measure(
    measure: SLAMeasureCreate,
    db: Session = Depends(get_db)
):
    """Create a new SLA measure configuration."""
    return create_sla_measure(db, measure)


@router.put("/measures/{measure_id}", response_model=SLAMeasureResponse)
async def update_sla_measure_detail(
    measure_id: int,
    measure: SLAMeasureUpdate,
    db: Session = Depends(get_db)
):
    """Update an existing SLA measure."""
    updated = update_sla_measure(db, measure_id, measure)
    if not updated:
        raise HTTPException(status_code=404, detail="SLA measure not found")
    return updated


@router.delete("/measures/{measure_id}")
async def delete_sla_measure_item(
    measure_id: int,
    db: Session = Depends(get_db)
):
    """Deactivate an SLA measure (soft delete)."""
    success = delete_sla_measure(db, measure_id)
    if not success:
        raise HTTPException(status_code=404, detail="SLA measure not found")
    return {"status": "success", "message": "SLA measure deactivated"}


# ============================================================================
# Milestone Tracking Routes
# ============================================================================

@router.post("/milestones/start")
async def start_milestone_tracking(
    request: MilestoneStartRequest,
    db: Session = Depends(get_db)
):
    """Start tracking a milestone for a loan/lead."""
    milestone = create_milestone_history(
        db,
        loan_id=request.loan_id,
        lead_id=request.lead_id,
        loan_number=request.loan_number,
        milestone_type=MilestoneType[request.milestone_type.value.upper()],
        assigned_to_id=request.assigned_to_id,
        notes=request.notes
    )
    if not milestone:
        raise HTTPException(
            status_code=400,
            detail="Could not start milestone. Check that SLA measure exists for this milestone type."
        )
    return {"status": "success", "milestone_id": milestone.id}


@router.post("/milestones/{milestone_id}/complete")
async def complete_milestone_tracking(
    milestone_id: int,
    request: MilestoneCompleteRequest,
    db: Session = Depends(get_db)
):
    """Mark a milestone as completed."""
    milestone = complete_milestone(
        db,
        milestone_id,
        completed_by_id=request.completed_by_id,
        notes=request.notes
    )
    if not milestone:
        raise HTTPException(status_code=404, detail="Milestone not found or already completed")

    return {
        "status": "success",
        "milestone_id": milestone.id,
        "actual_hours": milestone.actual_hours,
        "variance_hours": milestone.variance_hours,
        "variance_pct": milestone.variance_pct,
        "on_time": milestone.variance_hours <= 0 if milestone.variance_hours else True
    }


@router.post("/milestones/{milestone_id}/waive")
async def waive_milestone_tracking(
    milestone_id: int,
    request: MilestoneWaiveRequest,
    db: Session = Depends(get_db)
):
    """Waive a milestone (external dependency, etc.)."""
    milestone = waive_milestone(db, milestone_id, request.waive_reason)
    if not milestone:
        raise HTTPException(status_code=404, detail="Milestone not found")
    return {"status": "success", "milestone_id": milestone.id, "waive_reason": request.waive_reason}


@router.get("/milestones/loan/{loan_id}", response_model=List[MilestoneHistoryResponse])
async def get_loan_milestone_history(
    loan_id: int,
    db: Session = Depends(get_db)
):
    """Get all milestones for a specific loan."""
    milestones = get_loan_milestones(db, loan_id=loan_id)
    return milestones


@router.get("/milestones/lead/{lead_id}", response_model=List[MilestoneHistoryResponse])
async def get_lead_milestone_history(
    lead_id: int,
    db: Session = Depends(get_db)
):
    """Get all milestones for a specific lead."""
    milestones = get_loan_milestones(db, lead_id=lead_id)
    return milestones


@router.get("/milestones/active")
async def get_active_milestone_list(
    status: Optional[str] = Query(None, description="Filter by status: at_risk, overdue"),
    db: Session = Depends(get_db)
):
    """Get all active milestones, optionally filtered by status."""
    if status == "at_risk":
        milestones = get_at_risk_milestones(db)
    elif status == "overdue":
        milestones = get_overdue_milestones(db)
    else:
        milestones = get_active_milestones(db)

    return {
        "total": len(milestones),
        "milestones": milestones
    }


# ============================================================================
# Alert Management Routes
# ============================================================================

@router.get("/alerts", response_model=List[SLAAlertResponse])
async def get_alert_list(
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db)
):
    """Get active SLA alerts."""
    return get_active_alerts(db, limit=limit)


@router.get("/alerts/loan/{loan_id}", response_model=List[SLAAlertResponse])
async def get_loan_alerts(
    loan_id: int,
    db: Session = Depends(get_db)
):
    """Get all alerts for a specific loan."""
    return get_alerts_for_loan(db, loan_id=loan_id)


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_sla_alert(
    alert_id: int,
    request: AlertAcknowledgeRequest,
    db: Session = Depends(get_db)
):
    """Acknowledge an SLA alert."""
    alert = acknowledge_alert(db, alert_id, notes=request.notes)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"status": "success", "alert_id": alert.id}


@router.post("/alerts/{alert_id}/resolve")
async def resolve_sla_alert(
    alert_id: int,
    request: AlertResolveRequest,
    db: Session = Depends(get_db)
):
    """Resolve an SLA alert."""
    alert = resolve_alert(db, alert_id, request.resolution_notes)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"status": "success", "alert_id": alert.id}


@router.post("/alerts/{alert_id}/escalate")
async def escalate_sla_alert(
    alert_id: int,
    request: AlertEscalateRequest,
    db: Session = Depends(get_db)
):
    """Escalate an SLA alert."""
    alert = escalate_alert(db, alert_id, request.escalated_to_id, notes=request.notes)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"status": "success", "alert_id": alert.id, "escalated_to": request.escalated_to_id}


@router.post("/alerts/{alert_id}/snooze")
async def snooze_sla_alert(
    alert_id: int,
    request: AlertSnoozeRequest,
    db: Session = Depends(get_db)
):
    """Snooze an SLA alert until a specified time."""
    alert = snooze_alert(db, alert_id, request.snooze_until, notes=request.notes)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"status": "success", "alert_id": alert.id, "snoozed_until": request.snooze_until}


# ============================================================================
# Dashboard Routes
# ============================================================================

@router.get("/dashboard/summary")
async def get_sla_dashboard_summary(
    db: Session = Depends(get_db)
):
    """Get SLA dashboard summary metrics."""
    summary = get_dashboard_summary(db)
    return summary


@router.get("/dashboard")
async def get_full_sla_dashboard(
    db: Session = Depends(get_db)
):
    """Get complete SLA dashboard data."""
    summary = get_dashboard_summary(db)
    alerts = get_active_alerts(db, limit=10)
    at_risk = get_at_risk_milestones(db)[:10]

    # Get performance trend for last 30 days
    end_date = date.today()
    start_date = end_date - timedelta(days=30)
    snapshots = get_performance_snapshots(db, start_date, end_date)

    trend_points = [
        {
            "date": s.snapshot_date.isoformat(),
            "on_time_rate": s.on_time_rate or 0,
            "avg_completion_hours": s.avg_completion_time_hours or 0,
            "total_milestones": s.total_milestones or 0,
            "overdue_count": s.overdue or 0
        }
        for s in snapshots
    ]

    return {
        "summary": summary,
        "recent_alerts": alerts,
        "at_risk_loans": at_risk,
        "performance_trend": trend_points
    }


@router.get("/dashboard/trend")
async def get_performance_trend(
    start_date: date = Query(None),
    end_date: date = Query(None),
    milestone_type: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Get performance trending data for a date range."""
    if not end_date:
        end_date = date.today()
    if not start_date:
        start_date = end_date - timedelta(days=30)

    mt = MilestoneType[milestone_type.upper()] if milestone_type else None
    snapshots = get_performance_snapshots(db, start_date, end_date, milestone_type=mt)

    return {
        "period_start": start_date.isoformat(),
        "period_end": end_date.isoformat(),
        "milestone_type": milestone_type,
        "data_points": [
            {
                "date": s.snapshot_date.isoformat(),
                "on_time_rate": s.on_time_rate or 0,
                "avg_completion_hours": s.avg_completion_time_hours or 0,
                "total_milestones": s.total_milestones or 0,
                "overdue_count": s.overdue or 0
            }
            for s in snapshots
        ]
    }


@router.get("/dashboard/team-performance")
async def get_team_performance_data(
    start_date: date = Query(None),
    end_date: date = Query(None),
    db: Session = Depends(get_db)
):
    """Get team performance metrics."""
    if not end_date:
        end_date = date.today()
    if not start_date:
        start_date = end_date - timedelta(days=30)

    performance = get_team_performance(db, start_date, end_date)

    return {
        "period_start": start_date.isoformat(),
        "period_end": end_date.isoformat(),
        "members": performance
    }


@router.get("/dashboard/bottlenecks")
async def get_bottleneck_analysis_data(
    start_date: date = Query(None),
    end_date: date = Query(None),
    db: Session = Depends(get_db)
):
    """Get bottleneck analysis showing stages with most delays."""
    if not end_date:
        end_date = date.today()
    if not start_date:
        start_date = end_date - timedelta(days=30)

    try:
        bottlenecks = get_bottleneck_analysis(db, start_date, end_date)
    except Exception as e:
        logger.warning(f"Bottleneck analysis error: {e}")
        bottlenecks = []

    # Generate recommendations
    recommendations = []
    for b in bottlenecks[:3]:
        if b.get("delay_frequency_pct", 0) > 30:
            recommendations.append(
                f"Consider reviewing {b['milestone_type']} process - {b['delay_frequency_pct']}% of loans experience delays"
            )

    return {
        "period_start": start_date.isoformat(),
        "period_end": end_date.isoformat(),
        "bottlenecks": bottlenecks,
        "recommendations": recommendations
    }


@router.get("/dashboard/run-rates")
async def get_run_rate_report(
    lookback_days: int = Query(30, ge=7, le=90),
    db: Session = Depends(get_db)
):
    """
    Get run rate report with forecasting for all milestone types.

    Run rates show the average completions per day/week for each milestone type,
    with trend analysis (improving/declining/stable) and inventory forecasts.

    Returns:
        - milestone_run_rates: Run rate metrics per milestone type
        - inventory_forecasts: Current inventory and time to clear
        - bottlenecks: Potential bottlenecks identified
        - summary: Overall health metrics
    """
    from tasks.sla_tasks import calculate_run_rate, calculate_inventory_forecast, calculate_health_score

    # Get all active SLA measures
    measures = get_all_sla_measures(db, organization_id=1, active_only=True)
    milestone_types = list(set(m.milestone_type for m in measures))

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lookback_days": lookback_days,
        "milestone_run_rates": [],
        "inventory_forecasts": [],
        "bottlenecks": [],
        "summary": {}
    }

    total_inventory = 0
    total_at_risk = 0
    total_overdue = 0

    for mt in milestone_types:
        try:
            # Calculate run rate
            run_rate = calculate_run_rate(db, mt, lookback_days=lookback_days, organization_id=1)
            report["milestone_run_rates"].append(run_rate)

            # Calculate inventory forecast
            forecast = calculate_inventory_forecast(db, mt, organization_id=1)
            report["inventory_forecasts"].append(forecast)

            # Track bottlenecks
            if forecast["is_potential_bottleneck"]:
                report["bottlenecks"].append({
                    "milestone_type": mt.value,
                    "inventory": forecast["current_inventory"],
                    "days_to_clear": forecast["days_to_clear_inventory"],
                    "overdue_count": forecast["overdue_count"],
                    "at_risk_count": forecast["at_risk_count"],
                    "daily_run_rate": forecast["daily_run_rate"],
                    "trend": run_rate["trend"]
                })

            # Aggregate totals
            total_inventory += forecast["current_inventory"]
            total_at_risk += forecast["at_risk_count"]
            total_overdue += forecast["overdue_count"]
        except Exception as e:
            logger.warning(f"Error calculating run rate for {mt}: {e}")

    # Sort bottlenecks by days to clear (worst first)
    report["bottlenecks"].sort(
        key=lambda x: x["days_to_clear"] if x["days_to_clear"] else float('inf'),
        reverse=True
    )

    # Summary
    report["summary"] = {
        "total_active_milestones": total_inventory,
        "total_at_risk": total_at_risk,
        "total_overdue": total_overdue,
        "bottleneck_count": len(report["bottlenecks"]),
        "health_score": calculate_health_score(total_inventory, total_at_risk, total_overdue)
    }

    return report


@router.get("/dashboard/run-rates/{milestone_type}")
async def get_milestone_run_rate(
    milestone_type: str,
    lookback_days: int = Query(30, ge=7, le=90),
    db: Session = Depends(get_db)
):
    """
    Get detailed run rate and forecast for a specific milestone type.

    Returns run rate metrics, trend analysis, and inventory forecast.
    """
    from tasks.sla_tasks import calculate_run_rate, calculate_inventory_forecast

    # Convert string to MilestoneType enum
    try:
        mt = MilestoneType(milestone_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid milestone type: {milestone_type}")

    run_rate = calculate_run_rate(db, mt, lookback_days=lookback_days, organization_id=1)
    forecast = calculate_inventory_forecast(db, mt, organization_id=1)

    return {
        "milestone_type": milestone_type,
        "run_rate": run_rate,
        "forecast": forecast
    }


# ============================================================================
# Efficiency Reports Routes
# ============================================================================

@router.post("/reports/efficiency")
async def generate_efficiency_report(
    request: EfficiencyReportGenerateRequest,
    db: Session = Depends(get_db)
):
    """Generate a new efficiency report for a period."""
    report = create_efficiency_report(db, request.period_start, request.period_end)
    return {
        "status": "success",
        "report_id": report.id,
        "compliance_rate": report.overall_sla_compliance_rate
    }


@router.get("/reports/efficiency", response_model=List[EfficiencyReportResponse])
async def list_efficiency_reports(
    limit: int = Query(10, le=50),
    db: Session = Depends(get_db)
):
    """Get recent efficiency reports."""
    return get_efficiency_reports(db, limit=limit)


# ============================================================================
# Configuration Routes
# ============================================================================

@router.get("/config")
async def get_sla_configuration(
    db: Session = Depends(get_db)
):
    """Get complete SLA configuration."""
    measures = get_all_sla_measures(db)

    return {
        "measures": measures,
        "business_hours": {
            "start_hour": 9,
            "end_hour": 17,
            "work_days": [0, 1, 2, 3, 4]  # Mon-Fri
        },
        "holidays": [],  # Would come from config
        "escalation_rules": {
            "warning_to_critical_hours": 4,
            "auto_escalate_overdue": True
        }
    }


@router.post("/config/seed-defaults")
async def seed_default_measures(
    db: Session = Depends(get_db)
):
    """Seed default SLA measures (run once during setup)."""
    created = seed_default_sla_measures(db)
    return {
        "status": "success",
        "measures_created": len(created),
        "message": f"Created {len(created)} default SLA measures"
    }


# ============================================================================
# Background Job Trigger Routes (for testing/manual runs)
# ============================================================================

@router.post("/jobs/update-statuses")
async def trigger_status_update(
    db: Session = Depends(get_db)
):
    """
    Manually trigger milestone status update job.
    This is normally run by a background scheduler.
    """
    results = update_milestone_statuses_batch(db)
    return {
        "status": "success",
        "updated": results
    }


# ============================================================================
# Email Report Endpoint
# ============================================================================

from pydantic import BaseModel, EmailStr

class SLAReportEmailRequest(BaseModel):
    email_address: str
    include_run_rates: bool = True
    include_forecasts: bool = True
    include_bottlenecks: bool = True


@router.post("/reports/send-email")
async def send_sla_report_email(
    request: SLAReportEmailRequest,
    db: Session = Depends(get_db)
):
    """
    Send SLA run rate report via email.

    Generates a comprehensive report including:
    - Run rates per milestone type
    - Inventory forecasts
    - Bottleneck analysis
    - Health score
    """
    from tasks.sla_tasks import calculate_run_rate, calculate_inventory_forecast, calculate_health_score

    # Get all active SLA measures
    measures = get_all_sla_measures(db, organization_id=1, active_only=True)
    milestone_types = list(set(m.milestone_type for m in measures))

    # Build report data
    run_rates = []
    forecasts = []
    bottlenecks = []
    total_inventory = 0
    total_at_risk = 0
    total_overdue = 0

    for mt in milestone_types:
        try:
            rr = calculate_run_rate(db, mt, lookback_days=30, organization_id=1)
            run_rates.append(rr)

            fc = calculate_inventory_forecast(db, mt, organization_id=1)
            forecasts.append(fc)

            if fc["is_potential_bottleneck"]:
                bottlenecks.append({
                    "milestone_type": mt.value,
                    "inventory": fc["current_inventory"],
                    "days_to_clear": fc["days_to_clear_inventory"],
                    "daily_run_rate": fc["daily_run_rate"]
                })

            total_inventory += fc["current_inventory"]
            total_at_risk += fc["at_risk_count"]
            total_overdue += fc["overdue_count"]
        except Exception as e:
            logger.warning(f"Error calculating metrics for {mt}: {e}")

    health_score = calculate_health_score(total_inventory, total_at_risk, total_overdue)
    report_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Build HTML email
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: 'Segoe UI', Arial, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; background-color: #f5f5f5; }}
            .container {{ max-width: 800px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #218D8D 0%, #1a7070 100%); color: white; padding: 30px; text-align: center; border-radius: 12px 12px 0 0; }}
            .header h1 {{ margin: 0; font-size: 28px; font-weight: 600; }}
            .header p {{ margin: 10px 0 0; opacity: 0.9; }}
            .content {{ background: white; padding: 30px; border-radius: 0 0 12px 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
            .summary-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin-bottom: 30px; }}
            .summary-card {{ background: #f8f9fa; padding: 20px; border-radius: 8px; text-align: center; }}
            .summary-card.green {{ border-left: 4px solid #10b981; }}
            .summary-card.yellow {{ border-left: 4px solid #f59e0b; }}
            .summary-card.red {{ border-left: 4px solid #ef4444; }}
            .summary-card.blue {{ border-left: 4px solid #3b82f6; }}
            .summary-card .value {{ font-size: 32px; font-weight: 700; color: #1f2937; }}
            .summary-card .label {{ font-size: 12px; color: #6b7280; text-transform: uppercase; letter-spacing: 0.5px; }}
            .section {{ margin-bottom: 30px; }}
            .section h2 {{ font-size: 18px; color: #1f2937; border-bottom: 2px solid #218D8D; padding-bottom: 10px; margin-bottom: 15px; }}
            table {{ width: 100%; border-collapse: collapse; }}
            th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #e5e7eb; }}
            th {{ background: #f9fafb; font-size: 12px; text-transform: uppercase; color: #6b7280; font-weight: 600; }}
            .trend-up {{ color: #10b981; }}
            .trend-down {{ color: #ef4444; }}
            .trend-stable {{ color: #6b7280; }}
            .bottleneck-badge {{ display: inline-block; background: #fef2f2; color: #dc2626; padding: 4px 12px; border-radius: 16px; font-size: 12px; font-weight: 500; }}
            .footer {{ text-align: center; padding: 20px; color: #9ca3af; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>SLA Run Rate Report</h1>
                <p>Generated: {report_time}</p>
            </div>
            <div class="content">
                <div class="summary-grid">
                    <div class="summary-card blue">
                        <div class="value">{health_score}</div>
                        <div class="label">Health Score</div>
                    </div>
                    <div class="summary-card green">
                        <div class="value">{total_inventory}</div>
                        <div class="label">Active Milestones</div>
                    </div>
                    <div class="summary-card yellow">
                        <div class="value">{total_at_risk}</div>
                        <div class="label">At Risk</div>
                    </div>
                    <div class="summary-card red">
                        <div class="value">{total_overdue}</div>
                        <div class="label">Overdue</div>
                    </div>
                </div>
    """

    if request.include_run_rates and run_rates:
        html_content += """
                <div class="section">
                    <h2>Run Rates by Milestone Type</h2>
                    <table>
                        <tr>
                            <th>Milestone</th>
                            <th>Daily Rate</th>
                            <th>Weekly Rate</th>
                            <th>On-Time %</th>
                            <th>Trend</th>
                        </tr>
        """
        for rr in sorted(run_rates, key=lambda x: x["daily_run_rate"], reverse=True):
            trend_class = "trend-up" if rr["trend"] == "improving" else ("trend-down" if rr["trend"] == "declining" else "trend-stable")
            trend_arrow = "↑" if rr["trend"] == "improving" else ("↓" if rr["trend"] == "declining" else "→")
            html_content += f"""
                        <tr>
                            <td>{rr["milestone_type"].replace("_", " ").title()}</td>
                            <td>{rr["daily_run_rate"]}</td>
                            <td>{rr["weekly_run_rate"]}</td>
                            <td>{rr["on_time_rate"]}%</td>
                            <td class="{trend_class}">{trend_arrow} {rr["trend"].title()}</td>
                        </tr>
            """
        html_content += """
                    </table>
                </div>
        """

    if request.include_forecasts and forecasts:
        active_forecasts = [f for f in forecasts if f["current_inventory"] > 0]
        if active_forecasts:
            html_content += """
                <div class="section">
                    <h2>Inventory Forecast</h2>
                    <table>
                        <tr>
                            <th>Milestone</th>
                            <th>Inventory</th>
                            <th>Days to Clear</th>
                            <th>At Risk</th>
                            <th>Overdue</th>
                        </tr>
            """
            for fc in sorted(active_forecasts, key=lambda x: x["current_inventory"], reverse=True):
                days_to_clear = fc["days_to_clear_inventory"] if fc["days_to_clear_inventory"] else "∞"
                html_content += f"""
                        <tr>
                            <td>{fc["milestone_type"].replace("_", " ").title()}</td>
                            <td>{fc["current_inventory"]}</td>
                            <td>{days_to_clear}</td>
                            <td>{fc["at_risk_count"]}</td>
                            <td>{fc["overdue_count"]}</td>
                        </tr>
                """
            html_content += """
                    </table>
                </div>
            """

    if request.include_bottlenecks and bottlenecks:
        html_content += """
                <div class="section">
                    <h2>Potential Bottlenecks</h2>
        """
        for bn in bottlenecks:
            days = bn["days_to_clear"] if bn["days_to_clear"] else "∞"
            html_content += f"""
                    <div style="background: #fef2f2; padding: 15px; border-radius: 8px; margin-bottom: 10px; border-left: 4px solid #ef4444;">
                        <strong>{bn["milestone_type"].replace("_", " ").title()}</strong><br>
                        <span style="color: #6b7280;">Inventory: {bn["inventory"]} | Days to clear: {days} | Daily rate: {bn["daily_run_rate"]}</span>
                    </div>
            """
        html_content += """
                </div>
        """

    if not bottlenecks and total_inventory == 0:
        html_content += """
                <div class="section">
                    <div style="text-align: center; padding: 40px; color: #6b7280;">
                        <div style="font-size: 48px; margin-bottom: 10px;">✓</div>
                        <h3 style="color: #10b981; margin: 0;">All Clear</h3>
                        <p>No active milestones or bottlenecks detected.</p>
                        <p style="font-size: 12px;">SLA tracking will populate as loans progress through the pipeline.</p>
                    </div>
                </div>
        """

    html_content += """
            </div>
            <div class="footer">
                <p>This report was generated automatically by the Mortgage CRM SLA Tracking System.</p>
                <p>Snapshots are captured daily at 8 AM and 12 PM.</p>
            </div>
        </div>
    </body>
    </html>
    """

    # Send email using the email service (supports SendGrid + SMTP fallback)
    try:
        from email_service import email_service

        # Plain text version
        text_content = f"""
SLA Run Rate Report
Generated: {report_time}

Health Score: {health_score}/100
Active Milestones: {total_inventory}
At Risk: {total_at_risk}
Overdue: {total_overdue}

View the full report in HTML format.
        """

        success = email_service.send_html_email(
            to_email=request.email_address,
            subject=f"SLA Run Rate Report - {report_time}",
            html_body=html_content,
            plain_text_body=text_content
        )

        if success:
            logger.info(f"SLA report email sent to {request.email_address}")
            return {
                "status": "success",
                "message": f"Report sent to {request.email_address}",
                "report_summary": {
                    "health_score": health_score,
                    "total_inventory": total_inventory,
                    "at_risk": total_at_risk,
                    "overdue": total_overdue,
                    "bottleneck_count": len(bottlenecks)
                }
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to send email - check email configuration")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to send SLA report email: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to send email: {str(e)}")
