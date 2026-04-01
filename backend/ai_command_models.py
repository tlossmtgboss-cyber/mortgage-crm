"""
AI Command Models for Perennia AI AI Landing Page

This module contains:
- AI reliability configuration (AI_CONFIG)
- AICircuitBreaker class for preventing cascading AI failures
- AIMetrics class for logging AI interactions
- AI_TOOLS list (function calling tools definition for Claude)
- ValidationResult and ActionValidator classes
- Pydantic request/response models
- SYSTEM_PROMPT for Claude
- EMAIL_TEMPLATE_PROMPTS for AI email generation
- Screenshot-related Pydantic models
- Lazy import helpers and global instances
"""

from pydantic import BaseModel
from typing import Optional, Dict, List, Any
from datetime import datetime
import logging
import time

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
    def validate_action(action: Dict[str, Any], user_id: int, db) -> 'ValidationResult':
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
    def pre_execution_check(action: Dict[str, Any], user_id: int, db) -> 'ValidationResult':
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


# ============================================================================
# Lazy import helper for main module to avoid circular imports
# ============================================================================

def get_main_module():
    import main
    return main


def get_current_user_dependency():
    """Get the get_current_user dependency from main module"""
    return get_main_module().get_current_user


# In-memory action cache with TTL and size bounds (in production, use Redis)
class BoundedCache(dict):
    """A dict with TTL expiration and max size to prevent unbounded memory growth."""

    def __init__(self, maxsize: int = 10000, ttl: int = 3600):
        super().__init__()
        self.maxsize = maxsize
        self.ttl = ttl
        self._timestamps: Dict[str, float] = {}

    def __setitem__(self, key, value):
        self._cleanup()
        if len(self) >= self.maxsize:
            # Evict the oldest entry
            oldest = min(self._timestamps, key=self._timestamps.get)
            self.pop(oldest, None)
            self._timestamps.pop(oldest, None)
        super().__setitem__(key, value)
        self._timestamps[key] = time.time()

    def __getitem__(self, key):
        if key in self._timestamps and time.time() - self._timestamps[key] > self.ttl:
            del self[key]
            del self._timestamps[key]
            raise KeyError(key)
        return super().__getitem__(key)

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def __contains__(self, key):
        if key in self._timestamps and time.time() - self._timestamps[key] > self.ttl:
            self.pop(key, None)
            self._timestamps.pop(key, None)
            return False
        return super().__contains__(key)

    def __delitem__(self, key):
        super().__delitem__(key)
        self._timestamps.pop(key, None)

    def _cleanup(self):
        now = time.time()
        expired = [k for k, t in self._timestamps.items() if now - t > self.ttl]
        for k in expired:
            self.pop(k, None)
            self._timestamps.pop(k, None)


action_cache: BoundedCache = BoundedCache(maxsize=10000, ttl=3600)


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


class SendEmailRequest(BaseModel):
    email_address: Optional[str] = None


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


# ============================================================================
# Email Template Prompts for AI Generation
# ============================================================================

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
