"""
DNS Verification Service

Provides DNS record verification for custom domain ownership.
Supports multiple verification methods:
1. TXT record verification (domain ownership proof)
2. CNAME record verification (points to our service)
3. A record verification (direct IP pointing)

Usage:
    from services.dns_verification_service import dns_verification_service

    # Generate verification token for a domain
    token = dns_verification_service.generate_verification_token("example.com")

    # Check if TXT record exists
    result = dns_verification_service.verify_txt_record("example.com", token)

    # Check CNAME/A record configuration
    result = dns_verification_service.verify_dns_configuration("example.com")
"""

import dns.resolver
import dns.exception
import hashlib
import secrets
import logging
import socket
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class VerificationMethod(str, Enum):
    """Supported DNS verification methods."""
    TXT_RECORD = "txt_record"
    CNAME_RECORD = "cname_record"
    A_RECORD = "a_record"
    HTTP_FILE = "http_file"  # Future: /.well-known/domain-verification


class VerificationStatus(str, Enum):
    """Status of verification attempt."""
    VERIFIED = "verified"
    PENDING = "pending"
    FAILED = "failed"
    ERROR = "error"


@dataclass
class VerificationResult:
    """Result of a DNS verification attempt."""
    success: bool
    status: VerificationStatus
    method: VerificationMethod
    message: str
    details: Dict[str, Any] = None
    records_found: List[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "status": self.status.value,
            "method": self.method.value,
            "message": self.message,
            "details": self.details or {},
            "records_found": self.records_found or []
        }


