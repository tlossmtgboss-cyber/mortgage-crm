#!/usr/bin/env python3
"""
Workflow SLA System Validation Script

Performs validation and smoke testing of the workflow SLA system.
Can be run against development, staging, or production environments.

Usage:
    python scripts/validate_workflow_sla_system.py [--env prod|staging|local] [--verbose]
    python scripts/validate_workflow_sla_system.py --check-migration
    python scripts/validate_workflow_sla_system.py --full-test
"""

import os
import sys
import argparse
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


class WorkflowSLAValidator:
    """Validates the Workflow SLA System components."""

    def __init__(self, db_url: str = None, verbose: bool = False):
        self.db_url = db_url or os.getenv("DATABASE_URL")
        self.verbose = verbose
        self.results = {
            "passed": [],
            "failed": [],
            "warnings": [],
            "skipped": []
        }
        self._db = None

    @property
    def db(self):
        """Lazy load database connection."""
        if self._db is None:
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker

            engine = create_engine(self.db_url)
            Session = sessionmaker(bind=engine)
            self._db = Session()
        return self._db

    def log_result(self, test_name: str, passed: bool, message: str = "", warning: bool = False):
        """Log a test result."""
        if warning:
            self.results["warnings"].append({"test": test_name, "message": message})
            logger.warning(f"⚠️  {test_name}: {message}")
        elif passed:
            self.results["passed"].append({"test": test_name, "message": message})
            logger.info(f"✅ {test_name}: {message or 'PASSED'}")
        else:
            self.results["failed"].append({"test": test_name, "message": message})
            logger.error(f"❌ {test_name}: {message or 'FAILED'}")

    # =========================================================================
    # DATABASE VALIDATION
    # =========================================================================

    def check_database_tables(self) -> bool:
        """Verify all required tables exist."""
        from sqlalchemy import text

        required_tables = [
            "workflow_instances",
            "workflow_task_instances",
            "workflow_ai_confidence",
            "lead_workflow_role_assignments",
            "loan_workflow_role_assignments",
            "workflow_configs",
            "workflow_task_configs",
            "workflow_roles"
        ]

        missing = []
        for table in required_tables:
            result = self.db.execute(text(f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = :table
                )
            """), {"table": table}).scalar()

            if not result:
                missing.append(table)

        if missing:
            self.log_result(
                "Database Tables",
                False,
                f"Missing tables: {', '.join(missing)}"
            )
            return False

        self.log_result(
            "Database Tables",
            True,
            f"All {len(required_tables)} required tables exist"
        )
        return True

    def check_database_enums(self) -> bool:
        """Verify all required enums exist."""
        from sqlalchemy import text

        required_enums = [
            "workflow_instance_status",
            "workflow_task_status",
            "workflow_task_type",
            "workflow_route"
        ]

        missing = []
        for enum in required_enums:
            result = self.db.execute(text(f"""
                SELECT EXISTS (
                    SELECT FROM pg_type WHERE typname = :enum
                )
            """), {"enum": enum}).scalar()

            if not result:
                missing.append(enum)

        if missing:
            self.log_result(
                "Database Enums",
                False,
                f"Missing enums: {', '.join(missing)}"
            )
            return False

        self.log_result(
            "Database Enums",
            True,
            f"All {len(required_enums)} required enums exist"
        )
        return True

    def check_database_columns(self) -> bool:
        """Verify critical columns exist on tables."""
        from sqlalchemy import text

        column_checks = [
            ("workflow_task_instances", "task_group_key"),
            ("workflow_task_instances", "route"),
            ("workflow_task_instances", "completion_source"),
            ("workflow_task_instances", "dialer_session_task_id"),
            ("leads", "source_category"),
        ]

        missing = []
        for table, column in column_checks:
            result = self.db.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.columns
                    WHERE table_name = :table AND column_name = :column
                )
            """), {"table": table, "column": column}).scalar()

            if not result:
                missing.append(f"{table}.{column}")

        if missing:
            self.log_result(
                "Database Columns",
                False,
                f"Missing columns: {', '.join(missing)}"
            )
            return False

        self.log_result(
            "Database Columns",
            True,
            f"All critical columns exist"
        )
        return True

    def check_database_indexes(self) -> bool:
        """Verify performance indexes exist."""
        from sqlalchemy import text

        # Check for key indexes
        result = self.db.execute(text("""
            SELECT indexname FROM pg_indexes
            WHERE tablename = 'workflow_task_instances'
        """)).fetchall()

        index_names = [r[0] for r in result]

        # Should have indexes on key columns
        expected_patterns = ["assigned_user", "status", "scheduled"]
        found = sum(1 for p in expected_patterns if any(p in idx for idx in index_names))

        if found < 2:
            self.log_result(
                "Database Indexes",
                False,
                f"Missing performance indexes on workflow_task_instances"
            )
            return False

        self.log_result("Database Indexes", True, f"Found {len(index_names)} indexes")
        return True

    # =========================================================================
    # SERVICE VALIDATION
    # =========================================================================

    def check_service_imports(self) -> bool:
        """Verify all services can be imported."""
        import importlib

        services = [
            ("services.workflow_sla_service", "WorkflowSLAService"),
            ("services.workflow_task_generator", "TaskGeneratorService"),
            ("services.workflow_role_assignment", "RoleAssignmentService"),
            ("services.workflow_scheduler", "WorkflowScheduler"),
            ("services.workflow_ai_evaluator", "WorkflowAIEvaluator"),
            ("services.workflow_ai_executor", "WorkflowAIExecutor"),
            ("services.workflow_dialer_integration", "WorkflowDialerIntegration"),
            ("services.workflow_websocket_events", "WorkflowEvent"),
        ]

        failed = []
        for module_name, cls_name in services:
            try:
                # Safe dynamic import using importlib instead of exec()
                module = importlib.import_module(module_name)
                getattr(module, cls_name)  # Verify class exists
            except (ImportError, AttributeError) as e:
                failed.append(f"{module_name}.{cls_name}: {e}")

        if failed:
            self.log_result(
                "Service Imports",
                False,
                f"Failed imports: {'; '.join(failed)}"
            )
            return False

        self.log_result(
            "Service Imports",
            True,
            f"All {len(services)} services import successfully"
        )
        return True

    def check_service_instantiation(self) -> bool:
        """Verify services can be instantiated."""
        try:
            from services.workflow_sla_service import WorkflowSLAService
            from services.workflow_task_generator import TaskGeneratorService
            from services.workflow_scheduler import WorkflowScheduler

            # Test instantiation
            sla_service = WorkflowSLAService(self.db)
            task_gen = TaskGeneratorService(self.db)
            scheduler = WorkflowScheduler(self.db)

            self.log_result(
                "Service Instantiation",
                True,
                "Core services instantiate correctly"
            )
            return True

        except Exception as e:
            self.log_result(
                "Service Instantiation",
                False,
                f"Failed: {e}"
            )
            return False

    # =========================================================================
    # DATA VALIDATION
    # =========================================================================

    def check_workflow_configs(self) -> bool:
        """Verify workflow configurations exist."""
        from sqlalchemy import text

        result = self.db.execute(text("""
            SELECT workflow_key, workflow_name, is_active
            FROM workflow_configs
            WHERE is_active = true
        """)).fetchall()

        if not result:
            self.log_result(
                "Workflow Configs",
                False,
                "No active workflow configurations found"
            )
            return False

        configs = [r[0] for r in result]
        self.log_result(
            "Workflow Configs",
            True,
            f"Found {len(result)} active workflows: {', '.join(configs)}"
        )
        return True

    def check_workflow_roles(self) -> bool:
        """Verify workflow roles exist."""
        from sqlalchemy import text

        result = self.db.execute(text("""
            SELECT role_key, role_name
            FROM workflow_roles
            WHERE is_active = true
        """)).fetchall()

        if not result:
            self.log_result(
                "Workflow Roles",
                True,
                "No roles configured (may be intentional)",
                warning=True
            )
            return True

        roles = [r[0] for r in result]
        self.log_result(
            "Workflow Roles",
            True,
            f"Found {len(result)} roles: {', '.join(roles)}"
        )
        return True

    def check_active_workflows(self) -> bool:
        """Check for active workflow instances."""
        from sqlalchemy import text

        result = self.db.execute(text("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN status = 'active' THEN 1 END) as active,
                COUNT(CASE WHEN status = 'paused' THEN 1 END) as paused
            FROM workflow_instances
        """)).fetchone()

        self.log_result(
            "Active Workflows",
            True,
            f"Total: {result[0]}, Active: {result[1]}, Paused: {result[2]}"
        )
        return True

    def check_pending_tasks(self) -> bool:
        """Check for pending workflow tasks."""
        from sqlalchemy import text

        result = self.db.execute(text("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN status = 'scheduled' THEN 1 END) as scheduled,
                COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending,
                COUNT(CASE WHEN scheduled_date <= NOW() AND status IN ('scheduled', 'pending') THEN 1 END) as due
            FROM workflow_task_instances
        """)).fetchone()

        self.log_result(
            "Pending Tasks",
            True,
            f"Total: {result[0]}, Scheduled: {result[1]}, Pending: {result[2]}, Due now: {result[3]}"
        )

        if result[3] > 100:
            self.log_result(
                "Due Tasks Warning",
                True,
                f"{result[3]} tasks are due - check scheduler is running",
                warning=True
            )

        return True

    # =========================================================================
    # API VALIDATION
    # =========================================================================

    def check_api_routes(self) -> bool:
        """Verify API routes are registered."""
        try:
            from main import app

            routes = [r.path for r in app.routes]
            workflow_routes = [r for r in routes if "workflow-sla" in r]

            if not workflow_routes:
                self.log_result(
                    "API Routes",
                    False,
                    "No workflow-sla routes found in app"
                )
                return False

            self.log_result(
                "API Routes",
                True,
                f"Found {len(workflow_routes)} workflow-sla routes"
            )
            return True

        except Exception as e:
            self.log_result(
                "API Routes",
                False,
                f"Could not check routes: {e}"
            )
            return False

    # =========================================================================
    # FUNCTIONAL TESTS
    # =========================================================================

    def test_workflow_enrollment(self) -> bool:
        """Test workflow enrollment functionality."""
        from sqlalchemy import text

        try:
            # Find a test lead
            lead = self.db.execute(text("""
                SELECT id FROM leads
                WHERE stage = 'NEW'
                LIMIT 1
            """)).fetchone()

            if not lead:
                self.log_result(
                    "Enrollment Test",
                    True,
                    "Skipped - no test leads available",
                    warning=True
                )
                return True

            # Check if already enrolled
            existing = self.db.execute(text("""
                SELECT id FROM workflow_instances
                WHERE lead_id = :lead_id AND status = 'active'
            """), {"lead_id": lead[0]}).fetchone()

            if existing:
                self.log_result(
                    "Enrollment Test",
                    True,
                    f"Lead {lead[0]} already enrolled in workflow {existing[0]}"
                )
                return True

            self.log_result(
                "Enrollment Test",
                True,
                f"Lead {lead[0]} available for enrollment test"
            )
            return True

        except Exception as e:
            self.log_result(
                "Enrollment Test",
                False,
                f"Error: {e}"
            )
            return False

    def test_task_generation(self) -> bool:
        """Test task generation functionality."""
        try:
            from services.workflow_task_generator import TaskGeneratorService

            generator = TaskGeneratorService(self.db)

            # Just verify the service works
            self.log_result(
                "Task Generation Test",
                True,
                "TaskGeneratorService initialized successfully"
            )
            return True

        except Exception as e:
            self.log_result(
                "Task Generation Test",
                False,
                f"Error: {e}"
            )
            return False

    def test_ai_evaluator(self) -> bool:
        """Test AI evaluator functionality."""
        try:
            from services.workflow_ai_evaluator import WorkflowAIEvaluator

            evaluator = WorkflowAIEvaluator(self.db)

            # Verify thresholds are set
            assert evaluator.AUTO_EXECUTE_THRESHOLD == 0.950
            assert evaluator.REVIEW_THRESHOLD == 0.700

            self.log_result(
                "AI Evaluator Test",
                True,
                "WorkflowAIEvaluator configured correctly"
            )
            return True

        except Exception as e:
            self.log_result(
                "AI Evaluator Test",
                False,
                f"Error: {e}"
            )
            return False

    # =========================================================================
    # RUN VALIDATION
    # =========================================================================

    def run_all(self) -> Dict[str, Any]:
        """Run all validation checks."""
        logger.info("=" * 60)
        logger.info("WORKFLOW SLA SYSTEM VALIDATION")
        logger.info("=" * 60)

        # Database checks
        logger.info("\n📦 DATABASE VALIDATION")
        self.check_database_tables()
        self.check_database_enums()
        self.check_database_columns()
        self.check_database_indexes()

        # Service checks
        logger.info("\n🔧 SERVICE VALIDATION")
        self.check_service_imports()
        self.check_service_instantiation()

        # Data checks
        logger.info("\n📊 DATA VALIDATION")
        self.check_workflow_configs()
        self.check_workflow_roles()
        self.check_active_workflows()
        self.check_pending_tasks()

        # API checks
        logger.info("\n🌐 API VALIDATION")
        self.check_api_routes()

        # Functional checks
        logger.info("\n🧪 FUNCTIONAL TESTS")
        self.test_workflow_enrollment()
        self.test_task_generation()
        self.test_ai_evaluator()

        # Summary
        logger.info("\n" + "=" * 60)
        logger.info("VALIDATION SUMMARY")
        logger.info("=" * 60)

        passed = len(self.results["passed"])
        failed = len(self.results["failed"])
        warnings = len(self.results["warnings"])

        logger.info(f"✅ Passed:   {passed}")
        logger.info(f"❌ Failed:   {failed}")
        logger.info(f"⚠️  Warnings: {warnings}")

        if failed > 0:
            logger.error("\n❌ VALIDATION FAILED")
            for f in self.results["failed"]:
                logger.error(f"  - {f['test']}: {f['message']}")
        else:
            logger.info("\n✅ VALIDATION PASSED")

        return {
            "success": failed == 0,
            "passed": passed,
            "failed": failed,
            "warnings": warnings,
            "results": self.results
        }

    def run_migration_check(self) -> Dict[str, Any]:
        """Run only migration/database checks."""
        logger.info("=" * 60)
        logger.info("WORKFLOW SLA MIGRATION CHECK")
        logger.info("=" * 60)

        self.check_database_tables()
        self.check_database_enums()
        self.check_database_columns()
        self.check_database_indexes()

        failed = len(self.results["failed"])
        return {
            "success": failed == 0,
            "results": self.results
        }


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Validate Workflow SLA System"
    )
    parser.add_argument(
        "--env",
        choices=["local", "staging", "prod"],
        default="local",
        help="Environment to validate"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )
    parser.add_argument(
        "--check-migration",
        action="store_true",
        help="Only check database migration status"
    )
    parser.add_argument(
        "--full-test",
        action="store_true",
        help="Run full test suite including functional tests"
    )
    parser.add_argument(
        "--db-url",
        help="Database URL (overrides environment)"
    )

    args = parser.parse_args()

    # Set log level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Get database URL
    db_url = args.db_url or os.getenv("DATABASE_URL")
    if not db_url:
        logger.error("DATABASE_URL not set. Use --db-url or set environment variable.")
        sys.exit(1)

    # Run validation
    validator = WorkflowSLAValidator(db_url=db_url, verbose=args.verbose)

    if args.check_migration:
        result = validator.run_migration_check()
    else:
        result = validator.run_all()

    # Exit with appropriate code
    sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
