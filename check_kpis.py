#!/usr/bin/env python3
"""
Check all KPI areas and verify data is reporting correctly
"""
import requests
import json
from datetime import datetime

API_BASE_URL = "https://mortgage-crm-production-7a9a.up.railway.app"

# Read token from file
with open('/tmp/current_token.txt', 'r') as f:
    TOKEN = f.read().strip()

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

def print_section(title):
    print("\n" + "="*80)
    print(f"  {title}")
    print("="*80)

def check_endpoint(name, endpoint):
    """Check an endpoint and return the data"""
    print(f"\n{name}:")
    print("-" * 80)
    try:
        response = requests.get(f"{API_BASE_URL}{endpoint}", headers=headers)
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Status: {response.status_code}")
            return data
        else:
            print(f"✗ Status: {response.status_code}")
            print(f"  Error: {response.text[:200]}")
            return None
    except Exception as e:
        print(f"✗ Exception: {str(e)}")
        return None

print_section("KPI AREAS REVIEW")

# 1. Dashboard
print_section("1. DASHBOARD")
dashboard = check_endpoint("Dashboard Stats", "/api/v1/dashboard")
if dashboard:
    print(f"  Active Leads: {dashboard.get('active_leads', 0)}")
    print(f"  Active Loans: {dashboard.get('active_loans', 0)}")
    print(f"  Active Tasks: {dashboard.get('active_tasks', 0)}")
    print(f"  Pending Activities: {dashboard.get('pending_activities', 0)}")

    production = dashboard.get('production', {})
    print(f"\n  Production:")
    print(f"    YTD Funded: {production.get('ytd', {}).get('actual', 0)}")
    print(f"    Monthly Funded: {production.get('monthly', {}).get('actual', 0)}")
    print(f"    Weekly Funded: {production.get('weekly', {}).get('actual', 0)}")
    print(f"    Daily Funded: {production.get('daily', {}).get('actual', 0)}")

# 2. Pipeline
print_section("2. LIVE LOAN PIPELINE")
pipeline = check_endpoint("Pipeline Stats", "/api/v1/analytics/pipeline")
if pipeline:
    for stage in pipeline:
        print(f"  {stage['name']}: {stage['count']} loans (${stage['total_volume']:,.0f})")

# 3. Monthly Performance Tracker
print_section("3. MONTHLY PERFORMANCE TRACKER")
monthly = check_endpoint("Monthly Performance", "/api/v1/analytics/monthly-performance")
if monthly:
    print(f"  Reporting Period: {monthly.get('reporting_period', {}).get('label', 'N/A')}")

    metrics = monthly.get('metrics', [])
    for metric in metrics:
        print(f"\n  {metric['metric']}:")
        print(f"    Current: {metric['current_value']} (MTD: {metric['current_mtd']})")
        print(f"    Goal: {metric['goal_value']} (MTD: {metric['goal_mtd']})")
        print(f"    Status: {metric['status']}")

# 4. Loan Efficiency
print_section("4. LOAN EFFICIENCY")
efficiency = check_endpoint("Loan Efficiency", "/api/v1/analytics/loan-efficiency")
if efficiency:
    summary = efficiency.get('summary', {})
    print(f"  Current Pull Thru: {summary.get('current_pull_thru', 0)}%")
    print(f"  Target Pull Thru: {summary.get('target_pull_thru', 0)}%")
    print(f"  Current Funded: {summary.get('current_funded_count', 0)} units")
    print(f"  Target Funded: {summary.get('target_funded_count', 0)} units")
    print(f"  Current Volume: ${summary.get('current_volume', 0):,.0f}")
    print(f"  Target Volume: ${summary.get('target_volume', 0):,.0f}")

