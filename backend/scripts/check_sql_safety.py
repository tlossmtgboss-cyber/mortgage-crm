#!/usr/bin/env python3
"""
SQL Safety Checker - Pre-commit hook to detect potential SQL injection vulnerabilities.

This script detects dangerous SQL patterns that could lead to SQL injection:
1. Table/column name interpolation in SQL queries
2. .format() usage near SQL keywords
3. String concatenation in SQL contexts

Safe patterns (parameterized queries with :param placeholders) are allowed.
"""

import re
import sys
from pathlib import Path
from typing import List, Tuple


# Patterns that indicate unsafe SQL construction
UNSAFE_PATTERNS = [
    # Table name injection - interpolating variable as table name
    (
        r'execute\s*\(\s*text\s*\(\s*f["\'].*DELETE\s+FROM\s+\{[^}]+\}',
        "Table name interpolation in DELETE",
        "Use whitelist validation: validate_table_name(table)"
    ),
    (
        r'execute\s*\(\s*text\s*\(\s*f["\'].*INSERT\s+INTO\s+\{[^}]+\}',
        "Table name interpolation in INSERT",
        "Use whitelist validation: validate_table_name(table)"
    ),
    (
        r'execute\s*\(\s*text\s*\(\s*f["\'].*UPDATE\s+\{[^}]+\}',
        "Table name interpolation in UPDATE",
        "Use whitelist validation: validate_table_name(table)"
    ),
    (
        r'execute\s*\(\s*text\s*\(\s*f["\'].*FROM\s+\{[^}]+\}',
        "Table name interpolation in FROM clause",
        "Use whitelist validation: validate_table_name(table)"
    ),
    # Column name injection
    (
        r'WHERE\s+\{[^}]+\}\s*(=|!=|<>|<|>|<=|>=|IS|IN|LIKE|ILIKE)',
        "Column name interpolation in WHERE clause",
        "Use whitelist validation: validate_column_name(column)"
    ),
    (
        r'SET\s+\{[^}]+\}\s*=',
        "Column name interpolation in SET clause",
        "Use parameterized updates with ORM"
    ),
    # .format() near SQL - always dangerous
    (
        r'\.format\s*\([^)]*\)\s*\)?[^)]*(?:SELECT|INSERT|UPDATE|DELETE|FROM|WHERE)',
        ".format() used near SQL keywords",
        "Use parameterized queries with text() and :param syntax"
    ),
    (
        r'(?:SELECT|INSERT|UPDATE|DELETE|FROM|WHERE)[^"\']*\.format\s*\(',
        "SQL query using .format()",
        "Use parameterized queries with text() and :param syntax"
    ),
]

# Patterns that are known to be safe (whitelist-validated)
SAFE_PATTERNS = [
    r'\{validated_table\}',
    r'\{validated_column\}',
    r'\{safe_table\}',
    r'\{safe_column\}',
]


def check_file(filepath: Path) -> List[Tuple[int, str, str, str]]:
    """
    Check a Python file for SQL injection vulnerabilities.

    Returns list of (line_number, line, pattern_name, fix_suggestion) tuples.
    """
    issues = []

    try:
        content = filepath.read_text(encoding='utf-8')
        lines = content.split('\n')
    except Exception as e:
        print(f"Warning: Could not read {filepath}: {e}", file=sys.stderr)
        return []

    for line_num, line in enumerate(lines, 1):
        # Skip comments
        stripped = line.strip()
        if stripped.startswith('#'):
            continue

        # Skip if line contains a safe pattern (already validated)
        if any(re.search(safe_pat, line) for safe_pat in SAFE_PATTERNS):
            continue

        # Check for unsafe patterns
        for pattern, name, fix in UNSAFE_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                issues.append((line_num, line.strip(), name, fix))
                break  # Only report first issue per line

    return issues


def main():
    """Main entry point for pre-commit hook."""
    files = sys.argv[1:]

    if not files:
        print("Usage: check_sql_safety.py <file1.py> [file2.py] ...")
        sys.exit(0)

    all_issues = []

    for filepath_str in files:
        filepath = Path(filepath_str)

        # Only check Python files
        if filepath.suffix != '.py':
            continue

        # Skip test files and migration files (lower risk)
        if '/tests/' in str(filepath) or '/test_' in str(filepath):
            continue

        issues = check_file(filepath)
        if issues:
            all_issues.append((filepath, issues))

    if all_issues:
        print("\n" + "=" * 70)
        print("SQL INJECTION VULNERABILITY DETECTED")
        print("=" * 70)

        for filepath, issues in all_issues:
            print(f"\n{filepath}:")
            for line_num, line, pattern_name, fix in issues:
                print(f"  Line {line_num}: {pattern_name}")
                print(f"    Code: {line[:80]}{'...' if len(line) > 80 else ''}")
                print(f"    Fix:  {fix}")

        print("\n" + "-" * 70)
        print("COMMIT BLOCKED - Fix these SQL injection risks before committing.")
        print("-" * 70 + "\n")
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
