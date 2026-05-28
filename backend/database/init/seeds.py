"""
Seed Data - Sample/demo data and holiday seed data.

Contains:
    seed_holidays()      - Seed US federal holidays for SLA calculations
    create_sample_data() - Create demo users, leads, loans, tasks, partners, MUM clients
"""
import os
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def seed_holidays(engine):
    """Seed 2026 US federal holidays for business day SLA calculations (org_id=0 = system defaults)."""
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO company_holidays (organization_id, holiday_date, holiday_name, is_recurring)
                VALUES
                    (0, '2026-01-01', 'New Year''s Day', false),
                    (0, '2026-01-19', 'Martin Luther King Jr. Day', false),
                    (0, '2026-02-16', 'Presidents'' Day', false),
                    (0, '2026-05-25', 'Memorial Day', false),
                    (0, '2026-06-19', 'Juneteenth', false),
                    (0, '2026-07-03', 'Independence Day (Observed)', false),
                    (0, '2026-09-07', 'Labor Day', false),
                    (0, '2026-10-12', 'Columbus Day', false),
                    (0, '2026-11-11', 'Veterans Day', false),
                    (0, '2026-11-26', 'Thanksgiving Day', false),
                    (0, '2026-12-25', 'Christmas Day', false)
                ON CONFLICT DO NOTHING
            """))
            conn.commit()
            logger.info("Holiday seed data inserted/verified")
    except Exception as e:
        logger.warning(f"Holiday seed data note: {e}")


def create_sample_data(db: Session):
    """Create sample data for testing."""
    # Lazy imports to avoid circular dependencies
    from database.models import User, Branch, Lead, Loan, AITask, MUMClient
    from database.models.referral import ReferralPartner
    from database.enums import LeadStage, LoanStage, TaskType
    import bcrypt as _bcrypt

    # Import generate_ai_insights from DRE helpers
    try:
        from services.dre_helpers import generate_ai_insights
    except ImportError:
        def generate_ai_insights(loan):
            return f"AI insights for loan {getattr(loan, 'loan_number', 'unknown')}"

    def get_password_hash(password):
        return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()

    try:
        # Check if data already exists
        existing_demo = db.query(User).filter(User.email == "admin@perenniaai.com").first()
        existing_admin = db.query(User).filter(User.email == "admin@perenniaai.com").first()

        if existing_demo or existing_admin:
            logger.info("Sample data already exists")
            return

        # Create demo branch
        branch = Branch(
            name="Main Office",
            company="Demo Mortgage Company",
            nmls_id="123456"
        )
        db.add(branch)
        db.commit()

        # Create demo user
        _demo_pw = os.getenv("DEMO_USER_PASSWORD", "")
        if not _demo_pw:
            raise ValueError("DEMO_USER_PASSWORD env var required")
        demo_user = User(
            email="admin@perenniaai.com",
            hashed_password=get_password_hash(_demo_pw),
            full_name="Admin",
            role="admin",
            branch_id=branch.id
        )
        db.add(demo_user)
        db.commit()

        # Create sample leads
        sample_leads = [
            Lead(
                name="John Smith",
                email="john.smith@email.com",
                phone="555-0101",
                stage=LeadStage.NEW,
                source="Website",
                loan_type="Purchase",
                preapproval_amount=450000,
                credit_score=750,
                debt_to_income=0.35,
                owner_id=demo_user.id,
                ai_score=85,
                sentiment="positive",
                next_action="Schedule initial consultation"
            ),
            Lead(
                name="Sarah Johnson",
                email="sarah.j@email.com",
                phone="555-0102",
                stage=LeadStage.PROSPECT,
                source="Referral",
                loan_type="Refinance",
                preapproval_amount=350000,
                credit_score=720,
                debt_to_income=0.40,
                owner_id=demo_user.id,
                ai_score=78,
                sentiment="positive",
                next_action="Send pre-qualification letter"
            ),
            Lead(
                name="Mike Williams",
                email="mike.w@email.com",
                phone="555-0103",
                stage=LeadStage.Application,
                source="Zillow",
                loan_type="Purchase",
                preapproval_amount=525000,
                credit_score=680,
                debt_to_income=0.42,
                owner_id=demo_user.id,
                ai_score=65,
                sentiment="neutral",
                next_action="Collect additional documentation"
            )
        ]

        for lead in sample_leads:
            db.add(lead)
        db.commit()

        # Create sample loans
        sample_loans = [
            Loan(
                loan_number="L2024-001",
                borrower_name="Emily Davis",
                amount=400000,
                stage=LoanStage.PROCESSING,
                program="Conventional",
                loan_type="Purchase",
                rate=6.875,
                term=360,
                property_address="123 Main St, Anytown, CA",
                closing_date=datetime.now(timezone.utc) + timedelta(days=25),
                loan_officer_id=demo_user.id,
                processor="Jane Processor",
                days_in_stage=5,
                sla_status="on-track"
            ),
            Loan(
                loan_number="L2024-002",
                borrower_name="Robert Brown",
                amount=550000,
                stage=LoanStage.UW_RECEIVED,
                program="FHA",
                loan_type="Purchase",
                rate=7.125,
                term=360,
                property_address="456 Oak Ave, Somewhere, CA",
                closing_date=datetime.now(timezone.utc) + timedelta(days=18),
                loan_officer_id=demo_user.id,
                processor="John Processor",
                underwriter="Sarah UW",
                days_in_stage=3,
                sla_status="on-track"
            )
        ]

        for loan in sample_loans:
            loan.ai_insights = generate_ai_insights(loan)
            db.add(loan)
        db.commit()

        # Create sample tasks
        sample_tasks = [
            AITask(
                title="Review appraisal for L2024-001",
                description="Appraisal came in at $395,000 - need to discuss with borrower",
                type=TaskType.HUMAN_NEEDED,
                category="Documentation",
                priority="high",
                ai_confidence=85,
                borrower_name="Emily Davis",
                loan_id=sample_loans[0].id,
                assigned_to_id=demo_user.id,
                due_date=datetime.now(timezone.utc) + timedelta(days=1)
            ),
            AITask(
                title="Follow up on income verification",
                description="Waiting on 2023 W2 from borrower",
                type=TaskType.IN_PROGRESS,
                category="Documentation",
                priority="medium",
                ai_confidence=92,
                borrower_name="Robert Brown",
                loan_id=sample_loans[1].id,
                assigned_to_id=demo_user.id,
                due_date=datetime.now(timezone.utc) + timedelta(days=3)
            )
        ]

        for task in sample_tasks:
            db.add(task)
        db.commit()

        # Create sample referral partners
        sample_partners = [
            ReferralPartner(
                name="Jane Realtor",
                company="Premier Realty",
                type="Real Estate Agent",
                phone="555-0200",
                email="jane@premierrealty.com",
                referrals_in=15,
                closed_loans=8,
                volume=3200000,
                loyalty_tier="gold",
                status="active"
            ),
            ReferralPartner(
                name="Bob Builder",
                company="Custom Homes Inc",
                type="Builder",
                phone="555-0201",
                email="bob@customhomes.com",
                referrals_in=8,
                closed_loans=5,
                volume=2100000,
                loyalty_tier="silver",
                status="active"
            )
        ]

        for partner in sample_partners:
            db.add(partner)
        db.commit()

        # Create sample MUM clients
        sample_mum = [
            MUMClient(
                name="Previous Borrower 1",
                loan_number="L2023-045",
                original_close_date=datetime.now(timezone.utc) - timedelta(days=365),
                days_since_funding=365,
                original_rate=7.5,
                current_rate=6.875,
                loan_balance=380000,
                refinance_opportunity=True,
                estimated_savings=2375,
                status="opportunity"
            )
        ]

        for mum in sample_mum:
            db.add(mum)
        db.commit()

        logger.info("Sample data created successfully")
        logger.info(f"   Admin user: admin@perenniaai.com")
        logger.info(f"   Created {len(sample_leads)} leads, {len(sample_loans)} loans, {len(sample_tasks)} tasks")

    except Exception as e:
        logger.error(f"Sample data creation failed: {e}")
        db.rollback()
