"""Tests for PushNotificationService."""
import pytest


def test_service_import():
    from services.push_notification_service import PushNotificationService
    assert PushNotificationService is not None


def test_notification_types():
    from services.push_notification_service import NotificationType
    assert hasattr(NotificationType, 'LEAD_ASSIGNED')
    assert hasattr(NotificationType, 'APPOINTMENT_REMINDER')
    assert hasattr(NotificationType, 'SLA_ALERT')
    assert hasattr(NotificationType, 'BRIEFING_READY')
    assert hasattr(NotificationType, 'DOCUMENT_RECEIVED')
    assert hasattr(NotificationType, 'GENERAL')


def test_notification_templates():
    from services.push_notification_service import NOTIFICATION_TEMPLATES
    assert 'lead_assigned' in NOTIFICATION_TEMPLATES
    assert 'appointment_reminder' in NOTIFICATION_TEMPLATES
    assert 'sla_alert' in NOTIFICATION_TEMPLATES
    assert 'briefing_ready' in NOTIFICATION_TEMPLATES
    assert 'document_received' in NOTIFICATION_TEMPLATES
    assert 'general' in NOTIFICATION_TEMPLATES
    assert 'title' in NOTIFICATION_TEMPLATES['lead_assigned']
    assert 'body' in NOTIFICATION_TEMPLATES['lead_assigned']


def test_service_instantiation():
    from services.push_notification_service import PushNotificationService
    service = PushNotificationService()
    assert service._apns_client is None
    assert service._fcm_initialized is False
