"""
Channel Adapter Service — Module 5 Implementation

Unified multi-channel communication adapter that routes messages through
the correct channel based on ChannelPreference, enforces quiet hours,
verifies consent, prevents fatigue, and handles fallback routing.

This service sits above the individual channel senders (SendGrid, Telnyx,
push, in-app) and provides a single send() entry point for all agents.

Usage:
    from services.channel_adapter_service import ChannelAdapterService

    adapter = ChannelAdapterService(db)
    result = adapter.send(
        recipient_type="lead",
        recipient_id=123,
        organization_id=1,
        message_type="document_reminder",
        priority="high",
        subject="Missing Documents",
        body="Please upload your W-2s...",
        template_id=None,  # or use a MessageTemplate
        context={"loan_number": "LOAN-4521", "lo_name": "Tim"},
    )
"""

import hashlib
import logging
from datetime import datetime, timezone, time as dt_time
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS & CONSTANTS
# =============================================================================

class ChannelType(str, Enum):
    EMAIL = "email"
    SMS = "sms"
    CALL = "call"
    PUSH = "push"
    IN_APP = "in_app"
    TEAMS = "teams"
    VOICEMAIL = "voicemail"


class MessagePriority(str, Enum):
    CRITICAL = "critical"    # Lock expiration, SLA breach, system outage
    HIGH = "high"            # Condition updates, approval notifications
    NORMAL = "normal"        # Status updates, document confirmations
    LOW = "low"              # Tips, announcements, weekly summaries
    MARKETING = "marketing"  # Rate alerts, newsletters — requires consent


class DeliveryStatus(str, Enum):
    SENT = "sent"
    QUEUED = "queued"
    BUFFERED = "buffered"          # Held for quiet hours
    BLOCKED_CONSENT = "blocked_consent"
    BLOCKED_DNC = "blocked_dnc"
    BLOCKED_QUIET_HOURS = "blocked_quiet_hours"
    BLOCKED_FATIGUE = "blocked_fatigue"
    FAILED = "failed"
    FALLBACK = "fallback"          # Sent via fallback channel


# Channel selection by priority (Module 5 spec from Notification Center)
PRIORITY_CHANNEL_MAP = {
    MessagePriority.CRITICAL: [ChannelType.PUSH, ChannelType.SMS, ChannelType.EMAIL],
    MessagePriority.HIGH: [ChannelType.PUSH, ChannelType.EMAIL],
    MessagePriority.NORMAL: [ChannelType.IN_APP, ChannelType.EMAIL],
    MessagePriority.LOW: [ChannelType.IN_APP],
    MessagePriority.MARKETING: [ChannelType.EMAIL],
}

# Channel content limits
CHANNEL_LIMITS = {
    ChannelType.EMAIL: {"max_subject": 150, "max_body": 50000},
    ChannelType.SMS: {"max_body": 320},  # 2 segments
    ChannelType.PUSH: {"max_body": 240},
    ChannelType.IN_APP: {"max_body": 5000},
    ChannelType.VOICEMAIL: {"max_body": 500},  # Script text
    ChannelType.TEAMS: {"max_body": 5000},
}

# TCPA calling window (federal default)
TCPA_WINDOW_START = dt_time(8, 0)   # 8:00 AM
TCPA_WINDOW_END = dt_time(21, 0)    # 9:00 PM


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class ChannelDeliveryResult:
    """Result of a single channel delivery attempt."""
    channel: ChannelType
    status: DeliveryStatus
    message: str = ""
    tracking_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SendResult:
    """Result of the unified send operation."""
    success: bool
    primary_channel: Optional[ChannelType] = None
    delivery_results: List[ChannelDeliveryResult] = field(default_factory=list)
    message: str = ""
    buffered_until: Optional[datetime] = None
    fatigue_warning: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "primary_channel": self.primary_channel.value if self.primary_channel else None,
            "delivery_results": [
                {
                    "channel": r.channel.value,
                    "status": r.status.value,
                    "message": r.message,
                    "tracking_id": r.tracking_id,
                }
                for r in self.delivery_results
            ],
            "message": self.message,
            "buffered_until": self.buffered_until.isoformat() if self.buffered_until else None,
            "fatigue_warning": self.fatigue_warning,
        }


