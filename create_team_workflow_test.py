#!/usr/bin/env python3
"""
Test script to create 10 team members with different roles, workflows, and tasks
"""

import requests
import json
from datetime import datetime, timedelta

API_BASE = "https://app.perenniaai.com"

# Team member definitions
TEAM_MEMBERS = [
    {
        "first_name": "Sarah",
        "last_name": "Johnson",
        "email": "sarah.johnson@example.com",
        "phone": "(555) 101-0001",
        "role": "Sales",
        "title": "Senior Loan Officer",
        "password": "Sales2024!",
        "responsibilities": [
            {
                "title": "Lead Generation & Qualification",
                "description": "Identify and qualify potential mortgage leads through various channels",
                "key_activities": ["Cold calling prospects", "Networking events", "Referral follow-up", "Lead database management"]
            },
            {
                "title": "Client Consultation",
                "description": "Meet with clients to understand their needs and recommend mortgage solutions",
                "key_activities": ["Initial consultations", "Needs assessment", "Product recommendations", "Pre-qualification"]
            },
            {
                "title": "Application Management",
                "description": "Guide clients through the application process",
                "key_activities": ["Application completion", "Document collection", "Status updates", "Client communication"]
            }
        ],
        "tasks": [
            {"name": "Follow up with 10 warm leads", "priority": "High", "due_days": 1},
            {"name": "Schedule 5 client consultations this week", "priority": "High", "due_days": 2},
            {"name": "Complete CRM updates for active prospects", "priority": "Medium", "due_days": 3},
            {"name": "Review and respond to rate inquiries", "priority": "High", "due_days": 1},
            {"name": "Prepare monthly sales report", "priority": "Medium", "due_days": 7}
        ]
    },
    {
        "first_name": "Michael",
        "last_name": "Chen",
        "email": "michael.chen@example.com",
        "phone": "(555) 101-0002",
        "role": "Sales",
        "title": "Loan Officer",
        "password": "Sales2024!",
        "responsibilities": [
            {
                "title": "New Client Acquisition",
                "description": "Develop and maintain pipeline of new mortgage opportunities",
                "key_activities": ["Prospecting", "Networking", "Partnership development", "Marketing campaigns"]
            },
            {
                "title": "Loan Structuring",
                "description": "Design optimal loan solutions for clients",
                "key_activities": ["Rate analysis", "Product selection", "Terms negotiation", "Scenario modeling"]
            }
        ],
        "tasks": [
            {"name": "Contact 20 new leads from marketing campaign", "priority": "High", "due_days": 2},
            {"name": "Prepare rate quotes for 5 active clients", "priority": "High", "due_days": 1},
            {"name": "Attend realtor networking event", "priority": "Medium", "due_days": 4},
            {"name": "Update pipeline status in CRM", "priority": "Medium", "due_days": 2}
        ]
    },
    {
        "first_name": "Emily",
        "last_name": "Rodriguez",
        "email": "emily.rodriguez@example.com",
        "phone": "(555) 101-0003",
        "role": "Production Assistant",
        "title": "Senior Production Coordinator",
        "password": "Prod2024!",
        "responsibilities": [
            {
                "title": "File Management & Coordination",
                "description": "Manage loan files from application to closing",
                "key_activities": ["File setup", "Document tracking", "Milestone monitoring", "Team coordination"]
            },
            {
                "title": "Underwriting Support",
                "description": "Prepare files for underwriting and respond to conditions",
                "key_activities": ["Condition clearance", "Document verification", "Underwriter communication", "File packaging"]
            },
            {
                "title": "Closing Coordination",
                "description": "Ensure smooth closing process",
                "key_activities": ["Closing document review", "Title company coordination", "Final conditions", "Funding preparation"]
            }
        ],
        "tasks": [
            {"name": "Clear 8 underwriting conditions on Johnson file", "priority": "High", "due_days": 1},
            {"name": "Coordinate appraisal for 3 new files", "priority": "High", "due_days": 2},
            {"name": "Prepare closing documents for Smith closing", "priority": "High", "due_days": 3},
            {"name": "Follow up on pending verifications", "priority": "Medium", "due_days": 2},
            {"name": "Update loan status dashboard", "priority": "Low", "due_days": 5}
        ]
    },
    {
        "first_name": "David",
        "last_name": "Thompson",
        "email": "david.thompson@example.com",
        "phone": "(555) 101-0004",
        "role": "Production Assistant",
        "title": "Production Coordinator",
        "password": "Prod2024!",
        "responsibilities": [
            {
                "title": "Application Processing",
                "description": "Process incoming loan applications",
                "key_activities": ["Application intake", "Initial review", "Setup in system", "LO coordination"]
            },
            {
                "title": "Document Collection",
                "description": "Gather required documentation from borrowers",
                "key_activities": ["Document requests", "Borrower follow-up", "Document review", "File completion"]
            }
        ],
        "tasks": [
            {"name": "Process 5 new applications received today", "priority": "High", "due_days": 1},
            {"name": "Request missing docs from 7 borrowers", "priority": "High", "due_days": 1},
            {"name": "Complete file review for Davis application", "priority": "Medium", "due_days": 2},
            {"name": "Update application tracking system", "priority": "Low", "due_days": 3}
        ]
    },
    {
        "first_name": "Jessica",
        "last_name": "Martinez",
        "email": "jessica.martinez@example.com",
        "phone": "(555) 101-0005",
        "role": "Concierge",
        "title": "Client Experience Specialist",
        "password": "Concierge2024!",
        "responsibilities": [
            {
                "title": "Client Communication",
                "description": "Maintain regular communication with borrowers throughout the loan process",
                "key_activities": ["Status updates", "Expectation setting", "Question handling", "Proactive outreach"]
            },
            {
                "title": "Experience Management",
                "description": "Ensure exceptional client experience from application to closing",
                "key_activities": ["Welcome calls", "Process education", "Issue resolution", "Closing preparation"]
            },
            {
                "title": "Feedback Collection",
                "description": "Gather client feedback and reviews",
                "key_activities": ["Post-closing surveys", "Review requests", "Testimonial collection", "Experience analysis"]
            }
        ],
        "tasks": [
            {"name": "Welcome calls for 3 new borrowers", "priority": "High", "due_days": 1},
            {"name": "Send weekly status updates to 15 active borrowers", "priority": "High", "due_days": 2},
            {"name": "Follow up on client inquiries from yesterday", "priority": "High", "due_days": 1},
            {"name": "Request reviews from 5 recent closings", "priority": "Medium", "due_days": 3},
            {"name": "Prepare closing gift packages", "priority": "Low", "due_days": 4}
        ]
    },
    {
        "first_name": "Robert",
        "last_name": "Lee",
        "email": "robert.lee@example.com",
        "phone": "(555) 101-0006",
        "role": "Processor",
        "title": "Senior Loan Processor",
        "password": "Process2024!",
        "responsibilities": [
            {
                "title": "File Review & Validation",
                "description": "Comprehensive review of loan files for completeness and accuracy",
                "key_activities": ["Document verification", "Income analysis", "Asset verification", "Credit review"]
            },
            {
                "title": "Underwriting Preparation",
                "description": "Prepare loan files for underwriting submission",
                "key_activities": ["AUS submission", "File packaging", "Supporting documentation", "Quality assurance"]
            },
            {
                "title": "Condition Management",
                "description": "Track and clear underwriting conditions",
                "key_activities": ["Condition tracking", "Document requests", "Borrower coordination", "Underwriter communication"]
            }
        ],
        "tasks": [
            {"name": "Submit 4 files to underwriting", "priority": "High", "due_days": 1},
            {"name": "Review income documentation for Wilson file", "priority": "High", "due_days": 1},
            {"name": "Clear 12 conditions across active files", "priority": "High", "due_days": 2},
            {"name": "Quality check Anderson file before submission", "priority": "Medium", "due_days": 2},
            {"name": "Coordinate with appraiser on 3 files", "priority": "Medium", "due_days": 3}
        ]
    },
    {
        "first_name": "Amanda",
        "last_name": "White",
        "email": "amanda.white@example.com",
        "phone": "(555) 101-0007",
        "role": "Processor",
        "title": "Loan Processor",
        "password": "Process2024!",
        "responsibilities": [
            {
                "title": "Initial Processing",
                "description": "Initial processing of new loan applications",
                "key_activities": ["Application review", "Document organization", "Disclosures", "Initial setup"]
            },
            {
                "title": "Verification Coordination",
                "description": "Coordinate employment and income verifications",
                "key_activities": ["VOE requests", "Income verification", "Employment confirmation", "Follow-up"]
            }
        ],
        "tasks": [
            {"name": "Process 6 new applications", "priority": "High", "due_days": 1},
            {"name": "Send out 10 employment verifications", "priority": "High", "due_days": 1},
            {"name": "Review and organize documents for Thompson file", "priority": "Medium", "due_days": 2},
            {"name": "Follow up on pending verifications", "priority": "Medium", "due_days": 2}
        ]
    },
    {
        "first_name": "Kevin",
        "last_name": "Brown",
        "email": "kevin.brown@example.com",
        "phone": "(555) 101-0008",
        "role": "Processor Assistant",
        "title": "Processing Support Specialist",
        "password": "ProcAsst2024!",
        "responsibilities": [
            {
                "title": "Document Management",
                "description": "Organize and maintain loan file documentation",
                "key_activities": ["Document scanning", "File organization", "Index management", "Quality checks"]
            },
            {
                "title": "Administrative Support",
                "description": "Provide administrative support to processors",
                "key_activities": ["Data entry", "File maintenance", "Report generation", "System updates"]
            }
        ],
        "tasks": [
            {"name": "Scan and index documents for 15 files", "priority": "High", "due_days": 1},
            {"name": "Update loan status in system for 20 files", "priority": "Medium", "due_days": 2},
            {"name": "Generate weekly processing report", "priority": "Medium", "due_days": 3},
            {"name": "Organize digital files for archived loans", "priority": "Low", "due_days": 5}
        ]
    },
    {
        "first_name": "Rachel",
        "last_name": "Davis",
        "email": "rachel.davis@example.com",
        "phone": "(555) 101-0009",
        "role": "Processor Assistant",
        "title": "Junior Processing Assistant",
        "password": "ProcAsst2024!",
        "responsibilities": [
            {
                "title": "File Preparation",
                "description": "Prepare files for processor review",
                "key_activities": ["Initial document review", "Missing document identification", "Borrower outreach", "File setup"]
            }
        ],
        "tasks": [
            {"name": "Review 10 new files for completeness", "priority": "High", "due_days": 1},
            {"name": "Request missing documents from borrowers", "priority": "High", "due_days": 1},
            {"name": "Set up 8 new files in system", "priority": "Medium", "due_days": 2},
            {"name": "Assist processors with condition clearance", "priority": "Medium", "due_days": 2}
        ]
    },
    {
        "first_name": "Lisa",
        "last_name": "Anderson",
        "email": "lisa.anderson@example.com",
        "phone": "(555) 101-0010",
        "role": "Executive Assistant",
        "title": "Executive Assistant to Branch Manager",
        "password": "ExecAsst2024!",
        "responsibilities": [
            {
                "title": "Executive Support",
                "description": "Provide comprehensive administrative support to branch leadership",
                "key_activities": ["Calendar management", "Meeting coordination", "Correspondence", "Travel arrangements"]
            },
            {
                "title": "Team Coordination",
                "description": "Coordinate team activities and communication",
                "key_activities": ["Team meetings", "Event planning", "Communication distribution", "Schedule coordination"]
            },
            {
                "title": "Reporting & Analytics",
                "description": "Prepare reports and analytics for leadership",
                "key_activities": ["Data compilation", "Report generation", "Presentation preparation", "Metrics tracking"]
            }
        ],
        "tasks": [
            {"name": "Prepare weekly production report for manager", "priority": "High", "due_days": 2},
            {"name": "Schedule and coordinate monthly team meeting", "priority": "High", "due_days": 3},
            {"name": "Compile Q4 performance metrics", "priority": "Medium", "due_days": 5},
            {"name": "Organize client appreciation event", "priority": "Medium", "due_days": 7},
            {"name": "Update team contact directory", "priority": "Low", "due_days": 5}
        ]
    }
]

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

