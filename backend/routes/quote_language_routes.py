"""
Quote Language Presets API Routes

Provides endpoints for managing and testing quote-safe language presets.
"""

import os
import json
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from services.quote_language_service import (
    get_quote_language_service,
    select_quote_language,
    RateQuoteInput
)
from routes.auth_deps import require_auth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/quote-language", tags=["Quote Language"], dependencies=[Depends(require_auth)])

# Path to the presets config file
CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "config",
    "quote_language_presets.json"
)


class SelectLanguageRequest(BaseModel):
    """Request body for language selection test."""
    eligible: Optional[bool] = None
    quote_policy: Optional[str] = None
    goal: Optional[str] = None
    segment: Optional[str] = None
    rate_range_text: Optional[str] = None
    state: Optional[str] = None
    duration_minutes: int = 15


@router.get("/presets")
async def get_presets():
    """
    Get the current quote language presets configuration.

    Returns the full JSON configuration for viewing/editing in the admin UI.
    """
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r") as f:
                presets = json.load(f)
            return presets
        else:
            # Return default presets from service
            service = get_quote_language_service()
            return service._get_default_presets()
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in presets file: {e}")
        raise HTTPException(status_code=500, detail="Invalid presets configuration")
    except Exception as e:
        logger.error(f"Error loading presets: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/presets")
async def update_presets(presets: dict):
    """
    Update the quote language presets configuration.

    Validates the structure and saves to the config file.
    """
    try:
        # Validate required top-level keys
        required_keys = ["rules"]
        for key in required_keys:
            if key not in presets:
                raise HTTPException(
                    status_code=400,
                    detail=f"Missing required key: {key}"
                )

        # Validate rules structure
        rules = presets.get("rules", {})
        for bucket in ["range_only", "ballpark", "no_quote"]:
            if bucket not in rules:
                raise HTTPException(
                    status_code=400,
                    detail=f"Missing required policy bucket: {bucket}"
                )
            bucket_rules = rules[bucket]
            if "opener" not in bucket_rules or not isinstance(bucket_rules["opener"], list):
                raise HTTPException(
                    status_code=400,
                    detail=f"Policy bucket '{bucket}' must have 'opener' array"
                )
            if "close" not in bucket_rules or not isinstance(bucket_rules["close"], list):
                raise HTTPException(
                    status_code=400,
                    detail=f"Policy bucket '{bucket}' must have 'close' array"
                )

        # Ensure config directory exists
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)

        # Save to file
        with open(CONFIG_PATH, "w") as f:
            json.dump(presets, f, indent=2)

        # Reload the service to pick up changes
        from services import quote_language_service
        quote_language_service._quote_language_service = None

        return {"status": "success", "message": "Presets updated successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving presets: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/select")
async def select_language(request: SelectLanguageRequest):
    """
    Test language selection with given parameters.

    Returns the selected language snippets based on the input criteria.
    Useful for testing and previewing language selection in the admin UI.
    """
    try:
        result = select_quote_language(
            eligible=request.eligible,
            quote_policy=request.quote_policy,
            goal=request.goal,
            segment=request.segment,
            rate_range_text=request.rate_range_text,
            state=request.state,
            duration_minutes=request.duration_minutes
        )
        return result
    except Exception as e:
        logger.error(f"Error selecting language: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/policy-buckets")
async def get_policy_buckets():
    """
    Get list of available policy buckets.
    """
    return {
        "buckets": [
            {
                "id": "range_only",
                "name": "Range Only",
                "description": "Use when borrower is eligible and we can provide an indicative rate range"
            },
            {
                "id": "ballpark",
                "name": "Ballpark",
                "description": "Use when we don't have enough detail to quote even a range"
            },
            {
                "id": "no_quote",
                "name": "No Quote",
                "description": "Use when we cannot or should not quote any numbers"
            }
        ]
    }


@router.get("/goals")
async def get_goals():
    """
    Get list of available goal types for overrides.
    """
    return {
        "goals": [
            {"id": "annual_mortgage_review", "name": "Annual Mortgage Review"},
            {"id": "rate_term_refi_review", "name": "Rate & Term Refi Review"},
            {"id": "cash_out_planning", "name": "Cash-Out Planning"},
            {"id": "purchase_preapproval", "name": "Purchase Pre-Approval"}
        ]
    }


@router.get("/segments")
async def get_segments():
    """
    Get list of available segment types for overrides.
    """
    return {
        "segments": [
            {"id": "arm_safety_review", "name": "ARM Safety Review"},
            {"id": "equity_strategy_review", "name": "Equity Strategy Review"},
            {"id": "mortgage_tune_up", "name": "Mortgage Tune-Up"},
            {"id": "rate_watch", "name": "Rate Watch"}
        ]
    }
