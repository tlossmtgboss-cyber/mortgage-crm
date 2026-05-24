# Guideline RAG Pipeline Design

**Date:** 2026-05-24
**Status:** Approved
**Mockup:** `frontend/public/guideline-rag-mockup.html`

## Overview

Build a full guideline RAG pipeline so Aria and the LO-facing search UI can answer mortgage guideline questions backed by actual indexed guideline documents — not just Claude's training data. The system ingests PDFs from all major agencies (Fannie Mae, Freddie Mac, FHA, VA, USDA) plus specialty programs (Non-QM, AIO, DPA, Construction, Renovation, Reverse Mortgage), chunks them into ~500-token sections, embeds them with pgvector, and serves them through vector search with citations.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Storage | Enhance existing `GuidelineSection` table | Already has section splitting, AI analysis, keyword search. Just needs pgvector + better chunking. |
| Ingestion | Manual upload + automated scraping | Company overlays uploaded manually, agency updates scraped on schedule. |
| Retrieval UX | Silent injection + cited answers | Aria silently uses guidelines for routine context; provides citations when LO explicitly asks. |
| Overlay handling | Show both, flag difference | Always present both agency guideline and company overlay, highlighted so LO sees conflicts. |
| Embedding model | text-embedding-3-small (1536 dims) | Already used for borrower memory in `aria_memory/embedding_service.py`. |

## Architecture

### Existing Infrastructure (Reused)

| Component | File | What It Does |
|-----------|------|--------------|
| `UnderwritingGuideline` model | `backend/models/call_monitoring_models.py:753` | Stores guideline metadata, full text, key_points, structured_rules |
| `GuidelineSection` model | `backend/models/call_monitoring_models.py:826` | Stores sections with content, section_number, topics. Has `content_embedding ARRAY(Float)` (to be converted) |
| `guidelines_service.py` | `backend/services/call_monitoring/guidelines_service.py` | Text extraction (PDF/DOCX/HTML/TXT), AI analysis with Claude, section splitting, keyword search, Claude-powered Q&A |
| `retrieval_service.py` | `backend/services/aria_memory/retrieval_service.py` | pgvector cosine search with Redis caching, audit logging. Has `scope="guideline"` stub (Phase B) |
| `embedding_service.py` | `backend/services/aria_memory/embedding_service.py` | text-embedding-3-small, sync/async, PII scrubbing |
| `AriaContextLoader` | `backend/services/aria_memory/context_loader.py` | Loads borrower context for voice calls. No guideline context yet. |
| `knowledge_tools.py` | `backend/aria/tools/knowledge_tools.py` | `answer_guideline_question()` — currently falls back to Claude training data with disclaimer |
| `aria_prompts.py` | `backend/aria/agents/aria_prompts.py` | System prompts with `{memory_context}` placeholder. No `{guideline_context}` yet. |

### New/Modified Components

```
                    ┌─────────────────────────┐
                    │    Admin Upload UI       │
                    │  (existing KB routes)    │
                    └──────────┬──────────────┘
                               │ PDF/DOCX
                               ▼
                    ┌─────────────────────────┐
                    │  guidelines_service.py   │
                    │  ─────────────────────   │
                    │  extract_text()          │  ◄── existing
                    │  analyze_content()       │  ◄── existing
                    │  split_into_sections()   │  ◄── improved chunking
                    │  embed_sections()        │  ◄── NEW
                    │  store_with_vectors()    │  ◄── NEW
                    └──────────┬──────────────┘
                               │ chunks + embeddings
                               ▼
              ┌─────────────────────────────────────┐
              │   guideline_sections table           │
              │   ───────────────────────────        │
              │   content_embedding Vector(1536)     │  ◄── converted from ARRAY(Float)
              │   + HNSW index                       │  ◄── NEW
              │   embedding_model, token_count       │  ◄── NEW
              │   chunk_hash                         │  ◄── NEW
              └──────────┬──────────────────────────┘
                         │
          ┌──────────────┼──────────────────┐
          ▼              ▼                  ▼
   ┌────────────┐ ┌────────────────┐ ┌──────────────┐
   │ Search UI  │ │ Aria Tools     │ │ Aria Prompt  │
   │ (Answer/   │ │ (RAG search,   │ │ Injection    │
   │  Citations/│ │  comparison,   │ │ ({guideline  │
   │  Sources)  │ │  overlay check)│ │  _context})  │
   └────────────┘ └────────────────┘ └──────────────┘
```

