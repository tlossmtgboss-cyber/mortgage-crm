# Team Hierarchy for Referral Partners

## Overview

Your CRM now supports **team → member hierarchies** for referral partners. This allows you to:

- Track team-level performance (e.g., Keller Williams Team)
- Track individual agent performance within teams
- Calculate reciprocity scores at both levels
- Assign leads to specific agents within a team

---

## Database Structure

```
📁 Keller Williams Team (partner_category="team", id=1)
   ├── 👤 Sarah Johnson (partner_category="individual", parent_team_id=1)
   ├── 👤 Mike Roberts (partner_category="individual", parent_team_id=1)
   └── 👤 Lisa Chen (partner_category="individual", parent_team_id=1)
```

---

## Setup Instructions

### Step 1: Run Migration

Add the `parent_team_id` column to your database:

```bash
cd backend
python3 add_team_hierarchy.py
```

This will:
- Add `parent_team_id` column to `referral_partners` table
- Create foreign key relationship for team hierarchy

---

### Step 2: Create a Team

**API Request:**
```bash
POST /api/v1/referral-partners/
Authorization: Bearer <your_token>
Content-Type: application/json

{
  "name": "Keller Williams Team",
  "company": "Keller Williams Realty",
  "type": "Real Estate Team",
  "phone": "555-1234",
  "email": "team@kw.com",
  "partner_category": "team"  ← Important!
}
```

**Response:**
```json
{
  "id": 1,
  "name": "Keller Williams Team",
  "company": "Keller Williams Realty",
  "partner_category": "team",
  "member_count": 0,
  ...
}
```

---

### Step 3: Add Team Members

**API Request:**
```bash
POST /api/v1/referral-partners/
Authorization: Bearer <your_token>
Content-Type: application/json

{
  "name": "Sarah Johnson",
  "company": "Keller Williams Realty",
  "type": "Real Estate Agent",
  "phone": "555-2001",
  "email": "sarah@kw.com",
  "partner_category": "individual",
  "parent_team_id": 1  ← Links to team
}
```

Repeat for each team member.

---

## API Endpoints

### 1. Get All Partners (with Member Count)

```bash
GET /api/v1/referral-partners/
Authorization: Bearer <your_token>
```

**Response:**
```json
[
  {
    "id": 1,
    "name": "Keller Williams Team",
    "partner_category": "team",
    "member_count": 3,  ← Shows number of agents
    ...
  },
  {
    "id": 2,
    "name": "Sarah Johnson",
    "partner_category": "individual",
    "parent_team_id": 1,  ← Links to team
    "member_count": 0,
    ...
  }
]
```

### 2. Get Team Members

```bash
GET /api/v1/referral-partners/1/members
Authorization: Bearer <your_token>
```

**Response:**
```json
[
  {
    "id": 2,
    "name": "Sarah Johnson",
    "referrals_in": 5,
    "closed_loans": 3,
    "volume": 1200000,
    ...
  },
  {
    "id": 3,
    "name": "Mike Roberts",
    "referrals_in": 8,
    "closed_loans": 6,
    "volume": 2400000,
    ...
  }
]
```

---

## Use Cases

### 1. Real Estate Brokerages

```
📁 Coldwell Banker Downtown (team)
   ├── 👤 Agent 1 (10 deals)
   ├── 👤 Agent 2 (15 deals)
   ├── 👤 Agent 3 (8 deals)
   └── 👤 Agent 4 (12 deals)

Team Total: 45 deals
```

### 2. Builder Sales Teams

```
📁 Lennar Homes - South Division (team)
   ├── 👤 Sales Rep A
   ├── 👤 Sales Rep B
   └── 👤 Sales Rep C
```

### 3. Financial Advisor Firms

```
📁 Wealth Management Group (team)
   ├── 👤 Advisor 1
   ├── 👤 Advisor 2
   └── 👤 Advisor 3
```

---

## Metrics Tracking

### Team-Level Metrics
- Total referrals from all members
- Combined closed loans
- Total volume from team
- Team reciprocity score

### Individual Agent Metrics
- Personal referrals
- Personal closed loans
- Individual volume
- Agent-level reciprocity

### Example Query
```sql
-- Get team performance summary
SELECT
  t.name AS team_name,
  COUNT(m.id) AS member_count,
  SUM(m.referrals_in) AS total_referrals,
  SUM(m.closed_loans) AS total_closed,
  SUM(m.volume) AS total_volume
FROM referral_partners t
LEFT JOIN referral_partners m ON m.parent_team_id = t.id
WHERE t.partner_category = 'team'
GROUP BY t.id, t.name;
```

---

## Frontend Integration

### Display Team with Members

```typescript
// Fetch team
const team = await fetch('/api/v1/referral-partners/1');

// Fetch members
const members = await fetch('/api/v1/referral-partners/1/members');

// Display
console.log(`${team.name} (${team.member_count} members)`);
members.forEach(member => {
  console.log(`  - ${member.name}: ${member.referrals_in} referrals`);
});
```

---

## Migration for Existing Data

If you already have referral partners and want to organize them into teams:

1. **Create teams first:**
   ```bash
   POST /api/v1/referral-partners/
   { "name": "Team Name", "partner_category": "team" }
   ```

2. **Update existing partners:**
   ```bash
   PATCH /api/v1/referral-partners/5
   { "parent_team_id": 1 }
   ```

---

## Business Intelligence

With team hierarchy, you can now answer:

✅ Which real estate team sends us the most business?
✅ Who is the top-performing agent within Team X?
✅ Are we reciprocating with all agents in a brokerage?
✅ Which builder's sales reps need more attention?
✅ Should we host an event for Team Y based on their performance?

---

## Next Steps

1. ✅ Run migration: `python3 backend/add_team_hierarchy.py`
2. ✅ Create your first team via API or frontend
3. ✅ Add team members with `parent_team_id`
4. ✅ View team performance in dashboard
5. ✅ Build reciprocity reports by team and individual

---

## Questions?

- **Q: Can an agent belong to multiple teams?**
  A: No, current structure supports one parent team per agent. You can link agents to the primary team they work with.

- **Q: Can teams have sub-teams?**
  A: Not yet, but the structure supports it (nested hierarchy). Future enhancement.

- **Q: What happens if I delete a team?**
  A: The members will remain, but `parent_team_id` will be null. Consider archiving teams instead.

---

**Your CRM is now ready for team-based partner management! 🎉**
