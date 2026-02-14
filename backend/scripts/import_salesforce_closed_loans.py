"""
Import Closed Loans from Salesforce

This script imports all closed/funded loans (Opportunities with Stage = 'Closed Won')
from Salesforce into the CRM with all available fields.

Data flows ONE-WAY: Salesforce → CRM

Usage:
    python scripts/import_salesforce_closed_loans.py

Or via API:
    POST /api/v1/salesforce/import-closed-loans
"""
import asyncio
import logging
import os
import sys
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional

import httpx

# Add backend to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from database import SessionLocal

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


# Use MtgPlanner_CRM__Transaction_Property__c (Jungo Loan object) instead of Opportunity
USE_TRANSACTION_PROPERTY = True
SALESFORCE_LOAN_OBJECT = 'MtgPlanner_CRM__Transaction_Property__c' if USE_TRANSACTION_PROPERTY else 'Opportunity'

# Salesforce field to CRM field mapping
OPPORTUNITY_FIELD_MAPPING = {
    # Standard fields
    'Id': 'salesforce_id',
    'Name': 'borrower_name',
    'CreatedDate': 'created_at',
    'LastModifiedDate': 'updated_at',

    # MtgPlanner_CRM fields (Jungo Transaction Property)
    'MtgPlanner_CRM__Loan_Amount__c': 'amount',
    'MtgPlanner_CRM__Loan_Type__c': 'loan_type',
    'MtgPlanner_CRM__Loan_Program__c': 'program',
    'MtgPlanner_CRM__Interest_Rate__c': 'rate',
    'MtgPlanner_CRM__Note_Rate__c': 'rate',
    'MtgPlanner_CRM__Status__c': 'stage',
    'MtgPlanner_CRM__Borrower_Name__c': 'borrower_name',
    'MtgPlanner_CRM__Borrower_Email__c': 'borrower_email',
    'MtgPlanner_CRM__Borrower_Phone__c': 'borrower_phone',
    'MtgPlanner_CRM__CoBorrower_Name__c': 'coborrower_name',
    'MtgPlanner_CRM__Property_Address__c': 'property_address',
    'MtgPlanner_CRM__Property_City__c': 'property_city',
    'MtgPlanner_CRM__Property_State__c': 'property_state',
    'MtgPlanner_CRM__Property_Zip__c': 'property_zip',
    'MtgPlanner_CRM__Purchase_Price__c': 'purchase_price',
    'MtgPlanner_CRM__Down_Payment__c': 'down_payment',
    'MtgPlanner_CRM__LTV__c': 'ltv',
    'MtgPlanner_CRM__CLTV__c': 'cltv',
    'MtgPlanner_CRM__Closing_Date__c': 'closing_date',
    'MtgPlanner_CRM__Funded_Date__c': 'funded_date',
    'MtgPlanner_CRM__First_Payment_Date__c': 'first_payment_date',
    'MtgPlanner_CRM__Application_Date__c': 'application_date',
    'MtgPlanner_CRM__Lock_Date__c': 'lock_date',
    'MtgPlanner_CRM__Lock_Expiration__c': 'lock_expiration_date',

    # Standard Opportunity fields (fallback)
    'Amount': 'amount',
    'StageName': 'stage',
    'CloseDate': 'closing_date',
    'Description': 'notes',
    'AccountId': 'salesforce_account_id',

    # Generic custom fields
    'Contact_Email__c': 'borrower_email',
    'Borrower_Email__c': 'borrower_email',
    'Email__c': 'borrower_email',
    'Contact_Phone__c': 'borrower_phone',
    'Borrower_Phone__c': 'borrower_phone',
    'Phone__c': 'borrower_phone',
    'Co_Borrower_Name__c': 'coborrower_name',
    'Co_Borrower_Email__c': 'co_borrower_email',

    # Loan details
    'Loan_Number__c': 'loan_number',
    'File_Name__c': 'loan_number',
    'Loan_Amount__c': 'amount',
    'Interest_Rate__c': 'rate',
    'Loan_Term__c': 'term',
    'Loan_Type__c': 'loan_type',
    'Loan_Program__c': 'program',
    'Loan_Purpose__c': 'loan_purpose',
    'Rate_Type__c': 'rate_type',

    # Property fields
    'Property_Address__c': 'property_address',
    'Property_Street__c': 'property_address',
    'Property_City__c': 'property_city',
    'Property_State__c': 'property_state',
    'Property_Zip__c': 'property_zip',
    'Property_County__c': 'property_county',
    'Property_Type__c': 'property_type',
    'Property_Value__c': 'purchase_price',
    'Appraised_Value__c': 'appraisal_value',
    'Occupancy_Type__c': 'occupancy_type',
    'Property_Units__c': 'property_units',

    # Financial details
    'Purchase_Price__c': 'purchase_price',
    'Down_Payment__c': 'down_payment',
    'LTV__c': 'ltv',
    'CLTV__c': 'cltv',
    'Monthly_Payment__c': 'monthly_payment',
    'Property_Tax__c': 'property_tax',
    'Hazard_Insurance__c': 'hazard_insurance',
    'Mortgage_Insurance__c': 'mortgage_insurance',
    'HOA_Amount__c': 'hoa_amount',
    'Origination_Fee__c': 'origination_fee',

    # Team members
    'Loan_Officer__c': 'loan_officer_name',
    'Loan_Officer_Email__c': 'loan_officer_email',
    'Processor__c': 'processor',
    'Processor_Email__c': 'processor_email',
    'Underwriter__c': 'underwriter',
    'Underwriter_Email__c': 'underwriter_email',
    'Closer__c': 'closer',
    'Closer_Email__c': 'closer_email',

    # Dates
    'Lock_Date__c': 'lock_date',
    'Lock_Expiration_Date__c': 'lock_expiration_date',
    'Application_Date__c': 'application_date',
    'Approval_Date__c': 'loan_approved_date',
    'Clear_to_Close_Date__c': 'clear_to_close_date',
    'Docs_Out_Date__c': 'docs_out_date',
    'Funding_Date__c': 'funded_date',
    'Funded_Date__c': 'funded_date',

    # Additional fields
    'Lender__c': 'lender',
    'Title_Company__c': 'title_company',
    'Realtor__c': 'realtor_agent',
    'Referral_Source__c': 'referral_source',
    'Credit_Score__c': 'credit_score',

    # 2nd Loan
    'Second_Loan_Amount__c': 'second_loan_amount',
    'Second_Loan_Rate__c': 'second_loan_rate',
    'Second_Loan_Payment__c': 'second_loan_payment',
}


