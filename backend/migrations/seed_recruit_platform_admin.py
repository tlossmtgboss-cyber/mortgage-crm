"""
Seed initial recruit platform admin: tloss@cmgfi.com
Creates a default organization (slug='perennia-default') and the platform admin user.
Idempotent — safe to run multiple times.
"""
import logging
import bcrypt
from sqlalchemy import text

logger = logging.getLogger(__name__)


def run_migration(engine=None):
    if engine is None:
        from database import engine as db_engine
        engine = db_engine

    with engine.begin() as conn:
        # 1. Ensure the default organization exists
        row = conn.execute(text(
            "SELECT id FROM organizations WHERE slug = 'perennia-default'"
        )).fetchone()

        if row is None:
            result = conn.execute(text("""
                INSERT INTO organizations (name, slug, subscription_tier, is_active)
                VALUES ('Perennia AI', 'perennia-default', 'enterprise', TRUE)
                RETURNING id
            """))
            org_id = result.fetchone()[0]
            logger.info(f"✅ Created organization 'perennia-default' (id={org_id})")
        else:
            org_id = row[0]
            logger.info(f"Organization 'perennia-default' already exists (id={org_id})")

        # 2. Ensure the platform admin user exists
        user_row = conn.execute(text(
            "SELECT id, role FROM users WHERE email = 'tloss@cmgfi.com'"
        )).fetchone()

        if user_row is None:
            hashed_pw = bcrypt.hashpw("Password1!".encode(), bcrypt.gensalt()).decode()
            conn.execute(text("""
                INSERT INTO users (
                    email, hashed_password, role, permission_role,
                    first_name, last_name, organization_id,
                    is_active, email_verified, onboarding_completed
                )
                VALUES (
                    'tloss@cmgfi.com', :pw, 'platform_admin', 'admin',
                    'Timothy', 'Loss', :org_id,
                    TRUE, TRUE, TRUE
                )
            """), {"pw": hashed_pw, "org_id": org_id})
            logger.info("✅ Created platform admin user tloss@cmgfi.com")
        else:
            user_id, current_role = user_row[0], user_row[1]
            if current_role != "platform_admin":
                conn.execute(text(
                    "UPDATE users SET role = 'platform_admin' WHERE id = :uid"
                ), {"uid": user_id})
                logger.info(f"✅ Updated tloss@cmgfi.com role to platform_admin (was: {current_role})")
            else:
                logger.info("Platform admin tloss@cmgfi.com already exists with correct role")

    return {"status": "success"}


def rollback(engine=None):
    if engine is None:
        from database import engine as db_engine
        engine = db_engine

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM users WHERE email = 'tloss@cmgfi.com'"))
        conn.execute(text("DELETE FROM organizations WHERE slug = 'perennia-default'"))
    logger.info("Rolled back seed_recruit_platform_admin")
    return {"status": "rolled_back"}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(run_migration())
