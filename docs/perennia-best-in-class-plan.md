# Perennia AI: The Path to Best-in-Class

A step-by-step plan to convert the current platform from "most ambitious mortgage CRM ever built" into "most reliable, most loved, most defensible mortgage platform on the market."

---

## Strategic Framing

The audit is correct: you have a Ferrari engine on a go-kart chassis. But the real risk isn't the chassis — it's that you spend the next six months building *more* Ferrari and never fix the chassis, and then Kastle or Marr Labs ships a reliable enough point solution that LOs stop caring about all-in-one.

The plan below is sequenced around three premises:

1. **The AI moat is real but only valuable if the platform stays up.** No LO will trust their pipeline to a CRM that drops connections at 50 concurrent users.
2. **Feature breadth without depth in the basics will lose.** BNTouch wins on 180 pre-built campaigns and a working digital 1003. You can have 22 agents and lose anyway.
3. **Distribution beats engineering after week 12.** Once the platform is stable, the bottleneck shifts to getting LOs onto it. Most of the work between months 4 and 12 should be GTM, not code.

---

## Phase 0 — Stop the Bleeding (Days 1–7)

These are the items where every additional day of delay creates concrete legal, financial, or customer-trust risk. Do them this week.

| # | Task | Owner | Effort |
|---|------|-------|--------|
| 0.1 | Bump Railway to `numReplicas: 2`, raise DB pool `max_overflow` to 20+, enable PgBouncer on the Postgres add-on | You | 1–2 hrs |
| 0.2 | Enable JWT audience validation (`verify_aud=True`) across all middleware; ship behind a feature flag for staged rollout | Backend | 1 day |
| 0.3 | Patch `middleware/pii_response_filter.py:259` — verify JWT signature before extracting role claim. This is the single most dangerous bug in the codebase: a forged JWT reads unmasked SSNs | Backend | 2 hrs |
| 0.4 | Make `DATA_ENCRYPTION_KEY` a hard requirement in production — fail startup if missing | Backend | 30 min |
| 0.5 | Fix the case-sensitive CSRF env check in `main.py:453` | Backend | 30 min |
| 0.6 | Replace the `pipeline360.io` support email in `ErrorBoundary` with `support@perenniaai.com` | Frontend | 5 min |
| 0.7 | Strip `console.log` statements from production builds (`vite-plugin-remove-console`) | Frontend | 1 hr |

**Exit criteria:** A senior security reviewer would no longer call any of these P0. You should be able to run `npm run build && grep -r "console.log" dist/` and get zero results.

---

## Phase 1 — Production-Grade Foundation (Weeks 2–8)

The goal of this phase is unromantic: make Perennia survive 500 concurrent users and a deploy without an outage.

### 1.1 Database & Migration Framework (Weeks 2–3)
- **Adopt Alembic.** Generate an initial baseline from the current schema, then convert the 20+ inline migration scripts into versioned Alembic revisions. Add `alembic upgrade head` to the deploy pipeline.
- **Add migration safety nets:** dry-run on a snapshot of prod before every deploy, automatic rollback on `alembic downgrade -1` if smoke tests fail.
- **Backfill soft deletes** on `Lead`, `Loan`, `BorrowerApplication`, `Activity`. A `deleted_at` column plus a query filter is enough — compliance and data recovery both depend on this.

### 1.2 Connection Pooling & Concurrency (Week 3)
- Move the Postgres add-on behind PgBouncer in transaction-pooling mode.
- Switch the FastAPI process model: `uvicorn` with `--workers $(nproc * 2 + 1)` behind a load balancer, not a single process.
- Set realistic SQLAlchemy pool sizes (`pool_size=10, max_overflow=20` per worker, with PgBouncer absorbing the spikes).

