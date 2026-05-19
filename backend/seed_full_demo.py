#!/usr/bin/env python3
"""
Full Demo Seed Script — Perennia AI (thin shim)
================================================
This module is preserved as a thin compatibility shim. The original 6,652-line
monolith was mechanically decomposed into the ``seed_full_demo/`` package with
per-fixture sub-modules (``_org``, ``_users``, ``_leads``, ``_loans``,
``_borrowers``, ``_partners``, ``_tasks``, ``_comms``, ``_workflows``,
``_misc``). All public symbols continue to resolve through this module so that
existing callers (``python3 seed_full_demo.py`` and ``import seed_full_demo``)
keep working without modification.

Usage:
    DATABASE_URL=<url> python3 seed_full_demo.py
"""

# Re-export the full public API from the package. Star-import keeps the shim
# automatically in sync with seed_full_demo/__init__.__all__.
from seed_full_demo import *  # noqa: F401,F403
from seed_full_demo import (  # noqa: F401  (explicit names for static analysers)
    main,
    seed_full_demo,
    seed_organization,
    seed_branch,
    seed_users,
    seed_impersonation_permissions,
    seed_leads,
    seed_loans,
    seed_mum_clients,
    seed_borrower_portal,
    seed_referral_partners,
    seed_tasks,
    seed_documents,
    seed_calendar,
    seed_sms_conversations,
    seed_call_intelligence,
    seed_activities_and_history,
    seed_rate_monitor,
    seed_workflows_and_compliance,
    seed_ai_metrics,
    seed_content_and_campaigns,
    seed_team_chat,
    seed_notifications,
    get_engine,
    ORG_NAME,
    ORG_SLUG,
    DEMO_EMAIL,
    DEMO_PASSWORD,
)


if __name__ == "__main__":
    main()
