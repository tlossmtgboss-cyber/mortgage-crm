# Smart Docs V2 Configuration Guide

System administrator reference for configuring Smart Docs V2 across organizations.

API prefix: `/api/smart-docs`
Config endpoints: `/api/smart-docs/config/rules`

---

## 1. Initial Setup

### Enabling Smart Docs for an Organization

Smart Docs V2 routes are registered at startup via `register_smart_docs_v2_routes(app)` in `main.py`. Database tables are created automatically by the migration runner during registration. No per-org feature toggle exists at the route level -- all organizations with active accounts have access.

To seed default business rules for a new organization:

```
POST /api/smart-docs/config/rules/seed-defaults
Authorization: Bearer <admin_token>
```

This creates DB rows for all rules defined in `RULE_DEFAULTS` (see `services/smart_docs/business_rules_service.py`). Rules that already exist are skipped.

### Default Configuration Values

All business rules have hardcoded fallback values in `RULE_DEFAULTS`. The lookup precedence is:

1. Org-specific active rule matching the current date
2. System default (org_id IS NULL) active rule matching the current date
3. Hardcoded fallback from `RULE_DEFAULTS`

Values are cached in-memory with a 5-minute TTL. Cache is invalidated automatically on rule updates.

### Required vs Optional Configuration

**Required before first use:**
- Seed default business rules (POST to `/config/rules/seed-defaults`)
- Configure S3 storage bucket (env var `SMART_DOCS_S3_BUCKET`)
- Set `SMART_DOCS_ENCRYPTION_KEY` for PII encryption

**Optional (defaults are production-ready):**
- All business rule overrides (income, fraud, document freshness thresholds)
- Follow-up campaign cadence customization
- E-signature reminder frequency
- Retention policy overrides
- White-label branding

---

## 2. Document Types Configuration

### Adding Custom Document Types

Document types are defined in the `DocType` enum in `models/smart_docs_models.py`:

| DocType Enum Value | Description |
|---|---|
| `DRIVERS_LICENSE` | Government-issued photo ID |
| `PAYSTUB` | Recent pay stubs |
| `W2` | W-2 wage and tax statement |
| `TAX_RETURN` | Personal federal tax return |
| `BUSINESS_TAX_RETURN` | Business tax return (Schedule C, 1120, 1065) |
| `PROFIT_LOSS` | Year-to-date P&L statement |
| `BALANCE_SHEET` | Business balance sheet |
| `BANK_STATEMENT` | Personal or business bank statement |
| `INVESTMENT_STATEMENT` | Investment/retirement account statement |
| `GIFT_LETTER` | Gift funds letter with donor info |
| `LOE` | Letter of Explanation |
| `LEASE_AGREEMENT` | Rental/lease agreement |
| `FHA_CERT` | FHA certification |
| `VA_COE` | VA Certificate of Eligibility |
| `DD214` | DD-214 military discharge |
| `BANKRUPTCY_DISCHARGE` | Bankruptcy discharge paperwork |
| `PURCHASE_CONTRACT` | Purchase agreement |
| `APPRAISAL` | Property appraisal report |
| `TITLE_REPORT` | Title search/commitment |
| `HOMEOWNERS_INSURANCE` | Homeowner's insurance binder |
| `OTHER` | Catch-all for unlisted types |

Custom types beyond this enum require a code deployment. The `OTHER` type can be used with the `display_name` field on `SmartDocument` to label ad-hoc documents.

### Mapping Document Types to Categories

Frontend document IDs are mapped to backend `DocType` values in `routes/smart_docs_models.py` via the `DOCUMENT_ID_TO_DOC_TYPE` dict. Key mappings:

```python
# Identity
'id' -> DRIVERS_LICENSE
'va_coe' -> VA_COE

# Income
'paystubs' -> PAYSTUB
'w2_recent' -> W2
'tax_returns' -> TAX_RETURN
'business_tax_returns' -> BUSINESS_TAX_RETURN
'profit_loss' -> PROFIT_LOSS

# Assets
'bank_statements' -> BANK_STATEMENT
'investment_statements' -> INVESTMENT_STATEMENT
'gift_letter' -> GIFT_LETTER
```

Co-borrower variants (`coborrower_paystubs`, `coborrower_w2_recent`, etc.) map to the same `DocType` -- the `applies_to` field on `DocumentRequest` distinguishes BORROWER vs CO_BORROWER.

### Setting Freshness Requirements Per Type

Freshness is configured in two places:

**1. Hardcoded defaults** (`routes/smart_docs_models.py` -- `FRESHNESS_DAYS` dict):

| DocType | Default Freshness (days) |
|---|---|
| `PAYSTUB` | 30 |
| `BANK_STATEMENT` | 60 |
| `INVESTMENT_STATEMENT` | 90 |
| `W2` | 365 |
| `TAX_RETURN` | 365 |
| `BUSINESS_TAX_RETURN` | 365 |

**2. Business rules (overridable per org via API):**

| Rule Key | Default | Source | Description |
|---|---|---|---|
| `freshness_paystub` | 30 | fannie_mae | Max age in days for paystubs |
| `freshness_bank_statement` | 60 | fannie_mae | Max age in days for bank statements |
| `freshness_w2` | 365 | fannie_mae | Max age in days for W-2 forms |
| `freshness_tax_return` | 365 | fannie_mae | Max age in days for tax returns |

