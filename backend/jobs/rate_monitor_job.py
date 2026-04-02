"""
Rate Monitor Background Job
Runs periodically to check rate targets against current market rates.

Schedule: Every 15 minutes during business hours (8am-6pm Mon-Fri)

Features:
- Checks all active rate monitoring targets
- Calculates savings for each MUM client
- Creates alerts when targets are triggered
- Initiates AI calls when auto-call is enabled
"""

import logging
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from typing import List, Dict, Any, Optional
import pytz

from sqlalchemy.orm import Session

from models.rate_monitor import (
    RateMonitorTarget, RateMonitorHistory, RateMonitorAlert,
    calculate_monthly_savings, calculate_annual_savings
)
from services.optimal_blue_service import OptimalBlueService, RateScenario

logger = logging.getLogger(__name__)

# Business hours configuration
BUSINESS_START_HOUR = 8  # 8 AM
BUSINESS_END_HOUR = 18  # 6 PM
BUSINESS_DAYS = [0, 1, 2, 3, 4]  # Monday = 0, Friday = 4
TIMEZONE = pytz.timezone('America/Los_Angeles')  # Pacific Time


def is_business_hours() -> bool:
    """Check if current time is within business hours."""
    now = datetime.now(TIMEZONE)
    current_hour = now.hour
    current_day = now.weekday()

    return (
        current_day in BUSINESS_DAYS and
        BUSINESS_START_HOUR <= current_hour < BUSINESS_END_HOUR
    )


def get_call_preference_window(preference: str) -> bool:
    """Check if current time matches the call preference window."""
    now = datetime.now(TIMEZONE)
    current_hour = now.hour
    current_day = now.weekday()

    if preference == 'any_time':
        # Any time during reasonable hours (8am-8pm)
        return 8 <= current_hour < 20

    elif preference == 'business_hours':
        # Standard business hours
        return is_business_hours()

    elif preference == 'weekdays_only':
        # Weekdays during extended hours
        return current_day in BUSINESS_DAYS and 8 <= current_hour < 20

    elif preference == 'mornings':
        # Mornings only (8am-12pm)
        return current_day in BUSINESS_DAYS and 8 <= current_hour < 12

    elif preference == 'afternoons':
        # Afternoons only (12pm-6pm)
        return current_day in BUSINESS_DAYS and 12 <= current_hour < 18

    elif preference == 'evenings':
        # Evenings (5pm-8pm, excluding weekends)
        return current_day in BUSINESS_DAYS and 17 <= current_hour < 20

    return is_business_hours()


