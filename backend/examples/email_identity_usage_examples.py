"""Email Identity Resolution - Usage Examples.

This module provides 10 working code examples demonstrating how to use
the Email Identity Resolution system in various scenarios.

Examples include:
1. Basic email resolution
2. Microsoft Graph API integration
3. Batch email processing
4. Gmail sync integration
5. Priority email routing
6. Vendor classification
7. Statistics and monitoring
8. Known client sync
9. Thread-aware matching
10. Custom domain mappings

Each example is self-contained and can be run independently.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

# Set up logging for examples
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================
# Example 1: Basic Email Resolution
# ============================================================

def example_1_basic_resolution():
    """
    Basic usage: Resolve a single email to find the matching CRM entity.

    This is the most common use case - receiving an email and immediately
    determining who sent it and linking it to the correct record.
    """
    from sqlalchemy.orm import Session
    from services.email_identity_resolver import get_email_identity_resolver

    def process_incoming_email(db: Session, user_id: int, email_data: dict):
        """Process an incoming email and resolve its identity."""

        # Get the resolver instance
        resolver = get_email_identity_resolver(db)

        # Prepare email data
        email_payload = {
            "from_email": email_data.get("sender"),
            "subject": email_data.get("subject"),
            "body_preview": email_data.get("body", "")[:500],
            "thread_id": email_data.get("conversation_id"),
        }

        # Resolve the email identity
        match = resolver.resolve(email_payload, user_id)

        # Process based on match result
        if match["match_method"]:
            logger.info(f"Match found: {match['match_method']} "
                       f"(confidence: {match['match_confidence']})")

            if match["is_priority"]:
                logger.info("This is a PRIORITY email from a known client!")

            # Link to CRM entities
            if match["matched_loan_id"]:
                logger.info(f"Linked to loan ID: {match['matched_loan_id']}")
            if match["matched_lead_id"]:
                logger.info(f"Linked to lead ID: {match['matched_lead_id']}")
            if match["matched_contact_id"]:
                logger.info(f"Linked to contact ID: {match['matched_contact_id']}")

            return match
        else:
            logger.info("No match found - email will need manual review")
            return None

    # Example usage:
    # db = get_db_session()
    # result = process_incoming_email(db, user_id=1, email_data={
    #     "sender": "john.smith@gmail.com",
    #     "subject": "Question about my loan application",
    #     "body": "Hi, I have a quick question...",
    #     "conversation_id": "thread-123"
    # })

    print("Example 1: Basic email resolution - see function definition")


# ============================================================
# Example 2: Microsoft Graph API Integration
# ============================================================

def example_2_microsoft_graph_integration():
    """
    Integrate with Microsoft Graph API email format.

    Microsoft Graph returns emails in a specific nested format.
    The resolver handles this automatically.
    """
    from sqlalchemy.orm import Session
    from services.email_identity_resolver import get_email_identity_resolver

    def process_graph_message(db: Session, user_id: int, graph_message: dict):
        """Process a Microsoft Graph API message."""

        resolver = get_email_identity_resolver(db)

        # Microsoft Graph format - the resolver handles this automatically
        email_data = {
            "from": graph_message.get("from"),  # {"emailAddress": {"address": "...", "name": "..."}}
            "subject": graph_message.get("subject"),
            "body_preview": graph_message.get("bodyPreview", ""),
            "thread_id": graph_message.get("conversationId"),
            "to": graph_message.get("toRecipients", []),
            "cc": graph_message.get("ccRecipients", []),
        }

        match = resolver.resolve(email_data, user_id)

        return {
            "graph_id": graph_message.get("id"),
            "match": match,
            "is_matched": match["match_method"] is not None,
        }

    # Example Microsoft Graph message format:
    sample_graph_message = {
        "id": "AAMkAGI2...",
        "subject": "RE: Loan #12345678 Documents",
        "bodyPreview": "Here are the documents you requested...",
        "conversationId": "AAQkAGI2...",
        "from": {
            "emailAddress": {
                "name": "John Smith",
                "address": "john.smith@gmail.com"
            }
        },
        "toRecipients": [
            {
                "emailAddress": {
                    "name": "Loan Officer",
                    "address": "officer@mortgage.com"
                }
            }
        ],
        "ccRecipients": [],
    }

    print("Example 2: Microsoft Graph integration")
    print(f"Sample message format: {sample_graph_message.get('from')}")


# ============================================================
# Example 3: Batch Email Processing
# ============================================================

def example_3_batch_processing():
    """
    Process multiple emails efficiently in a batch.

    Useful for:
    - Initial email import
    - Periodic sync jobs
    - Re-processing unmatched emails
    """
    from sqlalchemy.orm import Session
    from services.email_identity_resolver import get_email_identity_resolver

    def process_email_batch(
        db: Session,
        user_id: int,
        emails: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Process a batch of emails and return statistics."""

        resolver = get_email_identity_resolver(db)

        # Convert to resolver format
        email_payloads = [
            {
                "from_email": email.get("sender"),
                "subject": email.get("subject"),
                "body_preview": email.get("body", "")[:500],
                "thread_id": email.get("thread_id"),
            }
            for email in emails
        ]

        # Batch resolve
        results = resolver.batch_resolve(email_payloads, user_id)

        # Calculate statistics
        matched = sum(1 for r in results if r["match_method"])
        priority = sum(1 for r in results if r["is_priority"])

        by_method = {}
        for r in results:
            method = r["match_method"] or "unmatched"
            by_method[method] = by_method.get(method, 0) + 1

        return {
            "total": len(emails),
            "matched": matched,
            "unmatched": len(emails) - matched,
            "priority_count": priority,
            "match_rate": round(matched / len(emails) * 100, 1) if emails else 0,
            "by_method": by_method,
            "results": results,
        }

    # Example usage:
    sample_emails = [
        {"sender": "client1@gmail.com", "subject": "Help with loan"},
        {"sender": "client2@yahoo.com", "subject": "RE: Loan #12345"},
        {"sender": "appraiser@fanniemae.com", "subject": "Appraisal Complete"},
    ]

    print("Example 3: Batch processing")
    print(f"Would process {len(sample_emails)} emails")