To override for an org:

```
PUT /api/smart-docs/config/rules/freshness_paystub
{
  "value": 45,
  "source": "internal_policy",
  "description": "Extended paystub freshness for this org"
}
```

### Configuring Document Type Display Names

Each `SmartDocument` has a `display_name` column (String 255) that can be set via:

```
PUT /api/smart-docs/documents/{document_id}/name
{
  "display_name": "Q4 2025 Bank Statement - Chase"
}
```

If `display_name` is null, the system falls back to `file_name`.

### Required Documents Per Loan Program

Needs list templates define required documents per loan program. Templates are stored in the `needs_list_templates` table with JSON configuration.

**NeedsListTemplate columns:**

| Field | Type | Description |
|---|---|---|
| `name` | String(255) | Template display name |
| `slug` | String(128) | URL-safe identifier |
| `loan_programs` | JSON | Array: `["CONVENTIONAL", "FHA", "VA", "USDA"]` |
| `occupancy_types` | JSON | Array: `["PRIMARY", "SECOND_HOME", "INVESTMENT"]` |
| `income_types` | JSON | Array: `["W2", "SELF_EMPLOYED", "RETIREMENT"]` |
| `request_templates` | JSON | Array of request template objects |
| `is_active` | Boolean | Whether template is active |

**Example template configuration:**

```json
{
  "name": "FHA Purchase - W2 Employee",
  "slug": "fha-purchase-w2",
  "loan_programs": ["FHA"],
  "occupancy_types": ["PRIMARY"],
  "income_types": ["W2"],
  "request_templates": [
    {
      "doc_type": "DRIVERS_LICENSE",
      "title": "Government-Issued Photo ID",
      "priority": "CRITICAL",
      "required_count": 1,
      "applies_to": "BOTH",
      "freshness_days": null
    },
    {
      "doc_type": "PAYSTUB",
      "title": "Most Recent Paystubs (30 days)",
      "priority": "HIGH",
      "required_count": 2,
      "applies_to": "BORROWER",
      "freshness_days": 30,
      "auto_renew": true
    },
    {
      "doc_type": "W2",
      "title": "W-2 Forms (2 most recent years)",
      "priority": "HIGH",
      "required_count": 2,
      "applies_to": "BORROWER",
      "freshness_days": 365
    },
    {
      "doc_type": "BANK_STATEMENT",
      "title": "Bank Statements (2 months)",
      "priority": "HIGH",
      "required_count": 2,
      "applies_to": "BORROWER",
      "freshness_days": 60
    },
    {
      "doc_type": "FHA_CERT",
      "title": "FHA Case Number Assignment",
      "priority": "NORMAL",
      "required_count": 1,
      "applies_to": "BORROWER"
    }
  ]
}
```

Generate a needs list from a template:

```
POST /api/v1/smart-docs/needs-list/generate
{
  "loan_id": 12345,
  "loan_program": "FHA",
  "occupancy_type": "PRIMARY",
  "income_type": "W2",
  "borrower_id": 678,
  "co_borrower_id": 679,
  "has_gift_funds": true,
  "is_self_employed": false,
  "has_bankruptcy": false
}
```

**Common customization: Adding VA-specific documents**

Create a template with `loan_programs: ["VA"]` that includes `VA_COE` and `DD214` in addition to standard income/asset docs.

**Validation rules:**
- `slug` must be unique within the organization
- `request_templates` must be a valid JSON array
- Each template object must include `doc_type` and `title`
- `priority` must be one of: `CRITICAL`, `HIGH`, `NORMAL`, `LOW`
- `applies_to` must be one of: `BORROWER`, `CO_BORROWER`, `BOTH`

---

## 3. Income Calculation Configuration

### Business Rules for Income

All income thresholds are configurable via the business rules API:

| Rule Key | Type | Default | Source | Description |
|---|---|---|---|---|
| `ss_wage_base` | integer | 176100 | irs_2025 | Social Security wage base for the current tax year |
| `income_variance_tolerance_pct` | decimal | 5.0 | custom | Allowable variance (%) between stated and calculated income |
| `declining_income_threshold_pct` | decimal | 25.0 | fannie_mae | YoY income decline (%) that triggers UW review |

**Example: Update SS wage base for new tax year:**

```
PUT /api/smart-docs/config/rules/ss_wage_base
{
  "value": 180000,
  "effective_date": "2026-01-01",
  "source": "irs_2026",
  "description": "2026 Social Security wage base"
}
```

Time-versioned rules allow setting a future effective date so the old value remains active until the new one takes effect.

### Self-Employment Threshold Configuration

Self-employment income requires additional documentation. The needs list generator checks the `is_self_employed` flag on the `GenerateNeedsListRequest` and adds:

- Business tax returns (2 years)
- Year-to-date P&L statement
- Balance sheet
- Business bank statements

Configure the ownership threshold percentage via business rules by adding a custom rule.

### Commission Percentage Thresholds

Income sources with a high commission percentage (typically >25%) require additional averaging documentation. This is handled by the `IncomeCalculation` model's `calculation_type` field:

