"""
Create recruit_social_posts and candidate_linkedin_posts tables.

recruit_social_posts: stores social media posts created by recruiters
candidate_linkedin_posts: caches LinkedIn post data for candidates

Both tables are referenced by recruit_social_routes.py but were never created.
"""

import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)


def run_migration(engine):
    """Create recruit_social_posts and candidate_linkedin_posts tables if they don't exist."""
    with engine.connect() as conn:
        # 1. Create recruit_social_posts table
        result = conn.execute(text("""
            SELECT 1 FROM information_schema.tables
            WHERE table_name = 'recruit_social_posts'
        """))
        if not result.fetchone():
            logger.info("Creating recruit_social_posts table...")
            conn.execute(text("""
                CREATE TABLE recruit_social_posts (
                    id SERIAL PRIMARY KEY,
                    content TEXT NOT NULL,
                    platforms VARCHAR(255),
                    image_url TEXT,
                    scheduled_at TIMESTAMP,
                    posted_at TIMESTAMP,
                    status VARCHAR(50) DEFAULT 'draft',
                    engagement_data JSONB,
                    organization_id INTEGER NOT NULL,
                    created_by INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """))
            conn.execute(text("""
                CREATE INDEX ix_recruit_social_posts_org_id
                ON recruit_social_posts (organization_id)
            """))
            conn.execute(text("""
                CREATE INDEX ix_recruit_social_posts_status
                ON recruit_social_posts (status)
            """))
            logger.info("recruit_social_posts table created")
        else:
            logger.info("recruit_social_posts already exists, skipping")

        # 2. Create candidate_linkedin_posts table
        result = conn.execute(text("""
            SELECT 1 FROM information_schema.tables
            WHERE table_name = 'candidate_linkedin_posts'
        """))
        if not result.fetchone():
            logger.info("Creating candidate_linkedin_posts table...")
            conn.execute(text("""
                CREATE TABLE candidate_linkedin_posts (
                    id SERIAL PRIMARY KEY,
                    candidate_id INTEGER NOT NULL,
                    post_content TEXT,
                    post_url TEXT,
                    likes INTEGER DEFAULT 0,
                    comments INTEGER DEFAULT 0,
                    shares INTEGER DEFAULT 0,
                    posted_at TIMESTAMP,
                    cached_at TIMESTAMP DEFAULT NOW()
                )
            """))
            conn.execute(text("""
                CREATE INDEX ix_candidate_linkedin_posts_candidate_id
                ON candidate_linkedin_posts (candidate_id)
            """))
            logger.info("candidate_linkedin_posts table created")
        else:
            logger.info("candidate_linkedin_posts already exists, skipping")

        conn.commit()
        logger.info("Social recruiting tables migration complete")
