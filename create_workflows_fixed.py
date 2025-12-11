#!/usr/bin/env python3
"""
Fixed script to create responsibilities and tasks with correct API structure
"""

import requests
import json
from datetime import datetime, timedelta

API_BASE = "https://mortgage-crm-production-7a9a.up.railway.app"

# Get the 10 team members we just created
TEAM_WORKFLOWS = {
    58: {  # Sarah Johnson - Sales
        "responsibilities": [
            {
                "title": "Lead Generation & Qualification",
                "description": "Identify and qualify potential mortgage leads through various channels including cold calling, networking events, referral follow-up, and lead database management",
                "ownership": "individual",
                "priority": "high",
                "effective_date": datetime.now().isoformat(),
                "key_activities": ["Cold calling prospects", "Networking events", "Referral follow-up", "Lead database management"]
            },
            {
                "title": "Client Consultation",
                "description": "Meet with clients to understand their needs and recommend mortgage solutions through initial consultations, needs assessment, product recommendations, and pre-qualification",
                "ownership": "individual",
                "priority": "high",
                "effective_date": datetime.now().isoformat(),
                "key_activities": ["Initial consultations", "Needs assessment", "Product recommendations", "Pre-qualification"]
            },
            {
                "title": "Application Management",
                "description": "Guide clients through the application process including application completion, document collection, status updates, and client communication",
                "ownership": "individual",
                "priority": "high",
                "effective_date": datetime.now().isoformat(),
                "key_activities": ["Application completion", "Document collection", "Status updates", "Client communication"]
            }
        ]
    },
    59: {  # Michael Chen - Sales
        "responsibilities": [
            {
                "title": "New Client Acquisition",
                "description": "Develop and maintain pipeline of new mortgage opportunities through prospecting, networking, partnership development, and marketing campaigns",
                "ownership": "individual",
                "priority": "high",
                "effective_date": datetime.now().isoformat(),
                "key_activities": ["Prospecting", "Networking", "Partnership development", "Marketing campaigns"]
            },
            {
                "title": "Loan Structuring",
                "description": "Design optimal loan solutions for clients through rate analysis, product selection, terms negotiation, and scenario modeling",
                "ownership": "individual",
                "priority": "high",
                "effective_date": datetime.now().isoformat(),
                "key_activities": ["Rate analysis", "Product selection", "Terms negotiation", "Scenario modeling"]
            }
        ]
    },
    60: {  # Emily Rodriguez - Production Assistant
        "responsibilities": [
            {
                "title": "File Management & Coordination",
                "description": "Manage loan files from application to closing through file setup, document tracking, milestone monitoring, and team coordination",
                "ownership": "individual",
                "priority": "high",
                "effective_date": datetime.now().isoformat(),
                "key_activities": ["File setup", "Document tracking", "Milestone monitoring", "Team coordination"]
            },
            {
                "title": "Underwriting Support",
                "description": "Prepare files for underwriting and respond to conditions through condition clearance, document verification, underwriter communication, and file packaging",
                "ownership": "individual",
                "priority": "high",
                "effective_date": datetime.now().isoformat(),
                "key_activities": ["Condition clearance", "Document verification", "Underwriter communication", "File packaging"]
            },
            {
                "title": "Closing Coordination",
                "description": "Ensure smooth closing process through closing document review, title company coordination, final conditions, and funding preparation",
                "ownership": "individual",
                "priority": "high",
                "effective_date": datetime.now().isoformat(),
                "key_activities": ["Closing document review", "Title company coordination", "Final conditions", "Funding preparation"]
            }
        ]
    },
    61: {  # David Thompson - Production Assistant
        "responsibilities": [
            {
                "title": "Application Processing",
                "description": "Process incoming loan applications through application intake, initial review, system setup, and loan officer coordination",
                "ownership": "individual",
                "priority": "high",
                "effective_date": datetime.now().isoformat(),
                "key_activities": ["Application intake", "Initial review", "Setup in system", "LO coordination"]
            },
            {
                "title": "Document Collection",
                "description": "Gather required documentation from borrowers through document requests, borrower follow-up, document review, and file completion",
                "ownership": "individual",
                "priority": "high",
                "effective_date": datetime.now().isoformat(),
                "key_activities": ["Document requests", "Borrower follow-up", "Document review", "File completion"]
            }
        ]
    },
    62: {  # Jessica Martinez - Concierge
        "responsibilities": [
            {
                "title": "Client Communication",
                "description": "Maintain regular communication with borrowers throughout the loan process via status updates, expectation setting, question handling, and proactive outreach",
                "ownership": "individual",
                "priority": "high",
                "effective_date": datetime.now().isoformat(),
                "key_activities": ["Status updates", "Expectation setting", "Question handling", "Proactive outreach"]
            },
            {
                "title": "Experience Management",
                "description": "Ensure exceptional client experience from application to closing through welcome calls, process education, issue resolution, and closing preparation",
                "ownership": "individual",
                "priority": "high",
                "effective_date": datetime.now().isoformat(),
                "key_activities": ["Welcome calls", "Process education", "Issue resolution", "Closing preparation"]
            },
            {
                "title": "Feedback Collection",
                "description": "Gather client feedback and reviews through post-closing surveys, review requests, testimonial collection, and experience analysis",
                "ownership": "individual",
                "priority": "medium",
                "effective_date": datetime.now().isoformat(),
                "key_activities": ["Post-closing surveys", "Review requests", "Testimonial collection", "Experience analysis"]
            }
        ]
    },
    63: {  # Robert Lee - Processor
        "responsibilities": [
            {
                "title": "File Review & Validation",
                "description": "Comprehensive review of loan files for completeness and accuracy through document verification, income analysis, asset verification, and credit review",
                "ownership": "individual",
                "priority": "high",
                "effective_date": datetime.now().isoformat(),
                "key_activities": ["Document verification", "Income analysis", "Asset verification", "Credit review"]
            },
            {
                "title": "Underwriting Preparation",
                "description": "Prepare loan files for underwriting submission through AUS submission, file packaging, supporting documentation, and quality assurance",
                "ownership": "individual",
                "priority": "high",
                "effective_date": datetime.now().isoformat(),
                "key_activities": ["AUS submission", "File packaging", "Supporting documentation", "Quality assurance"]
            },
            {
                "title": "Condition Management",
                "description": "Track and clear underwriting conditions through condition tracking, document requests, borrower coordination, and underwriter communication",
                "ownership": "individual",
                "priority": "high",
                "effective_date": datetime.now().isoformat(),
                "key_activities": ["Condition tracking", "Document requests", "Borrower coordination", "Underwriter communication"]
            }
        ]
    },
    64: {  # Amanda White - Processor
        "responsibilities": [
            {
                "title": "Initial Processing",
                "description": "Initial processing of new loan applications through application review, document organization, disclosures, and initial setup",
                "ownership": "individual",
                "priority": "high",
                "effective_date": datetime.now().isoformat(),
                "key_activities": ["Application review", "Document organization", "Disclosures", "Initial setup"]
            },
            {
                "title": "Verification Coordination",
                "description": "Coordinate employment and income verifications through VOE requests, income verification, employment confirmation, and follow-up",
                "ownership": "individual",
                "priority": "high",
                "effective_date": datetime.now().isoformat(),
                "key_activities": ["VOE requests", "Income verification", "Employment confirmation", "Follow-up"]
            }
        ]
    },
    65: {  # Kevin Brown - Processor Assistant
        "responsibilities": [
            {
                "title": "Document Management",
                "description": "Organize and maintain loan file documentation through document scanning, file organization, index management, and quality checks",
                "ownership": "individual",
                "priority": "medium",
                "effective_date": datetime.now().isoformat(),
                "key_activities": ["Document scanning", "File organization", "Index management", "Quality checks"]
            },
            {
                "title": "Administrative Support",
                "description": "Provide administrative support to processors through data entry, file maintenance, report generation, and system updates",
                "ownership": "individual",
                "priority": "medium",
                "effective_date": datetime.now().isoformat(),
                "key_activities": ["Data entry", "File maintenance", "Report generation", "System updates"]
            }
        ]
    },
    66: {  # Rachel Davis - Processor Assistant
        "responsibilities": [
            {
                "title": "File Preparation",
                "description": "Prepare files for processor review through initial document review, missing document identification, borrower outreach, and file setup",
                "ownership": "individual",
                "priority": "medium",
                "effective_date": datetime.now().isoformat(),
                "key_activities": ["Initial document review", "Missing document identification", "Borrower outreach", "File setup"]
            }
        ]
    },
    67: {  # Lisa Anderson - Executive Assistant
        "responsibilities": [
            {
                "title": "Executive Support",
                "description": "Provide comprehensive administrative support to branch leadership through calendar management, meeting coordination, correspondence, and travel arrangements",
                "ownership": "individual",
                "priority": "high",
                "effective_date": datetime.now().isoformat(),
                "key_activities": ["Calendar management", "Meeting coordination", "Correspondence", "Travel arrangements"]
            },
            {
                "title": "Team Coordination",
                "description": "Coordinate team activities and communication through team meetings, event planning, communication distribution, and schedule coordination",
                "ownership": "individual",
                "priority": "high",
                "effective_date": datetime.now().isoformat(),
                "key_activities": ["Team meetings", "Event planning", "Communication distribution", "Schedule coordination"]
            },
            {
                "title": "Reporting & Analytics",
                "description": "Prepare reports and analytics for leadership through data compilation, report generation, presentation preparation, and metrics tracking",
                "ownership": "individual",
                "priority": "high",
                "effective_date": datetime.now().isoformat(),
                "key_activities": ["Data compilation", "Report generation", "Presentation preparation", "Metrics tracking"]
            }
        ]
    }
}

