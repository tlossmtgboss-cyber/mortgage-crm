"""
PURL Event Processor
Perennia AI - Mortgage CRM

Processes events from the PURL events outbox table and dispatches
them to appropriate handlers for:
- Email notifications
- Webhook delivery
- Internal workflow triggers
- Analytics tracking

Run as a background worker:
    python purl_event_processor.py run
    python purl_event_processor.py run --once  (single batch)

Or schedule via cron:
    * * * * * cd /path/to/backend && python jobs/purl_event_processor.py run --once
"""

import os
import sys
import json
import time
import signal
import logging
import argparse
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass
from enum import Enum

# Add parent directory for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.orm import Session

# Import database session
from database import SessionLocal

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

class EventProcessorConfig:
    """Configuration for the event processor."""
    BATCH_SIZE = 50
    POLL_INTERVAL_SECONDS = 5
    MAX_RETRIES = 3
    RETRY_DELAY_MINUTES = [1, 5, 30]  # Exponential backoff
    DEAD_LETTER_AFTER_RETRIES = True
    WEBHOOK_TIMEOUT_SECONDS = 30


# =============================================================================
# EVENT HANDLERS
# =============================================================================

class EventHandlerRegistry:
    """Registry for event handlers."""

    def __init__(self):
        self._handlers: Dict[str, List[Callable]] = {}

    def register(self, event_key: str, handler: Callable):
        """Register a handler for an event type."""
        if event_key not in self._handlers:
            self._handlers[event_key] = []
        self._handlers[event_key].append(handler)

    def get_handlers(self, event_key: str) -> List[Callable]:
        """Get handlers for an event type."""
        return self._handlers.get(event_key, [])

    def list_events(self) -> List[str]:
        """List all registered event types."""
        return list(self._handlers.keys())


# Global handler registry
handler_registry = EventHandlerRegistry()


def event_handler(event_key: str):
    """Decorator to register an event handler."""
    def decorator(func):
        handler_registry.register(event_key, func)
        return func
    return decorator


# =============================================================================
# BUILT-IN EVENT HANDLERS
# =============================================================================

@event_handler("workspace_created")
def handle_workspace_created(event: Dict[str, Any], db: Session) -> bool:
    """Handle workspace creation event."""
    payload = event.get("payload", {})
    workspace_id = payload.get("workspace_id")
    org_id = event.get("organization_id")

    logger.info(f"Processing workspace_created: workspace={workspace_id}")

    # Create welcome notification for team
    try:
        # Get workspace details
        ws_result = db.execute(text("""
            SELECT display_name, slug FROM purl_workspaces WHERE id = :ws_id
        """), {"ws_id": workspace_id}).fetchone()

        if ws_result:
            # Get team members assigned to workspace
            members = db.execute(text("""
                SELECT user_id FROM purl_workspace_members
                WHERE workspace_id = :ws_id
            """), {"ws_id": workspace_id}).fetchall()

            # Create notifications for team members
            for member in members:
                db.execute(text("""
                    INSERT INTO notifications (user_id, type, title, message, link, created_at)
                    VALUES (:user_id, 'workspace_assigned', 'New Workspace Assigned',
                            :message, :link, CURRENT_TIMESTAMP)
                """), {
                    "user_id": member.user_id,
                    "message": f"You have been assigned to workspace: {ws_result.display_name}",
                    "link": f"/workspaces/{ws_result.slug}"
                })

        db.commit()
        return True

    except Exception as e:
        logger.error(f"Error in workspace_created handler: {e}")
        db.rollback()
        return False


@event_handler("application_started")
def handle_application_started(event: Dict[str, Any], db: Session) -> bool:
    """Handle application started event."""
    payload = event.get("payload", {})
    workspace_id = event.get("workspace_id")
    application_id = payload.get("application_id")

    logger.info(f"Processing application_started: app={application_id}")

    try:
        # Get workspace and team info
        ws = db.execute(text("""
            SELECT pw.display_name, pw.slug,
                   pc.email, pc.first_name
            FROM purl_workspaces pw
            LEFT JOIN purl_contacts pc ON pc.workspace_id = pw.id AND pc.is_primary = true
            WHERE pw.id = :ws_id
        """), {"ws_id": workspace_id}).fetchone()

        if ws:
            # Notify assigned team members
            members = db.execute(text("""
                SELECT wm.user_id, u.email
                FROM purl_workspace_members wm
                JOIN users u ON u.id = wm.user_id
                WHERE wm.workspace_id = :ws_id
            """), {"ws_id": workspace_id}).fetchall()

            for member in members:
                db.execute(text("""
                    INSERT INTO notifications (user_id, type, title, message, link, created_at)
                    VALUES (:user_id, 'application_started', 'Application Started',
                            :message, :link, CURRENT_TIMESTAMP)
                """), {
                    "user_id": member.user_id,
                    "message": f"{ws.first_name or 'Borrower'} started their loan application",
                    "link": f"/workspaces/{ws.slug}/application"
                })

        db.commit()
        return True

    except Exception as e:
        logger.error(f"Error in application_started handler: {e}")
        db.rollback()
        return False


