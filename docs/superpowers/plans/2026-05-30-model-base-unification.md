# Model-Layer Base Unification — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify the SQLAlchemy model layer onto a single declarative `Base`/registry so every cross-model relationship resolves, the test suite runs green, and future refactors are verifiable.

**Architecture:** Today the backend has 6+ independent `declarative_base()` instances and 11 model *factory functions* that cache created classes by `id(Base)` and cross-reference each other by string name. Because a factory binds its classes to whichever `Base` it was *first* called with, and the factories are invoked inconsistently (some in routes, some only in tests, some never during app load), `configure_mappers()` fails (`'Role'`, `'WorkflowInstance'`, `'WorkflowConfiguration'` "failed to locate a name"). This plan introduces **one canonical registration entry point** that registers every model on `db.Base` exactly once, fixes factory Base-binding, collapses duplicate definitions, renames genuinely-separate same-named models, and brings the test harness up green.

**Tech Stack:** Python 3.11, SQLAlchemy 2.0 (`DeclarativeBase`), FastAPI, PostgreSQL 16 (local `test_perennia` for tests), pytest.

---

## ✅ RESOLVED BLOCKER — canonical Role decided (2026-05-30)

Executing Task 1 surfaced a pre-existing mis-wired relationship: `LeadWorkflowRoleAssignment` (`models/workflow_sla.py:318`) has `role_id = ForeignKey("roles.id")` + `role = relationship("Role")`, but the only `class Role` maps to `onboarding_roles`, and **no ORM model maps to `roles`**.

**DECISION (product owner): the workflow role is the RBAC/team role (table `roles`).**

Verified against production: table `roles` exists with 19 rows. Schema:
`id int PK, name varchar NOT NULL, code varchar, description text, is_active bool, created_at timestamptz, updated_at timestamptz, abbreviation varchar`.

**Resolution (do this as Task 1a, before the rest of Task 1):**
1. **Create a canonical `Role` model on table `roles`** in `backend/database/models/permission.py` (alongside the RBAC `Responsibility`/`UserResponsibility`), matching the prod schema above, on the canonical `db.Base`. Re-export it via `database/models/__init__.py` if that's the established pattern. This is the `Role` that `relationship("Role")` resolves to.
2. **Rename `models/user_onboarding.py`'s `class Role` → `class OnboardingRole`** (table stays `onboarding_roles`) and add alias `Role = OnboardingRole` for back-compat. Update its internal relationship string refs (`"Role"` → `"OnboardingRole"` in user_onboarding only). NOTE: the `user_onboarding_integration.py` factory **already** names this class `OnboardingRole` — so after Task 4 (collapse to factory), this rename aligns the two.
3. **Update Task 0's parametrize row** to `("Role", "roles")` (was incorrectly `onboarding_roles`).

After 1–3, `LeadWorkflowRoleAssignment.role` / FK `roles.id` / `relationship("Role")` all agree on the RBAC `roles` table.

**Status:** Task 0 red gate committed (`d26576038`); plan committed; blocker recorded + resolved. Resume at Task 1a.

---

## ⚠ SCOPE FINDING #2 — pervasive duplicate model definitions (2026-05-30, with evidence)

Executing Task 1/2 proved the model layer contains **multiple parallel/duplicate definitions of the same domain models**, historically isolated by separate `Base`es. Unifying onto one Base surfaces each pair as a registry collision. Confirmed examples:

