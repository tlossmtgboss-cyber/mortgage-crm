"""
Salesforce Sync Engine
Handles BIDIRECTIONAL data synchronization: Salesforce ↔ CRM

Data flows BOTH WAYS:
- Inbound: Salesforce → CRM (pull emails, calendar, loans, leads)
- Outbound: CRM → Salesforce (push updated loans, leads, activities)

Sync runs automatically every 5 minutes via APScheduler.
"""
import hashlib
import json
import logging
from datetime import datetime, timedelta
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

            # Always include the Salesforce ID
            transformed_data['salesforce_id'] = record.get('Id')

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
        Handles leads and loans from Salesforce.
        """
        from sqlalchemy import text
        from datetime import datetime, timezone

        # Get user who owns this integration
        profile = db.query(IntegrationProfile).filter(
            IntegrationProfile.id == integration_profile_id
        ).first()

        if not profile:
            raise ValueError("Integration profile not found")

        user_id = profile.user_id
        salesforce_id = data.pop('salesforce_id', None)

        logger.info(f"Upserting to {target_entity}: salesforce_id={salesforce_id}")

        if target_entity == 'lead':
            return await self._upsert_lead(db, user_id, salesforce_id, data)
        elif target_entity == 'loan':
            return await self._upsert_loan(db, user_id, salesforce_id, data)
        elif target_entity == 'borrower':
            # Borrower data goes into loan record
            return await self._upsert_loan(db, user_id, salesforce_id, data)
        else:
            logger.warning(f"Unknown target entity: {target_entity}")
            return None

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

        # Check if lead exists by salesforce_id or email
        existing = None
        if salesforce_id:
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

        # Map Salesforce fields to CRM fields
        lead_data = {
            "first_name": data.get('first_name') or data.get('FirstName', ''),
            "last_name": data.get('last_name') or data.get('LastName', ''),
            "email": data.get('email') or data.get('Email', ''),
            "phone": data.get('phone') or data.get('Phone', ''),
            "company": data.get('company') or data.get('Company', ''),
            "source": data.get('source') or data.get('LeadSource', 'Salesforce'),
        }

        # Remove empty values
        lead_data = {k: v for k, v in lead_data.items() if v}

        if existing:
            # Update existing lead
            lead_id = existing[0]
            set_clauses = ", ".join([f"{k} = :{k}" for k in lead_data.keys()])
            if set_clauses:
                lead_data['lead_id'] = lead_id
                lead_data['salesforce_id'] = salesforce_id
                db.execute(text(f"""
                    UPDATE leads SET {set_clauses},
                        salesforce_id = :salesforce_id,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :lead_id
                """), lead_data)
            logger.info(f"Updated lead {lead_id} from Salesforce {salesforce_id}")
            return lead_id
        else:
            # Create new lead
            lead_data['owner_id'] = user_id
            lead_data['salesforce_id'] = salesforce_id
            lead_data['stage'] = 'new'

            columns = ", ".join(lead_data.keys())
            placeholders = ", ".join([f":{k}" for k in lead_data.keys()])

            result = db.execute(text(f"""
                INSERT INTO leads ({columns}, created_at, updated_at)
                VALUES ({placeholders}, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                RETURNING id
            """), lead_data)

            lead_id = result.fetchone()[0]
            logger.info(f"Created lead {lead_id} from Salesforce {salesforce_id}")
            return lead_id

    async def _upsert_loan(
        self,
        db: Session,
        user_id: int,
        salesforce_id: str,
        data: Dict[str, Any]
    ) -> Optional[int]:
        """Upsert a loan from Salesforce Opportunity"""
        from sqlalchemy import text
        from datetime import datetime, timezone
        import uuid

        # Check if loan exists by salesforce_id
        existing = None
        if salesforce_id:
            existing = db.execute(text("""
                SELECT id FROM loans
                WHERE salesforce_id = :sf_id
                LIMIT 1
            """), {"sf_id": salesforce_id}).fetchone()

        # Map Salesforce Opportunity fields to CRM loan fields
        loan_data = {
            "borrower_name": data.get('borrower_name') or data.get('Name', ''),
            "borrower_email": data.get('borrower_email') or data.get('Email__c', ''),
            "borrower_phone": data.get('borrower_phone') or data.get('Phone__c', ''),
            "amount": float(data.get('amount') or data.get('Amount', 0) or 0),
            "property_address": data.get('property_address') or data.get('Property_Address__c', ''),
            "loan_type": data.get('loan_type') or data.get('Loan_Type__c', ''),
            "program": data.get('program') or data.get('Loan_Program__c', ''),
        }

        # Handle closing date
        closing_date = data.get('closing_date') or data.get('CloseDate')
        if closing_date:
            if isinstance(closing_date, str):
                try:
                    loan_data['closing_date'] = closing_date
                except Exception:
                    pass

        # Map stage from Salesforce StageName
        sf_stage = data.get('stage') or data.get('StageName', '')
        loan_data['stage'] = self._map_salesforce_stage(sf_stage)

        # Remove empty values but keep amount even if 0
        loan_data = {k: v for k, v in loan_data.items() if v or k == 'amount'}

        if existing:
            # Update existing loan
            loan_id = existing[0]
            set_clauses = ", ".join([f"{k} = :{k}" for k in loan_data.keys() if k != 'amount'])
            if 'amount' in loan_data:
                if set_clauses:
                    set_clauses += ", amount = :amount"
                else:
                    set_clauses = "amount = :amount"

            if set_clauses:
                loan_data['loan_id'] = loan_id
                loan_data['salesforce_id'] = salesforce_id
                db.execute(text(f"""
                    UPDATE loans SET {set_clauses},
                        salesforce_id = :salesforce_id,
                        salesforce_last_synced_at = CURRENT_TIMESTAMP,
                        salesforce_sync_status = 'synced',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :loan_id
                """), loan_data)
            logger.info(f"Updated loan {loan_id} from Salesforce {salesforce_id}")
            return loan_id
        else:
            # Create new loan - need loan_number
            loan_number = f"SF-{str(uuid.uuid4())[:8].upper()}"
            loan_data['loan_number'] = loan_number
            loan_data['loan_officer_id'] = user_id
            loan_data['salesforce_id'] = salesforce_id
            loan_data['salesforce_sync_status'] = 'synced'

            # Ensure required fields have defaults
            if not loan_data.get('borrower_name'):
                loan_data['borrower_name'] = 'Unknown Borrower'
            if not loan_data.get('amount'):
                loan_data['amount'] = 0
            if not loan_data.get('stage'):
                loan_data['stage'] = 'Application'

            columns = ", ".join(loan_data.keys())
            placeholders = ", ".join([f":{k}" for k in loan_data.keys()])

            result = db.execute(text(f"""
                INSERT INTO loans ({columns}, salesforce_last_synced_at, created_at, updated_at)
                VALUES ({placeholders}, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                RETURNING id
            """), loan_data)

            loan_id = result.fetchone()[0]
            logger.info(f"Created loan {loan_id} ({loan_number}) from Salesforce {salesforce_id}")
            return loan_id

    def _map_salesforce_stage(self, sf_stage: str) -> str:
        """Map Salesforce Opportunity stage to CRM loan stage"""
        stage_mapping = {
            # Common Salesforce stages
            'Prospecting': 'Application',
            'Qualification': 'Application',
            'Needs Analysis': 'Application',
            'Value Proposition': 'Processing',
            'Id. Decision Makers': 'Processing',
            'Perception Analysis': 'Processing',
            'Proposal/Price Quote': 'Submitted',
            'Negotiation/Review': 'Underwriting',
            'Closed Won': 'Funded',
            'Closed Lost': 'Application',
            # Mortgage-specific stages
            'Application': 'Application',
            'Processing': 'Processing',
            'Submitted': 'Submitted',
            'Underwriting': 'Underwriting',
            'Conditional Approval': 'Conditional Approval',
            'Approved': 'Approved',
            'Clear to Close': 'CTC',
            'CTC': 'CTC',
            'Docs Out': 'Docs Out',
            'Closing': 'Closing',
            'Funded': 'Funded',
        }
        return stage_mapping.get(sf_stage, 'Application')

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


    # =========================================================================
    # OUTBOUND SYNC - Push CRM data TO Salesforce
    # =========================================================================

    async def push_loan_to_salesforce(
        self,
        db: Session,
        integration_profile_id: int,
        loan_id: int
    ) -> Dict[str, Any]:
        """
        Push a CRM loan to Salesforce as an Opportunity.

        Args:
            db: Database session
            integration_profile_id: User's Salesforce integration profile
            loan_id: CRM loan ID to push

        Returns:
            Result dict with salesforce_id and success status
        """
        from sqlalchemy import text

        # Get access token
        access_token, instance_url = await salesforce_oauth.get_access_token(
            db, integration_profile_id
        )

        # Get loan data
        loan = db.execute(text("""
            SELECT l.*, u.email as lo_email, u.name as lo_name
            FROM loans l
            LEFT JOIN users u ON u.id = l.loan_officer_id
            WHERE l.id = :loan_id
        """), {"loan_id": loan_id}).fetchone()

        if not loan:
            raise ValueError(f"Loan {loan_id} not found")

        # Map CRM loan fields to Salesforce Opportunity fields
        opportunity_data = {
            "Name": loan.borrower_name or f"Loan {loan.loan_number}",
            "Amount": float(loan.amount or 0),
            "StageName": self._map_crm_stage_to_salesforce(loan.stage),
            "CloseDate": str(loan.closing_date or loan.expected_close_date or datetime.utcnow().date()),
            "Description": f"Loan #{loan.loan_number}\nProperty: {loan.property_address or 'N/A'}",
        }

        # Add custom fields if they exist in Salesforce
        custom_fields = {
            "Loan_Number__c": loan.loan_number,
            "Property_Address__c": loan.property_address,
            "Loan_Type__c": loan.loan_type,
            "Loan_Program__c": loan.program,
            "Borrower_Email__c": loan.borrower_email,
            "Borrower_Phone__c": loan.borrower_phone,
            "Interest_Rate__c": float(loan.interest_rate) if loan.interest_rate else None,
            "LTV__c": float(loan.ltv) if hasattr(loan, 'ltv') and loan.ltv else None,
        }

        # Only include custom fields that have values
        for field, value in custom_fields.items():
            if value is not None:
                opportunity_data[field] = value

        # Check if loan already has a Salesforce ID (update) or needs to be created
        salesforce_id = loan.salesforce_id

        async with httpx.AsyncClient() as client:
            if salesforce_id:
                # UPDATE existing Opportunity
                response = await client.patch(
                    f"{instance_url}/services/data/v59.0/sobjects/Opportunity/{salesforce_id}",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json"
                    },
                    json=opportunity_data,
                    timeout=30.0
                )

                if response.status_code == 204:
                    logger.info(f"Updated Salesforce Opportunity {salesforce_id} for loan {loan_id}")

                    # Update loan's sync status
                    db.execute(text("""
                        UPDATE loans SET
                            salesforce_last_synced_at = CURRENT_TIMESTAMP,
                            salesforce_sync_status = 'synced',
                            salesforce_sync_direction = 'outbound'
                        WHERE id = :loan_id
                    """), {"loan_id": loan_id})
                    db.commit()

                    return {
                        "success": True,
                        "salesforce_id": salesforce_id,
                        "action": "updated",
                        "loan_id": loan_id
                    }
                else:
                    error = response.text
                    logger.error(f"Failed to update Salesforce Opportunity: {error}")
                    return {
                        "success": False,
                        "error": error,
                        "loan_id": loan_id
                    }
            else:
                # CREATE new Opportunity
                response = await client.post(
                    f"{instance_url}/services/data/v59.0/sobjects/Opportunity",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json"
                    },
                    json=opportunity_data,
                    timeout=30.0
                )

                if response.status_code == 201:
                    result = response.json()
                    salesforce_id = result.get('id')

                    logger.info(f"Created Salesforce Opportunity {salesforce_id} for loan {loan_id}")

                    # Update loan with Salesforce ID
                    db.execute(text("""
                        UPDATE loans SET
                            salesforce_id = :sf_id,
                            salesforce_last_synced_at = CURRENT_TIMESTAMP,
                            salesforce_sync_status = 'synced',
                            salesforce_sync_direction = 'outbound'
                        WHERE id = :loan_id
                    """), {"sf_id": salesforce_id, "loan_id": loan_id})
                    db.commit()

                    return {
                        "success": True,
                        "salesforce_id": salesforce_id,
                        "action": "created",
                        "loan_id": loan_id
                    }
                else:
                    error = response.text
                    logger.error(f"Failed to create Salesforce Opportunity: {error}")
                    return {
                        "success": False,
                        "error": error,
                        "loan_id": loan_id
                    }

    async def push_lead_to_salesforce(
        self,
        db: Session,
        integration_profile_id: int,
        lead_id: int
    ) -> Dict[str, Any]:
        """
        Push a CRM lead to Salesforce as a Lead.

        Args:
            db: Database session
            integration_profile_id: User's Salesforce integration profile
            lead_id: CRM lead ID to push

        Returns:
            Result dict with salesforce_id and success status
        """
        from sqlalchemy import text

        # Get access token
        access_token, instance_url = await salesforce_oauth.get_access_token(
            db, integration_profile_id
        )

        # Get lead data
        lead = db.execute(text("""
            SELECT * FROM leads WHERE id = :lead_id
        """), {"lead_id": lead_id}).fetchone()

        if not lead:
            raise ValueError(f"Lead {lead_id} not found")

        # Map CRM lead fields to Salesforce Lead fields
        lead_data = {
            "FirstName": lead.first_name or "",
            "LastName": lead.last_name or "Unknown",
            "Email": lead.email,
            "Phone": lead.phone,
            "Company": lead.company or "Individual",
            "LeadSource": lead.source or "CRM",
            "Status": self._map_crm_lead_stage_to_salesforce(lead.stage),
            "Description": f"CRM Lead ID: {lead.id}",
        }

        # Add custom fields if they exist
        custom_fields = {
            "CRM_Lead_ID__c": str(lead.id),
            "Loan_Amount__c": float(lead.estimated_loan_amount) if hasattr(lead, 'estimated_loan_amount') and lead.estimated_loan_amount else None,
            "Property_Type__c": lead.property_type if hasattr(lead, 'property_type') else None,
        }

        for field, value in custom_fields.items():
            if value is not None:
                lead_data[field] = value

        # Check if lead already has a Salesforce ID
        salesforce_id = lead.salesforce_id if hasattr(lead, 'salesforce_id') else None

        async with httpx.AsyncClient() as client:
            if salesforce_id:
                # UPDATE existing Lead
                response = await client.patch(
                    f"{instance_url}/services/data/v59.0/sobjects/Lead/{salesforce_id}",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json"
                    },
                    json=lead_data,
                    timeout=30.0
                )

                if response.status_code == 204:
                    logger.info(f"Updated Salesforce Lead {salesforce_id} for CRM lead {lead_id}")

                    db.execute(text("""
                        UPDATE leads SET
                            updated_at = CURRENT_TIMESTAMP,
                            meta_data = COALESCE(meta_data, '{}'::jsonb) ||
                                jsonb_build_object('salesforce_synced_at', :synced_at)
                        WHERE id = :lead_id
                    """), {"lead_id": lead_id, "synced_at": datetime.utcnow().isoformat()})
                    db.commit()

                    return {
                        "success": True,
                        "salesforce_id": salesforce_id,
                        "action": "updated",
                        "lead_id": lead_id
                    }
                else:
                    error = response.text
                    logger.error(f"Failed to update Salesforce Lead: {error}")
                    return {"success": False, "error": error, "lead_id": lead_id}
            else:
                # CREATE new Lead
                response = await client.post(
                    f"{instance_url}/services/data/v59.0/sobjects/Lead",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json"
                    },
                    json=lead_data,
                    timeout=30.0
                )

                if response.status_code == 201:
                    result = response.json()
                    salesforce_id = result.get('id')

                    logger.info(f"Created Salesforce Lead {salesforce_id} for CRM lead {lead_id}")

                    db.execute(text("""
                        UPDATE leads SET
                            salesforce_id = :sf_id,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = :lead_id
                    """), {"sf_id": salesforce_id, "lead_id": lead_id})
                    db.commit()

                    return {
                        "success": True,
                        "salesforce_id": salesforce_id,
                        "action": "created",
                        "lead_id": lead_id
                    }
                else:
                    error = response.text
                    logger.error(f"Failed to create Salesforce Lead: {error}")
                    return {"success": False, "error": error, "lead_id": lead_id}

    async def push_email_to_salesforce(
        self,
        db: Session,
        integration_profile_id: int,
        email_id: int
    ) -> Dict[str, Any]:
        """
        Push a CRM email to Salesforce as a Task (Email type).

        Args:
            db: Database session
            integration_profile_id: User's Salesforce integration profile
            email_id: CRM email ID to push

        Returns:
            Result dict with salesforce_id and success status
        """
        from sqlalchemy import text

        access_token, instance_url = await salesforce_oauth.get_access_token(
            db, integration_profile_id
        )

        # Get email data with related lead/loan Salesforce IDs
        email = db.execute(text("""
            SELECT em.*,
                   l.salesforce_id as lead_sf_id,
                   lo.salesforce_id as loan_sf_id
            FROM email_messages em
            LEFT JOIN leads l ON l.id = em.lead_id
            LEFT JOIN loans lo ON lo.id = em.loan_id
            WHERE em.id = :email_id
        """), {"email_id": email_id}).fetchone()

        if not email:
            raise ValueError(f"Email {email_id} not found")

        # Build Task data
        task_data = {
            "Subject": email.subject or "Email Activity",
            "Description": (email.body or "")[:32000],
            "TaskSubtype": "Email",
            "Status": "Completed",
            "Priority": "Normal",
            "ActivityDate": email.created_at.strftime("%Y-%m-%d") if email.created_at else datetime.utcnow().strftime("%Y-%m-%d"),
        }

        # Link to Lead or Opportunity
        if email.lead_sf_id:
            task_data["WhoId"] = email.lead_sf_id
        if email.loan_sf_id:
            task_data["WhatId"] = email.loan_sf_id

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{instance_url}/services/data/v59.0/sobjects/Task",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                },
                json=task_data,
                timeout=30.0
            )

            if response.status_code == 201:
                result = response.json()
                salesforce_id = result.get('id')

                logger.info(f"Created Salesforce Task {salesforce_id} for email {email_id}")

                # Update email with Salesforce Task ID
                db.execute(text("""
                    UPDATE email_messages SET
                        meta_data = COALESCE(meta_data, '{}'::jsonb) ||
                            jsonb_build_object(
                                'salesforce_task_id', :sf_id,
                                'salesforce_pushed_at', :pushed_at
                            )
                    WHERE id = :email_id
                """), {
                    "sf_id": salesforce_id,
                    "pushed_at": datetime.utcnow().isoformat(),
                    "email_id": email_id
                })
                db.commit()

                return {
                    "success": True,
                    "salesforce_id": salesforce_id,
                    "action": "created",
                    "email_id": email_id
                }
            else:
                error = response.text
                logger.error(f"Failed to create Salesforce Task: {error}")
                return {"success": False, "error": error, "email_id": email_id}

    async def push_calendar_event_to_salesforce(
        self,
        db: Session,
        integration_profile_id: int,
        event_id: int
    ) -> Dict[str, Any]:
        """
        Push a CRM calendar event to Salesforce as an Event.

        Args:
            db: Database session
            integration_profile_id: User's Salesforce integration profile
            event_id: CRM calendar event ID to push

        Returns:
            Result dict with salesforce_id and success status
        """
        from sqlalchemy import text

        access_token, instance_url = await salesforce_oauth.get_access_token(
            db, integration_profile_id
        )

        # Get event data
        event = db.execute(text("""
            SELECT ce.*,
                   l.salesforce_id as lead_sf_id,
                   lo.salesforce_id as loan_sf_id
            FROM calendar_events ce
            LEFT JOIN leads l ON l.id = ce.lead_id
            LEFT JOIN loans lo ON lo.id = ce.loan_id
            WHERE ce.id = :event_id
        """), {"event_id": event_id}).fetchone()

        if not event:
            raise ValueError(f"Calendar event {event_id} not found")

        # Build Salesforce Event data
        event_data = {
            "Subject": event.title or "CRM Event",
            "Description": event.description or "",
            "StartDateTime": event.start_time.isoformat() if event.start_time else datetime.utcnow().isoformat(),
            "EndDateTime": event.end_time.isoformat() if event.end_time else (event.start_time + timedelta(hours=1)).isoformat() if event.start_time else datetime.utcnow().isoformat(),
            "Location": event.location if hasattr(event, 'location') and event.location else None,
            "IsAllDayEvent": event.all_day if hasattr(event, 'all_day') else False,
        }

        # Remove None values
        event_data = {k: v for k, v in event_data.items() if v is not None}

        # Link to Lead or Opportunity
        if hasattr(event, 'lead_sf_id') and event.lead_sf_id:
            event_data["WhoId"] = event.lead_sf_id
        if hasattr(event, 'loan_sf_id') and event.loan_sf_id:
            event_data["WhatId"] = event.loan_sf_id

        # Check for existing Salesforce ID
        salesforce_id = None
        if hasattr(event, 'meta_data') and event.meta_data:
            salesforce_id = event.meta_data.get('salesforce_event_id')

        async with httpx.AsyncClient() as client:
            if salesforce_id:
                # UPDATE existing Event
                response = await client.patch(
                    f"{instance_url}/services/data/v59.0/sobjects/Event/{salesforce_id}",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json"
                    },
                    json=event_data,
                    timeout=30.0
                )

                if response.status_code == 204:
                    logger.info(f"Updated Salesforce Event {salesforce_id}")
                    return {
                        "success": True,
                        "salesforce_id": salesforce_id,
                        "action": "updated",
                        "event_id": event_id
                    }
                else:
                    error = response.text
                    return {"success": False, "error": error, "event_id": event_id}
            else:
                # CREATE new Event
                response = await client.post(
                    f"{instance_url}/services/data/v59.0/sobjects/Event",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json"
                    },
                    json=event_data,
                    timeout=30.0
                )

                if response.status_code == 201:
                    result = response.json()
                    salesforce_id = result.get('id')

                    logger.info(f"Created Salesforce Event {salesforce_id}")

                    # Update CRM event with Salesforce ID
                    db.execute(text("""
                        UPDATE calendar_events SET
                            meta_data = COALESCE(meta_data, '{}'::jsonb) ||
                                jsonb_build_object(
                                    'salesforce_event_id', :sf_id,
                                    'salesforce_pushed_at', :pushed_at
                                )
                        WHERE id = :event_id
                    """), {
                        "sf_id": salesforce_id,
                        "pushed_at": datetime.utcnow().isoformat(),
                        "event_id": event_id
                    })
                    db.commit()

                    return {
                        "success": True,
                        "salesforce_id": salesforce_id,
                        "action": "created",
                        "event_id": event_id
                    }
                else:
                    error = response.text
                    return {"success": False, "error": error, "event_id": event_id}

    async def sync_outbound(
        self,
        db: Session,
        integration_profile_id: int,
        sync_loans: bool = True,
        sync_leads: bool = True,
        sync_emails: bool = True,
        sync_calendar: bool = True,
        since_hours: int = 24
    ) -> Dict[str, Any]:
        """
        Push all recent CRM changes to Salesforce.

        Args:
            db: Database session
            integration_profile_id: User's Salesforce integration profile
            sync_loans: Push loan changes
            sync_leads: Push lead changes
            sync_emails: Push email activities
            sync_calendar: Push calendar events
            since_hours: Only sync records modified in the last N hours

        Returns:
            Summary of sync results
        """
        from sqlalchemy import text

        profile = db.query(IntegrationProfile).filter(
            IntegrationProfile.id == integration_profile_id
        ).first()

        if not profile:
            raise ValueError("Integration profile not found")

        user_id = profile.user_id
        since = datetime.utcnow() - timedelta(hours=since_hours)

        results = {
            "success": True,
            "loans": {"pushed": 0, "failed": 0, "errors": []},
            "leads": {"pushed": 0, "failed": 0, "errors": []},
            "emails": {"pushed": 0, "failed": 0, "errors": []},
            "calendar": {"pushed": 0, "failed": 0, "errors": []},
        }

        # Sync Loans
        if sync_loans:
            loans = db.execute(text("""
                SELECT id FROM loans
                WHERE loan_officer_id = :user_id
                  AND updated_at >= :since
                  AND (salesforce_sync_status IS NULL
                       OR salesforce_sync_status != 'synced'
                       OR salesforce_last_synced_at < updated_at)
                ORDER BY updated_at DESC
                LIMIT 100
            """), {"user_id": user_id, "since": since}).fetchall()

            for loan in loans:
                try:
                    result = await self.push_loan_to_salesforce(db, integration_profile_id, loan.id)
                    if result['success']:
                        results['loans']['pushed'] += 1
                    else:
                        results['loans']['failed'] += 1
                        results['loans']['errors'].append(result.get('error', 'Unknown error')[:100])
                except Exception as e:
                    results['loans']['failed'] += 1
                    results['loans']['errors'].append(str(e)[:100])
                    # Rollback to recover from any transaction errors
                    try:
                        db.rollback()
                    except Exception:
                        pass

        # Sync Leads
        if sync_leads:
            leads = db.execute(text("""
                SELECT id FROM leads
                WHERE owner_id = :user_id
                  AND updated_at >= :since
                  AND (salesforce_id IS NULL
                       OR (meta_data->>'salesforce_synced_at')::timestamp < updated_at)
                ORDER BY updated_at DESC
                LIMIT 100
            """), {"user_id": user_id, "since": since}).fetchall()

            for lead in leads:
                try:
                    result = await self.push_lead_to_salesforce(db, integration_profile_id, lead.id)
                    if result['success']:
                        results['leads']['pushed'] += 1
                    else:
                        results['leads']['failed'] += 1
                        results['leads']['errors'].append(result.get('error', 'Unknown error')[:100])
                except Exception as e:
                    results['leads']['failed'] += 1
                    results['leads']['errors'].append(str(e)[:100])
                    # Rollback to recover from any transaction errors
                    try:
                        db.rollback()
                    except Exception:
                        pass

        # Sync Emails
        if sync_emails:
            emails = db.execute(text("""
                SELECT id FROM email_messages
                WHERE user_id = :user_id
                  AND created_at >= :since
                  AND direction = 'outbound'
                  AND (meta_data IS NULL OR meta_data->>'salesforce_task_id' IS NULL)
                ORDER BY created_at DESC
                LIMIT 100
            """), {"user_id": user_id, "since": since}).fetchall()

            for email in emails:
                try:
                    result = await self.push_email_to_salesforce(db, integration_profile_id, email.id)
                    if result['success']:
                        results['emails']['pushed'] += 1
                    else:
                        results['emails']['failed'] += 1
                        results['emails']['errors'].append(result.get('error', 'Unknown error')[:100])
                except Exception as e:
                    results['emails']['failed'] += 1
                    results['emails']['errors'].append(str(e)[:100])
                    # Rollback to recover from any transaction errors
                    try:
                        db.rollback()
                    except Exception:
                        pass

        # Sync Calendar Events
        if sync_calendar:
            events = db.execute(text("""
                SELECT id FROM calendar_events
                WHERE user_id = :user_id
                  AND updated_at >= :since
                  AND (meta_data IS NULL OR meta_data->>'salesforce_event_id' IS NULL)
                ORDER BY updated_at DESC
                LIMIT 100
            """), {"user_id": user_id, "since": since}).fetchall()

            for event in events:
                try:
                    result = await self.push_calendar_event_to_salesforce(db, integration_profile_id, event.id)
                    if result['success']:
                        results['calendar']['pushed'] += 1
                    else:
                        results['calendar']['failed'] += 1
                        results['calendar']['errors'].append(result.get('error', 'Unknown error')[:100])
                except Exception as e:
                    results['calendar']['failed'] += 1
                    results['calendar']['errors'].append(str(e)[:100])
                    # Rollback to recover from any transaction errors
                    try:
                        db.rollback()
                    except Exception:
                        pass

        # Check overall success
        total_failed = sum([
            results['loans']['failed'],
            results['leads']['failed'],
            results['emails']['failed'],
            results['calendar']['failed']
        ])
        results['success'] = total_failed == 0

        logger.info(
            f"Outbound sync complete: "
            f"loans={results['loans']['pushed']}, "
            f"leads={results['leads']['pushed']}, "
            f"emails={results['emails']['pushed']}, "
            f"calendar={results['calendar']['pushed']}"
        )

        return results

    def _map_crm_stage_to_salesforce(self, crm_stage: str) -> str:
        """Map CRM loan stage to Salesforce Opportunity stage"""
        stage_mapping = {
            'Application': 'Qualification',
            'Processing': 'Needs Analysis',
            'Submitted': 'Proposal/Price Quote',
            'Underwriting': 'Negotiation/Review',
            'Conditional Approval': 'Negotiation/Review',
            'Approved': 'Negotiation/Review',
            'CTC': 'Negotiation/Review',
            'Clear to Close': 'Negotiation/Review',
            'Docs Out': 'Negotiation/Review',
            'Closing': 'Negotiation/Review',
            'Funded': 'Closed Won',
            'Cancelled': 'Closed Lost',
            'Denied': 'Closed Lost',
        }
        return stage_mapping.get(crm_stage, 'Qualification')

    def _map_crm_lead_stage_to_salesforce(self, crm_stage: str) -> str:
        """Map CRM lead stage to Salesforce Lead status"""
        stage_mapping = {
            'new': 'Open - Not Contacted',
            'contacted': 'Working - Contacted',
            'qualified': 'Closed - Converted',
            'unqualified': 'Closed - Not Converted',
            'converted': 'Closed - Converted',
        }
        return stage_mapping.get(crm_stage, 'Open - Not Contacted')


# Export singleton instance
salesforce_sync = SalesforceSyncService()
