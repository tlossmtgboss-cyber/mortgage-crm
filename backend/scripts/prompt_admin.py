#!/usr/bin/env python3
"""
prompt_admin.py — CLI for the versioned prompt registry.

Subcommands
-----------
    list                                 List all prompt_ids and current version
    versions <prompt_id>                 Show version history for a prompt_id
    rollback <prompt_id> <version>       Make <version> the current record
    diff <prompt_id> <v1> <v2>           Unified diff between two versions

Designed to be safe in production: read operations never mutate, and writes
(rollback) require an explicit confirmation flag.

Usage::

    python -m backend.scripts.prompt_admin list
    python -m backend.scripts.prompt_admin versions ctx:domain:mortgage
    python -m backend.scripts.prompt_admin rollback ctx:domain:mortgage 1.0.0 --yes
    python -m backend.scripts.prompt_admin diff ctx:domain:mortgage 1.0.0 1.1.0
"""
from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path


def _resolve_backend_on_path() -> Path:
    """Make ``backend`` importable when running this file directly."""
    here = Path(__file__).resolve()
    # backend/scripts/prompt_admin.py → backend/
    backend_dir = here.parent.parent
    repo_root = backend_dir.parent
    for candidate in (str(backend_dir), str(repo_root)):
        if candidate not in sys.path:
            sys.path.insert(0, candidate)
    return backend_dir


def _registry():
    _resolve_backend_on_path()
    from agents.orchestration.prompt_registry import get_default_registry  # noqa: WPS433
    return get_default_registry()


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_list(_args: argparse.Namespace) -> int:
    reg = _registry()
    rows = []
    for pid in reg.list_prompts():
        current = reg.get(pid, None)
        rows.append({
            "prompt_id": pid,
            "current_version": current.get("version") if current else None,
            "version_count": len(reg.list_versions(pid)),
        })
    print(json.dumps(rows, indent=2))
    return 0


def cmd_versions(args: argparse.Namespace) -> int:
    reg = _registry()
    history = reg.list_versions(args.prompt_id)
    if not history:
        print(f"no versions registered for prompt_id={args.prompt_id!r}", file=sys.stderr)
        return 1
    summary = [
        {
            "version": r.get("version"),
            "content_hash": r.get("content_hash", "")[:12],
            "is_current": bool(r.get("is_current")),
            "created_at": r.get("created_at"),
            "deprecated_at": r.get("deprecated_at"),
            "content_chars": len(r.get("content", "")),
        }
        for r in history
    ]
    print(json.dumps(summary, indent=2))
    return 0


def cmd_rollback(args: argparse.Namespace) -> int:
    reg = _registry()
    target = reg.get(args.prompt_id, args.version)
    if not target:
        print(
            f"version {args.version} not found for prompt_id={args.prompt_id!r}",
            file=sys.stderr,
        )
        return 1
    if not args.yes:
        print(
            f"refusing to rollback without --yes (would set {args.prompt_id} → {args.version})",
            file=sys.stderr,
        )
        return 2
    rec = reg.rollback(args.prompt_id, args.version)
    print(json.dumps({
        "rolled_back": True,
        "prompt_id": args.prompt_id,
        "current_version": rec.get("version"),
    }, indent=2))
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    reg = _registry()
    r1 = reg.get(args.prompt_id, args.v1)
    r2 = reg.get(args.prompt_id, args.v2)
    if not r1:
        print(f"version {args.v1} not found", file=sys.stderr)
        return 1
    if not r2:
        print(f"version {args.v2} not found", file=sys.stderr)
        return 1
    diff = difflib.unified_diff(
        r1.get("content", "").splitlines(keepends=True),
        r2.get("content", "").splitlines(keepends=True),
        fromfile=f"{args.prompt_id}@{args.v1}",
        tofile=f"{args.prompt_id}@{args.v2}",
        n=3,
    )
    sys.stdout.writelines(diff)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prompt registry administration")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List all prompt_ids and current versions").set_defaults(func=cmd_list)

    p_v = sub.add_parser("versions", help="Show version history for a prompt_id")
    p_v.add_argument("prompt_id")
    p_v.set_defaults(func=cmd_versions)

    p_r = sub.add_parser("rollback", help="Rollback to a prior version")
    p_r.add_argument("prompt_id")
    p_r.add_argument("version")
    p_r.add_argument("--yes", action="store_true", help="confirm the rollback")
    p_r.set_defaults(func=cmd_rollback)

    p_d = sub.add_parser("diff", help="Diff between two versions")
    p_d.add_argument("prompt_id")
    p_d.add_argument("v1")
    p_d.add_argument("v2")
    p_d.set_defaults(func=cmd_diff)

    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
