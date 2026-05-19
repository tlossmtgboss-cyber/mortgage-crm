#!/usr/bin/env python3
"""
Codemod: rewrite `except Exception:` -> `except Exception as _exc:  # noqa: BLE001`
and inject a logger.exception(...) call as the first statement of the handler
body when the body doesn't already log / raise / return.

Skips files that don't already import logging/logger to avoid adding new
imports (and to keep the import graph stable).

Skips: backend/tests/, backend/alembic/, backend/migrations/, __pycache__.
Run from repo root:  python3 scripts/fix_bare_except.py
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND = REPO_ROOT / "backend"

SKIP_DIR_PARTS = {"tests", "alembic", "migrations", "__pycache__", ".venv", "venv"}

EXCEPT_RE = re.compile(r"^(?P<indent>[ \t]*)except Exception:[ \t]*(?:#.*)?$")
INDENT_RE = re.compile(r"^([ \t]*)")

LOG_SIGNATURES = ("logger.", "log.", "logging.", "self.logger.", "self.log.", "_logger.")
SKIP_FIRST_LINE_PREFIXES = LOG_SIGNATURES + ("raise", "return", "pass", "continue", "break")


def has_logger_import(source: str) -> bool:
    # Cheap heuristic: any of these patterns means logging is already in scope.
    return (
        "import logging" in source
        or "from logging" in source
        or re.search(r"\blogger\s*=", source) is not None
        or re.search(r"\b_logger\s*=", source) is not None
        or "get_logger(" in source
    )


def should_skip(path: Path) -> bool:
    parts = set(path.parts)
    return bool(parts & SKIP_DIR_PARTS)


def first_non_empty_idx(lines: list[str], start: int) -> int:
    i = start
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped and not stripped.startswith("#"):
            return i
        i += 1
    return -1


def process_file(path: Path, can_inject_log: bool) -> tuple[int, int]:
    """Returns (rewrites, log_injections)."""
    original = path.read_text(encoding="utf-8")
    if "except Exception:" not in original:
        return (0, 0)

    lines = original.splitlines(keepends=True)
    out: list[str] = []
    rewrites = 0
    injections = 0

    i = 0
    while i < len(lines):
        line = lines[i]
        m = EXCEPT_RE.match(line.rstrip("\n").rstrip("\r"))
        if not m:
            out.append(line)
            i += 1
            continue

        indent = m.group("indent")
        # Preserve original line ending
        eol = "\n"
        if line.endswith("\r\n"):
            eol = "\r\n"
        rewritten = f"{indent}except Exception as _exc:  # noqa: BLE001{eol}"
        out.append(rewritten)
        rewrites += 1
        i += 1

        if not can_inject_log:
            continue

        # Find next non-blank, non-comment line inside the handler body.
        j = first_non_empty_idx(lines, i)
        if j == -1:
            continue
        body_line = lines[j]
        body_indent_match = INDENT_RE.match(body_line)
        body_indent = body_indent_match.group(1) if body_indent_match else ""
        # Must be more indented than the except clause itself.
        if len(body_indent) <= len(indent):
            continue
        stripped_body = body_line.strip()
        if stripped_body.startswith(SKIP_FIRST_LINE_PREFIXES):
            continue
        # Inject before body_line. Use the body's own indent so we sit inside the block.
        inject = f'{body_indent}logger.exception("unhandled exception"){eol}'
        # Copy any blank/comment lines between i and j first.
        while i < j:
            out.append(lines[i])
            i += 1
        out.append(inject)
        injections += 1
        # Continue copying from body_line onward in the main loop.

    new_source = "".join(out)
    if new_source != original:
        path.write_text(new_source, encoding="utf-8")
    return (rewrites, injections)


def main() -> int:
    files_modified = 0
    total_rewrites = 0
    total_injections = 0
    files_skipped_no_logger = 0
    files_scanned = 0

    for root, dirs, files in os.walk(BACKEND):
        # Prune skip directories in-place
        dirs[:] = [d for d in dirs if d not in SKIP_DIR_PARTS]
        for fname in files:
            if not fname.endswith(".py"):
                continue
            path = Path(root) / fname
            rel = path.relative_to(REPO_ROOT)
            if should_skip(rel):
                continue
            files_scanned += 1
            try:
                source = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if "except Exception:" not in source:
                continue
            can_inject = has_logger_import(source)
            if not can_inject:
                files_skipped_no_logger += 1
            rewrites, injections = process_file(path, can_inject)
            if rewrites:
                files_modified += 1
                total_rewrites += rewrites
                total_injections += injections

    print("=" * 60)
    print("fix_bare_except codemod summary")
    print("=" * 60)
    print(f"Files scanned:                {files_scanned}")
    print(f"Files modified:               {files_modified}")
    print(f"Except clauses rewritten:     {total_rewrites}")
    print(f"Log lines injected:           {total_injections}")
    print(f"Files w/o logger (no inject): {files_skipped_no_logger}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
