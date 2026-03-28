"""Tests for DeviceToken model."""
import pytest


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
    # SQLAlchemy column defaults (default=True) apply at INSERT, not at object construction.
    # Verify the column default is configured correctly instead.
    is_active_col = DeviceToken.__table__.c.is_active
    assert is_active_col.default is not None
    assert is_active_col.default.arg is True
    assert token.platform == "ios"


def test_device_token_user_relationship():
    """DeviceToken should have a user relationship."""
    from database.models import DeviceToken
    assert hasattr(DeviceToken, 'user')
