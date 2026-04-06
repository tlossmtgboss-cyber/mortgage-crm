"""
Marketing Agent Fleet — Domain 7

Coordinated marketing automation agents for loan officer operations:
- MarketingManagerAgent: Campaign orchestration and performance reporting
- ContentFactoryAgent: Blog, social, and email content generation
- ReferralNurtureAgent: Partner relationship management and co-branded content
- ReviewRequestAgent: Post-close review solicitation sequences
- SeminarHostAgent: AI-hosted educational webinar management
- ListingPartnerAgent: Realtor milestone notifications and co-branded updates
- BrandGuardAgent: Content compliance, fair lending, and NMLS enforcement
"""

from .marketing_manager_agent import MarketingManagerAgent
from .content_factory_agent import ContentFactoryAgent
from .referral_nurture_agent import ReferralNurtureAgent
from .review_request_agent import ReviewRequestAgent
from .seminar_host_agent import SeminarHostAgent
from .listing_partner_agent import ListingPartnerAgent
from .brand_guard_agent import BrandGuardAgent

__all__ = [
    "MarketingManagerAgent",
    "ContentFactoryAgent",
    "ReferralNurtureAgent",
    "ReviewRequestAgent",
    "SeminarHostAgent",
    "ListingPartnerAgent",
    "BrandGuardAgent",
]
