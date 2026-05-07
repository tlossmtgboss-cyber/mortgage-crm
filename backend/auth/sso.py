"""
SAML SSO Service

Provides the core SSO authentication bridge for enterprise customers.
Handles SAML AuthnRequest generation, response validation (including XML
signature verification via signxml), JIT user provisioning, and JWT token
generation that integrates with the existing Perennia auth system.

Uses defusedxml for safe XML parsing and signxml for cryptographic
verification of SAML response signatures against the IdP's X.509 certificate.

Usage:
    from auth.sso import (
        get_org_sso_config,
        create_saml_auth_request,
        process_saml_response,
        provision_or_update_user,
        generate_jwt_from_sso,
    )
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import uuid
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple
from urllib.parse import urlencode

from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from database.models.core import User

logger = logging.getLogger(__name__)

# SP defaults from environment
_SP_ENTITY_ID = os.getenv("SAML_SP_ENTITY_ID", "https://api.perenniaai.com")
_SP_ACS_URL = os.getenv("SAML_ACS_URL", "https://api.perenniaai.com/api/v1/auth/sso/{org_slug}/callback")
_SP_SLO_URL = os.getenv("SAML_SLO_URL", "https://api.perenniaai.com/api/v1/auth/sso/{org_slug}/logout")

# Default attribute mappings for common IdPs
_DEFAULT_ATTRIBUTE_MAPS = {
    "okta": {
        "email": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
        "first_name": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname",
        "last_name": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname",
        "groups": "http://schemas.xmlsoap.org/claims/Group",
    },
    "azure_ad": {
        "email": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
        "first_name": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname",
        "last_name": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname",
        "groups": "http://schemas.microsoft.com/ws/2008/06/identity/claims/groups",
    },
    "onelogin": {
        "email": "User.email",
        "first_name": "User.FirstName",
        "last_name": "User.LastName",
        "groups": "memberOf",
    },
    "google": {
        "email": "email",
        "first_name": "first_name",
        "last_name": "last_name",
        "groups": "groups",
    },
    "custom": {
        "email": "email",
        "first_name": "first_name",
        "last_name": "last_name",
        "groups": "groups",
    },
}

# In-memory request ID store for replay protection
# Maps request_id -> (created_at_timestamp, org_id)
# In production, this should use Redis for multi-process safety
_pending_requests: Dict[str, Tuple[float, int]] = {}
_REQUEST_TTL_SECONDS = 600  # 10 minute window for SAML response


# =============================================================================
# SSOConfig Dataclass
# =============================================================================

@dataclass
class SSOConfig:
    """Resolved SSO configuration for a single organization.

    This is the in-memory representation used by the SSO flow functions.
    It is constructed from the SSOConfiguration database model.
    """

    entity_id: str
    sso_url: str
    slo_url: Optional[str] = None
    x509_cert: Optional[str] = None
    attribute_mapping: Dict[str, str] = field(default_factory=dict)
    default_role: str = "loan_officer"
    default_permission_role: str = "sales"
    sp_entity_id: Optional[str] = None
    auto_provision: bool = True
    enforce_sso: bool = False
    organization_id: Optional[int] = None
    provider: str = "custom"


# =============================================================================
# Config Retrieval
# =============================================================================

def get_org_sso_config(org_id: int, db: Session) -> Optional[SSOConfig]:
    """Retrieve the active SSO configuration for an organization.

    Args:
        org_id: Organization ID.
        db: SQLAlchemy database session.

    Returns:
        SSOConfig dataclass if configured and active, None otherwise.
    """
    from database.models.sso_config import SSOConfiguration

    db_config = db.query(SSOConfiguration).filter(
        SSOConfiguration.organization_id == org_id,
        SSOConfiguration.is_active == True,
    ).first()

    if not db_config:
        return None

    if not db_config.is_saml_configured:
        logger.debug(f"SSO config for org {org_id} exists but SAML is not fully configured")
        return None

    # Resolve attribute mapping: use stored mapping or provider defaults
    attr_mapping = db_config.attribute_mapping or {}
    if not attr_mapping:
        attr_mapping = _DEFAULT_ATTRIBUTE_MAPS.get(db_config.provider, _DEFAULT_ATTRIBUTE_MAPS["custom"])

    return SSOConfig(
        entity_id=db_config.entity_id,
        sso_url=db_config.sso_url,
        slo_url=db_config.slo_url,
        x509_cert=db_config.x509_cert,
        attribute_mapping=attr_mapping,
        default_role=db_config.default_role or "loan_officer",
        default_permission_role=db_config.default_permission_role or "sales",
        sp_entity_id=db_config.sp_entity_id or _SP_ENTITY_ID,
        auto_provision=db_config.auto_provision,
        enforce_sso=db_config.enforce_sso,
        organization_id=org_id,
        provider=db_config.provider or "custom",
    )


def get_org_sso_config_by_slug(org_slug: str, db: Session) -> Tuple[Optional[SSOConfig], Optional[int]]:
    """Retrieve SSO configuration by organization slug.

    Args:
        org_slug: Organization URL slug.
        db: SQLAlchemy database session.

    Returns:
        Tuple of (SSOConfig, org_id) if found, (None, None) otherwise.
    """
    from database.models.core import Organization

    org = db.query(Organization).filter(
        Organization.slug == org_slug,
        Organization.is_active == True,
    ).first()

    if not org:
        return None, None

    config = get_org_sso_config(org.id, db)
    return config, org.id


# =============================================================================
# SAML AuthnRequest Generation
# =============================================================================

def create_saml_auth_request(
    config: SSOConfig,
    org_slug: Optional[str] = None,
) -> Tuple[str, str]:
    """Generate a SAML AuthnRequest and return the request ID and redirect URL.

    Creates a SAML 2.0 AuthnRequest XML, deflates it, base64-encodes it,
    and builds the redirect URL to the IdP's SSO endpoint using HTTP-Redirect
    binding.

    Args:
        config: Resolved SSOConfig for the organization.
        org_slug: Organization slug for building the ACS URL.

    Returns:
        Tuple of (request_id, redirect_url).
    """
    request_id = f"_perennia_{uuid.uuid4().hex}"
    issue_instant = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    sp_entity_id = config.sp_entity_id or _SP_ENTITY_ID

    # Build ACS URL with org slug
    if org_slug:
        acs_url = _SP_ACS_URL.replace("{org_slug}", org_slug)
    else:
        acs_url = os.getenv("SAML_ACS_URL", f"https://api.perenniaai.com/api/v1/auth/sso/callback")

    authn_request_xml = (
        '<samlp:AuthnRequest'
        ' xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"'
        ' xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"'
        f' ID="{request_id}"'
        ' Version="2.0"'
        f' IssueInstant="{issue_instant}"'
        f' Destination="{config.sso_url}"'
        f' AssertionConsumerServiceURL="{acs_url}"'
        ' ProtocolBinding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST">'
        f'<saml:Issuer>{sp_entity_id}</saml:Issuer>'
        '<samlp:NameIDPolicy'
        ' Format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress"'
        ' AllowCreate="true"/>'
        '</samlp:AuthnRequest>'
    )

    # Deflate (raw, no zlib header/trailer) and base64 encode
    deflated = zlib.compress(authn_request_xml.encode("utf-8"))[2:-4]
    encoded = base64.b64encode(deflated).decode("utf-8")

    # Build relay state with org info for the callback
    relay_state = f"org_{config.organization_id}"

    params = {
        "SAMLRequest": encoded,
        "RelayState": relay_state,
    }

    redirect_url = f"{config.sso_url}?{urlencode(params)}"

    # Store request ID for replay protection
    _pending_requests[request_id] = (datetime.now(timezone.utc).timestamp(), config.organization_id)
    _cleanup_expired_requests()

    logger.info(
        f"SAML AuthnRequest created: id={request_id[:20]}..., "
        f"org_id={config.organization_id}, idp={config.sso_url}"
    )

    return request_id, redirect_url


# =============================================================================
# SAML Response Processing
# =============================================================================

def _verify_saml_xml_signature(xml_bytes: bytes, x509_cert: str) -> None:
    """Verify XML digital signature on a SAML Response using the IdP's X.509 certificate.

    Args:
        xml_bytes: Raw XML bytes of the SAML Response.
        x509_cert: IdP X.509 certificate (PEM-encoded or raw base64 body).

    Raises:
        ValueError: If the signature is missing, invalid, or verification fails.
    """
    try:
        from signxml import XMLVerifier
        from signxml.exceptions import (
            InvalidCertificate,
            InvalidDigest,
            InvalidInput,
            InvalidSignature,
        )
    except ImportError:
        raise ValueError(
            "signxml library is required for SAML signature verification. "
            "Install it with: pip install signxml>=3.0.0"
        )

    # Normalize certificate to PEM format
    cert = x509_cert.strip()
    if not cert.startswith("-----BEGIN CERTIFICATE-----"):
        cert_body = cert.replace("\n", "").replace("\r", "").replace(" ", "")
        cert = f"-----BEGIN CERTIFICATE-----\n{cert_body}\n-----END CERTIFICATE-----"

    try:
        XMLVerifier().verify(xml_bytes, x509_cert=cert)
        logger.info("SAML XML signature verification succeeded")
    except InvalidDigest as e:
        logger.error(f"SAML signature digest mismatch (possible tampering): {e}")
        raise ValueError(f"SAML signature digest verification failed: {e}")
    except InvalidCertificate as e:
        logger.error(f"SAML IdP certificate validation failed: {e}")
        raise ValueError(f"SAML certificate verification failed: {e}")
    except InvalidSignature as e:
        logger.error(f"SAML signature verification failed: {e}")
        raise ValueError(f"SAML signature verification failed: {e}")
    except InvalidInput as e:
        logger.error(f"SAML signature invalid input: {e}")
        raise ValueError(f"SAML signature verification error: {e}")
    except Exception as e:
        logger.error(f"SAML signature verification unexpected error: {e}")
        raise ValueError(f"SAML signature verification failed: {e}")


def process_saml_response(
    saml_response: str,
    config: SSOConfig,
) -> dict:
    """Validate and parse a SAML Response, extracting user attributes.

    Performs the following validations:
    - Base64 decode
    - XML signature verification using IdP X.509 certificate
    - XML parsing (using defusedxml if available, stdlib fallback)
    - Status code check (must be Success)
    - Assertion presence
    - Conditions / NotOnOrAfter expiry check
    - Audience restriction check
    - NameID extraction
    - Attribute extraction using the configured attribute mapping

    Args:
        saml_response: Base64-encoded SAML Response from the IdP.
        config: SSOConfig for the organization.

    Returns:
        Dict with extracted user attributes:
        - email (str)
        - first_name (str or None)
        - last_name (str or None)
        - groups (list of str)
        - name_id (str)
        - session_index (str or None)
        - raw_attributes (dict)

    Raises:
        ValueError: If the SAML response is invalid or validation fails.
    """
    # Try defusedxml first (prevents XML bombs / XXE)
    try:
        import defusedxml.ElementTree as ET
    except ImportError:
        import xml.etree.ElementTree as ET
        logger.warning(
            "defusedxml not available; using stdlib xml.etree. "
            "Install defusedxml for XXE protection in production."
        )

    # Decode base64
    try:
        xml_bytes = base64.b64decode(saml_response)
        xml_str = xml_bytes.decode("utf-8")
    except Exception as e:
        raise ValueError(f"Failed to decode SAML Response: {e}")

    # ── XML Signature Verification ──
    if config.x509_cert:
        _verify_saml_xml_signature(xml_bytes, config.x509_cert)
    else:
        logger.warning(
            "SAML response processed WITHOUT signature verification — "
            f"no IdP X.509 certificate configured for org {config.organization_id}. "
            "This is insecure and should be fixed by uploading the IdP certificate."
        )

    # Parse XML
    try:
        root = ET.fromstring(xml_str)
    except Exception as e:
        raise ValueError(f"Failed to parse SAML Response XML: {e}")

    ns = {
        "samlp": "urn:oasis:names:tc:SAML:2.0:protocol",
        "saml": "urn:oasis:names:tc:SAML:2.0:assertion",
    }

    # Check status
    status_elem = root.find(".//samlp:Status/samlp:StatusCode", ns)
    if status_elem is not None:
        status_value = status_elem.get("Value", "")
        if "Success" not in status_value:
            raise ValueError(f"SAML Response status: {status_value}")

    # Find assertion
    assertion = root.find(".//saml:Assertion", ns)
    if assertion is None:
        raise ValueError("No Assertion element found in SAML Response")

    # Check conditions
    conditions = assertion.find("saml:Conditions", ns)
    if conditions is not None:
        not_on_or_after = conditions.get("NotOnOrAfter")
        if not_on_or_after:
            try:
                expiry = datetime.fromisoformat(not_on_or_after.replace("Z", "+00:00"))
                if datetime.now(timezone.utc) > expiry:
                    raise ValueError("SAML Assertion has expired (NotOnOrAfter)")
            except ValueError:
                raise  # re-raise our own ValueError
            except Exception:
                logger.warning(f"Could not parse NotOnOrAfter: {not_on_or_after}")

        # Audience restriction
        sp_entity_id = config.sp_entity_id or _SP_ENTITY_ID
        audience_elem = conditions.find(".//saml:AudienceRestriction/saml:Audience", ns)
        if audience_elem is not None and audience_elem.text:
            if audience_elem.text.strip() != sp_entity_id:
                raise ValueError(
                    f"Audience mismatch: expected '{sp_entity_id}', "
                    f"got '{audience_elem.text.strip()}'"
                )

    # Extract NameID
    name_id_elem = assertion.find("saml:Subject/saml:NameID", ns)
    name_id = name_id_elem.text.strip() if name_id_elem is not None and name_id_elem.text else None
    if not name_id:
        raise ValueError("No NameID found in SAML Assertion")

    # Extract raw attributes from AttributeStatement
    raw_attributes: Dict[str, str] = {}
    attr_statement = assertion.find("saml:AttributeStatement", ns)
    if attr_statement is not None:
        for attr_elem in attr_statement.findall("saml:Attribute", ns):
            attr_name = attr_elem.get("Name", "")
            values = [
                v.text for v in attr_elem.findall("saml:AttributeValue", ns)
                if v.text
            ]
            if values:
                raw_attributes[attr_name] = values[0] if len(values) == 1 else values

    # Extract session index for SLO
    authn_stmt = assertion.find("saml:AuthnStatement", ns)
    session_index = authn_stmt.get("SessionIndex") if authn_stmt is not None else None

    # Map attributes using the configured mapping
    attr_map = config.attribute_mapping or _DEFAULT_ATTRIBUTE_MAPS.get("custom", {})

    email = _resolve_attribute(raw_attributes, attr_map.get("email"), name_id)
    first_name = _resolve_attribute(raw_attributes, attr_map.get("first_name"))
    last_name = _resolve_attribute(raw_attributes, attr_map.get("last_name"))
    groups = _resolve_groups(raw_attributes, attr_map.get("groups"))

    # Ensure email looks like an email; fallback to NameID
    if not email or "@" not in email:
        if "@" in name_id:
            email = name_id.lower()
        else:
            raise ValueError("Could not determine email from SAML assertion")

    email = email.lower().strip()

    logger.info(f"SAML Response parsed: email={email}, name_id={name_id}")

    return {
        "email": email,
        "first_name": first_name,
        "last_name": last_name,
        "groups": groups,
        "name_id": name_id,
        "session_index": session_index,
        "raw_attributes": raw_attributes,
    }


# =============================================================================
# User Provisioning
# =============================================================================

def provision_or_update_user(
    attributes: dict,
    org_id: int,
    db: Session,
) -> "User":
    """JIT (just-in-time) provision or update a user from SAML attributes.

    If a user with the given email exists, updates their SSO metadata.
    If no user exists and auto_provision is enabled on the org's SSO config,
    creates a new user with a random (unusable) password hash.

    Args:
        attributes: Dict from process_saml_response() with email, first_name,
                    last_name, groups, name_id.
        org_id: Organization ID.
        db: SQLAlchemy database session.

    Returns:
        User object (existing or newly created).

    Raises:
        ValueError: If the user doesn't exist and auto-provisioning is disabled.
    """
    from auth.jit_provisioning import provision_user_from_sso, update_user_from_sso
    from database.models.core import User

    email = attributes["email"]
    user = db.query(User).filter(User.email == email.lower()).first()

    if user:
        update_user_from_sso(
            db=db,
            user=user,
            first_name=attributes.get("first_name"),
            last_name=attributes.get("last_name"),
            groups=attributes.get("groups", []),
            sso_provider="saml",
            sso_subject_id=attributes.get("name_id", email),
        )
        return user

    # Check if auto-provisioning is allowed
    from database.models.sso_config import SSOConfiguration
    sso_cfg = db.query(SSOConfiguration).filter(
        SSOConfiguration.organization_id == org_id,
        SSOConfiguration.is_active == True,
    ).first()

    if not sso_cfg or not sso_cfg.auto_provision:
        raise ValueError(
            f"No existing user for {email} and auto-provisioning is disabled for org {org_id}"
        )

    user = provision_user_from_sso(
        db=db,
        email=email,
        first_name=attributes.get("first_name"),
        last_name=attributes.get("last_name"),
        organization_id=org_id,
        sso_provider="saml",
        sso_subject_id=attributes.get("name_id", email),
        groups=attributes.get("groups", []),
        default_role=sso_cfg.default_role or "loan_officer",
        default_permission_role=sso_cfg.default_permission_role or "sales",
    )

    return user


# =============================================================================
# JWT Bridge
# =============================================================================

def generate_jwt_from_sso(user) -> Tuple[str, str]:
    """Generate Perennia JWT access + refresh tokens from an SSO-authenticated user.

    Bridges the SSO authentication into the existing JWT-based auth system so
    all downstream middleware, route guards, and WebSocket auth work unchanged.

    Args:
        user: User SQLAlchemy model instance.

    Returns:
        Tuple of (access_token, refresh_token).
    """
    from auth.tokens import create_access_token, create_refresh_token

    tenant_id = str(user.organization_id) if user.organization_id else None

    token_data = {
        "sub": user.email,
        "user_id": user.id,
        "sso_login": True,
    }
    if tenant_id:
        token_data["tenant_id"] = tenant_id

    access_token = create_access_token(data=token_data)
    refresh_token = create_refresh_token(data=token_data)

    return access_token, refresh_token


# =============================================================================
# SP Metadata Generation
# =============================================================================

def generate_sp_metadata_xml(org_slug: Optional[str] = None) -> str:
    """Generate SAML 2.0 SP metadata XML for IdP configuration.

    Args:
        org_slug: Organization slug (used to build per-org ACS/SLO URLs).

    Returns:
        XML string of SP metadata.
    """
    entity_id = _SP_ENTITY_ID
    acs_url = _SP_ACS_URL.replace("{org_slug}", org_slug) if org_slug else _SP_ACS_URL
    slo_url = _SP_SLO_URL.replace("{org_slug}", org_slug) if org_slug else _SP_SLO_URL

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
                     entityID="{entity_id}">
  <md:SPSSODescriptor
      AuthnRequestsSigned="false"
      WantAssertionsSigned="true"
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:NameIDFormat>urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress</md:NameIDFormat>
    <md:AssertionConsumerService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
        Location="{acs_url}"
        index="0"
        isDefault="true"/>
    <md:SingleLogoutService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="{slo_url}"/>
  </md:SPSSODescriptor>
</md:EntityDescriptor>"""


