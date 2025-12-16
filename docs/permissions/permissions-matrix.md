# Perennia AI - Stage-Based Permissions Matrix

## Overview

The permissions system is organized around **three core loan stages**, enabling:
- **Subscription-based licensing**: Users/organizations can subscribe to specific stages
- **Role-based access control**: Within each stage, permissions vary by role
- **Granular feature control**: Each feature within a stage can be enabled/disabled

---

## Loan Stages

| Stage | Description | Target Users | Subscription Tier |
|-------|-------------|--------------|-------------------|
| **Lead** | Lead management, intake, pre-qualification | Lead generators, SDRs, Inside Sales | Starter |
| **Active Loan** | Loan processing, underwriting, closing | Loan Officers, Processors, Underwriters | Professional |
| **Portfolio** | Client retention, servicing, MUM (Mortgages Under Management) | Account Managers, Retention Specialists | Enterprise |

---

## Stage: LEAD

### Features & Permissions

| Feature | Full Access | Standard LO | Read Only | Processing Team |
|---------|-------------|-------------|-----------|-----------------|
| **Lead Intake** |||||
| View all leads | ✅ | ❌ (team only) | ✅ | ✅ |
| Create leads | ✅ | ✅ | ❌ | ❌ |
| Edit leads | ✅ | ✅ (own/assigned) | ❌ | ✅ |
| Delete leads | ✅ | ❌ | ❌ | ❌ |
| Import leads (bulk) | ✅ | ❌ | ❌ | ❌ |
| Export leads | ✅ | ✅ | ❌ | ✅ |
| **Lead Assignment** |||||
| Assign leads | ✅ | ❌ | ❌ | ❌ |
| Reassign leads | ✅ | ❌ | ❌ | ❌ |
| View lead pool | ✅ | ✅ | ✅ | ✅ |
| Claim from pool | ✅ | ✅ | ❌ | ❌ |
| **Lead Communication** |||||
| Send emails | ✅ | ✅ | ❌ | ✅ |
| Send SMS | ✅ | ✅ | ❌ | ✅ |
| Make calls (dialer) | ✅ | ✅ | ❌ | ❌ |
| View communication history | ✅ | ✅ | ✅ | ✅ |
| **Lead Qualification** |||||
| Run credit checks | ✅ | ✅ | ❌ | ❌ |
| Pre-qualify leads | ✅ | ✅ | ❌ | ❌ |
| Update lead status | ✅ | ✅ | ❌ | ✅ |
| Add notes | ✅ | ✅ | ✅ | ✅ |
| **Lead Analytics** |||||
| View lead metrics | ✅ | ✅ (own) | ✅ | ✅ |
| View conversion rates | ✅ | ✅ (own) | ✅ | ❌ |
| View source performance | ✅ | ❌ | ❌ | ❌ |
| **Lead Automation** |||||
| Configure workflows | ✅ | ❌ | ❌ | ❌ |
| Manage drip campaigns | ✅ | ❌ | ❌ | ❌ |
| Set auto-assignment rules | ✅ | ❌ | ❌ | ❌ |

### Lead Stage Permission Keys

```
lead.intake.view_all
lead.intake.view_team
lead.intake.view_assigned
lead.intake.create
lead.intake.edit_all
lead.intake.edit_own
lead.intake.delete
lead.intake.import
lead.intake.export

lead.assignment.assign
lead.assignment.reassign
lead.assignment.view_pool
lead.assignment.claim

lead.communication.email
lead.communication.sms
lead.communication.call
lead.communication.view_history

lead.qualification.credit_check
lead.qualification.pre_qualify
lead.qualification.update_status
lead.qualification.add_notes

lead.analytics.view_metrics
lead.analytics.view_conversion
lead.analytics.view_sources

lead.automation.workflows
lead.automation.campaigns
lead.automation.auto_assignment
```

---

## Stage: ACTIVE LOAN

### Features & Permissions

