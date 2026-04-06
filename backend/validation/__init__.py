"""
Validation utilities for the Mortgage CRM API.

Provides reusable input sanitization and format validation functions
used across route handlers and service layers.
"""

from validation.common import (
    sanitize_string,
    sanitize_text,
    validate_email_format,
    validate_phone_format,
    validate_ssn,
    validate_loan_amount_decimal,
    validate_credit_score,
    validate_interest_rate,
    validate_loan_number,
    validate_uuid,
    safe_sql_identifier,
    validate_column_names,
    SAFE_IDENTIFIER_RE,
)

from validation.smart_docs_validators import (
    validate_regex_safe,
    sanitize_html,
    validate_threshold_pair,
    validate_dti,
    validate_phone,
    validate_email_safe,
    validate_loan_amount,
    validate_percentage,
    sanitize_filename,
    validate_json_size,
)

__all__ = [
    # common
    "sanitize_string",
    "sanitize_text",
    "validate_email_format",
    "validate_phone_format",
    "validate_ssn",
    "validate_loan_amount_decimal",
    "validate_credit_score",
    "validate_interest_rate",
    "validate_loan_number",
    "validate_uuid",
    "safe_sql_identifier",
    "validate_column_names",
    "SAFE_IDENTIFIER_RE",
    # smart_docs_validators
    "validate_regex_safe",
    "sanitize_html",
    "validate_threshold_pair",
    "validate_dti",
    "validate_phone",
    "validate_email_safe",
    "validate_loan_amount",
    "validate_percentage",
    "sanitize_filename",
    "validate_json_size",
]
