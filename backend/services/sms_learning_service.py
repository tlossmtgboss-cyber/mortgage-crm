import logging
import json
import re
from datetime import datetime, timezone
from typing import Optional, Dict, List
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)

STOP_WORDS = frozenset({
    'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
    'should', 'may', 'might', 'shall', 'can', 'need', 'dare', 'ought',
    'used', 'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by', 'from',
    'as', 'into', 'through', 'during', 'before', 'after', 'above', 'below',
    'between', 'out', 'off', 'over', 'under', 'again', 'further', 'then',
    'once', 'here', 'there', 'when', 'where', 'why', 'how', 'all', 'each',
    'every', 'both', 'few', 'more', 'most', 'other', 'some', 'such', 'no',
    'nor', 'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very',
    'just', 'because', 'but', 'and', 'or', 'if', 'while', 'about',
    'i', 'me', 'my', 'myself', 'we', 'our', 'you', 'your', 'he', 'him',
    'she', 'her', 'it', 'its', 'they', 'them', 'their', 'what', 'which',
    'who', 'whom', 'this', 'that', 'these', 'those', 'am', 'up', 'down',
    'ok', 'okay', 'yes', 'no', 'hi', 'hello', 'hey', 'thanks', 'thank',
    'please', 'lol', 'gonna', 'wanna', 'gotta',
})


def extract_keywords(message: str) -> List[str]:
    cleaned = re.sub(r'[^\w\s]', '', message.lower())
    words = cleaned.split()
    keywords = [w for w in words if w not in STOP_WORDS and len(w) > 1]
    return sorted(set(keywords))


def record_response(
    db: Session,
    organization_id: int,
    category: str,
    inbound_message: str,
    response_text: str,
    outcome: str,
    user_id: Optional[int] = None,
) -> dict:
    keywords = extract_keywords(inbound_message)
    keywords_json = json.dumps(keywords)

    try:
        existing = db.execute(
            text("""
                SELECT id, message_keywords, times_used, times_accepted,
                       times_edited, times_rejected, response_template
                FROM sms_response_patterns
                WHERE organization_id = :org_id
                  AND category = :category
                ORDER BY times_used DESC
            """),
            {"org_id": organization_id, "category": category},
        ).fetchall()
    except Exception as e:
        logger.warning("sms_response_patterns table may not exist: %s", e)
        return {}

    matched_row = None
    for row in existing:
        stored_kw = row[1] if isinstance(row[1], list) else json.loads(row[1] or "[]")
        if not stored_kw or not keywords:
            continue
        overlap = len(set(stored_kw) & set(keywords))
        shorter = min(len(stored_kw), len(keywords))
        if shorter > 0 and overlap / shorter >= 0.5:
            matched_row = row
            break

    now = datetime.now(timezone.utc)

    if matched_row:
        pattern_id = matched_row[0]
        new_used = matched_row[2] + 1
        new_accepted = matched_row[3] + (1 if outcome == "accepted" else 0)
        new_edited = matched_row[4] + (1 if outcome == "edited" else 0)
        new_rejected = matched_row[5] + (1 if outcome == "rejected" else 0)
        new_success = (new_accepted + new_edited * 0.5) / new_used if new_used > 0 else 0

        db.execute(
            text("""
                UPDATE sms_response_patterns
                SET times_used = :used,
                    times_accepted = :accepted,
                    times_edited = :edited,
                    times_rejected = :rejected,
                    success_rate = :rate,
                    last_used_at = :now,
                    updated_at = :now
                WHERE id = :id
            """),
            {
                "used": new_used,
                "accepted": new_accepted,
                "edited": new_edited,
                "rejected": new_rejected,
                "rate": round(new_success, 4),
                "now": now,
                "id": pattern_id,
            },
        )
        db.flush()

        return {
            "id": pattern_id,
            "organization_id": organization_id,
            "category": category,
            "message_keywords": keywords,
            "response_template": matched_row[6],
            "times_used": new_used,
            "times_accepted": new_accepted,
            "times_edited": new_edited,
            "times_rejected": new_rejected,
            "success_rate": round(new_success, 4),
            "updated": True,
        }

    initial_rate = 1.0 if outcome == "accepted" else (0.5 if outcome == "edited" else 0.0)

    result = db.execute(
        text("""
            INSERT INTO sms_response_patterns
                (organization_id, category, message_keywords, response_template,
                 times_used, times_accepted, times_edited, times_rejected,
                 success_rate, last_used_at, created_by_user_id, created_at, updated_at)
            VALUES
                (:org_id, :category, :keywords::jsonb, :template,
                 1, :accepted, :edited, :rejected,
                 :rate, :now, :user_id, :now, :now)
            RETURNING id
        """),
        {
            "org_id": organization_id,
            "category": category,
            "keywords": keywords_json,
            "template": response_text,
            "accepted": 1 if outcome == "accepted" else 0,
            "edited": 1 if outcome == "edited" else 0,
            "rejected": 1 if outcome == "rejected" else 0,
            "rate": round(initial_rate, 4),
            "now": now,
            "user_id": user_id,
        },
    )
    new_id = result.scalar()
    db.flush()

    return {
        "id": new_id,
        "organization_id": organization_id,
        "category": category,
        "message_keywords": keywords,
        "response_template": response_text,
        "times_used": 1,
        "times_accepted": 1 if outcome == "accepted" else 0,
        "times_edited": 1 if outcome == "edited" else 0,
        "times_rejected": 1 if outcome == "rejected" else 0,
        "success_rate": round(initial_rate, 4),
        "updated": False,
    }


