"""
Notification Delivery Integration Tests

Tests for the notification system:
- Notification model creation
- Read/unread state management
- Multi-tenant isolation
- Bulk notification creation
- Notification types
- Circuit breaker for external providers

Key files:
    backend/database/models/security.py (Notification model)
    backend/services/notification_service.py
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

pytestmark = [pytest.mark.integration, pytest.mark.critical]


@pytest.fixture
def org(db_session):
    """Create a test organization."""
    from database.models import Organization
    org = Organization(name="Notif Org", slug="notif-org", is_active=True)
    db_session.add(org)
    db_session.flush()
    return org


@pytest.fixture
def user(db_session, org):
    """Create a test user."""
    from database.models import User
    user = User(
        email="notif-user@test.com",
        hashed_password="hashed",
        first_name="Notif",
        last_name="User",
        role="loan_officer",
        organization_id=org.id,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def second_user(db_session, org):
    """Create a second user in same org for bulk tests."""
    from database.models import User
    user = User(
        email="notif-user2@test.com",
        hashed_password="hashed",
        first_name="Second",
        last_name="User",
        role="loan_officer",
        organization_id=org.id,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


class TestNotificationModel:
    """Test Notification model creation and fields."""

    def test_create_notification(self, db_session, org, user):
        """Creating a notification with required fields should succeed."""
        from database.models.security import Notification

        notif = Notification(
            organization_id=org.id,
            user_id=user.id,
            type="milestone_due",
            title="Appraisal Due",
            message="Appraisal for loan STG-001 is due in 2 days",
            link="/loans/STG-001",
        )
        db_session.add(notif)
        db_session.flush()

        assert notif.id is not None
        assert notif.is_read is False
        assert notif.read_at is None
        assert notif.type == "milestone_due"

    def test_notification_default_unread(self, db_session, org, user):
        """New notifications should default to unread."""
        from database.models.security import Notification

        notif = Notification(
            organization_id=org.id,
            user_id=user.id,
            type="assessment_reminder",
            title="Assessment Due",
            message="Skills assessment due next week",
        )
        db_session.add(notif)
        db_session.flush()

        assert notif.is_read is False

    @pytest.mark.parametrize("notif_type", [
        "permission_approved",
        "permission_denied",
        "milestone_due",
        "assessment_reminder",
        "goal_reminder",
        "feedback_added",
    ])
    def test_notification_types(self, db_session, org, user, notif_type):
        """Various notification types should be creatable."""
        from database.models.security import Notification

        notif = Notification(
            organization_id=org.id,
            user_id=user.id,
            type=notif_type,
            title=f"Test {notif_type}",
            message=f"Test message for {notif_type}",
        )
        db_session.add(notif)
        db_session.flush()
        assert notif.type == notif_type


class TestNotificationReadState:
    """Test notification read/unread state management."""

    def test_mark_notification_as_read(self, db_session, org, user):
        """Marking a notification as read should set is_read and read_at."""
        from database.models.security import Notification

        notif = Notification(
            organization_id=org.id,
            user_id=user.id,
            type="milestone_due",
            title="Read Test",
            message="Testing read state",
        )
        db_session.add(notif)
        db_session.flush()

        # Mark as read
        notif.is_read = True
        notif.read_at = datetime.now(timezone.utc)
        db_session.flush()

        assert notif.is_read is True
        assert notif.read_at is not None

    def test_mark_notification_back_to_unread(self, db_session, org, user):
        """Notifications should be re-markable as unread."""
        from database.models.security import Notification

        notif = Notification(
            organization_id=org.id,
            user_id=user.id,
            type="feedback_added",
            title="Unread Test",
            message="Testing unread state",
        )
        db_session.add(notif)
        db_session.flush()

        notif.is_read = True
        notif.read_at = datetime.now(timezone.utc)
        db_session.flush()

        notif.is_read = False
        notif.read_at = None
        db_session.flush()

        assert notif.is_read is False
        assert notif.read_at is None

    def test_query_unread_notifications(self, db_session, org, user):
        """Querying for unread notifications should filter correctly."""
        from database.models.security import Notification

        # Create 3 notifications: 2 unread, 1 read
        for i in range(3):
            notif = Notification(
                organization_id=org.id,
                user_id=user.id,
                type="milestone_due",
                title=f"Notif {i}",
                message=f"Message {i}",
                is_read=(i == 2),  # Third one is read
            )
            db_session.add(notif)
        db_session.flush()

        unread = db_session.query(Notification).filter(
            Notification.user_id == user.id,
            Notification.is_read == False,
        ).all()
        assert len(unread) == 2


class TestNotificationTenantIsolation:
    """Test that notifications are scoped to organizations."""

    def test_notifications_scoped_by_org(self, db_session):
        """Users in different orgs should only see their own notifications."""
        from database.models import Organization, User
        from database.models.security import Notification

        org1 = Organization(name="NOrg1", slug="norg1", is_active=True)
        org2 = Organization(name="NOrg2", slug="norg2", is_active=True)
        db_session.add_all([org1, org2])
        db_session.flush()

        u1 = User(
            email="n-u1@test.com", hashed_password="h",
            organization_id=org1.id, is_active=True,
        )
        u2 = User(
            email="n-u2@test.com", hashed_password="h",
            organization_id=org2.id, is_active=True,
        )
        db_session.add_all([u1, u2])
        db_session.flush()

        n1 = Notification(
            organization_id=org1.id, user_id=u1.id,
            type="milestone_due", title="Org1 Notif", message="Org1",
        )
        n2 = Notification(
            organization_id=org2.id, user_id=u2.id,
            type="milestone_due", title="Org2 Notif", message="Org2",
        )
        db_session.add_all([n1, n2])
        db_session.flush()

        org1_notifs = db_session.query(Notification).filter(
            Notification.organization_id == org1.id
        ).all()
        assert len(org1_notifs) == 1
        assert org1_notifs[0].title == "Org1 Notif"


class TestBulkNotifications:
    """Test creating multiple notifications at once."""

    def test_bulk_create_notifications(self, db_session, org, user, second_user):
        """Bulk notification creation for multiple users."""
        from database.models.security import Notification

        user_ids = [user.id, second_user.id]
        notifications = []
        for uid in user_ids:
            notifications.append(Notification(
                organization_id=org.id,
                user_id=uid,
                type="goal_reminder",
                title="Monthly Goal Check",
                message="Review your monthly pipeline goals",
            ))
        db_session.add_all(notifications)
        db_session.flush()

        all_notifs = db_session.query(Notification).filter(
            Notification.organization_id == org.id,
            Notification.type == "goal_reminder",
        ).all()
        assert len(all_notifs) == 2


class TestNotificationServiceCircuitBreaker:
    """Test the circuit breaker for external notification providers."""

    def test_circuit_breaker_starts_closed(self):
        """Circuit breaker should start in CLOSED state."""
        from services.notification_service import NotificationCircuitBreaker

        cb = NotificationCircuitBreaker(
            provider_name="TestProvider", failure_threshold=3, recovery_timeout=5,
        )
        assert cb.state == cb.CLOSED
        assert cb.allow_request() is True

    def test_circuit_breaker_opens_after_threshold(self):
        """Circuit breaker should open after threshold failures."""
        from services.notification_service import NotificationCircuitBreaker

        cb = NotificationCircuitBreaker(
            provider_name="TestProvider", failure_threshold=3, recovery_timeout=5,
        )
        for _ in range(3):
            cb.record_failure()
        assert cb.state == cb.OPEN
        assert cb.allow_request() is False

    def test_circuit_breaker_resets_on_success(self):
        """Success should reset failure count and close circuit."""
        from services.notification_service import NotificationCircuitBreaker

        cb = NotificationCircuitBreaker(
            provider_name="TestProvider", failure_threshold=3, recovery_timeout=5,
        )
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.state == cb.CLOSED
