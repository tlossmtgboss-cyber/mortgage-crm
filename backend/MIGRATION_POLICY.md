# Migration Policy (March 2026)

## Rules

1. ALL schema changes MUST go through Alembic migrations
2. NO ad-hoc Python migration scripts (run_*migration*.py pattern)
3. Test migrations locally before pushing
4. Each migration must be reversible (include downgrade)

## Creating a migration

```
cd backend && alembic revision --autogenerate -m "description" && alembic upgrade head
```

## Legacy scripts

The 185+ ad-hoc scripts in backend/ are archived. Do not use them.
