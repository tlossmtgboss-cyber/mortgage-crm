"""
Listing Agent Weekly Update Email Service
Sends weekly status updates to listing agents with PII-safe transaction snapshots.
"""

import os
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, date

from email_service import email_service

logger = logging.getLogger(__name__)


class ListingUpdateEmailService:
    """Service for sending weekly updates to listing agents"""

    def __init__(self):
        self.from_email = os.getenv('LISTING_UPDATE_FROM_EMAIL', 'updates@perenniaai.com')
        self.from_name = os.getenv('LISTING_UPDATE_FROM_NAME', 'Perennia AI Transaction Updates')

    def send_weekly_update(
        self,
        to_email: str,
        party_name: str,
        transactions: List[Dict[str, Any]],
        portal_url: str,
        unsubscribe_url: str
    ) -> bool:
        """Send weekly update email to a listing agent"""
        try:
            subject = f"Weekly Transaction Update - {len(transactions)} Active Transaction{'s' if len(transactions) != 1 else ''}"
            html_body = self._format_weekly_update_html(
                party_name, transactions, portal_url, unsubscribe_url
            )
            plain_text = self._format_weekly_update_plain(
                party_name, transactions, portal_url, unsubscribe_url
            )

            success = email_service.send_html_email(
                to_email=to_email,
                subject=subject,
                html_body=html_body,
                plain_text_body=plain_text,
                from_email=self.from_email
            )

            if success:
                logger.info(f"Weekly update sent to {to_email} for {len(transactions)} transactions")
            else:
                logger.error(f"Failed to send weekly update to {to_email}")

            return success

        except Exception as e:
            logger.error(f"Error sending weekly update: {e}")
            return False

    def _format_weekly_update_html(
        self,
        party_name: str,
        transactions: List[Dict[str, Any]],
        portal_url: str,
        unsubscribe_url: str
    ) -> str:
        """Format weekly update email as HTML"""

        # Build transaction cards
        transaction_cards = ""
        for txn in transactions:
            # Calculate progress bar
            progress = txn.get("milestone_progress", {})
            completed = progress.get("completed", 0)
            total = progress.get("total", 1)
            progress_pct = int((completed / total) * 100) if total > 0 else 0

            # Status badge color
            status = txn.get("current_status", "active")
            status_colors = {
                "active": "#3b82f6",
                "pending": "#f59e0b",
                "closing": "#10b981",
                "on_hold": "#6b7280"
            }
            status_color = status_colors.get(status, "#3b82f6")

            # Days until close
            days_until = txn.get("days_until_close")
            close_info = ""
            if days_until is not None:
                if days_until < 0:
                    close_info = f'<span style="color: #ef4444;">Closing date passed ({abs(days_until)} days ago)</span>'
                elif days_until == 0:
                    close_info = '<span style="color: #10b981; font-weight: bold;">Closing TODAY!</span>'
                elif days_until <= 7:
                    close_info = f'<span style="color: #f59e0b; font-weight: bold;">{days_until} days until closing</span>'
                else:
                    close_info = f'{days_until} days until closing'

            # Recent milestones
            milestones_html = ""
            recent_completed = [m for m in txn.get("milestones", []) if m.get("status") == "completed"][-3:]
            if recent_completed:
                milestones_html = '<div style="margin-top: 12px;"><strong>Recent Progress:</strong><ul style="margin: 8px 0; padding-left: 20px;">'
                for m in recent_completed:
                    milestones_html += f'<li style="color: #10b981;">{m["name"]}</li>'
                milestones_html += '</ul></div>'

            # Next milestone
            pending_milestones = [m for m in txn.get("milestones", []) if m.get("status") in ["pending", "in_progress"]]
            next_milestone = pending_milestones[0] if pending_milestones else None
            next_html = ""
            if next_milestone:
                next_html = f'''
                <div style="margin-top: 8px; padding: 8px 12px; background: #fef3c7; border-radius: 6px;">
                    <strong>Next Step:</strong> {next_milestone["name"]}
                </div>
                '''

            transaction_cards += f'''
            <div style="background: white; border-radius: 12px; padding: 24px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);">
                <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 16px;">
                    <div>
                        <h3 style="margin: 0 0 4px 0; color: #1f2937; font-size: 18px;">
                            {txn.get("property_address", "Property")}
                        </h3>
                        <p style="margin: 0; color: #6b7280; font-size: 14px;">
                            {txn.get("property_city", "")}{", " + txn.get("property_state", "") if txn.get("property_state") else ""}
                        </p>
                    </div>
                    <span style="background: {status_color}; color: white; padding: 4px 12px; border-radius: 20px; font-size: 12px; text-transform: uppercase; font-weight: 600;">
                        {status.replace("_", " ")}
                    </span>
                </div>

                <div style="background: #f3f4f6; border-radius: 8px; padding: 12px 16px; margin-bottom: 16px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <span style="font-size: 14px; color: #374151;">Progress</span>
                        <span style="font-size: 14px; font-weight: 600; color: #374151;">{completed}/{total} milestones</span>
                    </div>
                    <div style="background: #e5e7eb; border-radius: 999px; height: 8px; overflow: hidden;">
                        <div style="background: linear-gradient(90deg, #10b981, #34d399); height: 100%; width: {progress_pct}%; border-radius: 999px;"></div>
                    </div>
                </div>

                {f'<p style="margin: 0 0 12px 0; font-size: 14px;">{close_info}</p>' if close_info else ''}

                {milestones_html}
                {next_html}
            </div>
            '''

        html = f'''
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Weekly Transaction Update</title>
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f3f4f6;">
    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">

        <!-- Header -->
        <div style="text-align: center; margin-bottom: 32px;">
            <h1 style="color: #1f2937; font-size: 28px; margin: 0 0 8px 0;">
                Weekly Transaction Update
            </h1>
            <p style="color: #6b7280; font-size: 16px; margin: 0;">
                {datetime.now().strftime("%B %d, %Y")}
            </p>
        </div>

        <!-- Greeting -->
        <div style="background: white; border-radius: 12px; padding: 24px; margin-bottom: 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);">
            <p style="margin: 0; font-size: 16px; color: #374151;">
                Hi {party_name},
            </p>
            <p style="margin: 12px 0 0 0; font-size: 16px; color: #374151;">
                Here's your weekly update on your {len(transactions)} active transaction{"s" if len(transactions) != 1 else ""}.
            </p>
        </div>

        <!-- Transaction Cards -->
        {transaction_cards}

        <!-- CTA -->
        <div style="text-align: center; margin: 32px 0;">
            <a href="{portal_url}" style="display: inline-block; background: #3b82f6; color: white; padding: 14px 32px; border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 16px;">
                View Full Details in Portal
            </a>
        </div>

        <!-- Footer -->
        <div style="text-align: center; padding-top: 24px; border-top: 1px solid #e5e7eb;">
            <p style="color: #9ca3af; font-size: 12px; margin: 0 0 8px 0;">
                This email was sent by Perennia AI on behalf of your loan officer.
            </p>
            <p style="color: #9ca3af; font-size: 12px; margin: 0;">
                <a href="{unsubscribe_url}" style="color: #6b7280;">Unsubscribe from weekly updates</a>
            </p>
        </div>

    </div>
</body>
</html>
'''
        return html

    def _format_weekly_update_plain(
        self,
        party_name: str,
        transactions: List[Dict[str, Any]],
        portal_url: str,
        unsubscribe_url: str
    ) -> str:
        """Format weekly update email as plain text"""
        lines = [
            f"Weekly Transaction Update - {datetime.now().strftime('%B %d, %Y')}",
            "",
            f"Hi {party_name},",
            "",
            f"Here's your weekly update on your {len(transactions)} active transaction{'s' if len(transactions) != 1 else ''}.",
            "",
            "=" * 50,
            ""
        ]

        for txn in transactions:
            progress = txn.get("milestone_progress", {})
            completed = progress.get("completed", 0)
            total = progress.get("total", 1)

            lines.append(f"PROPERTY: {txn.get('property_address', 'Property')}")
            if txn.get("property_city"):
                lines.append(f"Location: {txn.get('property_city')}, {txn.get('property_state', '')}")
            lines.append(f"Status: {txn.get('current_status', 'active').upper()}")
            lines.append(f"Progress: {completed}/{total} milestones completed")

            days_until = txn.get("days_until_close")
            if days_until is not None:
                if days_until < 0:
                    lines.append(f"Closing: OVERDUE by {abs(days_until)} days")
                elif days_until == 0:
                    lines.append("Closing: TODAY!")
                else:
                    lines.append(f"Days until closing: {days_until}")

            # Recent completed milestones
            recent_completed = [m for m in txn.get("milestones", []) if m.get("status") == "completed"][-3:]
            if recent_completed:
                lines.append("")
                lines.append("Recent Progress:")
                for m in recent_completed:
                    lines.append(f"  - {m['name']}")

            # Next milestone
            pending = [m for m in txn.get("milestones", []) if m.get("status") in ["pending", "in_progress"]]
            if pending:
                lines.append(f"Next Step: {pending[0]['name']}")

            lines.append("")
            lines.append("-" * 50)
            lines.append("")

        lines.extend([
            f"View full details: {portal_url}",
            "",
            "---",
            "This email was sent by Perennia AI on behalf of your loan officer.",
            f"Unsubscribe: {unsubscribe_url}"
        ])

        return "\n".join(lines)

    def send_milestone_notification(
        self,
        to_email: str,
        party_name: str,
        property_address: str,
        milestone_name: str,
        milestone_status: str,
        portal_url: str,
        unsubscribe_url: str
    ) -> bool:
        """Send notification when a milestone changes"""
        try:
            subject = f"Milestone Update: {milestone_name} - {property_address}"

            status_emoji = {
                "completed": "check",
                "in_progress": "arrow-right",
                "blocked": "alert"
            }
            emoji = status_emoji.get(milestone_status, "info")

            html_body = f'''
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Milestone Update</title>
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #f3f4f6;">
    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background: white; border-radius: 12px; padding: 32px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);">

            <h1 style="margin: 0 0 16px 0; color: #1f2937; font-size: 24px;">
                Milestone Update
            </h1>

            <p style="margin: 0 0 24px 0; color: #6b7280;">
                Hi {party_name}, there's an update on your transaction.
            </p>

            <div style="background: #f0fdf4; border-left: 4px solid #10b981; padding: 16px; border-radius: 0 8px 8px 0; margin-bottom: 24px;">
                <h2 style="margin: 0 0 8px 0; color: #166534; font-size: 18px;">
                    {milestone_name}
                </h2>
                <p style="margin: 0; color: #166534; text-transform: uppercase; font-size: 12px; font-weight: 600;">
                    {milestone_status.replace("_", " ")}
                </p>
            </div>

            <p style="margin: 0 0 8px 0; color: #6b7280; font-size: 14px;">Property:</p>
            <p style="margin: 0 0 24px 0; color: #1f2937; font-size: 16px; font-weight: 500;">
                {property_address}
            </p>

            <a href="{portal_url}" style="display: inline-block; background: #3b82f6; color: white; padding: 12px 24px; border-radius: 8px; text-decoration: none; font-weight: 600;">
                View Transaction Details
            </a>

        </div>

        <div style="text-align: center; padding-top: 24px;">
            <p style="color: #9ca3af; font-size: 12px; margin: 0;">
                <a href="{unsubscribe_url}" style="color: #6b7280;">Unsubscribe from milestone updates</a>
            </p>
        </div>
    </div>
</body>
</html>
'''

            plain_text = f'''
Milestone Update

Hi {party_name}, there's an update on your transaction.

MILESTONE: {milestone_name}
STATUS: {milestone_status.upper()}

Property: {property_address}

View details: {portal_url}

---
Unsubscribe: {unsubscribe_url}
'''

            success = email_service.send_html_email(
                to_email=to_email,
                subject=subject,
                html_body=html_body,
                plain_text_body=plain_text,
                from_email=self.from_email
            )

            return success

        except Exception as e:
            logger.error(f"Error sending milestone notification: {e}")
            return False

    def send_portal_invite(
        self,
        to_email: str,
        party_name: str,
        property_address: str,
        lo_name: str,
        portal_url: str
    ) -> bool:
        """Send portal invite email with magic link"""
        try:
            subject = f"You're invited to track your transaction - {property_address}"

            html_body = f'''
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Portal Invitation</title>
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #f3f4f6;">
    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background: white; border-radius: 12px; padding: 32px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);">

            <div style="text-align: center; margin-bottom: 24px;">
                <h1 style="margin: 0; color: #1f2937; font-size: 28px;">
                    Transaction Portal Invitation
                </h1>
            </div>

            <p style="color: #374151; font-size: 16px; line-height: 1.6;">
                Hi {party_name},
            </p>

            <p style="color: #374151; font-size: 16px; line-height: 1.6;">
                {lo_name} has invited you to access the transaction portal for:
            </p>

            <div style="background: #f0f9ff; border-radius: 8px; padding: 16px; margin: 24px 0; text-align: center;">
                <p style="margin: 0; color: #1e40af; font-size: 18px; font-weight: 600;">
                    {property_address}
                </p>
            </div>

            <p style="color: #374151; font-size: 16px; line-height: 1.6;">
                With this portal, you can:
            </p>

            <ul style="color: #374151; font-size: 16px; line-height: 1.8; padding-left: 24px;">
                <li>Track loan progress in real-time</li>
                <li>See milestone completions</li>
                <li>Communicate directly with your loan officer</li>
                <li>Receive weekly status updates</li>
            </ul>

            <div style="text-align: center; margin: 32px 0;">
                <a href="{portal_url}" style="display: inline-block; background: #3b82f6; color: white; padding: 16px 48px; border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 18px;">
                    Access Your Portal
                </a>
            </div>

            <p style="color: #6b7280; font-size: 14px; text-align: center;">
                This link is unique to you and will remain active for 72 hours.
                <br>No password required - just click the button above.
            </p>

        </div>

        <div style="text-align: center; padding-top: 24px;">
            <p style="color: #9ca3af; font-size: 12px; margin: 0;">
                Sent via Perennia AI on behalf of {lo_name}
            </p>
        </div>
    </div>
</body>
</html>
'''

            plain_text = f'''
Transaction Portal Invitation

Hi {party_name},

{lo_name} has invited you to access the transaction portal for:

{property_address}

With this portal, you can:
- Track loan progress in real-time
- See milestone completions
- Communicate directly with your loan officer
- Receive weekly status updates

Access your portal: {portal_url}

This link is unique to you and will remain active for 72 hours.
No password required - just click the link above.

---
Sent via Perennia AI on behalf of {lo_name}
'''

            success = email_service.send_html_email(
                to_email=to_email,
                subject=subject,
                html_body=html_body,
                plain_text_body=plain_text,
                from_email=self.from_email
            )

            if success:
                logger.info(f"Portal invite sent to {to_email}")

            return success

        except Exception as e:
            logger.error(f"Error sending portal invite: {e}")
            return False


# Global instance
listing_update_email_service = ListingUpdateEmailService()
