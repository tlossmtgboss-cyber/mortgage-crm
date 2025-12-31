#!/usr/bin/env python3
"""
HTTP-based Test script for RETR Webhook Integration

Run this script against a running server to test the RETR webhook.
Usage: python test_retr_webhook_http.py [base_url] [webhook_secret]

Examples:
  python test_retr_webhook_http.py http://localhost:8000
  python test_retr_webhook_http.py https://www.perenniaai.com your-secret-key
"""
import sys
import json
import requests
from datetime import datetime


def print_section(title):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def print_result(test_name, success, details=None):
    status = "PASS" if success else "FAIL"
    print(f"[{status}] {test_name}")
    if details:
        print(f"       {details}")


def test_webhook_status(base_url):
    """Test the webhook status endpoint."""
    print_section("Testing Webhook Status Endpoint")

    try:
        response = requests.get(f"{base_url}/webhooks/retr/status", timeout=10)
        success = response.status_code == 200

        if success:
            data = response.json()
            print_result("GET /webhooks/retr/status", True)
            print(f"       Response: {json.dumps(data, indent=2)}")
            return True
        else:
            print_result("GET /webhooks/retr/status", False, f"Status: {response.status_code}")
            return False
    except Exception as e:
        print_result("GET /webhooks/retr/status", False, str(e))
        return False


def test_agent_import(base_url, secret=None):
    """Test importing a realtor/agent via webhook."""
    print_section("Testing Agent (Realtor) Import")

    agent_payload = {
        "FirstName": "Sarah",
        "LastName": "Johnson",
        "FullName": "Sarah Johnson",
        "Email": f"sarah.test.{datetime.now().strftime('%H%M%S')}@remax.com",
        "Phone": "555-123-4567",
        "Company": "RE/MAX Premier",
        "RETRAgentId": f"AGT-TEST-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "RetrProfileURL": "https://retr.app/agent/AGT-TEST-12345",
        "BuyerCt_12Mo": 24,
        "BuyerVol_12Mo": 5800000.00,
        "SellerCt_12Mo": 18,
        "SellerVol_12Mo": 5900000.00,
        "TotalCt_12Mo": 42,
        "TotalVol_12Mo": 11700000.00,
        "City": "Charlotte",
        "State": "NC",
        "ZipCode": "28202",
        "Tags": "Top Producer, Charlotte Area, Buyer Specialist"
    }

    headers = {"Content-Type": "application/json"}
    if secret:
        headers["X-Webhook-Secret"] = secret

    print(f"Sending agent payload:")
    print(f"  Name: {agent_payload['FirstName']} {agent_payload['LastName']}")
    print(f"  Email: {agent_payload['Email']}")
    print(f"  Company: {agent_payload['Company']}")
    print(f"  RETR ID: {agent_payload['RETRAgentId']}")
    print(f"  Total Volume (12mo): ${agent_payload['TotalVol_12Mo']:,.2f}")

    try:
        response = requests.post(
            f"{base_url}/webhooks/retr/import",
            headers=headers,
            json=agent_payload,
            timeout=30
        )

        # 202 Accepted is the expected response
        success = response.status_code == 202

        if success:
            print_result("POST /webhooks/retr/import (Agent)", True)
            print(f"       Response: {response.text}")
            return True
        else:
            print_result("POST /webhooks/retr/import (Agent)", False,
                        f"Status: {response.status_code}, Body: {response.text}")
            return False
    except Exception as e:
        print_result("POST /webhooks/retr/import (Agent)", False, str(e))
        return False