### 1.3 Token Budget & Rate Limit Correctness (Week 4)
- Move the per-org token budget out of in-memory and into Redis (`INCR` with TTL, atomic). This is the single change that lets you run more than one replica without the budgets multiplying.
- Same for the token blacklist — Redis-backed, with a hard startup failure if Redis is unreachable in production.
- Audit the 27 middleware layers. Drop the duplicates (`RequestLoggingMiddleware` vs `StructuredLoggingMiddleware`, `AuditMiddleware` vs `BreadcrumbAuditMiddleware`, the two rate limit middlewares). Document the ordering in code, not comments.

### 1.4 Load Testing in CI (Week 5)
- Add a Locust suite that simulates 200 concurrent LOs running typical workflows: pipeline view, calculator, Aria call, document upload.
- Run nightly against staging. Fail the build if p95 latency exceeds 800ms or error rate exceeds 0.5%.
- This is what catches the "we deployed something that quietly cut throughput in half" problem.

### 1.5 Observability (Weeks 6–8)
- Structured JSON logs everywhere (you have `StructuredLoggingMiddleware` — make it the only logger).
- Distributed tracing across LangGraph agent runs. Each agent invocation gets a trace ID that propagates through tool calls. When an LO complains "Aria gave me wrong numbers," you can replay the entire reasoning trace.
- Metrics: per-agent latency, per-tool error rate, hallucination verifier rejection rate, AI cost per loan. The last one is the metric that determines whether your pricing model survives scale.

**Exit criteria:** Locust at 500 concurrent users sustains 99.5% success. Deploys cause no measurable outage. You can answer "what did Aria do for loan #4821 last Tuesday?" by clicking a trace ID.

---

## Phase 2 — Frontend Surgery (Weeks 4–12, parallel)

Run this in parallel with Phase 1; different person, different codebase area.

### 2.1 Wire Up the Abandoned Refactor (Weeks 4–5)
The audit found that `frontend/src/routes/index.jsx` is a complete 732-line refactor of the App.jsx routing system using `MainLayout` and `withMainLayout()` — and it isn't imported anywhere. Whoever started this got 80% of the way there. Finish it.

Outcome: App.jsx drops from 4,836 lines to ~800. Three thousand lines of copy-pasted layout boilerplate disappear.

### 2.2 API Client Adoption (Weeks 5–10)
- Codemod the 304 files using raw `fetch()` to use `src/utils/api/client.js`.
- Add an ESLint rule that fails the build on any direct `fetch()` outside the client.
- Replace ad-hoc `useEffect` + `useState` data fetching with React Query, starting with the highest-traffic pages (Pipeline, Lead Detail, Loan Detail, CalculatorDashboard).

This is the single change that makes the app *feel* reliable. Right now 96% of API calls have no retry, no timeout, no centralized error handling — users see blank screens or stale data and have no idea why.

### 2.3 Route Guards (Week 8)
- Add a `<ProtectedRoute requiredRoles={[...]}>` wrapper. Apply it at the route definition level in `routes/index.jsx`, not inside each page.
- Add a 404 catch-all.
- Verify with a test: "Anonymous user navigates to `/admin/permissions` → 403 page, not blank screen, not data leak."

### 2.4 CalculatorDashboard Decomposition (Weeks 9–11)
6,847 lines of untested financial calculations is a lawsuit waiting to happen. Extract:
- `CalculatorService` (PITI, DTI, amortization, prepay scenarios) — pure functions, in `/services/calculator/`.
- 100% unit test coverage with reference values from a published mortgage textbook or Freddie Mac calculator.
- Reduce the page component to a thin UI layer that calls the service.

### 2.5 Dependency Hygiene (Week 12)
- Remove `axios` (unused).
- Remove `react-beautiful-dnd` (unmaintained); replace with `@dnd-kit/core` if drag-and-drop is needed.
- Pick one video SDK between Chime and LiveKit; remove the other.
- ARIA pass: get from 625 ARIA attributes in 1,198 files to full WCAG 2.1 AA on the 20 most-used pages.

**Exit criteria:** Zero raw `fetch()` calls outside the API client. App.jsx under 1,000 lines. CalculatorDashboard under 800 lines. 100% test coverage on financial calculation functions. WCAG audit passes on top pages.

---

## Phase 3 — Close Competitive Gaps (Weeks 9–20)

