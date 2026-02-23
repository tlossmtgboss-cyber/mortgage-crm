"""
Base Audit Module for Application Engine

All audit modules inherit from this base class.
Provides standardized audit flow, task generation, and validation.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Any, Tuple, Type
import logging
import time
import uuid

from .data_contracts import (
    AuditModuleType,
    AuditStatus,
    AuditResult,
    FieldStatus,
    ExtractedField,
    GeneratedTask,
    TaskPriority,
    TaskAssignee,
    ConfidenceLevel,
)

logger = logging.getLogger(__name__)


# =============================================================================
# VALIDATION RULES
# =============================================================================

@dataclass
class ValidationRule:
    """A validation rule for field checking."""
    rule_id: str
    field_name: str
    rule_type: str  # "required", "format", "range", "dependency", "cross_field"
    error_message: str

    # For format validation
    regex_pattern: Optional[str] = None

    # For range validation
    min_value: Optional[Any] = None
    max_value: Optional[Any] = None

    # For dependency validation
    depends_on_field: Optional[str] = None
    depends_on_value: Optional[Any] = None

    # Task generation if validation fails
    generate_task: bool = True
    task_priority: TaskPriority = TaskPriority.MEDIUM
    task_assignee: TaskAssignee = TaskAssignee.PA


# =============================================================================
# FIELD DEFINITIONS
# =============================================================================

@dataclass
class FieldDefinition:
    """Definition of a field for audit purposes."""
    name: str
    display_name: str
    required: bool = True

    # Data type
    data_type: str = "string"  # string, date, decimal, boolean, enum

    # For enum types
    allowed_values: List[str] = field(default_factory=list)

    # Validation
    validation_rules: List[ValidationRule] = field(default_factory=list)

    # Document requirements
    requires_documentation: bool = False
    document_types: List[str] = field(default_factory=list)

    # Task generation
    task_title_template: str = ""
    task_description_template: str = ""
    borrower_instructions: str = ""

    # URLA section mapping
    urla_section: Optional[str] = None
    urla_field_id: Optional[str] = None


# =============================================================================
# BASE AUDIT MODULE
# =============================================================================

class BaseAuditModule(ABC):
    """
    Abstract base class for all audit modules.

    Each module:
    1. Takes extracted data from call transcripts
    2. Validates against field definitions
    3. Identifies missing/conflicting data
    4. Generates tasks for resolution
    5. Returns AuditResult
    """

    MODULE_TYPE: AuditModuleType = None
    MODULE_VERSION: str = "1.0"

    def __init__(self, db_session=None):
        """Initialize module with optional database session."""
        self.db = db_session
        self._field_definitions: Dict[str, FieldDefinition] = {}
        self._setup_field_definitions()

    # -------------------------------------------------------------------------
    # Abstract Methods
    # -------------------------------------------------------------------------

    @abstractmethod
    def _setup_field_definitions(self) -> None:
        """Set up field definitions for this module."""
        pass

    @abstractmethod
    def _extract_data(
        self,
        call_extractions: Dict[str, Any],
        existing_data: Dict[str, Any],
    ) -> Any:
        """
        Extract and merge data from call and existing records.

        Returns module-specific data class.
        """
        pass

    @abstractmethod
    def _validate_data(self, data: Any) -> Tuple[List[str], List[str]]:
        """
        Validate the extracted data.

        Returns tuple of (issues, warnings).
        """
        pass

    # -------------------------------------------------------------------------
    # Main Audit Method
    # -------------------------------------------------------------------------

    def audit(
        self,
        call_extractions: Dict[str, Any],
        existing_data: Dict[str, Any],
        generate_tasks: bool = True,
        loan_id: Optional[int] = None,
        borrower_type: str = "primary",
    ) -> AuditResult:
        """
        Perform audit on the data.

        Args:
            call_extractions: Data extracted from call transcript
            existing_data: Existing application data from database
            generate_tasks: Whether to generate tasks for missing/conflicting data
            loan_id: Loan ID for task context
            borrower_type: "primary" or "co_borrower"

        Returns:
            AuditResult with status, data, and tasks
        """
        start_time = time.time()

        try:
            # Extract and merge data
            data = self._extract_data(call_extractions, existing_data)

            # Analyze field status
            field_stats = self._analyze_fields(data)

            # Validate data
            issues, warnings = self._validate_data(data)

            # Generate tasks if requested
            tasks = []
            if generate_tasks:
                tasks = self._generate_tasks(
                    data=data,
                    field_stats=field_stats,
                    loan_id=loan_id,
                    borrower_type=borrower_type,
                )

            # Determine overall status
            status = self._determine_status(field_stats, issues)

            # Calculate duration
            duration_ms = int((time.time() - start_time) * 1000)

            return AuditResult(
                module=self.MODULE_TYPE,
                status=status,
                fields_total=field_stats["total"],
                fields_complete=field_stats["complete"],
                fields_missing=field_stats["missing"],
                fields_conflicting=field_stats["conflicting"],
                completion_percentage=field_stats["completion_pct"],
                data=data,
                tasks=tasks,
                issues=issues,
                warnings=warnings,
                processing_duration_ms=duration_ms,
            )

        except Exception as e:
            logger.exception(f"Audit error in {self.MODULE_TYPE}: {e}")
            duration_ms = int((time.time() - start_time) * 1000)

            return AuditResult(
                module=self.MODULE_TYPE,
                status=AuditStatus.ERROR,
                issues=[f"Audit error: {str(e)}"],
                processing_duration_ms=duration_ms,
            )

    # -------------------------------------------------------------------------
    # Field Analysis
    # -------------------------------------------------------------------------

    def _analyze_fields(self, data: Any) -> Dict[str, int]:
        """Analyze field completion status."""
        stats = {
            "total": 0,
            "complete": 0,
            "missing": 0,
            "conflicting": 0,
            "completion_pct": 0.0,
        }

        for field_name, field_def in self._field_definitions.items():
            if not field_def.required:
                continue

            stats["total"] += 1

            # Get the field value from data
            field_value = getattr(data, field_name, None)

            if field_value is None:
                stats["missing"] += 1
            elif isinstance(field_value, ExtractedField):
                if field_value.status == FieldStatus.MISSING:
                    stats["missing"] += 1
                elif field_value.status == FieldStatus.CONFLICTING:
                    stats["conflicting"] += 1
                else:
                    stats["complete"] += 1
            else:
                # Non-ExtractedField with value
                stats["complete"] += 1

        if stats["total"] > 0:
            stats["completion_pct"] = round(
                (stats["complete"] / stats["total"]) * 100, 1
            )

        return stats

    def _determine_status(
        self,
        field_stats: Dict[str, int],
        issues: List[str],
    ) -> AuditStatus:
        """Determine overall audit status."""
        if issues:
            return AuditStatus.NEEDS_REVIEW

        if field_stats["conflicting"] > 0:
            return AuditStatus.NEEDS_REVIEW

        if field_stats["missing"] > 0:
            return AuditStatus.INCOMPLETE

        return AuditStatus.COMPLETE

    # -------------------------------------------------------------------------
    # Task Generation
    # -------------------------------------------------------------------------

    def _generate_tasks(
        self,
        data: Any,
        field_stats: Dict[str, int],
        loan_id: Optional[int],
        borrower_type: str,
    ) -> List[GeneratedTask]:
        """Generate tasks for missing/conflicting data."""
        tasks = []

        for field_name, field_def in self._field_definitions.items():
            field_value = getattr(data, field_name, None)

            # Check if task needed
            needs_task = False
            task_type = ""

            if field_value is None and field_def.required:
                needs_task = True
                task_type = "COLLECT_INFO"
            elif isinstance(field_value, ExtractedField):
                if field_value.status == FieldStatus.MISSING and field_def.required:
                    needs_task = True
                    task_type = "COLLECT_INFO"
                elif field_value.status == FieldStatus.CONFLICTING:
                    needs_task = True
                    task_type = "RESOLVE_CONFLICT"
                elif field_value.status == FieldStatus.INVALID:
                    needs_task = True
                    task_type = "VERIFY_INFO"

            if not needs_task:
                continue

            # Create task
            task = self._create_task_for_field(
                field_name=field_name,
                field_def=field_def,
                task_type=task_type,
                field_value=field_value,
                loan_id=loan_id,
                borrower_type=borrower_type,
            )

            if task:
                tasks.append(task)

        # Sort by priority
        priority_order = {
            TaskPriority.CRITICAL: 0,
            TaskPriority.HIGH: 1,
            TaskPriority.MEDIUM: 2,
            TaskPriority.LOW: 3,
        }
        tasks.sort(key=lambda t: priority_order.get(t.priority, 2))

        return tasks

    def _create_task_for_field(
        self,
        field_name: str,
        field_def: FieldDefinition,
        task_type: str,
        field_value: Optional[ExtractedField],
        loan_id: Optional[int],
        borrower_type: str,
    ) -> Optional[GeneratedTask]:
        """Create a task for a specific field."""

        # Determine title
        if field_def.task_title_template:
            title = field_def.task_title_template
        else:
            if task_type == "COLLECT_INFO":
                title = f"Collect {field_def.display_name}"
            elif task_type == "RESOLVE_CONFLICT":
                title = f"Resolve conflict: {field_def.display_name}"
            elif task_type == "VERIFY_INFO":
                title = f"Verify {field_def.display_name}"
            else:
                title = f"Review {field_def.display_name}"

        # Determine description
        if field_def.task_description_template:
            description = field_def.task_description_template
        else:
            if task_type == "COLLECT_INFO":
                description = f"Missing required field: {field_def.display_name}. Please collect this information from the borrower."
            elif task_type == "RESOLVE_CONFLICT":
                conflicts = field_value.conflicts if field_value else []
                description = f"Conflicting values found for {field_def.display_name}. Please verify the correct value."
                if conflicts:
                    description += f" Conflicts: {conflicts}"
            else:
                description = f"Please review and verify: {field_def.display_name}"

        # Determine assignee
        if field_def.requires_documentation:
            assignee = TaskAssignee.BORROWER
            borrower_visible = True
        else:
            assignee = TaskAssignee.PA
            borrower_visible = False

        # Determine priority
        if task_type == "RESOLVE_CONFLICT":
            priority = TaskPriority.HIGH
        elif field_def.required:
            priority = TaskPriority.MEDIUM
        else:
            priority = TaskPriority.LOW

        return GeneratedTask(
            task_id=str(uuid.uuid4())[:8],
            title=title,
            description=description,
            task_type=task_type,
            assignee=assignee,
            priority=priority,
            module=self.MODULE_TYPE,
            field_name=field_name,
            borrower_type=borrower_type,
            required_document_type=field_def.document_types[0] if field_def.document_types else None,
            days_until_due=3 if priority == TaskPriority.HIGH else 5,
            due_date=datetime.utcnow() + timedelta(days=3 if priority == TaskPriority.HIGH else 5),
            borrower_portal_visible=borrower_visible,
            borrower_instructions=field_def.borrower_instructions or None,
        )

    # -------------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------------

    def create_extracted_field(
        self,
        field_name: str,
        value: Any,
        confidence: float = 80.0,
        source: str = "call_transcript",
    ) -> ExtractedField:
        """Create an ExtractedField from extracted data."""
        status = FieldStatus.EXTRACTED

        if value is None or value == "":
            status = FieldStatus.MISSING
        elif confidence >= 90:
            status = FieldStatus.VERIFIED

        return ExtractedField(
            field_name=field_name,
            value=value,
            status=status,
            confidence=confidence,
            source=source,
            extracted_at=datetime.utcnow(),
        )

    def merge_field(
        self,
        call_value: Any,
        existing_value: Any,
        field_name: str,
        call_confidence: float = 80.0,
    ) -> ExtractedField:
        """
        Merge call-extracted value with existing value.

        Priority: Verified > Higher Confidence > Most Recent
        """
        # If no call value, use existing
        if call_value is None or call_value == "":
            if existing_value is None:
                return self.create_extracted_field(field_name, None, 0, "")

            if isinstance(existing_value, ExtractedField):
                return existing_value

            return self.create_extracted_field(
                field_name, existing_value, 100, "database"
            )

        # If no existing value, use call value
        if existing_value is None:
            return self.create_extracted_field(
                field_name, call_value, call_confidence, "call_transcript"
            )

        # Both values exist - check for conflict
        existing_val = existing_value.value if isinstance(existing_value, ExtractedField) else existing_value

        if str(call_value).strip().lower() == str(existing_val).strip().lower():
            # Values match - return verified
            return ExtractedField(
                field_name=field_name,
                value=call_value,
                status=FieldStatus.VERIFIED,
                confidence=max(call_confidence,
                              existing_value.confidence if isinstance(existing_value, ExtractedField) else 100),
                source="verified",
                verified_at=datetime.utcnow(),
                verification_method="call_confirm",
            )

        # Values conflict
        return ExtractedField(
            field_name=field_name,
            value=call_value,
            status=FieldStatus.CONFLICTING,
            confidence=call_confidence,
            source="call_transcript",
            extracted_at=datetime.utcnow(),
            conflicts=[
                {
                    "source": "existing",
                    "value": existing_val,
                    "from": existing_value.source if isinstance(existing_value, ExtractedField) else "database",
                }
            ],
        )

    def validate_date(self, value: Any) -> Tuple[bool, Optional[str]]:
        """Validate a date value."""
        from datetime import date

        if value is None:
            return False, "Date is missing"

        if isinstance(value, date):
            return True, None

        if isinstance(value, str):
            try:
                from dateutil import parser
                parser.parse(value)
                return True, None
            except (ValueError, TypeError):
                return False, f"Invalid date format: {value}"

        return False, f"Invalid date type: {type(value)}"

    def validate_ssn(self, value: Any) -> Tuple[bool, Optional[str]]:
        """Validate SSN format (last 4 only stored)."""
        if value is None:
            return False, "SSN is missing"

        ssn_str = str(value).replace("-", "").replace(" ", "")

        if len(ssn_str) == 4 and ssn_str.isdigit():
            return True, None

        if len(ssn_str) == 9 and ssn_str.isdigit():
            return True, None

        return False, "Invalid SSN format"

    def validate_email(self, value: Any) -> Tuple[bool, Optional[str]]:
        """Validate email format."""
        import re

        if value is None:
            return False, "Email is missing"

        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if re.match(pattern, str(value)):
            return True, None

        return False, f"Invalid email format: {value}"

    def validate_phone(self, value: Any) -> Tuple[bool, Optional[str]]:
        """Validate phone number format."""
        import re

        if value is None:
            return False, "Phone is missing"

        # Remove common formatting
        phone = re.sub(r'[\s\-\(\)\.]', '', str(value))

        # Check for valid length (10 or 11 digits)
        if len(phone) == 10 and phone.isdigit():
            return True, None

        if len(phone) == 11 and phone.startswith('1') and phone.isdigit():
            return True, None

        return False, f"Invalid phone format: {value}"

    def validate_zip(self, value: Any) -> Tuple[bool, Optional[str]]:
        """Validate ZIP code format."""
        import re

        if value is None:
            return False, "ZIP code is missing"

        zip_str = str(value)

        # 5-digit or 9-digit (ZIP+4)
        if re.match(r'^\d{5}(-\d{4})?$', zip_str):
            return True, None

        return False, f"Invalid ZIP format: {value}"
