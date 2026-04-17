# backend/tests/test_call_authorization.py
import pytest
from database.models.call_authorization import CallAuthorization


def test_call_authorization_has_required_columns():
    columns = {c.name for c in CallAuthorization.__table__.columns}
    required = {
        "id", "lead_id", "call_id", "authorization_type",
        "authorized_by", "rule_id", "borrower_consent_source",
        "borrower_consent_date", "created_at",
    }
    assert required.issubset(columns), f"Missing columns: {required - columns}"


def test_call_authorization_table_name():
    assert CallAuthorization.__tablename__ == "call_authorizations"


def test_authorization_type_values():
    auth = CallAuthorization(authorization_type="lo_manual", lead_id=1)
    assert auth.authorization_type == "lo_manual"
    auth2 = CallAuthorization(authorization_type="auto_rule", lead_id=1, rule_id="appointment_reminder_v2")
    assert auth2.rule_id == "appointment_reminder_v2"
