#!/usr/bin/env python3
"""
Perennia AI - Comprehensive Code Quality Audit System
Automated scanning to detect error handling gaps, anti-patterns, and quality issues

This script analyzes the entire codebase and generates an objective report
that developers cannot argue with - it's automated, consistent, and verifiable.

Usage:
    python audit_system.py --frontend ./frontend --backend ./backend --output report.md
"""

import os
import re
import json
import argparse
from pathlib import Path
from typing import List, Dict, Tuple, Set
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class Issue:
    """Represents a code quality issue"""
    severity: str  # 'critical', 'high', 'medium', 'low'
    category: str
    file_path: str
    line_number: int
    issue_type: str
    description: str
    code_snippet: str
    fix_suggestion: str

    def __str__(self):
        return f"[{self.severity.upper()}] {self.file_path}:{self.line_number} - {self.description}"


@dataclass
class FileReport:
    """Report for a single file"""
    file_path: str
    file_type: str  # 'frontend', 'backend'
    total_lines: int
    issues: List[Issue] = field(default_factory=list)
    score: float = 100.0

    @property
    def critical_count(self):
        return len([i for i in self.issues if i.severity == 'critical'])

    @property
    def high_count(self):
        return len([i for i in self.issues if i.severity == 'high'])

    @property
    def medium_count(self):
        return len([i for i in self.issues if i.severity == 'medium'])

    @property
    def low_count(self):
        return len([i for i in self.issues if i.severity == 'low'])


@dataclass
class AuditReport:
    """Complete audit report"""
    timestamp: str
    files_scanned: int
    frontend_files: List[FileReport] = field(default_factory=list)
    backend_files: List[FileReport] = field(default_factory=list)

    @property
    def total_issues(self):
        return sum(len(f.issues) for f in self.frontend_files + self.backend_files)

    @property
    def critical_issues(self):
        return sum(f.critical_count for f in self.frontend_files + self.backend_files)

    @property
    def high_issues(self):
        return sum(f.high_count for f in self.frontend_files + self.backend_files)

    @property
    def overall_score(self):
        if not (self.frontend_files + self.backend_files):
            return 0.0
        avg_score = sum(f.score for f in self.frontend_files + self.backend_files) / \
                    len(self.frontend_files + self.backend_files)
        return round(avg_score, 2)


# ============================================================================
# FRONTEND SCANNERS (React/JavaScript/TypeScript)
# ============================================================================

