# Smart Docs V2 -- Administrator Guide

## Getting Started

### What Smart Docs V2 Does

Smart Docs V2 is Perennia's intelligent document collection and management system for mortgage lending. It automates the creation of borrower needs lists based on loan program and borrower profile, processes uploaded documents through AI-powered classification and fraud detection, tracks document freshness and expiration, calculates income from paystubs and tax returns, manages e-signatures, and gives borrowers a self-service portal to upload and sign documents. The result: faster closings, fewer stips, and less back-and-forth with borrowers.

### Key Features Overview

- **Automated needs list generation** -- builds a customized document checklist based on loan program, occupancy type, income type, and borrower profile
- **AI document classification** -- automatically identifies document types (W-2, paystub, bank statement, etc.) and extracts key data
- **Screenshot detection** -- flags screenshots of documents and requires original uploads
- **Freshness enforcement** -- tracks document dates and flags expired items (30 days for paystubs, 90 days for bank statements)
- **Auto-renewal scheduling** -- automatically creates new document requests when paystubs and bank statements expire based on payroll frequency
- **Income calculation** -- AI-assisted income analysis with maker-checker approval workflow
- **Bank statement analysis** -- detects large deposits, NSF events, undisclosed debts, and IRS payments
- **Built-in e-signatures** -- send documents for electronic signature without leaving the platform
- **Borrower portal** -- self-service portal where borrowers upload documents, sign forms, and track progress
- **Fraud detection** -- risk scoring with tamper detection, integrity verification, and suspicious activity alerts
- **Follow-up campaigns** -- automated email/SMS reminders for outstanding documents
- **Analytics dashboard** -- real-time metrics on document pipeline health, SLA compliance, and team productivity

### User Roles Explained

| Role | What They Can Do |
|------|-----------------|
| **Loan Officer (LO)** | Generate needs lists, send document requests, review borrower uploads, send e-signature envelopes, view their own pipeline analytics |
| **Processor** | Review and approve/reject documents, manage the review queue, claim documents for review, run income calculations, analyze bank statements |
| **Underwriter** | Review documents in the queue, approve income calculations (maker-checker), verify compliance conditions, access fraud analysis |
| **Closer** | Manage e-signature envelopes for closing documents, track signing status, access audit trails |
| **Admin** | All of the above, plus: configure business rules, manage templates, run diagnostics, view cross-team analytics, manage retention policies, access storage health checks |

---

## Managing Document Requests

### How to Generate a Needs List for a New Loan

1. Open the loan file and navigate to the **Smart Docs** tab
2. Click **Generate Needs List**
3. Fill in the required fields:
   - **Loan Program**: Conventional, FHA, VA, or USDA
   - **Occupancy Type**: Primary Residence, Second Home, or Investment
   - **Income Type**: W-2 Employee, Self-Employed, or Retirement
4. Check the applicable boxes:
   - Has gift funds?
   - Is self-employed?
   - Has bankruptcy history?
5. Click **Generate**

The system builds a customized checklist from your organization's needs list templates. Each item includes the document type, description, instructions for the borrower, priority level, and freshness requirements.

> **Pro Tip:** If you have a co-borrower, include their borrower ID when generating the needs list. The system will create separate requests for borrower and co-borrower documents (paystubs, W-2s, etc.) so nothing gets missed.

### How to Add Custom Document Requests

Sometimes the standard needs list does not cover everything. To add a one-off request:

1. Open the loan's needs list
2. Click **Add Custom Request**
3. Fill in:
   - **Title**: What you need (e.g., "Divorce Decree")
   - **Description**: Why you need it
   - **Instructions**: What the borrower should provide
   - **Priority**: Critical, High, Normal, or Low
   - **Due Date**: When you need it by
4. Optionally check **Send Notification** and enter the borrower's email to alert them immediately

### How to Waive a Requirement

To waive a document requirement (for example, when an AUS finding does not require it):

1. Find the item in the needs list
2. Click **Waive**
3. Enter a reason (this is required and recorded in the audit trail)
4. Confirm

The request status changes to WAIVED. The borrower will no longer see it in their portal.

> **Pro Tip:** Waiver reasons are auditable. Use clear, compliant language like "Per DU Finding: asset verification not required" rather than vague notes.

