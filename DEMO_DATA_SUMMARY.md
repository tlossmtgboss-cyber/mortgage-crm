# Demo Data & Calculations Summary

## ✅ What's Working

### Demo Data Created (21 Total Records)

#### 👥 Team Members (9 people)
All with password: `demo123`

**Leadership:**
- sarah.mitchell@company.com - Chief Lending Officer (Admin)
- michael.chen@company.com - VP of Operations (Management)

**Management:**
- jennifer.rodriguez@company.com - Sales Manager
- david.thompson@company.com - Operations Manager

**Operations:**
- robert.garcia@company.com - Senior Processor
- amanda.foster@company.com - Loan Processor

**Sales:**
- marcus.johnson@company.com - Senior Loan Officer
- emily.patterson@company.com - Loan Officer
- brandon.lee@company.com - Loan Officer

#### 🎯 Leads (5 prospects) - Owned by demo@example.com
1. **James Wilson** - New ($360,000 loan)
   - Property: $450,000
   - Down Payment: $90,000 (20%)
   - LTV: 80%
   - Credit: 750

2. **Maria Hernandez** - Prospect ($313,625 loan)
   - Property: $325,000
   - Down Payment: $11,375 (3.5% FHA)
   - LTV: 96.5%
   - Credit: 680

3. **Robert Taylor** - Application Started ($550,000 refi)
   - Property: $550,000
   - Credit: 720

4. **Ashley Thompson** - Application Complete ($380,000 loan)
   - Property: $380,000
   - VA Loan (0% down)
   - Credit: 695

5. **Christopher Davis** - Pre-Approved ($680,000 loan)
   - Property: $850,000
   - Down Payment: $170,000 (20%)
   - LTV: 80%
   - Credit: 780
   - **Pre-approval Amount: $680,000**

#### 💰 Active Loans (4 in pipeline) - Owned by demo@example.com

1. **2025-001234** - Michael & Sarah Roberts
   - Amount: $420,000
   - Program: Conventional 30-Year Fixed
   - Rate: 6.875%
   - Stage: Processing
   - Closing: ~25 days

2. **2025-001235** - Jennifer Kim
   - Amount: $285,000
   - Program: FHA 30-Year Fixed
   - Rate: 6.625%
   - Stage: UW Received
   - Closing: ~25 days

3. **2025-001236** - William & Patricia Turner
   - Amount: $365,000
   - Program: VA 30-Year Fixed
   - Rate: 6.500%
   - Stage: Approved
   - Closing: ~25 days

4. **2025-001237** - Elizabeth & Richard Moore
   - Amount: $825,000
   - Program: Jumbo 30-Year Fixed
   - Rate: 7.125%
   - Stage: CTC (Clear to Close)
   - Closing: ~25 days

**Total Pipeline Value: $1,895,000**

#### 🏡 MUM Clients (3 past clients)

1. **Charles Bennett** (MUM-2023-001)
   - Original Loan: $385,000 (2 years ago)
   - Current Balance: $354,200 (8% paid down)
   - Original Rate: 6.5%
   - Current Rate: 6.875%
   - Engagement: 75/100

2. **Rebecca Sullivan** (MUM-2022-001)
   - Original Loan: $425,000 (3 years ago)
   - Current Balance: $391,000
   - Original Rate: 6.5%
   - Engagement: 75/100

3. **Gregory Phillips** (MUM-2024-001)
   - Original Loan: $295,000 (1 year ago)
   - Current Balance: $271,400
   - Original Rate: 6.5%
   - Engagement: 75/100

## 📊 Calculations That Should Be Working

### Dashboard Metrics
- **Production Numbers:**
  - Annual Goal vs Actual (funded loans)
  - Monthly Goal vs Actual
  - Weekly Goal vs Actual
  - Daily Goal vs Actual

- **Pipeline Stats:**
  - New Leads Count (should show 1-2 based on stage)
  - Pre-Approved Count (should show 1 - Christopher Davis)
  - Processing Count (should show 1 - Loan 2025-001234)
  - In Underwriting Count (should show 1 - Loan 2025-001235)
  - Clear to Close Count (should show 1 - Loan 2025-001237)

