import logging
import threading
import time
from datetime import datetime, timezone, timedelta
from sqlalchemy import text

logger = logging.getLogger(__name__)

_stop_event: threading.Event | None = None


def expire_stale_tasks(hours=24) -> int:
    from db import SessionLocal
    session = SessionLocal()
    try:
        result = session.execute(
            text("""
                UPDATE sms_tasks
                SET status = 'expired', updated_at = NOW()
                WHERE status = 'pending'
                  AND created_at < NOW() - make_interval(hours => :hours)
            """),
            {"hours": int(hours)}
        )
        count = result.rowcount
        session.commit()
        if count > 0:
            logger.info(f"Expired {count} stale SMS tasks (older than {hours}h)")
        return count
    except Exception as e:
        session.rollback()
        logger.exception(f"Failed to expire stale SMS tasks: {e}")
        return 0
    finally:
        session.close()


def cleanup_old_audit_logs(days=90) -> int:
    from db import SessionLocal
    session = SessionLocal()
    total_deleted = 0
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        while True:
            result = session.execute(
                text("""
                    DELETE FROM sms_ai_audit_log
                    WHERE id IN (
                        SELECT id FROM sms_ai_audit_log
                        WHERE created_at < :cutoff
                        LIMIT 10000
                    )
                """),
                {"cutoff": cutoff}
            )
            batch = result.rowcount
            session.commit()
            total_deleted += batch
            if batch < 10000:
                break
        if total_deleted > 0:
            logger.info(f"Cleaned up {total_deleted} audit log entries older than {days} days")
        return total_deleted
    except Exception as e:
        session.rollback()
        logger.exception(f"Failed to cleanup audit logs: {e}")
        return total_deleted
    finally:
        session.close()


def cleanup_stale_patterns(min_uses=5, max_reject_rate=0.9) -> int:
    from db import SessionLocal
    session = SessionLocal()
    try:
        result = session.execute(
            text("""
                DELETE FROM sms_response_patterns
                WHERE times_used >= :min_uses
                  AND (times_rejected::float / times_used) > :max_reject_rate
            """),
            {"min_uses": min_uses, "max_reject_rate": max_reject_rate}
        )
        count = result.rowcount
        session.commit()
        if count > 0:
            logger.info(f"Cleaned up {count} stale response patterns (reject rate > {max_reject_rate})")
        return count
    except Exception as e:
        session.rollback()
        logger.exception(f"Failed to cleanup stale patterns: {e}")
        return 0
    finally:
        session.close()


def start_background_expiry(interval_seconds=3600):
    global _stop_event
    _stop_event = threading.Event()
    stop = _stop_event

    def _loop():
        logger.info(f"SMS task expiry background thread started (interval={interval_seconds}s)")
        while not stop.wait(interval_seconds):
            try:
                expire_stale_tasks()
            except Exception as e:
                logger.exception(f"Background expiry error: {e}")

    thread = threading.Thread(target=_loop, daemon=True, name="sms-task-expiry")
    thread.start()
    return thread, stop


def run_all_maintenance():
    expired = expire_stale_tasks()
    audit_deleted = cleanup_old_audit_logs()
    patterns_deleted = cleanup_stale_patterns()
    logger.info(
        f"SMS maintenance complete: {expired} tasks expired, "
        f"{audit_deleted} audit logs cleaned, {patterns_deleted} patterns removed"
    )
