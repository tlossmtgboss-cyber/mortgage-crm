# Mobile App — Full Production Readiness Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete all remaining work to make the Perennia AI iOS mobile app fully functional and add Android support.

**Architecture:** Capacitor v8 wraps the React frontend as a native iOS/Android app. Push notifications use APNS (iOS) and FCM (Android) via a backend dispatch service. Universal links route `app.perenniaai.com` URLs into the native app. Offline support caches API responses in native storage with network-aware UI.

**Tech Stack:** Capacitor 8, React, FastAPI, PyAPNs2 (APNS), firebase-admin (FCM), @capacitor/network, @capacitor/preferences

---

## File Structure

| File | Responsibility |
|------|---------------|
| `backend/database/models/device_token.py` | **CREATE** — DeviceToken SQLAlchemy model |
| `backend/database/models/__init__.py` | **MODIFY** — Export DeviceToken |
| `backend/database/init_db.py` | **MODIFY** — Wire device_tokens migration |
| `backend/routes/_register_auth_security.py` | **MODIFY** — Pass DeviceToken to setup_auth_routes |
| `backend/services/push_notification_service.py` | **CREATE** — APNS/FCM dispatch service |
| `backend/routes/push_notification_routes.py` | **CREATE** — Admin/internal push endpoints + triggers |
| `backend/push_config.py` | **CREATE** — APNS/FCM env var configuration (root level — `config.py` shadows `config/` package) |
| `backend/routes/well_known_routes.py` | **CREATE** — .well-known/apple-app-site-association |
| `frontend/ios/App/App/App.entitlements` | **MODIFY** — Add Associated Domains |
| `frontend/ios/App/App/App.entitlements.release` | **MODIFY** — Add Associated Domains (production) |
| `frontend/capacitor.config.ts` | **MODIFY** — Add android config block |
| `frontend/src/hooks/useNetworkStatus.js` | **CREATE** — Network state detection |
| `frontend/src/hooks/useOfflineCache.js` | **CREATE** — API response cache layer |
| `frontend/src/components/OfflineIndicator.js` | **CREATE** — Offline banner component |
| `frontend/src/components/OfflineIndicator.css` | **CREATE** — Offline banner styles |
| `frontend/src/App.jsx` | **MODIFY** — Add deep link handler + offline indicator |
| `frontend/scripts/android-build.sh` | **CREATE** — Android build script |
| `backend/tests/test_device_token_model.py` | **CREATE** — DeviceToken model tests |
| `backend/tests/test_push_notification_service.py` | **CREATE** — Push service tests |
| `docs/mobile/app-store-submission-checklist.md` | **CREATE** — App Store submission guide |
| `docs/mobile/apns-setup-guide.md` | **CREATE** — APNS credential setup guide |

---

### Task 1: DeviceToken Model + Migration Wiring

**Context:** The `device_tokens` table migration exists (`backend/migrations/add_device_tokens_table.py`) and push token registration endpoints exist in `auth_routes.py` (lines 1476-1556), but the SQLAlchemy model class was never created. The `setup_auth_routes()` call in `_register_auth_security.py:61` doesn't pass `DeviceToken`, so push routes are silently skipped.

**Files:**
- Create: `backend/database/models/device_token.py`
- Create: `backend/tests/test_device_token_model.py`
- Modify: `backend/database/models/__init__.py` — add DeviceToken export
- Modify: `backend/database/init_db.py` — wire migration (~line 1767+)
- Modify: `backend/routes/_register_auth_security.py:59-61` — pass DeviceToken

- [ ] **Step 1: Write failing test for DeviceToken model**

```python
# backend/tests/test_device_token_model.py
"""Tests for DeviceToken model."""
import pytest
from datetime import datetime, timezone


def test_device_token_import():
    """DeviceToken should be importable from database.models."""
    from database.models import DeviceToken
    assert DeviceToken is not None
    assert hasattr(DeviceToken, '__tablename__')
    assert DeviceToken.__tablename__ == 'device_tokens'


def test_device_token_columns():
    """DeviceToken should have all required columns."""
    from database.models import DeviceToken
    mapper = DeviceToken.__mapper__
    column_names = [c.key for c in mapper.columns]
    required = ['id', 'user_id', 'device_token', 'platform', 'is_active', 'created_at', 'updated_at']
    for col in required:
        assert col in column_names, f"Missing column: {col}"


def test_device_token_defaults():
    """DeviceToken should have correct defaults."""
    from database.models import DeviceToken
    token = DeviceToken(user_id=1, device_token="abc123", platform="ios")
    assert token.is_active is True
    assert token.platform == "ios"


def test_device_token_user_relationship():
    """DeviceToken should have a user relationship."""
    from database.models import DeviceToken
    assert hasattr(DeviceToken, 'user')
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_device_token_model.py -v`
Expected: ImportError — DeviceToken not found in database.models

- [ ] **Step 3: Create DeviceToken model**

```python
# backend/database/models/device_token.py
"""DeviceToken model — stores APNs/FCM push notification tokens per user."""
from datetime import datetime, timezone

from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship

from db import Base


class DeviceToken(Base):
    __tablename__ = 'device_tokens'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    device_token = Column(String(500), nullable=False)
    platform = Column(String(20), nullable=False)  # "ios" or "android"
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", back_populates="device_tokens")

    __table_args__ = (
        UniqueConstraint('user_id', 'device_token', name='uq_user_device_token'),
        Index('idx_device_tokens_user_id', 'user_id'),
        Index('idx_device_tokens_active', 'is_active', postgresql_where=(is_active == True)),
    )

    def __repr__(self):
        return f"<DeviceToken(id={self.id}, user_id={self.user_id}, platform={self.platform})>"
```

- [ ] **Step 4: Add DeviceToken export to models/__init__.py**

After the security models import block (~line 158), add:

```python
# Device token models (push notifications)
from .device_token import DeviceToken
```

And ensure DeviceToken appears in `__all__` if that list exists.

- [ ] **Step 5: Add `device_tokens` relationship to User model**

In `backend/database/models/core.py`, add to the User class:

```python
device_tokens = relationship("DeviceToken", back_populates="user", cascade="all, delete-orphan")
```

- [ ] **Step 6: Wire device_tokens migration into init_db.py**

After the last migration block (~line 1767), add:

```python
try:
    from migrations.add_device_tokens_table import run_migration as run_device_tokens
    run_device_tokens()
    logger.info("✅ device_tokens table ready")
except Exception as e:
    logger.warning(f"⚠️ device_tokens migration note: {e}")
```

**Important:** The existing migration's `run_migration()` creates its own engine from `DATABASE_URL`. This is consistent with other migrations in init_db.py — they all use their own engine connections. No signature change needed.

