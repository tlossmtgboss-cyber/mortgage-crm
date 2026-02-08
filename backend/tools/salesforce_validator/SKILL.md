---
name: salesforce-integration-validator
description: >
  Validates Salesforce CRM integration for Perennia AI, ensuring all data pushes
  are complete and accurate. Focuses on field mapping verification, custom byte
  mapping validation (date tracking updates), SLA milestone synchronization, and
  end-to-end data integrity between source systems and Salesforce CRM client pages.
  Use when auditing integrations, debugging sync failures, onboarding new field
  mappings, or verifying SLA-driven workflow triggers.
---

# Salesforce Integration Validator

## Purpose

This skill validates that data flowing from Perennia AI into Salesforce CRM is:

1. **Complete** — Every expected field is pushed; nothing is silently dropped
2. **Accurate** — Source values match destination values after transformation
3. **Timely** — SLA date milestones arrive before workflow deadlines
4. **Mapped correctly** — Custom byte mappings (date tracking) land on the correct CRM client page fields
5. **Workflow-ready** — SLA dates that drive task generation are present, correctly formatted, and actionable

---

## When to Use This Skill

- Auditing an existing Salesforce integration for data integrity
- Debugging why workflows or tasks aren't firing (usually missing/malformed SLA dates)
- Onboarding new field mappings or custom objects
- Validating after a deployment that touches sync logic
- Periodic health checks on integration reliability
- Investigating discrepancies between Perennia AI and Salesforce records

---

## Core Concepts

### Custom Byte Mappings (Date Tracking Updates)

Custom byte mappings are the mechanism by which date-based milestone events in Perennia AI
are serialized and pushed to Salesforce custom fields. These are **the most critical data
points in the integration** because they:

- Populate the CRM client page timeline
- Drive SLA countdown calculations
- Trigger automated workflow task creation
- Feed compliance reporting and audit trails

A "byte mapping" in this context refers to the compact field-level encoding used to
track date state changes (e.g., `application_received_date`, `disclosure_sent_date`,
`appraisal_ordered_date`, `clear_to_close_date`) that get mapped to corresponding
Salesforce custom fields (typically `__c` suffixed fields on the Opportunity or
custom Loan object).

### SLA Date Milestones

SLA milestones are date fields on the client profile that define expected completion
windows for mortgage workflow stages. When these dates are pushed to Salesforce:

- **Workflow rules** fire to create tasks for loan officers and processors
- **Escalation rules** trigger when dates pass without completion
- **Dashboard rollups** calculate pipeline health metrics
- **Compliance checks** validate regulatory timing requirements

If an SLA date is missing, malformed, or mapped to the wrong field, the entire
downstream workflow chain breaks silently.

---

## Validation Process

### Step 1: Inventory Field Mappings

Before validating data, build a complete inventory of all field mappings.

```
Run: scripts/inventory_field_mappings.py
```

This script produces a mapping manifest (`field_mapping_manifest.json`) that documents:

| Property | Description |
|----------|-------------|
| `source_system` | Origin system (e.g., `perennia_ai`) |
| `source_field` | Field name in source (e.g., `loan.appraisal_ordered_at`) |
| `source_type` | Data type in source (e.g., `datetime`, `string`, `decimal`) |
| `sf_object` | Salesforce object (e.g., `Opportunity`, `Loan__c`, `Contact`) |
| `sf_field` | Salesforce field API name (e.g., `Appraisal_Ordered_Date__c`) |
| `sf_type` | Salesforce field type (e.g., `Date`, `DateTime`, `Text`) |
| `transform` | Any transformation applied (e.g., `utc_to_local`, `cents_to_dollars`) |
| `is_sla_field` | Boolean — does this field drive SLA/workflow logic |
| `is_byte_mapped` | Boolean — is this a custom byte mapping (date tracking) |
| `required` | Boolean — must this field always be present |
| `sync_direction` | `push`, `pull`, or `bidirectional` |

