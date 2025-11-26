#!/usr/bin/env python3
"""
Script to populate team members for all active loans
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.orm import Session
from database import SessionLocal
from models.active_loan_profile import ActiveLoanProfile

# Team member data to assign
TEAM_MEMBERS = {
    "processor": {
        "name": "Robert Garcia",
        "email": "robert.garcia@company.com",
        "title": "Senior Processor"
    },
    "processor_assistant": {
        "name": "Amanda Foster",
        "email": "amanda.foster@company.com",
        "title": "Loan Processor"
    },
    "underwriter": {
        "name": "Rachel Stevens",
        "email": "rachel.stevens@company.com",
        "title": "Underwriting Assistant"
    },
    "closer": {
        "name": "Lisa Wong",
        "email": "lisa.wong@company.com",
        "title": "Processing Manager"
    },
    "loan_officer": {
        "name": "Timothy Loss",
        "email": "tloss@cmgfi.com",
        "title": "Senior Loan Officer"
    }
}

def populate_loan_team_members():
    """Populate team members for all active loans"""
    db = SessionLocal()
    try:
        loans = db.query(ActiveLoanProfile).filter(
            ActiveLoanProfile.is_deleted == False
        ).all()

        print(f"Found {len(loans)} active loans to update")

        for loan in loans:
            # Update loan officer
            loan.loan_officer_name = TEAM_MEMBERS["loan_officer"]["name"]
            loan.loan_officer_email = TEAM_MEMBERS["loan_officer"]["email"]

            # Update processor
            loan.processor = TEAM_MEMBERS["processor"]["name"]
            loan.processor_email = TEAM_MEMBERS["processor"]["email"]

            # Update underwriter
            loan.underwriter = TEAM_MEMBERS["underwriter"]["name"]
            loan.underwriter_email = TEAM_MEMBERS["underwriter"]["email"]

            # Update closer
            loan.closer = TEAM_MEMBERS["closer"]["name"]
            loan.closer_email = TEAM_MEMBERS["closer"]["email"]

            print(f"Updated loan for {loan.borrower_name}")

        db.commit()
        print(f"\nSuccessfully updated {len(loans)} loans with team members")

    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    populate_loan_team_members()
