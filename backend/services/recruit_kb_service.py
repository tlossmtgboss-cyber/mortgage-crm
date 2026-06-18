"""
Recruiting Knowledge Base Service

Text extraction, chunking, embedding, and semantic retrieval for the
recruiting chatbot knowledge base.

Embedding model: sentence-transformers all-MiniLM-L6-v2 (384 dimensions)
Fallback: dummy zero-vector embedding when sentence_transformers is unavailable.
"""

import io
import logging
import os
from typing import List

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sentence-transformer singleton (loaded once on first embed call)
# ---------------------------------------------------------------------------
_st_model = None
_st_available: bool | None = None  # None = not yet checked


def _get_st_model():
    global _st_model, _st_available
    if _st_available is None:
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
            _st_model = SentenceTransformer("all-MiniLM-L6-v2")
            _st_available = True
            logger.info("sentence-transformers model loaded (all-MiniLM-L6-v2)")
        except ImportError:
            _st_available = False
            logger.warning(
                "sentence-transformers not installed — using dummy embeddings. "
                "Run: pip install sentence-transformers"
            )
    return _st_model if _st_available else None


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

async def extract_text(file_content: bytes, file_type: str) -> str:
    """Extract plain text from a document byte payload."""
    ft = file_type.lower().lstrip(".")

    if ft == "pdf":
        try:
            from pypdf import PdfReader  # type: ignore
            reader = PdfReader(io.BytesIO(file_content))
            pages = [page.extract_text() or "" for page in reader.pages]
            return "\n\n".join(pages).strip()
        except Exception as e:
            logger.error("PDF extraction failed: %s", e)
            return ""

    if ft in ("docx", "doc"):
        try:
            from docx import Document  # type: ignore
            doc = Document(io.BytesIO(file_content))
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            return "\n\n".join(paragraphs).strip()
        except Exception as e:
            logger.error("DOCX extraction failed: %s", e)
            return ""

    if ft in ("txt", "md", "markdown"):
        try:
            return file_content.decode("utf-8").strip()
        except UnicodeDecodeError:
            return file_content.decode("latin-1").strip()

    logger.warning("Unsupported file type for extraction: %s", file_type)
    return ""


# ---------------------------------------------------------------------------
# Text chunking
# ---------------------------------------------------------------------------

def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    """
    Split text into overlapping word-count chunks.

    Strategy:
      1. Split on paragraph breaks or sentence ends to avoid mid-sentence cuts.
      2. Accumulate sentences into chunks of ~chunk_size words.
      3. The last `overlap` words of chunk N appear at the start of chunk N+1.
    """
    if not text.strip():
        return []

    # Split into sentence-like segments
    import re
    segments = re.split(r"(?<=\. )|(?<=\n\n)", text)
    segments = [s.strip() for s in segments if s.strip()]

    chunks: List[str] = []
    current_words: List[str] = []

    for segment in segments:
        seg_words = segment.split()
        current_words.extend(seg_words)

        if len(current_words) >= chunk_size:
            chunk_text_str = " ".join(current_words[:chunk_size])
            chunks.append(chunk_text_str)
            # Carry overlap words into the next chunk
            current_words = current_words[chunk_size - overlap:]

    # Flush remaining words as the last chunk
    if current_words:
        chunks.append(" ".join(current_words))

    return chunks


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------

async def embed_chunks(chunks: List[str]) -> List[List[float]]:
    """Return a 384-dim embedding for each chunk."""
    model = _get_st_model()

    if model is not None:
        try:
            embeddings = model.encode(chunks, show_progress_bar=False)
            return [emb.tolist() for emb in embeddings]
        except Exception as e:
            logger.error("Embedding failed: %s — falling back to dummy vectors", e)

    # Dummy fallback: zeros with chunk index as first element
    logger.warning("Using dummy embeddings (sentence-transformers unavailable)")
    result = []
    for i, _ in enumerate(chunks):
        vec = [0.0] * 384
        vec[0] = float(i)
        result.append(vec)
    return result


async def embed_query(query: str) -> List[float]:
    """Return a single 384-dim embedding for a query string."""
    embeddings = await embed_chunks([query])
    return embeddings[0]


# ---------------------------------------------------------------------------
# Full document processing (background task)
# ---------------------------------------------------------------------------

