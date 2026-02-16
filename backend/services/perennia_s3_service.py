"""
Perennia Docs S3 Service

Handles document storage with AWS S3:
- Presigned URL generation for secure uploads
- Presigned URL generation for downloads
- File deletion and management
- Storage key generation
"""

import os
import uuid
import logging
import mimetypes
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple

import boto3
from botocore.exceptions import ClientError
from botocore.config import Config

logger = logging.getLogger(__name__)


class PerenniaS3Service:
    """
    S3 service for Perennia Docs document storage.

    Features:
    - Presigned upload URLs (PUT)
    - Presigned download URLs (GET)
    - Multi-part upload support for large files
    - Automatic content type detection
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
            bucket_name: S3 bucket name (defaults to PERENNIA_S3_BUCKET env var)
            region: AWS region (defaults to AWS_REGION env var)
            access_key: AWS access key (defaults to AWS_ACCESS_KEY_ID env var)
            secret_key: AWS secret key (defaults to AWS_SECRET_ACCESS_KEY env var)
        """
        self.bucket_name = bucket_name or os.getenv("PERENNIA_S3_BUCKET", "perennia-docs")
        self.region = region or os.getenv("AWS_REGION", "us-east-1")

        # Configure client
        config = Config(
            signature_version='s3v4',
            s3={'addressing_style': 'virtual'}
        )

        # Use explicit credentials if provided, otherwise use env/IAM role
        if access_key and secret_key:
            self.s3_client = boto3.client(
                's3',
                region_name=self.region,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                config=config
            )
        else:
            self.s3_client = boto3.client(
                's3',
                region_name=self.region,
                config=config
            )

        # Storage configuration
        self.upload_expiry = 3600  # 1 hour for uploads
        self.download_expiry = 300  # 5 minutes for downloads
        self.max_file_size = 50 * 1024 * 1024  # 50MB

        # Content type restrictions for security
        self.allowed_content_types = [
            'application/pdf',
            'image/jpeg',
            'image/png',
            'image/gif',
            'image/tiff',
            'image/webp',
            'application/msword',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'application/vnd.ms-excel',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        ]

    def generate_storage_key(
        self,
        loan_id: int,
        file_name: str,
        folder: str = "originals",
        organization_id: Optional[int] = None,
    ) -> str:
        """
        Generate a unique storage key for a document.

        Format: org/{org_id}/documents/{loan_id}/{folder}/{uuid}.{extension}
        Legacy (no org): documents/{loan_id}/{folder}/{uuid}.{extension}

        Args:
            loan_id: Loan ID for organization
            file_name: Original file name (for extension)
            folder: Subfolder (originals, compressed, previews)
            organization_id: Organization ID for tenant isolation

        Returns:
            Storage key string
        """
        # Extract extension
        ext = file_name.rsplit('.', 1)[-1].lower() if '.' in file_name else 'bin'

        # Sanitize extension
        allowed_extensions = ['pdf', 'jpg', 'jpeg', 'png', 'gif', 'tiff', 'tif', 'webp', 'doc', 'docx', 'xls', 'xlsx']
        if ext not in allowed_extensions:
            ext = 'bin'

        # Generate unique key
        unique_id = uuid.uuid4().hex

        # Org-prefixed key for tenant isolation
        org_prefix = f"org/{organization_id}/" if organization_id else ""
        return f"{org_prefix}documents/{loan_id}/{folder}/{unique_id}.{ext}"

    def get_presigned_upload_url(
        self,
        storage_key: str,
        content_type: str,
        file_size: Optional[int] = None,
        metadata: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Generate a presigned URL for direct upload to S3.

        Args:
            storage_key: S3 object key
            content_type: MIME type of the file
            file_size: Expected file size (optional, for validation)
            metadata: Custom metadata to attach to the object

        Returns:
            Dict with presigned_url, fields (for POST), and expiry info
        """
        # Validate content type
        if content_type not in self.allowed_content_types:
            return {
                "success": False,
                "error": f"Content type '{content_type}' not allowed",
                "allowed_types": self.allowed_content_types
            }

        # Validate file size
        if file_size and file_size > self.max_file_size:
            return {
                "success": False,
                "error": f"File size {file_size} exceeds maximum {self.max_file_size} bytes"
            }

        try:
            # Generate presigned POST (more secure than PUT for browser uploads)
            conditions = [
                {"bucket": self.bucket_name},
                ["starts-with", "$key", storage_key],
                {"Content-Type": content_type},
                ["content-length-range", 1, self.max_file_size]
            ]

            fields = {
                "Content-Type": content_type
            }

            # Add custom metadata
            if metadata:
                for key, value in metadata.items():
                    fields[f"x-amz-meta-{key}"] = value
                    conditions.append({f"x-amz-meta-{key}": value})

            response = self.s3_client.generate_presigned_post(
                Bucket=self.bucket_name,
                Key=storage_key,
                Fields=fields,
                Conditions=conditions,
                ExpiresIn=self.upload_expiry
            )

            return {
                "success": True,
                "presigned_url": response['url'],
                "fields": response['fields'],
                "storage_key": storage_key,
                "expires_in": self.upload_expiry,
                "method": "POST"
            }

        except ClientError as e:
            logger.error(f"Error generating presigned upload URL: {e}")
            return {
                "success": False,
                "error": "Internal server error"
            }

    def get_presigned_put_url(
        self,
        storage_key: str,
        content_type: str
    ) -> Dict[str, Any]:
        """
        Generate a presigned PUT URL for upload.

        This is simpler than POST but less flexible for browser uploads.

        Args:
            storage_key: S3 object key
            content_type: MIME type of the file

        Returns:
            Dict with presigned_url and expiry info
        """
        try:
            presigned_url = self.s3_client.generate_presigned_url(
                'put_object',
                Params={
                    'Bucket': self.bucket_name,
                    'Key': storage_key,
                    'ContentType': content_type
                },
                ExpiresIn=self.upload_expiry
            )

            return {
                "success": True,
                "presigned_url": presigned_url,
                "storage_key": storage_key,
                "expires_in": self.upload_expiry,
                "method": "PUT",
                "headers": {
                    "Content-Type": content_type
                }
            }

        except ClientError as e:
            logger.error(f"Error generating presigned PUT URL: {e}")
            return {
                "success": False,
                "error": "Internal server error"
            }

    def get_presigned_download_url(
        self,
        storage_key: str,
        file_name: Optional[str] = None,
        expires_in: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Generate a presigned URL for downloading a document.

        Args:
            storage_key: S3 object key
            file_name: Original file name for Content-Disposition
            expires_in: Custom expiry time in seconds

        Returns:
            Dict with presigned_url and expiry info
        """
        try:
            params = {
                'Bucket': self.bucket_name,
                'Key': storage_key
            }

            # Add download file name
            if file_name:
                params['ResponseContentDisposition'] = f'attachment; filename="{file_name}"'

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

    def verify_upload(self, storage_key: str) -> Dict[str, Any]:
        """
        Verify that a file was successfully uploaded.

        Args:
            storage_key: S3 object key

        Returns:
            Dict with file info or error
        """
        try:
            response = self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=storage_key
            )

            return {
                "success": True,
                "exists": True,
                "file_size": response['ContentLength'],
                "content_type": response['ContentType'],
                "last_modified": response['LastModified'].isoformat(),
                "etag": response['ETag'].strip('"'),
                "metadata": response.get('Metadata', {})
            }

        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return {
                    "success": True,
                    "exists": False
                }
            logger.error(f"Error verifying upload: {e}")
            return {
                "success": False,
                "error": "Internal server error"
            }

    def make_public_and_get_url(self, storage_key: str) -> Dict[str, Any]:
        """
        Make an S3 object public and return its public URL.

        Use this for videos that should be publicly accessible.

        Args:
            storage_key: S3 object key

        Returns:
            Dict with public URL or error
        """
        try:
            # Make the object public-read
            self.s3_client.put_object_acl(
                Bucket=self.bucket_name,
                Key=storage_key,
                ACL='public-read'
            )

            # Return public URL
            public_url = f"https://{self.bucket_name}.s3.amazonaws.com/{storage_key}"

            return {
                "success": True,
                "public_url": public_url,
                "storage_key": storage_key
            }
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            logger.warning(f"Cannot make object public ({error_code}): {e}")

            # Fall back to long-lived presigned URL if public access fails
            # This handles AccessDenied, AccessControlListNotSupported, etc.
            logger.info(f"Falling back to presigned URL for {storage_key}")
            return self.get_presigned_download_url(storage_key, expires_in=86400 * 7)

    def delete_document(self, storage_key: str) -> Dict[str, Any]:
        """
        Delete a document from S3.

        Args:
            storage_key: S3 object key

        Returns:
            Dict with success status
        """
        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=storage_key
            )

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

    def copy_document(
        self,
        source_key: str,
        dest_key: str,
        metadata: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Copy a document within S3.

        Args:
            source_key: Source object key
            dest_key: Destination object key
            metadata: Optional new metadata

        Returns:
            Dict with success status and new key
        """
        try:
            copy_source = {
                'Bucket': self.bucket_name,
                'Key': source_key
            }

            extra_args = {}
            if metadata:
                extra_args['Metadata'] = metadata
                extra_args['MetadataDirective'] = 'REPLACE'

            self.s3_client.copy_object(
                CopySource=copy_source,
                Bucket=self.bucket_name,
                Key=dest_key,
                **extra_args
            )

            return {
                "success": True,
                "source_key": source_key,
                "dest_key": dest_key
            }

        except ClientError as e:
            logger.error(f"Error copying document: {e}")
            return {
                "success": False,
                "error": "Internal server error"
            }

    def get_file_metadata(self, storage_key: str) -> Dict[str, Any]:
        """
        Get metadata for a file.

        Args:
            storage_key: S3 object key

        Returns:
            Dict with file metadata
        """
        return self.verify_upload(storage_key)

    def upload_file(
        self,
        storage_key: str,
        file_content: bytes,
        content_type: str,
        metadata: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Upload file content directly to S3.

        Args:
            storage_key: S3 object key
            file_content: File bytes to upload
            content_type: MIME type of the file
            metadata: Optional custom metadata

        Returns:
            Dict with success status and storage info
        """
        from io import BytesIO

        # Validate content type
        if content_type not in self.allowed_content_types:
            return {
                "success": False,
                "error": f"Content type '{content_type}' not allowed",
                "allowed_types": self.allowed_content_types
            }

        # Validate file size
        file_size = len(file_content)
        if file_size > self.max_file_size:
            return {
                "success": False,
                "error": f"File size {file_size} exceeds maximum {self.max_file_size} bytes"
            }

        try:
            extra_args = {
                'ContentType': content_type
            }

            if metadata:
                extra_args['Metadata'] = metadata

            # Upload using upload_fileobj for efficient streaming
            self.s3_client.upload_fileobj(
                BytesIO(file_content),
                self.bucket_name,
                storage_key,
                ExtraArgs=extra_args
            )

            logger.info(f"Uploaded {file_size} bytes to s3://{self.bucket_name}/{storage_key}")

            return {
                "success": True,
                "storage_key": storage_key,
                "bucket": self.bucket_name,
                "file_size": file_size,
                "content_type": content_type,
                "s3_uri": f"s3://{self.bucket_name}/{storage_key}"
            }

        except ClientError as e:
            logger.error(f"Error uploading file to S3: {e}")
            return {
                "success": False,
                "error": "Internal server error"
            }

    def download_file(self, storage_key: str) -> Dict[str, Any]:
        """
        Download file content directly from S3.

        Args:
            storage_key: S3 object key

        Returns:
            Dict with file content bytes and metadata
        """
        try:
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=storage_key
            )

            content = response['Body'].read()

            logger.info(f"Downloaded {len(content)} bytes from s3://{self.bucket_name}/{storage_key}")

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
                logger.warning(f"File not found in S3: {storage_key}")
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

    def move_file(
        self,
        source_key: str,
        dest_key: str,
        delete_source: bool = True
    ) -> Dict[str, Any]:
        """
        Move a file within S3 (copy then delete).

        Args:
            source_key: Source object key
            dest_key: Destination object key
            delete_source: Whether to delete source after copy

        Returns:
            Dict with success status
        """
        try:
            # Copy to new location
            copy_result = self.copy_document(source_key, dest_key)
            if not copy_result.get("success"):
                return copy_result

            # Delete source if requested
            if delete_source:
                delete_result = self.delete_document(source_key)
                if not delete_result.get("success"):
                    logger.warning(f"Failed to delete source after move: {source_key}")

            logger.info(f"Moved s3://{self.bucket_name}/{source_key} to {dest_key}")

            return {
                "success": True,
                "source_key": source_key,
                "dest_key": dest_key,
                "deleted_source": delete_source
            }

        except ClientError as e:
            logger.error(f"Error moving file: {e}")
            return {
                "success": False,
                "error": "Internal server error"
            }

    def generate_intake_key(
        self,
        email_intake_id: int,
        filename: str,
        organization_id: Optional[int] = None,
    ) -> str:
        """
        Generate storage key for document intake (temp storage).

        Format: org/{org_id}/intake/{email_intake_id}/{uuid}.{extension}
        Legacy (no org): intake/{email_intake_id}/{uuid}.{extension}

        Args:
            email_intake_id: Email intake record ID
            filename: Original filename
            organization_id: Organization ID for tenant isolation

        Returns:
            Storage key string
        """
        ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'bin'
        unique_id = uuid.uuid4().hex
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        org_prefix = f"org/{organization_id}/" if organization_id else ""
        return f"{org_prefix}intake/{email_intake_id}/{timestamp}_{unique_id}.{ext}"

    def generate_document_key(
        self,
        borrower_id: Optional[int],
        loan_id: Optional[int],
        doc_type: str,
        filename: str,
        organization_id: Optional[int] = None,
    ) -> str:
        """
        Generate permanent storage key for classified document.

        Format: org/{org_id}/documents/{borrower_id or 'unassigned'}/{loan_id or 'general'}/{doc_type}/{uuid}.{extension}
        Legacy (no org): documents/{borrower_id or 'unassigned'}/{loan_id or 'general'}/{doc_type}/{uuid}.{extension}

        Args:
            borrower_id: Borrower ID (optional)
            loan_id: Loan ID (optional)
            doc_type: Document type (e.g., 'W2', 'BANK_STATEMENT')
            filename: Original filename
            organization_id: Organization ID for tenant isolation

        Returns:
            Storage key string
        """
        ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'bin'
        unique_id = uuid.uuid4().hex

        borrower_folder = str(borrower_id) if borrower_id else 'unassigned'
        loan_folder = str(loan_id) if loan_id else 'general'

        org_prefix = f"org/{organization_id}/" if organization_id else ""
        return f"{org_prefix}documents/{borrower_folder}/{loan_folder}/{doc_type.lower()}/{unique_id}.{ext}"

    def validate_org_access(self, storage_key: str, organization_id: int) -> bool:
        """
        Verify the storage key belongs to the requesting organization.

        Args:
            storage_key: S3 object key to validate
            organization_id: Organization ID of the requesting user

        Returns:
            True if the key belongs to the org, False otherwise
        """
        if not organization_id:
            return False
        expected_prefix = f"org/{organization_id}/"
        # Allow access to org-prefixed keys that match, and legacy keys without org prefix
        if storage_key.startswith("org/"):
            return storage_key.startswith(expected_prefix)
        # Legacy keys (no org prefix) — allow access for backward compatibility
        return True

    def list_loan_documents(
        self,
        loan_id: int,
        folder: Optional[str] = None,
        max_keys: int = 100
    ) -> Dict[str, Any]:
        """
        List all documents for a loan.

        Args:
            loan_id: Loan ID
            folder: Optional subfolder (originals, compressed, previews)
            max_keys: Maximum number of keys to return

        Returns:
            Dict with list of document keys
        """
        prefix = f"documents/{loan_id}/"
        if folder:
            prefix += f"{folder}/"

        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix,
                MaxKeys=max_keys
            )

            documents = []
            for obj in response.get('Contents', []):
                documents.append({
                    'key': obj['Key'],
                    'size': obj['Size'],
                    'last_modified': obj['LastModified'].isoformat()
                })

            return {
                "success": True,
                "prefix": prefix,
                "documents": documents,
                "count": len(documents),
                "is_truncated": response.get('IsTruncated', False)
            }

        except ClientError as e:
            logger.error(f"Error listing documents: {e}")
            return {
                "success": False,
                "error": "Internal server error"
            }


# Singleton instance
_s3_service: Optional[PerenniaS3Service] = None


def get_s3_service() -> PerenniaS3Service:
    """Get or create the S3 service singleton."""
    global _s3_service
    if _s3_service is None:
        _s3_service = PerenniaS3Service()
    return _s3_service
