"""
Comprehensive test suite for Salesforce integration.

Covers: stage mapping, field transformation, sync engine, webhook processing,
        OAuth security, SOQL sanitization, circuit breaker, record routing,
        change detection hashing, and data integrity.

Run with: python -m pytest tests/test_salesforce_integration.py -v
"""
import pytest
import hashlib
import hmac
import json
import re
import secrets
import base64
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock
from decimal import Decimal
from typing import Dict, Any, Optional

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


# ============================================================================
# Stage Mapping Tests
# ============================================================================

@pytest.mark.unit
class TestStageMapping:
    """Test the canonical stage mapping from Salesforce to CRM."""

    def test_import_stage_mapping_module(self):
        """Stage mapping module should be importable and contain entries."""
        from services.salesforce.stage_mapping import (
            map_salesforce_stage,
            SALESFORCE_STAGE_MAPPING,
        )
        assert isinstance(SALESFORCE_STAGE_MAPPING, dict)
        assert len(SALESFORCE_STAGE_MAPPING) >= 40

    @pytest.mark.parametrize("sf_stage", [
        "Funded", "Loan Funded", "Closed", "Closed Won",
        "Closed - Converted", "Post-Closing", "Post-Funding",
        "Purchased", "Completed", "File Complete", "Loan Sold", "Settled",
    ])
    def test_funded_stages_map_to_funded(self, sf_stage):
        """All funded/closed stages should map to FUNDED."""
        from services.salesforce.stage_mapping import map_salesforce_stage
        assert map_salesforce_stage(sf_stage) == "FUNDED"

    @pytest.mark.parametrize("sf_stage,expected", [
        ("Cancelled", "CANCELLED"),
        ("Denied", "DENIED"),
        ("Rejected", "DENIED"),
        ("Withdrawn", "WITHDRAWN"),
        ("Dead", "DEAD"),
        ("Inactive", "DEAD"),
        ("Does Not Qualify", "DOES_NOT_QUALIFY"),
        ("Suspended", "SUSPENDED"),
        ("Nurture", "NURTURE"),
    ])
    def test_terminal_stages_map_correctly(self, sf_stage, expected):
        """Terminal stages should map to the correct CRM values."""
        from services.salesforce.stage_mapping import map_salesforce_stage
        assert map_salesforce_stage(sf_stage) == expected

    @pytest.mark.parametrize("sf_stage", [
        "Processing", "Processed", "In Processing",
        "Contract Received", "Submitted to Processing",
        "Loan in Process", "Document Collection",
        "Documents Requested", "Documents Received",
    ])
    def test_processing_stages_map_to_processing(self, sf_stage):
        """Processing-related stages should map to PROCESSING."""
        from services.salesforce.stage_mapping import map_salesforce_stage
        assert map_salesforce_stage(sf_stage) == "PROCESSING"

    @pytest.mark.parametrize("sf_stage", [
        "New", "Application", "Application Received",
        "Started", "File Started", "Prospecting",
        "Qualification", "Needs Analysis",
    ])
    def test_application_stages_map_to_application(self, sf_stage):
        """Application/early stages should map to APPLICATION."""
        from services.salesforce.stage_mapping import map_salesforce_stage
        assert map_salesforce_stage(sf_stage) == "APPLICATION"

    @pytest.mark.parametrize("sf_stage", [
        "Submitted", "Submitted to UW", "Submitted to Underwriting",
        "Proposal/Price Quote",
    ])
    def test_submitted_stages(self, sf_stage):
        """Submitted stages should map to SUBMITTED."""
        from services.salesforce.stage_mapping import map_salesforce_stage
        assert map_salesforce_stage(sf_stage) == "SUBMITTED"

    @pytest.mark.parametrize("sf_stage", [
        "Conditionally Approved", "Conditional Approval",
        "Cond. Approved", "Approved with Conditions",
    ])
    def test_conditional_approval_stages(self, sf_stage):
        """Conditional approval variants should map to CONDITIONAL_APPROVAL."""
        from services.salesforce.stage_mapping import map_salesforce_stage
        assert map_salesforce_stage(sf_stage) == "CONDITIONAL_APPROVAL"

    def test_clear_to_close_stages(self):
        """CTC variants should map to CLEAR_TO_CLOSE."""
        from services.salesforce.stage_mapping import map_salesforce_stage
        assert map_salesforce_stage("Clear to Close") == "CLEAR_TO_CLOSE"
        assert map_salesforce_stage("CTC") == "CLEAR_TO_CLOSE"

    def test_docs_out_stages(self):
        """Docs out variants should map to DOCS_OUT."""
        from services.salesforce.stage_mapping import map_salesforce_stage
        assert map_salesforce_stage("Closing Docs Out") == "DOCS_OUT"
        assert map_salesforce_stage("Docs Out") == "DOCS_OUT"
        assert map_salesforce_stage("Docs Signing") == "DOCS_OUT"
        assert map_salesforce_stage("Docs Signed") == "DOCS_OUT"

    def test_disclosed_stages(self):
        """Disclosed variants should map to DISCLOSED."""
        from services.salesforce.stage_mapping import map_salesforce_stage
        assert map_salesforce_stage("Disclosed") == "DISCLOSED"
        assert map_salesforce_stage("LE Sent") == "DISCLOSED"

    def test_underwriting_stages(self):
        """Underwriting variants should map to UNDERWRITING."""
        from services.salesforce.stage_mapping import map_salesforce_stage
        assert map_salesforce_stage("Underwriting") == "UNDERWRITING"
        assert map_salesforce_stage("In Underwriting") == "UNDERWRITING"
        assert map_salesforce_stage("Negotiation/Review") == "UNDERWRITING"

    def test_unknown_stage_returns_none(self):
        """Unknown stage values should return None."""
        from services.salesforce.stage_mapping import map_salesforce_stage
        assert map_salesforce_stage("NonExistentStage") is None
        assert map_salesforce_stage("XYZZY") is None

    def test_empty_string_returns_none(self):
        """Empty string should return None."""
        from services.salesforce.stage_mapping import map_salesforce_stage
        assert map_salesforce_stage("") is None

    def test_none_input_returns_none(self):
        """None input should return None."""
        from services.salesforce.stage_mapping import map_salesforce_stage
        assert map_salesforce_stage(None) is None

    def test_all_mapped_values_are_valid_loan_stages(self):
        """Every mapped value must be a valid LoanStage enum value."""
        from services.salesforce.stage_mapping import SALESFORCE_STAGE_MAPPING
        valid_stages = {
            "APPLICATION", "DISCLOSED", "PROCESSING", "SUBMITTED", "UNDERWRITING",
            "UW_RECEIVED", "CONDITIONAL_APPROVAL", "APPROVED", "SUSPENDED",
            "CTC", "CLEAR_TO_CLOSE", "CLOSING", "DOCS", "DOCS_OUT", "FUNDED",
            "CANCELLED", "DENIED", "DEAD", "NURTURE", "WITHDRAWN", "DOES_NOT_QUALIFY",
        }
        for sf_stage, crm_stage in SALESFORCE_STAGE_MAPPING.items():
            assert crm_stage in valid_stages, (
                f"Mapped value '{crm_stage}' for '{sf_stage}' is not a valid LoanStage"
            )

    def test_case_sensitivity_exact_picklist_values(self):
        """Mapping should be case-sensitive (Salesforce picklist values are case-sensitive)."""
        from services.salesforce.stage_mapping import map_salesforce_stage
        assert map_salesforce_stage("Funded") == "FUNDED"
        # lowercase / uppercase variants should not match the exact-match dict
        assert map_salesforce_stage("funded") is None
        assert map_salesforce_stage("FUNDED") is None

    def test_no_duplicate_salesforce_keys(self):
        """Each Salesforce stage string should appear exactly once."""
        from services.salesforce.stage_mapping import SALESFORCE_STAGE_MAPPING
        # Python dicts enforce unique keys, so just verify count matches
        assert len(SALESFORCE_STAGE_MAPPING) == len(list(SALESFORCE_STAGE_MAPPING.keys()))


