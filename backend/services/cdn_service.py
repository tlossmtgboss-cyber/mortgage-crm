"""
CDN Service for Perennia CRM

Provides CloudFront CDN integration for document and media delivery:
- URL signing for private content
- Cache invalidation
- CDN URL generation
- Integration with existing S3 service
"""

import os
import json
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
from urllib.parse import quote, urljoin

import boto3
from botocore.exceptions import ClientError
from botocore.signers import CloudFrontSigner

logger = logging.getLogger(__name__)


class CDNService:
    """
    CloudFront CDN service for document and media delivery.

    Features:
    - Signed URL generation for private content
    - Cache invalidation
    - URL transformation (S3 -> CDN)
    - Presigned URL generation through CloudFront
    """

    def __init__(
        self,
        distribution_id: Optional[str] = None,
        domain_name: Optional[str] = None,
        key_pair_id: Optional[str] = None,
        private_key_path: Optional[str] = None,
        private_key_string: Optional[str] = None,
        s3_bucket: Optional[str] = None
    ):
        """
        Initialize CDN service.

        Args:
            distribution_id: CloudFront distribution ID
            domain_name: CloudFront domain name (e.g., d1234.cloudfront.net)
            key_pair_id: CloudFront key pair ID for signed URLs
            private_key_path: Path to private key file for URL signing
            private_key_string: Private key as string (for environment variable)
            s3_bucket: S3 bucket name for origin
        """
        self.distribution_id = distribution_id or os.getenv("CLOUDFRONT_DISTRIBUTION_ID")
        self.domain_name = domain_name or os.getenv("CLOUDFRONT_DOMAIN_NAME")
        self.key_pair_id = key_pair_id or os.getenv("CLOUDFRONT_KEY_PAIR_ID")
        self.s3_bucket = s3_bucket or os.getenv("PERENNIA_S3_BUCKET", "perennia-docs")

        # Load private key for URL signing
        self._private_key = None
        if private_key_string:
            self._private_key = private_key_string
        elif private_key_path or os.getenv("CLOUDFRONT_PRIVATE_KEY_PATH"):
            key_path = private_key_path or os.getenv("CLOUDFRONT_PRIVATE_KEY_PATH")
            try:
                with open(key_path, 'r') as f:
                    self._private_key = f.read()
            except Exception as e:
                logger.warning(f"Could not load CloudFront private key: {e}")
        elif os.getenv("CLOUDFRONT_PRIVATE_KEY"):
            self._private_key = os.getenv("CLOUDFRONT_PRIVATE_KEY")

        # Initialize CloudFront client
        self.cloudfront_client = boto3.client('cloudfront')

        # CDN configuration
        self.default_expiry = 3600  # 1 hour
        self.enabled = bool(self.distribution_id and self.domain_name)

        if self.enabled:
            logger.info(f"CDN service initialized: {self.domain_name}")
        else:
            logger.info("CDN service running in passthrough mode (no CloudFront configured)")

    def _rsa_signer(self, message: bytes) -> bytes:
        """
        RSA signer for CloudFront signed URLs.

        Args:
            message: Message to sign

        Returns:
            RSA signature bytes
        """
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding

            private_key = serialization.load_pem_private_key(
                self._private_key.encode('utf-8'),
                password=None
            )

            return private_key.sign(
                message,
                padding.PKCS1v15(),
                hashes.SHA1()
            )
        except ImportError:
            logger.error("cryptography package required for signed URLs")
            raise

    def get_cdn_url(
        self,
        s3_key: str,
        expires_in: Optional[int] = None,
        signed: bool = False
    ) -> str:
        """
        Get CDN URL for an S3 object.

        Args:
            s3_key: S3 object key
            expires_in: Expiry time in seconds (for signed URLs)
            signed: Whether to generate a signed URL

        Returns:
            CDN URL string
        """
        if not self.enabled:
            # Fallback to direct S3 URL
            return f"https://{self.s3_bucket}.s3.amazonaws.com/{s3_key}"

        # Build base URL
        url = f"https://{self.domain_name}/{s3_key}"

        if signed and self._private_key and self.key_pair_id:
            return self._generate_signed_url(url, expires_in)

        return url

    def _generate_signed_url(
        self,
        url: str,
        expires_in: Optional[int] = None
    ) -> str:
        """
        Generate a signed CloudFront URL.

        Args:
            url: Base URL to sign
            expires_in: Expiry time in seconds

        Returns:
            Signed URL string
        """
        expires_in = expires_in or self.default_expiry
        expire_date = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        try:
            cloudfront_signer = CloudFrontSigner(self.key_pair_id, self._rsa_signer)
            signed_url = cloudfront_signer.generate_presigned_url(
                url,
                date_less_than=expire_date
            )
            return signed_url
        except Exception as e:
            logger.error(f"Error generating signed URL: {e}")
            # Return unsigned URL as fallback
            return url

    def transform_s3_url_to_cdn(
        self,
        s3_url: str,
        signed: bool = False,
        expires_in: Optional[int] = None
    ) -> str:
        """
        Transform an S3 URL to a CDN URL.

        Args:
            s3_url: Original S3 URL
            signed: Whether to sign the URL
            expires_in: Expiry time for signed URLs

        Returns:
            CDN URL string
        """
        if not self.enabled:
            return s3_url

        # Extract key from S3 URL
        # Handles both virtual-hosted and path-style URLs
        key = None

        if f"{self.s3_bucket}.s3" in s3_url:
            # Virtual-hosted style: https://bucket.s3.amazonaws.com/key
            parts = s3_url.split(f"{self.s3_bucket}.s3.amazonaws.com/")
            if len(parts) > 1:
                key = parts[1].split('?')[0]  # Remove query string
        elif f"s3.amazonaws.com/{self.s3_bucket}/" in s3_url:
            # Path style: https://s3.amazonaws.com/bucket/key
            parts = s3_url.split(f"/{self.s3_bucket}/")
            if len(parts) > 1:
                key = parts[1].split('?')[0]

        if key:
            return self.get_cdn_url(key, expires_in=expires_in, signed=signed)

        logger.warning(f"Could not extract key from S3 URL: {s3_url}")
        return s3_url

    def invalidate_cache(
        self,
        paths: List[str],
        caller_reference: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Invalidate CloudFront cache for specified paths.

        Args:
            paths: List of paths to invalidate (e.g., ['/documents/*', '/videos/123.mp4'])
            caller_reference: Unique reference for this invalidation

        Returns:
            Dict with invalidation details
        """
        if not self.enabled:
            return {
                "success": False,
                "error": "CDN not configured"
            }

        # Ensure paths start with /
        normalized_paths = [p if p.startswith('/') else f'/{p}' for p in paths]

        if not caller_reference:
            caller_reference = f"invalidation-{datetime.now(timezone.utc).timestamp()}"

        try:
            response = self.cloudfront_client.create_invalidation(
                DistributionId=self.distribution_id,
                InvalidationBatch={
                    'Paths': {
                        'Quantity': len(normalized_paths),
                        'Items': normalized_paths
                    },
                    'CallerReference': caller_reference
                }
            )

            invalidation = response.get('Invalidation', {})

            return {
                "success": True,
                "invalidation_id": invalidation.get('Id'),
                "status": invalidation.get('Status'),
                "paths": normalized_paths,
                "created_at": invalidation.get('CreateTime', datetime.now(timezone.utc)).isoformat()
            }

        except ClientError as e:
            logger.error(f"Error creating cache invalidation: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def invalidate_document(self, s3_key: str) -> Dict[str, Any]:
        """
        Invalidate cache for a specific document.

        Args:
            s3_key: S3 object key

        Returns:
            Dict with invalidation details
        """
        return self.invalidate_cache([f"/{s3_key}"])

    def invalidate_loan_documents(self, loan_id: int) -> Dict[str, Any]:
        """
        Invalidate cache for all documents of a loan.

        Args:
            loan_id: Loan ID

        Returns:
            Dict with invalidation details
        """
        return self.invalidate_cache([f"/documents/{loan_id}/*"])

    def get_distribution_status(self) -> Dict[str, Any]:
        """
        Get CloudFront distribution status.

        Returns:
            Dict with distribution details
        """
        if not self.enabled:
            return {
                "enabled": False,
                "message": "CDN not configured"
            }

        try:
            response = self.cloudfront_client.get_distribution(
                Id=self.distribution_id
            )

            distribution = response.get('Distribution', {})
            config = distribution.get('DistributionConfig', {})

            return {
                "enabled": True,
                "id": distribution.get('Id'),
                "domain_name": distribution.get('DomainName'),
                "status": distribution.get('Status'),
                "state": "Enabled" if config.get('Enabled') else "Disabled",
                "price_class": config.get('PriceClass'),
                "aliases": config.get('Aliases', {}).get('Items', []),
                "last_modified": distribution.get('LastModifiedTime', '').isoformat() if distribution.get('LastModifiedTime') else None
            }

        except ClientError as e:
            logger.error(f"Error getting distribution status: {e}")
            return {
                "enabled": True,
                "error": str(e)
            }

    def get_cache_statistics(self, days: int = 7) -> Dict[str, Any]:
        """
        Get CloudFront cache statistics.

        Args:
            days: Number of days to look back

        Returns:
            Dict with cache statistics
        """
        if not self.enabled:
            return {
                "enabled": False,
                "message": "CDN not configured"
            }

        try:
            cloudwatch = boto3.client('cloudwatch')

            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(days=days)

            metrics = {}
            metric_names = ['Requests', 'BytesDownloaded', 'BytesUploaded', 'TotalErrorRate']

            for metric_name in metric_names:
                response = cloudwatch.get_metric_statistics(
                    Namespace='AWS/CloudFront',
                    MetricName=metric_name,
                    Dimensions=[
                        {'Name': 'DistributionId', 'Value': self.distribution_id},
                        {'Name': 'Region', 'Value': 'Global'}
                    ],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=86400,  # Daily
                    Statistics=['Sum', 'Average']
                )

                datapoints = response.get('Datapoints', [])
                if datapoints:
                    total = sum(dp.get('Sum', 0) for dp in datapoints)
                    avg = sum(dp.get('Average', 0) for dp in datapoints) / len(datapoints)
                    metrics[metric_name.lower()] = {
                        "total": total,
                        "average": avg
                    }

            return {
                "enabled": True,
                "period_days": days,
                "metrics": metrics
            }

        except ClientError as e:
            logger.error(f"Error getting cache statistics: {e}")
            return {
                "enabled": True,
                "error": str(e)
            }

    def get_document_cdn_url(
        self,
        loan_id: int,
        storage_key: str,
        file_name: Optional[str] = None,
        expires_in: int = 300
    ) -> Dict[str, Any]:
        """
        Get CDN URL for a loan document.

        Args:
            loan_id: Loan ID
            storage_key: S3 storage key
            file_name: Original file name (for download)
            expires_in: Expiry time in seconds

        Returns:
            Dict with URL and metadata
        """
        # Determine if this should be a signed URL
        # Documents are private by default
        signed = self._private_key and self.key_pair_id

        cdn_url = self.get_cdn_url(storage_key, expires_in=expires_in, signed=signed)

        return {
            "success": True,
            "url": cdn_url,
            "storage_key": storage_key,
            "expires_in": expires_in if signed else None,
            "signed": signed,
            "cdn_enabled": self.enabled
        }

    def get_video_cdn_url(
        self,
        video_key: str,
        signed: bool = False,
        expires_in: int = 86400
    ) -> Dict[str, Any]:
        """
        Get CDN URL for a video.

        Args:
            video_key: S3 video key
            signed: Whether to sign the URL
            expires_in: Expiry time in seconds

        Returns:
            Dict with URL and metadata
        """
        cdn_url = self.get_cdn_url(video_key, expires_in=expires_in, signed=signed)

        return {
            "success": True,
            "url": cdn_url,
            "storage_key": video_key,
            "expires_in": expires_in if signed else None,
            "signed": signed,
            "cdn_enabled": self.enabled
        }


# =============================================================================
# Singleton instance
# =============================================================================

_cdn_service: Optional[CDNService] = None


def get_cdn_service() -> CDNService:
    """Get or create the CDN service singleton."""
    global _cdn_service
    if _cdn_service is None:
        _cdn_service = CDNService()
    return _cdn_service


def init_cdn_service(**kwargs) -> CDNService:
    """Initialize CDN service with custom configuration."""
    global _cdn_service
    _cdn_service = CDNService(**kwargs)
    return _cdn_service
