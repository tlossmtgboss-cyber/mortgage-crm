#!/usr/bin/env python3
"""
Salesforce Integration Validator — Main Runner
===============================================
Orchestrates all validation checks for Perennia AI → Salesforce data sync.
Focuses on custom byte mapping accuracy and SLA date milestone integrity.

Usage:
    python run_validation.py --mode quick
    python run_validation.py --mode standard
    python run_validation.py --mode full --sample-size 500
    python run_validation.py --mode post-deploy --compare-previous
"""

import argparse
import json
import os
import sys
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = {
    "sample_size": 50,
    "days_back": 7,
    "sync_latency_tolerance_seconds": 300,
    "date_comparison_tolerance_hours": 24,
    "strict_byte_mapping": True,
    "report_output_dir": "./reports",
    "report_formats": ["json", "html"],
    "alert_on_critical": True,
}

VALIDATION_MODES = {
    "quick": {
        "sample_size": 10,
        "checks": ["field_existence", "push_sample", "critical_sla_only"],
        "description": "Quick health check — field existence + 10 record sample + critical SLA fields",
    },
    "standard": {
        "sample_size": 50,
        "checks": [
            "field_existence",
            "push_completeness",
            "byte_mapping_accuracy",
            "sla_workflow_chain",
        ],
        "description": "Standard validation — all fields, 50 records, byte mappings, SLA workflows",
    },
    "full": {
        "sample_size": 500,
        "checks": [
            "field_existence",
            "push_completeness",
            "byte_mapping_accuracy",
            "sla_workflow_chain",
            "historical_comparison",
            "trend_analysis",
        ],
        "description": "Full audit — everything + historical comparison + trend analysis",
    },
    "post-deploy": {
        "sample_size": 50,
        "checks": [
            "field_existence",
            "push_completeness",
            "byte_mapping_accuracy",
            "sla_workflow_chain",
            "compare_previous_baseline",
        ],
        "description": "Post-deployment verification — standard + comparison to last baseline",
    },
}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("sf_validator")

# ---------------------------------------------------------------------------
# Field Mapping Registry
# ---------------------------------------------------------------------------

# This is the canonical registry of all field mappings between Perennia AI
# and Salesforce. In production, load from config/field_mappings.yaml.
# This inline version serves as the reference and fallback.