# =============================================================================
# SLO (Single Logout) Request
# =============================================================================

def create_slo_request(config: SSOConfig, name_id: str, session_index: Optional[str] = None) -> Optional[str]:
    """Create a SAML LogoutRequest redirect URL.

    Args:
        config: SSOConfig for the organization.
        name_id: NameID of the user to log out.
        session_index: Optional session index from the original assertion.

    Returns:
        Redirect URL to IdP SLO endpoint, or None if SLO is not configured.
    """
    if not config.slo_url:
        return None

    request_id = f"_perennia_slo_{uuid.uuid4().hex}"
    issue_instant = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    sp_entity_id = config.sp_entity_id or _SP_ENTITY_ID

    session_index_xml = ""
    if session_index:
        session_index_xml = f"<samlp:SessionIndex>{session_index}</samlp:SessionIndex>"

    logout_xml = (
        '<samlp:LogoutRequest'
        ' xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"'
        ' xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"'
        f' ID="{request_id}"'
        ' Version="2.0"'
        f' IssueInstant="{issue_instant}"'
        f' Destination="{config.slo_url}">'
        f'<saml:Issuer>{sp_entity_id}</saml:Issuer>'
        f'<saml:NameID Format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress">{name_id}</saml:NameID>'
        f'{session_index_xml}'
        '</samlp:LogoutRequest>'
    )

    deflated = zlib.compress(logout_xml.encode("utf-8"))[2:-4]
    encoded = base64.b64encode(deflated).decode("utf-8")

    params = {"SAMLRequest": encoded}
    return f"{config.slo_url}?{urlencode(params)}"


