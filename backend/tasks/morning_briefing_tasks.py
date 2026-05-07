"""
Morning Briefing Celery Tasks

Dispatch: runs every 15 min, finds users due for briefings.
Generate: builds one briefing per user (data + AI + email + send).
Cleanup: deletes briefings older than 90 days.
"""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@contextmanager
def _get_scoped_session(org_id=None):
    """Yield a DB session that always closes, with optional tenant scoping."""
    from db import SessionLocal
    from sqlalchemy import text
    db = SessionLocal()
    try:
        if org_id is not None:
            db.execute(text("SET app.current_tenant = :org_id"), {"org_id": str(org_id)})
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _get_all_briefing_candidates(db):
    """Get all active users with briefing_enabled = True."""
    from sqlalchemy import text as sa_text
    rows = db.execute(sa_text("""
        SELECT id, timezone, briefing_hour, permission_role, organization_id
        FROM users
        WHERE is_active = TRUE
          AND COALESCE(briefing_enabled, TRUE) = TRUE
    """)).fetchall()
    return rows


@celery_app.task(name="tasks.morning_briefing_tasks.dispatch_briefings")
def dispatch_briefings():
    """
    Runs every 15 minutes via Beat. Checks which users are due for a briefing
    based on their timezone and briefing_hour.
    """
    from sqlalchemy import text as sa_text

    try:
        now_utc = datetime.now(timezone.utc)

        with _get_scoped_session() as db:
            candidates = _get_all_briefing_candidates(db)

        enqueued = 0
        individual_idx = 0
        manager_idx = 0

        for row in candidates:
            user_id, user_tz, briefing_hour, perm_role, org_id = (
                row[0], row[1] or "America/Chicago", row[2] or 7, row[3] or "sales", row[4],
            )

            try:
                tz = ZoneInfo(user_tz)
            except Exception:
                tz = ZoneInfo("America/Chicago")

            local_now = now_utc.astimezone(tz)
            local_hour = local_now.hour
            local_date = local_now.date()

            if local_hour != briefing_hour:
                continue

            # Check if briefing already exists for today
            try:
                with _get_scoped_session() as check_db:
                    exists = check_db.execute(sa_text("""
                        SELECT 1 FROM morning_briefings
                        WHERE user_id = :uid AND briefing_date = :bdate
                        LIMIT 1
                    """), {"uid": user_id, "bdate": local_date}).fetchone()

                if exists:
                    continue
            except Exception:
                continue

            # Determine level
            is_leadership = perm_role in ("leadership", "admin", "site_admin", "platform_admin")
            is_manager = perm_role in ("management", "branch_manager", "regional_manager")

            if is_leadership:
                level = "leadership"
            elif is_manager:
                # Check if they have direct reports
                try:
                    with _get_scoped_session() as rpt_db:
                        has_reports = rpt_db.execute(sa_text("""
                            SELECT 1 FROM users
                            WHERE manager_id = :uid AND is_active = TRUE
                            LIMIT 1
                        """), {"uid": user_id}).fetchone()
                    level = "manager" if has_reports else "individual"
                except Exception:
                    level = "individual"
            else:
                level = "individual"

            # Stagger: individuals first, managers/leadership delayed 5 min
            if level == "individual":
                delay = individual_idx * 2
                individual_idx += 1
            else:
                delay = 300 + manager_idx * 2
                manager_idx += 1

            generate_user_briefing.apply_async(
                args=[user_id, local_date.isoformat(), level],
                countdown=delay,
            )
            enqueued += 1

        logger.info("Briefing dispatch: enqueued %d users", enqueued)
        return {"enqueued": enqueued}

    except Exception as e:
        logger.error("Briefing dispatch failed: %s", e)
        return {"error": str(e)}


