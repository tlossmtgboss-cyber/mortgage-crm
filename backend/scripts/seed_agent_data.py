"""
Seed all 20 Perennia AI agents with complete data
Run after database migration: python backend/scripts/seed_agent_data.py
"""
import sys
import os
import random
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta, timezone
from database import SessionLocal
from models.agent_governance import (
    AgentProfile, AgentExecution, AgentAlert, AgentMetricsTimeseries,
    TrainingScenario, TrainingSession
)

def seed_agents(db):
    """Seed all 20 Perennia AI agents"""

    agents_data = [
        {
            "agent_name": "receptionist",
            "display_name": "AI Receptionist",
            "description": "Voice/chat receptionist for inbound calls & queries. Handles all inbound communication, routes to appropriate team members, captures leads.",
            "category": "communication",
            "capabilities": ["call_routing", "lead_capture", "appointment_scheduling", "faq_handling", "callback_scheduling"],
            "model_name": "claude-3-sonnet",
            "tools_available": ["route_call", "capture_lead", "schedule_callback", "get_availability", "send_sms", "answer_faq", "transfer_to_agent", "log_interaction"]
        },
        {
            "agent_name": "task_automation",
            "display_name": "Task Automation",
            "description": "Task creation, scheduling & workflow automation. Automates task management across all workflows.",
            "category": "operations",
            "capabilities": ["task_creation", "task_scheduling", "workflow_automation", "task_assignment", "recurring_tasks"],
            "model_name": "claude-3-sonnet",
            "tools_available": ["create_task", "schedule_task", "assign_task", "complete_task", "get_overdue_tasks", "create_recurring_task", "send_reminder", "update_workflow", "get_task_status"]
        },
        {
            "agent_name": "profitability_analyst",
            "display_name": "Profitability Analyst",
            "description": "Loan & branch profitability analysis. Analyzes financial performance at loan and branch level.",
            "category": "analytics",
            "capabilities": ["loan_profitability", "branch_analysis", "cost_analysis", "revenue_forecasting", "margin_optimization"],
            "model_name": "claude-3-sonnet",
            "tools_available": ["calculate_loan_profitability", "analyze_branch_performance", "get_cost_breakdown", "forecast_revenue", "compare_to_benchmark", "generate_profitability_report", "identify_cost_drivers", "calculate_margin"]
        },
        {
            "agent_name": "subscription_manager",
            "display_name": "Subscription Manager",
            "description": "SaaS subscription & billing management. Manages all subscription plans, billing, and feature access.",
            "category": "operations",
            "capabilities": ["plan_management", "billing_processing", "payment_handling", "feature_access", "invoice_generation"],
            "model_name": "claude-3-sonnet",
            "tools_available": ["get_subscription_status", "upgrade_plan", "downgrade_plan", "process_payment", "handle_payment_failure", "generate_invoice", "manage_feature_access", "apply_discount"]
        },
        {
            "agent_name": "compliance_checker",
            "display_name": "Compliance Checker",
            "description": "TRID, RESPA, fair lending compliance. Authoritative source for all compliance determinations.",
            "category": "compliance",
            "capabilities": ["trid_verification", "respa_compliance", "fair_lending_check", "timeline_validation", "risk_flagging"],
            "model_name": "claude-3-sonnet",
            "tools_available": ["check_trid_compliance", "check_respa_compliance", "check_fair_lending", "get_state_requirements", "audit_loan_file", "get_disclosure_timeline", "check_tolerance_violations", "get_compliance_history"]
        },
        {
            "agent_name": "onboarding_assistant",
            "display_name": "Onboarding Assistant",
            "description": "New user onboarding & training. Guides new users through setup and training.",
            "category": "operations",
            "capabilities": ["setup_guidance", "training_assignment", "progress_tracking", "question_answering", "issue_escalation"],
            "model_name": "claude-3-sonnet",
            "tools_available": ["start_onboarding", "get_onboarding_status", "assign_training", "track_progress", "answer_question", "escalate_issue", "complete_step", "send_reminder"]
        },
        {
            "agent_name": "document_tracker",
            "display_name": "Document Tracker",
            "description": "Document collection & condition tracking. Manages all document requirements and tracking.",
            "category": "operations",
            "capabilities": ["document_tracking", "collection_monitoring", "reminder_sending", "document_classification", "issue_flagging"],
            "model_name": "claude-3-sonnet",
            "tools_available": ["get_missing_documents", "get_loan_conditions", "track_document_request", "send_document_reminder", "escalate_issue", "get_document_timeline", "check_document_expiration", "get_third_party_status"]
        },
        {
            "agent_name": "voice_agent",
            "display_name": "Voice OS",
            "description": "Voice command processing & interaction. Processes voice commands and provides voice responses.",
            "category": "communication",
            "capabilities": ["voice_processing", "speech_to_action", "voice_response", "conversation_handling", "phone_integration"],
            "model_name": "claude-3-sonnet",
            "tools_available": ["process_voice_command", "convert_speech_to_text", "generate_voice_response", "handle_conversation", "transfer_call", "record_call", "get_call_summary", "dial_number"]
        },
        {
            "agent_name": "lead_nurturer",
            "display_name": "Lead Nurturer",
            "description": "Lead scoring, follow-up & conversion. Automates lead management and conversion optimization.",
            "category": "sales",
            "capabilities": ["lead_scoring", "followup_automation", "outreach_personalization", "engagement_tracking", "hot_lead_identification"],
            "model_name": "claude-3-sonnet",
            "tools_available": ["get_lead_details", "get_engagement_history", "score_lead", "suggest_followup", "draft_message", "schedule_outreach", "get_similar_converted_leads", "get_optimal_contact_time"]
        },
        {
            "agent_name": "team_coach",
            "display_name": "Team Coach",
            "description": "LO performance coaching & benchmarking. Provides performance insights and coaching recommendations.",
            "category": "analytics",
            "capabilities": ["performance_analysis", "improvement_identification", "coaching_recommendations", "peer_benchmarking", "skill_tracking"],
            "model_name": "claude-3-sonnet",
            "tools_available": ["get_lo_performance", "identify_improvement_areas", "generate_coaching_tips", "benchmark_against_peers", "track_skill_development", "get_team_rankings", "schedule_coaching_session", "get_performance_trend"]
        },
        {
            "agent_name": "sla_monitor",
            "display_name": "SLA Tracker",
            "description": "SLA monitoring & milestone tracking. Monitors all loan milestones and SLA compliance.",
            "category": "monitoring",
            "capabilities": ["milestone_tracking", "sla_monitoring", "breach_alerting", "report_generation", "risk_prediction"],
            "model_name": "claude-3-sonnet",
            "tools_available": ["track_milestones", "check_sla_compliance", "send_breach_alert", "generate_sla_report", "predict_at_risk_loans", "get_sla_history", "update_milestone", "get_team_sla_summary"]
        },
        {
            "agent_name": "pipeline_analyst",
            "display_name": "Pipeline Analyst",
            "description": "Pipeline metrics, velocity & forecasting. Analyzes pipeline health and forecasts closings.",
            "category": "analytics",
            "capabilities": ["pipeline_analysis", "velocity_calculation", "closing_forecast", "bottleneck_identification", "report_generation"],
            "model_name": "claude-3-sonnet",
            "tools_available": ["get_pipeline_metrics", "get_loans_by_status", "get_loan_aging_report", "calculate_conversion_rates", "predict_closing_timeline", "get_bottleneck_analysis", "compare_to_benchmark", "get_lo_pipeline_breakdown"]
        },
        {
            "agent_name": "email_intel_agent",
            "display_name": "Email Intelligence",
            "description": "Email parsing, response & training. Handles all email processing and response generation.",
            "category": "automation",
            "capabilities": ["email_parsing", "information_extraction", "response_generation", "email_categorization", "pattern_training"],
            "model_name": "claude-3-sonnet",
            "tools_available": ["parse_email", "extract_key_info", "generate_response_draft", "categorize_email", "train_on_pattern", "get_email_summary", "flag_urgent_email", "auto_reply", "forward_to_team", "create_task_from_email", "link_to_loan", "get_email_history"]
        },
        {
            "agent_name": "notification_center",
            "display_name": "Notification Center",
            "description": "Push/email/SMS notification management. Manages all outbound notifications across channels.",
            "category": "automation",
            "capabilities": ["push_notifications", "email_alerts", "sms_messaging", "preference_management", "delivery_tracking"],
            "model_name": "claude-3-sonnet",
            "tools_available": ["send_push", "send_email", "send_sms", "manage_preferences", "track_delivery", "schedule_notification", "get_engagement_stats", "batch_notify"]
        },
        {
            "agent_name": "customer_intelligence",
            "display_name": "Customer Intelligence",
            "description": "Customer lifecycle & retention analysis. Analyzes customer behavior and retention patterns.",
            "category": "analytics",
            "capabilities": ["lifecycle_analysis", "churn_prediction", "upsell_identification", "satisfaction_tracking", "retention_strategies"],
            "model_name": "claude-3-sonnet",
            "tools_available": ["analyze_lifecycle_stage", "predict_churn_risk", "identify_upsell_opportunity", "track_satisfaction", "generate_retention_strategy", "get_customer_timeline", "calculate_ltv", "segment_customers", "get_engagement_score"]
        },
        {
            "agent_name": "scheduler",
            "display_name": "Smart Scheduler",
            "description": "Intelligent meeting & calendar scheduling. Automates scheduling and calendar management.",
            "category": "operations",
            "capabilities": ["availability_finding", "appointment_scheduling", "calendar_invites", "rescheduling", "efficiency_optimization"],
            "model_name": "claude-3-sonnet",
            "tools_available": ["find_availability", "schedule_meeting", "send_calendar_invite", "reschedule_meeting", "cancel_meeting", "optimize_calendar", "get_schedule_summary", "block_time"]
        },
        {
            "agent_name": "video_agent",
            "display_name": "UVIP",
            "description": "Unified Video Intelligence Platform. Processes video content for meetings and async messaging.",
            "category": "analytics",
            "capabilities": ["meeting_recording", "transcription", "summary_generation", "action_extraction", "conversation_analysis"],
            "model_name": "claude-3-sonnet",
            "tools_available": ["record_meeting", "transcribe_video", "generate_summary", "extract_action_items", "analyze_conversation", "create_video_message", "share_video", "get_meeting_insights"]
        },
        {
            "agent_name": "integrations_agent",
            "display_name": "Integrations",
            "description": "Third-party integration management. Manages all external system integrations.",
            "category": "operations",
            "capabilities": ["system_connection", "data_sync", "api_authentication", "health_monitoring", "troubleshooting"],
            "model_name": "claude-3-sonnet",
            "tools_available": ["connect_system", "sync_data", "authenticate_api", "monitor_health", "troubleshoot_connection", "get_integration_status", "map_fields", "test_connection"]
        },
        {
            "agent_name": "reporting_engine",
            "display_name": "Reporting Engine",
            "description": "Report generation & analytics. Generates reports and analytics dashboards.",
            "category": "analytics",
            "capabilities": ["scheduled_reports", "adhoc_analytics", "data_export", "metric_visualization", "report_distribution"],
            "model_name": "claude-3-sonnet",
            "tools_available": ["generate_report", "create_adhoc_query", "export_data", "visualize_metrics", "schedule_report", "distribute_report", "get_report_history", "create_dashboard"]
        },
        {
            "agent_name": "rate_advisor",
            "display_name": "Rate Advisor",
            "description": "Rate lock, pricing & float-down advice. Provides rate guidance and processes rate locks.",
            "category": "advisory",
            "capabilities": ["rate_quotes", "lock_timing_advice", "rate_lock_processing", "trend_monitoring", "float_down_recommendations"],
            "model_name": "claude-3-sonnet",
            "tools_available": ["get_current_rates", "quote_rate", "advise_on_lock_timing", "process_rate_lock", "monitor_rate_trends", "recommend_float_down", "compare_loan_options", "get_rate_history"]
        }
    ]

    print("Starting agent data seed...")

    for idx, data in enumerate(agents_data, 1):
        print(f"\nCreating Agent #{idx}: {data['display_name']}")

        # Build config with model settings and capabilities
        config = {
            "model_name": data["model_name"],
            "temperature": 0.7,
            "max_tokens": 4096,
            "system_prompt": f"You are {data['display_name']}, a specialized AI agent for {data['description']}",
            "capabilities": data["capabilities"],
            "tools_available": data["tools_available"]
        }

        total_executions = random.randint(1000, 10000)
        base_success_rate = random.uniform(0.88, 0.98)
        successful_executions = int(total_executions * base_success_rate)

        # Create agent profile
        agent = AgentProfile(
            agent_name=data["agent_name"],
            display_name=data["display_name"],
            description=data["description"],
            category=data["category"],
            status="active",
            health_status="healthy",
            version="1.0.0",
            tool_count=len(data["tools_available"]),
            config=config,
            total_executions=total_executions,
            successful_executions=successful_executions,
            failed_executions=total_executions - successful_executions,
            success_rate=base_success_rate * 100,
            avg_response_time_ms=random.randint(500, 2000),
            last_execution_at=datetime.now(timezone.utc) - timedelta(minutes=random.randint(1, 60)),
            last_health_check=datetime.now(timezone.utc) - timedelta(minutes=random.randint(1, 10))
        )

        db.add(agent)
        db.flush()  # Get agent.id

        print(f"   Created agent profile (ID: {agent.id})")

    db.commit()
    print("\nAll 20 agents seeded successfully!")