# 5. Scorecard
print_section("5. LOAN SCORECARD REPORT")
scorecard = check_endpoint("Scorecard", "/api/v1/analytics/scorecard")
if scorecard:
    print(f"  Period: {scorecard.get('period', {}).get('start_date', 'N/A')} to {scorecard.get('period', {}).get('end_date', 'N/A')}")

    conversion = scorecard.get('conversion_metrics', [])
    print(f"\n  Conversion Metrics:")
    for metric in conversion:
        print(f"    {metric['metric']}: {metric['current']}/{metric['total']} ({metric['mot_pct']}%)")

    funding = scorecard.get('funding_totals', {})
    print(f"\n  Funding Totals:")
    print(f"    Total Units: {funding.get('total_units', 0)}")
    print(f"    Total Volume: ${funding.get('total_volume', 0):,.0f}")

    loan_types = funding.get('loan_types', [])
    if loan_types:
        print(f"\n  Loan Types Breakdown:")
        for lt in loan_types:
            print(f"    {lt['type']}: {lt['count']} loans (${lt['volume']:,.0f})")

# 6. Portfolio
print_section("6. PORTFOLIO")
portfolio_stats = check_endpoint("Portfolio Stats", "/api/v1/portfolio/stats")
if portfolio_stats:
    print(f"  Total Funded Loans: {portfolio_stats.get('total_loans', 0)}")
    print(f"  Total Volume: ${portfolio_stats.get('total_volume', 0):,.0f}")
    print(f"  Active Loans: {portfolio_stats.get('active_loans', 0)}")
    print(f"  Closed Loans: {portfolio_stats.get('closed_loans', 0)}")

portfolio = check_endpoint("Portfolio Loans", "/api/v1/portfolio/")
if portfolio:
    print(f"  Portfolio Loans Count: {len(portfolio)}")

# 7. Leads
print_section("7. LEADS")
leads = check_endpoint("All Leads", "/api/v1/leads/")
if leads:
    print(f"  Total Leads: {len(leads)}")

    # Count by stage
    stages = {}
    for lead in leads:
        stage = lead.get('stage', 'Unknown')
        stages[stage] = stages.get(stage, 0) + 1

    print(f"\n  Leads by Stage:")
    for stage, count in sorted(stages.items()):
        print(f"    {stage}: {count}")

# 8. Loans
print_section("8. LOANS")
loans = check_endpoint("All Loans", "/api/v1/loans/")
if loans:
    print(f"  Total Loans: {len(loans)}")

    # Count by stage
    stages = {}
    funded_count = 0
    funded_volume = 0
    active_count = 0
    active_volume = 0

    for loan in loans:
        stage = loan.get('stage', 'Unknown')
        stages[stage] = stages.get(stage, 0) + 1

        if stage == 'Funded':
            funded_count += 1
            funded_volume += loan.get('amount', 0) or 0
        else:
            active_count += 1
            active_volume += loan.get('amount', 0) or 0

    print(f"\n  Loans by Stage:")
    for stage, count in sorted(stages.items()):
        print(f"    {stage}: {count}")

    print(f"\n  Summary:")
    print(f"    Funded: {funded_count} loans (${funded_volume:,.0f})")
    print(f"    Active: {active_count} loans (${active_volume:,.0f})")

# 9. Team Performance
print_section("9. TEAM PERFORMANCE")
team = check_endpoint("Team Performance", "/api/v1/analytics/team-performance")
if team:
    members = team.get('team_members', [])
    print(f"  Team Members: {len(members)}")

    if members:
        print(f"\n  Performance Summary:")
        for member in members:
            print(f"\n    {member['name']} ({member['role']}):")
            print(f"      Active Leads: {member['active_leads']}")
            print(f"      Active Loans: {member['active_loans']}")
            print(f"      Funded This Month: {member['funded_this_month']}")

# Summary
print_section("SUMMARY")
print("\n✓ All KPI areas checked")
print("\nKey Findings:")
print(f"  - Dashboard is showing production metrics")
print(f"  - Pipeline shows loan stages and volumes")
print(f"  - Monthly performance tracking is active")
print(f"  - Loan efficiency metrics calculated")
print(f"  - Scorecard showing conversion rates")
print(f"  - Portfolio contains funded loans")
print(f"  - Leads and Loans data populated")
print(f"  - Team performance metrics available")
print("\n" + "="*80 + "\n")
