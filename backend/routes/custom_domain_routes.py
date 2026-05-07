"""
Custom Domain SSL Routes — White-Label Portal Domains

API endpoints for enterprise custom-domain provisioning. Stores domain state
in WhiteLabelConfig (organization_branding table) and optionally
integrates with Vercel for automatic SSL cert issuance.

Admin endpoints (original):
  1. POST  /api/v1/admin/custom-domain/setup   — Register domain, get TXT token
  2. Add TXT DNS record at registrar
  3. POST  /api/v1/admin/custom-domain/verify   — DNS lookup; marks verified, calls Vercel
  4. GET   /api/v1/admin/custom-domain/status   — Poll SSL status
  5. DELETE /api/v1/admin/custom-domain          — Remove domain and revoke Vercel entry

White-label endpoints (Domain 12):
  1. POST  /api/v1/white-label/domain/configure — Set custom domain (validates format)
  2. POST  /api/v1/white-label/domain/verify    — DNS verification (TXT + CNAME check)
  3. GET   /api/v1/white-label/domain/status     — Current domain + SSL status

Registered via register_custom_domain_routes(app, get_db_func, get_current_user_flexible)
from main.py — never imported at module load time to avoid circular imports.

Requires admin / site_admin / platform_admin permission role.
"""

import logging
import re
import uuid

logger = logging.getLogger(__name__)

# Expected CNAME target for custom domains
_CNAME_TARGET = "cname.vercel-dns.com"

_ADMIN_ROLES = {"admin", "site_admin", "platform_admin"}


