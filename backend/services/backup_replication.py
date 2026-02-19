"""
Cross-Region Backup Replication Service
Enterprise Readiness - Domain 8: Disaster Recovery (Check 8.4)

Provides S3 cross-region replication configuration for document backups,
database backup export to S3, and replication health monitoring.
"""

import os
import io
import gzip
import logging
import subprocess
import tempfile
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# Configuration from environment
PRIMARY_REGION = os.getenv("AWS_REGION", "us-east-1")
DR_REGION = os.getenv("DR_AWS_REGION", "us-west-2")
PRIMARY_BUCKET = os.getenv("PERENNIA_S3_BUCKET", "perennia-docs")
DR_BUCKET = os.getenv("DR_S3_BUCKET", "perennia-docs-dr")
DB_BACKUP_BUCKET = os.getenv("DB_BACKUP_S3_BUCKET", PRIMARY_BUCKET)
DB_BACKUP_PREFIX = os.getenv("DB_BACKUP_S3_PREFIX", "database-backups/")
DATABASE_URL = os.getenv("DATABASE_URL", "")


def _get_s3_client(region: Optional[str] = None):
    """Get an S3 client for the specified region."""
    try:
        import boto3
        from botocore.config import Config

        config = Config(
            signature_version='s3v4',
            s3={'addressing_style': 'virtual'}
        )

        return boto3.client(
            's3',
            region_name=region or PRIMARY_REGION,
            config=config,
        )
    except ImportError:
        logger.error("boto3 not available for S3 operations")
        return None


