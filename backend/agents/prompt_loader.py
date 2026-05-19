#!/usr/bin/env python3
"""
Prompt Loader - Dynamically loads prompt sections based on context.

This module provides intelligent loading of prompt sections with:
- Context-aware section selection
- Automatic dependency resolution
- LRU caching for performance
- Multiple preset contexts
"""

import os
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set, Any
from functools import lru_cache
from enum import Enum


def _next_semver(current: str) -> str:
    """Bump the minor segment of a semver string."""
    try:
        parts = [int(p) for p in current.split(".")]
        while len(parts) < 3:
            parts.append(0)
        parts[1] += 1
        parts[2] = 0
        return ".".join(str(p) for p in parts[:3])
    except Exception:  # noqa: BLE001
        return "1.0.0"


class Priority(str, Enum):
    """Section priority levels."""
    CORE = "core"
    CONDITIONAL = "conditional"
    OPTIONAL = "optional"


@dataclass
class LoadContext:
    """Context for determining which sections to load."""
    domain: Optional[str] = None          # e.g., "mortgage", "telephony"
    needs_tools: bool = False             # Load tool-related sections
    needs_memory: bool = False            # Load memory/context sections
    needs_search: bool = False            # Load search capability sections
    needs_agent: bool = False             # Load agent orchestration sections
    tags: List[str] = field(default_factory=list)  # Additional capability tags
    include_optional: bool = False        # Include optional sections
    max_chars: Optional[int] = None       # Maximum character limit

    def to_cache_key(self) -> str:
        """Generate a cache key for this context."""
        parts = [
            f"domain:{self.domain or 'none'}",
            f"tools:{self.needs_tools}",
            f"memory:{self.needs_memory}",
            f"search:{self.needs_search}",
            f"agent:{self.needs_agent}",
            f"tags:{','.join(sorted(self.tags))}",
            f"optional:{self.include_optional}",
            f"max:{self.max_chars or 'none'}"
        ]
        return '|'.join(parts)


class ContextPresets:
    """Pre-defined context configurations for common use cases."""

    @staticmethod
    def minimal() -> LoadContext:
        """Minimal context - only core identity and safety."""
        return LoadContext(
            needs_tools=False,
            needs_memory=False,
            needs_search=False,
            tags=['identity', 'safety']
        )

    @staticmethod
    def conversational() -> LoadContext:
        """Conversational context - for chat interactions."""
        return LoadContext(
            needs_tools=False,
            needs_memory=True,
            needs_search=False,
            tags=['identity', 'safety', 'communication']
        )

    @staticmethod
    def mortgage_crm() -> LoadContext:
        """Mortgage CRM context - full domain functionality."""
        return LoadContext(
            domain="mortgage",
            needs_tools=True,
            needs_memory=True,
            needs_search=False,
            tags=['identity', 'safety', 'domain', 'workflow']
        )

    @staticmethod
    def tool_use() -> LoadContext:
        """Tool use context - for API and tool interactions."""
        return LoadContext(
            needs_tools=True,
            needs_memory=True,
            needs_search=True,
            tags=['identity', 'safety', 'tools']
        )

    @staticmethod
    def agent_orchestration() -> LoadContext:
        """Agent orchestration context - for multi-agent coordination."""
        return LoadContext(
            needs_tools=True,
            needs_memory=True,
            needs_agent=True,
            tags=['identity', 'safety', 'agent', 'workflow']
        )

    @staticmethod
    def full() -> LoadContext:
        """Full context - load everything."""
        return LoadContext(
            needs_tools=True,
            needs_memory=True,
            needs_search=True,
            needs_agent=True,
            include_optional=True,
            tags=['identity', 'safety', 'tools', 'memory', 'search',
                  'domain', 'agent', 'communication', 'workflow']
        )