# =============================================================================
# IdP Metadata Parsing
# =============================================================================

def parse_idp_metadata_xml(metadata_xml: str) -> dict:
    """Parse IdP metadata XML and extract configuration values.

    Extracts entity_id, sso_url, slo_url, and x509_cert from standard
    SAML 2.0 IdP metadata XML.

    Args:
        metadata_xml: IdP metadata XML string.

    Returns:
        Dict with: entity_id, sso_url, slo_url, x509_cert.

    Raises:
        ValueError: If the metadata XML cannot be parsed.
    """
    try:
        import defusedxml.ElementTree as ET
    except ImportError:
        import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(metadata_xml)
    except Exception as e:
        raise ValueError(f"Invalid IdP metadata XML: {e}")

    ns = {
        "md": "urn:oasis:names:tc:SAML:2.0:metadata",
        "ds": "http://www.w3.org/2000/09/xmldsig#",
    }

    result = {
        "entity_id": root.get("entityID"),
        "sso_url": None,
        "slo_url": None,
        "x509_cert": None,
    }

    # Find SSO endpoint (HTTP-Redirect or HTTP-POST)
    idp_sso_desc = root.find(".//md:IDPSSODescriptor", ns)
    if idp_sso_desc is not None:
        for sso_svc in idp_sso_desc.findall("md:SingleSignOnService", ns):
            binding = sso_svc.get("Binding", "")
            if "HTTP-Redirect" in binding or "HTTP-POST" in binding:
                result["sso_url"] = sso_svc.get("Location")
                break

        # Find SLO endpoint
        for slo_svc in idp_sso_desc.findall("md:SingleLogoutService", ns):
            binding = slo_svc.get("Binding", "")
            if "HTTP-Redirect" in binding:
                result["slo_url"] = slo_svc.get("Location")
                break

        # Find X.509 certificate
        cert_elem = idp_sso_desc.find(
            ".//md:KeyDescriptor[@use='signing']/ds:KeyInfo/ds:X509Data/ds:X509Certificate", ns
        )
        if cert_elem is None:
            # Try without use="signing" attribute
            cert_elem = idp_sso_desc.find(
                ".//md:KeyDescriptor/ds:KeyInfo/ds:X509Data/ds:X509Certificate", ns
            )
        if cert_elem is not None and cert_elem.text:
            # Normalize certificate: strip whitespace and wrap in PEM headers
            cert_body = cert_elem.text.strip().replace("\n", "").replace("\r", "")
            result["x509_cert"] = (
                f"-----BEGIN CERTIFICATE-----\n{cert_body}\n-----END CERTIFICATE-----"
            )

    return result


