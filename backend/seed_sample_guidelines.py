#!/usr/bin/env python3
"""
Seed sample guideline updates for testing
"""
import sys
import os
from datetime import datetime, timedelta
import hashlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal
from guideline_updates_models import GuidelineUpdate

def generate_hash(content: str) -> str:
    """Generate SHA256 hash"""
    return hashlib.sha256(content.encode()).hexdigest()

def seed_sample_guidelines():
    """Add sample guideline updates to database"""
    db = SessionLocal()

    sample_updates = [
        # Fannie Mae
        {
            'source': 'fannie_mae',
            'title': 'Selling Guide Announcement SEL-2024-08',
            'section_code': 'SEL-2024-08',
            'description': 'Updated requirements for home equity conversion mortgages',
            'url': 'https://selling-guide.fanniemae.com/Selling-Guide/Origination-thru-Closing/Subpart-B3-Underwriting-Borrowers/Chapter-B3-5-Credit-Assessment/Section-B3-5-1-Credit-Scores',
            'published_date': datetime.now(timezone.utc) - timedelta(days=2),
            'is_new': True
        },
        {
            'source': 'fannie_mae',
            'title': 'Selling Guide Announcement SEL-2024-07',
            'section_code': 'SEL-2024-07',
            'description': 'Changes to income calculation guidelines for self-employed borrowers',
            'url': 'https://selling-guide.fanniemae.com/Selling-Guide/Origination-thru-Closing/Subpart-B3-Underwriting-Borrowers/Chapter-B3-3-Income-Assessment/1040',
            'published_date': datetime.now(timezone.utc) - timedelta(days=5),
            'is_new': True
        },

        # Freddie Mac
        {
            'source': 'freddie_mac',
            'title': 'Bulletin 2024-15: Updated DTI Requirements',
            'section_code': '2024-15',
            'description': 'New debt-to-income ratio requirements for conventional loans',
            'url': 'https://guide.freddiemac.com/app/guide/bulletin/2024-15',
            'published_date': datetime.now(timezone.utc) - timedelta(days=3),
            'is_new': True
        },
        {
            'source': 'freddie_mac',
            'title': 'Bulletin 2024-14: Appraisal Modernization',
            'section_code': '2024-14',
            'description': 'Expanded use of automated valuation models',
            'url': 'https://guide.freddiemac.com/app/guide/bulletin/2024-14',
            'published_date': datetime.now(timezone.utc) - timedelta(days=7),
            'is_new': True
        },

        # FHA
        {
            'source': 'fha',
            'title': 'Mortgagee Letter 2024-11: Credit Score Requirements',
            'section_code': 'ML 2024-11',
            'description': 'Updated minimum credit score requirements for FHA loans',
            'url': 'https://www.hud.gov/program_offices/administration/hudclips/letters/mortgagee/2024ml',
            'published_date': datetime.now(timezone.utc) - timedelta(days=4),
            'is_new': True
        },
        {
            'source': 'fha',
            'title': 'Mortgagee Letter 2024-10: Property Flip Requirements',
            'section_code': 'ML 2024-10',
            'description': 'Changes to anti-flipping regulations',
            'url': 'https://www.hud.gov/program_offices/administration/hudclips/letters/mortgagee/2024ml',
            'published_date': datetime.now(timezone.utc) - timedelta(days=8),
            'is_new': False
        },

        # VA
        {
            'source': 'va',
            'title': 'VA Circular 26-24-10: Residual Income Updates',
            'section_code': '26-24-10',
            'description': 'Updated residual income tables for VA loans',
            'url': 'https://www.benefits.va.gov/HOMELOANS/circulars.asp',
            'published_date': datetime.now(timezone.utc) - timedelta(days=6),
            'is_new': True
        },
        {
            'source': 'va',
            'title': 'VA Circular 26-24-09: Energy Efficient Improvements',
            'section_code': '26-24-09',
            'description': 'Expanded eligibility for energy efficiency upgrades',
            'url': 'https://www.benefits.va.gov/HOMELOANS/circulars.asp',
            'published_date': datetime.now(timezone.utc) - timedelta(days=10),
            'is_new': False
        },

        # USDA
        {
            'source': 'usda',
            'title': 'USDA Rural Development Notice: Area Eligibility Changes',
            'section_code': None,
            'description': 'Updated list of eligible rural areas for USDA loans',
            'url': 'https://www.rd.usda.gov/newsroom',
            'published_date': datetime.now(timezone.utc) - timedelta(days=1),
            'is_new': True
        },
        {
            'source': 'usda',
            'title': 'USDA Rural Development Notice: Income Limits Update',
            'section_code': None,
            'description': 'New income limits for USDA guaranteed loan program',
            'url': 'https://www.rd.usda.gov/newsroom',
            'published_date': datetime.now(timezone.utc) - timedelta(days=9),
            'is_new': False
        },
    ]

    added_count = 0

    for update_data in sample_updates:
        # Generate unique hash
        content_hash = generate_hash(update_data['title'] + update_data['url'])
        update_data['content_hash'] = content_hash

        # Check if already exists
        existing = db.query(GuidelineUpdate).filter_by(content_hash=content_hash).first()
        if existing:
            print(f"⏭️  Skipping (already exists): {update_data['title'][:50]}...")
            continue

        try:
            update = GuidelineUpdate(**update_data)
            db.add(update)
            db.commit()
            added_count += 1
            print(f"✅ Added: {update_data['source'].upper()} - {update_data['title'][:50]}...")
        except Exception as e:
            db.rollback()
            print(f"❌ Error adding update: {e}")

    db.close()

    print(f"\n{'='*60}")
    print(f"✅ Seeding complete: {added_count} new guideline updates added")
    print(f"{'='*60}")
    return added_count

if __name__ == "__main__":
    print("Seeding sample guideline updates...\n")
    seed_sample_guidelines()
