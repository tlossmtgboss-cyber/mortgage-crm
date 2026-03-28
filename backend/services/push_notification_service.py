"""
Push Notification Dispatch Service

Sends push notifications to iOS (APNS) and Android (FCM) devices.
Uses token-based APNS auth and firebase-admin for FCM.
"""
import logging
from enum import Enum

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class NotificationType(str, Enum):
    LEAD_ASSIGNED = "lead_assigned"
    APPOINTMENT_REMINDER = "appointment_reminder"
    SLA_ALERT = "sla_alert"
    BRIEFING_READY = "briefing_ready"
    DOCUMENT_RECEIVED = "document_received"
    GENERAL = "general"


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
        from database.models.device_token import DeviceToken
        tokens = db.query(DeviceToken).filter(
            DeviceToken.user_id == user_id,
            DeviceToken.is_active == True,
        ).all()
        return tokens

    def _build_apns_payload(self, title: str, body: str, data: dict = None, badge: int = None):
        from apns2.payload import Payload
        return Payload(
            alert={"title": title, "body": body},
            badge=badge,
            sound="default",
            custom=data or {},
        )

    def _build_fcm_message(self, token: str, title: str, body: str, data: dict = None):
        from firebase_admin import messaging
        return messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            data={k: str(v) for k, v in (data or {}).items()},
            token=token,
        )

    def _send_ios(self, device_token: str, title: str, body: str, data: dict = None, badge: int = None) -> bool:
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
                logger.error("APNS failed: %s", response.description)
                return False
        except Exception as e:
            logger.error("APNS send error: %s", e)
            return False

    def _send_android(self, device_token: str, title: str, body: str, data: dict = None) -> bool:
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

    def send_to_user(self, db: Session, user_id: int, notification_type: str,
                     template_data: dict = None, custom_title: str = None,
                     custom_body: str = None, extra_data: dict = None) -> dict:
        tokens = self.get_active_tokens(db, user_id)
        if not tokens:
            return {"sent": 0, "failed": 0, "skipped": 0}

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

        logger.info("Push to user %d: %s", user_id, result)
        return result

    def send_to_users(self, db: Session, user_ids: list, **kwargs) -> dict:
        totals = {"sent": 0, "failed": 0, "skipped": 0}
        for uid in user_ids:
            r = self.send_to_user(db, uid, **kwargs)
            for k in totals:
                totals[k] += r[k]
        return totals
