"""
Salesforce Sync and MUM Import Script
1. Pulls closed/funded loans from Salesforce
2. Imports them into the loans table
3. Creates MUM client records for portfolio management

Run: python scripts/sync_salesforce_and_import_mum.py
"""
import os
import sys
from datetime import datetime, date, timezone
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import requests
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class SalesforceImporter:
    """Import closed loans from Salesforce and create MUM client records"""

    def __init__(self):
        self.db_url = os.getenv('DATABASE_URL')
        if not self.db_url:
            raise ValueError("DATABASE_URL not set")

        self.engine = create_engine(self.db_url)
        self.Session = sessionmaker(bind=self.engine)

    def get_salesforce_connection(self):
        """Get Salesforce OAuth tokens from database"""
        with self.engine.connect() as conn:
            result = conn.execute(text("""
                SELECT user_id, access_token, refresh_token, scopes
                FROM user_integrations
                WHERE provider = 'salesforce' AND access_token IS NOT NULL
                ORDER BY updated_at DESC
                LIMIT 1
            """))
            row = result.fetchone()
            if row:
                # Parse instance_url from scopes
                instance_url = None
                scopes = row[3] or ""
                if "instance_url:" in scopes:
                    instance_url = scopes.split("instance_url:")[1].split(",")[0]

                return {
                    'user_id': row[0],
                    'access_token': row[1],
                    'refresh_token': row[2],
                    'instance_url': instance_url
                }
        return None

    def pull_closed_loans_from_salesforce(self, access_token, instance_url, limit=200):
        """Pull closed/funded loans from Salesforce"""
        logger.info("Pulling closed loans from Salesforce...")

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        sf_object = "MtgPlanner_CRM__Transaction_Property__c"

        # Get object fields
        describe_url = f"{instance_url}/services/data/v58.0/sobjects/{sf_object}/describe/"
        describe_resp = requests.get(describe_url, headers=headers, timeout=30)

        if describe_resp.status_code == 401:
            logger.error("Salesforce token expired. Please reconnect via Settings > Integrations")
            return []

        describe_resp.raise_for_status()
        describe_data = describe_resp.json()

        # Build field list
        queryable_fields = []
        for field in describe_data.get('fields', []):
            if field.get('type') not in ['base64', 'address', 'location']:
                queryable_fields.append(field.get('name'))

        field_list = ", ".join(queryable_fields[:50])

        # Query for funded/closed/shipped loans
        # Only include Funded_Date__c filter if the field exists on this object
        funded_date_filter = ""
        if 'MtgPlanner_CRM__Funded_Date__c' in queryable_fields:
            funded_date_filter = "OR MtgPlanner_CRM__Funded_Date__c != null"

        soql = f"""
            SELECT {field_list}
            FROM {sf_object}
            WHERE MtgPlanner_CRM__Status__c IN ('Funded', 'Closed', 'Closed Won', 'Shipped')
               {funded_date_filter}
            ORDER BY LastModifiedDate DESC
            LIMIT {limit}
        """

        logger.info(f"Executing SOQL query...")
        query_url = f"{instance_url}/services/data/v58.0/query/"
        query_resp = requests.get(query_url, headers=headers, params={"q": soql}, timeout=60)
        query_resp.raise_for_status()

        records = query_resp.json().get('records', [])
        logger.info(f"Found {len(records)} closed loans in Salesforce")

        return records

    def import_salesforce_records_to_loans(self, records):
        """Import Salesforce records into the loans table"""
        from services.salesforce_sync_service import DEFAULT_FIELD_MAPPING

        logger.info(f"Importing {len(records)} records to loans table...")

        results = {'created': 0, 'updated': 0, 'errors': []}

        with self.Session() as session:
            for record in records:
                try:
                    sf_id = record.get('Id')

                    # Check if loan exists
                    existing = session.execute(text(
                        "SELECT id FROM loans WHERE salesforce_id = :sf_id"
                    ), {"sf_id": sf_id}).fetchone()

                    # Map fields
                    loan_data = {'salesforce_id': sf_id}

                    for sf_field, (crm_field, transform) in DEFAULT_FIELD_MAPPING.items():
                        if sf_field in record and record[sf_field] is not None:
                            value = record[sf_field]

                            # Apply transforms
                            if transform == "decimal" and value:
                                try:
                                    value = float(value)
                                except Exception as e:
                                    logger.error(f"Error converting decimal field '{crm_field}' value '{value}': {e}")
                                    continue
                            elif transform == "date" and value:
                                try:
                                    value = datetime.fromisoformat(value.replace('Z', '+00:00')).date()
                                except Exception as e:
                                    logger.error(f"Error parsing ISO date for field '{crm_field}' value '{value}': {e}")
                                    try:
                                        value = datetime.strptime(value[:10], "%Y-%m-%d").date()
                                    except Exception as e2:
                                        logger.error(f"Error parsing date fallback for field '{crm_field}' value '{value}': {e2}")
                                        continue
                            elif transform == "stage_mapping":
                                from services.salesforce_sync_service import STAGE_MAPPING
                                value = STAGE_MAPPING.get(str(value), "FUNDED")
                            elif transform == "integer" and value:
                                try:
                                    value = int(value)
                                except Exception as e:
                                    logger.error(f"Error converting integer field '{crm_field}' value '{value}': {e}")
                                    continue

                            loan_data[crm_field] = value

                    # Set sync metadata
                    loan_data['salesforce_last_synced_at'] = datetime.now(timezone.utc)
                    loan_data['salesforce_sync_status'] = 'synced'

                    # Ensure loan_number
                    if not loan_data.get('loan_number'):
                        loan_data['loan_number'] = f"SF-{sf_id[-8:]}"

                    # Ensure stage is set for funded loans
                    if not loan_data.get('stage'):
                        loan_data['stage'] = 'FUNDED'

                    if existing:
                        # Update
                        update_fields = ", ".join([f"{k} = :{k}" for k in loan_data.keys() if k != 'salesforce_id'])
                        session.execute(text(f"""
                            UPDATE loans SET {update_fields}, updated_at = CURRENT_TIMESTAMP
                            WHERE salesforce_id = :salesforce_id
                        """), loan_data)
                        results['updated'] += 1
                    else:
                        # Insert
                        loan_data['organization_id'] = 1
                        columns = ", ".join(loan_data.keys())
                        placeholders = ", ".join([f":{k}" for k in loan_data.keys()])
                        session.execute(text(f"""
                            INSERT INTO loans ({columns}, created_at, updated_at)
                            VALUES ({placeholders}, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                        """), loan_data)
                        results['created'] += 1

                except Exception as e:
                    results['errors'].append(f"SF ID {record.get('Id')}: {str(e)}")
                    logger.error(f"Error importing {record.get('Id')}: {e}")

            session.commit()

        logger.info(f"Import complete: {results['created']} created, {results['updated']} updated")
        return results

    def import_funded_loans_to_mum_clients(self):
        """Import funded loans from loans table to mum_clients table"""
        logger.info("Importing funded loans to MUM clients...")

        with self.Session() as session:
            # Get funded loans not already in mum_clients
            result = session.execute(text("""
                SELECT l.id, l.loan_number, l.borrower_name, l.borrower_first_name, l.borrower_last_name,
                       l.borrower_email, l.borrower_phone, l.amount, l.interest_rate,
                       l.funded_date, l.closing_date, l.property_address,
                       l.property_city, l.property_state, l.property_zip,
                       l.loan_type, l.stage, l.status
                FROM loans l
                WHERE (l.stage IN ('FUNDED', 'Funded', 'funded')
                       OR l.status IN ('funded', 'FUNDED', 'Funded', 'closed', 'CLOSED')
                       OR l.funded_date IS NOT NULL)
                AND NOT EXISTS (
                    SELECT 1 FROM mum_clients m
                    WHERE m.loan_number = l.loan_number
                )
            """))

            loans_to_import = result.fetchall()
            logger.info(f"Found {len(loans_to_import)} funded loans to import to MUM clients")

            imported = 0
            errors = []

            for loan in loans_to_import:
                try:
                    # Build client name
                    client_name = loan[2]  # borrower_name
                    if not client_name and (loan[3] or loan[4]):  # first/last name
                        client_name = f"{loan[3] or ''} {loan[4] or ''}".strip()
                    if not client_name:
                        client_name = f"Client - {loan[1]}"  # loan_number

                    # Get closing date
                    close_date = loan[9] or loan[10]  # funded_date or closing_date

                    # Insert into mum_clients
                    session.execute(text("""
                        INSERT INTO mum_clients (
                            name, loan_number, original_close_date,
                            original_rate, loan_balance,
                            status, engagement_score, created_at
                        ) VALUES (
                            :name, :loan_number, :close_date,
                            :rate, :balance,
                            'active', 50, CURRENT_TIMESTAMP
                        )
                    """), {
                        'name': client_name,
                        'loan_number': loan[1],
                        'close_date': close_date,
                        'rate': loan[8],  # interest_rate
                        'balance': loan[7],  # amount
                    })

                    imported += 1
                    logger.info(f"  Imported: {client_name} ({loan[1]})")

                except Exception as e:
                    errors.append(f"Loan {loan[1]}: {str(e)}")
                    logger.error(f"Error importing loan {loan[1]}: {e}")

            session.commit()

        logger.info(f"MUM import complete: {imported} clients created, {len(errors)} errors")
        return {'imported': imported, 'errors': errors}

    def update_missing_fields_from_salesforce(self, access_token, instance_url):
        """Update loans with missing fields from Salesforce"""
        logger.info("Updating missing fields from Salesforce...")

        with self.Session() as session:
            # Get loans with Salesforce IDs that might have missing data
            result = session.execute(text("""
                SELECT id, salesforce_id, loan_number
                FROM loans
                WHERE salesforce_id IS NOT NULL
                AND (borrower_email IS NULL OR amount IS NULL OR amount = 0)
            """))

            loans_to_update = result.fetchall()
            logger.info(f"Found {len(loans_to_update)} loans with potentially missing data")

            if not loans_to_update:
                return {'updated': 0}

            # Fetch fresh data from Salesforce for each
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }

            updated = 0
            for loan_id, sf_id, loan_number in loans_to_update:
                try:
                    url = f"{instance_url}/services/data/v58.0/sobjects/MtgPlanner_CRM__Transaction_Property__c/{sf_id}"
                    resp = requests.get(url, headers=headers, timeout=30)

                    if resp.status_code == 200:
                        record = resp.json()
                        # Re-import this record
                        self.import_salesforce_records_to_loans([record])
                        updated += 1
                except Exception as e:
                    logger.error(f"Error updating loan {loan_number}: {e}")

            return {'updated': updated}

    def run(self):
        """Run the full sync and import process"""
        logger.info("=" * 60)
        logger.info("SALESFORCE SYNC AND MUM IMPORT")
        logger.info("=" * 60)

        # Check for Salesforce connection
        sf_conn = self.get_salesforce_connection()

        if sf_conn and sf_conn['access_token'] and sf_conn['instance_url']:
            logger.info(f"Found Salesforce connection (instance: {sf_conn['instance_url']})")

            # Step 1: Pull closed loans from Salesforce
            try:
                records = self.pull_closed_loans_from_salesforce(
                    sf_conn['access_token'],
                    sf_conn['instance_url']
                )

                if records:
                    # Step 2: Import to loans table
                    import_results = self.import_salesforce_records_to_loans(records)
                    logger.info(f"Salesforce import: {import_results['created']} new, {import_results['updated']} updated")

                    # Step 3: Update missing fields
                    update_results = self.update_missing_fields_from_salesforce(
                        sf_conn['access_token'],
                        sf_conn['instance_url']
                    )
                    logger.info(f"Updated {update_results['updated']} loans with missing fields")

            except Exception as e:
                logger.error(f"Salesforce sync error: {e}")
        else:
            logger.warning("No Salesforce connection found. Skipping Salesforce sync.")
            logger.warning("To connect: Go to Settings > Integrations > Connect Salesforce")

        # Step 4: Import funded loans to MUM clients (regardless of Salesforce)
        mum_results = self.import_funded_loans_to_mum_clients()

        logger.info("")
        logger.info("=" * 60)
        logger.info("SYNC COMPLETE")
        logger.info("=" * 60)
        logger.info(f"MUM clients imported: {mum_results['imported']}")

        return mum_results


def main():
    """Main entry point"""
    try:
        importer = SalesforceImporter()
        results = importer.run()
        return 0 if results else 1
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
