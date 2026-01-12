"""
Calendar Sync Service
Handles bidirectional sync between CRM calendar and Salesforce/Outlook

Phase 1: Core Push (CRM → Salesforce)
- Create/update/cancel events in Salesforce
- Fingerprint-based change detection
- Sync status tracking
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
            self.db.refresh(global_settings)

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
        updates: Dict[str, Any],
        auto_sync: bool = True
    ) -> Optional[CRMCalendarEvent]:
        """
        Update an existing calendar event.

        Args:
            event_id: CRM event ID
            user_id: User making the update (for authorization)
            updates: Dictionary of field updates
            auto_sync: Whether to queue sync to Salesforce

        Returns:
            Updated CRMCalendarEvent or None if not found
        """
        event = self.db.query(CRMCalendarEvent).filter(
            CRMCalendarEvent.id == event_id,
            CRMCalendarEvent.owner_user_id == user_id
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
        auto_sync: bool = True
    ) -> Optional[CRMCalendarEvent]:
        """
        Cancel (soft delete) a calendar event.

        Args:
            event_id: CRM event ID
            user_id: User making the cancellation
            auto_sync: Whether to queue sync to Salesforce

        Returns:
            Cancelled CRMCalendarEvent or None if not found
        """
        event = self.db.query(CRMCalendarEvent).filter(
            CRMCalendarEvent.id == event_id,
            CRMCalendarEvent.owner_user_id == user_id
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

    def get_event(self, event_id: str, user_id: int = None) -> Optional[CRMCalendarEvent]:
        """Get a single event by ID"""
        query = self.db.query(CRMCalendarEvent).filter(CRMCalendarEvent.id == event_id)
        if user_id:
            query = query.filter(CRMCalendarEvent.owner_user_id == user_id)
        return query.first()

    def get_events(
        self,
        user_id: int,
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
            start_date: Filter by start date >= this
            end_date: Filter by start date <= this
            status: Filter by event status
            sync_status: Filter by sync status
            limit: Maximum events to return

        Returns:
            List of CRMCalendarEvent
        """
        query = self.db.query(CRMCalendarEvent).filter(
            CRMCalendarEvent.owner_user_id == user_id
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
                self._log_sync("push", "update", crm_event_id, None, event.owner_user_id if event else None,
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
                              event.fingerprint_hash, None, "failed", result.error, start_time)
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
                "success" if result.success else "failed", result.error, start_time
            )

        except Exception as e:
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
        start_time: float
    ):
        """Log a sync operation"""
        try:
            duration_ms = int((time.time() - start_time) * 1000)

            log_entry = CalendarSyncLog(
                crm_event_id=crm_event_id,
                salesforce_event_id=sf_event_id,
                user_id=user_id,
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
        except Exception as e:
            logger.error(f"Failed to log sync operation: {e}")

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
                except Exception:
                    pass

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
