"""
Content Calendar Service

Manages 30-day content calendars and brief generation:
- Create and manage content calendars
- Auto-generate content briefs from calendar settings
- Schedule content across multiple channels
- Track calendar progress and status
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, date, timedelta, time
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from models.content_marketing import (
    ContentCalendar, ContentBrief, ContentBrandVoice,
    ContentMarketingTemplate as ContentTemplate, CalendarStatus, ContentStatus,
    ContentArchetype, ContentChannel, PersonalizationType
)

logger = logging.getLogger(__name__)


class ContentCalendarService:
    """
    Service for managing content calendars and briefs.

    Handles calendar creation, brief generation, and scheduling
    for multi-channel content marketing campaigns.
    """

    # Default content mix for mortgage industry
    DEFAULT_CONTENT_MIX = {
        "blog": {
            "weekly_count": 3,
            "archetypes": ["informative", "how_to", "data_driven"],
            "topics": [
                "mortgage rates update",
                "home buying tips",
                "refinance opportunities",
                "first-time buyer guide",
                "market analysis",
            ],
        },
        "linkedin": {
            "weekly_count": 5,
            "archetypes": ["informative", "story", "news"],
            "topics": [
                "industry insights",
                "client success stories",
                "market updates",
                "professional tips",
            ],
        },
        "facebook": {
            "weekly_count": 4,
            "archetypes": ["story", "celebration", "how_to"],
            "topics": [
                "homeowner tips",
                "closing celebrations",
                "community events",
                "home maintenance",
            ],
        },
        "instagram": {
            "weekly_count": 3,
            "archetypes": ["celebration", "story", "informative"],
            "topics": [
                "closing day photos",
                "home tours",
                "behind the scenes",
                "quick tips",
            ],
        },
        "email": {
            "weekly_count": 2,
            "archetypes": ["informative", "how_to"],
            "topics": [
                "rate alerts",
                "loan milestone updates",
                "market insights",
            ],
        },
    }

    # Mortgage industry seasonal themes
    SEASONAL_THEMES = {
        1: "New Year home goals, fresh start buying",
        2: "Valentine's Day dream home, spring market prep",
        3: "Spring buying season kickoff, tax season tips",
        4: "Peak buying season, first-time buyers",
        5: "Memorial Day weekend open houses, summer prep",
        6: "Summer moving tips, vacation home buying",
        7: "Mid-year market review, summer closings",
        8: "Back-to-school neighborhood guides, fall prep",
        9: "Fall market opportunities, refinance season",
        10: "Year-end tax planning, rate lock strategies",
        11: "Holiday homeowner tips, gratitude",
        12: "Year in review, new year planning",
    }

    def __init__(self, db: Session):
        """Initialize with database session."""
        self.db = db

    # =========================================================================
    # Calendar CRUD
    # =========================================================================

    def create_calendar(
        self,
        name: str,
        start_date: date,
        end_date: Optional[date] = None,
        user_id: Optional[int] = None,
        organization_id: int = 1,
        brand_voice_id: Optional[str] = None,
        channels: List[str] = None,
        posts_per_week: int = 5,
        auto_generate_briefs: bool = True,
        primary_theme: Optional[str] = None,
        target_keywords: List[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a new content calendar.

        Args:
            name: Calendar name
            start_date: Calendar start date
            end_date: Calendar end date (default: start + 30 days)
            user_id: Owner user ID
            organization_id: Organization ID
            brand_voice_id: Associated brand voice profile
            channels: List of channels to include
            posts_per_week: Total posts per week
            auto_generate_briefs: Auto-generate briefs on creation
            primary_theme: Primary theme for the calendar
            target_keywords: Target SEO keywords

        Returns:
            Created calendar data
        """
        try:
            # Default to 30-day calendar
            if not end_date:
                end_date = start_date + timedelta(days=30)

            # Default channels
            if not channels:
                channels = ["blog", "linkedin", "facebook"]

            # Get seasonal theme if not provided
            if not primary_theme:
                primary_theme = self.SEASONAL_THEMES.get(
                    start_date.month,
                    "General mortgage content"
                )

            calendar = ContentCalendar(
                user_id=user_id,
                organization_id=organization_id,
                name=name,
                description=f"Content calendar: {primary_theme}",
                start_date=start_date,
                end_date=end_date,
                status=CalendarStatus.DRAFT.value,
                posts_per_week=posts_per_week,
                blog_posts_per_week=self._calculate_channel_posts(channels, "blog"),
                social_posts_per_day=1,
                channels=channels,
                brand_voice_id=brand_voice_id,
                auto_generate_briefs=auto_generate_briefs,
                auto_generate_content=False,
                auto_publish=False,
                primary_theme=primary_theme,
                target_keywords=target_keywords or [],
                total_briefs=0,
                published_count=0,
            )

            self.db.add(calendar)
            self.db.commit()
            self.db.refresh(calendar)

            # Auto-generate briefs if requested
            briefs_created = 0
            if auto_generate_briefs:
                briefs_created = self.generate_calendar_briefs(calendar.id)

            return {
                "success": True,
                "calendar_id": calendar.id,
                "name": calendar.name,
                "start_date": calendar.start_date.isoformat(),
                "end_date": calendar.end_date.isoformat(),
                "channels": calendar.channels,
                "briefs_created": briefs_created,
            }

        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to create calendar: {e}")
            return {"success": False, "error": "Internal server error"}

    def _calculate_channel_posts(self, channels: List[str], channel: str) -> int:
        """Calculate posts per week for a specific channel."""
        if channel not in channels:
            return 0
        mix = self.DEFAULT_CONTENT_MIX.get(channel, {})
        return mix.get("weekly_count", 0)

    def get_calendar(self, calendar_id: str) -> Optional[ContentCalendar]:
        """Get a calendar by ID."""
        return self.db.query(ContentCalendar).filter(
            ContentCalendar.id == calendar_id
        ).first()

    def list_calendars(
        self,
        organization_id: int = 1,
        status: Optional[str] = None,
        include_past: bool = False,
    ) -> List[ContentCalendar]:
        """List calendars for an organization."""
        query = self.db.query(ContentCalendar).filter(
            ContentCalendar.organization_id == organization_id
        )

        if status:
            query = query.filter(ContentCalendar.status == status)

        if not include_past:
            query = query.filter(ContentCalendar.end_date >= date.today())

        return query.order_by(ContentCalendar.start_date.desc()).all()

    def update_calendar(
        self,
        calendar_id: str,
        updates: Dict[str, Any]
    ) -> Optional[ContentCalendar]:
        """Update a calendar."""
        calendar = self.get_calendar(calendar_id)
        if not calendar:
            return None

        allowed_fields = [
            "name", "description", "status", "posts_per_week",
            "blog_posts_per_week", "channels", "brand_voice_id",
            "auto_generate_briefs", "auto_generate_content", "auto_publish",
            "primary_theme", "target_keywords"
        ]

        for field, value in updates.items():
            if field in allowed_fields:
                setattr(calendar, field, value)

        self.db.commit()
        self.db.refresh(calendar)
        return calendar

    def activate_calendar(self, calendar_id: str) -> bool:
        """Activate a calendar (start scheduling)."""
        calendar = self.get_calendar(calendar_id)
        if not calendar:
            return False

        calendar.status = CalendarStatus.ACTIVE.value
        self.db.commit()
        return True

    def pause_calendar(self, calendar_id: str) -> bool:
        """Pause a calendar."""
        calendar = self.get_calendar(calendar_id)
        if not calendar:
            return False

        calendar.status = CalendarStatus.PAUSED.value
        self.db.commit()
        return True

    def delete_calendar(self, calendar_id: str, delete_briefs: bool = False) -> bool:
        """Delete a calendar."""
        calendar = self.get_calendar(calendar_id)
        if not calendar:
            return False

        if delete_briefs:
            # Delete associated briefs
            self.db.query(ContentBrief).filter(
                ContentBrief.calendar_id == calendar_id
            ).delete()

        self.db.delete(calendar)
        self.db.commit()
        return True

    # =========================================================================
    # Brief Generation
    # =========================================================================

    def generate_calendar_briefs(
        self,
        calendar_id: str,
        regenerate: bool = False
    ) -> int:
        """
        Generate content briefs for all days in a calendar.

        Args:
            calendar_id: Calendar ID
            regenerate: If True, replace existing briefs

        Returns:
            Number of briefs created
        """
        calendar = self.get_calendar(calendar_id)
        if not calendar:
            return 0

        if regenerate:
            # Delete existing briefs
            self.db.query(ContentBrief).filter(
                ContentBrief.calendar_id == calendar_id
            ).delete()
            self.db.commit()

        # Calculate days in calendar
        total_days = (calendar.end_date - calendar.start_date).days + 1
        total_weeks = total_days / 7

        briefs_created = 0
        current_date = calendar.start_date

        # Generate briefs day by day
        while current_date <= calendar.end_date:
            day_of_week = current_date.weekday()  # 0=Monday, 6=Sunday

            # Generate briefs for each channel
            for channel in calendar.channels:
                channel_mix = self.DEFAULT_CONTENT_MIX.get(channel, {})
                weekly_count = channel_mix.get("weekly_count", 0)

                # Determine if we should post on this day
                should_post = self._should_post_on_day(
                    channel, day_of_week, weekly_count
                )

                if should_post:
                    brief = self._create_brief_for_day(
                        calendar=calendar,
                        scheduled_date=current_date,
                        channel=channel,
                    )
                    if brief:
                        briefs_created += 1

            current_date += timedelta(days=1)

        # Update calendar stats
        calendar.total_briefs = briefs_created
        self.db.commit()

        return briefs_created

    def _should_post_on_day(
        self,
        channel: str,
        day_of_week: int,
        weekly_count: int
    ) -> bool:
        """Determine if we should post on this day of the week."""
        # Skip weekends for most channels
        if day_of_week >= 5:  # Saturday, Sunday
            return channel in ["facebook", "instagram"]

        # Distribute posts across weekdays
        posting_days = {
            5: [0, 1, 2, 3, 4],  # Post every weekday
            4: [0, 1, 2, 4],     # Skip Wednesday
            3: [0, 2, 4],        # Mon, Wed, Fri
            2: [1, 3],           # Tue, Thu
            1: [2],              # Wednesday only
        }

        days = posting_days.get(weekly_count, [])
        return day_of_week in days

    def _create_brief_for_day(
        self,
        calendar: ContentCalendar,
        scheduled_date: date,
        channel: str,
    ) -> Optional[ContentBrief]:
        """Create a content brief for a specific day and channel."""
        try:
            channel_mix = self.DEFAULT_CONTENT_MIX.get(channel, {})
            archetypes = channel_mix.get("archetypes", ["informative"])
            topics = channel_mix.get("topics", ["mortgage tips"])

            # Rotate through archetypes and topics
            day_index = (scheduled_date - calendar.start_date).days
            archetype = archetypes[day_index % len(archetypes)]
            topic_base = topics[day_index % len(topics)]

            # Build topic with theme context
            topic = f"{topic_base} - {calendar.primary_theme}"

            # Default time based on channel
            scheduled_time = self._get_default_post_time(channel)

            # Get a relevant keyword from calendar
            keyword = None
            if calendar.target_keywords:
                keyword = calendar.target_keywords[
                    day_index % len(calendar.target_keywords)
                ]

            brief = ContentBrief(
                calendar_id=calendar.id,
                user_id=calendar.user_id,
                organization_id=calendar.organization_id,
                scheduled_date=scheduled_date,
                scheduled_time=scheduled_time,
                channels=[channel],
                topic=topic,
                archetype=archetype,
                primary_keyword=keyword,
                secondary_keywords=[],
                target_word_count=self._get_word_count_for_channel(channel),
                target_audience=calendar.brand_voice.target_audience if calendar.brand_voice else None,
                key_points=[],
                call_to_action=self._get_default_cta(channel),
                personalization_type=PersonalizationType.GENERAL.value,
                status=ContentStatus.PLANNED.value,
            )

            self.db.add(brief)
            self.db.commit()
            self.db.refresh(brief)

            return brief

        except Exception as e:
            logger.error(f"Failed to create brief: {e}")
            self.db.rollback()
            return None

    def _get_default_post_time(self, channel: str) -> time:
        """Get default posting time for a channel."""
        default_times = {
            "blog": time(9, 0),
            "linkedin": time(8, 30),
            "facebook": time(12, 0),
            "instagram": time(17, 0),
            "twitter": time(10, 0),
            "email": time(10, 0),
        }
        return default_times.get(channel, time(10, 0))

    def _get_word_count_for_channel(self, channel: str) -> int:
        """Get target word count for a channel."""
        word_counts = {
            "blog": 800,
            "linkedin": 300,
            "facebook": 150,
            "instagram": 150,
            "twitter": 50,
            "email": 500,
        }
        return word_counts.get(channel, 300)

    def _get_default_cta(self, channel: str) -> str:
        """Get default call-to-action for a channel."""
        ctas = {
            "blog": "Contact us today to learn more about your mortgage options.",
            "linkedin": "Connect with me to discuss your home financing needs.",
            "facebook": "Drop a comment or send us a message!",
            "instagram": "Save this post for later!",
            "twitter": "Retweet if you found this helpful!",
            "email": "Reply to this email or call us at [phone].",
        }
        return ctas.get(channel, "Contact us to learn more.")

    # =========================================================================
    # Brief Management
    # =========================================================================

    def get_brief(self, brief_id: str) -> Optional[ContentBrief]:
        """Get a brief by ID."""
        return self.db.query(ContentBrief).filter(
            ContentBrief.id == brief_id
        ).first()

    def list_briefs(
        self,
        calendar_id: Optional[str] = None,
        organization_id: int = 1,
        status: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        channel: Optional[str] = None,
    ) -> List[ContentBrief]:
        """List briefs with filters."""
        query = self.db.query(ContentBrief).filter(
            ContentBrief.organization_id == organization_id
        )

        if calendar_id:
            query = query.filter(ContentBrief.calendar_id == calendar_id)

        if status:
            query = query.filter(ContentBrief.status == status)

        if start_date:
            query = query.filter(ContentBrief.scheduled_date >= start_date)

        if end_date:
            query = query.filter(ContentBrief.scheduled_date <= end_date)

        if channel:
            # Filter briefs that include this channel
            query = query.filter(
                ContentBrief.channels.contains([channel])
            )

        return query.order_by(ContentBrief.scheduled_date).all()

    def get_briefs_for_date(
        self,
        target_date: date,
        organization_id: int = 1
    ) -> List[ContentBrief]:
        """Get all briefs scheduled for a specific date."""
        return self.db.query(ContentBrief).filter(
            ContentBrief.organization_id == organization_id,
            ContentBrief.scheduled_date == target_date
        ).order_by(ContentBrief.scheduled_time).all()

    def get_upcoming_briefs(
        self,
        organization_id: int = 1,
        days_ahead: int = 7,
        status: Optional[str] = None
    ) -> List[ContentBrief]:
        """Get upcoming briefs within specified days."""
        end_date = date.today() + timedelta(days=days_ahead)

        query = self.db.query(ContentBrief).filter(
            ContentBrief.organization_id == organization_id,
            ContentBrief.scheduled_date >= date.today(),
            ContentBrief.scheduled_date <= end_date
        )

        if status:
            query = query.filter(ContentBrief.status == status)

        return query.order_by(
            ContentBrief.scheduled_date,
            ContentBrief.scheduled_time
        ).all()

    def update_brief(
        self,
        brief_id: str,
        updates: Dict[str, Any]
    ) -> Optional[ContentBrief]:
        """Update a brief."""
        brief = self.get_brief(brief_id)
        if not brief:
            return None

        allowed_fields = [
            "scheduled_date", "scheduled_time", "channels", "title", "topic",
            "archetype", "primary_keyword", "secondary_keywords",
            "target_word_count", "target_audience", "key_points",
            "call_to_action", "personalization_type", "personalization_segment",
            "personalization_tokens", "template_id", "status", "assigned_to",
            "due_date", "generated_title", "generated_content"
        ]

        for field, value in updates.items():
            if field in allowed_fields:
                setattr(brief, field, value)

        self.db.commit()
        self.db.refresh(brief)
        return brief

    def update_brief_status(
        self,
        brief_id: str,
        status: str
    ) -> Optional[ContentBrief]:
        """Update brief status."""
        return self.update_brief(brief_id, {"status": status})

    def reschedule_brief(
        self,
        brief_id: str,
        new_date: date,
        new_time: Optional[time] = None
    ) -> Optional[ContentBrief]:
        """Reschedule a brief to a new date/time."""
        updates = {"scheduled_date": new_date}
        if new_time:
            updates["scheduled_time"] = new_time
        return self.update_brief(brief_id, updates)

    def delete_brief(self, brief_id: str) -> bool:
        """Delete a brief."""
        brief = self.get_brief(brief_id)
        if not brief:
            return False

        calendar_id = brief.calendar_id
        self.db.delete(brief)
        self.db.commit()

        # Update calendar stats
        if calendar_id:
            calendar = self.get_calendar(calendar_id)
            if calendar:
                calendar.total_briefs = self.db.query(ContentBrief).filter(
                    ContentBrief.calendar_id == calendar_id
                ).count()
                self.db.commit()

        return True

    # =========================================================================
    # Calendar Analytics
    # =========================================================================

    def get_calendar_stats(self, calendar_id: str) -> Dict[str, Any]:
        """Get statistics for a calendar."""
        calendar = self.get_calendar(calendar_id)
        if not calendar:
            return {}

        briefs = self.list_briefs(calendar_id=calendar_id)

        status_counts = {}
        channel_counts = {}

        for brief in briefs:
            # Count by status
            status = brief.status or "unknown"
            status_counts[status] = status_counts.get(status, 0) + 1

            # Count by channel
            for channel in (brief.channels or []):
                channel_counts[channel] = channel_counts.get(channel, 0) + 1

        return {
            "calendar_id": calendar_id,
            "calendar_name": calendar.name,
            "start_date": calendar.start_date.isoformat(),
            "end_date": calendar.end_date.isoformat(),
            "status": calendar.status,
            "total_briefs": len(briefs),
            "status_breakdown": status_counts,
            "channel_breakdown": channel_counts,
            "published_count": status_counts.get(ContentStatus.PUBLISHED.value, 0),
            "completion_rate": (
                status_counts.get(ContentStatus.PUBLISHED.value, 0) / len(briefs) * 100
                if briefs else 0
            ),
        }

    def get_weekly_view(
        self,
        calendar_id: str,
        week_start: Optional[date] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Get calendar view organized by week."""
        if not week_start:
            week_start = date.today() - timedelta(days=date.today().weekday())

        week_end = week_start + timedelta(days=6)

        briefs = self.list_briefs(
            calendar_id=calendar_id,
            start_date=week_start,
            end_date=week_end
        )

        # Organize by day
        week_view = {
            "Monday": [],
            "Tuesday": [],
            "Wednesday": [],
            "Thursday": [],
            "Friday": [],
            "Saturday": [],
            "Sunday": [],
        }

        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

        for brief in briefs:
            day_name = day_names[brief.scheduled_date.weekday()]
            week_view[day_name].append({
                "id": brief.id,
                "title": brief.title or brief.topic,
                "channels": brief.channels,
                "status": brief.status,
                "time": brief.scheduled_time.strftime("%H:%M") if brief.scheduled_time else None,
                "archetype": brief.archetype,
            })

        return {
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
            "days": week_view,
        }

    def get_monthly_view(
        self,
        calendar_id: str,
        year: int,
        month: int
    ) -> Dict[str, Any]:
        """Get calendar view for a month."""
        from calendar import monthrange

        _, last_day = monthrange(year, month)
        month_start = date(year, month, 1)
        month_end = date(year, month, last_day)

        briefs = self.list_briefs(
            calendar_id=calendar_id,
            start_date=month_start,
            end_date=month_end
        )

        # Organize by date
        days = {}
        for day in range(1, last_day + 1):
            day_date = date(year, month, day)
            days[day_date.isoformat()] = []

        for brief in briefs:
            date_key = brief.scheduled_date.isoformat()
            if date_key in days:
                days[date_key].append({
                    "id": brief.id,
                    "title": brief.title or brief.topic[:50],
                    "channels": brief.channels,
                    "status": brief.status,
                })

        return {
            "year": year,
            "month": month,
            "month_start": month_start.isoformat(),
            "month_end": month_end.isoformat(),
            "days": days,
            "total_briefs": len(briefs),
        }
