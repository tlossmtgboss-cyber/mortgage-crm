"""
Migration: Add Dynamic Role Support to Workflow Tables
Adds columns to support dynamic roles from the Role table instead of hardcoded enums.

New columns:
- workflow_day_configs.role_responsibilities (JSON) - Stores {role_id: boolean} mapping
- workflow_role_assignments.role_id (Integer FK) - Links to roles table
"""

import logging

logger = logging.getLogger(__name__)


async def run_migration(db, is_postgres=True):
    """Add dynamic role columns to workflow tables"""

    try:
        # Add role_responsibilities JSON column to workflow_day_configs
        try:
            if is_postgres:
                await db.execute("""
                    ALTER TABLE workflow_day_configs
                    ADD COLUMN IF NOT EXISTS role_responsibilities JSONB DEFAULT '{}'::jsonb
                """)
            else:
                await db.execute("""
                    ALTER TABLE workflow_day_configs
                    ADD COLUMN role_responsibilities TEXT DEFAULT '{}'
                """)
            logger.info("Added role_responsibilities column to workflow_day_configs")
        except Exception as e:
            if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                logger.info("role_responsibilities column already exists")
            else:
                raise

        # Add role_id column to workflow_role_assignments
        try:
            await db.execute("""
                ALTER TABLE workflow_role_assignments
                ADD COLUMN IF NOT EXISTS role_id INTEGER REFERENCES roles(id)
            """)
            logger.info("Added role_id column to workflow_role_assignments")
        except Exception as e:
            if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                logger.info("role_id column already exists")
            else:
                raise

        # Make the old 'role' enum column nullable since we now use role_id
        try:
            await db.execute("""
                ALTER TABLE workflow_role_assignments
                ALTER COLUMN role DROP NOT NULL
            """)
            logger.info("Made 'role' column nullable in workflow_role_assignments")
        except Exception as e:
            if "already" in str(e).lower():
                logger.info("role column already nullable")
            else:
                # This might fail if column is already nullable, that's ok
                logger.warning(f"Could not make role column nullable: {e}")

        # Create index for faster lookups
        try:
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_workflow_role_assignments_role_id
                ON workflow_role_assignments(role_id)
            """)
            logger.info("Created index on role_id")
        except Exception as e:
            if "already exists" in str(e).lower():
                logger.info("Index already exists")
            else:
                logger.warning(f"Could not create index: {e}")

        await db.commit()
        logger.info("Migration completed successfully")
        return True

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        await db.rollback()
        raise


def run_migration_sync(db, is_postgres=True):
    """Synchronous version for FastAPI route"""

    try:
        # Add role_responsibilities JSON column to workflow_day_configs
        try:
            if is_postgres:
                db.execute("""
                    ALTER TABLE workflow_day_configs
                    ADD COLUMN IF NOT EXISTS role_responsibilities JSONB DEFAULT '{}'::jsonb
                """)
            else:
                db.execute("""
                    ALTER TABLE workflow_day_configs
                    ADD COLUMN role_responsibilities TEXT DEFAULT '{}'
                """)
            logger.info("Added role_responsibilities column to workflow_day_configs")
        except Exception as e:
            if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                logger.info("role_responsibilities column already exists")
            else:
                raise

        # Add role_id column to workflow_role_assignments
        try:
            db.execute("""
                ALTER TABLE workflow_role_assignments
                ADD COLUMN IF NOT EXISTS role_id INTEGER REFERENCES roles(id)
            """)
            logger.info("Added role_id column to workflow_role_assignments")
        except Exception as e:
            if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                logger.info("role_id column already exists")
            else:
                raise

        # Make the old 'role' enum column nullable since we now use role_id
        try:
            db.execute("""
                ALTER TABLE workflow_role_assignments
                ALTER COLUMN role DROP NOT NULL
            """)
            logger.info("Made 'role' column nullable in workflow_role_assignments")
        except Exception as e:
            if "already" in str(e).lower():
                logger.info("role column already nullable")
            else:
                logger.warning(f"Could not make role column nullable: {e}")

        # Create index for faster lookups
        try:
            db.execute("""
                CREATE INDEX IF NOT EXISTS idx_workflow_role_assignments_role_id
                ON workflow_role_assignments(role_id)
            """)
            logger.info("Created index on role_id")
        except Exception as e:
            if "already exists" in str(e).lower():
                logger.info("Index already exists")
            else:
                logger.warning(f"Could not create index: {e}")

        db.commit()
        logger.info("Migration completed successfully")
        return True

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        db.rollback()
        raise