# =============================================================================
# CHANNEL ADAPTER SERVICE
# =============================================================================

class ChannelAdapterService:
    """Unified multi-channel communication adapter (Module 5).

    Routes messages through the correct channel based on recipient preferences,
    consent status, quiet hours, and fatigue limits. Handles fallback routing
    when the preferred channel is blocked.
    """

    def __init__(self, db_session):
        """Initialize with a SQLAlchemy session.

        Args:
            db_session: Active SQLAlchemy session for preference lookups.
        """
        self.db = db_session

    # -------------------------------------------------------------------------
    # PUBLIC API
    # -------------------------------------------------------------------------

    def send(
        self,
        recipient_type: str,           # "lead" or "user"
        recipient_id: int,
        organization_id: int,
        message_type: str,             # document_reminder, rate_alert, sla_breach, etc.
        priority: str,                 # critical, high, normal, low, marketing
        body: str,
        subject: Optional[str] = None,
        template_id: Optional[int] = None,
        context: Optional[Dict[str, Any]] = None,
        force_channel: Optional[str] = None,
        skip_quiet_hours: bool = False,
    ) -> SendResult:
        """Send a message through the optimal channel.

        1. Load recipient preferences (ChannelPreference)
        2. Determine channels based on priority + preferences
        3. Check consent per channel
        4. Enforce quiet hours
        5. Check fatigue limits
        6. Attempt delivery with fallback
        7. Log the delivery attempt

        Args:
            recipient_type: "lead" or "user"
            recipient_id: ID of the lead or user
            organization_id: Tenant ID
            message_type: Category of message for template matching
            priority: Message priority level
            body: Message body text
            subject: Subject line (email only)
            template_id: Optional MessageTemplate ID to use
            context: Variables for template personalization
            force_channel: Override channel selection (bypasses preference logic)
            skip_quiet_hours: Only for CRITICAL priority — override quiet hours

        Returns:
            SendResult with delivery status per channel
        """
        priority_enum = MessagePriority(priority)
        context = context or {}

        # Step 1: Load preferences
        prefs = self._load_preferences(recipient_type, recipient_id, organization_id)

        # Step 2: Determine channel order
        if force_channel:
            channels = [ChannelType(force_channel)]
        else:
            channels = self._resolve_channels(priority_enum, prefs)

        if not channels:
            return SendResult(
                success=False,
                message="No eligible channels for this recipient and priority",
            )

        # Step 3: Load template if specified
        if template_id:
            template_content = self._load_template(template_id, context)
            if template_content:
                body = template_content.get("body", body)
                subject = template_content.get("subject", subject)

        # Step 4: Quiet hours check
        if not skip_quiet_hours or priority_enum != MessagePriority.CRITICAL:
            in_quiet, resume_at = self._check_quiet_hours(prefs)
            if in_quiet and priority_enum not in (MessagePriority.CRITICAL,):
                return SendResult(
                    success=False,
                    message=f"Recipient is in quiet hours. Buffered until {resume_at}",
                    buffered_until=resume_at,
                    delivery_results=[
                        ChannelDeliveryResult(
                            channel=channels[0],
                            status=DeliveryStatus.BUFFERED,
                            message=f"Quiet hours active until {resume_at}",
                        )
                    ],
                )

        # Step 5: Fatigue check
        fatigue_ok, fatigue_msg = self._check_fatigue(
            recipient_type, recipient_id, organization_id, priority_enum
        )
        if not fatigue_ok:
            return SendResult(
                success=False,
                message=fatigue_msg,
                fatigue_warning=True,
                delivery_results=[
                    ChannelDeliveryResult(
                        channel=channels[0],
                        status=DeliveryStatus.BLOCKED_FATIGUE,
                        message=fatigue_msg,
                    )
                ],
            )

        # Step 6: Attempt delivery with fallback
        delivery_results = []
        sent = False
        primary_channel = None

        for channel in channels:
            # Check consent for this specific channel
            consent_ok, consent_msg = self._check_consent(channel, prefs, priority_enum)
            if not consent_ok:
                delivery_results.append(ChannelDeliveryResult(
                    channel=channel,
                    status=DeliveryStatus.BLOCKED_CONSENT,
                    message=consent_msg,
                ))
                continue

            # Check DNC for this channel
            dnc_blocked = self._check_dnc(channel, prefs)
            if dnc_blocked:
                delivery_results.append(ChannelDeliveryResult(
                    channel=channel,
                    status=DeliveryStatus.BLOCKED_DNC,
                    message=f"DNC active for {channel.value}",
                ))
                continue

            # Check TCPA window for SMS/call
            if channel in (ChannelType.SMS, ChannelType.CALL, ChannelType.VOICEMAIL):
                if not self._in_tcpa_window(prefs.get("timezone", "America/New_York")):
                    if priority_enum != MessagePriority.CRITICAL:
                        delivery_results.append(ChannelDeliveryResult(
                            channel=channel,
                            status=DeliveryStatus.BLOCKED_QUIET_HOURS,
                            message="Outside TCPA 8am-9pm calling window",
                        ))
                        continue

            # Truncate content for channel limits
            channel_body = self._enforce_channel_limits(channel, body)
            channel_subject = subject

            # Dispatch to channel-specific sender
            result = self._dispatch(
                channel=channel,
                recipient_type=recipient_type,
                recipient_id=recipient_id,
                organization_id=organization_id,
                message_type=message_type,
                subject=channel_subject,
                body=channel_body,
                context=context,
            )

            delivery_results.append(result)

            if result.status == DeliveryStatus.SENT:
                sent = True
                primary_channel = channel
                # For non-critical, stop after first successful send
                if priority_enum != MessagePriority.CRITICAL:
                    break
            elif result.status == DeliveryStatus.QUEUED:
                sent = True
                primary_channel = channel
                break

        # Step 7: Log delivery attempt
        self._log_delivery(
            recipient_type=recipient_type,
            recipient_id=recipient_id,
            organization_id=organization_id,
            message_type=message_type,
            priority=priority_enum,
            channels_attempted=[r.channel for r in delivery_results],
            primary_channel=primary_channel,
            success=sent,
        )

        return SendResult(
            success=sent,
            primary_channel=primary_channel,
            delivery_results=delivery_results,
            message="Delivered" if sent else "All channels blocked or failed",
            fatigue_warning=self._near_fatigue_limit(
                recipient_type, recipient_id, organization_id
            ),
        )

    def get_preferences(
        self,
        recipient_type: str,
        recipient_id: int,
        organization_id: int,
    ) -> Dict[str, Any]:
        """Get channel preferences for a recipient (public accessor)."""
        return self._load_preferences(recipient_type, recipient_id, organization_id)

    def update_opt_out(
        self,
        recipient_type: str,
        recipient_id: int,
        organization_id: int,
        channel: str,
    ) -> Dict[str, Any]:
        """Process an opt-out request for a specific channel.

        Per Module 5 compliance: opt-outs process IMMEDIATELY, no confirmation
        required, no delay permitted.
        """
        try:
            from database.models.communication import ChannelPreference
        except ImportError:
            logger.warning("ChannelPreference model not available")
            return {"success": False, "error": "Model not available"}

        filter_kwargs = {"organization_id": organization_id}
        if recipient_type == "lead":
            filter_kwargs["lead_id"] = recipient_id
        else:
            filter_kwargs["user_id"] = recipient_id

        pref = self.db.query(ChannelPreference).filter_by(**filter_kwargs).first()
        if not pref:
            return {"success": False, "error": "No preferences found"}

        channel_dnc_map = {
            "email": "do_not_email",
            "sms": "do_not_sms",
            "call": "do_not_call",
            "mail": "do_not_mail",
        }

        attr = channel_dnc_map.get(channel)
        if attr and hasattr(pref, attr):
            setattr(pref, attr, True)
            pref.updated_at = datetime.now(timezone.utc)
            self.db.flush()
            logger.info(
                "Opt-out processed: %s %d opted out of %s",
                recipient_type, recipient_id, channel,
            )
            return {"success": True, "channel": channel, "action": "opted_out"}

        return {"success": False, "error": f"Unknown channel: {channel}"}

    # -------------------------------------------------------------------------
    # PREFERENCE LOADING
    # -------------------------------------------------------------------------

    def _load_preferences(
        self,
        recipient_type: str,
        recipient_id: int,
        organization_id: int,
    ) -> Dict[str, Any]:
        """Load ChannelPreference for the recipient.

        Returns a dict of preferences for use by routing logic.
        Falls back to system defaults if no preferences exist.
        """
        try:
            from database.models.communication import ChannelPreference
        except ImportError:
            logger.warning("ChannelPreference model not available, using defaults")
            return self._default_preferences()

        filter_kwargs = {"organization_id": organization_id}
        if recipient_type == "lead":
            filter_kwargs["lead_id"] = recipient_id
        else:
            filter_kwargs["user_id"] = recipient_id

        pref = self.db.query(ChannelPreference).filter_by(**filter_kwargs).first()

        if not pref:
            return self._default_preferences()

        return {
            "preferred_channels": pref.preferred_channels or ["email", "sms", "call"],
            "do_not_email": pref.do_not_email or False,
            "do_not_sms": pref.do_not_sms or False,
            "do_not_call": pref.do_not_call or False,
            "do_not_mail": pref.do_not_mail or False,
            "quiet_hours_start": pref.quiet_hours_start or "21:00",
            "quiet_hours_end": pref.quiet_hours_end or "08:00",
            "quiet_days": pref.quiet_days or [],
            "timezone": pref.timezone or "America/New_York",
            "language": pref.language or "en",
            "sms_consent": pref.sms_consent or False,
            "call_consent": pref.call_consent or False,
            "email_opt_in": pref.email_opt_in if pref.email_opt_in is not None else True,
            "max_contacts_per_day": pref.max_contacts_per_day or 5,
            "max_contacts_per_week": pref.max_contacts_per_week or 15,
        }

    def _default_preferences(self) -> Dict[str, Any]:
        """Return system default preferences."""
        return {
            "preferred_channels": ["email", "sms", "call"],
            "do_not_email": False,
            "do_not_sms": False,
            "do_not_call": False,
            "do_not_mail": False,
            "quiet_hours_start": "21:00",
            "quiet_hours_end": "08:00",
            "quiet_days": ["Saturday", "Sunday"],
            "timezone": "America/New_York",
            "language": "en",
            "sms_consent": False,
            "call_consent": False,
            "email_opt_in": True,
            "max_contacts_per_day": 5,
            "max_contacts_per_week": 15,
        }

    # -------------------------------------------------------------------------
    # CHANNEL RESOLUTION
    # -------------------------------------------------------------------------

    def _resolve_channels(
        self,
        priority: MessagePriority,
        prefs: Dict[str, Any],
    ) -> List[ChannelType]:
        """Determine ordered channel list based on priority and preferences.

        For CRITICAL: use all priority-mapped channels regardless of preference.
        For others: intersect priority channels with user preferred channels,
        then append remaining priority channels as fallback.
        """
        priority_channels = PRIORITY_CHANNEL_MAP.get(priority, [ChannelType.EMAIL])

        if priority == MessagePriority.CRITICAL:
            # Critical bypasses preference ordering but still respects DNC
            return list(priority_channels)

        preferred = [
            ChannelType(c) for c in prefs.get("preferred_channels", [])
            if c in [ch.value for ch in ChannelType]
        ]

        # Intersect: preferred channels that are in the priority set
        ordered = [c for c in preferred if c in priority_channels]

        # Append remaining priority channels as fallback
        for c in priority_channels:
            if c not in ordered:
                ordered.append(c)

        return ordered

    # -------------------------------------------------------------------------
    # CONSENT & DNC CHECKS
    # -------------------------------------------------------------------------

    def _check_consent(
        self,
        channel: ChannelType,
        prefs: Dict[str, Any],
        priority: MessagePriority,
    ) -> Tuple[bool, str]:
        """Check if consent exists for this channel.

        SMS requires explicit sms_consent (TCPA).
        Call requires call_consent.
        Email requires email_opt_in for marketing, otherwise assumed OK.
        Push/In-app don't require explicit consent.
        """
        if channel == ChannelType.SMS:
            if not prefs.get("sms_consent"):
                return False, "No SMS consent on file (TCPA required)"
        elif channel == ChannelType.CALL:
            if not prefs.get("call_consent"):
                return False, "No call consent on file"
        elif channel == ChannelType.EMAIL:
            if priority == MessagePriority.MARKETING:
                if not prefs.get("email_opt_in"):
                    return False, "Email marketing opt-in required"
        # Push, in-app, teams don't require explicit consent
        return True, "OK"

    def _check_dnc(self, channel: ChannelType, prefs: Dict[str, Any]) -> bool:
        """Check if the channel is DNC-blocked."""
        dnc_map = {
            ChannelType.EMAIL: "do_not_email",
            ChannelType.SMS: "do_not_sms",
            ChannelType.CALL: "do_not_call",
            ChannelType.VOICEMAIL: "do_not_call",  # Voicemail = call channel
        }
        dnc_key = dnc_map.get(channel)
        if dnc_key:
            return prefs.get(dnc_key, False)
        return False

    # -------------------------------------------------------------------------
    # QUIET HOURS & TCPA
    # -------------------------------------------------------------------------

    def _check_quiet_hours(
        self,
        prefs: Dict[str, Any],
    ) -> Tuple[bool, Optional[datetime]]:
        """Check if recipient is in quiet hours.

        Returns (is_in_quiet_hours, resume_at_datetime).
        """
        try:
            import pytz
            tz = pytz.timezone(prefs.get("timezone", "America/New_York"))
            now_local = datetime.now(tz)
        except Exception as e:
            logger.exception(f"Failed to determine local time for quiet hours check: {e}")
            now_local = datetime.now(timezone.utc)

        # Check quiet days
        day_name = now_local.strftime("%A")
        quiet_days = prefs.get("quiet_days", [])
        if day_name in quiet_days:
            # Quiet all day — resume next non-quiet day at quiet_hours_end
            return True, None

        # Check quiet hours
        start_str = prefs.get("quiet_hours_start", "21:00")
        end_str = prefs.get("quiet_hours_end", "08:00")

        try:
            start_h, start_m = map(int, start_str.split(":"))
            end_h, end_m = map(int, end_str.split(":"))
        except (ValueError, AttributeError):
            return False, None

        start_time = dt_time(start_h, start_m)
        end_time = dt_time(end_h, end_m)
        current_time = now_local.time()

        # Handle overnight quiet hours (e.g., 21:00 to 08:00)
        if start_time > end_time:
            in_quiet = current_time >= start_time or current_time < end_time
        else:
            in_quiet = start_time <= current_time < end_time

        if in_quiet:
            # Calculate resume time
            resume_time = now_local.replace(
                hour=end_h, minute=end_m, second=0, microsecond=0
            )
            if resume_time <= now_local:
                from datetime import timedelta
                resume_time += timedelta(days=1)
            return True, resume_time

        return False, None

    def _in_tcpa_window(self, timezone_str: str) -> bool:
        """Check if current time is within TCPA 8am-9pm window."""
        try:
            import pytz
            tz = pytz.timezone(timezone_str)
            now_local = datetime.now(tz).time()
        except Exception as e:
            logger.exception(f"Failed to determine local time for TCPA window check: {e}")
            now_local = datetime.now(timezone.utc).time()

        return TCPA_WINDOW_START <= now_local <= TCPA_WINDOW_END

    # -------------------------------------------------------------------------
    # FATIGUE PREVENTION
    # -------------------------------------------------------------------------

    def _check_fatigue(
        self,
        recipient_type: str,
        recipient_id: int,
        organization_id: int,
        priority: MessagePriority,
    ) -> Tuple[bool, str]:
        """Check if sending would exceed fatigue limits.

        Critical priority bypasses fatigue limits.
        """
        if priority == MessagePriority.CRITICAL:
            return True, "Critical bypasses fatigue"

        try:
            from database.models.security import IntegrationLog
        except ImportError:
            return True, "Fatigue check skipped — model not available"

        # Count recent notifications for this recipient
        prefs = self._load_preferences(recipient_type, recipient_id, organization_id)
        max_daily = prefs.get("max_contacts_per_day", 5)

        try:
            from datetime import timedelta
            since = datetime.now(timezone.utc) - timedelta(hours=24)
            count = self.db.execute(
                """
                SELECT COUNT(*) FROM integration_logs
                WHERE organization_id = :org_id
                  AND log_type = 'channel_delivery'
                  AND details->>'recipient_id' = :rid
                  AND details->>'recipient_type' = :rtype
                  AND created_at >= :since
                """,
                {
                    "org_id": organization_id,
                    "rid": str(recipient_id),
                    "rtype": recipient_type,
                    "since": since,
                },
            ).scalar() or 0

            if count >= max_daily:
                return False, f"Fatigue limit reached: {count}/{max_daily} contacts in 24h"
        except Exception as e:
            logger.warning("Fatigue check failed: %s — allowing send", e)

        return True, "OK"

    def _near_fatigue_limit(
        self,
        recipient_type: str,
        recipient_id: int,
        organization_id: int,
    ) -> bool:
        """Check if recipient is approaching fatigue limit (>80%)."""
        prefs = self._load_preferences(recipient_type, recipient_id, organization_id)
        max_daily = prefs.get("max_contacts_per_day", 5)

        try:
            from datetime import timedelta
            since = datetime.now(timezone.utc) - timedelta(hours=24)
            count = self.db.execute(
                """
                SELECT COUNT(*) FROM integration_logs
                WHERE organization_id = :org_id
                  AND log_type = 'channel_delivery'
                  AND details->>'recipient_id' = :rid
                  AND details->>'recipient_type' = :rtype
                  AND created_at >= :since
                """,
                {
                    "org_id": organization_id,
                    "rid": str(recipient_id),
                    "rtype": recipient_type,
                    "since": since,
                },
            ).scalar() or 0

            return count >= (max_daily * 0.8)
        except Exception as e:
            logger.exception(f"Failed to check near-fatigue limit: {e}")
            return False

    # -------------------------------------------------------------------------
    # CHANNEL LIMITS
    # -------------------------------------------------------------------------

    def _enforce_channel_limits(self, channel: ChannelType, body: str) -> str:
        """Truncate body to fit channel limits."""
        limits = CHANNEL_LIMITS.get(channel, {})
        max_body = limits.get("max_body")
        if max_body and len(body) > max_body:
            return body[:max_body - 3] + "..."
        return body

    # -------------------------------------------------------------------------
    # TEMPLATE LOADING
    # -------------------------------------------------------------------------

    def _load_template(
        self,
        template_id: int,
        context: Dict[str, Any],
    ) -> Optional[Dict[str, str]]:
        """Load and render a MessageTemplate."""
        try:
            from database.models.communication import MessageTemplate
        except ImportError:
            return None

        template = self.db.query(MessageTemplate).filter_by(
            id=template_id, is_active=True
        ).first()

        if not template:
            return None

        body = template.body_text or ""
        subject = template.subject or ""

        # Simple variable substitution: {{variable_name}}
        for key, value in context.items():
            placeholder = "{{" + key + "}}"
            body = body.replace(placeholder, str(value))
            subject = subject.replace(placeholder, str(value))

        return {"body": body, "subject": subject}

    # -------------------------------------------------------------------------
    # DISPATCH (CHANNEL-SPECIFIC SENDERS)
    # -------------------------------------------------------------------------

    def _dispatch(
        self,
        channel: ChannelType,
        recipient_type: str,
        recipient_id: int,
        organization_id: int,
        message_type: str,
        subject: Optional[str],
        body: str,
        context: Dict[str, Any],
    ) -> ChannelDeliveryResult:
        """Dispatch message to channel-specific sender.

        This is the integration point where the adapter connects to
        actual delivery infrastructure (SendGrid, Telnyx, etc.).
        Each channel delegates to the appropriate existing service.
        """
        try:
            if channel == ChannelType.EMAIL:
                return self._send_email(
                    recipient_type, recipient_id, organization_id,
                    subject, body, context,
                )
            elif channel == ChannelType.SMS:
                return self._send_sms(
                    recipient_type, recipient_id, organization_id,
                    body, context,
                )
            elif channel == ChannelType.PUSH:
                return self._send_push(
                    recipient_type, recipient_id, organization_id,
                    body, context,
                )
            elif channel == ChannelType.IN_APP:
                return self._send_in_app(
                    recipient_type, recipient_id, organization_id,
                    subject, body, context,
                )
            elif channel in (ChannelType.CALL, ChannelType.VOICEMAIL):
                # Calls/voicemails are scheduled, not sent inline
                return ChannelDeliveryResult(
                    channel=channel,
                    status=DeliveryStatus.QUEUED,
                    message=f"{channel.value} queued for dialer/voicemail system",
                )
            elif channel == ChannelType.TEAMS:
                return self._send_teams(
                    recipient_type, recipient_id, organization_id,
                    body, context,
                )
            else:
                return ChannelDeliveryResult(
                    channel=channel,
                    status=DeliveryStatus.FAILED,
                    message=f"Unknown channel: {channel.value}",
                )
        except Exception as e:
            logger.exception("Channel dispatch failed for %s", channel.value)
            return ChannelDeliveryResult(
                channel=channel,
                status=DeliveryStatus.FAILED,
                message=str(e),
            )

    def _send_email(
        self,
        recipient_type: str,
        recipient_id: int,
        organization_id: int,
        subject: Optional[str],
        body: str,
        context: Dict[str, Any],
    ) -> ChannelDeliveryResult:
        """Send via email (delegates to NotificationService/SendGrid)."""
        email_address = self._get_recipient_email(recipient_type, recipient_id)
        if not email_address:
            return ChannelDeliveryResult(
                channel=ChannelType.EMAIL,
                status=DeliveryStatus.FAILED,
                message="No email address on file",
            )

        try:
            from services.notification_service import NotificationService
            svc = NotificationService()
            svc.send_email(
                to_email=email_address,
                subject=subject or "Notification",
                body=body,
            )
            tracking_id = hashlib.md5(
                f"{email_address}:{datetime.now().isoformat()}".encode()
            ).hexdigest()[:12]

            return ChannelDeliveryResult(
                channel=ChannelType.EMAIL,
                status=DeliveryStatus.SENT,
                message=f"Email sent to {email_address}",
                tracking_id=tracking_id,
            )
        except Exception as e:
            logger.warning("Email send failed: %s", e)
            return ChannelDeliveryResult(
                channel=ChannelType.EMAIL,
                status=DeliveryStatus.FAILED,
                message=f"Email send failed: {e}",
            )

    def _send_sms(
        self,
        recipient_type: str,
        recipient_id: int,
        organization_id: int,
        body: str,
        context: Dict[str, Any],
    ) -> ChannelDeliveryResult:
        """Send via SMS (delegates to NotificationService/Telnyx)."""
        phone = self._get_recipient_phone(recipient_type, recipient_id)
        if not phone:
            return ChannelDeliveryResult(
                channel=ChannelType.SMS,
                status=DeliveryStatus.FAILED,
                message="No phone number on file",
            )

        try:
            from services.notification_service import NotificationService
            svc = NotificationService()
            svc.send_sms(to_phone=phone, message=body)

            return ChannelDeliveryResult(
                channel=ChannelType.SMS,
                status=DeliveryStatus.SENT,
                message=f"SMS sent to {phone[-4:]}",
            )
        except Exception as e:
            logger.warning("SMS send failed: %s", e)
            return ChannelDeliveryResult(
                channel=ChannelType.SMS,
                status=DeliveryStatus.FAILED,
                message=f"SMS send failed: {e}",
            )

    def _send_push(
        self,
        recipient_type: str,
        recipient_id: int,
        organization_id: int,
        body: str,
        context: Dict[str, Any],
    ) -> ChannelDeliveryResult:
        """Send push notification via APNs/FCM to user's registered devices."""
        if recipient_type != "user":
            return ChannelDeliveryResult(
                channel=ChannelType.PUSH,
                status=DeliveryStatus.SKIPPED,
                message=f"Push only supports user recipients, got {recipient_type}",
            )

        try:
            from services.push_notification_service import send_push_to_user

            title = context.get("subject") or context.get("title") or "Notification"
            notification_type = context.get("notification_type", "general")
            data = context.get("data")

            result = send_push_to_user(
                user_id=recipient_id,
                title=title,
                body=body[:500],
                data=data,
                notification_type=notification_type,
                db=self.db,
            )

            sent = result.get("sent", 0)
            if sent > 0:
                return ChannelDeliveryResult(
                    channel=ChannelType.PUSH,
                    status=DeliveryStatus.SENT,
                    message=f"Push sent to {sent} device(s)",
                )
            elif result.get("skipped", 0) > 0:
                return ChannelDeliveryResult(
                    channel=ChannelType.PUSH,
                    status=DeliveryStatus.SKIPPED,
                    message=result.get("reason", "No active devices or preference muted"),
                )
            else:
                return ChannelDeliveryResult(
                    channel=ChannelType.PUSH,
                    status=DeliveryStatus.FAILED,
                    message="Push failed for all devices",
                )

        except Exception as e:
            logger.warning("Push notification send failed: %s", e)
            return ChannelDeliveryResult(
                channel=ChannelType.PUSH,
                status=DeliveryStatus.FAILED,
                message=f"Push send failed: {e}",
            )

    def _send_in_app(
        self,
        recipient_type: str,
        recipient_id: int,
        organization_id: int,
        subject: Optional[str],
        body: str,
        context: Dict[str, Any],
    ) -> ChannelDeliveryResult:
        """Create in-app notification (writes to Notification table)."""
        try:
            from database.models.security import Notification

            notif = Notification(
                organization_id=organization_id,
                user_id=recipient_id if recipient_type == "user" else None,
                title=subject or "Notification",
                message=body[:500],
                type="system",
                is_read=False,
            )
            self.db.add(notif)
            self.db.flush()

            return ChannelDeliveryResult(
                channel=ChannelType.IN_APP,
                status=DeliveryStatus.SENT,
                message="In-app notification created",
                tracking_id=str(notif.id),
            )
        except Exception as e:
            logger.warning("In-app notification failed: %s", e)
            return ChannelDeliveryResult(
                channel=ChannelType.IN_APP,
                status=DeliveryStatus.FAILED,
                message=f"In-app notification failed: {e}",
            )

    def _send_teams(
        self,
        recipient_type: str,
        recipient_id: int,
        organization_id: int,
        body: str,
        context: Dict[str, Any],
    ) -> ChannelDeliveryResult:
        """Send Teams message (placeholder — requires Microsoft Graph integration)."""
        return ChannelDeliveryResult(
            channel=ChannelType.TEAMS,
            status=DeliveryStatus.QUEUED,
            message="Teams message queued",
        )

    # -------------------------------------------------------------------------
    # RECIPIENT LOOKUPS
    # -------------------------------------------------------------------------

    def _get_recipient_email(self, recipient_type: str, recipient_id: int) -> Optional[str]:
        """Look up email address for recipient."""
        try:
            if recipient_type == "lead":
                from database.models.lead_loan import Lead
                lead = self.db.query(Lead).filter_by(id=recipient_id).first()
                return lead.email if lead else None
            else:
                from database.models.core import User
                user = self.db.query(User).filter_by(id=recipient_id).first()
                return user.email if user else None
        except Exception as e:
            logger.exception(f"Failed to look up recipient email for {recipient_type} {recipient_id}: {e}")
            return None

    def _get_recipient_phone(self, recipient_type: str, recipient_id: int) -> Optional[str]:
        """Look up phone number for recipient."""
        try:
            if recipient_type == "lead":
                from database.models.lead_loan import Lead
                lead = self.db.query(Lead).filter_by(id=recipient_id).first()
                return lead.phone if lead else None
            else:
                from database.models.core import User
                user = self.db.query(User).filter_by(id=recipient_id).first()
                return user.phone if user else None
        except Exception as e:
            logger.exception(f"Failed to look up recipient phone for {recipient_type} {recipient_id}: {e}")
            return None

    # -------------------------------------------------------------------------
    # DELIVERY LOGGING
    # -------------------------------------------------------------------------

    def _log_delivery(
        self,
        recipient_type: str,
        recipient_id: int,
        organization_id: int,
        message_type: str,
        priority: MessagePriority,
        channels_attempted: List[ChannelType],
        primary_channel: Optional[ChannelType],
        success: bool,
    ) -> None:
        """Log the delivery attempt for fatigue tracking and audit."""
        try:
            from database.models.communication import IntegrationLog

            log = IntegrationLog(
                organization_id=organization_id,
                log_type="channel_delivery",
                details={
                    "recipient_type": recipient_type,
                    "recipient_id": str(recipient_id),
                    "message_type": message_type,
                    "priority": priority.value,
                    "channels_attempted": [c.value for c in channels_attempted],
                    "primary_channel": primary_channel.value if primary_channel else None,
                    "success": success,
                },
            )
            self.db.add(log)
            self.db.flush()
        except Exception as e:
            logger.warning("Failed to log channel delivery: %s", e)
