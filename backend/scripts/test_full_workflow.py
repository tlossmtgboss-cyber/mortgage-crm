#!/usr/bin/env python3
"""
Full Workflow Test Script
Tests the complete lead-to-loan-to-MUM workflow with SLA milestone tracking.
Creates 10 test people and simulates the entire mortgage process.
"""

import logging
import requests
import json
import time
from datetime import datetime
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# Configuration
BASE_URL = "https://app.perenniaai.com"
# BASE_URL = "http://localhost:8000"  # Uncomment for local testing

# Test data for 10 people
TEST_PEOPLE = [
    {"name": "John Smith", "email": "john.smith.test@example.com", "phone": "555-0001", "loan_amount": 350000},
    {"name": "Sarah Johnson", "email": "sarah.j.test@example.com", "phone": "555-0002", "loan_amount": 425000},
    {"name": "Michael Brown", "email": "michael.b.test@example.com", "phone": "555-0003", "loan_amount": 275000},
    {"name": "Emily Davis", "email": "emily.d.test@example.com", "phone": "555-0004", "loan_amount": 500000},
    {"name": "Robert Wilson", "email": "robert.w.test@example.com", "phone": "555-0005", "loan_amount": 320000},
    {"name": "Jennifer Martinez", "email": "jennifer.m.test@example.com", "phone": "555-0006", "loan_amount": 450000},
    {"name": "David Anderson", "email": "david.a.test@example.com", "phone": "555-0007", "loan_amount": 380000},
    {"name": "Lisa Taylor", "email": "lisa.t.test@example.com", "phone": "555-0008", "loan_amount": 295000},
    {"name": "Christopher Lee", "email": "chris.l.test@example.com", "phone": "555-0009", "loan_amount": 525000},
    {"name": "Amanda White", "email": "amanda.w.test@example.com", "phone": "555-0010", "loan_amount": 410000},
]

# Lead stages in order
LEAD_STAGES = [
    "New",
    "Attempted Contact",
    "Prospect",
    "Pre-Qualified",
    "Pre-Approved",
    "Under Contract",
    "Disclosed"  # This is where the lead converts to a loan
]

# Loan stages in order
LOAN_STAGES = [
    "Disclosed",
    "Processing",
    "Submitted",
    "UW Received",
    "Approved",
    "CTC",
    "Docs Out",
    "Funded"
]


