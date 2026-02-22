# Feature Focus & Deprecation Strategy

## The Core Problem

Perennia AI tries to be 12 products at once: CRM, LOS portal, AI agent platform, telephony suite, video conferencing, accounting system, content marketing hub, e-signature system, borrower portal, microsite builder, avatar studio, and document AI. Each of these is a company-sized problem. The result is that nothing achieves the polish users expect from a $99/seat SaaS product.

This isn't a technical problem — it's a strategic one. The decision takes 1 day. The discipline takes months.

## The Framework: Core vs. Differentiating vs. Non-Core

### 🟢 CORE (Keep + Polish)

These are features every mortgage CRM must have. Without them, Perennia isn't viable:

| Feature | Why Core | Polish Target |
|---------|----------|---------------|
| Contact/Lead Management | Table stakes CRM | Fast, searchable, no bugs |
| Pipeline Management | LO daily workflow | <3 clicks to check/update pipeline |
| Loan Tracking | Mortgage-specific requirement | Accurate, real-time status |
| Basic Email/SMS | Communication is CRM core | Reliable delivery, templates |
| Reporting/Dashboard | Manager requirement | Clear, fast, exportable |
| User/Team Management | Multi-user requirement | RBAC working correctly |
| Salesforce Sync | Existing integration | Reliable, audited |
| Encompass Integration | #1 enterprise sales blocker | See encompass-integration.md |

### 🔵 DIFFERENTIATING (Keep + Invest — This Is the Moat)

These are features no competitor matches. They're why someone picks Perennia over Shape:

| Feature | Why Differentiating | Investment Target |
|---------|--------------------|-------------------|
| AI Agent Fleet (20 agents) | No competitor has this depth | Prove ROI with metrics |
| Borrower Portal Suite | Most comprehensive in market | Polish UX, add i18n |
| PURL System | Personalization at scale | Integrate with portal |
| AI-Powered Content Gen | Replaces Surefire's library | Add compliance review |
| Pipeline Intelligence | AI-driven insights | Prove accuracy |

### 🔴 NON-CORE (Freeze or Deprecate)

These features consume development bandwidth without providing competitive advantage. Each has a mature third-party alternative:

| Feature | Replace With | Action |
|---------|-------------|--------|
| Video Conferencing | Zoom/Google Meet integration | Freeze, add meeting link field |
| Accounting Module | QuickBooks/Xero integration | Freeze, no new development |
| E-Signature System | DocuSign/HelloSign integration | Freeze, integrate existing tools |
| Avatar Studio | Remove or deprioritize | Freeze indefinitely |
| Microsite Builder | Remove or deprioritize | Freeze indefinitely |
| Power Dialer | Keep basic version, don't expand | Maintenance only |

## Making the Decision

### Step 1: Classify Every Feature (1 hour)

Go through the route files and classify each feature area:

```
Core: Keep, fix bugs, polish UX
Differentiating: Keep, invest, measure ROI
Non-Core: Freeze code, no new features, maintenance fixes only
Deprecated: Remove from UI, keep data, delete code in 90 days
```

### Step 2: Communicate the Freeze (1 hour)

For frozen features:
- Remove from marketing/demo materials
- Add "Coming Soon" or "Beta" labels in the UI where appropriate
- Stop accepting feature requests for these areas
- Only fix critical bugs (data loss, security)

### Step 3: Redirect Engineering Time (Ongoing)

Every hour NOT spent on accounting/video/avatars is an hour spent on:
- Test coverage for core features
- Encompass integration
- AI agent reliability
- Portal UX polish
- Accessibility fixes

### Step 4: Replace with Integrations (Quarter 2)

For non-core features that users actually need, build lightweight integrations:

```python
# Instead of a full accounting module, add:
# - "Open in QuickBooks" link on financial pages
# - QuickBooks OAuth connection in settings
# - Loan closing data export to QuickBooks format

# Instead of video conferencing:
# - Zoom meeting link field on contacts/leads
# - "Schedule Zoom Meeting" button that opens Zoom's scheduler
# - Meeting URL auto-populated in calendar events
```

## The 70% Deletion Test

The audit asks: "If you had to delete 70% of features tomorrow and keep only what makes Perennia uniquely valuable, what would survive?"

Answer: **AI agents + Portal suite + Pipeline CRM.**

Everything else is either table-stakes CRM (needed but not differentiating) or non-core (replaceable by integrations).

## Metrics to Track

After focusing:

| Metric | Baseline | Target (90 days) |
|--------|----------|-------------------|
| Core features with >80% test coverage | 0% | 50% |
| Average bug fix time (core features) | ? | <24 hours |
| LO daily workflow clicks (pipeline check) | ? | <5 clicks |
| AI agent reliability (successful completions) | ? | >95% |
| Portal NPS (borrower satisfaction) | ? | >50 |
| Enterprise demo-to-close rate | 0% | Track first 10 |

## Validation Checklist

- [ ] Every feature classified as Core / Differentiating / Non-Core / Deprecated
- [ ] Non-core features frozen (no active development branches)
- [ ] Engineering backlog reorganized — 80% of tickets are Core or Differentiating
- [ ] Marketing materials reflect focused value proposition
- [ ] Integration plan exists for each non-core feature that users need
- [ ] Weekly time tracking shows <20% of dev hours on non-core maintenance