FIELD_MAPPINGS = [
    # ── Loan Origination SLA Dates (Critical — drive workflows) ─────────
    {
        "source_system": "perennia_ai",
        "source_object": "loan",
        "source_field": "application_received_at",
        "source_type": "datetime",
        "sf_object": "Loan__c",
        "sf_field": "Application_Received_Date__c",
        "sf_type": "Date",
        "transform": "utc_to_date_only",
        "is_sla_field": True,
        "is_byte_mapped": True,
        "required": True,
        "sync_direction": "push",
        "sla_config": {
            "window_days": 0,
            "workflow_name": "Initial_Doc_Review",
            "task_type": "Document Review",
            "assigned_to": "Processor_Queue",
        },
    },
    {
        "source_system": "perennia_ai",
        "source_object": "loan",
        "source_field": "disclosure_sent_at",
        "source_type": "datetime",
        "sf_object": "Loan__c",
        "sf_field": "Disclosure_Sent_Date__c",
        "sf_type": "Date",
        "transform": "utc_to_date_only",
        "is_sla_field": True,
        "is_byte_mapped": True,
        "required": True,
        "sla_config": {
            "window_days": 3,
            "workflow_name": "TRID_Compliance_Check",
            "task_type": "Compliance Review",
            "assigned_to": "Compliance_Team",
        },
    },
    {
        "source_system": "perennia_ai",
        "source_object": "loan",
        "source_field": "disclosure_acknowledged_at",
        "source_type": "datetime",
        "sf_object": "Loan__c",
        "sf_field": "Disclosure_Ack_Date__c",
        "sf_type": "Date",
        "transform": "utc_to_date_only",
        "is_sla_field": True,
        "is_byte_mapped": True,
        "required": False,
        "sync_direction": "push",
        "sla_config": {
            "window_days": 10,
            "workflow_name": "Disclosure_Escalation",
            "task_type": "Escalation",
            "assigned_to": "Processor_Queue",
        },
    },
    {
        "source_system": "perennia_ai",
        "source_object": "loan",
        "source_field": "appraisal_ordered_at",
        "source_type": "datetime",
        "sf_object": "Loan__c",
        "sf_field": "Appraisal_Ordered_Date__c",
        "sf_type": "Date",
        "transform": "utc_to_date_only",
        "is_sla_field": True,
        "is_byte_mapped": True,
        "required": True,
        "sync_direction": "push",
        "sla_config": {
            "window_days": 1,
            "workflow_name": "Appraisal_Followup",
            "task_type": "Follow-up",
            "assigned_to": "Processor_Queue",
        },
    },
    {
        "source_system": "perennia_ai",
        "source_object": "loan",
        "source_field": "appraisal_received_at",
        "source_type": "datetime",
        "sf_object": "Loan__c",
        "sf_field": "Appraisal_Received_Date__c",
        "sf_type": "Date",
        "transform": "utc_to_date_only",
        "is_sla_field": True,
        "is_byte_mapped": True,
        "required": False,
        "sync_direction": "push",
        "sla_config": {
            "window_days": 0,
            "workflow_name": "Appraisal_Review",
            "task_type": "Appraisal Review",
            "assigned_to": "Processor_Queue",
        },
    },
    {
        "source_system": "perennia_ai",
        "source_object": "loan",
        "source_field": "title_ordered_at",
        "source_type": "datetime",
        "sf_object": "Loan__c",
        "sf_field": "Title_Ordered_Date__c",
        "sf_type": "Date",
        "transform": "utc_to_date_only",
        "is_sla_field": True,
        "is_byte_mapped": True,
        "required": True,
        "sync_direction": "push",
        "sla_config": {
            "window_days": 1,
            "workflow_name": "Title_Followup",
            "task_type": "Follow-up",
            "assigned_to": "Processor_Queue",
        },
    },
    {
        "source_system": "perennia_ai",
        "source_object": "loan",
        "source_field": "title_received_at",
        "source_type": "datetime",
        "sf_object": "Loan__c",
        "sf_field": "Title_Received_Date__c",
        "sf_type": "Date",
        "transform": "utc_to_date_only",
        "is_sla_field": True,
        "is_byte_mapped": True,
        "required": False,
        "sync_direction": "push",
        "sla_config": {
            "window_days": 0,
            "workflow_name": "Title_Review",
            "task_type": "Title Review",
            "assigned_to": "Processor_Queue",
        },
    },
    {
        "source_system": "perennia_ai",
        "source_object": "loan",
        "source_field": "conditions_sent_at",
        "source_type": "datetime",
        "sf_object": "Loan__c",
        "sf_field": "Conditions_Sent_Date__c",
        "sf_type": "Date",
        "transform": "utc_to_date_only",
        "is_sla_field": True,
        "is_byte_mapped": True,
        "required": False,
        "sync_direction": "push",
        "sla_config": {
            "window_days": 3,
            "workflow_name": "Condition_Followup",
            "task_type": "Condition Follow-up",
            "assigned_to": "Processor_Queue",
        },
    },
    {
        "source_system": "perennia_ai",
        "source_object": "loan",
        "source_field": "conditions_cleared_at",
        "source_type": "datetime",
        "sf_object": "Loan__c",
        "sf_field": "Conditions_Cleared_Date__c",
        "sf_type": "Date",
        "transform": "utc_to_date_only",
        "is_sla_field": True,
        "is_byte_mapped": True,
        "required": False,
        "sync_direction": "push",
        "sla_config": {
            "window_days": 0,
            "workflow_name": "Clear_To_Close_Prep",
            "task_type": "Closing Preparation",
            "assigned_to": "Closer_Queue",
        },
    },
    {
        "source_system": "perennia_ai",
        "source_object": "loan",
        "source_field": "clear_to_close_at",
        "source_type": "datetime",
        "sf_object": "Loan__c",
        "sf_field": "Clear_To_Close_Date__c",
        "sf_type": "Date",
        "transform": "utc_to_date_only",
        "is_sla_field": True,
        "is_byte_mapped": True,
        "required": False,
        "sync_direction": "push",
        "sla_config": {
            "window_days": 0,
            "workflow_name": "Closing_Package",
            "task_type": "Closing Package Prep",
            "assigned_to": "Closer_Queue",
        },
    },
    {
        "source_system": "perennia_ai",
        "source_object": "loan",
        "source_field": "closing_scheduled_at",
        "source_type": "datetime",
        "sf_object": "Loan__c",
        "sf_field": "Closing_Scheduled_Date__c",
        "sf_type": "DateTime",
        "transform": "utc_passthrough",
        "is_sla_field": True,
        "is_byte_mapped": True,
        "required": False,
        "sync_direction": "push",
        "sla_config": {
            "window_days": -1,
            "workflow_name": "Pre_Closing_Verification",
            "task_type": "Pre-Closing Check",
            "assigned_to": "Closer_Queue",
        },
    },
    {
        "source_system": "perennia_ai",
        "source_object": "loan",
        "source_field": "funded_at",
        "source_type": "datetime",
        "sf_object": "Loan__c",
        "sf_field": "Funded_Date__c",
        "sf_type": "Date",
        "transform": "utc_to_date_only",
        "is_sla_field": True,
        "is_byte_mapped": True,
        "required": False,
        "sync_direction": "push",
        "sla_config": {
            "window_days": 0,
            "workflow_name": "Post_Closing_Audit",
            "task_type": "Post-Closing Audit",
            "assigned_to": "Compliance_Team",
        },
    },
    {
        "source_system": "perennia_ai",
        "source_object": "loan",
        "source_field": "docs_out_at",
        "source_type": "datetime",
        "sf_object": "Loan__c",
        "sf_field": "Docs_Out_Date__c",
        "sf_type": "Date",
        "transform": "utc_to_date_only",
        "is_sla_field": True,
        "is_byte_mapped": True,
        "required": False,
        "sync_direction": "push",
        "sla_config": {
            "window_days": 0,
            "workflow_name": "Doc_Tracking_Confirmation",
            "task_type": "Document Tracking",
            "assigned_to": "Processor_Queue",
        },
    },
    {
        "source_system": "perennia_ai",
        "source_object": "loan",
        "source_field": "submitted_to_uw_at",
        "source_type": "datetime",
        "sf_object": "Loan__c",
        "sf_field": "Submitted_To_UW_Date__c",
        "sf_type": "Date",
        "transform": "utc_to_date_only",
        "is_sla_field": True,
        "is_byte_mapped": True,
        "required": True,
        "sync_direction": "push",
        "sla_config": {
            "window_days": 2,
            "workflow_name": "UW_Followup",
            "task_type": "UW Follow-up",
            "assigned_to": "Processor_Queue",
        },
    },
    # ── Borrower/Contact SLA Dates ──────────────────────────────────────
    {
        "source_system": "perennia_ai",
        "source_object": "borrower",
        "source_field": "last_contact_at",
        "source_type": "datetime",
        "sf_object": "Contact",
        "sf_field": "Last_Contact_Date__c",
        "sf_type": "Date",
        "transform": "utc_to_date_only",
        "is_sla_field": True,
        "is_byte_mapped": True,
        "required": False,
        "sync_direction": "push",
        "sla_config": {
            "window_days": 7,
            "workflow_name": "Re_Engagement",
            "task_type": "Re-engagement Outreach",
            "assigned_to": "LO_Owner",
        },
    },
    {
        "source_system": "perennia_ai",
        "source_object": "borrower",
        "source_field": "next_followup_at",
        "source_type": "datetime",
        "sf_object": "Contact",
        "sf_field": "Next_Followup_Date__c",
        "sf_type": "DateTime",
        "transform": "utc_passthrough",
        "is_sla_field": True,
        "is_byte_mapped": True,
        "required": False,
        "sync_direction": "push",
        "sla_config": {
            "window_days": 0,
            "workflow_name": "Followup_Reminder",
            "task_type": "Follow-up Reminder",
            "assigned_to": "LO_Owner",
        },
    },
    {
        "source_system": "perennia_ai",
        "source_object": "borrower",
        "source_field": "preapproval_expires_at",
        "source_type": "datetime",
        "sf_object": "Contact",
        "sf_field": "Preapproval_Expiry__c",
        "sf_type": "Date",
        "transform": "utc_to_date_only",
        "is_sla_field": True,
        "is_byte_mapped": True,
        "required": False,
        "sync_direction": "push",
        "sla_config": {
            "window_days": -14,
            "workflow_name": "Preapproval_Renewal",
            "task_type": "Renewal Outreach",
            "assigned_to": "LO_Owner",
        },
    },
    {
        "source_system": "perennia_ai",
        "source_object": "borrower",
        "source_field": "rate_lock_expires_at",
        "source_type": "datetime",
        "sf_object": "Contact",
        "sf_field": "Rate_Lock_Expiry__c",
        "sf_type": "Date",
        "transform": "utc_to_date_only",
        "is_sla_field": True,
        "is_byte_mapped": True,
        "required": False,
        "sync_direction": "push",
        "sla_config": {
            "window_days": -7,
            "workflow_name": "Rate_Lock_Extension",
            "task_type": "Rate Lock Review",
            "assigned_to": "LO_Owner",
        },
    },
    # ── Non-SLA Fields (Standard sync) ──────────────────────────────────
    {
        "source_system": "perennia_ai",
        "source_object": "loan",
        "source_field": "loan_amount",
        "source_type": "decimal",
        "sf_object": "Loan__c",
        "sf_field": "Loan_Amount__c",
        "sf_type": "Currency",
        "transform": "cents_to_dollars",
        "is_sla_field": False,
        "is_byte_mapped": False,
        "required": True,
        "sync_direction": "push",
    },
    {
        "source_system": "perennia_ai",
        "source_object": "loan",
        "source_field": "interest_rate",
        "source_type": "decimal",
        "sf_object": "Loan__c",
        "sf_field": "Interest_Rate__c",
        "sf_type": "Percent",
        "transform": "decimal_to_percent",
        "is_sla_field": False,
        "is_byte_mapped": False,
        "required": True,
        "sync_direction": "push",
    },
    {
        "source_system": "perennia_ai",
        "source_object": "loan",
        "source_field": "loan_status",
        "source_type": "string",
        "sf_object": "Loan__c",
        "sf_field": "Loan_Status__c",
        "sf_type": "Picklist",
        "transform": "status_code_to_label",
        "is_sla_field": False,
        "is_byte_mapped": False,
        "required": True,
        "sync_direction": "push",
    },
    {
        "source_system": "perennia_ai",
        "source_object": "loan",
        "source_field": "loan_type",
        "source_type": "string",
        "sf_object": "Loan__c",
        "sf_field": "Loan_Type__c",
        "sf_type": "Picklist",
        "transform": "none",
        "is_sla_field": False,
        "is_byte_mapped": False,
        "required": True,
        "sync_direction": "push",
    },
    {
        "source_system": "perennia_ai",
        "source_object": "borrower",
        "source_field": "email",
        "source_type": "string",
        "sf_object": "Contact",
        "sf_field": "Email",
        "sf_type": "Email",
        "transform": "none",
        "is_sla_field": False,
        "is_byte_mapped": False,
        "required": True,
        "sync_direction": "push",
    },
    {
        "source_system": "perennia_ai",
        "source_object": "borrower",
        "source_field": "phone",
        "source_type": "string",
        "sf_object": "Contact",
        "sf_field": "Phone",
        "sf_type": "Phone",
        "transform": "normalize_phone_e164",
        "is_sla_field": False,
        "is_byte_mapped": False,
        "required": False,
        "sync_direction": "push",
    },
    {
        "source_system": "perennia_ai",
        "source_object": "borrower",
        "source_field": "credit_score",
        "source_type": "integer",
        "sf_object": "Contact",
        "sf_field": "Credit_Score__c",
        "sf_type": "Number",
        "transform": "none",
        "is_sla_field": False,
        "is_byte_mapped": False,
        "required": False,
        "sync_direction": "push",
    },
]


