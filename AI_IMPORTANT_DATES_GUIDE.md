# AI Important Dates - Implementation Guide

## Overview

The **AI Important Dates** system automatically extracts and tracks critical dates throughout the customer lifecycle (Lead → Active Loan → MUM). As AI processes emails, it fills in date fields and triggers tasks automatically.

---

## ✅ **What's Been Implemented (Part 1)**

### 1. Database Schema Changes

**Added `important_dates` JSON column to:**
- `leads` table
- `loans` table
- `mum_clients` table

**Structure:**
```json
{
  "application_started_date": {
    "date": "2025-01-15",
    "confidence": 0.95,
    "source_text": "started your application on January 15th",
    "label": "Application Started",
    "creates_task": true,
    "task_template": "Follow up on application completion",
    "task_created": false
  }
}
```

### 2. AI Date Extraction Engine (`ai_date_extractor.py`)

**Features:**
- Uses OpenAI GPT-4o to extract dates from emails
- Categorizes dates by process type (lead/loan/mum)
- Confidence scoring (1.0 = explicit mention, 0.7-0.9 = implied)
- Parses relative dates ("next Tuesday", "in 2 weeks")
- Automatic task trigger generation

**Date Categories:**

#### **Lead Pipeline (7 dates):**
1. **First Contact Date** - Initial contact with lead
2. **Application Started** - Borrower began application → *Creates task*
3. **Application Submitted** - Application submitted → *Creates task*
4. **Credit Pull Date** - Credit report pulled
5. **Pre-Approval Issued** - Pre-approval letter issued → *Creates task*
6. **Pre-Approval Expiration** - Expiration date → *Creates task 7 days before*
7. **Expected Closing Date** - Target closing date

#### **Active Loan Pipeline (13 dates):**
1. **Application Date** - Official application date
2. **Initial Disclosure** - Disclosures sent → *Creates task*
3. **Rate Lock Date** - Interest rate locked → *Creates task*
4. **Lock Expiration** - Lock expires → *Creates task 10 days before*
5. **Appraisal Ordered** - Appraisal ordered → *Creates task*
6. **Appraisal Scheduled** - Inspection scheduled → *Creates task*
7. **Appraisal Completed** - Appraisal finished → *Creates task*
8. **Title Ordered** - Title search ordered
9. **HOI Ordered** - Homeowners insurance confirmed → *Creates task*
10. **UW Submission** - Submitted to underwriting → *Creates task*
11. **Approval Date** - Loan approved → *Creates task*
12. **Clear to Close** - CTC received → *Creates task*
13. **Closing Date** - Scheduled closing → *Creates task 3 days before*
14. **Funding Date** - Funds disbursed → *Creates task*
15. **First Payment Due** - First mortgage payment → *Creates task 7 days before*

#### **MUM / Post-Close (6 dates):**
1. **Original Close Date** - Original loan closing
2. **Last Contact** - Most recent touchpoint
3. **Next Review Date** - Scheduled review → *Creates task*
4. **Rate Watch Alert** - Check rates for refi → *Creates task*
5. **Annual Review** - Yearly portfolio review → *Creates task*
6. **Referral Request** - Ask for referrals → *Creates task*

---

## 🚧 **What Needs to Be Completed (Part 2 & 3)**

### **Part 2: API Endpoints & Email Integration**

#### **API Endpoints to Create:**

**GET `/api/v1/{entity_type}/{id}/important-dates`**
```json
{
  "entity_type": "lead",
  "entity_id": 123,
  "important_dates": {
    "application_started_date": {...},
    "credit_pull_date": {...}
  },
  "upcoming_tasks": [
    {
      "date_key": "pre_approval_expiration",
      "task_title": "Renew pre-approval before expiration",
      "due_date": "2025-02-01"
    }
  ]
}
```

**POST `/api/v1/{entity_type}/{id}/important-dates`**
- Manually add/update important dates
- Accepts: `{ "date_key": "application_date", "date": "2025-01-15", "confidence": 1.0 }`

