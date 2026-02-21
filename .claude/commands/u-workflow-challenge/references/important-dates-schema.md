# Important Dates Schema — Source of Truth for Workflow Triggers

## Overview

The Important Dates tab on the client profile is the single source of truth for when each
milestone was entered. Every workflow trigger, every SLA calculation, and every task generation
depends on these date fields being correctly populated.

---

## Database Schema

### Option A: Dedicated Columns on loans/leads (Current Approach)

```sql
-- =====================================================
-- IMPORTANT DATES COLUMNS ON LOANS TABLE
-- These are the fields displayed in the Important Dates tab
-- =====================================================

ALTER TABLE loans ADD COLUMN IF NOT EXISTS new_lead_date TIMESTAMPTZ;
ALTER TABLE loans ADD COLUMN IF NOT EXISTS attempted_contact_date TIMESTAMPTZ;
ALTER TABLE loans ADD COLUMN IF NOT EXISTS pre_qual_date TIMESTAMPTZ;
ALTER TABLE loans ADD COLUMN IF NOT EXISTS pre_approval_date TIMESTAMPTZ;
ALTER TABLE loans ADD COLUMN IF NOT EXISTS application_received_date TIMESTAMPTZ;
ALTER TABLE loans ADD COLUMN IF NOT EXISTS credit_pulled_date TIMESTAMPTZ;
ALTER TABLE loans ADD COLUMN IF NOT EXISTS disclosed_date TIMESTAMPTZ;
ALTER TABLE loans ADD COLUMN IF NOT EXISTS processing_date TIMESTAMPTZ;
ALTER TABLE loans ADD COLUMN IF NOT EXISTS appraisal_ordered_date TIMESTAMPTZ;
ALTER TABLE loans ADD COLUMN IF NOT EXISTS appraisal_received_date TIMESTAMPTZ;
ALTER TABLE loans ADD COLUMN IF NOT EXISTS title_ordered_date TIMESTAMPTZ;
ALTER TABLE loans ADD COLUMN IF NOT EXISTS title_received_date TIMESTAMPTZ;
ALTER TABLE loans ADD COLUMN IF NOT EXISTS uw_submission_date TIMESTAMPTZ;
ALTER TABLE loans ADD COLUMN IF NOT EXISTS conditional_approval_date TIMESTAMPTZ;
ALTER TABLE loans ADD COLUMN IF NOT EXISTS conditions_sent_date TIMESTAMPTZ;
ALTER TABLE loans ADD COLUMN IF NOT EXISTS conditions_received_date TIMESTAMPTZ;
ALTER TABLE loans ADD COLUMN IF NOT EXISTS resubmission_date TIMESTAMPTZ;
ALTER TABLE loans ADD COLUMN IF NOT EXISTS clear_to_close_date TIMESTAMPTZ;
ALTER TABLE loans ADD COLUMN IF NOT EXISTS closing_disclosure_sent_date TIMESTAMPTZ;
ALTER TABLE loans ADD COLUMN IF NOT EXISTS closing_scheduled_date TIMESTAMPTZ;
ALTER TABLE loans ADD COLUMN IF NOT EXISTS funded_date TIMESTAMPTZ;
ALTER TABLE loans ADD COLUMN IF NOT EXISTS mum_date TIMESTAMPTZ;
ALTER TABLE loans ADD COLUMN IF NOT EXISTS suspended_date TIMESTAMPTZ;

-- Current state fields (fast reads for workflow engine)
ALTER TABLE loans ADD COLUMN IF NOT EXISTS current_milestone_status VARCHAR(50);
ALTER TABLE loans ADD COLUMN IF NOT EXISTS current_milestone_entered_at TIMESTAMPTZ;

-- Same for leads table
ALTER TABLE leads ADD COLUMN IF NOT EXISTS new_lead_date TIMESTAMPTZ;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS attempted_contact_date TIMESTAMPTZ;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS pre_qual_date TIMESTAMPTZ;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS pre_approval_date TIMESTAMPTZ;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS application_received_date TIMESTAMPTZ;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS current_milestone_status VARCHAR(50);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS current_milestone_entered_at TIMESTAMPTZ;

-- Performance indexes
CREATE INDEX IF NOT EXISTS idx_loans_milestone_status 
    ON loans(current_milestone_status, current_milestone_entered_at);
CREATE INDEX IF NOT EXISTS idx_leads_milestone_status 
    ON leads(current_milestone_status, current_milestone_entered_at);
CREATE INDEX IF NOT EXISTS idx_loans_org_milestone 
    ON loans(organization_id, current_milestone_status) WHERE current_milestone_status IS NOT NULL;
```