| CalculationType | Description |
|---|---|
| `BASE_SALARY` | Straightforward W2 salary |
| `HOURLY` | Hourly wage calculation |
| `COMMISSION` | Commission-heavy income |
| `SELF_EMPLOYMENT` | Schedule C / 1099 income |
| `RENTAL` | Rental property income |
| `RETIREMENT` | Social Security, pension |
| `OTHER` | Other income types |

### Declining Income Rules

The `declining_income_threshold_pct` rule (default: 25%) controls when year-over-year income decline triggers underwriting review. When the income calculator detects a decline exceeding this threshold:

1. A verification task is created with `TaskStatus.PENDING`
2. The calculation is flagged and requires manual review
3. The reviewer/approver cannot be the same person who calculated (maker-checker control)

### DTI Limits Per Loan Program

DTI validation uses `validate_dti()` from `validation/smart_docs_validators.py`. The validator enforces a range of 0-100. Program-specific DTI limits should be configured as business rules:

```
PUT /api/smart-docs/config/rules/dti_limit_conventional
{
  "value": 50.0,
  "source": "fannie_mae",
  "description": "Max DTI for conventional loans"
}
```

**Validation rules:**
- DTI value must be between 0 and 100 inclusive
- Both front-end and back-end ratios should be validated
- Loan amount must be positive and not exceed $50,000,000 (`validate_loan_amount()`)
- Percentages validated via `validate_percentage()` with configurable min/max

### Gross-Up Percentages for Non-Taxable Income

Non-taxable income (VA disability, Social Security, etc.) can be grossed up for qualifying. Configure via custom business rules:

```
PUT /api/smart-docs/config/rules/grossup_pct_nontaxable
{
  "value": 25.0,
  "source": "fannie_mae",
  "description": "Gross-up percentage for non-taxable income"
}
```

---

## 4. E-Signature Configuration

E-signature routes are mounted at `/api/v1/esign/*`. Models are in `database/models/esignature.py`.

### Signing Key Management

Signing uses SHA-256 document hashing for tamper detection. The `document_hash_sha256` column on `ESignatureEnvelope` stores the hash at creation time. Each audit event also captures `document_hash_at_event` for chain-of-custody verification.

The cryptographic service is in `services/smart_docs/esignature_crypto_service.py`. Set the signing key via environment variable:

| Env Var | Description |
|---|---|
| `ESIGN_SIGNING_KEY` | HMAC key for signing token generation |
| `ESIGN_ENCRYPTION_KEY` | AES key for access code encryption |

### Token Expiration Settings

| Setting | Location | Default | Description |
|---|---|---|---|
| `signing_token_expires_at` | `ESignatureRecipient` column | Set at envelope send time | When the signing URL expires |
| `expires_at` | `ESignatureEnvelope` column | Set at creation | When the entire envelope expires |
| `reminder_frequency_hours` | `ESignatureEnvelope` column | 48 | Hours between automated reminders |

Expired envelopes are automatically set to `EXPIRED` status by the `send_esignature_reminders` cron task (runs every 4 hours). Expired signing tokens are cleaned up by the `cleanup_smart_docs` task (daily at 3:00 AM).

### Access Code Requirements

Recipients can be configured with an optional access code for additional security:

```json
{
  "name": "John Smith",
  "email": "john@example.com",
  "recipient_type": "signer",
  "auth_method": "access_code",
  "access_code": "SECURE-PIN-2026"
}
```

| Auth Method | Description |
|---|---|
| `email_link` | Default. Signing URL sent via email. |
| `sms_code` | SMS verification code sent to phone on file. |
| `access_code` | Recipient must enter a pre-shared PIN before viewing. |
| `kba` | Knowledge-Based Authentication (identity proofing questions). |

The `access_code` column on `ESignatureRecipient` is String(128).

### KBA Thresholds

KBA sessions are tracked in the `esign_kba_sessions` table:

| Field | Type | Default | Description |
|---|---|---|---|
| `max_attempts` | Integer | 3 | Maximum KBA attempts before lockout |
| `attempts_used` | Integer | 0 | Current attempt count |
| `locked` | Boolean | false | Whether session is locked after failures |
| `passed` | Boolean | null | Outcome (null = not yet attempted) |

After `max_attempts` failed attempts, the session is locked and the recipient status is set to `AUTH_FAILED`. This is not configurable per-org via business rules -- it requires a code change to adjust the default.

### Consent Disclosure Customization

The ESIGN Act (15 U.S.C. 7001) requires affirmative consent before electronic signatures are legally binding. Consent is tracked in the `esign_consent_sessions` table:

| Field | Type | Description |
|---|---|---|
| `consent_given` | Boolean | Whether signer consented |
| `consent_text_version` | String(50) | Version of disclosure text shown |
| `consented_at` | DateTime | When consent was given |
| `withdrawn_at` | DateTime | When consent was withdrawn (if applicable) |
| `withdrawal_reason` | Text | Reason for withdrawal |

**Consent text versioning:** Update the version string when the disclosure text changes. The consent service (`services/smart_docs/esign_consent_service.py`) checks that active consent exists before allowing signature capture.

