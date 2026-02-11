"""
Salesforce Calendar Sync Custom Fields Setup

Creates the required custom fields on the Salesforce Event object
for CRM ↔ Salesforce calendar synchronization.

Custom Fields:
- CRM_Event_ID__c: External ID linking to CRM event (Text 36, Unique)
- CRM_Fingerprint__c: SHA256 hash for change detection (Text 64)
- CRM_Last_Pushed_At__c: Timestamp of last push from CRM (DateTime)
- CRM_Source__c: Source system identifier (Text 20)
- CRM_Sync_Version__c: Sync version counter (Number)

Usage:
    python -m scripts.salesforce_calendar_fields_setup --user-id 1
    python -m scripts.salesforce_calendar_fields_setup --check
    python -m scripts.salesforce_calendar_fields_setup --manual

Requirements:
    - User must have Salesforce OAuth connected
    - User must have Salesforce admin permissions (Customize Application)
"""
import os
import sys
import logging
import argparse
import asyncio
from typing import Optional, Dict, Any, List

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from database import SessionLocal
from salesforce_integration_models import IntegrationProfile
from services.salesforce.oauth_service import salesforce_oauth

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# Custom field definitions for Event object
CUSTOM_FIELDS = [
    {
        "fullName": "Event.CRM_Event_ID__c",
        "label": "CRM Event ID",
        "type": "Text",
        "length": 36,
        "description": "Unique identifier linking to CRM calendar event",
        "externalId": True,
        "unique": True,
        "caseSensitive": True,
    },
    {
        "fullName": "Event.CRM_Fingerprint__c",
        "label": "CRM Fingerprint",
        "type": "Text",
        "length": 64,
        "description": "SHA256 hash of event data for change detection and loop prevention",
        "externalId": False,
        "unique": False,
    },
    {
        "fullName": "Event.CRM_Last_Pushed_At__c",
        "label": "CRM Last Pushed At",
        "type": "DateTime",
        "description": "Timestamp when event was last pushed from CRM",
    },
    {
        "fullName": "Event.CRM_Source__c",
        "label": "CRM Source",
        "type": "Text",
        "length": 20,
        "description": "Source system (crm, salesforce, outlook)",
        "defaultValue": '"crm"',
    },
    {
        "fullName": "Event.CRM_Sync_Version__c",
        "label": "CRM Sync Version",
        "type": "Number",
        "precision": 10,
        "scale": 0,
        "description": "Incremental version number for sync tracking",
        "defaultValue": "1",
    },
]


async def get_salesforce_credentials(user_id: int) -> tuple[str, str]:
    """Get Salesforce access token and instance URL for a user."""
    db = SessionLocal()
    try:
        profile = db.query(IntegrationProfile).filter(
            IntegrationProfile.user_id == user_id,
            IntegrationProfile.provider == "salesforce",
            IntegrationProfile.status == "active"
        ).first()

        if not profile:
            raise Exception(f"No active Salesforce integration for user {user_id}")

        access_token, instance_url = await salesforce_oauth.get_access_token(db, profile.id)
        return access_token, instance_url
    finally:
        db.close()


async def check_existing_fields(access_token: str, instance_url: str) -> Dict[str, bool]:
    """Check which custom fields already exist on Event object."""
    results = {}

    async with httpx.AsyncClient() as client:
        # Query Event object metadata
        response = await client.get(
            f"{instance_url}/services/data/v60.0/sobjects/Event/describe",
            headers={"Authorization": f"Bearer {access_token}"}
        )

        if response.status_code != 200:
            raise Exception(f"Failed to describe Event object: {response.text}")

        event_metadata = response.json()
        existing_fields = {f["name"] for f in event_metadata.get("fields", [])}

        for field_def in CUSTOM_FIELDS:
            field_name = field_def["fullName"].replace("Event.", "")
            results[field_name] = field_name in existing_fields

    return results


