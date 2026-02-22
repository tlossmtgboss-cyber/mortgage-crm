"""
Calculator Settings Routes

Manages calculator-to-buyer-type assignments for the Calculator Agent.
Self-setup creates the `calculator_buyer_type_assignments` table and
adds `buyer_type` column to leads.
"""

import logging
from typing import Optional, List
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import text
from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

CALCULATOR_TYPES = [
    {"id": "monthly_pi", "label": "Monthly P&I", "description": "Basic principal & interest payment"},
    {"id": "piti", "label": "Full PITI", "description": "Payment with taxes, insurance, PMI"},
    {"id": "pmi", "label": "PMI/MIP", "description": "Mortgage insurance calculation"},
    {"id": "dti", "label": "DTI Ratios", "description": "Debt-to-income ratios"},
    {"id": "ltv", "label": "LTV", "description": "Loan-to-value ratio"},
    {"id": "affordability", "label": "Affordability", "description": "Maximum purchase price"},
    {"id": "closing_costs", "label": "Closing Costs", "description": "Estimated closing costs"},
    {"id": "amortization", "label": "Amortization", "description": "Payment schedule"},
    {"id": "cost_of_waiting", "label": "Cost of Waiting", "description": "Cost of waiting to buy"},
    {"id": "prepay_vs_invest", "label": "Prepay vs Invest", "description": "Compare prepaying vs investing"},
    {"id": "rent_vs_buy", "label": "Rent vs Buy", "description": "Rent vs buy analysis"},
    {"id": "program_comparison", "label": "Program Comparison", "description": "Compare loan programs"},
]

DEFAULT_BUYER_TYPES = [
    {"id": "first_time", "label": "First-Time Buyer"},
    {"id": "repeat", "label": "Repeat Buyer"},
    {"id": "vacation", "label": "Vacation Home"},
    {"id": "investment", "label": "Investment Property"},
    {"id": "refinance", "label": "Refinance"},
]


class AssignmentUpdate(BaseModel):
    assignments: List[dict]  # [{buyer_type, calculator_type, enabled, priority}]


class CustomBuyerType(BaseModel):
    label: str


def register_calculator_settings_routes(app, get_db, get_current_user, **kwargs):
    """Register calculator settings routes."""

    @app.post("/api/v1/settings/calculator-types/setup")
    async def setup_calculator_tables(
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Create calculator_buyer_type_assignments table and add buyer_type column to leads."""
        try:
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS calculator_buyer_type_assignments (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    buyer_type VARCHAR(50) NOT NULL,
                    calculator_type VARCHAR(50) NOT NULL,
                    enabled BOOLEAN DEFAULT TRUE,
                    priority INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(user_id, buyer_type, calculator_type)
                )
            """))

            db.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_calc_buyer_type_user
                ON calculator_buyer_type_assignments(user_id, buyer_type)
            """))

            # Add buyer_type column to leads if not exists
            db.execute(text("""
                ALTER TABLE leads ADD COLUMN IF NOT EXISTS buyer_type VARCHAR(50)
            """))

            # Custom buyer types table
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS custom_buyer_types (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    label VARCHAR(100) NOT NULL,
                    type_id VARCHAR(50) NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(user_id, type_id)
                )
            """))

            db.commit()
            return {"success": True, "message": "Calculator settings tables created"}
        except Exception as e:
            db.rollback()
            logger.error(f"Error setting up calculator tables: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.get("/api/v1/settings/calculator-types")
    async def get_calculator_settings(
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Get calculator types, buyer types, and current assignments."""
        try:
            # Get custom buyer types for this user
            custom_types = []
            try:
                rows = db.execute(text(
                    "SELECT type_id, label FROM custom_buyer_types WHERE user_id = :uid ORDER BY label"
                ), {"uid": current_user.id}).fetchall()
                custom_types = [{"id": r[0], "label": r[1]} for r in rows]
            except Exception as e:
                logger.warning(f"Error fetching custom_buyer_types (table may not exist): {e}")

            all_buyer_types = DEFAULT_BUYER_TYPES + custom_types

            # Get current assignments
            assignments = []
            try:
                rows = db.execute(text("""
                    SELECT buyer_type, calculator_type, enabled, priority
                    FROM calculator_buyer_type_assignments
                    WHERE user_id = :uid
                    ORDER BY buyer_type, priority DESC
                """), {"uid": current_user.id}).fetchall()
                assignments = [
                    {
                        "buyer_type": r[0],
                        "calculator_type": r[1],
                        "enabled": r[2],
                        "priority": r[3],
                    }
                    for r in rows
                ]
            except Exception as e:
                logger.warning(f"Error fetching calculator_buyer_type_assignments (table may not exist): {e}")

            return {
                "calculator_types": CALCULATOR_TYPES,
                "buyer_types": all_buyer_types,
                "assignments": assignments,
            }
        except Exception as e:
            logger.error(f"Error getting calculator settings: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.put("/api/v1/settings/calculator-types")
    async def update_calculator_assignments(
        data: AssignmentUpdate,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Bulk update calculator-buyer-type assignments."""
        try:
            # Delete existing assignments for this user
            db.execute(text(
                "DELETE FROM calculator_buyer_type_assignments WHERE user_id = :uid"
            ), {"uid": current_user.id})

            # Insert new assignments
            for a in data.assignments:
                if a.get("enabled", True):
                    db.execute(text("""
                        INSERT INTO calculator_buyer_type_assignments
                            (user_id, buyer_type, calculator_type, enabled, priority, updated_at)
                        VALUES (:uid, :bt, :ct, :enabled, :priority, NOW())
                    """), {
                        "uid": current_user.id,
                        "bt": a["buyer_type"],
                        "ct": a["calculator_type"],
                        "enabled": a.get("enabled", True),
                        "priority": a.get("priority", 0),
                    })

            db.commit()
            return {
                "success": True,
                "message": f"Saved {len([a for a in data.assignments if a.get('enabled', True)])} assignments",
            }
        except Exception as e:
            db.rollback()
            logger.error(f"Error updating calculator assignments: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.post("/api/v1/settings/calculator-types/buyer-types")
    async def add_custom_buyer_type(
        data: CustomBuyerType,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Add a custom buyer type."""
        try:
            type_id = f"custom_{data.label.lower().replace(' ', '_').replace('-', '_')}"

            db.execute(text("""
                INSERT INTO custom_buyer_types (user_id, label, type_id)
                VALUES (:uid, :label, :type_id)
                ON CONFLICT (user_id, type_id) DO NOTHING
            """), {
                "uid": current_user.id,
                "label": data.label,
                "type_id": type_id,
            })
            db.commit()

            return {"success": True, "buyer_type": {"id": type_id, "label": data.label}}
        except Exception as e:
            db.rollback()
            logger.error(f"Error adding custom buyer type: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.delete("/api/v1/settings/calculator-types/buyer-types/{type_id}")
    async def delete_custom_buyer_type(
        type_id: str,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Delete a custom buyer type and its assignments."""
        try:
            db.execute(text(
                "DELETE FROM custom_buyer_types WHERE user_id = :uid AND type_id = :tid"
            ), {"uid": current_user.id, "tid": type_id})

            db.execute(text(
                "DELETE FROM calculator_buyer_type_assignments WHERE user_id = :uid AND buyer_type = :tid"
            ), {"uid": current_user.id, "tid": type_id})

            db.commit()
            return {"success": True, "message": f"Deleted buyer type '{type_id}'"}
        except Exception as e:
            db.rollback()
            logger.error(f"Error deleting custom buyer type: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    logger.info("Calculator settings routes registered")
