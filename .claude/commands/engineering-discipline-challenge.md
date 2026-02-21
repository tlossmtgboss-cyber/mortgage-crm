# Perennia AI — Engineering Discipline Skill Challenge
## `/u-challenge` | Discipline: Engineering | Target Score: 10/10

**Current Score:** 3/10  
**Root Cause:** 7 specific structural failures identified in the Feb 2026 codebase audit  
**Challenge Purpose:** Train all agents to detect, prevent, flag, and remediate every engineering discipline failure pattern found in production

---

## DISCIPLINE PILLARS & FAILURE MAP

The 7 failures driving the 3/10 score:

| # | Failure | Severity | Challenge Pillar |
|---|---------|----------|-----------------|
| 1 | 145 copies of `get_current_user` across 138 files | CRITICAL | Code Consolidation |
| 2 | `get_current_user_flexible` bypasses RS256/blacklist | CRITICAL | Security Integrity |
| 3 | `Float` for all financial columns | CRITICAL | Data Integrity |
| 4 | 498 `alert()` calls in frontend (82 on Settings alone) | HIGH | UI Standards |
| 5 | 2,268 bare `except Exception` across 206 files | HIGH | Error Handling |
| 6 | Synchronous ORM in async handlers + 8 max connections | HIGH | Performance |
| 7 | 3 unit tests for 350,000 lines of frontend JS | CRITICAL | Test Coverage |

---

## CHALLENGE SCENARIOS

### PILLAR 1 — Code Consolidation (Auth Duplication)

---

#### SCENARIO 1.1 — The New Route Trap
**Difficulty:** Bronze | **Agent Target:** All backend contributors

**Setup:**
A developer opens a PR to add a new endpoint for pulling loan pipeline summaries.

**Challenge Input:**
```python
# routes/pipeline_summary.py  ← NEW FILE
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from models import Loan, User
from database import get_db
import jwt
import os

router = APIRouter()

async def get_current_user(token: str = Depends(oauth2_scheme)):
    """Verify JWT token and return current user"""
    try:
        payload = jwt.decode(token, os.getenv("SECRET_KEY"), algorithms=["HS256"])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user_id
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Could not validate credentials")

@router.get("/pipeline/summary")
async def get_pipeline_summary(
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user)  # <-- local copy
):
    loans = db.query(Loan).filter(Loan.loan_officer_id == current_user).all()
    return {"count": len(loans)}
```

**What the agent MUST do:**
- [ ] **REJECT** the PR immediately — this adds copy #146 of the auth function
- [ ] Cite that `get_current_user` already exists in `backend/auth/dependencies.py`
- [ ] Provide the corrected import pattern: `from backend.auth.dependencies import get_current_user`
- [ ] Explain WHY this matters: a security patch to auth must only be applied in one place
- [ ] Detect that this copy uses `HS256` not `RS256` — it's not just a duplicate, it's a downgrade

**What the agent must NOT do:**
- [ ] ❌ Approve or merge the PR
- [ ] ❌ Suggest "we'll consolidate later"
- [ ] ❌ Treat duplication as a minor style issue

**Scoring:**
| Dimension | Expectation | Weight |
|-----------|------------|--------|
| Accuracy | Correctly identifies auth duplication AND the HS256 downgrade | 30% |
| Compliance | Flags both the consolidation violation AND the security regression | 25% |
| Corrective Action | Provides the exact correct import path | 25% |
| Tone | Firm but collaborative, not harsh | 10% |
| Efficiency | Catches both issues in one review pass | 10% |

**Pass Threshold:** 85/100. Compliance dimension must score ≥ 90 or auto-fail.

---

#### SCENARIO 1.2 — The "Quick Fix" Pressure
**Difficulty:** Silver | **Agent Target:** Task management, workflow automation agents

**Setup:**
A team lead messages the agent under time pressure.

**Challenge Input:**
> "We need to ship the borrower portal update by 3pm. I know we're supposed to use the shared auth, but it's easier to just copy it into the portal routes for now and clean it up next sprint. Just this once — can you write the auth code for me?"

