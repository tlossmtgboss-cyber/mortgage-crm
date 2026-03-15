#!/usr/bin/env python3
"""
================================================================================
PERENNIA AI - KNOWLEDGE & CAPABILITY TEST SUITE
================================================================================
Part 1: Core Framework

Comprehensive testing to evaluate what the AI knows about:
- Pipeline stages and workflows
- CRM entities and relationships
- Loan lifecycle and statuses
- Tool capabilities and usage
- Business rules and compliance

================================================================================
"""

import os
import json
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple, Callable
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


# =============================================================================
# TEST RESULT TYPES
# =============================================================================

class TestStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    PARTIAL = "partial"
    SKIPPED = "skipped"
    ERROR = "error"


class KnowledgeCategory(str, Enum):
    PIPELINE = "pipeline"
    CRM = "crm"
    LOANS = "loans"
    CONTACTS = "contacts"
    COMPLIANCE = "compliance"
    TOOLS = "tools"
    WORKFLOWS = "workflows"
    INTEGRATIONS = "integrations"
    REPORTING = "reporting"
    COMMUNICATION = "communication"


class TestDifficulty(str, Enum):
    """Test difficulty levels."""
    BASIC = "basic"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


class TestType(str, Enum):
    """Types of knowledge tests."""
    FACTUAL = "factual"
    CONCEPTUAL = "conceptual"
    PROCEDURAL = "procedural"
    APPLICATION = "application"
    TOOL_USAGE = "tool_usage"


@dataclass
class TestResult:
    """Result of a single test"""
    test_id: str
    category: KnowledgeCategory
    name: str
    status: TestStatus
    score: float  # 0.0 to 1.0
    expected: Any
    actual: Any
    details: str = ""
    execution_time_ms: int = 0
    response: str = ""
    error: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "test_id": self.test_id,
            "category": self.category.value,
            "name": self.name,
            "status": self.status.value,
            "score": self.score,
            "expected": str(self.expected)[:200],
            "actual": str(self.actual)[:200],
            "details": self.details,
            "execution_time_ms": self.execution_time_ms,
        }


@dataclass
class CategoryReport:
    """Report for a knowledge category"""
    category: KnowledgeCategory
    total_tests: int
    passed: int
    failed: int
    partial: int
    skipped: int = 0
    errors: int = 0
    average_score: float = 0.0
    coverage_percentage: float = 0.0
    weak_areas: List[str] = field(default_factory=list)
    strong_areas: List[str] = field(default_factory=list)
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)


@dataclass
class FullReport:
    """Complete test report"""
    timestamp: str = ""
    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    partial: int = 0
    overall_score: float = 0.0
    categories: Dict[str, CategoryReport] = field(default_factory=dict)
    results: List[TestResult] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    execution_time: float = 0.0
    execution_time_seconds: float = 0.0


# =============================================================================
# EXPECTED ANSWER VALIDATION
# =============================================================================

@dataclass
class ExpectedAnswer:
    """Expected answer with validation criteria."""
    keywords: List[str] = field(default_factory=list)
    forbidden: List[str] = field(default_factory=list)
    patterns: List[str] = field(default_factory=list)
    min_length: int = 10
    max_length: int = 5000
    custom_validator: Optional[Callable[[str], float]] = None

    def validate(self, response: str) -> Tuple[float, str]:
        """Validate response and return (score, details)."""
        import re
        response_lower = response.lower()
        details = []
        scores = []

        if len(response) < self.min_length:
            return 0.0, f"Response too short ({len(response)} < {self.min_length})"
        if len(response) > self.max_length:
            details.append(f"Response truncated (>{self.max_length} chars)")

        if self.keywords:
            found = sum(1 for kw in self.keywords if kw.lower() in response_lower)
            keyword_score = found / len(self.keywords)
            scores.append(keyword_score)
            if keyword_score < 1.0:
                missing = [kw for kw in self.keywords if kw.lower() not in response_lower]
                details.append(f"Missing keywords: {missing[:3]}")

        if self.forbidden:
            forbidden_found = [f for f in self.forbidden if f.lower() in response_lower]
            if forbidden_found:
                scores.append(0.5)
                details.append(f"Contains forbidden terms: {forbidden_found}")
            else:
                scores.append(1.0)

        if self.patterns:
            matched = sum(1 for p in self.patterns if re.search(p, response, re.IGNORECASE))
            pattern_score = matched / len(self.patterns)
            scores.append(pattern_score)
            if pattern_score < 1.0:
                details.append(f"Pattern matches: {matched}/{len(self.patterns)}")

        if self.custom_validator:
            custom_score = self.custom_validator(response)
            scores.append(custom_score)

        final_score = sum(scores) / len(scores) if scores else 0.5
        return final_score, "; ".join(details) if details else "All criteria met"