### How to Set Due Dates and Priorities

Each document request has a priority level and an optional due date:

- **Priority levels**: Critical, High, Normal, Low
- **Due dates**: Set when creating or editing a request
- **SLA tracking**: The system automatically sets an SLA due date (3 business days from creation) and tracks whether requests are being fulfilled on time

To update a priority or due date, edit the document request from the needs list view.

### How to Send Reminders to Borrowers

**Manual reminders:**
1. Open the loan's needs list
2. Click **Send Reminder** on individual items or use the bulk reminder option

**Automated follow-up campaigns:**
1. Go to the loan's document follow-up section
2. Click **Create Campaign**
3. Choose the campaign type (email, SMS, or both)
4. Set the schedule (e.g., every 3 days) and maximum number of attempts
5. The system will automatically send reminders until the borrower uploads the document or the campaign reaches its limit

Reminder settings are per-loan. You can enable/disable reminders and adjust the frequency (default is every 72 hours).

> **Pro Tip:** The system tracks reminder counts per loan. If a borrower has received multiple reminders without responding, consider a phone call instead -- the follow-up analytics dashboard shows response rates by channel.

---

## Reviewing Documents

### The Review Queue: How It Works

When a borrower uploads a document, it goes through an automated pipeline:

1. **Upload** -- File is stored securely in S3
2. **Scanning** -- AI checks for screenshots, extracts dates, identifies document type
3. **Processing** -- Freshness validation, data extraction, owner matching (borrower vs. co-borrower)
4. **Decision** -- The system recommends ACCEPT, REJECT, or NEEDS_REVIEW

Documents marked NEEDS_REVIEW land in the review queue. The queue is sorted by priority and shows:
- Document type and loan information
- AI confidence score
- Quality and completeness scores
- Flagged issues (screenshot detected, expired, poor quality)

**Claiming documents:** Click **Claim** on a document to assign it to yourself. This prevents two reviewers from working on the same document. Click **Release** if you need to hand it off.

### How to Approve a Document

1. Open the document from the review queue
2. Review the AI extraction results (the system shows what data it found)
3. Verify the document meets requirements
4. Click **Approve**
5. Optionally assign the document owner (Borrower or Co-Borrower)
6. Optionally apply extracted fields to the loan/lead profile

When you approve, the linked document request status changes to ACCEPTED and the borrower sees a green checkmark in their portal.

### How to Reject a Document

1. Open the document from the review queue
2. Click **Reject**
3. Select a rejection category:
   - **Screenshot** -- Borrower submitted a screenshot instead of the original
   - **Expired** -- Document is too old (beyond freshness window)
   - **Poor Quality** -- Unreadable, blurry, or cut off
   - **Incomplete** -- Missing pages or information
   - **Wrong Type** -- Uploaded to the wrong category
   - **Other** -- Provide a specific reason
4. Enter the rejection reason (required)

The linked request resets to OPEN so the borrower can upload a replacement. The borrower receives a notification explaining what they need to fix.

> **Pro Tip:** Be specific in your rejection reason. Instead of "wrong document," write "This is a 2024 W-2 but we need the 2025 W-2." The borrower sees this message in their portal.

### How to Re-Request a Rejected Document

If a document was rejected and you need the borrower to try again:

1. Find the document request in the needs list
2. Click **Re-Request**
3. Optionally set a new due date (defaults to 7 days from now)
4. Add any clarifying notes

The system marks any previously submitted documents as superseded and sends the borrower a notification with the new request.

### How to Change Document Classification

If the AI misclassified a document (e.g., labeled a W-2 as a paystub):

1. Open the document
2. Click **Change Type**
3. Select the correct document type from the dropdown
4. The system updates the classification and re-links the document to the correct request if applicable

### How to Split Multi-Page Uploads

When a borrower uploads a single PDF containing multiple document types (e.g., W-2 and paystubs combined):

1. Open the document
2. Use the page preview to identify where each document starts and ends
3. Use the split function to separate the pages into individual documents
4. Classify each resulting document appropriately

### How to Merge Documents for Submission

To combine multiple related uploads into a single file (e.g., all pages of a tax return):

