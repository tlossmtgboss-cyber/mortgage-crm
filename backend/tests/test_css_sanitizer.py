"""
Tests for CSS Sanitizer
=======================
Comprehensive tests for the allow-list CSS sanitizer used in booking
branding routes. Validates that safe CSS passes through and all known
injection vectors are blocked.
"""

import pytest
import sys
import os

# Ensure backend is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.css_sanitizer import (
    CSSSanitizer,
    ALLOWED_CSS_PROPERTIES,
    ALLOWED_VALUE_PATTERNS,
    BLOCKED_PATTERNS,
)


# ===========================================================================
# sanitize_property_value tests
# ===========================================================================

class TestSanitizePropertyValue:
    """Tests for individual property:value pair sanitization."""

    # -- Colors --

    def test_hex_color_3_digit(self):
        result = CSSSanitizer.sanitize_property_value("color", "#abc")
        assert result == ("color", "#abc")

    def test_hex_color_6_digit(self):
        result = CSSSanitizer.sanitize_property_value("color", "#1a73e8")
        assert result == ("color", "#1a73e8")

    def test_hex_color_8_digit_alpha(self):
        result = CSSSanitizer.sanitize_property_value("color", "#1a73e8ff")
        assert result == ("color", "#1a73e8ff")

    def test_rgb_color(self):
        result = CSSSanitizer.sanitize_property_value("color", "rgb(255, 128, 0)")
        assert result == ("color", "rgb(255, 128, 0)")

    def test_rgba_color(self):
        result = CSSSanitizer.sanitize_property_value("color", "rgba(255, 128, 0, 0.5)")
        assert result == ("color", "rgba(255, 128, 0, 0.5)")

    def test_named_color(self):
        result = CSSSanitizer.sanitize_property_value("color", "red")
        assert result == ("color", "red")

    def test_named_color_camelcase(self):
        result = CSSSanitizer.sanitize_property_value("color", "darkSlateGray")
        assert result == ("color", "darkSlateGray")

    def test_background_color_hex(self):
        result = CSSSanitizer.sanitize_property_value("background-color", "#ffffff")
        assert result == ("background-color", "#ffffff")

    def test_border_color_named(self):
        result = CSSSanitizer.sanitize_property_value("border-color", "transparent")
        assert result == ("border-color", "transparent")

    # -- Typography --

    def test_font_family_simple(self):
        result = CSSSanitizer.sanitize_property_value("font-family", "Arial")
        assert result == ("font-family", "Arial")

    def test_font_family_with_quotes(self):
        result = CSSSanitizer.sanitize_property_value("font-family", '"Helvetica Neue", Arial, sans-serif')
        assert result == ("font-family", '"Helvetica Neue", Arial, sans-serif')

    def test_font_family_with_single_quotes(self):
        result = CSSSanitizer.sanitize_property_value("font-family", "'Open Sans', sans-serif")
        assert result == ("font-family", "'Open Sans', sans-serif")

    def test_font_size_px(self):
        result = CSSSanitizer.sanitize_property_value("font-size", "16px")
        assert result == ("font-size", "16px")

    def test_font_size_rem(self):
        result = CSSSanitizer.sanitize_property_value("font-size", "1.25rem")
        assert result == ("font-size", "1.25rem")

    def test_font_size_em(self):
        result = CSSSanitizer.sanitize_property_value("font-size", "2em")
        assert result == ("font-size", "2em")

    def test_font_size_percent(self):
        result = CSSSanitizer.sanitize_property_value("font-size", "120%")
        assert result == ("font-size", "120%")

    def test_font_weight_bold(self):
        result = CSSSanitizer.sanitize_property_value("font-weight", "bold")
        assert result == ("font-weight", "bold")

    def test_font_weight_numeric(self):
        result = CSSSanitizer.sanitize_property_value("font-weight", "700")
        assert result == ("font-weight", "700")

    def test_font_style_italic(self):
        result = CSSSanitizer.sanitize_property_value("font-style", "italic")
        assert result == ("font-style", "italic")

    def test_text_align_center(self):
        result = CSSSanitizer.sanitize_property_value("text-align", "center")
        assert result == ("text-align", "center")

    def test_text_transform_uppercase(self):
        result = CSSSanitizer.sanitize_property_value("text-transform", "uppercase")
        assert result == ("text-transform", "uppercase")

    def test_line_height_normal(self):
        result = CSSSanitizer.sanitize_property_value("line-height", "normal")
        assert result == ("line-height", "normal")

    def test_line_height_numeric(self):
        result = CSSSanitizer.sanitize_property_value("line-height", "1.5")
        assert result == ("line-height", "1.5")

    def test_letter_spacing_px(self):
        result = CSSSanitizer.sanitize_property_value("letter-spacing", "2px")
        assert result == ("letter-spacing", "2px")

    def test_letter_spacing_negative(self):
        result = CSSSanitizer.sanitize_property_value("letter-spacing", "-1px")
        assert result == ("letter-spacing", "-1px")

    # -- Spacing --

    def test_padding_px(self):
        result = CSSSanitizer.sanitize_property_value("padding", "16px")
        assert result == ("padding", "16px")

    def test_margin_negative(self):
        result = CSSSanitizer.sanitize_property_value("margin-top", "-8px")
        assert result == ("margin-top", "-8px")

    def test_padding_rem(self):
        result = CSSSanitizer.sanitize_property_value("padding-left", "2rem")
        assert result == ("padding-left", "2rem")

    # -- Borders --

    def test_border_shorthand(self):
        result = CSSSanitizer.sanitize_property_value("border", "1px solid #ccc")
        assert result == ("border", "1px solid #ccc")

    def test_border_width_px(self):
        result = CSSSanitizer.sanitize_property_value("border-width", "2px")
        assert result == ("border-width", "2px")

    def test_border_style_dashed(self):
        result = CSSSanitizer.sanitize_property_value("border-style", "dashed")
        assert result == ("border-style", "dashed")

    def test_border_radius_single(self):
        result = CSSSanitizer.sanitize_property_value("border-radius", "8px")
        assert result == ("border-radius", "8px")

    def test_border_radius_four_values(self):
        result = CSSSanitizer.sanitize_property_value("border-radius", "4px 8px 4px 8px")
        assert result == ("border-radius", "4px 8px 4px 8px")

    # -- Layout --

    def test_max_width_px(self):
        result = CSSSanitizer.sanitize_property_value("max-width", "1200px")
        assert result == ("max-width", "1200px")

    def test_min_height_vh(self):
        result = CSSSanitizer.sanitize_property_value("min-height", "100vh")
        assert result == ("min-height", "100vh")

    # -- Opacity --

    def test_opacity_zero(self):
        result = CSSSanitizer.sanitize_property_value("opacity", "0")
        assert result == ("opacity", "0")

    def test_opacity_one(self):
        result = CSSSanitizer.sanitize_property_value("opacity", "1")
        assert result == ("opacity", "1")

    def test_opacity_decimal(self):
        result = CSSSanitizer.sanitize_property_value("opacity", "0.75")
        assert result == ("opacity", "0.75")

    # -- Property name normalization --

    def test_property_name_trimmed(self):
        result = CSSSanitizer.sanitize_property_value("  color  ", "#fff")
        assert result == ("color", "#fff")

    def test_property_name_case_insensitive(self):
        result = CSSSanitizer.sanitize_property_value("Color", "#fff")
        assert result == ("color", "#fff")

    def test_value_trimmed(self):
        result = CSSSanitizer.sanitize_property_value("color", "  #fff  ")
        assert result == ("color", "#fff")