- [ ] **Step 7: Pass DeviceToken to setup_auth_routes**

In `backend/routes/_register_auth_security.py`, change line 59-61 from:

```python
from routes.auth_routes import router as auth_routes_router, setup_auth_routes
app.include_router(auth_routes_router, tags=["Authentication"])
setup_auth_routes(app, oauth2_scheme, get_current_user)
```

to:

```python
from routes.auth_routes import router as auth_routes_router, setup_auth_routes
app.include_router(auth_routes_router, tags=["Authentication"])
try:
    from database.models.device_token import DeviceToken
except ImportError:
    DeviceToken = None
setup_auth_routes(app, oauth2_scheme, get_current_user, DeviceToken=DeviceToken)
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_device_token_model.py -v`
Expected: All 4 tests PASS

- [ ] **Step 9: Verify push endpoints are wired with AST parse**

Run: `cd backend && python -c "from routes.auth_routes import setup_auth_routes; print('setup_auth_routes imported OK')"`
Expected: No errors

- [ ] **Step 10: Commit**

```bash
git add backend/database/models/device_token.py backend/database/models/__init__.py backend/database/models/core.py backend/database/init_db.py backend/routes/_register_auth_security.py backend/tests/test_device_token_model.py
git commit -m "feat: create DeviceToken model and wire push notification endpoints"
```

---

### Task 2: Push Notification Dispatch Service

**Context:** Device tokens are stored, but nothing sends notifications to them. This task creates the backend service that dispatches push notifications via APNS (iOS) and FCM (Android). Uses token-based APNS auth (.p8 key file) and firebase-admin for FCM.

**Files:**
- Create: `backend/services/push_notification_service.py`
- Create: `backend/push_config.py` (root level — `config.py` shadows `config/` package)
- Create: `backend/tests/test_push_notification_service.py`
- Modify: `backend/requirements.txt` — add PyAPNs2, firebase-admin

- [ ] **Step 1: Write failing tests for push notification service**

```python
# backend/tests/test_push_notification_service.py
"""Tests for PushNotificationService."""
import pytest
from unittest.mock import MagicMock, patch


def test_service_import():
    """PushNotificationService should be importable."""
    from services.push_notification_service import PushNotificationService
    assert PushNotificationService is not None


def test_notification_types():
    """All notification types should be defined."""
    from services.push_notification_service import NotificationType
    assert hasattr(NotificationType, 'LEAD_ASSIGNED')
    assert hasattr(NotificationType, 'APPOINTMENT_REMINDER')
    assert hasattr(NotificationType, 'SLA_ALERT')
    assert hasattr(NotificationType, 'BRIEFING_READY')
    assert hasattr(NotificationType, 'DOCUMENT_RECEIVED')
    assert hasattr(NotificationType, 'GENERAL')


def test_build_apns_payload():
    """Should build a valid APNS payload."""
    from services.push_notification_service import PushNotificationService
    service = PushNotificationService()
    payload = service._build_apns_payload(
        title="New Lead Assigned",
        body="John Smith — $350,000 purchase",
        data={"lead_id": 123, "type": "lead_assigned"},
        badge=3
    )
    assert payload is not None
    assert "aps" in payload or hasattr(payload, 'alert')


def test_build_fcm_message():
    """Should build a valid FCM message dict."""
    from services.push_notification_service import PushNotificationService
    service = PushNotificationService()
    msg = service._build_fcm_message(
        token="fake-fcm-token",
        title="New Lead Assigned",
        body="John Smith — $350,000 purchase",
        data={"lead_id": "123", "type": "lead_assigned"}
    )
    assert msg is not None


def test_get_user_tokens(db_session):
    """Should retrieve active tokens for a user."""
    from services.push_notification_service import PushNotificationService
    service = PushNotificationService()
    # With no tokens in DB, should return empty list
    tokens = service.get_active_tokens(db_session, user_id=99999)
    assert tokens == []


def test_notification_templates():
    """Each notification type should have a template."""
    from services.push_notification_service import NOTIFICATION_TEMPLATES
    assert 'lead_assigned' in NOTIFICATION_TEMPLATES
    assert 'appointment_reminder' in NOTIFICATION_TEMPLATES
    assert 'title' in NOTIFICATION_TEMPLATES['lead_assigned']
    assert 'body' in NOTIFICATION_TEMPLATES['lead_assigned']
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_push_notification_service.py -v`
Expected: ImportError

- [ ] **Step 3: Create APNS/FCM configuration module**

```python
# backend/push_config.py
"""Push notification configuration — APNS (iOS) and FCM (Android)."""
import os
import logging

logger = logging.getLogger(__name__)

# APNS Configuration (token-based auth with .p8 key)
APNS_KEY_ID = os.getenv("APNS_KEY_ID")  # 10-char key ID from Apple
APNS_TEAM_ID = os.getenv("APNS_TEAM_ID", "V5ZA5FZ2J8")  # Apple Developer Team ID
APNS_KEY_PATH = os.getenv("APNS_KEY_PATH")  # Path to .p8 key file
APNS_BUNDLE_ID = os.getenv("APNS_BUNDLE_ID", "com.perenniaai.crm")
APNS_USE_SANDBOX = os.getenv("APNS_USE_SANDBOX", "true").lower() == "true"

# FCM Configuration (Firebase Cloud Messaging for Android)
FCM_CREDENTIALS_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")  # Path to firebase service account JSON

def is_apns_configured():
    """Check if APNS credentials are available."""
    configured = bool(APNS_KEY_ID and APNS_KEY_PATH and os.path.exists(APNS_KEY_PATH or ""))
    if not configured:
        logger.debug("APNS not configured — set APNS_KEY_ID, APNS_KEY_PATH env vars")
    return configured

def is_fcm_configured():
    """Check if FCM credentials are available."""
    configured = bool(FCM_CREDENTIALS_PATH and os.path.exists(FCM_CREDENTIALS_PATH or ""))
    if not configured:
        logger.debug("FCM not configured — set GOOGLE_APPLICATION_CREDENTIALS env var")
    return configured
```

- [ ] **Step 4: Create push notification service**

