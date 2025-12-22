#!/usr/bin/env python3
"""
Test application for a self-employed person with complex financial situation.

Scenario:
- Self-employed (writes off all expenses)
- Pays child support
- Owes money to the IRS
- Getting gift funds
- Just bought a car
- Realtor: Timothy Loss
- Loan Officer: Tim Loss (ID: 57)
"""

import requests
import json
import os

# Use production URL
BASE_URL = os.getenv("API_URL", "https://mortgage-crm-production-7a9a.up.railway.app")
ADMIN_LO_ID = "57"  # Tim Loss's user ID

def find_or_create_timothy_loss_partner():
    """
    Find Timothy Loss as a referral partner, or return partner ID to use.
    In production, we'll check if the partner exists and get their ID.
    """
    # For now, we'll assume partner ID 1 is Timothy Loss or we create him
    # The frontend application will use the agent autocomplete to find the partner
    return None  # Will be set via agent_partner_id in declarations

def create_test_application():
    """Create and submit a test application for a self-employed person"""

    # Test borrower data - Self-employed contractor
    application_data = {
        "profileData": {
            "firstName": "Marcus",
            "lastName": "Reynolds",
            "email": "marcus.reynolds.selfemployed@testapplication.com",
            "phone": "555-742-9183",
            "address": "4521 Enterprise Drive",
            "city": "San Diego",
            "state": "CA",
            "zip": "92101",
            "dateOfBirth": "1982-05-15",
            "ssn": "***-**-1234",  # Last 4 only for security
            "maritalStatus": "divorced",
        },
        "incomeData": {
            "employmentType": "self_employed",
            "employerName": "Reynolds Construction LLC",
            "jobTitle": "Owner/General Contractor",
            "startDate": "2018-03-15",
            "annualSalary": 185000,  # Gross income before expenses
            "yearsInBusiness": 6,
            "businessType": "LLC",
            "businessAddress": "4521 Enterprise Drive, San Diego, CA 92101",
            # Note: High write-offs reduce net income significantly
            "additionalNotes": "Self-employed general contractor. High business expenses including truck, equipment, materials. Net income after write-offs approximately $65,000",
        },
        "assetData": {
            "checking": 12500,
            "savings": 28000,
            "investments": 45000,
            "retirement401k": 82000,
            "giftAmount": 35000,  # Getting gift funds from family
            "giftDonor": "Parents - John and Mary Reynolds",
            "giftRelationship": "Parents",
        },
        "propertyData": {
            "address": "8742 Coastal View Lane",
            "city": "San Diego",
            "state": "CA",
            "zip": "92037",
            "county": "San Diego County",
            "propertyType": "Single Family",
            "occupancy": "primary",
            "purchasePrice": 625000,
            "downPayment": 62500,  # 10% down
            "loanProgram": "FHA",  # FHA may be better for self-employed with write-offs
        },
        "declarations": {
            # Employment status
            "self_employed": "yes",
            "self_employed_business_type": "LLC",
            "self_employed_years": "6",

            # Family situation
            "borrower_count": "1",
            "citizenship": "us_citizen",
            "first_time_buyer": "no",
            "marital_status": "divorced",

            # Child support obligation
            "child_support": "yes",
            "child_support_monthly": 1200,
            "child_support_children": 2,

            # IRS debt
            "irs_debt": "yes",
            "irs_debt_amount": 18500,
            "irs_payment_plan": "yes",
            "irs_monthly_payment": 450,

            # Gift funds
            "gift_funds": "yes",
            "gift_amount": 35000,
            "gift_donor_name": "John and Mary Reynolds",
            "gift_donor_relationship": "Parents",

            # Recent major purchase (car)
            "recent_large_purchase": "yes",
            "recent_purchase_type": "vehicle",
            "recent_purchase_amount": 42000,
            "recent_purchase_date": "2024-10-15",
            "recent_purchase_monthly_payment": 685,

            # Outstanding liabilities
            "outstanding_judgments": "no",
            "bankruptcy": "no",
            "foreclosure": "no",

            # Realtor selection - Timothy Loss
            # This is the key field that links to the partner portal
            "working_with_agent": "yes",
            "agent_name": "Timothy Loss",
            "agent_company": "Perennia Real Estate",
            "agent_phone": "555-123-4567",
            "agent_email": "timothy.loss@perenniaai.com",
            # This ID links to the referral_partners table
            # Will be populated when the user selects from autocomplete
            "agent_partner_id": 1,  # Assuming partner ID 1 - adjust as needed
        },
        "paymentEstimate": {
            "monthlyPayment": 4250,
            "rate": 6.875,
            "apr": 7.125,
            "loanTerm": 30,
        },
        # Consent flags
        "eConsentAgreed": True,
        "creditAuthAgreed": True,

        # Assign to Tim Loss
        "loId": ADMIN_LO_ID,

        # Additional notes for loan officer
        "borrowerNotes": """
IMPORTANT CONSIDERATIONS FOR THIS APPLICATION:

1. SELF-EMPLOYMENT INCOME:
   - Business: Reynolds Construction LLC (General Contractor)
   - Gross Income: ~$185,000/year
   - High write-offs (truck, equipment, materials, fuel, insurance)
   - Net income after write-offs: ~$65,000
   - Will need 2 years tax returns and P&L statement
   - Bank statements will show higher deposits than net income reported

2. CHILD SUPPORT OBLIGATION:
   - $1,200/month for 2 children
   - Court-ordered, ongoing obligation
   - Include in DTI calculation

3. IRS DEBT:
   - Outstanding balance: $18,500
   - On IRS payment plan
   - Monthly payment: $450
   - Will need IRS payment agreement documentation

4. GIFT FUNDS:
   - $35,000 from parents (John and Mary Reynolds)
   - Will need gift letter and donor bank statements
   - Funds to be used for down payment/closing costs

5. RECENT VEHICLE PURCHASE:
   - Purchased 10/2024: $42,000
   - New work truck for business
   - Monthly payment: $685
   - Will show as new tradeline on credit report

6. REALTOR:
   - Working with Timothy Loss
   - Partner should see this application in their portal

RECOMMENDED LOAN PROGRAM: FHA
- More lenient on self-employment income calculation
- Allows for higher DTI ratios
- Gift funds acceptable for entire down payment
""",
    }

    return application_data


