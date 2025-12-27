"""Create a test loan for Smart Docs testing."""
import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)

def run_migration(engine):
    """Create a test loan."""
    with engine.connect() as conn:
        # Check if test loan already exists
        existing = conn.execute(text(
            "SELECT id FROM loans WHERE borrower_name = 'Test Borrower - Smart Docs' LIMIT 1"
        )).fetchone()
        
        if existing:
            logger.info(f"Test loan already exists with ID: {existing[0]}")
            return existing[0]
        
        # Get a user to assign the loan to
        user = conn.execute(text("SELECT id FROM users LIMIT 1")).fetchone()
        user_id = user[0] if user else None
        
        # Create test loan
        result = conn.execute(text("""
            INSERT INTO loans (
                borrower_name, loan_amount, property_address, 
                loan_type, status, transaction_type,
                loan_officer_id, created_at, updated_at
            ) VALUES (
                'Test Borrower - Smart Docs', 350000, '123 Test Street, Austin TX 78701',
                'Conventional', 'In Processing', 'Purchase',
                :user_id, NOW(), NOW()
            ) RETURNING id
        """), {"user_id": user_id})
        
        loan_id = result.fetchone()[0]
        conn.commit()
        
        logger.info(f"Created test loan with ID: {loan_id}")
        return loan_id

if __name__ == "__main__":
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from database import engine
    logging.basicConfig(level=logging.INFO)
    loan_id = run_migration(engine)
    print(f"Test loan URL: https://www.perenniaai.com/loans/{loan_id}")
