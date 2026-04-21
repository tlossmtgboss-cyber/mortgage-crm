"""
Visitor Tracking Routes
=======================
Track website visitors and auto-create leads in Admin CRM.
Captures IP, user agent, referrer, pages visited, and visit frequency.
"""

import os
import logging
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import text

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/visitor-tracking", tags=["Visitor Tracking"])

# Import canonical RLS-aware get_db from db.py
from db import get_db


# =============================================================================
# MODELS
# =============================================================================

class VisitorTrackRequest(BaseModel):
    """Request model for tracking a visitor."""
    page_url: str
    page_title: Optional[str] = None
    referrer: Optional[str] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    utm_term: Optional[str] = None
    utm_content: Optional[str] = None
    screen_width: Optional[int] = None
    screen_height: Optional[int] = None
    timezone: Optional[str] = None
    language: Optional[str] = None
    visitor_id: Optional[str] = None  # Client-side generated ID for anonymous tracking


class VisitorTrackResponse(BaseModel):
    """Response model for visitor tracking."""
    success: bool
    visitor_id: str
    visit_count: int
    is_new_visitor: bool
    message: str


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_client_ip(request: Request) -> str:
    """Extract client IP from request, handling proxies."""
    # Check for forwarded headers (common with proxies/load balancers)
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        # Take the first IP in the chain (original client)
        return forwarded_for.split(",")[0].strip()

    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()

    # Fall back to direct client IP
    if request.client:
        return request.client.host

    return "unknown"


def generate_visitor_hash(ip: str, user_agent: str) -> str:
    """Generate a consistent hash for visitor identification."""
    # Create a hash from IP + user agent for fingerprinting
    fingerprint = f"{ip}:{user_agent}"
    return hashlib.sha256(fingerprint.encode()).hexdigest()[:32]


def parse_user_agent(user_agent: str) -> dict:
    """Parse user agent string to extract device info."""
    ua_lower = user_agent.lower()

    # Detect device type
    if "mobile" in ua_lower or "android" in ua_lower or "iphone" in ua_lower:
        device_type = "mobile"
    elif "tablet" in ua_lower or "ipad" in ua_lower:
        device_type = "tablet"
    else:
        device_type = "desktop"

    # Detect browser
    if "chrome" in ua_lower and "edg" not in ua_lower:
        browser = "Chrome"
    elif "firefox" in ua_lower:
        browser = "Firefox"
    elif "safari" in ua_lower and "chrome" not in ua_lower:
        browser = "Safari"
    elif "edg" in ua_lower:
        browser = "Edge"
    else:
        browser = "Other"

    # Detect OS
    if "windows" in ua_lower:
        os_name = "Windows"
    elif "mac" in ua_lower:
        os_name = "macOS"
    elif "linux" in ua_lower:
        os_name = "Linux"
    elif "android" in ua_lower:
        os_name = "Android"
    elif "iphone" in ua_lower or "ipad" in ua_lower:
        os_name = "iOS"
    else:
        os_name = "Other"

    return {
        "device_type": device_type,
        "browser": browser,
        "os": os_name,
    }


# =============================================================================
# ROUTES
# =============================================================================

