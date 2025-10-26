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
    prefix="/api/leads",
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

# --------------------
# NLP and Provider Setup
# --------------------
@dataclass
class EmailProviderConfig:
    provider: Literal["gmail", "outlook"]
    # For Gmail
    gmail_token_path: Optional[str] = None  # path to stored OAuth token.json
    gmail_client_id: Optional[str] = None
    gmail_client_secret: Optional[str] = None
    # For Outlook (Microsoft Graph)
    ms_client_id: Optional[str] = None
    ms_client_secret: Optional[str] = None
    ms_tenant_id: Optional[str] = None
    ms_scope: str = "https://graph.microsoft.com/.default"


def get_provider_config() -> EmailProviderConfig:
    """
    Select provider via env var LEAD_PROVIDER with values 'gmail' or 'outlook'.
    - To switch providers: set LEAD_PROVIDER=gmail or outlook and restart the app.
    - OAuth setup:
      Gmail:
        1) Create OAuth client in Google Cloud Console (Desktop or Web).
        2) Save client ID/secret as GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET.
        3) After first auth flow, persist token.json and set GMAIL_TOKEN_PATH to its path.
      Outlook (Microsoft Graph):
        1) Create Entra ID App Registration.
        2) Add a client secret.
        3) Set MS_CLIENT_ID, MS_CLIENT_SECRET, MS_TENANT_ID.
        4) Grant Mail.Read permissions and admin-consent.
    """
    provider = os.getenv("LEAD_PROVIDER", "gmail").lower()
    return EmailProviderConfig(
        provider=provider if provider in ("gmail", "outlook") else "gmail",
        gmail_token_path=os.getenv("GMAIL_TOKEN_PATH", "token.json"),
        gmail_client_id=os.getenv("GMAIL_CLIENT_ID"),
        gmail_client_secret=os.getenv("GMAIL_CLIENT_SECRET"),
        ms_client_id=os.getenv("MS_CLIENT_ID"),
        ms_client_secret=os.getenv("MS_CLIENT_SECRET"),
        ms_tenant_id=os.getenv("MS_TENANT_ID"),
    )


# Very lightweight NLP extraction from email body/signature
NAME_RE = re.compile(r"(?i)\b([A-Z][a-z]+)\s+([A-Z][a-z]+)\b")
PHONE_RE = re.compile(r"(?i)(?:\+?1\s*)?(?:\(\d{3}\)|\d{3})[\s.-]?\d{3}[\s.-]?\d{4}")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def nlp_extract_lead(text: str) -> LeadCreate:
    email_match = EMAIL_RE.search(text)
    phone_match = PHONE_RE.search(text)
    # Try to find a likely name; fallback to parts of email local-part
    name = None
    for m in NAME_RE.finditer(text[:200]):
        # Skip common non-names
        first, last = m.group(1), m.group(2)
        if first.lower() not in {"thanks", "thank", "best", "regards"}:
            name = (first, last)
            break
    first_name = "Unknown"
    last_name = "Lead"
    if name:
        first_name, last_name = name
    elif email_match:
        local = email_match.group(0).split("@")[0]
        parts = re.split(r"[._-]+", local)
        if len(parts) >= 2:
            first_name, last_name = parts[0].title(), parts[1].title()
        else:
            first_name = local.title()
    return LeadCreate(
        first_name=first_name,
        last_name=last_name,
        email=email_match.group(0) if email_match else None,
        phone=phone_match.group(0) if phone_match else None,
        status="new",
        source="email",
        notes=text[:1000],
    )


# --------------------
# Provider fetchers
# --------------------

def fetch_latest_gmail_thread_text(cfg: EmailProviderConfig) -> Optional[str]:
    if google_build is None or GoogleCredentials is None:
        return None
    token_path = cfg.gmail_token_path or "token.json"
    try:
        creds = GoogleCredentials.from_authorized_user_file(token_path, [
            "https://www.googleapis.com/auth/gmail.readonly",
        ])
        service = google_build('gmail', 'v1', credentials=creds)
        results = service.users().messages().list(userId='me', q='newer_than:3d subject:(introduction) OR subject:(referred) OR subject:(lead) OR subject:(inquiry)').execute()
        messages = results.get('messages', [])
        if not messages:
            return None
        msg = service.users().messages().get(userId='me', id=messages[0]['id'], format='full').execute()
        # Concatenate plaintext parts
        parts_text = []
        def traverse(payload):
            if not payload:
                return
            mime = payload.get('mimeType')
            data = payload.get('body', {}).get('data')
            if data and mime == 'text/plain':
                import base64
                parts_text.append(base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore'))
            for p in payload.get('parts', []) or []:
                traverse(p)
        traverse(msg.get('payload'))
        return "\n".join(parts_text) or msg.get('snippet')
    except Exception:
        return None


def fetch_latest_outlook_message_text(cfg: EmailProviderConfig) -> Optional[str]:
    if msal is None or requests is None:
        return None
    try:
        app = msal.ConfidentialClientApplication(
            client_id=cfg.ms_client_id,
            client_credential=cfg.ms_client_secret,
            authority=f"https://login.microsoftonline.com/{cfg.ms_tenant_id}",
        )
        token_result = app.acquire_token_silent([cfg.ms_scope], account=None)
        if not token_result:
            token_result = app.acquire_token_for_client(scopes=[cfg.ms_scope])
        access_token = token_result.get("access_token")
        if not access_token:
            return None
        headers = {"Authorization": f"Bearer {access_token}"}
        params = {
            "$top": 1,
            "$orderby": "receivedDateTime desc",
            "$search": '"introduction" OR "referred" OR "lead" OR "inquiry"',
        }
        resp = requests.get("https://graph.microsoft.com/v1.0/me/messages", headers=headers, params=params, timeout=20)
        if resp.status_code != 200:
            return None
        data = resp.json()
        if not data.get('value'):
            return None
        msg = data['value'][0]
        # Prefer textBody if available via $expand in richer queries; fall back to body.content
        body = msg.get('body', {}).get('content', '') or ''
        # Strip simple HTML tags
        return re.sub(r"<[^>]+>", " ", body)
    except Exception:
        return None


@router.post("/ingest/email", response_model=LeadResponse, status_code=status.HTTP_201_CREATED)
def ingest_lead_from_email(db: Session = Depends(get_db)):
    """
    Ingest the latest introduction/lead email and create a Lead using NLP extraction.
    - Switch providers via LEAD_PROVIDER env var: 'gmail' or 'outlook'.
    - Ensure OAuth credentials are configured per get_provider_config docstring.
    """
    cfg = get_provider_config()
    text: Optional[str] = None
    if cfg.provider == "gmail":
        text = fetch_latest_gmail_thread_text(cfg)
    elif cfg.provider == "outlook":
        text = fetch_latest_outlook_message_text(cfg)
    if not text:
        raise HTTPException(status_code=400, detail="No recent lead/introduction emails found or provider misconfigured")

    lead_create = nlp_extract_lead(text)
    db_lead = Lead(**lead_create.dict())
    db.add(db_lead)
    db.commit()
    db.refresh(db_lead)
    return db_lead


# CRUD endpoints (existing)
@router.post("/", response_model=LeadResponse, status_code=status.HTTP_201_CREATED)
def create_lead(lead: LeadCreate, db: Session = Depends(get_db)):
    """Create a new lead"""
    db_lead = Lead(**lead.dict())
    db.add(db_lead)
    db.commit()
    db.refresh(db_lead)
    return db_lead


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
