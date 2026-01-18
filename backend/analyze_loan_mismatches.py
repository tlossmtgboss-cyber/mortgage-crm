#!/usr/bin/env python3
"""
Analyze loan ID mismatches between Smart Docs and PURL system.
Run this script from the backend directory.
"""

import os
import sys

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Get database URL
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mortgage_crm.db")

engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
db = Session()

try:
    from models.smart_docs_models import DocumentRequest, SmartDocument
    from models.purl import PURLLoan, PURLWorkspace

    print("=" * 60)
    print("LOAN ID MISMATCH ANALYSIS")
    print("=" * 60)

    # Get counts
    total_requests = db.query(DocumentRequest).filter(DocumentRequest.is_active == True).count()
    total_documents = db.query(SmartDocument).filter(SmartDocument.status.notin_(["DELETED", "SUPERSEDED"])).count()
    total_purl_loans = db.query(PURLLoan).count()

    print(f"\nTotal active document requests: {total_requests}")
    print(f"Total active documents: {total_documents}")
    print(f"Total PURL loans: {total_purl_loans}")

    # Get all data
    requests = db.query(DocumentRequest).filter(DocumentRequest.is_active == True).all()
    purl_loans = db.query(PURLLoan).all()

    # Build lookup maps
    purl_by_main_loan_id = {pl.main_loan_id: pl for pl in purl_loans if pl.main_loan_id}
    purl_by_id = {pl.id: pl for pl in purl_loans}

    mismatches = []
    fixable = []
    orphaned = []
    correct = []

    # Analyze each request
    for req in requests:
        loan_id = req.loan_id

        # Check if correctly linked via main_loan_id
        if loan_id in purl_by_main_loan_id:
            correct.append(req)
            continue

        # Check if using PURL loan id
        purl_loan = purl_by_id.get(loan_id)

        if purl_loan:
            if not purl_loan.main_loan_id:
                fixable.append({
                    "request_id": req.id,
                    "title": req.title,
                    "loan_id": loan_id,
                    "purl_loan_id": purl_loan.id,
                    "workspace_id": purl_loan.workspace_id,
                    "issue": "PURL loan exists but main_loan_id not set",
                })
            elif purl_loan.main_loan_id != loan_id:
                mismatches.append({
                    "request_id": req.id,
                    "title": req.title,
                    "request_loan_id": loan_id,
                    "purl_loan_id": purl_loan.id,
                    "purl_main_loan_id": purl_loan.main_loan_id,
                    "issue": "Request loan_id doesn't match PURL main_loan_id",
                })
        else:
            orphaned.append({
                "request_id": req.id,
                "title": req.title,
                "loan_id": loan_id,
                "issue": "No PURL loan found",
            })

    # Also check for requests using purl.id instead of main_loan_id
    for purl_loan in purl_loans:
        if purl_loan.main_loan_id and purl_loan.main_loan_id != purl_loan.id:
            wrong_requests = [r for r in requests if r.loan_id == purl_loan.id]
            for req in wrong_requests:
                if not any(m["request_id"] == req.id for m in mismatches):
                    mismatches.append({
                        "request_id": req.id,
                        "title": req.title,
                        "request_loan_id": req.loan_id,
                        "purl_loan_id": purl_loan.id,
                        "purl_main_loan_id": purl_loan.main_loan_id,
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
        for m in mismatches[:10]:  # Show first 10
            print(f"\n  Request #{m['request_id']}: {m['title']}")
            print(f"    Current loan_id: {m['request_loan_id']}")
            print(f"    Should be:       {m['purl_main_loan_id']}")
            print(f"    Issue: {m['issue']}")
        if len(mismatches) > 10:
            print(f"\n  ... and {len(mismatches) - 10} more")

    if fixable:
        print("\n" + "-" * 60)
        print("FIXABLE (PURL loan needs main_loan_id set)")
        print("-" * 60)
        for f in fixable[:10]:  # Show first 10
            print(f"\n  Request #{f['request_id']}: {f['title']}")
            print(f"    loan_id: {f['loan_id']}")
            print(f"    PURL loan needs main_loan_id = {f['loan_id']}")
        if len(fixable) > 10:
            print(f"\n  ... and {len(fixable) - 10} more")

    if orphaned:
        print("\n" + "-" * 60)
        print("ORPHANED (no PURL loan found)")
        print("-" * 60)
        for o in orphaned[:10]:  # Show first 10
            print(f"\n  Request #{o['request_id']}: {o['title']}")
            print(f"    loan_id: {o['loan_id']} (no matching PURL loan)")
        if len(orphaned) > 10:
            print(f"\n  ... and {len(orphaned) - 10} more")

    # Show PURL loan details
    print("\n" + "-" * 60)
    print("PURL LOANS DETAIL")
    print("-" * 60)
    for pl in purl_loans[:15]:
        workspace = db.query(PURLWorkspace).filter(PURLWorkspace.id == pl.workspace_id).first()
        slug = workspace.slug if workspace else "N/A"
        print(f"  PURL Loan #{pl.id}: main_loan_id={pl.main_loan_id or 'NULL'}, workspace={slug}")
    if len(purl_loans) > 15:
        print(f"  ... and {len(purl_loans) - 15} more")

    print("\n" + "=" * 60)
    print("To fix these issues, run:")
    print("  POST /api/v1/smart-docs/portal/fix-loan-id-mismatches?dry_run=false")
    print("=" * 60)

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
finally:
    db.close()
