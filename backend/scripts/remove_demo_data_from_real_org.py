#!/usr/bin/env python3
"""
Remove demo/sample data that leaked into a real user's organization.

Root cause: init_db.py's create_sample_data() created records without
organization_id, and fix_demo_user_ownership.py reassigned them to the
first org it found (the real user's org).

This script identifies demo data by known sample names/emails/loan_numbers
and removes them from any org that isn't the demo org.

Run:
  railway run python scripts/remove_demo_data_from_real_org.py          # dry run
  railway run python scripts/remove_demo_data_from_real_org.py --apply  # actually delete
"""

import os
import sys
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL environment variable is required")
    sys.exit(1)

DRY_RUN = "--apply" not in sys.argv

# Sample data from init_db.py create_sample_data()
SAMPLE_LEAD_EMAILS = [
    "john.smith@email.com",
    "sarah.j@email.com",
    "mike.w@email.com",
]

SAMPLE_LOAN_NUMBERS = [
    "L2024-001",
    "L2024-002",
]

SAMPLE_PARTNER_EMAILS = [
    "jane@premierrealty.com",
    "bob@customhomes.com",
]

SAMPLE_MUM_LOAN_NUMBERS = [
    "L2023-045",
]

# Sample data from seed-demo-data endpoint (public_routes.py)
# These use the summit-peak-demo-appstore org and should be self-contained,
# but check anyway.
SEED_DEMO_LEAD_EMAILS = [
    "m.thompson@email.com", "j.davis@email.com", "r.wilson@email.com",
    "e.martinez@email.com", "d.anderson@email.com", "l.taylor@email.com",
    "c.brown@email.com", "a.jackson@email.com", "d.white@email.com",
    "j.harris@email.com", "m.lewis@email.com", "a.clark@email.com",
    "r.walker@email.com", "n.robinson@email.com", "b.young@email.com",
    "s.king@email.com", "t.scott@email.com", "m.adams@email.com",
    "k.nelson@email.com", "r.carter@email.com",
]

SEED_DEMO_LOAN_PATTERN = "SP-2026-%"

# Previously seeded names (from cleanup_sample_data.py)
LEGACY_SAMPLE_NAMES = [
    "Jeffrey Kim", "Patricia Luna", "David Okafor",
    "Rachel Green", "William Chen", "Sandra Yee",
]

# Known demo org slugs — data in these orgs is intentional, skip it
DEMO_ORG_SLUGS = ["demo-mortgage", "summit-peak-demo-appstore"]


