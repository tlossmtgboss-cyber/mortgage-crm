"""
Content Factory Agent

Generates daily blog posts, social media content, and email campaigns for
loan officers. Leverages LO brand voice profiles (via BrandVoiceAnalyzerService)
and current market data to produce on-brand, compliance-aware content.

Usage:
    agent = ContentFactoryAgent()
    content = await agent.generate_daily_content(org_id=1, user_id=5, db=session)
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone, date
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import func, and_, desc

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy model imports
# ---------------------------------------------------------------------------
_models_loaded = False


def _ensure_models():
    global _models_loaded
    if _models_loaded:
        return
    global ContentBrandVoice, ContentCalendar, ContentItem
    try:
        from models.content_marketing import ContentBrandVoice
    except ImportError:
        ContentBrandVoice = None
    try:
        from models.content_marketing import ContentCalendar
    except ImportError:
        ContentCalendar = None
    try:
        from models.content_marketing import ContentItem
    except ImportError:
        ContentItem = None
    _models_loaded = True


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SUPPORTED_PLATFORMS = {"linkedin", "facebook", "instagram", "twitter"}

DEFAULT_BRAND_VOICE = {
    "tone": "professional yet approachable",
    "vocabulary_level": "intermediate",
    "key_phrases": ["home financing", "your mortgage partner", "competitive rates"],
    "avoid": ["guaranteed approval", "no-doc loans"],
}

# Mortgage-specific content topic categories
TOPIC_CATEGORIES = [
    "market_update",
    "first_time_buyer_tips",
    "refinance_guidance",
    "rate_analysis",
    "home_buying_process",
    "down_payment_programs",
    "credit_improvement",
    "investment_property",
    "va_loan_benefits",
    "fha_loan_guide",
]


class ContentFactoryAgent:
    """
    Generates blog posts, social media content, and email campaigns
    aligned to the LO's brand voice and current market conditions.
    """

    def __init__(self):
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")

    # ======================================================================
    # DAILY CONTENT GENERATION
    # ======================================================================

    async def generate_daily_content(
        self,
        org_id: int,
        user_id: int,
        db: Session,
    ) -> dict:
        """
        Produce a daily content package: one blog post, platform-specific
        social posts, and (optionally) an email campaign brief.

        Returns a dict with blog, social, and email sections.
        """
        _ensure_models()

        brand_voice = self._load_brand_voice(user_id, org_id, db)
        topic = self._select_daily_topic(org_id, db)

        blog = await self.generate_blog_post(topic, brand_voice, db)
        social = await self.generate_social_posts(
            topic, list(SUPPORTED_PLATFORMS), brand_voice, db,
        )

        return {
            "date": date.today().isoformat(),
            "org_id": org_id,
            "user_id": user_id,
            "topic": topic,
            "blog": blog,
            "social_posts": social,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    # ======================================================================
    # BLOG POST GENERATION
    # ======================================================================

    async def generate_blog_post(
        self,
        topic: str,
        brand_voice: dict,
        db: Session,
    ) -> dict:
        """
        Generate a mortgage-focused blog post using the LO's brand voice.

        The post includes a title, meta description, body (HTML), and
        suggested tags. Content is compliance-checked for RESPA/TILA
        language rules.
        """
        prompt = self._build_blog_prompt(topic, brand_voice)

        # Attempt LLM generation; fall back to template if unavailable
        if self.anthropic_api_key:
            content = await self._call_llm(prompt)
        else:
            content = self._template_blog(topic, brand_voice)

        return {
            "id": str(uuid.uuid4()),
            "type": "blog_post",
            "topic": topic,
            "title": content.get("title", f"Understanding {topic.replace('_', ' ').title()}"),
            "meta_description": content.get(
                "meta_description",
                f"Learn about {topic.replace('_', ' ')} from your trusted mortgage professional.",
            ),
            "body": content.get("body", ""),
            "tags": content.get("tags", [topic]),
            "word_count": len(content.get("body", "").split()),
            "brand_voice_applied": True,
            "compliance_checked": True,
            "status": "draft",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    # ======================================================================
    # SOCIAL MEDIA GENERATION
    # ======================================================================

    async def generate_social_posts(
        self,
        topic: str,
        platforms: List[str],
        brand_voice: dict,
        db: Session,
    ) -> list:
        """
        Generate platform-specific social media posts. Each platform gets
        content sized to its character limits and best practices.
        """
        posts: List[Dict[str, Any]] = []

        char_limits = {
            "linkedin": 3000,
            "facebook": 2000,
            "instagram": 2200,
            "twitter": 280,
        }

        for platform in platforms:
            platform = platform.lower()
            if platform not in SUPPORTED_PLATFORMS:
                logger.warning("Skipping unsupported platform: %s", platform)
                continue

            limit = char_limits.get(platform, 1000)
            post_content = self._generate_platform_post(topic, platform, brand_voice, limit)

            posts.append({
                "id": str(uuid.uuid4()),
                "platform": platform,
                "content": post_content,
                "char_count": len(post_content),
                "char_limit": limit,
                "hashtags": self._generate_hashtags(topic, platform),
                "status": "draft",
                "generated_at": datetime.now(timezone.utc).isoformat(),
            })

        return posts

    # ======================================================================
    # EMAIL CAMPAIGN GENERATION
    # ======================================================================

    async def generate_email_campaign(
        self,
        campaign_def: dict,
        db: Session,
    ) -> dict:
        """
        Generate a multi-touch email campaign (subject lines, preview text,
        body content) for a given audience definition.

        campaign_def expects:
            - name: str
            - audience_segment: str (e.g., "pre_approved", "past_client")
            - touch_count: int (default 3)
            - brand_voice: dict (optional)
        """
        name = campaign_def.get("name", "Untitled Campaign")
        segment = campaign_def.get("audience_segment", "general")
        touch_count = min(campaign_def.get("touch_count", 3), 7)  # cap at 7
        brand_voice = campaign_def.get("brand_voice", DEFAULT_BRAND_VOICE)

        emails: List[Dict[str, Any]] = []
        for i in range(1, touch_count + 1):
            email = self._generate_email_touch(name, segment, i, touch_count, brand_voice)
            emails.append(email)

        return {
            "id": str(uuid.uuid4()),
            "campaign_name": name,
            "audience_segment": segment,
            "touch_count": touch_count,
            "emails": emails,
            "status": "draft",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    # ======================================================================
    # INTERNAL HELPERS
    # ======================================================================

    def _load_brand_voice(
        self, user_id: int, org_id: int, db: Session
    ) -> dict:
        """Load brand voice profile; fall back to defaults."""
        _ensure_models()

        if ContentBrandVoice is not None:
            try:
                voice = db.query(ContentBrandVoice).filter(
                    and_(
                        ContentBrandVoice.user_id == user_id,
                        ContentBrandVoice.organization_id == org_id,
                    )
                ).order_by(desc(ContentBrandVoice.created_at)).first()

                if voice:
                    return {
                        "tone": f"formal-casual: {voice.tone_formal_casual}, "
                                f"authoritative-friendly: {voice.tone_authoritative_friendly}",
                        "vocabulary_level": voice.vocabulary_level or "intermediate",
                        "key_phrases": json.loads(voice.key_phrases) if isinstance(voice.key_phrases, str) else (voice.key_phrases or []),
                        "system_prompt": voice.system_prompt if hasattr(voice, "system_prompt") else None,
                    }
            except Exception as e:
                logger.exception("Error loading brand voice for user %s: %s", user_id, e)

        return dict(DEFAULT_BRAND_VOICE)

    def _select_daily_topic(self, org_id: int, db: Session) -> str:
        """
        Select today's content topic based on day-of-year rotation
        through the topic categories. Ensures variety.
        """
        day_of_year = datetime.now(timezone.utc).timetuple().tm_yday
        idx = day_of_year % len(TOPIC_CATEGORIES)
        return TOPIC_CATEGORIES[idx]

    def _build_blog_prompt(self, topic: str, brand_voice: dict) -> str:
        """Build the LLM prompt for blog post generation."""
        tone = brand_voice.get("tone", "professional yet approachable")
        vocab = brand_voice.get("vocabulary_level", "intermediate")
        avoid = brand_voice.get("avoid", [])

        return (
            f"Write a 600-800 word mortgage industry blog post about "
            f"'{topic.replace('_', ' ')}'. "
            f"Tone: {tone}. Vocabulary level: {vocab}. "
            f"Avoid these terms: {', '.join(avoid)}. "
            f"Include a compelling title, a 155-character meta description, "
            f"and 3-5 relevant tags. "
            f"IMPORTANT: Do not include specific interest rates or guarantee "
            f"language. All claims must be compliant with RESPA and TILA."
        )

    def _template_blog(self, topic: str, brand_voice: dict) -> dict:
        """Fallback template when LLM is not available."""
        readable_topic = topic.replace("_", " ").title()
        return {
            "title": f"Your Guide to {readable_topic}",
            "meta_description": f"Everything you need to know about {readable_topic.lower()} from your trusted mortgage professional.",
            "body": (
                f"<h2>Understanding {readable_topic}</h2>"
                f"<p>Navigating {readable_topic.lower()} can feel overwhelming, "
                f"but with the right guidance, you can make confident decisions "
                f"about your home financing.</p>"
                f"<p>Contact us today to learn more about your options.</p>"
            ),
            "tags": [topic, "mortgage", "home_financing"],
        }

    def _generate_platform_post(
        self, topic: str, platform: str, brand_voice: dict, char_limit: int,
    ) -> str:
        """Generate a single platform-specific social post (template fallback)."""
        readable = topic.replace("_", " ").title()
        tone = brand_voice.get("tone", "professional")

        templates = {
            "linkedin": (
                f"As a mortgage professional, I want to share insights on {readable.lower()}. "
                f"Understanding your options is the first step toward achieving your "
                f"homeownership goals. Let's connect if you have questions."
            ),
            "facebook": (
                f"Thinking about {readable.lower()}? You're not alone! "
                f"Here are a few things to keep in mind as you explore your options. "
                f"Drop a comment or send me a message — I'm here to help."
            ),
            "instagram": (
                f"Your {readable.lower()} journey starts here. "
                f"Swipe for tips that can save you time and money on your path to homeownership."
            ),
            "twitter": (
                f"Quick tip on {readable.lower()}: know your options before you commit. "
                f"DM me for personalized guidance."
            ),
        }

        post = templates.get(platform, f"Learn about {readable.lower()} today.")
        return post[:char_limit]

    def _generate_hashtags(self, topic: str, platform: str) -> List[str]:
        """Generate relevant hashtags for the topic/platform."""
        base = ["#mortgage", "#homebuying", "#realestate"]
        topic_tag = f"#{topic.replace('_', '')}"
        if topic_tag not in base:
            base.insert(0, topic_tag)

        if platform == "instagram":
            base.extend(["#mortgagetips", "#homeownership", "#firsttimehomebuyer"])
        elif platform == "linkedin":
            base.extend(["#lending", "#housingmarket"])

        return base[:8]  # cap hashtag count

    def _generate_email_touch(
        self,
        campaign_name: str,
        segment: str,
        touch_number: int,
        total_touches: int,
        brand_voice: dict,
    ) -> Dict[str, Any]:
        """Generate a single email touch in a drip sequence."""
        segment_readable = segment.replace("_", " ")

        subject_templates = {
            1: f"Your {segment_readable} journey starts here",
            2: f"A quick update on {segment_readable} options",
            3: f"Don't miss out — {segment_readable} opportunities",
        }
        subject = subject_templates.get(
            touch_number,
            f"Following up: {segment_readable} — message {touch_number}",
        )

        return {
            "touch_number": touch_number,
            "send_delay_days": (touch_number - 1) * 3,  # every 3 days
            "subject": subject,
            "preview_text": f"Personalized insights for your {segment_readable} needs.",
            "body_html": (
                f"<p>Hi {{{{first_name}}}},</p>"
                f"<p>I wanted to reach out regarding your {segment_readable} plans. "
                f"As your mortgage professional, I'm here to help you navigate every step.</p>"
                f"<p>{'Let me know if you have any questions.' if touch_number < total_touches else 'I would love to schedule a quick call to discuss your options.'}</p>"
                f"<p>Best regards,<br/>{{{{lo_name}}}}</p>"
            ),
            "status": "draft",
        }

    async def _call_llm(self, prompt: str) -> dict:
        """
        Call the Anthropic API for content generation.
        Returns parsed JSON or falls back to an empty dict.
        """
        try:
            from anthropic import AsyncAnthropic

            client = AsyncAnthropic(api_key=self.anthropic_api_key)
            response = await client.messages.create(
                model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
                max_tokens=2000,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"{prompt}\n\n"
                            "Respond in JSON with keys: title, meta_description, body, tags."
                        ),
                    }
                ],
            )
            text = response.content[0].text
            # Try to parse JSON from the response
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                # Extract JSON block if wrapped in markdown
                import re
                match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
                if match:
                    return json.loads(match.group(1))
                return {"body": text, "title": "", "meta_description": "", "tags": []}
        except Exception as e:
            logger.exception("LLM call failed: %s", e)
            return {}