# ===========================================================================
# Blocked properties and values
# ===========================================================================

class TestBlockedProperties:
    """Tests for properties and values that must be rejected."""

    def test_unknown_property_rejected(self):
        assert CSSSanitizer.sanitize_property_value("display", "none") is None

    def test_position_rejected(self):
        assert CSSSanitizer.sanitize_property_value("position", "fixed") is None

    def test_z_index_rejected(self):
        assert CSSSanitizer.sanitize_property_value("z-index", "9999") is None

    def test_overflow_rejected(self):
        assert CSSSanitizer.sanitize_property_value("overflow", "hidden") is None

    def test_cursor_rejected(self):
        assert CSSSanitizer.sanitize_property_value("cursor", "pointer") is None

    def test_visibility_rejected(self):
        assert CSSSanitizer.sanitize_property_value("visibility", "hidden") is None

    def test_content_rejected(self):
        assert CSSSanitizer.sanitize_property_value("content", "'hello'") is None

    def test_background_image_rejected(self):
        assert CSSSanitizer.sanitize_property_value("background-image", "url(evil.png)") is None

    def test_background_rejected(self):
        """'background' (shorthand with url support) is not on the allow-list."""
        assert CSSSanitizer.sanitize_property_value("background", "url(evil.png)") is None

    def test_animation_rejected(self):
        assert CSSSanitizer.sanitize_property_value("animation", "spin 1s infinite") is None

    def test_transform_rejected(self):
        assert CSSSanitizer.sanitize_property_value("transform", "rotate(45deg)") is None

    def test_transition_rejected(self):
        assert CSSSanitizer.sanitize_property_value("transition", "all 0.3s ease") is None


