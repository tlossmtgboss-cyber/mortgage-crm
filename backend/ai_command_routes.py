"""
AI Command Routes for Perennia AI AI Landing Page

This module provides endpoints for processing natural language commands
and executing CRM actions through Claude AI.
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, File, UploadFile, Request
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from pydantic import BaseModel
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta
import logging
import os
import json
import uuid
import time
import anthropic
import base64

from database import get_db
from conversation_memory_service import ConversationMemory
from crm_context_service import CRMContextService
from pattern_analyzer import PatternAnalyzer
from query_executor import QueryExecutor, execute_query, format_results

logger = logging.getLogger(__name__)


# ============================================================================
# AI Reliability Configuration
# ============================================================================

AI_CONFIG = {
    "temperature": 0,           # No randomness - deterministic
    "top_p": 1,                  # No nucleus sampling
    "max_tokens": 2000,
}


# ============================================================================
# Circuit Breaker Pattern
# ============================================================================

class AICircuitBreaker:
    """Circuit breaker to prevent cascading AI failures"""

    def __init__(self, failure_threshold=3, timeout=300):
        self.failure_count = 0
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED = working, OPEN = broken

    def record_success(self):
        """Record successful AI call"""
        self.failure_count = 0
        if self.state == "HALF_OPEN":
            self.state = "CLOSED"
            logger.info("AI Circuit breaker CLOSED - recovered")

    def record_failure(self):
        """Record failed AI call"""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            logger.error(f"AI Circuit breaker OPEN after {self.failure_count} failures")

    def can_execute(self) -> bool:
        """Check if we can make an AI call"""
        if self.state == "CLOSED":
            return True

        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.timeout:
                self.state = "HALF_OPEN"
                logger.info("AI Circuit breaker HALF_OPEN - attempting recovery")
                return True
            return False

        # HALF_OPEN - allow one test call
        return True

    def get_fallback(self) -> Dict[str, Any]:
        """Return fallback response when circuit is open"""
        return {
            "intent": "GENERAL_QUERY",
            "explanation": "The AI assistant is temporarily unavailable. Please try again in a few minutes.",
            "data": {},
            "fallback": True
        }


# Global circuit breaker instance
ai_circuit_breaker = AICircuitBreaker(failure_threshold=3, timeout=300)


# ============================================================================
# AI Metrics Logging
# ============================================================================

class AIMetrics:
    """Log AI interactions for monitoring and debugging"""

    @staticmethod
    def log_interaction(
        user_id: int,
        request_message: str,
        response: Dict[str, Any],
        execution_time_ms: float,
        success: bool,
        error: str = None,
        function_calls_made: int = 0
    ):
        """Log an AI interaction"""
        try:
            logger.info(f"AI_METRIC | user_id={user_id} | "
                       f"intent={response.get('intent', 'UNKNOWN')} | "
                       f"success={success} | "
                       f"time_ms={execution_time_ms:.0f} | "
                       f"function_calls={function_calls_made} | "
                       f"message_preview={request_message[:50]}...")

            if error:
                logger.error(f"AI_ERROR | user_id={user_id} | error={error}")
        except Exception as e:
            logger.warning(f"Failed to log AI metrics: {e}")


# ============================================================================
# Function Calling Tools Definition
# ============================================================================

AI_TOOLS = [
    {
        "name": "get_daily_summary",
        "description": "Get the user's daily summary including tasks, leads, loans, and follow-ups",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "search_crm",
        "description": "Search for leads, loans, or clients by name, email, or phone",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search term (name, email, or phone)"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "update_lead_status",
        "description": "Update a lead's status/stage in the CRM",
        "input_schema": {
            "type": "object",
            "properties": {
                "lead_id": {
                    "type": "integer",
                    "description": "The lead's ID"
                },
                "new_status": {
                    "type": "string",
                    "enum": ["New", "Prospect", "Application Started", "Pre-Approved", "Closed Won", "Closed Lost"],
                    "description": "New status for the lead"
                }
            },
            "required": ["lead_id", "new_status"]
        }
    },
    {
        "name": "create_task",
        "description": "Create a new task in the CRM",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Task title"
                },
                "due_date": {
                    "type": "string",
                    "description": "Due date in ISO format (YYYY-MM-DD)"
                },
                "priority": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "description": "Task priority"
                },
                "lead_id": {
                    "type": "integer",
                    "description": "Optional lead ID to associate with task"
                }
            },
            "required": ["title", "due_date"]
        }
    },
    {
        "name": "send_email_campaign",
        "description": "Send an email campaign to selected clients",
        "input_schema": {
            "type": "object",
            "properties": {
                "filter_criteria": {
                    "type": "object",
                    "description": "Criteria to select recipients (status, loan_type, etc.)"
                },
                "subject": {
                    "type": "string",
                    "description": "Email subject line"
                },
                "body": {
                    "type": "string",
                    "description": "Email body content"
                }
            },
            "required": ["subject", "body"]
        }
    },
    {
        "name": "get_pipeline_report",
        "description": "Generate a pipeline analysis report",
        "input_schema": {
            "type": "object",
            "properties": {
                "date_range": {
                    "type": "string",
                    "enum": ["7d", "30d", "90d", "ytd"],
                    "description": "Date range for the report"
                }
            },
            "required": []
        }
    },
    # Analytical Query Tools
    {
        "name": "query_pipeline_analysis",
        "description": "Get detailed pipeline analysis by stage including lead counts, values, and age",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "query_lead_source_performance",
        "description": "Analyze lead source performance including close rates and revenue",
        "input_schema": {
            "type": "object",
            "properties": {
                "date_range_days": {
                    "type": "integer",
                    "description": "Number of days to analyze (default 90)",
                    "default": 90
                }
            },
            "required": []
        }
    },
    {
        "name": "query_conversion_funnel",
        "description": "Analyze conversion rates through pipeline stages",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "query_loan_type_performance",
        "description": "Get performance breakdown by loan type including win rates",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "query_monthly_trends",
        "description": "Get monthly trends for leads and closings",
        "input_schema": {
            "type": "object",
            "properties": {
                "months": {
                    "type": "integer",
                    "description": "Number of months to analyze (default 6)",
                    "default": 6
                }
            },
            "required": []
        }
    },
    {
        "name": "query_stale_leads",
        "description": "Find stale leads that need attention",
        "input_schema": {
            "type": "object",
            "properties": {
                "stale_days": {
                    "type": "integer",
                    "description": "Days since created to consider stale (default 14)",
                    "default": 14
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results to return (default 20)",
                    "default": 20
                }
            },
            "required": []
        }
    },
    {
        "name": "query_high_value_opportunities",
        "description": "Find high-value leads in pipeline",
        "input_schema": {
            "type": "object",
            "properties": {
                "min_amount": {
                    "type": "integer",
                    "description": "Minimum loan amount to include (default 500000)",
                    "default": 500000
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results to return (default 20)",
                    "default": 20
                }
            },
            "required": []
        }
    },
    {
        "name": "query_activity_summary",
        "description": "Get summary of recent activities by type",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of days to analyze (default 30)",
                    "default": 30
                }
            },
            "required": []
        }
    },
    # Market Intelligence Tools
    {
        "name": "get_market_intelligence",
        "description": "Get current market conditions including treasury yields, mortgage rates, MBS prices, and rate lock recommendations",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_rate_lock_recommendation",
        "description": "Get specific rate lock recommendation based on lock period and current market conditions",
        "input_schema": {
            "type": "object",
            "properties": {
                "lock_days": {
                    "type": "integer",
                    "description": "Number of days for rate lock (15, 30, 45, 60)",
                    "default": 30
                },
                "loan_amount": {
                    "type": "number",
                    "description": "Loan amount for context"
                }
            },
            "required": []
        }
    },
    # Customer Lifecycle & Value
    {
        "name": "query_client_lifetime_value",
        "description": "Calculate client lifetime value including total loan volume, referrals, and estimated revenue per client",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_refi_candidates",
        "description": "Identify clients likely to refinance based on rate environment, loan age, and current interest rates",
        "input_schema": {
            "type": "object",
            "properties": {
                "months_since_closing": {"type": "integer", "default": 12, "description": "Minimum months since closing"}
            },
            "required": []
        }
    },
    {
        "name": "query_client_retention_rate",
        "description": "Calculate percentage of clients who return for additional loans",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_ghost_clients",
        "description": "Find past clients with no recent contact who need re-engagement",
        "input_schema": {
            "type": "object",
            "properties": {
                "days_since_contact": {"type": "integer", "default": 180, "description": "Days since last contact"}
            },
            "required": []
        }
    },
    {
        "name": "query_communication_effectiveness",
        "description": "Analyze response rates by time of day and communication channel",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_referral_likelihood",
        "description": "Identify clients most likely to provide referrals based on satisfaction scores",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    # Operational Efficiency
    {
        "name": "query_process_bottlenecks",
        "description": "Identify where loans get stuck in the pipeline and average time in each stage",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_sla_compliance",
        "description": "Calculate on-time performance metrics by stage",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_document_turnaround",
        "description": "Calculate time from document request to receipt",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_pull_through_rate",
        "description": "Calculate percentage of leads that actually close by source",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_capacity_utilization",
        "description": "Calculate active loans vs optimal capacity for loan officers",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_cycle_time_by_loan_type",
        "description": "Calculate average time to close by loan product type",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    # Risk & Early Warning
    {
        "name": "query_at_risk_loans",
        "description": "Predict loans at risk of falling out based on patterns like stall time and risk scores",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_expiring_rate_locks",
        "description": "Find rate locks expiring soon with urgency levels",
        "input_schema": {
            "type": "object",
            "properties": {
                "days_threshold": {"type": "integer", "default": 15, "description": "Days until expiration"}
            },
            "required": []
        }
    },
    {
        "name": "query_credit_quality_trend",
        "description": "Track average FICO scores and DTI trends over time",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_compliance_risk_score",
        "description": "Calculate compliance risk based on violations and missing disclosures",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_poor_quality_sources",
        "description": "Identify referral partners with low conversion and high fallout rates",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    # Marketing & Growth
    {
        "name": "query_cost_per_acquisition",
        "description": "Calculate cost per acquisition by marketing channel",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_marketing_roi",
        "description": "Track marketing campaign ROI from ad to closed loan",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_seasonal_trends",
        "description": "Identify month-over-month patterns for forecasting",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_competitive_analysis",
        "description": "Analyze lost deals to understand competitive positioning",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_market_share_by_zip",
        "description": "Calculate local market dominance by ZIP code",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    # Financial Forecasting
    {
        "name": "query_revenue_forecast_90d",
        "description": "Forecast 90-day revenue based on current pipeline and conversion rates",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_pipeline_value_at_risk",
        "description": "Calculate loans likely to cancel or fall through",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_margin_trend",
        "description": "Analyze interest rate spread trends over time",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_breakeven_analysis",
        "description": "Calculate loans needed to cover compensation and overhead",
        "input_schema": {
            "type": "object",
            "properties": {
                "monthly_overhead": {"type": "number", "default": 15000},
                "avg_commission": {"type": "number", "default": 3000}
            },
            "required": []
        }
    },
    # Quality & Performance
    {
        "name": "query_processor_quality_metrics",
        "description": "Analyze error rates and quality metrics by processor",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_loan_delay_root_causes",
        "description": "Identify what causes most loan delays",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_documentation_completeness",
        "description": "Calculate missing documents by loan stage",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_customer_satisfaction_by_lo",
        "description": "Get NPS and satisfaction scores by loan officer",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    # Partnership Intelligence
    {
        "name": "query_top_realtor_partners",
        "description": "Identify top producing realtor partners by volume and close rate",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_referral_partner_response_time",
        "description": "Measure how fast referral partners engage leads",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_vendor_performance",
        "description": "Compare appraisal, title, and credit vendor performance",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    # Strategic Planning
    {
        "name": "query_hiring_recommendation",
        "description": "Analyze if hiring another team member makes financial sense based on capacity",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_product_profitability",
        "description": "Calculate margin and time analysis by loan type to identify most profitable products",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_optimal_product_mix",
        "description": "Recommend optimal product mix for revenue maximization",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_cost_cutting_opportunities",
        "description": "Identify expense efficiency opportunities",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_employee_productivity_benchmark",
        "description": "Compare performance to industry standards and benchmarks",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    # ========== TACTICAL QUERIES - Day-to-Day Operations (99 queries) ==========
    # Daily Operations & Priorities
    {
        "name": "query_daily_focus_priorities",
        "description": "Get AI-prioritized action items based on urgency and revenue impact",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_hot_list",
        "description": "Get loans needing immediate attention (closing soon, stalled, high risk)",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_callback_list",
        "description": "Get missed calls, unreturned voicemails, and pending responses",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_overdue_tasks",
        "description": "Get past due items sorted by priority",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_weekly_calendar",
        "description": "Get upcoming closings, appointments, and deadlines this week",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_critical_issues",
        "description": "Get critical issues flagged by AI (angry clients, compliance, high risk)",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    # Client Communication
    {
        "name": "query_untouched_clients",
        "description": "Get clients not contacted in X days",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "default": 7, "description": "Days since last contact"}
            },
            "required": []
        }
    },
    {
        "name": "query_waiting_on_me",
        "description": "Get loans where ball is in your court - action needed from you",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_followups_due",
        "description": "Get scheduled follow-ups that are due or overdue",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_email_openers_no_response",
        "description": "Get leads who opened emails but haven't responded",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_my_response_time",
        "description": "Get your average response time to leads and clients",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_potentially_upset_clients",
        "description": "Get clients who may be frustrated (low sentiment, long delays)",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_video_update_candidates",
        "description": "Get loans that would benefit from a video update message",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    # Loan Status & Milestones
    {
        "name": "query_closing_this_period",
        "description": "Get loans closing this week or month",
        "input_schema": {
            "type": "object",
            "properties": {
                "period": {"type": "string", "enum": ["week", "month"], "default": "week", "description": "Time period"}
            },
            "required": []
        }
    },
    {
        "name": "query_outstanding_conditions",
        "description": "Get all outstanding underwriting conditions that need clearing",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_needs_appraisal",
        "description": "Get loans that need appraisal ordered or are waiting for results",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_waiting_underwriting",
        "description": "Get loans submitted to underwriting waiting for decision",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_needs_insurance_title",
        "description": "Get loans waiting on insurance or title work",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_clear_to_close_pipeline",
        "description": "Get loans that are clear to close - ready for final review",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_loans_in_final_review",
        "description": "Get loans in final QC review before closing",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_milestones_this_week",
        "description": "Get key milestones coming up this week (locks, closings, apps)",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    # Income & Commission
    {
        "name": "query_my_commission_this_month",
        "description": "Get commission from funded loans this month",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_projected_income",
        "description": "Get projected income from current pipeline",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_funded_this_week",
        "description": "Get loans that funded this week with commission details",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_goal_progress",
        "description": "Get progress toward monthly/quarterly goals",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_ytd_income",
        "description": "Get year-to-date income, volume, and unit counts",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_pipeline_commission_value",
        "description": "Get total potential commission from active pipeline",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_highest_commission_loans",
        "description": "Get your highest commission loans in pipeline",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    # Personal Performance
    {
        "name": "query_am_i_hitting_numbers",
        "description": "Check if you're on track for monthly goals",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_my_conversion_rate",
        "description": "Get your lead-to-close conversion rate",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_compare_to_last_period",
        "description": "Compare current month to last month performance",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_my_avg_time_to_close",
        "description": "Get your average time from application to funding",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_personal_best_month",
        "description": "Get your best month ever for volume and units",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_am_i_improving",
        "description": "Analyze if your key metrics are trending up or down",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_closing_ratio_by_type",
        "description": "Get your closing ratio broken down by loan type",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    # Referral Partner Management
    {
        "name": "query_partners_for_lunch",
        "description": "Get referral partners you haven't taken to lunch recently",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_top_referral_source_quarter",
        "description": "Get top producing referral partners this quarter",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_dormant_partners",
        "description": "Get partners who used to send business but haven't lately",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_partners_need_followup",
        "description": "Get partners you need to follow up with",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_relationships_need_nurture",
        "description": "Get key relationships that need attention",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_partners_shopping_competitors",
        "description": "Get partners who may be working with competitors",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_partners_sent_bad_leads",
        "description": "Get partners sending low-quality leads",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    # Borrower Qualification
    {
        "name": "query_can_borrower_qualify",
        "description": "Check if a specific borrower can qualify for a loan",
        "input_schema": {
            "type": "object",
            "properties": {
                "lead_id": {"type": "integer", "description": "Lead ID to check"}
            },
            "required": ["lead_id"]
        }
    },
    {
        "name": "query_max_purchase_price",
        "description": "Calculate max purchase price a borrower can afford",
        "input_schema": {
            "type": "object",
            "properties": {
                "lead_id": {"type": "integer", "description": "Lead ID"}
            },
            "required": ["lead_id"]
        }
    },
    {
        "name": "query_eligible_loan_programs",
        "description": "Get eligible loan programs for a borrower",
        "input_schema": {
            "type": "object",
            "properties": {
                "lead_id": {"type": "integer", "description": "Lead ID"}
            },
            "required": ["lead_id"]
        }
    },
    {
        "name": "query_qualification_gaps",
        "description": "Identify what's preventing qualification",
        "input_schema": {
            "type": "object",
            "properties": {
                "lead_id": {"type": "integer", "description": "Lead ID"}
            },
            "required": ["lead_id"]
        }
    },
    {
        "name": "query_buy_now_or_wait",
        "description": "Advise if borrower should buy now or wait",
        "input_schema": {
            "type": "object",
            "properties": {
                "lead_id": {"type": "integer", "description": "Lead ID"}
            },
            "required": ["lead_id"]
        }
    },
    {
        "name": "query_afford_more_house",
        "description": "Show options for borrower to afford more house",
        "input_schema": {
            "type": "object",
            "properties": {
                "lead_id": {"type": "integer", "description": "Lead ID"}
            },
            "required": ["lead_id"]
        }
    },
    {
        "name": "query_required_documentation",
        "description": "Get list of required documents for a loan",
        "input_schema": {
            "type": "object",
            "properties": {
                "loan_id": {"type": "integer", "description": "Loan ID"}
            },
            "required": ["loan_id"]
        }
    },
    {
        "name": "query_dti_analysis",
        "description": "Analyze debt-to-income ratio and payoff strategies",
        "input_schema": {
            "type": "object",
            "properties": {
                "lead_id": {"type": "integer", "description": "Lead ID"}
            },
            "required": ["lead_id"]
        }
    },
    # Time Management
    {
        "name": "query_time_spent_analysis",
        "description": "Analyze where you're spending your time",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_revenue_per_activity",
        "description": "Calculate revenue generated per activity type",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_should_delegate",
        "description": "Identify low-value tasks you should delegate",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_task_balance_analysis",
        "description": "Analyze balance between sales vs admin tasks",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_productive_windows",
        "description": "Identify your most productive times of day",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_time_per_loan",
        "description": "Calculate average time spent per loan file",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    # Pipeline Health
    {
        "name": "query_pipeline_health_check",
        "description": "Check if your pipeline is healthy (funnel shape analysis)",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_lead_flow_adequate",
        "description": "Check if you have enough new leads coming in",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_pipeline_velocity",
        "description": "Calculate how fast loans move through your pipeline",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_stage_concentration",
        "description": "Identify if too many loans are stuck in one stage",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_pipeline_coverage_ratio",
        "description": "Calculate pipeline value vs monthly goal coverage",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_leads_needed_for_goal",
        "description": "Calculate how many more leads needed to hit goal",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    # Action Items
    {
        "name": "query_most_urgent_now",
        "description": "Get the single most urgent thing to do right now",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_highest_impact_actions",
        "description": "Get actions that will have biggest impact on revenue",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_falling_through_cracks",
        "description": "Get tasks or loans that are being neglected",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_productive_downtime",
        "description": "Get suggestions for productive tasks during slow periods",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_quick_wins",
        "description": "Get easy tasks that can be completed quickly",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    # Scenario Analysis
    {
        "name": "query_rate_drop_impact",
        "description": "Model impact of a rate drop on refi pipeline",
        "input_schema": {
            "type": "object",
            "properties": {
                "rate_drop": {"type": "number", "description": "Rate drop in percentage points"}
            },
            "required": ["rate_drop"]
        }
    },
    {
        "name": "query_portfolio_refi_potential",
        "description": "Calculate refinance potential in your closed loan portfolio",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_referral_source_risk",
        "description": "Model impact if top referral source goes away",
        "input_schema": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "Referral source name"}
            },
            "required": []
        }
    },
    {
        "name": "query_processor_hire_roi",
        "description": "Calculate ROI of hiring another processor",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_product_focus_impact",
        "description": "Model impact of focusing on specific loan products",
        "input_schema": {
            "type": "object",
            "properties": {
                "product": {"type": "string", "description": "Product to focus on"}
            },
            "required": []
        }
    },
    {
        "name": "query_vacation_feasibility",
        "description": "Check if you can take vacation without impacting closings",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "Vacation start date"},
                "end_date": {"type": "string", "description": "Vacation end date"}
            },
            "required": []
        }
    },
    # Client Deep Dives
    {
        "name": "query_client_360_view",
        "description": "Get complete 360-degree view of a client relationship",
        "input_schema": {
            "type": "object",
            "properties": {
                "lead_id": {"type": "integer", "description": "Lead ID"}
            },
            "required": ["lead_id"]
        }
    },
    {
        "name": "query_loan_story",
        "description": "Get complete timeline and story of a loan file",
        "input_schema": {
            "type": "object",
            "properties": {
                "loan_id": {"type": "integer", "description": "Loan ID"}
            },
            "required": ["loan_id"]
        }
    },
    {
        "name": "query_loan_delay_reason",
        "description": "Analyze why a specific loan is delayed",
        "input_schema": {
            "type": "object",
            "properties": {
                "loan_id": {"type": "integer", "description": "Loan ID"}
            },
            "required": ["loan_id"]
        }
    },
    {
        "name": "query_file_risk_level",
        "description": "Assess risk level and fallout probability for a loan",
        "input_schema": {
            "type": "object",
            "properties": {
                "loan_id": {"type": "integer", "description": "Loan ID"}
            },
            "required": ["loan_id"]
        }
    },
    {
        "name": "query_client_needs_from_me",
        "description": "Identify what a specific client needs from you right now",
        "input_schema": {
            "type": "object",
            "properties": {
                "lead_id": {"type": "integer", "description": "Lead ID"}
            },
            "required": ["lead_id"]
        }
    },
    {
        "name": "query_client_history",
        "description": "Get full interaction history with a client",
        "input_schema": {
            "type": "object",
            "properties": {
                "lead_id": {"type": "integer", "description": "Lead ID"}
            },
            "required": ["lead_id"]
        }
    },
    # Market Intelligence
    {
        "name": "query_competitor_rates",
        "description": "Get current competitor rate comparison",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_losing_on_rate",
        "description": "Check if you're losing deals due to rate",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_why_losing_to_competitors",
        "description": "Analyze why you're losing to competitors",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_my_value_prop",
        "description": "Get your unique value proposition vs competitors",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    # Compliance & Risk
    {
        "name": "query_compliance_red_flags",
        "description": "Get loans with potential compliance issues",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_overdue_disclosures",
        "description": "Get loans with overdue TRID disclosures",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_loans_might_not_close",
        "description": "Get loans at high risk of not closing",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_audit_risk_assessment",
        "description": "Get overall audit risk assessment for your files",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_fair_lending_concerns",
        "description": "Check for fair lending concerns in your pipeline",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    # Relationship Maintenance
    {
        "name": "query_weekly_outreach_list",
        "description": "Get prioritized list of people to reach out to this week",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_loan_anniversaries",
        "description": "Get clients with upcoming loan anniversaries for check-ins",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_past_client_checkins",
        "description": "Get past clients due for periodic check-ins",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_upcoming_celebrations",
        "description": "Get upcoming birthdays, home purchase anniversaries to celebrate",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_gratitude_followups",
        "description": "Get clients you should send thank you notes to",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_referral_ask_opportunities",
        "description": "Get satisfied clients you haven't asked for referrals yet",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    # Learning & Improvement
    {
        "name": "query_my_weaknesses",
        "description": "Identify areas where you're underperforming",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_success_patterns",
        "description": "Analyze what leads to your fastest closings and best outcomes",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_repeated_mistakes",
        "description": "Identify recurring errors or issues in your process",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_close_faster_tips",
        "description": "Get personalized tips on how to close loans faster",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_skill_gaps",
        "description": "Identify skills you should develop or training needed",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    # ========== PROCESSOR QUERIES - Day-to-Day Processor Operations (105 queries) ==========
    # Daily Operations & Workload Management
    {
        "name": "query_processor_workload_today",
        "description": "Get processor's workload today - files assigned with priority order",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_deadlines_today",
        "description": "Get deadlines due today for processor's files",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_priority_queue",
        "description": "Get processor's files prioritized by closing date and urgency",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_current_capacity",
        "description": "Get processor's current workload capacity metrics",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_files_by_loan_officer",
        "description": "Get files grouped by loan officer for a processor",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_weekly_calendar",
        "description": "Get processor's weekly calendar with key deadlines",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_overdue_tasks",
        "description": "Get processor's overdue tasks and action items",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_file_list",
        "description": "Get complete list of processor's active files",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    # Document Management
    {
        "name": "query_processor_missing_documents",
        "description": "Get documents missing across processor's files",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_unresponsive_borrowers_docs",
        "description": "Get borrowers not responding to document requests",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_documents_uploaded_today",
        "description": "Get documents uploaded today requiring review",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_complete_documentation",
        "description": "Get files with complete documentation ready to submit",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_overdue_doc_requests",
        "description": "Get overdue document requests from borrowers",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_loan_stips",
        "description": "Get stipulations needed for a specific loan",
        "input_schema": {
            "type": "object",
            "properties": {
                "loan_id": {"type": "integer", "description": "Loan ID"}
            },
            "required": ["loan_id"]
        }
    },
    {
        "name": "query_processor_initial_disclosures_needed",
        "description": "Get files needing initial disclosures",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_pending_verifications",
        "description": "Get pending VOE/VOI/VOR verifications",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_credit_supplement_needed",
        "description": "Get files needing credit supplements or explanations",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_tax_return_requests",
        "description": "Get outstanding tax return requests",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_incomplete_income_docs",
        "description": "Get files with incomplete income documentation",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_expired_documents",
        "description": "Get documents that have expired and need renewal",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    # Third-Party Services & Vendors
    {
        "name": "query_processor_appraisals_to_order",
        "description": "Get files needing appraisals ordered",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_appraisals_in_progress",
        "description": "Get appraisals currently in progress",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_overdue_appraisals",
        "description": "Get overdue appraisals past expected completion date",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_appraisal_issues",
        "description": "Get files with appraisal problems or low values",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_title_work_pending",
        "description": "Get files waiting on title work",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_title_commitments_review",
        "description": "Get title commitments received needing review",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_hoa_docs_pending",
        "description": "Get files waiting on HOA documents",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_vendor_turnaround_times",
        "description": "Get vendor performance and turnaround times",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_inspections_scheduled",
        "description": "Get scheduled home inspections",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_insurance_needed",
        "description": "Get files needing homeowners insurance binders",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    # Underwriting Coordination
    {
        "name": "query_processor_ready_for_underwriting",
        "description": "Get files ready to submit to underwriting",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_files_with_underwriter",
        "description": "Get files currently with underwriter",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_conditions_received_today",
        "description": "Get underwriting conditions received today",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_all_outstanding_conditions",
        "description": "Get all outstanding underwriting conditions across files",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_cleared_conditions",
        "description": "Get conditions cleared and ready to resubmit",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_suspended_files",
        "description": "Get files suspended by underwriting",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_initial_approvals",
        "description": "Get files that received initial approval",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_clear_to_close_files",
        "description": "Get files that are clear to close",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_high_risk_underwriting",
        "description": "Get files with high underwriting risk",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_next_uw_call",
        "description": "Get topics for next underwriter call",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    # Timeline & Rate Lock Management
    {
        "name": "query_processor_closing_schedule",
        "description": "Get upcoming closing schedule",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_at_risk_closings",
        "description": "Get closings at risk of missing target date",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_expiring_rate_locks",
        "description": "Get rate locks expiring soon",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_tight_timeline_files",
        "description": "Get files with tight timelines",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_disclosures_due",
        "description": "Get disclosures due soon per TRID timing",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_delayed_files",
        "description": "Get files running behind schedule",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_closing_success_rate",
        "description": "Get processor's on-time closing success rate",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_avg_days_to_close",
        "description": "Get processor's average days from app to closing",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    # Quality Control & Compliance
    {
        "name": "query_processor_files_needing_qc",
        "description": "Get files needing quality control review",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_compliance_red_flags",
        "description": "Get files with compliance red flags",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_trid_violations",
        "description": "Get potential TRID timing violations",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_missing_disclosures",
        "description": "Get files with missing required disclosures",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_data_errors",
        "description": "Get files with data entry errors or mismatches",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_aus_rerun_needed",
        "description": "Get files needing AUS rerun after data changes",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_appraisal_issues_qc",
        "description": "Get appraisal quality control issues",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_credit_issues_qc",
        "description": "Get credit report quality control issues",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_audit_ready",
        "description": "Check if files are audit-ready",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    # Borrower Communication
    {
        "name": "query_processor_unresponsive_borrowers",
        "description": "Get unresponsive borrowers needing follow-up",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_borrowers_to_call_today",
        "description": "Get borrowers processor needs to call today",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_frustrated_borrowers",
        "description": "Get potentially frustrated borrowers",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_borrower_response_times",
        "description": "Get borrower responsiveness metrics",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_borrowers_need_updates",
        "description": "Get borrowers needing status updates",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_borrower_meetings_needed",
        "description": "Get files needing borrower meetings or calls",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_borrower_satisfaction",
        "description": "Get borrower satisfaction scores for processor's files",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    # Loan Officer Coordination
    {
        "name": "query_processor_lo_action_items",
        "description": "Get action items waiting on loan officers",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_los_blocking_files",
        "description": "Get loan officers blocking file progress",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_lo_response_times",
        "description": "Get loan officer response time metrics",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_my_loan_officers",
        "description": "Get loan officers processor works with and file counts",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_files_need_lo_approval",
        "description": "Get files needing loan officer approval or review",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_problem_files_by_lo",
        "description": "Get problem files grouped by loan officer",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_los_with_most_conditions",
        "description": "Get loan officers with most underwriting conditions",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    # File Status & Progress Tracking
    {
        "name": "query_processor_files_by_stage",
        "description": "Get files grouped by loan stage",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_files_moved_today",
        "description": "Get files that advanced stages today",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_stalled_files",
        "description": "Get files stuck in same stage too long",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_file_aging_report",
        "description": "Get file aging report by days in process",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_file_velocity",
        "description": "Get average file velocity through stages",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_files_at_risk_fallout",
        "description": "Get files at risk of falling out",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_funnel_health",
        "description": "Get processor's funnel health metrics",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_files_closed_this_week",
        "description": "Get files closed this week",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    # Problem Resolution
    {
        "name": "query_processor_all_file_issues",
        "description": "Get all open issues across processor's files",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_income_calc_problems",
        "description": "Get files with income calculation issues",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_credit_disputes",
        "description": "Get files with credit disputes in progress",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_appraisal_gaps",
        "description": "Get files with appraisal shortfalls",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_title_issues",
        "description": "Get files with title problems",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_manual_underwriting_files",
        "description": "Get files requiring manual underwriting",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_eligibility_issues",
        "description": "Get files with eligibility or guideline issues",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_whats_blocking_files",
        "description": "Get summary of what's blocking each file",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    # Performance & Analytics
    {
        "name": "query_processor_closing_ratio",
        "description": "Get processor's closing ratio (files closed vs started)",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_avg_processing_time",
        "description": "Get average processing time by loan type",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_peer_comparison",
        "description": "Compare processor's metrics to peer averages",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_condition_clear_rate",
        "description": "Get condition clearance rate and turnaround time",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_error_rate",
        "description": "Get processor's error and resubmission rate",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_fastest_loan_types",
        "description": "Get processor's fastest loan types to close",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_slowest_files",
        "description": "Get processor's slowest files currently in pipeline",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    # Capacity & Workload Planning
    {
        "name": "query_processor_at_capacity_check",
        "description": "Check if processor is at capacity",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_incoming_files",
        "description": "Get new files coming to processor soon",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_can_take_another",
        "description": "Check if processor can take another file",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_workload_trend",
        "description": "Get processor's workload trend over time",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_file_distribution",
        "description": "Get file distribution across all processors",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    # Reporting & Insights
    {
        "name": "query_processor_weekly_summary",
        "description": "Get processor's weekly performance summary",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_weekly_wins",
        "description": "Get files successfully closed this week",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_time_allocation",
        "description": "Get time allocation analysis for processor",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_biggest_bottleneck",
        "description": "Identify processor's biggest bottleneck",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_common_conditions",
        "description": "Get most common underwriting conditions",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "query_processor_lo_quality_ranking",
        "description": "Rank loan officers by file quality",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    # Pre-Approval Letter Tool
    {
        "name": "send_pre_approval_letter",
        "description": "Generate and send a pre-approval letter for a lead/borrower. Use this when the user asks to send, create, or generate a pre-approval letter. If any required fields are missing, ask follow-up questions to gather: borrower name, property address (or 'TBD'), loan amount, loan type, and recipient email.",
        "input_schema": {
            "type": "object",
            "properties": {
                "lead_id": {
                    "type": "integer",
                    "description": "The lead's ID (can look up by name if not provided)"
                },
                "borrower_names": {
                    "type": "string",
                    "description": "Full name(s) of the borrower(s)"
                },
                "property_address": {
                    "type": "string",
                    "description": "Property address or 'To Be Determined'"
                },
                "loan_amount": {
                    "type": "number",
                    "description": "Approved loan amount"
                },
                "loan_type": {
                    "type": "string",
                    "enum": ["Conventional", "FHA", "VA", "USDA", "Jumbo"],
                    "description": "Type of loan program"
                },
                "recipient_email": {
                    "type": "string",
                    "description": "Email address to send the pre-approval letter to"
                },
                "interest_rate": {
                    "type": "number",
                    "description": "Optional interest rate (will use current market rate if not provided)"
                },
                "expiration_days": {
                    "type": "integer",
                    "description": "Days until letter expires (default 90)"
                }
            },
            "required": ["borrower_names", "loan_amount", "loan_type", "recipient_email"]
        }
    }
]


# ============================================================================
# Validation Pipeline
# ============================================================================

class ValidationResult:
    def __init__(self, is_valid: bool, reason: str = None):
        self.is_valid = is_valid
        self.reason = reason


class ActionValidator:
    """Validate AI actions before execution"""

    @staticmethod
    def validate_action(action: Dict[str, Any], user_id: int, db: Session) -> ValidationResult:
        """Validate an action is safe to execute"""
        action_name = action.get("name", "")
        parameters = action.get("parameters", {})

        # Check 1: Known action type
        valid_actions = [
            "get_daily_summary", "search_crm", "update_lead_status",
            "create_task", "send_email_campaign", "get_pipeline_report",
            # Original analytical query tools
            "query_pipeline_analysis", "query_lead_source_performance",
            "query_conversion_funnel", "query_loan_type_performance",
            "query_monthly_trends", "query_stale_leads",
            "query_high_value_opportunities", "query_activity_summary",
            "get_market_intelligence", "get_rate_lock_recommendation",
            # Customer Lifecycle & Value
            "query_client_lifetime_value", "query_refi_candidates",
            "query_client_retention_rate", "query_ghost_clients",
            "query_communication_effectiveness", "query_referral_likelihood",
            # Operational Efficiency
            "query_process_bottlenecks", "query_sla_compliance",
            "query_document_turnaround", "query_pull_through_rate",
            "query_capacity_utilization", "query_cycle_time_by_loan_type",
            # Risk & Early Warning
            "query_at_risk_loans", "query_expiring_rate_locks",
            "query_credit_quality_trend", "query_compliance_risk_score",
            "query_poor_quality_sources",
            # Marketing & Growth
            "query_cost_per_acquisition", "query_marketing_roi",
            "query_seasonal_trends", "query_competitive_analysis",
            "query_market_share_by_zip",
            # Financial Forecasting
            "query_revenue_forecast_90d", "query_pipeline_value_at_risk",
            "query_margin_trend", "query_breakeven_analysis",
            # Quality & Performance
            "query_processor_quality_metrics", "query_loan_delay_root_causes",
            "query_documentation_completeness", "query_customer_satisfaction_by_lo",
            # Partnership Intelligence
            "query_top_realtor_partners", "query_referral_partner_response_time",
            "query_vendor_performance",
            # Strategic Planning
            "query_hiring_recommendation", "query_product_profitability",
            "query_optimal_product_mix", "query_cost_cutting_opportunities",
            "query_employee_productivity_benchmark",
            # ========== TACTICAL QUERIES - Day-to-Day Operations (99 queries) ==========
            # Daily Operations & Priorities
            "query_daily_focus_priorities", "query_hot_list", "query_callback_list",
            "query_overdue_tasks", "query_weekly_calendar", "query_critical_issues",
            # Client Communication
            "query_untouched_clients", "query_waiting_on_me", "query_followups_due",
            "query_email_openers_no_response", "query_my_response_time",
            "query_potentially_upset_clients", "query_video_update_candidates",
            # Loan Status & Milestones
            "query_closing_this_period", "query_outstanding_conditions",
            "query_needs_appraisal", "query_waiting_underwriting",
            "query_needs_insurance_title", "query_clear_to_close_pipeline",
            "query_loans_in_final_review", "query_milestones_this_week",
            # Income & Commission
            "query_my_commission_this_month", "query_projected_income",
            "query_funded_this_week", "query_goal_progress", "query_ytd_income",
            "query_pipeline_commission_value", "query_highest_commission_loans",
            # Personal Performance
            "query_am_i_hitting_numbers", "query_my_conversion_rate",
            "query_compare_to_last_period", "query_my_avg_time_to_close",
            "query_personal_best_month", "query_am_i_improving",
            "query_closing_ratio_by_type",
            # Referral Partner Management
            "query_partners_for_lunch", "query_top_referral_source_quarter",
            "query_dormant_partners", "query_partners_need_followup",
            "query_relationships_need_nurture", "query_partners_shopping_competitors",
            "query_partners_sent_bad_leads",
            # Borrower Qualification
            "query_can_borrower_qualify", "query_max_purchase_price",
            "query_eligible_loan_programs", "query_qualification_gaps",
            "query_buy_now_or_wait", "query_afford_more_house",
            "query_required_documentation", "query_dti_analysis",
            # Time Management
            "query_time_spent_analysis", "query_revenue_per_activity",
            "query_should_delegate", "query_task_balance_analysis",
            "query_productive_windows", "query_time_per_loan",
            # Pipeline Health
            "query_pipeline_health_check", "query_lead_flow_adequate",
            "query_pipeline_velocity", "query_stage_concentration",
            "query_pipeline_coverage_ratio", "query_leads_needed_for_goal",
            # Action Items
            "query_most_urgent_now", "query_highest_impact_actions",
            "query_falling_through_cracks", "query_productive_downtime",
            "query_quick_wins",
            # Scenario Analysis
            "query_rate_drop_impact", "query_portfolio_refi_potential",
            "query_referral_source_risk", "query_processor_hire_roi",
            "query_product_focus_impact", "query_vacation_feasibility",
            # Client Deep Dives
            "query_client_360_view", "query_loan_story", "query_loan_delay_reason",
            "query_file_risk_level", "query_client_needs_from_me",
            "query_client_history",
            # Market Intelligence
            "query_competitor_rates", "query_losing_on_rate",
            "query_why_losing_to_competitors", "query_my_value_prop",
            # Compliance & Risk
            "query_compliance_red_flags", "query_overdue_disclosures",
            "query_loans_might_not_close", "query_audit_risk_assessment",
            "query_fair_lending_concerns",
            # Relationship Maintenance
            "query_weekly_outreach_list", "query_loan_anniversaries",
            "query_past_client_checkins", "query_upcoming_celebrations",
            "query_gratitude_followups", "query_referral_ask_opportunities",
            # Learning & Improvement
            "query_my_weaknesses", "query_success_patterns",
            "query_repeated_mistakes", "query_close_faster_tips",
            "query_skill_gaps",
            # ========== PROCESSOR QUERIES - Day-to-Day Processor Operations (105 queries) ==========
            # Daily Operations & Workload Management
            "query_processor_workload_today", "query_processor_deadlines_today",
            "query_processor_priority_queue", "query_processor_current_capacity",
            "query_processor_files_by_loan_officer", "query_processor_weekly_calendar",
            "query_processor_overdue_tasks", "query_processor_file_list",
            # Document Management
            "query_processor_missing_documents", "query_processor_unresponsive_borrowers_docs",
            "query_processor_documents_uploaded_today", "query_processor_complete_documentation",
            "query_processor_overdue_doc_requests", "query_processor_loan_stips",
            "query_processor_initial_disclosures_needed", "query_processor_pending_verifications",
            "query_processor_credit_supplement_needed", "query_processor_tax_return_requests",
            "query_processor_incomplete_income_docs", "query_processor_expired_documents",
            # Third-Party Services & Vendors
            "query_processor_appraisals_to_order", "query_processor_appraisals_in_progress",
            "query_processor_overdue_appraisals", "query_processor_appraisal_issues",
            "query_processor_title_work_pending", "query_processor_title_commitments_review",
            "query_processor_hoa_docs_pending", "query_processor_vendor_turnaround_times",
            "query_processor_inspections_scheduled", "query_processor_insurance_needed",
            # Underwriting Coordination
            "query_processor_ready_for_underwriting", "query_processor_files_with_underwriter",
            "query_processor_conditions_received_today", "query_processor_all_outstanding_conditions",
            "query_processor_cleared_conditions", "query_processor_suspended_files",
            "query_processor_initial_approvals", "query_processor_clear_to_close_files",
            "query_processor_high_risk_underwriting", "query_processor_next_uw_call",
            # Timeline & Rate Lock Management
            "query_processor_closing_schedule", "query_processor_at_risk_closings",
            "query_processor_expiring_rate_locks", "query_processor_tight_timeline_files",
            "query_processor_disclosures_due", "query_processor_delayed_files",
            "query_processor_closing_success_rate", "query_processor_avg_days_to_close",
            # Quality Control & Compliance
            "query_processor_files_needing_qc", "query_processor_compliance_red_flags",
            "query_processor_trid_violations", "query_processor_missing_disclosures",
            "query_processor_data_errors", "query_processor_aus_rerun_needed",
            "query_processor_appraisal_issues_qc", "query_processor_credit_issues_qc",
            "query_processor_audit_ready",
            # Borrower Communication
            "query_processor_unresponsive_borrowers", "query_processor_borrowers_to_call_today",
            "query_processor_frustrated_borrowers", "query_processor_borrower_response_times",
            "query_processor_borrowers_need_updates", "query_processor_borrower_meetings_needed",
            "query_processor_borrower_satisfaction",
            # Loan Officer Coordination
            "query_processor_lo_action_items", "query_processor_los_blocking_files",
            "query_processor_lo_response_times", "query_processor_my_loan_officers",
            "query_processor_files_need_lo_approval", "query_processor_problem_files_by_lo",
            "query_processor_los_with_most_conditions",
            # File Status & Progress Tracking
            "query_processor_files_by_stage", "query_processor_files_moved_today",
            "query_processor_stalled_files", "query_processor_file_aging_report",
            "query_processor_file_velocity", "query_processor_files_at_risk_fallout",
            "query_processor_funnel_health", "query_processor_files_closed_this_week",
            # Problem Resolution
            "query_processor_all_file_issues", "query_processor_income_calc_problems",
            "query_processor_credit_disputes", "query_processor_appraisal_gaps",
            "query_processor_title_issues", "query_processor_manual_underwriting_files",
            "query_processor_eligibility_issues", "query_processor_whats_blocking_files",
            # Performance & Analytics
            "query_processor_closing_ratio", "query_processor_avg_processing_time",
            "query_processor_peer_comparison", "query_processor_condition_clear_rate",
            "query_processor_error_rate", "query_processor_fastest_loan_types",
            "query_processor_slowest_files",
            # Capacity & Workload Planning
            "query_processor_at_capacity_check", "query_processor_incoming_files",
            "query_processor_can_take_another", "query_processor_workload_trend",
            "query_processor_file_distribution",
            # Reporting & Insights
            "query_processor_weekly_summary", "query_processor_weekly_wins",
            "query_processor_time_allocation", "query_processor_biggest_bottleneck",
            "query_processor_common_conditions", "query_processor_lo_quality_ranking"
        ]
        if action_name not in valid_actions:
            return ValidationResult(False, f"Unknown action: {action_name}")

        # Check 2: User owns the entity (for update operations)
        if action_name == "update_lead_status":
            lead_id = parameters.get("lead_id")
            if lead_id:
                main = get_main_module()
                Lead = main.Lead
                lead = db.query(Lead).filter(Lead.id == lead_id, Lead.owner_id == user_id).first()
                if not lead:
                    return ValidationResult(False, "Lead not found or not owned by user")

        # Check 3: Parameter validation
        if action_name == "create_task":
            due_date_str = parameters.get("due_date", "")
            try:
                due_date = datetime.fromisoformat(due_date_str) if due_date_str else None
                if due_date and due_date.date() < datetime.now().date():
                    return ValidationResult(False, "Cannot create tasks with past due dates")
            except ValueError:
                return ValidationResult(False, "Invalid date format")

        return ValidationResult(True)

    @staticmethod
    def pre_execution_check(action: Dict[str, Any], user_id: int, db: Session) -> ValidationResult:
        """Verify data exists before attempting action"""
        action_name = action.get("name", "")
        parameters = action.get("parameters", {})

        if action_name == "update_lead_status":
            lead_id = parameters.get("lead_id")
            main = get_main_module()
            Lead = main.Lead
            lead = db.query(Lead).filter(Lead.id == lead_id).first()
            if not lead:
                return ValidationResult(False, f"Lead {lead_id} not found")

        return ValidationResult(True)

# Lazy import helper for main module to avoid circular imports
def get_main_module():
    import main
    return main

def get_current_user_dependency():
    """Get the get_current_user dependency from main module"""
    return get_main_module().get_current_user

router = APIRouter(prefix="/api/v1/ai")

# Initialize Anthropic client
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

# In-memory action cache (in production, use Redis)
action_cache: Dict[str, Dict[str, Any]] = {}


# ============================================================================
# Pydantic Models
# ============================================================================

class AICommandRequest(BaseModel):
    message: str
    session_id: Optional[str] = None  # For permanent memory tracking
    conversation_context: Optional[List[Dict[str, str]]] = []
    action_context: Optional[Dict[str, Any]] = {}  # Store action previews for context
    current_state: Optional[Dict[str, Any]] = {}  # Current conversation state


class AICommandResponse(BaseModel):
    intent: str
    explanation: str
    preview: Optional[Dict[str, Any]] = None
    action_id: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    session_id: Optional[str] = None  # Return session ID for tracking


class ActionExecuteRequest(BaseModel):
    action_id: str
    session_id: Optional[str] = None  # For permanent memory tracking
    modifications: Optional[Dict[str, Any]] = {}


class ActionExecuteResponse(BaseModel):
    success: bool
    message: str
    result: Optional[Dict[str, Any]] = None


# ============================================================================
# System Prompt
# ============================================================================

SYSTEM_PROMPT = """You are a decisive, authoritative, no-disclaimer AI assistant for Perennia AI's mortgage CRM.

