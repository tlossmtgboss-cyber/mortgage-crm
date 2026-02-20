"""
Conversation Memory Service
Handles permanent conversation storage and retrieval
"""

from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime
from typing import List, Dict, Optional
import json
import logging

logger = logging.getLogger(__name__)


class ConversationMemory:
    """Handles permanent conversation storage and retrieval"""

    @staticmethod
    def save_message(
        db: Session,
        user_id: int,
        session_id: str,
        role: str,
        content: str,
        action_id: str = None,
        action_data: dict = None,
        organization_id: int = None
    ):
        """Save a message to permanent storage.

        Args:
            organization_id: Tenant org ID for RLS. Defense-in-depth: RLS policies
                enforce isolation via app.current_tenant, but writing the correct
                organization_id ensures new rows are visible under the policy.
        """
        try:
            # Get next message index
            result = db.execute(text("""
                SELECT COALESCE(MAX(message_index), -1) + 1
                FROM ai_conversation_memory
                WHERE session_id = CAST(:session_id AS uuid)
            """), {"session_id": session_id})
            message_index = result.scalar() or 0

            # Prepare action data
            action_id_val = action_id if action_id else None
            action_data_val = json.dumps(action_data) if action_data else None

            # Build column/value lists dynamically based on optional fields
            columns = ["id", "user_id", "session_id", "message_index", "role", "content", "created_at"]
            values = [
                "gen_random_uuid()",
                ":user_id",
                "CAST(:session_id AS uuid)",
                ":message_index",
                ":role",
                ":content",
                "NOW()"
            ]
            params = {
                "user_id": user_id,
                "session_id": session_id,
                "message_index": message_index,
                "role": role,
                "content": content,
            }

            if organization_id is not None:
                columns.append("organization_id")
                values.append(":organization_id")
                params["organization_id"] = organization_id

            if action_id_val:
                columns.append("action_id")
                values.append("CAST(:action_id AS uuid)")
                params["action_id"] = action_id_val

            if action_data_val:
                columns.append("action_data")
                values.append("CAST(:action_data AS jsonb)")
                params["action_data"] = action_data_val

            col_sql = ", ".join(columns)
            val_sql = ", ".join(values)

            db.execute(text(f"""
                INSERT INTO ai_conversation_memory ({col_sql})
                VALUES ({val_sql})
            """), params)
            db.commit()
            logger.info(f"Saved message for user {user_id}, session {session_id}")

        except Exception as e:
            logger.error(f"Error saving message: {e}")
            db.rollback()
            raise

    @staticmethod
    def get_recent_messages(db: Session, user_id: int, limit: int = 50) -> List[Dict]:
        """Get recent messages for context.

        Tenant isolation: user_id scopes the query to the requesting user.
        RLS policy on ai_conversation_memory (via app.current_tenant) provides
        additional tenant-level isolation as defense-in-depth.
        """
        try:
            result = db.execute(text("""
                SELECT role, content, action_id, action_data, created_at
                FROM ai_conversation_memory
                WHERE user_id = :user_id
                ORDER BY created_at DESC
                LIMIT :limit
            """), {"user_id": user_id, "limit": limit})

            messages = []
            for row in result:
                messages.append({
                    'role': row[0],
                    'content': row[1],
                    'action_id': str(row[2]) if row[2] else None,
                    'action_data': row[3],
                    'timestamp': row[4].isoformat() if row[4] else None
                })

            # Return in chronological order
            return list(reversed(messages))

        except Exception as e:
            logger.error(f"Error getting recent messages: {e}")
            return []

    @staticmethod
    def search_history(db: Session, user_id: int, query: str, limit: int = 10) -> List[Dict]:
        """Search conversation history using full-text search.

        Tenant isolation: user_id scopes the query. RLS on ai_conversation_memory
        provides additional tenant-level isolation via app.current_tenant.
        """
        try:
            result = db.execute(text("""
                SELECT role, content, created_at
                FROM ai_conversation_memory
                WHERE user_id = :user_id
                AND to_tsvector('english', content) @@ plainto_tsquery('english', :query)
                ORDER BY created_at DESC
                LIMIT :limit
            """), {"user_id": user_id, "query": query, "limit": limit})

            return [{
                'role': r[0],
                'content': r[1],
                'timestamp': r[2].isoformat() if r[2] else None
            } for r in result]

        except Exception as e:
            logger.error(f"Error searching history: {e}")
            return []

    @staticmethod
    def save_action(
        db: Session,
        user_id: int,
        action_id: str,
        action_type: str,
        preview_data: dict,
        organization_id: int = None
    ):
        """Save action to history.

        Args:
            organization_id: Tenant org ID for RLS defense-in-depth.
        """
        try:
            columns = ["id", "user_id", "action_id", "action_type", "preview_data", "status", "created_at"]
            values = [
                "gen_random_uuid()",
                ":user_id",
                "CAST(:action_id AS uuid)",
                ":action_type",
                "CAST(:preview_data AS jsonb)",
                "'previewed'",
                "NOW()"
            ]
            params = {
                "user_id": user_id,
                "action_id": action_id,
                "action_type": action_type,
                "preview_data": json.dumps(preview_data),
            }

            if organization_id is not None:
                columns.append("organization_id")
                values.append(":organization_id")
                params["organization_id"] = organization_id

            col_sql = ", ".join(columns)
            val_sql = ", ".join(values)

            db.execute(text(f"""
                INSERT INTO ai_action_history ({col_sql})
                VALUES ({val_sql})
            """), params)
            db.commit()
            logger.info(f"Saved action {action_id} for user {user_id}")

        except Exception as e:
            logger.error(f"Error saving action: {e}")
            db.rollback()
            raise

    @staticmethod
    def update_action_status(
        db: Session,
        action_id: str,
        status: str,
        execution_data: dict = None
    ):
        """Update action status"""
        try:
            exec_data = json.dumps(execution_data) if execution_data else None

            if exec_data:
                db.execute(text("""
                    UPDATE ai_action_history
                    SET status = :status,
                        execution_data = CAST(:exec_data AS jsonb),
                        executed_at = CASE WHEN :status = 'executed' THEN NOW() ELSE NULL END
                    WHERE action_id = CAST(:action_id AS uuid)
                """), {
                    "status": status,
                    "exec_data": exec_data,
                    "action_id": action_id
                })
            else:
                db.execute(text("""
                    UPDATE ai_action_history
                    SET status = :status,
                        executed_at = CASE WHEN :status = 'executed' THEN NOW() ELSE NULL END
                    WHERE action_id = CAST(:action_id AS uuid)
                """), {
                    "status": status,
                    "action_id": action_id
                })
            db.commit()
            logger.info(f"Updated action {action_id} to status {status}")

        except Exception as e:
            logger.error(f"Error updating action status: {e}")
            db.rollback()
            raise

    @staticmethod
    def get_recent_actions(db: Session, user_id: int, limit: int = 10) -> List[Dict]:
        """Get recent actions"""
        try:
            result = db.execute(text("""
                SELECT action_id, action_type, status, preview_data, created_at
                FROM ai_action_history
                WHERE user_id = :user_id
                ORDER BY created_at DESC
                LIMIT :limit
            """), {"user_id": user_id, "limit": limit})

            return [{
                'action_id': str(r[0]),
                'action_type': r[1],
                'status': r[2],
                'preview': r[3],
                'timestamp': r[4].isoformat() if r[4] else None
            } for r in result]

        except Exception as e:
            logger.error(f"Error getting recent actions: {e}")
            return []

    @staticmethod
    def get_full_context(db: Session, user_id: int, current_message: str) -> Dict:
        """Get intelligent context for Claude"""
        try:
            # Get recent messages
            recent = ConversationMemory.get_recent_messages(db, user_id, limit=50)

            # Search relevant past if user references history
            relevant_past = []
            memory_keywords = ['remember', 'discussed', 'mentioned', 'said', 'before',
                             'yesterday', 'last', 'earlier', 'previous', 'ago']
            if any(word in current_message.lower() for word in memory_keywords):
                relevant_past = ConversationMemory.search_history(db, user_id, current_message, limit=5)

            # Get recent actions
            actions = ConversationMemory.get_recent_actions(db, user_id, limit=10)

            # Get total message count
            total_result = db.execute(text("""
                SELECT COUNT(*) FROM ai_conversation_memory WHERE user_id = :user_id
            """), {"user_id": user_id})
            total_messages = total_result.scalar() or 0

            return {
                'recent_messages': recent,
                'relevant_past': relevant_past,
                'recent_actions': actions,
                'total_messages': total_messages
            }

        except Exception as e:
            logger.error(f"Error getting full context: {e}")
            return {
                'recent_messages': [],
                'relevant_past': [],
                'recent_actions': [],
                'total_messages': 0
            }

    @staticmethod
    def get_session_messages(db: Session, session_id: str, user_id: int = None) -> List[Dict]:
        """Get all messages for a specific session.

        Args:
            user_id: If provided, also filter by user_id as defense-in-depth.
                RLS via app.current_tenant provides tenant isolation, but adding
                user_id prevents cross-user session access within the same tenant.
        """
        try:
            if user_id is not None:
                result = db.execute(text("""
                    SELECT role, content, action_id, action_data, created_at
                    FROM ai_conversation_memory
                    WHERE session_id = CAST(:session_id AS uuid)
                      AND user_id = :user_id
                    ORDER BY message_index ASC
                """), {"session_id": session_id, "user_id": user_id})
            else:
                result = db.execute(text("""
                    SELECT role, content, action_id, action_data, created_at
                    FROM ai_conversation_memory
                    WHERE session_id = CAST(:session_id AS uuid)
                    ORDER BY message_index ASC
                """), {"session_id": session_id})

            return [{
                'role': r[0],
                'content': r[1],
                'action_id': str(r[2]) if r[2] else None,
                'action_data': r[3],
                'timestamp': r[4].isoformat() if r[4] else None
            } for r in result]

        except Exception as e:
            logger.error(f"Error getting session messages: {e}")
            return []
