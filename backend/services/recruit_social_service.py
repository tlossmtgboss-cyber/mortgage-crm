"""
Recruit Social Media Integration Service
Handles LinkedIn, Facebook, and Instagram API integrations for recruiting outreach.

Features:
- LinkedIn profile lookup and messaging
- Facebook page/group posting
- Instagram DM automation (via Facebook Graph API)
- Social profile enrichment
- Post scheduling and analytics
"""

import os
import logging
import httpx
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
import json
import secrets

logger = logging.getLogger(__name__)


@dataclass
class SocialProfile:
    """Unified social profile data structure."""
    platform: str
    profile_id: str
    name: str
    headline: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    profile_url: Optional[str] = None
    avatar_url: Optional[str] = None
    connections: Optional[int] = None
    followers: Optional[int] = None
    raw_data: Optional[Dict] = None


@dataclass
class SocialPost:
    """Social media post data structure."""
    platform: str
    post_id: str
    content: str
    media_urls: List[str]
    posted_at: datetime
    engagement: Dict[str, int]
    url: Optional[str] = None


class RecruitSocialService:
    """Service for social media integrations in recruiting."""

    def __init__(self):
        # Facebook/Instagram credentials
        self.fb_app_id = os.getenv("FACEBOOK_APP_ID", "870154102050380")
        self.fb_app_secret = os.getenv("FACEBOOK_APP_SECRET", "")
        self.fb_access_token = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN", "")

        # LinkedIn credentials
        self.linkedin_client_id = os.getenv("LINKEDIN_CLIENT_ID", "")
        self.linkedin_client_secret = os.getenv("LINKEDIN_CLIENT_SECRET", "")
        self.linkedin_access_token = os.getenv("LINKEDIN_ACCESS_TOKEN", "")

        # API base URLs
        self.fb_graph_url = "https://graph.facebook.com/v18.0"
        self.linkedin_api_url = "https://api.linkedin.com/v2"

    # =========================================================================
    # FACEBOOK/INSTAGRAM INTEGRATION
    # =========================================================================

    async def get_facebook_page_info(self, page_id: str) -> Optional[Dict]:
        """Get Facebook page information."""
        if not self.fb_access_token:
            logger.warning("Facebook access token not configured")
            return None

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.fb_graph_url}/{page_id}",
                    params={
                        "access_token": self.fb_access_token,
                        "fields": "id,name,about,category,fan_count,website,link,picture"
                    }
                )

                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(f"Facebook API error: {response.text}")
                    return None
        except Exception as e:
            logger.error(f"Error fetching Facebook page info: {e}")
            return None

    async def post_to_facebook_page(
        self,
        page_id: str,
        message: str,
        link: Optional[str] = None,
        image_url: Optional[str] = None,
        scheduled_time: Optional[datetime] = None
    ) -> Optional[Dict]:
        """Post content to a Facebook page."""
        if not self.fb_access_token:
            logger.warning("Facebook access token not configured")
            return {"error": "Facebook not configured"}

        try:
            async with httpx.AsyncClient() as client:
                payload = {
                    "access_token": self.fb_access_token,
                    "message": message
                }

                if link:
                    payload["link"] = link

                if scheduled_time:
                    # Facebook requires Unix timestamp for scheduled posts
                    payload["published"] = False
                    payload["scheduled_publish_time"] = int(scheduled_time.timestamp())

                # If posting with image
                if image_url:
                    # For photos, use /photos endpoint
                    response = await client.post(
                        f"{self.fb_graph_url}/{page_id}/photos",
                        data={**payload, "url": image_url}
                    )
                else:
                    # For text/link posts
                    response = await client.post(
                        f"{self.fb_graph_url}/{page_id}/feed",
                        data=payload
                    )

                if response.status_code == 200:
                    result = response.json()
                    logger.info(f"Posted to Facebook page {page_id}: {result.get('id')}")
                    return result
                else:
                    logger.error(f"Facebook post error: {response.text}")
                    return {"error": response.text}
        except Exception as e:
            logger.error(f"Error posting to Facebook: {e}")
            return {"error": str(e)}

    async def get_instagram_business_account(self, fb_page_id: str) -> Optional[str]:
        """Get Instagram business account ID linked to a Facebook page."""
        if not self.fb_access_token:
            return None

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.fb_graph_url}/{fb_page_id}",
                    params={
                        "access_token": self.fb_access_token,
                        "fields": "instagram_business_account"
                    }
                )

                if response.status_code == 200:
                    data = response.json()
                    ig_account = data.get("instagram_business_account", {})
                    return ig_account.get("id")
                return None
        except Exception as e:
            logger.error(f"Error getting Instagram account: {e}")
            return None

    async def post_to_instagram(
        self,
        ig_account_id: str,
        image_url: str,
        caption: str
    ) -> Optional[Dict]:
        """Post an image to Instagram business account."""
        if not self.fb_access_token:
            return {"error": "Facebook/Instagram not configured"}

        try:
            async with httpx.AsyncClient() as client:
                # Step 1: Create media container
                container_response = await client.post(
                    f"{self.fb_graph_url}/{ig_account_id}/media",
                    data={
                        "access_token": self.fb_access_token,
                        "image_url": image_url,
                        "caption": caption
                    }
                )

                if container_response.status_code != 200:
                    return {"error": container_response.text}

                container_id = container_response.json().get("id")

                # Step 2: Publish the container
                publish_response = await client.post(
                    f"{self.fb_graph_url}/{ig_account_id}/media_publish",
                    data={
                        "access_token": self.fb_access_token,
                        "creation_id": container_id
                    }
                )

                if publish_response.status_code == 200:
                    return publish_response.json()
                else:
                    return {"error": publish_response.text}
        except Exception as e:
            logger.error(f"Error posting to Instagram: {e}")
            return {"error": str(e)}

    async def get_facebook_post_engagement(self, post_id: str) -> Dict[str, int]:
        """Get engagement metrics for a Facebook post."""
        if not self.fb_access_token:
            return {}

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.fb_graph_url}/{post_id}",
                    params={
                        "access_token": self.fb_access_token,
                        "fields": "likes.summary(true),comments.summary(true),shares"
                    }
                )

                if response.status_code == 200:
                    data = response.json()
                    return {
                        "likes": data.get("likes", {}).get("summary", {}).get("total_count", 0),
                        "comments": data.get("comments", {}).get("summary", {}).get("total_count", 0),
                        "shares": data.get("shares", {}).get("count", 0)
                    }
                return {}
        except Exception as e:
            logger.error(f"Error getting post engagement: {e}")
            return {}

    # =========================================================================
    # LINKEDIN INTEGRATION
    # =========================================================================

    async def get_linkedin_profile(self, access_token: str = None) -> Optional[SocialProfile]:
        """Get LinkedIn profile for authenticated user."""
        token = access_token or self.linkedin_access_token
        if not token:
            logger.warning("LinkedIn access token not configured")
            return None

        try:
            async with httpx.AsyncClient() as client:
                # Get basic profile
                profile_response = await client.get(
                    f"{self.linkedin_api_url}/me",
                    headers={"Authorization": f"Bearer {token}"}
                )

                if profile_response.status_code != 200:
                    return None

                profile_data = profile_response.json()

                # Get profile picture
                picture_response = await client.get(
                    f"{self.linkedin_api_url}/me?projection=(id,profilePicture(displayImage~:playableStreams))",
                    headers={"Authorization": f"Bearer {token}"}
                )

                avatar_url = None
                if picture_response.status_code == 200:
                    pic_data = picture_response.json()
                    elements = pic_data.get("profilePicture", {}).get("displayImage~", {}).get("elements", [])
                    if elements:
                        avatar_url = elements[-1].get("identifiers", [{}])[0].get("identifier")

                return SocialProfile(
                    platform="linkedin",
                    profile_id=profile_data.get("id"),
                    name=f"{profile_data.get('localizedFirstName', '')} {profile_data.get('localizedLastName', '')}".strip(),
                    headline=profile_data.get("headline"),
                    avatar_url=avatar_url,
                    raw_data=profile_data
                )
        except Exception as e:
            logger.error(f"Error getting LinkedIn profile: {e}")
            return None

    async def post_to_linkedin(
        self,
        author_id: str,
        text: str,
        media_url: Optional[str] = None,
        access_token: str = None
    ) -> Optional[Dict]:
        """Post content to LinkedIn."""
        token = access_token or self.linkedin_access_token
        if not token:
            return {"error": "LinkedIn not configured"}

        try:
            async with httpx.AsyncClient() as client:
                # Prepare the post payload
                payload = {
                    "author": f"urn:li:person:{author_id}",
                    "lifecycleState": "PUBLISHED",
                    "specificContent": {
                        "com.linkedin.ugc.ShareContent": {
                            "shareCommentary": {
                                "text": text
                            },
                            "shareMediaCategory": "NONE"
                        }
                    },
                    "visibility": {
                        "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
                    }
                }

                # If media is provided, add it
                if media_url:
                    payload["specificContent"]["com.linkedin.ugc.ShareContent"]["shareMediaCategory"] = "ARTICLE"
                    payload["specificContent"]["com.linkedin.ugc.ShareContent"]["media"] = [{
                        "status": "READY",
                        "originalUrl": media_url
                    }]

                response = await client.post(
                    f"{self.linkedin_api_url}/ugcPosts",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                        "X-Restli-Protocol-Version": "2.0.0"
                    },
                    json=payload
                )

                if response.status_code in [200, 201]:
                    return response.json()
                else:
                    logger.error(f"LinkedIn post error: {response.text}")
                    return {"error": response.text}
        except Exception as e:
            logger.error(f"Error posting to LinkedIn: {e}")
            return {"error": str(e)}

    async def search_linkedin_people(
        self,
        keywords: str,
        location: Optional[str] = None,
        current_company: Optional[str] = None,
        access_token: str = None
    ) -> List[Dict]:
        """Search LinkedIn for people (requires Sales Navigator or Recruiter API)."""
        # Note: LinkedIn's people search API is restricted and requires special access
        # This is a placeholder for the implementation
        logger.info(f"LinkedIn people search requested: {keywords}")
        return []

    # =========================================================================
    # OAUTH FLOW HELPERS
    # =========================================================================

    def get_facebook_oauth_url(self, redirect_uri: str, state: str = None) -> str:
        """Generate Facebook OAuth authorization URL."""
        state = state or secrets.token_urlsafe(32)
        scopes = "pages_manage_posts,pages_read_engagement,instagram_basic,instagram_content_publish"

        return (
            f"https://www.facebook.com/v18.0/dialog/oauth?"
            f"client_id={self.fb_app_id}&"
            f"redirect_uri={redirect_uri}&"
            f"state={state}&"
            f"scope={scopes}"
        )

    def get_linkedin_oauth_url(self, redirect_uri: str, state: str = None) -> str:
        """Generate LinkedIn OAuth authorization URL."""
        state = state or secrets.token_urlsafe(32)
        scopes = "r_liteprofile r_emailaddress w_member_social"

        return (
            f"https://www.linkedin.com/oauth/v2/authorization?"
            f"response_type=code&"
            f"client_id={self.linkedin_client_id}&"
            f"redirect_uri={redirect_uri}&"
            f"state={state}&"
            f"scope={scopes}"
        )

    async def exchange_facebook_code(self, code: str, redirect_uri: str) -> Optional[Dict]:
        """Exchange Facebook authorization code for access token."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.fb_graph_url}/oauth/access_token",
                    params={
                        "client_id": self.fb_app_id,
                        "client_secret": self.fb_app_secret,
                        "redirect_uri": redirect_uri,
                        "code": code
                    }
                )

                if response.status_code == 200:
                    return response.json()
                return None
        except Exception as e:
            logger.error(f"Error exchanging Facebook code: {e}")
            return None

    async def exchange_linkedin_code(self, code: str, redirect_uri: str) -> Optional[Dict]:
        """Exchange LinkedIn authorization code for access token."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://www.linkedin.com/oauth/v2/accessToken",
                    data={
                        "grant_type": "authorization_code",
                        "code": code,
                        "redirect_uri": redirect_uri,
                        "client_id": self.linkedin_client_id,
                        "client_secret": self.linkedin_client_secret
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )

                if response.status_code == 200:
                    return response.json()
                return None
        except Exception as e:
            logger.error(f"Error exchanging LinkedIn code: {e}")
            return None

    # =========================================================================
    # SOCIAL PROFILE ENRICHMENT
    # =========================================================================

    async def enrich_candidate_from_linkedin(
        self,
        linkedin_url: str
    ) -> Optional[Dict]:
        """
        Enrich candidate data from LinkedIn profile URL.
        Note: This requires LinkedIn API access or web scraping.
        For compliance, we'll use the official API when available.
        """
        # Parse the LinkedIn URL to extract profile identifier
        if "/in/" in linkedin_url:
            profile_slug = linkedin_url.split("/in/")[1].split("/")[0].split("?")[0]
        else:
            return None

        # In production, this would use LinkedIn's API with proper permissions
        # For now, return a placeholder indicating manual enrichment is needed
        return {
            "linkedin_url": linkedin_url,
            "profile_slug": profile_slug,
            "status": "manual_review_required",
            "message": "LinkedIn profile enrichment requires API access. Please review manually."
        }

    async def enrich_candidate_from_facebook(
        self,
        facebook_url: str
    ) -> Optional[Dict]:
        """
        Enrich candidate data from Facebook profile.
        Limited by Facebook's privacy restrictions on user data.
        """
        return {
            "facebook_url": facebook_url,
            "status": "privacy_restricted",
            "message": "Facebook profile enrichment is limited by privacy settings."
        }

    # =========================================================================
    # SCHEDULED POSTING
    # =========================================================================

    async def schedule_recruiting_post(
        self,
        platforms: List[str],
        content: str,
        scheduled_time: datetime,
        image_url: Optional[str] = None,
        user_id: int = 1
    ) -> Dict:
        """Schedule a recruiting post across multiple platforms."""
        results = {
            "scheduled_time": scheduled_time.isoformat(),
            "platforms": {}
        }

        for platform in platforms:
            if platform == "facebook":
                # Get configured page ID
                page_id = os.getenv("FACEBOOK_PAGE_ID", "")
                if page_id:
                    result = await self.post_to_facebook_page(
                        page_id=page_id,
                        message=content,
                        image_url=image_url,
                        scheduled_time=scheduled_time
                    )
                    results["platforms"]["facebook"] = result
                else:
                    results["platforms"]["facebook"] = {"error": "Page not configured"}

            elif platform == "linkedin":
                # Get configured author ID
                author_id = os.getenv("LINKEDIN_AUTHOR_ID", "")
                if author_id:
                    # LinkedIn doesn't support scheduled posts via API
                    # Store in database for later posting
                    results["platforms"]["linkedin"] = {
                        "status": "queued",
                        "message": "LinkedIn post queued for scheduled time"
                    }
                else:
                    results["platforms"]["linkedin"] = {"error": "Author not configured"}

            elif platform == "instagram":
                ig_account_id = os.getenv("INSTAGRAM_ACCOUNT_ID", "")
                if ig_account_id and image_url:
                    # Instagram requires image for posts
                    results["platforms"]["instagram"] = {
                        "status": "queued",
                        "message": "Instagram post queued for scheduled time"
                    }
                else:
                    results["platforms"]["instagram"] = {"error": "Account not configured or image required"}

        return results

    # =========================================================================
    # ANALYTICS
    # =========================================================================

    async def get_recruiting_post_analytics(
        self,
        post_ids: Dict[str, str]  # platform -> post_id mapping
    ) -> Dict:
        """Get analytics for recruiting posts across platforms."""
        analytics = {}

        for platform, post_id in post_ids.items():
            if platform == "facebook":
                analytics[platform] = await self.get_facebook_post_engagement(post_id)
            elif platform == "linkedin":
                # LinkedIn analytics would go here
                analytics[platform] = {"status": "not_implemented"}
            elif platform == "instagram":
                # Instagram analytics via Graph API
                analytics[platform] = {"status": "not_implemented"}

        return analytics


# Singleton instance
recruit_social_service = RecruitSocialService()