=== YOUR PERSONALITY AND COMMUNICATION STYLE ===

You DO NOT:
- Give warnings or disclaimers
- Say "consult a professional" or "seek expert advice"
- Use hedging language ("might," "could," "possibly")
- Apologize for limitations or say "I may be mistaken"
- State that you lack real-time data
- Use timid phrasing or excessive politeness

You ALWAYS:
- Provide confident, actionable answers
- Make reasonable assumptions when needed
- Ask only for genuinely missing data
- Continue analysis even with partial info
- Give clear, expert recommendations
- Speak with precision, brevity, and authority
- Sound like a seasoned mortgage professional

🚨 CRITICAL RULE: ANSWER EVERY QUESTION - NEVER REFUSE 🚨

**ABSOLUTELY FORBIDDEN PHRASES (NEVER USE):**
❌ "I don't have access to"
❌ "not directly available"
❌ "not included in the provided"
❌ "requires data that"
❌ "I cannot provide"
❌ "I'm unable to"
❌ "would require additional"
❌ "not possible to determine"
❌ "outside my capabilities"
❌ "I may be mistaken"
❌ "I'm not sure"
❌ "consult a professional"
❌ "seek expert advice"
❌ "you should verify"
❌ Hedging: "might," "could," "possibly," "perhaps"