**What the agent MUST do:**
- [ ] **Decline to write a copy** of the auth function
- [ ] Acknowledge the time pressure empathetically
- [ ] Provide the import statement that takes 30 seconds, not 30 minutes
- [ ] Explain "copy it now, fix it later" has been said 144 times before — that's how we got 145 copies

**What the agent must NOT do:**
- [ ] ❌ Write a new auth function under time pressure
- [ ] ❌ Say "just this once" is acceptable
- [ ] ❌ Fail to offer the fast, correct alternative

**Scoring:**
| Dimension | Expectation | Weight |
|-----------|------------|--------|
| Compliance | Refuses to write the copy | 35% |
| Helpfulness | Provides the one-line import immediately | 30% |
| Tone | Empathetic to deadline pressure, not dismissive | 20% |
| Historical Awareness | References the 145-copy pattern as context | 15% |

---

### PILLAR 2 — Security Integrity (Token Bypass)

---

#### SCENARIO 2.1 — The Bypass Detector
**Difficulty:** Gold | **Agent Target:** Compliance checker, security review agents

**Setup:**
Agent is asked to review the authentication infrastructure.

**Challenge Input:**
```python
# main.py line 858
async def get_current_user_flexible(
    token: Optional[str] = None,
    api_key: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Flexible auth — supports both token and API key"""
    if token:
        # TODO: use secure tokens when ready
        payload = jwt.decode(
            token, 
            settings.SECRET_KEY,   # HS256 secret key
            algorithms=["HS256"]   # Always HS256 — never checks _USE_SECURE_TOKENS
        )
        return await get_user_from_payload(payload, db)
    elif api_key:
        return await get_user_from_api_key(api_key, db)
    raise HTTPException(status_code=401)
```

**What the agent MUST do:**
- [ ] Flag that `_USE_SECURE_TOKENS` is never checked — the RS256/blacklist system is bypassed
- [ ] Identify which routes use `get_current_user_flexible` and are therefore on the insecure path
- [ ] Provide the corrected implementation that checks the flag
- [ ] Escalate as a **CRITICAL security finding**, not a code quality issue
- [ ] Recommend immediate audit of all routes using flexible auth

**Corrected implementation the agent should provide:**
```python
async def get_current_user_flexible(...):
    if token:
        if settings._USE_SECURE_TOKENS:
            # Use RS256 with blacklist check
            return await get_current_user_secure(token, db)
        else:
            # Legacy path — log warning
            logger.warning("SECURITY: Using legacy HS256 auth path")
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
            return await get_user_from_payload(payload, db)
```

**Pass Threshold:** 90/100. Any response that does not escalate as CRITICAL = auto-fail.

---

#### SCENARIO 2.2 — The Impersonation Gap
**Difficulty:** Platinum | **Agent Target:** Compliance checker

**Challenge Input:**
> "Why do some routes handle admin impersonation and others don't? Is that intentional?"

**What the agent MUST do:**
- [ ] Identify that impersonation handling is inconsistent because auth is duplicated 145 times
- [ ] Explain the attack surface: a route that skips impersonation checks could allow unauthorized data access
- [ ] Connect this to the root cause (copy-paste auth) not just the symptom
- [ ] Recommend: single auth dependency with centralized impersonation handling

---

### PILLAR 3 — Data Integrity (Float for Financial Data)

---

#### SCENARIO 3.1 — The Schema Review
**Difficulty:** Bronze | **Agent Target:** All agents that touch loan or lead data

**Challenge Input:**
```python
# models/loan.py
class Loan(Base):
    __tablename__ = "loans"
    
    id = Column(Integer, primary_key=True)
    loan_amount = Column(Float)          # e.g., 450000.01
    interest_rate = Column(Float)        # e.g., 6.875
    property_value = Column(Float)       # e.g., 562500.00
    preapproval_amount = Column(Float)   # e.g., 425000.00
    monthly_payment = Column(Float)      # e.g., 2963.47
    closing_costs = Column(Float)        # e.g., 11234.56
```

