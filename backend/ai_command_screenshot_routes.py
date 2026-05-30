"""
AI Command Screenshot Routes for Perennia AI

This module contains screenshot-related API endpoints for the AI command system:
- parse_screenshot_upload: Parse a screenshot image to extract lead information using Claude vision
- create_lead_from_screenshot: Create a new lead from parsed screenshot data
"""

from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from sqlalchemy.orm import Session
import logging
import json
import base64
import os

from database import get_db
from ai_command_models import (
    get_main_module,
    get_current_user_dependency,
    ScreenshotLeadData,
    CreateLeadFromScreenshotRequest,
)

logger = logging.getLogger(__name__)

screenshot_router = APIRouter()

# Initialize Anthropic client for vision
import anthropic

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None


# ============================================================================
# Screenshot Parsing Endpoints
# ============================================================================

@screenshot_router.post("/parse-screenshot-upload")
async def parse_screenshot_upload(
    image: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Parse a screenshot image (file upload) to extract lead information using Claude's vision.
    For JSON base64 input, use /parse-screenshot instead.
    """
    if not anthropic_client:
        raise HTTPException(status_code=500, detail="AI service not configured")

    # Validate file type
    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    try:
        # Read and encode the image
        image_data = await image.read()
        base64_image = base64.standard_b64encode(image_data).decode("utf-8")

        # Determine media type
        media_type = image.content_type or "image/jpeg"

        # Create the prompt for Claude to extract lead information
        extraction_prompt = """Analyze this screenshot which appears to be a text message or email introducing a lead from a realtor or referral partner.

Extract the following information if present:
- First Name
- Last Name
- Email
- Phone Number
- Referral Source (who sent the introduction - the realtor/partner name and company)
- Property Address (if mentioned)
- Loan Type (purchase, refinance, etc.)
- Loan Amount (if mentioned)
- Any additional notes or context

Return the information as a JSON object with these fields:
{
    "first_name": "",
    "last_name": "",
    "email": "",
    "phone": "",
    "referral_source": "",
    "property_address": "",
    "loan_type": "",
    "loan_amount": null,
    "notes": ""
}

Only include fields where you can extract actual data from the image. Leave fields empty or null if the information is not present.
Format phone numbers as (XXX) XXX-XXXX if possible.
For loan_amount, extract just the numeric value (no $ or commas).

Return ONLY the JSON object, no additional text."""

        # Call Claude with vision
        response = anthropic_client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": base64_image
                            }
                        },
                        {
                            "type": "text",
                            "text": extraction_prompt
                        }
                    ]
                }
            ]
        )

        # Parse the response
        response_text = response.content[0].text

        # Extract JSON from response
        try:
            # Find JSON in the response
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                lead_data = json.loads(json_str)

                # Check if we got any meaningful data
                has_data = any([
                    lead_data.get("first_name"),
                    lead_data.get("last_name"),
                    lead_data.get("email"),
                    lead_data.get("phone")
                ])

                if has_data:
                    return {
                        "success": True,
                        "lead_data": lead_data,
                        "message": "Successfully extracted lead information from screenshot"
                    }
                else:
                    return {
                        "success": False,
                        "lead_data": None,
                        "message": "Could not find lead information in the screenshot. Please ensure the image contains contact details."
                    }
            else:
                return {
                    "success": False,
                    "lead_data": None,
                    "message": "Could not parse the image. Please try a clearer screenshot."
                }

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from Claude response: {e}")
            return {
                "success": False,
                "lead_data": None,
                "message": "Failed to extract structured data from the screenshot."
            }

    except Exception as e:
        logger.error(f"Error parsing screenshot: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to process screenshot")


@screenshot_router.post("/create-lead-from-screenshot")
async def create_lead_from_screenshot(
    request: CreateLeadFromScreenshotRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dependency)
):
    """
    Create a new lead from parsed screenshot data.
    The lead will be created in the 'Attempted Contact' stage.
    """
    # Require authenticated user
    if not current_user or not hasattr(current_user, 'id'):
        raise HTTPException(status_code=401, detail="Authentication required")
    current_user_id = current_user.id

    main = get_main_module()
    Lead = main.Lead
    LeadStage = main.LeadStage

    try:
        # Construct the full name
        name = f"{request.first_name or ''} {request.last_name or ''}".strip()
        if not name:
            name = "Unknown"

        # Create the new lead
        new_lead = Lead(
            owner_id=current_user_id,
            name=name,
            email=request.email,
            phone=request.phone,
            source=request.referral_source or "Realtor Referral",
            stage=LeadStage.ATTEMPTED_CONTACT,  # Set to Attempted Contact stage
            loan_type=request.loan_type,
            preapproval_amount=request.loan_amount,
            notes=request.notes,
            property_address=request.property_address if hasattr(Lead, 'property_address') else None
        )

        db.add(new_lead)
        db.flush()

        from services.client_file_service import ensure_client_file
        ensure_client_file(db, new_lead)

        db.commit()
        db.refresh(new_lead)

        logger.info(f"Created lead from screenshot: {new_lead.id} - {new_lead.name}")

        return {
            "success": True,
            "message": f"Lead '{new_lead.name}' created successfully in Attempted Contact stage",
            "lead_id": new_lead.id,
            "lead_name": new_lead.name
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Error creating lead from screenshot: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create lead")
