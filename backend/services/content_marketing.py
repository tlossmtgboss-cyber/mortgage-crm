"""
Content Marketing Services

Services for content marketing automation:
- Brand voice analysis and management
- Content calendars and briefs
- SEO keyword tracking
- Content personalization
- Publishing and collaboration
"""

import logging
import uuid
import socket
import ipaddress
from urllib.parse import urlparse
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import text
import json

logger = logging.getLogger(__name__)


_BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def _validate_url_for_ssrf(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("URL scheme must be http or https")
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL must have a valid hostname")
    if hostname.lower() in ("localhost", "0.0.0.0"):
        raise ValueError("Blocked hostname")
    try:
        addrinfos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        raise ValueError("Could not resolve hostname")
    for family, _type, _proto, _canonname, sockaddr in addrinfos:
        ip = ipaddress.ip_address(sockaddr[0])
        for network in _BLOCKED_NETWORKS:
            if ip in network:
                raise ValueError("Blocked IP address")
    return url


class BrandVoiceAnalyzerService:
    """Service for brand voice analysis and management."""

    def __init__(self, db: Session):
        self.db = db

    async def create_voice_profile(
        self,
        name: str,
        user_id: int,
        organization_id: int,
        source_url: Optional[str] = None,
        source_content: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Create a new brand voice profile."""
        profile_id = f"bv_{uuid.uuid4().hex[:12]}"

        try:
            self.db.execute(text("""
                INSERT INTO content_brand_voices (
                    id, user_id, organization_id, name, source_url, source_content,
                    tone_formal_casual, tone_authoritative_friendly,
                    tone_technical_simple, tone_serious_playful,
                    vocabulary_level, industry_context, is_active, created_at
                ) VALUES (
                    :id, :user_id, :org_id, :name, :source_url, :source_content,
                    0.5, 0.5, 0.5, 0.5, 'intermediate', 'mortgage lending', true, NOW()
                )
            """), {
                "id": profile_id,
                "user_id": user_id,
                "org_id": organization_id,
                "name": name,
                "source_url": source_url,
                "source_content": source_content
            })
            self.db.commit()

            return {
                "success": True,
                "profile_id": profile_id,
                "name": name
            }
        except Exception as e:
            logger.error(f"Failed to create brand voice: {e}")
            self.db.rollback()
            raise

    def list_voice_profiles(
        self,
        organization_id: int,
        active_only: bool = True
    ) -> List[Any]:
        """List brand voice profiles."""
        query = """
            SELECT * FROM content_brand_voices
            WHERE organization_id = :org_id
        """
        if active_only:
            query += " AND is_active = true"
        query += " ORDER BY created_at DESC"

        result = self.db.execute(text(query), {"org_id": organization_id})
        return result.fetchall()

    def get_voice_profile(self, profile_id: str) -> Optional[Any]:
        """Get a specific brand voice profile."""
        result = self.db.execute(text("""
            SELECT * FROM content_brand_voices WHERE id = :id
        """), {"id": profile_id})
        return result.fetchone()

    def update_voice_profile(self, profile_id: str, updates: Dict) -> Optional[Any]:
        """Update a brand voice profile."""
        set_clauses = []
        params = {"id": profile_id}

        for key, value in updates.items():
            if key not in ["id", "created_at"]:
                set_clauses.append(f"{key} = :{key}")
                params[key] = value

        if not set_clauses:
            return self.get_voice_profile(profile_id)

        set_clauses.append("updated_at = NOW()")

        self.db.execute(text(f"""
            UPDATE content_brand_voices
            SET {', '.join(set_clauses)}
            WHERE id = :id
        """), params)
        self.db.commit()

        return self.get_voice_profile(profile_id)

    def delete_voice_profile(self, profile_id: str) -> bool:
        """Deactivate a brand voice profile."""
        result = self.db.execute(text("""
            UPDATE content_brand_voices
            SET is_active = false, updated_at = NOW()
            WHERE id = :id
            RETURNING id
        """), {"id": profile_id})
        self.db.commit()
        return result.fetchone() is not None

    def export_voice_profile(self, profile_id: str) -> Dict[str, Any]:
        """Export a voice profile as a dictionary."""
        profile = self.get_voice_profile(profile_id)
        if not profile:
            return {}

        return {
            "id": profile.id,
            "name": profile.name,
            "source_url": profile.source_url,
            "tone": {
                "formal_casual": profile.tone_formal_casual,
                "authoritative_friendly": profile.tone_authoritative_friendly,
                "technical_simple": profile.tone_technical_simple,
                "serious_playful": profile.tone_serious_playful
            },
            "vocabulary_level": profile.vocabulary_level,
            "industry_context": profile.industry_context,
            "is_active": profile.is_active,
            "created_at": str(profile.created_at) if profile.created_at else None
        }

    async def fetch_website_content(self, url: str) -> Dict[str, Any]:
        """Fetch content from a website for analysis."""
        try:
            _validate_url_for_ssrf(url)
        except ValueError:
            return {"success": False, "error": "Invalid or blocked URL"}
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=30, follow_redirects=True)
                return {
                    "success": True,
                    "content": response.text[:50000],  # Limit content
                    "url": str(response.url)
                }
        except Exception as e:
            return {"success": False, "error": "Internal server error"}

    async def analyze_voice(self, content: str, url: Optional[str] = None) -> Dict[str, Any]:
        """Analyze content to extract brand voice characteristics."""
        # Basic analysis - in production this would use AI
        word_count = len(content.split())

        return {
            "tone": {
                "formal_casual": 0.5,
                "authoritative_friendly": 0.6,
                "technical_simple": 0.4,
                "serious_playful": 0.3
            },
            "vocabulary_level": "intermediate",
            "key_phrases": [],
            "brand_values": ["trust", "expertise", "service"],
            "analysis_confidence": 0.7,
            "word_count_analyzed": word_count
        }


class ContentCalendarService:
    """Service for content calendar management."""

    def __init__(self, db: Session):
        self.db = db

    def create_calendar(
        self,
        name: str,
        start_date: date,
        end_date: date,
        user_id: int,
        organization_id: int,
        **kwargs
    ) -> Dict[str, Any]:
        """Create a new content calendar."""
        calendar_id = f"cal_{uuid.uuid4().hex[:12]}"

        self.db.execute(text("""
            INSERT INTO content_calendars (
                id, user_id, organization_id, name, start_date, end_date,
                status, created_at
            ) VALUES (
                :id, :user_id, :org_id, :name, :start_date, :end_date,
                'draft', NOW()
            )
        """), {
            "id": calendar_id,
            "user_id": user_id,
            "org_id": organization_id,
            "name": name,
            "start_date": start_date,
            "end_date": end_date
        })
        self.db.commit()

        return {"success": True, "calendar_id": calendar_id}

    def list_calendars(
        self,
        organization_id: int,
        status: Optional[str] = None,
        include_past: bool = False
    ) -> List[Any]:
        """List content calendars."""
        query = "SELECT * FROM content_calendars WHERE organization_id = :org_id"
        params = {"org_id": organization_id}

        if status:
            query += " AND status = :status"
            params["status"] = status
        if not include_past:
            query += " AND end_date >= CURRENT_DATE"

        query += " ORDER BY start_date DESC"

        result = self.db.execute(text(query), params)
        return result.fetchall()

    def get_calendar(self, calendar_id: str) -> Optional[Any]:
        """Get a specific calendar."""
        result = self.db.execute(text("""
            SELECT * FROM content_calendars WHERE id = :id
        """), {"id": calendar_id})
        return result.fetchone()

    def get_calendar_stats(self, calendar_id: str) -> Dict[str, Any]:
        """Get calendar statistics."""
        result = self.db.execute(text("""
            SELECT
                COUNT(*) as total_briefs,
                COUNT(CASE WHEN status = 'published' THEN 1 END) as published,
                COUNT(CASE WHEN status = 'draft' THEN 1 END) as drafts,
                COUNT(CASE WHEN status = 'planned' THEN 1 END) as planned
            FROM content_briefs
            WHERE calendar_id = :calendar_id
        """), {"calendar_id": calendar_id})
        row = result.fetchone()

        return {
            "total_briefs": row.total_briefs if row else 0,
            "published": row.published if row else 0,
            "drafts": row.drafts if row else 0,
            "planned": row.planned if row else 0
        }

    def get_weekly_view(self, calendar_id: str, week_start: date) -> Dict[str, Any]:
        """Get weekly view of calendar."""
        week_end = week_start + timedelta(days=6)

        result = self.db.execute(text("""
            SELECT * FROM content_briefs
            WHERE calendar_id = :calendar_id
            AND scheduled_date BETWEEN :start AND :end
            ORDER BY scheduled_date, scheduled_time
        """), {
            "calendar_id": calendar_id,
            "start": week_start,
            "end": week_end
        })

        briefs = result.fetchall()
        return {
            "week_start": str(week_start),
            "week_end": str(week_end),
            "briefs": [{"id": b.id, "title": b.title, "date": str(b.scheduled_date)} for b in briefs]
        }

    def get_monthly_view(self, calendar_id: str, year: int, month: int) -> Dict[str, Any]:
        """Get monthly view of calendar."""
        start_date = date(year, month, 1)
        if month == 12:
            end_date = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = date(year, month + 1, 1) - timedelta(days=1)

        result = self.db.execute(text("""
            SELECT * FROM content_briefs
            WHERE calendar_id = :calendar_id
            AND scheduled_date BETWEEN :start AND :end
            ORDER BY scheduled_date
        """), {
            "calendar_id": calendar_id,
            "start": start_date,
            "end": end_date
        })

        briefs = result.fetchall()
        return {
            "year": year,
            "month": month,
            "briefs": [{"id": b.id, "title": b.title, "date": str(b.scheduled_date)} for b in briefs]
        }

    def update_calendar(self, calendar_id: str, updates: Dict) -> Optional[Any]:
        """Update a calendar."""
        set_clauses = []
        params = {"id": calendar_id}

        for key, value in updates.items():
            if key not in ["id", "created_at"]:
                set_clauses.append(f"{key} = :{key}")
                params[key] = value

        if set_clauses:
            set_clauses.append("updated_at = NOW()")
            self.db.execute(text(f"""
                UPDATE content_calendars
                SET {', '.join(set_clauses)}
                WHERE id = :id
            """), params)
            self.db.commit()

        return self.get_calendar(calendar_id)

    def activate_calendar(self, calendar_id: str) -> bool:
        """Activate a calendar."""
        result = self.db.execute(text("""
            UPDATE content_calendars
            SET status = 'active', updated_at = NOW()
            WHERE id = :id
            RETURNING id
        """), {"id": calendar_id})
        self.db.commit()
        return result.fetchone() is not None

    def pause_calendar(self, calendar_id: str) -> bool:
        """Pause a calendar."""
        result = self.db.execute(text("""
            UPDATE content_calendars
            SET status = 'paused', updated_at = NOW()
            WHERE id = :id
            RETURNING id
        """), {"id": calendar_id})
        self.db.commit()
        return result.fetchone() is not None

    def generate_calendar_briefs(self, calendar_id: str, regenerate: bool = False) -> int:
        """Generate briefs for a calendar."""
        # Placeholder - would generate AI content briefs
        return 0

    def delete_calendar(self, calendar_id: str, delete_briefs: bool = False) -> bool:
        """Delete a calendar."""
        if delete_briefs:
            self.db.execute(text("""
                DELETE FROM content_briefs WHERE calendar_id = :id
            """), {"id": calendar_id})

        result = self.db.execute(text("""
            DELETE FROM content_calendars WHERE id = :id RETURNING id
        """), {"id": calendar_id})
        self.db.commit()
        return result.fetchone() is not None

    def create_brief(
        self,
        topic: str,
        scheduled_date: date,
        user_id: int,
        organization_id: int,
        calendar_id: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Create a content brief."""
        brief_id = f"brief_{uuid.uuid4().hex[:12]}"

        self.db.execute(text("""
            INSERT INTO content_briefs (
                id, calendar_id, user_id, organization_id, topic,
                scheduled_date, status, created_at
            ) VALUES (
                :id, :calendar_id, :user_id, :org_id, :topic,
                :scheduled_date, 'planned', NOW()
            )
        """), {
            "id": brief_id,
            "calendar_id": calendar_id,
            "user_id": user_id,
            "org_id": organization_id,
            "topic": topic,
            "scheduled_date": scheduled_date
        })
        self.db.commit()

        return {"success": True, "brief_id": brief_id}

    def list_briefs(
        self,
        organization_id: int,
        calendar_id: Optional[str] = None,
        status: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Any]:
        """List content briefs."""
        query = "SELECT * FROM content_briefs WHERE organization_id = :org_id"
        params = {"org_id": organization_id, "limit": limit, "offset": offset}

        if calendar_id:
            query += " AND calendar_id = :calendar_id"
            params["calendar_id"] = calendar_id
        if status:
            query += " AND status = :status"
            params["status"] = status
        if start_date:
            query += " AND scheduled_date >= :start_date"
            params["start_date"] = start_date
        if end_date:
            query += " AND scheduled_date <= :end_date"
            params["end_date"] = end_date

        query += " ORDER BY scheduled_date DESC LIMIT :limit OFFSET :offset"

        result = self.db.execute(text(query), params)
        return result.fetchall()

    def get_upcoming_briefs(
        self,
        organization_id: int,
        days_ahead: int = 7,
        status: Optional[str] = None
    ) -> List[Any]:
        """Get upcoming briefs."""
        query = """
            SELECT * FROM content_briefs
            WHERE organization_id = :org_id
            AND scheduled_date BETWEEN CURRENT_DATE AND CURRENT_DATE + :days
        """
        params = {"org_id": organization_id, "days": days_ahead}

        if status:
            query += " AND status = :status"
            params["status"] = status

        query += " ORDER BY scheduled_date"

        result = self.db.execute(text(query), params)
        return result.fetchall()

    def get_brief(self, brief_id: str) -> Optional[Any]:
        """Get a specific brief."""
        result = self.db.execute(text("""
            SELECT * FROM content_briefs WHERE id = :id
        """), {"id": brief_id})
        return result.fetchone()

    def update_brief(self, brief_id: str, updates: Dict) -> Optional[Any]:
        """Update a brief."""
        set_clauses = []
        params = {"id": brief_id}

        for key, value in updates.items():
            if key not in ["id", "created_at"]:
                set_clauses.append(f"{key} = :{key}")
                params[key] = value

        if set_clauses:
            set_clauses.append("updated_at = NOW()")
            self.db.execute(text(f"""
                UPDATE content_briefs
                SET {', '.join(set_clauses)}
                WHERE id = :id
            """), params)
            self.db.commit()

        return self.get_brief(brief_id)

    def delete_brief(self, brief_id: str) -> bool:
        """Delete a brief."""
        result = self.db.execute(text("""
            DELETE FROM content_briefs WHERE id = :id RETURNING id
        """), {"id": brief_id})
        self.db.commit()
        return result.fetchone() is not None


class SEOKeywordService:
    """Service for SEO keyword tracking."""

    def __init__(self, db: Session):
        self.db = db

    def add_keyword(
        self,
        keyword: str,
        user_id: int,
        organization_id: int,
        category: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Add a keyword to track."""
        keyword_id = f"kw_{uuid.uuid4().hex[:12]}"

        self.db.execute(text("""
            INSERT INTO seo_keywords (
                id, user_id, organization_id, keyword, category,
                status, created_at
            ) VALUES (
                :id, :user_id, :org_id, :keyword, :category,
                'tracking', NOW()
            )
        """), {
            "id": keyword_id,
            "user_id": user_id,
            "org_id": organization_id,
            "keyword": keyword,
            "category": category
        })
        self.db.commit()

        return {"success": True, "keyword_id": keyword_id}

    def list_keywords(
        self,
        organization_id: int,
        category: Optional[str] = None,
        status: Optional[str] = None,
        min_volume: Optional[int] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Any]:
        """List tracked keywords."""
        query = "SELECT * FROM seo_keywords WHERE organization_id = :org_id"
        params = {"org_id": organization_id, "limit": limit, "offset": offset}

        if category:
            query += " AND category = :category"
            params["category"] = category
        if status:
            query += " AND status = :status"
            params["status"] = status
        if min_volume:
            query += " AND search_volume >= :min_volume"
            params["min_volume"] = min_volume

        query += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"

        result = self.db.execute(text(query), params)
        return result.fetchall()

    def get_keyword(self, keyword_id: str) -> Optional[Any]:
        """Get a specific keyword."""
        result = self.db.execute(text("""
            SELECT * FROM seo_keywords WHERE id = :id
        """), {"id": keyword_id})
        return result.fetchone()

    def get_keyword_analytics(self, organization_id: int) -> Dict[str, Any]:
        """Get keyword analytics."""
        result = self.db.execute(text("""
            SELECT
                COUNT(*) as total_keywords,
                COUNT(CASE WHEN current_ranking <= 10 THEN 1 END) as top_10,
                COUNT(CASE WHEN current_ranking <= 3 THEN 1 END) as top_3,
                AVG(current_ranking) as avg_ranking
            FROM seo_keywords
            WHERE organization_id = :org_id AND status = 'tracking'
        """), {"org_id": organization_id})
        row = result.fetchone()

        return {
            "total_keywords": row.total_keywords if row else 0,
            "top_10": row.top_10 if row else 0,
            "top_3": row.top_3 if row else 0,
            "avg_ranking": float(row.avg_ranking) if row and row.avg_ranking else None
        }

    def get_keyword_opportunities(self, organization_id: int) -> Dict[str, Any]:
        """Get keyword opportunities."""
        return {"opportunities": []}

    def get_ranking_changes(self, organization_id: int, days: int = 7) -> Dict[str, Any]:
        """Get ranking changes."""
        return {"changes": [], "period_days": days}

    async def suggest_keywords(
        self,
        seed_keyword: str,
        category: Optional[str] = None,
        count: int = 10
    ) -> List[Dict[str, Any]]:
        """Suggest related keywords."""
        # Placeholder - would use AI or keyword API
        return []

    def update_keyword(self, keyword_id: str, updates: Dict) -> Optional[Any]:
        """Update a keyword."""
        set_clauses = []
        params = {"id": keyword_id}

        for key, value in updates.items():
            if key not in ["id", "created_at"]:
                set_clauses.append(f"{key} = :{key}")
                params[key] = value

        if set_clauses:
            set_clauses.append("updated_at = NOW()")
            self.db.execute(text(f"""
                UPDATE seo_keywords
                SET {', '.join(set_clauses)}
                WHERE id = :id
            """), params)
            self.db.commit()

        return self.get_keyword(keyword_id)

    def update_ranking(
        self,
        keyword_id: str,
        ranking: int,
        url: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update keyword ranking."""
        self.db.execute(text("""
            UPDATE seo_keywords
            SET current_ranking = :ranking, ranking_url = :url, updated_at = NOW()
            WHERE id = :id
        """), {"id": keyword_id, "ranking": ranking, "url": url})
        self.db.commit()
        return {"success": True}

    def bulk_update_rankings(self, rankings: List[Dict]) -> Dict[str, Any]:
        """Bulk update rankings."""
        updated = 0
        for item in rankings:
            self.update_ranking(item["keyword_id"], item["ranking"], item.get("url"))
            updated += 1
        return {"success": True, "updated": updated}

    def delete_keyword(self, keyword_id: str) -> bool:
        """Archive a keyword."""
        result = self.db.execute(text("""
            UPDATE seo_keywords
            SET status = 'archived', updated_at = NOW()
            WHERE id = :id
            RETURNING id
        """), {"id": keyword_id})
        self.db.commit()
        return result.fetchone() is not None

    def seed_mortgage_keywords(self, user_id: int, organization_id: int) -> Dict[str, Any]:
        """Seed mortgage industry keywords."""
        keywords = [
            "mortgage rates", "home loan", "refinance",
            "first time home buyer", "FHA loan", "VA loan",
            "mortgage calculator", "down payment assistance"
        ]

        added = 0
        for kw in keywords:
            try:
                self.add_keyword(kw, user_id, organization_id, "mortgage")
                added += 1
            except Exception:
                pass

        return {"success": True, "keywords_added": added}


class ContentPersonalizationService:
    """Service for content personalization."""

    def __init__(self, db: Session):
        self.db = db

    def get_tokens(self, organization_id: int) -> List[Any]:
        """Get personalization tokens."""
        result = self.db.execute(text("""
            SELECT * FROM personalization_tokens
            ORDER BY category, token_name
        """))
        return result.fetchall()

    def resolve_tokens(self, content: str, context: Dict) -> str:
        """Resolve tokens in content."""
        # Basic token replacement
        for key, value in context.items():
            content = content.replace(f"{{{{{key}}}}}", str(value))
        return content


class ContentCollaborationService:
    """Service for content collaboration."""

    def __init__(self, db: Session):
        self.db = db

    def add_comment(
        self,
        brief_id: str,
        user_id: int,
        content: str,
        **kwargs
    ) -> Dict[str, Any]:
        """Add a comment to a brief."""
        comment_id = f"cmt_{uuid.uuid4().hex[:12]}"

        self.db.execute(text("""
            INSERT INTO content_comments (
                id, brief_id, user_id, content, created_at
            ) VALUES (
                :id, :brief_id, :user_id, :content, NOW()
            )
        """), {
            "id": comment_id,
            "brief_id": brief_id,
            "user_id": user_id,
            "content": content
        })
        self.db.commit()

        return {"success": True, "comment_id": comment_id}

    def get_comments(self, brief_id: str) -> List[Any]:
        """Get comments for a brief."""
        result = self.db.execute(text("""
            SELECT c.*, u.name as user_name
            FROM content_comments c
            LEFT JOIN users u ON u.id = c.user_id
            WHERE c.brief_id = :brief_id
            ORDER BY c.created_at
        """), {"brief_id": brief_id})
        return result.fetchall()


class ContentPublisherService:
    """Service for content publishing."""

    def __init__(self, db: Session):
        self.db = db

    async def publish_content(
        self,
        brief_id: str,
        channels: List[str],
        **kwargs
    ) -> Dict[str, Any]:
        """Publish content to channels."""
        # Placeholder - would integrate with publishing APIs
        return {"success": True, "published_to": channels}

    def get_publish_history(self, brief_id: str) -> List[Any]:
        """Get publish history for a brief."""
        result = self.db.execute(text("""
            SELECT * FROM content_publish_logs
            WHERE brief_id = :brief_id
            ORDER BY published_at DESC
        """), {"brief_id": brief_id})
        return result.fetchall()
