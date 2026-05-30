"""
Perennia AI - Comprehensive Test Configuration & Fixtures

Layered Testing Strategy:
- unit: Fast isolated tests with mocked dependencies
- integration: Tests with real external services
- e2e: Full conversation flow tests
- regression: Golden response comparisons
"""
import logging
import pytest
import os
import json
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from dataclasses import dataclass

# Load environment variables from .env file BEFORE any other imports
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

# Signal to main.py startup event to skip DB-dependent operations
# (TestClient triggers startup before dependency overrides are in effect)
os.environ["TESTING"] = "1"

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from fastapi.testclient import TestClient
from io import BytesIO

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

# Pre-import model submodules BEFORE `from main import app` so they are fully
# loaded before pytest's assertion rewriter intercepts them.
import models.smart_docs_models  # noqa: F401
import models.sms_models  # noqa: F401

from main import app
from database import get_db

# =============================================================================
# DATABASE FIXTURES
# =============================================================================

# Disable mutation audit logging during tests
os.environ.setdefault("ENABLE_MUTATION_AUDIT", "false")

# Default to local PostgreSQL. Override via TEST_DATABASE_URL env var.
# PostgreSQL is REQUIRED — SQLite cannot handle JSONB, ARRAY, INET, TSVECTOR.
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://localhost:5432/test_perennia",
)

# Fix postgres:// to postgresql:// for SQLAlchemy
if TEST_DATABASE_URL.startswith("postgres://"):
    TEST_DATABASE_URL = TEST_DATABASE_URL.replace("postgres://", "postgresql://", 1)

