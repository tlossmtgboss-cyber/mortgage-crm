"""
Salesforce Schema Discovery Service
Auto-discovers the structure of each user's Salesforce org
"""
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
import httpx

from sqlalchemy.orm import Session

from salesforce_integration_models import (
    IntegrationProfile,
    SfUserSchema,
    IntegrationEvent
)
from .oauth_service import salesforce_oauth

logger = logging.getLogger(__name__)


# Canonical field mappings (what the CRM expects)
CANONICAL_MAPPINGS = {
    # Borrower fields
    'first_name': {'entity': 'borrower', 'field': 'first_name', 'aliases': ['firstname', 'fname', 'first', 'borrowerfirstname']},
    'last_name': {'entity': 'borrower', 'field': 'last_name', 'aliases': ['lastname', 'lname', 'last', 'borrowerlastname']},
    'email': {'entity': 'borrower', 'field': 'email', 'aliases': ['emailaddress', 'email__c', 'borroweremail']},
    'phone': {'entity': 'borrower', 'field': 'phone', 'aliases': ['mobilephone', 'phone__c', 'cellphone', 'mobile']},
    'ssn': {'entity': 'borrower', 'field': 'ssn', 'aliases': ['socialsecuritynumber', 'ssn__c', 'social']},

    # Loan fields
    'loan_amount': {'entity': 'loan', 'field': 'loan_amount', 'aliases': ['loanamount__c', 'amount', 'requestedamount']},
    'loan_purpose': {'entity': 'loan', 'field': 'loan_purpose', 'aliases': ['purpose__c', 'loanpurpose__c', 'purpose']},
    'property_value': {'entity': 'loan', 'field': 'property_value', 'aliases': ['propertyvalue__c', 'homevalue', 'purchaseprice']},
    'loan_type': {'entity': 'loan', 'field': 'loan_type', 'aliases': ['loantype__c', 'producttype', 'program']},

    # Stage/Status
    'stage': {'entity': 'loan', 'field': 'stage', 'aliases': ['status', 'stage__c', 'leadstatus', 'opportunitystage']},

    # Property
    'property_address': {'entity': 'property', 'field': 'address', 'aliases': ['propertyaddress__c', 'streetaddress', 'address']},
    'property_city': {'entity': 'property', 'field': 'city', 'aliases': ['propertycity__c', 'city']},
    'property_state': {'entity': 'property', 'field': 'state', 'aliases': ['propertystate__c', 'state']},
    'property_zip': {'entity': 'property', 'field': 'zip', 'aliases': ['propertyzip__c', 'postalcode', 'zipcode']}
}


