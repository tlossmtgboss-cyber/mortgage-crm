"""Lightweight codebase scanning utilities.

Agents declare which tools they're authorized to use in ``agents.yaml``.
The base agent enforces those permissions at the envelope level; this
module provides the actual implementations agents call from their
build_prompt step to fetch the evidence they need.

We deliberately keep these read-only. Any mutation of the target
codebase flows through patches, not direct file writes from here.
"""
from __future__ import annotations

import ast
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator


# ----------------------------------------------------------------------------
# File reading
# ----------------------------------------------------------------------------


@dataclass
class FileSnippet:
    path: str
    start_line: int
    end_line: int
    content: str


def read_lines(root: str | Path, relpath: str, lines: tuple[int, int] | None = None) -> FileSnippet:
    """Read an inclusive line range from a file under `root`."""
    target = Path(root) / relpath
    text = target.read_text(encoding="utf-8", errors="replace").splitlines()
    if lines is None:
        start, end = 1, len(text)
        body = "\n".join(text)
    else:
        start, end = lines
        body = "\n".join(text[start - 1:end])
    return FileSnippet(path=relpath, start_line=start, end_line=end, content=body)


# ----------------------------------------------------------------------------
# Grep
# ----------------------------------------------------------------------------


@dataclass
class GrepHit:
    path: str
    line: int
    text: str


def grep(root: str | Path, pattern: str, globs: Iterable[str]) -> list[GrepHit]:
    """Regex search across files matching any of the provided globs."""
    rx = re.compile(pattern)
    hits: list[GrepHit] = []
    root = Path(root)
    for g in globs:
        for path in root.glob(g):
            if not path.is_file():
                continue
            try:
                for idx, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
                    if rx.search(line):
                        rel = str(path.relative_to(root))
                        hits.append(GrepHit(path=rel, line=idx, text=line))
            except (UnicodeDecodeError, OSError):
                continue
    return hits


# ----------------------------------------------------------------------------
# Python AST walking
# ----------------------------------------------------------------------------


@dataclass
class AttrHit:
    path: str
    line: int
    col: int
    attr_chain: str  # e.g. "doc.document_id"


def walk_attribute_access(
    root: str | Path,
    globs: Iterable[str],
    target_attrs: set[str],
) -> list[AttrHit]:
    """Walk Python ASTs and flag every attribute access matching `target_attrs`.

    For example, ``target_attrs={'id', 'document_id'}`` produces every
    ``<something>.id`` and ``<something>.document_id`` reference with
    file/line information — exactly the input A02 and A03 need.
    """
    hits: list[AttrHit] = []
    root = Path(root)
    for g in globs:
        for path in root.glob(g):
            if not path.is_file() or path.suffix != ".py":
                continue
            try:
                tree = ast.parse(path.read_text(errors="replace"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr in target_attrs:
                    chain = _attr_chain(node)
                    if chain:
                        hits.append(AttrHit(
                            path=str(path.relative_to(root)),
                            line=getattr(node, "lineno", 0),
                            col=getattr(node, "col_offset", 0),
                            attr_chain=chain,
                        ))
    return hits


def _attr_chain(node: ast.AST) -> str | None:
    parts: list[str] = []
    cur: ast.AST = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
        return ".".join(reversed(parts))
    return None


# ----------------------------------------------------------------------------
# Access-log querying
# ----------------------------------------------------------------------------


def log_traffic_by_route(log_path: str | Path) -> dict[str, int]:
    """Count hits per route from a JSONL access log.

    Expects lines of the shape: ``{"path": "/api/...", "status": 200, ...}``.
    Robust to missing keys.
    """
    import json
    from collections import Counter

    counts: Counter[str] = Counter()
    path = Path(log_path)
    if not path.exists():
        return {}
    with path.open() as f:
        for line in f:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            route = event.get("path") or event.get("route")
            if route:
                counts[route] += 1
    return dict(counts)


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------


def glob_files(root: str | Path, globs: Iterable[str]) -> Iterator[Path]:
    r = Path(root)
    for g in globs:
        yield from r.glob(g)
