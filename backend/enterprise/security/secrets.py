"""
Secret Management Service

Provides enterprise-grade secret management with support for:
- HashiCorp Vault integration
- AWS Secrets Manager integration
- Azure Key Vault integration
- Local encrypted secrets for development

Enterprise Features:
- Automatic secret rotation
- Secret versioning
- Access audit logging
- Lease management
- Dynamic secrets
"""

import os
import json
import base64
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum
from abc import ABC, abstractmethod
import hashlib
import secrets as python_secrets

logger = logging.getLogger(__name__)


class SecretProvider(str, Enum):
    """Supported secret providers"""
    LOCAL = "local"
    VAULT = "vault"
    AWS = "aws"
    AZURE = "azure"
    GCP = "gcp"


@dataclass
class Secret:
    """Container for a secret with metadata"""
    key: str
    value: str
    version: int
    created_at: datetime
    expires_at: Optional[datetime]
    metadata: Dict[str, Any]

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at


@dataclass
class SecretAccessLog:
    """Audit log entry for secret access"""
    secret_key: str
    accessor: str
    action: str
    timestamp: datetime
    success: bool
    error: Optional[str] = None


class SecretBackend(ABC):
    """Abstract base class for secret backends"""

    @abstractmethod
    async def get_secret(self, key: str, version: Optional[int] = None) -> Optional[Secret]:
        """Retrieve a secret"""
        pass

    @abstractmethod
    async def set_secret(self, key: str, value: str, metadata: Optional[Dict] = None) -> Secret:
        """Store a secret"""
        pass

    @abstractmethod
    async def delete_secret(self, key: str) -> bool:
        """Delete a secret"""
        pass

    @abstractmethod
    async def list_secrets(self, prefix: Optional[str] = None) -> List[str]:
        """List secret keys"""
        pass

    @abstractmethod
    async def rotate_secret(self, key: str, new_value: str) -> Secret:
        """Rotate a secret to a new value"""
        pass


class LocalSecretBackend(SecretBackend):
    """
    Local encrypted secret storage for development.

    NOT recommended for production - use Vault or cloud providers.
    """

    def __init__(self, encryption_key: Optional[str] = None, storage_path: Optional[str] = None):
        self.storage_path = storage_path or ".secrets.json"
        self._encryption_key = encryption_key or os.getenv("SECRET_ENCRYPTION_KEY", "dev-key")
        self._secrets: Dict[str, Dict] = {}
        self._load_secrets()

    def _load_secrets(self):
        """Load secrets from storage file"""
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, 'r') as f:
                    self._secrets = json.load(f)
            except Exception as e:
                logger.warning(f"Could not load secrets file: {e}")
                self._secrets = {}

    def _save_secrets(self):
        """Save secrets to storage file"""
        try:
            with open(self.storage_path, 'w') as f:
                json.dump(self._secrets, f)
        except Exception as e:
            logger.error(f"Could not save secrets file: {e}")

    def _encrypt(self, value: str) -> str:
        """Simple encryption for development (use proper encryption in production)"""
        # XOR-based obfuscation (NOT secure - for dev only)
        key_bytes = self._encryption_key.encode()
        value_bytes = value.encode()
        encrypted = bytes(v ^ key_bytes[i % len(key_bytes)] for i, v in enumerate(value_bytes))
        return base64.b64encode(encrypted).decode()

    def _decrypt(self, encrypted: str) -> str:
        """Simple decryption for development"""
        key_bytes = self._encryption_key.encode()
        encrypted_bytes = base64.b64decode(encrypted)
        decrypted = bytes(v ^ key_bytes[i % len(key_bytes)] for i, v in enumerate(encrypted_bytes))
        return decrypted.decode()

    async def get_secret(self, key: str, version: Optional[int] = None) -> Optional[Secret]:
        secret_data = self._secrets.get(key)
        if not secret_data:
            return None

        versions = secret_data.get("versions", [])
        if not versions:
            return None

        if version is not None:
            version_data = next((v for v in versions if v["version"] == version), None)
        else:
            version_data = versions[-1]  # Latest version

        if not version_data:
            return None

        return Secret(
            key=key,
            value=self._decrypt(version_data["value"]),
            version=version_data["version"],
            created_at=datetime.fromisoformat(version_data["created_at"]),
            expires_at=datetime.fromisoformat(version_data["expires_at"]) if version_data.get("expires_at") else None,
            metadata=version_data.get("metadata", {}),
        )

    async def set_secret(self, key: str, value: str, metadata: Optional[Dict] = None) -> Secret:
        if key not in self._secrets:
            self._secrets[key] = {"versions": []}

        versions = self._secrets[key]["versions"]
        new_version = len(versions) + 1

        now = datetime.now(timezone.utc)
        version_data = {
            "version": new_version,
            "value": self._encrypt(value),
            "created_at": now.isoformat(),
            "expires_at": None,
            "metadata": metadata or {},
        }

        versions.append(version_data)
        self._save_secrets()

        return Secret(
            key=key,
            value=value,
            version=new_version,
            created_at=now,
            expires_at=None,
            metadata=metadata or {},
        )

    async def delete_secret(self, key: str) -> bool:
        if key in self._secrets:
            del self._secrets[key]
            self._save_secrets()
            return True
        return False

    async def list_secrets(self, prefix: Optional[str] = None) -> List[str]:
        keys = list(self._secrets.keys())
        if prefix:
            keys = [k for k in keys if k.startswith(prefix)]
        return keys

    async def rotate_secret(self, key: str, new_value: str) -> Secret:
        return await self.set_secret(key, new_value)


