"""Tests for guideline text chunking and hashing functions."""

import sys
import os

# Ensure backend is on the path so the service module can be imported directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.call_monitoring.guidelines_service import (
    chunk_text_with_overlap,
    compute_chunk_hash,
    _count_tokens,
)


# ---------------------------------------------------------------------------
# Helper to generate text of a known approximate token count
# ---------------------------------------------------------------------------

def _make_long_text(target_tokens: int = 1000) -> str:
    """Return text that is roughly *target_tokens* tokens long.

    Each 'word' is ~1 token with cl100k_base.  We use distinct words
    separated by paragraph breaks so the splitter has boundaries.
    """
    paragraphs = []
    words_per_para = 40  # ~40 tokens per paragraph
    num_paras = (target_tokens // words_per_para) + 1
    for i in range(num_paras):
        para = " ".join(f"word{i}_{j}" for j in range(words_per_para))
        paragraphs.append(para)
    return "\n\n".join(paragraphs)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestChunkRespectsTokenLimit:
    """Long text (~1000 tokens) produces multiple chunks, each <= 550 tokens."""

    def test_chunk_respects_token_limit(self):
        text = _make_long_text(1000)
        chunks = chunk_text_with_overlap(text, max_tokens=500, overlap_tokens=50)

        # Must produce more than one chunk for ~1000-token text
        assert len(chunks) >= 2, f"Expected >= 2 chunks, got {len(chunks)}"

        for i, chunk in enumerate(chunks):
            tok = _count_tokens(chunk["content"])
            # Allow a small buffer above max_tokens because we split on
            # paragraph boundaries, not mid-paragraph.
            assert tok <= 550, (
                f"Chunk {i} has {tok} tokens (limit 550)"
            )


class TestChunkPreservesSectionMetadata:
    """Chunks inherit section_number (with .N suffix) and section_title."""

    def test_chunk_preserves_section_metadata(self):
        text = _make_long_text(1000)
        chunks = chunk_text_with_overlap(
            text,
            max_tokens=500,
            overlap_tokens=50,
            section_number="B3-3.1",
            section_title="Credit Requirements",
        )

        assert len(chunks) >= 2

        for i, chunk in enumerate(chunks):
            assert chunk["section_number"] == f"B3-3.1.{i}", (
                f"Chunk {i} section_number = {chunk['section_number']!r}"
            )
            assert chunk["section_title"] == "Credit Requirements"


class TestShortTextSingleChunk:
    """Text under limit produces exactly one chunk."""

    def test_short_text_single_chunk(self):
        short_text = "This is a very short guideline about minimum credit scores."
        chunks = chunk_text_with_overlap(
            short_text,
            max_tokens=500,
            section_number="1.2",
            section_title="Credit",
        )

        assert len(chunks) == 1
        assert chunks[0]["content"] == short_text
        assert chunks[0]["section_number"] == "1.2.0"
        assert chunks[0]["section_title"] == "Credit"
        assert chunks[0]["token_count"] == _count_tokens(short_text)
        assert len(chunks[0]["chunk_hash"]) == 64

    def test_empty_text_no_chunks(self):
        chunks = chunk_text_with_overlap("")
        assert chunks == []


class TestChunkHashDeterministic:
    """Same content produces the same hash, and hash is 64 hex chars."""

    def test_chunk_hash_deterministic(self):
        content = "Minimum credit score for conventional is 620."
        h1 = compute_chunk_hash(content)
        h2 = compute_chunk_hash(content)

        assert h1 == h2
        assert len(h1) == 64
        # Verify it's valid hex
        int(h1, 16)


class TestChunkHashDiffersForDifferentContent:
    """Different content produces different hashes."""

    def test_chunk_hash_differs_for_different_content(self):
        h1 = compute_chunk_hash("Minimum credit score is 620.")
        h2 = compute_chunk_hash("Maximum DTI is 45%.")

        assert h1 != h2
        assert len(h1) == 64
        assert len(h2) == 64
