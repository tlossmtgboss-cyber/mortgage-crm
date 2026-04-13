"""
Document Generator Unit Tests

Tests for aria/documents/document_generator.py:
  - Pre-approval letter generation
  - Conditional approval letter generation
  - Adverse action notice generation
  - Letter of Explanation (LOE) generation (with mocked Claude API)
  - PDF rendering via _render_pdf()

All async methods tested with @pytest.mark.asyncio.
Claude API calls are mocked so no network requests are made.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date, timedelta

pytestmark = [pytest.mark.unit]

# ── Shared test fixtures ─────────────────────────────────────────────────────

@pytest.fixture
def generator():
    from aria.documents.document_generator import DocumentGenerator
    return DocumentGenerator()


@pytest.fixture
def sample_borrower():
    return {
        "full_name": "Jane A. Doe",
        "loan_number": "LN-2026-00451",
    }


@pytest.fixture
def sample_loan():
    return {
        "loan_type": "FHA",
        "loan_amount": 385000,
        "rate_lock_days": 45,
    }


@pytest.fixture
def sample_lo():
    return {
        "full_name": "Michael Torres",
        "title": "Senior Loan Officer",
        "phone": "(843) 555-1234",
        "email": "mtorres@perenniaai.com",
        "nmls_number": "1234567",
        "org_name": "Perennia Mortgage",
        "org_address": "100 Broad St, Suite 400, Charleston, SC 29401",
    }


# ── Pre-Approval Letter ─────────────────────────────────────────────────────

class TestGeneratePreapprovalLetter:

    @pytest.mark.asyncio
    async def test_returns_dict_with_required_keys(self, generator, sample_borrower, sample_loan, sample_lo):
        """generate_preapproval_letter returns a dict containing document_id, pdf_bytes, preview_text, and letter_text."""
        result = await generator.generate_preapproval_letter(
            borrower=sample_borrower,
            loan=sample_loan,
            lo=sample_lo,
            approval_amount=385000.0,
        )

        assert isinstance(result, dict)
        assert "document_id" in result
        assert "pdf_bytes" in result
        assert "preview_text" in result
        assert "letter_text" in result

    @pytest.mark.asyncio
    async def test_preview_includes_borrower_name_and_amount(self, generator, sample_borrower, sample_loan, sample_lo):
        """Preview text must include the borrower's name and formatted approval amount."""
        result = await generator.generate_preapproval_letter(
            borrower=sample_borrower,
            loan=sample_loan,
            lo=sample_lo,
            approval_amount=425000.0,
        )

        preview = result["preview_text"]
        assert "Jane A. Doe" in preview
        assert "$425,000" in preview

    @pytest.mark.asyncio
    async def test_pdf_bytes_start_with_pdf_header(self, generator, sample_borrower, sample_loan, sample_lo):
        """PDF output must begin with the %PDF magic bytes."""
        result = await generator.generate_preapproval_letter(
            borrower=sample_borrower,
            loan=sample_loan,
            lo=sample_lo,
            approval_amount=350000.0,
        )

        pdf = result["pdf_bytes"]
        assert isinstance(pdf, bytes)
        assert pdf[:5] == b"%PDF-"

    @pytest.mark.asyncio
    async def test_respects_expiry_days_parameter(self, generator, sample_borrower, sample_loan, sample_lo):
        """Expiry date in the letter and preview should reflect the expiry_days argument."""
        expiry_days = 60
        expected_expiry = (date.today() + timedelta(days=expiry_days)).strftime("%B %d, %Y")

        result = await generator.generate_preapproval_letter(
            borrower=sample_borrower,
            loan=sample_loan,
            lo=sample_lo,
            approval_amount=300000.0,
            expiry_days=expiry_days,
        )

        assert expected_expiry in result["letter_text"]
        assert expected_expiry in result["preview_text"]

    @pytest.mark.asyncio
    async def test_includes_custom_note_when_provided(self, generator, sample_borrower, sample_loan, sample_lo):
        """When custom_note is supplied, it should appear in the rendered letter text."""
        note = "Borrower has additional reserves in a trust account."

        result = await generator.generate_preapproval_letter(
            borrower=sample_borrower,
            loan=sample_loan,
            lo=sample_lo,
            approval_amount=400000.0,
            custom_note=note,
        )

        assert note in result["letter_text"]


# ── Conditional Approval Letter ──────────────────────────────────────────────

class TestGenerateConditionalApproval:

    @pytest.mark.asyncio
    async def test_returns_conditions_count_in_preview(self, generator, sample_borrower, sample_loan, sample_lo):
        """Preview text must include the number of outstanding conditions."""
        conditions = "Provide updated bank statements\nVerify employment dates\nSign updated 1003"

        result = await generator.generate_conditional_approval(
            borrower=sample_borrower,
            loan=sample_loan,
            lo=sample_lo,
            conditions=conditions,
        )

        preview = result["preview_text"]
        assert "3 outstanding conditions" in preview

    @pytest.mark.asyncio
    async def test_parses_newline_separated_conditions(self, generator, sample_borrower, sample_loan, sample_lo):
        """Conditions string split on newlines should produce correct count and borrower name in preview.

        Note: generate_conditional_approval does not return letter_text, only preview_text,
        pdf_bytes, and document_id. We verify parsing via the conditions count in preview.
        """
        conditions = "Updated W-2s for 2025\nCPA letter for self-employment income"

        result = await generator.generate_conditional_approval(
            borrower=sample_borrower,
            loan=sample_loan,
            lo=sample_lo,
            conditions=conditions,
        )

        preview = result["preview_text"]
        # 2 conditions parsed from the newline-separated string
        assert "2 outstanding conditions" in preview
        assert "Jane A. Doe" in preview