```python
# backend/services/push_notification_service.py
"""
Push Notification Dispatch Service

Sends push notifications to iOS (APNS) and Android (FCM) devices.
Uses token-based APNS auth and firebase-admin for FCM.
"""
import logging
from enum import Enum
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class NotificationType(str, Enum):
    LEAD_ASSIGNED = "lead_assigned"
    APPOINTMENT_REMINDER = "appointment_reminder"
    SLA_ALERT = "sla_alert"
    BRIEFING_READY = "briefing_ready"
    DOCUMENT_RECEIVED = "document_received"
    GENERAL = "general"


# Notification templates — title/body use {placeholders} filled at send time
NOTIFICATION_TEMPLATES = {
    "lead_assigned": {
        "title": "New Lead Assigned",
        "body": "{lead_name} — ${amount:,.0f} {loan_purpose}",
    },
    "appointment_reminder": {
        "title": "Upcoming Appointment",
        "body": "{contact_name} at {time}",
    },
    "sla_alert": {
        "title": "SLA Warning",
        "body": "{loan_name} — {milestone} due in {hours_remaining}h",
    },
    "briefing_ready": {
        "title": "Morning Briefing Ready",
        "body": "{active_count} active loans, {at_risk_count} at risk",
    },
    "document_received": {
        "title": "Document Received",
        "body": "{doc_type} from {borrower_name}",
    },
    "general": {
        "title": "{title}",
        "body": "{body}",
    },
}


class PushNotificationService:
    """Dispatches push notifications to registered devices."""

    def __init__(self):
        self._apns_client = None
        self._fcm_initialized = False

    def _get_apns_client(self):
        """Lazy-init APNS client."""
        if self._apns_client is not None:
            return self._apns_client

        from push_config import is_apns_configured, APNS_KEY_PATH, APNS_KEY_ID, APNS_TEAM_ID, APNS_USE_SANDBOX
        if not is_apns_configured():
            return None

        try:
            from apns2.client import APNsClient
            from apns2.credentials import TokenCredentials
            token_credentials = TokenCredentials(
                auth_key_path=APNS_KEY_PATH,
                auth_key_id=APNS_KEY_ID,
                team_id=APNS_TEAM_ID,
            )
            self._apns_client = APNsClient(
                credentials=token_credentials,
                use_sandbox=APNS_USE_SANDBOX,
            )
            logger.info("APNS client initialized (sandbox=%s)", APNS_USE_SANDBOX)
            return self._apns_client
        except Exception as e:
            logger.error("Failed to initialize APNS client: %s", e)
            return None

    def _init_fcm(self):
        """Lazy-init Firebase Admin SDK for FCM."""
        if self._fcm_initialized:
            return True

        from push_config import is_fcm_configured
        if not is_fcm_configured():
            return False

        try:
            import firebase_admin
            from firebase_admin import credentials as fb_credentials
            from push_config import FCM_CREDENTIALS_PATH
            if not firebase_admin._apps:
                cred = fb_credentials.Certificate(FCM_CREDENTIALS_PATH)
                firebase_admin.initialize_app(cred)
            self._fcm_initialized = True
            logger.info("FCM initialized")
            return True
        except Exception as e:
            logger.error("Failed to initialize FCM: %s", e)
            return False

    def get_active_tokens(self, db: Session, user_id: int) -> list:
        """Get all active device tokens for a user."""
        from database.models.device_token import DeviceToken
        tokens = db.query(DeviceToken).filter(
            DeviceToken.user_id == user_id,
            DeviceToken.is_active == True,
        ).all()
        return tokens

    def _build_apns_payload(self, title: str, body: str, data: dict = None, badge: int = None):
        """Build an APNS payload object."""
        from apns2.payload import Payload
        return Payload(
            alert={"title": title, "body": body},
            badge=badge,
            sound="default",
            custom=data or {},
        )

    def _build_fcm_message(self, token: str, title: str, body: str, data: dict = None):
        """Build an FCM message dict."""
        from firebase_admin import messaging
        return messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            data={k: str(v) for k, v in (data or {}).items()},
            token=token,
        )

    def _send_ios(self, device_token: str, title: str, body: str, data: dict = None, badge: int = None) -> bool:
        """Send a push notification to an iOS device via APNS."""
        client = self._get_apns_client()
        if not client:
            logger.warning("APNS not configured — skipping iOS push")
            return False

        try:
            from push_config import APNS_BUNDLE_ID
            payload = self._build_apns_payload(title, body, data, badge)
            response = client.send_notification(device_token, payload, topic=APNS_BUNDLE_ID)
            if response.is_successful:
                logger.info("APNS sent to %s...%s", device_token[:8], device_token[-4:])
                return True
            else:
                logger.error("APNS failed: %s (token %s...%s)", response.description, device_token[:8], device_token[-4:])
                return False
        except Exception as e:
            logger.error("APNS send error: %s", e)
            return False

    def _send_android(self, device_token: str, title: str, body: str, data: dict = None) -> bool:
        """Send a push notification to an Android device via FCM."""
        if not self._init_fcm():
            logger.warning("FCM not configured — skipping Android push")
            return False

        try:
            from firebase_admin import messaging
            message = self._build_fcm_message(device_token, title, body, data)
            response = messaging.send(message)
            logger.info("FCM sent: %s", response)
            return True
        except Exception as e:
            logger.error("FCM send error: %s", e)
            return False

    def send_to_user(
        self,
        db: Session,
        user_id: int,
        notification_type: str,
        template_data: dict = None,
        custom_title: str = None,
        custom_body: str = None,
        extra_data: dict = None,
    ) -> dict:
        """
        Send a push notification to all of a user's active devices.

        Args:
            db: Database session
            user_id: Target user ID
            notification_type: Key from NOTIFICATION_TEMPLATES
            template_data: Dict of values to fill template placeholders
            custom_title: Override template title
            custom_body: Override template body
            extra_data: Additional data payload sent with notification

        Returns:
            {"sent": int, "failed": int, "skipped": int}
        """
        tokens = self.get_active_tokens(db, user_id)
        if not tokens:
            return {"sent": 0, "failed": 0, "skipped": 0}

        # Resolve title and body from template
        template = NOTIFICATION_TEMPLATES.get(notification_type, NOTIFICATION_TEMPLATES["general"])
        title = custom_title or template["title"]
        body = custom_body or template["body"]

        if template_data:
            try:
                title = title.format(**template_data)
                body = body.format(**template_data)
            except (KeyError, ValueError) as e:
                logger.warning("Template format error for %s: %s", notification_type, e)

        data = {"type": notification_type, **(extra_data or {})}
        result = {"sent": 0, "failed": 0, "skipped": 0}

        for token_record in tokens:
            if token_record.platform == "ios":
                ok = self._send_ios(token_record.device_token, title, body, data)
            elif token_record.platform == "android":
                ok = self._send_android(token_record.device_token, title, body, data)
            else:
                result["skipped"] += 1
                continue

            if ok:
                result["sent"] += 1
            else:
                result["failed"] += 1
                # Deactivate token on permanent failure (optional — could check APNS response codes)

        logger.info("Push to user %d: %s", user_id, result)
        return result

    def send_to_users(self, db: Session, user_ids: list, **kwargs) -> dict:
        """Send the same notification to multiple users."""
        totals = {"sent": 0, "failed": 0, "skipped": 0}
        for uid in user_ids:
            r = self.send_to_user(db, uid, **kwargs)
            for k in totals:
                totals[k] += r[k]
        return totals
```