# =============================================================================
# Internal Helpers
# =============================================================================

def _resolve_attribute(
    raw_attributes: Dict,
    mapping_key: Optional[str],
    fallback: Optional[str] = None,
) -> Optional[str]:
    """Resolve a single attribute value using the mapping key."""
    if not mapping_key:
        return fallback

    value = raw_attributes.get(mapping_key)
    if value:
        return value[0] if isinstance(value, list) else value

    # Try case-insensitive match
    mapping_lower = mapping_key.lower()
    for key, val in raw_attributes.items():
        if key.lower() == mapping_lower:
            return val[0] if isinstance(val, list) else val

    return fallback


def _resolve_groups(raw_attributes: Dict, mapping_key: Optional[str]) -> List[str]:
    """Resolve group membership from attributes."""
    if not mapping_key:
        return []

    value = raw_attributes.get(mapping_key)
    if not value:
        # Try case-insensitive
        mapping_lower = mapping_key.lower()
        for key, val in raw_attributes.items():
            if key.lower() == mapping_lower:
                value = val
                break

    if not value:
        return []

    if isinstance(value, list):
        return value
    return [value]


def _cleanup_expired_requests():
    """Remove expired pending SAML request IDs."""
    now = datetime.now(timezone.utc).timestamp()
    expired = [
        rid for rid, (created, _) in _pending_requests.items()
        if now - created > _REQUEST_TTL_SECONDS
    ]
    for rid in expired:
        _pending_requests.pop(rid, None)
    if expired:
        logger.debug(f"Cleaned up {len(expired)} expired SAML request IDs")


__all__ = [
    "SSOConfig",
    "get_org_sso_config",
    "get_org_sso_config_by_slug",
    "create_saml_auth_request",
    "process_saml_response",
    "provision_or_update_user",
    "generate_jwt_from_sso",
    "generate_sp_metadata_xml",
    "create_slo_request",
    "parse_idp_metadata_xml",
]
