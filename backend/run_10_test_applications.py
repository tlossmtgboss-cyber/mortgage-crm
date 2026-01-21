#!/usr/bin/env python3
"""
Run 10 test mortgage applications with varied data.
Each application will:
1. Create a new borrower profile
2. Submit complete application
3. Generate and store e-sign documents
4. Generate Fannie Mae 3.4 file
5. Send email to admin with attachments and Q&A
"""

import requests
import random
import time
import json

BASE_URL = "https://app.perenniaai.com"
ADMIN_LO_ID = "57"  # Tim Loss's user ID

# Test data arrays for variety
FIRST_NAMES = ["Michael", "Jennifer", "David", "Sarah", "Robert", "Emily", "William", "Jessica", "James", "Ashley"]
LAST_NAMES = ["Anderson", "Thompson", "Martinez", "Johnson", "Williams", "Brown", "Davis", "Garcia", "Miller", "Wilson"]
CITIES = ["Los Angeles", "San Diego", "San Francisco", "Sacramento", "Austin", "Denver", "Seattle", "Portland", "Phoenix", "Miami"]
STATES = ["CA", "CA", "CA", "CA", "TX", "CO", "WA", "OR", "AZ", "FL"]
PROPERTY_TYPES = ["Single Family", "Condo", "Townhouse", "Single Family", "Single Family", "Condo", "Single Family", "Townhouse", "Single Family", "Condo"]
EMPLOYERS = ["Tech Corp Inc", "Healthcare Solutions LLC", "Finance Partners", "Education First", "Manufacturing Co", "Retail Giants", "Service Industries", "Construction Pros", "Legal Associates", "Media Group"]
JOB_TITLES = ["Software Engineer", "Nurse Manager", "Financial Analyst", "Teacher", "Production Manager", "Store Manager", "Consultant", "Project Manager", "Attorney", "Marketing Director"]
LOAN_PROGRAMS = ["Conventional", "FHA", "VA", "Conventional", "Conventional", "FHA", "Conventional", "VA", "Conventional", "FHA"]

def generate_test_data(index):
    """Generate unique test data for each application"""
    base_price = random.randint(300000, 800000)
    down_payment_pct = random.choice([5, 10, 15, 20, 25])
    down_payment = int(base_price * down_payment_pct / 100)

    annual_salary = random.randint(75000, 200000)
    checking = random.randint(10000, 50000)
    savings = random.randint(20000, 100000)
    investments = random.randint(0, 150000)

    return {
        "profileData": {
            "firstName": FIRST_NAMES[index],
            "lastName": LAST_NAMES[index],
            "email": f"test.{FIRST_NAMES[index].lower()}.{LAST_NAMES[index].lower()}{random.randint(100,999)}@testapplication.com",
            "phone": f"555-{random.randint(100,999)}-{random.randint(1000,9999)}",
            "address": f"{random.randint(100,9999)} {random.choice(['Main', 'Oak', 'Maple', 'Cedar', 'Pine'])} {random.choice(['Street', 'Avenue', 'Drive', 'Lane', 'Court'])}",
            "city": CITIES[index],
            "state": STATES[index],
            "zip": f"{random.randint(10000, 99999)}",
        },
        "incomeData": {
            "employerName": EMPLOYERS[index],
            "jobTitle": JOB_TITLES[index],
            "startDate": f"20{random.randint(15, 22)}-{random.randint(1,12):02d}-01",
            "annualSalary": annual_salary,
        },
        "assetData": {
            "checking": checking,
            "savings": savings,
            "investments": investments,
            "giftAmount": random.choice([0, 0, 0, 10000, 25000, 50000]),
        },
        "propertyData": {
            "address": f"{random.randint(100,9999)} {random.choice(['Sunset', 'Ocean', 'Mountain', 'Valley', 'Park'])} {random.choice(['Boulevard', 'Way', 'Place', 'Road', 'Circle'])}",
            "city": CITIES[index],
            "state": STATES[index],
            "zip": f"{random.randint(10000, 99999)}",
            "county": f"{CITIES[index]} County",
            "propertyType": PROPERTY_TYPES[index],
            "occupancy": random.choice(["primary", "primary", "primary", "second_home", "investment"]),
            "purchasePrice": base_price,
            "downPayment": down_payment,
            "loanProgram": LOAN_PROGRAMS[index],
        },
        "declarations": {
            "citizenship": random.choice(["us_citizen", "us_citizen", "us_citizen", "permanent_resident"]),
            "first_time_buyer": random.choice(["yes", "no"]),
        },
        "paymentEstimate": {
            "monthlyPayment": int((base_price - down_payment) * 0.006),
            "rate": round(random.uniform(6.0, 7.5), 3),
        },
        "eConsentAgreed": True,
        "creditAuthAgreed": True,
        "loId": ADMIN_LO_ID,
    }