- [ ] **Step 5: Add dependencies to requirements.txt**

Append to `backend/requirements.txt`:

```
# Push notifications
apns2>=0.7.2
firebase-admin>=6.0.0
```

- [ ] **Step 6: Run tests**

Run: `cd backend && pip install apns2 firebase-admin && python -m pytest tests/test_push_notification_service.py -v`
Expected: All tests PASS (some may skip FCM tests if no credentials)

- [ ] **Step 7: Commit**

```bash
git add backend/services/push_notification_service.py backend/push_config.py backend/tests/test_push_notification_service.py backend/requirements.txt
git commit -m "feat: add push notification dispatch service with APNS and FCM support"
```

---

### Task 3: Push Notification Trigger Routes

**Context:** The dispatch service exists but nothing triggers it. This task creates internal API endpoints that trigger notifications from business events (lead assignment, appointment reminders, briefing ready) and a Celery task for scheduled reminders.

**Files:**
- Create: `backend/routes/push_notification_routes.py`
- Modify: `backend/routes/_register_auth_security.py` — register new routes

- [ ] **Step 1: Create push notification trigger routes**

```python
# backend/routes/push_notification_routes.py
"""
Push Notification Routes

Internal API endpoints for triggering push notifications.
All endpoints require authentication.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session

from db import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/push", tags=["Push Notifications"])


class SendNotificationRequest(BaseModel):
    user_id: int
    notification_type: str = "general"
    title: Optional[str] = None
    body: Optional[str] = None
    data: Optional[dict] = None


def setup_push_routes(app, get_current_user):
    """Register push notification routes requiring auth."""

    @app.post("/api/v1/push/send")
    async def send_push_notification(
        request: SendNotificationRequest,
        current_user=Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        """Send a push notification to a specific user. Requires admin/manager role."""
        if current_user.permission_role not in (
            "admin", "site_admin", "platform_admin", "management",
            "branch_manager", "regional_manager", "leadership",
        ):
            raise HTTPException(status_code=403, detail="Insufficient permissions")

        from services.push_notification_service import PushNotificationService
        service = PushNotificationService()
        result = service.send_to_user(
            db=db,
            user_id=request.user_id,
            notification_type=request.notification_type,
            custom_title=request.title,
            custom_body=request.body,
            extra_data=request.data,
        )
        return {"success": True, **result}

    @app.post("/api/v1/push/test")
    async def send_test_notification(
        current_user=Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        """Send a test notification to the current user's devices."""
        from services.push_notification_service import PushNotificationService
        service = PushNotificationService()
        result = service.send_to_user(
            db=db,
            user_id=current_user.id,
            notification_type="general",
            template_data={"title": "Test Notification", "body": "Push notifications are working!"},
        )
        return {"success": True, **result}


# Module-level singleton to preserve lazy-init APNS/FCM clients across calls
_push_service = None
def _get_push_service():
    global _push_service
    if _push_service is None:
        from services.push_notification_service import PushNotificationService
        _push_service = PushNotificationService()
    return _push_service


# Convenience functions for internal use (called from other services)
def notify_lead_assigned(db: Session, user_id: int, lead_name: str, amount: float, loan_purpose: str):
    """Send push notification when a lead is assigned."""
    service = _get_push_service()
    return service.send_to_user(
        db=db,
        user_id=user_id,
        notification_type="lead_assigned",
        template_data={"lead_name": lead_name, "amount": amount, "loan_purpose": loan_purpose},
        extra_data={"screen": "/leads"},
    )


def notify_appointment_reminder(db: Session, user_id: int, contact_name: str, time: str):
    """Send push notification for upcoming appointment."""
    service = _get_push_service()
    return service.send_to_user(
        db=db,
        user_id=user_id,
        notification_type="appointment_reminder",
        template_data={"contact_name": contact_name, "time": time},
        extra_data={"screen": "/calendar"},
    )


def notify_briefing_ready(db: Session, user_id: int, active_count: int, at_risk_count: int):
    """Send push notification when morning briefing is ready."""
    service = _get_push_service()
    return service.send_to_user(
        db=db,
        user_id=user_id,
        notification_type="briefing_ready",
        template_data={"active_count": active_count, "at_risk_count": at_risk_count},
        extra_data={"screen": "/dashboard"},
    )


def notify_document_received(db: Session, user_id: int, doc_type: str, borrower_name: str):
    """Send push notification when a document is received."""
    service = _get_push_service()
    return service.send_to_user(
        db=db,
        user_id=user_id,
        notification_type="document_received",
        template_data={"doc_type": doc_type, "borrower_name": borrower_name},
        extra_data={"screen": "/documents"},
    )


def notify_sla_alert(db: Session, user_id: int, loan_name: str, milestone: str, hours_remaining: int):
    """Send push notification for SLA warning."""
    service = _get_push_service()
    return service.send_to_user(
        db=db,
        user_id=user_id,
        notification_type="sla_alert",
        template_data={"loan_name": loan_name, "milestone": milestone, "hours_remaining": hours_remaining},
        extra_data={"screen": "/loans"},
    )
```

- [ ] **Step 2: Register push routes in _register_auth_security.py**

After the auth routes block (~line 64), add:

```python
# Include push notification trigger routes
try:
    from routes.push_notification_routes import router as push_router, setup_push_routes
    app.include_router(push_router)
    setup_push_routes(app, get_current_user)
    logger.info("Push notification routes loaded")
except Exception as e:
    logger.warning(f"Push notification routes not loaded: {e}")
```

- [ ] **Step 3: Wire briefing notification into morning briefing task**

In `backend/tasks/morning_briefing_tasks.py`, after `briefing.status = "delivered" if email_sent else "failed"` and before `db.commit()`, add:

```python
# Send push notification that briefing is ready
try:
    from routes.push_notification_routes import notify_briefing_ready
    at_risk_count = len(ctx.at_risk) if ctx.at_risk else 0
    active_count = ctx.pipeline.get("active_count", 0) if ctx.pipeline else 0
    notify_briefing_ready(db, user_id, active_count, at_risk_count)
except Exception as push_err:
    logger.debug("Push notification skipped: %s", push_err)
```

- [ ] **Step 4: Verify routes load**

Run: `cd backend && python -c "from routes.push_notification_routes import router, setup_push_routes; print('Push routes OK')"`
Expected: No errors

