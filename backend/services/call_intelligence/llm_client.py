"""
LLM Client for Call Intelligence

Provides structured extraction using Claude or OpenAI models.
Handles retries, rate limiting, and response parsing.
"""

import os
import json
import logging
import asyncio
import re
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from enum import Enum

logger = logging.getLogger(__name__)


# =============================================================================
# CUSTOM EXCEPTIONS
# =============================================================================

class LLMError(Exception):
    """Base exception for LLM-related errors."""
    pass


class LLMTimeoutError(LLMError):
    """Raised when an LLM request times out."""
    pass


class LLMRateLimitError(LLMError):
    """Raised when rate limit is exceeded."""
    pass


class LLMAPIError(LLMError):
    """Raised for API-specific errors (auth, invalid request, etc.)."""
    pass


class LLMParseError(LLMError):
    """Raised when LLM response cannot be parsed."""
    pass


# =============================================================================
# RATE LIMITER
# =============================================================================

class TokenBucketRateLimiter:
    """
    Simple token bucket rate limiter for LLM API calls.

    Limits requests to prevent hitting API rate limits and avoid
    thundering herd problems during retries.
    """

    def __init__(
        self,
        requests_per_minute: int = 60,
        burst_size: int = 10,
    ):
        """
        Initialize rate limiter.

        Args:
            requests_per_minute: Sustained request rate limit
            burst_size: Maximum burst of requests allowed
        """
        self.requests_per_minute = requests_per_minute
        self.burst_size = burst_size
        self.tokens = float(burst_size)
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, timeout: float = 30.0) -> bool:
        """
        Acquire a token to make a request.

        Args:
            timeout: Maximum time to wait for a token

        Returns:
            True if token acquired, False if timed out

        Raises:
            LLMRateLimitError if rate limit exceeded and timeout
        """
        start_time = time.monotonic()

        async with self._lock:
            while True:
                now = time.monotonic()
                # Replenish tokens based on time elapsed
                elapsed = now - self.last_update
                self.tokens = min(
                    self.burst_size,
                    self.tokens + elapsed * (self.requests_per_minute / 60.0)
                )
                self.last_update = now

                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return True

                # Check timeout
                if now - start_time >= timeout:
                    raise LLMRateLimitError(
                        f"Rate limit exceeded, waited {timeout}s for token"
                    )

                # Wait for token replenishment
                wait_time = min(
                    (1.0 - self.tokens) / (self.requests_per_minute / 60.0),
                    timeout - (now - start_time)
                )
                await asyncio.sleep(max(0.1, wait_time))


# Global rate limiters (one per provider)
_rate_limiters: Dict[str, TokenBucketRateLimiter] = {}


def get_rate_limiter(provider: str) -> TokenBucketRateLimiter:
    """Get or create a rate limiter for a provider."""
    if provider not in _rate_limiters:
        # Default limits (can be tuned per provider)
        if provider == "anthropic":
            _rate_limiters[provider] = TokenBucketRateLimiter(
                requests_per_minute=50,  # Conservative for Anthropic
                burst_size=5,
            )
        else:
            _rate_limiters[provider] = TokenBucketRateLimiter(
                requests_per_minute=60,  # OpenAI default tier
                burst_size=10,
            )
    return _rate_limiters[provider]


class LLMProvider(str, Enum):
    """Supported LLM providers."""
    ANTHROPIC = "anthropic"
    OPENAI = "openai"


# Default configuration constants
DEFAULT_ANTHROPIC_MODEL = "claude-3-haiku-20240307"  # Fast and cost-effective for extraction
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"  # Cost-effective OpenAI model
DEFAULT_MAX_TOKENS = 4096  # Sufficient for mortgage data extraction
DEFAULT_TEMPERATURE = 0.0  # Deterministic for structured extraction
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MAX_RETRIES = 3


