#!/usr/bin/env python3
"""
Code Evaluator - Automated Check Script

Scans Python and TypeScript/JavaScript files for common bug patterns,
anti-patterns, and security issues. Supplements manual review.

Usage:
    python3 check_code.py <file_or_directory> [--severity critical|high|medium|all]
"""

import ast
import os
import re
import sys
import json
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

@dataclass
class Finding:
    severity: str  # critical, high, medium, low
    category: str  # security, correctness, performance, etc.
    title: str
    file: str
    line: int
    message: str
    code_snippet: str = ""

    def to_dict(self):
        return asdict(self)

@dataclass
class Report:
    findings: list = field(default_factory=list)
    files_scanned: int = 0
    errors: list = field(default_factory=list)

    def add(self, finding: Finding):
        self.findings.append(finding)

    def to_dict(self):
        return {
            "files_scanned": self.files_scanned,
            "summary": {
                "critical": len([f for f in self.findings if f.severity == "critical"]),
                "high": len([f for f in self.findings if f.severity == "high"]),
                "medium": len([f for f in self.findings if f.severity == "medium"]),
                "low": len([f for f in self.findings if f.severity == "low"]),
            },
            "findings": [f.to_dict() for f in self.findings],
            "errors": self.errors,
        }


# =============================================================================
# Python Checks
# =============================================================================