- [ ] **Step 5: Commit**

```bash
git add backend/routes/push_notification_routes.py backend/routes/_register_auth_security.py backend/tasks/morning_briefing_tasks.py
git commit -m "feat: add push notification trigger routes and wire to morning briefing"
```

---

### Task 4: Universal Links (Apple App Site Association)

**Context:** Universal links allow `app.perenniaai.com` URLs to open directly in the native app. Requires: (1) `.well-known/apple-app-site-association` JSON served from the backend, (2) Associated Domains entitlement in iOS, (3) Deep link handling in frontend.

**Files:**
- Create: `backend/routes/well_known_routes.py`
- Modify: `frontend/ios/App/App/App.entitlements` — add Associated Domains
- Modify: `frontend/ios/App/App/App.entitlements.release` — add Associated Domains
- Modify: `frontend/src/App.jsx` — add deep link listener

- [ ] **Step 1: Create .well-known routes**

```python
# backend/routes/well_known_routes.py
"""
.well-known routes for Apple Universal Links and Android App Links.

Apple requires this JSON to be served at:
  https://app.perenniaai.com/.well-known/apple-app-site-association

It must be served with Content-Type: application/json (no file extension).
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(tags=["Well Known"])

APPLE_APP_ID = "V5ZA5FZ2J8.com.perenniaai.crm"  # TeamID.BundleID

@router.get("/.well-known/apple-app-site-association")
async def apple_app_site_association():
    """Serve Apple App Site Association file for Universal Links."""
    return JSONResponse(
        content={
            "applinks": {
                "apps": [],
                "details": [
                    {
                        "appID": APPLE_APP_ID,
                        "paths": [
                            "/dashboard",
                            "/dashboard/*",
                            "/leads",
                            "/leads/*",
                            "/loans",
                            "/loans/*",
                            "/calendar",
                            "/calendar/*",
                            "/tasks",
                            "/tasks/*",
                            "/settings",
                            "/settings/*",
                            "/clients/*",
                            "/documents/*",
                            "/pipeline",
                            "/pipeline/*",
                            "NOT /api/*",
                            "NOT /admin/*",
                            "NOT /.well-known/*",
                        ],
                    }
                ],
            },
            "webcredentials": {
                "apps": [APPLE_APP_ID],
            },
        },
        media_type="application/json",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/.well-known/assetlinks.json")
async def android_asset_links():
    """Serve Android Digital Asset Links for App Links."""
    return JSONResponse(
        content=[
            {
                "relation": ["delegate_permission/common.handle_all_urls"],
                "target": {
                    "namespace": "android_app",
                    "package_name": "com.perenniaai.crm",
                    "sha256_cert_fingerprints": [
                        # TODO: Add signing certificate fingerprint after generating keystore
                        # Run: keytool -list -v -keystore release.keystore -alias perenniaai
                    ],
                },
            }
        ],
        media_type="application/json",
    )
```

- [ ] **Step 2: Register well-known routes in main app**

In `backend/routes/_register_auth_security.py`, add at the **beginning** of the function (these routes need no auth):

```python
# Well-known routes (no auth required — Apple/Google verification)
try:
    from routes.well_known_routes import router as well_known_router
    app.include_router(well_known_router)
    logger.info("Well-known routes loaded (AASA, assetlinks)")
except Exception as e:
    logger.warning(f"Well-known routes not loaded: {e}")
```

- [ ] **Step 3: Add Associated Domains to iOS entitlements (development)**

Replace `frontend/ios/App/App/App.entitlements`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>aps-environment</key>
	<string>development</string>
	<key>com.apple.developer.applesignin</key>
	<array>
		<string>Default</string>
	</array>
	<key>com.apple.developer.associated-domains</key>
	<array>
		<string>applinks:app.perenniaai.com</string>
		<string>webcredentials:app.perenniaai.com</string>
	</array>
</dict>
</plist>
```

- [ ] **Step 4: Add Associated Domains to iOS entitlements (release)**

Replace `frontend/ios/App/App/App.entitlements.release`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>aps-environment</key>
	<string>production</string>
	<key>com.apple.developer.applesignin</key>
	<array>
		<string>Default</string>
	</array>
	<key>com.apple.developer.associated-domains</key>
	<array>
		<string>applinks:app.perenniaai.com</string>
		<string>webcredentials:app.perenniaai.com</string>
	</array>
</dict>
</plist>
```

- [ ] **Step 5: Add deep link handler in frontend App.jsx**

At the top of App.jsx, add import and useEffect for deep links. The app uses `BrowserRouter`, so use `window.history.pushState` to trigger navigation:

```javascript
import { App as CapApp } from '@capacitor/app';
import { isNative } from './services/nativeServices';

// Inside the App component, add this useEffect:
useEffect(() => {
  if (!isNative) return;

  // Handle deep links when app is opened via universal link
  const listener = CapApp.addListener('appUrlOpen', (event) => {
    try {
      const url = new URL(event.url);
      const path = url.pathname + url.search;
      if (path && path !== '/') {
        // BrowserRouter: push state and trigger popstate for React Router
        window.history.pushState({}, '', path);
        window.dispatchEvent(new PopStateEvent('popstate'));
      }
    } catch (e) {
      console.error('Deep link error:', e);
    }
  });

  return () => {
    listener.then(l => l.remove());
  };
}, []);
```

- [ ] **Step 6: Verify AASA endpoint**

Run: `cd backend && python -c "from routes.well_known_routes import router; print('Well-known routes OK')"`
Expected: No errors

- [ ] **Step 7: Commit**

```bash
git add backend/routes/well_known_routes.py backend/routes/_register_auth_security.py frontend/ios/App/App/App.entitlements frontend/ios/App/App/App.entitlements.release frontend/src/App.jsx
git commit -m "feat: add universal links with AASA endpoint and deep link handling"
```

---

### Task 5: Offline Support (Network Detection + Cache Layer)

**Context:** The app currently has no offline support — all data is lost on reload when offline. This task adds: (1) network state detection via `@capacitor/network`, (2) API response caching via `@capacitor/preferences`, (3) an offline indicator banner. Service workers are intentionally disabled (see `frontend/public/index.html:64-71`).

**Files:**
- Create: `frontend/src/hooks/useNetworkStatus.js`
- Create: `frontend/src/hooks/useOfflineCache.js`
- Create: `frontend/src/components/OfflineIndicator.js`
- Create: `frontend/src/components/OfflineIndicator.css`
- Modify: `frontend/src/App.jsx` — add OfflineIndicator
- Modify: `frontend/package.json` — add @capacitor/network

