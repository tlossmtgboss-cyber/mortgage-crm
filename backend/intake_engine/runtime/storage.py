"""
Session Storage with Redis and Postgres support
Implements append-only event log with hash chaining
"""

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .models import (
    Session, AuditEvent, EventType, SLATask,
    DataClass
)

# Try to import Redis, fallback to in-memory if not available
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

# Try to import SQLAlchemy for Postgres
try:
    from sqlalchemy import create_engine, text, Column, String, JSON, DateTime, Boolean, Integer
    from sqlalchemy.ext.declarative import declarative_base
    from sqlalchemy.orm import sessionmaker
    SQLALCHEMY_AVAILABLE = True
except ImportError:
    SQLALCHEMY_AVAILABLE = False


class InMemoryStore:
    """Fallback in-memory storage for development"""
    def __init__(self):
        self.sessions: Dict[str, Session] = {}
        self.events: Dict[str, List[AuditEvent]] = {}
        self.tasks: Dict[str, List[SLATask]] = {}

    def set_session(self, session: Session, ttl: int = 3600):
        self.sessions[session.session_id] = session

    def get_session(self, session_id: str) -> Optional[Session]:
        return self.sessions.get(session_id)

    def delete_session(self, session_id: str):
        self.sessions.pop(session_id, None)

    def append_event(self, event: AuditEvent):
        if event.session_id not in self.events:
            self.events[event.session_id] = []
        self.events[event.session_id].append(event)

    def get_events(self, session_id: str) -> List[AuditEvent]:
        return self.events.get(session_id, [])

    def add_task(self, task: SLATask):
        if task.session_id not in self.tasks:
            self.tasks[task.session_id] = []
        self.tasks[task.session_id].append(task)

    def get_tasks(self, session_id: str) -> List[SLATask]:
        return self.tasks.get(session_id, [])


class RedisStore:
    """Redis-based session storage"""
    def __init__(self, redis_url: str, prefix: str = "intake:"):
        if not REDIS_AVAILABLE:
            raise ImportError("redis package not installed")
        self.client = redis.from_url(redis_url)
        self.prefix = prefix

    def _key(self, suffix: str) -> str:
        return f"{self.prefix}{suffix}"

    def set_session(self, session: Session, ttl: int = 3600):
        key = self._key(f"session:{session.session_id}")
        self.client.setex(key, ttl, session.model_dump_json())

    def get_session(self, session_id: str) -> Optional[Session]:
        key = self._key(f"session:{session_id}")
        data = self.client.get(key)
        if data:
            return Session.model_validate_json(data)
        return None

    def delete_session(self, session_id: str):
        key = self._key(f"session:{session_id}")
        self.client.delete(key)

    def append_event(self, event: AuditEvent):
        key = self._key(f"events:{event.session_id}")
        self.client.rpush(key, event.model_dump_json())

    def get_events(self, session_id: str) -> List[AuditEvent]:
        key = self._key(f"events:{session_id}")
        events = self.client.lrange(key, 0, -1)
        return [AuditEvent.model_validate_json(e) for e in events]


