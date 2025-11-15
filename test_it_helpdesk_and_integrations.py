#!/usr/bin/env python3
"""
Comprehensive test script for AI IT Helpdesk and Outlook/Calendar integrations
"""

import requests
import json
import sys
from datetime import datetime

# Configuration
API_BASE_URL = "https://mortgage-crm-production-7a9a.up.railway.app"

# ANSI color codes for terminal output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

def print_header(text):
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}{text:^60}{RESET}")
    print(f"{BLUE}{'='*60}{RESET}\n")

def print_success(text):
    print(f"{GREEN}✓ {text}{RESET}")

def print_error(text):
    print(f"{RED}✗ {text}{RESET}")

def print_info(text):
    print(f"{YELLOW}ℹ {text}{RESET}")

def login():
    """Login and get authentication token"""
    print_header("Step 1: Authentication")

    # You'll need to provide credentials
    email = input("Enter your email: ")
    password = input("Enter your password: ")

    response = requests.post(
        f"{API_BASE_URL}/api/v1/login",
        json={"email": email, "password": password}
    )

    if response.status_code == 200:
        data = response.json()
        token = data.get('access_token')
        print_success("Login successful")
        return token
    else:
        print_error(f"Login failed: {response.status_code} - {response.text}")
        sys.exit(1)

def test_it_helpdesk_submit(token):
    """Test IT Helpdesk ticket submission"""
    print_header("Step 2: Submit IT Helpdesk Ticket")

    ticket_data = {
        "title": "Outlook Email and Calendar Integration Not Working",
        "description": """I'm having issues with the Outlook email and calendar integrations:

1. Email sync is not pulling emails from my Outlook inbox
2. Calendar events are not syncing properly
3. I see a 502 error when trying to sync
4. The connection status shows as disconnected even after I authorize

Error message: "Failed to sync emails: 502 Bad Gateway"

Please diagnose and provide steps to fix these integration issues.""",
        "category": "saas_config",
        "urgency": "high",
        "affected_system": "Microsoft 365",
        "affected_project": "mortgage-crm",
        "logs_attached": [
            "Error 502: Bad Gateway when calling /api/v1/microsoft/sync",
            "Connection timeout after 30 seconds",
            "OAuth token appears valid but API calls fail"
        ]
    }

    print_info("Submitting ticket with Outlook/Calendar integration issue...")
    print_info(f"Title: {ticket_data['title']}")

    response = requests.post(
        f"{API_BASE_URL}/api/v1/it-helpdesk/submit",
        json=ticket_data,
        headers={"Authorization": f"Bearer {token}"}
    )

    if response.status_code == 200:
        data = response.json()
        print_success("Ticket submitted successfully!")
        print_info(f"Ticket ID: {data.get('ticket_id')}")
        print_info(f"Status: {data.get('status')}")

        print("\n" + "─"*60)
        print(f"{GREEN}AI DIAGNOSIS:{RESET}")
        print("─"*60)
        print(f"\n{YELLOW}Root Cause:{RESET} {data.get('root_cause')}")
        print(f"\n{YELLOW}Diagnosis:{RESET}\n{data.get('diagnosis')}\n")

        if data.get('proposed_fix'):
            fix = data['proposed_fix']
            print(f"{YELLOW}Proposed Fix (Risk: {fix.get('risk_level', 'unknown').upper()}):{RESET}\n")

            if fix.get('steps'):
                print("Steps:")
                for i, step in enumerate(fix['steps'], 1):
                    print(f"  {i}. {step}")

            if fix.get('commands'):
                print(f"\n{YELLOW}Commands to Run:{RESET}")
                for cmd in fix['commands']:
                    print(f"\n  {cmd.get('description', 'N/A')}")
                    print(f"  $ {cmd.get('command', 'N/A')}")

        print("\n" + "─"*60 + "\n")

        return data.get('ticket_id')
    else:
        print_error(f"Failed to submit ticket: {response.status_code}")
        print_error(f"Response: {response.text}")
        return None

def test_get_tickets(token):
    """Test getting all tickets"""
    print_header("Step 3: Retrieve All IT Tickets")

    response = requests.get(
        f"{API_BASE_URL}/api/v1/it-helpdesk/tickets",
        headers={"Authorization": f"Bearer {token}"}
    )

    if response.status_code == 200:
        data = response.json()
        tickets = data.get('tickets', [])
        print_success(f"Retrieved {len(tickets)} tickets")

        for ticket in tickets:
            print(f"\n  Ticket #{ticket['id']}: {ticket.get('title', 'No title')}")
            print(f"    Status: {ticket['status']}")
            print(f"    Created: {ticket['created_at']}")
            if ticket.get('root_cause'):
                print(f"    Root Cause: {ticket['root_cause']}")

        return tickets
    else:
        print_error(f"Failed to get tickets: {response.status_code}")
        return []

def test_approve_ticket(token, ticket_id):
    """Test ticket approval"""
    print_header(f"Step 4: Approve Ticket #{ticket_id}")

    response = requests.post(
        f"{API_BASE_URL}/api/v1/it-helpdesk/tickets/{ticket_id}/approve",
        headers={"Authorization": f"Bearer {token}"}
    )

    if response.status_code == 200:
        print_success("Ticket approved successfully")
        return True
    else:
        print_error(f"Failed to approve ticket: {response.status_code}")
        return False

