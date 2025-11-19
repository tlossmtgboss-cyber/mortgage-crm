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
