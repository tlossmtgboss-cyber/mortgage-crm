"""Auto-extracted from seed_full_demo.py — mechanical decomposition (no logic changes)."""
import json
import random
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import text

from ._shared import (
    NOW,
    TODAY,
    ORG_NAME,
    ORG_SLUG,
    DEMO_EMAIL,
    DEMO_PASSWORD,
    pwd_context,
    days_ago,
    days_from_now,
    date_ago,
    date_from_now,
    exists,
    get_id,
)


def seed_organization(conn):
    """Create the demo organization. Returns org_id."""
    existing_id = get_id(conn, "organizations", "slug", ORG_SLUG)
    if existing_id:
        print("⏭️  Organization exists")
        return existing_id

    result = conn.execute(
        text("""
            INSERT INTO organizations
                (name, slug, subscription_tier, timezone, is_active,
                 booking_slug, booking_primary_color, created_at, updated_at)
            VALUES
                (:name, :slug, :tier, :tz, :active,
                 :booking_slug, :booking_color, :now, :now)
            RETURNING id
        """),
        {
            "name": ORG_NAME,
            "slug": ORG_SLUG,
            "tier": "enterprise",
            "tz": "America/New_York",
            "active": True,
            "booking_slug": ORG_SLUG,
            "booking_color": "#1a73e8",
            "now": NOW,
        },
    )
    org_id = result.fetchone()[0]
    conn.commit()
    print(f"✅ Created organization (id={org_id})")
    return org_id


def seed_branch(conn, org_id):
    """Create the demo branch. Returns branch_id."""
    existing_id = get_id(conn, "branches", "nmls_id", "789012")
    if existing_id:
        return existing_id

    result = conn.execute(
        text("""
            INSERT INTO branches
                (name, company, nmls_id, organization_id, created_at)
            VALUES
                (:name, :company, :nmls_id, :org_id, :now)
            RETURNING id
        """),
        {
            "name": "Charleston HQ",
            "company": ORG_NAME,
            "nmls_id": "789012",
            "org_id": org_id,
            "now": NOW,
        },
    )
    branch_id = result.fetchone()[0]
    conn.commit()
    print(f"✅ Created branch (id={branch_id})")
    return branch_id


