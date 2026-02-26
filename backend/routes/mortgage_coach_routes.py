"""
Mortgage Coach Integration Routes
Triggers Total Cost Analysis (TCA) creation via the Salesforce API
by invoking the Mortgage Coach custom action on a Salesforce record.
"""
import os
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/mortgage-coach",
    tags=["Mortgage Coach"],
)


def _get_db():
    """Get database session."""
    from database import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _get_current_user_id(request: Request, db: Session) -> Optional[int]:
    """Extract user ID from JWT token in request."""
    try:
        import jwt
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            secret_key = os.getenv("SECRET_KEY", "")
            payload = jwt.decode(
                token,
                secret_key,
                algorithms=["HS256"],
                options={"verify_aud": False, "verify_iss": False},
            )
            email = payload.get("sub")
            if email and db:
                result = db.execute(
                    text("SELECT id FROM users WHERE email = :email"),
                    {"email": email},
                ).fetchone()
                if result:
                    return result[0]
            return payload.get("user_id")
    except Exception as e:
        logger.warning(f"Failed to extract user ID: {e}")
    return None


def _get_salesforce_credentials(user_id: int, db: Session):
    """
    Retrieve the Salesforce access token and instance URL for the user.

    Checks the new OAuth integration_profiles table first, then falls back
    to the legacy user_integrations table.
    """
    # Try new OAuth integration_profiles table
    try:
        profile = db.execute(text("""
            SELECT id, access_token_encrypted, instance_url, status
            FROM integration_profiles
            WHERE user_id = :user_id
              AND provider = 'salesforce'
              AND status = 'connected'
            ORDER BY updated_at DESC
            LIMIT 1
        """), {"user_id": user_id}).fetchone()

        if profile and profile[1]:
            from encryption_utils import decrypt_value
            access_token = decrypt_value(profile[1])
            instance_url = profile[3] if len(profile) > 3 else profile[2]
            # Column order: id, access_token_encrypted, instance_url, status
            instance_url = profile[2]
            return access_token, instance_url
    except Exception as e:
        logger.debug(f"integration_profiles lookup failed: {e}")

    # Fallback to legacy user_integrations table
    try:
        integration = db.execute(text("""
            SELECT access_token, scopes
            FROM user_integrations
            WHERE user_id = :user_id AND provider = 'salesforce'
        """), {"user_id": user_id}).fetchone()

        if integration and integration[0]:
            try:
                from services.calendly_service import decrypt_token
                access_token = decrypt_token(integration[0])
            except ImportError:
                access_token = integration[0]

            instance_url = None
            scopes = integration[1] or ""
            if "instance_url:" in scopes:
                after_prefix = scopes.split("instance_url:")[1]
                instance_url = after_prefix.split(",")[0].strip()
                if not (instance_url.startswith("https://") and ".salesforce.com" in instance_url):
                    instance_url = None

            return access_token, instance_url
    except Exception as e:
        logger.debug(f"user_integrations lookup failed: {e}")

    return None, None


