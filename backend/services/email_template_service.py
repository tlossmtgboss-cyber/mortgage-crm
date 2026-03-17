"""
Email Template Service
Renders responsive HTML email templates with org branding and appointment data.

Provides a central rendering engine for all appointment notification emails,
replacing the inline HTML that was previously constructed in scheduler_email_service.py.

Templates use a simple {{variable}} substitution syntax (no Jinja dependency).
"""

import html
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Template directory
# ---------------------------------------------------------------------------
TEMPLATES_DIR = Path(__file__).parent.parent / "templates" / "email"

# ---------------------------------------------------------------------------
# Default branding
# ---------------------------------------------------------------------------
DEFAULT_BRANDING = {
    "primary_color": "#217F8D",
    "org_name": "Perennia AI",
    "org_address": "",
    "footer_text": "Sent from Perennia AI",
}

# Header gradients keyed by semantic purpose
HEADER_GRADIENTS = {
    "confirmation": "linear-gradient(135deg, #217F8D 0%, #1a6670 100%)",
    "reminder": "linear-gradient(135deg, #f59e0b 0%, #d97706 100%)",
    "cancelled": "linear-gradient(135deg, #dc2626 0%, #991b1b 100%)",
    "rescheduled": "linear-gradient(135deg, #f59e0b 0%, #d97706 100%)",
    "no_show": "linear-gradient(135deg, #f59e0b 0%, #d97706 100%)",
    "ai_booking": "linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%)",
    "prep": "linear-gradient(135deg, #059669 0%, #047857 100%)",
}