async def create_custom_field_tooling(
    access_token: str,
    instance_url: str,
    field_def: Dict[str, Any]
) -> Dict[str, Any]:
    """Create a custom field using Tooling API."""

    field_name = field_def["fullName"].replace("Event.", "")

    # Build CustomField metadata
    metadata = {
        "Metadata": {
            "label": field_def["label"],
            "description": field_def.get("description", ""),
            "type": field_def["type"],
        },
        "FullName": field_def["fullName"],
    }

    # Add type-specific attributes
    if field_def["type"] == "Text":
        metadata["Metadata"]["length"] = field_def.get("length", 255)
        if field_def.get("externalId"):
            metadata["Metadata"]["externalId"] = True
        if field_def.get("unique"):
            metadata["Metadata"]["unique"] = True
        if field_def.get("caseSensitive"):
            metadata["Metadata"]["caseSensitive"] = True

    elif field_def["type"] == "Number":
        metadata["Metadata"]["precision"] = field_def.get("precision", 18)
        metadata["Metadata"]["scale"] = field_def.get("scale", 0)

    if "defaultValue" in field_def:
        metadata["Metadata"]["defaultValue"] = field_def["defaultValue"]

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{instance_url}/services/data/v60.0/tooling/sobjects/CustomField",
            json=metadata,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
        )

        if response.status_code == 201:
            return {"success": True, "field": field_name, "id": response.json().get("id")}
        else:
            return {"success": False, "field": field_name, "error": response.text}