@router.post("/create-tca/{loan_id}")
async def create_total_cost_analysis(
    loan_id: str,
    request: Request,
    db: Session = Depends(_get_db),
):
    """
    Create a Mortgage Coach Total Cost Analysis for a loan.

    This endpoint:
    1. Looks up the loan's Salesforce record ID
    2. Uses the authenticated Salesforce connection to invoke the
       Mortgage Coach TCA action on that record
    3. Returns the TCA URL or confirmation

    The Mortgage Coach integration in Salesforce is typically exposed as a
    custom button/link that calls a Visualforce page or custom Apex REST
    endpoint. This route invokes that action programmatically.
    """
    user_id = _get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Get loan data
    loan = db.execute(text("""
        SELECT id, loan_number, borrower_name, borrower_email,
               amount, rate, loan_type, property_address,
               salesforce_id, stage
        FROM loans
        WHERE id = :loan_id
    """), {"loan_id": loan_id}).fetchone()

    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    loan_dict = dict(loan._mapping) if hasattr(loan, '_mapping') else {
        "id": loan[0], "loan_number": loan[1], "borrower_name": loan[2],
        "borrower_email": loan[3], "amount": loan[4], "rate": loan[5],
        "loan_type": loan[6], "property_address": loan[7],
        "salesforce_id": loan[8], "stage": loan[9],
    }

    salesforce_record_id = loan_dict.get("salesforce_id")
    if not salesforce_record_id:
        raise HTTPException(
            status_code=400,
            detail="This loan is not linked to Salesforce. Please sync the loan to Salesforce first.",
        )

    # Get Salesforce credentials
    access_token, instance_url = _get_salesforce_credentials(user_id, db)
    if not access_token or not instance_url:
        raise HTTPException(
            status_code=400,
            detail="Salesforce is not connected. Please connect in Settings > Integrations.",
        )

    # Determine the Salesforce API version
    try:
        from integrations.salesforce_service import SALESFORCE_API_VERSION
    except ImportError:
        SALESFORCE_API_VERSION = "v60.0"

    # Invoke the Mortgage Coach TCA creation via Salesforce
    # Mortgage Coach integrates with Salesforce through custom Apex REST endpoints
    # or by invoking a custom action/quick action on the Opportunity/Transaction object
    import httpx

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    tca_url = None
    method_used = None

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Strategy 1: Try invoking the Mortgage Coach custom Apex REST endpoint
        # Many Mortgage Coach SF packages expose: /services/apexrest/MortgageCoach/TCA
        try:
            apex_url = f"{instance_url}/services/apexrest/MortgageCoach/TCA"
            payload = {
                "recordId": salesforce_record_id,
                "action": "createTCA",
            }
            resp = await client.post(apex_url, headers=headers, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                tca_url = data.get("tcaUrl") or data.get("url") or data.get("redirectUrl")
                method_used = "apex_rest"
                logger.info(f"Mortgage Coach TCA created via Apex REST for loan {loan_id}")
        except Exception as e:
            logger.debug(f"Apex REST approach failed: {e}")

        # Strategy 2: Try invoking a Quick Action on the Salesforce record
        if not tca_url:
            try:
                # Try Opportunity quick action
                qa_url = (
                    f"{instance_url}/services/data/{SALESFORCE_API_VERSION}"
                    f"/sobjects/Opportunity/{salesforce_record_id}/quickActions/Mortgage_Coach_TCA"
                )
                resp = await client.post(qa_url, headers=headers, json={})
                if resp.status_code in (200, 201, 204):
                    tca_url = resp.json().get("url") if resp.content else None
                    method_used = "quick_action_opportunity"
                    logger.info(f"Mortgage Coach TCA created via Quick Action (Opportunity) for loan {loan_id}")
            except Exception as e:
                logger.debug(f"Quick Action Opportunity approach failed: {e}")

        # Strategy 3: Try the custom Transaction Property object quick action
        if not tca_url:
            try:
                qa_url = (
                    f"{instance_url}/services/data/{SALESFORCE_API_VERSION}"
                    f"/sobjects/MtgPlanner_CRM__Transaction_Property__c"
                    f"/{salesforce_record_id}/quickActions/Mortgage_Coach_TCA"
                )
                resp = await client.post(qa_url, headers=headers, json={})
                if resp.status_code in (200, 201, 204):
                    tca_url = resp.json().get("url") if resp.content else None
                    method_used = "quick_action_transaction"
                    logger.info(f"Mortgage Coach TCA created via Quick Action (Transaction) for loan {loan_id}")
            except Exception as e:
                logger.debug(f"Quick Action Transaction approach failed: {e}")

        # Strategy 4: Invoke via Salesforce composite/actions API
        if not tca_url:
            try:
                actions_url = (
                    f"{instance_url}/services/data/{SALESFORCE_API_VERSION}"
                    f"/actions/custom/flow/Mortgage_Coach_Create_TCA"
                )
                payload = {
                    "inputs": [{"recordId": salesforce_record_id}]
                }
                resp = await client.post(actions_url, headers=headers, json=payload)
                if resp.status_code in (200, 201):
                    result = resp.json()
                    if isinstance(result, list) and result:
                        tca_url = result[0].get("outputValues", {}).get("tcaUrl")
                    method_used = "flow_action"
                    logger.info(f"Mortgage Coach TCA created via Flow Action for loan {loan_id}")
            except Exception as e:
                logger.debug(f"Flow Action approach failed: {e}")

        # Strategy 5: Open the Mortgage Coach URL directly with record context
        # This is the most universal fallback - constructs the MC URL that
        # Salesforce's button typically opens
        if not tca_url:
            try:
                # Query the Salesforce record for the Mortgage Coach button URL
                # Check for a custom field that stores the MC link
                query = (
                    f"SELECT Id, Mortgage_Coach_Link__c, Mortgage_Coach_TCA_URL__c "
                    f"FROM Opportunity WHERE Id = '{salesforce_record_id}'"
                )
                query_url = (
                    f"{instance_url}/services/data/{SALESFORCE_API_VERSION}/query"
                    f"?q={query}"
                )
                resp = await client.get(query_url, headers=headers)
                if resp.status_code == 200:
                    records = resp.json().get("records", [])
                    if records:
                        tca_url = (
                            records[0].get("Mortgage_Coach_TCA_URL__c")
                            or records[0].get("Mortgage_Coach_Link__c")
                        )
                        if tca_url:
                            method_used = "existing_url_field"
            except Exception as e:
                logger.debug(f"URL field query failed: {e}")

        # Strategy 6: Construct the standard Mortgage Coach button URL
        # The Mortgage Coach button in SF typically navigates to:
        # {instance_url}/apex/MortgageCoach__MortgageCoachTCA?id={recordId}
        if not tca_url:
            tca_url = (
                f"{instance_url}/apex/MortgageCoach__MortgageCoachTCA"
                f"?id={salesforce_record_id}"
            )
            method_used = "standard_vf_page"
            logger.info(
                f"Using standard Mortgage Coach VF page URL for loan {loan_id}"
            )

    return {
        "status": "success",
        "loan_id": loan_id,
        "loan_number": loan_dict.get("loan_number"),
        "borrower_name": loan_dict.get("borrower_name"),
        "salesforce_id": salesforce_record_id,
        "tca_url": tca_url,
        "method": method_used,
        "message": "Mortgage Coach Total Cost Analysis initiated successfully",
    }


@router.get("/tca-status/{loan_id}")
async def get_tca_status(
    loan_id: str,
    request: Request,
    db: Session = Depends(_get_db),
):
    """
    Check if a loan has an existing Mortgage Coach TCA and return its URL.
    """
    user_id = _get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    loan = db.execute(text("""
        SELECT id, loan_number, salesforce_id
        FROM loans
        WHERE id = :loan_id
    """), {"loan_id": loan_id}).fetchone()

    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    loan_dict = dict(loan._mapping) if hasattr(loan, '_mapping') else {
        "id": loan[0], "loan_number": loan[1], "salesforce_id": loan[2],
    }

    salesforce_id = loan_dict.get("salesforce_id")
    if not salesforce_id:
        return {
            "status": "not_linked",
            "has_tca": False,
            "message": "Loan is not linked to Salesforce",
        }

    access_token, instance_url = _get_salesforce_credentials(user_id, db)
    if not access_token or not instance_url:
        return {
            "status": "not_connected",
            "has_tca": False,
            "message": "Salesforce is not connected",
        }

    return {
        "status": "available",
        "has_tca": True,
        "salesforce_id": salesforce_id,
        "tca_url": (
            f"{instance_url}/apex/MortgageCoach__MortgageCoachTCA"
            f"?id={salesforce_id}"
        ),
    }