1. From the loan's document list, select the documents to merge
2. Click **Merge Documents**
3. Enter a name for the merged file
4. The system creates a single combined document while preserving the originals

---

## Income Calculation

### How the System Calculates Income

Smart Docs uses AI to extract income data from uploaded documents and calculate qualifying income. The system analyzes:

- Paystub data (base pay, overtime, bonuses, commissions, YTD totals)
- W-2 annual earnings
- Tax return income (Schedule C, K-1, rental income)
- Bank statement deposit patterns

The calculation follows standard agency guidelines for annualizing, trending, and averaging income.

### Understanding the Income Breakdown

Each income calculation shows:
- **Income sources**: Each source listed separately with type, amount, frequency, and confidence score
- **Monthly qualifying income**: The calculated monthly amount
- **Trending analysis**: Whether income is stable, increasing, or declining
- **Supporting documents**: Which documents were used in the calculation

### When to Override AI Calculations

You can override AI-calculated values when:
- The AI misread a number on a document
- A non-standard income situation requires manual adjustment
- Agency guidelines require a specific calculation method the AI did not apply

To override: click on the income source, enter the corrected value, and provide a reason. All overrides are logged in the audit trail.

### Maker-Checker: Why You Cannot Approve Your Own Work

For compliance and quality control, Smart Docs enforces a **maker-checker** rule on income calculations:

- The person who creates or calculates income **cannot** be the same person who approves it
- The system enforces this automatically -- if you calculated the income, the Approve button will not be available to you
- A different team member must review and approve the calculation
- The approved_by field is always set from the authenticated user's identity, never from manual input

### Common Income Scenarios

**W-2 Salaried Employee**
- System uses most recent paystub YTD earnings and prior year W-2s
- Calculates monthly income by dividing YTD by months elapsed or annualizing W-2 income
- Flags any variance between paystub and W-2 income

**Self-Employed Borrower**
- Requires 2 years of personal and business tax returns plus year-to-date profit and loss
- System calculates net income from Schedule C or K-1 distributions
- Automatically checks for declining income trends

**Commission Income**
- Uses 2-year average from W-2s and/or tax returns
- Flags if commission is less than 25% of total income (may not need 2-year history per agency guidelines)
- Compares to YTD paystub commission for trending

**Rental Income**
- Extracts Schedule E data from tax returns
- Applies standard depreciation add-back and vacancy factor
- Calculates net rental income per property

**Retirement Income**
- Identifies pension, Social Security, and retirement account distributions
- Verifies 3-year continuance requirement
- Flags non-taxable income for gross-up eligibility

**Multiple Income Sources**
- Each source is calculated independently
- System aggregates all qualifying sources into a total monthly income
- Sources can be individually approved, rejected, or overridden

---

## E-Signatures

### How to Send a Document for Signature

1. Open the loan file and go to the Smart Docs section
2. Click **Send for Signature**
3. Choose the document to send or create from a template
4. Add recipients:
   - Enter name and email for each signer
   - Set the signing order if sequential signatures are needed
   - Choose authentication method (email link, access code, or knowledge-based authentication)
5. Place signature fields on the document (signature, initials, date, text)
6. Add a message to the signers (optional)
7. Click **Send**

The system creates an envelope, generates secure signing links, and sends email notifications to each recipient.

> **Pro Tip:** Use e-signature templates for documents you send repeatedly (disclosures, LOEs, authorization forms). Templates save the field placement so you do not have to redo it each time.

### Tracking Signature Status

The e-signature dashboard shows:
- **Envelope status**: Draft, Sent, Partially Signed, Completed, Declined, Voided, Expired
- **Per-recipient status**: Pending, Viewed, Signed, Declined
- **Timeline**: When each recipient received, viewed, and signed the document

You can filter by status, date range, or loan to find specific envelopes.

### What Borrowers See in the Signing Experience

When a borrower receives a signing request:

1. They get an email with a secure link
2. The link opens a signing page (no login required)
3. They review the document
4. They consent to electronic signatures (E-SIGN Act disclosure)
5. They complete any authentication challenges (if KBA is enabled)
6. They click each signature/initial field to apply their signature
7. They receive a confirmation email with the signed document attached

