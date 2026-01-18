#!/usr/bin/env python3
"""
Analyze loan ID mismatches between Smart Docs and PURL system.
Uses raw SQL to avoid ORM schema mismatch issues.
"""

import os
import sys
import sqlite3

# Get database path
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mortgage_crm.db")

if not os.path.exists(DB_PATH):
    print(f"Database not found at: {DB_PATH}")
    sys.exit(1)

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

print("=" * 60)
print("LOAN ID MISMATCH ANALYSIS")
print("=" * 60)

# Check if tables exist
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='smart_document_requests'")
has_requests = cursor.fetchone()

cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='purl_loans'")
has_purl = cursor.fetchone()

if not has_requests:
    print("\n[!] smart_document_requests table not found")
    conn.close()
    sys.exit(1)

if not has_purl:
    print("\n[!] purl_loans table not found")
    conn.close()
    sys.exit(1)

# Get counts
cursor.execute("SELECT COUNT(*) FROM smart_document_requests WHERE is_active = 1")
total_requests = cursor.fetchone()[0]

cursor.execute("SELECT COUNT(*) FROM purl_loans")
total_purl = cursor.fetchone()[0]

print(f"\nTotal active document requests: {total_requests}")
print(f"Total PURL loans: {total_purl}")

# Get all document requests
cursor.execute("""
    SELECT id, loan_id, title, doc_type, status
    FROM smart_document_requests
    WHERE is_active = 1
""")
requests = cursor.fetchall()

# Get all PURL loans with workspace info
cursor.execute("""
    SELECT pl.id, pl.main_loan_id, pl.workspace_id, pw.slug, pw.display_name
    FROM purl_loans pl
    LEFT JOIN purl_workspaces pw ON pw.id = pl.workspace_id
""")
purl_loans = cursor.fetchall()

# Build lookup maps
purl_by_main_loan_id = {}
purl_by_id = {}

for pl in purl_loans:
    purl_by_id[pl['id']] = pl
    if pl['main_loan_id']:
        purl_by_main_loan_id[pl['main_loan_id']] = pl

mismatches = []
fixable = []
orphaned = []
correct = []

# Analyze each request
for req in requests:
    loan_id = req['loan_id']

    # Check if correctly linked via main_loan_id
    if loan_id in purl_by_main_loan_id:
        correct.append(req)
        continue

    # Check if using PURL loan id
    purl_loan = purl_by_id.get(loan_id)

    if purl_loan:
        if not purl_loan['main_loan_id']:
            fixable.append({
                "request_id": req['id'],
                "title": req['title'],
                "loan_id": loan_id,
                "purl_loan_id": purl_loan['id'],
                "workspace_slug": purl_loan['slug'],
                "workspace_name": purl_loan['display_name'],
                "issue": "PURL loan exists but main_loan_id not set",
            })
        elif purl_loan['main_loan_id'] != loan_id:
            mismatches.append({
                "request_id": req['id'],
                "title": req['title'],
                "request_loan_id": loan_id,
                "purl_loan_id": purl_loan['id'],
                "purl_main_loan_id": purl_loan['main_loan_id'],
                "workspace_slug": purl_loan['slug'],
                "issue": "Request loan_id doesn't match PURL main_loan_id",
            })
    else:
        orphaned.append({
            "request_id": req['id'],
            "title": req['title'],
            "loan_id": loan_id,
            "issue": "No PURL loan found",
        })

# Check for requests using purl.id instead of main_loan_id
for pl in purl_loans:
    if pl['main_loan_id'] and pl['main_loan_id'] != pl['id']:
        for req in requests:
            if req['loan_id'] == pl['id']:
                if not any(m["request_id"] == req['id'] for m in mismatches):
                    mismatches.append({
                        "request_id": req['id'],
                        "title": req['title'],
                        "request_loan_id": req['loan_id'],
                        "purl_loan_id": pl['id'],
                        "purl_main_loan_id": pl['main_loan_id'],
                        "workspace_slug": pl['slug'],
                        "issue": "Uses PURL loan ID instead of main_loan_id",
                    })

print("\n" + "-" * 60)
print("SUMMARY")
print("-" * 60)
print(f"Correctly linked:    {len(correct)}")
print(f"Mismatches:          {len(mismatches)}")
print(f"Fixable PURL loans:  {len(fixable)}")
print(f"Orphaned requests:   {len(orphaned)}")

if mismatches:
    print("\n" + "-" * 60)
    print("MISMATCHES (loan_id doesn't match main_loan_id)")
    print("-" * 60)
    for m in mismatches[:10]:
        print(f"\n  Request #{m['request_id']}: {m['title'][:40]}...")
        print(f"    Current loan_id: {m['request_loan_id']}")
        print(f"    Should be:       {m['purl_main_loan_id']}")
        print(f"    Workspace:       {m.get('workspace_slug', 'N/A')}")
    if len(mismatches) > 10:
        print(f"\n  ... and {len(mismatches) - 10} more")

if fixable:
    print("\n" + "-" * 60)
    print("FIXABLE (PURL loan needs main_loan_id set)")
    print("-" * 60)
    for f in fixable[:10]:
        print(f"\n  Request #{f['request_id']}: {f['title'][:40]}...")
        print(f"    loan_id: {f['loan_id']}")
        print(f"    Workspace: {f.get('workspace_slug', 'N/A')} ({f.get('workspace_name', 'N/A')})")
        print(f"    Fix: Set purl_loans.main_loan_id = {f['loan_id']} WHERE id = {f['purl_loan_id']}")
    if len(fixable) > 10:
        print(f"\n  ... and {len(fixable) - 10} more")

if orphaned:
    print("\n" + "-" * 60)
    print("ORPHANED (no PURL loan found)")
    print("-" * 60)
    for o in orphaned[:10]:
        print(f"\n  Request #{o['request_id']}: {o['title'][:40]}...")
        print(f"    loan_id: {o['loan_id']} (no matching PURL loan)")
    if len(orphaned) > 10:
        print(f"\n  ... and {len(orphaned) - 10} more")

# Show PURL loan details
print("\n" + "-" * 60)
print("PURL LOANS DETAIL")
print("-" * 60)
for pl in purl_loans[:15]:
    main_id = pl['main_loan_id'] if pl['main_loan_id'] else 'NULL'
    print(f"  PURL #{pl['id']}: main_loan_id={main_id}, workspace={pl['slug'] or 'N/A'}")
if len(purl_loans) > 15:
    print(f"  ... and {len(purl_loans) - 15} more")

# Provide fix commands
if fixable or mismatches:
    print("\n" + "=" * 60)
    print("FIX COMMANDS")
    print("=" * 60)

    if fixable:
        print("\n-- Fix PURL loans with missing main_loan_id:")
        for f in fixable:
            print(f"UPDATE purl_loans SET main_loan_id = {f['loan_id']} WHERE id = {f['purl_loan_id']};")

    if mismatches:
        print("\n-- Fix document requests with wrong loan_id:")
        for m in mismatches:
            print(f"UPDATE smart_document_requests SET loan_id = {m['purl_main_loan_id']} WHERE id = {m['request_id']};")

print("\n" + "=" * 60)

conn.close()