- **E-sign ×2:** `models/esign_models.py` (factory, tables `esign_*`) **and** `database/models/esignature.py` (direct, tables `esignature_*`). Evidence: registering the esign factory then importing `database.models.esignature` (pulled in by `perennia_docs`'s import chain) collapses the `EsignAuditEvent` registry entry to `None` (name collision), which is what breaks `configure_mappers()` after factory #6 in `register_all_models`.
- **Onboarding ×2:** `models/user_onboarding.py` (direct) **and** `user_onboarding_integration.py` (factory) — same `onboarding_*` tables. (Task 4 already addresses this one.)
- **Module-level duplicate class names** (partial scan, excludes factory-internal classes): `Appointment`, `AvailabilitySlot`, plus many enum/Pydantic-name overlaps to triage.

**Implication:** Tasks 1–7 as written are necessary but **not sufficient**. Before the mechanical Base-binding can go green, the duplicate **domain** models must be reconciled — and each pair is a product/architecture decision (which definition is canonical, or are they genuinely distinct and need distinct names?). This is the same shape as the Role decision, repeated per duplicated entity.

**Required new step — Task 0b: Duplicate-model reconciliation inventory.** Before resuming Task 2:
1. Enumerate every model NAME and TABLE defined in more than one module (include factory-internal classes — grep `^\s*class [A-Z]` across `models/`, `database/models/`, and the `*_models.py` factory files).
2. For each duplicate, classify: (a) true duplicate of one entity → pick canonical, delete/redirect the other; (b) distinct entities sharing a name → rename one with a back-compat alias (the Role/Responsibility pattern).
3. Get product sign-off on the (a)-vs-(b) call for each pair (esign, onboarding, Appointment, AvailabilitySlot, …).
4. THEN the mechanical Base unification (Tasks 1–7) can complete.

**Honest scope:** this is a multi-session reconciliation, not a single mechanical pass. The architectural blocker (Role) is resolved and committed; `register_all_models` + the canonical Role are in place; the remaining gate to green is the duplicate-model reconciliation above.

**Commits so far on `refactor/model-base-unification`:** plan + finding (`315a2f14a`), red gate (`d26576038`), canonical Role (`803108760`), register_all_models (`34f5f38a2`), idempotency guard (`ca8845efc`).

---

## Ground Truth (verified during investigation — read before starting)

**Canonical Base:** `backend/db.py:74` — `class Base(DeclarativeBase)`. Importable as `from db import Base` or `from database import Base`.

**The 11 model factories** (`def create_*_models(Base)`):

| Factory | File | Called in app at | Notes |
|---|---|---|---|
| `create_user_onboarding_models` | `user_onboarding_integration.py:26` | `routes/inline_legacy_routes.py:1989` | Defines Role/Category/OnboardingResponsibility/… (tables `onboarding_*`). **Duplicates** the direct classes in `models/user_onboarding.py`. |
| `create_workflow_config_models` | `workflow_config_models.py:58` | `routes/workflow_sla_routes.py:1367`, `routes/inline_legacy_routes.py:1227`, `services/workflow_sla_service.py:52` | Defines `WorkflowTaskInstance` → `relationship("WorkflowInstance")` (owned by SLA factory). |
| `create_workflow_sla_models` | `models/workflow_sla.py:108` | **only `tests/test_db_helper.py`** — never during app load | Defines `WorkflowInstance`, `LeadWorkflowRoleAssignment` → `relationship("Role")`, and references `"WorkflowConfiguration"`. This is the root of the mapper failure. |
| `create_smart_scheduler_models` | `smart_scheduler_models.py:53` | (audit during Task 2) | |
| `create_video_clip_models` | `video_clip_models.py:220` | (audit during Task 2) | |
| `create_video_meeting_models` | `video_meeting_models.py:87` | (audit during Task 2) | |
| `create_scheduler_enhancement_models` | `scheduler_enhancements.py:89` | (audit during Task 2) | |
| `create_esign_models` | `models/esign_models.py:112` | (audit during Task 2) | Has `declarative_base()` fallback at `:508`. |
| `create_perennia_docs_models` | `models/perennia_docs.py:174` | (audit during Task 2) | Has `declarative_base()` fallback at `:633`. |
| `create_feature_models` | `models/feature_flags.py:35` | (audit during Task 2) | |
| `create_holiday_models` | `services/holiday_service.py:36` | (audit during Task 2) | |

**Separate `declarative_base()` instances:**
- `models/user_onboarding.py:24` — **UNCONDITIONAL** module-level (the real offender; `Role` lives here on a private Base).
- `models/esign_models.py:508`, `models/portal_models.py:25`, `models/call_monitoring_models.py:39`, `models/perennia_docs.py:633`, `models/conversation_intelligence_models.py:35` — all **indented try/except fallbacks**; investigation showed portal/call_monitoring/conversation_intelligence already resolve to canonical `db.Base` (their fallback is dead code).

**Genuinely-separate same-named collisions** (different tables, must get distinct names — confirmed by product owner):
- `Responsibility`: `database/models/permission.py:190` (table `responsibilities`, RBAC) vs `models/user_onboarding.py:87` (table `onboarding_responsibilities`).
- `UserResponsibility`: `database/models/permission.py:222` (`user_responsibilities`) vs `models/user_onboarding.py:214` (`onboarding_user_responsibilities`).
- `OnboardingSession`: `models/user_onboarding.py:395` vs `user_onboarding_integration.py:182` (table `onboarding_wizard_sessions`).

**Duplicate onboarding definitions:** `models/user_onboarding.py` (direct classes) and `user_onboarding_integration.py` (factory) define the **same `onboarding_*` tables**. Production registers the **factory** version (`inline_legacy_routes.py:1989`). Decision for this plan: **the factory is canonical**; the direct module becomes thin re-exports.

**Test harness facts:**
- `tests/conftest.py` requires PostgreSQL (`TEST_DATABASE_URL`, default `postgresql://localhost:5432/test_perennia`). Local PG16 is at `/usr/local/opt/postgresql@16/bin`.
- `tests/test_db_helper.py:42 _register_factory_models()` currently registers only the two workflow factories.
- Session teardown `Base.metadata.drop_all()` (`conftest.py:136`) fails on unnamed/`use_alter` FK constraints the multi-pass creator didn't name → must become `DROP SCHEMA public CASCADE`.
- `agent_memories.embedding` is `Vector(1536)`; local PG needs the `vector` extension or those tables are skipped (acceptable for non-memory tests).

**Baseline:** `pytest tests/test_leads_crud.py` → **11 passed, 26 failed** (failures all trace to `configure_mappers()` failing on `Role`/`WorkflowInstance` + teardown). This number is the acceptance metric.

---

## File Structure

- **Create** `backend/model_registry.py` — single `register_all_models()` entry point + `assert_mappers_configure()` helper.
- **Create** `backend/tests/test_model_registry_integrity.py` — the safety-net test (configure_mappers + key relationships resolve).
- **Modify** the 11 factory files — make each idempotent on the *canonical* Base (return cached classes only when bound to the same Base; never hand back stale-Base classes).
- **Modify** `models/user_onboarding.py` — drop its private Base; become re-exports of the canonical onboarding models.
- **Modify** `database/models/permission.py` references / `models/user_onboarding.py` — rename the 3 colliding classes with back-compat aliases.
- **Modify** `backend/main.py` (~line 350) — call `register_all_models(Base)` before `configure_mappers()`.
- **Modify** `backend/tests/conftest.py`, `backend/tests/test_db_helper.py` — use `register_all_models`, resilient teardown.

---

## Task 0: Safety net — model-integrity test (do this FIRST)

**Files:**
- Create: `backend/tests/test_model_registry_integrity.py`
- Reference: `backend/db.py:74`

This test is the verification gate run after **every** subsequent task. It must move from FAIL → PASS as the refactor lands.

- [ ] **Step 1: Write the integrity test**

```python
# backend/tests/test_model_registry_integrity.py
"""Asserts the whole model layer initializes on one Base. The acceptance gate
for the Base-unification refactor."""
import importlib
import pytest


def test_configure_mappers_succeeds():
    """All mappers across all factories + direct models initialize cleanly."""
    from db import Base  # noqa: F401
    # register_all_models is introduced in Task 1; until then this test fails.
    reg = importlib.import_module("model_registry")
    reg.register_all_models()
    from sqlalchemy.orm import configure_mappers
    configure_mappers()  # raises if any relationship() string ref is unresolved


@pytest.mark.parametrize("cls_name,expected_table", [
    ("Role", "onboarding_roles"),
    ("WorkflowInstance", "workflow_instances"),
    ("LeadWorkflowRoleAssignment", "lead_workflow_role_assignments"),
])
def test_key_relationships_registered_on_canonical_base(cls_name, expected_table):
    from db import Base
    import model_registry
    model_registry.register_all_models()
    assert cls_name in Base.registry._class_registry, (
        f"{cls_name} not registered on the canonical db.Base registry"
    )


def test_no_duplicate_class_names_on_canonical_base():
    """No two mapped classes share a name on the canonical registry."""
    from db import Base
    import model_registry
    model_registry.register_all_models()
    seen = {}
    dupes = []
    for key, val in Base.registry._class_registry.items():
        if isinstance(key, str) and hasattr(val, "__name__"):
            if key in seen:
                dupes.append(key)
            seen[key] = val
    assert not dupes, f"Duplicate class names on one Base: {sorted(set(dupes))}"
```

- [ ] **Step 2: Run it — expect failure (module + mappers not ready)**

Run: `cd backend && PYTHONPATH=. TEST_DATABASE_URL=postgresql://localhost:5432/test_perennia ../.venv/bin/python -m pytest tests/test_model_registry_integrity.py -q`
Expected: FAIL (`ModuleNotFoundError: model_registry`).

- [ ] **Step 3: Commit the failing gate**

```bash
git add backend/tests/test_model_registry_integrity.py
git commit -m "test(models): add Base-unification acceptance gate (currently red)"
```

---

## Task 1: Single registration entry point + fix factory Base-binding

**Files:**
- Create: `backend/model_registry.py`
- Modify each factory: `models/workflow_sla.py:108`, `workflow_config_models.py:58`, `user_onboarding_integration.py:26`, and the other 8 factories listed in Ground Truth — to **never return classes bound to a different Base**.

**Root-cause note:** the factories cache by `id(Base)` and, when called with a fresh `Base`, must build on *that* Base. The bug is that some are first called with a throwaway/separate Base (during import) and the cache then returns those for the db.Base call. The fix: key the cache on `id(Base)` AND verify the cached class's `registry` is `Base.registry`; if not, rebuild.

- [ ] **Step 1: Create the registry module**

```python
# backend/model_registry.py
"""Single source of truth for registering every ORM model on the canonical Base.

Call register_all_models() exactly once at app startup (main.py) and in test
setup (conftest) BEFORE configure_mappers(). Order matters: direct-model modules
import first (they self-register on import), then factory models in dependency
order so cross-factory relationship() string refs resolve.
"""
from __future__ import annotations
import importlib
import logging

logger = logging.getLogger(__name__)

# Direct-model modules that self-register on import. Importing them is enough.
_DIRECT_MODEL_MODULES = [
    "database.models",            # canonical Lead/Loan/User/permission/etc.
    "models.smart_docs_models",
    "models.sms_models",
]

# Factory modules in DEPENDENCY ORDER (a factory that owns a class referenced by
# another must run first). user_onboarding owns Role (referenced by workflow_sla);
# workflow_sla owns WorkflowInstance/WorkflowConfiguration (referenced by config).
_FACTORY_CALLS = [
    ("user_onboarding_integration", "create_user_onboarding_models"),
    ("models.workflow_sla", "create_workflow_sla_models"),
    ("workflow_config_models", "create_workflow_config_models"),
    ("models.feature_flags", "create_feature_models"),
    ("models.esign_models", "create_esign_models"),
    ("models.perennia_docs", "create_perennia_docs_models"),
    ("smart_scheduler_models", "create_smart_scheduler_models"),
    ("video_clip_models", "create_video_clip_models"),
    ("video_meeting_models", "create_video_meeting_models"),
    ("scheduler_enhancements", "create_scheduler_enhancement_models"),
    ("services.holiday_service", "create_holiday_models"),
]

_registered = False


def register_all_models(Base=None):
    """Idempotent: imports all direct models, then calls every factory on Base."""
    global _registered
    if Base is None:
        from db import Base as _B
        Base = _B
    for mod in _DIRECT_MODEL_MODULES:
        importlib.import_module(mod)
    for mod_name, fn_name in _FACTORY_CALLS:
        try:
            mod = importlib.import_module(mod_name)
            getattr(mod, fn_name)(Base)
        except Exception as e:
            logger.error("Factory %s.%s failed: %s", mod_name, fn_name, e)
            raise
    _registered = True
    return True


def assert_mappers_configure():
    from sqlalchemy.orm import configure_mappers
    register_all_models()
    configure_mappers()
```

- [ ] **Step 2: Fix each factory's cache to bind to the given Base**

For **every** factory (start with `models/workflow_sla.py`, `workflow_config_models.py`, `user_onboarding_integration.py`), find the cache lookup (e.g. `if base_id in _cache: return _cache[base_id]`) and add a registry-identity guard. Pattern to apply in each:

```python
# at top of create_*_models(Base):
base_id = id(Base)
cached = _models_cache.get(base_id)
if cached is not None:
    # Guard: only reuse if the cached classes belong to THIS Base's registry.
    sample = next(iter(cached.values()))
    if getattr(sample, "registry", None) is Base.registry:
        return cached
    # else fall through and rebuild on the correct Base
```

For factories that use `declarative_base()` *internally* instead of the passed `Base` (audit each — `grep -n "declarative_base\|Base = " <file>`), replace the internal base with the passed `Base`.

- [ ] **Step 3: Run the integrity test**

Run: `cd backend && PYTHONPATH=. TEST_DATABASE_URL=postgresql://localhost:5432/test_perennia ../.venv/bin/python -m pytest tests/test_model_registry_integrity.py::test_configure_mappers_succeeds -q`
Expected: progresses past `Role`/`WorkflowInstance`. Iterate on factory Base-binding until it PASSES. (Use `PYTHONPATH=. ../.venv/bin/python -c "import model_registry; model_registry.assert_mappers_configure()"` for fast feedback.)

- [ ] **Step 4: Wire app startup**

In `backend/main.py` immediately before `configure_mappers()` (~line 349):

```python
from model_registry import register_all_models
register_all_models(Base)
```

- [ ] **Step 5: Commit**

```bash
git add backend/model_registry.py backend/main.py models/workflow_sla.py workflow_config_models.py user_onboarding_integration.py <other factory files touched>
git commit -m "refactor(models): single register_all_models entry point + canonical Base binding"
```

---

## Task 2: Audit + bind the remaining 8 factories to canonical Base

**Files:** `smart_scheduler_models.py`, `video_clip_models.py`, `video_meeting_models.py`, `scheduler_enhancements.py`, `models/esign_models.py`, `models/perennia_docs.py`, `models/feature_flags.py`, `services/holiday_service.py`

- [ ] **Step 1: For each, confirm it builds on the passed Base**

Run for each file: `grep -nE "declarative_base|Base\b" <file> | head`. If it has an internal `declarative_base()` used for model definitions (not just a typed default arg), change those classes to use the passed `Base`. Apply the same cache-guard from Task 1 Step 2 if it caches.

- [ ] **Step 2: Run integrity test after each file**

Run: `cd backend && PYTHONPATH=. ../.venv/bin/python -c "import model_registry; model_registry.assert_mappers_configure()" && echo OK`
Expected: `OK` (no traceback). Fix one file at a time.

- [ ] **Step 3: Commit per file or as a group**

```bash
git add <factory files> && git commit -m "refactor(models): bind remaining factories to canonical Base"
```

---

## Task 3: Rename genuinely-separate same-named collisions

**Files:**
- Modify: `models/user_onboarding.py` (and/or `user_onboarding_integration.py` — whichever is canonical after Task 4)
- Verify refs: `routes/user_creation_routes.py`, `routes/onboarding_extended_routes.py`, `seeds/user_onboarding_seed.py`

Rename the onboarding-side classes (distinct entities, confirmed) and keep aliases so existing imports/instantiations work.

- [ ] **Step 1: Rename + alias**

In the canonical onboarding model definitions:
- `class Responsibility` → `class OnboardingResponsibility`; add `Responsibility = OnboardingResponsibility`.
- `class UserResponsibility` → `class OnboardingUserResponsibility`; add `UserResponsibility = OnboardingUserResponsibility`.
- `class OnboardingSession` (the `onboarding_wizard_sessions` one) is already distinct in name from the SLA/other models; if it still collides after Task 4 consolidation, rename the loser to `OnboardingWizardSession` + alias.
- Update internal `relationship("Responsibility")` → `relationship("OnboardingResponsibility")` etc. (in user_onboarding the refs are at lines 81, 145, 188, 229).

- [ ] **Step 2: Grep for external string-based relationship refs to the renamed names**

Run: `cd backend && grep -rnE "relationship\(\"(Responsibility|UserResponsibility)\"" --include="*.py" . | grep -v permission.py`
Expected: none outside the onboarding module. If any exist, update them.

- [ ] **Step 3: Run integrity test (no-dupes assertion now meaningful)**

Run: `cd backend && PYTHONPATH=. ../.venv/bin/python -m pytest tests/test_model_registry_integrity.py::test_no_duplicate_class_names_on_canonical_base -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add models/user_onboarding.py user_onboarding_integration.py
git commit -m "refactor(models): distinct names for onboarding Responsibility/UserResponsibility (+aliases)"
```

---

## Task 4: Collapse duplicate onboarding definitions (direct vs factory)

**Files:**
- Modify: `models/user_onboarding.py` (becomes thin re-exports)
- Reference: `user_onboarding_integration.py:26` (canonical factory)

Production registers the **factory** version. Make `models/user_onboarding.py` stop defining its own classes/Base and instead re-export the factory's models so all importers (`routes/user_creation_routes.py`, `routes/onboarding_extended_routes.py`, `seeds/user_onboarding_seed.py`) get the single canonical classes.

- [ ] **Step 1: Replace direct class defs with re-exports**

```python
# models/user_onboarding.py (top, replacing the private Base + class defs)
"""Back-compat shim. Canonical onboarding models are built by
user_onboarding_integration.create_user_onboarding_models() on the canonical Base.
This module re-exports them so existing `from models.user_onboarding import X`
keeps working."""
from db import Base  # noqa: F401
from user_onboarding_integration import create_user_onboarding_models

_models = create_user_onboarding_models(Base)
Role = _models["Role"]
Category = _models["Category"]
OnboardingResponsibility = _models["OnboardingResponsibility"]
Responsibility = OnboardingResponsibility  # alias
# ... re-export every key in _models, plus the back-compat aliases from Task 3.
```

(Enumerate every key returned by the factory — run `PYTHONPATH=. ../.venv/bin/python -c "from db import Base; from user_onboarding_integration import create_user_onboarding_models as f; print(list(f(Base).keys()))"` and re-export each.)

- [ ] **Step 2: Run onboarding route import smoke**

Run: `cd backend && PYTHONPATH=. ../.venv/bin/python -c "import routes.user_creation_routes, routes.onboarding_extended_routes; print('imports OK')"`
Expected: `imports OK`.

- [ ] **Step 3: Run integrity test**

Run: `cd backend && PYTHONPATH=. ../.venv/bin/python -m pytest tests/test_model_registry_integrity.py -q`
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add models/user_onboarding.py
git commit -m "refactor(models): collapse onboarding to one definition (factory canonical, direct module re-exports)"
```

---

## Task 5: Harden the dead `declarative_base()` fallbacks

**Files:** `models/portal_models.py:25`, `models/call_monitoring_models.py:39`, `models/conversation_intelligence_models.py:35`, `models/esign_models.py:508`, `models/perennia_docs.py:633`

These are try/except fallbacks that currently resolve to canonical but are latent landmines.

- [ ] **Step 1: For each, make the fallback raise instead of forking a new Base**

Replace the `except ...: Base = declarative_base()` fallback with an explicit import error (so a broken import surfaces loudly instead of silently creating a second registry):

```python
try:
    from db import Base
except Exception as e:  # fail loud — a second Base silently breaks the registry
    raise ImportError(f"{__name__} requires the canonical db.Base") from e
```

- [ ] **Step 2: Run integrity test + import smoke**

Run: `cd backend && PYTHONPATH=. ../.venv/bin/python -c "import model_registry; model_registry.assert_mappers_configure(); print('OK')"`
Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add models/portal_models.py models/call_monitoring_models.py models/conversation_intelligence_models.py models/esign_models.py models/perennia_docs.py
git commit -m "refactor(models): remove dead declarative_base fallbacks; require canonical Base"
```

---

## Task 6: Test harness — use register_all_models + resilient teardown

**Files:** `backend/tests/conftest.py`, `backend/tests/test_db_helper.py`

- [ ] **Step 1: Route test registration through the canonical entry point**

In `tests/test_db_helper.py` `_register_factory_models(Base)` (line 42), replace its body with:

```python
def _register_factory_models(Base):
    from model_registry import register_all_models
    register_all_models(Base)
```

- [ ] **Step 2: Make session teardown stale-safe**

In `tests/conftest.py:136`, replace `Base.metadata.drop_all(bind=test_engine)` with:

```python
    with test_engine.connect() as _c:
        _c.execute(text("DROP SCHEMA public CASCADE"))
        _c.execute(text("CREATE SCHEMA public"))
        _c.commit()
```

- [ ] **Step 3: Run the lead suite — the acceptance metric**

Run: `cd backend && PATH="/usr/local/opt/postgresql@16/bin:$PATH" bash -c 'dropdb -h localhost test_perennia 2>/dev/null; createdb -h localhost test_perennia; TEST_DATABASE_URL=postgresql://localhost:5432/test_perennia ../.venv/bin/python -m pytest tests/test_leads_crud.py -q'`
Expected: **0 failures from mapper/teardown** (was 26). Remaining failures, if any, are genuine test-logic issues to triage individually — they are out of scope for *this* plan and get their own tickets.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/conftest.py backend/tests/test_db_helper.py
git commit -m "test(models): register via canonical entry point + stale-safe teardown"
```

---

## Task 7: Full-suite regression sweep

- [ ] **Step 1: Run the broader suite, capture mapper-related failures only**

Run: `cd backend && PATH="/usr/local/opt/postgresql@16/bin:$PATH" TEST_DATABASE_URL=postgresql://localhost:5432/test_perennia ../.venv/bin/python -m pytest tests/ -q -x -k "lead or loan or auth or pipeline" 2>&1 | tail -30`
Expected: no `failed to locate a name` / `Multiple classes found` / `DROP CONSTRAINT` errors. Triage anything else as separate work.

- [ ] **Step 2: Production smoke — app boots and configures mappers cleanly**

Run: `cd backend && PYTHONPATH=. ../.venv/bin/python -c "import main; from sqlalchemy.orm import configure_mappers; configure_mappers(); print('app mappers OK')"`
Expected: `app mappers OK` (no warning from `main.py:351`).

- [ ] **Step 3: Commit any final fixes + update memory note**

```bash
git commit -am "refactor(models): Base unification complete — single registry, suite green"
```

---

## Risk & Rollback

- **Each task is an independent commit** — `git revert <sha>` rolls back one step without unwinding the rest.
- **Highest-risk task is #4** (collapsing onboarding to re-exports): if any importer relies on a direct class identity that differs from the factory's, it surfaces at Step 2 import smoke. Mitigation: the re-export keeps the same public names; verify `routes/user_creation_routes.py` + `routes/onboarding_extended_routes.py` import-smoke before committing.
- **Production behavior:** these changes make `configure_mappers()` at `main.py:350` *succeed* instead of warn. That is strictly safer (previously-unresolved relationships were latent runtime risks). No DB schema changes — table names are unchanged throughout, so **no migration is required**.
- **Do not** ship Task 1–5 partially to prod without Task 6/7 green locally — a half-bound registry can make a currently-warned relationship into a hard error on a live code path.

## Out of scope (separate tickets)
- Genuine test-logic failures unrelated to mapper init (surfaced in Task 6/7).
- The wider "duplication & drift" items from the architecture review (orchestration unification, gateway migration, legacy-voice retirement) — these become *doable* once this plan lands a green suite.
- pgvector for local tests (memory-table tests) — install `vector` extension in `test_perennia` if/when memory tests are in scope.