class FrontendScanner:
    """Scans frontend files for error handling issues"""

    SETTINGS_PAGE_PATTERNS = [
        'Settings.js', 'Settings.tsx',
        'settings.js', 'settings.tsx'
    ]

    def __init__(self, root_path: str):
        self.root_path = Path(root_path)

    def scan_file(self, file_path: Path) -> FileReport:
        """Scan a single frontend file"""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            lines = content.split('\n')

        report = FileReport(
            file_path=str(file_path.relative_to(self.root_path)),
            file_type='frontend',
            total_lines=len(lines)
        )

        # Run all checks
        report.issues.extend(self._check_error_handling_imports(content, lines, file_path))
        report.issues.extend(self._check_async_operations(content, lines, file_path))
        report.issues.extend(self._check_toast_usage(content, lines, file_path))
        report.issues.extend(self._check_loading_states(content, lines, file_path))
        report.issues.extend(self._check_try_catch_blocks(content, lines, file_path))
        report.issues.extend(self._check_validation(content, lines, file_path))
        report.issues.extend(self._check_deprecated_patterns(content, lines, file_path))

        # Calculate score
        report.score = self._calculate_score(report)

        return report

    def _check_error_handling_imports(self, content: str, lines: List[str], file_path: Path) -> List[Issue]:
        """Check if file imports error handling utilities"""
        issues = []

        # Skip if not a settings page
        if not self._is_settings_page(file_path):
            return issues

        required_imports = {
            'useAsyncOperation': r"import.*\buseAsyncOperation\b",
            'toast': r"import.*\btoast\b.*from.*['\"].*toast",
        }

        missing_imports = []
        for import_name, pattern in required_imports.items():
            if not re.search(pattern, content):
                missing_imports.append(import_name)

        if missing_imports:
            issues.append(Issue(
                severity='high',
                category='missing_imports',
                file_path=str(file_path.relative_to(self.root_path)),
                line_number=1,
                issue_type='Missing error handling imports',
                description=f'Missing required imports: {", ".join(missing_imports)}',
                code_snippet=lines[0] if lines else '',
                fix_suggestion=f'Add: import {{ {", ".join(missing_imports)} }} from appropriate paths'
            ))

        return issues

    def _check_async_operations(self, content: str, lines: List[str], file_path: Path) -> List[Issue]:
        """Check async operations for proper error handling"""
        issues = []

        # Find all async functions
        async_pattern = r'(async\s+(?:function\s+)?(?:\w+\s*)?\([^)]*\)\s*=>|async\s+function\s+\w+\s*\([^)]*\))'

        for match in re.finditer(async_pattern, content):
            line_num = content[:match.start()].count('\n') + 1

            # Get the function body (simplified - look ahead ~50 lines)
            start_pos = match.end()
            end_pos = min(start_pos + 2000, len(content))  # ~50 lines
            func_body = content[start_pos:end_pos]

            # Check if function has try-catch OR uses useAsyncOperation
            has_try_catch = re.search(r'\btry\s*{', func_body)

            # Check if this is inside a useAsyncOperation call
            before_func = content[max(0, match.start()-200):match.start()]
            uses_hook = re.search(r'useAsyncOperation\s*\(', before_func)

            if not has_try_catch and not uses_hook:
                # Check if function makes API calls
                makes_api_call = re.search(r'\bfetch\s*\(|\baxios\.|\.post\(|\.get\(|\.put\(|\.delete\(', func_body)

                if makes_api_call:
                    issues.append(Issue(
                        severity='critical',
                        category='error_handling',
                        file_path=str(file_path.relative_to(self.root_path)),
                        line_number=line_num,
                        issue_type='Unhandled async operation',
                        description='Async function makes API calls without try-catch or useAsyncOperation wrapper',
                        code_snippet=lines[line_num-1] if line_num <= len(lines) else '',
                        fix_suggestion='Wrap in try-catch or use useAsyncOperation hook'
                    ))

        return issues

    def _check_toast_usage(self, content: str, lines: List[str], file_path: Path) -> List[Issue]:
        """Check for proper toast notification usage"""
        issues = []

        # Check for deprecated alert() usage
        for i, line in enumerate(lines, 1):
            if re.search(r'\balert\s*\(', line):
                issues.append(Issue(
                    severity='high',
                    category='deprecated_pattern',
                    file_path=str(file_path.relative_to(self.root_path)),
                    line_number=i,
                    issue_type='Using deprecated alert()',
                    description='Using browser alert() instead of toast notifications',
                    code_snippet=line.strip(),
                    fix_suggestion='Replace alert() with toast.success() or toast.error()'
                ))

        # Check for custom showToast instead of standard toast
        for i, line in enumerate(lines, 1):
            if re.search(r'\bshowToast\s*\(', line) and not re.search(r'function\s+showToast', line):
                issues.append(Issue(
                    severity='medium',
                    category='inconsistent_pattern',
                    file_path=str(file_path.relative_to(self.root_path)),
                    line_number=i,
                    issue_type='Using custom showToast',
                    description='Using custom showToast instead of standard toast library',
                    code_snippet=line.strip(),
                    fix_suggestion='Replace showToast() with toast.success() or toast.error()'
                ))

        return issues

    def _check_loading_states(self, content: str, lines: List[str], file_path: Path) -> List[Issue]:
        """Check for proper loading state management"""
        issues = []

        # Find save/submit buttons
        button_pattern = r'<button[^>]*onClick\s*=\s*\{[^}]*\bsave|submit\b[^}]*\}'

        for match in re.finditer(button_pattern, content, re.IGNORECASE):
            line_num = content[:match.start()].count('\n') + 1
            button_code = match.group(0)

            # Check if button has disabled state tied to loading
            has_loading_disabled = re.search(r'disabled\s*=\s*\{[^}]*\bisLoading\b', button_code)

            # Check if button text changes based on loading
            has_loading_text = re.search(r'\{[^}]*\bisLoading\b.*\?', button_code)

            if not has_loading_disabled and not has_loading_text:
                issues.append(Issue(
                    severity='medium',
                    category='ux',
                    file_path=str(file_path.relative_to(self.root_path)),
                    line_number=line_num,
                    issue_type='Missing loading state',
                    description='Save/submit button does not show loading state',
                    code_snippet=lines[line_num-1] if line_num <= len(lines) else '',
                    fix_suggestion='Add disabled={isLoading} and conditional text: {isLoading ? "Saving..." : "Save"}'
                ))

        return issues

    def _check_try_catch_blocks(self, content: str, lines: List[str], file_path: Path) -> List[Issue]:
        """Check try-catch blocks for proper error handling"""
        issues = []

        # Find all try-catch blocks
        try_catch_pattern = r'try\s*\{([^}]*)\}\s*catch\s*\(([^)]*)\)\s*\{([^}]*)\}'

        for match in re.finditer(try_catch_pattern, content, re.DOTALL):
            line_num = content[:match.start()].count('\n') + 1
            catch_block = match.group(3)

            # Check for empty catch blocks
            if not catch_block.strip() or catch_block.strip() == '':
                # Only flag as issue if not using hooks that handle errors
                before_try = content[max(0, match.start()-300):match.start()]
                uses_hook = re.search(r'useAsyncOperation|useFormSubmit', before_try)

                if not uses_hook:
                    issues.append(Issue(
                        severity='high',
                        category='error_handling',
                        file_path=str(file_path.relative_to(self.root_path)),
                        line_number=line_num,
                        issue_type='Empty catch block',
                        description='Catch block is empty - errors will be silently swallowed',
                        code_snippet=lines[line_num-1] if line_num <= len(lines) else '',
                        fix_suggestion='Add error handling: toast.error(error.message) or logger.error(error)'
                    ))

            # Check for generic error messages
            if re.search(r'["\']Error["\']|["\']Failed["\']|["\']Something went wrong["\']', catch_block):
                issues.append(Issue(
                    severity='medium',
                    category='error_handling',
                    file_path=str(file_path.relative_to(self.root_path)),
                    line_number=line_num,
                    issue_type='Generic error message',
                    description='Using generic error message instead of specific error details',
                    code_snippet=lines[line_num-1] if line_num <= len(lines) else '',
                    fix_suggestion='Use error.message or error.getUserMessage() for specific errors'
                ))

        return issues

    def _check_validation(self, content: str, lines: List[str], file_path: Path) -> List[Issue]:
        """Check for client-side validation"""
        issues = []

        # Skip if not a settings page
        if not self._is_settings_page(file_path):
            return issues

        # Look for save/submit functions
        save_pattern = r'const\s+(?:handleSave|handleSubmit|onSave|onSubmit)\s*='

        for match in re.finditer(save_pattern, content):
            line_num = content[:match.start()].count('\n') + 1

            # Get function body
            start = match.end()
            end = min(start + 1000, len(content))
            func_body = content[start:end]

            # Check if validation exists before API call
            has_validation = re.search(r'\bvalidate|isValid|checkValid', func_body, re.IGNORECASE)
            makes_api_call = re.search(r'\bfetch\(|\baxios\.|api\.|\.post\(|\.put\(', func_body)

            if makes_api_call and not has_validation:
                issues.append(Issue(
                    severity='medium',
                    category='validation',
                    file_path=str(file_path.relative_to(self.root_path)),
                    line_number=line_num,
                    issue_type='Missing client-side validation',
                    description='Save function does not validate data before API call',
                    code_snippet=lines[line_num-1] if line_num <= len(lines) else '',
                    fix_suggestion='Add validation check before API call to catch errors early'
                ))

        return issues

    def _check_deprecated_patterns(self, content: str, lines: List[str], file_path: Path) -> List[Issue]:
        """Check for deprecated patterns"""
        issues = []

        deprecated_patterns = {
            r'\.then\([^)]*\)\.catch\([^)]*\)': {
                'name': 'Promise chains',
                'severity': 'low',
                'suggestion': 'Use async/await with try-catch for better readability'
            },
            r'console\.log\s*\([^)]*error': {
                'name': 'console.log for errors',
                'severity': 'low',
                'suggestion': 'Use logger.error() or proper error tracking'
            },
            r'setState\([^)]*\)\s*;?\s*api\.|fetch\(': {
                'name': 'setState before async call',
                'severity': 'medium',
                'suggestion': 'Use useAsyncOperation hook to handle loading state automatically'
            }
        }

        for pattern, info in deprecated_patterns.items():
            for match in re.finditer(pattern, content):
                line_num = content[:match.start()].count('\n') + 1
                issues.append(Issue(
                    severity=info['severity'],
                    category='deprecated_pattern',
                    file_path=str(file_path.relative_to(self.root_path)),
                    line_number=line_num,
                    issue_type=f'Deprecated: {info["name"]}',
                    description=f'Using deprecated pattern: {info["name"]}',
                    code_snippet=lines[line_num-1] if line_num <= len(lines) else '',
                    fix_suggestion=info['suggestion']
                ))

        return issues

    def _is_settings_page(self, file_path: Path) -> bool:
        """Check if file is a settings page"""
        return any(pattern.lower() in file_path.name.lower() for pattern in self.SETTINGS_PAGE_PATTERNS)

    def _calculate_score(self, report: FileReport) -> float:
        """Calculate quality score for a file (0-100)"""
        score = 100.0

        # Deduct points based on severity
        score -= report.critical_count * 20
        score -= report.high_count * 10
        score -= report.medium_count * 5
        score -= report.low_count * 2

        return max(0.0, score)


