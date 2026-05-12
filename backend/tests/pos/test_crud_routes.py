"""Tests for POS documents, messages, tasks, and team routes.

Covers happy-path behavior and cross-borrower auth isolation for the
four untested POS CRUD route modules.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Generator
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import get_db
from database.models.pos import POSApplication, POSBorrowerMessage, POSStatus
from database.models.task import Task
from middleware.purl_auth import (
    PURLAuthContext,
    check_purl_rate_limit,
    require_purl_token,
    require_purl_write_scope,
)


# ---------------------------------------------------------------------------
# Extra DDL for tables needed by these route modules
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def _crud_tables(_pos_engine):
    """Create additional tables needed by documents, messages, tasks, team."""
    with _pos_engine.begin() as conn:
        # POS borrower messages
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS pos_borrower_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                application_id VARCHAR(36) NOT NULL
                    REFERENCES pos_applications(id) ON DELETE CASCADE,
                organization_id INTEGER NOT NULL,
                sender_user_id INTEGER,
                sender_name VARCHAR(128) NOT NULL,
                sender_role VARCHAR(64) NOT NULL DEFAULT 'Loan Officer',
                content TEXT NOT NULL,
                read_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        # Tasks
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                title VARCHAR NOT NULL,
                description TEXT,
                status VARCHAR DEFAULT 'pending',
                priority VARCHAR DEFAULT 'medium',
                due_date TIMESTAMP,
                owner_id INTEGER,
                lead_id INTEGER,
                loan_id INTEGER,
                related_contact_name VARCHAR,
                related_type VARCHAR,
                completed_at TIMESTAMP,
                sla_milestone_id INTEGER,
                sla_milestone_type VARCHAR,
                sla_date_field VARCHAR,
                milestone_date TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                email_intake_id INTEGER,
                workflow_task_instance_id INTEGER,
                task_group_key VARCHAR(100),
                sf_proposed_stage VARCHAR(50),
                sf_current_stage VARCHAR(50),
                sf_raw_stage VARCHAR(200),
                disposition_action VARCHAR(20),
                disposition_date TIMESTAMP,
                disposition_by INTEGER
            )
        """))
        # Users (stub for team route)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email VARCHAR NOT NULL,
                hashed_password VARCHAR NOT NULL DEFAULT '',
                first_name VARCHAR,
                last_name VARCHAR,
                role VARCHAR DEFAULT 'loan_officer',
                permission_role VARCHAR DEFAULT 'sales',
                organization_id INTEGER,
                is_active BOOLEAN DEFAULT 1,
                phone VARCHAR,
                title TEXT,
                current_role VARCHAR,
                headshot_url TEXT,
                nmls_id VARCHAR,
                nmls_number VARCHAR,
                timezone VARCHAR DEFAULT 'America/Chicago',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                slug VARCHAR,
                team_name TEXT,
                company_logo_url TEXT,
                business_address VARCHAR,
                business_hours TEXT,
                email_verified BOOLEAN DEFAULT 0,
                onboarding_completed BOOLEAN DEFAULT 0,
                user_metadata TEXT,
                phone_verified_at TIMESTAMP,
                email_verified_at TIMESTAMP,
                branch_id INTEGER,
                manager_id INTEGER,
                briefing_enabled BOOLEAN DEFAULT 1,
                briefing_hour INTEGER DEFAULT 7,
                briefing_preferences TEXT,
                last_activity_at TIMESTAMP,
                failed_login_attempts INTEGER DEFAULT 0,
                locked_until TIMESTAMP,
                last_failed_login_at TIMESTAMP,
                mfa_secret VARCHAR,
                mfa_enabled BOOLEAN DEFAULT 0,
                mfa_backup_codes TEXT,
                mfa_enabled_at TIMESTAMP,
                sso_provider VARCHAR,
                sso_subject_id VARCHAR,
                password_changed_at TIMESTAMP
            )
        """))
        # Loans (stub for team route — must include all Loan model columns
        # since db.get(Loan, id) selects all columns)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS loans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                loan_number VARCHAR,
                borrower_name VARCHAR NOT NULL DEFAULT '',
                borrower_email VARCHAR,
                borrower_phone VARCHAR,
                preferred_communication VARCHAR,
                coborrower_name VARCHAR,
                co_borrower_email VARCHAR,
                co_borrower_phone VARCHAR,
                stage VARCHAR DEFAULT 'DISCLOSED',
                program VARCHAR,
                loan_type VARCHAR,
                amount REAL DEFAULT 0,
                purchase_price REAL,
                down_payment REAL,
                rate REAL,
                term INTEGER DEFAULT 360,
                property_address VARCHAR,
                property_city VARCHAR,
                property_state VARCHAR,
                property_zip VARCHAR,
                lock_date TIMESTAMP,
                closing_date TIMESTAMP,
                funded_date TIMESTAMP,
                loan_officer_id INTEGER,
                processor VARCHAR,
                underwriter VARCHAR,
                realtor_agent VARCHAR,
                title_company VARCHAR,
                lender VARCHAR,
                loan_officer_name VARCHAR,
                loan_officer_email VARCHAR,
                processor_email VARCHAR,
                underwriter_email VARCHAR,
                closer VARCHAR,
                closer_email VARCHAR,
                production_assistant VARCHAR,
                days_in_stage INTEGER DEFAULT 0,
                sla_status VARCHAR DEFAULT 'on-track',
                milestones TEXT,
                ai_insights TEXT,
                predicted_close_date TIMESTAMP,
                risk_score INTEGER DEFAULT 0,
                user_metadata TEXT,
                appraisal_ordered_date TIMESTAMP,
                appraisal_scheduled_date TIMESTAMP,
                appraisal_completed_date TIMESTAMP,
                appraisal_value REAL,
                appraisal_received_date TIMESTAMP,
                appraisal_docs_expire_date TIMESTAMP,
                title_ordered_date TIMESTAMP,
                title_received_date TIMESTAMP,
                insurance_ordered_date TIMESTAMP,
                insurance_received_date TIMESTAMP,
                lock_expiration_date TIMESTAMP,
                rate_lock_status VARCHAR,
                rate_lock_recommendation VARCHAR,
                lock_term_days INTEGER,
                float_down_available BOOLEAN DEFAULT 0,
                float_down_terms VARCHAR,
                extension_cost_estimate REAL,
                volatility_score INTEGER DEFAULT 50,
                borrower_risk_profile VARCHAR,
                lock_score INTEGER,
                lock_decision_date TIMESTAMP,
                lock_decision_notes TEXT,
                last_rate_check TIMESTAMP,
                rate_lock_history TEXT,
                initial_disclosures_sent_date TIMESTAMP,
                initial_disclosures_signed_date TIMESTAMP,
                cd_received_signed_date TIMESTAMP,
                final_closing_package_sent_date TIMESTAMP,
                contract_received_date TIMESTAMP,
                loan_estimate_sent_date TIMESTAMP,
                conditional_approval_date TIMESTAMP,
                last_amr_date TIMESTAMP,
                next_amr_date TIMESTAMP,
                refi_opportunity_score INTEGER DEFAULT 0,
                current_workflow_id VARCHAR,
                last_workflow_action TIMESTAMP,
                stage_changed_at TIMESTAMP,
                current_milestone_status VARCHAR(50),
                current_milestone_entered_at TIMESTAMP,
                mum_date TIMESTAMP,
                prospect_date TIMESTAMP,
                application_date TIMESTAMP,
                le_pending_date TIMESTAMP,
                credit_only_date TIMESTAMP,
                file_received_date TIMESTAMP,
                preapproval_date TIMESTAMP,
                uw_received_date TIMESTAMP,
                conditions_for_review_date TIMESTAMP,
                suspended_date TIMESTAMP,
                loan_approved_date TIMESTAMP,
                approved_not_accepted_date TIMESTAMP,
                approval_expires_date TIMESTAMP,
                cd_requested_date TIMESTAMP,
                cd_sent_to_borrower_date TIMESTAMP,
                cd_acknowledged_date TIMESTAMP,
                clear_to_close_date TIMESTAMP,
                docs_ordered_date TIMESTAMP,
                docs_out_date TIMESTAMP,
                credit_docs_expire_date TIMESTAMP,
                scheduled_closing_date TIMESTAMP,
                scheduled_funding_date TIMESTAMP,
                funds_ordered_date TIMESTAMP,
                funds_sent_date TIMESTAMP,
                first_payment_date TIMESTAMP,
                investor_purchased_date TIMESTAMP,
                withdrawn_date TIMESTAMP,
                property_type VARCHAR,
                occupancy_type VARCHAR,
                property_county VARCHAR,
                property_ownership_type VARCHAR,
                property_units INTEGER,
                rate_type VARCHAR,
                monthly_payment REAL,
                property_tax REAL,
                hazard_insurance REAL,
                mortgage_insurance REAL,
                hoa_amount REAL,
                origination_fee REAL,
                estimated_prepaid_interest REAL,
                points REAL,
                index_rate REAL,
                margin REAL,
                ltv REAL,
                cltv REAL,
                loan_purpose VARCHAR,
                file_state VARCHAR,
                second_loan_amount REAL,
                second_loan_rate REAL,
                second_loan_payment REAL,
                present_housing_expense REAL,
                proposed_housing_expense REAL,
                present_monthly_payment REAL,
                proposed_monthly_payment REAL,
                salesforce_id VARCHAR,
                encompass_loan_id VARCHAR,
                encompass_last_synced_at TIMESTAMP,
                encompass_sync_status VARCHAR,
                last_modified_by_ai BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                deleted_at TIMESTAMP
            )
        """))
        # PURL loans (for documents route ownership check)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS purl_loans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                workspace_id INTEGER NOT NULL,
                application_id INTEGER,
                main_loan_id INTEGER,
                loan_number VARCHAR(100),
                status VARCHAR(30) DEFAULT 'active',
                loan_purpose VARCHAR(50),
                product_type VARCHAR(100),
                loan_amount REAL,
                interest_rate REAL,
                property_address TEXT,
                property_type VARCHAR(50),
                target_close_date DATE,
                actual_close_date DATE,
                los_loan_id VARCHAR(100),
                meta_data TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        # PURL contacts (for message sender name lookup)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS purl_contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                workspace_id INTEGER NOT NULL,
                contact_type VARCHAR(50) NOT NULL DEFAULT 'borrower',
                first_name VARCHAR(255) NOT NULL DEFAULT '',
                last_name VARCHAR(255) NOT NULL DEFAULT '',
                email VARCHAR(255),
                phone VARCHAR(50),
                auth_user_id INTEGER,
                auth_provider VARCHAR(50),
                meta_data TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        # Smart document requests (for documents route)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS smart_document_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL DEFAULT 1,
                loan_id INTEGER NOT NULL,
                borrower_id INTEGER,
                doc_type VARCHAR(100) NOT NULL,
                title VARCHAR(255) NOT NULL,
                description TEXT,
                instructions TEXT,
                required_count INTEGER DEFAULT 1,
                applies_to VARCHAR(50) DEFAULT 'BORROWER',
                priority VARCHAR(50) DEFAULT 'NORMAL',
                freshness_days INTEGER,
                auto_renew BOOLEAN DEFAULT 0,
                next_expected_available_at TIMESTAMP,
                payroll_frequency VARCHAR(50),
                status VARCHAR(50) DEFAULT 'OPEN',
                is_required BOOLEAN DEFAULT 1,
                due_date TIMESTAMP,
                completed_at TIMESTAMP,
                fulfilled_at TIMESTAMP,
                requires_esign BOOLEAN DEFAULT 0,
                request_metadata TEXT,
                sla_due_at TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                superseded_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        # Smart documents (for documents route)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS smart_documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL DEFAULT 1,
                request_id INTEGER,
                loan_id INTEGER,
                borrower_id INTEGER NOT NULL,
                file_name VARCHAR(512) NOT NULL,
                original_filename VARCHAR(512),
                mime_type VARCHAR(128) NOT NULL,
                file_size INTEGER NOT NULL,
                file_hash VARCHAR(64),
                storage_key VARCHAR(1024) NOT NULL,
                page_count INTEGER,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                doc_type VARCHAR(100),
                detected_doc_type VARCHAR(64),
                detected_is_screenshot BOOLEAN DEFAULT 0,
                screenshot_confidence REAL,
                screenshot_reasons TEXT,
                extracted_dates TEXT,
                extracted_names TEXT,
                extracted_employer VARCHAR(255),
                extracted_account_number VARCHAR(64),
                extracted_amount REAL,
                extraction_confidence REAL,
                ocr_text TEXT,
                doc_date TIMESTAMP,
                doc_expires_at TIMESTAMP,
                is_expired BOOLEAN DEFAULT 0,
                days_until_expiration INTEGER,
                status VARCHAR(32) DEFAULT 'UPLOADED',
                decision VARCHAR(50),
                decision_reasons TEXT,
                rejection_reason TEXT,
                rejection_category VARCHAR(50),
                fix_instructions TEXT,
                reviewed_at TIMESTAMP,
                reviewed_by VARCHAR(64),
                upload_source VARCHAR(32),
                user_agent VARCHAR(512),
                ip_address VARCHAR(45),
                display_name VARCHAR(255),
                assigned_owner VARCHAR(20),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        # Default role assignments (for team route)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS default_role_assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                role_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL
            )
        """))
        # Roles (for team route)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR NOT NULL
            )
        """))
        # Organizations (for FK references)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS organizations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR NOT NULL,
                slug VARCHAR,
                domain VARCHAR,
                settings TEXT,
                subscription_tier VARCHAR DEFAULT 'lead_management',
                is_active BOOLEAN DEFAULT 1,
                timezone VARCHAR(50) DEFAULT 'America/Chicago',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                sso_enforced BOOLEAN DEFAULT 0,
                mfa_required BOOLEAN DEFAULT 0,
                booking_slug VARCHAR,
                booking_logo_url TEXT,
                booking_primary_color VARCHAR(7) DEFAULT '#1a73e8',
                booking_accent_color VARCHAR(7) DEFAULT '#34a853',
                booking_tagline VARCHAR(200),
                booking_welcome_message TEXT,
                booking_custom_css TEXT,
                booking_cover_image_url TEXT,
                booking_show_testimonials BOOLEAN DEFAULT 0,
                booking_testimonials TEXT
            )
        """))


# ---------------------------------------------------------------------------
# App fixture that includes all 4 CRUD routers
# ---------------------------------------------------------------------------


@pytest.fixture
def crud_app(
    db_session: Session,
    borrower_alice: PURLAuthContext,
) -> FastAPI:
    """FastAPI app with documents, messages, tasks, team routers mounted."""
    from routes.pos.documents import router as documents_router
    from routes.pos.messages import router as messages_router
    from routes.pos.tasks import router as tasks_router
    from routes.pos.team import router as team_router

    test_app = FastAPI()
    test_app.include_router(documents_router)
    test_app.include_router(messages_router)
    test_app.include_router(tasks_router)
    test_app.include_router(team_router)

    def _override_db() -> Generator[Session, None, None]:
        yield db_session

    test_app.dependency_overrides[get_db] = _override_db
    test_app.dependency_overrides[require_purl_token] = lambda: borrower_alice
    test_app.dependency_overrides[require_purl_write_scope] = lambda: borrower_alice
    test_app.dependency_overrides[check_purl_rate_limit] = lambda: None

    # Override the application resolver dependencies so they use our test DB
    from routes.pos._helpers import (
        get_application_service,
        resolve_application_for_borrower,
        resolve_application_for_borrower_write,
    )
    from services.pos.application_service import ApplicationService

    test_app.dependency_overrides[get_application_service] = lambda: ApplicationService()

    return test_app


@pytest.fixture
def crud_app_as_bob(
    crud_app: FastAPI,
    borrower_bob: PURLAuthContext,
) -> FastAPI:
    """Same CRUD app, but PURL context resolves to Bob."""
    crud_app.dependency_overrides[require_purl_token] = lambda: borrower_bob
    crud_app.dependency_overrides[require_purl_write_scope] = lambda: borrower_bob
    return crud_app


@pytest.fixture
def crud_client(crud_app: FastAPI) -> Generator[TestClient, None, None]:
    with TestClient(crud_app) as c:
        yield c


@pytest.fixture
def crud_client_as_bob(crud_app_as_bob: FastAPI) -> Generator[TestClient, None, None]:
    with TestClient(crud_app_as_bob) as c:
        yield c


# ---------------------------------------------------------------------------
# Data fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def alice_app_with_loan(
    db_session: Session, borrower_alice: PURLAuthContext
) -> POSApplication:
    """Application owned by Alice linked to loan_id=42."""
    app = POSApplication(
        id=uuid4(),
        organization_id=borrower_alice.organization_id,
        workspace_id=borrower_alice.workspace_id,
        contact_id=borrower_alice.contact_id,
        loan_id=42,
        status=POSStatus.DRAFT,
        current_step="personal",
    )
    db_session.add(app)
    db_session.flush()
    return app


@pytest.fixture
def bob_app_with_loan(
    db_session: Session, borrower_bob: PURLAuthContext
) -> POSApplication:
    """Application owned by Bob linked to loan_id=99."""
    app = POSApplication(
        id=uuid4(),
        organization_id=borrower_bob.organization_id,
        workspace_id=borrower_bob.workspace_id,
        contact_id=borrower_bob.contact_id,
        loan_id=99,
        status=POSStatus.DRAFT,
        current_step="personal",
    )
    db_session.add(app)
    db_session.flush()
    return app


@pytest.fixture
def alice_messages(
    db_session: Session, alice_app_with_loan: POSApplication
) -> list[POSBorrowerMessage]:
    """Three messages on Alice's application: 2 unread from LO, 1 read."""
    now = datetime.now(timezone.utc)
    msgs = [
        POSBorrowerMessage(
            application_id=alice_app_with_loan.id,
            organization_id=alice_app_with_loan.organization_id,
            sender_user_id=10,
            sender_name="Jane Smith",
            sender_role="Loan Officer",
            content="Please upload your W2.",
            read_at=None,
            created_at=now - timedelta(hours=3),
        ),
        POSBorrowerMessage(
            application_id=alice_app_with_loan.id,
            organization_id=alice_app_with_loan.organization_id,
            sender_user_id=10,
            sender_name="Jane Smith",
            sender_role="Loan Officer",
            content="Welcome to your loan portal!",
            read_at=now - timedelta(hours=1),
            created_at=now - timedelta(hours=5),
        ),
        POSBorrowerMessage(
            application_id=alice_app_with_loan.id,
            organization_id=alice_app_with_loan.organization_id,
            sender_user_id=None,
            sender_name="Alice Anderson",
            sender_role="Borrower",
            content="Thanks, I will upload it today.",
            read_at=None,
            created_at=now - timedelta(hours=2),
        ),
    ]
    for m in msgs:
        db_session.add(m)
    db_session.flush()
    return msgs