async def create_fields_via_composite(
    access_token: str,
    instance_url: str,
    fields_to_create: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Create multiple fields using Composite API."""
    results = []

    for field_def in fields_to_create:
        result = await create_custom_field_tooling(access_token, instance_url, field_def)
        results.append(result)

        if result["success"]:
            logger.info(f"  ✅ Created: {result['field']}")
        else:
            logger.error(f"  ❌ Failed: {result['field']} - {result['error']}")

    return results


async def setup_fields(user_id: int) -> Dict[str, Any]:
    """Main function to set up all custom fields."""
    logger.info("=" * 60)
    logger.info("Salesforce Calendar Sync - Custom Fields Setup")
    logger.info("=" * 60)

    # Get credentials
    logger.info(f"\n1. Getting Salesforce credentials for user {user_id}...")
    try:
        access_token, instance_url = await get_salesforce_credentials(user_id)
        logger.info(f"   ✅ Connected to: {instance_url}")
    except Exception as e:
        logger.error(f"   ❌ Failed: {e}")
        return {"success": False, "error": "Internal server error"}

    # Check existing fields
    logger.info("\n2. Checking existing fields on Event object...")
    try:
        existing = await check_existing_fields(access_token, instance_url)
        for field, exists in existing.items():
            status = "✅ Exists" if exists else "⬜ Missing"
            logger.info(f"   {status}: {field}")
    except Exception as e:
        logger.error(f"   ❌ Failed to check fields: {e}")
        return {"success": False, "error": "Internal server error"}

    # Determine which fields to create
    fields_to_create = [
        field_def for field_def in CUSTOM_FIELDS
        if not existing.get(field_def["fullName"].replace("Event.", ""), False)
    ]

    if not fields_to_create:
        logger.info("\n3. All fields already exist! Nothing to create.")
        return {"success": True, "created": [], "existing": list(existing.keys())}

    # Create missing fields
    logger.info(f"\n3. Creating {len(fields_to_create)} missing field(s)...")
    try:
        results = await create_fields_via_composite(access_token, instance_url, fields_to_create)

        created = [r["field"] for r in results if r["success"]]
        failed = [r for r in results if not r["success"]]

        logger.info(f"\n4. Summary:")
        logger.info(f"   Created: {len(created)}")
        logger.info(f"   Failed: {len(failed)}")

        if failed:
            logger.info("\n   Failed fields:")
            for f in failed:
                logger.info(f"   - {f['field']}: {f['error'][:100]}")

        return {
            "success": len(failed) == 0,
            "created": created,
            "failed": failed,
            "existing": [f for f, exists in existing.items() if exists]
        }

    except Exception as e:
        logger.error(f"   ❌ Failed to create fields: {e}")
        return {"success": False, "error": "Internal server error"}


async def check_fields(user_id: int):
    """Just check which fields exist."""
    logger.info("Checking Salesforce Event custom fields...\n")

    try:
        access_token, instance_url = await get_salesforce_credentials(user_id)
        existing = await check_existing_fields(access_token, instance_url)

        logger.info("Field Status:")
        logger.info("-" * 40)
        all_exist = True
        for field_def in CUSTOM_FIELDS:
            field_name = field_def["fullName"].replace("Event.", "")
            exists = existing.get(field_name, False)
            status = "✅" if exists else "❌"
            logger.info(f"  {status} {field_name}")
            if not exists:
                all_exist = False

        logger.info("-" * 40)
        if all_exist:
            logger.info("All required fields exist!")
        else:
            logger.info("Some fields are missing. Run setup to create them.")

    except Exception as e:
        logger.error(f"Error: {e}")


def print_manual_instructions():
    """Print manual setup instructions for Salesforce admin."""
    logger.info("""
================================================================================
MANUAL SETUP INSTRUCTIONS
================================================================================

If automated setup fails, create these custom fields manually in Salesforce:

1. Go to: Setup → Object Manager → Event → Fields & Relationships → New

2. Create the following fields:

   Field 1: CRM Event ID
   ─────────────────────
   - Data Type: Text
   - Field Label: CRM Event ID
   - Length: 36
   - Field Name: CRM_Event_ID
   - ☑️ External ID
   - ☑️ Unique
   - ☑️ Case Sensitive

   Field 2: CRM Fingerprint
   ────────────────────────
   - Data Type: Text
   - Field Label: CRM Fingerprint
   - Length: 64
   - Field Name: CRM_Fingerprint

   Field 3: CRM Last Pushed At
   ───────────────────────────
   - Data Type: Date/Time
   - Field Label: CRM Last Pushed At
   - Field Name: CRM_Last_Pushed_At

   Field 4: CRM Source
   ───────────────────
   - Data Type: Text
   - Field Label: CRM Source
   - Length: 20
   - Field Name: CRM_Source
   - Default Value: "crm"

   Field 5: CRM Sync Version
   ─────────────────────────
   - Data Type: Number
   - Field Label: CRM Sync Version
   - Length: 10
   - Decimal Places: 0
   - Field Name: CRM_Sync_Version
   - Default Value: 1

3. Set Field-Level Security:
   - Make all fields visible to profiles that need calendar sync

4. (Optional) Add to Page Layouts:
   - Add fields to Event page layouts for visibility

================================================================================
""")


def main():
    parser = argparse.ArgumentParser(
        description="Setup Salesforce custom fields for calendar sync"
    )
    parser.add_argument(
        "--user-id", "-u",
        type=int,
        help="CRM user ID with Salesforce OAuth connection"
    )
    parser.add_argument(
        "--check", "-c",
        action="store_true",
        help="Only check if fields exist (requires --user-id)"
    )
    parser.add_argument(
        "--manual", "-m",
        action="store_true",
        help="Print manual setup instructions"
    )

    args = parser.parse_args()

    if args.manual:
        print_manual_instructions()
        return

    if not args.user_id:
        parser.error("--user-id is required for setup or check")

    if args.check:
        asyncio.run(check_fields(args.user_id))
    else:
        result = asyncio.run(setup_fields(args.user_id))
        if result.get("success"):
            logger.info("\n✅ Setup completed successfully!")
        else:
            logger.error(f"\n❌ Setup failed: {result.get('error', 'Unknown error')}")
            logger.info("\nRun with --manual to see manual setup instructions.")
            sys.exit(1)


if __name__ == "__main__":
    main()