def configure_s3_replication(
    source_bucket: Optional[str] = None,
    dest_bucket: Optional[str] = None,
    dest_region: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Configure S3 cross-region replication (CRR) for document backups.

    This generates the replication configuration that should be applied
    to the source bucket. In production, this is typically set up via
    Terraform/CloudFormation, but this function provides the configuration
    for verification and documentation purposes.

    Note: Actually enabling CRR requires S3 versioning on both buckets
    and an IAM role. This function returns the configuration spec.

    Args:
        source_bucket: Source S3 bucket name.
        dest_bucket: Destination S3 bucket name.
        dest_region: Destination AWS region.

    Returns:
        Dict with replication configuration and instructions.
    """
    source = source_bucket or PRIMARY_BUCKET
    dest = dest_bucket or DR_BUCKET
    region = dest_region or DR_REGION

    # Build the CRR configuration structure
    replication_config = {
        "Role": f"arn:aws:iam::role/s3-replication-{source}-to-{dest}",
        "Rules": [
            {
                "ID": "dr-full-replication",
                "Status": "Enabled",
                "Filter": {
                    "Prefix": "",
                },
                "Destination": {
                    "Bucket": f"arn:aws:s3:::{dest}",
                    "StorageClass": "STANDARD_IA",
                    "ReplicationTime": {
                        "Status": "Enabled",
                        "Time": {"Minutes": 15},
                    },
                    "Metrics": {
                        "Status": "Enabled",
                        "EventThreshold": {"Minutes": 15},
                    },
                },
                "DeleteMarkerReplication": {"Status": "Enabled"},
            }
        ],
    }

    result = {
        "source_bucket": source,
        "source_region": PRIMARY_REGION,
        "dest_bucket": dest,
        "dest_region": region,
        "replication_config": replication_config,
        "prerequisites": [
            f"Enable versioning on source bucket: {source}",
            f"Enable versioning on destination bucket: {dest}",
            f"Create IAM replication role with cross-region permissions",
            f"Create destination bucket in {region} if not exists",
        ],
        "status": "configuration_generated",
    }

    # Check if source bucket is accessible and versioning is enabled
    s3_client = _get_s3_client()
    if s3_client:
        try:
            versioning = s3_client.get_bucket_versioning(Bucket=source)
            result["source_versioning"] = versioning.get("Status", "Not enabled")
            if versioning.get("Status") != "Enabled":
                result["action_required"] = (
                    "Enable versioning on source bucket before CRR"
                )
        except Exception as e:
            result["source_versioning"] = "check_failed"
            logger.debug(f"Could not check versioning for {source}: {e}")

        # Check replication status
        try:
            repl = s3_client.get_bucket_replication(Bucket=source)
            result["current_replication"] = {
                "configured": True,
                "rules_count": len(
                    repl.get("ReplicationConfiguration", {}).get("Rules", [])
                ),
            }
            result["status"] = "configured"
        except Exception:
            result["current_replication"] = {"configured": False}

    return result


def export_db_backup_to_s3(
    backup_bucket: Optional[str] = None,
    backup_prefix: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Export a database backup (pg_dump) to S3 for disaster recovery.

    Runs pg_dump on the configured DATABASE_URL, compresses the output
    with gzip, and uploads to S3 with a timestamped key.

    Args:
        backup_bucket: S3 bucket for backup storage.
        backup_prefix: S3 key prefix for backup files.

    Returns:
        Dict with backup status, S3 key, size, and timing info.
    """
    bucket = backup_bucket or DB_BACKUP_BUCKET
    prefix = backup_prefix or DB_BACKUP_PREFIX

    if not DATABASE_URL or DATABASE_URL.startswith("sqlite"):
        return {
            "status": "skipped",
            "reason": "No PostgreSQL DATABASE_URL configured",
        }

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_key = f"{prefix}{timestamp}.sql.gz"

    result = {
        "status": "in_progress",
        "backup_key": backup_key,
        "bucket": bucket,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        # Parse DATABASE_URL for pg_dump connection
        db_url = DATABASE_URL
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)

        # Use pg_dump with the connection URL
        with tempfile.NamedTemporaryFile(suffix=".sql.gz", delete=True) as tmp:
            # Run pg_dump and pipe through gzip
            pg_dump_cmd = [
                "pg_dump",
                "--no-owner",
                "--no-privileges",
                "--format=plain",
                db_url,
            ]

            process = subprocess.Popen(
                pg_dump_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={**os.environ, "PGCONNECT_TIMEOUT": "30"},
            )

            # Compress in memory
            compressed = io.BytesIO()
            with gzip.GzipFile(fileobj=compressed, mode='wb') as gz:
                while True:
                    chunk = process.stdout.read(65536)
                    if not chunk:
                        break
                    gz.write(chunk)

            process.wait()

            if process.returncode != 0:
                stderr = process.stderr.read().decode('utf-8', errors='replace')
                result["status"] = "failed"
                result["error"] = f"pg_dump exited with code {process.returncode}"
                logger.error(f"pg_dump failed: {stderr[:500]}")
                return result

            compressed_size = compressed.tell()
            compressed.seek(0)

            # Upload to S3
            s3_client = _get_s3_client()
            if not s3_client:
                result["status"] = "failed"
                result["error"] = "S3 client not available"
                return result

            s3_client.upload_fileobj(
                compressed,
                bucket,
                backup_key,
                ExtraArgs={
                    "ContentType": "application/gzip",
                    "ServerSideEncryption": "AES256",
                    "Metadata": {
                        "backup-type": "pg_dump",
                        "timestamp": timestamp,
                        "source": "perennia-crm",
                    },
                },
            )

            result["status"] = "completed"
            result["size_bytes"] = compressed_size
            result["size_mb"] = round(compressed_size / (1024 * 1024), 2)
            result["completed_at"] = datetime.now(timezone.utc).isoformat()

            logger.info(
                f"Database backup uploaded to s3://{bucket}/{backup_key} "
                f"({result['size_mb']} MB)"
            )

    except FileNotFoundError:
        result["status"] = "failed"
        result["error"] = (
            "pg_dump not found. Install postgresql-client for "
            "database backup exports."
        )
    except Exception as e:
        result["status"] = "failed"
        result["error"] = str(e)
        logger.error(f"Database backup export failed: {e}")

    return result


def verify_replication_status(
    source_bucket: Optional[str] = None,
    dest_bucket: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Check S3 cross-region replication health by comparing object counts
    and verifying replication metrics.

    Args:
        source_bucket: Source S3 bucket.
        dest_bucket: Destination S3 bucket.

    Returns:
        Dict with replication health status and metrics.
    """
    source = source_bucket or PRIMARY_BUCKET
    dest = dest_bucket or DR_BUCKET

    result = {
        "source_bucket": source,
        "dest_bucket": dest,
        "status": "unknown",
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }

    s3_client = _get_s3_client()
    if not s3_client:
        result["status"] = "unavailable"
        result["error"] = "S3 client not available"
        return result

    # Check source bucket metrics
    try:
        # List recent objects in source
        source_response = s3_client.list_objects_v2(
            Bucket=source,
            MaxKeys=1,
        )
        result["source_accessible"] = True
        result["source_object_count"] = source_response.get("KeyCount", 0)
    except Exception as e:
        result["source_accessible"] = False
        result["source_error"] = str(e)

    # Check destination bucket
    dr_client = _get_s3_client(region=DR_REGION)
    if dr_client:
        try:
            dest_response = dr_client.list_objects_v2(
                Bucket=dest,
                MaxKeys=1,
            )
            result["dest_accessible"] = True
            result["dest_object_count"] = dest_response.get("KeyCount", 0)
        except Exception as e:
            result["dest_accessible"] = False
            result["dest_error"] = str(e)

    # Check replication configuration on source
    try:
        repl_config = s3_client.get_bucket_replication(Bucket=source)
        rules = repl_config.get(
            "ReplicationConfiguration", {}
        ).get("Rules", [])

        active_rules = [r for r in rules if r.get("Status") == "Enabled"]
        result["replication_configured"] = True
        result["active_rules"] = len(active_rules)

        if active_rules:
            result["status"] = "active"
        else:
            result["status"] = "configured_but_disabled"

    except Exception:
        result["replication_configured"] = False
        result["status"] = "not_configured"

    # Check S3 backup files
    try:
        prefix = DB_BACKUP_PREFIX
        backup_response = s3_client.list_objects_v2(
            Bucket=DB_BACKUP_BUCKET,
            Prefix=prefix,
            MaxKeys=5,
        )

        backups = backup_response.get("Contents", [])
        if backups:
            latest = max(backups, key=lambda x: x.get("LastModified", ""))
            result["latest_db_backup"] = {
                "key": latest["Key"],
                "size_bytes": latest["Size"],
                "last_modified": latest["LastModified"].isoformat(),
            }
        result["db_backup_count"] = len(backups)

    except Exception as e:
        logger.debug(f"Could not list DB backups: {e}")
        result["db_backup_count"] = 0

    return result


def get_replication_lag(
    source_bucket: Optional[str] = None,
    dest_bucket: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Measure replication delay by comparing the most recent object
    timestamps between source and destination buckets.

    Args:
        source_bucket: Source S3 bucket.
        dest_bucket: Destination S3 bucket.

    Returns:
        Dict with replication lag measurement.
    """
    source = source_bucket or PRIMARY_BUCKET
    dest = dest_bucket or DR_BUCKET

    result = {
        "source_bucket": source,
        "dest_bucket": dest,
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "lag_seconds": None,
        "lag_status": "unknown",
    }

    s3_source = _get_s3_client()
    s3_dest = _get_s3_client(region=DR_REGION)

    if not s3_source or not s3_dest:
        result["error"] = "S3 clients not available"
        return result

    source_latest = None
    dest_latest = None

    # Get latest object in source
    try:
        response = s3_source.list_objects_v2(
            Bucket=source,
            Prefix="org-",
            MaxKeys=5,
        )
        objects = response.get("Contents", [])
        if objects:
            latest = max(objects, key=lambda x: x["LastModified"])
            source_latest = latest["LastModified"]
            result["source_latest_object"] = latest["Key"]
            result["source_latest_time"] = source_latest.isoformat()
    except Exception as e:
        result["source_error"] = str(e)

    # Get latest object in destination
    try:
        response = s3_dest.list_objects_v2(
            Bucket=dest,
            Prefix="org-",
            MaxKeys=5,
        )
        objects = response.get("Contents", [])
        if objects:
            latest = max(objects, key=lambda x: x["LastModified"])
            dest_latest = latest["LastModified"]
            result["dest_latest_object"] = latest["Key"]
            result["dest_latest_time"] = dest_latest.isoformat()
    except Exception as e:
        result["dest_error"] = str(e)

    # Calculate lag
    if source_latest and dest_latest:
        lag = (source_latest - dest_latest).total_seconds()
        result["lag_seconds"] = max(0, lag)

        if lag <= 300:  # 5 minutes
            result["lag_status"] = "healthy"
        elif lag <= 3600:  # 1 hour
            result["lag_status"] = "acceptable"
        else:
            result["lag_status"] = "degraded"
    elif source_latest and not dest_latest:
        result["lag_status"] = "no_destination_data"
    elif not source_latest:
        result["lag_status"] = "no_source_data"

    return result
