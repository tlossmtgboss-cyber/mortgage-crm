"""
Tool Argument Validator

Validates tool arguments before execution to prevent malformed LLM-generated
arguments from causing unexpected behavior in SQL queries or tool functions.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# Argument Schemas (tool_name → expected args)
# =============================================================================

# Type validators
def _is_str(v: Any) -> bool:
    return isinstance(v, str)

def _is_int(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)

def _is_bool(v: Any) -> bool:
    return isinstance(v, bool)

def _is_optional_str(v: Any) -> bool:
    return v is None or isinstance(v, str)

def _is_optional_int(v: Any) -> bool:
    return v is None or (isinstance(v, (int, float)) and not isinstance(v, bool))

def _is_positive_int(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0


# Schema definition: {param_name: (required, validator, description)}
TOOL_SCHEMAS: Dict[str, Dict[str, Tuple[bool, Any, str]]] = {
    "get_pipeline": {
        "include_details": (False, _is_bool, "boolean"),
    },
    "get_pipeline_metrics": {
        "lo_id": (False, _is_optional_str, "string or null"),
        "organization_id": (False, _is_optional_str, "string or null"),
        "days": (False, _is_positive_int, "positive integer"),
    },
    "search_loans": {
        "query": (False, _is_optional_str, "search string"),
        "limit": (False, _is_positive_int, "positive integer"),
    },
    "search_leads": {
        "query": (False, _is_optional_str, "search string"),
        "limit": (False, _is_positive_int, "positive integer"),
    },
    "get_tasks": {
        "limit": (False, _is_positive_int, "positive integer"),
    },
    "create_task": {
        "title": (True, _is_str, "non-empty string"),
    },
    "get_daily_priorities": {},
    "get_lead_details": {
        "lead_id": (True, _is_str, "string"),
    },
    "get_loan_details": {
        "loan_id": (True, _is_str, "string"),
    },
    "click_to_dial": {
        "phone_number": (True, _is_str, "phone number string"),
    },
    "send_email": {
        "to": (False, _is_optional_str, "email string"),
        "subject": (False, _is_optional_str, "string"),
        "body": (False, _is_optional_str, "string"),
    },
}


# =============================================================================
# SQL Injection Detection
# =============================================================================

# Patterns that suggest SQL injection attempts in argument values
_SQL_INJECTION_PATTERNS = [
    re.compile(r";\s*(DROP|DELETE|UPDATE|INSERT|ALTER|CREATE)\s", re.IGNORECASE),
    re.compile(r"'\s*(OR|AND)\s+\d+\s*=\s*\d+", re.IGNORECASE),
    re.compile(r"UNION\s+(ALL\s+)?SELECT", re.IGNORECASE),
    re.compile(r"--\s*$"),  # SQL comment at end
    re.compile(r"/\*.*\*/"),  # Block comments
]


def _check_sql_injection(value: Any) -> bool:
    """Check if a string value contains potential SQL injection patterns."""
    if not isinstance(value, str):
        return False
    for pattern in _SQL_INJECTION_PATTERNS:
        if pattern.search(value):
            return True
    return False


# =============================================================================
# Validation Function
# =============================================================================

def validate_tool_arguments(
    tool_name: str,
    arguments: Dict[str, Any],
) -> Tuple[bool, Dict[str, Any], List[str]]:
    """
    Validate tool arguments before execution.

    Returns:
        (is_valid, sanitized_arguments, errors)
        - is_valid: True if arguments pass validation
        - sanitized_arguments: Cleaned arguments (with defaults applied)
        - errors: List of validation error messages
    """
    errors: List[str] = []
    sanitized = dict(arguments)

    # Check for SQL injection in all string values
    for key, value in arguments.items():
        if _check_sql_injection(value):
            errors.append(f"Potentially unsafe value for '{key}'")
            logger.warning(
                f"[VALIDATOR] SQL injection pattern detected in {tool_name}.{key}: "
                f"{str(value)[:100]}"
            )
            # Remove the suspicious value
            sanitized.pop(key, None)

    # Check against schema if available
    schema = TOOL_SCHEMAS.get(tool_name)
    if schema:
        for param_name, (required, validator, type_desc) in schema.items():
            value = sanitized.get(param_name)

            if required and (value is None or value == ""):
                errors.append(f"Missing required parameter '{param_name}' ({type_desc})")
                continue

            if value is not None and not validator(value):
                errors.append(
                    f"Invalid type for '{param_name}': expected {type_desc}, "
                    f"got {type(value).__name__}"
                )
                # Try to coerce common mismatches
                if type_desc == "positive integer" and isinstance(value, str):
                    try:
                        sanitized[param_name] = int(value)
                        errors.pop()  # Remove the error if coercion worked
                    except (ValueError, TypeError):
                        pass
                elif type_desc == "boolean" and isinstance(value, str):
                    sanitized[param_name] = value.lower() in ("true", "1", "yes")
                    errors.pop()

    # Enforce limits on limit/count parameters to prevent excessive queries
    for limit_key in ("limit", "count", "max_results"):
        if limit_key in sanitized:
            val = sanitized[limit_key]
            if isinstance(val, (int, float)) and val > 500:
                sanitized[limit_key] = 500
                logger.info(f"[VALIDATOR] Clamped {tool_name}.{limit_key} from {val} to 500")

    is_valid = len(errors) == 0
    if not is_valid:
        logger.warning(f"[VALIDATOR] {tool_name} validation failed: {errors}")

    return is_valid, sanitized, errors