# ---------------------------------------------------------------------------
# Validation Result Classes
# ---------------------------------------------------------------------------


class ValidationResult:
    """Single field-level or record-level validation result."""

    def __init__(
        self,
        check_name: str,
        status: str,
        severity: str,
        details: dict,
    ):
        self.check_name = check_name
        self.status = status  # PASS, FAIL, WARNING, SKIP
        self.severity = severity  # critical, high, medium, low
        self.details = details
        self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "check_name": self.check_name,
            "status": self.status,
            "severity": self.severity,
            "details": self.details,
            "timestamp": self.timestamp,
        }


class ValidationReport:
    """Aggregated validation report across all checks."""

    def __init__(self, mode: str, started_at: str):
        self.mode = mode
        self.started_at = started_at
        self.completed_at: Optional[str] = None
        self.results: list[ValidationResult] = []
        self.health_score: float = 0.0
        self.summary = {
            "total_checks": 0,
            "passed": 0,
            "failed": 0,
            "warnings": 0,
            "skipped": 0,
        }

    def add_result(self, result: ValidationResult):
        self.results.append(result)
        self.summary["total_checks"] += 1
        if result.status == "PASS":
            self.summary["passed"] += 1
        elif result.status == "FAIL":
            self.summary["failed"] += 1
        elif result.status == "WARNING":
            self.summary["warnings"] += 1
        elif result.status == "SKIP":
            self.summary["skipped"] += 1

    def calculate_health_score(self):
        """
        Health Score = (
            (critical_passing / total_critical) * 0.50 +
            (sla_passing / total_sla) * 0.30 +
            (all_passing / total_fields) * 0.15 +
            (workflow_passing / total_workflows) * 0.05
        ) * 100
        """
        critical_total = sum(
            1 for r in self.results if r.severity == "critical"
        )
        critical_passing = sum(
            1
            for r in self.results
            if r.severity == "critical" and r.status == "PASS"
        )

        sla_total = sum(
            1
            for r in self.results
            if r.details.get("is_sla_field", False)
        )
        sla_passing = sum(
            1
            for r in self.results
            if r.details.get("is_sla_field", False) and r.status == "PASS"
        )

        all_total = max(len(self.results), 1)
        all_passing = self.summary["passed"]

        workflow_total = sum(
            1
            for r in self.results
            if r.check_name.startswith("sla_workflow_")
        )
        workflow_passing = sum(
            1
            for r in self.results
            if r.check_name.startswith("sla_workflow_") and r.status == "PASS"
        )

        score = 0.0
        if critical_total > 0:
            score += (critical_passing / critical_total) * 0.50
        else:
            score += 0.50  # No critical fields = full marks for this bucket

        if sla_total > 0:
            score += (sla_passing / sla_total) * 0.30
        else:
            score += 0.30

        score += (all_passing / all_total) * 0.15

        if workflow_total > 0:
            score += (workflow_passing / workflow_total) * 0.05
        else:
            score += 0.05

        self.health_score = round(score * 100, 1)

    def finalize(self):
        self.completed_at = datetime.now(timezone.utc).isoformat()
        self.calculate_health_score()

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "health_score": self.health_score,
            "health_status": self._health_status(),
            "summary": self.summary,
            "results": [r.to_dict() for r in self.results],
            "sla_field_summary": self._sla_summary(),
            "byte_mapping_summary": self._byte_mapping_summary(),
            "critical_issues": self._critical_issues(),
        }

    def _health_status(self) -> str:
        if self.health_score >= 95:
            return "HEALTHY"
        elif self.health_score >= 85:
            return "WARNING"
        elif self.health_score >= 70:
            return "DEGRADED"
        else:
            return "CRITICAL"

    def _sla_summary(self) -> dict:
        sla_results = [
            r for r in self.results if r.details.get("is_sla_field", False)
        ]
        return {
            "total_sla_fields": len(sla_results),
            "passing": sum(1 for r in sla_results if r.status == "PASS"),
            "failing": sum(1 for r in sla_results if r.status == "FAIL"),
            "warnings": sum(1 for r in sla_results if r.status == "WARNING"),
        }

    def _byte_mapping_summary(self) -> dict:
        bm_results = [
            r
            for r in self.results
            if r.details.get("is_byte_mapped", False)
        ]
        return {
            "total_byte_mapped_fields": len(bm_results),
            "passing": sum(1 for r in bm_results if r.status == "PASS"),
            "failing": sum(1 for r in bm_results if r.status == "FAIL"),
            "decode_errors": sum(
                1
                for r in bm_results
                if r.details.get("error_type") == "BYTE_DECODE_ERROR"
            ),
        }

    def _critical_issues(self) -> list[dict]:
        return [
            r.to_dict()
            for r in self.results
            if r.status == "FAIL" and r.severity == "critical"
        ]


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------


