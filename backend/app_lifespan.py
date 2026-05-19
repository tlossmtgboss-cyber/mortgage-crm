"""
Application Lifespan

Startup and shutdown event handlers for the FastAPI application.
Extracted from main.py — structural move only, no logic changes.
"""

import logging
import os

from fastapi import FastAPI

logger = logging.getLogger(__name__)

# Module-level alias — see note in startup_event about scoping
_os = os


def register_startup_event(app: FastAPI, engine, scheduler, SessionLocal, _startup_degradation_check=None):
    """Register the startup event handler on the app."""

    @app.on_event("startup")  # Deprecated in FastAPI >=0.103; migrate to lifespan when feasible
    async def startup_event():
        """Initialize the scheduler on app startup and run critical schema migrations."""
        # Skip DB-dependent startup when running under pytest
        if _os.environ.get("TESTING") == "1":
            logger.info("Skipping startup DB operations (TESTING=1)")
            return

        # Run all startup migrations
        from startup_migrations import run_all_startup_migrations
        run_all_startup_migrations(engine)

        # SEC-005: Validate RLS policies
        try:
            _validate_rls_policies(engine)
        except Exception as e:
            logger.warning(f"RLS policy validation skipped: {e}")

        # Initialize query timing middleware
        try:
            from middleware.query_timing import setup_query_timing
            setup_query_timing(engine)
            logger.info("Query timing middleware initialized")
        except Exception as e:
            logger.warning(f"Query timing middleware skipped: {e}")

        # Initialize scheduler
        try:
            from services.scheduler_service import init_scheduler
            init_scheduler()
            logger.info("Scheduler initialized and started (workflow tasks, SLA tracking, appointment reminders)")
        except Exception as e:
            logger.error(f"Scheduler failed to start: {e}")
            import traceback
            traceback.print_exc()

        # Register scheduler error handler
        try:
            from middleware.scheduler_error_handler import register_scheduler_error_handlers
            register_scheduler_error_handlers(app)
            logger.info("Scheduler exception handler registered")
        except Exception as e:
            logger.warning(f"Scheduler error handler skipped: {e}")

        # Register event bus subscribers
        try:
            from services.event_subscribers import register_all_subscribers
            register_all_subscribers()
            logger.info("Event bus subscribers registered")
        except Exception as e:
            logger.warning(f"Event bus subscribers skipped: {e}")

        # Register agent-specific event subscribers
        try:
            from services.agent_event_subscribers import register_agent_subscribers
            register_agent_subscribers()
            logger.info("Agent event subscribers registered")
        except Exception as e:
            logger.warning(f"Agent event subscribers skipped: {e}")

        # Agent message processor is now in the centralized job registry
        # (services/scheduled_jobs.py) and registered via register_from_registry().
        # No separate registration needed here.

        # Register autonomous AI agents via unified scheduler for lock wrapping
        try:
            from agents.autonomous.loop import register_all_autonomous_agents
            from services.scheduler_service import scheduler_service
            agent_count = register_all_autonomous_agents(scheduler_service)
            logger.info(f"{agent_count} autonomous agents registered with scheduler")
        except Exception as e:
            logger.warning(f"Autonomous agents registration skipped: {e}")

        # Register SOC 2 compliance jobs via unified scheduler
        try:
            from services.scheduler_service import scheduler_service as _svc
            _register_soc2_jobs_unified(_svc)
            logger.info("SOC 2 compliance jobs registered via unified scheduler")
        except Exception as e:
            logger.warning(f"SOC 2 unified scheduler registration skipped: {e}")

        # Start autonomous AI task executor
        try:
            from services.autonomous.task_executor import get_executor
            _task_executor = get_executor()
            import asyncio
            asyncio.create_task(_task_executor.start())
            logger.info("Autonomous AI task executor started")
        except Exception as e:
            logger.warning(f"Autonomous task executor skipped: {e}")

        # Vapi phone number health check
        try:
            import asyncio as _aio_vapi
            _aio_vapi.create_task(_check_vapi_phone_config())
        except Exception as e:
            logger.warning(f"Vapi phone config check skipped: {e}")

        # SOC 2 compliance scheduled jobs — registered via unified scheduler above.
        # Legacy fallback: if unified registration failed, try direct registration.
        try:
            from services.scheduler_service import scheduler_service as _svc_check
            soc2_registered = any(
                j.id.startswith("soc2_") for j in _svc_check.scheduler.get_jobs()
            )
            if not soc2_registered:
                from soc2_compliance.scheduler import register_soc2_jobs
                register_soc2_jobs(scheduler)
                logger.info("SOC 2 compliance jobs registered (legacy fallback)")
        except Exception as e:
            logger.warning(f"SOC 2 scheduler registration skipped: {e}")

        # Record deployment event for SOC 2 change management
        try:
            from db import SessionLocal
            from soc2_compliance.services.change_management_service import ChangeManagementService
            cms_session = SessionLocal()
            cms = ChangeManagementService(cms_session)
            cms.record_deployment(
                title=f"Application startup — {_os.getenv('RAILWAY_DEPLOYMENT_ID', 'local')[:12]}",
                description="Automated deployment event recorded at application startup",
                git_commit=_os.getenv("RAILWAY_GIT_COMMIT_SHA"),
                git_branch=_os.getenv("RAILWAY_GIT_BRANCH"),
                deployment_id=_os.getenv("RAILWAY_DEPLOYMENT_ID"),
            )
            cms_session.close()
        except Exception as e:
            logger.debug(f"SOC 2 deployment record skipped: {e}")

        # Start DB connection pool monitor
        try:
            from services.db_monitor import start_pool_monitor
            start_pool_monitor()
            logger.info("DB connection pool monitor started")
        except Exception as e:
            logger.warning(f"DB pool monitor failed to start: {e}")

        # Post-startup route health check
        critical_paths = ["/api/v1/leads", "/api/v1/loans", "/api/v1/pipeline", "/api/v1/auth", "/api/v1/ai"]
        registered_paths = [route.path for route in app.routes if hasattr(route, 'path')]
        missing = [p for p in critical_paths if not any(p in rp for rp in registered_paths)]
        if missing:
            logger.error(f"CRITICAL: Missing route registrations: {missing}")
        else:
            logger.info(f"All {len(critical_paths)} critical route groups verified")

        # Graceful degradation startup check
        try:
            if _startup_degradation_check is not None:
                import asyncio
                asyncio.create_task(_startup_degradation_check())
                logger.info("Graceful degradation startup check scheduled (background)")
        except Exception as e:
            logger.warning(f"Graceful degradation startup check skipped: {e}")

        # Verify certificate pins
        try:
            from routes.security_certificate_routes import _run_startup_pin_check
            import asyncio
            asyncio.create_task(_run_startup_pin_check())
            logger.info("Certificate pin verification scheduled (background)")
        except Exception as e:
            logger.warning(f"Certificate pin verification skipped: {e}")

        # Microsoft 365 scheduled tasks — register via unified scheduler
        try:
            from integrations.microsoft365.tasks import (
                renew_expiring_subscriptions as _ms365_renew,
                delta_sync_all_active_accounts as _ms365_delta,
                garbage_collect_subscriptions as _ms365_gc,
            )
            from services.scheduler_service import scheduler_service as _sched_svc

            async def _ms365_renew_job():
                from db import SessionLocal
                db = SessionLocal()
                try:
                    await _ms365_renew(db)
                    db.commit()
                except Exception as _e:
                    db.rollback()
                    logger.error(f"MS365 subscription renewal failed: {_e}")
                finally:
                    db.close()

            async def _ms365_delta_job():
                from db import SessionLocal
                db = SessionLocal()
                try:
                    await _ms365_delta(db)
                    db.commit()
                except Exception as _e:
                    db.rollback()
                    logger.error(f"MS365 delta sync failed: {_e}")
                finally:
                    db.close()

            async def _ms365_gc_job():
                from db import SessionLocal
                db = SessionLocal()
                try:
                    await _ms365_gc(db)
                    db.commit()
                except Exception as _e:
                    db.rollback()
                    logger.error(f"MS365 subscription GC failed: {_e}")
                finally:
                    db.close()

            _sched_svc.register_job("ms365_renew_subs", _ms365_renew_job, "interval",
                                    description="MS365 subscription renewal", lock_ttl=120, minutes=15)
            _sched_svc.register_job("ms365_delta_sync", _ms365_delta_job, "interval",
                                    description="MS365 delta sync", lock_ttl=600, hours=6)
            _sched_svc.register_job("ms365_gc_subs", _ms365_gc_job, "cron",
                                    description="MS365 subscription garbage collection", lock_ttl=120, hour=3, minute=0)
            logger.info("Microsoft 365 scheduled tasks registered via unified scheduler (renew/15m, delta/6h, GC/daily)")
        except Exception as e:
            logger.warning(f"Microsoft 365 scheduled tasks skipped: {e}")

        # Outlook inbox/sent sync — register via unified scheduler
        try:
            from services.email_inbox_sync import sync_all_users as _email_sync_all
            from services.scheduler_service import scheduler_service as _sched_svc2

            async def _email_inbox_sync_job():
                try:
                    result = await _email_sync_all()
                    if result.get("stored") or result.get("matched"):
                        logger.info(
                            "Email inbox sync: users=%d stored=%d matched=%d",
                            result.get("users", 0),
                            result.get("stored", 0),
                            result.get("matched", 0),
                        )
                except Exception as _e:
                    logger.error(f"Email inbox sync failed: {_e}")

            _sched_svc2.register_job("email_inbox_sync", _email_inbox_sync_job, "interval",
                                     description="Outlook inbox/sent email sync", lock_ttl=120, minutes=5)
            logger.info("Email inbox sync scheduled via unified scheduler (every 5m)")
        except Exception as e:
            logger.warning(f"Email inbox sync skipped: {e}")

        # LangGraph thread pool executor
        from concurrent.futures import ThreadPoolExecutor
        langgraph_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="langgraph")
        app.state.langgraph_executor = langgraph_executor
        logger.info("LangGraph thread pool executor started (4 workers)")


