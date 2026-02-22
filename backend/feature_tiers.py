"""
Feature Tier Configuration for Perennia AI

Defines three tiers of feature modules:
- CORE: Always maintained, SLA'd. Critical path for the business.
- PREMIUM: Maintained when resources allow. Important but not critical.
- EXPERIMENTAL: Frozen, no SLA. Prototypes or low-usage features.

Usage:
    from feature_tiers import FeatureTier, get_tier, get_modules_by_tier, FEATURE_TIERS

    tier = get_tier("accounting")  # -> FeatureTier.EXPERIMENTAL
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
    # CORE - always maintained
    "leads": FeatureTier.CORE,
    "loans": FeatureTier.CORE,
    "pipeline": FeatureTier.CORE,
    "dashboard": FeatureTier.CORE,
    "ai_agents": FeatureTier.CORE,
    "ai_chat": FeatureTier.CORE,
    "auth": FeatureTier.CORE,
    "salesforce_sync": FeatureTier.CORE,
    "encompass_sync": FeatureTier.CORE,
    "smart_docs": FeatureTier.CORE,
    "workflow_sla": FeatureTier.CORE,
    "portals": FeatureTier.CORE,
    "tasks": FeatureTier.CORE,
    "calendar": FeatureTier.CORE,
    "compliance": FeatureTier.CORE,
    "permissions": FeatureTier.CORE,
    "onboarding": FeatureTier.CORE,
    "notifications": FeatureTier.CORE,

    # PREMIUM - maintained when resources allow
    "telephony": FeatureTier.PREMIUM,
    "dialer": FeatureTier.PREMIUM,
    "content_marketing": FeatureTier.PREMIUM,
    "email_intelligence": FeatureTier.PREMIUM,
    "video_clips": FeatureTier.PREMIUM,
    "referral_partners": FeatureTier.PREMIUM,
    "sms_intelligence": FeatureTier.PREMIUM,
    "voicemail_drops": FeatureTier.PREMIUM,
    "call_intelligence": FeatureTier.PREMIUM,
    "recruiting": FeatureTier.PREMIUM,
    "rate_monitor": FeatureTier.PREMIUM,

    # EXPERIMENTAL - frozen, no SLA
    "accounting": FeatureTier.EXPERIMENTAL,
    "video_meetings": FeatureTier.EXPERIMENTAL,
    "avatar_studio": FeatureTier.EXPERIMENTAL,
    "microsite_builder": FeatureTier.EXPERIMENTAL,
    "decision_lab": FeatureTier.EXPERIMENTAL,
    "hr_management": FeatureTier.EXPERIMENTAL,
    "circle_of_cashflow": FeatureTier.EXPERIMENTAL,
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
