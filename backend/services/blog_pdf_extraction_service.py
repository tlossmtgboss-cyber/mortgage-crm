"""
Blog PDF Extraction Service - Extract and process PDF content for AI content mining.

Handles:
- PDF text extraction with OCR fallback
- Page-by-page mapping for source attribution
- Concept extraction and topic mining
- Background job processing
"""

import os
import io
import re
import json
import logging
import uuid
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class PDFExtractionResult:
    """Result from PDF extraction."""

    def __init__(
        self,
        success: bool,
        full_text: str = "",
        page_map: Dict[int, str] = None,
        page_count: int = 0,
        concept_map: Dict[str, Any] = None,
        error: Optional[str] = None,
        metadata: Dict[str, Any] = None,
    ):
        self.success = success
        self.full_text = full_text
        self.page_map = page_map or {}
        self.page_count = page_count
        self.concept_map = concept_map or {}
        self.error = error
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "full_text_length": len(self.full_text),
            "page_count": self.page_count,
            "concept_count": len(self.concept_map.get("topics", [])),
            "error": self.error,
            "metadata": self.metadata,
        }


class BlogPDFExtractionService:
    """Service for extracting and processing PDF content for blog generation."""

    def __init__(self):
        self.enabled = True
        self._check_dependencies()
        logger.info("Blog PDF extraction service initialized")

    def _check_dependencies(self):
        """Check if required dependencies are available."""
        try:
            from PyPDF2 import PdfReader
            self.pypdf2_available = True
        except ImportError:
            self.pypdf2_available = False
            logger.warning("PyPDF2 not available - PDF extraction will be limited")

        try:
            import pytesseract
            from pdf2image import convert_from_path
            self.ocr_available = True
        except ImportError:
            self.ocr_available = False
            logger.warning("OCR dependencies not available - scanned PDFs won't be processed")

    def extract_pdf(
        self,
        pdf_path: str,
        use_ocr_fallback: bool = True,
        extract_concepts: bool = True,
    ) -> PDFExtractionResult:
        """
        Extract text and concepts from a PDF file.

        Args:
            pdf_path: Path to the PDF file
            use_ocr_fallback: Whether to use OCR if text extraction fails
            extract_concepts: Whether to extract concepts/topics from text

        Returns:
            PDFExtractionResult with extracted text and metadata
        """
        if not self.pypdf2_available:
            return PDFExtractionResult(
                success=False,
                error="PDF extraction not available - PyPDF2 not installed"
            )

        try:
            file_path = Path(pdf_path)
            if not file_path.exists():
                return PDFExtractionResult(
                    success=False,
                    error=f"File not found: {pdf_path}"
                )

            # Get file metadata
            metadata = {
                "file_name": file_path.name,
                "file_size": file_path.stat().st_size,
                "extracted_at": datetime.now(timezone.utc).isoformat(),
            }

            # Try standard text extraction first
            full_text, page_map, page_count = self._extract_text_pypdf2(pdf_path)

            # Check if extraction was successful (has meaningful content)
            if self._is_text_meaningful(full_text):
                metadata["extraction_method"] = "text"
            elif use_ocr_fallback and self.ocr_available:
                # Fallback to OCR for scanned documents
                logger.info(f"Text extraction minimal, trying OCR for {file_path.name}")
                full_text, page_map, page_count = self._extract_text_ocr(pdf_path)
                metadata["extraction_method"] = "ocr"
            else:
                metadata["extraction_method"] = "text_minimal"

            # Extract concepts if requested
            concept_map = {}
            if extract_concepts and self._is_text_meaningful(full_text):
                concept_map = self._extract_concepts(full_text)

            metadata["character_count"] = len(full_text)
            metadata["word_count"] = len(full_text.split())

            return PDFExtractionResult(
                success=True,
                full_text=full_text,
                page_map=page_map,
                page_count=page_count,
                concept_map=concept_map,
                metadata=metadata,
            )

        except Exception as e:
            logger.error(f"PDF extraction failed for {pdf_path}: {e}")
            return PDFExtractionResult(
                success=False,
                error=str(e)
            )

    def _extract_text_pypdf2(self, pdf_path: str) -> Tuple[str, Dict[int, str], int]:
        """Extract text using PyPDF2."""
        from PyPDF2 import PdfReader

        reader = PdfReader(pdf_path)
        page_count = len(reader.pages)
        page_map = {}
        full_text_parts = []

        for i, page in enumerate(reader.pages):
            try:
                text = page.extract_text() or ""
                page_map[i + 1] = text
                full_text_parts.append(text)
            except Exception as e:
                logger.warning(f"Failed to extract page {i + 1}: {e}")
                page_map[i + 1] = ""

        full_text = "\n\n".join(full_text_parts)
        return full_text, page_map, page_count

    def _extract_text_ocr(self, pdf_path: str) -> Tuple[str, Dict[int, str], int]:
        """Extract text using OCR (for scanned documents)."""
        import pytesseract
        from pdf2image import convert_from_path

        # Convert PDF pages to images
        images = convert_from_path(pdf_path, dpi=200)
        page_count = len(images)
        page_map = {}
        full_text_parts = []

        for i, image in enumerate(images):
            try:
                text = pytesseract.image_to_string(image)
                page_map[i + 1] = text
                full_text_parts.append(text)
            except Exception as e:
                logger.warning(f"OCR failed for page {i + 1}: {e}")
                page_map[i + 1] = ""

        full_text = "\n\n".join(full_text_parts)
        return full_text, page_map, page_count

    def _is_text_meaningful(self, text: str, min_words: int = 50) -> bool:
        """Check if extracted text has meaningful content."""
        if not text:
            return False
        words = text.split()
        # Check word count and that it's not just garbage characters
        if len(words) < min_words:
            return False
        # Check for reasonable character distribution
        alpha_ratio = sum(1 for c in text if c.isalpha()) / max(len(text), 1)
        return alpha_ratio > 0.4

    def _extract_concepts(self, text: str) -> Dict[str, Any]:
        """Extract concepts, topics, and key phrases from text."""
        concepts = {
            "topics": [],
            "key_phrases": [],
            "potential_titles": [],
            "sections": [],
            "statistics": [],
            "quotes": [],
        }

        # Split into paragraphs
        paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]

        # Extract section headers (lines that look like titles)
        for para in paragraphs:
            lines = para.split('\n')
            for line in lines:
                line = line.strip()
                # Heuristics for section headers
                if len(line) < 100 and len(line) > 5:
                    if line.isupper() or (line[0].isupper() and ':' in line):
                        concepts["sections"].append(line)
                    elif re.match(r'^(Chapter|Section|Part)\s+\d+', line, re.I):
                        concepts["sections"].append(line)

        # Extract potential topics (noun phrases, repeated terms)
        words = text.lower().split()
        word_freq = {}
        for word in words:
            word = re.sub(r'[^\w]', '', word)
            if len(word) > 4:  # Skip short words
                word_freq[word] = word_freq.get(word, 0) + 1

        # Get most frequent meaningful words as topics
        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
        stopwords = {'about', 'their', 'would', 'could', 'should', 'these', 'those',
                    'there', 'where', 'which', 'being', 'having', 'doing', 'going',
                    'after', 'before', 'between', 'through', 'during', 'under', 'above'}
        concepts["topics"] = [
            word for word, count in sorted_words[:30]
            if word not in stopwords and count > 2
        ]

        # Extract statistics and numbers
        stat_patterns = [
            r'\d+(?:\.\d+)?%',  # Percentages
            r'\$[\d,]+(?:\.\d{2})?',  # Dollar amounts
            r'\d+(?:,\d{3})+',  # Large numbers with commas
        ]
        for pattern in stat_patterns:
            matches = re.findall(pattern, text)
            concepts["statistics"].extend(matches[:10])

        # Extract quotes (text in quotation marks)
        quote_matches = re.findall(r'"([^"]{20,200})"', text)
        concepts["quotes"] = quote_matches[:10]

        # Generate potential blog titles based on content
        concepts["potential_titles"] = self._generate_title_suggestions(
            concepts["topics"][:10],
            concepts["sections"][:5]
        )

        return concepts

    def _generate_title_suggestions(
        self,
        topics: List[str],
        sections: List[str]
    ) -> List[str]:
        """Generate potential blog title suggestions based on extracted concepts."""
        suggestions = []

        # Title templates
        templates = [
            "Understanding {topic}: A Complete Guide",
            "How {topic} Impacts Your {related}",
            "The Truth About {topic}",
            "{number} Things to Know About {topic}",
            "Why {topic} Matters for {audience}",
            "{topic} Explained: What You Need to Know",
            "The Ultimate Guide to {topic}",
        ]

        audiences = ["Homebuyers", "First-Time Buyers", "Homeowners", "Investors"]
        related_terms = ["Mortgage", "Home Loan", "Financing", "Investment"]
        numbers = ["5", "7", "10", "3"]

        for topic in topics[:5]:
            topic_title = topic.title()
            for template in templates[:3]:
                title = template.format(
                    topic=topic_title,
                    related=related_terms[0],
                    audience=audiences[0],
                    number=numbers[0],
                )
                suggestions.append(title)

        # Also use section headers as title inspiration
        for section in sections[:3]:
            if len(section) < 60:
                suggestions.append(section.title())

        return suggestions[:15]

    async def process_document_async(
        self,
        document_id: str,
        pdf_path: str,
        user_id: int,
        db_session,
    ) -> bool:
        """
        Process a PDF document asynchronously and update the database.

        Args:
            document_id: ID of the BlogSourceDocument record
            pdf_path: Path to the PDF file
            user_id: User who owns the document
            db_session: Database session for updates

        Returns:
            True if processing succeeded
        """
        from models.ai_daily_blog import BlogSourceDocument

        try:
            # Get the document record
            document = db_session.query(BlogSourceDocument).filter_by(
                id=document_id,
                user_id=user_id
            ).first()

            if not document:
                logger.error(f"Document {document_id} not found")
                return False

            # Extract the PDF
            result = self.extract_pdf(pdf_path)

            if result.success:
                # Update the document record
                document.extracted_text = result.full_text
                document.page_map_json = result.page_map
                document.concept_map_json = result.concept_map
                document.page_count = result.page_count
                document.processed = True
                document.processing_error = None
            else:
                document.processed = False
                document.processing_error = result.error

            db_session.commit()
            return result.success

        except Exception as e:
            logger.error(f"Async document processing failed: {e}")
            if db_session:
                try:
                    document = db_session.query(BlogSourceDocument).filter_by(id=document_id).first()
                    if document:
                        document.processing_error = str(e)
                        db_session.commit()
                except Exception as e:
                    logger.exception(f"Failed to save processing error to document record: {e}")
            return False

    def get_content_chunks(
        self,
        text: str,
        chunk_size: int = 2000,
        overlap: int = 200,
    ) -> List[Dict[str, Any]]:
        """
        Split text into overlapping chunks for LLM processing.

        Args:
            text: Full text to chunk
            chunk_size: Target size of each chunk in characters
            overlap: Overlap between chunks

        Returns:
            List of chunk dicts with text and metadata
        """
        chunks = []

        # Split by paragraphs first
        paragraphs = text.split('\n\n')
        current_chunk = ""
        chunk_start = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # If adding this paragraph exceeds chunk size, save current and start new
            if len(current_chunk) + len(para) > chunk_size and current_chunk:
                chunks.append({
                    "text": current_chunk.strip(),
                    "start_pos": chunk_start,
                    "end_pos": chunk_start + len(current_chunk),
                    "chunk_index": len(chunks),
                })
                # Start new chunk with overlap
                overlap_text = current_chunk[-overlap:] if len(current_chunk) > overlap else current_chunk
                current_chunk = overlap_text + "\n\n" + para
                chunk_start = chunk_start + len(current_chunk) - len(overlap_text) - len(para) - 2
            else:
                if current_chunk:
                    current_chunk += "\n\n" + para
                else:
                    current_chunk = para
                    chunk_start = 0

        # Don't forget the last chunk
        if current_chunk:
            chunks.append({
                "text": current_chunk.strip(),
                "start_pos": chunk_start,
                "end_pos": chunk_start + len(current_chunk),
                "chunk_index": len(chunks),
            })

        return chunks

    def find_source_page(
        self,
        search_text: str,
        page_map: Dict[int, str],
        threshold: float = 0.6,
    ) -> Optional[int]:
        """
        Find which page contains the source text.

        Args:
            search_text: Text snippet to find
            page_map: Page number to text mapping
            threshold: Minimum match ratio

        Returns:
            Page number if found, None otherwise
        """
        search_words = set(search_text.lower().split()[:20])  # First 20 words

        best_page = None
        best_ratio = 0

        for page_num, page_text in page_map.items():
            page_words = set(page_text.lower().split())
            if not page_words:
                continue

            # Calculate word overlap ratio
            overlap = len(search_words & page_words)
            ratio = overlap / len(search_words) if search_words else 0

            if ratio > best_ratio:
                best_ratio = ratio
                best_page = page_num

        return best_page if best_ratio >= threshold else None


# Create singleton instance
blog_pdf_extraction_service = BlogPDFExtractionService()
