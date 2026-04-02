"""
Social Content Generation Service
AI-powered social media content generation for loan officers
"""

import os
import logging
from typing import Dict, Any, List, Optional
from anthropic import Anthropic
from datetime import datetime

logger = logging.getLogger(__name__)


class SocialContentService:
    """
    AI-powered social media content generator for mortgage professionals.

    Generates platform-specific content for:
    - Market updates
    - Homebuyer tips
    - Rate alerts
    - Success stories
    - Educational content
    """

    PLATFORM_SPECS = {
        "linkedin": {
            "max_chars": 3000,
            "style": "professional and informative",
            "hashtag_count": 3,
            "emoji_usage": "minimal",
        },
        "facebook": {
            "max_chars": 2000,
            "style": "friendly and engaging",
            "hashtag_count": 2,
            "emoji_usage": "moderate",
        },
        "instagram": {
            "max_chars": 2200,
            "style": "visual and inspirational",
            "hashtag_count": 10,
            "emoji_usage": "heavy",
        },
        "twitter": {
            "max_chars": 280,
            "style": "concise and punchy",
            "hashtag_count": 2,
            "emoji_usage": "moderate",
        },
    }

    CONTENT_TEMPLATES = {
        "market_update": """Generate a social media post about current mortgage market conditions.
Include:
- Current rate trends (mention rates are dynamic)
- What this means for buyers/homeowners
- A call to action to learn more

Tone: Informative but approachable
Do NOT mention specific rate numbers (they change daily).""",

        "tip": """Generate a helpful homebuyer tip post.
Topic ideas:
- Credit score improvement
- Saving for down payment
- Documentation preparation
- Pre-approval process
- Closing costs
- Home inspection importance

Make it actionable and valuable.""",

        "rate_alert": """Generate an attention-grabbing rate alert post.
Focus on:
- Urgency without being pushy
- The benefit of acting now
- Invitation to get personalized quote

Do NOT mention specific rate numbers.""",

        "success_story": """Generate a celebratory post about helping a client close.
Include:
- Excitement about the achievement
- Mention of overcoming challenges (generic)
- Congratulations to the "clients"
- Offer to help others achieve the same

Keep it authentic and not salesy.""",

        "educational": """Generate an educational post explaining a mortgage concept.
Topics to choose from:
- DTI ratio explained
- Points and buydowns
- Loan types (Conventional vs FHA vs VA)
- PMI explained
- Escrow accounts
- Refinancing benefits

Make complex topics simple.""",
    }

    def __init__(self):
        self.client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

    async def generate_content(
        self,
        content_type: str,
        platform: str = "all",
        lo_name: Optional[str] = None,
        company_name: Optional[str] = None,
        additional_context: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Generate social media content

        Args:
            content_type: Type of content (market_update, tip, rate_alert, success_story, educational)
            platform: Target platform (linkedin, facebook, instagram, twitter, all)
            lo_name: Loan officer name for personalization
            company_name: Company name for branding
            additional_context: Additional context or requirements

        Returns:
            List of content dictionaries with platform, text, and hashtags
        """
        if content_type not in self.CONTENT_TEMPLATES:
            content_type = "tip"  # Default to tip

        base_prompt = self.CONTENT_TEMPLATES[content_type]

        # Determine target platforms
        if platform == "all":
            platforms = ["linkedin", "facebook", "instagram", "twitter"]
        else:
            platforms = [platform]

        results = []

        for plat in platforms:
            spec = self.PLATFORM_SPECS.get(plat, self.PLATFORM_SPECS["facebook"])

            prompt = f"""{base_prompt}

Platform: {plat.upper()}
Maximum length: {spec['max_chars']} characters
Style: {spec['style']}
Number of hashtags: {spec['hashtag_count']}
Emoji usage: {spec['emoji_usage']}

{f"Loan Officer Name: {lo_name}" if lo_name else ""}
{f"Company: {company_name}" if company_name else ""}
{f"Additional context: {additional_context}" if additional_context else ""}

Output format:
POST:
[Your post content here]

HASHTAGS:
[hashtags separated by spaces]"""

            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=1024,
                    messages=[
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ]
                )

                text = response.content[0].text

                # Parse response
                post_text = ""
                hashtags = ""

                if "POST:" in text and "HASHTAGS:" in text:
                    parts = text.split("HASHTAGS:")
                    post_text = parts[0].replace("POST:", "").strip()
                    hashtags = parts[1].strip() if len(parts) > 1 else ""
                else:
                    post_text = text.strip()

                results.append({
                    "platform": plat,
                    "text": post_text[:spec["max_chars"]],
                    "hashtags": hashtags,
                    "content_type": content_type,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                })

            except Exception as e:
                logger.error(f"Error generating content for {plat}: {e}")
                # Add fallback content
                results.append({
                    "platform": plat,
                    "text": self._get_fallback_content(content_type, plat),
                    "hashtags": "#mortgage #homebuying #realestate",
                    "content_type": content_type,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "is_fallback": True,
                })

        return results

    def _get_fallback_content(self, content_type: str, platform: str) -> str:
        """Get fallback content if AI generation fails"""
        fallbacks = {
            "market_update": "Rates are always changing! Contact me today to discuss your options and lock in your rate. Let's make your homeownership dreams a reality!",
            "tip": "Pro tip: Start gathering your financial documents early! Pay stubs, tax returns, and bank statements are essentials for a smooth loan process.",
            "rate_alert": "Now could be a great time to explore your mortgage options! Reach out for a personalized rate quote and see what you qualify for.",
            "success_story": "Another happy client in their new home! Congratulations to our latest family on closing. Ready to be next? Let's chat!",
            "educational": "Did you know? Getting pre-approved before house hunting shows sellers you're serious and helps you know exactly what you can afford.",
        }
        return fallbacks.get(content_type, fallbacks["tip"])

    async def generate_batch(
        self,
        content_types: List[str],
        platform: str = "all",
        lo_name: Optional[str] = None,
        company_name: Optional[str] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Generate multiple types of content in one batch

        Returns:
            Dictionary with content_type as key and list of platform content as value
        """
        results = {}
        for content_type in content_types:
            content = await self.generate_content(
                content_type=content_type,
                platform=platform,
                lo_name=lo_name,
                company_name=company_name,
            )
            results[content_type] = content
        return results

    def get_posting_schedule_suggestions(self, platform: str) -> Dict[str, Any]:
        """Get optimal posting time suggestions for a platform"""
        schedules = {
            "linkedin": {
                "best_days": ["Tuesday", "Wednesday", "Thursday"],
                "best_times": ["7:00 AM", "12:00 PM", "5:00 PM"],
                "posts_per_week": 3,
            },
            "facebook": {
                "best_days": ["Wednesday", "Thursday", "Friday"],
                "best_times": ["9:00 AM", "1:00 PM", "4:00 PM"],
                "posts_per_week": 5,
            },
            "instagram": {
                "best_days": ["Monday", "Wednesday", "Friday"],
                "best_times": ["11:00 AM", "2:00 PM", "7:00 PM"],
                "posts_per_week": 4,
            },
            "twitter": {
                "best_days": ["Tuesday", "Wednesday", "Thursday"],
                "best_times": ["8:00 AM", "12:00 PM", "6:00 PM"],
                "posts_per_week": 7,
            },
        }
        return schedules.get(platform, schedules["facebook"])


# Singleton instance
social_content_service = SocialContentService()