# ============================================================================
# BACKEND SCANNERS (Python/FastAPI)
# ============================================================================

class BackendScanner:
    """Scans backend files for error handling issues"""

    def __init__(self, root_path: str):
        self.root_path = Path(root_path)

    def scan_file(self, file_path: Path) -> FileReport:
        """Scan a single backend file"""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            lines = content.split('\n')

        report = FileReport(
            file_path=str(file_path.relative_to(self.root_path)),
            file_type='backend',
            total_lines=len(lines)
        )

        # Run all checks
        report.issues.extend(self._check_exception_handling(content, lines, file_path))
        report.issues.extend(self._check_endpoint_patterns(content, lines, file_path))
        report.issues.extend(self._check_database_transactions(content, lines, file_path))
        report.issues.extend(self._check_validation(content, lines, file_path))
        report.issues.extend(self._check_logging(content, lines, file_path))
        report.issues.extend(self._check_response_format(content, lines, file_path))

        # Calculate score
        report.score = self._calculate_score(report)

        return report

    def _check_exception_handling(self, content: str, lines: List[str], file_path: Path) -> List[Issue]:
        """Check for proper exception handling"""
        issues = []

        # Find all API endpoints
        endpoint_pattern = r'@\w+\.(get|post|put|delete|patch)\s*\([^)]*\)\s*(?:async\s+)?def\s+(\w+)'

        for match in re.finditer(endpoint_pattern, content):
            line_num = content[:match.start()].count('\n') + 1
            endpoint_name = match.group(2)

            # Get function body (simplified - look ahead)
            start = match.end()
            # Find the next function definition or end of file
            next_def = re.search(r'\n(?:async\s+)?def\s+\w+', content[start:])
            end = start + next_def.start() if next_def else len(content)
            func_body = content[start:end]

            # Check for try-except
            has_try_except = re.search(r'\btry\s*:', func_body)

            if not has_try_except:
                issues.append(Issue(
                    severity='critical',
                    category='error_handling',
                    file_path=str(file_path.relative_to(self.root_path)),
                    line_number=line_num,
                    issue_type='Missing exception handling',
                    description=f'Endpoint {endpoint_name} has no try-except block',
                    code_snippet=lines[line_num-1] if line_num <= len(lines) else '',
                    fix_suggestion='Wrap endpoint logic in try-except with proper error handling'
                ))
            else:
                # Check for bare except
                if re.search(r'except\s*:', func_body):
                    issues.append(Issue(
                        severity='high',
                        category='error_handling',
                        file_path=str(file_path.relative_to(self.root_path)),
                        line_number=line_num,
                        issue_type='Bare except clause',
                        description='Using bare except: - should catch specific exceptions',
                        code_snippet=lines[line_num-1] if line_num <= len(lines) else '',
                        fix_suggestion='Catch specific exceptions (HTTPException, ValidationException, etc.)'
                    ))

        return issues

    def _check_endpoint_patterns(self, content: str, lines: List[str], file_path: Path) -> List[Issue]:
        """Check endpoints follow proper patterns"""
        issues = []

        # Check if endpoints import error utilities
        if '@router.' in content or '@app.' in content:
            has_error_imports = re.search(r'from.*error|from.*exception', content, re.IGNORECASE)

            if not has_error_imports:
                issues.append(Issue(
                    severity='high',
                    category='missing_imports',
                    file_path=str(file_path.relative_to(self.root_path)),
                    line_number=1,
                    issue_type='Missing error handling imports',
                    description='File has endpoints but does not import error handling utilities',
                    code_snippet='',
                    fix_suggestion='Import: ValidationException, PermissionException, DatabaseException, etc.'
                ))

        return issues

    def _check_database_transactions(self, content: str, lines: List[str], file_path: Path) -> List[Issue]:
        """Check database operations use transactions"""
        issues = []

        # Find database commit calls
        commit_pattern = r'db\.commit\(\)'

        for match in re.finditer(commit_pattern, content):
            line_num = content[:match.start()].count('\n') + 1

            # Check if there's a corresponding rollback in except block
            # Look backwards for try statement
            before = content[max(0, match.start()-500):match.start()]
            has_try = re.search(r'\btry\s*:', before)

            if has_try:
                # Look forward for except with rollback
                after = content[match.end():min(match.end()+500, len(content))]
                has_rollback = re.search(r'except.*db\.rollback\(\)', after, re.DOTALL)

                if not has_rollback:
                    issues.append(Issue(
                        severity='high',
                        category='database',
                        file_path=str(file_path.relative_to(self.root_path)),
                        line_number=line_num,
                        issue_type='Missing rollback',
                        description='Database commit without rollback in exception handler',
                        code_snippet=lines[line_num-1] if line_num <= len(lines) else '',
                        fix_suggestion='Add db.rollback() in except block'
                    ))

        return issues

    def _check_validation(self, content: str, lines: List[str], file_path: Path) -> List[Issue]:
        """Check for Pydantic validation"""
        issues = []

        # Find POST/PUT endpoints
        mutating_endpoint_pattern = r'@\w+\.(post|put|patch)\s*\([^)]*\)\s*(?:async\s+)?def\s+(\w+)\s*\([^)]*\)'

        for match in re.finditer(mutating_endpoint_pattern, content):
            line_num = content[:match.start()].count('\n') + 1
            endpoint_name = match.group(2)
            params = match.group(0)

            # Check if endpoint has Pydantic model parameter
            has_pydantic_model = re.search(r':\s*\w+(?:Settings|Input|Request|Model)', params)

            if not has_pydantic_model:
                issues.append(Issue(
                    severity='medium',
                    category='validation',
                    file_path=str(file_path.relative_to(self.root_path)),
                    line_number=line_num,
                    issue_type='Missing Pydantic validation',
                    description=f'POST/PUT endpoint {endpoint_name} does not use Pydantic model for validation',
                    code_snippet=lines[line_num-1] if line_num <= len(lines) else '',
                    fix_suggestion='Add Pydantic BaseModel for request validation'
                ))

        return issues

    def _check_logging(self, content: str, lines: List[str], file_path: Path) -> List[Issue]:
        """Check for proper logging"""
        issues = []

        # Check if file with endpoints has logging
        if '@router.' in content or '@app.' in content:
            has_logger = re.search(r'logger\s*=|import.*logging', content)

            if not has_logger:
                issues.append(Issue(
                    severity='medium',
                    category='logging',
                    file_path=str(file_path.relative_to(self.root_path)),
                    line_number=1,
                    issue_type='Missing logging',
                    description='File has endpoints but no logging configured',
                    code_snippet='',
                    fix_suggestion='Add: logger = logging.getLogger(__name__)'
                ))

        return issues

    def _check_response_format(self, content: str, lines: List[str], file_path: Path) -> List[Issue]:
        """Check endpoints return standardized responses"""
        issues = []

        # Find return statements in endpoints
        endpoint_pattern = r'@\w+\.(get|post|put|delete)\s*\([^)]*\)\s*(?:async\s+)?def\s+(\w+).*?(?=\n(?:async\s+)?def\s+|\Z)'

        for match in re.finditer(endpoint_pattern, content, re.DOTALL):
            func_body = match.group(0)
            line_num = content[:match.start()].count('\n') + 1

            # Check for return statements
            returns = re.finditer(r'\breturn\s+(.+)', func_body)

            for ret_match in returns:
                return_value = ret_match.group(1).strip()

                # Check if using standardized response functions
                uses_standard_response = re.search(
                    r'success_response\(|error_response\(|created_response\(',
                    return_value
                )

                # Check if returning raw dict
                returns_raw_dict = return_value.startswith('{') or return_value.startswith('dict(')

                if returns_raw_dict and not uses_standard_response:
                    ret_line_num = content[:match.start() + ret_match.start()].count('\n') + 1
                    issues.append(Issue(
                        severity='low',
                        category='response_format',
                        file_path=str(file_path.relative_to(self.root_path)),
                        line_number=ret_line_num,
                        issue_type='Non-standard response format',
                        description='Endpoint returns raw dict instead of using success_response()',
                        code_snippet=lines[ret_line_num-1] if ret_line_num <= len(lines) else '',
                        fix_suggestion='Use success_response() or created_response() for consistency'
                    ))

        return issues

    def _calculate_score(self, report: FileReport) -> float:
        """Calculate quality score for a file (0-100)"""
        score = 100.0

        score -= report.critical_count * 20
        score -= report.high_count * 10
        score -= report.medium_count * 5
        score -= report.low_count * 2

        return max(0.0, score)


