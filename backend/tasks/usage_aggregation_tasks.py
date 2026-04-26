"""
Usage Aggregation Tasks

Daily background tasks that aggregate raw usage data into snapshots
for the Usage Intelligence system.

Run these tasks daily (preferably at midnight UTC) via APScheduler or cron:
    - aggregate_daily_user_usage(): Creates UserUsageSnapshots
    - aggregate_daily_team_usage(): Creates TeamUsageSnapshots
    - aggregate_daily_org_usage(): Creates OrgUsageSnapshots

Usage:
    from tasks.usage_aggregation_tasks import run_daily_aggregation
    run_daily_aggregation(db_session, organization_id=org_id)

When run as a CLI script, iterates over all organizations automatically.
"""

import os
import sys
import logging
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Any, Optional
from collections import defaultdict

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# =============================================================================
# COMMUNICATION SERVICE COSTS (fetch from ServiceUsageRecord)
# =============================================================================

def get_communication_costs_for_user(
    db: Session,
    user_id: int,
    snapshot_date: date,
    organization_id: int
) -> Dict[str, Any]:
    """
    Get SMS, Voice, and Email costs for a user on a specific date.
    Pulls from service_usage_records table.
    """
    result = db.execute(text("""
        SELECT
            sp.category,
            COALESCE(SUM(sur.quantity), 0) as quantity,
            COALESCE(SUM(sur.total_cost), 0) as total_cost
        FROM service_usage_records sur
        JOIN service_providers sp ON sp.id = sur.service_provider_id
        WHERE sur.user_id = :user_id
        AND sur.organization_id = :organization_id
        AND sur.usage_date = :snapshot_date
        AND sp.category IN ('communications', 'email', 'storage')
        GROUP BY sp.category, sp.provider_type
    """), {
        "user_id": user_id,
        "organization_id": organization_id,
        "snapshot_date": snapshot_date
    }).fetchall()

    costs = {
        "sms_cost": Decimal("0"),
        "sms_segments": 0,
        "voice_cost": Decimal("0"),
        "voice_minutes": Decimal("0"),
        "email_cost": Decimal("0"),
        "email_count": 0,
        "storage_cost": Decimal("0"),
        "storage_gb": Decimal("0"),
        "storage_requests": 0
    }

    for row in result:
        category = row[0]
        quantity = Decimal(str(row[1]))
        total_cost = Decimal(str(row[2]))

        if category == "communications":
            # Need to distinguish SMS from Voice via provider_type
            # For now, assume Telnyx SMS
            costs["sms_cost"] += total_cost
            costs["sms_segments"] += int(quantity)
        elif category == "email":
            costs["email_cost"] += total_cost
            costs["email_count"] += int(quantity)
        elif category == "storage":
            costs["storage_cost"] += total_cost
            costs["storage_gb"] += quantity

    return costs


# =============================================================================
# USER USAGE AGGREGATION
# =============================================================================

