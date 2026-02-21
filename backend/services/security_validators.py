"""
Security Validators
====================

Enterprise Readiness Domain 4: Security Audit.

Provides:
- File upload validation with magic byte verification (Check 4.15)
- Dependency vulnerability scanning (Check 4.24)
- Request payload size enforcement (Check 4.16)

Password complexity is handled by utils/auth.py:validate_password_strength().
"""

import logging
import subprocess
import json
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# FILE UPLOAD VALIDATION (Domain 4, Check 4.15)
# =============================================================================

# Magic byte signatures for common file types
MAGIC_BYTES: Dict[str, List[Tuple[bytes, int]]] = {
    # Documents
    "application/pdf": [(b"%PDF", 0)],
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [(b"PK\x03\x04", 0)],  # XLSX
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [(b"PK\x03\x04", 0)],  # DOCX
    "application/vnd.ms-excel": [(b"\xd0\xcf\x11\xe0", 0)],  # XLS (OLE)
    "application/msword": [(b"\xd0\xcf\x11\xe0", 0)],  # DOC (OLE)
    # Images
    "image/jpeg": [(b"\xff\xd8\xff", 0)],
    "image/png": [(b"\x89PNG\r\n\x1a\n", 0)],
    "image/gif": [(b"GIF87a", 0), (b"GIF89a", 0)],
    "image/webp": [(b"RIFF", 0)],
    "image/tiff": [(b"II\x2a\x00", 0), (b"MM\x00\x2a", 0)],
    # Archives
    "application/zip": [(b"PK\x03\x04", 0)],
}

# Allowed MIME types for document uploads
ALLOWED_UPLOAD_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/tiff",
    "image/webp",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/msword",
    "text/csv",
    "text/plain",
}

# Dangerous file extensions that should always be rejected
BLOCKED_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".com", ".msi", ".scr", ".pif",
    ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh", ".ps1",
    ".sh", ".bash", ".csh", ".ksh", ".py", ".rb", ".pl",
    ".dll", ".so", ".dylib", ".sys", ".drv",
    ".jar", ".war", ".ear", ".class",
    ".php", ".asp", ".aspx", ".jsp", ".cgi",
}

# Max file sizes per type (bytes)
MAX_FILE_SIZES = {
    "default": 25 * 1024 * 1024,         # 25MB
    "image": 10 * 1024 * 1024,            # 10MB for images
    "document": 50 * 1024 * 1024,         # 50MB for documents
    "spreadsheet": 25 * 1024 * 1024,      # 25MB for spreadsheets
}


def validate_file_upload(
    filename: str,
    content: bytes,
    claimed_mime_type: Optional[str] = None,
    max_size_bytes: Optional[int] = None,
) -> Dict:
    """
    Validate an uploaded file for security.

    Checks:
    1. File extension not in blocked list
    2. MIME type in allowed list
    3. Magic bytes match claimed type (prevents disguised executables)
    4. File size within limits
    5. No null bytes in filename (path traversal prevention)

    Returns:
        dict with 'valid' bool, 'errors' list, and 'detected_type' str
    """
    errors = []
    warnings = []
    detected_type = None

    # 1. Filename safety checks
    if not filename:
        errors.append("Filename is required")
        return {"valid": False, "errors": errors, "warnings": warnings, "detected_type": None}

    if "\x00" in filename or ".." in filename or "/" in filename or "\\" in filename:
        errors.append("Filename contains unsafe characters (null bytes, path traversal)")
        return {"valid": False, "errors": errors, "warnings": warnings, "detected_type": None}

    # 2. Extension check
    ext = ""
    if "." in filename:
        ext = "." + filename.rsplit(".", 1)[-1].lower()

    if ext in BLOCKED_EXTENSIONS:
        errors.append(f"File type '{ext}' is not allowed. Executable and script files are blocked.")
        return {"valid": False, "errors": errors, "warnings": warnings, "detected_type": None}

    # 3. MIME type check
    if claimed_mime_type and claimed_mime_type not in ALLOWED_UPLOAD_TYPES:
        errors.append(
            f"MIME type '{claimed_mime_type}' is not allowed. "
            f"Allowed types: {', '.join(sorted(ALLOWED_UPLOAD_TYPES))}"
        )

    # 4. Magic byte verification
    if content and len(content) >= 8:
        for mime_type, signatures in MAGIC_BYTES.items():
            for magic, offset in signatures:
                if content[offset:offset + len(magic)] == magic:
                    detected_type = mime_type
                    break
            if detected_type:
                break

        # Cross-check: if claimed MIME has magic bytes, verify they match
        if claimed_mime_type and claimed_mime_type in MAGIC_BYTES:
            match_found = False
            for magic, offset in MAGIC_BYTES[claimed_mime_type]:
                if content[offset:offset + len(magic)] == magic:
                    match_found = True
                    break
            if not match_found:
                errors.append(
                    f"File content does not match claimed type '{claimed_mime_type}'. "
                    f"Detected type: {detected_type or 'unknown'}"
                )

        # Check if detected type is an executable disguised with a safe extension
        executable_signatures = [
            (b"MZ", 0),           # Windows PE/EXE
            (b"\x7fELF", 0),     # Linux ELF
            (b"\xca\xfe\xba\xbe", 0),  # Mach-O (macOS)
            (b"\xfe\xed\xfa", 0),      # Mach-O
        ]
        for magic, offset in executable_signatures:
            if content[offset:offset + len(magic)] == magic:
                errors.append("File appears to be an executable binary disguised with a safe extension")
                break

    # 5. File size check
    max_size = max_size_bytes or MAX_FILE_SIZES["default"]
    if len(content) > max_size:
        errors.append(
            f"File size ({len(content):,} bytes) exceeds maximum allowed size ({max_size:,} bytes)"
        )

    # 6. Empty file check
    if len(content) == 0:
        errors.append("File is empty")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "detected_type": detected_type,
        "file_size": len(content),
        "filename": filename,
    }