# ============================================================
# Example 4: Gmail Sync Integration
# ============================================================

def example_4_gmail_sync_integration():
    """
    Integrate email identity resolution into Gmail sync workflow.

    Shows how to use the resolver as part of a larger email
    synchronization pipeline.
    """
    from sqlalchemy.orm import Session
    from services.email_identity_resolver import get_email_identity_resolver

    class GmailSyncWithIdentity:
        """Gmail sync class with identity resolution."""

        def __init__(self, db: Session, user_id: int):
            self.db = db
            self.user_id = user_id
            self.resolver = get_email_identity_resolver(db)

        def process_synced_message(self, gmail_message: dict) -> dict:
            """Process a synced Gmail message with identity resolution."""

            # Extract email data from Gmail format
            email_data = {
                "from_email": self._extract_header(gmail_message, "From"),
                "subject": self._extract_header(gmail_message, "Subject"),
                "body_preview": gmail_message.get("snippet", ""),
                "thread_id": gmail_message.get("threadId"),
                "to_emails": self._parse_recipients(
                    self._extract_header(gmail_message, "To")
                ),
            }

            # Resolve identity
            match = self.resolver.resolve(email_data, self.user_id)

            # Create reconciliation queue record
            return self._create_queue_record(gmail_message, email_data, match)

        def _extract_header(self, message: dict, header_name: str) -> Optional[str]:
            """Extract a header value from Gmail message."""
            headers = message.get("payload", {}).get("headers", [])
            for h in headers:
                if h.get("name", "").lower() == header_name.lower():
                    return h.get("value")
            return None

        def _parse_recipients(self, header_value: Optional[str]) -> List[str]:
            """Parse recipient list from header."""
            if not header_value:
                return []
            # Simple split - in production, use email parsing library
            return [r.strip() for r in header_value.split(",")]

        def _create_queue_record(
            self,
            gmail_message: dict,
            email_data: dict,
            match: dict
        ) -> dict:
            """Create email reconciliation queue record."""
            return {
                "gmail_id": gmail_message.get("id"),
                "from_email": email_data["from_email"],
                "subject": email_data["subject"],
                "thread_id": email_data["thread_id"],

                # Identity resolution fields
                "matched_contact_id": match["matched_contact_id"],
                "matched_loan_id": match["matched_loan_id"],
                "matched_lead_id": match["matched_lead_id"],
                "match_method": match["match_method"],
                "match_confidence": match["match_confidence"],
                "match_evidence": match["match_evidence"],
                "match_client_name": match["match_client_name"],
                "match_loan_number": match["match_loan_number"],
                "is_priority": match["is_priority"],
            }

    print("Example 4: Gmail sync integration")
    print("GmailSyncWithIdentity class defined")


