"""
Sensitive Data Detector - Compliance Critical

Detects and handles PII/sensitive data to:
- Prevent sensitive data from being stored in chat logs
- Warn users about sharing sensitive information
- Comply with data protection regulations
"""

import re
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SensitiveDataFinding:
    """A detected piece of sensitive data"""
    data_type: str
    matched_text: str
    severity: str  # 'critical', 'high', 'medium'
    should_block: bool


class SensitiveDataDetector:
    """Detect and redact PII/sensitive data"""

    # Pattern definitions with severity levels
    PATTERNS = {
        'ssn': {
            'pattern': r'\b\d{3}-?\d{2}-?\d{4}\b',
            'severity': 'critical',
            'description': 'Social Security Number',
            'should_block': True
        },
        'ssn_partial': {
            'pattern': r'\b(?:ssn|social|social security)[:\s]*\d{3,}\b',
            'severity': 'critical',
            'description': 'Partial SSN',
            'should_block': True
        },
        'dob_full': {
            'pattern': r'\b(?:0?[1-9]|1[0-2])[/-](?:0?[1-9]|[12]\d|3[01])[/-](?:19|20)\d{2}\b',
            'severity': 'high',
            'description': 'Full date of birth',
            'should_block': True
        },
        'dob_with_label': {
            'pattern': r'\b(?:dob|birth|birthday|born)[:\s]*\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b',
            'severity': 'high',
            'description': 'Date of birth',
            'should_block': True
        },
        'account_number': {
            'pattern': r'\b(?:account|acct)[:\s#]*\d{8,17}\b',
            'severity': 'high',
            'description': 'Account number',
            'should_block': True
        },
        'routing_number': {
            'pattern': r'\b(?:routing|aba)[:\s#]*\d{9}\b',
            'severity': 'high',
            'description': 'Routing number',
            'should_block': True
        },
        'credit_card': {
            'pattern': r'\b(?:4\d{3}|5[1-5]\d{2}|3[47]\d{2}|6(?:011|5\d{2}))[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b',
            'severity': 'critical',
            'description': 'Credit card number',
            'should_block': True
        },
        'drivers_license': {
            'pattern': r'\b(?:license|dl|driver)[:\s#]*[A-Z]?\d{6,12}\b',
            'severity': 'high',
            'description': 'Driver\'s license number',
            'should_block': True
        },
        'bank_account_explicit': {
            'pattern': r'\b(?:bank account|checking|savings)[:\s#]*\d{8,17}\b',
            'severity': 'high',
            'description': 'Bank account number',
            'should_block': True
        },
        'email': {
            'pattern': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            'severity': 'medium',
            'description': 'Email address',
            'should_block': False  # Email is OK to share
        },
        'phone_with_area': {
            'pattern': r'\b(?:\+1[- ]?)?(?:\(\d{3}\)|\d{3})[- ]?\d{3}[- ]?\d{4}\b',
            'severity': 'medium',
            'description': 'Phone number',
            'should_block': False  # Phone is OK for callbacks
        }
    }

    # Standard response when blocking sensitive data
    REDACTION_RESPONSE = (
        "For your security, please don't share sensitive information like "
        "Social Security numbers, full dates of birth, or account numbers in this chat. "
        "We'll collect that information securely during the official application process. "
        "How else can I help you today?"
    )

    # Softer warning for partial sensitive data
    SOFT_WARNING = (
        "Just a heads up - for your security, please avoid sharing sensitive details "
        "like SSN or account numbers here. We'll collect those securely later. "
        "What else can I help with?"
    )

    @classmethod
    def scan(cls, message: str) -> List[SensitiveDataFinding]:
        """
        Scan message for all types of sensitive data.

        Args:
            message: User message to scan

        Returns:
            List of SensitiveDataFinding objects
        """
        findings = []

        for data_type, config in cls.PATTERNS.items():
            matches = re.findall(config['pattern'], message, re.IGNORECASE)
            for match in matches:
                findings.append(SensitiveDataFinding(
                    data_type=data_type,
                    matched_text=match,
                    severity=config['severity'],
                    should_block=config['should_block']
                ))

        return findings

    @classmethod
    def should_block(cls, message: str) -> bool:
        """
        Determine if message should trigger a warning/block.

        Args:
            message: User message

        Returns:
            True if message contains critical sensitive data
        """
        findings = cls.scan(message)

        # Block if any critical or high-severity, block-worthy finding
        for finding in findings:
            if finding.should_block and finding.severity in ['critical', 'high']:
                logger.warning(
                    f"Blocking message with sensitive data type: {finding.data_type}"
                )
                return True

        return False

    @classmethod
    def get_severity_level(cls, message: str) -> Optional[str]:
        """
        Get the highest severity level found in message.

        Returns:
            'critical', 'high', 'medium', or None
        """
        findings = cls.scan(message)

        if not findings:
            return None

        # Return highest severity found
        for level in ['critical', 'high', 'medium']:
            if any(f.severity == level for f in findings):
                return level

        return None

    @classmethod
    def redact(cls, message: str) -> str:
        """
        Redact sensitive data from message for logging.

        Args:
            message: Original message

        Returns:
            Message with sensitive data replaced with [REDACTED]
        """
        redacted = message

        # Only redact critical and high-severity patterns
        for data_type, config in cls.PATTERNS.items():
            if config['severity'] in ['critical', 'high'] and config['should_block']:
                redacted = re.sub(
                    config['pattern'],
                    f'[{config["description"].upper()} REDACTED]',
                    redacted,
                    flags=re.IGNORECASE
                )

        return redacted

    @classmethod
    def get_warning_message(cls, message: str) -> Optional[str]:
        """
        Get appropriate warning message based on what was detected.

        Args:
            message: User message

        Returns:
            Warning message or None if no warning needed
        """
        findings = cls.scan(message)

        if not findings:
            return None

        # Check for critical items
        critical_findings = [f for f in findings if f.severity == 'critical']
        if critical_findings:
            return cls.REDACTION_RESPONSE

        # Check for high-severity items that should block
        high_findings = [f for f in findings if f.severity == 'high' and f.should_block]
        if high_findings:
            return cls.REDACTION_RESPONSE

        return None

    @classmethod
    def safe_to_store(cls, message: str) -> tuple:
        """
        Check if message is safe to store and get safe version.

        Returns:
            Tuple of (is_safe, message_to_store)
            - is_safe: True if original is OK to store
            - message_to_store: Redacted version if needed
        """
        if not cls.should_block(message):
            return True, message

        return False, cls.redact(message)

    @classmethod
    def extract_safe_contact_info(cls, message: str) -> Dict[str, Optional[str]]:
        """
        Extract contact info that IS safe to collect (email, phone).

        Returns:
            Dict with 'email' and 'phone' keys
        """
        contact_info = {
            'email': None,
            'phone': None
        }

        # Extract email
        email_match = re.search(
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            message
        )
        if email_match:
            contact_info['email'] = email_match.group(0)

        # Extract phone
        phone_match = re.search(
            r'\b(?:\+1[- ]?)?(?:\(\d{3}\)|\d{3})[- ]?\d{3}[- ]?\d{4}\b',
            message
        )
        if phone_match:
            contact_info['phone'] = phone_match.group(0)

        return contact_info


class ComplianceLogger:
    """Log compliance-related events"""

    @staticmethod
    def log_sensitive_data_blocked(
        session_id: str,
        data_type: str,
        severity: str
    ):
        """Log when sensitive data is blocked"""
        logger.warning(
            f"COMPLIANCE: Blocked sensitive data | "
            f"session={session_id} | "
            f"type={data_type} | "
            f"severity={severity}"
        )

    @staticmethod
    def log_data_redacted(
        session_id: str,
        data_types: List[str]
    ):
        """Log when data is redacted before storage"""
        logger.info(
            f"COMPLIANCE: Data redacted before storage | "
            f"session={session_id} | "
            f"types={','.join(data_types)}"
        )