@router.post("/track", response_model=VisitorTrackResponse)
async def track_visitor(
    request: Request,
    data: VisitorTrackRequest,
    db=Depends(get_db)
):
    """
    Track a website visitor.

    - Captures IP address, user agent, referrer, UTM parameters
    - Creates or updates visitor record
    - Auto-creates lead for new visitors (anonymous until identified)
    - Tracks page views and visit frequency
    """
    try:
        # Extract visitor info
        ip_address = get_client_ip(request)
        user_agent = request.headers.get("user-agent", "")
        visitor_hash = generate_visitor_hash(ip_address, user_agent)
        device_info = parse_user_agent(user_agent)

        # Use client-provided visitor_id or generate from hash
        visitor_id = data.visitor_id or visitor_hash

        now = datetime.now(timezone.utc)

        # Check if visitor exists
        existing = db.execute(text("""
            SELECT id, visit_count, first_visit_at, last_visit_at, lead_id
            FROM website_visitors
            WHERE visitor_id = :visitor_id OR (ip_address = :ip AND visitor_hash = :hash)
            LIMIT 1
        """), {
            "visitor_id": visitor_id,
            "ip": ip_address,
            "hash": visitor_hash,
        }).fetchone()

        is_new_visitor = existing is None

        if is_new_visitor:
            # Create new visitor record
            db.execute(text("""
                INSERT INTO website_visitors (
                    visitor_id, visitor_hash, ip_address, user_agent,
                    device_type, browser, os,
                    first_visit_at, last_visit_at, visit_count,
                    first_page_url, first_referrer,
                    utm_source, utm_medium, utm_campaign, utm_term, utm_content,
                    screen_width, screen_height, timezone, language,
                    created_at
                ) VALUES (
                    :visitor_id, :hash, :ip, :user_agent,
                    :device_type, :browser, :os,
                    :now, :now, 1,
                    :page_url, :referrer,
                    :utm_source, :utm_medium, :utm_campaign, :utm_term, :utm_content,
                    :screen_width, :screen_height, :timezone, :language,
                    :now
                )
            """), {
                "visitor_id": visitor_id,
                "hash": visitor_hash,
                "ip": ip_address,
                "user_agent": user_agent,
                "device_type": device_info["device_type"],
                "browser": device_info["browser"],
                "os": device_info["os"],
                "now": now,
                "page_url": data.page_url,
                "referrer": data.referrer,
                "utm_source": data.utm_source,
                "utm_medium": data.utm_medium,
                "utm_campaign": data.utm_campaign,
                "utm_term": data.utm_term,
                "utm_content": data.utm_content,
                "screen_width": data.screen_width,
                "screen_height": data.screen_height,
                "timezone": data.timezone,
                "language": data.language,
            })

            # Auto-create anonymous lead
            db.execute(text("""
                INSERT INTO website_visitor_leads (
                    visitor_id, ip_address, source, status,
                    first_seen_at, last_seen_at, page_views,
                    utm_source, utm_medium, utm_campaign,
                    device_type, browser, os,
                    created_at
                ) VALUES (
                    :visitor_id, :ip, :source, 'anonymous',
                    :now, :now, 1,
                    :utm_source, :utm_medium, :utm_campaign,
                    :device_type, :browser, :os,
                    :now
                )
            """), {
                "visitor_id": visitor_id,
                "ip": ip_address,
                "source": data.utm_source or data.referrer or "direct",
                "now": now,
                "utm_source": data.utm_source,
                "utm_medium": data.utm_medium,
                "utm_campaign": data.utm_campaign,
                "device_type": device_info["device_type"],
                "browser": device_info["browser"],
                "os": device_info["os"],
            })

            visit_count = 1

        else:
            # Update existing visitor
            visit_count = (existing.visit_count or 0) + 1

            db.execute(text("""
                UPDATE website_visitors
                SET last_visit_at = :now,
                    visit_count = :visit_count,
                    ip_address = :ip,
                    user_agent = :user_agent
                WHERE visitor_id = :visitor_id OR id = :id
            """), {
                "now": now,
                "visit_count": visit_count,
                "ip": ip_address,
                "user_agent": user_agent,
                "visitor_id": visitor_id,
                "id": existing.id,
            })

            # Update lead record
            db.execute(text("""
                UPDATE website_visitor_leads
                SET last_seen_at = :now,
                    page_views = page_views + 1
                WHERE visitor_id = :visitor_id
            """), {
                "now": now,
                "visitor_id": visitor_id,
            })

        # Log page view
        db.execute(text("""
            INSERT INTO website_page_views (
                visitor_id, page_url, page_title, referrer,
                ip_address, user_agent, viewed_at
            ) VALUES (
                :visitor_id, :page_url, :page_title, :referrer,
                :ip, :user_agent, :now
            )
        """), {
            "visitor_id": visitor_id,
            "page_url": data.page_url,
            "page_title": data.page_title,
            "referrer": data.referrer,
            "ip": ip_address,
            "user_agent": user_agent,
            "now": now,
        })

        db.commit()

        return VisitorTrackResponse(
            success=True,
            visitor_id=visitor_id,
            visit_count=visit_count,
            is_new_visitor=is_new_visitor,
            message="Visitor tracked successfully",
        )

    except Exception as e:
        logger.error(f"Error tracking visitor: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/stats")
