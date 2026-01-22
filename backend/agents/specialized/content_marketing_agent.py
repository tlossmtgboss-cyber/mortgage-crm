"""
Content Marketing Agent

Specialized agent for managing content marketing automation and carousel creation.
Combines the Vocable.ai-style content marketing system with the carousel builder.

Capabilities:
- Content calendar management (30-day planning, AI briefs)
- Brand voice analysis and profile management
- Multi-channel publishing (blog, email, LinkedIn, Facebook, Instagram)
- SEO keyword tracking and optimization
- AI-powered carousel generation for social media
- CRM data personalization with tokens

16 Tools:
1. create_content_calendar - Create a content calendar with auto-generated briefs
2. get_content_calendar - Get calendar details with briefs
3. list_content_calendars - List all calendars
4. generate_content_briefs - Generate AI content briefs
5. analyze_brand_voice - Analyze website/content for brand voice
6. get_brand_voice - Get brand voice profile
7. publish_content - Publish or schedule content
8. get_publishing_analytics - Get publishing performance metrics
9. track_keyword - Track a keyword for SEO
10. get_keyword_suggestions - Get AI keyword suggestions
11. get_keyword_opportunities - Find keyword ranking opportunities
12. create_carousel_project - Create a carousel project
13. generate_carousel_content - Generate AI carousel slides
14. get_carousel_templates - Get available templates
15. preview_personalization - Preview content with CRM tokens
16. get_personalization_tokens - Get available CRM tokens
"""

from typing import Any, Dict, List
import logging
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

from .base import (
    SpecializedAgent,
    AgentTool,
    AgentContext,
    ToolCategory,
    RiskLevel,
    ToolResult,
    AgentRegistry
)

from ..tools.content_marketing import (
    CONTENT_MARKETING_TOOLS,
    # Calendar tools
    create_content_calendar,
    get_content_calendar,
    list_content_calendars,
    generate_content_briefs,
    # Brand voice tools
    analyze_brand_voice,
    get_brand_voice,
    # Publishing tools
    publish_content,
    get_publishing_analytics,
    # SEO tools
    track_keyword,
    get_keyword_suggestions,
    get_keyword_opportunities,
    # Carousel tools
    create_carousel_project,
    generate_carousel_content,
    get_carousel_templates,
    # Personalization tools
    preview_personalization,
    get_personalization_tokens,
    # Input schemas
    CreateCalendarInput,
    GetCalendarInput,
    ListCalendarsInput,
    GenerateBriefsInput,
    AnalyzeBrandVoiceInput,
    GetBrandVoiceInput,
    PublishContentInput,
    GetPublishingAnalyticsInput,
    TrackKeywordInput,
    GetKeywordSuggestionsInput,
    GetKeywordOpportunitiesInput,
    CreateCarouselInput,
    GenerateCarouselContentInput,
    GetCarouselTemplatesInput,
    PreviewPersonalizationInput,
    GetPersonalizationTokensInput,
)


def _get_category(cat_str: str) -> ToolCategory:
    """Convert string category to ToolCategory enum."""
    mapping = {
        "query": ToolCategory.QUERY,
        "action": ToolCategory.ACTION,
        "analysis": ToolCategory.ANALYSIS,
        "communication": ToolCategory.COMMUNICATION,
        "workflow": ToolCategory.WORKFLOW,
    }
    return mapping.get(cat_str, ToolCategory.ACTION)


def _get_risk_level(risk_str: str) -> RiskLevel:
    """Convert string risk level to RiskLevel enum."""
    mapping = {
        "low": RiskLevel.LOW,
        "medium": RiskLevel.MEDIUM,
        "high": RiskLevel.HIGH,
        "critical": RiskLevel.CRITICAL,
    }
    return mapping.get(risk_str, RiskLevel.LOW)


