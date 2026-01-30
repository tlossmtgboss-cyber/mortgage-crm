#!/usr/bin/env python3
"""
Setup Script for Tim Loss Tenant Database

This script creates a dedicated tenant database for Tim Loss (tloss@cmgfi.com)
with isolated data storage in the multi-tenant system.

Usage:
    python setup_tim_loss_tenant.py

Requirements:
    - MASTER_DATABASE_URL environment variable configured
    - DATABASE_SERVER_URL environment variable configured
    - PostgreSQL server access with CREATE DATABASE permissions
"""

import asyncio
import sys
import os
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Tim Loss tenant configuration
TIM_LOSS_TENANT = {
    "organization_name": "Tim Loss - CMG Financial",
    "subdomain": "timloss",
    "admin_email": "tloss@cmgfi.com",
    "database_name": "mortgage_crm_timloss"
}


async def setup_tim_loss_tenant():
    """
    Set up Tim Loss as a tenant in the multi-tenant system.
    """
    try:
        logger.info("="*60)
        logger.info("Starting Tim Loss Tenant Setup")
        logger.info("="*60)
        
        # Import after path is set
        from tenant_database_manager import tenant_db_manager
        from services.tenant_provisioning_service import tenant_provisioning_service
        from models.tenant import Tenant, Base
        
        # Get environment variables
        master_db_url = os.getenv('MASTER_DATABASE_URL')
        db_server_url = os.getenv('DATABASE_SERVER_URL')
        
        if not master_db_url:
            logger.error("MASTER_DATABASE_URL environment variable not set!")
            logger.info("Please set: export MASTER_DATABASE_URL='postgresql://user:pass@host:5432/master_db'")
            return False
        
        if not db_server_url:
            logger.error("DATABASE_SERVER_URL environment variable not set!")
            logger.info("Please set: export DATABASE_SERVER_URL='postgresql://user:pass@host:5432/postgres'")
            return False
        
        logger.info(f"Master DB URL: {master_db_url.split('@')[1] if '@' in master_db_url else 'configured'}")
        logger.info(f"DB Server URL: {db_server_url.split('@')[1] if '@' in db_server_url else 'configured'}")
        
        # Create master database engine and session
        logger.info("\n" + "="*60)
        logger.info("Step 1: Connecting to Master Database")
        logger.info("="*60)
        
        master_engine = create_engine(master_db_url)
        SessionLocal = sessionmaker(bind=master_engine)
        master_session = SessionLocal()
        
        # Create tenants table if it doesn't exist
        logger.info("Creating tenants table in master database...")
        Base.metadata.create_all(master_engine)
        logger.info("✓ Tenants table ready")
        
        # Check if Tim Loss tenant already exists
        logger.info("\n" + "="*60)
        logger.info("Step 2: Checking for Existing Tenant")
        logger.info("="*60)
        
        existing_tenant = master_session.query(Tenant).filter(
            (Tenant.subdomain == TIM_LOSS_TENANT["subdomain"]) |
            (Tenant.admin_email == TIM_LOSS_TENANT["admin_email"])
        ).first()
        
        if existing_tenant:
            logger.warning(f"\n⚠️  Tenant already exists!")
            logger.info(f"   Organization: {existing_tenant.organization_name}")
            logger.info(f"   Subdomain: {existing_tenant.subdomain}")
            logger.info(f"   Database: {existing_tenant.database_name}")
            logger.info(f"   Status: {'Active' if existing_tenant.is_active else 'Inactive'}")
            logger.info(f"   Created: {existing_tenant.created_at}")
            
            response = input("\nTenant exists. Do you want to recreate it? (yes/no): ")
            if response.lower() not in ['yes', 'y']:
                logger.info("Setup cancelled.")
                master_session.close()
                return True
            
            # Delete existing tenant
            logger.info("\nDeleting existing tenant...")
            success = await tenant_provisioning_service.delete_tenant(
                tenant_id=existing_tenant.id,
                master_db_session=master_session
            )
            if not success:
                logger.error("Failed to delete existing tenant")
                master_session.close()
                return False
            logger.info("✓ Existing tenant deleted")
        
        # Create new tenant for Tim Loss
        logger.info("\n" + "="*60)
        logger.info("Step 3: Creating Tim Loss Tenant")
        logger.info("="*60)
        logger.info(f"Organization: {TIM_LOSS_TENANT['organization_name']}")
        logger.info(f"Subdomain: {TIM_LOSS_TENANT['subdomain']}")
        logger.info(f"Admin Email: {TIM_LOSS_TENANT['admin_email']}")
        logger.info(f"Database: {TIM_LOSS_TENANT['database_name']}")
        
        tenant = await tenant_provisioning_service.create_tenant(
            organization_name=TIM_LOSS_TENANT["organization_name"],
            subdomain=TIM_LOSS_TENANT["subdomain"],
            master_db_session=master_session
        )
        
        if not tenant:
            logger.error("❌ Failed to create tenant!")
            logger.error("Check the logs above for errors.")
            master_session.close()
            return False
        
        logger.info("\n" + "="*60)
        logger.info("✅ SUCCESS - Tim Loss Tenant Created!")
        logger.info("="*60)
        logger.info(f"Tenant ID: {tenant.id}")
        logger.info(f"Organization: {tenant.organization_name}")
        logger.info(f"Subdomain: {tenant.subdomain}")
        logger.info(f"Database: {tenant.database_name}")
        logger.info(f"Status: {'Active' if tenant.is_active else 'Inactive'}")
        logger.info(f"Created: {tenant.created_at}")
        
        # Access instructions
        logger.info("\n" + "="*60)
        logger.info("Access Instructions")
        logger.info("="*60)
        logger.info(f"Via Subdomain: https://{tenant.subdomain}.yourdomain.com")
        logger.info(f"Via Header: X-Tenant-ID: {tenant.subdomain}")
        logger.info(f"Via API: /api/tenants/{tenant.id}")
        
        logger.info("\n" + "="*60)
        logger.info("Next Steps")
        logger.info("="*60)
        logger.info("1. Configure your DNS to point the subdomain to your app")
        logger.info("2. Ensure TenantMiddleware is enabled in your FastAPI app")
        logger.info("3. Tim Loss can now access his isolated database")
        logger.info("4. All data for tloss@cmgfi.com will be stored in: " + tenant.database_name)
        
        master_session.close()
        return True
        
    except Exception as e:
        logger.error(f"\n❌ Setup failed with error: {e}")
        logger.exception("Full traceback:")
        return False


if __name__ == "__main__":
    logger.info("Tim Loss Tenant Setup Script")
    logger.info("This will create an isolated database for Tim Loss (tloss@cmgfi.com)\n")
    
    # Run setup
    success = asyncio.run(setup_tim_loss_tenant())
    
    if success:
        logger.info("\n✅ Setup completed successfully!")
        sys.exit(0)
    else:
        logger.error("\n❌ Setup failed. Please check the errors above.")
        sys.exit(1)
