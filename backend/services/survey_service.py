"""
Survey Service
Business logic for survey delivery, analytics, and sentiment analysis.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, and_

logger = logging.getLogger(__name__)


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
        now = datetime.utcnow()

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

        target_date = date or datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

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
        expires_at = datetime.utcnow() + timedelta(days=template.expires_days)

        response = SurveyResponse(
            organization_id=organization_id,
            template_id=template.id,
            borrower_id=loan.borrower_id,
            loan_id=loan_id,
            email=loan.borrower_email,
            access_token=access_token,
            status=ResponseStatus.PENDING,
            sent_at=datetime.utcnow(),
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
