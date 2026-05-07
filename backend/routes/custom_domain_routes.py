"""
Custom Domain SSL Routes — White-Label Portal Domains

API endpoints for enterprise custom-domain provisioning. Stores domain state
in WhiteLabelConfig (organization_branding table) and optionally
integrates with Vercel for automatic SSL cert issuance.

Flow:
  1. POST  /api/v1/admin/custom-domain/setup   — Register domain, get TXT token
  2. Add TXT DNS record at registrar
  3. POST  /api/v1/admin/custom-domain/verify   — DNS lookup; marks verified, calls Vercel
  4. GET   /api/v1/admin/custom-domain/status   — Poll SSL status
  5. DELETE /api/v1/admin/custom-domain          — Remove domain and revoke Vercel entry

Registered via register_custom_domain_routes(app, get_db_func, get_current_user_flexible)
from main.py — never imported at module load time to avoid circular imports.

Requires admin / site_admin / platform_admin permission role.
"""

import logging
import uuid

logger = logging.getLogger(__name__)

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
        try:
            from services import vercel_domain_service

            result = vercel_domain_service.add_domain(domain)
            # Vercel returns {"name": domain, "apexName": ..., ...} on success
            if result and not result.get("error") and not result.get("skipped"):
                vercel_domain_id = result.get("name") or result.get("id") or domain
                config.ssl_status = "provisioning"
                logger.info("Vercel domain added: %s -> %s", domain, vercel_domain_id)
        except Exception as exc:
            logger.warning("Vercel add_domain failed for %s: %s", domain, exc)

        config.vercel_domain_id = vercel_domain_id
        db.commit()

        return {
            "verified": True,
            "ssl_status": config.ssl_status,
            "vercel_domain_id": vercel_domain_id,
            "message": (
                "Domain ownership verified. SSL provisioning is underway — "
                "check /status in a few minutes."
            ),
        }

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