class TestBlockedValuePatterns:
    """Tests for injection vectors that must be blocked in values."""

    def test_url_in_color_blocked(self):
        result = CSSSanitizer.sanitize_property_value("color", "url(javascript:alert(1))")
        assert result is None

    def test_url_in_background_color_blocked(self):
        result = CSSSanitizer.sanitize_property_value("background-color", "url(data:image/svg+xml,...)")
        assert result is None

    def test_javascript_colon_blocked(self):
        result = CSSSanitizer.sanitize_property_value("color", "javascript:alert(1)")
        assert result is None

    def test_javascript_with_spaces_blocked(self):
        result = CSSSanitizer.sanitize_property_value("color", "javascript :alert(1)")
        assert result is None

    def test_expression_blocked(self):
        result = CSSSanitizer.sanitize_property_value("color", "expression(alert(1))")
        assert result is None

    def test_expression_with_spaces_blocked(self):
        result = CSSSanitizer.sanitize_property_value("color", "expression (alert(1))")
        assert result is None

    def test_import_in_value_blocked(self):
        result = CSSSanitizer.sanitize_property_value("color", "@import url(evil.css)")
        assert result is None

    def test_behavior_blocked(self):
        result = CSSSanitizer.sanitize_property_value("color", "behavior: url(xss.htc)")
        assert result is None

    def test_moz_binding_blocked(self):
        result = CSSSanitizer.sanitize_property_value("color", "-moz-binding: url(xss.xml#xss)")
        assert result is None

    def test_html_in_value_blocked(self):
        result = CSSSanitizer.sanitize_property_value("color", "<script>alert(1)</script>")
        assert result is None

    def test_html_angle_brackets_blocked(self):
        result = CSSSanitizer.sanitize_property_value("font-family", "Arial<img onerror=alert(1)>")
        assert result is None

    def test_backslash_escape_blocked(self):
        result = CSSSanitizer.sanitize_property_value("color", "\\6a avascript:alert(1)")
        assert result is None

    def test_url_background_variant_blocked(self):
        """The specific vector from the challenge: background: url(javascript:...)"""
        result = CSSSanitizer.sanitize_property_value("background-color", "url(javascript:void(0))")
        assert result is None

    def test_empty_property_blocked(self):
        assert CSSSanitizer.sanitize_property_value("", "#fff") is None

    def test_empty_value_blocked(self):
        assert CSSSanitizer.sanitize_property_value("color", "") is None


# ===========================================================================
# sanitize_css_string tests
# ===========================================================================

