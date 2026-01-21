#!/usr/bin/env python3
"""
Migration Script: Move leads from 'leads' table to 'mum_clients' table.

This script moves leads that were accidentally imported as leads to the mum_clients table.

Usage:
    python migrate_leads_to_mum.py [--source "Auto Import"] [--delete] [--dry-run]

Options:
    --source    Filter leads by source (default: "Auto Import")
    --delete    Delete leads after migration (default: False)
    --dry-run   Preview what would be migrated without making changes
"""

import os
import sys
import argparse
from datetime import date, timedelta

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))
except ImportError:
    pass


def get_db_connection():
    """Get database connection from environment."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")

    # Check if SQLite or PostgreSQL
    if database_url.startswith("sqlite"):
        import sqlite3
        # Extract the path from sqlite:///./path
        db_path = database_url.replace("sqlite:///", "")
        if db_path.startswith("./"):
            db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), db_path[2:])
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn, "sqlite"
    else:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        return psycopg2.connect(database_url), "postgresql"


def migrate_leads_to_mum(source_filter: str = "Auto Import", delete_after: bool = False, dry_run: bool = False):
    """
    Migrate leads to MUM clients.

    Args:
        source_filter: Only migrate leads with this source
        delete_after: Delete leads after successful migration
        dry_run: Preview without making changes
    """
    conn, db_type = get_db_connection()
    cursor = conn.cursor()

    # For PostgreSQL, use RealDictCursor
    if db_type == "postgresql":
        from psycopg2.extras import RealDictCursor
        cursor = conn.cursor(cursor_factory=RealDictCursor)

    print(f"Connected to {db_type} database")

    try:
        # Get leads to migrate - use ? for SQLite, %s for PostgreSQL
        param_marker = "?" if db_type == "sqlite" else "%s"
        cursor.execute(f"""
            SELECT
                id, name, first_name, last_name, email, phone,
                loan_number, loan_amount, interest_rate,
                appraisal_value, property_value, closing_date,
                loan_type, ltv, owner_id, source, created_at
            FROM leads
            WHERE source = {param_marker}
            ORDER BY created_at DESC
        """, (source_filter,))

        rows = cursor.fetchall()

        # Convert to list of dicts for consistent access
        if db_type == "sqlite":
            leads = [dict(row) for row in rows]
        else:
            leads = rows

        if not leads:
            print(f"No leads found with source '{source_filter}'")
            return

        print(f"Found {len(leads)} leads with source '{source_filter}'")

        if dry_run:
            print("\n=== DRY RUN - No changes will be made ===\n")

        migrated = []
        errors = []
        lead_ids_to_delete = []

        for lead in leads:
            try:
                # Build client_name from available fields
                client_name = lead['name']
                if not client_name or client_name.strip() == '':
                    first = lead['first_name'] or ''
                    last = lead['last_name'] or ''
                    client_name = f"{first} {last}".strip()
                if not client_name:
                    client_name = f"Client (Lead #{lead['id']})"

                # Get user_id from lead's owner_id
                mum_user_id = lead['owner_id']

                # Get loan amount (default to 0 if not available)
                loan_amount = lead['loan_amount'] or 0

                # Get interest rate (default to 0 if not available)
                rate = lead['interest_rate'] or 0

                # Get property value - try appraisal first, then property_value
                prop_value = lead['appraisal_value'] or lead['property_value'] or 0

                # Get closing date (default to today if not available)
                closing = lead['closing_date']
                if closing is None:
                    closing = date.today()
                elif hasattr(closing, 'date'):
                    closing = closing.date()

                # First payment date is typically ~30 days after closing
                first_payment = closing + timedelta(days=30)

                if dry_run:
                    print(f"  Would migrate: Lead #{lead['id']} -> '{client_name}' ({lead['email']})")
                    migrated.append({
                        "lead_id": lead['id'],
                        "client_name": client_name,
                        "email": lead['email']
                    })
                    lead_ids_to_delete.append(lead['id'])
                else:
                    # Insert into mum_clients - different syntax for SQLite vs PostgreSQL
                    from datetime import datetime
                    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

                    if db_type == "sqlite":
                        cursor.execute("""
                            INSERT INTO mum_clients (
                                client_name, email, phone,
                                origination_loan_number,
                                original_loan_amount, current_loan_amount,
                                interest_rate,
                                appraisal_value_at_closing, current_property_value,
                                closing_date, first_payment_date,
                                loan_type, ltv,
                                user_id, status, is_active,
                                created_at, updated_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', 1, ?, ?)
                        """, (
                            client_name, lead['email'], lead['phone'],
                            lead['loan_number'],
                            loan_amount, loan_amount,
                            rate,
                            prop_value, prop_value,
                            str(closing), str(first_payment),
                            lead['loan_type'], lead['ltv'],
                            mum_user_id,
                            now, now
                        ))
                        new_mum_id = cursor.lastrowid
                    else:
                        cursor.execute("""
                            INSERT INTO mum_clients (
                                client_name, email, phone,
                                origination_loan_number,
                                original_loan_amount, current_loan_amount,
                                interest_rate,
                                appraisal_value_at_closing, current_property_value,
                                closing_date, first_payment_date,
                                loan_type, ltv,
                                user_id, status, is_active,
                                created_at, updated_at
                            ) VALUES (
                                %s, %s, %s,
                                %s,
                                %s, %s,
                                %s,
                                %s, %s,
                                %s, %s,
                                %s, %s,
                                %s, 'active', true,
                                NOW(), NOW()
                            )
                            RETURNING id
                        """, (
                            client_name, lead['email'], lead['phone'],
                            lead['loan_number'],
                            loan_amount, loan_amount,
                            rate,
                            prop_value, prop_value,
                            closing, first_payment,
                            lead['loan_type'], lead['ltv'],
                            mum_user_id
                        ))
                        result = cursor.fetchone()
                        new_mum_id = result['id'] if isinstance(result, dict) else result[0]

                    migrated.append({
                        "lead_id": lead['id'],
                        "mum_client_id": new_mum_id,
                        "client_name": client_name,
                        "email": lead['email']
                    })
                    lead_ids_to_delete.append(lead['id'])

                    print(f"  Migrated: Lead #{lead['id']} -> MUM Client #{new_mum_id} ({client_name})")

            except Exception as e:
                errors.append({
                    "lead_id": lead['id'],
                    "name": lead['name'],
                    "error": str(e)
                })
                print(f"  ERROR on Lead #{lead['id']}: {e}")

        # Delete migrated leads if requested
        deleted_count = 0
        if delete_after and lead_ids_to_delete and not dry_run:
            if db_type == "sqlite":
                # SQLite doesn't support ANY, use IN with placeholders
                placeholders = ','.join('?' * len(lead_ids_to_delete))
                cursor.execute(f"DELETE FROM leads WHERE id IN ({placeholders})", lead_ids_to_delete)
            else:
                cursor.execute("DELETE FROM leads WHERE id = ANY(%s)", (lead_ids_to_delete,))
            deleted_count = cursor.rowcount
            print(f"\nDeleted {deleted_count} leads from leads table")

        if not dry_run:
            conn.commit()
            print("\n=== Migration committed successfully ===")

        # Summary
        print(f"\n=== Summary ===")
        print(f"Source filter: {source_filter}")
        print(f"Total leads found: {len(leads)}")
        print(f"Successfully migrated: {len(migrated)}")
        if delete_after:
            print(f"Leads deleted: {deleted_count if not dry_run else len(lead_ids_to_delete)} (would be)")
        print(f"Errors: {len(errors)}")

        if errors:
            print(f"\n=== Errors ===")
            for err in errors[:10]:
                print(f"  Lead #{err['lead_id']} ({err['name']}): {err['error']}")

        return {
            "migrated_count": len(migrated),
            "error_count": len(errors),
            "deleted_count": deleted_count
        }

    except Exception as e:
        conn.rollback()
        print(f"Migration failed: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate leads to MUM clients")
    parser.add_argument("--source", default="Auto Import", help="Filter leads by source")
    parser.add_argument("--delete", action="store_true", help="Delete leads after migration")
    parser.add_argument("--dry-run", action="store_true", help="Preview without making changes")

    args = parser.parse_args()

    print(f"=== Lead to MUM Client Migration ===")
    print(f"Source filter: {args.source}")
    print(f"Delete after: {args.delete}")
    print(f"Dry run: {args.dry_run}")
    print()

    migrate_leads_to_mum(
        source_filter=args.source,
        delete_after=args.delete,
        dry_run=args.dry_run
    )