def find_matching_patterns(
    db: Session,
    organization_id: int,
    category: str,
    inbound_message: str,
    limit: int = 5,
) -> List[dict]:
    keywords = extract_keywords(inbound_message)
    if not keywords:
        return []

    keywords_json = json.dumps(keywords)

    try:
        rows = db.execute(
            text("""
                WITH input_kw AS (
                    SELECT jsonb_array_elements_text(:keywords::jsonb) AS kw
                ),
                pattern_matches AS (
                    SELECT
                        p.id,
                        p.response_template,
                        p.success_rate,
                        p.times_used,
                        p.times_accepted,
                        p.message_keywords,
                        (
                            SELECT COUNT(*)
                            FROM jsonb_array_elements_text(p.message_keywords) pk
                            INNER JOIN input_kw ik ON pk.value = ik.kw
                        ) AS overlap_count,
                        jsonb_array_length(p.message_keywords) AS stored_count
                    FROM sms_response_patterns p
                    WHERE p.organization_id = :org_id
                      AND p.category = :category
                      AND jsonb_array_length(p.message_keywords) > 0
                )
                SELECT id, response_template, success_rate, times_used, times_accepted,
                       message_keywords, overlap_count, stored_count
                FROM pattern_matches
                WHERE overlap_count::float / LEAST(stored_count, :input_count)::float >= 0.5
                ORDER BY success_rate DESC, times_used DESC
                LIMIT :lim
            """),
            {
                "keywords": keywords_json,
                "org_id": organization_id,
                "category": category,
                "input_count": len(keywords),
                "lim": limit,
            },
        ).fetchall()
    except Exception as e:
        logger.warning("Failed to find matching patterns: %s", e)
        return []

    return [
        {
            "template": row[1],
            "success_rate": row[2],
            "times_used": row[3],
            "times_accepted": row[4],
        }
        for row in rows
    ]


def get_best_template(
    db: Session,
    organization_id: int,
    category: str,
    inbound_message: str,
) -> Optional[str]:
    keywords = extract_keywords(inbound_message)
    if not keywords:
        return None

    keywords_json = json.dumps(keywords)

    try:
        row = db.execute(
            text("""
                WITH pattern_matches AS (
                    SELECT
                        p.response_template,
                        p.success_rate,
                        p.times_used,
                        (
                            SELECT COUNT(*)
                            FROM jsonb_array_elements_text(p.message_keywords) pk
                            WHERE pk.value = ANY(:keywords_arr::text[])
                        ) AS overlap_count,
                        jsonb_array_length(p.message_keywords) AS stored_count
                    FROM sms_response_patterns p
                    WHERE p.organization_id = :org_id
                      AND p.category = :category
                      AND p.success_rate > 0.6
                      AND p.times_used >= 3
                      AND jsonb_array_length(p.message_keywords) > 0
                )
                SELECT response_template
                FROM pattern_matches
                WHERE overlap_count::float / LEAST(stored_count, :input_count)::float >= 0.5
                ORDER BY success_rate DESC, times_used DESC
                LIMIT 1
            """),
            {
                "keywords_arr": keywords,
                "org_id": organization_id,
                "category": category,
                "input_count": len(keywords),
            },
        ).fetchone()
    except Exception as e:
        logger.warning("Failed to get best template: %s", e)
        return None

    return row[0] if row else None


def cleanup_stale_patterns(
    db: Session,
    organization_id: Optional[int] = None,
    min_success_rate: float = 0.1,
    min_uses: int = 5,
) -> int:
    try:
        params: Dict = {"min_rate": min_success_rate, "min_uses": min_uses}
        org_filter = ""
        if organization_id is not None:
            org_filter = "AND organization_id = :org_id"
            params["org_id"] = organization_id

        result = db.execute(
            text(f"""
                DELETE FROM sms_response_patterns
                WHERE times_used >= :min_uses
                  AND success_rate < :min_rate
                  {org_filter}
            """),
            params,
        )
        db.flush()
        return result.rowcount
    except Exception as e:
        logger.warning("Failed to cleanup stale patterns: %s", e)
        return 0


def get_pattern_stats(db: Session, organization_id: int) -> dict:
    try:
        total = db.execute(
            text("""
                SELECT COUNT(*) FROM sms_response_patterns
                WHERE organization_id = :org_id
            """),
            {"org_id": organization_id},
        ).scalar() or 0

        by_category_rows = db.execute(
            text("""
                SELECT category, COUNT(*) FROM sms_response_patterns
                WHERE organization_id = :org_id
                GROUP BY category
                ORDER BY COUNT(*) DESC
            """),
            {"org_id": organization_id},
        ).fetchall()

        avg_rate = db.execute(
            text("""
                SELECT COALESCE(AVG(success_rate), 0) FROM sms_response_patterns
                WHERE organization_id = :org_id
            """),
            {"org_id": organization_id},
        ).scalar()

        top_rows = db.execute(
            text("""
                SELECT id, category, response_template, success_rate, times_used
                FROM sms_response_patterns
                WHERE organization_id = :org_id
                ORDER BY success_rate DESC, times_used DESC
                LIMIT 5
            """),
            {"org_id": organization_id},
        ).fetchall()
    except Exception as e:
        logger.warning("Failed to get pattern stats: %s", e)
        return {"total_patterns": 0, "by_category": {}, "avg_success_rate": 0, "top_patterns": []}

    return {
        "total_patterns": total,
        "by_category": {row[0]: row[1] for row in by_category_rows},
        "avg_success_rate": round(float(avg_rate), 4),
        "top_patterns": [
            {
                "id": row[0],
                "category": row[1],
                "response_template": row[2],
                "success_rate": row[3],
                "times_used": row[4],
            }
            for row in top_rows
        ],
    }