You can have the best AI in the industry and still lose to BNTouch because BNTouch ships a working borrower application and 180 marketing campaigns. Close the table-stakes gaps.

### 3.1 Digital 1003 / Borrower Point-of-Sale (Weeks 9–14)
You already built **Avery** (URLA voice agent) and the **URLA loan interview system**. The hard part is done. Wrap them in a borrower-facing web flow:
- Mobile-first, 7-step progressive 1003 with auto-save.
- Document upload (drive license, paystubs, W-2s) with Smart Docs OCR + classification.
- Co-borrower invitation flow.
- Verbal completion option ("don't want to type? Avery will call you").
- Direct ULAD push to BytePro on completion.

This is your single biggest table-stakes gap. Without it, every LO has to bolt on a separate POS (BeSmartee, Maxwell, Floify) and the all-in-one thesis dies.

### 3.2 Pre-Built Campaign Library (Weeks 12–18, ongoing)
Goal: 50 campaigns at launch, 100 by month 6, 200 by month 12.

Categories that matter:
- New lead nurture (purchase, refi, HELOC, jumbo, FHA, VA, USDA)
- Pre-approval expiration (30 / 14 / 7 / 1 day)
- Rate-watch alerts
- Post-close referral / review request
- Birthday / anniversary / closing anniversary
- Realtor partner co-marketing
- Past-client annual mortgage review
- Lost lead recovery

Each campaign: drip sequence (email + SMS), pre-written copy with merge fields, suggested cadence, branching logic on engagement. License a copywriter for two months — this is content work, not engineering work.

### 3.3 Realtor / Partner Portal (Weeks 16–20)
You built **Listing-Side Partner Updates**. Productize it as a full partner portal:
- Realtor logs in, sees all their buyers' loans in real time.
- Pre-approval letter generator the realtor can request without bothering the LO.
- Co-branded marketing (the realtor's photo + LO's photo on flyers).
- Lead-sharing tools (the realtor sends a buyer to the LO with one click).

Realtors drive 30%+ of LO pipeline. A great partner experience is a referral multiplier.

---

## Phase 4 — Compound the AI Moat (Weeks 16–32)

This is where you stop competing with Shape and BNTouch and start defining a new category. The audit is right that 60 agent roles with overlapping tools is sprawl — but the answer isn't "fewer agents," it's **fewer, deeper, irreplaceable agents**.

### 4.1 Agent Consolidation & Quality Bar (Weeks 16–20)
Collapse 60 agent roles into ~10 first-class agents with deep, high-quality tool integrations:

1. **Aria** — inbound receptionist (existing)
2. **Avery** — outbound URLA / data collection (existing)
3. **Pipeline Coach** — proactive next-best-action for each loan in pipeline
4. **Calculator Agent** — affordability, scenarios, rate-shopping
5. **Document Intelligence** — Smart Docs unified (existing)
6. **Compliance Sentry** — TRID, fair lending, TCPA, RESPA monitoring
7. **Email Inbox** — already built
8. **Talent Radar** — recruiting (already built)
9. **Opportunity Agent** — MUM (already built)
10. **Underwriter Copilot** — guideline RAG + scenario reasoning

Tool registry drops from 233 → ~120, deduped. Each tool gets a contract test that runs in CI.

### 4.2 The Memory Moat (Weeks 18–24)
You already started Aria's borrower memory system (Phase A merged in PR #45). Extend memory to all agent surfaces:
- **Persistent borrower memory** across calls, emails, SMS, portal sessions.
- **LO memory** — the platform learns each LO's style (do they always pitch a 15-year refi? Do they prefer email over SMS?).
- **Org-level memory** — shared institutional knowledge (Wisconsin VA loans run through this lender, the rate-lock desk closes at 4 PM).

This is the feature competitors cannot copy in 12 months. A voice agent that remembers what the borrower said three months ago is a different product than a voice agent that doesn't.

