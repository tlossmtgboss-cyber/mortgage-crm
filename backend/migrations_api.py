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