class DNSVerificationService:
    """
    Service for verifying DNS records for custom domain ownership.

    Verification Flow:
    1. User adds domain to system
    2. System generates unique verification token
    3. User adds TXT record: _perennia-verify.domain.com -> token
    4. System verifies TXT record exists with correct token
    5. System also verifies CNAME/A record points to our infrastructure
    """

    # TXT record prefix for domain verification
    TXT_RECORD_PREFIX = "_perennia-verify"

    # Expected CNAME target (users should point their domain here)
    EXPECTED_CNAME_TARGETS = [
        "cname.vercel-dns.com",
        "cname.perenniaai.com",
        "proxy.perenniaai.com",
    ]

    # Expected A record IPs (Vercel's IP addresses)
    EXPECTED_A_RECORDS = [
        "76.76.21.21",  # Vercel
        "76.76.21.22",  # Vercel
        "76.76.21.164", # Vercel
    ]

    # DNS resolver timeout in seconds
    DNS_TIMEOUT = 10

    def __init__(self):
        """Initialize DNS resolver with custom settings."""
        self.resolver = dns.resolver.Resolver()
        self.resolver.timeout = self.DNS_TIMEOUT
        self.resolver.lifetime = self.DNS_TIMEOUT

        # Use reliable public DNS servers
        self.resolver.nameservers = [
            "8.8.8.8",      # Google DNS
            "8.8.4.4",      # Google DNS
            "1.1.1.1",      # Cloudflare DNS
            "1.0.0.1",      # Cloudflare DNS
        ]

    def generate_verification_token(self, domain: str) -> str:
        """
        Generate a unique verification token for a domain.

        The token is a 32-character hex string that users must add
        as a TXT record to prove domain ownership.

        Args:
            domain: The domain to generate token for

        Returns:
            32-character verification token
        """
        # Create a unique token using random bytes and domain
        random_bytes = secrets.token_bytes(16)
        domain_bytes = domain.lower().encode('utf-8')

        # Hash to create deterministic-looking but unique token
        combined = random_bytes + domain_bytes
        token = hashlib.sha256(combined).hexdigest()[:32]

        return f"perennia-verify={token}"

    def get_txt_record_name(self, domain: str) -> str:
        """
        Get the full TXT record name for verification.

        Args:
            domain: The domain being verified

        Returns:
            Full TXT record name (e.g., _perennia-verify.example.com)
        """
        return f"{self.TXT_RECORD_PREFIX}.{domain}"

    def verify_txt_record(
        self,
        domain: str,
        expected_token: str
    ) -> VerificationResult:
        """
        Verify that a TXT record exists with the expected token.

        Args:
            domain: The domain to verify
            expected_token: The token that should be in the TXT record

        Returns:
            VerificationResult with status and details
        """
        txt_record_name = self.get_txt_record_name(domain)

        try:
            logger.info(f"Checking TXT record for {txt_record_name}")

            answers = self.resolver.resolve(txt_record_name, 'TXT')
            found_records = []

            for rdata in answers:
                # TXT records can have multiple strings, join them
                txt_value = ''.join([s.decode('utf-8') for s in rdata.strings])
                found_records.append(txt_value)

                # Check if this record matches our expected token
                if txt_value.strip() == expected_token.strip():
                    logger.info(f"TXT verification successful for {domain}")
                    return VerificationResult(
                        success=True,
                        status=VerificationStatus.VERIFIED,
                        method=VerificationMethod.TXT_RECORD,
                        message=f"TXT record verified for {domain}",
                        details={
                            "record_name": txt_record_name,
                            "expected_value": expected_token,
                            "found_value": txt_value
                        },
                        records_found=found_records
                    )

            # Records found but none match
            logger.warning(f"TXT records found for {domain} but none match expected token")
            return VerificationResult(
                success=False,
                status=VerificationStatus.FAILED,
                method=VerificationMethod.TXT_RECORD,
                message=f"TXT record found but value doesn't match. Expected: {expected_token}",
                details={
                    "record_name": txt_record_name,
                    "expected_value": expected_token,
                    "found_values": found_records
                },
                records_found=found_records
            )

        except dns.resolver.NXDOMAIN:
            logger.info(f"No TXT record found for {txt_record_name}")
            return VerificationResult(
                success=False,
                status=VerificationStatus.PENDING,
                method=VerificationMethod.TXT_RECORD,
                message=f"TXT record not found. Please add: {txt_record_name} -> {expected_token}",
                details={
                    "record_name": txt_record_name,
                    "expected_value": expected_token,
                    "instruction": f"Add a TXT record with name '{txt_record_name}' and value '{expected_token}'"
                }
            )

        except dns.resolver.NoAnswer:
            logger.info(f"No TXT answer for {txt_record_name}")
            return VerificationResult(
                success=False,
                status=VerificationStatus.PENDING,
                method=VerificationMethod.TXT_RECORD,
                message=f"No TXT record found at {txt_record_name}",
                details={
                    "record_name": txt_record_name,
                    "instruction": f"Add a TXT record with name '{txt_record_name}' and value '{expected_token}'"
                }
            )

        except dns.exception.Timeout:
            logger.error(f"DNS timeout for {txt_record_name}")
            return VerificationResult(
                success=False,
                status=VerificationStatus.ERROR,
                method=VerificationMethod.TXT_RECORD,
                message="DNS lookup timed out. Please try again.",
                details={"error": "timeout"}
            )

        except Exception as e:
            logger.error(f"DNS verification error for {domain}: {e}")
            return VerificationResult(
                success=False,
                status=VerificationStatus.ERROR,
                method=VerificationMethod.TXT_RECORD,
                message=f"DNS verification error: {str(e)}",
                details={"error": "Internal server error"}
            )

    def verify_cname_record(self, domain: str) -> VerificationResult:
        """
        Verify that domain has a CNAME record pointing to our infrastructure.

        Args:
            domain: The domain to verify

        Returns:
            VerificationResult with status and details
        """
        try:
            logger.info(f"Checking CNAME record for {domain}")

            answers = self.resolver.resolve(domain, 'CNAME')
            found_records = []

            for rdata in answers:
                cname_target = str(rdata.target).rstrip('.')
                found_records.append(cname_target)

                # Check if CNAME points to any of our expected targets
                for expected in self.EXPECTED_CNAME_TARGETS:
                    if cname_target.lower() == expected.lower() or cname_target.lower().endswith(f".{expected.lower()}"):
                        logger.info(f"CNAME verification successful for {domain} -> {cname_target}")
                        return VerificationResult(
                            success=True,
                            status=VerificationStatus.VERIFIED,
                            method=VerificationMethod.CNAME_RECORD,
                            message=f"CNAME record correctly configured: {domain} -> {cname_target}",
                            details={
                                "domain": domain,
                                "cname_target": cname_target,
                                "expected_targets": self.EXPECTED_CNAME_TARGETS
                            },
                            records_found=found_records
                        )

            # CNAME found but doesn't point to our infrastructure
            logger.warning(f"CNAME for {domain} points to {found_records}, not our infrastructure")
            return VerificationResult(
                success=False,
                status=VerificationStatus.FAILED,
                method=VerificationMethod.CNAME_RECORD,
                message=f"CNAME record found but points to wrong target: {found_records[0] if found_records else 'unknown'}",
                details={
                    "domain": domain,
                    "found_target": found_records[0] if found_records else None,
                    "expected_targets": self.EXPECTED_CNAME_TARGETS,
                    "instruction": f"Update CNAME to point to: {self.EXPECTED_CNAME_TARGETS[0]}"
                },
                records_found=found_records
            )

        except dns.resolver.NoAnswer:
            # No CNAME, might have A record instead
            logger.info(f"No CNAME record for {domain}, checking A record")
            return self.verify_a_record(domain)

        except dns.resolver.NXDOMAIN:
            logger.info(f"Domain {domain} does not exist")
            return VerificationResult(
                success=False,
                status=VerificationStatus.FAILED,
                method=VerificationMethod.CNAME_RECORD,
                message=f"Domain {domain} does not exist in DNS",
                details={"error": "NXDOMAIN"}
            )

        except dns.exception.Timeout:
            logger.error(f"DNS timeout for {domain}")
            return VerificationResult(
                success=False,
                status=VerificationStatus.ERROR,
                method=VerificationMethod.CNAME_RECORD,
                message="DNS lookup timed out. Please try again.",
                details={"error": "timeout"}
            )

        except Exception as e:
            logger.error(f"CNAME verification error for {domain}: {e}")
            return VerificationResult(
                success=False,
                status=VerificationStatus.ERROR,
                method=VerificationMethod.CNAME_RECORD,
                message=f"DNS verification error: {str(e)}",
                details={"error": "Internal server error"}
            )

    def verify_a_record(self, domain: str) -> VerificationResult:
        """
        Verify that domain has an A record pointing to our infrastructure.

        Args:
            domain: The domain to verify

        Returns:
            VerificationResult with status and details
        """
        try:
            logger.info(f"Checking A record for {domain}")

            answers = self.resolver.resolve(domain, 'A')
            found_records = []

            for rdata in answers:
                ip_address = str(rdata.address)
                found_records.append(ip_address)

                # Check if A record points to our expected IPs
                if ip_address in self.EXPECTED_A_RECORDS:
                    logger.info(f"A record verification successful for {domain} -> {ip_address}")
                    return VerificationResult(
                        success=True,
                        status=VerificationStatus.VERIFIED,
                        method=VerificationMethod.A_RECORD,
                        message=f"A record correctly configured: {domain} -> {ip_address}",
                        details={
                            "domain": domain,
                            "ip_address": ip_address,
                            "expected_ips": self.EXPECTED_A_RECORDS
                        },
                        records_found=found_records
                    )

            # A record found but doesn't point to our infrastructure
            logger.warning(f"A record for {domain} points to {found_records}, not our infrastructure")
            return VerificationResult(
                success=False,
                status=VerificationStatus.FAILED,
                method=VerificationMethod.A_RECORD,
                message=f"A record found but points to wrong IP: {found_records[0] if found_records else 'unknown'}",
                details={
                    "domain": domain,
                    "found_ips": found_records,
                    "expected_ips": self.EXPECTED_A_RECORDS,
                    "instruction": f"Update A record to point to: {self.EXPECTED_A_RECORDS[0]} or use CNAME to {self.EXPECTED_CNAME_TARGETS[0]}"
                },
                records_found=found_records
            )

        except dns.resolver.NoAnswer:
            logger.info(f"No A record for {domain}")
            return VerificationResult(
                success=False,
                status=VerificationStatus.PENDING,
                method=VerificationMethod.A_RECORD,
                message=f"No A record found for {domain}",
                details={
                    "instruction": f"Add a CNAME record pointing to {self.EXPECTED_CNAME_TARGETS[0]} or an A record pointing to {self.EXPECTED_A_RECORDS[0]}"
                }
            )

        except dns.resolver.NXDOMAIN:
            logger.info(f"Domain {domain} does not exist")
            return VerificationResult(
                success=False,
                status=VerificationStatus.FAILED,
                method=VerificationMethod.A_RECORD,
                message=f"Domain {domain} does not exist in DNS",
                details={"error": "NXDOMAIN"}
            )

        except Exception as e:
            logger.error(f"A record verification error for {domain}: {e}")
            return VerificationResult(
                success=False,
                status=VerificationStatus.ERROR,
                method=VerificationMethod.A_RECORD,
                message=f"DNS verification error: {str(e)}",
                details={"error": "Internal server error"}
            )

    def verify_dns_configuration(self, domain: str) -> VerificationResult:
        """
        Verify that domain DNS is configured to point to our infrastructure.

        Checks CNAME first, falls back to A record.

        Args:
            domain: The domain to verify

        Returns:
            VerificationResult with status and details
        """
        # Try CNAME first (preferred)
        result = self.verify_cname_record(domain)

        if result.success:
            return result

        # If CNAME failed with NoAnswer, verify_cname_record already checked A record
        if result.method == VerificationMethod.A_RECORD:
            return result

        # If CNAME verification errored, try A record directly
        if result.status == VerificationStatus.ERROR:
            return self.verify_a_record(domain)

        return result

    def perform_full_verification(
        self,
        domain: str,
        verification_token: str
    ) -> Dict[str, Any]:
        """
        Perform complete domain verification.

        Checks both:
        1. TXT record for ownership verification
        2. CNAME/A record for DNS configuration

        Args:
            domain: The domain to verify
            verification_token: The token for TXT record verification

        Returns:
            Dict with results of all verification checks
        """
        logger.info(f"Performing full verification for {domain}")

        # Check TXT record for ownership
        txt_result = self.verify_txt_record(domain, verification_token)

        # Check DNS configuration (CNAME or A record)
        dns_result = self.verify_dns_configuration(domain)

        # Overall status
        is_fully_verified = txt_result.success and dns_result.success

        result = {
            "domain": domain,
            "fully_verified": is_fully_verified,
            "ownership_verified": txt_result.success,
            "dns_configured": dns_result.success,
            "txt_verification": txt_result.to_dict(),
            "dns_verification": dns_result.to_dict(),
            "verified_at": datetime.now(timezone.utc).isoformat() if is_fully_verified else None,
            "next_steps": []
        }

        # Add helpful next steps
        if not txt_result.success:
            txt_name = self.get_txt_record_name(domain)
            result["next_steps"].append({
                "step": 1,
                "action": "Add TXT record for ownership verification",
                "record_type": "TXT",
                "record_name": txt_name,
                "record_value": verification_token,
                "example": f"{txt_name} IN TXT \"{verification_token}\""
            })

        if not dns_result.success:
            result["next_steps"].append({
                "step": 2 if not txt_result.success else 1,
                "action": "Configure DNS to point to our servers",
                "option_a": {
                    "record_type": "CNAME",
                    "record_name": domain,
                    "record_value": self.EXPECTED_CNAME_TARGETS[0],
                    "example": f"{domain} IN CNAME {self.EXPECTED_CNAME_TARGETS[0]}"
                },
                "option_b": {
                    "record_type": "A",
                    "record_name": domain,
                    "record_value": self.EXPECTED_A_RECORDS[0],
                    "example": f"{domain} IN A {self.EXPECTED_A_RECORDS[0]}"
                }
            })

        return result

    def check_domain_reachability(self, domain: str, timeout: int = 5) -> Dict[str, Any]:
        """
        Check if domain is reachable via HTTP/HTTPS.

        Args:
            domain: The domain to check
            timeout: Connection timeout in seconds

        Returns:
            Dict with reachability status
        """
        import urllib.request
        import urllib.error
        import ssl

        results = {
            "domain": domain,
            "https_reachable": False,
            "http_reachable": False,
            "ssl_valid": False,
            "errors": []
        }

        # Check HTTPS
        try:
            context = ssl.create_default_context()
            req = urllib.request.Request(
                f"https://{domain}",
                headers={"User-Agent": "PerenniaAI-DomainVerifier/1.0"}
            )
            with urllib.request.urlopen(req, timeout=timeout, context=context) as response:
                results["https_reachable"] = True
                results["ssl_valid"] = True
                results["https_status_code"] = response.status
        except ssl.SSLError as e:
            results["errors"].append(f"SSL error: {str(e)}")
        except urllib.error.URLError as e:
            results["errors"].append(f"HTTPS error: {str(e)}")
        except Exception as e:
            results["errors"].append(f"HTTPS error: {str(e)}")

        # Check HTTP (without SSL)
        try:
            req = urllib.request.Request(
                f"http://{domain}",
                headers={"User-Agent": "PerenniaAI-DomainVerifier/1.0"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as response:
                results["http_reachable"] = True
                results["http_status_code"] = response.status
        except Exception as e:
            if not results["https_reachable"]:
                results["errors"].append(f"HTTP error: {str(e)}")

        return results


# Singleton instance
dns_verification_service = DNSVerificationService()