class FieldExistenceValidator:
    """
    Step 2: Validate that all mapped fields exist in Salesforce
    and have the correct type and permissions.
    """

    def __init__(self, sf_client, mappings: list[dict]):
        self.sf_client = sf_client
        self.mappings = mappings

    def validate(self) -> list[ValidationResult]:
        results = []
        logger.info(
            "Validating field existence for %d mappings...", len(self.mappings)
        )

        for mapping in self.mappings:
            sf_object = mapping["sf_object"]
            sf_field = mapping["sf_field"]
            expected_type = mapping["sf_type"]
            is_sla = mapping.get("is_sla_field", False)
            is_byte_mapped = mapping.get("is_byte_mapped", False)

            severity = "critical" if is_sla else "medium"

            try:
                # Query Salesforce describe for the object
                field_meta = self.sf_client.describe_field(
                    sf_object, sf_field
                )

                if field_meta is None:
                    results.append(
                        ValidationResult(
                            check_name=f"field_exists.{sf_object}.{sf_field}",
                            status="FAIL",
                            severity=severity,
                            details={
                                "sf_object": sf_object,
                                "sf_field": sf_field,
                                "error": "Field does not exist on object",
                                "error_type": "FIELD_NOT_FOUND",
                                "is_sla_field": is_sla,
                                "is_byte_mapped": is_byte_mapped,
                                "source": f"{mapping['source_object']}.{mapping['source_field']}",
                            },
                        )
                    )
                    continue

                # Check type match
                if field_meta.get("type") != expected_type:
                    results.append(
                        ValidationResult(
                            check_name=f"field_type.{sf_object}.{sf_field}",
                            status="FAIL",
                            severity="high",
                            details={
                                "sf_object": sf_object,
                                "sf_field": sf_field,
                                "expected_type": expected_type,
                                "actual_type": field_meta.get("type"),
                                "error_type": "TYPE_MISMATCH",
                                "is_sla_field": is_sla,
                                "is_byte_mapped": is_byte_mapped,
                            },
                        )
                    )
                    continue

                # Check writability
                if not field_meta.get("updateable", False):
                    results.append(
                        ValidationResult(
                            check_name=f"field_writable.{sf_object}.{sf_field}",
                            status="FAIL",
                            severity="high",
                            details={
                                "sf_object": sf_object,
                                "sf_field": sf_field,
                                "error": "Field is not writable by integration user",
                                "error_type": "PERMISSION_ERROR",
                                "is_sla_field": is_sla,
                                "is_byte_mapped": is_byte_mapped,
                            },
                        )
                    )
                    continue

                # All checks passed
                results.append(
                    ValidationResult(
                        check_name=f"field_exists.{sf_object}.{sf_field}",
                        status="PASS",
                        severity=severity,
                        details={
                            "sf_object": sf_object,
                            "sf_field": sf_field,
                            "sf_type": field_meta.get("type"),
                            "is_sla_field": is_sla,
                            "is_byte_mapped": is_byte_mapped,
                        },
                    )
                )

            except Exception as e:
                results.append(
                    ValidationResult(
                        check_name=f"field_exists.{sf_object}.{sf_field}",
                        status="FAIL",
                        severity=severity,
                        details={
                            "sf_object": sf_object,
                            "sf_field": sf_field,
                            "error": str(e),
                            "error_type": "API_ERROR",
                            "is_sla_field": is_sla,
                            "is_byte_mapped": is_byte_mapped,
                        },
                    )
                )

        return results


class DataPushValidator:
    """
    Step 3: Validate data push completeness.
    For a sample of records, verify every mapped field was pushed correctly.
    """

    def __init__(
        self,
        sf_client,
        perennia_client,
        mappings: list[dict],
        sample_size: int = 50,
        days_back: int = 7,
    ):
        self.sf_client = sf_client
        self.perennia_client = perennia_client
        self.mappings = mappings
        self.sample_size = sample_size
        self.days_back = days_back

    def validate(self) -> list[ValidationResult]:
        results = []
        logger.info(
            "Validating data push for %d records over last %d days...",
            self.sample_size,
            self.days_back,
        )

        # Get sample of recently synced records from Perennia
        since = datetime.now(timezone.utc) - timedelta(days=self.days_back)
        source_records = self.perennia_client.get_recent_loans(
            limit=self.sample_size, since=since
        )

        for record in source_records:
            record_id = record.get("id")
            sf_external_id = record.get("salesforce_id")

            if not sf_external_id:
                results.append(
                    ValidationResult(
                        check_name=f"push_completeness.record.{record_id}",
                        status="FAIL",
                        severity="critical",
                        details={
                            "record_id": record_id,
                            "error": "No Salesforce ID — record never synced",
                            "error_type": "MISSING_SF_RECORD",
                            "is_sla_field": False,
                            "is_byte_mapped": False,
                        },
                    )
                )
                continue

            # Fetch the corresponding Salesforce record
            sf_record = self.sf_client.get_record(
                "Loan__c", sf_external_id
            )

            if sf_record is None:
                results.append(
                    ValidationResult(
                        check_name=f"push_completeness.record.{record_id}",
                        status="FAIL",
                        severity="critical",
                        details={
                            "record_id": record_id,
                            "sf_id": sf_external_id,
                            "error": "Salesforce record not found — may have been deleted",
                            "error_type": "SF_RECORD_NOT_FOUND",
                            "is_sla_field": False,
                            "is_byte_mapped": False,
                        },
                    )
                )
                continue

            # Check each mapped field
            for mapping in self.mappings:
                if mapping["source_object"] != "loan":
                    continue  # Handle borrower fields separately

                source_field = mapping["source_field"]
                sf_field = mapping["sf_field"]
                is_sla = mapping.get("is_sla_field", False)
                is_byte_mapped = mapping.get("is_byte_mapped", False)
                is_required = mapping.get("required", False)

                source_value = record.get(source_field)
                sf_value = sf_record.get(sf_field)

                severity = "critical" if is_sla else ("high" if is_required else "medium")

                # Check: source has value but SF doesn't
                if source_value is not None and sf_value is None:
                    error_type = (
                        "MISSING_SLA_DATE"
                        if is_sla
                        else "MISSING_FIELD_VALUE"
                    )
                    results.append(
                        ValidationResult(
                            check_name=f"push_value.{sf_field}.{record_id}",
                            status="FAIL",
                            severity=severity,
                            details={
                                "record_id": record_id,
                                "sf_id": sf_external_id,
                                "source_field": f"{mapping['source_object']}.{source_field}",
                                "sf_field": sf_field,
                                "source_value": str(source_value),
                                "sf_value": None,
                                "error": f"Source has value but Salesforce field is null",
                                "error_type": error_type,
                                "is_sla_field": is_sla,
                                "is_byte_mapped": is_byte_mapped,
                            },
                        )
                    )
                    continue

                # Check: values match (with transform awareness)
                if source_value is not None and sf_value is not None:
                    expected_sf_value = self._apply_transform(
                        source_value, mapping["transform"]
                    )
                    if not self._values_match(
                        expected_sf_value, sf_value, mapping
                    ):
                        results.append(
                            ValidationResult(
                                check_name=f"push_accuracy.{sf_field}.{record_id}",
                                status="FAIL",
                                severity=severity,
                                details={
                                    "record_id": record_id,
                                    "sf_id": sf_external_id,
                                    "source_field": f"{mapping['source_object']}.{source_field}",
                                    "sf_field": sf_field,
                                    "source_value": str(source_value),
                                    "expected_sf_value": str(expected_sf_value),
                                    "actual_sf_value": str(sf_value),
                                    "error": "Value mismatch after transform",
                                    "error_type": "VALUE_MISMATCH",
                                    "is_sla_field": is_sla,
                                    "is_byte_mapped": is_byte_mapped,
                                },
                            )
                        )
                        continue

                # Check: null placeholder detection
                if sf_value in ("1970-01-01", "9999-12-31", "1900-01-01"):
                    results.append(
                        ValidationResult(
                            check_name=f"null_placeholder.{sf_field}.{record_id}",
                            status="FAIL",
                            severity="high" if is_sla else "medium",
                            details={
                                "record_id": record_id,
                                "sf_field": sf_field,
                                "sf_value": sf_value,
                                "error": "Null placeholder date detected — should be null",
                                "error_type": "NULL_PLACEHOLDER",
                                "is_sla_field": is_sla,
                                "is_byte_mapped": is_byte_mapped,
                            },
                        )
                    )
                    continue

                # Passed all checks for this field/record
                results.append(
                    ValidationResult(
                        check_name=f"push_value.{sf_field}.{record_id}",
                        status="PASS",
                        severity=severity,
                        details={
                            "record_id": record_id,
                            "sf_field": sf_field,
                            "is_sla_field": is_sla,
                            "is_byte_mapped": is_byte_mapped,
                        },
                    )
                )

        return results

    def _apply_transform(self, value, transform: str):
        """Apply the configured transform to a source value."""
        if transform == "utc_to_date_only":
            if isinstance(value, str):
                dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return dt.strftime("%Y-%m-%d")
            return value
        elif transform == "cents_to_dollars":
            return round(float(value) / 100, 2)
        elif transform == "decimal_to_percent":
            return round(float(value) * 100, 4)
        elif transform == "utc_passthrough":
            return value
        elif transform == "status_code_to_label":
            # Map internal status codes to Salesforce picklist labels
            STATUS_MAP = {
                "application": "Application",
                "processing": "Processing",
                "underwriting": "Underwriting",
                "approved": "Approved",
                "clear_to_close": "Clear to Close",
                "closing": "Closing",
                "funded": "Funded",
                "denied": "Denied",
                "withdrawn": "Withdrawn",
            }
            return STATUS_MAP.get(value, value)
        elif transform == "normalize_phone_e164":
            # Strip non-digits and prepend +1 if US
            digits = "".join(c for c in str(value) if c.isdigit())
            if len(digits) == 10:
                return f"+1{digits}"
            elif len(digits) == 11 and digits.startswith("1"):
                return f"+{digits}"
            return value
        elif transform == "none":
            return value
        else:
            logger.warning("Unknown transform: %s", transform)
            return value

    def _values_match(self, expected, actual, mapping: dict) -> bool:
        """Compare expected and actual values with type-aware tolerance."""
        if expected is None and actual is None:
            return True

        sf_type = mapping.get("sf_type", "")

        # Date comparison with timezone tolerance
        if sf_type in ("Date", "DateTime"):
            try:
                if isinstance(expected, str) and isinstance(actual, str):
                    exp_date = expected[:10]  # YYYY-MM-DD
                    act_date = str(actual)[:10]
                    return exp_date == act_date
            except (ValueError, TypeError):
                return False

        # Numeric comparison with tolerance
        if sf_type in ("Currency", "Number", "Percent"):
            try:
                return abs(float(expected) - float(actual)) < 0.01
            except (ValueError, TypeError):
                return False

        # String comparison (case-insensitive for picklists)
        if sf_type == "Picklist":
            return str(expected).lower() == str(actual).lower()

        return str(expected) == str(actual)


