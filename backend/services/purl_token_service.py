"""
PURL Token Service

Provides business logic for PURL access token operations including:
- Token generation and creation
- Token verification and validation
- Token revocation
- Token lifecycle management
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Tuple
import secrets
import hashlib

from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_

from sqlalchemy.exc import SQLAlchemyError
from models.purl import (
    PURLAccessToken,
    PURLWorkspace,
    PURLContact,
    TokenScope,
    TokenStatus,
    PURLTokenGenerator,
    PURLEventsOutbox,
    EventStatus
)

logger = logging.getLogger(__name__)


class PURLTokenService:
    """
    Service for PURL access token operations.
    Manages token creation, verification, and revocation.
    """

    def __init__(self, db: Session):
        self.db = db

    # =========================================================================
    # TOKEN CREATION
    # =========================================================================

    def create_token(
        self,
        organization_id: int,
        workspace_id: int,
        scope: TokenScope = TokenScope.WRITE,
        contact_id: Optional[int] = None,
        expires_in_days: Optional[int] = None,
        created_by: Optional[int] = None
    ) -> Tuple[int, str]:
        """
        Create a new PURL access token.

        Args:
            organization_id: Organization ID
            workspace_id: Workspace ID
            scope: Token scope (read, write, full)
            contact_id: Optional contact association
            expires_in_days: Days until expiration (None = no expiration)
            created_by: User ID who created the token

        Returns:
            Tuple of (token_id, full_token)
        """
        from sqlalchemy import text

        # Generate token
        full_token, token_hash, token_prefix = PURLTokenGenerator.generate_token()

        # Calculate expiration
        expires_at = None
        if expires_in_days:
            expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)

        # Use raw SQL to bypass ORM ForeignKey resolution issues
        # The purl_access_tokens table has ForeignKey constraints to users table,
        # but the ORM can't resolve them if User model isn't loaded first
        result = self.db.execute(
            text("""
                INSERT INTO purl_access_tokens
                (organization_id, workspace_id, token_hash, token_prefix, scope, status,
                 contact_id, expires_at, created_by, created_at)
                VALUES
                (:org_id, :ws_id, :token_hash, :token_prefix, :scope, :status,
                 :contact_id, :expires_at, :created_by, :created_at)
                RETURNING id
            """),
            {
                "org_id": organization_id,
                "ws_id": workspace_id,
                "token_hash": token_hash,
                "token_prefix": token_prefix,
                "scope": scope.value,
                "status": TokenStatus.ACTIVE.value,
                "contact_id": contact_id,
                "expires_at": expires_at,
                "created_by": created_by,
                "created_at": datetime.now(timezone.utc)
            }
        )
        token_id = result.scalar()
        self.db.commit()

        # Emit event - wrapped in try-except with its own transaction
        try:
            self._emit_event(
                organization_id=organization_id,
                workspace_id=workspace_id,
                event_key="token_created",
                payload={
                    "token_id": token_id,
                    "scope": scope.value,
                    "contact_id": contact_id,
                    "expires_at": expires_at.isoformat() if expires_at else None
                }
            )
            # Commit event separately so failure doesn't affect token creation
            self.db.commit()
        except SQLAlchemyError as e:
            # Rollback just the event, keep the token
            self.db.rollback()
            logger.warning(f"Failed to emit token_created event: {e}")

        logger.info(f"Created PURL token {token_id} for workspace {workspace_id}")

        return token_id, full_token

    # =========================================================================
    # TOKEN VERIFICATION
    # =========================================================================

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Verify a token and return workspace context.

        Args:
            token: The full token string

        Returns:
            Context dict if valid, None if invalid
        """
        # Validate format
        if not PURLTokenGenerator.is_valid_format(token):
            logger.warning(
                "PURL verify rejected: bad format (prefix=%r, len=%d)",
                token[:10] if token else "",
                len(token) if token else 0,
            )
            return None

        # Hash the token for lookup
        token_hash = PURLTokenGenerator.hash_token(token)

        # Query token with workspace
        token_record = self.db.query(PURLAccessToken).filter(
            PURLAccessToken.token_hash == token_hash
        ).first()

        if not token_record:
            logger.warning("PURL verify rejected: hash not found in purl_access_tokens (prefix=%s)", token[:16])
            return None

        # Check status
        if token_record.status != TokenStatus.ACTIVE.value:
            logger.warning(
                "PURL verify rejected: token %d status=%s (expected active)",
                token_record.id,
                token_record.status,
            )
            return None

        # Check expiration
        if token_record.expires_at and token_record.expires_at < datetime.now(timezone.utc):
            # Auto-expire the token
            token_record.status = TokenStatus.EXPIRED.value
            self.db.commit()
            logger.info(
                "PURL verify rejected: token %d auto-expired (expires_at=%s)",
                token_record.id,
                token_record.expires_at.isoformat(),
            )
            return None

        # Get workspace
        workspace = self.db.query(PURLWorkspace).filter(
            PURLWorkspace.id == token_record.workspace_id
        ).first()

        if not workspace:
            logger.error(
                "PURL verify rejected: token %d references missing workspace %d",
                token_record.id,
                token_record.workspace_id,
            )
            return None

        # Update last_used_at — flush only, don't commit. The route handler
        # owns the transaction and will commit when it's done. Committing here
        # would finalize the session prematurely; failing without rollback
        # would leave the session in a broken state for the route handler.
        try:
            from sqlalchemy import text
            self.db.execute(
                text("UPDATE purl_access_tokens SET last_used_at = :now WHERE id = :id"),
                {"now": datetime.now(timezone.utc), "id": token_record.id}
            )
            self.db.flush()
        except SQLAlchemyError as e:
            try:
                self.db.rollback()
            except Exception:
                pass
            logger.warning(f"Failed to update last_used_at for token {token_record.id}: {e}")

        return {
            "token_id": token_record.id,
            "organization_id": token_record.organization_id,
            "workspace_id": token_record.workspace_id,
            "workspace_slug": workspace.slug,
            "workspace_status": workspace.status,
            "scope": TokenScope(token_record.scope),
            "contact_id": token_record.contact_id
        }

    def verify_token_for_workspace(
        self,
        token: str,
        workspace_slug: str
    ) -> Optional[Dict[str, Any]]:
        """
        Verify a token matches a specific workspace.

        Args:
            token: The full token string
            workspace_slug: Expected workspace slug

        Returns:
            Context dict if valid and matches, None otherwise
        """
        context = self.verify_token(token)

        if not context:
            return None

        if context["workspace_slug"] != workspace_slug:
            logger.warning(
                f"Token workspace mismatch: expected {workspace_slug}, "
                f"got {context['workspace_slug']}"
            )
            return None

        return context

    # =========================================================================
    # TOKEN MANAGEMENT
    # =========================================================================

    def revoke_token(
        self,
        token_id: int,
        revoked_by: Optional[int] = None,
        reason: Optional[str] = None
    ) -> bool:
        """
        Revoke an access token.

        Args:
            token_id: Token ID to revoke
            revoked_by: User ID who revoked the token
            reason: Reason for revocation

        Returns:
            True if successful, False if token not found
        """
        token = self.db.query(PURLAccessToken).filter(
            PURLAccessToken.id == token_id
        ).first()

        if not token:
            return False

        token.status = TokenStatus.REVOKED.value
        token.revoked_at = datetime.now(timezone.utc)
        token.revoked_by = revoked_by
        token.revoked_reason = reason

        self.db.commit()

        # Emit event - wrapped in try-except
        try:
            self._emit_event(
                organization_id=token.organization_id,
                workspace_id=token.workspace_id,
                event_key="token_revoked",
                payload={
                    "token_id": token_id,
                    "revoked_by": revoked_by,
                    "reason": reason
                }
            )
            self.db.commit()
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.warning(f"Failed to emit token_revoked event: {e}")

        logger.info(f"Revoked token {token_id}")
        return True

    def revoke_all_workspace_tokens(
        self,
        workspace_id: int,
        revoked_by: Optional[int] = None,
        reason: str = "Bulk revocation"
    ) -> int:
        """
        Revoke all active tokens for a workspace.

        Returns:
            Number of tokens revoked
        """
        now = datetime.now(timezone.utc)

        result = self.db.query(PURLAccessToken).filter(
            PURLAccessToken.workspace_id == workspace_id,
            PURLAccessToken.status == TokenStatus.ACTIVE.value
        ).update({
            "status": TokenStatus.REVOKED.value,
            "revoked_at": now,
            "revoked_by": revoked_by,
            "revoked_reason": reason
        })

        self.db.commit()

        if result > 0:
            # Get org_id for event
            workspace = self.db.query(PURLWorkspace).filter(
                PURLWorkspace.id == workspace_id
            ).first()

            if workspace:
                try:
                    self._emit_event(
                        organization_id=workspace.organization_id,
                        workspace_id=workspace_id,
                        event_key="all_tokens_revoked",
                        payload={
                            "count": result,
                            "revoked_by": revoked_by,
                            "reason": reason
                        }
                    )
                    self.db.commit()
                except SQLAlchemyError as e:
                    self.db.rollback()
                    logger.warning(f"Failed to emit all_tokens_revoked event: {e}")

        logger.info(f"Revoked {result} tokens for workspace {workspace_id}")
        return result

    def get_workspace_tokens(
        self,
        workspace_id: int,
        include_revoked: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get all tokens for a workspace.

        Args:
            workspace_id: Workspace ID
            include_revoked: Whether to include revoked/expired tokens

        Returns:
            List of token dicts
        """
        query = self.db.query(PURLAccessToken).filter(
            PURLAccessToken.workspace_id == workspace_id
        )

        if not include_revoked:
            query = query.filter(
                PURLAccessToken.status == TokenStatus.ACTIVE.value
            )

        tokens = query.order_by(PURLAccessToken.created_at.desc()).all()

        return [
            {
                "id": t.id,
                "token_prefix": t.token_prefix,
                "scope": t.scope,
                "status": t.status,
                "contact_id": t.contact_id,
                "expires_at": t.expires_at.isoformat() if t.expires_at else None,
                "last_used_at": t.last_used_at.isoformat() if t.last_used_at else None,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "created_by": t.created_by,
                "revoked_at": t.revoked_at.isoformat() if t.revoked_at else None,
                "revoked_reason": t.revoked_reason
            }
            for t in tokens
        ]

    def get_token_stats(self, organization_id: int) -> Dict[str, Any]:
        """
        Get token statistics for an organization.

        Returns:
            Dict with token counts and usage stats
        """
        # Count by status
        status_counts = self.db.query(
            PURLAccessToken.status,
            func.count(PURLAccessToken.id)
        ).filter(
            PURLAccessToken.organization_id == organization_id
        ).group_by(PURLAccessToken.status).all()

        counts = {status: count for status, count in status_counts}

        # Recent usage (last 7 days)
        week_ago = datetime.now(timezone.utc) - timedelta(days=7)
        active_tokens = self.db.query(func.count(PURLAccessToken.id)).filter(
            PURLAccessToken.organization_id == organization_id,
            PURLAccessToken.last_used_at >= week_ago
        ).scalar() or 0

        # Tokens expiring soon (next 7 days)
        week_ahead = datetime.now(timezone.utc) + timedelta(days=7)
        expiring_soon = self.db.query(func.count(PURLAccessToken.id)).filter(
            PURLAccessToken.organization_id == organization_id,
            PURLAccessToken.status == TokenStatus.ACTIVE.value,
            PURLAccessToken.expires_at.isnot(None),
            PURLAccessToken.expires_at <= week_ahead
        ).scalar() or 0

        return {
            "total": sum(counts.values()),
            "by_status": counts,
            "active_last_7_days": active_tokens,
            "expiring_next_7_days": expiring_soon
        }

    def cleanup_expired_tokens(self, batch_size: int = 100) -> int:
        """
        Mark expired tokens as expired.

        Args:
            batch_size: Number of tokens to process per batch

        Returns:
            Number of tokens updated
        """
        now = datetime.now(timezone.utc)

        result = self.db.query(PURLAccessToken).filter(
            PURLAccessToken.status == TokenStatus.ACTIVE.value,
            PURLAccessToken.expires_at.isnot(None),
            PURLAccessToken.expires_at < now
        ).limit(batch_size).update({
            "status": TokenStatus.EXPIRED.value
        }, synchronize_session=False)

        self.db.commit()

        if result > 0:
            logger.info(f"Expired {result} tokens")

        return result

    # =========================================================================
    # INTERNAL METHODS
    # =========================================================================

    def _emit_event(
        self,
        organization_id: int,
        workspace_id: int,
        event_key: str,
        payload: Dict[str, Any]
    ):
        """Emit event to outbox."""
        try:
            event = PURLEventsOutbox(
                organization_id=organization_id,
                workspace_id=workspace_id,
                event_key=event_key,
                payload=payload,
                status=EventStatus.PENDING.value
            )
            self.db.add(event)
            # Don't commit here - let caller handle transaction
        except SQLAlchemyError as e:
            # Don't fail the main operation if event emission fails
            logger.warning(f"Failed to emit event {event_key}: {e}")
