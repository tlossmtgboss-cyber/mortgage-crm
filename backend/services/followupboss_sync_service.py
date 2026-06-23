"""
Follow Up Boss Sync Service
Perennia AI - Mortgage CRM

Handles bidirectional sync between FUB and CRM:
- Inbound: FUB webhook events → CRM leads
- Outbound: CRM changes → FUB updates
- Stage mapping and field transformation
"""

import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
from difflib import SequenceMatcher

from sqlalchemy.orm import Session
from sqlalchemy import text

from integrations.followupboss_service import (
    FollowUpBossClient,
    decrypt_api_key,
    extract_email,
    extract_phone,
    format_emails_for_fub,
    format_phones_for_fub,
    compute_sync_hash
)
from models.followupboss_models import (
    FUBUserConnection,
    FUBLeadMapping,
    FUBSyncEvent,
    FUBStageMapping,
    FUBSyncDirection,
    FUBSyncStatus,
    FUBEventType,
    FUB_TO_CRM_FIELD_MAP,
    CRM_TO_FUB_FIELD_MAP,
    DEFAULT_STAGE_MAPPINGS
)

logger = logging.getLogger(__name__)


class FollowUpBossSyncService:
    """
    Service for syncing data between Follow Up Boss and CRM.
    """

    def __init__(self, db: Session):
        self.db = db

    # =========================================================================
    # CONNECTION MANAGEMENT
    # =========================================================================

    def get_connection(self, user_id: int) -> Optional[FUBUserConnection]:
        """Get FUB connection for user."""
        return self.db.query(FUBUserConnection).filter(
            FUBUserConnection.user_id == user_id
        ).first()

    def get_client(self, connection: FUBUserConnection) -> FollowUpBossClient:
        """Get FUB API client from connection."""
        api_key = decrypt_api_key(connection.api_key_encrypted)
        return FollowUpBossClient(api_key)

    # =========================================================================
    # STAGE MAPPING
    # =========================================================================

    def get_stage_mappings(self, connection_id: int) -> Dict[str, str]:
        """
        Get FUB stage → CRM stage mappings.

        Returns:
            Dict mapping FUB stage name to CRM LeadStage value
        """
        mappings = self.db.query(FUBStageMapping).filter(
            FUBStageMapping.connection_id == connection_id
        ).all()

        return {m.fub_stage_name: m.crm_stage for m in mappings}

    def get_reverse_stage_mappings(self, connection_id: int) -> Dict[str, str]:
        """
        Get CRM stage → FUB stage mappings.

        Returns:
            Dict mapping CRM LeadStage value to FUB stage name
        """
        mappings = self.db.query(FUBStageMapping).filter(
            FUBStageMapping.connection_id == connection_id
        ).all()

        return {m.crm_stage: m.fub_stage_name for m in mappings}

    def auto_map_stages(
        self,
        connection: FUBUserConnection,
        fub_stages: List[Dict]
    ) -> List[FUBStageMapping]:
        """
        Auto-map FUB stages to CRM stages based on name similarity.

        Args:
            connection: FUB connection
            fub_stages: List of stage dicts from FUB API

        Returns:
            List of created stage mappings
        """
        # Get CRM stage names
        from database.enums import LeadStage
        crm_stages = {s.value: s.name for s in LeadStage}

        created_mappings = []

        for fub_stage in fub_stages:
            fub_name = fub_stage.get("name", "")
            fub_id = fub_stage.get("id")

            # Check if already mapped
            existing = self.db.query(FUBStageMapping).filter(
                FUBStageMapping.connection_id == connection.id,
                FUBStageMapping.fub_stage_name == fub_name
            ).first()

            if existing:
                continue

            # Try default mapping first
            crm_stage = DEFAULT_STAGE_MAPPINGS.get(fub_name)

            if not crm_stage:
                # Find best match by name similarity
                best_match = None
                best_score = 0

                for crm_value, crm_name in crm_stages.items():
                    # Compare both value and display name
                    score1 = SequenceMatcher(None, fub_name.lower(), crm_value.lower()).ratio()
                    score2 = SequenceMatcher(None, fub_name.lower(), crm_name.lower().replace("_", " ")).ratio()
                    score = max(score1, score2)

                    if score > best_score:
                        best_score = score
                        best_match = crm_value

                if best_match and best_score > 0.5:
                    crm_stage = best_match
                else:
                    # Default to NEW for unmatched stages
                    crm_stage = "NEW"
                    best_score = 0

            # Create mapping
            mapping = FUBStageMapping(
                connection_id=connection.id,
                fub_stage_name=fub_name,
                fub_stage_id=fub_id,
                crm_stage=crm_stage,
                is_auto_mapped=True,
                confidence_score=int(best_score * 100) if best_score else 100
            )
            self.db.add(mapping)
            created_mappings.append(mapping)

        self.db.commit()
        return created_mappings

    # =========================================================================
    # INBOUND SYNC (FUB → CRM)
    # =========================================================================

    def _get_user_org_id(self, user_id: int) -> Optional[int]:
        """Look up organization_id for a user (needed for Lead creation)."""
        row = self.db.execute(
            text("SELECT organization_id FROM users WHERE id = :uid"),
            {"uid": user_id}
        ).fetchone()
        return row[0] if row else None

    def sync_person_to_lead(
        self,
        connection: FUBUserConnection,
        fub_person: Dict,
        event_type: str = "manual_sync",
        organization_id: Optional[int] = None,
    ) -> Tuple[Optional[int], bool]:
        """
        Sync FUB person to CRM lead.

        Args:
            connection: FUB connection
            fub_person: Person data from FUB
            event_type: Type of sync event
            organization_id: Org ID for the new lead (required; looked up if not provided)

        Returns:
            Tuple of (lead_id, is_new)
        """
        from database.enums import LeadStage
        from database.models import Lead

        fub_person_id = fub_person.get("id")
        if not fub_person_id:
            logger.error("FUB person has no ID")
            return None, False

        # Resolve org ID — required for Lead.organization_id NOT NULL constraint
        if organization_id is None:
            organization_id = self._get_user_org_id(connection.user_id)

        # Log sync event
        sync_event = FUBSyncEvent(
            connection_id=connection.id,
            event_type=event_type,
            direction=FUBSyncDirection.INBOUND.value,
            fub_entity_type="people",
            fub_entity_id=fub_person_id,
            status=FUBSyncStatus.IN_PROGRESS.value,
            request_payload=fub_person
        )
        self.db.add(sync_event)
        self.db.flush()

        try:
            # Check if already mapped
            mapping = self.db.query(FUBLeadMapping).filter(
                FUBLeadMapping.connection_id == connection.id,
                FUBLeadMapping.fub_person_id == fub_person_id
            ).first()

            is_new = mapping is None

            if mapping:
                # Update existing lead
                lead = self.db.query(Lead).filter(Lead.id == mapping.lead_id).first()
                if not lead:
                    logger.error(f"Lead {mapping.lead_id} not found for mapping")
                    is_new = True
                    mapping = None

            # Extract basic fields first (needed before flush — name is NOT NULL)
            _first = fub_person.get("firstName", "") or ""
            _last = fub_person.get("lastName", "") or ""
            _name = f"{_first} {_last}".strip() or "Unknown"
            _email = extract_email(fub_person)
            _phone = extract_phone(fub_person)
            _source = fub_person.get("source", "Follow Up Boss")

            if is_new:
                # Create new lead with required NOT NULL fields set before flush
                lead = Lead(
                    owner_id=connection.user_id,
                    organization_id=organization_id,
                    first_name=_first,
                    last_name=_last,
                    name=_name,
                    email=_email,
                    phone=_phone,
                    source=_source,
                )
                self.db.add(lead)
                self.db.flush()

                from services.client_file_service import ensure_client_file
                ensure_client_file(self.db, lead)

            # Transform and apply fields
            stage_mappings = self.get_stage_mappings(connection.id)

            # Basic fields (update on existing lead too)
            lead.first_name = _first
            lead.last_name = _last
            lead.name = _name
            lead.email = _email
            lead.phone = _phone
            lead.source = _source

            # Property fields
            lead.address = fub_person.get("propertyStreet", "")
            lead.city = fub_person.get("propertyCity", "")
            lead.state = fub_person.get("propertyState", "")
            lead.zip_code = fub_person.get("propertyZip", "")

            # Financial fields
            if fub_person.get("price"):
                try:
                    lead.loan_amount = float(fub_person.get("price"))
                except (ValueError, TypeError):
                    pass

            # Stage mapping
            fub_stage = fub_person.get("stage")
            if fub_stage and fub_stage in stage_mappings:
                crm_stage = stage_mappings[fub_stage]
                try:
                    lead.stage = LeadStage(crm_stage)
                except ValueError:
                    logger.warning(f"Invalid CRM stage: {crm_stage}")

            # Store FUB metadata
            lead.fub_person_id = fub_person_id
            lead.fub_last_synced_at = datetime.now(timezone.utc)

            # Store tags and other data in metadata
            if not lead.user_metadata:
                lead.user_metadata = {}
            lead.user_metadata["fub_tags"] = fub_person.get("tags", [])
            lead.user_metadata["fub_assignedTo"] = fub_person.get("assignedTo")

            self.db.flush()

            # Create or update mapping
            sync_hash = compute_sync_hash({
                "firstName": lead.first_name,
                "lastName": lead.last_name,
                "email": lead.email,
                "phone": lead.phone,
                "stage": str(lead.stage) if lead.stage else None
            })

            if is_new:
                mapping = FUBLeadMapping(
                    connection_id=connection.id,
                    fub_person_id=fub_person_id,
                    lead_id=lead.id,
                    sync_hash=sync_hash,
                    last_synced_at=datetime.now(timezone.utc),
                    sync_direction=FUBSyncDirection.INBOUND.value,
                    fub_stage=fub_stage,
                    fub_assigned_to=str(fub_person.get("assignedTo")),
                    fub_updated_at=datetime.fromisoformat(fub_person["updated"].replace("Z", "+00:00")) if fub_person.get("updated") else None
                )
                self.db.add(mapping)
            else:
                mapping.sync_hash = sync_hash
                mapping.last_synced_at = datetime.now(timezone.utc)
                mapping.sync_direction = FUBSyncDirection.INBOUND.value
                mapping.fub_stage = fub_stage

            # Update sync event
            sync_event.crm_entity_type = "lead"
            sync_event.crm_entity_id = lead.id
            sync_event.status = FUBSyncStatus.COMPLETED.value
            sync_event.completed_at = datetime.now(timezone.utc)

            self.db.commit()

            logger.info(f"Synced FUB person {fub_person_id} to lead {lead.id} (new={is_new})")
            return lead.id, is_new

        except Exception as e:
            logger.exception(f"Error syncing FUB person {fub_person_id}: {e}")
            sync_event.status = FUBSyncStatus.FAILED.value
            sync_event.error_message = str(e)
            sync_event.completed_at = datetime.now(timezone.utc)
            try:
                self.db.commit()
            except Exception:
                self.db.rollback()
            return None, False

    def sync_note_to_activity(
        self,
        connection: FUBUserConnection,
        fub_note: Dict
    ) -> Optional[int]:
        """
        Sync FUB note to CRM activity.

        Args:
            connection: FUB connection
            fub_note: Note data from FUB

        Returns:
            Activity ID if created
        """
        from database.enums import ActivityType
        from database.models import Activity

        fub_note_id = fub_note.get("id")
        fub_person_id = fub_note.get("personId")

        if not fub_person_id:
            logger.error("FUB note has no personId")
            return None

        # Find lead mapping
        mapping = self.db.query(FUBLeadMapping).filter(
            FUBLeadMapping.connection_id == connection.id,
            FUBLeadMapping.fub_person_id == fub_person_id
        ).first()

        if not mapping:
            logger.warning(f"No lead mapping for FUB person {fub_person_id}")
            return None

        # Deduplicate: skip if this note was already imported
        if fub_note_id:
            existing = self.db.query(Activity).filter(
                Activity.lead_id == mapping.lead_id,
                Activity.user_metadata["fub_note_id"].as_string() == str(fub_note_id)
            ).first()
            if existing:
                return existing.id

        # Resolve organization_id (required NOT NULL on activities)
        from database.models import Lead as _Lead
        _lead = self.db.query(_Lead).filter(_Lead.id == mapping.lead_id).first()
        org_id = _lead.organization_id if _lead else None

        # Log sync event
        sync_event = FUBSyncEvent(
            connection_id=connection.id,
            event_type=FUBEventType.NOTES_CREATED.value,
            direction=FUBSyncDirection.INBOUND.value,
            fub_entity_type="notes",
            fub_entity_id=fub_note_id,
            status=FUBSyncStatus.IN_PROGRESS.value,
            request_payload=fub_note
        )
        self.db.add(sync_event)
        self.db.flush()

        try:
            # Create activity
            activity = Activity(
                type=ActivityType.NOTE,
                organization_id=org_id,
                lead_id=mapping.lead_id,
                user_id=connection.user_id,
                content=fub_note.get("body", ""),
            )

            # Store FUB note ID in metadata
            activity.user_metadata = {
                "fub_note_id": fub_note_id,
                "fub_subject": fub_note.get("subject"),
                "synced_from": "followupboss"
            }

            self.db.add(activity)

            # Update sync event
            sync_event.crm_entity_type = "activity"
            sync_event.crm_entity_id = activity.id
            sync_event.status = FUBSyncStatus.COMPLETED.value
            sync_event.completed_at = datetime.now(timezone.utc)

            self.db.commit()

            logger.info(f"Synced FUB note {fub_note_id} to activity {activity.id}")
            return activity.id

        except Exception as e:
            logger.exception(f"Error syncing FUB note: {e}")
            sync_event.status = FUBSyncStatus.FAILED.value
            sync_event.error_message = str(e)
            try:
                self.db.commit()
            except Exception:
                self.db.rollback()
            return None

    # =========================================================================
    # OUTBOUND SYNC (CRM → FUB)
    # =========================================================================

    def sync_lead_to_fub(
        self,
        lead_id: int,
        changed_fields: Optional[List[str]] = None
    ) -> bool:
        """
        Sync CRM lead changes to FUB.

        Args:
            lead_id: Lead ID
            changed_fields: List of changed field names (optional)

        Returns:
            True if sync successful
        """
        from database.models import Lead

        lead = self.db.query(Lead).filter(Lead.id == lead_id).first()
        if not lead:
            logger.error(f"Lead {lead_id} not found")
            return False

        if not lead.owner_id:
            logger.warning(f"Lead {lead_id} has no owner")
            return False

        # Get FUB connection for lead owner
        connection = self.get_connection(lead.owner_id)
        if not connection or not connection.sync_enabled:
            return False

        # Get existing mapping
        mapping = self.db.query(FUBLeadMapping).filter(
            FUBLeadMapping.lead_id == lead_id
        ).first()

        if not mapping:
            logger.debug(f"Lead {lead_id} not linked to FUB")
            return False

        # Log sync event
        sync_event = FUBSyncEvent(
            connection_id=connection.id,
            event_type=FUBEventType.MANUAL_SYNC.value,
            direction=FUBSyncDirection.OUTBOUND.value,
            crm_entity_type="lead",
            crm_entity_id=lead_id,
            fub_entity_type="people",
            fub_entity_id=mapping.fub_person_id,
            status=FUBSyncStatus.IN_PROGRESS.value
        )
        self.db.add(sync_event)
        self.db.flush()

        try:
            client = self.get_client(connection)

            # Build update payload
            data = {}

            if not changed_fields or "first_name" in changed_fields:
                data["firstName"] = lead.first_name
            if not changed_fields or "last_name" in changed_fields:
                data["lastName"] = lead.last_name
            if not changed_fields or "email" in changed_fields:
                if lead.email:
                    data["emails"] = format_emails_for_fub(lead.email)
            if not changed_fields or "phone" in changed_fields:
                if lead.phone:
                    data["phones"] = format_phones_for_fub(lead.phone)
            if not changed_fields or "source" in changed_fields:
                data["source"] = lead.source
            if not changed_fields or "address" in changed_fields:
                data["propertyStreet"] = lead.address
            if not changed_fields or "city" in changed_fields:
                data["propertyCity"] = lead.city
            if not changed_fields or "state" in changed_fields:
                data["propertyState"] = lead.state
            if not changed_fields or "zip_code" in changed_fields:
                data["propertyZip"] = lead.zip_code
            if not changed_fields or "loan_amount" in changed_fields:
                if lead.loan_amount:
                    data["price"] = lead.loan_amount

            # Stage mapping
            if not changed_fields or "stage" in changed_fields:
                if lead.stage and connection.sync_stages:
                    stage_mappings = self.get_reverse_stage_mappings(connection.id)
                    crm_stage = lead.stage.value if hasattr(lead.stage, 'value') else str(lead.stage)
                    if crm_stage in stage_mappings:
                        data["stage"] = stage_mappings[crm_stage]

            if data:
                sync_event.request_payload = data
                response = client.update_person(mapping.fub_person_id, data)
                sync_event.response_payload = response

            # Update mapping
            mapping.last_synced_at = datetime.now(timezone.utc)
            mapping.sync_direction = FUBSyncDirection.OUTBOUND.value

            sync_event.status = FUBSyncStatus.COMPLETED.value
            sync_event.completed_at = datetime.now(timezone.utc)

            self.db.commit()

            logger.info(f"Synced lead {lead_id} to FUB person {mapping.fub_person_id}")
            return True

        except Exception as e:
            logger.exception(f"Error syncing lead {lead_id} to FUB: {e}")
            sync_event.status = FUBSyncStatus.FAILED.value
            sync_event.error_message = str(e)
            sync_event.completed_at = datetime.now(timezone.utc)
            try:
                self.db.commit()
            except Exception:
                self.db.rollback()
            return False

    def sync_activity_to_fub(self, activity_id: int) -> bool:
        """
        Sync CRM activity/note to FUB.

        Args:
            activity_id: Activity ID

        Returns:
            True if sync successful
        """
        from database.enums import ActivityType
        from database.models import Activity

        activity = self.db.query(Activity).filter(Activity.id == activity_id).first()
        if not activity:
            logger.error(f"Activity {activity_id} not found")
            return False

        # Only sync notes
        if activity.type != ActivityType.NOTE:
            return False

        if not activity.lead_id:
            return False

        # Check if already synced from FUB
        if activity.user_metadata and activity.user_metadata.get("synced_from") == "followupboss":
            return False

        # Get lead mapping
        mapping = self.db.query(FUBLeadMapping).filter(
            FUBLeadMapping.lead_id == activity.lead_id
        ).first()

        if not mapping:
            logger.debug(f"Lead {activity.lead_id} not linked to FUB")
            return False

        connection = self.db.query(FUBUserConnection).filter(
            FUBUserConnection.id == mapping.connection_id
        ).first()

        if not connection or not connection.sync_enabled or not connection.sync_notes:
            return False

        # Log sync event
        sync_event = FUBSyncEvent(
            connection_id=connection.id,
            event_type="activity_created",
            direction=FUBSyncDirection.OUTBOUND.value,
            crm_entity_type="activity",
            crm_entity_id=activity_id,
            fub_entity_type="notes",
            status=FUBSyncStatus.IN_PROGRESS.value
        )
        self.db.add(sync_event)
        self.db.flush()

        try:
            client = self.get_client(connection)

            # Create note in FUB
            response = client.create_note(
                person_id=mapping.fub_person_id,
                body=activity.content or "",
                subject=f"Note from Perennia CRM"
            )

            sync_event.fub_entity_id = response.get("id")
            sync_event.response_payload = response
            sync_event.status = FUBSyncStatus.COMPLETED.value
            sync_event.completed_at = datetime.now(timezone.utc)

            # Mark activity as synced
            if not activity.user_metadata:
                activity.user_metadata = {}
            activity.user_metadata["fub_synced"] = True
            activity.user_metadata["fub_note_id"] = response.get("id")

            self.db.commit()

            logger.info(f"Synced activity {activity_id} to FUB note {response.get('id')}")
            return True

        except Exception as e:
            logger.exception(f"Error syncing activity {activity_id} to FUB: {e}")
            sync_event.status = FUBSyncStatus.FAILED.value
            sync_event.error_message = str(e)
            try:
                self.db.commit()
            except Exception:
                self.db.rollback()
            return False

    def _sync_fub_event_to_activity(
        self,
        connection: FUBUserConnection,
        fub_event: Dict,
        lead_id: int,
        org_id: Optional[int] = None,
    ) -> None:
        """Sync a single FUB event (Email/SMS/Call) to a CRM Activity, deduplicating by fub_event_id."""
        from database.enums import ActivityType
        from database.models import Activity

        fub_event_id = fub_event.get("id")
        event_type_str = fub_event.get("type", "")

        type_map = {
            "Email": ActivityType.EMAIL,
            "SMS": ActivityType.SMS,
            "Call": ActivityType.CALL,
        }
        activity_type = type_map.get(event_type_str)
        if not activity_type or not fub_event_id:
            return

        # Deduplicate: skip if already imported (use JSON path operator ->>)
        existing = self.db.query(Activity).filter(
            Activity.lead_id == lead_id,
            Activity.user_metadata["fub_event_id"].as_string() == str(fub_event_id)
        ).first()
        if existing:
            return

        try:
            activity = Activity(
                type=activity_type,
                organization_id=org_id,
                lead_id=lead_id,
                user_id=connection.user_id,
                content=fub_event.get("description") or fub_event.get("body") or "",
            )
            activity.user_metadata = {
                "fub_event_id": fub_event_id,
                "fub_event_type": event_type_str,
                "synced_from": "followupboss",
            }
            self.db.add(activity)
            self.db.commit()
        except Exception as e:
            logger.warning(f"Failed to create activity for FUB event {fub_event_id}: {e}")
            self.db.rollback()

    # =========================================================================
    # FULL SYNC
    # =========================================================================

    def full_sync_from_fub(
        self,
        connection: FUBUserConnection,
        limit: int = 500
    ) -> Dict[str, int]:
        """
        Pull all assigned leads from FUB with pagination.

        Args:
            connection: FUB connection
            limit: Max leads to sync total

        Returns:
            Stats dict with counts
        """
        client = self.get_client(connection)

        stats = {
            "total": 0,
            "created": 0,
            "updated": 0,
            "errors": 0
        }

        try:
            # Look up org_id once — avoids per-lead query and satisfies NOT NULL constraint
            org_id = self._get_user_org_id(connection.user_id)

            offset = 0
            page_size = min(limit, 100)  # FUB API max per page

            while stats["total"] < limit:
                # Fetch all people in account (no user filter) — FUB admin accounts own all contacts
                result = client.get_people(
                    limit=page_size,
                    offset=offset,
                )

                people = result.get("people", [])
                if not people:
                    break  # No more results

                for person in people:
                    fub_person_id = person.get("id")
                    try:
                        lead_id, is_new = self.sync_person_to_lead(
                            connection,
                            person,
                            event_type=FUBEventType.MANUAL_SYNC.value,
                            organization_id=org_id,
                        )
                    except Exception as person_err:
                        logger.exception(f"Unexpected error syncing FUB person {fub_person_id}: {person_err}")
                        lead_id, is_new = None, False

                    if lead_id:
                        if is_new:
                            stats["created"] += 1
                        else:
                            stats["updated"] += 1

                        # Pull notes for this person and sync to CRM activities
                        if fub_person_id and connection.sync_notes:
                            try:
                                notes_result = client.get_notes(person_id=fub_person_id, limit=50)
                                for note in notes_result.get("notes", []):
                                    self.sync_note_to_activity(connection, note)
                            except Exception as notes_err:
                                logger.warning(f"Failed to sync notes for FUB person {fub_person_id}: {notes_err}")

                        # Pull email/SMS/call events for this person
                        if fub_person_id:
                            for event_type_str in ("Email", "SMS", "Call"):
                                try:
                                    events_result = client.get_events(
                                        person_id=fub_person_id,
                                        event_type=event_type_str,
                                        limit=20,
                                    )
                                    for event in events_result.get("events", []):
                                        self._sync_fub_event_to_activity(connection, event, lead_id, org_id)
                                except Exception as ev_err:
                                    logger.warning(f"Failed to sync {event_type_str} events for FUB person {fub_person_id}: {ev_err}")
                    else:
                        stats["errors"] += 1

                stats["total"] += len(people)
                offset += len(people)

                # Stop if we got fewer results than requested (last page)
                if len(people) < page_size:
                    break

            # Update connection last sync
            connection.last_sync_at = datetime.now(timezone.utc)
            connection.last_sync_status = "completed"
            self.db.commit()

        except Exception as e:
            logger.exception(f"Error in full sync: {e}")
            connection.last_sync_status = "failed"
            connection.last_error = str(e)
            try:
                self.db.commit()
            except Exception:
                self.db.rollback()

        return stats