**DELETE `/api/v1/{entity_type}/{id}/important-dates/{date_key}`**
- Remove an extracted date

**POST `/api/v1/{entity_type}/{id}/important-dates/trigger-tasks`**
- Manually trigger task creation from dates

#### **Email Processing Integration:**

Update `process_microsoft_email_to_dre()` in `main.py`:

```python
# After extracting fields, extract dates
from ai_date_extractor import extract_dates_from_email, merge_dates

# Determine process type based on matched entity
process_type = "lead" if entity_match["entity_type"] == "lead" else \
               "loan" if entity_match["entity_type"] == "loan" else "mum"

# Extract dates from email
extracted_dates = extract_dates_from_email(
    email_content=content,
    subject=subject,
    process_type=process_type
)

# Get entity and merge dates
if entity_match["entity_id"]:
    entity = db.query(Lead/Loan/MUMClient).filter_by(id=entity_match["entity_id"]).first()
    if entity:
        existing_dates = entity.important_dates or {}
        updated_dates = merge_dates(existing_dates, extracted_dates)
        entity.important_dates = updated_dates
        db.commit()

        # Trigger tasks
        from ai_date_extractor import get_upcoming_task_triggers
        triggers = get_upcoming_task_triggers(updated_dates)
        for trigger in triggers:
            # Create AITask
            task = AITask(
                title=trigger["task_title"],
                description=f"Auto-generated from {trigger['label']}",
                due_date=trigger["due_date"],
                assigned_to_id=user_id,
                lead_id=entity.id if process_type=="lead" else None,
                loan_id=entity.id if process_type=="loan" else None
            )
            db.add(task)

            # Mark task as created
            updated_dates[trigger["date_key"]]["task_created"] = True

        entity.important_dates = updated_dates
        db.commit()
```

### **Part 3: Frontend & Migration**

#### **Frontend - Important Dates Tab:**

Add to Lead/Loan profile pages:

```jsx
// Frontend component structure
<Tabs>
  <Tab label="Overview" />
  <Tab label="Important Dates" />  {/* NEW */}
  <Tab label="Tasks" />
  <Tab label="Documents" />
</Tabs>

// Important Dates Tab Content
<ImportantDatesTab>
  <DateTimeline>
    {dates.map(date => (
      <DateCard
        key={date.key}
        label={date.label}
        date={date.date}
        confidence={date.confidence}
        source={date.source_text}
        taskCreated={date.task_created}
        onEdit={() => editDate(date)}
        onDelete={() => deleteDate(date.key)}
      />
    ))}
  </DateTimeline>

  <AddDateButton onClick={showAddDateModal} />
</ImportantDatesTab>
```

#### **Database Migration:**

```python
# backend/add_important_dates_columns.py
@app.post("/admin/add-important-dates-columns")
async def add_important_dates_columns(db: Session = Depends(get_db)):
    """Add important_dates JSON columns to leads, loans, and mum_clients"""
    try:
        db.execute(text("""
            ALTER TABLE leads
            ADD COLUMN IF NOT EXISTS important_dates JSON
        """))

        db.execute(text("""
            ALTER TABLE loans
            ADD COLUMN IF NOT EXISTS important_dates JSON
        """))

        db.execute(text("""
            ALTER TABLE mum_clients
            ADD COLUMN IF NOT EXISTS important_dates JSON
        """))

        db.commit()

        return {
            "status": "success",
            "message": "Important dates columns added",
            "tables_updated": ["leads", "loans", "mum_clients"]
        }
    except Exception as e:
        db.rollback()
        return {"status": "error", "message": str(e)}
```

---

## 📊 **Use Cases & Examples**

### **Example 1: Lead Email Processing**

**Email Content:**
> "Hi Sarah, thanks for starting your application on Tuesday! We pulled your credit on January 10th. Your pre-approval letter will be ready by January 15th and will be valid for 90 days."

