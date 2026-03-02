# Perennia Smart Scheduler: 90-Day Action Plan (Q2 2026)
**Strategic Roadmap to Enterprise Market Leadership**

---

## EXECUTIVE BRIEF

**Objective**: Position Perennia Smart Scheduler as the scheduling backbone for enterprise mortgage lenders (100+ LOs) by Q4 2026.

**Current State**:
- ✅ Solid architectural foundation (audit-ready, multi-tenant, AI-integrated)
- ❌ Missing 3 critical integrations (LOS, Salesforce, email archiving)
- ❌ No compliance certifications (SOC 2, WCAG)

**Target Outcome**:
- Close 5-10 enterprise mortgage customers ($200K-$500K ACV)
- Establish "Calendly for Mortgage" market positioning
- Achieve SOC 2 Type II certification
- Ship LOS integration (Encompass MVP)

---

## PHASE 1: IMMEDIATE (WEEKS 1-12, Q2 2026)

### Sprint 1-2: Encompass LOS Integration (Weeks 1-4)

**Goal**: Real-time appraisal scheduling sync (ServiceLink pattern)

**Deliverables**:
1. **Encompass API Client Library**
   - OAuth 2.0 token refresh flow (30-min expiration)
   - Appraisal order query endpoint (`GET /loans/{loanId}/appraisals`)
   - Task creation endpoint (`POST /loans/{loanId}/tasks`)
   - Estimated effort: 15 dev days

2. **Webhook Listener**
   - Inbound: Encompass webhook when appraisal needed
   - Parse: Loan ID, property address, borrower contact
   - Trigger: Create appointment link + email to borrower
   - Estimated effort: 10 dev days

3. **Database Extensions**
   - Add columns to Appointment: `encompass_loan_id`, `appraisal_order_id`
   - Add columns to AppointmentType: `associated_los_entity` (appraisal/title/closing)
   - Migration: Estimated 3 dev days

4. **Configuration UI**
   - Admin panel: Enable/disable Encompass sync
   - Store OAuth credentials (encrypted in database)
   - Test connection button
   - Estimated effort: 8 dev days

**Total Sprint Effort**: 36 dev days
**Dependencies**: Access to Encompass sandbox; OAuth credentials
**Success Metric**: Appraisal scheduled in Encompass → borrower receives booking link within 60 seconds

**Owner**: Backend team lead + LOS integration expert
**Stakeholder Validation**: Talk to Encompass customers (reference calls)

---

### Sprint 3: FINRA Compliance — Email Archiving (Weeks 5-8)

**Goal**: RFC 5322 email archiving + audit trail for regulatory exams

**Option A: Global Relay Integration** (Recommended)
- Cost: $3K-5K annually per lender customer
- Compliance pre-certified (FINRA/SEC)
- Estimated effort: 20 dev days

**Option B: In-House Email Archive** (Lower cost, higher risk)
- Cost: $0 (internal storage)
- Compliance: Requires 17a-4 certification
- Estimated effort: 40 dev days + audit

**Deliverables (Option A)**:
1. **Global Relay API Integration**
   - Store API credentials (encrypted)
   - Archive all `AppointmentReminder` email sends
   - Archive all borrower confirmation emails
   - Estimated effort: 12 dev days

2. **Audit Trail Extension**
   - Link each email to `SchedulerAuditLog` entry
   - Retention policy: 3 years (FINRA 4511)
   - Estimated effort: 5 dev days

3. **Compliance Reporting**
   - Admin panel: Archive status dashboard
   - Export: "Appts archived between [date] and [date]"
   - Estimated effort: 8 dev days

4. **Documentation**
   - FINRA 4511 compliance guide (internal)
   - Customer compliance checklist
   - Estimated effort: 3 dev days

**Total Sprint Effort**: 28 dev days
**Dependencies**: Global Relay partnership (legal + sales)
**Success Metric**: Archive audit passes compliance review; 3-year retention verified

**Owner**: Compliance officer + backend team
**Stakeholder Validation**: Talk to compliance consultants (ACA, STRATMOR)

---

### Sprint 4: Salesforce Lead + Task Sync (Weeks 9-12)

