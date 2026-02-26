# Vendor Management Policy

**SOC 2 Criteria:** CC9 (Risk Mitigation)
**Last Reviewed:** 2026-02-25
**Next Review:** 2026-08-25
**Owner:** Security Team

## 1. Purpose

Manage risks associated with third-party vendors and service providers that access, process, or store Perennia AI data.

## 2. Scope

All third-party vendors, SaaS providers, and service integrations used by the Perennia AI platform.

## 3. Policy Statements

### 3.1 Vendor Registry
All vendors tracked in `soc2_vendor_registry` table with:
- Vendor name and category
- Data access level (full, limited, metadata, none)
- SOC 2 certification status
- Risk level assessment
- Review schedule

### 3.2 Current Vendors

| Vendor | Category | Data Access | SOC 2 Status | Risk |
|---|---|---|---|---|
| Railway | Infrastructure | Full | Certified | Low |
| SendGrid | Communication | Limited | Certified | Low |
| DataDog | Monitoring | Metadata | Certified | Low |
| Telnyx | Telephony | Limited | Certified | Medium |
| Twilio | Telephony | Limited | Certified | Medium |
| Vapi | AI Telephony | Limited | Review Pending | Medium |
| OpenAI | AI Services | Content | Certified | Medium |
| Salesforce | CRM Integration | Full | Certified | Low |

### 3.3 Vendor Assessment Criteria
- SOC 2 Type II certification (required for vendors with data access)
- Data processing agreement (DPA) in place
- Incident notification procedures defined
- Data residency compliance (US-only for mortgage data)

### 3.4 Vendor Risk Levels
| Level | Criteria | Review Frequency |
|---|---|---|
| Low | SOC 2 certified, limited data access | Annual |
| Medium | Pending certification or sensitive data access | Semi-annual |
| High | No certification, full data access | Quarterly |

### 3.5 Vendor Onboarding
- Security assessment before contract signing
- DPA execution required before data access granted
- API credentials stored in encrypted environment variables
- Access scoped to minimum necessary permissions

## 4. Procedures

1. New vendor: complete security questionnaire and risk assessment.
2. Contract: include DPA, incident notification, and data deletion clauses.
3. Onboarding: configure credentials, scope access, register in vendor registry.
4. Review: assess vendor compliance per risk-based schedule.
5. Offboarding: revoke access, confirm data deletion, update registry.

## 5. Review Schedule

| Review Type | Frequency | Responsible Party |
|---|---|---|
| Policy review | Semi-annual | Security Team |
| Vendor registry audit | Quarterly | Security Team |
| Vendor risk reassessment | Per risk level schedule | Security Team |