def submit_application(test_num, data):
    """Submit a test application"""
    print(f"\n{'='*60}")
    print(f"TEST {test_num + 1}/10: {data['profileData']['firstName']} {data['profileData']['lastName']}")
    print(f"{'='*60}")

    print(f"  Property: ${data['propertyData']['purchasePrice']:,} in {data['propertyData']['city']}, {data['propertyData']['state']}")
    print(f"  Loan Type: {data['propertyData']['loanProgram']}")
    print(f"  Down Payment: ${data['propertyData']['downPayment']:,}")
    print(f"  Annual Income: ${data['incomeData']['annualSalary']:,}")

    url = f"{BASE_URL}/borrower/submit-application"
    headers = {"Content-Type": "application/json"}

    try:
        response = requests.post(url, json=data, headers=headers, timeout=60)

        if response.status_code == 200:
            result = response.json()
            print(f"\n  SUCCESS!")
            print(f"  Lead ID: {result.get('data', {}).get('lead_id')}")
            print(f"  PDFs Generated: {result.get('data', {}).get('pdfs_generated')}")
            print(f"  Fannie Mae Generated: {result.get('data', {}).get('fannie_mae_generated')}")
            print(f"  Email Sent: {result.get('data', {}).get('email_sent_to_lo')}")
            print(f"  Documents Stored: {result.get('data', {}).get('documents_stored', [])}")
            return result
        else:
            print(f"\n  ERROR: Status {response.status_code}")
            print(f"  Response: {response.text[:500]}")
            return None
    except Exception as e:
        print(f"\n  EXCEPTION: {str(e)}")
        return None


def main():
    print("\n" + "="*60)
    print("RUNNING 10 TEST MORTGAGE APPLICATIONS")
    print("="*60)
    print(f"Target: {BASE_URL}")
    print(f"Loan Officer ID: {ADMIN_LO_ID}")
    print("="*60)

    results = []
    successful = 0
    failed = 0

    for i in range(10):
        test_data = generate_test_data(i)
        result = submit_application(i, test_data)

        if result and result.get("success"):
            successful += 1
            results.append({
                "test_num": i + 1,
                "name": f"{test_data['profileData']['firstName']} {test_data['profileData']['lastName']}",
                "email": test_data['profileData']['email'],
                "lead_id": result.get('data', {}).get('lead_id'),
                "status": "SUCCESS",
            })
        else:
            failed += 1
            results.append({
                "test_num": i + 1,
                "name": f"{test_data['profileData']['firstName']} {test_data['profileData']['lastName']}",
                "status": "FAILED",
            })

        # Wait between submissions to avoid rate limiting
        if i < 9:
            print(f"\n  Waiting 3 seconds before next test...")
            time.sleep(3)

    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"Total Tests: 10")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print("\nResults:")
    for r in results:
        status_icon = "OK" if r['status'] == 'SUCCESS' else "X"
        lead_info = f" (Lead ID: {r.get('lead_id')})" if r.get('lead_id') else ""
        print(f"  [{status_icon}] Test {r['test_num']}: {r['name']}{lead_info}")

    print("\n" + "="*60)
    print("TEST COMPLETE")
    print("="*60)

    return successful, failed, results


if __name__ == "__main__":
    main()