@celery_app.task(
    name="tasks.morning_briefing_tasks.generate_user_briefing",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    queue="ai_tasks",
)
def generate_user_briefing(self, user_id: int, briefing_date_str: str, briefing_level: str):
    """Generate and deliver a single user's morning briefing."""
    import time
    from database.models.morning_briefing import MorningBriefing
    from services.morning_briefing_service import MorningBriefingService
    from templates.morning_briefing_email import render_briefing_email

    start_time = time.time()
    briefing_date = date.fromisoformat(briefing_date_str)

    # First, look up the user's org_id to establish tenant context.
    # This initial query is un-scoped (users table may not have RLS).
    with _get_scoped_session() as lookup_db:
        from sqlalchemy import text as sa_text
        user_row = lookup_db.execute(
            sa_text("SELECT id, organization_id FROM users WHERE id = :uid"),
            {"uid": user_id},
        ).fetchone()
        if not user_row:
            logger.warning("Briefing: user %d not found", user_id)
            return {"error": "user_not_found"}
        org_id = user_row[1]

    if not org_id:
        logger.warning("Briefing: user %d has no organization_id", user_id)
        return {"error": "no_organization"}

    # Use tenant-scoped session for all data queries (RLS enforced)
    with _get_scoped_session(org_id) as db:
        try:
            from database.models import User
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                logger.warning("Briefing: user %d not found in tenant session", user_id)
                return {"error": "user_not_found"}

            # Check for existing briefing (race condition guard)
            existing = db.query(MorningBriefing).filter(
                MorningBriefing.user_id == user_id,
                MorningBriefing.briefing_date == briefing_date,
            ).first()
            if existing:
                logger.info("Briefing already exists for user %d on %s", user_id, briefing_date_str)
                return {"status": "already_exists"}

            # Create pending record
            briefing = MorningBriefing(
                organization_id=org_id,
                user_id=user_id,
                briefing_date=briefing_date,
                briefing_level=briefing_level,
                status="generating",
            )
            db.add(briefing)
            try:
                db.flush()
            except Exception as flush_exc:
                db.rollback()
                # UniqueConstraint violation means another worker already created it
                from sqlalchemy.exc import IntegrityError
                if isinstance(flush_exc, IntegrityError):
                    logger.info("Briefing already exists (concurrent) for user %d on %s", user_id, briefing_date_str)
                    return {"status": "already_exists"}
                raise

            # Load user preferences (NULL = all defaults)
            prefs = MorningBriefingService.load_preferences(user)

            # Gather data
            service = MorningBriefingService()
            ctx = service.build_context(db, user, briefing_date, prefs)

            briefing.briefing_data = {
                "pipeline": ctx.pipeline,
                "at_risk": ctx.at_risk,
                "stale_leads": ctx.stale_leads,
                "appointments": ctx.appointments,
                "conditions": ctx.conditions,
                "yesterday": ctx.yesterday,
            }
            if ctx.team:
                briefing.team_data = ctx.team

            # Generate AI narrative
            ai_start = time.time()
            narrative = service.generate_narrative(ctx, prefs.ai_tone, prefs)
            ai_duration = (time.time() - ai_start) * 1000
            briefing.ai_narrative = narrative

            # Render email HTML
            user_name = user.full_name if hasattr(user, "full_name") else (
                f"{user.first_name or ''} {user.last_name or ''}".strip() or "there"
            )

            # Load white-label branding (if configured)
            branding = {}
            wl_config = None
            try:
                from database.models.white_label_config import WhiteLabelConfig
                wl_config = db.query(WhiteLabelConfig).filter(
                    WhiteLabelConfig.organization_id == user.organization_id,
                    WhiteLabelConfig.is_active == True,
                    WhiteLabelConfig.setting_type.is_(None),
                ).first()
                if wl_config:
                    branding = {
                        "company_name": wl_config.company_name or "The Tim Loss Team",
                        "logo_url": wl_config.logo_url,
                        "primary_color": wl_config.primary_color or "#218d8d",
                        "secondary_color": wl_config.secondary_color,
                    }
            except Exception as e:
                logger.warning("Failed to load white-label config for org %s: %s", user.organization_id, e)

            html = render_briefing_email(
                user_name=user_name,
                briefing_date=briefing_date,
                level=briefing_level,
                ai_narrative=narrative,
                pipeline=ctx.pipeline,
                at_risk=ctx.at_risk,
                stale_leads=ctx.stale_leads,
                appointments=ctx.appointments,
                conditions=ctx.conditions,
                yesterday=ctx.yesterday,
                team=ctx.team,
                dashboard_snapshot=ctx.dashboard_snapshot,
                **branding,
            )
            briefing.html_content = html

            # Send email
            email_sent = False
            try:
                _send_briefing_email(
                    user.email, user_name, briefing_date, briefing_level, html, ctx.pipeline,
                    from_name_override=branding.get("company_name"),
                    from_email_override=wl_config.email_from_address if wl_config else None,
                )
                briefing.email_sent_at = datetime.now(timezone.utc)
                email_sent = True
            except Exception as e:
                logger.error("Briefing email send failed for user %d: %s", user_id, e)

            briefing.status = "delivered" if email_sent else "failed"
            briefing.updated_at = datetime.now(timezone.utc)

            # Send push notification that briefing is ready
            try:
                from routes.push_notification_routes import notify_briefing_ready
                at_risk_count = len(ctx.at_risk) if ctx.at_risk else 0
                active_count = ctx.pipeline.get("active_count", 0) if ctx.pipeline else 0
                notify_briefing_ready(db, user_id, active_count, at_risk_count)
            except Exception as push_err:
                logger.debug("Push notification skipped: %s", push_err)

            db.commit()

            total_duration = (time.time() - start_time) * 1000
            logger.info(
                "briefing.generate.complete user_id=%d level=%s ai_ms=%.0f total_ms=%.0f email=%s",
                user_id, briefing_level, ai_duration, total_duration, email_sent,
            )

            return {"status": briefing.status, "briefing_id": briefing.id}

        except Exception as e:
            db.rollback()
            logger.error("Briefing generation failed for user %d: %s", user_id, e)
            try:
                self.retry(exc=e)
            except self.MaxRetriesExceededError:
                # Mark as failed after all retries
                try:
                    fail_briefing = db.query(MorningBriefing).filter(
                        MorningBriefing.user_id == user_id,
                        MorningBriefing.briefing_date == briefing_date,
                    ).first()
                    if fail_briefing:
                        fail_briefing.status = "failed"
                        fail_briefing.updated_at = datetime.now(timezone.utc)
                        db.commit()
                except Exception as mark_err:
                    logger.error("Failed to mark briefing as failed for user %d: %s", user_id, mark_err)
                return {"error": str(e)}


