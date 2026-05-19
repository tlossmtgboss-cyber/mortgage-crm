"""seed_full_demo package — decomposed from monolithic seed_full_demo.py.

Re-exports the full public API (orchestrator + every fixture loader) so existing
callers `from seed_full_demo import <name>` continue to work via the thin shim.
"""

from ._shared import (
    NOW,
    TODAY,
    ORG_NAME,
    ORG_SLUG,
    DEMO_EMAIL,
    DEMO_PASSWORD,
    pwd_context,
    days_ago,
    days_from_now,
    date_ago,
    date_from_now,
    get_engine,
    exists,
    get_id,
)
from ._org import seed_organization, seed_branch
from ._users import seed_users, seed_impersonation_permissions
from ._leads import seed_leads
from ._loans import seed_loans
from ._borrowers import seed_mum_clients, seed_borrower_portal
from ._partners import seed_referral_partners
from ._tasks import seed_tasks, seed_documents, seed_calendar
from ._comms import (
    seed_sms_conversations,
    seed_call_intelligence,
    seed_activities_and_history,
)
from ._workflows import seed_rate_monitor, seed_workflows_and_compliance
from ._misc import (
    seed_ai_metrics,
    seed_content_and_campaigns,
    seed_team_chat,
    seed_notifications,
)


def seed_full_demo():
    """Orchestrate every fixture loader in the original order."""
    print("\U0001f50c Connecting...")
    engine = get_engine()

    with engine.connect() as conn:
        print("\u2705 Connected")

        org_id = seed_organization(conn)
        branch_id = seed_branch(conn, org_id)
        user_ids = seed_users(conn, org_id, branch_id)
        seed_impersonation_permissions(conn, user_ids)
        lead_ids = seed_leads(conn, org_id, user_ids)
        loan_ids = seed_loans(conn, org_id, user_ids, lead_ids)
        mum_ids = seed_mum_clients(conn, org_id, user_ids)
        partner_ids = seed_referral_partners(conn, org_id, user_ids, lead_ids)
        seed_tasks(conn, org_id, user_ids, lead_ids, loan_ids)
        seed_documents(conn, org_id, user_ids, loan_ids)
        seed_calendar(conn, org_id, user_ids, lead_ids, loan_ids)
        seed_sms_conversations(conn, org_id, user_ids, lead_ids)
        seed_call_intelligence(conn, org_id, user_ids, lead_ids)
        seed_activities_and_history(conn, org_id, user_ids, lead_ids, loan_ids)
        seed_ai_metrics(conn, org_id)
        seed_rate_monitor(conn, org_id, mum_ids, loan_ids)
        seed_workflows_and_compliance(conn, org_id, user_ids, lead_ids, loan_ids)
        seed_borrower_portal(conn, org_id, lead_ids, loan_ids)
        seed_content_and_campaigns(conn, org_id, user_ids, lead_ids)
        seed_team_chat(conn, org_id, user_ids)
        seed_notifications(conn, org_id, user_ids)

    print("\n\U0001f389 Demo seed complete!")
    print(f"   Org  : {ORG_NAME} (slug: {ORG_SLUG})")
    print(f"   Login: {DEMO_EMAIL}")
    print(f"   Pass : {DEMO_PASSWORD}")


# Backwards-compat alias matching the original entry point.
main = seed_full_demo


__all__ = [
    "seed_full_demo",
    "main",
    "seed_organization",
    "seed_branch",
    "seed_users",
    "seed_impersonation_permissions",
    "seed_leads",
    "seed_loans",
    "seed_mum_clients",
    "seed_borrower_portal",
    "seed_referral_partners",
    "seed_tasks",
    "seed_documents",
    "seed_calendar",
    "seed_sms_conversations",
    "seed_call_intelligence",
    "seed_activities_and_history",
    "seed_rate_monitor",
    "seed_workflows_and_compliance",
    "seed_ai_metrics",
    "seed_content_and_campaigns",
    "seed_team_chat",
    "seed_notifications",
    "get_engine",
    "ORG_NAME",
    "ORG_SLUG",
    "DEMO_EMAIL",
    "DEMO_PASSWORD",
]