def check_python_file(filepath: str, report: Report):
    """Run all Python checks on a single file."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
            lines = content.split("\n")
    except Exception as e:
        report.errors.append(f"Could not read {filepath}: {e}")
        return

    # Parse AST for structural checks
    try:
        tree = ast.parse(content, filename=filepath)
    except SyntaxError as e:
        report.add(Finding(
            severity="critical",
            category="correctness",
            title="Syntax Error",
            file=filepath,
            line=e.lineno or 0,
            message=f"Python syntax error: {e.msg}",
        ))
        return

    # Line-by-line pattern checks
    _check_python_patterns(filepath, lines, report)
    # AST-based checks
    _check_python_ast(filepath, tree, content, lines, report)


def _check_python_patterns(filepath: str, lines: list, report: Report):
    """Regex/pattern-based checks on Python files."""

    patterns = [
        # Security
        {
            "pattern": r"(?:password|secret|api_key|token)\s*=\s*['\"][^'\"]+['\"]",
            "severity": "critical",
            "category": "security",
            "title": "Hardcoded Secret",
            "message": "Potential hardcoded secret found. Use environment variables.",
            "exclude": r"(?:example|test|mock|fake|dummy|placeholder|xxx|your_)",
        },
        {
            "pattern": r"eval\s*\(",
            "severity": "critical",
            "category": "security",
            "title": "eval() Usage",
            "message": "eval() can execute arbitrary code. Use ast.literal_eval() or safer alternatives.",
        },
        {
            "pattern": r"exec\s*\(",
            "severity": "high",
            "category": "security",
            "title": "exec() Usage",
            "message": "exec() can execute arbitrary code. Ensure input is fully trusted and sanitized.",
        },
        {
            "pattern": r"pickle\.loads?\(",
            "severity": "high",
            "category": "security",
            "title": "Pickle Deserialization",
            "message": "pickle.load() can execute arbitrary code. Use JSON or a safe serialization format.",
        },
        {
            "pattern": r"subprocess\.(?:call|run|Popen)\(.*shell\s*=\s*True",
            "severity": "high",
            "category": "security",
            "title": "Shell Injection Risk",
            "message": "shell=True with user input enables command injection. Use shell=False with list args.",
        },
        # Correctness
        {
            "pattern": r"def\s+\w+\([^)]*=\s*(?:\[\]|\{\}|\bset\(\))",
            "severity": "high",
            "category": "correctness",
            "title": "Mutable Default Argument",
            "message": "Mutable default arguments are shared across calls. Use None and create inside function.",
        },
        {
            "pattern": r"except\s*:",
            "severity": "medium",
            "category": "correctness",
            "title": "Bare Except Clause",
            "message": "Bare except catches SystemExit and KeyboardInterrupt. Use 'except Exception:' at minimum.",
        },
        {
            "pattern": r"time\.sleep\(",
            "severity": "medium",
            "category": "performance",
            "title": "Blocking sleep()",
            "message": "time.sleep() blocks the thread. In async code, use asyncio.sleep() instead.",
        },
        {
            "pattern": r"requests\.(?:get|post|put|patch|delete)\(",
            "severity": "medium",
            "category": "performance",
            "title": "Synchronous HTTP in Potentially Async Context",
            "message": "requests library is synchronous. Consider httpx.AsyncClient for async FastAPI endpoints.",
        },
        # Performance
        {
            "pattern": r"\.all\(\)\s*$",
            "severity": "medium",
            "category": "performance",
            "title": "Unbounded Query (.all())",
            "message": "Loading all records without limit. Add pagination or limit clause.",
        },
        {
            "pattern": r"SELECT\s+\*\s+FROM",
            "severity": "low",
            "category": "performance",
            "title": "SELECT * Query",
            "message": "SELECT * loads all columns. Select only needed columns for better performance.",
        },
        # Error Handling
        {
            "pattern": r"except\s+\w+.*:\s*\n\s*pass",
            "severity": "high",
            "category": "correctness",
            "title": "Swallowed Exception",
            "message": "Exception caught and silently ignored. At minimum, log the error.",
        },
        # Async issues
        {
            "pattern": r"asyncio\.run\(",
            "severity": "medium",
            "category": "correctness",
            "title": "asyncio.run() Usage",
            "message": "asyncio.run() creates a new event loop. Don't use inside an existing async context (e.g., FastAPI).",
        },
    ]

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        # Skip comments
        if stripped.startswith("#"):
            continue
        for p in patterns:
            if re.search(p["pattern"], line, re.IGNORECASE):
                # Check exclusion pattern
                if "exclude" in p and re.search(p["exclude"], line, re.IGNORECASE):
                    continue
                report.add(Finding(
                    severity=p["severity"],
                    category=p["category"],
                    title=p["title"],
                    file=filepath,
                    line=i,
                    message=p["message"],
                    code_snippet=stripped[:200],
                ))


def _check_python_ast(filepath: str, tree: ast.Module, content: str, lines: list, report: Report):
    """AST-based structural checks."""

    for node in ast.walk(tree):
        # Check for async def without any await
        if isinstance(node, ast.AsyncFunctionDef):
            has_await = False
            for child in ast.walk(node):
                if isinstance(child, ast.Await):
                    has_await = True
                    break
            if not has_await:
                report.add(Finding(
                    severity="medium",
                    category="correctness",
                    title="Async Function Without Await",
                    file=filepath,
                    line=node.lineno,
                    message=f"async def {node.name}() contains no await. Consider making it synchronous or add awaited calls.",
                ))

        # Check for f-strings in logging calls (potential injection / perf issue)
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                if node.func.attr in ("debug", "info", "warning", "error", "critical"):
                    for arg in node.args:
                        if isinstance(arg, ast.JoinedStr):  # f-string
                            report.add(Finding(
                                severity="low",
                                category="performance",
                                title="F-string in Logging",
                                file=filepath,
                                line=node.lineno,
                                message="Use lazy formatting in logging (logger.info('msg %s', var)) instead of f-strings.",
                            ))


# =============================================================================
# TypeScript/JavaScript Checks
# =============================================================================

def check_ts_file(filepath: str, report: Report):
    """Run pattern-based checks on TypeScript/JavaScript files."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
            lines = content.split("\n")
    except Exception as e:
        report.errors.append(f"Could not read {filepath}: {e}")
        return

    patterns = [
        # Security
        {
            "pattern": r"dangerouslySetInnerHTML",
            "severity": "high",
            "category": "security",
            "title": "dangerouslySetInnerHTML Usage",
            "message": "Ensure content is sanitized with DOMPurify or similar before injection.",
        },
        {
            "pattern": r"innerHTML\s*=",
            "severity": "high",
            "category": "security",
            "title": "Direct innerHTML Assignment",
            "message": "innerHTML can execute scripts. Use textContent or sanitize with DOMPurify.",
        },
        {
            "pattern": r"localStorage\.setItem\([^,]*(?:token|password|secret|key)",
            "severity": "high",
            "category": "security",
            "title": "Sensitive Data in localStorage",
            "message": "Storing auth tokens in localStorage is vulnerable to XSS. Use httpOnly cookies.",
        },
        # Correctness
        {
            "pattern": r"==\s*(?!=)",
            "severity": "low",
            "category": "correctness",
            "title": "Loose Equality (==)",
            "message": "Use === for strict equality to avoid type coercion bugs.",
            "exclude": r"===|!==",
        },
        {
            "pattern": r"console\.log\(",
            "severity": "low",
            "category": "correctness",
            "title": "console.log in Code",
            "message": "Remove console.log before production or use a proper logging utility.",
        },
        {
            "pattern": r"\.catch\(\s*\(\s*\)\s*=>\s*\{\s*\}\s*\)",
            "severity": "high",
            "category": "correctness",
            "title": "Empty Catch Block",
            "message": "Swallowed promise error. At minimum log the error or show user feedback.",
        },
        {
            "pattern": r"catch\s*\(\s*\w*\s*\)\s*\{\s*\}",
            "severity": "high",
            "category": "correctness",
            "title": "Empty Catch Block",
            "message": "Swallowed error. At minimum log the error or handle the failure case.",
        },
        # TypeScript
        {
            "pattern": r":\s*any(?:\s|;|,|\)|\])",
            "severity": "medium",
            "category": "correctness",
            "title": "'any' Type Usage",
            "message": "Avoid 'any' type. Use 'unknown' with type guards or define proper types.",
        },
        {
            "pattern": r"as\s+any",
            "severity": "medium",
            "category": "correctness",
            "title": "Type Assertion to 'any'",
            "message": "Casting to 'any' bypasses type safety. Use proper type narrowing.",
        },
        {
            "pattern": r"!\.",
            "severity": "low",
            "category": "correctness",
            "title": "Non-null Assertion",
            "message": "Non-null assertion (!.) can cause runtime errors. Prefer optional chaining (?.) with null checks.",
        },
        # React
        {
            "pattern": r"useEffect\(\s*(?:async|\(\)\s*=>\s*\{[^}]*(?:await|\.then))",
            "severity": "medium",
            "category": "correctness",
            "title": "Async useEffect",
            "message": "useEffect cannot be async directly. Define async function inside and call it.",
        },
        {
            "pattern": r"useState\([^)]*\)\s*\n.*useState\([^)]*\)\s*\n.*useState\([^)]*\)\s*\n.*useState\([^)]*\)\s*\n.*useState",
            "severity": "low",
            "category": "architecture",
            "title": "Many useState Hooks",
            "message": "Consider useReducer for complex state or group related state into objects.",
        },
        # Performance
        {
            "pattern": r"import\s+(?:\*\s+as\s+)?_\s+from\s+['\"]lodash['\"]",
            "severity": "medium",
            "category": "performance",
            "title": "Full Lodash Import",
            "message": "Import specific functions: import debounce from 'lodash/debounce' to reduce bundle size.",
        },
        {
            "pattern": r"import\s+moment\s+from",
            "severity": "low",
            "category": "performance",
            "title": "Moment.js Usage",
            "message": "Moment.js is large and deprecated. Consider date-fns or dayjs.",
        },
    ]

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("/*"):
            continue
        for p in patterns:
            if re.search(p["pattern"], line):
                if "exclude" in p and re.search(p["exclude"], line):
                    continue
                report.add(Finding(
                    severity=p["severity"],
                    category=p["category"],
                    title=p["title"],
                    file=filepath,
                    line=i,
                    message=p["message"],
                    code_snippet=stripped[:200],
                ))


