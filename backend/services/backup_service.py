"""
Backup Verification Service
Enterprise Readiness - Domain 8: Disaster Recovery (Checks 8.2, 8.3)

Provides backup verification, integrity checking, RPO compliance monitoring,
backup history tracking, and backup restoration testing for Railway
PostgreSQL deployments.
"""

import os
import hashlib
import logging
import shutil
import subprocess
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# RPO/RTO configuration (configurable via environment)
RPO_TARGET_HOURS = float(os.getenv("DR_RPO_TARGET_HOURS", "1"))
RTO_TARGET_HOURS = float(os.getenv("DR_RTO_TARGET_HOURS", "4"))
BACKUP_WARN_THRESHOLD_HOURS = float(os.getenv("BACKUP_WARN_THRESHOLD_HOURS", "0.75"))

# Key tables to verify during backup integrity checks
KEY_TABLES = [
    "users",
    "organizations",
    "leads",
    "loans",
    "audit_logs",
]


class BackupVerificationService:
    """
    Verifies database backup status, integrity, and RPO compliance.

    Designed for Railway PostgreSQL which provides automatic daily backups
    with point-in-time recovery. This service adds verification and monitoring
    on top of the platform-provided backup infrastructure.
    """

    def __init__(self, db: Session):
        self.db = db

    def verify_latest_backup(self) -> Dict[str, Any]:
        """
        Check that a recent backup exists by querying PostgreSQL WAL
        and replication status. On Railway, backups are WAL-based, so we
        check WAL archiving status and the last checkpoint time.

        Returns:
            Dict with backup status, last backup time, and compliance info.
        """
        result = {
            "status": "unknown",
            "last_checkpoint": None,
            "wal_archiving": None,
            "rpo_compliant": False,
            "rpo_target_hours": RPO_TARGET_HOURS,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            # Check last checkpoint time from pg_control_checkpoint()
            checkpoint = self.db.execute(text(
                "SELECT checkpoint_time, timeline_id "
                "FROM pg_control_checkpoint()"
            )).fetchone()

            if checkpoint:
                checkpoint_time = checkpoint[0]
                if checkpoint_time.tzinfo is None:
                    checkpoint_time = checkpoint_time.replace(tzinfo=timezone.utc)

                result["last_checkpoint"] = checkpoint_time.isoformat()
                result["timeline_id"] = checkpoint[1]

                age_hours = (
                    datetime.now(timezone.utc) - checkpoint_time
                ).total_seconds() / 3600

                result["hours_since_checkpoint"] = round(age_hours, 2)
                result["rpo_compliant"] = age_hours <= RPO_TARGET_HOURS

                if age_hours <= RPO_TARGET_HOURS:
                    result["status"] = "healthy"
                elif age_hours <= RPO_TARGET_HOURS * 2:
                    result["status"] = "warning"
                else:
                    result["status"] = "critical"

        except Exception as e:
            # pg_control_checkpoint may not be available on all setups;
            # fall back to pg_stat_activity for approximate timing
            logger.warning(f"pg_control_checkpoint not available: {e}")
            try:
                self.db.rollback()
                activity = self.db.execute(text(
                    "SELECT now() AS current_time, "
                    "pg_postmaster_start_time() AS server_start"
                )).fetchone()

                if activity:
                    result["server_time"] = activity[0].isoformat() if activity[0] else None
                    result["server_start"] = activity[1].isoformat() if activity[1] else None
                    result["status"] = "partial"
                    result["note"] = (
                        "pg_control_checkpoint() not available; "
                        "using server uptime as proxy"
                    )
            except Exception as inner_e:
                logger.error(f"Backup verification fallback failed: {inner_e}")
                self.db.rollback()
                result["status"] = "error"
                result["error"] = "Could not query backup status"

        # Check WAL archiving status if available
        try:
            wal_status = self.db.execute(text(
                "SELECT archived_count, failed_count, "
                "last_archived_wal, last_archived_time "
                "FROM pg_stat_archiver"
            )).fetchone()

            if wal_status:
                result["wal_archiving"] = {
                    "archived_count": wal_status[0],
                    "failed_count": wal_status[1],
                    "last_archived_wal": wal_status[2],
                    "last_archived_time": (
                        wal_status[3].isoformat() if wal_status[3] else None
                    ),
                }
                if wal_status[1] and wal_status[1] > 0:
                    result["wal_archiving"]["has_failures"] = True
        except Exception as e:
            logger.debug(f"WAL archiver stats not available: {e}")
            self.db.rollback()

        return result

    def verify_backup_integrity(self, backup_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Verify backup integrity by checking row counts and computing
        checksums on key tables. This provides a snapshot of data state
        that can be compared against a restored backup.

        Args:
            backup_id: Optional identifier for the backup to verify.
                       If None, verifies current database state.

        Returns:
            Dict with table checksums, row counts, and integrity status.
        """
        result = {
            "backup_id": backup_id or "current",
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "tables": {},
            "integrity_status": "pass",
            "total_rows": 0,
        }

        for table_name in KEY_TABLES:
            table_result = {
                "status": "unknown",
                "row_count": 0,
                "checksum": None,
            }

            try:
                # Check if table exists
                exists = self.db.execute(text(
                    "SELECT EXISTS ("
                    "  SELECT FROM information_schema.tables "
                    "  WHERE table_name = :table_name"
                    ")"
                ), {"table_name": table_name}).scalar()

                if not exists:
                    table_result["status"] = "missing"
                    result["integrity_status"] = "warning"
                    result["tables"][table_name] = table_result
                    continue

                # Get row count
                count = self.db.execute(
                    text(f"SELECT COUNT(*) FROM {table_name}")  # noqa: S608
                ).scalar()
                table_result["row_count"] = count
                result["total_rows"] += count

                # Compute a lightweight checksum using count + max id
                try:
                    max_id = self.db.execute(
                        text(f"SELECT MAX(id) FROM {table_name}")  # noqa: S608
                    ).scalar()

                    checksum_input = f"{table_name}:{count}:{max_id}"
                    table_result["checksum"] = hashlib.sha256(
                        checksum_input.encode()
                    ).hexdigest()[:16]
                    table_result["max_id"] = max_id
                except Exception as e:
                    # Table may not have 'id' column
                    logger.error(f"Error computing checksum for {table_name}: {e}")
                    table_result["checksum"] = hashlib.sha256(
                        f"{table_name}:{count}".encode()
                    ).hexdigest()[:16]

                table_result["status"] = "verified"

            except Exception as e:
                logger.warning(f"Integrity check failed for {table_name}: {e}")
                self.db.rollback()
                table_result["status"] = "error"
                table_result["error"] = str(e)
                result["integrity_status"] = "partial"

            result["tables"][table_name] = table_result

        return result

    def get_backup_history(self, limit: int = 20) -> Dict[str, Any]:
        """
        List recent backup verification records. Since Railway does not
        expose a backup list API directly, we track verifications in the
        backup_verifications table (created on first use).

        Args:
            limit: Maximum number of records to return.

        Returns:
            Dict with backup history and summary stats.
        """
        self._ensure_verification_table()

        try:
            records = self.db.execute(text(
                "SELECT id, verified_at, status, total_rows, "
                "integrity_status, rpo_compliant, details "
                "FROM backup_verifications "
                "ORDER BY verified_at DESC "
                "LIMIT :limit"
            ), {"limit": limit}).fetchall()

            history = []
            for r in records:
                history.append({
                    "id": r[0],
                    "verified_at": r[1].isoformat() if r[1] else None,
                    "status": r[2],
                    "total_rows": r[3],
                    "integrity_status": r[4],
                    "rpo_compliant": r[5],
                })

            return {
                "total_records": len(history),
                "history": history,
            }

        except Exception as e:
            logger.error(f"Error fetching backup history: {e}")
            self.db.rollback()
            return {"total_records": 0, "history": [], "error": str(e)}

    def calculate_rpo_compliance(self) -> Dict[str, Any]:
        """
        Check if RPO target is being met based on backup frequency
        and the most recent verification.

        Returns:
            Dict with RPO compliance status, metrics, and recommendations.
        """
        result = {
            "rpo_target_hours": RPO_TARGET_HOURS,
            "rto_target_hours": RTO_TARGET_HOURS,
            "is_compliant": False,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "recommendations": [],
        }

        # Get latest backup verification
        backup_status = self.verify_latest_backup()
        result["backup_status"] = backup_status.get("status")
        result["hours_since_checkpoint"] = backup_status.get(
            "hours_since_checkpoint"
        )

        if backup_status.get("rpo_compliant"):
            result["is_compliant"] = True
            result["compliance_status"] = "met"
        else:
            result["compliance_status"] = "at_risk"
            hours_since = backup_status.get("hours_since_checkpoint")
            if hours_since:
                result["recommendations"].append(
                    f"Last checkpoint was {hours_since:.1f} hours ago "
                    f"(target: {RPO_TARGET_HOURS}h). "
                    "Consider increasing WAL archiving frequency."
                )

        # Check WAL archiving health
        wal = backup_status.get("wal_archiving")
        if wal and wal.get("has_failures"):
            result["recommendations"].append(
                f"WAL archiving has {wal['failed_count']} failures. "
                "Investigate archiving configuration."
            )
            result["compliance_status"] = "degraded"

        # Warn if approaching threshold
        hours_since = backup_status.get("hours_since_checkpoint")
        warn_threshold = RPO_TARGET_HOURS * BACKUP_WARN_THRESHOLD_HOURS
        if hours_since and hours_since > warn_threshold and result["is_compliant"]:
            result["recommendations"].append(
                f"Approaching RPO threshold ({hours_since:.1f}h of "
                f"{RPO_TARGET_HOURS}h). Monitor closely."
            )

        return result

    def record_verification(
        self,
        backup_status: Dict[str, Any],
        integrity: Dict[str, Any],
    ) -> Optional[int]:
        """
        Record a backup verification result for audit history.

        Args:
            backup_status: Result from verify_latest_backup()
            integrity: Result from verify_backup_integrity()

        Returns:
            ID of the created record, or None on failure.
        """
        self._ensure_verification_table()

        try:
            import json

            result = self.db.execute(text(
                "INSERT INTO backup_verifications "
                "(verified_at, status, total_rows, integrity_status, "
                "rpo_compliant, details) "
                "VALUES (:verified_at, :status, :total_rows, "
                ":integrity_status, :rpo_compliant, :details) "
                "RETURNING id"
            ), {
                "verified_at": datetime.now(timezone.utc),
                "status": backup_status.get("status", "unknown"),
                "total_rows": integrity.get("total_rows", 0),
                "integrity_status": integrity.get("integrity_status", "unknown"),
                "rpo_compliant": backup_status.get("rpo_compliant", False),
                "details": json.dumps({
                    "backup": backup_status,
                    "integrity": integrity,
                }),
            })
            self.db.commit()

            row = result.fetchone()
            return row[0] if row else None

        except Exception as e:
            logger.error(f"Failed to record backup verification: {e}")
            self.db.rollback()
            return None

    # =================================================================
    # Backup Restoration Testing (Domain 8.2)
    # =================================================================

    def test_backup_restoration(self) -> Dict[str, Any]:
        """
        Test backup restoration to verify recoverability.

        Strategy (in order of preference):
        1. If pg_dump/pg_restore are available and we can create temp
           databases, perform a full dump-and-restore cycle.
        2. Otherwise, fall back to a comprehensive logical verification:
           - Snapshot current row counts and recent records
           - Verify WAL archive continuity
           - Verify pg_basebackup availability
           - Check index and constraint integrity
           - Record what a full restore test would require

        Returns:
            Dict with success, rto_seconds, row_counts, integrity_checks,
            started_at, completed_at, and method used.
        """
        import json

        started_at = datetime.now(timezone.utc)
        result = {
            "success": False,
            "method": None,
            "rto_seconds": None,
            "row_counts": {},
            "integrity_checks": [],
            "test_database": None,
            "started_at": started_at.isoformat(),
            "completed_at": None,
            "errors": [],
            "warnings": [],
        }

        # Attempt full dump-restore if pg_dump is available
        pg_dump_path = shutil.which("pg_dump")
        pg_restore_available = shutil.which("pg_restore") or shutil.which("psql")
        db_url = os.environ.get("DATABASE_URL", "")

        if pg_dump_path and pg_restore_available and db_url:
            full_result = self._test_full_restore(db_url, started_at)
            result.update(full_result)
        else:
            # Fall back to logical verification
            if not pg_dump_path:
                result["warnings"].append(
                    "pg_dump not available; using logical verification"
                )
            if not db_url:
                result["warnings"].append(
                    "DATABASE_URL not set; using logical verification"
                )
            logical_result = self._test_logical_restore(started_at)
            result.update(logical_result)

        completed_at = datetime.now(timezone.utc)
        result["completed_at"] = completed_at.isoformat()
        result["rto_seconds"] = round(
            (completed_at - started_at).total_seconds(), 2
        )

        # Record the test result in backup_verifications
        self._record_restore_test(result)

        return result

    def _test_full_restore(
        self, db_url: str, started_at: datetime
    ) -> Dict[str, Any]:
        """
        Attempt a full pg_dump / restore to a temporary test database.

        This creates a new database from a schema+data dump of the
        production database, runs integrity checks on the restored
        copy, then drops the test database.
        """
        import json

        result = {
            "method": "pg_dump_restore",
            "success": False,
            "row_counts": {},
            "integrity_checks": [],
            "test_database": None,
            "errors": [],
            "warnings": [],
        }

        timestamp = int(time.time())
        test_db_name = f"perennia_restore_test_{timestamp}"
        result["test_database"] = test_db_name

        parsed = urlparse(db_url)
        host = parsed.hostname
        port = parsed.port or 5432
        user = parsed.username
        password = parsed.password
        source_db = (parsed.path or "").lstrip("/")

        # Build connection env for subprocess (avoids password prompts)
        env = os.environ.copy()
        if password:
            env["PGPASSWORD"] = password

        conn_args = []
        if host:
            conn_args.extend(["-h", host])
        if port:
            conn_args.extend(["-p", str(port)])
        if user:
            conn_args.extend(["-U", user])

        try:
            # Step 1: Create the test database
            logger.info(f"Creating test database: {test_db_name}")
            create_result = subprocess.run(
                ["psql"] + conn_args + [
                    "-d", source_db,
                    "-c", f'CREATE DATABASE "{test_db_name}"',
                ],
                capture_output=True,
                text=True,
                timeout=30,
                env=env,
            )

            if create_result.returncode != 0:
                # Try alternative: createdb command
                create_result = subprocess.run(
                    ["createdb"] + conn_args + [test_db_name],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    env=env,
                )

            if create_result.returncode != 0:
                result["errors"].append(
                    f"Cannot create test database: {create_result.stderr.strip()}"
                )
                result["warnings"].append(
                    "Falling back to logical verification"
                )
                return {**result, **self._test_logical_restore(started_at)}

            # Step 2: pg_dump the source and pipe into test database
            logger.info("Running pg_dump | psql restore")
            dump_proc = subprocess.Popen(
                ["pg_dump"] + conn_args + [
                    "--no-owner",
                    "--no-privileges",
                    source_db,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )

            restore_proc = subprocess.Popen(
                ["psql"] + conn_args + [
                    "-d", test_db_name,
                    "-q",
                ],
                stdin=dump_proc.stdout,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )

            dump_proc.stdout.close()
            restore_stdout, restore_stderr = restore_proc.communicate(
                timeout=300
            )
            dump_proc.wait(timeout=10)

            if dump_proc.returncode != 0:
                dump_stderr = dump_proc.stderr.read().decode()
                result["errors"].append(
                    f"pg_dump failed: {dump_stderr.strip()[:200]}"
                )
            elif restore_proc.returncode != 0:
                result["warnings"].append(
                    f"Restore had warnings: "
                    f"{restore_stderr.decode().strip()[:200]}"
                )

            # Step 3: Verify the restored database
            logger.info("Verifying restored database")
            integrity = self._verify_restored_database(
                test_db_name, conn_args, env
            )
            result["integrity_checks"] = integrity["checks"]
            result["row_counts"] = integrity["row_counts"]

            # Step 4: Compare row counts with source
            source_counts = self._get_source_row_counts()
            comparison_ok = True
            for table, source_count in source_counts.items():
                restored_count = result["row_counts"].get(table, -1)
                if restored_count == -1:
                    result["integrity_checks"].append({
                        "check": f"table_{table}_exists",
                        "passed": False,
                        "detail": f"Table {table} missing in restored DB",
                    })
                    comparison_ok = False
                elif restored_count != source_count:
                    result["integrity_checks"].append({
                        "check": f"table_{table}_row_count",
                        "passed": False,
                        "detail": (
                            f"{table}: source={source_count}, "
                            f"restored={restored_count}"
                        ),
                    })
                    comparison_ok = False
                else:
                    result["integrity_checks"].append({
                        "check": f"table_{table}_row_count",
                        "passed": True,
                        "detail": f"{table}: {source_count} rows match",
                    })

            result["success"] = comparison_ok and not result["errors"]

        except subprocess.TimeoutExpired:
            result["errors"].append(
                "Restore operation timed out (5 min limit)"
            )
        except FileNotFoundError as e:
            result["errors"].append(f"Required tool not found: {e}")
            result["warnings"].append("Falling back to logical verification")
            return {**result, **self._test_logical_restore(started_at)}
        except Exception as e:
            logger.exception("Full restore test failed")
            result["errors"].append(f"Unexpected error: {str(e)[:200]}")
        finally:
            # Step 5: Always drop the test database
            self._drop_test_database(
                test_db_name, source_db, conn_args, env
            )

        return result

    def _verify_restored_database(
        self,
        test_db_name: str,
        conn_args: List[str],
        env: Dict[str, str],
    ) -> Dict[str, Any]:
        """
        Run integrity checks on the restored test database via psql.

        Returns dict with 'checks' list and 'row_counts' dict.
        """
        checks = []
        row_counts = {}

        for table_name in KEY_TABLES:
            try:
                count_result = subprocess.run(
                    ["psql"] + conn_args + [
                        "-d", test_db_name,
                        "-t", "-A",
                        "-c", (
                            f"SELECT COUNT(*) FROM {table_name}"
                        ),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    env=env,
                )
                if count_result.returncode == 0:
                    count_str = count_result.stdout.strip()
                    count = int(count_str) if count_str.isdigit() else -1
                    row_counts[table_name] = count
                else:
                    row_counts[table_name] = -1
                    checks.append({
                        "check": f"table_{table_name}_accessible",
                        "passed": False,
                        "detail": count_result.stderr.strip()[:100],
                    })
            except Exception as e:
                row_counts[table_name] = -1
                checks.append({
                    "check": f"table_{table_name}_accessible",
                    "passed": False,
                    "detail": str(e)[:100],
                })

        # Check indexes exist
        try:
            idx_result = subprocess.run(
                ["psql"] + conn_args + [
                    "-d", test_db_name,
                    "-t", "-A",
                    "-c", (
                        "SELECT COUNT(*) FROM pg_indexes "
                        "WHERE schemaname = 'public'"
                    ),
                ],
                capture_output=True,
                text=True,
                timeout=30,
                env=env,
            )
            if idx_result.returncode == 0:
                idx_count = idx_result.stdout.strip()
                checks.append({
                    "check": "indexes_present",
                    "passed": int(idx_count) > 0 if idx_count.isdigit() else False,
                    "detail": f"{idx_count} indexes found in restored DB",
                })
        except Exception as e:
            checks.append({
                "check": "indexes_present",
                "passed": False,
                "detail": str(e)[:100],
            })

        # Check constraints exist
        try:
            con_result = subprocess.run(
                ["psql"] + conn_args + [
                    "-d", test_db_name,
                    "-t", "-A",
                    "-c", (
                        "SELECT COUNT(*) FROM "
                        "information_schema.table_constraints "
                        "WHERE constraint_schema = 'public'"
                    ),
                ],
                capture_output=True,
                text=True,
                timeout=30,
                env=env,
            )
            if con_result.returncode == 0:
                con_count = con_result.stdout.strip()
                checks.append({
                    "check": "constraints_present",
                    "passed": int(con_count) > 0 if con_count.isdigit() else False,
                    "detail": f"{con_count} constraints in restored DB",
                })
        except Exception as e:
            checks.append({
                "check": "constraints_present",
                "passed": False,
                "detail": str(e)[:100],
            })

        return {"checks": checks, "row_counts": row_counts}

    def _drop_test_database(
        self,
        test_db_name: str,
        source_db: str,
        conn_args: List[str],
        env: Dict[str, str],
    ):
        """Drop the temporary test database. Best-effort, never raises."""
        try:
            # Terminate connections first
            subprocess.run(
                ["psql"] + conn_args + [
                    "-d", source_db,
                    "-c", (
                        "SELECT pg_terminate_backend(pid) "
                        "FROM pg_stat_activity "
                        f"WHERE datname = '{test_db_name}'"
                    ),
                ],
                capture_output=True,
                text=True,
                timeout=15,
                env=env,
            )
            # Drop the database
            subprocess.run(
                ["psql"] + conn_args + [
                    "-d", source_db,
                    "-c", f'DROP DATABASE IF EXISTS "{test_db_name}"',
                ],
                capture_output=True,
                text=True,
                timeout=30,
                env=env,
            )
            logger.info(f"Dropped test database: {test_db_name}")
        except Exception as e:
            logger.error(
                f"Failed to drop test database {test_db_name}: {e}"
            )

    def _get_source_row_counts(self) -> Dict[str, int]:
        """Get current row counts from the source database."""
        counts = {}
        for table_name in KEY_TABLES:
            try:
                exists = self.db.execute(text(
                    "SELECT EXISTS ("
                    "  SELECT FROM information_schema.tables "
                    "  WHERE table_name = :table_name"
                    ")"
                ), {"table_name": table_name}).scalar()

                if exists:
                    count = self.db.execute(
                        text(f"SELECT COUNT(*) FROM {table_name}")  # noqa: S608
                    ).scalar()
                    counts[table_name] = count or 0
            except Exception as e:
                logger.warning(
                    f"Could not count rows in {table_name}: {e}"
                )
                self.db.rollback()
        return counts

    def _test_logical_restore(
        self, started_at: datetime
    ) -> Dict[str, Any]:
        """
        Logical backup restoration verification when pg_dump/pg_restore
        are not available (e.g., Railway managed database without shell
        tool access).

        Performs:
        1. Row count snapshot of key tables
        2. Verification that recent records exist (data is not stale)
        3. WAL archive continuity check
        4. Index and constraint integrity verification
        5. pg_basebackup capability check
        6. Documents what a full restore would require

        Returns partial result dict to merge into the main result.
        """
        result = {
            "method": "logical_verification",
            "success": False,
            "row_counts": {},
            "integrity_checks": [],
            "test_database": None,
            "errors": [],
            "warnings": [],
        }

        all_passed = True

        # 1. Row count snapshot
        row_counts = self._get_source_row_counts()
        result["row_counts"] = row_counts

        total_rows = sum(row_counts.values())
        result["integrity_checks"].append({
            "check": "key_tables_populated",
            "passed": total_rows > 0,
            "detail": (
                f"{len(row_counts)} tables checked, "
                f"{total_rows} total rows"
            ),
        })
        if total_rows == 0:
            all_passed = False

        # 2. Verify recent records exist (data freshness)
        try:
            freshness_checks = [
                ("users", "created_at"),
                ("leads", "created_at"),
                ("audit_logs", "created_at"),
            ]
            for table, col in freshness_checks:
                try:
                    exists = self.db.execute(text(
                        "SELECT EXISTS ("
                        "  SELECT FROM information_schema.tables "
                        "  WHERE table_name = :t"
                        ")"
                    ), {"t": table}).scalar()

                    if not exists:
                        continue

                    # Check column exists
                    col_exists = self.db.execute(text(
                        "SELECT EXISTS ("
                        "  SELECT FROM information_schema.columns "
                        "  WHERE table_name = :t AND column_name = :c"
                        ")"
                    ), {"t": table, "c": col}).scalar()

                    if not col_exists:
                        continue

                    recent = self.db.execute(text(
                        f"SELECT COUNT(*) FROM {table} "  # noqa: S608
                        f"WHERE {col} >= CURRENT_TIMESTAMP - INTERVAL '7 days'"
                    )).scalar()

                    result["integrity_checks"].append({
                        "check": f"recent_records_{table}",
                        "passed": (recent or 0) > 0,
                        "detail": (
                            f"{recent} records in {table} from last 7 days"
                        ),
                    })
                except Exception as e:
                    logger.debug(f"Freshness check for {table} skipped: {e}")
                    self.db.rollback()

        except Exception as e:
            result["warnings"].append(
                f"Data freshness check failed: {str(e)[:100]}"
            )
            self.db.rollback()

        # 3. WAL archive continuity
        try:
            wal_status = self.db.execute(text(
                "SELECT archived_count, failed_count, "
                "last_archived_wal, last_archived_time "
                "FROM pg_stat_archiver"
            )).fetchone()

            if wal_status:
                archived = wal_status[0] or 0
                failed = wal_status[1] or 0
                wal_ok = archived > 0 and failed == 0
                result["integrity_checks"].append({
                    "check": "wal_archive_continuity",
                    "passed": wal_ok,
                    "detail": (
                        f"Archived: {archived}, Failed: {failed}"
                        + (
                            f", Last: {wal_status[3].isoformat()}"
                            if wal_status[3] else ""
                        )
                    ),
                })
                if not wal_ok and failed > 0:
                    all_passed = False
            else:
                result["integrity_checks"].append({
                    "check": "wal_archive_continuity",
                    "passed": False,
                    "detail": "pg_stat_archiver returned no rows",
                })
        except Exception as e:
            logger.debug(f"WAL archive check not available: {e}")
            self.db.rollback()
            result["integrity_checks"].append({
                "check": "wal_archive_continuity",
                "passed": False,
                "detail": f"Not available: {str(e)[:80]}",
            })

        # 4. Index and constraint integrity
        try:
            idx_count = self.db.execute(text(
                "SELECT COUNT(*) FROM pg_indexes "
                "WHERE schemaname = 'public'"
            )).scalar()

            result["integrity_checks"].append({
                "check": "indexes_present",
                "passed": (idx_count or 0) > 0,
                "detail": f"{idx_count} indexes in public schema",
            })
        except Exception as e:
            self.db.rollback()
            result["integrity_checks"].append({
                "check": "indexes_present",
                "passed": False,
                "detail": str(e)[:100],
            })

        try:
            constraint_count = self.db.execute(text(
                "SELECT COUNT(*) FROM "
                "information_schema.table_constraints "
                "WHERE constraint_schema = 'public'"
            )).scalar()

            result["integrity_checks"].append({
                "check": "constraints_present",
                "passed": (constraint_count or 0) > 0,
                "detail": (
                    f"{constraint_count} constraints in public schema"
                ),
            })
        except Exception as e:
            self.db.rollback()
            result["integrity_checks"].append({
                "check": "constraints_present",
                "passed": False,
                "detail": str(e)[:100],
            })

        # 5. Check for invalid indexes (corruption indicator)
        try:
            invalid = self.db.execute(text(
                "SELECT COUNT(*) FROM pg_index WHERE indisvalid = false"
            )).scalar()

            result["integrity_checks"].append({
                "check": "no_invalid_indexes",
                "passed": (invalid or 0) == 0,
                "detail": (
                    "No invalid indexes"
                    if (invalid or 0) == 0
                    else f"{invalid} invalid indexes detected"
                ),
            })
            if invalid and invalid > 0:
                all_passed = False
        except Exception as e:
            self.db.rollback()
            result["integrity_checks"].append({
                "check": "no_invalid_indexes",
                "passed": False,
                "detail": str(e)[:100],
            })

        # 6. Check pg_basebackup availability
        try:
            # On Railway managed PG, we check if replication slots exist
            # which indicates PITR capability
            slots = self.db.execute(text(
                "SELECT COUNT(*) FROM pg_replication_slots"
            )).scalar()

            result["integrity_checks"].append({
                "check": "replication_slots",
                "passed": True,  # Informational
                "detail": f"{slots} replication slot(s) configured",
            })
        except Exception as e:
            self.db.rollback()
            result["integrity_checks"].append({
                "check": "replication_slots",
                "passed": False,
                "detail": f"Cannot query replication: {str(e)[:80]}",
            })

        # 7. Document full restore requirements
        result["restore_requirements"] = {
            "note": (
                "Full physical restore on Railway requires using the "
                "Railway dashboard or CLI to restore from automatic "
                "daily backups / point-in-time recovery."
            ),
            "steps": [
                "1. Open Railway dashboard > Database > Backups",
                "2. Select backup point or specify PITR timestamp",
                "3. Railway creates a new PG instance from backup",
                "4. Update DATABASE_URL to point to restored instance",
                "5. Verify application connectivity and data integrity",
            ],
            "estimated_rto_minutes": RTO_TARGET_HOURS * 60,
        }

        # Determine overall success (all critical checks passed)
        critical_failures = [
            c for c in result["integrity_checks"]
            if not c["passed"] and c["check"] in (
                "key_tables_populated",
                "no_invalid_indexes",
                "wal_archive_continuity",
            )
        ]
        result["success"] = all_passed and len(critical_failures) == 0

        return result

    def _record_restore_test(self, test_result: Dict[str, Any]):
        """Record a restoration test result in backup_verifications."""
        import json

        self._ensure_restore_tests_table()

        try:
            self.db.execute(text(
                "INSERT INTO backup_restore_tests "
                "(tested_at, success, method, rto_seconds, "
                "row_counts, integrity_checks, errors, details) "
                "VALUES (:tested_at, :success, :method, :rto_seconds, "
                ":row_counts, :integrity_checks, :errors, :details)"
            ), {
                "tested_at": datetime.now(timezone.utc),
                "success": test_result.get("success", False),
                "method": test_result.get("method", "unknown"),
                "rto_seconds": test_result.get("rto_seconds"),
                "row_counts": json.dumps(
                    test_result.get("row_counts", {})
                ),
                "integrity_checks": json.dumps(
                    test_result.get("integrity_checks", [])
                ),
                "errors": json.dumps(
                    test_result.get("errors", [])
                ),
                "details": json.dumps(test_result),
            })
            self.db.commit()
        except Exception as e:
            logger.error(f"Failed to record restore test: {e}")
            self.db.rollback()

    def get_restoration_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Retrieve past backup restoration test results.

        Args:
            limit: Maximum number of records to return.

        Returns:
            List of restoration test result dicts, newest first.
        """
        import json

        self._ensure_restore_tests_table()

        try:
            records = self.db.execute(text(
                "SELECT id, tested_at, success, method, rto_seconds, "
                "row_counts, integrity_checks, errors, details "
                "FROM backup_restore_tests "
                "ORDER BY tested_at DESC "
                "LIMIT :limit"
            ), {"limit": limit}).fetchall()

            history = []
            for r in records:
                # Columns: id(0), tested_at(1), success(2), method(3),
                #   rto_seconds(4), row_counts(5), integrity_checks(6),
                #   errors(7), details(8)
                raw_row_counts = r[5]
                raw_ic = r[6]
                raw_errors = r[7]

                row_counts = (
                    json.loads(raw_row_counts)
                    if isinstance(raw_row_counts, str)
                    else raw_row_counts or {}
                )
                ic_parsed = (
                    json.loads(raw_ic)
                    if isinstance(raw_ic, str)
                    else raw_ic or []
                )
                errors_parsed = (
                    json.loads(raw_errors)
                    if isinstance(raw_errors, str)
                    else raw_errors or []
                )

                entry = {
                    "id": r[0],
                    "tested_at": r[1].isoformat() if r[1] else None,
                    "success": r[2],
                    "method": r[3],
                    "rto_seconds": (
                        float(r[4]) if r[4] is not None else None
                    ),
                    "row_counts": row_counts,
                    "integrity_checks_summary": None,
                    "errors": errors_parsed,
                }

                # Summarize integrity checks
                if isinstance(ic_parsed, list):
                    passed = sum(
                        1 for c in ic_parsed if c.get("passed")
                    )
                    failed = len(ic_parsed) - passed
                    entry["integrity_checks_summary"] = {
                        "total": len(ic_parsed),
                        "passed": passed,
                        "failed": failed,
                    }

                history.append(entry)

            return history

        except Exception as e:
            logger.error(f"Error fetching restoration history: {e}")
            self.db.rollback()
            return []

    def _ensure_restore_tests_table(self):
        """Create the backup_restore_tests table if it does not exist."""
        try:
            self.db.execute(text("""
                CREATE TABLE IF NOT EXISTS backup_restore_tests (
                    id SERIAL PRIMARY KEY,
                    tested_at TIMESTAMP WITH TIME ZONE NOT NULL
                        DEFAULT CURRENT_TIMESTAMP,
                    success BOOLEAN NOT NULL DEFAULT FALSE,
                    method VARCHAR(50) NOT NULL DEFAULT 'unknown',
                    rto_seconds NUMERIC(10,2),
                    row_counts JSONB DEFAULT '{}',
                    integrity_checks JSONB DEFAULT '[]',
                    errors JSONB DEFAULT '[]',
                    details JSONB,
                    created_at TIMESTAMP WITH TIME ZONE
                        DEFAULT CURRENT_TIMESTAMP
                )
            """))
            self.db.commit()
        except Exception as e:
            logger.warning(
                f"Could not ensure backup_restore_tests table: {e}"
            )
            self.db.rollback()

    def _ensure_verification_table(self):
        """Create the backup_verifications table if it does not exist."""
        try:
            self.db.execute(text("""
                CREATE TABLE IF NOT EXISTS backup_verifications (
                    id SERIAL PRIMARY KEY,
                    verified_at TIMESTAMP WITH TIME ZONE NOT NULL
                        DEFAULT CURRENT_TIMESTAMP,
                    status VARCHAR(20) NOT NULL DEFAULT 'unknown',
                    total_rows INTEGER DEFAULT 0,
                    integrity_status VARCHAR(20) DEFAULT 'unknown',
                    rpo_compliant BOOLEAN DEFAULT FALSE,
                    details JSONB,
                    created_at TIMESTAMP WITH TIME ZONE
                        DEFAULT CURRENT_TIMESTAMP
                )
            """))
            self.db.commit()
        except Exception as e:
            logger.warning(f"Could not ensure backup_verifications table: {e}")
            self.db.rollback()


def get_dr_status_summary(db: Session) -> Dict[str, Any]:
    """
    Get an overall DR readiness dashboard summarizing backup status,
    RPO/RTO compliance, and replication health.

    Args:
        db: Database session.

    Returns:
        Comprehensive DR status dictionary.
    """
    service = BackupVerificationService(db)

    backup_status = service.verify_latest_backup()
    rpo_compliance = service.calculate_rpo_compliance()
    integrity = service.verify_backup_integrity()

    # Determine overall DR readiness
    issues = []
    if backup_status.get("status") in ("critical", "error"):
        issues.append("Backup status is critical or errored")
    if not rpo_compliance.get("is_compliant"):
        issues.append("RPO target not being met")
    if integrity.get("integrity_status") not in ("pass",):
        issues.append(
            f"Data integrity check: {integrity.get('integrity_status')}"
        )

    if not issues:
        overall_status = "ready"
    elif len(issues) == 1 and "integrity" in issues[0].lower():
        overall_status = "degraded"
    else:
        overall_status = "at_risk"

    return {
        "overall_status": overall_status,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "rpo": {
            "target_hours": RPO_TARGET_HOURS,
            "compliant": rpo_compliance.get("is_compliant", False),
            "status": rpo_compliance.get("compliance_status", "unknown"),
        },
        "rto": {
            "target_hours": RTO_TARGET_HOURS,
            "note": "RTO validated during DR drills",
        },
        "backup": {
            "status": backup_status.get("status"),
            "last_checkpoint": backup_status.get("last_checkpoint"),
            "hours_since_checkpoint": backup_status.get(
                "hours_since_checkpoint"
            ),
            "wal_archiving": backup_status.get("wal_archiving"),
        },
        "integrity": {
            "status": integrity.get("integrity_status"),
            "total_rows": integrity.get("total_rows"),
            "tables_checked": len(integrity.get("tables", {})),
        },
        "issues": issues,
        "recommendations": rpo_compliance.get("recommendations", []),
    }
