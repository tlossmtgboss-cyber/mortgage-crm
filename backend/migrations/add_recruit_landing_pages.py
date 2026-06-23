"""
Recruit Landing Pages Migration

Creates recruit_landing_pages table — stores configurable HTML landing pages
for the recruiting platform (website builder).
"""

import json
import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)

_CALLCENTER_CONFIG = {
    "page_title": "Careers | CMG Home Loans — South Carolina",
    "company_name": "CMG Home Loans",
    "location_display": "Charleston, SC",
    "primary_color": "#6AAA26",
    "primary_color_dark": "#578F1E",
    "primary_color_pale": "#EFF7E1",
    "hero_headline": 'Build a <span class="red">six-figure</span><br>mortgage career<br>from <span class="italic">day one.</span>',
    "hero_headline_plain": "Build a six-figure mortgage career from day one.",
    "hero_subheadline": '<p class="hero-sub">CMG Financial is a nationally recognized mortgage lender that specializes in home purchase and refinance needs. Since 1993, we\'ve been closing loans and opening doors of opportunity for our clients, partners, and employees.</p><p class="hero-sub">When you join team CMG, you don\'t just “start another job.” You join a culture of education, collaboration, and celebration. You join a group of <span style="color:#8ec94a;font-weight:600">leaders who advocate</span> for a better industry. You join a culture that <span style="color:#8ec94a;font-weight:600">cares</span> more about the world around us.</p><p class="hero-sub">And you join a family that cares about <strong>YOU.</strong></p>',
    "signing_bonus": "",
    "signing_bonus_month": "",
    "signing_bonus_deadline": "",
    "year1_range": "$65–90K",
    "year2_top": "$120,000+",
    "senior_lo": "$180,000+",
    "team_lead": "$250,000+",
    "stat_1_num": "2,400+", "stat_1_label": "Loans closed in SC last year",
    "stat_2_num": "94%", "stat_2_label": "Employees promoted within 18 months",
    "stat_3_num": "4.97 ★", "stat_3_label": "Tim Loss team borrower rating",
    "stat_4_num": "8 Weeks", "stat_4_label": "Fully paid training program",
    "manager_initials": "TL", "manager_name": "Tim Loss",
    "manager_title": "Branch Manager · CMG Home Loans, Mt. Pleasant SC · NMLS# 187037",
    "manager_nmls": "187037",
    "contact_phone_display": "(843) 834-4997",
    "contact_phone_tel": "+18438344997",
    "branch_address": "975 Johnnie Dodds Blvd. Suite A, Mt. Pleasant, SC 29464",
    "branch_nmls": "1594871",
    "training_1_week": "Weeks 1–2",
    "training_1_title": "Industry Foundations",
    "training_1_desc": "Understand mortgages end-to-end — loan types, rates, credit, and the SC housing market.",
    "training_1_items": "NMLS pre-licensing education (fully paid by CMG)\nSC mortgage law and compliance overview\nFull product catalog deep dive\nShadowing licensed LOs on live calls",
    "training_2_week": "Weeks 3–4",
    "training_2_title": "Sales Skills & Scripts",
    "training_2_desc": "Build your frameworks. Practice until they feel natural. CMG's playbook is built from 10,000+ SC conversations.",
    "training_2_items": "Call recording and live coaching feedback\nComplete objection handling library\nPre-qualification scripting techniques\nDaily role-play with your cohort",
    "training_3_week": "Weeks 5–6",
    "training_3_title": "CRM & Technology Mastery",
    "training_3_desc": "Learn every tool you'll use daily — so technology accelerates you instead of slowing you down.",
    "training_3_items": "Encompass LOS certification\nSalesforce pipeline management\nLead routing and prioritization\nAutomated follow-up sequences",
    "training_4_week": "Weeks 7–8",
    "training_4_title": "Live Pipeline Launch",
    "training_4_desc": "You're licensed, trained, and ready. Work real leads with a senior coach in your corner.",
    "training_4_items": "First live borrower conversations\nFirst closed loan milestone bonus\n90-day personalized coaching plan\nFull team integration and onboarding",
    # Hero checks
    "hero_check_1": "No mortgage license required to start — CMG pays for it",
    "hero_check_2": "Warm, pre-qualified leads delivered to your pipeline daily",
    "hero_check_3": "Fully paid 8-week training program with live coaching",
    "hero_check_4": "Competitive base + uncapped commission from day one",
    # Earnings card labels
    "earnings_label": "Year 1 On-Target Earnings",
    "earnings_note": "base salary + commission",
    # Career path section
    "career_title": "A real path forward —<br>not just another job.",
    "career_sub": "Every CMG loan officer in South Carolina starts at the same place. Where you go depends entirely on your drive and coachability.",
    "career_1_timeline": "Month 1–2", "career_1_title": "Loan Officer Trainee",
    "career_1_desc": "Paid training. Learn products, systems, compliance, and SC market dynamics.",
    "career_1_salary": "$45K base",
    "career_2_timeline": "Month 3–12", "career_2_title": "Junior Loan Officer",
    "career_2_desc": "Live warm leads. Building pipeline. Coached on every deal you work.",
    "career_2_salary": "$65–90K OTE",
    "career_3_timeline": "Year 2–3", "career_3_title": "Senior Loan Officer",
    "career_3_desc": "Referral network. Complex purchase loans. Mentoring incoming hires.",
    "career_3_salary": "$120–180K OTE",
    "career_4_timeline": "Year 3+", "career_4_title": "Team Lead / Branch Mgr",
    "career_4_desc": "Build and lead your own team. Override income. Equity in the platform.",
    "career_4_salary": "$250K+ OTE",
    # Training section headers
    "training_section_title": "Eight weeks that change<br>your career trajectory.",
    "training_section_sub": "CMG’s Mortgage Academy is nationally recognized. You’ll be licensed, certified, and pipeline-ready before you take your first live borrower call.",
    # Testimonials (raw HTML)
    "testimonials_html": '<div class="tcard"><div class="tcard-stars">★★★★★</div><div class="tcard-quote">I waited tables for six years before CMG. The training alone was worth more than any course I ever took. I closed $97,000 in my first full year and I had zero finance background.</div><div class="tcard-author"><div class="tcard-avatar" style="background: var(--cmg-navy);">JM</div><div><div class="tcard-name">Jordan M.</div><div class="tcard-detail">Former server → Senior LO, Year 2</div></div></div></div><div class="tcard"><div class="tcard-stars">★★★★★</div><div class="tcard-quote">My DISC assessment placed me in purchase loans — exactly where my personality thrives. I\'m now team lead at 26. The career path CMG lays out is real and they actually hold up their end.</div><div class="tcard-author"><div class="tcard-avatar" style="background: var(--cmg-red);">AL</div><div><div class="tcard-name">Ashley L.</div><div class="tcard-detail">Team Lead, Charleston branch</div></div></div></div><div class="tcard"><div class="tcard-stars">★★★★★</div><div class="tcard-quote">I came from retail banking and thought I knew mortgages. CMG\'s training showed me how much I didn\'t know — and how to close at twice the rate. Best career move I\'ve made.</div><div class="tcard-author"><div class="tcard-avatar" style="background: var(--green);">RC</div><div><div class="tcard-name">Rafael C.</div><div class="tcard-detail">Former bank teller → $145K Year 3</div></div></div></div>',
    # Video / manager section
    "video_label": "3-minute message from our Regional Director",
    "video_headline": "“We built this team to create careers, not fill seats.”",
    "video_body": "<p>When we opened the South Carolina call center, the goal wasn’t volume — it was building a team of mortgage professionals who’d still be here, and thriving, five years from now.</p>\n<p>Watch this short message to hear what our top performers have in common and what your first 90 days will actually look like.</p>",
    # CTA section
    "cta_headline": "Your application takes under 3 minutes.",
    "cta_body": "No cover letter. No lengthy questionnaire. Just your name, phone, and a bit about yourself. A recruiter will be in touch within one business day.",
    "cta_btn": "Apply Now — It’s Free →",
    # Page 2 — Why CMG hero
    "why_hero_headline": "The platform that lets<br>great producers <span>win.</span>",
    "why_hero_body": "Tools, leads, coaching, and culture. Here’s why CMG loan officers outperform the market — and why they stay.",
    # Page 4 — Apply sidebar
    "apply_sidebar_headline": "Tell us about <span>yourself.</span>",
    "apply_sidebar_body": "Your application takes under 3 minutes. No resume required to start. A recruiter will contact you within one business day — and you’ll schedule your intro call right here.",
    # Footer legal disclaimer
    "footer_legal": 'CMG Mortgage, Inc., NMLS ID# 1820 (For licensing information, go to <a href="https://www.nmlsconsumeraccess.org" target="_blank" style="color:rgba(255,255,255,0.45);text-decoration:underline;">www.nmlsconsumeraccess.org</a>). Equal Housing Opportunity. Licensed by the Department of Financial Protection and Innovation (DFPI) under the California Residential Mortgage Lending Act No. 4150025.; AZ #0903132; Colorado regulated by the Division of Real Estate; Georgia Residential Mortgage Licensee #15438; Mortgage Servicer License No. MS068. Hawaii Mortgage Loan Originator Company License No. HI-1820. Massachusetts Mortgage Lender License #MC1820 and Mortgage Broker License #MC1820; Mississippi Licensed Mortgage Company Licensed by the Mississippi Department of Banking and Consumer Finance; Licensed by the New Hampshire Banking Department; Licensed by the NJ Department of Banking and Insurance; Licensed Mortgage Banker – NYS Department of Financial Services; Ohio Mortgage Broker Act Mortgage Banker Exemption #MBMB.850204.000; Rhode Island Licensed Lender #20142986LL; Registered Mortgage Banker with the Texas Department of Savings and Mortgage Lending, and Licensed by the Virginia State Corporation Commission #MC-5521. CMG Mortgage, Inc. is licensed in all 50 states, the District of Columbia, Guam, Puerto Rico, and the Virgin Islands (<a href="https://www.cmgfi.com/corporate/licensing" target="_blank" style="color:rgba(255,255,255,0.45);text-decoration:underline;">https://www.cmgfi.com/corporate/licensing</a>).',
}


