"""
Calendar Sync Service - CRM Calendar ↔ Salesforce Events Bi-Directional Sync

Implements 1-minute bi-directional sync between CRM Calendar and Salesforce Events.
Salesforce serves as the bridge layer to Outlook calendars.

Key Features:
- 60-second push loop (CRM → Salesforce)
- 60-second pull loop (Salesforce → CRM)
- Fingerprint-based change detection
- Echo/loop prevention
- Exponential backoff retry
- Watermark-based incremental polling
"""
import hashlib
import json
import logging
import asyncio
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any, Tuple
import httpx

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from calendar_sync_models import (
    CalendarEvent,
    CalendarEventSyncMap,
    SyncWatermark,
    CalendarSyncSettings,
    CalendarSyncEventLog,
    SalesforceUserMapping,
    CalendarEventStatus,
    CalendarEventSourceSystem,
    CalendarSyncStatus,
    ConflictResolutionPolicy,
)
from salesforce_integration_models import IntegrationProfile
from services.salesforce.oauth_service import salesforce_oauth

logger = logging.getLogger(__name__)


# ============================================================================
# CONSTANTS
# ============================================================================

ECHO_IGNORE_WINDOW_SECONDS = 90  # Default window to ignore echoes
SALESFORCE_API_VERSION = "v60.0"
BATCH_SIZE = 200  # Salesforce SOQL limit
MAX_RETRY_ATTEMPTS = 5
RETRY_BACKOFF_BASE = 3  # Exponential backoff: 5s, 15s, 45s, 135s, 405s

RETRYABLE_ERRORS = [
    'UNABLE_TO_LOCK_ROW',
    'REQUEST_LIMIT_EXCEEDED',
    'QUERY_TIMEOUT',
    'SERVER_UNAVAILABLE',
]


# ============================================================================
# SYNC RESULT
# ============================================================================

class CalendarSyncResult:
    """Result of a calendar sync operation"""

    def __init__(self):
        self.success = False
        self.records_processed = 0
        self.records_succeeded = 0
        self.records_failed = 0
        self.records_skipped = 0
        self.echo_prevented = 0
        self.errors: List[Dict[str, str]] = []
        self.duration_ms = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'success': self.success,
            'records_processed': self.records_processed,
            'records_succeeded': self.records_succeeded,
            'records_failed': self.records_failed,
            'records_skipped': self.records_skipped,
            'echo_prevented': self.echo_prevented,
            'errors': self.errors,
            'duration_ms': self.duration_ms
        }


# ============================================================================
# FINGERPRINT COMPUTATION
# ============================================================================

def compute_fingerprint(event_data: Dict[str, Any]) -> str:
    """
    Compute a deterministic SHA-256 hash for change detection.

    Normalizes event content to ensure consistent hashing regardless
    of whitespace, casing, or timestamp formatting.
    """
    normalized = [
        (event_data.get('title') or '').strip().lower(),
        _normalize_datetime(event_data.get('start_at')),
        _normalize_datetime(event_data.get('end_at')),
        '1' if event_data.get('all_day') else '0',
        (event_data.get('location') or '').strip().lower(),
        (event_data.get('notes') or '').strip(),
    ]

    data_string = '|'.join(normalized)
    return hashlib.sha256(data_string.encode()).hexdigest()


def _normalize_datetime(dt: Any) -> str:
    """Normalize datetime to ISO 8601 UTC string"""
    if dt is None:
        return ''
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        except ValueError:
            return dt
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    return str(dt)


# ============================================================================
# ECHO/LOOP DETECTION
# ============================================================================

def is_echo(
    sf_event: Dict[str, Any],
    sync_map: CalendarEventSyncMap,
    echo_window_seconds: int = ECHO_IGNORE_WINDOW_SECONDS
) -> bool:
    """
    Check if a Salesforce event change is an echo of a recent CRM push.

    Returns True if:
    1. The CRM Event ID matches (CRM_Event_ID__c field)
    2. We pushed this event within the echo window
    3. The fingerprint matches what we pushed
    """
    if not sync_map or not sync_map.last_pushed_at:
        return False

    # Check if this is linked to a CRM event
    crm_event_id = sf_event.get('CRM_Event_ID__c')
    if not crm_event_id:
        return False

    # Check time window
    now = datetime.now(timezone.utc)
    time_since_push = (now - sync_map.last_pushed_at.replace(tzinfo=timezone.utc)).total_seconds()

    if time_since_push >= echo_window_seconds:
        return False

    # Check fingerprint match
    sf_fingerprint = sf_event.get('CRM_Fingerprint__c')
    if sf_fingerprint and sf_fingerprint == sync_map.fingerprint_hash:
        return True

    return False


