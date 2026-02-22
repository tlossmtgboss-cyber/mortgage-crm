"""
API endpoint to run migrations remotely
This allows running migrations on production via HTTP request
"""
from fastapi import APIRouter, HTTPException, Depends, Header
from typing import Any, Optional
import logging
import os

from database import SessionLocal
from sqlalchemy import text

router = APIRouter(prefix="/api/v1/migrations", tags=["migrations"])

logger = logging.getLogger(__name__)


async def verify_admin_access(
    x_admin_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None)
):
    """
    Verify admin access for migration endpoints.
    Requires either:
    1. X-Admin-Key header matching MIGRATION_ADMIN_KEY env var
    2. Valid admin user token (checks is_admin flag)
    """
    admin_key = os.getenv("MIGRATION_ADMIN_KEY")

    # Option 1: Check admin key header
    if admin_key and x_admin_key == admin_key:
        return True

    # Option 2: Check for authenticated admin user via JWT token
    if authorization and authorization.startswith("Bearer "):
        try:
            from jose import jwt, JWTError

            token = authorization.replace("Bearer ", "")
            secret_key = os.getenv("SECRET_KEY", "")

            try:
                payload = jwt.decode(token, secret_key, algorithms=["HS256"], options={"verify_aud": False})
                email = payload.get("sub")

                if email:
                    db = SessionLocal()
                    try:
                        # Check if user is admin
                        result = db.execute(text("""
                            SELECT u.id, u.is_admin, u.role
                            FROM users u
                            WHERE u.email = :email
                        """), {"email": email}).fetchone()

                        if result and (result[1] or result[2] in ('admin', 'site_admin')):
                            return True
                    finally:
                        db.close()
            except JWTError as e:
                logger.warning(f"JWT decode failed: {e}")

        except Exception as e:
            logger.warning(f"Admin auth check failed: {e}")

    raise HTTPException(
        status_code=403,
        detail="Admin access required. Provide X-Admin-Key header or authenticate as admin user."
    )


@router.get("/debug-auth")
async def debug_auth(
    authorization: Optional[str] = Header(None)
):
    """Debug endpoint to check auth token decoding"""
    from jose import jwt, JWTError

    if not authorization or not authorization.startswith("Bearer "):
        return {"error": "No Bearer token provided"}

    token = authorization.replace("Bearer ", "")
    secret_key = os.getenv("SECRET_KEY", "")

    try:
        payload = jwt.decode(token, secret_key, algorithms=["HS256"], options={"verify_aud": False})
        email = payload.get("sub")

        db = SessionLocal()
        try:
            result = db.execute(text("""
                SELECT u.id, u.email, u.is_admin, u.role
                FROM users u
                WHERE u.email = :email
            """), {"email": email}).fetchone()

            if result:
                return {
                    "token_valid": True,
                    "email": email,
                    "user_id": result[0],
                    "is_admin": result[2],
                    "role": result[3],
                    "would_allow": result[2] or result[3] in ('admin', 'site_admin')
                }
            return {"token_valid": True, "email": email, "user_found": False}
        finally:
            db.close()
    except JWTError as e:
        return {"token_valid": False, "error": "Internal server error"}


@router.post("/add-guideline-updates-tables")
async def run_guideline_updates_migration(
    admin: Any = Depends(verify_admin_access)
):
    """
    Run the guideline updates tables migration
    Creates guideline_updates and user_update_views tables
    """
    try:
        from migrations.add_guideline_updates_tables import run_migration

        logger.info("Starting guideline updates tables migration...")
        success = run_migration()

        if success:
            return {
                "status": "success",
                "message": "Guideline updates tables created successfully"
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Migration failed - check logs for details"
            )

    except Exception as e:
        logger.error(f"Migration error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/seed-guideline-updates")
async def seed_guideline_updates(
    admin: Any = Depends(verify_admin_access)
):
    """
    Seed sample guideline updates data
    """
    try:
        from seed_sample_guidelines import seed_sample_guidelines

        logger.info("Starting guideline updates seeding...")
        count = seed_sample_guidelines()

        return {
            "status": "success",
            "message": f"Seeded {count} guideline updates",
            "count": count
        }

    except Exception as e:
        logger.error(f"Seeding error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/update-guideline-urls")
async def update_guideline_urls(
    admin: Any = Depends(verify_admin_access)
):
    """
    Update guideline URLs with real, working links
    """
    try:
        from database import SessionLocal
        from guideline_updates_models import GuidelineUpdate

        db = SessionLocal()

        # Real, verified working URLs for each source
        url_updates = {
            # Fannie Mae - Real Selling Guide links
            'fannie_mae': [
                {
                    'title': 'Selling Guide Announcement SEL-2024-08',
                    'url': 'https://singlefamily.fanniemae.com/originating-underwriting',
                    'description': 'Fannie Mae originating and underwriting guidelines'
                },
                {
                    'title': 'Selling Guide Announcement SEL-2024-07',
                    'url': 'https://singlefamily.fanniemae.com/delivering-selling',
                    'description': 'Fannie Mae delivering and selling guidelines'
                }
            ],

            # Freddie Mac - Real Guide links
            'freddie_mac': [
                {
                    'title': 'Bulletin 2024-15: Updated DTI Requirements',
                    'url': 'https://sf.freddiemac.com/working-with-us',
                    'description': 'Freddie Mac seller/servicer guidelines and resources'
                },
                {
                    'title': 'Bulletin 2024-14: Appraisal Modernization',
                    'url': 'https://sf.freddiemac.com/tools-learning',
                    'description': 'Freddie Mac tools and learning resources'
                }
            ],

            # FHA - Real HUD links
            'fha': [
                {
                    'title': 'Mortgagee Letter 2024-11: Credit Score Requirements',
                    'url': 'https://www.hud.gov/program_offices/housing/sfh/ins',
                    'description': 'FHA mortgage insurance programs and requirements'
                },
                {
                    'title': 'Mortgagee Letter 2024-10: Property Flip Requirements',
                    'url': 'https://www.hud.gov/program_offices/administration/hudclips/letters/mortgagee',
                    'description': 'FHA mortgagee letters and policy updates'
                }
            ],

            # VA - Real VA.gov links
            'va': [
                {
                    'title': 'VA Circular 26-24-10: Residual Income Updates',
                    'url': 'https://www.benefits.va.gov/homeloans/purchaseco_loan_fee.asp',
                    'description': 'VA loan funding fees and residual income requirements'
                },
                {
                    'title': 'VA Circular 26-24-09: Energy Efficient Improvements',
                    'url': 'https://www.benefits.va.gov/homeloans/purchaseco_certificate.asp',
                    'description': 'VA certificate of eligibility and loan benefits'
                }
            ],

            # USDA - Real USDA.gov links
            'usda': [
                {
                    'title': 'USDA Rural Development Notice: Area Eligibility Changes',
                    'url': 'https://eligibility.sc.egov.usda.gov/eligibility/welcomeAction.do',
                    'description': 'USDA property eligibility lookup and rural area determination'
                },
                {
                    'title': 'USDA Rural Development Notice: Income Limits Update',
                    'url': 'https://www.rd.usda.gov/programs-services/single-family-housing-programs/single-family-housing-guaranteed-loan-program/single-family-housing-income-limits',
                    'description': 'USDA income limits for guaranteed loan program'
                }
            ]
        }

        updated_count = 0
        updates_log = []

        for source, updates in url_updates.items():
            for update_info in updates:
                # Find the guideline update by title
                guideline = db.query(GuidelineUpdate).filter(
                    GuidelineUpdate.source == source,
                    GuidelineUpdate.title == update_info['title']
                ).first()

                if guideline:
                    # Update URL and description
                    guideline.url = update_info['url']
                    guideline.description = update_info['description']
                    updated_count += 1
                    updates_log.append(f"Updated: {source} - {update_info['title'][:50]}")
                    logger.info(f"Updated: {source} - {update_info['title'][:50]}")
                else:
                    updates_log.append(f"Not found: {source} - {update_info['title'][:50]}")
                    logger.warning(f"Not found: {source} - {update_info['title'][:50]}")

        db.commit()
        db.close()

        return {
            "status": "success",
            "message": f"Updated {updated_count} URLs with real, working links",
            "count": updated_count,
            "updates": updates_log
        }

    except Exception as e:
        logger.error(f"URL update error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/scrape-mortgage-guidelines")
async def scrape_mortgage_guidelines(
    admin: Any = Depends(verify_admin_access)
):
    """
    Scrape real guideline updates from my.mortgageguidelines.com
    Logs in with credentials and retrieves latest updates from all 5 sources
    """
    try:
        from mortgage_guidelines_scraper import run_scraper

        logger.info("Starting mortgage guidelines scraper...")
        count = run_scraper(limit_per_source=5)

        return {
            "status": "success",
            "message": f"Successfully scraped and added {count} new guideline updates",
            "count": count,
            "sources": ["fannie_mae", "freddie_mac", "fha", "va", "usda"]
        }

    except Exception as e:
        logger.error(f"Scraper error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/clear-guidelines")
async def clear_guideline_updates(
    admin: Any = Depends(verify_admin_access)
):
    """
    Clear all guideline updates and user views from database
    Use this before running the scraper to get fresh data
    """
    try:
        from database import SessionLocal
        from guideline_updates_models import GuidelineUpdate, UserUpdateView

        db = SessionLocal()

        # Delete user views first (foreign key)
        view_count = db.query(UserUpdateView).delete()
        logger.info(f"Deleted {view_count} user views")

        # Delete all updates
        update_count = db.query(GuidelineUpdate).delete()
        logger.info(f"Deleted {update_count} guideline updates")

        db.commit()
        db.close()

        return {
            "status": "success",
            "message": f"Cleared {update_count} guideline updates and {view_count} user views",
            "updates_deleted": update_count,
            "views_deleted": view_count
        }

    except Exception as e:
        logger.error(f"Clear error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/import-browser-guidelines")
async def import_browser_guidelines(
    request: dict,
    admin: Any = Depends(verify_admin_access)
):
    """
    Import guideline updates scraped by browser extension
    Receives data from the Chrome/Firefox extension while user is logged into mortgageguidelines.com
    """
    try:
        from database import SessionLocal
        from guideline_updates_models import GuidelineUpdate
        from datetime import datetime, timedelta
        import hashlib
        import re

        guidelines = request.get('guidelines', [])

        if not guidelines:
            return {
                "status": "error",
                "message": "No guidelines provided"
            }

        db = SessionLocal()
        added_count = 0
        skipped_count = 0

        for guideline_data in guidelines:
            try:
                # Parse date
                date_str = guideline_data.get('date_str', '')
                published_date = datetime.utcnow()

                if date_str:
                    # Try to parse various date formats
                    for fmt in ['%B %d, %Y', '%b %d, %Y', '%m/%d/%Y', '%Y-%m-%d']:
                        try:
                            published_date = datetime.strptime(date_str, fmt)
                            break
                        except Exception as e:
                            logger.exception(f"Failed to parse date string '{date_str}' with format '{fmt}': {e}")
                            continue

                # Generate hash
                content_hash = hashlib.sha256(
                    f"{guideline_data['title']}{guideline_data['url']}".encode()
                ).hexdigest()

                # Check if exists
                existing = db.query(GuidelineUpdate).filter_by(
                    content_hash=content_hash
                ).first()

                if existing:
                    skipped_count += 1
                    continue

                # Create new guideline update
                new_guideline = GuidelineUpdate(
                    source=guideline_data['source'],
                    title=guideline_data['title'],
                    section_code=guideline_data.get('section_code'),
                    description=guideline_data.get('description', guideline_data['title']),
                    url=guideline_data['url'],
                    published_date=published_date,
                    scraped_date=datetime.utcnow(),
                    is_new=True,
                    content_hash=content_hash
                )

                db.add(new_guideline)
                db.commit()
                added_count += 1

                logger.info(f"Added guideline: {guideline_data['title'][:50]}...")

            except Exception as e:
                db.rollback()
                logger.error(f"Error adding guideline: {e}")
                continue

        db.close()

        return {
            "status": "success",
            "message": f"Imported {added_count} new guidelines, skipped {skipped_count} duplicates",
            "added": added_count,
            "skipped": skipped_count,
            "total_received": len(guidelines)
        }

    except Exception as e:
        logger.error(f"Import error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/add-circle-of-cashflow-tables")
