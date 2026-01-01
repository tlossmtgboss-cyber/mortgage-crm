"""
Migration: Seed Recruiting Workflow Data
Seeds default playbooks, cadences, and message templates for the recruiting CRM.

Run after: add_recruiting_workflow_crm.py
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
import json
import uuid

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/perennia")


def run_migration():
    engine = create_engine(DATABASE_URL)

    with engine.connect() as conn:
        # =============================================================================
        # SEED PLAYBOOKS
        # =============================================================================
        print("Seeding playbooks...")

        playbooks = [
            # Loan Officer Playbooks
            {
                "key": "LO_HIGH_INTENT_SURGE",
                "name": "LO High Intent Surge",
                "description": "Triggered when timing_score >= 70 or MEETING_INTENT signal. Rapid high-touch sequence.",
                "person_type": "LOAN_OFFICER",
                "trigger_config": {
                    "timing_score_min": 70,
                    "signal_types": ["MEETING_INTENT"],
                    "operator": "OR"
                },
                "actions": [
                    {"type": "SMS", "timing": "within_15_min", "template_key": "lo_hot_sms"},
                    {"type": "TASK", "title": "Call with 2 discovery angles: ops pain + comp clarity", "priority": "URGENT"},
                    {"type": "EMAIL", "template_key": "lo_switch_plan"},
                    {"type": "INTRO_REQUEST", "condition": "if_mutual_exists"}
                ],
                "priority": 90,
                "cooldown_days": 14
            },
            {
                "key": "LO_BRANCH_INSTABILITY",
                "name": "LO Branch Instability Response",
                "description": "Triggered when BRANCH_INSTABILITY or MANAGEMENT_CONFLICT signal detected.",
                "person_type": "LOAN_OFFICER",
                "trigger_config": {
                    "signal_types": ["BRANCH_INSTABILITY", "MANAGEMENT_CONFLICT"],
                    "operator": "OR"
                },
                "actions": [
                    {"type": "EMAIL", "template_key": "lo_confidential_options"},
                    {"type": "ASSET", "asset_key": "branch_transition_checklist"},
                    {"type": "TASK", "title": "Book 15-min 'what would have to be true?' call", "priority": "HIGH"}
                ],
                "priority": 85,
                "cooldown_days": 30
            },
            {
                "key": "LO_TECH_PAIN",
                "name": "LO Tech Pain Response",
                "description": "Triggered when TECH_PAIN signal detected. Offer tech demos.",
                "person_type": "LOAN_OFFICER",
                "trigger_config": {
                    "signal_types": ["TECH_PAIN"],
                    "operator": "OR"
                },
                "actions": [
                    {"type": "EMAIL", "template_key": "lo_tech_demo_offer"},
                    {"type": "ASSET", "asset_key": "tech_stack_comparison"},
                    {"type": "TASK", "title": "Schedule tech demo walkthrough", "priority": "MEDIUM"}
                ],
                "priority": 70,
                "cooldown_days": 45
            },
            {
                "key": "LO_OPS_PAIN",
                "name": "LO Ops Pain Response",
                "description": "Triggered when OPS_PAIN signal detected. Address processing concerns.",
                "person_type": "LOAN_OFFICER",
                "trigger_config": {
                    "signal_types": ["OPS_PAIN"],
                    "operator": "OR"
                },
                "actions": [
                    {"type": "EMAIL", "template_key": "lo_sla_metrics"},
                    {"type": "ASSET", "asset_key": "sla_dashboard"},
                    {"type": "TASK", "title": "Share processing SLAs and support model", "priority": "MEDIUM"}
                ],
                "priority": 70,
                "cooldown_days": 30
            },

            # Realtor Playbooks
            {
                "key": "REALTOR_LENDER_PAIN",
                "name": "Realtor Lender Dissatisfaction Response",
                "description": "Triggered when LENDER_DISSATISFACTION signal detected.",
                "person_type": "REALTOR",
                "trigger_config": {
                    "signal_types": ["LENDER_DISSATISFACTION"],
                    "operator": "OR"
                },
                "actions": [
                    {"type": "SMS", "timing": "immediate", "template_key": "realtor_empathy_sms"},
                    {"type": "TASK", "title": "Call within 2 hours - offer to run point on comms", "priority": "URGENT"},
                    {"type": "EMAIL", "template_key": "realtor_listing_update_engine"},
                    {"type": "INTRO_REQUEST", "condition": "if_mutual_exists"}
                ],
                "priority": 90,
                "cooldown_days": 14
            },
            {
                "key": "REALTOR_SPRING_SURGE",
                "name": "Realtor Spring Market Surge",
                "description": "Triggered during spring market (Mar-May) with TIME_WINDOW signal.",
                "person_type": "REALTOR",
                "trigger_config": {
                    "signal_types": ["SEASONAL_SURGE", "TIME_WINDOW"],
                    "operator": "OR"
                },
                "actions": [
                    {"type": "ASSET", "asset_key": "open_house_scripts"},
                    {"type": "EMAIL", "template_key": "realtor_fast_preapproval"},
                    {"type": "ASSET", "asset_key": "buyers_30_days_playbook"}
                ],
                "priority": 75,
                "cooldown_days": 60
            },
            {
                "key": "REALTOR_HIGH_INTENT",
                "name": "Realtor High Intent Response",
                "description": "Triggered when timing_score >= 70 for Realtors.",
                "person_type": "REALTOR",
                "trigger_config": {
                    "timing_score_min": 70,
                    "operator": "OR"
                },
                "actions": [
                    {"type": "SMS", "timing": "within_15_min", "template_key": "realtor_hot_sms"},
                    {"type": "TASK", "title": "Book partnership meeting - discuss co-marketing", "priority": "HIGH"},
                    {"type": "EMAIL", "template_key": "realtor_partnership_proposal"}
                ],
                "priority": 85,
                "cooldown_days": 21
            }
        ]

        for pb in playbooks:
            playbook_id = str(uuid.uuid4())
            conn.execute(text("""
                INSERT INTO rw_playbook (id, key, name, description, person_type, trigger_config, actions, priority, cooldown_days)
                VALUES (:id, :key, :name, :description, :person_type, :trigger_config, :actions, :priority, :cooldown_days)
                ON CONFLICT (key) DO UPDATE SET
                    name = EXCLUDED.name,
                    description = EXCLUDED.description,
                    trigger_config = EXCLUDED.trigger_config,
                    actions = EXCLUDED.actions,
                    priority = EXCLUDED.priority,
                    cooldown_days = EXCLUDED.cooldown_days
            """), {
                "id": playbook_id,
                "key": pb["key"],
                "name": pb["name"],
                "description": pb["description"],
                "person_type": pb["person_type"],
                "trigger_config": json.dumps(pb["trigger_config"]),
                "actions": json.dumps(pb["actions"]),
                "priority": pb["priority"],
                "cooldown_days": pb["cooldown_days"]
            })

        print(f"  Created/updated {len(playbooks)} playbooks")

        # =============================================================================
        # SEED CADENCES
        # =============================================================================
        print("Seeding cadences...")

        cadences = [
            # LO Cadences
            {
                "key": "LO_YEAR_0_1_CREDIBILITY",
                "name": "LO Year 0-1: Credibility Building",
                "description": "Initial credibility building cadence. Touch every 21-35 days with operational insights and social proof.",
                "person_type": "LOAN_OFFICER",
                "target_stages": ["DISCOVERED", "CONNECTED", "NURTURING"],
                "is_default": True,
                "steps": [
                    {"step_order": 1, "min_days": 0, "channel": "EMAIL", "template_key": "lo_welcome", "goal": "Introduction + quick value"},
                    {"step_order": 2, "min_days": 7, "channel": "SMS", "template_key": "lo_quick_win", "goal": "Quick win update"},
                    {"step_order": 3, "min_days": 14, "channel": "LINKEDIN", "template_key": "lo_linkedin_connect", "goal": "Social connection"},
                    {"step_order": 4, "min_days": 21, "channel": "EMAIL", "template_key": "lo_friction_removal", "goal": "One idea to remove friction"},
                    {"step_order": 5, "min_days": 28, "channel": "EMAIL", "template_key": "lo_market_insight", "goal": "Market insight share"},
                    {"step_order": 6, "min_days": 35, "channel": "SMS", "template_key": "lo_checkin", "goal": "Casual check-in"},
                    {"step_order": 7, "min_days": 49, "channel": "EMAIL", "template_key": "lo_case_study", "goal": "Success story share"},
                    {"step_order": 8, "min_days": 63, "channel": "EMAIL", "template_key": "lo_webinar_invite", "goal": "Micro-event invite"},
                    {"step_order": 9, "min_days": 77, "channel": "SMS", "template_key": "lo_rate_update", "goal": "Rate environment update"},
                    {"step_order": 10, "min_days": 90, "channel": "EMAIL", "template_key": "lo_branch_template", "goal": "Branch performance template offer"}
                ]
            },
            {
                "key": "LO_YEAR_1_2_DEPTH",
                "name": "LO Year 1-2: Relationship Depth",
                "description": "Deepen relationship with mutual intros and transparent SLAs. Touch every 30-45 days.",
                "person_type": "LOAN_OFFICER",
                "target_stages": ["NURTURING", "WARMING"],
                "is_default": False,
                "steps": [
                    {"step_order": 1, "min_days": 0, "channel": "EMAIL", "template_key": "lo_depth_intro", "goal": "Transition to deeper relationship"},
                    {"step_order": 2, "min_days": 14, "channel": "EMAIL", "template_key": "lo_deal_rescue", "goal": "Deal rescue story"},
                    {"step_order": 3, "min_days": 30, "channel": "PHONE", "template_key": "lo_check_call", "goal": "Personal check-in call"},
                    {"step_order": 4, "min_days": 45, "channel": "EMAIL", "template_key": "lo_sla_transparency", "goal": "SLA transparency share"},
                    {"step_order": 5, "min_days": 60, "channel": "EMAIL", "template_key": "lo_mutual_intro_offer", "goal": "Offer mutual intro"},
                    {"step_order": 6, "min_days": 75, "channel": "SMS", "template_key": "lo_industry_news", "goal": "Industry news reaction"},
                    {"step_order": 7, "min_days": 90, "channel": "EMAIL", "template_key": "lo_comp_insight", "goal": "Compensation market insight"}
                ]
            },
            {
                "key": "LO_YEAR_2_PLUS_TIMING",
                "name": "LO Year 2+: Timing Readiness",
                "description": "Long-term nurture with signal sensitivity. Touch every 45-60 days, surge on signals.",
                "person_type": "LOAN_OFFICER",
                "target_stages": ["WARMING", "ACTIVE_CONVERSATION", "EVALUATING_SWITCH"],
                "is_default": False,
                "steps": [
                    {"step_order": 1, "min_days": 0, "channel": "EMAIL", "template_key": "lo_staying_connected", "goal": "Stay top of mind"},
                    {"step_order": 2, "min_days": 30, "channel": "SMS", "template_key": "lo_quick_thought", "goal": "Quick thought share"},
                    {"step_order": 3, "min_days": 60, "channel": "EMAIL", "template_key": "lo_market_report", "goal": "Market report share"},
                    {"step_order": 4, "min_days": 90, "channel": "EMAIL", "template_key": "lo_annual_checkin", "goal": "Annual check-in"},
                    {"step_order": 5, "min_days": 120, "channel": "EMAIL", "template_key": "lo_new_opportunity", "goal": "New opportunity share"}
                ]
            },

            # Realtor Cadences
            {
                "key": "REALTOR_YEAR_0_1_TRUST",
                "name": "Realtor Year 0-1: Trust & Responsiveness",
                "description": "Build trust through responsiveness. Touch every 14-28 days with speed and certainty themes.",
                "person_type": "REALTOR",
                "target_stages": ["DISCOVERED", "CONNECTED", "NURTURING"],
                "is_default": True,
                "steps": [
                    {"step_order": 1, "min_days": 0, "channel": "EMAIL", "template_key": "realtor_welcome", "goal": "Introduction + speed promise"},
                    {"step_order": 2, "min_days": 5, "channel": "SMS", "template_key": "realtor_quick_intro", "goal": "Personal touch"},
                    {"step_order": 3, "min_days": 10, "channel": "EMAIL", "template_key": "realtor_preapproval_speed", "goal": "Pre-approval speed demo"},
                    {"step_order": 4, "min_days": 17, "channel": "SMS", "template_key": "realtor_availability", "goal": "Availability reminder"},
                    {"step_order": 5, "min_days": 24, "channel": "EMAIL", "template_key": "realtor_creative_strategies", "goal": "Creative financing strategies"},
                    {"step_order": 6, "min_days": 35, "channel": "EMAIL", "template_key": "realtor_closing_certainty", "goal": "Closing certainty examples"},
                    {"step_order": 7, "min_days": 49, "channel": "SMS", "template_key": "realtor_checkin", "goal": "Casual check-in"},
                    {"step_order": 8, "min_days": 63, "channel": "EMAIL", "template_key": "realtor_success_story", "goal": "Success story share"},
                    {"step_order": 9, "min_days": 77, "channel": "EMAIL", "template_key": "realtor_comarketing_teaser", "goal": "Co-marketing teaser"}
                ]
            },
            {
                "key": "REALTOR_YEAR_1_2_COMARKETING",
                "name": "Realtor Year 1-2: Co-Marketing",
                "description": "Partner on marketing initiatives. Touch every 21-35 days.",
                "person_type": "REALTOR",
                "target_stages": ["NURTURING", "WARMING"],
                "is_default": False,
                "steps": [
                    {"step_order": 1, "min_days": 0, "channel": "EMAIL", "template_key": "realtor_partnership_level_up", "goal": "Partnership deepening"},
                    {"step_order": 2, "min_days": 14, "channel": "EMAIL", "template_key": "realtor_cobranded_content", "goal": "Co-branded content offer"},
                    {"step_order": 3, "min_days": 28, "channel": "PHONE", "template_key": "realtor_strategy_call", "goal": "Strategy call"},
                    {"step_order": 4, "min_days": 42, "channel": "EMAIL", "template_key": "realtor_open_house_support", "goal": "Open house support offer"},
                    {"step_order": 5, "min_days": 56, "channel": "EMAIL", "template_key": "realtor_buyer_scripts", "goal": "Buyer scripts share"},
                    {"step_order": 6, "min_days": 70, "channel": "SMS", "template_key": "realtor_season_prep", "goal": "Seasonal prep reminder"}
                ]
            },
            {
                "key": "REALTOR_YEAR_2_PLUS_POCKET",
                "name": "Realtor Year 2+: Stay in Pocket",
                "description": "Maintain top-of-mind presence. Touch every 30-45 days.",
                "person_type": "REALTOR",
                "target_stages": ["WARMING", "ACTIVE_CONVERSATION"],
                "is_default": False,
                "steps": [
                    {"step_order": 1, "min_days": 0, "channel": "EMAIL", "template_key": "realtor_top_of_mind", "goal": "Stay connected"},
                    {"step_order": 2, "min_days": 21, "channel": "SMS", "template_key": "realtor_market_pulse", "goal": "Market pulse share"},
                    {"step_order": 3, "min_days": 45, "channel": "EMAIL", "template_key": "realtor_team_update", "goal": "Team/capacity update"},
                    {"step_order": 4, "min_days": 70, "channel": "EMAIL", "template_key": "realtor_quarterly_review", "goal": "Quarterly review offer"},
                    {"step_order": 5, "min_days": 100, "channel": "EMAIL", "template_key": "realtor_annual_planning", "goal": "Annual planning invite"}
                ]
            }
        ]

        for cad in cadences:
            cadence_id = str(uuid.uuid4())

            # Insert cadence
            conn.execute(text("""
                INSERT INTO rw_cadence (id, key, name, description, person_type, target_stages, is_default)
                VALUES (:id, :key, :name, :description, :person_type, :target_stages, :is_default)
                ON CONFLICT (key) DO UPDATE SET
                    name = EXCLUDED.name,
                    description = EXCLUDED.description,
                    target_stages = EXCLUDED.target_stages,
                    is_default = EXCLUDED.is_default
            """), {
                "id": cadence_id,
                "key": cad["key"],
                "name": cad["name"],
                "description": cad["description"],
                "person_type": cad["person_type"],
                "target_stages": cad.get("target_stages", []),
                "is_default": cad.get("is_default", False)
            })

            # Get the cadence ID (in case it already existed)
            result = conn.execute(text("SELECT id FROM rw_cadence WHERE key = :key"), {"key": cad["key"]}).fetchone()
            actual_cadence_id = result.id

            # Delete existing steps and insert new ones
            conn.execute(text("DELETE FROM rw_cadence_step WHERE cadence_id = :cadence_id"), {"cadence_id": actual_cadence_id})

            for step in cad["steps"]:
                step_id = str(uuid.uuid4())
                conn.execute(text("""
                    INSERT INTO rw_cadence_step (id, cadence_id, step_order, min_days_after_prev, channel, template_key, goal)
                    VALUES (:id, :cadence_id, :step_order, :min_days, :channel, :template_key, :goal)
                """), {
                    "id": step_id,
                    "cadence_id": actual_cadence_id,
                    "step_order": step["step_order"],
                    "min_days": step["min_days"],
                    "channel": step["channel"],
                    "template_key": step["template_key"],
                    "goal": step.get("goal")
                })

        print(f"  Created/updated {len(cadences)} cadences with steps")

        # =============================================================================
        # SEED MESSAGE TEMPLATES
        # =============================================================================
        print("Seeding message templates...")

        templates = [
            # LO Email Templates
            {
                "key": "lo_welcome",
                "name": "LO Welcome Email",
                "channel": "EMAIL",
                "person_type": "LOAN_OFFICER",
                "subject": "Quick intro + one idea for {first_name}",
                "body": """Hi {first_name},