## Schema Changes

### GuidelineSection — Modified Columns

```python
# Convert existing column
content_embedding = Column(Vector(1536))  # was ARRAY(Float)

# New columns
embedding_model = Column(String(50), default="text-embedding-3-small")
token_count = Column(Integer)
chunk_hash = Column(String(64))  # SHA-256 of content for dedup
```

**New index:**
```sql
CREATE INDEX idx_guideline_sections_embedding
ON guideline_sections USING hnsw (content_embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
```

### UnderwritingGuideline — New Columns

```python
embedding_status = Column(String(20), default="pending")  # pending, processing, complete, failed
chunk_count = Column(Integer, default=0)
overlay_priority = Column(Integer, default=4)  # 1=company, 2=investor, 3=state, 4=agency
```

### Migration

Inline migration in the guideline processing startup (same pattern as existing `checkfirst=True` + ALTER TABLE ADD COLUMN IF NOT EXISTS):
1. Convert `content_embedding` column type from `real[]` to `vector(1536)`
2. Add HNSW index
3. Add new columns with defaults

## Ingestion Pipeline

### Improved Chunking (`split_into_sections()`)

The existing function splits on structural headers (Fannie Mae `B3-3.1-07` pattern, numbered sections) or falls back to 2000-char paragraphs. Changes:

1. **Target ~500 tokens** (~2000 chars) per chunk instead of the current 2000-char fallback
2. **If a structural section exceeds 500 tokens**, split on paragraph boundaries within it
3. **50-token overlap** between consecutive chunks for context continuity
4. **Preserve section metadata**: Each sub-chunk inherits `section_number`, `section_title`, and gets a `chunk_index` suffix (e.g., `B3-3.1-07.1`, `B3-3.1-07.2`)
5. **Token counting**: Use tiktoken (`cl100k_base` encoding) for accurate counts

### Embedding Generation

New function in `guidelines_service.py`:

```python
async def embed_guideline_sections(guideline_id: str):
    """Generate embeddings for all sections of a guideline."""
    # 1. Load all sections for this guideline
    # 2. Filter to sections where chunk_hash has changed or embedding is NULL
    # 3. Batch embed using embedding_service.generate_embedding_async()
    # 4. Update content_embedding, embedding_model, token_count
    # 5. Update guideline.embedding_status and chunk_count
```

Batch processing: Process 20 sections at a time to avoid OpenAI rate limits. Use asyncio.gather for parallelism within each batch.

### Content Hash Dedup

On re-ingestion (guideline update):
1. Compute SHA-256 hash of each chunk's content
2. Compare against existing `chunk_hash` values
3. Only re-embed chunks where hash changed
4. Delete chunks that no longer exist in the new version
5. Track version via `UnderwritingGuideline.version`

### Automated Scraping

Extend existing `guideline_updates_scraper.py` and `mortgage_guidelines_scraper.py`:
1. When scraper detects a new update, download the full document (not just the summary)
2. Feed through the same ingestion pipeline
3. Content hash dedup prevents duplicate embedding of unchanged sections
4. Scraper runs on schedule (existing cron pattern)

## Retrieval & Search

### Extending `retrieval_service.py`

The existing `retrieve()` method has a `scope` parameter with `"memory"` implemented and `"guideline"` stubbed. Implementation:

```python
# scope="guideline" branch in retrieve()
async def _retrieve_guidelines(self, query_embedding, filters):
    """
    Vector search over guideline_sections table.
    
    Filters applied BEFORE vector search:
    - agency/source (from UnderwritingGuideline.guideline_type)
    - loan_program
    - category
    - is_active
    - organization_id (for company overlays) OR NULL (for agency guidelines)
    
    Returns: List[GuidelineResult] with:
    - content, section_number, section_title, page_number
    - guideline_name, guideline_type, loan_program
    - similarity_score, overlay_priority
    """
```