# =============================================================================
# Main
# =============================================================================

PYTHON_EXTENSIONS = {".py"}
TS_EXTENSIONS = {".ts", ".tsx", ".js", ".jsx"}
SKIP_DIRS = {"node_modules", ".git", "__pycache__", ".venv", "venv", "dist", "build", ".next"}


def scan_path(target: str, report: Report):
    """Scan a file or directory."""
    target_path = Path(target)

    if target_path.is_file():
        report.files_scanned = 1
        ext = target_path.suffix.lower()
        if ext in PYTHON_EXTENSIONS:
            check_python_file(str(target_path), report)
        elif ext in TS_EXTENSIONS:
            check_ts_file(str(target_path), report)
        else:
            report.errors.append(f"Unsupported file type: {ext}")
        return

    if target_path.is_dir():
        for root, dirs, files in os.walk(target_path):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for fname in files:
                fpath = os.path.join(root, fname)
                ext = Path(fname).suffix.lower()
                if ext in PYTHON_EXTENSIONS:
                    report.files_scanned += 1
                    check_python_file(fpath, report)
                elif ext in TS_EXTENSIONS:
                    report.files_scanned += 1
                    check_ts_file(fpath, report)
        return

    report.errors.append(f"Path not found: {target}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 check_code.py <file_or_directory> [--severity critical|high|medium|all]")
        sys.exit(1)

    target = sys.argv[1]
    severity_filter = "all"
    if "--severity" in sys.argv:
        idx = sys.argv.index("--severity")
        if idx + 1 < len(sys.argv):
            severity_filter = sys.argv[idx + 1]

    report = Report()
    scan_path(target, report)

    # Filter by severity
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    if severity_filter != "all" and severity_filter in severity_order:
        threshold = severity_order[severity_filter]
        report.findings = [f for f in report.findings if severity_order.get(f.severity, 3) <= threshold]

    # Sort by severity
    report.findings.sort(key=lambda f: severity_order.get(f.severity, 3))

    # Output
    result = report.to_dict()
    print(json.dumps(result, indent=2))

    # Exit code based on findings
    if result["summary"]["critical"] > 0:
        sys.exit(2)
    elif result["summary"]["high"] > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