class ByteMappingValidator:
    """
    Step 4: Validate custom byte mapping accuracy for date tracking fields.
    This is the most critical validation — ensures date milestones that drive
    workflows are correctly encoded, pushed, and decoded.
    """

    def __init__(
        self,
        sf_client,
        perennia_client,
        mappings: list[dict],
        strict: bool = True,
        sample_size: int = 50,
    ):
        self.sf_client = sf_client
        self.perennia_client = perennia_client
        self.mappings = [m for m in mappings if m.get("is_byte_mapped", False)]
        self.strict = strict
        self.sample_size = sample_size

    def validate(self) -> list[ValidationResult]:
        results = []
        logger.info(
            "Validating %d byte-mapped date fields (strict=%s)...",
            len(self.mappings),
            self.strict,
        )

        # Get sample records with their byte mapping data
        source_records = self.perennia_client.get_records_with_byte_mappings(
            limit=self.sample_size
        )

        for mapping in self.mappings:
            field_results = self._validate_field(mapping, source_records)
            results.extend(field_results)

        return results

    def _validate_field(
        self, mapping: dict, source_records: list[dict]
    ) -> list[ValidationResult]:
        results = []
        sf_field = mapping["sf_field"]
        source_field = mapping["source_field"]
        sf_object = mapping["sf_object"]

        exact_match = 0
        tz_adjusted_match = 0
        mismatch = 0
        null_correct = 0
        null_incorrect = 0
        decode_errors = 0
        issues = []

        for record in source_records:
            record_id = record.get("id")
            sf_id = record.get("salesforce_id")

            if not sf_id:
                continue

            # Step 1: Read source value
            source_value = record.get(source_field)

            # Step 2: Decode byte mapping
            byte_data = record.get("byte_mappings", {}).get(source_field)
            try:
                decoded_value = self._decode_byte_mapping(byte_data)
            except Exception as e:
                decode_errors += 1
                issues.append(
                    {
                        "record_id": record_id,
                        "error": f"Byte decode error: {e}",
                        "error_type": "BYTE_DECODE_ERROR",
                        "raw_bytes": str(byte_data),
                    }
                )
                continue

            # Step 3: Read destination value from Salesforce
            sf_record = self.sf_client.get_record(sf_object, sf_id)
            sf_value = sf_record.get(sf_field) if sf_record else None

            # Step 4: Compare
            if source_value is None and sf_value is None:
                null_correct += 1
                continue

            if source_value is None and sf_value is not None:
                if sf_value in ("1970-01-01", "9999-12-31", "1900-01-01"):
                    null_incorrect += 1
                    issues.append(
                        {
                            "record_id": record_id,
                            "source_value": None,
                            "sf_value": sf_value,
                            "issue": "Null placeholder in SF — should be null",
                            "error_type": "NULL_PLACEHOLDER",
                        }
                    )
                else:
                    null_incorrect += 1
                    issues.append(
                        {
                            "record_id": record_id,
                            "source_value": None,
                            "sf_value": sf_value,
                            "issue": "Source is null but SF has a value",
                            "error_type": "STALE_DATA",
                        }
                    )
                continue

            if source_value is not None and sf_value is None:
                mismatch += 1
                issues.append(
                    {
                        "record_id": record_id,
                        "source_value": str(source_value),
                        "sf_value": None,
                        "issue": "Source has value but SF field is null",
                        "error_type": "MISSING_SLA_DATE",
                    }
                )
                continue

            # Both have values — compare dates
            match_type = self._compare_dates(source_value, sf_value, mapping)
            if match_type == "exact":
                exact_match += 1
            elif match_type == "tz_adjusted":
                tz_adjusted_match += 1
                if self.strict:
                    issues.append(
                        {
                            "record_id": record_id,
                            "source_value": str(source_value),
                            "sf_value": str(sf_value),
                            "issue": "Date matched only after timezone adjustment",
                            "error_type": "TIMEZONE_SHIFT",
                        }
                    )
            else:
                mismatch += 1
                issues.append(
                    {
                        "record_id": record_id,
                        "source_value": str(source_value),
                        "sf_value": str(sf_value),
                        "issue": "Date values do not match",
                        "error_type": "VALUE_MISMATCH",
                    }
                )

        # Determine overall status for this field
        total_checked = (
            exact_match
            + tz_adjusted_match
            + mismatch
            + null_correct
            + null_incorrect
            + decode_errors
        )
        has_critical = mismatch > 0 or decode_errors > 0
        has_warnings = tz_adjusted_match > 0 or null_incorrect > 0

        if has_critical:
            status = "FAIL"
        elif has_warnings:
            status = "WARNING"
        else:
            status = "PASS"

        results.append(
            ValidationResult(
                check_name=f"byte_mapping.{sf_object}.{sf_field}",
                status=status,
                severity="critical",
                details={
                    "source_field": f"{mapping['source_object']}.{source_field}",
                    "sf_field": sf_field,
                    "sf_object": sf_object,
                    "records_checked": total_checked,
                    "exact_match": exact_match,
                    "timezone_adjusted_match": tz_adjusted_match,
                    "mismatch": mismatch,
                    "null_handling_correct": null_correct,
                    "null_handling_incorrect": null_incorrect,
                    "decode_errors": decode_errors,
                    "is_sla_field": mapping.get("is_sla_field", False),
                    "is_byte_mapped": True,
                    "issues": issues[:10],  # Cap issues for report size
                    "sla_config": mapping.get("sla_config"),
                },
            )
        )

        return results

    def _decode_byte_mapping(self, byte_data) -> Optional[str]:
        """
        Decode a custom byte mapping to a date string.
        Byte format: 4 bytes representing epoch seconds (big-endian unsigned int).
        Returns ISO date string or None.
        """
        if byte_data is None:
            return None

        if isinstance(byte_data, bytes):
            if len(byte_data) < 4:
                raise ValueError(
                    f"Byte mapping too short: {len(byte_data)} bytes"
                )
            epoch_seconds = int.from_bytes(byte_data[:4], byteorder="big")
        elif isinstance(byte_data, int):
            epoch_seconds = byte_data
        elif isinstance(byte_data, str):
            # Hex-encoded string
            byte_data_clean = byte_data.replace("0x", "").replace(" ", "")
            raw_bytes = bytes.fromhex(byte_data_clean)
            epoch_seconds = int.from_bytes(raw_bytes[:4], byteorder="big")
        else:
            raise ValueError(f"Unknown byte mapping format: {type(byte_data)}")

        if epoch_seconds == 0:
            return None  # Null sentinel

        dt = datetime.fromtimestamp(epoch_seconds, tz=timezone.utc)
        return dt.isoformat()

    def _compare_dates(
        self, source_value, sf_value, mapping: dict
    ) -> str:
        """
        Compare source and SF date values.
        Returns: 'exact', 'tz_adjusted', or 'mismatch'
        """
        try:
            # Parse source (always UTC datetime)
            if isinstance(source_value, str):
                source_dt = datetime.fromisoformat(
                    source_value.replace("Z", "+00:00")
                )
            else:
                source_dt = source_value

            source_date = source_dt.date() if hasattr(source_dt, "date") else source_dt

            # Parse SF value
            sf_str = str(sf_value)
            if "T" in sf_str:
                sf_dt = datetime.fromisoformat(
                    sf_str.replace("Z", "+00:00")
                )
                sf_date = sf_dt.date()
            else:
                sf_date = datetime.strptime(sf_str[:10], "%Y-%m-%d").date()

            # Exact date match
            if source_date == sf_date:
                return "exact"

            # Check if off by 1 day (timezone issue)
            diff = abs((source_date - sf_date).days)
            if diff == 1:
                return "tz_adjusted"

            return "mismatch"

        except (ValueError, TypeError, AttributeError):
            return "mismatch"