def aggregate_daily_user_usage(
    db: Session,
    organization_id: int,
    snapshot_date: date = None
) -> Dict[str, Any]:
    """
    Aggregate all usage data for each user into UserUsageSnapshot records.
    Creates one snapshot per active user per day.

    Args:
        db: Database session
        organization_id: Organization to aggregate for
        snapshot_date: Date to aggregate (defaults to yesterday)

    Returns:
        Dict with summary of snapshots created
    """
    if snapshot_date is None:
        snapshot_date = date.today() - timedelta(days=1)

    logger.info(f"Starting user usage aggregation for {snapshot_date}")

    # Get all users with AI activity on this date
    active_users = db.execute(text("""
        SELECT DISTINCT user_id
        FROM ai_token_usage_log
        WHERE organization_id = :organization_id
        AND DATE(timestamp) = :snapshot_date
    """), {
        "organization_id": organization_id,
        "snapshot_date": snapshot_date
    }).fetchall()

    user_ids = [row[0] for row in active_users]
    logger.info(f"Found {len(user_ids)} users with AI activity")

    # Also get users with service usage (SMS, Voice, Email)
    service_users = db.execute(text("""
        SELECT DISTINCT user_id
        FROM service_usage_records
        WHERE organization_id = :organization_id
        AND usage_date = :snapshot_date
        AND user_id IS NOT NULL
    """), {
        "organization_id": organization_id,
        "snapshot_date": snapshot_date
    }).fetchall()

    for row in service_users:
        if row[0] not in user_ids:
            user_ids.append(row[0])

    logger.info(f"Total users to aggregate: {len(user_ids)}")

    snapshots_created = 0
    snapshots_updated = 0
    total_cost = Decimal("0")

    for user_id in user_ids:
        try:
            # Get AI token usage for user
            ai_data = db.execute(text("""
                SELECT
                    COALESCE(SUM(input_tokens), 0) as input_tokens,
                    COALESCE(SUM(output_tokens), 0) as output_tokens,
                    COALESCE(SUM(total_cost), 0) as total_cost,
                    COUNT(*) as request_count
                FROM ai_token_usage_log
                WHERE user_id = :user_id
                AND organization_id = :organization_id
                AND DATE(timestamp) = :snapshot_date
            """), {
                "user_id": user_id,
                "organization_id": organization_id,
                "snapshot_date": snapshot_date
            }).fetchone()

            # Get cost by model
            model_costs = db.execute(text("""
                SELECT
                    model,
                    COALESCE(SUM(total_cost), 0) as cost
                FROM ai_token_usage_log
                WHERE user_id = :user_id
                AND organization_id = :organization_id
                AND DATE(timestamp) = :snapshot_date
                GROUP BY model
            """), {
                "user_id": user_id,
                "organization_id": organization_id,
                "snapshot_date": snapshot_date
            }).fetchall()

            cost_by_model = {row[0]: float(row[1]) for row in model_costs}

            # Get cost by feature
            feature_costs = db.execute(text("""
                SELECT
                    COALESCE(feature, 'unknown') as feature,
                    COALESCE(SUM(total_cost), 0) as cost
                FROM ai_token_usage_log
                WHERE user_id = :user_id
                AND organization_id = :organization_id
                AND DATE(timestamp) = :snapshot_date
                GROUP BY feature
            """), {
                "user_id": user_id,
                "organization_id": organization_id,
                "snapshot_date": snapshot_date
            }).fetchall()

            cost_by_feature = {row[0]: float(row[1]) for row in feature_costs}

            # Get communication costs
            comm_costs = get_communication_costs_for_user(
                db, user_id, snapshot_date, organization_id
            )

            # Calculate total daily cost
            ai_cost = Decimal(str(ai_data[2])) if ai_data[2] else Decimal("0")
            user_total_cost = (
                ai_cost +
                comm_costs["sms_cost"] +
                comm_costs["voice_cost"] +
                comm_costs["email_cost"] +
                comm_costs["storage_cost"]
            )

            # Check if snapshot already exists
            existing = db.execute(text("""
                SELECT id FROM user_usage_snapshots
                WHERE organization_id = :organization_id
                AND user_id = :user_id
                AND snapshot_date = :snapshot_date
            """), {
                "organization_id": organization_id,
                "user_id": user_id,
                "snapshot_date": snapshot_date
            }).fetchone()

            if existing:
                # Update existing snapshot
                db.execute(text("""
                    UPDATE user_usage_snapshots SET
                        ai_tokens_cost = :ai_cost,
                        ai_tokens_input = :input_tokens,
                        ai_tokens_output = :output_tokens,
                        sms_cost = :sms_cost,
                        sms_segments = :sms_segments,
                        voice_cost = :voice_cost,
                        voice_minutes = :voice_minutes,
                        email_cost = :email_cost,
                        email_count = :email_count,
                        storage_cost = :storage_cost,
                        storage_gb = :storage_gb,
                        storage_requests = :storage_requests,
                        total_cost = :total_cost,
                        cost_by_model = :cost_by_model,
                        cost_by_feature = :cost_by_feature,
                        ai_request_count = :ai_request_count,
                        updated_at = :updated_at
                    WHERE id = :id
                """), {
                    "id": existing[0],
                    "ai_cost": str(ai_cost),
                    "input_tokens": int(ai_data[0]) if ai_data[0] else 0,
                    "output_tokens": int(ai_data[1]) if ai_data[1] else 0,
                    "sms_cost": str(comm_costs["sms_cost"]),
                    "sms_segments": comm_costs["sms_segments"],
                    "voice_cost": str(comm_costs["voice_cost"]),
                    "voice_minutes": str(comm_costs["voice_minutes"]),
                    "email_cost": str(comm_costs["email_cost"]),
                    "email_count": comm_costs["email_count"],
                    "storage_cost": str(comm_costs["storage_cost"]),
                    "storage_gb": str(comm_costs["storage_gb"]),
                    "storage_requests": comm_costs["storage_requests"],
                    "total_cost": str(user_total_cost),
                    "cost_by_model": cost_by_model,
                    "cost_by_feature": cost_by_feature,
                    "ai_request_count": int(ai_data[3]) if ai_data[3] else 0,
                    "updated_at": datetime.now(timezone.utc)
                })
                snapshots_updated += 1
            else:
                # Create new snapshot
                import uuid
                db.execute(text("""
                    INSERT INTO user_usage_snapshots (
                        id, organization_id, user_id, snapshot_date,
                        ai_tokens_cost, ai_tokens_input, ai_tokens_output,
                        sms_cost, sms_segments, voice_cost, voice_minutes,
                        email_cost, email_count, storage_cost, storage_gb, storage_requests,
                        infrastructure_cost, total_cost,
                        cost_by_model, cost_by_feature, ai_request_count
                    ) VALUES (
                        :id, :organization_id, :user_id, :snapshot_date,
                        :ai_cost, :input_tokens, :output_tokens,
                        :sms_cost, :sms_segments, :voice_cost, :voice_minutes,
                        :email_cost, :email_count, :storage_cost, :storage_gb, :storage_requests,
                        :infrastructure_cost, :total_cost,
                        :cost_by_model, :cost_by_feature, :ai_request_count
                    )
                """), {
                    "id": str(uuid.uuid4()),
                    "organization_id": organization_id,
                    "user_id": user_id,
                    "snapshot_date": snapshot_date,
                    "ai_cost": str(ai_cost),
                    "input_tokens": int(ai_data[0]) if ai_data[0] else 0,
                    "output_tokens": int(ai_data[1]) if ai_data[1] else 0,
                    "sms_cost": str(comm_costs["sms_cost"]),
                    "sms_segments": comm_costs["sms_segments"],
                    "voice_cost": str(comm_costs["voice_cost"]),
                    "voice_minutes": str(comm_costs["voice_minutes"]),
                    "email_cost": str(comm_costs["email_cost"]),
                    "email_count": comm_costs["email_count"],
                    "storage_cost": str(comm_costs["storage_cost"]),
                    "storage_gb": str(comm_costs["storage_gb"]),
                    "storage_requests": comm_costs["storage_requests"],
                    "infrastructure_cost": "0",  # Calculated separately
                    "total_cost": str(user_total_cost),
                    "cost_by_model": cost_by_model,
                    "cost_by_feature": cost_by_feature,
                    "ai_request_count": int(ai_data[3]) if ai_data[3] else 0
                })
                snapshots_created += 1

            total_cost += user_total_cost

        except Exception as e:
            logger.error(f"Failed to aggregate user {user_id}: {e}")
            continue

    db.commit()

    summary = {
        "snapshot_date": str(snapshot_date),
        "organization_id": organization_id,
        "users_processed": len(user_ids),
        "snapshots_created": snapshots_created,
        "snapshots_updated": snapshots_updated,
        "total_cost": float(total_cost)
    }

    logger.info(f"User aggregation complete: {summary}")
    return summary