- [ ] **Step 1: Install @capacitor/network**

Run: `cd frontend && npm install @capacitor/network && npx cap sync ios`

- [ ] **Step 2: Create network status hook**

```javascript
// frontend/src/hooks/useNetworkStatus.js
/**
 * useNetworkStatus — Detects online/offline state.
 * Uses @capacitor/network on native, navigator.onLine on web.
 */
import { useState, useEffect } from 'react';
import { Capacitor } from '@capacitor/core';

export function useNetworkStatus() {
  const [isOnline, setIsOnline] = useState(true);
  const [connectionType, setConnectionType] = useState('unknown');

  useEffect(() => {
    if (Capacitor.isNativePlatform()) {
      // Use Capacitor Network plugin
      let listener;
      import('@capacitor/network').then(({ Network }) => {
        // Get initial status
        Network.getStatus().then(status => {
          setIsOnline(status.connected);
          setConnectionType(status.connectionType);
        });

        // Listen for changes
        listener = Network.addListener('networkStatusChange', (status) => {
          setIsOnline(status.connected);
          setConnectionType(status.connectionType);
        });
      });

      return () => {
        if (listener) listener.then(l => l.remove());
      };
    } else {
      // Web fallback
      const handleOnline = () => setIsOnline(true);
      const handleOffline = () => setIsOnline(false);
      setIsOnline(navigator.onLine);

      window.addEventListener('online', handleOnline);
      window.addEventListener('offline', handleOffline);
      return () => {
        window.removeEventListener('online', handleOnline);
        window.removeEventListener('offline', handleOffline);
      };
    }
  }, []);

  return { isOnline, connectionType };
}

export default useNetworkStatus;
```

- [ ] **Step 3: Create offline cache hook**

```javascript
// frontend/src/hooks/useOfflineCache.js
/**
 * useOfflineCache — Caches API responses for offline access.
 * Uses @capacitor/preferences on native, localStorage on web.
 */
import { useCallback } from 'react';
import { Capacitor } from '@capacitor/core';

const CACHE_PREFIX = 'offline_cache_';
const CACHE_TTL_MS = 30 * 60 * 1000; // 30 minutes

async function setCache(key, data) {
  const entry = JSON.stringify({ data, timestamp: Date.now() });
  if (Capacitor.isNativePlatform()) {
    const { Preferences } = await import('@capacitor/preferences');
    await Preferences.set({ key: CACHE_PREFIX + key, value: entry });
  } else {
    try { localStorage.setItem(CACHE_PREFIX + key, entry); } catch {}
  }
}

async function getCache(key) {
  let raw;
  if (Capacitor.isNativePlatform()) {
    const { Preferences } = await import('@capacitor/preferences');
    const result = await Preferences.get({ key: CACHE_PREFIX + key });
    raw = result.value;
  } else {
    raw = localStorage.getItem(CACHE_PREFIX + key);
  }

  if (!raw) return null;
  try {
    const entry = JSON.parse(raw);
    // Check TTL
    if (Date.now() - entry.timestamp > CACHE_TTL_MS) return null;
    return entry.data;
  } catch {
    return null;
  }
}

/**
 * Hook that wraps a fetch function with offline caching.
 *
 * Usage:
 *   const { fetchWithCache } = useOfflineCache();
 *   const data = await fetchWithCache('dashboard', () => api.get('/api/v1/dashboard'));
 */
export function useOfflineCache() {
  const fetchWithCache = useCallback(async (cacheKey, fetchFn) => {
    try {
      // Try network first
      const data = await fetchFn();
      // Cache the successful response
      await setCache(cacheKey, data);
      return { data, fromCache: false };
    } catch (error) {
      // Network failed — try cache
      const cached = await getCache(cacheKey);
      if (cached) {
        return { data: cached, fromCache: true };
      }
      // No cache available
      throw error;
    }
  }, []);

  const getCached = useCallback(async (cacheKey) => {
    return await getCache(cacheKey);
  }, []);

  const invalidateCache = useCallback(async (cacheKey) => {
    if (Capacitor.isNativePlatform()) {
      const { Preferences } = await import('@capacitor/preferences');
      await Preferences.remove({ key: CACHE_PREFIX + cacheKey });
    } else {
      localStorage.removeItem(CACHE_PREFIX + cacheKey);
    }
  }, []);

  return { fetchWithCache, getCached, invalidateCache };
}

export default useOfflineCache;
```

- [ ] **Step 4: Create offline indicator component**

```css
/* frontend/src/components/OfflineIndicator.css */
.offline-indicator {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 10000;
  background: #f59e0b;
  color: #1a1a1a;
  text-align: center;
  padding: 6px 16px;
  font-size: 13px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding-top: calc(6px + env(safe-area-inset-top, 0px));
  transform: translateY(-100%);
  transition: transform 0.3s ease;
}

.offline-indicator.visible {
  transform: translateY(0);
}

.offline-indicator__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #dc2626;
  animation: pulse-dot 2s infinite;
}

@keyframes pulse-dot {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
```

```javascript
// frontend/src/components/OfflineIndicator.js
import React from 'react';
import { useNetworkStatus } from '../hooks/useNetworkStatus';
import './OfflineIndicator.css';

export function OfflineIndicator() {
  const { isOnline } = useNetworkStatus();

  return (
    <div className={`offline-indicator ${!isOnline ? 'visible' : ''}`}>
      <span className="offline-indicator__dot" />
      You're offline — showing cached data
    </div>
  );
}

export default OfflineIndicator;
```

- [ ] **Step 5: Add OfflineIndicator to App.js**

Import and render at the top of the App component's JSX:

```javascript
import { OfflineIndicator } from './components/OfflineIndicator';

// In the component return, before the Router:
<OfflineIndicator />
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/hooks/useNetworkStatus.js frontend/src/hooks/useOfflineCache.js frontend/src/components/OfflineIndicator.js frontend/src/components/OfflineIndicator.css frontend/src/App.jsx frontend/package.json frontend/package-lock.json
git commit -m "feat: add offline support with network detection, cache layer, and offline indicator"
```

---

### Task 6: App Store Preparation (Docs + Config)

**Context:** Build scripts and signing are in place. This task creates documentation for the manual steps needed: APNS credential setup, App Store submission checklist, and privacy policy URL configuration.

**Files:**
- Create: `docs/mobile/apns-setup-guide.md`
- Create: `docs/mobile/app-store-submission-checklist.md`
- Create: `backend/routes/privacy_routes.py` — serve privacy policy at known URL

- [ ] **Step 1: Create APNS setup guide**

