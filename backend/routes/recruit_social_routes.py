"""
Recruit Social Media Routes
API endpoints for LinkedIn, Facebook, and Instagram integrations.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Header
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime
from urllib.parse import urlparse
from database import get_db
from services.recruit_social_service import recruit_social_service, SocialProfile
import logging
import os
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

_ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")

_ALLOWED_REDIRECT_HOSTS = {"app.perenniaai.com", "localhost", "127.0.0.1"}


def _validate_redirect_uri(uri: str) -> str:
    parsed = urlparse(uri)
    hostname = parsed.hostname or ""
    if parsed.scheme not in ("https", "http"):
        raise HTTPException(status_code=400, detail="Invalid redirect URI scheme")
    if hostname not in _ALLOWED_REDIRECT_HOSTS and not hostname.endswith(".perenniaai.com"):
        raise HTTPException(status_code=400, detail="Redirect URI not allowed")
    return uri


def _get_current_user():
    """Lazy import auth dependency for router-level protection."""
    from main import get_current_user_flexible
    return get_current_user_flexible

router = APIRouter(
    prefix="/api/v1/recruit-social", tags=["recruit-social"],
    dependencies=[Depends(_get_current_user())],
)


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class SocialPostCreate(BaseModel):
    content: str
    platforms: List[str]  # ["facebook", "linkedin", "instagram"]
    image_url: Optional[str] = None
    scheduled_time: Optional[datetime] = None


class OAuthCallbackRequest(BaseModel):
    code: str
    redirect_uri: str
    state: Optional[str] = None


class LinkedInProfileEnrich(BaseModel):
    linkedin_url: str
    candidate_id: int


class CandidateLinkedInPostsResponse(BaseModel):
    candidate_id: int
    username: str
    posts: List[dict]


# ============================================================================
# OAUTH ENDPOINTS
# ============================================================================

@router.get("/oauth/facebook/url")
async def get_facebook_oauth_url(
    redirect_uri: str = Query(..., description="OAuth callback URL")
):
    """Get Facebook OAuth authorization URL."""
    _validate_redirect_uri(redirect_uri)
    url = recruit_social_service.get_facebook_oauth_url(redirect_uri)
    return {"oauth_url": url}


@router.get("/oauth/linkedin/url")
async def get_linkedin_oauth_url(
    redirect_uri: str = Query(..., description="OAuth callback URL")
):
    """Get LinkedIn OAuth authorization URL."""
    _validate_redirect_uri(redirect_uri)
    url = recruit_social_service.get_linkedin_oauth_url(redirect_uri)
    return {"oauth_url": url}


@router.post("/oauth/facebook/callback")
async def facebook_oauth_callback(
    request: OAuthCallbackRequest,
    db: Session = Depends(get_db)
):
    """Exchange Facebook authorization code for access token."""
    try:
        token_data = await recruit_social_service.exchange_facebook_code(
            code=request.code,
            redirect_uri=request.redirect_uri
        )

        if not token_data:
            raise HTTPException(status_code=400, detail="Failed to exchange code")

        # Store token in database
        db.execute(text("""
            INSERT INTO social_tokens (platform, access_token, expires_at, created_at)
            VALUES ('facebook', :token, :expires, NOW())
            ON CONFLICT (platform) DO UPDATE SET
                access_token = :token,
                expires_at = :expires,
                updated_at = NOW()
        """), {
            "token": token_data.get("access_token"),
            "expires": datetime.now().isoformat() if not token_data.get("expires_in") else None
        })
        db.commit()

        return {
            "status": "success",
            "message": "Facebook connected successfully",
            "expires_in": token_data.get("expires_in")
        }
    except SQLAlchemyError as e:
        logger.error(f"Facebook OAuth error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/oauth/linkedin/callback")
async def linkedin_oauth_callback(
    request: OAuthCallbackRequest,
    db: Session = Depends(get_db)
):
    """Exchange LinkedIn authorization code for access token."""
    try:
        token_data = await recruit_social_service.exchange_linkedin_code(
            code=request.code,
            redirect_uri=request.redirect_uri
        )

        if not token_data:
            raise HTTPException(status_code=400, detail="Failed to exchange code")

        # Store token in database
        db.execute(text("""
            INSERT INTO social_tokens (platform, access_token, expires_at, created_at)
            VALUES ('linkedin', :token, :expires, NOW())
            ON CONFLICT (platform) DO UPDATE SET
                access_token = :token,
                expires_at = :expires,
                updated_at = NOW()
        """), {
            "token": token_data.get("access_token"),
            "expires": datetime.now().isoformat() if not token_data.get("expires_in") else None
        })
        db.commit()

        return {
            "status": "success",
            "message": "LinkedIn connected successfully",
            "expires_in": token_data.get("expires_in")
        }
    except SQLAlchemyError as e:
        logger.error(f"LinkedIn OAuth error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# POSTING ENDPOINTS
# ============================================================================

@router.post("/posts")
async def create_social_post(
    post: SocialPostCreate,
    db: Session = Depends(get_db)
):
    """Create a post across social media platforms."""
    try:
        if post.scheduled_time and post.scheduled_time > datetime.now():
            # Schedule the post
            result = await recruit_social_service.schedule_recruiting_post(
                platforms=post.platforms,
                content=post.content,
                scheduled_time=post.scheduled_time,
                image_url=post.image_url
            )
        else:
            # Post immediately
            result = {"platforms": {}}

            for platform in post.platforms:
                if platform == "facebook":
                    page_id = os.getenv("FACEBOOK_PAGE_ID", "")
                    if page_id:
                        fb_result = await recruit_social_service.post_to_facebook_page(
                            page_id=page_id,
                            message=post.content,
                            image_url=post.image_url
                        )
                        result["platforms"]["facebook"] = fb_result
                    else:
                        result["platforms"]["facebook"] = {"error": "Page not configured"}

                elif platform == "linkedin":
                    author_id = os.getenv("LINKEDIN_AUTHOR_ID", "")
                    if author_id:
                        li_result = await recruit_social_service.post_to_linkedin(
                            author_id=author_id,
                            text=post.content,
                            media_url=post.image_url
                        )
                        result["platforms"]["linkedin"] = li_result
                    else:
                        result["platforms"]["linkedin"] = {"error": "Author not configured"}

                elif platform == "instagram":
                    ig_account_id = os.getenv("INSTAGRAM_ACCOUNT_ID", "")
                    if ig_account_id and post.image_url:
                        ig_result = await recruit_social_service.post_to_instagram(
                            ig_account_id=ig_account_id,
                            image_url=post.image_url,
                            caption=post.content
                        )
                        result["platforms"]["instagram"] = ig_result
                    else:
                        result["platforms"]["instagram"] = {"error": "Account not configured or image required"}

        # Log the post to database
        db.execute(text("""
            INSERT INTO recruit_social_posts (content, platforms, image_url, scheduled_at, status, created_at)
            VALUES (:content, :platforms, :image_url, :scheduled_at, :status, NOW())
        """), {
            "content": post.content,
            "platforms": ",".join(post.platforms),
            "image_url": post.image_url,
            "scheduled_at": post.scheduled_time,
            "status": "scheduled" if post.scheduled_time else "posted"
        })
        db.commit()

        return result
    except SQLAlchemyError as e:
        logger.error(f"Error creating social post: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/posts")
async def get_social_posts(
    limit: int = Query(20, le=100),
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get recruiting social media posts."""
    try:
        query = """
            SELECT id, content, platforms, image_url, scheduled_at,
                   status, posted_at, engagement_data, created_at
            FROM recruit_social_posts
        """
        params = {"limit": limit}

        if status:
            query += " WHERE status = :status"
            params["status"] = status

        query += " ORDER BY created_at DESC LIMIT :limit"

        result = db.execute(text(query), params)
        posts = [dict(row._mapping) for row in result]

        return {"posts": posts, "count": len(posts)}
    except SQLAlchemyError as e:
        logger.error(f"Error getting social posts: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/posts/{post_id}/analytics")
