"""
Listing Agent Weekly Update Job
Runs weekly to send status updates to listing agents.
"""

import os
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

# Use shared database module for connection pooling
from database import SessionLocal

logger = logging.getLogger(__name__)


def get_db_session() -> Session:
    """Get a database session from the shared pool"""
    return SessionLocal()


def run_weekly_updates(
    organization_id: Optional[int] = None,
    dry_run: bool = False
) -> dict:
    """
    Run weekly updates for all eligible parties.

    Args:
        organization_id: Optional org filter
        dry_run: If True, don't actually send emails

    Returns:
        Statistics about the run
    """
    from services.listing_snapshot_service import listing_snapshot_service
    from services.listing_update_email_service import listing_update_email_service
    from services.listing_portal_service import listing_portal_service

    db = get_db_session()
    stats = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "parties_processed": 0,
        "emails_sent": 0,
        "emails_failed": 0,
        "transactions_included": 0,
        "errors": []
    }

    try:
        logger.info(f"Starting weekly update job (org_id={organization_id}, dry_run={dry_run})")

        # Get all parties that should receive updates
        parties = listing_snapshot_service.get_parties_for_weekly_update(db, organization_id)
        logger.info(f"Found {len(parties)} parties to update")

        for party_data in parties:
            stats["parties_processed"] += 1

            try:
                # Generate update data
                update_data = listing_snapshot_service.generate_weekly_update_data(
                    db,
                    party_data["email"],
                    party_data["transaction_ids"]
                )

                if not update_data or not update_data.get("transactions"):
                    logger.debug(f"No transactions for {party_data['email']}, skipping")
                    continue

                stats["transactions_included"] += len(update_data["transactions"])

                if dry_run:
                    logger.info(f"[DRY RUN] Would send to {party_data['email']}: "
                               f"{len(update_data['transactions'])} transactions")
                    stats["emails_sent"] += 1
                    continue

                # Send the email
                success = listing_update_email_service.send_weekly_update(
                    to_email=update_data["party_email"],
                    party_name=update_data["party_name"],
                    transactions=update_data["transactions"],
                    portal_url=update_data["portal_url"],
                    unsubscribe_url=update_data["unsubscribe_url"]
                )

                if success:
                    stats["emails_sent"] += 1

                    # Record delivery for each transaction
                    for txn in update_data["transactions"]:
                        listing_snapshot_service.record_delivery(
                            db,
                            party_id=update_data["party_id"],
                            transaction_id=txn["transaction_id"],
                            delivery_type="weekly_update",
                            snapshot_data=txn
                        )
                        listing_snapshot_service.update_delivery_status(
                            db,
                            delivery_id=txn["transaction_id"],  # This is a simplification
                            status="sent"
                        )
                else:
                    stats["emails_failed"] += 1
                    stats["errors"].append(f"Failed to send to {party_data['email']}")

            except Exception as e:
                logger.error(f"Error processing party {party_data['email']}: {e}")
                stats["emails_failed"] += 1
                stats["errors"].append(str(e))

        stats["completed_at"] = datetime.now(timezone.utc).isoformat()
        logger.info(f"Weekly update job complete: {stats}")

        return stats

    except Exception as e:
        logger.error(f"Weekly update job failed: {e}")
        stats["errors"].append(str(e))
        stats["completed_at"] = datetime.now(timezone.utc).isoformat()
        return stats

    finally:
        db.close()


def send_milestone_notifications(
    transaction_id: int,
    milestone_id: int,
    new_status: str
) -> dict:
    """
    Send milestone change notifications to subscribed parties.
    Called when a milestone status changes.
    """
    from services.listing_portal_service import listing_portal_service
    from services.listing_update_email_service import listing_update_email_service

    db = get_db_session()
    stats = {
        "notifications_sent": 0,
        "notifications_failed": 0
    }

    try:
        # Get transaction and milestone info
        transaction = listing_portal_service.get_transaction(db, transaction_id)
        if not transaction:
            return stats

        # Get milestone name
        milestones = listing_portal_service.get_milestones(db, transaction_id)
        milestone = next((m for m in milestones if m["id"] == milestone_id), None)
        if not milestone:
            return stats

        # Get parties subscribed to milestone notifications
        parties = listing_portal_service.get_transaction_parties(db, transaction_id)

        for party in parties:
            if not party.get("notify_milestone_changes"):
                continue

            if party.get("unsubscribed_at"):
                continue

            try:
                # Create unsubscribe token
                unsub_token = listing_portal_service.create_unsubscribe_token(
                    db, party["id"], "milestones"
                )

                frontend_url = listing_portal_service.frontend_url
                portal_url = f"{frontend_url}/listing-portal"
                unsub_url = f"{frontend_url}/listing-portal/unsubscribe?token={unsub_token}"

                success = listing_update_email_service.send_milestone_notification(
                    to_email=party["email"],
                    party_name=f"{party['first_name']} {party['last_name']}",
                    property_address=transaction["property_address"],
                    milestone_name=milestone["milestone_name"],
                    milestone_status=new_status,
                    portal_url=portal_url,
                    unsubscribe_url=unsub_url
                )

                if success:
                    stats["notifications_sent"] += 1
                else:
                    stats["notifications_failed"] += 1

            except Exception as e:
                logger.error(f"Error sending milestone notification to {party['email']}: {e}")
                stats["notifications_failed"] += 1

        return stats

    except Exception as e:
        logger.error(f"Error in send_milestone_notifications: {e}")
        return stats

    finally:
        db.close()


# CLI entry point
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run listing agent weekly updates")
    parser.add_argument("--org-id", type=int, help="Filter by organization ID")
    parser.add_argument("--dry-run", action="store_true", help="Don't actually send emails")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    result = run_weekly_updates(
        organization_id=args.org_id,
        dry_run=args.dry_run
    )

    print(f"\nResults:")
    print(f"  Parties processed: {result['parties_processed']}")
    print(f"  Emails sent: {result['emails_sent']}")
    print(f"  Emails failed: {result['emails_failed']}")
    print(f"  Transactions included: {result['transactions_included']}")

    if result["errors"]:
        print(f"\nErrors:")
        for error in result["errors"][:10]:
            print(f"  - {error}")
