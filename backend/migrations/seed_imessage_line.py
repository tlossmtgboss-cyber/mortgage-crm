"""
Seed: Insert a default iMessage line configuration for the first organization.

Creates a single IMessageLine row so the iMessage/BlueBubbles integration
has a configured sender handle out of the box.

Run standalone:  python -m migrations.seed_imessage_line
Idempotent:      Skips if the org already has any rows in imessage_lines.

Environment variables (optional):
  IMESSAGE_BB_BASE_URL   — BlueBubbles server URL (default: https://bb.perenniaai.com)
  IMESSAGE_BB_PASSWORD   — BlueBubbles API password (stored as-is; encryption
                           happens at the service layer)
"""
from __future__ import annotations

import logging
import os
import sys
import uuid

logger = logging.getLogger(__name__)


def run_seed():
    # ------------------------------------------------------------------
    # 1. Bootstrap imports
    # ------------------------------------------------------------------
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from sqlalchemy import text
    from db import engine

    bb_base_url = os.environ.get("IMESSAGE_BB_BASE_URL", "https://bb.perenniaai.com")
    bb_password = os.environ.get("IMESSAGE_BB_PASSWORD")

    # ------------------------------------------------------------------
    # 2. Resolve organization_id (first org, or fallback to 1)
    # ------------------------------------------------------------------
    with engine.connect() as conn:
        # Ensure the table exists before attempting anything
        table_check = conn.execute(
            text(
                "SELECT EXISTS ("
                "  SELECT 1 FROM information_schema.tables"
                "  WHERE table_name = 'imessage_lines'"
                ")"
            )
        ).scalar()
        if not table_check:
            logger.error(
                "imessage_lines table does not exist — "
                "run 20260427_add_imessage_tables.py first"
            )
            return

        # Grab the organization that has the most users (the real tenant)
        row = conn.execute(
            text(
                "SELECT organization_id, COUNT(*) as cnt "
                "FROM users WHERE organization_id IS NOT NULL "
                "GROUP BY organization_id ORDER BY cnt DESC LIMIT 1"
            )
        ).fetchone()
        org_id = row[0] if row else 1
        logger.warning("Using organization_id = %s (most active org)", org_id)

        # ------------------------------------------------------------------
        # 3. Check for existing lines
        # ------------------------------------------------------------------
        existing = conn.execute(
            text(
                "SELECT COUNT(*) FROM imessage_lines "
                "WHERE organization_id = :org_id"
            ),
            {"org_id": org_id},
        ).scalar()

        if existing and existing > 0:
            logger.warning(
                "Organization %s already has %d iMessage line(s) — skipping seed",
                org_id,
                existing,
            )
            return

        # If there are lines for a different org but none for the real org,
        # reassign them (handles initial seed that picked wrong org)
        total_lines = conn.execute(
            text("SELECT COUNT(*) FROM imessage_lines")
        ).scalar() or 0
        if total_lines > 0:
            moved = conn.execute(
                text(
                    "UPDATE imessage_lines SET organization_id = :org_id "
                    "WHERE organization_id != :org_id "
                    "RETURNING id"
                ),
                {"org_id": org_id},
            ).fetchall()
            if moved:
                conn.commit()
                logger.warning(
                    "Reassigned %d iMessage line(s) to org %s (was wrong org)",
                    len(moved), org_id,
                )
            return

        # ------------------------------------------------------------------
        # 4. Insert the default line
        # ------------------------------------------------------------------
        line_id = uuid.uuid4()
        conn.execute(
            text(
                "INSERT INTO imessage_lines "
                "  (id, organization_id, label, handle, bb_base_url, "
                "   bb_password, enabled, daily_send_limit, "
                "   created_at, updated_at) "
                "VALUES "
                "  (:id, :org_id, :label, :handle, :bb_base_url, "
                "   :bb_password, :enabled, :daily_send_limit, "
                "   NOW(), NOW())"
            ),
            {
                "id": str(line_id),
                "org_id": org_id,
                "label": "Main iMessage Line",
                "handle": "+18438838956",
                "bb_base_url": bb_base_url,
                "bb_password": bb_password,
                "enabled": True,
                "daily_send_limit": 2500,
            },
        )
        conn.commit()

        logger.info(
            "Seeded iMessage line: id=%s, org=%s, handle=+18438838956, "
            "bb_base_url=%s, daily_send_limit=2500",
            line_id,
            org_id,
            bb_base_url,
        )
        if not bb_password:
            logger.warning(
                "IMESSAGE_BB_PASSWORD not set — bb_password stored as NULL. "
                "Set the env var and re-run, or update the row manually."
            )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    run_seed()
