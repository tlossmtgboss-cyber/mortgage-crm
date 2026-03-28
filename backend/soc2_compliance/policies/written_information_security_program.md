# Written Information Security Program (WISP)

**Perennia AI, Inc.**

---

| Field | Value |
|---|---|
| **Document Title** | Written Information Security Program (WISP) |
| **Document ID** | WISP-001 |
| **Classification** | Confidential |
| **Version** | 1.0 |
| **Effective Date** | 2026-03-27 |
| **Last Reviewed** | 2026-03-27 |
| **Next Review** | 2026-09-27 |
| **Owner** | Security Officer |
| **SOC 2 Criteria** | CC1-CC9, A1, PI1, C1, P1-P8 |

---

## Table of Contents

1. [Executive Summary & Purpose](#1-executive-summary--purpose)
2. [Scope](#2-scope)
3. [Organizational Security Governance](#3-organizational-security-governance)
4. [Information Security Objectives](#4-information-security-objectives)
5. [Risk Assessment Framework](#5-risk-assessment-framework)
6. [Security Control Framework](#6-security-control-framework)
7. [Data Classification & Handling](#7-data-classification--handling)
8. [Access Control & Authentication](#8-access-control--authentication)
9. [Encryption Standards](#9-encryption-standards)
10. [Incident Response Overview](#10-incident-response-overview)
11. [Business Continuity & Disaster Recovery](#11-business-continuity--disaster-recovery)
12. [Vendor & Third-Party Risk Management](#12-vendor--third-party-risk-management)
13. [Employee Security Responsibilities](#13-employee-security-responsibilities)
14. [Security Awareness Training Requirements](#14-security-awareness-training-requirements)
15. [Compliance Monitoring & Audit](#15-compliance-monitoring--audit)
16. [Policy Review & Update Schedule](#16-policy-review--update-schedule)
17. [Approval & Signatures](#17-approval--signatures)

---

## 1. Executive Summary & Purpose

**SOC 2 Criteria:** CC1.1, CC1.2, CC1.3, CC1.4, CC5.1

### 1.1 Executive Summary

Perennia AI, Inc. ("Perennia AI," "the Company") operates an AI-first operating platform for mortgage loan officers, processing and storing sensitive financial data including personally identifiable information (PII), loan application data, credit information, and financial records subject to federal and state regulatory requirements.

This Written Information Security Program (WISP) establishes the comprehensive framework governing the protection of all information assets under Perennia AI's custody or control. It serves as the authoritative, board-level security document that consolidates and governs eight subordinate security policies into a unified program aligned with SOC 2 Type II Trust Service Criteria.

### 1.2 Purpose

The purpose of this WISP is to:

(a) Define the organizational structure, roles, and responsibilities for information security governance at Perennia AI, Inc.

(b) Establish information security objectives and the risk management framework used to identify, assess, and mitigate threats to the confidentiality, integrity, and availability of information assets.

(c) Provide a unified control framework that consolidates and references eight subordinate security policies, ensuring comprehensive coverage of all SOC 2 Trust Service Criteria.

(d) Ensure compliance with applicable federal and state regulations, including but not limited to the Gramm-Leach-Bliley Act (GLBA), the Truth in Lending Act/Real Estate Settlement Procedures Act Integrated Disclosure rule (TRID), the California Consumer Privacy Act (CCPA), and state breach notification laws.

(e) Communicate security expectations to all personnel, contractors, and third-party service providers who access, process, or store Perennia AI information assets.

### 1.3 Authority

This WISP is approved by the Chief Executive Officer, Chief Technology Officer, and Security Officer of Perennia AI, Inc. It supersedes all prior versions and takes precedence in the event of any conflict with subordinate policies. Subordinate policies shall be interpreted in a manner consistent with this WISP.

### 1.4 Regulatory Context

Perennia AI operates within the mortgage lending industry and is subject to the following regulatory frameworks, which inform the controls established in this program:

| Regulation | Applicability |
|---|---|
| Gramm-Leach-Bliley Act (GLBA) | Financial data safeguards, privacy notices |
| TILA-RESPA Integrated Disclosure (TRID) | Loan disclosure timing and tolerance |
| Real Estate Settlement Procedures Act (RESPA) | Settlement service provider oversight |
| California Consumer Privacy Act (CCPA) | Consumer data rights for California residents |
| State Breach Notification Laws | Incident notification obligations (all 50 states) |
| Fair Credit Reporting Act (FCRA) | Credit data handling and permissible purposes |
| SOC 2 Type II | Trust Service Criteria for service organizations |

---

## 2. Scope

**SOC 2 Criteria:** CC1.1, CC2.1, CC2.2

### 2.1 Systems in Scope

This WISP applies to all information systems owned, operated, or managed by Perennia AI, Inc., including but not limited to:

(a) **Production Platform** -- The Perennia AI mortgage CRM application, including all backend services (FastAPI application server), frontend single-page application, and supporting microservices.

(b) **Data Stores** -- All PostgreSQL databases, including production, staging, and backup instances hosted on Railway infrastructure.

(c) **AI and Voice Services** -- Aria voice AI agent, AI chat services, call intelligence processing, and all integrations with third-party AI providers (OpenAI, Deepgram, Vapi).

(d) **Communication Systems** -- Telephony integrations (Telnyx, Twilio), email intelligence (SendGrid), SMS services, and voicemail drop capabilities.

(e) **Integration Points** -- Salesforce CRM synchronization, Encompass LOS integration, and all third-party API connections.

(f) **Monitoring and Observability** -- DataDog SIEM integration, audit logging infrastructure, and compliance scanning systems.

(g) **Development Infrastructure** -- Source code repositories (GitHub), CI/CD pipelines (Railway), and development environments.

### 2.2 Data in Scope

All data processed, stored, or transmitted by Perennia AI systems, classified per the Data Classification Policy (Section 7), including:

- Borrower personally identifiable information (PII)
- Loan application and processing data
- Financial records (income, assets, credit)
- Communication records (calls, emails, SMS)
- Audit logs and security event data
- System configuration and credentials

### 2.3 Personnel in Scope

This WISP applies to all individuals who access Perennia AI information systems or data:

- Full-time and part-time employees
- Independent contractors and consultants
- Third-party service providers and their personnel
- Temporary workers and interns
- Loan officers, processors, and other end users of the platform

### 2.4 Exclusions

No systems, data categories, or personnel with access to Perennia AI information assets are excluded from the scope of this WISP.

---

## 3. Organizational Security Governance

**SOC 2 Criteria:** CC1.1, CC1.2, CC1.3, CC1.4, CC1.5

### 3.1 Governance Structure

Perennia AI maintains a security governance structure with clearly defined roles, responsibilities, and reporting lines to ensure accountability for the protection of information assets.

```
Board of Directors / CEO
        |
Chief Technology Officer (CTO)
        |
  +-----+-----+
  |             |
Security    Engineering
Officer       Lead
  |
Data Protection
  Officer
```

### 3.2 Roles and Responsibilities

#### 3.2.1 Chief Executive Officer (CEO)

- Bears ultimate accountability for the information security posture of Perennia AI, Inc.
- Approves this WISP and allocates resources for its implementation.
- Receives quarterly security posture briefings from the Security Officer.
- Authorizes exceptions to security policies when business justification warrants and compensating controls are documented.

#### 3.2.2 Chief Technology Officer (CTO)

- Provides executive oversight of the security program and its alignment with business objectives.
- Approves the security budget, staffing, and technology investments.
- Ensures security requirements are integrated into the software development lifecycle.
- Serves as the executive escalation point for security incidents classified as Critical severity.
- Co-approves this WISP and all material amendments.

#### 3.2.3 Security Officer (CISO Function)

- Owns and maintains this WISP and all subordinate security policies.
- Directs the security team in the execution of the information security program.
- Conducts or oversees risk assessments, vulnerability management, and compliance monitoring.
- Manages the incident response program and serves as the Incident Commander for Critical and High severity incidents.
- Reports security posture metrics to the CTO and CEO on a quarterly basis.
- Coordinates SOC 2 Type II audit activities with external auditors.
- Oversees security awareness training program for all personnel.

#### 3.2.4 Data Protection Officer (DPO)

- Ensures compliance with data privacy regulations (GLBA, CCPA, FCRA, state privacy laws).
- Manages data subject access requests (DSARs) and deletion requests.
- Oversees the data classification program and ensures appropriate handling controls are implemented.
- Reviews data processing agreements (DPAs) with third-party vendors.
- Advises on privacy impact assessments for new features or integrations involving PII.
- Coordinates breach notification obligations under applicable state and federal law.

#### 3.2.5 Engineering Lead

- Implements technical security controls within the Perennia AI platform.
- Manages the change management process and ensures all changes follow the Change Management Policy.
- Maintains the CI/CD pipeline security, including automated testing and deployment safeguards.
- Oversees database security, encryption implementation, and infrastructure hardening.
- Leads post-mortem reviews for security incidents involving application or infrastructure components.
- Conducts code reviews with security considerations for all pull requests affecting sensitive systems.

#### 3.2.6 All Personnel

- Comply with this WISP and all subordinate security policies.
- Complete required security awareness training within established timelines.
- Report suspected security incidents, policy violations, and vulnerabilities promptly.
- Protect credentials, access tokens, and other authentication materials from unauthorized disclosure.

### 3.3 Security Governance Cadence

| Activity | Frequency | Participants |
|---|---|---|
| Security posture briefing to CEO | Quarterly | Security Officer, CEO |
| Security program review | Semi-annual | CTO, Security Officer, Engineering Lead, DPO |
| Policy review cycle | Semi-annual | Security Officer, policy owners |
| Risk assessment review | Annual (or upon material change) | Security Officer, CTO, Engineering Lead |
| SOC 2 audit coordination | Annual | Security Officer, external auditors |
| Incident response drill | Quarterly | Security team, engineering team |

---

## 4. Information Security Objectives

**SOC 2 Criteria:** CC1.1, CC1.3, CC2.1

### 4.1 Primary Objectives

Perennia AI establishes the following information security objectives, which shall guide the design, implementation, and continuous improvement of all security controls:

**(a) Confidentiality** -- Ensure that sensitive information, including borrower PII, financial records, loan data, and proprietary business information, is accessible only to authorized individuals and systems with a legitimate need. *(SOC 2 Criteria: C1)*

**(b) Integrity** -- Maintain the accuracy, completeness, and reliability of all information assets throughout their lifecycle. Prevent unauthorized modification of data, system configurations, and audit records. *(SOC 2 Criteria: PI1)*

**(c) Availability** -- Ensure that information systems and data are accessible to authorized users when needed, with defined recovery time and recovery point objectives. *(SOC 2 Criteria: A1)*

**(d) Privacy** -- Process personal information in accordance with applicable privacy regulations and the Company's privacy commitments, including collection limitation, use limitation, and secure disposal. *(SOC 2 Criteria: P1-P8)*

**(e) Regulatory Compliance** -- Maintain continuous compliance with GLBA, TRID, RESPA, CCPA, FCRA, and other applicable federal and state regulations governing the mortgage lending industry.

### 4.2 Measurable Security Targets

| Objective | Metric | Target |
|---|---|---|
| Incident response time (Critical) | Time from detection to containment | Less than or equal to 1 hour |
| Incident response time (High) | Time from detection to containment | Less than or equal to 4 hours |
| System availability | Platform uptime | Greater than or equal to 99.5% |
| Vulnerability remediation (Critical) | Time from identification to patch | Less than or equal to 72 hours |
| Access review completion | Percentage of reviews completed on schedule | 100% quarterly |
| Security training completion | Percentage of personnel trained | 100% within 30 days of hire; annual refresher |
| Encryption coverage (Restricted data) | Percentage of Restricted fields encrypted at rest | 100% |
| Backup restoration success | Quarterly restoration test pass rate | 100% |
| SOC 2 audit findings | Number of qualified/adverse findings | Zero |

### 4.3 Continuous Improvement

The security program shall be subject to continuous improvement through:

- Lessons learned from security incidents and post-mortems.
- Findings from internal compliance scans and external audits.
- Changes in the regulatory landscape or threat environment.
- Feedback from personnel, customers, and third-party assessors.

---

## 5. Risk Assessment Framework

**SOC 2 Criteria:** CC3.1, CC3.2, CC3.3, CC3.4, CC9.1

### 5.1 Risk Assessment Methodology

Perennia AI conducts formal risk assessments to identify, analyze, and evaluate risks to the confidentiality, integrity, and availability of information assets. The risk assessment methodology follows these phases:

#### Phase 1: Asset Identification
- Inventory all information assets, including data stores, applications, integrations, and infrastructure components.
- Classify assets according to the Data Classification Policy.
- Identify asset owners responsible for security decisions.

#### Phase 2: Threat Identification
- Identify potential threat sources, including external adversaries, insider threats, environmental hazards, and system failures.
- Consider threats specific to the mortgage lending industry, including fraud, identity theft, and regulatory non-compliance.
- Review threat intelligence sources and industry advisories.

#### Phase 3: Vulnerability Assessment
- Identify vulnerabilities in systems, processes, and controls that could be exploited by identified threats.
- Conduct automated vulnerability scanning of application dependencies (pinned in `requirements.lock`).
- Perform annual penetration testing by a qualified third party.
- Review application security through code reviews and static analysis.

#### Phase 4: Risk Analysis

Risks are evaluated using a qualitative risk matrix based on likelihood and impact:

| | **Impact: Low** | **Impact: Medium** | **Impact: High** | **Impact: Critical** |
|---|---|---|---|---|
| **Likelihood: High** | Medium | High | Critical | Critical |
| **Likelihood: Medium** | Low | Medium | High | Critical |
| **Likelihood: Low** | Low | Low | Medium | High |
| **Likelihood: Rare** | Low | Low | Low | Medium |

#### Phase 5: Risk Treatment

For each identified risk, one of the following treatment strategies shall be applied:

- **Mitigate** -- Implement controls to reduce the likelihood or impact of the risk to an acceptable level.
- **Transfer** -- Transfer the risk to a third party through insurance, contractual terms, or outsourcing.
- **Accept** -- Accept the residual risk with documented justification and executive approval.
- **Avoid** -- Eliminate the risk by discontinuing the activity or removing the asset.

### 5.2 Risk Assessment Schedule

| Assessment Type | Frequency | Responsible Party |
|---|---|---|
| Comprehensive risk assessment | Annual | Security Officer |
| Targeted risk assessment (new features/integrations) | As needed | Security Officer, Engineering Lead |
| Automated vulnerability scanning | Monthly (dependency review) | Engineering Lead |
| Penetration testing | Annual | External vendor |
| Risk register review | Quarterly | Security Officer, CTO |

### 5.3 Risk Acceptance

Risks with a residual rating of High or Critical after treatment require documented acceptance by the CTO or CEO. Accepted risks shall be reviewed quarterly and re-evaluated at each annual risk assessment.

### 5.4 Mortgage Industry-Specific Risks

The following risk categories receive heightened attention due to the nature of the mortgage lending industry:

| Risk Category | Description | Primary Controls |
|---|---|---|
| Borrower PII exposure | Unauthorized access to SSN, financial data, credit scores | Fernet field-level encryption, RLS, access logging |
| Regulatory non-compliance | TRID timing violations, RESPA fee tolerance breaches | Automated compliance scanning, disclosure timeline tracking |
| Loan data integrity | Unauthorized modification of loan terms, rates, or conditions | Audit trails, change management, WORM protections |
| Third-party data sharing | Improper data exposure through integrations | Vendor risk management, DPAs, scoped API credentials |
| Fraud and identity theft | Synthetic identity fraud, wire fraud schemes | Anomaly detection, verification workflows |

---

## 6. Security Control Framework

**SOC 2 Criteria:** CC5.1, CC5.2, CC5.3

### 6.1 Framework Overview

Perennia AI implements a layered security control framework organized into eight subordinate policies. Each policy addresses a specific domain of the security program and maps to one or more SOC 2 Trust Service Criteria. Together, these policies provide comprehensive coverage of all applicable criteria.

This WISP serves as the governing document. In the event of any conflict between this WISP and a subordinate policy, this WISP shall prevail.

### 6.2 Subordinate Policy Index

| # | Policy Name | Path | SOC 2 Criteria | Owner |
|---|---|---|---|---|
| 1 | Information Security Policy | `backend/soc2_compliance/policies/information_security_policy.md` | CC1, CC5 | Security Team |
| 2 | Access Control Policy | `backend/soc2_compliance/policies/access_control_policy.md` | CC6 | Security Team |
| 3 | Incident Response Policy | `backend/soc2_compliance/policies/incident_response_policy.md` | CC7 | Security Team |
| 4 | Change Management Policy | `backend/soc2_compliance/policies/change_management_policy.md` | CC8 | Engineering Team |
| 5 | Data Classification Policy | `backend/soc2_compliance/policies/data_classification_policy.md` | C1 | Security Team |
| 6 | Data Retention Policy | `backend/soc2_compliance/policies/data_retention_policy.md` | P4 | Security Team |
| 7 | Vendor Management Policy | `backend/soc2_compliance/policies/vendor_management_policy.md` | CC9 | Security Team |
| 8 | Disaster Recovery Policy | `backend/soc2_compliance/policies/disaster_recovery_policy.md` | A1 | Engineering Team |

### 6.3 SOC 2 Trust Service Criteria Coverage Matrix

The following matrix maps each SOC 2 Trust Service Criterion to the subordinate policies and WISP sections that address it:

| Criterion | Description | Governing Policies | WISP Sections |
|---|---|---|---|
| **CC1** | Control Environment | Information Security Policy, WISP | 1, 3, 4, 13, 14 |
| **CC2** | Communication and Information | WISP | 2, 3, 6, 14 |
| **CC3** | Risk Assessment | WISP | 5 |
| **CC4** | Monitoring Activities | WISP | 15 |
| **CC5** | Control Activities | Information Security Policy, WISP | 6, 7, 8, 9 |
| **CC6** | Logical and Physical Access | Access Control Policy | 8 |
| **CC7** | System Operations | Incident Response Policy | 10 |
| **CC8** | Change Management | Change Management Policy | 6.2 (#4) |
| **CC9** | Risk Mitigation | Vendor Management Policy, WISP | 5, 12 |
| **A1** | Availability | Disaster Recovery Policy | 11 |
| **PI1** | Processing Integrity | Change Management Policy, WISP | 4, 6, 9 |
| **C1** | Confidentiality | Data Classification Policy, WISP | 7, 9 |
| **P1** | Privacy Notice | WISP | 7, 13 |
| **P2** | Choice and Consent | WISP | 7.5 |
| **P3** | Collection | Data Classification Policy, WISP | 7 |
| **P4** | Use, Retention, and Disposal | Data Retention Policy | 7, 16 |
| **P5** | Access (Data Subject Rights) | Data Retention Policy, WISP | 7.5 |
| **P6** | Disclosure and Notification | Incident Response Policy, WISP | 10 |
| **P7** | Quality | WISP | 7, 15 |
| **P8** | Monitoring and Enforcement | WISP | 15 |

### 6.4 Control Implementation Tiers

Controls are implemented across three tiers:

**(a) Administrative Controls** -- Policies, procedures, governance structures, training, and personnel security measures documented in this WISP and subordinate policies.

**(b) Technical Controls** -- Automated enforcement mechanisms within the Perennia AI platform, including:
- Fernet field-level encryption for Restricted data (`EncryptionService`)
- Row-Level Security (RLS) tenant isolation at the database layer
- JWT RS256 token-based authentication with blacklist enforcement
- SOC 2 audit middleware for comprehensive API request logging
- Automated compliance scanning (daily at 02:15 UTC)
- Automated data retention enforcement (daily at 03:00 UTC)
- Anomaly detection with risk-score-based escalation
- WORM triggers preventing ad-hoc deletion of audit trails
- CSRF middleware with defined bypass protocols

**(c) Physical Controls** -- Infrastructure security provided by Railway (SOC 2 certified) for hosting, with US-based data residency for mortgage data compliance.

---

## 7. Data Classification & Handling

**SOC 2 Criteria:** C1, P1, P2, P3, P4, P7

### 7.1 Classification Levels

All data processed, stored, or transmitted by Perennia AI systems shall be classified into one of the following levels, as defined in the Data Classification Policy:

| Classification Level | Description | Examples |
|---|---|---|
| **Public** | Information approved for unrestricted distribution. No harm from unauthorized disclosure. | Marketing materials, public API documentation, published rate sheets |
| **Internal** | Business information not intended for public distribution. Limited harm from unauthorized disclosure. | Pipeline metrics, organization settings, internal reports, system configuration (non-credential) |
| **Confidential** | Sensitive business information whose unauthorized disclosure could cause significant harm. | Loan application details, borrower contact information, pricing data, internal communications |
| **Restricted** | Highly sensitive information subject to regulatory requirements. Unauthorized disclosure could cause severe harm. | Social Security Numbers, bank account numbers, credit scores, tax returns, income documentation, credit card numbers |

### 7.2 PII Field Inventory

Perennia AI maintains an authoritative inventory of thirty (30) PII fields in the data classification registry (`soc2_compliance/constants.py:PII_FIELDS`). This inventory includes, but is not limited to:

- Social Security Numbers, Tax IDs, Employer Identification Numbers
- Bank account numbers, routing numbers, credit card numbers
- Dates of birth, driver's license numbers, passport numbers
- Credit scores, income data, employment information
- Phone numbers, email addresses, physical addresses

The PII field inventory is re-seeded weekly by the automated scheduler and verified during daily compliance scans. New PII fields must be registered in the inventory and classified before implementation in production systems.

### 7.3 Handling Requirements by Classification Level

| Requirement | Public | Internal | Confidential | Restricted |
|---|---|---|---|---|
| Encryption at rest | Optional | Optional | Recommended | **Required** (Fernet) |
| Encryption in transit | TLS 1.2+ | TLS 1.2+ | TLS 1.2+ | TLS 1.2+ |
| Access logging | Not required | Required | Required | Required (PII flag) |
| Access control | Open | Role-based | Role-based + need-to-know | Role-based + need-to-know + audit |
| Data masking in logs | Not required | Not required | Recommended | **Required** |
| Retention period | Indefinite | Per policy | Per policy | Per regulation (see Section 7.4) |
| Disposal method | Standard deletion | Standard deletion | Secure deletion | Secure deletion with audit trail |
| Backup encryption | Not required | Recommended | Required | **Required** |

### 7.4 Regulatory Retention Requirements

As defined in the Data Retention Policy, the following retention periods apply:

| Data Category | Retention Period | Regulatory Basis |
|---|---|---|
| Audit logs | 2 years (730 days) | SOC 2 |
| Access logs | 2 years (730 days) | SOC 2 |
| Security incidents | 3 years (1,095 days) | SOC 2 / GLBA |
| Change records | 2 years (730 days) | SOC 2 |
| Compliance checks | 2 years (730 days) | SOC 2 |
| PII data | 3 years (1,095 days) | CCPA / GLBA |
| Loan data | 5 years (1,825 days) | TRID / RESPA |
| Financial records | 7 years (2,555 days) | IRS / GLBA |

Retention is enforced automatically by the `RetentionService` at 03:00 UTC daily. Records are archived to the `soc2_retention_archive` table before deletion. WORM triggers prevent ad-hoc deletion of audit trails outside the automated retention process.

### 7.5 Data Subject Rights

In accordance with CCPA, GLBA, and other applicable privacy regulations:

**(a)** Data subjects may request access to their personal information held by Perennia AI.

**(b)** Data subjects may request deletion of their personal information, subject to regulatory retention requirements. Deletion requests shall be processed within thirty (30) days.

**(c)** Deletion of loan records and financial data subject to TRID, RESPA, or IRS retention requirements may be deferred until the applicable retention period has expired, with written notice to the requestor.

**(d)** The Data Protection Officer shall manage all data subject access requests and maintain a log of requests and dispositions.

---

## 8. Access Control & Authentication

**SOC 2 Criteria:** CC6.1, CC6.2, CC6.3, CC6.4, CC6.5, CC6.6, CC6.7, CC6.8

### 8.1 Principles

All access to Perennia AI systems and data shall be governed by the following principles, as detailed in the Access Control Policy:

**(a) Least Privilege** -- Users and systems shall be granted the minimum level of access necessary to perform their authorized functions.

**(b) Need-to-Know** -- Access to Confidential and Restricted data shall be limited to individuals with a demonstrated business need.

**(c) Separation of Duties** -- Critical functions shall be divided among multiple individuals to prevent unauthorized actions by a single person.

**(d) Defense in Depth** -- Multiple layers of access controls shall be implemented so that the failure of a single control does not result in unauthorized access.

### 8.2 Authentication Standards

| Control | Requirement |
|---|---|
| Authentication method | JWT RS256 token-based authentication |
| Password minimum length | 12 characters |
| Password complexity | Uppercase, lowercase, digit, and special character required |
| Password expiration | 90 days |
| Password history | Last 12 passwords may not be reused |
| Multi-factor authentication | Required for all administrative access |
| Account lockout threshold | 5 failed attempts |
| Account lockout duration | 30 minutes |
| Session timeout | 30 minutes of inactivity (configurable via `SOC2_SESSION_TIMEOUT_MINUTES`) |
| Token blacklist | Maintained for revoked tokens; checked on every authentication |

### 8.3 Authorization Model

Perennia AI implements role-based access control (RBAC) with the following principal roles:

| Role | Access Level | Administrative Privileges |
|---|---|---|
| Platform Admin | Full platform access across all tenants | User management, system configuration, security administration |
| Site Admin | Full access within assigned organization | Organization user management, configuration |
| Loan Officer | Access to own pipeline and assigned data | Loan management, borrower communication |
| Processor | Access to assigned loans for processing | Loan processing, document management |
| Read-Only | View access to authorized data | Reporting, dashboard viewing |

### 8.4 Tenant Isolation

Row-Level Security (RLS) is enforced at the database layer to ensure that each organization's data is isolated from all other organizations. The `get_db()` function applies tenant context to every database session, and all queries are automatically scoped to the authenticated user's organization.

### 8.5 API Key Management

- API keys are stored as cryptographic hashes in the `soc2_api_key_registry` table; plaintext keys are never persisted.
- All API keys must have defined access scopes and expiration dates.
- Revoked keys are logged with the reason for revocation and the identity of the revoking user.
- API key usage is subject to the same audit logging as interactive user sessions.

### 8.6 Anomaly Detection

The platform implements automated login anomaly detection:

| Risk Score | Action |
|---|---|
| Less than 40 | Normal -- access granted, event logged |
| 40-59 | Anomalous -- access granted, event flagged for review |
| 60-79 | High risk -- access granted, security incident auto-created |
| 80 or above | Critical -- access granted, high-severity incident auto-created, immediate notification to Security Officer |

Risk scores are calculated based on factors including new IP addresses, new devices, geographic anomalies, and temporal patterns.

### 8.7 Provisioning and Deprovisioning

**(a) Provisioning** -- New accounts are created by an authorized administrator. Users must set a compliant password and enroll in MFA before accessing Confidential or Restricted data.

**(b) Access Reviews** -- All active accounts and their permissions are reviewed quarterly by the Platform Admin and Security Team.

**(c) Deprovisioning** -- Upon termination of the access relationship (employment termination, contract end, role change), the following actions are taken within one (1) business day:
- User account disabled
- All active sessions terminated
- All API keys revoked
- Access removal logged in the audit trail

---

## 9. Encryption Standards

**SOC 2 Criteria:** CC5.1, CC6.1, C1, PI1

### 9.1 Encryption at Rest

| Data Classification | Encryption Requirement | Method |
|---|---|---|
| Restricted | Mandatory | Fernet symmetric encryption (AES-128-CBC with HMAC-SHA256) applied at the field level via `EncryptionService` |
| Confidential | Recommended | AES-256 or equivalent where technically feasible |
| Internal | Optional | Database-level encryption where available |
| Public | Not required | N/A |

Fernet field-level encryption is applied to all PII columns identified in the data classification registry. Encryption keys are managed securely and stored as encrypted environment variables in Railway's credential management system.

### 9.2 Encryption in Transit

All data transmitted between clients and the Perennia AI platform, between platform components, and between the platform and third-party services shall be encrypted using TLS 1.2 or higher. Plaintext transmission of any data classified as Internal or above is prohibited.

| Communication Path | Minimum TLS Version | Certificate Management |
|---|---|---|
| Client to API (`api.perenniaai.com`) | TLS 1.2 | Managed by Railway (auto-renewal) |
| Client to frontend (`app.perenniaai.com`) | TLS 1.2 | Managed by Railway (auto-renewal) |
| API to PostgreSQL | TLS 1.2 | Railway internal certificates |
| API to third-party services | TLS 1.2 | Vendor-managed certificates |
| Internal service communication | TLS 1.2 | Railway internal network |

### 9.3 Encryption Key Management

**(a)** Encryption keys shall not be stored in source code, configuration files, or unencrypted storage.

**(b)** All encryption keys and API credentials are stored as encrypted environment variables in Railway's secure credential store.

**(c)** Key rotation shall be performed at least annually or immediately upon suspicion of compromise.

**(d)** Access to encryption keys is limited to the Security Officer and authorized Engineering personnel.

**(e)** Key access events are logged in the audit trail.

### 9.4 Cryptographic Standards

| Use Case | Algorithm | Key Length |
|---|---|---|
| Field-level encryption (PII) | Fernet (AES-128-CBC + HMAC-SHA256) | 256-bit key |
| Authentication tokens | RS256 (RSA-SHA256) | 2048-bit minimum |
| Password hashing | bcrypt | Cost factor 12 |
| Data in transit | TLS 1.2+ (AES-GCM preferred) | 128-bit minimum |
| API key hashing | SHA-256 | N/A (hash-only storage) |

---

## 10. Incident Response Overview

**SOC 2 Criteria:** CC7.1, CC7.2, CC7.3, CC7.4, CC7.5, P6

### 10.1 Incident Response Program

Perennia AI maintains a formal incident response program as detailed in the Incident Response Policy. This section provides the governance-level overview; operational procedures are defined in the subordinate policy.

### 10.2 Incident Categories

The following categories of security events are within the scope of the incident response program:

- Unauthorized access to systems or data
- Data breaches involving PII or Restricted data
- Malware infections or phishing attacks
- Insider threat activity
- Denial of service attacks
- Data loss or corruption
- Configuration errors with security implications
- Vulnerability exploitation
- Policy violations

### 10.3 Severity Classification and Response Times

| Severity | Definition | Response Time | Escalation Path |
|---|---|---|---|
| **Critical** | Active data breach, widespread system compromise, or imminent threat to Restricted data | 1 hour | Immediate notification to CEO, CTO, Security Officer |
| **High** | Confirmed unauthorized access, significant vulnerability exploitation, or system integrity compromise | 4 hours | Security Officer, Engineering Lead |
| **Medium** | Policy violation, failed attack attempt, or minor security weakness identified | 24 hours | Security team |
| **Low** | Informational security event, low-impact policy deviation | 72 hours | Logged for review |

### 10.4 Incident Lifecycle

All security incidents shall progress through the following lifecycle stages, each documented in the `soc2_security_incident` table with timestamped status transitions:

1. **Detection** -- Automated detection via anomaly detection, compliance scanning, or manual report by personnel.
2. **Triage** -- Classification by category and severity; assignment of Incident Commander.
3. **Containment** -- Immediate actions to limit the impact (session termination, IP blocking, credential revocation).
4. **Investigation** -- Root cause analysis to determine the scope, attack vector, and affected assets.
5. **Remediation** -- Fix the underlying vulnerability and implement corrective controls.
6. **Recovery** -- Restore normal operations and verify system integrity.
7. **Post-Mortem** -- Document lessons learned and preventive measures within five (5) business days of resolution.
8. **Closure** -- Incident closed after post-mortem completion and verification of preventive measures.

### 10.5 Breach Notification

In the event of a data breach involving personally identifiable information:

**(a)** Affected individuals shall be notified within seventy-two (72) hours of breach confirmation, as required by applicable state breach notification laws.

**(b)** Regulatory authorities shall be notified in accordance with GLBA and applicable state requirements.

**(c)** The Data Protection Officer shall coordinate all breach notification activities, including content review, notification logistics, and regulatory filings.

**(d)** A written breach report shall be prepared and retained for a minimum of three (3) years.

### 10.6 Automated Escalation

The platform implements automated escalation based on anomaly detection risk scores:

- Login anomaly with risk score of 60 or above: Security incident auto-created at Medium severity.
- Login anomaly with risk score of 80 or above: Security incident auto-created at High severity.
- Overdue Critical and High severity incidents: Flagged by the daily compliance scan at 02:15 UTC.

---

## 11. Business Continuity & Disaster Recovery

**SOC 2 Criteria:** A1.1, A1.2, A1.3

### 11.1 Business Continuity Commitment

Perennia AI is committed to maintaining the availability and resilience of its platform services. The disaster recovery program, detailed in the Disaster Recovery Policy, ensures that business-critical operations can be restored within defined objectives following a disruptive event.

### 11.2 Recovery Objectives

| Metric | Target | Description |
|---|---|---|
| **Recovery Time Objective (RTO)** | 4 hours | Maximum acceptable duration of service disruption |
| **Recovery Point Objective (RPO)** | 1 hour | Maximum acceptable data loss measured in time |

### 11.3 Infrastructure Resilience

| Component | Resilience Measure | Provider |
|---|---|---|
| Application server | Stateless containers with instant rollback to previous deployment | Railway |
| PostgreSQL database | Automated daily backups with 7-day retention | Railway |
| Source code | Git repository with full version history | GitHub |
| Environment configuration | Encrypted storage with current-state preservation | Railway |
| Audit logs | Database storage with real-time SIEM forwarding | DataDog |

### 11.4 Recovery Procedures

The Disaster Recovery Policy defines three recovery scenarios:

**(a) Database Recovery** -- Restore from the latest clean Railway backup, verify data integrity via compliance scan, and re-run pending migrations.

**(b) Application Recovery** -- Roll back to the last known-good deployment via Railway, verify the health endpoint, and confirm audit logging is active.

**(c) Complete Infrastructure Recovery** -- Provision a new Railway project, restore the database from backup, configure environment variables, deploy the application, run a full compliance scan, and verify all integrations.

### 11.5 Communication During Disruptions

| Condition | Notification | Timeline |
|---|---|---|
| Service disruption detected | Engineering on-call team | Immediate |
| Outage exceeding 30 minutes | Affected customers | Within 1 hour |
| Post-incident | All stakeholders | Written report within 48 hours |

### 11.6 Testing and Validation

| Test Type | Frequency | Responsible Party |
|---|---|---|
| Backup restoration test | Quarterly | Engineering Team |
| Failover drill | Semi-annual | Engineering Team |
| Full disaster recovery exercise | Annual | Engineering + Security Teams |

---

## 12. Vendor & Third-Party Risk Management

**SOC 2 Criteria:** CC9.1, CC9.2

### 12.1 Vendor Risk Management Program

Perennia AI maintains a formal vendor risk management program, detailed in the Vendor Management Policy, to assess and monitor the security posture of all third-party service providers that access, process, or store Company data.

### 12.2 Vendor Registry

All third-party vendors and service providers are registered in the `soc2_vendor_registry` table with the following attributes:

- Vendor name, category, and contact information
- Data access level (full, limited, metadata, none)
- SOC 2 Type II certification status
- Risk level assessment (Low, Medium, High)
- Data processing agreement (DPA) status
- Review schedule based on risk level

### 12.3 Current Vendor Inventory

| Vendor | Category | Data Access | SOC 2 Status | Risk Level |
|---|---|---|---|---|
| Railway | Infrastructure (hosting) | Full | Certified | Low |
| SendGrid | Communication (email) | Limited | Certified | Low |
| DataDog | Monitoring (observability) | Metadata | Certified | Low |
| Telnyx | Telephony (voice, SMS) | Limited | Certified | Medium |
| Twilio | Telephony (AI voice) | Limited | Certified | Medium |
| Vapi | AI telephony | Limited | Review Pending | Medium |
| OpenAI | AI services (LLM) | Content | Certified | Medium |
| Salesforce | CRM integration | Full | Certified | Low |

### 12.4 Vendor Assessment Requirements

Before granting any vendor access to Perennia AI data, the following assessments must be completed:

**(a)** SOC 2 Type II certification is required for all vendors with data access classified as "Full" or "Limited." Vendors without current SOC 2 certification must undergo an enhanced security assessment and are classified as Medium or High risk.

**(b)** A Data Processing Agreement (DPA) must be executed before any data access is granted. The DPA shall address data handling, security requirements, breach notification obligations, and data deletion upon contract termination.

**(c)** Data residency compliance must be verified. Mortgage data must reside within the United States.

**(d)** Incident notification procedures must be defined, with vendors required to notify Perennia AI of security incidents affecting Company data within the timeframes specified in the DPA.

### 12.5 Vendor Risk Classification and Review Schedule

| Risk Level | Criteria | Review Frequency |
|---|---|---|
| **Low** | SOC 2 certified, limited or metadata data access | Annual |
| **Medium** | Pending SOC 2 certification, or sensitive data access | Semi-annual |
| **High** | No SOC 2 certification with data access, or full access without DPA | Quarterly |

### 12.6 Vendor Lifecycle Management

**(a) Onboarding** -- Security questionnaire, risk assessment, DPA execution, credential configuration (encrypted environment variables), access scope definition, and vendor registry entry.

**(b) Ongoing Monitoring** -- Risk-based review per the schedule above, SOC 2 certification renewal tracking, and incident monitoring.

**(c) Offboarding** -- Access revocation, confirmation of data deletion, credential rotation for shared systems, and vendor registry update.

---

## 13. Employee Security Responsibilities

**SOC 2 Criteria:** CC1.1, CC1.4, P1

### 13.1 General Responsibilities

All personnel (employees, contractors, and temporary workers) with access to Perennia AI information systems shall:

**(a)** Read, understand, and acknowledge this WISP and all applicable subordinate security policies upon hire or engagement, and annually thereafter.

**(b)** Protect authentication credentials (passwords, API keys, MFA tokens) from unauthorized disclosure. Credentials shall not be shared, written down in plaintext, or stored in unencrypted files.

**(c)** Use Perennia AI systems and data solely for authorized business purposes.

**(d)** Report suspected or confirmed security incidents, policy violations, and vulnerabilities to the Security Officer promptly and without fear of retaliation.

**(e)** Complete all required security awareness training within established timelines (see Section 14).

**(f)** Lock workstations and mobile devices when unattended.

**(g)** Follow the change management process for all modifications to production systems (see Change Management Policy).

**(h)** Cooperate with security investigations, audits, and access reviews.

### 13.2 Role-Specific Responsibilities

#### Administrators (Platform Admin, Site Admin)

- Perform quarterly access reviews for all users within their scope.
- Ensure timely deprovisioning of accounts for terminated personnel.
- Review and approve privilege escalation requests.
- Monitor anomalous activity alerts and take appropriate action.

#### Engineers and Developers

- Follow secure coding practices and conduct security-focused code reviews.
- Ensure all changes follow the Change Management Policy, including peer review and testing.
- Report and remediate security vulnerabilities discovered during development.
- Maintain encryption implementation and key management practices.

#### Loan Officers and Processors

- Access borrower PII and loan data only for authorized loan processing purposes.
- Verify borrower identity before disclosing sensitive information.
- Comply with GLBA, TRID, and RESPA requirements in all borrower interactions.
- Report unusual borrower activity or suspected fraud.

### 13.3 Acceptable Use

**(a)** Company systems shall be used for authorized business purposes. Limited personal use is permitted provided it does not violate any security policy, introduce risk to Company systems, or interfere with job performance.

**(b)** The following activities are expressly prohibited:
- Attempting to circumvent access controls or security mechanisms.
- Accessing, modifying, or deleting data without authorization.
- Installing unauthorized software on Company systems.
- Transmitting Confidential or Restricted data via unapproved channels.
- Using Company systems for illegal activities.

### 13.4 Consequences of Non-Compliance

Violations of this WISP or subordinate security policies may result in disciplinary action up to and including termination of employment or contract, and referral to law enforcement where warranted.

---

## 14. Security Awareness Training Requirements

**SOC 2 Criteria:** CC1.4, CC2.2

### 14.1 Training Program Overview

Perennia AI maintains a security awareness training program to ensure all personnel understand their security responsibilities and can identify and respond to security threats.

### 14.2 Training Requirements

| Training Type | Audience | Frequency | Completion Deadline |
|---|---|---|---|
| New hire security orientation | All new personnel | Upon hire | Within 30 calendar days of start date |
| Annual security awareness refresher | All personnel | Annual | Within 30 calendar days of anniversary |
| Phishing awareness training | All personnel with email access | Semi-annual | Within 14 calendar days of assignment |
| Secure development training | Engineers and developers | Annual | Within 30 calendar days of assignment |
| Incident response training | Security team, engineering leads | Quarterly | Within 7 calendar days of drill |
| Privacy and data handling (GLBA/CCPA) | All personnel handling PII | Annual | Within 30 calendar days of assignment |
| Administrative access training | Platform Admins, Site Admins | Upon role assignment | Before administrative access is granted |

### 14.3 Training Content

Security awareness training shall cover, at a minimum:

- Overview of this WISP and subordinate security policies
- Password hygiene and multi-factor authentication
- Phishing and social engineering recognition
- Data classification and handling procedures
- Incident reporting procedures
- Acceptable use requirements
- Physical security awareness
- Regulatory obligations specific to the mortgage industry (GLBA, TRID, RESPA, CCPA)

### 14.4 Training Records

**(a)** Completion records shall be maintained for all training activities, including participant name, training type, completion date, and assessment results.

**(b)** Training completion rates shall be reported to the Security Officer monthly and to the CTO quarterly.

**(c)** Personnel who fail to complete required training within the specified deadline shall have their system access restricted until training is completed.

**(d)** Training records shall be retained for a minimum of two (2) years in accordance with the Data Retention Policy.

---

## 15. Compliance Monitoring & Audit

**SOC 2 Criteria:** CC4.1, CC4.2, P8

### 15.1 Continuous Monitoring

Perennia AI implements continuous automated monitoring to detect control failures, policy violations, and security anomalies:

| Monitoring Activity | Frequency | Mechanism |
|---|---|---|
| API request audit logging | Real-time | SOC 2 audit middleware logs all requests to `soc2_audit_log` |
| Compliance scanning | Daily at 02:15 UTC | Automated `ComplianceScanner` checks 15+ control points |
| Data retention enforcement | Daily at 03:00 UTC | `RetentionService` archives and purges expired records |
| Data classification verification | Weekly | Automated re-seed of `soc2_data_classification` table |
| Anomalous login detection | Real-time | Risk-score-based anomaly detection on every login |
| Session management | Real-time | Active session tracking in `soc2_active_session` table |
| Unapproved change detection | Daily | Automated scan of `soc2_change_record` table |

### 15.2 Audit Trail Integrity

**(a)** All audit records are stored in dedicated SOC 2 audit tables with WORM (Write-Once Read-Many) protections to prevent unauthorized modification or deletion.

**(b)** The automated retention service is the only mechanism authorized to remove audit records, and only after the applicable retention period has expired.

**(c)** Audit records include, at a minimum: timestamp, user identity, action performed, resource affected, IP address, and outcome (success/failure).

**(d)** High-severity events are forwarded in real-time to DataDog SIEM for centralized monitoring and alerting.

### 15.3 Internal Audit Activities

| Audit Activity | Frequency | Responsible Party | Output |
|---|---|---|---|
| Access review (all accounts and permissions) | Quarterly | Platform Admin, Security Team | Access review report |
| API key audit | Quarterly | Security Team | Key inventory and revocation report |
| Anomaly detection review | Weekly | Security Team | Anomaly summary report |
| Change management audit | Monthly | Security Team | Unapproved change report |
| Data classification completeness | Quarterly | Security Team | PII field coverage report |
| Retention enforcement verification | Monthly | Platform Admin | Retention status report |
| Vendor risk reassessment | Per risk-level schedule | Security Team | Vendor assessment report |
| Open incident review | Weekly | Security Team | Incident status report |
| Post-mortem compliance | Monthly | Engineering Lead | Post-mortem completion report |

### 15.4 External Audit

**(a)** Perennia AI shall engage a qualified independent auditor to conduct an annual SOC 2 Type II audit covering all Trust Service Criteria in scope.

**(b)** The Security Officer shall coordinate audit activities, including evidence collection, auditor access, and management response to findings.

**(c)** Audit findings shall be tracked to resolution, with remediation plans approved by the CTO.

**(d)** The SOC 2 Type II report shall be made available to customers and prospects under non-disclosure agreement upon request.

### 15.5 Compliance Dashboard Metrics

The following metrics shall be tracked and reported:

| Metric | Target | Reporting Frequency |
|---|---|---|
| Compliance scan pass rate | 100% | Daily (automated) |
| Open security incidents | Zero Critical/High for more than SLA | Weekly |
| Access review completion | 100% on schedule | Quarterly |
| Training completion rate | 100% within deadlines | Monthly |
| Encryption coverage (Restricted fields) | 100% | Weekly (automated) |
| Data classification coverage | 100% of PII fields registered | Weekly (automated) |
| Vendor DPA coverage | 100% of data-access vendors | Quarterly |

---

## 16. Policy Review & Update Schedule

**SOC 2 Criteria:** CC1.1, CC4.2

### 16.1 Review Cadence

This WISP and all subordinate security policies shall be reviewed on a semi-annual basis (every six months), or more frequently when triggered by the events described in Section 16.3.

### 16.2 Review Schedule

| Document | Current Version Date | Next Scheduled Review | Owner |
|---|---|---|---|
| Written Information Security Program (this document) | 2026-03-27 | 2026-09-27 | Security Officer |
| Information Security Policy | 2026-02-25 | 2026-08-25 | Security Team |
| Access Control Policy | 2026-02-25 | 2026-08-25 | Security Team |
| Incident Response Policy | 2026-02-25 | 2026-08-25 | Security Team |
| Change Management Policy | 2026-02-25 | 2026-08-25 | Engineering Team |
| Data Classification Policy | 2026-02-25 | 2026-08-25 | Security Team |
| Data Retention Policy | 2026-02-25 | 2026-08-25 | Security Team |
| Vendor Management Policy | 2026-02-25 | 2026-08-25 | Security Team |
| Disaster Recovery Policy | 2026-02-25 | 2026-08-25 | Engineering Team |

### 16.3 Triggers for Unscheduled Review

The following events shall trigger an unscheduled review of this WISP or relevant subordinate policies:

- A significant security incident (Critical or High severity)
- Material changes to the regulatory environment (new laws, amended regulations, updated guidance)
- Significant changes to the Perennia AI platform architecture, technology stack, or infrastructure
- Findings from SOC 2 audits or other external assessments
- Introduction of new categories of sensitive data or new third-party integrations
- Organizational changes (mergers, acquisitions, restructuring)
- Lessons learned from incident post-mortems requiring policy updates

### 16.4 Review Process

**(a)** The Security Officer shall initiate the review cycle by distributing current policy versions to all policy owners at least thirty (30) days before the scheduled review date.

**(b)** Policy owners shall assess their respective policies for accuracy, completeness, and alignment with current operations, threats, and regulatory requirements.

**(c)** Proposed changes shall be documented with justification and submitted to the Security Officer for consolidation.

**(d)** Material changes to this WISP require approval from the CEO and CTO.

**(e)** Material changes to subordinate policies require approval from the Security Officer and the policy owner.

**(f)** Approved changes shall be communicated to all affected personnel, and the version history shall be updated.

### 16.5 Version History

| Version | Date | Author | Description |
|---|---|---|---|
| 1.0 | 2026-03-27 | Security Officer | Initial publication |

---

## 17. Approval & Signatures

This Written Information Security Program has been reviewed and approved by the undersigned officers of Perennia AI, Inc. By signing below, each officer acknowledges their understanding of and commitment to the security program established herein.

---

### Chief Executive Officer

| Field | Value |
|---|---|
| **Name** | __________________________________ |
| **Title** | Chief Executive Officer |
| **Signature** | __________________________________ |
| **Date** | ______ / ______ / __________ |

---

### Chief Technology Officer

| Field | Value |
|---|---|
| **Name** | __________________________________ |
| **Title** | Chief Technology Officer |
| **Signature** | __________________________________ |
| **Date** | ______ / ______ / __________ |

---

### Security Officer

| Field | Value |
|---|---|
| **Name** | __________________________________ |
| **Title** | Security Officer |
| **Signature** | __________________________________ |
| **Date** | ______ / ______ / __________ |

---

*This document constitutes the governing information security program for Perennia AI, Inc. All subordinate policies referenced herein are incorporated by reference and shall be maintained in accordance with the review schedule established in Section 16. Questions regarding this program should be directed to the Security Officer.*

---

**Document Classification: Confidential**
**Perennia AI, Inc. -- All Rights Reserved**