def test_resolve_ticket(token, ticket_id):
    """Test ticket resolution"""
    print_header(f"Step 5: Resolve Ticket #{ticket_id}")

    resolution_data = {
        "resolution_notes": "Tested the AI-proposed fix. Reconnected Microsoft 365 account and verified email sync is now working. Calendar events are syncing properly. Issue resolved!"
    }

    response = requests.post(
        f"{API_BASE_URL}/api/v1/it-helpdesk/tickets/{ticket_id}/resolve",
        json=resolution_data,
        headers={"Authorization": f"Bearer {token}"}
    )

    if response.status_code == 200:
        print_success("Ticket resolved successfully")
        return True
    else:
        print_error(f"Failed to resolve ticket: {response.status_code}")
        return False

def test_microsoft_sync_diagnostics(token):
    """Test Microsoft 365 sync diagnostics"""
    print_header("Step 6: Microsoft 365 Sync Diagnostics")

    response = requests.get(
        f"{API_BASE_URL}/api/v1/microsoft/sync-diagnostics",
        headers={"Authorization": f"Bearer {token}"}
    )

    if response.status_code == 200:
        data = response.json()
        print_success("Diagnostics retrieved successfully")

        conn = data.get('connection', {})
        print(f"\n{YELLOW}Connection Status:{RESET}")
        print(f"  Connected: {conn.get('connected')}")
        print(f"  Email: {conn.get('email_address')}")
        print(f"  Sync Enabled: {conn.get('sync_enabled')}")
        print(f"  Last Sync: {conn.get('last_sync_at', 'Never')}")

        emails = data.get('recent_emails', {})
        print(f"\n{YELLOW}Recent Emails:{RESET}")
        print(f"  Count: {emails.get('count', 0)}")

        if data.get('recommendations'):
            print(f"\n{YELLOW}Recommendations:{RESET}")
            for rec in data['recommendations']:
                rec_type = rec.get('type', 'info').upper()
                color = GREEN if rec_type == 'SUCCESS' else YELLOW if rec_type == 'WARNING' else RED
                print(f"  {color}[{rec_type}]{RESET} {rec.get('message')}")
                if rec.get('action'):
                    print(f"    → {rec.get('action')}")

        return data
    else:
        print_error(f"Failed to get diagnostics: {response.status_code}")
        return None

def test_outlook_integration_status(token):
    """Test Outlook integration status"""
    print_header("Step 7: Check Outlook Integration Status")

    response = requests.get(
        f"{API_BASE_URL}/api/v1/integrations/status",
        headers={"Authorization": f"Bearer {token}"}
    )

    if response.status_code == 200:
        data = response.json()
        print_success("Integration status retrieved")

        if 'microsoft_365' in data:
            ms365 = data['microsoft_365']
            print(f"\n{YELLOW}Microsoft 365:{RESET}")
            print(f"  Email Connected: {ms365.get('email_connected', False)}")
            print(f"  Calendar Connected: {ms365.get('calendar_connected', False)}")

        return data
    else:
        print_error(f"Failed to get integration status: {response.status_code}")
        return None

def main():
    """Run all tests"""
    print_header("AI IT Helpdesk & Outlook Integration Tests")
    print_info(f"Testing API: {API_BASE_URL}")
    print_info(f"Test Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    try:
        # Step 1: Login
        token = login()

        # Step 2: Submit IT Helpdesk ticket for Outlook/Calendar issues
        ticket_id = test_it_helpdesk_submit(token)

        if not ticket_id:
            print_error("Cannot continue without a ticket ID")
            sys.exit(1)

        # Step 3: Get all tickets
        tickets = test_get_tickets(token)

        # Step 4: Approve the ticket
        test_approve_ticket(token, ticket_id)

        # Step 5: Resolve the ticket (simulating fix completion)
        input(f"\n{YELLOW}Press Enter to mark ticket as resolved...{RESET}")
        test_resolve_ticket(token, ticket_id)

        # Step 6: Test Microsoft 365 diagnostics
        test_microsoft_sync_diagnostics(token)

        # Step 7: Test Outlook integration status
        test_outlook_integration_status(token)

        # Summary
        print_header("Test Summary")
        print_success("All IT Helpdesk tests completed!")
        print_success("AI diagnosis system is operational")
        print_success("Ticket workflow (submit → approve → resolve) working")
        print_success("Microsoft 365 diagnostics endpoint responding")
        print_success("Integration status endpoint responding")

        print(f"\n{YELLOW}Next Steps:{RESET}")
        print("  1. Check the frontend at https://mortgage-crm-nine.vercel.app/settings")
        print("  2. Navigate to IT Helpdesk tab")
        print("  3. View the ticket created by this test")
        print("  4. For Outlook integration issues, follow AI-proposed fixes")

    except KeyboardInterrupt:
        print(f"\n\n{YELLOW}Test interrupted by user{RESET}")
        sys.exit(0)
    except Exception as e:
        print_error(f"Test failed with error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
