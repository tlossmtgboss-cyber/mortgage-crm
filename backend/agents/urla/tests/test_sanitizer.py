"""Tests for URLA input sanitizer."""
import pytest

from agents.urla.sanitizer import (
    sanitize_text,
    sanitize_name,
    sanitize_address,
    sanitize_description,
)


class TestSanitizeText:
    def test_strips_html(self):
        assert sanitize_text("<b>hello</b>", "f") == "hello"

    def test_strips_script_tags(self):
        result = sanitize_text("<script>alert(1)</script>test", "f")
        assert "<script" not in result.lower()
        assert "</script" not in result.lower()

    def test_removes_control_chars(self):
        result = sanitize_text("hello\x00world\x07", "f")
        assert result == "helloworld"

    def test_truncates(self):
        long = "a" * 600
        result = sanitize_text(long, "f", max_length=500)
        assert len(result) == 500

    def test_blocks_sql_injection(self):
        result = sanitize_text("Robert'; DROP TABLE users;--", "name")
        assert "DROP TABLE" not in result

    def test_blocks_xss(self):
        result = sanitize_text('test<img onerror="alert(1)">', "f")
        assert "onerror" not in result

    def test_none_returns_none(self):
        assert sanitize_text(None, "f") is None

    def test_preserves_normal_text(self):
        assert sanitize_text("John Smith Jr.", "name") == "John Smith Jr."


class TestSanitizeName:
    def test_strips_special_chars(self):
        result = sanitize_name("John@#$Smith", "name")
        assert result == "JohnSmith"

    def test_allows_hyphen_apostrophe(self):
        assert sanitize_name("O'Brien-Smith", "name") == "O'Brien-Smith"

    def test_allows_period(self):
        assert sanitize_name("John Jr.", "name") == "John Jr."


class TestSanitizeAddress:
    def test_allows_hash_slash(self):
        result = sanitize_address("123 Main St #4B", "addr")
        assert result == "123 Main St #4B"

    def test_strips_injection(self):
        result = sanitize_address("123 Main<script>", "addr")
        assert "script" not in result.lower()


class TestSanitizeDescription:
    def test_max_1000(self):
        long = "x" * 1200
        result = sanitize_description(long, "desc")
        assert len(result) == 1000
