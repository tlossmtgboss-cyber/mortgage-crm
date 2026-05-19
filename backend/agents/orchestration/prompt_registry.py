"""
Prompt Registry — Versioned prompt storage with rollback
=========================================================

Wave 5 (D3 audit remediation). Closes the "no prompt versioning + rollback"
gap by giving every prompt a semver-stamped history with SHA-256 change
detection.

Backing store
-------------
A flat JSON file at ``backend/agents/orchestration/_prompts_registry.json``::

    {
      "prompt_id": [
        {
          "version":      "1.0.0",
          "content_hash": "<sha256>",
          "content":      "<full text>",
          "metadata":     {...},
          "created_at":   "2026-05-19T...",
          "deprecated_at": null,
          "is_current":   true
        },
        ...
      ]
    }

The flat file is fine for v1 (low write volume, single-writer at registration
time). **Production should swap this for a Postgres-backed store** (e.g.
``prompt_versions`` table with row-level locks) so multi-worker deploys can
share a registry without file-lock contention. The public API stays the same.

Concurrency
-----------
Writes are serialized with ``threading.Lock`` (intra-process) plus
``fcntl.flock`` (inter-process, Unix only). On non-Unix platforms the file
lock is a no-op — same-host concurrent writers should be avoided in that
configuration.

Idempotency
-----------
``register(prompt_id, version, content, ...)`` is idempotent on content_hash:
if the latest version of ``prompt_id`` already has the same SHA-256 the call
is a no-op (and returns the existing version). This lets callers register on
every prompt load without growing version history when nothing changed.

Public surface
--------------
* ``PromptRegistry.register(prompt_id, version, content, metadata=None)``
* ``PromptRegistry.get(prompt_id, version=None)``  — ``None`` = latest
* ``PromptRegistry.list_versions(prompt_id)``
* ``PromptRegistry.rollback(prompt_id, target_version)``
* ``PromptRegistry.current_version(prompt_id) -> str``
* ``PromptRegistry.list_prompts() -> list[str]``
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:  # POSIX file lock; harmless to skip on Windows.
    import fcntl  # type: ignore
    _HAS_FCNTL = True
except ImportError:  # pragma: no cover - non-POSIX
    fcntl = None  # type: ignore
    _HAS_FCNTL = False

logger = logging.getLogger(__name__)

_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
_DEFAULT_STORE = Path(__file__).resolve().parent / "_prompts_registry.json"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _validate_semver(version: str) -> None:
    if not isinstance(version, str) or not _SEMVER_RE.match(version):
        raise ValueError(f"version must be semver (e.g. '1.0.0'); got: {version!r}")


def _semver_key(version: str) -> tuple:
    try:
        return tuple(int(p) for p in version.split("."))
    except Exception:  # noqa: BLE001
        return (0, 0, 0)


class PromptRegistry:
    """File-backed, thread-safe prompt version store."""

    def __init__(self, store_path: Optional[Path] = None) -> None:
        self._path = Path(store_path) if store_path else _DEFAULT_STORE
        self._lock = threading.Lock()
        # Touch the parent directory; create empty file if missing.
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._write_atomic({})

    # ------------------------------------------------------------------
    # Low-level IO
    # ------------------------------------------------------------------

    def _read_all(self) -> Dict[str, List[Dict[str, Any]]]:
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                if _HAS_FCNTL:
                    try:
                        fcntl.flock(fh.fileno(), fcntl.LOCK_SH)  # type: ignore[union-attr]
                    except OSError:
                        pass
                raw = fh.read()
            if not raw.strip():
                return {}
            data = json.loads(raw)
            if not isinstance(data, dict):
                return {}
            return data
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError as exc:
            logger.error("prompt registry corrupt at %s: %s", self._path, exc)
            return {}

    def _write_atomic(self, data: Dict[str, List[Dict[str, Any]]]) -> None:
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            if _HAS_FCNTL:
                try:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX)  # type: ignore[union-attr]
                except OSError:
                    pass
            json.dump(data, fh, indent=2, sort_keys=True)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self._path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(
        self,
        prompt_id: str,
        version: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Register a prompt version. Idempotent on content_hash.

        Returns the stored record (either new or existing match).
        """
        if not prompt_id or not isinstance(prompt_id, str):
            raise ValueError("prompt_id must be a non-empty string")
        _validate_semver(version)
        if content is None:
            raise ValueError("content cannot be None")
        content = str(content)
        meta = dict(metadata or {})
        content_hash = _sha256(content)

        with self._lock:
            data = self._read_all()
            history = list(data.get(prompt_id, []))

            # Idempotency: if latest hash matches, return existing.
            if history:
                latest = max(history, key=lambda r: _semver_key(r.get("version", "0.0.0")))
                if latest.get("content_hash") == content_hash:
                    return latest

            # Reject duplicate version numbers — pick a fresh one.
            for rec in history:
                if rec.get("version") == version:
                    raise ValueError(
                        f"version {version} already exists for prompt_id={prompt_id!r}; "
                        "increment semver or call rollback()"
                    )

            # Mark prior records as not current.
            for rec in history:
                rec["is_current"] = False

            new_rec = {
                "version": version,
                "content_hash": content_hash,
                "content": content,
                "metadata": meta,
                "created_at": _utc_now_iso(),
                "deprecated_at": None,
                "is_current": True,
            }
            history.append(new_rec)
            history.sort(key=lambda r: _semver_key(r.get("version", "0.0.0")))
            data[prompt_id] = history
            self._write_atomic(data)
            return new_rec

    def get(self, prompt_id: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Fetch a prompt version. ``version=None`` returns the current record."""
        with self._lock:
            data = self._read_all()
            history = data.get(prompt_id, [])
            if not history:
                return None
            if version is None:
                # Find is_current, fall back to highest semver.
                current = [r for r in history if r.get("is_current")]
                if current:
                    return current[0]
                return max(history, key=lambda r: _semver_key(r.get("version", "0.0.0")))
            for rec in history:
                if rec.get("version") == version:
                    return rec
            return None

    def list_versions(self, prompt_id: str) -> List[Dict[str, Any]]:
        """Version history for a prompt_id (oldest first)."""
        with self._lock:
            data = self._read_all()
            history = list(data.get(prompt_id, []))
            history.sort(key=lambda r: _semver_key(r.get("version", "0.0.0")))
            return history

    def rollback(self, prompt_id: str, target_version: str) -> Dict[str, Any]:
        """Make ``target_version`` the current record. Older 'current' is
        marked deprecated. The target's content is preserved (rollback does
        not delete newer versions — it just flips the current pointer)."""
        _validate_semver(target_version)
        with self._lock:
            data = self._read_all()
            history = list(data.get(prompt_id, []))
            if not history:
                raise KeyError(f"prompt_id={prompt_id!r} has no registered versions")
            target = None
            for rec in history:
                if rec.get("version") == target_version:
                    target = rec
                    break
            if target is None:
                raise KeyError(
                    f"version {target_version} not found for prompt_id={prompt_id!r}"
                )
            now = _utc_now_iso()
            for rec in history:
                if rec.get("is_current") and rec is not target:
                    rec["is_current"] = False
                    rec["deprecated_at"] = now
            target["is_current"] = True
            target["deprecated_at"] = None
            data[prompt_id] = history
            self._write_atomic(data)
            return target

    def current_version(self, prompt_id: str) -> Optional[str]:
        rec = self.get(prompt_id, None)
        return rec.get("version") if rec else None

    def list_prompts(self) -> List[str]:
        with self._lock:
            data = self._read_all()
            return sorted(data.keys())


# Module-level default singleton (file-backed at the default path).
_default_registry: Optional[PromptRegistry] = None


def get_default_registry() -> PromptRegistry:
    """Lazy-init the module singleton."""
    global _default_registry
    if _default_registry is None:
        _default_registry = PromptRegistry()
    return _default_registry


__all__ = ["PromptRegistry", "get_default_registry"]