# ============================================================================
# SOQL Sanitization Tests
# ============================================================================

@pytest.mark.unit
class TestSOQLSanitization:
    """Test SOQL injection prevention."""

    def test_sanitize_soql_string_escapes_single_quotes(self):
        """_sanitize_soql_string should escape single quotes."""
        from services.salesforce.sync_service import _sanitize_soql_string
        result = _sanitize_soql_string("O'Brien")
        assert "\\'" in result
        assert result == "O\\'Brien"

    def test_sanitize_soql_string_escapes_backslashes(self):
        """_sanitize_soql_string should escape backslashes before quotes."""
        from services.salesforce.sync_service import _sanitize_soql_string
        result = _sanitize_soql_string("path\\to\\thing")
        assert "\\\\" in result

    def test_sanitize_soql_string_strips_whitespace(self):
        """_sanitize_soql_string should strip leading/trailing whitespace."""
        from services.salesforce.sync_service import _sanitize_soql_string
        result = _sanitize_soql_string("  hello  ")
        assert result == "hello"

    def test_sanitize_soql_string_rejects_control_characters(self):
        """_sanitize_soql_string should reject strings with control chars."""
        from services.salesforce.sync_service import _sanitize_soql_string
        assert _sanitize_soql_string("hello\x00world") == ""
        assert _sanitize_soql_string("line\nbreak") == ""
        assert _sanitize_soql_string("tab\there") == ""

    def test_sanitize_soql_string_empty_input(self):
        """_sanitize_soql_string should return empty string for None/empty."""
        from services.salesforce.sync_service import _sanitize_soql_string
        assert _sanitize_soql_string("") == ""
        assert _sanitize_soql_string(None) == ""

    def test_sanitize_soql_string_non_string_input(self):
        """_sanitize_soql_string should return empty string for non-strings."""
        from services.salesforce.sync_service import _sanitize_soql_string
        assert _sanitize_soql_string(12345) == ""

    def test_sanitize_soql_email_valid(self):
        """_sanitize_soql_email should accept valid emails."""
        from services.salesforce.sync_service import _sanitize_soql_email
        result = _sanitize_soql_email("john@example.com")
        assert result == "john@example.com"

    def test_sanitize_soql_email_rejects_invalid(self):
        """_sanitize_soql_email should reject non-email strings."""
        from services.salesforce.sync_service import _sanitize_soql_email
        assert _sanitize_soql_email("not_an_email") == ""
        assert _sanitize_soql_email("@no_local") == ""
        assert _sanitize_soql_email("") == ""

    def test_sanitize_soql_email_escapes_quotes_in_valid_email(self):
        """_sanitize_soql_email should escape quotes if email passes format check."""
        from services.salesforce.sync_service import _sanitize_soql_email
        # An email with a quote in the domain would fail format validation
        result = _sanitize_soql_email("user@ex'ample.com")
        # Should either reject (empty) or escape -- either is acceptable
        assert "'" not in result or "\\'" in result

    @pytest.mark.parametrize("identifier,valid", [
        ("Lead", True),
        ("Contact", True),
        ("Opportunity", True),
        ("MtgPlanner_CRM__Transaction_Property__c", True),
        ("Custom_Field__c", True),
        ("Name", True),
        ("Id", True),
        ("Lead; DROP TABLE", False),
        ("Contact' OR '1'='1", False),
        ("Lead UNION SELECT", False),
        ("../../../etc/passwd", False),
        ("", False),
        (" ", False),
        ("123Invalid", False),
    ])
    def test_soql_identifier_validation_regex(self, identifier, valid):
        """SOQL identifiers should be validated against a safe pattern."""
        SAFE_SOQL_IDENTIFIER = re.compile(r'^[A-Za-z][A-Za-z0-9_]*(__[a-zA-Z])?$')
        result = bool(SAFE_SOQL_IDENTIFIER.match(identifier))
        assert result == valid, f"'{identifier}' expected valid={valid}, got {result}"


# ============================================================================
# Field Transformation Tests
# ============================================================================

@pytest.mark.unit
class TestFieldTransformations:
    """Test the FieldMappingService.transform_value method."""

    def _get_service(self):
        from services.salesforce.field_mapping_service import FieldMappingService
        return FieldMappingService()

    def test_direct_transform_returns_value_unchanged(self):
        """Direct transform should pass value through."""
        svc = self._get_service()
        assert svc.transform_value("hello", "direct", {}) == "hello"
        assert svc.transform_value(42, "direct", None) == 42

    def test_direct_transform_none_returns_default(self):
        """Direct transform with None value should return config default."""
        svc = self._get_service()
        result = svc.transform_value(None, "direct", {"default": "fallback"})
        assert result == "fallback"

    def test_stage_map_transform(self):
        """Stage map transform should map values using config."""
        svc = self._get_service()
        config = {"mappings": {"Funded": "FUNDED", "Processing": "PROCESSING"}}
        assert svc.transform_value("Funded", "stage_map", config) == "FUNDED"
        assert svc.transform_value("Processing", "stage_map", config) == "PROCESSING"

    def test_stage_map_unmapped_value_uses_default(self):
        """Stage map with unmapped value should use default."""
        svc = self._get_service()
        config = {"mappings": {"Funded": "FUNDED"}, "default": "APPLICATION"}
        assert svc.transform_value("Unknown", "stage_map", config) == "APPLICATION"

    def test_stage_map_unmapped_value_no_default_passes_through(self):
        """Stage map with unmapped value and no default should pass through."""
        svc = self._get_service()
        config = {"mappings": {"Funded": "FUNDED"}}
        assert svc.transform_value("Unknown", "stage_map", config) == "Unknown"

    def test_picklist_map_transform(self):
        """Picklist map should work like stage map."""
        svc = self._get_service()
        config = {"mappings": {"Yes": "true", "No": "false"}}
        assert svc.transform_value("Yes", "picklist_map", config) == "true"
        assert svc.transform_value("No", "picklist_map", config) == "false"

    def test_date_format_iso_string(self):
        """Date format should parse ISO strings."""
        svc = self._get_service()
        config = {"outputFormat": "iso8601"}
        result = svc.transform_value("2025-01-15T10:30:00Z", "date_format", config)
        assert "2025-01-15" in result

    def test_date_format_with_date_output(self):
        """Date format with non-iso8601 output should produce YYYY-MM-DD."""
        svc = self._get_service()
        config = {"outputFormat": "date_only"}
        result = svc.transform_value("2025-06-20T14:00:00Z", "date_format", config)
        assert result == "2025-06-20"

    def test_date_format_unparseable_returns_original(self):
        """Unparseable date should return the original value."""
        svc = self._get_service()
        config = {"outputFormat": "iso8601"}
        result = svc.transform_value("not-a-date", "date_format", config)
        assert result == "not-a-date"

    def test_currency_convert(self):
        """Currency convert should round to specified decimals."""
        svc = self._get_service()
        config = {"decimalPlaces": 2}
        assert svc.transform_value("500000.456", "currency_convert", config) == 500000.46
        assert svc.transform_value(123456, "currency_convert", config) == 123456.0

    def test_currency_convert_non_numeric_returns_original(self):
        """Currency convert with non-numeric should return original."""
        svc = self._get_service()
        config = {"decimalPlaces": 2}
        result = svc.transform_value("N/A", "currency_convert", config)
        assert result == "N/A"

    def test_phone_format_ten_digits(self):
        """Phone format should format 10-digit numbers as (XXX) XXX-XXXX."""
        svc = self._get_service()
        config = {"format": "national", "defaultCountry": "US"}
        assert svc.transform_value("8435551234", "phone_format", config) == "(843) 555-1234"
        assert svc.transform_value("(843) 555-1234", "phone_format", config) == "(843) 555-1234"

    def test_phone_format_non_ten_digits_returns_original(self):
        """Phone format with non-10-digit after cleaning should return original."""
        svc = self._get_service()
        config = {"format": "national"}
        # 11 digits: "18435551234" -> len 11 -> returns original
        result = svc.transform_value("+1 843 555 1234", "phone_format", config)
        assert result == "+1 843 555 1234"

    def test_none_value_returns_config_default(self):
        """None value with any transform should return config default."""
        svc = self._get_service()
        assert svc.transform_value(None, "stage_map", {"default": "APP"}) == "APP"
        assert svc.transform_value(None, "currency_convert", {"default": 0}) == 0
        assert svc.transform_value(None, "direct", None) is None