async def get_post_analytics(
    post_id: int,
    db: Session = Depends(get_db)
):
    """Get engagement analytics for a social post."""
    try:
        result = db.execute(text("""
            SELECT id, platforms, engagement_data, external_post_ids
            FROM recruit_social_posts
            WHERE id = :post_id
        """), {"post_id": post_id})
        post = result.fetchone()

        if not post:
            raise HTTPException(status_code=404, detail="Post not found")

        post_dict = dict(post._mapping)
        external_ids = post_dict.get("external_post_ids") or {}

        # Fetch live analytics from platforms
        analytics = await recruit_social_service.get_recruiting_post_analytics(external_ids)

        return {
            "post_id": post_id,
            "platforms": post_dict.get("platforms", "").split(","),
            "analytics": analytics
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting post analytics: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# PROFILE ENRICHMENT
# ============================================================================

@router.post("/enrich/linkedin")
async def enrich_from_linkedin(
    request: LinkedInProfileEnrich,
    db: Session = Depends(get_db)
):
    """Enrich candidate data from LinkedIn profile."""
    try:
        enrichment = await recruit_social_service.enrich_candidate_from_linkedin(
            request.linkedin_url
        )

        if enrichment:
            # Store enrichment data
            db.execute(text("""
                UPDATE recruiting_candidates
                SET linkedin_url = :linkedin_url,
                    linkedin_data = :linkedin_data,
                    updated_at = NOW()
                WHERE id = :candidate_id
            """), {
                "candidate_id": request.candidate_id,
                "linkedin_url": request.linkedin_url,
                "linkedin_data": str(enrichment)
            })
            db.commit()

        return {
            "candidate_id": request.candidate_id,
            "enrichment": enrichment
        }
    except SQLAlchemyError as e:
        logger.error(f"Error enriching from LinkedIn: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/candidates/{candidate_id}/linkedin-posts")
async def get_candidate_linkedin_posts(
    candidate_id: int,
    db: Session = Depends(get_db)
):
    """Get recent LinkedIn posts for a candidate."""
    try:
        # Get candidate's LinkedIn info
        result = db.execute(text("""
            SELECT id, name, linkedin_url, linkedin_data
            FROM recruiting_candidates
            WHERE id = :candidate_id
        """), {"candidate_id": candidate_id})
        candidate = result.fetchone()

        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")

        candidate_dict = dict(candidate._mapping)
        linkedin_url = candidate_dict.get("linkedin_url")

        if not linkedin_url:
            return {
                "candidate_id": candidate_id,
                "posts": [],
                "message": "No LinkedIn profile linked"
            }

        # Note: Getting posts from LinkedIn requires their API or scraping
        # which has legal implications. This returns cached/stored data.
        cached_posts = db.execute(text("""
            SELECT id, post_content, post_url, likes, comments, shares,
                   posted_at, cached_at
            FROM candidate_linkedin_posts
            WHERE candidate_id = :candidate_id
            ORDER BY posted_at DESC
            LIMIT 10
        """), {"candidate_id": candidate_id})

        posts = [dict(row._mapping) for row in cached_posts]

        return {
            "candidate_id": candidate_id,
            "linkedin_url": linkedin_url,
            "posts": posts,
            "cached": True,
            "message": "Posts are cached. LinkedIn API access required for live data."
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting candidate LinkedIn posts: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# CONNECTION STATUS
# ============================================================================

@router.get("/connections")
async def get_social_connections(db: Session = Depends(get_db)):
    """Get status of social media connections."""
    try:
        result = db.execute(text("""
            SELECT platform,
                   access_token IS NOT NULL as connected,
                   expires_at,
                   updated_at
            FROM social_tokens
        """))
        tokens = [dict(row._mapping) for row in result]

        # Build connection status
        connections = {
            "facebook": {"connected": False, "expires_at": None},
            "linkedin": {"connected": False, "expires_at": None},
            "instagram": {"connected": False, "expires_at": None}
        }

        for token in tokens:
            platform = token["platform"]
            if platform in connections:
                connections[platform] = {
                    "connected": token["connected"],
                    "expires_at": token["expires_at"],
                    "updated_at": token["updated_at"]
                }

        # Check if environment variables are set
        connections["facebook"]["configured"] = bool(os.getenv("FACEBOOK_APP_ID"))
        connections["linkedin"]["configured"] = bool(os.getenv("LINKEDIN_CLIENT_ID"))
        connections["instagram"]["configured"] = bool(os.getenv("INSTAGRAM_ACCOUNT_ID"))

        return connections
    except Exception as e:
        logger.error(f"Error getting social connections: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/page-info/facebook")
async def get_facebook_page_info():
    """Get connected Facebook page information."""
    try:
        page_id = os.getenv("FACEBOOK_PAGE_ID", "")
        if not page_id:
            return {"error": "No Facebook page configured"}

        page_info = await recruit_social_service.get_facebook_page_info(page_id)
        return page_info or {"error": "Could not fetch page info"}
    except Exception as e:
        logger.error(f"Error getting Facebook page info: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/profile/linkedin")
async def get_linkedin_profile():
    """Get connected LinkedIn profile information."""
    try:
        profile = await recruit_social_service.get_linkedin_profile()
        if profile:
            return {
                "profile_id": profile.profile_id,
                "name": profile.name,
                "headline": profile.headline,
                "avatar_url": profile.avatar_url
            }
        return {"error": "Could not fetch LinkedIn profile"}
    except Exception as e:
        logger.error(f"Error getting LinkedIn profile: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# MIGRATION ENDPOINT
# ============================================================================

@router.post("/admin/run-migration")
async def run_social_migration(
    admin_key: str = Query(...),
    db: Session = Depends(get_db)
):
    """Run migration to create social media tables."""
    if admin_key != _ADMIN_API_KEY or not _ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    try:
        db.execute(text("""
            -- Social tokens storage
            CREATE TABLE IF NOT EXISTS social_tokens (
                id SERIAL PRIMARY KEY,
                platform VARCHAR(50) UNIQUE NOT NULL,
                access_token TEXT,
                refresh_token TEXT,
                expires_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );

            -- Recruiting social posts
            CREATE TABLE IF NOT EXISTS recruit_social_posts (
                id SERIAL PRIMARY KEY,
                content TEXT NOT NULL,
                platforms VARCHAR(100),
                image_url TEXT,
                scheduled_at TIMESTAMP,
                posted_at TIMESTAMP,
                status VARCHAR(20) DEFAULT 'draft',
                external_post_ids JSONB DEFAULT '{}',
                engagement_data JSONB DEFAULT '{}',
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS idx_recruit_social_posts_status
                ON recruit_social_posts(status);
            CREATE INDEX IF NOT EXISTS idx_recruit_social_posts_scheduled
                ON recruit_social_posts(scheduled_at) WHERE status = 'scheduled';

            -- Cached LinkedIn posts for candidates
            CREATE TABLE IF NOT EXISTS candidate_linkedin_posts (
                id SERIAL PRIMARY KEY,
                candidate_id INTEGER NOT NULL,
                post_content TEXT,
                post_url TEXT,
                likes INTEGER DEFAULT 0,
                comments INTEGER DEFAULT 0,
                shares INTEGER DEFAULT 0,
                posted_at TIMESTAMP,
                cached_at TIMESTAMP DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS idx_candidate_linkedin_posts_candidate
                ON candidate_linkedin_posts(candidate_id);
        """))
        db.commit()

        return {"status": "success", "message": "Social media tables created"}
    except SQLAlchemyError as e:
        logger.error(f"Migration error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# PUBLIC PORTAL ENDPOINTS (no auth required)
# ============================================================================

@router.post("/admin/seed-posts")
async def seed_sample_posts(
    x_admin_key: str = Header(..., alias="X-Admin-Key"),
    db: Session = Depends(get_db)
):
    """Seed sample social posts for demo purposes."""
    import hmac
    if not _ADMIN_API_KEY or not hmac.compare_digest(x_admin_key, _ADMIN_API_KEY):
        raise HTTPException(status_code=403, detail="Invalid admin key")

    try:
        sample_posts = [
            {
                "content": "🎉 Welcome to our newest team members! We're thrilled to have you join the Perennia family. Here's to building something amazing together! #TeamPerennia #MortgageLife #NewBeginnings",
                "platforms": "linkedin,facebook",
                "image_url": "https://images.unsplash.com/photo-1522071820081-009f0129c71c?w=800",
            },
            {
                "content": "💡 Industry insight: The mortgage market is evolving rapidly. At Perennia, we're staying ahead with cutting-edge AI tools that help our LOs close more deals. Want to learn more? Let's connect! #MortgageIndustry #AIinMortgage",
                "platforms": "linkedin",
                "image_url": None,
            },
            {
                "content": "🏆 Congratulations to our top producers this month! Your dedication and hard work inspire us all. #TopProducers #MortgageSuccess #PerenniaProud",
                "platforms": "linkedin,facebook,instagram",
                "image_url": "https://images.unsplash.com/photo-1552664730-d307ca884978?w=800",
            },
            {
                "content": "📈 Q4 is here! Are you ready to finish the year strong? Our team has the tools, leads, and support to help you hit your goals. DM us to learn about opportunities! #Recruiting #MortgageCareers",
                "platforms": "linkedin,facebook",
                "image_url": None,
            },
            {
                "content": "🎯 What sets us apart? Technology that works FOR you, not against you. See how our AI-powered CRM is helping loan officers save 10+ hours per week. #MortgageTech #Efficiency",
                "platforms": "linkedin,instagram",
                "image_url": "https://images.unsplash.com/photo-1460925895917-afdab827c52f?w=800",
            },
            {
                "content": "🤝 Culture matters. At Perennia, we believe in supporting each other's growth. Our mentorship program pairs new LOs with experienced pros. Ready to grow? #CompanyCulture #Mentorship",
                "platforms": "facebook,instagram",
                "image_url": "https://images.unsplash.com/photo-1517245386807-bb43f82c33c4?w=800",
            },
        ]

        from datetime import timedelta
        import random

        for i, post in enumerate(sample_posts):
            # Stagger posted_at times over the past week
            posted_at = datetime.now() - timedelta(days=i, hours=random.randint(1, 12))

            db.execute(text("""
                INSERT INTO recruit_social_posts
                (content, platforms, image_url, status, posted_at, engagement_data, created_at)
                VALUES (:content, :platforms, :image_url, 'posted', :posted_at, :engagement, NOW())
            """), {
                "content": post["content"],
                "platforms": post["platforms"],
                "image_url": post["image_url"],
                "posted_at": posted_at,
                "engagement": f'{{"likes": {random.randint(15, 150)}, "comments": {random.randint(2, 25)}, "shares": {random.randint(1, 20)}}}'
            })

        db.commit()
        return {"status": "success", "message": f"Seeded {len(sample_posts)} sample posts"}
    except SQLAlchemyError as e:
        logger.error(f"Error seeding posts: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/public/feed")
async def get_public_social_feed(
    limit: int = Query(10, le=50),
    db: Session = Depends(get_db)
):
    """
    Get recent social posts for public display on recruit portal.
    No authentication required - only shows published posts.
    """
    try:
        result = db.execute(text("""
            SELECT id, content, platforms, image_url, posted_at,
                   engagement_data, created_at
            FROM recruit_social_posts
            WHERE status = 'posted'
              AND posted_at IS NOT NULL
            ORDER BY posted_at DESC
            LIMIT :limit
        """), {"limit": limit})

        posts = []
        for row in result:
            row_dict = dict(row._mapping)
            posts.append({
                "id": row_dict["id"],
                "content": row_dict["content"],
                "platforms": (row_dict["platforms"] or "").split(","),
                "image_url": row_dict["image_url"],
                "posted_at": row_dict["posted_at"].isoformat() if row_dict["posted_at"] else None,
                "engagement": row_dict.get("engagement_data") or {}
            })

        return {"posts": posts, "count": len(posts)}
    except Exception as e:
        logger.error(f"Error getting public feed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
