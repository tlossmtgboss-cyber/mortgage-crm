"""
Tenant Provisioning Service
Handles creation, deletion, and management of tenant databases.
"""

import uuid
import logging
import re
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from tenant_database_manager import tenant_db_manager
from models.tenant import Tenant

logger = logging.getLogger(__name__)


class TenantProvisioningService:
    """
    Service for provisioning and managing tenant databases.
    """

    def __init__(self, db_manager = tenant_db_manager):
        self.db_manager = db_manager

    def _sanitize_database_name(self, name: str) -> str:
        """
        Convert name to PostgreSQL-safe database name.
        
        Args:
            name: Organization name or identifier
        
        Returns:
            Sanitized database name
        """
        # Remove special characters, convert to lowercase
        sanitized = re.sub(r'[^a-z0-9_]', '_', name.lower())
        # Ensure it starts with a letter
        if not sanitized[0].isalpha():
            sanitized = '@b_' + sanitized
        # Limit length
        return sanitized[:60]

    def _validate_subdomain(self, subdomain: str) -> bool:
        """
        Validate subdomain format.
        
        Args:
            subdomain: Subdomain to validate
        
        Returns:
            True if valid, False otherwise
        """
        # Must be 3-63 characters, alphanumeric and hyphens, start/end with alphanumeric
        pattern = r'^[a-z0-9]([a-z0-9-]{1,61}[a-z0-9])?$'
        return bool(re.match(pattern, subdomain.lower()))

    async def create_tenant(self,
        organization_name: str,
        subdomain: str,
        master_db_session
    ) -> Optional[Tenant]:
        """
        Create a new tenant with its own database.
        
        Args:
            organization_name: Name of the organization
            subdomain: Subdomain for tenant access
            master_db_session: SQLAlchemy session for master database
        
        Returns:
            Tenant object if successful, None otherwise
        """
        try:
            # Validate subdomain
            if not self._validate_subdomain(subdomain):
                logger.error(f"Invalid subdomain format: {subdomain}")
                return None
            
            # Check if subdomain already exists
            existing = master_db_session.query(Tenant).filter_by(subdomain=subdomain).first()
            if existing:
                logger.error(f"Subdomain already exists: {subdomain}")
                return None
            
            # Create database name
            db_name = self._sanitize_database_name(organization_name)
            
            # Create physical database
            success = await self.db_manager.create_tenant_database(db_name)
            if not success:
                logger.error(f"Failed to create database for tenant: {db_name}")
                return None
            
            # Create tenant record
            tenant = Tenant(
                id=str(uuid.uuid4()),
                organization_name=organization_name,
                subdomain=subdomain,
                database_name=db_name,
                is_active=True,
                created_at=datetime.now(timezone.utc)
            )
            
            master_db_session.add(tenant)
            master_db_session.commit()
            
            logger.info(f"Successfully created tenant: {subdomain} with database: {db_name}")
            return tenant
            
        except Exception as e:
            logger.error(f"Error creating tenant: {e}")
            master_db_session.rollback()
            return None

    async def delete_tenant(self, tenant_id: str, master_db_session) -> bool:
        """
        Delete a tenant and its database.
        
        Args:
            tenant_id: UUID of the tenant
            master_db_session: SQLAlchemy session for master database
        
        Returns:
            True if successful, False otherwise
        """
        try:
            tenant = master_db_session.query(Tenant).filter_by(id=tenant_id).first()
            if not tenant:
                logger.error(f"Tenant not found: {tenant_id}")
                return False
            
            # Delete physical database
            success = await self.db_manager.delete_tenant_database(tenant.database_name)
            if not success:
                logger.error(f"Failed to delete database: {tenant.database_name}")
                return False
            
            # Delete tenant record
            master_db_session.delete(tenant)
            master_db_session.commit()
            
            logger.info(f"Successfully deleted tenant: {tenant.subdomain}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting tenant: {e}")
            master_db_session.rollback()
            return False


# Create singleton instance
tenant_provisioning_service = TenantProvisioningService()
