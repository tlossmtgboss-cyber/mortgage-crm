"""
Test Fraud Vendor Service & PDF Forensics Integration

Covers:
1. Vendor API call with mock
2. Internal fallback analyzer
3. PDF metadata extraction
4. Font analysis
5. Date validity checking
6. Risk score calculation
7. Combined scoring with vendor + forensics + cross-doc
8. PointPredictive response parsing
9. Resistant AI response parsing
10. Overlay detection
11. Editing trace detection
12. Image consistency analysis
"""

import io
import pytest
from datetime import datetime, date, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from services.smart_docs.integrations.fraud_vendor_service import (
    FraudVendorService,
    InternalFraudAnalyzer,
    FraudIndicator,
    VendorFraudResult,
    get_fraud_vendor_service,
    SUSPICIOUS_PDF_CREATORS,
)
from services.smart_docs.pdf_forensics_service import (
    PDFForensicsService,
    ForensicsFinding,
    ForensicsReport,
    get_pdf_forensics_service,
    EDITING_SOFTWARE,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_db():
    """Mock database session."""
    return MagicMock()


@pytest.fixture
def vendor_service(mock_db):
    """FraudVendorService configured for internal analysis."""
    with patch.dict("os.environ", {
        "FRAUD_VENDOR": "internal",
        "FRAUD_VENDOR_API_KEY": "",
        "FRAUD_VENDOR_API_URL": "",
    }):
        return FraudVendorService(mock_db)


@pytest.fixture
def internal_analyzer():
    """InternalFraudAnalyzer instance."""
    return InternalFraudAnalyzer()


@pytest.fixture
def forensics_service():
    """PDFForensicsService instance."""
    return PDFForensicsService()


def _make_minimal_pdf(
    creator: str = "TestApp",
    producer: str = "TestLib",
    creation_date: str = "D:20260101120000",
    modification_date: str = "D:20260101120000",
) -> bytes:
    """Build a minimal valid-ish PDF for metadata testing."""
    # This is a simplified PDF-like byte stream for testing regex-based
    # metadata extraction. It is NOT a fully valid PDF but contains the
    # markers that the regex parser looks for.
    header = b"%PDF-1.7\n"
    info = (
        f"1 0 obj\n"
        f"<< /Creator ({creator}) "
        f"/Producer ({producer}) "
        f"/CreationDate ({creation_date}) "
        f"/ModDate ({modification_date}) "
        f">>\n"
        f"endobj\n"
    ).encode("latin-1")
    # Add a dummy font reference for font extraction tests
    font_block = (
        b"2 0 obj\n"
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\n"
        b"endobj\n"
        b"3 0 obj\n"
        b"<< /Type /Font /Subtype /TrueType /BaseFont /TimesNewRoman >>\n"
        b"endobj\n"
        b"4 0 obj\n"
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier-Bold >>\n"
        b"endobj\n"
    )
    trailer = b"%%EOF"
    return header + info + font_block + trailer


def _make_photoshop_pdf() -> bytes:
    """Build a PDF that looks like it was created with Photoshop."""
    return _make_minimal_pdf(
        creator="Adobe Photoshop CC 2024",
        producer="Adobe Photoshop CC 2024",
    )


def _make_modified_pdf() -> bytes:
    """Build a PDF with a large creation-to-modification gap."""
    return _make_minimal_pdf(
        creator="ADP Payroll",
        producer="ADP Inc.",
        creation_date="D:20260101120000",
        modification_date="D:20260115120000",  # 14 days later
    )


def _make_future_dated_pdf() -> bytes:
    """Build a PDF with a future creation date."""
    future = datetime.now(timezone.utc) + timedelta(days=30)
    future_str = future.strftime("D:%Y%m%d%H%M%S")
    return _make_minimal_pdf(
        creator="Microsoft Word",
        producer="Microsoft Office",
        creation_date=future_str,
    )


# =============================================================================
# TEST INTERNAL FRAUD ANALYZER — PDF METADATA
# =============================================================================

class TestInternalFraudAnalyzerMetadata:
    """Test InternalFraudAnalyzer.analyze_pdf_metadata."""

    def test_extracts_basic_metadata(self, internal_analyzer):
        """Should extract creator, producer, and dates from PDF."""
        pdf = _make_minimal_pdf()
        result = internal_analyzer.analyze_pdf_metadata(pdf)

        assert result["creator"] == "TestApp"
        assert result["producer"] == "TestLib"
        assert result["creation_date"] is not None
        assert result["modification_date"] is not None

    def test_flags_photoshop_creator(self, internal_analyzer):
        """Should flag documents created with Photoshop as critical."""
        pdf = _make_photoshop_pdf()
        result = internal_analyzer.analyze_pdf_metadata(pdf)

        assert len(result["indicators"]) >= 1
        critical_indicators = [
            i for i in result["indicators"]
            if i.severity == "critical" and i.indicator_type == "metadata_anomaly"
        ]
        assert len(critical_indicators) >= 1
        assert "photoshop" in critical_indicators[0].description.lower()

    def test_flags_modification_gap(self, internal_analyzer):
        """Should flag significant gap between creation and modification dates."""
        pdf = _make_modified_pdf()
        result = internal_analyzer.analyze_pdf_metadata(pdf)

        gap_indicators = [
            i for i in result["indicators"]
            if "modified" in i.description.lower()
        ]
        assert len(gap_indicators) >= 1

    def test_flags_future_creation_date(self, internal_analyzer):
        """Should flag PDFs with future creation dates."""
        pdf = _make_future_dated_pdf()
        result = internal_analyzer.analyze_pdf_metadata(pdf)

        future_indicators = [
            i for i in result["indicators"]
            if i.indicator_type == "date_mismatch"
        ]
        assert len(future_indicators) >= 1

    def test_legitimate_creator_no_flags(self, internal_analyzer):
        """Should not flag legitimate document creators."""
        pdf = _make_minimal_pdf(
            creator="ADP Payroll Systems",
            producer="ADP Inc.",
        )
        result = internal_analyzer.analyze_pdf_metadata(pdf)

        critical_indicators = [
            i for i in result["indicators"]
            if i.severity == "critical" and i.indicator_type == "metadata_anomaly"
        ]
        assert len(critical_indicators) == 0

    def test_handles_empty_bytes(self, internal_analyzer):
        """Should handle empty file gracefully."""
        result = internal_analyzer.analyze_pdf_metadata(b"")
        assert result["creator"] is None
        assert result["producer"] is None
        assert len(result["indicators"]) == 0

    def test_handles_non_pdf_bytes(self, internal_analyzer):
        """Should handle non-PDF content gracefully."""
        result = internal_analyzer.analyze_pdf_metadata(b"This is not a PDF")
        assert result["creator"] is None


# =============================================================================
# TEST INTERNAL FRAUD ANALYZER — PDF STRUCTURE
# =============================================================================

class TestInternalFraudAnalyzerStructure:
    """Test InternalFraudAnalyzer.analyze_pdf_structure."""

    def test_extracts_fonts_from_pdf(self, internal_analyzer):
        """Should extract font names from PDF content."""
        pdf = _make_minimal_pdf()
        result = internal_analyzer.analyze_pdf_structure(pdf)

        assert result["font_count"] > 0
        assert len(result["fonts_found"]) > 0
        # Check that known fonts from our test PDF are found
        font_names = [f.lower() for f in result["fonts_found"]]
        assert any("helvetica" in f for f in font_names)

    def test_empty_pdf_no_crash(self, internal_analyzer):
        """Should handle PDFs with no fonts gracefully."""
        result = internal_analyzer.analyze_pdf_structure(b"%PDF-1.4\n%%EOF")
        assert result["font_count"] == 0

    def test_handles_empty_bytes(self, internal_analyzer):
        """Should handle empty bytes without crashing."""
        result = internal_analyzer.analyze_pdf_structure(b"")
        assert result["font_count"] == 0
        assert result["has_overlaid_objects"] is False


# =============================================================================
# TEST INTERNAL FRAUD ANALYZER — IMAGE CONSISTENCY
# =============================================================================

class TestInternalFraudAnalyzerImage:
    """Test InternalFraudAnalyzer.analyze_image_consistency."""

    def test_handles_pdf_without_images(self, internal_analyzer):
        """Should handle PDFs with no embedded images."""
        pdf = _make_minimal_pdf()
        result = internal_analyzer.analyze_image_consistency(pdf)

        assert result["images_found"] == 0
        assert result["dpi_consistent"] is True

    def test_handles_empty_bytes(self, internal_analyzer):
        """Should handle empty bytes without crashing."""
        result = internal_analyzer.analyze_image_consistency(b"")
        assert result["images_found"] == 0

    def test_raw_exif_scan_detects_photoshop(self, internal_analyzer):
        """Should detect Photoshop via raw EXIF scanning."""
        # Create bytes with embedded Photoshop marker
        fake_content = b"%PDF-1.4\n" + b"Adobe Photoshop" + b"\n%%EOF"
        result = internal_analyzer.analyze_image_consistency(fake_content)

        assert len(result["exif_flags"]) >= 1
        assert any("Photoshop" in f for f in result["exif_flags"])


# =============================================================================
# TEST INTERNAL FRAUD ANALYZER — RISK SCORE CALCULATION
# =============================================================================

class TestInternalFraudAnalyzerScoring:
    """Test InternalFraudAnalyzer.calculate_forgery_risk_score."""

    def test_no_indicators_returns_zero(self, internal_analyzer):
        """Score should be 0 with no indicators."""
        empty = {"indicators": []}
        score, level = internal_analyzer.calculate_forgery_risk_score(
            empty, empty, empty,
        )
        assert score == 0.0
        assert level == "LOW"

    def test_critical_indicator_high_score(self, internal_analyzer):
        """Critical indicators should push score high."""
        critical_result = {
            "indicators": [
                FraudIndicator(
                    indicator_type="metadata_anomaly",
                    severity="critical",
                    description="Photoshop detected",
                ),
                FraudIndicator(
                    indicator_type="metadata_anomaly",
                    severity="critical",
                    description="Another critical finding",
                ),
                FraudIndicator(
                    indicator_type="image_manipulation",
                    severity="critical",
                    description="Third critical finding",
                ),
            ],
        }
        empty = {"indicators": []}
        score, level = internal_analyzer.calculate_forgery_risk_score(
            critical_result, empty, empty,
        )
        assert score >= 70
        assert level == "HIGH"

    def test_medium_indicators_medium_score(self, internal_analyzer):
        """Multiple medium indicators should yield MEDIUM risk."""
        medium_result = {
            "indicators": [
                FraudIndicator(
                    indicator_type="font_inconsistency",
                    severity="medium",
                    description="Too many fonts",
                ),
                FraudIndicator(
                    indicator_type="font_inconsistency",
                    severity="medium",
                    description="Mixed font types",
                ),
                FraudIndicator(
                    indicator_type="image_manipulation",
                    severity="medium",
                    description="DPI inconsistency",
                ),
                FraudIndicator(
                    indicator_type="font_inconsistency",
                    severity="medium",
                    description="Another font issue",
                ),
                FraudIndicator(
                    indicator_type="font_inconsistency",
                    severity="medium",
                    description="Yet another font issue",
                ),
            ],
        }
        empty = {"indicators": []}
        score, level = internal_analyzer.calculate_forgery_risk_score(
            medium_result, empty, empty,
        )
        assert score >= 40
        assert level == "MEDIUM"

    def test_low_indicators_low_score(self, internal_analyzer):
        """Low-severity indicators should yield LOW risk."""
        low_result = {
            "indicators": [
                FraudIndicator(
                    indicator_type="metadata_anomaly",
                    severity="low",
                    description="Weekend creation",
                ),
            ],
        }
        empty = {"indicators": []}
        score, level = internal_analyzer.calculate_forgery_risk_score(
            low_result, empty, empty,
        )
        assert score < 40
        assert level == "LOW"

    def test_score_capped_at_100(self, internal_analyzer):
        """Score should never exceed 100."""
        many_critical = {
            "indicators": [
                FraudIndicator(
                    indicator_type="metadata_anomaly",
                    severity="critical",
                    description=f"Critical finding {i}",
                )
                for i in range(10)
            ],
        }
        empty = {"indicators": []}
        score, _ = internal_analyzer.calculate_forgery_risk_score(
            many_critical, empty, empty,
        )
        assert score <= 100.0


# =============================================================================
# TEST FRAUD VENDOR SERVICE
# =============================================================================

class TestFraudVendorService:
    """Test FraudVendorService main interface."""

    def test_initialization_defaults_to_internal(self, mock_db):
        """Should default to internal vendor when no env vars set."""
        with patch.dict("os.environ", {}, clear=True):
            service = FraudVendorService(mock_db)
            assert service.vendor == "internal"

    def test_get_vendor_status(self, vendor_service):
        """Should return vendor status dict."""
        status = vendor_service.get_vendor_status()
        assert status["vendor"] == "internal"
        assert status["configured"] is True
        assert isinstance(status["supported_doc_types"], list)
        assert len(status["supported_doc_types"]) > 0

    def test_get_supported_doc_types(self, vendor_service):
        """Should return supported doc types for the vendor."""
        types = vendor_service.get_supported_doc_types()
        assert "paystub" in types
        assert "w2" in types
        assert "bank_statement" in types

    @pytest.mark.asyncio
    async def test_analyze_document_internal(self, vendor_service):
        """Should run internal analysis when vendor is 'internal'."""
        pdf = _make_minimal_pdf()
        result = await vendor_service.analyze_document(
            file_bytes=pdf,
            filename="test.pdf",
            doc_type="paystub",
            loan_id=1,
            org_id=1,
        )

        assert isinstance(result, VendorFraudResult)
        assert result.vendor == "internal"
        assert result.risk_score >= 0
        assert result.risk_level in ("HIGH", "MEDIUM", "LOW")
        assert result.recommendation in ("flag", "review", "pass")
        assert result.analysis_duration_ms >= 0

    @pytest.mark.asyncio
    async def test_analyze_photoshop_pdf_flags_high_risk(self, vendor_service):
        """Should flag Photoshop PDFs as high risk."""
        pdf = _make_photoshop_pdf()
        result = await vendor_service.analyze_document(
            file_bytes=pdf,
            filename="suspicious.pdf",
            doc_type="paystub",
            loan_id=1,
            org_id=1,
        )

        assert result.risk_score > 0
        assert len(result.indicators) >= 1
        critical = [i for i in result.indicators if i.severity == "critical"]
        assert len(critical) >= 1

    @pytest.mark.asyncio
    async def test_analyze_document_vendor_fallback(self, mock_db):
        """Should fall back to internal when vendor API fails."""
        with patch.dict("os.environ", {
            "FRAUD_VENDOR": "pointpredictive",
            "FRAUD_VENDOR_API_KEY": "fake-key",
            "FRAUD_VENDOR_API_URL": "https://fake.example.com",
        }):
            service = FraudVendorService(mock_db)

            # Mock the httpx call to raise
            with patch(
                "services.smart_docs.integrations.fraud_vendor_service.FraudVendorService._call_pointpredictive",
                side_effect=Exception("Connection refused"),
            ):
                pdf = _make_minimal_pdf()
                result = await service.analyze_document(
                    file_bytes=pdf,
                    filename="test.pdf",
                    doc_type="paystub",
                    loan_id=1,
                    org_id=1,
                )

                # Should fall back to internal
                assert result.vendor == "internal"
                assert isinstance(result.risk_score, float)

    def test_vendor_fraud_result_to_dict(self):
        """VendorFraudResult.to_dict should serialize properly."""
        result = VendorFraudResult(
            risk_score=75.0,
            risk_level="HIGH",
            indicators=[
                FraudIndicator(
                    indicator_type="metadata_anomaly",
                    severity="critical",
                    description="Test indicator",
                    evidence={"key": "value"},
                ),
            ],
            vendor="internal",
            analysis_duration_ms=150,
            recommendation="flag",
        )

        d = result.to_dict()
        assert d["risk_score"] == 75.0
        assert d["risk_level"] == "HIGH"
        assert len(d["indicators"]) == 1
        assert d["indicators"][0]["indicator_type"] == "metadata_anomaly"
        assert d["recommendation"] == "flag"

    def test_parse_pointpredictive_response(self, vendor_service):
        """Should parse PointPredictive API response correctly."""
        resp = {
            "risk_score": 82.5,
            "signals": [
                {
                    "type": "document_forgery",
                    "severity": "high",
                    "description": "Font inconsistency detected",
                    "evidence": {"fonts": ["Arial", "Photoshop-Custom"]},
                },
                {
                    "type": "metadata_tampering",
                    "severity": "critical",
                    "description": "Creation date altered",
                    "evidence": {"original_date": "2025-01-01"},
                },
            ],
            "recommendation": "flag",
        }

        result = vendor_service._parse_pointpredictive_response(resp)

        assert result.risk_score == 82.5
        assert result.risk_level == "HIGH"
        assert result.vendor == "pointpredictive"
        assert result.recommendation == "flag"
        assert len(result.indicators) == 2
        assert result.indicators[0].indicator_type == "document_forgery"
        assert result.indicators[1].severity == "critical"

    def test_parse_resistant_ai_response(self, vendor_service):
        """Should parse Resistant AI API response correctly."""
        resp = {
            "score": 55.0,
            "findings": [
                {
                    "category": "pixel_manipulation",
                    "severity": "high",
                    "message": "Cloned regions detected",
                    "details": {"regions": [{"x": 100, "y": 200}]},
                },
            ],
            "verdict": "suspicious",
        }

        result = vendor_service._parse_resistant_ai_response(resp)

        assert result.risk_score == 55.0
        assert result.risk_level == "MEDIUM"
        assert result.vendor == "resistant_ai"
        assert result.recommendation == "review"
        assert len(result.indicators) == 1
        assert result.indicators[0].indicator_type == "pixel_manipulation"


# =============================================================================
# TEST PDF FORENSICS SERVICE
# =============================================================================

class TestPDFForensicsService:
    """Test PDFForensicsService."""

    def test_extract_metadata(self, forensics_service):
        """Should extract metadata from a PDF."""
        pdf = _make_minimal_pdf(
            creator="ADP Payroll",
            producer="ADP Inc.",
        )
        metadata = forensics_service.extract_metadata(pdf)

        assert metadata["creator"] is not None
        assert "ADP" in (metadata["creator"] or "") or "ADP" in (metadata["producer"] or "")
        assert metadata["page_count"] >= 0

    def test_extract_metadata_from_empty(self, forensics_service):
        """Should handle empty bytes gracefully."""
        metadata = forensics_service.extract_metadata(b"")
        assert metadata["creator"] is None
        assert metadata["producer"] is None

    def test_analyze_fonts(self, forensics_service):
        """Should list fonts from a PDF."""
        pdf = _make_minimal_pdf()
        fonts = forensics_service.analyze_fonts(pdf)

        assert fonts["font_count"] > 0
        assert len(fonts["fonts"]) > 0
        assert isinstance(fonts["unique_families"], list)
        assert isinstance(fonts["inconsistencies"], list)

    def test_analyze_fonts_empty(self, forensics_service):
        """Should handle no-font PDFs."""
        fonts = forensics_service.analyze_fonts(b"%PDF-1.4\n%%EOF")
        assert fonts["font_count"] == 0

    def test_detect_overlaid_objects_no_crash(self, forensics_service):
        """Should not crash on minimal PDF."""
        pdf = _make_minimal_pdf()
        overlays = forensics_service.detect_overlaid_objects(pdf)
        assert isinstance(overlays, list)

    def test_analyze_images_no_images(self, forensics_service):
        """Should return empty list for PDFs without images."""
        pdf = _make_minimal_pdf()
        images = forensics_service.analyze_images_in_pdf(pdf)
        assert isinstance(images, list)

    def test_check_creation_date_validity_future(self, forensics_service):
        """Should flag future creation dates."""
        future = datetime.now(timezone.utc) + timedelta(days=30)
        future_str = future.strftime("D:%Y%m%d%H%M%S")

        metadata = {"creation_date": future_str}
        result = forensics_service.check_creation_date_validity(
            metadata, "paystub",
        )

        assert result["is_valid"] is False
        assert any(
            i.get("type") == "future_creation_date"
            for i in result["issues"]
        )

    def test_check_creation_date_validity_premature(self, forensics_service):
        """Should flag PDFs created well before the document date."""
        metadata = {"creation_date": "D:20250101120000"}
        doc_date = date(2026, 3, 1)  # Doc date far in the future

        result = forensics_service.check_creation_date_validity(
            metadata, "paystub", doc_date,
        )

        assert result["is_valid"] is False
        premature = [
            i for i in result["issues"]
            if i.get("type") == "premature_creation"
        ]
        assert len(premature) >= 1

    def test_check_creation_date_validity_weekend(self, forensics_service):
        """Should note weekend creation for financial documents."""
        # Find a Saturday
        now = datetime.now(timezone.utc)
        saturday = now + timedelta(days=(5 - now.weekday()) % 7)
        if saturday <= now:
            saturday += timedelta(days=7)
        # Use a past Saturday to avoid future-date flag
        past_saturday = saturday - timedelta(weeks=52)
        sat_str = past_saturday.strftime("D:%Y%m%d%H%M%S")

        metadata = {"creation_date": sat_str}
        result = forensics_service.check_creation_date_validity(
            metadata, "paystub",
        )

        weekend_issues = [
            i for i in result["issues"]
            if i.get("type") == "weekend_creation"
        ]
        assert len(weekend_issues) >= 1

    def test_check_creation_date_no_date(self, forensics_service):
        """Should handle missing creation date gracefully."""
        metadata = {"creation_date": None}
        result = forensics_service.check_creation_date_validity(
            metadata, "paystub",
        )
        assert result["is_valid"] is True
        assert len(result["issues"]) == 0

    def test_detect_editing_traces_photoshop(self, forensics_service):
        """Should detect Photoshop editing traces."""
        pdf = _make_photoshop_pdf()
        traces = forensics_service.detect_editing_traces(pdf)

        assert len(traces) >= 1
        assert any("photoshop" in t.get("software", "").lower() for t in traces)
        assert any(t.get("severity") == "critical" for t in traces)

    def test_detect_editing_traces_clean(self, forensics_service):
        """Should find no editing traces in clean PDFs."""
        pdf = _make_minimal_pdf(
            creator="ADP Payroll",
            producer="ADP Inc.",
        )
        traces = forensics_service.detect_editing_traces(pdf)

        # Should not flag ADP as editing software
        critical_traces = [t for t in traces if t.get("severity") == "critical"]
        assert len(critical_traces) == 0

    def test_detect_editing_traces_8bim_markers(self, forensics_service):
        """Should detect Photoshop 8BIM resource markers."""
        # Create a PDF-like file with embedded 8BIM markers
        content = (
            b"%PDF-1.4\n"
            b"1 0 obj\n<< /Creator (Microsoft Word) /Producer (Word) >>\nendobj\n"
            b"photoshop"  # lowercase to trigger the check
            b"8BIM"       # Photoshop resource block marker
            b"8BIM"
            b"\n%%EOF"
        )
        traces = forensics_service.detect_editing_traces(content)

        bim_traces = [
            t for t in traces
            if t.get("source") == "photoshop_markers"
        ]
        assert len(bim_traces) >= 1

    def test_generate_forensics_report(self, forensics_service):
        """Should generate a complete forensics report."""
        pdf = _make_minimal_pdf()
        report = forensics_service.generate_forensics_report(
            file_bytes=pdf,
            doc_type="paystub",
            filename="test_paystub.pdf",
        )

        assert isinstance(report, ForensicsReport)
        assert report.filename == "test_paystub.pdf"
        assert report.doc_type == "paystub"
        assert report.analysis_timestamp != ""
        assert isinstance(report.metadata, dict)
        assert isinstance(report.fonts, dict)
        assert isinstance(report.findings, list)
        assert report.risk_score >= 0
        assert report.risk_level in ("HIGH", "MEDIUM", "LOW")

    def test_generate_forensics_report_photoshop(self, forensics_service):
        """Should flag Photoshop PDFs in forensics report."""
        pdf = _make_photoshop_pdf()
        report = forensics_service.generate_forensics_report(
            file_bytes=pdf,
            doc_type="paystub",
            filename="suspicious.pdf",
        )

        assert report.risk_score > 0
        assert len(report.findings) >= 1
        critical_findings = [
            f for f in report.findings if f.severity == "critical"
        ]
        assert len(critical_findings) >= 1

    def test_forensics_report_to_dict(self, forensics_service):
        """ForensicsReport.to_dict should serialize properly."""
        pdf = _make_minimal_pdf()
        report = forensics_service.generate_forensics_report(
            file_bytes=pdf,
            doc_type="w2",
            filename="w2_2025.pdf",
        )

        d = report.to_dict()
        assert isinstance(d, dict)
        assert d["filename"] == "w2_2025.pdf"
        assert d["doc_type"] == "w2"
        assert isinstance(d["findings"], list)
        assert "risk_score" in d
        assert "risk_level" in d


# =============================================================================
# TEST COMBINED SCORING (Integration)
# =============================================================================

class TestCombinedScoring:
    """Test the combined scoring logic in FraudDetectionService."""

    def test_combine_analysis_scores_all_available(self):
        """Should weight scores correctly when all components available."""
        from services.smart_docs.fraud_detection_service import FraudDetectionService
        from services.smart_docs.fraud_detection_service import CrossValidationResult

        db = MagicMock()
        service = FraudDetectionService(db)

        vendor_result = VendorFraudResult(
            risk_score=80.0,
            risk_level="HIGH",
            vendor="internal",
        )

        forensics_result = ForensicsReport(
            risk_score=60.0,
            risk_level="MEDIUM",
        )

        cross_doc_result = CrossValidationResult(
            loan_id=1,
            documents_analyzed=5,
            inconsistencies=[],
            fraud_indicators=[],
            risk_score=40,
            risk_level="MEDIUM",
            summary="Test",
            recommendations=[],
        )

        score, level = service._combine_analysis_scores(
            vendor_result=vendor_result,
            forensics_result=forensics_result,
            cross_doc_result=cross_doc_result,
        )

        # Expected: 80*0.4 + 60*0.3 + 40*0.3 = 32 + 18 + 12 = 62
        assert 61.0 <= score <= 63.0
        assert level == "HIGH"

    def test_combine_analysis_scores_vendor_only(self):
        """Should use only vendor score when others unavailable."""
        from services.smart_docs.fraud_detection_service import FraudDetectionService

        db = MagicMock()
        service = FraudDetectionService(db)

        vendor_result = VendorFraudResult(
            risk_score=50.0,
            risk_level="MEDIUM",
            vendor="internal",
        )

        score, level = service._combine_analysis_scores(
            vendor_result=vendor_result,
            forensics_result=None,
            cross_doc_result=None,
        )

        # Only vendor available, should be 50.0 (100% of weight goes to vendor)
        assert score == 50.0
        assert level == "HIGH"

    def test_combine_analysis_scores_none_available(self):
        """Should return 0/LOW when no components available."""
        from services.smart_docs.fraud_detection_service import FraudDetectionService

        db = MagicMock()
        service = FraudDetectionService(db)

        score, level = service._combine_analysis_scores(
            vendor_result=None,
            forensics_result=None,
            cross_doc_result=None,
        )

        assert score == 0.0
        assert level == "LOW"

    def test_combine_analysis_scores_forensics_and_crossdoc(self):
        """Should redistribute weights when vendor unavailable."""
        from services.smart_docs.fraud_detection_service import FraudDetectionService
        from services.smart_docs.fraud_detection_service import CrossValidationResult

        db = MagicMock()
        service = FraudDetectionService(db)

        forensics_result = ForensicsReport(
            risk_score=90.0,
            risk_level="HIGH",
        )

        cross_doc_result = CrossValidationResult(
            loan_id=1,
            documents_analyzed=3,
            inconsistencies=[],
            fraud_indicators=[],
            risk_score=30,
            risk_level="MEDIUM",
            summary="Test",
            recommendations=[],
        )

        score, level = service._combine_analysis_scores(
            vendor_result=None,
            forensics_result=forensics_result,
            cross_doc_result=cross_doc_result,
        )

        # Weights: forensics 0.3, cross_doc 0.3 -> normalized to 0.5 each
        # Expected: 90*0.5 + 30*0.5 = 45 + 15 = 60
        assert 59.0 <= score <= 61.0

    def test_combined_score_capped_at_100(self):
        """Combined score should not exceed 100."""
        from services.smart_docs.fraud_detection_service import FraudDetectionService

        db = MagicMock()
        service = FraudDetectionService(db)

        vendor_result = VendorFraudResult(
            risk_score=100.0,
            risk_level="HIGH",
            vendor="internal",
        )

        forensics_result = ForensicsReport(
            risk_score=100.0,
            risk_level="HIGH",
        )

        score, _ = service._combine_analysis_scores(
            vendor_result=vendor_result,
            forensics_result=forensics_result,
            cross_doc_result=None,
        )

        assert score <= 100.0


# =============================================================================
# TEST FACTORY FUNCTIONS
# =============================================================================

class TestFactoryFunctions:
    """Test factory/singleton functions."""

    def test_get_fraud_vendor_service(self, mock_db):
        """Should create a FraudVendorService instance."""
        service = get_fraud_vendor_service(mock_db)
        assert isinstance(service, FraudVendorService)

    def test_get_pdf_forensics_service(self):
        """Should create a PDFForensicsService instance."""
        service = get_pdf_forensics_service()
        assert isinstance(service, PDFForensicsService)


# =============================================================================
# TEST SUPPORTED DOC TYPES
# =============================================================================

class TestSupportedDocTypes:
    """Test vendor-specific document type support."""

    def test_pointpredictive_doc_types(self, mock_db):
        """PointPredictive should support common financial docs."""
        with patch.dict("os.environ", {"FRAUD_VENDOR": "pointpredictive"}):
            service = FraudVendorService(mock_db)
            types = service.get_supported_doc_types()
            assert "paystub" in types
            assert "w2" in types
            assert "bank_statement" in types

    def test_resistant_ai_doc_types(self, mock_db):
        """Resistant AI should support financial + identity docs."""
        with patch.dict("os.environ", {"FRAUD_VENDOR": "resistant_ai"}):
            service = FraudVendorService(mock_db)
            types = service.get_supported_doc_types()
            assert "paystub" in types
            assert "drivers_license" in types
            assert "passport" in types

    def test_internal_doc_types(self, mock_db):
        """Internal analyzer should support broad doc types."""
        with patch.dict("os.environ", {"FRAUD_VENDOR": "internal"}):
            service = FraudVendorService(mock_db)
            types = service.get_supported_doc_types()
            assert len(types) >= 10
            assert "appraisal" in types
            assert "purchase_contract" in types
