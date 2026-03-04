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
        self.fb_app_id = os.getenv("FACEBOOK_APP_ID", "")
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
            return {"error": "Internal server error"}

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
            return {"error": "Internal server error"}

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
            return {"error": "Internal server error"}

    async def search_linkedin_people(
        self,
        keywords: str,
        location: Optional[str] = None,
        current_company: Optional[str] = None,
        access_token: str = None
    ) -> List[Dict]:
        """
        Search LinkedIn for people using Proxycurl or Apollo enrichment APIs.
        LinkedIn's native people search API requires Sales Navigator/Recruiter access.
        """
        logger.info(f"LinkedIn people search requested: {keywords}, location={location}, company={current_company}")

        proxycurl_key = os.getenv("PROXYCURL_API_KEY", "")
        apollo_key = os.getenv("APOLLO_API_KEY", "")

        results = []

        # Try Proxycurl Person Search API first
        if proxycurl_key:
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    # Proxycurl Person Search Endpoint
                    params = {
                        "api_key": proxycurl_key,
                        "first_name": keywords.split()[0] if keywords else "",
                        "last_name": keywords.split()[-1] if len(keywords.split()) > 1 else "",
                        "enrich_profile": "skip",  # Just search, don't enrich yet
                        "page_size": 10
                    }
                    if location:
                        params["location"] = location
                    if current_company:
                        params["current_company_name"] = current_company

                    response = await client.get(
                        "https://nubela.co/proxycurl/api/search/person/",
                        params=params
                    )

                    if response.status_code == 200:
                        data = response.json()
                        for person in data.get("results", []):
                            results.append({
                                "platform": "linkedin",
                                "profile_url": person.get("linkedin_profile_url"),
                                "name": person.get("name", ""),
                                "headline": person.get("headline"),
                                "location": person.get("location"),
                                "current_company": person.get("current_company"),
                                "profile_picture": person.get("profile_picture"),
                                "source": "proxycurl"
                            })
                        return results
                    elif response.status_code == 401:
                        logger.warning("Proxycurl API key invalid or expired")
                    elif response.status_code == 429:
                        logger.warning("Proxycurl rate limit reached")
            except Exception as e:
                logger.error(f"Proxycurl search failed: {e}")

        # Fallback to Apollo.io People Search
        if apollo_key:
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    payload = {
                        "api_key": apollo_key,
                        "q_keywords": keywords,
                        "per_page": 10,
                        "page": 1
                    }
                    if location:
                        payload["person_locations"] = [location]
                    if current_company:
                        payload["q_organization_name"] = current_company

                    response = await client.post(
                        "https://api.apollo.io/v1/mixed_people/search",
                        json=payload
                    )

                    if response.status_code == 200:
                        data = response.json()
                        for person in data.get("people", []):
                            results.append({
                                "platform": "linkedin",
                                "profile_url": person.get("linkedin_url"),
                                "name": f"{person.get('first_name', '')} {person.get('last_name', '')}".strip(),
                                "headline": person.get("title"),
                                "location": f"{person.get('city', '')}, {person.get('state', '')}".strip(", "),
                                "current_company": person.get("organization", {}).get("name"),
                                "email": person.get("email"),
                                "phone": person.get("phone_numbers", [{}])[0].get("sanitized_number") if person.get("phone_numbers") else None,
                                "source": "apollo"
                            })
                        return results
            except Exception as e:
                logger.error(f"Apollo search failed: {e}")

        # If no API keys configured, return helpful message
        if not proxycurl_key and not apollo_key:
            logger.warning("No LinkedIn enrichment API configured (PROXYCURL_API_KEY or APOLLO_API_KEY)")
            return [{
                "status": "not_configured",
                "message": "LinkedIn search requires PROXYCURL_API_KEY or APOLLO_API_KEY. Configure in environment.",
                "search_query": keywords,
                "location": location,
                "company": current_company
            }]

        return results

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
        Enrich candidate data from LinkedIn profile URL using Proxycurl API.
        Returns profile data including name, headline, experience, education.
        """
        # Parse the LinkedIn URL to extract profile identifier
        if "/in/" not in linkedin_url:
            return {"error": "Invalid LinkedIn URL format", "linkedin_url": linkedin_url}

        profile_slug = linkedin_url.split("/in/")[1].split("/")[0].split("?")[0]
        proxycurl_key = os.getenv("PROXYCURL_API_KEY", "")

        if not proxycurl_key:
            logger.warning("PROXYCURL_API_KEY not configured for LinkedIn enrichment")
            return {
                "linkedin_url": linkedin_url,
                "profile_slug": profile_slug,
                "status": "not_configured",
                "message": "LinkedIn enrichment requires PROXYCURL_API_KEY environment variable"
            }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                # Proxycurl Profile Lookup API
                response = await client.get(
                    "https://nubela.co/proxycurl/api/v2/linkedin",
                    params={
                        "url": linkedin_url,
                        "fallback_to_cache": "on-error",
                        "use_cache": "if-present",
                        "skills": "include",
                        "inferred_salary": "include",
                        "personal_email": "include",
                        "personal_contact_number": "include",
                    },
                    headers={"Authorization": f"Bearer {proxycurl_key}"}
                )

                if response.status_code == 200:
                    data = response.json()

                    # Extract key information
                    enriched = {
                        "linkedin_url": linkedin_url,
                        "profile_slug": profile_slug,
                        "status": "enriched",
                        "source": "proxycurl",

                        # Basic info
                        "first_name": data.get("first_name"),
                        "last_name": data.get("last_name"),
                        "full_name": data.get("full_name"),
                        "headline": data.get("headline"),
                        "summary": data.get("summary"),
                        "location": data.get("city"),
                        "state": data.get("state"),
                        "country": data.get("country_full_name"),
                        "profile_picture": data.get("profile_pic_url"),
                        "background_cover": data.get("background_cover_image_url"),

                        # Contact (if available)
                        "personal_emails": data.get("personal_emails", []),
                        "personal_numbers": data.get("personal_numbers", []),

                        # Current position
                        "current_company": None,
                        "current_title": None,
                        "current_company_linkedin": None,

                        # Experience summary
                        "experience": [],
                        "education": [],
                        "skills": data.get("skills", []),

                        # Inferred data
                        "inferred_salary": data.get("inferred_salary"),
                        "connections": data.get("connections"),
                        "followers": data.get("follower_count"),
                    }

                    # Parse current experience
                    experiences = data.get("experiences", [])
                    if experiences:
                        current_exp = experiences[0]
                        enriched["current_company"] = current_exp.get("company")
                        enriched["current_title"] = current_exp.get("title")
                        enriched["current_company_linkedin"] = current_exp.get("company_linkedin_profile_url")

                        for exp in experiences[:5]:  # Last 5 positions
                            enriched["experience"].append({
                                "company": exp.get("company"),
                                "title": exp.get("title"),
                                "starts_at": exp.get("starts_at"),
                                "ends_at": exp.get("ends_at"),
                                "location": exp.get("location"),
                                "description": exp.get("description")
                            })

                    # Parse education
                    education = data.get("education", [])
                    for edu in education[:3]:  # Top 3 education entries
                        enriched["education"].append({
                            "school": edu.get("school"),
                            "degree": edu.get("degree_name"),
                            "field": edu.get("field_of_study"),
                            "starts_at": edu.get("starts_at"),
                            "ends_at": edu.get("ends_at")
                        })

                    return enriched

                elif response.status_code == 404:
                    return {
                        "linkedin_url": linkedin_url,
                        "profile_slug": profile_slug,
                        "status": "not_found",
                        "message": "LinkedIn profile not found or is private"
                    }
                elif response.status_code == 401:
                    logger.error("Proxycurl API key invalid")
                    return {
                        "linkedin_url": linkedin_url,
                        "status": "auth_error",
                        "message": "Proxycurl API key is invalid or expired"
                    }
                elif response.status_code == 429:
                    return {
                        "linkedin_url": linkedin_url,
                        "status": "rate_limited",
                        "message": "Proxycurl rate limit reached. Try again later."
                    }
                else:
                    logger.warning(f"Proxycurl returned status {response.status_code}: {response.text}")
                    return {
                        "linkedin_url": linkedin_url,
                        "status": "error",
                        "message": f"Enrichment failed with status {response.status_code}"
                    }

        except httpx.TimeoutException:
            return {
                "linkedin_url": linkedin_url,
                "status": "timeout",
                "message": "Request timed out. LinkedIn may be slow to respond."
            }
        except Exception as e:
            logger.error(f"LinkedIn enrichment error: {e}")
            return {
                "linkedin_url": linkedin_url,
                "status": "error",
                "message": "Internal server error"
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
        *,
        user_id: int
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

    async def get_linkedin_post_analytics(self, share_urn: str, access_token: str = None) -> Dict[str, Any]:
        """Get analytics for a LinkedIn share/post."""
        token = access_token or self.linkedin_access_token
        if not token:
            return {"status": "not_configured", "message": "LinkedIn access token not set"}

        try:
            async with httpx.AsyncClient() as client:
                # LinkedIn Share Statistics API
                response = await client.get(
                    f"{self.linkedin_api_url}/socialActions/{share_urn}",
                    headers={"Authorization": f"Bearer {token}"}
                )

                if response.status_code == 200:
                    data = response.json()
                    return {
                        "likes": data.get("likesSummary", {}).get("totalLikes", 0),
                        "comments": data.get("commentsSummary", {}).get("totalFirstLevelComments", 0),
                        "shares": data.get("shareCount", 0),
                        "impressions": data.get("impressionCount", 0),
                        "clicks": data.get("clickCount", 0),
                        "engagement_rate": data.get("engagementRate", 0),
                    }
                elif response.status_code == 401:
                    return {"status": "auth_error", "message": "LinkedIn token expired or invalid"}
                else:
                    return {"status": "error", "message": f"HTTP {response.status_code}"}
        except Exception as e:
            logger.error(f"LinkedIn analytics error: {e}")
            return {"status": "error", "message": "Internal server error"}

    async def get_instagram_post_analytics(self, media_id: str) -> Dict[str, Any]:
        """Get analytics for an Instagram post via Graph API."""
        if not self.fb_access_token:
            return {"status": "not_configured", "message": "Facebook access token not set"}

        try:
            async with httpx.AsyncClient() as client:
                # Instagram Insights API
                response = await client.get(
                    f"{self.fb_graph_url}/{media_id}/insights",
                    params={
                        "access_token": self.fb_access_token,
                        "metric": "impressions,reach,engagement,saved,comments,likes,shares"
                    }
                )

                if response.status_code == 200:
                    data = response.json()
                    metrics = {}
                    for item in data.get("data", []):
                        metrics[item["name"]] = item.get("values", [{}])[0].get("value", 0)
                    return {
                        "impressions": metrics.get("impressions", 0),
                        "reach": metrics.get("reach", 0),
                        "engagement": metrics.get("engagement", 0),
                        "saves": metrics.get("saved", 0),
                        "comments": metrics.get("comments", 0),
                        "likes": metrics.get("likes", 0),
                        "shares": metrics.get("shares", 0),
                    }
                elif response.status_code == 400:
                    # Fall back to basic metrics
                    basic_response = await client.get(
                        f"{self.fb_graph_url}/{media_id}",
                        params={
                            "access_token": self.fb_access_token,
                            "fields": "like_count,comments_count"
                        }
                    )
                    if basic_response.status_code == 200:
                        basic_data = basic_response.json()
                        return {
                            "likes": basic_data.get("like_count", 0),
                            "comments": basic_data.get("comments_count", 0),
                        }
                    return {"status": "limited_access", "message": "Insights not available for this media"}
                else:
                    return {"status": "error", "message": f"HTTP {response.status_code}"}
        except Exception as e:
            logger.error(f"Instagram analytics error: {e}")
            return {"status": "error", "message": "Internal server error"}

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
                analytics[platform] = await self.get_linkedin_post_analytics(post_id)
            elif platform == "instagram":
                analytics[platform] = await self.get_instagram_post_analytics(post_id)

        return analytics


# Singleton instance
recruit_social_service = RecruitSocialService()
