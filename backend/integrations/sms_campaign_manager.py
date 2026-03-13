"""SMS Campaign Manager - Mortgage CRM A+ Module #7
Batch SMS campaigns with audience segmentation, scheduling,
rate limiting, compliance checks, and delivery reporting.
"""
import asyncio
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class CampaignStatus(str, Enum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class CampaignType(str, Enum):
    BROADCAST = "broadcast"       # One-time blast to a list
    DRIP = "drip"                  # Sequential multi-message sequence
    TRIGGER = "trigger"            # Event-triggered (rate change, birthday, etc.)
    NURTURE = "nurture"            # Long-term relationship sequence


class SMSCampaign:
    """Represents a single SMS campaign configuration."""

    def __init__(
        self,
        campaign_id: str,
        name: str,
        campaign_type: CampaignType,
        template_key: str,
        audience: List[Dict[str, Any]],
        scheduled_at: Optional[datetime] = None,
        batch_size: int = 50,
        batch_delay_seconds: int = 60,
        variables: Optional[Dict[str, Any]] = None,
        tenant_id: Optional[str] = None,
    ):
        self.campaign_id = campaign_id
        self.name = name
        self.campaign_type = campaign_type
        self.template_key = template_key
        self.audience = audience
        self.scheduled_at = scheduled_at or datetime.utcnow()
        self.batch_size = batch_size
        self.batch_delay_seconds = batch_delay_seconds
        self.variables = variables or {}
        self.tenant_id = tenant_id
        self.status = CampaignStatus.DRAFT
        self.stats = {
            "total": len(audience),
            "sent": 0,
            "delivered": 0,
            "failed": 0,
            "opted_out": 0,
            "compliance_blocked": 0,
        }
        self.created_at = datetime.utcnow()
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.errors: List[str] = []


class SMSCampaignManager:
    """Manage and execute SMS campaigns with compliance and rate limiting."""

    def __init__(
        self,
        sms_service=None,
        compliance_gate=None,
        rate_limiter=None,
        template_engine=None,
        db=None,
    ):
        self.sms_service = sms_service
        self.compliance_gate = compliance_gate
        self.rate_limiter = rate_limiter
        self.template_engine = template_engine
        self.db = db
        self._active_campaigns: Dict[str, SMSCampaign] = {}

    # ── Campaign lifecycle ───────────────────────────────────────────────────
    def create_campaign(self, config: Dict[str, Any]) -> SMSCampaign:
        """Create a new campaign from config dict."""
        import uuid
        campaign = SMSCampaign(
            campaign_id=config.get("campaign_id", str(uuid.uuid4())),
            name=config["name"],
            campaign_type=CampaignType(config.get("type", "broadcast")),
            template_key=config["template_key"],
            audience=config["audience"],
            scheduled_at=config.get("scheduled_at"),
            batch_size=config.get("batch_size", 50),
            batch_delay_seconds=config.get("batch_delay_seconds", 60),
            variables=config.get("variables", {}),
            tenant_id=config.get("tenant_id"),
        )
        self._active_campaigns[campaign.campaign_id] = campaign
        logger.info(f"Campaign created: {campaign.campaign_id} ({campaign.name})")
        return campaign

    async def launch_campaign(self, campaign_id: str) -> Dict[str, Any]:
        """Launch a campaign - process all recipients in batches."""
        campaign = self._active_campaigns.get(campaign_id)
        if not campaign:
            raise ValueError(f"Campaign {campaign_id} not found")
        if campaign.status not in (CampaignStatus.DRAFT, CampaignStatus.SCHEDULED):
            raise ValueError(f"Campaign is in {campaign.status} state, cannot launch")

        campaign.status = CampaignStatus.RUNNING
        campaign.started_at = datetime.utcnow()
        logger.info(f"Launching campaign {campaign_id} to {len(campaign.audience)} recipients")

        try:
            batches = [
                campaign.audience[i:i + campaign.batch_size]
                for i in range(0, len(campaign.audience), campaign.batch_size)
            ]

            for batch_num, batch in enumerate(batches):
                if campaign.status == CampaignStatus.CANCELLED:
                    logger.info(f"Campaign {campaign_id} cancelled at batch {batch_num}")
                    break

                await self._process_batch(campaign, batch, batch_num)

                # Delay between batches to respect rate limits
                if batch_num < len(batches) - 1:
                    await asyncio.sleep(campaign.batch_delay_seconds)

            campaign.status = CampaignStatus.COMPLETED
            campaign.completed_at = datetime.utcnow()
            logger.info(f"Campaign {campaign_id} completed. Stats: {campaign.stats}")

        except Exception as e:
            campaign.status = CampaignStatus.FAILED
            campaign.errors.append(str(e))
            logger.error(f"Campaign {campaign_id} failed: {e}")

        return self.get_campaign_stats(campaign_id)

    async def _process_batch(
        self, campaign: SMSCampaign, batch: List[Dict], batch_num: int
    ) -> None:
        """Process a single batch of recipients."""
        logger.info(
            f"Processing batch {batch_num + 1} ({len(batch)} recipients) "
            f"for campaign {campaign.campaign_id}"
        )

        tasks = [self._send_to_recipient(campaign, recipient) for recipient in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                campaign.stats["failed"] += 1
                campaign.errors.append(str(result))

    async def _send_to_recipient(
        self, campaign: SMSCampaign, recipient: Dict[str, Any]
    ) -> None:
        """Send campaign message to a single recipient."""
        phone = recipient.get("phone") or recipient.get("to")
        if not phone:
            campaign.stats["failed"] += 1
            return

        # Compliance check
        if self.compliance_gate:
            try:
                check = await self.compliance_gate.check(
                    to=phone,
                    tenant_id=campaign.tenant_id,
                    category=campaign.campaign_type.value,
                )
                if not check.get("allowed", True):
                    campaign.stats["compliance_blocked"] += 1
                    logger.debug(f"Compliance blocked: {phone} - {check.get('reason')}")
                    return
            except Exception as e:
                logger.warning(f"Compliance check error for {phone}: {e}")

        # Render message with recipient-specific variables
        merged_vars = {**campaign.variables, **recipient}
        try:
            if self.template_engine:
                body = self.template_engine.render(campaign.template_key, merged_vars)
            else:
                body = merged_vars.get("message", "")
        except Exception as e:
            campaign.stats["failed"] += 1
            logger.error(f"Template render error for {phone}: {e}")
            return

        # Send via SMS service
        if self.sms_service:
            try:
                result = await self.sms_service.send_sms(
                    to=phone,
                    body=body,
                    tenant_id=campaign.tenant_id,
                )
                if result.get("success"):
                    campaign.stats["sent"] += 1
                else:
                    campaign.stats["failed"] += 1
            except Exception as e:
                campaign.stats["failed"] += 1
                logger.error(f"SMS send error for {phone}: {e}")
        else:
            # Dry-run mode
            campaign.stats["sent"] += 1
            logger.debug(f"[DRY RUN] Would send to {phone}: {body[:50]}...")

    # ── Campaign management ──────────────────────────────────────────────────
    def pause_campaign(self, campaign_id: str) -> bool:
        campaign = self._active_campaigns.get(campaign_id)
        if campaign and campaign.status == CampaignStatus.RUNNING:
            campaign.status = CampaignStatus.PAUSED
            return True
        return False

    def cancel_campaign(self, campaign_id: str) -> bool:
        campaign = self._active_campaigns.get(campaign_id)
        if campaign and campaign.status in (CampaignStatus.RUNNING, CampaignStatus.PAUSED):
            campaign.status = CampaignStatus.CANCELLED
            return True
        return False

    def get_campaign_stats(self, campaign_id: str) -> Dict[str, Any]:
        campaign = self._active_campaigns.get(campaign_id)
        if not campaign:
            return {"error": "Campaign not found"}
        return {
            "campaign_id": campaign.campaign_id,
            "name": campaign.name,
            "status": campaign.status.value,
            "stats": campaign.stats,
            "started_at": campaign.started_at.isoformat() if campaign.started_at else None,
            "completed_at": campaign.completed_at.isoformat() if campaign.completed_at else None,
            "error_count": len(campaign.errors),
        }

    def list_campaigns(self) -> List[Dict[str, Any]]:
        return [self.get_campaign_stats(cid) for cid in self._active_campaigns]


# ── Singleton ──────────────────────────────────────────────────────────────────
_manager: Optional[SMSCampaignManager] = None


def get_campaign_manager(**kwargs) -> SMSCampaignManager:
    global _manager
    if _manager is None:
        _manager = SMSCampaignManager(**kwargs)
    return _manager