class PerenniaContexts:
    """Context presets specifically for Perennia AI agents."""

    @staticmethod
    def receptionist() -> LoadContext:
        """AI Receptionist - voice interactions, greeting, routing."""
        return LoadContext(
            domain="voice",
            needs_tools=True,  # calendar, CRM lookups
            needs_memory=True,
            needs_agent=True,
            tags=['identity', 'communication', 'agent', 'workflow', 'domain']
        )

    @staticmethod
    def pipeline_analyst() -> LoadContext:
        """Pipeline analysis - data queries, reasoning, metrics."""
        return LoadContext(
            domain="analytics",
            needs_tools=True,  # data queries
            needs_memory=True,
            tags=['identity', 'tools', 'domain', 'workflow', 'search']
        )

    @staticmethod
    def loan_processor() -> LoadContext:
        """Loan processing - full CRM, compliance, documents."""
        return LoadContext(
            domain="mortgage",
            needs_tools=True,
            needs_memory=True,
            needs_search=True,
            tags=['identity', 'tools', 'domain', 'workflow', 'communication']
        )

    @staticmethod
    def lead_manager() -> LoadContext:
        """Lead management - CRM, follow-up, scoring, outreach."""
        return LoadContext(
            domain="leads",
            needs_tools=True,
            needs_memory=True,
            tags=['identity', 'tools', 'domain', 'workflow', 'communication']
        )

    @staticmethod
    def email_intelligence() -> LoadContext:
        """Email processing - parsing, sentiment, routing."""
        return LoadContext(
            domain="email",
            needs_tools=False,  # usually just parsing
            needs_memory=False,
            tags=['identity', 'communication', 'domain']
        )

    @staticmethod
    def daily_briefing() -> LoadContext:
        """Daily briefing mode - lead coaching, priorities."""
        return LoadContext(
            domain="coaching",
            needs_tools=True,
            needs_memory=True,
            tags=['identity', 'tools', 'domain', 'workflow', 'communication']
        )

    @staticmethod
    def market_intelligence() -> LoadContext:
        """Market intelligence - rates, lock/float, trends."""
        return LoadContext(
            domain="market",
            needs_tools=True,
            needs_search=True,
            tags=['identity', 'tools', 'domain', 'search']
        )

    @staticmethod
    def general() -> LoadContext:
        """General purpose - balanced context for mixed queries."""
        return LoadContext(
            domain="mortgage",
            needs_tools=True,
            needs_memory=True,
            tags=['identity', 'tools', 'domain', 'communication', 'workflow']
        )


@dataclass
class LoadedPrompt:
    """Result of loading a prompt."""
    content: str
    sections_loaded: List[str]
    total_chars: int
    total_sections: int
    cache_key: str
    # Wave 5 — D3 audit: callers can rely on this to know which versioned
    # prompt they got. Format: "<prompt_id>@<semver>" (e.g. "ctx-mortgage@1.0.0").
    # Optional; defaults to None for backward compatibility.
    version_stamp: Optional[str] = None