### Hybrid Scoring

1. **Primary**: pgvector cosine similarity (threshold: 0.3, same as memory)
2. **Boost**: If query terms appear in `section_title` or `topics`, add score bonus
3. **Overlay ordering**: Results sorted by `overlay_priority` (company first, then agency) within the same similarity tier
4. **Top-k**: Default 5, configurable per tool

### Caching

Same Redis pattern as borrower memory:
- Cache key: `aria:cache:guideline:{query_hash}:{filter_hash}`
- TTL: 300s (guidelines change less frequently than borrower context)
- Invalidate on guideline re-ingestion

## Aria Integration

### New Tools

Register in `backend/aria/tools/knowledge_tools.py`:

```python
@mortgage_tool(
    name="search_guidelines_rag",
    description="Search mortgage underwriting guidelines by question. Returns cited answers from indexed guideline documents.",
    agent_roles=["compliance_checker", "loan_processor", "manager", "receptionist"]
)
async def search_guidelines_rag(
    query: str,
    loan_program: Optional[str] = None,
    agency: Optional[str] = None,
    include_overlays: bool = True,
) -> dict:
    """
    Returns:
    - answer: AI-synthesized answer from retrieved chunks
    - citations: List of {section_number, section_title, page_number, guideline_name, snippet}
    - sources: List of {guideline_name, source_url, citation_count}
    - confidence: float (0-1)
    """

@mortgage_tool(
    name="compare_across_agencies",
    description="Compare a specific guideline topic across all agencies and overlays. Returns comparison table.",
    agent_roles=["compliance_checker", "loan_processor", "manager"]
)
async def compare_across_agencies(
    topic: str,  # e.g., "minimum credit score", "DTI limits", "reserve requirements"
) -> dict:
    """
    Returns:
    - topic: str
    - comparison: List of {agency, guideline, requirement, citation}
    - overlay_conflicts: List of {agency_rule, overlay_rule, difference}
    """

@mortgage_tool(
    name="check_overlay_conflict",
    description="Check if company overlay differs from agency guideline for a specific rule.",
    agent_roles=["compliance_checker", "loan_processor"]
)
async def check_overlay_conflict(
    rule_type: str,  # e.g., "min_credit_score", "max_dti", "max_ltv"
    loan_program: str,
) -> dict:
    """
    Returns:
    - has_conflict: bool
    - agency_rule: {value, source, citation}
    - overlay_rule: {value, source, citation}
    - effective_rule: the more restrictive value
    """
```

### Prompt Injection

Extend `AriaContextLoader.load_context()`:

```python
# After loading borrower context, add guideline context
if loan and loan.loan_program:
    guideline_chunks = await retrieval_service.retrieve(
        scope="guideline",
        query=f"{loan.loan_program} eligibility requirements",
        filters={"loan_program": loan.loan_program},
        top_k=3,
    )
    context.guideline_context = format_guideline_context(guideline_chunks)
```

Add `{guideline_context}` placeholder to `aria_prompts.py` system prompts:

```
{guideline_context}

When answering questions about guidelines:
- If the borrower's loan context is known, silently apply relevant guidelines
- If the LO explicitly asks a guideline question, cite the specific section
- Always flag when your company overlay differs from the agency guideline
```

### Answer Formatting

Two modes based on query intent:

**Silent injection** (routine conversation):
- Aria references guideline rules naturally without explicit citations
- Example: "His 645 clears the 580 minimum for 3.5% down"

**Cited answer** (explicit guideline question):
- Structured response with inline citations: `[FHA 4000.1 p.204]`
- Tables for numeric comparisons (credit scores, DTI limits)
- Company overlay callout (amber highlight) when conflict exists
- Confidence score and disclaimer

## Knowledge & Memory Integration

Guidelines are not a standalone corpus — they need to be a first-class part of Aria's knowledge architecture, cross-referenced with borrower memory and unified with the existing AI Knowledge Base.

### Context Loading Priority