class SLAWorkflowValidator:
    """
    Step 5: Validate that SLA dates in Salesforce trigger the expected workflows.
    """

    def __init__(self, sf_client, mappings: list[dict]):
        self.sf_client = sf_client
        self.sla_mappings = [
            m for m in mappings if m.get("is_sla_field", False)
        ]

    def validate(self) -> list[ValidationResult]:
        results = []
        logger.info(
            "Validating SLA workflow chains for %d milestone fields...",
            len(self.sla_mappings),
        )

        for mapping in self.sla_mappings:
            sla_config = mapping.get("sla_config", {})
            if not sla_config:
                continue

            sf_field = mapping["sf_field"]
            workflow_name = sla_config.get("workflow_name")
            task_type = sla_config.get("task_type")
            assigned_to = sla_config.get("assigned_to")
            window_days = sla_config.get("window_days", 0)

            # Check 1: Workflow Rule or Flow exists and is active
            workflow_active = self.sf_client.check_workflow_active(
                workflow_name
            )

            if not workflow_active:
                results.append(
                    ValidationResult(
                        check_name=f"sla_workflow_exists.{sf_field}",
                        status="FAIL",
                        severity="critical",
                        details={
                            "sf_field": sf_field,
                            "workflow_name": workflow_name,
                            "error": "Workflow rule/flow not found or inactive",
                            "is_sla_field": True,
                            "is_byte_mapped": True,
                        },
                    )
                )
                continue

            # Check 2: Workflow references the correct field
            workflow_references_field = (
                self.sf_client.check_workflow_references_field(
                    workflow_name, sf_field
                )
            )

            if not workflow_references_field:
                results.append(
                    ValidationResult(
                        check_name=f"sla_workflow_field_ref.{sf_field}",
                        status="FAIL",
                        severity="critical",
                        details={
                            "sf_field": sf_field,
                            "workflow_name": workflow_name,
                            "error": f"Workflow does not reference field {sf_field}",
                            "is_sla_field": True,
                            "is_byte_mapped": True,
                        },
                    )
                )
                continue

            # Check 3: Verify tasks are being created
            recent_tasks = self.sf_client.get_recent_tasks_by_type(
                task_type, days_back=7
            )

            if not recent_tasks:
                results.append(
                    ValidationResult(
                        check_name=f"sla_workflow_tasks.{sf_field}",
                        status="WARNING",
                        severity="high",
                        details={
                            "sf_field": sf_field,
                            "workflow_name": workflow_name,
                            "task_type": task_type,
                            "error": "No tasks found for this SLA type in last 7 days",
                            "note": "May be expected if no loans reached this milestone recently",
                            "is_sla_field": True,
                            "is_byte_mapped": True,
                        },
                    )
                )
                continue

            # Check 4: Verify task assignment
            misassigned = [
                t
                for t in recent_tasks
                if t.get("assigned_to") != assigned_to
                and assigned_to != "LO_Owner"  # LO_Owner is dynamic
            ]

            if misassigned:
                results.append(
                    ValidationResult(
                        check_name=f"sla_workflow_assignment.{sf_field}",
                        status="WARNING",
                        severity="medium",
                        details={
                            "sf_field": sf_field,
                            "workflow_name": workflow_name,
                            "expected_assignee": assigned_to,
                            "misassigned_count": len(misassigned),
                            "total_tasks": len(recent_tasks),
                            "is_sla_field": True,
                            "is_byte_mapped": True,
                        },
                    )
                )
                continue

            # All workflow checks passed
            results.append(
                ValidationResult(
                    check_name=f"sla_workflow_chain.{sf_field}",
                    status="PASS",
                    severity="critical",
                    details={
                        "sf_field": sf_field,
                        "workflow_name": workflow_name,
                        "task_type": task_type,
                        "assigned_to": assigned_to,
                        "window_days": window_days,
                        "recent_tasks_count": len(recent_tasks),
                        "is_sla_field": True,
                        "is_byte_mapped": True,
                    },
                )
            )

        return results


