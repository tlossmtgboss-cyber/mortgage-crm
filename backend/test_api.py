"""
API Testing Script for Mortgage CRM
Tests all endpoints to verify functionality
"""

import requests
import json
from datetime import datetime

BASE_URL = "http://localhost:8000"
TOKEN = None

def print_section(title):
    print("\n" + "="*60)
    print(f"  {title}")
    print("="*60)

def print_result(test_name, success, response=None):
    status = "✅" if success else "❌"
    print(f"{status} {test_name}")
    if response and not success:
        print(f"   Error: {response.text if hasattr(response, 'text') else response}")

def test_health_check():
    print_section("Testing Health Check")
    try:
        response = requests.get(f"{BASE_URL}/health")
        success = response.status_code == 200
        print_result("Health Check", success, response)
        if success:
            print(f"   {response.json()}")
        return success
    except Exception as e:
        print_result("Health Check", False, str(e))
        return False

def test_login():
    global TOKEN
    print_section("Testing Authentication")

    # Test login with demo account
    try:
        response = requests.post(
            f"{BASE_URL}/token",
            data={
                "username": "demo@example.com",
                "password": "demo123"
            }
        )
        success = response.status_code == 200
        print_result("Login with demo account", success, response)

        if success:
            data = response.json()
            TOKEN = data.get("access_token")
            print(f"   Token received: {TOKEN[:20]}...")
            return True
        return False
    except Exception as e:
        print_result("Login", False, str(e))
        return False

def test_dashboard():
    print_section("Testing Dashboard")
    try:
        headers = {"Authorization": f"Bearer {TOKEN}"}
        response = requests.get(f"{BASE_URL}/api/v1/dashboard", headers=headers)
        success = response.status_code == 200
        print_result("Get Dashboard", success, response)

        if success:
            data = response.json()
            print(f"   User: {data['user']['name']}")
            print(f"   Total Leads: {data['stats']['total_leads']}")
            print(f"   Active Loans: {data['stats']['active_loans']}")
        return success
    except Exception as e:
        print_result("Dashboard", False, str(e))
        return False

def test_leads():
    print_section("Testing Leads CRUD")
    headers = {"Authorization": f"Bearer {TOKEN}"}
    lead_id = None

    # CREATE
    try:
        lead_data = {
            "name": "Test Lead",
            "email": "testlead@example.com",
            "phone": "555-9999",
            "credit_score": 750,
            "preapproval_amount": 500000,
            "loan_type": "Purchase"
        }
        response = requests.post(f"{BASE_URL}/api/v1/leads/", json=lead_data, headers=headers)
        success = response.status_code == 201
        print_result("Create Lead", success, response)

        if success:
            lead = response.json()
            lead_id = lead["id"]
            print(f"   Lead ID: {lead_id}, AI Score: {lead['ai_score']}")
    except Exception as e:
        print_result("Create Lead", False, str(e))

    # READ
    try:
        response = requests.get(f"{BASE_URL}/api/v1/leads/", headers=headers)
        success = response.status_code == 200
        print_result("List Leads", success, response)

        if success:
            leads = response.json()
            print(f"   Total leads: {len(leads)}")
    except Exception as e:
        print_result("List Leads", False, str(e))

    # UPDATE
    if lead_id:
        try:
            update_data = {"notes": "Updated via API test"}
            response = requests.patch(f"{BASE_URL}/api/v1/leads/{lead_id}", json=update_data, headers=headers)
            success = response.status_code == 200
            print_result("Update Lead", success, response)
        except Exception as e:
            print_result("Update Lead", False, str(e))

    # DELETE
    if lead_id:
        try:
            response = requests.delete(f"{BASE_URL}/api/v1/leads/{lead_id}", headers=headers)
            success = response.status_code == 204
            print_result("Delete Lead", success, response)
        except Exception as e:
            print_result("Delete Lead", False, str(e))

def test_loans():
    print_section("Testing Loans CRUD")
    headers = {"Authorization": f"Bearer {TOKEN}"}

    try:
        loan_data = {
            "loan_number": f"TEST-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "borrower_name": "Test Borrower",
            "amount": 450000,
            "program": "Conventional",
            "rate": 6.875
        }
        response = requests.post(f"{BASE_URL}/api/v1/loans/", json=loan_data, headers=headers)
        success = response.status_code == 201
        print_result("Create Loan", success, response)

        if success:
            loan = response.json()
            print(f"   Loan Number: {loan['loan_number']}")
            print(f"   AI Insights: {loan.get('ai_insights', 'N/A')}")
    except Exception as e:
        print_result("Create Loan", False, str(e))

    try:
        response = requests.get(f"{BASE_URL}/api/v1/loans/", headers=headers)
        success = response.status_code == 200
        print_result("List Loans", success, response)

        if success:
            loans = response.json()
            print(f"   Total loans: {len(loans)}")
    except Exception as e:
        print_result("List Loans", False, str(e))