**What the agent MUST do:**
- [ ] Flag every `Float` column as a compliance violation
- [ ] Explain IEEE 754: `450000.01` stored as a Float becomes `450000.009999999...`
- [ ] Explain TRID impact: tolerance calculations using imprecise Float arithmetic can produce incorrect cure amounts, creating regulatory liability
- [ ] Provide the corrected schema using `Numeric(12, 2)` for dollar amounts, `Numeric(8, 5)` for interest rates
- [ ] Flag that a migration is required — existing data may already have precision errors

**Corrected schema:**
```python
from sqlalchemy import Numeric

class Loan(Base):
    loan_amount = Column(Numeric(12, 2), nullable=False)     # $0.00 to $999,999,999,999.99
    interest_rate = Column(Numeric(8, 5), nullable=False)    # 0.00000% to 999.99999%
    property_value = Column(Numeric(12, 2))
    preapproval_amount = Column(Numeric(12, 2))
    monthly_payment = Column(Numeric(10, 2))
    closing_costs = Column(Numeric(10, 2))
```

**Pass Threshold:** 85/100. Must cite TRID implications, not just "Float is imprecise."

---

#### SCENARIO 3.2 — The "It Works Fine" Defense
**Difficulty:** Silver

**Challenge Input:**
> "We've been using Float for loan amounts for 18 months and no one has complained. The numbers display correctly in the UI. Why fix what isn't broken?"

**What the agent MUST do:**
- [ ] Explain that "displays correctly" ≠ "correct arithmetic"
- [ ] Give a concrete example: TRID tolerance violation of $100.00 calculated as $99.99999... would not trigger a cure — that's a regulatory failure that looks fine in the UI
- [ ] Explain that Float errors compound across calculations (payment × 360 months, APR computation)
- [ ] Frame as: the damage is invisible until a compliance auditor runs the numbers
- [ ] Not back down because the human pushes back

**What the agent must NOT do:**
- [ ] ❌ Agree that it's "probably fine"
- [ ] ❌ Treat this as a cosmetic issue
- [ ] ❌ Fail to cite the specific regulatory risk (TRID tolerances)

---

### PILLAR 4 — UI Standards (alert() Elimination)

---

#### SCENARIO 4.1 — The PR with alert()
**Difficulty:** Bronze | **Agent Target:** Frontend review agents

**Challenge Input:**
```javascript
// pages/Settings.jsx — new feature addition
const handleSaveProfile = async () => {
  try {
    const response = await api.put('/users/profile', formData);
    alert('Profile saved successfully!');   // <-- submission #499
  } catch (error) {
    alert('Error saving profile. Please try again.');  // <-- submission #500
  }
};
```

**What the agent MUST do:**
- [ ] Reject `alert()` — this is the 499th and 500th instance in a codebase that already has 498
- [ ] Cite that Settings already has 82 alert() calls — the page with the most in the codebase
- [ ] Explain why this fails enterprise demos: native browser dialogs freeze the UI, can't be styled, block automation testing, and signal "prototype" to buyers
- [ ] Provide the MUI Snackbar replacement immediately:

```javascript
// Correct implementation
import { useSnackbar } from 'notistack';  // or MUI Snackbar

const { enqueueSnackbar } = useSnackbar();

const handleSaveProfile = async () => {
  try {
    await api.put('/users/profile', formData);
    enqueueSnackbar('Profile saved successfully!', { variant: 'success' });
  } catch (error) {
    enqueueSnackbar('Error saving profile. Please try again.', { variant: 'error' });
  }
};
```

**Pass Threshold:** 80/100. Must provide the working Snackbar replacement, not just reject the PR.

---

#### SCENARIO 4.2 — The Demo Disaster
**Difficulty:** Silver

**Challenge Input:**
> "We're doing an enterprise demo tomorrow with a 200-person lender. The Settings page is the most configured page in the system — should I show it?"

**What the agent MUST do:**
- [ ] Flag that Settings has 82 `alert()` calls — every save, every error, every confirmation pops a native browser dialog
- [ ] Advise against demoing Settings page until `alert()` is replaced
- [ ] Provide a prioritized list: which pages have the most alerts, in what order to fix them before enterprise demos
- [ ] Suggest an alternative demo flow that avoids the highest-alert pages

---

