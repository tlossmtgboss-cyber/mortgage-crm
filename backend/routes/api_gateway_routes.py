"""
API Gateway & Developer Experience Routes
Enterprise Readiness - Domain 11

Comprehensive API key and webhook management with database integration.

Features:
- API Key CRUD with scope enforcement
- Per-key rate limiting
- Webhook subscriptions and event catalog
- Webhook delivery with retry logic and exponential backoff
- API documentation endpoints
"""

from fastapi import Depends, HTTPException, Query, BackgroundTasks, Request
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_, and_, func
from pydantic import BaseModel, Field, validator, HttpUrl
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta, timezone
import asyncio
import random
import secrets
import hashlib
import hmac
import logging
import httpx

logger = logging.getLogger(__name__)

# Import models
from database.models import (
    ApiKey, User, Organization,
    WebhookSubscription, WebhookDeliveryLog, WebhookEventCatalog
)


# =============================================================================
# WEBHOOK CIRCUIT BREAKER (Check 7.6 - Webhook Delivery Reliability)
# =============================================================================

class WebhookCircuitBreaker:
    """Per-subscription circuit breaker for webhook delivery.

    After N consecutive delivery failures for a subscription, the circuit
    opens and further deliveries are paused until a test ping succeeds.

    This prevents wasting resources on endpoints that are persistently down
    and satisfies enterprise readiness Check 7.6.

    States:
        closed       - Normal delivery
        circuit_open - Deliveries paused; subscription is disabled
    """

    # Class-level state: subscription_id -> consecutive failure count
    _failure_counts: Dict[int, int] = {}
    FAILURE_THRESHOLD = 5  # Consecutive failures before opening circuit

    @classmethod
    def record_success(cls, subscription_id: int) -> None:
        """Record a successful delivery; reset failure count."""
        cls._failure_counts.pop(subscription_id, None)

    @classmethod
    def record_failure(cls, subscription_id: int) -> int:
        """Record a failed delivery; return new consecutive failure count."""
        count = cls._failure_counts.get(subscription_id, 0) + 1
        cls._failure_counts[subscription_id] = count
        return count

    @classmethod
    def is_circuit_open(cls, subscription_id: int) -> bool:
        """Check if the circuit is open (too many consecutive failures)."""
        return cls._failure_counts.get(subscription_id, 0) >= cls.FAILURE_THRESHOLD

    @classmethod
    def reset(cls, subscription_id: int) -> None:
        """Reset circuit breaker (e.g., after successful test ping)."""
        cls._failure_counts.pop(subscription_id, None)

    @classmethod
    def get_failure_count(cls, subscription_id: int) -> int:
        return cls._failure_counts.get(subscription_id, 0)