### Accessing the Audit Trail

Every e-signature action is logged with timestamps, IP addresses, and user agents:

- Envelope created, sent, viewed, signed, declined, voided
- Authentication attempts (passed/failed)
- Document access events
- Consent records

To view the audit trail: open the envelope and click **Audit Trail**. You can export this as a compliance record.

### Troubleshooting Common Signer Issues

| Issue | Solution |
|-------|----------|
| Signer says they never got the email | Check the recipient status -- if still "Pending," resend the envelope. Check spam filters. |
| Signing link expired | Resend the envelope to generate a fresh link. Default expiration is 7 days. |
| Signer declined | Review the decline reason. You can void the envelope and create a new one. |
| KBA authentication failed | The signer may have answered identity questions incorrectly. They get multiple attempts. Contact them to verify identity offline. |
| Signer cannot open on mobile | The signing experience is web-based and mobile-friendly. Suggest they try a different browser. |

---

## Borrower Portal

### What Borrowers See in the Portal

The borrower portal shows:
- **Document checklist** -- all requested documents with status indicators (needed, uploaded, approved, rejected)
- **Upload area** -- drag-and-drop or file selector for each document request
- **E-signature requests** -- any documents waiting for their signature
- **Letter of Explanation (LOE)** -- a form to write and sign explanations when requested
- **Messages** -- communication with their loan officer about document questions
- **Loan progress** -- visual tracker showing where their loan is in the process
- **Previously uploaded documents** -- list of everything they have submitted

### How to Send Portal Access

**Magic link (recommended):**
1. From the loan file, click **Send Portal Access**
2. Enter the borrower's email
3. Choose language (English or Spanish)
4. Click **Send Magic Link**
5. The borrower receives an email with a one-click login link

**Access code:**
1. Generate a 6-digit access code for the borrower
2. Share the code with them (by phone, text, or in person)
3. The borrower enters their email and the code on the portal login page

Both methods create a time-limited JWT token for secure access. No password creation is required.

> **Pro Tip:** Magic links are the easiest option for borrowers. The link works on any device -- phone, tablet, or computer -- and no app download is needed.

### Customizing Portal Branding

Admins can customize the borrower portal appearance through the organization settings:
- Company logo
- Primary and accent colors
- Custom welcome message
- Contact information displayed to borrowers

### Monitoring Borrower Engagement

The analytics dashboard tracks borrower portal activity:
- When the borrower last visited the portal
- Which documents they have viewed, uploaded, or signed
- Response time (how quickly they act after receiving a request)
- Follow-up campaign effectiveness (open rates, response rates by channel)

Use this data to identify borrowers who may need a personal phone call to keep things moving.

---

## Fraud Detection

### What the System Checks For

Smart Docs runs several automated fraud checks on every uploaded document:

- **Screenshot detection** -- Multi-layer analysis detects screenshots of documents (metadata analysis, visual artifacts, DPI inconsistencies). Each detection includes a confidence score and the specific reasons it was flagged.
- **Document integrity** -- SHA-256 hash comparison to detect tampering after upload
- **Date consistency** -- Cross-references dates across documents (e.g., paystub dates match W-2 tax year)
- **Name matching** -- Verifies names on documents match the borrower and co-borrower on file
- **Large deposit analysis** -- Flags unexplained large deposits in bank statements
- **Undisclosed debt detection** -- Identifies recurring payments in bank statements not reflected on the application
- **IRS payment detection** -- Flags tax payments that may indicate unreported tax obligations

### Understanding Fraud Scores

Each document receives a risk score based on the automated checks:

- **Low risk (0-30)**: No significant concerns detected
- **Medium risk (31-60)**: Minor flags that warrant a quick review (e.g., slightly low image quality)
- **High risk (61-80)**: Significant concerns detected (e.g., screenshot indicators, date inconsistencies)
- **Critical risk (81-100)**: Strong fraud indicators -- requires immediate human review

The risk score considers multiple factors and weights them based on severity. A single critical flag (like confirmed screenshot detection) can push the score into the high/critical range.

### What to Do When Fraud Is Detected

