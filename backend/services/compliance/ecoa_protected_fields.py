"""
ECOA Protected Fields — Decisioning Barrier

Equal Credit Opportunity Act (Regulation B, 12 CFR 1002) prohibits
creditors from discriminating on the basis of:
    - Race
    - Color
    - Religion
    - National origin
    - Sex
    - Marital status
    - Age (provided capacity to contract)
    - Public assistance receipt

These fields may be COLLECTED for legitimate purposes (e.g., HMDA
reporting, community property state determinations, government
monitoring) but must NEVER be used as inputs to credit/lending
decisions, scoring, pricing, or eligibility calculations.

Usage:
    from services.compliance.ecoa_protected_fields import (
        ECOA_PROTECTED_FIELDS,
        strip_protected_fields,
    )

    # Before any decisioning logic:
    safe_data = strip_protected_fields(applicant_data)
"""

from typing import Any, Dict

# ECOA: These fields must NEVER flow into credit decisioning, scoring,
# pricing, or eligibility calculations.  They may be stored for
# compliance reporting (HMDA), property-rights analysis (community
# property states), or government monitoring purposes only.
ECOA_PROTECTED_FIELDS: frozenset = frozenset({
    "marital_status",
    "race",
    "ethnicity",
    "sex",
    "gender",
    "national_origin",
    "religion",
    "age",
    "date_of_birth",
    "public_assistance",
    "color",
    "familial_status",
})


def strip_protected_fields(data: Dict[str, Any]) -> Dict[str, Any]:
    """Remove ECOA protected fields from a data dict before decisioning.

    Args:
        data: Applicant/borrower data dict that may contain protected fields.

    Returns:
        A new dict with all ECOA protected fields removed.  The original
        dict is NOT mutated.

    Example::

        raw = {"income": 85000, "marital_status": "married", "credit_score": 740}
        safe = strip_protected_fields(raw)
        # safe == {"income": 85000, "credit_score": 740}
    """
    return {k: v for k, v in data.items() if k not in ECOA_PROTECTED_FIELDS}


def strip_protected_fields_nested(data: Dict[str, Any]) -> Dict[str, Any]:
    """Remove ECOA protected fields from a nested data dict.

    Recursively strips protected field keys from the top level and from
    any nested dict values.  Does NOT mutate the original.
    """
    result = {}
    for k, v in data.items():
        if k in ECOA_PROTECTED_FIELDS:
            continue
        if isinstance(v, dict):
            result[k] = strip_protected_fields_nested(v)
        else:
            result[k] = v
    return result