# ============================================================
# Example 5: Priority Email Routing
# ============================================================

def example_5_priority_routing():
    """
    Route emails based on priority and match confidence.

    High-priority emails from known clients can be routed
    differently than unmatched emails.
    """
    from enum import Enum
    from sqlalchemy.orm import Session
    from services.email_identity_resolver import get_email_identity_resolver

    class EmailRoute(Enum):
        PRIORITY_INBOX = "priority_inbox"
        STANDARD_INBOX = "standard_inbox"
        REVIEW_QUEUE = "review_queue"
        VENDOR_FOLDER = "vendor_folder"

    def determine_route(match: dict) -> EmailRoute:
        """Determine email routing based on match result."""

        # Priority emails from known clients
        if match["is_priority"]:
            return EmailRoute.PRIORITY_INBOX

        # High-confidence matches
        if match["match_confidence"] and match["match_confidence"] >= 0.9:
            return EmailRoute.PRIORITY_INBOX

        # Vendor emails
        if match["vendor_type"]:
            return EmailRoute.VENDOR_FOLDER

        # Medium confidence matches
        if match["match_confidence"] and match["match_confidence"] >= 0.7:
            return EmailRoute.STANDARD_INBOX

        # Unmatched or low confidence
        return EmailRoute.REVIEW_QUEUE

    def process_with_routing(db: Session, user_id: int, email_data: dict) -> dict:
        """Process email and determine its route."""

        resolver = get_email_identity_resolver(db)
        match = resolver.resolve(email_data, user_id)
        route = determine_route(match)

        return {
            "match": match,
            "route": route.value,
            "should_notify": route in [EmailRoute.PRIORITY_INBOX],
            "needs_review": route == EmailRoute.REVIEW_QUEUE,
        }

    # Example results:
    print("Example 5: Priority routing")
    print("Routes: PRIORITY_INBOX, STANDARD_INBOX, REVIEW_QUEUE, VENDOR_FOLDER")


# ============================================================
# Example 6: Vendor Classification
# ============================================================

def example_6_vendor_classification():
    """
    Classify and handle vendor/partner emails.

    Vendor emails can be automatically categorized and
    linked to the appropriate loan based on context.
    """
    from services.email_identity_resolver import (
        get_email_identity_resolver,
        KNOWN_VENDOR_DOMAINS,
    )

    def get_vendor_info(email_address: str) -> Optional[dict]:
        """Get vendor information from email domain."""

        if "@" not in email_address:
            return None

        domain = email_address.lower().split("@")[1]

        # Check exact domain
        if domain in KNOWN_VENDOR_DOMAINS:
            entity_type, name, confidence = KNOWN_VENDOR_DOMAINS[domain]
            return {
                "domain": domain,
                "vendor_name": name,
                "vendor_type": entity_type,
                "confidence": confidence,
            }

        # Check parent domain for subdomains
        parts = domain.split(".")
        if len(parts) > 2:
            parent = ".".join(parts[-2:])
            if parent in KNOWN_VENDOR_DOMAINS:
                entity_type, name, confidence = KNOWN_VENDOR_DOMAINS[parent]
                return {
                    "domain": domain,
                    "parent_domain": parent,
                    "vendor_name": name,
                    "vendor_type": entity_type,
                    "confidence": confidence * 0.95,  # Slightly lower for subdomain
                }

        return None

    # Test vendor classification
    test_emails = [
        "appraiser@fanniemae.com",
        "support@noreply.equifax.com",
        "title@firstam.com",
        "agent@unknown-realty.com",
    ]

    print("Example 6: Vendor classification")
    for email in test_emails:
        info = get_vendor_info(email)
        if info:
            print(f"  {email} -> {info['vendor_name']} ({info['confidence']})")
        else:
            print(f"  {email} -> Unknown vendor")


