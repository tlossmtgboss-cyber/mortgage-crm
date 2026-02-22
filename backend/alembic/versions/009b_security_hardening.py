"""Security hardening: account lockout, MFA, API key scopes

Revision ID: 009b_security
Revises: 009_enterprise_readiness_p0
Create Date: 2026-02-19

Enterprise Readiness Checks:
- 4.4: Account lockout after failed login attempts
- 4.6: MFA via TOTP (mfa_secret, mfa_backup_codes, mfa_enabled_at)
- 4.11: API key scopes for fine-grained access control

Notes:
- mfa_enabled may already exist from add_account_management_tables migration
- All new columns are nullable to avoid breaking existing rows
"""
import logging

from alembic import op
import sqlalchemy as sa

logger = logging.getLogger(__name__)

# revision identifiers, used by Alembic
revision = '009b_security'
down_revision = '009_enterprise_readiness_p0'
branch_labels = None
depends_on = None


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table (PostgreSQL)."""
    result = bind.execute(sa.text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public'
            AND table_name = :table_name
            AND column_name = :column_name
        )
    """), {"table_name": table_name, "column_name": column_name})
    return result.scalar()


def _table_exists(bind, table_name: str) -> bool:
    """Check if a table exists (PostgreSQL)."""
    result = bind.execute(sa.text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name = :table_name
        )
    """), {"table_name": table_name})
    return result.scalar()


def upgrade():
    """Add security hardening columns to users and api_keys tables."""
    bind = op.get_bind()

    # Skip for SQLite (local development)
    if bind.dialect.name == 'sqlite':
        print("SQLite detected - using simplified migration")
        _upgrade_sqlite()
        return

    # =========================================================================
    # Users table: Account lockout fields (Check 4.4)
    # =========================================================================
    if _table_exists(bind, 'users'):
        # failed_login_attempts
        if not _column_exists(bind, 'users', 'failed_login_attempts'):
            op.add_column('users', sa.Column('failed_login_attempts', sa.Integer(), nullable=True, server_default='0'))
            print("Added users.failed_login_attempts")

        # locked_until
        if not _column_exists(bind, 'users', 'locked_until'):
            op.add_column('users', sa.Column('locked_until', sa.DateTime(), nullable=True))
            print("Added users.locked_until")

        # last_failed_login_at
        if not _column_exists(bind, 'users', 'last_failed_login_at'):
            op.add_column('users', sa.Column('last_failed_login_at', sa.DateTime(), nullable=True))
            print("Added users.last_failed_login_at")

        # =====================================================================
        # Users table: MFA fields (Check 4.6)
        # =====================================================================
        # mfa_secret
        if not _column_exists(bind, 'users', 'mfa_secret'):
            op.add_column('users', sa.Column('mfa_secret', sa.String(), nullable=True))
            print("Added users.mfa_secret")

        # mfa_enabled - may already exist from account_management migration
        if not _column_exists(bind, 'users', 'mfa_enabled'):
            op.add_column('users', sa.Column('mfa_enabled', sa.Boolean(), nullable=True, server_default='false'))
            print("Added users.mfa_enabled")
        else:
            print("users.mfa_enabled already exists - skipping")

        # mfa_backup_codes
        if not _column_exists(bind, 'users', 'mfa_backup_codes'):
            op.add_column('users', sa.Column('mfa_backup_codes', sa.JSON(), nullable=True))
            print("Added users.mfa_backup_codes")

        # mfa_enabled_at
        if not _column_exists(bind, 'users', 'mfa_enabled_at'):
            op.add_column('users', sa.Column('mfa_enabled_at', sa.DateTime(), nullable=True))
            print("Added users.mfa_enabled_at")
    else:
        print("users table not found - skipping user columns")

    # =========================================================================
    # API Keys table: Scope fields (Check 4.11)
    # =========================================================================
    if _table_exists(bind, 'api_keys'):
        # scopes
        if not _column_exists(bind, 'api_keys', 'scopes'):
            op.add_column('api_keys', sa.Column('scopes', sa.JSON(), nullable=True, server_default='[]'))
            print("Added api_keys.scopes")

        # description
        if not _column_exists(bind, 'api_keys', 'description'):
            op.add_column('api_keys', sa.Column('description', sa.String(), nullable=True))
            print("Added api_keys.description")

        # expires_at
        if not _column_exists(bind, 'api_keys', 'expires_at'):
            op.add_column('api_keys', sa.Column('expires_at', sa.DateTime(), nullable=True))
            print("Added api_keys.expires_at")
    else:
        print("api_keys table not found - skipping API key columns")

    print("Security hardening migration complete")


def _upgrade_sqlite():
    """Simplified migration for SQLite (no IF NOT EXISTS support)."""
    # SQLite doesn't support information_schema, so we try/except each column
    columns_to_add = [
        ('users', 'failed_login_attempts', 'INTEGER DEFAULT 0'),
        ('users', 'locked_until', 'TIMESTAMP'),
        ('users', 'last_failed_login_at', 'TIMESTAMP'),
        ('users', 'mfa_secret', 'VARCHAR'),
        ('users', 'mfa_enabled', 'BOOLEAN DEFAULT 0'),
        ('users', 'mfa_backup_codes', 'JSON'),
        ('users', 'mfa_enabled_at', 'TIMESTAMP'),
        ('api_keys', 'scopes', 'JSON DEFAULT \'[]\''),
        ('api_keys', 'description', 'VARCHAR'),
        ('api_keys', 'expires_at', 'TIMESTAMP'),
    ]

    bind = op.get_bind()
    for table, column, col_type in columns_to_add:
        try:
            bind.execute(sa.text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
            print(f"Added {table}.{column}")
        except Exception as e:
            print(f"{table}.{column} already exists - skipping: {e}")


def downgrade():
    """Remove security hardening columns."""
    bind = op.get_bind()

    if bind.dialect.name == 'sqlite':
        print("SQLite does not support DROP COLUMN - skipping downgrade")
        return

    # Remove API key columns
    if _table_exists(bind, 'api_keys'):
        for col in ['scopes', 'description', 'expires_at']:
            if _column_exists(bind, 'api_keys', col):
                op.drop_column('api_keys', col)

    # Remove user MFA columns
    if _table_exists(bind, 'users'):
        for col in ['mfa_secret', 'mfa_backup_codes', 'mfa_enabled_at']:
            if _column_exists(bind, 'users', col):
                op.drop_column('users', col)
        # Note: We do NOT drop mfa_enabled as it may have existed before this migration

        # Remove lockout columns
        for col in ['failed_login_attempts', 'locked_until', 'last_failed_login_at']:
            if _column_exists(bind, 'users', col):
                op.drop_column('users', col)

    print("Security hardening downgrade complete")
