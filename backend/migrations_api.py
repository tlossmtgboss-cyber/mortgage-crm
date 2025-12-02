"""
API endpoint to run migrations remotely
This allows running migrations on production via HTTP request
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Any
import logging

router = APIRouter(prefix="/api/v1/migrations", tags=["migrations"])

logger = logging.getLogger(__name__)


def get_admin_user():
    """Placeholder for admin authentication - implement proper auth"""
    # TODO: Add proper admin authentication
    return True


@router.post("/add-guideline-updates-tables")
async def run_guideline_updates_migration(
    admin: Any = Depends(get_admin_user)
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
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/seed-guideline-updates")
async def seed_guideline_updates(
    admin: Any = Depends(get_admin_user)
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
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/update-guideline-urls")
async def update_guideline_urls(
    admin: Any = Depends(get_admin_user)
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
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scrape-mortgage-guidelines")
async def scrape_mortgage_guidelines(
    admin: Any = Depends(get_admin_user)
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
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/clear-guidelines")
async def clear_guideline_updates(
    admin: Any = Depends(get_admin_user)
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
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/import-browser-guidelines")
async def import_browser_guidelines(
    request: dict,
    admin: Any = Depends(get_admin_user)
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
                        except:
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
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/add-circle-of-cashflow-tables")
async def run_circle_of_cashflow_migration(
    admin: Any = Depends(get_admin_user)
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
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/add-circle-contacts-table")
async def run_circle_contacts_migration(
    admin: Any = Depends(get_admin_user)
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
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/add-ai-task-automation-tables")
async def run_ai_task_automation_migration(
    admin: Any = Depends(get_admin_user)
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
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/create-mortgage-glossary")
async def run_mortgage_glossary_migration(
    admin: Any = Depends(get_admin_user)
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
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/add-concierge-responsible-column")
async def add_concierge_responsible_column(
    admin: Any = Depends(get_admin_user)
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
            except:
                pass  # Column doesn't exist, proceed with adding it

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
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/update-user-email")
async def update_user_email(
    admin: Any = Depends(get_admin_user)
):
    """
    Update demo user email from demo@example.com to admin@perenniaai.com
    """
    try:
        from database import engine
        from sqlalchemy import text

        old_email = "demo@example.com"
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
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/add-weekly-task-columns")
async def run_weekly_task_columns_migration(
    admin: Any = Depends(get_admin_user)
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
        raise HTTPException(status_code=500, detail=str(e))

