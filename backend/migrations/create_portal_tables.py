"""
Database Migration: Create Portal Tables

This script creates all tables required for the Perennia Portal system.
Run with: python -m migrations.create_portal_tables

Features:
- Creates all portal-related tables
- Seeds milestone templates and notification templates
- Seeds federal holidays for current and next year
- Idempotent - safe to run multiple times
"""

import os
import sys
from datetime import datetime, date

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, inspect
from database import DATABASE_URL, Base
from models.portal_models import (
    LifecycleStage, MilestoneStatus, TaskStatus,
    DocumentType, DocumentStatus, NotificationChannel, NotificationStatus,
    PortalLoan, LifecycleStateHistory,
    MilestoneTemplate, MilestoneInstance, TaskTemplate, TaskInstance,
    FederalHoliday, CloseOnTimeSchedule, CloseOnTimeMilestone,
    PortalDocument, DocumentExtraction, PropertyCosts,
    HomePriceIndex, PropertyValueBaseline, PropertyValuation, HomeValueInsight,
    NotificationTemplate, NotificationQueue,
    LoanActivityLog, RiskFlag, PartnerAccessToken,
    AnnualRefreshCycle, PresentationSession, PresentationScenario, PresentationCitation
)


def create_tables(engine):
    """Create all portal tables."""
    print("Creating portal tables...")

    # Import portal models to register them with Base
    from models import portal_models

    # List of portal-specific tables to create
    portal_tables = [
        PortalLoan.__table__,
        LifecycleStateHistory.__table__,
        MilestoneTemplate.__table__,
        MilestoneInstance.__table__,
        TaskTemplate.__table__,
        TaskInstance.__table__,
        FederalHoliday.__table__,
        CloseOnTimeSchedule.__table__,
        CloseOnTimeMilestone.__table__,
        PortalDocument.__table__,
        DocumentExtraction.__table__,
        PropertyCosts.__table__,
        HomePriceIndex.__table__,
        PropertyValueBaseline.__table__,
        PropertyValuation.__table__,
        HomeValueInsight.__table__,
        NotificationTemplate.__table__,
        NotificationQueue.__table__,
        LoanActivityLog.__table__,
        RiskFlag.__table__,
        PartnerAccessToken.__table__,
        AnnualRefreshCycle.__table__,
        PresentationSession.__table__,
        PresentationScenario.__table__,
        PresentationCitation.__table__,
    ]

    # Create only portal tables
    Base.metadata.create_all(bind=engine, tables=portal_tables)

    print("Tables created successfully!")