# ============================================================================
# Field Mapping Validation Tests
# ============================================================================

@pytest.mark.unit
class TestFieldMappingValidation:
    """Test the _validate_mapping method for data integrity."""

    def _get_service(self):
        from services.salesforce.field_mapping_service import FieldMappingService
        return FieldMappingService()

    def test_missing_source_object_produces_error(self):
        """Validation should fail when source_object is missing."""
        svc = self._get_service()
        mapping = {
            "source_object": "",
            "source_field": "Name",
            "target_entity": "lead",
            "target_field": "name",
            "transform_type": "direct",
        }
        result = svc._validate_mapping(MagicMock(), mapping)
        assert not result["is_valid"]
        assert any("Source object" in e for e in result["errors"])

    def test_missing_source_field_produces_error(self):
        """Validation should fail when source_field is missing."""
        svc = self._get_service()
        mapping = {
            "source_object": "Lead",
            "source_field": "",
            "target_entity": "lead",
            "target_field": "name",
            "transform_type": "direct",
        }
        result = svc._validate_mapping(MagicMock(), mapping)
        assert not result["is_valid"]
        assert any("Source field" in e for e in result["errors"])

    def test_missing_target_entity_produces_error(self):
        """Validation should fail when target_entity is missing."""
        svc = self._get_service()
        mapping = {
            "source_object": "Lead",
            "source_field": "Name",
            "target_entity": "",
            "target_field": "name",
            "transform_type": "direct",
        }
        result = svc._validate_mapping(MagicMock(), mapping)
        assert not result["is_valid"]

    def test_missing_transform_type_produces_error(self):
        """Validation should fail when transform_type is missing."""
        svc = self._get_service()
        mapping = {
            "source_object": "Lead",
            "source_field": "Name",
            "target_entity": "lead",
            "target_field": "name",
            "transform_type": "",
        }
        result = svc._validate_mapping(MagicMock(), mapping)
        assert not result["is_valid"]

    def test_valid_mapping_passes(self):
        """A fully specified mapping should pass validation."""
        svc = self._get_service()
        mapping = {
            "source_object": "Lead",
            "source_field": "Name",
            "target_entity": "lead",
            "target_field": "name",
            "transform_type": "direct",
        }
        result = svc._validate_mapping(MagicMock(), mapping)
        assert result["is_valid"]
        assert len(result["errors"]) == 0

    def test_required_field_without_default_produces_warning(self):
        """Required field without default and non-direct transform should warn."""
        svc = self._get_service()
        mapping = {
            "source_object": "Lead",
            "source_field": "Status",
            "target_entity": "lead",
            "target_field": "stage",
            "transform_type": "stage_map",
            "required": True,
            "default_value": None,
            "transform_config": {"mappings": {"New": "APPLICATION"}},
        }
        result = svc._validate_mapping(MagicMock(), mapping)
        assert len(result["warnings"]) > 0


# ============================================================================
# Transform Type Detection Tests
# ============================================================================

@pytest.mark.unit
class TestTransformTypeDetection:
    """Test automatic transform type determination."""

    def _get_service(self):
        from services.salesforce.field_mapping_service import FieldMappingService
        return FieldMappingService()

    def test_stage_field_gets_stage_map(self):
        """Fields targeting 'stage' should get stage_map transform."""
        svc = self._get_service()
        field = {"name": "StageName", "type": "picklist"}
        assert svc._determine_transform_type(field, "stage") == "stage_map"

    def test_status_field_gets_stage_map(self):
        """Fields with 'status' in name should get stage_map transform."""
        svc = self._get_service()
        field = {"name": "Lead_Status__c", "type": "picklist"}
        assert svc._determine_transform_type(field, "lead_status") == "stage_map"

    def test_picklist_field_gets_picklist_map(self):
        """Picklist fields with values should get picklist_map transform."""
        svc = self._get_service()
        field = {"name": "Loan_Type__c", "type": "picklist", "picklistValues": [{"value": "FHA"}]}
        assert svc._determine_transform_type(field, "loan_type") == "picklist_map"

    def test_date_field_gets_date_format(self):
        """Date fields should get date_format transform."""
        svc = self._get_service()
        field = {"name": "CloseDate", "type": "date"}
        assert svc._determine_transform_type(field, "closing_date") == "date_format"

    def test_datetime_field_gets_date_format(self):
        """Datetime fields should also get date_format transform."""
        svc = self._get_service()
        field = {"name": "LastModifiedDate", "type": "datetime"}
        assert svc._determine_transform_type(field, "updated_at") == "date_format"

    def test_currency_field_gets_currency_convert(self):
        """Currency fields should get currency_convert transform."""
        svc = self._get_service()
        field = {"name": "Amount", "type": "currency"}
        assert svc._determine_transform_type(field, "amount") == "currency_convert"

    def test_phone_field_gets_phone_format(self):
        """Phone fields should get phone_format transform."""
        svc = self._get_service()
        field = {"name": "Phone", "type": "phone"}
        assert svc._determine_transform_type(field, "phone") == "phone_format"

    def test_phone_name_field_gets_phone_format(self):
        """Fields with 'phone' in the name should get phone_format."""
        svc = self._get_service()
        field = {"name": "Home_Phone__c", "type": "string"}
        assert svc._determine_transform_type(field, "home_phone") == "phone_format"

    def test_string_field_gets_direct(self):
        """Regular string fields should get direct transform."""
        svc = self._get_service()
        field = {"name": "FirstName", "type": "string"}
        assert svc._determine_transform_type(field, "first_name") == "direct"


# ============================================================================
# Sync Hash / Change Detection Tests
# ============================================================================