def create_team_member(member_data, token):
    """Create a team member via API"""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # Create the team member
    team_member_payload = {
        "first_name": member_data["first_name"],
        "last_name": member_data["last_name"],
        "email": member_data["email"],
        "phone": member_data["phone"],
        "role": member_data["role"],
        "title": member_data.get("title")
    }

    print(f"Creating team member: {member_data['first_name']} {member_data['last_name']} ({member_data['role']})")

    response = requests.post(
        f"{API_BASE}/api/v1/team/members",
        headers=headers,
        json=team_member_payload
    )

    if response.status_code in [200, 201]:
        member = response.json()
        print(f"  ✓ Team member created with ID: {member.get('id')}")
        return member
    else:
        print(f"  ✗ Failed to create team member: {response.text}")
        return None

def create_responsibilities(member_data, user_id, token):
    """Create responsibilities for a team member"""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    print(f"  Creating {len(member_data.get('responsibilities', []))} responsibilities...")

    for resp in member_data.get('responsibilities', []):
        payload = {
            "title": resp["title"],
            "description": resp["description"],
            "key_activities": resp.get("key_activities", [])
        }

        response = requests.post(
            f"{API_BASE}/api/v1/users/{user_id}/responsibilities",
            headers=headers,
            json=payload
        )

        if response.status_code in [200, 201]:
            print(f"    ✓ Created: {resp['title']}")
        else:
            print(f"    ✗ Failed to create responsibility: {resp['title']}")