def seed_milestone_templates(engine):
    """Seed default milestone templates."""
    from sqlalchemy.orm import Session

    session = Session(bind=engine)

    # Check if templates already exist
    existing = session.query(MilestoneTemplate).count()
    if existing > 0:
        print(f"Milestone templates already exist ({existing} found), skipping seed...")
        session.close()
        return

    print("Seeding milestone templates...")

    templates = [
        # Pre-Approval Stage
        {
            "code": "PREAPP_START",
            "name": "Application Started",
            "description": "Your loan application has been initiated",
            "lifecycle_stage": LifecycleStage.PREAPPROVAL,
            "order_index": 1,
            "icon": "file-text",
            "color": "#3B82F6",
            "typical_duration_days": 1,
        },
        {
            "code": "PREAPP_DOCS",
            "name": "Documents Submitted",
            "description": "Initial documents have been received",
            "lifecycle_stage": LifecycleStage.PREAPPROVAL,
            "order_index": 2,
            "icon": "upload",
            "color": "#8B5CF6",
            "typical_duration_days": 3,
        },
        {
            "code": "PREAPP_REVIEW",
            "name": "Application Under Review",
            "description": "Your application is being reviewed by our team",
            "lifecycle_stage": LifecycleStage.PREAPPROVAL,
            "order_index": 3,
            "icon": "search",
            "color": "#EC4899",
            "typical_duration_days": 2,
        },
        {
            "code": "PREAPP_APPROVED",
            "name": "Pre-Approval Issued",
            "description": "Congratulations! You have been pre-approved",
            "lifecycle_stage": LifecycleStage.PREAPPROVAL,
            "order_index": 4,
            "icon": "check-circle",
            "color": "#10B981",
            "typical_duration_days": 1,
        },

        # Under Contract Stage
        {
            "code": "CONTRACT_RECEIVED",
            "name": "Contract Received",
            "description": "Purchase contract has been received",
            "lifecycle_stage": LifecycleStage.UNDER_CONTRACT,
            "order_index": 1,
            "icon": "file-signature",
            "color": "#F59E0B",
            "typical_duration_days": 1,
        },
        {
            "code": "CONTRACT_REVIEWED",
            "name": "Contract Reviewed",
            "description": "Contract terms have been reviewed",
            "lifecycle_stage": LifecycleStage.UNDER_CONTRACT,
            "order_index": 2,
            "icon": "clipboard-check",
            "color": "#3B82F6",
            "typical_duration_days": 2,
        },

        # Processing Stage
        {
            "code": "PROC_APPRAISAL",
            "name": "Appraisal Ordered",
            "description": "Property appraisal has been ordered",
            "lifecycle_stage": LifecycleStage.PROCESSING,
            "order_index": 1,
            "icon": "home",
            "color": "#6366F1",
            "typical_duration_days": 2,
        },
        {
            "code": "PROC_APPRAISAL_RECEIVED",
            "name": "Appraisal Received",
            "description": "Property appraisal report is in",
            "lifecycle_stage": LifecycleStage.PROCESSING,
            "order_index": 2,
            "icon": "file-check",
            "color": "#8B5CF6",
            "typical_duration_days": 7,
        },
        {
            "code": "PROC_TITLE",
            "name": "Title Ordered",
            "description": "Title search has been ordered",
            "lifecycle_stage": LifecycleStage.PROCESSING,
            "order_index": 3,
            "icon": "shield",
            "color": "#EC4899",
            "typical_duration_days": 1,
        },
        {
            "code": "PROC_SUBMITTED",
            "name": "Submitted to Underwriting",
            "description": "Your file has been submitted for underwriting",
            "lifecycle_stage": LifecycleStage.PROCESSING,
            "order_index": 4,
            "icon": "send",
            "color": "#F59E0B",
            "typical_duration_days": 3,
        },
        {
            "code": "PROC_CONDITIONAL",
            "name": "Conditional Approval",
            "description": "Loan conditionally approved pending final items",
            "lifecycle_stage": LifecycleStage.PROCESSING,
            "order_index": 5,
            "icon": "check",
            "color": "#10B981",
            "typical_duration_days": 3,
        },
        {
            "code": "PROC_CONDITIONS",
            "name": "Final Conditions Cleared",
            "description": "All conditions have been satisfied",
            "lifecycle_stage": LifecycleStage.PROCESSING,
            "order_index": 6,
            "icon": "check-circle",
            "color": "#059669",
            "typical_duration_days": 2,
        },

        # Clear to Close Stage
        {
            "code": "CTC_APPROVED",
            "name": "Clear to Close",
            "description": "Your loan is clear to close!",
            "lifecycle_stage": LifecycleStage.CLEAR_TO_CLOSE,
            "order_index": 1,
            "icon": "award",
            "color": "#10B981",
            "typical_duration_days": 1,
        },
        {
            "code": "CTC_DISCLOSURE",
            "name": "Closing Disclosure Sent",
            "description": "Your closing disclosure has been sent",
            "lifecycle_stage": LifecycleStage.CLEAR_TO_CLOSE,
            "order_index": 2,
            "icon": "file-text",
            "color": "#3B82F6",
            "typical_duration_days": 1,
        },
        {
            "code": "CTC_DISCLOSURE_SIGNED",
            "name": "Closing Disclosure Signed",
            "description": "Closing disclosure has been acknowledged",
            "lifecycle_stage": LifecycleStage.CLEAR_TO_CLOSE,
            "order_index": 3,
            "icon": "pen",
            "color": "#8B5CF6",
            "typical_duration_days": 1,
        },
        {
            "code": "CTC_SCHEDULED",
            "name": "Closing Scheduled",
            "description": "Your closing date is confirmed",
            "lifecycle_stage": LifecycleStage.CLEAR_TO_CLOSE,
            "order_index": 4,
            "icon": "calendar",
            "color": "#F59E0B",
            "typical_duration_days": 1,
        },

        # Funded Stage
        {
            "code": "FUNDED_CLOSED",
            "name": "Closed",
            "description": "Loan documents have been signed",
            "lifecycle_stage": LifecycleStage.FUNDED,
            "order_index": 1,
            "icon": "pen-tool",
            "color": "#10B981",
            "typical_duration_days": 0,
        },
        {
            "code": "FUNDED_RECORDED",
            "name": "Recorded",
            "description": "Deed has been recorded",
            "lifecycle_stage": LifecycleStage.FUNDED,
            "order_index": 2,
            "icon": "book",
            "color": "#6366F1",
            "typical_duration_days": 1,
        },
        {
            "code": "FUNDED_DISBURSED",
            "name": "Funds Disbursed",
            "description": "Congratulations! Your loan has been funded",
            "lifecycle_stage": LifecycleStage.FUNDED,
            "order_index": 3,
            "icon": "dollar-sign",
            "color": "#059669",
            "typical_duration_days": 1,
        },
    ]

    for template_data in templates:
        template = MilestoneTemplate(
            is_active=True,
            is_borrower_visible=True,
            is_partner_visible=True,
            **template_data
        )
        session.add(template)

    session.commit()
    print(f"Seeded {len(templates)} milestone templates")
    session.close()


