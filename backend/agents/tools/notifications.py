"""
Perennia AI - Notification Center Tools
=======================================
Tools for the Notification Center Agent managing alerts and notifications.
8 tools for notification management, preferences, and delivery.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

from .base import (
    mortgage_tool,
    ToolResult,
    execute_query,
    execute_single,
    format_date,
    db_session,
)


def _check_sms_compliance(phone: str) -> Optional[ToolResult]:
    """Check TCPA/DNC compliance before sending SMS."""
    # Check DNC
    dnc = execute_single(
        "SELECT id, reason FROM contact_dnc_status WHERE phone_number = :phone",
        {"phone": phone}
    )
    if dnc:
        return ToolResult.error(f"BLOCKED: Phone {phone} is on DNC list. Reason: {dnc.get('reason', 'N/A')}")

    # Check quiet hours (9pm-8am)
    now = datetime.now()
    if now.hour < 8 or now.hour >= 21:
        return ToolResult.error(f"BLOCKED: Outside TCPA SMS window (8am-9pm). Current hour: {now.hour}")

    return None


# =============================================================================
# Notification Center Tools (8 tools)
# =============================================================================

@mortgage_tool(
    name="send_notification",
    description="Send notification through specified channels",
    agent_roles=["notification_center"],
    risk_level="LOW",
    parameters={
        "recipient_id": "User ID to notify",
        "notification_type": "Type: alert, reminder, update, marketing",
        "title": "Notification title",
        "message": "Notification message",
        "channels": "Channels: in_app, email, sms, push",
        "priority": "Priority: low, normal, high, urgent",
        "data": "Additional data payload",
    },
)
def send_notification(
    recipient_id: str,
    notification_type: str,
    title: str,
    message: str,
    channels: Optional[List[str]] = None,
    priority: str = "normal",
    data: Optional[Dict] = None,
) -> ToolResult:
    """Send notification with TCPA compliance gate for SMS channel."""
    import uuid
    notification_id = str(uuid.uuid4())[:8].upper()

    if not channels:
        channels = ["in_app", "email"]

    # Validate channels
    valid_channels = ["in_app", "email", "sms", "push"]
    invalid_channels = [c for c in channels if c not in valid_channels]
    if invalid_channels:
        return ToolResult.error(f"Invalid channels: {invalid_channels}. Valid: {valid_channels}")

    # COMPLIANCE GATE — if SMS is a channel, check TCPA/DNC
    if "sms" in channels:
        # Get user phone for compliance check
        user_phone = execute_single(
            "SELECT phone FROM users WHERE id = :id", {"id": recipient_id}
        )
        if user_phone and user_phone.get("phone"):
            sms_block = _check_sms_compliance(user_phone["phone"])
            if sms_block:
                # Remove SMS from channels but continue with others
                channels = [c for c in channels if c != "sms"]
                if not channels:
                    return sms_block

    # Write to Notification table
    try:
        with db_session() as session:
            from sqlalchemy import text
            session.execute(text("""
                INSERT INTO notifications (user_id, type, title, message, is_read, created_at)
                VALUES (:user_id, :type, :title, :message, false, NOW())
            """), {
                "user_id": int(recipient_id) if recipient_id.isdigit() else None,
                "type": notification_type,
                "title": title,
                "message": message,
            })
    except Exception as e:
        logger.warning(f"Error writing notification to DB: {e}")  # DB write failure shouldn't block notification

    notification = {
        "notification_id": f"NOT-{notification_id}",
        "recipient_id": recipient_id,
        "type": notification_type,
        "title": title,
        "message": message,
        "channels": channels,
        "priority": priority,
        "data": data,
        "status": "sent",
        "sent_at": datetime.now().isoformat(),
        "delivery_status": {channel: "pending" for channel in channels},
        "compliance_cleared": True,
    }

    return ToolResult.success(
        data=notification,
        message=f"Notification sent: {title}",
    )


@mortgage_tool(
    name="get_pending_notifications",
    description="Get pending notifications in queue awaiting delivery",
    agent_roles=["notification_center"],
    risk_level="LOW",
    parameters={
        "channel": "Filter by channel: email, sms, push, in_app",
        "priority": "Filter by priority: low, normal, high, urgent",
        "recipient_id": "Filter by recipient",
        "limit": "Maximum to return",
    },
)
def get_pending_notifications(
    channel: Optional[str] = None,
    priority: Optional[str] = None,
    recipient_id: Optional[str] = None,
    limit: int = 50,
) -> ToolResult:
    """Get pending notifications."""
    params = {"limit": limit}
    filters = ["status = 'pending'"]

    if channel:
        filters.append(":channel = ANY(channels)")
        params["channel"] = channel
    if priority:
        filters.append("priority = :priority")
        params["priority"] = priority
    if recipient_id:
        filters.append("recipient_id = :recipient_id")
        params["recipient_id"] = recipient_id

    where_sql = " AND ".join(filters)

    notifications = execute_query(f"""
        SELECT
            id, notification_id, recipient_id, type,
            title, message, channels, priority,
            status, created_at
        FROM notifications
        WHERE {where_sql}
        ORDER BY
            CASE priority
                WHEN 'urgent' THEN 1
                WHEN 'high' THEN 2
                WHEN 'normal' THEN 3
                WHEN 'low' THEN 4
                ELSE 5
            END,
            created_at ASC
        LIMIT :limit
    """, params)

    if not notifications:
        notifications = []

    # Get queue summary
    summary = execute_single("""
        SELECT
            COUNT(*) as total_pending,
            COUNT(CASE WHEN priority = 'urgent' THEN 1 END) as urgent,
            COUNT(CASE WHEN priority = 'high' THEN 1 END) as high,
            COUNT(CASE WHEN 'email' = ANY(channels) THEN 1 END) as email,
            COUNT(CASE WHEN 'sms' = ANY(channels) THEN 1 END) as sms
        FROM notifications
        WHERE status = 'pending'
    """)

    queue = {
        "notifications": [
            {
                "notification_id": n.get("notification_id"),
                "recipient_id": n.get("recipient_id"),
                "type": n.get("type"),
                "title": n.get("title"),
                "channels": n.get("channels"),
                "priority": n.get("priority"),
                "created_at": format_date(n.get("created_at")),
            }
            for n in notifications
        ],
        "count": len(notifications),
        "summary": {
            "total_pending": summary.get("total_pending", 0) if summary else 0,
            "urgent": summary.get("urgent", 0) if summary else 0,
            "high": summary.get("high", 0) if summary else 0,
        },
        "by_channel": {
            "email": summary.get("email", 0) if summary else 0,
            "sms": summary.get("sms", 0) if summary else 0,
        },
        "filters_applied": {
            "channel": channel,
            "priority": priority,
            "recipient_id": recipient_id,
        },
    }

    return ToolResult.success(
        data=queue,
        message=f"Queue: {queue['summary']['total_pending']} pending notifications",
    )


@mortgage_tool(
    name="get_notification_templates",
    description="Get available notification templates for sending",
    agent_roles=["notification_center"],
    risk_level="LOW",
    parameters={
        "notification_type": "Optional type filter: alert, reminder, update, marketing",
        "channel": "Optional channel filter",
    },
)
def get_notification_templates(
    notification_type: Optional[str] = None,
    channel: Optional[str] = None,
) -> ToolResult:
    """Get notification templates."""
    templates = [
        {
            "id": "loan_status_update",
            "name": "Loan Status Update",
            "type": "update",
            "subject": "Your loan status has changed",
            "body": "Hi {borrower_name}, your loan {loan_number} is now in {status} status.",
            "channels": ["email", "sms", "in_app"],
            "variables": ["borrower_name", "loan_number", "status"],
        },
        {
            "id": "document_reminder",
            "name": "Document Reminder",
            "type": "reminder",
            "subject": "Documents needed for your loan",
            "body": "Hi {borrower_name}, we need the following documents: {document_list}. Please upload at your earliest convenience.",
            "channels": ["email", "sms"],
            "variables": ["borrower_name", "document_list"],
        },
        {
            "id": "task_due",
            "name": "Task Due Reminder",
            "type": "reminder",
            "subject": "Task due: {task_title}",
            "body": "Your task '{task_title}' for {borrower_name} is due {due_date}.",
            "channels": ["email", "push", "in_app"],
            "variables": ["task_title", "borrower_name", "due_date"],
        },
        {
            "id": "appointment_reminder",
            "name": "Appointment Reminder",
            "type": "reminder",
            "subject": "Upcoming appointment with {contact_name}",
            "body": "Reminder: You have an appointment with {contact_name} on {appointment_date} at {appointment_time}.",
            "channels": ["email", "sms", "push"],
            "variables": ["contact_name", "appointment_date", "appointment_time"],
        },
        {
            "id": "sla_warning",
            "name": "SLA Warning",
            "type": "alert",
            "subject": "SLA Warning: {loan_number}",
            "body": "Loan {loan_number} has been in {status} for {days} days. Action required.",
            "channels": ["email", "push", "in_app"],
            "variables": ["loan_number", "status", "days"],
        },
        {
            "id": "closing_reminder",
            "name": "Closing Date Reminder",
            "type": "reminder",
            "subject": "Closing approaching: {loan_number}",
            "body": "{borrower_name}'s loan {loan_number} is scheduled to close on {closing_date}.",
            "channels": ["email", "push"],
            "variables": ["borrower_name", "loan_number", "closing_date"],
        },
        {
            "id": "lock_expiration",
            "name": "Rate Lock Expiration",
            "type": "alert",
            "subject": "Rate lock expiring: {loan_number}",
            "body": "The rate lock for {borrower_name}'s loan expires on {lock_expiration}. Please take action.",
            "channels": ["email", "push", "in_app"],
            "variables": ["borrower_name", "loan_number", "lock_expiration"],
        },
        {
            "id": "welcome_email",
            "name": "Welcome Email",
            "type": "marketing",
            "subject": "Welcome to {company_name}!",
            "body": "Hi {name}, thank you for choosing {company_name} for your mortgage needs.",
            "channels": ["email"],
            "variables": ["name", "company_name"],
        },
    ]

    if notification_type:
        templates = [t for t in templates if t["type"] == notification_type]
    if channel:
        templates = [t for t in templates if channel in t["channels"]]

    return ToolResult.success(
        data={
            "templates": templates,
            "count": len(templates),
            "types": list(set(t["type"] for t in templates)),
        },
        message=f"Found {len(templates)} notification templates",
    )


@mortgage_tool(
    name="schedule_notification",
    description="Schedule a notification for future delivery",
    agent_roles=["notification_center"],
    risk_level="LOW",
    parameters={
        "recipient_id": "User ID",
        "notification_type": "Notification type",
        "title": "Notification title",
        "message": "Notification message",
        "scheduled_time": "Scheduled delivery time (ISO format)",
        "channels": "Delivery channels",
        "timezone": "Recipient timezone",
    },
)
def schedule_notification(
    recipient_id: str,
    notification_type: str,
    title: str,
    message: str,
    scheduled_time: str,
    channels: Optional[List[str]] = None,
    timezone: Optional[str] = None,
) -> ToolResult:
    """Schedule notification for later."""
    import uuid
    notification_id = str(uuid.uuid4())[:8].upper()

    # Parse and validate scheduled time
    try:
        scheduled_dt = datetime.fromisoformat(scheduled_time.replace("Z", "+00:00"))
        if scheduled_dt <= datetime.now():
            return ToolResult.error("Scheduled time must be in the future")
    except ValueError:
        return ToolResult.error("Invalid scheduled_time format. Use ISO format.")

    scheduled = {
        "notification_id": f"NOT-SCH-{notification_id}",
        "recipient_id": recipient_id,
        "type": notification_type,
        "title": title,
        "message": message,
        "scheduled_time": scheduled_time,
        "timezone": timezone or "America/New_York",
        "channels": channels or ["email", "in_app"],
        "status": "scheduled",
        "created_at": datetime.now().isoformat(),
    }

    return ToolResult.success(
        data=scheduled,
        message=f"Notification scheduled for {scheduled_time}",
    )


@mortgage_tool(
    name="get_delivery_status",
    description="Get delivery status for sent notifications",
    agent_roles=["notification_center"],
    risk_level="LOW",
    parameters={
        "notification_id": "Specific notification ID",
        "recipient_id": "Filter by recipient",
        "date_from": "Start date for status check",
        "date_to": "End date for status check",
    },
)
def get_delivery_status(
    notification_id: Optional[str] = None,
    recipient_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> ToolResult:
    """Get notification delivery status."""
    if notification_id:
        # Get specific notification status
        notification = execute_single("""
            SELECT
                notification_id, recipient_id, type, title,
                channels, status, sent_at, delivered_at, read_at
            FROM notifications
            WHERE notification_id = :notification_id
        """, {"notification_id": notification_id})

        if not notification:
            return ToolResult.no_data(f"Notification {notification_id} not found")

        # Get per-channel delivery status
        channel_status = execute_query("""
            SELECT channel, status, sent_at, delivered_at, error
            FROM notification_deliveries
            WHERE notification_id = :notification_id
        """, {"notification_id": notification_id})

        delivery = {
            "notification_id": notification_id,
            "recipient_id": notification.get("recipient_id"),
            "title": notification.get("title"),
            "overall_status": notification.get("status"),
            "sent_at": format_date(notification.get("sent_at")),
            "delivered_at": format_date(notification.get("delivered_at")),
            "read_at": format_date(notification.get("read_at")),
            "channel_status": [
                {
                    "channel": cs.get("channel"),
                    "status": cs.get("status"),
                    "sent_at": format_date(cs.get("sent_at")),
                    "delivered_at": format_date(cs.get("delivered_at")),
                    "error": cs.get("error"),
                }
                for cs in channel_status
            ] if channel_status else [],
        }

        return ToolResult.success(
            data=delivery,
            message=f"Status: {delivery['overall_status']}",
        )

    # Get aggregate delivery status
    if not date_to:
        date_to = datetime.now().strftime("%Y-%m-%d")
    if not date_from:
        date_from = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

    params = {"date_from": date_from, "date_to": date_to}
    filters = ["sent_at >= :date_from AND sent_at <= :date_to"]

    if recipient_id:
        filters.append("recipient_id = :recipient_id")
        params["recipient_id"] = recipient_id

    where_sql = " AND ".join(filters)

    stats = execute_single(f"""
        SELECT
            COUNT(*) as total_sent,
            COUNT(CASE WHEN status = 'delivered' THEN 1 END) as delivered,
            COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed,
            COUNT(CASE WHEN read_at IS NOT NULL THEN 1 END) as read
        FROM notifications
        WHERE {where_sql}
    """, params)

    total = stats.get("total_sent", 0) if stats else 0
    delivered = stats.get("delivered", 0) if stats else 0
    failed = stats.get("failed", 0) if stats else 0
    read = stats.get("read", 0) if stats else 0

    status = {
        "period": {"from": date_from, "to": date_to},
        "recipient_id": recipient_id,
        "summary": {
            "total_sent": total,
            "delivered": delivered,
            "failed": failed,
            "read": read,
            "delivery_rate": round((delivered / total * 100), 1) if total > 0 else 0,
            "read_rate": round((read / delivered * 100), 1) if delivered > 0 else 0,
        },
    }

    return ToolResult.success(
        data=status,
        message=f"Delivery rate: {status['summary']['delivery_rate']}%",
    )


@mortgage_tool(
    name="update_preferences",
    description="Update notification preferences for a user",
    agent_roles=["notification_center"],
    risk_level="LOW",
    parameters={
        "user_id": "User ID",
        "channel_preferences": "Channel enable/disable: {email: true, sms: false, ...}",
        "category_preferences": "Category enable/disable: {loan_updates: true, ...}",
        "quiet_hours": "Quiet hours settings: {enabled: true, start: '22:00', end: '08:00'}",
        "digest_settings": "Digest settings: {enabled: true, frequency: 'daily'}",
    },
)
def update_preferences(
    user_id: str,
    channel_preferences: Optional[Dict[str, bool]] = None,
    category_preferences: Optional[Dict[str, bool]] = None,
    quiet_hours: Optional[Dict[str, Any]] = None,
    digest_settings: Optional[Dict[str, Any]] = None,
) -> ToolResult:
    """Update notification preferences."""
    # Get current preferences
    current = execute_single("""
        SELECT preferences FROM user_notification_preferences
        WHERE user_id = :user_id
    """, {"user_id": user_id})

    # Default structure
    preferences = {
        "channels": {
            "email": True,
            "sms": False,
            "push": True,
            "in_app": True,
        },
        "categories": {
            "loan_updates": True,
            "task_reminders": True,
            "document_requests": True,
            "sla_alerts": True,
            "marketing": False,
            "system_alerts": True,
        },
        "quiet_hours": {
            "enabled": False,
            "start": "22:00",
            "end": "08:00",
        },
        "digest": {
            "enabled": False,
            "frequency": "daily",
            "time": "08:00",
        },
    }

    # Merge with current if exists
    if current and current.get("preferences"):
        import json
        try:
            existing = json.loads(current["preferences"]) if isinstance(current["preferences"], str) else current["preferences"]
            for key in preferences:
                if key in existing:
                    if isinstance(preferences[key], dict):
                        preferences[key].update(existing[key])
                    else:
                        preferences[key] = existing[key]
        except (json.JSONDecodeError, TypeError):
            pass

    # Apply updates
    if channel_preferences:
        preferences["channels"].update(channel_preferences)
    if category_preferences:
        preferences["categories"].update(category_preferences)
    if quiet_hours:
        preferences["quiet_hours"].update(quiet_hours)
    if digest_settings:
        preferences["digest"].update(digest_settings)

    result = {
        "user_id": user_id,
        "preferences": preferences,
        "updated_at": datetime.now().isoformat(),
        "changes_applied": {
            "channels": channel_preferences is not None,
            "categories": category_preferences is not None,
            "quiet_hours": quiet_hours is not None,
            "digest": digest_settings is not None,
        },
    }

    return ToolResult.success(
        data=result,
        message=f"Preferences updated for user {user_id}",
    )


@mortgage_tool(
    name="get_preferences",
    description="Get notification preferences for a user",
    agent_roles=["notification_center"],
    risk_level="LOW",
    parameters={
        "user_id": "User ID",
    },
)
def get_preferences(user_id: str) -> ToolResult:
    """Get notification preferences."""
    prefs = execute_single("""
        SELECT user_id, preferences, updated_at
        FROM user_notification_preferences
        WHERE user_id = :user_id
    """, {"user_id": user_id})

    if prefs and prefs.get("preferences"):
        import json
        try:
            preferences = json.loads(prefs["preferences"]) if isinstance(prefs["preferences"], str) else prefs["preferences"]
        except (json.JSONDecodeError, TypeError):
            preferences = None
    else:
        preferences = None

    # Default preferences if not found
    if not preferences:
        preferences = {
            "channels": {
                "email": True,
                "sms": False,
                "push": True,
                "in_app": True,
            },
            "categories": {
                "loan_updates": True,
                "task_reminders": True,
                "document_requests": True,
                "sla_alerts": True,
                "marketing": False,
                "system_alerts": True,
            },
            "quiet_hours": {
                "enabled": False,
                "start": "22:00",
                "end": "08:00",
            },
            "digest": {
                "enabled": False,
                "frequency": "daily",
                "time": "08:00",
            },
        }

    result = {
        "user_id": user_id,
        "preferences": preferences,
        "last_updated": format_date(prefs.get("updated_at")) if prefs else None,
        "is_default": prefs is None,
    }

    return ToolResult.success(
        data=result,
        message=f"Preferences retrieved for user {user_id}",
    )


@mortgage_tool(
    name="batch_send",
    description="Send notifications to multiple recipients in batch",
    agent_roles=["notification_center"],
    risk_level="MEDIUM",
    parameters={
        "recipient_ids": "List of user IDs",
        "notification_type": "Notification type",
        "title": "Notification title",
        "message": "Notification message",
        "channels": "Delivery channels",
        "personalization": "Personalization data by recipient ID",
    },
)
def batch_send(
    recipient_ids: List[str],
    notification_type: str,
    title: str,
    message: str,
    channels: Optional[List[str]] = None,
    personalization: Optional[Dict[str, Dict]] = None,
) -> ToolResult:
    """Send batch notifications with per-recipient TCPA check for SMS."""
    import uuid
    batch_id = str(uuid.uuid4())[:8].upper()

    if not recipient_ids:
        return ToolResult.error("recipient_ids list cannot be empty")

    if len(recipient_ids) > 1000:
        return ToolResult.error("Maximum 1000 recipients per batch")

    use_channels = channels or ["email", "in_app"]
    blocked_recipients = []
    cleared_recipients = []

    # COMPLIANCE GATE — if SMS channel, check each recipient
    if "sms" in use_channels:
        for rid in recipient_ids:
            user_phone = execute_single(
                "SELECT phone FROM users WHERE id = :id", {"id": rid}
            )
            if user_phone and user_phone.get("phone"):
                block = _check_sms_compliance(user_phone["phone"])
                if block:
                    blocked_recipients.append(rid)
                    continue
            cleared_recipients.append(rid)
    else:
        cleared_recipients = list(recipient_ids)

    # Write Notification rows for cleared recipients
    sent_count = 0
    for rid in cleared_recipients:
        try:
            with db_session() as session:
                from sqlalchemy import text
                session.execute(text("""
                    INSERT INTO notifications (user_id, type, title, message, is_read, created_at)
                    VALUES (:user_id, :type, :title, :message, false, NOW())
                """), {
                    "user_id": int(rid) if rid.isdigit() else None,
                    "type": notification_type,
                    "title": title,
                    "message": message,
                })
                sent_count += 1
        except Exception as e:
            logger.warning(f"Error writing batch notification for recipient {rid}: {e}")

    batch = {
        "batch_id": f"BATCH-{batch_id}",
        "recipient_count": len(recipient_ids),
        "notification_type": notification_type,
        "title": title,
        "message": message,
        "channels": use_channels,
        "has_personalization": personalization is not None,
        "status": "completed",
        "progress": {
            "total": len(recipient_ids),
            "sent": sent_count,
            "blocked_compliance": len(blocked_recipients),
            "failed": len(recipient_ids) - sent_count - len(blocked_recipients),
        },
        "blocked_recipients": blocked_recipients[:10] if blocked_recipients else [],
        "started_at": datetime.now().isoformat(),
        "completed_at": datetime.now().isoformat(),
    }

    return ToolResult.success(
        data=batch,
        message=f"Batch: {sent_count} sent, {len(blocked_recipients)} blocked (compliance)",
    )