def run_migration(engine=None) -> None:
    if engine is None:
        from db import engine as _engine
        engine = _engine

    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS recruit_landing_pages (
                id              SERIAL          PRIMARY KEY,
                organization_id INTEGER         NOT NULL,
                title           VARCHAR(255)    NOT NULL,
                slug            VARCHAR(100)    NOT NULL,
                status          VARCHAR(20)     NOT NULL DEFAULT 'draft',
                config          JSONB           NOT NULL DEFAULT '{}'::jsonb,
                view_count      INTEGER         NOT NULL DEFAULT 0,
                submission_count INTEGER        NOT NULL DEFAULT 0,
                created_by      INTEGER,
                created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
                updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_recruit_landing_pages_org_slug UNIQUE (organization_id, slug)
            );

            CREATE INDEX IF NOT EXISTS ix_recruit_lp_org
                ON recruit_landing_pages (organization_id);
            CREATE INDEX IF NOT EXISTS ix_recruit_lp_slug
                ON recruit_landing_pages (slug);
            CREATE INDEX IF NOT EXISTS ix_recruit_lp_status
                ON recruit_landing_pages (status);

            DO $$ BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.table_constraints
                    WHERE table_name = 'recruit_landing_pages'
                      AND constraint_name = 'uq_recruit_landing_pages_org_slug'
                ) THEN
                    ALTER TABLE recruit_landing_pages
                    ADD CONSTRAINT uq_recruit_landing_pages_org_slug
                    UNIQUE (organization_id, slug);
                END IF;
            END $$;
        """))

        conn.commit()
        logger.info("✅ recruit_landing_pages table ready")

    # Seed callcenter page for every org. Each INSERT is in its own
    # engine.begin() so FORCE RLS doesn't block us — we set app.current_tenant
    # to the org slug before inserting so the tenant isolation policy passes.
    # ON CONFLICT DO NOTHING makes this idempotent across restarts.
    try:
        with engine.connect() as list_conn:
            orgs = list_conn.execute(
                text("SELECT id, slug FROM organizations")
            ).fetchall()
        for org_id, org_slug in orgs:
            try:
                with engine.begin() as seed_conn:
                    seed_conn.execute(
                        text(f"SET app.current_tenant = '{org_slug}'")
                    )
                    seed_conn.execute(text("""
                        INSERT INTO recruit_landing_pages
                            (organization_id, title, slug, status, config)
                        VALUES (:org_id, :title, :slug, :status, CAST(:config AS jsonb))
                        ON CONFLICT (organization_id, slug)
                        DO UPDATE SET
                            config = CAST(EXCLUDED.config AS jsonb),
                            status = 'published',
                            updated_at = NOW()
                    """), {
                        "org_id": org_id,
                        "title": "Call Center — SC",
                        "slug": "callcenter",
                        "status": "published",
                        "config": json.dumps(_CALLCENTER_CONFIG),
                    })
            except Exception as e:
                logger.warning(f"Could not seed callcenter page for org {org_id}: {e}")
    except Exception as e:
        logger.warning(f"Could not seed callcenter pages: {e}")
