"""
Shared helpers for seed_full_demo package
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
import secrets
import sys
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import bcrypt as _bcrypt
from sqlalchemy import create_engine, text

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------


class _BcryptCompat:
    """Drop-in replacement providing .hash() over raw bcrypt."""
    def hash(self, password: str) -> str:
        return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()

pwd_context = _BcryptCompat()

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


import re as _re

# Hardcoded allowlist of tables/columns this seed script is permitted to query.
# All callers pass string literals — this is defense-in-depth, not user-input
# sanitization.
_SEED_ALLOWED_TABLES = frozenset({
    "organizations", "users", "leads", "loans", "mum_clients",
    "referral_partners", "tasks", "documents", "activities",
    "scheduler_appointments", "availability_slots", "appointment_types",
    "scheduler_configs", "stage_history", "disclosure_events", "loan_fees",
    "compliance_alerts", "loan_team_members", "morning_briefings",
    "ai_tasks", "email_intakes", "attachment_intakes",
    "sms_conversations", "sms_messages", "call_records",
    "call_intelligence_records", "rate_monitor_alerts",
    "content_items", "content_campaigns", "notifications",
    "borrower_profiles", "borrower_applications",
})

_SEED_ALLOWED_COLUMNS = frozenset({
    "id", "slug", "email", "name", "loan_number", "client_name",
    "organization_id", "user_id", "owner_id",
})


def _validate_seed_identifier(name: str) -> str:
    """Validate that a SQL identifier is alphanumeric+underscore only."""
    if not _re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', name):
        raise ValueError(f"Invalid SQL identifier in seed script: {name!r}")
    return name


def exists(conn, table: str, column: str, value) -> bool:
    """Return True if a row matching column=value exists in table.

    SAFETY: table and column come from hardcoded string literals at each call
    site within this seed script. Validated against allowlists and regex for
    defense-in-depth. The value uses :val bind parameter.
    """
    _validate_seed_identifier(table)
    _validate_seed_identifier(column)
    if table not in _SEED_ALLOWED_TABLES:
        raise ValueError(f"Seed script: table {table!r} not in allowlist")
    if column not in _SEED_ALLOWED_COLUMNS:
        raise ValueError(f"Seed script: column {column!r} not in allowlist")
    result = conn.execute(
        text(f"SELECT 1 FROM {table} WHERE {column} = :val LIMIT 1"),
        {"val": value},
    )
    return result.fetchone() is not None


def get_id(conn, table: str, column: str, value):
    """Return the id of the first row matching column=value, or None.

    SAFETY: table and column come from hardcoded string literals at each call
    site within this seed script. Validated against allowlists and regex for
    defense-in-depth. The value uses :val bind parameter.
    """
    _validate_seed_identifier(table)
    _validate_seed_identifier(column)
    if table not in _SEED_ALLOWED_TABLES:
        raise ValueError(f"Seed script: table {table!r} not in allowlist")
    if column not in _SEED_ALLOWED_COLUMNS:
        raise ValueError(f"Seed script: column {column!r} not in allowlist")
    result = conn.execute(
        text(f"SELECT id FROM {table} WHERE {column} = :val LIMIT 1"),
        {"val": value},
    )
    row = result.fetchone()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# Seed functions — stubs (to be implemented in subsequent tasks)
# ---------------------------------------------------------------------------


