#!/usr/bin/env python3
"""
Comprehensive Mission Control Systems Check
Tests database tables, API endpoints, and data flow
"""

import os
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv
from sqlalchemy import create_engine, text, inspect

# Load environment
load_dotenv()

# Configuration
API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000")
DATABASE_URL = os.getenv("DATABASE_URL", "")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Colors for output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'

def print_status(message, status="info"):
    if status == "success":
        print(f"{Colors.GREEN}✅ {message}{Colors.RESET}")
    elif status == "error":
        print(f"{Colors.RED}❌ {message}{Colors.RESET}")
    elif status == "warning":
        print(f"{Colors.YELLOW}⚠️  {message}{Colors.RESET}")
    else:
        print(f"{Colors.BLUE}ℹ️  {message}{Colors.RESET}")

def print_section(title):
    print(f"\n{Colors.BLUE}{'='*70}")
    print(f"{title}")
    print(f"{'='*70}{Colors.RESET}\n")

# ============================================================================
# TEST 1: Database Tables Check
# ============================================================================
def test_database_tables():
    print_section("TEST 1: Database Tables")

    try:
        engine = create_engine(DATABASE_URL)
        inspector = inspect(engine)

        required_tables = [
            "ai_colleague_actions",
            "ai_colleague_learning_metrics",
            "ai_performance_daily",
            "ai_journey_insights",
            "ai_health_score"
        ]

        existing_tables = inspector.get_table_names()

        for table in required_tables:
            if table in existing_tables:
                # Get column count
                columns = inspector.get_columns(table)
                print_status(f"Table '{table}' exists ({len(columns)} columns)", "success")

                # Show first few columns
                col_names = [col['name'] for col in columns[:5]]
                print(f"   Columns: {', '.join(col_names)}...")
            else:
                print_status(f"Table '{table}' MISSING", "error")
                return False

        # Check for views
        print("\nChecking views...")
        with engine.connect() as conn:
            view_check = text("""
                SELECT table_name
                FROM information_schema.views
                WHERE table_schema = 'public'
                AND table_name IN ('mission_control_overview', 'recent_ai_actions')
            """)
            views = conn.execute(view_check).fetchall()
            for view in views:
                print_status(f"View '{view[0]}' exists", "success")

        # Check for functions
        print("\nChecking functions...")
        with engine.connect() as conn:
            func_check = text("""
                SELECT routine_name
                FROM information_schema.routines
                WHERE routine_schema = 'public'
                AND routine_name = 'calculate_ai_health_score'
            """)
            funcs = conn.execute(func_check).fetchall()
            if funcs:
                print_status(f"Function 'calculate_ai_health_score' exists", "success")
            else:
                print_status(f"Function 'calculate_ai_health_score' missing", "warning")

        return True

    except Exception as e:
        print_status(f"Database check failed: {str(e)}", "error")
        return False

# ============================================================================
# TEST 2: Database Content Check
# ============================================================================
def test_database_content():
    print_section("TEST 2: Database Content")

    try:
        engine = create_engine(DATABASE_URL)

        with engine.connect() as conn:
            # Check ai_colleague_actions table
            count_query = text("SELECT COUNT(*) FROM ai_colleague_actions")
            count = conn.execute(count_query).scalar()

            if count > 0:
                print_status(f"ai_colleague_actions has {count} records", "success")

                # Get recent action
                recent_query = text("""
                    SELECT action_id, agent_name, action_type, created_at
                    FROM ai_colleague_actions
                    ORDER BY created_at DESC
                    LIMIT 1
                """)
                recent = conn.execute(recent_query).fetchone()
                if recent:
                    print(f"   Latest: {recent[1]} - {recent[2]} ({recent[3]})")
            else:
                print_status(f"ai_colleague_actions is EMPTY (no test data)", "warning")

            # Check ai_performance_daily
            daily_query = text("SELECT COUNT(*) FROM ai_performance_daily")
            daily_count = conn.execute(daily_query).scalar()

            if daily_count > 0:
                print_status(f"ai_performance_daily has {daily_count} records", "success")
            else:
                print_status(f"ai_performance_daily is EMPTY", "warning")

            # Check ai_health_score
            health_query = text("SELECT COUNT(*) FROM ai_health_score")
            health_count = conn.execute(health_query).scalar()

            if health_count > 0:
                print_status(f"ai_health_score has {health_count} records", "success")
            else:
                print_status(f"ai_health_score is EMPTY", "warning")

        return True

    except Exception as e:
        print_status(f"Content check failed: {str(e)}", "error")
        return False

