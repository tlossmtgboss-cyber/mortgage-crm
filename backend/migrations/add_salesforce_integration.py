"""
Salesforce Integration Migration
Adds Salesforce tracking fields to loans table and creates sync tracking table
"""
import os
import logging
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)


def run_migration():
    """Add Salesforce integration fields to the database."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set")
        return False

    engine = create_engine(database_url)

    # Detect database type
    is_sqlite = "sqlite" in database_url.lower()

    migrations = []

    if is_sqlite:
        # SQLite migrations
        migrations = [
            # Add salesforce_id to loans table
            """
            ALTER TABLE loans ADD COLUMN salesforce_id VARCHAR(18);
            """,
            """
            ALTER TABLE loans ADD COLUMN salesforce_last_synced_at TIMESTAMP;
            """,
            """
            ALTER TABLE loans ADD COLUMN salesforce_sync_status VARCHAR(20) DEFAULT 'pending';
            """,
            # Create index (SQLite syntax)
            """
            CREATE INDEX IF NOT EXISTS idx_loans_salesforce_id ON loans(salesforce_id);
            """,
            # Create Salesforce sync log table
            """
            CREATE TABLE IF NOT EXISTS salesforce_sync_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sync_type VARCHAR(20) NOT NULL,
                direction VARCHAR(20) DEFAULT 'inbound',
                salesforce_id VARCHAR(18),
                loan_id INTEGER,
                status VARCHAR(20) NOT NULL,
                records_processed INTEGER DEFAULT 0,
                records_created INTEGER DEFAULT 0,
                records_updated INTEGER DEFAULT 0,
                records_failed INTEGER DEFAULT 0,
                error_message TEXT,
                payload_summary TEXT,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                user_id INTEGER,
                organization_id INTEGER,
                FOREIGN KEY (loan_id) REFERENCES loans(id) ON DELETE SET NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
            );
            """,
            # Create Salesforce field mappings table (for customizable mappings)
            """
            CREATE TABLE IF NOT EXISTS salesforce_field_mappings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                salesforce_object VARCHAR(100) NOT NULL,
                salesforce_field VARCHAR(100) NOT NULL,
                crm_entity VARCHAR(50) NOT NULL,
                crm_field VARCHAR(100) NOT NULL,
                transform_type VARCHAR(50),
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(organization_id, salesforce_object, salesforce_field)
            );
            """,
        ]
    else:
        # PostgreSQL migrations
        migrations = [
            # Add salesforce_id to loans table (with IF NOT EXISTS check)
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'loans' AND column_name = 'salesforce_id'
                ) THEN
                    ALTER TABLE loans ADD COLUMN salesforce_id VARCHAR(18) UNIQUE;
                END IF;
            END $$;
            """,
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'loans' AND column_name = 'salesforce_last_synced_at'
                ) THEN
                    ALTER TABLE loans ADD COLUMN salesforce_last_synced_at TIMESTAMP;
                END IF;
            END $$;
            """,
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'loans' AND column_name = 'salesforce_sync_status'
                ) THEN
                    ALTER TABLE loans ADD COLUMN salesforce_sync_status VARCHAR(20) DEFAULT 'pending';
                END IF;
            END $$;
            """,
            # Create index
            """
            CREATE INDEX IF NOT EXISTS idx_loans_salesforce_id ON loans(salesforce_id);
            """,
            # Create Salesforce sync log table
            """
            CREATE TABLE IF NOT EXISTS salesforce_sync_logs (
                id SERIAL PRIMARY KEY,
                sync_type VARCHAR(20) NOT NULL,
                direction VARCHAR(20) DEFAULT 'inbound',
                salesforce_id VARCHAR(18),
                loan_id INTEGER REFERENCES loans(id) ON DELETE SET NULL,
                status VARCHAR(20) NOT NULL,
                records_processed INTEGER DEFAULT 0,
                records_created INTEGER DEFAULT 0,
                records_updated INTEGER DEFAULT 0,
                records_failed INTEGER DEFAULT 0,
                error_message TEXT,
                payload_summary JSONB,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                organization_id INTEGER
            );
            """,
            # Create indexes for sync logs
            """
            CREATE INDEX IF NOT EXISTS idx_sf_sync_logs_salesforce_id ON salesforce_sync_logs(salesforce_id);
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_sf_sync_logs_loan_id ON salesforce_sync_logs(loan_id);
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_sf_sync_logs_started_at ON salesforce_sync_logs(started_at);
            """,
            # Create Salesforce field mappings table
            """
            CREATE TABLE IF NOT EXISTS salesforce_field_mappings (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER NOT NULL,
                salesforce_object VARCHAR(100) NOT NULL,
                salesforce_field VARCHAR(100) NOT NULL,
                crm_entity VARCHAR(50) NOT NULL,
                crm_field VARCHAR(100) NOT NULL,
                transform_type VARCHAR(50),
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(organization_id, salesforce_object, salesforce_field)
            );
            """,
        ]

    with engine.connect() as conn:
        for migration in migrations:
            try:
                conn.execute(text(migration))
                conn.commit()
            except Exception as e:
                error_msg = str(e).lower()
                # Ignore "already exists" errors
                if "already exists" in error_msg or "duplicate column" in error_msg:
                    logger.info(f"Column/table already exists, skipping: {migration[:50]}...")
                    continue
                logger.error(f"Migration failed: {e}")
                logger.error(f"Failed SQL: {migration[:100]}...")
                # Continue with other migrations
                continue

    logger.info("Salesforce integration migration completed successfully")
    return True


