"""
Salesforce Sync Engine
Handles bidirectional data synchronization using user-specific field mappings
"""
import hashlib
import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from urllib.parse import quote
import httpx

from sqlalchemy.orm import Session

from salesforce_integration_models import (
    IntegrationProfile,
    FieldMapping,
    IntegrationEvent,
    IntegrationRecordTracking,
    SyncQueueItem
)
from .oauth_service import salesforce_oauth
from .field_mapping_service import field_mapping

logger = logging.getLogger(__name__)


class SyncResult:
    """Result of a sync operation"""
    def __init__(self):
        self.success = False
        self.records_processed = 0
        self.records_succeeded = 0
        self.records_failed = 0
        self.errors: List[Dict[str, str]] = []
        self.duration_ms = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'success': self.success,
            'records_processed': self.records_processed,
            'records_succeeded': self.records_succeeded,
            'records_failed': self.records_failed,
            'errors': self.errors,
            'duration_ms': self.duration_ms
        }


class SalesforceSyncService:
    """Handles bidirectional data synchronization"""

    async def sync(
        self,
        db: Session,
        integration_profile_id: int,
        direction: str = 'bidirectional',
        objects: Optional[List[str]] = None,
        full_sync: bool = False,
        batch_size: int = 200
    ) -> SyncResult:
        """Execute sync for a user's integration"""
        start_time = datetime.utcnow()
        result = SyncResult()

        try:
            # Verify integration is active
            profile = db.query(IntegrationProfile).filter(
                IntegrationProfile.id == integration_profile_id
            ).first()

            if not profile or profile.status != 'active':
                raise ValueError("Integration is not active")

            # Get access token
            access_token, instance_url = await salesforce_oauth.get_access_token(
                db, integration_profile_id
            )

            # Get enabled field mappings
            mappings = field_mapping.get_mappings(
                db, integration_profile_id, enabled=True
            )

            if not mappings:
                raise ValueError("No field mappings configured")

            # Group mappings by source object
            mappings_by_object = self._group_mappings_by_object(mappings)

            # Sync each object
            for object_name, object_mappings in mappings_by_object.items():
                if objects and object_name not in objects:
                    continue

                object_result = await self._sync_object(
                    db=db,
                    access_token=access_token,
                    instance_url=instance_url,
                    integration_profile_id=integration_profile_id,
                    object_name=object_name,
                    mappings=object_mappings,
                    direction=direction,
                    full_sync=full_sync,
                    batch_size=batch_size
                )

                result.records_processed += object_result.records_processed
                result.records_succeeded += object_result.records_succeeded
                result.records_failed += object_result.records_failed
                result.errors.extend(object_result.errors)

            # Update profile
            profile.last_sync_at = datetime.utcnow()
            profile.last_error = None
            db.commit()

            result.success = True
            result.duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            # Log success event
            event = IntegrationEvent(
                integration_profile_id=integration_profile_id,
                event_type='sync_completed',
                status='success',
                records_processed=result.records_processed,
                records_succeeded=result.records_succeeded,
                records_failed=result.records_failed,
                duration_ms=result.duration_ms,
                event_data={
                    'direction': direction,
                    'full_sync': full_sync,
                    'objects_synced': len(mappings_by_object)
                }
            )
            db.add(event)
            db.commit()

        except Exception as e:
            result.duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            # Log failure event
            event = IntegrationEvent(
                integration_profile_id=integration_profile_id,
                event_type='sync_failed',
                status='error',
                error_message=str(e),
                duration_ms=result.duration_ms
            )
            db.add(event)

            # Update profile with error
            profile = db.query(IntegrationProfile).filter(
                IntegrationProfile.id == integration_profile_id
            ).first()
            if profile:
                profile.last_error = str(e)
            db.commit()

            raise

        return result

    async def _sync_object(
        self,
        db: Session,
        access_token: str,
        instance_url: str,
        integration_profile_id: int,
        object_name: str,
        mappings: List[FieldMapping],
        direction: str,
        full_sync: bool,
        batch_size: int
    ) -> SyncResult:
        """Sync a specific Salesforce object"""
        result = SyncResult()

        try:
            # Build SOQL query
            soql = self._build_soql_query(object_name, mappings, full_sync, batch_size)

            # Query Salesforce
            records = await self._query_records(access_token, instance_url, soql)

            # Transform and upsert each record
            for record in records:
                try:
                    await self._process_record(
                        db=db,
                        integration_profile_id=integration_profile_id,
                        object_name=object_name,
                        record=record,
                        mappings=mappings
                    )
                    result.records_succeeded += 1
                except Exception as e:
                    result.records_failed += 1
                    result.errors.append({
                        'record_id': record.get('Id', 'N/A'),
                        'error': str(e)
                    })

                result.records_processed += 1

            result.success = result.records_failed == 0

        except Exception as e:
            result.success = False
            result.errors.append({
                'record_id': 'N/A',
                'error': str(e)
            })

        return result

    def _build_soql_query(
        self,
        object_name: str,
        mappings: List[FieldMapping],
        full_sync: bool,
        batch_size: int
    ) -> str:
        """Build SOQL query based on field mappings"""
        # Get all source fields to query
        fields = ['Id']
        fields.extend(set(m.source_field for m in mappings))

        # Base query
        soql = f"SELECT {', '.join(fields)} FROM {object_name}"

        # Add WHERE clause for incremental sync
        if not full_sync:
            soql += " WHERE LastModifiedDate >= LAST_N_DAYS:1"

        # Add ORDER BY for consistent pagination
        soql += " ORDER BY LastModifiedDate ASC"

        # Add LIMIT for batch processing
        soql += f" LIMIT {batch_size}"

        return soql

    async def _query_records(
        self,
        access_token: str,
        instance_url: str,
        soql: str
    ) -> List[Dict[str, Any]]:
        """Query records from Salesforce"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{instance_url}/services/data/v60.0/query",
                params={'q': soql},
                headers={
                    'Authorization': f'Bearer {access_token}',
                    'Content-Type': 'application/json'
                }
            )

            if response.status_code != 200:
                error = response.text
                raise ValueError(f"Salesforce query failed: {error}")

            data = response.json()
            return data.get('records', [])

    async def _process_record(
        self,
        db: Session,
        integration_profile_id: int,
        object_name: str,
        record: Dict[str, Any],
        mappings: List[FieldMapping]
    ):
        """Process and transform a single record"""
        # Group mappings by target entity
        entity_mappings = self._group_mappings_by_entity(mappings)

        # Transform and upsert each entity
        for target_entity, entity_maps in entity_mappings.items():
            transformed_data = self._transform_record(record, entity_maps)

            # Upsert into CRM
            await self._upsert_record(
                db=db,
                integration_profile_id=integration_profile_id,
                target_entity=target_entity,
                source_object=object_name,
                source_record_id=record['Id'],
                data=transformed_data
            )

            # Log sync event
            event = IntegrationEvent(
                integration_profile_id=integration_profile_id,
                event_type='record_synced',
                direction='inbound',
                source_object=object_name,
                source_record_id=record['Id'],
                target_entity=target_entity,
                status='success',
                event_data={
                    'fields_transformed': len(transformed_data)
                }
            )
            db.add(event)
            db.commit()

    def _transform_record(
        self,
        source_record: Dict[str, Any],
        mappings: List[FieldMapping]
    ) -> Dict[str, Any]:
        """Transform a Salesforce record using field mappings"""
        transformed = {}

        for mapping in mappings:
            source_value = source_record.get(mapping.source_field)

            try:
                transformed_value = field_mapping.transform_value(
                    source_value,
                    mapping.transform_type,
                    mapping.transform_config
                )
                transformed[mapping.target_field] = transformed_value
            except Exception as e:
                # Use default value if transformation fails
                if mapping.default_value is not None:
                    transformed[mapping.target_field] = mapping.default_value
                elif mapping.required:
                    raise ValueError(
                        f"Failed to transform required field {mapping.source_field}: {str(e)}"
                    )

        return transformed

    async def _upsert_record(
        self,
        db: Session,
        integration_profile_id: int,
        target_entity: str,
        source_object: str,
        source_record_id: str,
        data: Dict[str, Any]
    ):
        """Upsert record into CRM and track for change detection"""
        # Generate sync hash for change detection
        sync_hash = self._generate_sync_hash(data)

        # Check for existing tracking record
        tracking = db.query(IntegrationRecordTracking).filter(
            IntegrationRecordTracking.integration_profile_id == integration_profile_id,
            IntegrationRecordTracking.source_object == source_object,
            IntegrationRecordTracking.source_record_id == source_record_id
        ).first()

        if tracking:
            # Check if data actually changed
            if tracking.sync_hash == sync_hash:
                return  # No change, skip upsert

            tracking.last_synced_at = datetime.utcnow()
            tracking.sync_hash = sync_hash
        else:
            tracking = IntegrationRecordTracking(
                integration_profile_id=integration_profile_id,
                source_object=source_object,
                source_record_id=source_record_id,
                target_entity=target_entity,
                last_synced_at=datetime.utcnow(),
                sync_hash=sync_hash
            )
            db.add(tracking)

        # Upsert into appropriate CRM table based on entity
        target_record_id = await self._upsert_to_crm(
            db=db,
            integration_profile_id=integration_profile_id,
            target_entity=target_entity,
            data=data,
            tracking_id=tracking.id if tracking.id else None
        )

        if target_record_id:
            tracking.target_record_id = target_record_id

        db.commit()

    async def _upsert_to_crm(
        self,
        db: Session,
        integration_profile_id: int,
        target_entity: str,
        data: Dict[str, Any],
        tracking_id: Optional[int]
    ) -> Optional[int]:
        """
        Upsert record into the appropriate CRM table.
        This is a placeholder that should be customized based on your CRM schema.
        """
        # Get user who owns this integration
        profile = db.query(IntegrationProfile).filter(
            IntegrationProfile.id == integration_profile_id
        ).first()

        if not profile:
            raise ValueError("Integration profile not found")

        # Add user ownership and source tracking
        data['user_id'] = profile.user_id
        data['integration_tracking_id'] = tracking_id
        data['source'] = 'salesforce'

        # The actual upsert logic depends on your CRM schema
        # Here's a placeholder that logs the operation
        logger.info(f"Upserting to {target_entity}: {json.dumps(data, default=str)[:200]}...")

        # In production, you would:
        # 1. Look up the appropriate model based on target_entity
        # 2. Find existing record by email/phone/unique identifier
        # 3. Create or update the record

        # Example for borrower entity:
        # if target_entity == 'borrower':
        #     borrower = db.query(Borrower).filter(
        #         Borrower.email == data.get('email')
        #     ).first()
        #     if borrower:
        #         for key, value in data.items():
        #             if hasattr(borrower, key):
        #                 setattr(borrower, key, value)
        #     else:
        #         borrower = Borrower(**data)
        #         db.add(borrower)
        #     db.commit()
        #     return borrower.id

        return None

    def _group_mappings_by_object(
        self,
        mappings: List[FieldMapping]
    ) -> Dict[str, List[FieldMapping]]:
        """Group mappings by source object"""
        result = {}
        for mapping in mappings:
            obj = mapping.source_object
            if obj not in result:
                result[obj] = []
            result[obj].append(mapping)
        return result

    def _group_mappings_by_entity(
        self,
        mappings: List[FieldMapping]
    ) -> Dict[str, List[FieldMapping]]:
        """Group mappings by target entity"""
        result = {}
        for mapping in mappings:
            entity = mapping.target_entity
            if entity not in result:
                result[entity] = []
            result[entity].append(mapping)
        return result

    def _generate_sync_hash(self, data: Dict[str, Any]) -> str:
        """Generate MD5 hash for change detection"""
        data_string = json.dumps(data, sort_keys=True, default=str)
        return hashlib.md5(data_string.encode()).hexdigest()

    async def process_queue(self, db: Session, limit: int = 10):
        """Process pending items from the sync queue"""
        items = db.query(SyncQueueItem).filter(
            SyncQueueItem.status == 'pending',
            SyncQueueItem.attempts < SyncQueueItem.max_attempts
        ).order_by(
            SyncQueueItem.priority.desc(),
            SyncQueueItem.scheduled_for
        ).limit(limit).all()

        for item in items:
            item.status = 'processing'
            item.started_at = datetime.utcnow()
            item.attempts += 1
            db.commit()

            try:
                if item.operation == 'schema_refresh':
                    from .schema_service import salesforce_schema
                    await salesforce_schema.discover_schema(db, item.integration_profile_id)
                elif item.operation in ('full_sync', 'incremental_sync'):
                    await self.sync(
                        db=db,
                        integration_profile_id=item.integration_profile_id,
                        full_sync=(item.operation == 'full_sync'),
                        objects=[item.source_object] if item.source_object else None
                    )
                elif item.operation == 'single_record':
                    # Handle single record sync
                    pass

                item.status = 'completed'
                item.completed_at = datetime.utcnow()
                item.result = {'success': True}

            except Exception as e:
                if item.attempts >= item.max_attempts:
                    item.status = 'failed'
                else:
                    item.status = 'retry'
                item.error_message = str(e)

            db.commit()


# Export singleton instance
salesforce_sync = SalesforceSyncService()