```markdown
# APNS Setup Guide — Perennia AI iOS Push Notifications

## Prerequisites
- Apple Developer Account (Team ID: V5ZA5FZ2J8)
- Access to Apple Developer Portal

## Step 1: Create APNS Key

1. Go to https://developer.apple.com/account/resources/authkeys/list
2. Click "+" to create a new key
3. Name: "Perennia AI Push Key"
4. Check "Apple Push Notifications service (APNs)"
5. Click Continue → Register
6. **Download the .p8 file** (you can only download once!)
7. Note the **Key ID** (10-character string)

## Step 2: Store the Key

```bash
# On the server / Railway
mkdir -p /app/keys
# Upload your .p8 file to /app/keys/AuthKey_<KEY_ID>.p8
```

## Step 3: Set Environment Variables

Add these to Railway (or your deployment platform):

```
APNS_KEY_ID=<your 10-char key ID>
APNS_TEAM_ID=V5ZA5FZ2J8
APNS_KEY_PATH=/app/keys/AuthKey_<KEY_ID>.p8
APNS_BUNDLE_ID=com.perenniaai.crm
APNS_USE_SANDBOX=false
```

Set `APNS_USE_SANDBOX=true` for development/TestFlight builds.

## Step 4: Verify

```bash
curl -X POST https://api.perenniaai.com/api/v1/push/test \
  -H "Authorization: Bearer <your-token>"
```

Should return `{"success": true, "sent": 1, ...}`

## Troubleshooting

| Error | Fix |
|-------|-----|
| "APNS not configured" | Check env vars are set and .p8 file exists at APNS_KEY_PATH |
| "BadDeviceToken" | Device token is invalid or from wrong environment (sandbox vs production) |
| "TopicDisallowed" | Bundle ID doesn't match the APNS key's associated app |
```

- [ ] **Step 2: Create App Store submission checklist**

```markdown
# App Store Submission Checklist — Perennia AI

## App Store Connect Setup

- [ ] Create app in App Store Connect (bundle ID: com.perenniaai.crm)
- [ ] Set primary language: English (U.S.)
- [ ] Set primary category: Business
- [ ] Set secondary category: Finance

## App Information

- [ ] App name: "Perennia AI"
- [ ] Subtitle: "AI-Powered Mortgage CRM"
- [ ] Privacy policy URL: https://app.perenniaai.com/privacy
- [ ] Support URL: https://perenniaai.com/support

## App Store Listing

- [ ] Description (max 4000 chars)
- [ ] Keywords (max 100 chars, comma-separated)
- [ ] Screenshots: 6.7" (iPhone 15 Pro Max) — 3-5 screenshots required
- [ ] Screenshots: 6.5" (iPhone 14 Plus) — 3-5 screenshots required
- [ ] Screenshots: 5.5" (iPhone 8 Plus) — optional
- [ ] App icon: 1024x1024 PNG (no alpha, no rounded corners)

## Build & Upload

1. Increment version in package.json
2. Run: `cd frontend && npm run ios:build:testflight`
3. Run: `cd frontend && npm run ios:upload`
4. Wait for processing (10-30 min)

## Review Preparation

- [ ] Demo account credentials for App Review team
- [ ] Notes explaining any features requiring login
- [ ] Age rating questionnaire completed
- [ ] Export compliance (ITSAppUsesNonExemptEncryption = NO, already set in Info.plist)

## Pre-Submission Checks

- [ ] App loads on iPhone SE (smallest screen)
- [ ] App loads on iPhone 15 Pro Max (largest screen)
- [ ] Push notifications work on physical device
- [ ] Face ID / Touch ID login works
- [ ] All links open correctly (no broken routes)
- [ ] Offline indicator shows when airplane mode on
- [ ] App returns to foreground correctly after backgrounding
```

- [ ] **Step 3: Create privacy policy route**

```python
# backend/routes/privacy_routes.py
"""Privacy policy and terms — required for App Store submission."""
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["Legal"])


@router.get("/privacy")
async def privacy_policy():
    """Serve privacy policy page (required by App Store)."""
    return HTMLResponse(content="""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Privacy Policy — Perennia AI</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
               max-width: 800px; margin: 0 auto; padding: 20px; line-height: 1.6; color: #333; }
        h1 { color: #1a1a2e; }
        h2 { color: #16213e; margin-top: 2em; }
    </style>
</head>
<body>
    <h1>Privacy Policy</h1>
    <p><strong>Perennia AI, Inc.</strong><br>Last updated: March 2026</p>

    <h2>Information We Collect</h2>
    <p>We collect information you provide when using Perennia AI, including your name, email, phone number,
    and mortgage-related data. On mobile devices, we may collect device tokens for push notifications,
    biometric authentication preferences (stored locally on your device), and camera/photo access when
    you choose to capture documents.</p>

    <h2>How We Use Information</h2>
    <p>We use your information to provide CRM services, send notifications about your pipeline,
    generate AI-powered insights, and improve our platform.</p>

    <h2>Data Security</h2>
    <p>We use industry-standard encryption for data in transit (TLS) and at rest. Biometric data
    never leaves your device — it is processed by the device's secure enclave.</p>

    <h2>Push Notifications</h2>
    <p>You may opt in to push notifications for lead assignments, appointment reminders, and pipeline
    alerts. You can disable notifications at any time in your device settings or app preferences.</p>

    <h2>Third-Party Services</h2>
    <p>We use SendGrid (email), OpenAI (AI features), and Apple Push Notification service (iOS notifications).
    These services have their own privacy policies.</p>

    <h2>Contact</h2>
    <p>Questions? Email us at <a href="mailto:privacy@perenniaai.com">privacy@perenniaai.com</a></p>
</body>
</html>""")


@router.get("/terms")
async def terms_of_service():
    """Serve terms of service page."""
    return HTMLResponse(content="""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Terms of Service — Perennia AI</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
               max-width: 800px; margin: 0 auto; padding: 20px; line-height: 1.6; color: #333; }
        h1 { color: #1a1a2e; }
        h2 { color: #16213e; margin-top: 2em; }
    </style>
</head>
<body>
    <h1>Terms of Service</h1>
    <p><strong>Perennia AI, Inc.</strong><br>Last updated: March 2026</p>

    <h2>Acceptance</h2>
    <p>By using Perennia AI, you agree to these terms.</p>

    <h2>Service Description</h2>
    <p>Perennia AI is a mortgage CRM platform with AI-powered features for loan officers.</p>

    <h2>User Responsibilities</h2>
    <p>You are responsible for maintaining the confidentiality of your account credentials
    and for all activities under your account.</p>

    <h2>Contact</h2>
    <p>Email: <a href="mailto:support@perenniaai.com">support@perenniaai.com</a></p>
</body>
</html>""")
```

