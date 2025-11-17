#!/usr/bin/env python3
"""
Database seed script to create responsibilities and workflows for the 10 team members
This script runs directly on Railway
"""

import psycopg2
import os
from datetime import datetime
import json

# This will be run via Railway
conn = psycopg2.connect(os.getenv('DATABASE_URL'))
cur = conn.cursor()

# Team workflows data
TEAM_WORKFLOWS = {
    58: {  # Sarah Johnson - Sales
        "name": "Sarah Johnson",
        "role": "Sales",
        "responsibilities": [
            {
                "title": "Lead Generation & Qualification",
                "description": "Identify and qualify potential mortgage leads through various channels including cold calling, networking events, referral follow-up, and lead database management",
                "ownership": "individual",
                "priority": "high",
                "key_activities": ["Cold calling prospects", "Networking events", "Referral follow-up", "Lead database management"]
            },
            {
                "title": "Client Consultation",
                "description": "Meet with clients to understand their needs and recommend mortgage solutions through initial consultations, needs assessment, product recommendations, and pre-qualification",
                "ownership": "individual",
                "priority": "high",
                "key_activities": ["Initial consultations", "Needs assessment", "Product recommendations", "Pre-qualification"]
            },
            {
                "title": "Application Management",
                "description": "Guide clients through the application process including application completion, document collection, status updates, and client communication",
                "ownership": "individual",
                "priority": "high",
                "key_activities": ["Application completion", "Document collection", "Status updates", "Client communication"]
            }
        ]
    },
    59: {  # Michael Chen - Sales
        "name": "Michael Chen",
        "role": "Sales",
        "responsibilities": [
            {
                "title": "New Client Acquisition",
                "description": "Develop and maintain pipeline of new mortgage opportunities through prospecting, networking, partnership development, and marketing campaigns",
                "ownership": "individual",
                "priority": "high",
                "key_activities": ["Prospecting", "Networking", "Partnership development", "Marketing campaigns"]
            },
            {
                "title": "Loan Structuring",
                "description": "Design optimal loan solutions for clients through rate analysis, product selection, terms negotiation, and scenario modeling",
                "ownership": "individual",
                "priority": "high",
                "key_activities": ["Rate analysis", "Product selection", "Terms negotiation", "Scenario modeling"]
            }
        ]
    },
    60: {  # Emily Rodriguez - Production Assistant
        "name": "Emily Rodriguez",
        "role": "Production Assistant",
        "responsibilities": [
            {
                "title": "File Management & Coordination",
                "description": "Manage loan files from application to closing through file setup, document tracking, milestone monitoring, and team coordination",
                "ownership": "individual",
                "priority": "high",
                "key_activities": ["File setup", "Document tracking", "Milestone monitoring", "Team coordination"]
            },
            {
                "title": "Underwriting Support",
                "description": "Prepare files for underwriting and respond to conditions through condition clearance, document verification, underwriter communication, and file packaging",
                "ownership": "individual",
                "priority": "high",
                "key_activities": ["Condition clearance", "Document verification", "Underwriter communication", "File packaging"]
            },
            {
                "title": "Closing Coordination",
                "description": "Ensure smooth closing process through closing document review, title company coordination, final conditions, and funding preparation",
                "ownership": "individual",
                "priority": "high",
                "key_activities": ["Closing document review", "Title company coordination", "Final conditions", "Funding preparation"]
            }
        ]
    },
    61: {  # David Thompson - Production Assistant
        "name": "David Thompson",
        "role": "Production Assistant",
        "responsibilities": [
            {
                "title": "Application Processing",
                "description": "Process incoming loan applications through application intake, initial review, system setup, and loan officer coordination",
                "ownership": "individual",
                "priority": "high",
                "key_activities": ["Application intake", "Initial review", "Setup in system", "LO coordination"]
            },
            {
                "title": "Document Collection",
                "description": "Gather required documentation from borrowers through document requests, borrower follow-up, document review, and file completion",
                "ownership": "individual",
                "priority": "high",
                "key_activities": ["Document requests", "Borrower follow-up", "Document review", "File completion"]
            }
        ]
    },
    62: {  # Jessica Martinez - Concierge
        "name": "Jessica Martinez",
        "role": "Concierge",
        "responsibilities": [
            {
                "title": "Client Communication",
                "description": "Maintain regular communication with borrowers throughout the loan process via status updates, expectation setting, question handling, and proactive outreach",
                "ownership": "individual",
                "priority": "high",
                "key_activities": ["Status updates", "Expectation setting", "Question handling", "Proactive outreach"]
            },
            {
                "title": "Experience Management",
                "description": "Ensure exceptional client experience from application to closing through welcome calls, process education, issue resolution, and closing preparation",
                "ownership": "individual",
                "priority": "high",
                "key_activities": ["Welcome calls", "Process education", "Issue resolution", "Closing preparation"]
            },
            {
                "title": "Feedback Collection",
                "description": "Gather client feedback and reviews through post-closing surveys, review requests, testimonial collection, and experience analysis",
                "ownership": "individual",
                "priority": "medium",
                "key_activities": ["Post-closing surveys", "Review requests", "Testimonial collection", "Experience analysis"]
            }
        ]
    },
    63: {  # Robert Lee - Processor
        "name": "Robert Lee",
        "role": "Processor",
        "responsibilities": [
            {
                "title": "File Review & Validation",
                "description": "Comprehensive review of loan files for completeness and accuracy through document verification, income analysis, asset verification, and credit review",
                "ownership": "individual",
                "priority": "high",
                "key_activities": ["Document verification", "Income analysis", "Asset verification", "Credit review"]
            },
            {
                "title": "Underwriting Preparation",
                "description": "Prepare loan files for underwriting submission through AUS submission, file packaging, supporting documentation, and quality assurance",
                "ownership": "individual",
                "priority": "high",
                "key_activities": ["AUS submission", "File packaging", "Supporting documentation", "Quality assurance"]
            },
            {
                "title": "Condition Management",
                "description": "Track and clear underwriting conditions through condition tracking, document requests, borrower coordination, and underwriter communication",
                "ownership": "individual",
                "priority": "high",
                "key_activities": ["Condition tracking", "Document requests", "Borrower coordination", "Underwriter communication"]
            }
        ]
    },
    64: {  # Amanda White - Processor
        "name": "Amanda White",
        "role": "Processor",
        "responsibilities": [
            {
                "title": "Initial Processing",
                "description": "Initial processing of new loan applications through application review, document organization, disclosures, and initial setup",
                "ownership": "individual",
                "priority": "high",
                "key_activities": ["Application review", "Document organization", "Disclosures", "Initial setup"]
            },
            {
                "title": "Verification Coordination",
                "description": "Coordinate employment and income verifications through VOE requests, income verification, employment confirmation, and follow-up",
                "ownership": "individual",
                "priority": "high",
                "key_activities": ["VOE requests", "Income verification", "Employment confirmation", "Follow-up"]
            }
        ]
    },
    65: {  # Kevin Brown - Processor Assistant
        "name": "Kevin Brown",
        "role": "Processor Assistant",
        "responsibilities": [
            {
                "title": "Document Management",
                "description": "Organize and maintain loan file documentation through document scanning, file organization, index management, and quality checks",
                "ownership": "individual",
                "priority": "medium",
                "key_activities": ["Document scanning", "File organization", "Index management", "Quality checks"]
            },
            {
                "title": "Administrative Support",
                "description": "Provide administrative support to processors through data entry, file maintenance, report generation, and system updates",
                "ownership": "individual",
                "priority": "medium",
                "key_activities": ["Data entry", "File maintenance", "Report generation", "System updates"]
            }
        ]
    },
    66: {  # Rachel Davis - Processor Assistant
        "name": "Rachel Davis",
        "role": "Processor Assistant",
        "responsibilities": [
            {
                "title": "File Preparation",
                "description": "Prepare files for processor review through initial document review, missing document identification, borrower outreach, and file setup",
                "ownership": "individual",
                "priority": "medium",
                "key_activities": ["Initial document review", "Missing document identification", "Borrower outreach", "File setup"]
            }
        ]
    },
    67: {  # Lisa Anderson - Executive Assistant
        "name": "Lisa Anderson",
        "role": "Executive Assistant",
        "responsibilities": [
            {
                "title": "Executive Support",
                "description": "Provide comprehensive administrative support to branch leadership through calendar management, meeting coordination, correspondence, and travel arrangements",
                "ownership": "individual",
                "priority": "high",
                "key_activities": ["Calendar management", "Meeting coordination", "Correspondence", "Travel arrangements"]
            },
            {
                "title": "Team Coordination",
                "description": "Coordinate team activities and communication through team meetings, event planning, communication distribution, and schedule coordination",
                "ownership": "individual",
                "priority": "high",
                "key_activities": ["Team meetings", "Event planning", "Communication distribution", "Schedule coordination"]
            },
            {
                "title": "Reporting & Analytics",
                "description": "Prepare reports and analytics for leadership through data compilation, report generation, presentation preparation, and metrics tracking",
                "ownership": "individual",
                "priority": "high",
                "key_activities": ["Data compilation", "Report generation", "Presentation preparation", "Metrics tracking"]
            }
        ]
    }
}

# Get the demo user ID to use as creator
cur.execute("SELECT id FROM users WHERE email = 'demo@example.com'")
demo_user_id = cur.fetchone()[0]

print(f"Using demo user ID: {demo_user_id}")
print()

total_created = 0

for user_id, data in TEAM_WORKFLOWS.items():
    print(f"Creating responsibilities for {data['name']} ({data['role']})...")

    for resp in data['responsibilities']:
        # Insert into user_responsibilities table
        cur.execute("""
            INSERT INTO user_responsibilities
            (user_id, title, description, ownership, priority, effective_date, key_activities, created_by, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            user_id,
            resp['title'],
            resp['description'],
            resp['ownership'],
            resp['priority'],
            datetime.now(),
            json.dumps(resp['key_activities']),
            demo_user_id,
            datetime.now()
        ))

        print(f"  ✓ {resp['title']}")
        total_created += 1

conn.commit()

print()
print("=" * 80)
print(f"Successfully created {total_created} responsibilities across 10 team members!")
print("=" * 80)

cur.close()
conn.close()