def test_tasks():
    print_section("Testing Tasks CRUD")
    headers = {"Authorization": f"Bearer {TOKEN}"}

    try:
        task_data = {
            "title": "Test Task",
            "description": "This is a test task",
            "priority": "high"
        }
        response = requests.post(f"{BASE_URL}/api/v1/tasks/", json=task_data, headers=headers)
        success = response.status_code == 201
        print_result("Create Task", success, response)

        if success:
            task = response.json()
            print(f"   Task ID: {task['id']}, Priority: {task['priority']}")
    except Exception as e:
        print_result("Create Task", False, str(e))

    try:
        response = requests.get(f"{BASE_URL}/api/v1/tasks/", headers=headers)
        success = response.status_code == 200
        print_result("List Tasks", success, response)

        if success:
            tasks = response.json()
            print(f"   Total tasks: {len(tasks)}")
    except Exception as e:
        print_result("List Tasks", False, str(e))

def test_referral_partners():
    print_section("Testing Referral Partners CRUD")
    headers = {"Authorization": f"Bearer {TOKEN}"}

    try:
        partner_data = {
            "name": "Test Realtor",
            "company": "Test Realty",
            "type": "Real Estate Agent",
            "email": "realtor@test.com"
        }
        response = requests.post(f"{BASE_URL}/api/v1/referral-partners/", json=partner_data, headers=headers)
        success = response.status_code == 201
        print_result("Create Referral Partner", success, response)

        if success:
            partner = response.json()
            print(f"   Partner ID: {partner['id']}, Name: {partner['name']}")
    except Exception as e:
        print_result("Create Referral Partner", False, str(e))

    try:
        response = requests.get(f"{BASE_URL}/api/v1/referral-partners/", headers=headers)
        success = response.status_code == 200
        print_result("List Referral Partners", success, response)

        if success:
            partners = response.json()
            print(f"   Total partners: {len(partners)}")
    except Exception as e:
        print_result("List Referral Partners", False, str(e))

def test_mum_clients():
    print_section("Testing MUM Clients CRUD")
    headers = {"Authorization": f"Bearer {TOKEN}"}

    try:
        client_data = {
            "name": "Test MUM Client",
            "loan_number": f"MUM-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "original_close_date": "2023-06-01T00:00:00",
            "original_rate": 7.5,
            "loan_balance": 400000
        }
        response = requests.post(f"{BASE_URL}/api/v1/mum-clients/", json=client_data, headers=headers)
        success = response.status_code == 201
        print_result("Create MUM Client", success, response)

        if success:
            client = response.json()
            print(f"   Client ID: {client['id']}, Days Since Funding: {client.get('days_since_funding', 'N/A')}")
    except Exception as e:
        print_result("Create MUM Client", False, str(e))

    try:
        response = requests.get(f"{BASE_URL}/api/v1/mum-clients/", headers=headers)
        success = response.status_code == 200
        print_result("List MUM Clients", success, response)

        if success:
            clients = response.json()
            print(f"   Total MUM clients: {len(clients)}")
    except Exception as e:
        print_result("List MUM Clients", False, str(e))

def test_activities():
    print_section("Testing Activities CRUD")
    headers = {"Authorization": f"Bearer {TOKEN}"}

    try:
        activity_data = {
            "type": "Note",
            "content": "This is a test activity note",
            "sentiment": "positive"
        }
        response = requests.post(f"{BASE_URL}/api/v1/activities/", json=activity_data, headers=headers)
        success = response.status_code == 201
        print_result("Create Activity", success, response)

        if success:
            activity = response.json()
            print(f"   Activity ID: {activity['id']}, Type: {activity['type']}")
    except Exception as e:
        print_result("Create Activity", False, str(e))

    try:
        response = requests.get(f"{BASE_URL}/api/v1/activities/", headers=headers)
        success = response.status_code == 200
        print_result("List Activities", success, response)

        if success:
            activities = response.json()
            print(f"   Total activities: {len(activities)}")
    except Exception as e:
        print_result("List Activities", False, str(e))

def test_analytics():
    print_section("Testing Analytics")
    headers = {"Authorization": f"Bearer {TOKEN}"}

    try:
        response = requests.get(f"{BASE_URL}/api/v1/analytics/conversion-funnel", headers=headers)
        success = response.status_code == 200
        print_result("Conversion Funnel", success, response)

        if success:
            data = response.json()
            print(f"   Total Leads: {data.get('total_leads', 0)}")
    except Exception as e:
        print_result("Conversion Funnel", False, str(e))

    try:
        response = requests.get(f"{BASE_URL}/api/v1/analytics/pipeline", headers=headers)
        success = response.status_code == 200
        print_result("Pipeline Analytics", success, response)

        if success:
            data = response.json()
            print(f"   Total Loans: {data.get('total_loans', 0)}")
            print(f"   Total Volume: ${data.get('total_volume', 0):,.2f}")
    except Exception as e:
        print_result("Pipeline Analytics", False, str(e))

def main():
    print("\n" + "="*60)
    print("  MORTGAGE CRM API TEST SUITE")
    print("="*60)
    print(f"\nTesting API at: {BASE_URL}")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Run all tests
    if not test_health_check():
        print("\n❌ Server is not running! Please start the server first.")
        return

    if not test_login():
        print("\n❌ Authentication failed! Cannot continue tests.")
        return

    test_dashboard()
    test_leads()
    test_loans()
    test_tasks()
    test_referral_partners()
    test_mum_clients()
    test_activities()
    test_analytics()

    print("\n" + "="*60)
    print("  TEST SUITE COMPLETED")
    print("="*60)
    print(f"\nFinished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("\n✅ All major features tested!")
    print("\n📚 View full API docs at: http://localhost:8000/docs\n")

if __name__ == "__main__":
    main()
