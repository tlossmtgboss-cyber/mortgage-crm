"""
Survey Service
Business logic for survey delivery, analytics, and sentiment analysis.

Contains:
  - SurveyService:            Legacy loan-event-based survey system
  - SurveyTriggerService:     Triggers surveys from loan events
  - AppointmentSurveyService: Post-appointment feedback surveys (token-based)
"""

import logging
import os
import secrets as _secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, case

logger = logging.getLogger(__name__)

FRONTEND_URL = os.getenv("FRONTEND_URL", "https://app.perenniaai.com")
SURVEY_EXPIRY_DAYS = 14  # Post-appointment surveys expire after 14 days


class SurveyService:
    """Service for survey operations."""

    def __init__(self, db: Session):
        self.db = db

    async def send_survey_email(
        self,
        email: str,
        template_name: str,
        survey_url: str,
        intro_message: Optional[str] = None,
        borrower_name: Optional[str] = None,
        loan_officer_name: Optional[str] = None,
    ) -> bool:
        """
        Send survey invitation email.

        Returns True if email was sent successfully.
        """
        try:
            from email_service import email_service

            subject = f"We'd love your feedback - {template_name}"

            # Build email content
            html_content = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background-color: #319795; padding: 20px; text-align: center;">
                    <h1 style="color: white; margin: 0;">Your Feedback Matters</h1>
                </div>

                <div style="padding: 30px; background-color: #f7f7f7;">
                    <p style="font-size: 16px; color: #333;">
                        Hi{' ' + borrower_name if borrower_name else ''},
                    </p>

                    {f'<p style="font-size: 16px; color: #333;">{intro_message}</p>' if intro_message else ''}

                    <p style="font-size: 16px; color: #333;">
                        We would greatly appreciate if you could take a moment to share your experience with us.
                        Your feedback helps us improve our services.
                    </p>

                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{survey_url}"
                           style="background-color: #319795; color: white; padding: 15px 30px;
                                  text-decoration: none; border-radius: 5px; font-size: 16px;">
                            Take the Survey
                        </a>
                    </div>

                    <p style="font-size: 14px; color: #666;">
                        This survey takes less than 2 minutes to complete.
                    </p>

                    {f'<p style="font-size: 14px; color: #666;">Best regards,<br>{loan_officer_name}</p>' if loan_officer_name else ''}
                </div>

                <div style="padding: 20px; text-align: center; background-color: #e2e8f0;">
                    <p style="font-size: 12px; color: #666; margin: 0;">
                        This survey is powered by Perennia AI
                    </p>
                </div>
            </div>
            """

            text_content = f"""
            Hi{' ' + borrower_name if borrower_name else ''},

            {intro_message if intro_message else 'We would love to hear about your experience.'}

            Please take a moment to complete our brief survey:
            {survey_url}

            This survey takes less than 2 minutes to complete.

            {f'Best regards, {loan_officer_name}' if loan_officer_name else 'Thank you for your time.'}
            """

            result = await email_service.send_email(
                to_email=email,
                subject=subject,
                html_content=html_content,
                text_content=text_content,
            )

            return result.get("success", False)

        except Exception as e:
            logger.error(f"Failed to send survey email to {email}: {e}")
            return False

    async def send_reminder_email(
        self,
        email: str,
        template_name: str,
        survey_url: str,
        reminder_number: int = 1,
        borrower_name: Optional[str] = None,
    ) -> bool:
        """Send survey reminder email."""
        try:
            from email_service import email_service

            subject = f"Reminder: We'd still love your feedback - {template_name}"

            html_content = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background-color: #319795; padding: 20px; text-align: center;">
                    <h1 style="color: white; margin: 0;">Quick Reminder</h1>
                </div>

                <div style="padding: 30px; background-color: #f7f7f7;">
                    <p style="font-size: 16px; color: #333;">
                        Hi{' ' + borrower_name if borrower_name else ''},
                    </p>

                    <p style="font-size: 16px; color: #333;">
                        We noticed you haven't completed our feedback survey yet.
                        Your input is incredibly valuable to us!
                    </p>

                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{survey_url}"
                           style="background-color: #319795; color: white; padding: 15px 30px;
                                  text-decoration: none; border-radius: 5px; font-size: 16px;">
                            Complete Survey Now
                        </a>
                    </div>

                    <p style="font-size: 14px; color: #666;">
                        It only takes about 2 minutes.
                    </p>
                </div>
            </div>
            """

            result = await email_service.send_email(
                to_email=email,
                subject=subject,
                html_content=html_content,
            )

            return result.get("success", False)

        except Exception as e:
            logger.error(f"Failed to send reminder email to {email}: {e}")
            return False

    def analyze_sentiment(self, text: str) -> Dict[str, Any]:
        """
        Analyze sentiment of text response.

        Returns:
            dict with 'score' (-1 to 1), 'sentiment' level, and 'key_phrases'
        """
        if not text or len(text) < 5:
            return {"score": 0.0, "sentiment": "neutral", "key_phrases": []}

        text_lower = text.lower()

        # Positive indicators
        positive_words = {
            "excellent": 0.9, "amazing": 0.9, "outstanding": 0.9, "fantastic": 0.85,
            "wonderful": 0.85, "great": 0.7, "good": 0.5, "helpful": 0.6,
            "professional": 0.6, "efficient": 0.6, "responsive": 0.65,
            "smooth": 0.6, "easy": 0.5, "quick": 0.5, "love": 0.8,
            "recommend": 0.7, "thank": 0.5, "appreciate": 0.6,
            "best": 0.8, "happy": 0.7, "pleased": 0.65, "satisfied": 0.6,
        }

        # Negative indicators
        negative_words = {
            "terrible": -0.9, "awful": -0.9, "horrible": -0.85, "worst": -0.9,
            "bad": -0.6, "poor": -0.65, "slow": -0.5, "frustrated": -0.7,
            "disappointed": -0.7, "confusing": -0.5, "difficult": -0.5,
            "unprofessional": -0.75, "rude": -0.8, "unresponsive": -0.65,
            "never": -0.4, "not": -0.3, "problem": -0.5, "issue": -0.4,
            "hate": -0.85, "angry": -0.7, "annoyed": -0.6,
        }

        # Calculate sentiment score
        total_score = 0.0
        word_count = 0

        for word, score in positive_words.items():
            if word in text_lower:
                total_score += score
                word_count += 1

        for word, score in negative_words.items():
            if word in text_lower:
                total_score += score  # score is already negative
                word_count += 1

        # Average score
        if word_count > 0:
            sentiment_score = total_score / word_count
        else:
            sentiment_score = 0.0

        # Clamp to -1 to 1
        sentiment_score = max(-1.0, min(1.0, sentiment_score))

        # Determine sentiment level
        if sentiment_score >= 0.6:
            sentiment_level = "very_positive"
        elif sentiment_score >= 0.2:
            sentiment_level = "positive"
        elif sentiment_score >= -0.2:
            sentiment_level = "neutral"
        elif sentiment_score >= -0.6:
            sentiment_level = "negative"
        else:
            sentiment_level = "very_negative"

        # Extract key phrases (simple word extraction)
        words = text.split()
        key_phrases = []
        for word in words:
            clean_word = word.strip(".,!?\"'").lower()
            if len(clean_word) > 5 and clean_word not in ["about", "would", "could", "should", "their", "there", "these", "those"]:
                if clean_word not in key_phrases:
                    key_phrases.append(clean_word)
                if len(key_phrases) >= 5:
                    break

        return {
            "score": round(sentiment_score, 3),
            "sentiment": sentiment_level,
            "key_phrases": key_phrases,
        }

    def calculate_nps(self, scores: List[int]) -> Optional[float]:
        """
        Calculate Net Promoter Score.

        NPS = (% Promoters - % Detractors) * 100
        Promoters: 9-10, Passives: 7-8, Detractors: 0-6
        """
        if not scores:
            return None

        promoters = len([s for s in scores if s >= 9])
        detractors = len([s for s in scores if s <= 6])
        total = len(scores)

        nps = ((promoters - detractors) / total) * 100
        return round(nps, 1)

    def calculate_csat(self, scores: List[float]) -> Optional[float]:
        """Calculate Customer Satisfaction Score (average)."""
        if not scores:
            return None
        return round(sum(scores) / len(scores), 2)

    async def process_scheduled_reminders(self, organization_id: Optional[int] = None):
        """
        Process scheduled survey reminders.

        Finds pending surveys that need reminders and sends them.
        """
        from models.surveying_models import SurveyResponse, SurveyTemplate, ResponseStatus

        # Build query for surveys needing reminders
        now = datetime.now(timezone.utc)

        query = self.db.query(SurveyResponse).join(
            SurveyTemplate,
            SurveyResponse.template_id == SurveyTemplate.id
        ).filter(
            and_(
                SurveyResponse.status == ResponseStatus.PENDING,
                SurveyTemplate.reminder_enabled == True,
                SurveyResponse.reminder_count < SurveyTemplate.max_reminders,
            )
        )

        if organization_id:
            query = query.filter(SurveyResponse.organization_id == organization_id)

        pending_responses = query.all()
        sent_count = 0

        for response in pending_responses:
            template = response.template

            # Check if it's time to send a reminder
            last_contact = response.last_reminder_at or response.sent_at
            if not last_contact:
                continue

            days_since_contact = (now - last_contact).days
            if days_since_contact >= template.reminder_days:
                # Send reminder
                survey_url = f"/survey/{response.access_token}"
                success = await self.send_reminder_email(
                    email=response.email,
                    template_name=template.name,
                    survey_url=survey_url,
                    reminder_number=response.reminder_count + 1,
                )

                if success:
                    response.reminder_count += 1
                    response.last_reminder_at = now
                    sent_count += 1

        self.db.commit()
        logger.info(f"Processed reminders: {sent_count} sent")
        return sent_count

    async def update_daily_analytics(self, organization_id: int, date: Optional[datetime] = None):
        """
        Update daily analytics snapshot for an organization.
        """
        from models.surveying_models import (
            SurveyResponse, SurveyAnalytics, ResponseStatus, SentimentLevel
        )

        target_date = date or datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        # Get responses for the day
        start_of_day = target_date
        end_of_day = target_date + timedelta(days=1)

        responses = self.db.query(SurveyResponse).filter(
            and_(
                SurveyResponse.organization_id == organization_id,
                SurveyResponse.sent_at >= start_of_day,
                SurveyResponse.sent_at < end_of_day,
            )
        ).all()

        if not responses:
            return None

        # Calculate metrics
        sent_count = len(responses)
        started_count = len([r for r in responses if r.started_at])
        completed_count = len([r for r in responses if r.status == ResponseStatus.COMPLETED])
        expired_count = len([r for r in responses if r.status == ResponseStatus.EXPIRED])

        completed_responses = [r for r in responses if r.status == ResponseStatus.COMPLETED]

        # NPS metrics
        nps_scores = [r.nps_score for r in completed_responses if r.nps_score is not None]
        nps_promoters = len([s for s in nps_scores if s >= 9])
        nps_passives = len([s for s in nps_scores if 7 <= s <= 8])
        nps_detractors = len([s for s in nps_scores if s <= 6])
        nps_calculated = self.calculate_nps(nps_scores)

        # CSAT metrics
        csat_scores = [r.csat_score for r in completed_responses if r.csat_score is not None]
        avg_csat = self.calculate_csat(csat_scores)

        # Sentiment breakdown
        sentiment_counts = {
            "very_positive": 0, "positive": 0, "neutral": 0,
            "negative": 0, "very_negative": 0,
        }
        for r in completed_responses:
            if r.sentiment:
                sentiment_counts[r.sentiment.value] = sentiment_counts.get(r.sentiment.value, 0) + 1

        # Average completion time
        completion_times = [r.completion_time_seconds for r in completed_responses if r.completion_time_seconds]
        avg_completion_time = round(sum(completion_times) / len(completion_times)) if completion_times else None

        # Check if analytics record exists for this date
        existing = self.db.query(SurveyAnalytics).filter(
            and_(
                SurveyAnalytics.organization_id == organization_id,
                SurveyAnalytics.date == target_date,
                SurveyAnalytics.template_id == None,  # Overall analytics
            )
        ).first()

        if existing:
            analytics = existing
        else:
            analytics = SurveyAnalytics(
                organization_id=organization_id,
                date=target_date,
            )
            self.db.add(analytics)

        # Update metrics
        analytics.sent_count = sent_count
        analytics.started_count = started_count
        analytics.completed_count = completed_count
        analytics.expired_count = expired_count
        analytics.response_rate = (completed_count / sent_count * 100) if sent_count > 0 else 0
        analytics.completion_rate = (completed_count / started_count * 100) if started_count > 0 else 0
        analytics.avg_nps_score = sum(nps_scores) / len(nps_scores) if nps_scores else None
        analytics.avg_csat_score = avg_csat
        analytics.nps_promoters = nps_promoters
        analytics.nps_passives = nps_passives
        analytics.nps_detractors = nps_detractors
        analytics.nps_calculated = nps_calculated
        analytics.sentiment_very_positive = sentiment_counts["very_positive"]
        analytics.sentiment_positive = sentiment_counts["positive"]
        analytics.sentiment_neutral = sentiment_counts["neutral"]
        analytics.sentiment_negative = sentiment_counts["negative"]
        analytics.sentiment_very_negative = sentiment_counts["very_negative"]
        analytics.avg_completion_time = avg_completion_time

        self.db.commit()
        return analytics