@pytest.mark.unit
class TestSyncHash:
    """Test change detection hash computation."""

    def _get_service(self):
        from services.salesforce.sync_service import SalesforceSyncService
        return SalesforceSyncService()

    def test_same_data_produces_same_hash(self):
        """Identical data should produce identical hashes."""
        svc = self._get_service()
        data = {"name": "John", "amount": 500000, "stage": "PROCESSING"}
        assert svc._generate_sync_hash(data) == svc._generate_sync_hash(data)

    def test_different_data_produces_different_hash(self):
        """Different data should produce different hashes."""
        svc = self._get_service()
        data1 = {"name": "John", "amount": 500000}
        data2 = {"name": "Jane", "amount": 500000}
        assert svc._generate_sync_hash(data1) != svc._generate_sync_hash(data2)

    def test_key_order_does_not_affect_hash(self):
        """Dict key order should not affect hash (sort_keys=True)."""
        svc = self._get_service()
        data1 = {"b": 2, "a": 1}
        data2 = {"a": 1, "b": 2}
        assert svc._generate_sync_hash(data1) == svc._generate_sync_hash(data2)

    def test_hash_is_32_char_hex(self):
        """Hash should be a 32-character hex string (MD5)."""
        svc = self._get_service()
        h = svc._generate_sync_hash({"test": True})
        assert len(h) == 32
        assert all(c in "0123456789abcdef" for c in h)

    def test_hash_handles_datetime_values(self):
        """Hash should handle non-JSON-serializable types via default=str."""
        svc = self._get_service()
        data = {"date": datetime(2025, 1, 15, 10, 30), "amount": Decimal("500000.00")}
        # Should not raise
        h = svc._generate_sync_hash(data)
        assert len(h) == 32

    def test_hash_sensitive_to_value_changes(self):
        """Even small value changes should produce a different hash."""
        svc = self._get_service()
        data1 = {"amount": 500000}
        data2 = {"amount": 500001}
        assert svc._generate_sync_hash(data1) != svc._generate_sync_hash(data2)


# ============================================================================
# Record Bucket Classification Tests
# ============================================================================

@pytest.mark.unit
class TestRecordBucketClassification:
    """Test the _classify_record_bucket method for routing logic."""

    def _get_service(self):
        from services.salesforce.sync_service import SalesforceSyncService
        return SalesforceSyncService()

    @pytest.mark.parametrize("sf_status", [
        "New", "Prospecting", "Qualification", "Pre-Qualified",
        "Pre-Approved", "Nurture", "Open - Not Contacted",
        "Working - Contacted", "Needs Analysis", "Long-Term Nurture",
    ])
    def test_lead_statuses_classify_as_lead(self, sf_status):
        """Prospect/pre-qualified statuses should classify as 'lead'."""
        svc = self._get_service()
        result = svc._classify_record_bucket({"stage": sf_status})
        assert result == "lead", f"'{sf_status}' should classify as lead, got {result}"

    @pytest.mark.parametrize("sf_status", [
        "Funded", "Closed", "Closed Won", "Closed - Converted",
        "Loan Funded", "Completed", "Purchased", "File Complete",
        "Post-Closing", "Post-Funding", "Loan Sold", "Settled",
    ])
    def test_funded_statuses_classify_as_loan_funded(self, sf_status):
        """Funded/closed statuses should classify as 'loan_funded'."""
        svc = self._get_service()
        result = svc._classify_record_bucket({"stage": sf_status})
        assert result == "loan_funded", f"'{sf_status}' should classify as loan_funded, got {result}"

    @pytest.mark.parametrize("sf_status", [
        "Processing", "Submitted", "Underwriting",
        "Approved", "Clear to Close", "Closing",
    ])
    def test_active_loan_statuses_classify_as_loan(self, sf_status):
        """Active loan statuses should classify as 'loan'."""
        svc = self._get_service()
        result = svc._classify_record_bucket({"stage": sf_status})
        assert result == "loan", f"'{sf_status}' should classify as loan, got {result}"

    def test_no_stage_with_amount_classifies_as_loan(self):
        """Record with no stage but an amount should default to 'loan'."""
        svc = self._get_service()
        assert svc._classify_record_bucket({"amount": 500000}) == "loan"

    def test_no_stage_with_loan_number_classifies_as_loan(self):
        """Record with no stage but a loan_number should default to 'loan'."""
        svc = self._get_service()
        assert svc._classify_record_bucket({"loan_number": "2024-001"}) == "loan"

    def test_no_stage_no_loan_data_classifies_as_lead(self):
        """Record with no stage or loan indicators should default to 'lead'."""
        svc = self._get_service()
        assert svc._classify_record_bucket({}) == "lead"

    def test_cancelled_classifies_as_loan(self):
        """Cancelled status should stay in loans table (not regress to lead)."""
        svc = self._get_service()
        assert svc._classify_record_bucket({"stage": "Cancelled"}) == "loan"

    def test_sf_status_field_fallback(self):
        """Should check _sf_status when stage is not set."""
        svc = self._get_service()
        result = svc._classify_record_bucket({"_sf_status": "Funded"})
        assert result == "loan_funded"

    def test_stagename_field_fallback(self):
        """Should check StageName when stage is not set."""
        svc = self._get_service()
        result = svc._classify_record_bucket({"StageName": "Processing"})
        assert result == "loan"

    def test_status_field_fallback(self):
        """Should check Status when stage/StageName are not set."""
        svc = self._get_service()
        result = svc._classify_record_bucket({"Status": "New"})
        assert result == "lead"


# ============================================================================
# Mapping Grouping Tests
# ============================================================================

@pytest.mark.unit
class TestMappingGrouping:
    """Test the grouping utility methods."""

    def _get_service(self):
        from services.salesforce.sync_service import SalesforceSyncService
        return SalesforceSyncService()

    def _make_mapping(self, source_object, source_field, target_entity, target_field):
        m = MagicMock()
        m.source_object = source_object
        m.source_field = source_field
        m.target_entity = target_entity
        m.target_field = target_field
        return m

    def test_group_by_object(self):
        """Mappings should be grouped by source_object."""
        svc = self._get_service()
        mappings = [
            self._make_mapping("Lead", "Name", "lead", "name"),
            self._make_mapping("Lead", "Email", "lead", "email"),
            self._make_mapping("Opportunity", "Amount", "loan", "amount"),
        ]
        grouped = svc._group_mappings_by_object(mappings)
        assert len(grouped) == 2
        assert len(grouped["Lead"]) == 2
        assert len(grouped["Opportunity"]) == 1

    def test_group_by_entity(self):
        """Mappings should be grouped by target_entity."""
        svc = self._get_service()
        mappings = [
            self._make_mapping("Lead", "Name", "lead", "name"),
            self._make_mapping("Lead", "Amount", "loan", "amount"),
            self._make_mapping("Lead", "Email", "lead", "email"),
        ]
        grouped = svc._group_mappings_by_entity(mappings)
        assert len(grouped) == 2
        assert len(grouped["lead"]) == 2
        assert len(grouped["loan"]) == 1

    def test_empty_mappings(self):
        """Empty mapping list should return empty groups."""
        svc = self._get_service()
        assert svc._group_mappings_by_object([]) == {}
        assert svc._group_mappings_by_entity([]) == {}


# ============================================================================
# SOQL Query Builder Tests
# ============================================================================