A consent row must exist with `consent_given = True` and `withdrawn_at IS NULL` before the signing endpoint accepts a signature.

### Signer Notification Templates

E-signature templates are stored in `esignature_templates` and support:

- Pre-configured field positions (`fields_config` JSON)
- Default recipient role slots (`default_recipients` JSON)
- Categories: `disclosure`, `loe`, `authorization`
- Per-org customization via `organization_id`

```json
{
  "name": "Standard LOE Template",
  "category": "loe",
  "fields_config": [
    {
      "field_type": "signature",
      "page_number": 1,
      "x": 100.0, "y": 500.0,
      "width": 200.0, "height": 50.0,
      "is_required": true,
      "recipient_role": "borrower"
    },
    {
      "field_type": "date_signed",
      "page_number": 1,
      "x": 350.0, "y": 500.0,
      "width": 100.0, "height": 30.0,
      "is_required": true,
      "recipient_role": "borrower"
    }
  ],
  "default_recipients": [
    {
      "role_label": "borrower",
      "recipient_type": "signer",
      "signing_order": 1
    },
    {
      "role_label": "loan_officer",
      "recipient_type": "cc",
      "signing_order": 1
    }
  ]
}
```

---

## 5. Follow-up & Communication Configuration

Models: `database/models/document_followup.py`
Routes: `routes/smart_docs_followup_routes.py`

### Default Cadence Sequences

Follow-up campaigns use a step-based configuration stored in the `step_config` JSON column on `FollowupCampaign`:

```json
[
  {"step": 1, "channel": "email", "delay_hours": 0, "template": "initial_request"},
  {"step": 2, "channel": "sms", "delay_hours": 48, "template": "gentle_reminder"},
  {"step": 3, "channel": "call", "delay_hours": 96, "template": "urgent_reminder"},
  {"step": 4, "channel": "email", "delay_hours": 168, "template": "escalation"},
  {"step": 5, "channel": "call", "delay_hours": 240, "template": "final_escalation"}
]
```

| Campaign Type | Description | Default Steps |
|---|---|---|
| `initial_request` | First request for documents | 3 |
| `gentle_reminder` | Soft follow-up | 3 |
| `urgent_reminder` | Time-sensitive follow-up | 3 |
| `escalation` | Escalated to loan officer | 2 |
| `appointment_offer` | Offer to schedule a call | 2 |

### Business Rules for Follow-up

| Rule Key | Type | Default | Description |
|---|---|---|---|
| `max_followup_emails_per_day` | integer | 3 | Max automated follow-up emails per borrower per day |
| `followup_escalation_day` | integer | 7 | Days without response before escalating to LO |

### Quiet Hours Settings

Quiet hours are enforced at the campaign processing level. The `process_document_followups` cron task runs every 15 minutes. To configure quiet hours, set the campaign's `next_action_at` to skip quiet periods when creating or advancing steps.

Currently, quiet hours are not a standalone business rule. Implement by adjusting `step_config` delay values or extending the follow-up automation service.

### Channel Preferences

Available channels per campaign step:

| Channel | Template Field | Recipient Field |
|---|---|---|
| `email` | `subject_template` + `body_template` | `recipient_email` |
| `sms` | `body_template` only | `recipient_phone` |
| `call_script` | `body_template` only | `recipient_phone` |
| `portal` | In-app notification | Portal session |
| `in_app` | Push notification | User session |

### Reminder Frequency

Per-loan reminder settings are stored in the `client_reminder_settings` table:

| Field | Type | Default | Description |
|---|---|---|---|
| `reminders_enabled` | Boolean | true | Whether reminders are active for this loan |
| `reminder_frequency_hours` | Integer | 72 | Hours between reminders (3 days default) |
| `last_reminder_sent_at` | DateTime | null | When the last reminder was sent |
| `reminder_count` | Integer | 0 | Total reminders sent |

Update via:
```
PUT /api/v1/smart-docs/loans/{loan_id}/reminder-settings
{
  "reminders_enabled": true,
  "reminder_frequency_hours": 48
}
```

### Escalation Chain Setup

The campaign's `max_reminders` field (default: 5) controls how many touchpoints occur before the campaign completes or escalates. Trigger sources for campaigns:

| Trigger Source | Description |
|---|---|
| `needs_list_generated` | Automatic when needs list is created |
| `document_rejected` | When a document is rejected |
| `document_expired` | When a document expires |
| `ai_recommendation` | AI suggests follow-up |
| `manual` | LO or processor manually creates |
| `sla_breach` | SLA deadline missed |

### TCPA Consent Requirements

Models in `database/models/tcpa_smart_docs.py` manage telephony consent. SMS and call channels require verified TCPA consent before outbound messages. The follow-up automation service checks consent status before executing call/SMS steps.

### Follow-up Templates

Templates support merge variables substituted at send time:

| Variable | Description |
|---|---|
| `{{borrower_name}}` | Borrower's first name |
| `{{document_list}}` | Comma-separated list of missing docs |
| `{{portal_link}}` | Link to borrower portal |
| `{{due_date}}` | Document request due date |
| `{{lo_name}}` | Loan officer's name |
| `{{lo_phone}}` | Loan officer's phone |

