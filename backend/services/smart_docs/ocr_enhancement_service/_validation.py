"""Auto-generated. See ocr_enhancement_service/__init__.py."""
from __future__ import annotations

import hashlib
import io
import logging
import os
import re
import statistics
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

logger = logging.getLogger(__name__)

# Optional dependency imports (graceful degradation)
try:
    from PIL import Image, ImageFilter, ImageEnhance, ImageOps
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import pytesseract
    HAS_TESSERACT = True
except ImportError:
    HAS_TESSERACT = False

try:
    from pdf2image import convert_from_bytes
    HAS_PDF2IMAGE = True
except ImportError:
    HAS_PDF2IMAGE = False

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

try:
    from anthropic import Anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

from middleware.upload_limits import (
    MAX_VISION_API_SIZE,
    MAX_IMAGE_DIMENSIONS,
    MAX_OCR_OUTPUT_CHARS,
    MAX_PDF_PAGES,
)

# Pull all constants/enums/dataclasses (incl. DEFAULT_TARGET_DPI, MIN_TABLE_ROWS, etc.)
from ._types import *  # noqa: F401,F403


# FieldValidator

class FieldValidator:
    """Validates extracted fields against document-type-specific rules.

    Applies single-field validations (type, range, pattern) and
    cross-field validations (e.g., net_pay <= gross_pay).
    """

    @staticmethod
    def validate_field(
        field_name: str,
        value: Any,
        validation_rule: Dict[str, Any],
    ) -> Tuple[bool, str]:
        """Validate a single field value against its rule.

        Args:
            field_name: Name of the field.
            value: Extracted value.
            validation_rule: Validation specification from the schema.

        Returns:
            Tuple of (is_valid, validation_message).
        """
        if value is None:
            return True, ""  # Missing values are handled by required-field checks

        rule_type = validation_rule.get("type", "string")

        if rule_type == "currency":
            return FieldValidator._validate_currency(
                field_name, value,
                validation_rule.get("min"),
                validation_rule.get("max"),
            )

        if rule_type == "integer":
            return FieldValidator._validate_integer(
                field_name, value,
                validation_rule.get("min"),
                validation_rule.get("max"),
            )

        if rule_type == "number":
            return FieldValidator._validate_number(
                field_name, value,
                validation_rule.get("min"),
                validation_rule.get("max"),
            )

        if rule_type == "regex":
            pattern = validation_rule.get("pattern", "")
            return FieldValidator._validate_regex(field_name, value, pattern)

        if rule_type == "enum":
            allowed = validation_rule.get("values", [])
            return FieldValidator._validate_enum(field_name, value, allowed)

        return True, ""

    @staticmethod
    def validate_cross_fields(
        fields: Dict[str, Any],
        cross_validations: List[Dict[str, Any]],
    ) -> List[str]:
        """Run cross-field validations.

        Args:
            fields: Dict of field_name -> value.
            cross_validations: List of cross-validation rules from the schema.

        Returns:
            List of validation error messages (empty if all pass).
        """
        errors: List[str] = []

        for rule in cross_validations:
            check_type = rule.get("check", "")
            rule_fields = rule.get("fields", [])
            message = rule.get("message", "Cross-field validation failed")

            # Get field values
            values = []
            all_present = True
            for f in rule_fields:
                v = fields.get(f)
                if v is None:
                    all_present = False
                    break
                values.append(FieldValidator._to_float(v))

            if not all_present:
                continue  # Skip if any field is missing

            if any(v is None for v in values):
                continue

            if check_type == "lte" and len(values) >= 2:
                # First field should be <= second field
                if values[0] > values[1]:
                    errors.append(
                        f"{message}: {rule_fields[0]}={values[0]} > "
                        f"{rule_fields[1]}={values[1]}"
                    )

            elif check_type == "gte" and len(values) >= 2:
                if values[0] < values[1]:
                    errors.append(
                        f"{message}: {rule_fields[0]}={values[0]} < "
                        f"{rule_fields[1]}={values[1]}"
                    )

            elif check_type == "max_value":
                max_val = rule.get("max", float("inf"))
                for i, v in enumerate(values):
                    if v > max_val:
                        errors.append(f"{message}: {rule_fields[i]}={v}")

            elif check_type == "balance_equation" and len(values) >= 4:
                # beginning + deposits - withdrawals should equal ending
                beginning, deposits, withdrawals, ending = values[:4]
                tolerance = rule.get("tolerance", 1.0)
                calculated = beginning + deposits - withdrawals
                diff = abs(calculated - ending)
                if diff > tolerance:
                    errors.append(
                        f"{message}: calculated={calculated:.2f} vs "
                        f"ending={ending:.2f} (diff={diff:.2f})"
                    )

        return errors

    @staticmethod
    def _validate_currency(
        name: str, value: Any, min_val: Optional[float], max_val: Optional[float],
    ) -> Tuple[bool, str]:
        num = FieldValidator._to_float(value)
        if num is None:
            return False, f"{name}: not a valid currency value"
        if min_val is not None and num < min_val:
            return False, f"{name}: {num} below minimum {min_val}"
        if max_val is not None and num > max_val:
            return False, f"{name}: {num} exceeds maximum {max_val}"
        return True, ""

    @staticmethod
    def _validate_integer(
        name: str, value: Any, min_val: Optional[int], max_val: Optional[int],
    ) -> Tuple[bool, str]:
        try:
            num = int(value)
        except (ValueError, TypeError):
            return False, f"{name}: not a valid integer"
        if min_val is not None and num < min_val:
            return False, f"{name}: {num} below minimum {min_val}"
        if max_val is not None and num > max_val:
            return False, f"{name}: {num} exceeds maximum {max_val}"
        return True, ""

    @staticmethod
    def _validate_number(
        name: str, value: Any, min_val: Optional[float], max_val: Optional[float],
    ) -> Tuple[bool, str]:
        num = FieldValidator._to_float(value)
        if num is None:
            return False, f"{name}: not a valid number"
        if min_val is not None and num < min_val:
            return False, f"{name}: {num} below minimum {min_val}"
        if max_val is not None and num > max_val:
            return False, f"{name}: {num} exceeds maximum {max_val}"
        return True, ""

    @staticmethod
    def _validate_regex(name: str, value: Any, pattern: str) -> Tuple[bool, str]:
        val_str = str(value).strip()
        if not re.match(pattern, val_str):
            return False, f"{name}: '{val_str}' does not match pattern {pattern}"
        return True, ""

    @staticmethod
    def _validate_enum(
        name: str, value: Any, allowed: List[str],
    ) -> Tuple[bool, str]:
        val_str = str(value).strip().lower()
        allowed_lower = [a.lower() for a in allowed]
        if val_str not in allowed_lower:
            return False, f"{name}: '{val_str}' not in {allowed}"
        return True, ""

    @staticmethod
    def _to_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, str):
            cleaned = value.replace("$", "").replace(",", "").strip()
            if not cleaned:
                return None
            try:
                return float(cleaned)
            except ValueError:
                return None
        return None
