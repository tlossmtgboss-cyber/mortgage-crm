"""
Smart Docs S3 Storage Service

Handles document storage for Smart Docs:
- Direct file uploads from backend
- Presigned URLs for downloads
- File retrieval for reprocessing
- Storage key management
"""

import os
import uuid
import logging
from io import BytesIO
from datetime import datetime, timezone
from typing import Optional, Dict, Any, BinaryIO, Union

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from botocore.config import Config

logger = logging.getLogger(__name__)


class SmartDocsS3Service:
    """
    S3 service for Smart Docs document storage.

    Features:
    - Direct upload from backend (server-side)
    - Presigned download URLs
    - File retrieval for reprocessing
    - Automatic content type handling
    """

    def __init__(
        self,
        bucket_name: Optional[str] = None,
        region: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None
    ):
        """
        Initialize S3 service.

        Args:
            bucket_name: S3 bucket name (defaults to SMART_DOCS_S3_BUCKET or PERENNIA_S3_BUCKET)
            region: AWS region (defaults to AWS_REGION)
            access_key: AWS access key (defaults to AWS_ACCESS_KEY_ID)
            secret_key: AWS secret key (defaults to AWS_SECRET_ACCESS_KEY)
        """
        self.bucket_name = bucket_name or os.getenv(
            "SMART_DOCS_S3_BUCKET",
            os.getenv("PERENNIA_S3_BUCKET", "perennia-docs")
        )
        self.region = region or os.getenv("AWS_REGION", "us-east-1")
        self.prefix = "smart-docs"  # All smart docs stored under this prefix

        # Check if we have AWS credentials
        self._s3_available = False
        self.s3_client = None

        try:
            # Configure client
            config = Config(
                signature_version='s3v4',
                s3={'addressing_style': 'virtual'}
            )

            # Use explicit credentials if provided, otherwise use env/IAM role
            ak = access_key or os.getenv("AWS_ACCESS_KEY_ID")
            sk = secret_key or os.getenv("AWS_SECRET_ACCESS_KEY")

            if ak and sk:
                self.s3_client = boto3.client(
                    's3',
                    region_name=self.region,
                    aws_access_key_id=ak,
                    aws_secret_access_key=sk,
                    config=config
                )
                self._s3_available = True
                logger.info(f"Smart Docs S3 service initialized with bucket: {self.bucket_name}")
            else:
                # Try default credentials (IAM role, etc.)
                try:
                    self.s3_client = boto3.client(
                        's3',
                        region_name=self.region,
                        config=config
                    )
                    # Test credentials
                    self.s3_client.list_buckets()
                    self._s3_available = True
                    logger.info(f"Smart Docs S3 service initialized with IAM credentials")
                except (NoCredentialsError, ClientError):
                    logger.warning("AWS credentials not available - S3 storage disabled")
                    self._s3_available = False

        except Exception as e:
            logger.warning(f"Failed to initialize S3 client: {e} - storage disabled")
            self._s3_available = False

        # Storage configuration
        self.download_expiry = 300  # 5 minutes for downloads
        self.max_file_size = 50 * 1024 * 1024  # 50MB

    @property
    def is_available(self) -> bool:
        """Check if S3 storage is available."""
        return self._s3_available

    def generate_storage_key(
        self,
        loan_id: int,
        borrower_id: Optional[int],
        file_name: str,
        document_id: Optional[int] = None,
        organization_id: Optional[int] = None,
    ) -> str:
        """
        Generate a unique storage key for a document.

        Format: org/{org_id}/smart-docs/{loan_id}/{borrower_id}/{uuid}_{filename}
        Legacy (no org): smart-docs/{loan_id}/{borrower_id}/{uuid}_{filename}

        Args:
            loan_id: Loan ID
            borrower_id: Borrower ID (optional)
            file_name: Original file name
            document_id: Optional document ID to include
            organization_id: Organization ID for tenant isolation

        Returns:
            Storage key string

        Raises:
            ValueError: If organization_id is None
        """
        if organization_id is None:
            raise ValueError("organization_id is required for document storage")

        # Sanitize filename
        safe_name = "".join(c for c in file_name if c.isalnum() or c in '.-_').strip()
        if not safe_name:
            safe_name = "document"

        # Generate unique ID
        unique_id = uuid.uuid4().hex[:12]

        # Build path
        borrower_part = str(borrower_id) if borrower_id else "unknown"
        org_prefix = f"org/{organization_id}/" if organization_id else ""

        if document_id:
            return f"{org_prefix}{self.prefix}/{loan_id}/{borrower_part}/{document_id}_{unique_id}_{safe_name}"
        else:
            return f"{org_prefix}{self.prefix}/{loan_id}/{borrower_part}/{unique_id}_{safe_name}"

    def upload_file(
        self,
        file_content: Union[bytes, BinaryIO],
        storage_key: str,
        content_type: str,
        metadata: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Upload a file directly to S3.

        Args:
            file_content: File content as bytes or file-like object
            storage_key: S3 object key
            content_type: MIME type
            metadata: Optional custom metadata

        Returns:
            Dict with success status and details
        """
        if not self._s3_available:
            logger.warning(f"S3 not available - file not uploaded: {storage_key}")
            return {
                "success": False,
                "error": "S3 storage not configured",
                "storage_key": storage_key,
                "stored": False
            }

        try:
            # Convert file-like objects to bytes
            if isinstance(file_content, bytes):
                body = file_content
                file_size = len(file_content)
                logger.debug(f"S3 upload: using bytes directly, size={file_size}")
            else:
                # Read from file-like object
                logger.debug(f"S3 upload: reading from file-like object type={type(file_content)}")
                body = file_content.read()
                file_size = len(body)

            logger.debug(f"S3 upload: size={file_size}, key={storage_key}")

            # Build put_object params
            put_params = {
                'Bucket': self.bucket_name,
                'Key': storage_key,
                'Body': body,
                'ContentType': content_type,
            }

            if metadata:
                put_params['Metadata'] = {
                    str(k): str(v) for k, v in metadata.items()
                }

            logger.debug("S3 upload: calling put_object...")
            # Upload using put_object (simpler than upload_fileobj)
            self.s3_client.put_object(**put_params)
            logger.debug("S3 upload: put_object completed successfully")

            logger.info(f"Uploaded to S3: {storage_key} ({file_size} bytes)")

            return {
                "success": True,
                "storage_key": storage_key,
                "bucket": self.bucket_name,
                "file_size": file_size,
                "content_type": content_type,
                "stored": True
            }

        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            logger.error(f"S3 upload failed ({error_code}): {e}")
            return {
                "success": False,
                "error": f"S3 upload failed: {error_code}",
                "storage_key": storage_key,
                "stored": False
            }
        except Exception as e:
            logger.error(f"Unexpected error uploading to S3: {e}")
            return {
                "success": False,
                "error": "Internal server error",
                "storage_key": storage_key,
                "stored": False
            }

    def download_file(self, storage_key: str) -> Dict[str, Any]:
        """
        Download a file from S3.

        Args:
            storage_key: S3 object key

        Returns:
            Dict with file content and metadata, or error
        """
        if not self._s3_available:
            return {
                "success": False,
                "error": "S3 storage not configured"
            }

        try:
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=storage_key
            )

            content = response['Body'].read()

            return {
                "success": True,
                "content": content,
                "content_type": response.get('ContentType', 'application/octet-stream'),
                "file_size": response['ContentLength'],
                "last_modified": response['LastModified'].isoformat(),
                "metadata": response.get('Metadata', {})
            }

        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            if error_code == '404' or error_code == 'NoSuchKey':
                return {
                    "success": False,
                    "error": "File not found",
                    "not_found": True
                }
            logger.error(f"S3 download failed ({error_code}): {e}")
            return {
                "success": False,
                "error": f"S3 download failed: {error_code}"
            }

    def get_presigned_download_url(
        self,
        storage_key: str,
        file_name: Optional[str] = None,
        expires_in: Optional[int] = None,
        inline: bool = False,
        organization_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Generate a presigned URL for downloading/viewing a document.

        Args:
            storage_key: S3 object key
            file_name: Original file name for Content-Disposition
            expires_in: Custom expiry time in seconds
            inline: If True, use inline disposition for browser viewing
            organization_id: Organization ID for tenant validation (recommended)

        Returns:
            Dict with presigned_url and expiry info
        """
        if not self._s3_available:
            return {
                "success": False,
                "error": "S3 storage not configured"
            }

        # Validate tenant access (required for all presigned URLs)
        if not organization_id:
            logger.error("presigned_url_denied: organization_id is required")
            return {
                "success": False,
                "error": "organization_id is required for presigned URL generation"
            }
        if not self._validate_org_access(storage_key, organization_id):
                logger.warning(
                    f"Presigned URL denied: org {organization_id} cannot access key {storage_key}"
                )
                return {
                    "success": False,
                    "error": "Access denied: document belongs to another organization"
                }

        try:
            params = {
                'Bucket': self.bucket_name,
                'Key': storage_key
            }

            # Set content disposition
            if file_name:
                disposition = "inline" if inline else "attachment"
                params['ResponseContentDisposition'] = f'{disposition}; filename="{file_name}"'

            presigned_url = self.s3_client.generate_presigned_url(
                'get_object',
                Params=params,
                ExpiresIn=expires_in or self.download_expiry
            )

            return {
                "success": True,
                "presigned_url": presigned_url,
                "storage_key": storage_key,
                "expires_in": expires_in or self.download_expiry
            }

        except ClientError as e:
            logger.error(f"Error generating presigned download URL: {e}")
            return {
                "success": False,
                "error": "Internal server error"
            }

    def _validate_org_access(self, storage_key: str, organization_id: int) -> bool:
        """
        Verify the storage key belongs to the requesting organization.

        Keys MUST begin with org-{id}/ or org/{id}/. Legacy untagged keys
        must be migrated via scripts/migrate_legacy_s3_keys.py first.
        """
        if not organization_id or not storage_key:
            return False
        new_prefix = f"org-{organization_id}/"
        legacy_prefix = f"org/{organization_id}/"
        if storage_key.startswith(new_prefix) or storage_key.startswith(legacy_prefix):
            return True
        logger.warning(
            "s3_access_denied key=%s org_id=%s (no matching org prefix)",
            storage_key, organization_id,
        )
        return False

    def delete_file(self, storage_key: str) -> Dict[str, Any]:
        """
        Delete a file from S3.

        Args:
            storage_key: S3 object key

        Returns:
            Dict with success status
        """
        if not self._s3_available:
            return {
                "success": False,
                "error": "S3 storage not configured"
            }

        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=storage_key
            )

            logger.info(f"Deleted document from S3: {storage_key}")

            return {
                "success": True,
                "deleted": storage_key
            }

        except ClientError as e:
            logger.error(f"Error deleting document: {e}")
            return {
                "success": False,
                "error": "Internal server error"
            }

    def file_exists(self, storage_key: str) -> bool:
        """
        Check if a file exists in S3.

        Args:
            storage_key: S3 object key

        Returns:
            True if file exists, False otherwise
        """
        if not self._s3_available:
            return False

        try:
            self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=storage_key
            )
            return True
        except ClientError:
            return False


# Singleton instance
_smart_docs_s3_service: Optional[SmartDocsS3Service] = None


def get_smart_docs_s3_service() -> SmartDocsS3Service:
    """Get or create the Smart Docs S3 service singleton."""
    global _smart_docs_s3_service
    if _smart_docs_s3_service is None:
        _smart_docs_s3_service = SmartDocsS3Service()
    return _smart_docs_s3_service
