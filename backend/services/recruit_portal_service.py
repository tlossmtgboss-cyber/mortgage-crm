"""
Candidate Recruit Portal Service

Handles:
- Portal workspace management
- Company updates retrieval
- Chat with AI assistant
- Appointment scheduling
- Production calculator
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import html
import secrets
import re
from sqlalchemy import text

# Use shared engine from database.py to avoid connection pool exhaustion
from database import SessionLocal

import logging
from sqlalchemy.exc import SQLAlchemyError
from models.recruit_portal_models import (
    PortalData,
    CalculatorInput,
    CalculatorResult,
    AvailabilitySlot,
)

logger = logging.getLogger(__name__)


class RecruitPortalService:
    """Service for managing the candidate portal."""

    def __init__(self):
        pass

    # =========================================================================
    # Portal Workspace Management
    # =========================================================================

    def create_portal_workspace(
        self,
        candidate_id: int,
        slug: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a portal workspace for a candidate."""
        with SessionLocal() as conn:
            # Get candidate info for auto-slug generation
            result = conn.execute(
                text("SELECT first_name, last_name FROM mm_candidates WHERE id = :id"),
                {"id": candidate_id}
            )
            candidate = result.fetchone()

            if not candidate:
                raise ValueError(f"Candidate {candidate_id} not found")

            # Generate slug if not provided
            if not slug:
                import secrets
                base_slug = f"{candidate.first_name.lower()}-{candidate.last_name.lower()}"
                base_slug = re.sub(r'[^a-z0-9-]', '', base_slug)
                random_suffix = secrets.token_hex(3)
                slug = f"{base_slug}-{random_suffix}"

                # Check for uniqueness (collision is extremely unlikely with 6 hex chars)
                count = 1
                while True:
                    result = conn.execute(
                        text("SELECT id FROM recruit_portal_workspaces WHERE slug = :slug"),
                        {"slug": slug}
                    )
                    if not result.fetchone():
                        break
                    random_suffix = secrets.token_hex(3)
                    slug = f"{base_slug}-{random_suffix}"
                    count += 1

            # Create workspace
            result = conn.execute(
                text("""
                    INSERT INTO recruit_portal_workspaces (candidate_id, slug, is_active, created_at)
                    VALUES (:candidate_id, :slug, true, NOW())
                    RETURNING id
                """),
                {"candidate_id": candidate_id, "slug": slug}
            )
            workspace_id = result.fetchone().id

            # Generate access token
            token = f"recruit_{secrets.token_hex(32)}"
            conn.execute(
                text("""
                    INSERT INTO recruit_portal_tokens (workspace_id, token, scope, created_at)
                    VALUES (:workspace_id, :token, 'full', NOW())
                """),
                {"workspace_id": workspace_id, "token": token}
            )

            conn.commit()

        return {
            "workspace_id": workspace_id,
            "slug": slug,
            "token": token,
            "portal_url": f"/recruit-portal/{slug}"
        }

    def get_portal_by_slug(self, slug: str, token: Optional[str] = None) -> Optional[PortalData]:
        """Get portal data by slug, optionally validating token."""
        with SessionLocal() as conn:
            # Get portal and candidate info
            result = conn.execute(
                text("""
                    SELECT w.id as workspace_id, w.slug, w.theme_config,
                           c.first_name, c.last_name, c.status,
                           c.referrer_user_id
                    FROM recruit_portal_workspaces w
                    JOIN mm_candidates c ON c.id = w.candidate_id
                    WHERE w.slug = :slug AND w.is_active = true
                """),
                {"slug": slug}
            )
            row = result.fetchone()

        if not row:
            return None

        # Get recruiter info if referrer exists
        recruiter_name = None
        recruiter_photo = None
        recruiter_phone = None
        recruiter_email = None

        if row.referrer_user_id:
            with SessionLocal() as conn:
                # Use only columns that are guaranteed to exist
                recruiter_result = conn.execute(
                    text("""
                        SELECT full_name, email
                        FROM users WHERE id = :user_id
                    """),
                    {"user_id": row.referrer_user_id}
                )
                recruiter = recruiter_result.fetchone()
                if recruiter:
                    recruiter_name = recruiter.full_name
                    recruiter_email = recruiter.email
                    # Photo and phone may not be in users table
                    recruiter_photo = None
                    recruiter_phone = None

        # Get calculator config
        calc_config = self.get_calculator_config()

        return PortalData(
            workspace_id=row.workspace_id,
            candidate_name=f"{row.first_name} {row.last_name}",
            candidate_status=row.status,
            recruiter_name=recruiter_name,
            recruiter_photo=recruiter_photo,
            recruiter_phone=recruiter_phone,
            recruiter_email=recruiter_email,
            next_steps=self._get_next_steps(row.status),
            calculator_config=calc_config,
            theme_config=row.theme_config
        )

    def _get_next_steps(self, status: str) -> str:
        """Get next steps message based on candidate status."""
        messages = {
            "new": "Thank you for your interest! We're reviewing your profile and will be in touch soon.",
            "screening": "We're currently reviewing your qualifications. Please use the calculator below to see your potential with us!",
            "phone_screen": "Great news! We'd like to schedule a phone conversation with you. Use the calendar below to book a time.",
            "interview": "We're excited to meet you! Your interview is coming up. Feel free to chat with our AI assistant if you have any questions.",
            "assessment": "Thank you for completing your interview! We're reviewing your assessment results.",
            "offer": "We're preparing an exciting offer for you! Stay tuned for details.",
            "hired": "Welcome to the team! We're thrilled to have you join us.",
        }
        return messages.get(status, "Thank you for your interest in joining our team!")

    # =========================================================================
    # Company Updates
    # =========================================================================

    def get_company_updates(
        self,
        limit: int = 10,
        category: Optional[str] = None
    ) -> List[Dict]:
        """Get company updates for the portal."""
        params = {"limit": limit}
        category_filter = ""
        if category:
            category_filter = "AND category = :category"
            params["category"] = category

        with SessionLocal() as conn:
            result = conn.execute(
                text(f"""
                    SELECT id, title, content, media_url, category,
                           is_featured, published_at
                    FROM recruit_company_updates
                    WHERE published_at IS NOT NULL
                    {category_filter}
                    ORDER BY is_featured DESC, published_at DESC
                    LIMIT :limit
                """),
                params
            )
            rows = result.fetchall()

        return [
            {
                "id": row.id,
                "title": row.title,
                "content": row.content,
                "media_url": row.media_url,
                "category": row.category,
                "is_featured": row.is_featured,
                "published_at": row.published_at.isoformat() if row.published_at else None
            }
            for row in rows
        ]

    def create_company_update(
        self,
        title: str,
        content: str,
        category: str = "news",
        media_url: Optional[str] = None,
        is_featured: bool = False,
        created_by: int = 1
    ) -> Dict:
        """Create a new company update."""
        with SessionLocal() as conn:
            result = conn.execute(
                text("""
                    INSERT INTO recruit_company_updates
                    (title, content, media_url, category, is_featured, published_at, created_by)
                    VALUES (:title, :content, :media_url, :category, :is_featured, NOW(), :created_by)
                    RETURNING id
                """),
                {
                    "title": title,
                    "content": content,
                    "media_url": media_url,
                    "category": category,
                    "is_featured": is_featured,
                    "created_by": created_by
                }
            )
            update_id = result.fetchone().id
            conn.commit()

        return {"id": update_id, "title": title, "category": category}

    # =========================================================================
    # AI Chat
    # =========================================================================

    def chat_with_assistant(
        self,
        workspace_id: int,
        message: str,
        context: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Handle chat interaction with the AI assistant."""
        # Get workspace and candidate context
        with SessionLocal() as conn:
            result = conn.execute(
                text("""
                    SELECT w.id, c.first_name, c.last_name, c.status,
                           c.current_company, c.current_title
                    FROM recruit_portal_workspaces w
                    JOIN mm_candidates c ON c.id = w.candidate_id
                    WHERE w.id = :workspace_id
                """),
                {"workspace_id": workspace_id}
            )
            candidate = result.fetchone()

        if not candidate:
            return {"response": "I'm sorry, I couldn't find your information. Please contact your recruiter directly."}

        # Build AI prompt
        system_prompt = f"""You are a helpful recruiting assistant for Perennia, a mortgage company.
You're chatting with {candidate.first_name} {candidate.last_name}, a potential recruit who is currently
in the "{candidate.status}" stage of our hiring process.

Their current role: {candidate.current_title or 'Unknown'} at {candidate.current_company or 'Unknown'}

You should:
- Be friendly and professional
- Answer questions about the company, culture, and opportunity
- Help them understand the benefits of joining Perennia
- Never discuss specific compensation details (direct them to speak with their recruiter)
- Encourage them to schedule a call if they have complex questions

Company Facts:
- Perennia offers competitive compensation and technology tools
- We have a supportive team culture focused on growth
- Our technology helps loan officers close more deals faster
- We provide training and mentorship for new team members

Candidate's current status: {candidate.status}
"""

        # Try to use OpenAI for the response
        try:
            import os
            import openai

            client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message}
                ],
                max_tokens=500,
                temperature=0.7
            )

            ai_response = response.choices[0].message.content

        except Exception as e:
            # Fallback to canned responses
            ai_response = self._get_fallback_response(message, candidate.status)

        # Store the conversation
        with SessionLocal() as conn:
            conn.execute(
                text("""
                    INSERT INTO recruit_portal_messages (workspace_id, role, content, created_at)
                    VALUES (:workspace_id, 'user', :message, NOW())
                """),
                {"workspace_id": workspace_id, "message": message}
            )
            conn.execute(
                text("""
                    INSERT INTO recruit_portal_messages (workspace_id, role, content, created_at)
                    VALUES (:workspace_id, 'assistant', :response, NOW())
                """),
                {"workspace_id": workspace_id, "response": ai_response}
            )
            conn.commit()

        return {"response": ai_response}

    def _get_fallback_response(self, message: str, status: str) -> str:
        """Get a fallback response if AI is unavailable."""
        message_lower = message.lower()

        if any(word in message_lower for word in ["compensation", "salary", "pay", "money"]):
            return "Great question! Compensation details are best discussed directly with your recruiter. They can provide personalized information based on your experience and production. Would you like me to help you schedule a call?"

        if any(word in message_lower for word in ["culture", "team", "environment"]):
            return "We pride ourselves on our supportive team culture! At Perennia, we believe in helping each other succeed. We have regular team events, mentorship programs, and a collaborative environment. Is there something specific about our culture you'd like to know?"

        if any(word in message_lower for word in ["technology", "tools", "system"]):
            return "We invest heavily in technology to help our loan officers succeed. Our platform includes CRM tools, automated marketing, AI-powered insights, and streamlined processing. You can see a demo during your interview!"

        if any(word in message_lower for word in ["next", "process", "steps"]):
            status_steps = {
                "screening": "You're currently in our screening phase. Our team is reviewing your qualifications and you should hear from us soon!",
                "phone_screen": "Great news - we'd like to schedule a phone conversation! Use the calendar on this page to book a time that works for you.",
                "interview": "Your interview is coming up! Make sure to review the company info on this page. Feel free to ask me any questions!",
            }
            return status_steps.get(status, "Your application is being processed. Our team will be in touch soon with next steps!")

        return "Thanks for your message! If you have specific questions, feel free to ask about our culture, technology, or the hiring process. For detailed questions, I recommend scheduling a call with your recruiter using the calendar below."

    def get_chat_history(self, workspace_id: int, limit: int = 50) -> List[Dict]:
        """Get chat history for a workspace."""
        with SessionLocal() as conn:
            result = conn.execute(
                text("""
                    SELECT role, content, created_at
                    FROM recruit_portal_messages
                    WHERE workspace_id = :workspace_id
                    ORDER BY created_at ASC
                    LIMIT :limit
                """),
                {"workspace_id": workspace_id, "limit": limit}
            )
            rows = result.fetchall()

        return [
            {
                "role": row.role,
                "content": row.content,
                "created_at": row.created_at.isoformat() if row.created_at else None
            }
            for row in rows
        ]

    # =========================================================================
    # Scheduling
    # =========================================================================

    def get_availability(
        self,
        workspace_id: int,
        date: str
    ) -> List[AvailabilitySlot]:
        """Get available time slots for scheduling."""
        # For now, return simulated availability
        # In production, this would integrate with Calendly or a scheduling system

        target_date = datetime.strptime(date, "%Y-%m-%d")
        slots = []

        # Generate slots from 9 AM to 5 PM
        for hour in range(9, 17):
            start = target_date.replace(hour=hour, minute=0)
            end = start + timedelta(hours=1)

            # Simulate some slots being unavailable
            is_available = (hour % 3 != 0)  # Every 3rd slot is "booked"

            slots.append(AvailabilitySlot(
                start_time=start.isoformat(),
                end_time=end.isoformat(),
                is_available=is_available
            ))

        return slots

    def schedule_appointment(
        self,
        workspace_id: int,
        scheduled_at: str,
        appointment_type: str = "phone_call",
        notes: Optional[str] = None
    ) -> Dict:
        """Schedule an appointment from the portal."""
        with SessionLocal() as conn:
            # Insert the appointment
            result = conn.execute(
                text("""
                    INSERT INTO recruit_portal_appointments
                    (workspace_id, appointment_type, scheduled_at, notes, status, created_at)
                    VALUES (:workspace_id, :type, :scheduled_at, :notes, 'scheduled', NOW())
                    RETURNING id
                """),
                {
                    "workspace_id": workspace_id,
                    "type": appointment_type,
                    "scheduled_at": scheduled_at,
                    "notes": notes
                }
            )
            appointment_id = result.fetchone().id
            conn.commit()

            # Get candidate and recruiter info for email
            portal_info = conn.execute(
                text("""
                    SELECT
                        w.candidate_id,
                        c.first_name as candidate_first_name,
                        c.last_name as candidate_last_name,
                        c.email as candidate_email,
                        u.full_name as recruiter_name,
                        u.email as recruiter_email
                    FROM recruit_portal_workspaces w
                    LEFT JOIN mm_candidates c ON c.id = w.candidate_id
                    LEFT JOIN users u ON u.id = c.referrer_user_id
                    WHERE w.id = :workspace_id
                """),
                {"workspace_id": workspace_id}
            ).fetchone()

        # Send confirmation email
        email_sent = False
        if portal_info and portal_info.candidate_email:
            try:
                from services.notification_service import NotificationService
                notification_service = NotificationService()

                # Format appointment time nicely
                appt_time = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
                formatted_time = appt_time.strftime("%A, %B %d, %Y at %I:%M %p")

                # Map appointment type to friendly name
                type_names = {
                    "discovery_call": "Discovery Call",
                    "deep_dive": "Deep Dive Session",
                    "tech_demo": "Technology Demo",
                    "phone_call": "Phone Call"
                }
                friendly_type = type_names.get(appointment_type, appointment_type.replace("_", " ").title())

                # Build email content
                html_content = f"""
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                    <h2 style="color: #2563eb;">Your Appointment is Confirmed!</h2>
                    <p>Hi {portal_info.candidate_first_name or 'there'},</p>
                    <p>Your <strong>{friendly_type}</strong> has been scheduled.</p>
                    <div style="background: #f3f4f6; padding: 20px; border-radius: 8px; margin: 20px 0;">
                        <p style="margin: 0 0 10px 0;"><strong>Date & Time:</strong> {formatted_time}</p>
                        <p style="margin: 0 0 10px 0;"><strong>Type:</strong> {friendly_type}</p>
                        <p style="margin: 0;"><strong>With:</strong> {portal_info.recruiter_name or 'Your Recruiter'}</p>
                    </div>
                    {f'<p><strong>Notes:</strong> {html.escape(notes)}</p>' if notes else ''}
                    <p>We're looking forward to speaking with you!</p>
                    <p>Best regards,<br>{portal_info.recruiter_name or 'The Recruiting Team'}</p>
                </div>
                """

                notification_service.send_email(
                    to_email=portal_info.candidate_email,
                    subject=f"Appointment Confirmed: {friendly_type} on {appt_time.strftime('%B %d')}",
                    html_content=html_content
                )
                email_sent = True
            except Exception as e:
                logger.error(f"Failed to send confirmation email: {e}")

        return {
            "appointment_id": appointment_id,
            "scheduled_at": scheduled_at,
            "status": "scheduled",
            "email_sent": email_sent,
            "message": "Your appointment has been scheduled! You'll receive a confirmation email shortly."
        }

    # =========================================================================
    # Production Calculator
    # =========================================================================

    def get_calculator_config(self, organization_id: int = 1) -> Dict:
        """Get calculator configuration."""
        with SessionLocal() as conn:
            result = conn.execute(
                text("""
                    SELECT lead_conversion_lift, avg_deal_size_lift,
                           closing_speed_factor, tech_efficiency_gain,
                           marketing_lead_boost, comp_percentage
                    FROM recruit_calculator_config
                    WHERE organization_id = :org_id OR organization_id IS NULL
                    ORDER BY organization_id DESC NULLS LAST
                    LIMIT 1
                """),
                {"org_id": organization_id}
            )
            row = result.fetchone()

        if not row:
            return {
                "lead_conversion_lift": 1.25,
                "avg_deal_size_lift": 1.15,
                "tech_efficiency_gain": 1.20,
                "marketing_lead_boost": 1.30,
                "comp_percentage": 0.0125
            }

        return {
            "lead_conversion_lift": float(row.lead_conversion_lift),
            "avg_deal_size_lift": float(row.avg_deal_size_lift),
            "tech_efficiency_gain": float(row.tech_efficiency_gain),
            "marketing_lead_boost": float(row.marketing_lead_boost),
            "comp_percentage": float(row.comp_percentage)
        }

    def calculate_production_impact(self, input_data: CalculatorInput) -> CalculatorResult:
        """Calculate projected production impact."""
        config = self.get_calculator_config()

        current_volume = input_data.current_volume
        current_units = input_data.current_units

        # Calculate projections
        volume_multiplier = (
            config["lead_conversion_lift"] *
            config["avg_deal_size_lift"] *
            config["marketing_lead_boost"]
        )
        projected_volume = current_volume * volume_multiplier

        units_multiplier = (
            config["lead_conversion_lift"] *
            config["tech_efficiency_gain"] *
            config["marketing_lead_boost"]
        )
        projected_units = int(current_units * units_multiplier)

        # Calculate earnings
        current_earnings = current_volume * config["comp_percentage"]
        potential_earnings = projected_volume * config["comp_percentage"]

        return CalculatorResult(
            current_volume=current_volume,
            current_units=current_units,
            projected_volume=round(projected_volume, 2),
            projected_units=projected_units,
            volume_increase=round(projected_volume - current_volume, 2),
            volume_increase_pct=round(((projected_volume / current_volume) - 1) * 100, 1) if current_volume > 0 else 0,
            unit_increase=projected_units - current_units,
            unit_increase_pct=round(((projected_units / current_units) - 1) * 100, 1) if current_units > 0 else 0,
            potential_earnings=round(potential_earnings, 2),
            current_earnings=round(current_earnings, 2),
            earnings_increase=round(potential_earnings - current_earnings, 2),
            earnings_increase_pct=round(((potential_earnings / current_earnings) - 1) * 100, 1) if current_earnings > 0 else 0
        )


# Singleton instance
recruit_portal_service = RecruitPortalService()
