"""
Migration: Create aria_campaigns and aria_campaign_recipients tables.

Run: python migrations/add_aria_campaigns.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import inspect
from db import engine
from database.models.aria_campaign import AriaCampaign, AriaCampaignRecipient


def migrate():
    inspector = inspect(engine)
    existing = inspector.get_table_names()

    if "aria_campaigns" not in existing:
        AriaCampaign.__table__.create(engine, checkfirst=True)
        print("Created table: aria_campaigns")
    else:
        print("Table aria_campaigns already exists")

    if "aria_campaign_recipients" not in existing:
        AriaCampaignRecipient.__table__.create(engine, checkfirst=True)
        print("Created table: aria_campaign_recipients")
    else:
        print("Table aria_campaign_recipients already exists")


if __name__ == "__main__":
    migrate()
