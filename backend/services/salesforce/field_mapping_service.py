"""
Field Mapping Service
Manages how each user's Salesforce fields map to CRM canonical model
"""
import re
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum

from sqlalchemy.orm import Session

from salesforce_integration_models import (
    IntegrationProfile,
    FieldMapping,
    SfUserSchema,
    IntegrationEvent
)
from .schema_service import salesforce_schema

logger = logging.getLogger(__name__)


class TransformType(str, Enum):
    DIRECT = 'direct'                    # No transformation, direct copy
    PICKLIST_MAP = 'picklist_map'        # Map picklist values to canonical values
    STAGE_MAP = 'stage_map'              # Map stage/status values to CRM stages
    DATE_FORMAT = 'date_format'          # Transform date formats
    CURRENCY_CONVERT = 'currency_convert' # Currency conversion
    PHONE_FORMAT = 'phone_format'        # Phone number formatting
    NAME_CONCAT = 'name_concat'          # Concatenate multiple fields
    NAME_SPLIT = 'name_split'            # Split full name into first/last
    CUSTOM_FUNCTION = 'custom_function'  # Custom transformation


class SyncDirection(str, Enum):
    INBOUND = 'inbound'
    OUTBOUND = 'outbound'
    BIDIRECTIONAL = 'bidirectional'


# Type compatibility matrix
TYPE_COMPATIBILITY = {
    'string': ['string', 'textarea', 'email', 'phone', 'url'],
    'textarea': ['string', 'textarea'],
    'email': ['string', 'email'],
    'phone': ['string', 'phone'],
    'double': ['number', 'double', 'currency', 'percent'],
    'currency': ['number', 'double', 'currency'],
    'int': ['number', 'int', 'double'],
    'boolean': ['boolean'],
    'date': ['date', 'datetime'],
    'datetime': ['datetime'],
    'picklist': ['string', 'picklist'],
    'multipicklist': ['array', 'multipicklist']
}


# Default stage mappings
DEFAULT_STAGE_MAPPINGS = {
    'New Lead': 'LEAD',
    'Contacted': 'LEAD',
    'Qualified': 'QUALIFIED',
    'Application': 'APPLICATION',
    'Submitted': 'SUBMITTED',
    'Processing': 'PROCESSING',
    'Underwriting': 'UNDERWRITING',
    'Approved': 'APPROVED',
    'Closing': 'CLOSING',
    'Funded': 'FUNDED',
    'Lost': 'LOST',
    'Closed Won': 'FUNDED',
    'Closed Lost': 'LOST'
}


