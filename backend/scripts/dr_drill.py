"""Disaster-Recovery (DR) drill — automated backup / restore simulation.

Goal: prove that the platform can reach RTO < 4 hours and RPO < 1 hour by
exercising the full backup -> drop -> restore -> verify loop on demand.

Modes
-----
* ``--target sqlite``  (default in CI) — operates on a temporary on-disk
  SQLite database. Used by the integration test so the drill is always
  exercised even when Postgres is not available.
* ``--target postgres`` — uses ``pg_dump`` / ``pg_restore`` against the
  ``TEST_DATABASE_URL`` Postgres instance.

Each run writes a JSON report to ``dr_drills/<UTC timestamp>.json``:

    {
        "start_time": "...",
        "end_time": "...",
        "rto_seconds": <float>,
        "tables_restored": <int>,
        "row_count_deltas": {table: 0|delta, ...},
        "success": true|false,
        "target": "sqlite" | "postgres",
        "report_path": "..."
    }

CLI
---
    python3 -m backend.scripts.dr_drill --target sqlite --report-dir dr_drills/
    python3 -m backend.scripts.dr_drill --target postgres --report-dir dr_drills/

Exit code: ``0`` on success, ``1`` on any verification failure.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Tuple


# ---------------------------------------------------------------------------
# SQLite drill (CI-safe, no external services required)
# ---------------------------------------------------------------------------
def _seed_sqlite(path: Path) -> Dict[str, int]:
    """Seed a synthetic schema and return baseline row counts."""
    conn = sqlite3.connect(str(path))
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE loans (
            id INTEGER PRIMARY KEY, stage TEXT NOT NULL
        );
        CREATE TABLE leads (
            id INTEGER PRIMARY KEY, email TEXT
        );
        CREATE TABLE loan_state_change_audit (
            id TEXT PRIMARY KEY, loan_id INTEGER, to_stage TEXT
        );
        """
    )
    for i in range(50):
        cur.execute("INSERT INTO loans VALUES (?, 'APPLICATION')", (i,))
    for i in range(30):
        cur.execute("INSERT INTO leads VALUES (?, ?)", (i, f"u{i}@x.io"))
    for i in range(20):
        cur.execute(
            "INSERT INTO loan_state_change_audit VALUES (?, ?, ?)",
            (f"id-{i}", i, "SUBMITTED"),
        )
    conn.commit()
    counts = _table_counts_sqlite(conn)
    conn.close()
    return counts


def _table_counts_sqlite(conn: sqlite3.Connection) -> Dict[str, int]:
    cur = conn.cursor()
    cur.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )
    tables = [r[0] for r in cur.fetchall()]
    out: Dict[str, int] = {}
    for t in tables:
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        out[t] = cur.fetchone()[0]
    return out


def _run_sqlite_drill(workdir: Path) -> Tuple[Dict, bool]:
    primary = workdir / "primary.db"
    dump = workdir / "dump.sql"
    restored = workdir / "restored.db"

    baseline = _seed_sqlite(primary)

    # Step 1: dump (text SQL — equivalent of pg_dump --format=plain).
    with sqlite3.connect(str(primary)) as conn:
        with open(dump, "w") as fh:
            for line in conn.iterdump():
                fh.write(line + "\n")

    # Step 2: drop -- delete the primary DB outright, as if the volume
    # was lost.
    primary.unlink()

    # Step 3: restore into a brand-new file.
    conn = sqlite3.connect(str(restored))
    with open(dump, "r") as fh:
        conn.executescript(fh.read())
    conn.commit()

    # Step 4: parity check.
    restored_counts = _table_counts_sqlite(conn)
    conn.close()

    deltas: Dict[str, int] = {}
    success = True
    for table, expected in baseline.items():
        actual = restored_counts.get(table, 0)
        deltas[table] = actual - expected
        if actual != expected:
            success = False
    # Catch tables that appeared post-restore (shouldn't happen).
    for table, actual in restored_counts.items():
        if table not in baseline:
            deltas[table] = actual
            success = False

    details = {
        "tables_restored": len(restored_counts),
        "row_count_deltas": deltas,
        "baseline_total_rows": sum(baseline.values()),
        "restored_total_rows": sum(restored_counts.values()),
    }
    return details, success


# ---------------------------------------------------------------------------
# PostgreSQL drill (production-shaped, requires pg_dump/pg_restore in $PATH)
# ---------------------------------------------------------------------------
def _run_postgres_drill(workdir: Path, db_url: str) -> Tuple[Dict, bool]:
    if not shutil.which("pg_dump") or not shutil.which("psql"):
        return (
            {"error": "pg_dump or psql not on PATH"},
            False,
        )

    dump_path = workdir / "dump.sql"

    # 1. pg_dump
    res = subprocess.run(
        ["pg_dump", "--no-owner", "--no-acl", "-d", db_url, "-f", str(dump_path)],
        capture_output=True, text=True,
    )
    if res.returncode != 0:
        return ({"error": f"pg_dump failed: {res.stderr}"}, False)

    # 2./3. Drop & recreate a parallel schema for restore.
    restore_schema = "dr_drill_restore"
    psql_cmd = ["psql", db_url, "-v", "ON_ERROR_STOP=1", "-c"]
    subprocess.run(psql_cmd + [f"DROP SCHEMA IF EXISTS {restore_schema} CASCADE;"],
                   capture_output=True)
    subprocess.run(psql_cmd + [f"CREATE SCHEMA {restore_schema};"],
                   capture_output=True)
    res = subprocess.run(
        ["psql", db_url, "-v", "ON_ERROR_STOP=1",
         "-c", f"SET search_path TO {restore_schema};",
         "-f", str(dump_path)],
        capture_output=True, text=True,
    )
    success = res.returncode == 0
    return (
        {
            "dump_bytes": dump_path.stat().st_size if dump_path.exists() else 0,
            "restore_schema": restore_schema,
            "stderr_tail": (res.stderr or "")[-500:],
        },
        success,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def run_drill(target: str, report_dir: Path) -> Dict:
    report_dir.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    start_iso = datetime.now(timezone.utc).isoformat()

    with tempfile.TemporaryDirectory(prefix="dr_drill_") as tmp:
        workdir = Path(tmp)
        if target == "sqlite":
            details, success = _run_sqlite_drill(workdir)
        elif target == "postgres":
            db_url = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL", "")
            details, success = _run_postgres_drill(workdir, db_url)
        else:
            details = {"error": f"unknown target: {target}"}
            success = False

    end = time.monotonic()
    end_iso = datetime.now(timezone.utc).isoformat()
    rto_seconds = round(end - start, 3)

    report = {
        "start_time": start_iso,
        "end_time": end_iso,
        "rto_seconds": rto_seconds,
        "success": success,
        "target": target,
        **details,
    }

    ts = start_iso.replace(":", "").replace("-", "").replace(".", "_")
    report_path = report_dir / f"{ts}.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True))
    report["report_path"] = str(report_path)
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run a DR drill")
    parser.add_argument(
        "--target",
        choices=["sqlite", "postgres"],
        default="sqlite",
    )
    parser.add_argument(
        "--report-dir",
        default="dr_drills",
        help="Directory to write the drill report JSON.",
    )
    args = parser.parse_args(argv)

    report = run_drill(args.target, Path(args.report_dir))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("success") else 1


if __name__ == "__main__":
    sys.exit(main())
