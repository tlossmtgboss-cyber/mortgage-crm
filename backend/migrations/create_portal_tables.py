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
    LifecycleStage, MilestoneStatus, TaskStatus, PortalUserRole,
    DocumentType, DocumentStatus, NotificationChannel, NotificationStatus, NotificationPriority,
    PortalLoan, LifecycleStateHistory,
    MilestoneTemplate, MilestoneInstance, TaskTemplate, TaskInstance,
    FederalHoliday, CloseOnTimeSchedule, CloseOnTimeMilestone,
    PortalDocument, DocumentExtraction, PropertyCosts,
    HomePriceIndex, PropertyValueBaseline, PropertyValuation, HomeValueInsight,
    NotificationTemplate, NotificationQueue,
    LoanActivityLog, RiskFlag, PartnerAccessToken,
    AnnualRefreshCycle, PresentationSession, PortalPresentationScenario, PresentationCitation
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
        PortalPresentationScenario.__table__,
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
            "key": "PREAPP_START",
            "name": "Application Started",
            "description": "Your loan application has been initiated",
            "stage": LifecycleStage.PREAPPROVAL,
            "display_order": 1,
            "icon": "file-text",
            "color_code": "#3B82F6",
        },
        {
            "key": "PREAPP_DOCS",
            "name": "Documents Submitted",
            "description": "Initial documents have been received",
            "stage": LifecycleStage.PREAPPROVAL,
            "display_order": 2,
            "icon": "upload",
            "color_code": "#8B5CF6",
        },
        {
            "key": "PREAPP_REVIEW",
            "name": "Application Under Review",
            "description": "Your application is being reviewed by our team",
            "stage": LifecycleStage.PREAPPROVAL,
            "display_order": 3,
            "icon": "search",
            "color_code": "#EC4899",
        },
        {
            "key": "PREAPP_APPROVED",
            "name": "Pre-Approval Issued",
            "description": "Congratulations! You have been pre-approved",
            "stage": LifecycleStage.PREAPPROVAL,
            "display_order": 4,
            "icon": "check-circle",
            "color_code": "#10B981",
        },

        # Under Contract Stage
        {
            "key": "CONTRACT_RECEIVED",
            "name": "Contract Received",
            "description": "Purchase contract has been received",
            "stage": LifecycleStage.UNDER_CONTRACT,
            "display_order": 1,
            "icon": "file-signature",
            "color_code": "#F59E0B",
        },
        {
            "key": "CONTRACT_REVIEWED",
            "name": "Contract Reviewed",
            "description": "Contract terms have been reviewed",
            "stage": LifecycleStage.UNDER_CONTRACT,
            "display_order": 2,
            "icon": "clipboard-check",
            "color_code": "#3B82F6",
        },

        # Processing Stage
        {
            "key": "PROC_APPRAISAL",
            "name": "Appraisal Ordered",
            "description": "Property appraisal has been ordered",
            "stage": LifecycleStage.PROCESSING,
            "display_order": 1,
            "icon": "home",
            "color_code": "#6366F1",
        },
        {
            "key": "PROC_APPRAISAL_RECEIVED",
            "name": "Appraisal Received",
            "description": "Property appraisal report is in",
            "stage": LifecycleStage.PROCESSING,
            "display_order": 2,
            "icon": "file-check",
            "color_code": "#8B5CF6",
        },
        {
            "key": "PROC_TITLE",
            "name": "Title Ordered",
            "description": "Title search has been ordered",
            "stage": LifecycleStage.PROCESSING,
            "display_order": 3,
            "icon": "shield",
            "color_code": "#EC4899",
        },
        {
            "key": "PROC_SUBMITTED",
            "name": "Submitted to Underwriting",
            "description": "Your file has been submitted for underwriting",
            "stage": LifecycleStage.PROCESSING,
            "display_order": 4,
            "icon": "send",
            "color_code": "#F59E0B",
        },
        {
            "key": "PROC_CONDITIONAL",
            "name": "Conditional Approval",
            "description": "Loan conditionally approved pending final items",
            "stage": LifecycleStage.PROCESSING,
            "display_order": 5,
            "icon": "check",
            "color_code": "#10B981",
        },
        {
            "key": "PROC_CONDITIONS",
            "name": "Final Conditions Cleared",
            "description": "All conditions have been satisfied",
            "stage": LifecycleStage.PROCESSING,
            "display_order": 6,
            "icon": "check-circle",
            "color_code": "#059669",
        },

        # Clear to Close Stage
        {
            "key": "CTC_APPROVED",
            "name": "Clear to Close",
            "description": "Your loan is clear to close!",
            "stage": LifecycleStage.CLEAR_TO_CLOSE,
            "display_order": 1,
            "icon": "award",
            "color_code": "#10B981",
        },
        {
            "key": "CTC_DISCLOSURE",
            "name": "Closing Disclosure Sent",
            "description": "Your closing disclosure has been sent",
            "stage": LifecycleStage.CLEAR_TO_CLOSE,
            "display_order": 2,
            "icon": "file-text",
            "color_code": "#3B82F6",
        },
        {
            "key": "CTC_DISCLOSURE_SIGNED",
            "name": "Closing Disclosure Signed",
            "description": "Closing disclosure has been acknowledged",
            "stage": LifecycleStage.CLEAR_TO_CLOSE,
            "display_order": 3,
            "icon": "pen",
            "color_code": "#8B5CF6",
        },
        {
            "key": "CTC_SCHEDULED",
            "name": "Closing Scheduled",
            "description": "Your closing date is confirmed",
            "stage": LifecycleStage.CLEAR_TO_CLOSE,
            "display_order": 4,
            "icon": "calendar",
            "color_code": "#F59E0B",
        },

        # Funded Stage
        {
            "key": "FUNDED_CLOSED",
            "name": "Closed",
            "description": "Loan documents have been signed",
            "stage": LifecycleStage.FUNDED,
            "display_order": 1,
            "icon": "pen-tool",
            "color_code": "#10B981",
        },
        {
            "key": "FUNDED_RECORDED",
            "name": "Recorded",
            "description": "Deed has been recorded",
            "stage": LifecycleStage.FUNDED,
            "display_order": 2,
            "icon": "book",
            "color_code": "#6366F1",
        },
        {
            "key": "FUNDED_DISBURSED",
            "name": "Funds Disbursed",
            "description": "Congratulations! Your loan has been funded",
            "stage": LifecycleStage.FUNDED,
            "display_order": 3,
            "icon": "dollar-sign",
            "color_code": "#059669",
        },
    ]

    for template_data in templates:
        template = MilestoneTemplate(
            is_active=True,
            visible_to_borrower=True,
            visible_to_partner=True,
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
    milestones = {m.key: m.id for m in session.query(MilestoneTemplate).all()}

    task_templates = [
        # Pre-Approval Tasks
        {"milestone_key": "PREAPP_DOCS", "key": "upload_paystubs", "title": "Upload Pay Stubs", "instructions": "Upload your most recent pay stubs", "display_order": 1, "is_required": True, "owner_role": PortalUserRole.BORROWER, "cta_type": "UPLOAD"},
        {"milestone_key": "PREAPP_DOCS", "key": "upload_bank_statements", "title": "Upload Bank Statements", "instructions": "Upload 2 months of bank statements", "display_order": 2, "is_required": True, "owner_role": PortalUserRole.BORROWER, "cta_type": "UPLOAD"},
        {"milestone_key": "PREAPP_DOCS", "key": "upload_tax_returns", "title": "Upload Tax Returns", "instructions": "Upload last 2 years of tax returns", "display_order": 3, "is_required": True, "owner_role": PortalUserRole.BORROWER, "cta_type": "UPLOAD"},
        {"milestone_key": "PREAPP_DOCS", "key": "upload_id", "title": "Upload ID", "instructions": "Upload government-issued ID", "display_order": 4, "is_required": True, "owner_role": PortalUserRole.BORROWER, "cta_type": "UPLOAD"},

        # Under Contract Tasks
        {"milestone_key": "CONTRACT_RECEIVED", "key": "upload_purchase_contract", "title": "Upload Purchase Contract", "instructions": "Upload signed purchase agreement", "display_order": 1, "is_required": True, "owner_role": PortalUserRole.BORROWER, "cta_type": "UPLOAD"},
        {"milestone_key": "CONTRACT_REVIEWED", "key": "review_contract_terms", "title": "Review Contract Terms", "instructions": "LO reviews contract terms", "display_order": 1, "is_required": True, "owner_role": PortalUserRole.LO},

        # Processing Tasks
        {"milestone_key": "PROC_CONDITIONAL", "key": "clear_conditions", "title": "Clear Conditions", "instructions": "Provide any additional documents requested", "display_order": 1, "is_required": True, "owner_role": PortalUserRole.BORROWER, "cta_type": "UPLOAD"},

        # Clear to Close Tasks
        {"milestone_key": "CTC_DISCLOSURE", "key": "review_cd", "title": "Review Closing Disclosure", "instructions": "Review your closing disclosure carefully", "display_order": 1, "is_required": True, "owner_role": PortalUserRole.BORROWER},
        {"milestone_key": "CTC_DISCLOSURE_SIGNED", "key": "sign_cd", "title": "Sign Closing Disclosure", "instructions": "E-sign your closing disclosure", "display_order": 1, "is_required": True, "owner_role": PortalUserRole.BORROWER, "cta_type": "SIGN"},
        {"milestone_key": "CTC_SCHEDULED", "key": "upload_insurance", "title": "Upload Homeowners Insurance", "instructions": "Provide proof of homeowners insurance", "display_order": 1, "is_required": True, "owner_role": PortalUserRole.BORROWER, "cta_type": "UPLOAD"},
        {"milestone_key": "CTC_SCHEDULED", "key": "wire_funds", "title": "Wire Funds", "instructions": "Wire closing funds to title company", "display_order": 2, "is_required": True, "owner_role": PortalUserRole.BORROWER},
    ]

    for task_data in task_templates:
        milestone_id = milestones.get(task_data.pop("milestone_key"))
        if milestone_id:
            task = TaskTemplate(
                milestone_template_id=milestone_id,
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
            "key": "milestone_completed",
            "name": "Milestone Completed",
            "description": "Sent when a milestone is completed",
            "trigger_event": "milestone_completed",
            "target_role": PortalUserRole.BORROWER,
            "channels": [NotificationChannel.EMAIL.value],
            "priority": NotificationPriority.MEDIUM,
            "subject_template": "Milestone Completed: {{milestone_name}}",
            "body_template": """
<h2>Great news, {{borrower_name}}!</h2>
<p>Your loan has reached a new milestone: <strong>{{milestone_name}}</strong></p>
<p>{{milestone_description}}</p>
<p>Completed on: {{completed_date}}</p>
<p>If you have any questions, please contact {{lo_name}}.</p>
""",
        },
        {
            "key": "document_needed",
            "name": "Document Needed",
            "description": "Sent when a document is requested",
            "trigger_event": "document_needed",
            "target_role": PortalUserRole.BORROWER,
            "channels": [NotificationChannel.EMAIL.value],
            "priority": NotificationPriority.HIGH,
            "subject_template": "Document Needed: {{document_type}}",
            "body_template": """
<h2>Hi {{borrower_name}},</h2>
<p>We need the following document to continue processing your loan:</p>
<p><strong>{{document_type}}</strong></p>
<p>Please upload this document by {{due_date}}.</p>
<p>You can upload documents through your borrower portal.</p>
""",
        },
        {
            "key": "stage_change",
            "name": "Stage Change",
            "description": "Sent when loan moves to a new stage",
            "trigger_event": "stage_change",
            "target_role": PortalUserRole.BORROWER,
            "channels": [NotificationChannel.EMAIL.value],
            "priority": NotificationPriority.MEDIUM,
            "subject_template": "Loan Update: {{stage_message}}",
            "body_template": """
<h2>Hi {{borrower_name}},</h2>
<p>{{stage_message}}!</p>
<p>Your loan has moved from <strong>{{from_stage}}</strong> to <strong>{{to_stage}}</strong>.</p>
<p>Log in to your portal to see your updated milestone journey.</p>
""",
        },
        {
            "key": "closing_reminder",
            "name": "Closing Reminder",
            "description": "Sent to remind borrower of upcoming closing",
            "trigger_event": "closing_reminder",
            "target_role": PortalUserRole.BORROWER,
            "channels": [NotificationChannel.EMAIL.value, NotificationChannel.SMS.value],
            "priority": NotificationPriority.HIGH,
            "subject_template": "{{business_days_remaining}} Business Days Until Closing!",
            "body_template": """
<h2>Hi {{borrower_name}},</h2>
<p>Your closing is coming up!</p>
<p><strong>Closing Date:</strong> {{closing_day}}, {{closing_date}}</p>
<p><strong>Business Days Remaining:</strong> {{business_days_remaining}}</p>
<p>Make sure you have completed all outstanding tasks in your portal.</p>
""",
            "sms_template": "Hi {{borrower_name}}! Your closing is in {{business_days_remaining}} business days on {{closing_date}}. Check your portal for any outstanding tasks.",
        },
        {
            "key": "home_value_update",
            "name": "Home Value Update",
            "description": "Sent with home value estimate updates",
            "trigger_event": "home_value_update",
            "target_role": PortalUserRole.BORROWER,
            "channels": [NotificationChannel.EMAIL.value],
            "priority": NotificationPriority.LOW,
            "subject_template": "Your Home Value Update",
            "body_template": """
<h2>Hi {{borrower_name}},</h2>
<p>Here's your latest home value estimate:</p>
<p><strong>Estimated Value:</strong> {{current_value}}</p>
<p><strong>Appreciation:</strong> {{appreciation_percent}} since purchase</p>
<p>Log in to your portal to see detailed insights about your home's value.</p>
""",
        },
        {
            "key": "partner_portal_invite",
            "name": "Partner Portal Invite",
            "description": "Sent to partners with portal access link",
            "trigger_event": "partner_portal_invite",
            "target_role": PortalUserRole.REALTOR,
            "channels": [NotificationChannel.EMAIL.value],
            "priority": NotificationPriority.MEDIUM,
            "subject_template": "Access Your Partner Portal",
            "body_template": """
<h2>Hi {{partner_name}},</h2>
<p>You've been granted access to view loan progress.</p>
<p>Click the link below to access the partner portal:</p>
<p><a href="{{portal_url}}">Access Portal</a></p>
<p>This link is unique to you. Please do not share it.</p>
""",
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