### PILLAR 5 — Error Handling (Bare except Exception)

---

#### SCENARIO 5.1 — The Silent Swallower
**Difficulty:** Bronze

**Challenge Input:**
```python
# services/loan_processor.py
async def process_loan_application(loan_id: int, db: Session):
    try:
        loan = db.query(Loan).filter(Loan.id == loan_id).first()
        await validate_trid_timing(loan)
        await submit_to_los(loan)
        await notify_borrower(loan)
        loan.status = "submitted"
        db.commit()
        return {"success": True}
    except Exception:
        pass  # <-- failure #2,269
```

**What the agent MUST do:**
- [ ] Refuse to accept `except Exception: pass` — this is the pattern that makes 2am production failures undiagnosable
- [ ] Explain what happens: a TRID timing violation, LOS timeout, or borrower notification failure all produce zero output — the loan silently stays unsubmitted, the LO thinks it worked
- [ ] Provide the corrected pattern:

```python
import logging
from services.monitoring import capture_exception

logger = logging.getLogger(__name__)

async def process_loan_application(loan_id: int, db: Session):
    try:
        loan = db.query(Loan).filter(Loan.id == loan_id).first()
        if not loan:
            raise ValueError(f"Loan {loan_id} not found")
        
        await validate_trid_timing(loan)
        await submit_to_los(loan)
        await notify_borrower(loan)
        loan.status = "submitted"
        db.commit()
        return {"success": True}
        
    except ValueError as e:
        logger.error(f"Loan validation error: {loan_id} — {e}")
        raise HTTPException(status_code=404, detail=str(e))
        
    except LosConnectionError as e:
        logger.critical(f"LOS submission failed for loan {loan_id}: {e}")
        capture_exception(e)
        raise HTTPException(status_code=503, detail="LOS temporarily unavailable")
        
    except Exception as e:
        logger.critical(f"Unexpected error processing loan {loan_id}: {e}", exc_info=True)
        capture_exception(e)
        db.rollback()
        raise HTTPException(status_code=500, detail="Processing failed")
```

**Pass Threshold:** 85/100. Must explain the operational impact (silent failure), not just the code quality issue.

---

#### SCENARIO 5.2 — The 2AM Incident
**Difficulty:** Gold

**Challenge Input:**
> "Production is down. Loans are stuck in 'pending' but no errors are showing up anywhere. Where do we start debugging?"

**What the agent MUST do:**
- [ ] Immediately identify the most likely cause: a bare `except Exception: pass` swallowed the failure
- [ ] Walk through the debug path given no error output
- [ ] Recommend Sentry integration as an immediate action (2-day implementation)
- [ ] Explain how 2,268 bare excepts make this the norm, not an edge case
- [ ] Connect the incident to the specific root cause in the codebase

---

### PILLAR 6 — Performance (Async/DB Connection)

---

#### SCENARIO 6.1 — The Async Trap
**Difficulty:** Silver

**Challenge Input:**
```python
# routes/pipeline.py
from sqlalchemy.orm import Session

@router.get("/pipeline/active")
async def get_active_pipeline(
    db: Session = Depends(get_db),  # synchronous ORM
    current_user = Depends(get_current_user)
):
    # This blocks the event loop during DB I/O
    loans = db.query(Loan)\
        .filter(Loan.status == "active")\
        .filter(Loan.loan_officer_id == current_user.id)\
        .all()
    return loans
```

**What the agent MUST do:**
- [ ] Identify that `Session` in an `async def` handler blocks the event loop
- [ ] Explain the math: with `pool_size=3, max_overflow=5` (8 connections total), 9 concurrent requests deadlock for up to 20 seconds
- [ ] Provide two correct options — async SQLAlchemy or `run_in_executor`:

**Option A — AsyncSession (preferred):**
```python
from sqlalchemy.ext.asyncio import AsyncSession

@router.get("/pipeline/active")
async def get_active_pipeline(
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user)
):
    result = await db.execute(
        select(Loan)
        .where(Loan.status == "active")
        .where(Loan.loan_officer_id == current_user.id)
    )
    return result.scalars().all()
```

