#!/usr/bin/env python3
"""
Test data upload functionality to identify 500 errors
"""

import requests
import json
import io

API_BASE_URL = "https://api.perenniaai.com"

def get_auth_token():
    """Login and get authentication token"""
    login_data = {
        "username": "admin@perenniaai.com",
        "password": "demo123"
    }

    try:
        response = requests.post(
            f"{API_BASE_URL}/token",
            data=login_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        if response.status_code == 200:
            return response.json().get("access_token")
        else:
            print(f"❌ Login failed: {response.status_code}")
            print(f"   Response: {response.text}")
            return None
    except Exception as e:
        print(f"❌ Login error: {e}")
        return None

def test_upload_analyze(token):
    """Test the analyze endpoint"""
    print("\n" + "="*70)
    print("TESTING FILE UPLOAD - ANALYZE ENDPOINT")
    print("="*70)

    # Create a simple CSV file
    csv_content = """first_name,last_name,email,phone
John,Doe,john@example.com,555-1234
Jane,Smith,jane@example.com,555-5678
"""

    files = {
        'file': ('test_leads.csv', io.StringIO(csv_content), 'text/csv')
    }

    headers = {
        "Authorization": f"Bearer {token}"
    }

    try:
        response = requests.post(
            f"{API_BASE_URL}/api/v1/data-import/analyze",
            files=files,
            headers=headers
        )

        print(f"\n📊 Status Code: {response.status_code}")

        if response.status_code == 200:
            print(f"✅ Analyze endpoint working!")
            result = response.json()
            print(f"\n📋 Analysis Results:")
            print(f"   Headers found: {result.get('headers', [])}")
            print(f"   Total rows: {result.get('total_rows', 0)}")
            print(f"   Questions: {len(result.get('questions', []))}")
            return True, result
        else:
            print(f"❌ Analyze failed!")
            print(f"   Response: {response.text}")
            return False, None

    except Exception as e:
        print(f"❌ Error: {e}")
        return False, None

def test_upload_execute(token):
    """Test the execute endpoint"""
    print("\n" + "="*70)
    print("TESTING FILE UPLOAD - EXECUTE ENDPOINT")
    print("="*70)

    # Create a simple CSV file
    csv_content = """first_name,last_name,email,phone
John,Doe,john@example.com,555-1234
Jane,Smith,jane@example.com,555-5678
"""

    # Prepare mappings and answers
    mappings = {
        "first_name": "first_name",
        "last_name": "last_name",
        "email": "email",
        "phone": "phone"
    }

    answers = {
        "destination": "leads"
    }

    files = {
        'file': ('test_leads.csv', csv_content, 'text/csv')
    }

    data = {
        'mappings': json.dumps(mappings),
        'answers': json.dumps(answers)
    }

    headers = {
        "Authorization": f"Bearer {token}"
    }

    try:
        response = requests.post(
            f"{API_BASE_URL}/api/v1/data-import/execute",
            files=files,
            data=data,
            headers=headers
        )

        print(f"\n📊 Status Code: {response.status_code}")

        if response.status_code == 200:
            print(f"✅ Upload executed successfully!")
            result = response.json()
            print(f"\n📋 Upload Results:")
            print(f"   Total rows: {result.get('total', 0)}")
            print(f"   Imported: {result.get('imported', 0)}")
            print(f"   Failed: {result.get('failed', 0)}")
            print(f"   Destination: {result.get('destination', '')}")
            if result.get('errors'):
                print(f"\n⚠️  Errors:")
                for error in result.get('errors', [])[:5]:  # Show first 5 errors
                    print(f"      {error}")
            return True
        else:
            print(f"❌ Upload failed with {response.status_code}!")
            print(f"   Response: {response.text}")

            # Try to parse error details
            try:
                error_data = response.json()
                if 'detail' in error_data:
                    print(f"\n🔍 Error Details: {error_data['detail']}")
            except:
                pass

            return False

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("\n" + "🔷"*35)
    print("DATA UPLOAD FUNCTIONALITY TEST")
    print("🔷"*35)

    # Get auth token
    token = get_auth_token()
    if not token:
        print("\n❌ Cannot proceed without authentication")
        return

    print(f"\n✅ Authentication successful")

    # Test analyze endpoint
    analyze_ok, analysis = test_upload_analyze(token)

    # Test execute endpoint
    execute_ok = test_upload_execute(token)

    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    print(f"\n{'✅' if analyze_ok else '❌'} Analyze Endpoint: {'Working' if analyze_ok else 'Failed'}")
    print(f"{'✅' if execute_ok else '❌'} Execute Endpoint: {'Working' if execute_ok else 'Failed'}")

    if not execute_ok:
        print(f"\n⚠️  Upload functionality is currently broken")
        print(f"   This needs to be fixed before data can be uploaded")

    print("\n" + "🔷"*35 + "\n")

if __name__ == "__main__":
    main()