# ============================================================
# Example 7: Statistics and Monitoring
# ============================================================

def example_7_statistics_monitoring():
    """
    Monitor email identity resolution performance.

    Track match rates, method effectiveness, and identify
    areas for improvement.
    """
    from sqlalchemy.orm import Session
    from services.email_identity_resolver import get_email_identity_resolver
    from services.email_identity_analytics import EmailIdentityAnalytics, MonitoringAlerts

    def get_resolution_dashboard(db: Session, user_id: int, days: int = 7) -> dict:
        """Get comprehensive resolution statistics dashboard."""

        analytics = EmailIdentityAnalytics(db)
        monitor = MonitoringAlerts(db)

        # Get match statistics
        stats = analytics.get_match_statistics(user_id, days=days)

        # Get method effectiveness
        effectiveness = analytics.get_method_effectiveness(user_id, days=days)

        # Get unmatched patterns
        patterns = analytics.get_unmatched_patterns(user_id, limit=10)

        # Run health check
        health = monitor.run_health_check(user_id)

        return {
            "period_days": days,
            "overview": {
                "total_emails": stats.total_emails,
                "matched": stats.matched,
                "unmatched": stats.unmatched,
                "match_rate": f"{stats.match_rate:.1f}%",
                "avg_confidence": f"{stats.avg_confidence:.2f}",
                "priority_emails": stats.priority_count,
            },
            "by_method": {
                m.method: {
                    "count": m.count,
                    "percentage": f"{m.percentage:.1f}%",
                    "avg_confidence": f"{m.avg_confidence:.2f}",
                }
                for m in effectiveness
            },
            "top_unmatched_patterns": [
                {"domain": p.domain, "count": p.count}
                for p in patterns
            ],
            "health": health,
        }

    print("Example 7: Statistics and monitoring")
    print("Dashboard includes: match rates, method effectiveness, unmatched patterns, health checks")


# ============================================================
# Example 8: Known Client Sync
# ============================================================

def example_8_known_client_sync():
    """
    Synchronize known client emails from CRM data.

    This populates the lookup table for fast matching.
    Should be run periodically to keep data fresh.
    """
    from sqlalchemy.orm import Session
    from services.email_identity_resolver import get_email_identity_resolver

    def sync_known_clients(db: Session, user_id: int) -> dict:
        """Sync known client emails from CRM tables."""

        resolver = get_email_identity_resolver(db)

        # Populate from leads, loans, contacts
        counts = resolver.populate_known_clients(user_id)

        # Get total count after sync
        stats = resolver.get_resolution_stats(user_id)

        return {
            "synced": counts,
            "total_known_clients": stats["known_clients_count"],
            "sync_time": datetime.now().isoformat(),
        }

    def schedule_periodic_sync():
        """Example of scheduling periodic sync."""

        # In production, use APScheduler, Celery, or similar
        # This is pseudo-code for illustration

        # schedule.every(6).hours.do(sync_all_users_known_clients)

        pass

    print("Example 8: Known client sync")
    print("Syncs emails from leads, loans, and contacts tables")


# ============================================================
# Example 9: Thread-Aware Matching
# ============================================================

def example_9_thread_aware_matching():
    """
    Demonstrate thread continuity matching.

    When a new email arrives in an existing thread,
    it inherits the match from previous emails.
    """
    from sqlalchemy.orm import Session
    from services.email_identity_resolver import get_email_identity_resolver

    def process_email_thread(
        db: Session,
        user_id: int,
        thread_emails: List[dict]
    ) -> List[dict]:
        """Process a sequence of emails in a thread."""

        resolver = get_email_identity_resolver(db)
        results = []

        for i, email in enumerate(thread_emails):
            email_data = {
                "from_email": email.get("from"),
                "subject": email.get("subject"),
                "thread_id": email.get("thread_id"),
            }

            match = resolver.resolve(email_data, user_id)

            results.append({
                "email_index": i,
                "from": email.get("from"),
                "match_method": match["match_method"],
                "confidence": match["match_confidence"],
                "inherited": match["match_method"] == "thread_continuity",
            })

        return results

    # Example thread scenario:
    example_thread = [
        {
            "from": "john.smith@gmail.com",  # Known client
            "subject": "Question about refinance",
            "thread_id": "thread-abc-123",
        },
        {
            "from": "loan.officer@mortgage.com",  # Loan officer reply
            "subject": "RE: Question about refinance",
            "thread_id": "thread-abc-123",
        },
        {
            "from": "spouse@different-email.com",  # Unknown sender, same thread
            "subject": "RE: RE: Question about refinance",
            "thread_id": "thread-abc-123",
        },
    ]

    print("Example 9: Thread-aware matching")
    print("Third email (unknown sender) inherits match from first email in thread")