test_engine = create_engine(TEST_DATABASE_URL)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="session")
def db_engine():
    """Create test database engine for the session.

    Uses Base.metadata.create_all() against PostgreSQL to create all ORM
    tables in correct dependency order with full type support.
    """
    from db import Base
    from tests.test_db_helper import create_all_tables
    # Import models so their tables are registered on Base.metadata
    try:
        from database.models import Lead, Loan, User  # noqa: F401
    except Exception as e:
        logger.debug(f"Model import skipped in db_engine: {e}")

    # Drop and recreate all tables for a clean test run.
    # Uses per-table creation to handle missing FK targets from factory models.
    create_all_tables(Base, test_engine)

    # Create lightweight tables used only by estimate-parser tests
    # (these are NOT ORM models — they use raw SQL in the route handlers)
    with test_engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS estimate_parse_cache (
                id SERIAL PRIMARY KEY,
                doc_hash TEXT UNIQUE NOT NULL,
                parsed_json TEXT,
                confidence_score REAL,
                needs_review INTEGER DEFAULT 0,
                source_type TEXT,
                access_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS estimate_parse_failures (
                id SERIAL PRIMARY KEY,
                request_id TEXT,
                doc_hash TEXT,
                error_stage TEXT,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS estimate_comparisons (
                id TEXT PRIMARY KEY,
                user_id INTEGER,
                session_id TEXT,
                estimate_a_hash TEXT,
                estimate_b_hash TEXT,
                winner TEXT,
                winner_reason TEXT,
                savings_amount REAL,
                converted INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        conn.commit()

    yield test_engine

    # Clean up after the full test session.
    #
    # Prefer DROP SCHEMA ... CASCADE over Base.metadata.drop_all(): the latter
    # emits a per-constraint "ALTER TABLE ... DROP CONSTRAINT" for every
    # use_alter=True ForeignKey, and several factory/feature tables (e.g.
    # purl_loans' self/forward FKs) declare those constraints WITHOUT an explicit
    # name. SQLAlchemy cannot compile a DROP for an unnamed constraint and raises
    # CompileError ("it has no name") / the constraint may not even exist under
    # that name in the DB ("constraint ... does not exist"), erroring teardown.
    # A schema-level CASCADE drop removes everything in one statement, never
    # needing a constraint name. We guard every step so teardown can NEVER fail
    # the session.
    try:
        with test_engine.begin() as _conn:
            _conn.execute(text("DROP SCHEMA public CASCADE"))
            _conn.execute(text("CREATE SCHEMA public"))
    except Exception as _e:
        logger.warning(f"Teardown schema reset failed, falling back to drop_all: {_e}")
        try:
            Base.metadata.drop_all(bind=test_engine)
        except Exception as _e2:
            logger.warning(f"Teardown drop_all ignored (non-fatal): {_e2}")


@pytest.fixture(scope="function")
def db_session(db_engine):
    """Create a new database session for each test with rollback"""
    connection = db_engine.connect()
    transaction = connection.begin()
    session = TestSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="function")
def client(db_session):
    """Create test client with database session override"""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# =============================================================================
# AUTHENTICATION FIXTURES
# =============================================================================

class MockUser:
    """Mock user for authenticated tests"""
    def __init__(
        self,
        id: int = 1,
        email: str = "test@example.com",
        organization_id: int = 1,
        role: str = "loan_officer",
        is_active: bool = True,
        **kwargs
    ):
        self.id = id
        self.email = email
        self.organization_id = organization_id
        self.role = role
        self.is_active = is_active
        # Add any additional attributes
        for key, value in kwargs.items():
            setattr(self, key, value)


@pytest.fixture
def mock_user():
    """Create a mock authenticated user"""
    return MockUser()


@pytest.fixture
def mock_admin_user():
    """Create a mock admin user"""
    return MockUser(id=2, email="admin@example.com", role="admin")


@pytest.fixture
def auth_headers():
    """Generate auth headers for testing"""
    return {"Authorization": "Bearer test_token_123"}


@pytest.fixture
def lo_auth_headers():
    """Generate LO auth headers for testing (used by legacy tests)"""
    return {"Authorization": "Bearer lo_test_token_123"}


@pytest.fixture
def application_id():
    """Return test application ID"""
    return 1


@pytest.fixture(scope="function")
def authenticated_client(db_session, mock_user):
    """Create test client with authentication mocked"""
    from main import get_current_user, get_current_user_flexible
    from auth.dependencies import (
        get_current_user as auth_dep_gcu,
        get_current_user_flexible as auth_dep_gcuf,
    )

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    async def override_get_current_user():
        return mock_user

    async def override_get_current_user_flexible():
        return mock_user

    # Override all auth-related dependencies — both main.py and auth.dependencies references
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_current_user_flexible] = override_get_current_user_flexible
    app.dependency_overrides[auth_dep_gcu] = override_get_current_user
    app.dependency_overrides[auth_dep_gcuf] = override_get_current_user_flexible

    # Also override route-specific auth wrappers
    try:
        from routes import workflow_sla_routes
        # Store original values
        original_get_current_user = workflow_sla_routes._get_current_user
        original_get_db = workflow_sla_routes._get_db

        # Override the internal auth function
        async def mock_auth(*args, **kwargs):
            return mock_user

        workflow_sla_routes._get_current_user = mock_auth
        workflow_sla_routes._get_db = lambda: (yield db_session)
    except ImportError:
        original_get_current_user = None
        original_get_db = None

    with TestClient(app) as test_client:
        yield test_client

    # Restore original values
    if original_get_current_user is not None:
        try:
            workflow_sla_routes._get_current_user = original_get_current_user
            workflow_sla_routes._get_db = original_get_db
        except Exception as e:
            logger.debug(f"Failed to restore workflow_sla_routes overrides in authenticated_client: {e}")

    app.dependency_overrides.clear()


# Alias for backward compatibility with tests using 'client' fixture
# Tests that need auth should use 'authenticated_client' instead
@pytest.fixture(scope="function")
def auth_client(authenticated_client):
    """Alias for authenticated_client"""
    return authenticated_client


# =============================================================================
# MOCK TOOL RESULTS
# =============================================================================

@dataclass
class MockToolResult:
    """Standard mock result for tool calls"""
    status: str = "success"
    data: Dict[str, Any] = None
    message: str = ""
    error: Optional[str] = None

    def __post_init__(self):
        if self.data is None:
            self.data = {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "data": self.data,
            "message": self.message,
            "error": self.error,
        }


@pytest.fixture
def mock_tool_success():
    """Factory for successful tool results"""
    def _create(data: Dict[str, Any], message: str = "Success"):
        return MockToolResult(status="success", data=data, message=message)
    return _create


@pytest.fixture
def mock_tool_error():
    """Factory for error tool results"""
    def _create(error: str, message: str = ""):
        return MockToolResult(status="error", error=error, message=message or error)
    return _create


# =============================================================================
# AGENT FIXTURES
# =============================================================================

@pytest.fixture
def mock_openai_client():
    """Mock OpenAI client for agent tests"""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Mock AI response"
    mock_response.choices[0].message.tool_calls = None
    mock_response.usage.total_tokens = 500
    mock_response.usage.prompt_tokens = 400
    mock_response.usage.completion_tokens = 100

    mock_client.chat.completions.create = MagicMock(return_value=mock_response)
    return mock_client


@pytest.fixture
def mock_anthropic_client():
    """Mock Anthropic client for agent tests"""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock()]
    mock_response.content[0].text = "Mock Claude response"
    mock_response.usage.input_tokens = 400
    mock_response.usage.output_tokens = 100

    mock_client.messages.create = MagicMock(return_value=mock_response)
    return mock_client