class SurveyTriggerService:
    """Service for handling survey triggers from loan events."""

    def __init__(self, db: Session):
        self.db = db

    async def trigger_survey_for_event(
        self,
        event_type: str,
        loan_id: int,
        organization_id: int,
    ) -> Optional[int]:
        """
        Trigger a survey based on a loan event.

        Returns the survey response ID if a survey was sent, None otherwise.
        """
        from models.surveying_models import (
            SurveyTemplate, SurveyResponse, SurveyStatus, TriggerType, ResponseStatus
        )
        import secrets

        # Map event types to trigger types
        event_trigger_map = {
            "loan_funded": TriggerType.LOAN_FUNDED,
            "loan_closed": TriggerType.LOAN_CLOSED,
            "application_submitted": TriggerType.APPLICATION_SUBMITTED,
            "milestone_reached": TriggerType.MILESTONE_REACHED,
        }

        trigger_type = event_trigger_map.get(event_type)
        if not trigger_type:
            logger.warning(f"Unknown event type: {event_type}")
            return None

        # Find active template for this trigger
        template = self.db.query(SurveyTemplate).filter(
            and_(
                SurveyTemplate.organization_id == organization_id,
                SurveyTemplate.status == SurveyStatus.ACTIVE,
                SurveyTemplate.trigger_type == trigger_type,
            )
        ).first()

        if not template:
            logger.info(f"No active template for trigger {trigger_type} in org {organization_id}")
            return None

        # Get loan details
        loan = self.db.execute(
            "SELECT borrower_email, borrower_id, loan_officer_id FROM loans WHERE id = :loan_id",
            {"loan_id": loan_id}
        ).fetchone()

        if not loan or not loan.borrower_email:
            logger.warning(f"No borrower email found for loan {loan_id}")
            return None

        # Check if survey already sent for this loan + template
        existing = self.db.query(SurveyResponse).filter(
            and_(
                SurveyResponse.loan_id == loan_id,
                SurveyResponse.template_id == template.id,
            )
        ).first()

        if existing:
            logger.info(f"Survey already sent for loan {loan_id} with template {template.id}")
            return None

        # Create survey response
        access_token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(days=template.expires_days)

        response = SurveyResponse(
            organization_id=organization_id,
            template_id=template.id,
            borrower_id=loan.borrower_id,
            loan_id=loan_id,
            email=loan.borrower_email,
            access_token=access_token,
            status=ResponseStatus.PENDING,
            sent_at=datetime.now(timezone.utc),
            expires_at=expires_at,
            trigger_event=event_type,
            loan_officer_id=loan.loan_officer_id,
        )

        self.db.add(response)
        self.db.commit()
        self.db.refresh(response)

        # Send email
        survey_service = SurveyService(self.db)
        survey_url = f"/survey/{access_token}"

        await survey_service.send_survey_email(
            email=loan.borrower_email,
            template_name=template.name,
            survey_url=survey_url,
            intro_message=template.intro_message,
        )

        logger.info(f"Survey triggered for loan {loan_id}: response ID {response.id}")
        return response.id