# ============================================================
# Example 10: Custom Domain Mappings
# ============================================================

def example_10_custom_domain_mappings():
    """
    Add custom domain mappings for organization-specific vendors.

    Useful for adding local title companies, appraisers,
    or other partners not in the default list.
    """
    from sqlalchemy.orm import Session
    from sqlalchemy import text

    def add_custom_domain(
        db: Session,
        domain: str,
        entity_type: str,
        entity_name: str,
        confidence: float = 0.85
    ) -> bool:
        """Add a custom domain mapping to the database."""

        try:
            db.execute(
                text("""
                    INSERT INTO custom_domain_mappings
                    (domain, entity_type, entity_name, confidence, is_active, created_at)
                    VALUES (:domain, :entity_type, :entity_name, :confidence, true, NOW())
                    ON CONFLICT (domain)
                    DO UPDATE SET
                        entity_type = :entity_type,
                        entity_name = :entity_name,
                        confidence = :confidence,
                        is_active = true
                """),
                {
                    "domain": domain.lower(),
                    "entity_type": entity_type,
                    "entity_name": entity_name,
                    "confidence": confidence,
                }
            )
            db.commit()
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to add custom domain: {e}")
            return False

    def list_custom_domains(db: Session) -> List[dict]:
        """List all custom domain mappings."""

        try:
            result = db.execute(
                text("""
                    SELECT domain, entity_type, entity_name, confidence
                    FROM custom_domain_mappings
                    WHERE is_active = true
                    ORDER BY domain
                """)
            ).fetchall()

            return [
                {
                    "domain": row[0],
                    "entity_type": row[1],
                    "entity_name": row[2],
                    "confidence": row[3],
                }
                for row in result
            ]
        except Exception as e:
            logger.error(f"Error listing known domains: {e}")
            return []

    # Example custom domains to add:
    custom_domains = [
        ("localtitle.com", "vendor", "Local Title Company", 0.85),
        ("cityappraisers.net", "vendor", "City Appraisers Inc", 0.85),
        ("partner-realty.com", "realtor", "Partner Realty Group", 0.80),
    ]

    print("Example 10: Custom domain mappings")
    for domain, etype, name, conf in custom_domains:
        print(f"  Would add: {domain} -> {name} ({etype}, {conf})")


# ============================================================
# Main - Run all examples
# ============================================================

def main():
    """Run all examples to demonstrate functionality."""

    print("=" * 60)
    print("Email Identity Resolution - Usage Examples")
    print("=" * 60)
    print()

    examples = [
        (example_1_basic_resolution, "Basic Email Resolution"),
        (example_2_microsoft_graph_integration, "Microsoft Graph Integration"),
        (example_3_batch_processing, "Batch Email Processing"),
        (example_4_gmail_sync_integration, "Gmail Sync Integration"),
        (example_5_priority_routing, "Priority Email Routing"),
        (example_6_vendor_classification, "Vendor Classification"),
        (example_7_statistics_monitoring, "Statistics and Monitoring"),
        (example_8_known_client_sync, "Known Client Sync"),
        (example_9_thread_aware_matching, "Thread-Aware Matching"),
        (example_10_custom_domain_mappings, "Custom Domain Mappings"),
    ]

    for i, (example_func, name) in enumerate(examples, 1):
        print(f"\n{'=' * 60}")
        print(f"Example {i}: {name}")
        print("=" * 60)
        try:
            example_func()
        except Exception as e:
            print(f"Error running example: {e}")

    print("\n" + "=" * 60)
    print("Examples complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
