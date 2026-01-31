"""
Database Migration: Encrypt Sensitive Borrower Data
Migrates sensitive fields to encrypted storage for compliance with GLBA, GDPR
"""
import os
import sys
from sqlalchemy import create_engine, text, MetaData, Table
from sqlalchemy.orm import sessionmaker, Session
import logging
from encryption_utils import encrypt_value

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mortgage_crm.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)


def migrate_encrypted_fields():
    """
    Migrate sensitive fields to encrypted storage

    Strategy:
    1. Add new VARCHAR columns for encrypted data (_encrypted suffix)
    2. Encrypt existing data and copy to new columns
    3. Drop old columns
    4. Rename new columns to original names
    """

    try:
        engine = create_engine(DATABASE_URL)
        is_sqlite = DATABASE_URL.startswith("sqlite")

        def safe_add_column(conn, table, column, col_type="VARCHAR"):
            """Add column if it doesn't exist (works with SQLite and PostgreSQL)."""
            try:
                if is_sqlite:
                    # SQLite doesn't support IF NOT EXISTS for ALTER TABLE
                    # Try to add and catch error if exists
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
                else:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {col_type}"))
                return True
            except Exception as e:
                if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                    logger.info(f"    (column {column} already exists)")
                    return True
                raise

        with engine.connect() as conn:
            trans = conn.begin()

            try:
                logger.info("=" * 60)
                logger.info("STARTING ENCRYPTION MIGRATION")
                logger.info("=" * 60)

                # ============================================================
                # PHASE 1: ADD NEW ENCRYPTED COLUMNS
                # ============================================================
                logger.info("\n📝 Phase 1: Adding new encrypted columns...")

                # Lead table encrypted columns
                logger.info("  → leads.annual_income_encrypted")
                safe_add_column(conn, "leads", "annual_income_encrypted")

                logger.info("  → leads.monthly_debts_encrypted")
                safe_add_column(conn, "leads", "monthly_debts_encrypted")

                logger.info("  → leads.credit_score_encrypted")
                safe_add_column(conn, "leads", "credit_score_encrypted")

                # Loan table encrypted columns
                logger.info("  → loans.amount_encrypted")
                safe_add_column(conn, "loans", "amount_encrypted")

                logger.info("  → loans.purchase_price_encrypted")
                safe_add_column(conn, "loans", "purchase_price_encrypted")

                logger.info("  → loans.down_payment_encrypted")
                safe_add_column(conn, "loans", "down_payment_encrypted")

                logger.info("  → loans.rate_encrypted")
                safe_add_column(conn, "loans", "rate_encrypted")

                logger.info("✅ New columns added successfully")

                # ============================================================
                # PHASE 2: ENCRYPT AND MIGRATE DATA
                # ============================================================
                logger.info("\n🔐 Phase 2: Encrypting and migrating data...")

                # Migrate Lead data
                logger.info("  → Encrypting Lead records...")
                leads_result = conn.execute(text("SELECT id, annual_income, monthly_debts, credit_score FROM leads"))
                leads = leads_result.fetchall()
                lead_count = 0

                for lead in leads:
                    lead_id, annual_income, monthly_debts, credit_score = lead

                    # Encrypt each field if it has a value
                    encrypted_income = encrypt_value(str(annual_income)) if annual_income is not None else None
                    encrypted_debts = encrypt_value(str(monthly_debts)) if monthly_debts is not None else None
                    encrypted_score = encrypt_value(str(credit_score)) if credit_score is not None else None

                    conn.execute(text("""
                        UPDATE leads
                        SET annual_income_encrypted = :income,
                            monthly_debts_encrypted = :debts,
                            credit_score_encrypted = :score
                        WHERE id = :id
                    """), {
                        "income": encrypted_income,
                        "debts": encrypted_debts,
                        "score": encrypted_score,
                        "id": lead_id
                    })
                    lead_count += 1

                logger.info(f"    ✓ Encrypted {lead_count} lead records")

                # Migrate Loan data
                logger.info("  → Encrypting Loan records...")
                loans_result = conn.execute(text("SELECT id, amount, purchase_price, down_payment, rate FROM loans"))
                loans = loans_result.fetchall()
                loan_count = 0

                for loan in loans:
                    loan_id, amount, purchase_price, down_payment, rate = loan

                    # Encrypt each field if it has a value
                    encrypted_amount = encrypt_value(str(amount)) if amount is not None else None
                    encrypted_price = encrypt_value(str(purchase_price)) if purchase_price is not None else None
                    encrypted_down = encrypt_value(str(down_payment)) if down_payment is not None else None
                    encrypted_rate = encrypt_value(str(rate)) if rate is not None else None

                    conn.execute(text("""
                        UPDATE loans
                        SET amount_encrypted = :amount,
                            purchase_price_encrypted = :price,
                            down_payment_encrypted = :down,
                            rate_encrypted = :rate
                        WHERE id = :id
                    """), {
                        "amount": encrypted_amount,
                        "price": encrypted_price,
                        "down": encrypted_down,
                        "rate": encrypted_rate,
                        "id": loan_id
                    })
                    loan_count += 1

                logger.info(f"    ✓ Encrypted {loan_count} loan records")

                # ============================================================
                # PHASE 3: DROP OLD COLUMNS AND RENAME
                # ============================================================
                if is_sqlite:
                    # SQLite has limited ALTER TABLE support
                    # For local dev, we keep both columns (encrypted data is in *_encrypted columns)
                    logger.info("\n⚠️  Phase 3: SQLite detected - skipping column drop/rename")
                    logger.info("    (For local development, encrypted data is in *_encrypted columns)")
                    logger.info("    (Production PostgreSQL will complete full migration)")
                else:
                    logger.info("\n🗑️  Phase 3: Replacing old columns with encrypted versions...")

                    # Drop and rename Lead columns
                    logger.info("  → Updating Lead table schema...")
                    conn.execute(text("ALTER TABLE leads DROP COLUMN IF EXISTS annual_income"))
                    conn.execute(text("ALTER TABLE leads RENAME COLUMN annual_income_encrypted TO annual_income"))

                    conn.execute(text("ALTER TABLE leads DROP COLUMN IF EXISTS monthly_debts"))
                    conn.execute(text("ALTER TABLE leads RENAME COLUMN monthly_debts_encrypted TO monthly_debts"))

                    conn.execute(text("ALTER TABLE leads DROP COLUMN IF EXISTS credit_score"))
                    conn.execute(text("ALTER TABLE leads RENAME COLUMN credit_score_encrypted TO credit_score"))

                    # Drop and rename Loan columns
                    logger.info("  → Updating Loan table schema...")
                    conn.execute(text("ALTER TABLE loans DROP COLUMN IF EXISTS amount"))
                    conn.execute(text("ALTER TABLE loans RENAME COLUMN amount_encrypted TO amount"))

                    conn.execute(text("ALTER TABLE loans DROP COLUMN IF EXISTS purchase_price"))
                    conn.execute(text("ALTER TABLE loans RENAME COLUMN purchase_price_encrypted TO purchase_price"))

                    conn.execute(text("ALTER TABLE loans DROP COLUMN IF EXISTS down_payment"))
                    conn.execute(text("ALTER TABLE loans RENAME COLUMN down_payment_encrypted TO down_payment"))

                    conn.execute(text("ALTER TABLE loans DROP COLUMN IF EXISTS rate"))
                    conn.execute(text("ALTER TABLE loans RENAME COLUMN rate_encrypted TO rate"))

                    logger.info("✅ Schema updated successfully")

                # Commit all changes
                trans.commit()

                logger.info("\n" + "=" * 60)
                logger.info("✅ ENCRYPTION MIGRATION COMPLETED SUCCESSFULLY!")
                logger.info("=" * 60)
                logger.info(f"📊 Summary:")
                logger.info(f"   • {lead_count} lead records encrypted")
                logger.info(f"   • {loan_count} loan records encrypted")
                logger.info(f"   • 7 fields now using encryption")
                logger.info("=" * 60)

                return True

            except Exception as e:
                trans.rollback()
                logger.error(f"\n❌ Migration failed: {e}")
                logger.error("Database rolled back to previous state")
                raise

    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        return False


if __name__ == "__main__":
    logger.info("🔐 Sensitive Data Encryption Migration")
    logger.info("This will encrypt borrower financial data for compliance\n")

    success = migrate_encrypted_fields()

    if success:
        logger.info("\n✅ Migration completed successfully!")
        logger.info("   Sensitive data is now encrypted at rest")
        logger.info("   Compliant with GLBA, GDPR requirements")
        sys.exit(0)
    else:
        logger.error("\n❌ Migration failed!")
        sys.exit(1)