# =============================================================================
# TEAM USAGE AGGREGATION
# =============================================================================

def aggregate_daily_team_usage(
    db: Session,
    organization_id: int,
    snapshot_date: date = None
) -> Dict[str, Any]:
    """
    Aggregate UserUsageSnapshots into TeamUsageSnapshots.
    Rolls up user data by team.
    """
    if snapshot_date is None:
        snapshot_date = date.today() - timedelta(days=1)

    logger.info(f"Starting team usage aggregation for {snapshot_date}")

    # Get all teams with user activity
    # Join with users table to get team assignments
    teams = db.execute(text("""
        SELECT DISTINCT u.team_id
        FROM user_usage_snapshots uus
        JOIN users u ON u.id = uus.user_id
        WHERE uus.organization_id = :organization_id
        AND uus.snapshot_date = :snapshot_date
        AND u.team_id IS NOT NULL
    """), {
        "organization_id": organization_id,
        "snapshot_date": snapshot_date
    }).fetchall()

    team_ids = [row[0] for row in teams if row[0]]
    logger.info(f"Found {len(team_ids)} teams to aggregate")

    snapshots_created = 0
    snapshots_updated = 0
    total_cost = Decimal("0")

    for team_id in team_ids:
        try:
            # Aggregate user snapshots for this team
            team_data = db.execute(text("""
                SELECT
                    COUNT(DISTINCT uus.user_id) as user_count,
                    COALESCE(SUM(uus.total_cost), 0) as total_cost,
                    COALESCE(SUM(uus.ai_tokens_cost), 0) as ai_cost,
                    COALESCE(SUM(uus.sms_cost), 0) as sms_cost,
                    COALESCE(SUM(uus.voice_cost), 0) as voice_cost,
                    COALESCE(SUM(uus.email_cost), 0) as email_cost,
                    COALESCE(SUM(uus.storage_cost), 0) as storage_cost,
                    COALESCE(SUM(uus.infrastructure_cost), 0) as infrastructure_cost
                FROM user_usage_snapshots uus
                JOIN users u ON u.id = uus.user_id
                WHERE uus.organization_id = :organization_id
                AND uus.snapshot_date = :snapshot_date
                AND u.team_id = :team_id
            """), {
                "organization_id": organization_id,
                "snapshot_date": snapshot_date,
                "team_id": team_id
            }).fetchone()

            # Get top users for this team
            top_users = db.execute(text("""
                SELECT
                    uus.user_id,
                    COALESCE(es.full_name, u.email) AS name,
                    uus.total_cost
                FROM user_usage_snapshots uus
                JOIN users u ON u.id = uus.user_id
                LEFT JOIN email_signatures es ON es.user_id = u.id
                WHERE uus.organization_id = :organization_id
                AND uus.snapshot_date = :snapshot_date
                AND u.team_id = :team_id
                ORDER BY uus.total_cost DESC
                LIMIT 5
            """), {
                "organization_id": organization_id,
                "snapshot_date": snapshot_date,
                "team_id": team_id
            }).fetchall()

            top_users_list = [
                {"user_id": row[0], "name": row[1], "cost": float(row[2])}
                for row in top_users
            ]

            # Build cost breakdown
            communications_cost = (
                Decimal(str(team_data[3])) +
                Decimal(str(team_data[4])) +
                Decimal(str(team_data[5]))
            )

            cost_breakdown = {
                "by_category": {
                    "ai": float(team_data[2]),
                    "sms": float(team_data[3]),
                    "voice": float(team_data[4]),
                    "email": float(team_data[5]),
                    "storage": float(team_data[6]),
                    "infrastructure": float(team_data[7])
                }
            }

            team_total = Decimal(str(team_data[1]))

            # Check if snapshot exists
            existing = db.execute(text("""
                SELECT id FROM team_usage_snapshots
                WHERE organization_id = :organization_id
                AND team_id = :team_id
                AND snapshot_date = :snapshot_date
            """), {
                "organization_id": organization_id,
                "team_id": team_id,
                "snapshot_date": snapshot_date
            }).fetchone()

            if existing:
                db.execute(text("""
                    UPDATE team_usage_snapshots SET
                        total_cost = :total_cost,
                        user_count = :user_count,
                        ai_tokens_cost = :ai_cost,
                        communications_cost = :communications_cost,
                        storage_cost = :storage_cost,
                        infrastructure_cost = :infrastructure_cost,
                        cost_breakdown = :cost_breakdown,
                        top_users = :top_users
                    WHERE id = :id
                """), {
                    "id": existing[0],
                    "total_cost": str(team_total),
                    "user_count": int(team_data[0]),
                    "ai_cost": str(team_data[2]),
                    "communications_cost": str(communications_cost),
                    "storage_cost": str(team_data[6]),
                    "infrastructure_cost": str(team_data[7]),
                    "cost_breakdown": cost_breakdown,
                    "top_users": top_users_list
                })
                snapshots_updated += 1
            else:
                import uuid
                db.execute(text("""
                    INSERT INTO team_usage_snapshots (
                        id, organization_id, team_id, snapshot_date,
                        total_cost, user_count,
                        ai_tokens_cost, communications_cost, storage_cost, infrastructure_cost,
                        cost_breakdown, top_users
                    ) VALUES (
                        :id, :organization_id, :team_id, :snapshot_date,
                        :total_cost, :user_count,
                        :ai_cost, :communications_cost, :storage_cost, :infrastructure_cost,
                        :cost_breakdown, :top_users
                    )
                """), {
                    "id": str(uuid.uuid4()),
                    "organization_id": organization_id,
                    "team_id": team_id,
                    "snapshot_date": snapshot_date,
                    "total_cost": str(team_total),
                    "user_count": int(team_data[0]),
                    "ai_cost": str(team_data[2]),
                    "communications_cost": str(communications_cost),
                    "storage_cost": str(team_data[6]),
                    "infrastructure_cost": str(team_data[7]),
                    "cost_breakdown": cost_breakdown,
                    "top_users": top_users_list
                })
                snapshots_created += 1

            total_cost += team_total

        except Exception as e:
            logger.error(f"Failed to aggregate team {team_id}: {e}")
            continue

    db.commit()

    summary = {
        "snapshot_date": str(snapshot_date),
        "organization_id": organization_id,
        "teams_processed": len(team_ids),
        "snapshots_created": snapshots_created,
        "snapshots_updated": snapshots_updated,
        "total_cost": float(total_cost)
    }

    logger.info(f"Team aggregation complete: {summary}")
    return summary


