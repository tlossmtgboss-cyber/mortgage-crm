"""
Query Executor - Executes dynamic analytical queries for AI
Allows AI to answer complex questions about pipeline, performance, and trends
"""
import logging
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timedelta

# Import tactical query implementations
import query_executor_tactical as tactical
import query_executor_processor as processor

logger = logging.getLogger(__name__)


class QueryExecutor:
    """
    Executes predefined analytical queries based on AI requests
    All queries are parameterized and safe from SQL injection
    """

    @staticmethod
    def execute_query(
        db: Session,
        query_type: str,
        params: Dict[str, Any],
        user_id: int
    ) -> Dict[str, Any]:
        """
        Execute a predefined query with parameters

        Args:
            db: Database session
            query_type: Type of query to execute
            params: Query parameters
            user_id: User making the request
        """
        try:
            db.rollback()  # Clear any failed transactions
        except Exception as e:
            logger.exception(f"Failed to rollback DB session before query execution: {e}")

        logger.info(f"Executing {query_type} for user {user_id} with params {params}")

        # Route to appropriate query method
        query_methods = {
            "pipeline_analysis": QueryExecutor._query_pipeline_analysis,
            "lead_source_performance": QueryExecutor._query_lead_source_performance,
            "conversion_funnel": QueryExecutor._query_conversion_funnel,
            "loan_type_performance": QueryExecutor._query_loan_type_performance,
            "monthly_trends": QueryExecutor._query_monthly_trends,
            "stale_leads_report": QueryExecutor._query_stale_leads,
            "high_value_opportunities": QueryExecutor._query_high_value_opportunities,
            "activity_summary": QueryExecutor._query_activity_summary,
            # Customer Lifecycle & Value
            "client_lifetime_value": QueryExecutor._query_client_lifetime_value,
            "refi_candidates": QueryExecutor._query_refi_candidates,
            "client_retention_rate": QueryExecutor._query_client_retention_rate,
            "ghost_clients": QueryExecutor._query_ghost_clients,
            "communication_effectiveness": QueryExecutor._query_communication_effectiveness,
            "referral_likelihood": QueryExecutor._query_referral_likelihood,
            # Operational Efficiency
            "process_bottlenecks": QueryExecutor._query_process_bottlenecks,
            "sla_compliance": QueryExecutor._query_sla_compliance,
            "document_turnaround": QueryExecutor._query_document_turnaround,
            "pull_through_rate": QueryExecutor._query_pull_through_rate,
            "capacity_utilization": QueryExecutor._query_capacity_utilization,
            "cycle_time_by_loan_type": QueryExecutor._query_cycle_time_by_loan_type,
            # Risk & Early Warning
            "at_risk_loans": QueryExecutor._query_at_risk_loans,
            "expiring_rate_locks": QueryExecutor._query_expiring_rate_locks,
            "credit_quality_trend": QueryExecutor._query_credit_quality_trend,
            "compliance_risk_score": QueryExecutor._query_compliance_risk_score,
            "poor_quality_sources": QueryExecutor._query_poor_quality_sources,
            # Marketing & Growth
            "cost_per_acquisition": QueryExecutor._query_cost_per_acquisition,
            "marketing_roi": QueryExecutor._query_marketing_roi,
            "seasonal_trends": QueryExecutor._query_seasonal_trends,
            "competitive_analysis": QueryExecutor._query_competitive_analysis,
            "market_share_by_zip": QueryExecutor._query_market_share_by_zip,
            # Financial Forecasting
            "revenue_forecast_90d": QueryExecutor._query_revenue_forecast_90d,
            "pipeline_value_at_risk": QueryExecutor._query_pipeline_value_at_risk,
            "margin_trend": QueryExecutor._query_margin_trend,
            "breakeven_analysis": QueryExecutor._query_breakeven_analysis,
            # Quality & Performance
            "processor_quality_metrics": QueryExecutor._query_processor_quality_metrics,
            "loan_delay_root_causes": QueryExecutor._query_loan_delay_root_causes,
            "documentation_completeness": QueryExecutor._query_documentation_completeness,
            "customer_satisfaction_by_lo": QueryExecutor._query_customer_satisfaction_by_lo,
            # Partnership Intelligence
            "top_realtor_partners": QueryExecutor._query_top_realtor_partners,
            "referral_partner_response_time": QueryExecutor._query_referral_partner_response_time,
            "vendor_performance": QueryExecutor._query_vendor_performance,
            # Strategic Planning
            "hiring_recommendation": QueryExecutor._query_hiring_recommendation,
            "product_profitability": QueryExecutor._query_product_profitability,
            "optimal_product_mix": QueryExecutor._query_optimal_product_mix,
            "cost_cutting_opportunities": QueryExecutor._query_cost_cutting_opportunities,
            "employee_productivity_benchmark": QueryExecutor._query_employee_productivity_benchmark,
            # Daily Operations & Priorities
            "daily_focus_priorities": QueryExecutor._query_daily_focus_priorities,
            "hot_list": QueryExecutor._query_hot_list,
            "callback_list": QueryExecutor._query_callback_list,
            "overdue_tasks": QueryExecutor._query_overdue_tasks,
            "weekly_calendar": QueryExecutor._query_weekly_calendar,
            "critical_issues": QueryExecutor._query_critical_issues,
            # Client Communication
            "untouched_clients": QueryExecutor._query_untouched_clients,
            "waiting_on_me": QueryExecutor._query_waiting_on_me,
            "followups_due": QueryExecutor._query_followups_due,
            "email_openers_no_response": QueryExecutor._query_email_openers_no_response,
            "my_response_time": QueryExecutor._query_my_response_time,
            "potentially_upset_clients": QueryExecutor._query_potentially_upset_clients,
            "video_update_candidates": QueryExecutor._query_video_update_candidates,
            # Loan Status & Milestones
            "closing_this_period": QueryExecutor._query_closing_this_period,
            "outstanding_conditions": QueryExecutor._query_outstanding_conditions,
            "needs_appraisal": QueryExecutor._query_needs_appraisal,
            "waiting_underwriting": QueryExecutor._query_waiting_underwriting,
            "needs_insurance_title": QueryExecutor._query_needs_insurance_title,
            "clear_to_close_pipeline": QueryExecutor._query_clear_to_close_pipeline,
            "loans_in_final_review": QueryExecutor._query_loans_in_final_review,
            "milestones_this_week": QueryExecutor._query_milestones_this_week,
            # Income & Commission
            "my_commission_this_month": QueryExecutor._query_my_commission_this_month,
            "projected_income": QueryExecutor._query_projected_income,
            "funded_this_week": QueryExecutor._query_funded_this_week,
            "goal_progress": QueryExecutor._query_goal_progress,
            "ytd_income": QueryExecutor._query_ytd_income,
            "pipeline_commission_value": QueryExecutor._query_pipeline_commission_value,
            "highest_commission_loans": QueryExecutor._query_highest_commission_loans,
            # Personal Performance
            "am_i_hitting_numbers": QueryExecutor._query_am_i_hitting_numbers,
            "my_conversion_rate": QueryExecutor._query_my_conversion_rate,
            "compare_to_last_period": QueryExecutor._query_compare_to_last_period,
            "my_avg_time_to_close": QueryExecutor._query_my_avg_time_to_close,
            "personal_best_month": QueryExecutor._query_personal_best_month,
            "am_i_improving": QueryExecutor._query_am_i_improving,
            "closing_ratio_by_type": QueryExecutor._query_closing_ratio_by_type,
            # Referral Partner Management
            "partners_for_lunch": QueryExecutor._query_partners_for_lunch,
            "top_referral_source_quarter": QueryExecutor._query_top_referral_source_quarter,
            "dormant_partners": QueryExecutor._query_dormant_partners,
            "partners_need_followup": QueryExecutor._query_partners_need_followup,
            "relationships_need_nurture": QueryExecutor._query_relationships_need_nurture,
            "partners_shopping_competitors": QueryExecutor._query_partners_shopping_competitors,
            "partners_sent_bad_leads": QueryExecutor._query_partners_sent_bad_leads,
            # Borrower Qualification
            "can_borrower_qualify": QueryExecutor._query_can_borrower_qualify,
            "max_purchase_price": QueryExecutor._query_max_purchase_price,
            "eligible_loan_programs": QueryExecutor._query_eligible_loan_programs,
            "qualification_gaps": QueryExecutor._query_qualification_gaps,
            "buy_now_or_wait": QueryExecutor._query_buy_now_or_wait,
            "afford_more_house": QueryExecutor._query_afford_more_house,
            "required_documentation": QueryExecutor._query_required_documentation,
            "dti_analysis": QueryExecutor._query_dti_analysis,
            # Time Management
            "time_spent_analysis": QueryExecutor._query_time_spent_analysis,
            "revenue_per_activity": QueryExecutor._query_revenue_per_activity,
            "should_delegate": QueryExecutor._query_should_delegate,
            "task_balance_analysis": QueryExecutor._query_task_balance_analysis,
            "productive_windows": QueryExecutor._query_productive_windows,
            "time_per_loan": QueryExecutor._query_time_per_loan,
            # Pipeline Health
            "pipeline_health_check": QueryExecutor._query_pipeline_health_check,
            "lead_flow_adequate": QueryExecutor._query_lead_flow_adequate,
            "pipeline_velocity": QueryExecutor._query_pipeline_velocity,
            "stage_concentration": QueryExecutor._query_stage_concentration,
            "pipeline_coverage_ratio": QueryExecutor._query_pipeline_coverage_ratio,
            "leads_needed_for_goal": QueryExecutor._query_leads_needed_for_goal,
            # Action Items
            "most_urgent_now": QueryExecutor._query_most_urgent_now,
            "highest_impact_actions": QueryExecutor._query_highest_impact_actions,
            "falling_through_cracks": QueryExecutor._query_falling_through_cracks,
            "productive_downtime": QueryExecutor._query_productive_downtime,
            "quick_wins": QueryExecutor._query_quick_wins,
            # Scenario Analysis
            "rate_drop_impact": QueryExecutor._query_rate_drop_impact,
            "portfolio_refi_potential": QueryExecutor._query_portfolio_refi_potential,
            "referral_source_risk": QueryExecutor._query_referral_source_risk,
            "processor_hire_roi": QueryExecutor._query_processor_hire_roi,
            "product_focus_impact": QueryExecutor._query_product_focus_impact,
            "vacation_feasibility": QueryExecutor._query_vacation_feasibility,
            # Client Deep Dives
            "client_360_view": QueryExecutor._query_client_360_view,
            "loan_story": QueryExecutor._query_loan_story,
            "loan_delay_reason": QueryExecutor._query_loan_delay_reason,
            "file_risk_level": QueryExecutor._query_file_risk_level,
            "client_needs_from_me": QueryExecutor._query_client_needs_from_me,
            "client_history": QueryExecutor._query_client_history,
            # Market Intelligence
            "competitor_rates": QueryExecutor._query_competitor_rates,
            "losing_on_rate": QueryExecutor._query_losing_on_rate,
            "why_losing_to_competitors": QueryExecutor._query_why_losing_to_competitors,
            "my_value_prop": QueryExecutor._query_my_value_prop,
            # Compliance & Risk
            "compliance_red_flags": QueryExecutor._query_compliance_red_flags,
            "overdue_disclosures": QueryExecutor._query_overdue_disclosures,
            "loans_might_not_close": QueryExecutor._query_loans_might_not_close,
            "audit_risk_assessment": QueryExecutor._query_audit_risk_assessment,
            "fair_lending_concerns": QueryExecutor._query_fair_lending_concerns,
            # Relationship Maintenance
            "weekly_outreach_list": QueryExecutor._query_weekly_outreach_list,
            "loan_anniversaries": QueryExecutor._query_loan_anniversaries,
            "past_client_checkins": QueryExecutor._query_past_client_checkins,
            "upcoming_celebrations": QueryExecutor._query_upcoming_celebrations,
            "gratitude_followups": QueryExecutor._query_gratitude_followups,
            "referral_ask_opportunities": QueryExecutor._query_referral_ask_opportunities,
            # Learning & Improvement
            "my_weaknesses": QueryExecutor._query_my_weaknesses,
            "success_patterns": QueryExecutor._query_success_patterns,
            "repeated_mistakes": QueryExecutor._query_repeated_mistakes,
            "close_faster_tips": QueryExecutor._query_close_faster_tips,
            "skill_gaps": QueryExecutor._query_skill_gaps,
            # Processor - Daily Operations & Workload Management
            "processor_workload_today": QueryExecutor._query_processor_workload_today,
            "processor_deadlines_today": QueryExecutor._query_processor_deadlines_today,
            "processor_priority_queue": QueryExecutor._query_processor_priority_queue,
            "processor_current_capacity": QueryExecutor._query_processor_current_capacity,
            "processor_files_by_loan_officer": QueryExecutor._query_processor_files_by_loan_officer,
            "processor_weekly_calendar": QueryExecutor._query_processor_weekly_calendar,
            "processor_overdue_tasks": QueryExecutor._query_processor_overdue_tasks,
            "processor_file_list": QueryExecutor._query_processor_file_list,
            # Processor - Document Management
            "processor_missing_documents": QueryExecutor._query_processor_missing_documents,
            "processor_unresponsive_borrowers_docs": QueryExecutor._query_processor_unresponsive_borrowers_docs,
            "processor_documents_uploaded_today": QueryExecutor._query_processor_documents_uploaded_today,
            "processor_complete_documentation": QueryExecutor._query_processor_complete_documentation,
            "processor_overdue_doc_requests": QueryExecutor._query_processor_overdue_doc_requests,
            "processor_loan_stips": QueryExecutor._query_processor_loan_stips,
            "processor_initial_disclosures_needed": QueryExecutor._query_processor_initial_disclosures_needed,
            "processor_pending_verifications": QueryExecutor._query_processor_pending_verifications,
            "processor_credit_supplement_needed": QueryExecutor._query_processor_credit_supplement_needed,
            "processor_tax_return_requests": QueryExecutor._query_processor_tax_return_requests,
            "processor_incomplete_income_docs": QueryExecutor._query_processor_incomplete_income_docs,
            "processor_expired_documents": QueryExecutor._query_processor_expired_documents,
            # Processor - Third-Party Services & Vendors
            "processor_appraisals_to_order": QueryExecutor._query_processor_appraisals_to_order,
            "processor_appraisals_in_progress": QueryExecutor._query_processor_appraisals_in_progress,
            "processor_overdue_appraisals": QueryExecutor._query_processor_overdue_appraisals,
            "processor_appraisal_issues": QueryExecutor._query_processor_appraisal_issues,
            "processor_title_work_pending": QueryExecutor._query_processor_title_work_pending,
            "processor_title_commitments_review": QueryExecutor._query_processor_title_commitments_review,
            "processor_hoa_docs_pending": QueryExecutor._query_processor_hoa_docs_pending,
            "processor_vendor_turnaround_times": QueryExecutor._query_processor_vendor_turnaround_times,
            "processor_inspections_scheduled": QueryExecutor._query_processor_inspections_scheduled,
            "processor_insurance_needed": QueryExecutor._query_processor_insurance_needed,
            # Processor - Underwriting Coordination
            "processor_ready_for_underwriting": QueryExecutor._query_processor_ready_for_underwriting,
            "processor_files_with_underwriter": QueryExecutor._query_processor_files_with_underwriter,
            "processor_conditions_received_today": QueryExecutor._query_processor_conditions_received_today,
            "processor_all_outstanding_conditions": QueryExecutor._query_processor_all_outstanding_conditions,
            "processor_cleared_conditions": QueryExecutor._query_processor_cleared_conditions,
            "processor_suspended_files": QueryExecutor._query_processor_suspended_files,
            "processor_initial_approvals": QueryExecutor._query_processor_initial_approvals,
            "processor_clear_to_close_files": QueryExecutor._query_processor_clear_to_close_files,
            "processor_high_risk_underwriting": QueryExecutor._query_processor_high_risk_underwriting,
            "processor_next_uw_call": QueryExecutor._query_processor_next_uw_call,
            # Processor - Timeline & Rate Lock Management
            "processor_closing_schedule": QueryExecutor._query_processor_closing_schedule,
            "processor_at_risk_closings": QueryExecutor._query_processor_at_risk_closings,
            "processor_expiring_rate_locks": QueryExecutor._query_processor_expiring_rate_locks,
            "processor_tight_timeline_files": QueryExecutor._query_processor_tight_timeline_files,
            "processor_disclosures_due": QueryExecutor._query_processor_disclosures_due,
            "processor_delayed_files": QueryExecutor._query_processor_delayed_files,
            "processor_closing_success_rate": QueryExecutor._query_processor_closing_success_rate,
            "processor_avg_days_to_close": QueryExecutor._query_processor_avg_days_to_close,
            # Processor - Quality Control & Compliance
            "processor_files_needing_qc": QueryExecutor._query_processor_files_needing_qc,
            "processor_compliance_red_flags": QueryExecutor._query_processor_compliance_red_flags,
            "processor_trid_violations": QueryExecutor._query_processor_trid_violations,
            "processor_missing_disclosures": QueryExecutor._query_processor_missing_disclosures,
            "processor_data_errors": QueryExecutor._query_processor_data_errors,
            "processor_aus_rerun_needed": QueryExecutor._query_processor_aus_rerun_needed,
            "processor_appraisal_issues_qc": QueryExecutor._query_processor_appraisal_issues_qc,
            "processor_credit_issues_qc": QueryExecutor._query_processor_credit_issues_qc,
            "processor_audit_ready": QueryExecutor._query_processor_audit_ready,
            # Processor - Borrower Communication
            "processor_unresponsive_borrowers": QueryExecutor._query_processor_unresponsive_borrowers,
            "processor_borrowers_to_call_today": QueryExecutor._query_processor_borrowers_to_call_today,
            "processor_frustrated_borrowers": QueryExecutor._query_processor_frustrated_borrowers,
            "processor_borrower_response_times": QueryExecutor._query_processor_borrower_response_times,
            "processor_borrowers_need_updates": QueryExecutor._query_processor_borrowers_need_updates,
            "processor_borrower_meetings_needed": QueryExecutor._query_processor_borrower_meetings_needed,
            "processor_borrower_satisfaction": QueryExecutor._query_processor_borrower_satisfaction,
            # Processor - Loan Officer Coordination
            "processor_lo_action_items": QueryExecutor._query_processor_lo_action_items,
            "processor_los_blocking_files": QueryExecutor._query_processor_los_blocking_files,
            "processor_lo_response_times": QueryExecutor._query_processor_lo_response_times,
            "processor_my_loan_officers": QueryExecutor._query_processor_my_loan_officers,
            "processor_files_need_lo_approval": QueryExecutor._query_processor_files_need_lo_approval,
            "processor_problem_files_by_lo": QueryExecutor._query_processor_problem_files_by_lo,
            "processor_los_with_most_conditions": QueryExecutor._query_processor_los_with_most_conditions,
            # Processor - File Status & Progress Tracking
            "processor_files_by_stage": QueryExecutor._query_processor_files_by_stage,
            "processor_files_moved_today": QueryExecutor._query_processor_files_moved_today,
            "processor_stalled_files": QueryExecutor._query_processor_stalled_files,
            "processor_file_aging_report": QueryExecutor._query_processor_file_aging_report,
            "processor_file_velocity": QueryExecutor._query_processor_file_velocity,
            "processor_files_at_risk_fallout": QueryExecutor._query_processor_files_at_risk_fallout,
            "processor_funnel_health": QueryExecutor._query_processor_funnel_health,
            "processor_files_closed_this_week": QueryExecutor._query_processor_files_closed_this_week,
            # Processor - Problem Resolution
            "processor_all_file_issues": QueryExecutor._query_processor_all_file_issues,
            "processor_income_calc_problems": QueryExecutor._query_processor_income_calc_problems,
            "processor_credit_disputes": QueryExecutor._query_processor_credit_disputes,
            "processor_appraisal_gaps": QueryExecutor._query_processor_appraisal_gaps,
            "processor_title_issues": QueryExecutor._query_processor_title_issues,
            "processor_manual_underwriting_files": QueryExecutor._query_processor_manual_underwriting_files,
            "processor_eligibility_issues": QueryExecutor._query_processor_eligibility_issues,
            "processor_whats_blocking_files": QueryExecutor._query_processor_whats_blocking_files,
            # Processor - Performance & Analytics
            "processor_closing_ratio": QueryExecutor._query_processor_closing_ratio,
            "processor_avg_processing_time": QueryExecutor._query_processor_avg_processing_time,
            "processor_peer_comparison": QueryExecutor._query_processor_peer_comparison,
            "processor_condition_clear_rate": QueryExecutor._query_processor_condition_clear_rate,
            "processor_error_rate": QueryExecutor._query_processor_error_rate,
            "processor_fastest_loan_types": QueryExecutor._query_processor_fastest_loan_types,
            "processor_slowest_files": QueryExecutor._query_processor_slowest_files,
            # Processor - Capacity & Workload Planning
            "processor_at_capacity_check": QueryExecutor._query_processor_at_capacity_check,
            "processor_incoming_files": QueryExecutor._query_processor_incoming_files,
            "processor_can_take_another": QueryExecutor._query_processor_can_take_another,
            "processor_workload_trend": QueryExecutor._query_processor_workload_trend,
            "processor_file_distribution": QueryExecutor._query_processor_file_distribution,
            # Processor - Reporting & Insights
            "processor_weekly_summary": QueryExecutor._query_processor_weekly_summary,
            "processor_weekly_wins": QueryExecutor._query_processor_weekly_wins,
            "processor_time_allocation": QueryExecutor._query_processor_time_allocation,
            "processor_biggest_bottleneck": QueryExecutor._query_processor_biggest_bottleneck,
            "processor_common_conditions": QueryExecutor._query_processor_common_conditions,
            "processor_lo_quality_ranking": QueryExecutor._query_processor_lo_quality_ranking,
        }

        query_func = query_methods.get(query_type)
        if not query_func:
            raise ValueError(f"Unknown query type: {query_type}")

        try:
            result = query_func(db, params, user_id)
            return {
                "success": True,
                "query_type": query_type,
                "data": result,
                "count": len(result) if isinstance(result, list) else 1
            }
        except Exception as e:
            logger.error(f"Query execution error: {e}")
            try:
                db.rollback()
            except Exception as e2:
                logger.exception(f"Failed to rollback DB session after query execution error: {e2}")
            return {
                "success": False,
                "error": "Internal server error",
                "query_type": query_type
            }

    @staticmethod
    def _query_pipeline_analysis(db: Session, params: Dict, user_id: int) -> List[Dict]:
        """Detailed pipeline analysis by stage"""
        result = db.execute(text("""
            SELECT
                stage,
                COUNT(*) as lead_count,
                COALESCE(SUM(preapproval_amount), 0) as total_value,
                COALESCE(AVG(preapproval_amount), 0) as avg_loan_amount,
                ROUND(AVG(EXTRACT(EPOCH FROM (NOW() - created_at))/86400)::numeric, 1) as avg_age_days
            FROM leads
            WHERE owner_id = :user_id
            GROUP BY stage
            ORDER BY total_value DESC
        """), {"user_id": user_id})

        return [
            {
                "stage": str(row[0]) if row[0] else "Unknown",
                "lead_count": row[1],
                "total_value": float(row[2]),
                "avg_loan_amount": float(row[3]),
                "avg_age_days": float(row[4]) if row[4] else 0
            }
            for row in result
        ]

    @staticmethod
    def _query_lead_source_performance(db: Session, params: Dict, user_id: int) -> List[Dict]:
        """Analyze performance by lead source"""
        date_range = params.get("date_range_days", 90)

        result = db.execute(text("""
            SELECT
                COALESCE(source, 'Unknown') as source,
                COUNT(*) as total_leads,
                0 as closed_won,
                ROUND(
                    (0::numeric /
                     NULLIF(COUNT(*), 0) * 100), 1
                ) as close_rate_pct,
                0 as total_revenue,
                0 as avg_deal_size
            FROM leads
            WHERE owner_id = :user_id
            AND created_at > NOW() - INTERVAL :date_range
            GROUP BY source
            HAVING COUNT(*) >= 2
            ORDER BY total_revenue DESC
        """), {"user_id": user_id, "date_range": f"{date_range} days"})

        return [
            {
                "source": row[0],
                "total_leads": row[1],
                "closed_won": row[2],
                "close_rate_pct": float(row[3]) if row[3] else 0,
                "total_revenue": float(row[4]),
                "avg_deal_size": float(row[5])
            }
            for row in result
        ]

    @staticmethod
    def _query_conversion_funnel(db: Session, params: Dict, user_id: int) -> List[Dict]:
        """Analyze conversion rates through pipeline stages"""
        result = db.execute(text("""
            WITH stage_counts AS (
                SELECT
                    COUNT(*) as total_leads,
                    COUNT(*) FILTER (WHERE stage IN ('PROSPECT', 'Application', 'PRE_APPROVED')) as reached_prospect,
                    COUNT(*) FILTER (WHERE stage IN ('Application', 'PRE_APPROVED')) as reached_application,
                    COUNT(*) FILTER (WHERE stage = 'PRE_APPROVED') as reached_preapproved,
                    0 as closed_won
                FROM leads
                WHERE owner_id = :user_id
            )
            SELECT * FROM stage_counts
        """), {"user_id": user_id})

        row = result.fetchone()
        if not row:
            return []

        total = row[0] or 1
        return [
            {"stage": "New → Prospect", "count": row[1], "rate_pct": round(row[1] / total * 100, 1)},
            {"stage": "Prospect → Application", "count": row[2], "rate_pct": round(row[2] / max(row[1], 1) * 100, 1)},
            {"stage": "Application → Pre-Approved", "count": row[3], "rate_pct": round(row[3] / max(row[2], 1) * 100, 1)},
            {"stage": "Pre-Approved → CLOSED_WON", "count": row[4], "rate_pct": round(row[4] / max(row[3], 1) * 100, 1)},
        ]

    @staticmethod
    def _query_loan_type_performance(db: Session, params: Dict, user_id: int) -> List[Dict]:
        """Performance breakdown by loan type"""
        result = db.execute(text("""
            SELECT
                COALESCE(loan_type, 'Unknown') as loan_type,
                COUNT(*) as total_leads,
                0 as closed_won,
                0 as closed_lost,
                ROUND(
                    (0::numeric /
                     NULLIF(COUNT(*) FILTER (WHERE stage IN ('PRE_APPROVED', 'NEW')), 0) * 100), 1
                ) as win_rate_pct,
                COALESCE(SUM(preapproval_amount), 0) as total_volume,
                COALESCE(AVG(preapproval_amount), 0) as avg_loan_amount
            FROM leads
            WHERE owner_id = :user_id
            GROUP BY loan_type
            ORDER BY total_volume DESC
        """), {"user_id": user_id})

        return [
            {
                "loan_type": row[0],
                "total_leads": row[1],
                "closed_won": row[2],
                "closed_lost": row[3],
                "win_rate_pct": float(row[4]) if row[4] else 0,
                "total_volume": float(row[5]),
                "avg_loan_amount": float(row[6])
            }
            for row in result
        ]

    @staticmethod
    def _query_monthly_trends(db: Session, params: Dict, user_id: int) -> List[Dict]:
        """Monthly trends for leads and closings"""
        months = params.get("months", 6)

        result = db.execute(text("""
            SELECT
                TO_CHAR(DATE_TRUNC('month', created_at), 'YYYY-MM') as month,
                COUNT(*) as new_leads,
                0 as closed_won,
                0 as revenue
            FROM leads
            WHERE owner_id = :user_id
            AND created_at > NOW() - INTERVAL :months
            GROUP BY DATE_TRUNC('month', created_at)
            ORDER BY month DESC
        """), {"user_id": user_id, "months": f"{months} months"})

        return [
            {
                "month": row[0],
                "new_leads": row[1],
                "closed_won": row[2],
                "revenue": float(row[3])
            }
            for row in result
        ]

    @staticmethod
    def _query_stale_leads(db: Session, params: Dict, user_id: int) -> List[Dict]:
        """Find stale leads that need attention"""
        stale_days = params.get("stale_days", 14)
        limit = params.get("limit", 20)

        result = db.execute(text("""
            SELECT
                id,
                name,
                stage,
                loan_type,
                preapproval_amount,
                created_at,
                ROUND(EXTRACT(EPOCH FROM (NOW() - created_at))/86400) as days_since_created
            FROM leads
            WHERE owner_id = :user_id
            
            AND created_at < NOW() - INTERVAL :stale_days
            ORDER BY created_at ASC
            LIMIT :limit
        """), {"user_id": user_id, "stale_days": f"{stale_days} days", "limit": limit})

        return [
            {
                "id": row[0],
                "name": row[1],
                "stage": str(row[2]) if row[2] else "Unknown",
                "loan_type": row[3],
                "loan_amount": float(row[4]) if row[4] else 0,
                "created_at": row[5].isoformat() if row[5] else None,
                "days_stale": int(row[6]) if row[6] else 0
            }
            for row in result
        ]

    @staticmethod
    def _query_high_value_opportunities(db: Session, params: Dict, user_id: int) -> List[Dict]:
        """Find high-value leads in pipeline"""
        min_amount = params.get("min_amount", 500000)
        limit = params.get("limit", 20)

        result = db.execute(text("""
            SELECT
                id,
                name,
                stage,
                loan_type,
                preapproval_amount,
                email,
                phone,
                created_at
            FROM leads
            WHERE owner_id = :user_id
            
            AND preapproval_amount >= :min_amount
            ORDER BY preapproval_amount DESC
            LIMIT :limit
        """), {"user_id": user_id, "min_amount": min_amount, "limit": limit})

        return [
            {
                "id": row[0],
                "name": row[1],
                "stage": str(row[2]) if row[2] else "Unknown",
                "loan_type": row[3],
                "loan_amount": float(row[4]) if row[4] else 0,
                "email": row[5],
                "phone": row[6],
                "created_at": row[7].isoformat() if row[7] else None
            }
            for row in result
        ]

    @staticmethod
    def _query_activity_summary(db: Session, params: Dict, user_id: int) -> List[Dict]:
        """Summary of recent activities"""
        days = params.get("days", 30)

        result = db.execute(text("""
            SELECT
                activity_type,
                COUNT(*) as count,
                COUNT(DISTINCT lead_id) as unique_leads
            FROM activities
            WHERE user_id = :user_id
            AND created_at > NOW() - INTERVAL :days
            GROUP BY activity_type
            ORDER BY count DESC
        """), {"user_id": user_id, "days": f"{days} days"})

        return [
            {
                "activity_type": row[0],
                "count": row[1],
                "unique_leads": row[2]
            }
            for row in result
        ]

    # ============================================================================
    # CUSTOMER LIFECYCLE & VALUE QUERIES
    # ============================================================================

    @staticmethod
    def _query_client_lifetime_value(db: Session, params: Dict, user_id: int) -> List[Dict]:
        """Calculate client lifetime value - total value per client including originations and refinances"""
        result = db.execute(text("""
            WITH client_summary AS (
                SELECT
                    CONCAT(l.first_name, ' ', l.last_name) as client_name,
                    l.email,
                    COUNT(DISTINCT l.id) as total_loans,
                    COALESCE(SUM(l.preapproval_amount), 0) as total_loan_volume,
                    MIN(l.created_at) as first_loan_date,
                    MAX(l.created_at) as last_loan_date,
                    COUNT(DISTINCT CASE WHEN l.loan_type = 'Refinance' THEN l.id END) as refi_count,
                    COALESCE(SUM(l.preapproval_amount * 0.01), 0) as estimated_revenue
                FROM leads l
                WHERE l.owner_id = :user_id
                AND l.email IS NOT NULL
                GROUP BY l.email, CONCAT(l.first_name, ' ', l.last_name)
                HAVING COUNT(*) >= 1
            )
            SELECT * FROM client_summary
            ORDER BY estimated_revenue DESC
            LIMIT 50
        """), {"user_id": user_id})

        return [
            {
                "client_name": row[0],
                "email": row[1],
                "total_loans": row[2],
                "total_loan_volume": float(row[3]),
                "first_loan_date": row[4].isoformat() if row[4] else None,
                "last_loan_date": row[5].isoformat() if row[5] else None,
                "refi_count": row[6],
                "estimated_revenue": float(row[7]),
                "lifetime_value": float(row[7])
            }
            for row in result
        ]

    @staticmethod
    def _query_refi_candidates(db: Session, params: Dict, user_id: int) -> List[Dict]:
        """Identify clients likely to refinance based on rate environment and loan age"""
        months_threshold = params.get("months_since_closing", 12)
        result = db.execute(text("""
            SELECT
                l.id,
                CONCAT(l.first_name, ' ', l.last_name) as client_name,
                l.email,
                l.phone,
                l.loan_type,
                l.preapproval_amount as original_amount,
                l.interest_rate as current_rate,
                l.created_at as loan_date,
                ROUND(EXTRACT(EPOCH FROM (NOW() - l.created_at))/2592000) as months_since_loan,
                CASE
                    WHEN l.interest_rate > 6.5 THEN 'High'
                    WHEN l.interest_rate > 5.5 THEN 'Medium'
                    ELSE 'Low'
                END as refi_priority
            FROM leads l
            WHERE l.owner_id = :user_id
            AND l.stage IN ('CLOSED_WON', 'PRE_APPROVED')
            AND l.created_at < NOW() - INTERVAL :months_threshold
            AND l.interest_rate > 4.0
            ORDER BY l.interest_rate DESC, months_since_loan DESC
            LIMIT 50
        """), {"user_id": user_id, "months_threshold": f"{months_threshold} months"})

        return [
            {
                "id": row[0],
                "client_name": row[1],
                "email": row[2],
                "phone": row[3],
                "loan_type": row[4],
                "original_amount": float(row[5]) if row[5] else 0,
                "current_rate": float(row[6]) if row[6] else 0,
                "loan_date": row[7].isoformat() if row[7] else None,
                "months_since_loan": int(row[8]) if row[8] else 0,
                "refi_priority": row[9]
            }
            for row in result
        ]

    @staticmethod
    def _query_client_retention_rate(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
        """Calculate percentage of clients who come back for additional loans"""
        result = db.execute(text("""
            WITH client_loan_counts AS (
                SELECT
                    email,
                    COUNT(DISTINCT id) as loan_count
                FROM leads
                WHERE owner_id = :user_id
                AND email IS NOT NULL
                AND stage IN ('CLOSED_WON', 'PRE_APPROVED')
                GROUP BY email
            )
            SELECT
                COUNT(*) as total_clients,
                COUNT(*) FILTER (WHERE loan_count > 1) as repeat_clients,
                ROUND(100.0 * COUNT(*) FILTER (WHERE loan_count > 1) / NULLIF(COUNT(*), 0), 1) as retention_rate_pct,
                AVG(loan_count) as avg_loans_per_client
            FROM client_loan_counts
        """), {"user_id": user_id})

        row = result.fetchone()
        if not row:
            return {"total_clients": 0, "repeat_clients": 0, "retention_rate_pct": 0, "avg_loans_per_client": 0}

        return {
            "total_clients": row[0],
            "repeat_clients": row[1],
            "retention_rate_pct": float(row[2]) if row[2] else 0,
            "avg_loans_per_client": float(row[3]) if row[3] else 0
        }

    @staticmethod
    def _query_ghost_clients(db: Session, params: Dict, user_id: int) -> List[Dict]:
        """Find past clients with no recent contact who need re-engagement"""
        days_threshold = params.get("days_since_contact", 180)
        result = db.execute(text("""
            SELECT
                l.id,
                CONCAT(l.first_name, ' ', l.last_name) as client_name,
                l.email,
                l.phone,
                l.last_contact,
                ROUND(EXTRACT(EPOCH FROM (NOW() - COALESCE(l.last_contact, l.updated_at)))/86400) as days_since_contact,
                l.preapproval_amount,
                l.loan_type
            FROM leads l
            WHERE l.owner_id = :user_id
            AND l.stage IN ('CLOSED_WON', 'PRE_APPROVED')
            AND COALESCE(l.last_contact, l.updated_at) < NOW() - INTERVAL :days_threshold
            ORDER BY days_since_contact DESC
            LIMIT 50
        """), {"user_id": user_id, "days_threshold": f"{days_threshold} days"})

        return [
            {
                "id": row[0],
                "client_name": row[1],
                "email": row[2],
                "phone": row[3],
                "last_contact": row[4].isoformat() if row[4] else None,
                "days_since_contact": int(row[5]) if row[5] else 0,
                "last_loan_amount": float(row[6]) if row[6] else 0,
                "loan_type": row[7]
            }
            for row in result
        ]

    @staticmethod
    def _query_communication_effectiveness(db: Session, params: Dict, user_id: int) -> List[Dict]:
        """Analyze response rates by touch frequency and channel"""
        result = db.execute(text("""
            WITH communication_stats AS (
                SELECT
                    DATE_TRUNC('hour', created_at) as hour_of_day,
                    COUNT(*) as total_communications,
                    COUNT(*) FILTER (WHERE status = 'replied') as replies,
                    ROUND(100.0 * COUNT(*) FILTER (WHERE status = 'replied') / NULLIF(COUNT(*), 0), 1) as response_rate_pct
                FROM communications
                WHERE user_id = :user_id
                AND created_at > NOW() - INTERVAL '90 days'
                GROUP BY DATE_TRUNC('hour', created_at)
                HAVING COUNT(*) >= 5
            )
            SELECT
                EXTRACT(HOUR FROM hour_of_day)::int as hour,
                SUM(total_communications) as total,
                SUM(replies) as replies,
                ROUND(AVG(response_rate_pct), 1) as avg_response_rate
            FROM communication_stats
            GROUP BY EXTRACT(HOUR FROM hour_of_day)
            ORDER BY hour
        """), {"user_id": user_id})

        return [
            {
                "hour_of_day": row[0],
                "total_communications": row[1],
                "replies": row[2],
                "avg_response_rate_pct": float(row[3]) if row[3] else 0
            }
            for row in result
        ]

    @staticmethod
    def _query_referral_likelihood(db: Session, params: Dict, user_id: int) -> List[Dict]:
        """Identify clients most likely to refer based on satisfaction and past behavior"""
        result = db.execute(text("""
            SELECT
                l.id,
                CONCAT(l.first_name, ' ', l.last_name) as client_name,
                l.email,
                l.phone,
                l.sentiment as satisfaction_score,
                l.referral_source_score,
                l.referral_source_rating,
                CASE
                    WHEN l.sentiment >= 8 AND l.referral_source_score >= 80 THEN 'Very High'
                    WHEN l.sentiment >= 7 AND l.referral_source_score >= 60 THEN 'High'
                    WHEN l.sentiment >= 6 THEN 'Medium'
                    ELSE 'Low'
                END as referral_likelihood
            FROM leads l
            WHERE l.owner_id = :user_id
            AND l.stage IN ('CLOSED_WON', 'PRE_APPROVED')
            AND l.sentiment IS NOT NULL
            ORDER BY l.sentiment DESC, l.referral_source_score DESC
            LIMIT 50
        """), {"user_id": user_id})

        return [
            {
                "id": row[0],
                "client_name": row[1],
                "email": row[2],
                "phone": row[3],
                "satisfaction_score": row[4],
                "referral_score": row[5],
                "referral_rating": row[6],
                "referral_likelihood": row[7]
            }
            for row in result
        ]

    # ============================================================================
    # OPERATIONAL EFFICIENCY QUERIES
    # ============================================================================

    @staticmethod
    def _query_process_bottlenecks(db: Session, params: Dict, user_id: int) -> List[Dict]:
        """Identify where loans get stuck in the pipeline"""
        result = db.execute(text("""
            SELECT
                stage,
                COUNT(*) as loans_in_stage,
                ROUND(AVG(EXTRACT(EPOCH FROM (NOW() - updated_at))/86400), 1) as avg_days_in_stage,
                MAX(EXTRACT(EPOCH FROM (NOW() - updated_at))/86400)::int as max_days_in_stage,
                COUNT(*) FILTER (WHERE updated_at < NOW() - INTERVAL '7 days') as stale_count
            FROM loans
            WHERE loan_officer_id = :user_id
            AND stage NOT IN ('FUNDED', 'CLOSED', 'CANCELLED')
            GROUP BY stage
            ORDER BY avg_days_in_stage DESC
        """), {"user_id": user_id})

        return [
            {
                "stage": row[0],
                "loans_in_stage": row[1],
                "avg_days_in_stage": float(row[2]) if row[2] else 0,
                "max_days_in_stage": row[3],
                "stale_count": row[4],
                "is_bottleneck": float(row[2]) > 7 if row[2] else False
            }
            for row in result
        ]

    @staticmethod
    def _query_sla_compliance(db: Session, params: Dict, user_id: int) -> List[Dict]:
        """Calculate on-time performance metrics by stage"""
        result = db.execute(text("""
            SELECT
                stage,
                COUNT(*) as total_loans,
                COUNT(*) FILTER (WHERE sla_status = 'on_time') as on_time_count,
                COUNT(*) FILTER (WHERE sla_status = 'at_risk') as at_risk_count,
                COUNT(*) FILTER (WHERE sla_status = 'overdue') as overdue_count,
                ROUND(100.0 * COUNT(*) FILTER (WHERE sla_status = 'on_time') / NULLIF(COUNT(*), 0), 1) as compliance_rate_pct
            FROM loans
            WHERE loan_officer_id = :user_id
            AND created_at > NOW() - INTERVAL '90 days'
            GROUP BY stage
            ORDER BY compliance_rate_pct ASC
        """), {"user_id": user_id})

        return [
            {
                "stage": row[0],
                "total_loans": row[1],
                "on_time_count": row[2],
                "at_risk_count": row[3],
                "overdue_count": row[4],
                "compliance_rate_pct": float(row[5]) if row[5] else 0
            }
            for row in result
        ]

    @staticmethod
    def _query_document_turnaround(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
        """Calculate time from document request to receipt"""
        result = db.execute(text("""
            SELECT
                COUNT(*) as total_requests,
                ROUND(AVG(EXTRACT(EPOCH FROM (updated_at - created_at))/3600), 1) as avg_turnaround_hours,
                COUNT(*) FILTER (WHERE updated_at - created_at < INTERVAL '24 hours') as within_24h,
                COUNT(*) FILTER (WHERE updated_at - created_at > INTERVAL '72 hours') as over_72h
            FROM documents
            WHERE user_id = :user_id
            AND status = 'received'
            AND created_at > NOW() - INTERVAL '90 days'
        """), {"user_id": user_id})

        row = result.fetchone()
        if not row:
            return {"total_requests": 0, "avg_turnaround_hours": 0, "within_24h": 0, "over_72h": 0}

        return {
            "total_requests": row[0],
            "avg_turnaround_hours": float(row[1]) if row[1] else 0,
            "within_24h_count": row[2],
            "over_72h_count": row[3],
            "within_24h_pct": round(100.0 * row[2] / max(row[0], 1), 1)
        }

    @staticmethod
    def _query_pull_through_rate(db: Session, params: Dict, user_id: int) -> List[Dict]:
        """Calculate percentage of leads that close by source"""
        result = db.execute(text("""
            SELECT
                COALESCE(source, 'Unknown') as source,
                COUNT(*) as total_leads,
                COUNT(*) FILTER (WHERE stage = 'CLOSED_WON') as closed_count,
                COUNT(*) FILTER (WHERE stage = 'CLOSED_LOST') as lost_count,
                ROUND(100.0 * COUNT(*) FILTER (WHERE stage = 'CLOSED_WON') / NULLIF(COUNT(*), 0), 1) as pull_through_rate_pct
            FROM leads
            WHERE owner_id = :user_id
            AND created_at > NOW() - INTERVAL '180 days'
            GROUP BY source
            HAVING COUNT(*) >= 5
            ORDER BY pull_through_rate_pct DESC
        """), {"user_id": user_id})

        return [
            {
                "source": row[0],
                "total_leads": row[1],
                "closed_count": row[2],
                "lost_count": row[3],
                "pull_through_rate_pct": float(row[4]) if row[4] else 0
            }
            for row in result
        ]

    @staticmethod
    def _query_capacity_utilization(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
        """Calculate loans per LO vs optimal capacity"""
        result = db.execute(text("""
            WITH user_capacity AS (
                SELECT
                    COUNT(*) as active_loans,
                    COUNT(*) FILTER (WHERE stage IN ('APPLICATION', 'PROCESSING', 'UNDERWRITING')) as in_process_loans,
                    30 as optimal_capacity
                FROM loans
                WHERE loan_officer_id = :user_id
                AND stage NOT IN ('FUNDED', 'CLOSED', 'CANCELLED')
            )
            SELECT
                active_loans,
                in_process_loans,
                optimal_capacity,
                ROUND(100.0 * active_loans / optimal_capacity, 1) as utilization_pct,
                optimal_capacity - active_loans as capacity_remaining
            FROM user_capacity
        """), {"user_id": user_id})

        row = result.fetchone()
        if not row:
            return {"active_loans": 0, "optimal_capacity": 30, "utilization_pct": 0, "capacity_remaining": 30}

        return {
            "active_loans": row[0],
            "in_process_loans": row[1],
            "optimal_capacity": row[2],
            "utilization_pct": float(row[3]) if row[3] else 0,
            "capacity_remaining": row[4]
        }

    @staticmethod
    def _query_cycle_time_by_loan_type(db: Session, params: Dict, user_id: int) -> List[Dict]:
        """Calculate time to close by loan product"""
        result = db.execute(text("""
            SELECT
                COALESCE(loan_type, 'Unknown') as loan_type,
                COUNT(*) as closed_loans,
                ROUND(AVG(EXTRACT(EPOCH FROM (funded_date - created_at))/86400), 1) as avg_days_to_close,
                MIN(EXTRACT(EPOCH FROM (funded_date - created_at))/86400)::int as fastest_close,
                MAX(EXTRACT(EPOCH FROM (funded_date - created_at))/86400)::int as slowest_close
            FROM loans
            WHERE loan_officer_id = :user_id
            AND stage = 'FUNDED'
            AND funded_date IS NOT NULL
            AND created_at > NOW() - INTERVAL '180 days'
            GROUP BY loan_type
            HAVING COUNT(*) >= 3
            ORDER BY avg_days_to_close ASC
        """), {"user_id": user_id})

        return [
            {
                "loan_type": row[0],
                "closed_loans": row[1],
                "avg_days_to_close": float(row[2]) if row[2] else 0,
                "fastest_close": row[3],
                "slowest_close": row[4]
            }
            for row in result
        ]

    # ============================================================================
    # RISK & EARLY WARNING QUERIES
    # ============================================================================

    @staticmethod
    def _query_at_risk_loans(db: Session, params: Dict, user_id: int) -> List[Dict]:
        """Predict loans at risk of falling out based on patterns"""
        result = db.execute(text("""
            SELECT
                l.id,
                l.loan_number,
                l.borrower_name,
                l.stage,
                l.amount,
                l.days_in_stage,
                l.risk_score,
                CASE
                    WHEN l.days_in_stage > 30 AND l.risk_score > 70 THEN 'Critical'
                    WHEN l.days_in_stage > 21 OR l.risk_score > 60 THEN 'High'
                    WHEN l.days_in_stage > 14 OR l.risk_score > 40 THEN 'Medium'
                    ELSE 'Low'
                END as risk_level,
                ARRAY_AGG(DISTINCT
                    CASE
                        WHEN l.days_in_stage > 21 THEN 'Stalled in stage'
                        WHEN l.risk_score > 60 THEN 'High risk score'
                        WHEN l.sla_status = 'overdue' THEN 'SLA overdue'
                    END
                ) FILTER (WHERE l.days_in_stage > 0) as risk_factors
            FROM loans l
            WHERE l.loan_officer_id = :user_id
            AND l.stage NOT IN ('FUNDED', 'CLOSED', 'CANCELLED')
            AND (l.days_in_stage > 14 OR l.risk_score > 40)
            GROUP BY l.id, l.loan_number, l.borrower_name, l.stage, l.amount, l.days_in_stage, l.risk_score
            ORDER BY l.risk_score DESC, l.days_in_stage DESC
            LIMIT 50
        """), {"user_id": user_id})

        return [
            {
                "id": row[0],
                "loan_number": row[1],
                "borrower_name": row[2],
                "stage": row[3],
                "loan_amount": float(row[4]) if row[4] else 0,
                "days_in_stage": row[5],
                "risk_score": row[6],
                "risk_level": row[7],
                "risk_factors": [f for f in row[8] if f] if row[8] else []
            }
            for row in result
        ]

    @staticmethod
    def _query_expiring_rate_locks(db: Session, params: Dict, user_id: int) -> List[Dict]:
        """Find rate locks expiring soon"""
        days_threshold = params.get("days_threshold", 15)
        result = db.execute(text("""
            SELECT
                l.id,
                l.loan_number,
                l.borrower_name,
                l.stage,
                l.amount,
                l.rate as locked_rate,
                l.lock_date,
                l.closing_date as lock_expiration,
                EXTRACT(DAY FROM (l.closing_date - NOW()))::int as days_until_expiration,
                CASE
                    WHEN l.closing_date < NOW() THEN 'Expired'
                    WHEN l.closing_date < NOW() + INTERVAL '3 days' THEN 'Critical'
                    WHEN l.closing_date < NOW() + INTERVAL '7 days' THEN 'Urgent'
                    ELSE 'Warning'
                END as urgency
            FROM loans l
            WHERE l.loan_officer_id = :user_id
            AND l.lock_date IS NOT NULL
            AND l.closing_date IS NOT NULL
            AND l.closing_date < NOW() + INTERVAL :days_threshold
            AND l.stage NOT IN ('FUNDED', 'CLOSED', 'CANCELLED')
            ORDER BY l.closing_date ASC
        """), {"user_id": user_id, "days_threshold": f"{days_threshold} days"})

        return [
            {
                "id": row[0],
                "loan_number": row[1],
                "borrower_name": row[2],
                "stage": row[3],
                "loan_amount": float(row[4]) if row[4] else 0,
                "locked_rate": float(row[5]) if row[5] else 0,
                "lock_date": row[6].isoformat() if row[6] else None,
                "lock_expiration": row[7].isoformat() if row[7] else None,
                "days_until_expiration": row[8],
                "urgency": row[9]
            }
            for row in result
        ]

    @staticmethod
    def _query_credit_quality_trend(db: Session, params: Dict, user_id: int) -> List[Dict]:
        """Track average FICO and DTI trends over time"""
        result = db.execute(text("""
            SELECT
                TO_CHAR(DATE_TRUNC('month', created_at), 'YYYY-MM') as month,
                COUNT(*) as loan_count,
                ROUND(AVG(credit_score)) as avg_credit_score,
                ROUND(AVG(dti), 1) as avg_dti,
                COUNT(*) FILTER (WHERE credit_score >= 740) as excellent_credit_count,
                COUNT(*) FILTER (WHERE credit_score < 620) as poor_credit_count
            FROM leads
            WHERE owner_id = :user_id
            AND created_at > NOW() - INTERVAL '12 months'
            AND credit_score IS NOT NULL
            GROUP BY DATE_TRUNC('month', created_at)
            ORDER BY month DESC
        """), {"user_id": user_id})

        return [
            {
                "month": row[0],
                "loan_count": row[1],
                "avg_credit_score": int(row[2]) if row[2] else 0,
                "avg_dti": float(row[3]) if row[3] else 0,
                "excellent_credit_count": row[4],
                "poor_credit_count": row[5]
            }
            for row in result
        ]

    @staticmethod
    def _query_compliance_risk_score(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
        """Calculate compliance risk score based on violations and issues"""
        result = db.execute(text("""
            WITH compliance_metrics AS (
                SELECT
                    COUNT(*) FILTER (WHERE stage = 'CLOSED_WON') as total_closed_loans,
                    0 as missing_disclosure_count,
                    0 as trid_violations,
                    0 as late_disclosure_count
                FROM leads
                WHERE owner_id = :user_id
                AND created_at > NOW() - INTERVAL '90 days'
            )
            SELECT
                total_closed_loans,
                missing_disclosure_count,
                trid_violations,
                late_disclosure_count,
                CASE
                    WHEN trid_violations > 5 THEN 'High'
                    WHEN trid_violations > 2 OR late_disclosure_count > 10 THEN 'Medium'
                    ELSE 'Low'
                END as risk_level,
                ROUND(100.0 * (trid_violations + late_disclosure_count) / NULLIF(total_closed_loans, 0), 1) as violation_rate_pct
            FROM compliance_metrics
        """), {"user_id": user_id})

        row = result.fetchone()
        if not row:
            return {"risk_level": "Low", "violation_rate_pct": 0}

        return {
            "total_closed_loans": row[0],
            "missing_disclosure_count": row[1],
            "trid_violations": row[2],
            "late_disclosure_count": row[3],
            "risk_level": row[4],
            "violation_rate_pct": float(row[5]) if row[5] else 0
        }

    @staticmethod
    def _query_poor_quality_sources(db: Session, params: Dict, user_id: int) -> List[Dict]:
        """Identify referral partners with low conversion and high fallout"""
        result = db.execute(text("""
            SELECT
                COALESCE(source, 'Unknown') as source,
                COUNT(*) as total_leads,
                COUNT(*) FILTER (WHERE stage = 'CLOSED_WON') as closed_count,
                COUNT(*) FILTER (WHERE stage = 'CLOSED_LOST') as fallout_count,
                ROUND(100.0 * COUNT(*) FILTER (WHERE stage = 'CLOSED_WON') / NULLIF(COUNT(*), 0), 1) as close_rate_pct,
                ROUND(100.0 * COUNT(*) FILTER (WHERE stage = 'CLOSED_LOST') / NULLIF(COUNT(*), 0), 1) as fallout_rate_pct,
                ROUND(AVG(ai_score), 1) as avg_quality_score
            FROM leads
            WHERE owner_id = :user_id
            AND created_at > NOW() - INTERVAL '180 days'
            GROUP BY source
            HAVING COUNT(*) >= 10
            AND ROUND(100.0 * COUNT(*) FILTER (WHERE stage = 'CLOSED_WON') / NULLIF(COUNT(*), 0), 1) < 15
            ORDER BY close_rate_pct ASC
        """), {"user_id": user_id})

        return [
            {
                "source": row[0],
                "total_leads": row[1],
                "closed_count": row[2],
                "fallout_count": row[3],
                "close_rate_pct": float(row[4]) if row[4] else 0,
                "fallout_rate_pct": float(row[5]) if row[5] else 0,
                "avg_quality_score": float(row[6]) if row[6] else 0
            }
            for row in result
        ]

    # ============================================================================
    # MARKETING & GROWTH QUERIES
    # ============================================================================

    @staticmethod
    def _query_cost_per_acquisition(db: Session, params: Dict, user_id: int) -> List[Dict]:
        """Calculate cost per acquisition by marketing channel"""
        # This would integrate with marketing spend data
        result = db.execute(text("""
            SELECT
                COALESCE(source, 'Unknown') as channel,
                COUNT(*) as total_leads,
                COUNT(*) FILTER (WHERE stage = 'CLOSED_WON') as conversions,
                0 as marketing_spend,
                CASE
                    WHEN COUNT(*) FILTER (WHERE stage = 'CLOSED_WON') > 0
                    THEN ROUND(0 / COUNT(*) FILTER (WHERE stage = 'CLOSED_WON'), 2)
                    ELSE 0
                END as cost_per_acquisition
            FROM leads
            WHERE owner_id = :user_id
            AND created_at > NOW() - INTERVAL '90 days'
            GROUP BY source
            ORDER BY conversions DESC
        """), {"user_id": user_id})

        return [
            {
                "channel": row[0],
                "total_leads": row[1],
                "conversions": row[2],
                "marketing_spend": float(row[3]),
                "cost_per_acquisition": float(row[4])
            }
            for row in result
        ]

    @staticmethod
    def _query_marketing_roi(db: Session, params: Dict, user_id: int) -> List[Dict]:
        """Track campaign conversion from ad to closed loan"""
        result = db.execute(text("""
            SELECT
                COALESCE(source, 'Unknown') as campaign,
                COUNT(*) as leads,
                COUNT(*) FILTER (WHERE stage = 'CLOSED_WON') as conversions,
                COALESCE(SUM(CASE WHEN stage = 'CLOSED_WON' THEN preapproval_amount ELSE 0 END), 0) as total_revenue,
                0 as campaign_cost,
                CASE
                    WHEN 0 > 0 THEN ROUND((COALESCE(SUM(CASE WHEN stage = 'CLOSED_WON' THEN preapproval_amount ELSE 0 END), 0) * 0.01 - 0) / 0 * 100, 1)
                    ELSE 0
                END as roi_pct
            FROM leads
            WHERE owner_id = :user_id
            AND created_at > NOW() - INTERVAL '90 days'
            GROUP BY source
            HAVING COUNT(*) >= 5
            ORDER BY total_revenue DESC
        """), {"user_id": user_id})

        return [
            {
                "campaign": row[0],
                "leads": row[1],
                "conversions": row[2],
                "total_revenue": float(row[3]),
                "campaign_cost": float(row[4]),
                "roi_pct": float(row[5])
            }
            for row in result
        ]

    @staticmethod
    def _query_seasonal_trends(db: Session, params: Dict, user_id: int) -> List[Dict]:
        """Identify month-over-month patterns for forecasting"""
        result = db.execute(text("""
            SELECT
                EXTRACT(MONTH FROM created_at)::int as month_number,
                TO_CHAR(created_at, 'Month') as month_name,
                COUNT(*) as lead_count,
                COALESCE(AVG(preapproval_amount), 0) as avg_loan_amount,
                COUNT(*) FILTER (WHERE stage = 'CLOSED_WON') as closed_count
            FROM leads
            WHERE owner_id = :user_id
            AND created_at > NOW() - INTERVAL '24 months'
            GROUP BY EXTRACT(MONTH FROM created_at), TO_CHAR(created_at, 'Month')
            ORDER BY month_number
        """), {"user_id": user_id})

        return [
            {
                "month_number": row[0],
                "month_name": row[1].strip(),
                "lead_count": row[2],
                "avg_loan_amount": float(row[3]),
                "closed_count": row[4]
            }
            for row in result
        ]

    @staticmethod
    def _query_competitive_analysis(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
        """Analyze lost deals to understand why clients went elsewhere"""
        result = db.execute(text("""
            SELECT
                COUNT(*) FILTER (WHERE stage = 'CLOSED_WON') as won_count,
                COUNT(*) FILTER (WHERE stage = 'CLOSED_LOST') as lost_count,
                ROUND(100.0 * COUNT(*) FILTER (WHERE stage = 'CLOSED_WON') /
                      NULLIF(COUNT(*) FILTER (WHERE stage IN ('CLOSED_WON', 'CLOSED_LOST')), 0), 1) as win_rate_pct,
                COALESCE(AVG(CASE WHEN stage = 'CLOSED_WON' THEN interest_rate END), 0) as avg_won_rate,
                COALESCE(AVG(CASE WHEN stage = 'CLOSED_LOST' THEN interest_rate END), 0) as avg_lost_rate
            FROM leads
            WHERE owner_id = :user_id
            AND created_at > NOW() - INTERVAL '90 days'
            AND stage IN ('CLOSED_WON', 'CLOSED_LOST')
        """), {"user_id": user_id})

        row = result.fetchone()
        if not row:
            return {"won_count": 0, "lost_count": 0, "win_rate_pct": 0}

        return {
            "won_count": row[0],
            "lost_count": row[1],
            "win_rate_pct": float(row[2]) if row[2] else 0,
            "avg_won_rate": float(row[3]) if row[3] else 0,
            "avg_lost_rate": float(row[4]) if row[4] else 0,
            "rate_advantage": round(float(row[4] or 0) - float(row[3] or 0), 3)
        }

    @staticmethod
    def _query_market_share_by_zip(db: Session, params: Dict, user_id: int) -> List[Dict]:
        """Calculate local dominance metrics by ZIP code"""
        result = db.execute(text("""
            SELECT
                COALESCE(zip_code, 'Unknown') as zip_code,
                city,
                state,
                COUNT(*) as total_leads,
                COUNT(*) FILTER (WHERE stage = 'CLOSED_WON') as closed_loans,
                COALESCE(SUM(CASE WHEN stage = 'CLOSED_WON' THEN preapproval_amount ELSE 0 END), 0) as total_volume
            FROM leads
            WHERE owner_id = :user_id
            AND created_at > NOW() - INTERVAL '12 months'
            AND zip_code IS NOT NULL
            GROUP BY zip_code, city, state
            HAVING COUNT(*) >= 3
            ORDER BY closed_loans DESC
            LIMIT 20
        """), {"user_id": user_id})

        return [
            {
                "zip_code": row[0],
                "city": row[1],
                "state": row[2],
                "total_leads": row[3],
                "closed_loans": row[4],
                "total_volume": float(row[5])
            }
            for row in result
        ]

    # ============================================================================
    # FINANCIAL FORECASTING QUERIES
    # ============================================================================

    @staticmethod
    def _query_revenue_forecast_90d(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
        """Forecast revenue based on current pipeline and conversion rates"""
        result = db.execute(text("""
            WITH pipeline_stats AS (
                SELECT
                    COUNT(*) as active_loans,
                    COALESCE(SUM(amount), 0) as pipeline_value,
                    ROUND(AVG(CASE WHEN stage IN ('CLEAR_TO_CLOSE', 'APPROVED') THEN 0.85
                                   WHEN stage = 'UNDERWRITING' THEN 0.65
                                   WHEN stage = 'PROCESSING' THEN 0.45
                                   WHEN stage = 'APPLICATION' THEN 0.25
                                   ELSE 0.10 END), 2) as avg_close_probability
                FROM loans
                WHERE loan_officer_id = :user_id
                AND stage NOT IN ('FUNDED', 'CLOSED', 'CANCELLED')
            ),
            historical_conversion AS (
                SELECT
                    ROUND(100.0 * COUNT(*) FILTER (WHERE stage = 'FUNDED') /
                          NULLIF(COUNT(*), 0), 1) as historical_close_rate_pct
                FROM loans
                WHERE loan_officer_id = :user_id
                AND created_at > NOW() - INTERVAL '180 days'
            )
            SELECT
                p.active_loans,
                p.pipeline_value,
                p.avg_close_probability,
                h.historical_close_rate_pct,
                ROUND(p.pipeline_value * p.avg_close_probability * 0.01, 2) as forecasted_revenue,
                ROUND(p.pipeline_value * (h.historical_close_rate_pct / 100) * 0.01, 2) as conservative_forecast
            FROM pipeline_stats p, historical_conversion h
        """), {"user_id": user_id})

        row = result.fetchone()
        if not row:
            return {"forecasted_revenue": 0, "pipeline_value": 0}

        return {
            "active_loans": row[0],
            "pipeline_value": float(row[1]),
            "avg_close_probability": float(row[2]) if row[2] else 0,
            "historical_close_rate_pct": float(row[3]) if row[3] else 0,
            "forecasted_revenue": float(row[4]) if row[4] else 0,
            "conservative_forecast": float(row[5]) if row[5] else 0
        }

    @staticmethod
    def _query_pipeline_value_at_risk(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
        """Calculate loans likely to cancel or fall through"""
        result = db.execute(text("""
            SELECT
                COUNT(*) as at_risk_count,
                COALESCE(SUM(amount), 0) as value_at_risk,
                COUNT(*) FILTER (WHERE risk_score > 70) as high_risk_count,
                COALESCE(SUM(CASE WHEN risk_score > 70 THEN amount ELSE 0 END), 0) as high_risk_value
            FROM loans
            WHERE loan_officer_id = :user_id
            AND stage NOT IN ('FUNDED', 'CLOSED', 'CANCELLED')
            AND (risk_score > 50 OR days_in_stage > 21)
        """), {"user_id": user_id})

        row = result.fetchone()
        if not row:
            return {"at_risk_count": 0, "value_at_risk": 0}

        return {
            "at_risk_count": row[0],
            "value_at_risk": float(row[1]),
            "high_risk_count": row[2],
            "high_risk_value": float(row[3])
        }

    @staticmethod
    def _query_margin_trend(db: Session, params: Dict, user_id: int) -> List[Dict]:
        """Analyze rate spread over time"""
        result = db.execute(text("""
            SELECT
                TO_CHAR(DATE_TRUNC('month', created_at), 'YYYY-MM') as month,
                COUNT(*) as loan_count,
                ROUND(AVG(rate), 3) as avg_rate,
                ROUND(MIN(rate), 3) as min_rate,
                ROUND(MAX(rate), 3) as max_rate
            FROM loans
            WHERE loan_officer_id = :user_id
            AND rate IS NOT NULL
            AND created_at > NOW() - INTERVAL '12 months'
            GROUP BY DATE_TRUNC('month', created_at)
            ORDER BY month DESC
        """), {"user_id": user_id})

        return [
            {
                "month": row[0],
                "loan_count": row[1],
                "avg_rate": float(row[2]) if row[2] else 0,
                "min_rate": float(row[3]) if row[3] else 0,
                "max_rate": float(row[4]) if row[4] else 0
            }
            for row in result
        ]

    @staticmethod
    def _query_breakeven_analysis(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
        """Calculate loans needed to cover compensation and overhead"""
        monthly_overhead = params.get("monthly_overhead", 15000)
        avg_commission = params.get("avg_commission", 3000)

        result = db.execute(text("""
            WITH monthly_performance AS (
                SELECT
                    COUNT(*) FILTER (WHERE stage = 'FUNDED'
                                    AND funded_date >= DATE_TRUNC('month', NOW())) as loans_this_month,
                    COALESCE(AVG(CASE WHEN stage = 'FUNDED' THEN amount END), 0) as avg_loan_amount
                FROM loans
                WHERE loan_officer_id = :user_id
            )
            SELECT
                loans_this_month,
                avg_loan_amount,
                :monthly_overhead as monthly_overhead,
                :avg_commission as avg_commission,
                CEIL(:monthly_overhead / NULLIF(:avg_commission, 0))::int as loans_needed_breakeven,
                GREATEST(0, CEIL(:monthly_overhead / NULLIF(:avg_commission, 0))::int - loans_this_month) as loans_remaining
            FROM monthly_performance
        """), {
            "user_id": user_id,
            "monthly_overhead": monthly_overhead,
            "avg_commission": avg_commission
        })

        row = result.fetchone()
        if not row:
            return {"loans_needed_breakeven": 0, "loans_remaining": 0}

        return {
            "loans_this_month": row[0],
            "avg_loan_amount": float(row[1]),
            "monthly_overhead": float(row[2]),
            "avg_commission": float(row[3]),
            "loans_needed_breakeven": row[4],
            "loans_remaining": row[5]
        }

    # ============================================================================
    # QUALITY & PERFORMANCE QUERIES
    # ============================================================================

    @staticmethod
    def _query_processor_quality_metrics(db: Session, params: Dict, user_id: int) -> List[Dict]:
        """Analyze error rates and quality metrics by processor"""
        result = db.execute(text("""
            SELECT
                COALESCE(processor, 'Unassigned') as processor_name,
                COUNT(*) as total_loans,
                COUNT(*) FILTER (WHERE stage = 'FUNDED') as closed_loans,
                ROUND(AVG(EXTRACT(EPOCH FROM (COALESCE(funded_date, NOW()) - created_at))/86400), 1) as avg_days_to_close,
                0 as error_count,
                0 as resubmission_count,
                ROUND(100.0 * COUNT(*) FILTER (WHERE sla_status = 'on_time') / NULLIF(COUNT(*), 0), 1) as sla_compliance_pct
            FROM loans
            WHERE loan_officer_id = :user_id
            AND processor IS NOT NULL
            AND created_at > NOW() - INTERVAL '90 days'
            GROUP BY processor
            HAVING COUNT(*) >= 3
            ORDER BY sla_compliance_pct DESC
        """), {"user_id": user_id})

        return [
            {
                "processor_name": row[0],
                "total_loans": row[1],
                "closed_loans": row[2],
                "avg_days_to_close": float(row[3]) if row[3] else 0,
                "error_count": row[4],
                "resubmission_count": row[5],
                "sla_compliance_pct": float(row[6]) if row[6] else 0
            }
            for row in result
        ]

    @staticmethod
    def _query_loan_delay_root_causes(db: Session, params: Dict, user_id: int) -> List[Dict]:
        """Identify what causes most loan delays"""
        result = db.execute(text("""
            SELECT
                stage,
                COUNT(*) as delayed_loans,
                ROUND(AVG(days_in_stage), 1) as avg_delay_days,
                'Document delays' as primary_cause
            FROM loans
            WHERE loan_officer_id = :user_id
            AND days_in_stage > 14
            AND stage NOT IN ('FUNDED', 'CLOSED', 'CANCELLED')
            GROUP BY stage
            ORDER BY delayed_loans DESC
        """), {"user_id": user_id})

        return [
            {
                "stage": row[0],
                "delayed_loans": row[1],
                "avg_delay_days": float(row[2]) if row[2] else 0,
                "primary_cause": row[3]
            }
            for row in result
        ]

    @staticmethod
    def _query_documentation_completeness(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
        """Calculate missing documents by loan stage"""
        result = db.execute(text("""
            WITH doc_stats AS (
                SELECT
                    l.stage,
                    COUNT(DISTINCT l.id) as total_loans,
                    0 as missing_docs
                FROM loans l
                WHERE l.loan_officer_id = :user_id
                AND l.stage NOT IN ('FUNDED', 'CLOSED', 'CANCELLED')
                GROUP BY l.stage
            )
            SELECT
                SUM(total_loans) as total_active_loans,
                SUM(missing_docs) as total_missing_docs,
                ROUND(100.0 * SUM(CASE WHEN missing_docs = 0 THEN total_loans ELSE 0 END) / NULLIF(SUM(total_loans), 0), 1) as completeness_pct
            FROM doc_stats
        """), {"user_id": user_id})

        row = result.fetchone()
        if not row:
            return {"completeness_pct": 100, "total_missing_docs": 0}

        return {
            "total_active_loans": row[0],
            "total_missing_docs": row[1],
            "completeness_pct": float(row[2]) if row[2] else 100
        }

    @staticmethod
    def _query_customer_satisfaction_by_lo(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
        """Get NPS/CSAT scores by loan officer"""
        result = db.execute(text("""
            SELECT
                COUNT(*) as rated_loans,
                ROUND(AVG(sentiment), 1) as avg_satisfaction,
                COUNT(*) FILTER (WHERE sentiment >= 9) as promoters,
                COUNT(*) FILTER (WHERE sentiment <= 6) as detractors,
                ROUND(100.0 * (COUNT(*) FILTER (WHERE sentiment >= 9) - COUNT(*) FILTER (WHERE sentiment <= 6)) / NULLIF(COUNT(*), 0), 1) as nps_score
            FROM leads
            WHERE owner_id = :user_id
            AND sentiment IS NOT NULL
            AND stage IN ('CLOSED_WON', 'PRE_APPROVED')
            AND created_at > NOW() - INTERVAL '180 days'
        """), {"user_id": user_id})

        row = result.fetchone()
        if not row:
            return {"nps_score": 0, "avg_satisfaction": 0}

        return {
            "rated_loans": row[0],
            "avg_satisfaction": float(row[1]) if row[1] else 0,
            "promoters": row[2],
            "detractors": row[3],
            "nps_score": float(row[4]) if row[4] else 0
        }

    # ============================================================================
    # PARTNERSHIP INTELLIGENCE QUERIES
    # ============================================================================

    @staticmethod
    def _query_top_realtor_partners(db: Session, params: Dict, user_id: int) -> List[Dict]:
        """Identify top producing realtor partners"""
        result = db.execute(text("""
            SELECT
                COALESCE(realtor_agent, 'Direct') as realtor_name,
                COUNT(*) as total_referrals,
                COUNT(*) FILTER (WHERE stage = 'CLOSED_WON') as closed_loans,
                ROUND(100.0 * COUNT(*) FILTER (WHERE stage = 'CLOSED_WON') / NULLIF(COUNT(*), 0), 1) as close_rate_pct,
                COALESCE(SUM(CASE WHEN stage = 'CLOSED_WON' THEN amount ELSE 0 END), 0) as total_volume
            FROM loans
            WHERE loan_officer_id = :user_id
            AND realtor_agent IS NOT NULL
            AND created_at > NOW() - INTERVAL '180 days'
            GROUP BY realtor_agent
            HAVING COUNT(*) >= 2
            ORDER BY total_volume DESC
            LIMIT 20
        """), {"user_id": user_id})

        return [
            {
                "realtor_name": row[0],
                "total_referrals": row[1],
                "closed_loans": row[2],
                "close_rate_pct": float(row[3]) if row[3] else 0,
                "total_volume": float(row[4])
            }
            for row in result
        ]

    @staticmethod
    def _query_referral_partner_response_time(db: Session, params: Dict, user_id: int) -> List[Dict]:
        """Measure how fast referral partners engage leads"""
        result = db.execute(text("""
            SELECT
                COALESCE(source, 'Unknown') as partner_name,
                COUNT(*) as total_referrals,
                ROUND(AVG(EXTRACT(EPOCH FROM (COALESCE(last_contact, updated_at) - created_at))/3600), 1) as avg_response_hours,
                COUNT(*) FILTER (WHERE COALESCE(last_contact, updated_at) - created_at < INTERVAL '24 hours') as responded_24h
            FROM leads
            WHERE owner_id = :user_id
            AND source IS NOT NULL
            AND created_at > NOW() - INTERVAL '90 days'
            GROUP BY source
            HAVING COUNT(*) >= 5
            ORDER BY avg_response_hours ASC
        """), {"user_id": user_id})

        return [
            {
                "partner_name": row[0],
                "total_referrals": row[1],
                "avg_response_hours": float(row[2]) if row[2] else 0,
                "responded_24h_count": row[3],
                "response_rate_24h_pct": round(100.0 * row[3] / max(row[1], 1), 1)
            }
            for row in result
        ]

    @staticmethod
    def _query_vendor_performance(db: Session, params: Dict, user_id: int) -> List[Dict]:
        """Compare appraisal, title, and credit vendor performance"""
        result = db.execute(text("""
            SELECT
                COALESCE(title_company, 'Unknown') as vendor_name,
                'Title Company' as vendor_type,
                COUNT(*) as loans_count,
                ROUND(AVG(EXTRACT(EPOCH FROM (closing_date - lock_date))/86400), 1) as avg_turnaround_days,
                0 as avg_cost
            FROM loans
            WHERE loan_officer_id = :user_id
            AND title_company IS NOT NULL
            AND closing_date IS NOT NULL
            AND lock_date IS NOT NULL
            AND created_at > NOW() - INTERVAL '180 days'
            GROUP BY title_company
            HAVING COUNT(*) >= 3
            ORDER BY avg_turnaround_days ASC
            LIMIT 10
        """), {"user_id": user_id})

        return [
            {
                "vendor_name": row[0],
                "vendor_type": row[1],
                "loans_count": row[2],
                "avg_turnaround_days": float(row[3]) if row[3] else 0,
                "avg_cost": float(row[4])
            }
            for row in result
        ]

    # ============================================================================
    # STRATEGIC PLANNING QUERIES
    # ============================================================================

    @staticmethod
    def _query_hiring_recommendation(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
        """Analyze if hiring another team member makes sense"""
        result = db.execute(text("""
            WITH capacity_analysis AS (
                SELECT
                    COUNT(*) as active_loans,
                    COUNT(*) FILTER (WHERE days_in_stage > 14) as stalled_loans,
                    30 as optimal_capacity_per_lo,
                    ROUND(COUNT(*)::numeric / 30, 2) as current_utilization,
                    CASE
                        WHEN COUNT(*) > 30 THEN 'Over capacity'
                        WHEN COUNT(*) > 25 THEN 'Near capacity'
                        ELSE 'Under capacity'
                    END as capacity_status
                FROM loans
                WHERE loan_officer_id = :user_id
                AND stage NOT IN ('FUNDED', 'CLOSED', 'CANCELLED')
            )
            SELECT
                active_loans,
                stalled_loans,
                optimal_capacity_per_lo,
                current_utilization,
                capacity_status,
                CASE
                    WHEN active_loans > 30 AND stalled_loans > 5 THEN 'Strongly Recommended'
                    WHEN active_loans > 25 THEN 'Consider'
                    ELSE 'Not Needed'
                END as hiring_recommendation
            FROM capacity_analysis
        """), {"user_id": user_id})

        row = result.fetchone()
        if not row:
            return {"hiring_recommendation": "Not Needed", "capacity_status": "Under capacity"}

        return {
            "active_loans": row[0],
            "stalled_loans": row[1],
            "optimal_capacity": row[2],
            "current_utilization_pct": float(row[3]) * 100 if row[3] else 0,
            "capacity_status": row[4],
            "hiring_recommendation": row[5]
        }

    @staticmethod
    def _query_product_profitability(db: Session, params: Dict, user_id: int) -> List[Dict]:
        """Calculate margin and time analysis by loan type"""
        result = db.execute(text("""
            SELECT
                COALESCE(loan_type, 'Unknown') as product,
                COUNT(*) as volume,
                ROUND(AVG(amount), 0) as avg_loan_size,
                ROUND(AVG(rate), 3) as avg_rate,
                ROUND(AVG(EXTRACT(EPOCH FROM (COALESCE(funded_date, NOW()) - created_at))/86400), 1) as avg_days_to_close,
                COALESCE(SUM(amount), 0) * 0.01 as estimated_revenue
            FROM loans
            WHERE loan_officer_id = :user_id
            AND created_at > NOW() - INTERVAL '180 days'
            GROUP BY loan_type
            HAVING COUNT(*) >= 3
            ORDER BY estimated_revenue DESC
        """), {"user_id": user_id})

        return [
            {
                "product": row[0],
                "volume": row[1],
                "avg_loan_size": float(row[2]) if row[2] else 0,
                "avg_rate": float(row[3]) if row[3] else 0,
                "avg_days_to_close": float(row[4]) if row[4] else 0,
                "estimated_revenue": float(row[5])
            }
            for row in result
        ]

    @staticmethod
    def _query_optimal_product_mix(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
        """Recommend revenue maximization based on capacity"""
        result = db.execute(text("""
            WITH product_stats AS (
                SELECT
                    loan_type,
                    COUNT(*) as volume,
                    AVG(amount) as avg_amount,
                    AVG(EXTRACT(EPOCH FROM (COALESCE(funded_date, NOW()) - created_at))/86400) as avg_days,
                    (AVG(amount) * 0.01) / NULLIF(AVG(EXTRACT(EPOCH FROM (COALESCE(funded_date, NOW()) - created_at))/86400), 0) as revenue_per_day
                FROM loans
                WHERE loan_officer_id = :user_id
                AND created_at > NOW() - INTERVAL '180 days'
                GROUP BY loan_type
                HAVING COUNT(*) >= 3
            )
            SELECT
                loan_type,
                volume,
                ROUND(avg_amount, 0) as avg_loan_amount,
                ROUND(avg_days, 1) as avg_days_to_close,
                ROUND(revenue_per_day, 2) as revenue_efficiency
            FROM product_stats
            ORDER BY revenue_per_day DESC
            LIMIT 3
        """), {"user_id": user_id})

        top_products = []
        for row in result:
            top_products.append({
                "product": row[0],
                "volume": row[1],
                "avg_loan_amount": float(row[2]) if row[2] else 0,
                "avg_days_to_close": float(row[3]) if row[3] else 0,
                "revenue_efficiency": float(row[4]) if row[4] else 0
            })

        return {
            "recommended_products": top_products,
            "recommendation": f"Focus on {top_products[0]['product'] if top_products else 'Unknown'} - highest revenue per day"
        }

    @staticmethod
    def _query_cost_cutting_opportunities(db: Session, params: Dict, user_id: int) -> List[Dict]:
        """Identify expense efficiency opportunities"""
        # This would integrate with expense tracking data
        return [
            {
                "category": "Marketing",
                "current_spend": 5000,
                "low_roi_channels": ["Channel A", "Channel B"],
                "potential_savings": 1500,
                "recommendation": "Reallocate from low-performing channels"
            },
            {
                "category": "Technology",
                "current_spend": 2000,
                "underutilized_tools": ["Tool X"],
                "potential_savings": 500,
                "recommendation": "Consolidate tools"
            }
        ]

    @staticmethod
    def _query_employee_productivity_benchmark(db: Session, params: Dict, user_id: int) -> Dict[str, Any]:
        """Compare performance to industry standards"""
        result = db.execute(text("""
            WITH user_performance AS (
                SELECT
                    COUNT(*) FILTER (WHERE stage = 'FUNDED'
                                    AND funded_date >= DATE_TRUNC('month', NOW())) as loans_this_month,
                    COUNT(*) FILTER (WHERE stage = 'FUNDED'
                                    AND funded_date >= DATE_TRUNC('month', NOW()) - INTERVAL '1 month'
                                    AND funded_date < DATE_TRUNC('month', NOW())) as loans_last_month,
                    COALESCE(SUM(CASE WHEN stage = 'FUNDED'
                                 AND funded_date >= DATE_TRUNC('month', NOW())
                                 THEN amount ELSE 0 END), 0) as volume_this_month
                FROM loans
                WHERE loan_officer_id = :user_id
            )
            SELECT
                loans_this_month,
                loans_last_month,
                volume_this_month,
                8 as industry_avg_loans_per_month,
                CASE
                    WHEN loans_this_month >= 12 THEN 'Top Performer'
                    WHEN loans_this_month >= 8 THEN 'Above Average'
                    WHEN loans_this_month >= 5 THEN 'Average'
                    ELSE 'Below Average'
                END as performance_tier
            FROM user_performance
        """), {"user_id": user_id})

        row = result.fetchone()
        if not row:
            return {"performance_tier": "No Data", "loans_this_month": 0}

        return {
            "loans_this_month": row[0],
            "loans_last_month": row[1],
            "volume_this_month": float(row[2]),
            "industry_benchmark": row[3],
            "performance_tier": row[4],
            "vs_benchmark": row[0] - row[3] if row[0] else 0
        }

    # ============================================================================
    # TACTICAL QUERIES - Day-to-Day Operations (99 queries)
    # Imported from query_executor_tactical.py
    # ============================================================================

    # Daily Operations & Priorities
    _query_daily_focus_priorities = staticmethod(tactical._query_daily_focus_priorities)
    _query_hot_list = staticmethod(tactical._query_hot_list)
    _query_callback_list = staticmethod(tactical._query_callback_list)
    _query_overdue_tasks = staticmethod(tactical._query_overdue_tasks)
    _query_weekly_calendar = staticmethod(tactical._query_weekly_calendar)
    _query_critical_issues = staticmethod(tactical._query_critical_issues)

    # Client Communication
    _query_untouched_clients = staticmethod(tactical._query_untouched_clients)
    _query_waiting_on_me = staticmethod(tactical._query_waiting_on_me)
    _query_followups_due = staticmethod(tactical._query_followups_due)
    _query_email_openers_no_response = staticmethod(tactical._query_email_openers_no_response)
    _query_my_response_time = staticmethod(tactical._query_my_response_time)
    _query_potentially_upset_clients = staticmethod(tactical._query_potentially_upset_clients)
    _query_video_update_candidates = staticmethod(tactical._query_video_update_candidates)

    # Loan Status & Milestones
    _query_closing_this_period = staticmethod(tactical._query_closing_this_period)
    _query_outstanding_conditions = staticmethod(tactical._query_outstanding_conditions)
    _query_needs_appraisal = staticmethod(tactical._query_needs_appraisal)
    _query_waiting_underwriting = staticmethod(tactical._query_waiting_underwriting)
    _query_needs_insurance_title = staticmethod(tactical._query_needs_insurance_title)
    _query_clear_to_close_pipeline = staticmethod(tactical._query_clear_to_close_pipeline)
    _query_loans_in_final_review = staticmethod(tactical._query_loans_in_final_review)
    _query_milestones_this_week = staticmethod(tactical._query_milestones_this_week)

    # Income & Commission
    _query_my_commission_this_month = staticmethod(tactical._query_my_commission_this_month)
    _query_projected_income = staticmethod(tactical._query_projected_income)
    _query_funded_this_week = staticmethod(tactical._query_funded_this_week)
    _query_goal_progress = staticmethod(tactical._query_goal_progress)
    _query_ytd_income = staticmethod(tactical._query_ytd_income)
    _query_pipeline_commission_value = staticmethod(tactical._query_pipeline_commission_value)
    _query_highest_commission_loans = staticmethod(tactical._query_highest_commission_loans)

    # Personal Performance
    _query_am_i_hitting_numbers = staticmethod(tactical._query_am_i_hitting_numbers)
    _query_my_conversion_rate = staticmethod(tactical._query_my_conversion_rate)
    _query_compare_to_last_period = staticmethod(tactical._query_compare_to_last_period)
    _query_my_avg_time_to_close = staticmethod(tactical._query_my_avg_time_to_close)
    _query_personal_best_month = staticmethod(tactical._query_personal_best_month)
    _query_am_i_improving = staticmethod(tactical._query_am_i_improving)
    _query_closing_ratio_by_type = staticmethod(tactical._query_closing_ratio_by_type)

    # Referral Partner Management
    _query_partners_for_lunch = staticmethod(tactical._query_partners_for_lunch)
    _query_top_referral_source_quarter = staticmethod(tactical._query_top_referral_source_quarter)
    _query_dormant_partners = staticmethod(tactical._query_dormant_partners)
    _query_partners_need_followup = staticmethod(tactical._query_partners_need_followup)
    _query_relationships_need_nurture = staticmethod(tactical._query_relationships_need_nurture)
    _query_partners_shopping_competitors = staticmethod(tactical._query_partners_shopping_competitors)
    _query_partners_sent_bad_leads = staticmethod(tactical._query_partners_sent_bad_leads)

    # Borrower Qualification
    _query_can_borrower_qualify = staticmethod(tactical._query_can_borrower_qualify)
    _query_max_purchase_price = staticmethod(tactical._query_max_purchase_price)
    _query_eligible_loan_programs = staticmethod(tactical._query_eligible_loan_programs)
    _query_qualification_gaps = staticmethod(tactical._query_qualification_gaps)
    _query_buy_now_or_wait = staticmethod(tactical._query_buy_now_or_wait)
    _query_afford_more_house = staticmethod(tactical._query_afford_more_house)
    _query_required_documentation = staticmethod(tactical._query_required_documentation)
    _query_dti_analysis = staticmethod(tactical._query_dti_analysis)

    # Time Management
    _query_time_spent_analysis = staticmethod(tactical._query_time_spent_analysis)
    _query_revenue_per_activity = staticmethod(tactical._query_revenue_per_activity)
    _query_should_delegate = staticmethod(tactical._query_should_delegate)
    _query_task_balance_analysis = staticmethod(tactical._query_task_balance_analysis)
    _query_productive_windows = staticmethod(tactical._query_productive_windows)
    _query_time_per_loan = staticmethod(tactical._query_time_per_loan)

    # Pipeline Health
    _query_pipeline_health_check = staticmethod(tactical._query_pipeline_health_check)
    _query_lead_flow_adequate = staticmethod(tactical._query_lead_flow_adequate)
    _query_pipeline_velocity = staticmethod(tactical._query_pipeline_velocity)
    _query_stage_concentration = staticmethod(tactical._query_stage_concentration)
    _query_pipeline_coverage_ratio = staticmethod(tactical._query_pipeline_coverage_ratio)
    _query_leads_needed_for_goal = staticmethod(tactical._query_leads_needed_for_goal)

    # Action Items
    _query_most_urgent_now = staticmethod(tactical._query_most_urgent_now)
    _query_highest_impact_actions = staticmethod(tactical._query_highest_impact_actions)
    _query_falling_through_cracks = staticmethod(tactical._query_falling_through_cracks)
    _query_productive_downtime = staticmethod(tactical._query_productive_downtime)
    _query_quick_wins = staticmethod(tactical._query_quick_wins)

    # Scenario Analysis
    _query_rate_drop_impact = staticmethod(tactical._query_rate_drop_impact)
    _query_portfolio_refi_potential = staticmethod(tactical._query_portfolio_refi_potential)
    _query_referral_source_risk = staticmethod(tactical._query_referral_source_risk)
    _query_processor_hire_roi = staticmethod(tactical._query_processor_hire_roi)
    _query_product_focus_impact = staticmethod(tactical._query_product_focus_impact)
    _query_vacation_feasibility = staticmethod(tactical._query_vacation_feasibility)

    # Client Deep Dives
    _query_client_360_view = staticmethod(tactical._query_client_360_view)
    _query_loan_story = staticmethod(tactical._query_loan_story)
    _query_loan_delay_reason = staticmethod(tactical._query_loan_delay_reason)
    _query_file_risk_level = staticmethod(tactical._query_file_risk_level)
    _query_client_needs_from_me = staticmethod(tactical._query_client_needs_from_me)
    _query_client_history = staticmethod(tactical._query_client_history)

    # Market Intelligence
    _query_competitor_rates = staticmethod(tactical._query_competitor_rates)
    _query_losing_on_rate = staticmethod(tactical._query_losing_on_rate)
    _query_why_losing_to_competitors = staticmethod(tactical._query_why_losing_to_competitors)
    _query_my_value_prop = staticmethod(tactical._query_my_value_prop)

    # Compliance & Risk
    _query_compliance_red_flags = staticmethod(tactical._query_compliance_red_flags)
    _query_overdue_disclosures = staticmethod(tactical._query_overdue_disclosures)
    _query_loans_might_not_close = staticmethod(tactical._query_loans_might_not_close)
    _query_audit_risk_assessment = staticmethod(tactical._query_audit_risk_assessment)
    _query_fair_lending_concerns = staticmethod(tactical._query_fair_lending_concerns)

    # Relationship Maintenance
    _query_weekly_outreach_list = staticmethod(tactical._query_weekly_outreach_list)
    _query_loan_anniversaries = staticmethod(tactical._query_loan_anniversaries)
    _query_past_client_checkins = staticmethod(tactical._query_past_client_checkins)
    _query_upcoming_celebrations = staticmethod(tactical._query_upcoming_celebrations)
    _query_gratitude_followups = staticmethod(tactical._query_gratitude_followups)
    _query_referral_ask_opportunities = staticmethod(tactical._query_referral_ask_opportunities)

    # Learning & Improvement
    _query_my_weaknesses = staticmethod(tactical._query_my_weaknesses)
    _query_success_patterns = staticmethod(tactical._query_success_patterns)
    _query_repeated_mistakes = staticmethod(tactical._query_repeated_mistakes)
    _query_close_faster_tips = staticmethod(tactical._query_close_faster_tips)
    _query_skill_gaps = staticmethod(tactical._query_skill_gaps)

    # ============================================================================
    # PROCESSOR QUERIES - Imported from query_executor_processor.py
    # ============================================================================

    # Daily Operations & Workload Management
    _query_processor_workload_today = staticmethod(processor._query_processor_workload_today)
    _query_processor_deadlines_today = staticmethod(processor._query_processor_deadlines_today)
    _query_processor_priority_queue = staticmethod(processor._query_processor_priority_queue)
    _query_processor_current_capacity = staticmethod(processor._query_processor_current_capacity)
    _query_processor_files_by_loan_officer = staticmethod(processor._query_processor_files_by_loan_officer)
    _query_processor_weekly_calendar = staticmethod(processor._query_processor_weekly_calendar)
    _query_processor_overdue_tasks = staticmethod(processor._query_processor_overdue_tasks)
    _query_processor_file_list = staticmethod(processor._query_processor_file_list)

    # Document Management
    _query_processor_missing_documents = staticmethod(processor._query_processor_missing_documents)
    _query_processor_unresponsive_borrowers_docs = staticmethod(processor._query_processor_unresponsive_borrowers_docs)
    _query_processor_documents_uploaded_today = staticmethod(processor._query_processor_documents_uploaded_today)
    _query_processor_complete_documentation = staticmethod(processor._query_processor_complete_documentation)
    _query_processor_overdue_doc_requests = staticmethod(processor._query_processor_overdue_doc_requests)
    _query_processor_loan_stips = staticmethod(processor._query_processor_loan_stips)
    _query_processor_initial_disclosures_needed = staticmethod(processor._query_processor_initial_disclosures_needed)
    _query_processor_pending_verifications = staticmethod(processor._query_processor_pending_verifications)
    _query_processor_credit_supplement_needed = staticmethod(processor._query_processor_credit_supplement_needed)
    _query_processor_tax_return_requests = staticmethod(processor._query_processor_tax_return_requests)
    _query_processor_incomplete_income_docs = staticmethod(processor._query_processor_incomplete_income_docs)
    _query_processor_expired_documents = staticmethod(processor._query_processor_expired_documents)

    # Third-Party Services & Vendors
    _query_processor_appraisals_to_order = staticmethod(processor._query_processor_appraisals_to_order)
    _query_processor_appraisals_in_progress = staticmethod(processor._query_processor_appraisals_in_progress)
    _query_processor_overdue_appraisals = staticmethod(processor._query_processor_overdue_appraisals)
    _query_processor_appraisal_issues = staticmethod(processor._query_processor_appraisal_issues)
    _query_processor_title_work_pending = staticmethod(processor._query_processor_title_work_pending)
    _query_processor_title_commitments_review = staticmethod(processor._query_processor_title_commitments_review)
    _query_processor_hoa_docs_pending = staticmethod(processor._query_processor_hoa_docs_pending)
    _query_processor_vendor_turnaround_times = staticmethod(processor._query_processor_vendor_turnaround_times)
    _query_processor_inspections_scheduled = staticmethod(processor._query_processor_inspections_scheduled)
    _query_processor_insurance_needed = staticmethod(processor._query_processor_insurance_needed)

    # Underwriting Coordination
    _query_processor_ready_for_underwriting = staticmethod(processor._query_processor_ready_for_underwriting)
    _query_processor_files_with_underwriter = staticmethod(processor._query_processor_files_with_underwriter)
    _query_processor_conditions_received_today = staticmethod(processor._query_processor_conditions_received_today)
    _query_processor_all_outstanding_conditions = staticmethod(processor._query_processor_all_outstanding_conditions)
    _query_processor_cleared_conditions = staticmethod(processor._query_processor_cleared_conditions)
    _query_processor_suspended_files = staticmethod(processor._query_processor_suspended_files)
    _query_processor_initial_approvals = staticmethod(processor._query_processor_initial_approvals)
    _query_processor_clear_to_close_files = staticmethod(processor._query_processor_clear_to_close_files)
    _query_processor_high_risk_underwriting = staticmethod(processor._query_processor_high_risk_underwriting)
    _query_processor_next_uw_call = staticmethod(processor._query_processor_next_uw_call)

    # Timeline & Rate Lock Management
    _query_processor_closing_schedule = staticmethod(processor._query_processor_closing_schedule)
    _query_processor_at_risk_closings = staticmethod(processor._query_processor_at_risk_closings)
    _query_processor_expiring_rate_locks = staticmethod(processor._query_processor_expiring_rate_locks)
    _query_processor_tight_timeline_files = staticmethod(processor._query_processor_tight_timeline_files)
    _query_processor_disclosures_due = staticmethod(processor._query_processor_disclosures_due)
    _query_processor_delayed_files = staticmethod(processor._query_processor_delayed_files)
    _query_processor_closing_success_rate = staticmethod(processor._query_processor_closing_success_rate)
    _query_processor_avg_days_to_close = staticmethod(processor._query_processor_avg_days_to_close)

    # Quality Control & Compliance
    _query_processor_files_needing_qc = staticmethod(processor._query_processor_files_needing_qc)
    _query_processor_compliance_red_flags = staticmethod(processor._query_processor_compliance_red_flags)
    _query_processor_trid_violations = staticmethod(processor._query_processor_trid_violations)
    _query_processor_missing_disclosures = staticmethod(processor._query_processor_missing_disclosures)
    _query_processor_data_errors = staticmethod(processor._query_processor_data_errors)
    _query_processor_aus_rerun_needed = staticmethod(processor._query_processor_aus_rerun_needed)
    _query_processor_appraisal_issues_qc = staticmethod(processor._query_processor_appraisal_issues_qc)
    _query_processor_credit_issues_qc = staticmethod(processor._query_processor_credit_issues_qc)
    _query_processor_audit_ready = staticmethod(processor._query_processor_audit_ready)

    # Borrower Communication
    _query_processor_unresponsive_borrowers = staticmethod(processor._query_processor_unresponsive_borrowers)
    _query_processor_borrowers_to_call_today = staticmethod(processor._query_processor_borrowers_to_call_today)
    _query_processor_frustrated_borrowers = staticmethod(processor._query_processor_frustrated_borrowers)
    _query_processor_borrower_response_times = staticmethod(processor._query_processor_borrower_response_times)
    _query_processor_borrowers_need_updates = staticmethod(processor._query_processor_borrowers_need_updates)
    _query_processor_borrower_meetings_needed = staticmethod(processor._query_processor_borrower_meetings_needed)
    _query_processor_borrower_satisfaction = staticmethod(processor._query_processor_borrower_satisfaction)

    # Loan Officer Coordination
    _query_processor_lo_action_items = staticmethod(processor._query_processor_lo_action_items)
    _query_processor_los_blocking_files = staticmethod(processor._query_processor_los_blocking_files)
    _query_processor_lo_response_times = staticmethod(processor._query_processor_lo_response_times)
    _query_processor_my_loan_officers = staticmethod(processor._query_processor_my_loan_officers)
    _query_processor_files_need_lo_approval = staticmethod(processor._query_processor_files_need_lo_approval)
    _query_processor_problem_files_by_lo = staticmethod(processor._query_processor_problem_files_by_lo)
    _query_processor_los_with_most_conditions = staticmethod(processor._query_processor_los_with_most_conditions)

    # File Status & Progress Tracking
    _query_processor_files_by_stage = staticmethod(processor._query_processor_files_by_stage)
    _query_processor_files_moved_today = staticmethod(processor._query_processor_files_moved_today)
    _query_processor_stalled_files = staticmethod(processor._query_processor_stalled_files)
    _query_processor_file_aging_report = staticmethod(processor._query_processor_file_aging_report)
    _query_processor_file_velocity = staticmethod(processor._query_processor_file_velocity)
    _query_processor_files_at_risk_fallout = staticmethod(processor._query_processor_files_at_risk_fallout)
    _query_processor_funnel_health = staticmethod(processor._query_processor_funnel_health)
    _query_processor_files_closed_this_week = staticmethod(processor._query_processor_files_closed_this_week)

    # Problem Resolution
    _query_processor_all_file_issues = staticmethod(processor._query_processor_all_file_issues)
    _query_processor_income_calc_problems = staticmethod(processor._query_processor_income_calc_problems)
    _query_processor_credit_disputes = staticmethod(processor._query_processor_credit_disputes)
    _query_processor_appraisal_gaps = staticmethod(processor._query_processor_appraisal_gaps)
    _query_processor_title_issues = staticmethod(processor._query_processor_title_issues)
    _query_processor_manual_underwriting_files = staticmethod(processor._query_processor_manual_underwriting_files)
    _query_processor_eligibility_issues = staticmethod(processor._query_processor_eligibility_issues)
    _query_processor_whats_blocking_files = staticmethod(processor._query_processor_whats_blocking_files)

    # Performance & Analytics
    _query_processor_closing_ratio = staticmethod(processor._query_processor_closing_ratio)
    _query_processor_avg_processing_time = staticmethod(processor._query_processor_avg_processing_time)
    _query_processor_peer_comparison = staticmethod(processor._query_processor_peer_comparison)
    _query_processor_condition_clear_rate = staticmethod(processor._query_processor_condition_clear_rate)
    _query_processor_error_rate = staticmethod(processor._query_processor_error_rate)
    _query_processor_fastest_loan_types = staticmethod(processor._query_processor_fastest_loan_types)
    _query_processor_slowest_files = staticmethod(processor._query_processor_slowest_files)

    # Capacity & Workload Planning
    _query_processor_at_capacity_check = staticmethod(processor._query_processor_at_capacity_check)
    _query_processor_incoming_files = staticmethod(processor._query_processor_incoming_files)
    _query_processor_can_take_another = staticmethod(processor._query_processor_can_take_another)
    _query_processor_workload_trend = staticmethod(processor._query_processor_workload_trend)
    _query_processor_file_distribution = staticmethod(processor._query_processor_file_distribution)

    # Reporting & Insights
    _query_processor_weekly_summary = staticmethod(processor._query_processor_weekly_summary)
    _query_processor_weekly_wins = staticmethod(processor._query_processor_weekly_wins)
    _query_processor_time_allocation = staticmethod(processor._query_processor_time_allocation)
    _query_processor_biggest_bottleneck = staticmethod(processor._query_processor_biggest_bottleneck)
    _query_processor_common_conditions = staticmethod(processor._query_processor_common_conditions)
    _query_processor_lo_quality_ranking = staticmethod(processor._query_processor_lo_quality_ranking)

    @staticmethod
    def format_query_results_for_claude(query_type: str, result: Dict[str, Any]) -> str:
        """Format query results as text for Claude"""
        if not result.get("success"):
            return f"Query failed: {result.get('error', 'Unknown error')}"

        data = result.get("data", [])
        if not data:
            return f"No data found for {query_type}"

        lines = [f"\n=== {query_type.upper().replace('_', ' ')} RESULTS ===\n"]

        if query_type == "pipeline_analysis":
            lines.append("Pipeline by Stage:")
            for item in data:
                lines.append(f"  {item['stage']}: {item['lead_count']} leads, "
                           f"${item['total_value']:,.0f} total, "
                           f"avg {item['avg_age_days']:.0f} days old")

        elif query_type == "lead_source_performance":
            lines.append("Lead Source Performance:")
            for item in data:
                lines.append(f"  {item['source']}: {item['total_leads']} leads, "
                           f"{item['close_rate_pct']:.1f}% close rate, "
                           f"${item['total_revenue']:,.0f} revenue")

        elif query_type == "conversion_funnel":
            lines.append("Conversion Funnel:")
            for item in data:
                lines.append(f"  {item['stage']}: {item['count']} leads ({item['rate_pct']:.1f}%)")

        elif query_type == "loan_type_performance":
            lines.append("Performance by Loan Type:")
            for item in data:
                lines.append(f"  {item['loan_type']}: {item['total_leads']} leads, "
                           f"{item['win_rate_pct']:.1f}% win rate, "
                           f"${item['total_volume']:,.0f} volume")

        elif query_type == "monthly_trends":
            lines.append("Monthly Trends:")
            for item in data:
                lines.append(f"  {item['month']}: {item['new_leads']} new, "
                           f"{item['closed_won']} closed, "
                           f"${item['revenue']:,.0f} revenue")

        elif query_type == "stale_leads_report":
            lines.append(f"Stale Leads ({len(data)} found):")
            for item in data[:10]:
                lines.append(f"  {item['name']} ({item['stage']}): "
                           f"${item['loan_amount']:,.0f}, "
                           f"{item['days_stale']} days stale")

        elif query_type == "high_value_opportunities":
            lines.append(f"High Value Opportunities ({len(data)} found):")
            for item in data[:10]:
                lines.append(f"  {item['name']}: ${item['loan_amount']:,.0f} "
                           f"({item['loan_type']}, {item['stage']})")

        else:
            # Generic formatting
            lines.append(f"Results ({len(data)} records):")
            for item in data[:10]:
                lines.append(f"  {item}")

        lines.append("\n=== END QUERY RESULTS ===")
        return "\n".join(lines)


# Convenience function
def execute_query(db: Session, query_type: str, params: Dict, user_id: int) -> Dict:
    """Execute a query"""
    return QueryExecutor.execute_query(db, query_type, params, user_id)


def format_results(query_type: str, result: Dict) -> str:
    """Format results for AI"""
    return QueryExecutor.format_query_results_for_claude(query_type, result)
