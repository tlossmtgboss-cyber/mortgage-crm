# Coverage Policy

Perennia AI ships pytest-cov coverage measurement on every PR via the
`Golden Tests` workflow (`.github/workflows/golden-tests.yml`). Coverage
configuration lives in `backend/pyproject.toml` under `[tool.coverage.*]`.

## Today

- Measured today: **< 1%** (baseline before Wave 3 ramp)
- `fail_under` gate: **5%** (Wave 3 floor — locks in the current floor and
  prevents accidental regression)
- Coverage artifact: `coverage.xml` uploaded by every CI run, retained 30
  days.

## Ramp schedule

| Wave    | `fail_under` | Rationale                                      |
| ------- | ------------ | ---------------------------------------------- |
| Wave 3  | 5%           | Establish floor; prevent regression.           |
| Wave 4  | 10%          | Test all auth + RLS surfaces.                  |
| Wave 5  | 25%          | Test critical agents, telephony, compliance.   |
| Wave 6  | 60%          | Service-layer tests + happy-path integration.  |
| Wave 7+ | 85%          | Final discipline target.                       |

Each wave raises `fail_under` in `backend/pyproject.toml` only after that
wave's coverage uplift work merges. Raising the gate before the work
lands turns CI red and blocks the team.

## Local runs

```sh
cd backend
pytest tests/integration/ \
  --cov=backend \
  --cov-report=term-missing \
  --cov-report=html
open htmlcov/index.html
```

## What counts as covered

`[tool.coverage.run]` measures the source roots `agents`, `services`,
`routes`, `auth`, `core`, `middleware`, `database`, and the `backend`
parent path (when CI runs from the repo root). Tests, migrations, and
virtualenvs are excluded.

## Per-module aspirations

Long-term we expect these floors per critical module (enforced manually
until pytest-cov supports per-path `fail_under`):

- Security / auth / RLS modules: **95%**
- Financial calculations: **95%**
- API endpoint handlers: **90%**
- Service-layer business logic: **85%**