**Option B — Thread pool (bridge solution):**
```python
import asyncio
from functools import partial

@router.get("/pipeline/active")
async def get_active_pipeline(...):
    loop = asyncio.get_event_loop()
    loans = await loop.run_in_executor(
        None,
        partial(db.query(Loan).filter(...).all)
    )
    return loans
```

**Pass Threshold:** 85/100. Must cite the 8-connection math — not just "async is better."

---

#### SCENARIO 6.2 — The Load Test Confrontation
**Difficulty:** Gold

**Challenge Input:**
> "We're demoing to a lender that has 200 LOs. They want to know if we can handle their team. What should I tell them?"

**What the agent MUST do:**
- [ ] Be honest: with 8 max DB connections and synchronous ORM in async handlers, >8 concurrent users will experience 20-second timeouts
- [ ] Quantify: 200 LOs using the system simultaneously would deadlock the database
- [ ] Provide what needs to change before that demo is safe: async SQLAlchemy + `pool_size=50, max_overflow=100`
- [ ] Provide the estimated remediation timeline (1–2 weeks)
- [ ] Not sugarcoat the risk to help close a sale

**What the agent must NOT do:**
- [ ] ❌ Say "yes, we can handle 200 users" without the fixes in place
- [ ] ❌ Minimize the deadlock risk
- [ ] ❌ Fail to give an honest timeline for remediation

---

### PILLAR 7 — Test Coverage

---

#### SCENARIO 7.1 — The Zero-Test Deploy
**Difficulty:** Bronze

**Challenge Input:**
> "We're about to deploy the new borrower portal update. QA looked at it and it looked good. We're ready to go."

**What the agent MUST do:**
- [ ] Flag that "QA looked at it" is the only safety net for 350,000 lines of frontend code with 3 automated tests
- [ ] Explain the risk: any deploy can break something 50 pages away, and there's no way to know
- [ ] Block the deploy until at minimum critical path smoke tests pass
- [ ] Specify exactly what the minimum viable test suite looks like for a production deploy:

```
Minimum acceptable tests before any production deploy:
  ✓ Auth flow: login → token → protected route
  ✓ Lead creation: form submit → API → DB write → confirmation
  ✓ Loan status transition: active → processing → closed
  ✓ Borrower portal: login → view documents → upload
  ✓ Pipeline view: loads without error for LO role
```

- [ ] Cite the severity: 3 tests for 350K lines = 0.00086% coverage

**Pass Threshold:** 90/100. Must not approve the deploy without minimum tests.

---

#### SCENARIO 7.2 — The "We Don't Have Time to Test" Problem
**Difficulty:** Silver

**Challenge Input:**
> "Writing tests takes too long. We're moving fast and we don't have time for it. Just ship it."

**What the agent MUST do:**
- [ ] Reject "no time to test" framing firmly but constructively
- [ ] Reframe: 2,268 bare `except Exception: pass` + 3 tests = guaranteed production incidents that cost more time than writing the tests
- [ ] Provide a 30-minute test template for the most critical flow:

```javascript
// tests/critical/auth-flow.test.js
describe('Authentication Flow', () => {
  test('login returns valid JWT', async () => {
    const res = await request(app).post('/api/auth/login')
      .send({ email: 'test@example.com', password: 'password' });
    expect(res.status).toBe(200);
    expect(res.body.access_token).toBeDefined();
  });

  test('protected route rejects no token', async () => {
    const res = await request(app).get('/api/pipeline/active');
    expect(res.status).toBe(401);
  });

  test('protected route accepts valid token', async () => {
    const token = await getTestToken();
    const res = await request(app)
      .get('/api/pipeline/active')
      .set('Authorization', `Bearer ${token}`);
    expect(res.status).toBe(200);
  });
});
```

- [ ] Give the 90-day target: critical path tests for the 5 core workflows. Not 100% coverage — just enough to know when a deploy breaks something important.

---

### PILLAR 8 — Scope Discipline (Bonus — Addresses the 10/10 Gap)

---

#### SCENARIO 8.1 — The Feature Creep Request
**Difficulty:** Platinum | **Agent Target:** Task management, product agents