# ============================================================================
# TEST 3: Create Sample Data
# ============================================================================
def create_sample_data():
    print_section("TEST 3: Creating Sample Test Data")

    try:
        engine = create_engine(DATABASE_URL)

        with engine.connect() as conn:
            # Create a sample action
            action_id = f"test_action_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            insert_query = text("""
                INSERT INTO ai_colleague_actions (
                    action_id, agent_name, action_type,
                    autonomy_level, confidence_score, status,
                    outcome, reasoning, created_at
                ) VALUES (
                    :action_id, :agent_name, :action_type,
                    :autonomy_level, :confidence_score, :status,
                    :outcome, :reasoning, :created_at
                )
            """)

            conn.execute(insert_query, {
                "action_id": action_id,
                "agent_name": "Smart AI Chat",
                "action_type": "conversation_response",
                "autonomy_level": "full",
                "confidence_score": 0.95,
                "status": "completed",
                "outcome": "success",
                "reasoning": "Test action for Mission Control systems check",
                "created_at": datetime.utcnow()
            })
            conn.commit()

            print_status(f"Created test action: {action_id}", "success")

        return True

    except Exception as e:
        print_status(f"Sample data creation failed: {str(e)}", "error")
        return False

# ============================================================================
# TEST 4: Health Score Function
# ============================================================================
def test_health_score_function():
    print_section("TEST 4: Health Score Calculation Function")

    try:
        engine = create_engine(DATABASE_URL)

        with engine.connect() as conn:
            # Call the health score calculation function
            period_start = datetime.utcnow() - timedelta(days=7)
            period_end = datetime.utcnow()

            health_query = text("""
                SELECT * FROM calculate_ai_health_score(
                    :period_start::timestamp with time zone,
                    :period_end::timestamp with time zone
                )
            """)

            result = conn.execute(health_query, {
                "period_start": period_start,
                "period_end": period_end
            }).fetchone()

            if result:
                print_status("Health score function executed successfully", "success")
                print(f"   Overall Score: {result[0]:.2f}")
                print(f"   Autonomy Score: {result[1]:.2f}")
                print(f"   Accuracy Score: {result[2]:.2f}")
                print(f"   Total Actions: {result[6]}")
                return True
            else:
                print_status("Health score function returned no data", "warning")
                return False

    except Exception as e:
        print_status(f"Health score function test failed: {str(e)}", "error")
        return False

# ============================================================================
# TEST 5: Mission Control Views
# ============================================================================
def test_mission_control_views():
    print_section("TEST 5: Mission Control Views")

    try:
        engine = create_engine(DATABASE_URL)

        with engine.connect() as conn:
            # Test mission_control_overview view
            try:
                overview_query = text("SELECT * FROM mission_control_overview LIMIT 5")
                overview_results = conn.execute(overview_query).fetchall()

                if overview_results:
                    print_status(f"mission_control_overview view works ({len(overview_results)} rows)", "success")
                else:
                    print_status("mission_control_overview view exists but has no data", "warning")
            except Exception as e:
                print_status(f"mission_control_overview view error: {str(e)}", "warning")

            # Test recent_ai_actions view
            try:
                recent_query = text("SELECT * FROM recent_ai_actions LIMIT 5")
                recent_results = conn.execute(recent_query).fetchall()

                if recent_results:
                    print_status(f"recent_ai_actions view works ({len(recent_results)} rows)", "success")
                else:
                    print_status("recent_ai_actions view exists but has no data", "warning")
            except Exception as e:
                print_status(f"recent_ai_actions view error: {str(e)}", "warning")

        return True

    except Exception as e:
        print_status(f"Views test failed: {str(e)}", "error")
        return False

# ============================================================================
# RUN ALL TESTS
# ============================================================================
def main():
    print(f"\n{Colors.BLUE}{'='*70}")
    print("MISSION CONTROL SYSTEMS CHECK")
    print(f"{'='*70}{Colors.RESET}")
    print(f"Database: {DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else 'Local'}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    results = {
        "Database Tables": test_database_tables(),
        "Database Content": test_database_content(),
        "Sample Data Creation": create_sample_data(),
        "Health Score Function": test_health_score_function(),
        "Mission Control Views": test_mission_control_views()
    }

    # Summary
    print_section("SUMMARY")

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test, result in results.items():
        status = "success" if result else "error"
        print_status(f"{test}: {'PASSED' if result else 'FAILED'}", status)

    print(f"\n{Colors.BLUE}Overall: {passed}/{total} tests passed{Colors.RESET}")

    if passed == total:
        print_status("✨ All systems functional!", "success")
        return 0
    else:
        print_status(f"⚠️  {total - passed} test(s) failed", "error")
        return 1

if __name__ == "__main__":
    sys.exit(main())