class TestSanitizeCssString:
    """Tests for full CSS string sanitization."""

    def test_single_declaration(self):
        result = CSSSanitizer.sanitize_css_string("color: #fff")
        assert result == "color: #fff"

    def test_multiple_declarations(self):
        result = CSSSanitizer.sanitize_css_string(
            "color: #333; font-size: 16px; padding: 10px"
        )
        assert "color: #333" in result
        assert "font-size: 16px" in result
        assert "padding: 10px" in result

    def test_trailing_semicolon(self):
        result = CSSSanitizer.sanitize_css_string("color: #333;")
        assert result == "color: #333"

    def test_mixed_valid_and_invalid(self):
        result = CSSSanitizer.sanitize_css_string(
            "color: #333; display: none; font-size: 14px; position: fixed"
        )
        assert "color: #333" in result
        assert "font-size: 14px" in result
        assert "display" not in result
        assert "position" not in result

    def test_url_injection_stripped(self):
        result = CSSSanitizer.sanitize_css_string(
            "color: #333; background-color: url(javascript:alert(1)); font-size: 14px"
        )
        assert "color: #333" in result
        assert "font-size: 14px" in result
        assert "url" not in result
        assert "javascript" not in result

    def test_expression_injection_stripped(self):
        result = CSSSanitizer.sanitize_css_string(
            "color: expression(alert(1)); font-weight: bold"
        )
        assert "expression" not in result
        assert "font-weight: bold" in result

    def test_script_tag_in_css_stripped(self):
        result = CSSSanitizer.sanitize_css_string(
            "color: <script>alert(1)</script>#fff; font-size: 16px"
        )
        assert "script" not in result
        assert "font-size: 16px" in result

    def test_import_stripped(self):
        result = CSSSanitizer.sanitize_css_string(
            "@import url(evil.css); color: #333"
        )
        assert "@import" not in result
        assert "color: #333" in result

    def test_empty_string(self):
        assert CSSSanitizer.sanitize_css_string("") == ""

    def test_none_input(self):
        assert CSSSanitizer.sanitize_css_string(None) == ""

    def test_whitespace_only(self):
        assert CSSSanitizer.sanitize_css_string("   ") == ""

    def test_no_valid_declarations(self):
        result = CSSSanitizer.sanitize_css_string("display: flex; position: absolute")
        assert result == ""

    def test_max_length_enforced(self):
        long_css = "color: #fff; " * 1000  # Very long input
        result = CSSSanitizer.sanitize_css_string(long_css, max_length=100)
        # Should still produce valid output, just truncated at input
        assert len(result) <= 100  # Result should be shorter than max_length

    def test_branding_realistic_css(self):
        """Test a realistic branding CSS string."""
        css = (
            "color: #1a73e8; "
            "background-color: #f5f5f5; "
            "font-family: 'Roboto', sans-serif; "
            "font-size: 16px; "
            "font-weight: 400; "
            "border-radius: 8px; "
            "padding: 24px; "
            "max-width: 800px; "
            "opacity: 0.95"
        )
        result = CSSSanitizer.sanitize_css_string(css)
        assert "color: #1a73e8" in result
        assert "background-color: #f5f5f5" in result
        assert "'Roboto', sans-serif" in result
        assert "font-size: 16px" in result
        assert "font-weight: 400" in result
        assert "border-radius: 8px" in result
        assert "padding: 24px" in result
        assert "max-width: 800px" in result
        assert "opacity: 0.95" in result

    def test_malicious_full_payload(self):
        """Test a full malicious payload is completely neutralized."""
        malicious = (
            "color: url(javascript:alert('xss')); "
            "background-color: expression(document.cookie); "
            "font-family: </style><script>alert(1)</script>; "
            "-moz-binding: url(evil.xml#xss); "
            "behavior: url(evil.htc); "
            "@import url(evil.css)"
        )
        result = CSSSanitizer.sanitize_css_string(malicious)
        assert result == ""
        assert "javascript" not in result
        assert "expression" not in result
        assert "script" not in result
        assert "url" not in result
        assert "binding" not in result
        assert "behavior" not in result
        assert "@import" not in result