async def process_document(doc_id: int, db: Session) -> None:
    """
    Load a document record, extract text, chunk, embed, and persist chunks.
    Updates recruit_kb_documents.status to 'ready' or 'failed'.
    """
    try:
        row = db.execute(
            text(
                "SELECT id, organization_id, storage_path, raw_text, file_type "
                "FROM recruit_kb_documents WHERE id = :id"
            ),
            {"id": doc_id},
        ).fetchone()

        if not row:
            logger.error("process_document: doc %d not found", doc_id)
            return

        org_id = row.organization_id
        file_type = row.file_type

        # Get text: prefer raw_text already set, otherwise read from storage_path
        raw_text = row.raw_text or ""
        if not raw_text and row.storage_path and os.path.exists(row.storage_path):
            with open(row.storage_path, "rb") as fh:
                file_content = fh.read()
            raw_text = await extract_text(file_content, file_type)
            # Persist extracted text so reprocessing skips the file read
            db.execute(
                text("UPDATE recruit_kb_documents SET raw_text = :t WHERE id = :id"),
                {"t": raw_text, "id": doc_id},
            )
            db.commit()

        if not raw_text:
            db.execute(
                text(
                    "UPDATE recruit_kb_documents "
                    "SET status = 'failed', updated_at = NOW() WHERE id = :id"
                ),
                {"id": doc_id},
            )
            db.commit()
            logger.warning("process_document: no text extracted for doc %d", doc_id)
            return

        chunks = chunk_text(raw_text)
        embeddings = await embed_chunks(chunks)

        # Delete old chunks (for reprocessing)
        db.execute(
            text("DELETE FROM recruit_kb_chunks WHERE document_id = :id"),
            {"id": doc_id},
        )

        for idx, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            vec_str = "[" + ",".join(str(v) for v in emb) + "]"
            db.execute(
                text("""
                    INSERT INTO recruit_kb_chunks
                        (document_id, organization_id, chunk_index, content, embedding, token_count)
                    VALUES (:doc_id, :org_id, :idx, :content, :emb::vector, :tok)
                """),
                {
                    "doc_id": doc_id,
                    "org_id": org_id,
                    "idx": idx,
                    "content": chunk,
                    "emb": vec_str,
                    "tok": len(chunk.split()),
                },
            )

        db.execute(
            text("""
                UPDATE recruit_kb_documents
                SET status = 'ready', chunk_count = :n, updated_at = NOW()
                WHERE id = :id
            """),
            {"n": len(chunks), "id": doc_id},
        )
        db.commit()
        logger.info(
            "process_document: doc %d processed — %d chunks for org %d",
            doc_id, len(chunks), org_id,
        )

    except Exception as e:
        logger.exception("process_document: doc %d failed: %s", doc_id, e)
        try:
            db.execute(
                text(
                    "UPDATE recruit_kb_documents "
                    "SET status = 'failed', updated_at = NOW() WHERE id = :id"
                ),
                {"id": doc_id},
            )
            db.commit()
        except Exception as ex:
            logger.error("process_document: could not set failed status: %s", ex)


# ---------------------------------------------------------------------------
# Semantic retrieval
# ---------------------------------------------------------------------------

async def retrieve_relevant_chunks(
    query: str,
    org_id: int,
    db: Session,
    top_k: int = 5,
) -> List[str]:
    """
    Retrieve the most relevant KB chunks for a query using pgvector cosine similarity.
    Falls back to PostgreSQL full-text search if embedding is unavailable or returns nothing.
    """
    # Try vector search first
    try:
        query_emb = await embed_query(query)
        # Only use vector search with a real model (skip if dummy)
        model = _get_st_model()
        if model is not None:
            vec_str = "[" + ",".join(str(v) for v in query_emb) + "]"
            rows = db.execute(
                text("""
                    SELECT content
                    FROM recruit_kb_chunks
                    WHERE organization_id = :org_id
                    ORDER BY embedding <=> :qvec::vector
                    LIMIT :k
                """),
                {"org_id": org_id, "qvec": vec_str, "k": top_k},
            ).fetchall()
            if rows:
                return [r.content for r in rows]
    except Exception as e:
        logger.warning("Vector search failed, falling back to full-text: %s", e)

    # Full-text search fallback
    try:
        rows = db.execute(
            text("""
                SELECT content
                FROM recruit_kb_chunks
                WHERE organization_id = :org_id
                  AND to_tsvector('english', content) @@ plainto_tsquery('english', :query)
                LIMIT :k
            """),
            {"org_id": org_id, "query": query, "k": top_k},
        ).fetchall()
        return [r.content for r in rows]
    except Exception as e:
        logger.warning("Full-text search also failed: %s", e)
        return []