def should_pull_from_salesforce(
    sf_event: Dict[str, Any],
    crm_event: CalendarEvent,
    sync_map: CalendarEventSyncMap,
    conflict_policy: ConflictResolutionPolicy = ConflictResolutionPolicy.LAST_WRITE_WINS
) -> bool:
    """
    Determine if we should pull changes from Salesforce to CRM.

    Uses conflict resolution policy to decide which version wins.
    """
    # Policy-based resolution
    if conflict_policy == ConflictResolutionPolicy.CRM_WINS:
        return False
    if conflict_policy == ConflictResolutionPolicy.SALESFORCE_WINS:
        return True
    if conflict_policy == ConflictResolutionPolicy.OUTLOOK_WINS:
        return True  # Outlook changes come through Salesforce

    # Last-write-wins (default)
    sf_modified = sf_event.get('LastModifiedDate')
    if sf_modified:
        if isinstance(sf_modified, str):
            sf_modified = datetime.fromisoformat(sf_modified.replace('Z', '+00:00'))
        crm_modified = crm_event.last_modified_at
        if crm_modified:
            if crm_modified.tzinfo is None:
                crm_modified = crm_modified.replace(tzinfo=timezone.utc)
            return sf_modified > crm_modified

    # If we haven't synced recently, pull to be safe
    if sync_map and sync_map.last_pulled_at:
        last_pull = sync_map.last_pulled_at.replace(tzinfo=timezone.utc)
        if (datetime.now(timezone.utc) - last_pull).total_seconds() > 300:
            return True

    return False


# ============================================================================
# CALENDAR SYNC SERVICE
# ============================================================================