class VaultSecretBackend(SecretBackend):
    """
    HashiCorp Vault secret backend.

    Supports:
    - KV v2 secrets engine
    - Dynamic database credentials
    - Token renewal
    - Namespace support
    """

    def __init__(
        self,
        url: Optional[str] = None,
        token: Optional[str] = None,
        namespace: Optional[str] = None,
        mount_point: str = "secret",
    ):
        self.url = url or os.getenv("VAULT_ADDR", "http://localhost:8200")
        self.token = token or os.getenv("VAULT_TOKEN")
        self.namespace = namespace or os.getenv("VAULT_NAMESPACE")
        self.mount_point = mount_point
        self._client = None

    def _get_client(self):
        """Get or create Vault client"""
        if self._client is None:
            try:
                import hvac
                self._client = hvac.Client(
                    url=self.url,
                    token=self.token,
                    namespace=self.namespace,
                )
                if not self._client.is_authenticated():
                    raise ValueError("Vault authentication failed")
            except ImportError:
                raise ImportError("hvac package required for Vault integration: pip install hvac")
        return self._client

    async def get_secret(self, key: str, version: Optional[int] = None) -> Optional[Secret]:
        try:
            client = self._get_client()
            response = client.secrets.kv.v2.read_secret_version(
                path=key,
                mount_point=self.mount_point,
                version=version,
            )

            data = response["data"]
            metadata = response["data"]["metadata"]

            return Secret(
                key=key,
                value=json.dumps(data["data"]) if isinstance(data["data"], dict) else str(data["data"]),
                version=metadata["version"],
                created_at=datetime.fromisoformat(metadata["created_time"].replace("Z", "+00:00")),
                expires_at=None,
                metadata=metadata,
            )
        except Exception as e:
            logger.error(f"Failed to get secret {key} from Vault: {e}")
            return None

    async def set_secret(self, key: str, value: str, metadata: Optional[Dict] = None) -> Secret:
        try:
            client = self._get_client()

            # Parse value as JSON if possible, otherwise wrap in dict
            try:
                secret_data = json.loads(value)
            except json.JSONDecodeError:
                secret_data = {"value": value}

            response = client.secrets.kv.v2.create_or_update_secret(
                path=key,
                secret=secret_data,
                mount_point=self.mount_point,
            )

            return Secret(
                key=key,
                value=value,
                version=response["data"]["version"],
                created_at=datetime.now(timezone.utc),
                expires_at=None,
                metadata=metadata or {},
            )
        except Exception as e:
            logger.error(f"Failed to set secret {key} in Vault: {e}")
            raise

    async def delete_secret(self, key: str) -> bool:
        try:
            client = self._get_client()
            client.secrets.kv.v2.delete_metadata_and_all_versions(
                path=key,
                mount_point=self.mount_point,
            )
            return True
        except Exception as e:
            logger.error(f"Failed to delete secret {key} from Vault: {e}")
            return False

    async def list_secrets(self, prefix: Optional[str] = None) -> List[str]:
        try:
            client = self._get_client()
            path = prefix or ""
            response = client.secrets.kv.v2.list_secrets(
                path=path,
                mount_point=self.mount_point,
            )
            return response["data"]["keys"]
        except Exception as e:
            logger.error(f"Failed to list secrets from Vault: {e}")
            return []

    async def rotate_secret(self, key: str, new_value: str) -> Secret:
        return await self.set_secret(key, new_value)

    async def get_database_credentials(self, role: str) -> Dict[str, str]:
        """Get dynamic database credentials from Vault"""
        try:
            client = self._get_client()
            response = client.secrets.database.generate_credentials(role=role)
            return {
                "username": response["data"]["username"],
                "password": response["data"]["password"],
                "lease_id": response["lease_id"],
                "lease_duration": response["lease_duration"],
            }
        except Exception as e:
            logger.error(f"Failed to get database credentials for role {role}: {e}")
            raise