# ============================================================================
# REPORT GENERATOR
# ============================================================================

class ReportGenerator:
    """Generates formatted audit reports"""

    @staticmethod
    def generate_markdown(report: AuditReport, output_path: str):
        """Generate detailed markdown report"""

        lines = [
            "# Perennia AI - Comprehensive Code Quality Audit Report",
            f"**Generated**: {report.timestamp}",
            f"**Files Scanned**: {report.files_scanned}",
            "",
            "---",
            "",
            "## Executive Summary",
            "",
            f"**Overall Score**: {report.overall_score}/100",
            "",
            "| Metric | Count |",
            "|--------|-------|",
            f"| Total Issues | {report.total_issues} |",
            f"| Critical | {report.critical_issues} |",
            f"| High | {report.high_issues} |",
            f"| Medium | {sum(f.medium_count for f in report.frontend_files + report.backend_files)} |",
            f"| Low | {sum(f.low_count for f in report.frontend_files + report.backend_files)} |",
            "",
        ]

        # Grade
        grade = ReportGenerator._calculate_grade(report.overall_score)
        lines.extend([
            f"**Grade**: {grade}",
            "",
            ReportGenerator._get_grade_description(grade),
            "",
            "---",
            ""
        ])

        # Critical Issues First
        if report.critical_issues > 0:
            lines.extend([
                "## CRITICAL ISSUES (Must Fix Immediately)",
                "",
                "These issues will cause production failures and must be fixed before deployment:",
                ""
            ])

            for file_report in sorted(
                report.frontend_files + report.backend_files,
                key=lambda x: x.critical_count,
                reverse=True
            ):
                if file_report.critical_count > 0:
                    lines.append(f"### {file_report.file_path} ({file_report.critical_count} critical)")
                    lines.append("")

                    for issue in [i for i in file_report.issues if i.severity == 'critical']:
                        lines.extend([
                            f"**Line {issue.line_number}**: {issue.description}",
                            f"```",
                            f"{issue.code_snippet}",
                            f"```",
                            f"**Fix**: {issue.fix_suggestion}",
                            ""
                        ])

            lines.append("---")
            lines.append("")

        # Frontend Files
        if report.frontend_files:
            lines.extend([
                "## Frontend Analysis",
                "",
                f"**Files Scanned**: {len(report.frontend_files)}",
                f"**Average Score**: {sum(f.score for f in report.frontend_files) / len(report.frontend_files):.2f}/100",
                ""
            ])

            # File-by-file breakdown
            for file_report in sorted(report.frontend_files, key=lambda x: x.score):
                if file_report.issues:
                    lines.extend([
                        f"### {file_report.file_path}",
                        f"**Score**: {file_report.score}/100 | "
                        f"Critical: {file_report.critical_count} | "
                        f"High: {file_report.high_count} | "
                        f"Medium: {file_report.medium_count} | "
                        f"Low: {file_report.low_count}",
                        ""
                    ])

                    for issue in file_report.issues:
                        severity_marker = {
                            'critical': '[CRITICAL]',
                            'high': '[HIGH]',
                            'medium': '[MEDIUM]',
                            'low': '[LOW]'
                        }[issue.severity]

                        lines.extend([
                            f"{severity_marker} **Line {issue.line_number}**: {issue.description}",
                            f"- **Fix**: {issue.fix_suggestion}",
                            ""
                        ])

                    lines.append("")

        # Backend Files
        if report.backend_files:
            lines.extend([
                "---",
                "",
                "## Backend Analysis",
                "",
                f"**Files Scanned**: {len(report.backend_files)}",
                f"**Average Score**: {sum(f.score for f in report.backend_files) / len(report.backend_files):.2f}/100",
                ""
            ])

            for file_report in sorted(report.backend_files, key=lambda x: x.score):
                if file_report.issues:
                    lines.extend([
                        f"### {file_report.file_path}",
                        f"**Score**: {file_report.score}/100 | "
                        f"Critical: {file_report.critical_count} | "
                        f"High: {file_report.high_count} | "
                        f"Medium: {file_report.medium_count} | "
                        f"Low: {file_report.low_count}",
                        ""
                    ])

                    for issue in file_report.issues:
                        severity_marker = {
                            'critical': '[CRITICAL]',
                            'high': '[HIGH]',
                            'medium': '[MEDIUM]',
                            'low': '[LOW]'
                        }[issue.severity]

                        lines.extend([
                            f"{severity_marker} **Line {issue.line_number}**: {issue.description}",
                            f"- **Fix**: {issue.fix_suggestion}",
                            ""
                        ])

        # Summary and Recommendations
        lines.extend([
            "---",
            "",
            "## Recommendations",
            ""
        ])

        if report.critical_issues > 0:
            lines.extend([
                f"### NOT READY FOR PRODUCTION",
                "",
                f"**{report.critical_issues} critical issues** must be fixed before deployment.",
                ""
            ])
        elif report.overall_score >= 80:
            lines.extend([
                "### READY FOR PRODUCTION",
                "",
                "Code quality meets standards. Minor improvements recommended but not blocking.",
                ""
            ])
        else:
            lines.extend([
                "### NEEDS IMPROVEMENT",
                "",
                f"Overall score of {report.overall_score}/100 is below production standard (80+).",
                "Address high-priority issues before deployment.",
                ""
            ])

        # Write to file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

        print(f"Report generated: {output_path}")

    @staticmethod
    def _calculate_grade(score: float) -> str:
        """Calculate letter grade from score"""
        if score >= 90:
            return "A (Excellent)"
        elif score >= 80:
            return "B (Good)"
        elif score >= 70:
            return "C (Acceptable)"
        elif score >= 60:
            return "D (Needs Work)"
        else:
            return "F (Failing)"

    @staticmethod
    def _get_grade_description(grade: str) -> str:
        """Get description for grade"""
        descriptions = {
            "A (Excellent)": "**Production Ready** - Code quality exceeds standards. Deploy with confidence.",
            "B (Good)": "**Production Ready** - Code quality meets standards. Minor improvements recommended.",
            "C (Acceptable)": "**Conditional** - Code quality is acceptable but should be improved soon.",
            "D (Needs Work)": "**Not Recommended** - Significant quality issues. Refactor before production.",
            "F (Failing)": "**NOT READY** - Critical quality issues. Do not deploy."
        }
        return descriptions.get(grade, "")


