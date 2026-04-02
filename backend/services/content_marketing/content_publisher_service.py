"""
Content Publisher Service

Handles multi-channel content publishing and scheduling:
- Publish to blog, LinkedIn, Facebook, Instagram, email
- Schedule future publications
- Track publishing status and results
- Fetch engagement metrics
"""

import os
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import httpx

from models.content_marketing import (
    ContentBrief, ContentPublishLog, ContentStatus, ContentChannel
)
from services.recruit_social_service import RecruitSocialService

logger = logging.getLogger(__name__)


class ContentPublisherService:
    """
    Service for multi-channel content publishing.

    Handles publishing to various platforms and tracking results.
    Integrates with existing social media services.
    """

    # Platform configuration
    PLATFORM_CONFIG = {
        "blog": {
            "requires_api": False,
            "supports_scheduling": True,
            "max_content_length": None,
        },
        "linkedin": {
            "requires_api": True,
            "supports_scheduling": True,
            "max_content_length": 3000,
        },
        "facebook": {
            "requires_api": True,
            "supports_scheduling": True,
            "max_content_length": 63206,
        },
        "instagram": {
            "requires_api": True,
            "supports_scheduling": False,  # Via FB API requires immediate publish
            "max_content_length": 2200,
            "requires_image": True,
        },
        "twitter": {
            "requires_api": True,
            "supports_scheduling": True,
            "max_content_length": 280,
        },
        "email": {
            "requires_api": False,
            "supports_scheduling": True,
            "max_content_length": None,
        },
    }

    def __init__(self, db: Session):
        """Initialize with database session."""
        self.db = db
        self.social_service = RecruitSocialService()

        # Platform credentials
        self.fb_page_id = os.getenv("FACEBOOK_PAGE_ID", "")
        self.ig_account_id = os.getenv("INSTAGRAM_ACCOUNT_ID", "")
        self.linkedin_org_id = os.getenv("LINKEDIN_ORG_ID", "")

    # =========================================================================
    # Publishing
    # =========================================================================

    async def publish_brief(
        self,
        brief_id: str,
        channels: Optional[List[str]] = None,
        publish_now: bool = False
    ) -> Dict[str, Any]:
        """
        Publish a content brief to specified channels.

        Args:
            brief_id: Brief to publish
            channels: Channels to publish to (defaults to brief's channels)
            publish_now: If True, publish immediately regardless of schedule

        Returns:
            Publishing results for each channel
        """
        brief = self.db.query(ContentBrief).filter(
            ContentBrief.id == brief_id
        ).first()

        if not brief:
            return {"success": False, "error": "Brief not found"}

        if not brief.generated_content:
            return {"success": False, "error": "Brief has no generated content"}

        # Use brief's channels if not specified
        channels = channels or brief.channels or []

        if not channels:
            return {"success": False, "error": "No channels specified"}

        results = {}
        all_success = True

        for channel in channels:
            result = await self._publish_to_channel(
                brief=brief,
                channel=channel,
                publish_now=publish_now
            )
            results[channel] = result
            if not result.get("success"):
                all_success = False

        # Update brief status
        if all_success:
            brief.status = ContentStatus.PUBLISHED.value
            brief.published_at = datetime.now(timezone.utc)
            brief.publish_results = results
        else:
            brief.status = ContentStatus.FAILED.value
            brief.publish_results = results

        self.db.commit()

        return {
            "success": all_success,
            "brief_id": brief_id,
            "channels_published": list(results.keys()),
            "results": results,
        }

    async def _publish_to_channel(
        self,
        brief: ContentBrief,
        channel: str,
        publish_now: bool = False
    ) -> Dict[str, Any]:
        """Publish content to a specific channel."""
        try:
            config = self.PLATFORM_CONFIG.get(channel)
            if not config:
                return {"success": False, "error": f"Unknown channel: {channel}"}

            # Check content length
            content = brief.generated_content or ""
            max_length = config.get("max_content_length")
            if max_length and len(content) > max_length:
                content = content[:max_length - 3] + "..."

            # Determine scheduled time
            scheduled_at = None
            if not publish_now and brief.scheduled_date:
                scheduled_at = datetime.combine(
                    brief.scheduled_date,
                    brief.scheduled_time or datetime.now().time()
                )
                # Only schedule if in the future
                if scheduled_at <= datetime.now():
                    scheduled_at = None

            # Publish based on channel
            if channel == "blog":
                result = await self._publish_to_blog(brief, content)
            elif channel == "linkedin":
                result = await self._publish_to_linkedin(brief, content, scheduled_at)
            elif channel == "facebook":
                result = await self._publish_to_facebook(brief, content, scheduled_at)
            elif channel == "instagram":
                result = await self._publish_to_instagram(brief, content)
            elif channel == "twitter":
                result = await self._publish_to_twitter(brief, content)
            elif channel == "email":
                result = await self._publish_to_email(brief, content, scheduled_at)
            else:
                result = {"success": False, "error": f"Publishing not implemented for {channel}"}

            # Log the publish attempt
            await self._log_publish_attempt(
                brief_id=brief.id,
                channel=channel,
                result=result,
                scheduled_at=scheduled_at
            )

            return result

        except Exception as e:
            logger.error(f"Error publishing to {channel}: {e}")
            return {"success": False, "error": "Internal server error"}

    async def _publish_to_blog(
        self,
        brief: ContentBrief,
        content: str
    ) -> Dict[str, Any]:
        """Publish to internal blog system."""
        # This would integrate with your blog_content_items table
        # For now, mark as ready for manual publishing
        return {
            "success": True,
            "status": "ready",
            "message": "Content ready for blog publishing",
            "title": brief.generated_title or brief.title or brief.topic,
            "content_preview": content[:200] + "...",
        }

    async def _publish_to_linkedin(
        self,
        brief: ContentBrief,
        content: str,
        scheduled_at: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Publish to LinkedIn."""
        if not self.social_service.linkedin_access_token:
            return {"success": False, "error": "LinkedIn not configured"}

        try:
            # LinkedIn API integration via recruit_social_service
            # The service would need to be extended for organization posts
            # For now, return as scheduled/ready

            if scheduled_at:
                return {
                    "success": True,
                    "status": "scheduled",
                    "scheduled_at": scheduled_at.isoformat(),
                    "message": "Content scheduled for LinkedIn"
                }

            # Would call LinkedIn API here
            return {
                "success": True,
                "status": "ready",
                "message": "Content ready for LinkedIn publishing",
                "content_preview": content[:200] + "..."
            }

        except Exception as e:
            return {"success": False, "error": "Internal server error"}

    async def _publish_to_facebook(
        self,
        brief: ContentBrief,
        content: str,
        scheduled_at: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Publish to Facebook page."""
        if not self.fb_page_id:
            return {"success": False, "error": "Facebook page ID not configured"}

        try:
            result = await self.social_service.post_to_facebook_page(
                page_id=self.fb_page_id,
                message=content,
                scheduled_time=scheduled_at
            )

            if result and "error" not in result:
                return {
                    "success": True,
                    "status": "scheduled" if scheduled_at else "published",
                    "post_id": result.get("id"),
                    "scheduled_at": scheduled_at.isoformat() if scheduled_at else None,
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error", "Unknown error")
                }

        except Exception as e:
            return {"success": False, "error": "Internal server error"}

    async def _publish_to_instagram(
        self,
        brief: ContentBrief,
        content: str
    ) -> Dict[str, Any]:
        """Publish to Instagram."""
        if not self.ig_account_id:
            # Try to get from Facebook page
            if self.fb_page_id:
                self.ig_account_id = await self.social_service.get_instagram_business_account(
                    self.fb_page_id
                )

        if not self.ig_account_id:
            return {"success": False, "error": "Instagram account not configured"}

        # Instagram requires an image
        # Would need image URL from brief or generated image
        return {
            "success": False,
            "error": "Instagram publishing requires an image URL",
            "status": "ready",
            "message": "Content ready - image required for Instagram"
        }

    async def _publish_to_twitter(
        self,
        brief: ContentBrief,
        content: str
    ) -> Dict[str, Any]:
        """Publish to Twitter/X."""
        # Twitter API integration would go here
        return {
            "success": True,
            "status": "ready",
            "message": "Content ready for Twitter publishing",
            "content_preview": content[:280]
        }

    async def _publish_to_email(
        self,
        brief: ContentBrief,
        content: str,
        scheduled_at: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Prepare content for email campaign."""
        # This would integrate with email service
        return {
            "success": True,
            "status": "scheduled" if scheduled_at else "ready",
            "scheduled_at": scheduled_at.isoformat() if scheduled_at else None,
            "message": "Content ready for email campaign",
            "subject": brief.generated_title or brief.title or brief.topic,
        }

    async def _log_publish_attempt(
        self,
        brief_id: str,
        channel: str,
        result: Dict[str, Any],
        scheduled_at: Optional[datetime] = None
    ) -> None:
        """Log a publish attempt."""
        try:
            log = ContentPublishLog(
                brief_id=brief_id,
                channel=channel,
                scheduled_at=scheduled_at,
                published_at=datetime.now(timezone.utc) if result.get("status") == "published" else None,
                status=result.get("status", "failed" if not result.get("success") else "pending"),
                external_post_id=result.get("post_id"),
                external_url=result.get("url"),
                error_message=result.get("error"),
            )

            self.db.add(log)
            self.db.commit()

        except Exception as e:
            logger.error(f"Error logging publish attempt: {e}")

    # =========================================================================
    # Scheduling
    # =========================================================================

    async def schedule_brief(
        self,
        brief_id: str,
        scheduled_datetime: datetime,
        channels: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Schedule a brief for future publishing."""
        brief = self.db.query(ContentBrief).filter(
            ContentBrief.id == brief_id
        ).first()

        if not brief:
            return {"success": False, "error": "Brief not found"}

        # Update brief schedule
        brief.scheduled_date = scheduled_datetime.date()
        brief.scheduled_time = scheduled_datetime.time()
        if channels:
            brief.channels = channels
        brief.status = ContentStatus.SCHEDULED.value

        self.db.commit()

        # Create publish log entries for tracking
        for channel in (channels or brief.channels or []):
            log = ContentPublishLog(
                brief_id=brief_id,
                channel=channel,
                scheduled_at=scheduled_datetime,
                status="scheduled",
            )
            self.db.add(log)

        self.db.commit()

        return {
            "success": True,
            "brief_id": brief_id,
            "scheduled_datetime": scheduled_datetime.isoformat(),
            "channels": channels or brief.channels,
        }

    def get_scheduled_content(
        self,
        organization_id: int = 1,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[ContentPublishLog]:
        """Get all scheduled content within a date range."""
        query = self.db.query(ContentPublishLog).filter(
            ContentPublishLog.status == "scheduled"
        )

        if start_date:
            query = query.filter(ContentPublishLog.scheduled_at >= start_date)
        if end_date:
            query = query.filter(ContentPublishLog.scheduled_at <= end_date)

        return query.order_by(ContentPublishLog.scheduled_at).all()

    def get_pending_publications(self) -> List[ContentPublishLog]:
        """Get content scheduled to publish now or in the past."""
        return self.db.query(ContentPublishLog).filter(
            ContentPublishLog.status == "scheduled",
            ContentPublishLog.scheduled_at <= datetime.now(timezone.utc)
        ).order_by(ContentPublishLog.scheduled_at).all()

    async def process_scheduled_publications(self) -> Dict[str, Any]:
        """Process all pending scheduled publications."""
        pending = self.get_pending_publications()

        if not pending:
            return {"success": True, "processed": 0, "message": "No pending publications"}

        results = []
        for log in pending:
            if log.brief_id:
                result = await self.publish_brief(
                    brief_id=log.brief_id,
                    channels=[log.channel],
                    publish_now=True
                )
                results.append({
                    "log_id": log.id,
                    "brief_id": log.brief_id,
                    "channel": log.channel,
                    "result": result
                })

        return {
            "success": True,
            "processed": len(results),
            "results": results,
        }

    # =========================================================================
    # Engagement Metrics
    # =========================================================================

    async def fetch_engagement_metrics(
        self,
        brief_id: str
    ) -> Dict[str, Any]:
        """Fetch engagement metrics for published content."""
        logs = self.db.query(ContentPublishLog).filter(
            ContentPublishLog.brief_id == brief_id,
            ContentPublishLog.status == "published"
        ).all()

        if not logs:
            return {"success": False, "error": "No published content found"}

        metrics = {}
        for log in logs:
            channel_metrics = await self._fetch_channel_metrics(log)
            if channel_metrics:
                metrics[log.channel] = channel_metrics

                # Update the log
                log.views = channel_metrics.get("views", 0)
                log.likes = channel_metrics.get("likes", 0)
                log.comments = channel_metrics.get("comments", 0)
                log.shares = channel_metrics.get("shares", 0)
                log.clicks = channel_metrics.get("clicks", 0)
                log.metrics_updated_at = datetime.now(timezone.utc)

        self.db.commit()

        return {
            "success": True,
            "brief_id": brief_id,
            "metrics": metrics,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    async def _fetch_channel_metrics(
        self,
        log: ContentPublishLog
    ) -> Optional[Dict[str, int]]:
        """Fetch metrics for a specific channel post."""
        if not log.external_post_id:
            return None

        if log.channel == "facebook":
            return await self.social_service.get_facebook_post_engagement(
                log.external_post_id
            )

        # Add other channel metric fetching as needed
        return None

    def get_publishing_analytics(
        self,
        organization_id: int = 1,
        days: int = 30
    ) -> Dict[str, Any]:
        """Get publishing analytics for the organization."""
        start_date = datetime.now(timezone.utc) - timedelta(days=days)

        logs = self.db.query(ContentPublishLog).filter(
            ContentPublishLog.created_at >= start_date
        ).all()

        # Aggregate stats
        total_published = len([l for l in logs if l.status == "published"])
        total_scheduled = len([l for l in logs if l.status == "scheduled"])
        total_failed = len([l for l in logs if l.status == "failed"])

        by_channel = {}
        total_engagement = {
            "views": 0,
            "likes": 0,
            "comments": 0,
            "shares": 0,
            "clicks": 0,
        }

        for log in logs:
            channel = log.channel
            if channel not in by_channel:
                by_channel[channel] = {"published": 0, "failed": 0, "engagement": 0}

            if log.status == "published":
                by_channel[channel]["published"] += 1
                engagement = (log.likes or 0) + (log.comments or 0) + (log.shares or 0)
                by_channel[channel]["engagement"] += engagement

                total_engagement["views"] += log.views or 0
                total_engagement["likes"] += log.likes or 0
                total_engagement["comments"] += log.comments or 0
                total_engagement["shares"] += log.shares or 0
                total_engagement["clicks"] += log.clicks or 0

            elif log.status == "failed":
                by_channel[channel]["failed"] += 1

        return {
            "period_days": days,
            "total_published": total_published,
            "total_scheduled": total_scheduled,
            "total_failed": total_failed,
            "success_rate": (
                total_published / (total_published + total_failed) * 100
                if (total_published + total_failed) > 0 else 0
            ),
            "by_channel": by_channel,
            "total_engagement": total_engagement,
        }

    # =========================================================================
    # Publish Log Management
    # =========================================================================

    def get_publish_log(self, log_id: str) -> Optional[ContentPublishLog]:
        """Get a publish log by ID."""
        return self.db.query(ContentPublishLog).filter(
            ContentPublishLog.id == log_id
        ).first()

    def list_publish_logs(
        self,
        brief_id: Optional[str] = None,
        channel: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50
    ) -> List[ContentPublishLog]:
        """List publish logs with filters."""
        query = self.db.query(ContentPublishLog)

        if brief_id:
            query = query.filter(ContentPublishLog.brief_id == brief_id)
        if channel:
            query = query.filter(ContentPublishLog.channel == channel)
        if status:
            query = query.filter(ContentPublishLog.status == status)

        return query.order_by(
            ContentPublishLog.created_at.desc()
        ).limit(limit).all()

    async def retry_failed_publication(
        self,
        log_id: str
    ) -> Dict[str, Any]:
        """Retry a failed publication."""
        log = self.get_publish_log(log_id)
        if not log:
            return {"success": False, "error": "Log not found"}

        if log.status != "failed":
            return {"success": False, "error": "Publication is not in failed status"}

        log.retry_count = (log.retry_count or 0) + 1
        self.db.commit()

        return await self.publish_brief(
            brief_id=log.brief_id,
            channels=[log.channel],
            publish_now=True
        )

    def cancel_scheduled_publication(
        self,
        log_id: str
    ) -> bool:
        """Cancel a scheduled publication."""
        log = self.get_publish_log(log_id)
        if not log or log.status != "scheduled":
            return False

        log.status = "cancelled"
        self.db.commit()
        return True
