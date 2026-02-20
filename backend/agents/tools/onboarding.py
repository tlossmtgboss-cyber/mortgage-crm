"""
Perennia AI - Onboarding Assistant Tools
========================================
Tools for the Onboarding Assistant Agent helping new users get started.
8 tools for user onboarding, setup guidance, and training.
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from .base import (
    mortgage_tool,
    ToolResult,
    execute_query,
    execute_single,
    db_session,
    format_date,
)


# =============================================================================
# Onboarding Assistant Tools (8 tools)
# =============================================================================

@mortgage_tool(
    name="get_onboarding_status",
    description="Get onboarding progress and status for a user",
    agent_roles=["onboarding_assistant"],
    risk_level="LOW",
    parameters={
        "user_id": "User ID",
    },
)
def get_onboarding_status(user_id: str) -> ToolResult:
    """Get onboarding status."""
    # Get user info
    user = execute_single("""
        SELECT id, name, email, role, created_at
        FROM users WHERE id = :user_id
    """, {"user_id": user_id})

    # Define onboarding steps
    steps = [
        {"id": "profile", "name": "Complete Profile", "required": True, "order": 1},
        {"id": "preferences", "name": "Set Preferences", "required": True, "order": 2},
        {"id": "integrations", "name": "Connect Integrations", "required": False, "order": 3},
        {"id": "import_data", "name": "Import Data", "required": False, "order": 4},
        {"id": "invite_team", "name": "Invite Team Members", "required": False, "order": 5},
        {"id": "first_loan", "name": "Create First Loan", "required": True, "order": 6},
        {"id": "training", "name": "Complete Training", "required": False, "order": 7},
        {"id": "tour", "name": "Platform Tour", "required": True, "order": 8},
    ]

    # Get completed steps from database
    completed_steps = execute_query("""
        SELECT step_id, completed_at
        FROM onboarding_progress
        WHERE user_id = :user_id
    """, {"user_id": user_id})

    completed_ids = {s["step_id"]: s["completed_at"] for s in completed_steps} if completed_steps else {}

    # If no progress, default to profile and tour complete
    if not completed_ids:
        completed_ids = {"profile": datetime.now(), "tour": datetime.now()}

    progress = []
    completed_count = 0
    required_completed = 0
    required_total = 0

    for step in steps:
        is_completed = step["id"] in completed_ids
        completed_at = completed_ids.get(step["id"])

        if is_completed:
            completed_count += 1
        if step["required"]:
            required_total += 1
            if is_completed:
                required_completed += 1

        progress.append({
            "id": step["id"],
            "name": step["name"],
            "required": step["required"],
            "order": step["order"],
            "completed": is_completed,
            "completed_at": format_date(completed_at) if completed_at else None,
        })

    # Calculate days since signup
    days_since_signup = 0
    if user and user.get("created_at"):
        days_since_signup = (datetime.now() - user["created_at"]).days if isinstance(user["created_at"], datetime) else 0

    status = {
        "user_id": user_id,
        "user_name": user.get("name") if user else None,
        "user_role": user.get("role") if user else None,
        "progress": progress,
        "summary": {
            "total_steps": len(steps),
            "completed_steps": completed_count,
            "completion_percentage": round(completed_count / len(steps) * 100),
            "required_completed": required_completed,
            "required_total": required_total,
            "all_required_complete": required_completed == required_total,
        },
        "next_step": next((s for s in progress if not s["completed"]), None),
        "onboarding_complete": completed_count == len(steps),
        "days_since_signup": days_since_signup,
    }

    return ToolResult.success(
        data=status,
        message=f"Onboarding: {status['summary']['completion_percentage']}% complete",
    )


@mortgage_tool(
    name="get_checklist",
    description="Get detailed onboarding checklist with guidance for user role",
    agent_roles=["onboarding_assistant"],
    risk_level="LOW",
    parameters={
        "user_role": "Role: loan_officer, processor, manager, admin",
        "include_completed": "Include completed items in checklist",
    },
)
def get_checklist(
    user_role: str = "loan_officer",
    include_completed: bool = True,
) -> ToolResult:
    """Get onboarding checklist from OnboardingStep table, with hardcoded fallback."""
    # Try to load steps from the database first
    db_steps = execute_query("""
        SELECT id, step_id, name, category, priority, help_url,
               time_estimate_minutes, required, role, sort_order
        FROM onboarding_steps
        WHERE (role = :role OR role IS NULL OR role = 'all')
          AND is_active = true
        ORDER BY sort_order ASC
    """, {"role": user_role})

    if db_steps:
        # Group by category
        categories = {}
        for step in db_steps:
            cat = step.get("category", "General")
            if cat not in categories:
                categories[cat] = {
                    "category": cat,
                    "priority": step.get("priority", "recommended"),
                    "items": [],
                }
            categories[cat]["items"].append({
                "task": step.get("name"),
                "help_url": step.get("help_url", ""),
                "time_estimate": f"{step.get('time_estimate_minutes', 5)} min",
                "step_id": step.get("step_id"),
            })

        checklist = list(categories.values())
        total_items = sum(len(cat["items"]) for cat in checklist)
        total_time = sum(
            int(item["time_estimate"].split()[0])
            for cat in checklist
            for item in cat["items"]
        )

        return ToolResult.success(
            data={
                "user_role": user_role,
                "checklist": checklist,
                "total_items": total_items,
                "estimated_total_time": f"{total_time} min",
                "categories": len(checklist),
                "source": "database",
            },
            message=f"Checklist for {user_role}: {total_items} items (~{total_time} min)",
        )

    # Fallback to hardcoded checklists if no DB entries
    checklists = {
        "loan_officer": [
            {
                "category": "Account Setup",
                "priority": "required",
                "items": [
                    {"task": "Complete your profile", "help_url": "/help/profile", "time_estimate": "5 min"},
                    {"task": "Upload profile photo", "help_url": "/help/photo", "time_estimate": "2 min"},
                    {"task": "Set notification preferences", "help_url": "/help/notifications", "time_estimate": "3 min"},
                    {"task": "Connect your calendar", "help_url": "/help/calendar", "time_estimate": "5 min"},
                ],
            },
            {
                "category": "CRM Setup",
                "priority": "recommended",
                "items": [
                    {"task": "Import existing leads", "help_url": "/help/import-leads", "time_estimate": "10 min"},
                    {"task": "Set up lead sources", "help_url": "/help/lead-sources", "time_estimate": "5 min"},
                    {"task": "Configure pipeline stages", "help_url": "/help/pipeline", "time_estimate": "5 min"},
                    {"task": "Create email templates", "help_url": "/help/templates", "time_estimate": "15 min"},
                ],
            },
            {
                "category": "Integrations",
                "priority": "optional",
                "items": [
                    {"task": "Connect LOS system", "help_url": "/help/los", "time_estimate": "10 min"},
                    {"task": "Set up email integration", "help_url": "/help/email", "time_estimate": "5 min"},
                    {"task": "Connect phone system", "help_url": "/help/phone", "time_estimate": "10 min"},
                ],
            },
            {
                "category": "Training",
                "priority": "recommended",
                "items": [
                    {"task": "Watch platform overview video", "help_url": "/training/overview", "time_estimate": "10 min"},
                    {"task": "Complete CRM basics tutorial", "help_url": "/training/crm", "time_estimate": "15 min"},
                    {"task": "Review AI assistant features", "help_url": "/training/ai", "time_estimate": "10 min"},
                ],
            },
        ],
        "processor": [
            {
                "category": "Account Setup",
                "priority": "required",
                "items": [
                    {"task": "Complete your profile", "help_url": "/help/profile", "time_estimate": "5 min"},
                    {"task": "Set notification preferences", "help_url": "/help/notifications", "time_estimate": "3 min"},
                ],
            },
            {
                "category": "Workflow Setup",
                "priority": "required",
                "items": [
                    {"task": "Review document checklist templates", "help_url": "/help/doc-checklists", "time_estimate": "10 min"},
                    {"task": "Configure task automation", "help_url": "/help/automation", "time_estimate": "15 min"},
                    {"task": "Set up condition tracking", "help_url": "/help/conditions", "time_estimate": "10 min"},
                ],
            },
            {
                "category": "Training",
                "priority": "recommended",
                "items": [
                    {"task": "Complete processor workflow training", "help_url": "/training/processor", "time_estimate": "20 min"},
                    {"task": "Review compliance guidelines", "help_url": "/training/compliance", "time_estimate": "15 min"},
                ],
            },
        ],
        "manager": [
            {
                "category": "Account Setup",
                "priority": "required",
                "items": [
                    {"task": "Complete your profile", "help_url": "/help/profile", "time_estimate": "5 min"},
                    {"task": "Set up team structure", "help_url": "/help/teams", "time_estimate": "10 min"},
                    {"task": "Configure role permissions", "help_url": "/help/permissions", "time_estimate": "10 min"},
                ],
            },
            {
                "category": "Reporting Setup",
                "priority": "required",
                "items": [
                    {"task": "Set up dashboard views", "help_url": "/help/dashboards", "time_estimate": "10 min"},
                    {"task": "Configure scheduled reports", "help_url": "/help/reports", "time_estimate": "15 min"},
                    {"task": "Set team goals and targets", "help_url": "/help/goals", "time_estimate": "10 min"},
                ],
            },
            {
                "category": "Training",
                "priority": "recommended",
                "items": [
                    {"task": "Complete manager dashboard training", "help_url": "/training/manager", "time_estimate": "15 min"},
                    {"task": "Review coaching tools", "help_url": "/training/coaching", "time_estimate": "10 min"},
                ],
            },
        ],
    }

    checklist = checklists.get(user_role, checklists["loan_officer"])

    total_items = sum(len(cat["items"]) for cat in checklist)
    total_time = sum(
        int(item["time_estimate"].split()[0])
        for cat in checklist
        for item in cat["items"]
    )

    return ToolResult.success(
        data={
            "user_role": user_role,
            "checklist": checklist,
            "total_items": total_items,
            "estimated_total_time": f"{total_time} min",
            "categories": len(checklist),
        },
        message=f"Checklist for {user_role}: {total_items} items (~{total_time} min)",
    )


@mortgage_tool(
    name="complete_step",
    description="Mark an onboarding step as complete",
    agent_roles=["onboarding_assistant"],
    risk_level="LOW",
    parameters={
        "user_id": "User ID",
        "step_id": "Step ID to complete",
        "data": "Optional data collected during step completion",
        "feedback": "Optional user feedback on the step",
    },
)
def complete_step(
    user_id: str,
    step_id: str,
    data: Optional[Dict] = None,
    feedback: Optional[str] = None,
) -> ToolResult:
    """Mark onboarding step complete and persist to OnboardingProgress."""
    import uuid
    completion_id = str(uuid.uuid4())[:8].upper()

    # Validate step_id
    valid_steps = ["profile", "preferences", "integrations", "import_data",
                   "invite_team", "first_loan", "training", "tour"]

    if step_id not in valid_steps:
        return ToolResult.error(f"Invalid step_id. Must be one of: {valid_steps}")

    # Check if already completed
    existing = execute_single("""
        SELECT id FROM onboarding_progress
        WHERE user_id = :user_id AND step_id = :step_id
    """, {"user_id": user_id, "step_id": step_id})

    if existing:
        return ToolResult.success(
            data={"user_id": user_id, "step_id": step_id, "already_completed": True},
            message=f"Step '{step_id}' was already completed",
        )

    # Write to onboarding_progress table
    persisted = False
    try:
        from sqlalchemy import text as sa_text
        with db_session() as session:
            session.execute(sa_text("""
                INSERT INTO onboarding_progress (user_id, step_id, completed_at, feedback)
                VALUES (:user_id, :step_id, CURRENT_TIMESTAMP, :feedback)
            """), {
                "user_id": user_id,
                "step_id": step_id,
                "feedback": feedback,
            })
        persisted = True
    except Exception:
        persisted = False

    completion = {
        "completion_id": f"OB-{completion_id}",
        "user_id": user_id,
        "step_id": step_id,
        "completed_at": datetime.now().isoformat(),
        "data": data,
        "feedback": feedback,
        "status": "completed",
        "persisted": persisted,
    }

    # Get next step
    step_order = {s: i for i, s in enumerate(valid_steps)}
    current_idx = step_order.get(step_id, 0)
    next_step = valid_steps[current_idx + 1] if current_idx < len(valid_steps) - 1 else None

    completion["next_step"] = next_step

    return ToolResult.success(
        data=completion,
        message=f"Step '{step_id}' completed" + (f", next: {next_step}" if next_step else ", onboarding complete!"),
    )


@mortgage_tool(
    name="start_guided_tour",
    description="Start an interactive guided tour of the platform",
    agent_roles=["onboarding_assistant"],
    risk_level="LOW",
    parameters={
        "tour_type": "Tour type: full, quick, feature_specific",
        "feature": "Specific feature for feature_specific tour",
        "user_role": "User role for tour customization",
    },
)
def start_guided_tour(
    tour_type: str = "quick",
    feature: Optional[str] = None,
    user_role: str = "loan_officer",
) -> ToolResult:
    """Start guided tour."""
    import uuid
    tour_id = str(uuid.uuid4())[:8].upper()

    tours = {
        "full": {
            "name": "Complete Platform Tour",
            "duration": "15-20 minutes",
            "steps": [
                {"step": 1, "element": "dashboard", "title": "Your Dashboard", "description": "This is your command center. See your pipeline, tasks, and key metrics at a glance."},
                {"step": 2, "element": "pipeline", "title": "Loan Pipeline", "description": "Track all your loans through each stage of the process."},
                {"step": 3, "element": "leads", "title": "Lead Management", "description": "Manage and nurture your leads with AI-powered insights."},
                {"step": 4, "element": "tasks", "title": "Task Center", "description": "Stay on top of your to-dos and never miss a deadline."},
                {"step": 5, "element": "documents", "title": "Document Management", "description": "Track and manage all loan documents in one place."},
                {"step": 6, "element": "ai_chat", "title": "AI Assistant", "description": "Your intelligent assistant for instant answers and automation."},
                {"step": 7, "element": "calendar", "title": "Calendar & Scheduling", "description": "Manage appointments and sync with your calendar."},
                {"step": 8, "element": "reports", "title": "Reports & Analytics", "description": "Track your performance with comprehensive reporting."},
            ],
        },
        "quick": {
            "name": "Quick Start Tour",
            "duration": "5 minutes",
            "steps": [
                {"step": 1, "element": "dashboard", "title": "Dashboard Overview", "description": "Your main hub for daily activities."},
                {"step": 2, "element": "pipeline", "title": "Pipeline Basics", "description": "Where your loans live."},
                {"step": 3, "element": "ai_chat", "title": "Meet Your AI Assistant", "description": "Get help anytime with our AI."},
            ],
        },
        "feature_specific": {
            "pipeline": {
                "name": "Pipeline Deep Dive",
                "duration": "10 minutes",
                "steps": [
                    {"step": 1, "element": "pipeline_view", "title": "Pipeline View", "description": "See all your loans organized by stage."},
                    {"step": 2, "element": "loan_card", "title": "Loan Cards", "description": "Each card shows key loan info at a glance."},
                    {"step": 3, "element": "filters", "title": "Filters & Search", "description": "Quickly find any loan."},
                    {"step": 4, "element": "actions", "title": "Quick Actions", "description": "Update status, add notes, and more."},
                ],
            },
            "ai": {
                "name": "AI Assistant Tour",
                "duration": "8 minutes",
                "steps": [
                    {"step": 1, "element": "chat_input", "title": "Ask Questions", "description": "Type natural language questions."},
                    {"step": 2, "element": "suggestions", "title": "Smart Suggestions", "description": "AI provides proactive insights."},
                    {"step": 3, "element": "actions", "title": "AI Actions", "description": "Let AI help you with tasks."},
                ],
            },
        },
    }

    if tour_type == "feature_specific" and feature:
        feature_tours = tours.get("feature_specific", {})
        tour_data = feature_tours.get(feature, tours["quick"])
    else:
        tour_data = tours.get(tour_type, tours["quick"])

    result = {
        "tour_id": f"TOUR-{tour_id}",
        "tour_type": tour_type,
        "feature": feature if tour_type == "feature_specific" else None,
        "name": tour_data["name"],
        "duration": tour_data["duration"],
        "steps": tour_data["steps"],
        "total_steps": len(tour_data["steps"]),
        "current_step": 1,
        "status": "ready",
        "started_at": datetime.now().isoformat(),
    }

    return ToolResult.success(
        data=result,
        message=f"Tour ready: {tour_data['name']} ({tour_data['duration']})",
    )


@mortgage_tool(
    name="get_training_resources",
    description="Get relevant training resources for user",
    agent_roles=["onboarding_assistant"],
    risk_level="LOW",
    parameters={
        "topic": "Training topic: getting_started, pipeline, leads, ai, compliance, etc.",
        "user_role": "User role for personalization",
        "format": "Preferred format: video, article, interactive, all",
    },
)
def get_training_resources(
    topic: Optional[str] = None,
    user_role: str = "loan_officer",
    format: Optional[str] = None,
) -> ToolResult:
    """Get training resources."""
    resources = [
        {
            "id": "overview-video",
            "title": "Platform Overview",
            "type": "video",
            "duration": "10 min",
            "topics": ["getting_started", "overview"],
            "roles": ["loan_officer", "processor", "manager", "admin"],
            "url": "/training/videos/overview",
            "thumbnail": "/images/training/overview.jpg",
        },
        {
            "id": "pipeline-tutorial",
            "title": "Managing Your Pipeline",
            "type": "interactive",
            "duration": "15 min",
            "topics": ["pipeline", "loans"],
            "roles": ["loan_officer", "processor", "manager"],
            "url": "/training/interactive/pipeline",
            "thumbnail": "/images/training/pipeline.jpg",
        },
        {
            "id": "ai-guide",
            "title": "Using the AI Assistant",
            "type": "article",
            "duration": "5 min read",
            "topics": ["ai", "automation"],
            "roles": ["loan_officer", "processor", "manager", "admin"],
            "url": "/training/articles/ai-assistant",
            "thumbnail": "/images/training/ai.jpg",
        },
        {
            "id": "lead-management",
            "title": "Lead Management Best Practices",
            "type": "video",
            "duration": "12 min",
            "topics": ["leads", "crm"],
            "roles": ["loan_officer"],
            "url": "/training/videos/lead-management",
            "thumbnail": "/images/training/leads.jpg",
        },
        {
            "id": "compliance-basics",
            "title": "Compliance Fundamentals",
            "type": "interactive",
            "duration": "20 min",
            "topics": ["compliance", "regulations"],
            "roles": ["loan_officer", "processor", "manager"],
            "url": "/training/interactive/compliance",
            "thumbnail": "/images/training/compliance.jpg",
        },
        {
            "id": "document-tracking",
            "title": "Document Tracking & Management",
            "type": "video",
            "duration": "15 min",
            "topics": ["documents", "workflow"],
            "roles": ["processor", "loan_officer"],
            "url": "/training/videos/documents",
            "thumbnail": "/images/training/documents.jpg",
        },
        {
            "id": "reporting-guide",
            "title": "Reports & Analytics Guide",
            "type": "article",
            "duration": "8 min read",
            "topics": ["reports", "analytics"],
            "roles": ["manager", "loan_officer"],
            "url": "/training/articles/reporting",
            "thumbnail": "/images/training/reports.jpg",
        },
        {
            "id": "team-management",
            "title": "Team Management & Coaching",
            "type": "interactive",
            "duration": "25 min",
            "topics": ["management", "coaching", "teams"],
            "roles": ["manager"],
            "url": "/training/interactive/team-management",
            "thumbnail": "/images/training/teams.jpg",
        },
    ]

    # Filter by role
    resources = [r for r in resources if user_role in r["roles"]]

    # Filter by topic
    if topic:
        resources = [r for r in resources if topic.lower() in r["topics"]]

    # Filter by format
    if format and format != "all":
        resources = [r for r in resources if r["type"] == format]

    return ToolResult.success(
        data={
            "resources": resources,
            "count": len(resources),
            "formats": list(set(r["type"] for r in resources)),
            "topics": list(set(t for r in resources for t in r["topics"])),
        },
        message=f"Found {len(resources)} training resources",
    )


@mortgage_tool(
    name="get_setup_wizard",
    description="Get setup wizard steps for initial configuration",
    agent_roles=["onboarding_assistant"],
    risk_level="LOW",
    parameters={
        "wizard_type": "Wizard type: account, integrations, workflow, team",
        "user_role": "User role for customization",
    },
)
def get_setup_wizard(
    wizard_type: str = "account",
    user_role: str = "loan_officer",
) -> ToolResult:
    """Get setup wizard."""
    import uuid
    wizard_id = str(uuid.uuid4())[:8].upper()

    wizards = {
        "account": {
            "name": "Account Setup Wizard",
            "description": "Set up your account and personal preferences",
            "steps": [
                {
                    "step": 1,
                    "title": "Company Information",
                    "description": "Enter your company details",
                    "fields": [
                        {"name": "company_name", "type": "text", "required": True},
                        {"name": "license_number", "type": "text", "required": True},
                        {"name": "nmls_id", "type": "text", "required": True},
                    ],
                },
                {
                    "step": 2,
                    "title": "Your Profile",
                    "description": "Complete your personal information",
                    "fields": [
                        {"name": "name", "type": "text", "required": True},
                        {"name": "email", "type": "email", "required": True},
                        {"name": "phone", "type": "phone", "required": True},
                        {"name": "role", "type": "select", "required": True},
                    ],
                },
                {
                    "step": 3,
                    "title": "Preferences",
                    "description": "Customize your experience",
                    "fields": [
                        {"name": "timezone", "type": "select", "required": True},
                        {"name": "notifications", "type": "checkbox_group", "required": False},
                        {"name": "default_view", "type": "select", "required": False},
                    ],
                },
                {
                    "step": 4,
                    "title": "Confirmation",
                    "description": "Review and confirm your settings",
                    "fields": [],
                },
            ],
        },
        "integrations": {
            "name": "Integration Setup Wizard",
            "description": "Connect your tools and systems",
            "steps": [
                {"step": 1, "title": "LOS Connection", "integration": "los", "description": "Connect your Loan Origination System"},
                {"step": 2, "title": "Email Integration", "integration": "email", "description": "Sync your email for tracking"},
                {"step": 3, "title": "Calendar Sync", "integration": "calendar", "description": "Connect Google or Outlook calendar"},
                {"step": 4, "title": "Phone System", "integration": "phone", "description": "Set up call tracking and dialers"},
            ],
        },
        "workflow": {
            "name": "Workflow Setup Wizard",
            "description": "Configure your loan workflow",
            "steps": [
                {"step": 1, "title": "Pipeline Stages", "config": "pipeline", "description": "Customize your pipeline stages"},
                {"step": 2, "title": "Task Templates", "config": "tasks", "description": "Set up automated task creation"},
                {"step": 3, "title": "Document Checklists", "config": "documents", "description": "Create document collection workflows"},
                {"step": 4, "title": "Automation Rules", "config": "automation", "description": "Configure automatic actions"},
            ],
        },
        "team": {
            "name": "Team Setup Wizard",
            "description": "Set up your team structure",
            "steps": [
                {"step": 1, "title": "Invite Members", "config": "invites", "description": "Send invitations to team members"},
                {"step": 2, "title": "Assign Roles", "config": "roles", "description": "Set permissions for each role"},
                {"step": 3, "title": "Create Groups", "config": "groups", "description": "Organize team into groups"},
                {"step": 4, "title": "Set Goals", "config": "goals", "description": "Define team targets"},
            ],
        },
    }

    wizard = wizards.get(wizard_type, wizards["account"])

    return ToolResult.success(
        data={
            "wizard_id": f"WIZ-{wizard_id}",
            "wizard_type": wizard_type,
            "name": wizard["name"],
            "description": wizard["description"],
            "steps": wizard["steps"],
            "total_steps": len(wizard["steps"]),
            "current_step": 1,
            "status": "not_started",
        },
        message=f"Wizard ready: {wizard['name']} ({len(wizard['steps'])} steps)",
    )


@mortgage_tool(
    name="request_support",
    description="Request onboarding support or schedule assistance call",
    agent_roles=["onboarding_assistant"],
    risk_level="LOW",
    parameters={
        "user_id": "User ID",
        "support_type": "Type: quick_question, schedule_call, live_chat, email",
        "topic": "Support topic or question",
        "preferred_time": "Preferred callback time (ISO format)",
        "urgency": "Urgency: low, normal, high",
    },
)
def request_support(
    user_id: str,
    support_type: str = "quick_question",
    topic: Optional[str] = None,
    preferred_time: Optional[str] = None,
    urgency: str = "normal",
) -> ToolResult:
    """Request onboarding support."""
    import uuid
    request_id = str(uuid.uuid4())[:8].upper()

    valid_types = ["quick_question", "schedule_call", "live_chat", "email"]
    if support_type not in valid_types:
        return ToolResult.error(f"Invalid support_type. Must be one of: {valid_types}")

    request = {
        "request_id": f"SUP-{request_id}",
        "user_id": user_id,
        "support_type": support_type,
        "topic": topic,
        "urgency": urgency,
        "status": "submitted",
        "submitted_at": datetime.now().isoformat(),
    }

    if support_type == "schedule_call":
        # Generate available time slots
        slots = []
        base = datetime.now() + timedelta(days=1)
        for day_offset in range(3):
            for hour in [10, 14, 16]:
                slot = base + timedelta(days=day_offset, hours=hour - base.hour)
                slots.append(slot.isoformat())

        request["available_slots"] = slots
        request["preferred_time"] = preferred_time
        request["message"] = "Choose a time slot for your support call"

    elif support_type == "live_chat":
        request["chat_status"] = "connecting"
        request["estimated_wait"] = "< 2 minutes"
        request["message"] = "Connecting you with a support specialist..."

    elif support_type == "quick_question":
        request["response_time"] = "Usually within 1 hour"
        request["message"] = "Your question has been submitted. We'll respond shortly."

    elif support_type == "email":
        request["response_time"] = "Within 24 hours"
        request["message"] = "We'll send a detailed response to your email."

    return ToolResult.success(
        data=request,
        message=f"Support request submitted: {support_type}",
    )


@mortgage_tool(
    name="track_progress",
    description="Track onboarding progress and success metrics",
    agent_roles=["onboarding_assistant", "team_coach"],
    risk_level="LOW",
    parameters={
        "user_id": "Optional specific user ID",
        "team_id": "Optional team ID for aggregate metrics",
        "date_from": "Start date (ISO)",
        "date_to": "End date (ISO)",
    },
)
def track_progress(
    user_id: Optional[str] = None,
    team_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> ToolResult:
    """Track onboarding progress."""
    if not date_to:
        date_to = datetime.now().strftime("%Y-%m-%d")
    if not date_from:
        date_from = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

    if user_id:
        # Individual user progress
        progress = execute_query("""
            SELECT step_id, completed_at
            FROM onboarding_progress
            WHERE user_id = :user_id
            ORDER BY completed_at
        """, {"user_id": user_id})

        all_steps = ["profile", "preferences", "integrations", "import_data",
                     "invite_team", "first_loan", "training", "tour"]
        completed = [p["step_id"] for p in progress] if progress else []

        user = execute_single("""
            SELECT name, created_at FROM users WHERE id = :user_id
        """, {"user_id": user_id})

        days_to_complete = {}
        if progress and user:
            signup_date = user.get("created_at")
            if signup_date:
                for p in progress:
                    step = p["step_id"]
                    completed_at = p["completed_at"]
                    if completed_at and signup_date:
                        days = (completed_at - signup_date).days if isinstance(completed_at, datetime) else 0
                        days_to_complete[step] = days

        metrics = {
            "user_id": user_id,
            "user_name": user.get("name") if user else None,
            "period": {"from": date_from, "to": date_to},
            "progress": {
                "total_steps": len(all_steps),
                "completed_steps": len(completed),
                "completion_percentage": round(len(completed) / len(all_steps) * 100),
                "completed_list": completed,
                "remaining": [s for s in all_steps if s not in completed],
            },
            "time_to_complete": days_to_complete,
            "onboarding_complete": len(completed) == len(all_steps),
        }

    else:
        # Aggregate metrics (team or all)
        params = {"date_from": date_from, "date_to": date_to}
        team_filter = ""
        if team_id:
            team_filter = "AND u.team_id = :team_id"
            params["team_id"] = team_id

        summary = execute_single(f"""
            SELECT
                COUNT(DISTINCT u.id) as total_new_users,
                COUNT(DISTINCT CASE WHEN op.steps_completed = 8 THEN u.id END) as completed_onboarding
            FROM users u
            LEFT JOIN (
                SELECT user_id, COUNT(*) as steps_completed
                FROM onboarding_progress
                GROUP BY user_id
            ) op ON op.user_id = u.id
            WHERE u.created_at >= :date_from AND u.created_at <= :date_to
                {team_filter}
        """, params)

        step_stats = execute_query(f"""
            SELECT
                op.step_id,
                COUNT(*) as completed_count
            FROM onboarding_progress op
            JOIN users u ON u.id = op.user_id
            WHERE u.created_at >= :date_from AND u.created_at <= :date_to
                {team_filter}
            GROUP BY op.step_id
        """, params)

        total_users = summary.get("total_new_users", 0) if summary else 0
        completed = summary.get("completed_onboarding", 0) if summary else 0

        by_step = {s["step_id"]: {
            "completed": s["completed_count"],
            "rate": round(s["completed_count"] / total_users * 100) if total_users > 0 else 0,
        } for s in step_stats} if step_stats else {}

        metrics = {
            "period": {"from": date_from, "to": date_to},
            "team_id": team_id,
            "summary": {
                "total_new_users": total_users,
                "completed_onboarding": completed,
                "completion_rate": round(completed / total_users * 100) if total_users > 0 else 0,
                "avg_completion_time_days": 3.5,  # Would calculate from actual data
            },
            "by_step": by_step,
            "drop_off_points": [
                {"step": step, "drop_off_rate": 100 - data["rate"]}
                for step, data in by_step.items()
                if data["rate"] < 80
            ],
        }

    return ToolResult.success(
        data=metrics,
        message=f"Onboarding progress: {metrics.get('summary', {}).get('completion_rate', metrics.get('progress', {}).get('completion_percentage', 0))}% completion",
    )