I wanted to reach out briefly - I help loan officers like yourself streamline operations and close more loans with less friction.

One quick idea that's worked well for others: Having a dedicated ops support line that processors can reach in under 2 minutes for condition clarifications. It's cut turn times by 20%+ for several LOs we work with.

Would love to share more if you're ever curious. No pressure at all.

Best,
{sender_name}""",
                "merge_fields": ["first_name", "sender_name"],
                "category": "initial",
                "purpose": "introduction"
            },
            {
                "key": "lo_friction_removal",
                "name": "LO Friction Removal Idea",
                "channel": "EMAIL",
                "person_type": "LOAN_OFFICER",
                "subject": "One idea to remove pipeline friction",
                "body": """Hi {first_name},

Hope you're having a strong month.

One thing I've been seeing work really well: automated condition requests that go out within 30 minutes of submission, with specific document checklists based on loan type.

It sounds simple, but it's been shaving days off the back-end for LOs who've implemented it.

Happy to walk through how we've set it up if you're interested.

Best,
{sender_name}""",
                "merge_fields": ["first_name", "sender_name"],
                "category": "nurture",
                "purpose": "value"
            },
            {
                "key": "lo_switch_plan",
                "name": "LO Switch Plan Email",
                "channel": "EMAIL",
                "person_type": "LOAN_OFFICER",
                "subject": "Your 4-week transition roadmap",
                "body": """Hi {first_name},