class EmailTemplateService:
    """Renders email templates with org branding and appointment data.

    All user-supplied values are HTML-escaped before substitution to prevent
    XSS. Template files are cached after first read.
    """

    _template_cache: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # Core rendering
    # ------------------------------------------------------------------

    @classmethod
    def _load_template(cls, template_name: str) -> str:
        """Load a template file, using an in-memory cache."""
        if template_name in cls._template_cache:
            return cls._template_cache[template_name]

        template_path = TEMPLATES_DIR / f"{template_name}.html"
        if not template_path.exists():
            raise FileNotFoundError(f"Email template not found: {template_path}")

        content = template_path.read_text(encoding="utf-8")
        cls._template_cache[template_name] = content
        return content

    @classmethod
    def clear_cache(cls) -> None:
        """Clear the template cache (useful in tests or after template edits)."""
        cls._template_cache.clear()

    @classmethod
    def render(cls, template_name: str, context: Dict[str, Any]) -> str:
        """Render a template with context variables.

        Variables in templates use ``{{key}}`` syntax.  Values are converted
        to strings via ``str()``.  Empty / None values are replaced with an
        empty string so no stray ``{{...}}`` tokens remain.
        """
        template = cls._load_template(template_name)

        for key, value in context.items():
            placeholder = "{{" + key + "}}"
            template = template.replace(placeholder, str(value) if value is not None else "")

        # Strip any remaining unreplaced placeholders
        template = re.sub(r"\{\{[a-zA-Z0-9_]+\}\}", "", template)

        return template

    @classmethod
    def render_with_base(
        cls,
        body_template: str,
        context: Dict[str, Any],
        base_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Render a body template then wrap it inside the base layout.

        ``base_context`` is merged into the outer context that fills the
        base template (header gradient, heading, footer, etc.).
        """
        body_html = cls.render(body_template, context)

        full_context = {**DEFAULT_BRANDING}
        if base_context:
            full_context.update(base_context)
        full_context["body_content"] = body_html

        return cls.render("base", full_context)

    # ------------------------------------------------------------------
    # Shared HTML fragment builders
    # ------------------------------------------------------------------

    @staticmethod
    def build_video_button(video_link: str, show_copy_link: bool = False) -> str:
        """Build the video-call CTA button HTML."""
        if not video_link:
            return ""
        safe_link = html.escape(video_link)
        copy_line = ""
        if show_copy_link:
            copy_line = (
                f'<p style="text-align: center; font-size: 12px; color: #666; margin-top: 8px;">'
                f'Or copy this link: <a href="{safe_link}" style="color: #217F8D;">{safe_link}</a></p>'
            )
        return (
            f'<div style="text-align: center; margin: 24px 0;">'
            f'<a href="{safe_link}" class="btn-primary" style="display: inline-block; '
            f"background: linear-gradient(135deg, #217F8D 0%, #1a6670 100%); color: white; "
            f'padding: 14px 32px; text-decoration: none; border-radius: 8px; font-weight: 700; '
            f'font-size: 16px;">Join Video Call</a>'
            f"</div>{copy_line}"
        )

    @staticmethod
    def build_calendar_notice(text: Optional[str] = None) -> str:
        """Build the blue calendar-invite notice box."""
        msg = text or (
            "A calendar invite is attached to this email. "
            "Click on the attachment to add this appointment to your calendar."
        )
        return (
            '<div style="background: #e0f2fe; border-radius: 8px; padding: 16px; '
            'margin: 20px 0; text-align: center;">'
            f'<p style="margin: 0; color: #0369a1; font-size: 14px;">{msg}</p>'
            "</div>"
        )

    @staticmethod
    def build_team_member_row(team_member_name: str) -> str:
        """Build the 'Meeting with' row for the details card."""
        if not team_member_name:
            return ""
        safe_name = html.escape(team_member_name)
        return (
            '<tr><td>'
            '<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%"><tr>'
            '<td style="width: 32px; vertical-align: top; padding-top: 2px;">'
            '<img src="https://app.perenniaai.com/email-icons/user.png" alt="" width="20" height="20" '
            'style="display: block;" onerror="this.style.display=\'none\'"></td>'
            "<td>"
            '<p class="detail-label" style="margin: 0 0 2px; font-size: 12px; color: #6b7280; '
            'text-transform: uppercase; letter-spacing: 0.5px; font-weight: 600;">Meeting With</p>'
            f'<p class="detail-value" style="margin: 0; font-size: 15px; color: #111827;">{safe_name}</p>'
            "</td></tr></table>"
            "</td></tr>"
        )

    @staticmethod
    def build_reschedule_button(
        reschedule_url: str,
        label: str = "Reschedule Appointment",
        style: str = "secondary",
    ) -> str:
        """Build a reschedule CTA button."""
        if not reschedule_url:
            return ""
        safe_url = html.escape(reschedule_url)
        if style == "primary":
            btn_style = (
                "background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%); "
                "color: white; border: none;"
            )
        else:
            btn_style = (
                "background: #f3f4f6; color: #374151; border: 1px solid #d1d5db;"
            )
        return (
            f'<div style="text-align: center; margin: 20px 0;">'
            f'<a href="{safe_url}" class="btn-secondary" style="display: inline-block; '
            f"padding: 12px 28px; text-decoration: none; border-radius: 8px; "
            f'font-weight: 600; font-size: 15px; {btn_style}">'
            f"{label}</a></div>"
        )

    @staticmethod
    def build_lo_contact_card(
        lo_name: Optional[str] = None,
        lo_email: Optional[str] = None,
        lo_phone: Optional[str] = None,
    ) -> str:
        """Build the loan officer / team member contact info card."""
        if not lo_name:
            return ""
        safe_name = html.escape(lo_name)
        email_line = ""
        if lo_email:
            safe_email = html.escape(lo_email)
            email_line = (
                f'<a href="mailto:{safe_email}" style="color: #217F8D; '
                f'text-decoration: none;">{safe_email}</a><br>'
            )
        phone_line = ""
        if lo_phone:
            safe_phone = html.escape(lo_phone)
            phone_line = (
                f'<a href="tel:{safe_phone}" style="color: #217F8D; '
                f'text-decoration: none;">{safe_phone}</a>'
            )
        return (
            '<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
            'width="100%" style="margin: 24px 0;">'
            "<tr><td>"
            '<div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; '
            'padding: 20px;">'
            '<p style="margin: 0 0 8px; font-size: 12px; color: #6b7280; text-transform: uppercase; '
            'letter-spacing: 0.5px; font-weight: 600;">Your Contact</p>'
            f'<p style="margin: 0; font-size: 15px; color: #1e293b; line-height: 1.8;">'
            f"<strong>{safe_name}</strong><br>"
            f"{email_line}{phone_line}</p>"
            "</div>"
            "</td></tr></table>"
        )

    @staticmethod
    def build_prep_checklist(items: List[str]) -> str:
        """Build a preparation checklist card."""
        if not items:
            return ""
        items_html = "".join(
            f'<tr><td style="width: 24px; vertical-align: top; padding: 4px 0; color: #059669; '
            f'font-size: 14px;">&#10003;</td>'
            f'<td style="padding: 4px 0; font-size: 14px; color: #374151; line-height: 1.5;">'
            f"{html.escape(item)}</td></tr>"
            for item in items
        )
        return (
            '<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
            'width="100%" style="background: #ecfdf5; border: 1px solid #a7f3d0; '
            'border-radius: 12px; margin: 0 0 24px;">'
            '<tr><td style="padding: 24px;">'
            '<p style="margin: 0 0 16px; color: #065f46; font-weight: 700; font-size: 14px; '
            'text-transform: uppercase; letter-spacing: 0.5px;">Preparation Checklist</p>'
            '<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">'
            f"{items_html}"
            "</table></td></tr></table>"
        )

    @staticmethod
    def build_reason_row(reason: Optional[str]) -> str:
        """Build a cancellation-reason row."""
        if not reason:
            return ""
        safe_reason = html.escape(reason)
        return (
            "<tr><td>"
            '<p class="detail-label" style="margin: 0 0 2px; font-size: 12px; color: #6b7280; '
            'text-transform: uppercase; letter-spacing: 0.5px; font-weight: 600;">Reason</p>'
            f'<p class="detail-value" style="margin: 0; font-size: 15px; color: #6b7280;">'
            f"{safe_reason}</p>"
            "</td></tr>"
        )

    # ------------------------------------------------------------------
    # High-level render methods for each email type
    # ------------------------------------------------------------------

    @classmethod
    def render_confirmation(
        cls,
        attendee_name: str,
        appointment_title: str,
        appointment_date: str,
        appointment_time: str,
        duration: str,
        meeting_mode: str = "Phone Call",
        team_member_name: Optional[str] = None,
        video_link: Optional[str] = None,
        reschedule_url: Optional[str] = None,
        lo_name: Optional[str] = None,
        lo_email: Optional[str] = None,
        lo_phone: Optional[str] = None,
        org_branding: Optional[Dict[str, str]] = None,
    ) -> str:
        """Render appointment confirmation email."""
        branding = {**DEFAULT_BRANDING, **(org_branding or {})}

        context = {
            "attendee_name": html.escape(attendee_name or ""),
            "appointment_title": html.escape(appointment_title or ""),
            "appointment_date": html.escape(appointment_date or ""),
            "appointment_time": html.escape(appointment_time or ""),
            "duration": html.escape(str(duration) if duration else ""),
            "meeting_mode": html.escape(meeting_mode or "Phone Call"),
            "team_member_section": cls.build_team_member_row(team_member_name),
            "team_member_bottom_pad": "0" if not team_member_name else "12px",
            "video_button": cls.build_video_button(video_link, show_copy_link=True),
            "calendar_notice": cls.build_calendar_notice(),
            "reschedule_section": cls.build_reschedule_button(reschedule_url),
            "lo_contact_section": cls.build_lo_contact_card(
                lo_name or team_member_name,
                lo_email,
                lo_phone,
            ),
        }

        base_context = {
            "header_gradient": HEADER_GRADIENTS["confirmation"],
            "heading": "Appointment Confirmed!",
            "header_icon": "",
            "header_subtitle": "",
            "preheader_text": (
                f"Your appointment on {appointment_date} at {appointment_time} is confirmed."
            ),
            "email_title": f"Appointment Confirmed - {appointment_title}",
            **branding,
        }

        return cls.render_with_base("appointment_confirmation", context, base_context)

    @classmethod
    def render_reminder(
        cls,
        attendee_name: str,
        appointment_title: str,
        appointment_date: str,
        appointment_time: str,
        duration: str,
        hours_before: int = 24,
        meeting_mode: str = "Phone Call",
        team_member_name: Optional[str] = None,
        video_link: Optional[str] = None,
        reschedule_url: Optional[str] = None,
        prep_items: Optional[List[str]] = None,
        org_branding: Optional[Dict[str, str]] = None,
        header_style: Optional[str] = None,
        heading_override: Optional[str] = None,
    ) -> str:
        """Render appointment reminder email.

        Args:
            header_style: Key into HEADER_GRADIENTS (e.g., "prep", "reminder").
                Defaults to "reminder".
            heading_override: Custom heading text. Overrides the auto heading
                derived from ``hours_before``.
        """
        branding = {**DEFAULT_BRANDING, **(org_branding or {})}

        if hours_before >= 24:
            heading = "Your Appointment is Tomorrow!"
            reminder_message = "This is a friendly reminder about your upcoming appointment."
        else:
            heading = "Your Appointment Starts Soon!"
            reminder_message = "Your appointment is coming up shortly. Please be ready."

        if heading_override:
            heading = heading_override

        context = {
            "attendee_name": html.escape(attendee_name or ""),
            "reminder_message": reminder_message,
            "appointment_date": html.escape(appointment_date or ""),
            "appointment_time": html.escape(appointment_time or ""),
            "duration": html.escape(str(duration) if duration else ""),
            "meeting_mode": html.escape(meeting_mode or "Phone Call"),
            "team_member_section": cls.build_team_member_row(team_member_name),
            "team_member_bottom_pad": "0" if not team_member_name else "12px",
            "video_button": cls.build_video_button(video_link),
            "prep_checklist": cls.build_prep_checklist(prep_items or []),
            "reschedule_section": cls.build_reschedule_button(reschedule_url),
        }

        gradient_key = header_style or "reminder"
        base_context = {
            "header_gradient": HEADER_GRADIENTS.get(gradient_key, HEADER_GRADIENTS["reminder"]),
            "heading": heading,
            "header_icon": "",
            "header_subtitle": "",
            "preheader_text": (
                f"Reminder: Your appointment on {appointment_date} at {appointment_time}."
            ),
            "email_title": f"Appointment Reminder - {appointment_title}",
            **branding,
        }

        return cls.render_with_base("appointment_reminder", context, base_context)

    @classmethod
    def render_cancelled(
        cls,
        attendee_name: str,
        appointment_title: str,
        appointment_date: str,
        appointment_time: str,
        team_member_name: Optional[str] = None,
        cancellation_reason: Optional[str] = None,
        reschedule_url: Optional[str] = None,
        lo_name: Optional[str] = None,
        lo_email: Optional[str] = None,
        lo_phone: Optional[str] = None,
        org_branding: Optional[Dict[str, str]] = None,
    ) -> str:
        """Render appointment cancellation email."""
        branding = {**DEFAULT_BRANDING, **(org_branding or {})}

        team_with = f" with {html.escape(team_member_name)}" if team_member_name else ""

        context = {
            "attendee_name": html.escape(attendee_name or ""),
            "appointment_title": html.escape(appointment_title or ""),
            "appointment_date": html.escape(appointment_date or ""),
            "appointment_time": html.escape(appointment_time or ""),
            "team_member_with": team_with,
            "reason_section": cls.build_reason_row(cancellation_reason),
            "reason_bottom_pad": "0" if not cancellation_reason else "10px",
            "reschedule_button": cls.build_reschedule_button(
                reschedule_url, label="Reschedule Now", style="primary"
            ),
            "lo_contact_section": cls.build_lo_contact_card(
                lo_name or team_member_name,
                lo_email,
                lo_phone,
            ),
        }

        base_context = {
            "header_gradient": HEADER_GRADIENTS["cancelled"],
            "heading": "Appointment Cancelled",
            "header_icon": "",
            "header_subtitle": "",
            "preheader_text": (
                f"Your appointment on {appointment_date} has been cancelled."
            ),
            "email_title": f"Appointment Cancelled - {appointment_title}",
            **branding,
        }

        return cls.render_with_base("appointment_cancelled", context, base_context)

    @classmethod
    def render_rescheduled(
        cls,
        attendee_name: str,
        appointment_title: str,
        appointment_date: str,
        appointment_time: str,
        duration: str,
        meeting_mode: str = "Phone Call",
        team_member_name: Optional[str] = None,
        old_date: Optional[str] = None,
        old_time: Optional[str] = None,
        video_link: Optional[str] = None,
        reschedule_url: Optional[str] = None,
        org_branding: Optional[Dict[str, str]] = None,
    ) -> str:
        """Render appointment rescheduled email."""
        branding = {**DEFAULT_BRANDING, **(org_branding or {})}

        context = {
            "attendee_name": html.escape(attendee_name or ""),
            "appointment_title": html.escape(appointment_title or ""),
            "appointment_date": html.escape(appointment_date or ""),
            "appointment_time": html.escape(appointment_time or ""),
            "duration": html.escape(str(duration) if duration else ""),
            "meeting_mode": html.escape(meeting_mode or "Phone Call"),
            "old_date": html.escape(old_date or ""),
            "old_time": html.escape(old_time or ""),
            "team_member_section": cls.build_team_member_row(team_member_name),
            "team_member_bottom_pad": "0" if not team_member_name else "10px",
            "video_button": cls.build_video_button(video_link),
            "calendar_notice": cls.build_calendar_notice(
                "An updated calendar invite is attached. "
                "Please add it to replace the previous appointment."
            ),
            "reschedule_section": cls.build_reschedule_button(reschedule_url),
        }

        base_context = {
            "header_gradient": HEADER_GRADIENTS["rescheduled"],
            "heading": "Appointment Updated!",
            "header_icon": "",
            "header_subtitle": "",
            "preheader_text": (
                f"Your appointment has been rescheduled to "
                f"{appointment_date} at {appointment_time}."
            ),
            "email_title": f"Appointment Updated - {appointment_title}",
            **branding,
        }

        return cls.render_with_base("appointment_rescheduled", context, base_context)

    @classmethod
    def render_no_show(
        cls,
        attendee_name: str,
        appointment_title: str,
        appointment_date: str,
        appointment_time: str,
        team_member_name: Optional[str] = None,
        reschedule_url: Optional[str] = None,
        lo_name: Optional[str] = None,
        lo_email: Optional[str] = None,
        lo_phone: Optional[str] = None,
        org_branding: Optional[Dict[str, str]] = None,
    ) -> str:
        """Render no-show follow-up email."""
        branding = {**DEFAULT_BRANDING, **(org_branding or {})}

        team_with = f" with {html.escape(team_member_name)}" if team_member_name else ""

        context = {
            "attendee_name": html.escape(attendee_name or ""),
            "appointment_title": html.escape(appointment_title or ""),
            "appointment_date": html.escape(appointment_date or ""),
            "appointment_time": html.escape(appointment_time or ""),
            "team_member_with": team_with,
            "reschedule_button": cls.build_reschedule_button(
                reschedule_url, label="Reschedule Now", style="primary"
            ),
            "lo_contact_section": cls.build_lo_contact_card(
                lo_name or team_member_name,
                lo_email,
                lo_phone,
            ),
        }

        base_context = {
            "header_gradient": HEADER_GRADIENTS["no_show"],
            "heading": "We Missed You!",
            "header_icon": "",
            "header_subtitle": "",
            "preheader_text": (
                f"We missed you at your appointment on {appointment_date}. "
                "Let's reschedule!"
            ),
            "email_title": f"We Missed You - {appointment_title}",
            **branding,
        }

        return cls.render_with_base("no_show_followup", context, base_context)