# ---------------------------------------------------------------------------
# Client Interfaces (Abstract — implement for your environment)
# ---------------------------------------------------------------------------


class SalesforceClient:
    """
    Salesforce API client interface.
    Replace with your actual Salesforce connection (simple-salesforce, etc.)
    """

    def __init__(self, config: dict):
        self.config = config
        self._connection = None

    def connect(self):
        """Establish Salesforce connection using OAuth or username/password."""
        # Implementation: use simple-salesforce or custom OAuth flow
        #
        # from simple_salesforce import Salesforce
        # self._connection = Salesforce(
        #     instance_url=self.config['SF_INSTANCE_URL'],
        #     username=self.config['SF_USERNAME'],
        #     password=self.config['SF_PASSWORD'],
        #     security_token=self.config['SF_SECURITY_TOKEN'],
        # )
        raise NotImplementedError("Implement with your SF connection library")

    def describe_field(self, object_name: str, field_name: str) -> Optional[dict]:
        """Get field metadata from Salesforce object describe."""
        raise NotImplementedError

    def get_record(self, object_name: str, record_id: str) -> Optional[dict]:
        """Get a single record by ID."""
        raise NotImplementedError

    def check_workflow_active(self, workflow_name: str) -> bool:
        """Check if a workflow rule or flow is active."""
        raise NotImplementedError

    def check_workflow_references_field(
        self, workflow_name: str, field_name: str
    ) -> bool:
        """Check if a workflow references a specific field."""
        raise NotImplementedError

    def get_recent_tasks_by_type(
        self, task_type: str, days_back: int = 7
    ) -> list[dict]:
        """Get recent tasks filtered by type."""
        raise NotImplementedError


class PerenniaClient:
    """
    Perennia AI API/database client interface.
    Replace with your actual data access layer.
    """

    def __init__(self, config: dict):
        self.config = config

    def get_recent_loans(
        self, limit: int = 50, since: Optional[datetime] = None
    ) -> list[dict]:
        """Get recently updated loan records."""
        raise NotImplementedError

    def get_records_with_byte_mappings(
        self, limit: int = 50
    ) -> list[dict]:
        """Get records that include raw byte mapping data for validation."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Report Generator
# ---------------------------------------------------------------------------


class ReportGenerator:
    """Generate validation reports in JSON and HTML formats."""

    def __init__(self, output_dir: str = "./reports"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(self, report: ValidationReport, formats: list[str] = None):
        formats = formats or ["json", "html"]
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")

        if "json" in formats:
            self._write_json(report, timestamp)

        if "html" in formats:
            self._write_html(report, timestamp)

        logger.info("Reports written to %s", self.output_dir)

    def _write_json(self, report: ValidationReport, timestamp: str):
        filepath = self.output_dir / f"validation_report_{timestamp}.json"
        with open(filepath, "w") as f:
            json.dump(report.to_dict(), f, indent=2, default=str)
        logger.info("JSON report: %s", filepath)

    def _write_html(self, report: ValidationReport, timestamp: str):
        filepath = self.output_dir / f"validation_report_{timestamp}.html"
        data = report.to_dict()

        health_color = {
            "HEALTHY": "#22c55e",
            "WARNING": "#f59e0b",
            "DEGRADED": "#f97316",
            "CRITICAL": "#ef4444",
        }.get(data["health_status"], "#6b7280")

        critical_issues_html = ""
        for issue in data.get("critical_issues", []):
            critical_issues_html += f"""
            <div class="issue-card critical">
                <strong>{issue['check_name']}</strong>
                <p>{issue['details'].get('error', 'Unknown error')}</p>
                <small>SF Field: {issue['details'].get('sf_field', 'N/A')} |
                       Type: {issue['details'].get('error_type', 'N/A')}</small>
            </div>"""

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>SF Integration Validation — {timestamp}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
               background: #0f172a; color: #e2e8f0; padding: 2rem; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{ font-size: 1.75rem; margin-bottom: 0.5rem; }}
        .subtitle {{ color: #94a3b8; margin-bottom: 2rem; }}
        .health-score {{
            display: inline-flex; align-items: center; gap: 1rem;
            background: #1e293b; border-radius: 12px; padding: 1.5rem 2rem;
            margin-bottom: 2rem; border-left: 4px solid {health_color};
        }}
        .score-number {{ font-size: 3rem; font-weight: 700; color: {health_color}; }}
        .score-label {{ font-size: 1.25rem; color: {health_color}; text-transform: uppercase; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                 gap: 1rem; margin-bottom: 2rem; }}
        .card {{
            background: #1e293b; border-radius: 8px; padding: 1.25rem;
            border: 1px solid #334155;
        }}
        .card h3 {{ font-size: 0.875rem; color: #94a3b8; text-transform: uppercase;
                     letter-spacing: 0.05em; margin-bottom: 0.5rem; }}
        .card .value {{ font-size: 2rem; font-weight: 700; }}
        .pass {{ color: #22c55e; }}
        .fail {{ color: #ef4444; }}
        .warn {{ color: #f59e0b; }}
        .issue-card {{
            background: #1e293b; border-radius: 8px; padding: 1rem;
            margin-bottom: 0.75rem; border-left: 3px solid #ef4444;
        }}
        .issue-card.critical {{ border-left-color: #ef4444; }}
        .issue-card strong {{ display: block; margin-bottom: 0.25rem; }}
        .issue-card small {{ color: #94a3b8; }}
        .section {{ margin-bottom: 2rem; }}
        .section h2 {{ font-size: 1.25rem; margin-bottom: 1rem;
                        border-bottom: 1px solid #334155; padding-bottom: 0.5rem; }}
    </style>
</head>
<body>
<div class="container">
    <h1>Salesforce Integration Validation</h1>
    <p class="subtitle">Mode: {data['mode']} | Run: {data['started_at']}</p>

    <div class="health-score">
        <div>
            <div class="score-number">{data['health_score']}</div>
            <div class="score-label">{data['health_status']}</div>
        </div>
    </div>

    <div class="grid">
        <div class="card">
            <h3>Total Checks</h3>
            <div class="value">{data['summary']['total_checks']}</div>
        </div>
        <div class="card">
            <h3>Passed</h3>
            <div class="value pass">{data['summary']['passed']}</div>
        </div>
        <div class="card">
            <h3>Failed</h3>
            <div class="value fail">{data['summary']['failed']}</div>
        </div>
        <div class="card">
            <h3>Warnings</h3>
            <div class="value warn">{data['summary']['warnings']}</div>
        </div>
    </div>

    <div class="grid">
        <div class="card">
            <h3>SLA Fields</h3>
            <div class="value">{data['sla_field_summary']['total_sla_fields']}</div>
            <small class="pass">{data['sla_field_summary']['passing']} passing</small> /
            <small class="fail">{data['sla_field_summary']['failing']} failing</small>
        </div>
        <div class="card">
            <h3>Byte-Mapped Fields</h3>
            <div class="value">{data['byte_mapping_summary']['total_byte_mapped_fields']}</div>
            <small class="pass">{data['byte_mapping_summary']['passing']} passing</small> /
            <small class="fail">{data['byte_mapping_summary']['failing']} failing</small>
        </div>
    </div>

    <div class="section">
        <h2>Critical Issues ({len(data.get('critical_issues', []))})</h2>
        {critical_issues_html if critical_issues_html else '<p style="color:#94a3b8">No critical issues found.</p>'}
    </div>
</div>
</body>
</html>"""

        with open(filepath, "w") as f:
            f.write(html)
        logger.info("HTML report: %s", filepath)


