"""
Appointment Outcome Tracker
============================
Tracks whether scheduled appointments lead to funded loans.
Provides feedback loop for AI scheduling optimization.

Uses:
- scheduler_appointments table (Appointment model) with booked_by_ai, loan_id, lead_id, status, etc.
- loans table (Loan model) with stage, funded_date, amount, etc.
- appointment_types table (SchedulerAppointmentType) with type_key, type_name, meeting_type.
"""
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy import func, case, text, and_, or_
import logging

logger = logging.getLogger(__name__)


async def track_appointment_outcomes(
    db: Session,
    organization_id: int = None,
    days: int = 90,
):
    """
    Analyze appointment-to-funding conversion rates.
    Returns metrics on how AI-scheduled vs manually-scheduled appointments perform.

    Joins scheduler_appointments with loans (via loan_id) and checks
    whether the associated loan reached FUNDED stage.
    Groups by booked_by_ai flag and appointment meeting_type.
    """
    from database.models.scheduler import Appointment, AppointmentStatus
    from database.models.lead_loan import Loan

    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        # Base filters
        filters = [
            Appointment.scheduled_start >= cutoff,
            Appointment.status.notin_([
                AppointmentStatus.CANCELLED,
                AppointmentStatus.RESCHEDULED,
            ]),
        ]
        if organization_id:
            filters.append(Appointment.organization_id == organization_id)

        # -- Aggregate: group by booked_by_ai --
        by_ai_rows = (
            db.query(
                Appointment.booked_by_ai,
                func.count(Appointment.id).label("total_appointments"),
                func.count(Loan.id).label("with_loan"),
                func.sum(
                    case(
                        (Loan.stage == "FUNDED", 1),
                        else_=0,
                    )
                ).label("funded_count"),
                func.sum(
                    case(
                        (Loan.stage == "FUNDED", Loan.amount),
                        else_=0,
                    )
                ).label("funded_volume"),
                func.avg(
                    case(
                        (
                            and_(Loan.stage == "FUNDED", Loan.funded_date.isnot(None)),
                            func.extract("epoch", Loan.funded_date - Appointment.scheduled_start) / 86400,
                        ),
                        else_=None,
                    )
                ).label("avg_days_to_fund"),
                func.sum(
                    case(
                        (Appointment.status == AppointmentStatus.NO_SHOW, 1),
                        else_=0,
                    )
                ).label("no_show_count"),
                func.sum(
                    case(
                        (Appointment.status == AppointmentStatus.COMPLETED, 1),
                        else_=0,
                    )
                ).label("completed_count"),
            )
            .outerjoin(Loan, Appointment.loan_id == Loan.id)
            .filter(*filters)
            .group_by(Appointment.booked_by_ai)
            .all()
        )

        # -- Aggregate: group by meeting_type --
        by_type_rows = (
            db.query(
                Appointment.meeting_type,
                Appointment.booked_by_ai,
                func.count(Appointment.id).label("total_appointments"),
                func.sum(
                    case(
                        (Loan.stage == "FUNDED", 1),
                        else_=0,
                    )
                ).label("funded_count"),
                func.sum(
                    case(
                        (Loan.stage == "FUNDED", Loan.amount),
                        else_=0,
                    )
                ).label("funded_volume"),
            )
            .outerjoin(Loan, Appointment.loan_id == Loan.id)
            .filter(*filters)
            .group_by(Appointment.meeting_type, Appointment.booked_by_ai)
            .all()
        )

        def _safe_rate(numerator, denominator):
            if not denominator:
                return 0.0
            return round(float(numerator or 0) / float(denominator) * 100, 2)

        # Build AI vs manual summary
        summary_by_source = []
        for row in by_ai_rows:
            total = row.total_appointments or 0
            funded = int(row.funded_count or 0)
            no_shows = int(row.no_show_count or 0)
            completed = int(row.completed_count or 0)
            summary_by_source.append({
                "booked_by_ai": bool(row.booked_by_ai),
                "total_appointments": total,
                "appointments_with_loan": int(row.with_loan or 0),
                "funded_count": funded,
                "funded_volume": float(row.funded_volume or 0),
                "conversion_rate_pct": _safe_rate(funded, total),
                "avg_days_to_fund": round(float(row.avg_days_to_fund or 0), 1) if row.avg_days_to_fund else None,
                "no_show_count": no_shows,
                "no_show_rate_pct": _safe_rate(no_shows, total),
                "completed_count": completed,
                "completion_rate_pct": _safe_rate(completed, total),
            })

        # Build breakdown by meeting type
        by_meeting_type = []
        for row in by_type_rows:
            total = row.total_appointments or 0
            funded = int(row.funded_count or 0)
            meeting_type_val = row.meeting_type.value if hasattr(row.meeting_type, "value") else str(row.meeting_type)
            by_meeting_type.append({
                "meeting_type": meeting_type_val,
                "booked_by_ai": bool(row.booked_by_ai),
                "total_appointments": total,
                "funded_count": funded,
                "funded_volume": float(row.funded_volume or 0),
                "conversion_rate_pct": _safe_rate(funded, total),
            })

        # Overall totals
        total_appts = sum(s["total_appointments"] for s in summary_by_source)
        total_funded = sum(s["funded_count"] for s in summary_by_source)

        return {
            "period_days": days,
            "organization_id": organization_id,
            "total_appointments": total_appts,
            "total_funded": total_funded,
            "overall_conversion_rate_pct": _safe_rate(total_funded, total_appts),
            "by_booking_source": summary_by_source,
            "by_meeting_type": sorted(
                by_meeting_type,
                key=lambda x: x["conversion_rate_pct"],
                reverse=True,
            ),
        }

    except Exception as e:
        logger.exception("Failed to track appointment outcomes")
        return {"error": str(e)}