class CalendarSyncService:
    """
    Bi-directional calendar sync between CRM and Salesforce.

    Implements two polling loops:
    1. Push loop (CRM → Salesforce): Every 60 seconds
    2. Pull loop (Salesforce → CRM): Every 60 seconds (staggered by 30s)
    """

    def __init__(self):
        self.api_version = SALESFORCE_API_VERSION

    # ========================================================================
    # PUSH LOOP (CRM → Salesforce)
    # ========================================================================

    async def push_pending_events(
        self,
        db: Session,
        user_id: Optional[int] = None,
        batch_size: int = 100
    ) -> CalendarSyncResult:
        """
        Push pending CRM events to Salesforce.

        This is the main push loop that runs every 60 seconds.
        """
        start_time = datetime.now(timezone.utc)
        result = CalendarSyncResult()

        try:
            # Build query for pending events
            query = db.query(CalendarEvent).filter(
                CalendarEvent.sync_status.in_([
                    CalendarSyncStatus.PENDING,
                    CalendarSyncStatus.FAILED
                ])
            )

            if user_id:
                query = query.filter(CalendarEvent.owner_user_id == user_id)

            # Order by last modified to process oldest first
            query = query.order_by(CalendarEvent.last_modified_at.asc())
            query = query.limit(batch_size)

            pending_events = query.all()

            for event in pending_events:
                try:
                    await self.push_event_to_salesforce(db, event.id)
                    result.records_succeeded += 1
                except Exception as e:
                    result.records_failed += 1
                    result.errors.append({
                        'event_id': event.id,
                        'error': str(e)
                    })
                    logger.error(f"Failed to push event {event.id}: {e}")

                result.records_processed += 1

            result.success = result.records_failed == 0
            result.duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

            # Update push watermark
            await self._update_watermark(db, 'calendar_push', result.records_processed)

        except Exception as e:
            result.duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
            logger.exception(f"Push loop failed: {e}")
            raise

        return result

    async def push_event_to_salesforce(
        self,
        db: Session,
        crm_event_id: str,
        retry_count: int = 0
    ) -> None:
        """
        Push a single CRM event to Salesforce.

        Creates or updates the corresponding Salesforce Event record.
        """
        # Get the CRM event
        event = db.query(CalendarEvent).filter(CalendarEvent.id == crm_event_id).first()
        if not event:
            raise ValueError(f"Event {crm_event_id} not found")

        # Mark as syncing
        event.sync_status = CalendarSyncStatus.SYNCING
        db.commit()

        try:
            # Get sync map (may not exist for new events)
            sync_map = db.query(CalendarEventSyncMap).filter(
                CalendarEventSyncMap.crm_event_id == crm_event_id
            ).first()

            # Get user's Salesforce integration
            settings = db.query(CalendarSyncSettings).filter(
                CalendarSyncSettings.user_id == event.owner_user_id
            ).first()

            if not settings or not settings.integration_profile_id:
                raise ValueError("No Salesforce integration configured for user")

            # Get access token
            access_token, instance_url = await salesforce_oauth.get_access_token(
                db, settings.integration_profile_id
            )

            # Map CRM user to Salesforce user
            sf_owner_id = await self._get_salesforce_user_id(db, event.owner_user_id)

            # Build Salesforce event data
            sf_event_data = {
                'Subject': event.title,
                'StartDateTime': event.start_at.isoformat() if event.start_at else None,
                'EndDateTime': event.end_at.isoformat() if event.end_at else None,
                'IsAllDayEvent': event.all_day,
                'Location': event.location,
                'Description': event.notes,
                'OwnerId': sf_owner_id,
                # Custom fields for sync tracking
                'CRM_Event_ID__c': event.id,
                'CRM_Last_Pushed_At__c': datetime.now(timezone.utc).isoformat(),
                'CRM_Fingerprint__c': event.fingerprint_hash,
                'CRM_Source__c': 'crm',
                'CRM_Sync_Version__c': (sync_map.sync_version if sync_map else 0) + 1,
            }

            # Map related entity to WhoId/WhatId
            if event.related_entity_type and event.related_entity_id:
                who_what_id = await self._map_related_entity_to_salesforce(
                    db, event.related_entity_type, event.related_entity_id
                )
                if who_what_id:
                    if event.related_entity_type in ['lead', 'contact']:
                        sf_event_data['WhoId'] = who_what_id
                    else:
                        sf_event_data['WhatId'] = who_what_id

            # Create or update in Salesforce
            if sync_map and sync_map.salesforce_event_id:
                # Update existing
                await self._update_salesforce_event(
                    access_token, instance_url, sync_map.salesforce_event_id, sf_event_data
                )
                sf_event_id = sync_map.salesforce_event_id
            else:
                # Create new
                sf_event_id = await self._create_salesforce_event(
                    access_token, instance_url, sf_event_data
                )

            # Update sync map
            now = datetime.now(timezone.utc)
            if sync_map:
                sync_map.salesforce_event_id = sf_event_id
                sync_map.salesforce_owner_id = sf_owner_id
                sync_map.fingerprint_hash = event.fingerprint_hash
                sync_map.last_pushed_at = now
                sync_map.sync_version = sf_event_data['CRM_Sync_Version__c']
            else:
                sync_map = CalendarEventSyncMap(
                    crm_event_id=event.id,
                    salesforce_event_id=sf_event_id,
                    salesforce_owner_id=sf_owner_id,
                    fingerprint_hash=event.fingerprint_hash,
                    last_pushed_at=now,
                    sync_version=sf_event_data['CRM_Sync_Version__c'],
                )
                db.add(sync_map)

            # Mark as synced
            event.sync_status = CalendarSyncStatus.SYNCED
            event.last_synced_at = now
            event.sync_error = None
            db.commit()

            # Log sync event
            self._log_sync_event(
                db, crm_event_id, sf_event_id, 'push',
                'update' if sync_map.salesforce_event_id else 'create',
                'success'
            )

        except Exception as e:
            # Check if retryable
            error_code = self._extract_error_code(str(e))
            if error_code in RETRYABLE_ERRORS and retry_count < MAX_RETRY_ATTEMPTS:
                delay = (RETRY_BACKOFF_BASE ** retry_count) * 5
                logger.warning(f"Retryable error, waiting {delay}s: {e}")
                await asyncio.sleep(delay)
                return await self.push_event_to_salesforce(db, crm_event_id, retry_count + 1)

            # Mark as failed
            event.sync_status = CalendarSyncStatus.FAILED
            event.sync_error = str(e)
            db.commit()

            self._log_sync_event(
                db, crm_event_id, None, 'push', 'create', 'failed',
                error_message=str(e)
            )
            raise

    # ========================================================================
    # PULL LOOP (Salesforce → CRM)
    # ========================================================================

    async def pull_salesforce_changes(
        self,
        db: Session,
        user_id: Optional[int] = None,
        batch_size: int = BATCH_SIZE
    ) -> CalendarSyncResult:
        """
        Pull changes from Salesforce to CRM.

        This is the main pull loop that runs every 60 seconds.
        """
        start_time = datetime.now(timezone.utc)
        result = CalendarSyncResult()

        try:
            # Get watermark
            watermark = await self._get_watermark(db, 'calendar_pull')

            # Get users to sync for
            if user_id:
                settings_list = [db.query(CalendarSyncSettings).filter(
                    CalendarSyncSettings.user_id == user_id,
                    CalendarSyncSettings.sync_enabled == True
                ).first()]
            else:
                settings_list = db.query(CalendarSyncSettings).filter(
                    CalendarSyncSettings.sync_enabled == True,
                    CalendarSyncSettings.integration_profile_id.isnot(None)
                ).all()

            for settings in settings_list:
                if not settings:
                    continue

                try:
                    user_result = await self._pull_for_user(
                        db, settings, watermark, batch_size
                    )
                    result.records_processed += user_result.records_processed
                    result.records_succeeded += user_result.records_succeeded
                    result.records_failed += user_result.records_failed
                    result.records_skipped += user_result.records_skipped
                    result.echo_prevented += user_result.echo_prevented
                    result.errors.extend(user_result.errors)
                except Exception as e:
                    logger.error(f"Pull failed for user {settings.user_id}: {e}")
                    result.errors.append({
                        'user_id': settings.user_id,
                        'error': str(e)
                    })

            # Update watermark
            await self._update_watermark(db, 'calendar_pull', result.records_processed)

            result.success = result.records_failed == 0
            result.duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

        except Exception as e:
            result.duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
            logger.exception(f"Pull loop failed: {e}")
            raise

        return result

    async def _pull_for_user(
        self,
        db: Session,
        settings: CalendarSyncSettings,
        watermark: datetime,
        batch_size: int
    ) -> CalendarSyncResult:
        """Pull Salesforce events for a specific user"""
        result = CalendarSyncResult()

        # Get access token
        access_token, instance_url = await salesforce_oauth.get_access_token(
            db, settings.integration_profile_id
        )

        # Build SOQL query
        soql = f"""
            SELECT Id, Subject, StartDateTime, EndDateTime, IsAllDayEvent,
                   Location, Description, OwnerId, WhoId, WhatId,
                   LastModifiedDate, CRM_Event_ID__c, CRM_Fingerprint__c,
                   CRM_Last_Pushed_At__c, CRM_Source__c, CRM_Sync_Version__c
            FROM Event
            WHERE LastModifiedDate > {watermark.strftime('%Y-%m-%dT%H:%M:%SZ')}
            ORDER BY LastModifiedDate ASC
            LIMIT {batch_size}
        """

        # Add filter for sync mode
        if settings.sync_mode == 'crm_only':
            soql = soql.replace(
                'ORDER BY',
                "AND CRM_Event_ID__c != null ORDER BY"
            )

        # Query Salesforce
        sf_events = await self._query_salesforce(access_token, instance_url, soql)

        for sf_event in sf_events:
            try:
                pull_result = await self.pull_event_from_salesforce(
                    db, sf_event, settings
                )
                if pull_result == 'success':
                    result.records_succeeded += 1
                elif pull_result == 'skipped':
                    result.records_skipped += 1
                elif pull_result == 'echo':
                    result.echo_prevented += 1
            except Exception as e:
                result.records_failed += 1
                result.errors.append({
                    'sf_event_id': sf_event.get('Id'),
                    'error': str(e)
                })
                logger.error(f"Failed to pull event {sf_event.get('Id')}: {e}")

            result.records_processed += 1

        return result

    async def pull_event_from_salesforce(
        self,
        db: Session,
        sf_event: Dict[str, Any],
        settings: CalendarSyncSettings
    ) -> str:
        """
        Pull a single Salesforce event to CRM.

        Returns: 'success', 'skipped', or 'echo'
        """
        sf_event_id = sf_event.get('Id')
        crm_event_id = sf_event.get('CRM_Event_ID__c')

        # Get existing sync map
        sync_map = None
        if crm_event_id:
            sync_map = db.query(CalendarEventSyncMap).filter(
                CalendarEventSyncMap.crm_event_id == crm_event_id
            ).first()
        elif sf_event_id:
            sync_map = db.query(CalendarEventSyncMap).filter(
                CalendarEventSyncMap.salesforce_event_id == sf_event_id
            ).first()

        # Check for echo (loop prevention)
        if sync_map and is_echo(sf_event, sync_map, settings.echo_ignore_window_seconds):
            logger.debug(f"Skipping echo for event {sf_event_id}")
            self._log_sync_event(
                db, crm_event_id, sf_event_id, 'pull', 'update', 'echo'
            )
            return 'echo'

        # Get or find CRM event
        crm_event = None
        if crm_event_id:
            crm_event = db.query(CalendarEvent).filter(
                CalendarEvent.id == crm_event_id
            ).first()
        elif sync_map:
            crm_event = db.query(CalendarEvent).filter(
                CalendarEvent.id == sync_map.crm_event_id
            ).first()

        # Compute incoming fingerprint
        sf_fingerprint = compute_fingerprint({
            'title': sf_event.get('Subject'),
            'start_at': sf_event.get('StartDateTime'),
            'end_at': sf_event.get('EndDateTime'),
            'all_day': sf_event.get('IsAllDayEvent'),
            'location': sf_event.get('Location'),
            'notes': sf_event.get('Description'),
        })

        # Check if update is needed
        if crm_event and crm_event.fingerprint_hash == sf_fingerprint:
            # No changes, just update sync map
            if sync_map:
                sync_map.last_pulled_at = datetime.now(timezone.utc)
                db.commit()
            logger.debug(f"Event {sf_event_id} unchanged, skipping")
            return 'skipped'

        # Check conflict resolution
        if crm_event and not should_pull_from_salesforce(
            sf_event, crm_event, sync_map, settings.conflict_policy
        ):
            logger.debug(f"Conflict resolution: keeping CRM version for {crm_event_id}")
            return 'skipped'

        # Map Salesforce user to CRM user
        crm_user_id = await self._get_crm_user_id(db, sf_event.get('OwnerId'))
        if not crm_user_id:
            crm_user_id = settings.user_id  # Fallback to settings owner

        # Build CRM event data
        now = datetime.now(timezone.utc)
        crm_event_data = {
            'title': sf_event.get('Subject'),
            'start_at': self._parse_sf_datetime(sf_event.get('StartDateTime')),
            'end_at': self._parse_sf_datetime(sf_event.get('EndDateTime')),
            'all_day': sf_event.get('IsAllDayEvent', False),
            'location': sf_event.get('Location'),
            'notes': sf_event.get('Description'),
            'owner_user_id': crm_user_id,
            'last_modified_by_system': CalendarEventSourceSystem.SALESFORCE,
            'last_modified_at': now,
            'fingerprint_hash': sf_fingerprint,
            'sync_status': CalendarSyncStatus.SYNCED,
            'last_synced_at': now,
            'sync_error': None,
        }

        if crm_event:
            # Update existing
            for key, value in crm_event_data.items():
                setattr(crm_event, key, value)
            operation = 'update'
        else:
            # Create new
            crm_event_data['id'] = crm_event_id or self._generate_ulid()
            crm_event_data['source_system'] = CalendarEventSourceSystem.SALESFORCE
            crm_event = CalendarEvent(**crm_event_data)
            db.add(crm_event)
            operation = 'create'

        # Update sync map
        if sync_map:
            sync_map.fingerprint_hash = sf_fingerprint
            sync_map.last_pulled_at = now
            sync_map.last_seen_salesforce_modified_at = self._parse_sf_datetime(
                sf_event.get('LastModifiedDate')
            )
        else:
            sync_map = CalendarEventSyncMap(
                crm_event_id=crm_event.id,
                salesforce_event_id=sf_event_id,
                salesforce_owner_id=sf_event.get('OwnerId'),
                fingerprint_hash=sf_fingerprint,
                last_pulled_at=now,
                last_seen_salesforce_modified_at=self._parse_sf_datetime(
                    sf_event.get('LastModifiedDate')
                ),
            )
            db.add(sync_map)

        db.commit()

        self._log_sync_event(
            db, crm_event.id, sf_event_id, 'pull', operation, 'success'
        )

        return 'success'

    # ========================================================================
    # IMMEDIATE PUSH (for real-time sync on create/update)
    # ========================================================================

    async def immediate_push(self, db: Session, crm_event_id: str) -> None:
        """
        Immediately push an event to Salesforce (don't wait for cycle).

        Called when enable_immediate_push is True in settings.
        """
        event = db.query(CalendarEvent).filter(CalendarEvent.id == crm_event_id).first()
        if not event:
            return

        settings = db.query(CalendarSyncSettings).filter(
            CalendarSyncSettings.user_id == event.owner_user_id
        ).first()

        if settings and settings.enable_immediate_push and settings.sync_enabled:
            try:
                await self.push_event_to_salesforce(db, crm_event_id)
            except Exception as e:
                logger.error(f"Immediate push failed for {crm_event_id}: {e}")
                # Event is already marked as pending/failed by push_event_to_salesforce

    # ========================================================================
    # SALESFORCE API HELPERS
    # ========================================================================

    async def _create_salesforce_event(
        self,
        access_token: str,
        instance_url: str,
        event_data: Dict[str, Any]
    ) -> str:
        """Create a new event in Salesforce"""
        # Remove None values
        event_data = {k: v for k, v in event_data.items() if v is not None}

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{instance_url}/services/data/{self.api_version}/sobjects/Event",
                json=event_data,
                headers={
                    'Authorization': f'Bearer {access_token}',
                    'Content-Type': 'application/json'
                }
            )

            if response.status_code not in [200, 201]:
                raise ValueError(f"Failed to create Salesforce event: {response.text}")

            result = response.json()
            return result.get('id')

    async def _update_salesforce_event(
        self,
        access_token: str,
        instance_url: str,
        event_id: str,
        event_data: Dict[str, Any]
    ) -> None:
        """Update an existing event in Salesforce"""
        # Remove None values and read-only fields
        event_data = {k: v for k, v in event_data.items() if v is not None and k != 'Id'}

        async with httpx.AsyncClient() as client:
            response = await client.patch(
                f"{instance_url}/services/data/{self.api_version}/sobjects/Event/{event_id}",
                json=event_data,
                headers={
                    'Authorization': f'Bearer {access_token}',
                    'Content-Type': 'application/json'
                }
            )

            if response.status_code not in [200, 204]:
                raise ValueError(f"Failed to update Salesforce event: {response.text}")

    async def _query_salesforce(
        self,
        access_token: str,
        instance_url: str,
        soql: str
    ) -> List[Dict[str, Any]]:
        """Query records from Salesforce"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{instance_url}/services/data/{self.api_version}/query",
                params={'q': soql},
                headers={
                    'Authorization': f'Bearer {access_token}',
                    'Content-Type': 'application/json'
                }
            )

            if response.status_code != 200:
                raise ValueError(f"Salesforce query failed: {response.text}")

            data = response.json()
            return data.get('records', [])

    # ========================================================================
    # USER MAPPING HELPERS
    # ========================================================================

    async def _get_salesforce_user_id(self, db: Session, crm_user_id: int) -> str:
        """Get Salesforce user ID for a CRM user"""
        mapping = db.query(SalesforceUserMapping).filter(
            SalesforceUserMapping.crm_user_id == crm_user_id,
            SalesforceUserMapping.is_active == True
        ).first()

        if mapping:
            return mapping.salesforce_user_id

        raise ValueError(f"No Salesforce user mapping for CRM user {crm_user_id}")

    async def _get_crm_user_id(self, db: Session, sf_user_id: str) -> Optional[int]:
        """Get CRM user ID for a Salesforce user"""
        if not sf_user_id:
            return None

        mapping = db.query(SalesforceUserMapping).filter(
            SalesforceUserMapping.salesforce_user_id == sf_user_id,
            SalesforceUserMapping.is_active == True
        ).first()

        return mapping.crm_user_id if mapping else None

    async def _map_related_entity_to_salesforce(
        self,
        db: Session,
        entity_type: str,
        entity_id: str
    ) -> Optional[str]:
        """Map CRM related entity to Salesforce WhoId/WhatId"""
        # This would need to be implemented based on your Salesforce object structure
        # For now, return None (optional field)
        return None

    # ========================================================================
    # WATERMARK HELPERS
    # ========================================================================

    async def _get_watermark(self, db: Session, sync_type: str) -> datetime:
        """Get last sync watermark"""
        watermark = db.query(SyncWatermark).filter(
            SyncWatermark.sync_type == sync_type
        ).first()

        if watermark:
            return watermark.last_synced_at

        # Default to 7 days ago
        default = datetime.now(timezone.utc) - timedelta(days=7)

        # Create watermark
        watermark = SyncWatermark(
            sync_type=sync_type,
            last_synced_at=default
        )
        db.add(watermark)
        db.commit()

        return default

    async def _update_watermark(
        self,
        db: Session,
        sync_type: str,
        records_processed: int
    ) -> None:
        """Update sync watermark"""
        watermark = db.query(SyncWatermark).filter(
            SyncWatermark.sync_type == sync_type
        ).first()

        now = datetime.now(timezone.utc)

        if watermark:
            watermark.last_synced_at = now
            watermark.records_processed = records_processed
            watermark.last_error = None
        else:
            watermark = SyncWatermark(
                sync_type=sync_type,
                last_synced_at=now,
                records_processed=records_processed
            )
            db.add(watermark)

        db.commit()

    # ========================================================================
    # UTILITY HELPERS
    # ========================================================================

    def _parse_sf_datetime(self, dt_str: Optional[str]) -> Optional[datetime]:
        """Parse Salesforce datetime string"""
        if not dt_str:
            return None
        try:
            return datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        except ValueError:
            return None

    def _generate_ulid(self) -> str:
        """Generate a ULID-like identifier"""
        import time
        import random
        import string

        # Timestamp component (48 bits)
        timestamp = int(time.time() * 1000)
        timestamp_chars = []
        for _ in range(10):
            timestamp_chars.append(string.ascii_uppercase[timestamp % 26])
            timestamp = timestamp // 26

        # Random component (80 bits)
        random_chars = ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))

        return ''.join(reversed(timestamp_chars)) + random_chars

    def _extract_error_code(self, error_message: str) -> str:
        """Extract Salesforce error code from error message"""
        for code in RETRYABLE_ERRORS:
            if code in error_message:
                return code
        return 'UNKNOWN'

    def _log_sync_event(
        self,
        db: Session,
        crm_event_id: Optional[str],
        sf_event_id: Optional[str],
        direction: str,
        operation: str,
        result: str,
        error_message: Optional[str] = None,
        duration_ms: Optional[int] = None
    ) -> None:
        """Log a sync event for auditing"""
        log = CalendarSyncEventLog(
            crm_event_id=crm_event_id,
            salesforce_event_id=sf_event_id,
            direction=direction,
            operation=operation,
            result=result,
            error_message=error_message,
            duration_ms=duration_ms,
        )
        db.add(log)
        db.commit()


# ============================================================================
# SYNC STATUS HELPER
# ============================================================================

async def get_sync_status(db: Session) -> Dict[str, Any]:
    """Get current sync status for monitoring dashboard"""
    push_watermark = db.query(SyncWatermark).filter(
        SyncWatermark.sync_type == 'calendar_push'
    ).first()

    pull_watermark = db.query(SyncWatermark).filter(
        SyncWatermark.sync_type == 'calendar_pull'
    ).first()

    pending_count = db.query(CalendarEvent).filter(
        CalendarEvent.sync_status == CalendarSyncStatus.PENDING
    ).count()

    failed_count = db.query(CalendarEvent).filter(
        CalendarEvent.sync_status == CalendarSyncStatus.FAILED
    ).count()

    # Get recent sync stats
    recent_logs = db.query(CalendarSyncEventLog).filter(
        CalendarSyncEventLog.created_at >= datetime.now(timezone.utc) - timedelta(hours=1)
    ).all()

    avg_duration = 0
    if recent_logs:
        durations = [log.duration_ms for log in recent_logs if log.duration_ms]
        avg_duration = sum(durations) / len(durations) if durations else 0

    echo_count = len([log for log in recent_logs if log.result == 'echo'])

    return {
        'last_push_cycle': push_watermark.last_synced_at.isoformat() if push_watermark else None,
        'last_pull_cycle': pull_watermark.last_synced_at.isoformat() if pull_watermark else None,
        'pending_pushes': pending_count,
        'failed_syncs': failed_count,
        'avg_sync_time_ms': round(avg_duration, 2),
        'echo_prevented_last_hour': echo_count,
    }


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

calendar_sync_service = CalendarSyncService()