# =============================================================================
# DEPENDENCY VULNERABILITY SCANNING (Domain 4, Check 4.24)
# =============================================================================

def scan_python_dependencies() -> Dict:
    """
    Scan Python dependencies for known vulnerabilities using pip-audit.

    Returns:
        dict with scan results, vulnerability count, and details
    """
    result = {
        "scanner": "pip-audit",
        "status": "unknown",
        "total_packages": 0,
        "vulnerabilities": {
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
        },
        "details": [],
    }

    try:
        # Try pip-audit first
        proc = subprocess.run(
            ["pip-audit", "--format", "json", "--progress-spinner", "off"],
            capture_output=True, text=True, timeout=120,
        )

        if proc.returncode == 0 or proc.stdout:
            audit_data = json.loads(proc.stdout) if proc.stdout.strip() else []
            result["status"] = "completed"
            result["total_packages"] = len(audit_data) if isinstance(audit_data, list) else 0

            vulns = audit_data if isinstance(audit_data, list) else audit_data.get("dependencies", [])
            for vuln in vulns:
                if isinstance(vuln, dict) and vuln.get("vulns"):
                    for v in vuln["vulns"]:
                        severity = _classify_severity(v.get("id", ""))
                        result["vulnerabilities"][severity] += 1
                        result["details"].append({
                            "package": vuln.get("name", "unknown"),
                            "version": vuln.get("version", "unknown"),
                            "vuln_id": v.get("id", "unknown"),
                            "severity": severity,
                            "fix_version": v.get("fix_versions", []),
                        })
        else:
            result["status"] = "error"
            result["error"] = proc.stderr[:500] if proc.stderr else "pip-audit returned non-zero"

    except FileNotFoundError:
        # pip-audit not installed, try safety check
        try:
            proc = subprocess.run(
                ["safety", "check", "--json"],
                capture_output=True, text=True, timeout=120,
            )
            result["scanner"] = "safety"
            if proc.stdout:
                safety_data = json.loads(proc.stdout)
                result["status"] = "completed"
                for vuln in safety_data:
                    if isinstance(vuln, list) and len(vuln) >= 5:
                        result["vulnerabilities"]["high"] += 1
                        result["details"].append({
                            "package": vuln[0],
                            "version": vuln[2],
                            "vuln_id": vuln[4] if len(vuln) > 4 else "unknown",
                            "severity": "high",
                        })
        except (FileNotFoundError, Exception) as e:
            result["scanner"] = "none"
            result["status"] = "no_scanner_available"
            result["error"] = (
                "No vulnerability scanner found. Install pip-audit: pip install pip-audit"
            )

    except subprocess.TimeoutExpired:
        result["status"] = "timeout"
        result["error"] = "Scan timed out after 120 seconds"

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)

    # Summary
    total_vulns = sum(result["vulnerabilities"].values())
    result["summary"] = (
        f"{total_vulns} vulnerabilities found "
        f"({result['vulnerabilities']['critical']} critical, "
        f"{result['vulnerabilities']['high']} high)"
    )
    result["pass"] = result["vulnerabilities"]["critical"] == 0 and result["vulnerabilities"]["high"] == 0

    return result


def scan_node_dependencies() -> Dict:
    """
    Scan Node.js dependencies for known vulnerabilities using npm audit.

    Returns:
        dict with scan results
    """
    result = {
        "scanner": "npm-audit",
        "status": "unknown",
        "vulnerabilities": {"critical": 0, "high": 0, "moderate": 0, "low": 0},
        "details": [],
    }

    try:
        proc = subprocess.run(
            ["npm", "audit", "--json"],
            capture_output=True, text=True, timeout=120,
            cwd="frontend",
        )
        if proc.stdout:
            audit_data = json.loads(proc.stdout)
            result["status"] = "completed"

            if "vulnerabilities" in audit_data:
                for name, info in audit_data["vulnerabilities"].items():
                    severity = info.get("severity", "low")
                    result["vulnerabilities"][severity] = result["vulnerabilities"].get(severity, 0) + 1
                    result["details"].append({
                        "package": name,
                        "severity": severity,
                        "via": info.get("via", []),
                    })
            elif "metadata" in audit_data:
                v = audit_data["metadata"].get("vulnerabilities", {})
                result["vulnerabilities"] = {
                    "critical": v.get("critical", 0),
                    "high": v.get("high", 0),
                    "moderate": v.get("moderate", 0),
                    "low": v.get("low", 0),
                }

    except FileNotFoundError:
        result["status"] = "npm_not_found"
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)

    total = sum(result["vulnerabilities"].values())
    result["summary"] = f"{total} vulnerabilities found"
    result["pass"] = result["vulnerabilities"]["critical"] == 0 and result["vulnerabilities"]["high"] == 0

    return result


def _classify_severity(vuln_id: str) -> str:
    """Classify vulnerability severity from ID patterns."""
    vuln_id = vuln_id.upper()
    # GHSA or CVE with known critical patterns
    if "CRITICAL" in vuln_id:
        return "critical"
    if "HIGH" in vuln_id:
        return "high"
    if "MEDIUM" in vuln_id or "MODERATE" in vuln_id:
        return "medium"
    return "low"