# ── Adverse Action Notice ────────────────────────────────────────────────────

class TestGenerateAdverseActionNotice:

    @pytest.mark.asyncio
    async def test_includes_ecoa_and_fcra_references(self, generator, sample_borrower, sample_lo):
        """Adverse action notice rendered text must reference ECOA and FCRA statutes.

        generate_adverse_action_notice does not return letter_text in its dict,
        so we render the template directly and verify statutory references.
        """
        from aria.documents.document_generator import ADVERSE_ACTION_TEMPLATE
        from jinja2 import Environment, BaseLoader
        from datetime import datetime

        reasons = "Insufficient income\nExcessive debt-to-income ratio"
        reasons_list = [r.strip() for r in reasons.split("\n") if r.strip()]

        jinja = Environment(loader=BaseLoader())
        rendered = jinja.from_string(ADVERSE_ACTION_TEMPLATE).render(
            today=datetime.now().strftime("%B %d, %Y"),
            borrower_name=sample_borrower["full_name"],
            loan_number=sample_borrower.get("loan_number", "N/A"),
            reasons_list=reasons_list,
            credit_score=580,
            credit_bureau="Equifax, Experian, TransUnion",
            score_threshold=620,
            lo_name=sample_lo.get("full_name"),
            org_name=sample_lo.get("org_name"),
            lo_nmls=sample_lo.get("nmls_number"),
        )

        assert "ECOA" in rendered
        assert "FCRA" in rendered
        assert "15 U.S.C. 1691" in rendered
        assert "15 U.S.C. 1681" in rendered

    @pytest.mark.asyncio
    async def test_includes_credit_score(self, generator, sample_borrower, sample_lo):
        """Adverse action notice rendered text must disclose the applicant's credit score.

        We verify via the template since the return dict has no letter_text key.
        """
        from aria.documents.document_generator import ADVERSE_ACTION_TEMPLATE
        from jinja2 import Environment, BaseLoader
        from datetime import datetime

        jinja = Environment(loader=BaseLoader())
        rendered = jinja.from_string(ADVERSE_ACTION_TEMPLATE).render(
            today=datetime.now().strftime("%B %d, %Y"),
            borrower_name=sample_borrower["full_name"],
            loan_number=sample_borrower.get("loan_number", "N/A"),
            reasons_list=["High LTV ratio"],
            credit_score=602,
            credit_bureau="Equifax, Experian, TransUnion",
            score_threshold=620,
            lo_name=sample_lo.get("full_name"),
            org_name=sample_lo.get("org_name"),
            lo_nmls=sample_lo.get("nmls_number"),
        )

        assert "602" in rendered


# ── Letter of Explanation (LOE) ──────────────────────────────────────────────

class TestGenerateLOE:

    @pytest.mark.asyncio
    async def test_calls_claude_api_for_explanation_body(self, generator, sample_borrower, sample_lo):
        """generate_loe must call the Anthropic client to produce the explanation body."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="I changed jobs in March 2025 to accept a higher-paying position at a new firm. My income has remained stable throughout the transition.")]

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch("aria.documents.document_generator.client", mock_client):
            result = await generator.generate_loe(
                borrower=sample_borrower,
                lo=sample_lo,
                topic="Employment gap",
                details="Borrower switched employers in Q1 2025",
            )

        mock_client.messages.create.assert_called_once()
        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["model"] == "claude-sonnet-4-20250514"
        assert call_kwargs["max_tokens"] == 300

        assert "Employment gap" in result["letter_text"]
        assert "changed jobs" in result["letter_text"]

    @pytest.mark.asyncio
    async def test_includes_borrower_signature_line(self, generator, sample_borrower, sample_lo):
        """LOE letter text must include the borrower's name under a signature line."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="I deposited a $5,000 gift from my parents to cover closing costs.")]

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch("aria.documents.document_generator.client", mock_client):
            result = await generator.generate_loe(
                borrower=sample_borrower,
                lo=sample_lo,
                topic="Large deposit",
            )

        letter = result["letter_text"]
        assert "________________________" in letter
        assert "Jane A. Doe" in letter
        assert "Date: ___________________" in letter


# ── PDF Rendering ────────────────────────────────────────────────────────────

class TestRenderPdf:

    def test_produces_non_empty_bytes(self, generator):
        """_render_pdf should return non-empty bytes."""
        content = "This is a test document.\nWith multiple lines.\n\nAnd a blank line."
        result = generator._render_pdf("Test Document", content, "Test Org Inc")

        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_includes_org_name_in_output(self, generator):
        """Changing the org name must produce different PDF output, confirming it is embedded."""
        content = "Sample letter body for testing."
        pdf_a = generator._render_pdf("Test", content, "Perennia Mortgage")
        pdf_b = generator._render_pdf("Test", content, "Acme Lending Corp")

        # Both are valid PDFs
        assert pdf_a[:5] == b"%PDF-"
        assert pdf_b[:5] == b"%PDF-"

        # The content streams differ because the org name (uppercased in a Paragraph)
        # is part of the rendered page content
        assert pdf_a != pdf_b