def register_custom_domain_routes(app, get_db_func, get_current_user_flexible):
    """Register custom-domain endpoints with the FastAPI app.

    Called from main.py during startup. All auth/DB dependencies are received
    as arguments — no module-level imports from main.py.

    Startup side-effect: runs ADD COLUMN IF NOT EXISTS migrations for the four
    new SSL columns on organization_branding (canonical branding table).
    """
    from fastapi import Depends, HTTPException, status
    from pydantic import BaseModel
    from sqlalchemy.orm import Session
    from sqlalchemy import text

    # ------------------------------------------------------------------ #
    # Startup migration — idempotent, safe to run on every deploy          #
    # ------------------------------------------------------------------ #
    try:
        db_gen = get_db_func()
        db = next(db_gen)
        for col, col_type, default in [
            ("ssl_status", "VARCHAR(20)", "'pending'"),
            ("ssl_expires_at", "TIMESTAMP", "NULL"),
            ("domain_verified", "BOOLEAN", "FALSE"),
            ("domain_verification_token", "VARCHAR(100)", "NULL"),
            ("vercel_domain_id", "VARCHAR(100)", "NULL"),
        ]:
            db.execute(
                text(
                    f"ALTER TABLE organization_branding "
                    f"ADD COLUMN IF NOT EXISTS {col} {col_type} DEFAULT {default}"
                )
            )
        db.commit()
        logger.info("Custom domain columns migrated on organization_branding")
    except Exception as exc:
        logger.warning("Custom domain column migration skipped: %s", exc)

    # ------------------------------------------------------------------ #
    # Pydantic schemas                                                      #
    # ------------------------------------------------------------------ #

    class DomainSetupRequest(BaseModel):
        domain: str  # e.g. "portal.acmemortgage.com"

    # ------------------------------------------------------------------ #
    # Helpers                                                               #
    # ------------------------------------------------------------------ #

    def _require_admin(current_user):
        role = getattr(current_user, "permission_role", None) or ""
        if role not in _ADMIN_ROLES:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin role required for custom domain management.",
            )

    def _get_white_label_config(db: Session, organization_id: int):
        """Return the org's WhiteLabelConfig row or None."""
        from database.models.white_label_config import WhiteLabelConfig

        return (
            db.query(WhiteLabelConfig)
            .filter(
                WhiteLabelConfig.organization_id == organization_id,
                WhiteLabelConfig.is_active == True,
                WhiteLabelConfig.setting_type.is_(None),
            )
            .first()
        )

    def _clean_domain(raw: str) -> str:
        """Strip protocol prefix and lowercase."""
        domain = raw.lower().strip()
        for prefix in ("https://", "http://"):
            if domain.startswith(prefix):
                domain = domain[len(prefix):]
        return domain.rstrip("/")

    # ------------------------------------------------------------------ #
    # POST /api/v1/admin/custom-domain/setup                               #
    # ------------------------------------------------------------------ #

    @app.post("/api/v1/admin/custom-domain/setup", tags=["Custom Domain SSL"])
    async def setup_custom_domain(
        body: DomainSetupRequest,
        db: Session = Depends(get_db_func),
        current_user=Depends(get_current_user_flexible),
    ):
        """Initiate custom-domain setup for the caller's organisation.

        Generates a verification token (UUID-based TXT record value), stores it
        alongside the domain in WhiteLabelConfig, and returns DNS instructions.

        The caller must:
        1. Create a DNS TXT record ``_perennia-verify.<domain>`` with the
           returned ``verification_token`` value.
        2. Create a DNS CNAME record pointing the domain to
           ``cname.vercel-dns.com``.
        3. Call POST /api/v1/admin/custom-domain/verify once DNS has propagated.
        """
        _require_admin(current_user)

        organization_id = getattr(current_user, "organization_id", None)
        if organization_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No organization associated with this user.",
            )

        domain = _clean_domain(body.domain)
        if not domain:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid domain value.",
            )

        config = _get_white_label_config(db, organization_id)
        if config is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    "No active white-label configuration found for your organisation. "
                    "Create one first via the White-Label settings."
                ),
            )

        # Generate a fresh verification token
        verification_token = f"perennia-verify={uuid.uuid4().hex}"

        config.custom_domain = domain
        config.domain_verification_token = verification_token
        config.domain_verified = False
        config.ssl_status = "pending"
        config.vercel_domain_id = None
        db.commit()

        txt_record_name = f"_perennia-verify.{domain}"
        return {
            "domain": domain,
            "verification_token": verification_token,
            "dns_instructions": {
                "txt_record": {
                    "name": txt_record_name,
                    "type": "TXT",
                    "value": verification_token,
                    "purpose": "Domain ownership verification",
                },
                "cname_record": {
                    "name": domain,
                    "type": "CNAME",
                    "value": "cname.vercel-dns.com",
                    "purpose": "Route traffic to Perennia portal",
                },
            },
            "message": (
                f"Add the TXT record {txt_record_name} = {verification_token} "
                "to your DNS, then call /verify."
            ),
            "next_step": "POST /api/v1/admin/custom-domain/verify",
        }

    # ------------------------------------------------------------------ #
    # POST /api/v1/admin/custom-domain/verify                              #
    # ------------------------------------------------------------------ #

    @app.post("/api/v1/admin/custom-domain/verify", tags=["Custom Domain SSL"])
    async def verify_custom_domain(
        db: Session = Depends(get_db_func),
        current_user=Depends(get_current_user_flexible),
    ):
        """Verify domain ownership via DNS TXT lookup.

        Performs a live DNS query for the TXT record placed by the client. On
        success:
        - Sets ``domain_verified = True`` and ``ssl_status = "provisioning"``
        - Calls Vercel API to add the domain (triggers SSL cert issuance)
        - Stores the Vercel domain ID for future management

        Vercel integration is best-effort — if VERCEL_TOKEN / VERCEL_PROJECT_ID
        are not set the domain is still marked verified and manual DNS works.
        """
        _require_admin(current_user)

        organization_id = getattr(current_user, "organization_id", None)
        if organization_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No organization associated with this user.",
            )

        config = _get_white_label_config(db, organization_id)
        if config is None or not config.custom_domain:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No custom domain configured. Call /setup first.",
            )

        domain = config.custom_domain
        expected_token = config.domain_verification_token

        if not expected_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No verification token found. Call /setup first.",
            )

        # ---- DNS TXT lookup ------------------------------------------ #
        txt_record_name = f"_perennia-verify.{domain}"
        verified = False
        dns_error = None

        try:
            import dns.resolver  # dnspython

            answers = dns.resolver.resolve(txt_record_name, "TXT")
            found_values = []
            for rdata in answers:
                for string in rdata.strings:
                    found_values.append(string.decode("utf-8", errors="replace"))

            if expected_token in found_values:
                verified = True
            else:
                dns_error = (
                    f"TXT record found but value did not match. "
                    f"Expected '{expected_token}', found: {found_values}"
                )
        except Exception as exc:
            dns_error = f"DNS lookup failed: {exc}"

        if not verified:
            return {
                "verified": False,
                "ssl_status": config.ssl_status,
                "message": (
                    dns_error
                    or "Verification token not found in DNS. Check record and retry."
                ),
            }

        # ---- Mark verified ------------------------------------------- #
        config.domain_verified = True
        config.ssl_status = "provisioning"

        # ---- Vercel integration (best-effort) ------------------------- #
        vercel_domain_id = None
        vercel_warning = None
        try:
            from services import vercel_domain_service

            result = vercel_domain_service.add_domain(domain)
            if result and not result.get("error") and not result.get("skipped"):
                vercel_domain_id = result.get("name") or result.get("id") or domain
                config.ssl_status = "provisioning"
                logger.info("Vercel domain added: %s -> %s", domain, vercel_domain_id)
            elif result and result.get("error"):
                error_type = result.get("error_type", "VercelDomainError")
                vercel_warning = result["error"]
                logger.warning(
                    "Vercel add_domain returned error for %s: [%s] %s",
                    domain, error_type, result["error"],
                )
        except Exception as exc:
            vercel_warning = f"Vercel integration unavailable: {exc}"
            logger.warning("Vercel add_domain failed for %s: %s", domain, exc)

        config.vercel_domain_id = vercel_domain_id
        db.commit()

        response = {
            "verified": True,
            "ssl_status": config.ssl_status,
            "vercel_domain_id": vercel_domain_id,
            "message": (
                "Domain ownership verified. SSL provisioning is underway — "
                "check /status in a few minutes."
            ),
        }
        if vercel_warning:
            response["vercel_warning"] = vercel_warning
        return response

    # ------------------------------------------------------------------ #
    # GET /api/v1/admin/custom-domain/status                               #
    # ------------------------------------------------------------------ #

    @app.get("/api/v1/admin/custom-domain/status", tags=["Custom Domain SSL"])
    async def get_custom_domain_status(
        db: Session = Depends(get_db_func),
        current_user=Depends(get_current_user_flexible),
    ):
        """Return the current custom-domain state for the caller's organisation.

        If Vercel credentials are present, also polls the Vercel API to refresh
        the SSL status before returning.
        """
        _require_admin(current_user)

        organization_id = getattr(current_user, "organization_id", None)
        if organization_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No organization associated with this user.",
            )

        config = _get_white_label_config(db, organization_id)
        if config is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active white-label configuration found.",
            )

        if not config.custom_domain:
            return {
                "domain": None,
                "domain_verified": False,
                "ssl_status": "pending",
                "vercel_domain_id": None,
                "message": "No custom domain configured yet.",
            }

        # Refresh SSL status from Vercel if we have credentials and a domain ID
        if config.domain_verified and config.custom_domain:
            try:
                from services import vercel_domain_service

                live_ssl = vercel_domain_service.check_ssl_status(config.custom_domain)
                if live_ssl not in ("unknown", config.ssl_status):
                    config.ssl_status = live_ssl
                    db.commit()
            except Exception as exc:
                logger.warning("Vercel SSL status check failed: %s", exc)

        return {
            "domain": config.custom_domain,
            "domain_verified": bool(config.domain_verified),
            "ssl_status": config.ssl_status or "pending",
            "vercel_domain_id": config.vercel_domain_id,
            "verification_token": config.domain_verification_token,
        }

    # ------------------------------------------------------------------ #
    # DELETE /api/v1/admin/custom-domain                                   #
    # ------------------------------------------------------------------ #

    @app.delete("/api/v1/admin/custom-domain", tags=["Custom Domain SSL"])
    async def remove_custom_domain(
        db: Session = Depends(get_db_func),
        current_user=Depends(get_current_user_flexible),
    ):
        """Remove the custom domain for the caller's organisation.

        - Calls Vercel API to deregister the domain (best-effort)
        - Clears all domain columns on WhiteLabelConfig
        """
        _require_admin(current_user)

        organization_id = getattr(current_user, "organization_id", None)
        if organization_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No organization associated with this user.",
            )

        config = _get_white_label_config(db, organization_id)
        if config is None or not config.custom_domain:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No custom domain configured.",
            )

        domain = config.custom_domain

        # Vercel removal (best-effort)
        try:
            from services import vercel_domain_service

            vercel_domain_service.remove_domain(domain)
        except Exception as exc:
            logger.warning("Vercel remove_domain failed for %s: %s", domain, exc)

        # Clear all domain columns
        config.custom_domain = None
        config.ssl_status = "pending"
        config.domain_verified = False
        config.domain_verification_token = None
        config.vercel_domain_id = None
        db.commit()

        return {
            "success": True,
            "message": f"Custom domain '{domain}' removed successfully.",
        }

    # ------------------------------------------------------------------ #
    # Domain format validation helper                                      #
    # ------------------------------------------------------------------ #

    _DOMAIN_PATTERN = re.compile(
        r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.[A-Za-z0-9-]{1,63})*\.[A-Za-z]{2,}$"
    )

    def _validate_domain_format(domain: str) -> str | None:
        """Return an error message if domain format is invalid, else None."""
        if not domain or len(domain) > 253:
            return "Domain must be between 1 and 253 characters."
        if not _DOMAIN_PATTERN.match(domain):
            return (
                "Invalid domain format. Use a fully qualified domain name "
                "(e.g. portal.example.com). No protocol prefix or trailing slash."
            )
        # Block bare TLDs and common reserved domains
        if domain.count(".") < 1:
            return "Domain must have at least two labels (e.g. portal.example.com)."
        return None

    # ------------------------------------------------------------------ #
    # DNS lookup helpers                                                    #
    # ------------------------------------------------------------------ #

    def _check_txt_record(domain: str, expected_token: str) -> tuple[bool, str | None]:
        """Check TXT record for domain verification.

        Returns (verified, error_message).
        """
        txt_record_name = f"_perennia-verify.{domain}"
        try:
            import dns.resolver

            answers = dns.resolver.resolve(txt_record_name, "TXT")
            found_values = []
            for rdata in answers:
                for s in rdata.strings:
                    found_values.append(s.decode("utf-8", errors="replace"))

            if expected_token in found_values:
                return True, None
            return False, (
                f"TXT record found but value did not match. "
                f"Expected '{expected_token}', found: {found_values}"
            )
        except Exception as exc:
            return False, f"TXT lookup for {txt_record_name} failed: {exc}"

    def _check_cname_record(domain: str) -> tuple[bool, str | None]:
        """Check CNAME record points to the expected target.

        Returns (matches, error_message).
        """
        try:
            import dns.resolver

            answers = dns.resolver.resolve(domain, "CNAME")
            targets = [rdata.target.to_text().rstrip(".").lower() for rdata in answers]

            if _CNAME_TARGET in targets:
                return True, None
            return False, (
                f"CNAME record found but target did not match. "
                f"Expected '{_CNAME_TARGET}', found: {targets}"
            )
        except dns.resolver.NoAnswer:
            # May be an A record or ALIAS instead (some providers don't use CNAME
            # for apex domains). Fall back to checking if it resolves at all.
            return False, (
                f"No CNAME record found for {domain}. "
                f"Ensure a CNAME pointing to {_CNAME_TARGET} exists."
            )
        except dns.resolver.NXDOMAIN:
            return False, f"Domain {domain} does not exist in DNS."
        except Exception as exc:
            return False, f"CNAME lookup for {domain} failed: {exc}"

    # ================================================================== #
    # White-Label Domain Endpoints (Domain 12)                             #
    # ================================================================== #

    # ------------------------------------------------------------------ #
    # POST /api/v1/white-label/domain/configure                            #
    # ------------------------------------------------------------------ #

    @app.post("/api/v1/white-label/domain/configure", tags=["White-Label Domain"])
    async def configure_white_label_domain(
        body: DomainSetupRequest,
        db: Session = Depends(get_db_func),
        current_user=Depends(get_current_user_flexible),
    ):
        """Set or update the custom domain for the org's white-label portal.

        Validates the domain format, generates a verification token, and returns
        DNS instructions. The caller must create the required DNS records and
        then call POST /api/v1/white-label/domain/verify.
        """
        _require_admin(current_user)

        organization_id = getattr(current_user, "organization_id", None)
        if organization_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No organization associated with this user.",
            )

        domain = _clean_domain(body.domain)

        # Validate domain format
        validation_error = _validate_domain_format(domain)
        if validation_error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=validation_error,
            )

        config = _get_white_label_config(db, organization_id)
        if config is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    "No active white-label configuration found for your organisation. "
                    "Create one first via the White-Label settings."
                ),
            )

        # Generate verification token
        verification_token = f"perennia-verify={uuid.uuid4().hex}"

        config.custom_domain = domain
        config.domain_verification_token = verification_token
        config.domain_verified = False
        config.ssl_status = "pending"
        config.vercel_domain_id = None
        db.commit()

        txt_record_name = f"_perennia-verify.{domain}"
        return {
            "domain": domain,
            "verification_token": verification_token,
            "ssl_status": "pending",
            "dns_instructions": {
                "txt_record": {
                    "name": txt_record_name,
                    "type": "TXT",
                    "value": verification_token,
                    "purpose": "Domain ownership verification",
                },
                "cname_record": {
                    "name": domain,
                    "type": "CNAME",
                    "value": _CNAME_TARGET,
                    "purpose": "Route traffic to Perennia portal",
                },
            },
            "next_step": "POST /api/v1/white-label/domain/verify",
        }

    # ------------------------------------------------------------------ #
    # POST /api/v1/white-label/domain/verify                               #
    # ------------------------------------------------------------------ #

    @app.post("/api/v1/white-label/domain/verify", tags=["White-Label Domain"])
    async def verify_white_label_domain(
        db: Session = Depends(get_db_func),
        current_user=Depends(get_current_user_flexible),
    ):
        """Verify domain ownership via DNS TXT + CNAME lookup.

        Checks both:
        1. TXT record at ``_perennia-verify.<domain>`` matches the stored token.
        2. CNAME record on ``<domain>`` points to ``cname.vercel-dns.com``.

        On full verification, marks the domain as verified and triggers Vercel
        SSL provisioning (best-effort). Updates ssl_status through the lifecycle:
        pending -> verified -> provisioning -> active (or failed).
        """
        _require_admin(current_user)

        organization_id = getattr(current_user, "organization_id", None)
        if organization_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No organization associated with this user.",
            )

        config = _get_white_label_config(db, organization_id)
        if config is None or not config.custom_domain:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No custom domain configured. Call /configure first.",
            )

        domain = config.custom_domain
        expected_token = config.domain_verification_token

        if not expected_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No verification token found. Call /configure first.",
            )

        # ---- DNS checks ------------------------------------------------ #
        txt_ok, txt_error = _check_txt_record(domain, expected_token)
        cname_ok, cname_error = _check_cname_record(domain)

        checks = {
            "txt_record": {
                "passed": txt_ok,
                "error": txt_error,
            },
            "cname_record": {
                "passed": cname_ok,
                "error": cname_error,
            },
        }

        if not txt_ok:
            # TXT is mandatory for ownership proof
            config.ssl_status = "pending"
            db.commit()
            return {
                "verified": False,
                "ssl_status": "pending",
                "checks": checks,
                "message": (
                    "Domain ownership not verified. "
                    "Ensure the TXT record is set correctly and DNS has propagated."
                ),
            }

        # TXT passed — mark ownership verified
        config.domain_verified = True

        if not cname_ok:
            # Ownership proven but routing not set up
            config.ssl_status = "verified"
            db.commit()
            return {
                "verified": True,
                "ssl_status": "verified",
                "checks": checks,
                "message": (
                    "Domain ownership verified, but CNAME record is missing or "
                    f"not pointing to {_CNAME_TARGET}. SSL cannot be provisioned "
                    "until CNAME is configured."
                ),
            }

        # Both checks passed — provision SSL
        config.ssl_status = "provisioning"

        # ---- Vercel integration (best-effort) ------------------------- #
        vercel_domain_id = None
        vercel_warning = None
        try:
            from services import vercel_domain_service

            result = vercel_domain_service.add_domain(domain)
            if result and not result.get("error") and not result.get("skipped"):
                vercel_domain_id = result.get("name") or result.get("id") or domain
                logger.info("Vercel domain added: %s -> %s", domain, vercel_domain_id)
            elif result and result.get("error"):
                error_type = result.get("error_type", "VercelDomainError")
                vercel_warning = result["error"]
                logger.warning(
                    "Vercel add_domain returned error for %s: [%s] %s",
                    domain, error_type, result["error"],
                )
        except Exception as exc:
            vercel_warning = f"Vercel integration unavailable: {exc}"
            logger.warning("Vercel add_domain failed for %s: %s", domain, exc)

        config.vercel_domain_id = vercel_domain_id
        db.commit()

        response = {
            "verified": True,
            "ssl_status": config.ssl_status,
            "checks": checks,
            "vercel_domain_id": vercel_domain_id,
            "message": (
                "Domain fully verified. SSL provisioning is underway — "
                "check /status in a few minutes."
            ),
        }
        if vercel_warning:
            response["vercel_warning"] = vercel_warning
        return response

    # ------------------------------------------------------------------ #
    # GET /api/v1/white-label/domain/status                                #
    # ------------------------------------------------------------------ #

    @app.get("/api/v1/white-label/domain/status", tags=["White-Label Domain"])
    async def get_white_label_domain_status(
        db: Session = Depends(get_db_func),
        current_user=Depends(get_current_user_flexible),
    ):
        """Return current domain configuration and SSL status.

        If Vercel credentials are present and the domain is verified, polls
        Vercel for a live SSL status update before responding.
        """
        _require_admin(current_user)

        organization_id = getattr(current_user, "organization_id", None)
        if organization_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No organization associated with this user.",
            )

        config = _get_white_label_config(db, organization_id)
        if config is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active white-label configuration found.",
            )

        if not config.custom_domain:
            return {
                "configured": False,
                "domain": None,
                "domain_verified": False,
                "ssl_status": "pending",
                "vercel_domain_id": None,
                "message": "No custom domain configured yet.",
            }

        # Refresh SSL status and expiry from Vercel if domain is verified
        ssl_expires_at = getattr(config, "ssl_expires_at", None)
        ssl_expires_in_days = None
        ssl_renewal_warning = None

        if config.domain_verified and config.vercel_domain_id:
            try:
                from services import vercel_domain_service
                from datetime import datetime as _dt, timezone as _tz

                live_ssl = vercel_domain_service.check_ssl_status(config.custom_domain)
                if live_ssl not in ("unknown", config.ssl_status):
                    config.ssl_status = live_ssl

                # Fetch SSL expiry from Vercel
                vercel_expiry = vercel_domain_service.get_ssl_expiry(config.custom_domain)
                if vercel_expiry:
                    ssl_expires_at = vercel_expiry
                    config.ssl_expires_at = vercel_expiry

                db.commit()
            except Exception as exc:
                logger.warning("Vercel SSL status/expiry check failed: %s", exc)

        if ssl_expires_at:
            from datetime import datetime as _dt, timezone as _tz
            now = _dt.now(_tz.utc)
            ssl_expires_in_days = (ssl_expires_at - now).days
            if ssl_expires_in_days <= 0:
                ssl_renewal_warning = (
                    "SSL certificate has EXPIRED. Visitors will see security warnings."
                )
            elif ssl_expires_in_days <= 30:
                ssl_renewal_warning = (
                    f"SSL certificate expires in {ssl_expires_in_days} days "
                    f"({ssl_expires_at.strftime('%Y-%m-%d')}). "
                    "Verify auto-renewal is not blocked by DNS issues."
                )

        response = {
            "configured": True,
            "domain": config.custom_domain,
            "domain_verified": bool(config.domain_verified),
            "ssl_status": config.ssl_status or "pending",
            "ssl_expires_at": ssl_expires_at.isoformat() if ssl_expires_at else None,
            "ssl_expires_in_days": ssl_expires_in_days,
            "ssl_renewal_warning": ssl_renewal_warning,
            "vercel_domain_id": config.vercel_domain_id,
            "verification_token": config.domain_verification_token,
            "dns_instructions": {
                "txt_record": {
                    "name": f"_perennia-verify.{config.custom_domain}",
                    "type": "TXT",
                    "value": config.domain_verification_token,
                },
                "cname_record": {
                    "name": config.custom_domain,
                    "type": "CNAME",
                    "value": _CNAME_TARGET,
                },
            } if not config.domain_verified else None,
        }
        return response

    # ================================================================== #
    # White-Label Compliance Check (Domain 12)                             #
    # ================================================================== #

    # ------------------------------------------------------------------ #
    # GET /api/v1/white-label/compliance-check                             #
    # ------------------------------------------------------------------ #

    @app.get("/api/v1/white-label/compliance-check", tags=["White-Label Domain"])
    async def white_label_compliance_check(
        db: Session = Depends(get_db_func),
        current_user=Depends(get_current_user_flexible),
    ):
        """Run a unified white-label compliance check for the caller's org.

        Combines portal branding completeness, branding leak scan, and custom
        domain health into a single compliance report with action items.

        Returns:
          - portal_branding: completeness checks (logo, colors, fonts, etc.)
          - branding_leaks: platform-name references in tenant output
          - domain_health: SSL expiry, domain verification, provisioning status
          - action_items: prioritized list of things to fix
          - overall_score: 0-100 compliance score
        """
        _require_admin(current_user)

        organization_id = getattr(current_user, "organization_id", None)
        if organization_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No organization associated with this user.",
            )

        from services.white_label_service import (
            check_portal_branding,
            scan_for_branding_leaks,
            check_domain_health,
        )

        portal_result = check_portal_branding(db, organization_id)
        leak_result = scan_for_branding_leaks(db, organization_id)
        domain_result = check_domain_health(db, organization_id)

        # Build prioritized action items
        action_items = []

        # Portal branding actions
        for check_name, passed in portal_result.get("checks", {}).items():
            if not passed:
                action_items.append({
                    "category": "portal_branding",
                    "priority": "high" if check_name in ("logo", "company_name") else "medium",
                    "action": f"Configure {check_name.replace('_', ' ')} in White-Label settings.",
                })

        # Branding leak actions
        for leak in leak_result.get("leaks", []):
            action_items.append({
                "category": "branding_leak",
                "priority": leak.get("severity", "medium"),
                "action": leak.get("fix", f"Fix branding leak in {leak.get('location', 'unknown')}"),
            })

        # Domain health actions
        for warning in domain_result.get("warnings", []):
            code = warning.get("code", "")
            if code in ("ALL_CLEAR", "NO_CUSTOM_DOMAIN"):
                continue
            action_items.append({
                "category": "domain_health",
                "priority": warning.get("severity", "medium"),
                "action": warning.get("message", "Address domain issue"),
            })

        # Sort: critical > high > medium > low > info
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
        action_items.sort(key=lambda x: priority_order.get(x.get("priority", "info"), 4))

        # Compute overall score (0-100)
        # Portal branding: 50 points (proportional to completion %)
        portal_score = (portal_result.get("completion_pct", 0) / 100) * 50

        # Branding leaks: 25 points (0 leaks = 25, each leak deducts points)
        leak_count = leak_result.get("leaks_found", 0)
        leak_score = max(0, 25 - (leak_count * 5))

        # Domain health: 25 points
        domain_score = 25
        if not domain_result.get("healthy", True):
            domain_score = 5
        elif any(
            w.get("severity") in ("high", "critical")
            for w in domain_result.get("warnings", [])
            if w.get("code") not in ("ALL_CLEAR", "NO_CUSTOM_DOMAIN")
        ):
            domain_score = 15

        overall_score = round(portal_score + leak_score + domain_score)

        from datetime import datetime as _dt, timezone as _tz

        return {
            "org_id": organization_id,
            "overall_score": overall_score,
            "grade": (
                "A+" if overall_score >= 95 else
                "A" if overall_score >= 90 else
                "B" if overall_score >= 75 else
                "C" if overall_score >= 60 else
                "D" if overall_score >= 40 else "F"
            ),
            "portal_branding": portal_result,
            "branding_leaks": leak_result,
            "domain_health": domain_result,
            "action_items": action_items,
            "action_items_count": len(action_items),
            "checked_at": _dt.now(_tz.utc).isoformat(),
        }

    # ================================================================== #
    # SSL Expiry Alerts (Domain 12, Check 12.10)                           #
    # ================================================================== #

    # ------------------------------------------------------------------ #
    # GET /api/v1/white-label/ssl-alerts                                   #
    # ------------------------------------------------------------------ #

    @app.get("/api/v1/white-label/ssl-alerts", tags=["White-Label Domain"])
    async def get_ssl_expiry_alerts(
        db: Session = Depends(get_db_func),
        current_user=Depends(get_current_user_flexible),
    ):
        """Return proactive SSL expiry alerts for all custom domains.

        Queries all organizations with custom domains and checks for SSL
        certificates expiring within 30 days. Returns alerts sorted by
        urgency (fewest days remaining first).

        Severity levels:
          - critical: expired or expiring within 7 days
          - warning: expiring within 14-30 days
          - ok: more than 30 days remaining (not included in alerts)

        Requires admin role.
        """
        _require_admin(current_user)

        from services.white_label_service import check_ssl_expiry_alerts

        return check_ssl_expiry_alerts(db)

    # ================================================================== #
    # Branding Completeness Check (Domain 12, Check 12.7b)                 #
    # ================================================================== #

    # ------------------------------------------------------------------ #
    # GET /api/v1/white-label/branding-completeness                        #
    # ------------------------------------------------------------------ #

    @app.get("/api/v1/white-label/branding-completeness", tags=["White-Label Domain"])
    async def get_branding_completeness(
        db: Session = Depends(get_db_func),
        current_user=Depends(get_current_user_flexible),
    ):
        """Check branding configuration completeness for the caller's org.

        Verifies that all required branding fields are set (company_name,
        logo_url, primary_color at minimum) and returns a completeness
        percentage along with a list of missing fields.

        Requires admin role.
        """
        _require_admin(current_user)

        organization_id = getattr(current_user, "organization_id", None)
        if organization_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No organization associated with this user.",
            )

        from services.white_label_service import check_branding_completeness

        return check_branding_completeness(db, organization_id)