def register_shutdown_event(app: FastAPI):
    """Register the shutdown event handler on the app."""

    @app.on_event("shutdown")  # Deprecated in FastAPI >=0.103; migrate to lifespan when feasible
    async def shutdown_event():
        """Shutdown handler — clean up resources."""
        # Shut down the unified scheduler service
        try:
            from services.scheduler_service import scheduler_service
            scheduler_service.stop()
            logger.info("Unified scheduler service shut down")
        except Exception as e:
            logger.warning(f"Scheduler shutdown error: {e}")

        if hasattr(app.state, "langgraph_executor"):
            app.state.langgraph_executor.shutdown(wait=False)
            logger.info("LangGraph thread pool executor shut down")
        try:
            from integrations.imessage import shutdown_clients
            await shutdown_clients()
            logger.info("BlueBubbles httpx clients closed")
        except Exception as _exc:  # noqa: BLE001
            pass


def register_seed_demo_endpoint(app: FastAPI, SECRET_KEY: str):
    """Register the temporary seed-demo endpoint."""
    from fastapi import HTTPException, Request
    from fastapi.responses import JSONResponse

    @app.post("/api/v1/management/seed-demo")
    async def seed_demo_account(request: Request):
        """One-time endpoint to create App Store review demo account. Protected by SECRET_KEY."""
        import secrets as _secrets_mod

        _env = _os.getenv("RAILWAY_ENVIRONMENT", _os.getenv("ENVIRONMENT", "development")).lower()
        if _env == "production":
            raise HTTPException(status_code=403, detail="Seed endpoint disabled in production")

        body = await request.json()
        auth = (body.get("key", "") or "").strip()
        expected = SECRET_KEY.strip()
        admin_key = _os.getenv("ADMIN_API_KEY", "").strip()
        key_ok = auth and (
            _secrets_mod.compare_digest(auth, expected)
            or (admin_key and _secrets_mod.compare_digest(auth, admin_key))
        )
        if not key_ok:
            raise HTTPException(status_code=403, detail="Forbidden")

        try:
            from database import SessionLocal
            import importlib
            import scripts.seed_demo_account as seed_mod
            importlib.reload(seed_mod)

            db = SessionLocal()
            try:
                seed_mod.main(external_session=db)
                return {"status": "success", "message": "Demo account seeded with full data"}
            finally:
                db.close()
        except Exception as e:
            logger.exception("Demo seed failed")
            return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


