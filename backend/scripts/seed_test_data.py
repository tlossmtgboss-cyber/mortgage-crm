#!/usr/bin/env python3
"""
CRM Test Data Seeder
====================
This script:
1. Creates a backup of existing data
2. Wipes transactional data (loans, leads, tasks, etc.)
3. Seeds the test team (1 LO, 1 Processor, 2 PAs, 5 UWs)
4. Seeds 30 test scenarios provided by Tim

Usage:
    python scripts/seed_test_data.py --backup-only  # Just create backup
    python scripts/seed_test_data.py --wipe-only    # Just wipe data (after manual backup)
    python scripts/seed_test_data.py                # Full run: backup, wipe, seed
"""

import logging
import os
import sys
import json
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import bcrypt as _bcrypt

# Import models
from database import Base
from database.enums import (
    LeadStage,
    LoanStage,
    RateLockStatus,
    RateLockRecommendation,
    BuyingTimelineCategory,
    BorrowerRiskProfile,
)
from database.models import User, Lead, Loan, MUMClient, Task, AITask, Activity

# Password hashing


class _BcryptCompat:
    """Drop-in replacement providing .hash() over raw bcrypt."""
    def hash(self, password: str) -> str:
        return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()

pwd_context = _BcryptCompat()

# Database URL
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mortgage_crm.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Create engine
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# =============================================================================
# TEST TEAM MEMBERS
# =============================================================================
TEST_TEAM = [
    {
        "employee_code": "LO001",
        "full_name": "Timothy Loss",
        "email": "tim.loss@example.com",
        "role": "loan_officer",
        "permission_role": "sales"
    },
    {
        "employee_code": "PR001",
        "full_name": "Jessica Marlow",
        "email": "jessica.marlow@example.com",
        "role": "processor",
        "permission_role": "processing"
    },
    {
        "employee_code": "PA101",
        "full_name": "Michael Santos",
        "email": "michael.santos@example.com",
        "role": "production_assistant",
        "permission_role": "operations"
    },
    {
        "employee_code": "PA102",
        "full_name": "Lauren Carter",
        "email": "lauren.carter@example.com",
        "role": "production_assistant",
        "permission_role": "operations"
    },
    {
        "employee_code": "UW201",
        "full_name": "Danielle Brooks",
        "email": "danielle.brooks@example.com",
        "role": "underwriter",
        "permission_role": "operations"
    },
    {
        "employee_code": "UW202",
        "full_name": "Samuel Price",
        "email": "sam.price@example.com",
        "role": "underwriter",
        "permission_role": "operations"
    },
    {
        "employee_code": "UW203",
        "full_name": "Helen Rogers",
        "email": "helen.rogers@example.com",
        "role": "underwriter",
        "permission_role": "operations"
    },
    {
        "employee_code": "UW204",
        "full_name": "Kelvin Abdul",
        "email": "kelvin.abdul@example.com",
        "role": "underwriter",
        "permission_role": "operations"
    },
    {
        "employee_code": "UW205",
        "full_name": "Patricia Donovan",
        "email": "patricia.donovan@example.com",
        "role": "underwriter",
        "permission_role": "operations"
    },
]


# =============================================================================
# 30 TEST SCENARIOS (to be populated)
# =============================================================================
TEST_SCENARIOS = []  # Will be loaded from JSON file or defined inline


