#!/usr/bin/env python3
"""
Prompt Splitter - Analyzes and splits large CLAUDE.md files into modular components.

Usage:
    python prompt_splitter.py CLAUDE.md ./prompts

This will:
1. Analyze the CLAUDE.md file structure
2. Identify section boundaries and priorities
3. Split into modular files in ./prompts/
4. Generate a manifest.json with metadata
"""

import os
import re
import json
import hashlib
import argparse
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Set
from enum import Enum


class Priority(str, Enum):
    """Section priority levels."""
    CORE = "core"           # Always loaded
    CONDITIONAL = "conditional"  # Loaded based on context
    OPTIONAL = "optional"   # Rarely needed


class Capability(str, Enum):
    """Section capabilities/tags."""
    IDENTITY = "identity"
    SAFETY = "safety"
    TOOLS = "tools"
    MEMORY = "memory"
    SEARCH = "search"
    DOMAIN = "domain"
    AGENT = "agent"
    COMMUNICATION = "communication"
    WORKFLOW = "workflow"


@dataclass
class Section:
    """Represents a section of the prompt."""
    id: str
    title: str
    content: str
    priority: Priority
    capabilities: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    char_count: int = 0
    line_count: int = 0

    def __post_init__(self):
        self.char_count = len(self.content)
        self.line_count = self.content.count('\n') + 1


@dataclass
class SplitResult:
    """Result of splitting a prompt file."""
    sections: List[Section]
    total_chars: int
    total_sections: int
    by_priority: Dict[str, int]
    manifest_path: str


