"""
Market Chat Routes

API endpoints for team chat on the Market Dashboard.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import sqlite3
import os

router = APIRouter(prefix="/api/v1/market-chat", tags=["market-chat"])

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:RzXRIwJsZINuRwMQybbbZYqYFoHBaxRw@postgres.railway.internal:5432/railway")


def get_db_connection():
    """Get database connection - uses PostgreSQL in production."""
    if "postgresql" in DATABASE_URL:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    else:
        # SQLite fallback for local dev
        conn = sqlite3.connect("mortgage_crm.db")
        conn.row_factory = sqlite3.Row
        return conn


def init_chat_table():
    """Initialize the market_chat_messages table."""
    conn = get_db_connection()
    cursor = conn.cursor()

    if "postgresql" in DATABASE_URL:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS market_chat_messages (
                id SERIAL PRIMARY KEY,
                user_id INTEGER,
                user_name VARCHAR(255),
                message TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    else:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS market_chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                user_name TEXT,
                message TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

    conn.commit()
    conn.close()


# Initialize table on module load
try:
    init_chat_table()
except Exception as e:
    print(f"Warning: Could not initialize chat table: {e}")


class ChatMessage(BaseModel):
    message: str


class ChatMessageResponse(BaseModel):
    id: int
    user_id: Optional[int]
    user_name: str
    message: str
    created_at: str


# Auth dependency (simplified - in production use proper auth)
async def get_current_user(authorization: str = None):
    """Get current user from token."""
    from jose import jwt

    if not authorization:
        return {"id": 1, "name": "Demo User", "email": "demo@example.com"}

    try:
        token = authorization.replace("Bearer ", "")
        secret = os.getenv("JWT_SECRET", "your-secret-key")
        payload = jwt.decode(token, secret, algorithms=["HS256"])

        # Get user from database
        conn = get_db_connection()
        cursor = conn.cursor()

        if "postgresql" in DATABASE_URL:
            from psycopg2.extras import RealDictCursor
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("SELECT id, name, email FROM users WHERE email = %s", (payload.get("sub"),))
        else:
            cursor.execute("SELECT id, name, email FROM users WHERE email = ?", (payload.get("sub"),))

        user = cursor.fetchone()
        conn.close()

        if user:
            if isinstance(user, dict):
                return user
            return {"id": user[0], "name": user[1] or user[2].split("@")[0], "email": user[2]}

        return {"id": 1, "name": payload.get("sub", "User").split("@")[0], "email": payload.get("sub")}
    except Exception as e:
        print(f"Auth error: {e}")
        return {"id": 1, "name": "User", "email": "user@example.com"}


@router.get("/messages")
async def get_messages(limit: int = 50, authorization: str = None):
    """Get recent chat messages."""
    try:
        conn = get_db_connection()

        if "postgresql" in DATABASE_URL:
            from psycopg2.extras import RealDictCursor
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("""
                SELECT id, user_id, user_name, message, created_at
                FROM market_chat_messages
                ORDER BY created_at DESC
                LIMIT %s
            """, (limit,))
        else:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, user_id, user_name, message, created_at
                FROM market_chat_messages
                ORDER BY created_at DESC
                LIMIT ?
            """, (limit,))

        rows = cursor.fetchall()
        conn.close()

        messages = []
        for row in reversed(rows):  # Reverse to show oldest first
            if isinstance(row, dict):
                messages.append({
                    "id": row["id"],
                    "user_id": row["user_id"],
                    "user_name": row["user_name"],
                    "message": row["message"],
                    "created_at": str(row["created_at"])
                })
            else:
                messages.append({
                    "id": row[0],
                    "user_id": row[1],
                    "user_name": row[2],
                    "message": row[3],
                    "created_at": str(row[4])
                })

        return {"messages": messages}
    except Exception as e:
        print(f"Error getting messages: {e}")
        return {"messages": []}


@router.post("/messages")
async def send_message(chat_message: ChatMessage, authorization: str = None):
    """Send a new chat message."""
    user = await get_current_user(authorization)

    if not chat_message.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    try:
        conn = get_db_connection()

        if "postgresql" in DATABASE_URL:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO market_chat_messages (user_id, user_name, message)
                VALUES (%s, %s, %s)
                RETURNING id
            """, (user.get("id"), user.get("name", "User"), chat_message.message.strip()))
            message_id = cursor.fetchone()[0]
        else:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO market_chat_messages (user_id, user_name, message)
                VALUES (?, ?, ?)
            """, (user.get("id"), user.get("name", "User"), chat_message.message.strip()))
            message_id = cursor.lastrowid

        conn.commit()
        conn.close()

        return {
            "success": True,
            "message_id": message_id,
            "user_name": user.get("name", "User")
        }
    except Exception as e:
        print(f"Error sending message: {e}")
        raise HTTPException(status_code=500, detail="Failed to send message")
