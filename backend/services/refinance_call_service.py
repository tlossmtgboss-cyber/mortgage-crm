"""
Refinance Call Service
Integrates with VAPI to initiate outbound calls for refinance opportunities.

Features:
- Initiates AI-powered outbound calls to MUM clients
- Builds context-aware call scripts based on savings potential
- Schedules appointments with refinance team
- Sends follow-up SMS with rate details
"""

import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


class RefinanceCallService:
    """
    Service for initiating AI-powered refinance opportunity calls.

    Uses VAPI for outbound calls with a specialized refinance assistant
    that discusses savings opportunities and schedules consultations.
    """

    def __init__(self, db: Session):
        self.db = db
        self._vapi_service = None
        self._sms_service = None

        # Configuration
        self.refinance_assistant_id = os.getenv(
            'VAPI_REFINANCE_ASSISTANT_ID',
            os.getenv('VAPI_ASSISTANT_ID')  # Fallback to default assistant
        )
        self.calendly_link = os.getenv('CALENDLY_LINK', 'https://calendly.com/timloss/discovery-call')
        self.business_name = os.getenv('BUSINESS_NAME', 'CMG Home Loans')
        self.lo_name = os.getenv('LO_NAME', 'Tim')

    def _get_vapi_service(self):
        """Lazy load VAPI service."""
        if self._vapi_service is None:
            try:
                from vapi_service import VapiCRMIntegration
                self._vapi_service = VapiCRMIntegration(self.db)
            except Exception as e:
                logger.error(f"Failed to initialize VAPI service: {e}")
                return None
        return self._vapi_service

    def _get_sms_service(self):
        """Lazy load SMS service."""
        if self._sms_service is None:
            try:
                from vapi_service import AIReceptionistSMSService
                self._sms_service = AIReceptionistSMSService(self.db)
            except Exception as e:
                logger.error(f"Failed to initialize SMS service: {e}")
                return None
        return self._sms_service

    async def initiate_refinance_call(
        self,
        alert_id: int,
        mum_client: Any,
        savings_info: Dict[str, Any],
        custom_message: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Initiate an AI call to discuss refinance opportunity.

        Args:
            alert_id: Rate monitor alert ID
            mum_client: MUM client object
            savings_info: Dict with monthly_savings, annual_savings, client_rate, market_rate
            custom_message: Optional custom opening message

        Returns:
            Dict with call status and details
        """
        vapi = self._get_vapi_service()

        if not vapi:
            logger.warning("VAPI service not available - logging call attempt only")
            return {
                'status': 'service_unavailable',
                'message': 'VAPI service not configured',
                'alert_id': alert_id,
            }

        if not mum_client.phone:
            return {
                'status': 'no_phone',
                'message': 'Client has no phone number on file',
                'alert_id': alert_id,
            }

        # Build call context
        call_context = self._build_call_context(mum_client, savings_info, custom_message)

        try:
            # Use VAPI to create the outbound call
            # Note: This creates a call via the VAPI API
            call_response = await vapi.vapi.create_phone_call(
                assistant_id=self.refinance_assistant_id,
                customer_number=mum_client.phone,
                customer_name=mum_client.client_name,
                metadata={
                    'alert_id': alert_id,
                    'mum_client_id': mum_client.id,
                    'call_type': 'refinance_opportunity',
                    'monthly_savings': savings_info.get('monthly_savings', 0),
                    'annual_savings': savings_info.get('annual_savings', 0),
                    'context': call_context,
                }
            )

            vapi_call_id = call_response.get('id')

            # Log the call in our database
            await self._log_call_attempt(
                alert_id=alert_id,
                mum_client_id=mum_client.id,
                vapi_call_id=vapi_call_id,
                call_context=call_context,
            )

            logger.info(f"Initiated refinance call for alert {alert_id}, VAPI call ID: {vapi_call_id}")

            return {
                'status': 'initiated',
                'vapi_call_id': vapi_call_id,
                'alert_id': alert_id,
                'customer_name': mum_client.client_name,
                'phone': mum_client.phone,
            }

        except Exception as e:
            logger.error(f"Error initiating refinance call: {e}")
            return {
                'status': 'error',
                'message': str(e),
                'alert_id': alert_id,
            }

    def _build_call_context(
        self,
        mum_client: Any,
        savings_info: Dict[str, Any],
        custom_message: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Build context for the AI assistant to use during the call.

        This provides the assistant with all the information needed to have
        a personalized, savings-focused conversation.
        """
        monthly_savings = savings_info.get('monthly_savings', 0)
        annual_savings = savings_info.get('annual_savings', 0)
        client_rate = savings_info.get('client_rate', 0)
        market_rate = savings_info.get('market_rate', 0)

        # Determine call urgency/enthusiasm level
        if monthly_savings >= 300:
            savings_tier = 'high'
            enthusiasm = 'This is a significant savings opportunity!'
        elif monthly_savings >= 150:
            savings_tier = 'medium'
            enthusiasm = 'This is a great opportunity to lower your payments.'
        else:
            savings_tier = 'low'
            enthusiasm = 'Even small savings add up over time.'

        context = {
            'customer': {
                'name': mum_client.client_name,
                'first_name': mum_client.client_name.split()[0] if mum_client.client_name else 'there',
            },
            'current_loan': {
                'rate': client_rate,
                'rate_formatted': f"{client_rate:.3f}%" if client_rate else 'N/A',
            },
            'opportunity': {
                'market_rate': market_rate,
                'market_rate_formatted': f"{market_rate:.3f}%" if market_rate else 'N/A',
                'rate_drop': round(client_rate - market_rate, 3) if client_rate and market_rate else 0,
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
                'calendly_link': self.calendly_link,
            },
            'call_type': 'refinance_opportunity',
            'custom_message': custom_message,
        }

        # Generate suggested opening
        first_name = context['customer']['first_name']
        savings_formatted = context['opportunity']['monthly_savings_formatted']

        context['suggested_opening'] = custom_message or (
            f"Hi {first_name}, this is the AI assistant calling on behalf of {self.lo_name} "
            f"at {self.business_name}. I'm reaching out because with recent rate changes, "
            f"we've identified that you could potentially save around {savings_formatted} per month "
            f"on your mortgage. Do you have a moment to discuss this opportunity?"
        )

        return context

    async def _log_call_attempt(
        self,
        alert_id: int,
        mum_client_id: int,
        vapi_call_id: str,
        call_context: Dict[str, Any],
    ) -> None:
        """Log the call attempt in the database."""
        try:
            from models.rate_monitor import RateMonitorAlert

            alert = self.db.query(RateMonitorAlert).filter(
                RateMonitorAlert.id == alert_id
            ).first()

            if alert:
                alert.auto_call_attempted = True
                alert.vapi_call_id = vapi_call_id
                alert.call_status = 'initiated'
                self.db.commit()

        except SQLAlchemyError as e:
            logger.error(f"Error logging call attempt: {e}")

    async def send_post_call_followup(
        self,
        mum_client: Any,
        savings_info: Dict[str, Any],
        appointment_scheduled: bool = False,
        appointment_time: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send SMS follow-up after a refinance call.

        Args:
            mum_client: MUM client object
            savings_info: Savings information from the alert
            appointment_scheduled: Whether an appointment was scheduled
            appointment_time: Scheduled appointment time if any

        Returns:
            SMS result dict
        """
        sms = self._get_sms_service()

        if not sms:
            logger.warning("SMS service not available")
            return {'status': 'service_unavailable'}

        if not mum_client.phone:
            return {'status': 'no_phone'}

        monthly_savings = savings_info.get('monthly_savings', 0)
        client_rate = savings_info.get('client_rate', 0)
        market_rate = savings_info.get('market_rate', 0)

        first_name = mum_client.client_name.split()[0] if mum_client.client_name else 'there'

        if appointment_scheduled and appointment_time:
            # Appointment confirmation
            message = (
                f"Hi {first_name}! Thanks for speaking with us about your refinance opportunity. "
                f"Your consultation is confirmed for {appointment_time}. "
                f"As discussed, current rates could save you approximately ${monthly_savings:,.0f}/month. "
                f"We'll review all your options then!\n\n"
                f"Need to reschedule? {self.calendly_link}\n\n"
                f"- {self.lo_name} at {self.business_name}"
            )
        else:
            # General follow-up with rate details
            message = (
                f"Hi {first_name}! Thanks for speaking with us about refinancing. "
                f"As mentioned, your current rate of {client_rate:.3f}% could potentially be reduced to "
                f"around {market_rate:.3f}%, saving you approximately ${monthly_savings:,.0f}/month.\n\n"
                f"Ready to explore your options? Schedule a consultation:\n"
                f"{self.calendly_link}\n\n"
                f"Questions? Just reply to this text.\n"
                f"- {self.lo_name} at {self.business_name}"
            )

        try:
            return await sms.send_post_call_followup(
                phone_number=mum_client.phone,
                caller_name=first_name,
                call_summary=f"Discussed refinance opportunity with potential savings of ${monthly_savings:,.0f}/month",
                appointment_scheduled=appointment_scheduled,
                appointment_time=appointment_time,
                include_calendly=not appointment_scheduled,
            )
        except Exception as e:
            logger.error(f"Error sending refinance follow-up SMS: {e}")
            return {'status': 'error', 'message': str(e)}

    async def handle_call_completed(
        self,
        vapi_call_id: str,
        call_data: Dict[str, Any],
    ) -> None:
        """
        Handle webhook notification when a refinance call completes.

        Updates alert status, extracts call outcome, and sends follow-up SMS.

        Args:
            vapi_call_id: VAPI call ID
            call_data: Call completion data from VAPI webhook
        """
        try:
            from models.rate_monitor import RateMonitorAlert, RateMonitorTarget

            # Find the alert by VAPI call ID
            alert = self.db.query(RateMonitorAlert).filter(
                RateMonitorAlert.vapi_call_id == vapi_call_id
            ).first()

            if not alert:
                logger.warning(f"No alert found for VAPI call {vapi_call_id}")
                return

            # Extract call outcome from VAPI data
            call_status = call_data.get('status', 'unknown')
            duration = call_data.get('duration', 0)
            analysis = call_data.get('analysis', {})

            # Update alert
            alert.call_status = call_status
            alert.call_duration = duration
            alert.call_summary = analysis.get('summary')

            # Try to determine outcome from analysis
            summary_lower = (analysis.get('summary') or '').lower()

            if 'appointment' in summary_lower or 'scheduled' in summary_lower:
                alert.call_outcome = 'appointment_scheduled'
                alert.status = 'called'

                # Try to extract appointment time from structured data
                tool_calls = call_data.get('messages', [])
                for msg in tool_calls:
                    if msg.get('type') == 'tool-call' and 'schedule' in str(msg).lower():
                        # Extract appointment details if available
                        alert.appointment_scheduled_at = datetime.now(timezone.utc)
                        break

            elif 'callback' in summary_lower or 'call back' in summary_lower:
                alert.call_outcome = 'callback_requested'
                alert.status = 'called'

            elif 'not interested' in summary_lower or 'no thanks' in summary_lower:
                alert.call_outcome = 'not_interested'
                alert.status = 'dismissed'

            elif 'voicemail' in summary_lower or 'no answer' in summary_lower:
                alert.call_outcome = 'voicemail'
                alert.status = 'pending'  # Keep pending for retry

            else:
                alert.call_outcome = 'completed'
                alert.status = 'called'

            # Update target with call tracking
            if alert.target_id:
                target = self.db.query(RateMonitorTarget).filter(
                    RateMonitorTarget.id == alert.target_id
                ).first()

                if target:
                    target.last_call_at = datetime.now(timezone.utc)
                    target.last_call_status = call_status
                    target.vapi_call_id = vapi_call_id

                    if alert.call_outcome == 'appointment_scheduled':
                        target.appointment_scheduled = True
                        target.appointment_date = alert.appointment_scheduled_at

            self.db.commit()

            # Send follow-up SMS if call was answered
            if duration and duration > 30 and alert.mum_client_id:
                try:
                    from database.models import MUMClient
                    mum_client = self.db.query(MUMClient).filter(
                        MUMClient.id == alert.mum_client_id
                    ).first()

                    if mum_client:
                        await self.send_post_call_followup(
                            mum_client=mum_client,
                            savings_info={
                                'monthly_savings': float(alert.monthly_savings) if alert.monthly_savings else 0,
                                'client_rate': float(alert.client_rate) if alert.client_rate else 0,
                                'market_rate': float(alert.market_rate) if alert.market_rate else 0,
                            },
                            appointment_scheduled=(alert.call_outcome == 'appointment_scheduled'),
                        )
                except SQLAlchemyError as e:
                    logger.error(f"Error sending post-call SMS: {e}")

            logger.info(f"Processed refinance call completion for alert {alert.id}, outcome: {alert.call_outcome}")

        except Exception as e:
            logger.error(f"Error handling call completion: {e}")


def get_refinance_assistant_prompt(context: Dict[str, Any]) -> str:
    """
    Generate the system prompt for the refinance AI assistant.

    This can be used to configure a VAPI assistant for refinance calls.
    """
    customer = context.get('customer', {})
    opportunity = context.get('opportunity', {})
    business = context.get('business', {})

    prompt = f"""You are a friendly and professional AI assistant helping {business.get('lo_name', 'the loan officer')} at {business.get('name', 'the mortgage company')} reach out to clients about refinance opportunities.

## Your Goal
Your primary goal is to inform the client about their potential savings opportunity and, if they're interested, schedule a consultation with the refinance team.

## Context for This Call
- Customer: {customer.get('name', 'the client')}
- Current Rate: {opportunity.get('rate_formatted', 'N/A')}
- New Potential Rate: {opportunity.get('market_rate_formatted', 'N/A')}
- Estimated Monthly Savings: {opportunity.get('monthly_savings_formatted', 'N/A')}
- Estimated Annual Savings: {opportunity.get('annual_savings_formatted', 'N/A')}

## Guidelines
1. Be warm, friendly, and conversational - not salesy
2. Lead with the value proposition (savings) upfront
3. Acknowledge this is an AI assistant, but you represent the loan officer
4. If they're interested, offer to schedule a consultation
5. If they're not interested or it's a bad time, be respectful and offer to follow up later
6. Always offer to send details via text message
7. Keep the call focused and respectful of their time

## Scheduling
If the customer wants to schedule a consultation, use the scheduling tool to book an appointment. The calendly link is: {business.get('calendly_link', 'N/A')}

## Handling Objections
- "Not interested": Acknowledge politely, mention rates change and you can check back. Ask if they'd like a text with the details to review on their own time.
- "Bad time": Offer to call back at a specific time or send information via text.
- "Already refinanced": Thank them and update their file, offer to monitor rates for future opportunities.
- "Working with someone else": Wish them well, mention you're here if they want a second opinion.

Remember: You're here to help, not to pressure. A positive interaction that doesn't result in an appointment is still valuable for the relationship."""

    return prompt
