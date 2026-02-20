"""
Seed data for User Creation & Onboarding System
Includes roles, categories, responsibilities, and permission templates
"""

from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


def seed_user_onboarding_data(db, Role, Category, Responsibility, PermissionTemplate,
                               RoleDefaultCategory, RoleDefaultResponsibility):
    """
    Seed the database with initial data for user onboarding system
    """

    # Check if data already exists
    existing_roles = db.query(Role).count()
    if existing_roles > 0:
        logger.info("User onboarding seed data already exists, skipping...")
        return

    logger.info("Seeding user onboarding data...")

    # ========================================================================
    # SEED ROLES
    # ========================================================================
    roles_data = [
        {
            "name": "Site Administrator",
            "description": "Site-level administrator with full system access and multi-role capabilities"
        },
        {
            "name": "Application Analysis",
            "description": "Analyzes and reviews loan applications for eligibility and risk"
        },
        {
            "name": "Concierge",
            "description": "Manages borrower communication, milestone updates, and partner engagement"
        },
        {
            "name": "Jr. Loan Officer",
            "description": "Assists with lead qualification and basic loan processing under supervision"
        },
        {
            "name": "Jr. Processor",
            "description": "Supports loan processing with document collection and condition tracking"
        },
        {
            "name": "Loan Officer",
            "description": "Originates loans, manages borrower relationships, and closes transactions"
        },
        {
            "name": "Loan Officer Assistant",
            "description": "Supports loan officers with administrative tasks and borrower communication"
        },
        {
            "name": "Processing Assistant",
            "description": "Assists processors with documentation and milestone tracking"
        },
        {
            "name": "Processor",
            "description": "Manages complete loan processing from application to clear-to-close"
        },
        {
            "name": "Production Assistant 1",
            "description": "Entry-level support for loan production operations"
        },
        {
            "name": "Production Assistant 2",
            "description": "Mid-level support for loan production with expanded responsibilities"
        },
        {
            "name": "Buyer Agent",
            "description": "Real estate agent representing the buyer in a purchase transaction"
        },
        {
            "name": "Buyers Agent Closing Coordinator",
            "description": "Coordinates closing activities on behalf of the buyer's real estate agent"
        },
        {
            "name": "Listing Agent",
            "description": "Real estate agent representing the seller in a purchase transaction"
        },
        {
            "name": "Listing Agent Closing Coordinator",
            "description": "Coordinates closing activities on behalf of the listing agent"
        }
    ]

    roles = {}
    for role_data in roles_data:
        role = Role(
            name=role_data["name"],
            description=role_data["description"],
            is_active=True
        )
        db.add(role)
        db.flush()
        roles[role_data["name"]] = role
        logger.info(f"  Created role: {role_data['name']}")

    # ========================================================================
    # SEED CATEGORIES
    # ========================================================================
    categories_data = [
        {"name": "Lead Generation", "description": "Activities related to generating and capturing new leads", "sort_order": 1},
        {"name": "Borrower Engagement", "description": "Direct communication and relationship management with borrowers", "sort_order": 2},
        {"name": "Partner Engagement", "description": "Managing relationships with referral partners and external stakeholders", "sort_order": 3},
        {"name": "Application Review", "description": "Initial review and analysis of loan applications", "sort_order": 4},
        {"name": "Pre-Approval Workflow", "description": "Pre-qualification and pre-approval processes", "sort_order": 5},
        {"name": "Processing & Milestones", "description": "Core loan processing tasks and milestone management", "sort_order": 6},
        {"name": "Closing Coordination", "description": "Final steps to close the loan transaction", "sort_order": 7},
        {"name": "Post-Closing / MUM", "description": "Post-closing activities and mortgage under management", "sort_order": 8},
        {"name": "Referral Management", "description": "Managing referral sources and tracking referral performance", "sort_order": 9},
        {"name": "Rate Lock Support", "description": "Rate lock advisory and market monitoring", "sort_order": 10}
    ]

    categories = {}
    for cat_data in categories_data:
        category = Category(
            name=cat_data["name"],
            description=cat_data["description"],
            sort_order=cat_data["sort_order"],
            is_active=True
        )
        db.add(category)
        db.flush()
        categories[cat_data["name"]] = category
        logger.info(f"  Created category: {cat_data['name']}")

    # ========================================================================
    # SEED RESPONSIBILITIES
    # ========================================================================
    responsibilities_data = [
        # Lead Generation
        {
            "name": "Lead qualification",
            "description": "Qualify inbound leads based on pre-defined criteria",
            "category": "Lead Generation",
            "applicable_roles": ["Concierge", "Jr. Loan Officer", "Loan Officer"],
            "kpi_mapping": {
                "daily_kpis": ["leads_contacted", "leads_qualified"],
                "weekly_kpis": ["lead_conversion_rate"]
            }
        },
        {
            "name": "Outbound prospecting",
            "description": "Proactive outreach to generate new leads",
            "category": "Lead Generation",
            "applicable_roles": ["Loan Officer", "Jr. Loan Officer"],
            "kpi_mapping": {
                "daily_kpis": ["outbound_calls_made", "leads_generated"],
                "monthly_kpis": ["prospecting_volume"]
            }
        },
        {
            "name": "Lead follow-up",
            "description": "Systematic follow-up with existing leads",
            "category": "Lead Generation",
            "applicable_roles": ["Concierge", "Loan Officer Assistant", "Production Assistant 1"],
            "kpi_mapping": {
                "daily_kpis": ["follow_up_calls", "emails_sent"],
                "efficiency_scores": ["response_time"]
            }
        },
        # Borrower Engagement
        {
            "name": "Borrower milestone updates",
            "description": "Communicate loan progress and milestones to borrowers",
            "category": "Borrower Engagement",
            "applicable_roles": ["Concierge", "Loan Officer Assistant"],
            "kpi_mapping": {
                "daily_kpis": ["milestone_updates_sent"],
                "communication_scores": ["borrower_satisfaction", "update_timeliness"]
            }
        },
        {
            "name": "Application consultation",
            "description": "Guide borrowers through the application process",
            "category": "Borrower Engagement",
            "applicable_roles": ["Loan Officer", "Jr. Loan Officer"],
            "kpi_mapping": {
                "weekly_kpis": ["consultations_completed"],
                "efficiency_scores": ["consultation_to_app_rate"]
            }
        },
        {
            "name": "Document collection support",
            "description": "Assist borrowers with document gathering",
            "category": "Borrower Engagement",
            "applicable_roles": ["Loan Officer Assistant", "Processing Assistant"],
            "kpi_mapping": {
                "daily_kpis": ["documents_requested", "documents_received"],
                "efficiency_scores": ["document_collection_rate"]
            }
        },
        {
            "name": "Borrower issue resolution",
            "description": "Address and resolve borrower questions and concerns",
            "category": "Borrower Engagement",
            "applicable_roles": ["Loan Officer", "Processor"],
            "kpi_mapping": {
                "daily_kpis": ["issues_resolved"],
                "communication_scores": ["resolution_time", "borrower_satisfaction"]
            }
        },
        # Partner Engagement
        {
            "name": "Weekly partner updates",
            "description": "Provide regular updates to referral partners",
            "category": "Partner Engagement",
            "applicable_roles": ["Concierge", "Loan Officer"],
            "kpi_mapping": {
                "weekly_kpis": ["partner_updates_sent"],
                "referral_scores": ["partner_satisfaction"]
            }
        },
        {
            "name": "Partner relationship management",
            "description": "Build and maintain relationships with referral sources",
            "category": "Partner Engagement",
            "applicable_roles": ["Loan Officer"],
            "kpi_mapping": {
                "monthly_kpis": ["partner_meetings"],
                "referral_scores": ["referral_volume_from_partners"]
            }
        },
        {
            "name": "Partner onboarding",
            "description": "Onboard new referral partners to the system",
            "category": "Partner Engagement",
            "applicable_roles": ["Loan Officer"],
            "kpi_mapping": {
                "monthly_kpis": ["partners_onboarded"]
            }
        },
        # Application Review
        {
            "name": "Initial application review",
            "description": "Review new applications for completeness",
            "category": "Application Review",
            "applicable_roles": ["Application Analysis", "Processor"],
            "kpi_mapping": {
                "daily_kpis": ["applications_reviewed"],
                "efficiency_scores": ["review_time"]
            }
        },
        {
            "name": "Credit analysis",
            "description": "Analyze borrower credit profiles",
            "category": "Application Review",
            "applicable_roles": ["Application Analysis"],
            "kpi_mapping": {
                "daily_kpis": ["credit_analyses_completed"]
            }
        },
        {
            "name": "Income verification",
            "description": "Verify borrower income documentation",
            "category": "Application Review",
            "applicable_roles": ["Application Analysis", "Processor"],
            "kpi_mapping": {
                "daily_kpis": ["income_verifications_completed"]
            }
        },
        # Pre-Approval Workflow
        {
            "name": "Pre-qualification processing",
            "description": "Process pre-qualification requests",
            "category": "Pre-Approval Workflow",
            "applicable_roles": ["Jr. Loan Officer", "Loan Officer"],
            "kpi_mapping": {
                "daily_kpis": ["prequalifications_issued"],
                "efficiency_scores": ["prequal_turnaround_time"]
            }
        },
        {
            "name": "Pre-approval letter generation",
            "description": "Generate and issue pre-approval letters",
            "category": "Pre-Approval Workflow",
            "applicable_roles": ["Loan Officer", "Processor"],
            "kpi_mapping": {
                "weekly_kpis": ["preapprovals_issued"]
            }
        },
        {
            "name": "Pre-approval follow-up",
            "description": "Follow up on pre-approved borrowers",
            "category": "Pre-Approval Workflow",
            "applicable_roles": ["Loan Officer Assistant", "Production Assistant 2"],
            "kpi_mapping": {
                "weekly_kpis": ["preapproval_followups"],
                "efficiency_scores": ["preapproval_to_app_conversion"]
            }
        },
        # Processing & Milestones
        {
            "name": "Milestone tracking",
            "description": "Track and update loan milestones",
            "category": "Processing & Milestones",
            "applicable_roles": ["Processor", "Processing Assistant"],
            "kpi_mapping": {
                "daily_kpis": ["milestones_updated"]
            }
        },
        {
            "name": "Condition management",
            "description": "Manage and clear loan conditions",
            "category": "Processing & Milestones",
            "applicable_roles": ["Processor", "Jr. Processor"],
            "kpi_mapping": {
                "daily_kpis": ["conditions_cleared"],
                "efficiency_scores": ["condition_clearance_rate"]
            }
        },
        {
            "name": "Underwriting coordination",
            "description": "Coordinate with underwriting team",
            "category": "Processing & Milestones",
            "applicable_roles": ["Processor"],
            "kpi_mapping": {
                "daily_kpis": ["uw_submissions"]
            }
        },
        {
            "name": "Title and appraisal ordering",
            "description": "Order title work and appraisals",
            "category": "Processing & Milestones",
            "applicable_roles": ["Processor", "Processing Assistant"],
            "kpi_mapping": {
                "weekly_kpis": ["orders_placed"]
            }
        },
        # Closing Coordination
        {
            "name": "Closing documentation preparation",
            "description": "Prepare final closing documents",
            "category": "Closing Coordination",
            "applicable_roles": ["Processor"],
            "kpi_mapping": {
                "weekly_kpis": ["closing_docs_prepared"]
            }
        },
        {
            "name": "Closing scheduling",
            "description": "Schedule closing appointments",
            "category": "Closing Coordination",
            "applicable_roles": ["Processor", "Processing Assistant"],
            "kpi_mapping": {
                "weekly_kpis": ["closings_scheduled"]
            }
        },
        {
            "name": "Final walkthrough coordination",
            "description": "Coordinate final pre-closing steps",
            "category": "Closing Coordination",
            "applicable_roles": ["Processor", "Loan Officer"],
            "kpi_mapping": {
                "weekly_kpis": ["walkthroughs_completed"]
            }
        },
        # Post-Closing / MUM
        {
            "name": "Post-close check-ins",
            "description": "Follow up with borrowers after closing",
            "category": "Post-Closing / MUM",
            "applicable_roles": ["Concierge", "Loan Officer"],
            "kpi_mapping": {
                "monthly_kpis": ["post_close_contacts"],
                "mum_engagement_scores": ["borrower_retention"]
            }
        },
        {
            "name": "MUM annual reviews",
            "description": "Conduct annual mortgage reviews",
            "category": "Post-Closing / MUM",
            "applicable_roles": ["Loan Officer"],
            "kpi_mapping": {
                "monthly_kpis": ["annual_reviews_completed"],
                "mum_engagement_scores": ["review_completion_rate"]
            }
        },
        {
            "name": "Refinance opportunity identification",
            "description": "Identify and present refi opportunities",
            "category": "Post-Closing / MUM",
            "applicable_roles": ["Loan Officer"],
            "kpi_mapping": {
                "monthly_kpis": ["refi_opportunities_identified"],
                "mum_engagement_scores": ["refi_conversion_rate"]
            }
        },
        # Referral Management
        {
            "name": "Referral tracking",
            "description": "Track and manage referral sources",
            "category": "Referral Management",
            "applicable_roles": ["Loan Officer"],
            "kpi_mapping": {
                "monthly_kpis": ["referrals_tracked"],
                "referral_scores": ["referral_source_diversity"]
            }
        },
        {
            "name": "Referral acknowledgment",
            "description": "Acknowledge and thank referral sources",
            "category": "Referral Management",
            "applicable_roles": ["Concierge", "Loan Officer Assistant"],
            "kpi_mapping": {
                "weekly_kpis": ["referral_acknowledgments_sent"],
                "referral_scores": ["acknowledgment_timeliness"]
            }
        },
        {
            "name": "Referral incentive management",
            "description": "Manage referral reward programs",
            "category": "Referral Management",
            "applicable_roles": ["Loan Officer"],
            "kpi_mapping": {
                "monthly_kpis": ["incentives_distributed"]
            }
        },
        # Rate Lock Support
        {
            "name": "Rate monitoring",
            "description": "Monitor market rates and advise borrowers",
            "category": "Rate Lock Support",
            "applicable_roles": ["Loan Officer"],
            "kpi_mapping": {
                "daily_kpis": ["rate_alerts_sent"]
            }
        },
        {
            "name": "Rate lock execution",
            "description": "Execute rate locks for borrowers",
            "category": "Rate Lock Support",
            "applicable_roles": ["Loan Officer", "Processor"],
            "kpi_mapping": {
                "weekly_kpis": ["rate_locks_executed"]
            }
        }
    ]

    responsibilities = {}
    for resp_data in responsibilities_data:
        # Get role IDs for applicable roles
        role_ids = [roles[r].id for r in resp_data["applicable_roles"] if r in roles]

        responsibility = Responsibility(
            name=resp_data["name"],
            description=resp_data["description"],
            category_id=categories[resp_data["category"]].id,
            applicable_role_ids=role_ids,
            kpi_mapping=resp_data.get("kpi_mapping", {}),
            is_active=True
        )
        db.add(responsibility)
        db.flush()
        responsibilities[resp_data["name"]] = responsibility
        logger.info(f"  Created responsibility: {resp_data['name']}")

    # ========================================================================
    # SEED PERMISSION TEMPLATES
    # ========================================================================
    permission_templates_data = [
        {
            "name": "Loan Officer - Full Access",
            "description": "Complete access to leads, loans, and borrower communication",
            "is_system_template": True,
            "permissions": {
                "leads": {
                    "view": True,
                    "edit": True,
                    "reassign": True,
                    "delete": False,
                    "import": True
                },
                "active_loans": {
                    "view_assigned": True,
                    "view_all_branch": True,
                    "update_borrower_info": True,
                    "approve_tasks": True,
                    "update_milestones": True,
                    "add_docs_messages": True
                },
                "mum": {
                    "view": True,
                    "execute_annual_reviews": True,
                    "trigger_ai_followups": True,
                    "manage_refi_alerts": True
                },
                "communication_ai": {
                    "click_to_dial": True,
                    "teams_texting": True,
                    "view_ai_call_summaries": True,
                    "view_email_intelligence": True,
                    "access_borrower_sentiment": True
                },
                "referral_partners": {
                    "view": True,
                    "edit": True,
                    "assign_leads": True,
                    "view_analytics": True
                },
                "scorecards_reporting": {
                    "view_own": True,
                    "view_team": True,
                    "view_company": True,
                    "export_data": True
                },
                "admin": {
                    "manage_users": False,
                    "modify_permissions": False,
                    "configure_ai_settings": False,
                    "company_level_settings": False,
                    "configure_rate_lock": False
                }
            }
        },
        {
            "name": "Processor - Standard",
            "description": "Standard processor permissions for assigned loans",
            "is_system_template": True,
            "permissions": {
                "leads": {
                    "view": True,
                    "edit": False,
                    "reassign": False,
                    "delete": False,
                    "import": False
                },
                "active_loans": {
                    "view_assigned": True,
                    "view_all_branch": False,
                    "update_borrower_info": True,
                    "approve_tasks": False,
                    "update_milestones": True,
                    "add_docs_messages": True
                },
                "mum": {
                    "view": True,
                    "execute_annual_reviews": False,
                    "trigger_ai_followups": False,
                    "manage_refi_alerts": False
                },
                "communication_ai": {
                    "click_to_dial": True,
                    "teams_texting": True,
                    "view_ai_call_summaries": True,
                    "view_email_intelligence": True,
                    "access_borrower_sentiment": False
                },
                "referral_partners": {
                    "view": True,
                    "edit": False,
                    "assign_leads": False,
                    "view_analytics": False
                },
                "scorecards_reporting": {
                    "view_own": True,
                    "view_team": False,
                    "view_company": False,
                    "export_data": False
                },
                "admin": {
                    "manage_users": False,
                    "modify_permissions": False,
                    "configure_ai_settings": False,
                    "company_level_settings": False,
                    "configure_rate_lock": False
                }
            }
        },
        {
            "name": "Concierge - Communication Focus",
            "description": "Focus on borrower and partner communication",
            "is_system_template": True,
            "permissions": {
                "leads": {
                    "view": True,
                    "edit": True,
                    "reassign": False,
                    "delete": False,
                    "import": False
                },
                "active_loans": {
                    "view_assigned": True,
                    "view_all_branch": True,
                    "update_borrower_info": False,
                    "approve_tasks": False,
                    "update_milestones": True,
                    "add_docs_messages": True
                },
                "mum": {
                    "view": True,
                    "execute_annual_reviews": False,
                    "trigger_ai_followups": True,
                    "manage_refi_alerts": False
                },
                "communication_ai": {
                    "click_to_dial": True,
                    "teams_texting": True,
                    "view_ai_call_summaries": True,
                    "view_email_intelligence": True,
                    "access_borrower_sentiment": True
                },
                "referral_partners": {
                    "view": True,
                    "edit": False,
                    "assign_leads": False,
                    "view_analytics": True
                },
                "scorecards_reporting": {
                    "view_own": True,
                    "view_team": False,
                    "view_company": False,
                    "export_data": False
                },
                "admin": {
                    "manage_users": False,
                    "modify_permissions": False,
                    "configure_ai_settings": False,
                    "company_level_settings": False,
                    "configure_rate_lock": False
                }
            }
        },
        {
            "name": "Junior Staff - Limited",
            "description": "Limited permissions for junior staff members",
            "is_system_template": True,
            "permissions": {
                "leads": {
                    "view": True,
                    "edit": False,
                    "reassign": False,
                    "delete": False,
                    "import": False
                },
                "active_loans": {
                    "view_assigned": True,
                    "view_all_branch": False,
                    "update_borrower_info": False,
                    "approve_tasks": False,
                    "update_milestones": False,
                    "add_docs_messages": True
                },
                "mum": {
                    "view": True,
                    "execute_annual_reviews": False,
                    "trigger_ai_followups": False,
                    "manage_refi_alerts": False
                },
                "communication_ai": {
                    "click_to_dial": True,
                    "teams_texting": True,
                    "view_ai_call_summaries": False,
                    "view_email_intelligence": False,
                    "access_borrower_sentiment": False
                },
                "referral_partners": {
                    "view": True,
                    "edit": False,
                    "assign_leads": False,
                    "view_analytics": False
                },
                "scorecards_reporting": {
                    "view_own": True,
                    "view_team": False,
                    "view_company": False,
                    "export_data": False
                },
                "admin": {
                    "manage_users": False,
                    "modify_permissions": False,
                    "configure_ai_settings": False,
                    "company_level_settings": False,
                    "configure_rate_lock": False
                }
            }
        },
        {
            "name": "Admin - Full Control",
            "description": "Full administrative access to all system features",
            "is_system_template": True,
            "permissions": {
                "leads": {
                    "view": True,
                    "edit": True,
                    "reassign": True,
                    "delete": True,
                    "import": True
                },
                "active_loans": {
                    "view_assigned": True,
                    "view_all_branch": True,
                    "update_borrower_info": True,
                    "approve_tasks": True,
                    "update_milestones": True,
                    "add_docs_messages": True
                },
                "mum": {
                    "view": True,
                    "execute_annual_reviews": True,
                    "trigger_ai_followups": True,
                    "manage_refi_alerts": True
                },
                "communication_ai": {
                    "click_to_dial": True,
                    "teams_texting": True,
                    "view_ai_call_summaries": True,
                    "view_email_intelligence": True,
                    "access_borrower_sentiment": True
                },
                "referral_partners": {
                    "view": True,
                    "edit": True,
                    "assign_leads": True,
                    "view_analytics": True
                },
                "scorecards_reporting": {
                    "view_own": True,
                    "view_team": True,
                    "view_company": True,
                    "export_data": True
                },
                "admin": {
                    "manage_users": True,
                    "modify_permissions": True,
                    "configure_ai_settings": True,
                    "company_level_settings": True,
                    "configure_rate_lock": True
                }
            }
        }
    ]

    templates = {}
    for template_data in permission_templates_data:
        template = PermissionTemplate(
            name=template_data["name"],
            description=template_data["description"],
            permissions=template_data["permissions"],
            is_system_template=template_data["is_system_template"]
        )
        db.add(template)
        db.flush()
        templates[template_data["name"]] = template
        logger.info(f"  Created permission template: {template_data['name']}")

    # ========================================================================
    # SEED ROLE DEFAULT CATEGORIES
    # ========================================================================
    role_default_categories = {
        "Loan Officer": ["Lead Generation", "Borrower Engagement", "Partner Engagement", "Pre-Approval Workflow", "Post-Closing / MUM", "Referral Management", "Rate Lock Support"],
        "Processor": ["Application Review", "Processing & Milestones", "Closing Coordination"],
        "Concierge": ["Borrower Engagement", "Partner Engagement", "Post-Closing / MUM", "Referral Management"],
        "Jr. Loan Officer": ["Lead Generation", "Borrower Engagement", "Pre-Approval Workflow"],
        "Jr. Processor": ["Processing & Milestones"],
        "Loan Officer Assistant": ["Lead Generation", "Borrower Engagement", "Referral Management"],
        "Processing Assistant": ["Borrower Engagement", "Processing & Milestones", "Closing Coordination"],
        "Application Analysis": ["Application Review"],
        "Production Assistant 1": ["Lead Generation", "Borrower Engagement"],
        "Production Assistant 2": ["Lead Generation", "Borrower Engagement", "Pre-Approval Workflow"],
        "Buyer Agent": ["Partner Engagement", "Closing Coordination"],
        "Buyers Agent Closing Coordinator": ["Partner Engagement", "Closing Coordination"],
        "Listing Agent": ["Partner Engagement", "Closing Coordination"],
        "Listing Agent Closing Coordinator": ["Partner Engagement", "Closing Coordination"]
    }

    for role_name, cat_names in role_default_categories.items():
        if role_name in roles:
            for cat_name in cat_names:
                if cat_name in categories:
                    default_cat = RoleDefaultCategory(
                        role_id=roles[role_name].id,
                        category_id=categories[cat_name].id
                    )
                    db.add(default_cat)

    # ========================================================================
    # SEED ROLE DEFAULT RESPONSIBILITIES
    # ========================================================================
    role_default_responsibilities = {
        "Loan Officer": [
            "Lead qualification", "Outbound prospecting", "Application consultation",
            "Borrower issue resolution", "Weekly partner updates", "Partner relationship management",
            "Pre-qualification processing", "Pre-approval letter generation",
            "Post-close check-ins", "MUM annual reviews", "Refinance opportunity identification",
            "Referral tracking", "Rate monitoring", "Rate lock execution"
        ],
        "Processor": [
            "Initial application review", "Income verification",
            "Pre-approval letter generation", "Milestone tracking", "Condition management",
            "Underwriting coordination", "Title and appraisal ordering",
            "Closing documentation preparation", "Closing scheduling", "Final walkthrough coordination"
        ],
        "Concierge": [
            "Lead qualification", "Lead follow-up", "Borrower milestone updates",
            "Weekly partner updates", "Post-close check-ins", "Referral acknowledgment"
        ],
        "Jr. Loan Officer": [
            "Lead qualification", "Outbound prospecting", "Application consultation",
            "Pre-qualification processing"
        ],
        "Jr. Processor": [
            "Condition management"
        ],
        "Loan Officer Assistant": [
            "Lead follow-up", "Borrower milestone updates", "Document collection support",
            "Pre-approval follow-up", "Referral acknowledgment"
        ],
        "Processing Assistant": [
            "Document collection support", "Milestone tracking",
            "Title and appraisal ordering", "Closing scheduling"
        ],
        "Application Analysis": [
            "Initial application review", "Credit analysis", "Income verification"
        ],
        "Production Assistant 1": [
            "Lead follow-up"
        ],
        "Production Assistant 2": [
            "Lead follow-up", "Pre-approval follow-up"
        ],
        "Buyer Agent": [
            "Weekly partner updates", "Final walkthrough coordination"
        ],
        "Buyers Agent Closing Coordinator": [
            "Closing scheduling", "Final walkthrough coordination"
        ],
        "Listing Agent": [
            "Weekly partner updates"
        ],
        "Listing Agent Closing Coordinator": [
            "Closing scheduling"
        ]
    }

    for role_name, resp_names in role_default_responsibilities.items():
        if role_name in roles:
            for resp_name in resp_names:
                if resp_name in responsibilities:
                    default_resp = RoleDefaultResponsibility(
                        role_id=roles[role_name].id,
                        responsibility_id=responsibilities[resp_name].id
                    )
                    db.add(default_resp)

    # ========================================================================
    # LINK ROLES TO DEFAULT PERMISSION TEMPLATES
    # ========================================================================
    role_template_mapping = {
              "Site Administrator": "Admin - Full Control",
        "Loan Officer": "Loan Officer - Full Access",
        "Processor": "Processor - Standard",
        "Concierge": "Concierge - Communication Focus",
        "Jr. Loan Officer": "Junior Staff - Limited",
        "Jr. Processor": "Junior Staff - Limited",
        "Loan Officer Assistant": "Junior Staff - Limited",
        "Processing Assistant": "Junior Staff - Limited",
        "Application Analysis": "Processor - Standard",
        "Production Assistant 1": "Junior Staff - Limited",
        "Production Assistant 2": "Junior Staff - Limited",
        "Buyer Agent": "Junior Staff - Limited",
        "Buyers Agent Closing Coordinator": "Junior Staff - Limited",
        "Listing Agent": "Junior Staff - Limited",
        "Listing Agent Closing Coordinator": "Junior Staff - Limited"
    }

    for role_name, template_name in role_template_mapping.items():
        if role_name in roles and template_name in templates:
            roles[role_name].default_permission_template_id = templates[template_name].id

    db.commit()
    logger.info("✅ User onboarding seed data created successfully!")
    logger.info(f"   - {len(roles)} roles")
    logger.info(f"   - {len(categories)} categories")
    logger.info(f"   - {len(responsibilities)} responsibilities")
    logger.info(f"   - {len(templates)} permission templates")