class AWSSecretBackend(SecretBackend):
    """
    AWS Secrets Manager backend.

    Supports:
    - Secret versioning
    - Automatic rotation
    - Cross-region replication
    """

    def __init__(self, region: Optional[str] = None):
        self.region = region or os.getenv("AWS_REGION", "us-east-1")
        self._client = None

    def _get_client(self):
        """Get or create AWS client"""
        if self._client is None:
            try:
                import boto3
                self._client = boto3.client("secretsmanager", region_name=self.region)
            except ImportError:
                raise ImportError("boto3 package required for AWS integration: pip install boto3")
        return self._client

    async def get_secret(self, key: str, version: Optional[int] = None) -> Optional[Secret]:
        try:
            client = self._get_client()
            kwargs = {"SecretId": key}
            if version:
                kwargs["VersionId"] = str(version)

            response = client.get_secret_value(**kwargs)

            return Secret(
                key=key,
                value=response.get("SecretString", ""),
                version=int(response.get("VersionId", "1").split("-")[-1]) if response.get("VersionId") else 1,
                created_at=response.get("CreatedDate", datetime.now(timezone.utc)),
                expires_at=None,
                metadata={
                    "arn": response.get("ARN"),
                    "version_id": response.get("VersionId"),
                },
            )
        except Exception as e:
            logger.error(f"Failed to get secret {key} from AWS: {e}")
            return None

    async def set_secret(self, key: str, value: str, metadata: Optional[Dict] = None) -> Secret:
        try:
            client = self._get_client()

            try:
                # Try to update existing secret
                response = client.put_secret_value(
                    SecretId=key,
                    SecretString=value,
                )
            except client.exceptions.ResourceNotFoundException:
                # Create new secret
                response = client.create_secret(
                    Name=key,
                    SecretString=value,
                    Description=metadata.get("description", "") if metadata else "",
                )

            return Secret(
                key=key,
                value=value,
                version=1,
                created_at=datetime.now(timezone.utc),
                expires_at=None,
                metadata={"arn": response.get("ARN")},
            )
        except Exception as e:
            logger.error(f"Failed to set secret {key} in AWS: {e}")
            raise

    async def delete_secret(self, key: str) -> bool:
        try:
            client = self._get_client()
            client.delete_secret(
                SecretId=key,
                ForceDeleteWithoutRecovery=False,  # 30-day recovery window
            )
            return True
        except Exception as e:
            logger.error(f"Failed to delete secret {key} from AWS: {e}")
            return False

    async def list_secrets(self, prefix: Optional[str] = None) -> List[str]:
        try:
            client = self._get_client()
            paginator = client.get_paginator("list_secrets")

            secrets = []
            for page in paginator.paginate():
                for secret in page["SecretList"]:
                    name = secret["Name"]
                    if prefix is None or name.startswith(prefix):
                        secrets.append(name)

            return secrets
        except Exception as e:
            logger.error(f"Failed to list secrets from AWS: {e}")
            return []

    async def rotate_secret(self, key: str, new_value: str) -> Secret:
        return await self.set_secret(key, new_value)