### 4.3 Underwriter Copilot (Weeks 22–28)
You already have the 5-agency guideline RAG. Productize it as an LO-facing agent that answers "Will my borrower qualify for this scenario?" with cited guideline excerpts and a confidence score. Zeitro charges $8/user/month for guideline search alone — this is a defensible feature.

### 4.4 Real-Time Decisioning (Weeks 26–32)
Combine Pipeline Coach + Compliance Sentry + Calculator into a real-time view: for every loan in pipeline, the platform shows "next best action," "compliance risk score," "predicted close probability," "recommended outreach." This is the dashboard LOs will open every morning.

---

## Phase 5 — Compliance & Trust Excellence (Ongoing)

This is the work that determines whether you survive your first lawsuit, your first SOC 2 audit, and your first enterprise procurement review.

### 5.1 TCPA & Voice Compliance (Weeks 6–10)
The Mortgage One class action set the precedent: $500–$1,500 per AI voice call without consent, retained 5+ years.

- Dedicated `voice_consent` table with: timestamp, consent language version, channel (verbal / written / e-sign), recording URL, retention policy.
- Pre-call DNC scrub remains blocking.
- Universal recording disclosure on every outbound call (Block 2 work — finish the LiveKit egress verification and ship).
- Quarterly compliance review with outside counsel.

### 5.2 SOC 2 Type II (Months 4–9)
You already have the config. Now enforce it:
- Password expiry, history, complexity — enforced at the auth layer.
- Request/response body audit logging — enabled in production (with PII scrubbing).
- Quarterly access reviews automated.
- Engage Vanta or Drata; budget 6–9 months to first Type II report.

Without SOC 2 Type II, the largest 50 mortgage shops in the country won't even take a sales call.

### 5.3 State-Level NMLS & Privacy (Ongoing)
- GLBA privacy notice delivery — Block 2 work.
- CCPA / CPRA / state-level privacy compliance — automated DSAR (data subject access request) flow.
- NMLS audit trail — ensure every loan has an immutable record of who touched what and when.

---

## Phase 6 — Distribution Engine (Weeks 20+)

You have zero enterprise customers. The audit is right that this is the single biggest existential risk after infrastructure.

### 6.1 First 10 LOs (Weeks 20–26)
- Hand-recruit 10 LOs from your network. Free for 6 months in exchange for weekly feedback calls.
- Goal: not revenue. Goal: 10 LOs who say "I would pay $200/month for this" unprompted.
- Instrument everything: which features they use daily, which they ignore, what they ask for that's missing.

### 6.2 First 100 LOs (Months 7–10)
- Pricing: $149/LO/month for the platform, $0.10/min for AI voice usage. Comes in under Surefire ($499) but premium to Shape ($99) — justified by AI feature density.
- Distribution channels: AIME chapters, NAMB local events, mortgage podcast sponsorships (The Loan Officer Podcast, Mortgage Marketing Animals).
- Content: LO-facing blog and YouTube channel. Tim publishes weekly "I built this in Perennia in 30 minutes" demos. This is the channel that converts.
- Hire one part-time LO-turned-customer-success person at month 7. They own onboarding for the first 100.

### 6.3 First Enterprise Customer (Months 9–12)
Target: a 50-LO independent mortgage banker, not a top-50 lender. Get them on, get a logo, get a case study with measurable ROI ("X% lift in pull-through, $Y saved per loan in compliance ops").

### 6.4 Brand & Positioning
Don't position as "another CRM." Position as **"the AI operating system for mortgage."** Every piece of marketing reinforces: this is not a CRM with AI bolted on. Competitors with comparable feature breadth do not exist.

---

## Phase 7 — Enterprise Readiness (Months 8–12)

Once you have 100 LOs, the question becomes: can you sell to a 500-person mortgage banker?

### 7.1 LOS Depth Beyond BytePro
- Add Encompass / ICE Mortgage Technology integration. This is the single most-requested integration from larger shops.
- Add LendingPad, Calyx Point.
- Build the integration layer as plugin architecture so the next LOS takes 4 weeks instead of 4 months.

