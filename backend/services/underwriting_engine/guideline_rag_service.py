"""
Guideline RAG Service

Retrieval-Augmented Generation service for mortgage underwriting guidelines.
Uses pgvector for semantic search over agency guideline documents (Fannie Mae,
Freddie Mac, FHA, VA, USDA).

Capabilities:
- Ingest and chunk guideline documents into embeddings
- Query guidelines by semantic similarity with optional agency filter
- Return ranked results with agency, section, requirement text, and relevance score

Embedding model: OpenAI text-embedding-3-small (1536 dimensions)
Vector store: PostgreSQL + pgvector extension

Schema (guideline_embeddings table):
    id          SERIAL PRIMARY KEY
    agency      VARCHAR          -- fannie_mae, freddie_mac, fha, va, usda
    section     VARCHAR          -- e.g. "B3-5.3-01" or "4000.1 II.A.4"
    title       VARCHAR          -- Section title
    full_text   TEXT             -- Original text of the guideline section
    embedding   VECTOR(1536)    -- pgvector embedding
    metadata    JSONB           -- Extra metadata (effective_date, source_url, etc.)
    created_at  TIMESTAMP
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence
import hashlib
import logging
import os
import re

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Index, text as sa_text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

EMBEDDING_MODEL = os.getenv("GUIDELINE_EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIMENSIONS = 1536
DEFAULT_CHUNK_SIZE = 1500       # characters per chunk
DEFAULT_CHUNK_OVERLAP = 200     # overlap between chunks
SUPPORTED_AGENCIES = {"fannie_mae", "freddie_mac", "fha", "va", "usda"}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class GuidelineChunk:
    """A single chunk of guideline text ready for embedding."""
    agency: str
    section: str
    title: str
    full_text: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    content_hash: str = ""

    def __post_init__(self):
        if not self.content_hash:
            self.content_hash = hashlib.sha256(self.full_text.encode()).hexdigest()[:16]


@dataclass
class GuidelineResult:
    """A single result from a guideline query."""
    agency: str
    section: str
    title: str
    requirement: str
    relevance_score: float
    full_text: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agency": self.agency,
            "section": self.section,
            "title": self.title,
            "requirement": self.requirement,
            "relevance_score": round(self.relevance_score, 4),
            "full_text": self.full_text,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# Table definition (raw SQL — pgvector requires the extension)
# ---------------------------------------------------------------------------

_CREATE_EXTENSION_SQL = "CREATE EXTENSION IF NOT EXISTS vector;"

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS guideline_embeddings (
    id              SERIAL PRIMARY KEY,
    agency          VARCHAR(50) NOT NULL,
    section         VARCHAR(200) NOT NULL,
    title           VARCHAR(500),
    full_text       TEXT NOT NULL,
    embedding       vector({dimensions}),
    content_hash    VARCHAR(32),
    metadata        JSONB DEFAULT '{{}}'::jsonb,
    created_at      TIMESTAMP DEFAULT (NOW() AT TIME ZONE 'utc')
);
""".format(dimensions=EMBEDDING_DIMENSIONS)

_CREATE_INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS ix_ge_agency ON guideline_embeddings (agency);",
    "CREATE INDEX IF NOT EXISTS ix_ge_section ON guideline_embeddings (section);",
    "CREATE INDEX IF NOT EXISTS ix_ge_hash ON guideline_embeddings (content_hash);",
    # IVFFlat index for approximate nearest-neighbor search
    # Must be created AFTER data is inserted for optimal list count
    # "CREATE INDEX IF NOT EXISTS ix_ge_embedding ON guideline_embeddings "
    # "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);",
]


# ---------------------------------------------------------------------------
# Embedding client wrapper
# ---------------------------------------------------------------------------

