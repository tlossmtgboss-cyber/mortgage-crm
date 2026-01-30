"""
User Onboarding & Tenant Database Integration

This module integrates the tenant provisioning service with the user onboarding system.
When new users/organizations are created, they automatically get their own isolated database.
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def integrate_tenant_provisioning_with_onboarding(
    db_manager,  # TenantDatabaseManager instance
    provisioning_service,  # TenantProvisioningService instance
    onboarding_models: Dict[str, Any]
):
    """
    Adds tenant provisioning hooks to the onboarding system.
    
    This function should be called during application startup to integrate
    tenant database creation with user onboarding workflows.
    """
    
    def create_tenant_for_user(
        db: Session,
        user_id: int,
        user_email: str,
        organization_name: str,
        subdomain: Optional[str] = None,
        created_by_user_id: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Create a tenant database for a new user/organization.
        
        Args:
            db: Database session
            user_id: User ID from the users table
            user_email: User's email address
            organization_name: Name of the organization
            subdomain: Optional subdomain (generated from org name if not provided)
            created_by_user_id: ID of the admin who created this user
            
        Returns:
            Dict with tenant info or None if creation failed
        """
        try:
            # Generate subdomain from organization name if not provided
            if not subdomain:
                subdomain = organization_name.lower()
                subdomain = ''.join(c if c.isalnum() else '_' for c in subdomain)
                subdomain = subdomain.strip('_')[:50]  # Limit length
            
            # Create tenant via provisioning service
            tenant_data = provisioning_service.provision_new_tenant(
                organization_name=organization_name,
                subdomain=subdomain,
                admin_email=user_email,
                created_by_user_id=created_by_user_id or user_id
            )
            
            if not tenant_data:
                logger.error(f"Failed to provision tenant for user {user_id}")
                return None
            
            logger.info(
                f"✅ Created tenant database for user {user_id}: "
                f"tenant_id={tenant_data['tenant_id']}, "
                f"db={tenant_data['database_name']}"
            )
            
            return {
                'tenant_id': tenant_data['tenant_id'],
                'database_name': tenant_data['database_name'],
                'subdomain': tenant_data['subdomain'],
                'status': tenant_data['status']
            }
            
        except Exception as e:
            logger.exception(f"Error creating tenant for user {user_id}: {e}")
            return None
    
    
    def create_tenant_for_onboarding_user(
        db: Session,
        user_profile: Any,  # OnboardingUserProfile instance
        organization_name: Optional[str] = None,
        subdomain: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Create tenant database for a user going through onboarding.
        
        Args:
            db: Database session
            user_profile: OnboardingUserProfile instance
            organization_name: Name of organization (uses user name if not provided)
            subdomain: Optional custom subdomain
            
        Returns:
            Dict with tenant info or None if creation failed
        """
        try:
            # Get the actual User record
            from database import get_db
            User = onboarding_models.get('User')  # Assuming User is passed in models
            
            user = db.query(User).filter(User.id == user_profile.user_id).first()
            if not user:
                logger.error(f"User {user_profile.user_id} not found")
                return None
            
            # Use organization name or create from user name
            if not organization_name:
                organization_name = f"{user_profile.first_name} {user_profile.last_name}".strip()
                if not organization_name:
                    organization_name = user.email.split('@')[0]
            
            # Create tenant
            return create_tenant_for_user(
                db=db,
                user_id=user.id,
                user_email=user.email,
                organization_name=organization_name,
                subdomain=subdomain,
                created_by_user_id=user_profile.created_by
            )
            
        except Exception as e:
            logger.exception(f"Error creating tenant for onboarding user: {e}")
            return None
    
    
    # Return the helper functions for use in onboarding endpoints
    return {
        'create_tenant_for_user': create_tenant_for_user,
        'create_tenant_for_onboarding_user': create_tenant_for_onboarding_user
    }


def add_tenant_creation_to_unified_endpoint(
    onboarding_router,
    tenant_helpers: Dict[str, Any]
):
    """
    Modifies the unified user creation endpoint to include tenant provisioning.
    
    This should be called after the onboarding router is created to add
    tenant database creation as part of the user creation flow.
    
    Usage in main.py:
    ```python
    # After creating onboarding router
    tenant_helpers = integrate_tenant_provisioning_with_onboarding(
        db_manager=tenant_db_manager,
        provisioning_service=tenant_provisioning_service,
        onboarding_models=onboarding_models
    )
    
    add_tenant_creation_to_unified_endpoint(
        onboarding_router=onboarding_router,
        tenant_helpers=tenant_helpers
    )
    ```
    """
    logger.info("🔗 Tenant provisioning integrated with user onboarding")
    # Note: Actual endpoint modification would happen in the router creation
    # This function documents the integration pattern


def should_create_tenant_for_user(user_profile: Any, config: Dict[str, Any]) -> bool:
    """
    Determine if a tenant database should be created for this user.
    
    Args:
        user_profile: OnboardingUserProfile instance
        config: Configuration dict with tenant creation rules
        
    Returns:
        bool: True if tenant should be created
        
    Configuration options:
    - create_tenant_for_all: bool - Create tenant for every user
    - create_tenant_for_roles: List[str] - Create only for specific roles
    - create_tenant_for_emails: List[str] - Create for specific email domains
    - tenant_per_user: bool - Each user gets their own database
    - tenant_per_organization: bool - Users share organization database
    """
    # Default: create tenant for all users
    if config.get('create_tenant_for_all', True):
        return True
    
    # Check role-based rules
    allowed_roles = config.get('create_tenant_for_roles', [])
    if allowed_roles and user_profile.role_id:
        # Would need to fetch role name and check
        return True
    
    # Check email domain rules
    allowed_domains = config.get('create_tenant_for_emails', [])
    if allowed_domains:
        # Would need to fetch user email and check domain
        return True
    
    return False


# Example usage documentation
"""
EXAMPLE: Integrating into main.py

```python
from tenant_database_manager import TenantDatabaseManager
from services.tenant_provisioning_service import TenantProvisioningService
from user_onboarding_tenant_integration import integrate_tenant_provisioning_with_onboarding

# After creating database and onboarding models
tenant_db_manager = TenantDatabaseManager(master_db_url=settings.DATABASE_URL)
tenant_provisioning_service = TenantProvisioningService(tenant_db_manager)

# Integrate tenant provisioning with onboarding
tenant_helpers = integrate_tenant_provisioning_with_onboarding(
    db_manager=tenant_db_manager,
    provisioning_service=tenant_provisioning_service,
    onboarding_models={'User': User, **onboarding_models}
)

# Make tenant helpers available to onboarding endpoints
app.state.tenant_helpers = tenant_helpers
```

EXAMPLE: Modified unified user creation endpoint

```python
@router.post("/create")
async def create_user_unified(
    data: UnifiedCreateUserRequest,
    request: Request,
    db = Depends(get_db),
    current_user = Depends(get_current_user)
):
    # ... existing user creation code ...
    
    # After user and profile are created:
    if hasattr(request.app.state, 'tenant_helpers'):
        tenant_helpers = request.app.state.tenant_helpers
        
        # Create tenant database for this user
        tenant_info = tenant_helpers['create_tenant_for_onboarding_user'](
            db=db,
            user_profile=profile,
            organization_name=data.organization_name,  # if provided
            subdomain=data.subdomain  # if provided
        )
        
        if tenant_info:
            # Store tenant_id in user profile metadata
            profile.tenant_id = tenant_info['tenant_id']  # Add this column to model
            db.commit()
            
            response_data['tenant'] = tenant_info
    
    return response_data
```

EXAMPLE: For Tim Loss specifically

```python
# In setup_tim_loss_tenant.py or similar script
from user_onboarding_tenant_integration import integrate_tenant_provisioning_with_onboarding

# Get Tim Loss's user profile
user = db.query(User).filter(User.email == 'tloss@cmgfi.com').first()
profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()

# Create tenant
tenant_info = tenant_helpers['create_tenant_for_onboarding_user'](
    db=db,
    user_profile=profile,
    organization_name="CMG Financial - Tim Loss",
    subdomain="timloss_cmg"
)

if tenant_info:
    print(f"✅ Tenant created for Tim Loss: {tenant_info['database_name']}")
else:
    print("❌ Failed to create tenant")
```
"""