### Option B: Milestone History Table (Audit Trail + Single Source of Truth)

```sql
-- =====================================================
-- LOAN MILESTONE HISTORY
-- Records every milestone transition with precise timestamps
-- This is the audit trail AND the calculation source
-- =====================================================

CREATE TABLE IF NOT EXISTS loan_milestone_history (
    id BIGSERIAL PRIMARY KEY,
    loan_id BIGINT NOT NULL REFERENCES loans(id) ON DELETE CASCADE,
    lead_id BIGINT REFERENCES leads(id) ON DELETE CASCADE,
    organization_id BIGINT NOT NULL REFERENCES organizations(id),
    
    -- What milestone was entered
    milestone_type VARCHAR(50) NOT NULL,
    
    -- When it started and (optionally) ended
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    
    -- SLA tracking
    target_deadline TIMESTAMPTZ,          -- When this milestone SHOULD be done
    sla_target_days INTEGER,              -- Business days allowed
    actual_days INTEGER,                  -- Business days it actually took
    sla_status VARCHAR(20) DEFAULT 'IN_PROGRESS',  -- IN_PROGRESS, ON_TRACK, APPROACHING, OVERDUE, COMPLETED, MISSED
    
    -- Who/what triggered this change
    triggered_by VARCHAR(50),             -- 'user', 'system', 'ai', 'email_reconciliation', 'api_sync'
    triggered_by_user_id BIGINT REFERENCES users(id),
    trigger_notes TEXT,                   -- Optional context
    
    -- Previous milestone (for audit trail)
    previous_milestone_type VARCHAR(50),
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    CONSTRAINT valid_sla_status CHECK (sla_status IN (
        'IN_PROGRESS', 'ON_TRACK', 'APPROACHING', 'OVERDUE', 'COMPLETED', 'MISSED'
    ))
);

CREATE INDEX idx_milestone_history_loan ON loan_milestone_history(loan_id, started_at DESC);
CREATE INDEX idx_milestone_history_type ON loan_milestone_history(milestone_type, sla_status);
CREATE INDEX idx_milestone_history_org ON loan_milestone_history(organization_id, milestone_type);
```

---

## Milestone-to-Date Field Mapping

This is the critical mapping the workflow engine uses to know WHICH date field to read
for WHICH milestone.

