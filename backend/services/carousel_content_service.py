"""
Carousel Content Generation Service
AI-powered content generation for social media carousels using Claude
"""

import os
import re
import logging
from typing import Dict, Any, List, Optional
from anthropic import Anthropic
from datetime import datetime
from decimal import Decimal

logger = logging.getLogger(__name__)


class CarouselContentService:
    """
    AI-powered carousel content generator for mortgage professionals.

    Generates slide content for:
    - Just Closed celebrations
    - Rate updates and market trends
    - Educational content (homebuyer tips, loan types)
    - Marketing/promotional content
    """

    PLATFORM_SPECS = {
        "linkedin": {
            "style": "professional, informative, industry-focused",
            "tone": "authoritative yet approachable",
            "emoji_usage": "minimal (1-2 per slide max)",
        },
        "instagram": {
            "style": "visual, inspirational, lifestyle-focused",
            "tone": "friendly and engaging",
            "emoji_usage": "moderate (2-4 per slide)",
        },
        "tiktok": {
            "style": "trendy, snappy, attention-grabbing",
            "tone": "casual and energetic",
            "emoji_usage": "heavy (3-5 per slide)",
        },
        "facebook": {
            "style": "community-focused, shareable, relatable",
            "tone": "warm and conversational",
            "emoji_usage": "moderate (2-3 per slide)",
        },
    }

    # Prompt templates for each project type
    CONTENT_TEMPLATES = {
        "just_closed": """Create a celebratory "Just Closed" carousel for social media celebrating a successful mortgage closing.

CONTEXT:
{context}

REQUIREMENTS:
- Create {num_slides} slides for a {platform} carousel
- Slide 1: Eye-catching hook/celebration announcement
- Middle slides: Highlight the journey, key stats, or client experience
- Final slide: Call-to-action (contact info, encouragement for others)
- {tone_style}
- Keep text SHORT and impactful for visual slides
- Each slide should have: title (5-10 words max), subtitle (optional, 5-15 words), body (optional, 1-2 short sentences)

IMPORTANT:
- Be celebratory but professional
- Focus on the achievement, not specific loan details unless provided
- Include a personal touch where possible
- Make it shareable and inspiring to potential buyers

OUTPUT FORMAT (JSON):
Return a JSON array of slides, each with:
{{
  "title": "Main headline",
  "subtitle": "Supporting text (optional)",
  "body_text": "Additional context (optional)",
  "suggested_background": "gradient/solid recommendation",
  "suggested_colors": ["#hex1", "#hex2"]
}}""",

        "rate_update": """Create a mortgage rate update carousel for social media.

CONTEXT:
{context}

REQUIREMENTS:
- Create {num_slides} slides for a {platform} carousel
- Slide 1: Attention-grabbing rate announcement
- Middle slides: What this means for buyers/homeowners, market context
- Final slide: Call-to-action to get a personalized quote
- {tone_style}
- DO NOT include specific rate numbers (they change daily) unless explicitly provided
- Keep text SHORT and impactful

IMPORTANT:
- Create urgency without being pushy
- Educate while informing
- Position the LO as a trusted advisor

OUTPUT FORMAT (JSON):
Return a JSON array of slides, each with:
{{
  "title": "Main headline",
  "subtitle": "Supporting text (optional)",
  "body_text": "Additional context (optional)",
  "suggested_background": "gradient/solid recommendation",
  "suggested_colors": ["#hex1", "#hex2"]
}}""",

        "educational": """Create an educational mortgage carousel for social media.

CONTEXT:
{context}

REQUIREMENTS:
- Create {num_slides} slides for a {platform} carousel
- Slide 1: Hook with intriguing question or fact
- Middle slides: Break down the concept simply, use analogies
- Final slide: Summary and CTA to learn more
- {tone_style}
- Make complex mortgage concepts SIMPLE and accessible
- Use everyday language, avoid jargon

TOPICS TO CHOOSE FROM (if not specified):
- Credit score tips for homebuyers
- Down payment myths busted
- First-time homebuyer programs
- Refinancing: when does it make sense?
- Loan types explained (FHA vs Conventional vs VA)
- What happens at closing
- Pre-approval vs pre-qualification

OUTPUT FORMAT (JSON):
Return a JSON array of slides, each with:
{{
  "title": "Main headline",
  "subtitle": "Supporting text (optional)",
  "body_text": "Additional context (optional)",
  "suggested_background": "gradient/solid recommendation",
  "suggested_colors": ["#hex1", "#hex2"]
}}""",

        "marketing": """Create a marketing/promotional carousel for a mortgage professional.

CONTEXT:
{context}

REQUIREMENTS:
- Create {num_slides} slides for a {platform} carousel
- Slide 1: Strong value proposition or hook
- Middle slides: Benefits, testimonials, or service highlights
- Final slide: Clear call-to-action
- {tone_style}
- Focus on VALUE to the client, not features
- Be authentic and build trust

MARKETING ANGLES (if not specified):
- Why work with me (value proposition)
- Client success stories
- Local market expertise
- Service differentiators
- Seasonal opportunities

OUTPUT FORMAT (JSON):
Return a JSON array of slides, each with:
{{
  "title": "Main headline",
  "subtitle": "Supporting text (optional)",
  "body_text": "Additional context (optional)",
  "suggested_background": "gradient/solid recommendation",
  "suggested_colors": ["#hex1", "#hex2"]
}}""",

        "custom": """Create a custom carousel based on the following prompt.

CONTEXT:
{context}

REQUIREMENTS:
- Create {num_slides} slides for a {platform} carousel
- {tone_style}
- Keep text SHORT and impactful for visual slides
- Each slide should build on the previous, creating a cohesive narrative

USER PROMPT:
{custom_prompt}

OUTPUT FORMAT (JSON):
Return a JSON array of slides, each with:
{{
  "title": "Main headline",
  "subtitle": "Supporting text (optional)",
  "body_text": "Additional context (optional)",
  "suggested_background": "gradient/solid recommendation",
  "suggested_colors": ["#hex1", "#hex2"]
}}""",
    }

    # Token mapping for CRM data binding
    TOKEN_PATTERNS = {
        # Loan data tokens
        "loan.amount": lambda d: format_currency(d.get("amount")),
        "loan.rate": lambda d: f"{d.get('rate', 0):.3f}%" if d.get("rate") else "",
        "loan.term": lambda d: f"{d.get('term', 30)} years",
        "loan.program": lambda d: d.get("program", ""),
        "loan.lender": lambda d: d.get("lender", ""),
        "loan.ltv": lambda d: f"{d.get('ltv', 0):.1f}%" if d.get("ltv") else "",
        "loan.number": lambda d: d.get("loan_number", ""),

        # Property tokens
        "property.address": lambda d: d.get("property_address", ""),
        "property.city": lambda d: d.get("property_city", d.get("city", "")),
        "property.state": lambda d: d.get("property_state", d.get("state", "")),
        "property.zip": lambda d: d.get("property_zip", d.get("zip_code", "")),
        "property.value": lambda d: format_currency(d.get("appraisal_value", d.get("property_value"))),
        "property.type": lambda d: format_property_type(d.get("property_type", "")),

        # Borrower tokens
        "borrower.first_name": lambda d: d.get("first_name", d.get("borrower_name", "").split()[0] if d.get("borrower_name") else ""),
        "borrower.last_name": lambda d: d.get("last_name", d.get("borrower_name", "").split()[-1] if d.get("borrower_name") else ""),
        "borrower.name": lambda d: d.get("name", f"{d.get('first_name', '')} {d.get('last_name', '')}".strip()),

        # LO tokens
        "lo.name": lambda d: d.get("loan_officer_name", d.get("loan_officer", "")),
        "lo.email": lambda d: d.get("loan_officer_email", ""),
        "lo.phone": lambda d: d.get("lo_phone", ""),
        "lo.nmls": lambda d: d.get("lo_nmls", ""),
        "lo.company": lambda d: d.get("company_name", ""),

        # Date tokens
        "date.closing": lambda d: format_date(d.get("closing_scheduled_date", d.get("closing_date", d.get("original_close_date")))),
        "date.funding": lambda d: format_date(d.get("funding_date")),
        "date.today": lambda d: datetime.now().strftime("%B %d, %Y"),
    }

    def __init__(self):
        self.client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

    async def generate_carousel_content(
        self,
        project_type: str,
        platform: str = "linkedin",
        num_slides: int = 5,
        crm_data: Optional[Dict[str, Any]] = None,
        custom_prompt: Optional[str] = None,
        lo_info: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Generate carousel content using AI.

        Args:
            project_type: Type of carousel (just_closed, rate_update, educational, marketing, custom)
            platform: Target platform (linkedin, instagram, tiktok, facebook)
            num_slides: Number of slides to generate (3-10)
            crm_data: CRM data for token resolution (loan, lead, or MUM client data)
            custom_prompt: Custom prompt for custom project type
            lo_info: Loan officer information for personalization

        Returns:
            Dictionary with generated slides and metadata
        """
        # Validate inputs
        num_slides = max(3, min(10, num_slides))

        if project_type not in self.CONTENT_TEMPLATES:
            project_type = "custom"

        # Build context from CRM data
        context = self._build_context(crm_data, lo_info)

        # Get platform specs
        platform_spec = self.PLATFORM_SPECS.get(platform, self.PLATFORM_SPECS["linkedin"])
        tone_style = f"Style: {platform_spec['style']}\nTone: {platform_spec['tone']}\nEmoji usage: {platform_spec['emoji_usage']}"

        # Build prompt
        template = self.CONTENT_TEMPLATES[project_type]
        prompt = template.format(
            context=context,
            num_slides=num_slides,
            platform=platform.upper(),
            tone_style=tone_style,
            custom_prompt=custom_prompt or "",
        )

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )

            text = response.content[0].text

            # Parse JSON response
            slides = self._parse_slides_response(text)

            # Resolve any tokens in the generated content
            if crm_data:
                merged_data = {**(crm_data or {}), **(lo_info or {})}
                slides = self._resolve_tokens_in_slides(slides, merged_data)

            return {
                "success": True,
                "slides": slides,
                "project_type": project_type,
                "platform": platform,
                "generated_at": datetime.utcnow().isoformat(),
                "tokens_used": response.usage.input_tokens + response.usage.output_tokens,
            }

        except Exception as e:
            logger.error(f"Error generating carousel content: {e}")
            return {
                "success": False,
                "error": "Internal server error",
                "slides": self._get_fallback_slides(project_type, num_slides),
                "is_fallback": True,
            }

    def _build_context(
        self,
        crm_data: Optional[Dict[str, Any]],
        lo_info: Optional[Dict[str, Any]],
    ) -> str:
        """Build context string from CRM data."""
        context_parts = []

        if crm_data:
            # Loan information
            if crm_data.get("loan_number"):
                context_parts.append(f"Loan Number: {crm_data['loan_number']}")
            if crm_data.get("amount"):
                context_parts.append(f"Loan Amount: {format_currency(crm_data['amount'])}")
            if crm_data.get("program"):
                context_parts.append(f"Loan Program: {crm_data['program']}")

            # Property information
            city = crm_data.get("property_city") or crm_data.get("city")
            state = crm_data.get("property_state") or crm_data.get("state")
            if city and state:
                context_parts.append(f"Location: {city}, {state}")

            # Borrower information
            name = crm_data.get("name") or crm_data.get("borrower_name")
            first_name = crm_data.get("first_name")
            if name:
                context_parts.append(f"Client Name: {name}")
            elif first_name:
                last_name = crm_data.get("last_name", "")
                context_parts.append(f"Client Name: {first_name} {last_name}".strip())

            # Dates
            closing_date = crm_data.get("closing_scheduled_date") or crm_data.get("closing_date") or crm_data.get("original_close_date")
            if closing_date:
                context_parts.append(f"Closing Date: {format_date(closing_date)}")

        if lo_info:
            if lo_info.get("name") or lo_info.get("loan_officer_name"):
                context_parts.append(f"Loan Officer: {lo_info.get('name') or lo_info.get('loan_officer_name')}")
            if lo_info.get("company_name"):
                context_parts.append(f"Company: {lo_info['company_name']}")
            if lo_info.get("nmls") or lo_info.get("lo_nmls"):
                context_parts.append(f"NMLS#: {lo_info.get('nmls') or lo_info.get('lo_nmls')}")

        if not context_parts:
            return "No specific CRM data provided. Generate generic content."

        return "\n".join(context_parts)

    def _parse_slides_response(self, text: str) -> List[Dict[str, Any]]:
        """Parse the AI response to extract slides."""
        import json

        # Try to find JSON array in response
        try:
            # Look for JSON array pattern
            json_match = re.search(r'\[[\s\S]*\]', text)
            if json_match:
                slides = json.loads(json_match.group())
                return self._normalize_slides(slides)
        except json.JSONDecodeError:
            pass

        # Fallback: try to parse structured text
        slides = []
        slide_pattern = r'(?:Slide\s*\d+|Title):\s*(.+?)(?:Subtitle:\s*(.+?))?(?:Body:\s*(.+?))?(?=Slide\s*\d+|Title:|$)'
        matches = re.findall(slide_pattern, text, re.IGNORECASE | re.DOTALL)

        for match in matches:
            slide = {
                "title": match[0].strip() if match[0] else "",
                "subtitle": match[1].strip() if len(match) > 1 and match[1] else "",
                "body_text": match[2].strip() if len(match) > 2 and match[2] else "",
            }
            if slide["title"]:
                slides.append(slide)

        return slides if slides else self._get_fallback_slides("custom", 5)

    def _normalize_slides(self, slides: List[Dict]) -> List[Dict[str, Any]]:
        """Normalize slide structure."""
        normalized = []
        for slide in slides:
            normalized.append({
                "title": slide.get("title", ""),
                "subtitle": slide.get("subtitle", ""),
                "body_text": slide.get("body_text", slide.get("body", "")),
                "suggested_background": slide.get("suggested_background", "gradient"),
                "suggested_colors": slide.get("suggested_colors", ["#217F8D", "#1a5f6a"]),
            })
        return normalized

    def _resolve_tokens_in_slides(
        self,
        slides: List[Dict[str, Any]],
        data: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Resolve {{token}} patterns in slide content."""
        resolved = []
        for slide in slides:
            resolved_slide = {}
            for key, value in slide.items():
                if isinstance(value, str):
                    resolved_slide[key] = self.resolve_tokens(value, data)
                else:
                    resolved_slide[key] = value
            resolved.append(resolved_slide)
        return resolved

    def resolve_tokens(self, text: str, data: Dict[str, Any]) -> str:
        """
        Resolve {{token}} patterns in text using CRM data.

        Args:
            text: Text with {{token}} patterns
            data: CRM data dictionary

        Returns:
            Text with tokens resolved
        """
        if not text or not data:
            return text

        def replace_token(match):
            token = match.group(1).strip()
            if token in self.TOKEN_PATTERNS:
                try:
                    return str(self.TOKEN_PATTERNS[token](data))
                except Exception as e:
                    logger.warning(f"Token resolution failed for '{token}': {e}")
                    return match.group(0)  # Keep original if error
            return match.group(0)  # Keep original if unknown token

        return re.sub(r'\{\{(.+?)\}\}', replace_token, text)

    def get_available_tokens(self) -> Dict[str, str]:
        """Get list of available tokens with descriptions."""
        return {
            "{{loan.amount}}": "Loan amount formatted as currency",
            "{{loan.rate}}": "Interest rate with percentage",
            "{{loan.term}}": "Loan term in years",
            "{{loan.program}}": "Loan program type",
            "{{loan.number}}": "Loan number",
            "{{property.address}}": "Full property address",
            "{{property.city}}": "Property city",
            "{{property.state}}": "Property state",
            "{{property.value}}": "Property/appraisal value",
            "{{property.type}}": "Property type (formatted)",
            "{{borrower.first_name}}": "Borrower first name",
            "{{borrower.last_name}}": "Borrower last name",
            "{{borrower.name}}": "Borrower full name",
            "{{lo.name}}": "Loan officer name",
            "{{lo.email}}": "Loan officer email",
            "{{lo.nmls}}": "Loan officer NMLS number",
            "{{lo.company}}": "Company name",
            "{{date.closing}}": "Closing date",
            "{{date.funding}}": "Funding date",
            "{{date.today}}": "Today's date",
        }

    def _get_fallback_slides(self, project_type: str, num_slides: int) -> List[Dict[str, Any]]:
        """Get fallback slides if AI generation fails."""
        fallbacks = {
            "just_closed": [
                {"title": "🎉 Just Closed!", "subtitle": "Another Dream Home Funded", "body_text": ""},
                {"title": "The Journey", "subtitle": "From Application to Keys", "body_text": "Every step of the way, we were there."},
                {"title": "Congratulations!", "subtitle": "Welcome Home", "body_text": ""},
                {"title": "Your Turn?", "subtitle": "Let's Make It Happen", "body_text": "Contact me to start your journey."},
            ],
            "rate_update": [
                {"title": "📊 Rate Update", "subtitle": "What You Need to Know", "body_text": ""},
                {"title": "Market Movement", "subtitle": "Rates Are Changing", "body_text": "Now might be the time to act."},
                {"title": "What This Means", "subtitle": "For Buyers & Homeowners", "body_text": ""},
                {"title": "Get Your Quote", "subtitle": "Personalized Rates Available", "body_text": "Contact me today!"},
            ],
            "educational": [
                {"title": "Did You Know?", "subtitle": "Mortgage Tips", "body_text": ""},
                {"title": "The Basics", "subtitle": "Understanding Your Options", "body_text": ""},
                {"title": "Pro Tip", "subtitle": "What the Experts Know", "body_text": ""},
                {"title": "Learn More", "subtitle": "I'm Here to Help", "body_text": "Have questions? Let's talk!"},
            ],
            "marketing": [
                {"title": "Why Work With Me?", "subtitle": "Your Trusted Mortgage Partner", "body_text": ""},
                {"title": "Experience Matters", "subtitle": "Hundreds of Happy Clients", "body_text": ""},
                {"title": "My Promise", "subtitle": "Communication & Transparency", "body_text": ""},
                {"title": "Let's Connect", "subtitle": "Your Dream Home Awaits", "body_text": ""},
            ],
        }

        slides = fallbacks.get(project_type, fallbacks["marketing"])
        return slides[:num_slides]


# Helper functions
def format_currency(amount) -> str:
    """Format amount as currency."""
    if amount is None:
        return ""
    try:
        if isinstance(amount, Decimal):
            amount = float(amount)
        return f"${amount:,.0f}"
    except (ValueError, TypeError):
        return ""


def format_date(date_value) -> str:
    """Format date for display."""
    if date_value is None:
        return ""
    try:
        if isinstance(date_value, str):
            date_value = datetime.fromisoformat(date_value.replace('Z', '+00:00'))
        return date_value.strftime("%B %d, %Y")
    except Exception as e:
        logger.warning(f"Date formatting failed in format_date: {e}")
        return str(date_value) if date_value else ""


def format_property_type(prop_type: str) -> str:
    """Format property type for display."""
    mapping = {
        "single_family": "Single Family Home",
        "condo": "Condominium",
        "townhouse": "Townhouse",
        "multi_family": "Multi-Family",
        "manufactured": "Manufactured Home",
    }
    return mapping.get(prop_type, prop_type.replace("_", " ").title() if prop_type else "")


# Singleton instance
carousel_content_service = CarouselContentService()
