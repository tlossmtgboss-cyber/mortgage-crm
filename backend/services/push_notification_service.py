"""
Push Notification Service

Sends push notifications to iOS (APNs) and Android (FCM) devices.
- APNs: Uses JWT auth + httpx HTTP/2 for async delivery
- FCM: Uses firebase-admin SDK
- Handles token invalidation on APNs 410 (Unregistered) responses
- Supports alert notifications, silent data pushes, and batch sends
"""
import logging
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# =============================================================================
# Notification types matching frontend NOTIFICATION_CATEGORIES
# =============================================================================

class NotificationType(str, Enum):
    LEAD_ASSIGNED = "lead_assigned"
    LOAN_UPDATE = "loan_update"
    APPOINTMENT_REMINDER = "appointment_reminder"
    SLA_ALERT = "sla_alert"
    BRIEFING_READY = "briefing_ready"
    DOCUMENT_RECEIVED = "document_received"
    COMPLIANCE_ALERT = "compliance_alert"
    TASK_ASSIGNED = "task_assigned"
    ESIGN_COMPLETED = "esign_completed"
    SMS_ESCALATION = "sms_escalation"
    GENERAL = "general"


NOTIFICATION_TEMPLATES = {
    "lead_assigned": {
        "title": "New Lead Assigned",
        "body": "{lead_name} — ${amount:,.0f} {loan_purpose}",
    },
    "loan_update": {
        "title": "Loan Update",
        "body": "{borrower_name} moved to {stage}",
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
    "compliance_alert": {
        "title": "Compliance Alert",
        "body": "{alert_type}: {description}",
    },
    "task_assigned": {
        "title": "New Task",
        "body": "{task_title}",
    },
    "esign_completed": {
        "title": "eSign Complete",
        "body": "{borrower_name} signed {document_name}",
    },
    "sms_escalation": {
        "title": "Aria needs your help",
        "body": "{contact_name}: {reason}",
    },
    "general": {
        "title": "{title}",
        "body": "{body}",
    },
}

# Default notification categories (all enabled)
DEFAULT_CATEGORIES = {
    "lead_assigned": True,
    "loan_update": True,
    "appointment_reminder": True,
    "sla_alert": True,
    "briefing_ready": True,
    "document_received": True,
    "compliance_alert": True,
    "task_assigned": True,
    "esign_completed": True,
    "sms_escalation": True,
    "general": True,
}


# =============================================================================
# APNs JWT Token Generation
# =============================================================================

class APNsTokenManager:
    """Manages JWT tokens for APNs authentication.

    APNs requires a short-lived JWT signed with the team's auth key.
    Tokens are valid for up to 60 minutes; we refresh after 50 minutes.
    """

    def __init__(self, key_id: str, team_id: str, key_path: str):
        self._key_id = key_id
        self._team_id = team_id
        self._key_path = key_path
        self._private_key: Optional[str] = None
        self._token: Optional[str] = None
        self._token_issued_at: float = 0

    def _load_key(self) -> str:
        if self._private_key is None:
            with open(self._key_path, "r") as f:
                self._private_key = f.read()
        return self._private_key

    def get_token(self) -> str:
        """Get a valid APNs JWT token, refreshing if needed."""
        now = time.time()
        # Refresh if token is older than 50 minutes (buffer before 60-minute expiry)
        if self._token and (now - self._token_issued_at) < 3000:
            return self._token

        try:
            import jwt as pyjwt
        except ImportError:
            # PyJWT is the only JWT library (python-jose removed per audit C2)
            raise

        key = self._load_key()
        issued_at = int(now)
        headers = {"alg": "ES256", "kid": self._key_id}
        payload = {"iss": self._team_id, "iat": issued_at}

        self._token = pyjwt.encode(payload, key, algorithm="ES256", headers=headers)
        self._token_issued_at = now
        logger.debug("APNs JWT token refreshed")
        return self._token


# =============================================================================
# Push Notification Service
# =============================================================================

class PushNotificationService:
    """Dispatches push notifications to registered devices.

    Public API:
        send_to_user(db, user_id, title, body, data, badge) -> dict
        send_to_users(db, user_ids, title, body, data) -> dict
        send_silent(db, user_id, data) -> dict
    """

    def __init__(self):
        self._apns_token_manager: Optional[APNsTokenManager] = None
        self._apns_configured: Optional[bool] = None
        self._fcm_initialized = False
        self._httpx_client = None

    # -------------------------------------------------------------------------
    # Configuration
    # -------------------------------------------------------------------------

    def _is_apns_configured(self) -> bool:
        if self._apns_configured is not None:
            return self._apns_configured

        from push_config import is_apns_configured, APNS_KEY_ID, APNS_TEAM_ID, APNS_KEY_PATH
        self._apns_configured = is_apns_configured()
        if self._apns_configured:
            self._apns_token_manager = APNsTokenManager(
                key_id=APNS_KEY_ID,
                team_id=APNS_TEAM_ID,
                key_path=APNS_KEY_PATH,
            )
        return self._apns_configured

    def _get_apns_url(self, device_token: str) -> str:
        from push_config import APNS_USE_SANDBOX
        host = "api.sandbox.push.apple.com" if APNS_USE_SANDBOX else "api.push.apple.com"
        return f"https://{host}/3/device/{device_token}"

    def _get_httpx_client(self):
        """Get or create an httpx client with HTTP/2 support for APNs."""
        if self._httpx_client is not None:
            return self._httpx_client
        try:
            import httpx
            self._httpx_client = httpx.Client(http2=True, timeout=10.0)
            return self._httpx_client
        except ImportError:
            logger.error("httpx not installed — cannot send APNs notifications")
            return None
        except Exception as e:
            logger.error("Failed to create httpx client: %s", e)
            return None

    def _init_fcm(self) -> bool:
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

    # -------------------------------------------------------------------------
    # Token management
    # -------------------------------------------------------------------------

    def get_active_tokens(self, db: Session, user_id: int) -> list:
        """Get all active device tokens for a user."""
        from database.models.device_token import DeviceToken
        return db.query(DeviceToken).filter(
            DeviceToken.user_id == user_id,
            DeviceToken.is_active == True,
        ).all()

    def _deactivate_token(self, db: Session, device_token_str: str, reason: str = "unregistered"):
        """Mark a device token as inactive (e.g., APNs returned 410)."""
        from database.models.device_token import DeviceToken
        try:
            row = db.query(DeviceToken).filter(
                DeviceToken.device_token == device_token_str
            ).first()
            if row:
                row.is_active = False
                row.failure_count = (row.failure_count or 0) + 1
                row.updated_at = datetime.now(timezone.utc)
                db.commit()
                logger.info(
                    "Deactivated token %s...%s (reason: %s)",
                    device_token_str[:8], device_token_str[-4:], reason,
                )
        except Exception as e:
            logger.error("Error deactivating token: %s", e)
            db.rollback()

    def _increment_failure(self, db: Session, device_token_str: str):
        """Increment failure count; deactivate after 3 consecutive failures."""
        from database.models.device_token import DeviceToken
        try:
            row = db.query(DeviceToken).filter(
                DeviceToken.device_token == device_token_str
            ).first()
            if row:
                row.failure_count = (row.failure_count or 0) + 1
                if row.failure_count >= 3:
                    row.is_active = False
                    logger.warning(
                        "Token %s...%s deactivated after %d failures",
                        device_token_str[:8], device_token_str[-4:], row.failure_count,
                    )
                db.commit()
        except Exception as e:
            logger.error("Error incrementing failure count: %s", e)
            db.rollback()

    def _record_success(self, db: Session, device_token_str: str):
        """Reset failure count and update last_used on successful send."""
        from database.models.device_token import DeviceToken
        try:
            row = db.query(DeviceToken).filter(
                DeviceToken.device_token == device_token_str
            ).first()
            if row:
                row.failure_count = 0
                row.last_used_at = datetime.now(timezone.utc)
                db.commit()
        except Exception as e:
            logger.error("Error recording success: %s", e)
            db.rollback()

    # -------------------------------------------------------------------------
    # Preference checking
    # -------------------------------------------------------------------------

    def _check_preference(self, db: Session, user_id: int, notification_type: str) -> bool:
        """Check if user has opted in to this notification category.

        Returns True if the notification should be sent (default is send).
        """
        from database.models.device_token import PushNotificationPreference
        try:
            pref = db.query(PushNotificationPreference).filter(
                PushNotificationPreference.user_id == user_id,
            ).first()

            if not pref:
                return True  # No preferences set = all enabled

            if pref.muted:
                return False  # Global mute

            categories = pref.categories or {}
            # Default to enabled if category not explicitly set
            return categories.get(notification_type, True)

        except Exception as e:
            logger.error("Error checking push preference: %s", e)
            return True  # Fail open — send the notification

    # -------------------------------------------------------------------------
    # iOS (APNs) via httpx HTTP/2
    # -------------------------------------------------------------------------

    def _build_apns_payload(
        self,
        title: Optional[str] = None,
        body: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        badge: Optional[int] = None,
        silent: bool = False,
    ) -> dict:
        """Build APNs JSON payload.

        For alert notifications: {"aps": {"alert": {...}, "badge": N, "sound": "default"}, ...data}
        For silent pushes:       {"aps": {"content-available": 1}, ...data}
        """
        aps: Dict[str, Any] = {}

        if silent:
            aps["content-available"] = 1
        else:
            alert: Dict[str, str] = {}
            if title:
                alert["title"] = title
            if body:
                alert["body"] = body
            aps["alert"] = alert
            aps["sound"] = "default"

        if badge is not None:
            aps["badge"] = badge

        payload = {"aps": aps}
        if data:
            payload.update(data)
        return payload

    def _send_ios(
        self,
        db: Session,
        device_token: str,
        title: Optional[str] = None,
        body: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        badge: Optional[int] = None,
        silent: bool = False,
    ) -> bool:
        """Send a notification to an iOS device via APNs HTTP/2."""
        if not self._is_apns_configured():
            logger.warning("APNs not configured — skipping iOS push")
            return False

        client = self._get_httpx_client()
        if not client:
            return False

        try:
            from push_config import APNS_BUNDLE_ID

            token = self._apns_token_manager.get_token()
            url = self._get_apns_url(device_token)

            payload = self._build_apns_payload(
                title=title, body=body, data=data, badge=badge, silent=silent,
            )

            headers = {
                "authorization": f"bearer {token}",
                "apns-topic": APNS_BUNDLE_ID,
                "apns-push-type": "background" if silent else "alert",
                "apns-priority": "5" if silent else "10",
            }

            response = client.post(url, json=payload, headers=headers)

            if response.status_code == 200:
                logger.info(
                    "APNs sent to %s...%s (%s)",
                    device_token[:8], device_token[-4:],
                    "silent" if silent else "alert",
                )
                self._record_success(db, device_token)
                return True

            elif response.status_code == 410:
                # Token is no longer valid — device unregistered
                logger.warning("APNs 410: token %s...%s unregistered", device_token[:8], device_token[-4:])
                self._deactivate_token(db, device_token, reason="apns_410_unregistered")
                return False

            elif response.status_code == 400:
                # Bad request — likely malformed token
                error_body = response.text
                logger.error("APNs 400: %s (token: %s...%s)", error_body, device_token[:8], device_token[-4:])
                if "BadDeviceToken" in error_body:
                    self._deactivate_token(db, device_token, reason="bad_device_token")
                return False

            else:
                logger.error(
                    "APNs error %d: %s (token: %s...%s)",
                    response.status_code, response.text,
                    device_token[:8], device_token[-4:],
                )
                self._increment_failure(db, device_token)
                return False

        except Exception as e:
            logger.error("APNs send exception: %s", e)
            self._increment_failure(db, device_token)
            return False

    # -------------------------------------------------------------------------
    # Android (FCM)
    # -------------------------------------------------------------------------

    def _send_android(
        self,
        db: Session,
        device_token: str,
        title: Optional[str] = None,
        body: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        silent: bool = False,
    ) -> bool:
        """Send a notification to an Android device via FCM."""
        if not self._init_fcm():
            logger.warning("FCM not configured — skipping Android push")
            return False

        try:
            from firebase_admin import messaging
            from firebase_admin.exceptions import NotFoundError, InvalidArgumentError

            notification = None
            if not silent and (title or body):
                notification = messaging.Notification(title=title, body=body)

            # FCM data values must be strings
            str_data = {k: str(v) for k, v in (data or {}).items()}

            message = messaging.Message(
                notification=notification,
                data=str_data,
                token=device_token,
            )

            response = messaging.send(message)
            logger.info("FCM sent: %s (token: %s...%s)", response, device_token[:8], device_token[-4:])
            self._record_success(db, device_token)
            return True

        except Exception as e:
            error_str = str(e)
            # Handle token invalidation
            if "registration-token-not-registered" in error_str.lower() or "not found" in error_str.lower():
                logger.warning("FCM token invalid: %s...%s", device_token[:8], device_token[-4:])
                self._deactivate_token(db, device_token, reason="fcm_not_registered")
            else:
                logger.error("FCM send error: %s", e)
                self._increment_failure(db, device_token)
            return False

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def send_to_user(
        self,
        db: Session,
        user_id: int,
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None,
        badge: Optional[int] = None,
        notification_type: str = "general",
        template_data: Optional[Dict[str, Any]] = None,
        custom_title: Optional[str] = None,
        custom_body: Optional[str] = None,
        extra_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, int]:
        """Send a push notification to all of a user's active devices.

        Supports two calling conventions:
        1. Direct: send_to_user(db, user_id, title="...", body="...", data={...})
        2. Template: send_to_user(db, user_id, notification_type="lead_assigned",
                                  template_data={...}, extra_data={...})

        Returns dict with keys: sent, failed, skipped
        """
        # Check user preference for this category
        if not self._check_preference(db, user_id, notification_type):
            logger.info("Push suppressed for user %d — category '%s' muted", user_id, notification_type)
            return {"sent": 0, "failed": 0, "skipped": 1}

        tokens = self.get_active_tokens(db, user_id)
        if not tokens:
            return {"sent": 0, "failed": 0, "skipped": 0}

        # Resolve title/body from template if using template calling convention
        resolved_title = custom_title or title
        resolved_body = custom_body or body

        if template_data and notification_type in NOTIFICATION_TEMPLATES:
            template = NOTIFICATION_TEMPLATES[notification_type]
            try:
                if not custom_title:
                    resolved_title = template["title"].format(**template_data)
                if not custom_body:
                    resolved_body = template["body"].format(**template_data)
            except (KeyError, ValueError, IndexError) as e:
                logger.warning("Template format error for %s: %s", notification_type, e)

        # Build notification data payload
        send_data = {"type": notification_type}
        if data:
            send_data.update(data)
        if extra_data:
            send_data.update(extra_data)

        result = {"sent": 0, "failed": 0, "skipped": 0}

        for token_record in tokens:
            if token_record.platform == "ios":
                ok = self._send_ios(
                    db, token_record.device_token,
                    title=resolved_title, body=resolved_body,
                    data=send_data, badge=badge,
                )
            elif token_record.platform == "android":
                ok = self._send_android(
                    db, token_record.device_token,
                    title=resolved_title, body=resolved_body,
                    data=send_data,
                )
            else:
                result["skipped"] += 1
                continue

            if ok:
                result["sent"] += 1
            else:
                result["failed"] += 1

        logger.info("Push to user %d: %s", user_id, result)
        return result

    def send_to_users(
        self,
        db: Session,
        user_ids: List[int],
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None,
        notification_type: str = "general",
        **kwargs,
    ) -> Dict[str, int]:
        """Send a push notification to multiple users.

        Returns aggregated dict with keys: sent, failed, skipped
        """
        totals = {"sent": 0, "failed": 0, "skipped": 0}
        for uid in user_ids:
            r = self.send_to_user(
                db, uid,
                title=title, body=body,
                data=data, notification_type=notification_type,
                **kwargs,
            )
            for k in totals:
                totals[k] += r[k]

        logger.info("Batch push to %d users: %s", len(user_ids), totals)
        return totals

    def send_silent(
        self,
        db: Session,
        user_id: int,
        data: Dict[str, Any],
    ) -> Dict[str, int]:
        """Send a silent/background data push to a user.

        Used for background data sync (e.g., badge count update, cache invalidation).
        No user-visible alert; triggers background processing in the app.
        """
        tokens = self.get_active_tokens(db, user_id)
        if not tokens:
            return {"sent": 0, "failed": 0, "skipped": 0}

        result = {"sent": 0, "failed": 0, "skipped": 0}

        for token_record in tokens:
            if token_record.platform == "ios":
                ok = self._send_ios(
                    db, token_record.device_token,
                    data=data, silent=True,
                )
            elif token_record.platform == "android":
                ok = self._send_android(
                    db, token_record.device_token,
                    data=data, silent=True,
                )
            else:
                result["skipped"] += 1
                continue

            if ok:
                result["sent"] += 1
            else:
                result["failed"] += 1

        return result

    def close(self):
        """Clean up httpx client on shutdown."""
        if self._httpx_client:
            try:
                self._httpx_client.close()
            except Exception:
                pass
            self._httpx_client = None


# =============================================================================
# Module-level convenience functions
# =============================================================================
# These are importable by other services that need a quick fire-and-forget push.
# e.g.  from services.push_notification_service import send_push_to_user

_singleton_service: Optional[PushNotificationService] = None


def _get_service() -> PushNotificationService:
    global _singleton_service
    if _singleton_service is None:
        _singleton_service = PushNotificationService()
    return _singleton_service


def send_push_to_user(
    user_id: int,
    title: str,
    body: str,
    data: Optional[Dict[str, Any]] = None,
    notification_type: str = "general",
    db: Optional[Session] = None,
) -> Dict[str, int]:
    """Send a push notification to a user's registered devices.

    If no db session is provided, creates one from the session factory.
    Gracefully returns zeros if push sending fails for any reason.
    """
    try:
        if db is None:
            from db import SessionLocal
            db = SessionLocal()
            _owns_session = True
            # TENANT-017: No org_id available for send_push_to_user;
            # push tokens are user-scoped, not tenant-scoped
        else:
            _owns_session = False

        try:
            service = _get_service()
            result = service.send_to_user(
                db=db,
                user_id=user_id,
                title=title,
                body=body,
                data=data or {},
                notification_type=notification_type,
            )
            return result
        finally:
            if _owns_session:
                db.close()

    except Exception as e:
        logger.error("send_push_to_user failed for user %d: %s", user_id, e)
        return {"sent": 0, "failed": 0, "skipped": 0}


def send_push_notification(
    user_id: int,
    title: str,
    body: str,
    data: Optional[Dict[str, Any]] = None,
    notification_type: str = "general",
    db: Optional[Session] = None,
) -> Dict[str, int]:
    """Alias for send_push_to_user — matches the import expected by
    scheduling_conversation_service and other callers.
    """
    return send_push_to_user(
        user_id=user_id,
        title=title,
        body=body,
        data=data,
        notification_type=notification_type,
        db=db,
    )


def send_push_to_org(
    org_id: int,
    title: str,
    body: str,
    data: Optional[Dict[str, Any]] = None,
    notification_type: str = "general",
    db: Optional[Session] = None,
) -> Dict[str, int]:
    """Send a push notification to all users in an organization.

    If no db session is provided, creates one from the session factory.
    """
    try:
        if db is None:
            from db import SessionLocal
            db = SessionLocal()
            _owns_session = True
            # TENANT-017: Set RLS context for org-scoped push
            try:
                from database.tenant_mixin import set_tenant_context
                set_tenant_context(db, org_id)
            except Exception:
                pass
        else:
            _owns_session = False

        try:
            from database.models.device_token import DeviceToken
            # Get distinct user IDs with active tokens in this org
            user_ids = [
                row[0] for row in db.query(DeviceToken.user_id).filter(
                    DeviceToken.organization_id == org_id,
                    DeviceToken.is_active == True,
                ).distinct().all()
            ]

            service = _get_service()
            return service.send_to_users(
                db=db,
                user_ids=user_ids,
                title=title,
                body=body,
                data=data or {},
                notification_type=notification_type,
            )
        finally:
            if _owns_session:
                db.close()

    except Exception as e:
        logger.error("send_push_to_org failed for org %d: %s", org_id, e)
        return {"sent": 0, "failed": 0, "skipped": 0}


async def send_notification_with_push(
    user_id: int,
    title: str,
    body: str,
    data: Optional[Dict[str, Any]] = None,
    db: Optional[Session] = None,
    notification_type: str = "general",
) -> Dict[str, Any]:
    """Async helper that creates an in-app notification AND sends a push.

    Other services should call this when they want both an in-app record
    and an actual device push in a single call.
    """
    result = {"in_app": False, "push": {"sent": 0, "failed": 0, "skipped": 0}}

    if db is None:
        from db import SessionLocal
        db = SessionLocal()
        _owns_session = True
        # TENANT-017: No org_id available here; user-scoped notification
    else:
        _owns_session = False

    try:
        # 1) Create in-app notification record
        try:
            from database.models.security import Notification
            notif = Notification(
                user_id=user_id,
                title=title,
                message=body[:500],
                type=notification_type,
                is_read=False,
            )
            db.add(notif)
            db.flush()
            result["in_app"] = True
        except Exception as e:
            logger.warning("In-app notification creation failed: %s", e)

        # 2) Send push notification to registered devices
        service = _get_service()
        push_result = service.send_to_user(
            db=db,
            user_id=user_id,
            title=title,
            body=body,
            data=data or {},
            notification_type=notification_type,
        )
        result["push"] = push_result

        db.commit()
    except Exception as e:
        logger.error("send_notification_with_push failed: %s", e)
        db.rollback()
    finally:
        if _owns_session:
            db.close()

    return result
