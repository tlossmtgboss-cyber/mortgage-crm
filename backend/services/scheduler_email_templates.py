"""
Scheduler Email Templates
Extracted from scheduler_email_service.py

Provides:
- Shared HTML email boilerplate (header, body, footer)
- Header color constants for different email types
- Video call button HTML
- Calendar invite notice HTML
- Pre-appointment preparation checklist defaults
"""

import logging
import os

logger = logging.getLogger(__name__)

# CAN-SPAM: physical address required in all commercial email footers
try:
    from routes.scheduler.constants import CAN_SPAM_PHYSICAL_ADDRESS
except ImportError:
    CAN_SPAM_PHYSICAL_ADDRESS = os.environ.get(
        "CAN_SPAM_ADDRESS",
        "Perennia AI, 123 Main Street, Suite 100, Austin, TX 78701"
    )


# ============================================================================
# Header color constants
# ============================================================================

HEADER_COLOR_TEAL = "linear-gradient(135deg, #217F8D 0%, #1a6670 100%)"
HEADER_COLOR_AMBER = "linear-gradient(135deg, #f59e0b 0%, #d97706 100%)"
HEADER_COLOR_RED = "linear-gradient(135deg, #dc2626 0%, #991b1b 100%)"
HEADER_COLOR_BLUE = "linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%)"
HEADER_COLOR_GREEN = "linear-gradient(135deg, #059669 0%, #047857 100%)"
HEADER_COLOR_PURPLE = "linear-gradient(135deg, #7c3aed 0%, #6d28d9 100%)"


# ============================================================================
# Shared base email template
# ============================================================================

def build_scheduler_email_html(
    header_color: str,
    heading: str,
    body_content: str,
    footer_text: str = None,
) -> str:
    """Build a complete HTML email from shared boilerplate.

    Args:
        header_color: CSS gradient for the header bar,
            e.g. ``"linear-gradient(135deg, #217F8D 0%, #1a6670 100%)"``
        heading: Text shown inside the colored header bar.
        body_content: Pre-escaped HTML that goes inside the white content area.
        footer_text: Optional override for the small footer line.
            Defaults to ``"Sent from Perennia AI"``.
    """
    footer = footer_text or "Sent from Perennia AI"
    return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background-color: #f6f9fc;">
            <div style="max-width: 600px; margin: 0 auto; padding: 40px 20px;">
                <div style="background: white; border-radius: 16px; box-shadow: 0 4px 24px rgba(0,0,0,0.08); overflow: hidden;">
                    <div style="background: {header_color}; padding: 30px; text-align: center;">
                        <h1 style="color: white; margin: 0; font-size: 24px;">{heading}</h1>
                    </div>

                    <div style="padding: 30px;">
                        {body_content}
                    </div>
                </div>

                <p style="text-align: center; color: #9ca3af; font-size: 12px; margin-top: 20px;">
                    {footer}
                </p>
                <p style="text-align: center; color: #9ca3af; font-size: 11px; margin-top: 4px;">
                    {CAN_SPAM_PHYSICAL_ADDRESS}
                </p>
            </div>
        </body>
        </html>
        """


def video_button_html(safe_video_link: str, show_copy_link: bool = False) -> str:
    """Return HTML for the video-call button (and optional copy-link line)."""
    if not safe_video_link:
        return ""
    copy_line = ""
    if show_copy_link:
        copy_line = f"""
                    <p style="text-align: center; font-size: 12px; color: #666; margin-top: 8px;">
                        Or copy this link: <a href="{safe_video_link}" style="color: #217F8D;">{safe_video_link}</a>
                    </p>"""
    return f"""
                    <div style="text-align: center; margin: 25px 0;">
                        <a href="{safe_video_link}" style="display: inline-block; background: linear-gradient(135deg, #217F8D 0%, #1a6670 100%); color: white; padding: 14px 32px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 16px;">
                            Join Video Call
                        </a>
                    </div>{copy_line}
            """


def calendar_notice_html(text: str = None) -> str:
    """Return the blue calendar-invite notice box."""
    msg = text or "A calendar invite is attached to this email. Click on the attachment to add this appointment to your calendar."
    return f"""
                        <div style="background: #e0f2fe; border-radius: 8px; padding: 16px; margin: 20px 0; text-align: center;">
                            <p style="margin: 0; color: #0369a1; font-size: 14px;">
                                {msg}
                            </p>
                        </div>
        """


# ============================================================================
# Pre-appointment preparation defaults
# ============================================================================

def default_prep_items(meeting_type_key: str = None) -> list:
    """Return default preparation checklist items based on meeting type."""
    defaults = {
        "discovery_call": [
            "Think about your home buying timeline and budget",
            "Have a rough idea of your desired location and property type",
            "Know your current employment and income situation",
            "Prepare any questions you have about the mortgage process",
        ],
        "pre_approval_review": [
            "Have your most recent pay stubs available (last 30 days)",
            "Know your approximate credit score",
            "Have your bank/asset statements handy",
            "Prepare your target home price range",
        ],
        "application_walkthrough": [
            "Gather your last 2 years of W-2s or tax returns",
            "Have your most recent pay stubs (last 30 days)",
            "Prepare 2 months of bank statements for all accounts",
            "Have your driver's license or government ID ready",
            "Know your current debts and monthly payments",
        ],
        "document_review": [
            "Have any documents you were asked to provide",
            "Prepare questions about items on your to-do list",
            "Have access to your email to share documents if needed",
        ],
        "rate_lock_discussion": [
            "Know your expected closing date",
            "Review your current rate quote",
            "Consider how long you plan to stay in the home",
            "Think about your preference: lowest rate vs. lowest payment",
        ],
        "closing_prep": [
            "Review your Closing Disclosure (CD) document",
            "Confirm your closing date and time",
            "Have your cashier's check or wire transfer ready",
            "Bring a valid photo ID to closing",
            "Prepare any questions about closing costs",
        ],
    }
    if meeting_type_key and meeting_type_key in defaults:
        return defaults[meeting_type_key]
    # Generic fallback
    return [
        "Review any documents or information previously discussed",
        "Prepare questions you would like to ask",
        "Ensure you are in a quiet place with good connectivity",
    ]
