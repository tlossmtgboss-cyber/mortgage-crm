"""Add password_changed_at column to users table

Revision ID: 020_password_changed_at
Revises: 019_reconcile
Create Date: 2026-06-18

Adds users.password_changed_at (TIMESTAMPTZ) required by the User ORM model
(database/models/core.py). Missing column caused ProgrammingError on every
db.query(User) call, breaking all login endpoints with HTTP 500.
"""
import sqlalchemy as sa
from alembic import op

revision = "020_password_changed_at"
down_revision = "019_reconcile"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()

    # SQLite (dev): plain ALTER TABLE — no IF NOT EXISTS support
    if bind.dialect.name == "sqlite":
        try:
            op.add_column("users", sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True))
            print("Added users.password_changed_at (SQLite)")
        except Exception as e:
            print(f"users.password_changed_at already exists (SQLite): {e}")
        return

    # PostgreSQL: idempotent via IF NOT EXISTS
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_changed_at TIMESTAMP WITH TIME ZONE")
    print("Ensured users.password_changed_at exists")


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return  # SQLite does not support DROP COLUMN
    op.drop_column("users", "password_changed_at")