def _register_soc2_jobs_unified(sched_svc):
    """Register SOC 2 compliance jobs via the unified SchedulerService.

    This replaces the direct APScheduler registration in
    soc2_compliance/scheduler.py with distributed-lock-wrapped versions.
    """
    from soc2_compliance.scheduler import (
        run_daily_compliance_scan,
        run_retention_enforcement,
        run_data_classification_seed,
    )

    sched_svc.register_job(
        "soc2_daily_compliance_scan", run_daily_compliance_scan, "cron",
        description="SOC 2 Daily Compliance Scan",
        lock_ttl=300, hour=2, minute=15,
    )
    sched_svc.register_job(
        "soc2_daily_retention", run_retention_enforcement, "cron",
        description="SOC 2 Daily Retention Enforcement",
        lock_ttl=300, hour=3, minute=0,
    )
    sched_svc.register_job(
        "soc2_weekly_classification", run_data_classification_seed, "cron",
        description="SOC 2 Weekly Data Classification Update",
        lock_ttl=300, day_of_week="sun", hour=4, minute=0,
    )


def _validate_rls_policies(eng):
    """Verify RLS policies exist on all tenant-scoped tables."""
    from sqlalchemy import text as _text

    if not str(eng.url).startswith("postgresql"):
        logger.debug("RLS policy validation skipped (non-PostgreSQL)")
        return

    try:
        with eng.connect() as conn:
            tenant_tables = conn.execute(_text("""
                SELECT table_name
                FROM information_schema.columns
                WHERE column_name = 'organization_id'
                  AND table_schema = 'public'
                ORDER BY table_name
            """)).fetchall()
            tenant_table_names = {row[0] for row in tenant_tables}

            if not tenant_table_names:
                logger.info("RLS validation: no tenant-scoped tables found")
                return

            rls_tables = conn.execute(_text("""
                SELECT DISTINCT tablename
                FROM pg_policies
                WHERE schemaname = 'public'
            """)).fetchall()
            rls_table_names = {row[0] for row in rls_tables}

            rls_enabled = conn.execute(_text("""
                SELECT relname
                FROM pg_class
                WHERE relrowsecurity = true
                  AND relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public')
            """)).fetchall()
            rls_enabled_names = {row[0] for row in rls_enabled}

            uncovered = tenant_table_names - rls_table_names
            not_enabled = rls_table_names - rls_enabled_names

            if uncovered:
                logger.warning(
                    "SEC-005: %d tenant-scoped tables have NO RLS policy: %s",
                    len(uncovered), ", ".join(sorted(uncovered)),
                )
            else:
                logger.info(
                    "SEC-005: All %d tenant-scoped tables have RLS policies",
                    len(tenant_table_names),
                )

            if not_enabled:
                logger.warning(
                    "SEC-005: %d tables have RLS policies but ROW SECURITY not enabled: %s",
                    len(not_enabled), ", ".join(sorted(not_enabled)),
                )
    except Exception as e:
        logger.error(f"SEC-005: RLS policy validation failed: {e}")


