"""Tests for PushNotificationService and related models."""
import pytest


def test_service_import():
    from services.push_notification_service import PushNotificationService
    assert PushNotificationService is not None


def test_notification_types():
    from services.push_notification_service import NotificationType
    assert hasattr(NotificationType, 'LEAD_ASSIGNED')
    assert hasattr(NotificationType, 'LOAN_UPDATE')
    assert hasattr(NotificationType, 'APPOINTMENT_REMINDER')
    assert hasattr(NotificationType, 'SLA_ALERT')
    assert hasattr(NotificationType, 'BRIEFING_READY')
    assert hasattr(NotificationType, 'DOCUMENT_RECEIVED')
    assert hasattr(NotificationType, 'COMPLIANCE_ALERT')
    assert hasattr(NotificationType, 'TASK_ASSIGNED')
    assert hasattr(NotificationType, 'ESIGN_COMPLETED')
    assert hasattr(NotificationType, 'GENERAL')


def test_notification_templates():
    from services.push_notification_service import NOTIFICATION_TEMPLATES
    expected_types = [
        'lead_assigned', 'loan_update', 'appointment_reminder',
        'sla_alert', 'briefing_ready', 'document_received',
        'compliance_alert', 'task_assigned', 'esign_completed', 'general',
    ]
    for nt in expected_types:
        assert nt in NOTIFICATION_TEMPLATES, f"Missing template: {nt}"
        assert 'title' in NOTIFICATION_TEMPLATES[nt]
        assert 'body' in NOTIFICATION_TEMPLATES[nt]


def test_default_categories():
    from services.push_notification_service import DEFAULT_CATEGORIES
    assert isinstance(DEFAULT_CATEGORIES, dict)
    assert all(v is True for v in DEFAULT_CATEGORIES.values())
    assert 'lead_assigned' in DEFAULT_CATEGORIES
    assert 'sla_alert' in DEFAULT_CATEGORIES
    assert 'general' in DEFAULT_CATEGORIES


def test_service_instantiation():
    from services.push_notification_service import PushNotificationService
    service = PushNotificationService()
    assert service._apns_token_manager is None
    assert service._fcm_initialized is False
    assert service._httpx_client is None


def test_apns_payload_alert():
    from services.push_notification_service import PushNotificationService
    service = PushNotificationService()
    payload = service._build_apns_payload(
        title="Test Title",
        body="Test Body",
        data={"type": "general", "route": "/dashboard"},
        badge=5,
    )
    assert payload["aps"]["alert"]["title"] == "Test Title"
    assert payload["aps"]["alert"]["body"] == "Test Body"
    assert payload["aps"]["badge"] == 5
    assert payload["aps"]["sound"] == "default"
    assert payload["type"] == "general"
    assert payload["route"] == "/dashboard"


def test_apns_payload_silent():
    from services.push_notification_service import PushNotificationService
    service = PushNotificationService()
    payload = service._build_apns_payload(
        data={"action": "sync"},
        silent=True,
    )
    assert payload["aps"]["content-available"] == 1
    assert "alert" not in payload["aps"]
    assert "sound" not in payload["aps"]
    assert payload["action"] == "sync"


def test_apns_payload_silent_no_badge():
    from services.push_notification_service import PushNotificationService
    service = PushNotificationService()
    payload = service._build_apns_payload(silent=True)
    assert "badge" not in payload["aps"]
    assert payload["aps"]["content-available"] == 1


def test_device_token_model_import():
    from database.models.device_token import DeviceToken, PushNotificationPreference
    assert DeviceToken is not None
    assert PushNotificationPreference is not None
    assert DeviceToken.__tablename__ == 'device_tokens'
    assert PushNotificationPreference.__tablename__ == 'push_notification_preferences'


def test_device_token_has_organization_id():
    from database.models.device_token import DeviceToken
    columns = {c.name for c in DeviceToken.__table__.columns}
    assert 'organization_id' in columns
    assert 'failure_count' in columns
    assert 'last_used_at' in columns
    assert 'device_name' in columns
    assert 'app_version' in columns


def test_push_preference_model_fields():
    from database.models.device_token import PushNotificationPreference
    columns = {c.name for c in PushNotificationPreference.__table__.columns}
    assert 'user_id' in columns
    assert 'organization_id' in columns
    assert 'categories' in columns
    assert 'muted' in columns
    assert 'quiet_hours_start' in columns
    assert 'quiet_hours_end' in columns


def test_convenience_functions_importable():
    """Verify all convenience notification functions are importable."""
    from routes.push_notification_routes import (
        notify_lead_assigned,
        notify_loan_update,
        notify_appointment_reminder,
        notify_briefing_ready,
        notify_document_received,
        notify_sla_alert,
        notify_compliance_alert,
        notify_task_assigned,
        notify_esign_completed,
    )
    # All should be callable
    assert callable(notify_lead_assigned)
    assert callable(notify_loan_update)
    assert callable(notify_appointment_reminder)
    assert callable(notify_briefing_ready)
    assert callable(notify_document_received)
    assert callable(notify_sla_alert)
    assert callable(notify_compliance_alert)
    assert callable(notify_task_assigned)
    assert callable(notify_esign_completed)


def test_route_models_importable():
    """Verify Pydantic request models are importable."""
    from routes.push_notification_routes import (
        RegisterTokenRequest,
        UnregisterTokenRequest,
        UpdatePreferencesRequest,
        SendNotificationRequest,
        TestNotificationRequest,
    )
    assert RegisterTokenRequest is not None
    assert UnregisterTokenRequest is not None
    assert UpdatePreferencesRequest is not None


def test_register_token_request_validation():
    """Verify RegisterTokenRequest validation."""
    from routes.push_notification_routes import RegisterTokenRequest

    # Valid request
    req = RegisterTokenRequest(device_token="a" * 64, platform="ios")
    assert req.platform == "ios"

    # Invalid platform should raise
    with pytest.raises(Exception):
        RegisterTokenRequest(device_token="a" * 64, platform="windows")

    # Token too short should raise
    with pytest.raises(Exception):
        RegisterTokenRequest(device_token="short", platform="ios")


def test_update_preferences_request_validation():
    """Verify UpdatePreferencesRequest validation."""
    from routes.push_notification_routes import UpdatePreferencesRequest

    # Valid request with categories
    req = UpdatePreferencesRequest(
        categories={"lead_assigned": False, "sla_alert": True},
        muted=False,
    )
    assert req.categories["lead_assigned"] is False

    # Valid quiet hours
    req = UpdatePreferencesRequest(quiet_hours_start="22:00", quiet_hours_end="07:00")
    assert req.quiet_hours_start == "22:00"

    # Invalid quiet hours format should raise
    with pytest.raises(Exception):
        UpdatePreferencesRequest(quiet_hours_start="25:00")