def submit_application(data):
    """Submit the test application"""
    print("\n" + "="*70)
    print("SUBMITTING TEST APPLICATION - SELF-EMPLOYED BORROWER")
    print("="*70)

    print(f"\nBorrower: {data['profileData']['firstName']} {data['profileData']['lastName']}")
    print(f"Email: {data['profileData']['email']}")
    print(f"Property: ${data['propertyData']['purchasePrice']:,} in {data['propertyData']['city']}, {data['propertyData']['state']}")
    print(f"Loan Program: {data['propertyData']['loanProgram']}")
    print(f"Down Payment: ${data['propertyData']['downPayment']:,}")

    print(f"\nKey Factors:")
    print(f"  - Self-Employed: {data['declarations'].get('self_employed')}")
    print(f"  - Child Support: ${data['declarations'].get('child_support_monthly', 0):,}/month")
    print(f"  - IRS Debt: ${data['declarations'].get('irs_debt_amount', 0):,}")
    print(f"  - Gift Funds: ${data['declarations'].get('gift_amount', 0):,}")
    print(f"  - Recent Car Purchase: ${data['declarations'].get('recent_purchase_amount', 0):,}")
    print(f"  - Realtor: {data['declarations'].get('agent_name')}")
    print(f"  - Agent Partner ID: {data['declarations'].get('agent_partner_id')}")

    url = f"{BASE_URL}/api/v1/borrower-auth/submit-application"
    headers = {"Content-Type": "application/json"}

    print(f"\nSubmitting to: {url}")

    try:
        response = requests.post(url, json=data, headers=headers, timeout=60)

        print(f"\nResponse Status: {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            print(f"\nSUCCESS!")
            print(f"Lead ID: {result.get('data', {}).get('lead_id')}")
            print(f"Workspace ID: {result.get('data', {}).get('workspace_id')}")
            print(f"Portal Slug: {result.get('data', {}).get('portal_slug')}")
            print(f"PDFs Generated: {result.get('data', {}).get('pdfs_generated')}")
            print(f"Email Sent: {result.get('data', {}).get('email_sent_to_lo')}")

            if result.get('data', {}).get('portal_slug'):
                portal_url = f"https://perenniaai.com/portal/{result['data']['portal_slug']}"
                print(f"\nBorrower Portal URL: {portal_url}")

            return result
        else:
            print(f"\nERROR: Status {response.status_code}")
            print(f"Response: {response.text[:1000]}")
            return None

    except requests.exceptions.Timeout:
        print("\nERROR: Request timed out")
        return None
    except requests.exceptions.ConnectionError as e:
        print(f"\nERROR: Connection failed - {e}")
        return None
    except Exception as e:
        print(f"\nEXCEPTION: {str(e)}")
        return None


def check_partner_portal(partner_id=1):
    """Check if the application shows up in the partner portal"""
    print("\n" + "="*70)
    print(f"CHECKING PARTNER PORTAL (Partner ID: {partner_id})")
    print("="*70)

    url = f"{BASE_URL}/api/v1/referral-partners/{partner_id}/referrals"

    # This would need authentication - for now just show the URL
    print(f"\nPartner referrals endpoint: {url}")
    print("Note: This endpoint requires authentication")

    # Could add authentication headers here if we had a token
    # headers = {"Authorization": f"Bearer {token}"}


def main():
    print("\n" + "="*70)
    print("TEST: SELF-EMPLOYED BORROWER APPLICATION")
    print("="*70)
    print(f"\nTarget API: {BASE_URL}")
    print(f"Loan Officer ID: {ADMIN_LO_ID} (Tim Loss)")

    # Create the test application data
    app_data = create_test_application()

    # Submit the application
    result = submit_application(app_data)

    if result and result.get('success'):
        print("\n" + "="*70)
        print("TEST COMPLETED SUCCESSFULLY")
        print("="*70)
        print("\nNext steps to verify:")
        print("1. Check CRM leads for Marcus Reynolds")
        print("2. Check SmartDocs for document requirements")
        print("3. Check Partner Portal for Timothy Loss - should see this applicant")
        print("4. Verify borrower portal is accessible")

        # Check partner portal
        check_partner_portal(partner_id=app_data['declarations'].get('agent_partner_id', 1))
    else:
        print("\n" + "="*70)
        print("TEST FAILED")
        print("="*70)

    return result


if __name__ == "__main__":
    main()