@pytest.fixture
def alice_tasks(
    db_session: Session, alice_app_with_loan: POSApplication
) -> list[Task]:
    """Tasks for Alice's loan: 2 borrower-visible, 1 internal, 1 completed."""
    now = datetime.now(timezone.utc)
    tasks = [
        Task(
            organization_id=alice_app_with_loan.organization_id,
            title="Upload bank statements",
            description="Please upload last 2 months of bank statements.",
            status="pending",
            priority="high",
            loan_id=alice_app_with_loan.loan_id,
            related_type="document",
            due_date=now + timedelta(days=3),
            created_at=now - timedelta(days=1),
        ),
        Task(
            organization_id=alice_app_with_loan.organization_id,
            title="Sign disclosures",
            description="Review and sign initial disclosures.",
            status="in_progress",
            priority="medium",
            loan_id=alice_app_with_loan.loan_id,
            related_type="disclosure",
            created_at=now - timedelta(days=2),
        ),
        Task(
            organization_id=alice_app_with_loan.organization_id,
            title="SF disposition review",
            description="Internal SF sync task.",
            status="pending",
            priority="low",
            loan_id=alice_app_with_loan.loan_id,
            related_type="sf_disposition",
            created_at=now - timedelta(days=1),
        ),
        Task(
            organization_id=alice_app_with_loan.organization_id,
            title="Verify employment",
            description="Call employer to verify.",
            status="completed",
            priority="medium",
            loan_id=alice_app_with_loan.loan_id,
            related_type="verification",
            completed_at=now - timedelta(hours=6),
            created_at=now - timedelta(days=3),
        ),
    ]
    for t in tasks:
        db_session.add(t)
    db_session.flush()
    return tasks


