"""
Migration: Add Realtor Roles
Adds Buyer Agent, Buyers Agent Closing Coordinator, Listing Agent,
and Listing Agent Closing Coordinator roles to the roles table.
"""

from sqlalchemy import create_engine, text
import os

DATABASE_URL = os.getenv("DATABASE_URL")


def run_migration():
    """Run the realtor roles migration."""
    if not DATABASE_URL:
        print("DATABASE_URL not set. Skipping migration.")
        return

    # Fix postgres:// to postgresql://
    db_url = DATABASE_URL
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    engine = create_engine(db_url)

    new_roles = [
        ("Buyer Agent", "Real estate agent representing the buyer in a purchase transaction"),
        ("Buyers Agent Closing Coordinator", "Coordinates closing activities on behalf of the buyer's real estate agent"),
        ("Listing Agent", "Real estate agent representing the seller in a purchase transaction"),
        ("Listing Agent Closing Coordinator", "Coordinates closing activities on behalf of the listing agent"),
    ]

    with engine.connect() as conn:
        for role_name, description in new_roles:
            # Check if role already exists
            result = conn.execute(text("""
                SELECT id FROM roles WHERE name = :name
            """), {"name": role_name})

            if result.fetchone():
                print(f"Role '{role_name}' already exists. Skipping.")
                continue

            # Insert new role
            conn.execute(text("""
                INSERT INTO roles (name, description, is_active, created_at, updated_at)
                VALUES (:name, :description, true, NOW(), NOW())
            """), {"name": role_name, "description": description})

            print(f"Created role: {role_name}")

        conn.commit()
        print("Migration completed successfully!")


if __name__ == "__main__":
    run_migration()
