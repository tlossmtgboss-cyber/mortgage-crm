"""
Feature Tier Configuration for Perennia AI

Defines three tiers of feature modules:
- CORE: Always maintained, SLA'd. Critical path for the business.
- PREMIUM: Maintained when resources allow. Important but not critical.
- EXPERIMENTAL: Frozen, no SLA. Prototypes or low-usage features.

Usage:
    from feature_tiers import FeatureTier, get_tier, get_modules_by_tier, FEATURE_TIERS

    tier = get_tier("accounting")  # -> FeatureTier.CORE
    core_modules = get_modules_by_tier(FeatureTier.CORE)
"""

from enum import Enum
from typing import Dict, Set


class FeatureTier(str, Enum):
    CORE = "core"               # Always maintained, SLA'd
    PREMIUM = "premium"         # Maintained when resources allow
    EXPERIMENTAL = "experimental"  # Frozen, no SLA


# Module -> tier mapping
FEATURE_TIERS: Dict[str, FeatureTier] = {
    # CORE - always maintained, SLA'd
    # CRM foundation
    "leads": FeatureTier.CORE,
    "loans": FeatureTier.CORE,
    "pipeline": FeatureTier.CORE,
    "dashboard": FeatureTier.CORE,
    "tasks": FeatureTier.CORE,
    "calendar": FeatureTier.CORE,
    "smart_docs": FeatureTier.CORE,
    "compliance": FeatureTier.CORE,
    "workflow_sla": FeatureTier.CORE,
    # AI platform
    "ai_agents": FeatureTier.CORE,
    "ai_chat": FeatureTier.CORE,
    # Auth & infrastructure
    "auth": FeatureTier.CORE,
    "permissions": FeatureTier.CORE,
    "onboarding": FeatureTier.CORE,
    "notifications": FeatureTier.CORE,
    "portals": FeatureTier.CORE,
    # Subscription & billing (how users pay for the platform)
    "accounting": FeatureTier.CORE,
    # LO marketing tools (the product LOs pay for)
    "telephony": FeatureTier.CORE,
    "dialer": FeatureTier.CORE,
    "content_marketing": FeatureTier.CORE,
    "email_intelligence": FeatureTier.CORE,
    "video_clips": FeatureTier.CORE,
    "voicemail_drops": FeatureTier.CORE,
    "sms_intelligence": FeatureTier.CORE,
    "call_intelligence": FeatureTier.CORE,
    "referral_partners": FeatureTier.CORE,
    "rate_monitor": FeatureTier.CORE,
    # DEPRECATED: Premium feature deregistered — not yet launched
    # "recruiting": FeatureTier.CORE,
    # Promoted from PREMIUM to CORE - enterprise table stakes (March 2026)
    "salesforce_sync": FeatureTier.CORE,
    "encompass_sync": FeatureTier.CORE,

    # Scheduler modules
    "scheduler_analytics": FeatureTier.CORE,
    "scheduler_conflicts": FeatureTier.CORE,
    "scheduler_reschedule": FeatureTier.CORE,

    # PREMIUM - maintained when resources allow
    "microsite_builder": FeatureTier.PREMIUM,
    "video_meetings": FeatureTier.PREMIUM,
    "scheduler_surveys": FeatureTier.PREMIUM,
    "scheduler_waitlist": FeatureTier.PREMIUM,
    # Deleted modules (Mar 2026): scheduler_labels, scheduler_booking_meta, scheduler_sitemap

    # EXPERIMENTAL - frozen, no SLA, not exposed to production orgs
    # "avatar_studio": FeatureTier.EXPERIMENTAL,  # DEPRECATED: Experimental feature deregistered
    # "hr_management": FeatureTier.EXPERIMENTAL,  # DEPRECATED: Premium feature deregistered — not yet launched
    "it_helpdesk": FeatureTier.EXPERIMENTAL,
    # "decision_lab": FeatureTier.EXPERIMENTAL,  # DEPRECATED: Experimental feature deregistered
    # "circle_of_cashflow": FeatureTier.EXPERIMENTAL,  # DEPRECATED: Experimental feature deregistered
    # "scheduler_ab_testing": removed — feature deleted, not needed for mortgage CRM
}


def get_tier(module: str) -> FeatureTier:
    """Get the feature tier for a module.

    Returns CORE as the default for unknown modules, since untiered
    modules should be treated as maintained until explicitly classified.
    """
    return FEATURE_TIERS.get(module, FeatureTier.CORE)


def get_modules_by_tier(tier: FeatureTier) -> Set[str]:
    """Get all modules in a specific tier."""
    return {m for m, t in FEATURE_TIERS.items() if t == tier}