class SalesforceSchemaService:
    """Discovers and manages Salesforce schema for each user's org"""

    async def discover_schema(self, db: Session, integration_profile_id: int):
        """Discover schema for all relevant objects"""
        start_time = datetime.utcnow()

        try:
            # Get access token
            access_token, instance_url = await salesforce_oauth.get_access_token(
                db, integration_profile_id
            )

            # Objects to discover (can be configured per user later)
            objects_to_discover = ['Lead', 'Contact', 'Account', 'Opportunity']

            # Discover custom objects related to mortgage/lending
            custom_objects = await self._discover_custom_objects(access_token, instance_url)
            objects_to_discover.extend(custom_objects)

            # Discover each object's schema
            discovered = []
            for object_name in objects_to_discover:
                schema = await self._discover_object(access_token, instance_url, object_name)
                if schema:
                    discovered.append(schema)

            # Store schemas in database
            self._store_schemas(db, integration_profile_id, discovered)

            # Update profile status
            profile = db.query(IntegrationProfile).filter(
                IntegrationProfile.id == integration_profile_id
            ).first()
            profile.status = 'mapping_required'
            profile.last_error = None
            db.commit()

            # Log success event
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            event = IntegrationEvent(
                integration_profile_id=integration_profile_id,
                event_type='schema_discovered',
                status='success',
                duration_ms=duration_ms,
                event_data={
                    'objects_discovered': len(discovered),
                    'custom_objects_found': len(custom_objects)
                }
            )
            db.add(event)
            db.commit()

            return discovered

        except Exception as e:
            # Log failure event
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            event = IntegrationEvent(
                integration_profile_id=integration_profile_id,
                event_type='schema_discovery_failed',
                status='error',
                error_message=str(e),
                duration_ms=duration_ms
            )
            db.add(event)

            # Update profile with error
            profile = db.query(IntegrationProfile).filter(
                IntegrationProfile.id == integration_profile_id
            ).first()
            if profile:
                profile.status = 'error'
                profile.last_error = f"Schema discovery failed: {str(e)}"
            db.commit()

            raise

    async def _discover_custom_objects(
        self,
        access_token: str,
        instance_url: str
    ) -> List[str]:
        """Discover custom objects (especially mortgage-related)"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{instance_url}/services/data/v60.0/sobjects",
                headers={
                    'Authorization': f'Bearer {access_token}',
                    'Content-Type': 'application/json'
                }
            )

            if response.status_code != 200:
                raise ValueError("Failed to list Salesforce objects")

            data = response.json()

        # Filter for custom objects related to mortgage/lending
        mortgage_keywords = [
            'loan', 'mortgage', 'application', 'borrower',
            'property', 'appraisal', 'underwriting', 'closing',
            'refinance', 'preapproval', 'credit', 'income'
        ]

        custom_objects = []
        for obj in data.get('sobjects', []):
            if not obj.get('custom'):
                continue

            name = obj.get('name', '').lower()
            label = obj.get('label', '').lower()

            # Check if related to mortgage/lending
            if any(keyword in name or keyword in label for keyword in mortgage_keywords):
                custom_objects.append(obj['name'])

        return custom_objects

    async def _discover_object(
        self,
        access_token: str,
        instance_url: str,
        object_name: str
    ) -> Optional[Dict[str, Any]]:
        """Discover schema for a specific object"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{instance_url}/services/data/v60.0/sobjects/{object_name}/describe",
                    headers={
                        'Authorization': f'Bearer {access_token}',
                        'Content-Type': 'application/json'
                    }
                )

                if response.status_code != 200:
                    logger.warning(f"Failed to describe {object_name}: {response.status_code}")
                    return None

                data = response.json()

            # Transform Salesforce fields to our format
            fields = []
            for field in data.get('fields', []):
                field_info = {
                    'name': field.get('name'),
                    'label': field.get('label'),
                    'type': field.get('type'),
                    'length': field.get('length'),
                    'precision': field.get('precision'),
                    'scale': field.get('scale'),
                    'required': not field.get('nillable', True) and not field.get('defaultedOnCreate', False),
                    'nillable': field.get('nillable', True),
                    'defaultValue': field.get('defaultValue'),
                    'custom': field.get('custom', False)
                }

                # Handle picklist values
                if field.get('picklistValues'):
                    field_info['picklistValues'] = [
                        {
                            'value': pv.get('value'),
                            'label': pv.get('label'),
                            'active': pv.get('active'),
                            'defaultValue': pv.get('defaultValue')
                        }
                        for pv in field['picklistValues']
                    ]

                # Handle reference fields
                if field.get('referenceTo'):
                    field_info['referenceTo'] = field['referenceTo']
                    field_info['relationshipName'] = field.get('relationshipName')

                fields.append(field_info)

            # Get record types if available
            record_types = None
            record_type_infos = data.get('recordTypeInfos', [])
            if len(record_type_infos) > 1:
                record_types = [
                    {
                        'name': rt.get('name'),
                        'recordTypeId': rt.get('recordTypeId'),
                        'developerName': rt.get('developerName'),
                        'active': rt.get('active')
                    }
                    for rt in record_type_infos
                    if rt.get('available') and rt.get('recordTypeId') != '012000000000000AAA'
                ]

            return {
                'name': data.get('name'),
                'label': data.get('label'),
                'labelPlural': data.get('labelPlural'),
                'custom': data.get('custom', False),
                'fields': fields,
                'recordTypes': record_types
            }

        except Exception as e:
            logger.error(f"Error discovering {object_name}: {e}")
            return None

    def _store_schemas(
        self,
        db: Session,
        integration_profile_id: int,
        schemas: List[Dict[str, Any]]
    ):
        """Store discovered schemas in database"""
        for schema in schemas:
            # Extract picklist values for easy reference
            picklist_values = {}
            for field in schema.get('fields', []):
                if field.get('picklistValues'):
                    picklist_values[field['name']] = field['picklistValues']

            # Check for existing schema
            existing = db.query(SfUserSchema).filter(
                SfUserSchema.integration_profile_id == integration_profile_id,
                SfUserSchema.object_name == schema['name']
            ).first()

            if existing:
                existing.fields = schema['fields']
                existing.record_types = schema.get('recordTypes')
                existing.picklist_values = picklist_values
                existing.discovered_at = datetime.utcnow()
            else:
                new_schema = SfUserSchema(
                    integration_profile_id=integration_profile_id,
                    object_name=schema['name'],
                    fields=schema['fields'],
                    record_types=schema.get('recordTypes'),
                    picklist_values=picklist_values,
                    discovered_at=datetime.utcnow()
                )
                db.add(new_schema)

        db.commit()

    def get_object_schema(
        self,
        db: Session,
        integration_profile_id: int,
        object_name: str
    ) -> Optional[Dict[str, Any]]:
        """Get schema for a specific object"""
        schema = db.query(SfUserSchema).filter(
            SfUserSchema.integration_profile_id == integration_profile_id,
            SfUserSchema.object_name == object_name
        ).first()

        if not schema:
            return None

        return {
            'name': object_name,
            'label': object_name,
            'labelPlural': object_name,
            'custom': object_name.endswith('__c'),
            'fields': schema.fields,
            'recordTypes': schema.record_types
        }

    def get_all_schemas(
        self,
        db: Session,
        integration_profile_id: int
    ) -> List[Dict[str, Any]]:
        """Get all discovered schemas for a user"""
        schemas = db.query(SfUserSchema).filter(
            SfUserSchema.integration_profile_id == integration_profile_id
        ).order_by(SfUserSchema.object_name).all()

        return [
            {
                'name': schema.object_name,
                'label': schema.object_name,
                'labelPlural': schema.object_name,
                'custom': schema.object_name.endswith('__c'),
                'fields': schema.fields,
                'recordTypes': schema.record_types
            }
            for schema in schemas
        ]

    def suggest_mappings(
        self,
        db: Session,
        integration_profile_id: int,
        object_name: str
    ) -> List[Dict[str, Any]]:
        """Suggest field mappings based on name similarity"""
        schema = self.get_object_schema(db, integration_profile_id, object_name)
        if not schema:
            return []

        suggestions = []

        for field in schema.get('fields', []):
            field_name_lower = field['name'].lower().replace('_', '')

            for canonical_field, mapping in CANONICAL_MAPPINGS.items():
                all_names = [canonical_field.lower().replace('_', '')]
                all_names.extend([a.lower().replace('_', '') for a in mapping['aliases']])

                # Check for exact match
                if field_name_lower in all_names:
                    suggestions.append({
                        'sourceField': field['name'],
                        'targetEntity': mapping['entity'],
                        'targetField': mapping['field'],
                        'confidence': 0.95,
                        'reason': 'Exact name match'
                    })
                    break

                # Check for partial match
                has_partial = any(
                    field_name_lower in name or name in field_name_lower
                    for name in all_names
                )

                if has_partial:
                    suggestions.append({
                        'sourceField': field['name'],
                        'targetEntity': mapping['entity'],
                        'targetField': mapping['field'],
                        'confidence': 0.7,
                        'reason': 'Partial name match'
                    })
                    break

        # Sort by confidence
        suggestions.sort(key=lambda x: x['confidence'], reverse=True)
        return suggestions

    async def refresh_schema(self, db: Session, integration_profile_id: int):
        """Refresh schema (re-discover)"""
        # Log refresh start event
        event = IntegrationEvent(
            integration_profile_id=integration_profile_id,
            event_type='schema_refresh_started',
            status='success'
        )
        db.add(event)
        db.commit()

        await self.discover_schema(db, integration_profile_id)


# Export singleton instance
salesforce_schema = SalesforceSchemaService()
