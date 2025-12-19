"""
Perennia AI - Comprehensive Test Configuration & Fixtures

Layered Testing Strategy:
- unit: Fast isolated tests with mocked dependencies
- integration: Tests with real external services
- e2e: Full conversation flow tests
- regression: Golden response comparisons
"""
import pytest
import os
import json
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from dataclasses import dataclass

# Load environment variables from .env file BEFORE any other imports
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from fastapi.testclient import TestClient
from io import BytesIO

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app
from database import get_db


# =============================================================================
# DATABASE FIXTURES
# =============================================================================

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "sqlite:///./test_perennia.db")
test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in TEST_DATABASE_URL else {}
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="session")
def db_engine():
    """Create test database engine for the session"""
    # Create tables needed for integration tests
    with test_engine.connect() as conn:
        # Create leads table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS leads (
                id TEXT PRIMARY KEY,
                first_name TEXT,
                last_name TEXT,
                email TEXT,
                phone TEXT,
                status TEXT DEFAULT 'new',
                source TEXT,
                campaign TEXT,
                loan_purpose TEXT,
                property_type TEXT,
                estimated_amount REAL,
                estimated_credit_score INTEGER,
                pre_approved INTEGER DEFAULT 0,
                lead_score INTEGER DEFAULT 0,
                assigned_to TEXT,
                preferred_contact_method TEXT,
                preferred_contact_time TEXT,
                timezone TEXT,
                last_contact_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # Create loans table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS loans (
                id TEXT PRIMARY KEY,
                loan_number TEXT,
                borrower_name TEXT,
                borrower_id TEXT,
                loan_amount REAL,
                interest_rate REAL,
                loan_type TEXT,
                property_address TEXT,
                status TEXT DEFAULT 'lead',
                loan_officer_id TEXT,
                branch_id TEXT,
                application_date TIMESTAMP,
                disclosure_sent_at TIMESTAMP,
                disclosure_received_at TIMESTAMP,
                closing_disclosure_sent_at TIMESTAMP,
                closing_disclosure_received_at TIMESTAMP,
                consummation_date TIMESTAMP,
                submitted_to_uw_at TIMESTAMP,
                approval_date TIMESTAMP,
                clear_to_close_at TIMESTAMP,
                funded_at TIMESTAMP,
                expected_close_date DATE,
                lock_expiration_date DATE,
                le_revision_count INTEGER DEFAULT 0,
                cd_revision_count INTEGER DEFAULT 0,
                borrower_credit_score INTEGER,
                pricing_exception INTEGER DEFAULT 0,
                pricing_exception_reason TEXT,
                referral_source TEXT,
                referral_fee_paid REAL,
                title_company_id TEXT,
                title_fee REAL,
                appraisal_company_id TEXT,
                appraisal_fee REAL,
                status_changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # Create users table for joins
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                name TEXT,
                email TEXT,
                nmls_id TEXT,
                manager_id TEXT
            )
        """))

        conn.commit()

    yield test_engine


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

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    async def override_get_current_user(*args, **kwargs):
        return mock_user

    async def override_get_current_user_flexible(*args, **kwargs):
        return mock_user

    # Override all auth-related dependencies
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_current_user_flexible] = override_get_current_user_flexible

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
        except:
            pass

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
        "loan_term": "30 years",
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
        "loan_term": "30 years",
        "loan_type": "Conventional",
        "doc_hash": "hash_b_67890",
        "confidence_score": 0.92,
    }