async def get_visitor_stats(
    days: int = 30,
    db=Depends(get_db)
):
    """Get visitor statistics for the admin dashboard."""
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        # Total visitors
        total = db.execute(text("""
            SELECT
                COUNT(DISTINCT visitor_id) as unique_visitors,
                COUNT(*) as total_page_views,
                COUNT(DISTINCT ip_address) as unique_ips
            FROM website_page_views
            WHERE viewed_at >= :cutoff
        """), {"cutoff": cutoff}).fetchone()

        # New vs returning
        visitor_types = db.execute(text("""
            SELECT
                COUNT(CASE WHEN visit_count = 1 THEN 1 END) as new_visitors,
                COUNT(CASE WHEN visit_count > 1 THEN 1 END) as returning_visitors
            FROM website_visitors
            WHERE last_visit_at >= :cutoff
        """), {"cutoff": cutoff}).fetchone()

        # Top pages
        top_pages = db.execute(text("""
            SELECT page_url, COUNT(*) as views
            FROM website_page_views
            WHERE viewed_at >= :cutoff
            GROUP BY page_url
            ORDER BY views DESC
            LIMIT 10
        """), {"cutoff": cutoff}).fetchall()

        # Top referrers
        top_referrers = db.execute(text("""
            SELECT
                COALESCE(first_referrer, 'Direct') as referrer,
                COUNT(*) as count
            FROM website_visitors
            WHERE first_visit_at >= :cutoff
            GROUP BY first_referrer
            ORDER BY count DESC
            LIMIT 10
        """), {"cutoff": cutoff}).fetchall()

        # Device breakdown
        devices = db.execute(text("""
            SELECT device_type, COUNT(*) as count
            FROM website_visitors
            WHERE last_visit_at >= :cutoff
            GROUP BY device_type
        """), {"cutoff": cutoff}).fetchall()

        # Daily trend
        daily_trend = db.execute(text("""
            SELECT
                DATE(viewed_at) as date,
                COUNT(DISTINCT visitor_id) as visitors,
                COUNT(*) as page_views
            FROM website_page_views
            WHERE viewed_at >= :cutoff
            GROUP BY DATE(viewed_at)
            ORDER BY date DESC
            LIMIT 30
        """), {"cutoff": cutoff}).fetchall()

        return {
            "period_days": days,
            "summary": {
                "unique_visitors": total.unique_visitors or 0,
                "total_page_views": total.total_page_views or 0,
                "unique_ips": total.unique_ips or 0,
                "new_visitors": visitor_types.new_visitors or 0,
                "returning_visitors": visitor_types.returning_visitors or 0,
            },
            "top_pages": [{"url": p.page_url, "views": p.views} for p in top_pages],
            "top_referrers": [{"referrer": r.referrer, "count": r.count} for r in top_referrers],
            "devices": {d.device_type: d.count for d in devices},
            "daily_trend": [
                {"date": str(d.date), "visitors": d.visitors, "page_views": d.page_views}
                for d in daily_trend
            ],
        }

    except Exception as e:
        logger.error(f"Error getting visitor stats: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/leads")
async def get_visitor_leads(
    status: Optional[str] = None,
    days: int = 30,
    limit: int = 50,
    db=Depends(get_db)
):
    """Get website visitor leads for the admin CRM."""
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        params = {"cutoff": cutoff, "limit": limit}
        status_filter = ""
        if status:
            status_filter = "AND status = :status"
            params["status"] = status

        leads_sql = """
            SELECT
                id, visitor_id, ip_address, source, status,
                first_seen_at, last_seen_at, page_views,
                utm_source, utm_medium, utm_campaign,
                device_type, browser, os,
                email, name, phone, company,
                notes, converted_lead_id
            FROM website_visitor_leads
            WHERE first_seen_at >= :cutoff """ + status_filter + """
            ORDER BY last_seen_at DESC
            LIMIT :limit
        """
        leads = db.execute(text(leads_sql), params).fetchall()

        return {
            "count": len(leads),
            "leads": [
                {
                    "id": lead.id,
                    "visitor_id": lead.visitor_id,
                    "ip_address": lead.ip_address,
                    "source": lead.source,
                    "status": lead.status,
                    "first_seen": lead.first_seen_at.isoformat() if lead.first_seen_at else None,
                    "last_seen": lead.last_seen_at.isoformat() if lead.last_seen_at else None,
                    "page_views": lead.page_views,
                    "utm": {
                        "source": lead.utm_source,
                        "medium": lead.utm_medium,
                        "campaign": lead.utm_campaign,
                    },
                    "device": {
                        "type": lead.device_type,
                        "browser": lead.browser,
                        "os": lead.os,
                    },
                    "contact": {
                        "email": lead.email,
                        "name": lead.name,
                        "phone": lead.phone,
                        "company": lead.company,
                    },
                    "notes": lead.notes,
                    "converted_lead_id": lead.converted_lead_id,
                }
                for lead in leads
            ],
        }

    except Exception as e:
        logger.error(f"Error getting visitor leads: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/leads/{visitor_id}/convert")
