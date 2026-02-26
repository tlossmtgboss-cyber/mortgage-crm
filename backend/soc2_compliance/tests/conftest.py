"""
SOC 2 Test Fixtures — Shared test infrastructure for all SOC 2 compliance tests.
"""
import os
import pytest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from soc2_compliance.config import SOC2Config


@pytest.fixture
def sample_user_id():
    return uuid4()


@pytest.fixture
def sample_tenant_id():
    return uuid4()


@pytest.fixture
def soc2_config():
    """SOC 2 config with a test encryption key."""
    from cryptography.fernet import Fernet
    test_key = Fernet.generate_key().decode()
    return SOC2Config(
        field_encryption_key=test_key,
        session_timeout_minutes=30,
        max_login_attempts=5,
        lockout_duration_minutes=30,
    )


@pytest.fixture
def mock_db():
    """Mock SQLAlchemy session."""
    db = MagicMock()

    # Default: execute returns empty result
    mock_result = MagicMock()
    mock_result.fetchone.return_value = None
    mock_result.fetchall.return_value = []
    mock_result.rowcount = 0
    db.execute.return_value = mock_result

    return db


@pytest.fixture
def audit_service(mock_db):
    """AuditService with mocked DB."""
    from soc2_compliance.services.audit_service import AuditService
    return AuditService(mock_db)


@pytest.fixture
def access_control_service(mock_db, soc2_config):
    """AccessControlService with mocked DB."""
    from soc2_compliance.services.access_control_service import AccessControlService
    return AccessControlService(mock_db, config=soc2_config)


@pytest.fixture
def incident_service(mock_db):
    """IncidentService with mocked DB."""
    from soc2_compliance.services.incident_service import IncidentService
    return IncidentService(mock_db)


@pytest.fixture
def retention_service(mock_db, soc2_config):
    """RetentionService with mocked DB."""
    from soc2_compliance.services.retention_service import RetentionService
    return RetentionService(mock_db, config=soc2_config)


@pytest.fixture
def encryption_service(soc2_config):
    """EncryptionService with test key."""
    from soc2_compliance.services.encryption_service import EncryptionService
    return EncryptionService(config=soc2_config)
