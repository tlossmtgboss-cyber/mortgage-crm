"""
Salesforce Sync Engine
Handles INBOUND data synchronization: Salesforce → CRM

Data flows ONE WAY: Salesforce → CRM
- Matches CRM clients to Salesforce records by EMAIL
- When matched, pulls ALL fields (text, number, date) from Salesforce to CRM
- Syncs emails, calendar events, tasks from Salesforce
- NO data is pushed from CRM to Salesforce

Sync runs automatically every 5 minutes via APScheduler.
"""
import functools
import hashlib
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from urllib.parse import quote
import httpx

from sqlalchemy import text
from sqlalchemy.orm import Session

from salesforce_integration_models import (
    IntegrationProfile,
    FieldMapping,
    IntegrationEvent,
    IntegrationRecordTracking,
    SyncQueueItem
)
from .oauth_service import salesforce_oauth
from .stage_mapping import map_salesforce_stage, map_salesforce_lead_stage, SALESFORCE_STAGE_MAPPING


# SalesforceTokenExpiredError extracted to _auth.py — re-exported for backwards compatibility
from ._auth import SalesforceTokenExpiredError
from .field_mapping_service import field_mapping
from .http_client import get_sf_client, SF_TIMEOUT

logger = logging.getLogger(__name__)

# SOQL helpers extracted to _queries.py — re-exported here for backwards compatibility
from ._queries import (
    SF_API_VERSION,
    SAFE_SOQL_IDENTIFIER,
    _validate_soql_identifier,
    _get_org_id_for_user,
    _sanitize_soql_string,
    _sanitize_soql_email,
)


# SyncResult extracted to _state.py — re-exported for backwards compatibility
from ._state import SyncResult

# Pure mapping helpers extracted to _mapping.py
from ._mapping import (
    map_crm_stage_to_salesforce,
    map_crm_lead_stage_to_salesforce,
    remap_loan_fields_for_lead,
    group_mappings_by_object,
    group_mappings_by_entity,
)

# Outbound (CRM → Salesforce) push handlers extracted to _webhooks.py
from ._webhooks import OutboundSyncMixin