@pytest.fixture
def agent_context():
    """Standard agent context for tests"""
    return {
        "user_id": "test-user-123",
        "session_id": "test-session-456",
        "loan_id": "test-loan-789",
        "timestamp": datetime.now().isoformat(),
        "metadata": {},
    }


# =============================================================================
# LEAD & LOAN FIXTURES
# =============================================================================

@pytest.fixture
def sample_lead():
    """Sample lead data for tests"""
    return {
        "id": "lead-123",
        "first_name": "John",
        "last_name": "Smith",
        "email": "john.smith@example.com",
        "phone": "+15551234567",
        "status": "new",
        "source": "website",
        "loan_purpose": "purchase",
        "estimated_amount": 400000,
        "estimated_credit_score": 740,
        "property_type": "single_family",
        "created_at": datetime.now().isoformat(),
    }


@pytest.fixture
def sample_loan():
    """Sample loan data for tests"""
    return {
        "id": "loan-456",
        "loan_number": "2024-001234",
        "borrower_name": "John Smith",
        "loan_amount": 400000,
        "interest_rate": 6.875,
        "loan_type": "conventional",
        "property_address": "123 Main St, Austin, TX 78701",
        "status": "processing",
        "loan_officer_id": "lo-789",
        "created_at": datetime.now().isoformat(),
    }


@pytest.fixture
def sample_client_file(db_session):
    """Create a real ClientFile linked to a real Lead in the test DB."""
    from database.models import Lead
    from services.client_file_service import ensure_client_file
    lead = Lead(
        organization_id=1,
        first_name="Test",
        last_name="Client",
        email="test.client@example.com",
        owner_id=1,
    )
    db_session.add(lead)
    db_session.flush()
    cf = ensure_client_file(db_session, lead)
    db_session.flush()
    return cf


@pytest.fixture
def sample_pipeline_metrics():
    """Sample pipeline metrics response"""
    return {
        "total_count": 45,
        "total_volume": 18500000,
        "total_volume_formatted": "$18,500,000.00",
        "closing_soon": 8,
        "avg_days_in_status": 4.2,
        "velocity": {
            "period_days": 30,
            "funded_count": 12,
            "funded_volume": 5200000,
        },
    }


# =============================================================================
# QUALIFICATION AGENT FIXTURES
# =============================================================================

@pytest.fixture
def qualification_conversation():
    """Sample qualification conversation history"""
    return [
        {"role": "user", "content": "Hi, I'm interested in getting a mortgage"},
        {"role": "assistant", "content": "Hello! I'd be happy to help you explore your mortgage options. To get started, could you tell me a bit about what you're looking for - is this for purchasing a new home or refinancing?"},
        {"role": "user", "content": "I want to buy a house"},
        {"role": "assistant", "content": "That's exciting! What price range are you considering for your new home?"},
        {"role": "user", "content": "Around $450,000"},
    ]


@pytest.fixture
def mock_qualification_tools():
    """Mock tools for qualification agent tests"""
    return {
        "check_lead_status": AsyncMock(return_value=MockToolResult(
            status="success",
            data={"status": "new", "score": 0},
        )),
        "update_lead_info": AsyncMock(return_value=MockToolResult(
            status="success",
            data={"updated": True},
        )),
        "calculate_qualification": AsyncMock(return_value=MockToolResult(
            status="success",
            data={
                "qualified": True,
                "max_loan_amount": 450000,
                "estimated_rate": 6.875,
            },
        )),
        "schedule_callback": AsyncMock(return_value=MockToolResult(
            status="success",
            data={"scheduled": True, "time": "2024-01-15T10:00:00"},
        )),
    }


# =============================================================================
# ORCHESTRATOR FIXTURES
# =============================================================================

@pytest.fixture
def sample_intents():
    """Sample user intents for orchestrator routing tests"""
    return {
        "rate_inquiry": "What's the best rate for a 740 FICO conventional loan?",
        "scheduling": "Can you set up a call with my client tomorrow at 2pm?",
        "pipeline": "Show me my current pipeline status",
        "compliance": "Check TRID compliance for loan 2024-001234",
        "lead_status": "What's the status of my lead from John Smith?",
        "document": "What documents are missing for loan 2024-001234?",
        "greeting": "Hello, how are you?",
        "unclear": "Can you help me with something?",
    }