**Goal**: Appointment booked → SF Lead/Task auto-created; live sync

**Deliverables**:
1. **Salesforce API Integration**
   - OAuth 2.0 token refresh (non-expiring)
   - Lead create: (`POST /services/data/v57.0/sobjects/Lead`)
   - Task create: (`POST /services/data/v57.0/sobjects/Task`)
   - Estimated effort: 15 dev days

2. **Bi-Directional Sync**
   - Perennia → SF: Appointment created → Task auto-created
   - SF → Perennia: Lead updated → pre-fill in Perennia (future)
   - Estimated effort: 12 dev days

3. **Configuration UI**
   - Org admin: Connect Salesforce (OAuth flow)
   - Map: Appointment fields → SF Lead/Task fields
   - Test sync (dry-run)
   - Estimated effort: 10 dev days

4. **Error Handling**
   - Retry queue for failed syncs (3 retries, backoff)
   - Admin alert: "SF sync failed for 5 appts"
   - Estimated effort: 8 dev days

**Total Sprint Effort**: 45 dev days
**Dependencies**: SF sandbox; org with SF + Perennia
**Success Metric**: 100 Perennia appts created → 100 SF Tasks created within 30 seconds

**Owner**: Backend team + Salesforce integration expert
**Stakeholder Validation**: Demo with SF-heavy customer (e.g., Guaranteed Rate, LoanDepot)

---

### Sprint 5 (Parallel): WCAG 2.1 AA Accessibility Audit (Weeks 1-12)

**Goal**: Ensure booking link + admin UI meet AA compliance

**Deliverables**:
1. **Third-Party Audit** (External vendor)
   - Full accessibility scan: booking link, admin panel, borrower portal
   - Report: Issues + remediation cost estimates
   - Estimated cost: $5K-8K
   - Timeline: 2-3 weeks

2. **Remediation Roadmap** (Internal)
   - Priority 1: Booking link (borrower-facing; highest impact)
   - Priority 2: Admin panel (internal; lower regulatory risk)
   - Estimated effort: 30 dev days (frontend)

3. **Validation** (Re-audit)
   - Re-scan post-remediation
   - Generate AA compliance report (for customer transparency)
   - Estimated cost: $2K-3K

**Total Phase 1 Effort**:
- Dev days: 36 + 28 + 45 + 30 = **139 dev days** (~7 FTE weeks or 2 FTE months)
- External costs: $5K (audit) + $3K (re-audit) + $3K-5K (Global Relay first year) = **$11K-13K**

**Phase 1 Success Metrics**:
- ✅ Encompass appraisal bookings live (1+ customer)
- ✅ Global Relay archiving configured + compliant
- ✅ Salesforce sync working (100% success rate)
- ✅ WCAG AA audit passed (booking link)
- ✅ Customer wins: 1-2 enterprise pilots with Encompass + SF

---

## PHASE 2: GROWTH (WEEKS 13-24, Q3 2026)

### Sprint 6-7: Territory + Expertise Routing UI (Weeks 13-20)

**Goal**: Visual rules builder; no-code territory/expertise definition

**Current State**:
- ✅ Schema supports `required_expertise`, `loan_amounts_min/max`
- ❌ Admin UI: Rules are JSON-only (no visual builder)

**Deliverables**:
1. **Visual Routing Rules Builder**
   - Drag-and-drop condition builder
   - Pre-built templates: "Territory", "Expertise", "Loan Amount", "Lead Source"
   - Test rule: "Run simulation against past 100 appts"
   - Estimated effort: 40 dev days (frontend + backend)

2. **Territory Management**
   - Org admin: Define territories (ZIP code ranges, county, state)
   - Assign LOs to territories
   - Routing rule: "Lead in Miami → route to Miami team only"
   - Estimated effort: 20 dev days

3. **Expertise Inventory**
   - Admin: List certifications (VA, USDA, jumbo, FHA, portfolio, etc.)
   - LO profile: Check boxes for held certifications
   - Routing rule: "Commercial inquiry → commercial-certified LOs only"
   - Estimated effort: 15 dev days

4. **Performance Dashboard**
   - Show rule effectiveness: "85% to primary LOs, 15% to fallback"
   - Conversion rates by routing strategy
   - Estimated effort: 12 dev days