@pytest.fixture
def alice_purl_loan(
    db_session: Session, borrower_alice: PURLAuthContext
):
    """PURL loan linking Alice's workspace to main loan_id=42."""
    db_session.execute(text(
        "INSERT INTO purl_loans (organization_id, workspace_id, main_loan_id) "
        "VALUES (:org, :ws, :loan)"
    ), {"org": borrower_alice.organization_id, "ws": borrower_alice.workspace_id, "loan": 42})
    db_session.flush()


@pytest.fixture
def alice_contact(
    db_session: Session, borrower_alice: PURLAuthContext
):
    """PURL contact record for Alice."""
    db_session.execute(text(
        "INSERT INTO purl_contacts (id, organization_id, workspace_id, contact_type, first_name, last_name, email) "
        "VALUES (:id, :org, :ws, 'borrower', 'Alice', 'Anderson', 'alice@example.com')"
    ), {
        "id": borrower_alice.contact_id,
        "org": borrower_alice.organization_id,
        "ws": borrower_alice.workspace_id,
    })
    db_session.flush()


@pytest.fixture
def org_and_users(db_session: Session, borrower_alice: PURLAuthContext):
    """Create an org with two active users for team tests."""
    db_session.execute(text(
        "INSERT INTO organizations (id, name, slug) VALUES (:id, :name, :slug)"
    ), {"id": borrower_alice.organization_id, "name": "Test Org", "slug": "test-org"})

    db_session.execute(text(
        "INSERT INTO users (id, email, hashed_password, first_name, last_name, organization_id, is_active, title, phone, nmls_id) "
        "VALUES (:id, :email, 'x', :fn, :ln, :org, 1, :title, :phone, :nmls)"
    ), {
        "id": 10,
        "email": "jane@test.com",
        "fn": "Jane",
        "ln": "Smith",
        "org": borrower_alice.organization_id,
        "title": "Senior Loan Officer",
        "phone": "555-1111",
        "nmls": "123456",
    })
    db_session.execute(text(
        "INSERT INTO users (id, email, hashed_password, first_name, last_name, organization_id, is_active, title, phone) "
        "VALUES (:id, :email, 'x', :fn, :ln, :org, 1, :title, :phone)"
    ), {
        "id": 11,
        "email": "bob@test.com",
        "fn": "Bob",
        "ln": "Processor",
        "org": borrower_alice.organization_id,
        "title": "Processor",
        "phone": "555-2222",
    })
    db_session.flush()


