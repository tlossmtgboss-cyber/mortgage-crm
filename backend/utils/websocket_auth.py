"""
WebSocket Authentication Utilities
Extracts and validates user authentication from WebSocket connections.

Security: Prefer authenticate_websocket_post_connect() over authenticate_websocket()
for new code. The post-connect variant reads the JWT from the first WebSocket message
instead of the URL query string, which avoids leaking tokens into server access logs,
proxy logs, and browser history.
"""
import asyncio
import json
import os
import logging
from typing import Optional, Tuple, Any
from dataclasses import dataclass

from fastapi import WebSocket
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Timeout (seconds) for the client to send the auth message after connect
WS_AUTH_TIMEOUT = 5.0


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
    Uses ORM query to properly decrypt EncryptedString columns (first_name, last_name).

    Returns:
        AuthenticatedUser or None if not found
    """
    try:
        from database.models import User
        user = db.query(User).filter(User.email == email).first()

        if user:
            return AuthenticatedUser(
                id=user.id,
                email=user.email,
                first_name=user.first_name or email.split("@")[0],
                last_name=user.last_name or "",
                role=user.role,
                organization_id=getattr(user, "organization_id", None)
            )

        logger.warning(f"[WebSocketAuth] User not found for email: {email}")
        return None

    except Exception as e:
        logger.error(f"[WebSocketAuth] Database lookup error: {e}")
        return None


def lookup_user_by_id(db: Session, user_id: int) -> Optional[AuthenticatedUser]:
    """
    Look up user in database by ID.
    Uses ORM query to properly decrypt EncryptedString columns (first_name, last_name).

    Returns:
        AuthenticatedUser or None if not found
    """
    try:
        from database.models import User
        user = db.query(User).filter(User.id == user_id).first()

        if user:
            return AuthenticatedUser(
                id=user.id,
                email=user.email,
                first_name=user.first_name or user.email.split("@")[0],
                last_name=user.last_name or "",
                role=user.role,
                organization_id=getattr(user, "organization_id", None)
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


async def authenticate_websocket_post_connect(
    websocket: WebSocket,
    db: Session,
    timeout: float = WS_AUTH_TIMEOUT,
) -> Tuple[Optional[AuthenticatedUser], Optional[str]]:
    """
    Authenticate a WebSocket connection using a post-connect auth message.

    Security: This avoids putting the JWT in the URL query string, which would
    leak it into server access logs, proxy logs, and browser history.

    Protocol:
    1. Server accepts the WebSocket connection (caller must do this first)
    2. Client sends a JSON message: {"type": "auth", "token": "<JWT>"}
    3. Server validates the token and looks up the user

    Also supports backwards compatibility: if the URL still contains a ?token=
    query param (e.g. from older clients), it will be used as a fallback. This
    allows a rolling upgrade where old frontend builds still work.

    Args:
        websocket: Already-accepted FastAPI WebSocket connection
        db: SQLAlchemy database session
        timeout: Seconds to wait for the auth message (default 5s)

    Returns:
        Tuple of (AuthenticatedUser or None, error_message or None)
    """
    # Backwards compat: check query params first for old clients
    token = websocket.query_params.get("token")

    if not token:
        # Wait for the first message to carry the auth token
        try:
            raw = await asyncio.wait_for(websocket.receive_text(), timeout=timeout)
        except asyncio.TimeoutError:
            return None, "Authentication timeout — no auth message received"
        except Exception as e:
            logger.warning(f"[WebSocketAuth] Error receiving auth message: {e}")
            return None, "Connection error during authentication"

        try:
            msg = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None, "Invalid auth message format (expected JSON)"

        if not isinstance(msg, dict) or msg.get("type") != "auth":
            return None, "First message must be {\"type\": \"auth\", \"token\": \"...\"}"

        token = msg.get("token")
        if not token or not isinstance(token, str):
            return None, "Auth message missing 'token' field"

    # Decode and validate token
    payload = decode_jwt_token(token)
    if not payload:
        return None, "Invalid authentication token"

    # Look up user
    user_id = payload.get("user_id")
    email = payload.get("sub")
    user = None

    if user_id:
        try:
            user = lookup_user_by_id(db, int(user_id))
        except (ValueError, TypeError):
            pass

    if not user and email:
        user = lookup_user_by_email(db, email)

    if not user:
        return None, "User not found"

    logger.info(f"[WebSocketAuth] Post-connect authenticated user ID: {user.id}")
    return user, None