# =============================================================================
# ORGANIZATION USAGE AGGREGATION
# =============================================================================

def aggregate_daily_org_usage(
    db: Session,
    organization_id: int,
    snapshot_date: date = None
) -> Dict[str, Any]:
    """
    Aggregate all usage into a single OrgUsageSnapshot.
    The top-level daily summary for the entire organization.
    """
    if snapshot_date is None:
        snapshot_date = date.today() - timedelta(days=1)

    logger.info(f"Starting org usage aggregation for {snapshot_date}")

    # Aggregate from user snapshots
    org_data = db.execute(text("""
        SELECT
            COUNT(DISTINCT user_id) as user_count,
            COALESCE(SUM(total_cost), 0) as total_cost,
            COALESCE(SUM(ai_tokens_cost), 0) as ai_cost,
            COALESCE(SUM(sms_cost + voice_cost + email_cost), 0) as communications_cost,
            COALESCE(SUM(storage_cost), 0) as storage_cost,
            COALESCE(SUM(infrastructure_cost), 0) as infrastructure_cost,
            COALESCE(SUM(ai_tokens_input), 0) as ai_input,
            COALESCE(SUM(ai_tokens_output), 0) as ai_output,
            COALESCE(SUM(ai_request_count), 0) as ai_requests,
            COALESCE(SUM(sms_segments), 0) as sms_segments,
            COALESCE(SUM(voice_minutes), 0) as voice_minutes,
            COALESCE(SUM(email_count), 0) as email_count
        FROM user_usage_snapshots
        WHERE organization_id = :organization_id
        AND snapshot_date = :snapshot_date
    """), {
        "organization_id": organization_id,
        "snapshot_date": snapshot_date
    }).fetchone()

    # Count teams
    team_count = db.execute(text("""
        SELECT COUNT(DISTINCT team_id)
        FROM team_usage_snapshots
        WHERE organization_id = :organization_id
        AND snapshot_date = :snapshot_date
    """), {
        "organization_id": organization_id,
        "snapshot_date": snapshot_date
    }).fetchone()[0]

    # Get top users
    top_users = db.execute(text("""
        SELECT
            uus.user_id,
            COALESCE(es.full_name, u.email) AS name,
            uus.total_cost
        FROM user_usage_snapshots uus
        JOIN users u ON u.id = uus.user_id
        LEFT JOIN email_signatures es ON es.user_id = u.id
        WHERE uus.organization_id = :organization_id
        AND uus.snapshot_date = :snapshot_date
        ORDER BY uus.total_cost DESC
        LIMIT 10
    """), {
        "organization_id": organization_id,
        "snapshot_date": snapshot_date
    }).fetchall()

    top_users_list = [
        {"user_id": row[0], "name": row[1], "cost": float(row[2])}
        for row in top_users
    ]

    # Get top teams
    top_teams = db.execute(text("""
        SELECT
            team_id,
            total_cost,
            user_count
        FROM team_usage_snapshots
        WHERE organization_id = :organization_id
        AND snapshot_date = :snapshot_date
        ORDER BY total_cost DESC
        LIMIT 5
    """), {
        "organization_id": organization_id,
        "snapshot_date": snapshot_date
    }).fetchall()

    top_teams_list = [
        {"team_id": row[0], "cost": float(row[1]), "user_count": row[2]}
        for row in top_teams
    ]

    # Get top features
    top_features = db.execute(text("""
        SELECT
            COALESCE(feature, 'unknown') as feature,
            SUM(total_cost) as cost
        FROM ai_token_usage_log
        WHERE organization_id = :organization_id
        AND DATE(timestamp) = :snapshot_date
        GROUP BY feature
        ORDER BY cost DESC
        LIMIT 10
    """), {
        "organization_id": organization_id,
        "snapshot_date": snapshot_date
    }).fetchall()

    top_features_list = [
        {"feature": row[0], "cost": float(row[1])}
        for row in top_features
    ]

    # Build cost breakdown
    cost_breakdown = {
        "ai_tokens": float(org_data[2]),
        "communications": float(org_data[3]),
        "storage": float(org_data[4]),
        "infrastructure": float(org_data[5])
    }

    # Check if snapshot exists
    existing = db.execute(text("""
        SELECT id FROM org_usage_snapshots
        WHERE organization_id = :organization_id
        AND snapshot_date = :snapshot_date
    """), {
        "organization_id": organization_id,
        "snapshot_date": snapshot_date
    }).fetchone()

    if existing:
        db.execute(text("""
            UPDATE org_usage_snapshots SET
                total_cost = :total_cost,
                user_count = :user_count,
                team_count = :team_count,
                ai_tokens_cost = :ai_cost,
                communications_cost = :communications_cost,
                storage_cost = :storage_cost,
                infrastructure_cost = :infrastructure_cost,
                ai_tokens_input = :ai_input,
                ai_tokens_output = :ai_output,
                ai_request_count = :ai_requests,
                sms_segments = :sms_segments,
                voice_minutes = :voice_minutes,
                email_count = :email_count,
                cost_breakdown = :cost_breakdown,
                top_teams = :top_teams,
                top_users = :top_users,
                top_features = :top_features
            WHERE id = :id
        """), {
            "id": existing[0],
            "total_cost": str(org_data[1]),
            "user_count": int(org_data[0]),
            "team_count": team_count or 0,
            "ai_cost": str(org_data[2]),
            "communications_cost": str(org_data[3]),
            "storage_cost": str(org_data[4]),
            "infrastructure_cost": str(org_data[5]),
            "ai_input": int(org_data[6]),
            "ai_output": int(org_data[7]),
            "ai_requests": int(org_data[8]),
            "sms_segments": int(org_data[9]),
            "voice_minutes": str(org_data[10]),
            "email_count": int(org_data[11]),
            "cost_breakdown": cost_breakdown,
            "top_teams": top_teams_list,
            "top_users": top_users_list,
            "top_features": top_features_list
        })
        action = "updated"
    else:
        import uuid
        db.execute(text("""
            INSERT INTO org_usage_snapshots (
                id, organization_id, snapshot_date,
                total_cost, user_count, team_count,
                ai_tokens_cost, communications_cost, storage_cost, infrastructure_cost,
                ai_tokens_input, ai_tokens_output, ai_request_count,
                sms_segments, voice_minutes, email_count,
                cost_breakdown, top_teams, top_users, top_features
            ) VALUES (
                :id, :organization_id, :snapshot_date,
                :total_cost, :user_count, :team_count,
                :ai_cost, :communications_cost, :storage_cost, :infrastructure_cost,
                :ai_input, :ai_output, :ai_requests,
                :sms_segments, :voice_minutes, :email_count,
                :cost_breakdown, :top_teams, :top_users, :top_features
            )
        """), {
            "id": str(uuid.uuid4()),
            "organization_id": organization_id,
            "snapshot_date": snapshot_date,
            "total_cost": str(org_data[1]),
            "user_count": int(org_data[0]),
            "team_count": team_count or 0,
            "ai_cost": str(org_data[2]),
            "communications_cost": str(org_data[3]),
            "storage_cost": str(org_data[4]),
            "infrastructure_cost": str(org_data[5]),
            "ai_input": int(org_data[6]),
            "ai_output": int(org_data[7]),
            "ai_requests": int(org_data[8]),
            "sms_segments": int(org_data[9]),
            "voice_minutes": str(org_data[10]),
            "email_count": int(org_data[11]),
            "cost_breakdown": cost_breakdown,
            "top_teams": top_teams_list,
            "top_users": top_users_list,
            "top_features": top_features_list
        })
        action = "created"

    db.commit()

    summary = {
        "snapshot_date": str(snapshot_date),
        "organization_id": organization_id,
        "action": action,
        "total_cost": float(org_data[1]),
        "user_count": int(org_data[0]),
        "team_count": team_count or 0,
        "ai_requests": int(org_data[8])
    }

    logger.info(f"Org aggregation complete: {summary}")
    return summary


