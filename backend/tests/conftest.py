"""
Test Configuration & Fixtures for Estimate Parser Tests
"""
import pytest
import os
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch
import base64
from io import BytesIO

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app
from database import get_db

# Test database setup - use SQLite for testing
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "sqlite:///./test_estimate_parser.db")
test_engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in TEST_DATABASE_URL else {})
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def create_test_tables(engine):
    """Create only the tables needed for estimate parser tests"""
    with engine.connect() as conn:
        # Create users table (minimal - needed for foreign key)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email VARCHAR(255),
                name VARCHAR(255)
            )
        """))

        # Create estimate_parse_cache table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS estimate_parse_cache (
                doc_hash VARCHAR(64) PRIMARY KEY,
                parsed_json JSON NOT NULL,
                confidence_score NUMERIC(3, 2),
                needs_review BOOLEAN DEFAULT FALSE,
                source_type VARCHAR(50) DEFAULT 'loan_estimate',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                access_count INTEGER DEFAULT 0
            )
        """))

        # Create estimate_parse_failures table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS estimate_parse_failures (
                id VARCHAR(36) PRIMARY KEY,
                request_id VARCHAR(36) NOT NULL,
                doc_hash VARCHAR(64) NOT NULL,
                error_stage VARCHAR(50) NOT NULL,
                error_message TEXT,
                raw_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # Create estimate_comparisons table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS estimate_comparisons (
                id VARCHAR(36) PRIMARY KEY,
                user_id INTEGER,
                session_id VARCHAR(100),
                estimate_a_hash VARCHAR(64) NOT NULL,
                estimate_b_hash VARCHAR(64) NOT NULL,
                winner VARCHAR(1),
                winner_reason TEXT,
                savings_amount NUMERIC(12, 2),
                converted BOOLEAN DEFAULT FALSE,
                converted_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.commit()


def drop_test_tables(engine):
    """Drop test tables"""
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS estimate_comparisons"))
        conn.execute(text("DROP TABLE IF EXISTS estimate_parse_failures"))
        conn.execute(text("DROP TABLE IF EXISTS estimate_parse_cache"))
        conn.execute(text("DROP TABLE IF EXISTS users"))
        conn.commit()


@pytest.fixture(scope="session")
def db_engine():
    """Create test database tables"""
    create_test_tables(test_engine)
    yield test_engine
    drop_test_tables(test_engine)


@pytest.fixture(scope="function")
def db_session(db_engine):
    """Create a new database session for each test"""
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


@pytest.fixture
def sample_text_pdf():
    """Create a sample text-based PDF for testing"""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

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
def sample_scanned_pdf():
    """Create a minimal PDF (simulating scanned - low text content)"""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    c.drawString(100, 750, "Scanned Document")  # Minimal text
    c.save()
    buffer.seek(0)
    return buffer


@pytest.fixture
def sample_image():
    """Create a sample image for testing"""
    # Create a simple 1x1 white JPEG
    from PIL import Image
    buffer = BytesIO()
    img = Image.new('RGB', (100, 100), color='white')
    img.save(buffer, format='JPEG')
    buffer.seek(0)
    return buffer


@pytest.fixture
def sample_le_with_pii():
    """Sample text containing PII for redaction testing"""
    return """
    LOAN ESTIMATE

    Borrower: John Smith
    Email: john.smith@email.com
    Phone: (555) 123-4567
    SSN: 123-45-6789
    Property: 123 Main Street, Anytown, CA 12345

    Loan Amount: $400,000
    Interest Rate: 6.875%
    APR: 7.125%
    Monthly P&I: $2,632.45
    Total Closing Costs: $12,500
    Cash to Close: $65,000

    Account Number: 9876543210
    """


@pytest.fixture
def mock_textract_response():
    """Mock AWS Textract response"""
    return {
        'Blocks': [
            {'BlockType': 'LINE', 'Text': 'LOAN ESTIMATE'},
            {'BlockType': 'LINE', 'Text': 'Loan Amount $400,000'},
            {'BlockType': 'LINE', 'Text': 'Interest Rate 6.875%'},
            {'BlockType': 'LINE', 'Text': 'APR 7.125%'},
            {'BlockType': 'LINE', 'Text': 'Monthly Principal & Interest $2,632.45'},
            {'BlockType': 'LINE', 'Text': 'Total Closing Costs $12,500'},
            {'BlockType': 'LINE', 'Text': 'Cash to Close $65,000'},
        ]
    }


@pytest.fixture
def mock_llm_response():
    """Mock LLM normalized response"""
    return """{
      "loan_amount": 400000,
      "interest_rate": 6.875,
      "apr": 7.125,
      "monthly_principal_and_interest": 2632.45,
      "estimated_total_monthly_payment": 3450.00,
      "total_closing_costs": 12500,
      "cash_to_close": 65000,
      "loan_term": 30,
      "loan_type": "Conventional"
    }"""


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
        "needs_review": False,
        "provenance": {
            "cash_to_close": "...Cash to Close $65,000...",
            "total_closing_costs": "...Total Closing Costs $12,500...",
            "interest_rate": "...Interest Rate 6.875%...",
            "apr": "...Annual Percentage Rate 7.125%..."
        }
    }


@pytest.fixture
def sample_parsed_estimate_b():
    """Sample parsed estimate B for comparison tests (slightly worse terms)"""
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
        "needs_review": False,
        "provenance": {
            "cash_to_close": "...Cash to Close $67,500...",
            "total_closing_costs": "...Total Closing Costs $14,000...",
            "interest_rate": "...Interest Rate 7.000%...",
            "apr": "...Annual Percentage Rate 7.250%..."
        }
    }