@event_handler("application_submitted")
def handle_application_submitted(event: Dict[str, Any], db: Session) -> bool:
    """Handle application submission event."""
    payload = event.get("payload", {})
    workspace_id = event.get("workspace_id")
    application_id = payload.get("application_id")
    loan_id = payload.get("loan_id")

    logger.info(f"Processing application_submitted: app={application_id}, loan={loan_id}")

    try:
        # Get workspace and contact info
        ws = db.execute(text("""
            SELECT pw.display_name, pw.slug,
                   pc.email, pc.first_name, pc.last_name
            FROM purl_workspaces pw
            LEFT JOIN purl_contacts pc ON pc.workspace_id = pw.id AND pc.is_primary = true
            WHERE pw.id = :ws_id
        """), {"ws_id": workspace_id}).fetchone()

        if ws and ws.email:
            # Generate a new token for the borrower to access their portal
            # Since tokens are hashed and can't be retrieved, we need to create a fresh one
            access_token = None
            try:
                from services.purl_token_service import PURLTokenService
                from models.purl import TokenScope

                # Get organization_id from workspace
                org_result = db.execute(text("""
                    SELECT organization_id FROM purl_workspaces WHERE id = :ws_id
                """), {"ws_id": workspace_id}).fetchone()

                if org_result:
                    token_service = PURLTokenService(db)
                    _, access_token = token_service.create_token(
                        organization_id=org_result.organization_id,
                        workspace_id=workspace_id,
                        scope=TokenScope.WRITE,
                        expires_in_days=30  # Token valid for 30 days
                    )
                    logger.info(f"Created new portal access token for workspace {workspace_id}")
            except Exception as token_error:
                logger.warning(f"Could not create portal token: {token_error}")

            # Queue email to borrower
            queue_email(
                db=db,
                to_email=ws.email,
                template="application_submitted",
                context={
                    "first_name": ws.first_name,
                    "workspace_slug": ws.slug,
                    "loan_id": loan_id,
                    "token": access_token  # Include token for portal access
                }
            )

        # Notify team
        members = db.execute(text("""
            SELECT wm.user_id FROM purl_workspace_members wm
            WHERE wm.workspace_id = :ws_id
        """), {"ws_id": workspace_id}).fetchall()

        for member in members:
            db.execute(text("""
                INSERT INTO notifications (user_id, type, title, message, link, created_at)
                VALUES (:user_id, 'application_submitted', 'Application Submitted',
                        :message, :link, CURRENT_TIMESTAMP)
            """), {
                "user_id": member.user_id,
                "message": f"{ws.first_name} {ws.last_name} submitted their application",
                "link": f"/loans/{loan_id}"
            })

        db.commit()
        return True

    except Exception as e:
        logger.error(f"Error in application_submitted handler: {e}")
        db.rollback()
        return False


@event_handler("document_uploaded")
def handle_document_uploaded(event: Dict[str, Any], db: Session) -> bool:
    """Handle document upload event."""
    payload = event.get("payload", {})
    workspace_id = event.get("workspace_id")
    document_id = payload.get("document_id")
    document_type = payload.get("document_type")

    logger.info(f"Processing document_uploaded: doc={document_id}")

    try:
        # Get workspace info
        ws = db.execute(text("""
            SELECT pw.slug, pc.first_name
            FROM purl_workspaces pw
            LEFT JOIN purl_contacts pc ON pc.workspace_id = pw.id AND pc.is_primary = true
            WHERE pw.id = :ws_id
        """), {"ws_id": workspace_id}).fetchone()

        if ws:
            # Notify team members
            members = db.execute(text("""
                SELECT user_id FROM purl_workspace_members WHERE workspace_id = :ws_id
            """), {"ws_id": workspace_id}).fetchall()

            for member in members:
                db.execute(text("""
                    INSERT INTO notifications (user_id, type, title, message, link, created_at)
                    VALUES (:user_id, 'document_uploaded', 'Document Uploaded',
                            :message, :link, CURRENT_TIMESTAMP)
                """), {
                    "user_id": member.user_id,
                    "message": f"{ws.first_name or 'Borrower'} uploaded: {document_type or 'document'}",
                    "link": f"/workspaces/{ws.slug}/documents"
                })

        db.commit()
        return True

    except Exception as e:
        logger.error(f"Error in document_uploaded handler: {e}")
        db.rollback()
        return False