def backup_data(db):
    """Create a JSON backup of all transactional data"""
    print("Creating backup...")

    backup = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "leads": [],
        "loans": [],
        "mum_clients": [],
        "tasks": [],
        "ai_tasks": [],
        "activities": []
    }

    # Backup leads
    leads = db.execute(text("SELECT * FROM leads")).fetchall()
    backup["leads"] = [dict(row._mapping) for row in leads] if leads else []

    # Backup loans
    loans = db.execute(text("SELECT * FROM loans")).fetchall()
    backup["loans"] = [dict(row._mapping) for row in loans] if loans else []

    # Backup MUM clients
    try:
        mum_clients = db.execute(text("SELECT * FROM mum_clients")).fetchall()
        backup["mum_clients"] = [dict(row._mapping) for row in mum_clients] if mum_clients else []
    except Exception as e:
        logger.error(f"Error backing up mum_clients in create_backup: {e}")
        backup["mum_clients"] = []

    # Backup tasks
    try:
        tasks = db.execute(text("SELECT * FROM tasks")).fetchall()
        backup["tasks"] = [dict(row._mapping) for row in tasks] if tasks else []
    except Exception as e:
        logger.error(f"Error backing up tasks in create_backup: {e}")
        backup["tasks"] = []

    # Backup AI tasks
    try:
        ai_tasks = db.execute(text("SELECT * FROM ai_tasks")).fetchall()
        backup["ai_tasks"] = [dict(row._mapping) for row in ai_tasks] if ai_tasks else []
    except Exception as e:
        logger.error(f"Error backing up ai_tasks in create_backup: {e}")
        backup["ai_tasks"] = []

    # Backup activities
    try:
        activities = db.execute(text("SELECT * FROM activities")).fetchall()
        backup["activities"] = [dict(row._mapping) for row in activities] if activities else []
    except Exception as e:
        logger.error(f"Error backing up activities in create_backup: {e}")
        backup["activities"] = []

    # Write backup file
    backup_dir = Path(__file__).parent / "backups"
    backup_dir.mkdir(exist_ok=True)

    backup_file = backup_dir / f"crm_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    # Convert datetime objects to strings for JSON serialization
    def json_serial(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Type {type(obj)} not serializable")

    with open(backup_file, 'w') as f:
        json.dump(backup, f, indent=2, default=json_serial)

    print(f"Backup saved to: {backup_file}")
    print(f"  - Leads: {len(backup['leads'])}")
    print(f"  - Loans: {len(backup['loans'])}")
    print(f"  - MUM Clients: {len(backup['mum_clients'])}")
    print(f"  - Tasks: {len(backup['tasks'])}")
    print(f"  - AI Tasks: {len(backup['ai_tasks'])}")
    print(f"  - Activities: {len(backup['activities'])}")

    return backup_file


def wipe_transactional_data(db):
    """Wipe all transactional data from the database"""
    print("\nWiping transactional data...")

    # Tables to wipe (order matters due to foreign keys)
    tables_to_wipe = [
        "activities",
        "ai_tasks",
        "tasks",
        "conversations",
        "ai_delegated_tasks",
        "mum_clients",
        "loans",
        "leads",
    ]

    for table in tables_to_wipe:
        try:
            # For SQLite, use DELETE instead of TRUNCATE
            if DATABASE_URL.startswith("sqlite"):
                db.execute(text(f"DELETE FROM {table}"))
                # Reset the auto-increment counter
                db.execute(text(f"DELETE FROM sqlite_sequence WHERE name='{table}'"))
            else:
                # PostgreSQL - use TRUNCATE with CASCADE
                db.execute(text(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE"))
            print(f"  ✓ Wiped {table}")
        except Exception as e:
            print(f"  ⚠ Could not wipe {table}: {e}")

    db.commit()
    print("Transactional data wiped successfully!")


def seed_team_members(db):
    """Seed the test team members"""
    print("\nSeeding test team members...")

    team_user_ids = {}

    for member in TEST_TEAM:
        # Check if user already exists
        existing = db.query(User).filter(User.email == member["email"]).first()

        if existing:
            print(f"  ✓ {member['full_name']} already exists (id={existing.id})")
            team_user_ids[member["employee_code"]] = existing.id
        else:
            # Create new user
            new_user = User(
                email=member["email"],
                hashed_password=pwd_context.hash("testpass123"),
                full_name=member["full_name"],
                role=member["role"],
                permission_role=member["permission_role"],
                is_active=True,
                user_metadata={"employee_code": member["employee_code"]}
            )
            db.add(new_user)
            db.flush()  # Get the ID
            team_user_ids[member["employee_code"]] = new_user.id
            print(f"  ✓ Created {member['full_name']} (id={new_user.id})")

    db.commit()
    print(f"Team members seeded: {len(team_user_ids)} users")
    return team_user_ids


def seed_test_scenarios(db, team_user_ids, scenarios):
    """Seed the 30 test scenarios"""
    print(f"\nSeeding {len(scenarios)} test scenarios...")

    lo_id = team_user_ids.get("LO001")

    for i, scenario in enumerate(scenarios, 1):
        try:
            # Determine if this is a lead, active loan, or MUM client based on status
            status = scenario.get("status", "").lower()

            if status in ["lead", "new lead", "pre-approved", "preapproved"]:
                # Create as Lead
                lead = create_lead_from_scenario(db, scenario, lo_id, i)
                print(f"  ✓ [{i}/30] Lead: {scenario.get('borrower_name', 'Unknown')}")

            elif status in ["closed", "mum", "closed / mum active", "funded"]:
                # Create as MUM Client (and optionally a funded loan)
                mum = create_mum_from_scenario(db, scenario, lo_id, i)
                print(f"  ✓ [{i}/30] MUM: {scenario.get('borrower_name', 'Unknown')}")

            else:
                # Create as Active Loan (in processing, conditional approval, CTC, etc.)
                loan = create_loan_from_scenario(db, scenario, lo_id, team_user_ids, i)
                print(f"  ✓ [{i}/30] Loan: {scenario.get('borrower_name', 'Unknown')}")

        except Exception as e:
            print(f"  ✗ [{i}/30] Error: {e}")

    db.commit()
    print("Test scenarios seeded successfully!")


def create_lead_from_scenario(db, scenario, owner_id, seq):
    """Create a Lead from a test scenario"""

    # Map status to LeadStage
    status_map = {
        "lead": LeadStage.NEW,
        "new lead": LeadStage.NEW,
        "pre-approved": LeadStage.PRE_APPROVED,
        "preapproved": LeadStage.PRE_APPROVED,
        "application": LeadStage.APPLICATION,
    }

    stage = status_map.get(scenario.get("status", "").lower(), LeadStage.NEW)

    lead = Lead(
        name=scenario.get("borrower_name", f"Test Borrower {seq}"),
        email=scenario.get("email", f"borrower{seq}@test.com"),
        phone=scenario.get("phone", f"555-{seq:04d}"),
        stage=stage,
        source=scenario.get("source", "Test Seed"),
        loan_type=scenario.get("loan_type", "Conventional"),
        preapproval_amount=scenario.get("loan_amount"),
        property_address=scenario.get("property_address"),
        loan_amount=scenario.get("loan_amount"),
        owner_id=owner_id,
        notes=scenario.get("ai_notes", ""),
        user_metadata={"is_test_data": True, "scenario_id": seq}
    )

    # Set dates
    if scenario.get("dates", {}).get("lead_created"):
        lead.created_at = parse_date(scenario["dates"]["lead_created"])
    if scenario.get("dates", {}).get("preapproval_issued"):
        lead.preapproval_issued_date = parse_date(scenario["dates"]["preapproval_issued"])

    db.add(lead)
    db.flush()
    return lead


def create_loan_from_scenario(db, scenario, lo_id, team_user_ids, seq):
    """Create an active Loan from a test scenario"""

    # Map status to LoanStage
    status_map = {
        "in-processing": LoanStage.PROCESSING,
        "in processing": LoanStage.PROCESSING,
        "processing": LoanStage.PROCESSING,
        "conditional approval": LoanStage.APPROVED,
        "conditionally approved": LoanStage.APPROVED,
        "approved": LoanStage.APPROVED,
        "suspended": LoanStage.SUSPENDED,
        "ctc": LoanStage.CTC,
        "clear to close": LoanStage.CTC,
        "submitted": LoanStage.SUBMITTED,
        "uw received": LoanStage.UW_RECEIVED,
    }

    stage = status_map.get(scenario.get("status", "").lower(), LoanStage.PROCESSING)

    # Get underwriter from scenario or assign one
    uw_code = scenario.get("assigned_team", {}).get("underwriter_code")
    uw_name = None
    if uw_code and uw_code in ["UW201", "UW202", "UW203", "UW204", "UW205"]:
        uw_map = {
            "UW201": "Danielle Brooks",
            "UW202": "Samuel Price",
            "UW203": "Helen Rogers",
            "UW204": "Kelvin Abdul",
            "UW205": "Patricia Donovan"
        }
        uw_name = uw_map.get(uw_code)

    loan = Loan(
        loan_number=scenario.get("loan_number", f"TST-{seq:04d}"),
        borrower_name=scenario.get("borrower_name", f"Test Borrower {seq}"),
        stage=stage,
        program=scenario.get("program", "Conventional"),
        loan_type=scenario.get("loan_type", "Purchase"),
        amount=scenario.get("loan_amount", 350000),
        purchase_price=scenario.get("purchase_price"),
        property_address=scenario.get("property_address"),
        rate=scenario.get("interest_rate"),
        loan_officer_id=lo_id,
        processor="Jessica Marlow",
        underwriter=uw_name,
        user_metadata={"is_test_data": True, "scenario_id": seq}
    )

    # Set dates
    dates = scenario.get("dates", {})
    if dates.get("contract_date"):
        loan.contract_received_date = parse_date(dates["contract_date"])
    if dates.get("uw_submission"):
        loan.created_at = parse_date(dates["uw_submission"])
    if dates.get("ctc_date"):
        loan.conditional_approval_date = parse_date(dates["ctc_date"])
    if dates.get("closing_date"):
        loan.closing_date = parse_date(dates["closing_date"])

    # Rate lock status
    if scenario.get("rate_locked"):
        loan.rate_lock_status = RateLockStatus.LOCKED
        loan.lock_date = datetime.now(timezone.utc) - timedelta(days=15)
    else:
        loan.rate_lock_status = RateLockStatus.ELIGIBLE_NO_LOCK
        if scenario.get("lock_guidance"):
            guidance_map = {
                "lock now": RateLockRecommendation.LOCK_NOW,
                "float": RateLockRecommendation.FLOAT_AND_MONITOR,
                "float cautious": RateLockRecommendation.FLOAT_AND_MONITOR,
            }
            loan.rate_lock_recommendation = guidance_map.get(
                scenario.get("lock_guidance", "").lower(),
                RateLockRecommendation.FLOAT_AND_MONITOR
            )

    db.add(loan)
    db.flush()
    return loan


def create_mum_from_scenario(db, scenario, lo_id, seq):
    """Create a MUM Client from a test scenario (closed loan)"""

    mum = MUMClient(
        name=scenario.get("borrower_name", f"Test Borrower {seq}"),
        email=scenario.get("email", f"borrower{seq}@test.com"),
        phone=scenario.get("phone", f"555-{seq:04d}"),
        loan_number=scenario.get("loan_number", f"TST-{seq:04d}"),
        original_close_date=parse_date(scenario.get("dates", {}).get("closing_date")) or datetime.now(timezone.utc),
        close_date=parse_date(scenario.get("dates", {}).get("closing_date")) or datetime.now(timezone.utc),
        original_rate=scenario.get("interest_rate", 6.5),
        current_rate=scenario.get("interest_rate", 6.5),
        loan_balance=scenario.get("loan_amount", 350000),
        loan_officer="Timothy Loss",
        loan_officer_email="tim.loss@example.com",
        processor="Jessica Marlow",
        processor_email="jessica.marlow@example.com",
        status="Active",
        notes=scenario.get("ai_notes", ""),
        user_id=lo_id
    )

    # Calculate days since funding
    if mum.original_close_date:
        mum.days_since_funding = (datetime.now(timezone.utc) - mum.original_close_date.replace(tzinfo=timezone.utc)).days

    db.add(mum)
    db.flush()
    return mum


def parse_date(date_str):
    """Parse a date string into a datetime object"""
    if not date_str:
        return None

    if isinstance(date_str, datetime):
        return date_str

    # Try various formats
    formats = [
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%m/%d/%Y",
        "%m-%d-%Y",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    return None


def load_scenarios_from_file(filepath):
    """Load test scenarios from a JSON file"""
    with open(filepath, 'r') as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(description="CRM Test Data Seeder")
    parser.add_argument("--backup-only", action="store_true", help="Only create backup")
    parser.add_argument("--wipe-only", action="store_true", help="Only wipe data")
    parser.add_argument("--scenarios-file", type=str, help="JSON file with test scenarios")
    args = parser.parse_args()

    db = SessionLocal()

    try:
        # Step 1: Backup
        if not args.wipe_only:
            backup_file = backup_data(db)

        if args.backup_only:
            print("\nBackup complete. Exiting.")
            return

        # Step 2: Wipe
        wipe_transactional_data(db)

        if args.wipe_only:
            print("\nWipe complete. Exiting.")
            return

        # Step 3: Seed team members
        team_user_ids = seed_team_members(db)

        # Step 4: Seed test scenarios
        if args.scenarios_file:
            scenarios = load_scenarios_from_file(args.scenarios_file)
        elif TEST_SCENARIOS:
            scenarios = TEST_SCENARIOS
        else:
            print("\nNo scenarios provided. Use --scenarios-file or define TEST_SCENARIOS.")
            print("Team members have been seeded. You can run again with scenarios.")
            return

        seed_test_scenarios(db, team_user_ids, scenarios)

        print("\n" + "=" * 50)
        print("TEST DATA SEEDING COMPLETE!")
        print("=" * 50)

    finally:
        db.close()


if __name__ == "__main__":
    main()