async def run_circle_of_cashflow_migration(
    admin: Any = Depends(verify_admin_access)
):
    """
    Run the Circle of Cashflow tables migration
    Creates mortgage_questionnaires, referral_partners, referral_opportunities,
    referrals, and partner_touchpoints tables
    """
    try:
        from migrations.add_circle_of_cashflow import run_migration

        logger.info("Starting Circle of Cashflow tables migration...")
        run_migration()

        return {
            "status": "success",
            "message": "Circle of Cashflow tables created successfully"
        }

    except Exception as e:
        logger.error(f"Migration error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/add-circle-contacts-table")
async def run_circle_contacts_migration(
    admin: Any = Depends(verify_admin_access)
):
    """
    Run the Circle Contacts table migration
    Creates circle_contacts table for storing borrower's trusted professionals
    """
    try:
        from migrations.add_circle_contacts_table import run_migration

        logger.info("Starting Circle Contacts table migration...")
        run_migration()

        return {
            "status": "success",
            "message": "Circle contacts table created successfully"
        }

    except Exception as e:
        logger.error(f"Migration error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/add-ai-task-automation-tables")
async def run_ai_task_automation_migration(
    admin: Any = Depends(verify_admin_access)
):
    """
    Run the AI Task Automation tables migration
    Creates ai_task_type_authorizations, ai_training_history, ai_audit_log,
    ai_cost_tracking, ai_rollback_states tables and modifies tasks table
    """
    try:
        from migrations.add_ai_task_automation_tables import run_migration

        logger.info("Starting AI Task Automation tables migration...")
        success = run_migration()

        if success:
            return {
                "status": "success",
                "message": "AI Task Automation tables created successfully",
                "tables_created": [
                    "ai_task_type_authorizations",
                    "ai_training_history",
                    "ai_audit_log",
                    "ai_cost_tracking",
                    "ai_rollback_states"
                ]
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Migration failed - check logs for details"
            )

    except Exception as e:
        logger.error(f"Migration error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/create-mortgage-glossary")
async def run_mortgage_glossary_migration(
    admin: Any = Depends(verify_admin_access)
):
    """
    Run the mortgage glossary migration
    Creates mortgage_glossary table with ~442 mortgage terminology terms
    for AI Orchestrator knowledge base
    """
    try:
        from migrations.create_mortgage_glossary import run_migration
        from database import SessionLocal

        logger.info("Starting mortgage glossary migration...")
        db = SessionLocal()
        success = run_migration(db)
        db.close()

        if success:
            return {
                "status": "success",
                "message": "Mortgage glossary table created with ~442 terms",
                "categories": [
                    "Origination", "Underwriting", "Credit", "Collateral",
                    "Compliance", "Processing", "Closing", "Servicing",
                    "Secondary Market", "Operations", "Marketing"
                ]
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Migration failed - check logs for details"
            )

    except Exception as e:
        logger.error(f"Migration error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/add-concierge-responsible-column")
async def add_concierge_responsible_column(
    admin: Any = Depends(verify_admin_access)
):
    """
    Add concierge_responsible column to workflow_day_configs table
    """
    try:
        from database import engine
        from sqlalchemy import text

        logger.info("Adding concierge_responsible column to workflow_day_configs...")

        with engine.connect() as conn:
            # Check if column already exists
            try:
                conn.execute(text("SELECT concierge_responsible FROM workflow_day_configs LIMIT 1"))
                return {
                    "status": "success",
                    "message": "Column concierge_responsible already exists"
                }
            except Exception as e:
                logger.exception(f"Column concierge_responsible check failed (proceeding to add): {e}")

            # Add the column
            conn.execute(text("""
                ALTER TABLE workflow_day_configs
                ADD COLUMN concierge_responsible BOOLEAN DEFAULT FALSE
            """))
            conn.commit()
            logger.info("Added concierge_responsible column successfully")

        return {
            "status": "success",
            "message": "Added concierge_responsible column to workflow_day_configs table"
        }

    except Exception as e:
        logger.error(f"Migration error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/update-user-email")