def create_tasks(member_data, user_id, token):
    """Create tasks for a team member"""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    print(f"  Creating {len(member_data.get('tasks', []))} tasks...")

    for task in member_data.get('tasks', []):
        due_date = (datetime.now() + timedelta(days=task['due_days'])).isoformat()

        # Create as a goal with tasks
        payload = {
            "title": task["name"],
            "description": f"Priority: {task['priority']}",
            "category": "daily_tasks",
            "target_date": due_date,
            "status": "active"
        }

        response = requests.post(
            f"{API_BASE}/api/v1/users/{user_id}/goals",
            headers=headers,
            json=payload
        )

        if response.status_code in [200, 201]:
            print(f"    ✓ Created: {task['name']} (Due: {task['due_days']} days)")
        else:
            print(f"    ✗ Failed to create task: {task['name']}")

def main():
    """Main execution"""
    print("=" * 80)
    print("MORTGAGE CRM - TEAM WORKFLOW TEST")
    print("Creating 10 team members with roles, responsibilities, and tasks")
    print("=" * 80)
    print()

    # Get authentication token
    token = get_auth_token()
    if not token:
        return

    # Summary counters
    created_members = 0
    created_responsibilities = 0
    created_tasks = 0

    # Create each team member
    for member_data in TEAM_MEMBERS:
        print("-" * 80)
        member = create_team_member(member_data, token)

        if member and member.get('id'):
            created_members += 1
            user_id = member['id']

            # Create responsibilities
            if 'responsibilities' in member_data:
                create_responsibilities(member_data, user_id, token)
                created_responsibilities += len(member_data['responsibilities'])

            # Create tasks
            if 'tasks' in member_data:
                create_tasks(member_data, user_id, token)
                created_tasks += len(member_data['tasks'])

            print()

    # Print summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"✓ Team Members Created: {created_members}/10")
    print(f"✓ Responsibilities Created: {created_responsibilities}")
    print(f"✓ Tasks/Goals Created: {created_tasks}")
    print()
    print("Team Breakdown:")
    print("  - Sales: 2 (Sarah Johnson, Michael Chen)")
    print("  - Production Assistants: 2 (Emily Rodriguez, David Thompson)")
    print("  - Concierge: 1 (Jessica Martinez)")
    print("  - Processors: 2 (Robert Lee, Amanda White)")
    print("  - Processor Assistants: 2 (Kevin Brown, Rachel Davis)")
    print("  - Executive Assistant: 1 (Lisa Anderson)")
    print()
    print("Login Credentials (all passwords):")
    print("  - Sales: Sales2024!")
    print("  - Production Assistant: Prod2024!")
    print("  - Concierge: Concierge2024!")
    print("  - Processor: Process2024!")
    print("  - Processor Assistant: ProcAsst2024!")
    print("  - Executive Assistant: ExecAsst2024!")
    print()
    print("You can now impersonate these users to view their workflows!")
    print("=" * 80)

if __name__ == "__main__":
    main()