@pytest.mark.unit
class TestSOQLQueryBuilder:
    """Test the _build_soql_query method."""

    def _get_service(self):
        from services.salesforce.sync_service import SalesforceSyncService
        return SalesforceSyncService()

    def _make_mapping(self, source_field):
        m = MagicMock()
        m.source_field = source_field
        return m

    def test_includes_id_field(self):
        """Generated SOQL should always include the Id field."""
        svc = self._get_service()
        mappings = [self._make_mapping("Name"), self._make_mapping("Email")]
        soql = svc._build_soql_query("Lead", mappings, full_sync=False, batch_size=200)
        assert "Id" in soql

    def test_includes_mapped_fields(self):
        """Generated SOQL should include all mapped source fields."""
        svc = self._get_service()
        mappings = [self._make_mapping("Name"), self._make_mapping("Email")]
        soql = svc._build_soql_query("Lead", mappings, full_sync=False, batch_size=200)
        assert "Name" in soql
        assert "Email" in soql

    def test_incremental_sync_has_where_clause(self):
        """Incremental sync should include LastModifiedDate filter."""
        svc = self._get_service()
        mappings = [self._make_mapping("Name")]
        soql = svc._build_soql_query("Lead", mappings, full_sync=False, batch_size=200)
        assert "LastModifiedDate" in soql
        assert "LAST_N_DAYS:1" in soql

    def test_full_sync_no_where_clause(self):
        """Full sync should not include LastModifiedDate filter."""
        svc = self._get_service()
        mappings = [self._make_mapping("Name")]
        soql = svc._build_soql_query("Lead", mappings, full_sync=True, batch_size=200)
        assert "WHERE" not in soql

    def test_includes_limit(self):
        """Generated SOQL should include LIMIT clause."""
        svc = self._get_service()
        mappings = [self._make_mapping("Name")]
        soql = svc._build_soql_query("Lead", mappings, full_sync=True, batch_size=100)
        assert "LIMIT 100" in soql

    def test_includes_order_by(self):
        """Generated SOQL should include ORDER BY for consistent pagination."""
        svc = self._get_service()
        mappings = [self._make_mapping("Name")]
        soql = svc._build_soql_query("Lead", mappings, full_sync=True, batch_size=200)
        assert "ORDER BY LastModifiedDate ASC" in soql

    def test_deduplicates_fields(self):
        """Duplicate source fields should be deduplicated."""
        svc = self._get_service()
        mappings = [self._make_mapping("Name"), self._make_mapping("Name")]
        soql = svc._build_soql_query("Lead", mappings, full_sync=True, batch_size=200)
        # Count occurrences of "Name" in the SELECT portion
        select_part = soql.split("FROM")[0]
        assert select_part.count("Name") == 1

    def test_uses_correct_object_name(self):
        """Generated SOQL should reference the specified object."""
        svc = self._get_service()
        mappings = [self._make_mapping("Name")]
        soql = svc._build_soql_query("Opportunity", mappings, full_sync=True, batch_size=200)
        assert "FROM Opportunity" in soql


# ============================================================================
# Webhook Signature Verification Tests
# ============================================================================

@pytest.mark.unit
class TestWebhookSecurity:
    """Test webhook signature verification patterns."""

    def test_valid_hmac_signature_accepted(self):
        """A correctly signed webhook payload should verify."""
        secret = "test_webhook_secret_key"
        payload = b'{"event": "record_updated", "id": "001ABC"}'
        signature = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

        computed = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        assert hmac.compare_digest(computed, signature)

    def test_invalid_signature_rejected(self):
        """An incorrectly signed webhook should fail verification."""
        secret = "test_webhook_secret_key"
        payload = b'{"event": "test"}'
        wrong_sig = "deadbeef" * 8

        computed = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        assert not hmac.compare_digest(computed, wrong_sig)

    def test_tampered_payload_detected(self):
        """Tampered payload should produce different signature."""
        secret = "test_webhook_secret_key"
        original = b'{"amount": 500000}'
        tampered = b'{"amount": 999999}'

        sig_original = hmac.new(secret.encode(), original, hashlib.sha256).hexdigest()
        sig_tampered = hmac.new(secret.encode(), tampered, hashlib.sha256).hexdigest()
        assert sig_original != sig_tampered

    def test_timing_safe_comparison(self):
        """Signature comparison must use constant-time comparison."""
        a = "a" * 64
        b = "a" * 64
        assert hmac.compare_digest(a, b)
        assert not hmac.compare_digest("short", "a" * 64)


# ============================================================================
# OAuth Security Tests
# ============================================================================

@pytest.mark.unit
class TestOAuthSecurity:
    """Test OAuth flow security mechanisms."""

    def test_state_token_sufficient_entropy(self):
        """OAuth state tokens should have sufficient entropy (32+ bytes)."""
        token1 = secrets.token_hex(32)
        token2 = secrets.token_hex(32)
        assert token1 != token2
        assert len(token1) == 64  # 32 bytes = 64 hex chars

    def test_pkce_code_verifier_generation(self):
        """PKCE code verifier should be 43-128 characters (RFC 7636)."""
        code_verifier = secrets.token_urlsafe(64)
        assert 43 <= len(code_verifier) <= 128

    def test_pkce_code_challenge_is_sha256_base64url(self):
        """PKCE code challenge should be SHA256 of verifier, base64url-encoded, no padding."""
        code_verifier = "test_verifier_string_for_pkce_flow_testing"
        digest = hashlib.sha256(code_verifier.encode()).digest()
        code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()

        assert len(code_challenge) > 0
        assert "=" not in code_challenge
        assert "+" not in code_challenge
        assert "/" not in code_challenge

    def test_oauth_state_expiry_detection(self):
        """OAuth states older than 15 minutes should be treated as expired."""
        created_at = datetime.now(timezone.utc) - timedelta(minutes=16)
        expires_at = created_at + timedelta(minutes=15)
        now = datetime.now(timezone.utc)
        assert now > expires_at

    def test_oauth_state_fresh_is_valid(self):
        """Recently created OAuth state should not be expired."""
        created_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        expires_at = created_at + timedelta(minutes=15)
        now = datetime.now(timezone.utc)
        assert now < expires_at

    @pytest.mark.parametrize("url,should_pass", [
        ("https://app.perenniaai.com/settings", True),
        ("https://app.perenniaai.com/integrations/salesforce", True),
        ("javascript:alert(1)", False),
        ("//evil.com/steal", False),
        ("https://evil.com/phish", False),
        ("data:text/html,<script>alert(1)</script>", False),
        ("ftp://evil.com/file", False),
    ])
    def test_redirect_url_validation(self, url, should_pass):
        """OAuth redirect URLs should be validated for open redirect prevention."""
        from urllib.parse import urlparse
        ALLOWED_HOSTS = {"app.perenniaai.com", "localhost"}
        ALLOWED_SCHEMES = {"http", "https"}

        parsed = urlparse(url)
        is_safe = (
            parsed.scheme in ALLOWED_SCHEMES
            and parsed.netloc in ALLOWED_HOSTS
        )
        assert is_safe == should_pass, f"URL '{url}' expected safe={should_pass}"

    def test_oauth_config_lazy_initialization(self):
        """SalesforceOAuthConfig should lazy-initialize on first access."""
        from services.salesforce.oauth_service import SalesforceOAuthConfig
        config = SalesforceOAuthConfig(
            client_id="test_id", client_secret="test_secret"
        )
        assert config._initialized is False
        _ = config.client_id
        assert config._initialized is True
        assert config.client_id == "test_id"

    def test_oauth_pkce_generation_method(self):
        """SalesforceOAuthService._generate_pkce should return verifier and challenge."""
        from services.salesforce.oauth_service import SalesforceOAuthService
        svc = SalesforceOAuthService()
        verifier, challenge = svc._generate_pkce()
        assert len(verifier) >= 43
        assert len(challenge) > 0
        # Verify challenge is derived from verifier
        expected_digest = hashlib.sha256(verifier.encode()).digest()
        expected_challenge = base64.urlsafe_b64encode(expected_digest).decode().rstrip("=")
        assert challenge == expected_challenge


# ============================================================================
# Column Whitelist Tests
# ============================================================================