class _EmbeddingClient:
    """
    Thin wrapper around the OpenAI embeddings API.
    Instantiated lazily so the service can be imported without an API key.
    """

    def __init__(self):
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            try:
                import openai
                self._client = openai.OpenAI(
                    api_key=os.getenv("OPENAI_API_KEY"),
                )
            except ImportError:
                raise RuntimeError(
                    "openai package is required for guideline embeddings. "
                    "Install with: pip install openai"
                )

    async def embed(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a batch of texts.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of embedding vectors (each a list of floats).
        """
        self._ensure_client()
        # OpenAI client is sync; run in thread for async compat
        import asyncio
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self._client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=texts,
            ),
        )
        return [item.embedding for item in result.data]

    async def embed_single(self, text: str) -> List[float]:
        """Embed a single text string."""
        results = await self.embed([text])
        return results[0]


# ---------------------------------------------------------------------------
# RAG Service
# ---------------------------------------------------------------------------

class GuidelineRAGService:
    """
    pgvector-based guideline retrieval service.

    Ingests agency guideline documents, splits them into chunks,
    generates embeddings, and provides semantic search.

    Usage::

        service = GuidelineRAGService(db_session)
        await service.ensure_schema()

        # Ingest a guideline document
        count = await service.ingest_guideline_document(
            document_path="/path/to/fnma_selling_guide_b3.txt",
            agency="fannie_mae",
        )

        # Query guidelines
        results = await service.query_guidelines(
            query="What is the minimum credit score for a conventional loan?",
            agencies=["fannie_mae", "freddie_mac"],
            top_k=5,
        )
        for r in results:
            print(r.agency, r.section, r.relevance_score)
    """

    def __init__(self, db: Session):
        """
        Args:
            db: SQLAlchemy session connected to a PostgreSQL database
                with the pgvector extension available.
        """
        self.db = db
        self._embedder = _EmbeddingClient()

    # ------------------------------------------------------------------
    # Schema management
    # ------------------------------------------------------------------

    async def ensure_schema(self) -> None:
        """Create the pgvector extension and guideline_embeddings table if needed."""
        try:
            self.db.execute(sa_text(_CREATE_EXTENSION_SQL))
            self.db.execute(sa_text(_CREATE_TABLE_SQL))
            for idx_sql in _CREATE_INDEXES_SQL:
                self.db.execute(sa_text(idx_sql))
            self.db.commit()
            logger.info("GuidelineRAGService: Schema ensured.")
        except Exception as e:
            self.db.rollback()
            logger.exception("GuidelineRAGService: Failed to ensure schema: %s", e)
            raise

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    async def ingest_guideline_document(
        self,
        document_path: str,
        agency: str,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Ingest a guideline document: chunk, embed, and store.

        Args:
            document_path: Path to the text file containing guideline content.
            agency: One of fannie_mae, freddie_mac, fha, va, usda.
            chunk_size: Maximum characters per chunk.
            chunk_overlap: Overlap between consecutive chunks.
            metadata: Extra metadata to store with each chunk.

        Returns:
            Number of chunks ingested.
        """
        if agency not in SUPPORTED_AGENCIES:
            raise ValueError(
                f"Unsupported agency '{agency}'. Must be one of: {SUPPORTED_AGENCIES}"
            )

        # Read document
        with open(document_path, "r", encoding="utf-8") as f:
            raw_text = f.read()

        if not raw_text.strip():
            logger.warning("GuidelineRAGService: Document at %s is empty.", document_path)
            return 0

        # Parse into sections
        chunks = self._parse_and_chunk(raw_text, agency, chunk_size, chunk_overlap, metadata)
        if not chunks:
            return 0

        # Deduplicate against existing content
        chunks = await self._deduplicate(chunks)
        if not chunks:
            logger.info("GuidelineRAGService: All chunks already ingested for %s.", document_path)
            return 0

        # Generate embeddings in batches
        batch_size = 100
        total_inserted = 0

        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            texts = [c.full_text for c in batch]

            try:
                embeddings = await self._embedder.embed(texts)
            except Exception as e:
                logger.exception(
                    "GuidelineRAGService: Embedding batch %d failed: %s", i, e,
                )
                continue

            for chunk, embedding in zip(batch, embeddings):
                embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"
                insert_sql = sa_text("""
                    INSERT INTO guideline_embeddings
                        (agency, section, title, full_text, embedding, content_hash, metadata)
                    VALUES
                        (:agency, :section, :title, :full_text,
                         :embedding::vector, :content_hash, :metadata::jsonb)
                """)
                self.db.execute(insert_sql, {
                    "agency": chunk.agency,
                    "section": chunk.section,
                    "title": chunk.title,
                    "full_text": chunk.full_text,
                    "embedding": embedding_str,
                    "content_hash": chunk.content_hash,
                    "metadata": _json_dumps(chunk.metadata),
                })
                total_inserted += 1

            self.db.commit()

        logger.info(
            "GuidelineRAGService: Ingested %d chunks from %s (%s).",
            total_inserted, document_path, agency,
        )
        return total_inserted

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    async def query_guidelines(
        self,
        query: str,
        agencies: Optional[List[str]] = None,
        top_k: int = 5,
    ) -> List[GuidelineResult]:
        """
        Semantic search over ingested guideline embeddings.

        Args:
            query: Natural language question or topic.
            agencies: Optional list to filter by agency. None = all agencies.
            top_k: Number of results to return.

        Returns:
            List of GuidelineResult sorted by relevance (highest first).
        """
        # Generate query embedding
        query_embedding = await self._embedder.embed_single(query)
        embedding_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

        # Build SQL with optional agency filter
        agency_filter = ""
        params: Dict[str, Any] = {
            "embedding": embedding_str,
            "top_k": top_k,
        }

        if agencies:
            validated = [a for a in agencies if a in SUPPORTED_AGENCIES]
            if validated:
                placeholders = ", ".join(f":agency_{i}" for i in range(len(validated)))
                agency_filter = f"WHERE agency IN ({placeholders})"
                for i, a in enumerate(validated):
                    params[f"agency_{i}"] = a

        # Cosine similarity: 1 - cosine_distance
        # pgvector <=> operator returns cosine distance
        sql = sa_text(f"""
            SELECT
                agency,
                section,
                title,
                full_text,
                metadata,
                1 - (embedding <=> :embedding::vector) AS relevance_score
            FROM guideline_embeddings
            {agency_filter}
            ORDER BY embedding <=> :embedding::vector
            LIMIT :top_k
        """)

        try:
            rows = self.db.execute(sql, params).fetchall()
        except Exception as e:
            logger.exception("GuidelineRAGService: Query failed: %s", e)
            return []

        results: List[GuidelineResult] = []
        for row in rows:
            # Extract the first sentence or requirement from full text
            requirement = self._extract_requirement(row[3])
            meta = row[4] if row[4] else {}

            results.append(GuidelineResult(
                agency=row[0],
                section=row[1],
                title=row[2] or "",
                requirement=requirement,
                relevance_score=float(row[5]) if row[5] else 0.0,
                full_text=row[3],
                metadata=meta,
            ))

        return results

    async def delete_agency_guidelines(self, agency: str) -> int:
        """
        Remove all guideline embeddings for a specific agency.
        Useful before re-ingesting an updated version.

        Returns:
            Number of rows deleted.
        """
        if agency not in SUPPORTED_AGENCIES:
            raise ValueError(f"Unsupported agency '{agency}'.")

        try:
            result = self.db.execute(
                sa_text("DELETE FROM guideline_embeddings WHERE agency = :agency"),
                {"agency": agency},
            )
            self.db.commit()
            count = result.rowcount
            logger.info("GuidelineRAGService: Deleted %d rows for agency %s.", count, agency)
            return count
        except Exception as e:
            self.db.rollback()
            logger.exception("GuidelineRAGService: Delete failed for %s: %s", agency, e)
            raise

    async def get_stats(self) -> Dict[str, Any]:
        """Return counts and metadata about ingested guidelines."""
        try:
            rows = self.db.execute(sa_text(
                "SELECT agency, COUNT(*) FROM guideline_embeddings GROUP BY agency ORDER BY agency"
            )).fetchall()
            by_agency = {row[0]: row[1] for row in rows}
            total = sum(by_agency.values())
            return {"total_chunks": total, "by_agency": by_agency}
        except Exception as e:
            logger.exception("GuidelineRAGService: Stats query failed: %s", e)
            return {"total_chunks": 0, "by_agency": {}}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_and_chunk(
        self,
        raw_text: str,
        agency: str,
        chunk_size: int,
        chunk_overlap: int,
        extra_metadata: Optional[Dict[str, Any]],
    ) -> List[GuidelineChunk]:
        """
        Parse raw guideline text into sections, then split into sized chunks.

        Heuristic section detection:
        - Lines matching patterns like "B3-5.3-01", "Section 4000.1", "Chapter 4", etc.
        """
        chunks: List[GuidelineChunk] = []
        meta = extra_metadata or {}

        # Try to detect sections by header patterns
        section_pattern = re.compile(
            r'^(?:'
            r'(?:Section\s+)?[A-Z]\d[\d\-\.]+\d'  # e.g. B3-5.3-01
            r'|Chapter\s+\d+'                       # e.g. Chapter 4
            r'|Section\s+\d[\d\.]*'                 # e.g. Section 4000.1
            r'|\d+\.\d+[\.\d]*'                     # e.g. 4000.1.II.A
            r')',
            re.MULTILINE,
        )

        lines = raw_text.split("\n")
        sections: List[Dict[str, str]] = []
        current_section = ""
        current_title = ""
        current_text_lines: List[str] = []

        for line in lines:
            match = section_pattern.match(line.strip())
            if match:
                # Save previous section
                if current_text_lines:
                    sections.append({
                        "section": current_section or "general",
                        "title": current_title,
                        "text": "\n".join(current_text_lines),
                    })
                current_section = match.group(0)
                # Title is the rest of the line after the section number
                remainder = line.strip()[len(current_section):].strip(" :-–—")
                current_title = remainder if remainder else current_section
                current_text_lines = [line.strip()]
            else:
                current_text_lines.append(line)

        # Don't forget the last section
        if current_text_lines:
            sections.append({
                "section": current_section or "general",
                "title": current_title,
                "text": "\n".join(current_text_lines),
            })

        # Chunk each section
        for sec in sections:
            text = sec["text"]
            if len(text) <= chunk_size:
                chunks.append(GuidelineChunk(
                    agency=agency,
                    section=sec["section"],
                    title=sec["title"],
                    full_text=text,
                    metadata=meta,
                ))
            else:
                # Sliding window chunking
                start = 0
                chunk_idx = 0
                while start < len(text):
                    end = min(start + chunk_size, len(text))
                    chunk_text = text[start:end]
                    chunks.append(GuidelineChunk(
                        agency=agency,
                        section=f"{sec['section']}#{chunk_idx}",
                        title=sec["title"],
                        full_text=chunk_text,
                        metadata={**meta, "chunk_index": chunk_idx},
                    ))
                    chunk_idx += 1
                    start += chunk_size - chunk_overlap

        return chunks

    async def _deduplicate(self, chunks: List[GuidelineChunk]) -> List[GuidelineChunk]:
        """Remove chunks whose content_hash already exists in the database."""
        if not chunks:
            return []

        hashes = [c.content_hash for c in chunks]
        # Query existing hashes in one round-trip
        placeholders = ", ".join(f":h{i}" for i in range(len(hashes)))
        params = {f"h{i}": h for i, h in enumerate(hashes)}

        try:
            rows = self.db.execute(
                sa_text(f"SELECT content_hash FROM guideline_embeddings WHERE content_hash IN ({placeholders})"),
                params,
            ).fetchall()
            existing = {row[0] for row in rows}
        except Exception as e:
            logger.warning("GuidelineRAGService: Dedup query failed, skipping: %s", e)
            return chunks

        return [c for c in chunks if c.content_hash not in existing]

    @staticmethod
    def _extract_requirement(full_text: str) -> str:
        """Extract the first meaningful sentence as the 'requirement' summary."""
        if not full_text:
            return ""
        # Strip leading section numbers / whitespace
        cleaned = re.sub(r'^[A-Z0-9\-\.#]+\s*', '', full_text.strip())
        # Take first sentence (up to period, question mark, or 200 chars)
        match = re.match(r'(.+?[.?!])\s', cleaned)
        if match:
            return match.group(1).strip()
        return cleaned[:200].strip()


# ---------------------------------------------------------------------------
# JSON helper (avoid importing json at module level for consistency)
# ---------------------------------------------------------------------------

def _json_dumps(obj: Any) -> str:
    """Serialize a dict to JSON string."""
    import json
    return json.dumps(obj, default=str)
