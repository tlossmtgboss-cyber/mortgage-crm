"""
Calendar Sync Service
Handles bidirectional sync between CRM calendar and Salesforce/Outlook

Phase 1: Core Push (CRM → Salesforce)
- Create/update/cancel events in Salesforce
- Fingerprint-based change detection
- Sync status tracking

Phase 2: Inbound Sync (Salesforce → CRM)
- Pull events from Salesforce
- Change Data Capture (CDC) support
- Conflict detection and resolution
- Loop prevention via fingerprint matching
"""
import logging
import time
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
import httpx

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from models.calendar_sync_models import (
    CRMCalendarEvent,
    CalendarEventSyncMap,
    CalendarSyncLog,
    CalendarSyncSettings,
    SyncStatus,
    SourceSystem,
    EventStatus,
    ConflictPolicy,
    DeletePolicy
)
from salesforce_integration_models import IntegrationProfile
from services.salesforce.oauth_service import salesforce_oauth
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


class CalendarSyncResult:
    """Result of a sync operation"""

    def __init__(self):
        self.success = False
        self.operation = None  # create, update, cancel
        self.crm_event_id = None
        self.salesforce_event_id = None
        self.error = None
        self.duration_ms = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "operation": self.operation,
            "crm_event_id": self.crm_event_id,
            "salesforce_event_id": self.salesforce_event_id,
            "error": self.error,
            "duration_ms": self.duration_ms
        }


