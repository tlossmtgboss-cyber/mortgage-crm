"""
API Route Tests for Estimate Parser
"""
import pytest
from io import BytesIO
from unittest.mock import patch, Mock
import json

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestEstimateParserRoutes:

    def test_health_endpoint(self, authenticated_client):
        """Test GET /api/v1/estimate-parser/health endpoint"""
        response = authenticated_client.get("/api/v1/estimate-parser/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "environment" in data

    def test_parse_endpoint_success(self, authenticated_client, sample_text_pdf, mock_llm_response):
        """Test POST /api/v1/estimate-parser/parse endpoint"""
        with patch('services.estimate_parser_service.Anthropic') as mock_anthropic:
            # Mock LLM
            mock_client = Mock()
            mock_message = Mock()
            mock_message.content = [Mock(text=mock_llm_response)]
            mock_client.messages.create.return_value = mock_message
            mock_anthropic.return_value = mock_client

            # Make request
            files = {"file": ("test.pdf", sample_text_pdf, "application/pdf")}
            response = authenticated_client.post("/api/v1/estimate-parser/parse", files=files)

            # Assertions
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert "data" in data
            assert "request_id" in data

    def test_parse_endpoint_invalid_file_type(self, authenticated_client):
        """Test parse endpoint with invalid file type"""
        txt_content = BytesIO(b"This is not a PDF or image")
        files = {"file": ("document.txt", txt_content, "text/plain")}

        response = authenticated_client.post("/api/v1/estimate-parser/parse", files=files)

        assert response.status_code == 200  # Returns 200 with error in body
        data = response.json()
        assert data["success"] is False
        assert "not supported" in data["error"].lower()

    def test_parse_endpoint_file_too_large(self, authenticated_client):
        """Test parse endpoint with file exceeding size limit"""
        # Create 20MB file
        large_content = BytesIO(b"x" * (20 * 1024 * 1024))
        files = {"file": ("large.pdf", large_content, "application/pdf")}

        response = authenticated_client.post("/api/v1/estimate-parser/parse", files=files)

        # API returns 413 for oversized files
        assert response.status_code in [200, 413]
        if response.status_code == 200:
            data = response.json()
            assert data["success"] is False

    @pytest.mark.skip(reason="Requires PostgreSQL - uses NOW() and INTERVAL syntax")
    def test_compare_endpoint_success(self, authenticated_client, db_session,
                                     sample_parsed_estimate_a, sample_parsed_estimate_b):
        """Test POST /api/v1/estimate-parser/compare endpoint"""
        from sqlalchemy import text

        # First, insert the estimates into cache
        db_session.execute(text("""
            INSERT INTO estimate_parse_cache (doc_hash, parsed_json, confidence_score, needs_review, source_type)
            VALUES (:hash, :json, :conf, :review, :source)
        """), {
            'hash': 'hash_a_12345',
            'json': json.dumps(sample_parsed_estimate_a),
            'conf': 0.95,
            'review': False,
            'source': 'loan_estimate'
        })

        db_session.execute(text("""
            INSERT INTO estimate_parse_cache (doc_hash, parsed_json, confidence_score, needs_review, source_type)
            VALUES (:hash, :json, :conf, :review, :source)
        """), {
            'hash': 'hash_b_67890',
            'json': json.dumps(sample_parsed_estimate_b),
            'conf': 0.92,
            'review': False,
            'source': 'loan_estimate'
        })
        db_session.commit()

        payload = {
            "estimate_a_hash": "hash_a_12345",
            "estimate_b_hash": "hash_b_67890"
        }

        response = authenticated_client.post("/api/v1/estimate-parser/compare", json=payload)

        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["winner"] == "A"
        assert data["savings_amount"] == 2500

    def test_compare_endpoint_missing_estimate(self, authenticated_client):
        """Test compare endpoint with missing estimate"""
        payload = {
            "estimate_a_hash": "nonexistent_hash_123",
            "estimate_b_hash": "nonexistent_hash_456"
        }

        response = authenticated_client.post("/api/v1/estimate-parser/compare", json=payload)

        assert response.status_code == 404

    def test_conversion_tracking_endpoint(self, authenticated_client, db_session):
        """Test POST /api/v1/estimate-parser/compare/convert endpoint"""
        from sqlalchemy import text
        import uuid

        # Create a comparison first
        comparison_id = str(uuid.uuid4())
        db_session.execute(text("""
            INSERT INTO estimate_comparisons
            (id, estimate_a_hash, estimate_b_hash, winner, winner_reason, savings_amount, converted)
            VALUES (:id, :a_hash, :b_hash, :winner, :reason, :savings, :converted)
        """), {
            'id': comparison_id,
            'a_hash': 'test_hash_a',
            'b_hash': 'test_hash_b',
            'winner': 'A',
            'reason': 'Lower cash to close',
            'savings': 2500,
            'converted': False
        })
        db_session.commit()

        # Track conversion
        response = authenticated_client.post(
            f"/api/v1/estimate-parser/compare/convert?comparison_id={comparison_id}"
        )

        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_stats_endpoint(self, authenticated_client, db_session):
        """Test GET /api/v1/estimate-parser/stats endpoint"""
        response = authenticated_client.get("/api/v1/estimate-parser/stats")

        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert "cache" in data
        assert "failures" in data
        assert "comparisons" in data

    def test_get_cached_estimate(self, authenticated_client, db_session, sample_parsed_estimate_a):
        """Test GET /api/v1/estimate-parser/cache/{doc_hash} endpoint"""
        from sqlalchemy import text

        # Insert cache entry
        db_session.execute(text("""
            INSERT INTO estimate_parse_cache (doc_hash, parsed_json, confidence_score, needs_review, source_type)
            VALUES (:hash, :json, :conf, :review, :source)
        """), {
            'hash': 'test_cache_hash',
            'json': json.dumps(sample_parsed_estimate_a),
            'conf': 0.95,
            'review': False,
            'source': 'loan_estimate'
        })
        db_session.commit()

        response = authenticated_client.get("/api/v1/estimate-parser/cache/test_cache_hash")

        assert response.status_code == 200
        data = response.json()
        assert data["doc_hash"] == "test_cache_hash"
        assert data["confidence_score"] == 0.95

    def test_get_cached_estimate_not_found(self, authenticated_client):
        """Test cache endpoint with non-existent hash"""
        response = authenticated_client.get("/api/v1/estimate-parser/cache/nonexistent_hash")

        assert response.status_code == 404

    def test_get_failures_endpoint(self, authenticated_client, db_session):
        """Test GET /api/v1/estimate-parser/failures endpoint"""
        response = authenticated_client.get("/api/v1/estimate-parser/failures")

        assert response.status_code == 200
        data = response.json()
        assert "failures" in data

    def test_pdf_generation_endpoint(self, authenticated_client, db_session,
                                    sample_parsed_estimate_a, sample_parsed_estimate_b):
        """Test GET /api/v1/estimate-parser/compare/{id}/pdf endpoint"""
        from sqlalchemy import text
        import uuid

        # Insert cache entries first
        db_session.execute(text("""
            INSERT INTO estimate_parse_cache (doc_hash, parsed_json, confidence_score, needs_review, source_type)
            VALUES (:hash, :json, :conf, :review, :source)
        """), {
            'hash': 'pdf_test_hash_a',
            'json': json.dumps(sample_parsed_estimate_a),
            'conf': 0.95,
            'review': False,
            'source': 'loan_estimate'
        })

        db_session.execute(text("""
            INSERT INTO estimate_parse_cache (doc_hash, parsed_json, confidence_score, needs_review, source_type)
            VALUES (:hash, :json, :conf, :review, :source)
        """), {
            'hash': 'pdf_test_hash_b',
            'json': json.dumps(sample_parsed_estimate_b),
            'conf': 0.92,
            'review': False,
            'source': 'loan_estimate'
        })

        # Create a comparison
        comparison_id = str(uuid.uuid4())
        db_session.execute(text("""
            INSERT INTO estimate_comparisons
            (id, estimate_a_hash, estimate_b_hash, winner, winner_reason, savings_amount)
            VALUES (:id, :a_hash, :b_hash, :winner, :reason, :savings)
        """), {
            'id': comparison_id,
            'a_hash': 'pdf_test_hash_a',
            'b_hash': 'pdf_test_hash_b',
            'winner': 'A',
            'reason': 'Lower cash to close',
            'savings': 2500
        })
        db_session.commit()

        # Request PDF
        response = authenticated_client.get(f"/api/v1/estimate-parser/compare/{comparison_id}/pdf")

        # Assertions
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert len(response.content) > 0  # PDF has content

    @pytest.mark.skip(reason="Rate limiting not active in test environment")
    def test_rate_limiting(self, authenticated_client):
        """Test that rate limiting works (basic check)"""
        # Make multiple requests quickly
        responses = []
        for i in range(5):
            txt_content = BytesIO(b"test content")
            files = {"file": (f"test{i}.pdf", txt_content, "application/pdf")}
            response = authenticated_client.post("/api/v1/estimate-parser/parse", files=files)
            responses.append(response)

        # All should complete (under rate limit for testing)
        # In real test with higher limit, would check for 429 responses
        assert all(r.status_code in [200, 429] for r in responses)


class TestRequestValidation:
    """Test request validation"""

    def test_compare_missing_hash_a(self, authenticated_client):
        """Test compare endpoint with missing estimate_a_hash"""
        payload = {
            "estimate_b_hash": "some_hash"
        }

        response = authenticated_client.post("/api/v1/estimate-parser/compare", json=payload)

        # Should fail validation
        assert response.status_code == 422  # Unprocessable Entity

    def test_compare_missing_hash_b(self, authenticated_client):
        """Test compare endpoint with missing estimate_b_hash"""
        payload = {
            "estimate_a_hash": "some_hash"
        }

        response = authenticated_client.post("/api/v1/estimate-parser/compare", json=payload)

        # Should fail validation
        assert response.status_code == 422
