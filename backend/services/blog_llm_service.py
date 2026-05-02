"""
Blog LLM Content Generation Service - AI-powered content creation for blogs and social.

Handles:
- Blog post generation with multiple archetypes
- Social media content adaptation
- Voice profile application
- Topic mining from source documents
- Image prompt generation

Caching Strategy:
- Topic mining: 6 hours TTL (same source should return consistent topics)
- Social content: 1 hour TTL (same blog content for same platforms)
- Image prompts: 24 hours TTL (same title/excerpt should be consistent)
- Blog posts: Not cached (users want unique content each time)
"""

import os
import json
import logging
import re
import hashlib
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import httpx

from services.llm_cache_service import llm_cache, LLMCacheService

logger = logging.getLogger(__name__)

# API Configuration
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DEFAULT_MODEL = "claude-haiku-4-5-20251001"  # Claude Haiku 4.5 - fast and efficient


class ContentGenerationResult:
    """Result from content generation."""

    def __init__(
        self,
        success: bool,
        title: str = "",
        slug: str = "",
        blog_md: str = "",
        blog_html: str = "",
        social: Dict[str, str] = None,
        image_prompt: str = "",
        metadata: Dict[str, Any] = None,
        error: Optional[str] = None,
    ):
        self.success = success
        self.title = title
        self.slug = slug
        self.blog_md = blog_md
        self.blog_html = blog_html
        self.social = social or {}
        self.image_prompt = image_prompt
        self.metadata = metadata or {}
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "title": self.title,
            "slug": self.slug,
            "blog_md": self.blog_md,
            "blog_html": self.blog_html,
            "social": self.social,
            "image_prompt": self.image_prompt,
            "metadata": self.metadata,
            "error": self.error,
        }