# ---------------------------------------------------------------------------
# Main Orchestrator
# ---------------------------------------------------------------------------


def run_validation(
    mode: str = "standard",
    sample_size: Optional[int] = None,
    compare_previous: bool = False,
    strict_byte_mapping: bool = True,
):
    """Run the full validation suite."""

    mode_config = VALIDATION_MODES.get(mode, VALIDATION_MODES["standard"])
    effective_sample_size = sample_size or mode_config["sample_size"]
    checks = mode_config["checks"]

    logger.info("=" * 60)
    logger.info("Salesforce Integration Validation")
    logger.info("Mode: %s — %s", mode, mode_config["description"])
    logger.info("Sample size: %d", effective_sample_size)
    logger.info("Checks: %s", ", ".join(checks))
    logger.info("=" * 60)

    report = ValidationReport(
        mode=mode,
        started_at=datetime.now(timezone.utc).isoformat(),
    )

    # Load config from environment
    config = {k: os.environ.get(k, "") for k in DEFAULT_CONFIG}

    # Initialize clients
    sf_client = SalesforceClient(config)
    perennia_client = PerenniaClient(config)

    try:
        sf_client.connect()
    except NotImplementedError:
        logger.warning(
            "SalesforceClient.connect() not implemented — "
            "running in dry-run mode with field mapping validation only"
        )

    # Run checks based on mode
    if "field_existence" in checks:
        logger.info("── Step 1: Validating field existence ──")
        validator = FieldExistenceValidator(sf_client, FIELD_MAPPINGS)
        try:
            results = validator.validate()
            for r in results:
                report.add_result(r)
        except NotImplementedError:
            logger.warning("Skipping field existence (client not implemented)")

    if "push_completeness" in checks or "push_sample" in checks:
        logger.info("── Step 2: Validating data push completeness ──")
        push_sample = 10 if "push_sample" in checks else effective_sample_size
        validator = DataPushValidator(
            sf_client, perennia_client, FIELD_MAPPINGS, sample_size=push_sample
        )
        try:
            results = validator.validate()
            for r in results:
                report.add_result(r)
        except NotImplementedError:
            logger.warning("Skipping data push (client not implemented)")

    if "byte_mapping_accuracy" in checks:
        logger.info("── Step 3: Validating byte mapping accuracy ──")
        validator = ByteMappingValidator(
            sf_client,
            perennia_client,
            FIELD_MAPPINGS,
            strict=strict_byte_mapping,
            sample_size=effective_sample_size,
        )
        try:
            results = validator.validate()
            for r in results:
                report.add_result(r)
        except NotImplementedError:
            logger.warning("Skipping byte mappings (client not implemented)")

    if "sla_workflow_chain" in checks or "critical_sla_only" in checks:
        logger.info("── Step 4: Validating SLA workflow chains ──")
        mappings_to_check = FIELD_MAPPINGS
        if "critical_sla_only" in checks:
            # Only check the most critical SLA fields in quick mode
            critical_fields = {
                "Application_Received_Date__c",
                "Clear_To_Close_Date__c",
                "Funded_Date__c",
                "Submitted_To_UW_Date__c",
            }
            mappings_to_check = [
                m
                for m in FIELD_MAPPINGS
                if m["sf_field"] in critical_fields
            ]
        validator = SLAWorkflowValidator(sf_client, mappings_to_check)
        try:
            results = validator.validate()
            for r in results:
                report.add_result(r)
        except NotImplementedError:
            logger.warning("Skipping SLA workflows (client not implemented)")

    # Finalize and generate report
    report.finalize()

    logger.info("=" * 60)
    logger.info("Health Score: %.1f (%s)", report.health_score, report._health_status())
    logger.info(
        "Results: %d passed, %d failed, %d warnings",
        report.summary["passed"],
        report.summary["failed"],
        report.summary["warnings"],
    )
    logger.info("=" * 60)

    # Generate reports
    report_gen = ReportGenerator(
        output_dir=os.environ.get("REPORT_OUTPUT_DIR", "./reports")
    )
    report_gen.generate(report, formats=["json", "html"])

    # Alert on critical issues
    if report.summary["failed"] > 0 and os.environ.get("ALERT_ON_CRITICAL"):
        _send_alert(report)

    return report


def _send_alert(report: ValidationReport):
    """Send alert for critical failures (Slack webhook, email, etc.)."""
    webhook_url = os.environ.get("ALERT_WEBHOOK_URL")
    if not webhook_url:
        return

    critical_count = len(report._critical_issues())
    logger.warning(
        "ALERT: %d critical issues found. Health score: %.1f",
        critical_count,
        report.health_score,
    )
    # Implementation: POST to Slack webhook with report summary
    # requests.post(webhook_url, json={...})


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Salesforce Integration Validator for Perennia AI"
    )
    parser.add_argument(
        "--mode",
        choices=list(VALIDATION_MODES.keys()),
        default="standard",
        help="Validation mode",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=None,
        help="Override sample size",
    )
    parser.add_argument(
        "--compare-previous",
        action="store_true",
        help="Compare against previous baseline",
    )
    parser.add_argument(
        "--no-strict",
        action="store_true",
        help="Disable strict byte mapping validation",
    )
    args = parser.parse_args()

    run_validation(
        mode=args.mode,
        sample_size=args.sample_size,
        compare_previous=args.compare_previous,
        strict_byte_mapping=not args.no_strict,
    )
