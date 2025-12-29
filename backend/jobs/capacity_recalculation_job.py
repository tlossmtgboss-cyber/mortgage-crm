"""
Capacity Recalculation Background Job
Periodically recalculates capacity metrics for all active users.

This job runs every 15 minutes via APScheduler to keep capacity data fresh.
"""

import logging
from datetime import datetime
from sqlalchemy.orm import Session
from database import get_db
from services.capacity_service import CapacityService

logger = logging.getLogger(__name__)


async def recalculate_all_capacities_job():
    """
    Background job to recalculate capacity for all users.
    Runs periodically to ensure capacity metrics stay accurate.
    """
    logger.info("Starting scheduled capacity recalculation...")

    try:
        # Get a fresh database session
        db = next(get_db())

        try:
            service = CapacityService(db)
            count = await service.recalculate_all_capacities()

            logger.info(f"Capacity recalculation complete. Updated {count} users.")

            # Check for alerts after recalculation
            await check_and_create_capacity_alerts(db, service)

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Error in capacity recalculation job: {e}", exc_info=True)


async def check_and_create_capacity_alerts(db: Session, service: CapacityService):
    """
    Check for capacity issues and create alerts.
    """
    from sqlalchemy import text

    try:
        # Find users over capacity
        over_capacity_query = text("""
            SELECT
                tc.user_id,
                u.full_name,
                rd.role_name,
                tc.overall_capacity_pct,
                tc.capacity_status
            FROM mm_talent_capacity tc
            JOIN users u ON u.id = tc.user_id
            LEFT JOIN mm_role_definitions rd ON rd.id = tc.role_definition_id
            WHERE tc.capacity_status = 'over_capacity'
            AND tc.is_available = true
        """)

        over_capacity_users = db.execute(over_capacity_query).fetchall()

        for user in over_capacity_users:
            # Check if alert already exists
            existing_alert = db.execute(text("""
                SELECT id FROM mm_capacity_alerts
                WHERE user_id = :user_id
                AND alert_type = 'over_capacity'
                AND status = 'open'
            """), {"user_id": user.user_id}).fetchone()

            if not existing_alert:
                # Create new alert
                db.execute(text("""
                    INSERT INTO mm_capacity_alerts (
                        organization_id, user_id, alert_type, severity,
                        title, description, current_value, threshold_value,
                        status, created_at
                    ) VALUES (
                        NULL, :user_id, 'over_capacity', 'warning',
                        :title, :description, :value, 100,
                        'open', CURRENT_TIMESTAMP
                    )
                """), {
                    "user_id": user.user_id,
                    "title": f"{user.full_name} is over capacity",
                    "description": f"{user.role_name or 'Team member'} is at {user.overall_capacity_pct:.0f}% capacity",
                    "value": user.overall_capacity_pct
                })

                logger.info(f"Created over-capacity alert for user {user.user_id}")

        db.commit()

    except Exception as e:
        logger.warning(f"Error checking capacity alerts: {e}")
        db.rollback()


def setup_capacity_scheduler(scheduler):
    """
    Set up the capacity recalculation job in APScheduler.
    Call this from your main app initialization.
    """
    import asyncio

    def run_job():
        asyncio.create_task(recalculate_all_capacities_job())

    # Run every 15 minutes
    scheduler.add_job(
        run_job,
        'interval',
        minutes=15,
        id='capacity_recalculation',
        name='Recalculate all user capacities',
        replace_existing=True
    )

    logger.info("Capacity recalculation job scheduled (every 15 minutes)")
