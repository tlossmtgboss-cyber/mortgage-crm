"""
Brand Voice Analyzer Service

Analyzes website content and sample text to extract brand voice characteristics:
- Tone analysis (formal/casual, authoritative/friendly, etc.)
- Vocabulary and sentence patterns
- Key phrases and brand values
- Generates system prompts for consistent content generation
"""

import os
import re
import json
import logging
import socket
import ipaddress
from urllib.parse import urlparse
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timezone
import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from models.content_marketing import ContentBrandVoice

_BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def _validate_url_for_ssrf(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("URL scheme must be http or https")
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL must have a valid hostname")
    if hostname.lower() in ("localhost", "0.0.0.0"):
        raise ValueError("Blocked hostname")
    try:
        addrinfos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        raise ValueError("Could not resolve hostname")
    for family, _type, _proto, _canonname, sockaddr in addrinfos:
        ip = ipaddress.ip_address(sockaddr[0])
        for network in _BLOCKED_NETWORKS:
            if ip in network:
                raise ValueError("Blocked IP address")
    return url

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


class BrandVoiceAnalyzerService:
    """
    Service for analyzing and extracting brand voice characteristics.

    Analyzes website content, blog posts, or sample text to create
    a brand voice profile that can be used for consistent content generation.
    """

    # Default model for analysis
    DEFAULT_MODEL = "claude-haiku-4-5-20251001"

    def __init__(self, db: Session):
        """Initialize with database session."""
        self.db = db
        self.enabled = bool(ANTHROPIC_API_KEY or OPENAI_API_KEY)
        if not self.enabled:
            logger.warning("No LLM API keys configured - voice analysis disabled")

    # =========================================================================
    # Website Content Fetching
    # =========================================================================

    async def fetch_website_content(
        self,
        url: str,
        max_pages: int = 5
    ) -> Dict[str, Any]:
        """
        Fetch and extract text content from a website.

        Args:
            url: Website URL to analyze
            max_pages: Maximum pages to crawl

        Returns:
            Dict with extracted content and metadata
        """
        try:
            _validate_url_for_ssrf(url)
        except ValueError:
            return {"success": False, "error": "Invalid or blocked URL"}

        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(url, headers={
                    "User-Agent": "Mozilla/5.0 (compatible; BrandVoiceAnalyzer/1.0)"
                })

                if response.status_code != 200:
                    return {
                        "success": False,
                        "error": f"Failed to fetch URL: {response.status_code}"
                    }

                soup = BeautifulSoup(response.text, "html.parser")

                # Remove script and style elements
                for element in soup(["script", "style", "nav", "footer", "header"]):
                    element.decompose()

                # Extract text content
                text_content = self._extract_text_content(soup)

                # Extract metadata
                title = soup.title.string if soup.title else ""
                meta_description = ""
                meta_tag = soup.find("meta", attrs={"name": "description"})
                if meta_tag:
                    meta_description = meta_tag.get("content", "")

                # Find additional pages to analyze
                links = self._find_content_pages(soup, url)

                return {
                    "success": True,
                    "url": url,
                    "title": title,
                    "meta_description": meta_description,
                    "text_content": text_content[:10000],  # Limit content size
                    "additional_links": links[:max_pages - 1],
                    "word_count": len(text_content.split()),
                }

        except Exception as e:
            logger.error(f"Error fetching website content: {e}")
            return {
                "success": False,
                "error": "Internal server error"
            }

    def _extract_text_content(self, soup: BeautifulSoup) -> str:
        """Extract meaningful text content from HTML."""
        # Prioritize main content areas
        main_content = (
            soup.find("main") or
            soup.find("article") or
            soup.find(class_=re.compile(r"(content|main|post|article)", re.I)) or
            soup.body
        )

        if not main_content:
            return ""

        # Get text and clean it up
        text = main_content.get_text(separator="\n", strip=True)

        # Clean up whitespace
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        return "\n".join(lines)

    def _find_content_pages(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        """Find additional content pages to analyze."""
        from urllib.parse import urljoin, urlparse

        content_pages = []
        base_domain = urlparse(base_url).netloc

        # Look for blog posts, about pages, service pages
        content_patterns = [
            r"/blog/", r"/posts/", r"/about", r"/services",
            r"/team", r"/our-story", r"/mission"
        ]

        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            full_url = urljoin(base_url, href)
            parsed = urlparse(full_url)

            # Stay on same domain
            if parsed.netloc != base_domain:
                continue

            # Check for content pages
            for pattern in content_patterns:
                if re.search(pattern, full_url, re.I):
                    if full_url not in content_pages:
                        content_pages.append(full_url)
                    break

        return content_pages

    # =========================================================================
    # Voice Analysis
    # =========================================================================

    async def analyze_voice(
        self,
        content: str,
        source_url: Optional[str] = None,
        industry: str = "mortgage lending"
    ) -> Dict[str, Any]:
        """
        Analyze content to extract brand voice characteristics.

        Args:
            content: Text content to analyze
            source_url: Optional source URL for reference
            industry: Industry context for analysis

        Returns:
            Dict with voice analysis results
        """
        if not self.enabled:
            return {"success": False, "error": "LLM service not configured"}

        if not content or len(content) < 100:
            return {"success": False, "error": "Insufficient content for analysis"}

        prompt = f"""Analyze this {industry} content to extract brand voice characteristics.

CONTENT TO ANALYZE:
{content[:5000]}

Analyze the voice and writing style, then respond with JSON:
{{
    "tone_analysis": {{
        "formal_casual": 0.5,  // 0=very formal, 1=very casual
        "authoritative_friendly": 0.5,  // 0=very authoritative, 1=very friendly
        "technical_simple": 0.5,  // 0=very technical, 1=very simple
        "serious_playful": 0.5  // 0=very serious, 1=very playful
    }},
    "vocabulary_level": "intermediate",  // basic, intermediate, advanced
    "sentence_structure": "Description of typical sentence patterns",
    "key_phrases": ["phrase 1", "phrase 2"],  // Distinctive phrases used
    "avoided_phrases": ["phrase to avoid"],  // Language patterns to avoid
    "brand_values": ["value 1", "value 2"],  // Core values expressed
    "target_audience": "Description of apparent target audience",
    "unique_characteristics": ["characteristic 1", "characteristic 2"],
    "style_summary": "Brief summary of the overall voice style",
    "analysis_confidence": 0.8  // 0-1 confidence in analysis
}}

Provide accurate analysis based solely on the content provided. Be specific about tone characteristics and provide numeric values between 0 and 1."""

        try:
            response_text = await self._call_llm(prompt)
            analysis = self._parse_voice_analysis(response_text)
            analysis["source_url"] = source_url
            analysis["analyzed_at"] = datetime.now(timezone.utc).isoformat()
            analysis["content_length"] = len(content)
            return analysis

        except Exception as e:
            logger.error(f"Voice analysis failed: {e}")
            return {"success": False, "error": "Internal server error"}

    def _parse_voice_analysis(self, response_text: str) -> Dict[str, Any]:
        """Parse voice analysis response."""
        try:
            # Extract JSON from response
            json_text = response_text
            if "```json" in json_text:
                json_text = json_text.split("```json")[1].split("```")[0]
            elif "```" in json_text:
                json_text = json_text.split("```")[1].split("```")[0]

            data = json.loads(json_text.strip())
            data["success"] = True
            return data

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse voice analysis: {e}")
            return {"success": False, "error": "Parse error"}

    # =========================================================================
    # System Prompt Generation
    # =========================================================================

    async def generate_system_prompt(
        self,
        voice_analysis: Dict[str, Any],
        industry: str = "mortgage lending"
    ) -> str:
        """
        Generate a system prompt for content generation based on voice analysis.

        Args:
            voice_analysis: Results from analyze_voice()
            industry: Industry context

        Returns:
            System prompt string for LLM content generation
        """
        if not self.enabled:
            return self._generate_default_prompt(industry)

        tone = voice_analysis.get("tone_analysis", {})
        key_phrases = voice_analysis.get("key_phrases", [])
        brand_values = voice_analysis.get("brand_values", [])
        vocabulary = voice_analysis.get("vocabulary_level", "intermediate")
        target_audience = voice_analysis.get("target_audience", "")
        style_summary = voice_analysis.get("style_summary", "")

        prompt = f"""Create a concise system prompt for an AI content writer that captures this brand voice.

VOICE CHARACTERISTICS:
- Tone: {self._describe_tone(tone)}
- Vocabulary Level: {vocabulary}
- Style Summary: {style_summary}
- Target Audience: {target_audience}
- Key Phrases to Use: {', '.join(key_phrases[:10])}
- Brand Values: {', '.join(brand_values[:5])}
- Industry: {industry}

Generate a system prompt (200-400 words) that instructs an AI to write content matching this voice. Include:
1. Overall tone and personality
2. Language and vocabulary guidelines
3. Key phrases to incorporate naturally
4. Topics and angles to emphasize
5. What to avoid

Respond with just the system prompt text, no explanation."""

        try:
            system_prompt = await self._call_llm(prompt, max_tokens=800)
            return system_prompt.strip()
        except Exception as e:
            logger.error(f"System prompt generation failed: {e}")
            return self._generate_default_prompt(industry)

    def _describe_tone(self, tone: Dict[str, float]) -> str:
        """Convert tone scores to description."""
        descriptions = []

        formal_casual = tone.get("formal_casual", 0.5)
        if formal_casual < 0.3:
            descriptions.append("very formal")
        elif formal_casual < 0.45:
            descriptions.append("somewhat formal")
        elif formal_casual > 0.7:
            descriptions.append("casual")
        elif formal_casual > 0.55:
            descriptions.append("conversational")

        authoritative_friendly = tone.get("authoritative_friendly", 0.5)
        if authoritative_friendly < 0.3:
            descriptions.append("authoritative")
        elif authoritative_friendly > 0.7:
            descriptions.append("warm and friendly")
        elif authoritative_friendly > 0.55:
            descriptions.append("approachable")

        technical_simple = tone.get("technical_simple", 0.5)
        if technical_simple < 0.3:
            descriptions.append("technical")
        elif technical_simple > 0.7:
            descriptions.append("simple and clear")

        return ", ".join(descriptions) if descriptions else "balanced"

    def _generate_default_prompt(self, industry: str) -> str:
        """Generate a default system prompt."""
        return f"""You are a professional content writer for the {industry} industry.

VOICE GUIDELINES:
- Tone: Professional yet approachable, building trust and credibility
- Language: Clear and accessible, avoiding excessive jargon
- Style: Informative and helpful, focused on educating the reader
- Personality: Knowledgeable expert who genuinely wants to help

WRITING PRINCIPLES:
1. Lead with value - every piece should help the reader
2. Use concrete examples and relatable scenarios
3. Break down complex topics into digestible sections
4. Include actionable takeaways
5. Maintain compliance with industry regulations

AVOID:
- Overly salesy or pushy language
- Guaranteed outcomes or promises
- Technical jargon without explanation
- Condescending or patronizing tone"""

    # =========================================================================
    # Voice Profile CRUD
    # =========================================================================

    async def create_voice_profile(
        self,
        name: str,
        source_url: Optional[str] = None,
        source_content: Optional[str] = None,
        user_id: Optional[int] = None,
        organization_id: int = 1,
        is_default: bool = False
    ) -> Dict[str, Any]:
        """
        Create a new brand voice profile from URL or content.

        Args:
            name: Profile name
            source_url: Website URL to analyze
            source_content: Sample content to analyze (if no URL)
            user_id: Owner user ID
            organization_id: Organization ID
            is_default: Set as default profile

        Returns:
            Created voice profile data
        """
        try:
            # Get content to analyze
            if source_url:
                fetch_result = await self.fetch_website_content(source_url)
                if not fetch_result.get("success"):
                    return fetch_result
                content = fetch_result.get("text_content", "")
            elif source_content:
                content = source_content
            else:
                return {"success": False, "error": "Either source_url or source_content required"}

            # Analyze the voice
            analysis = await self.analyze_voice(content, source_url)
            if not analysis.get("success"):
                return analysis

            # Generate system prompt
            system_prompt = await self.generate_system_prompt(analysis)

            # Extract tone scores
            tone = analysis.get("tone_analysis", {})

            # If setting as default, unset other defaults
            if is_default:
                self.db.query(ContentBrandVoice).filter(
                    ContentBrandVoice.organization_id == organization_id,
                    ContentBrandVoice.is_default == True
                ).update({"is_default": False})

            # Create the profile
            profile = ContentBrandVoice(
                user_id=user_id,
                organization_id=organization_id,
                name=name,
                source_url=source_url,
                source_content=content[:5000] if source_content else None,

                # Tone characteristics
                tone_formal_casual=tone.get("formal_casual", 0.5),
                tone_authoritative_friendly=tone.get("authoritative_friendly", 0.5),
                tone_technical_simple=tone.get("technical_simple", 0.5),
                tone_serious_playful=tone.get("serious_playful", 0.5),

                vocabulary_level=analysis.get("vocabulary_level", "intermediate"),
                sentence_structure=analysis.get("sentence_structure"),
                key_phrases=analysis.get("key_phrases", []),
                avoided_phrases=analysis.get("avoided_phrases", []),
                brand_values=analysis.get("brand_values", []),
                target_audience=analysis.get("target_audience"),
                industry_context="mortgage lending",

                system_prompt=system_prompt,
                style_examples=[],
                analysis_confidence=analysis.get("analysis_confidence", 0.5),

                is_active=True,
                is_default=is_default,
            )

            self.db.add(profile)
            self.db.commit()
            self.db.refresh(profile)

            return {
                "success": True,
                "profile_id": profile.id,
                "name": profile.name,
                "analysis": analysis,
                "system_prompt": system_prompt,
            }

        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to create voice profile: {e}")
            return {"success": False, "error": "Internal server error"}

    def get_voice_profile(self, profile_id: str) -> Optional[ContentBrandVoice]:
        """Get a voice profile by ID."""
        return self.db.query(ContentBrandVoice).filter(
            ContentBrandVoice.id == profile_id
        ).first()

    def get_default_voice_profile(
        self,
        organization_id: int = 1
    ) -> Optional[ContentBrandVoice]:
        """Get the default voice profile for an organization."""
        return self.db.query(ContentBrandVoice).filter(
            ContentBrandVoice.organization_id == organization_id,
            ContentBrandVoice.is_default == True,
            ContentBrandVoice.is_active == True
        ).first()

    def list_voice_profiles(
        self,
        organization_id: int = 1,
        active_only: bool = True
    ) -> List[ContentBrandVoice]:
        """List all voice profiles for an organization."""
        query = self.db.query(ContentBrandVoice).filter(
            ContentBrandVoice.organization_id == organization_id
        )

        if active_only:
            query = query.filter(ContentBrandVoice.is_active == True)

        return query.order_by(ContentBrandVoice.created_at.desc()).all()

    def update_voice_profile(
        self,
        profile_id: str,
        updates: Dict[str, Any]
    ) -> Optional[ContentBrandVoice]:
        """Update a voice profile."""
        profile = self.get_voice_profile(profile_id)
        if not profile:
            return None

        # Allowed update fields
        allowed_fields = [
            "name", "tone_formal_casual", "tone_authoritative_friendly",
            "tone_technical_simple", "tone_serious_playful",
            "vocabulary_level", "key_phrases", "avoided_phrases",
            "brand_values", "target_audience", "system_prompt",
            "is_active", "is_default"
        ]

        for field, value in updates.items():
            if field in allowed_fields:
                setattr(profile, field, value)

        # Handle default flag
        if updates.get("is_default"):
            self.db.query(ContentBrandVoice).filter(
                ContentBrandVoice.organization_id == profile.organization_id,
                ContentBrandVoice.id != profile_id,
                ContentBrandVoice.is_default == True
            ).update({"is_default": False})

        self.db.commit()
        self.db.refresh(profile)
        return profile

    def delete_voice_profile(self, profile_id: str) -> bool:
        """Delete (soft) a voice profile."""
        profile = self.get_voice_profile(profile_id)
        if not profile:
            return False

        profile.is_active = False
        self.db.commit()
        return True

    # =========================================================================
    # Voice Profile Export/Import
    # =========================================================================

    def export_voice_profile(self, profile_id: str) -> Optional[Dict[str, Any]]:
        """Export a voice profile as JSON."""
        profile = self.get_voice_profile(profile_id)
        if not profile:
            return None

        return {
            "name": profile.name,
            "tone": {
                "formal_casual": profile.tone_formal_casual,
                "authoritative_friendly": profile.tone_authoritative_friendly,
                "technical_simple": profile.tone_technical_simple,
                "serious_playful": profile.tone_serious_playful,
            },
            "vocabulary_level": profile.vocabulary_level,
            "sentence_structure": profile.sentence_structure,
            "key_phrases": profile.key_phrases,
            "avoided_phrases": profile.avoided_phrases,
            "brand_values": profile.brand_values,
            "target_audience": profile.target_audience,
            "industry_context": profile.industry_context,
            "system_prompt": profile.system_prompt,
            "exported_at": datetime.now(timezone.utc).isoformat(),
        }

    def get_voice_profile_for_llm(self, profile_id: str) -> Dict[str, Any]:
        """
        Get voice profile formatted for LLM integration.

        Returns format compatible with BlogLLMService._apply_voice_profile()
        """
        profile = self.get_voice_profile(profile_id)
        if not profile:
            return {}

        # Convert 0-1 scale to 0-100 for compatibility
        def scale_to_100(value):
            return int((value or 0.5) * 100)

        return {
            "sliders_json": {
                "professional_casual": scale_to_100(profile.tone_formal_casual),
                "bold_conservative": 50,  # Default
                "detailed_concise": 50,  # Default
                "formal_friendly": scale_to_100(profile.tone_authoritative_friendly),
                "technical_simple": scale_to_100(profile.tone_technical_simple),
            },
            "toggles_json": {
                "use_emojis": profile.tone_serious_playful and profile.tone_serious_playful > 0.6,
                "use_hashtags": True,
                "use_questions": True,
                "use_statistics": profile.tone_technical_simple and profile.tone_technical_simple < 0.4,
                "use_stories": profile.tone_authoritative_friendly and profile.tone_authoritative_friendly > 0.5,
            },
            "examples_json": {
                "sample_content": profile.source_content[:500] if profile.source_content else "",
            },
            "system_prompt": profile.system_prompt,
            "key_phrases": profile.key_phrases,
            "avoided_phrases": profile.avoided_phrases,
        }

    # =========================================================================
    # LLM Integration
    # =========================================================================

    async def _call_llm(
        self,
        prompt: str,
        max_tokens: int = 2000,
        model: str = None
    ) -> str:
        """Call the LLM API."""
        model = model or self.DEFAULT_MODEL

        if ANTHROPIC_API_KEY:
            return await self._call_anthropic(prompt, max_tokens, model)
        elif OPENAI_API_KEY:
            return await self._call_openai(prompt, max_tokens)
        else:
            raise Exception("No LLM API available")

    async def _call_anthropic(
        self,
        prompt: str,
        max_tokens: int,
        model: str
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
                raise Exception(f"Anthropic API error: {response.status_code}")

            result = response.json()
            return result["content"][0]["text"]

    async def _call_openai(
        self,
        prompt: str,
        max_tokens: int
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
                raise Exception(f"OpenAI API error: {response.status_code}")

            result = response.json()
            return result["choices"][0]["message"]["content"]
