"""
Recording Backup Service — S3-compatible cloud storage for call recordings.

Railway containers are ephemeral. Recordings saved to local disk at
recordings/{org_id}/ are lost on restart. This service uploads each
recording to S3 (or any S3-compatible store) immediately after download,
providing durable storage for compliance-mandated call retention.

Configuration (env vars):
    RECORDING_S3_BUCKET       — target bucket name (required to enable)
    RECORDING_S3_PREFIX       — key prefix, e.g. "recordings/" (default: "recordings/")
    AWS_ACCESS_KEY_ID         — IAM credentials
    AWS_SECRET_ACCESS_KEY     — IAM credentials
    AWS_REGION                — e.g. "us-east-1" (default: "us-east-1")

If RECORDING_S3_BUCKET is not set the service degrades gracefully:
all methods log a warning and return None.
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


class RecordingBackupService:
    """Upload call recordings to S3 and generate presigned download URLs."""

    def __init__(self):
        self._bucket = os.getenv("RECORDING_S3_BUCKET")
        self._prefix = os.getenv("RECORDING_S3_PREFIX", "recordings/")
        self._region = os.getenv("AWS_REGION", "us-east-1")
        self._client = None
        self._enabled = bool(self._bucket)

        if not self._enabled:
            logger.warning(
                "RecordingBackupService: RECORDING_S3_BUCKET not set — "
                "S3 backup is disabled. Recordings will only exist on local disk."
            )

    def _get_client(self):
        """Lazy-init the boto3 S3 client."""
        if self._client is not None:
            return self._client

        try:
            import boto3
            self._client = boto3.client(
                "s3",
                region_name=self._region,
                aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            )
            return self._client
        except Exception as e:
            logger.error("Failed to create S3 client: %s", e)
            self._enabled = False
            return None

    def _s3_key(self, org_id: Optional[int], call_id: str) -> str:
        """Build the S3 object key for a recording."""
        org_part = str(org_id) if org_id else "default"
        # Ensure prefix ends with / but avoid double-slash
        prefix = self._prefix.rstrip("/") + "/"
        return f"{prefix}{org_part}/{call_id}.wav"

    def upload_recording(
        self,
        org_id: Optional[int],
        call_id: str,
        file_path: str,
    ) -> Optional[str]:
        """
        Upload a local recording file to S3.

        Args:
            org_id:    Organization ID (used in the S3 key path).
            call_id:   Vapi call ID (used as the filename).
            file_path: Absolute or relative path to the local .wav file.

        Returns:
            The S3 key on success, or None if upload was skipped/failed.
        """
        if not self._enabled:
            logger.debug("S3 backup disabled — skipping upload for call %s", call_id)
            return None

        client = self._get_client()
        if client is None:
            return None

        key = self._s3_key(org_id, call_id)

        try:
            client.upload_file(
                Filename=file_path,
                Bucket=self._bucket,
                Key=key,
                ExtraArgs={"ContentType": "audio/wav"},
            )
            logger.info(
                "Recording uploaded to S3: bucket=%s key=%s",
                self._bucket,
                key,
            )
            return key
        except Exception as e:
            logger.error(
                "S3 upload failed for call %s: %s (local file retained at %s)",
                call_id,
                e,
                file_path,
            )
            return None

    def get_recording_url(
        self,
        org_id: Optional[int],
        call_id: str,
        expires_in: int = 3600,
    ) -> Optional[str]:
        """
        Generate a presigned URL for a recording stored in S3.

        Args:
            org_id:     Organization ID.
            call_id:    Vapi call ID.
            expires_in: URL validity in seconds (default: 1 hour).

        Returns:
            Presigned URL string, or None if S3 is not configured / call fails.
        """
        if not self._enabled:
            logger.debug("S3 backup disabled — cannot generate URL for call %s", call_id)
            return None

        client = self._get_client()
        if client is None:
            return None

        key = self._s3_key(org_id, call_id)

        try:
            url = client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=expires_in,
            )
            return url
        except Exception as e:
            logger.error(
                "Failed to generate presigned URL for call %s: %s",
                call_id,
                e,
            )
            return None


# Module-level singleton — import and use directly.
recording_backup = RecordingBackupService()
