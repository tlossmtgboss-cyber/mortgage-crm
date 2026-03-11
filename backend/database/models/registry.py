"""
Model Registry -- Detects duplicate __tablename__ definitions and model sprawl.

Scans all classes inheriting from Base and reports:
- Duplicate table names (same __tablename__ in multiple files)
- Models defined outside database/models/ (sprawl)
"""

import inspect
import logging
import os
from collections import defaultdict
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Canonical model directory (normalized, no trailing slash)
_CANONICAL_MODEL_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__))
)


def _get_source_file(cls: type) -> Optional[str]:
    """Get the source file path for a class, or None if unavailable."""
    try:
        source_file = inspect.getfile(cls)
        return os.path.normpath(os.path.abspath(source_file))
    except (TypeError, OSError):
        return None


def scan_models() -> Dict[str, Any]:
    """Inspect Base subclasses and Base.metadata.tables.

    Returns a dict with:
        - "models": list of dicts with class_name, tablename, source_file
        - "tables": list of table names registered in metadata
        - "model_count": total number of model classes found
        - "table_count": total number of tables in metadata
    """
    from db import Base

    models = []
    seen = set()

    for cls in Base.__subclasses__():
        # Walk the full subclass tree (handles multi-level inheritance)
        queue = [cls]
        while queue:
            klass = queue.pop()
            if klass in seen:
                continue
            seen.add(klass)
            queue.extend(klass.__subclasses__())

            tablename = getattr(klass, "__tablename__", None)
            if tablename is None:
                continue  # Abstract base, mixin, etc.

            source_file = _get_source_file(klass)
            models.append({
                "class_name": klass.__name__,
                "tablename": tablename,
                "source_file": source_file,
            })

    table_names = sorted(Base.metadata.tables.keys())

    return {
        "models": models,
        "tables": table_names,
        "model_count": len(models),
        "table_count": len(table_names),
    }


def check_duplicates(scan: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Find models with the same __tablename__ defined in different files.

    Returns a list of dicts, each describing a duplicate:
        {
            "tablename": "some_table",
            "definitions": [
                {"class_name": "Foo", "source_file": "/path/to/foo.py"},
                {"class_name": "Bar", "source_file": "/path/to/bar.py"},
            ]
        }

    Only reports cases where the same tablename appears in MORE THAN ONE
    distinct source file (re-exports from __init__.py are not duplicates).
    """
    if scan is None:
        scan = scan_models()

    by_table = defaultdict(list)
    for model in scan["models"]:
        by_table[model["tablename"]].append({
            "class_name": model["class_name"],
            "source_file": model["source_file"],
        })

    duplicates = []
    for tablename, definitions in sorted(by_table.items()):
        # Deduplicate by source file -- same class imported in multiple places
        # shows up once per file, but that's fine if it's the same file.
        unique_files = {d["source_file"] for d in definitions if d["source_file"]}
        if len(unique_files) > 1:
            duplicates.append({
                "tablename": tablename,
                "definitions": definitions,
            })

    return duplicates


def get_sprawl_report(scan: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """List models NOT defined inside the database/models/ directory.

    Returns a list of dicts:
        {"class_name": "Foo", "tablename": "foos", "source_file": "/path/to/foo.py"}
    """
    if scan is None:
        scan = scan_models()

    sprawl = []
    for model in scan["models"]:
        source = model["source_file"]
        if source is None:
            continue  # Can't determine origin -- skip
        if not source.startswith(_CANONICAL_MODEL_DIR + os.sep):
            sprawl.append(model)

    return sprawl


def validate_on_startup() -> Dict[str, Any]:
    """Run all checks and log warnings. Never raises.

    Returns a summary dict with counts and details for programmatic use.
    """
    summary = {
        "model_count": 0,
        "table_count": 0,
        "duplicate_count": 0,
        "sprawl_count": 0,
        "duplicates": [],
        "sprawl": [],
    }

    try:
        scan = scan_models()
        summary["model_count"] = scan["model_count"]
        summary["table_count"] = scan["table_count"]

        # Check duplicates
        duplicates = check_duplicates(scan)
        summary["duplicate_count"] = len(duplicates)
        summary["duplicates"] = duplicates

        if duplicates:
            logger.warning(
                "Model registry: %d duplicate __tablename__ definitions found",
                len(duplicates),
            )
            for dup in duplicates:
                files = [d["source_file"] or "unknown" for d in dup["definitions"]]
                logger.warning(
                    "  Duplicate table '%s' defined in: %s",
                    dup["tablename"],
                    ", ".join(files),
                )

        # Check sprawl
        sprawl = get_sprawl_report(scan)
        summary["sprawl_count"] = len(sprawl)
        summary["sprawl"] = sprawl

        if sprawl:
            logger.warning(
                "Model registry: %d model(s) defined outside database/models/",
                len(sprawl),
            )
            for s in sprawl:
                logger.warning(
                    "  Sprawl: %s (table '%s') in %s",
                    s["class_name"],
                    s["tablename"],
                    s["source_file"] or "unknown",
                )

        if not duplicates and not sprawl:
            logger.info(
                "Model registry: OK -- %d models, %d tables, no issues",
                scan["model_count"],
                scan["table_count"],
            )

    except Exception as e:
        logger.warning("Model registry validation failed (non-fatal): %s", e)
        summary["error"] = str(e)

    return summary