# =============================================================================
# MAIN AGGREGATION RUNNER
# =============================================================================

def run_daily_aggregation(
    db: Session,
    organization_id: int,
    snapshot_date: date = None
) -> Dict[str, Any]:
    """
    Run all daily aggregation tasks in order.
    Should be run once daily, typically at midnight UTC.
    """
    if snapshot_date is None:
        snapshot_date = date.today() - timedelta(days=1)

    logger.info(f"=" * 60)
    logger.info(f"Starting daily usage aggregation for {snapshot_date}")
    logger.info(f"=" * 60)

    results = {
        "snapshot_date": str(snapshot_date),
        "organization_id": organization_id,
        "status": "success"
    }

    try:
        # Step 1: Aggregate user usage
        user_result = aggregate_daily_user_usage(db, organization_id, snapshot_date)
        results["users"] = user_result

        # Step 2: Aggregate team usage
        team_result = aggregate_daily_team_usage(db, organization_id, snapshot_date)
        results["teams"] = team_result

        # Step 3: Aggregate org usage
        org_result = aggregate_daily_org_usage(db, organization_id, snapshot_date)
        results["organization"] = org_result

        logger.info(f"=" * 60)
        logger.info(f"Daily aggregation complete!")
        logger.info(f"Total cost for {snapshot_date}: ${org_result['total_cost']:.2f}")
        logger.info(f"=" * 60)

    except Exception as e:
        logger.error(f"Daily aggregation failed: {e}")
        results["status"] = "failed"
        results["error"] = str(e)
        raise

    return results


