"""Bootstrap MS365 integration from existing MicrosoftOAuthToken records.

Reads refresh tokens from microsoft_oauth_tokens (DRE encryption),
refreshes them against Microsoft, creates MSAccount records (MS365 encryption),
and sets up Graph webhook subscriptions.

Run: python migrations/bootstrap_ms365_from_existing.py
"""
import asyncio
import base64
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)


def get_dre_encryption_key():
    secret_key = os.environ.get("SECRET_KEY", "")
    key_material = secret_key.encode()[:32].ljust(32, b"0")
    return base64.urlsafe_b64encode(key_material)


def decrypt_dre_token(encrypted_token: str) -> str:
    from cryptography.fernet import Fernet
    f = Fernet(get_dre_encryption_key())
    return f.decrypt(encrypted_token.encode()).decode()


async def bootstrap():
    from db import SessionLocal
    from database.models.microsoft import MicrosoftOAuthToken
    from database.models.user import User

    db = SessionLocal()
    try:
        tokens = db.query(MicrosoftOAuthToken).filter(
            MicrosoftOAuthToken.refresh_token.isnot(None),
            MicrosoftOAuthToken.sync_enabled.is_(True),
        ).all()

        if not tokens:
            log.warning("No active MicrosoftOAuthToken records found")
            return

        log.info("Found %d existing Microsoft OAuth records", len(tokens))

        for token_record in tokens:
            user = db.query(User).filter(User.id == token_record.user_id).first()
            if not user:
                log.warning("User %d not found, skipping", token_record.user_id)
                continue

            log.info(
                "Bootstrapping user %d (%s) — email: %s",
                user.id, getattr(user, "email", "?"), token_record.email_address,
            )

            try:
                refresh_token = decrypt_dre_token(token_record.refresh_token)
            except Exception as e:
                log.error("Failed to decrypt refresh token for user %d: %s", user.id, e)
                continue

            # Refresh to get a fresh access token with the MS365 scopes
            from integrations.microsoft365.auth import refresh_access_token
            try:
                token_response = await refresh_access_token(refresh_token)
            except Exception as e:
                log.error("Token refresh failed for user %d: %s", user.id, e)
                continue

            # Get user profile from Graph
            import httpx
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    me_resp = await client.get(
                        "https://graph.microsoft.com/v1.0/me",
                        headers={"Authorization": f"Bearer {token_response['access_token']}"},
                    )
                    me_resp.raise_for_status()
                    me = me_resp.json()
            except Exception as e:
                log.error("Graph /me failed for user %d: %s", user.id, e)
                continue

            # Create MSAccount with MS365 encryption
            from integrations.microsoft365.auth import upsert_account_from_token_response
            org_id = getattr(user, "organization_id", None)
            if not org_id:
                log.warning("User %d has no organization_id, skipping", user.id)
                continue

            account = upsert_account_from_token_response(
                db,
                organization_id=org_id,
                user_id=user.id,
                token_response=token_response,
                me=me,
            )
            log.info(
                "Created MSAccount id=%d for user %d (upn=%s)",
                account.id, user.id, account.upn,
            )

            # Create webhook subscriptions
            try:
                from integrations.microsoft365.subscriptions import ensure_all_subscriptions
                await ensure_all_subscriptions(db, account)
                log.info("Webhook subscriptions created for account %d", account.id)
            except Exception as e:
                log.warning("Subscription creation failed (non-fatal): %s", e)

            db.commit()

            # Kick off initial delta sync
            try:
                from integrations.microsoft365.tasks import delta_sync_account
                counts = await delta_sync_account(db, account)
                db.commit()
                log.info(
                    "Initial sync complete: %d emails, %d events",
                    counts["emails"], counts["events"],
                )
            except Exception as e:
                log.warning("Initial delta sync failed (will retry on schedule): %s", e)
                db.rollback()

        log.info("Bootstrap complete")
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(bootstrap())