**Total Sprint Effort**: 87 dev days
**Owner**: Product + frontend + backend team
**Stakeholder Validation**: Beta with 2-3 enterprise customers

---

### Sprint 8: SMS Two-Way Confirmation (Weeks 21-24)

**Goal**: SMS reminder + confirmation (reduce email fatigue)

**Deliverables**:
1. **SMS Reminder Integration**
   - Use existing Telnyx API (already integrated)
   - Send 24h reminder: "Your appt with [LO] on [date] at [time]. Reply YES to confirm."
   - Estimated effort: 10 dev days

2. **SMS Reply Handler**
   - Webhook: Incoming SMS (Telnyx) → parse reply
   - Logic: "YES" = confirmed; "NO" = rejection; "?" = help
   - Update appointment status automatically
   - Estimated effort: 12 dev days

3. **Fallback Logic**
   - If SMS fails → send email confirmation instead
   - Track: SMS sent, SMS delivered, SMS replied (new metric)
   - Estimated effort: 8 dev days

4. **Configuration**
   - Admin UI: Enable SMS for appointment types (e.g., only for confirmations, not initial bookings)
   - Template customization: "Your appointment with {lo_name} on {date}..."
   - Estimated effort: 8 dev days

**Total Sprint Effort**: 38 dev days
**Owner**: Communications team + backend
**Success Metric**: 80%+ SMS delivery rate; 40%+ reply rate (industry average: 35%)

---

### Sprint 9 (Parallel): SOC 2 Type II Audit Kickoff (Weeks 13-24)

**Goal**: Start audit; target report issuance by Q4 2026

**Deliverables**:
1. **Vendor Selection** (Week 13-14)
   - RFP to Big 4 (Deloitte, EY, Grant Thornton) or niche SOC 2 firm (Vanta, Drata)
   - Cost estimate: $40K-60K (3-month audit)
   - Timeline: 12-16 weeks (start week 13 → report by week 24-28)

2. **Evidence Collection** (Weeks 15-24)
   - Security policies: access control, data encryption, incident response
   - Testing: penetration tests, vulnerability scans
   - Documentation: backup/disaster recovery, change management
   - Estimated internal effort: 40 dev days + 20 ops days

3. **Gap Closure**
   - Implement missing controls (e.g., DLP, MFA enforcement)
   - Estimated effort: 20 dev days

**Total Phase 2 Effort**:
- Dev days: 87 + 38 + 40 (SOC 2 support) = **165 dev days** (~2.5 FTE months)
- External costs: $40K-60K (SOC 2 audit)

**Phase 2 Success Metrics**:
- ✅ Territory/expertise routing shipped (2+ customers using)
- ✅ SMS two-way confirmation live (50%+ usage)
- ✅ SOC 2 audit in progress (report expected Q4)
- ✅ Customer wins: 2-3 additional enterprise logos

---

## PHASE 3: DIFFERENTIATION (Q4 2026+)

### Sprint 10-11: Fallback Cascading + Instant Offer (Weeks 25-32)

**Goal**: Chili Piper Instant Booker equivalent; borrower gets alternatives if primary LO booked

**Deliverables**:
1. **Cascading Logic**
   - Check primary LO availability
   - If booked: fetch 2 alternate LOs (same territory/expertise)
   - Show borrower: Primary + 2 alternates with times
   - Borrower picks one; appointment created
   - Estimated effort: 50 dev days

2. **Smart Fallback Selection**
   - Algo: Rank by geography proximity + expertise match + LO availability
   - ML-informed: Use historical conversion data
   - Estimated effort: 30 dev days

3. **UI/UX**
   - Borrower experience: "Your preferred LO isn't available. Here are alternatives..."
   - Calendar display: Show all 3 options side-by-side
   - Estimated effort: 20 dev days

**Total Sprint Effort**: 100 dev days
**Owner**: Product + ML + frontend
**Expected ROI**: 10-15% conversion increase (industry data)

---

### Sprint 12: Referral Partner Portal (Weeks 33-40)

**Goal**: Realtors, title companies, appraisers book time self-serve

