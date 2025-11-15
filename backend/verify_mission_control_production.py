"""
Mission Control Production Verification Script
Tests all 6 verification requirements from the checklist
"""
import os
import sys
from sqlalchemy import create_engine, text, inspect
from datetime import datetime, timedelta
import json

# Get production database URL
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("❌ DATABASE_URL environment variable not set")
    print("Please set it to your production PostgreSQL URL")
    sys.exit(1)

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)

def print_section(title):
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}\n")

def print_result(test_name, passed, details=""):
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status} - {test_name}")
    if details:
        print(f"   {details}")
    print()

# ============================================================================
# TEST 1: Verify Tables Exist
# ============================================================================
def test_1_tables_exist():
    print_section("TEST 1: Verify Mission Control Tables Exist")

    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names()

        required_tables = [
            "ai_colleague_actions",
            "ai_colleague_learning_metrics",
            "ai_performance_daily",
            "ai_journey_insights",
            "ai_health_score"
        ]

        missing_tables = []
        for table in required_tables:
            if table in tables:
                print_result(f"Table '{table}' exists", True)
            else:
                print_result(f"Table '{table}' exists", False)
                missing_tables.append(table)

        if missing_tables:
            print(f"\n❌ Missing tables: {', '.join(missing_tables)}")
            print("Run the migration first: python migrations/add_ai_colleague_tracking.py")
            return False

        return True

    except Exception as e:
        print_result("Database connection", False, str(e))
        return False

# ============================================================================
# TEST 2: Check for Real Data
# ============================================================================
def test_2_real_data_exists():
    print_section("TEST 2: Verify Real AI Actions Data Exists")

    try:
        with engine.connect() as conn:
            # Count total actions
            result = conn.execute(text("""
                SELECT COUNT(*) as count FROM ai_colleague_actions
            """))
            total_count = result.fetchone()[0]

            print_result(
                "Total AI actions in database",
                total_count > 0,
                f"{total_count} actions found"
            )

            if total_count == 0:
                print("⚠️  No AI actions logged yet. Database is empty.")
                print("   Try using Smart AI Chat feature to generate test data.")
                return False

            # Get recent actions (last 24 hours)
            result = conn.execute(text("""
                SELECT
                    action_id,
                    agent_name,
                    action_type,
                    autonomy_level,
                    status,
                    outcome,
                    created_at
                FROM ai_colleague_actions
                WHERE created_at >= CURRENT_TIMESTAMP - INTERVAL '24 hours'
                ORDER BY created_at DESC
                LIMIT 5
            """))
            recent_actions = result.fetchall()

            print_result(
                "Recent actions (last 24 hours)",
                len(recent_actions) > 0,
                f"{len(recent_actions)} actions found"
            )

            if recent_actions:
                print("Recent actions:")
                for action in recent_actions:
                    print(f"   - [{action.agent_name}] {action.action_type} @ {action.created_at}")

            # Group by agent
            result = conn.execute(text("""
                SELECT
                    agent_name,
                    COUNT(*) as count
                FROM ai_colleague_actions
                GROUP BY agent_name
                ORDER BY count DESC
            """))
            agent_counts = result.fetchall()

            print("\nActions by agent:")
            for row in agent_counts:
                print(f"   - {row.agent_name}: {row.count} actions")

            return total_count > 0

    except Exception as e:
        print_result("Database query", False, str(e))
        return False

