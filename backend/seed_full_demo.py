#!/usr/bin/env python3
"""
Full Demo Seed Script — Perennia AI
====================================
Creates a comprehensive demo account for product presentations.
Populates Summit Home Loans org with realistic data across all CRM modules:
  - Organization, branch, users (demo LO + teammates)
  - Leads, loans, MUM clients, referral partners
  - Tasks, documents, calendar events
  - SMS conversations, call intelligence records
  - Activity history, AI metrics, rate monitor alerts
  - Workflows, compliance records, borrower portal data
  - Content/campaigns, team chat, notifications

Usage:
    DATABASE_URL=<url> python3 seed_full_demo.py

The script is idempotent: re-running skips rows that already exist.
"""

import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from passlib.context import CryptContext
from sqlalchemy import create_engine, text

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ---------------------------------------------------------------------------
# Config constants
# ---------------------------------------------------------------------------

ORG_NAME = "Summit Home Loans"
ORG_SLUG = "summit-home-loans"
DEMO_EMAIL = "demo@perenniaai.com"
DEMO_PASSWORD = "Password1!"
NOW = datetime.now(timezone.utc)
TODAY = NOW.date()

# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------


def days_ago(n: int) -> datetime:
    """Return a UTC datetime n days before NOW."""
    return NOW - timedelta(days=n)


def days_from_now(n: int) -> datetime:
    """Return a UTC datetime n days after NOW."""
    return NOW + timedelta(days=n)


def date_ago(n: int):
    """Return a date n days before TODAY."""
    return TODAY - timedelta(days=n)


def date_from_now(n: int):
    """Return a date n days after TODAY."""
    return TODAY + timedelta(days=n)


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def get_engine():
    """Build a SQLAlchemy engine from DATABASE_URL env var."""
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print("ERROR: DATABASE_URL environment variable is not set.")
        sys.exit(1)
    # Railway / Heroku use postgres:// — SQLAlchemy 1.4+ requires postgresql://
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return create_engine(url, echo=False)


def exists(conn, table: str, column: str, value) -> bool:
    """Return True if a row matching column=value exists in table."""
    result = conn.execute(
        text(f"SELECT 1 FROM {table} WHERE {column} = :val LIMIT 1"),
        {"val": value},
    )
    return result.fetchone() is not None


def get_id(conn, table: str, column: str, value):
    """Return the id of the first row matching column=value, or None."""
    result = conn.execute(
        text(f"SELECT id FROM {table} WHERE {column} = :val LIMIT 1"),
        {"val": value},
    )
    row = result.fetchone()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# Seed functions — stubs (to be implemented in subsequent tasks)
# ---------------------------------------------------------------------------


def seed_organization(conn):
    """Create the demo organization. Returns org_id."""
    pass


def seed_branch(conn, org_id):
    """Create the demo branch. Returns branch_id."""
    pass


def seed_users(conn, org_id, branch_id):
    """Create the demo user and teammates. Returns dict of user_ids."""
    pass


def seed_impersonation_permissions(conn, user_ids):
    """Grant impersonation permissions between users."""
    pass


def seed_leads(conn, org_id, user_ids):
    """Create demo leads at various pipeline stages. Returns list of lead_ids."""
    pass


def seed_loans(conn, org_id, user_ids, lead_ids):
    """Create demo active loans. Returns list of loan_ids."""
    pass


def seed_mum_clients(conn, org_id, user_ids):
    """Create MUM (Mortgage Under Management) clients. Returns list of mum_ids."""
    pass


def seed_referral_partners(conn, org_id, user_ids, lead_ids):
    """Create referral partners linked to leads. Returns list of partner_ids."""
    pass


def seed_tasks(conn, org_id, user_ids, lead_ids, loan_ids):
    """Create demo tasks across users, leads, and loans."""
    pass


def seed_documents(conn, org_id, user_ids, loan_ids):
    """Create demo document records for loans."""
    pass


def seed_calendar(conn, org_id, user_ids, lead_ids, loan_ids):
    """Create demo calendar events and appointments."""
    pass


def seed_sms_conversations(conn, org_id, user_ids, lead_ids):
    """Create demo SMS conversation threads."""
    pass


def seed_call_intelligence(conn, org_id, user_ids, lead_ids):
    """Create demo call records with AI analysis."""
    pass


def seed_activities_and_history(conn, org_id, user_ids, lead_ids, loan_ids):
    """Create activity log entries for leads and loans."""
    pass


def seed_ai_metrics(conn, org_id):
    """Create demo AI usage metrics and performance data."""
    pass


def seed_rate_monitor(conn, org_id, mum_ids, loan_ids):
    """Create rate monitor alerts and rate watch records."""
    pass


def seed_workflows_and_compliance(conn, org_id, user_ids, lead_ids, loan_ids):
    """Create workflow automation records and compliance checks."""
    pass


def seed_borrower_portal(conn, org_id, lead_ids, loan_ids):
    """Create borrower portal sessions and document requests."""
    pass


def seed_content_and_campaigns(conn, org_id, user_ids, lead_ids):
    """Create content pieces and marketing campaign records."""
    pass


def seed_team_chat(conn, org_id, user_ids):
    """Create team chat channel messages."""
    pass


def seed_notifications(conn, org_id, user_ids):
    """Create demo in-app notification records."""
    pass


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------


def main():
    print("🔌 Connecting...")
    engine = get_engine()

    with engine.connect() as conn:
        print("✅ Connected")

        org_id = seed_organization(conn)
        branch_id = seed_branch(conn, org_id)
        user_ids = seed_users(conn, org_id, branch_id)
        seed_impersonation_permissions(conn, user_ids)
        lead_ids = seed_leads(conn, org_id, user_ids)
        loan_ids = seed_loans(conn, org_id, user_ids, lead_ids)
        mum_ids = seed_mum_clients(conn, org_id, user_ids)
        partner_ids = seed_referral_partners(conn, org_id, user_ids, lead_ids)
        seed_tasks(conn, org_id, user_ids, lead_ids, loan_ids)
        seed_documents(conn, org_id, user_ids, loan_ids)
        seed_calendar(conn, org_id, user_ids, lead_ids, loan_ids)
        seed_sms_conversations(conn, org_id, user_ids, lead_ids)
        seed_call_intelligence(conn, org_id, user_ids, lead_ids)
        seed_activities_and_history(conn, org_id, user_ids, lead_ids, loan_ids)
        seed_ai_metrics(conn, org_id)
        seed_rate_monitor(conn, org_id, mum_ids, loan_ids)
        seed_workflows_and_compliance(conn, org_id, user_ids, lead_ids, loan_ids)
        seed_borrower_portal(conn, org_id, lead_ids, loan_ids)
        seed_content_and_campaigns(conn, org_id, user_ids, lead_ids)
        seed_team_chat(conn, org_id, user_ids)
        seed_notifications(conn, org_id, user_ids)

    print("\n🎉 Demo seed complete!")
    print(f"   Org  : {ORG_NAME} (slug: {ORG_SLUG})")
    print(f"   Login: {DEMO_EMAIL}")
    print(f"   Pass : {DEMO_PASSWORD}")


if __name__ == "__main__":
    main()