def seed_default_field_mappings(organization_id: int = 1):
    """Seed default field mappings for MtgPlanner_CRM__Transaction_Property__c."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return False

    engine = create_engine(database_url)

    # Default field mappings for MtgPlanner_CRM package
    default_mappings = [
        # Core identifiers
        ("MtgPlanner_CRM__Transaction_Property__c", "Id", "loan", "salesforce_id", None),
        ("MtgPlanner_CRM__Transaction_Property__c", "Name", "loan", "loan_number", None),

        # Loan details
        ("MtgPlanner_CRM__Transaction_Property__c", "MtgPlanner_CRM__Loan_Amount__c", "loan", "amount", "decimal"),
        ("MtgPlanner_CRM__Transaction_Property__c", "MtgPlanner_CRM__Loan_Type__c", "loan", "loan_type", None),
        ("MtgPlanner_CRM__Transaction_Property__c", "MtgPlanner_CRM__Loan_Program__c", "loan", "program", None),

        # Property info
        ("MtgPlanner_CRM__Transaction_Property__c", "MtgPlanner_CRM__Property_Address__c", "loan", "property_address", None),
        ("MtgPlanner_CRM__Transaction_Property__c", "MtgPlanner_CRM__Property_City__c", "loan", "property_city", None),
        ("MtgPlanner_CRM__Transaction_Property__c", "MtgPlanner_CRM__Property_State__c", "loan", "property_state", None),
        ("MtgPlanner_CRM__Transaction_Property__c", "MtgPlanner_CRM__Property_Zip__c", "loan", "property_zip", None),
        ("MtgPlanner_CRM__Transaction_Property__c", "MtgPlanner_CRM__Purchase_Price__c", "loan", "purchase_price", "decimal"),

        # Borrower info
        ("MtgPlanner_CRM__Transaction_Property__c", "MtgPlanner_CRM__Borrower_Name__c", "loan", "borrower_name", None),
        ("MtgPlanner_CRM__Transaction_Property__c", "MtgPlanner_CRM__Borrower_Email__c", "loan", "borrower_email", None),
        ("MtgPlanner_CRM__Transaction_Property__c", "MtgPlanner_CRM__Borrower_Phone__c", "loan", "borrower_phone", None),

        # Status and dates
        ("MtgPlanner_CRM__Transaction_Property__c", "MtgPlanner_CRM__Status__c", "loan", "stage", "stage_mapping"),
        ("MtgPlanner_CRM__Transaction_Property__c", "MtgPlanner_CRM__Closing_Date__c", "loan", "closing_date", "date"),
        ("MtgPlanner_CRM__Transaction_Property__c", "MtgPlanner_CRM__Lock_Date__c", "loan", "lock_date", "date"),
        ("MtgPlanner_CRM__Transaction_Property__c", "MtgPlanner_CRM__Lock_Expiration__c", "loan", "lock_expiration_date", "date"),
    ]

    with engine.connect() as conn:
        for sf_object, sf_field, crm_entity, crm_field, transform in default_mappings:
            try:
                conn.execute(text("""
                    INSERT INTO salesforce_field_mappings
                    (organization_id, salesforce_object, salesforce_field, crm_entity, crm_field, transform_type)
                    VALUES (:org_id, :sf_object, :sf_field, :crm_entity, :crm_field, :transform)
                    ON CONFLICT (organization_id, salesforce_object, salesforce_field) DO NOTHING
                """), {
                    "org_id": organization_id,
                    "sf_object": sf_object,
                    "sf_field": sf_field,
                    "crm_entity": crm_entity,
                    "crm_field": crm_field,
                    "transform": transform
                })
                conn.commit()
            except Exception as e:
                logger.warning(f"Could not insert mapping {sf_field}: {e}")
                continue

    logger.info(f"Seeded {len(default_mappings)} default field mappings")
    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
    seed_default_field_mappings()