class PromptLoader:
    """Loads prompt sections dynamically based on context."""

    def __init__(self, prompts_dir: str):
        """
        Initialize the loader.

        Args:
            prompts_dir: Directory containing split prompt files
        """
        self.prompts_dir = Path(prompts_dir)
        self.manifest = self._load_manifest()
        self._section_cache: Dict[str, str] = {}

    def _load_manifest(self) -> Dict[str, Any]:
        """Load the manifest.json file."""
        manifest_path = self.prompts_dir / 'manifest.json'
        if not manifest_path.exists():
            raise FileNotFoundError(f"Manifest not found: {manifest_path}")

        with open(manifest_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _load_section_content(self, section_id: str) -> Optional[str]:
        """Load content for a specific section."""
        if section_id in self._section_cache:
            return self._section_cache[section_id]

        # Find section in manifest
        section_meta = None
        for s in self.manifest.get('sections', []):
            if s['id'] == section_id:
                section_meta = s
                break

        if not section_meta:
            return None

        # Load from file
        file_path = self.prompts_dir / section_meta['file']
        if not file_path.exists():
            return None

        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        self._section_cache[section_id] = content
        return content

    def _get_sections_for_context(self, context: LoadContext) -> List[Dict]:
        """Determine which sections to load based on context."""
        selected = []
        all_sections = self.manifest.get('sections', [])

        for section in all_sections:
            priority = section.get('priority', 'conditional')
            capabilities = set(section.get('capabilities', []))

            # Always include core sections
            if priority == Priority.CORE.value:
                selected.append(section)
                continue

            # Skip optional unless explicitly requested
            if priority == Priority.OPTIONAL.value and not context.include_optional:
                continue

            # Check capability matches
            should_include = False

            # Check context flags
            if context.needs_tools and 'tools' in capabilities:
                should_include = True
            if context.needs_memory and 'memory' in capabilities:
                should_include = True
            if context.needs_search and 'search' in capabilities:
                should_include = True
            if context.needs_agent and 'agent' in capabilities:
                should_include = True

            # Check domain match
            if context.domain and 'domain' in capabilities:
                # Check if section content relates to the domain
                should_include = True

            # Check tag matches
            if context.tags:
                if capabilities.intersection(set(context.tags)):
                    should_include = True

            if should_include:
                selected.append(section)

        return selected

    def _resolve_dependencies(self, sections: List[Dict]) -> List[Dict]:
        """Resolve dependencies and ensure all required sections are included."""
        section_ids = {s['id'] for s in sections}
        all_sections_map = {s['id']: s for s in self.manifest.get('sections', [])}

        # Keep adding dependencies until no new ones found
        changed = True
        while changed:
            changed = False
            new_ids = set()

            for section in sections:
                for dep_id in section.get('dependencies', []):
                    if dep_id not in section_ids and dep_id in all_sections_map:
                        new_ids.add(dep_id)

            if new_ids:
                changed = True
                for dep_id in new_ids:
                    sections.append(all_sections_map[dep_id])
                    section_ids.add(dep_id)

        return sections

    def _sort_sections(self, sections: List[Dict]) -> List[Dict]:
        """Sort sections by priority (core first) then by original order."""
        priority_order = {
            Priority.CORE.value: 0,
            Priority.CONDITIONAL.value: 1,
            Priority.OPTIONAL.value: 2
        }

        # Get original indices from manifest
        manifest_order = {s['id']: i for i, s in enumerate(self.manifest.get('sections', []))}

        return sorted(sections, key=lambda s: (
            priority_order.get(s.get('priority', 'conditional'), 1),
            manifest_order.get(s['id'], 999)
        ))

    def load_prompt(self, context: LoadContext) -> LoadedPrompt:
        """
        Load prompt sections based on context.

        Args:
            context: LoadContext specifying what to load

        Returns:
            LoadedPrompt with combined content and metadata
        """
        # Get sections for this context
        sections = self._get_sections_for_context(context)

        # Resolve dependencies
        sections = self._resolve_dependencies(sections)

        # Remove duplicates while preserving order
        seen = set()
        unique_sections = []
        for s in sections:
            if s['id'] not in seen:
                seen.add(s['id'])
                unique_sections.append(s)
        sections = unique_sections

        # Sort sections
        sections = self._sort_sections(sections)

        # Load content
        content_parts = []
        section_ids = []
        total_chars = 0

        for section in sections:
            section_content = self._load_section_content(section['id'])
            if section_content:
                # Check max chars limit
                if context.max_chars:
                    if total_chars + len(section_content) > context.max_chars:
                        break

                content_parts.append(section_content)
                section_ids.append(section['id'])
                total_chars += len(section_content)

        # Combine content
        combined_content = '\n\n'.join(content_parts)

        # Wave 5 — register/version this prompt. Idempotent on content hash.
        version_stamp = self._register_versioned(context, combined_content)

        return LoadedPrompt(
            content=combined_content,
            sections_loaded=section_ids,
            total_chars=total_chars,
            total_sections=len(section_ids),
            cache_key=context.to_cache_key(),
            version_stamp=version_stamp,
        )

    def _register_versioned(self, context: LoadContext, content: str) -> Optional[str]:
        """Best-effort register-on-load. Never raises into the caller."""
        try:
            from agents.orchestration.prompt_registry import get_default_registry

            registry = get_default_registry()
            # prompt_id is derived from the context cache key prefix so that
            # logically distinct contexts get separate histories.
            prompt_id = "ctx:" + context.to_cache_key()
            existing = registry.get(prompt_id, None)
            if existing is None:
                rec = registry.register(prompt_id, "1.0.0", content, metadata={
                    "domain": context.domain,
                    "tags": list(context.tags or []),
                })
                return f"{prompt_id}@{rec['version']}"
            # Idempotent: if hash matches, register() returns the same record.
            same = registry.register(
                prompt_id,
                _next_semver(existing.get("version", "1.0.0")),
                content,
                metadata={"domain": context.domain, "tags": list(context.tags or [])},
            )
            return f"{prompt_id}@{same['version']}"
        except Exception as _exc:
            # Never break prompt loading because of versioning bookkeeping.
            return None

    def get_section(self, section_id: str) -> Optional[str]:
        """Get a specific section by ID."""
        return self._load_section_content(section_id)

    def list_sections(self) -> List[Dict]:
        """List all available sections with metadata."""
        return self.manifest.get('sections', [])

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the prompt structure."""
        sections = self.manifest.get('sections', [])

        by_priority = {}
        by_capability = {}
        total_chars = 0

        for section in sections:
            # Count by priority
            priority = section.get('priority', 'conditional')
            by_priority[priority] = by_priority.get(priority, 0) + 1

            # Count by capability
            for cap in section.get('capabilities', []):
                by_capability[cap] = by_capability.get(cap, 0) + 1

            # Total chars
            total_chars += section.get('char_count', 0)

        return {
            'total_sections': len(sections),
            'total_characters': total_chars,
            'by_priority': by_priority,
            'by_capability': by_capability,
            'cached_sections': len(self._section_cache)
        }


class CachedPromptLoader:
    """Prompt loader with LRU caching for performance."""

    def __init__(self, prompts_dir: str, cache_size: int = 32):
        """
        Initialize the cached loader.

        Args:
            prompts_dir: Directory containing split prompt files
            cache_size: Maximum number of cached prompts
        """
        self._loader = PromptLoader(prompts_dir)
        self._cache_size = cache_size
        self._cache: Dict[str, LoadedPrompt] = {}
        self._cache_hits = 0
        self._cache_misses = 0

    def load_prompt(self, context: LoadContext) -> LoadedPrompt:
        """Load prompt with caching."""
        cache_key = context.to_cache_key()

        if cache_key in self._cache:
            self._cache_hits += 1
            return self._cache[cache_key]

        self._cache_misses += 1
        result = self._loader.load_prompt(context)

        # Add to cache (simple LRU by removing oldest if full)
        if len(self._cache) >= self._cache_size:
            # Remove first (oldest) item
            first_key = next(iter(self._cache))
            del self._cache[first_key]

        self._cache[cache_key] = result
        return result

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total = self._cache_hits + self._cache_misses
        hit_rate = (self._cache_hits / total * 100) if total > 0 else 0

        return {
            'hits': self._cache_hits,
            'misses': self._cache_misses,
            'total_requests': total,
            'hit_rate': round(hit_rate, 1),
            'cached_prompts': len(self._cache),
            'max_cache_size': self._cache_size
        }

    def clear_cache(self):
        """Clear the prompt cache."""
        self._cache.clear()
        self._cache_hits = 0
        self._cache_misses = 0

    def get_stats(self) -> Dict[str, Any]:
        """Get combined statistics."""
        stats = self._loader.get_stats()
        stats['cache'] = self.get_cache_stats()
        return stats

    def list_sections(self) -> List[Dict]:
        """List all available sections."""
        return self._loader.list_sections()


def main():
    """Demo usage of the prompt loader."""
    import argparse

    parser = argparse.ArgumentParser(description='Load prompts dynamically')
    parser.add_argument('prompts_dir', help='Directory containing split prompts')
    parser.add_argument('--context', choices=['minimal', 'conversational', 'mortgage', 'tools', 'agent', 'full'],
                        default='conversational', help='Context preset to use')
    parser.add_argument('--stats', action='store_true', help='Show statistics')

    args = parser.parse_args()

    loader = CachedPromptLoader(args.prompts_dir)

    if args.stats:
        stats = loader.get_stats()
        print(json.dumps(stats, indent=2))
        return

    # Get context preset
    context_map = {
        'minimal': ContextPresets.minimal(),
        'conversational': ContextPresets.conversational(),
        'mortgage': ContextPresets.mortgage_crm(),
        'tools': ContextPresets.tool_use(),
        'agent': ContextPresets.agent_orchestration(),
        'full': ContextPresets.full()
    }

    context = context_map.get(args.context, ContextPresets.conversational())

    # Load prompt
    result = loader.load_prompt(context)

    print(f"Loaded {result.total_sections} sections ({result.total_chars:,} chars)")
    print(f"Sections: {', '.join(result.sections_loaded)}")
    print("\n--- Content Preview (first 500 chars) ---")
    print(result.content[:500] + "..." if len(result.content) > 500 else result.content)


if __name__ == '__main__':
    main()
