"""
SAML 2.0 SSO Service
Enterprise Readiness Checks 4.5, 5.9

Provides SAML 2.0 Service Provider (SP) functionality:
- SP metadata generation
- AuthnRequest creation (login initiation)
- SAML Response/Assertion parsing and validation (with XML signature verification)
- Single Logout (SLO) support

Uses defusedxml for safe XML parsing and signxml for cryptographic signature
verification of SAML responses/assertions.
"""

import base64
import hashlib
import logging
import os
import uuid
import zlib
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Tuple
from urllib.parse import quote, urlencode

logger = logging.getLogger(__name__)

# App-level constants
SP_ENTITY_ID_DEFAULT = os.getenv("SAML_SP_ENTITY_ID", "https://api.perenniaai.com")
SP_ACS_URL = os.getenv("SAML_ACS_URL", "https://api.perenniaai.com/api/v1/auth/sso/saml/acs")
SP_SLO_URL = os.getenv("SAML_SLO_URL", "https://api.perenniaai.com/api/v1/auth/sso/saml/slo")
SP_METADATA_URL = os.getenv("SAML_METADATA_URL", "https://api.perenniaai.com/api/v1/auth/sso/saml/metadata")


def generate_sp_metadata(
    entity_id: Optional[str] = None,
    acs_url: Optional[str] = None,
    slo_url: Optional[str] = None,
) -> str:
    """
    Generate SAML 2.0 SP metadata XML.

    Args:
        entity_id: SP entity ID (defaults to env var or app URL).
        acs_url: Assertion Consumer Service URL.
        slo_url: Single Logout URL.

    Returns:
        XML string of SP metadata.
    """
    _entity_id = entity_id or SP_ENTITY_ID_DEFAULT
    _acs_url = acs_url or SP_ACS_URL
    _slo_url = slo_url or SP_SLO_URL

    metadata = f"""<?xml version="1.0" encoding="UTF-8"?>
<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
                     entityID="{_entity_id}">
  <md:SPSSODescriptor
      AuthnRequestsSigned="false"
      WantAssertionsSigned="true"
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:NameIDFormat>urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress</md:NameIDFormat>
    <md:AssertionConsumerService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
        Location="{_acs_url}"
        index="0"
        isDefault="true"/>
    <md:SingleLogoutService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="{_slo_url}"/>
  </md:SPSSODescriptor>
</md:EntityDescriptor>"""
    return metadata


def create_authn_request(
    idp_sso_url: str,
    sp_entity_id: Optional[str] = None,
    acs_url: Optional[str] = None,
    relay_state: Optional[str] = None,
) -> str:
    """
    Create a SAML AuthnRequest and return the redirect URL.

    Uses HTTP-Redirect binding (deflated + base64 + URL-encoded).

    Args:
        idp_sso_url: The IdP's SSO endpoint URL.
        sp_entity_id: SP entity ID.
        acs_url: Assertion Consumer Service URL.
        relay_state: Optional relay state to pass through.

    Returns:
        Full redirect URL to the IdP.
    """
    _sp_entity_id = sp_entity_id or SP_ENTITY_ID_DEFAULT
    _acs_url = acs_url or SP_ACS_URL
    request_id = f"_perennia_{uuid.uuid4().hex}"
    issue_instant = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    authn_request = f"""<samlp:AuthnRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="{request_id}"
    Version="2.0"
    IssueInstant="{issue_instant}"
    Destination="{idp_sso_url}"
    AssertionConsumerServiceURL="{_acs_url}"
    ProtocolBinding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST">
  <saml:Issuer>{_sp_entity_id}</saml:Issuer>
  <samlp:NameIDPolicy
      Format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress"
      AllowCreate="true"/>
</samlp:AuthnRequest>"""

    # Deflate and base64 encode
    deflated = zlib.compress(authn_request.encode("utf-8"))[2:-4]  # raw deflate
    encoded = base64.b64encode(deflated).decode("utf-8")

    params = {"SAMLRequest": encoded}
    if relay_state:
        params["RelayState"] = relay_state

    redirect_url = f"{idp_sso_url}?{urlencode(params)}"
    return redirect_url


