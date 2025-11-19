"""
Daily Metrics Aggregation Job
Aggregates AI Receptionist activity data into daily metrics for KPIs
"""
from sqlalchemy import func, and_
from sqlalchemy.orm import Session
from datetime import date, datetime, timezone, timedelta
import logging

from ai_receptionist_dashboard_models import (
    AIReceptionistActivity,
    AIReceptionistMetricsDaily,
    AIReceptionistConversation
)

logger = logging.getLogger(__name__)


def aggregate_daily_metrics(db: Session, target_date: date = None) -> int:
    """
    Aggregate activity data into daily metrics

    Args:
        db: Database session
        target_date: Date to aggregate (defaults to today)

    Returns:
        Number of conversations aggregated
    """
    if not target_date:
        target_date = date.today()

    logger.info(f"Aggregating metrics for {target_date}")

    # Define day boundaries
    day_start = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    day_end = datetime.combine(target_date, datetime.max.time()).replace(tzinfo=timezone.utc)

    try:
        # Query all activities for the day
        activities_query = db.query(AIReceptionistActivity).filter(
            and_(
                AIReceptionistActivity.timestamp >= day_start,
                AIReceptionistActivity.timestamp <= day_end
            )
        )

        # Count conversations (incoming calls + texts)
        total_conversations = activities_query.filter(
            AIReceptionistActivity.action_type.in_(['incoming_call', 'incoming_text'])
        ).count()

        # Count by channel/type
        inbound_calls = activities_query.filter(
            AIReceptionistActivity.action_type == 'incoming_call'
        ).count()

        inbound_texts = activities_query.filter(
            AIReceptionistActivity.action_type == 'incoming_text'
        ).count()

        outbound_messages = activities_query.filter(
            AIReceptionistActivity.action_type.in_(['outbound_call', 'outbound_followup'])
        ).count()

        # Count outcomes
        appointments_scheduled = activities_query.filter(
            AIReceptionistActivity.action_type == 'appointment_booked'
        ).count()

        forms_completed = activities_query.filter(
            AIReceptionistActivity.action_type == 'form_completed'
        ).count()

        loan_apps_initiated = activities_query.filter(
            AIReceptionistActivity.action_type.in_(['lead_captured', 'application_started'])
        ).count()

        escalations = activities_query.filter(
            AIReceptionistActivity.action_type == 'escalated'
        ).count()

        # Calculate average response time (if we have timing data)
        response_time_avg = None
        activities_with_times = activities_query.filter(
            AIReceptionistActivity.extra_data.has_key('response_time_seconds')
        ).all()

        if activities_with_times:
            times = [
                float(a.extra_data.get('response_time_seconds', 0))
                for a in activities_with_times
                if 'response_time_seconds' in (a.extra_data or {})
            ]
            if times:
                response_time_avg = sum(times) / len(times)

        # Calculate AI coverage percentage
        ai_coverage_percentage = 100.0
        if total_conversations > 0:
            ai_coverage_percentage = ((total_conversations - escalations) / total_conversations) * 100

        # Calculate average confidence score
        avg_confidence = db.query(
            func.avg(AIReceptionistActivity.confidence_score)
        ).filter(
            and_(
                AIReceptionistActivity.timestamp >= day_start,
                AIReceptionistActivity.timestamp <= day_end,
                AIReceptionistActivity.confidence_score.isnot(None)
            )
        ).scalar() or 0.0

        # Estimate revenue created (placeholder calculation)
        # Assume: $300k avg loan × 0.25% commission = $750 per funded loan
        # Assume: 10% of applications actually fund
        # Assume: Each appointment has 30% chance of becoming application
        estimated_revenue_created = (appointments_scheduled * 0.3 * 0.1 * 750) if appointments_scheduled > 0 else 0.0

        # Estimate saved labor hours
        # Assume: Each conversation saves 5 minutes = 0.083 hours
        saved_labor_hours = total_conversations * 0.083

        # Cost per interaction (fixed for now)
        cost_per_interaction = 0.50

        # Check if record already exists for this date
        existing = db.query(AIReceptionistMetricsDaily).filter(
            AIReceptionistMetricsDaily.date == target_date
        ).first()

        if existing:
            # Update existing record
            existing.total_conversations = total_conversations
            existing.inbound_calls = inbound_calls
            existing.inbound_texts = inbound_texts
            existing.outbound_messages = outbound_messages
            existing.response_time_avg_seconds = response_time_avg
            existing.appointments_scheduled = appointments_scheduled
            existing.forms_completed = forms_completed
            existing.loan_apps_initiated = loan_apps_initiated
            existing.escalations = escalations
            existing.ai_coverage_percentage = ai_coverage_percentage
            existing.estimated_revenue_created = estimated_revenue_created
            existing.saved_labor_hours = saved_labor_hours
            existing.cost_per_interaction = cost_per_interaction
            existing.avg_confidence_score = avg_confidence

            logger.info(f"Updated metrics for {target_date}: {total_conversations} conversations")
        else:
            # Create new record
            metric = AIReceptionistMetricsDaily(
                date=target_date,
                total_conversations=total_conversations,
                inbound_calls=inbound_calls,
                inbound_texts=inbound_texts,
                outbound_messages=outbound_messages,
                response_time_avg_seconds=response_time_avg,
                appointments_scheduled=appointments_scheduled,
                forms_completed=forms_completed,
                loan_apps_initiated=loan_apps_initiated,
                escalations=escalations,
                ai_coverage_percentage=ai_coverage_percentage,
                estimated_revenue_created=estimated_revenue_created,
                saved_labor_hours=saved_labor_hours,
                cost_per_interaction=cost_per_interaction,
                avg_confidence_score=avg_confidence
            )
            db.add(metric)
            logger.info(f"Created metrics for {target_date}: {total_conversations} conversations")

        db.commit()

        return total_conversations

    except Exception as e:
        logger.error(f"Error aggregating metrics for {target_date}: {e}")
        db.rollback()
        raise


def aggregate_metrics_range(db: Session, days: int = 30) -> dict:
    """
    Aggregate metrics for a range of days

    Args:
        db: Database session
        days: Number of days to aggregate (going backwards from today)

    Returns:
        Dictionary with aggregation results
    """
    results = {}

    for day_offset in range(days):
        target_date = date.today() - timedelta(days=day_offset)

        try:
            count = aggregate_daily_metrics(db, target_date)
            results[str(target_date)] = {
                "success": True,
                "conversations": count
            }
        except Exception as e:
            results[str(target_date)] = {
                "success": False,
                "error": str(e)
            }
            logger.error(f"Failed to aggregate {target_date}: {e}")

    return results