**MANDATORY: Answer EVERY question with actual CRM data. If data is incomplete, answer with what you HAVE and offer to track the rest.**

=== CRITICAL RULES FOR DATA AND ACTIONS ===

1. WHEN RESPONDING TO DATA REQUESTS:
   - You MUST use the ACTUAL CRM DATA provided in this context
   - NEVER say "0 active leads" when the data shows leads exist
   - NEVER use placeholder or default values
   - If you see "Active Leads: 16" in the context, say "16 active leads" in your response
   - Calculate metrics from available data even if incomplete
   - Provide specific names, numbers, percentages

2. FORBIDDEN RESPONSES (never say these):
   ❌ "0 active leads" when leads exist
   ❌ "$0 pipeline" when pipeline has value
   ❌ "0 tasks" when tasks are listed
   ❌ Any response with placeholder zeros when real data is provided
   ❌ Any refusal or "I don't have access" statements

3. FOR DAILY_VIEW REQUESTS ("what do I need to do today"):
   - Look at the DAILY VIEW DATA section below
   - Use the EXACT numbers provided
   - List actual client names from the data
   - Mention specific tasks and follow-ups

4. EXAMPLE OF CORRECT RESPONSE:
   If data shows: Active Leads: 16, Pipeline: $2,845,000
   ✅ CORRECT: "You have 16 active leads with $2,845,000 in pipeline"
   ❌ WRONG: "You have 0 active leads with $0 in pipeline"

5. FOR REFERRAL PARTNER QUESTIONS:
   When user asks "who is my most profitable referral partner":
   - You MUST name the specific partner from the data
   - You MUST include revenue amount and deal count
   - NEVER say "Let me show you..." without showing actual data

6. FORBIDDEN GENERIC RESPONSES:
   ❌ "Let me show you your tasks and priorities..."
   ❌ "I'll look at your referral partner data..."
   ❌ "Here's an overview of your pipeline..."
   ❌ "Would you like me to..."
   ❌ "I can analyze..." or "I can provide..."
   ❌ "Based on your CRM data, I can..."
   ❌ "What I can analyze:" followed by a list
   ❌ "Which analysis would you like?"

   These are WRONG because they don't include actual data or ask for permission.

   ALWAYS include specific names, numbers, and amounts from the CRM DATA section.

7. BE ACTION-ORIENTED, NOT PERMISSION-SEEKING:
   ❌ WRONG: "Would you like me to run a pipeline analysis?"
   ✅ RIGHT: "Here's your pipeline analysis: [actual data]"

   ❌ WRONG: "I can analyze your conversion rates. Would you like that?"
   ✅ RIGHT: "Your conversion rate from New to Pre-Approved is 25%. Here are the bottlenecks..."

   ❌ WRONG: "What requires external systems: gain-on-sale margins..."
   ✅ RIGHT: Just analyze what you have. Don't explain what you can't do.

   NEVER list your capabilities or limitations. JUST DO THE ANALYSIS with the data you have.
   NEVER ask "which would be most valuable" - decide based on the data and deliver insights.

8. COACHING MODE BEHAVIOR:
   When in ANY coaching mode, you must:
   - Immediately dive into analysis with specific data
   - Name actual clients, amounts, and dates
   - Be direct and assertive
   - Give specific action items, not options
   - NEVER deflect or ask for clarification
   - If user asks about profitability, analyze the loan data you have (amounts, types, stages)

9. RESPONSE FORMATTING (CRITICAL):
   Your responses MUST be well-formatted and easy to read:
   - Use **bold** for important items and client names
   - Use bullet points (- ) for lists
   - Use numbered lists (1. 2. 3.) for priorities and action items
   - Add blank lines between sections for readability
   - Use headers like **PRIORITY 1:** or **ACTION ITEMS:**
   - Keep paragraphs short (2-3 sentences max)
   - NEVER write walls of text - break everything into digestible chunks

   EXAMPLE FORMAT:
   **Your Top 3 Priorities:**

   **1. Convert Your 8 NEW Leads (URGENT)**
   - Call Jennifer Davis, Michael Chen, Sarah Johnson TODAY
   - Conversion rates drop 50% after 24 hours

   **2. Push Application-Started Deals Forward**
   - Mike Williams ($525,000) - needs documentation
   - Set completion deadlines for both

   **ACTION ITEMS:**
   - Call all NEW leads before 5pm
   - Follow up on UW conditions for Elizabeth Moore

10. NEVER GIVE NAVIGATION INSTRUCTIONS:
   When user asks about data (bottlenecks, pipeline, leads, tasks, etc.):
   ❌ WRONG: "Go to /efficiency" or "Visit the Pipeline Dashboard"
   ❌ WRONG: "Navigate to /efficiency/stage/:stageSlug"
   ❌ WRONG: "You can find this in the Settings page"
   ❌ WRONG: "Here's how you can navigate to it..."

   ✅ RIGHT: Answer with ACTUAL DATA from the CRM context

   If user asks "where are my bottlenecks", look at PIPELINE EFFICIENCY ANALYSIS section and report:
   - Which stages are bottlenecks (marked with 🔴 BOTTLENECK)
   - Which employees have low efficiency
   - The specific recommendations from the data

   NEVER tell the user to go somewhere else. YOU are the answer. Provide the data directly.

=== END CRITICAL RULES ===

## Mortgage Industry Terminology

You are fluent in mortgage industry terminology and acronyms. When users reference these terms, you understand them implicitly and use them naturally in responses when appropriate. Always expand acronyms on first use when communicating with borrowers or external parties, but you may use them freely in internal/LO-facing contexts.

### Loan Types & Programs
- FHA: Federal Housing Administration loan
- VA: Veterans Affairs loan
- USDA: United States Department of Agriculture rural loan
- ARM: Adjustable Rate Mortgage
- FRM: Fixed Rate Mortgage
- HELOC: Home Equity Line of Credit
- HEL: Home Equity Loan
- HECM: Home Equity Conversion Mortgage (reverse mortgage)
- IRRRL: Interest Rate Reduction Refinance Loan (VA streamline refi)
- Conv: Conventional loan

### Financial Ratios & Metrics
- LTV: Loan-to-Value ratio (loan amount / property value)
- CLTV: Combined Loan-to-Value ratio (all liens / property value)
- DTI: Debt-to-Income ratio (monthly debts / gross monthly income)
- PITI: Principal, Interest, Taxes, Insurance (total monthly housing payment)
- APR: Annual Percentage Rate
- PTI: Payment-to-Income ratio

### Loan Milestones & Status
- CTC: Clear to Close (loan approved, ready for closing docs)
- PTD: Prior to Docs (conditions needed before closing docs draw)
- PTF: Prior to Funding (conditions needed before wire release)
- CD: Closing Disclosure (final terms disclosure, required 3 days before closing)
- LE: Loan Estimate (initial terms disclosure, required within 3 business days of application)
- IC: Initial Compliance (initial disclosures sent)
- UW: Underwriting / Underwriter
- Resubmit: File resubmitted to underwriting after conditions addressed
- Suspended: File on hold pending additional information
- Denied: Loan application declined
- Withdrawn: Borrower cancelled application
- Funded: Loan proceeds disbursed
- Docs Out: Closing documents sent to title/escrow

### Documentation & Verification
- AUS: Automated Underwriting System
- DU: Desktop Underwriter (Fannie Mae AUS)
- LP/LPA: Loan Product Advisor (Freddie Mac AUS)
- VOE: Verification of Employment
- VOD: Verification of Deposit
- VOR: Verification of Rent
- VOM: Verification of Mortgage
- POF: Proof of Funds
- POI: Proof of Income
- LOE/LOX: Letter of Explanation
- AVM: Automated Valuation Model
- BPO: Broker Price Opinion
- 1003: Uniform Residential Loan Application
- 4506-T/4506-C: IRS Tax Transcript Request Form
- W2: Wage and Tax Statement
- YTD: Year-to-Date
- P&L: Profit and Loss Statement
- K-1: Partner/Shareholder Income Schedule
- COE: Certificate of Eligibility (VA)

### Entities & Investors
- FNMA/Fannie: Federal National Mortgage Association
- FHLMC/Freddie: Federal Home Loan Mortgage Corporation
- GNMA/Ginnie: Government National Mortgage Association
- GSE: Government-Sponsored Enterprise
- HUD: Department of Housing and Urban Development
- CFPB: Consumer Financial Protection Bureau
- NMLS: Nationwide Multistate Licensing System

### Insurance
- PMI: Private Mortgage Insurance (conventional loans)
- MIP: Mortgage Insurance Premium (FHA loans)
- UFMIP: Upfront Mortgage Insurance Premium (FHA)
- LPMI: Lender-Paid Mortgage Insurance
- BPMI: Borrower-Paid Mortgage Insurance
- HOI: Homeowners Insurance
- HOA: Homeowners Association (dues)

### Property Types
- SFR: Single Family Residence
- MFR: Multi-Family Residence (2-4 units)
- PUD: Planned Unit Development
- Condo: Condominium
- TH: Townhouse
- Mfg/MH: Manufactured Home
- Modular: Modular Home
- O/O: Owner Occupied
- NOO: Non-Owner Occupied
- 2nd: Second Home
- Inv: Investment Property

### Closing & Settlement
- EMD: Earnest Money Deposit
- POC: Paid Outside Closing
- P&S/PSA: Purchase and Sale Agreement
- LLPA: Loan-Level Price Adjustment
- YSP: Yield Spread Premium
- SRP: Service Release Premium
- COF: Cost of Funds
- Escrow: Impound account for taxes/insurance

### Credit
- FICO: Fair Isaac Corporation credit score
- TU: TransUnion
- EQ: Equifax
- EX: Experian
- RCR: Rapid Credit Rescore
- TL: Tradeline (credit account)
- AU: Authorized User
- BK: Bankruptcy (Ch 7, Ch 13)
- FC: Foreclosure
- SS: Short Sale
- DIL: Deed in Lieu of Foreclosure
- NOD: Notice of Default

### Compliance & Regulations
- RESPA: Real Estate Settlement Procedures Act
- TILA: Truth in Lending Act
- TRID: TILA-RESPA Integrated Disclosure rules
- QM: Qualified Mortgage
- ATR: Ability to Repay
- HMDA: Home Mortgage Disclosure Act
- ECOA: Equal Credit Opportunity Act

### People & Roles
- LO: Loan Officer
- MLO: Mortgage Loan Originator
- LP: Loan Processor
- UW: Underwriter
- TC: Transaction Coordinator
- RE/REA: Real Estate Agent
- AE: Account Executive