@event_handler("task_completed")
def handle_task_completed(event: Dict[str, Any], db: Session) -> bool:
    """Handle task completion event."""
    payload = event.get("payload", {})
    workspace_id = event.get("workspace_id")
    task_id = payload.get("task_id")

    logger.info(f"Processing task_completed: task={task_id}")

    try:
        # Check for milestone completion
        task = db.execute(text("""
            SELECT t.title, t.loan_id, pw.slug
            FROM purl_tasks t
            JOIN purl_workspaces pw ON pw.id = t.workspace_id
            WHERE t.id = :task_id
        """), {"task_id": task_id}).fetchone()

        if task and task.loan_id:
            # Check if all tasks for a milestone are complete
            check_milestone_completion(db, task.loan_id)

        db.commit()
        return True

    except Exception as e:
        logger.error(f"Error in task_completed handler: {e}")
        db.rollback()
        return False


@event_handler("milestone_completed")
def handle_milestone_completed(event: Dict[str, Any], db: Session) -> bool:
    """Handle milestone completion event."""
    payload = event.get("payload", {})
    workspace_id = event.get("workspace_id")
    milestone_id = payload.get("milestone_id")
    milestone_name = payload.get("milestone_name")

    logger.info(f"Processing milestone_completed: milestone={milestone_id}")

    try:
        # Get workspace and borrower info
        ws = db.execute(text("""
            SELECT pw.slug, pc.email, pc.first_name
            FROM purl_workspaces pw
            LEFT JOIN purl_contacts pc ON pc.workspace_id = pw.id AND pc.is_primary = true
            WHERE pw.id = :ws_id
        """), {"ws_id": workspace_id}).fetchone()

        if ws and ws.email:
            # Email borrower about milestone
            queue_email(
                db=db,
                to_email=ws.email,
                template="milestone_completed",
                context={
                    "first_name": ws.first_name,
                    "milestone_name": milestone_name,
                    "workspace_slug": ws.slug
                }
            )

        db.commit()
        return True

    except Exception as e:
        logger.error(f"Error in milestone_completed handler: {e}")
        db.rollback()
        return False


@event_handler("message_received")
def handle_message_received(event: Dict[str, Any], db: Session) -> bool:
    """Handle new message from borrower."""
    payload = event.get("payload", {})
    workspace_id = event.get("workspace_id")
    message_id = payload.get("message_id")

    logger.info(f"Processing message_received: message={message_id}")

    try:
        # Get workspace info
        ws = db.execute(text("""
            SELECT pw.slug, pc.first_name, pc.last_name
            FROM purl_workspaces pw
            LEFT JOIN purl_contacts pc ON pc.workspace_id = pw.id AND pc.is_primary = true
            WHERE pw.id = :ws_id
        """), {"ws_id": workspace_id}).fetchone()

        if ws:
            # Notify team members
            members = db.execute(text("""
                SELECT user_id FROM purl_workspace_members WHERE workspace_id = :ws_id
            """), {"ws_id": workspace_id}).fetchall()

            for member in members:
                db.execute(text("""
                    INSERT INTO notifications (user_id, type, title, message, link, created_at)
                    VALUES (:user_id, 'borrower_message', 'New Message from Borrower',
                            :message, :link, CURRENT_TIMESTAMP)
                """), {
                    "user_id": member.user_id,
                    "message": f"{ws.first_name} {ws.last_name} sent a message",
                    "link": f"/workspaces/{ws.slug}/messages"
                })

        db.commit()
        return True

    except Exception as e:
        logger.error(f"Error in message_received handler: {e}")
        db.rollback()
        return False


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def queue_email(db: Session, to_email: str, template: str, context: Dict[str, Any]):
    """Queue an email for sending."""
    try:
        db.execute(text("""
            INSERT INTO email_queue (to_email, template, context, status, created_at)
            VALUES (:to_email, :template, :context, 'pending', CURRENT_TIMESTAMP)
        """), {
            "to_email": to_email,
            "template": template,
            "context": json.dumps(context)
        })
    except Exception as e:
        # Email queue table may not exist, log and continue
        logger.warning(f"Could not queue email (table may not exist): {e}")


