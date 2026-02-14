"""
Email Management Routes
Extracted from inline_legacy_routes.py.

Includes:
- User onboarding completion
- Email signature CRUD + HTML generation + image upload
- Email drafts CRUD + send via Microsoft 365
- Call summary draft generation (AI-powered)

Lines ~17875-18774 from inline_legacy_routes.py.
"""
from fastapi import Depends, HTTPException, Request, UploadFile, File, Form, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timezone
from typing import List, Optional
import logging
import os
import json

logger = logging.getLogger(__name__)

# Import models
from database.models import (
    User, EmailSignature, EmailDraft, Lead, MicrosoftOAuthToken,
)


def register_email_management_routes(app, get_db, get_current_user, **kwargs):
    """Register email management routes.

    Required kwargs:
        refresh_microsoft_token: async function to refresh Microsoft OAuth tokens
    """
    refresh_microsoft_token = kwargs.get('refresh_microsoft_token')

    # ===========================================================================
    # FIRST-TIME USER ONBOARDING
    # ===========================================================================

    class OnboardingData(BaseModel):
        """Schema for completing first-time user onboarding"""
        first_name: str
        last_name: str
        phone: Optional[str] = None
        timezone: Optional[str] = 'America/New_York'
        role: Optional[str] = None
        department: Optional[str] = None
        job_title: Optional[str] = None
        nmls_id: Optional[str] = None
        annual_goal: Optional[float] = None
        monthly_goal: Optional[float] = None
        avg_loan_amount: Optional[float] = 350000
        pull_through_rate: Optional[float] = 75


    @app.post("/api/v1/users/complete-onboarding")
    async def complete_user_onboarding(
        data: OnboardingData,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        """Complete first-time user onboarding and save profile data"""
        try:
            # Update user profile
            current_user.full_name = f"{data.first_name} {data.last_name}"

            # Update additional fields if they exist
            if hasattr(current_user, 'phone'):
                current_user.phone = data.phone
            if hasattr(current_user, 'timezone'):
                current_user.timezone = data.timezone
            if hasattr(current_user, 'title'):
                current_user.title = data.job_title
            if hasattr(current_user, 'nmls_number'):
                current_user.nmls_number = data.nmls_id
            # department has no column on User; stored in user_metadata below

            # Store role and goals in user_metadata
            user_metadata = current_user.user_metadata or {}
            user_metadata['role_type'] = data.role
            user_metadata['department'] = data.department
            user_metadata['goals'] = {
                'annual_goal': data.annual_goal,
                'monthly_goal': data.monthly_goal,
                'avg_loan_amount': data.avg_loan_amount,
                'pull_through_rate': data.pull_through_rate
            }
            user_metadata['onboarding_data'] = {
                'first_name': data.first_name,
                'last_name': data.last_name,
                'completed_at': datetime.now(timezone.utc).isoformat()
            }
            current_user.user_metadata = user_metadata

            # Mark onboarding as completed
            current_user.onboarding_completed = True

            db.commit()
            db.refresh(current_user)

            logger.info(f"Onboarding completed for user {current_user.email}")

            return {
                "success": True,
                "message": "Onboarding completed successfully",
                "user": {
                    "id": current_user.id,
                    "email": current_user.email,
                    "full_name": current_user.full_name,
                    "onboarding_completed": True,
                    "role": data.role,
                    "department": data.department
                }
            }

        except Exception as e:
            db.rollback()
            logger.error(f"Error completing onboarding: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")


    # ============================================================================
    # EMAIL SIGNATURE MANAGEMENT
    # ============================================================================

    class EmailSignatureCreate(BaseModel):
        """Schema for creating/updating email signature"""
        full_name: Optional[str] = None
        title: Optional[str] = None
        team_name: Optional[str] = None
        headshot_url: Optional[str] = None
        company_logo_url: Optional[str] = None
        email: Optional[str] = None
        office_phone: Optional[str] = None
        cell_phone: Optional[str] = None
        fax: Optional[str] = None
        address: Optional[str] = None
        website_url: Optional[str] = None
        apply_now_url: Optional[str] = None
        doc_upload_url: Optional[str] = None
        schedule_url: Optional[str] = None
        linkedin_url: Optional[str] = None
        facebook_url: Optional[str] = None
        instagram_url: Optional[str] = None
        twitter_url: Optional[str] = None
        nmls_id: Optional[str] = None
        branch_nmls_id: Optional[str] = None
        corporate_nmls_id: Optional[str] = None
        primary_color: Optional[str] = "#006B6B"
        secondary_color: Optional[str] = "#1B3A4B"
        tagline: Optional[str] = None

    class EmailSignatureResponse(BaseModel):
        id: int
        user_id: int
        full_name: Optional[str]
        title: Optional[str]
        team_name: Optional[str]
        headshot_url: Optional[str]
        company_logo_url: Optional[str]
        email: Optional[str]
        office_phone: Optional[str]
        cell_phone: Optional[str]
        fax: Optional[str]
        address: Optional[str]
        website_url: Optional[str]
        apply_now_url: Optional[str]
        doc_upload_url: Optional[str]
        schedule_url: Optional[str]
        linkedin_url: Optional[str]
        facebook_url: Optional[str]
        instagram_url: Optional[str]
        twitter_url: Optional[str]
        nmls_id: Optional[str]
        branch_nmls_id: Optional[str]
        corporate_nmls_id: Optional[str]
        primary_color: Optional[str]
        secondary_color: Optional[str]
        tagline: Optional[str]
        is_active: bool
        created_at: Optional[datetime]
        updated_at: Optional[datetime]

        class Config:
            from_attributes = True

    @app.get("/api/v1/email-signature", response_model=EmailSignatureResponse)
    async def get_email_signature(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        """Get current user's email signature"""
        signature = db.query(EmailSignature).filter(
            EmailSignature.user_id == current_user.id
        ).first()

        if not signature:
            return EmailSignatureResponse(
                id=0,
                user_id=current_user.id,
                full_name=current_user.full_name,
                email=current_user.email,
                title=None,
                team_name=None,
                headshot_url=None,
                company_logo_url=None,
                office_phone=current_user.phone if hasattr(current_user, 'phone') else None,
                cell_phone=None,
                fax=None,
                address=current_user.business_address if hasattr(current_user, 'business_address') else None,
                website_url=None,
                apply_now_url=None,
                doc_upload_url=None,
                schedule_url=None,
                linkedin_url=None,
                facebook_url=None,
                instagram_url=None,
                twitter_url=None,
                nmls_id=current_user.nmls_number if hasattr(current_user, 'nmls_number') else None,
                branch_nmls_id=None,
                corporate_nmls_id=None,
                primary_color="#006B6B",
                secondary_color="#1B3A4B",
                tagline=None,
                is_active=True,
                created_at=None,
                updated_at=None
            )

        return signature

    class UserEmailUpdate(BaseModel):
        """Request body for updating user email"""
        new_email: EmailStr


    @app.put("/api/v1/account/email")
    async def update_current_user_email(
        email_update: UserEmailUpdate,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        """Update current user's email address"""
        try:
            # Check if new email is already in use
            existing = db.query(User).filter(User.email == email_update.new_email).first()
            if existing and existing.id != current_user.id:
                raise HTTPException(status_code=400, detail="Email already in use by another account")

            old_email = current_user.email
            current_user.email = email_update.new_email
            db.commit()
            db.refresh(current_user)

            logger.info(f"User email updated from {old_email} to {email_update.new_email}")

            return {
                "status": "success",
                "message": f"Email updated from {old_email} to {email_update.new_email}",
                "old_email": old_email,
                "new_email": email_update.new_email
            }
        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Error updating user email: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")


    @app.post("/api/v1/email-signature", response_model=EmailSignatureResponse)
    async def create_or_update_email_signature(
        signature_data: EmailSignatureCreate,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        """Create or update current user's email signature"""
        try:
            existing = db.query(EmailSignature).filter(
                EmailSignature.user_id == current_user.id
            ).first()

            if existing:
                for key, value in signature_data.model_dump(exclude_unset=True).items():
                    setattr(existing, key, value)
                existing.updated_at = datetime.now(timezone.utc)
                db.commit()
                db.refresh(existing)
                logger.info(f"Email signature updated for user {current_user.email}")
                return existing
            else:
                new_signature = EmailSignature(
                    user_id=current_user.id,
                    **signature_data.model_dump(exclude_unset=True)
                )
                db.add(new_signature)
                db.commit()
                db.refresh(new_signature)
                logger.info(f"Email signature created for user {current_user.email}")
                return new_signature
        except Exception as e:
            db.rollback()
            logger.error(f"Error saving email signature: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.post("/api/v1/email-signature/upload-image")
    async def upload_signature_image(
        file: UploadFile = File(...),
        image_type: str = Form(...),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        """Upload headshot or company logo for email signature"""
        import base64

        try:
            allowed_types = ["image/jpeg", "image/png", "image/gif", "image/webp"]
            if file.content_type not in allowed_types:
                raise HTTPException(status_code=400, detail=f"Invalid file type. Allowed: {', '.join(allowed_types)}")

            contents = await file.read()
            base64_data = base64.b64encode(contents).decode('utf-8')
            data_url = f"data:{file.content_type};base64,{base64_data}"

            signature = db.query(EmailSignature).filter(EmailSignature.user_id == current_user.id).first()

            if not signature:
                signature = EmailSignature(user_id=current_user.id)
                db.add(signature)

            if image_type == "headshot":
                signature.headshot_url = data_url
            elif image_type == "logo":
                signature.company_logo_url = data_url
            else:
                raise HTTPException(status_code=400, detail="image_type must be 'headshot' or 'logo'")

            signature.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(signature)

            logger.info(f"Uploaded {image_type} for user {current_user.email}")
            return {"success": True, "image_type": image_type, "url": data_url[:100] + "..."}

        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Error uploading signature image: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.get("/api/v1/email-signature/html")
    async def get_email_signature_html(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        """Get the HTML version of the email signature for embedding in emails"""
        signature = db.query(EmailSignature).filter(EmailSignature.user_id == current_user.id).first()

        if not signature:
            return {"html": "", "configured": False}

        html = generate_email_signature_html(signature)
        return {"html": html, "configured": True}

    def generate_email_signature_html(sig: EmailSignature) -> str:
        """Generate HTML email signature matching the CMG template style"""
        phones = []
        if sig.office_phone:
            phones.append(f'<span style="color: #333;">&#9742; {sig.office_phone}</span>')
        if sig.cell_phone:
            phones.append(f'<span style="color: #333;">&#9990; {sig.cell_phone}</span>')
        if sig.fax:
            phones.append(f'<span style="color: #333;">&#128224; {sig.fax}</span>')
        phone_html = ' | '.join(phones) if phones else ''

        links = []
        if sig.apply_now_url:
            links.append(f'<a href="{sig.apply_now_url}" style="color: {sig.primary_color}; text-decoration: none; font-weight: bold;">APPLY NOW</a>')
        if sig.website_url:
            links.append(f'<a href="{sig.website_url}" style="color: {sig.primary_color}; text-decoration: none; font-weight: bold;">MYSITE</a>')
        if sig.doc_upload_url:
            links.append(f'<a href="{sig.doc_upload_url}" style="color: {sig.primary_color}; text-decoration: none; font-weight: bold;">DOC UPLOAD</a>')
        if sig.schedule_url:
            links.append(f'<a href="{sig.schedule_url}" style="color: {sig.primary_color}; text-decoration: none; font-weight: bold;">SCHEDULE</a>')
        links_html = ' | '.join(links) if links else ''

        social_icons = []
        if sig.linkedin_url:
            social_icons.append(f'<a href="{sig.linkedin_url}" style="margin: 0 4px;"><img src="https://cdn-icons-png.flaticon.com/24/174/174857.png" alt="LinkedIn" width="20" height="20"></a>')
        if sig.facebook_url:
            social_icons.append(f'<a href="{sig.facebook_url}" style="margin: 0 4px;"><img src="https://cdn-icons-png.flaticon.com/24/733/733547.png" alt="Facebook" width="20" height="20"></a>')
        if sig.instagram_url:
            social_icons.append(f'<a href="{sig.instagram_url}" style="margin: 0 4px;"><img src="https://cdn-icons-png.flaticon.com/24/2111/2111463.png" alt="Instagram" width="20" height="20"></a>')
        if sig.twitter_url:
            social_icons.append(f'<a href="{sig.twitter_url}" style="margin: 0 4px;"><img src="https://cdn-icons-png.flaticon.com/24/733/733579.png" alt="Twitter" width="20" height="20"></a>')
        social_html = ''.join(social_icons) if social_icons else ''

        nmls_parts = []
        if sig.nmls_id:
            nmls_parts.append(f'NMLS# {sig.nmls_id}')
        if sig.branch_nmls_id:
            nmls_parts.append(f'BRANCH NMLS# {sig.branch_nmls_id}')
        if sig.corporate_nmls_id:
            nmls_parts.append(f'CORPORATE NMLS# {sig.corporate_nmls_id}')
        nmls_html = ' | '.join(nmls_parts) if nmls_parts else ''

        headshot_html = ''
        if sig.headshot_url:
            headshot_html = f'<td style="vertical-align: top; padding-right: 15px;"><img src="{sig.headshot_url}" alt="{sig.full_name or "Photo"}" style="width: 100px; height: 100px; border-radius: 50%; object-fit: cover; border: 2px solid {sig.primary_color};"></td>'

        logo_html = ''
        if sig.company_logo_url:
            tagline_span = f'<span style="background: {sig.secondary_color}; color: white; padding: 5px 15px; font-size: 11px; font-weight: bold; margin-left: 10px;">{sig.tagline}</span>' if sig.tagline else ''
            logo_html = f'<tr><td colspan="2" style="padding-top: 10px;"><img src="{sig.company_logo_url}" alt="Company Logo" style="max-height: 50px; max-width: 200px;">{tagline_span}</td></tr>'

        html = f'''<table cellpadding="0" cellspacing="0" border="0" style="font-family: Arial, sans-serif; font-size: 13px; color: #333; max-width: 500px;">
        <tr>
            {headshot_html}
            <td style="vertical-align: top;">
                <table cellpadding="0" cellspacing="0" border="0">
                    <tr><td style="font-size: 18px; font-weight: bold; color: {sig.primary_color};">{sig.full_name or ''}</td></tr>
                    {f'<tr><td style="font-size: 13px; color: #666;">{sig.team_name}</td></tr>' if sig.team_name else ''}
                    {f'<tr><td style="font-size: 13px; color: #666;">{sig.title}</td></tr>' if sig.title else ''}
                    <tr><td style="height: 8px;"></td></tr>
                    {f'<tr><td><a href="mailto:{sig.email}" style="color: {sig.primary_color}; text-decoration: none;">&#9993; {sig.email}</a></td></tr>' if sig.email else ''}
                    {f'<tr><td>{phone_html}</td></tr>' if phone_html else ''}
                    {f'<tr><td style="padding-top: 5px;">&#128205; {sig.address}</td></tr>' if sig.address else ''}
                    <tr><td style="height: 10px;"></td></tr>
                    {f'<tr><td>{links_html}</td></tr>' if links_html else ''}
                    {f'<tr><td style="padding-top: 8px;">{social_html}</td></tr>' if social_html else ''}
                    <tr><td style="height: 10px;"></td></tr>
                    {f'<tr><td style="font-size: 10px; color: #888;">{nmls_html}</td></tr>' if nmls_html else ''}
                </table>
            </td>
        </tr>
        {logo_html}
    </table>'''
        return html

    @app.get("/api/v1/email-signature/preview")
    async def preview_email_signature(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        """Get a preview of the email signature with all data"""
        signature = db.query(EmailSignature).filter(EmailSignature.user_id == current_user.id).first()

        if not signature:
            return {"configured": False, "html": "", "data": None}

        html = generate_email_signature_html(signature)

        return {
            "configured": True,
            "html": html,
            "data": {
                "full_name": signature.full_name,
                "title": signature.title,
                "team_name": signature.team_name,
                "email": signature.email,
                "office_phone": signature.office_phone,
                "cell_phone": signature.cell_phone,
                "address": signature.address,
                "has_headshot": bool(signature.headshot_url),
                "has_logo": bool(signature.company_logo_url),
                "links_count": sum([bool(signature.apply_now_url), bool(signature.website_url), bool(signature.doc_upload_url), bool(signature.schedule_url)]),
                "social_count": sum([bool(signature.linkedin_url), bool(signature.facebook_url), bool(signature.instagram_url), bool(signature.twitter_url)])
            }
        }

    # ============================================================================
    # EMAIL DRAFTS - Call Recording Summaries
    # ============================================================================

    class EmailDraftCreate(BaseModel):
        lead_id: Optional[int] = None
        loan_id: Optional[int] = None
        recipient_email: str
        recipient_name: Optional[str] = None
        cc_emails: Optional[List[str]] = []
        subject: str
        body_html: str
        body_text: Optional[str] = None
        source_type: Optional[str] = "manual"
        source_id: Optional[str] = None
        recording_url: Optional[str] = None
        call_summary: Optional[str] = None
        action_items: Optional[List[str]] = []

    class EmailDraftUpdate(BaseModel):
        recipient_email: Optional[str] = None
        recipient_name: Optional[str] = None
        cc_emails: Optional[List[str]] = None
        subject: Optional[str] = None
        body_html: Optional[str] = None
        body_text: Optional[str] = None
        status: Optional[str] = None

    class CallSummaryRequest(BaseModel):
        recording_url: str
        lead_id: Optional[int] = None
        loan_id: Optional[int] = None
        recipient_email: str
        recipient_name: Optional[str] = None
        meeting_name: Optional[str] = None
        call_duration_seconds: Optional[int] = None

    @app.post("/api/v1/email-drafts/setup-table")
    async def setup_email_drafts_table(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        """Setup email_drafts table (non-admin accessible migration)"""
        try:
            # Create email_drafts table if not exists
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS email_drafts (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id),
                    lead_id INTEGER REFERENCES leads(id),
                    loan_id INTEGER REFERENCES loans(id),
                    recipient_email VARCHAR(255),
                    recipient_name VARCHAR(255),
                    cc_emails JSONB DEFAULT '[]',
                    subject VARCHAR(500),
                    body_html TEXT,
                    body_text TEXT,
                    source_type VARCHAR(50),
                    source_id VARCHAR(255),
                    recording_url TEXT,
                    call_summary TEXT,
                    action_items JSONB DEFAULT '[]',
                    status VARCHAR(50) DEFAULT 'draft',
                    sent_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))

            # Create indexes
            try:
                db.execute(text("CREATE INDEX IF NOT EXISTS idx_email_drafts_user ON email_drafts(user_id)"))
                db.execute(text("CREATE INDEX IF NOT EXISTS idx_email_drafts_lead ON email_drafts(lead_id)"))
                db.execute(text("CREATE INDEX IF NOT EXISTS idx_email_drafts_status ON email_drafts(status)"))
            except Exception:
                pass

            db.commit()
            return {"success": True, "message": "Email drafts table created"}
        except Exception as e:
            logger.error(f"Error setting up email_drafts table: {e}")
            db.rollback()
            return {"success": False, "error": "Internal server error"}

    @app.post("/api/v1/email-drafts")
    async def create_email_draft(
        draft: EmailDraftCreate,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        """Create a new email draft"""
        try:
            new_draft = EmailDraft(
                user_id=current_user.id,
                lead_id=draft.lead_id,
                loan_id=draft.loan_id,
                recipient_email=draft.recipient_email,
                recipient_name=draft.recipient_name,
                cc_emails=draft.cc_emails or [],
                subject=draft.subject,
                body_html=draft.body_html,
                body_text=draft.body_text,
                source_type=draft.source_type,
                source_id=draft.source_id,
                recording_url=draft.recording_url,
                call_summary=draft.call_summary,
                action_items=draft.action_items or [],
                status="draft"
            )
            db.add(new_draft)
            db.commit()
            db.refresh(new_draft)

            return {
                "success": True,
                "draft_id": new_draft.id,
                "message": "Email draft created successfully"
            }
        except Exception as e:
            logger.error(f"Error creating email draft: {e}")
            db.rollback()
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.get("/api/v1/email-drafts")
    async def get_email_drafts(
        lead_id: Optional[int] = None,
        loan_id: Optional[int] = None,
        status: Optional[str] = "draft",
        source_type: Optional[str] = None,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        """Get email drafts, optionally filtered by lead/loan/source_type"""
        try:
            query = db.query(EmailDraft).filter(EmailDraft.user_id == current_user.id)

            if status:
                query = query.filter(EmailDraft.status == status)
            if lead_id:
                query = query.filter(EmailDraft.lead_id == lead_id)
            if loan_id:
                query = query.filter(EmailDraft.loan_id == loan_id)
            if source_type:
                query = query.filter(EmailDraft.source_type == source_type)

            drafts = query.order_by(EmailDraft.created_at.desc()).all()

            return {
                "drafts": [
                    {
                        "id": d.id,
                        "lead_id": d.lead_id,
                        "loan_id": d.loan_id,
                        "recipient_email": d.recipient_email,
                        "recipient_name": d.recipient_name,
                        "cc_emails": d.cc_emails or [],
                        "subject": d.subject,
                        "body_html": d.body_html,
                        "body_text": d.body_text,
                        "source_type": d.source_type,
                        "recording_url": d.recording_url,
                        "call_summary": d.call_summary,
                        "action_items": d.action_items or [],
                        "status": d.status,
                        "created_at": d.created_at.isoformat() if d.created_at else None,
                        "updated_at": d.updated_at.isoformat() if d.updated_at else None
                    }
                    for d in drafts
                ],
                "total": len(drafts)
            }
        except Exception as e:
            logger.error(f"Error fetching email drafts: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.get("/api/v1/email-drafts/{draft_id}")
    async def get_email_draft(
        draft_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        """Get a specific email draft"""
        draft = db.query(EmailDraft).filter(
            EmailDraft.id == draft_id,
            EmailDraft.user_id == current_user.id
        ).first()

        if not draft:
            raise HTTPException(status_code=404, detail="Draft not found")

        return {
            "id": draft.id,
            "lead_id": draft.lead_id,
            "loan_id": draft.loan_id,
            "recipient_email": draft.recipient_email,
            "recipient_name": draft.recipient_name,
            "cc_emails": draft.cc_emails or [],
            "subject": draft.subject,
            "body_html": draft.body_html,
            "body_text": draft.body_text,
            "source_type": draft.source_type,
            "source_id": draft.source_id,
            "recording_url": draft.recording_url,
            "call_summary": draft.call_summary,
            "action_items": draft.action_items or [],
            "status": draft.status,
            "created_at": draft.created_at.isoformat() if draft.created_at else None,
            "updated_at": draft.updated_at.isoformat() if draft.updated_at else None
        }

    @app.put("/api/v1/email-drafts/{draft_id}")
    async def update_email_draft(
        draft_id: int,
        update: EmailDraftUpdate,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        """Update an email draft"""
        draft = db.query(EmailDraft).filter(
            EmailDraft.id == draft_id,
            EmailDraft.user_id == current_user.id
        ).first()

        if not draft:
            raise HTTPException(status_code=404, detail="Draft not found")

        if update.recipient_email is not None:
            draft.recipient_email = update.recipient_email
        if update.recipient_name is not None:
            draft.recipient_name = update.recipient_name
        if update.cc_emails is not None:
            draft.cc_emails = update.cc_emails
        if update.subject is not None:
            draft.subject = update.subject
        if update.body_html is not None:
            draft.body_html = update.body_html
        if update.body_text is not None:
            draft.body_text = update.body_text
        if update.status is not None:
            draft.status = update.status
            if update.status == "sent":
                draft.sent_at = datetime.now(timezone.utc)

        db.commit()

        return {"success": True, "message": "Draft updated successfully"}

    @app.delete("/api/v1/email-drafts/{draft_id}")
    async def delete_email_draft(
        draft_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        """Delete (or mark as deleted) an email draft"""
        draft = db.query(EmailDraft).filter(
            EmailDraft.id == draft_id,
            EmailDraft.user_id == current_user.id
        ).first()

        if not draft:
            raise HTTPException(status_code=404, detail="Draft not found")

        draft.status = "deleted"
        db.commit()

        return {"success": True, "message": "Draft deleted successfully"}

    @app.post("/api/v1/email-drafts/{draft_id}/send")
    async def send_email_draft(
        draft_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        """Send an email draft via Microsoft 365"""
        draft = db.query(EmailDraft).filter(
            EmailDraft.id == draft_id,
            EmailDraft.user_id == current_user.id
        ).first()

        if not draft:
            raise HTTPException(status_code=404, detail="Draft not found")

        # Get Microsoft OAuth token
        oauth_record = db.query(MicrosoftOAuthToken).filter(
            MicrosoftOAuthToken.user_id == current_user.id
        ).first()

        if not oauth_record:
            raise HTTPException(status_code=400, detail="Microsoft 365 not connected. Please connect your email first.")

        try:
            # Refresh token if needed
            await refresh_microsoft_token(oauth_record, db)

            # Build the email
            to_recipients = [{"emailAddress": {"address": draft.recipient_email}}]
            cc_recipients = [{"emailAddress": {"address": email}} for email in (draft.cc_emails or [])]

            email_data = {
                "message": {
                    "subject": draft.subject,
                    "body": {
                        "contentType": "HTML",
                        "content": draft.body_html
                    },
                    "toRecipients": to_recipients,
                    "ccRecipients": cc_recipients if cc_recipients else []
                },
                "saveToSentItems": True
            }

            # Send via Microsoft Graph API
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://graph.microsoft.com/v1.0/me/sendMail",
                    headers={
                        "Authorization": f"Bearer {oauth_record.access_token}",
                        "Content-Type": "application/json"
                    },
                    json=email_data,
                    timeout=30.0
                )

                if response.status_code == 202:
                    draft.status = "sent"
                    draft.sent_at = datetime.now(timezone.utc)
                    db.commit()

                    logger.info(f"Email sent successfully from draft {draft_id}")
                    return {"success": True, "message": "Email sent successfully"}
                else:
                    error_detail = response.text
                    logger.error(f"Failed to send email: {response.status_code} - {error_detail}")
                    raise HTTPException(status_code=500, detail=f"Failed to send email: {error_detail}")

        except Exception as e:
            logger.error(f"Error sending email draft: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.post("/api/v1/email-drafts/generate-call-summary")
    async def generate_call_summary_draft(
        request: CallSummaryRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        """Generate an AI-powered call summary email draft from a recording"""
        try:
            # Get lead/loan info for context
            lead_name = request.recipient_name or "Valued Client"
            lead_info = None

            if request.lead_id:
                lead = db.query(Lead).filter(Lead.id == request.lead_id).first()
                if lead:
                    lead_name = lead.name or lead_name
                    lead_info = lead

            # Generate AI summary using Claude
            import anthropic
            client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

            prompt = f"""Generate a professional email summarizing a call with a mortgage client.

    Client Name: {lead_name}
    Meeting Name: {request.meeting_name or 'Call'}
    Call Duration: {request.call_duration_seconds // 60 if request.call_duration_seconds else 'Unknown'} minutes
    Recording Available: Yes

    Please generate:
    1. A professional email subject line
    2. An email body that includes:
       - A warm greeting
       - A summary of what was discussed (use placeholder text since we don't have the actual transcript)
       - Key takeaways and next steps
       - Action items for the recipient (formatted as a checklist)
       - A professional closing

    Format the response as JSON:
    {{
        "subject": "Subject line here",
        "body_html": "<html formatted email body>",
        "body_text": "Plain text version",
        "summary": "Brief summary of the call",
        "action_items": ["Action item 1", "Action item 2", "Action item 3"]
    }}

    Make the email warm but professional, and include placeholder action items like:
    - Review loan documents sent
    - Provide updated income documentation
    - Schedule follow-up call for next week
    - Complete and return disclosure forms"""

            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )

            # Parse the AI response
            ai_response = response.content[0].text

            # Try to parse as JSON
            try:
                # Find JSON in the response
                json_start = ai_response.find('{')
                json_end = ai_response.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    email_data = json.loads(ai_response[json_start:json_end])
                else:
                    raise ValueError("No JSON found in response")
            except json.JSONDecodeError:
                # Fallback: create structured response manually
                email_data = {
                    "subject": f"Summary of Our Call - {request.meeting_name or 'Follow Up'}",
                    "body_html": f"""<p>Dear {lead_name},</p>
    <p>Thank you for taking the time to speak with me today. I wanted to follow up with a summary of our conversation.</p>
    <p><strong>Discussion Summary:</strong></p>
    <p>We discussed your mortgage needs and reviewed the next steps in the process.</p>
    <p><strong>Action Items for You:</strong></p>
    <ul>
    <li>Review the loan documents I'll be sending</li>
    <li>Gather updated income documentation</li>
    <li>Let me know your availability for a follow-up call</li>
    </ul>
    <p>Please don't hesitate to reach out if you have any questions.</p>
    <p>Best regards</p>""",
                    "body_text": f"Dear {lead_name},\n\nThank you for taking the time to speak with me today...",
                    "summary": "Follow-up from our call",
                    "action_items": ["Review loan documents", "Provide updated income documentation", "Schedule follow-up"]
                }

            # Create the draft
            new_draft = EmailDraft(
                user_id=current_user.id,
                lead_id=request.lead_id,
                loan_id=request.loan_id,
                recipient_email=request.recipient_email,
                recipient_name=lead_name,
                cc_emails=[],
                subject=email_data.get("subject", f"Summary of Our Call - {request.meeting_name or 'Follow Up'}"),
                body_html=email_data.get("body_html", ""),
                body_text=email_data.get("body_text", ""),
                source_type="call_recording",
                recording_url=request.recording_url,
                call_summary=email_data.get("summary", ""),
                action_items=email_data.get("action_items", []),
                status="draft"
            )
            db.add(new_draft)
            db.commit()
            db.refresh(new_draft)

            logger.info(f"Generated call summary draft {new_draft.id} for lead {request.lead_id}")

            return {
                "success": True,
                "draft_id": new_draft.id,
                "subject": new_draft.subject,
                "message": "Call summary email draft created successfully"
            }

        except Exception as e:
            logger.error(f"Error generating call summary: {e}")
            db.rollback()
            raise HTTPException(status_code=500, detail="Internal server error")

    # Return functions that need to be exported for backward compatibility
    return {
        'generate_email_signature_html': generate_email_signature_html,
    }