class SecretManager:
    """
    Unified Secret Management Service

    Provides a consistent interface for secret management across
    multiple backends with features like:
    - Automatic backend selection
    - Secret caching
    - Access logging
    - Rotation scheduling
    """

    def __init__(
        self,
        provider: SecretProvider = SecretProvider.LOCAL,
        cache_ttl_seconds: int = 300,
        **backend_kwargs,
    ):
        self.provider = provider
        self.cache_ttl = timedelta(seconds=cache_ttl_seconds)
        self._cache: Dict[str, tuple] = {}  # key -> (secret, cached_at)
        self._access_logs: List[SecretAccessLog] = []

        # Initialize backend
        if provider == SecretProvider.LOCAL:
            self._backend = LocalSecretBackend(**backend_kwargs)
        elif provider == SecretProvider.VAULT:
            self._backend = VaultSecretBackend(**backend_kwargs)
        elif provider == SecretProvider.AWS:
            self._backend = AWSSecretBackend(**backend_kwargs)
        else:
            raise ValueError(f"Unsupported provider: {provider}")

        logger.info(f"Secret manager initialized with {provider.value} backend")

    async def get(
        self,
        key: str,
        default: Optional[str] = None,
        use_cache: bool = True,
        accessor: str = "system",
    ) -> Optional[str]:
        """
        Get a secret value.

        Args:
            key: Secret key
            default: Default value if secret not found
            use_cache: Whether to use cached value
            accessor: Identifier for audit logging

        Returns:
            Secret value or default
        """
        # Check cache
        if use_cache and key in self._cache:
            secret, cached_at = self._cache[key]
            if datetime.now(timezone.utc) - cached_at < self.cache_ttl:
                self._log_access(key, accessor, "get_cached", True)
                return secret.value

        # Fetch from backend
        try:
            secret = await self._backend.get_secret(key)
            if secret:
                self._cache[key] = (secret, datetime.now(timezone.utc))
                self._log_access(key, accessor, "get", True)
                return secret.value
            else:
                self._log_access(key, accessor, "get", False, "Not found")
                return default
        except Exception as e:
            self._log_access(key, accessor, "get", False, str(e))
            logger.error(f"Failed to get secret {key}: {e}")
            return default

    async def set(
        self,
        key: str,
        value: str,
        metadata: Optional[Dict] = None,
        accessor: str = "system",
    ) -> bool:
        """
        Set a secret value.

        Args:
            key: Secret key
            value: Secret value
            metadata: Optional metadata
            accessor: Identifier for audit logging

        Returns:
            True if successful
        """
        try:
            secret = await self._backend.set_secret(key, value, metadata)
            self._cache[key] = (secret, datetime.now(timezone.utc))
            self._log_access(key, accessor, "set", True)
            return True
        except Exception as e:
            self._log_access(key, accessor, "set", False, str(e))
            logger.error(f"Failed to set secret {key}: {e}")
            return False

    async def delete(self, key: str, accessor: str = "system") -> bool:
        """Delete a secret."""
        try:
            result = await self._backend.delete_secret(key)
            self._cache.pop(key, None)
            self._log_access(key, accessor, "delete", result)
            return result
        except Exception as e:
            self._log_access(key, accessor, "delete", False, str(e))
            logger.error(f"Failed to delete secret {key}: {e}")
            return False

    async def rotate(
        self,
        key: str,
        new_value: Optional[str] = None,
        accessor: str = "system",
    ) -> bool:
        """
        Rotate a secret to a new value.

        Args:
            key: Secret key
            new_value: New value (generated if not provided)
            accessor: Identifier for audit logging

        Returns:
            True if successful
        """
        if new_value is None:
            new_value = python_secrets.token_urlsafe(32)

        try:
            secret = await self._backend.rotate_secret(key, new_value)
            self._cache[key] = (secret, datetime.now(timezone.utc))
            self._log_access(key, accessor, "rotate", True)
            logger.info(f"Secret {key} rotated successfully")
            return True
        except Exception as e:
            self._log_access(key, accessor, "rotate", False, str(e))
            logger.error(f"Failed to rotate secret {key}: {e}")
            return False

    async def list(self, prefix: Optional[str] = None) -> List[str]:
        """List secret keys with optional prefix filter."""
        return await self._backend.list_secrets(prefix)

    def _log_access(
        self,
        key: str,
        accessor: str,
        action: str,
        success: bool,
        error: Optional[str] = None,
    ):
        """Log secret access for audit purposes."""
        log_entry = SecretAccessLog(
            secret_key=key,
            accessor=accessor,
            action=action,
            timestamp=datetime.now(timezone.utc),
            success=success,
            error=error,
        )
        self._access_logs.append(log_entry)

        # Keep only last 10000 entries in memory
        if len(self._access_logs) > 10000:
            self._access_logs = self._access_logs[-10000:]

    def get_access_logs(
        self,
        key: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[SecretAccessLog]:
        """Get secret access logs for auditing."""
        logs = self._access_logs

        if key:
            logs = [l for l in logs if l.secret_key == key]

        if since:
            logs = [l for l in logs if l.timestamp >= since]

        return logs[-limit:]

    def clear_cache(self):
        """Clear the secret cache."""
        self._cache.clear()
        logger.info("Secret cache cleared")


# Factory function for easy initialization
def create_secret_manager(
    provider: Optional[str] = None,
    **kwargs,
) -> SecretManager:
    """
    Create a SecretManager with automatic provider detection.

    Checks environment variables to determine the best provider:
    - VAULT_ADDR -> Vault
    - AWS_SECRET_ACCESS_KEY -> AWS
    - Otherwise -> Local
    """
    if provider:
        provider_enum = SecretProvider(provider.lower())
    elif os.getenv("VAULT_ADDR"):
        provider_enum = SecretProvider.VAULT
    elif os.getenv("AWS_SECRET_ACCESS_KEY"):
        provider_enum = SecretProvider.AWS
    else:
        provider_enum = SecretProvider.LOCAL
        logger.warning("Using local secret storage - not recommended for production")

    return SecretManager(provider=provider_enum, **kwargs)
