"""
Migration: Add social media and production fields to mm_candidates
For recruit detail pages with RETR production data and social media integration
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/perennia")


def run_migration():
    engine = create_engine(DATABASE_URL)

    with engine.connect() as conn:
        # Add production fields from RETR
        production_columns = [
            ("annual_volume", "NUMERIC(15,2)", "Annual loan volume from RETR"),
            ("annual_units", "INTEGER", "Annual loan units from RETR"),
            ("avg_loan_size", "NUMERIC(12,2)", "Average loan size"),
            ("nmls_id", "VARCHAR(20)", "NMLS ID"),
            ("license_states", "JSONB", "List of licensed states"),
            ("production_history", "JSONB", "Historical production data by year"),
            ("current_company", "VARCHAR(255)", "Current company name"),
            ("current_title", "VARCHAR(100)", "Current job title"),
        ]

        # Add social media fields
        social_columns = [
            ("facebook_url", "VARCHAR(500)", "Facebook profile URL"),
            ("instagram_url", "VARCHAR(500)", "Instagram profile URL"),
            ("twitter_url", "VARCHAR(500)", "Twitter/X profile URL"),
            ("social_profiles", "JSONB", "All social media profiles with metadata"),
            ("social_posts", "JSONB", "Cached social media posts for display"),
            ("social_last_synced", "TIMESTAMP", "Last social media sync timestamp"),
        ]

        # Add profile enhancement fields
        profile_columns = [
            ("headshot_url", "VARCHAR(500)", "Profile headshot image URL"),
            ("bio", "TEXT", "Professional bio/summary"),
            ("specialties", "JSONB", "List of loan product specialties"),
            ("market_areas", "JSONB", "Geographic market areas served"),
            ("education", "JSONB", "Education history"),
            ("certifications", "JSONB", "Professional certifications"),
            ("awards", "JSONB", "Awards and recognitions"),
            ("testimonials", "JSONB", "Client testimonials"),
        ]

        all_columns = production_columns + social_columns + profile_columns

        for col_name, col_type, description in all_columns:
            try:
                conn.execute(text(f"""
                    ALTER TABLE mm_candidates
                    ADD COLUMN IF NOT EXISTS {col_name} {col_type}
                """))
                print(f"  Added column: {col_name} ({description})")
            except Exception as e:
                if "already exists" in str(e).lower():
                    print(f"  Column {col_name} already exists")
                else:
                    print(f"  Warning adding {col_name}: {e}")

        conn.commit()
        print("\nMigration completed successfully!")

        # Show table structure
        result = conn.execute(text("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'mm_candidates'
            ORDER BY ordinal_position
        """))

        print("\nUpdated mm_candidates columns:")
        for row in result:
            print(f"  - {row.column_name}: {row.data_type}")


if __name__ == "__main__":
    run_migration()
