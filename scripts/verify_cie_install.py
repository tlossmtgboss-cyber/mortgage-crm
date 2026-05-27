#!/usr/bin/env python3
"""Verify CIE installation: tables, RLS, env vars, Redis, Celery, LLM key."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


def check(label: str, ok: bool, detail: str = "") -> bool:
    status = "OK" if ok else "FAIL"
    line = f"  [{status}] {label}"
    if detail:
        line += f" — {detail}"
    print(line)
    return ok


def main() -> int:
    results: list[bool] = []
    print("\n=== CIE Installation Verification ===\n")

    # 1. Config loads
    try:
        from engine.config import cie_settings
        results.append(check("Config loads", True, f"ENABLED={cie_settings.ENABLED}"))
    except Exception as e:
        results.append(check("Config loads", False, str(e)))
        print("\nCannot proceed without config. Exiting.")
        return 1

    # 2. Models importable
    try:
        from engine.models import CIECallRecord, CIEIntelligenceReport
        results.append(check("Models import", True))
    except Exception as e:
        results.append(check("Models import", False, str(e)))

    # 3. Pipeline compiles
    try:
        from engine.pipeline import cie_pipeline
        results.append(check("Pipeline compiles", True))
    except Exception as e:
        results.append(check("Pipeline compiles", False, str(e)))

    # 4. Source adapters
    try:
        from engine.sources import get_adapter
        get_adapter("vapi")
        get_adapter("telnyx")
        results.append(check("Source adapters", True, "vapi + telnyx"))
    except Exception as e:
        results.append(check("Source adapters", False, str(e)))

    # 5. Database tables exist
    try:
        from sqlalchemy import inspect as sa_inspect, text
        from db import engine
        inspector = sa_inspect(engine)
        tables = inspector.get_table_names()
        has_calls = "cie_call_records" in tables
        has_reports = "cie_intelligence_reports" in tables
        results.append(check("DB tables", has_calls and has_reports,
                             f"calls={has_calls} reports={has_reports}"))
    except Exception as e:
        results.append(check("DB tables", False, str(e)))

    # 6. RLS policies
    try:
        with engine.connect() as conn:
            rls_rows = conn.execute(text(
                "SELECT tablename, policyname FROM pg_policies "
                "WHERE tablename IN ('cie_call_records', 'cie_intelligence_reports')"
            )).fetchall()
            rls_count = len(rls_rows)
            results.append(check("RLS policies", rls_count >= 2, f"{rls_count} policies"))
    except Exception as e:
        results.append(check("RLS policies", False, str(e)))

    # 7. Env vars
    anthropic_key = bool(os.getenv("ANTHROPIC_API_KEY"))
    results.append(check("ANTHROPIC_API_KEY", anthropic_key))

    redis_url = os.getenv("REDIS_URL", "")
    results.append(check("REDIS_URL", bool(redis_url), redis_url[:30] + "..." if redis_url else "not set"))

    # 8. Celery task discovery
    try:
        from tasks.celery_app import celery_app
        task_names = list(celery_app.tasks.keys())
        cie_task = "engine.worker.tasks.process_call_pipeline"
        found = cie_task in task_names
        results.append(check("Celery task registered", found, cie_task))
    except Exception as e:
        results.append(check("Celery task registered", False, str(e)))

    # Summary
    passed = sum(results)
    total = len(results)
    print(f"\n  {passed}/{total} checks passed.\n")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