@AgentRegistry.register
class ContentMarketingAgent(SpecializedAgent):
    """
    Specialized agent for content marketing automation and carousel creation.

    Manages:
    - Content calendars and AI-generated briefs
    - Brand voice profiles for consistent messaging
    - Multi-channel publishing to social media and email
    - SEO keyword tracking and optimization
    - AI-powered carousel generation for social media
    - CRM data personalization (leads, loans, MUM clients)
    """

    @property
    def name(self) -> str:
        return "ContentMarketingAgent"

    @property
    def description(self) -> str:
        return (
            "Manages content marketing automation including calendars, brand voice, "
            "multi-channel publishing, SEO keywords, and AI carousel generation for social media"
        )

    def _register_tools(self):
        """Register all content marketing tools."""

        # Calendar Tools
        self.register_tool(AgentTool(
            name="create_content_calendar",
            description=(
                "Create a new content marketing calendar with AI-generated briefs. "
                "Supports multi-channel planning for blog, email, LinkedIn, Facebook, Instagram. "
                "Automatically generates content briefs based on mortgage industry best practices."
            ),
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.LOW,
            handler=create_content_calendar,
            input_schema=CreateCalendarInput,
        ))

        self.register_tool(AgentTool(
            name="get_content_calendar",
            description=(
                "Get content calendar details including all scheduled briefs and their status. "
                "Shows upcoming content, publishing schedule, and completion progress."
            ),
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=get_content_calendar,
            input_schema=GetCalendarInput,
        ))

        self.register_tool(AgentTool(
            name="list_content_calendars",
            description=(
                "List all content calendars. Filter by status: draft, active, paused, completed. "
                "Returns calendar summaries with brief counts and date ranges."
            ),
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=list_content_calendars,
            input_schema=ListCalendarsInput,
        ))

        self.register_tool(AgentTool(
            name="generate_content_briefs",
            description=(
                "Generate AI content briefs for a calendar. Creates topic suggestions, "
                "outlines, and CTA recommendations. Uses brand voice profile for consistency."
            ),
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.LOW,
            handler=generate_content_briefs,
            input_schema=GenerateBriefsInput,
        ))

        # Brand Voice Tools
        self.register_tool(AgentTool(
            name="analyze_brand_voice",
            description=(
                "Analyze brand voice from a website URL or sample content. "
                "Creates a voice profile with tone, vocabulary, and style guidelines "
                "for consistent content generation across all channels."
            ),
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=analyze_brand_voice,
            input_schema=AnalyzeBrandVoiceInput,
        ))

        self.register_tool(AgentTool(
            name="get_brand_voice",
            description=(
                "Get the brand voice profile for content generation. "
                "Includes tone description, key vocabulary, phrases to use/avoid, "
                "and style guidelines for each channel."
            ),
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=get_brand_voice,
            input_schema=GetBrandVoiceInput,
        ))

        # Publishing Tools
        self.register_tool(AgentTool(
            name="publish_content",
            description=(
                "Publish or schedule content to a channel (blog, email, linkedin, facebook, instagram). "
                "Supports immediate publishing or future scheduling. "
                "Uses connected social accounts for posting."
            ),
            category=ToolCategory.COMMUNICATION,
            risk_level=RiskLevel.MEDIUM,
            handler=publish_content,
            input_schema=PublishContentInput,
            requires_confirmation=True,
        ))

        self.register_tool(AgentTool(
            name="get_publishing_analytics",
            description=(
                "Get publishing analytics including engagement metrics, "
                "best performing content, and channel performance comparison. "
                "Helps identify what content resonates with your audience."
            ),
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=get_publishing_analytics,
            input_schema=GetPublishingAnalyticsInput,
        ))

        # SEO Tools
        self.register_tool(AgentTool(
            name="track_keyword",
            description=(
                "Start tracking a keyword for SEO. Monitor rankings over time. "
                "Useful for tracking mortgage-related keywords like 'mortgage rates [city]', "
                "'first time home buyer programs', etc."
            ),
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.LOW,
            handler=track_keyword,
            input_schema=TrackKeywordInput,
        ))

        self.register_tool(AgentTool(
            name="get_keyword_suggestions",
            description=(
                "Get AI-powered keyword suggestions for mortgage content. "
                "Returns relevant keywords with search volume estimates and competition levels. "
                "Great for planning blog and SEO content."
            ),
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=get_keyword_suggestions,
            input_schema=GetKeywordSuggestionsInput,
        ))

        self.register_tool(AgentTool(
            name="get_keyword_opportunities",
            description=(
                "Find keyword ranking opportunities. Identifies quick wins "
                "(keywords where you rank 11-20) and striking distance keywords "
                "(rank 4-10) that are close to page 1."
            ),
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=get_keyword_opportunities,
            input_schema=GetKeywordOpportunitiesInput,
        ))

        # Carousel Tools
        self.register_tool(AgentTool(
            name="create_carousel_project",
            description=(
                "Create a new carousel project for social media. "
                "Link to CRM data (loan, lead, active loan) for personalized 'Just Closed' "
                "celebrations or other mortgage content. Supports LinkedIn, Instagram, TikTok, Facebook."
            ),
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.LOW,
            handler=create_carousel_project,
            input_schema=CreateCarouselInput,
        ))

        self.register_tool(AgentTool(
            name="generate_carousel_content",
            description=(
                "Generate AI carousel content. Creates slides for just_closed celebrations, "
                "rate updates, educational content (homebuyer tips), or marketing. "
                "Uses linked CRM data for personalization."
            ),
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.LOW,
            handler=generate_carousel_content,
            input_schema=GenerateCarouselContentInput,
        ))

        self.register_tool(AgentTool(
            name="get_carousel_templates",
            description=(
                "Get available carousel templates. Filter by type (just_closed, marketing, "
                "rate_update, educational) or platform (linkedin, instagram, tiktok, facebook). "
                "Templates provide pre-designed slide layouts."
            ),
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=get_carousel_templates,
            input_schema=GetCarouselTemplatesInput,
        ))

        # Personalization Tools
        self.register_tool(AgentTool(
            name="preview_personalization",
            description=(
                "Preview content with CRM tokens resolved. Shows how {{lead.first_name}}, "
                "{{loan.rate}}, {{mum.estimated_savings}} etc. will appear with real data "
                "from leads, active loans, or MUM clients."
            ),
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=preview_personalization,
            input_schema=PreviewPersonalizationInput,
        ))

        self.register_tool(AgentTool(
            name="get_personalization_tokens",
            description=(
                "Get available personalization tokens for CRM data. "
                "Returns tokens like {{lead.first_name}}, {{loan.rate}}, {{mum.estimated_savings}} "
                "with descriptions of what data they resolve to."
            ),
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=get_personalization_tokens,
            input_schema=GetPersonalizationTokensInput,
        ))

    async def get_content_strategy_summary(self) -> Dict[str, Any]:
        """Get a summary of current content strategy status."""
        try:
            # Get active calendars
            calendars_result = await self.execute_tool(
                "list_content_calendars",
                {"status": "active", "limit": 5}
            )

            # Get keyword opportunities
            keywords_result = await self.execute_tool(
                "get_keyword_opportunities",
                {}
            )

            # Get publishing analytics
            analytics_result = await self.execute_tool(
                "get_publishing_analytics",
                {"days": 30}
            )

            return ToolResult(
                success=True,
                data={
                    "active_calendars": calendars_result.data if calendars_result.success else None,
                    "keyword_opportunities": keywords_result.data if keywords_result.success else None,
                    "publishing_analytics": analytics_result.data if analytics_result.success else None,
                },
                message="Content strategy summary retrieved"
            )

        except Exception as e:
            logger.error(f"Error getting content strategy summary: {e}")
            return ToolResult(success=False, error=str(e))

    async def create_just_closed_carousel(
        self,
        loan_id: str = None,
        active_loan_id: str = None,
        platform: str = "linkedin",
    ) -> ToolResult:
        """
        Convenience method to create a Just Closed carousel from loan data.

        Args:
            loan_id: Optional loan ID for CRM data
            active_loan_id: Optional active loan ID
            platform: Target platform (linkedin, instagram, etc.)

        Returns:
            ToolResult with created carousel and generated slides
        """
        try:
            # Create the carousel project
            project_result = await self.execute_tool(
                "create_carousel_project",
                {
                    "name": "Just Closed Celebration",
                    "project_type": "just_closed",
                    "platform": platform,
                    "loan_id": loan_id,
                    "active_loan_id": active_loan_id,
                }
            )

            if not project_result.success:
                return project_result

            project_id = project_result.data.get("project_id")

            # Generate the content
            content_result = await self.execute_tool(
                "generate_carousel_content",
                {
                    "project_id": project_id,
                    "num_slides": 5,
                    "include_crm_data": True,
                }
            )

            if not content_result.success:
                return ToolResult(
                    success=True,
                    data={
                        "project": project_result.data,
                        "content_generation": "failed",
                        "error": content_result.error,
                    },
                    message="Carousel created but content generation failed"
                )

            return ToolResult(
                success=True,
                data={
                    "project": project_result.data,
                    "slides": content_result.data.get("slides", []),
                },
                message=f"Just Closed carousel created with {len(content_result.data.get('slides', []))} slides"
            )

        except Exception as e:
            logger.error(f"Error creating Just Closed carousel: {e}")
            return ToolResult(success=False, error=str(e))