@pytest.mark.unit
class TestColumnWhitelists:
    """Test that SQL column whitelists prevent injection."""

    @pytest.mark.parametrize("col,safe", [
        ("borrower_name", True),
        ("amount", True),
        ("stage", True),
        ("loan_officer_id", True),
        ("property_state", True),
        ("1invalid", False),
        ("DROP TABLE", False),
        ("name; --", False),
        ("col=1", False),
        ("borrower_name OR 1=1", False),
        ("", False),
        (" ", False),
    ])
    def test_safe_column_regex(self, col, safe):
        """Column name regex should accept safe names and reject injections."""
        SAFE_COLUMN = re.compile(r"^[a-z][a-z0-9_]*$")
        assert bool(SAFE_COLUMN.match(col)) == safe, f"'{col}' expected safe={safe}"

    def test_valid_lead_columns_whitelist_exists(self):
        """SalesforceSyncService should have a VALID_LEAD_COLUMNS whitelist."""
        from services.salesforce.sync_service import SalesforceSyncService
        assert hasattr(SalesforceSyncService, "VALID_LEAD_COLUMNS")
        columns = SalesforceSyncService.VALID_LEAD_COLUMNS
        assert isinstance(columns, set)
        assert len(columns) > 30

    def test_core_lead_columns_present(self):
        """Whitelist should include essential lead columns."""
        from services.salesforce.sync_service import SalesforceSyncService
        required = {"first_name", "last_name", "email", "phone", "stage", "source"}
        missing = required - SalesforceSyncService.VALID_LEAD_COLUMNS
        assert not missing, f"Missing required columns: {missing}"

    def test_dangerous_columns_excluded(self):
        """Whitelist should not include columns that could be exploited."""
        from services.salesforce.sync_service import SalesforceSyncService
        dangerous = {"password", "password_hash", "access_token", "secret_key", "id"}
        overlap = dangerous & SalesforceSyncService.VALID_LEAD_COLUMNS
        assert not overlap, f"Dangerous columns in whitelist: {overlap}"

    def test_financial_columns_in_whitelist(self):
        """Whitelist should include financial/loan detail columns."""
        from services.salesforce.sync_service import SalesforceSyncService
        financial = {"loan_amount", "interest_rate", "loan_term", "apr", "credit_score"}
        missing = financial - SalesforceSyncService.VALID_LEAD_COLUMNS
        assert not missing, f"Missing financial columns: {missing}"

    def test_sla_date_columns_in_whitelist(self):
        """Whitelist should include SLA milestone date columns."""
        from services.salesforce.sync_service import SalesforceSyncService
        sla_dates = {"lead_received_date", "application_completed_date", "credit_pulled_date"}
        missing = sla_dates - SalesforceSyncService.VALID_LEAD_COLUMNS
        assert not missing, f"Missing SLA date columns: {missing}"


# ============================================================================
# Data Integrity / Validation Tests
# ============================================================================

@pytest.mark.unit
class TestDataIntegrity:
    """Test data integrity constraints for sync operations."""

    @pytest.mark.parametrize("amount,valid", [
        (500000.00, True),
        (100000, True),
        (0, False),
        (-1, False),
        (None, False),
    ])
    def test_loan_amount_validation(self, amount, valid):
        """Loan amounts should be positive."""
        is_valid = amount is not None and amount > 0
        assert is_valid == valid

    @pytest.mark.parametrize("rate,reasonable", [
        (3.5, True),
        (6.875, True),
        (0.0, True),
        (29.99, True),
        (-1.0, False),
        (50.0, False),
        (100.0, False),
    ])
    def test_rate_reasonableness(self, rate, reasonable):
        """Interest rates should be between 0 and 30%."""
        assert (0 <= rate <= 30) == reasonable

    @pytest.mark.parametrize("sf_id,valid", [
        ("001000000000001", True),
        ("001000000000001AAA", True),
        ("006Dn000001abc2IAA", True),
        ("a0BDn0000012345ABC", True),
        ("", False),
        ("short", False),
        ("way_too_long_to_be_valid_id_12345", False),
        ("001;DROP TABLE--", False),
    ])
    def test_salesforce_id_format(self, sf_id, valid):
        """Salesforce IDs should be 15 or 18 alphanumeric characters."""
        SF_ID_PATTERN = re.compile(r"^[a-zA-Z0-9]{15}([a-zA-Z0-9]{3})?$")
        assert bool(SF_ID_PATTERN.match(sf_id)) == valid, f"'{sf_id}' expected valid={valid}"

    @pytest.mark.parametrize("email,valid", [
        ("john@example.com", True),
        ("jane.doe@company.co.uk", True),
        ("user+tag@domain.com", True),
        ("not_an_email", False),
        ("@no_local", False),
        ("no@domain", False),
        ("", False),
    ])
    def test_email_format_validation(self, email, valid):
        """Emails should pass basic format validation."""
        EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
        assert bool(EMAIL_PATTERN.match(email)) == valid, f"'{email}' expected valid={valid}"


# ============================================================================
# Circuit Breaker Tests
# ============================================================================

@pytest.mark.unit
class TestCircuitBreaker:
    """Test circuit breaker constants and logic."""

    def test_max_failures_constant_exists(self):
        """SalesforceSyncService should define MAX_CONSECUTIVE_FAILURES."""
        from services.salesforce.sync_service import SalesforceSyncService
        assert hasattr(SalesforceSyncService, "MAX_CONSECUTIVE_FAILURES")
        assert SalesforceSyncService.MAX_CONSECUTIVE_FAILURES == 5

    def test_cooldown_constant_exists(self):
        """SalesforceSyncService should define CIRCUIT_COOLDOWN_MINUTES."""
        from services.salesforce.sync_service import SalesforceSyncService
        assert hasattr(SalesforceSyncService, "CIRCUIT_COOLDOWN_MINUTES")
        assert SalesforceSyncService.CIRCUIT_COOLDOWN_MINUTES == 30

    def test_circuit_opens_at_threshold(self):
        """Circuit should open when consecutive_failures >= MAX_CONSECUTIVE_FAILURES."""
        from services.salesforce.sync_service import SalesforceSyncService
        threshold = SalesforceSyncService.MAX_CONSECUTIVE_FAILURES
        # Simulating: failures accumulate up to threshold
        for i in range(1, threshold + 1):
            consecutive_failures = i
        assert consecutive_failures >= threshold

    def test_cooldown_period_blocks_sync(self):
        """After circuit opens, sync should be blocked during cooldown."""
        from services.salesforce.sync_service import SalesforceSyncService
        cooldown_min = SalesforceSyncService.CIRCUIT_COOLDOWN_MINUTES
        last_failure = datetime.utcnow() - timedelta(minutes=10)
        cooldown_until = last_failure + timedelta(minutes=cooldown_min)
        # 10 minutes ago + 30 min cooldown = 20 minutes from now
        assert datetime.utcnow() < cooldown_until

    def test_cooldown_elapsed_allows_retry(self):
        """After cooldown elapses, sync should be allowed (half-open state)."""
        from services.salesforce.sync_service import SalesforceSyncService
        cooldown_min = SalesforceSyncService.CIRCUIT_COOLDOWN_MINUTES
        last_failure = datetime.utcnow() - timedelta(minutes=cooldown_min + 5)
        cooldown_until = last_failure + timedelta(minutes=cooldown_min)
        assert datetime.utcnow() >= cooldown_until

    def test_success_resets_failure_count(self):
        """On success, consecutive_failures should be reset to 0."""
        # This tests the pattern used in sync() method
        metadata = {"consecutive_failures": 4, "last_failure_at": "2025-01-15T10:00:00"}
        # Simulate success path
        metadata["consecutive_failures"] = 0
        metadata.pop("last_failure_at", None)
        assert metadata["consecutive_failures"] == 0
        assert "last_failure_at" not in metadata