def seed_task_templates(engine):
    """Seed default task templates for milestones."""
    from sqlalchemy.orm import Session

    session = Session(bind=engine)

    # Check if task templates already exist
    existing = session.query(TaskTemplate).count()
    if existing > 0:
        print(f"Task templates already exist ({existing} found), skipping seed...")
        session.close()
        return

    print("Seeding task templates...")

    # Get milestone templates
    milestones = {m.code: m.id for m in session.query(MilestoneTemplate).all()}

    task_templates = [
        # Pre-Approval Tasks
        {"milestone_code": "PREAPP_DOCS", "name": "Upload Pay Stubs", "description": "Upload your most recent pay stubs", "order_index": 1, "is_required": True, "is_borrower_action": True},
        {"milestone_code": "PREAPP_DOCS", "name": "Upload Bank Statements", "description": "Upload 2 months of bank statements", "order_index": 2, "is_required": True, "is_borrower_action": True},
        {"milestone_code": "PREAPP_DOCS", "name": "Upload Tax Returns", "description": "Upload last 2 years of tax returns", "order_index": 3, "is_required": True, "is_borrower_action": True},
        {"milestone_code": "PREAPP_DOCS", "name": "Upload ID", "description": "Upload government-issued ID", "order_index": 4, "is_required": True, "is_borrower_action": True},

        # Under Contract Tasks
        {"milestone_code": "CONTRACT_RECEIVED", "name": "Upload Purchase Contract", "description": "Upload signed purchase agreement", "order_index": 1, "is_required": True, "is_borrower_action": True},
        {"milestone_code": "CONTRACT_REVIEWED", "name": "Review Contract Terms", "description": "LO reviews contract terms", "order_index": 1, "is_required": True, "is_borrower_action": False},

        # Processing Tasks
        {"milestone_code": "PROC_CONDITIONAL", "name": "Clear Conditions", "description": "Provide any additional documents requested", "order_index": 1, "is_required": True, "is_borrower_action": True},

        # Clear to Close Tasks
        {"milestone_code": "CTC_DISCLOSURE", "name": "Review Closing Disclosure", "description": "Review your closing disclosure carefully", "order_index": 1, "is_required": True, "is_borrower_action": True},
        {"milestone_code": "CTC_DISCLOSURE_SIGNED", "name": "Sign Closing Disclosure", "description": "E-sign your closing disclosure", "order_index": 1, "is_required": True, "is_borrower_action": True},
        {"milestone_code": "CTC_SCHEDULED", "name": "Upload Homeowners Insurance", "description": "Provide proof of homeowners insurance", "order_index": 1, "is_required": True, "is_borrower_action": True},
        {"milestone_code": "CTC_SCHEDULED", "name": "Wire Funds", "description": "Wire closing funds to title company", "order_index": 2, "is_required": True, "is_borrower_action": True},
    ]

    for task_data in task_templates:
        milestone_id = milestones.get(task_data.pop("milestone_code"))
        if milestone_id:
            task = TaskTemplate(
                milestone_template_id=milestone_id,
                is_active=True,
                is_borrower_visible=True,
                **task_data
            )
            session.add(task)

    session.commit()
    print(f"Seeded {len(task_templates)} task templates")
    session.close()