1. **Review the flagged document** -- Open the fraud analysis to see exactly what was detected
2. **Check the specific indicators** -- Each flag includes a description and recommendation
3. **Request replacement if needed** -- If the issue is a screenshot or quality problem, reject and re-request
4. **Escalate if warranted** -- For serious fraud indicators, follow your organization's fraud escalation procedures
5. **Document your findings** -- All actions are logged in the audit trail

### SAR Filing Obligations

If you identify suspected fraud that meets the reporting threshold, you are required to file a Suspicious Activity Report (SAR) with FinCEN. Smart Docs logs and audit trails can support your SAR documentation, but the filing decision and process should follow your organization's compliance procedures. Consult your compliance officer for specific guidance.

---

## Reports & Analytics

### Available Reports and What They Show

| Report | What It Shows |
|--------|---------------|
| **Document Dashboard** | Overview of pipeline health: total documents, review status breakdown, pending count, approval rate |
| **Pipeline Completeness** | Per-loan document completion percentage, showing which loans are closest to being file-complete |
| **SLA Compliance** | How many document requests are being fulfilled within SLA targets (3 business days), broken down by time period |
| **AI Performance** | Classification accuracy, auto-accept rate, false positive/negative rates for screenshot detection |
| **Follow-Up Effectiveness** | Campaign response rates, average documents received per campaign, channel performance (email vs. SMS) |
| **Income Summary** | Income calculations by status (pending, approved, rejected), average processing time |
| **Bank Analysis Summary** | Large deposit counts, NSF frequency, undisclosed debt detection rates |
| **E-Signature Metrics** | Envelope completion rates, average time to sign, decline rates |
| **Processor Productivity** | Per-reviewer metrics: documents reviewed, average review time, approval/rejection rates |
| **Document Trends** | Upload and approval volumes over time, seasonal patterns |
| **Bottleneck Analysis** | Identifies where documents are getting stuck in the pipeline |

### How to Run a Report

1. Navigate to **Smart Docs Analytics**
2. Select the report you want to run
3. Set filters:
   - **Date range**: Defaults to last 30 days
   - **Loan officer**: Filter by specific LO or view all
   - **Document type**: Filter by specific document category
4. Click **Run Report**

Results display in the dashboard with charts and tables.

### How to Schedule Recurring Reports

Contact your admin to set up scheduled reports. Reports can be configured to run daily, weekly, or monthly through the cron task system. Results are delivered via email or available in the dashboard.

### Key Metrics to Monitor

As an admin, focus on these metrics:

- **SLA compliance rate** -- Target 90%+ of document requests fulfilled within 3 business days
- **AI auto-accept rate** -- Higher is better (fewer documents needing manual review). Typical range: 40-60%
- **Screenshot rejection rate** -- Trend should decrease over time as borrowers learn to submit originals
- **Document expiration alerts** -- Monitor expiring documents to prevent delays at closing
- **Processor review backlog** -- Keep the review queue under control; redistribute workload if needed
- **Follow-up response rate** -- If below 30%, consider adjusting messaging or switching channels

### Exporting Data

Most reports support data export. Click **Export** to download results as CSV for further analysis in Excel or other tools. The loan-level timeline view can also be exported for compliance documentation.

---

## Managing Your Team

### Setting Up Processor Assignments

Documents enter the review queue where any processor can claim them. To manage assignments:

- **Self-service claiming**: Processors click **Claim** on documents in the queue to assign them to themselves
- **Release and reassign**: If a processor is unavailable, release their claimed documents back to the queue
- **Admin override**: Admins can reassign documents between team members

### Configuring Routing Rules

Admins can configure auto-review settings that determine which documents skip manual review:

- **Auto-accept threshold**: Documents above a certain AI confidence score are automatically accepted
- **Auto-reject threshold**: Documents below a certain score are automatically rejected (e.g., confirmed screenshots)
- **Always-review types**: Certain document types (e.g., tax returns, appraisals) can be set to always require human review regardless of AI confidence

To configure: go to **Smart Docs Settings** and adjust the auto-review thresholds.

> **Pro Tip:** Start with conservative thresholds (high auto-accept, low auto-reject) and gradually widen as you build confidence in the AI classification accuracy. Monitor the AI Performance report to track false positives and negatives.

### Monitoring SLA Compliance