### 7.2 Single Sign-On & Provisioning
- SAML SSO (Okta, Azure AD).
- SCIM provisioning.
- Custom RBAC per org (your 8-role default isn't enough for a 500-person shop with regional managers, branch managers, processors per branch, etc.).

### 7.3 White-Labeling
Big mortgage bankers want their brand on the borrower portal, not yours. Build proper white-labeling: custom domain, logo, color palette, email-from address.

### 7.4 Procurement Readiness
- Master Service Agreement template, reviewable by their legal team.
- Data Processing Agreement.
- SOC 2 Type II report (Phase 5).
- Penetration test report (annual third-party).
- Vendor risk questionnaire pre-completed for the standard 200-question banks use.

---

## What "Best Ever" Actually Looks Like at the Finish Line

By end of month 12, the platform should be defensible against the following challenges:

- **"It's unreliable."** → Locust at 1,000 concurrent users, 99.9% uptime SLA, p95 < 500ms.
- **"Voice AI isn't compliant."** → SOC 2 Type II, TCPA consent table, compliance sentry agent, outside counsel quarterly review.
- **"BNTouch has 180 campaigns."** → 200+ Perennia campaigns, plus AI-generated personalized variants per borrower.
- **"Total Expert has 200 enterprise customers."** → 5–10 enterprise customers, each with measurable ROI case study.
- **"Kastle just does voice better."** → Aria + Avery + memory + LOS push + compliance integration. Kastle is one feature of Perennia, not a substitute.
- **"It's expensive."** → Per-LO pricing comes in at $149, vs Surefire at $499. AI compute charged at cost-plus, transparent.

---

## Key Bets & Trade-Offs (Be Honest About These)

| Bet | If right | If wrong |
|-----|----------|----------|
| All-in-one beats best-of-breed | You own the LO desktop. $5B+ exit. | LOs buy Kastle + Maxwell + their existing CRM. You're undifferentiated. |
| AI compute economics stay favorable | Per-loan AI cost stays under $3, gross margin > 75% | Token costs eat the unit economics. Need to raise prices and lose customers. |
| Voice AI doesn't trigger a class action | TCPA infrastructure protects you | One bad outbound campaign and you're paying $1.5M+ in damages |
| Compliance is a moat, not a cost | Enterprise sales accelerate after SOC 2 | You spend $500K on compliance and the LOs you target don't care |

These are real bets. Not all will pay off. The plan is structured so that even if (1) is wrong, the platform is still a great single-product CRM. Even if (3) hits, the legal exposure is bounded by your consent infrastructure.

---

## How to Know You're Winning

Track these weekly. If they're not moving, reprioritize.

- **DAU/WAU ratio for active LOs.** Target: > 0.6. Below that, your platform isn't sticky.
- **Daily Aria/Avery interactions per LO.** Target: > 5. Below that, the AI isn't core to their workflow.
- **Per-loan AI cost.** Target: < $3. Above that, pricing model breaks.
- **Pull-through lift vs LO baseline.** Target: > 5% by month 6. This is the number that closes enterprise deals.
- **Time-to-first-Aria-call after signup.** Target: < 24 hrs. Activation metric.
- **NPS from active LOs.** Target: > 50. Below that, you have feature creep, not product-market fit.

---

## Immediate Next Actions

If you only do five things this week, do these:

1. Ship Phase 0 items 0.1–0.7 by Friday.
2. Start Alembic adoption (Phase 1.1) on Monday.
3. Assign someone — even part-time — to the routes/index.jsx wire-up (Phase 2.1). This is the single highest-leverage frontend fix.
4. Open a doc titled "First 10 LOs" and list the people you'd hand-recruit. Start outreach this week even though the platform isn't ready — the relationship-building takes 8 weeks anyway.
5. Decide pricing. Not perfect pricing. Just a number you can put on a website. You can't sell what isn't priced.

The competitive window is 12–18 months. The good news: you've already done 80% of the engineering that the competition will spend the next 18 months trying to catch up to. The remaining 20% — chassis hardening and distribution — is the part that determines whether you actually win.
