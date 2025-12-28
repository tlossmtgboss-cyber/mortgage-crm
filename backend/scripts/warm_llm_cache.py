#!/usr/bin/env python3
"""
LLM Cache Warming Script

Pre-populates the Redis cache with common AI queries to reduce cold-start
latency and improve user experience. Run on a schedule (e.g., daily).

Usage:
    python scripts/warm_llm_cache.py [--org-id ORG_ID]

Environment Variables Required:
    - DATABASE_URL: PostgreSQL connection string
    - REDIS_URL: Redis connection string
    - ANTHROPIC_API_KEY: For generating responses

Estimated cost per run: ~$0.50-1.00 (depending on number of queries)
Expected savings: Cache hits avoid ~$0.01 per call, 10k+ calls/month
"""

import os
import sys
import argparse
import logging
from datetime import date
from typing import List, Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def get_active_organizations(db) -> List[Dict[str, Any]]:
    """Get list of active organizations with recent activity."""
    result = db.execute(text("""
        SELECT DISTINCT o.id, o.name
        FROM organizations o
        JOIN users u ON u.organization_id = o.id
        WHERE u.is_active = true
        LIMIT 50
    """))
    return [{"id": row[0], "name": row[1]} for row in result.fetchall()]


def warm_ai_insights_cache(db, org_id: int, org_name: str):
    """Warm the AI insights cache for an organization."""
    from services.ai_insights_service import AIInsightsService

    logger.info(f"Warming AI insights cache for org {org_id} ({org_name})")

    service = AIInsightsService(db, org_id)
    current_month = date.today().replace(day=1)

    # Common natural language queries
    common_queries = [
        "Who are my top performing loan officers?",
        "What is our cost per loan this month?",
        "What's our profit margin trend?",
        "Which roles have the best ROI?",
        "Should we hire more processors?",
    ]

    warmed = 0
    for query in common_queries:
        try:
            result = service.query_natural_language(query, current_month)
            if result.get("_cached"):
                logger.debug(f"  Query already cached: {query[:40]}...")
            else:
                logger.info(f"  Warmed query: {query[:40]}...")
                warmed += 1
        except Exception as e:
            logger.warning(f"  Failed to warm query '{query[:30]}...': {e}")

    # Warm recommendations cache
    try:
        result = service.generate_smart_recommendations(current_month)
        if not isinstance(result, list) or not result or not result[0].get("_cached"):
            logger.info(f"  Warmed recommendations")
            warmed += 1
    except Exception as e:
        logger.warning(f"  Failed to warm recommendations: {e}")

    # Warm anomaly detection
    try:
        result = service.detect_anomalies(current_month)
        logger.info(f"  Warmed anomaly detection")
        warmed += 1
    except Exception as e:
        logger.warning(f"  Failed to warm anomaly detection: {e}")

    return warmed


def warm_executive_digest_cache(db, org_id: int, org_name: str):
    """Warm executive digest cache for organization."""
    from services.ai_insights_service import AIInsightsService

    logger.info(f"Warming executive digest for org {org_id}")

    service = AIInsightsService(db, org_id)
    current_month = date.today().replace(day=1)

    try:
        result = service.generate_executive_digest(current_month)
        if result.get("_cached"):
            logger.debug("  Digest already cached")
            return 0
        logger.info("  Warmed executive digest")
        return 1
    except Exception as e:
        logger.warning(f"  Failed to warm digest: {e}")
        return 0


def get_cache_stats():
    """Get current cache statistics."""
    from services.llm_cache_service import llm_cache
    return llm_cache.get_stats()


def main():
    parser = argparse.ArgumentParser(description="Warm LLM response cache")
    parser.add_argument("--org-id", type=int, help="Specific organization ID to warm")
    parser.add_argument("--insights-only", action="store_true", help="Only warm AI insights")
    parser.add_argument("--digest-only", action="store_true", help="Only warm executive digests")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be warmed without executing")
    args = parser.parse_args()

    # Check required environment variables
    required_vars = ["DATABASE_URL", "ANTHROPIC_API_KEY"]
    missing = [v for v in required_vars if not os.getenv(v)]
    if missing:
        logger.error(f"Missing required environment variables: {', '.join(missing)}")
        sys.exit(1)

    # Check Redis (optional but recommended)
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        logger.warning("REDIS_URL not set - cache warming will make API calls but won't cache")

    # Connect to database
    database_url = os.getenv("DATABASE_URL")
    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        # Get initial stats
        initial_stats = get_cache_stats()
        logger.info(f"Initial cache stats: {initial_stats}")

        # Get organizations to warm
        if args.org_id:
            orgs = [{"id": args.org_id, "name": "Specified"}]
        else:
            orgs = get_active_organizations(db)

        if args.dry_run:
            logger.info(f"DRY RUN - Would warm cache for {len(orgs)} organizations:")
            for org in orgs:
                logger.info(f"  - Org {org['id']}: {org['name']}")
            return

        logger.info(f"Starting cache warming for {len(orgs)} organizations")

        total_warmed = 0

        for org in orgs:
            try:
                if not args.digest_only:
                    warmed = warm_ai_insights_cache(db, org["id"], org["name"])
                    total_warmed += warmed

                if not args.insights_only:
                    warmed = warm_executive_digest_cache(db, org["id"], org["name"])
                    total_warmed += warmed

            except Exception as e:
                logger.error(f"Failed to warm cache for org {org['id']}: {e}")
                continue

        # Get final stats
        final_stats = get_cache_stats()

        logger.info("=" * 50)
        logger.info("Cache warming complete!")
        logger.info(f"  Total queries warmed: {total_warmed}")
        logger.info(f"  Cache hits: {final_stats['hits']} (was {initial_stats['hits']})")
        logger.info(f"  Cache misses: {final_stats['misses']} (was {initial_stats['misses']})")
        logger.info(f"  Hit rate: {final_stats['hit_rate_percent']}%")
        logger.info(f"  Estimated savings: ${final_stats['estimated_savings_usd']}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