async def get_scheduling_roi_metrics(
    db: Session,
    organization_id: int = None,
    days: int = 90,
):
    """
    Calculate ROI metrics for AI scheduling vs manual scheduling.

    Metrics returned:
    - Total AI-scheduled appointments vs manual
    - Appointments that led to funded loans (by source)
    - Average loan amount for AI-scheduled vs manual funded loans
    - No-show rate for AI-scheduled vs manual
    - Average time from appointment to funding
    """
    from database.models.scheduler import Appointment, AppointmentStatus
    from database.models.lead_loan import Loan

    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        filters = [Appointment.scheduled_start >= cutoff]
        if organization_id:
            filters.append(Appointment.organization_id == organization_id)

        rows = (
            db.query(
                Appointment.booked_by_ai,
                func.count(Appointment.id).label("total_appointments"),
                # Funded loan metrics
                func.sum(
                    case(
                        (Loan.stage == "FUNDED", 1),
                        else_=0,
                    )
                ).label("funded_count"),
                func.avg(
                    case(
                        (Loan.stage == "FUNDED", Loan.amount),
                        else_=None,
                    )
                ).label("avg_funded_amount"),
                func.sum(
                    case(
                        (Loan.stage == "FUNDED", Loan.amount),
                        else_=0,
                    )
                ).label("total_funded_volume"),
                # No-show metrics
                func.sum(
                    case(
                        (Appointment.status == AppointmentStatus.NO_SHOW, 1),
                        else_=0,
                    )
                ).label("no_show_count"),
                # Completed metrics
                func.sum(
                    case(
                        (Appointment.status == AppointmentStatus.COMPLETED, 1),
                        else_=0,
                    )
                ).label("completed_count"),
                # Cancelled metrics
                func.sum(
                    case(
                        (Appointment.status == AppointmentStatus.CANCELLED, 1),
                        else_=0,
                    )
                ).label("cancelled_count"),
                # Average days from appointment to funded_date
                func.avg(
                    case(
                        (
                            and_(Loan.stage == "FUNDED", Loan.funded_date.isnot(None)),
                            func.extract("epoch", Loan.funded_date - Appointment.scheduled_start) / 86400,
                        ),
                        else_=None,
                    )
                ).label("avg_days_to_fund"),
                # Reschedule count
                func.sum(
                    case(
                        (Appointment.reschedule_count > 0, 1),
                        else_=0,
                    )
                ).label("rescheduled_count"),
            )
            .outerjoin(Loan, Appointment.loan_id == Loan.id)
            .filter(*filters)
            .group_by(Appointment.booked_by_ai)
            .all()
        )

        def _safe_rate(num, denom):
            if not denom:
                return 0.0
            return round(float(num or 0) / float(denom) * 100, 2)

        ai_metrics = None
        manual_metrics = None

        for row in rows:
            total = row.total_appointments or 0
            funded = int(row.funded_count or 0)
            no_shows = int(row.no_show_count or 0)
            completed = int(row.completed_count or 0)
            cancelled = int(row.cancelled_count or 0)
            rescheduled = int(row.rescheduled_count or 0)

            metrics = {
                "total_appointments": total,
                "funded_count": funded,
                "funded_conversion_rate_pct": _safe_rate(funded, total),
                "total_funded_volume": float(row.total_funded_volume or 0),
                "avg_funded_loan_amount": round(float(row.avg_funded_amount or 0), 2) if row.avg_funded_amount else None,
                "no_show_count": no_shows,
                "no_show_rate_pct": _safe_rate(no_shows, total),
                "completed_count": completed,
                "completion_rate_pct": _safe_rate(completed, total),
                "cancelled_count": cancelled,
                "cancellation_rate_pct": _safe_rate(cancelled, total),
                "rescheduled_count": rescheduled,
                "reschedule_rate_pct": _safe_rate(rescheduled, total),
                "avg_days_to_fund": round(float(row.avg_days_to_fund), 1) if row.avg_days_to_fund else None,
            }

            if row.booked_by_ai:
                ai_metrics = metrics
            else:
                manual_metrics = metrics

        # Compute AI advantage (delta between AI and manual rates)
        ai_advantage = {}
        if ai_metrics and manual_metrics:
            ai_conv = ai_metrics["funded_conversion_rate_pct"]
            manual_conv = manual_metrics["funded_conversion_rate_pct"]
            ai_advantage = {
                "conversion_rate_delta_pct": round(ai_conv - manual_conv, 2),
                "no_show_rate_delta_pct": round(
                    (ai_metrics["no_show_rate_pct"] or 0) - (manual_metrics["no_show_rate_pct"] or 0),
                    2,
                ),
                "avg_loan_amount_delta": round(
                    (ai_metrics["avg_funded_loan_amount"] or 0) - (manual_metrics["avg_funded_loan_amount"] or 0),
                    2,
                ),
                "days_to_fund_delta": round(
                    (ai_metrics["avg_days_to_fund"] or 0) - (manual_metrics["avg_days_to_fund"] or 0),
                    1,
                ) if ai_metrics["avg_days_to_fund"] and manual_metrics["avg_days_to_fund"] else None,
            }

        return {
            "period_days": days,
            "organization_id": organization_id,
            "ai_scheduled": ai_metrics or {"total_appointments": 0},
            "manually_scheduled": manual_metrics or {"total_appointments": 0},
            "ai_advantage": ai_advantage,
        }

    except Exception as e:
        logger.exception("Failed to get scheduling ROI metrics")
        return {"error": str(e)}