**Deliverables**:
1. **Partner Portal**
   - Login (API key or SSO)
   - View available times (borrower name not shown; only address)
   - Book appointment for third-party referral
   - Estimated effort: 35 dev days

2. **Permissions Model**
   - Org admin: Invite partners (email list)
   - Partner types: Realtor, title company, appraiser, inspector
   - Restrictions: Can't view other partner bookings
   - Estimated effort: 15 dev days

3. **Integration**
   - Partner books → creates appointment + notifies borrower + LO
   - Auto-sync partner contact info to appointment
   - Estimated effort: 12 dev days

**Total Sprint Effort**: 62 dev days
**Owner**: Product + frontend + backend
**Expected Impact**: 20-30% of appointments could come from partners (sticky ecosystem)

---

### Sprint 13 (Ongoing): Predictive "Best Time" ML Model (Weeks 41-52)

**Goal**: ML model recommends best time slot based on borrower profile + LO history

**Deliverables**:
1. **Data Pipeline**
   - Historical data: 1000+ appointments + outcomes (booked, attended, converted)
   - Features: borrower attributes (loan amount, credit score, source), LO specialization, time of day, day of week
   - Target: conversion (booked appt → loan close)
   - Estimated effort: 30 dev days (data eng)

2. **ML Model Training**
   - Model: XGBoost or neural network (time series friendly)
   - Prediction: "Recommend slot [date time] — 89% conversion probability"
   - Training cadence: Weekly retrain on new data
   - Estimated effort: 40 dev days (ML engineer)

3. **UI Integration**
   - Borrower sees "Best Times" section in booking link
   - "Monday 10am (89% likelihood you'll close)" vs. generic slots
   - Estimated effort: 15 dev days (frontend)

4. **A/B Testing**
   - Measure: Does "Best Times" increase booking → conversion rate?
   - Expected lift: 5-10%
   - Estimated effort: 10 dev days

**Total Sprint Effort**: 95 dev days
**Owner**: ML/data science team
**Expected ROI**: Industry-first for mortgage; major differentiator

---

## RESOURCE ALLOCATION

### Team Composition (90-Day Sprint, Q2 2026)

**Backend** (6 FTE)
- 2x LOS integration engineers (Encompass API)
- 1x Salesforce integration engineer (SF OAuth/API)
- 1x Compliance engineer (Global Relay, archiving)
- 1x DevOps/infra (deployments, monitoring)
- 1x Senior architect (oversight, design review)

**Frontend** (4 FTE)
- 2x React engineers (rules builder, SMS UI, partner portal)
- 1x Accessibility specialist (WCAG remediation)
- 1x UI/UX designer

**Data/ML** (1 FTE, part-time)
- 1x Data engineer (Phase 2 onwards; model training)

**Compliance/PM** (2 FTE)
- 1x Compliance officer (SOC 2 audit, archiving)
- 1x Product manager (roadmap, prioritization, customer feedback)

**QA/Testing** (2 FTE)
- 1x Integration testing (Encompass, Salesforce, Global Relay)
- 1x Accessibility testing (WCAG)

**Total**: ~15 FTE for 12 weeks (can phase in/out as needed)

---

## GO-TO-MARKET STRATEGY

### Customer Acquisition Playbook

**Tier 1: Enterprise Mortgage (100-500 LOs, $200M+ volume)**
- Targets: Guaranteed Rate, LoanDepot, CrossCountry, NewRez, UWM (if acquired)
- Entry point: Replacing Calendly; LOS integration as must-have
- Sales motion: 6-9 month deal; $50K-100K ACV
- Approach: Direct sales + executive sponsorship

**Tier 2: Regional Mortgage (25-100 LOs, $50M-$200M volume)**
- Targets: Local mortgage companies, credit unions, portfolio lenders
- Entry point: SMB pricing; "All-in-one platform" story
- Sales motion: 2-4 month deal; $15K-40K ACV
- Approach: Inside sales + partner channel

**Tier 3: Mortgage Brokers (5-25 LOs, $20M-$100M volume)**
- Targets: Independent brokers, small chains
- Entry point: Product-led growth (free tier)
- Sales motion: 1-2 month deal; $5K-15K ACV
- Approach: Self-serve + email nurture

