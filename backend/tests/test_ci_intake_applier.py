"""Tests for P3: IntakeFieldApplier service."""
import sys, os, uuid, pytest, json
from unittest.mock import MagicMock, patch
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
pytestmark = [pytest.mark.unit]

ORG_ID = 1
SESSION_ID = str(uuid.uuid4())
LOAN_ID = str(uuid.uuid4())


class TestCoerceValue:
    def test_numeric_from_string(self):
        from services.call_monitoring.intake_field_applier import coerce_value
        assert coerce_value("$450,000", "numeric") == 450000.0

    def test_numeric_strips_dollar_sign(self):
        from services.call_monitoring.intake_field_applier import coerce_value
        assert coerce_value("$95,000.50", "numeric") == 95000.50

    def test_integer_from_string(self):
        from services.call_monitoring.intake_field_applier import coerce_value
        assert coerce_value("720", "integer") == 720

    def test_annual_to_monthly(self):
        from services.call_monitoring.intake_field_applier import coerce_value
        result = coerce_value("120000", "numeric_annual_to_monthly")
        assert result == 10000.0

    def test_invalid_numeric_returns_none(self):
        from services.call_monitoring.intake_field_applier import coerce_value
        assert coerce_value("not-a-number", "numeric") is None

    def test_string_capped_at_500(self):
        from services.call_monitoring.intake_field_applier import coerce_value
        result = coerce_value("x" * 600, "string")
        assert len(result) == 500


class TestFieldMap:
    def test_credit_score_mapped(self):
        from services.call_monitoring.intake_field_applier import FIELD_MAP
        assert "credit_score" in FIELD_MAP
        table, col, vtype, _ = FIELD_MAP["credit_score"]
        assert table == "loans"
        assert col == "credit_score"

    def test_loan_amount_mapped(self):
        from services.call_monitoring.intake_field_applier import FIELD_MAP
        assert "loan_amount" in FIELD_MAP

    def test_rate_validation(self):
        from services.call_monitoring.intake_field_applier import FIELD_MAP
        _, _, _, validator = FIELD_MAP["interest_rate"]
        assert validator(6.5) is True
        assert validator(25.0) is False


class TestIntakeFieldApplier:
    @pytest.mark.asyncio
    async def test_apply_no_artifacts_returns_zero(self):
        from services.call_monitoring.intake_field_applier import IntakeFieldApplier
        db = MagicMock()
        db.execute.return_value.fetchall.return_value = []
        applier = IntakeFieldApplier(db, ORG_ID)
        result = await applier.apply_intake_fields(SESSION_ID, loan_id=LOAN_ID)
        assert result["applied"] == 0