class BlogLLMService:
    """Service for AI-powered blog and social content generation."""

    # Content archetypes with their characteristics
    ARCHETYPES = {
        "informative": {
            "description": "Educational, fact-based content that explains concepts clearly",
            "tone": "authoritative but accessible",
            "structure": "introduction, key points, detailed explanation, conclusion",
            "length_target": 800,
        },
        "story": {
            "description": "Narrative-driven content with client scenarios or case studies",
            "tone": "engaging, empathetic, relatable",
            "structure": "hook, setup, challenge, resolution, takeaway",
            "length_target": 1000,
        },
        "data_driven": {
            "description": "Statistics and market data focused content",
            "tone": "analytical, credible, insightful",
            "structure": "key finding, context, data points, implications, action items",
            "length_target": 700,
        },
        "how_to": {
            "description": "Step-by-step guides and tutorials",
            "tone": "practical, clear, encouraging",
            "structure": "overview, prerequisites, steps, tips, summary",
            "length_target": 900,
        },
        "myth_busting": {
            "description": "Debunking common misconceptions",
            "tone": "corrective but not condescending, enlightening",
            "structure": "myth statement, why it's wrong, the truth, evidence, conclusion",
            "length_target": 750,
        },
    }

    # Social media format specifications
    SOCIAL_FORMATS = {
        "linkedin": {
            "max_length": 3000,
            "style": "professional, thought-leadership oriented",
            "hashtags": 3,
            "cta": "professional call-to-action",
        },
        "facebook": {
            "max_length": 500,
            "style": "friendly, conversational, community-focused",
            "hashtags": 2,
            "cta": "engagement-focused question or share prompt",
        },
        "instagram": {
            "max_length": 2200,
            "style": "visual-focused, emoji-friendly, inspirational",
            "hashtags": 10,
            "cta": "save, share, or comment prompt",
        },
        "twitter": {
            "max_length": 280,
            "style": "punchy, attention-grabbing, threaded if needed",
            "hashtags": 2,
            "cta": "retweet or reply prompt",
        },
    }

    def __init__(self):
        self.enabled = bool(ANTHROPIC_API_KEY or OPENAI_API_KEY)
        if not self.enabled:
            logger.warning("No LLM API keys configured - content generation disabled")
        else:
            logger.info("Blog LLM service initialized")

    def _apply_voice_profile(self, base_prompt: str, voice_profile: Dict[str, Any]) -> str:
        """Apply voice profile settings to the prompt."""
        if not voice_profile:
            return base_prompt

        sliders = voice_profile.get("sliders_json", {})
        toggles = voice_profile.get("toggles_json", {})
        examples = voice_profile.get("examples_json", {})

        voice_instructions = "\n\nVOICE PROFILE:\n"

        # Process sliders (0-100 scale)
        slider_mappings = {
            "professional_casual": ("professional", "casual"),
            "bold_conservative": ("bold", "conservative"),
            "detailed_concise": ("detailed", "concise"),
            "formal_friendly": ("formal", "friendly"),
            "technical_simple": ("technical", "simple"),
        }

        for slider_key, (low_label, high_label) in slider_mappings.items():
            if slider_key in sliders:
                value = sliders[slider_key]
                if value < 30:
                    voice_instructions += f"- Lean heavily toward {low_label} tone\n"
                elif value < 45:
                    voice_instructions += f"- Lean slightly toward {low_label} tone\n"
                elif value > 70:
                    voice_instructions += f"- Lean heavily toward {high_label} tone\n"
                elif value > 55:
                    voice_instructions += f"- Lean slightly toward {high_label} tone\n"

        # Process toggles
        if toggles.get("use_emojis"):
            voice_instructions += "- Include relevant emojis sparingly\n"
        if toggles.get("use_hashtags"):
            voice_instructions += "- Include relevant hashtags\n"
        if toggles.get("use_questions"):
            voice_instructions += "- Use rhetorical questions to engage readers\n"
        if toggles.get("use_statistics"):
            voice_instructions += "- Incorporate statistics when relevant\n"
        if toggles.get("use_stories"):
            voice_instructions += "- Include brief anecdotes or examples\n"

        # Add example content if available
        if examples.get("sample_content"):
            voice_instructions += f"\nMatch the style of this example:\n{examples['sample_content'][:500]}\n"

        return base_prompt + voice_instructions

    async def generate_blog_post(
        self,
        topic: str,
        archetype: str = "informative",
        keyword: str = "",
        source_content: str = "",
        voice_profile: Dict[str, Any] = None,
        compliance_profile: Dict[str, Any] = None,
        additional_context: str = "",
    ) -> ContentGenerationResult:
        """
        Generate a complete blog post.

        Args:
            topic: The topic or angle for the blog post
            archetype: Content archetype (informative, story, etc.)
            keyword: Target SEO keyword
            source_content: Source material to draw from
            voice_profile: Voice/brand settings
            compliance_profile: Compliance requirements
            additional_context: Any additional instructions

        Returns:
            ContentGenerationResult with the generated content
        """
        if not self.enabled:
            logger.error("LLM service not configured - ANTHROPIC_API_KEY or OPENAI_API_KEY environment variable not set")
            return ContentGenerationResult(
                success=False,
                error="LLM service not configured. Please set ANTHROPIC_API_KEY or OPENAI_API_KEY environment variable."
            )

        archetype_info = self.ARCHETYPES.get(archetype, self.ARCHETYPES["informative"])

        # Build the prompt
        prompt = f"""Generate a professional mortgage industry blog post.

TOPIC: {topic}
ARCHETYPE: {archetype} - {archetype_info['description']}
TARGET KEYWORD: {keyword or 'none specified'}
TONE: {archetype_info['tone']}
STRUCTURE: {archetype_info['structure']}
TARGET LENGTH: ~{archetype_info['length_target']} words

{f'SOURCE MATERIAL TO DRAW FROM (do not copy directly):{chr(10)}{source_content[:3000]}' if source_content else ''}

{f'ADDITIONAL CONTEXT: {additional_context}' if additional_context else ''}

REQUIREMENTS:
1. Write in Markdown format
2. Include a compelling title (H1)
3. Include 2-3 subheadings (H2)
4. Natural keyword integration (not stuffed)
5. Actionable takeaways
6. Professional mortgage industry voice
7. Original content - do not copy source material verbatim

Respond with valid JSON in this format:
{{
    "title": "The blog post title",
    "slug": "url-friendly-slug",
    "blog_md": "Full markdown content...",
    "meta_description": "SEO meta description (150-160 chars)",
    "excerpt": "Short excerpt for previews (200-250 chars)",
    "estimated_read_time": 4,
    "primary_keyword": "{keyword or 'mortgage topic'}",
    "secondary_keywords": ["related", "keywords"],
    "image_prompt": "Detailed prompt for generating a header image"
}}"""

        # Apply voice profile
        prompt = self._apply_voice_profile(prompt, voice_profile)

        # Apply compliance requirements
        if compliance_profile:
            prompt = self._apply_compliance_requirements(prompt, compliance_profile)

        try:
            response_text = await self._call_llm(prompt)
            result = self._parse_blog_response(response_text)

            # Convert markdown to HTML
            result.blog_html = self._markdown_to_html(result.blog_md)

            return result

        except Exception as e:
            logger.error(f"Blog generation failed: {e}")
            return ContentGenerationResult(
                success=False,
                error=str(e)
            )

    def _apply_compliance_requirements(
        self,
        prompt: str,
        compliance_profile: Dict[str, Any]
    ) -> str:
        """Apply compliance requirements to the prompt."""
        compliance_text = "\n\nCOMPLIANCE REQUIREMENTS:\n"

        # Required disclosures
        disclosures = compliance_profile.get("required_disclosures_json", [])
        if disclosures:
            compliance_text += "Include these disclosures at the end:\n"
            for disclosure in disclosures:
                compliance_text += f"- {disclosure}\n"

        # Banned phrases
        banned = compliance_profile.get("banned_phrases_json", [])
        if banned:
            compliance_text += "NEVER use these phrases:\n"
            for phrase in banned[:20]:  # Limit to avoid prompt bloat
                compliance_text += f"- \"{phrase}\"\n"

        return prompt + compliance_text

    @llm_cache.async_cached(ttl=LLMCacheService.TTL_MEDIUM, prefix="blog:social")
    async def generate_social_content(
        self,
        blog_content: str,
        blog_title: str,
        platforms: List[str] = None,
        voice_profile: Dict[str, Any] = None,
    ) -> Dict[str, str]:
        """
        Generate social media posts from blog content.
        Cached for 1 hour (same blog + platforms = same social posts).

        Args:
            blog_content: The blog post markdown
            blog_title: Title of the blog post
            platforms: List of platforms (linkedin, facebook, instagram, twitter)
            voice_profile: Voice/brand settings

        Returns:
            Dict mapping platform to post content
        """
        if not self.enabled:
            return {}

        platforms = platforms or ["linkedin", "facebook", "instagram"]

        platform_specs = []
        for platform in platforms:
            if platform in self.SOCIAL_FORMATS:
                spec = self.SOCIAL_FORMATS[platform]
                platform_specs.append(f"""
{platform.upper()}:
- Max length: {spec['max_length']} characters
- Style: {spec['style']}
- Hashtags: {spec['hashtags']}
- CTA style: {spec['cta']}""")

        prompt = f"""Create social media posts to promote this blog post.

BLOG TITLE: {blog_title}

BLOG CONTENT:
{blog_content[:2000]}

PLATFORM REQUIREMENTS:
{''.join(platform_specs)}

Respond with JSON:
{{
    "linkedin": "LinkedIn post content...",
    "facebook": "Facebook post content...",
    "instagram": "Instagram caption content..."
}}

Each post should:
1. Capture the key value of the blog
2. Include a hook that grabs attention
3. Be platform-appropriate in tone and format
4. Include relevant hashtags as specified
5. Have a clear call-to-action"""

        prompt = self._apply_voice_profile(prompt, voice_profile)

        try:
            response_text = await self._call_llm(prompt)
            return self._parse_social_response(response_text, platforms)
        except Exception as e:
            logger.error(f"Social content generation failed: {e}")
            return {}

    @llm_cache.async_cached(ttl=LLMCacheService.TTL_LONG, prefix="blog:topics")
    async def mine_topics_from_content(
        self,
        source_text: str,
        existing_topics: List[str] = None,
        count: int = 10,
        industry: str = "mortgage",
    ) -> List[Dict[str, Any]]:
        """
        Mine blog topic ideas from source content.
        Cached for 6 hours (same source should return consistent topics).

        Args:
            source_text: Source document text
            existing_topics: Topics to avoid duplicating
            count: Number of topics to generate
            industry: Industry context

        Returns:
            List of topic suggestions with metadata
        """
        if not self.enabled:
            return []

        existing = existing_topics or []
        existing_text = "\n".join(existing[:20]) if existing else "None"

        prompt = f"""Analyze this {industry} content and generate {count} unique blog topic ideas.

SOURCE CONTENT:
{source_text[:4000]}

EXISTING TOPICS (avoid duplicates):
{existing_text}

For each topic, provide:
1. A compelling title/topic
2. The best archetype (informative, story, data_driven, how_to, myth_busting)
3. A target keyword
4. A unique angle that differentiates it
5. Priority score (1-10, higher = more timely/valuable)

Respond with JSON:
{{
    "topics": [
        {{
            "topic": "Topic title here",
            "archetype": "informative",
            "keyword": "target keyword",
            "angle": "Unique angle description",
            "priority": 8,
            "source_excerpt": "Brief quote from source that inspired this"
        }}
    ]
}}

Focus on topics that would be valuable to {industry} consumers and position the writer as an authority."""

        try:
            response_text = await self._call_llm(prompt)
            return self._parse_topics_response(response_text)
        except Exception as e:
            logger.error(f"Topic mining failed: {e}")
            return []

    @llm_cache.async_cached(ttl=LLMCacheService.TTL_DAILY, prefix="blog:image")
    async def generate_image_prompt(
        self,
        blog_title: str,
        blog_excerpt: str,
        brand_style: str = "professional, modern",
    ) -> str:
        """Generate a detailed prompt for image generation.
        Cached for 24 hours (same title/excerpt = same prompt)."""
        if not self.enabled:
            return ""

        prompt = f"""Create a detailed image generation prompt for a blog header image.

BLOG TITLE: {blog_title}
BLOG EXCERPT: {blog_excerpt}
BRAND STYLE: {brand_style}

The image should:
1. Be appropriate for a mortgage/real estate professional blog
2. Convey the theme without showing specific people's faces
3. Use the brand style guidelines
4. Work well as a 16:9 header image

Respond with just the image prompt text, no explanation."""

        try:
            return await self._call_llm(prompt, max_tokens=300)
        except Exception as e:
            logger.error(f"Image prompt generation failed: {e}")
            return "Professional mortgage and home finance concept, modern clean design, blue and white color scheme"

    async def _call_llm(
        self,
        prompt: str,
        max_tokens: int = 4000,
        model: str = None,
    ) -> str:
        """Call the LLM API."""
        model = model or DEFAULT_MODEL

        if ANTHROPIC_API_KEY and ("claude" in model.lower() or not OPENAI_API_KEY):
            return await self._call_anthropic(prompt, max_tokens, model)
        elif OPENAI_API_KEY:
            return await self._call_openai(prompt, max_tokens)
        else:
            raise Exception("No LLM API available")

    async def _call_anthropic(
        self,
        prompt: str,
        max_tokens: int,
        model: str,
    ) -> str:
        """Call Anthropic Claude API."""
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": max_tokens,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )

            if response.status_code != 200:
                error_detail = response.text[:500] if response.text else "No response body"
                logger.error(f"Anthropic API error {response.status_code}: {error_detail}")
                raise Exception(f"Anthropic API error: {response.status_code} - {error_detail}")

            result = response.json()
            return result["content"][0]["text"]

    async def _call_openai(
        self,
        prompt: str,
        max_tokens: int,
    ) -> str:
        """Call OpenAI API."""
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4-turbo-preview",
                    "max_tokens": max_tokens,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )

            if response.status_code != 200:
                error_detail = response.text[:500] if response.text else "No response body"
                logger.error(f"OpenAI API error {response.status_code}: {error_detail}")
                raise Exception(f"OpenAI API error: {response.status_code} - {error_detail}")

            result = response.json()
            return result["choices"][0]["message"]["content"]

    def _parse_blog_response(self, response_text: str) -> ContentGenerationResult:
        """Parse the blog generation response."""
        try:
            # Extract JSON from response
            json_text = response_text
            if "```json" in json_text:
                json_text = json_text.split("```json")[1].split("```")[0]
            elif "```" in json_text:
                json_text = json_text.split("```")[1].split("```")[0]

            json_text = json_text.strip()

            # Clean control characters that break JSON parsing
            # Replace carriage returns
            json_text = json_text.replace('\r\n', '\\n').replace('\r', '\\n')

            # Handle unescaped newlines within JSON string values
            # This is tricky - we need to escape newlines inside strings but not the JSON structure
            def escape_newlines_in_strings(match):
                return match.group(0).replace('\n', '\\n')
            json_text = re.sub(r'"(?:[^"\\]|\\.)*"', escape_newlines_in_strings, json_text, flags=re.DOTALL)

            data = json.loads(json_text)

            return ContentGenerationResult(
                success=True,
                title=data.get("title", ""),
                slug=data.get("slug", self._generate_slug(data.get("title", ""))),
                blog_md=data.get("blog_md", "").replace('\\n', '\n'),  # Convert back to actual newlines
                blog_html="",  # Will be converted after
                image_prompt=data.get("image_prompt", ""),
                metadata={
                    "meta_description": data.get("meta_description", ""),
                    "excerpt": data.get("excerpt", ""),
                    "estimated_read_time": data.get("estimated_read_time", 4),
                    "primary_keyword": data.get("primary_keyword", ""),
                    "secondary_keywords": data.get("secondary_keywords", []),
                },
            )
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse blog response: {e}")
            logger.debug(f"Response preview: {response_text[:500]}")
            return ContentGenerationResult(
                success=False,
                error=f"Failed to parse response: {e}"
            )

    def _parse_social_response(
        self,
        response_text: str,
        platforms: List[str]
    ) -> Dict[str, str]:
        """Parse the social content response."""
        try:
            json_text = response_text

            # Try to extract JSON from code blocks
            if "```json" in json_text:
                json_text = json_text.split("```json")[1].split("```")[0]
            elif "```" in json_text:
                json_text = json_text.split("```")[1].split("```")[0]

            # Try to find JSON object in the text
            json_text = json_text.strip()
            if not json_text.startswith("{"):
                # Try to find the first { and last }
                start = json_text.find("{")
                end = json_text.rfind("}") + 1
                if start >= 0 and end > start:
                    json_text = json_text[start:end]

            # Clean up control characters that break JSON parsing
            # Replace actual newlines within strings with \n escape
            json_text = json_text.replace('\r\n', '\\n').replace('\r', '\\n')
            # Handle unescaped newlines in JSON string values
            import re
            # This regex finds newlines that are inside JSON strings and escapes them
            def escape_newlines_in_strings(match):
                return match.group(0).replace('\n', '\\n')
            json_text = re.sub(r'"[^"]*"', escape_newlines_in_strings, json_text)

            data = json.loads(json_text)
            return {p: data.get(p, "") for p in platforms if p in data}
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse social response: {e}")
            # Fallback: try to extract content manually
            result = {}
            for platform in platforms:
                # Try to find "platform": "content" pattern
                pattern = rf'"{platform}"\s*:\s*"((?:[^"\\]|\\.)*)"'
                match = re.search(pattern, response_text, re.DOTALL)
                if match:
                    result[platform] = match.group(1).replace('\\n', '\n').replace('\\"', '"')
            if result:
                logger.info(f"Recovered social content via regex for {list(result.keys())}")
                return result
            return {}

    def _parse_topics_response(self, response_text: str) -> List[Dict[str, Any]]:
        """Parse the topic mining response."""
        try:
            json_text = response_text
            if "```json" in json_text:
                json_text = json_text.split("```json")[1].split("```")[0]
            elif "```" in json_text:
                json_text = json_text.split("```")[1].split("```")[0]

            data = json.loads(json_text.strip())
            return data.get("topics", [])
        except json.JSONDecodeError:
            logger.error("Failed to parse topics response")
            return []

    def _generate_slug(self, title: str) -> str:
        """Generate a URL-friendly slug from title."""
        if not title:
            return ""
        slug = title.lower()
        slug = re.sub(r'[^\w\s-]', '', slug)
        slug = re.sub(r'[-\s]+', '-', slug)
        return slug.strip('-')[:100]

    def _markdown_to_html(self, markdown_text: str) -> str:
        """Convert markdown to HTML."""
        try:
            import markdown
            return markdown.markdown(
                markdown_text,
                extensions=['tables', 'fenced_code', 'toc']
            )
        except ImportError:
            # Basic conversion if markdown package not available
            html = markdown_text
            # Headers
            html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
            html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
            html = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)
            # Bold and italic
            html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
            html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)
            # Paragraphs
            html = re.sub(r'\n\n', '</p><p>', html)
            html = f'<p>{html}</p>'
            return html


# Create singleton instance
blog_llm_service = BlogLLMService()