def seed_sample_metrics(db):
    """Create sample metrics for visualization"""
    print("\nGenerating sample metrics for last 7 days...")

    agents = db.query(AgentProfile).all()

    for agent in agents:
        # Generate hourly metrics for last 7 days
        for days_ago in range(7):
            for hour in [0, 6, 12, 18]:  # 4 data points per day
                timestamp = datetime.now(timezone.utc) - timedelta(days=days_ago, hours=hour)

                # Simulate realistic metrics
                execution_count = random.randint(20, 150)
                success_count = int(execution_count * random.uniform(0.88, 0.98))
                failure_count = execution_count - success_count

                metric = AgentMetricsTimeseries(
                    agent_id=agent.id,
                    agent_name=agent.agent_name,
                    timestamp=timestamp,
                    period_type="hour",
                    execution_count=execution_count,
                    success_count=success_count,
                    failure_count=failure_count,
                    avg_response_time_ms=random.randint(500, 2500),
                    min_response_time_ms=random.randint(200, 500),
                    max_response_time_ms=random.randint(3000, 8000),
                    total_cost=round(random.uniform(0.5, 5.0), 2),
                    total_tokens=random.randint(5000, 50000),
                    error_rate=round((failure_count / execution_count) * 100, 2),
                    tool_usage={}
                )
                db.add(metric)

    db.commit()
    print("   Generated sample metrics")