### Common Shorthand
- Refi: Refinance
- Cash-out: Cash-out refinance
- R/T: Rate and Term refinance
- Purch: Purchase
- Pre-qual: Pre-qualification
- Pre-approval: Pre-approval letter
- DPA: Down Payment Assistance
- GUS: GUS (USDA's automated underwriting)

=== END TERMINOLOGY ===

## Communication Context Rules

Your communication style adapts based on the audience and context. Follow these rules for acronym and terminology usage:

### Audience Detection

Determine the audience from context clues:
- **Internal/LO-facing**: Messages to loan officers, processors, underwriters, or internal team members. Indicators include: internal notes, task assignments, Slack-style communications, CRM activity logs, pipeline discussions.
- **Borrower-facing**: Messages to borrowers, co-borrowers, or their representatives. Indicators include: email to borrower, SMS to client, welcome messages, status updates to applicants.
- **Partner-facing**: Messages to real estate agents, title companies, insurance agents, builders, or other third parties. Indicators include: referral partner communications, closing coordination, agent updates.

### Acronym Usage by Audience

**Internal/LO-facing communications:**
- Use acronyms freely without expansion
- Assume full industry knowledge
- Be concise and direct
- Example: "LTV is 78%, DTI at 42%. Waiting on VOE and 4506-C to get CTC."

**Borrower-facing communications:**
- Expand all acronyms on first use, then may abbreviate in parentheses for future reference
- Use plain language explanations alongside technical terms
- Avoid jargon when a simpler term exists
- Example: "Your Loan-to-Value ratio (LTV) is 78%, which means you won't need private mortgage insurance. We're waiting on verification of your employment before we can issue your Clear to Close."

**Partner-facing communications:**
- Expand acronyms on first use within a conversation thread
- Assume moderate industry knowledge but not lender-specific terminology
- Be professional but not overly simplified
- Example: "The loan is Clear to Close (CTC). We're targeting closing on the 15th pending the updated Closing Disclosure (CD) acknowledgment."

### Tone Calibration

| Audience | Tone | Detail Level | Acronym Style |
|----------|------|--------------|---------------|
| Internal | Direct, efficient | High technical detail | Free use |
| Borrower | Warm, reassuring | Simplified, milestone-focused | Always expand |
| Partner | Professional, collaborative | Moderate detail | Expand first use |


## Perennia AI Workflow Terminology

These terms are specific to Perennia AI's workflow automation and should be understood in all contexts:

### Theme Days Communication System

Theme Days is Perennia AI's structured borrower communication cadence during active loan processing. Each day of the week has a designated communication focus:

- **Monday - Milestone Monday**: Weekly status update summarizing loan progress, current stage, and what's ahead. Sets expectations for the week.
- **Tuesday - Task Tuesday**: Request day for outstanding items, documents, or borrower actions needed. Clear task lists with deadlines.
- **Wednesday - Wisdom Wednesday**: Educational content about the mortgage process, what to expect at closing, homeownership tips. Builds trust and reduces borrower anxiety.
- **Thursday - Thankful Thursday**: Gratitude and relationship-building. Thank borrowers for documents submitted, responsiveness, or patience. Humanizes the process.
- **Friday - Forward Friday**: Look-ahead communication. Preview next week's milestones, remind of upcoming deadlines, weekend availability info.

**Usage in AI communications:**
- When referencing Theme Days, the AI should understand which day's theme applies and match the tone/content appropriately
- Theme Day emails should follow the designated focus while still addressing urgent loan-specific matters
- If a critical update conflicts with the day's theme, prioritize the critical update but maintain the theme's tone where possible

### Last Mile Pre-Closing Process

Last Mile refers to Perennia AI's structured workflow for the final phase of loan processing, from Clear to Close through funding. It ensures nothing falls through the cracks in the critical final days.

**Last Mile Stages:**

1. **CTC Received**: Loan approved, conditions satisfied. Triggers Last Mile workflow initiation.

2. **CD Preparation**: Closing Disclosure drafted, fees balanced, figures confirmed with title.

3. **CD Sent**: Closing Disclosure delivered to borrower. 3-day waiting period begins. Track acknowledgment.

4. **Closing Scheduled**: Date/time/location confirmed with all parties. Wire instructions prepared.

5. **Pre-Closing QC**: Final quality control review. Verify all docs current, no changes to borrower status.

6. **Docs to Title**: Closing package sent to title company/attorney. Confirm receipt.

7. **Closing Day**: Signing appointment. Monitor for completion, handle last-minute issues.

8. **Docs Back**: Signed documents returned from title. Review for completeness and errors.

9. **Funding**: Wire released. Loan funded. Confirm with title.

10. **Recording**: Deed recorded with county. Transaction complete.

**Last Mile Alerts:**
- CD acknowledgment not received within 24 hours
- Closing scheduled within 3 days but CD not yet sent
- Docs to title not confirmed within 24 hours of sending
- Funding conditions outstanding on closing day
- Recording not confirmed within 48 hours of funding

### Post-Closing Referral Workflow

Automated relationship nurturing after loan closes to generate referrals and repeat business:

- **Closing Day**: Congratulations message, move-in tips, set expectations for post-closing contact
- **Week 1**: First payment reminder, mortgage servicer introduction, homeowner checklist
- **Day 30**: Check-in on move, address any post-closing questions
- **Day 60**: Request review/testimonial if experience was positive
- **Day 90**: Referral ask, introduce referral program/incentives
- **Quarterly**: Market updates, home value check-ins, refinance opportunities when rates favorable
- **Annual**: Loan anniversary acknowledgment, annual review offer, property tax reminder

### Rate Lock Intelligence

Perennia AI's system for managing rate lock decisions and expirations:

- **Lock Status**: Locked, Floating, Expired, Extended
- **Lock Expiration**: Date the current lock expires
- **Days to Expiration**: Countdown to lock expiration
- **Extension Cost**: Pricing impact of extending the lock
- **Renegotiation Eligibility**: Whether current market allows for rate improvement
- **Lock Alert Thresholds**: Configurable warnings at 7, 5, 3, 1 days before expiration

**Rate Lock Terminology:**
- Float: Loan rate not yet locked, subject to market movement
- Lock: Rate secured at specific price for specific period
- Relock: New lock after expiration (usually at worse pricing)
- Extend: Pay fee to extend existing lock period
- Renegotiate: Request better pricing if market improved significantly

### Loan Pipeline Stages

Perennia AI's standard loan lifecycle stages:

1. **Lead**: Initial inquiry, not yet application
2. **Pre-Qual**: Quick assessment completed, no full application
3. **Application**: 1003 received, file opened
4. **Processing**: Gathering documentation, ordering services
5. **Submitted**: File sent to underwriting
6. **Underwriting**: Active UW review
7. **Conditional Approval**: Approved with conditions (most common approval type)
8. **Final Approval**: All conditions cleared
9. **Clear to Close**: Approved for closing docs
10. **Closing Scheduled**: Appointment set
11. **Closed/Funded**: Transaction complete
12. **On Hold**: Paused, waiting on borrower or external factor
13. **Cancelled**: Withdrawn or denied

### AI Task Automation Terminology

Terms related to Perennia AI's AI learning and task automation system:

- **Task Template**: Predefined task structure the AI can learn to complete
- **Training Example**: Human-completed instance used to teach AI the task
- **Confidence Score**: AI's self-assessed likelihood of correct task completion (0-100%)
- **Human Review Queue**: Tasks AI completed but flagged for human verification
- **Graduation Threshold**: Confidence level at which AI can complete task autonomously
- **Feedback Loop**: Human corrections that refine AI task performance
- **Task Escalation**: AI recognition that a task requires human intervention

### Circle of Cashflow / Referral Ecosystem

Perennia AI's referral network model:

- **Referral Source**: Person or entity that sends business (agent, past client, partner)
- **Referral Score**: Weighted rating of referral source quality and volume
- **Reciprocal Referral**: Business sent back to referral partners
- **Attribution**: Tracking which source generated a lead/loan
- **Circle Member**: Active participant in referral ecosystem
- **Referral Velocity**: Rate of referrals over time from a source


## Combining Context and Terminology

When generating communications, the AI should:

1. Detect the audience (internal/borrower/partner)
2. Apply appropriate acronym expansion rules
3. Reference Perennia AI workflows by name when relevant to internal users
4. Translate Perennia AI concepts to plain language for borrowers
5. Match Theme Day tone when generating scheduled communications
6. Flag Last Mile alerts proactively when loan data indicates risk

### Example Transformations

**Internal note about a loan:**
"File is CTC as of today. Last Mile initiated. CD going out tomorrow, targeting closing 12/1. Lock expires 12/3, no extension needed if we stay on track. Theme Day comms paused for Last Mile sequence."

**Same information for borrower:**
"Great news! Your loan is fully approved and we're cleared to close. You'll receive your final Closing Disclosure tomorrow, and we're targeting your closing for December 1st. You'll hear from us with next steps as we finalize everything."

**Same information for real estate agent:**
"Loan is Clear to Close. CD goes out tomorrow, closing scheduled for 12/1. We're in good shape on the rate lock. Let me know if you need anything from our side for closing coordination."

=== END COMMUNICATION CONTEXT ===

INTENT CLASSIFICATION:
You MUST classify each user message to one of these intents and return the appropriate JSON:

COACHING MODES (ALL MUST return intent: "DAILY_VIEW"):
- "Daily Briefing" or "top 3 priorities" → intent: "DAILY_VIEW"
- "Pipeline Audit" or "bottlenecks" or "stalled deals" → intent: "DAILY_VIEW"
- "Focus Reset" or "back on track" or "get focused" → intent: "DAILY_VIEW"
- "What should I do next" or "priority decision" → intent: "DAILY_VIEW"
- "Accountability Review" or "review my performance" → intent: "DAILY_VIEW"
- "Tough Love" or "inefficiencies" or "call out" → intent: "DAILY_VIEW"
- "Teach me the process" or "systemic thinking" → intent: "DAILY_VIEW"

OTHER INTENTS:
- "What do I need to do today?" or "my tasks" or "daily overview" → intent: "DAILY_VIEW"
- "Tell me about my leads" or "how many leads" or "show my clients" → intent: "GENERAL_QUERY"
- "Send email" or "email clients" → intent: "EMAIL_CAMPAIGN"
- "Find [name]" or "search for" → intent: "SEARCH"
- Questions about data (leads, loans, pipeline) → intent: "GENERAL_QUERY"

CRITICAL: ALL coaching mode prompts MUST return "DAILY_VIEW", NOT "PIPELINE_REPORT".
STOP AND CHECK: If the user asked about "leads", "clients", or "data", you MUST return intent: "GENERAL_QUERY", NOT "DAILY_VIEW".

CRITICAL MEMORY INSTRUCTIONS:
- You have access to the FULL conversation history - use it!
- When user says "it", "that", "the email", "the update" - CHECK HISTORY to find what they're referring to
- NEVER ask "what email?" if we just discussed an email
- NEVER start over if user asks to modify something - build on what was already created
- When user asks to modify previous work, find it in history and make the specific change
- Always reference previous context when relevant to the current request
- If user says "make it shorter" or "make it more urgent", modify the PREVIOUS draft

CONVERSATION CONTINUITY EXAMPLES:
- If we just drafted an email and user says "make it shorter" → modify that email
- If we previewed a bulk update and user says "change the reason" → update that action
- If user refers to "the last one" or "that" → find it in conversation history
- Maintain context across multiple turns without losing track

INTENT MATCHING RULES (FOLLOW STRICTLY):
- When user asks "what do I need to do today", "my tasks", "what's on my plate", "daily overview" → return DAILY_VIEW
- When user asks about their leads, clients, or pipeline data (e.g., "tell me about my leads", "show my clients", "how many leads do I have") → return GENERAL_QUERY with the actual data from CRM context
- When user explicitly asks to "send email", "email clients", "draft email" → return EMAIL_CAMPAIGN
- When user explicitly asks to "update records", "bulk update" → return BULK_UPDATE
- When user explicitly asks about "voicemail", "drop voicemail" → return VOICEMAIL_DROP
- When user explicitly asks for "report", "pipeline report" → return PIPELINE_REPORT
- When user asks about specific lead/client by name → return SEARCH
- When user asks to "send pre-approval letter", "generate pre-approval", "create pre-approval letter" → return PRE_APPROVAL_LETTER
- DO NOT suggest actions the user didn't ask for. If they ask about leads, show the lead data from CRM context.

CRITICAL: When answering questions about CRM data (leads, loans, clients, pipeline):
- ALWAYS use the CRM DATA provided below - this is the user's ACTUAL data
- Include specific names, numbers, and details from the data
- Never make up placeholder data - use what's in the CRM DATA section

EXAMPLES OF CORRECT INTENT MATCHING:
User: "What do I need to do today?" → intent: "DAILY_VIEW"
User: "Daily Briefing - Get my top 3 priorities" → intent: "DAILY_VIEW"
User: "Focus Reset - Help me get back on track" → intent: "DAILY_VIEW"
User: "Pipeline Audit - Identify bottlenecks" → intent: "DAILY_VIEW"
User: "Accountability Review - Review my performance" → intent: "DAILY_VIEW"
User: "Tough Love Mode - Call out my inefficiencies" → intent: "DAILY_VIEW"
User: "Tell me about my leads" → intent: "GENERAL_QUERY" (explain the lead data)
User: "How many leads do I have?" → intent: "GENERAL_QUERY" (provide count)
User: "Show me my pipeline" → intent: "GENERAL_QUERY" (show pipeline data)
User: "Send an email to my pre-approved clients" → intent: "EMAIL_CAMPAIGN"
User: "Find John Smith" → intent: "SEARCH"
User: "Send a pre-approval letter for Steve Latterson" → intent: "PRE_APPROVAL_LETTER" (ask for missing details)
User: "Generate pre-approval for Jane Doe, $400k conventional to agent@email.com" → intent: "PRE_APPROVAL_LETTER" (has all info)

For GENERAL_QUERY about data, your response should include:
- explanation: A summary of the requested data with actual numbers and names from CRM context
- data: The relevant data subset

You can perform the following actions:

1. DAILY_VIEW - Show today's tasks, follow-ups, and reconciliation items (use for ANY question about "today", "tasks", "to do", "what should I do")
2. EMAIL_CAMPAIGN - Send emails to filtered groups of clients (ONLY when user explicitly requests email)
3. BULK_UPDATE - Update multiple records at once
4. VOICEMAIL_DROP - Queue ringless voicemail campaigns
5. PIPELINE_REPORT - Generate pipeline analysis reports
6. SEARCH - Search for clients, deals, or tasks
7. GENERAL_QUERY - Answer questions about the CRM data
8. ANALYTICAL_QUERY - Run advanced analytics on CRM data
9. MARKET_INTELLIGENCE - Get rate lock recommendations and market conditions
10. PRE_APPROVAL_LETTER - Generate and send pre-approval letters to borrowers or their agents

MARKET INTELLIGENCE QUERIES:
When user asks about rate locks, market conditions, rates, or whether to lock:
- "should I lock?" or "rate lock recommendation" → intent: "MARKET_INTELLIGENCE"
- "what are current rates?" or "market conditions" → intent: "MARKET_INTELLIGENCE"
- "when should I lock?" or "lock or float?" → intent: "MARKET_INTELLIGENCE"
- "MBS prices" or "treasury yields" → intent: "MARKET_INTELLIGENCE"
- "rate lock guidance" or "rate guidance for tomorrow" → intent: "MARKET_INTELLIGENCE"
- "what's the market looking like?" or "rate outlook" → intent: "MARKET_INTELLIGENCE"
- "should my clients lock?" or "lock timing" → intent: "MARKET_INTELLIGENCE"

IMPORTANT: For rate/market questions, NEVER ask the user for market data. The system has real-time market data available via get_market_intelligence(). Always use MARKET_INTELLIGENCE intent to fetch this data automatically.

For MARKET_INTELLIGENCE, data should include:
- lock_days: Optional number of days for lock (15, 30, 45, 60). Default 30.
- loan_amount: Optional loan amount for context

EXAMPLE MARKET_INTELLIGENCE RESPONSE:
{
  "intent": "MARKET_INTELLIGENCE",
  "explanation": "Based on current market conditions, here's my rate lock recommendation.",
  "data": {
    "lock_days": 30
  }
}

ANALYTICAL QUERIES AVAILABLE:
When user asks analytical questions, use these query types:
- "pipeline analysis" or "how is my pipeline doing" → query_pipeline_analysis
- "lead source performance" or "best lead sources" → query_lead_source_performance
- "conversion rates" or "funnel analysis" → query_conversion_funnel
- "loan type performance" or "best loan types" → query_loan_type_performance
- "monthly trends" or "month over month" → query_monthly_trends
- "stale leads" or "leads not spoken to" or "inactive leads" or "haven't contacted" → query_stale_leads

CRITICAL - STALE LEADS QUERIES:
When user asks about leads they haven't contacted, leads gone cold, or inactive leads:
Examples:
- "what leads have I not spoken to in a while?" → intent: "ANALYTICAL_QUERY", query_type: "query_stale_leads"
- "show me stale leads" → intent: "ANALYTICAL_QUERY", query_type: "query_stale_leads"
- "which leads need follow-up?" → intent: "ANALYTICAL_QUERY", query_type: "query_stale_leads"
- "leads I haven't contacted recently" → intent: "ANALYTICAL_QUERY", query_type: "query_stale_leads"
- "inactive leads" or "cold leads" → intent: "ANALYTICAL_QUERY", query_type: "query_stale_leads"

DO NOT return DAILY_VIEW for these queries - they are specifically asking about STALE LEADS, not daily tasks.
- "stale leads" or "leads need attention" → query_stale_leads
- "high value opportunities" or "big deals" → query_high_value_opportunities
- "activity summary" or "what have I done" → query_activity_summary

For ANALYTICAL_QUERY, data MUST include:
- query_type: One of: "query_pipeline_analysis", "query_lead_source_performance", "query_conversion_funnel", "query_loan_type_performance", "query_monthly_trends", "query_stale_leads", "query_high_value_opportunities", "query_activity_summary"
- params: Any parameters like date_range_days (default 90), min_amount (default 500000), limit (default 20), stale_days (default 14), months (default 6), days (default 30)

EXAMPLE ANALYTICAL_QUERY RESPONSE:
{
  "intent": "ANALYTICAL_QUERY",
  "explanation": "I'll run that analysis for you.",
  "data": {
    "query_type": "query_monthly_trends",
    "params": {"months": 6}
  }
}

When responding, you MUST return a valid JSON object with these fields:
- intent: The action type from the list above
- explanation: A brief, friendly explanation of what you're going to do
- preview: Object containing preview data for the action (if applicable)
- data: Additional data needed for execution

For EMAIL_CAMPAIGN, preview should include:
- recipients: List of client names/count
- subject: Email subject line
- body: Email content
- template: Template name if using one

For BULK_UPDATE, preview should include:
- records: List of records to update with current and new values
- field: Field being updated
- count: Number of records affected

For VOICEMAIL_DROP, preview should include:
- recipients: List of recipients
- script: The voicemail script content
- scheduled_time: When to send

For PIPELINE_REPORT, preview should include:
- report_type: Type of report
- date_range: Date range covered
- metrics: Key metrics to include

PRE-APPROVAL LETTER HANDLING:
When user asks to send, create, or generate a pre-approval letter:
- "send pre-approval letter for John Smith" → intent: "PRE_APPROVAL_LETTER"
- "create pre-approval for Jane Doe" → intent: "PRE_APPROVAL_LETTER"
- "generate pre-approval letter" → intent: "PRE_APPROVAL_LETTER"
- "send pre-approval to the agent" → intent: "PRE_APPROVAL_LETTER"

CRITICAL - GATHERING MISSING INFORMATION:
For pre-approval letters, you MUST have these required fields:
1. borrower_names - Full name(s) of the borrower(s)
2. loan_amount - Approved loan amount (number)
3. loan_type - Type of loan (Conventional, FHA, VA, USDA, Jumbo)
4. recipient_email - Email address to send the letter to

Optional fields (will use defaults if not provided):
- property_address - Property address or "To Be Determined"
- interest_rate - Interest rate (will use "Market Rate" if not provided)
- expiration_days - Days until letter expires (default 90)
- lead_id - Lead ID if known

IF ANY REQUIRED FIELD IS MISSING:
You MUST ask follow-up questions conversationally to gather the information.
DO NOT refuse to help. Instead, ask for the specific missing information.

EXAMPLE CONVERSATION FLOW:
User: "Send a pre-approval letter for Steve Latterson"
Assistant: "I'll prepare a pre-approval letter for Steve Latterson. I need a few details:

1. **Loan Amount**: What loan amount should I put on the letter?
2. **Loan Type**: What type of loan? (Conventional, FHA, VA, USDA, or Jumbo)
3. **Recipient Email**: Who should I send this letter to?
4. **Property Address**: Do you have a property address, or should I put 'To Be Determined'?"

User: "$450,000 conventional, send it to timothy@perenniaai.com, TBD on property"
Assistant: (Now has all required info, returns PRE_APPROVAL_LETTER intent with data)

SEARCHING FOR LEAD DATA:
When user mentions a name, first search the CRM to find their lead record and pull any available data:
- Lead ID for activity tracking
- Existing loan amount if on file
- Existing loan type if on file
- Email address if on file

Use this data to pre-fill fields and reduce questions needed.

For PRE_APPROVAL_LETTER, preview should include:
- borrower_names: Full name(s) of borrower(s)
- property_address: Property address or "To Be Determined"
- loan_amount: Approved loan amount (number)
- loan_type: Type of loan program
- recipient_email: Email to send the letter to
- interest_rate: (optional) Interest rate
- expiration_days: (optional) Days until expiration
- lead_id: (optional) Lead ID for activity tracking

EXAMPLE PRE_APPROVAL_LETTER RESPONSE:
{
  "intent": "PRE_APPROVAL_LETTER",
  "explanation": "I'll generate and send a pre-approval letter for Steve Latterson to timothy@perenniaai.com.",
  "preview": {
    "borrower_names": "Steve Latterson",
    "property_address": "To Be Determined",
    "loan_amount": 450000,
    "loan_type": "Conventional",
    "recipient_email": "timothy@perenniaai.com",
    "expiration_days": 90
  },
  "data": {
    "lead_id": 123
  }
}

For DAILY_VIEW, data should include:
- tasks: List of today's tasks
- follow_ups: List of follow-ups
- reconciliations: List of reconciliation items
- summary: Overview statistics

For SEARCH, data should include:
- results: List of matching records
- query: The search terms used

Always be helpful, concise, and focus on actionable results. If you can't determine the intent, ask for clarification.
"""


# ============================================================================
# Helper Functions
# ============================================================================

def get_daily_summary(db: Session, user_id: int) -> Dict[str, Any]:
    """Get daily summary data for the user - includes REAL CRM data"""
    # Clear any previous failed transaction state
    try:
        db.rollback()
    except Exception:
        pass

    main = get_main_module()
    Task = main.Task
    Lead = main.Lead
    Loan = main.Loan
    AITask = main.AITask
    TaskType = main.TaskType

    today = datetime.now().date()

    # Get ALL pending tasks (not just today's) with lead/loan info
    all_tasks = db.query(Task).filter(
        Task.owner_id == user_id,
        Task.status != 'completed'
    ).order_by(Task.priority.desc(), Task.due_date.asc()).limit(20).all()

    # Also get AI tasks which have borrower_name field
    ai_tasks = []
    try:
        ai_tasks = db.query(AITask).filter(
            AITask.assigned_to_id == user_id,
            AITask.type != TaskType.COMPLETED
        ).order_by(AITask.due_date.asc()).limit(20).all()
    except Exception as e:
        logger.debug(f"AITask query failed: {e}")
        db.rollback()

    # Get workflow tasks (these are the tasks shown on the /tasks page)
    workflow_tasks = []
    try:
        from sqlalchemy import text
        result = db.execute(text("""
            SELECT wt.id, wt.task_title, wt.task_description, wt.priority,
                   wt.due_date, wt.status, wt.loan_id, l.borrower_name
            FROM workflow_tasks wt
            LEFT JOIN loans l ON wt.loan_id = l.id
            WHERE wt.status NOT IN ('completed', 'cancelled')
            ORDER BY wt.due_date ASC NULLS LAST
            LIMIT 50
        """))
        workflow_tasks = [dict(row._mapping) for row in result]
    except Exception as e:
        logger.debug(f"Workflow tasks query failed (table may not exist): {e}")
        db.rollback()

    # Build loan_id -> borrower_name map for AI tasks using raw SQL to avoid enum issues
    loan_ids = [t.loan_id for t in ai_tasks if t.loan_id]
    loan_map = {}
    if loan_ids:
        try:
            from sqlalchemy import text
            result = db.execute(text("""
                SELECT id, borrower_name FROM loans WHERE id = ANY(:loan_ids)
            """), {"loan_ids": loan_ids})
            loan_map = {row.id: row.borrower_name for row in result}
        except Exception as e:
            logger.debug(f"Loan name lookup failed: {e}")
            db.rollback()

    # Build a map of lead_id -> lead_name for enriching task display
    lead_ids = [t.lead_id for t in all_tasks if t.lead_id]
    lead_ids.extend([t.lead_id for t in ai_tasks if t.lead_id])
    lead_map = {}
    if lead_ids:
        leads_for_tasks = db.query(Lead).filter(Lead.id.in_(lead_ids)).all()
        lead_map = {l.id: l.name for l in leads_for_tasks}

    # Separate today's tasks and overdue tasks
    today_tasks = [t for t in all_tasks if t.due_date and t.due_date.date() == today]
    overdue_tasks = [t for t in all_tasks if t.due_date and t.due_date.date() < today]

    # Get ACTUAL LEAD DATA
    all_leads = db.query(Lead).filter(Lead.owner_id == user_id).all()
    total_leads = len(all_leads)

    # Group leads by status
    lead_status_breakdown = {}
    for lead in all_leads:
        status = lead.stage.value if lead.stage else 'Unassigned'
        lead_status_breakdown[status] = lead_status_breakdown.get(status, 0) + 1

    # Get ACTUAL LOAN DATA - use raw SQL to avoid enum deserialization issues
    all_loans = []
    total_loans = 0
    total_pipeline_value = 0
    loan_stage_breakdown = {}
    try:
        # Use raw SQL to get loan counts by stage, avoiding enum issues
        from sqlalchemy import text
        result = db.execute(text("""
            SELECT
                COALESCE(stage::text, 'Unknown') as stage,
                COUNT(*) as count,
                SUM(COALESCE(amount, 0)) as total_amount
            FROM loans
            WHERE loan_officer_id = :user_id
            GROUP BY stage
        """), {"user_id": user_id})

        for row in result:
            stage_name = row.stage if row.stage else 'Unknown'
            loan_stage_breakdown[stage_name] = row.count
            total_loans += row.count
            total_pipeline_value += float(row.total_amount or 0)
    except Exception as e:
        logger.warning(f"Loan query failed, using fallback: {e}")
        db.rollback()
        # Fallback: try simple count query
        try:
            total_loans = db.query(func.count(Loan.id)).filter(Loan.loan_officer_id == user_id).scalar() or 0
            total_pipeline_value = db.query(func.sum(Loan.amount)).filter(Loan.loan_officer_id == user_id).scalar() or 0
        except Exception:
            db.rollback()

    # Get MUM clients (safely check if table exists)
    mum_clients = []
    try:
        # Check if MUMClient model exists and query
        if hasattr(main, 'MUMClient'):
            MUMClient = main.MUMClient
            mum_clients = db.query(MUMClient).filter(MUMClient.loan_officer_id == user_id).limit(10).all()
    except Exception as e:
        db.rollback()  # Rollback to clear failed transaction
        logger.debug(f"MUM query failed (table may not exist): {e}")

    # Get unread emails/messages (safely check if table exists)
    unread_messages = 0
    try:
        if hasattr(main, 'EmailMessage'):
            EmailMessage = main.EmailMessage
            unread_messages = db.query(EmailMessage).filter(
                EmailMessage.user_id == user_id,
                EmailMessage.direction == 'inbound',
                EmailMessage.status == 'received'
            ).count()
    except Exception as e:
        db.rollback()  # Rollback to clear failed transaction
        logger.debug(f"EmailMessage query failed (table may not exist): {e}")

    # Build follow-ups from leads needing attention
    follow_ups = []

    # Helper function to enrich task title with lead/borrower name
    def get_enriched_task_title(task, is_ai_task=False):
        title = task.title
        borrower_name = None

        # For AI tasks, use borrower_name field directly or look up from loan
        if is_ai_task:
            borrower_name = getattr(task, 'borrower_name', None)
            if not borrower_name and task.loan_id:
                borrower_name = loan_map.get(task.loan_id)

        # For regular tasks, use lead_name from lead_map
        if not borrower_name:
            borrower_name = lead_map.get(task.lead_id) if hasattr(task, 'lead_id') and task.lead_id else None

        # Add borrower/lead name to title
        if borrower_name:
            # Check if name already in title to avoid duplication
            if borrower_name.lower() not in title.lower():
                return f"{title} - {borrower_name}"
        return title

    # Overdue tasks need immediate attention
    if overdue_tasks:
        follow_ups.append({
            "type": "Overdue Tasks",
            "items": [f"{get_enriched_task_title(t)} (Due: {t.due_date.strftime('%m/%d') if t.due_date else 'N/A'})" for t in overdue_tasks[:5]],
            "priority": "High"
        })

    # New leads need initial contact
    new_stage_leads = [l for l in all_leads if l.stage and l.stage.value == 'New']
    if new_stage_leads:
        follow_ups.append({
            "type": "New Leads Follow-up",
            "items": [f"{l.name} ({l.loan_type or 'N/A'})" for l in new_stage_leads[:5]],
            "priority": "High"
        })

    # Pre-approved leads - rate lock opportunities
    preapproved = [l for l in all_leads if l.stage and l.stage.value == 'Pre-Approved']
    if preapproved:
        follow_ups.append({
            "type": "Pre-Approved - Rate Lock Check",
            "items": [f"{l.name} (${l.preapproval_amount or 0:,.0f})" for l in preapproved[:5]],
            "priority": "High"
        })

    # Prospects need nurturing
    prospects = [l for l in all_leads if l.stage and l.stage.value == 'Prospect']
    if prospects:
        follow_ups.append({
            "type": "Prospect Nurturing",
            "items": [f"{l.name}" for l in prospects[:5]],
            "priority": "Medium"
        })

    # Build reconciliations from loans in pipeline
    reconciliations = []

    # Loans needing attention by stage
    processing_loans = [l for l in all_loans if l.stage == 'Processing']
    if processing_loans:
        reconciliations.append({
            "type": "Processing - Document Collection",
            "items": [f"{loan.borrower_name} (${loan.amount or 0:,.0f})" for loan in processing_loans[:3]]
        })

    uw_loans = [l for l in all_loans if l.stage in ['UW Received', 'Approved']]
    if uw_loans:
        reconciliations.append({
            "type": "Underwriting Review",
            "items": [f"{loan.borrower_name} ({loan.stage} - ${loan.amount or 0:,.0f})" for loan in uw_loans[:3]]
        })

    ctc_loans = [l for l in all_loans if l.stage == 'CTC']
    if ctc_loans:
        reconciliations.append({
            "type": "Clear to Close - Schedule Closing",
            "items": [f"{loan.borrower_name} (${loan.amount or 0:,.0f})" for loan in ctc_loans[:3]]
        })

    # MUM clients needing attention
    if mum_clients:
        reconciliations.append({
            "type": "MUM Client Check-ins",
            "items": [f"{c.borrower_name} ({c.loan_type or 'N/A'})" for c in mum_clients[:3]]
        })

    # Combine regular tasks and AI tasks, sorted by due date
    combined_tasks = []

    # Add regular tasks
    for t in all_tasks[:10]:
        combined_tasks.append({
            "id": t.id,
            "title": get_enriched_task_title(t, is_ai_task=False),
            "description": t.description,
            "priority": t.priority,
            "due_date": t.due_date.isoformat() if t.due_date else None,
            "lead_id": t.lead_id,
            "lead_name": lead_map.get(t.lead_id) if t.lead_id else None,
            "borrower_name": None,
            "source": "task"
        })

    # Add AI tasks with borrower names
    for t in ai_tasks[:10]:
        borrower = t.borrower_name
        if not borrower and t.loan_id:
            borrower = loan_map.get(t.loan_id)
        combined_tasks.append({
            "id": f"ai-{t.id}",
            "title": get_enriched_task_title(t, is_ai_task=True),
            "description": t.description,
            "priority": t.priority,
            "due_date": t.due_date.isoformat() if t.due_date else None,
            "lead_id": t.lead_id,
            "lead_name": lead_map.get(t.lead_id) if t.lead_id else None,
            "borrower_name": borrower,
            "loan_id": t.loan_id,
            "source": "ai_task"
        })

    # Add workflow tasks (from /tasks page)
    for wt in workflow_tasks[:20]:
        combined_tasks.append({
            "id": f"wf-{wt['id']}",
            "title": wt.get('task_title', 'Workflow Task'),
            "description": wt.get('task_description'),
            "priority": wt.get('priority', 'medium'),
            "due_date": wt['due_date'].isoformat() if wt.get('due_date') else None,
            "lead_id": None,
            "lead_name": None,
            "borrower_name": wt.get('borrower_name'),
            "loan_id": wt.get('loan_id'),
            "source": "workflow_task"
        })

    # Sort combined tasks by due date (None values at end)
    combined_tasks.sort(key=lambda x: (x["due_date"] is None, x["due_date"] or ""))

    return {
        "tasks": combined_tasks[:15],
        "follow_ups": follow_ups,
        "reconciliations": reconciliations,
        "summary": {
            "total_tasks": len(all_tasks) + len(ai_tasks) + len(workflow_tasks),
            "workflow_tasks": len(workflow_tasks),
            "overdue_tasks": len(overdue_tasks),
            "active_leads": total_leads,
            "hot_prospects": len([l for l in all_leads if l.stage and l.stage.value in ['Prospect', 'Pre-Approved']]),
            "loans_in_pipeline": total_loans,
            "pipeline_volume": f"${total_pipeline_value:,.0f}",
            "unread_messages": unread_messages,
            "mum_clients": len(mum_clients),
            "lead_status_breakdown": lead_status_breakdown,
            "loan_stage_breakdown": loan_stage_breakdown
        }
    }


def search_records(db: Session, user_id: int, query: str) -> Dict[str, Any]:
    """Search across leads and loans"""
    main = get_main_module()
    Lead = main.Lead
    Loan = main.Loan

    search_term = f"%{query}%"

    # Search leads (using owner_id and name field)
    leads = db.query(Lead).filter(
        Lead.owner_id == user_id,
        or_(
            Lead.name.ilike(search_term),
            Lead.email.ilike(search_term),
            Lead.phone.ilike(search_term)
        )
    ).limit(10).all()

    # Search loans using raw SQL to avoid enum deserialization issues
    loan_results = []
    try:
        from sqlalchemy import text
        result = db.execute(text("""
            SELECT id, borrower_name, amount, stage::text as stage
            FROM loans
            WHERE loan_officer_id = :user_id
            AND (borrower_name ILIKE :search_term OR property_address ILIKE :search_term)
            LIMIT 10
        """), {"user_id": user_id, "search_term": search_term})
        loan_results = [
            {
                "id": row.id,
                "borrower_name": row.borrower_name,
                "loan_amount": float(row.amount) if row.amount else 0,
                "stage": row.stage
            } for row in result
        ]
    except Exception as e:
        logger.debug(f"Loan search failed: {e}")
        db.rollback()

    return {
        "leads": [
            {
                "id": l.id,
                "name": l.name,
                "email": l.email,
                "phone": l.phone,
                "status": l.stage.value if l.stage else "Unassigned"
            } for l in leads
        ],
        "loans": loan_results,
        "query": query
    }


def get_clients_by_filter(db: Session, user_id: int, filter_criteria: Dict[str, Any]):
    """Get clients matching filter criteria"""
    main = get_main_module()
    Lead = main.Lead

    query = db.query(Lead).filter(Lead.owner_id == user_id)

    if "loan_type" in filter_criteria:
        query = query.filter(Lead.loan_type == filter_criteria["loan_type"])

    if "status" in filter_criteria:
        query = query.filter(Lead.status == filter_criteria["status"])

    if "tag" in filter_criteria:
        from sqlalchemy import text
        tag_leads = db.execute(
            text("SELECT lead_id FROM lead_tags WHERE tag = :tag"),
            {"tag": filter_criteria["tag"]}
        ).fetchall()
        tag_lead_ids = [row[0] for row in tag_leads]
        if tag_lead_ids:
            query = query.filter(Lead.id.in_(tag_lead_ids))
        else:
            query = query.filter(Lead.id == None)

    return query.limit(100).all()


def execute_analytical_query(db: Session, user_id: int, query_type: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
    """Execute an analytical query and return formatted results"""
    if params is None:
        params = {}

    # Map tool names to query types
    query_type_map = {
        "query_pipeline_analysis": "pipeline_analysis",
        "query_lead_source_performance": "lead_source_performance",
        "query_conversion_funnel": "conversion_funnel",
        "query_loan_type_performance": "loan_type_performance",
        "query_monthly_trends": "monthly_trends",
        "query_stale_leads": "stale_leads_report",
        "query_high_value_opportunities": "high_value_opportunities",
        "query_activity_summary": "activity_summary",
    }

    actual_query_type = query_type_map.get(query_type, query_type)

    # Execute the query
    result = execute_query(db, actual_query_type, params, user_id)

    # Format for Claude
    formatted = format_results(actual_query_type, result)

    return {
        "query_type": actual_query_type,
        "success": result.get("success", False),
        "data": result.get("data", []),
        "count": result.get("count", 0),
        "formatted_text": formatted
    }


def get_market_intelligence(lock_days: int = 30) -> Dict[str, Any]:
    """Fetch current market intelligence for rate lock recommendations"""
    try:
        from scrapers import MarketDataOrchestrator

        orchestrator = MarketDataOrchestrator()
        snapshot = orchestrator.get_market_snapshot()

        if not snapshot:
            snapshot = get_fallback_market_data()

        # Get rate lock context for specific days
        lock_context = orchestrator.get_rate_lock_context(lock_days)

        return {
            "current_rates": {
                "30yr_fixed": snapshot.get("mortgage_rates", {}).get("rate_30yr", 6.50),
                "15yr_fixed": snapshot.get("mortgage_rates", {}).get("rate_15yr", 5.75),
                "spread_to_10yr": snapshot.get("mortgage_rates", {}).get("spread_to_10yr", 2.35)
            },
            "treasury_yields": {
                "2yr": snapshot.get("treasury", {}).get("2yr", 4.25),
                "5yr": snapshot.get("treasury", {}).get("5yr", 4.10),
                "10yr": snapshot.get("treasury", {}).get("10yr", 4.15),
                "30yr": snapshot.get("treasury", {}).get("30yr", 4.35),
                "spread_2s10s": snapshot.get("treasury", {}).get("spread_2s10s", -0.10)
            },
            "market_conditions": {
                "volatility": snapshot.get("volatility", {}).get("assessment", "moderate"),
                "vix": snapshot.get("volatility", {}).get("vix", 18.5),
                "market_score": snapshot.get("market_score", 55)
            },
            "rate_lock_recommendation": {
                "overall": snapshot.get("recommendation", "CAUTIOUS"),
                "lock_period": lock_days,
                "context": lock_context
            },
            "timestamp": snapshot.get("timestamp")
        }
    except Exception as e:
        logger.error(f"Error fetching market intelligence: {e}")
        return get_fallback_market_data()


def get_fallback_market_data() -> Dict[str, Any]:
    """Fallback market data when scrapers unavailable"""
    from datetime import datetime

    return {
        "current_rates": {
            "30yr_fixed": 6.50,
            "15yr_fixed": 5.75,
            "spread_to_10yr": 2.35
        },
        "treasury_yields": {
            "2yr": 4.25,
            "5yr": 4.10,
            "10yr": 4.15,
            "30yr": 4.35,
            "spread_2s10s": -0.10
        },
        "market_conditions": {
            "volatility": "moderate",
            "vix": 18.5,
            "market_score": 55
        },
        "rate_lock_recommendation": {
            "overall": "CAUTIOUS",
            "guidance": "Market conditions suggest careful evaluation. Consider locking if rate is acceptable and closing within 30 days. For longer timelines, monitor for better opportunities.",
            "factors": [
                "Treasury yields relatively stable",
                "Moderate volatility environment",
                "Mortgage spreads within normal range"
            ]
        },
        "timestamp": datetime.now().isoformat(),
        "is_fallback": True
    }


def get_sla_turnaround_times(db: Session) -> Dict[str, Any]:
    """Fetch SLA turnaround times from the SLA tracking system"""
    try:
        from crud.sla_tracking import get_all_sla_measures, get_dashboard_summary

        # Get all active SLA measures
        measures = get_all_sla_measures(db, organization_id=1, active_only=True)

        # Format SLA measures for display
        sla_list = []
        for measure in measures:
            # Convert target value to readable format
            target_value = measure.target_value
            target_unit = measure.target_unit if hasattr(measure, 'target_unit') else 'hours'

            # Format milestone type for display
            milestone_name = measure.milestone_type.value if hasattr(measure.milestone_type, 'value') else str(measure.milestone_type)
            display_name = milestone_name.replace('_', ' ').title()

            # Calculate display time (convert hours to days if > 24)
            if target_unit == 'hours' and target_value >= 24:
                display_time = f"{target_value / 24:.1f} business days"
            elif target_unit == 'hours':
                display_time = f"{target_value:.0f} hours"
            elif target_unit == 'days':
                display_time = f"{target_value:.0f} business days"
            else:
                display_time = f"{target_value} {target_unit}"

            sla_list.append({
                "milestone": display_name,
                "name": measure.name,
                "target": display_time,
                "target_hours": target_value,
                "description": measure.description,
                "warning_threshold": f"{measure.warning_threshold_pct}%",
                "business_hours_only": measure.business_hours_only if hasattr(measure, 'business_hours_only') else True
            })

        # Get dashboard summary for current performance
        try:
            summary = get_dashboard_summary(db, organization_id=1)
        except Exception:
            summary = {}

        return {
            "sla_measures": sla_list,
            "total_measures": len(sla_list),
            "current_performance": {
                "on_time_rate": summary.get("on_time_rate", "N/A"),
                "active_milestones": summary.get("active_milestones", 0),
                "at_risk": summary.get("at_risk", 0),
                "overdue": summary.get("overdue", 0)
            },
            "business_hours": {
                "start": "9:00 AM",
                "end": "5:00 PM",
                "work_days": "Monday - Friday"
            }
        }
    except Exception as e:
        logger.error(f"Error fetching SLA turnaround times: {e}")
        # Return default SLA values if database fetch fails
        return {
            "sla_measures": [
                {"milestone": "Application To Approval", "name": "Application to Approval", "target": "5-10 business days", "description": "Time from application submission to credit approval"},
                {"milestone": "Processing", "name": "Initial Processing", "target": "1-3 business days", "description": "Initial document collection and review"},
                {"milestone": "Underwriting", "name": "Underwriting Review", "target": "3-5 business days", "description": "Full underwriting analysis"},
                {"milestone": "Clear To Close", "name": "Clear to Close", "target": "1-2 business days", "description": "Final approval after conditions cleared"},
                {"milestone": "Funding", "name": "Funding", "target": "Same/next business day", "description": "Post-closing disbursement"}
            ],
            "total_measures": 5,
            "is_default": True,
            "note": "These are typical industry targets. Check /sla page for your organization's specific SLAs."
        }


async def process_with_claude(
    message: str,
    context: List[Dict[str, str]],
    db: Session,
    user_id: int,
    action_context: Optional[Dict[str, Any]] = None,
    relevant_past: Optional[List[Dict]] = None,
    total_messages: int = 0,
    crm_context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Process the message with Claude AI"""

    if not anthropic_client:
        # Return mock response if no API key
        return generate_mock_response(message, db, user_id)

    # Build conversation history - use more context (50 messages for permanent memory)
    messages = []
    for ctx in context[-50:]:  # Keep last 50 messages for better context
        messages.append({
            "role": ctx.get("role", "user"),
            "content": ctx.get("content", "")
        })

    messages.append({
        "role": "user",
        "content": message
    })

    # Build enhanced system prompt with memory context
    system = SYSTEM_PROMPT

    # Add current date to system prompt so AI knows what day it is
    current_date = datetime.now()
    system += f"""

=== CURRENT DATE AND TIME ===
Today is: {current_date.strftime('%B %d, %Y')} ({current_date.strftime('%A')})
Current time: {current_date.strftime('%I:%M %p')}

IMPORTANT: Use this date when evaluating any deadlines, closing dates, or due dates.
- Dates BEFORE today are in the PAST
- If a closing date has already passed, the loan either CLOSED or was DELAYED
- Never say a past closing date is "on track" - it has already passed
=== END DATE INFO ===
"""

    # CHECK IF THIS IS A DAILY_VIEW OR COACHING REQUEST - add explicit summary numbers
    message_lower = message.lower()

    # Coaching mode detection
    is_daily_briefing = "daily briefing" in message_lower or "top 3 priorities" in message_lower
    is_pipeline_audit = "pipeline audit" in message_lower or "bottlenecks" in message_lower
    is_focus_reset = "focus reset" in message_lower or "back on track" in message_lower
    is_next_action = "what should i do next" in message_lower or "priority decision" in message_lower
    is_accountability = "accountability review" in message_lower or "review my performance" in message_lower
    is_tough_love = "tough love" in message_lower or "inefficiencies" in message_lower
    is_teach_process = "teach me the process" in message_lower or "systemic thinking" in message_lower

    # SLA/Turnaround time detection
    is_sla_question = any(phrase in message_lower for phrase in [
        "sla", "turnaround", "turn time", "turntimes", "turn-time",
        "how long", "timeline", "time frame", "timeframe",
        "processing time", "expected time", "target time",
        "service level", "service-level"
    ])

    is_coaching_mode = any([is_daily_briefing, is_pipeline_audit, is_focus_reset, is_next_action,
                           is_accountability, is_tough_love, is_teach_process])

    # INJECT SLA DATA for SLA-related questions
    if is_sla_question:
        sla_data = get_sla_turnaround_times(db)
        sla_measures = sla_data.get("sla_measures", [])

        # Format SLA measures for the system prompt
        sla_text = "\n".join([
            f"- **{m['milestone']}**: {m['target']}" + (f" - {m['description']}" if m.get('description') else "")
            for m in sla_measures
        ])

        performance = sla_data.get("current_performance", {})
        business_hours = sla_data.get("business_hours", {})

        system += f"""

=== SLA TURNAROUND TIMES (USE THIS DATA TO ANSWER THE USER'S QUESTION) ===

YOUR ORGANIZATION'S SLA TARGETS:
{sla_text}

BUSINESS HOURS: {business_hours.get('start', '9 AM')} - {business_hours.get('end', '5 PM')}, {business_hours.get('work_days', 'Monday-Friday')}

CURRENT PERFORMANCE:
- On-Time Rate: {performance.get('on_time_rate', 'N/A')}
- Active Milestones: {performance.get('active_milestones', 0)}
- At Risk: {performance.get('at_risk', 0)}
- Overdue: {performance.get('overdue', 0)}

IMPORTANT: When answering questions about SLAs or turnaround times:
1. Use the EXACT values from the SLA TARGETS above
2. Reference specific milestones by name
3. Mention that these are measured in business hours (Mon-Fri, 9-5)
4. If asked about specific stages, provide the target time for that stage
5. DO NOT give generic industry estimates - use YOUR organization's configured SLAs

=== END SLA DATA ===
"""

    if is_coaching_mode or any(phrase in message_lower for phrase in ["today", "daily", "morning", "need to do", "what should i", "my tasks", "what's on"]):
        # Fetch daily summary data to show exact numbers
        daily_data = get_daily_summary(db, user_id)
        summary = daily_data.get("summary", {})

        # Build task list for display
        task_list = ""
        today = datetime.now().date()  # Define today BEFORE the conditional
        if daily_data.get("tasks"):
            for task in daily_data["tasks"][:10]:
                due_date = task.get("due_date")
                if due_date:
                    try:
                        due_date_obj = datetime.fromisoformat(due_date).date() if isinstance(due_date, str) else due_date
                        if due_date_obj < today:
                            status_label = f"OVERDUE ({due_date_obj.strftime('%m/%d')})"
                        elif due_date_obj == today:
                            status_label = "Due TODAY"
                        else:
                            status_label = f"Due {due_date_obj.strftime('%m/%d')}"
                    except Exception:
                        status_label = "Due date unknown"
                else:
                    status_label = "No due date"
                task_list += f"- [{task.get('priority', 'N/A')}] {task.get('title', 'Untitled')} | {status_label}\n"

        system += f"""

=== DAILY VIEW DATA (YOU MUST USE THESE EXACT NUMBERS) ===
TODAY'S DATE: {today.strftime('%B %d, %Y')} ({today.strftime('%A')})

CRITICAL DATE RULES:
- Any closing date, due date, or deadline BEFORE {today.strftime('%B %d, %Y')} is IN THE PAST
- If a loan's closing date has passed, it either ALREADY CLOSED or was DELAYED - do NOT say "on track"
- Only say "on track" for FUTURE dates that haven't passed yet
- For past dates, say "was scheduled for [date]" or "should have closed on [date]"

ACTUAL CRM DATA FOR TODAY:
- Active Leads: {summary.get('active_leads', 0)}
- Loans in Pipeline: {summary.get('loans_in_pipeline', 0)}
- Pipeline Volume: {summary.get('pipeline_volume', '$0')}
- Total Tasks: {summary.get('total_tasks', 0)}
- Overdue Tasks: {summary.get('overdue_tasks', 0)}
- Unread Messages: {summary.get('unread_messages', 0)}

LEAD STATUS BREAKDOWN:
{chr(10).join([f"- {status}: {count}" for status, count in summary.get('lead_status_breakdown', {}).items()])}

LOAN STAGE BREAKDOWN:
{chr(10).join([f"- {stage}: {count}" for stage, count in summary.get('loan_stage_breakdown', {}).items()])}

OUTSTANDING TASKS:
{task_list if task_list else "No tasks found"}

TASK PRESENTATION RULES:
- If there are {summary.get('overdue_tasks', 0)} overdue tasks: START with "You have {summary.get('overdue_tasks', 0)} overdue tasks that need immediate attention"
- If total_tasks > 0: Say "You have {summary.get('total_tasks', 0)} outstanding tasks" NOT "no tasks due today"
- ALWAYS prioritize overdue tasks first in your response
- DO NOT say "no tasks" if total_tasks > 0 or overdue_tasks > 0
- SHOW the actual tasks from the OUTSTANDING TASKS list above
=== END DAILY VIEW DATA ===
"""

        # Add coaching mode specific instructions
        if is_daily_briefing:
            system += """

=== COACHING MODE: DAILY BRIEFING ===
The user wants their TOP 3 PRIORITIES for today. Structure your response as:
1. Identify the 3 most critical items from tasks and follow-ups
2. ALWAYS include the BORROWER/CLIENT NAME for each task (from the title which includes "- Borrower Name")
3. For each priority, explain WHY it's urgent
4. Provide specific action steps
5. Keep it focused and actionable - no fluff

IMPORTANT: Each priority MUST include the borrower/client name. Never say just "Review Loan Documents" -
say "Review Loan Documents - John Smith" or "Review Loan Documents for John Smith".
=== END COACHING MODE ===
"""
        elif is_pipeline_audit:
            system += """

=== COACHING MODE: PIPELINE AUDIT ===
The user wants to identify BOTTLENECKS and STALLED DEALS. Structure your response as:
1. Identify deals that haven't moved stages in 7+ days
2. Call out any missing documents or pending items
3. Highlight conversion issues between stages
4. Provide specific recommendations to unstick each bottleneck
Be direct and specific - name names and amounts.
=== END COACHING MODE ===
"""
        elif is_focus_reset:
            system += """

=== COACHING MODE: FOCUS RESET ===
The user is scattered and needs to refocus. Structure your response as:
1. List ONLY the most critical items that need immediate attention
2. Cut through the noise - ignore low-priority items
3. Provide a clear sequence: do THIS first, THEN this, THEN this
4. Be calm but direct - help them see the path forward
=== END COACHING MODE ===
"""
        elif is_next_action:
            system += """

=== COACHING MODE: WHAT SHOULD I DO NEXT ===
The user needs priority decision guidance. Structure your response as:
1. Look at their current workload and identify the single most impactful action
2. Explain why this should be next (urgency, value, dependencies)
3. Provide the specific next step to take
4. If there are competing priorities, explain the trade-offs
=== END COACHING MODE ===
"""
        elif is_accountability:
            # Fetch additional accountability metrics
            from datetime import timedelta

            # Get completed tasks this month
            month_start = today.replace(day=1)
            completed_this_month = db.query(Task).filter(
                Task.owner_id == user_id,
                Task.status == 'completed',
                Task.updated_at >= month_start
            ).count()

            # Get total tasks assigned this month
            total_tasks_this_month = db.query(Task).filter(
                Task.owner_id == user_id,
                Task.created_at >= month_start
            ).count()

            # Calculate task completion rate
            completion_rate = (completed_this_month / total_tasks_this_month * 100) if total_tasks_this_month > 0 else 0

            # Get leads that have progressed stages this month
            leads_progressed = 0
            leads_stalled = 0
            stalled_lead_names = []
            seven_days_ago = today - timedelta(days=7)

            for lead in all_leads:
                if lead.updated_at and lead.updated_at.date() < seven_days_ago:
                    leads_stalled += 1
                    if len(stalled_lead_names) < 5:
                        stalled_lead_names.append(lead.name or "Unknown")
                elif lead.updated_at and lead.updated_at.date() >= month_start:
                    leads_progressed += 1

            # Get overdue task count
            overdue_count = len([t for t in all_tasks if t.due_date and t.due_date.date() < today])

            system += f"""

=== COACHING MODE: ACCOUNTABILITY REVIEW ===
The user wants honest performance feedback. You MUST include these specific metrics:

TASK PERFORMANCE:
- Tasks Completed This Month: {completed_this_month}
- Total Tasks This Month: {total_tasks_this_month}
- Completion Rate: {completion_rate:.0f}%
- Overdue Tasks: {overdue_count}

LEAD MANAGEMENT:
- Total Leads: {total_leads}
- Leads Progressed This Month: {leads_progressed}
- Leads Stalled (no activity 7+ days): {leads_stalled}
{f'- Stalled Leads: {", ".join(stalled_lead_names)}' if stalled_lead_names else ''}

PIPELINE STATUS:
- Active Loans: {total_loans}
- Pipeline Value: ${total_pipeline_value:,.0f}

Structure your response as:

**Performance Summary**
- Start with overall assessment (Good/Needs Improvement/Critical)
- Use the exact metrics above

**What's Working**
- Highlight positive metrics (completion rate > 70%, leads progressing, etc.)

**Areas Needing Attention**
- Call out low completion rates, overdue tasks, stalled leads BY NAME
- Be specific with numbers - don't soften the truth

**Action Items**
- List 3-5 specific actions they should take THIS WEEK
- Prioritize by impact

Be honest and direct - they asked for accountability. If the metrics are poor, say so clearly.
=== END COACHING MODE ===
"""
        elif is_tough_love:
            system += """

=== COACHING MODE: TOUGH LOVE ===
The user wants you to be DIRECT about inefficiencies. Structure your response as:
1. No sugar-coating - call out exactly what's not working
2. Point to specific leads, deals, or tasks that are being neglected
3. Highlight patterns of behavior that are hurting results
4. Be blunt about the cost of inaction (lost revenue, missed opportunities)
5. End with "Here's what you need to do TODAY"
They asked for tough love - deliver it respectfully but firmly.
=== END COACHING MODE ===
"""
        elif is_teach_process:
            system += """

=== COACHING MODE: TEACH ME THE PROCESS ===
The user wants to learn systemic thinking. Structure your response as:
1. Explain the optimal workflow for their current situation
2. Show how different pipeline stages connect
3. Teach them to identify leading vs lagging indicators
4. Provide frameworks they can apply repeatedly
5. Use their actual data as examples
This is educational - help them build better habits, not just solve today's problem.
=== END COACHING MODE ===
"""

    # ADD COMPLETE CRM DATA CONTEXT
    if crm_context:
        system += "\n\n=== COMPLETE CRM DATA (You have full access to all this data) ===\n"
        system += CRMContextService.format_complete_context_for_claude(crm_context)

        # Add detailed data for specific queries
        leads = crm_context.get("leads", {})
        if leads.get("recent_leads"):
            system += "\n\nDETAILED LEAD DATA:\n"
            for lead in leads["recent_leads"][:20]:
                system += f"- {lead['name']} | {lead['status']} | {lead.get('loan_type', 'N/A')} | ${lead.get('loan_amount', 0):,.0f} | {lead.get('email', 'N/A')}\n"

        loans = crm_context.get("loans", {})
        if loans.get("recent_loans"):
            system += "\n\nDETAILED LOAN/DEAL DATA:\n"
            for loan in loans["recent_loans"][:20]:
                system += f"- {loan['borrower_name']} | {loan['stage']} | {loan.get('loan_type', 'N/A')} | ${loan.get('loan_amount', 0):,.0f} | {loan.get('property_address', 'N/A')}\n"

        tasks = crm_context.get("tasks", {})
        if tasks.get("todays_tasks"):
            system += "\n\nTODAY'S TASKS:\n"
            for task in tasks["todays_tasks"]:
                system += f"- [{task.get('priority', 'N/A')}] {task['title']} | {task.get('status', 'N/A')}\n"

        mum = crm_context.get("mum_clients", {})
        if mum.get("clients"):
            system += "\n\nMUM CLIENTS:\n"
            for client in mum["clients"][:15]:
                system += f"- {client['name']} | ${client.get('loan_amount', 0):,.0f} | {client.get('interest_rate', 0)}% | Next review: {client.get('next_review_date', 'N/A')}\n"

        partners = crm_context.get("referral_partners", {})
        if partners.get("partners"):
            system += "\n\nREFERRAL PARTNER PERFORMANCE:\n"

            # Highlight most profitable first
            most_profitable = partners.get("most_profitable")
            if most_profitable:
                system += f"*** MOST PROFITABLE: {most_profitable['name']} - ${most_profitable['revenue']:,.0f} from {most_profitable['deals']} closed deals ***\n\n"

            system += "All Partners (ranked by revenue):\n"
            for i, partner in enumerate(partners["partners"][:10], 1):
                system += f"{i}. {partner['name']}"
                if partner.get('company'):
                    system += f" ({partner['company']})"
                system += f"\n   - Total Leads: {partner.get('total_leads', 0)}\n"
                system += f"   - Closed Deals: {partner.get('closed_deals', 0)}\n"
                system += f"   - Total Revenue: ${partner.get('total_revenue', 0):,.0f}\n"
                system += f"   - Avg Deal Size: ${partner.get('avg_deal_size', 0):,.0f}\n"
                system += f"   - Close Rate: {partner.get('close_rate_pct', 0):.0f}%\n\n"

        system += "\n=== END CRM DATA ===\n"

    # ADD PATTERN ANALYSIS & INSIGHTS
    try:
        patterns = PatternAnalyzer.analyze_user_patterns(db, user_id)
        if patterns:
            system += PatternAnalyzer.format_patterns_for_claude(patterns)
    except Exception as e:
        logger.warning(f"Failed to add pattern analysis: {e}")

    # ADD PERMANENT MEMORY CONTEXT
    if total_messages > 0:
        system += f"""

PERMANENT MEMORY STATUS:
- You have had {total_messages} total messages with this user
- You have COMPLETE MEMORY of everything we've discussed
- When user references "yesterday", "last week", or past conversations, check the context below
- ALWAYS use your memory - never claim to not remember something from our history
"""

    # Add relevant past conversations if available
    if relevant_past and len(relevant_past) > 0:
        system += "\n\nRELEVANT PAST CONVERSATIONS (from your permanent memory):\n"
        for msg in relevant_past:
            content_preview = msg.get('content', '')[:300]
            system += f"[{msg.get('timestamp', 'unknown')}] {msg.get('role', 'unknown')}: {content_preview}...\n"

    # Add action context
    if action_context:
        action_summary = "\n\nRECENT ACTIONS IN THIS CONVERSATION:\n"
        for action_id, action_data in action_context.items():
            intent = action_data.get('intent', 'unknown')
            status = action_data.get('status', 'unknown')
            preview = action_data.get('preview', {})
            action_summary += f"- Action {action_id}: {intent} ({status})\n"
            if preview:
                if intent == 'EMAIL_CAMPAIGN':
                    action_summary += f"  Subject: {preview.get('subject', 'N/A')}\n"
                    action_summary += f"  Body: {preview.get('body', 'N/A')[:200]}...\n"
                elif intent == 'BULK_UPDATE':
                    action_summary += f"  Field: {preview.get('field', 'N/A')}, Count: {preview.get('count', 'N/A')}\n"
        system += action_summary

    # Check circuit breaker before making AI call
    if not ai_circuit_breaker.can_execute():
        logger.warning("AI Circuit breaker is OPEN - using fallback")
        return ai_circuit_breaker.get_fallback()

    start_time = time.time()
    function_calls_made = 0

    try:
        # Log the request
        logger.info(f"AI Request - User ID: {user_id}, Message: {message[:100]}...")

        response = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=AI_CONFIG["max_tokens"],
            temperature=AI_CONFIG["temperature"],  # Deterministic responses
            system=system,
            messages=messages
        )

        # Log the response
        logger.info(f"AI Response - Stop reason: {response.stop_reason}")

        # Record success in circuit breaker
        ai_circuit_breaker.record_success()

        # Parse Claude's response
        response_text = response.content[0].text
        logger.info(f"AI Response text preview: {response_text[:200]}...")

        # Try to extract JSON from the response
        try:
            # Find JSON in the response
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                result = json.loads(json_str)

                # OVERRIDE INTENT FOR COACHING MODES
                # Force DAILY_VIEW for coaching prompts regardless of Claude's classification
                message_lower = message.lower()
                coaching_keywords = [
                    "daily briefing", "top 3 priorities",
                    "pipeline audit", "bottlenecks", "stalled deals",
                    "focus reset", "back on track", "get focused",
                    "what should i do next", "priority decision",
                    "accountability review", "review my performance",
                    "tough love", "inefficiencies", "call out",
                    "teach me the process", "systemic thinking"
                ]
                is_coaching = any(keyword in message_lower for keyword in coaching_keywords)

                if is_coaching and result.get("intent") != "DAILY_VIEW":
                    logger.info(f"Overriding intent from {result.get('intent')} to DAILY_VIEW for coaching prompt")
                    result["intent"] = "DAILY_VIEW"

                # INJECT REAL CRM DATA for DAILY_VIEW
                if result.get("intent") == "DAILY_VIEW":
                    daily_data = get_daily_summary(db, user_id)
                    # Merge Claude's response with actual CRM data
                    if "data" not in result:
                        result["data"] = {}
                    result["data"]["tasks"] = daily_data.get("tasks", [])
                    result["data"]["follow_ups"] = daily_data.get("follow_ups", [])
                    result["data"]["reconciliations"] = daily_data.get("reconciliations", [])
                    # Use Claude's summary if it has better formatting, but include all our data
                    if "summary" in result["data"]:
                        result["data"]["summary"].update({
                            "lead_status_breakdown": daily_data["summary"].get("lead_status_breakdown", {}),
                            "loan_stage_breakdown": daily_data["summary"].get("loan_stage_breakdown", {}),
                            "unread_messages": daily_data["summary"].get("unread_messages", 0),
                            "mum_clients": daily_data["summary"].get("mum_clients", 0),
                        })
                    else:
                        result["data"]["summary"] = daily_data.get("summary", {})

                    # VALIDATION: Check for placeholder values in AI response
                    actual_leads = daily_data["summary"].get("active_leads", 0)
                    actual_loans = daily_data["summary"].get("loans_in_pipeline", 0)
                    actual_tasks = daily_data["summary"].get("total_tasks", 0)
                    actual_overdue = daily_data["summary"].get("overdue_tasks", 0)
                    explanation = result.get("explanation", "").lower()

                    # Check for incorrect "no tasks" messaging
                    no_tasks_phrases = ["no tasks", "currently have no tasks", "have no tasks", "0 tasks", "no outstanding tasks"]
                    has_incorrect_no_tasks = any(phrase in explanation for phrase in no_tasks_phrases)

                    if has_incorrect_no_tasks and actual_tasks > 0:
                        logger.warning(f"AI said 'no tasks' but actual count is {actual_tasks} (overdue: {actual_overdue})")
                        # Build correct task summary
                        task_summary = f"You have {actual_tasks} outstanding tasks"
                        if actual_overdue > 0:
                            task_summary = f"You have {actual_overdue} overdue tasks that need immediate attention"

                        # Get first few tasks to show
                        task_items = daily_data.get("tasks", [])[:3]
                        task_list_text = "\n\n**Top Priority Tasks:**\n"
                        for task in task_items:
                            task_list_text += f"- [{task.get('priority', 'N/A')}] {task.get('title', 'Untitled')}\n"

                        result["explanation"] = f"{task_summary}.{task_list_text}\n\nWould you like me to help you prioritize or create a schedule for these tasks?"

                    if "0 active leads" in explanation and actual_leads > 0:
                        logger.warning(f"AI returned placeholder '0 leads' but actual count is {actual_leads}")
                        # Override the explanation with correct data
                        result["explanation"] = f"Here's your daily overview. You have {actual_leads} active leads and {actual_loans} loans in pipeline ({daily_data['summary'].get('pipeline_volume', '$0')})."

                    if "0 loans in pipeline" in explanation and actual_loans > 0:
                        logger.warning(f"AI returned placeholder '0 loans' but actual count is {actual_loans}")

                    logger.info(f"DAILY_VIEW response validated - Leads: {actual_leads}, Loans: {actual_loans}, Tasks: {actual_tasks}")

                # INJECT QUERY RESULTS for ANALYTICAL_QUERY
                if result.get("intent") == "ANALYTICAL_QUERY":
                    query_type = result.get("data", {}).get("query_type", "")
                    params = result.get("data", {}).get("params", {})

                    if query_type:
                        query_result = execute_analytical_query(db, user_id, query_type, params)
                        result["data"]["query_result"] = query_result
                        # Append formatted results to explanation
                        if query_result.get("success"):
                            result["explanation"] += "\n\n" + query_result.get("formatted_text", "")
                        logger.info(f"ANALYTICAL_QUERY executed: {query_type}, success={query_result.get('success')}")

                # INJECT MARKET DATA for MARKET_INTELLIGENCE
                if result.get("intent") == "MARKET_INTELLIGENCE":
                    lock_days = result.get("data", {}).get("lock_days", 30)
                    market_data = get_market_intelligence(lock_days)
                    result["data"]["market_data"] = market_data

                    # Format market data for explanation
                    rates = market_data.get("current_rates", {})
                    conditions = market_data.get("market_conditions", {})
                    recommendation = market_data.get("rate_lock_recommendation", {})

                    market_summary = f"""

**Current Market Conditions:**
- 30-Year Fixed: {rates.get('30yr_fixed', 'N/A')}%
- 15-Year Fixed: {rates.get('15yr_fixed', 'N/A')}%
- 10-Year Treasury: {market_data.get('treasury_yields', {}).get('10yr', 'N/A')}%
- Market Volatility: {conditions.get('volatility', 'Unknown')} (VIX: {conditions.get('vix', 'N/A')})
- Market Score: {conditions.get('market_score', 'N/A')}/100

**Rate Lock Recommendation: {recommendation.get('overall', 'CAUTIOUS')}**

{recommendation.get('guidance', '')}
"""
                    result["explanation"] += market_summary
                    logger.info(f"MARKET_INTELLIGENCE executed: lock_days={lock_days}, recommendation={recommendation.get('overall')}")

                # Log metrics for successful response
                execution_time = (time.time() - start_time) * 1000
                AIMetrics.log_interaction(
                    user_id=user_id,
                    request_message=message,
                    response=result,
                    execution_time_ms=execution_time,
                    success=True,
                    function_calls_made=function_calls_made
                )

                return result
        except json.JSONDecodeError:
            pass

        # If no JSON found, create a general response
        result = {
            "intent": "GENERAL_QUERY",
            "explanation": response_text,
            "data": {}
        }

        # Log metrics
        execution_time = (time.time() - start_time) * 1000
        AIMetrics.log_interaction(
            user_id=user_id,
            request_message=message,
            response=result,
            execution_time_ms=execution_time,
            success=True,
            function_calls_made=function_calls_made
        )

        return result

    except Exception as e:
        # Record failure in circuit breaker
        ai_circuit_breaker.record_failure()

        # Log metrics for failed response
        execution_time = (time.time() - start_time) * 1000
        AIMetrics.log_interaction(
            user_id=user_id,
            request_message=message,
            response={"intent": "ERROR"},
            execution_time_ms=execution_time,
            success=False,
            error=str(e)
        )

        logger.error(f"Claude API error: {str(e)}")
        return generate_mock_response(message, db, user_id)