**AI Extraction:**
```json
{
  "application_started_date": {
    "date": "2025-01-07",
    "confidence": 0.9,
    "source_text": "starting your application on Tuesday",
    "creates_task": true,
    "task_template": "Follow up on application completion"
  },
  "credit_pull_date": {
    "date": "2025-01-10",
    "confidence": 1.0,
    "source_text": "pulled your credit on January 10th"
  },
  "pre_approval_date": {
    "date": "2025-01-15",
    "confidence": 1.0,
    "source_text": "pre-approval letter will be ready by January 15th"
  },
  "pre_approval_expiration": {
    "date": "2025-04-15",
    "confidence": 0.95,
    "source_text": "valid for 90 days",
    "creates_task": true,
    "task_template": "Renew pre-approval before expiration",
    "task_days_before": 7
  }
}
```

**Tasks Auto-Created:**
1. "Follow up on application completion" (due: 2025-01-07)
2. "Renew pre-approval before expiration" (due: 2025-04-08)

### **Example 2: Loan Email Processing**

**Email Content:**
> "Your appraisal has been scheduled for January 20th at 2pm. We're targeting a closing date of February 15th. Your rate lock expires on February 10th."

**AI Extraction:**
```json
{
  "appraisal_scheduled_date": {
    "date": "2025-01-20",
    "confidence": 1.0,
    "creates_task": true,
    "task_template": "Remind borrower of appraisal appointment"
  },
  "closing_date": {
    "date": "2025-02-15",
    "confidence": 0.9,
    "creates_task": true,
    "task_template": "Send closing reminder and checklist",
    "task_days_before": 3
  },
  "lock_expiration_date": {
    "date": "2025-02-10",
    "confidence": 1.0,
    "creates_task": true,
    "task_template": "Extend rate lock or close before expiration",
    "task_days_before": 10
  }
}
```

**Tasks Auto-Created:**
1. "Remind borrower of appraisal appointment" (due: 2025-01-20)
2. "Extend rate lock or close before expiration" (due: 2025-01-31)
3. "Send closing reminder and checklist" (due: 2025-02-12)

---

## 🎯 **Benefits**

1. **Zero Manual Data Entry**: AI fills in dates automatically from emails
2. **Proactive Task Management**: Tasks created before deadlines
3. **Complete Audit Trail**: Source text for every extracted date
4. **Confidence Scoring**: Know which dates are certain vs. estimated
5. **Full Lifecycle Coverage**: From first contact → closing → post-close
6. **Automatic Reminders**: Never miss a deadline or expiration

---

## 🚀 **Deployment Checklist**

### **Immediate (Part 1 - DONE)**
- ✅ Added `important_dates` column to database models
- ✅ Created AI date extraction engine
- ✅ Defined all date categories and task triggers

### **Next Steps (Part 2)**
- ⏳ Create API endpoints for CRUD operations
- ⏳ Integrate date extraction into email processing
- ⏳ Add task creation logic
- ⏳ Run database migration

### **Future (Part 3)**
- ⏳ Build frontend "Important Dates" tab
- ⏳ Add manual date entry UI
- ⏳ Create date timeline visualization
- ⏳ Add date conflict detection

---

## 📝 **Configuration**

Set `OPENAI_API_KEY` in Railway environment variables (already configured).

No additional configuration needed - the system uses existing OpenAI client.

---

## 🔍 **Testing**

```python
# Test date extraction
from ai_date_extractor import extract_dates_from_email

email = "Your appraisal is scheduled for next Tuesday"
dates = extract_dates_from_email(email, "Appraisal Update", "loan")
print(dates)
# {
#   "appraisal_scheduled_date": {
#     "date": "2025-01-21",
#     "confidence": 0.9,
#     ...
#   }
# }
```

---

**System Status:** Part 1 complete, ready for Part 2 implementation.

**Goal:** AI autonomously manages the entire customer lifecycle by tracking every important date and triggering tasks automatically.