def backfill_aggregation(
    db: Session,
    organization_id: int,
    start_date: date,
    end_date: date = None
) -> List[Dict[str, Any]]:
    """
    Backfill aggregation for a date range.
    Useful for initial setup or recovering from missed runs.
    """
    if end_date is None:
        end_date = date.today() - timedelta(days=1)

    results = []
    current_date = start_date

    while current_date <= end_date:
        logger.info(f"Backfilling {current_date}...")
        try:
            result = run_daily_aggregation(db, organization_id, current_date)
            results.append(result)
        except Exception as e:
            logger.error(f"Failed to backfill {current_date}: {e}")
            results.append({
                "snapshot_date": str(current_date),
                "status": "failed",
                "error": "Internal server error"
            })

        current_date += timedelta(days=1)

    return results


# =============================================================================
# CLI ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    """Run aggregation from command line with tenant-scoped sessions."""
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from database import SessionLocal, get_db_with_tenant

    # Get org list with un-scoped session
    lookup_db = SessionLocal()
    try:
        org_ids = [row[0] for row in lookup_db.execute(text("SELECT id FROM organizations")).fetchall()]
    finally:
        lookup_db.close()

    if not org_ids:
        print("No organizations found in database.")
    else:
        print(f"Running daily aggregation for {len(org_ids)} organization(s)...")
        for org_id in org_ids:
            print(f"\n--- Organization {org_id} ---")
            with get_db_with_tenant(org_id) as tenant_db:
                result = run_daily_aggregation(tenant_db, organization_id=org_id)
                print(f"Aggregation complete: {result}")