@pytest.fixture
def expected_agent_routing():
    """Expected agent routing for sample intents"""
    return {
        "rate_inquiry": "rate_analysis_agent",
        "scheduling": "scheduling_agent",
        "pipeline": "pipeline_analyst",
        "compliance": "compliance_checker",
        "lead_status": "lead_nurturer",
        "document": "document_tracker",
        "greeting": "general_assistant",
        "unclear": "clarification_needed",
    }


# =============================================================================
# GOLDEN RESPONSE FIXTURES
# =============================================================================

@pytest.fixture
def golden_responses_path():
    """Path to golden responses fixture file"""
    return Path(__file__).parent / "fixtures" / "golden_responses.json"


@pytest.fixture
def load_golden_responses(golden_responses_path):
    """Load golden responses from fixture file"""
    if golden_responses_path.exists():
        with open(golden_responses_path) as f:
            return json.load(f)
    return []


# =============================================================================
# ASYNC TEST HELPERS
# =============================================================================

@pytest.fixture
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def async_mock():
    """Factory for creating async mocks"""
    def _create(return_value=None):
        mock = AsyncMock()
        mock.return_value = return_value
        return mock
    return _create


# =============================================================================
# TOKEN USAGE TRACKING
# =============================================================================

@dataclass
class TokenUsage:
    """Track token usage for efficiency tests"""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def add(self, prompt: int, completion: int):
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        self.total_tokens = self.prompt_tokens + self.completion_tokens


@pytest.fixture
def token_tracker():
    """Track token usage across test runs"""
    return TokenUsage()


# =============================================================================
# TEST UTILITIES
# =============================================================================

def compute_similarity(text1: str, text2: str) -> float:
    """Compute simple similarity between two texts (for regression tests)"""
    words1 = set(text1.lower().split())
    words2 = set(text2.lower().split())
    if not words1 or not words2:
        return 0.0
    intersection = words1.intersection(words2)
    union = words1.union(words2)
    return len(intersection) / len(union)


@pytest.fixture
def similarity_checker():
    """Provide similarity computation for tests"""
    return compute_similarity


# =============================================================================
# ESTIMATE PARSER FIXTURES (preserved from original)
# =============================================================================

@pytest.fixture
def sample_text_pdf():
    """Create a sample text-based PDF for testing"""
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
    except ImportError:
        pytest.skip("reportlab not installed")

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    c.drawString(100, 750, "LOAN ESTIMATE")
    c.drawString(100, 720, "Loan Amount: $400,000")
    c.drawString(100, 700, "Interest Rate: 6.875%")
    c.drawString(100, 680, "Annual Percentage Rate (APR): 7.125%")
    c.drawString(100, 660, "Monthly Principal & Interest: $2,632.45")
    c.drawString(100, 640, "Total Closing Costs: $12,500")
    c.drawString(100, 620, "Cash to Close: $65,000")
    c.drawString(100, 600, "Loan Term: 30 years")
    c.drawString(100, 580, "Loan Type: Conventional")
    c.save()
    buffer.seek(0)
    return buffer


@pytest.fixture
def sample_parsed_estimate_a():
    """Sample parsed estimate A for comparison tests"""
    return {
        "loan_amount": 400000,
        "interest_rate": 6.875,
        "apr": 7.125,
        "monthly_principal_and_interest": 2632.45,
        "total_closing_costs": 12500,
        "cash_to_close": 65000,
        "loan_term": 30,
        "loan_type": "Conventional",
        "doc_hash": "hash_a_12345",
        "confidence_score": 0.95,
    }


@pytest.fixture
def sample_parsed_estimate_b():
    """Sample parsed estimate B for comparison tests (worse terms)"""
    return {
        "loan_amount": 400000,
        "interest_rate": 7.000,
        "apr": 7.250,
        "monthly_principal_and_interest": 2661.21,
        "total_closing_costs": 14000,
        "cash_to_close": 67500,
        "loan_term": 30,
        "loan_type": "Conventional",
        "doc_hash": "hash_b_67890",
        "confidence_score": 0.92,
    }


@pytest.fixture
def mock_llm_response():
    """Mock LLM response with parsed loan estimate data"""
    return json.dumps({
        "loan_amount": 400000,
        "interest_rate": 6.875,
        "apr": 7.125,
        "monthly_principal_and_interest": 2632.45,
        "total_closing_costs": 12500,
        "cash_to_close": 65000,
        "loan_term": 30,
        "loan_type": "Conventional"
    })