def check_milestone_completion(db: Session, loan_id: int):
    """Check if all tasks for a milestone are complete."""
    # Get milestones with all tasks complete
    completed_milestones = db.execute(text("""
        SELECT lm.id, md.name
        FROM purl_loan_milestones lm
        JOIN purl_milestone_definitions md ON md.id = lm.milestone_definition_id
        WHERE lm.loan_id = :loan_id
        AND lm.status = 'in_progress'
        AND NOT EXISTS (
            SELECT 1 FROM purl_tasks t
            WHERE t.loan_id = :loan_id
            AND t.milestone_id = lm.id
            AND t.status != 'completed'
        )
    """), {"loan_id": loan_id}).fetchall()

    for milestone in completed_milestones:
        # Update milestone status
        db.execute(text("""
            UPDATE purl_loan_milestones
            SET status = 'completed', completed_at = CURRENT_TIMESTAMP
            WHERE id = :milestone_id
        """), {"milestone_id": milestone.id})

        logger.info(f"Auto-completed milestone: {milestone.name}")


def deliver_webhook(url: str, payload: Dict[str, Any], headers: Dict[str, str] = None) -> bool:
    """Deliver webhook to external URL."""
    import requests

    try:
        response = requests.post(
            url,
            json=payload,
            headers=headers or {"Content-Type": "application/json"},
            timeout=EventProcessorConfig.WEBHOOK_TIMEOUT_SECONDS
        )
        return response.status_code < 400
    except Exception as e:
        logger.error(f"Webhook delivery failed: {e}")
        return False


# =============================================================================
# EVENT PROCESSOR
# =============================================================================

class PURLEventProcessor:
    """Main event processor class."""

    def __init__(self):
        self.running = False
        self.processed_count = 0
        self.error_count = 0

    def start(self, run_once: bool = False):
        """Start the event processor."""
        self.running = True
        logger.info("PURL Event Processor starting...")
        logger.info(f"Registered handlers: {handler_registry.list_events()}")

        # Handle shutdown signals
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)

        while self.running:
            try:
                processed = self.process_batch()
                self.processed_count += processed

                if run_once:
                    break

                if processed == 0:
                    time.sleep(EventProcessorConfig.POLL_INTERVAL_SECONDS)

            except Exception as e:
                logger.error(f"Error in event processor loop: {e}")
                self.error_count += 1
                time.sleep(EventProcessorConfig.POLL_INTERVAL_SECONDS)

        logger.info(f"Event processor stopped. Processed: {self.processed_count}, Errors: {self.error_count}")

    def _handle_shutdown(self, signum, frame):
        """Handle shutdown signal."""
        logger.info("Shutdown signal received...")
        self.running = False

    def process_batch(self) -> int:
        """Process a batch of pending events."""
        db = SessionLocal()
        processed = 0

        try:
            # Get pending events
            events = db.execute(text("""
                SELECT id, organization_id, workspace_id, event_key, payload,
                       retry_count, created_at
                FROM purl_events_outbox
                WHERE status = 'pending'
                AND (process_after IS NULL OR process_after <= CURRENT_TIMESTAMP)
                ORDER BY created_at ASC
                LIMIT :batch_size
                FOR UPDATE SKIP LOCKED
            """), {"batch_size": EventProcessorConfig.BATCH_SIZE}).fetchall()

            for event in events:
                success = self.process_event(event, db)
                processed += 1

                if success:
                    # Mark as processed
                    db.execute(text("""
                        UPDATE purl_events_outbox
                        SET status = 'processed', processed_at = CURRENT_TIMESTAMP
                        WHERE id = :event_id
                    """), {"event_id": event.id})
                else:
                    # Handle retry logic
                    self.handle_failed_event(event, db)

                db.commit()

        except Exception as e:
            logger.error(f"Error processing batch: {e}")
            db.rollback()

        finally:
            db.close()

        return processed

    def process_event(self, event, db: Session) -> bool:
        """Process a single event."""
        event_key = event.event_key
        payload = event.payload if isinstance(event.payload, dict) else json.loads(event.payload or "{}")

        event_dict = {
            "id": event.id,
            "organization_id": event.organization_id,
            "workspace_id": event.workspace_id,
            "event_key": event_key,
            "payload": payload,
            "created_at": event.created_at.isoformat() if event.created_at else None
        }

        logger.info(f"Processing event {event.id}: {event_key}")

        handlers = handler_registry.get_handlers(event_key)

        if not handlers:
            logger.warning(f"No handlers registered for event: {event_key}")
            return True  # Mark as processed anyway

        success = True
        for handler in handlers:
            try:
                result = handler(event_dict, db)
                if not result:
                    success = False
            except Exception as e:
                logger.error(f"Handler error for {event_key}: {e}")
                success = False

        return success

    def handle_failed_event(self, event, db: Session):
        """Handle a failed event with retry logic."""
        retry_count = event.retry_count or 0

        if retry_count >= EventProcessorConfig.MAX_RETRIES:
            # Move to dead letter
            if EventProcessorConfig.DEAD_LETTER_AFTER_RETRIES:
                db.execute(text("""
                    UPDATE purl_events_outbox
                    SET status = 'dead_letter',
                        error_message = 'Max retries exceeded'
                    WHERE id = :event_id
                """), {"event_id": event.id})
                logger.warning(f"Event {event.id} moved to dead letter after {retry_count} retries")
            else:
                db.execute(text("""
                    UPDATE purl_events_outbox
                    SET status = 'failed',
                        error_message = 'Max retries exceeded'
                    WHERE id = :event_id
                """), {"event_id": event.id})
        else:
            # Schedule retry
            delay_minutes = EventProcessorConfig.RETRY_DELAY_MINUTES[
                min(retry_count, len(EventProcessorConfig.RETRY_DELAY_MINUTES) - 1)
            ]
            process_after = datetime.now(timezone.utc) + timedelta(minutes=delay_minutes)

            db.execute(text("""
                UPDATE purl_events_outbox
                SET retry_count = :retry_count,
                    process_after = :process_after
                WHERE id = :event_id
            """), {
                "event_id": event.id,
                "retry_count": retry_count + 1,
                "process_after": process_after
            })
            logger.info(f"Event {event.id} scheduled for retry in {delay_minutes} minutes")


