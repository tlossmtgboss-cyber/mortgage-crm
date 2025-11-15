#!/usr/bin/env python3
"""
AI Receptionist Dashboard - Complete Verification Script
Tests all functionality end-to-end and generates proof of operation
"""
import requests
import json
import time
from datetime import date, timedelta
from tabulate import tabulate

# Configuration
BACKEND_URL = "https://mortgage-crm-production-7a9a.up.railway.app"
API_BASE = f"{BACKEND_URL}/api/v1"

# Test results storage
results = {
    'passed': [],
    'failed': [],
    'warnings': []
}


def print_section(title):
    """Print formatted section header"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def test_result(test_name, passed, details=""):
    """Record and print test result"""
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status} - {test_name}")
    if details:
        print(f"     {details}")

    if passed:
        results['passed'].append(test_name)
    else:
        results['failed'].append((test_name, details))


def get_auth_token():
    """Get authentication token"""
    print("\n🔐 Getting authentication token...")
    email = input("Enter your email: ").strip()
    password = input("Enter your password: ").strip()

    response = requests.post(
        f"{BACKEND_URL}/token",
        data={"username": email, "password": password}
    )

    if response.status_code == 200:
        token = response.json().get("access_token")
        print("✅ Authentication successful")
        return token
    else:
        print(f"❌ Authentication failed: {response.status_code}")
        print(response.text)
        return None


def test_1_run_migration(headers):
    """Test 1: Run migration and verify tables"""
    print_section("TEST 1: DATABASE MIGRATION")

    # Run migration
    print("\n📊 Running migration...")
    response = requests.post(
        f"{API_BASE}/migrations/add-ai-receptionist-dashboard-tables",
        headers=headers
    )

    if response.status_code == 200:
        data = response.json()
        test_result("Migration endpoint", data.get('success'),
                   f"Message: {data.get('message')}")

        if data.get('tables_created'):
            print(f"\n📋 Tables created:")
            for table in data['tables_created']:
                print(f"   • {table}")

        return data.get('success')
    else:
        test_result("Migration endpoint", False,
                   f"Status: {response.status_code}, Response: {response.text[:200]}")
        return False


def test_2_seed_data():
    """Test 2: Seed sample data"""
    print_section("TEST 2: DATA SEEDING")

    print("\n🌱 Running seed script...")
    print("This will populate all 6 tables with sample data...")

    import subprocess
    import sys

    try:
        # Run the seed script
        result = subprocess.run(
            [sys.executable, "seed_ai_receptionist_dashboard.py"],
            capture_output=True,
            text=True,
            timeout=60
        )

        print(result.stdout)

        if result.returncode == 0:
            test_result("Data seeding", True, "All tables populated successfully")
            return True
        else:
            test_result("Data seeding", False, f"Exit code: {result.returncode}\n{result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        test_result("Data seeding", False, "Timeout after 60 seconds")
        return False
    except Exception as e:
        test_result("Data seeding", False, str(e))
        return False


def test_3_activity_feed(headers):
    """Test 3: Activity Feed endpoints"""
    print_section("TEST 3: ACTIVITY FEED ENDPOINTS")

    # Test activity feed
    print("\n📋 Testing GET /activity/feed...")
    response = requests.get(
        f"{API_BASE}/ai-receptionist/dashboard/activity/feed",
        headers=headers,
        params={"limit": 5}
    )

    if response.status_code == 200:
        data = response.json()
        test_result("Activity feed endpoint", True, f"Returned {len(data)} activities")

        if data:
            print("\n📊 Sample activity:")
            first = data[0]
            print(f"   • Type: {first.get('action_type')}")
            print(f"   • Client: {first.get('client_name')}")
            print(f"   • Timestamp: {first.get('timestamp')}")
            print(f"   • Confidence: {first.get('confidence_score'):.2%}" if first.get('confidence_score') else "")

        # Test count endpoint
        count_response = requests.get(
            f"{API_BASE}/ai-receptionist/dashboard/activity/count",
            headers=headers
        )
        if count_response.status_code == 200:
            total = count_response.json().get('total')
            test_result("Activity count endpoint", True, f"Total activities: {total}")
        else:
            test_result("Activity count endpoint", False, f"Status: {count_response.status_code}")

        return len(data) > 0
    else:
        test_result("Activity feed endpoint", False,
                   f"Status: {response.status_code}, Response: {response.text[:200]}")
        return False


def test_4_metrics(headers):
    """Test 4: Metrics endpoints"""
    print_section("TEST 4: METRICS ENDPOINTS")

    # Test realtime metrics
    print("\n⚡ Testing GET /metrics/realtime...")
    response = requests.get(
        f"{API_BASE}/ai-receptionist/dashboard/metrics/realtime",
        headers=headers
    )

    if response.status_code == 200:
        data = response.json()
        test_result("Realtime metrics endpoint", True, "Successfully retrieved")

        print("\n📊 Realtime Metrics:")
        metrics_table = [
            ["Conversations Today", data.get('conversations_today')],
            ["Appointments Today", data.get('appointments_today')],
            ["Escalations Today", data.get('escalations_today')],
            ["AI Coverage %", f"{data.get('ai_coverage_percentage', 0):.1f}%"],
            ["Errors Today", data.get('errors_today')]
        ]
        print(tabulate(metrics_table, tablefmt="simple"))
    else:
        test_result("Realtime metrics endpoint", False, f"Status: {response.status_code}")

    # Test daily metrics
    print("\n📅 Testing GET /metrics/daily...")
    end_date = date.today()
    start_date = end_date - timedelta(days=7)

    response = requests.get(
        f"{API_BASE}/ai-receptionist/dashboard/metrics/daily",
        headers=headers,
        params={
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat()
        }
    )

    if response.status_code == 200:
        data = response.json()
        test_result("Daily metrics endpoint", True, f"Retrieved {len(data)} days of metrics")

        if data:
            print("\n📊 Sample daily metrics (most recent):")
            recent = data[-1] if data else {}
            metrics_table = [
                ["Date", recent.get('date')],
                ["Total Conversations", recent.get('total_conversations')],
                ["Appointments", recent.get('appointments_scheduled')],
                ["AI Coverage %", f"{recent.get('ai_coverage_percentage', 0):.1f}%"],
                ["Est. Revenue", f"${recent.get('estimated_revenue_created', 0):,.2f}"]
            ]
            print(tabulate(metrics_table, tablefmt="simple"))

        return len(data) > 0
    else:
        test_result("Daily metrics endpoint", False, f"Status: {response.status_code}")
        return False


def test_5_skills(headers):
    """Test 5: Skills endpoints"""
    print_section("TEST 5: SKILLS ENDPOINTS")

    print("\n🎯 Testing GET /skills...")
    response = requests.get(
        f"{API_BASE}/ai-receptionist/dashboard/skills",
        headers=headers
    )

    if response.status_code == 200:
        data = response.json()
        test_result("Skills endpoint", True, f"Retrieved {len(data)} skills")

        if data:
            print("\n📊 Skills Performance (Top 5):")
            skills_table = []
            for skill in data[:5]:
                skills_table.append([
                    skill.get('skill_name', '')[:30],
                    f"{skill.get('accuracy_score', 0):.1%}",
                    skill.get('trend_direction', 'N/A'),
                    "🔴" if skill.get('needs_retraining') else "🟢"
                ])
            print(tabulate(skills_table,
                          headers=["Skill", "Accuracy", "Trend", "Status"],
                          tablefmt="simple"))

            # Test specific skill detail
            if data:
                skill_name = data[0]['skill_name']
                print(f"\n🔍 Testing GET /skills/{skill_name}...")
                detail_response = requests.get(
                    f"{API_BASE}/ai-receptionist/dashboard/skills/{skill_name}",
                    headers=headers
                )
                test_result("Skill detail endpoint", detail_response.status_code == 200)

        return len(data) > 0
    else:
        test_result("Skills endpoint", False, f"Status: {response.status_code}")
        return False


def test_6_roi(headers):
    """Test 6: ROI endpoint"""
    print_section("TEST 6: ROI METRICS")

    print("\n💰 Testing GET /roi...")
    end_date = date.today()
    start_date = end_date - timedelta(days=30)

    response = requests.get(
        f"{API_BASE}/ai-receptionist/dashboard/roi",
        headers=headers,
        params={
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat()
        }
    )

    if response.status_code == 200:
        data = response.json()
        test_result("ROI endpoint", True, "Successfully calculated")

        print("\n📊 ROI Metrics (Last 30 Days):")
        roi_table = [
            ["Total Appointments", data.get('total_appointments')],
            ["Estimated Revenue", f"${data.get('estimated_revenue', 0):,.2f}"],
            ["Labor Hours Saved", f"{data.get('saved_labor_hours', 0):.1f} hrs"],
            ["Saved Missed Calls", data.get('saved_missed_calls')],
            ["Cost per Interaction", f"${data.get('cost_per_interaction', 0):.2f}"],
            ["ROI %", f"{data.get('roi_percentage', 0):.1f}%" if data.get('roi_percentage') else "N/A"]
        ]
        print(tabulate(roi_table, tablefmt="simple"))

        return True
    else:
        test_result("ROI endpoint", False, f"Status: {response.status_code}")
        return False


def test_7_errors(headers):
    """Test 7: Error log endpoints"""
    print_section("TEST 7: ERROR LOG ENDPOINTS")

    print("\n🚨 Testing GET /errors...")
    response = requests.get(
        f"{API_BASE}/ai-receptionist/dashboard/errors",
        headers=headers,
        params={"status": "unresolved", "limit": 10}
    )

    if response.status_code == 200:
        data = response.json()
        test_result("Error log endpoint", True, f"Retrieved {len(data)} errors")

        if data:
            print("\n📊 Error Log (Unresolved):")
            errors_table = []
            for error in data[:5]:
                errors_table.append([
                    error.get('error_type', '')[:20],
                    error.get('severity', 'N/A'),
                    error.get('conversation_snippet', '')[:40] + "..." if error.get('conversation_snippet') else "N/A",
                    "⚠️" if error.get('needs_human_review') else "ℹ️"
                ])
            print(tabulate(errors_table,
                          headers=["Type", "Severity", "Snippet", "Review"],
                          tablefmt="simple"))

            # Test approve-fix endpoint
            if data:
                error_id = data[0]['id']
                print(f"\n✅ Testing POST /errors/{error_id}/approve-fix...")
                approve_response = requests.post(
                    f"{API_BASE}/ai-receptionist/dashboard/errors/{error_id}/approve-fix",
                    headers=headers
                )
                test_result("Error approve-fix endpoint", approve_response.status_code == 200,
                           f"Response: {approve_response.json().get('message', '')}")

        return len(data) >= 0  # Pass even if no errors
    else:
        test_result("Error log endpoint", False, f"Status: {response.status_code}")
        return False


def test_8_system_health(headers):
    """Test 8: System health endpoints"""
    print_section("TEST 8: SYSTEM HEALTH ENDPOINTS")

    print("\n💚 Testing GET /system-health...")
    response = requests.get(
        f"{API_BASE}/ai-receptionist/dashboard/system-health",
        headers=headers
    )

    if response.status_code == 200:
        data = response.json()
        test_result("System health endpoint", True, f"Retrieved {len(data)} components")

        if data:
            print("\n📊 System Health Status:")
            health_table = []
            for component in data:
                status_icon = {
                    'active': '🟢',
                    'degraded': '🟡',
                    'down': '🔴',
                    'unknown': '⚪'
                }.get(component.get('status'), '⚪')

                health_table.append([
                    component.get('component_name', '')[:25],
                    f"{status_icon} {component.get('status', 'unknown')}",
                    f"{component.get('latency_ms', 0)} ms" if component.get('latency_ms') else "N/A",
                    f"{component.get('error_rate', 0):.1f}%"
                ])
            print(tabulate(health_table,
                          headers=["Component", "Status", "Latency", "Error Rate"],
                          tablefmt="simple"))

        return len(data) > 0
    else:
        test_result("System health endpoint", False, f"Status: {response.status_code}")
        return False


def test_9_conversations(headers):
    """Test 9: Conversations endpoints"""
    print_section("TEST 9: CONVERSATIONS ENDPOINTS")

    print("\n💬 Testing GET /conversations...")
    response = requests.get(
        f"{API_BASE}/ai-receptionist/dashboard/conversations",
        headers=headers,
        params={"limit": 5}
    )

    if response.status_code == 200:
        data = response.json()
        test_result("Conversations list endpoint", True, f"Retrieved {len(data)} conversations")

        if data:
            print("\n📊 Recent Conversations:")
            conv_table = []
            for conv in data[:3]:
                conv_table.append([
                    conv.get('summary', 'N/A')[:40],
                    conv.get('intent_detected', 'N/A'),
                    conv.get('sentiment', 'N/A'),
                    conv.get('outcome', 'N/A')
                ])
            print(tabulate(conv_table,
                          headers=["Summary", "Intent", "Sentiment", "Outcome"],
                          tablefmt="simple"))

            # Test conversation detail
            if data:
                conv_id = data[0]['id']
                print(f"\n🔍 Testing GET /conversations/{conv_id}...")
                detail_response = requests.get(
                    f"{API_BASE}/ai-receptionist/dashboard/conversations/{conv_id}",
                    headers=headers
                )
                test_result("Conversation detail endpoint", detail_response.status_code == 200)

                if detail_response.status_code == 200:
                    detail = detail_response.json()
                    if detail.get('transcript'):
                        print("\n📄 Sample Transcript:")
                        print(detail['transcript'][:200] + "..." if len(detail['transcript']) > 200 else detail['transcript'])

        return len(data) >= 0
    else:
        test_result("Conversations endpoint", False, f"Status: {response.status_code}")
        return False


def test_10_error_handling(headers):
    """Test 10: Error handling"""
    print_section("TEST 10: ERROR HANDLING")

    # Test invalid date range
    print("\n🔍 Testing invalid date range...")
    response = requests.get(
        f"{API_BASE}/ai-receptionist/dashboard/metrics/daily",
        headers=headers,
        params={
            "start_date": "2025-12-31",
            "end_date": "2025-01-01"  # End before start
        }
    )
    test_result("Invalid date range handling", response.status_code in [200, 400, 422])

    # Test non-existent error ID
    print("\n🔍 Testing non-existent error ID...")
    response = requests.post(
        f"{API_BASE}/ai-receptionist/dashboard/errors/nonexistent-id/approve-fix",
        headers=headers
    )
    test_result("Non-existent error ID handling", response.status_code == 404)

    # Test non-existent skill
    print("\n🔍 Testing non-existent skill...")
    response = requests.get(
        f"{API_BASE}/ai-receptionist/dashboard/skills/NonExistentSkill",
        headers=headers
    )
    test_result("Non-existent skill handling", response.status_code == 404)


def test_11_performance(headers):
    """Test 11: Performance testing"""
    print_section("TEST 11: PERFORMANCE TESTING")

    print("\n⚡ Running 100 requests to activity feed...")
    print("This may take a minute...")

    start_time = time.time()
    response_times = []

    for i in range(100):
        req_start = time.time()
        response = requests.get(
            f"{API_BASE}/ai-receptionist/dashboard/activity/feed",
            headers=headers,
            params={"limit": 10}
        )
        req_end = time.time()

        response_times.append(req_end - req_start)

        if (i + 1) % 20 == 0:
            print(f"   Completed {i + 1}/100 requests...")

    end_time = time.time()
    total_time = end_time - start_time
    avg_response_time = sum(response_times) / len(response_times)
    min_time = min(response_times)
    max_time = max(response_times)

    print("\n📊 Performance Results:")
    perf_table = [
        ["Total Requests", "100"],
        ["Total Time", f"{total_time:.2f}s"],
        ["Requests/Second", f"{100/total_time:.2f}"],
        ["Avg Response Time", f"{avg_response_time*1000:.0f}ms"],
        ["Min Response Time", f"{min_time*1000:.0f}ms"],
        ["Max Response Time", f"{max_time*1000:.0f}ms"]
    ]
    print(tabulate(perf_table, tablefmt="simple"))

    # Pass if average response time is under 2 seconds
    test_result("Performance test", avg_response_time < 2.0,
               f"Avg response time: {avg_response_time*1000:.0f}ms")


def generate_summary():
    """Generate test summary"""
    print_section("TEST SUMMARY")

    total_tests = len(results['passed']) + len(results['failed'])
    pass_rate = (len(results['passed']) / total_tests * 100) if total_tests > 0 else 0

    print(f"\n📊 Results:")
    print(f"   Total Tests: {total_tests}")
    print(f"   ✅ Passed: {len(results['passed'])}")
    print(f"   ❌ Failed: {len(results['failed'])}")
    print(f"   Pass Rate: {pass_rate:.1f}%")

    if results['failed']:
        print("\n❌ Failed Tests:")
        for test_name, details in results['failed']:
            print(f"   • {test_name}")
            if details:
                print(f"     {details}")

    if results['warnings']:
        print("\n⚠️  Warnings:")
        for warning in results['warnings']:
            print(f"   • {warning}")

    print("\n" + "=" * 80)
    if len(results['failed']) == 0:
        print("🎉 ALL TESTS PASSED! Dashboard is fully functional.")
    else:
        print("⚠️  Some tests failed. Review the output above for details.")
    print("=" * 80)


def main():
    """Main verification function"""
    print("\n" + "=" * 80)
    print("  AI RECEPTIONIST DASHBOARD - COMPREHENSIVE VERIFICATION")
    print("=" * 80)

    print("\nThis script will:")
    print("  1. Run the database migration")
    print("  2. Seed sample data")
    print("  3. Test all 13 API endpoints")
    print("  4. Test error handling")
    print("  5. Run performance tests")
    print("  6. Generate verification report")

    input("\nPress Enter to begin verification...")

    # Get authentication
    headers = {}
    token = get_auth_token()
    if not token:
        print("\n❌ Cannot proceed without authentication")
        return False

    headers['Authorization'] = f"Bearer {token}"

    # Run all tests
    test_1_run_migration(headers)
    test_2_seed_data()
    test_3_activity_feed(headers)
    test_4_metrics(headers)
    test_5_skills(headers)
    test_6_roi(headers)
    test_7_errors(headers)
    test_8_system_health(headers)
    test_9_conversations(headers)
    test_10_error_handling(headers)
    test_11_performance(headers)

    # Generate summary
    generate_summary()

    return len(results['failed']) == 0


if __name__ == "__main__":
    try:
        success = main()
        exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Verification cancelled by user")
        exit(1)
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
