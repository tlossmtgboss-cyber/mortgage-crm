"""
WebSocket Authentication Utilities
Extracts and validates user authentication from WebSocket connections.
"""
import os
import logging
from typing import Optional, Tuple, Any
from dataclasses import dataclass

from fastapi import WebSocket
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)


@dataclass
class AuthenticatedUser:
    """Represents an authenticated user from WebSocket auth."""
    id: int
    email: str
    first_name: str
    last_name: str
    role: Optional[str] = None
    organization_id: Optional[int] = None

    @property
    def is_authenticated(self) -> bool:
        return self.id is not None and self.id > 0

    @property
    def name(self) -> str:
        """Full name for backwards compatibility."""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.first_name or self.last_name or ""


def extract_token_from_websocket(websocket: WebSocket) -> Optional[str]:
    """
    Extract JWT token from WebSocket connection.

    Checks in order:
    1. Query parameter 'token'
    2. Query parameter 'authorization' (lowercase)
    3. Header 'Authorization' with Bearer prefix
    4. Header 'Sec-WebSocket-Protocol' (some clients send token here)

    Returns:
        JWT token string or None if not found
    """
    # Check query params first (most common for mobile WebSocket)
    token = websocket.query_params.get("token")
    if token:
        logger.debug("[WebSocketAuth] Token found in query params")
        return token

    # Check authorization query param
    auth_param = websocket.query_params.get("authorization")
    if auth_param:
        if auth_param.startswith("Bearer "):
            token = auth_param[7:]
        else:
            token = auth_param
        logger.debug("[WebSocketAuth] Token found in authorization query param")
        return token

    # Check Authorization header
    auth_header = websocket.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        logger.debug("[WebSocketAuth] Token found in Authorization header")
        return token

    # Check Sec-WebSocket-Protocol header (used by some WebSocket clients)
    protocol_header = websocket.headers.get("sec-websocket-protocol", "")
    if protocol_header and not protocol_header.startswith("chat"):
        # Some clients pass token as protocol
        logger.debug("[WebSocketAuth] Token found in Sec-WebSocket-Protocol header")
        return protocol_header

    return None


def decode_jwt_token(token: str) -> Optional[dict]:
    """
    Decode and validate a JWT token.

    Returns:
        Decoded payload dict or None if invalid
    """
    try:
        from auth.tokens import verify_access_token

        payload = verify_access_token(token)
        if not payload:
            logger.warning("[WebSocketAuth] Token invalid, expired, or revoked")
            return None

        return payload

    except Exception as e:
        logger.error(f"[WebSocketAuth] Token decode error: {e}")
        return None


def lookup_user_by_email(db: Session, email: str) -> Optional[AuthenticatedUser]:
    """
    Look up user in database by email.

    Returns:
        AuthenticatedUser or None if not found
    """
    try:
        result = db.execute(
            text("""
                SELECT id, email, first_name, last_name, role, organization_id
                FROM users
                WHERE email = :email
                LIMIT 1
            """),
            {"email": email}
        )
        row = result.fetchone()

        if row:
            return AuthenticatedUser(
                id=row[0],
                email=row[1],
                first_name=row[2] or email.split("@")[0],
                last_name=row[3] or "",
                role=row[4],
                organization_id=row[5]
            )

        logger.warning(f"[WebSocketAuth] User not found for email: {email}")
        return None

    except Exception as e:
        logger.error(f"[WebSocketAuth] Database lookup error: {e}")
        return None


def lookup_user_by_id(db: Session, user_id: int) -> Optional[AuthenticatedUser]:
    """
    Look up user in database by ID.

    Returns:
        AuthenticatedUser or None if not found
    """
    try:
        result = db.execute(
            text("""
                SELECT id, email, first_name, last_name, role, organization_id
                FROM users
                WHERE id = :user_id
                LIMIT 1
            """),
            {"user_id": user_id}
        )
        row = result.fetchone()

        if row:
            return AuthenticatedUser(
                id=row[0],
                email=row[1],
                first_name=row[2] or row[1].split("@")[0],
                last_name=row[3] or "",
                role=row[4],
                organization_id=row[5]
            )

        logger.warning(f"[WebSocketAuth] User not found for ID: {user_id}")
        return None

    except Exception as e:
        logger.error(f"[WebSocketAuth] Database lookup error: {e}")
        return None


def authenticate_websocket(
    websocket: WebSocket,
    db: Session,
    require_auth: bool = True
) -> Tuple[Optional[AuthenticatedUser], Optional[str]]:
    """
    Authenticate a WebSocket connection.

    This is the main function to use for WebSocket authentication.

    Args:
        websocket: FastAPI WebSocket connection
        db: SQLAlchemy database session
        require_auth: Kept for backwards compatibility (always requires auth)

    Returns:
        Tuple of (AuthenticatedUser or None, error_message or None)
    """
    # Extract token
    token = extract_token_from_websocket(websocket)

    if not token:
        return None, "No authentication token provided"

    # Decode token
    payload = decode_jwt_token(token)
    if not payload:
        return None, "Invalid authentication token"

    # Extract user identifier from payload
    # JWT may contain user_id (int) or sub (email)
    user_id = payload.get("user_id")
    email = payload.get("sub")

    user = None

    # Try user_id first if it's a valid integer
    if user_id:
        try:
            user_id_int = int(user_id)
            user = lookup_user_by_id(db, user_id_int)
        except (ValueError, TypeError):
            pass

    # Fall back to email lookup
    if not user and email:
        user = lookup_user_by_email(db, email)

    if not user:
        return None, "User not found"

    logger.info(f"[WebSocketAuth] Authenticated user ID: {user.id}")
    return user, None


def get_user_id_from_websocket(websocket: WebSocket, db: Session) -> Optional[str]:
    """
    Simple helper to get user email from WebSocket.
    For backwards compatibility with existing code that expects email string.

    Returns:
        User email string or None if not authenticated
    """
    user, _ = authenticate_websocket(websocket, db)
    if user:
        return user.email
    return None


def get_authenticated_user_or_raise(websocket: WebSocket, db: Session) -> AuthenticatedUser:
    """
    Get authenticated user or raise an exception.
    Use this when authentication is required.

    Raises:
        ValueError: If authentication fails
    """
    user, error = authenticate_websocket(websocket, db, require_auth=True)
    if not user:
        raise ValueError(error or "Authentication required")
    return user