# ============================================================================
# POST-APPOINTMENT SURVEY SERVICE
# ============================================================================


class AppointmentSurveyService:
    """
    Service for post-appointment feedback surveys.

    Uses token-based access so borrowers can respond without authenticating.

    Usage:
        from services.survey_service import AppointmentSurveyService

        service = AppointmentSurveyService(db_session)
        result = service.create_and_send_survey(appointment_id, org_id)
        scores = service.get_aggregate_scores(org_id, lo_user_id=42)
    """

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Lazy model accessors
    # ------------------------------------------------------------------

    @staticmethod
    def _get_survey_model():
        from database.models.appointment_survey import AppointmentSurvey
        return AppointmentSurvey

    @staticmethod
    def _get_appointment_model():
        from smart_scheduler_models import create_smart_scheduler_models
        from db import Base
        models = create_smart_scheduler_models(Base)
        return models["Appointment"]

    # ------------------------------------------------------------------
    # Token generation
    # ------------------------------------------------------------------

    @staticmethod
    def generate_survey_token() -> str:
        """
        Create a cryptographically secure, URL-safe token for survey access.
        48 bytes = 64 characters in base64url, providing ~256 bits of entropy.
        """
        return _secrets.token_urlsafe(48)

    # ------------------------------------------------------------------
    # Create and send survey
    # ------------------------------------------------------------------

    def create_and_send_survey(
        self,
        appointment_id: int,
        organization_id: int,
        *,
        lo_user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Create a survey record for a completed appointment and send
        the invitation email to the borrower.

        Args:
            appointment_id: The completed appointment to survey
            organization_id: Organization context for tenant isolation
            lo_user_id: Override LO user ID (defaults to appointment.assigned_user_id)

        Returns:
            Dict with survey_id, token, sent status
        """
        AppointmentSurvey = self._get_survey_model()
        Appointment = self._get_appointment_model()

        # Load appointment and validate
        appointment = (
            self.db.query(Appointment)
            .filter(
                Appointment.id == appointment_id,
                Appointment.organization_id == organization_id,
            )
            .first()
        )
        if not appointment:
            return {"success": False, "error": "Appointment not found"}

        if not appointment.attendee_email:
            return {"success": False, "error": "No attendee email on this appointment"}

        # Prevent duplicate surveys for same appointment
        existing = (
            self.db.query(AppointmentSurvey)
            .filter(
                AppointmentSurvey.appointment_id == appointment_id,
                AppointmentSurvey.organization_id == organization_id,
            )
            .first()
        )
        if existing:
            return {
                "success": False,
                "error": "Survey already sent for this appointment",
                "survey_id": existing.id,
            }

        # Create survey
        token = self.generate_survey_token()
        now = datetime.now(timezone.utc)

        survey = AppointmentSurvey(
            organization_id=organization_id,
            appointment_id=appointment_id,
            lo_user_id=lo_user_id or appointment.assigned_user_id,
            borrower_email=appointment.attendee_email,
            borrower_name=appointment.attendee_name,
            token=token,
            sent_at=now,
            expires_at=now + timedelta(days=SURVEY_EXPIRY_DAYS),
        )
        self.db.add(survey)
        self.db.flush()

        # Send email
        survey_url = f"{FRONTEND_URL}/survey/{token}"
        email_result = self._send_survey_email(
            to_email=appointment.attendee_email,
            borrower_name=appointment.attendee_name or "there",
            lo_name=self._resolve_lo_name(survey.lo_user_id),
            survey_url=survey_url,
        )

        return {
            "success": True,
            "survey_id": survey.id,
            "token": token,
            "email_sent": email_result.get("success", False),
            "survey_url": survey_url,
            "expires_at": survey.expires_at.isoformat(),
        }

    # ------------------------------------------------------------------
    # Retrieve survey for response
    # ------------------------------------------------------------------

    def get_survey_by_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Look up a survey by its public token. Used by the public response
        endpoint to render the survey form.

        Returns None if not found; dict with state if found.
        """
        AppointmentSurvey = self._get_survey_model()

        survey = (
            self.db.query(AppointmentSurvey)
            .filter(AppointmentSurvey.token == token)
            .first()
        )

        if not survey:
            return None

        now = datetime.now(timezone.utc)

        # Check expiry
        if survey.expires_at and survey.expires_at < now:
            return {"expired": True, "completed": False}

        # Check already completed
        if survey.completed_at is not None:
            return {"expired": False, "completed": True}

        return {
            "expired": False,
            "completed": False,
            "survey_id": survey.id,
            "borrower_name": survey.borrower_name,
            "lo_name": self._resolve_lo_name(survey.lo_user_id),
        }

    # ------------------------------------------------------------------
    # Submit response
    # ------------------------------------------------------------------

    def submit_response(
        self,
        token: str,
        *,
        overall_rating: int,
        communication_rating: int,
        knowledge_rating: int,
        feedback_text: Optional[str] = None,
        would_recommend: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Record a borrower's survey response.

        Validates:
          - Token exists and is valid
          - Survey is not expired
          - Survey has not already been completed
          - Ratings are in range 1-5
        """
        AppointmentSurvey = self._get_survey_model()

        # Use FOR UPDATE to lock the row and prevent concurrent duplicate
        # submissions from racing past the completed_at check.
        survey = (
            self.db.query(AppointmentSurvey)
            .filter(AppointmentSurvey.token == token)
            .with_for_update()
            .first()
        )
        if not survey:
            return {"success": False, "error": "Survey not found"}

        now = datetime.now(timezone.utc)

        if survey.expires_at and survey.expires_at < now:
            return {"success": False, "error": "This survey has expired"}

        if survey.completed_at is not None:
            return {"success": False, "error": "This survey has already been submitted"}

        # Validate ratings
        for name, value in [
            ("overall_rating", overall_rating),
            ("communication_rating", communication_rating),
            ("knowledge_rating", knowledge_rating),
        ]:
            if not isinstance(value, int) or value < 1 or value > 5:
                return {"success": False, "error": f"{name} must be an integer between 1 and 5"}

        # Record response
        survey.overall_rating = overall_rating
        survey.communication_rating = communication_rating
        survey.knowledge_rating = knowledge_rating
        survey.feedback_text = (feedback_text or "").strip()[:5000] or None
        survey.would_recommend = would_recommend
        survey.completed_at = now

        self.db.flush()

        return {
            "success": True,
            "survey_id": survey.id,
            "message": "Thank you for your feedback!",
        }

    # ------------------------------------------------------------------
    # NPS calculation
    # ------------------------------------------------------------------

    def calculate_appointment_nps(
        self,
        organization_id: int,
        *,
        lo_user_id: Optional[int] = None,
        days: int = 90,
    ) -> Dict[str, Any]:
        """
        Calculate Net Promoter Score from the would_recommend field.

        NPS = %Promoters - %Detractors  (range -100 to +100)
        """
        AppointmentSurvey = self._get_survey_model()

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        filters = [
            AppointmentSurvey.organization_id == organization_id,
            AppointmentSurvey.completed_at.isnot(None),
            AppointmentSurvey.would_recommend.isnot(None),
            AppointmentSurvey.completed_at >= cutoff,
        ]
        if lo_user_id:
            filters.append(AppointmentSurvey.lo_user_id == lo_user_id)

        result = self.db.query(
            func.count(AppointmentSurvey.id).label("total"),
            func.count(case(
                (AppointmentSurvey.would_recommend == True, 1),
            )).label("promoters"),
            func.count(case(
                (AppointmentSurvey.would_recommend == False, 1),
            )).label("detractors"),
        ).filter(and_(*filters)).first()

        total = result.total or 0
        promoters = result.promoters or 0
        detractors = result.detractors or 0

        if total > 0:
            nps = round(((promoters - detractors) / total) * 100, 1)
        else:
            nps = None

        return {
            "nps": nps,
            "total_responses": total,
            "promoters": promoters,
            "detractors": detractors,
            "passives": total - promoters - detractors,
            "period_days": days,
        }

    # ------------------------------------------------------------------
    # Aggregate scores
    # ------------------------------------------------------------------

    def get_aggregate_scores(
        self,
        organization_id: int,
        *,
        lo_user_id: Optional[int] = None,
        days: int = 90,
    ) -> Dict[str, Any]:
        """
        Calculate average ratings, response rate, NPS, and recent feedback.
        """
        AppointmentSurvey = self._get_survey_model()

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        filters = [
            AppointmentSurvey.organization_id == organization_id,
            AppointmentSurvey.sent_at >= cutoff,
        ]
        if lo_user_id:
            filters.append(AppointmentSurvey.lo_user_id == lo_user_id)

        # Totals for response rate
        total_sent = (
            self.db.query(func.count(AppointmentSurvey.id))
            .filter(and_(*filters))
            .scalar()
        ) or 0

        total_completed = (
            self.db.query(func.count(AppointmentSurvey.id))
            .filter(and_(*filters, AppointmentSurvey.completed_at.isnot(None)))
            .scalar()
        ) or 0

        response_rate = round((total_completed / total_sent) * 100, 1) if total_sent > 0 else 0

        # Average ratings (only completed surveys)
        completed_filters = filters + [AppointmentSurvey.completed_at.isnot(None)]

        averages = self.db.query(
            func.avg(AppointmentSurvey.overall_rating).label("avg_overall"),
            func.avg(AppointmentSurvey.communication_rating).label("avg_communication"),
            func.avg(AppointmentSurvey.knowledge_rating).label("avg_knowledge"),
        ).filter(and_(*completed_filters)).first()

        avg_overall = round(float(averages.avg_overall), 2) if averages.avg_overall else None
        avg_communication = round(float(averages.avg_communication), 2) if averages.avg_communication else None
        avg_knowledge = round(float(averages.avg_knowledge), 2) if averages.avg_knowledge else None

        # NPS
        nps_data = self.calculate_appointment_nps(
            organization_id, lo_user_id=lo_user_id, days=days
        )

        # Recent feedback (last 10 with text)
        recent = (
            self.db.query(AppointmentSurvey)
            .filter(
                and_(*completed_filters),
                AppointmentSurvey.feedback_text.isnot(None),
                AppointmentSurvey.feedback_text != "",
            )
            .order_by(AppointmentSurvey.completed_at.desc())
            .limit(10)
            .all()
        )

        recent_feedback = [
            {
                "survey_id": s.id,
                "borrower_name": s.borrower_name,
                "overall_rating": s.overall_rating,
                "feedback_text": s.feedback_text,
                "would_recommend": s.would_recommend,
                "completed_at": s.completed_at.isoformat() if s.completed_at else None,
            }
            for s in recent
        ]

        return {
            "period_days": days,
            "total_sent": total_sent,
            "total_completed": total_completed,
            "response_rate": response_rate,
            "averages": {
                "overall": avg_overall,
                "communication": avg_communication,
                "knowledge": avg_knowledge,
            },
            "nps": nps_data,
            "recent_feedback": recent_feedback,
        }

    # ------------------------------------------------------------------
    # Per-LO breakdown
    # ------------------------------------------------------------------

    def get_lo_breakdown(
        self,
        organization_id: int,
        *,
        days: int = 90,
    ) -> List[Dict[str, Any]]:
        """
        Get survey score breakdown per loan officer.
        Returns list sorted by average overall rating descending.
        """
        AppointmentSurvey = self._get_survey_model()

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        rows = (
            self.db.query(
                AppointmentSurvey.lo_user_id,
                func.count(AppointmentSurvey.id).label("total"),
                func.avg(AppointmentSurvey.overall_rating).label("avg_overall"),
                func.avg(AppointmentSurvey.communication_rating).label("avg_communication"),
                func.avg(AppointmentSurvey.knowledge_rating).label("avg_knowledge"),
                func.count(case(
                    (AppointmentSurvey.would_recommend == True, 1),
                )).label("promoters"),
                func.count(case(
                    (AppointmentSurvey.would_recommend == False, 1),
                )).label("detractors"),
            )
            .filter(
                AppointmentSurvey.organization_id == organization_id,
                AppointmentSurvey.completed_at.isnot(None),
                AppointmentSurvey.completed_at >= cutoff,
            )
            .group_by(AppointmentSurvey.lo_user_id)
            .all()
        )

        breakdown = []
        for row in rows:
            total = row.total or 0
            promoters = row.promoters or 0
            detractors = row.detractors or 0
            nps = round(((promoters - detractors) / total) * 100, 1) if total > 0 else None

            lo_name = self._resolve_lo_name(row.lo_user_id)

            breakdown.append({
                "lo_user_id": row.lo_user_id,
                "lo_name": lo_name,
                "total_responses": total,
                "avg_overall": round(float(row.avg_overall), 2) if row.avg_overall else None,
                "avg_communication": round(float(row.avg_communication), 2) if row.avg_communication else None,
                "avg_knowledge": round(float(row.avg_knowledge), 2) if row.avg_knowledge else None,
                "nps": nps,
            })

        # Sort by average overall rating descending
        breakdown.sort(key=lambda x: x["avg_overall"] or 0, reverse=True)
        return breakdown

    # ------------------------------------------------------------------
    # Email sending
    # ------------------------------------------------------------------

    def _send_survey_email(
        self,
        to_email: str,
        borrower_name: str,
        lo_name: str,
        survey_url: str,
    ) -> Dict[str, Any]:
        """Send the post-appointment survey invitation email."""
        if not to_email:
            return {"success": False, "error": "No recipient email"}

        subject = "How was your appointment? We'd love your feedback"

        plain_body = (
            f"Hi {borrower_name},\n\n"
            f"Thank you for meeting with {lo_name}. We'd love to hear about your experience.\n\n"
            f"Please take a moment to share your feedback:\n"
            f"{survey_url}\n\n"
            f"Your response helps us improve our service.\n\n"
            f"Thank you!"
        )

        html_body = (
            f'<div style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', '
            f'Roboto, sans-serif; max-width: 560px; margin: 0 auto; padding: 24px;">'
            f'<h2 style="color: #1e293b; margin-bottom: 16px;">How was your appointment?</h2>'
            f'<p style="color: #475569; font-size: 15px; line-height: 1.6;">'
            f'Hi {borrower_name},</p>'
            f'<p style="color: #475569; font-size: 15px; line-height: 1.6;">'
            f'Thank you for meeting with {lo_name}. We\'d love to hear about your experience.</p>'
            f'<div style="text-align: center; margin: 32px 0;">'
            f'<a href="{survey_url}" style="display: inline-block; padding: 14px 32px; '
            f'background: #3b82f6; color: #fff; text-decoration: none; border-radius: 8px; '
            f'font-weight: 600; font-size: 15px;">Share Your Feedback</a>'
            f'</div>'
            f'<p style="color: #94a3b8; font-size: 13px;">This survey takes less than a minute '
            f'and helps us improve our service.</p>'
            f'</div>'
        )

        try:
            from services.notification_service import notification_service

            result = notification_service.send_email(
                to_email=to_email,
                subject=subject,
                html_content=html_body,
                plain_content=plain_body,
            )
            return result
        except Exception as e:
            logger.exception(f"Failed to send survey email to {to_email}")
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_lo_name(self, user_id: Optional[int]) -> str:
        """Resolve LO name from user_id."""
        if not user_id:
            return "your loan officer"
        try:
            from database.models.core import User
            user = self.db.query(User).filter(User.id == user_id).first()
            if user:
                return f"{user.first_name or ''} {user.last_name or ''}".strip() or "your loan officer"
        except Exception as e:
            logger.debug(f"Could not resolve LO name for user {user_id}: {e}")
        return "your loan officer"
