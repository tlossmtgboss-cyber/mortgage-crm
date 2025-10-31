from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional, Literal
from pydantic import BaseModel, EmailStr
from datetime import datetime

import sys
sys.path.append('..')
from app.db import get_db
from app.models import Lead

# New imports for provider integrations and NLP
import os
import re
from dataclasses import dataclass

# Optional dependencies: google-api-python-client, google-auth, msal, requests
try:
    from google.oauth2.credentials import Credentials as GoogleCredentials
    from googleapiclient.discovery import build as google_build
except Exception:
    GoogleCredentials = None
    google_build = None

try:
    import msal
    import requests
except Exception:
    msal = None
    requests = None

router = APIRouter(
    prefix="/leads",
    tags=["leads"],
)

# Pydantic schemas
class LeadBase(BaseModel):
    first_name: str
    last_name: str
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    status: Optional[str] = "new"
    source: Optional[str] = None
    notes: Optional[str] = None

class LeadCreate(LeadBase):
    pass

class LeadUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    status: Optional[str] = None
    source: Optional[str] = None
    notes: Optional[str] = None

class LeadResponse(LeadBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# Email provider helper classes
@dataclass
class EmailMessage:
    id: str
    subject: str
    sender: str
    date: str
    snippet: str

# Provider-specific functions
def fetch_gmail_messages(credentials_json: dict, max_results: int = 10) -> List[EmailMessage]:
    """Fetch recent Gmail messages using Google API."""
    if not GoogleCredentials or not google_build:
        raise HTTPException(status_code=500, detail="Google API dependencies not installed")
    
    try:
        creds = GoogleCredentials.from_authorized_user_info(credentials_json)
        service = google_build('gmail', 'v1', credentials=creds)
        results = service.users().messages().list(userId='me', maxResults=max_results).execute()
        messages = results.get('messages', [])
        
        email_messages = []
        for msg in messages:
            msg_data = service.users().messages().get(userId='me', id=msg['id'], format='metadata').execute()
            headers = {h['name']: h['value'] for h in msg_data.get('payload', {}).get('headers', [])}
            email_messages.append(EmailMessage(
                id=msg['id'],
                subject=headers.get('Subject', ''),
                sender=headers.get('From', ''),
                date=headers.get('Date', ''),
                snippet=msg_data.get('snippet', '')
            ))
        return email_messages
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch Gmail messages: {str(e)}")

def fetch_outlook_messages(access_token: str, max_results: int = 10) -> List[EmailMessage]:
    """Fetch recent Outlook messages using Microsoft Graph API."""
    if not requests:
        raise HTTPException(status_code=500, detail="Requests library not installed")
    
    try:
        headers = {'Authorization': f'Bearer {access_token}'}
        response = requests.get(
            f'https://graph.microsoft.com/v1.0/me/messages?$top={max_results}',
            headers=headers
        )
        response.raise_for_status()
        messages = response.json().get('value', [])
        
        email_messages = []
        for msg in messages:
            email_messages.append(EmailMessage(
                id=msg['id'],
                subject=msg.get('subject', ''),
                sender=msg.get('from', {}).get('emailAddress', {}).get('address', ''),
                date=msg.get('receivedDateTime', ''),
                snippet=msg.get('bodyPreview', '')
            ))
        return email_messages
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch Outlook messages: {str(e)}")

def extract_lead_info_from_email(email: EmailMessage) -> dict:
    """Simple NLP-like extraction of contact info from email."""
    # Basic regex patterns for email and phone
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    phone_pattern = r'\b(?:\+?1[-.]?)?\(?([0-9]{3})\)?[-.]?([0-9]{3})[-.]?([0-9]{4})\b'
    
    text = f"{email.subject} {email.snippet}"
    
    # Extract email addresses
    emails_found = re.findall(email_pattern, text)
    primary_email = emails_found[0] if emails_found else email.sender
    
    # Extract phone numbers
    phones_found = re.findall(phone_pattern, text)
    phone = '-'.join(phones_found[0]) if phones_found else None
    
    # Try to extract name from sender
    name_match = re.match(r'^([^<]+)', email.sender)
    name = name_match.group(1).strip() if name_match else "Unknown"
    name_parts = name.split()
    
    return {
        'first_name': name_parts[0] if len(name_parts) > 0 else "Unknown",
        'last_name': name_parts[-1] if len(name_parts) > 1 else "",
        'email': primary_email,
        'phone': phone,
        'source': 'Email Import',
        'notes': f"Subject: {email.subject}\nSnippet: {email.snippet}"
    }

# CRUD endpoints
@router.get("/", response_model=List[LeadResponse])
def get_leads(
    skip: int = 0,
    limit: int = 100,
    status_filter: Optional[str] = None,
    source_filter: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Get all leads with optional filters"""
    query = db.query(Lead)
    
    if status_filter:
        query = query.filter(Lead.status == status_filter)
    
    if source_filter:
        query = query.filter(Lead.source == source_filter)
    
    leads = query.offset(skip).limit(limit).all()
    return leads

@router.get("/{lead_id}", response_model=LeadResponse)
def get_lead(lead_id: int, db: Session = Depends(get_db)):
    """Get a specific lead by ID"""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    return lead

@router.post("/", response_model=LeadResponse, status_code=status.HTTP_201_CREATED)
def create_lead(lead: LeadCreate, db: Session = Depends(get_db)):
    """Create a new lead"""
    db_lead = Lead(**lead.dict())
    db.add(db_lead)
    db.commit()
    db.refresh(db_lead)
    return db_lead

@router.put("/{lead_id}", response_model=LeadResponse)
def update_lead(lead_id: int, lead_update: LeadUpdate, db: Session = Depends(get_db)):
    """Update a lead"""
    db_lead = db.query(Lead).filter(Lead.id == lead_id).first()
    
    if not db_lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    update_data = lead_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_lead, field, value)
    
    db.commit()
    db.refresh(db_lead)
    return db_lead

@router.delete("/{lead_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_lead(lead_id: int, db: Session = Depends(get_db)):
    """Delete a lead"""
    db_lead = db.query(Lead).filter(Lead.id == lead_id).first()
    
    if not db_lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    db.delete(db_lead)
    db.commit()
    return None

# Email integration endpoints
class GmailAuthRequest(BaseModel):
    credentials_json: dict
    max_results: int = 10

class OutlookAuthRequest(BaseModel):
    access_token: str
    max_results: int = 10

@router.post("/import/gmail")
def import_leads_from_gmail(request: GmailAuthRequest, db: Session = Depends(get_db)):
    """Import leads from Gmail messages"""
    messages = fetch_gmail_messages(request.credentials_json, request.max_results)
    
    created_leads = []
    for msg in messages:
        lead_data = extract_lead_info_from_email(msg)
        db_lead = Lead(**lead_data)
        db.add(db_lead)
        created_leads.append(lead_data)
    
    db.commit()
    return {"imported": len(created_leads), "leads": created_leads}

@router.post("/import/outlook")
def import_leads_from_outlook(request: OutlookAuthRequest, db: Session = Depends(get_db)):
    """Import leads from Outlook messages"""
    messages = fetch_outlook_messages(request.access_token, request.max_results)
    
    created_leads = []
    for msg in messages:
        lead_data = extract_lead_info_from_email(msg)
        db_lead = Lead(**lead_data)
        db.add(db_lead)
        created_leads.append(lead_data)
    
    db.commit()
    return {"imported": len(created_leads), "leads": created_leads}