def generate_mock_response(message: str, db: Session, user_id: int) -> Dict[str, Any]:
    """Generate a mock response for demo purposes"""
    main = get_main_module()
    Lead = main.Lead

    message_lower = message.lower()

    if "today" in message_lower or "daily" in message_lower or "morning" in message_lower:
        summary = get_daily_summary(db, user_id)
        return {
            "intent": "DAILY_VIEW",
            "explanation": "Here's your daily overview:",
            "data": summary
        }

    elif "email" in message_lower or "send" in message_lower:
        # Get some sample clients
        clients = db.query(Lead).filter(Lead.user_id == user_id).limit(5).all()
        return {
            "intent": "EMAIL_CAMPAIGN",
            "explanation": "I'll prepare an email campaign for you.",
            "preview": {
                "recipients": [f"{c.first_name} {c.last_name}" for c in clients],
                "count": len(clients),
                "subject": "Important Update from Your Mortgage Team",
                "body": "Dear Client,\n\nWe wanted to reach out with some important information about your loan.\n\nBest regards,\nYour Mortgage Team"
            }
        }

    elif "search" in message_lower or "find" in message_lower:
        # Extract search term (simple approach)
        words = message.split()
        search_term = words[-1] if len(words) > 1 else "client"
        results = search_records(db, user_id, search_term)
        return {
            "intent": "SEARCH",
            "explanation": f"Here are the search results for '{search_term}':",
            "data": results
        }

    elif "report" in message_lower or "pipeline" in message_lower:
        return {
            "intent": "PIPELINE_REPORT",
            "explanation": "I'll generate a pipeline report for you.",
            "preview": {
                "report_type": "Pipeline Analysis",
                "date_range": "Last 30 days",
                "metrics": ["Total Loans", "Conversion Rate", "Average Loan Size", "Stage Distribution"]
            }
        }

    elif "voicemail" in message_lower:
        clients = db.query(Lead).filter(Lead.user_id == user_id).limit(3).all()
        return {
            "intent": "VOICEMAIL_DROP",
            "explanation": "I'll set up a ringless voicemail campaign.",
            "preview": {
                "recipients": [f"{c.first_name} {c.last_name}" for c in clients],
                "script": "Hi, this is a quick message from your mortgage team. We have some important updates about current rates. Please call us back at your convenience.",
                "scheduled_time": "Immediately"
            }
        }

    else:
        return {
            "intent": "GENERAL_QUERY",
            "explanation": f"I understand you're asking about: {message}. How can I help you further?",
            "data": {}
        }


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("/process-command", response_model=AICommandResponse)
async def process_command(
    request: AICommandRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dependency)
):
    """
    Process a natural language command and return intent with preview.
    """
    # Get current user ID from authenticated user
    if not current_user or not hasattr(current_user, 'id'):
        raise HTTPException(status_code=401, detail="Authentication required")
    current_user_id = current_user.id

    # Get or create session ID for permanent memory
    session_id = request.session_id or str(uuid.uuid4())

    try:
        # 1. SAVE USER MESSAGE TO PERMANENT MEMORY
        try:
            ConversationMemory.save_message(
                db=db,
                user_id=current_user_id,
                session_id=session_id,
                role='user',
                content=request.message
            )
        except Exception as mem_error:
            logger.warning(f"Failed to save user message to memory: {mem_error}")

        # 2. GET FULL CONTEXT FROM PERMANENT MEMORY
        context = ConversationMemory.get_full_context(
            db=db,
            user_id=current_user_id,
            current_message=request.message
        )

        # 3. GET FULL CRM DATA CONTEXT (with Redis caching for performance)
        crm_context = await CRMContextService.get_full_crm_context_cached(db, current_user_id)

        # 4. BUILD ENHANCED CONTEXT FOR CLAUDE
        # Combine permanent memory with current session context
        combined_context = context['recent_messages'] if context['recent_messages'] else request.conversation_context

        # Process with Claude AI - pass full context including action history and CRM data
        result = await process_with_claude(
            request.message,
            combined_context,
            db,
            current_user_id,
            request.action_context,  # Include action context for memory
            context.get('relevant_past', []),
            context.get('total_messages', 0),
            crm_context  # Include full CRM data
        )

        # Generate action ID if this is an actionable command
        action_id = None
        if result.get("intent") in ["EMAIL_CAMPAIGN", "BULK_UPDATE", "VOICEMAIL_DROP"]:
            action_id = str(uuid.uuid4())
            # Cache the action for later execution
            action_cache[action_id] = {
                "intent": result["intent"],
                "preview": result.get("preview"),
                "user_id": current_user_id,
                "created_at": datetime.now().isoformat(),
                "session_id": session_id
            }

            # 4. SAVE ACTION TO PERMANENT MEMORY
            try:
                ConversationMemory.save_action(
                    db=db,
                    user_id=current_user_id,
                    action_id=action_id,
                    action_type=result["intent"],
                    preview_data=result.get("preview", {})
                )
            except Exception as action_error:
                logger.warning(f"Failed to save action to memory: {action_error}")

        # 5. SAVE ASSISTANT RESPONSE TO PERMANENT MEMORY
        try:
            ConversationMemory.save_message(
                db=db,
                user_id=current_user_id,
                session_id=session_id,
                role='assistant',
                content=result.get("explanation", ""),
                action_id=action_id,
                action_data=result.get("preview")
            )
        except Exception as mem_error:
            logger.warning(f"Failed to save assistant message to memory: {mem_error}")

        return AICommandResponse(
            intent=result.get("intent", "GENERAL_QUERY"),
            explanation=result.get("explanation", ""),
            preview=result.get("preview"),
            action_id=action_id,
            data=result.get("data"),
            session_id=session_id
        )

    except Exception as e:
        logger.error(f"Error processing command: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/execute-action", response_model=ActionExecuteResponse)
