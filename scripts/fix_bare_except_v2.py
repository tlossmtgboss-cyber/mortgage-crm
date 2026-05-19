#!/usr/bin/env python3
"""
Codemod v2: rewrite `except Exception:` -> `except Exception as _exc:  # noqa: BLE001`
and inject a logger.exception(...) call as the first statement of the handler
body when the body doesn't already log / raise / return / pass / continue / break.

Unlike v1, this version will INJECT `import logging` and `logger = logging.getLogger(__name__)`
at the top of any module (after the leading docstring and __future__ imports) that
contains bare `except Exception:` but has no logger in scope.

For handler bodies that consist solely of `pass` (cleanup idiom), append a
`# noqa: BLE001` marker on the except line (already there) and leave body alone.

Skips: backend/tests/, backend/alembic/, backend/migrations/, __pycache__, .venv, venv.
Run from repo root:  python3 scripts/fix_bare_except_v2.py
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND = REPO_ROOT / "backend"

SKIP_DIR_PARTS = {"tests", "alembic", "migrations", "__pycache__", ".venv", "venv"}

EXCEPT_RE = re.compile(r"^(?P<indent>[ \t]*)except Exception:[ \t]*(?P<comment>#.*)?$")
INDENT_RE = re.compile(r"^([ \t]*)")

LOG_SIGNATURES = ("logger.", "log.", "logging.", "self.logger.", "self.log.", "_logger.")
NO_INJECT_PREFIXES = LOG_SIGNATURES + ("raise", "return", "pass", "continue", "break")


def has_logger_in_scope(source: str) -> bool:
    return (
        re.search(r"^\s*logger\s*=\s*logging\.getLogger", source, re.MULTILINE) is not None
        or re.search(r"^\s*_logger\s*=\s*logging\.getLogger", source, re.MULTILINE) is not None
        or re.search(r"^\s*log\s*=\s*logging\.getLogger", source, re.MULTILINE) is not None
        or re.search(r"\bfrom\s+\S+\s+import\s+.*\blogger\b", source) is not None
        or re.search(r"\bget_logger\s*\(", source) is not None
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


def find_injection_point(lines: list[str]) -> int:
    """
    Return the index AFTER which we should insert the logger init.
    Skips shebang, encoding, module docstring, __future__ imports, and any
    consecutive `import` / `from X import Y` lines at the top.
    """
    i = 0
    n = len(lines)

    # Shebang
    if i < n and lines[i].startswith("#!"):
        i += 1
    # Encoding / leading comments
    while i < n and lines[i].lstrip().startswith("#"):
        i += 1
    # Blank lines
    while i < n and not lines[i].strip():
        i += 1

    # Module docstring
    if i < n:
        stripped = lines[i].lstrip()
        if stripped.startswith('"""') or stripped.startswith("'''"):
            quote = '"""' if stripped.startswith('"""') else "'''"
            # Single-line docstring?
            if stripped.count(quote) >= 2 and len(stripped) > 3:
                i += 1
            else:
                i += 1
                while i < n and quote not in lines[i]:
                    i += 1
                if i < n:
                    i += 1

    # __future__ imports + blank lines + ordinary imports at the top
    last_import = i - 1
    j = i
    while j < n:
        s = lines[j].strip()
        if not s:
            j += 1
            continue
        if s.startswith("from __future__ ") or s.startswith("import ") or s.startswith("from "):
            last_import = j
            j += 1
            continue
        break

    return last_import + 1


def inject_logger(lines: list[str]) -> list[str]:
    idx = find_injection_point(lines)
    eol = "\n"
    # Detect CRLF
    for ln in lines:
        if ln.endswith("\r\n"):
            eol = "\r\n"
            break

    insert_block = [
        f"import logging{eol}",
        f"logger = logging.getLogger(__name__){eol}",
        eol,
    ]

    # Avoid duplicate `import logging` line if one already exists somewhere we missed
    head = "".join(lines[:idx])
    if "import logging" in head:
        insert_block = [f"logger = logging.getLogger(__name__){eol}", eol]

    return lines[:idx] + insert_block + lines[idx:]


def process_file(path: Path) -> tuple[int, int, bool]:
    """Returns (rewrites, log_injections, logger_imported)."""
    original = path.read_text(encoding="utf-8")
    if "except Exception:" not in original:
        return (0, 0, False)

    lines = original.splitlines(keepends=True)

    # Maybe inject logger import
    logger_injected = False
    if not has_logger_in_scope(original):
        lines = inject_logger(lines)
        logger_injected = True

    out: list[str] = []
    rewrites = 0
    injections = 0

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped_line = line.rstrip("\n").rstrip("\r")
        m = EXCEPT_RE.match(stripped_line)
        if not m:
            out.append(line)
            i += 1
            continue

        indent = m.group("indent")
        existing_comment = m.group("comment") or ""
        # Preserve original line ending
        eol = "\r\n" if line.endswith("\r\n") else "\n"

        # Decide whether to add `noqa: BLE001` to the comment
        if "noqa" in existing_comment:
            tail_comment = f"  {existing_comment}".rstrip()
        elif existing_comment:
            # Append BLE001 to existing comment
            tail_comment = f"  {existing_comment.rstrip()}  # noqa: BLE001"
        else:
            tail_comment = "  # noqa: BLE001"

        rewritten = f"{indent}except Exception as _exc:{tail_comment}{eol}"
        out.append(rewritten)
        rewrites += 1
        i += 1

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
        if stripped_body.startswith(NO_INJECT_PREFIXES):
            # Skip injection if it's pass/raise/return/continue/break/log call
            continue
        # Inject before body_line at body_indent
        inject = f'{body_indent}logger.exception("unhandled exception"){eol}'
        # Copy any blank/comment lines between i and j first.
        while i < j:
            out.append(lines[i])
            i += 1
        out.append(inject)
        injections += 1

    new_source = "".join(out)
    if new_source != original:
        path.write_text(new_source, encoding="utf-8")
    return (rewrites, injections, logger_injected)


def main() -> int:
    files_modified = 0
    total_rewrites = 0
    total_injections = 0
    files_logger_injected = 0
    files_scanned = 0
    modified_paths: list[str] = []
    logger_injected_paths: list[str] = []

    for root, dirs, files in os.walk(BACKEND):
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
            rewrites, injections, logger_injected = process_file(path)
            if rewrites:
                files_modified += 1
                total_rewrites += rewrites
                total_injections += injections
                modified_paths.append(str(rel))
                if logger_injected:
                    files_logger_injected += 1
                    logger_injected_paths.append(str(rel))

    print("=" * 60)
    print("fix_bare_except_v2 codemod summary")
    print("=" * 60)
    print(f"Files scanned:                {files_scanned}")
    print(f"Files modified:               {files_modified}")
    print(f"Except clauses rewritten:     {total_rewrites}")
    print(f"Log lines injected:           {total_injections}")
    print(f"Files w/ new logger import:   {files_logger_injected}")
    print()
    print("Modified files:")
    for p in modified_paths:
        print(f"  {p}")
    print()
    print("Logger injected into:")
    for p in logger_injected_paths:
        print(f"  {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