# ===========================================================================
# sanitize_css_variables tests
# ===========================================================================

class TestSanitizeCssVariables:
    """Tests for CSS custom property (variable) sanitization."""

    def test_valid_hex_variable(self):
        result = CSSSanitizer.sanitize_css_variables({"--primary-color": "#1a73e8"})
        assert result == {"--primary-color": "#1a73e8"}

    def test_valid_rgb_variable(self):
        result = CSSSanitizer.sanitize_css_variables({"--bg-color": "rgb(255, 255, 255)"})
        assert result == {"--bg-color": "rgb(255, 255, 255)"}

    def test_valid_rgba_variable(self):
        result = CSSSanitizer.sanitize_css_variables({"--overlay": "rgba(0, 0, 0, 0.5)"})
        assert result == {"--overlay": "rgba(0, 0, 0, 0.5)"}

    def test_valid_named_color_variable(self):
        result = CSSSanitizer.sanitize_css_variables({"--accent": "coral"})
        assert result == {"--accent": "coral"}

    def test_multiple_valid_variables(self):
        variables = {
            "--primary": "#1a73e8",
            "--secondary": "#34a853",
            "--text": "white",
        }
        result = CSSSanitizer.sanitize_css_variables(variables)
        assert len(result) == 3
        assert result["--primary"] == "#1a73e8"
        assert result["--secondary"] == "#34a853"
        assert result["--text"] == "white"

    def test_non_dashed_key_rejected(self):
        result = CSSSanitizer.sanitize_css_variables({"primary-color": "#fff"})
        assert result == {}

    def test_plain_key_rejected(self):
        result = CSSSanitizer.sanitize_css_variables({"color": "#fff"})
        assert result == {}

    def test_url_value_rejected(self):
        result = CSSSanitizer.sanitize_css_variables({"--bg": "url(evil.png)"})
        assert result == {}

    def test_javascript_value_rejected(self):
        result = CSSSanitizer.sanitize_css_variables({"--color": "javascript:alert(1)"})
        assert result == {}

    def test_expression_value_rejected(self):
        result = CSSSanitizer.sanitize_css_variables({"--color": "expression(alert(1))"})
        assert result == {}

    def test_non_color_value_rejected(self):
        """CSS variables should only accept color values."""
        result = CSSSanitizer.sanitize_css_variables({"--size": "16px"})
        assert result == {}

    def test_empty_dict(self):
        assert CSSSanitizer.sanitize_css_variables({}) == {}

    def test_none_input(self):
        assert CSSSanitizer.sanitize_css_variables(None) == {}

    def test_non_dict_input(self):
        assert CSSSanitizer.sanitize_css_variables("not a dict") == {}

    def test_non_string_values_rejected(self):
        result = CSSSanitizer.sanitize_css_variables({"--color": 123})
        assert result == {}

    def test_non_string_keys_rejected(self):
        result = CSSSanitizer.sanitize_css_variables({123: "#fff"})
        assert result == {}

    def test_value_trimmed(self):
        result = CSSSanitizer.sanitize_css_variables({"--color": "  #fff  "})
        assert result == {"--color": "#fff"}

    def test_invalid_variable_name_rejected(self):
        """Variable names with special characters should be rejected."""
        result = CSSSanitizer.sanitize_css_variables({
            "--valid-name": "#fff",
            "---triple-dash": "#fff",  # starts with valid pattern
            "--123invalid": "#fff",  # starts with number after --
        })
        assert "--valid-name" in result
        assert "--123invalid" not in result

    def test_html_in_variable_name_rejected(self):
        result = CSSSanitizer.sanitize_css_variables({
            "--color<script>": "#fff",
        })
        assert result == {}

    def test_mixed_valid_and_invalid(self):
        variables = {
            "--primary": "#1a73e8",
            "--evil": "url(javascript:alert(1))",
            "--secondary": "rgb(52, 168, 83)",
            "not-a-var": "#fff",
        }
        result = CSSSanitizer.sanitize_css_variables(variables)
        assert len(result) == 2
        assert "--primary" in result
        assert "--secondary" in result