### Step 2: Validate Field Existence in Salesforce

Confirm every mapped field actually exists on the target Salesforce object.

```
Run: scripts/validate_sf_schema.py
```

**Checks performed:**
- Field API name exists on the specified object
- Field type matches expected type (e.g., don't push DateTime to a Text field)
- Field is writable (not a formula or system field being written to)
- Field-level security allows the integration user to write
- Custom fields haven't been deleted or renamed

**Failure modes to catch:**
- Field was renamed in Salesforce but mapping config wasn't updated
- Field was deleted during a Salesforce admin cleanup
- Field type was changed (e.g., Text → Picklist)
- Integration user lost write permission after a profile change

### Step 3: Validate Data Push Completeness

For a sample set of records, verify every mapped field was actually pushed.

```
Run: scripts/validate_data_push.py --sample-size 50 --days-back 7
```

**For each record, check:**
- Every required field has a non-null value in Salesforce
- Every SLA date field is populated when the source has a value
- Custom byte mappings are present and decoded correctly
- No orphaned records (pushed to SF but missing in source, or vice versa)
- Timestamps are within acceptable sync latency window

**Output:** `push_completeness_report.json`

```json
{
  "total_records_checked": 50,
  "fully_synced": 47,
  "partial_sync": 2,
  "failed_sync": 1,
  "field_level_results": {
    "Application_Received_Date__c": {
      "expected": 50,
      "present": 50,
      "missing": 0,
      "mismatched": 0,
      "status": "PASS"
    },
    "Clear_To_Close_Date__c": {
      "expected": 12,
      "present": 11,
      "missing": 1,
      "mismatched": 0,
      "status": "FAIL"
    }
  },
  "sla_fields_summary": {
    "total_sla_fields": 14,
    "all_passing": 12,
    "with_issues": 2
  }
}
```

### Step 4: Validate Custom Byte Mapping Accuracy

The most critical validation — ensure date tracking byte mappings are accurate.

```
Run: scripts/validate_byte_mappings.py --strict
```

**For each byte-mapped date field:**

1. **Read source value** from Perennia AI database
2. **Decode byte mapping** to get the expected Salesforce value
3. **Read destination value** from Salesforce
4. **Compare** with tolerance for timezone/format differences
5. **Verify CRM client page** displays the correct date

**Specific checks:**
- Byte encoding/decoding produces the correct date
- Timezone conversions are applied consistently (UTC → user's timezone)
- Date format matches Salesforce field type (Date vs DateTime)
- Null handling: source null → SF null (not epoch zero or placeholder dates)
- Update propagation: when source date changes, SF field updates within SLA window
- Historical accuracy: past date changes are logged, not silently overwritten

**Output:** `byte_mapping_validation_report.json`

```json
{
  "validation_timestamp": "2026-02-08T14:30:00Z",
  "total_byte_mapped_fields": 18,
  "fields_validated": [
    {
      "source_field": "loan.disclosure_sent_at",
      "sf_field": "Disclosure_Sent_Date__c",
      "sf_object": "Loan__c",
      "records_checked": 50,
      "exact_match": 48,
      "timezone_adjusted_match": 1,
      "mismatch": 1,
      "null_handling_correct": true,
      "update_propagation_verified": true,
      "status": "WARNING",
      "issues": [
        {
          "record_id": "a]0XX000001abcd",
          "source_value": "2026-01-15T09:30:00Z",
          "sf_value": "2026-01-14",
          "issue": "Date shifted by timezone conversion — UTC to EST not applied"
        }
      ]
    }
  ]
}
```

### Step 5: Validate SLA Milestone → Workflow Chain

Verify that SLA dates in Salesforce actually trigger the expected workflows.

```
Run: scripts/validate_sla_workflows.py
```

**For each SLA milestone field:**

1. Confirm the field is referenced in Salesforce Workflow Rules or Flows
2. Verify the workflow creates the expected Task record
3. Check Task assignment rules route to the correct user/queue
4. Validate escalation timing matches SLA configuration
5. Confirm task due dates are calculated correctly from the milestone date

**Validation matrix:**

| SLA Milestone | Expected Workflow | Task Created | Assigned To | Due Date Calc | Status |
|---------------|-------------------|-------------|-------------|---------------|--------|
| Application Received | Initial Review | ✅ | Processor Queue | +1 business day | PASS |
| Disclosure Sent | Compliance Check | ✅ | Compliance Team | +3 business days | PASS |
| Appraisal Ordered | Appraisal Follow-up | ❌ | — | — | FAIL |
| Clear to Close | Closing Prep | ✅ | Closer Queue | +2 business days | PASS |

### Step 6: Generate Reconciliation Report

Produce a comprehensive reconciliation report combining all validation results.

```
Run: scripts/generate_reconciliation_report.py
```

**Report sections:**
1. **Executive Summary** — Overall health score, critical issues count
2. **Field Mapping Inventory** — Complete mapping table with status
3. **Push Completeness** — Record-level sync results
4. **Byte Mapping Accuracy** — Date tracking validation details
5. **SLA Workflow Chain** — Milestone → Task generation verification
6. **Recommendations** — Prioritized fix list
7. **Trend Analysis** — Comparison with previous validation runs

---

## Critical Field Mapping Reference

These are the SLA date milestone fields that MUST be validated every run because
they directly drive workflow task creation:

### Loan Origination SLA Dates

| Source Field (Perennia AI) | SF Field (Loan__c) | SLA Window | Workflow Trigger |
|---------------------------|---------------------|------------|-----------------|
| `loan.application_received_at` | `Application_Received_Date__c` | T+0 | Initial doc review task |
| `loan.disclosure_sent_at` | `Disclosure_Sent_Date__c` | T+3 days | TRID compliance check |
| `loan.disclosure_acknowledged_at` | `Disclosure_Ack_Date__c` | T+10 days | Escalation if unsigned |
| `loan.appraisal_ordered_at` | `Appraisal_Ordered_Date__c` | T+1 day | Appraisal follow-up task |
| `loan.appraisal_received_at` | `Appraisal_Received_Date__c` | T+0 | Appraisal review task |
| `loan.title_ordered_at` | `Title_Ordered_Date__c` | T+1 day | Title follow-up task |
| `loan.title_received_at` | `Title_Received_Date__c` | T+0 | Title review task |
| `loan.conditions_sent_at` | `Conditions_Sent_Date__c` | T+3 days | Condition follow-up |
| `loan.conditions_cleared_at` | `Conditions_Cleared_Date__c` | T+0 | Clear to close prep |
| `loan.clear_to_close_at` | `Clear_To_Close_Date__c` | T+0 | Closing package task |
| `loan.closing_scheduled_at` | `Closing_Scheduled_Date__c` | T-1 day | Pre-closing verification |
| `loan.funded_at` | `Funded_Date__c` | T+0 | Post-closing audit task |
| `loan.docs_out_at` | `Docs_Out_Date__c` | T+0 | Doc tracking confirmation |
| `loan.submitted_to_uw_at` | `Submitted_To_UW_Date__c` | T+2 days | UW follow-up task |

### Contact/Borrower SLA Dates

| Source Field (Perennia AI) | SF Field (Contact) | SLA Window | Workflow Trigger |
|---------------------------|---------------------|------------|-----------------|
| `borrower.last_contact_at` | `Last_Contact_Date__c` | T+7 days | Re-engagement task |
| `borrower.next_followup_at` | `Next_Followup_Date__c` | T+0 | Follow-up reminder task |
| `borrower.preapproval_expires_at` | `Preapproval_Expiry__c` | T-14 days | Renewal outreach task |
| `borrower.rate_lock_expires_at` | `Rate_Lock_Expiry__c` | T-7 days | Rate lock extension task |

---

## Error Taxonomy

Common failure modes ranked by severity:

### Critical (Breaks workflows)
- **MISSING_SLA_DATE**: SLA field is null in SF when source has a value → tasks never created
- **WRONG_FIELD_MAPPING**: Date pushed to wrong SF field → wrong workflow fires
- **BYTE_DECODE_ERROR**: Byte mapping produces garbage date → unpredictable behavior
- **TYPE_MISMATCH**: DateTime pushed to Date field truncates time component

### High (Data integrity)
- **TIMEZONE_SHIFT**: Date off by 1 day due to UTC conversion → SLA miscalculated
- **STALE_DATA**: SF value doesn't reflect recent source update → outdated tasks
- **NULL_PLACEHOLDER**: Null date stored as 1970-01-01 or 9999-12-31 → false workflow triggers
- **DUPLICATE_PUSH**: Same record pushed multiple times → duplicate tasks

### Medium (Reporting/compliance)
- **FORMAT_MISMATCH**: Date format inconsistency → dashboard display errors
- **MISSING_OPTIONAL**: Non-required field not synced → incomplete client profile
- **PERMISSION_ERROR**: Field exists but integration user can't write → silent failure

### Low (Cosmetic)
- **DISPLAY_FORMAT**: Date displays differently on CRM page vs source
- **SORT_ORDER**: Multiple date fields display in unexpected order on layout

---

## Configuration

### Environment Variables

```env
# Salesforce Connection
SF_INSTANCE_URL=https://yourorg.my.salesforce.com
SF_CLIENT_ID=your_connected_app_client_id
SF_CLIENT_SECRET=your_connected_app_client_secret
SF_USERNAME=integration_user@yourorg.com
SF_PASSWORD=integration_user_password
SF_SECURITY_TOKEN=your_security_token
SF_API_VERSION=v59.0

# Perennia AI Database
PERENNIA_DB_URL=postgresql://user:pass@host:5432/perennia
PERENNIA_API_URL=https://api.perennia.ai
PERENNIA_API_KEY=your_api_key

# Validation Settings
VALIDATION_SAMPLE_SIZE=50
VALIDATION_DAYS_BACK=7
SYNC_LATENCY_TOLERANCE_SECONDS=300
DATE_COMPARISON_TOLERANCE_HOURS=24
STRICT_BYTE_MAPPING_MODE=true

# Reporting
REPORT_OUTPUT_DIR=./reports
REPORT_FORMAT=json,html
ALERT_ON_CRITICAL=true
ALERT_WEBHOOK_URL=https://hooks.slack.com/your-webhook
```

### Field Mapping Configuration File

Create `config/field_mappings.yaml`:

```yaml
mappings:
  - source:
      system: perennia_ai
      object: loan
      field: application_received_at
      type: datetime
    destination:
      object: Loan__c
      field: Application_Received_Date__c
      type: Date
    transform: utc_to_date_only
    is_sla_field: true
    is_byte_mapped: true
    required: true
    sla_config:
      window_days: 0
      workflow_name: Initial_Doc_Review
      task_type: Document Review
      assigned_to: Processor_Queue

  # Add all field mappings following this pattern
  # See templates/field_mapping_template.yaml for full template
```

---

## Running the Full Validation Suite

### Quick Health Check (5 minutes)
```bash
python scripts/run_validation.py --mode quick
# Checks: field existence, sample push (10 records), critical SLA fields only
```

### Standard Validation (15-30 minutes)
```bash
python scripts/run_validation.py --mode standard
# Checks: all fields, 50 record sample, byte mappings, SLA workflows
```

### Full Audit (1-2 hours)
```bash
python scripts/run_validation.py --mode full --sample-size 500
# Checks: everything above + historical comparison, trend analysis, all records in window
```

### Targeted Byte Mapping Check
```bash
python scripts/validate_byte_mappings.py --fields "Disclosure_Sent_Date__c,Clear_To_Close_Date__c" --strict
# Validates specific byte-mapped fields only
```

### Post-Deployment Verification
```bash
python scripts/run_validation.py --mode post-deploy --compare-previous
# Runs standard checks + compares against last validation baseline
```

---

## Interpreting Results

### Health Score Calculation

```
Health Score = (
  (critical_fields_passing / total_critical_fields) * 0.50 +
  (sla_fields_passing / total_sla_fields) * 0.30 +
  (all_fields_passing / total_fields) * 0.15 +
  (workflow_chain_intact / total_workflows) * 0.05
) * 100
```

| Score | Status | Action |
|-------|--------|--------|
| 95-100 | ✅ Healthy | Routine monitoring |
| 85-94 | ⚠️ Warning | Investigate within 24 hours |
| 70-84 | 🔶 Degraded | Fix within 4 hours |
| <70 | 🔴 Critical | Immediate intervention required |

### Reading the Reconciliation Report

The report highlights discrepancies in priority order:

1. **Red items**: SLA dates missing or wrong → workflows broken
2. **Orange items**: Byte mapping decode errors → data corruption risk
3. **Yellow items**: Non-SLA fields out of sync → incomplete profiles
4. **Blue items**: Informational — format differences, optional fields

---

## Automation & Scheduling

### Recommended Schedule

| Validation Type | Frequency | Trigger |
|----------------|-----------|---------|
| Quick Health Check | Every 4 hours | Cron job |
| Standard Validation | Daily at 6 AM | Scheduled pipeline |
| Full Audit | Weekly (Sunday) | Scheduled pipeline |
| Post-Deploy Check | After every deployment | CI/CD hook |
| Targeted Byte Mapping | On demand | Manual or alert-triggered |

### Alert Configuration

Configure alerts in `config/alerts.yaml`:

```yaml
alerts:
  critical:
    channels: [slack, email, pagerduty]
    conditions:
      - any_sla_field_missing
      - byte_mapping_decode_failure
      - health_score_below_70
    escalation_minutes: 15

  warning:
    channels: [slack]
    conditions:
      - health_score_below_85
      - sync_latency_exceeded
      - optional_field_missing_rate_above_10pct
    escalation_minutes: 60
```

---

## Troubleshooting Common Issues

### SLA Tasks Not Generating

1. Run `validate_byte_mappings.py --strict` for the specific SLA field
2. Check if the date is null in Salesforce (most common cause)
3. Verify the Salesforce Workflow Rule/Flow is active
4. Check if the integration user has permission to trigger workflows
5. Look for byte decode errors in the sync logs

### Date Off By One Day

1. Check timezone configuration: source stores UTC, SF expects local
2. Verify `utc_to_date_only` transform is applied for Date (not DateTime) fields
3. Check if the byte mapping preserves timezone offset
4. Compare raw byte value against decoded date

### Duplicate Tasks Being Created

1. Check if records are being pushed multiple times (dedup check)
2. Verify upsert key is configured correctly (External ID field)
3. Check if workflow rule has "re-evaluate after field change" enabled
4. Look for retry storms in the sync queue

### Fields Silently Not Syncing

1. Run `validate_sf_schema.py` to check field existence and permissions
2. Check Salesforce Setup → Debug Logs for the integration user
3. Verify field-level security on the integration user's profile
4. Check if a Salesforce validation rule is rejecting the value
5. Look for API errors in the Perennia sync logs

---

## Integration with Perennia AI Agent System

This validation skill can be invoked by Perennia AI's agent governance system:

- **Monitoring Agent**: Runs quick health checks on schedule
- **Compliance Agent**: Triggers full audit for regulatory reporting
- **Incident Agent**: Runs targeted validation when sync errors detected
- **Deployment Agent**: Runs post-deploy checks after releases

The validation results feed back into the agent governance dashboard for
real-time integration health visibility.
