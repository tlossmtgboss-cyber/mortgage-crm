"""
SSL Certificate Service

Manages SSL/TLS certificates for custom domains using Let's Encrypt (ACME protocol).
Handles certificate issuance, renewal, and monitoring.

Features:
- Let's Encrypt integration via ACME protocol
- HTTP-01 and DNS-01 challenge support
- Automatic certificate renewal
- Certificate storage and retrieval
- Status monitoring and alerts

Usage:
    from services.ssl_certificate_service import ssl_certificate_service

    # Request a new certificate
    result = await ssl_certificate_service.request_certificate("example.com")

    # Check certificate status
    status = ssl_certificate_service.get_certificate_status("example.com")

    # Renew expiring certificates
    await ssl_certificate_service.renew_expiring_certificates()
"""

import os
import json
import logging
import asyncio
import hashlib
import base64
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import httpx
from cryptography import x509
from cryptography.x509.oid import NameOID, ExtensionOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, ec
from cryptography.hazmat.backends import default_backend
import josepy as jose

logger = logging.getLogger(__name__)


class CertificateStatus(str, Enum):
    """Status of SSL certificate."""
    PENDING = "pending"           # Certificate requested, awaiting issuance
    CHALLENGE_PENDING = "challenge_pending"  # Waiting for challenge verification
    ISSUED = "issued"             # Certificate issued and active
    EXPIRED = "expired"           # Certificate has expired
    REVOKED = "revoked"           # Certificate was revoked
    FAILED = "failed"             # Certificate issuance failed
    RENEWING = "renewing"         # Certificate renewal in progress


class ChallengeType(str, Enum):
    """ACME challenge types."""
    HTTP_01 = "http-01"           # HTTP file-based challenge
    DNS_01 = "dns-01"             # DNS TXT record challenge
    TLS_ALPN_01 = "tls-alpn-01"   # TLS ALPN challenge


@dataclass
class CertificateInfo:
    """Information about an SSL certificate."""
    domain: str
    status: CertificateStatus
    issued_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    issuer: Optional[str] = None
    serial_number: Optional[str] = None
    fingerprint_sha256: Optional[str] = None
    san_domains: List[str] = field(default_factory=list)
    challenge_type: Optional[ChallengeType] = None
    challenge_token: Optional[str] = None
    challenge_response: Optional[str] = None
    error_message: Optional[str] = None
    last_check: Optional[datetime] = None
    auto_renew: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "domain": self.domain,
            "status": self.status.value,
            "issued_at": self.issued_at.isoformat() if self.issued_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "issuer": self.issuer,
            "serial_number": self.serial_number,
            "fingerprint_sha256": self.fingerprint_sha256,
            "san_domains": self.san_domains,
            "days_until_expiry": self.days_until_expiry,
            "is_valid": self.is_valid,
            "needs_renewal": self.needs_renewal,
            "error_message": self.error_message,
            "last_check": self.last_check.isoformat() if self.last_check else None,
            "auto_renew": self.auto_renew
        }

    @property
    def days_until_expiry(self) -> Optional[int]:
        if not self.expires_at:
            return None
        delta = self.expires_at - datetime.now(timezone.utc)
        return max(0, delta.days)

    @property
    def is_valid(self) -> bool:
        if self.status != CertificateStatus.ISSUED:
            return False
        if not self.expires_at:
            return False
        return datetime.now(timezone.utc) < self.expires_at

    @property
    def needs_renewal(self) -> bool:
        """Check if certificate needs renewal (within 30 days of expiry)."""
        if not self.expires_at:
            return True
        days_left = self.days_until_expiry
        return days_left is not None and days_left <= 30


@dataclass
class ACMEChallenge:
    """ACME challenge information."""
    type: ChallengeType
    token: str
    key_authorization: str
    url: str
    status: str

    # For HTTP-01 challenge
    http_path: Optional[str] = None
    http_content: Optional[str] = None

    # For DNS-01 challenge
    dns_record_name: Optional[str] = None
    dns_record_value: Optional[str] = None


