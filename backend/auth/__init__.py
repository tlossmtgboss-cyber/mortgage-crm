"""
Authentication Module for Mortgage CRM

This module provides secure authentication and authorization:
- JWT token creation and validation with RS256 asymmetric keys
- Refresh token rotation for security
- Token revocation/blacklist with Redis
- Proper JWT claims (iss, aud, jti, exp, iat)

Usage:
    from auth import create_access_token, verify_token, TokenType

    # Create access token
    token = create_access_token(data={"sub": user.email, "user_id": user.id})

    # Verify token
    token_data = verify_token(token, expected_type=TokenType.ACCESS)
    if token_data:
        print(f"User: {token_data.sub}")

Configuration:
    Set these environment variables:
    - AUTH_ALGORITHM=RS256 (or HS256 for symmetric)
    - AUTH_PRIVATE_KEY or AUTH_PRIVATE_KEY_PATH (for RS256)
    - AUTH_PUBLIC_KEY or AUTH_PUBLIC_KEY_PATH (for RS256)
    - SECRET_KEY (for HS256)
    - AUTH_TOKEN_BLACKLIST_ENABLED=true (optional)
    - REDIS_URL (required if blacklist enabled)
"""

from .tokens import (
    create_access_token,
    create_refresh_token,
    verify_token,
    verify_access_token,
    decode_token,
    get_token_jti,
    is_token_blacklisted,
    token_blacklist,
    TokenType,
    TokenData,
    load_rsa_keys,
    get_signing_key,
    get_verification_key,
)
from .config import AuthSettings, get_auth_settings
from .routes import router as auth_router

__all__ = [
    # Token functions
    'create_access_token',
    'create_refresh_token',
    'verify_token',
    'decode_token',
    'get_token_jti',
    # Token types and data
    'TokenType',
    'TokenData',
    # Blacklist
    'token_blacklist',
    'is_token_blacklisted',
    # Key management
    'load_rsa_keys',
    'get_signing_key',
    'get_verification_key',
    # Config
    'AuthSettings',
    'get_auth_settings',
    # Router
    'auth_router',
]