| Feature | Full Access | Standard LO | Read Only | Processing Team |
|---------|-------------|-------------|-----------|-----------------|
| **Loan Pipeline** |||||
| View all loans | ✅ | ❌ (team only) | ✅ | ✅ |
| Create loan files | ✅ | ✅ | ❌ | ✅ |
| Edit loan details | ✅ | ✅ (own) | ❌ | ✅ |
| Delete loans | ✅ | ❌ | ❌ | ❌ |
| **Loan Processing** |||||
| Upload documents | ✅ | ✅ | ❌ | ✅ |
| Request documents | ✅ | ✅ | ❌ | ✅ |
| Verify documents | ✅ | ❌ | ❌ | ✅ |
| Order services (appraisal, title) | ✅ | ✅ | ❌ | ✅ |
| **Underwriting** |||||
| Submit to underwriting | ✅ | ✅ | ❌ | ✅ |
| View conditions | ✅ | ✅ | ✅ | ✅ |
| Clear conditions | ✅ | ❌ | ❌ | ✅ |
| Approve loans | ✅ | ❌ | ❌ | ❌ |
| Deny loans | ✅ | ❌ | ❌ | ❌ |
| Suspend loans | ✅ | ❌ | ❌ | ❌ |
| **Closing** |||||
| Generate disclosures | ✅ | ✅ | ❌ | ✅ |
| Schedule closing | ✅ | ✅ | ❌ | ✅ |
| Clear to close | ✅ | ❌ | ❌ | ✅ |
| Record funding | ✅ | ❌ | ❌ | ✅ |
| **Rate Lock** |||||
| View rates | ✅ | ✅ | ✅ | ✅ |
| Lock rates | ✅ | ✅ | ❌ | ❌ |
| Extend locks | ✅ | ✅ | ❌ | ❌ |
| Re-lock rates | ✅ | ❌ | ❌ | ❌ |
| **Loan Analytics** |||||
| View pipeline metrics | ✅ | ✅ (own) | ✅ | ✅ |
| View pull-through rates | ✅ | ✅ (own) | ❌ | ❌ |
| View cycle times | ✅ | ✅ | ✅ | ✅ |
| **Compliance** |||||
| Run compliance checks | ✅ | ❌ | ❌ | ✅ |
| View audit logs | ✅ | ❌ | ❌ | ❌ |
| Generate compliance reports | ✅ | ❌ | ❌ | ❌ |

### Active Loan Permission Keys

```
loan.pipeline.view_all
loan.pipeline.view_team
loan.pipeline.view_assigned
loan.pipeline.create
loan.pipeline.edit_all
loan.pipeline.edit_own
loan.pipeline.delete

loan.processing.upload_docs
loan.processing.request_docs
loan.processing.verify_docs
loan.processing.order_services

loan.underwriting.submit
loan.underwriting.view_conditions
loan.underwriting.clear_conditions
loan.underwriting.approve
loan.underwriting.deny
loan.underwriting.suspend

loan.closing.generate_disclosures
loan.closing.schedule
loan.closing.clear_to_close
loan.closing.record_funding

loan.rate_lock.view
loan.rate_lock.lock
loan.rate_lock.extend
loan.rate_lock.relock

loan.analytics.view_pipeline
loan.analytics.view_pull_through
loan.analytics.view_cycle_times

loan.compliance.run_checks
loan.compliance.view_audit
loan.compliance.generate_reports
```

---

## Stage: PORTFOLIO

### Features & Permissions

| Feature | Full Access | Standard LO | Read Only | Processing Team |
|---------|-------------|-------------|-----------|-----------------|
| **Client Management** |||||
| View all clients | ✅ | ❌ (own) | ✅ | ✅ |
| Edit client info | ✅ | ✅ (own) | ❌ | ❌ |
| Add client notes | ✅ | ✅ | ✅ | ✅ |
| View loan history | ✅ | ✅ | ✅ | ✅ |
| **MUM (Mortgages Under Management)** |||||
| View MUM dashboard | ✅ | ✅ | ✅ | ❌ |
| View equity positions | ✅ | ✅ | ✅ | ❌ |
| View rate watch alerts | ✅ | ✅ | ✅ | ❌ |
| Send refinance offers | ✅ | ✅ | ❌ | ❌ |
| **Retention Campaigns** |||||
| Create campaigns | ✅ | ❌ | ❌ | ❌ |
| Execute campaigns | ✅ | ✅ | ❌ | ❌ |
| View campaign results | ✅ | ✅ | ✅ | ❌ |
| **Anniversaries & Milestones** |||||
| View upcoming events | ✅ | ✅ | ✅ | ❌ |
| Send milestone communications | ✅ | ✅ | ❌ | ❌ |
| Configure auto-messages | ✅ | ❌ | ❌ | ❌ |
| **Referral Management** |||||
| View referral partners | ✅ | ✅ | ✅ | ❌ |
| Add referral partners | ✅ | ✅ | ❌ | ❌ |
| Track referral deals | ✅ | ✅ | ✅ | ❌ |
| Send referral thank-yous | ✅ | ✅ | ❌ | ❌ |
| **Portfolio Analytics** |||||
| View portfolio value | ✅ | ✅ (own) | ✅ | ❌ |
| View retention metrics | ✅ | ✅ (own) | ❌ | ❌ |
| View lifetime value | ✅ | ❌ | ❌ | ❌ |
| **Property Monitoring** |||||
| View property values | ✅ | ✅ | ✅ | ❌ |
| Set value alerts | ✅ | ✅ | ❌ | ❌ |
| View market trends | ✅ | ✅ | ✅ | ❌ |

### Portfolio Permission Keys