class CalendarSyncService:
    """
    Service for syncing CRM calendar events with Salesforce.
    Salesforce acts as the bridge to Outlook calendar.
    """

    def __init__(self, db: Session):
        self.db = db

    # =========================================================================
    # Settings Management
    # =========================================================================

    def get_settings(self, user_id: int = None) -> CalendarSyncSettings:
        """Get sync settings for user or global defaults"""
        if user_id:
            settings = self.db.query(CalendarSyncSettings).filter(
                CalendarSyncSettings.user_id == user_id
            ).first()
            if settings:
                return settings

        # Get or create global settings
        global_settings = self.db.query(CalendarSyncSettings).filter(
            CalendarSyncSettings.user_id.is_(None)
        ).first()

        if not global_settings:
            global_settings = CalendarSyncSettings()
            self.db.add(global_settings)
            self.db.commit()
            # Re-query to get the committed object
            global_settings = self.db.query(CalendarSyncSettings).filter(
                CalendarSyncSettings.user_id.is_(None)
            ).first()

        return global_settings

    def update_settings(self, user_id: int, updates: Dict[str, Any]) -> CalendarSyncSettings:
        """Update sync settings for a user"""
        settings = self.db.query(CalendarSyncSettings).filter(
            CalendarSyncSettings.user_id == user_id
        ).first()

        if not settings:
            settings = CalendarSyncSettings(user_id=user_id)
            self.db.add(settings)

        for key, value in updates.items():
            if hasattr(settings, key):
                setattr(settings, key, value)

        self.db.commit()
        self.db.refresh(settings)
        return settings

    # =========================================================================
    # Event CRUD Operations
    # =========================================================================

    def create_event(
        self,
        user_id: int,
        organization_id: int,
        title: str,
        start_at: datetime,
        end_at: datetime,
        timezone: str = "America/New_York",
        all_day: bool = False,
        location: str = None,
        notes: str = None,
        attendees: List[Dict] = None,
        related_entity_type: str = None,
        related_entity_id: int = None,
        auto_sync: bool = True
    ) -> CRMCalendarEvent:
        """
        Create a new calendar event in CRM.

        Args:
            user_id: Owner user ID
            organization_id: Tenant organization ID
            title: Event subject/title
            start_at: Start datetime (UTC)
            end_at: End datetime (UTC)
            timezone: User timezone
            all_day: Is all-day event
            location: Event location
            notes: Event description
            attendees: List of attendee dicts
            related_entity_type: Type of related entity
            related_entity_id: ID of related entity
            auto_sync: Whether to queue sync to Salesforce

        Returns:
            Created CRMCalendarEvent
        """
        event = CRMCalendarEvent(
            title=title,
            start_at=start_at,
            end_at=end_at,
            timezone=timezone,
            all_day=all_day,
            location=location,
            notes=notes,
            owner_user_id=user_id,
            organization_id=organization_id,
            attendees=attendees or [],
            related_entity_type=related_entity_type,
            related_entity_id=related_entity_id,
            status=EventStatus.SCHEDULED.value,
            source_system=SourceSystem.CRM.value,
            last_modified_by_system=SourceSystem.CRM.value,
            sync_status=SyncStatus.PENDING.value if auto_sync else SyncStatus.SYNCED.value
        )

        # Compute fingerprint
        event.update_fingerprint()

        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)

        logger.info(f"Created calendar event: {event.id} - {title}")

        return event

    def update_event(
        self,
        event_id: str,
        user_id: int,
        organization_id: int,
        updates: Dict[str, Any],
        auto_sync: bool = True
    ) -> Optional[CRMCalendarEvent]:
        """
        Update an existing calendar event.

        Args:
            event_id: CRM event ID
            user_id: User making the update (for authorization)
            organization_id: Tenant organization ID
            updates: Dictionary of field updates
            auto_sync: Whether to queue sync to Salesforce

        Returns:
            Updated CRMCalendarEvent or None if not found
        """
        event = self.db.query(CRMCalendarEvent).filter(
            CRMCalendarEvent.id == event_id,
            CRMCalendarEvent.owner_user_id == user_id,
            CRMCalendarEvent.organization_id == organization_id
        ).first()

        if not event:
            return None

        # Store old fingerprint for logging
        old_fingerprint = event.fingerprint_hash

        # Apply updates
        allowed_fields = [
            'title', 'start_at', 'end_at', 'timezone', 'all_day',
            'location', 'notes', 'attendees', 'related_entity_type',
            'related_entity_id', 'status'
        ]

        for field, value in updates.items():
            if field in allowed_fields:
                setattr(event, field, value)

        # Update tracking fields
        event.last_modified_at = datetime.utcnow()
        event.last_modified_by_system = SourceSystem.CRM.value
        event.update_fingerprint()

        # Only mark as pending if fingerprint changed
        if event.fingerprint_hash != old_fingerprint and auto_sync:
            event.sync_status = SyncStatus.PENDING.value

        self.db.commit()
        self.db.refresh(event)

        logger.info(f"Updated calendar event: {event.id}")

        return event

    def cancel_event(
        self,
        event_id: str,
        user_id: int,
        organization_id: int,
        auto_sync: bool = True
    ) -> Optional[CRMCalendarEvent]:
        """
        Cancel (soft delete) a calendar event.

        Args:
            event_id: CRM event ID
            user_id: User making the cancellation
            organization_id: Tenant organization ID
            auto_sync: Whether to queue sync to Salesforce

        Returns:
            Cancelled CRMCalendarEvent or None if not found
        """
        event = self.db.query(CRMCalendarEvent).filter(
            CRMCalendarEvent.id == event_id,
            CRMCalendarEvent.owner_user_id == user_id,
            CRMCalendarEvent.organization_id == organization_id
        ).first()

        if not event:
            return None

        event.status = EventStatus.CANCELED.value
        event.last_modified_at = datetime.utcnow()
        event.last_modified_by_system = SourceSystem.CRM.value

        if auto_sync:
            event.sync_status = SyncStatus.PENDING.value

        self.db.commit()
        self.db.refresh(event)

        logger.info(f"Cancelled calendar event: {event.id}")

        return event

    def get_event(self, event_id: str, user_id: int = None, organization_id: int = None) -> Optional[CRMCalendarEvent]:
        """Get a single event by ID, scoped to organization"""
        query = self.db.query(CRMCalendarEvent).filter(CRMCalendarEvent.id == event_id)
        if organization_id:
            query = query.filter(CRMCalendarEvent.organization_id == organization_id)
        if user_id:
            query = query.filter(CRMCalendarEvent.owner_user_id == user_id)
        return query.first()

    def get_events(
        self,
        user_id: int,
        organization_id: int,
        start_date: datetime = None,
        end_date: datetime = None,
        status: str = None,
        sync_status: str = None,
        limit: int = 100
    ) -> List[CRMCalendarEvent]:
        """
        Get calendar events with filters.

        Args:
            user_id: Owner user ID
            organization_id: Tenant organization ID
            start_date: Filter by start date >= this
            end_date: Filter by start date <= this
            status: Filter by event status
            sync_status: Filter by sync status
            limit: Maximum events to return

        Returns:
            List of CRMCalendarEvent
        """
        query = self.db.query(CRMCalendarEvent).filter(
            CRMCalendarEvent.owner_user_id == user_id,
            CRMCalendarEvent.organization_id == organization_id
        )

        if start_date:
            query = query.filter(CRMCalendarEvent.start_at >= start_date)
        if end_date:
            query = query.filter(CRMCalendarEvent.start_at <= end_date)
        if status:
            query = query.filter(CRMCalendarEvent.status == status)
        if sync_status:
            query = query.filter(CRMCalendarEvent.sync_status == sync_status)

        return query.order_by(CRMCalendarEvent.start_at).limit(limit).all()

    def get_pending_sync_events(self, limit: int = 50) -> List[CRMCalendarEvent]:
        """Get events that need to be synced to Salesforce"""
        return self.db.query(CRMCalendarEvent).filter(
            CRMCalendarEvent.sync_status == SyncStatus.PENDING.value
        ).order_by(CRMCalendarEvent.updated_at).limit(limit).all()

    # =========================================================================
    # Salesforce Push Operations
    # =========================================================================

    async def push_event_to_salesforce(
        self,
        crm_event_id: str,
        force: bool = False
    ) -> CalendarSyncResult:
        """
        Push a CRM event to Salesforce.

        Args:
            crm_event_id: CRM event ID to push
            force: Force push even if fingerprint matches

        Returns:
            CalendarSyncResult with operation details
        """
        start_time = time.time()
        result = CalendarSyncResult()
        result.crm_event_id = crm_event_id

        try:
            # Load event
            event = self.db.query(CRMCalendarEvent).filter(
                CRMCalendarEvent.id == crm_event_id
            ).first()

            if not event:
                result.error = f"Event not found: {crm_event_id}"
                self._log_sync("push", "update", crm_event_id, None, None,
                              None, None, "failed", result.error, start_time)
                return result

            # Get sync mapping
            sync_map = event.sync_mapping

            # Get Salesforce credentials
            profile = self._get_integration_profile(event.owner_user_id)
            if not profile:
                result.error = "Salesforce not connected for user"
                event.sync_status = SyncStatus.FAILED.value
                event.sync_error = result.error
                self.db.commit()
                self._log_sync("push", "update", crm_event_id, None, event.owner_user_id,
                              event.fingerprint_hash, None, "failed", result.error, start_time,
                              organization_id=event.organization_id)
                return result

            # Get access token
            access_token, instance_url = await salesforce_oauth.get_access_token(
                self.db, profile.id
            )

            # Get Salesforce user ID for owner
            sf_owner_id = await self._get_salesforce_user_id(
                access_token, instance_url, event.owner_user_id
            )

            # Determine operation
            if sync_map and sync_map.salesforce_event_id:
                # Update existing Salesforce event
                result.operation = "update"
                result.salesforce_event_id = sync_map.salesforce_event_id

                if event.status == EventStatus.CANCELED.value:
                    # Handle cancellation
                    result.operation = "cancel"
                    success = await self._update_salesforce_event(
                        access_token, instance_url,
                        sync_map.salesforce_event_id,
                        event, sf_owner_id, canceled=True
                    )
                else:
                    success = await self._update_salesforce_event(
                        access_token, instance_url,
                        sync_map.salesforce_event_id,
                        event, sf_owner_id
                    )
            else:
                # Create new Salesforce event
                result.operation = "create"
                sf_event_id = await self._create_salesforce_event(
                    access_token, instance_url, event, sf_owner_id
                )

                if sf_event_id:
                    result.salesforce_event_id = sf_event_id
                    success = True

                    # Create sync mapping
                    sync_map = CalendarEventSyncMap(
                        crm_event_id=event.id,
                        salesforce_event_id=sf_event_id,
                        organization_id=event.organization_id,
                        fingerprint_hash=event.fingerprint_hash,
                        last_pushed_at=datetime.utcnow(),
                        sync_version=1
                    )
                    self.db.add(sync_map)
                else:
                    success = False

            if success:
                # Update event sync status
                event.sync_status = SyncStatus.SYNCED.value
                event.sync_error = None
                event.last_synced_at = datetime.utcnow()

                # Update sync mapping
                if sync_map:
                    sync_map.fingerprint_hash = event.fingerprint_hash
                    sync_map.last_pushed_at = datetime.utcnow()
                    sync_map.sync_version = (sync_map.sync_version or 0) + 1

                result.success = True
                logger.info(f"Pushed event to Salesforce: {crm_event_id} -> {result.salesforce_event_id}")
            else:
                event.sync_status = SyncStatus.FAILED.value
                event.sync_error = "Failed to sync to Salesforce"
                result.error = event.sync_error

            self.db.commit()

            # Log sync operation
            self._log_sync(
                "push", result.operation, crm_event_id, result.salesforce_event_id,
                event.owner_user_id, event.fingerprint_hash, event.fingerprint_hash,
                "success" if result.success else "failed", result.error, start_time,
                organization_id=event.organization_id
            )

        except SQLAlchemyError as e:
            logger.exception(f"Error pushing event to Salesforce: {e}")
            result.error = str(e)

            # Update event with error
            event = self.db.query(CRMCalendarEvent).filter(
                CRMCalendarEvent.id == crm_event_id
            ).first()
            if event:
                event.sync_status = SyncStatus.FAILED.value
                event.sync_error = str(e)
                self.db.commit()

            self._log_sync(
                "push", "unknown", crm_event_id, None, None,
                None, None, "failed", str(e), start_time
            )

        result.duration_ms = int((time.time() - start_time) * 1000)
        return result

    async def _create_salesforce_event(
        self,
        access_token: str,
        instance_url: str,
        event: CRMCalendarEvent,
        sf_owner_id: str = None
    ) -> Optional[str]:
        """Create a new event in Salesforce"""
        event_data = event.to_salesforce_event(sf_owner_id)

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{instance_url}/services/data/v60.0/sobjects/Event",
                    json=event_data,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json"
                    }
                )

                if response.status_code == 201:
                    data = response.json()
                    return data.get("id")
                else:
                    logger.error(f"Failed to create Salesforce event: {response.text}")
                    return None

        except Exception as e:
            logger.exception(f"Error creating Salesforce event: {e}")
            return None

    async def _update_salesforce_event(
        self,
        access_token: str,
        instance_url: str,
        salesforce_event_id: str,
        event: CRMCalendarEvent,
        sf_owner_id: str = None,
        canceled: bool = False
    ) -> bool:
        """Update an existing event in Salesforce"""
        event_data = event.to_salesforce_event(sf_owner_id)

        # Handle cancellation - prefix subject
        if canceled:
            event_data["Subject"] = f"[CANCELED] {event_data['Subject']}"

        # Remove ID fields for update
        event_data.pop("CRM_Event_ID__c", None)

        try:
            async with httpx.AsyncClient() as client:
                response = await client.patch(
                    f"{instance_url}/services/data/v60.0/sobjects/Event/{salesforce_event_id}",
                    json=event_data,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json"
                    }
                )

                if response.status_code == 204:
                    return True
                else:
                    logger.error(f"Failed to update Salesforce event: {response.text}")
                    return False

        except Exception as e:
            logger.exception(f"Error updating Salesforce event: {e}")
            return False

    async def _get_salesforce_user_id(
        self,
        access_token: str,
        instance_url: str,
        crm_user_id: int
    ) -> Optional[str]:
        """Get Salesforce User ID for a CRM user"""
        # First check if we have a mapping in the integration profile
        profile = self._get_integration_profile(crm_user_id)
        if profile and profile.sf_user_id:
            return profile.sf_user_id

        # Fall back to querying by email
        try:
            # Get user email from users table
            from sqlalchemy import text
            result = self.db.execute(
                text("SELECT email FROM users WHERE id = :user_id"),
                {"user_id": crm_user_id}
            ).fetchone()

            if not result:
                return None

            email = result[0]

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{instance_url}/services/data/v60.0/query",
                    params={"q": f"SELECT Id FROM User WHERE Email = '{email}'"},
                    headers={"Authorization": f"Bearer {access_token}"}
                )

                if response.status_code == 200:
                    data = response.json()
                    records = data.get("records", [])
                    if records:
                        return records[0].get("Id")

        except Exception as e:
            logger.warning(f"Failed to get Salesforce user ID: {e}")

        return None

    def _get_integration_profile(self, user_id: int) -> Optional[IntegrationProfile]:
        """Get Salesforce integration profile for a user"""
        return self.db.query(IntegrationProfile).filter(
            IntegrationProfile.user_id == user_id,
            IntegrationProfile.provider == "salesforce",
            IntegrationProfile.status == "active"
        ).first()

    def _log_sync(
        self,
        direction: str,
        operation: str,
        crm_event_id: str,
        sf_event_id: str,
        user_id: int,
        fingerprint_before: str,
        fingerprint_after: str,
        result: str,
        error: str,
        start_time: float,
        organization_id: int = None
    ):
        """Log a sync operation"""
        try:
            duration_ms = int((time.time() - start_time) * 1000)

            log_entry = CalendarSyncLog(
                crm_event_id=crm_event_id,
                salesforce_event_id=sf_event_id,
                user_id=user_id,
                organization_id=organization_id or 0,
                direction=direction,
                operation=operation,
                fingerprint_before=fingerprint_before,
                fingerprint_after=fingerprint_after,
                result=result,
                error_message=error,
                duration_ms=duration_ms
            )
            self.db.add(log_entry)
            self.db.commit()
        except SQLAlchemyError as e:
            logger.error(f"Failed to log sync operation: {e}")

    # =========================================================================
    # Salesforce Pull Operations (Phase 2)
    # =========================================================================

    async def pull_events_from_salesforce(
        self,
        user_id: int,
        since: datetime = None,
        limit: int = 200,
        organization_id: int = None
    ) -> Dict[str, Any]:
        """
        Pull events from Salesforce for a user.

        Args:
            user_id: CRM user ID
            since: Only pull events modified after this time
            limit: Maximum events to pull
            organization_id: Tenant organization ID

        Returns:
            Summary of pull operation
        """
        results = {
            "user_id": user_id,
            "pulled": 0,
            "created": 0,
            "updated": 0,
            "skipped_echo": 0,
            "skipped_conflict": 0,
            "errors": []
        }

        try:
            # Get Salesforce credentials
            profile = self._get_integration_profile(user_id)
            if not profile:
                results["errors"].append("Salesforce not connected")
                return results

            access_token, instance_url = await salesforce_oauth.get_access_token(
                self.db, profile.id
            )

            # Get settings
            settings = self.get_settings(user_id)

            # Build query for Salesforce events
            query = self._build_salesforce_events_query(
                since=since,
                limit=limit,
                sf_user_id=profile.sf_user_id
            )

            # Fetch events from Salesforce
            sf_events = await self._fetch_salesforce_events(
                access_token, instance_url, query
            )

            logger.info(f"Fetched {len(sf_events)} events from Salesforce for user {user_id}")

            # Batch-fetch EventRelation attendee data for all events
            event_ids = [e.get("Id") for e in sf_events if e.get("Id")]
            event_relations_map = await self._fetch_event_relations(
                access_token, instance_url, event_ids
            )

            # Enrich each event with its EventRelation attendees
            for sf_event in sf_events:
                sf_id = sf_event.get("Id")
                if sf_id and sf_id in event_relations_map:
                    sf_event["_event_relations"] = event_relations_map[sf_id]

            for sf_event in sf_events:
                try:
                    pull_result = await self._process_inbound_event(
                        user_id, sf_event, settings, organization_id=organization_id
                    )

                    results["pulled"] += 1
                    if pull_result["action"] == "created":
                        results["created"] += 1
                    elif pull_result["action"] == "updated":
                        results["updated"] += 1
                    elif pull_result["action"] == "skipped_echo":
                        results["skipped_echo"] += 1
                    elif pull_result["action"] == "skipped_conflict":
                        results["skipped_conflict"] += 1

                except Exception as e:
                    logger.error(f"Error processing SF event {sf_event.get('Id')}: {e}")
                    results["errors"].append({
                        "sf_event_id": sf_event.get("Id"),
                        "error": "Internal server error"
                    })

            # Update last poll watermark
            settings.last_poll_watermark = datetime.utcnow()
            self.db.commit()

        except SQLAlchemyError as e:
            logger.exception(f"Error pulling events from Salesforce: {e}")
            results["errors"].append(str(e))

        return results

    async def pull_single_event(
        self,
        user_id: int,
        salesforce_event_id: str,
        organization_id: int = None
    ) -> CalendarSyncResult:
        """
        Pull a single event from Salesforce by ID.

        Args:
            user_id: CRM user ID
            salesforce_event_id: Salesforce Event ID
            organization_id: Tenant organization ID

        Returns:
            CalendarSyncResult
        """
        start_time = time.time()
        result = CalendarSyncResult()
        result.salesforce_event_id = salesforce_event_id

        try:
            # Get Salesforce credentials
            profile = self._get_integration_profile(user_id)
            if not profile:
                result.error = "Salesforce not connected"
                return result

            access_token, instance_url = await salesforce_oauth.get_access_token(
                self.db, profile.id
            )

            # Fetch event from Salesforce
            sf_event = await self._fetch_salesforce_event(
                access_token, instance_url, salesforce_event_id
            )

            if not sf_event:
                result.error = f"Event not found in Salesforce: {salesforce_event_id}"
                return result

            # Fetch EventRelation attendees for this event
            event_relations_map = await self._fetch_event_relations(
                access_token, instance_url, [salesforce_event_id]
            )
            if salesforce_event_id in event_relations_map:
                sf_event["_event_relations"] = event_relations_map[salesforce_event_id]

            # Process the event
            settings = self.get_settings(user_id)
            pull_result = await self._process_inbound_event(user_id, sf_event, settings, organization_id=organization_id)

            result.success = True
            result.operation = pull_result["action"]
            result.crm_event_id = pull_result.get("crm_event_id")

            self._log_sync(
                "pull", result.operation, result.crm_event_id, salesforce_event_id,
                user_id, None, None, "success", None, start_time,
                organization_id=organization_id
            )

        except Exception as e:
            logger.exception(f"Error pulling single event: {e}")
            result.error = str(e)
            self._log_sync(
                "pull", "unknown", None, salesforce_event_id,
                user_id, None, None, "failed", str(e), start_time,
                organization_id=organization_id
            )

        result.duration_ms = int((time.time() - start_time) * 1000)
        return result

    async def _process_inbound_event(
        self,
        user_id: int,
        sf_event: Dict[str, Any],
        settings: CalendarSyncSettings,
        organization_id: int = None
    ) -> Dict[str, Any]:
        """
        Process an inbound Salesforce event.

        Handles:
        - Loop/echo detection
        - Conflict resolution
        - Create or update CRM event

        Args:
            user_id: CRM user ID
            sf_event: Salesforce event data
            settings: Sync settings
            organization_id: Tenant organization ID

        Returns:
            Dict with action taken and event details
        """
        sf_event_id = sf_event.get("Id")
        sf_last_modified = sf_event.get("LastModifiedDate")
        sf_fingerprint = sf_event.get("CRM_Fingerprint__c")
        crm_source_id = sf_event.get("CRM_Event_ID__c")

        # Check if this is a known event (has CRM mapping)
        sync_map = self.db.query(CalendarEventSyncMap).filter(
            CalendarEventSyncMap.salesforce_event_id == sf_event_id
        ).first()

        # LOOP PREVENTION: Check if this is an echo of our own push
        if sync_map and sf_fingerprint:
            if sync_map.fingerprint_hash == sf_fingerprint:
                # Fingerprint matches - this is our own change echoing back
                logger.debug(f"Skipping echo for SF event {sf_event_id}")
                return {"action": "skipped_echo", "reason": "fingerprint_match"}

            # Check echo window - if we recently pushed, ignore changes
            if sync_map.last_pushed_at:
                echo_window = timedelta(seconds=settings.echo_ignore_window_seconds)
                if datetime.utcnow() - sync_map.last_pushed_at < echo_window:
                    logger.debug(f"Skipping echo within window for SF event {sf_event_id}")
                    return {"action": "skipped_echo", "reason": "within_echo_window"}

        # Look up existing CRM event
        crm_event = None
        if sync_map:
            crm_event = self.db.query(CRMCalendarEvent).filter(
                CRMCalendarEvent.id == sync_map.crm_event_id
            ).first()
        elif crm_source_id:
            # Event has CRM_Event_ID__c but no mapping - try to find by ID
            crm_event = self.db.query(CRMCalendarEvent).filter(
                CRMCalendarEvent.id == crm_source_id
            ).first()

        if crm_event:
            # CONFLICT DETECTION: Check if CRM was modified after last sync
            if sync_map and sync_map.last_pulled_at:
                if crm_event.last_modified_at and crm_event.last_modified_at > sync_map.last_pulled_at:
                    if crm_event.last_modified_by_system == SourceSystem.CRM.value:
                        # CRM was modified locally - apply conflict policy
                        return await self._resolve_conflict(
                            crm_event, sf_event, sync_map, settings
                        )

            # Update existing CRM event
            self._update_crm_event_from_salesforce(crm_event, sf_event)

            # Update sync mapping
            if sync_map:
                sync_map.last_pulled_at = datetime.utcnow()
                sync_map.last_seen_sf_modified_at = self._parse_sf_datetime(sf_last_modified)
                sync_map.fingerprint_hash = crm_event.fingerprint_hash

            self.db.commit()

            logger.info(f"Updated CRM event {crm_event.id} from Salesforce")
            return {
                "action": "updated",
                "crm_event_id": crm_event.id,
                "sf_event_id": sf_event_id
            }

        else:
            # Create new CRM event from Salesforce
            crm_event = self._create_crm_event_from_salesforce(user_id, sf_event, organization_id=organization_id)

            # Create sync mapping
            sync_map = CalendarEventSyncMap(
                crm_event_id=crm_event.id,
                salesforce_event_id=sf_event_id,
                organization_id=crm_event.organization_id,
                fingerprint_hash=crm_event.fingerprint_hash,
                last_pulled_at=datetime.utcnow(),
                last_seen_sf_modified_at=self._parse_sf_datetime(sf_last_modified),
                sync_version=1
            )
            self.db.add(sync_map)
            self.db.commit()

            logger.info(f"Created CRM event {crm_event.id} from Salesforce event {sf_event_id}")
            return {
                "action": "created",
                "crm_event_id": crm_event.id,
                "sf_event_id": sf_event_id
            }

    async def _resolve_conflict(
        self,
        crm_event: CRMCalendarEvent,
        sf_event: Dict[str, Any],
        sync_map: CalendarEventSyncMap,
        settings: CalendarSyncSettings
    ) -> Dict[str, Any]:
        """
        Resolve a conflict between CRM and Salesforce changes.

        Args:
            crm_event: Local CRM event
            sf_event: Incoming Salesforce event
            sync_map: Sync mapping
            settings: Sync settings with conflict policy

        Returns:
            Dict with action taken
        """
        sf_event_id = sf_event.get("Id")
        sf_modified = self._parse_sf_datetime(sf_event.get("LastModifiedDate"))

        policy = settings.conflict_policy

        if policy == ConflictPolicy.LAST_WRITE_WINS.value:
            # Compare modification times - most recent wins
            crm_modified = crm_event.last_modified_at

            if sf_modified and crm_modified:
                if sf_modified > crm_modified:
                    # Salesforce is newer - apply SF changes
                    self._update_crm_event_from_salesforce(crm_event, sf_event)
                    sync_map.last_pulled_at = datetime.utcnow()
                    sync_map.fingerprint_hash = crm_event.fingerprint_hash
                    self.db.commit()
                    logger.info(f"Conflict resolved: SF wins for event {crm_event.id}")
                    return {"action": "updated", "resolution": "sf_wins", "crm_event_id": crm_event.id}
                else:
                    # CRM is newer - queue push to SF
                    crm_event.sync_status = SyncStatus.PENDING.value
                    self.db.commit()
                    logger.info(f"Conflict resolved: CRM wins for event {crm_event.id}")
                    return {"action": "skipped_conflict", "resolution": "crm_wins", "crm_event_id": crm_event.id}

        elif policy == ConflictPolicy.CRM_WINS.value:
            # Always keep CRM version, queue push
            crm_event.sync_status = SyncStatus.PENDING.value
            self.db.commit()
            logger.info(f"Conflict policy CRM_WINS: keeping CRM version for {crm_event.id}")
            return {"action": "skipped_conflict", "resolution": "crm_wins", "crm_event_id": crm_event.id}

        elif policy == ConflictPolicy.SALESFORCE_WINS.value:
            # Always apply Salesforce changes
            self._update_crm_event_from_salesforce(crm_event, sf_event)
            sync_map.last_pulled_at = datetime.utcnow()
            sync_map.fingerprint_hash = crm_event.fingerprint_hash
            self.db.commit()
            logger.info(f"Conflict policy SF_WINS: applying SF version for {crm_event.id}")
            return {"action": "updated", "resolution": "sf_wins", "crm_event_id": crm_event.id}

        # Default to last_write_wins if policy not recognized
        return {"action": "skipped_conflict", "resolution": "unknown_policy", "crm_event_id": crm_event.id}

    async def _fetch_event_relations(
        self,
        access_token: str,
        instance_url: str,
        event_ids: List[str]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Fetch EventRelation records for a batch of Salesforce events.
        EventRelation stores the full attendee list for each event.

        Args:
            access_token: OAuth access token
            instance_url: Salesforce instance URL
            event_ids: List of Salesforce Event IDs

        Returns:
            Dict mapping event_id -> list of attendee dicts
        """
        if not event_ids:
            return {}

        # Build SOQL to fetch EventRelation records in bulk
        ids_str = "','".join(event_ids)
        query = (
            f"SELECT EventId, RelationId, Relation.Name, Relation.Email, Status "
            f"FROM EventRelation "
            f"WHERE EventId IN ('{ids_str}') AND IsInvitee = true"
        )

        attendees_by_event: Dict[str, List[Dict[str, Any]]] = {eid: [] for eid in event_ids}

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{instance_url}/services/data/v60.0/query",
                    params={"q": query},
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=30.0
                )

                if response.status_code == 200:
                    records = response.json().get("records", [])
                    for record in records:
                        event_id = record.get("EventId")
                        if event_id in attendees_by_event:
                            relation = record.get("Relation") or {}
                            status_map = {
                                "Accepted": "accepted",
                                "Declined": "declined",
                                "Uninvited": "declined",
                                "New": "pending",
                                "Maybe": "tentative",
                            }
                            sf_status = record.get("Status", "New")
                            attendees_by_event[event_id].append({
                                "name": relation.get("Name", ""),
                                "email": relation.get("Email", ""),
                                "status": status_map.get(sf_status, "pending"),
                                "sf_relation_id": record.get("RelationId"),
                            })
                    logger.info(
                        f"Fetched EventRelation records for {len(event_ids)} events, "
                        f"found {sum(len(v) for v in attendees_by_event.values())} attendees"
                    )
                elif response.status_code == 400 and "INVALID_TYPE" in response.text:
                    # EventRelation may not be available in all orgs
                    logger.warning("EventRelation not available in this Salesforce org, using WhoId/WhatId only")
                else:
                    logger.warning(f"Failed to fetch EventRelation: {response.status_code} {response.text}")

        except Exception as e:
            logger.warning(f"Error fetching EventRelation records: {e}")

        return attendees_by_event

    def _parse_sf_attendees(
        self,
        sf_event: Dict[str, Any],
        event_relations: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Parse attendees from Salesforce event data.

        Combines WhoId/WhatId fields with EventRelation records (if available)
        into a unified attendee list.

        Args:
            sf_event: Salesforce event dict (includes WhoId, Who.Name, WhatId, What.Name)
            event_relations: Optional list of EventRelation-derived attendee dicts

        Returns:
            List of attendee dicts: [{"email": "...", "name": "...", "status": "..."}]
        """
        attendees = []
        seen_ids = set()

        # If we have EventRelation data, use it as the primary source
        if event_relations:
            for rel in event_relations:
                sf_id = rel.get("sf_relation_id")
                if sf_id:
                    seen_ids.add(sf_id)
                attendees.append({
                    "name": rel.get("name", ""),
                    "email": rel.get("email", ""),
                    "status": rel.get("status", "pending"),
                })

        # Add WhoId contact/lead if not already in EventRelation list
        who_id = sf_event.get("WhoId")
        if who_id and who_id not in seen_ids:
            # Who is a polymorphic lookup to Contact or Lead
            who_data = sf_event.get("Who") or {}
            who_name = who_data.get("Name", "") if isinstance(who_data, dict) else ""
            attendees.append({
                "name": who_name,
                "email": "",  # Email not reliably available from Who relationship
                "status": "accepted",
                "sf_who_id": who_id,
            })

        # Add WhatId related record as context (Account, Opportunity, etc.)
        what_id = sf_event.get("WhatId")
        if what_id:
            what_data = sf_event.get("What") or {}
            what_name = what_data.get("Name", "") if isinstance(what_data, dict) else ""
            if what_name:
                attendees.append({
                    "name": what_name,
                    "email": "",
                    "status": "accepted",
                    "sf_what_id": what_id,
                    "type": "related_record",
                })

        return attendees

    def _create_crm_event_from_salesforce(
        self,
        user_id: int,
        sf_event: Dict[str, Any],
        organization_id: int = None
    ) -> CRMCalendarEvent:
        """
        Create a new CRM event from Salesforce data.

        Args:
            user_id: CRM user ID (owner)
            sf_event: Salesforce event data
            organization_id: Tenant organization ID

        Returns:
            Created CRMCalendarEvent
        """
        # Parse Salesforce event fields
        start_at = self._parse_sf_datetime(sf_event.get("StartDateTime"))
        end_at = self._parse_sf_datetime(sf_event.get("EndDateTime"))

        # Handle all-day events
        all_day = sf_event.get("IsAllDayEvent", False)
        if all_day and not start_at:
            # All-day events use ActivityDate
            activity_date = sf_event.get("ActivityDate")
            if activity_date:
                start_at = datetime.strptime(activity_date, "%Y-%m-%d")
                end_at = start_at + timedelta(days=1)

        # Determine status from SF event
        status = EventStatus.SCHEDULED.value
        subject = sf_event.get("Subject", "")
        if subject.startswith("[CANCELED]"):
            status = EventStatus.CANCELED.value
            subject = subject.replace("[CANCELED]", "").strip()

        event = CRMCalendarEvent(
            title=subject,
            start_at=start_at,
            end_at=end_at,
            timezone="UTC",  # SF returns UTC
            all_day=all_day,
            location=sf_event.get("Location"),
            notes=sf_event.get("Description"),
            owner_user_id=user_id,
            organization_id=organization_id,
            attendees=self._parse_sf_attendees(sf_event, sf_event.get("_event_relations")),
            status=status,
            source_system=SourceSystem.SALESFORCE.value,
            last_modified_by_system=SourceSystem.SALESFORCE.value,
            sync_status=SyncStatus.SYNCED.value  # Already synced since from SF
        )

        event.update_fingerprint()
        self.db.add(event)
        self.db.flush()  # Get ID without committing

        return event

    def _update_crm_event_from_salesforce(
        self,
        crm_event: CRMCalendarEvent,
        sf_event: Dict[str, Any]
    ):
        """
        Update an existing CRM event with Salesforce data.

        Args:
            crm_event: CRM event to update
            sf_event: Salesforce event data
        """
        # Parse Salesforce event fields
        start_at = self._parse_sf_datetime(sf_event.get("StartDateTime"))
        end_at = self._parse_sf_datetime(sf_event.get("EndDateTime"))

        # Handle all-day events
        all_day = sf_event.get("IsAllDayEvent", False)
        if all_day and not start_at:
            activity_date = sf_event.get("ActivityDate")
            if activity_date:
                start_at = datetime.strptime(activity_date, "%Y-%m-%d")
                end_at = start_at + timedelta(days=1)

        # Check for cancellation
        subject = sf_event.get("Subject", "")
        if subject.startswith("[CANCELED]"):
            crm_event.status = EventStatus.CANCELED.value
            subject = subject.replace("[CANCELED]", "").strip()

        # Update fields
        crm_event.title = subject
        crm_event.start_at = start_at
        crm_event.end_at = end_at
        crm_event.all_day = all_day
        crm_event.location = sf_event.get("Location")
        crm_event.notes = sf_event.get("Description")
        crm_event.attendees = self._parse_sf_attendees(sf_event, sf_event.get("_event_relations"))
        crm_event.last_modified_at = datetime.utcnow()
        crm_event.last_modified_by_system = SourceSystem.SALESFORCE.value
        crm_event.sync_status = SyncStatus.SYNCED.value

        crm_event.update_fingerprint()

    def _build_salesforce_events_query(
        self,
        since: datetime = None,
        limit: int = 200,
        sf_user_id: str = None
    ) -> str:
        """
        Build SOQL query for Salesforce events.

        Args:
            since: Filter by last modified date
            limit: Maximum records
            sf_user_id: Filter by owner

        Returns:
            SOQL query string
        """
        fields = [
            "Id", "Subject", "StartDateTime", "EndDateTime",
            "IsAllDayEvent", "ActivityDate", "Location", "Description",
            "OwnerId", "LastModifiedDate", "CreatedDate",
            "WhoId", "Who.Name", "WhatId", "What.Name",
            "CRM_Event_ID__c", "CRM_Fingerprint__c",
            "CRM_Last_Pushed_At__c", "CRM_Source__c"
        ]

        query = f"SELECT {', '.join(fields)} FROM Event"

        conditions = []
        if sf_user_id:
            conditions.append(f"OwnerId = '{sf_user_id}'")
        if since:
            since_str = since.strftime("%Y-%m-%dT%H:%M:%SZ")
            conditions.append(f"LastModifiedDate > {since_str}")

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += f" ORDER BY LastModifiedDate DESC LIMIT {limit}"

        return query

    async def _fetch_salesforce_events(
        self,
        access_token: str,
        instance_url: str,
        query: str
    ) -> List[Dict[str, Any]]:
        """
        Execute SOQL query to fetch events from Salesforce.

        Args:
            access_token: OAuth access token
            instance_url: Salesforce instance URL
            query: SOQL query

        Returns:
            List of event records
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{instance_url}/services/data/v60.0/query",
                    params={"q": query},
                    headers={"Authorization": f"Bearer {access_token}"}
                )

                if response.status_code == 200:
                    data = response.json()
                    return data.get("records", [])
                else:
                    logger.error(f"Failed to query Salesforce events: {response.text}")
                    return []

        except Exception as e:
            logger.exception(f"Error fetching Salesforce events: {e}")
            return []

    async def _fetch_salesforce_event(
        self,
        access_token: str,
        instance_url: str,
        event_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch a single event from Salesforce by ID.

        Args:
            access_token: OAuth access token
            instance_url: Salesforce instance URL
            event_id: Salesforce Event ID

        Returns:
            Event data or None
        """
        fields = [
            "Id", "Subject", "StartDateTime", "EndDateTime",
            "IsAllDayEvent", "ActivityDate", "Location", "Description",
            "OwnerId", "LastModifiedDate", "CreatedDate",
            "WhoId", "WhatId",
            "CRM_Event_ID__c", "CRM_Fingerprint__c",
            "CRM_Last_Pushed_At__c", "CRM_Source__c"
        ]

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{instance_url}/services/data/v60.0/sobjects/Event/{event_id}",
                    params={"fields": ",".join(fields)},
                    headers={"Authorization": f"Bearer {access_token}"}
                )

                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(f"Failed to fetch Salesforce event {event_id}: {response.text}")
                    return None

        except Exception as e:
            logger.exception(f"Error fetching Salesforce event: {e}")
            return None

    def _parse_sf_datetime(self, sf_datetime: str) -> Optional[datetime]:
        """Parse Salesforce datetime string to Python datetime."""
        if not sf_datetime:
            return None

        try:
            # SF format: 2024-01-15T10:00:00.000+0000
            if "." in sf_datetime:
                return datetime.strptime(sf_datetime[:19], "%Y-%m-%dT%H:%M:%S")
            else:
                return datetime.strptime(sf_datetime[:19], "%Y-%m-%dT%H:%M:%S")
        except Exception as e:
            logger.exception(f"Failed to parse Salesforce datetime '{sf_datetime}': {e}")
            return None

    # =========================================================================
    # CDC (Change Data Capture) Support
    # =========================================================================

    async def process_cdc_event(
        self,
        user_id: int,
        cdc_payload: Dict[str, Any],
        organization_id: int = None
    ) -> Dict[str, Any]:
        """
        Process a Salesforce CDC (Change Data Capture) event.

        Called from webhook endpoint when Salesforce sends a CDC notification.

        Args:
            user_id: CRM user ID
            cdc_payload: CDC event payload from Salesforce
            organization_id: Tenant organization ID

        Returns:
            Processing result
        """
        change_type = cdc_payload.get("changeType")  # CREATE, UPDATE, DELETE
        entity_name = cdc_payload.get("entityName")  # Event

        if entity_name != "Event":
            return {"skipped": True, "reason": "not_event_object"}

        results = {
            "processed": 0,
            "created": 0,
            "updated": 0,
            "deleted": 0,
            "errors": []
        }

        settings = self.get_settings(user_id)

        # CDC payload contains changed records
        changed_records = cdc_payload.get("changedRecords", [])

        for record in changed_records:
            try:
                record_id = record.get("Id")

                if change_type == "DELETE":
                    # Handle deletion
                    delete_result = await self._handle_sf_delete(user_id, record_id, settings)
                    if delete_result:
                        results["deleted"] += 1
                else:
                    # CREATE or UPDATE - fetch full record and process
                    profile = self._get_integration_profile(user_id)
                    if profile:
                        access_token, instance_url = await salesforce_oauth.get_access_token(
                            self.db, profile.id
                        )
                        sf_event = await self._fetch_salesforce_event(
                            access_token, instance_url, record_id
                        )
                        if sf_event:
                            # Enrich with EventRelation attendees
                            event_relations_map = await self._fetch_event_relations(
                                access_token, instance_url, [record_id]
                            )
                            if record_id in event_relations_map:
                                sf_event["_event_relations"] = event_relations_map[record_id]

                            process_result = await self._process_inbound_event(
                                user_id, sf_event, settings, organization_id=organization_id
                            )
                            results["processed"] += 1
                            if process_result["action"] == "created":
                                results["created"] += 1
                            elif process_result["action"] == "updated":
                                results["updated"] += 1

            except Exception as e:
                logger.error(f"Error processing CDC record: {e}")
                results["errors"].append({"record_id": record.get("Id"), "error": "Internal server error"})

        return results

    async def _handle_sf_delete(
        self,
        user_id: int,
        sf_event_id: str,
        settings: CalendarSyncSettings
    ) -> bool:
        """
        Handle deletion of a Salesforce event.

        Args:
            user_id: CRM user ID
            sf_event_id: Deleted Salesforce Event ID
            settings: Sync settings

        Returns:
            True if handled successfully
        """
        # Find sync mapping
        sync_map = self.db.query(CalendarEventSyncMap).filter(
            CalendarEventSyncMap.salesforce_event_id == sf_event_id
        ).first()

        if not sync_map:
            return False

        crm_event = self.db.query(CRMCalendarEvent).filter(
            CRMCalendarEvent.id == sync_map.crm_event_id
        ).first()

        if not crm_event:
            # Just clean up orphaned mapping
            self.db.delete(sync_map)
            self.db.commit()
            return True

        # Apply delete policy
        if settings.delete_policy == DeletePolicy.SOFT_CANCEL.value:
            # Mark as canceled
            crm_event.status = EventStatus.CANCELED.value
            crm_event.last_modified_by_system = SourceSystem.SALESFORCE.value
            crm_event.sync_status = SyncStatus.SYNCED.value  # Don't re-push
            self.db.commit()
            logger.info(f"Soft-canceled CRM event {crm_event.id} due to SF deletion")

        elif settings.delete_policy == DeletePolicy.HARD_DELETE.value:
            # Actually delete
            self.db.delete(sync_map)
            self.db.delete(crm_event)
            self.db.commit()
            logger.info(f"Hard-deleted CRM event due to SF deletion")

        elif settings.delete_policy == DeletePolicy.IGNORE.value:
            # Just remove mapping, keep CRM event
            self.db.delete(sync_map)
            self.db.commit()
            logger.info(f"Removed SF mapping, kept CRM event {crm_event.id}")

        return True

    # =========================================================================
    # Sync Status and Health
    # =========================================================================

    def get_sync_status(self, user_id: int) -> Dict[str, Any]:
        """Get sync status summary for a user"""
        # Get counts
        pending_count = self.db.query(CRMCalendarEvent).filter(
            CRMCalendarEvent.owner_user_id == user_id,
            CRMCalendarEvent.sync_status == SyncStatus.PENDING.value
        ).count()

        failed_count = self.db.query(CRMCalendarEvent).filter(
            CRMCalendarEvent.owner_user_id == user_id,
            CRMCalendarEvent.sync_status == SyncStatus.FAILED.value
        ).count()

        # Get last successful sync
        last_synced = self.db.query(CRMCalendarEvent).filter(
            CRMCalendarEvent.owner_user_id == user_id,
            CRMCalendarEvent.sync_status == SyncStatus.SYNCED.value
        ).order_by(CRMCalendarEvent.last_synced_at.desc()).first()

        # Get last error
        last_failed = self.db.query(CRMCalendarEvent).filter(
            CRMCalendarEvent.owner_user_id == user_id,
            CRMCalendarEvent.sync_status == SyncStatus.FAILED.value
        ).order_by(CRMCalendarEvent.updated_at.desc()).first()

        return {
            "pending_count": pending_count,
            "failed_count": failed_count,
            "last_sync_at": last_synced.last_synced_at.isoformat() if last_synced and last_synced.last_synced_at else None,
            "last_error": last_failed.sync_error if last_failed else None,
            "healthy": pending_count == 0 and failed_count == 0
        }

    def get_sync_history(
        self,
        user_id: int,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get sync history for a user"""
        logs = self.db.query(CalendarSyncLog).filter(
            CalendarSyncLog.user_id == user_id
        ).order_by(CalendarSyncLog.created_at.desc()).limit(limit).all()

        return [log.to_dict() for log in logs]

    def get_failed_events(self, user_id: int) -> List[CRMCalendarEvent]:
        """Get events that failed to sync"""
        return self.db.query(CRMCalendarEvent).filter(
            CRMCalendarEvent.owner_user_id == user_id,
            CRMCalendarEvent.sync_status == SyncStatus.FAILED.value
        ).order_by(CRMCalendarEvent.updated_at.desc()).all()

    async def resync_event(self, event_id: str, user_id: int) -> CalendarSyncResult:
        """
        Force resync an event to Salesforce.
        Recreates in Salesforce if mapping is missing.
        """
        event = self.get_event(event_id, user_id)
        if not event:
            result = CalendarSyncResult()
            result.error = "Event not found"
            return result

        # Clear existing mapping to force recreate
        if event.sync_mapping:
            # Check if SF event still exists
            profile = self._get_integration_profile(user_id)
            if profile:
                try:
                    access_token, instance_url = await salesforce_oauth.get_access_token(
                        self.db, profile.id
                    )

                    async with httpx.AsyncClient() as client:
                        response = await client.get(
                            f"{instance_url}/services/data/v60.0/sobjects/Event/{event.sync_mapping.salesforce_event_id}",
                            headers={"Authorization": f"Bearer {access_token}"}
                        )

                        if response.status_code == 404:
                            # SF event deleted, remove mapping
                            self.db.delete(event.sync_mapping)
                            self.db.commit()
                except Exception as e:
                    logger.exception(f"Failed to check/remove Salesforce event mapping: {e}")

        # Reset sync status
        event.sync_status = SyncStatus.PENDING.value
        event.sync_error = None
        self.db.commit()

        # Push to Salesforce
        return await self.push_event_to_salesforce(event_id, force=True)


# Factory function
def get_calendar_sync_service(db: Session) -> CalendarSyncService:
    """Get calendar sync service instance"""
    return CalendarSyncService(db)