async def _check_vapi_phone_config():
    """Startup check: verify Vapi phone number has assistantId set and log config."""
    import httpx

    vapi_api_key = _os.getenv("VAPI_API_KEY")
    if not vapi_api_key:
        logger.warning("VAPI_API_KEY not set — skipping phone config check")
        return

    assistant_id = _os.getenv("VAPI_ASSISTANT_ID", "120e239e-4d19-4e43-ad92-1f8b07d08c8c")
    phone_number_id = "6adaf897-34d7-42d5-bc34-f1a17162a453"
    headers = {"Authorization": f"Bearer {vapi_api_key}", "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://api.vapi.ai/phone-number/{phone_number_id}",
                headers=headers, timeout=10,
            )
            if resp.status_code != 200:
                logger.error("Vapi phone config check FAILED: status=%s body=%s", resp.status_code, resp.text[:200])
                return

            phone = resp.json()
            current_aid = phone.get("assistantId")
            current_surl = phone.get("serverUrl")
            logger.info(
                "Vapi phone config: number=%s assistantId=%s serverUrl=%s squadId=%s",
                phone.get("number"), current_aid, current_surl, phone.get("squadId"),
            )

            if current_aid == assistant_id:
                logger.info("Vapi phone config OK — assistantId matches")
                a_resp = await client.get(
                    f"https://api.vapi.ai/assistant/{assistant_id}",
                    headers=headers, timeout=10,
                )
                if a_resp.status_code == 200:
                    a = a_resp.json()
                    logger.info(
                        "Vapi assistant config: name=%s model=%s/%s voice=%s/%s serverUrl=%s",
                        a.get("name"),
                        a.get("model", {}).get("provider"), a.get("model", {}).get("model"),
                        a.get("voice", {}).get("provider"), a.get("voice", {}).get("voiceId"),
                        a.get("serverUrl"),
                    )
                    surl = a.get("serverUrl", "")
                    if "app.perenniaai.com" in surl:
                        logger.warning("Vapi assistant has WRONG serverUrl: %s — fixing to api.perenniaai.com", surl)
                        fix_resp = await client.patch(
                            f"https://api.vapi.ai/assistant/{assistant_id}",
                            headers=headers,
                            json={"serverUrl": "https://api.perenniaai.com/api/vapi/webhook"},
                            timeout=10,
                        )
                        logger.info("Vapi assistant serverUrl fix: status=%s", fix_resp.status_code)
                else:
                    logger.error("Could not fetch Vapi assistant %s: %s", assistant_id, a_resp.status_code)
                return

            logger.warning(
                "Vapi phone number MISSING assistantId (has: assistantId=%s serverUrl=%s) — restoring",
                current_aid, current_surl,
            )
            fix_resp = await client.patch(
                f"https://api.vapi.ai/phone-number/{phone_number_id}",
                headers=headers,
                json={"assistantId": assistant_id, "serverUrl": None},
                timeout=15,
            )
            logger.info("Vapi phone config restore: status=%s", fix_resp.status_code)
            if fix_resp.status_code == 200:
                logger.info("Vapi phone number restored to assistantId=%s", assistant_id)
            else:
                logger.error("Vapi phone restore FAILED: %s", fix_resp.text[:200])
    except Exception as e:
        logger.error("Vapi phone config check error: %s", e)