class PostgresStore:
    """Postgres-based persistent storage"""
    def __init__(self, database_url: str, table_prefix: str = "intake_"):
        if not SQLALCHEMY_AVAILABLE:
            raise ImportError("sqlalchemy package not installed")

        self.engine = create_engine(database_url)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.prefix = table_prefix

    def set_session(self, session: Session, ttl: int = 3600):
        with self.SessionLocal() as db:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)
            db.execute(text(f"""
                INSERT INTO {self.prefix}sessions
                (session_id, data, expires_at, created_at, updated_at)
                VALUES (:session_id, :data, :expires_at, :created_at, :updated_at)
                ON CONFLICT (session_id)
                DO UPDATE SET data = :data, updated_at = :updated_at, expires_at = :expires_at
            """), {
                "session_id": session.session_id,
                "data": session.model_dump_json(),
                "expires_at": expires_at,
                "created_at": session.created_at,
                "updated_at": session.updated_at,
            })
            db.commit()

    def get_session(self, session_id: str) -> Optional[Session]:
        with self.SessionLocal() as db:
            result = db.execute(text(f"""
                SELECT data FROM {self.prefix}sessions
                WHERE session_id = :session_id AND expires_at > NOW()
            """), {"session_id": session_id})
            row = result.fetchone()
            if row:
                return Session.model_validate_json(row[0])
        return None

    def delete_session(self, session_id: str):
        with self.SessionLocal() as db:
            db.execute(text(f"""
                DELETE FROM {self.prefix}sessions WHERE session_id = :session_id
            """), {"session_id": session_id})
            db.commit()

    def append_event(self, event: AuditEvent):
        with self.SessionLocal() as db:
            db.execute(text(f"""
                INSERT INTO {self.prefix}audit_events
                (event_id, session_id, party_id, event_type, payload,
                 hash_prev, hash_self, pii_redacted, created_at)
                VALUES (:event_id, :session_id, :party_id, :event_type, :payload,
                        :hash_prev, :hash_self, :pii_redacted, :created_at)
            """), {
                "event_id": event.event_id,
                "session_id": event.session_id,
                "party_id": event.party_id,
                "event_type": event.event_type,
                "payload": json.dumps(event.payload),
                "hash_prev": event.hash_prev,
                "hash_self": event.hash_self,
                "pii_redacted": event.pii_redacted,
                "created_at": event.created_at,
            })
            db.commit()

    def get_events(self, session_id: str) -> List[AuditEvent]:
        with self.SessionLocal() as db:
            result = db.execute(text(f"""
                SELECT event_id, session_id, party_id, event_type, payload,
                       hash_prev, hash_self, pii_redacted, created_at
                FROM {self.prefix}audit_events
                WHERE session_id = :session_id
                ORDER BY created_at ASC
            """), {"session_id": session_id})
            events = []
            for row in result.fetchall():
                # JSONB columns return dict, TEXT returns string
                payload = row[4] if isinstance(row[4], dict) else (json.loads(row[4]) if row[4] else {})
                events.append(AuditEvent(
                    event_id=row[0],
                    session_id=row[1],
                    party_id=row[2],
                    event_type=row[3],
                    payload=payload,
                    hash_prev=row[5],
                    hash_self=row[6],
                    pii_redacted=row[7],
                    created_at=row[8],
                ))
            return events

    def add_task(self, task: SLATask):
        with self.SessionLocal() as db:
            db.execute(text(f"""
                INSERT INTO {self.prefix}sla_tasks
                (task_id, session_id, code, title, description, priority,
                 status, assignee_role, due_hours, created_at)
                VALUES (:task_id, :session_id, :code, :title, :description,
                        :priority, :status, :assignee_role, :due_hours, :created_at)
            """), {
                "task_id": task.task_id,
                "session_id": task.session_id,
                "code": task.code,
                "title": task.title,
                "description": task.description,
                "priority": task.priority,
                "status": task.status,
                "assignee_role": task.assignee_role,
                "due_hours": task.due_hours,
                "created_at": task.created_at,
            })
            db.commit()