def get_auth_token():
    """Login and get authentication token"""
    print("Logging in as demo user...")
    response = requests.post(
        f"{API_BASE}/token",
        data={"username": "admin@perenniaai.com", "password": "demo123"},
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )

    if response.status_code == 200:
        token = response.json()["access_token"]
        print("✓ Authentication successful\n")
        return token
    else:
        print(f"✗ Authentication failed: {response.text}")
        return None

def create_responsibilities(user_id, workflows, token):
    """Create responsibilities for a user with correct fields"""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    responsibilities = workflows.get('responsibilities', [])
    print(f"Creating {len(responsibilities)} responsibilities for user {user_id}...")

    created_count = 0
    for resp in responsibilities:
        response = requests.post(
            f"{API_BASE}/api/v1/users/{user_id}/responsibilities",
            headers=headers,
            json=resp
        )

        if response.status_code in [200, 201]:
            print(f"  ✓ Created: {resp['title']}")
            created_count += 1
        else:
            print(f"  ✗ Failed ({response.status_code}): {resp['title']}")
            print(f"    Error: {response.text[:200]}")

    return created_count

def main():
    """Main execution"""
    print("=" * 80)
    print("CREATING RESPONSIBILITIES AND WORKFLOWS FOR TEAM MEMBERS")
    print("=" * 80)
    print()

    token = get_auth_token()
    if not token:
        return

    total_created = 0

    for user_id, workflows in TEAM_WORKFLOWS.items():
        print(f"\n{'='*80}")
        created = create_responsibilities(user_id, workflows, token)
        total_created += created

    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")
    print(f"✓ Total Responsibilities Created: {total_created}")
    print()
    print("All team members now have their workflows and responsibilities configured!")
    print("=" * 80)

if __name__ == "__main__":
    main()
