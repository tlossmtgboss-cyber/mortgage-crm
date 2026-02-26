# Data Classification Policy

**SOC 2 Criteria:** C1 (Confidentiality)
**Last Reviewed:** 2026-02-25
**Next Review:** 2026-08-25
**Owner:** Security Team

## 1. Purpose

Classify all data processed by Perennia AI to ensure appropriate protection levels are applied based on sensitivity.

## 2. Scope

All data stored, processed, or transmitted by the Perennia AI platform, including database records, API payloads, logs, and backups.

## 3. Policy Statements

### 3.1 Classification Levels

| Level | Description | Examples |
|---|---|---|
| **Public** | No sensitivity, freely shareable | Marketing content, public API docs |
| **Internal** | Business data, not for public | Loan pipeline metrics, org settings |
| **Confidential** | Sensitive business data | Loan details, contact info, pricing |
| **Restricted** | PII, financial data, regulated | SSN, bank accounts, credit scores, income |

### 3.2 PII Fields (30 fields tracked)
SSN, tax ID, EIN, bank account numbers, routing numbers, credit card numbers, date of birth, income data, credit scores, driver's license, passport, phone numbers, email addresses, home/mailing addresses, employer information.

Full authoritative list maintained in `soc2_compliance/constants.py:PII_FIELDS`.

### 3.3 Protection Requirements

| Level | Encryption at Rest | Encryption in Transit | Access Logging | Retention |
|---|---|---|---|---|
| Public | Optional | TLS | No | Indefinite |
| Internal | Optional | TLS | Yes | Per policy |
| Confidential | Recommended | TLS | Yes | Per policy |
| Restricted | **Required** (Fernet) | TLS | Yes + PII flag | Per regulation |

### 3.4 Data Classification Registry
- All sensitive columns registered in `soc2_data_classification` table.
- Weekly re-seed via automated scheduler ensures coverage.
- Classification coverage checked by daily compliance scan.

## 4. Procedures

1. New data fields classified before implementation.
2. PII fields added to `PII_FIELDS` constant and `soc2_data_classification` table.
3. Restricted data encrypted using `EncryptionService` before storage.
4. Quarterly review of classification registry for completeness.

## 5. Review Schedule

| Review Type | Frequency | Responsible Party |
|---|---|---|
| Policy review | Semi-annual | Security Team |
| Classification audit | Weekly (automated) | SOC 2 Scheduler |
| PII field review | Quarterly | Security Team |
