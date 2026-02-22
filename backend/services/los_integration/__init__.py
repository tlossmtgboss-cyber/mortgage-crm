"""
LOS (Loan Origination System) Integration Package

Provides bidirectional integration with Encompass (ICE Mortgage Technology)
and an extensible framework for other LOS platforms.

Enterprise Readiness: Domain 7 (Integration Health)
- Check 7.1: LOS Integration Framework
- Check 7.2: Bidirectional LOS Sync
- Check 7.4: LOS Error Handling
- Check 7.6: LOS Webhook Receiver

Usage:
    from services.los_integration import EncompassClient, LOSSyncService

    client = EncompassClient(
        instance_id="BE11200822",
        client_id="xxx",
        client_secret="yyy",
    )
    await client.authenticate()
    loan = await client.get_loan("loan-guid")
"""

from .base import BaseLOSClient, LOSConfig, LOSSyncStatus, LOSFieldMapping
from .encompass_client import EncompassClient
from .sync_service import LOSSyncService
from .error_handler import LOSErrorHandler, LOSCircuitBreaker, LOSError, LOSRetryableError
from .encompass_oauth_service import EncompassOAuthService

__all__ = [
    "BaseLOSClient",
    "LOSConfig",
    "LOSSyncStatus",
    "LOSFieldMapping",
    "EncompassClient",
    "LOSSyncService",
    "LOSErrorHandler",
    "LOSCircuitBreaker",
    "LOSError",
    "LOSRetryableError",
    "EncompassOAuthService",
]
