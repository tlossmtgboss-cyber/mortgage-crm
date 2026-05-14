"""
PDF Sanitizer

Removes dangerous elements from PDF files before S3 storage:
- /JavaScript, /JS actions (embedded scripts)
- /Launch actions (execute external programs)
- /OpenAction, /AA (automatic actions on open/page view)
- /SubmitForm, /ImportData (data exfiltration / injection)
- /RichMedia (embedded Flash/video)
- Embedded executable files

The existing malware scanner DETECTS these threats but does not
neutralize them. This module removes the dangerous elements while
preserving the document's visual content.

Uses pypdf (with PyPDF2 fallback) which is already in requirements.

Usage:
    from utils.pdf_sanitizer import sanitize_pdf

    clean_bytes, removed = sanitize_pdf(raw_bytes)
    # removed = ["Removed /JavaScript from page 2", ...]
"""

import io
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)

# PDF dictionary keys that indicate dangerous actions
_DANGEROUS_KEYS = [
    "/JavaScript",
    "/JS",
    "/Launch",
    "/OpenAction",
    "/AA",
    "/SubmitForm",
    "/ImportData",
    "/RichMedia",
]


def sanitize_pdf(file_bytes: bytes) -> Tuple[bytes, List[str]]:
    """
    Remove dangerous elements from a PDF.

    Parses the PDF with pypdf, walks the page tree and document catalog,
    and removes any action dictionaries that could execute code or
    exfiltrate data. Returns the sanitized PDF bytes and a list of
    what was removed.

    Args:
        file_bytes: Raw PDF bytes.

    Returns:
        Tuple of (sanitized_bytes, removed_elements).
        - sanitized_bytes: The cleaned PDF. If sanitization fails,
          returns the original bytes unchanged.
        - removed_elements: List of human-readable strings describing
          what was removed (empty if nothing found).
    """
    if not file_bytes:
        return file_bytes, []

    # Quick check: does this look like a PDF?
    if not file_bytes[:5].startswith(b"%PDF"):
        return file_bytes, []

    removed: List[str] = []

    try:
        PdfReader, PdfWriter = _get_pdf_classes()
    except ImportError:
        logger.warning(
            "Neither pypdf nor PyPDF2 available, skipping PDF sanitization"
        )
        return file_bytes, []

    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        writer = PdfWriter()

        # --- Check what the READER's catalog contains (before copy) ---
        # pypdf's add_page() creates a fresh catalog, so catalog-level
        # actions (/OpenAction, /AA, /JavaScript) are automatically
        # dropped. We detect and report them here.
        try:
            reader_root = None
            if hasattr(reader, 'trailer') and reader.trailer:
                trailer_root_ref = reader.trailer.get("/Root")
                if trailer_root_ref:
                    if hasattr(trailer_root_ref, 'get_object'):
                        reader_root = trailer_root_ref.get_object()
                    elif isinstance(trailer_root_ref, dict):
                        reader_root = trailer_root_ref

            if reader_root and isinstance(reader_root, dict):
                for key in _DANGEROUS_KEYS:
                    if key in reader_root:
                        removed.append(
                            f"Removed {key} from document catalog "
                            f"(dropped during PDF reconstruction)"
                        )
        except Exception as e:
            logger.debug("Could not inspect reader catalog: %s", e)

        # Copy all pages to the writer
        for page in reader.pages:
            writer.add_page(page)

        # --- Sanitize the writer's catalog (belt-and-suspenders) ---
        if hasattr(writer, '_root_object'):
            root = writer._root_object
        elif hasattr(writer, '_root'):
            root = writer._root
        else:
            root = None

        if root is not None:
            _sanitize_dict(root, "document catalog", removed)

        # --- Sanitize each page ---
        for page_idx, page in enumerate(writer.pages):
            page_obj = page
            # Some pypdf versions wrap pages; get the underlying dict
            if hasattr(page_obj, 'get_object'):
                page_obj = page_obj.get_object()

            _sanitize_dict(page_obj, f"page {page_idx + 1}", removed)

            # Also check /Annots (annotations can carry /Launch, /URI actions)
            annots = page_obj.get("/Annots")
            if annots is not None:
                try:
                    annot_list = annots
                    if hasattr(annots, 'get_object'):
                        annot_list = annots.get_object()
                    if isinstance(annot_list, list):
                        for annot_ref in annot_list:
                            annot = annot_ref
                            if hasattr(annot_ref, 'get_object'):
                                annot = annot_ref.get_object()
                            if isinstance(annot, dict):
                                _sanitize_dict(
                                    annot,
                                    f"page {page_idx + 1} annotation",
                                    removed,
                                )
                except Exception as e:
                    logger.debug("Could not process annotations on page %d: %s", page_idx + 1, e)

        # --- Remove embedded files that look like executables ---
        _remove_dangerous_embedded_files(writer, removed)

        # Write sanitized PDF
        buf = io.BytesIO()
        writer.write(buf)
        result = buf.getvalue()

        if not result:
            logger.warning("PDF sanitization produced empty output, returning original")
            return file_bytes, []

        if removed:
            logger.info(
                "PDF sanitized: removed %d dangerous elements: %s",
                len(removed), "; ".join(removed),
            )

        return result, removed

    except Exception as e:
        logger.warning(
            "pypdf sanitization failed (%s), falling back to byte-level sanitization.",
            e,
        )
        # Fall through to byte-level sanitization
        return _sanitize_pdf_bytes(file_bytes)