async def get_optimal_appointment_types(
    db: Session,
    organization_id: int = None,
):
    """
    Determine which appointment types have highest conversion to funded loans.

    Groups by appointment_type_id, joins with appointment_types table for names,
    and calculates conversion rate for each type. Returns sorted by effectiveness
    (highest conversion rate first).
    """
    from database.models.scheduler import Appointment, SchedulerAppointmentType, AppointmentStatus
    from database.models.lead_loan import Loan

    try:
        filters = [
            Appointment.appointment_type_id.isnot(None),
            Appointment.status.notin_([
                AppointmentStatus.CANCELLED,
                AppointmentStatus.RESCHEDULED,
            ]),
        ]
        if organization_id:
            filters.append(Appointment.organization_id == organization_id)

        rows = (
            db.query(
                Appointment.appointment_type_id,
                SchedulerAppointmentType.type_key,
                SchedulerAppointmentType.type_name,
                SchedulerAppointmentType.meeting_type,
                func.count(Appointment.id).label("total_appointments"),
                func.sum(
                    case(
                        (Loan.stage == "FUNDED", 1),
                        else_=0,
                    )
                ).label("funded_count"),
                func.sum(
                    case(
                        (Loan.stage == "FUNDED", Loan.amount),
                        else_=0,
                    )
                ).label("funded_volume"),
                func.avg(
                    case(
                        (Loan.stage == "FUNDED", Loan.amount),
                        else_=None,
                    )
                ).label("avg_funded_amount"),
                func.sum(
                    case(
                        (Appointment.status == AppointmentStatus.NO_SHOW, 1),
                        else_=0,
                    )
                ).label("no_show_count"),
                func.sum(
                    case(
                        (Appointment.status == AppointmentStatus.COMPLETED, 1),
                        else_=0,
                    )
                ).label("completed_count"),
                func.avg(
                    case(
                        (
                            and_(Loan.stage == "FUNDED", Loan.funded_date.isnot(None)),
                            func.extract("epoch", Loan.funded_date - Appointment.scheduled_start) / 86400,
                        ),
                        else_=None,
                    )
                ).label("avg_days_to_fund"),
            )
            .join(SchedulerAppointmentType, Appointment.appointment_type_id == SchedulerAppointmentType.id)
            .outerjoin(Loan, Appointment.loan_id == Loan.id)
            .filter(*filters)
            .group_by(
                Appointment.appointment_type_id,
                SchedulerAppointmentType.type_key,
                SchedulerAppointmentType.type_name,
                SchedulerAppointmentType.meeting_type,
            )
            .all()
        )

        if not rows:
            return {
                "organization_id": organization_id,
                "appointment_types": [],
                "message": "No appointment data found",
            }

        def _safe_rate(num, denom):
            if not denom:
                return 0.0
            return round(float(num or 0) / float(denom) * 100, 2)

        appointment_types = []
        for row in rows:
            total = row.total_appointments or 0
            funded = int(row.funded_count or 0)
            no_shows = int(row.no_show_count or 0)
            completed = int(row.completed_count or 0)
            meeting_type_val = row.meeting_type.value if hasattr(row.meeting_type, "value") else str(row.meeting_type)

            appointment_types.append({
                "appointment_type_id": row.appointment_type_id,
                "type_key": row.type_key,
                "type_name": row.type_name,
                "meeting_type": meeting_type_val,
                "total_appointments": total,
                "completed_count": completed,
                "completion_rate_pct": _safe_rate(completed, total),
                "funded_count": funded,
                "funded_conversion_rate_pct": _safe_rate(funded, total),
                "funded_volume": float(row.funded_volume or 0),
                "avg_funded_amount": round(float(row.avg_funded_amount), 2) if row.avg_funded_amount else None,
                "no_show_count": no_shows,
                "no_show_rate_pct": _safe_rate(no_shows, total),
                "avg_days_to_fund": round(float(row.avg_days_to_fund), 1) if row.avg_days_to_fund else None,
            })

        # Sort by conversion rate descending
        appointment_types.sort(key=lambda x: x["funded_conversion_rate_pct"], reverse=True)

        # Identify best and worst performers
        best = appointment_types[0] if appointment_types else None
        worst = appointment_types[-1] if len(appointment_types) > 1 else None

        recommendations = []
        if best and best["funded_conversion_rate_pct"] > 0:
            recommendations.append(
                f"Prioritize '{best['type_name']}' appointments — "
                f"{best['funded_conversion_rate_pct']}% conversion rate"
            )
        if worst and worst["no_show_rate_pct"] > 20:
            recommendations.append(
                f"Reduce no-shows for '{worst['type_name']}' — "
                f"{worst['no_show_rate_pct']}% no-show rate. "
                f"Consider additional reminders or shorter booking windows."
            )

        return {
            "organization_id": organization_id,
            "appointment_types": appointment_types,
            "top_performer": best,
            "recommendations": recommendations,
        }

    except Exception as e:
        logger.exception("Failed to get optimal appointment types")
        return {"error": str(e)}