class SSLCertificateService:
    """
    Service for managing SSL certificates via Let's Encrypt.

    Supports both staging and production ACME environments.
    Uses HTTP-01 or DNS-01 challenges for domain validation.
    """

    # Let's Encrypt ACME endpoints
    ACME_DIRECTORY_STAGING = "https://acme-staging-v02.api.letsencrypt.org/directory"
    ACME_DIRECTORY_PRODUCTION = "https://acme-v02.api.letsencrypt.org/directory"

    # Certificate renewal threshold (days before expiry)
    RENEWAL_THRESHOLD_DAYS = 30

    # Default certificate validity (Let's Encrypt issues 90-day certs)
    DEFAULT_VALIDITY_DAYS = 90

    def __init__(
        self,
        use_production: bool = None,
        account_email: Optional[str] = None,
        storage_path: Optional[str] = None
    ):
        """
        Initialize SSL Certificate Service.

        Args:
            use_production: Use production ACME endpoint (default: from env)
            account_email: Email for ACME account registration
            storage_path: Path to store certificates and keys
        """
        # Determine environment
        if use_production is None:
            use_production = os.getenv("SSL_USE_PRODUCTION", "false").lower() == "true"

        self.use_production = use_production
        self.acme_directory = (
            self.ACME_DIRECTORY_PRODUCTION if use_production
            else self.ACME_DIRECTORY_STAGING
        )

        # Account email for Let's Encrypt notifications
        self.account_email = account_email or os.getenv(
            "SSL_ACCOUNT_EMAIL",
            "ssl@perenniaai.com"
        )

        # Storage path for certificates
        self.storage_path = Path(storage_path or os.getenv(
            "SSL_STORAGE_PATH",
            "/tmp/ssl_certificates"
        ))
        self.storage_path.mkdir(parents=True, exist_ok=True)

        # ACME account key and registration
        self._account_key = None
        self._account_url = None
        self._directory_cache = None

        # Certificate cache
        self._cert_cache: Dict[str, CertificateInfo] = {}

        # HTTP client for ACME requests
        self._http_client = None

        logger.info(
            f"SSL Certificate Service initialized "
            f"(production={use_production}, email={self.account_email})"
        )

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True
            )
        return self._http_client

    async def _get_directory(self) -> Dict[str, str]:
        """Fetch and cache ACME directory."""
        if self._directory_cache is None:
            client = await self._get_http_client()
            response = await client.get(self.acme_directory)
            response.raise_for_status()
            self._directory_cache = response.json()
            logger.debug(f"Fetched ACME directory: {list(self._directory_cache.keys())}")
        return self._directory_cache

    def _get_or_create_account_key(self) -> rsa.RSAPrivateKey:
        """Get or create ACME account private key."""
        if self._account_key is not None:
            return self._account_key

        key_path = self.storage_path / "account_key.pem"

        if key_path.exists():
            # Load existing key
            with open(key_path, "rb") as f:
                self._account_key = serialization.load_pem_private_key(
                    f.read(),
                    password=None,
                    backend=default_backend()
                )
            logger.debug("Loaded existing ACME account key")
        else:
            # Generate new key
            self._account_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
                backend=default_backend()
            )
            # Save key
            with open(key_path, "wb") as f:
                f.write(self._account_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption()
                ))
            os.chmod(key_path, 0o600)
            logger.info("Generated new ACME account key")

        return self._account_key

    def _create_jws_header(self, url: str, use_kid: bool = False) -> Dict:
        """Create JWS protected header for ACME requests."""
        account_key = self._get_or_create_account_key()

        header = {
            "alg": "RS256",
            "url": url,
        }

        if use_kid and self._account_url:
            header["kid"] = self._account_url
        else:
            # Include JWK for new account or when no kid
            public_key = account_key.public_key()
            public_numbers = public_key.public_numbers()
            header["jwk"] = {
                "kty": "RSA",
                "n": self._b64_encode(
                    public_numbers.n.to_bytes(
                        (public_numbers.n.bit_length() + 7) // 8, 'big'
                    )
                ),
                "e": self._b64_encode(
                    public_numbers.e.to_bytes(
                        (public_numbers.e.bit_length() + 7) // 8, 'big'
                    )
                )
            }

        return header

    def _b64_encode(self, data: bytes) -> str:
        """Base64 URL-safe encode without padding."""
        return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')

    def _b64_decode(self, data: str) -> bytes:
        """Base64 URL-safe decode with padding restoration."""
        padding = 4 - len(data) % 4
        if padding != 4:
            data += '=' * padding
        return base64.urlsafe_b64decode(data)

    async def _acme_request(
        self,
        url: str,
        payload: Optional[Dict] = None,
        use_kid: bool = True
    ) -> Tuple[Dict, Dict]:
        """
        Make a signed ACME request.

        Returns:
            Tuple of (response_json, response_headers)
        """
        client = await self._get_http_client()

        # Get nonce
        directory = await self._get_directory()
        nonce_response = await client.head(directory["newNonce"])
        nonce = nonce_response.headers["Replay-Nonce"]

        # Create signed request
        protected = self._create_jws_header(url, use_kid=use_kid)
        protected["nonce"] = nonce

        protected_b64 = self._b64_encode(json.dumps(protected).encode())

        if payload is None:
            payload_b64 = ""
        else:
            payload_b64 = self._b64_encode(json.dumps(payload).encode())

        # Sign
        account_key = self._get_or_create_account_key()
        signing_input = f"{protected_b64}.{payload_b64}".encode()

        from cryptography.hazmat.primitives.asymmetric import padding
        signature = account_key.sign(
            signing_input,
            padding.PKCS1v15(),
            hashes.SHA256()
        )
        signature_b64 = self._b64_encode(signature)

        # Make request
        jws = {
            "protected": protected_b64,
            "payload": payload_b64,
            "signature": signature_b64
        }

        response = await client.post(
            url,
            json=jws,
            headers={"Content-Type": "application/jose+json"}
        )

        # Parse response
        try:
            response_json = response.json()
        except Exception as e:
            logger.exception(f"Failed to parse ACME response as JSON: {e}")
            response_json = {}

        return response_json, dict(response.headers)

    async def register_account(self) -> str:
        """
        Register or retrieve ACME account.

        Returns:
            Account URL
        """
        if self._account_url:
            return self._account_url

        directory = await self._get_directory()

        payload = {
            "termsOfServiceAgreed": True,
            "contact": [f"mailto:{self.account_email}"]
        }

        response, headers = await self._acme_request(
            directory["newAccount"],
            payload,
            use_kid=False
        )

        self._account_url = headers.get("Location")
        logger.info(f"ACME account registered/retrieved: {self._account_url}")

        return self._account_url

    async def request_certificate(
        self,
        domain: str,
        challenge_type: ChallengeType = ChallengeType.HTTP_01,
        san_domains: Optional[List[str]] = None
    ) -> CertificateInfo:
        """
        Request a new SSL certificate for a domain.

        Args:
            domain: Primary domain for the certificate
            challenge_type: Type of ACME challenge to use
            san_domains: Additional Subject Alternative Names

        Returns:
            CertificateInfo with challenge details or issued certificate
        """
        logger.info(f"Requesting certificate for {domain}")

        # Ensure account is registered
        await self.register_account()

        # Create order
        directory = await self._get_directory()

        identifiers = [{"type": "dns", "value": domain}]
        if san_domains:
            for san in san_domains:
                if san != domain:
                    identifiers.append({"type": "dns", "value": san})

        order_payload = {"identifiers": identifiers}

        order_response, order_headers = await self._acme_request(
            directory["newOrder"],
            order_payload
        )

        order_url = order_headers.get("Location")
        logger.debug(f"Created order: {order_url}")

        # Get authorization challenges
        challenges = []
        for authz_url in order_response.get("authorizations", []):
            authz_response, _ = await self._acme_request(authz_url, None)

            for challenge in authz_response.get("challenges", []):
                if challenge["type"] == challenge_type.value:
                    # Compute key authorization
                    account_key = self._get_or_create_account_key()
                    public_key = account_key.public_key()
                    public_numbers = public_key.public_numbers()

                    jwk = {
                        "kty": "RSA",
                        "n": self._b64_encode(
                            public_numbers.n.to_bytes(
                                (public_numbers.n.bit_length() + 7) // 8, 'big'
                            )
                        ),
                        "e": self._b64_encode(
                            public_numbers.e.to_bytes(
                                (public_numbers.e.bit_length() + 7) // 8, 'big'
                            )
                        )
                    }

                    jwk_json = json.dumps(jwk, sort_keys=True, separators=(',', ':'))
                    thumbprint = self._b64_encode(
                        hashlib.sha256(jwk_json.encode()).digest()
                    )

                    token = challenge["token"]
                    key_authorization = f"{token}.{thumbprint}"

                    acme_challenge = ACMEChallenge(
                        type=challenge_type,
                        token=token,
                        key_authorization=key_authorization,
                        url=challenge["url"],
                        status=challenge["status"]
                    )

                    if challenge_type == ChallengeType.HTTP_01:
                        acme_challenge.http_path = f"/.well-known/acme-challenge/{token}"
                        acme_challenge.http_content = key_authorization

                    elif challenge_type == ChallengeType.DNS_01:
                        # DNS-01 requires base64url(sha256(keyAuthorization))
                        dns_value = self._b64_encode(
                            hashlib.sha256(key_authorization.encode()).digest()
                        )
                        acme_challenge.dns_record_name = f"_acme-challenge.{domain}"
                        acme_challenge.dns_record_value = dns_value

                    challenges.append(acme_challenge)
                    break

        # Create certificate info
        cert_info = CertificateInfo(
            domain=domain,
            status=CertificateStatus.CHALLENGE_PENDING,
            san_domains=san_domains or [],
            challenge_type=challenge_type,
            last_check=datetime.now(timezone.utc)
        )

        # Store challenge info for later verification
        if challenges:
            challenge = challenges[0]
            cert_info.challenge_token = challenge.token
            cert_info.challenge_response = challenge.key_authorization

            # Store additional challenge details in cache
            self._cert_cache[domain] = cert_info
            self._cert_cache[f"{domain}_order_url"] = order_url
            self._cert_cache[f"{domain}_challenges"] = challenges

        logger.info(f"Certificate request created for {domain}, awaiting challenge")

        return cert_info

    def get_challenge_details(self, domain: str) -> Optional[ACMEChallenge]:
        """Get challenge details for a pending certificate request."""
        challenges = self._cert_cache.get(f"{domain}_challenges", [])
        return challenges[0] if challenges else None

    async def complete_challenge(self, domain: str) -> CertificateInfo:
        """
        Complete the ACME challenge and issue certificate.

        Call this after setting up the challenge response
        (HTTP file or DNS record).
        """
        logger.info(f"Completing challenge for {domain}")

        cert_info = self._cert_cache.get(domain)
        if not cert_info:
            raise ValueError(f"No pending certificate request for {domain}")

        challenges = self._cert_cache.get(f"{domain}_challenges", [])
        order_url = self._cert_cache.get(f"{domain}_order_url")

        if not challenges or not order_url:
            raise ValueError(f"Missing challenge or order info for {domain}")

        challenge = challenges[0]

        # Notify ACME server that challenge is ready
        await self._acme_request(challenge.url, {})

        # Poll for authorization status
        max_attempts = 30
        for attempt in range(max_attempts):
            await asyncio.sleep(2)

            order_response, _ = await self._acme_request(order_url, None)
            status = order_response.get("status")

            logger.debug(f"Order status for {domain}: {status} (attempt {attempt + 1})")

            if status == "ready":
                # Ready to finalize
                break
            elif status == "valid":
                # Already finalized
                break
            elif status == "invalid":
                cert_info.status = CertificateStatus.FAILED
                cert_info.error_message = "Challenge validation failed"
                return cert_info

        if status not in ("ready", "valid"):
            cert_info.status = CertificateStatus.FAILED
            cert_info.error_message = f"Challenge timed out (status: {status})"
            return cert_info

        # Generate CSR if order is ready
        if status == "ready":
            csr, private_key = self._generate_csr(domain, cert_info.san_domains)

            # Finalize order
            finalize_url = order_response.get("finalize")
            csr_der = csr.public_bytes(serialization.Encoding.DER)
            csr_b64 = self._b64_encode(csr_der)

            await self._acme_request(finalize_url, {"csr": csr_b64})

            # Save private key
            key_path = self.storage_path / f"{domain}.key"
            with open(key_path, "wb") as f:
                f.write(private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption()
                ))
            os.chmod(key_path, 0o600)

            # Poll for certificate
            for attempt in range(max_attempts):
                await asyncio.sleep(2)
                order_response, _ = await self._acme_request(order_url, None)

                if order_response.get("status") == "valid":
                    break

        # Download certificate
        certificate_url = order_response.get("certificate")
        if certificate_url:
            client = await self._get_http_client()
            cert_response = await client.get(certificate_url)
            cert_pem = cert_response.text

            # Save certificate
            cert_path = self.storage_path / f"{domain}.crt"
            with open(cert_path, "w") as f:
                f.write(cert_pem)

            # Parse certificate for info
            cert_info = self._parse_certificate(domain, cert_pem)
            cert_info.status = CertificateStatus.ISSUED

            self._cert_cache[domain] = cert_info
            logger.info(f"Certificate issued for {domain}, expires {cert_info.expires_at}")

        return cert_info

    def _generate_csr(
        self,
        domain: str,
        san_domains: Optional[List[str]] = None
    ) -> Tuple[x509.CertificateSigningRequest, rsa.RSAPrivateKey]:
        """Generate a Certificate Signing Request."""
        # Generate private key
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )

        # Build CSR
        builder = x509.CertificateSigningRequestBuilder()
        builder = builder.subject_name(x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, domain)
        ]))

        # Add SANs
        all_domains = [domain]
        if san_domains:
            all_domains.extend([d for d in san_domains if d != domain])

        san_list = [x509.DNSName(d) for d in all_domains]
        builder = builder.add_extension(
            x509.SubjectAlternativeName(san_list),
            critical=False
        )

        # Sign CSR
        csr = builder.sign(private_key, hashes.SHA256(), default_backend())

        return csr, private_key

    def _parse_certificate(self, domain: str, cert_pem: str) -> CertificateInfo:
        """Parse a PEM certificate and extract information."""
        # Parse the first certificate in the chain
        cert = x509.load_pem_x509_certificate(
            cert_pem.encode(),
            default_backend()
        )

        # Extract SANs
        san_domains = []
        try:
            san_ext = cert.extensions.get_extension_for_oid(
                ExtensionOID.SUBJECT_ALTERNATIVE_NAME
            )
            for name in san_ext.value:
                if isinstance(name, x509.DNSName):
                    san_domains.append(name.value)
        except x509.ExtensionNotFound:
            pass

        # Get issuer
        issuer_parts = []
        for attr in cert.issuer:
            issuer_parts.append(f"{attr.oid._name}={attr.value}")
        issuer = ", ".join(issuer_parts)

        # Compute fingerprint
        fingerprint = cert.fingerprint(hashes.SHA256()).hex()

        return CertificateInfo(
            domain=domain,
            status=CertificateStatus.ISSUED,
            issued_at=cert.not_valid_before_utc if hasattr(cert, 'not_valid_before_utc') else cert.not_valid_before,
            expires_at=cert.not_valid_after_utc if hasattr(cert, 'not_valid_after_utc') else cert.not_valid_after,
            issuer=issuer,
            serial_number=format(cert.serial_number, 'x'),
            fingerprint_sha256=fingerprint,
            san_domains=san_domains,
            last_check=datetime.now(timezone.utc)
        )

    def get_certificate_status(self, domain: str) -> CertificateInfo:
        """Get current status of a domain's certificate."""
        # Check cache
        if domain in self._cert_cache:
            return self._cert_cache[domain]

        # Check stored certificate
        cert_path = self.storage_path / f"{domain}.crt"
        if cert_path.exists():
            with open(cert_path) as f:
                cert_pem = f.read()
            return self._parse_certificate(domain, cert_pem)

        # No certificate found
        return CertificateInfo(
            domain=domain,
            status=CertificateStatus.PENDING,
            last_check=datetime.now(timezone.utc)
        )

    def get_certificate_files(self, domain: str) -> Optional[Dict[str, str]]:
        """
        Get paths to certificate and key files.

        Returns:
            Dict with 'certificate' and 'private_key' paths, or None
        """
        cert_path = self.storage_path / f"{domain}.crt"
        key_path = self.storage_path / f"{domain}.key"

        if cert_path.exists() and key_path.exists():
            return {
                "certificate": str(cert_path),
                "private_key": str(key_path)
            }
        return None

    async def renew_expiring_certificates(
        self,
        threshold_days: int = None
    ) -> List[CertificateInfo]:
        """
        Renew all certificates expiring within threshold.

        Returns:
            List of renewed certificate info
        """
        threshold = threshold_days or self.RENEWAL_THRESHOLD_DAYS
        renewed = []

        # Find all stored certificates
        for cert_file in self.storage_path.glob("*.crt"):
            domain = cert_file.stem

            with open(cert_file) as f:
                cert_pem = f.read()

            cert_info = self._parse_certificate(domain, cert_pem)

            if cert_info.needs_renewal:
                logger.info(f"Renewing certificate for {domain} (expires in {cert_info.days_until_expiry} days)")

                try:
                    # Re-request certificate
                    new_cert = await self.request_certificate(
                        domain,
                        san_domains=cert_info.san_domains
                    )
                    renewed.append(new_cert)
                except Exception as e:
                    logger.error(f"Failed to renew certificate for {domain}: {e}")

        return renewed

    async def check_domain_ssl(self, domain: str) -> Dict[str, Any]:
        """
        Check current SSL status of a live domain.

        Makes an HTTPS connection to verify SSL is working.
        """
        import ssl
        import socket

        result = {
            "domain": domain,
            "ssl_working": False,
            "certificate": None,
            "errors": []
        }

        try:
            context = ssl.create_default_context()

            with socket.create_connection((domain, 443), timeout=10) as sock:
                with context.wrap_socket(sock, server_hostname=domain) as ssock:
                    cert = ssock.getpeercert()

                    result["ssl_working"] = True
                    result["certificate"] = {
                        "subject": dict(x[0] for x in cert.get('subject', [])),
                        "issuer": dict(x[0] for x in cert.get('issuer', [])),
                        "not_before": cert.get('notBefore'),
                        "not_after": cert.get('notAfter'),
                        "san": [
                            x[1] for x in cert.get('subjectAltName', [])
                            if x[0] == 'DNS'
                        ]
                    }

        except ssl.SSLError as e:
            result["errors"].append(f"SSL error: {str(e)}")
        except socket.timeout:
            result["errors"].append("Connection timed out")
        except socket.gaierror as e:
            result["errors"].append(f"DNS resolution failed: {str(e)}")
        except Exception as e:
            result["errors"].append(f"Connection failed: {str(e)}")

        return result

    async def close(self):
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None


# Singleton instance
ssl_certificate_service = SSLCertificateService()
