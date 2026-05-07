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
                      AND role != 'summary'
                    ORDER BY message_index ASC
                    LIMIT 50
                """), {"session_id": session_id, "user_id": user_id})
            else:
                result = db.execute(text("""
                    SELECT role, content, action_id, action_data, created_at
                    FROM ai_conversation_memory
                    WHERE session_id = CAST(:session_id AS uuid)
                      AND role != 'summary'
                    ORDER BY message_index ASC
                    LIMIT 50
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

    @staticmethod
    def get_session_messages_with_summary(
        db: Session,
        session_id: str,
        user_id: int = None,
        max_recent: int = 6,
        summary_threshold: int = 10
    ) -> List[Dict]:
        """
        Get conversation messages with a rolling summary for older turns.

        When the conversation exceeds summary_threshold messages:
        - Messages 1 through (total - max_recent) are compressed into a
          deterministic 2-3 sentence summary (no LLM call, zero latency)
        - The most recent max_recent messages are returned verbatim

        Returns:
            list: [{"role": "system", "content": "[CONVERSATION SUMMARY] ..."},
                   ...recent messages...]
        """
        # Get all messages for this session
        all_messages = ConversationMemory.get_session_messages(
            db, session_id, user_id=user_id
        )

        if len(all_messages) <= summary_threshold:
            return all_messages  # Not enough messages to warrant summarization

        # Split into old (to summarize) and recent (to keep verbatim)
        old_messages = all_messages[:-max_recent]
        recent_messages = all_messages[-max_recent:]

        # Check if we already have a cached summary for this session
        cached_summary = ConversationMemory._get_cached_summary(db, session_id)
        cached_msg_count = cached_summary.get('message_count', 0) if cached_summary else 0

        if cached_summary and cached_msg_count == len(old_messages):
            # Summary is still valid (no new messages to summarize)
            summary_text = cached_summary['summary']
        else:
            # Generate new summary from old messages
            summary_text = ConversationMemory._generate_summary(old_messages)
            # Cache the summary (non-fatal on failure)
            ConversationMemory._cache_summary(
                db, session_id, user_id, summary_text, len(old_messages)
            )

        # Build the output: summary + recent messages
        summary_message = {
            "role": "system",
            "content": (
                f"[CONVERSATION SUMMARY - Earlier in this conversation:] "
                f"{summary_text}"
            ),
        }
        return [summary_message] + recent_messages

    @staticmethod
    def _generate_summary(messages: list) -> str:
        """Generate a 2-3 sentence summary of conversation messages without an LLM call."""
        if not messages:
            return "No prior conversation."

        # Extract key topics from user messages
        user_messages = [m['content'] for m in messages if m.get('role') == 'user' and m.get('content')]
        assistant_messages = [m['content'] for m in messages if m.get('role') == 'assistant' and m.get('content')]

        # Build a deterministic summary by detecting topics
        topics = []
        for msg in user_messages:
            msg_lower = msg.lower()
            if any(w in msg_lower for w in ['pipeline', 'loan', 'processing', 'closing', 'underwriting']):
                topics.append('pipeline/loans')
            elif any(w in msg_lower for w in ['lead', 'prospect', 'client', 'borrower']):
                topics.append('leads')
            elif any(w in msg_lower for w in ['task', 'todo', 'reminder', 'follow up']):
                topics.append('tasks')
            elif any(w in msg_lower for w in ['sms', 'text', 'message', 'send']):
                topics.append('messaging')
            elif any(w in msg_lower for w in ['email', 'mail']):
                topics.append('email')
            elif any(w in msg_lower for w in ['call', 'phone', 'dial', 'voicemail']):
                topics.append('calls')
            elif any(w in msg_lower for w in ['schedule', 'calendar', 'appointment']):
                topics.append('scheduling')
            elif any(w in msg_lower for w in ['rate', 'market', 'pricing']):
                topics.append('rates')
            elif any(w in msg_lower for w in ['document', 'doc', 'upload', 'file']):
                topics.append('documents')
            elif any(w in msg_lower for w in ['compliance', 'regulation', 'audit']):
                topics.append('compliance')

        unique_topics = list(dict.fromkeys(topics))  # Preserve order, remove dupes

        # Build summary
        num_turns = len(user_messages)
        topics_str = ', '.join(unique_topics[:4]) if unique_topics else 'general questions'

        # Include the last user question from the old messages for continuity
        last_user = user_messages[-1] if user_messages else ''
        last_assistant = assistant_messages[-1][:150] if assistant_messages else ''

        summary = f"The user has asked {num_turns} questions about {topics_str}."
        if last_user:
            summary += f" Most recently discussed: \"{last_user[:100]}\"."
        if last_assistant:
            summary += f" Aria's last response on that topic: \"{last_assistant}\"."

        return summary

    @staticmethod
    def _get_cached_summary(db: Session, session_id: str) -> Optional[dict]:
        """Retrieve cached conversation summary from database."""
        try:
            result = db.execute(text("""
                SELECT content FROM ai_conversation_memory
                WHERE session_id = CAST(:session_id AS uuid)
                  AND role = 'summary'
                ORDER BY created_at DESC LIMIT 1
            """), {"session_id": session_id}).first()
            if result:
                return json.loads(result[0])
        except Exception as e:
            logger.debug(f"No cached summary found for session {session_id}: {e}")
        return None

    @staticmethod
    def _cache_summary(db: Session, session_id: str, user_id: int, summary: str, message_count: int):
        """Cache conversation summary in database.

        Uses role='summary' rows in ai_conversation_memory. If the table
        doesn't support this role value, caching silently fails and the
        summary is regenerated on each request (still zero-LLM-cost).
        """
        try:
            content = json.dumps({"summary": summary, "message_count": message_count})
            # Delete old summary for this session
            db.execute(text("""
                DELETE FROM ai_conversation_memory
                WHERE session_id = CAST(:session_id AS uuid)
                  AND role = 'summary'
            """), {"session_id": session_id})
            # Insert new summary — use message_index -1 so it sorts before real messages
            db.execute(text("""
                INSERT INTO ai_conversation_memory
                    (id, session_id, user_id, message_index, role, content, created_at)
                VALUES
                    (gen_random_uuid(), CAST(:session_id AS uuid), :user_id, -1, 'summary', :content, NOW())
            """), {"session_id": session_id, "user_id": user_id, "content": content})
            db.commit()
        except Exception as e:
            logger.warning(f"Failed to cache conversation summary: {e}")
            try:
                db.rollback()
            except Exception:
                pass
