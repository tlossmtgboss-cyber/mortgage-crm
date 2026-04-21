"""Email open/click tracking service — pixel injection, link rewriting, score updates."""
import hashlib
import hmac
import logging
import os
import re
import uuid
from datetime import datetime
from typing import Optional, Dict, List

from sqlalchemy.orm import Session
from sqlalchemy import func

from database.models.email_tracking import EmailTrackingEvent, TrackingLinkMap

logger = logging.getLogger(__name__)

BASE_URL = "https://api.perenniaai.com"

# 1x1 transparent GIF
PIXEL_GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff"
    b"\x00\x00\x00!\xf9\x04\x00\x00\x00\x00\x00,"
    b"\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)

# ---------------------------------------------------------------------------
# HMAC-signed tracking tokens (SEC-005)
# ---------------------------------------------------------------------------

_TRACKING_SECRET = os.getenv("EMAIL_TRACKING_SECRET") or os.getenv("SECRET_KEY") or ""
if not _TRACKING_SECRET:
    logger.critical(
        "EMAIL_TRACKING_SECRET (or SECRET_KEY) not set — "
        "HMAC-signed tracking tokens will be rejected"
    )


def _get_tracking_secret() -> bytes:
    """Return the secret key used for HMAC-signing tracking tokens.

    Raises RuntimeError if no secret is configured, preventing silent
    operation with a weak hardcoded key.
    """
    if not _TRACKING_SECRET:
        raise RuntimeError(
            "EMAIL_TRACKING_SECRET or SECRET_KEY environment variable must be set "
            "for HMAC-signed email tracking. Cannot proceed with no key configured."
        )
    return _TRACKING_SECRET.encode("utf-8")


def sign_tracking_id(tracking_id: str) -> str:
    """Generate an HMAC-SHA256 signature for a tracking ID (SEC-005).

    Returns a 16-char hex digest (truncated for URL brevity).
    """
    return hmac.new(_get_tracking_secret(), tracking_id.encode("utf-8"), hashlib.sha256).hexdigest()[:16]


def verify_tracking_signature(tracking_id: str, signature: str) -> bool:
    """Verify that a tracking ID signature is valid (SEC-005).

    Uses constant-time comparison to prevent timing attacks.
    """
    expected = sign_tracking_id(tracking_id)
    return hmac.compare_digest(expected, signature)


def generate_tracking_id() -> str:
    return str(uuid.uuid4())


def _hash_link(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:12]


def inject_tracking(html_body: str, tracking_id: str, base_url: str = BASE_URL) -> tuple:
    """Inject tracking pixel and rewrite links. Returns (modified_html, link_mappings).

    All tracking URLs include an HMAC signature query param (SEC-005) to prevent
    spoofed open/click events from guessed or enumerated tracking IDs.
    """
    sig = sign_tracking_id(tracking_id)
    link_mappings = []

    # Rewrite <a href="..."> links
    def rewrite_link(match):
        original_url = match.group(1)
        if "unsubscribe" in original_url.lower() or original_url.startswith("mailto:"):
            return match.group(0)
        link_hash = _hash_link(original_url)
        link_mappings.append({"link_hash": link_hash, "original_url": original_url})
        tracking_url = f"{base_url}/api/v1/email-tracking/click/{tracking_id}/{link_hash}?sig={sig}"
        return match.group(0).replace(original_url, tracking_url)

    html_body = re.sub(r'<a\s+[^>]*href=["\']([^"\']+)["\']', rewrite_link, html_body, flags=re.IGNORECASE)

    # Insert tracking pixel before </body>
    pixel = f'<img src="{base_url}/api/v1/email-tracking/open/{tracking_id}.png?sig={sig}" width="1" height="1" style="display:none" alt="" />'
    if "</body>" in html_body.lower():
        html_body = re.sub(r"</body>", f"{pixel}</body>", html_body, flags=re.IGNORECASE)
    else:
        html_body += pixel

    return html_body, link_mappings


def store_link_mappings(db: Session, tracking_id: str, link_mappings: List[Dict]):
    """Persist link hash → original URL mappings for click resolution."""
    for mapping in link_mappings:
        db.add(TrackingLinkMap(
            tracking_id=tracking_id,
            link_hash=mapping["link_hash"],
            original_url=mapping["original_url"],
        ))
    db.commit()


def record_open(db: Session, tracking_id: str, ip: str = None, user_agent: str = None, org_id: str = None):
    """Record email open event and update lead score."""
    try:
        event = EmailTrackingEvent(
            tracking_id=tracking_id,
            event_type="open",
            ip_address=ip,
            user_agent=user_agent,
            organization_id=org_id or "unknown",
        )
        db.add(event)
        db.commit()

        # Update lead score +2 if we can find the lead
        _update_lead_score(db, tracking_id, delta=2)
    except Exception:
        logger.exception(f"Failed to record open for tracking_id={tracking_id}")
        db.rollback()


def record_click(db: Session, tracking_id: str, link_hash: str, ip: str = None, user_agent: str = None, org_id: str = None) -> Optional[str]:
    """Record click event, update lead score, return original URL."""
    original_url = None
    try:
        # Look up original URL
        link_map = db.query(TrackingLinkMap).filter(
            TrackingLinkMap.tracking_id == tracking_id,
            TrackingLinkMap.link_hash == link_hash,
        ).first()
        original_url = link_map.original_url if link_map else None

        event = EmailTrackingEvent(
            tracking_id=tracking_id,
            event_type="click",
            link_url=original_url,
            link_hash=link_hash,
            ip_address=ip,
            user_agent=user_agent,
            organization_id=org_id or "unknown",
        )
        db.add(event)
        db.commit()

        # Update lead score +5
        _update_lead_score(db, tracking_id, delta=5)
    except Exception:
        logger.exception(f"Failed to record click for tracking_id={tracking_id}")
        db.rollback()

    return original_url


def get_tracking_stats(db: Session, tracking_id: str) -> Dict:
    """Get tracking stats for an email."""
    events = db.query(EmailTrackingEvent).filter(
        EmailTrackingEvent.tracking_id == tracking_id,
    ).all()

    opens = [e for e in events if e.event_type == "open"]
    clicks = [e for e in events if e.event_type == "click"]

    unique_open_ips = set(e.ip_address for e in opens if e.ip_address)
    unique_click_ips = set(e.ip_address for e in clicks if e.ip_address)

    click_details = {}
    for c in clicks:
        url = c.link_url or c.link_hash
        click_details[url] = click_details.get(url, 0) + 1

    return {
        "tracking_id": tracking_id,
        "opens": len(opens),
        "unique_opens": len(unique_open_ips),
        "clicks": len(clicks),
        "unique_clicks": len(unique_click_ips),
        "first_opened": opens[0].created_at.isoformat() if opens else None,
        "last_opened": opens[-1].created_at.isoformat() if opens else None,
        "click_details": [{"url": url, "count": count} for url, count in click_details.items()],
    }


def _update_lead_score(db: Session, tracking_id: str, delta: int):
    """Try to update the lead score associated with this tracking_id."""
    try:
        from database.models.communication import EmailMessage
        email = db.query(EmailMessage).filter(
            EmailMessage.tracking_id == tracking_id,
        ).first()
        if email and email.lead_id:
            from database.models.lead_loan import Lead
            lead = db.query(Lead).filter(Lead.id == email.lead_id).first()
            if lead and hasattr(lead, "ai_score") and lead.ai_score is not None:
                lead.ai_score = min(100, (lead.ai_score or 0) + delta)
                db.commit()
    except Exception:
        logger.debug(f"Could not update lead score for tracking_id={tracking_id}")