class SalesforceSyncService(OutboundSyncMixin):
    """Handles bidirectional data synchronization"""

    # Circuit breaker: max consecutive failures before auto-disabling sync
    MAX_CONSECUTIVE_FAILURES = 5
    # Cooldown period after circuit opens (minutes)
    CIRCUIT_COOLDOWN_MINUTES = 30

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
        start_time = datetime.now(timezone.utc)
        result = SyncResult()

        try:
            # Verify integration is active
            profile = db.query(IntegrationProfile).filter(
                IntegrationProfile.id == integration_profile_id
            ).first()

            if not profile or profile.status != 'active':
                raise ValueError("Integration is not active")

            # Circuit breaker: check consecutive failure count
            consecutive_failures = (profile.sync_metadata or {}).get('consecutive_failures', 0)
            last_failure_at = (profile.sync_metadata or {}).get('last_failure_at')
            if consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
                # Check if cooldown has elapsed
                if last_failure_at:
                    cooldown_until = datetime.fromisoformat(last_failure_at) + timedelta(minutes=self.CIRCUIT_COOLDOWN_MINUTES)
                    if datetime.now(timezone.utc) < cooldown_until:
                        logger.warning(
                            f"Circuit breaker OPEN for profile {integration_profile_id}: "
                            f"{consecutive_failures} consecutive failures, cooldown until {cooldown_until.isoformat()}"
                        )
                        result.errors.append({
                            'error': f'Circuit breaker open: {consecutive_failures} consecutive failures',
                            'cooldown_until': cooldown_until.isoformat(),
                        })
                        return result
                    else:
                        logger.info(f"Circuit breaker half-open for profile {integration_profile_id}: attempting retry after cooldown")
                else:
                    logger.info(f"Circuit breaker half-open (no timestamp): attempting retry")

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

            # Sync each object (with 401 retry)
            _token_refreshed = False
            for object_name, object_mappings in mappings_by_object.items():
                if objects and object_name not in objects:
                    continue

                try:
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
                except SalesforceTokenExpiredError:
                    if not _token_refreshed:
                        logger.info(f"SF token expired during field-mapping sync, refreshing...")
                        access_token, instance_url = await salesforce_oauth.force_refresh_and_get_token(
                            db, integration_profile_id
                        )
                        _token_refreshed = True
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
                    else:
                        raise

                result.records_processed += object_result.records_processed
                result.records_succeeded += object_result.records_succeeded
                result.records_failed += object_result.records_failed
                result.errors.extend(object_result.errors)

            # Update profile — reset circuit breaker on success
            profile.last_sync_at = datetime.now(timezone.utc)
            profile.last_error = None
            metadata = profile.sync_metadata or {}
            metadata['consecutive_failures'] = 0
            metadata.pop('last_failure_at', None)
            profile.sync_metadata = metadata
            db.commit()

            # Backfill organization_id for any records missing it
            try:
                from services.tenant_isolation import backfill_organization_id_for_user
                user_row = db.execute(text("""
                    SELECT user_id, u.organization_id
                    FROM integration_profiles ip
                    JOIN users u ON u.id = ip.user_id
                    WHERE ip.id = :profile_id
                """), {"profile_id": integration_profile_id}).fetchone()
                if user_row and user_row.organization_id:
                    backfill_organization_id_for_user(db, user_row.user_id, user_row.organization_id)
            except Exception as backfill_err:
                logger.warning(f"Post-sync org backfill failed (non-fatal): {backfill_err}")

            result.success = True
            result.duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

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
            result.duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

            # Log failure event
            event = IntegrationEvent(
                integration_profile_id=integration_profile_id,
                event_type='sync_failed',
                status='error',
                error_message=str(e),
                duration_ms=result.duration_ms
            )
            db.add(event)

            # Update profile with error — increment circuit breaker counter
            profile = db.query(IntegrationProfile).filter(
                IntegrationProfile.id == integration_profile_id
            ).first()
            if profile:
                profile.last_error = str(e)
                metadata = profile.sync_metadata or {}
                metadata['consecutive_failures'] = metadata.get('consecutive_failures', 0) + 1
                metadata['last_failure_at'] = datetime.now(timezone.utc).isoformat()
                profile.sync_metadata = metadata
                if metadata['consecutive_failures'] >= self.MAX_CONSECUTIVE_FAILURES:
                    logger.error(
                        f"Circuit breaker TRIPPED for profile {integration_profile_id}: "
                        f"{metadata['consecutive_failures']} consecutive failures"
                    )
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

            # Transform and upsert each record using savepoints for per-record
            # error isolation (Fix 5). The outer transaction in sync() commits once.
            for record in records:
                savepoint = db.begin_nested()  # Creates a SAVEPOINT
                try:
                    await self._process_record(
                        db=db,
                        integration_profile_id=integration_profile_id,
                        object_name=object_name,
                        record=record,
                        mappings=mappings
                    )
                    savepoint.commit()  # Release savepoint (doesn't commit outer txn)
                    result.records_succeeded += 1
                except Exception as e:
                    savepoint.rollback()  # Rollback just this record's changes
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
        """Build SOQL query based on field mappings.

        Fix 1a: Validates object_name and all field names as safe SOQL identifiers
        to prevent SOQL injection via user-configurable FieldMapping values.
        """
        # Validate object name (Fix 1a)
        _validate_soql_identifier(object_name, "object name")

        # Get all source fields to query, validating each one (Fix 1a)
        fields = ['Id']
        for m in mappings:
            _validate_soql_identifier(m.source_field, "field name")
            fields.append(m.source_field)
        fields = list(dict.fromkeys(fields))  # deduplicate while preserving order

        # Validate batch_size is a reasonable integer
        batch_size = max(1, min(int(batch_size), 2000))

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
        soql: str,
        max_records: int = 10000,
    ) -> List[Dict[str, Any]]:
        """Query records from Salesforce with automatic pagination.

        Enterprise Readiness Check 7.8: SOQL Pagination

        Salesforce returns a maximum of 2,000 records per response. If
        more records exist, the response includes a ``nextRecordsUrl``
        that must be followed to retrieve subsequent pages.

        This method transparently follows ``nextRecordsUrl`` links until
        all records are retrieved or ``max_records`` is reached.

        Args:
            access_token: Salesforce OAuth access token.
            instance_url: Salesforce instance base URL.
            soql: The SOQL query string.
            max_records: Safety limit to prevent unbounded fetches (default 10,000).

        Returns:
            List of all record dicts across all pages.
        """
        all_records: List[Dict[str, Any]] = []
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }

        async with get_sf_client() as client:
            # Initial query
            response = await client.get(
                f"{instance_url}/services/data/{SF_API_VERSION}/query",
                params={'q': soql},
                headers=headers,
            )

            if response.status_code == 401:
                raise SalesforceTokenExpiredError(f"Salesforce query returned 401: {response.text[:200]}")
            if response.status_code != 200:
                error = response.text
                raise ValueError(f"Salesforce query failed: {error}")

            data = response.json()
            records = data.get('records', [])
            all_records.extend(records)
            total_size = data.get('totalSize', len(records))

            # Follow nextRecordsUrl for pagination (Check 7.8)
            next_url = data.get('nextRecordsUrl')
            page_count = 1

            while next_url and len(all_records) < max_records:
                page_count += 1
                # nextRecordsUrl is a relative path like /services/data/vXX.0/query/01gXXX-2000
                full_url = f"{instance_url}{next_url}"

                response = await client.get(full_url, headers=headers)

                if response.status_code != 200:
                    logger.error(
                        f"Salesforce pagination failed on page {page_count}: "
                        f"{response.status_code} {response.text[:200]}"
                    )
                    break

                data = response.json()
                page_records = data.get('records', [])
                all_records.extend(page_records)
                next_url = data.get('nextRecordsUrl')

                logger.debug(
                    f"SF pagination page {page_count}: {len(page_records)} records "
                    f"(total so far: {len(all_records)}/{total_size})"
                )

            if len(all_records) >= max_records:
                logger.warning(
                    f"Salesforce query hit max_records limit ({max_records}). "
                    f"Total available: {total_size}. Consider narrowing the query."
                )

        logger.info(
            f"Salesforce query complete: {len(all_records)} records "
            f"across {page_count} page(s) (total available: {total_size})"
        )
        return all_records

    # Salesforce fields that carry pipeline status — checked in priority order.
    # The first non-empty value found is used for bucket classification and stage mapping.
    SF_STATUS_FIELDS = [
        'MtgPlanner_CRM__Status__c',   # Custom Jungo/MtgPlanner status field
        'StageName',                     # Standard Opportunity stage
        'Status',                        # Standard Lead status
        'LeadSource',                    # Sometimes carries status info
    ]

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

        # Extract the raw Salesforce status value from the source record.
        # This is needed for bucket classification and stage mapping even when
        # the status field isn't explicitly included in the field mappings.
        raw_sf_status = None
        for sf_field in self.SF_STATUS_FIELDS:
            val = record.get(sf_field)
            if val:
                raw_sf_status = val
                break

        # Transform and upsert each entity
        for target_entity, entity_maps in entity_mappings.items():
            transformed_data = self._transform_record(record, entity_maps)

            # Always include the Salesforce ID
            transformed_data['salesforce_id'] = record.get('Id')

            # Inject the raw SF status so _classify_record_bucket() and
            # stage mapping can use it (unless field mappings already set 'stage')
            if raw_sf_status and not transformed_data.get('stage'):
                transformed_data['_sf_status'] = raw_sf_status

            # Upsert into CRM
            await self._upsert_record(
                db=db,
                integration_profile_id=integration_profile_id,
                target_entity=target_entity,
                source_object=object_name,
                source_record_id=record['Id'],
                data=transformed_data
            )

            # Log sync event (no per-record commit — Fix 5: outer txn commits)
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
        """Upsert record into CRM and track for change detection.

        Fix 3a: Uses INSERT ... ON CONFLICT to eliminate race conditions
        between concurrent sync operations. No per-record commit (Fix 5).
        """
        # Generate sync hash for change detection
        sync_hash = self._generate_sync_hash(data)

        # Check if data changed (quick read before expensive CRM upsert)
        existing_hash = db.execute(text("""
            SELECT sync_hash FROM integration_record_tracking
            WHERE integration_profile_id = :profile_id
              AND source_object = :source_object
              AND source_record_id = :source_record_id
        """), {
            "profile_id": integration_profile_id,
            "source_object": source_object,
            "source_record_id": source_record_id,
        }).scalar()

        if existing_hash == sync_hash:
            return  # No change, skip upsert

        # Upsert into appropriate CRM table based on entity
        target_record_id = await self._upsert_to_crm(
            db=db,
            integration_profile_id=integration_profile_id,
            target_entity=target_entity,
            data=data,
            tracking_id=None
        )

        # Atomic upsert of tracking record (Fix 3a: INSERT ... ON CONFLICT)
        # NOTE: Requires unique constraint on (integration_profile_id, source_object, source_record_id).
        # Migration needed: CREATE UNIQUE INDEX IF NOT EXISTS
        #   idx_irt_profile_object_record ON integration_record_tracking
        #   (integration_profile_id, source_object, source_record_id);
        db.execute(text("""
            INSERT INTO integration_record_tracking
                (integration_profile_id, source_object, source_record_id,
                 target_entity, target_record_id, last_synced_at, sync_hash, sync_status)
            VALUES
                (:profile_id, :source_object, :source_record_id,
                 :target_entity, :target_record_id, :synced_at, :hash, 'synced')
            ON CONFLICT (integration_profile_id, source_object, source_record_id)
            DO UPDATE SET
                target_record_id = EXCLUDED.target_record_id,
                last_synced_at = EXCLUDED.last_synced_at,
                sync_hash = EXCLUDED.sync_hash,
                sync_status = 'synced',
                updated_at = NOW()
        """), {
            "profile_id": integration_profile_id,
            "source_object": source_object,
            "source_record_id": source_record_id,
            "target_entity": target_entity,
            "target_record_id": str(target_record_id) if target_record_id else None,
            "synced_at": datetime.now(timezone.utc),
            "hash": sync_hash,
        })

    async def _upsert_to_crm(
        self,
        db: Session,
        integration_profile_id: int,
        target_entity: str,
        data: Dict[str, Any],
        tracking_id: Optional[int]
    ) -> Optional[int]:
        """
        Upsert record into the appropriate CRM table using smart routing.

        Instead of routing purely by target_entity from field mappings, this
        examines the SF status to determine the correct destination:
        - Prospects/Pre-Approved → leads table
        - Active loans (Application through CTC) → loans table
        - Funded/Closed → loans table + MUM promotion

        Also handles cross-table transitions (e.g., lead → loan promotion).
        """
        from sqlalchemy import text as sa_text

        # Get user who owns this integration
        profile = db.query(IntegrationProfile).filter(
            IntegrationProfile.id == integration_profile_id
        ).first()

        if not profile:
            raise ValueError("Integration profile not found")

        user_id = profile.user_id
        salesforce_id = data.pop('salesforce_id', None)

        # Get org_id for multi-tenant scoping (Fix 8: cached lookup)
        org_id = _get_org_id_for_user(db, user_id)

        # Extract email for cross-table lookup
        email = (
            data.get('email')
            or data.get('borrower_email')
            or data.get('Email')
            or None
        )

        # --- Step 1: Classify where this record SHOULD go ---
        bucket = self._classify_record_bucket(data)

        # --- Step 2: Find if this record already exists anywhere ---
        existing = self._find_existing_record(db, salesforce_id, email, user_id, org_id)

        logger.info(
            f"Smart routing: sf_id={salesforce_id}, target_entity={target_entity}, "
            f"bucket={bucket}, existing={existing}"
        )

        # --- Step 3: Handle transitions and routing ---

        if existing and existing['table'] == 'mum_clients':
            # Already in MUM — update MUM client data only
            try:
                set_parts = []
                mum_data = {}
                if data.get('borrower_name') or data.get('name'):
                    mum_data['client_name'] = data.get('borrower_name') or data.get('name')
                    set_parts.append("client_name = :client_name")
                if data.get('borrower_email') or data.get('email'):
                    mum_data['email'] = data.get('borrower_email') or data.get('email')
                    set_parts.append("email = :email")
                if data.get('borrower_phone') or data.get('phone'):
                    mum_data['phone'] = data.get('borrower_phone') or data.get('phone')
                    set_parts.append("phone = :phone")
                if set_parts:
                    mum_data['mum_id'] = existing['id']
                    mum_data['sf_id'] = salesforce_id
                    set_parts.append("salesforce_id = :sf_id")
                    set_parts.append("updated_at = CURRENT_TIMESTAMP")
                    query = f"""
                        UPDATE mum_clients SET {', '.join(set_parts)}
                        WHERE id = :mum_id
                    """
                    db.execute(sa_text(query), mum_data)
                    logger.info(f"Updated MUM client {existing['id']} from SF {salesforce_id}")
            except Exception as e:
                logger.warning(f"MUM client update failed (non-fatal): {e}")
            return existing['id']

        if existing and existing['table'] == 'loans':
            # Record already exists as a loan
            if bucket == 'lead':
                # SF says prospect but CRM has it as a loan — don't regress
                logger.warning(
                    f"SF record {salesforce_id} is '{data.get('stage', '?')}' "
                    f"but already exists as loan {existing['id']} — not regressing to lead"
                )
                # Still update the loan with latest data (but don't change stage)
                data.pop('stage', None)
                return await self._upsert_loan(db, user_id, salesforce_id, data)
            elif bucket == 'loan_funded':
                # Update loan to funded stage + MUM promotion
                result_id = await self._upsert_loan(db, user_id, salesforce_id, data)
                if result_id:
                    self._try_mum_promotion(db, result_id, user_id)
                return result_id
            else:
                # Normal loan update
                return await self._upsert_loan(db, user_id, salesforce_id, data)

        if existing and existing['table'] == 'leads':
            # Record exists as a lead
            if bucket == 'lead':
                # Same bucket — update lead in place
                # Remap loan fields to lead fields if data came from loan mappings
                if target_entity in ('loan', 'borrower'):
                    lead_data = self._remap_loan_fields_for_lead(data)
                else:
                    lead_data = data
                # Map the SF status to a valid LeadStage value
                sf_status = data.get('stage') or data.get('StageName') or data.get('Status') or data.get('_sf_status')
                if sf_status:
                    lead_data['stage'] = self._map_sf_status_to_lead_stage(sf_status)
                return await self._upsert_lead(db, user_id, salesforce_id, lead_data)
            elif bucket in ('loan', 'loan_funded'):
                # Promote lead → loan
                loan_id = await self._promote_lead_to_loan(
                    db, user_id, salesforce_id, existing['id'], data
                )
                if loan_id and bucket == 'loan_funded':
                    self._try_mum_promotion(db, loan_id, user_id)
                return loan_id

        # --- Step 4: No existing record — create new in correct bucket ---
        if bucket == 'lead':
            # Remap loan fields to lead fields if needed
            if target_entity in ('loan', 'borrower'):
                lead_data = self._remap_loan_fields_for_lead(data)
            else:
                lead_data = data
            # Map SF status to valid LeadStage
            sf_status = data.get('stage') or data.get('StageName') or data.get('Status') or data.get('_sf_status')
            if sf_status:
                lead_data['stage'] = self._map_sf_status_to_lead_stage(sf_status)
            return await self._upsert_lead(db, user_id, salesforce_id, lead_data)
        elif bucket == 'loan_funded':
            loan_id = await self._upsert_loan(db, user_id, salesforce_id, data)
            if loan_id:
                self._try_mum_promotion(db, loan_id, user_id)
            return loan_id
        else:
            # Default: active loan
            return await self._upsert_loan(db, user_id, salesforce_id, data)

    # Valid columns on the leads table that can be set from Salesforce sync
    VALID_LEAD_COLUMNS = {
        # Core identity
        'first_name', 'last_name', 'name', 'email', 'phone',
        'co_applicant_name', 'co_applicant_email', 'co_applicant_phone',
        'preferred_communication',
        # Pipeline
        'stage', 'source',
        # Loan qualification
        'loan_type', 'preapproval_amount', 'credit_score', 'debt_to_income',
        # Assignment
        'loan_number', 'notes',
        # Property
        'address', 'city', 'state', 'zip_code', 'property_type',
        'property_value', 'down_payment', 'property_address',
        # Financial
        'employment_status', 'annual_income', 'monthly_debts', 'first_time_buyer',
        'employer_name', 'industry',
        # Loan details
        'loan_amount', 'interest_rate', 'loan_term', 'apr', 'points',
        'lock_date', 'lock_expiration', 'closing_date', 'lender',
        'loan_officer', 'processor', 'underwriter', 'appraisal_value',
        'ltv', 'cltv', 'dti', 'dti_front', 'dti_back', 'program',
        'loan_purpose', 'file_state',
        # SLA milestones
        'lead_received_date', 'first_contact_attempt_date',
        'first_contact_successful_date', 'lead_qualification_date',
        'application_link_sent_date', 'application_started_date',
        'application_completed_date', 'credit_pulled_date',
        'preapproval_submission_date', 'preapproval_issued_date',
        'preapproval_expiration_date', 'realtor_referral_date',
        'rate_watch_enrollment_date', 'initial_consultation_date',
        # Property details (extended)
        'occupancy_type', 'property_county', 'property_ownership_type',
        'property_units',
        # Financial details (extended)
        'rate_type', 'monthly_payment', 'property_tax', 'hazard_insurance',
        'mortgage_insurance', 'hoa_amount', 'origination_fee',
        'estimated_prepaid_interest', 'index_rate', 'margin',
        # 2nd loan
        'second_loan_amount', 'second_loan_rate', 'second_loan_payment',
        # Housing expenses
        'present_housing_expense', 'proposed_housing_expense',
        'present_monthly_payment', 'proposed_monthly_payment',
        # Referral
        'referral_score',
    }

    async def _upsert_lead(
        self,
        db: Session,
        user_id: int,
        salesforce_id: str,
        data: Dict[str, Any]
    ) -> Optional[int]:
        """Upsert a lead from Salesforce"""
        from sqlalchemy import text
        from datetime import datetime, timezone

        # Get user's organization_id for multi-tenant isolation (Fix 8: cached)
        org_id = _get_org_id_for_user(db, user_id)

        # Check if lead exists by salesforce_id or email (org-scoped)
        existing = None
        if salesforce_id:
            if org_id:
                existing = db.execute(text("""
                    SELECT id FROM leads
                    WHERE (salesforce_id = :sf_id OR meta_data->>'salesforce_id' = :sf_id)
                        AND organization_id = :org_id
                    LIMIT 1
                """), {"sf_id": salesforce_id, "org_id": org_id}).fetchone()
            else:
                existing = db.execute(text("""
                    SELECT id FROM leads
                    WHERE salesforce_id = :sf_id OR meta_data->>'salesforce_id' = :sf_id
                    LIMIT 1
                """), {"sf_id": salesforce_id}).fetchone()

        if not existing and data.get('email'):
            existing = db.execute(text("""
                SELECT id FROM leads
                WHERE LOWER(email) = LOWER(:email) AND owner_id = :user_id
                LIMIT 1
            """), {"email": data.get('email'), "user_id": user_id}).fetchone()

        # Build core identity fields with Salesforce fallbacks
        first_name = data.get('first_name') or data.get('FirstName', '')
        last_name = data.get('last_name') or data.get('LastName', '')
        data['first_name'] = first_name
        data['last_name'] = last_name
        data['name'] = f"{first_name} {last_name}".strip() or 'Unknown'
        if not data.get('email'):
            data['email'] = data.get('Email', '')
        if not data.get('phone'):
            data['phone'] = data.get('Phone', '')
        if not data.get('source'):
            data['source'] = data.get('LeadSource', 'Salesforce')

        # Filter to valid lead columns, drop empty values (keep 'name')
        lead_data = {}
        dropped = []
        for k, v in data.items():
            if k in self.VALID_LEAD_COLUMNS and (v or v == 0 or k == 'name'):
                lead_data[k] = v
            elif k not in self.VALID_LEAD_COLUMNS and k not in (
                'FirstName', 'LastName', 'Email', 'Phone', 'Company',
                'LeadSource', 'target_entity', 'mapping_category',
            ):
                dropped.append(k)

        if dropped:
            logger.warning(f"SF→Lead sync dropped unmapped fields: {dropped}")

        if existing:
            # Update existing lead — also backfill organization_id if missing
            lead_id = existing[0]

            # Capture old stage before update for SLA tracking
            old_stage_row = db.execute(text(
                "SELECT stage::text FROM leads WHERE id = :lid"
            ), {"lid": lead_id}).fetchone()
            old_stage = old_stage_row[0] if old_stage_row else None

            set_clauses = ", ".join([f"{k} = :{k}" for k in lead_data.keys()])
            if set_clauses:
                lead_data['lead_id'] = lead_id
                lead_data['salesforce_id'] = salesforce_id
                lead_data['org_id'] = org_id
                query = f"""
                    UPDATE leads SET {set_clauses},
                        salesforce_id = :salesforce_id,
                        organization_id = COALESCE(organization_id, :org_id),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :lead_id
                """
                db.execute(text(query), lead_data)
            logger.info(f"Updated lead {lead_id} from Salesforce {salesforce_id} ({len(lead_data)} fields)")

            # Wire to SLA tracking — detect stage changes
            new_stage = lead_data.get('stage')
            if new_stage and new_stage != old_stage:
                try:
                    from services.sla_tracking_service import track_lead_stage_change
                    track_lead_stage_change(db, lead_id, old_stage, new_stage, organization_id=org_id)
                except Exception as e:
                    logger.warning(f"SLA tracking hook failed for lead {lead_id} stage change: {e}")

            return lead_id
        else:
            # Create new lead — use INSERT ... ON CONFLICT to guard against race conditions
            # where two concurrent sync requests both pass the SELECT check above and
            # attempt to INSERT a lead with the same salesforce_id. (Fix 3b)
            # NOTE: Requires unique partial index on salesforce_id:
            #   CREATE UNIQUE INDEX IF NOT EXISTS idx_leads_salesforce_id
            #   ON leads(salesforce_id) WHERE salesforce_id IS NOT NULL;
            lead_data['owner_id'] = user_id
            lead_data['salesforce_id'] = salesforce_id
            if not lead_data.get('stage'):
                lead_data['stage'] = 'New'
            lead_data['organization_id'] = org_id

            columns = ", ".join(lead_data.keys())
            placeholders = ", ".join([f":{k}" for k in lead_data.keys()])

            # Build SET clause for the ON CONFLICT update path — update all mapped
            # fields except owner_id and organization_id (preserve originals)
            conflict_set_parts = []
            for k in lead_data.keys():
                if k not in ('owner_id', 'organization_id', 'salesforce_id'):
                    conflict_set_parts.append(f"{k} = EXCLUDED.{k}")
            conflict_set_parts.append("updated_at = CURRENT_TIMESTAMP")
            conflict_set_clause = ", ".join(conflict_set_parts)

            query = f"""
                INSERT INTO leads ({columns}, created_at, updated_at)
                VALUES ({placeholders}, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT (salesforce_id) WHERE salesforce_id IS NOT NULL
                DO UPDATE SET {conflict_set_clause}
                RETURNING id, (xmax = 0) AS was_inserted
            """
            result = db.execute(text(query), lead_data)

            row = result.fetchone()
            lead_id = row[0]
            was_inserted = row[1] if len(row) > 1 else True

            if was_inserted:
                logger.info(f"Created lead {lead_id} from Salesforce {salesforce_id} ({len(lead_data)} fields)")
                # Wire to SLA tracking — create initial milestone for new lead
                try:
                    from services.sla_tracking_service import track_lead_created
                    track_lead_created(db, lead_id, organization_id=org_id)
                except Exception as e:
                    logger.warning(f"SLA tracking hook failed for new lead {lead_id}: {e}")

                # Speed-to-lead hook — triggers AI call / SMS in background
                try:
                    from services.lead_creation_hooks import on_lead_created
                    await on_lead_created(
                        db=db,
                        lead_id=lead_id,
                        organization_id=org_id,
                        source="salesforce_field_sync",
                        owner_id=user_id,
                    )
                except Exception as e:
                    logger.warning(f"Speed-to-lead hook failed for SF lead {lead_id}: {e}")
            else:
                logger.info(
                    f"Lead {lead_id} already existed (race condition resolved via ON CONFLICT) "
                    f"from Salesforce {salesforce_id}"
                )

            return lead_id

    # Valid columns on the loans table that can be set from Salesforce sync
    VALID_LOAN_COLUMNS = {
        # Core borrower info
        'borrower_name', 'borrower_email', 'borrower_phone',
        # Core loan details
        'amount', 'rate', 'loan_type', 'loan_purpose', 'program',
        'loan_number', 'ltv', 'term', 'stage',
        # Core property info
        'property_address', 'property_city', 'property_state',
        'property_zip', 'property_type', 'property_value',
        # Core dates
        'closing_date', 'funded_date', 'application_date', 'lock_expiration_date',
        # Extended - property details
        'occupancy_type', 'property_county', 'property_ownership_type',
        'property_units', 'appraisal_value', 'purchase_price',
        # Extended - financial details
        'rate_type', 'monthly_payment', 'property_tax', 'hazard_insurance',
        'mortgage_insurance', 'hoa_amount', 'origination_fee',
        'estimated_prepaid_interest', 'points', 'index_rate', 'margin',
        # Extended - loan ratios
        'cltv', 'dti', 'apr', 'file_state',
        # Extended - 2nd loan
        'second_loan_amount', 'second_loan_rate', 'second_loan_payment',
        # Extended - housing expenses
        'present_monthly_payment', 'proposed_monthly_payment',
        'present_housing_expense', 'proposed_housing_expense',
        # Additional
        'down_payment', 'credit_score', 'lock_date', 'lender',
        # Audit / sync metadata
        'salesforce_raw_stage',
    }

    async def _upsert_loan(
        self,
        db: Session,
        user_id: int,
        salesforce_id: str,
        data: Dict[str, Any],
        _skip_cross_table: bool = False,
    ) -> Optional[int]:
        """Upsert a loan from Salesforce data (Opportunity or Transaction Property)."""
        from sqlalchemy import text
        import uuid

        # Get user's organization_id for multi-tenant isolation (Fix 8: cached)
        org_id = _get_org_id_for_user(db, user_id)

        # Check if loan exists by salesforce_id (scoped to org for multi-tenant isolation)
        existing = None
        if salesforce_id:
            if org_id:
                existing = db.execute(text("""
                    SELECT id FROM loans
                    WHERE salesforce_id = :sf_id AND organization_id = :org_id
                    LIMIT 1
                """), {"sf_id": salesforce_id, "org_id": org_id}).fetchone()
            else:
                # Legacy fallback: no org assigned yet
                existing = db.execute(text("""
                    SELECT id FROM loans
                    WHERE salesforce_id = :sf_id
                    LIMIT 1
                """), {"sf_id": salesforce_id}).fetchone()

        # Cross-table check: if not found in loans, check if it exists as a lead.
        # If so, promote the lead to a loan instead of creating a duplicate.
        # Skipped when called from _promote_lead_to_loan to prevent recursion.
        if not existing and salesforce_id and not _skip_cross_table:
            if org_id:
                lead_row = db.execute(text("""
                    SELECT id FROM leads
                    WHERE (salesforce_id = :sf_id OR meta_data->>'salesforce_id' = :sf_id)
                        AND organization_id = :org_id
                    LIMIT 1
                """), {"sf_id": salesforce_id, "org_id": org_id}).fetchone()
            else:
                lead_row = db.execute(text("""
                    SELECT id FROM leads
                    WHERE salesforce_id = :sf_id
                       OR meta_data->>'salesforce_id' = :sf_id
                    LIMIT 1
                """), {"sf_id": salesforce_id}).fetchone()

            if lead_row:
                logger.info(
                    f"SF record {salesforce_id} exists as lead {lead_row[0]} — "
                    f"promoting to loan via _upsert_loan cross-table check"
                )
                return await self._promote_lead_to_loan(
                    db, user_id, salesforce_id, lead_row[0], data
                )

        # Build borrower_name from first+last if not directly provided
        if not data.get('borrower_name'):
            first = data.get('borrower_first_name', '')
            last = data.get('borrower_last_name', '')
            combined = f"{first} {last}".strip()
            if combined:
                data['borrower_name'] = combined

        # Coerce amount to float
        if 'amount' in data:
            try:
                data['amount'] = float(data['amount'] or 0)
            except (TypeError, ValueError):
                data['amount'] = 0

        # Map stage from Salesforce — capture raw value for audit
        if data.get('stage'):
            raw_stage = data['stage']
            mapped = self._map_salesforce_stage(raw_stage)
            data['salesforce_raw_stage'] = raw_stage
            if mapped:
                data['stage'] = mapped
            else:
                # Unmapped stage: remove from data so existing stage is preserved on updates,
                # or APPLICATION default applies on creates (line 1088)
                del data['stage']
                logger.warning(f"Unmapped Salesforce stage '{raw_stage}' — preserving existing CRM stage")

        # Filter to only valid loan columns, drop empty values (keep amount even if 0)
        loan_data = {}
        dropped = []
        for k, v in data.items():
            if k in self.VALID_LOAN_COLUMNS and (v or v == 0 or k == 'amount'):
                loan_data[k] = v
            elif k not in self.VALID_LOAN_COLUMNS and k not in (
                'borrower_first_name', 'borrower_last_name',
                'target_entity', 'mapping_category',
            ):
                dropped.append(k)

        if dropped:
            logger.warning(f"SF→Loan sync dropped unmapped fields: {dropped}")

        if existing:
            # Update existing loan — also backfill organization_id if missing
            loan_id = existing[0]

            # Capture old stage before update for SLA tracking
            old_stage_row = db.execute(text(
                "SELECT stage::text, loan_number FROM loans WHERE id = :lid"
            ), {"lid": loan_id}).fetchone()
            old_stage = old_stage_row[0] if old_stage_row else None
            loan_number = old_stage_row[1] if old_stage_row else None

            # Pre-write reconciliation: validate stage transition before writing
            new_stage = loan_data.get('stage')
            reconciliation_result = None
            if new_stage and new_stage != old_stage:
                try:
                    from services.loan_reconciliation_service import LoanReconciliationService, ReconciliationAction
                    recon = LoanReconciliationService(db)
                    reconciliation_result = recon.reconcile(
                        loan_id,
                        old_data={"stage": old_stage, "loan_number": loan_number},
                        new_data={"stage": new_stage, "salesforce_raw_stage": loan_data.get('salesforce_raw_stage')},
                    )
                    if reconciliation_result.action == ReconciliationAction.SKIP:
                        # Idempotent or duplicate — don't overwrite stage
                        loan_data.pop('stage', None)
                        new_stage = None
                        logger.info(f"Reconciliation SKIP for loan {loan_id}: {reconciliation_result.audit_metadata}")
                    elif reconciliation_result.action == ReconciliationAction.FLAG_FOR_REVIEW:
                        # Don't apply stage change; disposition task already created by reconciliation
                        loan_data.pop('stage', None)
                        new_stage = None
                        logger.info(f"Reconciliation FLAG_FOR_REVIEW for loan {loan_id}")
                except Exception as e:
                    logger.warning(f"Pre-write reconciliation failed for loan {loan_id}, proceeding with write: {e}")

            set_parts = [f"{k} = :{k}" for k in loan_data.keys()]
            set_parts.append("salesforce_id = :salesforce_id")
            set_parts.append("organization_id = COALESCE(organization_id, :org_id)")
            set_parts.append("updated_at = CURRENT_TIMESTAMP")

            loan_data['loan_id'] = loan_id
            loan_data['salesforce_id'] = salesforce_id
            loan_data['org_id'] = org_id

            query = f"""
                UPDATE loans SET {', '.join(set_parts)}
                WHERE id = :loan_id
            """
            db.execute(text(query), loan_data)
            logger.info(f"Updated loan {loan_id} from Salesforce {salesforce_id}")

            # Wire to SLA tracking — detect stage changes
            if new_stage and new_stage != old_stage:
                try:
                    from services.sla_tracking_service import track_loan_stage_change
                    track_loan_stage_change(
                        db, loan_id, old_stage, new_stage,
                        loan_number=loan_number, organization_id=org_id
                    )
                except Exception as e:
                    logger.warning(f"SLA tracking hook failed for loan {loan_id} stage change: {e}")

                # MUM promotion: if stage just changed to FUNDED, promote to MUM client
                if new_stage == 'FUNDED' or (reconciliation_result and reconciliation_result.should_promote_mum):
                    self._try_mum_promotion(db, loan_id, user_id)

            return loan_id
        else:
            # Create new loan — use INSERT ... ON CONFLICT to guard against race conditions
            # where two concurrent sync requests both pass the SELECT check above and
            # attempt to INSERT a loan with the same salesforce_id. (Fix 3b)
            # NOTE: Requires unique partial index on salesforce_id:
            #   CREATE UNIQUE INDEX IF NOT EXISTS idx_loans_salesforce_id
            #   ON loans(salesforce_id) WHERE salesforce_id IS NOT NULL;

            # Use loan_number from Salesforce if provided, else generate one
            if not loan_data.get('loan_number'):
                loan_data['loan_number'] = f"SF-{str(uuid.uuid4())[:8].upper()}"

            loan_data['loan_officer_id'] = user_id
            loan_data['salesforce_id'] = salesforce_id
            loan_data['organization_id'] = org_id

            # Ensure required fields have defaults
            if not loan_data.get('borrower_name'):
                loan_data['borrower_name'] = 'Unknown Borrower'
            if not loan_data.get('amount'):
                loan_data['amount'] = 0
            if not loan_data.get('stage'):
                loan_data['stage'] = 'APPLICATION'

            columns = ", ".join(loan_data.keys())
            placeholders = ", ".join([f":{k}" for k in loan_data.keys()])

            # Build SET clause for the ON CONFLICT update path — update all mapped
            # fields except loan_officer_id and organization_id (preserve originals)
            conflict_set_parts = []
            for k in loan_data.keys():
                if k not in ('loan_officer_id', 'organization_id', 'salesforce_id', 'loan_number'):
                    conflict_set_parts.append(f"{k} = EXCLUDED.{k}")
            conflict_set_parts.append("updated_at = CURRENT_TIMESTAMP")
            conflict_set_clause = ", ".join(conflict_set_parts)

            query = f"""
                INSERT INTO loans ({columns}, created_at, updated_at)
                VALUES ({placeholders}, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT (salesforce_id) WHERE salesforce_id IS NOT NULL
                DO UPDATE SET {conflict_set_clause}
                RETURNING id, (xmax = 0) AS was_inserted
            """
            result = db.execute(text(query), loan_data)

            row = result.fetchone()
            loan_id = row[0]
            was_inserted = row[1] if len(row) > 1 else True

            if was_inserted:
                logger.info(f"Created loan {loan_id} ({loan_data['loan_number']}) from Salesforce {salesforce_id}")

                # Wire to SLA tracking — create initial milestone for new loan
                try:
                    from services.sla_tracking_service import track_loan_created
                    track_loan_created(
                        db, loan_id, loan_data['loan_number'], organization_id=org_id
                    )
                except Exception as e:
                    logger.warning(f"SLA tracking hook failed for new loan {loan_id}: {e}")

                # MUM promotion: if new loan is created with FUNDED stage, promote immediately
                if loan_data.get('stage') == 'FUNDED':
                    self._try_mum_promotion(db, loan_id, user_id)
            else:
                logger.info(
                    f"Loan {loan_id} already existed (race condition resolved via ON CONFLICT) "
                    f"from Salesforce {salesforce_id}"
                )

            return loan_id

    def _map_salesforce_stage(self, sf_stage: str) -> str:
        """Map Salesforce Opportunity stage to CRM loan stage (UPPERCASE enum values).

        Returns None for unmapped stages so callers can handle appropriately
        (preserve existing stage on updates, default to APPLICATION on creates).
        Uses the canonical shared mapping from stage_mapping.py.
        """
        from .stage_mapping import map_salesforce_stage
        return map_salesforce_stage(sf_stage)

    def _group_mappings_by_object(
        self,
        mappings: List[FieldMapping]
    ) -> Dict[str, List[FieldMapping]]:
        """Group mappings by source object"""
        return group_mappings_by_object(mappings)

    def _group_mappings_by_entity(
        self,
        mappings: List[FieldMapping]
    ) -> Dict[str, List[FieldMapping]]:
        """Group mappings by target entity"""
        return group_mappings_by_entity(mappings)

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
            item.started_at = datetime.now(timezone.utc)
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
                item.completed_at = datetime.now(timezone.utc)
                item.result = {'success': True}

            except Exception as e:
                if item.attempts >= item.max_attempts:
                    item.status = 'failed'
                else:
                    item.status = 'retry'
                item.error_message = str(e)

            db.commit()


    # =========================================================================
    # EMAIL-BASED MATCHING SYNC - Match CRM clients to Salesforce by email
    # Pull ALL fields from Salesforce to CRM
    # =========================================================================

    async def sync_crm_clients_from_salesforce(
        self,
        db: Session,
        integration_profile_id: int,
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        Match CRM clients to Salesforce records by EMAIL and pull ALL fields.

        This is the primary sync mechanism:
        1. Get CRM leads/loans with email addresses
        2. Search Salesforce for matching Lead/Contact by email
        3. When matched, pull ALL fields (text, number, date) from Salesforce
        4. Update the CRM record with all Salesforce data

        Args:
            db: Database session
            integration_profile_id: User's Salesforce integration profile
            limit: Max records to process per sync

        Returns:
            Sync result with counts
        """
        from sqlalchemy import text

        result = {
            'success': False,
            'leads_matched': 0,
            'leads_updated': 0,
            'leads_not_found': 0,
            'loans_matched': 0,
            'loans_updated': 0,
            'errors': []
        }

        try:
            # Get access token
            access_token, instance_url = await salesforce_oauth.get_access_token(
                db, integration_profile_id
            )

            if not access_token:
                result['errors'].append("Failed to get Salesforce access token")
                return result

            # Get the integration profile for user_id
            profile = db.query(IntegrationProfile).filter(
                IntegrationProfile.id == integration_profile_id
            ).first()

            if not profile:
                result['errors'].append("Integration profile not found")
                return result

            user_id = profile.user_id

            # ===== SYNC LEADS =====
            # Get CRM leads with email addresses
            crm_leads = db.execute(text("""
                SELECT id, email, first_name, last_name, salesforce_id
                FROM leads
                WHERE owner_id = :user_id
                  AND email IS NOT NULL
                  AND email != ''
                ORDER BY updated_at DESC
                LIMIT :limit
            """), {"user_id": user_id, "limit": limit}).fetchall()

            logger.info(f"Processing {len(crm_leads)} CRM leads for Salesforce matching")

            for lead in crm_leads:
                try:
                    # Search Salesforce for matching record by email
                    sf_record = await self._fetch_salesforce_record_by_email(
                        access_token, instance_url, lead.email
                    )

                    if sf_record.get('found'):
                        result['leads_matched'] += 1

                        # Update CRM lead with ALL Salesforce fields
                        updated = await self._update_lead_from_salesforce(
                            db, lead.id, sf_record['record'], sf_record['type'], sf_record['id']
                        )

                        if updated:
                            result['leads_updated'] += 1
                    else:
                        result['leads_not_found'] += 1

                except Exception as e:
                    logger.error(f"Error syncing lead {lead.id}: {e}")
                    result['errors'].append(f"Lead {lead.id}: {str(e)[:100]}")
                    try:
                        db.rollback()
                    except Exception as e2:
                        logger.exception(f"Failed to rollback after lead {lead.id} sync error: {e2}")

            # ===== SYNC LOANS =====
            # Get CRM loans with borrower email addresses
            crm_loans = db.execute(text("""
                SELECT id, borrower_email, borrower_name, salesforce_id
                FROM loans
                WHERE loan_officer_id = :user_id
                  AND borrower_email IS NOT NULL
                  AND borrower_email != ''
                ORDER BY updated_at DESC
                LIMIT :limit
            """), {"user_id": user_id, "limit": limit}).fetchall()

            logger.info(f"Processing {len(crm_loans)} CRM loans for Salesforce matching")

            for loan in crm_loans:
                try:
                    # Search Salesforce for matching Opportunity by related Contact email
                    sf_record = await self._fetch_salesforce_opportunity_by_email(
                        access_token, instance_url, loan.borrower_email
                    )

                    if sf_record.get('found'):
                        result['loans_matched'] += 1

                        # Update CRM loan with ALL Salesforce fields
                        updated = await self._update_loan_from_salesforce(
                            db, loan.id, sf_record['record'], sf_record['id']
                        )

                        if updated:
                            result['loans_updated'] += 1

                            # Auto-promote to MUM if loan is now funded
                            try:
                                from services.mum_promotion_service import maybe_promote_loan_to_mum
                                mum_id = maybe_promote_loan_to_mum(db, loan.id, user_id)
                                if mum_id:
                                    logger.info(f"Scheduled sync auto-promoted loan {loan.id} to MUM client {mum_id}")
                            except Exception as mum_err:
                                logger.warning(f"MUM promotion failed for loan {loan.id}: {mum_err}")

                except Exception as e:
                    logger.error(f"Error syncing loan {loan.id}: {e}")
                    result['errors'].append(f"Loan {loan.id}: {str(e)[:100]}")
                    try:
                        db.rollback()
                    except Exception as e2:
                        logger.exception(f"Failed to rollback after loan {loan.id} sync error: {e2}")

            result['success'] = True
            db.commit()

            logger.info(
                f"Email-based sync complete: "
                f"leads matched={result['leads_matched']}, updated={result['leads_updated']} | "
                f"loans matched={result['loans_matched']}, updated={result['loans_updated']}"
            )

        except Exception as e:
            logger.error(f"Email-based sync failed: {e}")
            result['errors'].append(str(e))
            try:
                db.rollback()
            except Exception as e2:
                logger.exception(f"Failed to rollback after email-based sync failure: {e2}")

        return result

    async def _fetch_salesforce_record_by_email(
        self,
        access_token: str,
        instance_url: str,
        email: str
    ) -> Dict[str, Any]:
        """
        Fetch ALL fields from a Salesforce Lead or Contact by email.

        Returns comprehensive record data including all text, number, and date fields.
        """
        if not email:
            return {"found": False}

        async with get_sf_client() as client:
            # Query Lead with ALL fields
            lead_query = f"""
                SELECT Id, FirstName, LastName, Email, Phone, MobilePhone, Company,
                       Title, Industry, Street, City, State, PostalCode, Country,
                       LeadSource, Status, Rating, AnnualRevenue, NumberOfEmployees,
                       Description, Website, Fax,
                       CreatedDate, LastModifiedDate
                FROM Lead
                WHERE Email = '{_sanitize_soql_email(email)}'
                LIMIT 1
            """

            response = await client.get(
                f"{instance_url}/services/data/{SF_API_VERSION}/query",
                params={"q": lead_query},
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=30.0
            )

            if response.status_code == 200:
                data = response.json()
                if data.get('totalSize', 0) > 0:
                    record = data['records'][0]
                    logger.info(f"Found Salesforce Lead {record['Id']} for CRM record lookup")
                    return {
                        "found": True,
                        "type": "Lead",
                        "id": record['Id'],
                        "record": record
                    }

            # If no Lead, query Contact with ALL fields
            contact_query = f"""
                SELECT Id, FirstName, LastName, Email, Phone, MobilePhone, HomePhone,
                       Title, Department, MailingStreet, MailingCity, MailingState,
                       MailingPostalCode, MailingCountry, Birthdate, AccountId,
                       Description, Fax, LeadSource,
                       CreatedDate, LastModifiedDate
                FROM Contact
                WHERE Email = '{_sanitize_soql_email(email)}'
                LIMIT 1
            """

            response = await client.get(
                f"{instance_url}/services/data/{SF_API_VERSION}/query",
                params={"q": contact_query},
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=30.0
            )

            if response.status_code == 200:
                data = response.json()
                if data.get('totalSize', 0) > 0:
                    record = data['records'][0]
                    logger.info(f"Found Salesforce Contact {record['Id']} for CRM record lookup")
                    return {
                        "found": True,
                        "type": "Contact",
                        "id": record['Id'],
                        "record": record
                    }

        return {"found": False}

    async def _fetch_salesforce_opportunity_by_email(
        self,
        access_token: str,
        instance_url: str,
        email: str
    ) -> Dict[str, Any]:
        """
        Fetch Salesforce Opportunity by related Contact email.

        Returns comprehensive Opportunity data with all fields.
        """
        if not email:
            return {"found": False}

        async with get_sf_client() as client:
            # First find the Contact by email
            contact_query = f"SELECT Id, AccountId FROM Contact WHERE Email = '{_sanitize_soql_email(email)}' LIMIT 1"

            response = await client.get(
                f"{instance_url}/services/data/{SF_API_VERSION}/query",
                params={"q": contact_query},
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=30.0
            )

            if response.status_code != 200:
                return {"found": False}

            data = response.json()
            if data.get('totalSize', 0) == 0:
                return {"found": False}

            contact = data['records'][0]
            account_id = contact.get('AccountId')

            if not account_id:
                return {"found": False}

            # Query Opportunity by AccountId with ALL fields
            # Fix 1c: Sanitize account_id before SOQL interpolation
            safe_acct_id = _sanitize_soql_string(account_id)
            opp_query = f"""
                SELECT Id, Name, Amount, StageName, CloseDate, Probability,
                       Type, LeadSource, NextStep, Description,
                       ExpectedRevenue, TotalOpportunityQuantity,
                       CreatedDate, LastModifiedDate, IsClosed, IsWon
                FROM Opportunity
                WHERE AccountId = '{safe_acct_id}'
                ORDER BY LastModifiedDate DESC
                LIMIT 1
            """

            response = await client.get(
                f"{instance_url}/services/data/{SF_API_VERSION}/query",
                params={"q": opp_query},
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=30.0
            )

            if response.status_code == 200:
                data = response.json()
                if data.get('totalSize', 0) > 0:
                    record = data['records'][0]
                    logger.info(f"Found Salesforce Opportunity {record['Id']} for CRM record lookup")
                    return {
                        "found": True,
                        "type": "Opportunity",
                        "id": record['Id'],
                        "record": record
                    }

        return {"found": False}

    async def _update_lead_from_salesforce(
        self,
        db: Session,
        lead_id: int,
        sf_record: Dict[str, Any],
        sf_type: str,
        sf_id: str
    ) -> bool:
        """
        Update a CRM lead with ALL fields from Salesforce Lead/Contact.

        Maps all text, number, and date fields from Salesforce to CRM.
        """
        from sqlalchemy import text

        # Build update data from Salesforce record
        update_fields = {}

        # Text fields
        if sf_record.get('FirstName'):
            update_fields['first_name'] = sf_record['FirstName']
        if sf_record.get('LastName'):
            update_fields['last_name'] = sf_record['LastName']
        if sf_record.get('Email'):
            update_fields['email'] = sf_record['Email']
        if sf_record.get('Phone'):
            update_fields['phone'] = sf_record['Phone']
        if sf_record.get('Company'):
            update_fields['employer_name'] = sf_record['Company']
        if sf_record.get('Industry'):
            update_fields['industry'] = sf_record['Industry']

        # Address fields
        street = sf_record.get('Street') or sf_record.get('MailingStreet')
        city = sf_record.get('City') or sf_record.get('MailingCity')
        state = sf_record.get('State') or sf_record.get('MailingState')
        postal = sf_record.get('PostalCode') or sf_record.get('MailingPostalCode')

        if street:
            update_fields['address'] = street
        if city:
            update_fields['city'] = city
        if state:
            update_fields['state'] = state
        if postal:
            update_fields['zip_code'] = postal

        # Source and status
        if sf_record.get('LeadSource'):
            update_fields['source'] = sf_record['LeadSource']
        if sf_record.get('Status'):
            update_fields['stage'] = self._map_sf_lead_status_to_crm(sf_record['Status'])
        if sf_record.get('Description'):
            update_fields['notes'] = sf_record['Description']

        # Number fields
        if sf_record.get('AnnualRevenue'):
            update_fields['annual_income'] = float(sf_record['AnnualRevenue'])

        # Always update salesforce_id and sync timestamp
        update_fields['salesforce_id'] = sf_id

        if not update_fields:
            return False

        # Build dynamic UPDATE query
        set_clauses = ", ".join([f"{k} = :{k}" for k in update_fields.keys()])
        update_fields['lead_id'] = lead_id
        update_fields['sf_type'] = sf_type

        query = f"""
            UPDATE leads SET {set_clauses},
                meta_data = COALESCE(meta_data, '{{}}'::jsonb) ||
                    jsonb_build_object(
                        'salesforce_type', :sf_type,
                        'salesforce_synced_at', CURRENT_TIMESTAMP
                    ),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :lead_id
        """
        db.execute(text(query), update_fields)

        logger.info(f"Updated lead {lead_id} with {len(update_fields)} fields from Salesforce {sf_type} {sf_id}")
        return True

    # Comprehensive SF Opportunity field → CRM loan column mapping
    SF_OPPORTUNITY_FIELD_MAP = {
        # Borrower info
        'Name': 'borrower_name',
        'Contact_Email__c': 'borrower_email',
        'Contact_Phone__c': 'borrower_phone',
        # Core loan details
        'Amount': 'amount',
        'Interest_Rate__c': 'rate',
        'Type': 'loan_type',
        'Loan_Purpose__c': 'loan_purpose',
        'Loan_Program__c': 'program',
        'Loan_Number__c': 'loan_number',
        'LTV__c': 'ltv',
        'Loan_Term__c': 'term',
        # Property info
        'Property_Address__c': 'property_address',
        'Property_City__c': 'property_city',
        'Property_State__c': 'property_state',
        'Property_Zip__c': 'property_zip',
        'Property_Type__c': 'property_type',
        'Property_Value__c': 'property_value',
        'Occupancy_Type__c': 'occupancy_type',
        'Appraisal_Value__c': 'appraisal_value',
        'Purchase_Price__c': 'purchase_price',
        # Dates
        'CloseDate': 'closing_date',
        'Funded_Date__c': 'funded_date',
        'Application_Date__c': 'application_date',
        'Lock_Expiration__c': 'lock_expiration_date',
        'Lock_Date__c': 'lock_date',
        # Financial details
        'Monthly_Payment__c': 'monthly_payment',
        'Down_Payment__c': 'down_payment',
        'Credit_Score__c': 'credit_score',
        'DTI__c': 'dti',
        'APR__c': 'apr',
        'CLTV__c': 'cltv',
        'Points__c': 'points',
        'Origination_Fee__c': 'origination_fee',
        # Jungo / MtgPlanner custom fields (override standard if present)
        'MtgPlanner_CRM__Loan_Number__c': 'loan_number',
        'MtgPlanner_CRM__Loan_Amount__c': 'amount',
        'MtgPlanner_CRM__Interest_Rate__c': 'rate',
        'MtgPlanner_CRM__Property_Address__c': 'property_address',
        'MtgPlanner_CRM__Property_City__c': 'property_city',
        'MtgPlanner_CRM__Property_State__c': 'property_state',
        'MtgPlanner_CRM__Property_Zip__c': 'property_zip',
        'MtgPlanner_CRM__Close_Date__c': 'closing_date',
        'MtgPlanner_CRM__Credit_Score__c': 'credit_score',
    }

    # Numeric CRM columns that should be coerced from SF string values
    _NUMERIC_LOAN_COLUMNS = {
        'amount', 'rate', 'ltv', 'property_value', 'appraisal_value',
        'purchase_price', 'monthly_payment', 'down_payment', 'credit_score',
        'dti', 'apr', 'cltv', 'points', 'origination_fee', 'term',
    }

    async def _update_loan_from_salesforce(
        self,
        db: Session,
        loan_id: int,
        sf_record: Dict[str, Any],
        sf_id: str
    ) -> bool:
        """
        Update a CRM loan with ALL fields from Salesforce Opportunity.

        Maps all text, number, and date fields from Salesforce to CRM
        using SF_OPPORTUNITY_FIELD_MAP. Only writes columns that exist
        in VALID_LOAN_COLUMNS.
        """
        from sqlalchemy import text
        from decimal import Decimal, InvalidOperation

        update_fields = {}

        # Map all known SF fields to CRM columns
        for sf_field, crm_column in self.SF_OPPORTUNITY_FIELD_MAP.items():
            value = sf_record.get(sf_field)
            if value is None or value == '':
                continue
            if crm_column not in self.VALID_LOAN_COLUMNS:
                continue

            # Coerce numeric columns
            if crm_column in self._NUMERIC_LOAN_COLUMNS:
                try:
                    value = float(Decimal(str(value)))
                except (InvalidOperation, TypeError, ValueError):
                    logger.warning(f"SF→Loan sync: invalid numeric value for {sf_field}={value!r}")
                    continue

            update_fields[crm_column] = value

        # Stage mapping (special handling — None means unmapped, preserve existing)
        if sf_record.get('StageName'):
            raw_stage = sf_record['StageName']
            mapped_stage = self._map_salesforce_stage(raw_stage)
            update_fields['salesforce_raw_stage'] = raw_stage
            if mapped_stage:
                update_fields['stage'] = mapped_stage
            else:
                logger.warning(f"Unmapped SF stage '{raw_stage}' for loan {loan_id} — preserving existing stage")

        # Always update salesforce_id
        update_fields['salesforce_id'] = sf_id

        if len(update_fields) <= 1:  # Only salesforce_id, no real data
            return False

        # Capture old stage for MUM promotion check
        old_stage_row = db.execute(text(
            "SELECT stage::text FROM loans WHERE id = :lid"
        ), {"lid": loan_id}).fetchone()
        old_stage = old_stage_row[0] if old_stage_row else None

        # Build dynamic UPDATE query
        set_clauses = ", ".join([f"{k} = :{k}" for k in update_fields.keys()])
        update_fields['loan_id'] = loan_id

        query = f"""
            UPDATE loans SET {set_clauses},
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :loan_id
        """
        db.execute(text(query), update_fields)

        logger.info(f"Updated loan {loan_id} with {len(update_fields) - 1} fields from Salesforce Opportunity {sf_id}")

        # MUM promotion: if stage just changed to FUNDED, promote
        new_stage = update_fields.get('stage')
        if new_stage == 'FUNDED' and old_stage != 'FUNDED':
            user_row = db.execute(text(
                "SELECT loan_officer_id FROM loans WHERE id = :lid"
            ), {"lid": loan_id}).fetchone()
            if user_row and user_row[0]:
                self._try_mum_promotion(db, loan_id, user_row[0])

        # Compliance hook: check TRID timing when disclosure dates are synced
        disclosure_fields = {'initial_disclosures_sent_date', 'cd_sent_to_borrower_date'}
        if disclosure_fields & set(update_fields.keys()):
            try:
                from services.compliance_check_service import check_trid_timing_async
                check_trid_timing_async(loan_id)
            except ImportError:
                pass  # Compliance service not available
            except Exception as e:
                logger.warning(f"TRID compliance check failed for loan {loan_id}: {e}")

        # ACO hook: trigger completeness review on key stage transitions from SF
        ACO_TRIGGER_STAGES = (
            "APPLICATION", "DISCLOSED", "SUBMITTED",
            "UW_RECEIVED", "CONDITIONAL_APPROVAL",
        )
        if new_stage and new_stage != old_stage and new_stage in ACO_TRIGGER_STAGES:
            try:
                from tasks.app_completion_tasks import trigger_application_review_task
                trigger_application_review_task.delay(
                    loan_id=loan_id,
                    triggered_by=f"SF_SYNC_{new_stage}",
                )
                logger.info(f"ACO review queued for loan {loan_id} via SF sync stage {new_stage}")
            except Exception as e:
                logger.warning(f"ACO review trigger failed for loan {loan_id}: {e}")

        return True

    def _map_sf_lead_status_to_crm(self, sf_status: str) -> str:
        """Map Salesforce Lead/Contact status to CRM stage (matches LeadStage enum values).

        Fix 2: Delegates to the canonical map_salesforce_lead_stage() in stage_mapping.py
        to prevent divergence between inline dictionaries and the single source of truth.
        """
        return map_salesforce_lead_stage(sf_status)

    # =========================================================================
    # SMART ROUTING: Classify records by SF status and route to correct table
    # =========================================================================

    # SF statuses that indicate a prospect/lead (not yet an active loan)
    LEAD_STATUSES = {
        'New', 'Prospecting', 'Qualification', 'Pre-Qualified', 'Pre-Approved',
        'Nurture', 'Open - Not Contacted', 'Working - Contacted',
        'Needs Analysis', 'Long-Term Nurture',
    }

    # SF statuses that indicate a funded/closed loan (MUM candidate)
    FUNDED_STATUSES = {
        'Funded', 'Closed', 'Closed Won', 'Closed - Converted',
        'Loan Funded', 'Completed', 'Purchased', 'File Complete',
        'Post-Closing', 'Post-Funding', 'Loan Sold', 'Settled',
        'Shipped', 'Loan Shipped',
    }

    # CRM stages that are terminal/funded — used when the stage_map transform
    # has already converted the SF status to an UPPERCASE CRM stage.
    _CRM_TERMINAL_STAGES = {'FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY'}
    _CRM_MUM_STAGES = {'FUNDED'}

    def _classify_record_bucket(self, data: Dict[str, Any]) -> str:
        """
        Classify a Salesforce record into 'lead', 'loan', or 'loan_funded'
        based on the SF status value.

        Returns:
            'lead' - prospect/pre-approved, goes to leads table
            'loan' - active loan (application through CTC), goes to loans table
            'loan_funded' - funded/closed, goes to loans table + MUM promotion
        """
        # Check the stage/status field — could be in 'stage' (from field mapping),
        # raw SF field names, or '_sf_status' (injected from raw record)
        sf_status = (
            data.get('stage')
            or data.get('StageName')
            or data.get('Status')
            or data.get('_sf_status')
            or ''
        )

        if not sf_status:
            # No stage info — route based on data shape
            if data.get('amount') or data.get('loan_number'):
                return 'loan'
            return 'lead'

        # The stage value might already be a CRM stage (UPPERCASE) if
        # the field mapping used a stage_map transform. Check that first.
        if sf_status in self._CRM_MUM_STAGES:
            return 'loan_funded'
        if sf_status in self._CRM_TERMINAL_STAGES:
            return 'loan'

        # Check lead statuses first (exact match on raw SF values)
        if sf_status in self.LEAD_STATUSES:
            return 'lead'

        # Check funded statuses (raw SF values)
        if sf_status in self.FUNDED_STATUSES:
            return 'loan_funded'

        # Check if _map_salesforce_stage maps this to FUNDED
        mapped_stage = self._map_salesforce_stage(sf_status)
        if mapped_stage == 'FUNDED':
            return 'loan_funded'
        if mapped_stage in ('CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY'):
            return 'loan'

        # Everything else with a recognized loan stage goes to loans
        # (APPLICATION, PROCESSING, SUBMITTED, UNDERWRITING, CTC, etc.)
        return 'loan'

    def _find_existing_record(
        self,
        db: Session,
        salesforce_id: Optional[str],
        email: Optional[str],
        user_id: int,
        organization_id: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Search across leads, loans, and mum_clients for an existing record
        matching the given salesforce_id or email.

        All salesforce_id lookups are scoped by organization_id when available
        to prevent cross-tenant data leakage.

        Returns:
            Dict with {'table': 'leads'|'loans'|'mum_clients', 'id': int, 'stage': str}
            or None if not found.
        """
        from sqlalchemy import text as sa_text

        # Build org filter clause for salesforce_id lookups
        org_filter = "AND organization_id = :org_id" if organization_id else ""
        params_base = {"org_id": organization_id} if organization_id else {}

        # 1. Check loans by salesforce_id (org-scoped)
        if salesforce_id:
            params = {"sf_id": salesforce_id, **params_base}
            query = f"""
                SELECT id, stage FROM loans
                WHERE salesforce_id = :sf_id {org_filter}
                LIMIT 1
            """
            row = db.execute(sa_text(query), params).fetchone()
            if row:
                return {"table": "loans", "id": row[0], "stage": row[1]}

        # 2. Check leads by salesforce_id (org-scoped)
        if salesforce_id:
            params = {"sf_id": salesforce_id, **params_base}
            query = f"""
                SELECT id, stage FROM leads
                WHERE (salesforce_id = :sf_id OR meta_data->>'salesforce_id' = :sf_id)
                    {org_filter}
                LIMIT 1
            """
            row = db.execute(sa_text(query), params).fetchone()
            if row:
                return {"table": "leads", "id": row[0], "stage": row[1]}

        # 3. Check mum_clients by salesforce_id (org-scoped)
        if salesforce_id:
            params = {"sf_id": salesforce_id, **params_base}
            query = f"""
                SELECT id FROM mum_clients
                WHERE salesforce_id = :sf_id {org_filter}
                LIMIT 1
            """
            row = db.execute(sa_text(query), params).fetchone()
            if row:
                return {"table": "mum_clients", "id": row[0], "stage": None}

        # 4. Fallback: leads by email (scoped to user)
        if email:
            row = db.execute(sa_text("""
                SELECT id, stage FROM leads
                WHERE LOWER(email) = LOWER(:email) AND owner_id = :user_id
                LIMIT 1
            """), {"email": email, "user_id": user_id}).fetchone()
            if row:
                return {"table": "leads", "id": row[0], "stage": row[1]}

        # 5. Fallback: loans by borrower_email (scoped to user)
        if email:
            row = db.execute(sa_text("""
                SELECT id, stage FROM loans
                WHERE LOWER(borrower_email) = LOWER(:email) AND loan_officer_id = :user_id
                LIMIT 1
            """), {"email": email, "user_id": user_id}).fetchone()
            if row:
                return {"table": "loans", "id": row[0], "stage": row[1]}

        # 6. Fallback: mum_clients by email (scoped to user)
        if email:
            row = db.execute(sa_text("""
                SELECT id FROM mum_clients
                WHERE LOWER(email) = LOWER(:email) AND user_id = :user_id
                LIMIT 1
            """), {"email": email, "user_id": user_id}).fetchone()
            if row:
                return {"table": "mum_clients", "id": row[0], "stage": None}

        return None

    def _map_sf_status_to_lead_stage(self, sf_status: str) -> str:
        """Map a Salesforce status to a valid LeadStage enum string.

        Fix 2: Delegates to the canonical map_salesforce_lead_stage() in stage_mapping.py
        to prevent divergence between inline dictionaries and the single source of truth.
        """
        return map_salesforce_lead_stage(sf_status)

    def _remap_loan_fields_for_lead(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform loan-shaped field names into lead-shaped field names.
        Used when a Salesforce record needs to go to the leads table but
        the field mappings targeted loan columns.
        """
        return remap_loan_fields_for_lead(data, self.VALID_LEAD_COLUMNS)

    async def _promote_lead_to_loan(
        self,
        db: Session,
        user_id: int,
        salesforce_id: Optional[str],
        lead_id: int,
        loan_data: Dict[str, Any],
    ) -> Optional[int]:
        """
        Promote an existing lead to a loan record.

        1. Fetch lead data and merge as fallbacks into loan_data
        2. Create/update the loan via _upsert_loan()
        3. Mark the lead as 'Disclosed' (converted to active loan)

        Returns the loan ID on success, None on failure.
        """
        from sqlalchemy import text as sa_text

        # Fetch existing lead data for fallback values
        lead_row = db.execute(sa_text("""
            SELECT name, first_name, last_name, email, phone,
                   property_type, property_address, city, state, zip_code,
                   credit_score, loan_amount, loan_type, property_value,
                   down_payment, annual_income, employer_name
            FROM leads WHERE id = :lead_id
        """), {"lead_id": lead_id}).fetchone()

        if lead_row:
            # Use lead data as fallbacks (SF data in loan_data takes precedence)
            fallbacks = {
                'borrower_name': lead_row.name,
                'borrower_email': lead_row.email,
                'borrower_phone': lead_row.phone,
                'property_type': lead_row.property_type,
                'property_address': lead_row.property_address,
                'property_city': lead_row.city,
                'property_state': lead_row.state,
                'property_zip': lead_row.zip_code,
                'loan_type': lead_row.loan_type,
                'purchase_price': lead_row.property_value,
                'down_payment': lead_row.down_payment,
            }
            if lead_row.loan_amount and not loan_data.get('amount'):
                fallbacks['amount'] = lead_row.loan_amount

            for key, fallback_val in fallbacks.items():
                if fallback_val and not loan_data.get(key):
                    loan_data[key] = fallback_val

        # Create/update the loan (skip cross-table check to prevent recursion)
        loan_id = await self._upsert_loan(
            db, user_id, salesforce_id, loan_data, _skip_cross_table=True
        )

        if loan_id:
            # Mark the lead as 'Disclosed' (converted) and store conversion metadata
            # Use CAST() instead of :: to avoid SQLAlchemy text() parameter parsing issues
            db.execute(sa_text("""
                UPDATE leads SET
                    stage = 'Disclosed',
                    stage_changed_at = CURRENT_TIMESTAMP,
                    meta_data = COALESCE(meta_data, CAST('{}' AS jsonb)) ||
                        jsonb_build_object(
                            'converted_to_loan_id', CAST(:loan_id AS text),
                            'converted_at', CAST(CURRENT_TIMESTAMP AS text)
                        ),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :lead_id
            """), {"loan_id": loan_id, "lead_id": lead_id})

            logger.info(
                f"Promoted lead {lead_id} to loan {loan_id} "
                f"(salesforce_id={salesforce_id})"
            )

        return loan_id

    def _try_mum_promotion(self, db: Session, loan_id: int, user_id: int) -> Optional[int]:
        """
        Attempt to promote a funded loan to MUM client.
        Wrapped in try/except so failures don't block the sync.

        Returns MUM client ID if promoted, None otherwise.
        """
        try:
            from services.mum_promotion_service import maybe_promote_loan_to_mum
            mum_id = maybe_promote_loan_to_mum(db, loan_id, user_id)
            if mum_id:
                logger.info(f"Smart routing auto-promoted loan {loan_id} to MUM client {mum_id}")
            return mum_id
        except Exception as e:
            logger.warning(f"MUM promotion failed for loan {loan_id} (non-fatal): {e}")
            return None

    # =========================================================================
    # IMPORT NEW CLIENTS FROM SALESFORCE
    # Query Salesforce for recently created Leads/Contacts/Opportunities
    # and create CRM records for any that don't already exist.
    # =========================================================================

    async def import_new_clients_from_salesforce(
        self,
        db: Session,
        integration_profile_id: int,
        days_back: int = 7,
        limit: int = 200
    ) -> Dict[str, Any]:
        """
        Import NEW clients from Salesforce that don't yet exist in the CRM.

        Queries Salesforce for recently created/modified Leads and Contacts,
        then creates CRM lead records for any that don't already exist
        (matched by email or salesforce_id).

        Args:
            db: Database session
            integration_profile_id: User's Salesforce integration profile
            days_back: How many days back to query for new records
            limit: Max records to process per sync

        Returns:
            Import result with counts
        """
        from sqlalchemy import text

        result = {
            'success': False,
            'sf_leads_found': 0,
            'sf_contacts_found': 0,
            'sf_opportunities_found': 0,
            'new_leads_created': 0,
            'new_loans_created': 0,
            'duplicates_skipped': 0,
            'errors': []
        }

        try:
            # Get access token
            access_token, instance_url = await salesforce_oauth.get_access_token(
                db, integration_profile_id
            )

            if not access_token:
                result['errors'].append("Failed to get Salesforce access token")
                return result

            # Get the integration profile for user_id
            profile = db.query(IntegrationProfile).filter(
                IntegrationProfile.id == integration_profile_id
            ).first()

            if not profile:
                result['errors'].append("Integration profile not found")
                return result

            user_id = profile.user_id
            _token_refreshed = False  # Track if we've already refreshed once

            # In-memory dedup: track SF IDs imported as leads in this batch,
            # so the Opportunity import phase can detect cross-entity overlap.
            _imported_lead_sf_ids = set()

            # ===== IMPORT SALESFORCE LEADS =====
            sf_leads = []
            try:
                sf_leads = await self._query_recent_sf_leads(
                    access_token, instance_url, days_back, limit
                )
                result['sf_leads_found'] = len(sf_leads)
            except SalesforceTokenExpiredError:
                # Token expired — refresh once and retry
                if not _token_refreshed:
                    try:
                        logger.info(f"Refreshing expired SF token for profile {integration_profile_id}")
                        access_token, instance_url = await salesforce_oauth.force_refresh_and_get_token(
                            db, integration_profile_id
                        )
                        _token_refreshed = True
                        sf_leads = await self._query_recent_sf_leads(
                            access_token, instance_url, days_back, limit
                        )
                        result['sf_leads_found'] = len(sf_leads)
                    except Exception as refresh_err:
                        logger.error(f"SF token refresh failed: {refresh_err}")
                        result['errors'].append(f"Token refresh failed: {str(refresh_err)[:100]}")
                        return result
                else:
                    result['errors'].append("SF token still invalid after refresh")
                    return result
            except Exception as e:
                logger.error(f"Error querying SF Leads: {e}")
                result['errors'].append(f"Lead query: {str(e)[:100]}")

            for sf_lead in sf_leads:
                try:
                    created = await self._create_crm_lead_if_new(
                        db, sf_lead, 'Lead', user_id
                    )
                    if created:
                        result['new_leads_created'] += 1
                        # Track for cross-entity dedup in the Opportunity phase
                        lead_sf_id = sf_lead.get('Id')
                        if lead_sf_id:
                            _imported_lead_sf_ids.add(lead_sf_id)
                    else:
                        result['duplicates_skipped'] += 1
                except Exception as e:
                    sf_id = sf_lead.get('Id', 'unknown')
                    logger.error(f"Error importing SF Lead {sf_id}: {e}")
                    result['errors'].append(f"Lead {sf_id}: {str(e)[:100]}")
                    try:
                        db.rollback()
                    except Exception as e2:
                        logger.exception(f"Failed to rollback after SF Lead {sf_id} import error: {e2}")

            # ===== IMPORT SALESFORCE CONTACTS =====
            sf_contacts = []
            try:
                sf_contacts = await self._query_recent_sf_contacts(
                    access_token, instance_url, days_back, limit
                )
                result['sf_contacts_found'] = len(sf_contacts)
            except SalesforceTokenExpiredError:
                if not _token_refreshed:
                    try:
                        logger.info(f"Refreshing expired SF token for profile {integration_profile_id} (contacts)")
                        access_token, instance_url = await salesforce_oauth.force_refresh_and_get_token(
                            db, integration_profile_id
                        )
                        _token_refreshed = True
                        sf_contacts = await self._query_recent_sf_contacts(
                            access_token, instance_url, days_back, limit
                        )
                        result['sf_contacts_found'] = len(sf_contacts)
                    except Exception as refresh_err:
                        logger.error(f"SF token refresh failed (contacts): {refresh_err}")
                        result['errors'].append(f"Token refresh failed: {str(refresh_err)[:100]}")
                else:
                    result['errors'].append("SF token still invalid after refresh (contacts)")
            except Exception as e:
                logger.error(f"Error querying SF Contacts: {e}")
                result['errors'].append(f"Contact query: {str(e)[:100]}")

            for sf_contact in sf_contacts:
                try:
                    created = await self._create_crm_lead_if_new(
                        db, sf_contact, 'Contact', user_id
                    )
                    if created:
                        result['new_leads_created'] += 1
                        # Track for cross-entity dedup in the Opportunity phase
                        contact_sf_id = sf_contact.get('Id')
                        if contact_sf_id:
                            _imported_lead_sf_ids.add(contact_sf_id)
                    else:
                        result['duplicates_skipped'] += 1
                except Exception as e:
                    sf_id = sf_contact.get('Id', 'unknown')
                    logger.error(f"Error importing SF Contact {sf_id}: {e}")
                    result['errors'].append(f"Contact {sf_id}: {str(e)[:100]}")
                    try:
                        db.rollback()
                    except Exception as e2:
                        logger.exception(f"Failed to rollback after SF Contact {sf_id} import error: {e2}")

            # ===== IMPORT SALESFORCE OPPORTUNITIES AS LOANS =====
            sf_opps = []
            try:
                sf_opps = await self._query_recent_sf_opportunities(
                    access_token, instance_url, days_back, limit
                )
                result['sf_opportunities_found'] = len(sf_opps)
            except SalesforceTokenExpiredError:
                if not _token_refreshed:
                    try:
                        logger.info(f"Refreshing expired SF token for profile {integration_profile_id} (opportunities)")
                        access_token, instance_url = await salesforce_oauth.force_refresh_and_get_token(
                            db, integration_profile_id
                        )
                        _token_refreshed = True
                        sf_opps = await self._query_recent_sf_opportunities(
                            access_token, instance_url, days_back, limit
                        )
                        result['sf_opportunities_found'] = len(sf_opps)
                    except Exception as refresh_err:
                        logger.error(f"SF token refresh failed (opportunities): {refresh_err}")
                        result['errors'].append(f"Token refresh failed: {str(refresh_err)[:100]}")
                else:
                    result['errors'].append("SF token still invalid after refresh (opportunities)")
            except Exception as e:
                logger.error(f"Error querying SF Opportunities: {e}")
                result['errors'].append(f"Opportunity query: {str(e)[:100]}")

            for sf_opp in sf_opps:
                try:
                    # Belt-and-suspenders: warn if we just imported a lead for this SF ID
                    opp_sf_id = sf_opp.get('Id')
                    if opp_sf_id and opp_sf_id in _imported_lead_sf_ids:
                        logger.warning(
                            f"SF Opportunity {opp_sf_id} was also imported as a lead in this batch. "
                            f"DB-level cross-entity dedup in _create_crm_loan_if_new will handle it."
                        )

                    created = await self._create_crm_loan_if_new(
                        db, sf_opp, user_id
                    )
                    if created:
                        result['new_loans_created'] += 1

                        # Auto-promote to MUM if the new loan is already funded/closed
                        sf_stage = self._map_salesforce_stage(sf_opp.get('StageName', ''))
                        if sf_stage == 'FUNDED':
                            try:
                                sf_id_val = sf_opp.get('Id')
                                loan_row = db.execute(text(
                                    "SELECT id FROM loans WHERE salesforce_id = :sf_id AND loan_officer_id = :uid LIMIT 1"
                                ), {"sf_id": sf_id_val, "uid": user_id}).fetchone()
                                if loan_row:
                                    from services.mum_promotion_service import maybe_promote_loan_to_mum
                                    mum_id = maybe_promote_loan_to_mum(db, loan_row[0], user_id)
                                    if mum_id:
                                        logger.info(f"Import sync auto-promoted new loan {loan_row[0]} to MUM client {mum_id}")
                            except Exception as mum_err:
                                logger.warning(f"MUM promotion failed for new SF loan {sf_opp.get('Id')}: {mum_err}")
                    else:
                        result['duplicates_skipped'] += 1
                except Exception as e:
                    sf_id = sf_opp.get('Id', 'unknown')
                    logger.error(f"Error importing SF Opportunity {sf_id}: {e}")
                    result['errors'].append(f"Opportunity {sf_id}: {str(e)[:100]}")
                    try:
                        db.rollback()
                    except Exception as e2:
                        logger.exception(f"Failed to rollback after SF Opportunity {sf_id} import error: {e2}")

            result['success'] = True
            db.commit()

            logger.info(
                f"New client import complete: "
                f"leads_created={result['new_leads_created']}, "
                f"loans_created={result['new_loans_created']}, "
                f"duplicates_skipped={result['duplicates_skipped']}"
            )

        except Exception as e:
            logger.error(f"New client import failed: {e}")
            result['errors'].append(str(e))
            try:
                db.rollback()
            except Exception as e2:
                logger.exception(f"Failed to rollback after new client import failure: {e2}")

        return result

    async def _query_recent_sf_leads(
        self,
        access_token: str,
        instance_url: str,
        days_back: int = 7,
        limit: int = 200
    ) -> List[Dict[str, Any]]:
        """Query Salesforce for recently created/modified Leads."""
        # Query standard Lead fields + MtgPlanner_CRM__Status__c (Jungo custom status)
        # The custom field may not exist in all orgs — query will still succeed with
        # standard fields; we catch any SOQL errors and retry without the custom field.
        soql = f"""
            SELECT Id, FirstName, LastName, Email, Phone, Company,
                   Title, Industry, Street, City, State, PostalCode, Country,
                   LeadSource, Status, Description,
                   MtgPlanner_CRM__Status__c,
                   CreatedDate, LastModifiedDate
            FROM Lead
            WHERE LastModifiedDate >= LAST_N_DAYS:{days_back}
              AND Email != null
            ORDER BY LastModifiedDate DESC
            LIMIT {limit}
        """

        async with get_sf_client() as client:
            response = await client.get(
                f"{instance_url}/services/data/{SF_API_VERSION}/query",
                params={"q": soql},
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=30.0
            )

            if response.status_code == 200:
                data = response.json()
                records = data.get('records', [])
                logger.info(f"Found {len(records)} recent SF Leads (last {days_back} days)")
                return records
            elif response.status_code == 401:
                logger.warning(f"SF Lead query: token expired (401). Will attempt refresh.")
                raise SalesforceTokenExpiredError("Lead query: 401 INVALID_SESSION_ID")
            elif response.status_code == 400 and 'MtgPlanner_CRM__Status__c' in response.text:
                # Custom field doesn't exist on Lead object — retry without it
                logger.info("MtgPlanner_CRM__Status__c not available on Lead object, retrying without it")
                soql_fallback = f"""
                    SELECT Id, FirstName, LastName, Email, Phone, Company,
                           Title, Industry, Street, City, State, PostalCode, Country,
                           LeadSource, Status, Description,
                           CreatedDate, LastModifiedDate
                    FROM Lead
                    WHERE LastModifiedDate >= LAST_N_DAYS:{days_back}
                      AND Email != null
                    ORDER BY LastModifiedDate DESC
                    LIMIT {limit}
                """
                response2 = await client.get(
                    f"{instance_url}/services/data/{SF_API_VERSION}/query",
                    params={"q": soql_fallback},
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=30.0
                )
                if response2.status_code == 200:
                    data = response2.json()
                    records = data.get('records', [])
                    logger.info(f"Found {len(records)} recent SF Leads (fallback query)")
                    return records
                logger.error(f"SF Lead fallback query failed: {response2.status_code}")
                return []
            else:
                logger.error(f"SF Lead query failed: {response.status_code} {response.text[:200]}")
                return []

    async def _query_recent_sf_contacts(
        self,
        access_token: str,
        instance_url: str,
        days_back: int = 7,
        limit: int = 200
    ) -> List[Dict[str, Any]]:
        """Query Salesforce for recently created/modified Contacts."""
        soql = f"""
            SELECT Id, FirstName, LastName, Email, Phone,
                   Title, Department, MailingStreet, MailingCity, MailingState,
                   MailingPostalCode, MailingCountry, AccountId,
                   Description, LeadSource,
                   CreatedDate, LastModifiedDate
            FROM Contact
            WHERE LastModifiedDate >= LAST_N_DAYS:{days_back}
              AND Email != null
            ORDER BY LastModifiedDate DESC
            LIMIT {limit}
        """

        async with get_sf_client() as client:
            response = await client.get(
                f"{instance_url}/services/data/{SF_API_VERSION}/query",
                params={"q": soql},
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=30.0
            )

            if response.status_code == 200:
                data = response.json()
                records = data.get('records', [])
                logger.info(f"Found {len(records)} recent SF Contacts (last {days_back} days)")
                return records
            elif response.status_code == 401:
                logger.warning(f"SF Contact query: token expired (401). Will attempt refresh.")
                raise SalesforceTokenExpiredError("Contact query: 401 INVALID_SESSION_ID")
            else:
                logger.error(f"SF Contact query failed: {response.status_code} {response.text[:200]}")
                return []

    async def _query_recent_sf_opportunities(
        self,
        access_token: str,
        instance_url: str,
        days_back: int = 7,
        limit: int = 200
    ) -> List[Dict[str, Any]]:
        """Query Salesforce for recently created/modified Opportunities."""
        soql = f"""
            SELECT Id, Name, Amount, StageName, CloseDate,
                   Type, LeadSource, NextStep, Description,
                   AccountId,
                   CreatedDate, LastModifiedDate, IsClosed, IsWon
            FROM Opportunity
            WHERE LastModifiedDate >= LAST_N_DAYS:{days_back}
            ORDER BY LastModifiedDate DESC
            LIMIT {limit}
        """

        async with get_sf_client() as client:
            response = await client.get(
                f"{instance_url}/services/data/{SF_API_VERSION}/query",
                params={"q": soql},
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=30.0
            )

            if response.status_code == 200:
                data = response.json()
                records = data.get('records', [])
                logger.info(f"Found {len(records)} recent SF Opportunities (last {days_back} days)")
                return records
            elif response.status_code == 401:
                logger.warning(f"SF Opportunity query: token expired (401). Will attempt refresh.")
                raise SalesforceTokenExpiredError("Opportunity query: 401 INVALID_SESSION_ID")
            else:
                logger.error(f"SF Opportunity query failed: {response.status_code} {response.text[:200]}")
                return []

    async def _create_crm_lead_if_new(
        self,
        db: Session,
        sf_record: Dict[str, Any],
        sf_type: str,
        user_id: int
    ) -> bool:
        """
        Create a CRM lead from a Salesforce Lead/Contact if it doesn't already exist.

        Returns True if a new lead was created, False if it already existed.
        """
        from sqlalchemy import text

        sf_id = sf_record.get('Id')
        email = sf_record.get('Email')

        if not sf_id:
            return False

        # --- Status gate: funded/closed records belong in MUM, not leads ---
        sf_status = (
            sf_record.get('MtgPlanner_CRM__Status__c')
            or sf_record.get('Status')
            or ''
        )
        is_funded = (
            sf_status in self.FUNDED_STATUSES
            or self._map_salesforce_stage(sf_status) == 'FUNDED'
        )
        if is_funded:
            logger.info(
                f"SF {sf_type} {sf_id} has funded status '{sf_status}' — "
                f"routing to loan+MUM instead of leads"
            )
            created = await self._create_funded_record_from_contact(
                db, sf_record, sf_type, user_id
            )
            return created

        # Check if already exists by salesforce_id
        existing = db.execute(text("""
            SELECT id FROM leads
            WHERE salesforce_id = :sf_id AND owner_id = :user_id
            LIMIT 1
        """), {"sf_id": sf_id, "user_id": user_id}).fetchone()

        if existing:
            return False

        # Cross-entity dedup: check if a LOAN already exists with this SF ID.
        existing_loan = db.execute(text("""
            SELECT id, stage FROM loans
            WHERE salesforce_id = :sf_id AND loan_officer_id = :user_id
            LIMIT 1
        """), {"sf_id": sf_id, "user_id": user_id}).fetchone()

        if existing_loan:
            logger.info(
                f"Skipping lead creation for SF {sf_type} {sf_id}: "
                f"already exists as loan {existing_loan[0]} (stage={existing_loan[1]})"
            )
            return False

        # Cross-entity dedup: check if a MUM CLIENT already exists with this SF ID.
        existing_mum = db.execute(text("""
            SELECT id FROM mum_clients
            WHERE salesforce_id = :sf_id AND user_id = :user_id
            LIMIT 1
        """), {"sf_id": sf_id, "user_id": user_id}).fetchone()

        if existing_mum:
            logger.info(
                f"Skipping lead creation for SF {sf_type} {sf_id}: "
                f"already exists as MUM client {existing_mum[0]}"
            )
            return False

        # Check if already exists by email (for this user)
        if email:
            existing_by_email = db.execute(text("""
                SELECT id FROM leads
                WHERE email = :email AND owner_id = :user_id
                LIMIT 1
            """), {"email": email, "user_id": user_id}).fetchone()

            if existing_by_email:
                # Update salesforce_id on the existing record
                db.execute(text("""
                    UPDATE leads SET salesforce_id = :sf_id,
                        meta_data = COALESCE(meta_data, '{}'::jsonb) ||
                            jsonb_build_object('salesforce_type', :sf_type,
                                              'salesforce_synced_at', CURRENT_TIMESTAMP::text),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :lead_id
                """), {"sf_id": sf_id, "sf_type": sf_type, "lead_id": existing_by_email.id})
                return False

            # Cross-entity dedup by email: check if a LOAN exists with this email
            existing_loan_by_email = db.execute(text("""
                SELECT id, stage FROM loans
                WHERE LOWER(borrower_email) = LOWER(:email) AND loan_officer_id = :user_id
                LIMIT 1
            """), {"email": email, "user_id": user_id}).fetchone()

            if existing_loan_by_email:
                logger.info(
                    f"Skipping lead creation for SF {sf_type} {sf_id}: "
                    f"loan {existing_loan_by_email[0]} already exists with matching email"
                )
                return False

            # Cross-entity dedup by email: check if a MUM CLIENT exists with this email
            existing_mum_by_email = db.execute(text("""
                SELECT id FROM mum_clients
                WHERE LOWER(email) = LOWER(:email) AND user_id = :user_id
                LIMIT 1
            """), {"email": email, "user_id": user_id}).fetchone()

            if existing_mum_by_email:
                logger.info(
                    f"Skipping lead creation for SF {sf_type} {sf_id}: "
                    f"MUM client {existing_mum_by_email[0]} already exists with matching email"
                )
                return False

        # Build new lead record
        first_name = sf_record.get('FirstName') or ''
        last_name = sf_record.get('LastName') or 'Unknown'
        full_name = f"{first_name} {last_name}".strip() or 'Unknown'

        # Address fields differ between Lead and Contact
        street = sf_record.get('Street') or sf_record.get('MailingStreet')
        city = sf_record.get('City') or sf_record.get('MailingCity')
        state = sf_record.get('State') or sf_record.get('MailingState')
        zip_code = sf_record.get('PostalCode') or sf_record.get('MailingPostalCode')

        source = sf_record.get('LeadSource') or 'Salesforce'
        # Check MtgPlanner_CRM__Status__c first (Jungo custom), then standard Status
        sf_status = (
            sf_record.get('MtgPlanner_CRM__Status__c')
            or sf_record.get('Status')
            or ''
        )
        stage = self._map_sf_lead_status_to_crm(sf_status)
        phone = sf_record.get('Phone') or sf_record.get('MobilePhone')
        employer_name = sf_record.get('Company') or ''
        industry = sf_record.get('Industry') or ''
        notes = sf_record.get('Description') or ''

        # Get user's organization_id for multi-tenant isolation (Fix 8: cached)
        org_id = _get_org_id_for_user(db, user_id)

        result = db.execute(text("""
            INSERT INTO leads (
                name, first_name, last_name, email, phone, employer_name,
                industry, source, stage, address, city, state, zip_code,
                notes, salesforce_id, owner_id, organization_id,
                meta_data, created_at, updated_at
            ) VALUES (
                :name, :first_name, :last_name, :email, :phone, :employer_name,
                :industry, :source, :stage, :address, :city, :state, :zip_code,
                :notes, :sf_id, :owner_id, :org_id,
                jsonb_build_object('salesforce_type', :sf_type,
                                   'salesforce_imported_at', CURRENT_TIMESTAMP::text,
                                   'salesforce_source', 'auto_import'),
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            RETURNING id
        """), {
            "name": full_name,
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "phone": phone,
            "employer_name": employer_name,
            "industry": industry,
            "source": source,
            "stage": stage,
            "address": street,
            "city": city,
            "state": state,
            "zip_code": zip_code,
            "notes": notes,
            "sf_id": sf_id,
            "owner_id": user_id,
            "org_id": org_id,
            "sf_type": sf_type,
        })

        lead_id = result.fetchone()[0]
        logger.info(f"Created CRM lead {lead_id} from Salesforce {sf_type} {sf_id}")

        # Wire to SLA tracking — create initial milestone for new lead
        try:
            from services.sla_tracking_service import track_lead_created
            track_lead_created(db, lead_id, organization_id=org_id)
        except Exception as e:
            logger.warning(f"SLA tracking hook failed for new SF lead {lead_id}: {e}")

        # Speed-to-lead hook — triggers AI call / SMS in background
        try:
            from services.lead_creation_hooks import on_lead_created
            await on_lead_created(
                db=db,
                lead_id=lead_id,
                organization_id=org_id,
                source="salesforce_auto_import",
                owner_id=user_id,
            )
        except Exception as e:
            logger.warning(f"Speed-to-lead hook failed for new SF lead {lead_id}: {e}")

        return True

    async def _create_crm_loan_if_new(
        self,
        db: Session,
        sf_opp: Dict[str, Any],
        user_id: int
    ) -> bool:
        """
        Create a CRM loan from a Salesforce Opportunity if it doesn't already exist.

        Returns True if a new loan was created, False if it already existed.
        """
        from sqlalchemy import text
        import uuid

        sf_id = sf_opp.get('Id')

        if not sf_id:
            return False

        # Check if already exists by salesforce_id
        existing = db.execute(text("""
            SELECT id FROM loans
            WHERE salesforce_id = :sf_id AND loan_officer_id = :user_id
            LIMIT 1
        """), {"sf_id": sf_id, "user_id": user_id}).fetchone()

        if existing:
            return False

        # Cross-entity dedup: check MUM clients by salesforce_id.
        # If a record is already in MUM, don't create a duplicate loan.
        existing_mum = db.execute(text("""
            SELECT id FROM mum_clients
            WHERE salesforce_id = :sf_id AND user_id = :user_id
            LIMIT 1
        """), {"sf_id": sf_id, "user_id": user_id}).fetchone()

        if existing_mum:
            logger.info(
                f"Skipping loan creation for SF Opportunity {sf_id}: "
                f"already exists as MUM client {existing_mum[0]}"
            )
            return False

        # Cross-entity dedup: check if a LEAD already exists with this SF ID.
        # If so, we'll still create the loan but mark the lead as converted afterward.
        existing_lead_sf_id = db.execute(text("""
            SELECT id FROM leads
            WHERE salesforce_id = :sf_id AND owner_id = :user_id
            LIMIT 1
        """), {"sf_id": sf_id, "user_id": user_id}).fetchone()

        # Get user's organization_id for multi-tenant isolation (Fix 8: cached)
        org_id = _get_org_id_for_user(db, user_id)

        # Email-based cross-entity dedup: check loans and MUM by borrower email.
        # The borrower email may come from the related Contact (fetched later),
        # but we can check the Opportunity-level email fields first.
        opp_email = sf_opp.get('Email') or sf_opp.get('ContactEmail')
        if opp_email:
            existing_loan_by_email = db.execute(text("""
                SELECT id FROM loans
                WHERE LOWER(borrower_email) = LOWER(:email) AND loan_officer_id = :user_id
                LIMIT 1
            """), {"email": opp_email, "user_id": user_id}).fetchone()

            if existing_loan_by_email:
                logger.info(
                    f"Skipping loan creation for SF Opportunity {sf_id}: "
                    f"loan {existing_loan_by_email[0]} already exists with matching email"
                )
                return False

            existing_mum_by_email = db.execute(text("""
                SELECT id FROM mum_clients
                WHERE LOWER(email) = LOWER(:email) AND user_id = :user_id
                LIMIT 1
            """), {"email": opp_email, "user_id": user_id}).fetchone()

            if existing_mum_by_email:
                logger.info(
                    f"Skipping loan creation for SF Opportunity {sf_id}: "
                    f"MUM client {existing_mum_by_email[0]} already exists with matching email"
                )
                return False

        # Build new loan record from Opportunity
        name = sf_opp.get('Name') or 'Salesforce Opportunity'
        amount = float(sf_opp.get('Amount') or 0)
        # Fix 6: Default to APPLICATION when map_salesforce_stage returns None
        stage = self._map_salesforce_stage(sf_opp.get('StageName', '')) or 'APPLICATION'
        close_date = sf_opp.get('CloseDate')
        loan_type = sf_opp.get('Type') or ''

        # Generate loan number (required NOT NULL field)
        loan_number = f"SF-{str(uuid.uuid4())[:8].upper()}"

        # Set funded_date if the stage is FUNDED (needed for MUM page)
        funded_date = close_date if stage == 'FUNDED' else None

        # Try to get borrower contact info from related Account/Contact
        borrower_email = None
        borrower_phone = None
        borrower_name = None
        account_id = sf_opp.get('AccountId')
        if account_id:
            try:
                contact_info = await self._get_contact_for_account(
                    db, sf_id, account_id, user_id
                )
                borrower_email = contact_info.get('email')
                borrower_phone = contact_info.get('phone')
                borrower_name = contact_info.get('full_name')
            except Exception as e:
                logger.exception(f"Failed to get contact info for account {account_id}: {e}")

        # Use contact name if available, otherwise fall back to Opportunity Name
        if not borrower_name:
            borrower_name = name

        db.execute(text("""
            INSERT INTO loans (
                loan_number, borrower_name, borrower_email, borrower_phone,
                amount, stage, closing_date, funded_date, loan_type,
                salesforce_id, loan_officer_id, organization_id,
                created_at, updated_at
            ) VALUES (
                :loan_number, :borrower_name, :borrower_email, :borrower_phone,
                :amount, :stage, :close_date, :funded_date, :loan_type,
                :sf_id, :user_id, :org_id,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """), {
            "loan_number": loan_number,
            "borrower_name": borrower_name,
            "borrower_email": borrower_email,
            "borrower_phone": borrower_phone,
            "amount": amount,
            "stage": stage,
            "close_date": close_date,
            "funded_date": funded_date,
            "loan_type": loan_type,
            "sf_id": sf_id,
            "user_id": user_id,
            "org_id": org_id,
        })

        # Get the new loan's ID for SLA tracking
        new_loan_row = db.execute(text("""
            SELECT id FROM loans WHERE salesforce_id = :sf_id AND loan_officer_id = :user_id
            LIMIT 1
        """), {"sf_id": sf_id, "user_id": user_id}).fetchone()

        # Fix 4: removed PII (borrower_name, amount) from info log
        new_loan_id = new_loan_row[0] if new_loan_row else "unknown"
        logger.info(f"Created CRM loan {new_loan_id} from Salesforce Opportunity {sf_id} (stage={stage})")

        # Wire to SLA tracking — create initial milestone for new loan
        if new_loan_row:
            try:
                from services.sla_tracking_service import track_loan_created
                track_loan_created(
                    db, new_loan_row[0], loan_number, organization_id=org_id
                )
            except Exception as e:
                logger.warning(f"SLA tracking hook failed for new SF loan {sf_id}: {e}")

        # Mark existing lead as converted (cross-entity cleanup)
        if existing_lead_sf_id:
            try:
                db.execute(text("""
                    UPDATE leads SET
                        stage = 'Disclosed',
                        meta_data = COALESCE(meta_data, '{}'::jsonb) ||
                            jsonb_build_object(
                                'converted_to_loan', 'true',
                                'converted_at', CURRENT_TIMESTAMP::text
                            ),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :lead_id
                """), {"lead_id": existing_lead_sf_id[0]})
                logger.info(
                    f"Marked lead {existing_lead_sf_id[0]} as converted "
                    f"after loan creation from SF Opportunity {sf_id}"
                )
            except Exception as e:
                logger.warning(f"Failed to mark lead as converted for SF {sf_id}: {e}")

        return True

    async def _create_funded_record_from_contact(
        self,
        db: Session,
        sf_record: Dict[str, Any],
        sf_type: str,
        user_id: int,
    ) -> bool:
        """Create a loan + MUM record from a funded SF Lead/Contact.

        Called when _create_crm_lead_if_new detects a funded status. Instead of
        silently dropping the record, we create a minimal loan and promote to MUM
        so the borrower appears on the MUM page.

        Returns True if a new record was created, False if it already existed.
        """
        from sqlalchemy import text
        import uuid

        sf_id = sf_record.get('Id')
        email = sf_record.get('Email')

        # Dedup: check if already exists as loan, MUM, or lead
        for tbl, id_col, uid_col in [
            ('loans', 'salesforce_id', 'loan_officer_id'),
            ('mum_clients', 'salesforce_id', 'user_id'),
            ('leads', 'salesforce_id', 'owner_id'),
        ]:
            row = db.execute(text(
                f"SELECT id FROM {tbl} WHERE {id_col} = :sf_id AND {uid_col} = :uid LIMIT 1"
            ), {"sf_id": sf_id, "uid": user_id}).fetchone()
            if row:
                logger.info(
                    f"Funded {sf_type} {sf_id} already exists in {tbl} ({row[0]}), skipping"
                )
                return False

        if email:
            for tbl, email_col, uid_col in [
                ('loans', 'borrower_email', 'loan_officer_id'),
                ('mum_clients', 'email', 'user_id'),
            ]:
                row = db.execute(text(
                    f"SELECT id FROM {tbl} WHERE LOWER({email_col}) = LOWER(:email) "
                    f"AND {uid_col} = :uid LIMIT 1"
                ), {"email": email, "uid": user_id}).fetchone()
                if row:
                    logger.info(
                        f"Funded {sf_type} {sf_id} matches existing {tbl} record "
                        f"({row[0]}) by email, skipping"
                    )
                    return False

        org_id = _get_org_id_for_user(db, user_id)

        first_name = sf_record.get('FirstName') or ''
        last_name = sf_record.get('LastName') or 'Unknown'
        borrower_name = f"{first_name} {last_name}".strip() or 'Unknown'
        phone = sf_record.get('Phone') or sf_record.get('MobilePhone')
        loan_number = f"SF-{str(uuid.uuid4())[:8].upper()}"

        result = db.execute(text("""
            INSERT INTO loans (
                loan_number, borrower_name, borrower_email, borrower_phone,
                stage, funded_date, salesforce_id, loan_officer_id, organization_id,
                created_at, updated_at
            ) VALUES (
                :loan_number, :borrower_name, :email, :phone,
                'FUNDED', CURRENT_DATE, :sf_id, :user_id, :org_id,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            RETURNING id
        """), {
            "loan_number": loan_number,
            "borrower_name": borrower_name,
            "email": email,
            "phone": phone,
            "sf_id": sf_id,
            "user_id": user_id,
            "org_id": org_id,
        })
        loan_id = result.fetchone()[0]
        logger.info(f"Created funded loan {loan_id} from SF {sf_type} {sf_id}")

        try:
            from services.mum_promotion_service import maybe_promote_loan_to_mum
            mum_id = maybe_promote_loan_to_mum(db, loan_id, user_id)
            if mum_id:
                logger.info(f"Promoted funded loan {loan_id} to MUM client {mum_id}")
        except Exception as e:
            logger.warning(f"MUM promotion failed for funded {sf_type} {sf_id}: {e}")

        return True

    async def _get_contact_for_account(
        self,
        db: Session,
        sf_opp_id: str,
        account_id: str,
        user_id: int
    ) -> Dict[str, Any]:
        """Get primary contact info for a Salesforce Account (for borrower details)."""
        from sqlalchemy import text

        access_token, instance_url = await salesforce_oauth.get_access_token(
            db, db.execute(text("""
                SELECT id FROM integration_profiles
                WHERE user_id = :user_id AND provider = 'salesforce'
                LIMIT 1
            """), {"user_id": user_id}).fetchone().id
        )

        # Fix 1b: Sanitize account_id before SOQL interpolation
        safe_account_id = _sanitize_soql_string(account_id)
        soql = f"SELECT FirstName, LastName, Email, Phone, MobilePhone FROM Contact WHERE AccountId = '{safe_account_id}' AND Email != null ORDER BY LastModifiedDate DESC LIMIT 1"

        async with get_sf_client() as client:
            response = await client.get(
                f"{instance_url}/services/data/{SF_API_VERSION}/query",
                params={"q": soql},
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=15.0
            )

            if response.status_code == 200:
                data = response.json()
                if data.get('totalSize', 0) > 0:
                    record = data['records'][0]
                    first = record.get('FirstName') or ''
                    last = record.get('LastName') or ''
                    full_name = f"{first} {last}".strip()
                    return {
                        'first_name': first,
                        'last_name': last,
                        'full_name': full_name,
                        'email': record.get('Email'),
                        'phone': record.get('Phone') or record.get('MobilePhone'),
                    }

        return {}


    # =========================================================================
    # OUTBOUND SYNC — extracted to _webhooks.OutboundSyncMixin
    # push_loan_to_salesforce, push_lead_to_salesforce, push_email_to_salesforce,
    # push_calendar_event_to_salesforce, sync_outbound, _find_salesforce_record_by_email
    # =========================================================================


    def _map_crm_stage_to_salesforce(self, crm_stage: str) -> str:
        """Map CRM loan stage to Salesforce Opportunity stage"""
        return map_crm_stage_to_salesforce(crm_stage)

    def _map_crm_lead_stage_to_salesforce(self, crm_stage: str) -> str:
        """Map CRM lead stage to Salesforce Lead status"""
        return map_crm_lead_stage_to_salesforce(crm_stage)


# Export singleton instance
salesforce_sync = SalesforceSyncService()
