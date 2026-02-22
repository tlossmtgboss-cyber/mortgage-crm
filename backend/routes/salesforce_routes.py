"""
Salesforce Integration Routes (Legacy)
OAuth authentication, webhook handling, and sync endpoints

DEPRECATION NOTICE:
This module is being phased out in favor of salesforce_integration_routes.py which provides:
- Per-user OAuth with PKCE
- Schema discovery and field mapping
- Email and calendar sync
- Bidirectional sync support

New endpoints are available at /api/integrations/salesforce/*
These legacy endpoints at /api/v1/salesforce/* will be maintained for backwards compatibility.

DECOMPOSITION NOTE:
This file is a thin router that includes sub-routers from:
- salesforce_auth_routes.py  -- OAuth flow: connect/callback/disconnect/status
- salesforce_sync_routes.py  -- Sync operations, webhook, history, sync-all-loans
- salesforce_mapping_routes.py -- Field mapping + schema exploration
- salesforce_data_routes.py  -- Import/export, push/pull, MUM endpoints
- salesforce_debug_routes.py -- Debug/diagnostic endpoints

Shared code lives in:
- salesforce_models.py   -- Pydantic schemas + constants
- salesforce_helpers.py  -- SQL building, validation, refresh logic
"""
from fastapi import APIRouter

from .salesforce_auth_routes import router as auth_router
from .salesforce_sync_routes import router as sync_router
from .salesforce_mapping_routes import router as mapping_router
from .salesforce_data_routes import router as data_router
from .salesforce_debug_routes import router as debug_router

router = APIRouter()

# Include all sub-routers (no prefix -- the parent prefix /api/v1/salesforce
# is applied by inline_legacy_routes.py when including this router)
router.include_router(auth_router)
router.include_router(sync_router)
router.include_router(mapping_router)
router.include_router(data_router)
router.include_router(debug_router)
