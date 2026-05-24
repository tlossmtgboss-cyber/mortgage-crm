"""
Refinance Outreach Service
Orchestrates SMS and AI call outreach for refinance opportunities.

Features:
- SMS with savings info
- AI-powered outbound calls via VAPI
- Appointment scheduling integration
- Outreach status tracking
"""

import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

# Configuration
OUTREACH_SMS_DELAY_MINUTES = int(os.getenv('OUTREACH_SMS_DELAY_MINUTES', '30'))
OUTREACH_CALL_WINDOW_START = int(os.getenv('OUTREACH_CALL_WINDOW_START', '9'))
OUTREACH_CALL_WINDOW_END = int(os.getenv('OUTREACH_CALL_WINDOW_END', '17'))
BUSINESS_NAME = os.getenv('BUSINESS_NAME', 'CMG Home Loans')
LO_NAME = os.getenv('LO_NAME', 'Tim')


class RefinanceOutreachService:
    """
    Service for managing outreach to refinance opportunity clients.
    Handles SMS notifications and AI call scheduling.
    """

    def __init__(self, db: Session):
        self.db = db
        self._notification_service = None
        self._vapi_service = None
        self.business_name = BUSINESS_NAME
        self.lo_name = LO_NAME

    def _get_notification_service(self):
        """Lazy load notification service."""
        if self._notification_service is None:
            try:
                from services.notification_service import notification_service
                self._notification_service = notification_service
            except Exception as e:
                logger.error(f"Failed to load notification service: {e}")
        return self._notification_service

    def _get_vapi_service(self):
        """Lazy load VAPI service."""
        if self._vapi_service is None:
            try:
                from vapi_service import VapiCRMIntegration
                self._vapi_service = VapiCRMIntegration(self.db)
            except Exception as e:
                logger.error(f"Failed to load VAPI service: {e}")
        return self._vapi_service

    async def send_opportunity_sms(
        self,
        opportunity_id: int,
    ) -> Dict[str, Any]:
        """
        Send SMS notification about refinance opportunity.

        Args:
            opportunity_id: ID of the refinance opportunity

        Returns:
            Dict with SMS send result
        """
        from models.rate_sheet import RefinanceOpportunity

        opportunity = self.db.query(RefinanceOpportunity).filter(
            RefinanceOpportunity.id == opportunity_id
        ).first()

        if not opportunity:
            return {
                'success': False,
                'error': f'Opportunity {opportunity_id} not found',
            }

        if not opportunity.client_phone:
            return {
                'success': False,
                'error': 'No phone number on file',
            }

        # Build SMS message
        message = self._build_opportunity_sms(opportunity)

        notification_service = self._get_notification_service()
        if not notification_service:
            logger.warning("Notification service not available - logging SMS only")
            return {
                'success': True,
                'dry_run': True,
                'message': message,
            }

        # Send SMS
        result = notification_service.send_sms(
            to_phone=opportunity.client_phone,
            message=message,
        )

        if result.get('success'):
            # Update opportunity status
            opportunity.status = 'sms_sent'
            opportunity.sms_sent_at = datetime.now(timezone.utc)
            opportunity.sms_message_sid = result.get('message_sid')
            self.db.commit()

            logger.info(f"SMS sent for opportunity {opportunity_id}")

        return {
            'success': result.get('success', False),
            'opportunity_id': opportunity_id,
            'message_sid': result.get('message_sid'),
            'error': result.get('error'),
        }

    def _build_opportunity_sms(self, opportunity) -> str:
        """Build SMS message for refinance opportunity."""
        first_name = opportunity.client_name.split()[0] if opportunity.client_name else 'there'
        monthly_savings = float(opportunity.monthly_savings) if opportunity.monthly_savings else 0
        annual_savings = float(opportunity.annual_savings) if opportunity.annual_savings else 0
        current_rate = float(opportunity.current_rate) if opportunity.current_rate else 0
        new_rate = float(opportunity.new_rate) if opportunity.new_rate else 0

        message = (
            f"Hi {first_name},\n\n"
            f"Great news! Based on today's rates, you could save ${monthly_savings:,.0f}/month on your mortgage.\n\n"
            f"Current rate: {current_rate:.3f}%\n"
            f"Available rate: {new_rate:.3f}%\n"
            f"Annual savings: ${annual_savings:,.0f}\n\n"
            f"{self.lo_name} will call you shortly to discuss."
        )

        return message

    async def initiate_opportunity_call(
        self,
        opportunity_id: int,
        custom_message: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Initiate an AI call for a refinance opportunity.

        Args:
            opportunity_id: ID of the refinance opportunity
            custom_message: Optional custom opening message

        Returns:
            Dict with call initiation result
        """
        from models.rate_sheet import RefinanceOpportunity

        opportunity = self.db.query(RefinanceOpportunity).filter(
            RefinanceOpportunity.id == opportunity_id
        ).first()

        if not opportunity:
            return {
                'success': False,
                'error': f'Opportunity {opportunity_id} not found',
            }

        if not opportunity.client_phone:
            return {
                'success': False,
                'error': 'No phone number on file',
            }

        # Check call window in RECIPIENT's timezone (TCPA compliance)
        try:
            from telephony.compliance import resolve_recipient_timezone
            from zoneinfo import ZoneInfo
            recipient_tz_name = resolve_recipient_timezone(opportunity.client_phone)
            recipient_tz = ZoneInfo(recipient_tz_name)
            recipient_hour = datetime.now(timezone.utc).astimezone(recipient_tz).hour
        except Exception:
            # Fallback to server time if timezone resolution fails
            recipient_hour = datetime.now().hour
            recipient_tz_name = "server"

        if not (OUTREACH_CALL_WINDOW_START <= recipient_hour < OUTREACH_CALL_WINDOW_END):
            return {
                'success': False,
                'error': (
                    f'Outside call window ({OUTREACH_CALL_WINDOW_START}:00-'
                    f'{OUTREACH_CALL_WINDOW_END}:00 in recipient timezone {recipient_tz_name})'
                ),
                'call_window_start': OUTREACH_CALL_WINDOW_START,
                'call_window_end': OUTREACH_CALL_WINDOW_END,
                'recipient_timezone': recipient_tz_name,
            }

        # Build call context
        call_context = self._build_call_context(opportunity, custom_message)

        vapi_service = self._get_vapi_service()
        if not vapi_service:
            logger.warning("VAPI service not available - logging call attempt only")
            return {
                'success': True,
                'dry_run': True,
                'context': call_context,
            }

        try:
            # Get assistant ID
            assistant_id = os.getenv(
                'VAPI_REFINANCE_ASSISTANT_ID',
                os.getenv('VAPI_ASSISTANT_ID')
            )

            # Create outbound call
            call_response = await vapi_service.vapi.create_phone_call(
                assistant_id=assistant_id,
                customer_number=opportunity.client_phone,
                customer_name=opportunity.client_name,
                metadata={
                    'opportunity_id': opportunity_id,
                    'call_type': 'refinance_opportunity',
                    'monthly_savings': float(opportunity.monthly_savings) if opportunity.monthly_savings else 0,
                    'annual_savings': float(opportunity.annual_savings) if opportunity.annual_savings else 0,
                    'context': call_context,
                }
            )

            vapi_call_id = call_response.get('id')

            # Update opportunity
            opportunity.status = 'called'
            opportunity.call_initiated_at = datetime.now(timezone.utc)
            opportunity.vapi_call_id = vapi_call_id
            opportunity.call_status = 'initiated'
            self.db.commit()

            logger.info(f"Call initiated for opportunity {opportunity_id}, VAPI call ID: {vapi_call_id}")

            return {
                'success': True,
                'opportunity_id': opportunity_id,
                'vapi_call_id': vapi_call_id,
                'client_name': opportunity.client_name,
            }

        except SQLAlchemyError as e:
            logger.error(f"Failed to initiate call for opportunity {opportunity_id}: {e}")
            return {
                'success': False,
                'error': str(e),
            }

    def _build_call_context(
        self,
        opportunity,
        custom_message: Optional[str] = None
    ) -> Dict[str, Any]:
        """Build context for the AI call."""
        monthly_savings = float(opportunity.monthly_savings) if opportunity.monthly_savings else 0
        annual_savings = float(opportunity.annual_savings) if opportunity.annual_savings else 0
        current_rate = float(opportunity.current_rate) if opportunity.current_rate else 0
        new_rate = float(opportunity.new_rate) if opportunity.new_rate else 0

        # Determine enthusiasm level
        if monthly_savings >= 300:
            savings_tier = 'high'
            enthusiasm = 'This is a significant savings opportunity!'
        elif monthly_savings >= 150:
            savings_tier = 'medium'
            enthusiasm = 'This is a great opportunity to lower your payments.'
        else:
            savings_tier = 'low'
            enthusiasm = 'Even small savings add up over time.'

        first_name = opportunity.client_name.split()[0] if opportunity.client_name else 'there'

        context = {
            'customer': {
                'name': opportunity.client_name,
                'first_name': first_name,
            },
            'current_loan': {
                'rate': current_rate,
                'rate_formatted': f"{current_rate:.3f}%",
                'amount': float(opportunity.current_loan_amount) if opportunity.current_loan_amount else 0,
            },
            'opportunity': {
                'new_rate': new_rate,
                'new_rate_formatted': f"{new_rate:.3f}%",
                'rate_drop': round(current_rate - new_rate, 3),
                'monthly_savings': monthly_savings,
                'monthly_savings_formatted': f"${monthly_savings:,.0f}",
                'annual_savings': annual_savings,
                'annual_savings_formatted': f"${annual_savings:,.0f}",
                'savings_tier': savings_tier,
                'enthusiasm': enthusiasm,
            },
            'business': {
                'name': self.business_name,
                'lo_name': self.lo_name,
            },
            'call_type': 'refinance_opportunity',
            'custom_message': custom_message,
        }

        context['suggested_opening'] = custom_message or (
            f"Hi {first_name}, this is the AI assistant calling on behalf of {self.lo_name} "
            f"at {self.business_name}. I'm reaching out because with recent rate changes, "
            f"we've identified that you could potentially save around ${monthly_savings:,.0f} per month "
            f"on your mortgage. Do you have a moment to discuss this opportunity?"
        )

        return context

    async def trigger_outreach_sequence(
        self,
        opportunity_id: int,
        skip_sms: bool = False,
    ) -> Dict[str, Any]:
        """
        Trigger the full outreach sequence: SMS first, then call.

        Args:
            opportunity_id: ID of the refinance opportunity
            skip_sms: If True, skip SMS and go directly to call

        Returns:
            Dict with outreach sequence result
        """
        results = {
            'opportunity_id': opportunity_id,
            'sms_result': None,
            'call_result': None,
        }

        if not skip_sms:
            # Send SMS first
            sms_result = await self.send_opportunity_sms(opportunity_id)
            results['sms_result'] = sms_result

            if not sms_result.get('success') and not sms_result.get('dry_run'):
                return {
                    'success': False,
                    'error': 'SMS send failed',
                    'results': results,
                }

        # Initiate call
        call_result = await self.initiate_opportunity_call(opportunity_id)
        results['call_result'] = call_result

        return {
            'success': call_result.get('success', False),
            'results': results,
        }

    async def bulk_outreach(
        self,
        opportunity_ids: List[int],
        skip_sms: bool = False,
    ) -> Dict[str, Any]:
        """
        Trigger outreach for multiple opportunities.

        Args:
            opportunity_ids: List of opportunity IDs
            skip_sms: If True, skip SMS and go directly to call

        Returns:
            Dict with bulk outreach results
        """
        results = []
        success_count = 0
        error_count = 0

        for opp_id in opportunity_ids:
            try:
                result = await self.trigger_outreach_sequence(opp_id, skip_sms)
                results.append({
                    'opportunity_id': opp_id,
                    'success': result.get('success', False),
                    'error': result.get('error'),
                })
                if result.get('success'):
                    success_count += 1
                else:
                    error_count += 1
            except Exception as e:
                logger.error(f"Error in bulk outreach for opportunity {opp_id}: {e}")
                results.append({
                    'opportunity_id': opp_id,
                    'success': False,
                    'error': str(e),
                })
                error_count += 1

        return {
            'total': len(opportunity_ids),
            'success_count': success_count,
            'error_count': error_count,
            'results': results,
        }

    async def handle_call_completed(
        self,
        vapi_call_id: str,
        call_data: Dict[str, Any],
    ) -> None:
        """
        Handle webhook notification when a call completes.

        Updates opportunity status based on call outcome.
        """
        from models.rate_sheet import RefinanceOpportunity

        opportunity = self.db.query(RefinanceOpportunity).filter(
            RefinanceOpportunity.vapi_call_id == vapi_call_id
        ).first()

        if not opportunity:
            logger.warning(f"No opportunity found for VAPI call {vapi_call_id}")
            return

        # Extract call outcome
        call_status = call_data.get('status', 'unknown')
        duration = call_data.get('duration', 0)
        analysis = call_data.get('analysis', {})

        opportunity.call_status = call_status
        opportunity.call_duration = duration
        opportunity.call_summary = analysis.get('summary')

        # Determine outcome from analysis
        summary_lower = (analysis.get('summary') or '').lower()

        if 'appointment' in summary_lower or 'scheduled' in summary_lower:
            opportunity.call_outcome = 'appointment_scheduled'
            opportunity.status = 'scheduled'
            opportunity.appointment_scheduled_at = datetime.now(timezone.utc)

        elif 'callback' in summary_lower or 'call back' in summary_lower:
            opportunity.call_outcome = 'callback_requested'
            opportunity.status = 'called'

        elif 'not interested' in summary_lower or 'no thanks' in summary_lower:
            opportunity.call_outcome = 'not_interested'
            opportunity.status = 'declined'

        elif 'voicemail' in summary_lower or 'no answer' in summary_lower:
            opportunity.call_outcome = 'voicemail'
            # Keep status as 'called' for potential retry

        else:
            opportunity.call_outcome = 'completed'
            opportunity.status = 'called'

        self.db.commit()

        logger.info(f"Updated opportunity {opportunity.id} after call: {opportunity.call_outcome}")

    def mark_opted_out(self, opportunity_id: int) -> bool:
        """Mark an opportunity as opted out."""
        from models.rate_sheet import RefinanceOpportunity

        opportunity = self.db.query(RefinanceOpportunity).filter(
            RefinanceOpportunity.id == opportunity_id
        ).first()

        if opportunity:
            opportunity.status = 'opted_out'
            self.db.commit()
            return True
        return False

    def mark_converted(self, opportunity_id: int, notes: Optional[str] = None) -> bool:
        """Mark an opportunity as converted."""
        from models.rate_sheet import RefinanceOpportunity

        opportunity = self.db.query(RefinanceOpportunity).filter(
            RefinanceOpportunity.id == opportunity_id
        ).first()

        if opportunity:
            opportunity.status = 'converted'
            if notes:
                opportunity.notes = notes
            self.db.commit()
            return True
        return False
