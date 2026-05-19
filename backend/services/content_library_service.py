"""
Content Library Service

Business logic for browsing, filtering, personalizing, and tracking
pre-built and custom marketing content templates.

Designed to support a Surefire-style library of 1,000+ pieces that loan
officers can browse by pipeline stage, channel, or category and deploy
directly to leads or into campaigns.

Usage:
    from services.content_library_service import ContentLibraryService

    svc = ContentLibraryService(db, organization_id=42)

    # Browse by stage
    items = svc.get_library_items(category="new_lead", content_type="email")

    # AI-suggested content for a lead in application
    recs = svc.get_recommended_content(lead_stage="prospect", loan_stage="APPLICATION")

    # Render a personalized copy of template #7
    rendered = svc.personalize_content(
        template_id=7,
        contact_data={
            "first_name": "Sarah",
            "loan_officer_name": "Mike Johnson",
            "company_name": "CMG Home Loans",
            "rate": "6.750%",
            "loan_amount": "$425,000",
        },
    )

    # Record that user 5 sent template #7 to lead #101
    svc.track_usage(template_id=7, user_id=5, lead_id=101, user_rating=5)
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, or_, func
from sqlalchemy.orm import Session

from database.models.content_library import (
    ContentLibraryItem,
    ContentLibraryUsageLog,
    ContentCategory,
    ContentType,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Stage-to-category mapping
# Used by get_recommended_content() to infer the right content category
# from pipeline position.
# ---------------------------------------------------------------------------

_LEAD_STAGE_TO_CATEGORY: Dict[str, str] = {
    # Lead stages (pre-application)
    "new": ContentCategory.NEW_LEAD,
    "contacted": ContentCategory.NEW_LEAD,
    "prospect": ContentCategory.NEW_LEAD,
    "pre_qual": ContentCategory.NEW_LEAD,
    "pre_approved": ContentCategory.APPLICATION,
    "nurture": ContentCategory.NEW_LEAD,
    "stale": ContentCategory.NEW_LEAD,
    "referral": ContentCategory.REFERRAL,
}

_LOAN_STAGE_TO_CATEGORY: Dict[str, str] = {
    "APPLICATION": ContentCategory.APPLICATION,
    "DISCLOSED": ContentCategory.APPLICATION,
    "PROCESSING": ContentCategory.PROCESSING,
    "SUBMITTED": ContentCategory.PROCESSING,
    "UNDERWRITING": ContentCategory.PROCESSING,
    "UW_RECEIVED": ContentCategory.PROCESSING,
    "CONDITIONAL_APPROVAL": ContentCategory.PROCESSING,
    "APPROVED": ContentCategory.CLOSING,
    "CTC": ContentCategory.CLOSING,
    "CLEAR_TO_CLOSE": ContentCategory.CLOSING,
    "CLOSING": ContentCategory.CLOSING,
    "DOCS": ContentCategory.CLOSING,
    "DOCS_OUT": ContentCategory.CLOSING,
    "FUNDED": ContentCategory.POST_CLOSE,
    # Terminal stages default to post-close nurture
    "CANCELLED": ContentCategory.POST_CLOSE,
    "DENIED": ContentCategory.POST_CLOSE,
    "DEAD": ContentCategory.NEW_LEAD,
    "NURTURE": ContentCategory.NEW_LEAD,
    "WITHDRAWN": ContentCategory.POST_CLOSE,
    "DOES_NOT_QUALIFY": ContentCategory.NEW_LEAD,
}

# Priority order of content types to suggest when no type is specified
_RECOMMENDED_TYPE_ORDER = [
    ContentType.EMAIL,
    ContentType.SMS,
    ContentType.SOCIAL_POST,
    ContentType.VIDEO_SCRIPT,
    ContentType.POSTCARD,
]


# ---------------------------------------------------------------------------
# Merge field token constants
# ---------------------------------------------------------------------------

# All recognized merge tokens — used for validation in personalize_content()
ALL_MERGE_FIELDS = frozenset([
    "{{first_name}}",
    "{{last_name}}",
    "{{full_name}}",
    "{{email}}",
    "{{phone}}",
    "{{loan_officer_name}}",
    "{{loan_officer_email}}",
    "{{loan_officer_phone}}",
    "{{loan_officer_nmls}}",
    "{{company_name}}",
    "{{company_address}}",
    "{{company_phone}}",
    "{{company_website}}",
    "{{company_nmls}}",
    "{{rate}}",
    "{{loan_amount}}",
    "{{loan_type}}",
    "{{property_address}}",
    "{{closing_date}}",
    "{{loan_number}}",
    "{{application_date}}",
    "{{funded_date}}",
    "{{home_value}}",
    "{{equity_amount}}",
    "{{monthly_payment}}",
    "{{current_rate}}",
    "{{new_rate}}",
    "{{monthly_savings}}",
    "{{anniversary_date}}",
    "{{birthday_month}}",
    "{{referral_name}}",
    "{{calendar_link}}",
    "{{portal_link}}",
    "{{unsubscribe_link}}",
    "{{current_year}}",
    "{{current_month}}",
])


class ContentLibraryService:
    """Service layer for the Perennia content library.

    All methods are org-scoped: platform defaults (organization_id=NULL) are
    always merged into result sets so LOs see the full catalog.

    Args:
        db: SQLAlchemy session.
        organization_id: ID of the current tenant. Required for write
            operations; read operations include platform defaults.
    """

    def __init__(self, db: Session, organization_id: Optional[int] = None) -> None:
        self.db = db
        self.organization_id = organization_id

    # =========================================================================
    # READ — BROWSE & FILTER
    # =========================================================================

    def get_library_items(
        self,
        category: Optional[str] = None,
        content_type: Optional[str] = None,
        search: Optional[str] = None,
        tags: Optional[List[str]] = None,
        compliance_approved_only: bool = True,
        include_platform_defaults: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[ContentLibraryItem], int]:
        """Return a filtered, paginated list of content library items.

        Items from the org's own library and (optionally) platform defaults
        are merged into a single result set, ordered by usage_count descending
        so the most popular templates surface first.

        Args:
            category: Filter by ContentCategory value string (e.g. "new_lead").
            content_type: Filter by ContentType value string (e.g. "email").
            search: Full-text search across title, description, and body_text.
            tags: Return only items that have ALL of the specified tags.
            compliance_approved_only: If True, exclude non-approved items.
            include_platform_defaults: If True, merge platform-wide defaults
                into the result set alongside org-specific items.
            limit: Page size (max 500).
            offset: Pagination offset.

        Returns:
            Tuple of (items list, total count before pagination).
        """
        limit = min(limit, 500)

        # Base: org items + platform defaults
        if self.organization_id and include_platform_defaults:
            scope_filter = or_(
                ContentLibraryItem.organization_id == self.organization_id,
                ContentLibraryItem.organization_id.is_(None),
            )
        elif self.organization_id:
            scope_filter = ContentLibraryItem.organization_id == self.organization_id
        else:
            # No org context — return platform defaults only
            scope_filter = ContentLibraryItem.organization_id.is_(None)

        q = self.db.query(ContentLibraryItem).filter(
            scope_filter,
            ContentLibraryItem.is_active == True,
        )

        if compliance_approved_only:
            q = q.filter(ContentLibraryItem.compliance_approved == True)

        if category:
            q = q.filter(ContentLibraryItem.category == category)

        if content_type:
            q = q.filter(ContentLibraryItem.content_type == content_type)

        if search:
            search_term = f"%{search.lower()}%"
            q = q.filter(
                or_(
                    func.lower(ContentLibraryItem.title).like(search_term),
                    func.lower(ContentLibraryItem.description).like(search_term),
                    func.lower(ContentLibraryItem.body_text).like(search_term),
                    func.lower(ContentLibraryItem.subject_line).like(search_term),
                )
            )

        if tags:
            # PostgreSQL JSON array containment — filter to items that have all requested tags
            for tag in tags:
                q = q.filter(
                    func.jsonb_exists(ContentLibraryItem.tags, tag)
                )

        total = q.count()

        items = (
            q.order_by(
                ContentLibraryItem.usage_count.desc(),
                ContentLibraryItem.title.asc(),
            )
            .offset(offset)
            .limit(limit)
            .all()
        )

        return items, total

    def get_item_by_id(self, template_id: int) -> Optional[ContentLibraryItem]:
        """Fetch a single item, respecting org scope.

        Returns the item if it belongs to the current org OR is a platform
        default. Returns None if it exists but belongs to a different org.
        """
        item = self.db.query(ContentLibraryItem).filter(
            ContentLibraryItem.id == template_id,
            ContentLibraryItem.is_active == True,
        ).first()

        if item is None:
            return None

        # Enforce tenant isolation: item must be platform default or own org
        if item.organization_id is not None and item.organization_id != self.organization_id:
            logger.warning(
                "Tenant isolation: org %s attempted to access content item %s owned by org %s",
                self.organization_id, template_id, item.organization_id,
            )
            return None

        return item

    # =========================================================================
    # READ — RECOMMENDATIONS
    # =========================================================================

    def get_recommended_content(
        self,
        lead_stage: Optional[str] = None,
        loan_stage: Optional[str] = None,
        content_type: Optional[str] = None,
        limit: int = 5,
    ) -> List[ContentLibraryItem]:
        """Return AI-suggested content items based on pipeline position.

        Inference logic:
        1. If loan_stage is set, derive the best-fit content category from the
           loan stage mapping (takes precedence over lead_stage).
        2. If only lead_stage is set, derive the category from the lead stage
           mapping.
        3. Fall back to NEW_LEAD if neither stage maps to a known category.

        Items are ranked by usage_count (popularity) then by whether they are
        compliance-approved at the org level vs. platform default.

        Args:
            lead_stage: Current lead stage string (e.g. "prospect").
            loan_stage: Current loan stage string (e.g. "PROCESSING").
            content_type: Optionally restrict to a single channel.
            limit: Number of recommendations to return.

        Returns:
            Ordered list of recommended ContentLibraryItem objects.
        """
        # Determine target category
        category = ContentCategory.NEW_LEAD  # safe default

        if loan_stage:
            normalized_loan = loan_stage.upper().strip()
            category = _LOAN_STAGE_TO_CATEGORY.get(normalized_loan, ContentCategory.NEW_LEAD)
        elif lead_stage:
            normalized_lead = lead_stage.lower().strip()
            category = _LEAD_STAGE_TO_CATEGORY.get(normalized_lead, ContentCategory.NEW_LEAD)

        # Scope filter
        if self.organization_id:
            scope_filter = or_(
                ContentLibraryItem.organization_id == self.organization_id,
                ContentLibraryItem.organization_id.is_(None),
            )
        else:
            scope_filter = ContentLibraryItem.organization_id.is_(None)

        q = self.db.query(ContentLibraryItem).filter(
            scope_filter,
            ContentLibraryItem.is_active == True,
            ContentLibraryItem.compliance_approved == True,
            ContentLibraryItem.category == category,
        )

        if content_type:
            q = q.filter(ContentLibraryItem.content_type == content_type)

        items = (
            q.order_by(ContentLibraryItem.usage_count.desc())
            .limit(limit)
            .all()
        )

        # If the specific category has fewer than `limit` items, backfill with
        # items from adjacent categories so we always return something useful.
        if len(items) < limit:
            exclude_ids = [i.id for i in items]
            backfill_q = self.db.query(ContentLibraryItem).filter(
                scope_filter,
                ContentLibraryItem.is_active == True,
                ContentLibraryItem.compliance_approved == True,
                ContentLibraryItem.id.notin_(exclude_ids),
            )
            if content_type:
                backfill_q = backfill_q.filter(ContentLibraryItem.content_type == content_type)

            backfill = (
                backfill_q
                .order_by(ContentLibraryItem.usage_count.desc())
                .limit(limit - len(items))
                .all()
            )
            items = items + backfill

        return items

    # =========================================================================
    # PERSONALIZATION
    # =========================================================================

    def personalize_content(
        self,
        template_id: int,
        contact_data: Dict[str, Any],
    ) -> Dict[str, str]:
        """Render a personalized copy of a template by substituting merge fields.

        The original template is never modified. A fresh rendered copy is
        returned for each call.

        Merge field syntax: ``{{token_name}}`` (double curly braces, snake_case).
        Unknown tokens that are not supplied in contact_data are left in place
        rather than removed, so a missing value is visible to the sender.

        Args:
            template_id: ID of the ContentLibraryItem to render.
            contact_data: Dict mapping token names (without braces) to values.
                Example: {"first_name": "Sarah", "rate": "6.750%"}

        Returns:
            Dict with keys:
                - ``subject``: Rendered subject line (email only; empty string otherwise).
                - ``body_html``: Rendered HTML body (may be empty string).
                - ``body_text``: Rendered plain-text body (may be empty string).
                - ``title``: Template title (for reference).
                - ``content_type``: The content type of the source template.
                - ``merge_fields_used``: List of tokens that were successfully replaced.
                - ``merge_fields_missing``: List of tokens present in template but
                  not supplied in contact_data.

        Raises:
            ValueError: If the template is not found or is not accessible by
                the current organization.
        """
        item = self.get_item_by_id(template_id)
        if item is None:
            raise ValueError(f"Content library item {template_id} not found or not accessible")

        # Inject built-in auto-values
        auto_values: Dict[str, str] = {
            "current_year": str(datetime.now(timezone.utc).year),
            "current_month": datetime.now(timezone.utc).strftime("%B"),
        }

        # Merge auto_values under contact_data (contact_data takes precedence)
        merged_data = {**auto_values, **{str(k): str(v) for k, v in contact_data.items()}}

        fields_used: List[str] = []
        fields_missing: List[str] = []

        def _replace(text: Optional[str]) -> str:
            if not text:
                return ""
            result = text
            # Find all {{token}} occurrences in this template
            tokens_in_text = set(re.findall(r"\{\{(\w+)\}\}", text))
            for token in tokens_in_text:
                placeholder = f"{{{{{token}}}}}"
                if token in merged_data:
                    result = result.replace(placeholder, merged_data[token])
                    token_display = f"{{{{{token}}}}}"
                    if token_display not in fields_used:
                        fields_used.append(token_display)
                else:
                    token_display = f"{{{{{token}}}}}"
                    if token_display not in fields_missing:
                        fields_missing.append(token_display)
            return result

        rendered_subject = _replace(item.subject_line)
        rendered_html = _replace(item.body_html)
        rendered_text = _replace(item.body_text)

        return {
            "subject": rendered_subject,
            "body_html": rendered_html,
            "body_text": rendered_text,
            "title": item.title,
            "content_type": item.content_type,
            "merge_fields_used": fields_used,
            "merge_fields_missing": fields_missing,
        }

    # =========================================================================
    # USAGE TRACKING
    # =========================================================================

    def track_usage(
        self,
        template_id: int,
        user_id: int,
        lead_id: Optional[int] = None,
        loan_id: Optional[int] = None,
        channel: Optional[str] = None,
        user_rating: Optional[int] = None,
    ) -> ContentLibraryUsageLog:
        """Record a send/deployment event and increment the template's usage counter.

        If user_rating is provided (1–5), the template's rolling average rating
        and rating_count are updated atomically.

        Args:
            template_id: The ContentLibraryItem that was used.
            user_id: The user who sent/deployed it.
            lead_id: Target lead, if applicable.
            loan_id: Target loan, if applicable.
            channel: Override channel (e.g. "email", "sms").
            user_rating: Optional star rating 1–5 from the user.

        Returns:
            The created ContentLibraryUsageLog record.

        Raises:
            ValueError: If template_id is not accessible.
        """
        if self.organization_id is None:
            raise ValueError("organization_id is required for track_usage()")

        item = self.get_item_by_id(template_id)
        if item is None:
            raise ValueError(f"Content library item {template_id} not found or not accessible")

        # Validate rating range
        if user_rating is not None:
            user_rating = max(1, min(5, int(user_rating)))

        # Create the usage log record
        log = ContentLibraryUsageLog(
            item_id=template_id,
            organization_id=self.organization_id,
            user_id=user_id,
            lead_id=lead_id,
            loan_id=loan_id,
            channel=channel or item.content_type,
            user_rating=user_rating,
            sent_at=datetime.now(timezone.utc),
        )
        self.db.add(log)

        # Increment usage counter on the item itself
        item.usage_count = (item.usage_count or 0) + 1

        # Update rolling average rating
        if user_rating is not None:
            old_count = item.rating_count or 0
            old_rating = float(item.rating or 0)
            new_count = old_count + 1
            # Incremental mean: new_avg = (old_avg * old_count + new_rating) / new_count
            new_rating = (old_rating * old_count + user_rating) / new_count
            item.rating = round(new_rating, 2)
            item.rating_count = new_count

        item.updated_at = datetime.now(timezone.utc)

        try:
            self.db.commit()
            self.db.refresh(log)
        except Exception as _exc:  # noqa: BLE001
            logger.exception("unhandled exception")
            self.db.rollback()
            logger.exception("Failed to track content usage for item %s", template_id)
            raise

        return log

    def update_engagement_outcome(
        self,
        log_id: int,
        was_opened: Optional[bool] = None,
        was_clicked: Optional[bool] = None,
        was_replied: Optional[bool] = None,
        led_to_conversion: Optional[bool] = None,
    ) -> Optional[ContentLibraryUsageLog]:
        """Update engagement outcomes on an existing usage log record.

        Called asynchronously by email/SMS webhook handlers when delivery
        events arrive (open, click, reply, conversion).

        Args:
            log_id: ContentLibraryUsageLog.id to update.
            was_opened: Mark the message as opened.
            was_clicked: Mark that a link was clicked.
            was_replied: Mark that the recipient replied.
            led_to_conversion: Mark that the contact converted to an application.

        Returns:
            Updated log record, or None if not found.
        """
        log = self.db.query(ContentLibraryUsageLog).filter(
            ContentLibraryUsageLog.id == log_id,
            ContentLibraryUsageLog.organization_id == self.organization_id,
        ).first()

        if log is None:
            logger.warning("ContentLibraryUsageLog %s not found for org %s", log_id, self.organization_id)
            return None

        if was_opened is not None:
            log.was_opened = was_opened
        if was_clicked is not None:
            log.was_clicked = was_clicked
        if was_replied is not None:
            log.was_replied = was_replied
        if led_to_conversion is not None:
            log.led_to_conversion = led_to_conversion

        try:
            self.db.commit()
            self.db.refresh(log)
        except Exception as _exc:  # noqa: BLE001
            logger.exception("unhandled exception")
            self.db.rollback()
            logger.exception("Failed to update engagement outcome for log %s", log_id)
            raise

        return log

    # =========================================================================
    # ADMIN — COPY / FORK PLATFORM DEFAULT
    # =========================================================================

    def fork_platform_default(
        self,
        template_id: int,
        created_by_id: int,
        title_override: Optional[str] = None,
    ) -> ContentLibraryItem:
        """Create an org-owned copy of a platform default for customization.

        The forked copy starts as non-compliance-approved so the org admin can
        review and approve it before it goes live.

        Args:
            template_id: ID of the platform default ContentLibraryItem.
            created_by_id: User ID of who is forking.
            title_override: Optional new title for the fork.

        Returns:
            The newly created org-owned ContentLibraryItem.

        Raises:
            ValueError: If template is not a platform default or not accessible.
        """
        if self.organization_id is None:
            raise ValueError("organization_id required to fork a template")

        source = self.db.query(ContentLibraryItem).filter(
            ContentLibraryItem.id == template_id,
            ContentLibraryItem.is_active == True,
        ).first()

        if source is None:
            raise ValueError(f"Template {template_id} not found")
        if source.organization_id is not None and not source.is_platform_default:
            raise ValueError(f"Template {template_id} is not a platform default and cannot be forked")

        fork = ContentLibraryItem(
            organization_id=self.organization_id,
            source_template_id=source.id,
            created_by_id=created_by_id,
            updated_by_id=created_by_id,
            title=title_override or f"{source.title} (Custom)",
            description=source.description,
            content_type=source.content_type,
            category=source.category,
            body_html=source.body_html,
            body_text=source.body_text,
            subject_line=source.subject_line,
            thumbnail_url=source.thumbnail_url,
            tags=list(source.tags or []),
            merge_fields=list(source.merge_fields or []),
            is_platform_default=False,
            is_customizable=True,
            compliance_approved=False,
            usage_count=0,
            rating=None,
            rating_count=0,
            is_active=True,
        )
        self.db.add(fork)

        try:
            self.db.commit()
            self.db.refresh(fork)
        except Exception as _exc:  # noqa: BLE001
            logger.exception("unhandled exception")
            self.db.rollback()
            logger.exception("Failed to fork template %s", template_id)
            raise

        return fork

    # =========================================================================
    # ADMIN — COMPLIANCE APPROVAL
    # =========================================================================

    def approve_for_compliance(
        self,
        template_id: int,
        approver_user_id: int,
        notes: Optional[str] = None,
    ) -> ContentLibraryItem:
        """Mark a content item as compliance-approved.

        Only applies to org-owned items (platform defaults ship pre-approved).

        Args:
            template_id: ID to approve.
            approver_user_id: User ID of the compliance reviewer.
            notes: Optional reviewer notes.

        Returns:
            Updated ContentLibraryItem.

        Raises:
            ValueError: If the item is not found or belongs to a different org.
        """
        item = self.get_item_by_id(template_id)
        if item is None:
            raise ValueError(f"Content library item {template_id} not found or not accessible")

        now = datetime.now(timezone.utc)
        item.compliance_approved = True
        item.compliance_approved_at = now
        item.compliance_approved_by_id = approver_user_id
        item.compliance_notes = notes
        item.updated_at = now

        try:
            self.db.commit()
            self.db.refresh(item)
        except Exception as _exc:  # noqa: BLE001
            logger.exception("unhandled exception")
            self.db.rollback()
            logger.exception("Failed to approve content item %s", template_id)
            raise

        return item

    # =========================================================================
    # ANALYTICS HELPERS
    # =========================================================================

    def get_top_items(
        self,
        content_type: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Return the most-used items for the current org (+ platform defaults).

        Useful for an analytics dashboard showing "most popular templates".

        Returns:
            List of dicts with keys: id, title, content_type, category,
            usage_count, rating, rating_count.
        """
        if self.organization_id:
            scope_filter = or_(
                ContentLibraryItem.organization_id == self.organization_id,
                ContentLibraryItem.organization_id.is_(None),
            )
        else:
            scope_filter = ContentLibraryItem.organization_id.is_(None)

        q = self.db.query(ContentLibraryItem).filter(
            scope_filter,
            ContentLibraryItem.is_active == True,
            ContentLibraryItem.usage_count > 0,
        )

        if content_type:
            q = q.filter(ContentLibraryItem.content_type == content_type)
        if category:
            q = q.filter(ContentLibraryItem.category == category)

        items = (
            q.order_by(ContentLibraryItem.usage_count.desc())
            .limit(limit)
            .all()
        )

        return [
            {
                "id": item.id,
                "title": item.title,
                "content_type": item.content_type,
                "category": item.category,
                "usage_count": item.usage_count,
                "rating": float(item.rating) if item.rating else None,
                "rating_count": item.rating_count,
            }
            for item in items
        ]
