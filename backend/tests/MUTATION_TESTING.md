# Mutation Testing — Perennia AI Backend

## What & Why

**Mutation testing** measures the *quality* of your test suite, not just its
coverage. It works by:

1. Introducing small, deliberate bugs ("mutants") into the source code —
   flipping operators (`+` → `-`), inverting comparisons (`<` → `>=`),
   replacing constants (`0` → `1`), and so on.
2. Running the test suite against each mutated source file.
3. If at least one test fails, the mutant is **killed** (the suite caught the
   bug). If all tests still pass, the mutant **survived** (the suite is blind
   to that bug class).

Line coverage proves a line *was executed*. Mutation testing proves the line
was *meaningfully asserted on*. A test that just calls a function without
checking its return value will hit 100 % line coverage but kill ~0 % of
mutants.

## Why we use it for Perennia AI

Mortgage compliance, SLA arithmetic, holiday calendars, audit logging,
governance metrics, and authentication code are **load-bearing**. A silent
mutation in `holiday_calendar.py` could move a closing date by a day. A
flipped comparison in `admin_guard.py` could let any user reach an admin
endpoint. Mutation testing forces the test suite to actually pin these
behaviours down.

## Target paths (covered by mutmut config in `setup.cfg`)

| Path                                                   | Why mutation-tested                         |
| ------------------------------------------------------ | ------------------------------------------- |
| `backend/auth/`                                        | JWT issue/verify, RS256, blacklist          |
| `backend/middleware/security_headers.py`               | OWASP security headers — silent regressions |
| `backend/middleware/admin_guard.py`                    | Role-based admin route protection           |
| `backend/agents/orchestration/`                        | Governance metrics store, prompt registry   |
| `backend/services/loan_state_audit_service.py`         | Compliance audit trail                      |
| `backend/services/loan_reconciliation_service.py`      | Salesforce-driven state machine             |
| `backend/services/holiday_calendar.py`                 | State-specific holiday detection            |
| `backend/services/important_dates_service.py`          | SLA milestone date computation              |

## Quality gate

**≥ 70 % killed mutations** on the covered paths.

Below that threshold, the test suite is not adequately pinning behaviour and
the PR/release should be blocked. Anything below 50 % is treated as a hard
fail (likely indicates broken test discovery rather than weak tests).

`no tests` mutants (where mutmut cannot find a test that exercises the mutated
line) are excluded from the denominator — they indicate missing tests, not
weak ones, and are tracked separately.

## How to run locally

```bash
# From repo root — uses setup.cfg [mutmut] section
mutmut run

# View the killed/survived breakdown
mutmut results

# Show the diff of a surviving mutant
mutmut show <mutant_id>

# Apply a surviving mutant to disk (to add a regression test against it)
mutmut apply <mutant_id>
```

Expect a full run (~8 files, ~3,000+ mutants) to take **30–90 minutes**
locally depending on hardware. Plan accordingly.

### Quick smoke (single file)

```bash
# Edit setup.cfg paths_to_mutate to a single file, then:
mutmut run
mutmut results | awk -F: '{print $NF}' | sort | uniq -c
```

## CI policy

Mutation testing is **not run on every commit** — it is too slow (~hours
at full scope) and CI minutes are finite.

Instead:

- The workflow `.github/workflows/mutation-testing.yml` is `workflow_dispatch`
  only (manual trigger via GitHub Actions UI).
- Run it before any release that touches the covered paths.
- Run it at least monthly on `main` to track drift in the killed-rate.
- The workflow uploads the `.mutmut-cache` (mutant catalog + results)
  as an artifact for triage.
- The workflow fails the run if killed-rate < 70 % on covered paths.

## Reading the cache

The `.mutmut-cache/` directory (and `mutants/` working dir) contain:

- `mutants/<source-path>/` — copy of source with all mutants inlined under
  a `_mutmut_trampoline` dispatcher.
- `.mutmut-cache` — SQLite DB tracking which mutants have been tested and
  their kill/survive status.

To clear stale state: `rm -rf mutants/ .mutmut-cache`.

## Known issues with mutmut 3.x

- Module-level code that calls mutated functions during import can crash the
  test runner before any test executes — visible as `no tests` for every
  mutant in that module. Workaround: refactor module-level constants to
  lazy properties / functions, or move them into a sub-module that is not
  itself mutated.
- mutmut **ignores the `runner=` line's pytest args** in some paths;
  pytest config (`pytest.ini` / `pyproject.toml [tool.pytest.ini_options]`)
  is the source of truth.