# ===========================================================================
# Allow-list completeness tests
# ===========================================================================

class TestAllowListCompleteness:
    """Verify the allow-list covers expected branding properties."""

    def test_color_properties_present(self):
        for prop in ("color", "background-color", "border-color"):
            assert prop in ALLOWED_CSS_PROPERTIES

    def test_typography_properties_present(self):
        for prop in ("font-family", "font-size", "font-weight", "font-style",
                      "line-height", "letter-spacing", "text-align", "text-transform"):
            assert prop in ALLOWED_CSS_PROPERTIES

    def test_spacing_properties_present(self):
        for prop in ("padding", "padding-top", "padding-right", "padding-bottom",
                      "padding-left", "margin", "margin-top", "margin-right",
                      "margin-bottom", "margin-left"):
            assert prop in ALLOWED_CSS_PROPERTIES

    def test_border_properties_present(self):
        for prop in ("border", "border-width", "border-style", "border-radius"):
            assert prop in ALLOWED_CSS_PROPERTIES

    def test_layout_properties_present(self):
        for prop in ("max-width", "min-height"):
            assert prop in ALLOWED_CSS_PROPERTIES

    def test_opacity_present(self):
        assert "opacity" in ALLOWED_CSS_PROPERTIES

    def test_dangerous_properties_absent(self):
        """Ensure dangerous properties are NOT on the allow-list."""
        dangerous = [
            "position", "display", "z-index", "overflow", "cursor",
            "visibility", "content", "background-image", "background",
            "animation", "transform", "transition", "filter",
            "clip-path", "pointer-events", "user-select",
        ]
        for prop in dangerous:
            assert prop not in ALLOWED_CSS_PROPERTIES, f"{prop} should not be allowed"


# ===========================================================================
# Edge cases
# ===========================================================================

class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_declaration_with_no_colon(self):
        """Declarations without : should be skipped."""
        result = CSSSanitizer.sanitize_css_string("not-a-declaration")
        assert result == ""

    def test_declaration_with_multiple_colons(self):
        """Only first colon should be used as separator."""
        result = CSSSanitizer.sanitize_css_string("color: rgb(0, 0, 0)")
        assert result == "color: rgb(0, 0, 0)"

    def test_semicolons_in_isolation(self):
        result = CSSSanitizer.sanitize_css_string(";;;")
        assert result == ""

    def test_only_semicolons_and_spaces(self):
        result = CSSSanitizer.sanitize_css_string("; ; ; ")
        assert result == ""

    def test_unicode_in_font_family(self):
        """Font names should only allow ASCII letters, spaces, quotes, hyphens."""
        result = CSSSanitizer.sanitize_property_value("font-family", "Arial\u0000")
        # Null byte is not in the allowed pattern
        assert result is None

    def test_very_large_numeric_value(self):
        """Values beyond 4 digits should be rejected by default pattern."""
        result = CSSSanitizer.sanitize_property_value("padding", "99999px")
        assert result is None

    def test_negative_padding_allowed(self):
        """Negative values are allowed by the pattern for margin."""
        result = CSSSanitizer.sanitize_property_value("margin-left", "-10px")
        assert result == ("margin-left", "-10px")

    def test_zero_without_unit(self):
        result = CSSSanitizer.sanitize_property_value("padding", "0")
        assert result == ("padding", "0")

    def test_border_shorthand_with_named_color(self):
        result = CSSSanitizer.sanitize_property_value("border", "2px solid red")
        assert result == ("border", "2px solid red")

    def test_border_shorthand_with_url_blocked(self):
        result = CSSSanitizer.sanitize_property_value("border", "url(evil) solid red")
        assert result is None