async def update_user_email(
    admin: Any = Depends(verify_admin_access)
):
    """
    Update demo user email from admin@perenniaai.com to admin@perenniaai.com
    """
    try:
        from database import engine
        from sqlalchemy import text

        old_email = "admin@perenniaai.com"
        new_email = "admin@perenniaai.com"

        logger.info(f"Updating user email from {old_email} to {new_email}...")

        with engine.connect() as conn:
            # Check if old user exists
            result = conn.execute(text("SELECT id, email FROM users WHERE email = :email"), {"email": old_email})
            user = result.fetchone()

            if not user:
                # Check if already updated
                result = conn.execute(text("SELECT id, email FROM users WHERE email = :email"), {"email": new_email})
                existing = result.fetchone()
                if existing:
                    return {
                        "status": "success",
                        "message": f"User already updated to {new_email}"
                    }
                raise HTTPException(status_code=404, detail=f"User with email {old_email} not found")

            # Update the email
            conn.execute(text("""
                UPDATE users SET email = :new_email WHERE email = :old_email
            """), {"old_email": old_email, "new_email": new_email})
            conn.commit()

            logger.info(f"Successfully updated user email to {new_email}")

        return {
            "status": "success",
            "message": f"User email updated from {old_email} to {new_email}",
            "new_credentials": {
                "email": new_email,
                "password": "demo123 (unchanged)"
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Migration error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/add-weekly-task-columns")
async def run_weekly_task_columns_migration(
    admin: Any = Depends(verify_admin_access)
):
    """
    Add weekly task scheduling columns to workflow_day_configs table.

    Adds columns for:
    - repeat_weekly: Boolean flag to mark tasks as weekly recurring
    - repeat_day_of_week: Integer (0=Monday, 6=Sunday) for which day to send
    - repeat_until_status: JSON array of statuses that stop the recurrence

    Business Rules:
    - Monday Weekly Update: First update goes out on the Monday FOLLOWING the
      Disclosed date entry (not same day if added on Monday)
    - Tasks repeat until loan is closed, canceled, withdrawn, or denied
    """
    try:
        from database import SessionLocal
        from migrations.add_weekly_task_columns import run_migration, update_existing_monday_tasks

        logger.info("Starting weekly task columns migration...")
        db = SessionLocal()

        # Run the column migration
        migration_results = run_migration(db)

        # Update existing Monday tasks if columns were added
        update_results = {}
        if migration_results.get('success'):
            update_results = update_existing_monday_tasks(db)

        db.close()

        if migration_results.get('success'):
            return {
                "status": "success",
                "message": "Weekly task columns migration completed",
                "columns_added": migration_results.get('columns_added', []),
                "existing_tasks_updated": update_results.get('tasks_updated', 0),
                "errors": migration_results.get('errors', []) + update_results.get('errors', [])
            }
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Migration failed: {migration_results.get('errors', ['Unknown error'])}"
            )

    except Exception as e:
        logger.error(f"Migration error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/add-email-response-training-tables")
async def run_email_response_training_migration(
    admin: Any = Depends(verify_admin_access)
):
    """
    Run the Email Response Training tables migration.

    Creates tables for AI email response learning:
    - email_response_patterns - Stores learned behaviors with confidence tracking
    - email_response_log - Tracks all email response actions
    - email_response_queue - Pending responses awaiting user review
    - Views for analytics and effectiveness tracking
    - Trigger for automatic confidence score calculation

    This enables the AI to learn from user approvals/rejections and
    auto-execute email responses when confidence reaches 95%.
    """
    try:
        from migrations.add_email_response_training_tables import run_migration

        logger.info("Starting Email Response Training tables migration...")
        success = run_migration()

        if success:
            return {
                "status": "success",
                "message": "Email Response Training tables created successfully",
                "tables_created": [
                    "email_response_patterns",
                    "email_response_log",
                    "email_response_queue"
                ],
                "views_created": [
                    "email_pattern_effectiveness",
                    "user_email_response_stats",
                    "pending_email_responses"
                ],
                "auto_execute_threshold": "95% confidence required"
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Migration failed - check logs for details"
            )

    except Exception as e:
        logger.error(f"Migration error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/rename-theme")
async def rename_microsite_theme(
    admin: Any = Depends(verify_admin_access)
):
    """
    Rename 'LeadPops Cardinal' theme to 'Bold Impact'
    Updates both slug and name in the database
    """
    try:
        from database import engine
        from sqlalchemy import text

        logger.info("Renaming theme from 'LeadPops Cardinal' to 'Bold Impact'...")

        with engine.connect() as conn:
            # Update the theme
            result = conn.execute(text("""
                UPDATE microsite_themes
                SET slug = 'bold-impact',
                    name = 'Bold Impact',
                    description = 'A bold, modern theme with strong call-to-actions and lead capture focus.'
                WHERE slug = 'leadpops-cardinal'
                RETURNING id, slug, name
            """))

            updated = result.fetchone()
            conn.commit()

            if updated:
                logger.info(f"Theme renamed: {updated}")
                return {
                    "status": "success",
                    "message": "Theme renamed from 'LeadPops Cardinal' to 'Bold Impact'",
                    "theme": {
                        "id": updated[0],
                        "slug": updated[1],
                        "name": updated[2]
                    }
                }
            else:
                # Check if already renamed
                result = conn.execute(text("""
                    SELECT id, slug, name FROM microsite_themes WHERE slug = 'bold-impact'
                """))
                existing = result.fetchone()

                if existing:
                    return {
                        "status": "success",
                        "message": "Theme is already named 'Bold Impact'",
                        "theme": {
                            "id": existing[0],
                            "slug": existing[1],
                            "name": existing[2]
                        }
                    }
                else:
                    return {
                        "status": "warning",
                        "message": "Theme 'leadpops-cardinal' not found in database"
                    }

    except Exception as e:
        logger.error(f"Theme rename error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/add-microsite-themes")
async def run_microsite_themes_migration(
    admin: Any = Depends(verify_admin_access)
):
    """
    Run the Microsite Themes migration.

    Creates tables and seeds default themes for the microsite theme marketplace:
    - microsite_themes - Registry of available themes
    - microsites - User microsite configuration
    - microsite_profiles - Extended profile data for microsites

    Seeds 4 default themes:
    - LeadPops Cardinal (bold)
    - Professional Clean (professional)
    - Modern Gradient (modern)
    - Minimal Focus (minimal)
    """
    try:
        import os
        from pathlib import Path
        from database import engine
        from sqlalchemy import text

        logger.info("Starting Microsite Themes migration...")

        # Read the migration file
        migration_path = Path(__file__).parent / "migrations" / "add_microsite_themes.sql"
        if not migration_path.exists():
            raise HTTPException(
                status_code=500,
                detail=f"Migration file not found at {migration_path}"
            )

        sql = migration_path.read_text()

        # Execute the migration
        with engine.connect() as conn:
            conn.execute(text(sql))
            conn.commit()

            # Verify tables were created
            result = conn.execute(text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name IN ('microsite_themes', 'microsites', 'microsite_profiles')
                ORDER BY table_name
            """))
            tables = [row[0] for row in result.fetchall()]

            # Count themes
            result = conn.execute(text("SELECT COUNT(*) FROM microsite_themes"))
            theme_count = result.fetchone()[0]

        logger.info(f"Migration completed. Tables: {tables}, Themes: {theme_count}")

        return {
            "status": "success",
            "message": "Microsite Themes tables created and seeded successfully",
            "tables_created": tables,
            "themes_seeded": theme_count,
            "default_themes": [
                "leadpops-cardinal",
                "professional-clean",
                "modern-gradient",
                "minimal-focus"
            ]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Migration error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/fix-referral-partner-links")
async def fix_referral_partner_links(
    admin: Any = Depends(verify_admin_access)
):
    """
    Fix referral partner links for existing leads and loans.
    Links leads/loans to their correct referral partners based on application declarations.
    Specifically fixes Steve Latterson -> Timothy Loss (partner ID 22) link.
    """
    try:
        from migrations.fix_referral_partner_links import run_migration

        logger.info("Starting referral partner link fix migration...")
        result = run_migration()

        return {
            "status": "success",
            "message": f"Fixed {result['updated_leads']} leads and {result['updated_loans']} loans",
            **result
        }

    except Exception as e:
        logger.error(f"Migration error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/add-income-intelligence-engine")
async def run_income_intelligence_engine_migration(
    admin: Any = Depends(verify_admin_access)
):
    """
    Run the Income Intelligence Engine tables migration.

    Creates tables for automated income calculation:
    - income_summaries: Single source of truth for calculated qualifying income
    - income_calculation_details: Detailed breakdown per income stream (audit trail)
    - income_flags: Conditions, warnings, and required actions
    - mileage_depreciation_rates: IRS mileage rate configuration
    - income_worksheets: Generated Excel worksheet tracking

    Also seeds mileage depreciation rates for 2021-2024.
    """
    try:
        from migrations.add_income_intelligence_engine import run_migration

        logger.info("Starting Income Intelligence Engine tables migration...")
        run_migration()

        return {
            "status": "success",
            "message": "Income Intelligence Engine tables created successfully",
            "tables_created": [
                "income_summaries",
                "income_calculation_details",
                "income_flags",
                "mileage_depreciation_rates",
                "income_worksheets"
            ],
            "mileage_rates_seeded": {
                "2021": "$0.26/mile",
                "2022": "$0.26/mile",
                "2023": "$0.28/mile",
                "2024": "$0.30/mile"
            }
        }

    except Exception as e:
        logger.error(f"Income Intelligence Engine migration error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/seed-ci-qa-rubrics")
async def seed_ci_qa_rubrics(
    admin: Any = Depends(verify_admin_access)
):
    """
    Seed QA rubrics and compliance rules for Conversation Intelligence platform
    """
    try:
        from database import SessionLocal
        from sqlalchemy import text
        from pathlib import Path

        logger.info("Starting CI QA rubrics seeding...")

        db = SessionLocal()

        # Read and execute the seed file
        seed_file = Path(__file__).parent / "migrations" / "seed_mortgage_qa_rubrics.sql"

        if not seed_file.exists():
            raise HTTPException(status_code=404, detail="Seed file not found")

        with open(seed_file, 'r') as f:
            seed_sql = f.read()

        # Split by INSERT statements and execute each
        statements = seed_sql.split('INSERT INTO')
        success_count = 0
        errors = []

        for i, stmt in enumerate(statements[1:], 1):  # Skip first empty split
            try:
                full_stmt = 'INSERT INTO' + stmt.rstrip().rstrip(';')
                db.execute(text(full_stmt))
                success_count += 1
                logger.info(f"Seed statement {i}: OK")
            except Exception as e:
                error_msg = str(e)[:100]
                errors.append(f"Statement {i}: {error_msg}")
                logger.warning(f"Seed statement {i}: {error_msg}")

        db.commit()

        # Get counts
        rubric_count = db.execute(text("SELECT COUNT(*) FROM ci_qa_rubrics")).scalar()
        rule_count = db.execute(text("SELECT COUNT(*) FROM ci_compliance_rules")).scalar()

        db.close()

        return {
            "status": "success",
            "message": f"Seeded {success_count} statements",
            "qa_rubrics_count": rubric_count,
            "compliance_rules_count": rule_count,
            "errors": errors if errors else None
        }

    except Exception as e:
        logger.error(f"CI QA rubrics seeding error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/add-video-os-tables")
async def run_video_os_migration(
    admin: Any = Depends(verify_admin_access)
):
    """
    Run the Video OS tables migration.
    Creates tables for video projects, render jobs, hosting, and analytics.
    """
    try:
        from migrations.add_video_os_tables import run_migration

        logger.info("Starting Video OS tables migration...")
        result = run_migration()

        if result.get("success"):
            return {
                "status": "success",
                "message": "Video OS tables created successfully"
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Migration failed - check logs for details"
            )

    except Exception as e:
        logger.error(f"Video OS migration error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/add-avatar-tables")
async def run_avatar_migration(
    admin: Any = Depends(verify_admin_access)
):
    """Run the AI Avatar tables migration."""
    try:
        from migrations.add_avatar_tables import run_migration

        logger.info("Starting Avatar tables migration...")
        result = run_migration()

        if result.get("success"):
            return {
                "status": "success",
                "message": "Avatar tables created successfully"
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Migration failed - check logs for details"
            )

    except Exception as e:
        logger.error(f"Avatar migration error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/run-partner-recruiting-migration")
async def run_partner_recruiting_migration(
    admin: Any = Depends(verify_admin_access)
):
    """Run the Partner Recruiting tables migration."""
    try:
        from migrations.add_partner_recruiting_tables import run_migration

        logger.info("Starting Partner Recruiting tables migration...")
        result = run_migration()

        return {
            "status": "success",
            "message": "Partner Recruiting tables created successfully",
            "result": result
        }

    except Exception as e:
        logger.error(f"Partner Recruiting migration error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/add-call-transcripts-table")
async def run_call_transcripts_migration(
    admin: Any = Depends(verify_admin_access)
):
    """
    Run the Call Transcripts table migration for Voice Intelligence.

    Creates the call_transcripts table to store AI-transcribed call recordings with:
    - Speaker-labeled transcript sentences
    - Sentiment analysis
    - Topic detection
    - Action items extraction
    - Entity recognition
    - AI-generated call summaries
    - PII redaction tracking
    """
    try:
        from pathlib import Path
        from database import engine
        from sqlalchemy import text

        logger.info("Starting Call Transcripts table migration...")

        # Read the migration file
        migration_path = Path(__file__).parent / "migrations" / "add_call_transcripts_table.sql"
        if not migration_path.exists():
            raise HTTPException(
                status_code=500,
                detail=f"Migration file not found at {migration_path}"
            )

        sql = migration_path.read_text()

        # Execute the migration
        with engine.connect() as conn:
            # Remove comment lines first, then split by semicolons
            lines = [line for line in sql.split('\n') if not line.strip().startswith('--')]
            clean_sql = '\n'.join(lines)
            statements = [s.strip() for s in clean_sql.split(';') if s.strip()]
            executed = 0
            skipped = 0

            for statement in statements:
                if not statement:
                    continue
                try:
                    conn.execute(text(statement))
                    executed += 1
                    logger.info(f"Executed: {statement[:60]}...")
                except Exception as e:
                    if "already exists" in str(e).lower():
                        skipped += 1
                        logger.info(f"Skipped (already exists): {statement[:60]}...")
                    else:
                        raise

            conn.commit()

            # Verify table was created
            result = conn.execute(text("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'call_transcripts'
                ORDER BY ordinal_position
            """))
            columns = [{"name": row[0], "type": row[1]} for row in result.fetchall()]

        logger.info(f"Migration completed. Executed: {executed}, Skipped: {skipped}")

        return {
            "status": "success",
            "message": "Call Transcripts table created successfully",
            "statements_executed": executed,
            "statements_skipped": skipped,
            "table_columns": len(columns),
            "features": [
                "transcript_sid - Unique transcript identifier",
                "sentences - JSONB array of speaker-labeled sentences",
                "sentiment - Overall call sentiment analysis",
                "topics - Detected discussion topics",
                "action_items - Extracted action items",
                "entities - Named entities (names, amounts, dates)",
                "summary - AI-generated call summary",
                "pii_detected - PII redaction flag"
            ]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Call Transcripts migration error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/add-sessions-table")
async def run_sessions_table_migration(
    admin: Any = Depends(verify_admin_access)
):
    """
    Run the sessions table migration
    Creates sessions table for storing user authentication tokens
    """
    try:
        from migrations.add_sessions_table import run_migration

        logger.info("Starting sessions table migration...")
        success = run_migration()

        if success:
            return {
                "status": "success",
                "message": "Sessions table created successfully"
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Migration failed - check logs for details"
            )

    except Exception as e:
        logger.error(f"Sessions table migration error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/add-voice-os-tables")
async def run_voice_os_migration(
    admin: Any = Depends(verify_admin_access)
):
    """
    Run the Voice OS tables migration.

    Creates tables for the Voice OS real-time voice AI system:
    - voice_os_agents: AI voice agent configurations
    - voice_os_phone_numbers: Telnyx phone number to agent mappings
    - voice_os_call_sessions: Call records with transcripts and analytics
    - voice_os_agent_performance: Real-time agent metrics view

    Also creates triggers for auto-updating agent stats and seeds
    the default "Sam - AI Receptionist" agent.
    """
    try:
        from migrations.add_voice_os_tables import run_migration

        logger.info("Starting Voice OS tables migration...")
        success = run_migration()

        if success:
            return {
                "status": "success",
                "message": "Voice OS tables created successfully",
                "tables_created": [
                    "voice_os_agents",
                    "voice_os_phone_numbers",
                    "voice_os_call_sessions"
                ],
                "views_created": [
                    "voice_os_agent_performance"
                ],
                "triggers_created": [
                    "trigger_update_voice_os_agent_stats"
                ],
                "default_agent": "Sam - AI Receptionist"
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Migration failed - check logs for details"
            )

    except Exception as e:
        logger.error(f"Voice OS migration error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/add-voice-workflow-tables")
async def run_voice_workflow_migration(
    admin: Any = Depends(verify_admin_access)
):
    """
    Run the Voice Workflow Sessions table migration.

    Creates the voice_workflow_sessions table for conversational AI workflows:
    - Stores workflow state machine state
    - Tracks collected slot data during conversation
    - Records conversation history for context
    - Stores execution results upon completion

    Enables voice-driven task completion like "Send a pre-approval letter to a realtor"
    with multi-turn conversational slot filling.
    """
    try:
        from pathlib import Path
        from database import engine
        from sqlalchemy import text

        logger.info("Starting Voice Workflow Sessions table migration...")

        # Read the migration file
        migration_path = Path(__file__).parent / "migrations" / "add_voice_workflow_tables.sql"
        if not migration_path.exists():
            raise HTTPException(
                status_code=500,
                detail=f"Migration file not found at {migration_path}"
            )

        sql = migration_path.read_text()

        # Execute the migration
        with engine.connect() as conn:
            # Remove comment lines first, then split by semicolons
            lines = [line for line in sql.split('\n') if not line.strip().startswith('--')]
            clean_sql = '\n'.join(lines)
            statements = [s.strip() for s in clean_sql.split(';') if s.strip()]
            executed = 0
            skipped = 0

            for statement in statements:
                if not statement:
                    continue
                try:
                    conn.execute(text(statement))
                    executed += 1
                    logger.info(f"Executed: {statement[:60]}...")
                except Exception as e:
                    if "already exists" in str(e).lower():
                        skipped += 1
                        logger.info(f"Skipped (already exists): {statement[:60]}...")
                    else:
                        raise

            conn.commit()

            # Verify table was created
            result = conn.execute(text("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'voice_workflow_sessions'
                ORDER BY ordinal_position
            """))
            columns = [{"name": row[0], "type": row[1]} for row in result.fetchall()]

        logger.info(f"Voice Workflow migration completed. Executed: {executed}, Skipped: {skipped}")

        return {
            "status": "success",
            "message": "Voice Workflow Sessions table created successfully",
            "statements_executed": executed,
            "statements_skipped": skipped,
            "table_columns": len(columns),
            "supported_workflows": [
                "pre_approval_letter - Send pre-approval letters to realtors",
                "schedule_appointment - Schedule meetings with contacts",
                "create_task - Create tasks and reminders",
                "send_email - Send emails to borrowers/realtors",
                "update_loan_status - Update loan pipeline status"
            ]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Voice Workflow migration error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/add-call-screening-tables")
async def run_call_screening_migration(
    admin: Any = Depends(verify_admin_access)
):
    """
    Run the call screening tables migration.
    Creates phone_blocklist, phone_whitelist, call_screening_log, phone_lookup_cache tables.
    """
    try:
        from migrations.add_call_screening_tables import run_migration

        logger.info("Starting call screening tables migration...")
        run_migration()

        return {
            "status": "success",
            "message": "Call screening tables created successfully",
            "tables_created": [
                "phone_blocklist",
                "phone_whitelist",
                "call_screening_log",
                "phone_lookup_cache"
            ]
        }

    except Exception as e:
        logger.error(f"Call screening migration error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/add-multi-role-system")
async def run_multi_role_migration(
    admin: Any = Depends(verify_admin_access)
):
    """
    Run the multi-role system migration
    Creates user_assigned_roles and user_active_role tables
    for supporting users with multiple roles and role switching
    """
    try:
        from migrations.add_multi_role_system import run_migration

        logger.info("Starting multi-role system migration...")
        success = run_migration()

        if success:
            return {
                "status": "success",
                "message": "Multi-role system tables created successfully",
                "tables_created": [
                    "user_assigned_roles",
                    "user_active_role"
                ]
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Migration failed - check logs for details"
            )

    except Exception as e:
        logger.error(f"Multi-role system migration error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/multi-role-system/status")
async def check_multi_role_migration_status(
    admin: Any = Depends(verify_admin_access)
):
    """
    Check if the multi-role system migration has been applied
    """
    try:
        from migrations.add_multi_role_system import check_migration_status

        status = check_migration_status()
        return status

    except Exception as e:
        logger.error(f"Multi-role status check error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/backfill-sla-tasks")
async def backfill_sla_tasks_endpoint(
    limit: int = 100,
    admin: Any = Depends(verify_admin_access)
):
    """
    Backfill SLA tasks for existing loans that don't have them.

    This endpoint creates SLA tasks for loans that:
    - Have an application_date set
    - Are not in final stages (FUNDED, CANCELLED, DENIED, WITHDRAWN)
    - Don't already have SLA tasks

    Args:
        limit: Maximum number of loans to process (default 100)

    Returns:
        Dict with backfill results including tasks created
    """
    try:
        from services.sla_task_hook_service import backfill_sla_tasks_batch

        logger.info(f"Starting SLA task backfill (limit={limit})...")

        # Run the backfill
        result = await backfill_sla_tasks_batch(limit=limit)

        logger.info(f"SLA task backfill completed: {result}")

        return {
            "status": "success",
            "message": f"Processed {result.get('loans_processed', 0)} loans",
            "loans_processed": result.get("loans_processed", 0),
            "tasks_created": result.get("tasks_created", 0),
            "errors": result.get("errors", []) if result.get("errors") else None
        }

    except Exception as e:
        logger.error(f"SLA task backfill error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/add-sla-milestone-type-columns")
async def run_sla_milestone_type_migration(
    admin: Any = Depends(verify_admin_access)
):
    """
    Add SLA milestone tracking columns to the tasks table.

    Adds columns for:
    - sla_milestone_id: References the SLA milestone definition
    - sla_milestone_type: Type identifier (disclosure, appraisal, closing, etc.)
    - sla_date_field: Which date field triggers the SLA
    - milestone_date: The actual date/deadline for this milestone
    - sla_days_allowed: Number of days allowed to complete this SLA
    - sla_status: Tracking SLA compliance (on_track, at_risk, overdue, completed)

    Also creates performance indexes for SLA queries.
    """
    try:
        from pathlib import Path
        from database import engine
        from sqlalchemy import text

        logger.info("Starting SLA milestone type columns migration...")

        # Read the migration file
        migration_path = Path(__file__).parent / "migrations" / "add_sla_milestone_type_column.sql"
        if not migration_path.exists():
            raise HTTPException(
                status_code=500,
                detail=f"Migration file not found at {migration_path}"
            )

        sql = migration_path.read_text()

        # Execute the migration
        with engine.connect() as conn:
            # For DO $$ blocks, we need to execute the whole thing
            # Split carefully - execute DO blocks as single statements
            executed = 0
            skipped = 0
            errors = []

            # Split by "DO $$" to handle PL/pgSQL blocks
            parts = sql.split('DO $$')

            for i, part in enumerate(parts):
                if i == 0:
                    # First part is comments/header - skip if empty
                    clean_part = part.strip()
                    if not clean_part or clean_part.startswith('--'):
                        continue
                else:
                    # This is a DO block - reconstruct it
                    # Find where the DO block ends (at "END $$;")
                    if 'END $$;' in part:
                        do_block_end = part.index('END $$;') + len('END $$;')
                        do_block = 'DO $$' + part[:do_block_end]
                        remainder = part[do_block_end:]

                        # Execute the DO block
                        try:
                            conn.execute(text(do_block))
                            executed += 1
                            logger.info(f"Executed DO block {i}")
                        except Exception as e:
                            if "already exists" in str(e).lower():
                                skipped += 1
                            else:
                                errors.append(f"DO block {i}: {str(e)[:100]}")
                                logger.error(f"DO block {i} error: {e}")

                        # Execute remaining statements (CREATE INDEX, etc.)
                        if remainder.strip():
                            for stmt in remainder.split(';'):
                                stmt = stmt.strip()
                                if stmt and not stmt.startswith('--') and stmt != 'RAISE NOTICE':
                                    # Skip standalone RAISE NOTICE
                                    if 'RAISE NOTICE' in stmt and 'DO' not in stmt:
                                        continue
                                    try:
                                        conn.execute(text(stmt))
                                        executed += 1
                                        logger.info(f"Executed: {stmt[:50]}...")
                                    except Exception as e:
                                        if "already exists" in str(e).lower():
                                            skipped += 1
                                        else:
                                            errors.append(f"Statement: {str(e)[:100]}")

            conn.commit()

            # Verify columns were created
            result = conn.execute(text("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'tasks'
                AND column_name IN ('sla_milestone_id', 'sla_milestone_type', 'sla_date_field',
                                   'milestone_date', 'sla_days_allowed', 'sla_status')
                ORDER BY column_name
            """))
            columns = [{"name": row[0], "type": row[1]} for row in result.fetchall()]

        logger.info(f"SLA migration completed. Executed: {executed}, Skipped: {skipped}")

        return {
            "status": "success",
            "message": "SLA milestone type columns migration completed",
            "statements_executed": executed,
            "statements_skipped": skipped,
            "columns_verified": columns,
            "errors": errors if errors else None
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"SLA milestone type migration error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/delete-sample-data")
async def delete_sample_data_endpoint(
    admin: Any = Depends(verify_admin_access)
):
    """
    Delete all sample/test data from the database.
    This removes:
    - All tasks
    - All extracted_data (reconciliation items)
    - All referral_partners
    - All team_members
    - Sample users (Sarah Johnson, Michael Chen, Emily Davis, James Wilson)
    - Sample leads and loans with test/sample names
    """
    try:
        from database import SessionLocal
        from sqlalchemy import text

        db = SessionLocal()
        results = {
            "tasks_deleted": 0,
            "extracted_data_deleted": 0,
            "incoming_events_deleted": 0,
            "referral_partners_deleted": 0,
            "team_members_deleted": 0,
            "users_deleted": 0,
            "leads_deleted": 0,
            "loans_deleted": 0,
            "workflow_instances_deleted": 0,
            "workflow_tasks_deleted": 0,
            "errors": []
        }

        try:
            # Delete in the correct order to avoid FK violations

            # 1. Delete all tasks (no FK dependencies typically)
            try:
                result = db.execute(text("DELETE FROM tasks"))
                results["tasks_deleted"] = result.rowcount
                db.commit()
            except Exception as e:
                results["errors"].append(f"tasks: {str(e)[:100]}")
                db.rollback()

            # 2. Delete workflow_tasks first (has FK to workflow_instances)
            try:
                result = db.execute(text("DELETE FROM workflow_tasks"))
                results["workflow_tasks_deleted"] = result.rowcount
                db.commit()
            except Exception as e:
                results["errors"].append(f"workflow_tasks: {str(e)[:100]}")
                db.rollback()

            # 3. Delete workflow_instances
            try:
                result = db.execute(text("DELETE FROM workflow_instances"))
                results["workflow_instances_deleted"] = result.rowcount
                db.commit()
            except Exception as e:
                results["errors"].append(f"workflow_instances: {str(e)[:100]}")
                db.rollback()

            # 4. Delete ai_training_events FIRST (references extracted_data)
            try:
                result = db.execute(text("DELETE FROM ai_training_events"))
                results["ai_training_events_deleted"] = result.rowcount
                db.commit()
            except Exception as e:
                results["errors"].append(f"ai_training_events: {str(e)[:100]}")
                db.rollback()

            # 5. Delete extracted_data (references incoming_data_events)
            try:
                result = db.execute(text("DELETE FROM extracted_data"))
                results["extracted_data_deleted"] = result.rowcount
                db.commit()
            except Exception as e:
                results["errors"].append(f"extracted_data: {str(e)[:100]}")
                db.rollback()

            # 6. Delete incoming_data_events LAST
            try:
                result = db.execute(text("DELETE FROM incoming_data_events"))
                results["incoming_events_deleted"] = result.rowcount
                db.commit()
            except Exception as e:
                results["errors"].append(f"incoming_data_events: {str(e)[:100]}")
                db.rollback()

            # 6. Delete referral partners
            try:
                result = db.execute(text("DELETE FROM referral_partners"))
                results["referral_partners_deleted"] = result.rowcount
                db.commit()
            except Exception as e:
                results["errors"].append(f"referral_partners: {str(e)[:100]}")
                db.rollback()

            # 7. Delete team_members
            try:
                result = db.execute(text("DELETE FROM team_members"))
                results["team_members_deleted"] = result.rowcount
                db.commit()
            except Exception as e:
                results["errors"].append(f"team_members: {str(e)[:100]}")
                db.rollback()

            # 8. Delete team_member_profiles (separate table)
            try:
                result = db.execute(text("DELETE FROM team_member_profiles"))
                results["team_member_profiles_deleted"] = result.rowcount
                db.commit()
            except Exception as e:
                results["errors"].append(f"team_member_profiles: {str(e)[:100]}")
                db.rollback()

            # 9. Delete sample users (Sarah, Michael, Emily, James)
            sample_emails = [
                'sjohnson@cmgfi.com', 'mchen@cmgfi.com', 'edavis@cmgfi.com', 'jwilson@cmgfi.com',
                'sarah@cmghomeloans.com', 'michael@cmghomeloans.com',
                'emily@cmghomeloans.com', 'james@cmghomeloans.com'
            ]
            try:
                result = db.execute(
                    text("DELETE FROM users WHERE email = ANY(:emails)"),
                    {"emails": sample_emails}
                )
                results["users_deleted"] = result.rowcount
                db.commit()
            except Exception as e:
                results["errors"].append(f"users: {str(e)[:100]}")
                db.rollback()

            # 10. Delete sample leads
            try:
                result = db.execute(text("""
                    DELETE FROM leads WHERE
                    first_name IN ('Test', 'Sample', 'Demo', 'John', 'Jane') AND
                    last_name IN ('User', 'Lead', 'Test', 'Sample', 'Doe')
                """))
                results["leads_deleted"] = result.rowcount
                db.commit()
            except Exception as e:
                results["errors"].append(f"leads: {str(e)[:100]}")
                db.rollback()

            # 11. Delete sample loans (including seeded sample data)
            seeded_borrower_names = [
                'Jeffrey Kim', 'Patricia Luna', 'David Okafor',
                'Rachel Green', 'William Chen', 'Sandra Yee'
            ]
            try:
                # Delete related records first
                for table in ['loan_documents', 'loan_notes', 'loan_activities', 'loan_conditions', 'loan_team_members']:
                    try:
                        db.execute(text(f"""
                            DELETE FROM {table}
                            WHERE loan_id IN (
                                SELECT id FROM loans WHERE
                                borrower_name = ANY(:names) OR
                                borrower_name LIKE '%Test%' OR
                                borrower_name LIKE '%Sample%' OR
                                borrower_name LIKE '%Demo%'
                            )
                        """), {"names": seeded_borrower_names})
                        db.commit()
                    except Exception as e:
                        logger.exception(f"Failed to delete related records from {table}: {e}")
                        db.rollback()

                # Now delete the loans
                result = db.execute(text("""
                    DELETE FROM loans WHERE
                    borrower_name = ANY(:names) OR
                    borrower_name LIKE '%Test%' OR
                    borrower_name LIKE '%Sample%' OR
                    borrower_name LIKE '%Demo%'
                """), {"names": seeded_borrower_names})
                results["loans_deleted"] = result.rowcount
                db.commit()
            except Exception as e:
                results["errors"].append(f"loans: {str(e)[:100]}")
                db.rollback()

            logger.info(f"Sample data cleanup completed: {results}")

            return {
                "status": "success",
                "message": "Sample data deleted successfully",
                "results": results
            }

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Sample data deletion error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/add-missing-columns")
async def add_missing_database_columns(
    admin: Any = Depends(verify_admin_access)
):
    """
    Add missing database columns that are causing 500 errors.
    - loans.prospect_date and other Jungo date fields
    - permission_key column for permissions
    """
    try:
        db = SessionLocal()
        results = {"columns_added": [], "errors": [], "skipped": []}

        try:
            # Add Jungo date fields to loans table
            jungo_date_columns = [
                "prospect_date", "application_date", "le_pending_date", "credit_only_date",
                "file_received_date", "preapproval_date", "lock_date", "lock_expiration_date",
                "uw_received_date", "conditions_for_review_date", "suspended_date",
                "loan_approved_date", "approved_not_accepted_date", "approval_expires_date",
                "appraisal_ordered_date", "appraisal_received_date", "appraisal_docs_expire_date",
                "cd_requested_date", "cd_sent_to_borrower_date", "cd_acknowledged_date",
                "clear_to_close_date", "docs_ordered_date", "docs_out_date", "credit_docs_expire_date",
                "scheduled_closing_date", "scheduled_funding_date", "funds_ordered_date",
                "funds_sent_date", "funded_date", "closing_date", "first_payment_date",
                "investor_purchased_date"
            ]

            for col in jungo_date_columns:
                try:
                    db.execute(text(f"""
                        ALTER TABLE loans ADD COLUMN IF NOT EXISTS {col} TIMESTAMP
                    """))
                    results["columns_added"].append(f"loans.{col}")
                except Exception as e:
                    if "already exists" in str(e).lower():
                        results["skipped"].append(f"loans.{col}")
                    else:
                        results["errors"].append(f"loans.{col}: {str(e)[:100]}")

            db.commit()

            # Add permission_key to user_permissions if it exists
            try:
                db.execute(text("""
                    ALTER TABLE user_permissions ADD COLUMN IF NOT EXISTS permission_key VARCHAR(100)
                """))
                results["columns_added"].append("user_permissions.permission_key")
                db.commit()
            except Exception as e:
                if "already exists" in str(e).lower():
                    results["skipped"].append("user_permissions.permission_key")
                elif "does not exist" in str(e).lower():
                    # Table doesn't exist, create it
                    try:
                        db.execute(text("""
                            CREATE TABLE IF NOT EXISTS user_permissions (
                                id SERIAL PRIMARY KEY,
                                user_id INTEGER REFERENCES users(id),
                                permission_key VARCHAR(100) NOT NULL,
                                granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                granted_by INTEGER,
                                UNIQUE(user_id, permission_key)
                            )
                        """))
                        results["columns_added"].append("user_permissions (table created)")
                        db.commit()
                    except Exception as e2:
                        results["errors"].append(f"user_permissions table: {str(e2)[:100]}")
                else:
                    results["errors"].append(f"user_permissions.permission_key: {str(e)[:100]}")

            logger.info(f"Missing columns migration completed: {results}")

            return {
                "status": "success",
                "message": "Missing columns migration completed",
                "results": results
            }

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Missing columns migration error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/fix-loan-stages")
async def fix_loan_stages(key: str = ""):
    """
    Fix NULL loan stage values to 'Processing'.
    Call with: POST /api/v1/migrations/fix-loan-stages?key=fix-stages
    """
    if key != "fix-stages":
        raise HTTPException(status_code=403, detail="Invalid key")

    db = SessionLocal()
    try:
        # Count NULLs before fix
        result = db.execute(text("SELECT COUNT(*) FROM loans WHERE stage IS NULL"))
        null_count = result.scalar()

        # Fix NULL stages
        db.execute(text("UPDATE loans SET stage = 'Processing' WHERE stage IS NULL"))
        db.commit()

        return {
            "status": "success",
            "null_count_before": null_count,
            "message": f"Fixed {null_count} NULL loan stages to 'Processing'"
        }
    except Exception as e:
        logger.error(f"Fix loan stages error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        db.close()


@router.post("/fix-loan-required-fields")
async def fix_loan_required_fields(key: str = ""):
    """
    Fix NULL values in required loan fields that cause validation errors.
    Call with: POST /api/v1/migrations/fix-loan-required-fields?key=fix-loans
    """
    if key != "fix-loans":
        raise HTTPException(status_code=403, detail="Invalid key")

    db = SessionLocal()
    try:
        fixes = {}

        # Check for NULL amounts
        result = db.execute(text("SELECT COUNT(*) FROM loans WHERE amount IS NULL"))
        null_amounts = result.scalar()
        if null_amounts > 0:
            db.execute(text("UPDATE loans SET amount = 0 WHERE amount IS NULL"))
            fixes["amount"] = null_amounts

        # Check for NULL days_in_stage
        result = db.execute(text("SELECT COUNT(*) FROM loans WHERE days_in_stage IS NULL"))
        null_days = result.scalar()
        if null_days > 0:
            db.execute(text("UPDATE loans SET days_in_stage = 0 WHERE days_in_stage IS NULL"))
            fixes["days_in_stage"] = null_days

        # Check for NULL sla_status
        result = db.execute(text("SELECT COUNT(*) FROM loans WHERE sla_status IS NULL"))
        null_sla = result.scalar()
        if null_sla > 0:
            db.execute(text("UPDATE loans SET sla_status = 'On Track' WHERE sla_status IS NULL"))
            fixes["sla_status"] = null_sla

        # Check for NULL stage
        result = db.execute(text("SELECT COUNT(*) FROM loans WHERE stage IS NULL"))
        null_stage = result.scalar()
        if null_stage > 0:
            db.execute(text("UPDATE loans SET stage = 'Processing' WHERE stage IS NULL"))
            fixes["stage"] = null_stage

        # Check for NULL borrower_name
        result = db.execute(text("SELECT COUNT(*) FROM loans WHERE borrower_name IS NULL OR borrower_name = ''"))
        null_borrower = result.scalar()
        if null_borrower > 0:
            db.execute(text("UPDATE loans SET borrower_name = 'Unknown Borrower' WHERE borrower_name IS NULL OR borrower_name = ''"))
            fixes["borrower_name"] = null_borrower

        # Check for NULL loan_number
        result = db.execute(text("SELECT COUNT(*) FROM loans WHERE loan_number IS NULL OR loan_number = ''"))
        null_loan_number = result.scalar()
        if null_loan_number > 0:
            db.execute(text("UPDATE loans SET loan_number = 'LN-' || id WHERE loan_number IS NULL OR loan_number = ''"))
            fixes["loan_number"] = null_loan_number

        # Check for NULL created_at
        result = db.execute(text("SELECT COUNT(*) FROM loans WHERE created_at IS NULL"))
        null_created = result.scalar()
        if null_created > 0:
            db.execute(text("UPDATE loans SET created_at = NOW() WHERE created_at IS NULL"))
            fixes["created_at"] = null_created

        db.commit()

        return {
            "status": "success",
            "fixes": fixes,
            "total_fixed": sum(fixes.values()),
            "message": f"Fixed {sum(fixes.values())} NULL values in required fields"
        }
    except Exception as e:
        logger.error(f"Fix loan required fields error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        db.close()


@router.get("/debug-loans")
async def debug_loans(key: str = ""):
    """
    Debug endpoint to check loan data for validation issues.
    Call with: GET /api/v1/migrations/debug-loans?key=debug
    """
    if key != "debug":
        raise HTTPException(status_code=403, detail="Invalid key")

    db = SessionLocal()
    try:
        # Get sample loan data
        result = db.execute(text("""
            SELECT id, loan_number, borrower_name, stage, amount,
                   days_in_stage, sla_status, created_at, loan_officer_id
            FROM loans
            LIMIT 5
        """))
        loans = [dict(row._mapping) for row in result.fetchall()]

        # Check for NULL values in required fields
        nulls = db.execute(text("""
            SELECT
                COUNT(*) FILTER (WHERE loan_number IS NULL OR loan_number = '') as null_loan_number,
                COUNT(*) FILTER (WHERE borrower_name IS NULL OR borrower_name = '') as null_borrower,
                COUNT(*) FILTER (WHERE stage IS NULL) as null_stage,
                COUNT(*) FILTER (WHERE amount IS NULL) as null_amount,
                COUNT(*) FILTER (WHERE days_in_stage IS NULL) as null_days,
                COUNT(*) FILTER (WHERE sla_status IS NULL OR sla_status = '') as null_sla,
                COUNT(*) FILTER (WHERE created_at IS NULL) as null_created,
                COUNT(*) as total
            FROM loans
        """)).fetchone()

        return {
            "sample_loans": loans,
            "null_counts": dict(nulls._mapping),
            "total_loans": nulls._mapping["total"]
        }
    except Exception as e:
        logger.error(f"Debug loans error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        db.close()


@router.delete("/delete-unknown-borrowers")
async def delete_unknown_borrowers(key: str = ""):
    """
    Delete loans with 'Unknown Borrower' as borrower_name.
    Call with: DELETE /api/v1/migrations/delete-unknown-borrowers?key=delete-unknown
    """
    if key != "delete-unknown":
        raise HTTPException(status_code=403, detail="Invalid key")

    db = SessionLocal()
    try:
        # First get the IDs that will be deleted
        result = db.execute(text("""
            SELECT id, loan_number, borrower_name
            FROM loans
            WHERE borrower_name = 'Unknown Borrower'
        """))
        to_delete = [dict(row._mapping) for row in result.fetchall()]

        if not to_delete:
            return {
                "status": "success",
                "message": "No 'Unknown Borrower' loans found",
                "deleted_count": 0
            }

        # Delete the loans
        db.execute(text("""
            DELETE FROM loans
            WHERE borrower_name = 'Unknown Borrower'
        """))
        db.commit()

        return {
            "status": "success",
            "deleted_count": len(to_delete),
            "deleted_loans": to_delete,
            "message": f"Deleted {len(to_delete)} 'Unknown Borrower' loans"
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Delete unknown borrowers error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        db.close()


@router.get("/debug-mum-clients")
async def debug_mum_clients(key: str = ""):
    """
    Debug endpoint to check mum_clients data and table structure.
    Call with: GET /api/v1/migrations/debug-mum-clients?key=debug
    """
    if key != "debug":
        raise HTTPException(status_code=403, detail="Invalid key")

    db = SessionLocal()
    try:
        # Check if table exists and get column info
        table_info = db.execute(text("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'mum_clients'
            ORDER BY ordinal_position
        """))
        columns = [dict(row._mapping) for row in table_info.fetchall()]

        # Get sample mum_clients data
        result = db.execute(text("""
            SELECT id, name, loan_number, user_id, created_at
            FROM mum_clients
            ORDER BY created_at DESC
            LIMIT 10
        """))
        clients = [dict(row._mapping) for row in result.fetchall()]

        # Get counts by user_id
        user_counts = db.execute(text("""
            SELECT user_id, COUNT(*) as count
            FROM mum_clients
            GROUP BY user_id
        """))
        by_user = [dict(row._mapping) for row in user_counts.fetchall()]

        # Get total count
        total = db.execute(text("SELECT COUNT(*) FROM mum_clients")).scalar()

        return {
            "table_columns": columns,
            "sample_clients": clients,
            "by_user_id": by_user,
            "total_clients": total
        }
    except Exception as e:
        logger.error(f"Debug mum_clients error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        db.close()


@router.post("/test-mum-insert")
async def test_mum_insert(key: str = "", user_id: int = 118):
    """
    Test direct insert into mum_clients to debug issues.
    Call with: POST /api/v1/migrations/test-mum-insert?key=test-mum&user_id=118
    """
    if key != "test-mum":
        raise HTTPException(status_code=403, detail="Invalid key")

    db = SessionLocal()
    try:
        from datetime import datetime
        # Try inserting a test record with all required fields
        db.execute(text("""
            INSERT INTO mum_clients (
                client_name, original_loan_amount, current_loan_amount,
                interest_rate, appraisal_value_at_closing, current_property_value,
                closing_date, first_payment_date, user_id, status, created_at, name
            ) VALUES (
                'Test Client', 300000, 290000,
                6.5, 375000, 400000,
                '2024-01-15', '2024-03-01', :user_id, 'active', NOW(), 'Test Client'
            )
        """), {"user_id": user_id})
        db.commit()

        # Verify it was inserted
        count = db.execute(text("SELECT COUNT(*) FROM mum_clients")).scalar()

        return {
            "status": "success",
            "message": "Test record inserted successfully",
            "total_mum_clients": count
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Test mum insert error: {e}")
        return {
            "status": "error",
            "error": "Internal server error"
        }
    finally:
        db.close()


@router.post("/test-mum-import-row")
async def test_mum_import_row(key: str = "", user_id: int = 118):
    """
    Test importing a single mum_clients row using import-style columns.
    Call with: POST /api/v1/migrations/test-mum-import-row?key=test-import&user_id=118
    """
    if key != "test-import":
        raise HTTPException(status_code=403, detail="Invalid key")

    import psycopg2
    from datetime import datetime

    # Simulate data that would come from import
    test_row = {
        'name': 'Import Test Client',
        'loan_number': 'TEST123456',
        'loan_balance': 350000,
        'current_rate': 6.875,
        'original_close_date': datetime(2024, 6, 15),
    }

    # Build columns and values like import does
    columns = list(test_row.keys())
    values = list(test_row.values())

    try:
        # Map 'name' to 'client_name'
        if 'name' in columns and 'client_name' not in columns:
            idx = columns.index('name')
            columns[idx] = 'client_name'

        # Add required NOT NULL fields
        required_fields = {
            'created_at': datetime.utcnow(),
            'status': 'active',
            'original_loan_amount': 0,
            'current_loan_amount': 0,
            'interest_rate': 0,
            'appraisal_value_at_closing': 0,
            'current_property_value': 0,
            'closing_date': datetime.utcnow().date(),
            'first_payment_date': datetime.utcnow().date(),
        }

        # Map loan_balance to required fields
        if 'loan_balance' in columns:
            idx = columns.index('loan_balance')
            lb_val = values[idx] or 0
            if 'original_loan_amount' not in columns:
                columns.append('original_loan_amount')
                values.append(lb_val)
            if 'current_loan_amount' not in columns:
                columns.append('current_loan_amount')
                values.append(lb_val)
            if 'appraisal_value_at_closing' not in columns:
                columns.append('appraisal_value_at_closing')
                values.append(lb_val * 1.25 if lb_val else 0)
            if 'current_property_value' not in columns:
                columns.append('current_property_value')
                values.append(lb_val * 1.25 if lb_val else 0)

        if 'current_rate' in columns and 'interest_rate' not in columns:
            idx = columns.index('current_rate')
            columns.append('interest_rate')
            values.append(values[idx] or 0)

        if 'original_close_date' in columns and 'closing_date' not in columns:
            idx = columns.index('original_close_date')
            columns.append('closing_date')
            values.append(values[idx] or datetime.utcnow().date())
            if 'first_payment_date' not in columns:
                columns.append('first_payment_date')
                values.append(values[idx] or datetime.utcnow().date())

        # Add remaining required fields
        for field, default in required_fields.items():
            if field not in columns:
                columns.append(field)
                values.append(default)

        # Add user_id
        if 'user_id' not in columns:
            columns.append('user_id')
            values.append(user_id)

        # Connect and insert
        import os
        conn = psycopg2.connect(os.getenv("DATABASE_URL"))
        cursor = conn.cursor()

        placeholders = ', '.join(['%s'] * len(columns))
        columns_str = ', '.join(columns)

        cursor.execute(
            f"INSERT INTO mum_clients ({columns_str}) VALUES ({placeholders})",
            values
        )
        conn.commit()

        # Get count
        cursor.execute("SELECT COUNT(*) FROM mum_clients")
        count = cursor.fetchone()[0]

        cursor.close()
        conn.close()

        return {
            "status": "success",
            "message": "Import-style test record inserted successfully",
            "columns_used": columns,
            "total_mum_clients": count
        }

    except Exception as e:
        return {
            "status": "error",
            "error": "Internal server error",
            "columns_attempted": columns,
            "values_count": len(values)
        }


@router.post("/fix-mum-clients-user-id")
async def fix_mum_clients_user_id(key: str = "", user_id: int = 118):
    """
    Fix mum_clients with NULL user_id by assigning them to specified user.
    Call with: POST /api/v1/migrations/fix-mum-clients-user-id?key=fix-mum&user_id=118
    """
    if key != "fix-mum":
        raise HTTPException(status_code=403, detail="Invalid key")

    db = SessionLocal()
    try:
        # Count affected rows
        count = db.execute(text("""
            SELECT COUNT(*) FROM mum_clients WHERE user_id IS NULL
        """)).scalar()

        if count == 0:
            return {
                "status": "success",
                "message": "No mum_clients with NULL user_id",
                "updated_count": 0
            }

        # Update all NULL user_ids
        db.execute(text("""
            UPDATE mum_clients
            SET user_id = :user_id
            WHERE user_id IS NULL
        """), {"user_id": user_id})
        db.commit()

        return {
            "status": "success",
            "updated_count": count,
            "assigned_to_user_id": user_id,
            "message": f"Updated {count} mum_clients with user_id = {user_id}"
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Fix mum_clients user_id error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        db.close()


@router.post("/clear-mum-clients-for-reimport")
async def clear_mum_clients_for_reimport(key: str = "", user_id: int = 0):
    """
    Delete all mum_clients for a user to allow fresh re-import with corrected names.
    Call with: POST /api/v1/migrations/clear-mum-clients-for-reimport?key=clear-mum&user_id=118
    """
    if key != "clear-mum":
        raise HTTPException(status_code=403, detail="Invalid key. Use ?key=clear-mum&user_id=N")

    if user_id <= 0:
        raise HTTPException(status_code=400, detail="Must specify a valid user_id")

    db = SessionLocal()
    try:
        # Count records to delete
        count = db.execute(text("""
            SELECT COUNT(*) FROM mum_clients WHERE user_id = :user_id
        """), {"user_id": user_id}).scalar()

        if count == 0:
            return {
                "status": "success",
                "message": f"No mum_clients found for user_id {user_id}",
                "deleted_count": 0
            }

        # Delete all mum_clients for this user
        db.execute(text("""
            DELETE FROM mum_clients WHERE user_id = :user_id
        """), {"user_id": user_id})
        db.commit()

        return {
            "status": "success",
            "message": f"Deleted {count} mum_clients for user_id {user_id}. Ready for re-import.",
            "deleted_count": count,
            "user_id": user_id
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Clear mum_clients error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        db.close()


@router.post("/fix-mum-client-names")
async def fix_mum_client_names(key: str = ""):
    """
    Fix mum_clients with generic 'Client N' names by looking up borrower names from loans table.
    Call with: POST /api/v1/migrations/fix-mum-client-names?key=fix-names
    """
    if key != "fix-names":
        raise HTTPException(status_code=403, detail="Invalid key. Use ?key=fix-names")

    db = SessionLocal()
    try:
        # Find mum_clients with generic names (matching 'Client N' pattern)
        generic_clients = db.execute(text("""
            SELECT id, client_name, loan_number
            FROM mum_clients
            WHERE client_name ~ '^Client [0-9]+$'
               OR client_name ~ '^Client \\(Loan #'
            ORDER BY id
        """)).fetchall()

        if not generic_clients:
            return {
                "status": "success",
                "message": "No mum_clients with generic 'Client N' names found",
                "updated_count": 0,
                "checked_count": 0
            }

        updated_count = 0
        not_found = []
        updated_details = []

        for client in generic_clients:
            client_id, current_name, loan_number = client

            if not loan_number:
                not_found.append({"id": client_id, "name": current_name, "reason": "no loan_number"})
                continue

            # Try to find borrower name from loans table
            loan = db.execute(text("""
                SELECT borrower_name FROM loans WHERE loan_number = :loan_number
            """), {"loan_number": loan_number}).fetchone()

            if loan and loan[0] and loan[0] != 'Unknown Borrower':
                borrower_name = loan[0]
                db.execute(text("""
                    UPDATE mum_clients
                    SET client_name = :name, updated_at = NOW()
                    WHERE id = :id
                """), {"name": borrower_name, "id": client_id})
                updated_count += 1
                updated_details.append({
                    "id": client_id,
                    "old_name": current_name,
                    "new_name": borrower_name,
                    "loan_number": loan_number
                })
            else:
                not_found.append({
                    "id": client_id,
                    "name": current_name,
                    "loan_number": loan_number,
                    "reason": "loan not found or no borrower_name"
                })

        db.commit()

        return {
            "status": "success",
            "message": f"Updated {updated_count} mum_client names from loans table",
            "checked_count": len(generic_clients),
            "updated_count": updated_count,
            "not_found_count": len(not_found),
            "updated_details": updated_details[:20],  # Limit to first 20
            "not_found_sample": not_found[:10]  # Sample of not found
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Fix mum_client names error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        db.close()


@router.post("/migrate-leads-to-mum-clients")
async def migrate_leads_to_mum_clients(
    key: str = "",
    source_filter: str = "Auto Import",
    user_id: int = 0,
    delete_after: bool = True
):
    """
    Migrate leads to MUM clients.
    This moves leads that were accidentally imported as leads to the mum_clients table.

    Call with: POST /api/v1/migrations/migrate-leads-to-mum-clients?key=migrate-to-mum&source_filter=Auto%20Import&user_id=118&delete_after=true

    Parameters:
    - key: Security key (must be "migrate-to-mum")
    - source_filter: Only migrate leads with this source (default: "Auto Import")
    - user_id: User ID to assign MUM clients to (if 0, uses lead's owner_id)
    - delete_after: Delete leads after successful migration (default: true)
    """
    if key != "migrate-to-mum":
        raise HTTPException(status_code=403, detail="Invalid key. Use ?key=migrate-to-mum")

    db = SessionLocal()
    try:
        # First, ensure LTV column can handle values >= 100 (VA loans)
        try:
            db.execute(text("ALTER TABLE mum_clients ALTER COLUMN ltv TYPE DECIMAL(7,4)"))
            db.commit()
        except Exception as e:
            logger.exception(f"Failed to alter mum_clients.ltv column type (may already be correct): {e}")
            db.rollback()  # Column might already be correct type

        # Get leads to migrate
        leads_query = """
            SELECT
                id, name, first_name, last_name, email, phone,
                loan_number, loan_amount, interest_rate,
                appraisal_value, property_value, closing_date,
                loan_type, ltv, owner_id, source, created_at
            FROM leads
            WHERE source = :source_filter
            ORDER BY created_at DESC
        """
        leads = db.execute(text(leads_query), {"source_filter": source_filter}).fetchall()

        if not leads:
            return {
                "status": "success",
                "message": f"No leads found with source '{source_filter}'",
                "migrated_count": 0
            }

        migrated = []
        errors = []
        lead_ids_to_delete = []

        for lead in leads:
            try:
                # Build client_name from available fields
                client_name = lead.name
                if not client_name or client_name.strip() == '':
                    first = lead.first_name or ''
                    last = lead.last_name or ''
                    client_name = f"{first} {last}".strip()
                if not client_name:
                    client_name = f"Client (Lead #{lead.id})"

                # Determine user_id for the MUM client
                mum_user_id = user_id if user_id > 0 else lead.owner_id

                # Get loan amount (default to 0 if not available)
                loan_amount = lead.loan_amount or 0

                # Get interest rate (default to 0 if not available)
                rate = lead.interest_rate or 0

                # Get property value - try appraisal first, then property_value
                prop_value = lead.appraisal_value or lead.property_value or 0

                # Get closing date (default to today if not available)
                from datetime import date, timedelta
                closing = lead.closing_date
                if closing is None:
                    closing = date.today()
                elif hasattr(closing, 'date'):
                    closing = closing.date()

                # First payment date is typically ~30 days after closing
                first_payment = closing + timedelta(days=30)

                # Insert into mum_clients
                insert_query = """
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
                        :client_name, :email, :phone,
                        :loan_number,
                        :loan_amount, :loan_amount,
                        :interest_rate,
                        :prop_value, :prop_value,
                        :closing_date, :first_payment_date,
                        :loan_type, :ltv,
                        :user_id, 'active', true,
                        NOW(), NOW()
                    )
                    RETURNING id
                """

                result = db.execute(text(insert_query), {
                    "client_name": client_name,
                    "email": lead.email,
                    "phone": lead.phone,
                    "loan_number": lead.loan_number,
                    "loan_amount": loan_amount,
                    "interest_rate": rate,
                    "prop_value": prop_value,
                    "closing_date": closing,
                    "first_payment_date": first_payment,
                    "loan_type": lead.loan_type,
                    "ltv": lead.ltv,
                    "user_id": mum_user_id
                })

                new_mum_id = result.fetchone()[0]

                migrated.append({
                    "lead_id": lead.id,
                    "mum_client_id": new_mum_id,
                    "client_name": client_name,
                    "email": lead.email
                })
                lead_ids_to_delete.append(lead.id)

            except Exception as e:
                # Rollback the failed transaction and start fresh
                db.rollback()
                errors.append({
                    "lead_id": lead.id,
                    "name": lead.name,
                    "error": "Internal server error"
                })

        # Delete migrated leads if requested
        deleted_count = 0
        if delete_after and lead_ids_to_delete:
            # Delete in batches to avoid issues with large lists
            for i in range(0, len(lead_ids_to_delete), 100):
                batch = lead_ids_to_delete[i:i+100]
                db.execute(text("""
                    DELETE FROM leads WHERE id = ANY(:ids)
                """), {"ids": batch})
                deleted_count += len(batch)

        db.commit()

        return {
            "status": "success",
            "message": f"Migrated {len(migrated)} leads to MUM clients",
            "source_filter": source_filter,
            "total_leads_found": len(leads),
            "migrated_count": len(migrated),
            "deleted_count": deleted_count if delete_after else 0,
            "error_count": len(errors),
            "migrated_sample": migrated[:20],  # First 20 for reference
            "errors": errors[:10] if errors else []  # First 10 errors
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Migrate leads to MUM clients error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        db.close()


@router.post("/create-salesforce-oauth-tables")
async def create_salesforce_oauth_tables(key: str = ""):
    """
    Create all Salesforce OAuth integration tables.
    Required for the new per-user Salesforce OAuth system.

    Call with: POST /api/v1/migrations/create-salesforce-oauth-tables?key=create-sf-oauth
    """
    if key != "create-sf-oauth":
        raise HTTPException(status_code=403, detail="Invalid key. Use ?key=create-sf-oauth")

    try:
        from migrations.add_salesforce_oauth_tables import run_migration
        success = run_migration()

        # Check which tables exist now
        db = SessionLocal()
        try:
            tables_status = {}
            tables = ["integration_profiles", "sf_user_schemas", "field_mappings",
                      "oauth_states", "sync_queue", "integration_events",
                      "integration_record_tracking", "calendar_sync_settings"]

            for table in tables:
                try:
                    result = db.execute(text(f"SELECT COUNT(*) FROM {table}"))
                    count = result.scalar()
                    tables_status[table] = {"exists": True, "count": count}
                except Exception as e:
                    tables_status[table] = {"exists": False, "error": "Internal server error"[:100]}

            return {
                "status": "success" if success else "partial",
                "migration_success": success,
                "tables": tables_status,
                "message": "Salesforce OAuth tables created/verified successfully" if success else "Migration completed with some issues"
            }
        finally:
            db.close()

    except Exception as e:
        logger.error(f"Create Salesforce OAuth tables error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/diagnose-salesforce")
async def diagnose_salesforce():
    """
    Diagnose Salesforce integration profiles - no auth required for debugging.
    """
    db = SessionLocal()
    try:
        diagnosis = {
            "profiles": [],
            "oauth_states_recent": [],
            "errors": []
        }

        try:
            # Get all integration profiles
            result = db.execute(text("""
                SELECT id, user_id, provider, status, instance_url, sf_username, sf_org_id,
                       connected_at, last_sync_at, last_error, sync_enabled,
                       CASE WHEN access_token_encrypted IS NOT NULL THEN true ELSE false END as has_access_token,
                       CASE WHEN refresh_token_encrypted IS NOT NULL THEN true ELSE false END as has_refresh_token
                FROM integration_profiles
                ORDER BY id DESC
                LIMIT 10
            """))
            profiles = result.fetchall()

            for p in profiles:
                diagnosis["profiles"].append({
                    "id": p[0],
                    "user_id": p[1],
                    "provider": p[2],
                    "status": p[3],
                    "instance_url": p[4],
                    "sf_username": p[5],
                    "sf_org_id": p[6],
                    "connected_at": str(p[7]) if p[7] else None,
                    "last_sync_at": str(p[8]) if p[8] else None,
                    "last_error": p[9],
                    "sync_enabled": p[10],
                    "has_access_token": p[11],
                    "has_refresh_token": p[12]
                })
        except Exception as e:
            diagnosis["errors"].append(f"Error fetching profiles: {str(e)}")

        try:
            # Get recent OAuth states
            result = db.execute(text("""
                SELECT id, user_id, provider, created_at, expires_at, used
                FROM oauth_states
                ORDER BY created_at DESC
                LIMIT 5
            """))
            states = result.fetchall()

            for s in states:
                diagnosis["oauth_states_recent"].append({
                    "id": s[0],
                    "user_id": s[1],
                    "provider": s[2],
                    "created_at": str(s[3]) if s[3] else None,
                    "expires_at": str(s[4]) if s[4] else None,
                    "used": s[5]
                })
        except Exception as e:
            diagnosis["errors"].append(f"Error fetching oauth_states: {str(e)}")

        return diagnosis

    finally:
        db.close()


@router.post("/fix-500-errors")
async def fix_500_errors(
    admin: Any = Depends(verify_admin_access)
):
    """
    Comprehensive fix for 500 Internal Server Errors.
    Creates missing tables: notifications, user_permissions, permission_templates, ai_tasks.
    Adds missing columns to users table.
    """
    try:
        db = SessionLocal()
        results = {
            "tables_created": [],
            "columns_added": [],
            "errors": [],
            "skipped": []
        }

        try:
            # ================================================================
            # 1. Create notifications table
            # ================================================================
            try:
                db.execute(text("""
                    CREATE TABLE IF NOT EXISTS notifications (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        type VARCHAR(50) NOT NULL,
                        title VARCHAR(255) NOT NULL,
                        message TEXT NOT NULL,
                        link VARCHAR(500),
                        is_read BOOLEAN DEFAULT FALSE,
                        read_at TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                db.commit()

                # Create indexes
                db.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id);
                    CREATE INDEX IF NOT EXISTS idx_notifications_read ON notifications(is_read);
                    CREATE INDEX IF NOT EXISTS idx_notifications_created ON notifications(created_at DESC);
                """))
                db.commit()
                results["tables_created"].append("notifications")
            except Exception as e:
                if "already exists" in str(e).lower():
                    results["skipped"].append("notifications table")
                else:
                    results["errors"].append(f"notifications: {str(e)[:100]}")
                db.rollback()

            # ================================================================
            # 2. Create user_permissions table
            # ================================================================
            try:
                # First try to create the table
                db.execute(text("""
                    CREATE TABLE IF NOT EXISTS user_permissions (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        permission_key VARCHAR(255) NOT NULL,
                        granted BOOLEAN DEFAULT TRUE,
                        granted_by INTEGER REFERENCES users(id),
                        granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        expires_at TIMESTAMP,
                        inherited_from VARCHAR(50) DEFAULT 'template',
                        CONSTRAINT unique_user_permission UNIQUE (user_id, permission_key)
                    )
                """))
                db.commit()
                results["tables_created"].append("user_permissions")
            except Exception as e:
                db.rollback()
                results["skipped"].append("user_permissions table (exists)")

            # Add missing columns to existing user_permissions table
            try:
                db.execute(text("ALTER TABLE user_permissions ADD COLUMN IF NOT EXISTS granted BOOLEAN DEFAULT TRUE"))
                db.execute(text("ALTER TABLE user_permissions ADD COLUMN IF NOT EXISTS granted_by INTEGER"))
                db.execute(text("ALTER TABLE user_permissions ADD COLUMN IF NOT EXISTS granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
                db.execute(text("ALTER TABLE user_permissions ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP"))
                db.execute(text("ALTER TABLE user_permissions ADD COLUMN IF NOT EXISTS inherited_from VARCHAR(50) DEFAULT 'template'"))
                db.commit()
                results["columns_added"].append("user_permissions columns")
            except Exception as e:
                db.rollback()

            # Create indexes (ignore if they exist)
            try:
                db.execute(text("CREATE INDEX IF NOT EXISTS idx_user_permissions_user ON user_permissions(user_id)"))
                db.commit()
            except Exception as e:
                logger.exception(f"Failed to create idx_user_permissions_user index: {e}")
                db.rollback()

            # ================================================================
            # 3. Create permission_templates table
            # ================================================================
            try:
                db.execute(text("""
                    CREATE TABLE IF NOT EXISTS permission_templates (
                        id SERIAL PRIMARY KEY,
                        name VARCHAR(255) NOT NULL UNIQUE,
                        description TEXT,
                        category VARCHAR(50) NOT NULL,
                        permissions JSONB NOT NULL DEFAULT '{}',
                        is_system_default BOOLEAN DEFAULT FALSE,
                        created_by INTEGER REFERENCES users(id),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                db.commit()
                results["tables_created"].append("permission_templates")
            except Exception as e:
                if "already exists" in str(e).lower():
                    results["skipped"].append("permission_templates table")
                else:
                    results["errors"].append(f"permission_templates: {str(e)[:100]}")
                db.rollback()

            # ================================================================
            # 4. Add permission_role column to users table
            # ================================================================
            try:
                db.execute(text("""
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS permission_role VARCHAR(50) DEFAULT 'sales'
                """))
                db.commit()
                results["columns_added"].append("users.permission_role")
            except Exception as e:
                if "already exists" in str(e).lower():
                    results["skipped"].append("users.permission_role")
                else:
                    results["errors"].append(f"users.permission_role: {str(e)[:100]}")
                db.rollback()

            # ================================================================
            # 5. Create ai_tasks table if it doesn't exist
            # ================================================================
            try:
                db.execute(text("""
                    CREATE TABLE IF NOT EXISTS ai_tasks (
                        id SERIAL PRIMARY KEY,
                        title VARCHAR(255) NOT NULL,
                        description TEXT,
                        type VARCHAR(50),
                        category VARCHAR(100),
                        priority INTEGER DEFAULT 0,
                        status VARCHAR(50) DEFAULT 'pending',
                        ai_confidence FLOAT,
                        ai_reasoning TEXT,
                        suggested_action TEXT,
                        due_date TIMESTAMP,
                        assigned_to_id INTEGER REFERENCES users(id),
                        created_by_id INTEGER REFERENCES users(id),
                        lead_id INTEGER,
                        loan_id INTEGER,
                        entity_type VARCHAR(50),
                        entity_id INTEGER,
                        completed_at TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                db.commit()

                db.commit()
                results["tables_created"].append("ai_tasks")
            except Exception as e:
                db.rollback()
                results["skipped"].append("ai_tasks table (exists)")

            # Add missing columns to ai_tasks table
            try:
                db.execute(text("ALTER TABLE ai_tasks ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'pending'"))
                db.execute(text("ALTER TABLE ai_tasks ADD COLUMN IF NOT EXISTS ai_confidence FLOAT"))
                db.execute(text("ALTER TABLE ai_tasks ADD COLUMN IF NOT EXISTS ai_reasoning TEXT"))
                db.execute(text("ALTER TABLE ai_tasks ADD COLUMN IF NOT EXISTS suggested_action TEXT"))
                db.execute(text("ALTER TABLE ai_tasks ADD COLUMN IF NOT EXISTS entity_type VARCHAR(50)"))
                db.execute(text("ALTER TABLE ai_tasks ADD COLUMN IF NOT EXISTS entity_id INTEGER"))
                db.execute(text("ALTER TABLE ai_tasks ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP"))
                db.commit()
                results["columns_added"].append("ai_tasks columns")
            except Exception as e:
                db.rollback()

            # Create indexes (ignore if they exist or column doesn't exist)
            try:
                db.execute(text("CREATE INDEX IF NOT EXISTS idx_ai_tasks_assigned ON ai_tasks(assigned_to_id)"))
                db.commit()
            except Exception as e:
                logger.exception(f"Failed to create idx_ai_tasks_assigned index: {e}")
                db.rollback()
            try:
                db.execute(text("CREATE INDEX IF NOT EXISTS idx_ai_tasks_status ON ai_tasks(status)"))
                db.commit()
            except Exception as e:
                logger.exception(f"Failed to create idx_ai_tasks_status index: {e}")
                db.rollback()
            try:
                db.execute(text("CREATE INDEX IF NOT EXISTS idx_ai_tasks_created ON ai_tasks(created_at DESC)"))
                db.commit()
            except Exception as e:
                logger.exception(f"Failed to create idx_ai_tasks_created index: {e}")
                db.rollback()

            # ================================================================
            # 6. Create incoming_data_events table (for reconciliation)
            # ================================================================
            try:
                db.execute(text("""
                    CREATE TABLE IF NOT EXISTS incoming_data_events (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER REFERENCES users(id),
                        source VARCHAR(50) NOT NULL,
                        source_id VARCHAR(255),
                        event_type VARCHAR(50),
                        raw_data JSONB,
                        processed BOOLEAN DEFAULT FALSE,
                        processed_at TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                db.commit()
                results["tables_created"].append("incoming_data_events")
            except Exception as e:
                if "already exists" in str(e).lower():
                    results["skipped"].append("incoming_data_events table")
                else:
                    results["errors"].append(f"incoming_data_events: {str(e)[:100]}")
                db.rollback()

            # ================================================================
            # 7. Create extracted_data table (for reconciliation)
            # ================================================================
            try:
                db.execute(text("""
                    CREATE TABLE IF NOT EXISTS extracted_data (
                        id SERIAL PRIMARY KEY,
                        event_id INTEGER REFERENCES incoming_data_events(id) ON DELETE CASCADE,
                        data_type VARCHAR(50),
                        fields JSONB,
                        match_entity_type VARCHAR(50),
                        match_entity_id INTEGER,
                        match_confidence FLOAT,
                        status VARCHAR(50) DEFAULT 'pending_review',
                        reviewed_by INTEGER REFERENCES users(id),
                        reviewed_at TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                db.commit()
                results["tables_created"].append("extracted_data")
            except Exception as e:
                if "already exists" in str(e).lower():
                    results["skipped"].append("extracted_data table")
                else:
                    results["errors"].append(f"extracted_data: {str(e)[:100]}")
                db.rollback()

            # ================================================================
            # 8. Seed default permission templates if needed
            # ================================================================
            try:
                # Check if templates already exist
                result = db.execute(text("""
                    SELECT COUNT(*) FROM permission_templates WHERE name IN ('Management', 'Sales', 'Operations')
                """))
                count = result.scalar()

                if count == 0:
                    # Seed default templates
                    import json

                    management_perms = {
                        "dashboard.view_all_widgets": True, "leads.view_all": True,
                        "loans.view_all": True, "team.view_all": True,
                        "team.manage_permissions": True, "permissions.view_all": True,
                        "permissions.manage": True, "tasks.view_all": True
                    }

                    sales_perms = {
                        "leads.view_assigned": True, "leads.create": True,
                        "leads.edit_own": True, "loans.view_assigned": True,
                        "tasks.view_assigned": True, "tasks.create": True
                    }

                    operations_perms = {
                        "leads.view_all": True, "loans.view_all": True,
                        "loans.process": True, "tasks.view_all": True
                    }

                    db.execute(text("""
                        INSERT INTO permission_templates (name, description, category, permissions, is_system_default)
                        VALUES
                        ('Management', 'Full access for management roles', 'management', :mgmt_perms, TRUE),
                        ('Sales', 'Sales-focused permissions', 'sales', :sales_perms, TRUE),
                        ('Operations', 'Operations-focused permissions', 'operations', :ops_perms, TRUE)
                    """), {
                        "mgmt_perms": json.dumps(management_perms),
                        "sales_perms": json.dumps(sales_perms),
                        "ops_perms": json.dumps(operations_perms)
                    })
                    db.commit()
                    results["tables_created"].append("permission_templates (seeded)")
                else:
                    results["skipped"].append("permission_templates (already seeded)")
            except Exception as e:
                results["errors"].append(f"permission_templates seeding: {str(e)[:100]}")
                db.rollback()

            logger.info(f"Fix 500 errors migration completed: {results}")

            return {
                "status": "success",
                "message": "500 errors fix migration completed",
                "results": results
            }

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Fix 500 errors migration error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/add-mum-salesforce-id")
async def add_mum_salesforce_id(
    admin: Any = Depends(verify_admin_access)
):
    """
    Add salesforce_id column to mum_clients table for Salesforce sync.
    """
    try:
        db = SessionLocal()
        results = {"columns_added": [], "skipped": [], "errors": []}

        try:
            # Check if column exists
            check = db.execute(text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'mum_clients' AND column_name = 'salesforce_id'
            """)).fetchone()

            if not check:
                db.execute(text("""
                    ALTER TABLE mum_clients
                    ADD COLUMN salesforce_id VARCHAR(100)
                """))
                db.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_mum_clients_salesforce_id
                    ON mum_clients(salesforce_id)
                """))
                db.commit()
                results["columns_added"].append("salesforce_id")
            else:
                results["skipped"].append("salesforce_id (already exists)")

            logger.info(f"MUM salesforce_id migration completed: {results}")

            return {
                "status": "success",
                "message": "MUM salesforce_id column migration completed",
                "results": results
            }

        finally:
            db.close()

    except Exception as e:
        logger.error(f"MUM salesforce_id migration error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/add-survey-tables")
async def add_survey_tables(
    admin: Any = Depends(verify_admin_access)
):
    """
    Create survey and feedback tables for customer satisfaction measurement.
    Creates: survey_templates, survey_questions, survey_responses,
             survey_answers, survey_analytics, savings_validations
    """
    try:
        from migrations.survey_tables import run_migration, check_tables_exist

        if check_tables_exist():
            return {
                "status": "success",
                "message": "Survey tables already exist",
                "created": False
            }

        logger.info("Starting survey tables migration...")
        success = run_migration()

        if success:
            return {
                "status": "success",
                "message": "Survey tables created successfully",
                "created": True,
                "tables": [
                    "survey_templates",
                    "survey_questions",
                    "survey_responses",
                    "survey_answers",
                    "survey_analytics",
                    "savings_validations"
                ]
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Survey tables migration failed"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Survey tables migration error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/run-survey-migration")
async def run_survey_migration_simple(
    secret_key: str = Header(None, alias="X-Secret-Key")
):
    """
    Simple survey migration endpoint - requires X-Secret-Key header matching SECRET_KEY env var.
    Creates all survey tables.
    """
    import re
    expected_key = re.sub(r'\s+', '', os.getenv("SECRET_KEY", ""))
    provided_key = re.sub(r'\s+', '', secret_key or "")

    if not expected_key or provided_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid secret key")

    try:
        from migrations.survey_tables import run_migration, check_tables_exist

        if check_tables_exist():
            return {
                "status": "success",
                "message": "Survey tables already exist",
                "created": False
            }

        logger.info("Starting survey tables migration...")
        success = run_migration()

        if success:
            return {
                "status": "success",
                "message": "Survey tables created successfully",
                "created": True
            }
        else:
            raise HTTPException(status_code=500, detail="Migration failed")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Survey migration error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/run-survey-seed")
async def run_survey_seed_simple(
    secret_key: str = Header(None, alias="X-Secret-Key")
):
    """
    Simple survey seeding endpoint - requires X-Secret-Key header matching SECRET_KEY env var.
    Seeds default survey templates.
    """
    import re
    expected_key = re.sub(r'\s+', '', os.getenv("SECRET_KEY", ""))
    provided_key = re.sub(r'\s+', '', secret_key or "")

    if not expected_key or provided_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid secret key")

    try:
        from seeds.seed_surveys import seed_surveys

        logger.info("Seeding survey templates...")
        success = seed_surveys(organization_id=1)

        if success:
            return {
                "status": "success",
                "message": "Survey templates seeded successfully",
                "templates": [
                    "Post-Close NPS Survey",
                    "Customer Satisfaction Survey (CSAT)",
                    "Customer Effort Score (CES)",
                    "Savings Validation Survey",
                    "Milestone Check-in Survey"
                ]
            }
        else:
            raise HTTPException(status_code=500, detail="Seeding failed")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Survey seeding error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/debug-survey-templates")
async def debug_survey_templates(key: str = ""):
    """
    Debug endpoint to check survey templates.
    Call with: GET /api/v1/migrations/debug-survey-templates?key=debug
    """
    if key != "debug":
        raise HTTPException(status_code=403, detail="Invalid key")

    try:
        from database import engine
        from sqlalchemy import text

        with engine.connect() as conn:
            # Get templates
            templates = conn.execute(text("""
                SELECT id, name, survey_type, status, trigger_type,
                       (SELECT COUNT(*) FROM survey_questions WHERE template_id = st.id) as question_count
                FROM survey_templates st
                ORDER BY id
            """)).fetchall()

            # Get question count
            total_questions = conn.execute(text("""
                SELECT COUNT(*) FROM survey_questions
            """)).scalar() or 0

            return {
                "status": "success",
                "templates_count": len(templates),
                "total_questions": total_questions,
                "templates": [
                    {
                        "id": t[0],
                        "name": t[1],
                        "type": t[2],
                        "status": t[3],
                        "trigger": t[4],
                        "questions": t[5]
                    }
                    for t in templates
                ]
            }

    except Exception as e:
        logger.error(f"Debug survey templates error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/run-content-marketing-migration")
async def run_content_marketing_migration(
    secret_key: str = Header(None, alias="X-Secret-Key")
):
    """
    Run the Content Marketing tables migration.
    Creates tables for brand voices, calendars, briefs, comments, etc.
    """
    import re
    expected_key = re.sub(r'\s+', '', os.getenv("SECRET_KEY", ""))
    provided_key = re.sub(r'\s+', '', secret_key or "")

    if not expected_key or provided_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid secret key")

    try:
        from database import engine
        from sqlalchemy import text

        # Check if tables exist
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'content_brand_voices'
                )
            """)).scalar()

            if result:
                return {
                    "status": "success",
                    "message": "Content Marketing tables already exist",
                    "created": False
                }

        # Run migration
        from migrations.add_content_marketing_tables import run_migration
        logger.info("Starting Content Marketing tables migration...")
        run_migration()

        # Verify tables were created
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'content_brand_voices'
                )
            """)).scalar()

            if result:
                return {
                    "status": "success",
                    "message": "Content Marketing tables created successfully",
                    "created": True,
                    "tables": [
                        "content_brand_voices",
                        "content_calendars",
                        "content_briefs",
                        "content_comments",
                        "content_approvals",
                        "seo_keywords",
                        "content_templates",
                        "personalization_tokens",
                        "content_publish_logs"
                    ]
                }
            else:
                raise HTTPException(status_code=500, detail="Migration ran but tables not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Content Marketing migration error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/seed-survey-templates")
async def seed_survey_templates(
    admin: Any = Depends(verify_admin_access)
):
    """
    Seed default survey templates (NPS, CSAT, CES, Savings Validation, Milestone).
    """
    try:
        from seeds.seed_surveys import seed_surveys

        logger.info("Seeding survey templates...")
        success = seed_surveys(organization_id=1)

        if success:
            return {
                "status": "success",
                "message": "Survey templates seeded successfully",
                "templates": [
                    "Post-Close NPS Survey",
                    "Customer Satisfaction Survey (CSAT)",
                    "Customer Effort Score (CES)",
                    "Savings Validation Survey",
                    "Milestone Check-in Survey"
                ]
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to seed survey templates"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Survey seed error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
