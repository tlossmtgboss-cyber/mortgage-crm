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
        folder: str = "originals"
    ) -> str:
        """
        Generate a unique storage key for a document.

        Format: documents/{loan_id}/{folder}/{uuid}.{extension}

        Args:
            loan_id: Loan ID for organization
            file_name: Original file name (for extension)
            folder: Subfolder (originals, compressed, previews)

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

        return f"documents/{loan_id}/{folder}/{unique_id}.{ext}"

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
                "error": str(e)
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
                "error": str(e)
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
                "error": str(e)
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
                "error": str(e)
            }

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
                "error": str(e)
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
                "error": str(e)
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
                "error": str(e)
            }


# Singleton instance
_s3_service: Optional[PerenniaS3Service] = None


def get_s3_service() -> PerenniaS3Service:
    """Get or create the S3 service singleton."""
    global _s3_service
    if _s3_service is None:
        _s3_service = PerenniaS3Service()
    return _s3_service
