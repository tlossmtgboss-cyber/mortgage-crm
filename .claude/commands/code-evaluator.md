---
name: code-evaluator
description: >
  Comprehensive code evaluation and bug detection skill. Use this skill whenever the user asks to
  review code, check for bugs, audit code quality, evaluate a codebase, find issues, or verify
  correctness. Also trigger when the user says things like "does this look right", "check my code",
  "find bugs", "code review", "what's wrong with this", "audit this", "evaluate the code",
  "make sure everything is correct", or any variation of verifying code quality. This skill covers
  Python (FastAPI, async, SQLAlchemy), TypeScript/React, API endpoints, database queries, security,
  performance, and architecture patterns. Use it even for single files or small snippets — every
  review benefits from a systematic checklist approach.
---

# Code Evaluator

A systematic code evaluation and bug detection skill that checks code for correctness, security
vulnerabilities, performance issues, and adherence to best practices.

## Overview

This skill performs multi-dimensional code evaluation across these categories:

| Category | What It Catches |
|----------|----------------|
| **Correctness** | Logic errors, off-by-ones, null/undefined handling, race conditions, type mismatches |
| **Security** | Injection, auth bypasses, data exposure, CSRF, insecure defaults, secrets in code |
| **Performance** | N+1 queries, missing indexes, memory leaks, unnecessary re-renders, blocking calls |
| **Error Handling** | Swallowed exceptions, missing try/catch, unclear error messages, unhandled edge cases |
| **Architecture** | Coupling, circular deps, separation of concerns, DRY violations, API contract issues |
| **Async/Concurrency** | Unawaited promises, deadlocks, race conditions, connection pool exhaustion |
| **Type Safety** | Missing types, unsafe casts, `any` abuse, incorrect generics |

## Workflow

### Step 1: Scope the Review

Determine what's being evaluated:
- **Single file/snippet**: Inline deep review
- **Multiple files**: Cross-file dependency and integration analysis
- **Full feature/module**: Architecture + integration + edge case review
- **PR/diff**: Focus on changed lines with context-aware review

Ask the user if the scope is unclear. If they say "check everything," focus on the most critical
paths first (auth, data mutations, API endpoints, payment logic).

### Step 2: Read the Code

Read ALL files under review before writing any findings. Do not start reporting issues mid-read.
Build a mental model of:
- Data flow (inputs → transformations → outputs)
- Control flow (branching, loops, early returns)
- Error propagation (where errors originate, how they bubble up)
- State management (what's mutable, what's shared)
- External dependencies (APIs, DBs, file system, env vars)

### Step 3: Run Automated Checks (when applicable)

If the code is available on disk, run the automated checker script:

```bash
python3 .claude/commands/code-evaluator/scripts/check_code.py <file_or_directory>
```

This catches low-hanging fruit: syntax issues, import problems, common anti-patterns.
Use script results to supplement (not replace) manual review.

### Step 4: Evaluate Against Checklists

Apply the relevant language/framework checklists. Read the appropriate reference files:

- **Python / FastAPI**: Read `.claude/commands/code-evaluator/references/python-checklist.md`
- **TypeScript / React**: Read `.claude/commands/code-evaluator/references/typescript-checklist.md`
- **Cross-cutting concerns** (security, DB, API design): Read `.claude/commands/code-evaluator/references/cross-cutting-checklist.md`

### Step 5: Report Findings

Structure findings by severity:

#### Severity Levels

| Level | Label | Meaning |
|-------|-------|---------|
| 🔴 | **Critical** | Will cause bugs in production, security vulnerability, data loss risk |
| 🟠 | **High** | Likely to cause issues under load or edge cases, potential data integrity issues |
| 🟡 | **Medium** | Code smell, maintainability concern, performance drag |
| 🔵 | **Low** | Style, naming, minor improvement opportunities |

#### Report Format

For each finding, provide:

```
🔴 [CRITICAL] Short title
File: path/to/file.py, Line: 42
Issue: What's wrong and WHY it's a problem
Evidence: The specific code that exhibits the issue
Fix: Concrete code change (not vague advice)
```

Always provide the **fix**, not just the diagnosis. Production-ready patches, not suggestions.

### Step 6: Summary

End every review with:

1. **Verdict**: PASS / PASS WITH WARNINGS / NEEDS FIXES / CRITICAL ISSUES
2. **Stats**: X critical, Y high, Z medium, W low findings
3. **Top 3 priorities**: The most important things to fix first
4. **Positive observations**: What's done well (important for morale and context)

## Special Review Modes

### Quick Check (for small snippets)
Skip the full workflow. Read → Evaluate → Report inline. No severity table needed for < 3 findings.

### Security Audit
Focus exclusively on security concerns. Read `.claude/commands/code-evaluator/references/cross-cutting-checklist.md` security
section. Check OWASP Top 10 patterns, auth flows, input validation, data exposure.

### Pre-Deploy Review
Highest scrutiny. Check all categories. Verify env vars, migration safety, rollback plan,
feature flags, error monitoring. Flag anything that could cause an outage.

## Key Principles

1. **No false confidence**: If you're unsure whether something is a bug, say so. "This *may* be
   intentional, but if not, it would cause X" is better than silence.
2. **Context matters**: A missing null check in a payment flow is critical. In a debug logger,
   it's low. Weight findings by where they sit in the codebase.
3. **Fix, don't lecture**: Provide the corrected code. The user knows theory — they need the patch.
4. **Check the happy path AND the sad path**: Most bugs live in error handling, edge cases, and
   cleanup logic.
5. **Read between the lines**: Missing code is often more dangerous than wrong code. Look for
   absent validation, missing auth checks, unhandled states.