def seed_sample_alerts(db):
    """Create sample alerts"""
    print("\nCreating sample alerts...")

    agents = db.query(AgentProfile).limit(5).all()

    alert_data = [
        {
            "agent": agents[0] if len(agents) > 0 else None,
            "alert_type": "performance",
            "severity": "warning",
            "title": "Response time above threshold",
            "message": "P95 response time is 12.5s, above threshold of 10s"
        },
        {
            "agent": agents[1] if len(agents) > 1 else None,
            "alert_type": "health",
            "severity": "critical",
            "title": "Increased failure rate detected",
            "message": "Failure rate increased from 2% to 8% in last hour"
        },
        {
            "agent": agents[2] if len(agents) > 2 else None,
            "alert_type": "cost",
            "severity": "warning",
            "title": "Daily budget at 85%",
            "message": "Agent has consumed 85% of daily budget"
        }
    ]

    for data in alert_data:
        if data["agent"]:
            alert = AgentAlert(
                agent_id=data["agent"].id,
                agent_name=data["agent"].agent_name,
                alert_type=data["alert_type"],
                severity=data["severity"],
                title=data["title"],
                message=data["message"],
                status="active",
                details={}
            )
            db.add(alert)

    db.commit()
    print(f"   Created sample alerts")


def seed_gym_scenarios(db):
    """Create training scenarios for gym"""
    print("\nCreating gym training scenarios...")

    agents = db.query(AgentProfile).all()
    agent_map = {a.agent_name: a for a in agents}

    scenarios_data = [
        {
            "agent_name": "compliance_checker",
            "name": "Basic TRID Timeline Check",
            "description": "Verify TRID compliance for standard purchase loan timeline",
            "category": "happy_path",
            "difficulty": "easy",
            "test_prompt": "Check TRID compliance: Application 12/1, Initial Disclosure 12/2, Closing 12/20",
            "expected_output_contains": ["compliant", "disclosure"],
            "success_criteria": ["Uses check_trid_compliance tool", "Identifies disclosure timing", "Reports compliance status"]
        },
        {
            "agent_name": "compliance_checker",
            "name": "Short Timeline Violation",
            "description": "Detect TRID violation with insufficient waiting period",
            "category": "edge_case",
            "difficulty": "medium",
            "test_prompt": "Check compliance: Application 12/15, Closing 12/20 - only 5 days between",
            "expected_output_contains": ["violation", "insufficient", "waiting period"],
            "success_criteria": ["Detects timeline violation", "Explains minimum requirements", "Suggests remediation"]
        },
        {
            "agent_name": "pipeline_analyst",
            "name": "Pipeline Health Check",
            "description": "Analyze overall pipeline health and identify bottlenecks",
            "category": "happy_path",
            "difficulty": "easy",
            "test_prompt": "Analyze the current pipeline health for branch 5 and identify any bottlenecks",
            "expected_output_contains": ["pipeline", "bottleneck", "loans"],
            "success_criteria": ["Uses get_pipeline_metrics", "Identifies bottleneck stages", "Provides recommendations"]
        },
        {
            "agent_name": "lead_nurturer",
            "name": "Lead Qualification",
            "description": "Score and qualify a new lead",
            "category": "happy_path",
            "difficulty": "easy",
            "test_prompt": "Evaluate lead ID 789: First-time buyer, $75k income, 720 credit score, looking to buy in 3 months",
            "expected_output_contains": ["score", "qualified", "follow-up"],
            "success_criteria": ["Retrieves lead details", "Calculates lead score", "Suggests appropriate follow-up"]
        },
        {
            "agent_name": "document_tracker",
            "name": "Document Status Review",
            "description": "Review missing documents for a loan",
            "category": "happy_path",
            "difficulty": "easy",
            "test_prompt": "What documents are missing for loan #54321 and what is the status of outstanding requests?",
            "expected_output_contains": ["missing", "documents", "status"],
            "success_criteria": ["Lists missing documents", "Shows request dates", "Suggests next steps"]
        },
        {
            "agent_name": "rate_advisor",
            "name": "Rate Comparison",
            "description": "Compare loan options and provide recommendation",
            "category": "happy_path",
            "difficulty": "medium",
            "test_prompt": "Compare 30-year fixed vs 15-year fixed for a $400k loan with 20% down, borrower wants lowest monthly payment",
            "expected_output_contains": ["30-year", "15-year", "monthly payment", "recommend"],
            "success_criteria": ["Fetches current rates", "Compares options", "Provides clear recommendation based on borrower goals"]
        }
    ]

    for data in scenarios_data:
        agent = agent_map.get(data["agent_name"])
        if agent:
            scenario = TrainingScenario(
                name=data["name"],
                description=data["description"],
                category=data["category"],
                target_agent_type=data["agent_name"],
                difficulty=data["difficulty"],
                max_score=100,
                time_limit_seconds=60,
                input_data={
                    "test_prompt": data["test_prompt"],
                    "agent_id": agent.id
                },
                expected_output={
                    "contains": data["expected_output_contains"]
                },
                evaluation_criteria=data["success_criteria"],
                is_active=True,
                times_run=random.randint(50, 200),
                avg_score=round(random.uniform(75, 95), 1)
            )
            db.add(scenario)

    db.commit()
    print(f"   Created {len(scenarios_data)} gym scenarios")