@dataclass
class LLMConfig:
    """Configuration for LLM client."""
    provider: LLMProvider = LLMProvider.ANTHROPIC
    model: str = DEFAULT_ANTHROPIC_MODEL
    temperature: float = DEFAULT_TEMPERATURE
    max_tokens: int = DEFAULT_MAX_TOKENS
    timeout: int = DEFAULT_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_MAX_RETRIES

    @classmethod
    def from_env(cls) -> "LLMConfig":
        """Create config from environment variables.

        Environment variables:
            CI_LLM_PROVIDER: "anthropic" or "openai" (default: anthropic)
            CI_LLM_MODEL: Model name (default: claude-3-haiku for Anthropic, gpt-4o-mini for OpenAI)
            CI_LLM_TEMPERATURE: 0.0-1.0 (default: 0.0 for deterministic extraction)
            CI_LLM_MAX_TOKENS: Max response tokens (default: 4096)
            CI_LLM_TIMEOUT: Request timeout in seconds (default: 30)
        """
        provider_str = os.getenv("CI_LLM_PROVIDER", "anthropic").lower()
        provider = LLMProvider(provider_str)

        # Use appropriate default model based on provider
        default_model = DEFAULT_OPENAI_MODEL if provider == LLMProvider.OPENAI else DEFAULT_ANTHROPIC_MODEL

        return cls(
            provider=provider,
            model=os.getenv("CI_LLM_MODEL", default_model),
            temperature=float(os.getenv("CI_LLM_TEMPERATURE", str(DEFAULT_TEMPERATURE))),
            max_tokens=int(os.getenv("CI_LLM_MAX_TOKENS", str(DEFAULT_MAX_TOKENS))),
            timeout=int(os.getenv("CI_LLM_TIMEOUT", str(DEFAULT_TIMEOUT_SECONDS))),
        )


@dataclass
class ExtractionField:
    """Definition of a field to extract."""
    name: str
    description: str
    type: str  # string, number, boolean, date, currency
    required: bool = False
    examples: List[str] = None

    def __post_init__(self):
        if self.examples is None:
            self.examples = []


@dataclass
class ExtractionSchema:
    """Schema for structured extraction."""
    fields: List[ExtractionField]
    context: str = ""
    instructions: str = ""