@pytest.fixture
def mock_textract_response():
    """Mock AWS Textract response for OCR tests"""
    return {
        "Blocks": [
            {
                "BlockType": "LINE",
                "Text": "LOAN ESTIMATE",
                "Confidence": 99.5
            },
            {
                "BlockType": "LINE",
                "Text": "Loan Amount: $400,000",
                "Confidence": 98.2
            },
            {
                "BlockType": "LINE",
                "Text": "Interest Rate: 6.875%",
                "Confidence": 97.8
            },
            {
                "BlockType": "LINE",
                "Text": "Annual Percentage Rate (APR): 7.125%",
                "Confidence": 98.1
            },
            {
                "BlockType": "LINE",
                "Text": "Monthly Principal & Interest: $2,632.45",
                "Confidence": 97.5
            },
            {
                "BlockType": "LINE",
                "Text": "Total Closing Costs: $12,500",
                "Confidence": 98.0
            },
            {
                "BlockType": "LINE",
                "Text": "Cash to Close: $65,000",
                "Confidence": 97.9
            }
        ]
    }


@pytest.fixture
def sample_scanned_pdf():
    """Create a minimal PDF that simulates a scanned document (image-based)"""
    # A minimal valid PDF with just enough structure to be recognized as PDF
    # In practice, this would trigger OCR since it has no extractable text
    pdf_content = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>
endobj
xref
0 4
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
trailer
<< /Size 4 /Root 1 0 R >>
startxref
196
%%EOF"""
    buffer = BytesIO(pdf_content)
    buffer.seek(0)
    return buffer


@pytest.fixture
def sample_image():
    """Create a minimal valid JPEG image for testing"""
    # Minimal 1x1 pixel JPEG (smallest valid JPEG)
    # This is a red pixel JPEG
    jpeg_bytes = bytes([
        0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
        0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
        0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07, 0x07, 0x07, 0x09,
        0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
        0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A, 0x1C, 0x1C, 0x20,
        0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29,
        0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32,
        0x3C, 0x2E, 0x33, 0x34, 0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
        0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00,
        0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
        0x09, 0x0A, 0x0B, 0xFF, 0xC4, 0x00, 0xB5, 0x10, 0x00, 0x02, 0x01, 0x03,
        0x03, 0x02, 0x04, 0x03, 0x05, 0x05, 0x04, 0x04, 0x00, 0x00, 0x01, 0x7D,
        0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12, 0x21, 0x31, 0x41, 0x06,
        0x13, 0x51, 0x61, 0x07, 0x22, 0x71, 0x14, 0x32, 0x81, 0x91, 0xA1, 0x08,
        0x23, 0x42, 0xB1, 0xC1, 0x15, 0x52, 0xD1, 0xF0, 0x24, 0x33, 0x62, 0x72,
        0x82, 0x09, 0x0A, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x25, 0x26, 0x27, 0x28,
        0x29, 0x2A, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3A, 0x43, 0x44, 0x45,
        0x46, 0x47, 0x48, 0x49, 0x4A, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59,
        0x5A, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69, 0x6A, 0x73, 0x74, 0x75,
        0x76, 0x77, 0x78, 0x79, 0x7A, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89,
        0x8A, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9A, 0xA2, 0xA3,
        0xA4, 0xA5, 0xA6, 0xA7, 0xA8, 0xA9, 0xAA, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6,
        0xB7, 0xB8, 0xB9, 0xBA, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7, 0xC8, 0xC9,
        0xCA, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9, 0xDA, 0xE1, 0xE2,
        0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA, 0xF1, 0xF2, 0xF3, 0xF4,
        0xF5, 0xF6, 0xF7, 0xF8, 0xF9, 0xFA, 0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01,
        0x00, 0x00, 0x3F, 0x00, 0xFB, 0xD5, 0xDB, 0x20, 0xA8, 0xF7, 0xFF, 0xD9
    ])
    buffer = BytesIO(jpeg_bytes)
    buffer.seek(0)
    return buffer


@pytest.fixture
def sample_le_with_pii():
    """Sample loan estimate text containing PII for redaction testing"""
    return """
LOAN ESTIMATE
Date Issued: January 15, 2024

Borrower Information:
Name: John Smith
Email: john.smith@email.com
Phone: (555) 123-4567
Social Security Number: 123-45-6789
Account Number: 9876543210

Property Address: 123 Main Street, Austin, TX 78701

Loan Information:
Loan Amount: $400,000.00
Interest Rate: 6.875%
Monthly Principal & Interest: $2,632.45
Annual Percentage Rate (APR): 7.125%
Total Closing Costs: $12,500.00
Cash to Close: $65,000.00

Lender: ABC Mortgage Company
NMLS ID: 12345
"""