if __name__ == "__main__":
    db = SessionLocal()

    try:
        print("\n" + "="*60)
        print("PERENNIA AI AGENT GOVERNANCE SYSTEM - DATA SEED")
        print("="*60)

        # Check if agents already exist
        existing_count = db.query(AgentProfile).count()
        if existing_count > 0:
            print(f"\nFound {existing_count} existing agents.")
            response = input("Delete and reseed? (yes/no): ")
            if response.lower() == 'yes':
                print("Deleting existing data...")
                db.query(TrainingSession).delete()
                db.query(TrainingScenario).delete()
                db.query(AgentMetricsTimeseries).delete()
                db.query(AgentAlert).delete()
                db.query(AgentExecution).delete()
                db.query(AgentProfile).delete()
                db.commit()
            else:
                print("Aborted.")
                sys.exit(0)

        # Seed all data
        seed_agents(db)
        seed_sample_metrics(db)
        seed_sample_alerts(db)
        seed_gym_scenarios(db)

        # Summary
        print("\n" + "="*60)
        print("SEED COMPLETE!")
        print("="*60)
        print(f"Total agents: {db.query(AgentProfile).count()}")
        print(f"Total metrics records: {db.query(AgentMetricsTimeseries).count()}")
        print(f"Total gym scenarios: {db.query(TrainingScenario).count()}")
        print(f"Total alerts: {db.query(AgentAlert).count()}")
        print("\nSystem ready for testing!")

    except Exception as e:
        print(f"\nError during seed: {str(e)}")
        db.rollback()
        raise
    finally:
        db.close()