When Aria assembles context for a conversation, load in this order (each layer builds on the previous):

```
1. Borrower Identity        — name, contact info, relationship to LO
2. Active Loan State         — loan_program, stage, amount, property
3. Guideline Context (NEW)   — top 3 relevant chunks for this loan_program
4. Borrower Preferences      — communication preferences, timezone, language
5. Episodic Facts            — recent conversation facts from agent_memories
6. Cross-Reference Alerts    — guideline thresholds vs borrower facts (NEW)
7. Last Interaction Summary  — what happened on the last call
```

Guidelines load at position 3 (after loan state, before borrower details) because the loan program determines which guidelines are relevant. Cross-reference alerts at position 6 are derived from combining positions 3 and 5.

Total context budget: ~600-800 tokens for guideline context (guideline chunks are pre-summarized to fit). Same budget discipline as borrower memory — never exceed the context window.

### Memory-to-Guideline Cross-Referencing

When loading borrower facts from `agent_memories`, detect financial facts and automatically cross-reference against guideline thresholds:

```python
# In AriaContextLoader, after loading borrower facts and guideline context
async def cross_reference_facts_with_guidelines(
    borrower_facts: list[RetrievedFact],
    loan_program: str,
    guidelines: list[GuidelineResult],
) -> list[CrossReferenceAlert]:
    """
    Detects borrower facts that have guideline implications.
    
    Examples:
    - Fact: "credit score 645" + FHA guideline min 580 → "Eligible (65 points above minimum)"
    - Fact: "credit score 645" + Company overlay min 640 → "Warning: only 5 points above overlay minimum"
    - Fact: "DTI 42%" + FHA manual UW max 43% → "Within limit but near threshold"
    - Fact: "Ch7 BK discharged 2023" + FHA wait 2yr → "Eligible as of 2025"
    
    Returns alerts sorted by urgency (near-threshold first).
    """
```

Cross-reference rules engine:
- **Credit score** → check against min score for loan_program (agency + overlay)
- **DTI ratio** → check against max DTI (manual UW vs AUS)
- **LTV** → check against max LTV for property type + occupancy
- **Derogatory events** (BK, foreclosure, short sale) → check waiting periods
- **Reserves** → check against minimum for property type

Alerts are injected into context at position 6 and formatted as:
```
⚠ GUIDELINE ALERT: Borrower credit score (645) is only 5 points above your company overlay minimum (640) for FHA. Agency minimum is 580.
```

### AI Knowledge Base Unification

The existing `AIKnowledgeBase` table stores manual knowledge entries (loan products, compliance notes, sales scripts, company policies) but has no embeddings. Unify it with the guideline retrieval pipeline:

**Schema addition to `AIKnowledgeBase`:**
```python
content_embedding = Column(Vector(1536))  # NEW — same as GuidelineSection
embedding_model = Column(String(50))
chunk_hash = Column(String(64))
```

**Unified retrieval in `retrieval_service.py`:**
```python
# scope="knowledge" — searches BOTH guideline_sections AND ai_knowledge_base
async def _retrieve_knowledge(self, query_embedding, filters):
    """
    Unified vector search across:
    1. guideline_sections (agency guidelines, overlays)
    2. ai_knowledge_base (company policies, loan products, compliance notes)
    
    Results merged and ranked by similarity.
    Source type included in response so UI can differentiate.
    """
```

**Embedding on upload:** When a knowledge base entry is created/updated via the existing `/api/v1/ai/knowledge-base` routes, generate and store the embedding. For entries longer than 500 tokens, chunk them (same as guidelines).

**Categories that benefit most from vector search:**
- `loan_products` — "What are our jumbo options?" → retrieves product sheets
- `compliance` — "What's our TRID timeline?" → retrieves compliance policies
- `company_policies` — "What's our lock extension policy?" → retrieves internal docs
- `underwriting` — Already covered by guidelines, but company-specific notes go here

### Guideline-Derived Insight Storage

When Aria combines borrower data with guideline rules and derives a new insight, store it as a special memory type for future conversations:

```python
# New memory_type value for agent_memories
memory_type = "guideline_insight"  # joins existing: fact, preference, context, insight, directive
```

**What gets stored:**
- Cross-reference results: "Borrower is 5 points above FHA overlay minimum (645 vs 640)"
- Eligibility determinations: "Eligible for FHA, VA. Not yet eligible for conventional (1yr remaining on BK wait)"
- Overlay conflicts identified: "Company overlay requires 640 vs agency 580 for FHA"

**Guardrails (per existing memory architecture):**
1. **Tagged as derived**: `source_type="guideline_cross_reference"` — not a verified fact from the borrower
2. **Auto-expires**: `expires_at` set to 30 days — financial data changes, don't let stale insights persist
3. **Superseded on re-calculation**: If borrower facts update (new credit pull, stage change), old insights are superseded
4. **Not used for compliance decisions**: Disclaimer attached — these are AI-derived, not official determinations
5. **Audit logged**: Every derived insight logged with source guideline, source fact, and derivation logic

**When insights are created:**
- After each call where financial facts are discussed
- When a loan stage changes (triggers re-evaluation against stage-specific guidelines)
- On guideline re-ingestion (existing insights may be stale if rules changed)

**When insights are recalled:**
- At the start of the next conversation with this borrower
- Injected at context position 6 (cross-reference alerts) alongside live cross-references
- Stale insights (>30 days) are recalculated rather than recalled

## Search UI

### Frontend Route

New page in the React SPA at `/guideline-search` matching the approved mockup:

**Components:**
- `GuidelineSearchPage` — main layout with sidebar + content
- `SourceCheckboxes` — Fannie Mae, Freddie Mac, FHA, VA, USDA, Non-QM, AIO, DPA, Construction, Renovation, Reverse Mortgage
- `QueryLibrary` — saved queries per user (stored in `user_preferences` or localStorage)
- `SearchResults` — tabbed view: Answer / Citations / Sources
- `ComparisonChart` — full agency comparison table, triggered from Sources tab

**API Endpoints (new):**
- `POST /api/v1/guidelines/search` — vector search with filters, returns answer + citations + sources
- `GET /api/v1/guidelines/compare/{topic}` — comparison chart data across all agencies
- `POST /api/v1/guidelines/library` — save/list user's saved queries

### Answer Tab
- AI-synthesized answer with inline citation pills (clickable, show source + page)
- Tables for structured comparisons (credit score tiers, DTI breakdowns)
- Company overlay callout block (amber border + background)
- Follow-up suggestions
- Disclaimer footer
- Copy / thumbs up / thumbs down actions

### Citations Tab
- Numbered cards in 2-column grid
- Each card: document name, section/page, link-out icon
- Company overlay citations highlighted amber

### Sources Tab
- Document list with citation counts
- Click to open comparison chart (for cross-agency topics)
- Link to original document source URL

### Comparison Chart
- Full-width table: Agency column + Guidelines column
- Detailed per-agency breakdowns with bullet points
- Links to specific guideline sections
- Company overlay row at bottom (amber background)

## Comparison Charts

Pre-built comparison topics extracted from `structured_rules`:
- Minimum Credit Score
- Maximum DTI Ratios
- Maximum LTV
- Reserve Requirements
- Bankruptcy/Foreclosure Waiting Periods
- Down Payment Requirements

Generated from `UnderwritingGuideline.structured_rules` JSON across all active guidelines. Cached and regenerated when guidelines are re-ingested.

## Testing

- Unit tests for improved chunking (token count accuracy, overlap, section inheritance)
- Unit tests for vector search query construction and filtering
- Integration test: upload a small guideline PDF → verify chunks created with embeddings
- Integration test: search query → verify relevant chunks returned with citations
- Integration test: overlay conflict detection returns correct comparison

## Performance Considerations

- HNSW index with `m=16, ef_construction=64` balances recall vs build time
- Batch embedding (20 sections/batch) avoids OpenAI rate limits
- Redis cache (300s TTL) for repeated guideline queries
- Content hash dedup avoids re-embedding unchanged content
- Retrieval filters applied before vector search to reduce candidate set