def _sanitize_dict(
    d: dict,
    location: str,
    removed: List[str],
) -> None:
    """
    Remove dangerous keys from a PDF dictionary object.

    Modifies the dictionary in place.
    """
    if not isinstance(d, dict):
        return

    for key in _DANGEROUS_KEYS:
        if key in d:
            try:
                del d[key]
                removed.append(f"Removed {key} from {location}")
            except Exception as e:
                logger.debug("Could not remove %s from %s: %s", key, location, e)

    # Also check /A (action) and /PA (page-additional-actions) dicts
    # which may contain sub-actions
    for action_key in ["/A", "/PA"]:
        action = d.get(action_key)
        if action is not None:
            if hasattr(action, 'get_object'):
                action = action.get_object()
            if isinstance(action, dict):
                action_type = action.get("/S", "")
                # Resolve indirect objects
                if hasattr(action_type, 'get_object'):
                    action_type = action_type.get_object()
                action_type_str = str(action_type)

                dangerous_action_types = {
                    "/JavaScript", "/Launch", "/SubmitForm",
                    "/ImportData", "/RichMedia",
                }
                if action_type_str in dangerous_action_types:
                    try:
                        del d[action_key]
                        removed.append(
                            f"Removed {action_key} (type={action_type_str}) "
                            f"from {location}"
                        )
                    except Exception as e:
                        logger.debug(
                            "Could not remove action %s from %s: %s",
                            action_key, location, e,
                        )


def _remove_dangerous_embedded_files(writer, removed: List[str]) -> None:
    """Remove embedded files that look like executables from the PDF."""
    dangerous_extensions = {
        ".exe", ".dll", ".bat", ".cmd", ".vbs", ".ps1",
        ".scr", ".com", ".pif", ".jar", ".msi",
    }

    try:
        root = None
        if hasattr(writer, '_root_object'):
            root = writer._root_object
        elif hasattr(writer, '_root'):
            root = writer._root

        if root is None:
            return

        names = root.get("/Names")
        if names is None:
            return

        if hasattr(names, 'get_object'):
            names = names.get_object()

        ef_tree = names.get("/EmbeddedFiles") if isinstance(names, dict) else None
        if ef_tree is None:
            return

        if hasattr(ef_tree, 'get_object'):
            ef_tree = ef_tree.get_object()

        # The embedded files tree has /Names array: [name1, ref1, name2, ref2, ...]
        names_array = ef_tree.get("/Names") if isinstance(ef_tree, dict) else None
        if not names_array or not isinstance(names_array, list):
            return

        # Walk in pairs: [filename, filespec, filename, filespec, ...]
        indices_to_remove = []
        for i in range(0, len(names_array) - 1, 2):
            name = str(names_array[i])
            name_lower = name.lower()
            if any(name_lower.endswith(ext) for ext in dangerous_extensions):
                indices_to_remove.append(i)
                removed.append(f"Removed embedded file: {name}")

        # Remove in reverse order to preserve indices
        for i in reversed(indices_to_remove):
            names_array.pop(i + 1)  # Remove filespec ref
            names_array.pop(i)      # Remove name

    except Exception as e:
        logger.debug("Could not check embedded files: %s", e)


def _sanitize_pdf_bytes(file_bytes: bytes) -> Tuple[bytes, List[str]]:
    """
    Byte-level PDF sanitization fallback.

    When pypdf cannot parse a PDF (malformed xref, encrypted, etc.),
    this function performs direct byte-level replacement of dangerous
    PDF action keywords. Less precise than the tree-walking approach
    but still effective at neutralizing known attack vectors.

    Replaces dangerous keywords with padded comments of the same length
    to preserve the PDF structure (xref offsets stay valid).
    """
    import re as _re

    removed: List[str] = []
    result = file_bytes

    # Patterns to neutralize (replace with same-length comment padding)
    _BYTE_PATTERNS = [
        (rb"/JavaScript", "JavaScript action"),
        (rb"/JS\s*\(", "JS action (parenthesized)"),
        (rb"/JS\s*<", "JS action (hex-encoded)"),
        (rb"/Launch", "Launch action"),
        (rb"/OpenAction", "OpenAction"),
        (rb"/SubmitForm", "SubmitForm action"),
        (rb"/ImportData", "ImportData action"),
        (rb"/RichMedia", "RichMedia"),
    ]

    for pattern, description in _BYTE_PATTERNS:
        matches = list(_re.finditer(pattern, result))
        if matches:
            # Replace each match with a comment of the same byte length.
            # Use "/ " (space) which is an invalid PDF name and gets ignored,
            # padded with spaces.
            for match in reversed(matches):
                original = match.group()
                # Replace the "/" with "% " to comment it out, keep same length
                replacement = b"%" + b" " * (len(original) - 1)
                result = result[:match.start()] + replacement + result[match.end():]
            removed.append(
                f"Neutralized {len(matches)} {description} occurrence(s) "
                f"(byte-level)"
            )

    if removed:
        logger.info(
            "PDF byte-level sanitization: %s",
            "; ".join(removed),
        )

    return result, removed


def _get_pdf_classes():
    """Import PdfReader and PdfWriter from pypdf or PyPDF2."""
    try:
        from pypdf import PdfReader, PdfWriter
        return PdfReader, PdfWriter
    except ImportError:
        from PyPDF2 import PdfReader, PdfWriter  # type: ignore[no-redef]
        return PdfReader, PdfWriter