### Partnership Strategy

**LOS Vendors** (Encompass, Calyx, MeridianLink)
- Joint go-to-market: Co-market Perennia + LOS integration
- App marketplace: List Perennia as certified integration
- Revenue share: 10-15% of customer ACV

**Referral Ecosystem** (Blend, ServiceLink, Better.com)
- Co-sell: Bundle Perennia scheduler with appraisal/closing tools
- Referral fee: $5K-10K per deal

**Consulting Partners** (ACA, STRATMOR, MBS Highway)
- Train-the-trainer: Educate consultants on Perennia deployment
- Reference customers: Consultants recommend to 20+ lender clients

---

## SUCCESS METRICS (90-Day Milestone, EOQ 2026)

| Metric | Target | How to Measure |
|--------|--------|-----------------|
| **Customer Acquisition** | 2-3 enterprise pilots | Sales pipeline |
| **Feature Completeness** | Encompass + SF + Archiving shipped | Deployment to test customers |
| **Compliance** | WCAG AA audit passed; SOC 2 in progress | Third-party reports |
| **Product Quality** | <5 critical bugs in Phase 1 features | QA + bug tracking |
| **Team Velocity** | 139 dev days delivered | Sprint burndown |
| **Customer Satisfaction** | NPS 40+; zero implementation blockers | Post-launch survey |

---

## RISKS & MITIGATION

| Risk | Impact | Mitigation |
|------|--------|-----------|
| **Encompass API instability** | Schedule delays | Engage Ellie Mae for sandbox access early; build comprehensive error handling |
| **Salesforce org complexity** | Integration delays (custom fields, workflows) | Document all SF org types; test with 3-5 orgs pre-release |
| **SOC 2 audit findings** | Remediation burden | Start audit week 13 (not week 1) to have time for fixes |
| **Competing scheduler launches** | Market share loss | Accelerate Phase 1; emphasize mortgage-native differentiation |
| **Customer feature expectations** | Scope creep | Lock requirements by week 2; communicate cut-line clearly |
| **Developer availability** | Staffing shortfall | Cross-train 1-2 engineers on each critical path; plan backfill early |

---

## BUDGET SUMMARY (Q2-Q4 2026)

| Category | Cost | Notes |
|----------|------|-------|
| **Personnel** (15 FTE × 12 weeks) | $450K | Fully loaded ($300K/yr salary + benefits + overhead) |
| **WCAG Audit** | $5K | Third-party accessibility audit |
| **WCAG Remediation** | $3K | Contractor support if needed |
| **Global Relay (first year)** | $5K | Archiving service; first 5 customers |
| **SOC 2 Audit** | $50K | Big 4 firm; Q3-Q4 2026 |
| **Encompass/SF Sandbox Access** | $2K | API access + test data |
| **Infrastructure/Testing** | $10K | Load testing, staging environment |
| **Total** | **$525K** | ~2.5x investment for enterprise market entry |

**ROI Projection**:
- Year 1 revenue: 3-5 customers × $75K ACV = $225K-375K
- Year 2 revenue: 10-15 customers (including SMB tier) = $800K-$1.2M
- Payback period: 8-14 months

---

## APPROVAL & SIGN-OFF

**Stakeholders**:
- [ ] **CEO/Board**: Budget allocation ($525K), strategic priority
- [ ] **CTO**: Technical feasibility, architecture review
- [ ] **VP Product**: Customer feedback integration, feature prioritization
- [ ] **VP Sales**: Go-to-market timing, sales enablement
- [ ] **Compliance Officer**: Regulatory requirements validation

**Next Steps**:
1. **Week 1 (This Week)**: Kickoff planning meeting; assign team leads
2. **Week 2**: Environment setup (Encompass sandbox, SF org, Global Relay setup)
3. **Week 3**: Sprint 1 engineering starts; customer outreach for pilots
4. **Week 8**: First integration demo to pilot customers
5. **Week 12**: Phase 1 launch (Encompass + SF + Archiving + WCAG)

---

**Document Version**: 1.0
**Date**: March 2026
**Status**: Ready for Executive Review
**Next Review**: Weekly sprint planning
