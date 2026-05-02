"""OAuth (delegated, auth-code-with-PKCE) and per-user token vault.

Uses MSAL for the auth-code flow and cryptography.fernet to encrypt the
refresh token at rest.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from .config import GRAPH_AUTHORITY, GRAPH_SCOPES, get_settings
from .models import MSAccount

log = logging.getLogger(__name__)


class TokenVault:
    def __init__(self) -> None:
        key = get_settings().token_encryption_key.get_secret_value().encode()
        try:
            Fernet(key)
        except (ValueError, TypeError) as exc:
            raise RuntimeError(
                "MS_TOKEN_ENCRYPTION_KEY must be a 32-byte url-safe base64 string"
            ) from exc
        self._fernet = Fernet(key)

    def encrypt(self, plaintext: str) -> bytes:
        return self._fernet.encrypt(plaintext.encode())

    def decrypt(self, ciphertext: bytes) -> str:
        try:
            return self._fernet.decrypt(ciphertext).decode()
        except InvalidToken as exc:
            raise RuntimeError("Token decryption failed — key rotation needed?") from exc


_vault: TokenVault | None = None


def get_vault() -> TokenVault:
    global _vault
    if _vault is None:
        _vault = TokenVault()
    return _vault


def build_authorization_url(state: str, code_challenge: str) -> str:
    s = get_settings()
    params = {
        "client_id": s.client_id,
        "response_type": "code",
        "redirect_uri": s.redirect_uri,
        "response_mode": "query",
        "scope": " ".join(GRAPH_SCOPES),
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "prompt": "select_account",
    }
    return f"{GRAPH_AUTHORITY}/{s.tenant_id}/oauth2/v2.0/authorize?{urlencode(params)}"


def generate_pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge


async def exchange_code_for_token(code: str, code_verifier: str) -> dict[str, Any]:
    s = get_settings()
    url = f"{GRAPH_AUTHORITY}/{s.tenant_id}/oauth2/v2.0/token"
    data = {
        "client_id": s.client_id,
        "client_secret": s.client_secret.get_secret_value(),
        "scope": " ".join(GRAPH_SCOPES),
        "code": code,
        "redirect_uri": s.redirect_uri,
        "grant_type": "authorization_code",
        "code_verifier": code_verifier,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, data=data)
        resp.raise_for_status()
        return resp.json()


async def refresh_access_token(refresh_token: str) -> dict[str, Any]:
    s = get_settings()
    url = f"{GRAPH_AUTHORITY}/{s.tenant_id}/oauth2/v2.0/token"
    data = {
        "client_id": s.client_id,
        "client_secret": s.client_secret.get_secret_value(),
        "scope": " ".join(GRAPH_SCOPES),
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, data=data)
        resp.raise_for_status()
        return resp.json()


def upsert_account_from_token_response(
    db: Session,
    *,
    organization_id: int,
    user_id: int,
    token_response: dict[str, Any],
    me: dict[str, Any],
) -> MSAccount:
    vault = get_vault()
    refresh_token = token_response.get("refresh_token")
    access_token = token_response.get("access_token")
    expires_in = int(token_response.get("expires_in", 3600))
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in - 60)

    if not refresh_token or not access_token:
        raise ValueError("Token response missing refresh_token or access_token")

    enc_refresh = vault.encrypt(refresh_token)
    enc_access = vault.encrypt(access_token)

    existing = db.query(MSAccount).filter(
        MSAccount.organization_id == organization_id,
        MSAccount.user_id == user_id,
    ).first()

    if existing:
        existing.encrypted_refresh_token = enc_refresh
        existing.encrypted_access_token = enc_access
        existing.access_token_expires_at = expires_at
        existing.ms_user_id = me["id"]
        existing.upn = me.get("userPrincipalName") or me.get("mail") or ""
        existing.display_name = me.get("displayName")
        existing.scopes = GRAPH_SCOPES
        existing.is_active = True
        existing.last_error = None
        db.flush()
        return existing

    account = MSAccount(
        organization_id=organization_id,
        user_id=user_id,
        ms_user_id=me["id"],
        upn=me.get("userPrincipalName") or me.get("mail") or "",
        display_name=me.get("displayName"),
        encrypted_refresh_token=enc_refresh,
        encrypted_access_token=enc_access,
        access_token_expires_at=expires_at,
        scopes=GRAPH_SCOPES,
        is_active=True,
    )
    db.add(account)
    db.flush()
    return account


async def get_valid_access_token(db: Session, account: MSAccount) -> str:
    vault = get_vault()
    now = datetime.now(timezone.utc)
    if (
        account.encrypted_access_token
        and account.access_token_expires_at
        and account.access_token_expires_at > now
    ):
        return vault.decrypt(account.encrypted_access_token)

    refresh = vault.decrypt(account.encrypted_refresh_token)
    try:
        resp = await refresh_access_token(refresh)
    except httpx.HTTPStatusError as exc:
        account.is_active = False
        account.last_error = f"Refresh failed: {exc.response.status_code} {exc.response.text[:200]}"
        db.flush()
        raise

    expires_in = int(resp.get("expires_in", 3600))
    account.encrypted_access_token = vault.encrypt(resp["access_token"])
    account.access_token_expires_at = now + timedelta(seconds=expires_in - 60)

    new_refresh = resp.get("refresh_token")
    if new_refresh:
        account.encrypted_refresh_token = vault.encrypt(new_refresh)

    db.flush()
    return resp["access_token"]