Templates can be platform defaults (`organization_id=NULL`, `is_default=True`) or org-specific customizations. The org-slug composite unique index ensures slug uniqueness within each organization.

---

## 6. Document Security Configuration

Models: `database/models/document_security.py`
Routes: `routes/smart_docs_security_routes.py`

### Upload Size Limits

| Constraint | Value | Location |
|---|---|---|
| File size column | `Integer` on SmartDocument | `models/smart_docs_models.py` |
| JSON payload limit | 1,048,576 bytes (1 MB) | `validate_json_size()` in validators |
| Filename max length | 255 characters | `sanitize_filename()` in validators |

Configure upload size limits at the reverse proxy / load balancer level (nginx `client_max_body_size`) and in FastAPI middleware.

### Allowed File Types

The `mime_type` column on `SmartDocument` (String 128) stores the detected MIME type. Pre-upload validation (`POST /doc-review/validate-upload`) checks file type, size, and basic integrity.

Common allowed MIME types for mortgage documents:
- `application/pdf`
- `image/jpeg`, `image/png`, `image/tiff`
- `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` (Excel)

### Malware Scanning Settings

Malware scanning integration is handled at the storage layer (S3 event trigger or pre-upload scan). The `status` field on `SmartDocument` progresses: `UPLOADED` -> `SCANNING` -> `PROCESSING` -> `APPROVED`/`REJECTED`.

### PII Encryption Configuration

Encryption records are tracked per-document in `document_encryption_records`:

| Field | Type | Description |
|---|---|---|
| `encryption_algorithm` | String(64) | Default: `AES-256-GCM` |
| `key_id` | String(128) | Reference to encryption key (never the key itself) |
| `key_version` | Integer | Supports key rotation |
| `iv_nonce` | String(64) | Initialization vector (hex-encoded) |
| `content_hash_before` | String(64) | SHA-256 of plaintext |
| `content_hash_after` | String(64) | SHA-256 of ciphertext |

Environment variable: `SMART_DOCS_ENCRYPTION_KEY`

Migration: `migrations/smart_docs_pii_encryption.py`

### Fraud Detection Thresholds

| Rule Key | Type | Default | Description |
|---|---|---|---|
| `large_deposit_threshold` | integer | 5000 | Dollar amount requiring sourcing documentation |
| `nsf_max_count_6months` | integer | 3 | Max NSF/overdraft in 6 months before flagging |
| `fraud_score_auto_flag_threshold` | integer | 70 | Risk score (0-100) triggering auto-flag |

**Example: Tighten fraud thresholds:**

```
PUT /api/smart-docs/config/rules/large_deposit_threshold
{
  "value": 3000,
  "description": "Reduced threshold for jumbo loan program"
}
```

Screenshot detection is performed automatically on upload. The `SmartDocument` model tracks:

| Field | Description |
|---|---|
| `detected_is_screenshot` | Boolean flag from AI detection |
| `screenshot_confidence` | Float confidence score |
| `screenshot_reasons` | JSON array of detection layer results |

### SAR Access Restrictions

Suspicious Activity Report access is restricted by role. The security routes enforce admin-only access for SAR-related endpoints. Access attempts (granted and denied) are logged in `document_access_logs` with full context (IP, user agent, geo location, session ID).

---

## 7. Workflow Configuration

### Default Workflows

Smart Docs V2 has built-in workflows triggered by document lifecycle events:

| Trigger Event | Automated Action |
|---|---|
| Needs list generated | Follow-up campaign created |
| Document uploaded | AI review queued |
| AI review: ACCEPT | Request status set to ACCEPTED |
| AI review: REJECT | Request status set to REJECTED, borrower notified |
| AI review: NEEDS_REVIEW | Document added to review queue |
| Document expired | Request reopened, urgent follow-up campaign started |
| Auto-renewal due | New request created, old request deactivated |
| SLA approaching (4 hrs) | SLA warning generated |
| SLA breached | SLA breach alert, potential escalation |

### Custom Workflow Creation

Custom workflows are implemented via campaign step configurations and follow-up templates. Create a campaign with custom `step_config`:

```
POST /api/smart-docs/followup/campaigns
{
  "loan_id": 12345,
  "borrower_id": 678,
  "campaign_type": "initial_request",
  "step_config": [
    {"step": 1, "channel": "portal", "delay_hours": 0, "template": "portal_welcome"},
    {"step": 2, "channel": "email", "delay_hours": 24, "template": "custom_initial"},
    {"step": 3, "channel": "sms", "delay_hours": 72, "template": "sms_nudge"},
    {"step": 4, "channel": "call", "delay_hours": 120, "template": "lo_call_script"}
  ],
  "max_reminders": 4
}
```

### Trigger Events Reference

| Event | Source | Description |
|---|---|---|
| `NEEDS_LIST_GENERATED` | Needs list creation | Full document list generated |
| `DOCUMENT_UPLOADED` | Borrower/LO upload | New document received |
| `AUTO_REQUEST_CREATED` | Auto-renewal cron | Fresh document auto-requested |
| `EXPIRED` | Expiration cron | Document past freshness date |
| `EXPIRATION_REMINDER_SENT` | Expiration cron | Warning before expiration |
| `SCREENSHOT_REJECTED` | AI review | Screenshot detected and rejected |
| `FRESHNESS_REJECTED` | AI review | Document too old |