class SalesforceClosedLoansImporter:
    """Import closed loans from Salesforce to CRM"""

    def __init__(self, integration_profile_id: int = None, user_id: int = None):
        self.integration_profile_id = integration_profile_id
        self.user_id = user_id
        self.access_token = None
        self.instance_url = None
        self.results = {
            'success': True,
            'total_found': 0,
            'imported': 0,
            'updated': 0,
            'skipped': 0,
            'failed': 0,
            'errors': [],
            'imported_loans': []
        }

    async def get_access_token(self, db) -> tuple:
        """Get Salesforce access token from integration profile"""
        from salesforce_integration_models import IntegrationProfile
        from services.salesforce.oauth_service import salesforce_oauth

        if self.integration_profile_id:
            return await salesforce_oauth.get_access_token(db, self.integration_profile_id)

        # Find first active Salesforce profile
        profile = db.query(IntegrationProfile).filter(
            IntegrationProfile.provider == 'salesforce',
            IntegrationProfile.status.in_(['connected', 'active'])
        ).first()

        if not profile:
            raise ValueError("No active Salesforce connection found")

        self.integration_profile_id = profile.id
        self.user_id = profile.user_id

        return await salesforce_oauth.get_access_token(db, profile.id)

    async def discover_opportunity_fields(self) -> List[str]:
        """Discover available fields on the Salesforce loan object"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.instance_url}/services/data/v60.0/sobjects/{SALESFORCE_LOAN_OBJECT}/describe",
                headers={
                    'Authorization': f'Bearer {self.access_token}',
                    'Content-Type': 'application/json'
                },
                timeout=30.0
            )

            if response.status_code != 200:
                logger.warning(f"Failed to describe {SALESFORCE_LOAN_OBJECT}: {response.text}")
                return list(OPPORTUNITY_FIELD_MAPPING.keys())

            data = response.json()
            available_fields = [f['name'] for f in data.get('fields', [])]

            logger.info(f"Discovered {len(available_fields)} fields on {SALESFORCE_LOAN_OBJECT}")
            return available_fields

    def build_soql_query(self, available_fields: List[str]) -> str:
        """Build SOQL query for closed loans"""
        # Get fields that exist in Salesforce - start with basic fields
        fields_to_query = ['Id', 'Name', 'CreatedDate', 'LastModifiedDate']

        # Add custom fields that exist
        for sf_field in OPPORTUNITY_FIELD_MAPPING.keys():
            if sf_field in available_fields and sf_field not in fields_to_query:
                fields_to_query.append(sf_field)

        fields_str = ', '.join(fields_to_query)

        if USE_TRANSACTION_PROPERTY:
            # Query MtgPlanner_CRM__Transaction_Property__c for closed/funded/shipped loans
            # Only include Funded_Date__c filter if the field exists on this object
            funded_date_filter = ""
            if 'MtgPlanner_CRM__Funded_Date__c' in available_fields:
                funded_date_filter = "OR MtgPlanner_CRM__Funded_Date__c != null"

            soql = f"""
                SELECT {fields_str}
                FROM {SALESFORCE_LOAN_OBJECT}
                WHERE MtgPlanner_CRM__Status__c IN ('Funded', 'Closed', 'Closed Won', 'Shipped', 'Complete', 'File Complete')
                   OR MtgPlanner_CRM__Status__c LIKE '%Fund%'
                   OR MtgPlanner_CRM__Status__c LIKE '%Ship%'
                   OR MtgPlanner_CRM__Status__c LIKE '%Close%'
                   {funded_date_filter}
                ORDER BY LastModifiedDate DESC
                LIMIT 2000
            """
        else:
            # Query standard Opportunity object
            soql = f"""
                SELECT {fields_str}
                FROM Opportunity
                WHERE StageName = 'Closed Won'
                   OR StageName LIKE '%Funded%'
                   OR StageName LIKE '%Closed%'
                   OR StageName LIKE '%Won%'
                   OR StageName LIKE '%Complete%'
                   OR StageName LIKE '%Settled%'
                   OR StageName LIKE '%Ship%'
                   OR StageName = 'Funded'
                   OR StageName = 'Shipped'
                   OR IsWon = true
                ORDER BY CloseDate DESC
                LIMIT 2000
            """

        return soql.strip()

    async def query_closed_opportunities(self, soql: str) -> List[Dict[str, Any]]:
        """Query Salesforce for closed opportunities"""
        all_records = []
        next_url = None

        async with httpx.AsyncClient() as client:
            # Initial query
            response = await client.get(
                f"{self.instance_url}/services/data/v60.0/query",
                params={'q': soql},
                headers={
                    'Authorization': f'Bearer {self.access_token}',
                    'Content-Type': 'application/json'
                },
                timeout=60.0
            )

            if response.status_code != 200:
                raise ValueError(f"Salesforce query failed: {response.text}")

            data = response.json()
            all_records.extend(data.get('records', []))
            next_url = data.get('nextRecordsUrl')

            # Handle pagination
            while next_url:
                response = await client.get(
                    f"{self.instance_url}{next_url}",
                    headers={
                        'Authorization': f'Bearer {self.access_token}',
                        'Content-Type': 'application/json'
                    },
                    timeout=60.0
                )

                if response.status_code != 200:
                    logger.warning(f"Pagination failed: {response.text}")
                    break

                data = response.json()
                all_records.extend(data.get('records', []))
                next_url = data.get('nextRecordsUrl')

        logger.info(f"Found {len(all_records)} closed opportunities in Salesforce")
        return all_records

    def transform_opportunity_to_loan(self, opportunity: Dict[str, Any]) -> Dict[str, Any]:
        """Transform Salesforce Opportunity to CRM Loan data"""
        loan_data = {}

        for sf_field, crm_field in OPPORTUNITY_FIELD_MAPPING.items():
            value = opportunity.get(sf_field)
            if value is not None:
                # Handle type conversions
                if crm_field in ['amount', 'purchase_price', 'down_payment', 'rate',
                                 'ltv', 'cltv', 'monthly_payment', 'appraisal_value',
                                 'property_tax', 'hazard_insurance', 'mortgage_insurance',
                                 'hoa_amount', 'origination_fee', 'second_loan_amount',
                                 'second_loan_rate', 'second_loan_payment']:
                    try:
                        loan_data[crm_field] = float(value)
                    except (ValueError, TypeError):
                        pass
                elif crm_field in ['term', 'property_units', 'credit_score']:
                    try:
                        loan_data[crm_field] = int(value)
                    except (ValueError, TypeError):
                        pass
                elif crm_field in ['closing_date', 'lock_date', 'lock_expiration_date',
                                  'funded_date', 'application_date', 'loan_approved_date',
                                  'clear_to_close_date', 'docs_out_date', 'first_payment_date',
                                  'created_at', 'updated_at']:
                    # Keep as string for now, database will parse
                    loan_data[crm_field] = str(value)[:10] if value else None
                else:
                    loan_data[crm_field] = str(value) if value else None

        # Map Salesforce stage to CRM stage (check both Opportunity and Transaction Property fields)
        sf_stage = opportunity.get('MtgPlanner_CRM__Status__c') or opportunity.get('StageName', '')
        loan_data['stage'] = self._map_stage(sf_stage)

        # Parse loan number and borrower name from the Name field (format: "Borrower - Loan # XXX")
        import re
        sf_name = opportunity.get('Name', '')

        if not loan_data.get('loan_number') and sf_name:
            if 'Loan #' in sf_name:
                match = re.search(r'Loan #\s*(\S+)', sf_name)
                if match:
                    loan_data['loan_number'] = match.group(1)
            elif 'RCA' in sf_name:
                match = re.search(r'(RCA\d+)', sf_name)
                if match:
                    loan_data['loan_number'] = match.group(1)

        # Extract borrower name from Name field if not set
        if not loan_data.get('borrower_name') and sf_name:
            if ' - Loan #' in sf_name:
                loan_data['borrower_name'] = sf_name.split(' - Loan #')[0].strip()
            else:
                loan_data['borrower_name'] = sf_name

        # Ensure required fields
        if not loan_data.get('borrower_name'):
            loan_data['borrower_name'] = 'Unknown Borrower'

        if not loan_data.get('amount'):
            amount = opportunity.get('MtgPlanner_CRM__Loan_Amount__c') or opportunity.get('Amount', 0)
            loan_data['amount'] = float(amount or 0)

        # Generate loan number if not present
        if not loan_data.get('loan_number'):
            loan_data['loan_number'] = f"SF-{opportunity.get('Id', '')[:15]}"

        return loan_data

    def _map_stage(self, sf_stage: str) -> str:
        """Map Salesforce stage to CRM stage (UPPERCASE enum values required)"""
        stage_lower = sf_stage.lower() if sf_stage else ''

        if 'funded' in stage_lower or 'closed won' in stage_lower or 'shipped' in stage_lower or 'complete' in stage_lower:
            return 'FUNDED'
        elif 'closing' in stage_lower:
            return 'CLOSING'
        elif 'clear to close' in stage_lower or 'ctc' in stage_lower:
            return 'CTC'
        elif 'docs' in stage_lower:
            return 'DOCS_OUT'
        elif 'approved' in stage_lower:
            return 'APPROVED'
        elif 'underwriting' in stage_lower:
            return 'UNDERWRITING'
        elif 'submitted' in stage_lower:
            return 'SUBMITTED'
        elif 'processing' in stage_lower:
            return 'PROCESSING'
        elif 'disclosed' in stage_lower:
            return 'DISCLOSED'
        elif 'application' in stage_lower:
            return 'APPLICATION'
        else:
            return 'FUNDED'  # Default for closed loans

    def _get_valid_columns(self, db) -> set:
        """Get actual column names from the loans table"""
        if not hasattr(self, '_valid_columns') or not self._valid_columns:
            rows = db.execute(text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'loans'
            """)).fetchall()
            self._valid_columns = {row[0] for row in rows}
            logger.info(f"Loans table has {len(self._valid_columns)} columns")
        return self._valid_columns

    async def import_loan(self, db, loan_data: Dict[str, Any]) -> Optional[int]:
        """Import a single loan to the CRM"""
        salesforce_id = loan_data.get('salesforce_id')
        loan_number = loan_data.get('loan_number')

        # Remove fields that don't exist in the actual DB table FIRST
        # Also exclude created_at/updated_at — we set those explicitly in SQL
        valid_columns = self._get_valid_columns(db)
        exclude_keys = {'created_at', 'updated_at', 'id'}
        loan_data = {k: v for k, v in loan_data.items() if k in valid_columns and k not in exclude_keys}

        # Check if loan already exists (use valid column checks)
        existing = None
        if salesforce_id and 'salesforce_id' in valid_columns:
            existing = db.execute(text("""
                SELECT id FROM loans WHERE salesforce_id = :sf_id
            """), {"sf_id": salesforce_id}).fetchone()

        if not existing and loan_number:
            existing = db.execute(text("""
                SELECT id FROM loans WHERE loan_number = :loan_num
            """), {"loan_num": loan_number}).fetchone()

        if existing:
            # Update existing loan
            loan_id = existing[0]

            # Build SET clause — exclude id and loan_number from updates
            set_parts = []
            for key in loan_data.keys():
                if key not in ('loan_number', 'id'):
                    set_parts.append(f"{key} = :{key}")

            if set_parts:
                set_clause = ", ".join(set_parts)

                loan_data['loan_id'] = loan_id

                db.execute(text(f"""
                    UPDATE loans SET {set_clause}, updated_at = CURRENT_TIMESTAMP
                    WHERE id = :loan_id
                """), loan_data)

            self.results['updated'] += 1
            return loan_id
        else:
            # Create new loan
            if not loan_data.get('loan_officer_id'):
                loan_data['loan_officer_id'] = self.user_id
            if not loan_data.get('organization_id') and getattr(self, 'organization_id', None):
                loan_data['organization_id'] = self.organization_id

            columns = ", ".join(loan_data.keys())
            placeholders = ", ".join([f":{k}" for k in loan_data.keys()])

            result = db.execute(text(f"""
                INSERT INTO loans ({columns}, created_at, updated_at)
                VALUES ({placeholders}, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                RETURNING id, loan_number
            """), loan_data)

            row = result.fetchone()
            self.results['imported'] += 1
            self.results['imported_loans'].append({
                'id': row[0],
                'loan_number': row[1],
                'borrower_name': loan_data.get('borrower_name'),
                'amount': loan_data.get('amount'),
                'salesforce_id': loan_data.get('salesforce_id')
            })

            return row[0]

    async def run(self) -> Dict[str, Any]:
        """Run the import process"""
        db = SessionLocal()

        try:
            logger.info("Starting Salesforce closed loans import...")

            # Get organization_id from user for multi-tenant isolation
            self.organization_id = None
            if self.user_id:
                user_row = db.execute(text(
                    "SELECT organization_id FROM users WHERE id = :uid"
                ), {"uid": self.user_id}).fetchone()
                if user_row:
                    self.organization_id = user_row[0]

            # Get access token
            self.access_token, self.instance_url = await self.get_access_token(db)
            logger.info(f"Connected to Salesforce: {self.instance_url}")

            # Discover available fields
            available_fields = await self.discover_opportunity_fields()

            # Build and execute query
            soql = self.build_soql_query(available_fields)
            logger.info(f"Executing SOQL query...")

            opportunities = await self.query_closed_opportunities(soql)
            self.results['total_found'] = len(opportunities)

            # Pre-fetch valid columns to avoid per-record queries
            self._get_valid_columns(db)

            # Import each opportunity
            for i, opp in enumerate(opportunities):
                try:
                    loan_data = self.transform_opportunity_to_loan(opp)
                    await self.import_loan(db, loan_data)

                    if (i + 1) % 50 == 0:
                        logger.info(f"Processed {i + 1}/{len(opportunities)} opportunities...")
                        db.commit()

                except Exception as e:
                    self.results['failed'] += 1
                    if len(self.results['errors']) < 20:
                        self.results['errors'].append({
                            'salesforce_id': opp.get('Id'),
                            'name': opp.get('Name'),
                            'error': str(e)
                        })
                    logger.error(f"Failed to import {opp.get('Id')}: {e}")
                    try:
                        db.rollback()
                    except Exception:
                        pass

            db.commit()

            logger.info(f"Import complete: {self.results['imported']} imported, "
                       f"{self.results['updated']} updated, {self.results['failed']} failed")

            return self.results

        except Exception as e:
            db.rollback()
            self.results['success'] = False
            self.results['errors'].append({'error': str(e)})
            logger.error(f"Import failed: {e}")
            raise
        finally:
            db.close()


async def main():
    """Main entry point for CLI execution"""
    importer = SalesforceClosedLoansImporter()
    results = await importer.run()

    print("\n" + "="*60)
    print("SALESFORCE CLOSED LOANS IMPORT COMPLETE")
    print("="*60)
    print(f"Total found in Salesforce: {results['total_found']}")
    print(f"Imported (new):            {results['imported']}")
    print(f"Updated (existing):        {results['updated']}")
    print(f"Failed:                    {results['failed']}")
    print("="*60)

    if results['errors']:
        print("\nErrors:")
        for err in results['errors'][:10]:
            print(f"  - {err}")

    return results


if __name__ == "__main__":
    asyncio.run(main())
