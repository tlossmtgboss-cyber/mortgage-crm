"""Auto-extracted from seed_full_demo.py — mechanical decomposition (no logic changes)."""
import json
import random
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import text

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
    exists,
    get_id,
)


def seed_referral_partners(conn, org_id, user_ids, lead_ids):
    """Create referral partners linked to leads. Returns dict of partner name→ID."""

    manager_id = user_ids.get("manager")
    lo_sarah_id = user_ids.get("lo_sarah")
    lo_marcus_id = user_ids.get("lo_marcus")

    PARTNERS = [
        {
            "name": "Jennifer Walsh",
            "business_name": "RE/MAX Charleston",
            "contact_name": "Jennifer Walsh",
            "category": "realtor",
            "company": "RE/MAX Charleston",
            "type": "realtor",
            "email": "jennifer.walsh@remax.com",
            "phone": "+18431220001",
            "referrals_in": 18,
            "referrals_out": 5,
            "closed_loans": 12,
            "volume": Decimal("4200000.00"),
            "loyalty_tier": "gold",
            "title": "Realtor / Team Lead",
            "street_address": "1122 East Bay St",
            "city": "Charleston",
            "state": "SC",
            "zip_code": "29403",
            "owner_id": lo_sarah_id,
            "notes": "Top-producing gold partner. Refers luxury buyers regularly. Monthly lunch relationship.",
        },
        {
            "name": "Amanda Foster",
            "business_name": "Lowcountry Homes",
            "contact_name": "Amanda Foster",
            "category": "realtor",
            "company": "Lowcountry Homes",
            "type": "realtor",
            "email": "amanda.foster@lowcountryhomes.com",
            "phone": "+18431220002",
            "referrals_in": 15,
            "referrals_out": 4,
            "closed_loans": 9,
            "volume": Decimal("3100000.00"),
            "loyalty_tier": "gold",
            "title": "Senior Realtor",
            "street_address": "850 Coleman Blvd",
            "city": "Mount Pleasant",
            "state": "SC",
            "zip_code": "29464",
            "owner_id": lo_sarah_id,
            "notes": "Specializes in Mt Pleasant. Strong first-time buyer pipeline.",
        },
        {
            "name": "Nicole Williams",
            "business_name": "Keller Williams Mt Pleasant",
            "contact_name": "Nicole Williams",
            "category": "realtor",
            "company": "Keller Williams Mt Pleasant",
            "type": "realtor",
            "email": "nicole.williams@kwmtp.com",
            "phone": "+18431220003",
            "referrals_in": 12,
            "referrals_out": 3,
            "closed_loans": 7,
            "volume": Decimal("2500000.00"),
            "loyalty_tier": "gold",
            "title": "Realtor",
            "street_address": "1050 Johnnie Dodds Blvd",
            "city": "Mount Pleasant",
            "state": "SC",
            "zip_code": "29464",
            "owner_id": lo_marcus_id,
            "notes": "Rising star in the Mt Pleasant market. Strong social media presence.",
        },
        {
            "name": "Robert Chen",
            "business_name": "Edward Jones",
            "contact_name": "Robert Chen",
            "category": "financial_advisor",
            "company": "Edward Jones",
            "type": "financial_advisor",
            "email": "robert.chen@edwardjones.com",
            "phone": "+18431220004",
            "referrals_in": 8,
            "referrals_out": 6,
            "closed_loans": 5,
            "volume": Decimal("1800000.00"),
            "loyalty_tier": "silver",
            "title": "Financial Advisor",
            "street_address": "470 King St",
            "city": "Charleston",
            "state": "SC",
            "zip_code": "29403",
            "owner_id": lo_sarah_id,
            "notes": "Mutual referral relationship. Refers HNW clients who need large purchase loans.",
        },
        {
            "name": "Maria Rodriguez",
            "business_name": "Lowcountry Builders",
            "contact_name": "Maria Rodriguez",
            "category": "builder",
            "company": "Lowcountry Builders",
            "type": "builder",
            "email": "maria.rodriguez@lowcountrybuilders.com",
            "phone": "+18431220005",
            "referrals_in": 6,
            "referrals_out": 2,
            "closed_loans": 3,
            "volume": Decimal("1200000.00"),
            "loyalty_tier": "silver",
            "title": "Sales Director",
            "street_address": "3000 Ashley River Rd",
            "city": "Charleston",
            "state": "SC",
            "zip_code": "29414",
            "owner_id": lo_marcus_id,
            "notes": "New construction pipeline. Prefers lenders with 60-day lock programs.",
        },
        {
            "name": "David Kim",
            "business_name": "Kim & Associates",
            "contact_name": "David Kim",
            "category": "attorney",
            "company": "Kim & Associates",
            "type": "attorney",
            "email": "david.kim@kimassociates.com",
            "phone": "+18431220006",
            "referrals_in": 4,
            "referrals_out": 8,
            "closed_loans": 2,
            "volume": Decimal("700000.00"),
            "loyalty_tier": "bronze",
            "title": "Real Estate Attorney",
            "street_address": "150 Meeting St",
            "city": "Charleston",
            "state": "SC",
            "zip_code": "29401",
            "owner_id": lo_sarah_id,
            "notes": "Handles estate and probate sales. Low volume but high-quality referrals.",
        },
        {
            "name": "Lisa Thompson",
            "business_name": "Allstate Insurance",
            "contact_name": "Lisa Thompson",
            "category": "insurance_agent",
            "company": "Allstate Insurance",
            "type": "insurance_agent",
            "email": "lisa.thompson@allstate.com",
            "phone": "+18431220007",
            "referrals_in": 3,
            "referrals_out": 5,
            "closed_loans": 1,
            "volume": Decimal("350000.00"),
            "loyalty_tier": "bronze",
            "title": "Insurance Agent",
            "street_address": "2200 Ashley Phosphate Rd",
            "city": "North Charleston",
            "state": "SC",
            "zip_code": "29405",
            "owner_id": lo_marcus_id,
            "notes": "Bundling opportunity — refers clients who need home insurance plus mortgage.",
        },
        {
            "name": "Michael Brown",
            "business_name": "Brown CPA Group",
            "contact_name": "Michael Brown",
            "category": "cpa",
            "company": "Brown CPA Group",
            "type": "cpa",
            "email": "michael.brown@browncpa.com",
            "phone": "+18431220008",
            "referrals_in": 2,
            "referrals_out": 3,
            "closed_loans": 1,
            "volume": Decimal("280000.00"),
            "loyalty_tier": "bronze",
            "title": "CPA / Tax Advisor",
            "street_address": "500 Wingo Way",
            "city": "Mount Pleasant",
            "state": "SC",
            "zip_code": "29464",
            "owner_id": lo_sarah_id,
            "notes": "Self-employed client referrals. Educating on bank statement loan programs.",
        },
    ]

    partner_ids = {}

    for partner in PARTNERS:
        if exists(conn, "referral_partners", "email", partner["email"]):
            existing_id = get_id(conn, "referral_partners", "email", partner["email"])
            partner_ids[partner["name"]] = existing_id
            print(f"⏭️  Referral partner exists: {partner['name']}")
            continue

        last_interaction = NOW - timedelta(days=random.randint(7, 45))

        result = conn.execute(
            text("""
                INSERT INTO referral_partners (
                    organization_id, name, business_name, contact_name,
                    category, company, type, phone, email,
                    referrals_in, referrals_out, closed_loans, volume,
                    status, loyalty_tier, last_interaction, notes,
                    street_address, city, state, zip_code,
                    title, created_at, owner_id
                ) VALUES (
                    :org_id, :name, :business_name, :contact_name,
                    :category, :company, :type, :phone, :email,
                    :referrals_in, :referrals_out, :closed_loans, :volume,
                    :status, :loyalty_tier, :last_interaction, :notes,
                    :street_address, :city, :state, :zip_code,
                    :title, :created_at, :owner_id
                ) RETURNING id
            """),
            {
                "org_id": org_id,
                "name": partner["name"],
                "business_name": partner["business_name"],
                "contact_name": partner["contact_name"],
                "category": partner["category"],
                "company": partner["company"],
                "type": partner["type"],
                "phone": partner["phone"],
                "email": partner["email"],
                "referrals_in": partner["referrals_in"],
                "referrals_out": partner["referrals_out"],
                "closed_loans": partner["closed_loans"],
                "volume": partner["volume"],
                "status": "active",
                "loyalty_tier": partner["loyalty_tier"],
                "last_interaction": last_interaction,
                "notes": partner["notes"],
                "street_address": partner["street_address"],
                "city": partner["city"],
                "state": partner["state"],
                "zip_code": partner["zip_code"],
                "title": partner["title"],
                "created_at": NOW - timedelta(days=random.randint(90, 730)),
                "owner_id": partner["owner_id"],
            },
        )
        new_id = result.fetchone()[0]
        partner_ids[partner["name"]] = new_id
        print(f"✅ Created referral partner: {partner['name']} ({partner['loyalty_tier']}, {partner['category']})")

    conn.commit()

    # Link 3-5 leads to gold-tier partners (skip leads already sourced as Referral)
    gold_partners = [
        ("Jennifer Walsh", "brianna.okafor@gmail.com"),
        ("Amanda Foster", "vanessa.hartley@gmail.com"),
        ("Nicole Williams", "roberto.sandoval@hotmail.com"),
        ("Jennifer Walsh", "michelle.osei@gmail.com"),
        ("Amanda Foster", "kevin.albright@gmail.com"),
    ]
    linked = 0
    for partner_name, lead_email in gold_partners:
        partner_id = partner_ids.get(partner_name)
        lead_id = lead_ids.get(lead_email) if lead_ids else None
        if not partner_id or not lead_id:
            continue

        # Only update if the lead exists and source is not already 'Referral'
        update_result = conn.execute(
            text("""
                UPDATE leads
                SET referral_partner_id = :partner_id, source = 'Referral'
                WHERE id = :lead_id
                  AND organization_id = :org_id
                  AND (source IS NULL OR source != 'Referral')
            """),
            {"partner_id": partner_id, "lead_id": lead_id, "org_id": org_id},
        )
        if update_result.rowcount:
            linked += 1
            print(f"✅ Linked lead {lead_email} → partner {partner_name}")

    conn.commit()
    print(f"✅ Seeded {len(partner_ids)} referral partners, linked {linked} leads")
    return partner_ids