```python
# =====================================================
# MILESTONE → DATE FIELD MAPPING
# The workflow engine uses this to find the start date
# for calculating days_elapsed in the current milestone
# =====================================================

MILESTONE_TO_DATE_FIELD = {
    # Lead Stage Milestones
    "NEW_LEAD":              "new_lead_date",
    "ATTEMPTED_CONTACT":     "attempted_contact_date",
    "PRE_QUAL":              "pre_qual_date",
    "PRE_APPROVAL":          "pre_approval_date",
    
    # Active Loan Stage Milestones
    "APPLICATION_RECEIVED":  "application_received_date",
    "DISCLOSED":             "disclosed_date",
    "IN_PROCESSING":         "processing_date",
    "UW_SUBMISSION":         "uw_submission_date",
    "CONDITIONAL_APPROVAL":  "conditional_approval_date",
    "CLEAR_TO_CLOSE":        "clear_to_close_date",
    "CLOSING_SCHEDULED":     "closing_scheduled_date",
    "FUNDED":                "funded_date",
    
    # Special Milestones
    "SUSPENDED":             "suspended_date",
    "MUM":                   "mum_date",
    
    # Sub-milestones (tracked but don't drive primary workflow)
    "CREDIT_PULLED":         "credit_pulled_date",
    "APPRAISAL_ORDERED":     "appraisal_ordered_date",
    "APPRAISAL_RECEIVED":    "appraisal_received_date",
    "TITLE_ORDERED":         "title_ordered_date",
    "TITLE_RECEIVED":        "title_received_date",
    "CONDITIONS_SENT":       "conditions_sent_date",
    "CONDITIONS_RECEIVED":   "conditions_received_date",
    "RESUBMISSION":          "resubmission_date",
    "CD_SENT":               "closing_disclosure_sent_date",
}

def get_milestone_start_date(entity, milestone_status: str) -> Optional[datetime]:
    """
    Get the date a loan/lead entered the given milestone.
    This is THE function the workflow engine calls to calculate days_elapsed.
    
    Returns None if the date field is not populated — this means
    the milestone was never properly entered and NO tasks can be generated.
    """
    date_field = MILESTONE_TO_DATE_FIELD.get(milestone_status)
    
    if not date_field:
        logger.warning(f"No date field mapping for milestone: {milestone_status}")
        return None
    
    date_value = getattr(entity, date_field, None)
    
    if date_value is None:
        logger.warning(
            f"Milestone date field '{date_field}' is NULL for "
            f"entity {entity.id} in milestone {milestone_status}. "
            f"No tasks will be generated until this date is populated."
        )
        return None
    
    return date_value
```

---

## The MilestoneService — ONLY Way to Write Dates

**Every milestone change MUST go through this service.** No direct column updates.
This ensures dates are always stamped, history is always recorded, and workflows are always triggered.

```python
class MilestoneService:
    """
    SINGLE ENTRY POINT for all milestone changes.
    
    If ANY code path changes a milestone without going through this service,
    the Important Dates will be wrong, workflows won't activate, and tasks
    won't be generated. This is the #1 cause of "nothing is working" bugs.
    
    Call sites that MUST use this service:
    - Manual status update by user (UI)
    - Online application received (auto-detection)
    - Email reconciliation (AI parsed milestone from email)
    - LOS sync (BytePro/Encompass pushes milestone update)
    - AI auto-complete (95%+ confidence task completion that advances milestone)
    - Bulk status update (admin tool)
    """
    
    def __init__(self, db, workflow_engine, sla_tracker):
        self.db = db
        self.workflow_engine = workflow_engine
        self.sla_tracker = sla_tracker
    
    def change_milestone(
        self,
        entity,                    # Loan or Lead
        new_milestone: str,        # e.g., "IN_PROCESSING"
        triggered_by: str,         # 'user', 'system', 'ai', 'email_reconciliation', 'api_sync'
        triggered_by_user_id: int = None,
        notes: str = None
    ):
        """
        Change an entity's milestone. This method:
        1. Stamps the date in the Important Dates field
        2. Updates current_milestone_status + current_milestone_entered_at
        3. Records in loan_milestone_history
        4. Completes the previous milestone's history record
        5. Cancels previous workflow's pending tasks
        6. Activates new workflow for the new milestone
        7. Recalculates SLA status
        """
        now = datetime.now(get_company_timezone(entity.organization_id))
        old_milestone = entity.current_milestone_status
        
        with self.db.begin():
            # ── Step 1: Stamp the Important Dates field ──
            date_field = MILESTONE_TO_DATE_FIELD.get(new_milestone)
            if date_field:
                setattr(entity, date_field, now)
            
            # ── Step 2: Update current state ──
            entity.current_milestone_status = new_milestone
            entity.current_milestone_entered_at = now
            
            # ── Step 3: Record in milestone history ──
            sla_config = self.sla_tracker.get_sla_config(
                entity.organization_id,
                entity.assigned_lo_id,  # User-level SLA if exists
                new_milestone
            )
            
            history = LoanMilestoneHistory(
                loan_id=entity.id if isinstance(entity, Loan) else None,
                lead_id=entity.id if isinstance(entity, Lead) else None,
                organization_id=entity.organization_id,
                milestone_type=new_milestone,
                started_at=now,
                target_deadline=self.sla_tracker.calculate_deadline(
                    now, sla_config.target_days
                ) if sla_config else None,
                sla_target_days=sla_config.target_days if sla_config else None,
                sla_status="IN_PROGRESS",
                triggered_by=triggered_by,
                triggered_by_user_id=triggered_by_user_id,
                trigger_notes=notes,
                previous_milestone_type=old_milestone
            )
            self.db.add(history)
            
            # ── Step 4: Complete previous milestone's history ──
            if old_milestone:
                prev_history = self.db.query(LoanMilestoneHistory).filter(
                    LoanMilestoneHistory.loan_id == entity.id,
                    LoanMilestoneHistory.milestone_type == old_milestone,
                    LoanMilestoneHistory.completed_at.is_(None)
                ).first()
                
                if prev_history:
                    prev_history.completed_at = now
                    prev_history.actual_days = business_days_between(
                        prev_history.started_at, now
                    )
                    prev_history.sla_status = (
                        "COMPLETED" if prev_history.actual_days <= (prev_history.sla_target_days or 999)
                        else "MISSED"
                    )
            
            # ── Step 5: Cancel previous workflow tasks ──
            self.workflow_engine.cancel_active_workflows(entity)
            
            # ── Step 6: Activate new workflow ──
            self.workflow_engine.activate_workflow_for_milestone(entity, new_milestone)
            
            # ── Step 7: Recalculate SLA ──
            self.sla_tracker.recalculate(entity)
            
            self.db.commit()
        
        logger.info(
            f"Milestone changed: {entity.__class__.__name__} {entity.id} "
            f"from {old_milestone} → {new_milestone} "
            f"(triggered by: {triggered_by})"
        )
```