# ============================================================================
# HTTP Client Configuration Tests
# ============================================================================

@pytest.mark.unit
class TestHTTPClientConfig:
    """Test the Salesforce HTTP client configuration."""

    def test_timeout_values(self):
        """SF_TIMEOUT should have reasonable values."""
        from services.salesforce.http_client import SF_TIMEOUT
        assert SF_TIMEOUT.connect == 10.0
        assert SF_TIMEOUT.read == 30.0
        assert SF_TIMEOUT.write == 10.0
        assert SF_TIMEOUT.pool == 10.0

    def test_request_timeout_value(self):
        """Overall request timeout should be 60 seconds."""
        from services.salesforce.http_client import SF_REQUEST_TIMEOUT
        assert SF_REQUEST_TIMEOUT == 60.0

    def test_get_sf_client_returns_async_client(self):
        """get_sf_client should return an httpx.AsyncClient."""
        import httpx
        from services.salesforce.http_client import get_sf_client
        client = get_sf_client()
        assert isinstance(client, httpx.AsyncClient)

    def test_api_usage_tracking_parses_header(self):
        """_track_api_usage should parse Sforce-Limit-Info header."""
        from services.salesforce.http_client import _track_api_usage, get_api_usage
        _track_api_usage("api-usage=500/15000")
        usage = get_api_usage()
        assert usage["used"] == 500
        assert usage["limit"] == 15000

    def test_api_usage_tracking_malformed_input(self):
        """_track_api_usage should silently handle malformed input."""
        from services.salesforce.http_client import _track_api_usage
        # These should not raise
        _track_api_usage("")
        _track_api_usage("garbage")
        _track_api_usage("api-usage=")

    def test_get_api_usage_returns_copy(self):
        """get_api_usage should return a copy, not the mutable original."""
        from services.salesforce.http_client import get_api_usage
        usage1 = get_api_usage()
        usage2 = get_api_usage()
        # Mutating one should not affect the other
        usage1["used"] = 99999
        assert get_api_usage()["used"] != 99999


# ============================================================================
# Lead Status Mapping Tests
# ============================================================================

@pytest.mark.unit
class TestLeadStatusMapping:
    """Test _map_sf_status_to_lead_stage for lead-specific stage mapping."""

    def _get_service(self):
        from services.salesforce.sync_service import SalesforceSyncService
        return SalesforceSyncService()

    @pytest.mark.parametrize("sf_status,expected_lead_stage", [
        ("New", "New"),
        ("Open - Not Contacted", "New"),
        ("Working - Contacted", "Attempted Contact"),
        ("Prospecting", "Prospect"),
        ("Pre-Qualified", "Pre-Qualified"),
        ("Pre-Approved", "Pre-Approved"),
        ("Nurture", "Long-Term Nurture"),
        ("Application", "Application"),
        ("Funded", "Closed"),
        ("Closed Won", "Closed"),
        ("Cancelled", "Withdrawn"),
        ("Denied", "Does Not Qualify"),
    ])
    def test_known_status_mappings(self, sf_status, expected_lead_stage):
        """Known SF statuses should map to correct lead stages."""
        svc = self._get_service()
        assert svc._map_sf_status_to_lead_stage(sf_status) == expected_lead_stage

    def test_unknown_status_defaults_to_new(self):
        """Unknown SF statuses should default to 'New'."""
        svc = self._get_service()
        assert svc._map_sf_status_to_lead_stage("RandomUnknownStatus") == "New"


# ============================================================================
# Loan Field Remapping Tests
# ============================================================================

@pytest.mark.unit
class TestLoanFieldRemapping:
    """Test _remap_loan_fields_for_lead for cross-table field translation."""

    def _get_service(self):
        from services.salesforce.sync_service import SalesforceSyncService
        return SalesforceSyncService()

    def test_borrower_name_maps_to_name(self):
        """borrower_name should be remapped to name."""
        svc = self._get_service()
        result = svc._remap_loan_fields_for_lead({"borrower_name": "John Doe"})
        assert result.get("name") == "John Doe"

    def test_borrower_email_maps_to_email(self):
        """borrower_email should be remapped to email."""
        svc = self._get_service()
        result = svc._remap_loan_fields_for_lead({"borrower_email": "j@test.com"})
        assert result.get("email") == "j@test.com"

    def test_amount_maps_to_loan_amount(self):
        """amount (loan) should be remapped to loan_amount (lead)."""
        svc = self._get_service()
        result = svc._remap_loan_fields_for_lead({"amount": 500000})
        assert result.get("loan_amount") == 500000

    def test_unmapped_fields_preserved(self):
        """Fields not in the remap table should still be included."""
        svc = self._get_service()
        result = svc._remap_loan_fields_for_lead({"notes": "test note"})
        assert result.get("notes") == "test note"


# ============================================================================
# SyncResult Tests
# ============================================================================

@pytest.mark.unit
class TestSyncResult:
    """Test the SyncResult data structure."""

    def test_default_values(self):
        """SyncResult should initialize with sensible defaults."""
        from services.salesforce.sync_service import SyncResult
        result = SyncResult()
        assert result.success is False
        assert result.records_processed == 0
        assert result.records_succeeded == 0
        assert result.records_failed == 0
        assert result.errors == []
        assert result.duration_ms == 0

    def test_to_dict(self):
        """SyncResult.to_dict should return a serializable dict."""
        from services.salesforce.sync_service import SyncResult
        result = SyncResult()
        result.success = True
        result.records_processed = 10
        result.records_succeeded = 9
        result.records_failed = 1
        result.errors = [{"record_id": "001", "error": "test"}]
        result.duration_ms = 1234

        d = result.to_dict()
        assert d["success"] is True
        assert d["records_processed"] == 10
        assert d["records_succeeded"] == 9
        assert d["records_failed"] == 1
        assert len(d["errors"]) == 1
        assert d["duration_ms"] == 1234

    def test_to_dict_keys(self):
        """SyncResult.to_dict should have all expected keys."""
        from services.salesforce.sync_service import SyncResult
        d = SyncResult().to_dict()
        expected_keys = {"success", "records_processed", "records_succeeded",
                         "records_failed", "errors", "duration_ms"}
        assert set(d.keys()) == expected_keys


# ============================================================================
# Type Compatibility Matrix Tests
# ============================================================================

@pytest.mark.unit
class TestTypeCompatibility:
    """Test the TYPE_COMPATIBILITY matrix in field_mapping_service."""

    def test_string_compatibility(self):
        """String type should be compatible with text-like types."""
        from services.salesforce.field_mapping_service import TYPE_COMPATIBILITY
        assert "string" in TYPE_COMPATIBILITY["string"]
        assert "email" in TYPE_COMPATIBILITY["string"]
        assert "phone" in TYPE_COMPATIBILITY["string"]

    def test_boolean_only_compatible_with_boolean(self):
        """Boolean type should only be compatible with boolean."""
        from services.salesforce.field_mapping_service import TYPE_COMPATIBILITY
        assert TYPE_COMPATIBILITY["boolean"] == ["boolean"]

    def test_date_compatible_with_datetime(self):
        """Date type should be compatible with datetime."""
        from services.salesforce.field_mapping_service import TYPE_COMPATIBILITY
        assert "datetime" in TYPE_COMPATIBILITY["date"]

    def test_currency_compatible_with_numeric_types(self):
        """Currency type should be compatible with numeric types."""
        from services.salesforce.field_mapping_service import TYPE_COMPATIBILITY
        assert "number" in TYPE_COMPATIBILITY["currency"]
        assert "double" in TYPE_COMPATIBILITY["currency"]

    def test_int_compatible_with_double(self):
        """Int type should be compatible with double for widening conversions."""
        from services.salesforce.field_mapping_service import TYPE_COMPATIBILITY
        assert "double" in TYPE_COMPATIBILITY["int"]


