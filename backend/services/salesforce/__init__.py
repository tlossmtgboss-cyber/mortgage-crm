"""
Salesforce Integration Services
Per-user Salesforce OAuth, schema discovery, field mapping, and sync
"""

from .oauth_service import SalesforceOAuthService, salesforce_oauth
from .schema_service import SalesforceSchemaService, salesforce_schema
from .field_mapping_service import FieldMappingService, field_mapping
from .sync_service import SalesforceSyncService, salesforce_sync
from .email_sync_service import SalesforceEmailSyncService, salesforce_email_sync
from .calendar_sync_service import SalesforceCalendarSyncService, salesforce_calendar_sync

__all__ = [
    'SalesforceOAuthService',
    'salesforce_oauth',
    'SalesforceSchemaService',
    'salesforce_schema',
    'FieldMappingService',
    'field_mapping',
    'SalesforceSyncService',
    'salesforce_sync',
    'SalesforceEmailSyncService',
    'salesforce_email_sync',
    'SalesforceCalendarSyncService',
    'salesforce_calendar_sync',
]