def main():
    if DRY_RUN:
        print("=== DRY RUN (pass --apply to actually delete) ===\n")
    else:
        print("=== APPLYING CHANGES ===\n")

    engine = create_engine(DATABASE_URL)

    with engine.connect() as conn:
        # Find demo org IDs to exclude
        demo_orgs = conn.execute(text(
            "SELECT id, slug, name FROM organizations WHERE slug = ANY(:slugs)"
        ), {"slugs": DEMO_ORG_SLUGS}).fetchall()

        demo_org_ids = [r[0] for r in demo_orgs]
        print(f"Demo orgs (will NOT touch): {[(r[1], r[0]) for r in demo_orgs]}")

        # Find the real user's org
        real_user = conn.execute(text(
            "SELECT id, email, organization_id FROM users WHERE email = 'tloss@cmgfi.com'"
        )).fetchone()

        if real_user:
            real_org_id = real_user[2]
            print(f"Real user: {real_user[1]} (ID: {real_user[0]}, org: {real_org_id})")
        else:
            print("Real user tloss@cmgfi.com not found — scanning all non-demo orgs")
            real_org_id = None

        # Build exclusion filter: only delete from non-demo orgs
        if demo_org_ids:
            org_filter = "AND organization_id NOT IN :demo_oids"
            org_filter_null = "AND (organization_id IS NULL OR organization_id NOT IN :demo_oids)"
            params_base = {"demo_oids": tuple(demo_org_ids)}
        else:
            org_filter = ""
            org_filter_null = ""
            params_base = {}

        total_deleted = 0

        # 1. Sample leads from init_db.py
        params = {**params_base, "emails": tuple(SAMPLE_LEAD_EMAILS)}
        count = conn.execute(text(f"""
            SELECT COUNT(*) FROM leads
            WHERE email IN :emails {org_filter_null}
        """), params).scalar()
        print(f"\nSample leads (init_db): {count} found")
        if count and not DRY_RUN:
            conn.execute(text(f"DELETE FROM leads WHERE email IN :emails {org_filter_null}"), params)
            total_deleted += count

        # 2. Sample loans from init_db.py
        params = {**params_base, "lns": tuple(SAMPLE_LOAN_NUMBERS)}
        count = conn.execute(text(f"""
            SELECT COUNT(*) FROM loans
            WHERE loan_number IN :lns {org_filter_null}
        """), params).scalar()
        print(f"Sample loans (init_db): {count} found")
        if count and not DRY_RUN:
            conn.execute(text(f"DELETE FROM loans WHERE loan_number IN :lns {org_filter_null}"), params)
            total_deleted += count

        # 3. Sample referral partners
        params = {**params_base, "emails": tuple(SAMPLE_PARTNER_EMAILS)}
        count = conn.execute(text(f"""
            SELECT COUNT(*) FROM referral_partners
            WHERE email IN :emails
        """), params).scalar()
        print(f"Sample referral partners: {count} found")
        if count and not DRY_RUN:
            conn.execute(text("DELETE FROM referral_partners WHERE email IN :emails"), params)
            total_deleted += count

        # 4. Sample MUM clients
        params = {**params_base, "lns": tuple(SAMPLE_MUM_LOAN_NUMBERS)}
        count = conn.execute(text(f"""
            SELECT COUNT(*) FROM mum_clients
            WHERE loan_number IN :lns {org_filter_null}
        """), params).scalar()
        print(f"Sample MUM clients: {count} found")
        if count and not DRY_RUN:
            conn.execute(text(f"DELETE FROM mum_clients WHERE loan_number IN :lns {org_filter_null}"), params)
            total_deleted += count

        # 5. Seed-demo leads that leaked (should be in summit-peak org)
        params = {**params_base, "emails": tuple(SEED_DEMO_LEAD_EMAILS)}
        count = conn.execute(text(f"""
            SELECT COUNT(*) FROM leads
            WHERE email IN :emails {org_filter_null}
        """), params).scalar()
        print(f"Seed-demo leads (leaked): {count} found")
        if count and not DRY_RUN:
            conn.execute(text(f"DELETE FROM leads WHERE email IN :emails {org_filter_null}"), params)
            total_deleted += count

        # 6. Seed-demo loans that leaked
        params = {**params_base, "pattern": SEED_DEMO_LOAN_PATTERN}
        count = conn.execute(text(f"""
            SELECT COUNT(*) FROM loans
            WHERE loan_number LIKE :pattern {org_filter_null}
        """), params).scalar()
        print(f"Seed-demo loans (leaked): {count} found")
        if count and not DRY_RUN:
            conn.execute(text(f"DELETE FROM loans WHERE loan_number LIKE :pattern {org_filter_null}"), params)
            total_deleted += count

        # 7. Legacy sample data (from older seeding)
        for name in LEGACY_SAMPLE_NAMES:
            first, last = name.split(" ", 1)
            params = {**params_base, "fn": first, "ln": last}
            count = conn.execute(text(f"""
                SELECT COUNT(*) FROM leads
                WHERE first_name = :fn AND last_name = :ln {org_filter_null}
            """), params).scalar()
            if count:
                print(f"Legacy lead '{name}': {count} found")
                if not DRY_RUN:
                    conn.execute(text(f"DELETE FROM leads WHERE first_name = :fn AND last_name = :ln {org_filter_null}"), params)
                    total_deleted += count

        # 8. Tasks referencing sample loans
        params = {**params_base, "pattern1": "%L2024-001%", "pattern2": "%L2024-002%"}
        count = conn.execute(text(f"""
            SELECT COUNT(*) FROM tasks
            WHERE (title LIKE :pattern1 OR title LIKE :pattern2) {org_filter_null}
        """), params).scalar()
        print(f"Sample tasks: {count} found")
        if count and not DRY_RUN:
            conn.execute(text(f"""
                DELETE FROM tasks
                WHERE (title LIKE :pattern1 OR title LIKE :pattern2) {org_filter_null}
            """), params)
            total_deleted += count

        if DRY_RUN:
            print(f"\n--- DRY RUN complete. No changes made. ---")
            print(f"Run with --apply to delete the records above.")
        else:
            conn.commit()
            print(f"\nDeleted {total_deleted} demo records from real org(s).")

        # Final: show what the real user's org looks like now
        if real_org_id:
            summary = conn.execute(text("""
                SELECT
                    (SELECT COUNT(*) FROM leads WHERE organization_id = :oid AND deleted_at IS NULL) as leads,
                    (SELECT COUNT(*) FROM loans WHERE organization_id = :oid AND deleted_at IS NULL) as loans,
                    (SELECT COUNT(*) FROM tasks WHERE organization_id = :oid) as tasks,
                    (SELECT COUNT(*) FROM mum_clients WHERE organization_id = :oid) as mum
            """), {"oid": real_org_id}).fetchone()
            print(f"\nReal org ({real_org_id}) remaining data:")
            print(f"  {summary[0]} leads, {summary[1]} loans, {summary[2]} tasks, {summary[3]} MUM clients")


if __name__ == "__main__":
    main()