def seed_notification_templates(engine):
    """Seed default notification templates."""
    from sqlalchemy.orm import Session

    session = Session(bind=engine)

    # Check if templates already exist
    existing = session.query(NotificationTemplate).count()
    if existing > 0:
        print(f"Notification templates already exist ({existing} found), skipping seed...")
        session.close()
        return

    print("Seeding notification templates...")

    templates = [
        {
            "event_type": "milestone_completed",
            "channel": NotificationChannel.EMAIL,
            "subject": "Milestone Completed: {{milestone_name}}",
            "body_template": """
<h2>Great news, {{borrower_name}}!</h2>
<p>Your loan has reached a new milestone: <strong>{{milestone_name}}</strong></p>
<p>{{milestone_description}}</p>
<p>Completed on: {{completed_date}}</p>
<p>If you have any questions, please contact {{lo_name}}.</p>
""",
            "variables": ["borrower_name", "milestone_name", "milestone_description", "completed_date", "lo_name"],
        },
        {
            "event_type": "document_needed",
            "channel": NotificationChannel.EMAIL,
            "subject": "Document Needed: {{document_type}}",
            "body_template": """
<h2>Hi {{borrower_name}},</h2>
<p>We need the following document to continue processing your loan:</p>
<p><strong>{{document_type}}</strong></p>
<p>Please upload this document by {{due_date}}.</p>
<p>You can upload documents through your borrower portal.</p>
""",
            "variables": ["borrower_name", "document_type", "due_date"],
        },
        {
            "event_type": "stage_change",
            "channel": NotificationChannel.EMAIL,
            "subject": "Loan Update: {{stage_message}}",
            "body_template": """
<h2>Hi {{borrower_name}},</h2>
<p>{{stage_message}}!</p>
<p>Your loan has moved from <strong>{{from_stage}}</strong> to <strong>{{to_stage}}</strong>.</p>
<p>Log in to your portal to see your updated milestone journey.</p>
""",
            "variables": ["borrower_name", "stage_message", "from_stage", "to_stage"],
        },
        {
            "event_type": "closing_reminder",
            "channel": NotificationChannel.EMAIL,
            "subject": "{{business_days_remaining}} Business Days Until Closing!",
            "body_template": """
<h2>Hi {{borrower_name}},</h2>
<p>Your closing is coming up!</p>
<p><strong>Closing Date:</strong> {{closing_day}}, {{closing_date}}</p>
<p><strong>Business Days Remaining:</strong> {{business_days_remaining}}</p>
<p>Make sure you have completed all outstanding tasks in your portal.</p>
""",
            "variables": ["borrower_name", "closing_day", "closing_date", "business_days_remaining"],
        },
        {
            "event_type": "home_value_update",
            "channel": NotificationChannel.EMAIL,
            "subject": "Your Home Value Update",
            "body_template": """
<h2>Hi {{borrower_name}},</h2>
<p>Here's your latest home value estimate:</p>
<p><strong>Estimated Value:</strong> {{current_value}}</p>
<p><strong>Appreciation:</strong> {{appreciation_percent}} since purchase</p>
<p>Log in to your portal to see detailed insights about your home's value.</p>
""",
            "variables": ["borrower_name", "current_value", "appreciation_percent"],
        },
        {
            "event_type": "partner_portal_invite",
            "channel": NotificationChannel.EMAIL,
            "subject": "Access Your Partner Portal",
            "body_template": """
<h2>Hi {{partner_name}},</h2>
<p>You've been granted access to view loan progress.</p>
<p>Click the link below to access the partner portal:</p>
<p><a href="{{portal_url}}">Access Portal</a></p>
<p>This link is unique to you. Please do not share it.</p>
""",
            "variables": ["partner_name", "portal_url"],
        },
    ]

    for template_data in templates:
        template = NotificationTemplate(is_active=True, **template_data)
        session.add(template)

    session.commit()
    print(f"Seeded {len(templates)} notification templates")
    session.close()


def seed_federal_holidays(engine):
    """Seed federal holidays for current and next year."""
    from sqlalchemy.orm import Session
    from sqlalchemy import extract
    from services.portal_close_on_time_service import PortalCloseOnTimeService

    session = Session(bind=engine)

    # Check if holidays already exist
    current_year = date.today().year
    existing = session.query(FederalHoliday).filter(
        extract('year', FederalHoliday.holiday_date) == current_year
    ).count()

    if existing > 0:
        print(f"Federal holidays already exist for {current_year}, skipping seed...")
        session.close()
        return

    print("Seeding federal holidays...")

    service = PortalCloseOnTimeService(session)

    # Seed current year and next year
    result1 = service.seed_federal_holidays(current_year)
    result2 = service.seed_federal_holidays(current_year + 1)

    print(f"Seeded {result1['holidays_created']} holidays for {current_year}")
    print(f"Seeded {result2['holidays_created']} holidays for {current_year + 1}")

    session.close()


def run_migration():
    """Run the complete migration."""
    print(f"Connecting to database: {DATABASE_URL[:50]}...")

    engine = create_engine(DATABASE_URL)

    # Create tables
    create_tables(engine)

    # Seed data
    seed_milestone_templates(engine)
    seed_task_templates(engine)
    seed_notification_templates(engine)
    seed_federal_holidays(engine)

    print("\nMigration complete!")


if __name__ == "__main__":
    run_migration()