class SessionStorage:
    """
    Unified session storage with Redis for caching and Postgres for persistence.
    Falls back to in-memory storage if neither is available.
    """

    # PII fields that should be redacted in audit logs
    PII_FIELDS = {
        "ssn", "ssn_last4", "ssn_full", "social_security",
        "dob", "date_of_birth", "birth_date",
        "email", "phone", "address",
        "first_name", "last_name", "full_name",
    }

    def __init__(
        self,
        redis_url: Optional[str] = None,
        postgres_url: Optional[str] = None,
        session_ttl: int = 3600,
        enable_audit: bool = True,
        enable_pii_redaction: bool = True,
    ):
        self.session_ttl = session_ttl
        self.enable_audit = enable_audit
        self.enable_pii_redaction = enable_pii_redaction

        # Initialize stores
        self.redis_store: Optional[RedisStore] = None
        self.postgres_store: Optional[PostgresStore] = None
        self.memory_store: Optional[InMemoryStore] = None

        # Redis URL from env or param
        redis_url = redis_url or os.getenv("REDIS_URL")
        postgres_url = postgres_url or os.getenv("DATABASE_URL")

        if redis_url and REDIS_AVAILABLE:
            try:
                self.redis_store = RedisStore(redis_url)
            except Exception as e:
                print(f"Failed to connect to Redis: {e}")

        if postgres_url and SQLALCHEMY_AVAILABLE:
            try:
                self.postgres_store = PostgresStore(postgres_url)
            except Exception as e:
                print(f"Failed to connect to Postgres: {e}")

        # Fallback to in-memory
        if not self.redis_store and not self.postgres_store:
            self.memory_store = InMemoryStore()
            print("Using in-memory storage (development mode)")

    def _compute_hash(self, event: AuditEvent, prev_hash: Optional[str]) -> str:
        """Compute SHA-256 hash for event chain"""
        data = json.dumps({
            "prev": prev_hash or "",
            "type": event.event_type,
            "payload": event.payload,
            "timestamp": event.created_at.isoformat(),
        }, sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()

    def _redact_pii(self, payload: Dict[str, Any], data_class: DataClass = DataClass.SENSITIVE) -> Dict[str, Any]:
        """Redact PII from payload based on data classification"""
        if not self.enable_pii_redaction or data_class == DataClass.PUBLIC:
            return payload

        redacted = {}
        for key, value in payload.items():
            key_lower = key.lower()

            # Check if this is a PII field
            is_pii = any(pii in key_lower for pii in self.PII_FIELDS)

            if is_pii and data_class == DataClass.RESTRICTED:
                # For RESTRICTED, only store a hash reference
                if value:
                    redacted[key] = f"[REDACTED:hash:{hashlib.sha256(str(value).encode()).hexdigest()[:8]}]"
                else:
                    redacted[key] = "[REDACTED]"
            elif is_pii and data_class == DataClass.SENSITIVE:
                # For SENSITIVE, store type info but not value
                redacted[key] = f"[REDACTED:{type(value).__name__}]"
            elif isinstance(value, dict):
                redacted[key] = self._redact_pii(value, data_class)
            else:
                redacted[key] = value

        return redacted

    # ========================================================================
    # Session Operations
    # ========================================================================

    def save_session(self, session: Session):
        """Save session to storage"""
        session.updated_at = datetime.now(timezone.utc)

        # Save to Redis (cache)
        if self.redis_store:
            self.redis_store.set_session(session, self.session_ttl)

        # Save to Postgres (persistence)
        if self.postgres_store:
            self.postgres_store.set_session(session, self.session_ttl)

        # Fallback to memory
        if self.memory_store:
            self.memory_store.set_session(session, self.session_ttl)

    def get_session(self, session_id: str) -> Optional[Session]:
        """Get session from storage"""
        # Try Redis first
        if self.redis_store:
            session = self.redis_store.get_session(session_id)
            if session:
                return session

        # Try Postgres
        if self.postgres_store:
            session = self.postgres_store.get_session(session_id)
            if session:
                # Re-cache in Redis
                if self.redis_store:
                    self.redis_store.set_session(session, self.session_ttl)
                return session

        # Fallback to memory
        if self.memory_store:
            return self.memory_store.get_session(session_id)

        return None

    def delete_session(self, session_id: str):
        """Delete session from storage"""
        if self.redis_store:
            self.redis_store.delete_session(session_id)
        if self.postgres_store:
            self.postgres_store.delete_session(session_id)
        if self.memory_store:
            self.memory_store.delete_session(session_id)

    # ========================================================================
    # Audit Event Operations
    # ========================================================================

    def create_event(
        self,
        session_id: str,
        event_type: EventType,
        payload: Dict[str, Any],
        party_id: Optional[str] = None,
        data_class: DataClass = DataClass.SENSITIVE,
    ) -> AuditEvent:
        """Create and store an audit event with hash chain"""
        if not self.enable_audit:
            return AuditEvent(
                session_id=session_id,
                event_type=event_type,
                payload=payload,
                party_id=party_id,
            )

        # Get previous hash
        events = self.get_events(session_id)
        prev_hash = events[-1].hash_self if events else None

        # Redact PII if needed
        redacted_payload = self._redact_pii(payload, data_class)
        pii_redacted = redacted_payload != payload

        # Create event
        event = AuditEvent(
            session_id=session_id,
            event_type=event_type,
            payload=redacted_payload,
            party_id=party_id,
            hash_prev=prev_hash,
            pii_redacted=pii_redacted,
        )

        # Compute hash
        event.hash_self = self._compute_hash(event, prev_hash)

        # Store event
        self._store_event(event)

        return event

    def _store_event(self, event: AuditEvent):
        """Store event to persistent storage"""
        if self.postgres_store:
            self.postgres_store.append_event(event)
        elif self.memory_store:
            self.memory_store.append_event(event)

        # Also cache in Redis for quick access
        if self.redis_store:
            self.redis_store.append_event(event)

    def get_events(self, session_id: str) -> List[AuditEvent]:
        """Get all events for a session"""
        # Try Postgres first (source of truth)
        if self.postgres_store:
            return self.postgres_store.get_events(session_id)

        # Try Redis
        if self.redis_store:
            return self.redis_store.get_events(session_id)

        # Fallback to memory
        if self.memory_store:
            return self.memory_store.get_events(session_id)

        return []

    def verify_event_chain(self, session_id: str) -> bool:
        """Verify the integrity of the event hash chain"""
        events = self.get_events(session_id)
        if not events:
            return True

        prev_hash = None
        for event in events:
            expected_hash = self._compute_hash(event, prev_hash)
            if event.hash_self != expected_hash:
                return False
            prev_hash = event.hash_self

        return True

    # ========================================================================
    # SLA Task Operations
    # ========================================================================

    def create_task(self, task: SLATask):
        """Create an SLA task"""
        if self.postgres_store:
            self.postgres_store.add_task(task)
        elif self.memory_store:
            self.memory_store.add_task(task)

    def get_tasks(self, session_id: str) -> List[SLATask]:
        """Get all tasks for a session"""
        if self.memory_store:
            return self.memory_store.get_tasks(session_id)
        return []
