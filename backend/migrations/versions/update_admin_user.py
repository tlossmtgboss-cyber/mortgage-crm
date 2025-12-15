"""Update admin user email

This migration updates the default user to the production admin account.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'update_admin_user_001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Update demo user to admin
    op.execute("""
        UPDATE users
        SET email = 'admin@perenniaai.com',
            full_name = 'Admin'
        WHERE email = 'demo@example.com'
    """)


def downgrade():
    # Revert to demo user (if needed)
    op.execute("""
        UPDATE users
        SET email = 'demo@example.com',
            full_name = 'Demo User'
        WHERE email = 'admin@perenniaai.com'
    """)