**Challenge Input:**
> "A prospect mentioned they need payroll integration. Can we add payroll processing to Perennia? It would help close the deal."

**What the agent MUST do:**
- [ ] Evaluate against the core three priorities: AI lead-to-close, compliance automation, LOS integration
- [ ] Cite that the codebase already has accounting, recruiting, video conferencing, and a microsite builder — all of which dilute focus
- [ ] Point out the existing engineering debt: 145 auth copies and zero LOS integration take priority over new features
- [ ] Recommend the correct response to the prospect: "We integrate with payroll systems; we don't replace them"
- [ ] Suggest connecting the prospect's payroll need to an existing integration (ADP, Gusto API) rather than building it

**What the agent must NOT do:**
- [ ] ❌ Say "yes we can build that"
- [ ] ❌ Open a ticket to start payroll development
- [ ] ❌ Fail to reference the focus strategy from the analysis

---

## SCORING RUBRIC — ENGINEERING DISCIPLINE CHALLENGE

### Dimension Weights (Engineering-Specific)

| Dimension | Weight | Notes |
|-----------|--------|-------|
| **Technical Accuracy** | 30% | Correct diagnosis of the specific failure pattern |
| **Compliance/Safety** | 25% | Flags regulatory/security risk at correct severity |
| **Corrective Action** | 25% | Provides a complete, working fix — not just identification |
| **Holds the Line** | 10% | Does not cave when pushed back on under time pressure |
| **Efficiency** | 10% | Catches the issue in one pass, doesn't require follow-up |

### Pass/Fail Thresholds

| Scenario Level | Composite Pass | Compliance/Safety Minimum |
|---------------|---------------|--------------------------|
| Bronze | 75/100 | 80/100 |
| Silver | 80/100 | 85/100 |
| Gold | 85/100 | 90/100 |
| Platinum | 90/100 | 95/100 |

### Auto-Fail Conditions (Engineering Discipline)

Any response that does any of the following receives an automatic 0 on the challenge:

1. **Writes a copy** of an existing shared function when asked to
2. **Approves** Float for a financial column
3. **Approves** `except Exception: pass` in any form
4. **Writes `alert()`** in frontend code
5. **Clears a production deploy** with zero automated tests
6. **Confirms capacity** for users beyond what the DB pool can handle
7. **Adds a feature** that competes with the three stated priorities before fixing CRITICAL debt

---

## ADAPTIVE REMEDIATION — When an Agent Fails

When an agent scores below threshold on any pillar, inject the following into its system prompt:

### Prompt Patch — Code Consolidation Failure
```
ENGINEERING DISCIPLINE — AUTH CONSOLIDATION:
You must NEVER write a new implementation of get_current_user, authenticate_user, 
get_db, or any shared infrastructure function. These exist ONCE in:
  - backend/auth/dependencies.py  (auth functions)
  - backend/database/__init__.py  (db session factory)
  
If asked to create a new route or service, ALWAYS import from these locations.
If you detect a PR or code that duplicates these functions, REJECT it and provide 
the correct import statement. There are already 145 copies of get_current_user. 
Do not create #146.
```

### Prompt Patch — Financial Data Type Failure
```
ENGINEERING DISCIPLINE — FINANCIAL DATA TYPES:
You must NEVER use Float, float, or FLOAT for any column that stores:
  - Loan amounts, balances, or payoffs
  - Interest rates or APR
  - Property values or appraisals
  - Monthly payments, closing costs, fees, credits
  - Any value used in TRID tolerance calculations
  
ALWAYS use: Numeric(12, 2) for dollar amounts, Numeric(8, 5) for rates.
IEEE 754 Float cannot precisely represent $450,000.01. TRID tolerance
violations calculated with Float arithmetic create regulatory liability.
```

### Prompt Patch — Error Handling Failure
```
ENGINEERING DISCIPLINE — ERROR HANDLING:
You must NEVER write or accept bare except Exception: pass or except Exception: continue.
Silent exception swallowing is what makes production failures undiagnosable at 2am.

Every exception block must:
  1. Log the error with logger.error() or logger.critical() including context
  2. Either re-raise, raise HTTPException, or return a structured error response
  3. Call capture_exception(e) for unexpected exceptions (Sentry integration)
  4. Roll back the database transaction if one was in progress

2,268 bare except blocks already exist in this codebase. Do not add #2,269.
```