Given our recent conversations, I put together a simple 4-week roadmap for what a transition would look like:

**Week 1:** Paperwork + licensing verification
**Week 2:** Tech setup + training scheduled
**Week 3:** Pipeline transfer planning + processor introductions
**Week 4:** Go-live + dedicated support

The goal is zero disruption to your current pipeline and a clean handoff.

Want me to walk through the details?

Best,
{sender_name}""",
                "merge_fields": ["first_name", "sender_name"],
                "category": "high_intent",
                "purpose": "book_meeting"
            },

            # LO SMS Templates
            {
                "key": "lo_hot_sms",
                "name": "LO Hot Lead SMS",
                "channel": "SMS",
                "person_type": "LOAN_OFFICER",
                "body": "Hi {first_name}, got a few minutes today? Would love to answer any questions you have. No pressure either way.",
                "merge_fields": ["first_name"],
                "category": "high_intent",
                "purpose": "micro_yes"
            },
            {
                "key": "lo_quick_win",
                "name": "LO Quick Win SMS",
                "channel": "SMS",
                "person_type": "LOAN_OFFICER",
                "body": "Hi {first_name}, quick win to share: {insight}. Let me know if you want details.",
                "merge_fields": ["first_name", "insight"],
                "category": "nurture",
                "purpose": "value"
            },

            # Realtor Email Templates
            {
                "key": "realtor_welcome",
                "name": "Realtor Welcome Email",
                "channel": "EMAIL",
                "person_type": "REALTOR",
                "subject": "Quick intro + a promise on response time",
                "body": """Hi {first_name},

