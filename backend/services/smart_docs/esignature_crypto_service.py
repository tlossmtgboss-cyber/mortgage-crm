"""
E-Signature Cryptographic Service

Built-in e-signature system — no third-party providers (DocuSign, etc.).
All signing operations happen on-platform using standard library crypto.

Provides:
- Document hashing (SHA-256) for tamper detection
- HMAC-based signature generation and verification
- Time-limited signing session tokens
- Completion certificate generation
- Access code / SMS verification code generation
- Audit trail integrity hashing
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import base64
import os
import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class SigningCertificate:
    """Certificate data for a completed signature."""

    certificate_id: str
    envelope_uuid: str
    signer_name: str
    signer_email: str
    signed_at: str
    document_hash: str
    signature_hash: str
    ip_address: str
    user_agent: str
    verification_url: str

    def to_dict(self) -> Dict:
        return asdict(self)


class ESignatureCryptoService:
    """
    Cryptographic operations for the built-in e-signature system.

    All signing happens on our platform — no external signing providers.

    Capabilities:
    - Document hashing (SHA-256) for tamper detection
    - HMAC-based signature generation
    - Signing session token generation with expiry
    - Completion certificate generation
    - Signature verification
    - Document integrity validation
    - Access code and SMS verification code generation
    - Audit trail integrity hashing
    """

    # Separator used in HMAC message construction to prevent field-boundary attacks
    _FIELD_SEP = "|"

    def __init__(self):
        # Signing secret: used to HMAC signature hashes that prove a signing event occurred.
        signing_secret_env = os.getenv("ESIGN_SIGNING_SECRET", "")
        if signing_secret_env:
            self._signing_secret = signing_secret_env.encode("utf-8")
        else:
            self._signing_secret = secrets.token_bytes(32)
            logger.warning(
                "ESIGN_SIGNING_SECRET not set — generated ephemeral secret. "
                "Signatures will not survive process restarts."
            )

        # Token secret: used to generate and validate time-limited signing URL tokens.
        token_secret_env = os.getenv("ESIGN_TOKEN_SECRET", "")
        if token_secret_env:
            self._token_secret = token_secret_env.encode("utf-8")
        else:
            self._token_secret = secrets.token_bytes(32)
            logger.warning(
                "ESIGN_TOKEN_SECRET not set — generated ephemeral secret. "
                "Signing tokens will not survive process restarts."
            )

        # Base URL for verification links embedded in certificates.
        self._base_url = os.getenv(
            "ESIGN_VERIFY_BASE_URL",
            "https://api.perenniaai.com/api/v1/esign/verify",
        )

    # ------------------------------------------------------------------
    # Document hashing
    # ------------------------------------------------------------------

    def hash_document(self, content: bytes) -> str:
        """
        Compute a SHA-256 hex digest of document content.

        Args:
            content: Raw bytes of the document.

        Returns:
            Lowercase hex-encoded SHA-256 hash string.
        """
        try:
            return hashlib.sha256(content).hexdigest()
        except Exception as e:
            logger.exception("Failed to hash document content")
            raise ValueError(f"Document hashing failed: {e}") from e

    # ------------------------------------------------------------------
    # Envelope UUID
    # ------------------------------------------------------------------

    def generate_envelope_uuid(self) -> str:
        """
        Generate a unique envelope identifier.

        Returns:
            A UUID-4 string (lowercase, with hyphens).
        """
        return str(uuid.uuid4())

    # ------------------------------------------------------------------
    # Signing tokens
    # ------------------------------------------------------------------

    def generate_signing_token(
        self,
        recipient_id: int,
        envelope_uuid: str,
        expires_hours: int = 168,
    ) -> Tuple[str, datetime]:
        """
        Generate a unique, time-limited signing URL token.

        The token encodes the recipient, envelope, and expiry so that
        ``validate_signing_token`` can verify it without a database lookup.

        Args:
            recipient_id: Database ID of the signing recipient.
            envelope_uuid: UUID of the envelope being signed.
            expires_hours: Token lifetime in hours (default 168 = 7 days).

        Returns:
            Tuple of (url-safe base64 token, expiry datetime in UTC).
        """
        try:
            expires_at = datetime.now(timezone.utc) + timedelta(hours=expires_hours)
            expires_ts = int(expires_at.timestamp())

            # Payload: recipient_id|envelope_uuid|expires_timestamp|random_nonce
            nonce = secrets.token_hex(16)
            payload = self._FIELD_SEP.join([
                str(recipient_id),
                envelope_uuid,
                str(expires_ts),
                nonce,
            ])

            # HMAC the payload so it cannot be forged
            mac = hmac.new(
                self._token_secret,
                payload.encode("utf-8"),
                hashlib.sha256,
            ).digest()

            # Token = base64(payload + "." + base64(mac))
            token_raw = payload.encode("utf-8") + b"." + base64.b64encode(mac)
            token = base64.urlsafe_b64encode(token_raw).decode("ascii")

            logger.info(
                "Generated signing token for recipient=%s envelope=%s expires=%s",
                recipient_id,
                envelope_uuid,
                expires_at.isoformat(),
            )
            return token, expires_at

        except Exception as e:
            logger.exception("Failed to generate signing token")
            raise ValueError(f"Token generation failed: {e}") from e

    def validate_signing_token(
        self,
        token: str,
        recipient_id: int,
        envelope_uuid: str,
    ) -> bool:
        """
        Validate that a signing token is authentic and unexpired.

        Args:
            token: The URL-safe base64 token string.
            recipient_id: Expected recipient ID.
            envelope_uuid: Expected envelope UUID.

        Returns:
            True if the token is valid, False otherwise.
        """
        try:
            # Decode outer base64
            token_raw = base64.urlsafe_b64decode(token.encode("ascii"))

            # Split payload from MAC
            if b"." not in token_raw:
                logger.warning("Signing token missing separator")
                return False

            payload_bytes, mac_b64 = token_raw.rsplit(b".", 1)
            payload = payload_bytes.decode("utf-8")
            provided_mac = base64.b64decode(mac_b64)

            # Verify HMAC
            expected_mac = hmac.new(
                self._token_secret,
                payload_bytes,
                hashlib.sha256,
            ).digest()

            if not hmac.compare_digest(provided_mac, expected_mac):
                logger.warning("Signing token HMAC mismatch")
                return False

            # Parse payload fields
            parts = payload.split(self._FIELD_SEP)
            if len(parts) != 4:
                logger.warning("Signing token has unexpected field count: %d", len(parts))
                return False

            token_recipient_id, token_envelope, token_expires_ts, _nonce = parts

            # Check recipient and envelope match
            if int(token_recipient_id) != recipient_id:
                logger.warning(
                    "Signing token recipient mismatch: token=%s expected=%s",
                    token_recipient_id,
                    recipient_id,
                )
                return False

            if token_envelope != envelope_uuid:
                logger.warning(
                    "Signing token envelope mismatch: token=%s expected=%s",
                    token_envelope,
                    envelope_uuid,
                )
                return False

            # Check expiry
            expires_at = datetime.fromtimestamp(int(token_expires_ts), tz=timezone.utc)
            if datetime.now(timezone.utc) > expires_at:
                logger.warning(
                    "Signing token expired at %s",
                    expires_at.isoformat(),
                )
                return False

            return True

        except Exception as e:
            logger.exception("Signing token validation failed: %s", e)
            return False

    # ------------------------------------------------------------------
    # Signature hashing / verification
    # ------------------------------------------------------------------

    def generate_signature_hash(
        self,
        document_hash: str,
        signer_email: str,
        signed_at: datetime,
        ip_address: str,
    ) -> str:
        """
        Create an HMAC-based signature hash proving a signing event occurred.

        The hash binds the document content, signer identity, timestamp, and
        IP address together so that none can be altered after the fact.

        Args:
            document_hash: SHA-256 hex digest of the signed document.
            signer_email: Email address of the signer.
            signed_at: UTC datetime of the signing event.
            ip_address: IP address from which the signer signed.

        Returns:
            Hex-encoded HMAC-SHA256 signature hash.
        """
        try:
            signed_at_iso = signed_at.isoformat()
            message = self._FIELD_SEP.join([
                document_hash,
                signer_email.lower().strip(),
                signed_at_iso,
                ip_address,
            ])

            signature = hmac.new(
                self._signing_secret,
                message.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()

            logger.info(
                "Generated signature hash for signer=%s document=%s…",
                signer_email,
                document_hash[:16],
            )
            return signature

        except Exception as e:
            logger.exception("Failed to generate signature hash")
            raise ValueError(f"Signature hash generation failed: {e}") from e

    def verify_signature_hash(
        self,
        signature_hash: str,
        document_hash: str,
        signer_email: str,
        signed_at: datetime,
        ip_address: str,
    ) -> bool:
        """
        Verify that a stored signature hash matches the expected inputs.

        Args:
            signature_hash: The hex HMAC hash to verify.
            document_hash: SHA-256 hex digest of the document at signing time.
            signer_email: Signer's email address.
            signed_at: UTC datetime of the signing event.
            ip_address: IP address used during signing.

        Returns:
            True if the signature hash is valid, False otherwise.
        """
        try:
            expected = self.generate_signature_hash(
                document_hash, signer_email, signed_at, ip_address,
            )
            return hmac.compare_digest(signature_hash, expected)
        except Exception as e:
            logger.exception("Signature hash verification failed: %s", e)
            return False

    # ------------------------------------------------------------------
    # Document integrity
    # ------------------------------------------------------------------

    def verify_document_integrity(
        self,
        original_hash: str,
        current_content: bytes,
    ) -> Tuple[bool, str]:
        """
        Compare a stored document hash against the current document content.

        Args:
            original_hash: The SHA-256 hex hash recorded at signing time.
            current_content: Current raw bytes of the document.

        Returns:
            Tuple of (is_valid, current_hash). ``is_valid`` is True when
            the document has not been tampered with.
        """
        try:
            current_hash = self.hash_document(current_content)
            is_valid = hmac.compare_digest(original_hash, current_hash)

            if not is_valid:
                logger.warning(
                    "Document integrity check FAILED: original=%s… current=%s…",
                    original_hash[:16],
                    current_hash[:16],
                )

            return is_valid, current_hash

        except Exception as e:
            logger.exception("Document integrity verification failed: %s", e)
            return False, ""

    # ------------------------------------------------------------------
    # Completion certificate
    # ------------------------------------------------------------------

    def generate_completion_certificate(
        self,
        envelope_uuid: str,
        title: str,
        signers: List[Dict],
        document_hash: str,
    ) -> SigningCertificate:
        """
        Generate certificate data for a fully-completed signing envelope.

        Each signer dict should contain at minimum:
            - name (str)
            - email (str)
            - signed_at (str, ISO-8601)
            - ip_address (str)
            - user_agent (str)

        The certificate is generated for the *last* signer (the one who
        completed the envelope).  A composite signature hash is computed
        over all signers to bind the entire ceremony together.

        Args:
            envelope_uuid: UUID of the completed envelope.
            title: Document/envelope title.
            signers: List of signer info dicts (see above).
            document_hash: SHA-256 hex digest of the final signed document.

        Returns:
            A ``SigningCertificate`` dataclass instance.
        """
        try:
            if not signers:
                raise ValueError("At least one signer is required")

            certificate_id = f"CERT-{uuid.uuid4().hex[:12].upper()}"

            # Build a composite signature hash over all signers
            signer_components = []
            for signer in signers:
                signed_at_str = signer.get("signed_at", datetime.now(timezone.utc).isoformat())
                if isinstance(signed_at_str, datetime):
                    signed_at_str = signed_at_str.isoformat()
                signer_components.append(self._FIELD_SEP.join([
                    signer.get("email", "").lower().strip(),
                    signed_at_str,
                    signer.get("ip_address", "unknown"),
                ]))

            composite_message = self._FIELD_SEP.join([
                certificate_id,
                envelope_uuid,
                document_hash,
                *signer_components,
            ])

            composite_hash = hmac.new(
                self._signing_secret,
                composite_message.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()

            # Use the last signer as the certificate's primary signer
            last_signer = signers[-1]
            signed_at_val = last_signer.get("signed_at", datetime.now(timezone.utc).isoformat())
            if isinstance(signed_at_val, datetime):
                signed_at_val = signed_at_val.isoformat()

            verification_url = f"{self._base_url}/{certificate_id}"

            certificate = SigningCertificate(
                certificate_id=certificate_id,
                envelope_uuid=envelope_uuid,
                signer_name=last_signer.get("name", "Unknown"),
                signer_email=last_signer.get("email", ""),
                signed_at=signed_at_val,
                document_hash=document_hash,
                signature_hash=composite_hash,
                ip_address=last_signer.get("ip_address", "unknown"),
                user_agent=last_signer.get("user_agent", "unknown"),
                verification_url=verification_url,
            )

            logger.info(
                "Generated completion certificate %s for envelope %s (%d signers)",
                certificate_id,
                envelope_uuid,
                len(signers),
            )
            return certificate

        except Exception as e:
            logger.exception("Failed to generate completion certificate")
            raise ValueError(f"Certificate generation failed: {e}") from e

    # ------------------------------------------------------------------
    # Access codes and SMS verification
    # ------------------------------------------------------------------

    def generate_access_code(self) -> str:
        """
        Generate a 6-digit numeric PIN for extra signer authentication.

        Returns:
            A zero-padded 6-digit string (e.g. "042817").
        """
        try:
            code = secrets.randbelow(1_000_000)
            return f"{code:06d}"
        except Exception as e:
            logger.exception("Failed to generate access code")
            raise ValueError(f"Access code generation failed: {e}") from e

    def generate_sms_verification_code(self) -> str:
        """
        Generate a 6-digit SMS verification code.

        Functionally identical to ``generate_access_code`` but kept as a
        separate method for clarity in calling code and potential future
        divergence (e.g., alphanumeric codes).

        Returns:
            A zero-padded 6-digit string.
        """
        try:
            code = secrets.randbelow(1_000_000)
            return f"{code:06d}"
        except Exception as e:
            logger.exception("Failed to generate SMS verification code")
            raise ValueError(f"SMS code generation failed: {e}") from e

    def hash_access_code(self, code: str) -> str:
        """
        Hash an access code for safe database storage.

        Uses SHA-256 with a per-service salt derived from the signing secret.

        Args:
            code: The plaintext access code.

        Returns:
            Hex-encoded hash suitable for storage.
        """
        try:
            # Derive a stable salt from the signing secret so hashes are
            # consistent across calls but not rainbow-table-friendly.
            salt = hashlib.sha256(
                b"access-code-salt" + self._signing_secret
            ).digest()[:16]

            return hashlib.sha256(salt + code.encode("utf-8")).hexdigest()

        except Exception as e:
            logger.exception("Failed to hash access code")
            raise ValueError(f"Access code hashing failed: {e}") from e

    def verify_access_code(self, code: str, hashed: str) -> bool:
        """
        Verify an access code against its stored hash.

        Args:
            code: The plaintext code provided by the user.
            hashed: The stored hex-encoded hash.

        Returns:
            True if the code matches, False otherwise.
        """
        try:
            expected = self.hash_access_code(code)
            return hmac.compare_digest(expected, hashed)
        except Exception as e:
            logger.exception("Access code verification failed: %s", e)
            return False

    # ------------------------------------------------------------------
    # Audit trail integrity
    # ------------------------------------------------------------------

    def generate_audit_hash(self, events: List[Dict]) -> str:
        """
        Generate a SHA-256 hash over a list of audit trail events.

        The events are serialized to canonical JSON (sorted keys, no extra
        whitespace) so that the hash is deterministic regardless of dict
        ordering.

        Args:
            events: List of audit event dicts. Each should contain at
                minimum ``action``, ``timestamp``, and ``actor``.

        Returns:
            Hex-encoded SHA-256 hash of the canonical event stream.
        """
        try:
            # Canonical JSON serialization for deterministic hashing
            canonical = json.dumps(
                events,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            )

            audit_hash = hmac.new(
                self._signing_secret,
                canonical.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()

            logger.debug(
                "Generated audit hash over %d events: %s…",
                len(events),
                audit_hash[:16],
            )
            return audit_hash

        except Exception as e:
            logger.exception("Failed to generate audit hash")
            raise ValueError(f"Audit hash generation failed: {e}") from e

    # ------------------------------------------------------------------
    # Signing payload
    # ------------------------------------------------------------------

    def create_signing_payload(
        self,
        document_hash: str,
        fields: List[Dict],
        signer_info: Dict,
    ) -> Dict:
        """
        Create the canonical signing payload that gets hashed when a
        signer applies their signature.

        The payload captures the document state, which fields were filled,
        and who is signing so that the resulting hash is a complete
        attestation of the signing event.

        Args:
            document_hash: SHA-256 hex digest of the document being signed.
            fields: List of field dicts, each containing at minimum
                ``field_id``, ``field_type``, and ``value``.
            signer_info: Dict with ``email``, ``name``, ``ip_address``,
                and ``user_agent``.

        Returns:
            A dict with keys ``payload``, ``payload_hash``, and
            ``created_at``, suitable for storage or downstream signing.
        """
        try:
            created_at = datetime.now(timezone.utc).isoformat()

            # Build canonical payload — sorted keys for determinism
            payload = {
                "created_at": created_at,
                "document_hash": document_hash,
                "fields": sorted(fields, key=lambda f: f.get("field_id", "")),
                "signer": {
                    "email": signer_info.get("email", "").lower().strip(),
                    "ip_address": signer_info.get("ip_address", "unknown"),
                    "name": signer_info.get("name", ""),
                    "user_agent": signer_info.get("user_agent", "unknown"),
                },
                "version": "1.0",
            }

            canonical = json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            )

            payload_hash = hmac.new(
                self._signing_secret,
                canonical.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()

            logger.info(
                "Created signing payload for signer=%s document=%s… hash=%s…",
                signer_info.get("email", "unknown"),
                document_hash[:16],
                payload_hash[:16],
            )

            return {
                "payload": payload,
                "payload_hash": payload_hash,
                "created_at": created_at,
            }

        except Exception as e:
            logger.exception("Failed to create signing payload")
            raise ValueError(f"Signing payload creation failed: {e}") from e


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_service: Optional[ESignatureCryptoService] = None


def get_esignature_crypto_service() -> ESignatureCryptoService:
    """
    Get or create the singleton ESignatureCryptoService instance.

    Returns:
        The shared ``ESignatureCryptoService`` instance.
    """
    global _service
    if _service is None:
        _service = ESignatureCryptoService()
    return _service
