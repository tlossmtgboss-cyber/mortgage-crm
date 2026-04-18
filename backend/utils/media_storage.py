"""
MMS Media Storage — S3-backed media storage for SMS/MMS attachments.

Railway containers are ephemeral: local filesystem wipes on every redeploy.
This module ensures MMS media (inbound and outbound) persists in S3.

Usage:
    from utils.media_storage import get_media_storage

    storage = get_media_storage()
    # Upload raw bytes
    url = storage.upload_media(file_bytes, "photo.jpg", "image/jpeg", org_id=1)
    # Download from a Telnyx media URL and re-upload to S3
    url = storage.store_from_url("https://telnyx.com/media/...", "attachment.jpg", org_id=1)
    # Get a presigned download URL for a stored key
    url = storage.get_media_url("sms-media/org-1/abc123.jpg")

Environment variables:
    AWS_S3_BUCKET          — S3 bucket name (falls back to PERENNIA_S3_BUCKET)
    AWS_ACCESS_KEY_ID      — AWS credentials
    AWS_SECRET_ACCESS_KEY  — AWS credentials
    AWS_REGION             — AWS region (default: us-east-1)
"""

from __future__ import annotations

import logging
import mimetypes
import os
import uuid
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# S3 client (lazy singleton)
# ---------------------------------------------------------------------------
_s3_client = None
_s3_available: bool = False
_bucket_name: str = ""
_region: str = ""


def _init_s3():
    """Lazily initialize the S3 client and module-level state."""
    global _s3_client, _s3_available, _bucket_name, _region

    if _s3_client is not None:
        return

    _bucket_name = (
        os.getenv("AWS_S3_BUCKET")
        or os.getenv("PERENNIA_S3_BUCKET", "perennia-docs")
    )
    _region = os.getenv("AWS_REGION", "us-east-1")

    ak = os.getenv("AWS_ACCESS_KEY_ID", "").strip()
    sk = os.getenv("AWS_SECRET_ACCESS_KEY", "").strip()

    if not ak or not sk:
        logger.warning(
            "MMS media storage: AWS credentials not configured — "
            "S3 uploads disabled, media URLs stored as references only"
        )
        _s3_available = False
        return

    try:
        import boto3
        from botocore.config import Config

        config = Config(
            signature_version="s3v4",
            s3={"addressing_style": "virtual"},
        )
        _s3_client = boto3.client(
            "s3",
            region_name=_region,
            aws_access_key_id=ak,
            aws_secret_access_key=sk,
            config=config,
        )
        _s3_available = True
        logger.info(
            "MMS media storage initialized: bucket=%s region=%s",
            _bucket_name,
            _region,
        )
    except Exception as e:
        logger.warning("Failed to initialize S3 for media storage: %s", e)
        _s3_available = False


# ---------------------------------------------------------------------------
# Key generation
# ---------------------------------------------------------------------------