I wanted to introduce myself - I work with agents like yourself who need a lending partner that actually picks up the phone and keeps deals moving.

My promise: pre-approval letters in under 4 hours, and you'll always be able to reach me or my team within 15 minutes during business hours.

I'd love to be a resource whenever you have a buyer who needs fast, reliable financing.

Best,
{sender_name}""",
                "merge_fields": ["first_name", "sender_name"],
                "category": "initial",
                "purpose": "introduction"
            },
            {
                "key": "realtor_listing_update_engine",
                "name": "Realtor Listing Update Engine Email",
                "channel": "EMAIL",
                "person_type": "REALTOR",
                "subject": "Never chase updates again",
                "body": """Hi {first_name},

I know one of the biggest frustrations agents face is chasing lenders for updates to share with sellers.

We've built a "Listing Agent Update Engine" - automated weekly emails to you (and your seller if you want) showing exactly where the loan stands, next steps, and any items needed.

You never have to chase, and your sellers see you're on top of it.

Worth a quick call to see if it fits your workflow?

Best,
{sender_name}""",
                "merge_fields": ["first_name", "sender_name"],
                "category": "high_intent",
                "purpose": "book_meeting"
            },

            # Realtor SMS Templates
            {
                "key": "realtor_empathy_sms",
                "name": "Realtor Empathy SMS",
                "channel": "SMS",
                "person_type": "REALTOR",
                "body": "Hi {first_name}, heard things got complicated on that last deal. Happy to run point on comms if you ever need backup. Here for you.",
                "merge_fields": ["first_name"],
                "category": "high_intent",
                "purpose": "value"
            },
            {
                "key": "realtor_hot_sms",
                "name": "Realtor Hot Lead SMS",
                "channel": "SMS",
                "person_type": "REALTOR",
                "body": "Hi {first_name}, quick question - would a 10-min call this week work to chat about partnering on some deals? No pitch, just want to see if we're a fit.",
                "merge_fields": ["first_name"],
                "category": "high_intent",
                "purpose": "book_meeting"
            }
        ]

        for tmpl in templates:
            template_id = str(uuid.uuid4())
            conn.execute(text("""
                INSERT INTO rw_message_template (id, key, name, channel, person_type, subject, body, merge_fields, category, purpose)
                VALUES (:id, :key, :name, :channel, :person_type, :subject, :body, :merge_fields, :category, :purpose)
                ON CONFLICT (organization_id, key) DO UPDATE SET
                    name = EXCLUDED.name,
                    subject = EXCLUDED.subject,
                    body = EXCLUDED.body,
                    merge_fields = EXCLUDED.merge_fields,
                    category = EXCLUDED.category,
                    purpose = EXCLUDED.purpose
            """), {
                "id": template_id,
                "key": tmpl["key"],
                "name": tmpl["name"],
                "channel": tmpl["channel"],
                "person_type": tmpl.get("person_type"),
                "subject": tmpl.get("subject"),
                "body": tmpl["body"],
                "merge_fields": tmpl.get("merge_fields", []),
                "category": tmpl.get("category"),
                "purpose": tmpl.get("purpose")
            })

        print(f"  Created/updated {len(templates)} message templates")

        conn.commit()
        print("\n Seed data migration completed successfully!")

    return {"message": "Seed data migration completed", "playbooks": len(playbooks), "cadences": len(cadences), "templates": len(templates)}


if __name__ == "__main__":
    run_migration()
