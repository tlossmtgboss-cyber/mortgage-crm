"""
Market Chat Routes
Perennia AI - IBMA

API endpoints for team chat on the Market Dashboard.
Enables real-time team communication about market conditions.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import text

from database import get_db, engine

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/market-chat", tags=["Market Chat"])
security = HTTPBearer(auto_error=False)


# ================================================================
# DATABASE TABLE INITIALIZATION
# ================================================================

def ensure_chat_table_exists():
    """Create market_chat_messages table if it doesn't exist."""
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS market_chat_messages (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id),
                    user_name VARCHAR(255),
                    message TEXT NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_chat_created_at
                ON market_chat_messages(created_at DESC);

                CREATE INDEX IF NOT EXISTS idx_chat_user_id
                ON market_chat_messages(user_id);
            """))
            conn.commit()
            logger.info("Market chat table initialized")
    except Exception as e:
        logger.warning(f"Chat table initialization note: {e}")


# Initialize table on module load
try:
    ensure_chat_table_exists()
except Exception as e:
    logger.warning(f"Could not auto-initialize chat table: {e}")


# ================================================================
# AUTHENTICATION
# ================================================================

class UserProxy:
    """Simple user proxy for authentication."""
    def __init__(self, id: int, email: str, name: Optional[str] = None):
        self.id = id
        self.email = email
        self.name = name or email.split("@")[0]


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> UserProxy:
    """
    Get current user from JWT token.
    Falls back to demo user for development.
    """
    import os
    from jose import jwt

    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        token = credentials.credentials
        secret = os.getenv("SECRET_KEY", "")
        payload = jwt.decode(token, secret, algorithms=["HS256"], options={"verify_aud": False})
        email = payload.get("sub")

        if not email:
            raise HTTPException(status_code=401, detail="Invalid token")

        result = db.execute(
            text("SELECT id, email, full_name FROM users WHERE email = :email"),
            {"email": email}
        )
        row = result.fetchone()
        if row:
            return UserProxy(id=row[0], email=row[1], name=row[2])

        raise HTTPException(status_code=401, detail="User not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Auth error in market_chat")
        raise HTTPException(status_code=401, detail="Authentication failed")


# ================================================================
# PYDANTIC MODELS
# ================================================================

class ChatMessageCreate(BaseModel):
    """Request model for creating a chat message."""
    message: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Chat message content"
    )


class ChatMessageResponse(BaseModel):
    """Response model for a single chat message."""
    id: int = Field(..., description="Message ID")
    user_id: Optional[int] = Field(None, description="User ID who sent the message")
    user_name: str = Field(..., description="Display name of sender")
    message: str = Field(..., description="Message content")
    created_at: str = Field(..., description="ISO timestamp when message was sent")

    class Config:
        from_attributes = True


class ChatMessagesResponse(BaseModel):
    """Response model for listing chat messages."""
    messages: List[ChatMessageResponse] = Field(default=[], description="List of chat messages")
    total: int = Field(0, description="Total number of messages returned")


class SendMessageResponse(BaseModel):
    """Response model for sending a message."""
    success: bool = Field(..., description="Whether the message was sent successfully")
    message_id: int = Field(..., description="ID of the created message")
    user_name: str = Field(..., description="Display name of sender")


# ================================================================
# API ENDPOINTS
# ================================================================

@router.get("/messages", response_model=ChatMessagesResponse)
async def get_messages(
    limit: int = Query(50, ge=1, le=200, description="Maximum messages to return"),
    db: Session = Depends(get_db),
    current_user: UserProxy = Depends(get_current_user)
):
    """
    Get recent chat messages for the market dashboard.

    Returns messages in chronological order (oldest first).
    """
    try:
        result = db.execute(text("""
            SELECT id, user_id, user_name, message, created_at
            FROM market_chat_messages
            ORDER BY created_at DESC
            LIMIT :limit
        """), {"limit": limit})

        rows = result.fetchall()

        # Reverse to show oldest first (chronological order)
        messages = []
        for row in reversed(rows):
            messages.append(ChatMessageResponse(
                id=row[0],
                user_id=row[1],
                user_name=row[2] or "Unknown",
                message=row[3],
                created_at=row[4].isoformat() if row[4] else ""
            ))

        return ChatMessagesResponse(
            messages=messages,
            total=len(messages)
        )

    except Exception as e:
        logger.error(f"Error getting chat messages: {e}")
        return ChatMessagesResponse(messages=[], total=0)


@router.post("/messages", response_model=SendMessageResponse)
async def send_message(
    chat_message: ChatMessageCreate,
    db: Session = Depends(get_db),
    current_user: UserProxy = Depends(get_current_user)
):
    """
    Send a new chat message to the market dashboard.

    Messages are visible to all team members viewing the market dashboard.
    """
    message_text = chat_message.message.strip()

    if not message_text:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    try:
        result = db.execute(text("""
            INSERT INTO market_chat_messages (user_id, user_name, message, created_at)
            VALUES (:user_id, :user_name, :message, :created_at)
            RETURNING id
        """), {
            "user_id": current_user.id,
            "user_name": current_user.name,
            "message": message_text,
            "created_at": datetime.now(timezone.utc)
        })

        message_id = result.fetchone()[0]
        db.commit()

        logger.info(f"Chat message {message_id} sent by user {current_user.id}")

        return SendMessageResponse(
            success=True,
            message_id=message_id,
            user_name=current_user.name
        )

    except Exception as e:
        logger.error(f"Error sending chat message: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to send message")


@router.delete("/messages/{message_id}")
async def delete_message(
    message_id: int,
    db: Session = Depends(get_db),
    current_user: UserProxy = Depends(get_current_user)
):
    """
    Delete a chat message.

    Users can only delete their own messages.
    """
    try:
        # Check if message exists and belongs to user
        result = db.execute(text("""
            SELECT id, user_id FROM market_chat_messages
            WHERE id = :message_id
        """), {"message_id": message_id})

        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Message not found")

        if row[1] != current_user.id:
            raise HTTPException(status_code=403, detail="Cannot delete another user's message")

        db.execute(text("""
            DELETE FROM market_chat_messages WHERE id = :message_id
        """), {"message_id": message_id})
        db.commit()

        return {"success": True, "message": "Message deleted"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting message: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to delete message")


@router.get("/health")
async def health_check():
    """Health check endpoint for market chat service."""
    return {
        "status": "healthy",
        "service": "market-chat",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