async def execute_action(
    request: ActionExecuteRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dependency)
):
    """
    Execute a previously previewed action.
    """
    # Require authenticated user
    if not current_user or not hasattr(current_user, 'id'):
        raise HTTPException(status_code=401, detail="Authentication required")
    current_user_id = current_user.id

    try:
        # Get cached action
        action_data = action_cache.get(request.action_id)
        if not action_data:
            raise HTTPException(status_code=404, detail="Action not found or expired")

        # Verify ownership
        if action_data["user_id"] != current_user_id:
            raise HTTPException(status_code=403, detail="Not authorized to execute this action")

        intent = action_data["intent"]
        preview = action_data.get("preview", {})
        modifications = request.modifications
        session_id = request.session_id or action_data.get("session_id")

        # Execute based on intent
        if intent == "EMAIL_CAMPAIGN":
            result = await execute_email_campaign(
                db, current_user_id, preview, modifications, background_tasks
            )
        elif intent == "BULK_UPDATE":
            result = await execute_bulk_update(
                db, current_user_id, preview, modifications
            )
        elif intent == "VOICEMAIL_DROP":
            result = await execute_voicemail_drop(
                db, current_user_id, preview, modifications, background_tasks
            )
        elif intent == "PRE_APPROVAL_LETTER":
            result = await execute_pre_approval_letter(
                db, current_user_id, preview, modifications, background_tasks
            )
        else:
            raise HTTPException(status_code=400, detail=f"Unknown action type: {intent}")

        # UPDATE ACTION STATUS IN PERMANENT MEMORY
        try:
            ConversationMemory.update_action_status(
                db=db,
                action_id=request.action_id,
                status='executed' if result.get('message') else 'failed',
                execution_data=result
            )
        except Exception as mem_error:
            logger.warning(f"Failed to update action status in memory: {mem_error}")

        # SAVE EXECUTION RESULT TO CONVERSATION
        if session_id:
            try:
                ConversationMemory.save_message(
                    db=db,
                    user_id=current_user_id,
                    session_id=session_id,
                    role='assistant',
                    content=f"Action executed: {result.get('message', 'Success')}"
                )
            except Exception as mem_error:
                logger.warning(f"Failed to save execution result to memory: {mem_error}")

        # Remove from cache after execution
        del action_cache[request.action_id]

        return ActionExecuteResponse(
            success=True,
            message=result.get("message", "Action executed successfully"),
            result=result
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing action: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# Action Executors
# ============================================================================

async def execute_email_campaign(
    db: Session,
    user_id: int,
    preview: Dict[str, Any],
    modifications: Dict[str, Any],
    background_tasks: BackgroundTasks
) -> Dict[str, Any]:
    """Execute an email campaign"""
    main = get_main_module()
    Lead = main.Lead
    Activity = main.Activity

    # Apply any modifications
    subject = modifications.get("subject", preview.get("subject", ""))
    body = modifications.get("body", preview.get("body", ""))
    recipients = preview.get("recipients", [])

    # In production, this would queue emails through your email service
    # For now, log the action and create activity records

    for recipient_name in recipients:
        # Find the lead
        names = recipient_name.split()
        if len(names) >= 2:
            lead = db.query(Lead).filter(
                Lead.user_id == user_id,
                Lead.first_name == names[0],
                Lead.last_name == names[-1]
            ).first()

            if lead:
                # Create activity record
                activity = Activity(
                    user_id=user_id,
                    lead_id=lead.id,
                    activity_type="email",
                    description=f"Email sent: {subject}",
                    data={"subject": subject, "body": body[:500]}
                )
                db.add(activity)

    db.commit()

    return {
        "message": f"Email campaign sent to {len(recipients)} recipients",
        "recipients_count": len(recipients),
        "subject": subject
    }


async def execute_bulk_update(
    db: Session,
    user_id: int,
    preview: Dict[str, Any],
    modifications: Dict[str, Any]
) -> Dict[str, Any]:
    """Execute a bulk update operation"""
    main = get_main_module()
    Lead = main.Lead
    Deal = main.Deal

    records = preview.get("records", [])
    field = modifications.get("field", preview.get("field", ""))
    new_value = modifications.get("new_value", preview.get("new_value", ""))

    updated_count = 0
    _protected_lead = {'id', 'organization_id', 'created_at', 'updated_at', 'owner_id'}
    _protected_deal = {'id', 'organization_id', 'created_at', 'updated_at'}

    for record in records:
        record_id = record.get("id")
        record_type = record.get("type", "lead")

        if record_type == "lead":
            lead = db.query(Lead).filter(
                Lead.id == record_id,
                Lead.user_id == user_id
            ).first()

            if lead and hasattr(lead, field) and field not in _protected_lead:
                setattr(lead, field, new_value)
                updated_count += 1

        elif record_type == "deal":
            deal = db.query(Deal).filter(
                Deal.id == record_id,
                Deal.user_id == user_id
            ).first()

            if deal and hasattr(deal, field) and field not in _protected_deal:
                setattr(deal, field, new_value)
                updated_count += 1

    db.commit()

    return {
        "message": f"Updated {updated_count} records",
        "updated_count": updated_count,
        "field": field,
        "new_value": new_value
    }


async def execute_voicemail_drop(
    db: Session,
    user_id: int,
    preview: Dict[str, Any],
    modifications: Dict[str, Any],
    background_tasks: BackgroundTasks
) -> Dict[str, Any]:
    """Execute a voicemail drop campaign"""
    main = get_main_module()
    Lead = main.Lead
    Activity = main.Activity

    script = modifications.get("script", preview.get("script", ""))
    recipients = preview.get("recipients", [])

    # In production, this would integrate with a service like Slybroadcast
    # For now, create activity records

    for recipient_name in recipients:
        names = recipient_name.split()
        if len(names) >= 2:
            lead = db.query(Lead).filter(
                Lead.user_id == user_id,
                Lead.first_name == names[0],
                Lead.last_name == names[-1]
            ).first()

            if lead:
                activity = Activity(
                    user_id=user_id,
                    lead_id=lead.id,
                    activity_type="voicemail",
                    description="Ringless voicemail sent",
                    data={"script": script[:500]}
                )
                db.add(activity)

    db.commit()

    return {
        "message": f"Voicemail campaign queued for {len(recipients)} recipients",
        "recipients_count": len(recipients),
        "status": "queued"
    }


async def execute_pre_approval_letter(
    db: Session,
    user_id: int,
    preview: Dict[str, Any],
    modifications: Dict[str, Any],
    background_tasks: BackgroundTasks
) -> Dict[str, Any]:
    """Execute sending a pre-approval letter via email with PDF attachment"""
    from routes.pre_approval_letter_settings_routes import (
        generate_pre_approval_letter_pdf,
        PreApprovalLetterSettings
    )
    from email_service import email_service

    main = get_main_module()
    Lead = main.Lead
    Activity = main.Activity
    User = main.User

    # Apply modifications to preview data
    borrower_names = modifications.get("borrower_names", preview.get("borrower_names", ""))
    property_address = modifications.get("property_address", preview.get("property_address", "To Be Determined"))
    loan_amount = modifications.get("loan_amount", preview.get("loan_amount", 0))
    loan_type = modifications.get("loan_type", preview.get("loan_type", "Conventional"))
    recipient_email = modifications.get("recipient_email", preview.get("recipient_email", ""))
    interest_rate = modifications.get("interest_rate", preview.get("interest_rate"))
    expiration_days = modifications.get("expiration_days", preview.get("expiration_days", 90))
    lead_id = modifications.get("lead_id", preview.get("lead_id"))

    # Get user/loan officer details
    user = db.query(User).filter(User.id == user_id).first()
    lo_name = f"{user.first_name} {user.last_name}" if user else "Loan Officer"
    lo_nmls = getattr(user, 'nmls_id', '') or ''
    lo_email = user.email if user else ''
    lo_phone = getattr(user, 'phone', '') or ''

    # Get or create settings (use defaults if not configured)
    settings = db.query(PreApprovalLetterSettings).filter(
        PreApprovalLetterSettings.user_id == user_id
    ).first()

    if not settings:
        # Create default settings
        settings = PreApprovalLetterSettings(
            user_id=user_id,
            company_name="Perennia Mortgage",
            company_address="123 Main Street, San Francisco, CA 94105",
            company_phone="(555) 123-4567",
            company_nmls="123456",
            logo_url=None,
            letter_template="standard",
            default_conditions=[
                "Verification of employment and income",
                "Satisfactory appraisal of the subject property",
                "Clear title and title insurance",
                "Verification of assets and funds to close"
            ],
            signature_name=lo_name,
            signature_title="Loan Officer",
            signature_nmls=lo_nmls,
            signature_phone=lo_phone,
            signature_email=lo_email,
            include_disclaimer=True
        )

    # Calculate expiration date
    from datetime import datetime, timedelta
    expiration_date = datetime.now() + timedelta(days=expiration_days)

    # Build sample data for PDF generation
    sample_data = {
        "borrower_names": borrower_names,
        "property_address": property_address,
        "loan_amount": f"${loan_amount:,.2f}" if isinstance(loan_amount, (int, float)) else str(loan_amount),
        "loan_type": loan_type,
        "interest_rate": f"{interest_rate}%" if interest_rate else "Market Rate",
        "expiration_date": expiration_date.strftime("%B %d, %Y"),
        "date_issued": datetime.now().strftime("%B %d, %Y")
    }

    try:
        # Generate PDF
        pdf_bytes = generate_pre_approval_letter_pdf(settings, sample_data)

        # Create filename
        borrower_filename = borrower_names.replace(" ", "_").replace(",", "")
        pdf_filename = f"Pre_Approval_Letter_{borrower_filename}.pdf"

        # Create email content
        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <p>Please find attached the pre-approval letter for <strong>{borrower_names}</strong>.</p>

            <p><strong>Loan Details:</strong></p>
            <ul>
                <li>Loan Amount: {sample_data['loan_amount']}</li>
                <li>Loan Type: {loan_type}</li>
                <li>Property: {property_address}</li>
                <li>Valid Until: {sample_data['expiration_date']}</li>
            </ul>

            <p>Please don't hesitate to reach out if you have any questions.</p>

            <p>Best regards,<br>
            {lo_name}<br>
            {settings.signature_title or 'Loan Officer'}<br>
            NMLS# {lo_nmls or settings.signature_nmls or 'N/A'}<br>
            {lo_phone or settings.signature_phone or ''}<br>
            {lo_email or settings.signature_email or ''}</p>
        </body>
        </html>
        """

        plain_text = f"""
Pre-Approval Letter for {borrower_names}

Loan Details:
- Loan Amount: {sample_data['loan_amount']}
- Loan Type: {loan_type}
- Property: {property_address}
- Valid Until: {sample_data['expiration_date']}

Please find the pre-approval letter attached.

Best regards,
{lo_name}
{settings.signature_title or 'Loan Officer'}
NMLS# {lo_nmls or settings.signature_nmls or 'N/A'}
        """

        # Create attachment
        attachments = [{
            'content': pdf_bytes,
            'filename': pdf_filename,
            'type': 'application/pdf'
        }]

        # Send email (SF routing skips automatically when attachments present)
        success = await email_service.send_html_email_sf(
            to_email=recipient_email,
            subject=f"Pre-Approval Letter - {borrower_names}",
            html_body=html_content,
            plain_text_body=plain_text,
            attachments=attachments,
            db=db,
            user_id=user_id,
        )

        if not success:
            return {
                "success": False,
                "message": "Failed to send pre-approval letter email",
                "error": "Email service returned failure"
            }

        # Create activity record if we have a lead
        if lead_id:
            lead = db.query(Lead).filter(Lead.id == lead_id, Lead.user_id == user_id).first()
            if lead:
                activity = Activity(
                    user_id=user_id,
                    lead_id=lead_id,
                    activity_type="pre_approval_letter",
                    description=f"Pre-approval letter sent to {recipient_email}",
                    data={
                        "borrower_names": borrower_names,
                        "loan_amount": loan_amount,
                        "loan_type": loan_type,
                        "recipient_email": recipient_email,
                        "expiration_date": sample_data['expiration_date']
                    }
                )
                db.add(activity)
                db.commit()

        return {
            "success": True,
            "message": f"Pre-approval letter sent successfully to {recipient_email}",
            "details": {
                "borrower": borrower_names,
                "loan_amount": sample_data['loan_amount'],
                "loan_type": loan_type,
                "sent_to": recipient_email,
                "valid_until": sample_data['expiration_date']
            }
        }

    except Exception as e:
        logger.error(f"Failed to generate/send pre-approval letter: {e}")
        return {
            "success": False,
            "message": "Failed to send pre-approval letter",
            "error": "Internal server error"
        }


# ============================================================================
# Email Daily Priorities Report
# ============================================================================

class SendEmailRequest(BaseModel):
    email_address: Optional[str] = None

@router.post("/send-daily-priorities-email")
async def send_daily_priorities_email(
    request: SendEmailRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dependency)
):
    """
    Send daily priorities report to specified email address
    """
    from email_service import email_service
    from query_executor import QueryExecutor

    # Require authenticated user
    if not current_user or not hasattr(current_user, 'id'):
        raise HTTPException(status_code=401, detail="Authentication required")
    current_user_id = current_user.id
    user_name = f"{current_user.first_name} {current_user.last_name}" if hasattr(current_user, 'first_name') else "User"
    user_email = current_user.email if hasattr(current_user, 'email') else ""

    # Use provided email or fallback to user's email
    to_email = request.email_address or user_email
    if not to_email:
        raise HTTPException(status_code=400, detail="No email address provided")

    try:
        # Execute the daily_focus_priorities query
        priorities = QueryExecutor.execute_query(
            db=db,
            query_type="daily_focus_priorities",
            params={},
            user_id=current_user_id
        )

        logger.info(f"Query result for user {current_user_id}: success={priorities.get('success') if priorities else None}, data_count={len(priorities.get('data', [])) if priorities else 0}")

        if not priorities or not isinstance(priorities, dict) or not priorities.get("data"):
            logger.warning(f"No priorities data found. priorities={priorities}")
            raise HTTPException(status_code=404, detail=f"No priorities data found for user {current_user_id}. Query returned: {len(priorities.get('data', [])) if priorities and isinstance(priorities, dict) else 0} items")

        priorities_data = priorities.get("data", [])

        # If data is empty list, still send email with empty message
        if not priorities_data or len(priorities_data) == 0:
            logger.info(f"No priority items for user {current_user_id}, sending empty report")
            # Create a placeholder message
            priorities_data = [{
                "type": "message",
                "title": "No pending tasks or urgent loans at this time",
                "priority_score": 0,
                "urgency_label": "All Clear"
            }]

        # Send the email
        success = email_service.send_daily_priorities_report(
            to_email=to_email,
            user_name=user_name,
            priorities=priorities_data
        )

        if success:
            return {
                "success": True,
                "message": f"Daily priorities report sent to {to_email}",
                "email": to_email,
                "items_count": len(priorities_data)
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to send email. Please check SMTP configuration."
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending daily priorities email: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to send email")


# ============================================================================
# Screenshot Parsing Models
# ============================================================================

class ScreenshotLeadData(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    referral_source: Optional[str] = None
    property_address: Optional[str] = None
    loan_type: Optional[str] = None
    loan_amount: Optional[float] = None
    notes: Optional[str] = None


class CreateLeadFromScreenshotRequest(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    referral_source: Optional[str] = None
    property_address: Optional[str] = None
    loan_type: Optional[str] = None
    loan_amount: Optional[float] = None
    notes: Optional[str] = None


# ============================================================================
# Screenshot Parsing Endpoints
# ============================================================================

@router.post("/parse-screenshot-upload")
async def parse_screenshot_upload(
    image: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Parse a screenshot image (file upload) to extract lead information using Claude's vision.
    For JSON base64 input, use /parse-screenshot instead.
    """
    if not anthropic_client:
        raise HTTPException(status_code=500, detail="AI service not configured")

    # Validate file type
    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    try:
        # Read and encode the image
        image_data = await image.read()
        base64_image = base64.standard_b64encode(image_data).decode("utf-8")

        # Determine media type
        media_type = image.content_type or "image/jpeg"

        # Create the prompt for Claude to extract lead information
        extraction_prompt = """Analyze this screenshot which appears to be a text message or email introducing a lead from a realtor or referral partner.

Extract the following information if present:
- First Name
- Last Name
- Email
- Phone Number
- Referral Source (who sent the introduction - the realtor/partner name and company)
- Property Address (if mentioned)
- Loan Type (purchase, refinance, etc.)
- Loan Amount (if mentioned)
- Any additional notes or context

Return the information as a JSON object with these fields:
{
    "first_name": "",
    "last_name": "",
    "email": "",
    "phone": "",
    "referral_source": "",
    "property_address": "",
    "loan_type": "",
    "loan_amount": null,
    "notes": ""
}

Only include fields where you can extract actual data from the image. Leave fields empty or null if the information is not present.
Format phone numbers as (XXX) XXX-XXXX if possible.
For loan_amount, extract just the numeric value (no $ or commas).

Return ONLY the JSON object, no additional text."""

        # Call Claude with vision
        response = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": base64_image
                            }
                        },
                        {
                            "type": "text",
                            "text": extraction_prompt
                        }
                    ]
                }
            ]
        )

        # Parse the response
        response_text = response.content[0].text

        # Extract JSON from response
        try:
            # Find JSON in the response
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                lead_data = json.loads(json_str)

                # Check if we got any meaningful data
                has_data = any([
                    lead_data.get("first_name"),
                    lead_data.get("last_name"),
                    lead_data.get("email"),
                    lead_data.get("phone")
                ])

                if has_data:
                    return {
                        "success": True,
                        "lead_data": lead_data,
                        "message": "Successfully extracted lead information from screenshot"
                    }
                else:
                    return {
                        "success": False,
                        "lead_data": None,
                        "message": "Could not find lead information in the screenshot. Please ensure the image contains contact details."
                    }
            else:
                return {
                    "success": False,
                    "lead_data": None,
                    "message": "Could not parse the image. Please try a clearer screenshot."
                }

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from Claude response: {e}")
            return {
                "success": False,
                "lead_data": None,
                "message": "Failed to extract structured data from the screenshot."
            }

    except Exception as e:
        logger.error(f"Error parsing screenshot: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to process screenshot")