class RateMonitorJob:
    """
    Background job for monitoring rate targets.

    Checks all active targets against current market rates and triggers
    alerts when thresholds are met.
    """

    def __init__(self, db: Session):
        self.db = db
        self._optimal_blue = None
        self._call_service = None

    def _get_optimal_blue(self) -> OptimalBlueService:
        """Lazy load Optimal Blue service."""
        if self._optimal_blue is None:
            self._optimal_blue = OptimalBlueService(self.db)
        return self._optimal_blue

    def _get_call_service(self):
        """Lazy load refinance call service."""
        if self._call_service is None:
            try:
                from services.refinance_call_service import RefinanceCallService
                self._call_service = RefinanceCallService(self.db)
            except ImportError:
                logger.warning("Refinance call service not available")
                return None
        return self._call_service

    async def run(self) -> Dict[str, Any]:
        """
        Main job execution method.

        Returns:
            Dict with job execution summary
        """
        start_time = datetime.now(timezone.utc)
        logger.info("Starting rate monitor job...")

        results = {
            'start_time': start_time.isoformat(),
            'targets_checked': 0,
            'thresholds_met': 0,
            'alerts_created': 0,
            'calls_initiated': 0,
            'errors': [],
        }

        try:
            # Get all active targets
            targets = self.db.query(RateMonitorTarget).filter(
                RateMonitorTarget.is_active == True,
                RateMonitorTarget.status == 'active'
            ).all()

            results['targets_checked'] = len(targets)
            logger.info(f"Checking {len(targets)} active rate monitoring targets")

            # Get current market rates (cached)
            rate_service = self._get_optimal_blue()

            for target in targets:
                try:
                    check_result = await self._check_target(target, rate_service)

                    if check_result.get('threshold_met'):
                        results['thresholds_met'] += 1

                        if check_result.get('alert_created'):
                            results['alerts_created'] += 1

                        if check_result.get('call_initiated'):
                            results['calls_initiated'] += 1

                except Exception as e:
                    error_msg = f"Error checking target {target.id}: {str(e)}"
                    logger.error(error_msg)
                    results['errors'].append(error_msg)

            # Cleanup expired rate cache
            await rate_service.cleanup_expired_cache()

        except Exception as e:
            error_msg = f"Rate monitor job failed: {str(e)}"
            logger.error(error_msg)
            results['errors'].append(error_msg)

        results['end_time'] = datetime.now(timezone.utc).isoformat()
        results['duration_seconds'] = (datetime.now(timezone.utc) - start_time).total_seconds()

        logger.info(
            f"Rate monitor job completed: {results['targets_checked']} checked, "
            f"{results['thresholds_met']} met, {results['alerts_created']} alerts, "
            f"{results['calls_initiated']} calls"
        )

        return results

    async def _check_target(
        self,
        target: RateMonitorTarget,
        rate_service: OptimalBlueService
    ) -> Dict[str, Any]:
        """
        Check a single rate monitoring target.

        Args:
            target: Rate monitor target to check
            rate_service: Optimal Blue service for rate lookup

        Returns:
            Dict with check results
        """
        result = {
            'target_id': target.id,
            'threshold_met': False,
            'alert_created': False,
            'call_initiated': False,
        }

        # Get MUM client data
        try:
            from database.models import MUMClient
            mum_client = self.db.query(MUMClient).filter(
                MUMClient.id == target.mum_client_id
            ).first()

            if not mum_client:
                logger.warning(f"MUM client {target.mum_client_id} not found for target {target.id}")
                return result

        except ImportError:
            logger.error("MUM client model not available")
            return result

        # Get client's current rate and loan balance
        client_rate = float(mum_client.interest_rate) if mum_client.interest_rate else None
        loan_balance = float(mum_client.current_loan_amount) if mum_client.current_loan_amount else None

        if not client_rate or not loan_balance:
            logger.debug(f"Skipping target {target.id}: missing rate or balance data")
            return result

        # Build rate scenario for this client
        scenario = RateScenario(
            loan_type=target.loan_type or 'conventional',
            loan_term=target.loan_term or 30,
            loan_amount=loan_balance,
            credit_score=740,  # Use reasonable default
            ltv=80.0,  # Use reasonable default
        )

        # Get current market rate
        rate_result = await rate_service.get_rate(scenario)
        market_rate = rate_result.rate

        # Calculate potential savings
        monthly_savings = calculate_monthly_savings(client_rate, market_rate, loan_balance)
        annual_savings = calculate_annual_savings(monthly_savings)
        rate_difference = client_rate - market_rate

        # Log this rate check
        history = RateMonitorHistory(
            target_id=target.id,
            mum_client_id=target.mum_client_id,
            check_timestamp=datetime.now(timezone.utc),
            client_rate=Decimal(str(client_rate)),
            market_rate=Decimal(str(market_rate)),
            rate_difference=Decimal(str(rate_difference)),
            loan_balance=Decimal(str(loan_balance)),
            monthly_savings=Decimal(str(monthly_savings)),
            annual_savings=Decimal(str(annual_savings)),
            rate_source=rate_result.source,
            rate_scenario=scenario.to_dict(),
        )

        # Check if threshold is met
        threshold_met = False
        threshold_type = None
        threshold_value = None

        if target.target_type == 'savings_threshold':
            threshold_value = float(target.monthly_savings_threshold or 0)
            if monthly_savings >= threshold_value:
                threshold_met = True
                threshold_type = 'savings'

        elif target.target_type == 'rate_drop_percentage':
            threshold_value = float(target.rate_drop_percentage or 0)
            if rate_difference >= threshold_value:
                threshold_met = True
                threshold_type = 'rate_drop'

        elif target.target_type == 'manual_target':
            threshold_value = float(target.target_rate or 0)
            if market_rate <= threshold_value:
                threshold_met = True
                threshold_type = 'manual'

        # Update history with threshold results
        history.threshold_met = threshold_met
        history.threshold_type = threshold_type
        history.threshold_value = Decimal(str(threshold_value)) if threshold_value else None

        result['threshold_met'] = threshold_met

        # If threshold met, check if we should create an alert
        if threshold_met:
            # Check cooldown - don't alert if we triggered recently (last 24 hours)
            cooldown_hours = 24
            if target.last_triggered_at:
                hours_since_trigger = (datetime.now(timezone.utc) - target.last_triggered_at).total_seconds() / 3600
                if hours_since_trigger < cooldown_hours:
                    logger.debug(f"Target {target.id} in cooldown period, skipping alert")
                    history.alert_generated = False
                    self.db.add(history)
                    self.db.commit()
                    return result

            # Create alert
            priority = self._determine_priority(monthly_savings, rate_difference)

            alert = RateMonitorAlert(
                target_id=target.id,
                mum_client_id=target.mum_client_id,
                history_id=None,  # Will update after history is committed
                alert_type=f'{threshold_type}_threshold',
                priority=priority,
                client_rate=Decimal(str(client_rate)),
                market_rate=Decimal(str(market_rate)),
                monthly_savings=Decimal(str(monthly_savings)),
                annual_savings=Decimal(str(annual_savings)),
                status='pending',
                created_at=datetime.now(timezone.utc),
            )

            self.db.add(alert)

            # Update target tracking
            target.last_triggered_at = datetime.now(timezone.utc)
            target.trigger_count = (target.trigger_count or 0) + 1

            history.alert_generated = True
            result['alert_created'] = True

            logger.info(
                f"Alert created for target {target.id}: "
                f"${monthly_savings:,.0f}/month savings ({rate_difference:.3f}% drop)"
            )

            # Check if we should initiate an automatic call
            if target.auto_call_enabled:
                # Verify we're in the right call window
                if get_call_preference_window(target.call_preference):
                    call_result = await self._initiate_call(alert, mum_client, {
                        'monthly_savings': monthly_savings,
                        'annual_savings': annual_savings,
                        'client_rate': client_rate,
                        'market_rate': market_rate,
                    })

                    if call_result.get('status') == 'initiated':
                        history.call_initiated = True
                        result['call_initiated'] = True
                else:
                    logger.debug(f"Outside call window for preference {target.call_preference}")

        # Save history
        self.db.add(history)
        self.db.commit()

        # Update alert with history ID if created
        if result['alert_created']:
            alert.history_id = history.id
            self.db.commit()

        return result

    def _determine_priority(self, monthly_savings: float, rate_difference: float) -> str:
        """
        Determine alert priority based on savings potential.

        Args:
            monthly_savings: Monthly savings amount
            rate_difference: Rate drop percentage

        Returns:
            Priority level: 'low', 'medium', 'high', or 'urgent'
        """
        if monthly_savings >= 400 or rate_difference >= 1.0:
            return 'urgent'
        elif monthly_savings >= 250 or rate_difference >= 0.75:
            return 'high'
        elif monthly_savings >= 150 or rate_difference >= 0.5:
            return 'medium'
        else:
            return 'low'

    async def _initiate_call(
        self,
        alert: RateMonitorAlert,
        mum_client: Any,
        savings_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Initiate an AI call for the alert.

        Args:
            alert: The alert to call about
            mum_client: MUM client to call
            savings_info: Savings information

        Returns:
            Call result dict
        """
        call_service = self._get_call_service()

        if not call_service:
            return {'status': 'service_unavailable'}

        try:
            result = await call_service.initiate_refinance_call(
                alert_id=alert.id,
                mum_client=mum_client,
                savings_info=savings_info,
            )

            if result.get('status') == 'initiated':
                alert.auto_call_attempted = True
                alert.vapi_call_id = result.get('vapi_call_id')
                alert.call_status = 'initiated'
                self.db.commit()

            return result

        except Exception as e:
            logger.error(f"Error initiating call for alert {alert.id}: {e}")
            alert.auto_call_attempted = True
            alert.call_status = 'error'
            self.db.commit()
            return {'status': 'error', 'message': str(e)}


async def run_rate_monitor_job(db: Session) -> Dict[str, Any]:
    """
    Entry point for running the rate monitor job.

    This function is called by the scheduler.
    """
    job = RateMonitorJob(db)
    return await job.run()


# APScheduler job function (sync wrapper for async job)
def rate_monitor_job_sync():
    """
    Synchronous wrapper for APScheduler.

    Creates its own database session and runs the async job.
    """
    import asyncio
    from database import SessionLocal

    db = SessionLocal()
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(run_rate_monitor_job(db))
        logger.info(f"Rate monitor job result: {result}")
    except Exception as e:
        logger.error(f"Rate monitor job error: {e}")
    finally:
        db.close()


def schedule_rate_monitor_job(scheduler):
    """
    Schedule the rate monitor job with APScheduler.

    Runs every 15 minutes during business hours.

    Args:
        scheduler: APScheduler AsyncIOScheduler instance
    """
    from apscheduler.triggers.cron import CronTrigger

    # Run every 15 minutes on weekdays between 8am and 6pm Pacific
    trigger = CronTrigger(
        day_of_week='mon-fri',
        hour='8-17',
        minute='*/15',
        timezone=TIMEZONE
    )

    scheduler.add_job(
        rate_monitor_job_sync,
        trigger=trigger,
        id='rate_monitor_job',
        name='Rate Monitor Job',
        replace_existing=True,
        max_instances=1,
    )

    logger.info("Rate monitor job scheduled: every 15 minutes, Mon-Fri 8am-6pm PT")
