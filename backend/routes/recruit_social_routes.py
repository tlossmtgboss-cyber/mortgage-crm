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
from urllib.parse import urlparse
from database import get_db
from auth.dependencies import get_current_user
from database.models import User
from services.recruit_social_service import recruit_social_service, SocialProfile
import logging
import os
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

_ALLOWED_REDIRECT_HOSTS = {"app.perenniaai.com", "localhost", "127.0.0.1"}


def _validate_redirect_uri(uri: str) -> str:
    parsed = urlparse(uri)
    hostname = parsed.hostname or ""
    if parsed.scheme not in ("https", "http"):
        raise HTTPException(status_code=400, detail="Invalid redirect URI scheme")
    if hostname not in _ALLOWED_REDIRECT_HOSTS and not hostname.endswith(".perenniaai.com"):
        raise HTTPException(status_code=400, detail="Redirect URI not allowed")
    return uri


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
    redirect_uri: str = Query(..., description="OAuth callback URL"),
    current_user: User = Depends(get_current_user),
):
    """Get Facebook OAuth authorization URL."""
    _validate_redirect_uri(redirect_uri)
    url = recruit_social_service.get_facebook_oauth_url(redirect_uri)
    return {"oauth_url": url}


@router.get("/oauth/linkedin/url")
async def get_linkedin_oauth_url(
    redirect_uri: str = Query(..., description="OAuth callback URL"),
    current_user: User = Depends(get_current_user),
):
    """Get LinkedIn OAuth authorization URL."""
    _validate_redirect_uri(redirect_uri)
    url = recruit_social_service.get_linkedin_oauth_url(redirect_uri)
    return {"oauth_url": url}


@router.post("/oauth/facebook/callback")
async def facebook_oauth_callback(
    request: OAuthCallbackRequest,
    current_user: User = Depends(get_current_user),
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
        org_id = current_user.organization_id
        db.execute(text("""
            INSERT INTO social_tokens (platform, access_token, expires_at, organization_id, created_at)
            VALUES ('facebook', :token, :expires, :org_id, NOW())
            ON CONFLICT (platform, organization_id) DO UPDATE SET
                access_token = :token,
                expires_at = :expires,
                updated_at = NOW()
        """), {
            "token": token_data.get("access_token"),
            "expires": datetime.now().isoformat() if not token_data.get("expires_in") else None,
            "org_id": org_id,
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
    current_user: User = Depends(get_current_user),
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
        org_id = current_user.organization_id
        db.execute(text("""
            INSERT INTO social_tokens (platform, access_token, expires_at, organization_id, created_at)
            VALUES ('linkedin', :token, :expires, :org_id, NOW())
            ON CONFLICT (platform, organization_id) DO UPDATE SET
                access_token = :token,
                expires_at = :expires,
                updated_at = NOW()
        """), {
            "token": token_data.get("access_token"),
            "expires": datetime.now().isoformat() if not token_data.get("expires_in") else None,
            "org_id": org_id,
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
    current_user: User = Depends(get_current_user),
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
            INSERT INTO recruit_social_posts (content, platforms, image_url, scheduled_at, status, organization_id, created_by, created_at)
            VALUES (:content, :platforms, :image_url, :scheduled_at, :status, :org_id, :created_by, NOW())
        """), {
            "content": post.content,
            "platforms": ",".join(post.platforms),
            "image_url": post.image_url,
            "scheduled_at": post.scheduled_time,
            "status": "scheduled" if post.scheduled_time else "posted",
            "org_id": current_user.organization_id,
            "created_by": current_user.id
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get recruiting social media posts."""
    try:
        org_id = current_user.organization_id
        query = """
            SELECT id, content, platforms, image_url, scheduled_at,
                   status, posted_at, engagement_data, created_at
            FROM recruit_social_posts
            WHERE organization_id = :org_id
        """
        params = {"limit": limit, "org_id": org_id}

        if status:
            query += " AND status = :status"
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get engagement analytics for a social post."""
    try:
        result = db.execute(text("""
            SELECT id, platforms, engagement_data, external_post_ids
            FROM recruit_social_posts
            WHERE id = :post_id AND organization_id = :org_id
        """), {"post_id": post_id, "org_id": current_user.organization_id})
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Enrich candidate data from LinkedIn profile."""
    try:
        # Verify candidate belongs to user's org
        org_check = db.execute(text(
            "SELECT id FROM mm_candidates WHERE id = :cid AND organization_id = :org_id"
        ), {"cid": request.candidate_id, "org_id": current_user.organization_id})
        if not org_check.fetchone():
            raise HTTPException(status_code=404, detail="Candidate not found")

        enrichment = await recruit_social_service.enrich_candidate_from_linkedin(
            request.linkedin_url
        )

        if enrichment:
            # Store enrichment data (already verified org ownership above)
            db.execute(text("""
                UPDATE mm_candidates
                SET linkedin_url = :linkedin_url,
                    linkedin_data = :linkedin_data,
                    updated_at = NOW()
                WHERE id = :candidate_id AND organization_id = :org_id
            """), {
                "candidate_id": request.candidate_id,
                "linkedin_url": request.linkedin_url,
                "linkedin_data": str(enrichment),
                "org_id": current_user.organization_id
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get recent LinkedIn posts for a candidate."""
    try:
        # Get candidate's LinkedIn info (tenant-scoped)
        result = db.execute(text("""
            SELECT id, name, linkedin_url, linkedin_data
            FROM mm_candidates
            WHERE id = :candidate_id AND organization_id = :org_id
        """), {"candidate_id": candidate_id, "org_id": current_user.organization_id})
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
async def get_social_connections(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get status of social media connections."""
    try:
        result = db.execute(text("""
            SELECT platform,
                   access_token IS NOT NULL as connected,
                   expires_at,
                   updated_at
            FROM social_tokens
            WHERE organization_id = :org_id
        """), {"org_id": current_user.organization_id})
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
async def get_facebook_page_info(current_user: User = Depends(get_current_user)):
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
async def get_linkedin_profile(current_user: User = Depends(get_current_user)):
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
# Migration/admin endpoints removed — use backend/migrations/ scripts instead.
# ============================================================================


# ============================================================================
# PUBLIC PORTAL ENDPOINTS (no auth required)
# ============================================================================

@router.get("/public/feed")
async def get_public_social_feed(
    slug: str = Query(..., description="Portal workspace slug to scope feed to correct organization"),
    limit: int = Query(10, le=50),
    db: Session = Depends(get_db)
):
    """
    Get recent social posts for public display on recruit portal.
    No authentication required - only shows published posts scoped to the portal's organization.
    """
    try:
        # Resolve slug → organization_id via workspace/candidate join
        workspace = db.execute(text("""
            SELECT c.organization_id
            FROM recruit_portal_workspaces w
            JOIN mm_candidates c ON c.id = w.candidate_id
            WHERE w.slug = :slug AND w.is_active = true
        """), {"slug": slug}).fetchone()
        if not workspace:
            raise HTTPException(status_code=404, detail="Portal not found")

        result = db.execute(text("""
            SELECT id, content, platforms, image_url, posted_at,
                   engagement_data, created_at
            FROM recruit_social_posts
            WHERE status = 'posted'
              AND posted_at IS NOT NULL
              AND organization_id = :org_id
            ORDER BY posted_at DESC
            LIMIT :limit
        """), {"limit": limit, "org_id": workspace.organization_id})

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
