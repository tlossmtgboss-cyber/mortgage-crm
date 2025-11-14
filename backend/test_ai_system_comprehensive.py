#!/usr/bin/env python3
"""
Comprehensive AI System Test Suite
Runs 20 consecutive tests to verify system functionality
"""

import requests
import json
import time
from datetime import datetime

BASE_URL = "https://mortgage-crm-production-7a9a.up.railway.app"

class TestRunner:
    def __init__(self):
        self.test_count = 0
        self.failed_tests = []
        self.start_time = None

    def log(self, message, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] [{level}] {message}")

    def run_test(self, test_num, test_name, test_func):
        """Run a single test and track results"""
        self.log(f"Test #{test_num}: {test_name}", "TEST")
        try:
            test_func()
            self.test_count += 1
            self.log(f"✅ PASS - Test #{test_num}: {test_name}", "PASS")
            return True
        except Exception as e:
            self.log(f"❌ FAIL - Test #{test_num}: {test_name}", "FAIL")
            self.log(f"   Error: {str(e)}", "ERROR")
            self.failed_tests.append((test_num, test_name, str(e)))
            return False

    def assert_response(self, response, min_status=200, max_status=299):
        """Assert HTTP response is successful"""
        if not (min_status <= response.status_code <= max_status):
            raise Exception(f"HTTP {response.status_code}: {response.text[:200]}")

    def assert_field(self, data, field, expected_type=None):
        """Assert field exists and optionally check type"""
        if field not in data:
            raise Exception(f"Missing field: {field}")
        if expected_type and not isinstance(data[field], expected_type):
            raise Exception(f"Field {field} has wrong type: {type(data[field])} (expected {expected_type})")

    # Test 1: Health check
    def test_health_check(self):
        response = requests.get(f"{BASE_URL}/health")
        self.assert_response(response)
        data = response.json()
        self.assert_field(data, "status")
        if data["status"] != "healthy":
            raise Exception(f"System not healthy: {data['status']}")

    # Test 2: List all agents
    def test_list_agents(self):
        response = requests.get(f"{BASE_URL}/api/ai/agents")
        self.assert_response(response)
        data = response.json()
        self.assert_field(data, "agents", list)
        self.assert_field(data, "count", int)
        if data["count"] != 7:
            raise Exception(f"Expected 7 agents, got {data['count']}")

    # Test 3: List all tools
    def test_list_tools(self):
        response = requests.get(f"{BASE_URL}/api/ai/tools")
        self.assert_response(response)
        data = response.json()
        self.assert_field(data, "tools", list)
        if len(data["tools"]) < 10:
            raise Exception(f"Expected at least 10 tools, got {len(data['tools'])}")

    # Test 4: Get specific agent (Lead Manager)
    def test_get_lead_manager(self):
        response = requests.get(f"{BASE_URL}/api/ai/agents")
        self.assert_response(response)
        agents = response.json()["agents"]
        lead_manager = next((a for a in agents if a["id"] == "lead_manager"), None)
        if not lead_manager:
            raise Exception("Lead Manager agent not found")
        if lead_manager["status"] != "active":
            raise Exception(f"Lead Manager status is {lead_manager['status']}")

    # Test 5: Get specific agent (Pipeline Manager)
    def test_get_pipeline_manager(self):
        response = requests.get(f"{BASE_URL}/api/ai/agents")
        self.assert_response(response)
        agents = response.json()["agents"]
        pipeline_mgr = next((a for a in agents if a["id"] == "pipeline_manager"), None)
        if not pipeline_mgr:
            raise Exception("Pipeline Manager agent not found")

    # Test 6: Get specific agent (Customer Engagement)
    def test_get_customer_engagement(self):
        response = requests.get(f"{BASE_URL}/api/ai/agents")
        self.assert_response(response)
        agents = response.json()["agents"]
        cust_eng = next((a for a in agents if a["id"] == "customer_engagement"), None)
        if not cust_eng:
            raise Exception("Customer Engagement agent not found")

    # Test 7: Dispatch LeadCreated event
    def test_dispatch_lead_created(self):
        payload = {
            "event_type": "LeadCreated",
            "payload": {
                "entity_type": "lead",
                "entity_id": "test_001",
                "first_name": "John",
                "last_name": "Doe",
                "email": "john.doe@example.com"
            }
        }
        response = requests.post(
            f"{BASE_URL}/api/ai/events",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        self.assert_response(response)
        data = response.json()
        self.assert_field(data, "event_id")

    # Test 8: Dispatch LoanStageChanged event
    def test_dispatch_loan_stage_changed(self):
        payload = {
            "event_type": "LoanStageChanged",
            "payload": {
                "entity_type": "loan",
                "entity_id": "test_loan_001",
                "old_stage": "application",
                "new_stage": "processing"
            }
        }
        response = requests.post(
            f"{BASE_URL}/api/ai/events",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        self.assert_response(response)

    # Test 9: List executions
    def test_list_executions(self):
        response = requests.get(f"{BASE_URL}/api/ai/executions")
        self.assert_response(response)
        data = response.json()
        self.assert_field(data, "executions", list)
        self.assert_field(data, "count", int)

    # Test 10: Get agent statistics
    def test_agent_statistics(self):
        response = requests.get(f"{BASE_URL}/api/ai/statistics")
        self.assert_response(response)
        data = response.json()
        # Should have some statistics structure
        if not isinstance(data, dict):
            raise Exception("Statistics should return a dictionary")

    # Test 11: List agents with status filter
    def test_list_active_agents(self):
        response = requests.get(f"{BASE_URL}/api/ai/agents?status=active")
        self.assert_response(response)
        data = response.json()
        if data["count"] != 7:
            raise Exception(f"Expected 7 active agents, got {data['count']}")

    # Test 12: Verify agent has correct tools
    def test_agent_tools_configuration(self):
        response = requests.get(f"{BASE_URL}/api/ai/agents")
        self.assert_response(response)
        agents = response.json()["agents"]
        lead_manager = next((a for a in agents if a["id"] == "lead_manager"), None)
        if not lead_manager["tools"] or len(lead_manager["tools"]) == 0:
            raise Exception("Lead Manager has no tools configured")

    # Test 13: Verify agent has correct triggers
    def test_agent_triggers_configuration(self):
        response = requests.get(f"{BASE_URL}/api/ai/agents")
        self.assert_response(response)
        agents = response.json()["agents"]
        lead_manager = next((a for a in agents if a["id"] == "lead_manager"), None)
        if "LeadCreated" not in lead_manager["triggers"]:
            raise Exception("Lead Manager missing LeadCreated trigger")

    # Test 14: Dispatch DocUploaded event
    def test_dispatch_doc_uploaded(self):
        payload = {
            "event_type": "DocUploaded",
            "payload": {
                "entity_type": "document",
                "entity_id": "doc_test_001",
                "loan_id": "loan_123",
                "doc_type": "paystub"
            }
        }
        response = requests.post(
            f"{BASE_URL}/api/ai/events",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        self.assert_response(response)

    # Test 15: Verify Portfolio Analyst agent
    def test_portfolio_analyst_config(self):
        response = requests.get(f"{BASE_URL}/api/ai/agents")
        self.assert_response(response)
        agents = response.json()["agents"]
        portfolio = next((a for a in agents if a["id"] == "portfolio_analyst"), None)
        if not portfolio:
            raise Exception("Portfolio Analyst not found")
        if "scanForRefiOpportunities" not in portfolio["tools"]:
            raise Exception("Portfolio Analyst missing refi scan tool")

    # Test 16: Verify Operations Agent
    def test_operations_agent_config(self):
        response = requests.get(f"{BASE_URL}/api/ai/agents")
        self.assert_response(response)
        agents = response.json()["agents"]
        ops = next((a for a in agents if a["id"] == "operations_agent"), None)
        if not ops:
            raise Exception("Operations Agent not found")

    # Test 17: Verify Forecasting Agent
    def test_forecasting_agent_config(self):
        response = requests.get(f"{BASE_URL}/api/ai/agents")
        self.assert_response(response)
        agents = response.json()["agents"]
        forecast = next((a for a in agents if a["id"] == "forecasting_planner"), None)
        if not forecast:
            raise Exception("Forecasting Agent not found")

    # Test 18: Verify Document/Underwriting Agent
    def test_underwriting_agent_config(self):
        response = requests.get(f"{BASE_URL}/api/ai/agents")
        self.assert_response(response)
        agents = response.json()["agents"]
        underwriting = next((a for a in agents if a["id"] == "underwriting_assistant"), None)
        if not underwriting:
            raise Exception("Underwriting Assistant not found")

    # Test 19: Test tools endpoint filtering
    def test_tools_filtering(self):
        response = requests.get(f"{BASE_URL}/api/ai/tools")
        self.assert_response(response)
        tools = response.json()["tools"]
        # Verify we have various tool categories
        tool_names = [t["name"] for t in tools]
        if "getLeadById" not in tool_names:
            raise Exception("getLeadById tool not found")

    # Test 20: Final integration test - dispatch multiple events
    def test_multiple_events_dispatch(self):
        events = [
            {
                "event_type": "LeadCreated",
                "payload": {"entity_type": "lead", "entity_id": "final_test_001"}
            },
            {
                "event_type": "LoanStageChanged",
                "payload": {"entity_type": "loan", "entity_id": "final_test_002"}
            }
        ]

        for event in events:
            response = requests.post(
                f"{BASE_URL}/api/ai/events",
                json=event,
                headers={"Content-Type": "application/json"}
            )
            self.assert_response(response)

    def run_all_tests(self):
        """Run all 20 tests in sequence"""
        self.start_time = time.time()

        print("=" * 80)
        print("🤖 AI SYSTEM COMPREHENSIVE TEST SUITE")
        print("=" * 80)
        print()

        tests = [
            ("Health Check", self.test_health_check),
            ("List All Agents", self.test_list_agents),
            ("List All Tools", self.test_list_tools),
            ("Get Lead Manager Agent", self.test_get_lead_manager),
            ("Get Pipeline Manager Agent", self.test_get_pipeline_manager),
            ("Get Customer Engagement Agent", self.test_get_customer_engagement),
            ("Dispatch LeadCreated Event", self.test_dispatch_lead_created),
            ("Dispatch LoanStageChanged Event", self.test_dispatch_loan_stage_changed),
            ("List Agent Executions", self.test_list_executions),
            ("Get Agent Statistics", self.test_agent_statistics),
            ("Filter Active Agents", self.test_list_active_agents),
            ("Verify Agent Tools Config", self.test_agent_tools_configuration),
            ("Verify Agent Triggers Config", self.test_agent_triggers_configuration),
            ("Dispatch DocUploaded Event", self.test_dispatch_doc_uploaded),
            ("Verify Portfolio Analyst", self.test_portfolio_analyst_config),
            ("Verify Operations Agent", self.test_operations_agent_config),
            ("Verify Forecasting Agent", self.test_forecasting_agent_config),
            ("Verify Underwriting Agent", self.test_underwriting_agent_config),
            ("Test Tools Filtering", self.test_tools_filtering),
            ("Final Integration Test", self.test_multiple_events_dispatch),
        ]

        for i, (name, test_func) in enumerate(tests, 1):
            success = self.run_test(i, name, test_func)
            if not success:
                self.log(f"Test suite FAILED at test #{i}", "FAIL")
                self.log(f"Successfully completed: {self.test_count}/{len(tests)} tests", "SUMMARY")
                return False
            time.sleep(0.5)  # Brief pause between tests

        elapsed = time.time() - self.start_time

        print()
        print("=" * 80)
        print("🎉 TEST SUITE COMPLETED SUCCESSFULLY!")
        print("=" * 80)
        print(f"✅ Passed: {self.test_count}/{len(tests)} tests")
        print(f"⏱️  Duration: {elapsed:.2f} seconds")
        print(f"📊 Success Rate: 100%")
        print()

        return True


if __name__ == "__main__":
    runner = TestRunner()
    success = runner.run_all_tests()

    if not success:
        print()
        print("Failed tests:")
        for test_num, name, error in runner.failed_tests:
            print(f"  #{test_num}: {name}")
            print(f"    {error}")
        exit(1)

    exit(0)