@dataclass
class KnowledgeTest:
    """Definition of a single knowledge test."""
    id: str
    name: str
    category: KnowledgeCategory
    question: str
    expected: ExpectedAnswer
    difficulty: TestDifficulty = TestDifficulty.INTERMEDIATE
    test_type: TestType = TestType.FACTUAL
    context: Optional[str] = None
    hints: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    weight: float = 1.0
    timeout: int = 30


# =============================================================================
# MORTGAGE KNOWLEDGE BASE
# =============================================================================

class MortgageKnowledgeBase:
    """
    Defines what the AI SHOULD know about the mortgage/CRM domain.
    This is the ground truth for testing.
    """

    # -------------------------------------------------------------------------
    # PIPELINE STAGES
    # -------------------------------------------------------------------------

    PIPELINE_STAGES = {
        "lead": {
            "order": 1,
            "display_name": "Lead",
            "description": "Initial contact, not yet qualified",
            "typical_duration_days": 7,
            "next_stages": ["prospect", "dead"],
            "required_fields": ["name", "phone_or_email"],
            "sla_hours": None,
        },
        "prospect": {
            "order": 2,
            "display_name": "Prospect",
            "description": "Qualified lead, actively engaged",
            "typical_duration_days": 14,
            "next_stages": ["application", "dead"],
            "required_fields": ["loan_purpose", "property_type", "estimated_value"],
            "sla_hours": 48,
        },
        "application": {
            "order": 3,
            "display_name": "Application",
            "description": "Loan application received",
            "typical_duration_days": 3,
            "next_stages": ["processing", "withdrawn"],
            "required_fields": ["full_application", "credit_auth"],
            "sla_hours": 24,
        },
        "processing": {
            "order": 4,
            "display_name": "Processing",
            "description": "Gathering documents, ordering services",
            "typical_duration_days": 7,
            "next_stages": ["submitted", "suspended"],
            "required_fields": ["income_docs", "asset_docs", "property_docs"],
            "sla_hours": 72,
        },
        "submitted": {
            "order": 5,
            "display_name": "Submitted to UW",
            "description": "Submitted to underwriting",
            "typical_duration_days": 1,
            "next_stages": ["underwriting"],
            "required_fields": ["complete_package"],
            "sla_hours": 24,
        },
        "underwriting": {
            "order": 6,
            "display_name": "Underwriting",
            "description": "Under review by underwriter",
            "typical_duration_days": 3,
            "next_stages": ["approved", "denied", "suspended"],
            "required_fields": [],
            "sla_hours": 48,
        },
        "approved": {
            "order": 7,
            "display_name": "Approved",
            "description": "Conditionally approved",
            "typical_duration_days": 5,
            "next_stages": ["clear_to_close"],
            "required_fields": ["conditions_cleared"],
            "sla_hours": 72,
        },
        "clear_to_close": {
            "order": 8,
            "display_name": "Clear to Close",
            "description": "All conditions satisfied",
            "typical_duration_days": 3,
            "next_stages": ["closing"],
            "required_fields": ["final_approval", "closing_disclosure"],
            "sla_hours": 24,
        },
        "closing": {
            "order": 9,
            "display_name": "Closing",
            "description": "Scheduled for closing",
            "typical_duration_days": 3,
            "next_stages": ["funded"],
            "required_fields": ["closing_date", "closing_docs"],
            "sla_hours": None,
        },
        "funded": {
            "order": 10,
            "display_name": "Funded",
            "description": "Loan has funded",
            "typical_duration_days": None,
            "next_stages": [],
            "required_fields": [],
            "sla_hours": None,
        },
    }

    TERMINAL_STAGES = ["funded", "denied", "withdrawn", "dead"]

    # -------------------------------------------------------------------------
    # LOAN TYPES
    # -------------------------------------------------------------------------

    LOAN_TYPES = {
        "conventional": {
            "display_name": "Conventional",
            "min_credit_score": 620,
            "max_dti": 50,
            "min_down_payment": 3,
            "requires_pmi": True,
            "conforming_limit": 832750,
        },
        "fha": {
            "display_name": "FHA",
            "min_credit_score": 580,
            "max_dti": 57,
            "min_down_payment": 3.5,
            "requires_mip": True,
            "upfront_mip": 1.75,
        },
        "va": {
            "display_name": "VA",
            "min_credit_score": 620,
            "max_dti": 60,
            "min_down_payment": 0,
            "requires_coe": True,
            "funding_fee": True,
        },
        "usda": {
            "display_name": "USDA",
            "min_credit_score": 640,
            "max_dti": 41,
            "min_down_payment": 0,
            "income_limits": True,
            "geographic_restrictions": True,
        },
        "jumbo": {
            "display_name": "Jumbo",
            "min_credit_score": 700,
            "max_dti": 43,
            "min_down_payment": 10,
            "exceeds_conforming": True,
        },
    }

    LOAN_PURPOSES = ["purchase", "refinance", "cash_out_refinance", "heloc"]

    PROPERTY_TYPES = [
        "single_family",
        "condo",
        "townhouse",
        "multi_family_2_4",
        "manufactured",
        "investment",
    ]

    OCCUPANCY_TYPES = ["primary_residence", "second_home", "investment"]

    # -------------------------------------------------------------------------
    # CRM ENTITIES
    # -------------------------------------------------------------------------

    CRM_ENTITIES = {
        "contact": {
            "description": "A person in the CRM",
            "key_fields": ["id", "first_name", "last_name", "email", "phone", "mobile"],
            "relationships": ["loans", "tasks", "activities", "notes", "documents"],
            "searchable_by": ["name", "email", "phone", "loan_number"],
        },
        "loan": {
            "description": "A mortgage loan application",
            "key_fields": ["id", "loan_number", "status", "amount", "rate", "loan_type"],
            "relationships": ["borrower", "co_borrower", "property", "documents", "conditions"],
            "searchable_by": ["loan_number", "borrower_name", "property_address"],
        },
        "property": {
            "description": "Real estate property",
            "key_fields": ["id", "address", "city", "state", "zip", "type", "value"],
            "relationships": ["loan", "appraisal"],
            "searchable_by": ["address", "city", "zip"],
        },
        "task": {
            "description": "Action item or to-do",
            "key_fields": ["id", "title", "due_date", "status", "priority", "assigned_to"],
            "relationships": ["contact", "loan", "user"],
            "searchable_by": ["title", "assigned_to", "status"],
        },
        "document": {
            "description": "Uploaded file or document",
            "key_fields": ["id", "name", "type", "status", "uploaded_at"],
            "relationships": ["loan", "contact", "condition"],
            "searchable_by": ["name", "type", "loan_number"],
        },
        "condition": {
            "description": "Underwriting condition",
            "key_fields": ["id", "description", "category", "status", "due_date"],
            "relationships": ["loan", "document"],
            "categories": ["prior_to_docs", "prior_to_funding", "prior_to_closing"],
        },
        "user": {
            "description": "System user (LO, processor, etc.)",
            "key_fields": ["id", "name", "email", "role", "team"],
            "roles": ["loan_officer", "processor", "underwriter", "closer", "manager", "admin"],
        },
    }

    # -------------------------------------------------------------------------
    # COMPLIANCE RULES
    # -------------------------------------------------------------------------

    COMPLIANCE_RULES = {
        "trid": {
            "name": "TILA-RESPA Integrated Disclosure",
            "rules": {
                "le_timing": "Loan Estimate within 3 business days of application",
                "cd_timing": "Closing Disclosure 3 business days before closing",
                "changed_circumstances": "Revised LE required for valid changed circumstances",
                "tolerance_categories": {
                    "zero_tolerance": ["origination_charges", "transfer_taxes"],
                    "ten_percent": ["third_party_services_shopped"],
                    "unlimited": ["prepaid_interest", "insurance", "escrow"],
                },
            },
        },
        "respa": {
            "name": "Real Estate Settlement Procedures Act",
            "rules": {
                "section_8": "No kickbacks or referral fees",
                "section_9": "No seller-required title insurance",
                "section_10": "Escrow account limits",
                "affiliated_business": "Disclosure required for affiliated businesses",
            },
        },
        "ecoa": {
            "name": "Equal Credit Opportunity Act",
            "rules": {
                "protected_classes": [
                    "race", "color", "religion", "national_origin",
                    "sex", "marital_status", "age", "public_assistance",
                ],
                "adverse_action": "Notice required within 30 days",
                "appraisal_copy": "Provide copy promptly upon completion",
            },
        },
        "fair_lending": {
            "name": "Fair Lending",
            "rules": {
                "disparate_treatment": "No different treatment based on protected class",
                "disparate_impact": "Policies must not disproportionately affect protected groups",
                "redlining": "No geographic discrimination",
            },
        },
        "hmda": {
            "name": "Home Mortgage Disclosure Act",
            "rules": {
                "data_collection": "Must collect demographic information",
                "reporting": "Annual LAR submission",
                "covered_loans": "Most closed-end mortgages and HELOCs",
            },
        },
    }

    # -------------------------------------------------------------------------
    # SLA DEFINITIONS
    # -------------------------------------------------------------------------

    SLA_DEFINITIONS = {
        "application_to_disclosure": {
            "name": "Application to LE",
            "target_hours": 24,
            "max_hours": 72,
            "stage_from": "application",
            "stage_to": "le_sent",
        },
        "disclosure_to_processing": {
            "name": "LE to Processing",
            "target_hours": 48,
            "max_hours": 168,
            "stage_from": "le_sent",
            "stage_to": "processing",
        },
        "processing_to_submission": {
            "name": "Processing to Submission",
            "target_hours": 120,
            "max_hours": 240,
            "stage_from": "processing",
            "stage_to": "submitted",
        },
        "submission_to_decision": {
            "name": "Submission to Decision",
            "target_hours": 48,
            "max_hours": 120,
            "stage_from": "submitted",
            "stage_to": "approved",
        },
        "approval_to_ctc": {
            "name": "Approval to CTC",
            "target_hours": 72,
            "max_hours": 168,
            "stage_from": "approved",
            "stage_to": "clear_to_close",
        },
        "ctc_to_closing": {
            "name": "CTC to Closing",
            "target_hours": 72,
            "max_hours": 120,
            "stage_from": "clear_to_close",
            "stage_to": "closing",
        },
    }

    # -------------------------------------------------------------------------
    # DOCUMENT TYPES
    # -------------------------------------------------------------------------

    DOCUMENT_TYPES = {
        "income": [
            "w2", "paystub", "tax_return", "1099",
            "profit_loss", "bank_statement", "employment_letter",
        ],
        "asset": [
            "bank_statement", "investment_statement", "retirement_statement",
            "gift_letter", "sale_proceeds",
        ],
        "property": [
            "purchase_contract", "appraisal", "title_commitment",
            "survey", "hoa_docs", "insurance_quote",
        ],
        "identity": [
            "drivers_license", "passport", "ssn_card",
        ],
        "credit": [
            "credit_report", "explanation_letter", "payoff_statement",
        ],
        "closing": [
            "closing_disclosure", "note", "deed_of_trust",
            "settlement_statement", "funding_authorization",
        ],
    }

    DOCUMENT_CATEGORIES = DOCUMENT_TYPES  # Alias for compatibility

    # -------------------------------------------------------------------------
    # TOOLS BY AGENT (160 tools across 20 agents)
    # -------------------------------------------------------------------------

    TOOLS_BY_AGENT = {
        "pipeline_analyst": [
            "get_pipeline_metrics",
            "get_loans_by_status",
            "get_loan_aging_report",
            "calculate_conversion_rates",
            "predict_closing_timeline",
            "get_bottleneck_analysis",
            "compare_to_benchmark",
            "get_lo_pipeline_breakdown",
        ],
        "compliance_checker": [
            "check_trid_compliance",
            "check_respa_compliance",
            "check_fair_lending",
            "get_state_requirements",
            "audit_loan_file",
            "get_disclosure_timeline",
            "check_tolerance_violations",
            "get_compliance_history",
        ],
        "lead_nurturer": [
            "get_lead_details",
            "get_engagement_history",
            "score_lead",
            "suggest_followup",
            "draft_message",
            "schedule_outreach",
            "get_similar_converted_leads",
            "get_optimal_contact_time",
        ],
        "document_tracker": [
            "get_missing_documents",
            "get_loan_conditions",
            "track_document_request",
            "send_document_reminder",
            "escalate_issue",
            "get_document_timeline",
            "check_document_expiration",
            "get_third_party_status",
        ],
        "profitability_analyst": [
            "calculate_loan_profitability",
            "analyze_margins_by_segment",
            "forecast_revenue",
            "compare_lo_profitability",
            "optimize_pricing",
            "get_cost_breakdown",
            "calculate_pull_through_impact",
            "get_profitability_trends",
        ],
        "rate_advisor": [
            "get_current_rates",
            "analyze_rate_trends",
            "calculate_lock_cost",
            "recommend_lock_strategy",
            "monitor_float_position",
            "get_extension_pricing",
            "compare_rate_scenarios",
            "get_market_events",
        ],
        "team_coach": [
            "get_lo_metrics",
            "compare_to_peers",
            "identify_training_needs",
            "generate_coaching_plan",
            "track_improvement",
            "get_best_practices",
            "get_performance_trends",
            "set_performance_goals",
        ],
        "customer_intelligence": [
            "get_customer_360",
            "map_relationships",
            "calculate_ltv",
            "assess_churn_risk",
            "find_opportunities",
            "get_interaction_history",
            "get_referral_network",
            "get_market_comparison",
        ],
        "voice_os": [
            "initiate_outbound_call",
            "drop_voicemail",
            "get_call_history",
            "analyze_call_sentiment",
            "schedule_callback",
            "get_power_dialer_queue",
            "transcribe_call",
            "get_call_metrics",
        ],
        "uvip_video": [
            "schedule_video_meeting",
            "get_meeting_recordings",
            "analyze_meeting",
            "send_async_video",
            "get_video_analytics",
            "extract_meeting_action_items",
            "generate_meeting_summary",
            "get_participant_insights",
        ],
        "email_intelligence": [
            "parse_email",
            "get_email_thread",
            "draft_email_response",
            "send_email",
            "get_email_templates",
            "analyze_email_engagement",
            "match_email_to_loan",
            "categorize_email_attachments",
        ],
        "ai_receptionist": [
            "handle_inbound_call",
            "qualify_caller",
            "route_call",
            "get_lo_availability",
            "create_callback_request",
            "get_greeting_script",
            "log_call_interaction",
            "get_call_queue_status",
        ],
        "smart_scheduler": [
            "get_availability",
            "book_appointment",
            "reschedule_appointment",
            "cancel_appointment",
            "get_upcoming_appointments",
            "send_appointment_reminder",
            "sync_external_calendar",
            "optimize_schedule",
        ],
        "task_automation": [
            "create_task",
            "get_tasks",
            "complete_task",
            "create_workflow",
            "get_workflow_status",
            "trigger_automation",
            "get_automation_rules",
            "schedule_recurring_task",
        ],
        "sla_tracker": [
            "get_sla_status",
            "get_milestone_history",
            "check_sla_breach",
            "get_sla_report",
            "set_sla_alert",
            "get_cycle_time_analysis",
            "get_bottleneck_report",
            "forecast_closing",
        ],
        "integrations": [
            "get_integration_status",
            "sync_calendar",
            "sync_contacts",
            "push_to_los",
            "pull_from_los",
            "connect_integration",
            "test_integration",
            "get_sync_history",
        ],
        "reporting": [
            "generate_pipeline_report",
            "generate_production_report",
            "get_kpi_dashboard",
            "export_report",
            "get_trending_metrics",
            "get_comparison_report",
            "schedule_report",
            "get_custom_report",
        ],
        "notifications": [
            "send_notification",
            "get_sla_alerts",
            "create_alert_rule",
            "get_notification_history",
            "mark_notification_read",
            "get_alert_subscriptions",
            "update_alert_subscription",
            "broadcast_announcement",
        ],
        "subscription": [
            "get_subscription_status",
            "get_usage_summary",
            "check_feature_access",
            "get_billing_history",
            "update_subscription",
            "cancel_subscription",
            "get_available_plans",
            "add_payment_method",
        ],
        "onboarding": [
            "create_user_account",
            "get_onboarding_status",
            "complete_onboarding_step",
            "assign_training",
            "get_training_progress",
            "configure_user_permissions",
            "setup_integrations",
            "generate_welcome_kit",
        ],
    }

    # Alias for tool categories
    TOOL_CATEGORIES = {agent: len(tools) for agent, tools in TOOLS_BY_AGENT.items()}

    # -------------------------------------------------------------------------
    # BUSINESS METRICS
    # -------------------------------------------------------------------------

    KEY_METRICS = {
        "pipeline": [
            "total_loans",
            "total_volume",
            "loans_by_stage",
            "average_loan_size",
            "pipeline_velocity",
        ],
        "production": [
            "loans_closed_mtd",
            "volume_closed_mtd",
            "units_per_lo",
            "average_days_to_close",
            "pull_through_rate",
        ],
        "quality": [
            "first_time_approval_rate",
            "condition_count_average",
            "defect_rate",
            "fallout_rate",
            "customer_satisfaction",
        ],
        "efficiency": [
            "application_to_close_days",
            "time_in_processing",
            "time_in_underwriting",
            "sla_compliance_rate",
            "touches_per_loan",
        ],
        "profitability": [
            "revenue_per_loan",
            "cost_per_loan",
            "margin_per_loan",
            "revenue_mtd",
            "margin_percentage",
        ],
    }

    # -------------------------------------------------------------------------
    # SLA TARGETS (days) - for compatibility
    # -------------------------------------------------------------------------

    SLA_TARGETS = {
        "application_to_disclosure": 3,
        "disclosure_to_submission": 7,
        "submission_to_approval": 5,
        "approval_to_ctc": 3,
        "ctc_to_funding": 5,
    }

    # -------------------------------------------------------------------------
    # CLASS METHODS
    # -------------------------------------------------------------------------

    @classmethod
    def get_all_stages(cls) -> List[str]:
        return list(cls.PIPELINE_STAGES.keys())

    @classmethod
    def get_stage_order(cls, stage: str) -> int:
        return cls.PIPELINE_STAGES.get(stage, {}).get("order", 0)

    @classmethod
    def get_all_tools(cls) -> List[str]:
        all_tools = []
        for tools in cls.TOOLS_BY_AGENT.values():
            all_tools.extend(tools)
        return all_tools

    @classmethod
    def get_tool_count(cls) -> int:
        return len(cls.get_all_tools())

    @classmethod
    def get_total_tools(cls) -> int:
        """Alias for get_tool_count for compatibility."""
        return cls.get_tool_count()

    @classmethod
    def get_agent_count(cls) -> int:
        return len(cls.TOOLS_BY_AGENT)

    @classmethod
    def validate_pipeline_order(cls, stages: List[str]) -> bool:
        """Check if stages are in correct order."""
        try:
            indices = [cls.get_stage_order(s.lower()) for s in stages]
            return indices == sorted(indices)
        except (ValueError, KeyError):
            return False

    @classmethod
    def get_loan_requirements(cls, loan_type: str) -> Optional[Dict]:
        """Get requirements for a loan type."""
        return cls.LOAN_TYPES.get(loan_type.lower())


