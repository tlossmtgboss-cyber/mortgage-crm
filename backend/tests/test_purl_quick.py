#!/usr/bin/env python3
"""
PURL System Quick Smoke Test
Perennia AI - Mortgage CRM

Run this to verify the PURL system is working correctly.

Usage:
    python tests/test_purl_quick.py

Environment:
    API_BASE: API base URL (default: http://localhost:8000)
    ADMIN_TOKEN: JWT token for admin access
"""

import os
import sys
import json
import requests
from datetime import datetime

API_BASE = os.getenv("API_BASE", "http://localhost:8000")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")


def print_step(step: int, message: str):
    """Print a test step."""
    print(f"\n{step}. {message}")


def print_result(success: bool, message: str):
    """Print result with status indicator."""
    status = "✓" if success else "✗"
    print(f"   {status} {message}")


def test_health_check():
    """Test API health endpoint."""
    print_step(1, "Testing API health check...")
    try:
        response = requests.get(f"{API_BASE}/health", timeout=5)
        if response.status_code == 200:
            print_result(True, f"API is healthy: {response.json()}")
            return True
        else:
            print_result(False, f"API returned status {response.status_code}")
            return False
    except Exception as e:
        print_result(False, f"Failed to connect: {e}")
        return False


def test_create_workspace(headers: dict):
    """Test workspace creation."""
    print_step(2, "Creating test workspace...")

    test_data = {
        "contact_id": None,  # Will create new contact
        "loan_id": None,
        "custom_slug": f"test-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "settings": {"test_mode": True}
    }

    # For testing, create a contact first or use existing
    contact_data = {
        "first_name": "Test",
        "last_name": "User",
        "email": f"test.{datetime.now().timestamp()}@example.com",
        "phone": "555-0100"
    }

    try:
        response = requests.post(
            f"{API_BASE}/api/v1/purl-admin/workspaces",
            headers=headers,
            json={
                **test_data,
                **contact_data,
                "loan_purpose": "purchase",
                "loan_amount": 350000
            },
            timeout=10
        )

        if response.status_code in [200, 201]:
            data = response.json()
            print_result(True, f"Workspace created: {data.get('workspace_slug', 'unknown')}")
            print_result(True, f"Token generated: {data.get('token', 'N/A')[:30]}...")
            return data
        else:
            print_result(False, f"Failed with status {response.status_code}: {response.text}")
            return None
    except Exception as e:
        print_result(False, f"Request failed: {e}")
        return None