class PromptSplitter:
    """Splits large prompt files into modular components."""

    # Patterns for identifying section headers
    HEADER_PATTERNS = [
        (r'^#{1,2}\s+(.+)$', 1),           # ## Header or # Header
        (r'^={3,}\s*\n(.+)\n={3,}', 2),    # === Header ===
        (r'^-{3,}\s*\n(.+)\n-{3,}', 2),    # --- Header ---
    ]

    # Keywords for priority classification
    PRIORITY_KEYWORDS = {
        Priority.CORE: [
            'identity', 'core', 'fundamental', 'always', 'essential',
            'safety', 'security', 'important', 'critical', 'base'
        ],
        Priority.CONDITIONAL: [
            'tool', 'memory', 'search', 'domain', 'context',
            'conditional', 'when', 'if', 'agent', 'workflow'
        ],
        Priority.OPTIONAL: [
            'optional', 'advanced', 'rarely', 'special', 'edge',
            'deprecated', 'legacy', 'experimental'
        ]
    }

    # Keywords for capability tagging
    CAPABILITY_KEYWORDS = {
        Capability.IDENTITY: ['identity', 'who', 'role', 'personality', 'character'],
        Capability.SAFETY: ['safety', 'security', 'harm', 'ethics', 'boundaries'],
        Capability.TOOLS: ['tool', 'function', 'api', 'execute', 'call'],
        Capability.MEMORY: ['memory', 'context', 'history', 'remember', 'recall'],
        Capability.SEARCH: ['search', 'query', 'find', 'lookup', 'retrieve'],
        Capability.DOMAIN: ['mortgage', 'loan', 'crm', 'business', 'industry'],
        Capability.AGENT: ['agent', 'orchestrat', 'delegate', 'subprocess'],
        Capability.COMMUNICATION: ['communicate', 'respond', 'tone', 'style', 'format'],
        Capability.WORKFLOW: ['workflow', 'process', 'step', 'procedure', 'pipeline'],
    }

    # Reference patterns for dependency detection
    REFERENCE_PATTERNS = [
        r'refer\s+to\s+\[([^\]]+)\]',
        r'see\s+\[([^\]]+)\]',
        r'as\s+defined\s+in\s+\[([^\]]+)\]',
        r'from\s+\[([^\]]+)\]',
        r'uses?\s+\[([^\]]+)\]',
    ]

    def __init__(self, min_section_chars: int = 100):
        """
        Initialize the splitter.

        Args:
            min_section_chars: Minimum characters for a valid section
        """
        self.min_section_chars = min_section_chars

    def split_file(self, input_path: str, output_dir: str) -> SplitResult:
        """
        Split a prompt file into modular components.

        Args:
            input_path: Path to the CLAUDE.md file
            output_dir: Directory to write split files

        Returns:
            SplitResult with metadata about the split
        """
        # Read input file
        with open(input_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Parse sections
        sections = self._parse_sections(content)

        # Classify priorities
        sections = self._classify_priorities(sections)

        # Detect capabilities
        sections = self._detect_capabilities(sections)

        # Detect dependencies
        sections = self._detect_dependencies(sections)

        # Create output directory structure
        output_path = Path(output_dir)
        self._create_directory_structure(output_path)

        # Write sections to files
        self._write_sections(sections, output_path)

        # Generate manifest
        manifest_path = self._write_manifest(sections, output_path, input_path)

        # Calculate stats
        by_priority = {}
        for section in sections:
            priority = section.priority.value
            by_priority[priority] = by_priority.get(priority, 0) + 1

        return SplitResult(
            sections=sections,
            total_chars=sum(s.char_count for s in sections),
            total_sections=len(sections),
            by_priority=by_priority,
            manifest_path=manifest_path
        )

    def _parse_sections(self, content: str) -> List[Section]:
        """Parse content into sections based on headers."""
        sections = []
        lines = content.split('\n')

        current_section = None
        current_content = []
        current_title = "Introduction"

        for i, line in enumerate(lines):
            # Check for header patterns
            is_header = False
            header_title = None

            for pattern, group in self.HEADER_PATTERNS:
                match = re.match(pattern, line, re.MULTILINE)
                if match:
                    is_header = True
                    header_title = match.group(group).strip()
                    break

            if is_header and header_title:
                # Save previous section if it has content
                if current_content:
                    section_content = '\n'.join(current_content).strip()
                    if len(section_content) >= self.min_section_chars:
                        section_id = self._generate_section_id(current_title)
                        sections.append(Section(
                            id=section_id,
                            title=current_title,
                            content=section_content,
                            priority=Priority.CONDITIONAL  # Default, will be classified later
                        ))

                # Start new section
                current_title = header_title
                current_content = []
            else:
                current_content.append(line)

        # Don't forget the last section
        if current_content:
            section_content = '\n'.join(current_content).strip()
            if len(section_content) >= self.min_section_chars:
                section_id = self._generate_section_id(current_title)
                sections.append(Section(
                    id=section_id,
                    title=current_title,
                    content=section_content,
                    priority=Priority.CONDITIONAL
                ))

        return sections

    def _generate_section_id(self, title: str) -> str:
        """Generate a clean section ID from title."""
        # Convert to lowercase, replace spaces with underscores
        section_id = title.lower()
        section_id = re.sub(r'[^a-z0-9\s]', '', section_id)
        section_id = re.sub(r'\s+', '_', section_id)
        section_id = section_id[:50]  # Limit length
        return section_id or 'section'

    def _classify_priorities(self, sections: List[Section]) -> List[Section]:
        """Classify sections by priority based on content analysis."""
        for section in sections:
            content_lower = (section.title + ' ' + section.content).lower()

            # Check for priority keywords
            priority_scores = {p: 0 for p in Priority}

            for priority, keywords in self.PRIORITY_KEYWORDS.items():
                for keyword in keywords:
                    if keyword in content_lower:
                        priority_scores[priority] += 1

            # Determine priority based on scores
            max_score = max(priority_scores.values())
            if max_score == 0:
                section.priority = Priority.CONDITIONAL
            else:
                for priority, score in priority_scores.items():
                    if score == max_score:
                        section.priority = priority
                        break

            # First section is usually core
            if sections.index(section) == 0:
                section.priority = Priority.CORE

        return sections

    def _detect_capabilities(self, sections: List[Section]) -> List[Section]:
        """Detect capabilities for each section."""
        for section in sections:
            content_lower = (section.title + ' ' + section.content).lower()

            for capability, keywords in self.CAPABILITY_KEYWORDS.items():
                for keyword in keywords:
                    if keyword in content_lower:
                        if capability.value not in section.capabilities:
                            section.capabilities.append(capability.value)
                        break

        return sections

    def _detect_dependencies(self, sections: List[Section]) -> List[Section]:
        """Detect dependencies between sections."""
        section_ids = {s.id for s in sections}
        section_titles = {s.title.lower(): s.id for s in sections}

        for section in sections:
            for pattern in self.REFERENCE_PATTERNS:
                matches = re.findall(pattern, section.content, re.IGNORECASE)
                for match in matches:
                    match_lower = match.lower()
                    # Check if reference matches a section
                    if match_lower in section_titles:
                        dep_id = section_titles[match_lower]
                        if dep_id != section.id and dep_id not in section.dependencies:
                            section.dependencies.append(dep_id)

        return sections

    def _create_directory_structure(self, output_path: Path):
        """Create the output directory structure."""
        (output_path / 'core').mkdir(parents=True, exist_ok=True)
        (output_path / 'conditional').mkdir(parents=True, exist_ok=True)
        (output_path / 'optional').mkdir(parents=True, exist_ok=True)

    def _write_sections(self, sections: List[Section], output_path: Path):
        """Write sections to individual files."""
        for section in sections:
            # Determine subdirectory based on priority
            subdir = section.priority.value

            # Write section content
            file_path = output_path / subdir / f"{section.id}.md"
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(f"# {section.title}\n\n")
                f.write(section.content)

    def _write_manifest(self, sections: List[Section], output_path: Path, input_path: str) -> str:
        """Write the manifest.json file."""
        # Calculate file hash
        with open(input_path, 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()

        manifest = {
            "version": "1.0",
            "source_file": os.path.basename(input_path),
            "source_hash": file_hash,
            "total_sections": len(sections),
            "total_characters": sum(s.char_count for s in sections),
            "sections": [
                {
                    "id": s.id,
                    "title": s.title,
                    "priority": s.priority.value,
                    "capabilities": s.capabilities,
                    "dependencies": s.dependencies,
                    "char_count": s.char_count,
                    "line_count": s.line_count,
                    "file": f"{s.priority.value}/{s.id}.md"
                }
                for s in sections
            ]
        }

        manifest_path = output_path / 'manifest.json'
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2)

        return str(manifest_path)


def main():
    parser = argparse.ArgumentParser(
        description='Split a large CLAUDE.md file into modular components'
    )
    parser.add_argument(
        'input_file',
        help='Path to the CLAUDE.md file to split'
    )
    parser.add_argument(
        'output_dir',
        help='Directory to write the split files'
    )
    parser.add_argument(
        '--min-chars',
        type=int,
        default=100,
        help='Minimum characters for a valid section (default: 100)'
    )

    args = parser.parse_args()

    if not os.path.exists(args.input_file):
        print(f"Error: Input file '{args.input_file}' not found")
        return 1

    splitter = PromptSplitter(min_section_chars=args.min_chars)

    print(f"Splitting {args.input_file}...")
    result = splitter.split_file(args.input_file, args.output_dir)

    print(f"\n✅ Split complete!")
    print(f"   Total sections: {result.total_sections}")
    print(f"   Total characters: {result.total_chars:,}")
    print(f"   By priority:")
    for priority, count in result.by_priority.items():
        print(f"      {priority}: {count}")
    print(f"   Manifest: {result.manifest_path}")

    return 0


if __name__ == '__main__':
    exit(main())