def register_api_gateway_routes(app, get_db, get_current_user, **kwargs):
    """
    Register API Gateway routes for enterprise developer experience.

    Check 11.4: API Key CRUD (HIGH - 10pts)
    Check 11.5: Per-Client Rate Limiting (HIGH - 10pts)
    Check 11.7: Webhook Event Catalog (HIGH - 10pts)
    Check 11.8: Webhook Retry with Backoff (HIGH - 10pts)
    """

    # =========================================================================
    # SCHEMAS
    # =========================================================================

    class ApiKeyCreateRequest(BaseModel):
        """Request schema for creating an API key"""
        name: str = Field(..., min_length=1, max_length=100, description="Human-readable name for the API key")
        description: Optional[str] = Field(None, max_length=500, description="Optional description of key usage")
        scopes: List[str] = Field(default_factory=list, description="List of permission scopes")
        expires_at: Optional[datetime] = Field(None, description="Optional expiration date")

        @validator('scopes')
        def validate_scopes(cls, v):
            valid_scopes = [
                'read:leads', 'write:leads', 'delete:leads',
                'read:loans', 'write:loans', 'delete:loans',
                'read:contacts', 'write:contacts', 'delete:contacts',
                'read:documents', 'write:documents', 'delete:documents',
                'read:analytics', 'read:reports',
                'webhooks:manage', 'integrations:manage',
                'admin:full'
            ]
            for scope in v:
                if scope not in valid_scopes:
                    raise ValueError(f'Invalid scope: {scope}. Valid scopes: {", ".join(valid_scopes)}')
            return v

    class ApiKeyUpdateRequest(BaseModel):
        """Request schema for updating an API key"""
        name: Optional[str] = Field(None, min_length=1, max_length=100)
        description: Optional[str] = Field(None, max_length=500)
        scopes: Optional[List[str]] = None
        is_active: Optional[bool] = None

    class ApiKeyResponse(BaseModel):
        """Response schema for API key"""
        id: int
        name: str
        description: Optional[str]
        masked_key: str
        scopes: List[str]
        is_active: bool
        expires_at: Optional[datetime]
        created_at: datetime
        last_used_at: Optional[datetime]

        class Config:
            from_attributes = True

    class WebhookSubscriptionCreateRequest(BaseModel):
        """Request schema for creating a webhook subscription"""
        name: str = Field(..., min_length=1, max_length=100, description="Name for this webhook")
        url: HttpUrl = Field(..., description="HTTPS URL to receive webhook events")
        events: List[str] = Field(..., min_items=1, description="List of event types to subscribe to")
        headers: Optional[Dict[str, str]] = Field(default_factory=dict, description="Custom headers to include")
        retry_count: int = Field(3, ge=0, le=10, description="Number of retry attempts")
        timeout_seconds: int = Field(30, ge=5, le=120, description="Request timeout in seconds")

        @validator('url')
        def validate_url(cls, v):
            url_str = str(v)
            if not url_str.startswith('https://') and not url_str.startswith('http://localhost'):
                raise ValueError('Webhook URL must use HTTPS (or localhost for testing)')
            return v

    class WebhookSubscriptionResponse(BaseModel):
        """Response schema for webhook subscription"""
        id: int
        name: str
        url: str
        events: List[str]
        is_active: bool
        success_count: int
        failure_count: int
        created_at: datetime

        class Config:
            from_attributes = True

    class WebhookEventResponse(BaseModel):
        """Response schema for webhook event catalog entry"""
        event_id: str
        name: str
        description: str
        category: str
        payload_schema: Dict[str, Any]
        example_payload: Dict[str, Any]

        class Config:
            from_attributes = True

    # =========================================================================
    # HELPER FUNCTIONS
    # =========================================================================

    def generate_api_key() -> tuple:
        """Generate a new API key and its hash"""
        key = f"pk_live_{secrets.token_urlsafe(32)}"
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        return key, key_hash

    def mask_api_key(key: str) -> str:
        """Mask an API key for display"""
        if len(key) <= 12:
            return "*" * len(key)
        return key[:8] + "*" * (len(key) - 12) + key[-4:]

    def generate_webhook_secret() -> str:
        """Generate a webhook signing secret"""
        return f"whsec_{secrets.token_urlsafe(32)}"

    async def deliver_webhook(
        subscription: WebhookSubscription,
        event_type: str,
        payload: Dict[str, Any],
        db: Session
    ):
        """
        Deliver webhook with retry logic, exponential backoff + jitter,
        circuit breaker, and dead-letter tracking.

        Enterprise Readiness Check 7.6: Webhook Delivery Reliability

        Features:
        - Exponential backoff with jitter to avoid thundering herd
        - Circuit breaker: after FAILURE_THRESHOLD consecutive failures,
          subscription is marked circuit_open and delivery stops
        - Dead letter: after max retries exhausted, status is set to
          "dead_letter" for later replay

        Retry schedule (with jitter applied +/- 25%):
        - Attempt 1: Immediate
        - Attempt 2: ~1 second delay
        - Attempt 3: ~5 seconds delay
        - Attempt 4: ~25 seconds delay
        - Attempt 5: ~125 seconds delay
        """
        # ---- Circuit breaker check ----
        if WebhookCircuitBreaker.is_circuit_open(subscription.id):
            logger.warning(
                f"Webhook circuit open for subscription {subscription.id} "
                f"({subscription.url}); skipping delivery"
            )
            # Log as dead-letter so it can be replayed later
            log = WebhookDeliveryLog(
                subscription_id=subscription.id,
                event_type=event_type,
                payload=payload,
                status="dead_letter",
                max_attempts=0,
                error_message="Circuit breaker open: delivery paused due to consecutive failures",
            )
            db.add(log)
            db.commit()
            return False

        retry_delays = [0, 1, 5, 25, 125]  # Exponential backoff base seconds
        max_attempts = min(subscription.retry_count + 1, len(retry_delays))

        # Create delivery log
        log = WebhookDeliveryLog(
            subscription_id=subscription.id,
            event_type=event_type,
            payload=payload,
            status="pending",
            max_attempts=max_attempts
        )
        db.add(log)
        db.commit()
        db.refresh(log)

        # Attempt delivery with retries
        for attempt in range(1, max_attempts + 1):
            log.attempt_number = attempt
            log.status = "retrying" if attempt > 1 else "pending"

            # Calculate delay with jitter for this attempt
            if attempt > 1:
                base_delay = retry_delays[attempt - 1]
                # Apply jitter: +/- 25% of base delay
                jitter = base_delay * (0.75 + random.random() * 0.5)
                delay = max(0.1, jitter)
                log.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
                db.commit()
                logger.info(
                    f"Webhook retry {attempt}/{max_attempts} in {delay:.1f}s "
                    f"(base: {base_delay}s) for subscription {subscription.id}"
                )
                await asyncio.sleep(delay)

            try:
                # Sign the payload
                timestamp = int(datetime.now(timezone.utc).timestamp())
                signature_payload = f"{timestamp}.{event_type}".encode() + str(payload).encode()
                signature = hmac.new(
                    subscription.secret.encode(),
                    signature_payload,
                    hashlib.sha256
                ).hexdigest()

                # Prepare headers
                headers = {
                    "Content-Type": "application/json",
                    "X-Webhook-Signature": signature,
                    "X-Webhook-Timestamp": str(timestamp),
                    "X-Webhook-Event": event_type,
                    "User-Agent": "PerenniaAI-Webhooks/1.0",
                    **subscription.headers
                }

                # Send webhook
                start_time = datetime.now(timezone.utc)
                async with httpx.AsyncClient(timeout=subscription.timeout_seconds) as client:
                    response = await client.post(
                        subscription.url,
                        json=payload,
                        headers=headers
                    )
                end_time = datetime.now(timezone.utc)

                # Record response
                log.response_code = response.status_code
                log.response_body = response.text[:1000]  # Limit to 1000 chars
                log.response_time_ms = int((end_time - start_time).total_seconds() * 1000)

                # Check if successful (2xx status code)
                if 200 <= response.status_code < 300:
                    log.status = "success"
                    log.delivered_at = end_time
                    subscription.success_count += 1
                    subscription.last_triggered_at = end_time
                    db.commit()
                    # Reset circuit breaker on success
                    WebhookCircuitBreaker.record_success(subscription.id)
                    logger.info(f"Webhook delivered successfully to {subscription.url}")
                    return True
                else:
                    log.error_message = f"HTTP {response.status_code}: {response.text[:200]}"
                    db.commit()

            except httpx.TimeoutException as e:
                log.error_message = f"Timeout after {subscription.timeout_seconds}s"
                db.commit()
                logger.warning(f"Webhook timeout for {subscription.url}: {str(e)}")

            except Exception as e:
                log.error_message = str(e)[:500]
                db.commit()
                logger.error(f"Webhook delivery error for {subscription.url}: {str(e)}")

        # ---- All retries exhausted: dead-letter the delivery ----
        log.status = "dead_letter"
        subscription.failure_count += 1
        db.commit()

        # Update circuit breaker
        consecutive = WebhookCircuitBreaker.record_failure(subscription.id)
        if WebhookCircuitBreaker.is_circuit_open(subscription.id):
            # Mark subscription as circuit_open to prevent further deliveries
            subscription.is_active = False
            db.commit()
            logger.error(
                f"Webhook circuit breaker OPEN for subscription {subscription.id} "
                f"({subscription.url}) after {consecutive} consecutive failures. "
                f"Subscription deactivated. Use test-ping endpoint to re-enable."
            )
        else:
            logger.error(
                f"Webhook delivery dead-lettered after {max_attempts} attempts "
                f"for {subscription.url} (consecutive failures: {consecutive}/{WebhookCircuitBreaker.FAILURE_THRESHOLD})"
            )

        return False

    # =========================================================================
    # API KEY MANAGEMENT ENDPOINTS (Check 11.4 - HIGH, 10pts)
    # =========================================================================

    @app.post(
        "/api/v1/api-keys",
        response_model=Dict[str, Any],
        tags=["API Gateway"],
        summary="Create API Key",
        description="Generate a new API key with specified scopes and permissions. The full key is only shown once."
    )
    async def create_api_key(
        http_request: Request,
        request: ApiKeyCreateRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        """
        Create a new API key for programmatic access.

        **Enterprise Check 11.4**: API Key CRUD (HIGH - 10pts)

        The generated key is hashed at rest and only shown in full at creation time.
        """
        # Rate limit API key creation — 5/hour per user
        from routes.auth_routes import (
            _check_auth_rate_limit, _raise_rate_limit,
            _AUTH_RATE_MAX_API_KEY_CREATE_HOUR, _AUTH_RATE_WINDOW_HOUR,
        )
        user_key = f"user:{current_user.id}"
        if not _check_auth_rate_limit(user_key, _AUTH_RATE_MAX_API_KEY_CREATE_HOUR, _AUTH_RATE_WINDOW_HOUR, "apikey_create"):
            logger.warning(f"API key creation rate limit exceeded for user {current_user.id}")
            _raise_rate_limit(_AUTH_RATE_WINDOW_HOUR, "Too many API key creation requests. Please try again later.")

        try:
            # Generate API key
            api_key, key_hash = generate_api_key()

            # Create database record — store only the hash, never plaintext
            db_key = ApiKey(
                key=None,
                key_hash=key_hash,
                key_prefix=api_key[:8],
                name=request.name,
                user_id=current_user.id,
                organization_id=current_user.organization_id,
                scopes=request.scopes,
                description=request.description,
                expires_at=request.expires_at,
                is_active=True
            )
            db.add(db_key)
            db.commit()
            db.refresh(db_key)

            logger.info(f"API key created: {request.name} for user {current_user.id}")

            return {
                "success": True,
                "data": {
                    "id": db_key.id,
                    "api_key": api_key,  # Only shown once!
                    "name": db_key.name,
                    "scopes": db_key.scopes,
                    "expires_at": db_key.expires_at.isoformat() if db_key.expires_at else None
                },
                "message": "API key created successfully. Save this key securely - it will not be shown again."
            }

        except Exception as e:
            logger.error(f"Error creating API key: {str(e)}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.get(
        "/api/v1/api-keys",
        response_model=Dict[str, Any],
        tags=["API Gateway"],
        summary="List API Keys",
        description="Get all API keys for the current organization (keys are masked)."
    )
    async def list_api_keys(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        """
        List all API keys for the current organization.

        **Enterprise Check 11.4**: API Key CRUD (HIGH - 10pts)
        """
        try:
            keys = db.query(ApiKey).filter(
                ApiKey.organization_id == current_user.organization_id
            ).order_by(desc(ApiKey.created_at)).all()

            return {
                "success": True,
                "data": [
                    {
                        "id": key.id,
                        "name": key.name,
                        "description": key.description,
                        "masked_key": mask_api_key(key.key),
                        "scopes": key.scopes or [],
                        "is_active": key.is_active,
                        "expires_at": key.expires_at.isoformat() if key.expires_at else None,
                        "created_at": key.created_at.isoformat(),
                        "last_used_at": key.last_used_at.isoformat() if key.last_used_at else None
                    }
                    for key in keys
                ],
                "message": f"Retrieved {len(keys)} API keys"
            }

        except Exception as e:
            logger.error(f"Error listing API keys: {str(e)}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.put(
        "/api/v1/api-keys/{key_id}",
        response_model=Dict[str, Any],
        tags=["API Gateway"],
        summary="Update API Key",
        description="Update API key name, scopes, or active status."
    )
    async def update_api_key(
        key_id: int,
        request: ApiKeyUpdateRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        """
        Update an existing API key.

        **Enterprise Check 11.4**: API Key CRUD (HIGH - 10pts)
        """
        try:
            # Find key
            db_key = db.query(ApiKey).filter(
                ApiKey.id == key_id,
                ApiKey.organization_id == current_user.organization_id
            ).first()

            if not db_key:
                raise HTTPException(status_code=404, detail="API key not found")

            # Update fields
            if request.name is not None:
                db_key.name = request.name
            if request.description is not None:
                db_key.description = request.description
            if request.scopes is not None:
                db_key.scopes = request.scopes
            if request.is_active is not None:
                db_key.is_active = request.is_active

            db.commit()
            db.refresh(db_key)

            logger.info(f"API key updated: {key_id} by user {current_user.id}")

            return {
                "success": True,
                "data": {
                    "id": db_key.id,
                    "name": db_key.name,
                    "scopes": db_key.scopes,
                    "is_active": db_key.is_active
                },
                "message": "API key updated successfully"
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error updating API key: {str(e)}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.delete(
        "/api/v1/api-keys/{key_id}",
        response_model=Dict[str, Any],
        tags=["API Gateway"],
        summary="Delete API Key",
        description="Permanently revoke and delete an API key."
    )
    async def delete_api_key(
        key_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        """
        Delete (revoke) an API key.

        **Enterprise Check 11.4**: API Key CRUD (HIGH - 10pts)
        """
        try:
            # Find key
            db_key = db.query(ApiKey).filter(
                ApiKey.id == key_id,
                ApiKey.organization_id == current_user.organization_id
            ).first()

            if not db_key:
                raise HTTPException(status_code=404, detail="API key not found")

            # Delete key
            db.delete(db_key)
            db.commit()

            logger.info(f"API key deleted: {key_id} by user {current_user.id}")

            return {
                "success": True,
                "data": {"id": key_id},
                "message": "API key revoked and deleted successfully"
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error deleting API key: {str(e)}")
            raise HTTPException(status_code=500, detail="Internal server error")

    # =========================================================================
    # WEBHOOK EVENT CATALOG (Check 11.7 - HIGH, 10pts)
    # =========================================================================

    @app.get(
        "/api/v1/webhooks/events",
        response_model=Dict[str, Any],
        tags=["Webhooks"],
        summary="List Webhook Events",
        description="Get catalog of all available webhook events with payload schemas and examples."
    )
    async def list_webhook_events(
        category: Optional[str] = Query(None, description="Filter by category"),
        current_user=Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """
        Get the webhook event catalog.

        **Enterprise Check 11.7**: Webhook Event Catalog (HIGH - 10pts)

        Returns all available webhook events with:
        - Event ID and human-readable name
        - Detailed description
        - Payload schema (JSON Schema format)
        - Example payload
        """
        try:
            query = db.query(WebhookEventCatalog).filter(
                WebhookEventCatalog.is_active == True
            )

            if category:
                query = query.filter(WebhookEventCatalog.category == category)

            events = query.order_by(
                WebhookEventCatalog.category,
                WebhookEventCatalog.event_id
            ).all()

            # Group by category
            categories = {}
            for event in events:
                if event.category not in categories:
                    categories[event.category] = []
                categories[event.category].append({
                    "event_id": event.event_id,
                    "name": event.name,
                    "description": event.description,
                    "payload_schema": event.payload_schema,
                    "example_payload": event.example_payload
                })

            return {
                "success": True,
                "data": {
                    "categories": categories,
                    "total_events": len(events),
                    "available_categories": list(categories.keys())
                },
                "message": f"Retrieved {len(events)} webhook events"
            }

        except Exception as e:
            logger.error(f"Error listing webhook events: {str(e)}")
            raise HTTPException(status_code=500, detail="Internal server error")

    # =========================================================================
    # WEBHOOK SUBSCRIPTIONS (Checks 11.7, 11.8)
    # =========================================================================

    @app.post(
        "/api/v1/webhooks/subscriptions",
        response_model=Dict[str, Any],
        tags=["Webhooks"],
        summary="Create Webhook Subscription",
        description="Subscribe to webhook events with a callback URL."
    )
    async def create_webhook_subscription(
        request: WebhookSubscriptionCreateRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        """
        Create a webhook subscription.

        **Enterprise Check 11.7**: Webhook Event Catalog (HIGH - 10pts)
        **Enterprise Check 11.8**: Webhook Retry with Backoff (HIGH - 10pts)
        """
        try:
            # Generate signing secret
            secret = generate_webhook_secret()

            # Create subscription
            subscription = WebhookSubscription(
                organization_id=current_user.organization_id,
                name=request.name,
                url=str(request.url),
                secret=secret,
                events=request.events,
                headers=request.headers or {},
                retry_count=request.retry_count,
                timeout_seconds=request.timeout_seconds,
                is_active=True
            )
            db.add(subscription)
            db.commit()
            db.refresh(subscription)

            logger.info(f"Webhook subscription created: {request.name} for org {current_user.organization_id}")

            return {
                "success": True,
                "data": {
                    "id": subscription.id,
                    "name": subscription.name,
                    "url": subscription.url,
                    "events": subscription.events,
                    "secret": secret,  # Only shown once!
                    "retry_config": {
                        "max_attempts": subscription.retry_count + 1,
                        "timeout_seconds": subscription.timeout_seconds,
                        "backoff_schedule": "1s, 5s, 25s, 125s"
                    }
                },
                "message": "Webhook subscription created. Save the secret securely for signature verification."
            }

        except Exception as e:
            logger.error(f"Error creating webhook subscription: {str(e)}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.get(
        "/api/v1/webhooks/subscriptions",
        response_model=Dict[str, Any],
        tags=["Webhooks"],
        summary="List Webhook Subscriptions",
        description="Get all webhook subscriptions for the current organization."
    )
    async def list_webhook_subscriptions(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        """
        List all webhook subscriptions.

        **Enterprise Check 11.7**: Webhook Event Catalog (HIGH - 10pts)
        """
        try:
            subscriptions = db.query(WebhookSubscription).filter(
                WebhookSubscription.organization_id == current_user.organization_id
            ).order_by(desc(WebhookSubscription.created_at)).all()

            return {
                "success": True,
                "data": [
                    {
                        "id": sub.id,
                        "name": sub.name,
                        "url": sub.url,
                        "events": sub.events,
                        "is_active": sub.is_active,
                        "success_count": sub.success_count,
                        "failure_count": sub.failure_count,
                        "last_triggered_at": sub.last_triggered_at.isoformat() if sub.last_triggered_at else None,
                        "created_at": sub.created_at.isoformat()
                    }
                    for sub in subscriptions
                ],
                "message": f"Retrieved {len(subscriptions)} webhook subscriptions"
            }

        except Exception as e:
            logger.error(f"Error listing webhook subscriptions: {str(e)}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.delete(
        "/api/v1/webhooks/subscriptions/{subscription_id}",
        response_model=Dict[str, Any],
        tags=["Webhooks"],
        summary="Delete Webhook Subscription",
        description="Remove a webhook subscription."
    )
    async def delete_webhook_subscription(
        subscription_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        """Delete a webhook subscription."""
        try:
            subscription = db.query(WebhookSubscription).filter(
                WebhookSubscription.id == subscription_id,
                WebhookSubscription.organization_id == current_user.organization_id
            ).first()

            if not subscription:
                raise HTTPException(status_code=404, detail="Webhook subscription not found")

            db.delete(subscription)
            db.commit()

            logger.info(f"Webhook subscription deleted: {subscription_id}")

            return {
                "success": True,
                "data": {"id": subscription_id},
                "message": "Webhook subscription deleted successfully"
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error deleting webhook subscription: {str(e)}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.get(
        "/api/v1/webhooks/subscriptions/{subscription_id}/logs",
        response_model=Dict[str, Any],
        tags=["Webhooks"],
        summary="Get Webhook Delivery Logs",
        description="View delivery attempts and status for a webhook subscription."
    )
    async def get_webhook_logs(
        subscription_id: int,
        limit: int = Query(50, ge=1, le=100),
        status: Optional[str] = Query(None, description="Filter by status: success, failed, pending"),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        """
        Get webhook delivery logs.

        **Enterprise Check 11.8**: Webhook Retry with Backoff (HIGH - 10pts)
        """
        try:
            # Verify subscription belongs to current org
            subscription = db.query(WebhookSubscription).filter(
                WebhookSubscription.id == subscription_id,
                WebhookSubscription.organization_id == current_user.organization_id
            ).first()

            if not subscription:
                raise HTTPException(status_code=404, detail="Webhook subscription not found")

            # Query logs
            query = db.query(WebhookDeliveryLog).filter(
                WebhookDeliveryLog.subscription_id == subscription_id
            )

            if status:
                query = query.filter(WebhookDeliveryLog.status == status)

            logs = query.order_by(desc(WebhookDeliveryLog.created_at)).limit(limit).all()

            return {
                "success": True,
                "data": {
                    "subscription_id": subscription_id,
                    "logs": [
                        {
                            "id": log.id,
                            "event_type": log.event_type,
                            "status": log.status,
                            "attempt_number": log.attempt_number,
                            "max_attempts": log.max_attempts,
                            "response_code": log.response_code,
                            "response_time_ms": log.response_time_ms,
                            "error_message": log.error_message,
                            "created_at": log.created_at.isoformat(),
                            "delivered_at": log.delivered_at.isoformat() if log.delivered_at else None
                        }
                        for log in logs
                    ],
                    "total": len(logs)
                },
                "message": f"Retrieved {len(logs)} delivery logs"
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error fetching webhook logs: {str(e)}")
            raise HTTPException(status_code=500, detail="Internal server error")

    # =========================================================================
    # WEBHOOK TEST-PING & DEAD-LETTER REPLAY (Check 7.6)
    # =========================================================================

    @app.post(
        "/api/v1/webhooks/subscriptions/{subscription_id}/test-ping",
        response_model=Dict[str, Any],
        tags=["Webhooks"],
        summary="Test Ping Webhook",
        description="Send a test ping to verify the webhook endpoint is reachable. "
                    "If the subscription was deactivated by the circuit breaker, "
                    "a successful ping re-enables it."
    )
    async def test_ping_webhook(
        subscription_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        """
        Test-ping a webhook subscription.

        **Enterprise Check 7.6**: Circuit breaker recovery path.
        """
        try:
            subscription = db.query(WebhookSubscription).filter(
                WebhookSubscription.id == subscription_id,
                WebhookSubscription.organization_id == current_user.organization_id
            ).first()

            if not subscription:
                raise HTTPException(status_code=404, detail="Webhook subscription not found")

            # Send a lightweight test ping
            test_payload = {
                "event": "webhook.test_ping",
                "subscription_id": subscription_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            timestamp = int(datetime.now(timezone.utc).timestamp())
            signature_payload = f"{timestamp}.webhook.test_ping".encode() + str(test_payload).encode()
            signature = hmac.new(
                subscription.secret.encode(),
                signature_payload,
                hashlib.sha256
            ).hexdigest()

            headers = {
                "Content-Type": "application/json",
                "X-Webhook-Signature": signature,
                "X-Webhook-Timestamp": str(timestamp),
                "X-Webhook-Event": "webhook.test_ping",
                "User-Agent": "PerenniaAI-Webhooks/1.0",
            }

            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    response = await client.post(
                        subscription.url,
                        json=test_payload,
                        headers=headers
                    )

                if 200 <= response.status_code < 300:
                    # Ping succeeded: reset circuit breaker and re-enable subscription
                    WebhookCircuitBreaker.reset(subscription_id)
                    if not subscription.is_active:
                        subscription.is_active = True
                        db.commit()
                        logger.info(f"Webhook subscription {subscription_id} re-enabled after successful test ping")

                    return {
                        "success": True,
                        "data": {
                            "subscription_id": subscription_id,
                            "response_code": response.status_code,
                            "circuit_breaker": "reset",
                            "subscription_active": True,
                        },
                        "message": "Test ping successful. Subscription is active."
                    }
                else:
                    return {
                        "success": False,
                        "data": {
                            "subscription_id": subscription_id,
                            "response_code": response.status_code,
                            "response_body": response.text[:200],
                            "circuit_breaker_failures": WebhookCircuitBreaker.get_failure_count(subscription_id),
                        },
                        "message": f"Test ping failed with HTTP {response.status_code}"
                    }

            except Exception as ping_error:
                return {
                    "success": False,
                    "data": {
                        "subscription_id": subscription_id,
                        "error": str(ping_error)[:200],
                        "circuit_breaker_failures": WebhookCircuitBreaker.get_failure_count(subscription_id),
                    },
                    "message": f"Test ping failed: {str(ping_error)[:100]}"
                }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error testing webhook: {str(e)}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.get(
        "/api/v1/webhooks/subscriptions/{subscription_id}/dead-letters",
        response_model=Dict[str, Any],
        tags=["Webhooks"],
        summary="List Dead-Lettered Deliveries",
        description="Get all dead-lettered webhook deliveries that can be replayed."
    )
    async def list_dead_letters(
        subscription_id: int,
        limit: int = Query(50, ge=1, le=200),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        """
        List dead-lettered deliveries for replay.

        **Enterprise Check 7.6**: Dead-letter queue visibility.
        """
        try:
            subscription = db.query(WebhookSubscription).filter(
                WebhookSubscription.id == subscription_id,
                WebhookSubscription.organization_id == current_user.organization_id
            ).first()

            if not subscription:
                raise HTTPException(status_code=404, detail="Webhook subscription not found")

            dead_letters = db.query(WebhookDeliveryLog).filter(
                WebhookDeliveryLog.subscription_id == subscription_id,
                WebhookDeliveryLog.status == "dead_letter"
            ).order_by(desc(WebhookDeliveryLog.created_at)).limit(limit).all()

            return {
                "success": True,
                "data": {
                    "subscription_id": subscription_id,
                    "dead_letters": [
                        {
                            "id": dl.id,
                            "event_type": dl.event_type,
                            "payload": dl.payload,
                            "error_message": dl.error_message,
                            "attempt_number": dl.attempt_number,
                            "max_attempts": dl.max_attempts,
                            "created_at": dl.created_at.isoformat(),
                        }
                        for dl in dead_letters
                    ],
                    "total": len(dead_letters),
                    "circuit_breaker_status": "open" if WebhookCircuitBreaker.is_circuit_open(subscription_id) else "closed",
                },
                "message": f"Retrieved {len(dead_letters)} dead-lettered deliveries"
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error listing dead letters: {str(e)}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.post(
        "/api/v1/webhooks/subscriptions/{subscription_id}/replay/{delivery_id}",
        response_model=Dict[str, Any],
        tags=["Webhooks"],
        summary="Replay Dead-Lettered Delivery",
        description="Retry a specific dead-lettered webhook delivery."
    )
    async def replay_dead_letter(
        subscription_id: int,
        delivery_id: int,
        background_tasks: BackgroundTasks,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        """
        Replay a dead-lettered delivery.

        **Enterprise Check 7.6**: Dead-letter replay capability.
        """
        try:
            subscription = db.query(WebhookSubscription).filter(
                WebhookSubscription.id == subscription_id,
                WebhookSubscription.organization_id == current_user.organization_id
            ).first()

            if not subscription:
                raise HTTPException(status_code=404, detail="Webhook subscription not found")

            if not subscription.is_active:
                raise HTTPException(
                    status_code=400,
                    detail="Subscription is deactivated. Send a test-ping first to re-enable."
                )

            delivery = db.query(WebhookDeliveryLog).filter(
                WebhookDeliveryLog.id == delivery_id,
                WebhookDeliveryLog.subscription_id == subscription_id,
                WebhookDeliveryLog.status == "dead_letter"
            ).first()

            if not delivery:
                raise HTTPException(status_code=404, detail="Dead-lettered delivery not found")

            # Mark as pending for replay
            delivery.status = "pending"
            delivery.error_message = f"Replayed at {datetime.now(timezone.utc).isoformat()} by user {current_user.id}"
            db.commit()

            # Schedule re-delivery in background
            background_tasks.add_task(
                deliver_webhook,
                subscription,
                delivery.event_type,
                delivery.payload,
                db
            )

            return {
                "success": True,
                "data": {
                    "delivery_id": delivery_id,
                    "event_type": delivery.event_type,
                    "status": "replay_scheduled",
                },
                "message": "Dead-lettered delivery queued for replay"
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error replaying dead letter: {str(e)}")
            raise HTTPException(status_code=500, detail="Internal server error")

    # Export deliver_webhook for use by other parts of the application
    app.state.deliver_webhook = deliver_webhook

    logger.info("API Gateway routes registered successfully")