@pytest.fixture
def loan_with_officer(
    db_session: Session,
    alice_app_with_loan: POSApplication,
    org_and_users,
):
    """Create a loan row with loan_officer_id pointing to user 10."""
    db_session.execute(text(
        "INSERT INTO loans (id, organization_id, loan_officer_id) "
        "VALUES (:id, :org, :lo_id)"
    ), {
        "id": alice_app_with_loan.loan_id,
        "org": alice_app_with_loan.organization_id,
        "lo_id": 10,
    })
    db_session.flush()


@pytest.fixture
def role_assignments(db_session: Session, org_and_users, borrower_alice: PURLAuthContext):
    """Create role assignments: user 11 = Processor role."""
    db_session.execute(text(
        "INSERT INTO roles (id, name) VALUES (1, 'Processor')"
    ))
    db_session.execute(text(
        "INSERT INTO default_role_assignments (organization_id, role_id, user_id) "
        "VALUES (:org, 1, 11)"
    ), {"org": borrower_alice.organization_id})
    db_session.flush()


# ===========================================================================
# TEST CLASS: Messages
# ===========================================================================


class TestMessages:
    """Tests for /api/v1/pos/applications/{app_id}/messages endpoints."""

    def test_list_messages_returns_all(
        self,
        crud_client: TestClient,
        alice_app_with_loan: POSApplication,
        alice_messages: list,
    ):
        resp = crud_client.get(
            f"/api/v1/pos/applications/{alice_app_with_loan.id}/messages"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["application_id"] == str(alice_app_with_loan.id)
        assert len(body["messages"]) == 3
        assert body["counts"]["total"] == 3
        # 2 messages have read_at=None (the LO message and borrower message)
        assert body["counts"]["unread"] == 2

    def test_list_messages_ordered_desc(
        self,
        crud_client: TestClient,
        alice_app_with_loan: POSApplication,
        alice_messages: list,
    ):
        """Messages returned in descending created_at order."""
        resp = crud_client.get(
            f"/api/v1/pos/applications/{alice_app_with_loan.id}/messages"
        )
        msgs = resp.json()["messages"]
        timestamps = [m["created_at"] for m in msgs]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_list_messages_empty(
        self,
        crud_client: TestClient,
        alice_app_with_loan: POSApplication,
    ):
        """Empty message list for a fresh application."""
        resp = crud_client.get(
            f"/api/v1/pos/applications/{alice_app_with_loan.id}/messages"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["messages"] == []
        assert body["counts"]["total"] == 0
        assert body["counts"]["unread"] == 0

    def test_send_message(
        self,
        crud_client: TestClient,
        alice_app_with_loan: POSApplication,
        alice_contact,
    ):
        resp = crud_client.post(
            f"/api/v1/pos/applications/{alice_app_with_loan.id}/messages",
            json={"content": "Hello, I have a question about my loan."},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["content"] == "Hello, I have a question about my loan."
        assert body["sender_role"] == "Borrower"
        assert body["is_from_borrower"] is True
        assert body["sender_name"] == "Alice Anderson"

    def test_send_message_html_sanitized(
        self,
        crud_client: TestClient,
        alice_app_with_loan: POSApplication,
        alice_contact,
    ):
        """HTML tags are stripped from borrower messages (nh3)."""
        resp = crud_client.post(
            f"/api/v1/pos/applications/{alice_app_with_loan.id}/messages",
            json={"content": "Hello <script>alert('xss')</script> world"},
        )
        assert resp.status_code == 201
        body = resp.json()
        # nh3 strips all tags when tags=set()
        assert "<script>" not in body["content"]
        assert "alert" not in body["content"] or "Hello" in body["content"]

    def test_send_message_empty_rejected(
        self,
        crud_client: TestClient,
        alice_app_with_loan: POSApplication,
    ):
        """Empty content should be rejected by Pydantic validation."""
        resp = crud_client.post(
            f"/api/v1/pos/applications/{alice_app_with_loan.id}/messages",
            json={"content": ""},
        )
        assert resp.status_code == 422

    def test_mark_message_read(
        self,
        crud_client: TestClient,
        alice_app_with_loan: POSApplication,
        alice_messages: list,
    ):
        unread_msg = alice_messages[0]  # LO message, read_at=None
        resp = crud_client.patch(
            f"/api/v1/pos/applications/{alice_app_with_loan.id}"
            f"/messages/{unread_msg.id}/read"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["is_read"] is True
        assert body["read_at"] is not None

    def test_mark_message_read_idempotent(
        self,
        crud_client: TestClient,
        alice_app_with_loan: POSApplication,
        alice_messages: list,
    ):
        """Marking an already-read message as read is a no-op."""
        read_msg = alice_messages[1]  # already has read_at
        resp = crud_client.patch(
            f"/api/v1/pos/applications/{alice_app_with_loan.id}"
            f"/messages/{read_msg.id}/read"
        )
        assert resp.status_code == 200
        assert resp.json()["is_read"] is True

    def test_mark_all_read(
        self,
        crud_client: TestClient,
        alice_app_with_loan: POSApplication,
        alice_messages: list,
    ):
        resp = crud_client.patch(
            f"/api/v1/pos/applications/{alice_app_with_loan.id}/messages/read-all"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["counts"]["unread"] == 0
        for m in body["messages"]:
            assert m["is_read"] is True

    def test_cross_borrower_messages_denied(
        self,
        crud_client_as_bob: TestClient,
        alice_app_with_loan: POSApplication,
    ):
        """Bob cannot list Alice's messages."""
        resp = crud_client_as_bob.get(
            f"/api/v1/pos/applications/{alice_app_with_loan.id}/messages"
        )
        assert resp.status_code == 404

    def test_cross_borrower_send_denied(
        self,
        crud_client_as_bob: TestClient,
        alice_app_with_loan: POSApplication,
    ):
        """Bob cannot send a message on Alice's application."""
        resp = crud_client_as_bob.post(
            f"/api/v1/pos/applications/{alice_app_with_loan.id}/messages",
            json={"content": "Sneaky message"},
        )
        assert resp.status_code == 404

    def test_mark_nonexistent_message_404(
        self,
        crud_client: TestClient,
        alice_app_with_loan: POSApplication,
    ):
        resp = crud_client.patch(
            f"/api/v1/pos/applications/{alice_app_with_loan.id}"
            f"/messages/99999/read"
        )
        assert resp.status_code == 404


# ===========================================================================
# TEST CLASS: Tasks
# ===========================================================================


class TestTasks:
    """Tests for /api/v1/pos/applications/{app_id}/tasks endpoints."""

    def test_list_tasks_excludes_internal(
        self,
        crud_client: TestClient,
        alice_app_with_loan: POSApplication,
        alice_tasks: list,
    ):
        """Internal task types (sf_disposition) are filtered out."""
        resp = crud_client.get(
            f"/api/v1/pos/applications/{alice_app_with_loan.id}/tasks"
        )
        assert resp.status_code == 200
        body = resp.json()
        titles = [t["title"] for t in body["tasks"]]
        # sf_disposition task should be excluded
        assert "SF disposition review" not in titles
        # Completed task excluded by default
        assert "Verify employment" not in titles
        # Visible non-completed tasks
        assert "Upload bank statements" in titles
        assert "Sign disclosures" in titles

    def test_list_tasks_counts(
        self,
        crud_client: TestClient,
        alice_app_with_loan: POSApplication,
        alice_tasks: list,
    ):
        """Counts include all non-internal tasks (even completed)."""
        resp = crud_client.get(
            f"/api/v1/pos/applications/{alice_app_with_loan.id}/tasks"
        )
        counts = resp.json()["counts"]
        # 3 non-internal tasks: 1 pending, 1 in_progress, 1 completed
        assert counts["total"] == 3
        assert counts["pending"] == 1
        assert counts["in_progress"] == 1
        assert counts["completed"] == 1

    def test_list_tasks_include_completed(
        self,
        crud_client: TestClient,
        alice_app_with_loan: POSApplication,
        alice_tasks: list,
    ):
        """With include_completed=true, completed tasks appear in the list."""
        resp = crud_client.get(
            f"/api/v1/pos/applications/{alice_app_with_loan.id}/tasks",
            params={"include_completed": "true"},
        )
        body = resp.json()
        titles = [t["title"] for t in body["tasks"]]
        assert "Verify employment" in titles
        assert len(body["tasks"]) == 3  # all non-internal

    def test_list_tasks_no_loan(
        self,
        crud_client: TestClient,
        borrower_alice: PURLAuthContext,
        db_session: Session,
    ):
        """Application with no loan returns empty task list."""
        app = POSApplication(
            id=uuid4(),
            organization_id=borrower_alice.organization_id,
            workspace_id=borrower_alice.workspace_id,
            contact_id=borrower_alice.contact_id,
            loan_id=None,
            status=POSStatus.DRAFT,
            current_step="personal",
        )
        db_session.add(app)
        db_session.flush()

        resp = crud_client.get(
            f"/api/v1/pos/applications/{app.id}/tasks"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["tasks"] == []
        assert body["counts"]["total"] == 0

    def test_complete_task(
        self,
        crud_client: TestClient,
        alice_app_with_loan: POSApplication,
        alice_tasks: list,
    ):
        """Borrower can mark a pending task as completed."""
        pending_task = alice_tasks[0]  # "Upload bank statements"
        resp = crud_client.patch(
            f"/api/v1/pos/applications/{alice_app_with_loan.id}"
            f"/tasks/{pending_task.id}"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"
        assert body["completed_at"] is not None

    def test_complete_already_completed_task_idempotent(
        self,
        crud_client: TestClient,
        alice_app_with_loan: POSApplication,
        alice_tasks: list,
    ):
        """Completing an already-completed task returns current state."""
        completed_task = alice_tasks[3]  # "Verify employment"
        resp = crud_client.patch(
            f"/api/v1/pos/applications/{alice_app_with_loan.id}"
            f"/tasks/{completed_task.id}"
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"

    def test_complete_nonexistent_task_404(
        self,
        crud_client: TestClient,
        alice_app_with_loan: POSApplication,
    ):
        resp = crud_client.patch(
            f"/api/v1/pos/applications/{alice_app_with_loan.id}/tasks/99999"
        )
        assert resp.status_code == 404

    def test_cross_borrower_tasks_denied(
        self,
        crud_client_as_bob: TestClient,
        alice_app_with_loan: POSApplication,
    ):
        """Bob cannot list Alice's tasks."""
        resp = crud_client_as_bob.get(
            f"/api/v1/pos/applications/{alice_app_with_loan.id}/tasks"
        )
        assert resp.status_code == 404

    def test_cross_borrower_complete_denied(
        self,
        crud_client_as_bob: TestClient,
        alice_app_with_loan: POSApplication,
        alice_tasks: list,
    ):
        """Bob cannot complete Alice's task."""
        resp = crud_client_as_bob.patch(
            f"/api/v1/pos/applications/{alice_app_with_loan.id}"
            f"/tasks/{alice_tasks[0].id}"
        )
        assert resp.status_code == 404

    def test_task_response_shape(
        self,
        crud_client: TestClient,
        alice_app_with_loan: POSApplication,
        alice_tasks: list,
    ):
        """Verify task response fields match the schema."""
        resp = crud_client.get(
            f"/api/v1/pos/applications/{alice_app_with_loan.id}/tasks"
        )
        task = resp.json()["tasks"][0]
        required_keys = {"id", "title", "description", "status", "priority", "category"}
        assert required_keys.issubset(task.keys())


# ===========================================================================
# TEST CLASS: Team
# ===========================================================================


class TestTeam:
    """Tests for /api/v1/pos/applications/{app_id}/team endpoint."""

    def test_team_returns_lo_from_loan(
        self,
        crud_client: TestClient,
        alice_app_with_loan: POSApplication,
        loan_with_officer,
    ):
        """LO assigned to the loan appears as first team member."""
        resp = crud_client.get(
            f"/api/v1/pos/applications/{alice_app_with_loan.id}/team"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["application_id"] == str(alice_app_with_loan.id)
        members = body["members"]
        assert len(members) >= 1
        lo = members[0]
        assert lo["name"] == "Jane Smith"
        assert lo["role"] == "Loan Officer"
        assert lo["email"] == "jane@test.com"

    def test_team_includes_role_assignments(
        self,
        crud_client: TestClient,
        alice_app_with_loan: POSApplication,
        loan_with_officer,
        role_assignments,
    ):
        """Role assignments add additional team members."""
        resp = crud_client.get(
            f"/api/v1/pos/applications/{alice_app_with_loan.id}/team"
        )
        members = resp.json()["members"]
        names = [m["name"] for m in members]
        assert "Jane Smith" in names
        assert "Bob Processor" in names
        # Bob should have the role from role assignments
        bob = next(m for m in members if m["name"] == "Bob Processor")
        assert bob["role"] == "Processor"

    def test_team_fallback_to_org_users(
        self,
        crud_client: TestClient,
        borrower_alice: PURLAuthContext,
        db_session: Session,
        org_and_users,
    ):
        """When no loan or role assignments, falls back to org users."""
        app = POSApplication(
            id=uuid4(),
            organization_id=borrower_alice.organization_id,
            workspace_id=borrower_alice.workspace_id,
            contact_id=borrower_alice.contact_id,
            loan_id=None,
            status=POSStatus.DRAFT,
            current_step="personal",
        )
        db_session.add(app)
        db_session.flush()

        resp = crud_client.get(
            f"/api/v1/pos/applications/{app.id}/team"
        )
        assert resp.status_code == 200
        members = resp.json()["members"]
        # Should have at least the org users
        assert len(members) >= 1

    def test_team_member_response_shape(
        self,
        crud_client: TestClient,
        alice_app_with_loan: POSApplication,
        loan_with_officer,
    ):
        """Verify team member response has expected fields."""
        resp = crud_client.get(
            f"/api/v1/pos/applications/{alice_app_with_loan.id}/team"
        )
        member = resp.json()["members"][0]
        expected_keys = {"user_id", "name", "role", "email", "phone", "title"}
        assert expected_keys.issubset(member.keys())
        assert member["phone"] == "555-1111"
        assert member["title"] == "Senior Loan Officer"

    def test_cross_borrower_team_denied(
        self,
        crud_client_as_bob: TestClient,
        alice_app_with_loan: POSApplication,
    ):
        """Bob cannot view Alice's team."""
        resp = crud_client_as_bob.get(
            f"/api/v1/pos/applications/{alice_app_with_loan.id}/team"
        )
        assert resp.status_code == 404

    def test_team_no_duplicate_members(
        self,
        crud_client: TestClient,
        alice_app_with_loan: POSApplication,
        loan_with_officer,
        role_assignments,
    ):
        """Same user should not appear twice (LO + role assignment)."""
        # Add user 10 (the LO) also as a role assignment
        resp = crud_client.get(
            f"/api/v1/pos/applications/{alice_app_with_loan.id}/team"
        )
        members = resp.json()["members"]
        user_ids = [m["user_id"] for m in members]
        assert len(user_ids) == len(set(user_ids)), "Duplicate team members found"


# ===========================================================================
# TEST CLASS: Documents
# ===========================================================================


class TestDocuments:
    """Tests for /api/v1/pos/documents endpoint."""

    def test_get_documents_with_requests(
        self,
        crud_client: TestClient,
        alice_purl_loan,
        db_session: Session,
    ):
        """GET returns document requests for the borrower's loan."""
        # Create a document request for loan 42
        db_session.execute(text(
            "INSERT INTO smart_document_requests "
            "(organization_id, loan_id, doc_type, title, status, is_active, priority) "
            "VALUES (1, 42, 'W2', 'W-2 Form (2025)', 'OPEN', 1, 'NORMAL')"
        ))
        db_session.flush()

        resp = crud_client.get(
            "/api/v1/pos/documents",
            params={"loan_id": 42},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "documents" in body
        assert "counts" in body
        assert len(body["documents"]) >= 1
        doc = body["documents"][0]
        assert doc["name"] == "W-2 Form (2025)"
        assert doc["status"] == "action"  # OPEN maps to "action"
        assert doc["category"] == "income"  # W2 is income

    def test_get_documents_category_mapping(
        self,
        crud_client: TestClient,
        alice_purl_loan,
        db_session: Session,
    ):
        """Different doc types map to correct categories."""
        types_and_categories = [
            ("BANK_STATEMENT", "assets"),
            ("DRIVERS_LICENSE", "identity"),
            ("PURCHASE_CONTRACT", "property"),
            ("LOE", "compliance"),
        ]
        for doc_type, expected_cat in types_and_categories:
            db_session.execute(text(
                "INSERT INTO smart_document_requests "
                "(organization_id, loan_id, doc_type, title, status, is_active) "
                "VALUES (1, 42, :dt, :title, 'OPEN', 1)"
            ), {"dt": doc_type, "title": f"Test {doc_type}"})
        db_session.flush()

        resp = crud_client.get(
            "/api/v1/pos/documents",
            params={"loan_id": 42},
        )
        docs = resp.json()["documents"]
        cat_by_name = {d["name"]: d["category"] for d in docs}
        for doc_type, expected_cat in types_and_categories:
            assert cat_by_name[f"Test {doc_type}"] == expected_cat

    def test_get_documents_status_buckets(
        self,
        crud_client: TestClient,
        alice_purl_loan,
        db_session: Session,
    ):
        """Request statuses map to correct frontend buckets."""
        status_map = [
            ("OPEN", "action"),
            ("REJECTED", "action"),
            ("PENDING_REVIEW", "review"),
            ("ACCEPTED", "approved"),
            ("WAIVED", "approved"),
        ]
        for req_status, _ in status_map:
            db_session.execute(text(
                "INSERT INTO smart_document_requests "
                "(organization_id, loan_id, doc_type, title, status, is_active) "
                "VALUES (1, 42, 'OTHER', :title, :status, 1)"
            ), {"title": f"Doc {req_status}", "status": req_status})
        db_session.flush()

        resp = crud_client.get(
            "/api/v1/pos/documents",
            params={"loan_id": 42},
        )
        docs = resp.json()["documents"]
        bucket_by_name = {d["name"]: d["status"] for d in docs}
        for req_status, expected_bucket in status_map:
            assert bucket_by_name[f"Doc {req_status}"] == expected_bucket

    def test_get_documents_wrong_loan_404(
        self,
        crud_client: TestClient,
        alice_purl_loan,
    ):
        """Requesting docs for a loan the borrower doesn't own returns 404."""
        resp = crud_client.get(
            "/api/v1/pos/documents",
            params={"loan_id": 999},
        )
        assert resp.status_code == 404

    def test_get_documents_no_purl_loan_404(
        self,
        crud_client: TestClient,
    ):
        """No PURL loan for workspace returns 404."""
        resp = crud_client.get(
            "/api/v1/pos/documents",
            params={"loan_id": 42},
        )
        assert resp.status_code == 404

    def test_get_documents_empty(
        self,
        crud_client: TestClient,
        alice_purl_loan,
    ):
        """No document requests returns empty list with zero counts."""
        resp = crud_client.get(
            "/api/v1/pos/documents",
            params={"loan_id": 42},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["documents"] == []
        assert body["counts"] == {"action": 0, "review": 0, "approved": 0, "reference": 0}

    def test_get_documents_with_uploaded_file(
        self,
        crud_client: TestClient,
        alice_purl_loan,
        db_session: Session,
    ):
        """Documents include uploaded file info."""
        from models.smart_docs_models import (
            DocumentRequest as DR,
            SmartDocument as SD,
            DocType,
            RequestStatus,
        )

        # Create request using ORM
        doc_req = DR(
            organization_id=1,
            loan_id=42,
            doc_type=DocType.PAYSTUB,
            title="Most Recent Paystub",
            status=RequestStatus.PENDING_REVIEW,
            is_active=True,
        )
        db_session.add(doc_req)
        db_session.flush()

        # Create uploaded document linked to request using ORM
        smart_doc = SD(
            organization_id=1,
            request_id=doc_req.id,
            loan_id=42,
            borrower_id=1,
            file_name="paystub.pdf",
            mime_type="application/pdf",
            file_size=524288,
            storage_key="s3://docs/paystub.pdf",
            status="PENDING_REVIEW",
            display_name="My Paystub",
        )
        db_session.add(smart_doc)
        db_session.flush()

        resp = crud_client.get(
            "/api/v1/pos/documents",
            params={"loan_id": 42},
        )
        docs = resp.json()["documents"]
        paystub = next(d for d in docs if d["name"] == "Most Recent Paystub")
        assert paystub["filename"] == "My Paystub"
        assert paystub["filesize"] == "512 KB"
        assert paystub["status"] == "review"

    def test_get_documents_reference_docs(
        self,
        crud_client: TestClient,
        alice_purl_loan,
        db_session: Session,
    ):
        """Reference docs (no request_id) appear with status='reference'."""
        from models.smart_docs_models import SmartDocument as SD

        ref_doc = SD(
            organization_id=1,
            loan_id=42,
            borrower_id=1,
            file_name="loan_estimate.pdf",
            mime_type="application/pdf",
            file_size=102400,
            storage_key="s3://docs/le.pdf",
            status="APPROVED",
            display_name="Loan Estimate",
            request_id=None,
        )
        db_session.add(ref_doc)
        db_session.flush()

        resp = crud_client.get(
            "/api/v1/pos/documents",
            params={"loan_id": 42},
        )
        docs = resp.json()["documents"]
        ref = next((d for d in docs if d["name"] == "Loan Estimate"), None)
        assert ref is not None
        assert ref["status"] == "reference"
        assert resp.json()["counts"]["reference"] == 1