def _verify_xml_signature(xml_bytes: bytes, idp_certificate: str) -> bytes:
    """Verify the XML digital signature on a SAML Response or Assertion.

    Uses the signxml library to perform W3C XML Signature verification
    against the IdP's X.509 certificate.

    Args:
        xml_bytes: Raw XML bytes of the SAML Response.
        idp_certificate: IdP X.509 certificate — either PEM-encoded string
            or raw base64 certificate body (without PEM headers).

    Returns:
        The verified XML bytes (signed content).

    Raises:
        ValueError: If signature verification fails for any reason.
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

    # Normalize certificate to PEM format if needed
    cert_pem = _normalize_cert_pem(idp_certificate)

    try:
        result = XMLVerifier().verify(xml_bytes, x509_cert=cert_pem)
        logger.info("SAML XML signature verification succeeded")
        return result.signed_xml
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


def _normalize_cert_pem(cert: str) -> str:
    """Normalize an X.509 certificate to PEM format.

    Accepts PEM-encoded strings or raw base64 certificate bodies
    (without headers) and returns a properly formatted PEM string.
    """
    cert = cert.strip()
    if cert.startswith("-----BEGIN CERTIFICATE-----"):
        return cert

    # Raw base64 body — strip whitespace and wrap in PEM headers
    cert_body = cert.replace("\n", "").replace("\r", "").replace(" ", "")
    return f"-----BEGIN CERTIFICATE-----\n{cert_body}\n-----END CERTIFICATE-----"


def parse_saml_response(
    saml_response_b64: str,
    idp_certificate: Optional[str] = None,
    expected_audience: Optional[str] = None,
) -> Tuple[bool, Dict]:
    """
    Parse and validate a SAML Response from the IdP.

    Performs the following validations:
    - Decodes the base64 response
    - Verifies XML signature using IdP X.509 certificate (if provided)
    - Extracts NameID (email), attributes, and session index
    - Checks status code
    - Checks audience restriction (if provided)
    - Checks NotOnOrAfter timestamp

    Args:
        saml_response_b64: Base64-encoded SAML Response XML.
        idp_certificate: PEM-encoded IdP certificate for signature verification.
            If provided, the XML signature MUST be valid or the response is rejected.
            If not provided, a warning is logged (no signature verification).
        expected_audience: Expected SP entity ID for audience validation.

    Returns:
        Tuple of (is_valid, attributes_dict).
        attributes_dict contains: email, name_id, first_name, last_name, groups, session_index.
    """
    import defusedxml.ElementTree as ET

    try:
        # Decode base64
        xml_bytes = base64.b64decode(saml_response_b64)
        xml_str = xml_bytes.decode("utf-8")

        # ── XML Signature Verification ──
        if idp_certificate:
            try:
                _verify_xml_signature(xml_bytes, idp_certificate)
            except ValueError as e:
                logger.error(f"SAML signature verification failed: {e}")
                return False, {"error": str(e)}
        else:
            logger.warning(
                "SAML response processed WITHOUT signature verification — "
                "no IdP certificate configured. This is insecure."
            )

        # Parse XML
        root = ET.fromstring(xml_str)

        # Namespace map
        ns = {
            "samlp": "urn:oasis:names:tc:SAML:2.0:protocol",
            "saml": "urn:oasis:names:tc:SAML:2.0:assertion",
        }

        # Check status
        status_code_elem = root.find(".//samlp:Status/samlp:StatusCode", ns)
        if status_code_elem is not None:
            status_value = status_code_elem.get("Value", "")
            if "Success" not in status_value:
                logger.warning(f"SAML Response status not success: {status_value}")
                return False, {"error": f"SAML status: {status_value}"}

        # Find assertion
        assertion = root.find(".//saml:Assertion", ns)
        if assertion is None:
            logger.warning("No Assertion found in SAML Response")
            return False, {"error": "No assertion in response"}

        # Check conditions / NotOnOrAfter
        conditions = assertion.find("saml:Conditions", ns)
        if conditions is not None:
            not_on_or_after = conditions.get("NotOnOrAfter")
            if not_on_or_after:
                expiry = datetime.fromisoformat(not_on_or_after.replace("Z", "+00:00"))
                if datetime.now(timezone.utc) > expiry:
                    logger.warning("SAML Assertion has expired")
                    return False, {"error": "Assertion expired"}

            # Check audience
            if expected_audience:
                audience_elem = conditions.find(".//saml:AudienceRestriction/saml:Audience", ns)
                if audience_elem is not None and audience_elem.text != expected_audience:
                    logger.warning(
                        f"SAML audience mismatch: expected={expected_audience}, got={audience_elem.text}"
                    )
                    return False, {"error": "Audience mismatch"}

        # Extract NameID (typically the email)
        subject = assertion.find("saml:Subject/saml:NameID", ns)
        name_id = subject.text.strip() if subject is not None and subject.text else None

        if not name_id:
            logger.warning("No NameID found in SAML Assertion")
            return False, {"error": "No NameID in assertion"}

        # Extract attributes
        attributes = {}
        attr_statement = assertion.find("saml:AttributeStatement", ns)
        if attr_statement is not None:
            for attr_elem in attr_statement.findall("saml:Attribute", ns):
                attr_name = attr_elem.get("Name", "")
                values = [v.text for v in attr_elem.findall("saml:AttributeValue", ns) if v.text]
                if values:
                    attributes[attr_name] = values[0] if len(values) == 1 else values

        # Extract session index for SLO
        authn_statement = assertion.find("saml:AuthnStatement", ns)
        session_index = authn_statement.get("SessionIndex") if authn_statement is not None else None

        # Build result
        result = {
            "name_id": name_id,
            "email": _extract_email(name_id, attributes),
            "first_name": _extract_attribute(attributes, [
                "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname",
                "urn:oid:2.5.4.42",
                "FirstName",
                "first_name",
                "givenName",
            ]),
            "last_name": _extract_attribute(attributes, [
                "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname",
                "urn:oid:2.5.4.4",
                "LastName",
                "last_name",
                "sn",
            ]),
            "groups": _extract_groups(attributes),
            "session_index": session_index,
            "raw_attributes": attributes,
        }

        logger.info(f"SAML Response parsed: email={result['email']}, name_id={result['name_id']}")
        return True, result

    except Exception as e:
        logger.error(f"Failed to parse SAML Response: {e}")
        return False, {"error": str(e)}


def create_logout_request(
    idp_slo_url: str,
    name_id: str,
    session_index: Optional[str] = None,
    sp_entity_id: Optional[str] = None,
) -> str:
    """
    Create a SAML LogoutRequest and return the redirect URL.

    Args:
        idp_slo_url: IdP's SLO endpoint.
        name_id: The NameID of the user to log out.
        session_index: Optional session index from the original assertion.
        sp_entity_id: SP entity ID.

    Returns:
        Redirect URL to the IdP for SLO.
    """
    _sp_entity_id = sp_entity_id or SP_ENTITY_ID_DEFAULT
    request_id = f"_perennia_slo_{uuid.uuid4().hex}"
    issue_instant = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    session_index_xml = ""
    if session_index:
        session_index_xml = f'<samlp:SessionIndex>{session_index}</samlp:SessionIndex>'

    logout_request = f"""<samlp:LogoutRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="{request_id}"
    Version="2.0"
    IssueInstant="{issue_instant}"
    Destination="{idp_slo_url}">
  <saml:Issuer>{_sp_entity_id}</saml:Issuer>
  <saml:NameID Format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress">{name_id}</saml:NameID>
  {session_index_xml}