class FieldMappingService:
    """Manages field mappings between Salesforce and CRM"""

    def create_mapping(
        self,
        db: Session,
        integration_profile_id: int,
        source_object: str,
        source_field: str,
        target_entity: str,
        target_field: str,
        transform_type: str = 'direct',
        transform_config: Optional[Dict] = None,
        data_type: Optional[str] = None,
        required: bool = False,
        default_value: Optional[str] = None,
        sync_direction: str = 'bidirectional',
        enabled: bool = True
    ) -> FieldMapping:
        """Create a new field mapping"""
        # Build mapping data
        mapping_data = {
            'integration_profile_id': integration_profile_id,
            'source_object': source_object,
            'source_field': source_field,
            'target_entity': target_entity,
            'target_field': target_field,
            'transform_type': transform_type,
            'transform_config': transform_config or {},
            'data_type': data_type,
            'required': required,
            'default_value': default_value,
            'sync_direction': sync_direction,
            'enabled': enabled
        }

        # Validate the mapping
        validation = self._validate_mapping(db, mapping_data)

        mapping = FieldMapping(
            **mapping_data,
            validation_status='valid' if validation['is_valid'] else 'invalid',
            validation_message='; '.join(validation['errors'] + validation['warnings']) or None
        )
        db.add(mapping)
        db.commit()
        db.refresh(mapping)

        return mapping

    def update_mapping(
        self,
        db: Session,
        mapping_id: int,
        **updates
    ) -> FieldMapping:
        """Update an existing field mapping"""
        mapping = db.query(FieldMapping).filter(FieldMapping.id == mapping_id).first()

        if not mapping:
            raise ValueError("Field mapping not found")

        # Apply updates
        for key, value in updates.items():
            if hasattr(mapping, key):
                setattr(mapping, key, value)

        # Re-validate
        mapping_data = {
            'integration_profile_id': mapping.integration_profile_id,
            'source_object': mapping.source_object,
            'source_field': mapping.source_field,
            'target_entity': mapping.target_entity,
            'target_field': mapping.target_field,
            'transform_type': mapping.transform_type,
            'transform_config': mapping.transform_config,
            'data_type': mapping.data_type,
            'required': mapping.required,
            'default_value': mapping.default_value
        }

        validation = self._validate_mapping(db, mapping_data)
        mapping.validation_status = 'valid' if validation['is_valid'] else 'invalid'
        mapping.validation_message = '; '.join(validation['errors'] + validation['warnings']) or None

        db.commit()
        db.refresh(mapping)
        return mapping

    def delete_mapping(self, db: Session, mapping_id: int):
        """Delete a field mapping"""
        mapping = db.query(FieldMapping).filter(FieldMapping.id == mapping_id).first()
        if mapping:
            db.delete(mapping)
            db.commit()

    def get_mappings(
        self,
        db: Session,
        integration_profile_id: int,
        source_object: Optional[str] = None,
        target_entity: Optional[str] = None,
        enabled: Optional[bool] = None
    ) -> List[FieldMapping]:
        """Get all mappings for an integration profile"""
        query = db.query(FieldMapping).filter(
            FieldMapping.integration_profile_id == integration_profile_id
        )

        if source_object:
            query = query.filter(FieldMapping.source_object == source_object)
        if target_entity:
            query = query.filter(FieldMapping.target_entity == target_entity)
        if enabled is not None:
            query = query.filter(FieldMapping.enabled == enabled)

        return query.order_by(FieldMapping.source_object, FieldMapping.source_field).all()

    def create_from_suggestions(
        self,
        db: Session,
        integration_profile_id: int,
        source_object: str,
        accepted_suggestions: List[Dict[str, str]]
    ) -> List[FieldMapping]:
        """Bulk create mappings from suggestions"""
        schema = salesforce_schema.get_object_schema(db, integration_profile_id, source_object)
        if not schema:
            raise ValueError("Schema not found for object")

        mappings = []
        for suggestion in accepted_suggestions:
            # Find field in schema
            field = next(
                (f for f in schema.get('fields', []) if f['name'] == suggestion['sourceField']),
                None
            )
            if not field:
                raise ValueError(f"Field {suggestion['sourceField']} not found in schema")

            # Determine appropriate transform type
            transform_type = self._determine_transform_type(field, suggestion['targetField'])
            transform_config = self._create_transform_config(field, transform_type)

            mapping = self.create_mapping(
                db=db,
                integration_profile_id=integration_profile_id,
                source_object=source_object,
                source_field=suggestion['sourceField'],
                target_entity=suggestion['targetEntity'],
                target_field=suggestion['targetField'],
                transform_type=transform_type,
                transform_config=transform_config,
                data_type=field.get('type'),
                required=field.get('required', False),
                sync_direction='bidirectional',
                enabled=True
            )
            mappings.append(mapping)

        return mappings

    def _determine_transform_type(self, field: Dict, target_field: str) -> str:
        """Determine appropriate transform type based on field characteristics"""
        # Stage/Status fields need mapping
        if target_field == 'stage' or 'status' in field.get('name', '').lower():
            return TransformType.STAGE_MAP.value

        # Picklist fields need value mapping
        if field.get('type') == 'picklist' and field.get('picklistValues'):
            return TransformType.PICKLIST_MAP.value

        # Date fields might need formatting
        if field.get('type') in ('date', 'datetime'):
            return TransformType.DATE_FORMAT.value

        # Currency fields
        if field.get('type') == 'currency':
            return TransformType.CURRENCY_CONVERT.value

        # Phone fields
        if field.get('type') == 'phone' or 'phone' in field.get('name', '').lower():
            return TransformType.PHONE_FORMAT.value

        # Default to direct mapping
        return TransformType.DIRECT.value

    def _create_transform_config(self, field: Dict, transform_type: str) -> Dict:
        """Create default transform configuration"""
        if transform_type == TransformType.STAGE_MAP.value:
            return {
                'mappings': DEFAULT_STAGE_MAPPINGS,
                'default': 'LEAD'
            }

        elif transform_type == TransformType.PICKLIST_MAP.value:
            # Create 1:1 mapping for picklist values
            mappings = {}
            for pv in field.get('picklistValues', []):
                mappings[pv['value']] = pv['value']  # User will customize
            return {'mappings': mappings}

        elif transform_type == TransformType.DATE_FORMAT.value:
            return {
                'inputFormat': 'salesforce',
                'outputFormat': 'iso8601',
                'timezone': 'America/New_York'
            }

        elif transform_type == TransformType.CURRENCY_CONVERT.value:
            return {
                'fromCurrency': 'USD',
                'toCurrency': 'USD',
                'decimalPlaces': 2
            }

        elif transform_type == TransformType.PHONE_FORMAT.value:
            return {
                'format': 'national',
                'defaultCountry': 'US'
            }

        return {}

    def _validate_mapping(self, db: Session, mapping: Dict) -> Dict[str, Any]:
        """Validate a field mapping"""
        errors = []
        warnings = []

        # Required field validations
        if not mapping.get('source_object'):
            errors.append("Source object is required")
        if not mapping.get('source_field'):
            errors.append("Source field is required")
        if not mapping.get('target_entity'):
            errors.append("Target entity is required")
        if not mapping.get('target_field'):
            errors.append("Target field is required")
        if not mapping.get('transform_type'):
            errors.append("Transform type is required")

        # Get source field schema to validate
        if (mapping.get('integration_profile_id') and
            mapping.get('source_object') and
            mapping.get('source_field')):

            schema = salesforce_schema.get_object_schema(
                db,
                mapping['integration_profile_id'],
                mapping['source_object']
            )

            if schema:
                field = next(
                    (f for f in schema.get('fields', []) if f['name'] == mapping['source_field']),
                    None
                )

                if not field:
                    errors.append(f"Field {mapping['source_field']} not found in {mapping['source_object']}")
                else:
                    # Type compatibility checks
                    if mapping.get('transform_type') == 'direct' and mapping.get('data_type'):
                        compatible_types = TYPE_COMPATIBILITY.get(field.get('type'), [])
                        if mapping['data_type'] not in compatible_types and field.get('type') not in compatible_types:
                            errors.append(f"Type mismatch: {field.get('type')} cannot be directly mapped to {mapping['data_type']}")

                    # Validate transform config
                    if mapping.get('transform_type') in ('stage_map', 'picklist_map'):
                        if not mapping.get('transform_config', {}).get('mappings'):
                            warnings.append("Transform configuration is incomplete - using defaults")

        # Validate required field logic
        if mapping.get('required') and not mapping.get('default_value') and mapping.get('transform_type') != 'direct':
            warnings.append("Required field without default value may cause sync failures if source is null")

        return {
            'is_valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings
        }

    def get_mapping_stats(
        self,
        db: Session,
        integration_profile_id: int
    ) -> Dict[str, Any]:
        """Get mapping statistics for a user"""
        mappings = self.get_mappings(db, integration_profile_id)

        stats = {
            'total': len(mappings),
            'by_status': {},
            'by_object': {},
            'by_entity': {},
            'required_mapped': 0,
            'required_total': 0,
            'ready_to_activate': False
        }

        for mapping in mappings:
            # By status
            status = mapping.validation_status or 'pending'
            stats['by_status'][status] = stats['by_status'].get(status, 0) + 1

            # By object
            obj = mapping.source_object
            stats['by_object'][obj] = stats['by_object'].get(obj, 0) + 1

            # By entity
            entity = mapping.target_entity
            stats['by_entity'][entity] = stats['by_entity'].get(entity, 0) + 1

            # Required fields
            if mapping.required:
                stats['required_total'] += 1
                if mapping.validation_status == 'valid':
                    stats['required_mapped'] += 1

        # Check if ready to activate
        stats['ready_to_activate'] = (
            stats['required_mapped'] == stats['required_total'] and
            stats['required_total'] > 0 and
            stats['by_status'].get('invalid', 0) == 0
        )

        return stats

    def activate_integration(self, db: Session, integration_profile_id: int):
        """Activate integration (mark as ready for syncing)"""
        stats = self.get_mapping_stats(db, integration_profile_id)

        if not stats['ready_to_activate']:
            raise ValueError(
                f"Cannot activate: {stats['required_total'] - stats['required_mapped']} required fields unmapped, "
                f"{stats['by_status'].get('invalid', 0)} invalid mappings"
            )

        profile = db.query(IntegrationProfile).filter(
            IntegrationProfile.id == integration_profile_id
        ).first()

        profile.status = 'active'
        profile.sync_enabled = True

        # Log activation event
        event = IntegrationEvent(
            integration_profile_id=integration_profile_id,
            event_type='integration_activated',
            status='success',
            event_data={
                'total_mappings': stats['total'],
                'required_mappings': stats['required_total']
            }
        )
        db.add(event)
        db.commit()

    def test_mapping(
        self,
        db: Session,
        mapping_id: int,
        test_value: Any
    ) -> Dict[str, Any]:
        """Test a field mapping transformation"""
        mapping = db.query(FieldMapping).filter(FieldMapping.id == mapping_id).first()

        if not mapping:
            raise ValueError("Mapping not found")

        try:
            transformed = self.transform_value(
                test_value,
                mapping.transform_type,
                mapping.transform_config
            )
            return {
                'success': True,
                'transformed_value': transformed
            }
        except Exception as e:
            return {
                'success': False,
                'transformed_value': None,
                'error': str(e)
            }

    def transform_value(
        self,
        value: Any,
        transform_type: str,
        config: Optional[Dict]
    ) -> Any:
        """Transform a value based on mapping configuration"""
        if value is None:
            return config.get('default') if config else None

        if transform_type == TransformType.DIRECT.value:
            return value

        elif transform_type in (TransformType.STAGE_MAP.value, TransformType.PICKLIST_MAP.value):
            mappings = config.get('mappings', {}) if config else {}
            return mappings.get(value, config.get('default', value) if config else value)

        elif transform_type == TransformType.DATE_FORMAT.value:
            # Parse and format date
            try:
                if isinstance(value, str):
                    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
                else:
                    dt = value

                output_format = config.get('outputFormat', 'iso8601') if config else 'iso8601'
                if output_format == 'iso8601':
                    return dt.isoformat()
                return dt.strftime('%Y-%m-%d')
            except Exception as e:
                logger.exception(f"Failed to format date value '{value}': {e}")
                return value

        elif transform_type == TransformType.CURRENCY_CONVERT.value:
            try:
                num_value = float(value)
                decimal_places = config.get('decimalPlaces', 2) if config else 2
                return round(num_value, decimal_places)
            except Exception as e:
                logger.exception(f"Failed to convert currency value '{value}': {e}")
                return value

        elif transform_type == TransformType.PHONE_FORMAT.value:
            # Simple phone formatting
            cleaned = re.sub(r'\D', '', str(value))
            if len(cleaned) == 10:
                return f"({cleaned[:3]}) {cleaned[3:6]}-{cleaned[6:]}"
            return value

        return value


# Export singleton instance
field_mapping = FieldMappingService()