@router.post("/create-lead-from-screenshot")
async def create_lead_from_screenshot(
    request: CreateLeadFromScreenshotRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dependency)
):
    """
    Create a new lead from parsed screenshot data.
    The lead will be created in the 'Attempted Contact' stage.
    """
    # Require authenticated user
    if not current_user or not hasattr(current_user, 'id'):
        raise HTTPException(status_code=401, detail="Authentication required")
    current_user_id = current_user.id

    main = get_main_module()
    Lead = main.Lead
    LeadStage = main.LeadStage

    try:
        # Construct the full name
        name = f"{request.first_name or ''} {request.last_name or ''}".strip()
        if not name:
            name = "Unknown"

        # Create the new lead
        new_lead = Lead(
            owner_id=current_user_id,
            name=name,
            email=request.email,
            phone=request.phone,
            source=request.referral_source or "Realtor Referral",
            stage=LeadStage.ATTEMPTED_CONTACT,  # Set to Attempted Contact stage
            loan_type=request.loan_type,
            preapproval_amount=request.loan_amount,
            notes=request.notes,
            property_address=request.property_address if hasattr(Lead, 'property_address') else None
        )

        db.add(new_lead)
        db.commit()
        db.refresh(new_lead)

        logger.info(f"Created lead from screenshot: {new_lead.id} - {new_lead.name}")

        return {
            "success": True,
            "message": f"Lead '{new_lead.name}' created successfully in Attempted Contact stage",
            "lead_id": new_lead.id,
            "lead_name": new_lead.name
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Error creating lead from screenshot: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create lead")


# ============================================================================
# AI Email Generation & Sending
# ============================================================================

class EmailGenerateRequest(BaseModel):
    """Request model for generating AI email content"""
    template_id: str
    template_name: str
    recipient_name: str
    recipient_email: Optional[str] = None
    entity_type: str  # 'lead', 'loan', 'mum', 'contact'
    entity_data: Optional[Dict[str, Any]] = {}


class EmailSendRequest(BaseModel):
    """Request model for sending composed email"""
    to_email: str
    to_name: Optional[str] = ""
    subject: str
    body: str
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    template_used: Optional[str] = None


# Email template prompts for AI generation
EMAIL_TEMPLATE_PROMPTS = {
    # Lead Nurturing
    "initial_followup": "Write a warm, professional initial follow-up email to a potential home buyer who just submitted their information. Thank them for their interest, briefly introduce yourself, and offer to answer any questions about the mortgage process.",
    "rate_update": "Write an email notifying a lead about favorable rate changes in the market. Make it informative but not pushy, emphasizing the opportunity without pressure.",
    "checking_in": "Write a friendly check-in email to a lead asking about their home search progress. Be warm and supportive, offering assistance without being salesy.",
    "pre_approval_invitation": "Write an invitation email encouraging a lead to get pre-approved for a mortgage. Explain the benefits of pre-approval (stronger offers, knowing your budget) in a helpful way.",

    # Application Process
    "welcome_application": "Write a welcome email thanking the borrower for starting their mortgage application. Set expectations for the process and express excitement about helping them achieve homeownership.",
    "documents_needed": "Write a professional email requesting required documents from a borrower. List the typical documents needed (pay stubs, W-2s, bank statements, ID) and explain why each is important.",
    "documents_received": "Write a confirmation email acknowledging receipt of documents from a borrower. Thank them and let them know what happens next.",
    "application_complete": "Write a congratulatory email informing the borrower that their application is complete and being submitted for processing.",

    # Processing Updates
    "processing_started": "Write an update email informing the borrower that their loan is now in processing. Explain what this stage involves and set timeline expectations.",
    "appraisal_ordered": "Write an email notifying the borrower that their appraisal has been ordered. Explain what to expect and any preparation needed.",
    "appraisal_complete": "Write an email sharing that the appraisal is complete. Be positive and note that the loan is progressing.",
    "title_update": "Write a brief update email about title work progress on the loan.",

    # Underwriting
    "submitted_to_uw": "Write an email informing the borrower their loan has been submitted to underwriting. Explain this is a crucial review stage and what they can expect.",
    "conditional_approval": "Write an exciting email sharing the great news of conditional approval! Explain what conditions might be needed while keeping the tone celebratory.",
    "conditions_needed": "Write a professional email requesting additional items needed to satisfy underwriting conditions. Be clear about what's needed and why.",
    "final_approval": "Write a celebratory email announcing full loan approval! This is exciting news - the borrower is cleared for closing.",

    # Closing
    "clear_to_close": "Write an exciting email announcing 'Clear to Close' status. Explain what this means and next steps for scheduling closing.",
    "closing_scheduled": "Write a confirmation email with closing details - date, time, location, what to bring, and final preparation tips.",
    "closing_reminder": "Write a friendly reminder email about upcoming closing. Include what to bring and any last-minute checklist items.",
    "congratulations": "Write a warm congratulations email celebrating their successful closing! Welcome them to homeownership.",

    # Post-Closing
    "thank_you": "Write a heartfelt thank you email expressing gratitude for choosing to work with you. Offer to be a resource for future mortgage needs.",
    "referral_request": "Write a friendly email asking for referrals. Mention how much you enjoyed working with them and would love to help their friends/family.",
    "annual_review": "Write an email offering an annual mortgage checkup. Mention changes in rates or their equity situation that might benefit them.",
    "refinance_opportunity": "Write an informative email about potential refinance opportunities. Be helpful, not pushy, focusing on their potential savings.",

    # General
    "market_update": "Write an informative email sharing current mortgage market insights. Include rate trends and what it means for borrowers.",
    "holiday_greeting": "Write a warm holiday greeting email that's professional but personal. Express good wishes and gratitude.",
    "birthday": "Write a friendly birthday wishes email. Keep it personal and warm without being overly promotional.",
}


@router.post("/generate-email")
async def generate_ai_email(
    request: EmailGenerateRequest,
    authorization: str = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dependency)
):
    """Generate AI-powered email content based on template and recipient data"""
    try:
        # Require authenticated user
        if not current_user or not hasattr(current_user, 'id'):
            raise HTTPException(status_code=401, detail="Authentication required")

        current_user_data = {
            "id": current_user.id,
            "name": current_user.full_name if hasattr(current_user, 'full_name') else "Loan Officer",
            "email": current_user.email if hasattr(current_user, 'email') else "",
            "phone": getattr(current_user, 'phone', ''),
            "title": getattr(current_user, 'current_role', 'Loan Officer'),
            "nmls_id": getattr(current_user, 'nmls_number', '')
        }

        # Get the base prompt for this template
        template_prompt = EMAIL_TEMPLATE_PROMPTS.get(
            request.template_id,
            f"Write a professional mortgage-related email with the topic: {request.template_name}"
        )

        # Get user info for signature
        user_name = current_user_data.get("name", current_user_data.get("email", "Your Loan Officer"))
        user_email = current_user_data.get("email", "")
        user_phone = current_user_data.get("phone", "")
        user_title = current_user_data.get("title", "Loan Officer")
        user_nmls = current_user_data.get("nmls_id", "")

        # Build context about the recipient
        recipient_context = f"Recipient Name: {request.recipient_name}"
        if request.entity_data:
            if request.entity_type == "loan":
                if request.entity_data.get("amount"):
                    recipient_context += f"\nLoan Amount: ${request.entity_data['amount']:,.0f}"
                if request.entity_data.get("property_address"):
                    recipient_context += f"\nProperty: {request.entity_data['property_address']}"
                if request.entity_data.get("stage"):
                    recipient_context += f"\nCurrent Stage: {request.entity_data['stage']}"
                if request.entity_data.get("closing_date"):
                    recipient_context += f"\nClosing Date: {request.entity_data['closing_date']}"
            elif request.entity_type == "lead":
                if request.entity_data.get("source"):
                    recipient_context += f"\nLead Source: {request.entity_data['source']}"
                if request.entity_data.get("stage"):
                    recipient_context += f"\nLead Stage: {request.entity_data['stage']}"

        # Build the full prompt for Claude
        full_prompt = f"""You are a professional mortgage loan officer writing an email to a client/prospect.

TASK: {template_prompt}

RECIPIENT INFORMATION:
{recipient_context}

SENDER INFORMATION:
Name: {user_name}
Title: {user_title}
Email: {user_email}
Phone: {user_phone}
NMLS#: {user_nmls if user_nmls else "N/A"}

GUIDELINES:
1. Be professional but warm and personable
2. Use the recipient's first name if available
3. Keep the email concise but complete
4. Include a clear call-to-action when appropriate
5. End with a professional signature block
6. Do NOT include the subject line in the body
7. Use proper paragraph breaks for readability

OUTPUT FORMAT:
Return ONLY a JSON object with exactly these two fields:
{{"subject": "Email subject line here", "body": "Full email body here with proper formatting"}}

Generate the email now:"""

        # Call Claude API
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            temperature=0.7,  # Some creativity for email writing
            messages=[
                {"role": "user", "content": full_prompt}
            ]
        )

        # Parse the response
        response_text = response.content[0].text.strip()

        # Try to parse as JSON
        try:
            # Clean up the response if it has markdown code blocks
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()

            email_data = json.loads(response_text)

            return {
                "success": True,
                "subject": email_data.get("subject", request.template_name),
                "body": email_data.get("body", "")
            }
        except json.JSONDecodeError:
            # If JSON parsing fails, try to extract subject and body manually
            logger.warning(f"Failed to parse email JSON, attempting manual extraction")

            # Return the whole response as body with a default subject
            return {
                "success": True,
                "subject": request.template_name,
                "body": response_text
            }

    except Exception as e:
        logger.error(f"Error generating email: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to generate email")