def test_lo_import(base_url, secret=None):
    """Test importing a loan officer via webhook."""
    print_section("Testing Loan Officer Import")

    lo_payload = {
        "FirstName": "Michael",
        "LastName": "Chen",
        "FullName": "Michael Chen",
        "Email": f"mchen.test.{datetime.now().strftime('%H%M%S')}@mortgage.com",
        "Phone": "555-987-6543",
        "Company": "Competitor Mortgage LLC",
        "RETRLoanOfficerId": f"LO-TEST-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "RetrProfileURL": "https://retr.app/lo/LO-TEST-67890",
        "NMLSID": "9876543",
        "UnitsLast12Mo": 65,
        "VolumeLast12Mo": 22500000.00,
        "UnitsLast24Mo": 120,
        "VolumeLast24Mo": 41000000.00,
        "AvgLoanSize": 346154.00,
        "PurchasePct": 72.0,
        "RefiPct": 28.0,
        "City": "Atlanta",
        "State": "GA",
        "ZipCode": "30301",
        "YearsExperience": 8,
        "LinkedIn": "https://linkedin.com/in/mchen-lo",
        "Tags": "High Volume, Purchase Focus, Georgia Market"
    }

    headers = {"Content-Type": "application/json"}
    if secret:
        headers["X-Webhook-Secret"] = secret

    print(f"Sending LO payload:")
    print(f"  Name: {lo_payload['FirstName']} {lo_payload['LastName']}")
    print(f"  Email: {lo_payload['Email']}")
    print(f"  NMLS: {lo_payload['NMLSID']}")
    print(f"  RETR ID: {lo_payload['RETRLoanOfficerId']}")
    print(f"  Units (12mo): {lo_payload['UnitsLast12Mo']}")
    print(f"  Volume (12mo): ${lo_payload['VolumeLast12Mo']:,.2f}")

    try:
        response = requests.post(
            f"{base_url}/webhooks/retr/import",
            headers=headers,
            json=lo_payload,
            timeout=30
        )

        # 202 Accepted is the expected response
        success = response.status_code == 202

        if success:
            print_result("POST /webhooks/retr/import (LO)", True)
            print(f"       Response: {response.text}")
            return True
        else:
            print_result("POST /webhooks/retr/import (LO)", False,
                        f"Status: {response.status_code}, Body: {response.text}")
            return False
    except Exception as e:
        print_result("POST /webhooks/retr/import (LO)", False, str(e))
        return False


def test_batch_import(base_url, secret=None):
    """Test importing multiple records at once."""
    print_section("Testing Batch Import (Multiple Records)")

    batch_payload = [
        {
            "FirstName": "Agent",
            "LastName": "One",
            "Email": f"agent1.test.{datetime.now().strftime('%H%M%S')}@test.com",
            "RETRAgentId": "AGT-BATCH-001",
            "TotalVol_12Mo": 5000000.00,
        },
        {
            "FirstName": "Agent",
            "LastName": "Two",
            "Email": f"agent2.test.{datetime.now().strftime('%H%M%S')}@test.com",
            "RETRAgentId": "AGT-BATCH-002",
            "TotalVol_12Mo": 8000000.00,
        },
        {
            "FirstName": "LO",
            "LastName": "Test",
            "Email": f"lo.test.{datetime.now().strftime('%H%M%S')}@test.com",
            "RETRLoanOfficerId": "LO-BATCH-001",
            "NMLSID": "1111111",
            "UnitsLast12Mo": 40,
            "VolumeLast12Mo": 15000000.00,
        }
    ]

    headers = {"Content-Type": "application/json"}
    if secret:
        headers["X-Webhook-Secret"] = secret

    print(f"Sending batch of {len(batch_payload)} records (2 agents, 1 LO)")

    try:
        response = requests.post(
            f"{base_url}/webhooks/retr/import",
            headers=headers,
            json=batch_payload,
            timeout=30
        )

        success = response.status_code == 202

        if success:
            print_result("POST /webhooks/retr/import (Batch)", True)
            print(f"       Response: {response.text}")
            return True
        else:
            print_result("POST /webhooks/retr/import (Batch)", False,
                        f"Status: {response.status_code}, Body: {response.text}")
            return False
    except Exception as e:
        print_result("POST /webhooks/retr/import (Batch)", False, str(e))
        return False


def run_all_tests(base_url, secret=None):
    """Run all webhook tests."""
    print("\n" + "=" * 60)
    print("  RETR WEBHOOK INTEGRATION TESTS")
    print(f"  Target: {base_url}")
    print("=" * 60)

    results = {
        "Status Endpoint": test_webhook_status(base_url),
        "Agent Import": test_agent_import(base_url, secret),
        "LO Import": test_lo_import(base_url, secret),
        "Batch Import": test_batch_import(base_url, secret),
    }

    print("\n" + "=" * 60)
    print("  TEST RESULTS SUMMARY")
    print("=" * 60)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, result in results.items():
        status = "PASS" if result else "FAIL"
        print(f"  [{status}] {test_name}")

    print("\n" + "-" * 60)
    print(f"  Total: {passed}/{total} tests passed")
    print("=" * 60)

    return passed == total


if __name__ == "__main__":
    # Default to localhost
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    secret = sys.argv[2] if len(sys.argv) > 2 else None

    # Ensure no trailing slash
    base_url = base_url.rstrip("/")

    print(f"\nTarget URL: {base_url}")
    if secret:
        print(f"Using webhook secret: {'*' * len(secret)}")

    success = run_all_tests(base_url, secret)
    sys.exit(0 if success else 1)