### Available Actions Reference

| Action | Description |
|---|---|
| Send email | Via follow-up event (`EMAIL_SENT`) |
| Send SMS | Via follow-up event (`SMS_SENT`) |
| Schedule call | Via follow-up event (`CALL_SCHEDULED`) |
| Portal notification | Via follow-up event (`PORTAL_NOTIFICATION`) |
| In-app notification | Via follow-up event (`IN_APP_NOTIFICATION`) |
| Book appointment | Via follow-up event (`APPOINTMENT_BOOKED`) |
| Escalate to LO | Via follow-up event (`ESCALATED_TO_LO`) |
| Create document request | New `DocumentRequest` row |
| Update request status | Change `RequestStatus` |

### Condition Syntax Guide

Campaign step conditions use the `step_config` JSON structure. Conditions are evaluated by the follow-up automation service when advancing steps. The `delay_hours` field controls the minimum wait between steps. The campaign `borrower_responded` flag short-circuits the sequence when the borrower uploads a document.

---

## 8. SLA Configuration

### Default SLA Targets

Document request SLAs are tracked via the `sla_due_at` column on `DocumentRequest`. The default SLA is 3 business days from request creation.

The SLA monitoring cron runs hourly and checks for:

| Condition | Action |
|---|---|
| `sla_due_at` within 4 hours | SLA warning alert |
| `sla_due_at` in the past | SLA breach alert |

### Business Hours Settings

Business hours are used for SLA calculation. Currently implemented at the service layer. Standard defaults:

| Setting | Default |
|---|---|
| Business days | Monday - Friday |
| Business hours | 8:00 AM - 6:00 PM (organization timezone) |
| Excluded | Federal holidays |

### Holiday Calendar Setup

Holidays are excluded from SLA business day calculations. The holiday calendar is managed in the scheduler routing service. Federal holidays are included by default. Add org-specific holidays via the scheduling configuration.

### Warning Thresholds

| Threshold | Default | Description |
|---|---|---|
| SLA warning | 4 hours before due | Approaching SLA deadline |
| SLA breach | Past due | SLA deadline missed |

### Escalation Chain Configuration

SLA breaches can trigger follow-up campaigns with `trigger_source = "sla_breach"`. Configure the escalation sequence using campaign step configs.

---

## 9. Routing & Assignment Configuration

### Round-Robin Setup

Document review queue assignment is handled via the `POST /doc-review/queue/claim` endpoint. Reviewers claim documents from the queue. The queue supports filtering by:

- Priority (`CRITICAL`, `HIGH`, `NORMAL`, `LOW`)
- Document type
- Pagination (limit/offset)

### Skill-Based Routing Rules

Routing is managed at the application layer. The review queue sorts by priority:

1. `CRITICAL` severity first
2. `HIGH` severity
3. `NORMAL` severity
4. `LOW` severity

Within each priority level, documents are ordered by upload date (oldest first).

### Processing Queue Creation

Queues are implicit -- the review queue endpoint filters documents by `decision = NEEDS_REVIEW` or `decision IS NULL` with `status != 'DELETED'`. Claimed documents track the reviewer via the `reviewed_by` column.

### Workload Limits Per User

There is no built-in workload cap per reviewer. Implement at the application layer by checking the count of documents currently claimed by a user before allowing new claims.

---

## 10. White-Label Configuration

### Branding (Logo, Colors, Fonts)

White-label settings are configured via the client portal settings:

```
PUT /api/client-portal/settings
{
  "logo_url": "https://cdn.example.com/logo.png",
  "primary_color": "#1a56db",
  "accent_color": "#e74c3c",
  "company_name": "Acme Mortgage"
}
```

### Email Template Customization

Follow-up email templates support per-org customization. Create org-specific templates:

```
POST /api/smart-docs/followup/templates
{
  "name": "Branded Initial Request",
  "slug": "branded-initial",
  "channel": "email",
  "category": "initial",
  "subject_template": "{{company_name}} - Documents Needed for Your Loan",
  "body_template": "Hi {{borrower_name}},\n\nWe need the following documents...\n\n{{document_list}}\n\nUpload here: {{portal_link}}\n\nQuestions? Call {{lo_name}} at {{lo_phone}}.",
  "variables": ["borrower_name", "document_list", "portal_link", "lo_name", "lo_phone", "company_name"]
}
```

### Portal Customization

The borrower portal (`smart_docs_portal_v2_routes.py`) supports:
- Magic link authentication (no password required)
- Custom branding via portal settings
- Secure document upload
- E-signature integration
- Messaging between borrower and LO

### SMS Sender Name

SMS sender identity is configured at the telephony provider level (Telnyx messaging profile). The default messaging profile ID is set via `TELNYX_MESSAGING_PROFILE_ID` environment variable.

### Compliance Footer (NMLS, Equal Housing)

Add compliance footer to email templates:

```
NMLS #{{nmls_number}} | Equal Housing Lender
{{company_name}} | {{company_address}}
```

Include this in the `body_template` of follow-up templates. NMLS number is stored on the `User` model (`nmls_number` column).

---

## 11. Integration Configuration

