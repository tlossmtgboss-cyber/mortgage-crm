# Testing & CI/CD Remediation

## Current State (Critical)
- ~50 test files for 1,465 source files and ~3,876 API endpoints
- Frontend: 3 test files for 295 components
- Roughly 1 test per 77 endpoints
- No CI/CD pipeline running tests on merge
- Zero safety net for production deployments

## Phase 1: CI/CD Pipeline (Days 1–3)

### Step 1: GitHub Actions Workflow

Create `.github/workflows/ci.yml`:

```yaml
name: Perennia CI
on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

env:
  PYTHON_VERSION: "3.11"
  NODE_VERSION: "20"

jobs:
  backend-tests:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_DB: perennia_test
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
        ports: ["5432:5432"]
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
          cache: pip
      - run: pip install -r requirements.txt -r requirements-test.txt
      - run: pytest tests/ -x --timeout=30 -q --tb=short
        env:
          DATABASE_URL: postgresql://test:test@localhost:5432/perennia_test
          TESTING: "true"

  frontend-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: ${{ env.NODE_VERSION }}
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - run: cd frontend && npm ci
      - run: cd frontend && npm test -- --watchAll=false --passWithNoTests

  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
      - run: pip install ruff
      - run: ruff check . --select E,W,F --ignore E501
```

### Step 2: Test Configuration

Create `pytest.ini` (or update `pyproject.toml`):

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_functions = test_*
asyncio_mode = auto
timeout = 30
markers =
    critical: Tests for revenue-critical paths
    integration: Tests requiring database
    unit: Pure unit tests
```

Create `requirements-test.txt`:

```
pytest>=8.0
pytest-asyncio>=0.23
pytest-timeout>=2.2
pytest-cov>=4.1
httpx>=0.27  # For async test client
factory-boy>=3.3
```

## Phase 2: Critical Path Tests (Days 3–10)

Focus on the 20 endpoints that, if broken, would cause customer-visible failures. These are the "if this breaks, we lose money" paths.

### Priority 1: Auth Endpoints (Day 3–4)

```python
# tests/test_auth.py
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

@pytest.fixture
async def auth_headers(client):
    """Create a test user and return auth headers."""
    # Register
    resp = await client.post("/api/auth/register", json={
        "email": "test@perennia.ai",
        "password": "TestPass123!",
        "first_name": "Test",
        "last_name": "User"
    })
    token = resp.json().get("access_token")
    return {"Authorization": f"Bearer {token}"}

class TestAuthFlow:
    async def test_register_new_user(self, client):
        resp = await client.post("/api/auth/register", json={
            "email": "new@test.com",
            "password": "Secure123!",
            "first_name": "New",
            "last_name": "User"
        })
        assert resp.status_code in (200, 201)
        assert "access_token" in resp.json()

    async def test_login_valid_credentials(self, client, auth_headers):
        resp = await client.post("/api/auth/login", json={
            "email": "test@perennia.ai",
            "password": "TestPass123!"
        })
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    async def test_login_invalid_password(self, client):
        resp = await client.post("/api/auth/login", json={
            "email": "test@perennia.ai",
            "password": "wrong"
        })
        assert resp.status_code in (401, 403)

    async def test_protected_route_without_token(self, client):
        resp = await client.get("/api/users/me")
        assert resp.status_code == 401
