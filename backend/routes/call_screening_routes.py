"""
Call Screening Management API Routes

Endpoints for managing blocklist/whitelist and viewing screening statistics.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text, func
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from pydantic import BaseModel
import logging

from database import get_db
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


def _get_current_user():
    """Lazy import auth dependency for router-level protection."""
    from auth.dependencies import get_current_user_flexible
    return get_current_user_flexible

router = APIRouter(
    prefix="/api/v1/call-screening", tags=["call-screening"],
    dependencies=[Depends(_get_current_user())],
)


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class BlocklistEntry(BaseModel):
    phone_number: str
    reason: str
    source: str = "manual"
    spam_score: Optional[int] = None
    expires_days: Optional[int] = None  # None = permanent


class WhitelistEntry(BaseModel):
    phone_number: str
    name: str
    category: str  # client, lead, referral_partner, vip, team
    source: str = "manual"
    lead_id: Optional[int] = None
    notes: Optional[str] = None
    priority: int = 0


class ScreeningStats(BaseModel):
    period_days: int
    total_calls: int
    allowed_calls: int
    blocked_calls: int
    screened_calls: int
    lookups_performed: int
    lookup_cost_cents: int
    whitelist_matches: int
    blocklist_matches: int


# ============================================================================
# BLOCKLIST MANAGEMENT
# ============================================================================

@router.get("/blocklist")
async def get_blocklist(
    db: Session = Depends(get_db),
    active_only: bool = True,
    limit: int = Query(default=100, le=500),
    offset: int = 0
):
    """Get blocklist entries."""
    try:
        filters = []
        if active_only:
            filters.append("is_active = true")
            filters.append("(expires_at IS NULL OR expires_at > NOW())")

        where_clause = " AND ".join(filters) if filters else "1=1"

        sql = """
            SELECT
                id, phone_number, reason, source, spam_score,
                blocked_at, blocked_by, expires_at, is_active,
                call_attempts_since_block, created_at
            FROM phone_blocklist
            WHERE """ + where_clause + """
            ORDER BY blocked_at DESC
            LIMIT :limit OFFSET :offset
        """
        result = db.execute(text(sql), {"limit": limit, "offset": offset})

        entries = []
        for row in result.fetchall():
            entries.append({
                "id": row[0],
                "phone_number": row[1],
                "reason": row[2],
                "source": row[3],
                "spam_score": row[4],
                "blocked_at": row[5].isoformat() if row[5] else None,
                "blocked_by": row[6],
                "expires_at": row[7].isoformat() if row[7] else None,
                "is_active": row[8],
                "call_attempts_since_block": row[9],
                "created_at": row[10].isoformat() if row[10] else None,
            })

        # Get total count
        count_sql = "SELECT COUNT(*) FROM phone_blocklist WHERE " + where_clause
        count_result = db.execute(text(count_sql))
        total = count_result.scalar()

        return {
            "entries": entries,
            "total": total,
            "limit": limit,
            "offset": offset
        }

    except SQLAlchemyError as e:
        logger.error(f"Error getting blocklist: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/blocklist")
async def add_to_blocklist(
    entry: BlocklistEntry,
    db: Session = Depends(get_db)
):
    """Add a phone number to the blocklist."""
    try:
        from services.call_screening_service import add_to_blocklist

        await add_to_blocklist(
            db=db,
            phone=entry.phone_number,
            reason=entry.reason,
            source=entry.source,
            spam_score=entry.spam_score,
            expires_days=entry.expires_days
        )

        return {
            "success": True,
            "message": f"Added {entry.phone_number} to blocklist",
            "phone_number": entry.phone_number
        }

    except Exception as e:
        logger.error(f"Error adding to blocklist: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/blocklist/{phone_number}")
async def remove_from_blocklist(
    phone_number: str,
    db: Session = Depends(get_db)
):
    """Remove a phone number from the blocklist (deactivate)."""
    try:
        # Normalize phone number
        import re
        phone = re.sub(r'[^\d+]', '', phone_number)
        if len(phone) == 10:
            phone = f"+1{phone}"
        elif not phone.startswith("+"):
            phone = f"+{phone}"

        result = db.execute(text("""
            UPDATE phone_blocklist
            SET is_active = false, updated_at = NOW()
            WHERE phone_number = :phone
            RETURNING id
        """), {"phone": phone})

        row = result.fetchone()
        db.commit()

        if row:
            return {
                "success": True,
                "message": f"Removed {phone} from blocklist",
                "phone_number": phone
            }
        else:
            raise HTTPException(status_code=404, detail="Phone number not found in blocklist")

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Error removing from blocklist: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# WHITELIST MANAGEMENT
# ============================================================================

@router.get("/whitelist")
async def get_whitelist(
    db: Session = Depends(get_db),
    category: Optional[str] = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0
):
    """Get whitelist entries."""
    try:
        filters = ["1=1"]
        params = {"limit": limit, "offset": offset}

        if category:
            filters.append("category = :category")
            params["category"] = category

        where_clause = " AND ".join(filters)

        sql = """
            SELECT
                id, phone_number, name, category, source,
                lead_id, user_id, added_at, added_by,
                notes, priority, created_at
            FROM phone_whitelist
            WHERE """ + where_clause + """
            ORDER BY priority DESC, added_at DESC
            LIMIT :limit OFFSET :offset
        """
        result = db.execute(text(sql), params)

        entries = []
        for row in result.fetchall():
            entries.append({
                "id": row[0],
                "phone_number": row[1],
                "name": row[2],
                "category": row[3],
                "source": row[4],
                "lead_id": row[5],
                "user_id": row[6],
                "added_at": row[7].isoformat() if row[7] else None,
                "added_by": row[8],
                "notes": row[9],
                "priority": row[10],
                "created_at": row[11].isoformat() if row[11] else None,
            })

        # Get total count
        count_sql = "SELECT COUNT(*) FROM phone_whitelist WHERE " + where_clause
        count_result = db.execute(text(count_sql), params)
        total = count_result.scalar()

        return {
            "entries": entries,
            "total": total,
            "limit": limit,
            "offset": offset
        }

    except SQLAlchemyError as e:
        logger.error(f"Error getting whitelist: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/whitelist")
async def add_to_whitelist(
    entry: WhitelistEntry,
    db: Session = Depends(get_db)
):
    """Add a phone number to the whitelist."""
    try:
        from services.call_screening_service import add_to_whitelist

        await add_to_whitelist(
            db=db,
            phone=entry.phone_number,
            name=entry.name,
            category=entry.category,
            source=entry.source,
            lead_id=entry.lead_id
        )

        return {
            "success": True,
            "message": f"Added {entry.phone_number} to whitelist",
            "phone_number": entry.phone_number
        }

    except Exception as e:
        logger.error(f"Error adding to whitelist: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/whitelist/{phone_number}")
async def remove_from_whitelist(
    phone_number: str,
    db: Session = Depends(get_db)
):
    """Remove a phone number from the whitelist."""
    try:
        # Normalize phone number
        import re
        phone = re.sub(r'[^\d+]', '', phone_number)
        if len(phone) == 10:
            phone = f"+1{phone}"
        elif not phone.startswith("+"):
            phone = f"+{phone}"

        result = db.execute(text("""
            DELETE FROM phone_whitelist
            WHERE phone_number = :phone
            RETURNING id
        """), {"phone": phone})

        row = result.fetchone()
        db.commit()

        if row:
            return {
                "success": True,
                "message": f"Removed {phone} from whitelist",
                "phone_number": phone
            }
        else:
            raise HTTPException(status_code=404, detail="Phone number not found in whitelist")

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Error removing from whitelist: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# SCREENING STATISTICS
# ============================================================================

@router.get("/stats")
async def get_screening_stats(
    db: Session = Depends(get_db),
    days: int = Query(default=30, le=365)
):
    """Get call screening statistics."""
    try:
        result = db.execute(text("""
            SELECT
                COUNT(*) as total_calls,
                COUNT(CASE WHEN screening_decision = 'allow' THEN 1 END) as allowed_calls,
                COUNT(CASE WHEN screening_decision = 'block' THEN 1 END) as blocked_calls,
                COUNT(CASE WHEN screening_decision = 'screen' THEN 1 END) as screened_calls,
                COUNT(CASE WHEN lookup_performed = true THEN 1 END) as lookups_performed,
                COALESCE(SUM(lookup_cost_cents), 0) as lookup_cost_cents,
                COUNT(CASE WHEN decision_reason LIKE 'whitelist%' THEN 1 END) as whitelist_matches,
                COUNT(CASE WHEN decision_reason LIKE 'blocklist%' THEN 1 END) as blocklist_matches
            FROM call_screening_log
            WHERE created_at >= CURRENT_DATE - :days
        """), {"days": days})

        row = result.fetchone()

        return {
            "period_days": days,
            "total_calls": row[0] or 0,
            "allowed_calls": row[1] or 0,
            "blocked_calls": row[2] or 0,
            "screened_calls": row[3] or 0,
            "lookups_performed": row[4] or 0,
            "lookup_cost_cents": row[5] or 0,
            "lookup_cost_dollars": round((row[5] or 0) / 100, 2),
            "whitelist_matches": row[6] or 0,
            "blocklist_matches": row[7] or 0,
            "block_rate": round((row[2] or 0) / (row[0] or 1) * 100, 1),
            "screen_rate": round((row[3] or 0) / (row[0] or 1) * 100, 1),
        }

    except Exception as e:
        logger.error(f"Error getting screening stats: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/log")
async def get_screening_log(
    db: Session = Depends(get_db),
    decision: Optional[str] = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0
):
    """Get detailed screening log."""
    try:
        filters = ["1=1"]
        params = {"limit": limit, "offset": offset}

        if decision:
            filters.append("screening_decision = :decision")
            params["decision"] = decision

        where_clause = " AND ".join(filters)

        sql = """
            SELECT
                id, call_sid, phone_number, screening_decision,
                decision_reason, lookup_performed, lookup_cost_cents,
                screening_duration_ms, caller_stated_name, caller_stated_reason,
                connected_to_ai, created_at
            FROM call_screening_log
            WHERE """ + where_clause + """
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """
        result = db.execute(text(sql), params)

        entries = []
        for row in result.fetchall():
            entries.append({
                "id": row[0],
                "call_sid": row[1],
                "phone_number": row[2],
                "decision": row[3],
                "reason": row[4],
                "lookup_performed": row[5],
                "lookup_cost_cents": row[6],
                "duration_ms": row[7],
                "caller_name": row[8],
                "caller_reason": row[9],
                "connected_to_ai": row[10],
                "created_at": row[11].isoformat() if row[11] else None,
            })

        # Get total count
        count_sql = "SELECT COUNT(*) FROM call_screening_log WHERE " + where_clause
        count_result = db.execute(text(count_sql), params)
        total = count_result.scalar()

        return {
            "entries": entries,
            "total": total,
            "limit": limit,
            "offset": offset
        }

    except SQLAlchemyError as e:
        logger.error(f"Error getting screening log: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# LOOKUP CACHE MANAGEMENT
# ============================================================================

@router.get("/lookup-cache")
async def get_lookup_cache(
    db: Session = Depends(get_db),
    limit: int = Query(default=100, le=500),
    offset: int = 0
):
    """Get cached phone lookup results."""
    try:
        result = db.execute(text("""
            SELECT
                phone_number, carrier_name, carrier_type, line_type,
                caller_name, caller_type, country_code, spam_score,
                risk_level, cached_at, expires_at
            FROM phone_lookup_cache
            WHERE expires_at > NOW()
            ORDER BY cached_at DESC
            LIMIT :limit OFFSET :offset
        """), {"limit": limit, "offset": offset})

        entries = []
        for row in result.fetchall():
            entries.append({
                "phone_number": row[0],
                "carrier_name": row[1],
                "carrier_type": row[2],
                "line_type": row[3],
                "caller_name": row[4],
                "caller_type": row[5],
                "country_code": row[6],
                "spam_score": row[7],
                "risk_level": row[8],
                "cached_at": row[9].isoformat() if row[9] else None,
                "expires_at": row[10].isoformat() if row[10] else None,
            })

        return {
            "entries": entries,
            "count": len(entries),
            "limit": limit,
            "offset": offset
        }

    except Exception as e:
        logger.error(f"Error getting lookup cache: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/lookup-cache/{phone_number}")
async def clear_lookup_cache(
    phone_number: str,
    db: Session = Depends(get_db)
):
    """Clear cached lookup for a phone number."""
    try:
        # Normalize phone number
        import re
        phone = re.sub(r'[^\d+]', '', phone_number)
        if len(phone) == 10:
            phone = f"+1{phone}"
        elif not phone.startswith("+"):
            phone = f"+{phone}"

        result = db.execute(text("""
            DELETE FROM phone_lookup_cache
            WHERE phone_number = :phone
            RETURNING phone_number
        """), {"phone": phone})

        row = result.fetchone()
        db.commit()

        if row:
            return {
                "success": True,
                "message": f"Cleared cache for {phone}",
                "phone_number": phone
            }
        else:
            return {
                "success": True,
                "message": f"No cache entry found for {phone}",
                "phone_number": phone
            }

    except SQLAlchemyError as e:
        logger.error(f"Error clearing lookup cache: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/lookup-cache/clear-expired")
async def clear_expired_cache(db: Session = Depends(get_db)):
    """Clear all expired lookup cache entries."""
    try:
        result = db.execute(text("""
            DELETE FROM phone_lookup_cache
            WHERE expires_at <= NOW()
        """))
        db.commit()

        return {
            "success": True,
            "message": f"Cleared {result.rowcount} expired cache entries",
            "cleared_count": result.rowcount
        }

    except SQLAlchemyError as e:
        logger.error(f"Error clearing expired cache: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# PHONE LOOKUP (MANUAL)
# ============================================================================

@router.get("/lookup/{phone_number}")
async def lookup_phone(
    phone_number: str,
    db: Session = Depends(get_db),
    force_refresh: bool = False
):
    """
    Perform a phone lookup (checks cache first unless force_refresh=true).

    Cost: ~$0.05 per lookup if not cached.
    """
    try:
        from services.call_screening_service import CallScreeningService
        from integrations.phone_lookup_service import get_phone_lookup_service
        phone_lookup_service = get_phone_lookup_service()

        # Normalize phone number
        import re
        phone = re.sub(r'[^\d+]', '', phone_number)
        if len(phone) == 10:
            phone = f"+1{phone}"
        elif not phone.startswith("+"):
            phone = f"+{phone}"

        # Check cache first (unless force refresh)
        if not force_refresh:
            screening_service = CallScreeningService(db)
            cached = await screening_service._check_lookup_cache(phone)
            if cached:
                return {
                    "phone_number": phone,
                    "cached": True,
                    **cached
                }

        # Perform lookup
        if not phone_lookup_service.is_enabled():
            raise HTTPException(
                status_code=503,
                detail="Phone Lookup service is not enabled"
            )

        result = await phone_lookup_service.lookup_phone(phone)

        # Cache the result
        if not result.error:
            screening_service = CallScreeningService(db)
            await screening_service._cache_lookup_result(phone, {
                "carrier_name": result.carrier_name,
                "carrier_type": result.carrier_type,
                "line_type": result.line_type,
                "caller_name": result.caller_name,
                "caller_type": result.caller_type,
                "country_code": result.country_code,
                "spam_score": result.spam_score,
                "risk_level": result.risk_level,
            })

        return {
            "phone_number": result.phone_number,
            "valid": result.valid,
            "cached": False,
            "carrier_name": result.carrier_name,
            "carrier_type": result.carrier_type,
            "line_type": result.line_type,
            "caller_name": result.caller_name,
            "caller_type": result.caller_type,
            "country_code": result.country_code,
            "spam_score": result.spam_score,
            "risk_level": result.risk_level,
            "error": result.error,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error performing lookup: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