### Plaid Setup

Routes: `routes/smart_docs_plaid_routes.py`

| Env Var | Description |
|---|---|
| `PLAID_CLIENT_ID` | Plaid API client ID |
| `PLAID_SECRET` | Plaid API secret key |
| `PLAID_ENVIRONMENT` | `sandbox`, `development`, or `production` |
| `PLAID_WEBHOOK_URL` | Webhook endpoint URL for async events |
| `PLAID_WEBHOOK_VERIFICATION_KEY` | JWT verification key for webhook signatures |

**Endpoints:**
- `POST /plaid/link-token` -- Create Link token for bank connection
- `POST /plaid/exchange-token` -- Exchange public token after Link
- `GET /plaid/connections/{loan_id}` -- List connected accounts
- `POST /plaid/asset-report/{loan_id}` -- Request GSE-certified asset report
- `POST /plaid/analyze/{loan_id}` -- Run bank analysis on Plaid data

Asset reports support 1-730 days of history (`days_requested` field, default: 60).

### AUS (DU/LPA) Setup

Routes: `routes/smart_docs_aus_routes.py`

| Env Var | Description |
|---|---|
| `DU_API_URL` | Desktop Underwriter API endpoint |
| `DU_API_KEY` | DU authentication key |
| `LPA_API_URL` | Loan Product Advisor API endpoint |
| `LPA_API_KEY` | LPA authentication key |

**Endpoints:**
- `POST /aus/submit/{loan_id}` -- Submit to DU or LPA
- `GET /aus/findings/{loan_id}` -- Get latest AUS findings
- `GET /aus/history/{loan_id}` -- Submission history
- `POST /aus/compare-income/{loan_id}` -- Compare our income vs AUS income
- `POST /aus/import-findings/{loan_id}` -- Import conditions into loan
- `GET /aus/mismo-preview/{loan_id}` -- Preview MISMO data before submission

Submit request body:
```json
{
  "aus_type": "DU",
  "include_income": true,
  "income_data": null
}
```

### MISMO Export Configuration

Routes: `routes/smart_docs_mismo_routes.py`

MISMO 3.6 XML generation and validation:

- `GET /mismo/preview/{loan_id}` -- Preview MISMO-mapped data as JSON
- `GET /mismo/xml/{loan_id}?version=3.6` -- Generate MISMO XML
- `GET /mismo/completeness/{loan_id}` -- Check field completeness
- `GET /mismo/mcd/{loan_id}` -- Generate MCD v2.0 report

The MISMO mapper service (`services/smart_docs/integrations/mismo_mapper_service.py`) handles field mapping from the Loan model to MISMO 3.6 structure.

### IRS Transcript Configuration

Routes: `routes/smart_docs_transcript_routes.py`

IRS 4506-C transcript ordering and verification. Tables created by `migrations/add_irs_transcript_table.py`.

| Env Var | Description |
|---|---|
| `IRS_TRANSCRIPT_API_URL` | Transcript vendor API endpoint |
| `IRS_TRANSCRIPT_API_KEY` | Vendor authentication key |

### LOS Field Mapping

For Encompass integration, field mappings are configured via the Encompass integration routes (see `routes/encompass_integration_routes.py`). Smart Docs income data can be pushed to the LOS via the AUS integration service, which builds MISMO data from loan fields.

---

## 12. Reporting Configuration

### Scheduled Report Setup

Reports are generated by the analytics routes (`routes/smart_docs_analytics_routes.py`). The monitoring routes (`routes/smart_docs_monitoring_routes.py`) provide system health dashboards.

Cron tasks generate operational data:

| Task | Schedule | Description |
|---|---|---|
| `process_document_followups` | Every 15 min | Process pending campaign actions |
| `check_document_expirations` | Daily 6:00 AM | Check for expired documents |
| `process_auto_renewals` | Daily 7:00 AM | Auto-renew document requests |
| `send_esignature_reminders` | Every 4 hours | Send e-sign reminders |
| `verify_document_integrity` | Daily 2:00 AM | Sample integrity verification |
| `process_call_intelligence_for_documents` | Every 30 min | Extract doc needs from calls |
| `monitor_document_slas` | Every hour | SLA monitoring |
| `cleanup_smart_docs` | Daily 3:00 AM | Clean expired tokens, count archivable records |

Register cron tasks:
```python
from routes.smart_docs_v2_registration import register_smart_docs_cron_tasks
register_smart_docs_cron_tasks(scheduler)
```

### Report Access by Role

| Role | Access Level |
|---|---|
| Platform Admin | All orgs, all reports, all config |
| Site Admin | Own org, all reports, config changes |
| Loan Officer | Own loans only, read-only reports |
| Processor | Assigned loans, review queue, read-only reports |

Access control is enforced via `get_current_user` dependency and tenant verification helpers (`_verify_loan_tenant`, `_verify_document_tenant`, `_verify_request_tenant`).

### Custom Report Creation

Analytics endpoints return JSON data that can be consumed by frontend dashboards or exported. Key analytics endpoints:

- Document processing volume and turnaround time
- AI review accuracy and decision distribution
- Follow-up campaign effectiveness (response rates)
- SLA compliance rates
- Income calculation statistics

