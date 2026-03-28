"""Push notification configuration — APNS (iOS) and FCM (Android)."""
import os
import logging

logger = logging.getLogger(__name__)

APNS_KEY_ID = os.getenv("APNS_KEY_ID")
APNS_TEAM_ID = os.getenv("APNS_TEAM_ID", "V5ZA5FZ2J8")
APNS_KEY_PATH = os.getenv("APNS_KEY_PATH")
APNS_BUNDLE_ID = os.getenv("APNS_BUNDLE_ID", "com.perenniaai.crm")
APNS_USE_SANDBOX = os.getenv("APNS_USE_SANDBOX", "true").lower() == "true"
FCM_CREDENTIALS_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")


def is_apns_configured():
    configured = bool(APNS_KEY_ID and APNS_KEY_PATH and os.path.exists(APNS_KEY_PATH or ""))
    if not configured:
        logger.debug("APNS not configured — set APNS_KEY_ID, APNS_KEY_PATH env vars")
    return configured


def is_fcm_configured():
    configured = bool(FCM_CREDENTIALS_PATH and os.path.exists(FCM_CREDENTIALS_PATH or ""))
    if not configured:
        logger.debug("FCM not configured — set GOOGLE_APPLICATION_CREDENTIALS env var")
    return configured
