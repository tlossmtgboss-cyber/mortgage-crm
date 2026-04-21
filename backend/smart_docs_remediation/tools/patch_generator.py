"""Patch generation and application.

Agents emit unified diffs in their envelopes. This module writes them
to disk under ``fixes/patches/``, validates them via ``git apply
--check``, and applies them when the runner is not in dry-run mode.

Keeping patches on disk is intentional — it gives the operator a
concrete artifact to review before the PR is opened, and it makes
rollback trivial (``git apply -R``).
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Iterable

log = logging.getLogger(__name__)


class PatchError(RuntimeError):
    """Raised when a patch cannot be applied cleanly."""


def write_patch(patch_dir: str | Path, agent_id: str, target_path: str, diff: str) -> Path:
    """Write a patch file named ``{agent_id}__{sanitized_path}.patch``."""
    out_dir = Path(patch_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = target_path.replace("/", "__").replace("\\", "__")
    out = out_dir / f"{agent_id}__{stem}.patch"
    out.write_text(diff if diff.endswith("\n") else diff + "\n")
    return out


def validate(codebase_root: str | Path, patch_path: str | Path) -> None:
    """Run ``git apply --check``; raise if the patch is invalid."""
    result = subprocess.run(
        ["git", "apply", "--check", str(patch_path)],
        cwd=str(codebase_root),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise PatchError(
            f"git apply --check failed for {patch_path}:\n{result.stderr}"
        )


def apply(codebase_root: str | Path, patch_path: str | Path, *, dry_run: bool = True) -> None:
    """Apply a patch. In dry-run mode only validation runs."""
    validate(codebase_root, patch_path)
    if dry_run:
        log.info("patch.dry_run path=%s", patch_path)
        return
    result = subprocess.run(
        ["git", "apply", str(patch_path)],
        cwd=str(codebase_root),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise PatchError(f"git apply failed: {result.stderr}")
    log.info("patch.applied path=%s", patch_path)


def apply_many(
    codebase_root: str | Path,
    patch_paths: Iterable[str | Path],
    *,
    dry_run: bool = True,
) -> list[Path]:
    applied: list[Path] = []
    for p in patch_paths:
        apply(codebase_root, p, dry_run=dry_run)
        applied.append(Path(p))
    return applied


def revert(codebase_root: str | Path, patch_path: str | Path) -> None:
    result = subprocess.run(
        ["git", "apply", "-R", str(patch_path)],
        cwd=str(codebase_root),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise PatchError(f"revert failed: {result.stderr}")
    log.info("patch.reverted path=%s", patch_path)