async def convert_visitor_to_lead(
    visitor_id: str,
    email: str,
    name: Optional[str] = None,
    phone: Optional[str] = None,
    company: Optional[str] = None,
    db=Depends(get_db)
):
    """Convert an anonymous visitor to a known lead."""
    try:
        now = datetime.now(timezone.utc)

        # Update visitor lead with contact info
        db.execute(text("""
            UPDATE website_visitor_leads
            SET email = :email,
                name = :name,
                phone = :phone,
                company = :company,
                status = 'identified',
                updated_at = :now
            WHERE visitor_id = :visitor_id
        """), {
            "email": email,
            "name": name,
            "phone": phone,
            "company": company,
            "now": now,
            "visitor_id": visitor_id,
        })

        db.commit()

        return {
            "success": True,
            "message": f"Visitor {visitor_id} converted to identified lead",
            "email": email,
        }

    except Exception as e:
        logger.error(f"Error converting visitor: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/admin/run-migration")
async def run_visitor_tracking_migration(
    secret_key: str,
    db=Depends(get_db)
):
    """
    Run the visitor tracking database migration.
    Requires SECRET_KEY for authorization.
    """
    expected_key = os.getenv("SECRET_KEY", "").replace("\n", "").replace(" ", "").strip()
    if not expected_key or secret_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid secret key")

    MIGRATION_SQL = """
    CREATE TABLE IF NOT EXISTS website_visitors (
        id SERIAL PRIMARY KEY,
        visitor_id VARCHAR(64) NOT NULL UNIQUE,
        visitor_hash VARCHAR(64),
        ip_address VARCHAR(45),
        user_agent TEXT,
        device_type VARCHAR(20),
        browser VARCHAR(50),
        os VARCHAR(50),
        first_visit_at TIMESTAMP WITH TIME ZONE,
        last_visit_at TIMESTAMP WITH TIME ZONE,
        visit_count INTEGER DEFAULT 1,
        first_page_url TEXT,
        first_referrer TEXT,
        utm_source VARCHAR(255),
        utm_medium VARCHAR(255),
        utm_campaign VARCHAR(255),
        utm_term VARCHAR(255),
        utm_content VARCHAR(255),
        screen_width INTEGER,
        screen_height INTEGER,
        timezone VARCHAR(100),
        language VARCHAR(20),
        lead_id UUID,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_website_visitors_visitor_id ON website_visitors(visitor_id);
    CREATE INDEX IF NOT EXISTS idx_website_visitors_ip ON website_visitors(ip_address);
    CREATE INDEX IF NOT EXISTS idx_website_visitors_last_visit ON website_visitors(last_visit_at);
    CREATE TABLE IF NOT EXISTS website_page_views (
        id SERIAL PRIMARY KEY,
        visitor_id VARCHAR(64) NOT NULL,
        page_url TEXT NOT NULL,
        page_title VARCHAR(500),
        referrer TEXT,
        ip_address VARCHAR(45),
        user_agent TEXT,
        viewed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_page_views_visitor ON website_page_views(visitor_id);
    CREATE INDEX IF NOT EXISTS idx_page_views_viewed_at ON website_page_views(viewed_at);
    CREATE TABLE IF NOT EXISTS website_visitor_leads (
        id SERIAL PRIMARY KEY,
        visitor_id VARCHAR(64) NOT NULL UNIQUE,
        ip_address VARCHAR(45),
        source VARCHAR(255),
        status VARCHAR(50) DEFAULT 'anonymous',
        first_seen_at TIMESTAMP WITH TIME ZONE,
        last_seen_at TIMESTAMP WITH TIME ZONE,
        page_views INTEGER DEFAULT 0,
        utm_source VARCHAR(255),
        utm_medium VARCHAR(255),
        utm_campaign VARCHAR(255),
        device_type VARCHAR(20),
        browser VARCHAR(50),
        os VARCHAR(50),
        email VARCHAR(255),
        name VARCHAR(255),
        phone VARCHAR(50),
        company VARCHAR(255),
        notes TEXT,
        converted_lead_id UUID,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_visitor_leads_visitor_id ON website_visitor_leads(visitor_id);
    CREATE INDEX IF NOT EXISTS idx_visitor_leads_status ON website_visitor_leads(status);
    CREATE INDEX IF NOT EXISTS idx_visitor_leads_last_seen ON website_visitor_leads(last_seen_at);
    """

    try:
        for statement in MIGRATION_SQL.split(';'):
            statement = statement.strip()
            if statement:
                db.execute(text(statement))
        db.commit()

        # Verify tables exist
        result = db.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name LIKE 'website_%'
        """))
        tables = [row[0] for row in result.fetchall()]

        return {
            "success": True,
            "message": "Migration completed successfully",
            "tables_created": tables,
        }

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")