# =============================================================================
# MAINTENANCE FUNCTIONS
# =============================================================================

def cleanup_old_events(days: int = 30):
    """Clean up old processed events."""
    db = SessionLocal()
    try:
        result = db.execute(text("""
            DELETE FROM purl_events_outbox
            WHERE status = 'processed'
            AND processed_at < CURRENT_TIMESTAMP - INTERVAL ':days days'
        """), {"days": days})

        db.commit()
        deleted = result.rowcount
        logger.info(f"Cleaned up {deleted} old events")
        return deleted

    except Exception as e:
        logger.error(f"Error cleaning up events: {e}")
        db.rollback()
        return 0
    finally:
        db.close()


def get_event_stats():
    """Get event processing statistics."""
    db = SessionLocal()
    try:
        stats = db.execute(text("""
            SELECT
                status,
                COUNT(*) as count,
                MIN(created_at) as oldest,
                MAX(created_at) as newest
            FROM purl_events_outbox
            GROUP BY status
        """)).fetchall()

        return {
            row.status: {
                "count": row.count,
                "oldest": row.oldest.isoformat() if row.oldest else None,
                "newest": row.newest.isoformat() if row.newest else None
            }
            for row in stats
        }

    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        return {}
    finally:
        db.close()


def reprocess_failed_events():
    """Requeue failed events for processing."""
    db = SessionLocal()
    try:
        result = db.execute(text("""
            UPDATE purl_events_outbox
            SET status = 'pending',
                retry_count = 0,
                process_after = NULL,
                error_message = NULL
            WHERE status IN ('failed', 'dead_letter')
        """))

        db.commit()
        requeued = result.rowcount
        logger.info(f"Requeued {requeued} failed events")
        return requeued

    except Exception as e:
        logger.error(f"Error reprocessing events: {e}")
        db.rollback()
        return 0
    finally:
        db.close()


# =============================================================================
# CLI
# =============================================================================

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="PURL Event Processor")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Run command
    run_parser = subparsers.add_parser("run", help="Run the event processor")
    run_parser.add_argument("--once", action="store_true", help="Process one batch and exit")

    # Stats command
    subparsers.add_parser("stats", help="Show event statistics")

    # Cleanup command
    cleanup_parser = subparsers.add_parser("cleanup", help="Clean up old events")
    cleanup_parser.add_argument("--days", type=int, default=30, help="Days to keep")

    # Reprocess command
    subparsers.add_parser("reprocess", help="Reprocess failed events")

    args = parser.parse_args()

    if args.command == "run":
        processor = PURLEventProcessor()
        processor.start(run_once=args.once)

    elif args.command == "stats":
        stats = get_event_stats()
        print("\nPURL Event Statistics:")
        print("-" * 40)
        for status, data in stats.items():
            print(f"  {status}: {data['count']} events")
            if data['oldest']:
                print(f"    oldest: {data['oldest']}")
                print(f"    newest: {data['newest']}")
        print()

    elif args.command == "cleanup":
        deleted = cleanup_old_events(args.days)
        print(f"Deleted {deleted} events older than {args.days} days")

    elif args.command == "reprocess":
        requeued = reprocess_failed_events()
        print(f"Requeued {requeued} failed events")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