---

## Important Dates Display — Client Profile Tab

The frontend reads these fields to render the Important Dates tab:

```typescript
// Frontend: ImportantDatesTab.tsx
interface ImportantDates {
  // Lead Stage
  new_lead_date: string | null;
  attempted_contact_date: string | null;
  pre_qual_date: string | null;
  pre_approval_date: string | null;
  
  // Active Loan Stage
  application_received_date: string | null;
  credit_pulled_date: string | null;
  disclosed_date: string | null;
  processing_date: string | null;
  appraisal_ordered_date: string | null;
  appraisal_received_date: string | null;
  title_ordered_date: string | null;
  title_received_date: string | null;
  uw_submission_date: string | null;
  conditional_approval_date: string | null;
  conditions_sent_date: string | null;
  conditions_received_date: string | null;
  resubmission_date: string | null;
  clear_to_close_date: string | null;
  closing_disclosure_sent_date: string | null;
  closing_scheduled_date: string | null;
  funded_date: string | null;
  
  // Special
  suspended_date: string | null;
  mum_date: string | null;
  
  // Current state
  current_milestone_status: string;
  current_milestone_entered_at: string;
}
```

---

## What Populates These Dates

| Source | How It Works | Date Fields Updated |
|--------|-------------|-------------------|
| **User manually changes status** | UI dropdown → API call → MilestoneService | The date for the new milestone |
| **Online application received** | Webhook → duplicate check → MilestoneService | `application_received_date` |
| **LOS sync (BytePro)** | Scheduled sync → field mapping → MilestoneService | Any milestone dates present in LOS data |
| **Email reconciliation** | AI parses email → confidence check → MilestoneService | Milestone detected in email |
| **AI auto-complete** | Task completion at 95%+ confidence → MilestoneService | If task completion advances milestone |
| **Close on Time widget** | Contract received → MilestoneService | `clear_to_close_date`, closing dates |
| **Document upload** | Specific doc types trigger milestone detection | Sub-milestones (appraisal, title, etc.) |

---

## Common Failure Points

1. **Date field is NULL** → Workflow engine can't calculate days → No tasks generated
2. **Milestone changed without using MilestoneService** → Date not stamped, history not recorded
3. **LOS sync overwrites dates** → Sync should only UPDATE dates, never clear them
4. **Timezone mismatch** → Date stored in UTC but displayed/calculated in wrong timezone
5. **Lead vs Loan confusion** → Lead converts to loan but Important Dates don't carry over
