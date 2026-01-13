"""Add multi-role user system tables

Revision ID: 004_multi_role
Revises: 003_estimate_parser_cache
Create Date: 2026-01-13

This migration creates tables to support users having multiple roles:
- user_assigned_roles: Many-to-many relationship between users and roles
- user_active_role: Tracks which role the user is currently viewing as

Also migrates existing users from onboarding_user_profiles to new system.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic
revision = '004_multi_role'
down_revision = '003_estimate_parser'
branch_labels = None
depends_on = None


def upgrade():
    """Create multi-role system tables and migrate existing data."""

    # 1. Create user_assigned_roles table
    op.create_table(
        'user_assigned_roles',
        sa.Column('id', sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('role_id', sa.Integer(), nullable=False),
        sa.Column('assigned_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.Column('assigned_by', sa.Integer(), nullable=True),
        sa.Column('is_primary', sa.Boolean(), server_default='false'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['role_id'], ['onboarding_roles.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['assigned_by'], ['users.id'], ondelete='SET NULL'),
        sa.UniqueConstraint('user_id', 'role_id', name='uq_user_assigned_roles_user_role')
    )

    op.create_index('idx_user_assigned_roles_user_id', 'user_assigned_roles', ['user_id'])
    op.create_index('idx_user_assigned_roles_role_id', 'user_assigned_roles', ['role_id'])

    # 2. Create user_active_role table
    op.create_table(
        'user_active_role',
        sa.Column('id', sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column('user_id', sa.Integer(), nullable=False, unique=True),
        sa.Column('active_role_id', sa.Integer(), nullable=False),
        sa.Column('switched_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['active_role_id'], ['onboarding_roles.id'], ondelete='RESTRICT'),
    )

    op.create_index('idx_user_active_role_user_id', 'user_active_role', ['user_id'])

    # 3. Migrate existing users from onboarding_user_profiles
    # This runs raw SQL for data migration
    connection = op.get_bind()

    # Insert existing role assignments
    connection.execute(text("""
        INSERT INTO user_assigned_roles (user_id, role_id, assigned_at, is_primary)
        SELECT
            oup.user_id,
            oup.role_id,
            COALESCE(oup.created_at, NOW()),
            TRUE
        FROM onboarding_user_profiles oup
        WHERE oup.user_id IS NOT NULL
            AND oup.role_id IS NOT NULL
            AND NOT EXISTS (
                SELECT 1 FROM user_assigned_roles uar
                WHERE uar.user_id = oup.user_id AND uar.role_id = oup.role_id
            )
    """))

    # Set active roles for migrated users
    connection.execute(text("""
        INSERT INTO user_active_role (user_id, active_role_id, switched_at)
        SELECT
            uar.user_id,
            uar.role_id,
            NOW()
        FROM user_assigned_roles uar
        WHERE uar.is_primary = TRUE
            AND NOT EXISTS (
                SELECT 1 FROM user_active_role uac
                WHERE uac.user_id = uar.user_id
            )
    """))


def downgrade():
    """Remove multi-role system tables."""
    op.drop_table('user_active_role')
    op.drop_table('user_assigned_roles')