# ============================================================================
# TEST 3: Verify Smart AI Chat Logging
# ============================================================================
def test_3_smart_chat_logging():
    print_section("TEST 3: Verify Smart AI Chat Is Logging")

    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT
                    COUNT(*) as count,
                    MAX(created_at) as last_action
                FROM ai_colleague_actions
                WHERE agent_name = 'Smart AI Chat'
            """))
            row = result.fetchone()

            count = row.count
            last_action = row.last_action

            print_result(
                "Smart AI Chat actions exist",
                count > 0,
                f"{count} actions found"
            )

            if last_action:
                time_ago = datetime.now() - last_action.replace(tzinfo=None)
                print(f"   Last action: {time_ago} ago")

            return count > 0

    except Exception as e:
        print_result("Smart AI Chat check", False, str(e))
        return False

# ============================================================================
# TEST 4: Check Health Score Calculation
# ============================================================================
def test_4_health_score():
    print_section("TEST 4: Verify Health Score Calculations")

    try:
        with engine.connect() as conn:
            # Check if health score table has data
            result = conn.execute(text("""
                SELECT
                    overall_score,
                    autonomy_score,
                    accuracy_score,
                    total_actions,
                    calculated_at
                FROM ai_health_score
                ORDER BY calculated_at DESC
                LIMIT 1
            """))
            health_row = result.fetchone()

            if health_row:
                print_result(
                    "Health score record exists",
                    True,
                    f"Score: {health_row.overall_score:.1f}/100"
                )
                print(f"   Autonomy: {health_row.autonomy_score:.1f}")
                print(f"   Accuracy: {health_row.accuracy_score:.1f}")
                print(f"   Total Actions: {health_row.total_actions}")
                print(f"   Last Calculated: {health_row.calculated_at}")
                return True
            else:
                print_result(
                    "Health score record exists",
                    False,
                    "No health scores calculated yet"
                )

                # Try to calculate it now
                print("   Attempting to calculate health score...")
                result = conn.execute(text("""
                    SELECT * FROM calculate_ai_health_score(
                        CURRENT_TIMESTAMP - INTERVAL '7 days',
                        CURRENT_TIMESTAMP
                    )
                """))
                score_data = result.fetchone()

                if score_data:
                    print(f"   ✅ Calculated score: {score_data.overall_score:.1f}/100")
                    print(f"   Total actions: {score_data.total_actions}")
                    return True

                return False

    except Exception as e:
        print_result("Health score check", False, str(e))
        return False

# ============================================================================
# TEST 5: Check Mission Control Views
# ============================================================================
def test_5_mission_control_views():
    print_section("TEST 5: Verify Mission Control Views Work")

    try:
        with engine.connect() as conn:
            # Check mission_control_overview view
            result = conn.execute(text("""
                SELECT * FROM mission_control_overview
                LIMIT 5
            """))
            overview_data = result.fetchall()

            print_result(
                "mission_control_overview view",
                len(overview_data) > 0,
                f"{len(overview_data)} records"
            )

            # Check recent_ai_actions view
            result = conn.execute(text("""
                SELECT * FROM recent_ai_actions
                LIMIT 5
            """))
            recent_data = result.fetchall()

            print_result(
                "recent_ai_actions view",
                len(recent_data) > 0,
                f"{len(recent_data)} records"
            )

            return len(overview_data) > 0 or len(recent_data) > 0

    except Exception as e:
        print_result("Views check", False, str(e))
        return False

# ============================================================================
# TEST 6: Verify API Endpoints (Sample Query)
# ============================================================================
def test_6_data_quality():
    print_section("TEST 6: Verify Data Quality")

    try:
        with engine.connect() as conn:
            # Check for null critical fields
            result = conn.execute(text("""
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN agent_name IS NULL THEN 1 END) as null_agent,
                    COUNT(CASE WHEN action_type IS NULL THEN 1 END) as null_type,
                    COUNT(CASE WHEN created_at IS NULL THEN 1 END) as null_date
                FROM ai_colleague_actions
            """))
            quality = result.fetchone()

            print_result(
                "No null agent names",
                quality.null_agent == 0,
                f"{quality.null_agent}/{quality.total} nulls"
            )

            print_result(
                "No null action types",
                quality.null_type == 0,
                f"{quality.null_type}/{quality.total} nulls"
            )

            print_result(
                "No null timestamps",
                quality.null_date == 0,
                f"{quality.null_date}/{quality.total} nulls"
            )

            # Check for recent data
            result = conn.execute(text("""
                SELECT
                    MAX(created_at) as latest,
                    MIN(created_at) as earliest
                FROM ai_colleague_actions
            """))
            dates = result.fetchone()

            if dates.latest:
                age = datetime.now() - dates.latest.replace(tzinfo=None)
                print(f"\n   Latest action: {age} ago")
                print(f"   Date range: {dates.earliest} to {dates.latest}")

            return quality.null_agent == 0 and quality.null_type == 0

    except Exception as e:
        print_result("Data quality check", False, str(e))
        return False

# ============================================================================
# MAIN VERIFICATION
# ============================================================================
def main():
    print("\n" + "="*80)
    print("  MISSION CONTROL - PRODUCTION VERIFICATION")
    print("="*80)
    print(f"\nConnecting to: {DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else 'database'}")
    print(f"Timestamp: {datetime.now()}")

    results = {}

    # Run all tests
    results['tables'] = test_1_tables_exist()
    results['data'] = test_2_real_data_exists()
    results['smart_chat'] = test_3_smart_chat_logging()
    results['health'] = test_4_health_score()
    results['views'] = test_5_mission_control_views()
    results['quality'] = test_6_data_quality()

    # Summary
    print_section("VERIFICATION SUMMARY")

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    print(f"Tests Passed: {passed}/{total}\n")

    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {test_name}")

    print()

    if all(results.values()):
        print("🎉 ALL TESTS PASSED - Mission Control is fully functional!")
        print("\nNext steps:")
        print("  1. Access Mission Control dashboard in the UI")
        print("  2. Use Smart AI Chat to generate more test data")
        print("  3. Monitor health scores and performance metrics")
        return 0
    else:
        print("⚠️  SOME TESTS FAILED")
        print("\nTroubleshooting:")
        if not results['tables']:
            print("  - Run migration: python migrations/add_ai_colleague_tracking.py")
        if not results['data']:
            print("  - Use Smart AI Chat feature to generate test data")
        if not results['smart_chat']:
            print("  - Check Smart AI Chat integration in main.py")
        if not results['health']:
            print("  - Health scores may need manual calculation initially")
        return 1

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⚠️  Verification cancelled")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