class WorkflowTester:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.token: Optional[str] = None
        self.results: Dict[str, Any] = {
            "leads_created": [],
            "loans_created": [],
            "milestones_triggered": [],
            "errors": [],
            "summary": {}
        }

    def authenticate(self) -> bool:
        """Get authentication token."""
        print("\n🔐 Authenticating...")
        try:
            response = requests.post(
                f"{self.base_url}/token",
                data={"username": "admin@perenniaai.com", "password": "demo123"},
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            if response.status_code == 200:
                data = response.json()
                self.token = data.get("access_token")
                print(f"✅ Authenticated as {data.get('user', {}).get('email')}")
                return True
            else:
                print(f"❌ Authentication failed: {response.text}")
                return False
        except Exception as e:
            print(f"❌ Authentication error: {e}")
            return False

    def _headers(self) -> Dict[str, str]:
        """Get request headers with auth token."""
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    def create_lead(self, person: Dict) -> Optional[Dict]:
        """Create a new lead."""
        timestamp = int(time.time())
        lead_data = {
            "name": person["name"],
            "email": f"test{timestamp}_{person['email']}",
            "phone": person["phone"],
            "source": "Workflow Test",
            "loan_amount": person["loan_amount"],
            "loan_type": "Purchase - Conventional",
            "credit_score": 720,
            "annual_income": 95000,
            "property_value": person["loan_amount"] * 1.25
        }

        try:
            response = requests.post(
                f"{self.base_url}/api/v1/leads/",
                json=lead_data,
                headers=self._headers()
            )
            if response.status_code in [200, 201]:
                lead = response.json()
                print(f"  ✅ Created lead: {lead.get('name')} (ID: {lead.get('id')})")
                return lead
            else:
                error = f"Failed to create lead {person['name']}: {response.text}"
                print(f"  ❌ {error}")
                self.results["errors"].append(error)
                return None
        except Exception as e:
            error = f"Error creating lead {person['name']}: {e}"
            print(f"  ❌ {error}")
            self.results["errors"].append(error)
            return None

    def update_lead_stage(self, lead_id: int, stage: str) -> bool:
        """Update lead stage."""
        try:
            response = requests.patch(
                f"{self.base_url}/api/v1/leads/{lead_id}",
                json={"stage": stage},
                headers=self._headers()
            )
            if response.status_code == 200:
                return True
            else:
                error = f"Failed to update lead {lead_id} to {stage}: {response.text}"
                self.results["errors"].append(error)
                return False
        except Exception as e:
            self.results["errors"].append(f"Error updating lead {lead_id}: {e}")
            return False

    def get_lead_milestones(self, lead_id: int) -> List[Dict]:
        """Get milestones for a lead."""
        try:
            response = requests.get(
                f"{self.base_url}/api/v1/sla/milestones/lead/{lead_id}",
                headers=self._headers()
            )
            if response.status_code == 200:
                return response.json()
            return []
        except Exception as e:
            logger.error(f"Error in get_lead_milestones: {e}")
            return []

    def complete_milestone(self, milestone_id: int) -> bool:
        """Complete a milestone."""
        try:
            response = requests.post(
                f"{self.base_url}/api/v1/sla/milestones/{milestone_id}/complete",
                json={"notes": "Completed via workflow test"},
                headers=self._headers()
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Error in complete_milestone: {e}")
            return False

    def start_milestone(self, lead_id: int = None, loan_id: int = None,
                       milestone_type: str = None, loan_number: str = None) -> bool:
        """Start a new milestone."""
        try:
            data = {"milestone_type": milestone_type}
            if lead_id:
                data["lead_id"] = lead_id
            if loan_id:
                data["loan_id"] = loan_id
            if loan_number:
                data["loan_number"] = loan_number

            response = requests.post(
                f"{self.base_url}/api/v1/sla/milestones/start",
                json=data,
                headers=self._headers()
            )
            return response.status_code == 200
        except Exception as e:
            print(f"    ⚠️ Failed to start milestone {milestone_type}: {e}")
            return False

    def create_loan(self, lead: Dict) -> Optional[Dict]:
        """Create a loan from a lead."""
        timestamp = int(time.time())
        loan_data = {
            "loan_number": f"TEST-{timestamp}-{lead.get('id', 0)}",
            "borrower_name": lead.get("name"),
            "borrower_email": lead.get("email"),
            "borrower_phone": lead.get("phone"),
            "amount": lead.get("loan_amount", 350000),
            "loan_type": "Conventional",
            "property_address": f"123 Test St #{lead.get('id', 0)}",
            "property_city": "Testville",
            "property_state": "CA",
            "property_zip": "90210",
            "status": "Disclosed",
            "lead_id": lead.get("id")
        }

        try:
            response = requests.post(
                f"{self.base_url}/api/v1/loans/",
                json=loan_data,
                headers=self._headers()
            )
            if response.status_code in [200, 201]:
                loan = response.json()
                print(f"  ✅ Created loan: {loan.get('loan_number')} (ID: {loan.get('id')})")
                return loan
            else:
                error = f"Failed to create loan for {lead.get('name')}: {response.text}"
                print(f"  ❌ {error}")
                self.results["errors"].append(error)
                return None
        except Exception as e:
            error = f"Error creating loan for {lead.get('name')}: {e}"
            print(f"  ❌ {error}")
            self.results["errors"].append(error)
            return None

    def update_loan_stage(self, loan_id: int, stage: str) -> bool:
        """Update loan stage."""
        try:
            response = requests.patch(
                f"{self.base_url}/api/v1/loans/{loan_id}",
                json={"status": stage},
                headers=self._headers()
            )
            if response.status_code == 200:
                return True
            else:
                error = f"Failed to update loan {loan_id} to {stage}: {response.text}"
                self.results["errors"].append(error)
                return False
        except Exception as e:
            self.results["errors"].append(f"Error updating loan {loan_id}: {e}")
            return False

    def get_loan_milestones(self, loan_id: int) -> List[Dict]:
        """Get milestones for a loan."""
        try:
            response = requests.get(
                f"{self.base_url}/api/v1/sla/milestones/loan/{loan_id}",
                headers=self._headers()
            )
            if response.status_code == 200:
                return response.json()
            return []
        except Exception as e:
            logger.error(f"Error in get_loan_milestones: {e}")
            return []

    def get_sla_dashboard(self) -> Dict:
        """Get SLA dashboard summary."""
        try:
            response = requests.get(
                f"{self.base_url}/api/v1/sla/dashboard",
                headers=self._headers()
            )
            if response.status_code == 200:
                return response.json()
            return {}
        except Exception as e:
            logger.error(f"Error in get_sla_dashboard: {e}")
            return {}

    def convert_to_mum(self, loan_id: int) -> bool:
        """Convert funded loan to MUM client."""
        try:
            response = requests.post(
                f"{self.base_url}/api/v1/loans/{loan_id}/convert-to-mum",
                headers=self._headers()
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Error in convert_to_mum: {e}")
            return False

    def process_person(self, person: Dict, index: int) -> Dict:
        """Process one person through the entire workflow."""
        result = {
            "name": person["name"],
            "lead_id": None,
            "loan_id": None,
            "lead_stages_completed": [],
            "loan_stages_completed": [],
            "milestones_created": [],
            "milestones_completed": [],
            "converted_to_mum": False,
            "success": False,
            "errors": []
        }

        print(f"\n{'='*60}")
        print(f"👤 Processing Person {index + 1}/10: {person['name']}")
        print(f"{'='*60}")

        # Step 1: Create lead
        print("\n📝 Step 1: Creating lead...")
        lead = self.create_lead(person)
        if not lead:
            result["errors"].append("Failed to create lead")
            return result

        result["lead_id"] = lead.get("id")
        self.results["leads_created"].append(lead)

        # Check for LEAD_RESPONSE milestone
        time.sleep(0.5)  # Give server time to process
        milestones = self.get_lead_milestones(lead["id"])
        if milestones:
            for m in milestones:
                result["milestones_created"].append(m.get("milestone_type"))
                print(f"  📍 Milestone created: {m.get('milestone_type')} (Status: {m.get('status')})")

        # Step 2: Progress through lead stages
        print("\n📈 Step 2: Progressing through lead stages...")
        for i, stage in enumerate(LEAD_STAGES[1:], 1):  # Skip "New" since lead starts there
            print(f"  → Moving to stage: {stage}")
            if self.update_lead_stage(lead["id"], stage):
                result["lead_stages_completed"].append(stage)

                # Check for new milestones after stage change
                time.sleep(0.3)
                new_milestones = self.get_lead_milestones(lead["id"])
                for m in new_milestones:
                    mt = m.get("milestone_type")
                    if mt not in result["milestones_created"]:
                        result["milestones_created"].append(mt)
                        print(f"    📍 New milestone: {mt}")
            else:
                print(f"    ⚠️ Failed to update to {stage}")

        # Step 3: Create loan when lead reaches "Disclosed"
        print("\n🏦 Step 3: Creating loan...")
        loan = self.create_loan(lead)
        if not loan:
            result["errors"].append("Failed to create loan")
            return result

        result["loan_id"] = loan.get("id")
        self.results["loans_created"].append(loan)

        # Check for loan milestones
        time.sleep(0.5)
        loan_milestones = self.get_loan_milestones(loan["id"])
        for m in loan_milestones:
            mt = m.get("milestone_type")
            if mt not in result["milestones_created"]:
                result["milestones_created"].append(mt)
                print(f"  📍 Loan milestone: {mt}")

        # Step 4: Progress through loan stages
        print("\n📈 Step 4: Progressing through loan stages...")
        for stage in LOAN_STAGES[1:]:  # Skip "Disclosed" since loan starts there
            print(f"  → Moving to stage: {stage}")
            if self.update_loan_stage(loan["id"], stage):
                result["loan_stages_completed"].append(stage)

                # Check for new milestones
                time.sleep(0.3)
                new_milestones = self.get_loan_milestones(loan["id"])
                for m in new_milestones:
                    mt = m.get("milestone_type")
                    if mt not in result["milestones_created"]:
                        result["milestones_created"].append(mt)
                        print(f"    📍 New milestone: {mt}")
            else:
                print(f"    ⚠️ Failed to update to {stage}")

        # Step 5: Convert to MUM
        print("\n🎯 Step 5: Converting to MUM client...")
        if "Funded" in result["loan_stages_completed"]:
            if self.convert_to_mum(loan["id"]):
                result["converted_to_mum"] = True
                print("  ✅ Successfully converted to MUM client!")
            else:
                print("  ⚠️ MUM conversion failed (may already be converted)")

        result["success"] = len(result["errors"]) == 0
        print(f"\n✨ Person {person['name']} processing complete!")
        print(f"   Lead stages: {len(result['lead_stages_completed'])}/{len(LEAD_STAGES)-1}")
        print(f"   Loan stages: {len(result['loan_stages_completed'])}/{len(LOAN_STAGES)-1}")
        print(f"   Milestones created: {len(result['milestones_created'])}")

        return result

    def run_full_test(self):
        """Run the complete workflow test for all 10 people."""
        print("\n" + "="*70)
        print("🚀 FULL WORKFLOW TEST - Lead to MUM Simulation")
        print("="*70)
        print(f"Testing {len(TEST_PEOPLE)} people through complete mortgage workflow")
        print(f"Target: {BASE_URL}")
        print("="*70)

        # Authenticate
        if not self.authenticate():
            print("\n❌ Cannot proceed without authentication")
            return

        # Get initial SLA dashboard state
        print("\n📊 Initial SLA Dashboard State:")
        initial_dashboard = self.get_sla_dashboard()
        if initial_dashboard.get("summary"):
            s = initial_dashboard["summary"]
            print(f"   Total active milestones: {s.get('total_active_milestones', 0)}")
            print(f"   On track: {s.get('on_track_count', 0)}")
            print(f"   At risk: {s.get('at_risk_count', 0)}")
            print(f"   Overdue: {s.get('overdue_count', 0)}")

        # Process each person
        person_results = []
        for i, person in enumerate(TEST_PEOPLE):
            result = self.process_person(person, i)
            person_results.append(result)
            time.sleep(0.5)  # Brief pause between people

        # Get final SLA dashboard state
        print("\n\n" + "="*70)
        print("📊 FINAL SLA DASHBOARD STATE")
        print("="*70)
        final_dashboard = self.get_sla_dashboard()
        if final_dashboard.get("summary"):
            s = final_dashboard["summary"]
            print(f"Total active milestones: {s.get('total_active_milestones', 0)}")
            print(f"On track: {s.get('on_track_count', 0)}")
            print(f"At risk: {s.get('at_risk_count', 0)}")
            print(f"Overdue: {s.get('overdue_count', 0)}")
            print(f"\nMilestone breakdown:")
            for mt, counts in s.get("milestone_breakdown", {}).items():
                print(f"  {mt}: {counts}")

        # Summary
        print("\n\n" + "="*70)
        print("📋 TEST SUMMARY")
        print("="*70)

        successful = sum(1 for r in person_results if r["success"])
        print(f"\nPeople processed: {len(person_results)}")
        print(f"Successful: {successful}")
        print(f"Failed: {len(person_results) - successful}")

        print(f"\nLeads created: {len(self.results['leads_created'])}")
        print(f"Loans created: {len(self.results['loans_created'])}")

        all_milestones = []
        for r in person_results:
            all_milestones.extend(r["milestones_created"])
        print(f"\nTotal milestones triggered: {len(all_milestones)}")

        # Count unique milestone types
        milestone_counts = {}
        for m in all_milestones:
            milestone_counts[m] = milestone_counts.get(m, 0) + 1
        print("\nMilestone breakdown:")
        for mt, count in sorted(milestone_counts.items()):
            print(f"  {mt}: {count}")

        mum_converted = sum(1 for r in person_results if r["converted_to_mum"])
        print(f"\nMUM conversions: {mum_converted}")

        if self.results["errors"]:
            print(f"\n⚠️ Errors encountered: {len(self.results['errors'])}")
            for error in self.results["errors"][:10]:  # Show first 10
                print(f"  - {error}")

        print("\n" + "="*70)
        print("✅ TEST COMPLETE")
        print("="*70)

        return {
            "person_results": person_results,
            "dashboard": final_dashboard,
            "errors": self.results["errors"]
        }


if __name__ == "__main__":
    tester = WorkflowTester(BASE_URL)
    results = tester.run_full_test()