# ============================================================================
# MAIN AUDIT SYSTEM
# ============================================================================

class AuditSystem:
    """Main audit orchestrator"""

    def __init__(self, frontend_path: str = None, backend_path: str = None):
        self.frontend_path = Path(frontend_path) if frontend_path else None
        self.backend_path = Path(backend_path) if backend_path else None

        self.frontend_scanner = FrontendScanner(frontend_path) if frontend_path else None
        self.backend_scanner = BackendScanner(backend_path) if backend_path else None

    def run_audit(self) -> AuditReport:
        """Run complete audit"""
        report = AuditReport(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            files_scanned=0
        )

        # Scan frontend
        if self.frontend_path and self.frontend_scanner:
            print(f"Scanning frontend: {self.frontend_path}")
            for file_path in self._get_frontend_files():
                print(f"  Checking {file_path.relative_to(self.frontend_path)}...")
                file_report = self.frontend_scanner.scan_file(file_path)
                if file_report.issues:  # Only include files with issues
                    report.frontend_files.append(file_report)
                report.files_scanned += 1

        # Scan backend
        if self.backend_path and self.backend_scanner:
            print(f"Scanning backend: {self.backend_path}")
            for file_path in self._get_backend_files():
                print(f"  Checking {file_path.relative_to(self.backend_path)}...")
                file_report = self.backend_scanner.scan_file(file_path)
                if file_report.issues:  # Only include files with issues
                    report.backend_files.append(file_report)
                report.files_scanned += 1

        return report

    def _get_frontend_files(self) -> List[Path]:
        """Get all frontend JavaScript/TypeScript files"""
        files = []
        if self.frontend_path:
            for ext in ['**/*.js', '**/*.jsx', '**/*.ts', '**/*.tsx']:
                files.extend(self.frontend_path.glob(ext))

        # Exclude node_modules, build, dist
        files = [
            f for f in files
            if 'node_modules' not in str(f)
            and 'build' not in str(f)
            and 'dist' not in str(f)
            and '.test.' not in str(f)
            and '.spec.' not in str(f)
        ]

        return files

    def _get_backend_files(self) -> List[Path]:
        """Get all backend Python files"""
        files = []
        if self.backend_path:
            files = list(self.backend_path.glob('**/*.py'))

        # Exclude tests, migrations, __pycache__
        files = [
            f for f in files
            if '__pycache__' not in str(f)
            and 'test_' not in f.name
            and 'migrations' not in str(f)
            and 'venv' not in str(f)
        ]

        return files


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Automated code quality audit for Perennia AI'
    )
    parser.add_argument(
        '--frontend',
        help='Path to frontend directory',
        required=False
    )
    parser.add_argument(
        '--backend',
        help='Path to backend directory',
        required=False
    )
    parser.add_argument(
        '--output',
        default='audit_report.md',
        help='Output file for report (default: audit_report.md)'
    )

    args = parser.parse_args()

    if not args.frontend and not args.backend:
        print("Error: Must specify --frontend and/or --backend")
        return 1

    print("Starting comprehensive code audit...")
    print()

    # Run audit
    audit_system = AuditSystem(
        frontend_path=args.frontend,
        backend_path=args.backend
    )

    report = audit_system.run_audit()

    # Generate report
    print()
    print("Generating report...")
    ReportGenerator.generate_markdown(report, args.output)

    # Print summary
    print()
    print("=" * 80)
    print("AUDIT SUMMARY")
    print("=" * 80)
    print(f"Overall Score: {report.overall_score}/100")
    print(f"Total Issues: {report.total_issues}")
    print(f"  Critical: {report.critical_issues}")
    print(f"  High: {report.high_issues}")
    print(f"  Medium: {sum(f.medium_count for f in report.frontend_files + report.backend_files)}")
    print(f"  Low: {sum(f.low_count for f in report.frontend_files + report.backend_files)}")
    print()

    if report.critical_issues > 0:
        print("NOT READY FOR PRODUCTION")
        print(f"   {report.critical_issues} critical issues must be fixed")
        return 1
    elif report.overall_score >= 80:
        print("READY FOR PRODUCTION")
        return 0
    else:
        print("NEEDS IMPROVEMENT")
        print(f"   Score of {report.overall_score}/100 is below standard (80+)")
        return 1


if __name__ == '__main__':
    exit(main())