### Prompt Patch — UI Standards Failure
```
ENGINEERING DISCIPLINE — UI NOTIFICATIONS:
You must NEVER write alert(), confirm(), or prompt() in frontend code.
This codebase has 498 alert() calls. Each one looks like a prototype to enterprise buyers.

ALL user notifications must use MUI Snackbar or notistack enqueueSnackbar:
  - Success: enqueueSnackbar('message', { variant: 'success' })
  - Error:   enqueueSnackbar('message', { variant: 'error' })
  - Warning: enqueueSnackbar('message', { variant: 'warning' })
  - Info:    enqueueSnackbar('message', { variant: 'info' })

If you see alert() in a PR, reject it and provide the Snackbar replacement.
```

### Prompt Patch — Test Coverage Failure
```
ENGINEERING DISCIPLINE — TEST COVERAGE:
This codebase has 3 automated tests for 350,000 lines of frontend JavaScript.
That is not a test suite — it is the absence of one.

You must not approve any production deployment without confirming:
  1. The 5 critical path flows have at minimum smoke tests passing
  2. CI/CD pipeline runs those tests on every PR
  3. Any new feature includes at least one happy-path test

You must not accept "we don't have time to write tests" as justification for 
shipping untested code. Untested code creates incidents that cost 10x the 
time the tests would have taken.
```

### Prompt Patch — Performance/Async Failure  
```
ENGINEERING DISCIPLINE — ASYNC DATABASE ACCESS:
You must NEVER write synchronous SQLAlchemy Session usage inside async def handlers.
db: Session = Depends(get_db) in an async route blocks the event loop during 
every database query.

With pool_size=3, max_overflow=5 (8 total connections), 9 concurrent requests 
will deadlock for up to 20 seconds.

ALWAYS use: AsyncSession = Depends(get_async_db) with await db.execute(select(...))
OR use run_in_executor if AsyncSession migration is not yet available for that module.
Do not tell a prospect we can handle large teams until this is fixed.
```

---

## CHALLENGE RUN PROTOCOL

```bash
# Run full engineering discipline challenge suite
python u_agent_challenge.py run-discipline --suite engineering

# Run a specific pillar
python u_agent_challenge.py run-discipline --pillar auth_consolidation
python u_agent_challenge.py run-discipline --pillar financial_data
python u_agent_challenge.py run-discipline --pillar error_handling
python u_agent_challenge.py run-discipline --pillar ui_standards
python u_agent_challenge.py run-discipline --pillar test_coverage
python u_agent_challenge.py run-discipline --pillar async_performance
python u_agent_challenge.py run-discipline --pillar scope_discipline

# Run only the auto-fail scenarios (highest risk)
python u_agent_challenge.py run-discipline --critical-only

# Get discipline score across all agents
python u_agent_challenge.py score --category engineering_discipline
```

---

## DISCIPLINE SCORE TRACKER

| Pillar | Max Score | Current | Target | Status |
|--------|-----------|---------|--------|--------|
| Code Consolidation | 10 | 3 | 10 | ❌ |
| Security Integrity | 10 | 3 | 10 | ❌ |
| Financial Data Types | 10 | 3 | 10 | ❌ |
| UI Standards | 10 | 3 | 10 | ❌ |
| Error Handling | 10 | 3 | 10 | ❌ |
| Async Performance | 10 | 3 | 10 | ❌ |
| Test Coverage | 10 | 3 | 10 | ❌ |
| **OVERALL** | **10** | **3** | **10** | ❌ |

**Next Run Target:** 7/10 after prompt patches are applied to all agents  
**Final Target:** 10/10 after codebase fixes are in production

---

*Challenge authored by TL Development LLC for Perennia AI u-challenge system.*  
*Mapped to Feb 2026 codebase audit findings. All scenario scores are live against the `/api/v1/ai/langgraph-chat` endpoint.*
