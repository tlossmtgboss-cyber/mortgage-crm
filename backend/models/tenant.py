"""
Tenant Model
Stores tenant registry information in the master database.
Each tenant gets their own separate database.
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, JSON
from datetime import datetime, timezone
from database import Base


class Tenant(Base):
    """
    Tenant registry stored in master database.
    Each tenant has their own separate PostgreSQL database.
    """
    __tablename__ = "tenants"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Tenant identification
    tenant_id = Column(String(100), unique=True, nullable=False, index=True)
    organization_name = Column(String(255), nullable=False)
    subdomain = Column(String(100), unique=True, nullable=True, index=True)  # e.g., 'acme' for acme.yourdomain.com
    
    # Database information
    database_name = Column(String(100), unique=True, nullable=False)  # PostgreSQL database name
    database_url = Column(Text, nullable=False)  # Full connection string to tenant database
    
    # Tenant status
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    is_provisioned = Column(Boolean, default=False, nullable=False)  # Whether DB has been created
    
    # Contact information
    owner_email = Column(String(255), nullable=True)
    owner_name = Column(String(255), nullable=True)
    
    # Subscription/billing info (optional)
    plan_type = Column(String(50), default="free")  # free, starter, professional, enterprise
    max_users = Column(Integer, default=5)
    max_storage_gb = Column(Integer, default=10)
    
    # Configuration
    settings = Column(JSON, default=dict)  # Custom tenant settings
    
    # Metadata
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    provisioned_at = Column(DateTime, nullable=True)  # When database was created
    last_accessed = Column(DateTime, nullable=True)  # Last time tenant was accessed
    
    # Soft delete
    deleted_at = Column(DateTime, nullable=True)
    
    def __repr__(self):
        return f"<Tenant {self.tenant_id} - {self.organization_name}>"
    
    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None
    
    def to_dict(self):
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "organization_name": self.organization_name,
            "subdomain": self.subdomain,
            "database_name": self.database_name,
            "is_active": self.is_active,
            "is_provisioned": self.is_provisioned,
            "plan_type": self.plan_type,
            "max_users": self.max_users,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_accessed": self.last_accessed.isoformat() if self.last_accessed else None,
        }