@router.post("/send-composed-email")
async def send_composed_email(
    request: EmailSendRequest,
    fastapi_request: Request,
    authorization: str = None,
    db: Session = Depends(get_db),
):
    """Send a composed email via the email service"""
    try:
        from email_service import email_service

        # Resolve auth dependency manually (get_current_user_dependency returns the function)
        get_current_user_fn = get_current_user_dependency()
        current_user = await get_current_user_fn(
            token=fastapi_request.headers.get("Authorization", "").replace("Bearer ", ""),
            request=fastapi_request,
            db=db,
        )

        # Require authenticated user
        if not current_user or not hasattr(current_user, 'id'):
            raise HTTPException(status_code=401, detail="Authentication required")

        # Get sender info
        sender_name = current_user.full_name if hasattr(current_user, 'full_name') else "Perennia AI"
        sender_email = current_user.email if hasattr(current_user, 'email') else ""

        # Process the email body: detect video and calendar markers
        import re

        body_text = request.body

        # Replace [VIDEO MESSAGE - Click to watch: URL] with styled HTML card
        def render_video_card(match):
            video_url = match.group(1)
            return (
                '<div style="background:#f0fdfa; border:1px solid #218D8D; border-radius:8px; '
                'padding:16px; margin:16px 0; text-align:center;">'
                '<p style="font-size:16px; font-weight:600; color:#1f2937; margin:0 0 12px 0;">'
                '&#127909; Video Message</p>'
                f'<a href="{video_url}" style="display:inline-block; padding:10px 24px; '
                'background:#218D8D; color:white; border-radius:6px; text-decoration:none; '
                'font-weight:500; font-size:14px;" target="_blank">Watch Video</a></div>'
            )

        body_text = re.sub(
            r'\[VIDEO MESSAGE - Click to watch:\s*(https?://[^\]]+)\]',
            render_video_card,
            body_text
        )

        # Replace "Schedule a time to talk: URL" with styled calendar CTA
        def render_calendar_card(match):
            booking_url = match.group(1)
            return (
                '<div style="background:#f0fdfa; border:1px solid #218D8D; border-radius:8px; '
                'padding:16px; margin:16px 0; text-align:center;">'
                '<p style="font-size:16px; font-weight:600; color:#1f2937; margin:0 0 12px 0;">'
                '&#128197; Schedule a Meeting</p>'
                f'<a href="{booking_url}" style="display:inline-block; padding:10px 24px; '
                'background:#218D8D; color:white; border-radius:6px; text-decoration:none; '
                'font-weight:500; font-size:14px;" target="_blank">Book a Time</a></div>'
            )

        body_text = re.sub(
            r'Schedule a time to talk:\s*(https?://\S+)',
            render_calendar_card,
            body_text
        )

        # Convert remaining newlines to <br>
        body_html_content = body_text.replace(chr(10), '<br>')

        # Format the email body as HTML
        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
        }}
        .email-content {{
            white-space: pre-wrap;
            font-size: 15px;
        }}
        .footer {{
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #eee;
            font-size: 12px;
            color: #888;
        }}
    </style>
</head>
<body>
    <div class="email-content">{body_html_content}</div>
    <div class="footer">
        <p>Sent via Perennia AI CRM</p>
    </div>
</body>
</html>
"""

        # Try sending via Salesforce first if the user has a connected SF profile
        send_method = "sendgrid"
        sf_contact_linked = False
        sf_send_attempted = False

        try:
            from salesforce_integration_models import IntegrationProfile
            from services.salesforce.email_sync_service import salesforce_email_sync

            sf_profile = db.query(IntegrationProfile).filter(
                IntegrationProfile.user_id == current_user.id,
                IntegrationProfile.provider == "salesforce",
                IntegrationProfile.status.in_(["connected", "active"])
            ).first()

            if sf_profile:
                sf_send_attempted = True
                sf_result = await salesforce_email_sync.send_email_via_salesforce(
                    db=db,
                    integration_profile_id=sf_profile.id,
                    to_email=request.to_email,
                    subject=request.subject,
                    html_body=html_body
                )

                if sf_result.get("success"):
                    send_method = "salesforce"
                    sf_contact_linked = sf_result.get("sf_contact_id") is not None
                    logger.info(f"Email sent via Salesforce to {request.to_email} (contact_linked={sf_contact_linked})")
                else:
                    logger.warning(f"Salesforce email send failed, falling back to SendGrid: {sf_result.get('message')}")
        except Exception as sf_err:
            logger.warning(f"Salesforce email attempt failed, falling back to SendGrid: {sf_err}")

        # Fall back to SendGrid if Salesforce didn't send
        if send_method != "salesforce":
            success = email_service.send_html_email(
                to_email=request.to_email,
                subject=request.subject,
                html_body=html_body,
                plain_text_body=request.body
            )
            if not success:
                raise HTTPException(status_code=500, detail="Failed to send email - email service returned error")

        # Log the email activity
        try:
            from models import Activity, Lead, Loan

            activity_data = {
                "organization_id": 1,
                "activity_type": "email_sent",
                "subject": f"Email: {request.subject}",
                "description": f"Email sent to {request.to_name or request.to_email}: {request.subject} (via {send_method})",
                "completed": True,
                "completed_at": datetime.utcnow(),
                "user_id": current_user.id,
            }

            if request.entity_type == "lead" and request.entity_id:
                activity_data["lead_id"] = request.entity_id
            elif request.entity_type == "loan" and request.entity_id:
                activity_data["loan_id"] = request.entity_id

            activity = Activity(**activity_data)
            db.add(activity)
            db.commit()
        except Exception as log_err:
            logger.warning(f"Failed to log email activity: {log_err}")

        return {
            "success": True,
            "message": f"Email sent successfully to {request.to_email}",
            "send_method": send_method,
            "sf_contact_linked": sf_contact_linked
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending email: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to send email")