def _generate_s3_key(
    filename: str,
    org_id: Optional[int] = None,
    prefix: str = "sms-media",
) -> str:
    """Generate a unique S3 key for an MMS attachment.

    Format: sms-media/org-{org_id}/{uuid12}.{ext}
    """
    ext = ""
    if filename and "." in filename:
        ext = filename.rsplit(".", 1)[-1].lower()
    if not ext or len(ext) > 10:
        ext = "bin"

    unique_id = uuid.uuid4().hex[:12]
    org_part = f"org-{org_id}" if org_id else "org-unknown"
    return f"{prefix}/{org_part}/{unique_id}.{ext}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class MediaStorage:
    """S3-backed media storage for MMS attachments."""

    @property
    def is_available(self) -> bool:
        """Return True if S3 is configured and the client is ready."""
        _init_s3()
        return _s3_available

    def upload_media(
        self,
        file_data: bytes,
        filename: str,
        content_type: str,
        org_id: Optional[int] = None,
    ) -> str:
        """Upload raw bytes to S3 and return the S3 key.

        If S3 is not configured, returns an empty string and logs a warning.
        The caller should treat an empty return as "not stored in S3" and
        fall back to storing the original URL reference.

        Parameters
        ----------
        file_data : bytes
            Raw file content.
        filename : str
            Original filename (used for extension detection).
        content_type : str
            MIME type (e.g. "image/jpeg").
        org_id : int, optional
            Organization ID for tenant-scoped storage.

        Returns
        -------
        str
            The S3 object key on success, or empty string on failure.
        """
        _init_s3()
        if not _s3_available or _s3_client is None:
            logger.warning("S3 not available — skipping media upload for %s", filename)
            return ""

        s3_key = _generate_s3_key(filename, org_id=org_id)

        try:
            _s3_client.put_object(
                Bucket=_bucket_name,
                Key=s3_key,
                Body=file_data,
                ContentType=content_type or "application/octet-stream",
            )
            logger.info(
                "MMS media uploaded to S3: %s (%d bytes)", s3_key, len(file_data)
            )
            return s3_key
        except Exception as e:
            logger.error("S3 upload failed for %s: %s", filename, e)
            return ""

    def get_media_url(self, key: str, expires_in: int = 3600) -> str:
        """Return a presigned download URL for an S3 key.

        Parameters
        ----------
        key : str
            S3 object key.
        expires_in : int
            URL validity in seconds (default 1 hour).

        Returns
        -------
        str
            Presigned URL, or empty string if S3 is unavailable.
        """
        _init_s3()
        if not _s3_available or _s3_client is None or not key:
            return ""

        try:
            url = _s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": _bucket_name, "Key": key},
                ExpiresIn=expires_in,
            )
            return url
        except Exception as e:
            logger.error("Failed to generate presigned URL for %s: %s", key, e)
            return ""

    def store_from_url(
        self,
        url: str,
        filename: str,
        org_id: Optional[int] = None,
        timeout: int = 15,
    ) -> str:
        """Download media from a URL and re-upload to S3.

        This is the primary method for persisting inbound MMS media:
        Telnyx provides temporary media URLs that expire; this method
        downloads the content and stores it permanently in S3.

        Parameters
        ----------
        url : str
            Source URL to download from (e.g. Telnyx media URL).
        filename : str
            Desired filename (for extension / content-type detection).
        org_id : int, optional
            Organization ID for tenant-scoped storage.
        timeout : int
            HTTP download timeout in seconds.

        Returns
        -------
        str
            S3 object key on success, or empty string on failure.
        """
        _init_s3()
        if not _s3_available or _s3_client is None:
            logger.warning(
                "S3 not available — cannot persist media from URL: %s", url
            )
            return ""

        if not url:
            return ""

        try:
            import requests

            resp = requests.get(url, timeout=timeout, stream=False)
            resp.raise_for_status()

            file_data = resp.content
            content_type = resp.headers.get("Content-Type", "")

            # If no filename extension, try to infer from Content-Type
            if not filename or "." not in filename:
                ext = mimetypes.guess_extension(content_type or "") or ".bin"
                filename = f"attachment{ext}"

            # Refine content_type from filename if response header was generic
            if not content_type or content_type == "application/octet-stream":
                guessed, _ = mimetypes.guess_type(filename)
                if guessed:
                    content_type = guessed

            return self.upload_media(file_data, filename, content_type, org_id=org_id)
        except Exception as e:
            logger.error("Failed to download and store media from %s: %s", url, e)
            return ""

    def get_public_url(self, key: str) -> str:
        """Return a direct (non-presigned) S3 URL.

        This only works if the bucket or object has public-read ACL.
        For most use cases, prefer ``get_media_url()`` which returns a
        presigned URL that works regardless of ACL.
        """
        _init_s3()
        if not key:
            return ""
        return f"https://{_bucket_name}.s3.amazonaws.com/{key}"


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_storage_instance: Optional[MediaStorage] = None


def get_media_storage() -> MediaStorage:
    """Return the singleton MediaStorage instance."""
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = MediaStorage()
    return _storage_instance