def test_workspace_access(slug: str, token: str):
    """Test accessing workspace with token."""
    print_step(3, "Testing workspace access with token...")

    headers = {"Authorization": f"Bearer {token}"}

    try:
        response = requests.get(
            f"{API_BASE}/api/purl/workspace/{slug}",
            headers=headers,
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            workspace = data.get("workspace", {})
            print_result(True, f"Workspace accessed: {workspace.get('display_name', 'unknown')}")
            print_result(True, f"Status: {workspace.get('status', 'unknown')}")
            return True
        else:
            print_result(False, f"Access denied: {response.status_code}")
            return False
    except Exception as e:
        print_result(False, f"Request failed: {e}")
        return False


def test_save_application(slug: str, token: str):
    """Test saving application data."""
    print_step(4, "Testing application save...")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    application_data = {
        "borrower_first_name": "Test",
        "borrower_last_name": "User",
        "borrower_email": "test@example.com",
        "borrower_phone": "555-0100",
        "loan_purpose": "purchase",
        "loan_amount": 350000,
        "property_type": "single_family",
        "property_state": "CA",
        "estimated_credit_score": 750
    }

    try:
        response = requests.post(
            f"{API_BASE}/api/purl/workspace/{slug}/application",
            headers=headers,
            json=application_data,
            timeout=10
        )

        if response.status_code in [200, 201]:
            data = response.json()
            print_result(True, f"Application saved: {data.get('completeness', 0)}% complete")
            return True
        else:
            print_result(False, f"Save failed: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print_result(False, f"Request failed: {e}")
        return False


def test_get_application(slug: str, token: str):
    """Test retrieving application data."""
    print_step(5, "Testing application retrieval...")

    headers = {"Authorization": f"Bearer {token}"}

    try:
        response = requests.get(
            f"{API_BASE}/api/purl/workspace/{slug}/application",
            headers=headers,
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            app = data.get("application", {})
            print_result(True, f"Application retrieved: {app.get('status', 'unknown')}")
            print_result(True, f"Completeness: {data.get('completeness', 0)}%")
            return True
        elif response.status_code == 404:
            print_result(True, "No application yet (expected for new workspace)")
            return True
        else:
            print_result(False, f"Retrieval failed: {response.status_code}")
            return False
    except Exception as e:
        print_result(False, f"Request failed: {e}")
        return False


def test_get_tasks(slug: str, token: str):
    """Test retrieving tasks."""
    print_step(6, "Testing tasks retrieval...")

    headers = {"Authorization": f"Bearer {token}"}

    try:
        response = requests.get(
            f"{API_BASE}/api/purl/workspace/{slug}/tasks",
            headers=headers,
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            tasks = data.get("tasks", [])
            print_result(True, f"Tasks retrieved: {len(tasks)} tasks")
            return True
        else:
            print_result(False, f"Retrieval failed: {response.status_code}")
            return False
    except Exception as e:
        print_result(False, f"Request failed: {e}")
        return False


def test_get_timeline(slug: str, token: str):
    """Test retrieving timeline."""
    print_step(7, "Testing timeline retrieval...")

    headers = {"Authorization": f"Bearer {token}"}

    try:
        response = requests.get(
            f"{API_BASE}/api/purl/workspace/{slug}/timeline",
            headers=headers,
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            events = data.get("events", [])
            print_result(True, f"Timeline retrieved: {len(events)} events")
            return True
        else:
            print_result(False, f"Retrieval failed: {response.status_code}")
            return False
    except Exception as e:
        print_result(False, f"Request failed: {e}")
        return False


def test_admin_list_workspaces(headers: dict):
    """Test admin workspace listing."""
    print_step(8, "Testing admin workspace listing...")

    try:
        response = requests.get(
            f"{API_BASE}/api/v1/purl-admin/workspaces",
            headers=headers,
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            workspaces = data.get("workspaces", [])
            print_result(True, f"Listed {len(workspaces)} workspaces")
            return True
        else:
            print_result(False, f"Listing failed: {response.status_code}")
            return False
    except Exception as e:
        print_result(False, f"Request failed: {e}")
        return False


def main():
    """Run all smoke tests."""
    print("=" * 60)
    print("PURL System Smoke Test")
    print("=" * 60)
    print(f"API Base: {API_BASE}")
    print(f"Admin Token: {'configured' if ADMIN_TOKEN else 'NOT SET'}")

    if not ADMIN_TOKEN:
        print("\n⚠️  Warning: ADMIN_TOKEN not set. Some tests will be skipped.")
        print("   Set ADMIN_TOKEN environment variable for full testing.")

    results = []

    # Test 1: Health check
    results.append(("Health Check", test_health_check()))

    if not results[0][1]:
        print("\n❌ API is not responding. Stopping tests.")
        sys.exit(1)

    # Admin tests (require token)
    admin_headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"} if ADMIN_TOKEN else {}

    if ADMIN_TOKEN:
        # Test 2: Create workspace
        workspace_data = test_create_workspace(admin_headers)
        results.append(("Create Workspace", workspace_data is not None))

        if workspace_data:
            slug = workspace_data.get("workspace_slug")
            token = workspace_data.get("token")

            if slug and token:
                # Test 3: Access workspace
                results.append(("Workspace Access", test_workspace_access(slug, token)))

                # Test 4: Save application
                results.append(("Save Application", test_save_application(slug, token)))

                # Test 5: Get application
                results.append(("Get Application", test_get_application(slug, token)))

                # Test 6: Get tasks
                results.append(("Get Tasks", test_get_tasks(slug, token)))

                # Test 7: Get timeline
                results.append(("Get Timeline", test_get_timeline(slug, token)))

        # Test 8: Admin list workspaces
        results.append(("Admin List Workspaces", test_admin_list_workspaces(admin_headers)))
    else:
        print("\n⚠️  Skipping admin tests (no token)")

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {status}: {name}")

    print(f"\nResults: {passed}/{total} tests passed")

    if passed == total:
        print("\n✅ All tests passed! PURL system is working correctly.")
        sys.exit(0)
    else:
        print(f"\n❌ {total - passed} test(s) failed. Review the output above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