The SLA compliance dashboard shows:
- Percentage of document requests fulfilled within the 3-business-day target
- Breakdown by document type (some types consistently take longer)
- Trend over time (are you improving or declining?)
- Individual loans that are past due on document requests

Set up alerts for loans where document SLAs are at risk of being breached.

### Workload Balancing

Use the Processor Productivity report to monitor team workload:
- Review count per processor
- Average review time
- Current queue depth
- Documents claimed but not yet reviewed

If one processor is overloaded while others have capacity, redistribute by releasing and reclaiming documents.

### Performance Tracking

Track team performance through these metrics:
- **Throughput**: Documents reviewed per day per processor
- **Accuracy**: Rejection rate and re-review rate (lower is better)
- **Responsiveness**: Average time from document upload to review completion
- **SLA compliance**: Percentage of reviews completed within target timeframes

---

## Troubleshooting

### Common Issues and Fixes

| Issue | Likely Cause | Fix |
|-------|-------------|-----|
| Borrower cannot see document requests in portal | Loan ID mismatch between Smart Docs and portal system | Admin: run the Loan ID Mismatch Analysis diagnostic. It will identify and optionally fix mismatches. |
| Document upload fails | File too large, unsupported format, or S3 storage issue | Check file size (max varies by config). Supported formats: PDF, JPG, PNG. Admin: run the Storage Health diagnostic. |
| AI classified document incorrectly | Low-confidence classification on unusual documents | Manually change the document type. The AI learns from corrections over time. |
| Screenshot detected on a legitimate document | Borrower took a photo of a printout, or document has low DPI | Review the screenshot confidence score. If below 70%, it may be a false positive. Approve manually. |
| Needs list is missing expected items | Template does not cover the specific scenario | Add custom requests for missing items. Admin: update the needs list template to include the document type. |
| Document shows as expired | Document date is outside the freshness window | Request a current version. For paystubs (30-day window) and bank statements (90-day window), the borrower needs to provide a recent copy. |
| E-signature email not received | Email delivery issue or spam filter | Check recipient status in the envelope. Resend the envelope. Ask borrower to check spam/junk folder. |
| Income calculation seems wrong | AI misread a value or used wrong calculation method | Override the specific income source with the correct value and provide a reason. Have a second person approve. |
| Borrower uploaded to wrong request | Borrower selected the wrong document type during upload | Change the document classification and re-link to the correct request. |
| Review queue is empty but documents are pending | Auto-review settings may be accepting/rejecting without manual review | Check the auto-review thresholds in Smart Docs Settings. Review the AI Performance report for auto-decision rates. |
| Portal magic link not working | Link expired (time-limited) or already used | Send a new magic link. Links are single-use and time-limited for security. |
| Merged document is missing pages | Source documents may have been deleted before merge | Check document status of the source files. Re-upload and re-merge if needed. |

### When to Contact Support

Contact Perennia support when:
- S3 storage diagnostics show persistent errors
- The AI classification accuracy drops significantly (check the AI Performance report)
- Database errors appear in the system health check
- Cron tasks (follow-up processing, expiration checks, SLA monitoring) are not running
- You need to adjust retention policies or compliance settings beyond what the admin interface provides

### Error Message Reference

| Error | Meaning |
|-------|---------|
| "Not found" | The document, request, or loan does not exist or belongs to a different organization (tenant isolation) |
| "Admin access required" | The action requires Platform Admin or Site Admin role |
| "Unable to retrieve document content for extraction" | The document file could not be downloaded from S3 storage for AI processing |
| "Extraction failed" | AI data extraction encountered an error -- try reprocessing the document |
| "Invalid document type" | The specified document type is not in the allowed list -- check the dropdown for valid options |
| "File not found in storage" | The document record exists in the database but the actual file is missing from S3 -- run the orphan cleanup diagnostic |
| "Request uses PURL loan ID instead of main_loan_id" | Internal ID mismatch -- run the Loan ID Mismatch fix from the admin panel |

> **Pro Tip:** The admin diagnostic endpoints (Storage Health, Upload Diagnostic, Loan ID Mismatch Analysis) are your first line of defense when troubleshooting. Run them before opening a support ticket -- they often identify and can auto-fix the issue.
