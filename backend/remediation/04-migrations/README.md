# 04 — Alembic Adoption

**Finding addressed:** #4 (no migration framework, 243 hand-written migrations with `checkfirst=True`)

## Strategy: Baseline, Don't Backfill

The 243 existing hand-written migrations have already run. Rewriting them as Alembic revisions is wasted work and risks introducing drift. Instead:

1. **Baseline from current production schema.** Alembic introspects the live DB and generates a single "starting point" migration.
2. **Mark production as up-to-date** at that baseline revision — no replay.
3. **All new schema changes** go through `alembic revision --autogenerate`.
4. **Hand-written migrations are deprecated.** Delete the old migration runner once the baseline is in place.

## Execution

```bash
# From repo root, in backend/:
cd backend

# 1. Install
pip install alembic

# 2. Initialize (creates alembic/ + alembic.ini)
alembic init -t async alembic

# 3. Replace the generated alembic/env.py with ours (async-aware)
cp ../04-migrations/env.py alembic/env.py
cp ../04-migrations/alembic.ini ./alembic.ini
cp ../04-migrations/script.py.mako alembic/script.py.mako

# 4. Generate the baseline revision from the live schema
export DATABASE_URL=$PROD_DATABASE_URL  # read-only is fine
alembic revision --autogenerate -m "baseline from production schema"

# 5. Review alembic/versions/*_baseline_from_production_schema.py
#    Verify it matches current schema. DELETE any `op.drop_*` calls — the
#    autogen will propose dropping things it doesn't know about.

# 6. Stamp the DB without running (production already has this schema)
alembic stamp head

# 7. Verify
alembic current  # should print the baseline revision
```

## Going Forward

```bash
# Make an ORM model change, then:
alembic revision --autogenerate -m "add foo column to bar"
# Review the generated migration file
alembic upgrade head  # apply locally
# Commit the migration file with your PR
```

CI enforces `alembic upgrade head` runs clean against a migration-test DB before merge.

## Retiring the old runner

After baseline is live in production for a full deploy cycle:

```bash
# Delete the legacy migration runner
rm backend/app/db/run_migrations.py
rm -rf backend/app/db/migrations_manual/
# Remove `checkfirst=True` from any remaining Base.metadata.create_all calls
grep -rn "checkfirst=True" backend/ && echo "!! found usages — replace with alembic"
```
