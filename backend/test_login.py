#!/usr/bin/env python3
"""Test login to mortgage guidelines to debug form fields"""
import os
import requests
from bs4 import BeautifulSoup

URL = "https://my.mortgageguidelines.com/account-login/"
USERNAME = os.environ.get("MG_USERNAME", "")
PASSWORD = os.environ.get("MG_PASSWORD", "")

def test_login():
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    })

    print(f"Fetching login page: {URL}\n")
    response = session.get(URL)
    print(f"Status: {response.status_code}")
    print(f"URL after redirect: {response.url}\n")

    soup = BeautifulSoup(response.content, 'html.parser')

    # Find all forms
    forms = soup.find_all('form')
    print(f"Found {len(forms)} forms on the page\n")

    for i, form in enumerate(forms):
        print(f"\n=== FORM {i+1} ===")
        print(f"Action: {form.get('action')}")
        print(f"Method: {form.get('method')}")
        print("\nInput fields:")

        inputs = form.find_all(['input', 'select', 'textarea'])
        for inp in inputs:
            name = inp.get('name')
            inp_type = inp.get('type', 'text')
            value = inp.get('value', '')
            print(f"  - {name}: type={inp_type}, value={value}")

    # Save HTML for inspection
    with open('/tmp/login_page.html', 'w') as f:
        f.write(response.text)
    print("\n✅ Saved full HTML to /tmp/login_page.html")

if __name__ == "__main__":
    test_login()