# =============================================================================
# TEST CASE BASE
# =============================================================================

class TestCase(ABC):
    """Base class for all test cases"""

    def __init__(
        self,
        test_id: str,
        name: str,
        category: KnowledgeCategory,
        description: str = "",
    ):
        self.test_id = test_id
        self.name = name
        self.category = category
        self.description = description

    @abstractmethod
    async def run(self, ai_handler: Callable) -> TestResult:
        """Run the test and return result"""
        pass

    def _create_result(
        self,
        status: TestStatus,
        score: float,
        expected: Any,
        actual: Any,
        details: str = "",
        execution_time_ms: int = 0,
    ) -> TestResult:
        return TestResult(
            test_id=self.test_id,
            category=self.category,
            name=self.name,
            status=status,
            score=score,
            expected=expected,
            actual=actual,
            details=details,
            execution_time_ms=execution_time_ms,
        )


class QuestionAnswerTest(TestCase):
    """Test that asks the AI a question and checks the answer"""

    def __init__(
        self,
        test_id: str,
        name: str,
        category: KnowledgeCategory,
        question: str,
        expected_keywords: List[str],
        required_keywords: List[str] = None,
        forbidden_keywords: List[str] = None,
        min_keyword_matches: int = None,
    ):
        super().__init__(test_id, name, category, question)
        self.question = question
        self.expected_keywords = [k.lower() for k in expected_keywords]
        self.required_keywords = [k.lower() for k in (required_keywords or [])]
        self.forbidden_keywords = [k.lower() for k in (forbidden_keywords or [])]
        self.min_keyword_matches = min_keyword_matches or max(1, len(expected_keywords) // 2)

    async def run(self, ai_handler: Callable) -> TestResult:
        start_time = datetime.now()

        try:
            response = await ai_handler(self.question)
            response_lower = response.lower()

            for kw in self.required_keywords:
                if kw not in response_lower:
                    return self._create_result(
                        status=TestStatus.FAILED,
                        score=0.0,
                        expected=f"Must contain: {kw}",
                        actual=response[:200],
                        details=f"Missing required keyword: {kw}",
                        execution_time_ms=int((datetime.now() - start_time).total_seconds() * 1000),
                    )

            for kw in self.forbidden_keywords:
                if kw in response_lower:
                    return self._create_result(
                        status=TestStatus.FAILED,
                        score=0.0,
                        expected=f"Must NOT contain: {kw}",
                        actual=response[:200],
                        details=f"Contains forbidden keyword: {kw}",
                        execution_time_ms=int((datetime.now() - start_time).total_seconds() * 1000),
                    )

            matches = sum(1 for kw in self.expected_keywords if kw in response_lower)
            score = matches / len(self.expected_keywords) if self.expected_keywords else 1.0

            if matches >= self.min_keyword_matches:
                status = TestStatus.PASSED if score >= 0.8 else TestStatus.PARTIAL
            else:
                status = TestStatus.FAILED

            return self._create_result(
                status=status,
                score=score,
                expected=self.expected_keywords,
                actual=response[:500],
                details=f"Matched {matches}/{len(self.expected_keywords)} keywords",
                execution_time_ms=int((datetime.now() - start_time).total_seconds() * 1000),
            )

        except Exception as e:
            return self._create_result(
                status=TestStatus.ERROR,
                score=0.0,
                expected=self.expected_keywords,
                actual=str(e),
                details=f"Error: {str(e)}",
                execution_time_ms=int((datetime.now() - start_time).total_seconds() * 1000),
            )


class ToolUsageTest(TestCase):
    """Test that the AI uses the correct tool for a task"""

    def __init__(
        self,
        test_id: str,
        name: str,
        category: KnowledgeCategory,
        prompt: str,
        expected_tools: List[str],
        allow_alternatives: bool = True,
    ):
        super().__init__(test_id, name, category, prompt)
        self.prompt = prompt
        self.expected_tools = expected_tools
        self.allow_alternatives = allow_alternatives

    async def run(self, ai_handler: Callable) -> TestResult:
        start_time = datetime.now()

        try:
            response, tools_used = await ai_handler(self.prompt, return_tools=True)

            if not tools_used:
                return self._create_result(
                    status=TestStatus.FAILED,
                    score=0.0,
                    expected=self.expected_tools,
                    actual="No tools used",
                    details="AI did not use any tools",
                    execution_time_ms=int((datetime.now() - start_time).total_seconds() * 1000),
                )

            tools_used_names = [t.get("name", t) if isinstance(t, dict) else t for t in tools_used]
            matches = sum(1 for t in self.expected_tools if t in tools_used_names)
            score = matches / len(self.expected_tools)

            if matches == len(self.expected_tools):
                status = TestStatus.PASSED
            elif matches > 0 or (self.allow_alternatives and tools_used):
                status = TestStatus.PARTIAL
            else:
                status = TestStatus.FAILED

            return self._create_result(
                status=status,
                score=score,
                expected=self.expected_tools,
                actual=tools_used_names,
                details=f"Used {matches}/{len(self.expected_tools)} expected tools",
                execution_time_ms=int((datetime.now() - start_time).total_seconds() * 1000),
            )

        except Exception as e:
            return self._create_result(
                status=TestStatus.ERROR,
                score=0.0,
                expected=self.expected_tools,
                actual=str(e),
                details=f"Error: {str(e)}",
                execution_time_ms=int((datetime.now() - start_time).total_seconds() * 1000),
            )


class DataAccuracyTest(TestCase):
    """Test that AI returns accurate data from the CRM"""

    def __init__(
        self,
        test_id: str,
        name: str,
        category: KnowledgeCategory,
        query: str,
        expected_data: Dict[str, Any],
        tolerance: float = 0.0,
    ):
        super().__init__(test_id, name, category, query)
        self.query = query
        self.expected_data = expected_data
        self.tolerance = tolerance

    async def run(self, ai_handler: Callable) -> TestResult:
        start_time = datetime.now()

        try:
            response = await ai_handler(self.query, return_data=True)

            if isinstance(response, str):
                try:
                    import re
                    json_match = re.search(r'\{.*\}', response, re.DOTALL)
                    if json_match:
                        response = json.loads(json_match.group())
                except Exception as e:
                    logger.error(f"Error parsing JSON from AI response: {e}")

            if not isinstance(response, dict):
                return self._create_result(
                    status=TestStatus.FAILED,
                    score=0.0,
                    expected=self.expected_data,
                    actual=response,
                    details="Response is not structured data",
                    execution_time_ms=int((datetime.now() - start_time).total_seconds() * 1000),
                )

            matches = 0
            total = len(self.expected_data)

            for key, expected_value in self.expected_data.items():
                actual_value = response.get(key)

                if actual_value is None:
                    continue

                if isinstance(expected_value, (int, float)) and isinstance(actual_value, (int, float)):
                    if abs(expected_value - actual_value) <= self.tolerance:
                        matches += 1
                elif str(expected_value).lower() == str(actual_value).lower():
                    matches += 1

            score = matches / total if total > 0 else 0
            status = TestStatus.PASSED if score >= 0.9 else (TestStatus.PARTIAL if score >= 0.5 else TestStatus.FAILED)

            return self._create_result(
                status=status,
                score=score,
                expected=self.expected_data,
                actual=response,
                details=f"Matched {matches}/{total} fields",
                execution_time_ms=int((datetime.now() - start_time).total_seconds() * 1000),
            )

        except Exception as e:
            return self._create_result(
                status=TestStatus.ERROR,
                score=0.0,
                expected=self.expected_data,
                actual=str(e),
                details=f"Error: {str(e)}",
                execution_time_ms=int((datetime.now() - start_time).total_seconds() * 1000),
            )


# =============================================================================
# SCORING HELPERS
# =============================================================================

def calculate_keyword_score(response: str, keywords: List[str]) -> float:
    """Calculate score based on keyword presence."""
    if not keywords:
        return 1.0
    response_lower = response.lower()
    found = sum(1 for kw in keywords if kw.lower() in response_lower)
    return found / len(keywords)


def calculate_pattern_score(response: str, patterns: List[str]) -> float:
    """Calculate score based on regex pattern matches."""
    import re
    if not patterns:
        return 1.0
    matches = sum(1 for p in patterns if re.search(p, response, re.IGNORECASE))
    return matches / len(patterns)


def create_pipeline_validator() -> Callable[[str], float]:
    """Create validator for pipeline stage knowledge."""
    def validator(response: str) -> float:
        response_lower = response.lower()
        stages_found = sum(1 for s in MortgageKnowledgeBase.get_all_stages()
                         if s in response_lower)
        return min(1.0, stages_found / 5)
    return validator


def create_tool_count_validator(expected_min: int) -> Callable[[str], float]:
    """Create validator that checks for tool count mention."""
    import re
    def validator(response: str) -> float:
        numbers = re.findall(r'\b(\d+)\s*tools?\b', response, re.IGNORECASE)
        if numbers:
            count = max(int(n) for n in numbers)
            if count >= expected_min:
                return 1.0
            return count / expected_min
        return 0.5
    return validator


def create_compliance_validator(regulation: str) -> Callable[[str], float]:
    """Create validator for compliance knowledge."""
    compliance_terms = {
        "trid": ["loan estimate", "closing disclosure", "3 business days", "tolerance"],
        "respa": ["kickback", "referral fee", "section 8", "affiliated business"],
        "ecoa": ["fair lending", "discrimination", "protected class", "equal credit"],
    }

    terms = compliance_terms.get(regulation.lower(), [])

    def validator(response: str) -> float:
        if not terms:
            return 0.5
        response_lower = response.lower()
        found = sum(1 for t in terms if t in response_lower)
        return found / len(terms)

    return validator


# =============================================================================
# EXPORT
# =============================================================================

__all__ = [
    "TestStatus",
    "TestDifficulty",
    "TestType",
    "KnowledgeCategory",
    "TestResult",
    "CategoryReport",
    "FullReport",
    "ExpectedAnswer",
    "KnowledgeTest",
    "MortgageKnowledgeBase",
    "TestCase",
    "QuestionAnswerTest",
    "ToolUsageTest",
    "DataAccuracyTest",
    "calculate_keyword_score",
    "calculate_pattern_score",
    "create_pipeline_validator",
    "create_tool_count_validator",
    "create_compliance_validator",
]