def _send_briefing_email(
    to_email: str, user_name: str, briefing_date: date,
    level: str, html: str, pipeline: dict,
    from_name_override: str = None,
    from_email_override: str = None,
):
    """Send briefing email via SendGrid / notification service."""
    import sendgrid
    from sendgrid.helpers.mail import Mail, Email, To, Content

    api_key = os.getenv("SENDGRID_API_KEY")
    if not api_key:
        logger.warning("SENDGRID_API_KEY not set; skipping email send")
        return

    active = pipeline.get("active_count", 0)
    volume = pipeline.get("total_volume", 0)
    short_date = briefing_date.strftime("%b %d")

    level_labels = {"individual": f"{active} active loans", "manager": "team briefing", "leadership": f"${volume / 1_000_000:.1f}M pipeline"}
    subject = f"Your Morning Briefing — {short_date} — {level_labels.get(level, '')}"

    from_email = from_email_override or os.getenv("BRIEFING_FROM_EMAIL", "briefing@perenniaai.com")
    from_name = from_name_override or os.getenv("SENDGRID_FROM_NAME", "The Tim Loss Team")

    message = Mail(
        from_email=Email(from_email, from_name),
        to_emails=To(to_email),
        subject=subject,
        html_content=Content("text/html", html),
    )

    sg = sendgrid.SendGridAPIClient(api_key=api_key)
    response = sg.send(message)

    if response.status_code >= 400:
        raise Exception(f"SendGrid returned {response.status_code}")

    logger.info("Briefing email sent to %s (status %d)", to_email, response.status_code)


@celery_app.task(name="tasks.morning_briefing_tasks.cleanup_old_briefings")
def cleanup_old_briefings(retention_days: int = 90):
    """Delete briefings older than retention_days."""
    from sqlalchemy import text as sa_text

    try:
        cutoff = date.today() - timedelta(days=retention_days)
        with _get_scoped_session() as db:
            result = db.execute(sa_text("""
                DELETE FROM morning_briefings WHERE briefing_date < :cutoff
            """), {"cutoff": cutoff})
            db.commit()
            deleted = result.rowcount
        logger.info("Briefing cleanup: deleted %d rows older than %s", deleted, cutoff)
        return {"deleted": deleted}
    except Exception as e:
        logger.error("Briefing cleanup failed: %s", e)
        return {"error": str(e)}