</samlp:LogoutRequest>"""

    deflated = zlib.compress(logout_request.encode("utf-8"))[2:-4]
    encoded = base64.b64encode(deflated).decode("utf-8")

    params = {"SAMLRequest": encoded}
    redirect_url = f"{idp_slo_url}?{urlencode(params)}"
    return redirect_url


# =============================================================================
# HELPERS
# =============================================================================

def _extract_email(name_id: str, attributes: Dict) -> str:
    """Extract email from NameID or attributes."""
    # If NameID looks like an email, use it
    if "@" in name_id:
        return name_id.lower()

    # Try common email attribute names
    email_keys = [
        "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
        "urn:oid:0.9.2342.19200300.100.1.3",
        "email",
        "Email",
        "mail",
    ]
    for key in email_keys:
        if key in attributes:
            val = attributes[key]
            if isinstance(val, list):
                val = val[0]
            if val and "@" in val:
                return val.lower()

    # Fallback: use NameID as-is
    return name_id.lower()


def _extract_attribute(attributes: Dict, possible_keys: list) -> Optional[str]:
    """Extract a single attribute value trying multiple possible key names."""
    for key in possible_keys:
        if key in attributes:
            val = attributes[key]
            if isinstance(val, list):
                return val[0]
            return val
    return None


def _extract_groups(attributes: Dict) -> list:
    """Extract group memberships from SAML attributes."""
    group_keys = [
        "http://schemas.xmlsoap.org/claims/Group",
        "http://schemas.microsoft.com/ws/2008/06/identity/claims/groups",
        "groups",
        "memberOf",
    ]
    for key in group_keys:
        if key in attributes:
            val = attributes[key]
            if isinstance(val, list):
                return val
            return [val]
    return []
