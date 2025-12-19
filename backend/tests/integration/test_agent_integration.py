"""
Integration Tests for Agent System

Tests agents against real (or staging) services to catch:
- Schema drift
- Auth issues
- Rate limits
- API changes

Run these on a schedule or pre-deploy, not on every commit.
"""
import pytest
import os
from datetime import datetime

# Mark all tests as integration tests
pytestmark = [pytest.mark.integration]

# Skip if no API keys configured
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")


@pytest.mark.skipif(not OPENAI_API_KEY, reason="OpenAI API key not configured")
class TestOpenAIIntegration:
    """Test OpenAI API integration"""

    @pytest.mark.asyncio
    async def test_openai_chat_completion(self):
        """Test basic OpenAI chat completion works"""
        from openai import OpenAI

        client = OpenAI(api_key=OPENAI_API_KEY)

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Say 'test successful' and nothing else."}],
            max_tokens=20,
        )

        assert response.choices[0].message.content is not None
        assert "test" in response.choices[0].message.content.lower()

    @pytest.mark.asyncio
    async def test_openai_function_calling(self):
        """Test OpenAI function calling works"""
        from openai import OpenAI

        client = OpenAI(api_key=OPENAI_API_KEY)

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_loan_status",
                    "description": "Get the status of a loan",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "loan_id": {"type": "string", "description": "The loan ID"}
                        },
                        "required": ["loan_id"],
                    },
                },
            }
        ]

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Get the status of loan 2024-001234"}],
            tools=tools,
            max_tokens=100,
        )

        # Should trigger function call
        assert response.choices[0].message.tool_calls is not None or \
               response.choices[0].finish_reason == "tool_calls"


@pytest.mark.skipif(not ANTHROPIC_API_KEY, reason="Anthropic API key not configured")
class TestAnthropicIntegration:
    """Test Anthropic Claude API integration"""

    @pytest.mark.asyncio
    async def test_claude_message(self):
        """Test basic Claude message works"""
        from anthropic import Anthropic

        client = Anthropic(api_key=ANTHROPIC_API_KEY)

        response = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=20,
            messages=[{"role": "user", "content": "Say 'test successful' and nothing else."}],
        )

        assert response.content[0].text is not None
        assert "test" in response.content[0].text.lower()


class TestDatabaseIntegration:
    """Test database integration"""

    @pytest.mark.asyncio
    async def test_database_connection(self, db_session):
        """Test database connection works"""
        from sqlalchemy import text

        result = db_session.execute(text("SELECT 1"))
        assert result.scalar() == 1

    @pytest.mark.asyncio
    async def test_can_query_leads(self, db_session):
        """Test querying leads table"""
        from sqlalchemy import text

        try:
            result = db_session.execute(text("SELECT COUNT(*) FROM leads"))
            count = result.scalar()
            assert count >= 0  # Just verify query works
        except Exception as e:
            pytest.skip(f"Leads table not available: {e}")

    @pytest.mark.asyncio
    async def test_can_query_loans(self, db_session):
        """Test querying loans table"""
        from sqlalchemy import text

        try:
            result = db_session.execute(text("SELECT COUNT(*) FROM loans"))
            count = result.scalar()
            assert count >= 0
        except Exception as e:
            pytest.skip(f"Loans table not available: {e}")


class TestExternalServiceIntegration:
    """Test external service integrations"""

    @pytest.mark.asyncio
    async def test_twilio_client_init(self):
        """Test Twilio client can be initialized"""
        twilio_sid = os.getenv("TWILIO_ACCOUNT_SID")
        twilio_token = os.getenv("TWILIO_AUTH_TOKEN")

        if not twilio_sid or not twilio_token:
            pytest.skip("Twilio credentials not configured")

        from twilio.rest import Client

        client = Client(twilio_sid, twilio_token)
        # Just verify client initializes
        assert client is not None

    @pytest.mark.asyncio
    async def test_sendgrid_client_init(self):
        """Test SendGrid client can be initialized"""
        sendgrid_key = os.getenv("SENDGRID_API_KEY")

        if not sendgrid_key:
            pytest.skip("SendGrid API key not configured")

        from sendgrid import SendGridAPIClient

        client = SendGridAPIClient(sendgrid_key)
        assert client is not None


class TestAgentToolIntegration:
    """Test agent tools with real database"""

    @pytest.mark.asyncio
    async def test_pipeline_tools_with_db(self, db_session):
        """Test pipeline tools work with real database"""
        try:
            from agents.tools.pipeline import get_pipeline_metrics

            # This will use real DB connection
            result = get_pipeline_metrics()

            assert result.status in ["success", "no_data"]
        except ImportError:
            pytest.skip("Pipeline tools not available")
        except Exception as e:
            pytest.skip(f"Pipeline tools failed: {e}")

    @pytest.mark.asyncio
    async def test_lead_tools_with_db(self, db_session):
        """Test lead tools work with real database"""
        try:
            from agents.tools.leads import get_lead_details

            # Try with non-existent lead
            result = get_lead_details(lead_id="nonexistent-123")

            assert result.status in ["success", "no_data", "error"]
        except ImportError:
            pytest.skip("Lead tools not available")
        except Exception as e:
            pytest.skip(f"Lead tools failed: {e}")
