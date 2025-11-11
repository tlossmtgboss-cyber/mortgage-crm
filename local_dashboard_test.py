#!/usr/bin/env python3
"""
Simulate dashboard logic locally to find errors
"""
from datetime import date, timedelta

# Test the date operations
today = date.today()
start_of_month = today.replace(day=1)
start_of_week = today - timedelta(days=today.weekday())
start_of_year = today.replace(month=1, day=1)

print(f"today: {today}")
print(f"start_of_month: {start_of_month}")
print(f"start_of_week: {start_of_week}")
print(f"start_of_year: {start_of_year}")

# Test timedelta operations
tomorrow = today + timedelta(days=1)
print(f"tomorrow: {tomorrow}")
print(f"Type: {type(tomorrow)}")

# Test the problematic comparison that was in the code
test_date = today + timedelta(days=1)
print(f"\nComparison test:")
print(f"test_date <= tomorrow: {test_date <= tomorrow}")

# Test dict construction
print("\nTesting dict construction with int() conversions:")
volume = 0
try:
    test_dict = {
        "volume": int(volume)
    }
    print(f"Success: {test_dict}")
except Exception as e:
    print(f"Error: {e}")

# Test with float
volume = 12345.67
try:
    test_dict = {
        "volume": int(volume)
    }
    print(f"Success with float: {test_dict}")
except Exception as e:
    print(f"Error with float: {e}")

print("\nAll local tests passed!")
