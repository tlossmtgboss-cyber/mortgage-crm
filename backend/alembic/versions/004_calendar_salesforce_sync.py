"""Create calendar Salesforce sync tables

Revision ID: 004_calendar_sf_sync
Revises: 003_estimate_parser
Create Date: 2026-01-11

Tables:
- calendar_events: CRM Calendar events (internal system)
- calendar_event_sync_map: Mapping between CRM and Salesforce events
- sync_watermarks: Track last sync times for polling loops
- calendar_sync_settings: Per-user sync configuration
- calendar_sync_event_logs: Audit log for sync operations
- salesforce_user_mappings: CRM to Salesforce user ID mapping
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = '004_calendar_sf_sync'
down_revision = '003_estimate_parser'
branch_labels = None
depends_on = None


def upgrade():
    # ========================================================================
    # CALENDAR EVENTS TABLE
    # ========================================================================
    op.create_table(
        'calendar_events',
        # Primary key - ULID/UUID format
        sa.Column('id', sa.String(36), primary_key=True),

        # Core event fields
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('start_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('end_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('timezone', sa.String(50), default='America/New_York'),
        sa.Column('all_day', sa.Boolean(), default=False),
        sa.Column('location', sa.String(500), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),

        # Ownership
        sa.Column('owner_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),

        # Attendees (JSON array of emails or CRM contact IDs)
        sa.Column('attendees', JSONB, default=list),

        # Related entity
        sa.Column('related_entity_type', sa.String(50), nullable=True),
        sa.Column('related_entity_id', sa.String(50), nullable=True),

        # Status and visibility
        sa.Column('status', sa.String(20), default='scheduled'),  # scheduled, canceled
        sa.Column('visibility', sa.String(20), default='internal'),  # private, public, internal

        # Sync metadata
        sa.Column('source_system', sa.String(20), default='crm'),  # crm, salesforce, outlook
        sa.Column('last_modified_by_system', sa.String(20), default='crm'),
        sa.Column('last_modified_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sync_status', sa.String(20), default='pending'),  # pending, syncing, synced, failed
        sa.Column('sync_error', sa.Text(), nullable=True),

        # Fingerprint hash (SHA-256)
        sa.Column('fingerprint_hash', sa.String(64), nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )

    # Indexes for calendar_events
    op.create_index('ix_calendar_events_owner', 'calendar_events', ['owner_user_id'])
    op.create_index('ix_calendar_events_start', 'calendar_events', ['start_at'])
    op.create_index('ix_calendar_events_sync_status', 'calendar_events', ['sync_status'])
    op.create_index(
        'ix_calendar_events_pending_sync',
        'calendar_events',
        ['last_modified_at'],
        postgresql_where=sa.text("sync_status = 'pending'")
    )

    # ========================================================================
    # CALENDAR EVENT SYNC MAP TABLE
    # ========================================================================
    op.create_table(
        'calendar_event_sync_map',
        # Primary key is CRM event ID
        sa.Column('crm_event_id', sa.String(36), sa.ForeignKey('calendar_events.id', ondelete='CASCADE'), primary_key=True),

        # Salesforce Event ID (18-character)
        sa.Column('salesforce_event_id', sa.String(18), unique=True, nullable=True),

        # Salesforce owner
        sa.Column('salesforce_owner_id', sa.String(18), nullable=True),

        # External calendar ID (Outlook)
        sa.Column('external_calendar_id', sa.String(255), nullable=True),

        # Fingerprint for echo prevention
        sa.Column('fingerprint_hash', sa.String(64), nullable=False),

        # Push/Pull tracking
        sa.Column('last_pushed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_pulled_at', sa.DateTime(timezone=True), nullable=True),

        # Last Salesforce modification time
        sa.Column('last_seen_salesforce_modified_at', sa.DateTime(timezone=True), nullable=True),

        # Version for optimistic locking
        sa.Column('sync_version', sa.Integer(), default=1),

        # Lock token for deduplication
        sa.Column('lock_token', sa.String(64), nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )

    # Indexes for sync_map
    op.create_index('ix_sync_map_sf_event', 'calendar_event_sync_map', ['salesforce_event_id'])
    op.create_index('ix_sync_map_last_pulled', 'calendar_event_sync_map', ['last_pulled_at'])
    op.create_index('ix_sync_map_pending_push', 'calendar_event_sync_map', ['last_pushed_at'])

    # ========================================================================
    # SYNC WATERMARKS TABLE
    # ========================================================================
    op.create_table(
        'sync_watermarks',
        # Sync type identifier (e.g., 'calendar_push', 'calendar_pull')
        sa.Column('sync_type', sa.String(100), primary_key=True),

        # Last successful sync timestamp
        sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=False),

        # Additional metadata
        sa.Column('records_processed', sa.Integer(), default=0),
        sa.Column('last_error', sa.Text(), nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )

    # ========================================================================
    # CALENDAR SYNC SETTINGS TABLE
    # ========================================================================
    op.create_table(
        'calendar_sync_settings',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), unique=True, nullable=False),

        # Integration profile link
        sa.Column('integration_profile_id', sa.Integer(), sa.ForeignKey('integration_profiles.id'), nullable=True),

        # Sync mode
        sa.Column('sync_mode', sa.String(50), default='crm_only'),  # crm_only, all_salesforce_events

        # Conflict resolution policy
        sa.Column('conflict_policy', sa.String(50), default='last_write_wins'),

        # Echo prevention window
        sa.Column('echo_ignore_window_seconds', sa.Integer(), default=90),

        # Sync intervals
        sa.Column('push_interval_seconds', sa.Integer(), default=60),
        sa.Column('pull_interval_seconds', sa.Integer(), default=60),

        # Batch size
        sa.Column('batch_size', sa.Integer(), default=100),

        # Max retries
        sa.Column('max_retries', sa.Integer(), default=5),

        # Delete policy
        sa.Column('delete_policy', sa.String(50), default='soft_cancel'),

        # Immediate push flag
        sa.Column('enable_immediate_push', sa.Boolean(), default=True),

        # Salesforce API version
        sa.Column('salesforce_api_version', sa.String(10), default='v60.0'),

        # Sync enabled
        sa.Column('sync_enabled', sa.Boolean(), default=True),

        # Last sync status
        sa.Column('last_push_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_pull_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_sync_error', sa.Text(), nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )

    # ========================================================================
    # CALENDAR SYNC EVENT LOGS TABLE
    # ========================================================================
    op.create_table(
        'calendar_sync_event_logs',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),

        # Event references
        sa.Column('crm_event_id', sa.String(36), nullable=True),
        sa.Column('salesforce_event_id', sa.String(18), nullable=True),

        # Sync details
        sa.Column('direction', sa.String(10), nullable=False),  # push, pull
        sa.Column('operation', sa.String(20), nullable=False),  # create, update, delete

        # Content hashes
        sa.Column('fingerprint_before', sa.String(64), nullable=True),
        sa.Column('fingerprint_after', sa.String(64), nullable=True),

        # Result
        sa.Column('result', sa.String(20), nullable=False),  # success, failed, skipped, echo
        sa.Column('error_message', sa.Text(), nullable=True),

        # Performance
        sa.Column('duration_ms', sa.Integer(), nullable=True),

        # Source system
        sa.Column('source_system', sa.String(20), nullable=True),

        # Timestamp
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )

    # Indexes for sync_event_logs
    op.create_index('ix_sync_log_timestamp', 'calendar_sync_event_logs', ['created_at'])
    op.create_index('ix_sync_log_crm_event', 'calendar_sync_event_logs', ['crm_event_id'])
    op.create_index('ix_sync_log_direction', 'calendar_sync_event_logs', ['direction'])

    # ========================================================================
    # SALESFORCE USER MAPPINGS TABLE
    # ========================================================================
    op.create_table(
        'salesforce_user_mappings',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('crm_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False, unique=True),
        sa.Column('salesforce_user_id', sa.String(18), nullable=False, unique=True),

        # User email for fallback matching
        sa.Column('email', sa.String(255), nullable=True),

        # Active flag
        sa.Column('is_active', sa.Boolean(), default=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),

        # Unique constraint
        sa.UniqueConstraint('crm_user_id', 'salesforce_user_id', name='uq_user_mapping'),
    )

    # Index for salesforce_user_mappings
    op.create_index('ix_sf_user_mapping_sf_id', 'salesforce_user_mappings', ['salesforce_user_id'])

    # ========================================================================
    # INITIALIZE WATERMARKS
    # ========================================================================
    # Insert default watermarks (7 days ago)
    op.execute("""
        INSERT INTO sync_watermarks (sync_type, last_synced_at, records_processed)
        VALUES
            ('calendar_push', NOW() - INTERVAL '7 days', 0),
            ('calendar_pull', NOW() - INTERVAL '7 days', 0)
        ON CONFLICT (sync_type) DO NOTHING
    """)


def downgrade():
    op.drop_table('salesforce_user_mappings')
    op.drop_table('calendar_sync_event_logs')
    op.drop_table('calendar_sync_settings')
    op.drop_table('sync_watermarks')
    op.drop_table('calendar_event_sync_map')
    op.drop_table('calendar_events')
