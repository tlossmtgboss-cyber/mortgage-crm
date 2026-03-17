"""
CSS Sanitizer
=============
Strict allow-list CSS sanitizer for organization branding.

Replaces regex-based CSS sanitization with a proper allow-list approach
that validates both CSS property names and their values against known-safe
patterns. Blocks all url(), expression(), javascript:, and other injection
vectors.

Usage:
    from services.css_sanitizer import CSSSanitizer

    safe_css = CSSSanitizer.sanitize_css_string(user_input)
    safe_vars = CSSSanitizer.sanitize_css_variables(user_vars)
"""

import re
import logging
from typing import Optional, Set, Dict, Tuple

logger = logging.getLogger(__name__)


# Strict allow-list of CSS properties safe for branding
ALLOWED_CSS_PROPERTIES: Set[str] = {
    # Colors
    "color", "background-color", "border-color",
    # Typography
    "font-family", "font-size", "font-weight", "font-style",
    "line-height", "letter-spacing", "text-align", "text-transform",
    # Spacing
    "padding", "padding-top", "padding-right", "padding-bottom", "padding-left",
    "margin", "margin-top", "margin-right", "margin-bottom", "margin-left",
    # Borders
    "border", "border-width", "border-style", "border-radius",
    # Layout (limited)
    "max-width", "min-height",
    # Opacity
    "opacity",
}

# Allow-list of CSS value patterns per property type
ALLOWED_VALUE_PATTERNS: Dict[str, str] = {
    "color": r"^(#[0-9a-fA-F]{3,8}|rgb\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}\s*\)|rgba\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*[\d.]+\s*\)|[a-zA-Z]+)$",
    "font-family": r'^[a-zA-Z\s\-,"\x27]+$',  # Letters, spaces, quotes, commas, hyphens
    "font-size": r"^\d{1,3}(\.\d+)?(px|rem|em|%)$",
    "font-weight": r"^(normal|bold|lighter|bolder|\d{3})$",
    "font-style": r"^(normal|italic|oblique)$",
    "line-height": r"^(normal|\d{1,3}(\.\d+)?(px|rem|em|%|))$",
    "letter-spacing": r"^(normal|-?\d{1,3}(\.\d+)?(px|rem|em))$",
    "text-align": r"^(left|right|center|justify)$",
    "text-transform": r"^(none|capitalize|uppercase|lowercase)$",
    "border-style": r"^(none|solid|dashed|dotted|double|groove|ridge|inset|outset)$",
    "border-radius": r"^\d{1,3}(\.\d+)?(px|rem|em|%)(\s+\d{1,3}(\.\d+)?(px|rem|em|%)){0,3}$",
    "opacity": r"^(0|1|0?\.\d+)$",
    # Generic number+unit for spacing/sizing properties
    "_default": r"^-?\d{1,4}(\.\d+)?(px|rem|em|%|vh|vw)?$",
}

# Border shorthand: <width> <style> <color>
_BORDER_SHORTHAND_PATTERN = r"^\d{1,3}(px|rem|em)\s+(none|solid|dashed|dotted|double)\s+(#[0-9a-fA-F]{3,8}|[a-zA-Z]+)$"

# Explicitly blocked patterns (defense in depth)
BLOCKED_PATTERNS = [
    r"url\s*\(",          # No url() values
    r"expression\s*\(",   # No expression() (IE)
    r"javascript\s*:",    # No javascript:
    r"@import",           # No @import
    r"behavior\s*:",      # No behavior: (IE)
    r"-moz-binding\s*:",  # No XBL binding
    r"<",                 # No HTML
    r">",
    r"\\",               # No CSS escape sequences that could bypass checks
]

# Compiled blocked patterns for performance
_COMPILED_BLOCKED = [re.compile(p, re.IGNORECASE) for p in BLOCKED_PATTERNS]


class CSSSanitizer:
    """Strict allow-list CSS sanitizer for org branding."""

    @classmethod
    def sanitize_property_value(cls, prop: str, value: str) -> Optional[Tuple[str, str]]:
        """
        Sanitize a single CSS property:value pair.

        Returns (prop, value) tuple if valid, or None if the property or value
        is not on the allow-list.
        """
        prop = prop.strip().lower()
        value = value.strip()

        if not prop or not value:
            return None

        # Check property allow-list
        if prop not in ALLOWED_CSS_PROPERTIES:
            return None

        # Check blocked patterns (defense in depth)
        for compiled in _COMPILED_BLOCKED:
            if compiled.search(value):
                logger.warning(
                    "CSS sanitizer blocked dangerous value for property '%s': '%s'",
                    prop, value[:100],
                )
                return None

        # Determine which value pattern to use
        pattern = cls._get_value_pattern(prop)

        if not re.match(pattern, value):
            return None

        return (prop, value)

    @classmethod
    def _get_value_pattern(cls, prop: str) -> str:
        """Get the appropriate value validation pattern for a CSS property."""
        # Color properties
        if prop in ("color", "background-color", "border-color"):
            return ALLOWED_VALUE_PATTERNS["color"]

        # Border shorthand
        if prop == "border":
            return _BORDER_SHORTHAND_PATTERN

        # Direct match
        if prop in ALLOWED_VALUE_PATTERNS:
            return ALLOWED_VALUE_PATTERNS[prop]

        # Spacing/sizing properties use default numeric pattern
        return ALLOWED_VALUE_PATTERNS["_default"]

    @classmethod
    def sanitize_css_string(cls, css: str, max_length: int = 10000) -> str:
        """
        Sanitize a full CSS string (property: value; property: value;).

        Only allows properties and values that pass the allow-list checks.
        Returns empty string for None/empty input.

        Args:
            css: Raw CSS declarations string.
            max_length: Maximum allowed length of input (default 10000).

        Returns:
            Sanitized CSS string with only allowed declarations.
        """
        if not css:
            return ""

        # Truncate before parsing to prevent DoS on very large inputs
        css = css[:max_length]

        sanitized = []
        for declaration in css.split(";"):
            declaration = declaration.strip()
            if ":" not in declaration:
                continue
            prop, _, value = declaration.partition(":")
            result = cls.sanitize_property_value(prop, value)
            if result:
                sanitized.append(f"{result[0]}: {result[1]}")

        return "; ".join(sanitized)

    @classmethod
    def sanitize_css_variables(cls, variables: dict) -> dict:
        """
        Sanitize CSS custom properties (--primary-color, etc.).

        Only allows variables whose names start with '--' and whose values
        match the color pattern (hex, rgb, rgba, named colors).

        Args:
            variables: Dict of CSS variable names to values.

        Returns:
            Dict with only valid CSS custom property names and color values.
        """
        if not variables or not isinstance(variables, dict):
            return {}

        sanitized = {}
        color_pattern = re.compile(ALLOWED_VALUE_PATTERNS["color"])

        for key, value in variables.items():
            if not isinstance(key, str) or not isinstance(value, str):
                continue

            # Only allow CSS custom properties (must start with --)
            if not key.startswith("--"):
                continue

            # Validate the variable name: only alphanumeric, hyphens
            if not re.match(r"^--[a-zA-Z][a-zA-Z0-9\-]*$", key):
                continue

            clean_value = value.strip()

            # Check blocked patterns
            blocked = False
            for compiled in _COMPILED_BLOCKED:
                if compiled.search(clean_value):
                    blocked = True
                    break
            if blocked:
                continue

            # Only allow color values for CSS variables
            if color_pattern.match(clean_value):
                sanitized[key] = clean_value

        return sanitized
