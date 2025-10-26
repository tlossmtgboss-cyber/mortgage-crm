from fastapi import APIRouter, HTTPException, Header, Request, Depends
from sqlalchemy.orm import Session
from typing import Optional
import hmac
import hashlib
import os
from datetime import datetime

from .db import get_db
from .models import Lead, Activity

router = APIRouter(prefix="/zapier", tags=["zapier"])

# Zapier webhook secret for authentication
ZAPIER_WEBHOOK_SECRET = os.getenv("ZAPIER_WEBHOOK_SECRET", "your-secret-key")


def verify_zapier_signature(payload: bytes, signature: str) -> bool:
    """Verify the webhook signature from Zapier."""
    expected_signature = hmac.new(
        ZAPIER_WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature, expected_signature)


@router.post("/webhook/lead")
async def receive_lead_webhook(
    request: Request,
    x_zapier_signature: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Receive lead data from Zapier webhook.
    Expects authenticated requests with detailed lead information.
    """
    # Get raw body for signature verification
    body = await request.body()
    
    # Verify signature if provided
    if x_zapier_signature:
        if not verify_zapier_signature(body, x_zapier_signature):
            raise HTTPException(status_code=401, detail="Invalid signature")
    
    # Parse JSON data
    data = await request.json()
    
    # Validate required fields
    required_fields = ["email", "name"]
    for field in required_fields:
        if field not in data:
            raise HTTPException(
                status_code=400,
                detail=f"Missing required field: {field}"
            )
    
    # Check if lead already exists
    existing_lead = db.query(Lead).filter(Lead.email == data["email"]).first()
    
    if existing_lead:
        # Update existing lead
        existing_lead.name = data.get("name", existing_lead.name)
        existing_lead.phone = data.get("phone", existing_lead.phone)
        existing_lead.status = data.get("status", existing_lead.status)
        existing_lead.source = data.get("source", existing_lead.source)
        existing_lead.loan_amount = data.get("loan_amount", existing_lead.loan_amount)
        existing_lead.property_address = data.get("property_address", existing_lead.property_address)
        existing_lead.updated_at = datetime.utcnow()
        
        # Log activity
        activity = Activity(
            lead_id=existing_lead.id,
            activity_type="lead_updated",
            description=f"Lead updated via Zapier webhook from {data.get('source', 'unknown')}",
            created_at=datetime.utcnow()
        )
        db.add(activity)
        db.commit()
        db.refresh(existing_lead)
        
        return {
            "status": "updated",
            "lead_id": existing_lead.id,
            "message": "Lead updated successfully"
        }
    else:
        # Create new lead
        new_lead = Lead(
            name=data["name"],
            email=data["email"],
            phone=data.get("phone"),
            status=data.get("status", "new"),
            source=data.get("source", "zapier"),
            loan_amount=data.get("loan_amount"),
            property_address=data.get("property_address"),
            notes=data.get("notes"),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(new_lead)
        db.commit()
        db.refresh(new_lead)
        
        # Log activity
        activity = Activity(
            lead_id=new_lead.id,
            activity_type="lead_created",
            description=f"Lead created via Zapier webhook from {data.get('source', 'unknown')}",
            created_at=datetime.utcnow()
        )
        db.add(activity)
        db.commit()
        
        return {
            "status": "created",
            "lead_id": new_lead.id,
            "message": "Lead created successfully"
        }


@router.post("/webhook/activity")
async def receive_activity_webhook(
    request: Request,
    x_zapier_signature: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Receive activity/interaction data from Zapier.
    Logs customer interactions from various sources.
    """
    # Get raw body for signature verification
    body = await request.body()
    
    # Verify signature if provided
    if x_zapier_signature:
        if not verify_zapier_signature(body, x_zapier_signature):
            raise HTTPException(status_code=401, detail="Invalid signature")
    
    # Parse JSON data
    data = await request.json()
    
    # Validate required fields
    if "lead_id" not in data:
        raise HTTPException(
            status_code=400,
            detail="Missing required field: lead_id"
        )
    
    # Verify lead exists
    lead = db.query(Lead).filter(Lead.id == data["lead_id"]).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    # Create activity record
    activity = Activity(
        lead_id=data["lead_id"],
        activity_type=data.get("activity_type", "interaction"),
        description=data.get("description", "Activity logged via Zapier"),
        created_at=datetime.utcnow()
    )
    db.add(activity)
    
    # Update lead's last interaction timestamp
    lead.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(activity)
    
    return {
        "status": "success",
        "activity_id": activity.id,
        "message": "Activity logged successfully"
    }


@router.get("/leads/{lead_id}")
def get_lead_for_zapier(
    lead_id: int,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Get lead data for Zapier to pull.
    Supports two-way sync - Zapier can fetch updated lead data.
    """
    # Verify API key
    expected_api_key = os.getenv("ZAPIER_API_KEY", "your-api-key")
    if api_key != expected_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    # Fetch lead
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    return {
        "id": lead.id,
        "name": lead.name,
        "email": lead.email,
        "phone": lead.phone,
        "status": lead.status,
        "source": lead.source,
        "loan_amount": lead.loan_amount,
        "property_address": lead.property_address,
        "notes": lead.notes,
        "created_at": lead.created_at.isoformat() if lead.created_at else None,
        "updated_at": lead.updated_at.isoformat() if lead.updated_at else None
    }


@router.get("/leads/updated")
def get_updated_leads(
    since: str,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Get leads updated since a specific timestamp.
    Enables Zapier to poll for changes and sync data.
    """
    # Verify API key
    expected_api_key = os.getenv("ZAPIER_API_KEY", "your-api-key")
    if api_key != expected_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    try:
        since_datetime = datetime.fromisoformat(since)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid datetime format. Use ISO format (YYYY-MM-DDTHH:MM:SS)"
        )
    
    # Fetch updated leads
    leads = db.query(Lead).filter(Lead.updated_at >= since_datetime).all()
    
    return {
        "count": len(leads),
        "leads": [
            {
                "id": lead.id,
                "name": lead.name,
                "email": lead.email,
                "phone": lead.phone,
                "status": lead.status,
                "source": lead.source,
                "loan_amount": lead.loan_amount,
                "property_address": lead.property_address,
                "updated_at": lead.updated_at.isoformat() if lead.updated_at else None
            }
            for lead in leads
        ]
    }