class BaseLLMClient(ABC):
    """Abstract base class for LLM clients."""

    @abstractmethod
    async def extract(
        self,
        transcript: str,
        schema: ExtractionSchema,
        existing_data: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        Extract structured data from transcript.

        Args:
            transcript: The call transcript text
            schema: Extraction schema defining fields to extract
            existing_data: Optional existing borrower data for context

        Returns:
            Dict with extracted fields and confidence scores
        """
        raise NotImplementedError("Subclasses must implement extract()")

    @abstractmethod
    async def extract_with_prompt(
        self,
        prompt: str,
        transcript: str,
    ) -> Dict[str, Any]:
        """
        Extract using custom prompt.

        Args:
            prompt: Custom extraction prompt
            transcript: The transcript text

        Returns:
            Extracted data as dict
        """
        raise NotImplementedError("Subclasses must implement extract_with_prompt()")


class AnthropicClient(BaseLLMClient):
    """Anthropic Claude client for extraction."""

    def __init__(self, config: LLMConfig = None):
        self.config = config or LLMConfig.from_env()
        self._client = None

    def _get_client(self):
        """Lazy initialization of Anthropic client."""
        if self._client is None:
            try:
                import anthropic
                api_key = os.getenv("ANTHROPIC_API_KEY")
                if not api_key:
                    raise ValueError("ANTHROPIC_API_KEY environment variable not set")
                self._client = anthropic.AsyncAnthropic(api_key=api_key)
            except ImportError:
                raise ImportError("anthropic package not installed. Run: pip install anthropic")
        return self._client

    def _build_extraction_prompt(
        self,
        schema: ExtractionSchema,
        transcript: str,
        existing_data: Dict[str, Any] = None,
    ) -> str:
        """Build the extraction prompt."""

        # Build field descriptions
        field_descriptions = []
        for field in schema.fields:
            desc = f"- **{field.name}** ({field.type}): {field.description}"
            if field.examples:
                desc += f"\n  Examples: {', '.join(field.examples)}"
            if field.required:
                desc += " [REQUIRED]"
            field_descriptions.append(desc)

        fields_text = "\n".join(field_descriptions)

        # Build existing data context
        existing_context = ""
        if existing_data:
            existing_context = f"""
## Existing Borrower Data (for context)
```json
{json.dumps(existing_data, indent=2)}
```
"""

        prompt = f"""You are an expert mortgage data extraction assistant. Your task is to extract structured information from a call transcript between a loan officer/AI assistant and a borrower.

## Instructions
{schema.instructions or "Extract the following fields from the transcript. Only extract information that is explicitly stated by the borrower. Do not infer or guess values."}

## Fields to Extract
{fields_text}

{existing_context}

## Call Transcript
```
{transcript}
```

## Response Format
Respond with a JSON object containing the extracted fields. For each extracted field, include:
- The field value
- A confidence score (0-100) based on how clearly the information was stated
- The source quote from the transcript that supports this extraction

Use this exact JSON structure:
```json
{{
  "extractions": {{
    "field_name": {{
      "value": <extracted value or null if not found>,
      "confidence": <0-100>,
      "source_text": "<quote from transcript>"
    }}
  }},
  "notes": "<any important observations about ambiguity or corrections needed>"
}}
```

Important rules:
1. Only extract information explicitly stated by the borrower
2. If the borrower corrects themselves, use the corrected value
3. Handle speech disfluencies (um, uh, like) - extract the actual information
4. If information is unclear or ambiguous, set confidence below 70
5. If a field is not mentioned, set value to null with confidence 0
6. For currency values, extract as numbers (e.g., "seventy thousand" -> 70000)
7. For dates, use ISO format (YYYY-MM-DD) when possible
8. For yes/no questions, extract as boolean true/false

Respond ONLY with the JSON object, no additional text."""

        return prompt

    async def extract(
        self,
        transcript: str,
        schema: ExtractionSchema,
        existing_data: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """Extract structured data using Claude."""
        client = self._get_client()
        prompt = self._build_extraction_prompt(schema, transcript, existing_data)
        rate_limiter = get_rate_limiter("anthropic")

        for attempt in range(self.config.max_retries):
            try:
                # Acquire rate limit token before making request
                await rate_limiter.acquire(timeout=self.config.timeout)

                response = await asyncio.wait_for(
                    client.messages.create(
                        model=self.config.model,
                        max_tokens=self.config.max_tokens,
                        temperature=self.config.temperature,
                        messages=[
                            {"role": "user", "content": prompt}
                        ]
                    ),
                    timeout=self.config.timeout
                )

                # Parse response - validate content exists
                if not response.content:
                    logger.warning("Empty response content from Anthropic API")
                    continue
                content = response.content[0].text

                # Extract JSON from response
                result = self._parse_json_response(content)

                if result:
                    return result
                else:
                    # JSON parse failed - log and retry
                    logger.warning(f"LLM extraction attempt {attempt + 1}: JSON parse failed, retrying...")
                    if attempt < self.config.max_retries - 1:
                        await asyncio.sleep(2 ** attempt)
                    continue

            except asyncio.TimeoutError:
                logger.warning(f"LLM extraction attempt {attempt + 1} timed out after {self.config.timeout}s")
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                else:
                    logger.error(f"LLM extraction failed after {self.config.max_retries} attempts (timeout)")
                    raise LLMTimeoutError(f"Anthropic extraction timed out after {self.config.max_retries} attempts")
            except LLMRateLimitError:
                logger.warning(f"Rate limit hit on attempt {attempt + 1}")
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise
            except json.JSONDecodeError as e:
                logger.warning(f"JSON decode error on attempt {attempt + 1}: {e}")
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise LLMParseError(f"Failed to parse Anthropic response as JSON: {e}")
            except (ConnectionError, OSError) as e:
                # Network-related errors
                logger.warning(f"Network error on attempt {attempt + 1}: {e}")
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise LLMAPIError(f"Network error calling Anthropic API: {e}")
            except Exception as e:
                # Log the exception type for debugging
                logger.warning(f"LLM extraction attempt {attempt + 1} failed ({type(e).__name__}): {e}")
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                else:
                    logger.error(f"LLM extraction failed after {self.config.max_retries} attempts")
                    raise LLMAPIError(f"Anthropic API error: {e}")

        return {"extractions": {}, "notes": "Extraction failed"}

    async def extract_with_prompt(
        self,
        prompt: str,
        transcript: str,
    ) -> Dict[str, Any]:
        """Extract using custom prompt."""
        client = self._get_client()

        full_prompt = f"""{prompt}

## Transcript
```
{transcript}
```

Respond with a JSON object containing the extracted information."""

        try:
            response = await asyncio.wait_for(
                client.messages.create(
                    model=self.config.model,
                    max_tokens=self.config.max_tokens,
                    temperature=self.config.temperature,
                    messages=[
                        {"role": "user", "content": full_prompt}
                    ]
                ),
                timeout=self.config.timeout
            )

            if not response.content:
                logger.warning("Empty response content from Anthropic API")
                return {}
            content = response.content[0].text
            return self._parse_json_response(content) or {}

        except asyncio.TimeoutError:
            logger.error(f"Anthropic custom prompt extraction timed out after {self.config.timeout}s")
            raise  # Re-raise to let caller handle timeout consistently
        except json.JSONDecodeError as e:
            logger.error(f"Anthropic custom prompt returned invalid JSON: {e}")
            return {}  # Return empty for parse errors - data may still be usable
        except Exception as e:
            logger.error(f"Anthropic custom prompt extraction failed: {type(e).__name__}: {e}")
            raise  # Re-raise unexpected errors for caller to handle

    def _parse_json_response(self, content: str) -> Optional[Dict[str, Any]]:
        """Parse JSON from LLM response.

        Attempts multiple parsing strategies:
        1. Direct JSON parse
        2. Extract from markdown code blocks
        3. Find JSON object in text
        """
        # Try direct JSON parse
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            logger.debug("Direct JSON parse failed, trying code block extraction")

        # Try to extract JSON from markdown code blocks
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                logger.debug("Code block JSON parse failed, trying object extraction")

        # Try to find JSON object in text
        try:
            start = content.find('{')
            end = content.rfind('}') + 1
            if start >= 0 and end > start:
                return json.loads(content[start:end])
        except json.JSONDecodeError:
            logger.debug("Object extraction JSON parse failed")

        # Don't log response content - could contain PII echoed from transcript
        logger.warning("Could not parse JSON from LLM response after all parsing attempts")
        return None


class OpenAIClient(BaseLLMClient):
    """OpenAI GPT client for extraction."""

    def __init__(self, config: LLMConfig = None):
        self.config = config or LLMConfig.from_env()
        # Only override model if explicitly using OpenAI and no custom model was set
        if self.config.model.startswith("claude"):
            self.config.model = os.getenv("CI_LLM_MODEL", DEFAULT_OPENAI_MODEL)
        self._client = None

    def _get_client(self):
        """Lazy initialization of OpenAI client."""
        if self._client is None:
            try:
                import openai
                api_key = os.getenv("OPENAI_API_KEY")
                if not api_key:
                    raise ValueError("OPENAI_API_KEY environment variable not set")
                self._client = openai.AsyncOpenAI(api_key=api_key)
            except ImportError:
                raise ImportError("openai package not installed. Run: pip install openai")
        return self._client

    async def extract(
        self,
        transcript: str,
        schema: ExtractionSchema,
        existing_data: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """Extract structured data using GPT."""
        client = self._get_client()
        rate_limiter = get_rate_limiter("openai")

        # Build the prompt (reuse Anthropic's prompt builder logic)
        anthropic_client = AnthropicClient(self.config)
        prompt = anthropic_client._build_extraction_prompt(schema, transcript, existing_data)

        for attempt in range(self.config.max_retries):
            try:
                # Acquire rate limit token before making request
                await rate_limiter.acquire(timeout=self.config.timeout)

                response = await asyncio.wait_for(
                    client.chat.completions.create(
                        model=self.config.model,
                        temperature=self.config.temperature,
                        max_tokens=self.config.max_tokens,
                        messages=[
                            {"role": "system", "content": "You are an expert mortgage data extraction assistant. Always respond with valid JSON."},
                            {"role": "user", "content": prompt}
                        ],
                        response_format={"type": "json_object"}
                    ),
                    timeout=self.config.timeout
                )

                if not response.choices:
                    logger.warning("Empty response choices from OpenAI API")
                    continue
                content = response.choices[0].message.content
                if not content:
                    logger.warning("Empty message content from OpenAI API")
                    continue
                try:
                    result = json.loads(content)
                    return result
                except json.JSONDecodeError:
                    logger.warning(f"OpenAI extraction attempt {attempt + 1}: JSON parse failed, retrying...")
                    if attempt < self.config.max_retries - 1:
                        await asyncio.sleep(2 ** attempt)
                    continue

            except asyncio.TimeoutError:
                logger.warning(f"OpenAI extraction attempt {attempt + 1} timed out after {self.config.timeout}s")
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise LLMTimeoutError(f"OpenAI extraction timed out after {self.config.max_retries} attempts")
            except LLMRateLimitError:
                logger.warning(f"Rate limit hit on attempt {attempt + 1}")
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise
            except (ConnectionError, OSError) as e:
                # Network-related errors
                logger.warning(f"Network error on attempt {attempt + 1}: {e}")
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise LLMAPIError(f"Network error calling OpenAI API: {e}")
            except Exception as e:
                # Log the exception type for debugging
                logger.warning(f"OpenAI extraction attempt {attempt + 1} failed ({type(e).__name__}): {e}")
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise LLMAPIError(f"OpenAI API error: {e}")

        return {"extractions": {}, "notes": "Extraction failed"}

    async def extract_with_prompt(
        self,
        prompt: str,
        transcript: str,
    ) -> Dict[str, Any]:
        """Extract using custom prompt."""
        client = self._get_client()

        try:
            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=self.config.model,
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens,
                    messages=[
                        {"role": "system", "content": "You are an expert mortgage data extraction assistant. Always respond with valid JSON."},
                        {"role": "user", "content": f"{prompt}\n\nTranscript:\n{transcript}"}
                    ],
                    response_format={"type": "json_object"}
                ),
                timeout=self.config.timeout
            )

            if not response.choices or not response.choices[0].message.content:
                logger.warning("Empty response from OpenAI API")
                return {}
            return json.loads(response.choices[0].message.content)

        except asyncio.TimeoutError:
            logger.error(f"OpenAI custom prompt extraction timed out after {self.config.timeout}s")
            raise  # Re-raise to let caller handle timeout consistently
        except json.JSONDecodeError as e:
            logger.error(f"OpenAI custom prompt returned invalid JSON: {e}")
            return {}  # Return empty for parse errors - data may still be usable
        except Exception as e:
            logger.error(f"OpenAI custom prompt extraction failed: {type(e).__name__}: {e}")
            raise  # Re-raise unexpected errors for caller to handle


def create_llm_client(config: LLMConfig = None) -> BaseLLMClient:
    """Factory function to create appropriate LLM client."""
    config = config or LLMConfig.from_env()

    if config.provider == LLMProvider.ANTHROPIC:
        return AnthropicClient(config)
    elif config.provider == LLMProvider.OPENAI:
        return OpenAIClient(config)
    else:
        raise ValueError(f"Unsupported LLM provider: {config.provider}")


# Pre-defined extraction schemas for each agent type
IDENTITY_SCHEMA = ExtractionSchema(
    fields=[
        ExtractionField("first_name", "Borrower's first/given name", "string", required=True, examples=["John", "Mary"]),
        ExtractionField("last_name", "Borrower's last/family name", "string", required=True, examples=["Smith", "Johnson"]),
        ExtractionField("middle_name", "Borrower's middle name", "string"),
        ExtractionField("suffix", "Name suffix", "string", examples=["Jr", "Sr", "III"]),
        ExtractionField("ssn_last_four", "Last 4 digits of SSN (if mentioned)", "string"),
        ExtractionField("date_of_birth", "Date of birth", "date", examples=["1985-03-15"]),
        ExtractionField("email", "Email address", "string"),
        ExtractionField("phone", "Phone number", "string"),
        ExtractionField("marital_status", "Marital status", "string", examples=["single", "married", "divorced", "separated", "widowed"]),
        ExtractionField("dependents", "Number of dependents", "number"),
        ExtractionField("citizenship_status", "Citizenship status", "string", examples=["US_CITIZEN", "PERMANENT_RESIDENT", "NON_PERMANENT_RESIDENT"]),
    ],
    instructions="""Extract borrower identity information from the call transcript.
Be careful to distinguish between the primary borrower and co-borrower information.
Only extract SSN last 4 digits if explicitly mentioned - never attempt to reconstruct full SSN."""
)

PROPERTY_SCHEMA = ExtractionSchema(
    fields=[
        ExtractionField("street_address", "Property street address", "string"),
        ExtractionField("city", "City", "string"),
        ExtractionField("state", "State (2-letter code preferred)", "string"),
        ExtractionField("zip_code", "ZIP code", "string"),
        ExtractionField("property_type", "Type of property", "string", examples=["single_family", "condo", "townhouse", "multi_family", "manufactured"]),
        ExtractionField("purchase_price", "Purchase price", "currency"),
        ExtractionField("down_payment", "Down payment amount", "currency"),
        ExtractionField("down_payment_percent", "Down payment percentage", "number"),
        ExtractionField("current_housing_status", "Current housing situation", "string", examples=["own", "rent", "living_with_family"]),
        ExtractionField("current_housing_payment", "Current monthly housing payment", "currency"),
        ExtractionField("years_at_current_address", "Years at current address", "number"),
    ],
    instructions="""Extract property and address information from the call transcript.
Distinguish between the subject property (being purchased/refinanced) and current residence.
For addresses, extract as much detail as is clearly stated."""
)

EMPLOYMENT_SCHEMA = ExtractionSchema(
    fields=[
        ExtractionField("employer_name", "Current employer name", "string"),
        ExtractionField("job_title", "Job title/position", "string"),
        ExtractionField("employment_start_date", "When started current job", "date"),
        ExtractionField("years_at_job", "Years at current job", "number"),
        ExtractionField("employment_type", "Type of employment", "string", examples=["full_time", "part_time", "contract", "self_employed"]),
        ExtractionField("is_self_employed", "Whether self-employed", "boolean"),
        ExtractionField("business_name", "Business name if self-employed", "string"),
        ExtractionField("industry", "Industry/sector", "string"),
        ExtractionField("employer_phone", "Employer phone number", "string"),
        ExtractionField("employer_address", "Employer address", "string"),
        ExtractionField("previous_employer", "Previous employer name", "string"),
        ExtractionField("years_at_previous_job", "Years at previous job", "number"),
    ],
    instructions="""Extract employment information from the call transcript.
Pay attention to employment history - current and previous employers.
Note any mentions of self-employment, business ownership, or multiple jobs."""
)

FINANCIAL_SCHEMA = ExtractionSchema(
    fields=[
        ExtractionField("annual_salary", "Annual base salary", "currency"),
        ExtractionField("monthly_salary", "Monthly base salary", "currency"),
        ExtractionField("hourly_rate", "Hourly rate if applicable", "currency"),
        ExtractionField("bonus_income", "Annual bonus income", "currency"),
        ExtractionField("commission_income", "Annual commission income", "currency"),
        ExtractionField("overtime_income", "Annual overtime income", "currency"),
        ExtractionField("rental_income", "Monthly rental income", "currency"),
        ExtractionField("other_income", "Other income", "currency"),
        ExtractionField("checking_balance", "Checking account balance", "currency"),
        ExtractionField("savings_balance", "Savings account balance", "currency"),
        ExtractionField("retirement_balance", "401k/IRA balance", "currency"),
        ExtractionField("investment_balance", "Investment account balance", "currency"),
        ExtractionField("gift_funds", "Gift funds for down payment", "currency"),
        ExtractionField("car_payment", "Monthly car payment", "currency"),
        ExtractionField("student_loan_payment", "Monthly student loan payment", "currency"),
        ExtractionField("credit_card_payment", "Monthly credit card payments", "currency"),
        ExtractionField("other_debt_payment", "Other monthly debt payments", "currency"),
    ],
    instructions="""Extract financial information including income, assets, and liabilities.
Convert verbal numbers to digits (e.g., "seventy-five thousand" -> 75000).
Distinguish between annual and monthly amounts - convert to the field's expected unit.
For "around" or "about" amounts, extract the stated number with lower confidence."""
)

COMPLIANCE_SCHEMA = ExtractionSchema(
    fields=[
        ExtractionField("has_bankruptcy", "Has declared bankruptcy", "boolean"),
        ExtractionField("bankruptcy_type", "Type of bankruptcy (Chapter 7, 13)", "string"),
        ExtractionField("bankruptcy_discharge_date", "When bankruptcy was discharged", "date"),
        ExtractionField("has_foreclosure", "Has had a foreclosure", "boolean"),
        ExtractionField("foreclosure_date", "When foreclosure occurred", "date"),
        ExtractionField("has_judgments", "Has outstanding judgments", "boolean"),
        ExtractionField("has_delinquent_debt", "Has delinquent federal debt", "boolean"),
        ExtractionField("is_party_to_lawsuit", "Is party to a lawsuit", "boolean"),
        ExtractionField("has_alimony", "Pays alimony/child support", "boolean"),
        ExtractionField("alimony_amount", "Monthly alimony/support amount", "currency"),
        ExtractionField("will_occupy_as_primary", "Will occupy as primary residence", "boolean"),
        ExtractionField("is_first_time_buyer", "Is first-time homebuyer", "boolean"),
        ExtractionField("has_ownership_interest", "Has ownership in other properties", "boolean"),
    ],
    instructions="""Extract compliance and declaration information from the call.
These are critical for loan underwriting. Look for mentions of:
- Credit events (bankruptcy, foreclosure, judgments)
- Current obligations (alimony, child support)
- Property ownership and occupancy intentions
Pay careful attention to whether the borrower confirms or denies these items."""
)

INTENT_SCHEMA = ExtractionSchema(
    fields=[
        ExtractionField("loan_purpose", "Purpose of the loan", "string", examples=["PURCHASE", "REFINANCE", "CASH_OUT", "CONSTRUCTION"]),
        ExtractionField("loan_type_preference", "Preferred loan type", "string", examples=["CONVENTIONAL", "FHA", "VA", "USDA", "JUMBO"]),
        ExtractionField("rate_type_preference", "Fixed or adjustable rate preference", "string", examples=["FIXED", "ARM"]),
        ExtractionField("target_timeline", "When they want to close", "string"),
        ExtractionField("urgency", "How urgent is the transaction", "string", examples=["URGENT", "SOON", "EXPLORING"]),
        ExtractionField("has_preapproval", "Already has pre-approval", "boolean"),
        ExtractionField("has_realtor", "Has a real estate agent", "boolean"),
        ExtractionField("realtor_name", "Realtor's name", "string"),
        ExtractionField("has_property_identified", "Has identified a specific property", "boolean"),
        ExtractionField("competing_with_other_lenders", "Shopping with other lenders", "boolean"),
    ],
    instructions="""Extract the borrower's loan intent and preferences.
Look for signals about urgency, timeline, and how far along they are in the process.
Note any mentions of competing lenders or existing pre-approvals."""
)

# Export schemas
EXTRACTION_SCHEMAS = {
    "identity": IDENTITY_SCHEMA,
    "property": PROPERTY_SCHEMA,
    "employment": EMPLOYMENT_SCHEMA,
    "financial": FINANCIAL_SCHEMA,
    "compliance": COMPLIANCE_SCHEMA,
    "intent": INTENT_SCHEMA,
}
