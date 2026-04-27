"""
POS Consent Reminder Service
=============================
Schedules and processes SMS reminders for borrowers who haven't completed
the consent flow after a voice-completed application.

Cadence:
  Day 1 — if magic link not opened
  Day 3 — if not submitted
  Day 7 — mark as abandoned, notify LO

Called by a periodic background task (cron or scheduler).
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger("pos_consent.reminders")


REMINDER_TEMPLATES = {
    "day1": (
        "Hi {first_name}, your mortgage application is ready for review. "
        "Tap to sign and submit: {link} — {lo_name}"
    ),
    "day3": (
        "Reminder: Your application from {lo_name} still needs your signature. "
        "It only takes 2 minutes: {link}"
    ),
    "day7_borrower": (
        "Final notice: Your mortgage application will expire soon. "
        "Please review and submit: {link} — {lo_name}"
    ),
}


def schedule_reminders(
    db: Session,
    application_id: int,
    borrower_phone: str,
    borrower_first_name: str,
    lo_name: str,
    magic_link: str,
) -> None:
    """Insert reminder rows for Day 1, Day 3, and Day 7."""
    now = datetime.now(timezone.utc)

    reminders = [
        ("pos_consent_reminder_day1", now + timedelta(days=1),
         REMINDER_TEMPLATES["day1"].format(
             first_name=borrower_first_name, link=magic_link, lo_name=lo_name)),
        ("pos_consent_reminder_day3", now + timedelta(days=3),
         REMINDER_TEMPLATES["day3"].format(
             first_name=borrower_first_name, link=magic_link, lo_name=lo_name)),
        ("pos_consent_reminder_day7", now + timedelta(days=7),
         REMINDER_TEMPLATES["day7_borrower"].format(
             first_name=borrower_first_name, link=magic_link, lo_name=lo_name)),
    ]

    for notification_type, send_at, message_text in reminders:
        try:
            db.execute(text("""
                INSERT INTO application_notifications
                (application_id, notification_type, channel, recipient_phone,
                 body, status, created_at)
                VALUES (:app_id, :ntype, 'sms', :phone, :msg, :status, NOW())
            """), {
                "app_id": application_id,
                "ntype": notification_type,
                "phone": borrower_phone,
                "msg": message_text,
                "status": f"scheduled:{send_at.isoformat()}",
            })
        except Exception as e:
            logger.warning("Failed to schedule reminder %s: %s", notification_type, e)

    db.flush()
    logger.info("Scheduled 3 consent reminders for application %d", application_id)


def process_pending_reminders(db: Session, batch_size: int = 50) -> int:
    """
    Process due reminders. Called by a periodic background task.

    Returns the number of reminders processed.
    """
    from database.enums import ApplicationStatus

    now = datetime.now(timezone.utc)

    # Find due, unsent reminders
    # status stores "scheduled:{iso_timestamp}" — extract and compare
    rows = db.execute(text("""
        SELECT an.id, an.application_id, an.notification_type, an.channel,
               an.recipient_phone, an.body,
               ba.status as app_status, an.status as notif_status
        FROM application_notifications an
        JOIN borrower_applications ba ON ba.id = an.application_id
        WHERE an.sent_at IS NULL
          AND an.notification_type LIKE 'pos_consent_reminder_%%'
          AND an.status LIKE 'scheduled:%%'
        ORDER BY an.created_at ASC
        LIMIT :batch_size
    """), {"batch_size": batch_size}).fetchall()

    processed = 0
    for row in rows:
        notification_id = row[0]
        application_id = row[1]
        notification_type = row[2]
        recipient_phone = row[4]
        message_text = row[5]
        app_status = row[6]
        notif_status = row[7] or ""

        # Parse scheduled time from status field
        if notif_status.startswith("scheduled:"):
            try:
                scheduled_time = datetime.fromisoformat(notif_status.split(":", 1)[1])
                if scheduled_time > now:
                    continue
            except (ValueError, IndexError):
                pass

        # Skip if application already submitted or no longer pending
        if app_status != ApplicationStatus.PENDING_CONSENT.value:
            db.execute(text(
                "UPDATE application_notifications SET sent_at = :now, "
                "status = 'skipped:' || :app_status "
                "WHERE id = :id"
            ), {"now": now, "id": notification_id, "app_status": app_status})
            processed += 1
            continue

        # Day 7 = mark abandoned
        if notification_type == "pos_consent_reminder_day7":
            _handle_abandonment(db, application_id, notification_id, now)
            processed += 1
            continue

        # Send SMS
        try:
            from services.notification_service import NotificationService
            ns = NotificationService()
            result = ns.send_sms(
                to_phone=recipient_phone,
                message=message_text,
                skip_consent_check=True,
            )

            db.execute(text(
                "UPDATE application_notifications SET sent_at = :now WHERE id = :id"
            ), {"now": now, "id": notification_id})

            # Increment reminder count on application
            db.execute(text(
                "UPDATE borrower_applications SET consent_reminder_count = "
                "COALESCE(consent_reminder_count, 0) + 1 WHERE id = :app_id"
            ), {"app_id": application_id})

            processed += 1
        except Exception as e:
            logger.exception("Failed to send reminder %d: %s", notification_id, e)

    if processed > 0:
        db.commit()

    return processed


def _handle_abandonment(
    db: Session,
    application_id: int,
    notification_id: int,
    now: datetime,
) -> None:
    """Mark application as abandoned after Day 7 with no consent."""
    from database.enums import ApplicationStatus

    # Send the Day 7 SMS
    try:
        row = db.execute(text(
            "SELECT recipient_phone, body FROM application_notifications WHERE id = :id"
        ), {"id": notification_id}).fetchone()

        if row:
            from services.notification_service import NotificationService
            ns = NotificationService()
            ns.send_sms(to_phone=row[0], message=row[1], skip_consent_check=True)
    except Exception as e:
        logger.warning("Day 7 SMS failed: %s", e)

    # Transition to EXPIRED
    db.execute(text(
        "UPDATE borrower_applications SET status = :status, "
        "updated_at = :now WHERE id = :app_id AND status = :pending"
    ), {
        "status": ApplicationStatus.EXPIRED.value,
        "now": now,
        "app_id": application_id,
        "pending": ApplicationStatus.PENDING_CONSENT.value,
    })

    # Mark notification as sent
    db.execute(text(
        "UPDATE application_notifications SET sent_at = :now WHERE id = :id"
    ), {"now": now, "id": notification_id})

    # Write audit event
    from services.pos_consent_service import _write_application_event
    _write_application_event(db, application_id, "consent_abandoned_day7", {
        "reason": "No consent captured within 7 days of voice completion",
    })

    # Notify LO
    _notify_lo_of_abandonment(db, application_id)

    logger.info("Application %d marked as abandoned (Day 7 consent timeout)", application_id)


def _notify_lo_of_abandonment(db: Session, application_id: int) -> None:
    """Send the LO a notification about the abandoned consent."""
    try:
        row = db.execute(text("""
            SELECT ba.owner_id, ba.borrower_first_name, ba.borrower_last_name,
                   u.email as lo_email
            FROM borrower_applications ba
            LEFT JOIN users u ON u.id = ba.owner_id
            WHERE ba.id = :app_id
        """), {"app_id": application_id}).fetchone()

        if row and row[3]:
            borrower_name = f"{row[1] or ''} {row[2] or ''}".strip() or "Borrower"
            logger.info(
                "LO notification: %s's application %d abandoned consent flow",
                borrower_name, application_id,
            )
            # TODO: Wire to notification_service.send_email() for LO alert
    except Exception as e:
        logger.warning("Failed to notify LO of abandonment: %s", e)