- [ ] **Step 4: Register privacy routes**

In `backend/routes/_register_auth_security.py`, add near the well-known routes (no auth):

```python
# Privacy and legal pages (no auth required)
try:
    from routes.privacy_routes import router as privacy_router
    app.include_router(privacy_router)
    logger.info("Privacy/legal routes loaded")
except Exception as e:
    logger.warning(f"Privacy routes not loaded: {e}")
```

- [ ] **Step 5: Commit**

```bash
git add docs/mobile/apns-setup-guide.md docs/mobile/app-store-submission-checklist.md backend/routes/privacy_routes.py backend/routes/_register_auth_security.py
git commit -m "feat: add App Store preparation — privacy policy, APNS guide, submission checklist"
```

---

### Task 7: Android Platform

**Context:** Currently iOS-only. This task adds the Android platform via Capacitor, configures it, and creates build scripts. FCM push notification support is already handled by the dispatch service (Task 2).

**Files:**
- Modify: `frontend/capacitor.config.ts` — add android block
- Create: `frontend/scripts/android-build.sh`
- Modify: `frontend/package.json` — add android scripts

- [ ] **Step 1: Add Android platform**

Run:
```bash
cd frontend && npx cap add android
```

This generates the `frontend/android/` directory with a full Android Studio project.

- [ ] **Step 2: Add Android config to capacitor.config.ts**

Modify `frontend/capacitor.config.ts` to add the android block:

```typescript
import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: process.env.CAPACITOR_APP_ID || 'com.perenniaai.crm',
  appName: process.env.CAPACITOR_APP_NAME || 'Perennia AI',
  webDir: 'build',
  server: {
    ...(process.env.CAPACITOR_SERVER_URL ? { url: process.env.CAPACITOR_SERVER_URL, cleartext: true } : {}),
    allowNavigation: [
      ...(process.env.CAPACITOR_ALLOWED_DOMAINS?.split(',') || []),
      'perenniaai.com', 'app.perenniaai.com', 'api.perenniaai.com', 'www.perenniaai.com', 'localhost', '127.0.0.1',
    ],
  },
  ios: {
    contentInset: 'automatic',
    allowsLinkPreview: false,
  },
  android: {
    allowMixedContent: false,
    backgroundColor: '#1a1a2e',
  },
};

export default config;
```

- [ ] **Step 3: Update usePushNotifications.js for Android platform detection**

In `frontend/src/hooks/usePushNotifications.js`, change the hardcoded `platform: 'ios'` (line 48) to:

```javascript
platform: Capacitor.getPlatform(),  // 'ios' or 'android'
```

Add the import at top: `import { Capacitor } from '@capacitor/core';`

- [ ] **Step 4: Create Android build script**

```bash
#!/bin/bash
set -e

# Android Build Script for Perennia AI
# Usage: ./scripts/android-build.sh [debug|release]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$(dirname "$SCRIPT_DIR")"
ANDROID_DIR="$FRONTEND_DIR/android"

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

BUILD_TYPE="${1:-debug}"

echo ""
log_info "========================================"
log_info "  Perennia AI Android Build"
log_info "========================================"
log_info "Build Type: $BUILD_TYPE"
echo ""

# Check for required tools
if ! command -v java &> /dev/null; then
    log_error "Java not found. Install JDK 17+."
    exit 1
fi

cd "$FRONTEND_DIR"

# Step 1: Build web assets
log_info "Step 1: Building web assets..."
npm run build

# Step 2: Sync Capacitor
log_info "Step 2: Syncing Capacitor..."
npx cap sync android

# Step 3: Build Android
cd "$ANDROID_DIR"

if [ "$BUILD_TYPE" = "release" ]; then
    log_info "Step 3: Building release APK..."
    ./gradlew assembleRelease

    APK_PATH="app/build/outputs/apk/release/app-release.apk"
    if [ -f "$APK_PATH" ]; then
        log_info "Release APK: $ANDROID_DIR/$APK_PATH"
    else
        log_error "Release APK not found!"
        exit 1
    fi
else
    log_info "Step 3: Building debug APK..."
    ./gradlew assembleDebug

    APK_PATH="app/build/outputs/apk/debug/app-debug.apk"
    if [ -f "$APK_PATH" ]; then
        log_info "Debug APK: $ANDROID_DIR/$APK_PATH"
    else
        log_error "Debug APK not found!"
        exit 1
    fi
fi

echo ""
log_info "========================================"
log_info "  Build Complete!"
log_info "========================================"
echo ""
```

Make executable: `chmod +x frontend/scripts/android-build.sh`

- [ ] **Step 5: Add Android scripts to package.json**

Add to `frontend/package.json` scripts:

```json
"android:build": "./scripts/android-build.sh debug",
"android:build:release": "./scripts/android-build.sh release",
"android:open": "npx cap open android",
"android:sync": "npx cap sync android"
```

- [ ] **Step 6: Sync and verify**

Run:
```bash
cd frontend && npx cap sync android
```

- [ ] **Step 7: Commit**

```bash
git add frontend/capacitor.config.ts frontend/scripts/android-build.sh frontend/package.json frontend/src/hooks/usePushNotifications.js
# Note: frontend/android/ may be gitignored. If not, add it too:
git add frontend/android/ 2>/dev/null || true
git commit -m "feat: add Android platform support with build scripts and FCM-ready config"
```

---

## Post-Implementation Verification

After all tasks are complete:

1. **Backend health check**: `cd backend && python -c "from database.models import DeviceToken; from services.push_notification_service import PushNotificationService; from routes.well_known_routes import router; print('All imports OK')"`

2. **Tests pass**: `cd backend && python -m pytest tests/test_device_token_model.py tests/test_push_notification_service.py -v`

3. **iOS build succeeds**: `cd frontend && npm run ios:dev` (requires Xcode)

4. **Frontend build succeeds**: `cd frontend && npm run build`

## Manual Steps Required (Post-Merge)

These require Apple Developer / Google Developer account access:

| Step | Owner | Guide |
|------|-------|-------|
| Create APNS key and set env vars | Tim | `docs/mobile/apns-setup-guide.md` |
| Enable Associated Domains in Apple Developer Portal | Tim | Apple Developer → Certificates → App ID → Associated Domains |
| Create App Store Connect listing | Tim | `docs/mobile/app-store-submission-checklist.md` |
| Upload first TestFlight build | Tim | `npm run ios:build:testflight && npm run ios:upload` |
| Create Firebase project for FCM (Android) | Tim | Firebase Console → Add Android app → Download google-services.json |
| Generate Android signing keystore | Tim | `keytool -genkey -v -keystore release.keystore -alias perenniaai` |
