"""
Recruit Social Media Routes
API endpoints for LinkedIn, Facebook, and Instagram integrations.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime
from database import get_db
from services.recruit_social_service import recruit_social_service, SocialProfile
import logging
import os

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/recruit-social", tags=["recruit-social"])


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
    url = recruit_social_service.get_facebook_oauth_url(redirect_uri)
    return {"oauth_url": url}


@router.get("/oauth/linkedin/url")
async def get_linkedin_oauth_url(
    redirect_uri: str = Query(..., description="OAuth callback URL")
):
    """Get LinkedIn OAuth authorization URL."""
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
    except Exception as e:
        logger.error(f"Facebook OAuth error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
    except Exception as e:
        logger.error(f"LinkedIn OAuth error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
    except Exception as e:
        logger.error(f"Error creating social post: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
    except Exception as e:
        logger.error(f"Error getting social posts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
        raise HTTPException(status_code=500, detail=str(e))


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
    except Exception as e:
        logger.error(f"Error enriching from LinkedIn: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
        raise HTTPException(status_code=500, detail=str(e))


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
        raise HTTPException(status_code=500, detail=str(e))


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
        raise HTTPException(status_code=500, detail=str(e))


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
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# MIGRATION ENDPOINT
# ============================================================================

@router.post("/admin/run-migration")
async def run_social_migration(
    admin_key: str = Query(...),
    db: Session = Depends(get_db)
):
    """Run migration to create social media tables."""
    if admin_key != "perennia-admin-2024":
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
    except Exception as e:
        logger.error(f"Migration error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