```
portfolio.clients.view_all
portfolio.clients.view_own
portfolio.clients.edit
portfolio.clients.add_notes
portfolio.clients.view_history

portfolio.mum.view_dashboard
portfolio.mum.view_equity
portfolio.mum.view_rate_watch
portfolio.mum.send_offers

portfolio.campaigns.create
portfolio.campaigns.execute
portfolio.campaigns.view_results

portfolio.milestones.view
portfolio.milestones.send_communications
portfolio.milestones.configure

portfolio.referrals.view
portfolio.referrals.add
portfolio.referrals.track
portfolio.referrals.send_thanks

portfolio.analytics.view_value
portfolio.analytics.view_retention
portfolio.analytics.view_ltv

portfolio.property.view_values
portfolio.property.set_alerts
portfolio.property.view_trends
```

---

## Cross-Stage Permissions (Always Available)

These permissions are not stage-specific and apply globally:

```
# Dashboard
dashboard.view
dashboard.customize
dashboard.widgets.add
dashboard.widgets.remove

# Profile
profile.view
profile.edit
profile.change_password
profile.notifications

# Team (if subscribed to team features)
team.view_members
team.view_performance
team.manage_members
team.manage_permissions

# Settings
settings.view
settings.edit_personal
settings.edit_company
settings.integrations

# AI Assistant
ai.chat
ai.tasks
ai.recommendations
ai.training

# Calendar & Scheduling
calendar.view
calendar.create_events
calendar.schedule_meetings

# Notifications
notifications.view
notifications.configure
notifications.email
notifications.sms
notifications.push
```

---

## Role Templates by Stage

### Lead Stage Templates

| Template | Description | Target Users |
|----------|-------------|--------------|
| `lead_admin` | Full lead management access | Sales Managers |
| `lead_officer` | Standard LO lead access | Loan Officers |
| `lead_sdr` | Lead intake and qualification | Sales Development Reps |
| `lead_readonly` | View-only lead access | Executives, Auditors |

### Active Loan Templates

| Template | Description | Target Users |
|----------|-------------|--------------|
| `loan_admin` | Full loan processing access | Branch Managers |
| `loan_officer` | Standard LO loan access | Loan Officers |
| `loan_processor` | Document and processing access | Processors |
| `loan_underwriter` | Underwriting decision access | Underwriters |
| `loan_closer` | Closing and funding access | Closers |
| `loan_readonly` | View-only loan access | Compliance, Auditors |

### Portfolio Templates

| Template | Description | Target Users |
|----------|-------------|--------------|
| `portfolio_admin` | Full portfolio management | Retention Managers |
| `portfolio_officer` | Client relationship access | Loan Officers |
| `portfolio_analyst` | Analytics and reporting | Business Analysts |
| `portfolio_readonly` | View-only portfolio access | Executives |

---

## Subscription Tiers

| Tier | Stages Included | Price Model |
|------|-----------------|-------------|
| **Starter** | Lead only | Per user/month |
| **Professional** | Lead + Active Loan | Per user/month |
| **Enterprise** | Lead + Active Loan + Portfolio | Per user/month |
| **Custom** | Any combination | Custom pricing |

### Feature Flags by Tier

```typescript
interface SubscriptionTier {
  id: string;
  name: string;
  stages: ('lead' | 'active_loan' | 'portfolio')[];
  features: {
    maxUsers: number;
    maxLeads: number;
    maxLoans: number;
    aiAssistant: boolean;
    advancedAnalytics: boolean;
    customWorkflows: boolean;
    apiAccess: boolean;
    whiteLabeling: boolean;
    dedicatedSupport: boolean;
  };
}
```

---

## Permission Resolution Order

1. **Subscription Check**: Does the user's subscription include this stage?
2. **Stage Enabled**: Is this stage enabled for the organization?
3. **Role Template**: What does the user's role template allow?
4. **Individual Overrides**: Are there specific permission overrides?
5. **Temporary Grants**: Are there time-limited permission grants?

```
Subscription → Stage → Role Template → Overrides → Temporary Grants
```

---

## Data Scoping

Each permission can have a scope that limits data visibility:

| Scope Level | Description | Example |
|-------------|-------------|---------|
| `all` | See all records | Admin sees all leads |
| `team` | See team records | Manager sees team's leads |
| `territory` | See territory records | Regional lead access |
| `branch` | See branch records | Branch-level access |
| `assigned` | See only assigned | LO sees own leads |
| `none` | No access | No visibility |

---

## Audit & Compliance

All permission changes are logged:

```typescript
interface PermissionAuditLog {
  id: string;
  timestamp: Date;
  userId: string;
  actorId: string;
  action: 'grant' | 'revoke' | 'modify' | 'template_apply';
  permissionKey: string;
  previousValue: boolean | null;
  newValue: boolean;
  reason?: string;
  expiresAt?: Date;
  ipAddress: string;
  userAgent: string;
}
```