```

### Priority 2: Leads CRUD (Day 4–5)

```python
# tests/test_leads.py
class TestLeadsCRUD:
    async def test_create_lead(self, client, auth_headers):
        resp = await client.post("/api/leads/", json={
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com",
            "phone": "5551234567",
            "lead_source": "website"
        }, headers=auth_headers)
        assert resp.status_code in (200, 201)
        data = resp.json()
        assert data["first_name"] == "John"
        return data["id"]

    async def test_get_lead(self, client, auth_headers):
        # Create then fetch
        create_resp = await client.post("/api/leads/", json={
            "first_name": "Jane",
            "last_name": "Doe",
            "email": "jane@example.com"
        }, headers=auth_headers)
        lead_id = create_resp.json()["id"]

        resp = await client.get(f"/api/leads/{lead_id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["email"] == "jane@example.com"

    async def test_update_lead(self, client, auth_headers):
        create_resp = await client.post("/api/leads/", json={
            "first_name": "Update",
            "last_name": "Test",
            "email": "update@example.com"
        }, headers=auth_headers)
        lead_id = create_resp.json()["id"]

        resp = await client.patch(f"/api/leads/{lead_id}", json={
            "phone": "5559876543"
        }, headers=auth_headers)
        assert resp.status_code == 200

    async def test_lead_isolation_between_tenants(self, client):
        """Critical: Ensure tenant A cannot see tenant B's leads."""
        # This test is the most important data integrity test
        # Create lead as user A, verify user B cannot access it
        pass  # Implement with two separate auth contexts
```

### Priority 3: Loans CRUD (Day 5–6)

```python
# tests/test_loans.py
class TestLoansCRUD:
    async def test_create_loan(self, client, auth_headers):
        # First create a lead
        lead_resp = await client.post("/api/leads/", json={
            "first_name": "Borrower",
            "last_name": "Test",
            "email": "borrower@test.com"
        }, headers=auth_headers)
        lead_id = lead_resp.json()["id"]

        resp = await client.post("/api/loans/", json={
            "lead_id": lead_id,
            "loan_amount": 350000,
            "loan_type": "conventional",
            "property_address": "123 Main St",
            "property_city": "Charleston",
            "property_state": "SC"
        }, headers=auth_headers)
        assert resp.status_code in (200, 201)
        # Critical: Verify loan amount stored correctly (Float→Numeric issue)
        data = resp.json()
        assert data["loan_amount"] == 350000

    async def test_loan_amount_precision(self, client, auth_headers):
        """Regression test: Float→Numeric conversion.
        Ensure $350,000 doesn't become $35,000 or $350,000.01"""
        # Create loan with specific amounts that historically caused precision issues
        test_amounts = [350000, 250000.50, 1000000, 99999.99]
        for amount in test_amounts:
            # Create and verify each amount round-trips correctly
            pass  # Implement with lead creation + loan creation + verification
```

### Priority 4: Pipeline Metrics (Day 6–7)

```python
# tests/test_pipeline.py
class TestPipelineMetrics:
    async def test_pipeline_summary(self, client, auth_headers):
        resp = await client.get("/api/pipeline/summary", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        # Verify expected shape
        assert "total_leads" in data or "pipeline" in data

    async def test_pipeline_performance_under_load(self, client, auth_headers):
        """Simulate Monday morning: 50 LOs querying pipeline simultaneously.
        Railway gives ~20 DB connections — this must not exhaust the pool."""
        import asyncio
        tasks = [
            client.get("/api/pipeline/summary", headers=auth_headers)
            for _ in range(20)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        errors = [r for r in results if isinstance(r, Exception)]
        assert len(errors) == 0, f"Connection pool exhaustion: {errors}"
```

### Priority 5: Salesforce Sync Data Integrity (Day 7–8)

```python
# tests/test_salesforce_sync.py
class TestSalesforceSyncIntegrity:
    async def test_loan_amount_not_corrupted_on_sync(self):
        """Critical: Verify field mapping doesn't corrupt loan amounts.
        $350,000 must not become $35,000 due to decimal/field mapping bugs."""
        pass  # Mock Salesforce API, create loan, trigger sync, verify amounts

    async def test_sync_conflict_detection(self):
        """When Salesforce and Perennia have different values,
        verify conflict is logged and not silently overwritten."""
        pass

    async def test_sync_audit_trail(self):
        """Every sync operation must produce an audit record
        showing before/after values for compliance."""
        pass
```

## Phase 3: Coverage Expansion (Week 2+)

### Coverage Targets

| Milestone | Backend | Frontend | Timeline |
|-----------|---------|----------|----------|
| Baseline  | ~0.04%  | ~1%      | Now      |
| Phase 2   | 5%      | 3%       | Week 1   |
| Phase 3   | 15%     | 10%      | Month 1  |
| Phase 4   | 30%     | 20%      | Month 2  |
| Target    | 50%+    | 40%+     | Month 3  |

### Test Prioritization Matrix

For each endpoint, score:
- **Revenue impact** (1–5): Would a bug here lose a customer?
- **Data integrity risk** (1–5): Could a bug corrupt financial data?
- **Usage frequency** (1–5): How often is this called daily?

Test endpoints scoring 12+ first. The top 20 by this scoring should cover 80% of real-world risk.

### Frontend Testing Strategy

```bash
# Install testing dependencies
npm install --save-dev @testing-library/react @testing-library/jest-dom
npm install --save-dev @testing-library/user-event vitest jsdom
```

Priority components to test:
1. **Login/Auth flow** — Broken login = no product
2. **Pipeline view** — LO's daily driver
3. **Lead/Contact forms** — Data entry accuracy
4. **Loan detail page** — Financial data display precision
5. **Settings page** (6,966 lines — but test critical sub-sections first)

## Validation Checklist

- [ ] GitHub Actions workflow runs on every push to main/develop
- [ ] Auth flow tests pass (register, login, token validation, route protection)
- [ ] Leads CRUD tests pass with tenant isolation verification
- [ ] Loans CRUD tests pass with amount precision verification
- [ ] Pipeline query doesn't exhaust connection pool under concurrent load
- [ ] Salesforce sync field mapping verified (no amount corruption)
- [ ] `pytest --cov` reports >5% backend coverage
- [ ] Frontend test runner (`npm test`) executes without errors