### Export Format Options

| Format | Endpoint | Description |
|---|---|---|
| JSON | All analytics endpoints | Default API response |
| XML | `GET /mismo/xml/{loan_id}` | MISMO 3.6 XML export |
| PDF | Via eClosing routes | Signed document packages |

### Audit Retention

| Rule Key | Default | Source | Description |
|---|---|---|---|
| `audit_retention_days` | 2555 (~7 years) | trid | Audit trail retention period |
| `document_retention_days` | 2555 (~7 years) | trid | Loan document retention period |

The cleanup cron enforces a minimum of 2555 days (7 years) for audit data -- this floor cannot be overridden below the minimum even via environment variable (`AUDIT_RETENTION_DAYS`).

```python
# From smart_docs_cron_tasks.py
MINIMUM_AUDIT_RETENTION_DAYS = 2555  # Floor -- never go below 7 years
```

---

## Appendix: Business Rules API Reference

### List All Rules

```
GET /api/smart-docs/config/rules
GET /api/smart-docs/config/rules?category=income
```

### List Rules by Category

```
GET /api/smart-docs/config/rules/{category}
```

Categories: `income`, `fraud`, `document`, `followup`, `esign`, `compliance`, `ai`

### Update a Rule (Admin Only)

```
PUT /api/smart-docs/config/rules/{rule_key}
{
  "value": <any>,
  "effective_date": "2026-04-01",
  "expiration_date": null,
  "source": "irs_2026",
  "description": "Updated for 2026 tax year"
}
```

### View Rule History

```
GET /api/smart-docs/config/rules/{rule_key}/history?scope=org
```

### Seed Defaults

```
POST /api/smart-docs/config/rules/seed-defaults
```

### Complete Rule Reference

| Rule Key | Type | Default | Category | Source | Description |
|---|---|---|---|---|---|
| `ss_wage_base` | integer | 176100 | income | irs_2025 | Social Security wage base |
| `income_variance_tolerance_pct` | decimal | 5.0 | income | custom | Income variance tolerance (%) |
| `declining_income_threshold_pct` | decimal | 25.0 | income | fannie_mae | Declining income trigger (%) |
| `freshness_paystub` | integer | 30 | document | fannie_mae | Paystub max age (days) |
| `freshness_bank_statement` | integer | 60 | document | fannie_mae | Bank statement max age (days) |
| `freshness_w2` | integer | 365 | document | fannie_mae | W-2 max age (days) |
| `freshness_tax_return` | integer | 365 | document | fannie_mae | Tax return max age (days) |
| `large_deposit_threshold` | integer | 5000 | fraud | custom | Large deposit sourcing threshold ($) |
| `nsf_max_count_6months` | integer | 3 | fraud | custom | Max NSF count in 6 months |
| `fraud_score_auto_flag_threshold` | integer | 70 | fraud | custom | Fraud score auto-flag threshold (0-100) |
| `auto_create_confidence_threshold` | integer | 80 | ai | custom | AI auto-create confidence (%) |
| `medium_confidence_threshold` | integer | 50 | ai | custom | Low-confidence flag threshold (%) |
| `auto_approve_min_confidence` | integer | 90 | ai | custom | AI auto-approve confidence (%) |
| `max_followup_emails_per_day` | integer | 3 | followup | custom | Max follow-up emails/day/borrower |
| `followup_escalation_day` | integer | 7 | followup | custom | Days to escalation |
| `audit_retention_days` | integer | 2555 | compliance | trid | Audit retention (~7 years) |
| `document_retention_days` | integer | 2555 | compliance | trid | Document retention (~7 years) |

### Appendix: Environment Variables

| Variable | Required | Description |
|---|---|---|
| `SMART_DOCS_S3_BUCKET` | Yes | S3 bucket for document storage |
| `SMART_DOCS_ENCRYPTION_KEY` | Yes | AES encryption key for PII |
| `ESIGN_SIGNING_KEY` | Yes | HMAC key for signing tokens |
| `ESIGN_ENCRYPTION_KEY` | Yes | AES key for access codes |
| `PLAID_CLIENT_ID` | For Plaid | Plaid API client ID |
| `PLAID_SECRET` | For Plaid | Plaid API secret |
| `PLAID_ENVIRONMENT` | For Plaid | `sandbox` / `development` / `production` |
| `PLAID_WEBHOOK_URL` | For Plaid | Plaid webhook endpoint |
| `PLAID_WEBHOOK_VERIFICATION_KEY` | For Plaid | Webhook signature verification |
| `DU_API_URL` | For AUS | Desktop Underwriter endpoint |
| `DU_API_KEY` | For AUS | DU authentication key |
| `LPA_API_URL` | For AUS | Loan Product Advisor endpoint |
| `LPA_API_KEY` | For AUS | LPA authentication key |
| `IRS_TRANSCRIPT_API_URL` | For transcripts | IRS transcript vendor endpoint |
| `IRS_TRANSCRIPT_API_KEY` | For transcripts | Vendor auth key |
| `AUDIT_RETENTION_DAYS` | No | Override audit retention (min 2555) |
| `TELNYX_MESSAGING_PROFILE_ID` | For SMS | Telnyx messaging profile |