- **Pipeline Volume:**
  - Processing: $420,000
  - Underwriting: $285,000
  - CTC: $825,000
  - **Total Active: $1,530,000**

### Lead Calculations
Each lead should show:
- **Loan Amount** = Property Value - Down Payment
- **LTV (Loan-to-Value)** = (Loan Amount / Property Value) × 100
- **DTI (Debt-to-Income)** = ~35% (estimated)
- **AI Score** = 50-95 based on credit, pre-approval, contact info

### Loan Calculations
Each loan should display:
- **Amount** (from database)
- **Rate** (interest rate)
- **Monthly Payment** = calculated from amount, rate, term
- **Days in Stage** (calculated from dates)
- **SLA Status** (on-track, at-risk, delayed)
- **Risk Score** (0-100)

### MUM Client Calculations
Each client should show:
- **Current Balance** = Original Amount × 0.92 (assuming 8% paid down)
- **Equity** = Current Home Value - Current Balance
- **Days Since Funding** = Today - Original Close Date
- **Engagement Score** = 75 (set in seed data)
- **Refinance Opportunity** = Based on rate comparison

## 🔧 Endpoints Created

1. **POST /api/v1/admin/seed-demo-people**
   - Creates all 21 demo records
   - Idempotent (won't duplicate)
   - Run via: `./seed_demo_data.sh`

2. **POST /api/v1/admin/assign-demo-data**
   - Assigns demo leads/loans to current user
   - Makes data visible in your dashboard
   - Run via: `./update_demo_user_data.sh`

## 🎯 How to View the Data

### Option 1: Login as Demo User
```
Email: demo@example.com
Password: demo123
```

Then run:
```bash
./update_demo_user_data.sh
```

This assigns all demo data to your user so it appears in your dashboard.

### Option 2: Login as a Loan Officer
Any of these accounts will show leads/loans assigned to them:
```
marcus.johnson@company.com / demo123
emily.patterson@company.com / demo123
brandon.lee@company.com / demo123
```

## 📈 Expected Dashboard Values

When logged in as demo@example.com (after assigning data):

**Leads Section:**
- Total Leads: 5
- New Leads: 1-2
- Pre-Approved: 1
- Average Credit Score: ~720

**Loans Section:**
- Total Active Loans: 4
- Processing: 1 ($420K)
- Underwriting: 1 ($285K)
- Approved: 1 ($365K)
- CTC: 1 ($825K)
- **Total Pipeline: $1,895,000**

**MUM Section:**
- Total Clients: 3
- Average Balance: ~$339K
- Total Book: ~$1,017,000

## ✅ Verification Steps

1. **Check Data Exists:**
   ```bash
   ./seed_demo_data.sh
   ```
   Should show: 21 total records created (or skipped if exists)

2. **Assign to Your User:**
   ```bash
   ./update_demo_user_data.sh
   ```
   Should show: 5 leads + 4 loans assigned

3. **View in Browser:**
   - https://mortgage-crm-nine.vercel.app/login
   - Login: demo@example.com / demo123
   - Navigate to:
     - Dashboard (should show pipeline stats)
     - Leads (should show 5 leads)
     - Loans (should show 4 active loans)
     - MUM Clients (should show 3 clients)

## 🐛 Troubleshooting

If dashboard shows "Internal Server Error":
- Check Railway logs: `railway logs`
- Recent fix: Changed `loan.status` to `loan.stage`
- Should be fixed in latest deployment

If leads/loans don't appear:
- Run `./update_demo_user_data.sh` to assign to your user
- Check you're logged in as demo@example.com
- Verify data exists: Check API directly via curl scripts

## 🔄 Re-seeding Data

To start fresh:
1. Delete all demo data (TODO: create clear endpoint)
2. Run `./seed_demo_data.sh` again
3. Run `./update_demo_user_data.sh` to assign

---

*Last Updated: 2025-11-17*
*Demo data seeded successfully with 21 records across all categories*