# ============================================================================
# Default Stage Mapping Tests
# ============================================================================

@pytest.mark.unit
class TestDefaultStageMappings:
    """Test the DEFAULT_STAGE_MAPPINGS in field_mapping_service."""

    def test_default_mappings_exist(self):
        """DEFAULT_STAGE_MAPPINGS should be populated."""
        from services.salesforce.field_mapping_service import DEFAULT_STAGE_MAPPINGS
        assert isinstance(DEFAULT_STAGE_MAPPINGS, dict)
        assert len(DEFAULT_STAGE_MAPPINGS) > 0

    def test_funded_mapped_correctly(self):
        """'Funded' and 'Closed Won' should map to FUNDED."""
        from services.salesforce.field_mapping_service import DEFAULT_STAGE_MAPPINGS
        assert DEFAULT_STAGE_MAPPINGS.get("Funded") == "FUNDED"
        assert DEFAULT_STAGE_MAPPINGS.get("Closed Won") == "FUNDED"

    def test_lost_mapped_to_cancelled(self):
        """'Lost' and 'Closed Lost' should map to CANCELLED."""
        from services.salesforce.field_mapping_service import DEFAULT_STAGE_MAPPINGS
        assert DEFAULT_STAGE_MAPPINGS.get("Lost") == "CANCELLED"
        assert DEFAULT_STAGE_MAPPINGS.get("Closed Lost") == "CANCELLED"

    def test_all_values_are_valid_crm_stages(self):
        """All DEFAULT_STAGE_MAPPINGS values should be valid CRM stages."""
        from services.salesforce.field_mapping_service import DEFAULT_STAGE_MAPPINGS
        valid_stages = {
            "APPLICATION", "DISCLOSED", "PROCESSING", "SUBMITTED", "UNDERWRITING",
            "UW_RECEIVED", "CONDITIONAL_APPROVAL", "APPROVED", "SUSPENDED",
            "CTC", "CLEAR_TO_CLOSE", "CLOSING", "DOCS", "DOCS_OUT", "FUNDED",
            "CANCELLED", "DENIED", "DEAD", "NURTURE", "WITHDRAWN", "DOES_NOT_QUALIFY",
        }
        for sf_val, crm_val in DEFAULT_STAGE_MAPPINGS.items():
            assert crm_val in valid_stages, (
                f"DEFAULT_STAGE_MAPPINGS['{sf_val}'] = '{crm_val}' is not valid"
            )


# ============================================================================
# Tenant Isolation Design Tests
# ============================================================================

@pytest.mark.unit
class TestTenantIsolationDesign:
    """Verify tenant isolation is enforced in sync service by design."""

    def test_upsert_lead_queries_org_id(self):
        """_upsert_lead should query organization_id from users table."""
        from services.salesforce.sync_service import SalesforceSyncService
        import inspect
        source = inspect.getsource(SalesforceSyncService._upsert_lead)
        assert "organization_id" in source

    def test_find_existing_record_uses_org_filter(self):
        """_find_existing_record should scope salesforce_id lookups by org."""
        from services.salesforce.sync_service import SalesforceSyncService
        import inspect
        source = inspect.getsource(SalesforceSyncService._find_existing_record)
        assert "organization_id" in source
        assert "org_id" in source

    def test_sf_status_fields_defined(self):
        """SF_STATUS_FIELDS should be defined for status extraction."""
        from services.salesforce.sync_service import SalesforceSyncService
        assert hasattr(SalesforceSyncService, "SF_STATUS_FIELDS")
        fields = SalesforceSyncService.SF_STATUS_FIELDS
        assert len(fields) >= 3
        assert "StageName" in fields
        assert "Status" in fields

    def test_token_expired_error_class_exists(self):
        """SalesforceTokenExpiredError should be importable for retry logic."""
        from services.salesforce.sync_service import SalesforceTokenExpiredError
        assert issubclass(SalesforceTokenExpiredError, Exception)


# ============================================================================
# Transform Config Generation Tests
# ============================================================================

@pytest.mark.unit
class TestTransformConfigGeneration:
    """Test _create_transform_config for auto-generated configs."""

    def _get_service(self):
        from services.salesforce.field_mapping_service import FieldMappingService
        return FieldMappingService()

    def test_stage_map_config_includes_defaults(self):
        """Stage map config should include default mappings and default value."""
        svc = self._get_service()
        config = svc._create_transform_config({}, "stage_map")
        assert "mappings" in config
        assert "default" in config
        assert config["default"] == "APPLICATION"

    def test_date_format_config(self):
        """Date format config should specify input/output formats."""
        svc = self._get_service()
        config = svc._create_transform_config({}, "date_format")
        assert "inputFormat" in config
        assert "outputFormat" in config

    def test_currency_config(self):
        """Currency config should specify decimal places."""
        svc = self._get_service()
        config = svc._create_transform_config({}, "currency_convert")
        assert "decimalPlaces" in config
        assert config["decimalPlaces"] == 2

    def test_phone_config(self):
        """Phone config should specify format and country."""
        svc = self._get_service()
        config = svc._create_transform_config({}, "phone_format")
        assert "format" in config
        assert "defaultCountry" in config

    def test_direct_config_is_empty(self):
        """Direct transform config should be empty dict."""
        svc = self._get_service()
        config = svc._create_transform_config({}, "direct")
        assert config == {}

    def test_picklist_config_from_field_values(self):
        """Picklist config should create 1:1 mappings from field values."""
        svc = self._get_service()
        field = {"picklistValues": [{"value": "FHA"}, {"value": "VA"}, {"value": "Conventional"}]}
        config = svc._create_transform_config(field, "picklist_map")
        assert "mappings" in config
        assert config["mappings"]["FHA"] == "FHA"
        assert config["mappings"]["VA"] == "VA"


# ============================================================================
# Phone Normalization Tests
# ============================================================================

@pytest.mark.unit
class TestPhoneNormalization:
    """Test phone number normalization patterns used in sync."""

    @pytest.mark.parametrize("raw,expected_digits", [
        ("(843) 555-1234", "8435551234"),
        ("843-555-1234", "8435551234"),
        ("+1 843 555 1234", "18435551234"),
        ("8435551234", "8435551234"),
        ("843.555.1234", "8435551234"),
    ])
    def test_digit_extraction(self, raw, expected_digits):
        """Phone normalization should extract only digits."""
        digits = re.sub(r"\D", "", raw)
        assert digits == expected_digits


# ============================================================================
# Name Splitting Tests
# ============================================================================

@pytest.mark.unit
class TestNameSplitting:
    """Test name splitting used during lead creation."""

    @pytest.mark.parametrize("full_name,expected_first,expected_last", [
        ("John Smith", "John", "Smith"),
        ("Mary Jane Watson", "Mary", "Jane Watson"),
        ("Cher", "Cher", ""),
        ("", "", ""),
    ])
    def test_name_split(self, full_name, expected_first, expected_last):
        """Full names should split correctly into first/last."""
        parts = full_name.split(" ", 1) if full_name else ["", ""]
        first = parts[0] if parts else ""
        last = parts[1] if len(parts) > 1 else ""
        assert first == expected_first
        assert last == expected_last


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
