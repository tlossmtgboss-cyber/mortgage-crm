#!/usr/bin/env python3
"""
Test data upload functionality with Excel file
"""
import os
import sys
import requests

# Add backend to path for imports
sys.path.insert(0, '/Users/timothyloss/my-project/mortgage-crm/backend')

print("🧪 TESTING DATA UPLOAD FUNCTIONALITY\n")
print("=" * 70)

# Step 1: Create a test Excel file
print("\n1. Creating test Excel file...")
try:
    import pandas as pd

    test_data = {
        'First Name': ['John', 'Jane', 'Bob'],
        'Last Name': ['Doe', 'Smith', 'Johnson'],
        'Email': ['john.doe@example.com', 'jane.smith@example.com', 'bob.j@example.com'],
        'Phone': ['555-123-4567', '555-234-5678', '555-345-6789'],
        'City': ['Charleston', 'Mount Pleasant', 'Summerville'],
        'State': ['SC', 'SC', 'SC'],
        'Loan Amount': [450000, 380000, 520000],
        'Annual Income': [120000, 95000, 145000],
        'Credit Score': [720, 695, 745]
    }

    df = pd.DataFrame(test_data)
    test_file = '/tmp/test_leads.xlsx'
    df.to_excel(test_file, index=False)
    print(f"   ✅ Test file created: {test_file}")
    print(f"   📊 Contains {len(df)} rows with {len(df.columns)} columns")
except Exception as e:
    print(f"   ❌ Error creating test file: {e}")
    print(f"   💡 Installing pandas and openpyxl...")
    os.system("pip install pandas openpyxl -q")
    # Try again
    df = pd.DataFrame(test_data)
    test_file = '/tmp/test_leads.xlsx'
    df.to_excel(test_file, index=False)
    print(f"   ✅ Test file created: {test_file}")

# Step 2: Test analyze endpoint
print("\n2. Testing /api/v1/data-import/analyze endpoint...")
BACKEND_URL = "https://app.perenniaai.com"

# First get a token
print("   Getting auth token...")
login_response = requests.post(
    f"{BACKEND_URL}/token",
    data={
        "username": "admin@perenniaai.com",
        "password": "demo123"
    }
)

if login_response.status_code == 200:
    token = login_response.json()['access_token']
    print("   ✅ Authenticated successfully")
else:
    print(f"   ❌ Login failed: {login_response.status_code}")
    print(f"   Response: {login_response.text}")
    sys.exit(1)

# Test analyze endpoint
print("\n   Uploading file for analysis...")
with open(test_file, 'rb') as f:
    files = {'file': ('test_leads.xlsx', f, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
    headers = {'Authorization': f'Bearer {token}'}

    response = requests.post(
        f"{BACKEND_URL}/api/v1/data-import/analyze",
        files=files,
        headers=headers
    )

if response.status_code == 200:
    data = response.json()
    print("   ✅ File analyzed successfully!")
    print(f"\n   📊 Analysis Results:")
    print(f"   ├─ Headers: {data['preview']['headers']}")
    print(f"   ├─ Total Rows: {data['preview']['total_rows']}")
    print(f"   ├─ Questions: {len(data['questions'])} questions generated")
    print(f"   └─ Suggested Mappings: {len(data['suggested_mappings'])} columns mapped")

    # Print questions
    print(f"\n   💬 AI Questions:")
    for i, q in enumerate(data['questions'], 1):
        print(f"   {i}. {q['question']}")
        if q['type'] == 'choice':
            for opt in q['options']:
                print(f"      • {opt['label']}: {opt['description']}")

    # Print suggested mappings
    print(f"\n   🗺️  Suggested Column Mappings:")
    for source, target in data['suggested_mappings'].items():
        print(f"      {source} → {target}")

    # Step 3: Test execute endpoint
    print("\n3. Testing /api/v1/data-import/execute endpoint...")

    # Prepare answers and mappings
    answers = {"destination": "leads"}
    mappings = data['suggested_mappings']

    # Re-upload file for execution
    with open(test_file, 'rb') as f:
        files = {'file': ('test_leads.xlsx', f, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
        execute_data = {
            'answers': str(answers).replace("'", '"'),
            'mappings': str(mappings).replace("'", '"')
        }

        exec_response = requests.post(
            f"{BACKEND_URL}/api/v1/data-import/execute",
            files=files,
            data=execute_data,
            headers=headers
        )

    if exec_response.status_code == 200:
        result = exec_response.json()
        print("   ✅ Data imported successfully!")
        print(f"\n   📊 Import Results:")
        print(f"   ├─ Total Records: {result['total']}")
        print(f"   ├─ Imported: {result['imported']}")
        print(f"   ├─ Failed: {result['failed']}")
        print(f"   └─ Destination: {result['destination']}")

        if result['errors']:
            print(f"\n   ⚠️  Errors ({len(result['errors'])}):")
            for error in result['errors'][:5]:
                print(f"      • {error}")
    else:
        print(f"   ❌ Import failed: {exec_response.status_code}")
        print(f"   Response: {exec_response.text}")

else:
    print(f"   ❌ Analysis failed: {response.status_code}")
    print(f"   Response: {response.text[:500]}")

print("\n" + "=" * 70)
print("✅ DATA UPLOAD TEST COMPLETE")
print("=" * 70)
print("\n📝 Summary:")
print("   1. Test Excel file created ✓")
print("   2. Analyze endpoint tested")
print("   3. Execute endpoint tested")
print("\n🎯 To test in UI:")
print(f"   1. Login to: https://mortgage-crm-nine.vercel.app")
print(f"   2. Go to Settings → Data Management")
print(f"   3. Upload file: {test_file}")
print(f"   4. Follow the AI-guided import process")
