"""CLI entry point.

Usage:
    python -m orchestrator.runner --codebase ~/perennia --findings 1,2,3
    python -m orchestrator.runner --codebase ~/perennia --all --apply

``--apply`` turns off dry-run; without it we only produce patch files
and reports (the safe default).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from orchestrator.graph import run_remediation


def _parse_findings(raw: str | None) -> list[int]:
    if not raw:
        return []
    return [int(x.strip()) for x in raw.split(",") if x.strip()]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="perennia-smart-docs-remediation")
    p.add_argument("--codebase", required=True, help="Path to Perennia monorepo checkout")
    p.add_argument("--findings", help="Comma-separated finding IDs, e.g. 1,2,3")
    p.add_argument("--all", action="store_true", help="Run every agent (all findings)")
    p.add_argument("--apply", action="store_true", help="Apply patches (default: dry-run)")
    p.add_argument("--parallelism", type=int, default=8)
    p.add_argument("--registry", default="config/agents.yaml")
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    if args.all and args.findings:
        p.error("--all and --findings are mutually exclusive")

    findings = [] if args.all else _parse_findings(args.findings)

    final = run_remediation(
        codebase_root=args.codebase,
        selected_findings=findings,
        dry_run=not args.apply,
        max_workers=args.parallelism,
        registry_path=args.registry,
    )

    report = Path(f"state/run_{final['run_id']}_report.json")
    print(f"\nrun complete — report at {report}")
    if report.exists():
        print(report.read_text())
    return 0


if __name__ == "__main__":
    sys.exit(main())
