"""
Pre-Approval Letter Settings Routes
Configure the pre-approval letter content and branding
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
from io import BytesIO
import logging
import json

from database import get_db, Base

# PDF Generation imports
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

def _get_current_user():
    """Lazy import auth dependency for router-level protection."""
    from auth.dependencies import get_current_user_flexible
    return get_current_user_flexible

router = APIRouter(
    prefix="/api/v1/settings", tags=["Settings"],
    dependencies=[Depends(_get_current_user())],
)


# Database Model
class PreApprovalLetterSettings(Base):
    """Pre-approval letter configuration settings"""
    __tablename__ = "pre_approval_letter_settings"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=True, index=True)

    # Company Information
    company_name = Column(String(255), default="")
    company_address = Column(Text, default="")
    company_phone = Column(String(50), default="")
    company_nmls = Column(String(50), default="")

    # Letter Content
    letter_header = Column(String(255), default="Pre-Approval Letter")
    opening_paragraph = Column(Text, default="This letter is to confirm that the below-named borrower(s) have been pre-approved for a mortgage loan based on a preliminary review of their credit and financial information.")
    conditions_intro = Column(String(500), default="This pre-approval is subject to the following conditions:")
    default_conditions = Column(Text, default='["Verification of employment and income","Satisfactory property appraisal","Clear title search","Verification of assets and funds for closing","No material changes to financial condition"]')  # Stored as JSON string
    closing_paragraph = Column(Text, default="This pre-approval is valid for 90 days from the date of this letter. Please note that this is not a commitment to lend and is subject to final underwriting approval.")
    disclaimer = Column(Text, default="This pre-approval letter is based on the information provided by the applicant and is subject to verification. Final loan approval is contingent upon satisfactory completion of all underwriting requirements.")

    # Display Options
    show_nmls = Column(Boolean, default=True)
    show_equal_housing = Column(Boolean, default=True)

    # Metadata
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


# Pydantic Schemas
class PreApprovalLetterSettingsUpdate(BaseModel):
    company_name: Optional[str] = None
    company_address: Optional[str] = None
    company_phone: Optional[str] = None
    company_nmls: Optional[str] = None
    letter_header: Optional[str] = None
    opening_paragraph: Optional[str] = None
    conditions_intro: Optional[str] = None
    default_conditions: Optional[List[str]] = None
    closing_paragraph: Optional[str] = None
    disclaimer: Optional[str] = None
    show_nmls: Optional[bool] = None
    show_equal_housing: Optional[bool] = None


class PreApprovalLetterSettingsResponse(BaseModel):
    id: int
    company_name: str
    company_address: str
    company_phone: str
    company_nmls: str
    letter_header: str
    opening_paragraph: str
    conditions_intro: str
    default_conditions: List[str]
    closing_paragraph: str
    disclaimer: str
    show_nmls: bool
    show_equal_housing: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Helper function to get or create settings
def get_or_create_settings(db: Session, organization_id: int = None) -> PreApprovalLetterSettings:
    """Get existing settings or create default ones, scoped by organization"""
    query = db.query(PreApprovalLetterSettings)
    if organization_id is not None:
        query = query.filter(PreApprovalLetterSettings.organization_id == organization_id)
    settings = query.first()
    if not settings:
        settings = PreApprovalLetterSettings(organization_id=organization_id)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


def parse_conditions(settings: PreApprovalLetterSettings) -> List[str]:
    """Parse the default_conditions JSON string into a list"""
    if not settings.default_conditions:
        return []
    try:
        if isinstance(settings.default_conditions, list):
            return settings.default_conditions
        return json.loads(settings.default_conditions)
    except (json.JSONDecodeError, TypeError):
        return []


def serialize_conditions(conditions: List[str]) -> str:
    """Serialize the conditions list to JSON string"""
    return json.dumps(conditions)


# Routes
@router.get("/pre-approval-letter")
async def get_pre_approval_letter_settings(db: Session = Depends(get_db)):
    """Get current pre-approval letter settings"""
    settings = get_or_create_settings(db)

    return {
        "id": settings.id,
        "company_name": settings.company_name or "",
        "company_address": settings.company_address or "",
        "company_phone": settings.company_phone or "",
        "company_nmls": settings.company_nmls or "",
        "letter_header": settings.letter_header or "Pre-Approval Letter",
        "opening_paragraph": settings.opening_paragraph or "",
        "conditions_intro": settings.conditions_intro or "",
        "default_conditions": parse_conditions(settings),
        "closing_paragraph": settings.closing_paragraph or "",
        "disclaimer": settings.disclaimer or "",
        "show_nmls": settings.show_nmls if settings.show_nmls is not None else True,
        "show_equal_housing": settings.show_equal_housing if settings.show_equal_housing is not None else True,
        "created_at": settings.created_at,
        "updated_at": settings.updated_at
    }


@router.post("/pre-approval-letter")
async def update_pre_approval_letter_settings(
    updates: PreApprovalLetterSettingsUpdate,
    db: Session = Depends(get_db)
):
    """Update pre-approval letter settings"""
    settings = get_or_create_settings(db)

    update_data = updates.dict(exclude_unset=True)
    _protected = {'id', 'organization_id', 'created_at', 'updated_at'}

    for field, value in update_data.items():
        if field not in _protected:
            if field == "default_conditions":
                # Serialize conditions list to JSON string
                setattr(settings, field, serialize_conditions(value))
            else:
                setattr(settings, field, value)

    settings.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(settings)

    logger.info(f"Pre-approval letter settings updated: {list(update_data.keys())}")

    return {
        "id": settings.id,
        "company_name": settings.company_name or "",
        "company_address": settings.company_address or "",
        "company_phone": settings.company_phone or "",
        "company_nmls": settings.company_nmls or "",
        "letter_header": settings.letter_header or "Pre-Approval Letter",
        "opening_paragraph": settings.opening_paragraph or "",
        "conditions_intro": settings.conditions_intro or "",
        "default_conditions": parse_conditions(settings),
        "closing_paragraph": settings.closing_paragraph or "",
        "disclaimer": settings.disclaimer or "",
        "show_nmls": settings.show_nmls if settings.show_nmls is not None else True,
        "show_equal_housing": settings.show_equal_housing if settings.show_equal_housing is not None else True,
        "created_at": settings.created_at,
        "updated_at": settings.updated_at
    }


def generate_pre_approval_letter_html(settings: PreApprovalLetterSettings, sample_data: dict = None) -> str:
    """Generate HTML for a pre-approval letter"""

    # Use sample data or defaults
    if sample_data is None:
        sample_data = {
            "borrower_names": "John Smith & Jane Smith",
            "property_address": "123 Main Street, Anytown, CA 90210",
            "pre_approved_amount": "$450,000",
            "loan_type": "Conventional 30-Year Fixed",
            "lo_name": "Tim Loss",
            "lo_title": "Senior Loan Officer",
            "lo_nmls": "123456",
            "lo_phone": "(555) 123-4567",
            "lo_email": "tim@perenniaai.com"
        }

    conditions = parse_conditions(settings)
    conditions_html = "".join([f"<li style='margin-bottom: 8px;'>{c}</li>" for c in conditions if c])

    letter_date = datetime.now().strftime("%B %d, %Y")

    html = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{
            font-family: 'Georgia', 'Times New Roman', serif;
            line-height: 1.8;
            color: #333;
            max-width: 800px;
            margin: 0 auto;
            padding: 40px;
            background: #fff;
        }}
        .letterhead {{
            text-align: center;
            margin-bottom: 40px;
            padding-bottom: 20px;
            border-bottom: 2px solid #1e40af;
        }}
        .company-name {{
            font-size: 24px;
            font-weight: bold;
            color: #1e40af;
            margin: 0;
        }}
        .company-info {{
            color: #666;
            font-size: 14px;
            margin-top: 8px;
        }}
        .nmls-badge {{
            font-size: 12px;
            color: #888;
            margin-top: 4px;
        }}
        .letter-date {{
            text-align: right;
            color: #666;
            margin-bottom: 30px;
        }}
        .letter-header {{
            text-align: center;
            font-size: 22px;
            font-weight: bold;
            color: #1e40af;
            margin: 30px 0;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        .borrower-info {{
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 20px;
            margin: 24px 0;
        }}
        .borrower-info p {{
            margin: 8px 0;
        }}
        .borrower-info strong {{
            color: #1e40af;
            display: inline-block;
            width: 180px;
        }}
        .amount-highlight {{
            font-size: 24px;
            font-weight: bold;
            color: #059669;
        }}
        .paragraph {{
            text-align: justify;
            margin: 20px 0;
        }}
        .conditions {{
            margin: 24px 0;
        }}
        .conditions-intro {{
            margin-bottom: 12px;
        }}
        .conditions ul {{
            margin: 0;
            padding-left: 24px;
        }}
        .signature-block {{
            margin-top: 50px;
        }}
        .signature-line {{
            border-top: 1px solid #333;
            width: 250px;
            margin-top: 60px;
            padding-top: 8px;
        }}
        .lo-name {{
            font-weight: bold;
            font-size: 16px;
        }}
        .lo-title {{
            color: #666;
            font-size: 14px;
        }}
        .lo-nmls {{
            font-size: 12px;
            color: #888;
        }}
        .lo-contact {{
            font-size: 14px;
            margin-top: 8px;
        }}
        .disclaimer {{
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #e2e8f0;
            font-size: 11px;
            color: #888;
            font-style: italic;
        }}
        .footer {{
            margin-top: 30px;
            text-align: center;
            font-size: 12px;
            color: #888;
        }}
        .equal-housing {{
            margin-top: 16px;
            font-size: 11px;
        }}
    </style>
</head>
<body>
    <div class="letterhead">
        <div class="company-name">{settings.company_name or '[Company Name]'}</div>
        <div class="company-info">{settings.company_address or '[Company Address]'}</div>
        <div class="company-info">{settings.company_phone or '[Phone Number]'}</div>
        {'<div class="nmls-badge">NMLS #' + (settings.company_nmls or '[NMLS]') + '</div>' if settings.show_nmls else ''}
    </div>

    <div class="letter-date">{letter_date}</div>

    <div class="letter-header">{settings.letter_header or 'Pre-Approval Letter'}</div>

    <div class="borrower-info">
        <p><strong>Borrower(s):</strong> {sample_data['borrower_names']}</p>
        <p><strong>Property Address:</strong> {sample_data['property_address']}</p>
        <p><strong>Pre-Approved Amount:</strong> <span class="amount-highlight">{sample_data['pre_approved_amount']}</span></p>
        <p><strong>Loan Type:</strong> {sample_data['loan_type']}</p>
    </div>

    <div class="paragraph">
        {settings.opening_paragraph or 'This letter confirms pre-approval for a mortgage loan.'}
    </div>

    <div class="conditions">
        <div class="conditions-intro">{settings.conditions_intro or 'This pre-approval is subject to the following conditions:'}</div>
        <ul>
            {conditions_html}
        </ul>
    </div>

    <div class="paragraph">
        {settings.closing_paragraph or 'This pre-approval is valid for 90 days.'}
    </div>

    <div class="signature-block">
        <p>Sincerely,</p>
        <div class="signature-line">
            <div class="lo-name">{sample_data['lo_name']}</div>
            <div class="lo-title">{sample_data['lo_title']}</div>
            <div class="lo-nmls">NMLS #{sample_data['lo_nmls']}</div>
            <div class="lo-contact">{sample_data['lo_phone']}</div>
            <div class="lo-contact">{sample_data['lo_email']}</div>
        </div>
    </div>

    <div class="disclaimer">
        {settings.disclaimer or 'This pre-approval is subject to verification.'}
    </div>

    <div class="footer">
        {'<div class="equal-housing">Equal Housing Lender</div>' if settings.show_equal_housing else ''}
    </div>
</body>
</html>
"""
    return html


def generate_pre_approval_letter_pdf(settings: PreApprovalLetterSettings, sample_data: dict = None) -> bytes:
    """Generate PDF for a pre-approval letter using reportlab"""

    # Use sample data or defaults
    if sample_data is None:
        sample_data = {
            "borrower_names": "John Smith & Jane Smith",
            "property_address": "123 Main Street, Anytown, CA 90210",
            "pre_approved_amount": "$450,000",
            "loan_type": "Conventional 30-Year Fixed",
            "lo_name": "Tim Loss",
            "lo_title": "Senior Loan Officer",
            "lo_nmls": "123456",
            "lo_phone": "(555) 123-4567",
            "lo_email": "tim@perenniaai.com"
        }

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.75*inch,
        leftMargin=0.75*inch,
        topMargin=0.5*inch,
        bottomMargin=0.5*inch
    )

    # Create custom styles
    styles = getSampleStyleSheet()

    # Company name style
    company_style = ParagraphStyle(
        'CompanyName',
        parent=styles['Heading1'],
        fontSize=20,
        textColor=colors.HexColor('#1e40af'),
        alignment=TA_CENTER,
        spaceAfter=6
    )

    # Company info style
    company_info_style = ParagraphStyle(
        'CompanyInfo',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#666666'),
        alignment=TA_CENTER,
        spaceAfter=2
    )

    # NMLS style
    nmls_style = ParagraphStyle(
        'NMLS',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.HexColor('#888888'),
        alignment=TA_CENTER,
        spaceAfter=12
    )

    # Date style
    date_style = ParagraphStyle(
        'Date',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#666666'),
        alignment=TA_RIGHT,
        spaceAfter=20
    )

    # Letter header style
    header_style = ParagraphStyle(
        'LetterHeader',
        parent=styles['Heading1'],
        fontSize=16,
        textColor=colors.HexColor('#1e40af'),
        alignment=TA_CENTER,
        spaceAfter=20,
        spaceBefore=10
    )

    # Body text style
    body_style = ParagraphStyle(
        'BodyText',
        parent=styles['Normal'],
        fontSize=11,
        leading=16,
        alignment=TA_JUSTIFY,
        spaceAfter=12
    )

    # Label style for borrower info
    label_style = ParagraphStyle(
        'Label',
        parent=styles['Normal'],
        fontSize=11,
        textColor=colors.HexColor('#1e40af'),
        fontName='Helvetica-Bold'
    )

    # Amount highlight style
    amount_style = ParagraphStyle(
        'Amount',
        parent=styles['Normal'],
        fontSize=14,
        textColor=colors.HexColor('#059669'),
        fontName='Helvetica-Bold'
    )

    # Conditions intro style
    conditions_intro_style = ParagraphStyle(
        'ConditionsIntro',
        parent=styles['Normal'],
        fontSize=11,
        spaceAfter=8
    )

    # Bullet style
    bullet_style = ParagraphStyle(
        'Bullet',
        parent=styles['Normal'],
        fontSize=11,
        leftIndent=20,
        spaceAfter=4
    )

    # Signature style
    signature_style = ParagraphStyle(
        'Signature',
        parent=styles['Normal'],
        fontSize=11,
        spaceAfter=4
    )

    # Disclaimer style
    disclaimer_style = ParagraphStyle(
        'Disclaimer',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.HexColor('#888888'),
        alignment=TA_JUSTIFY,
        fontName='Helvetica-Oblique',
        spaceBefore=20
    )

    # Footer style
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.HexColor('#888888'),
        alignment=TA_CENTER,
        spaceBefore=15
    )

    # Build document content
    story = []

    # Letterhead
    story.append(Paragraph(settings.company_name or '[Company Name]', company_style))
    story.append(Paragraph(settings.company_address or '[Company Address]', company_info_style))
    story.append(Paragraph(settings.company_phone or '[Phone Number]', company_info_style))

    if settings.show_nmls:
        story.append(Paragraph(f"NMLS #{settings.company_nmls or '[NMLS]'}", nmls_style))

    # Horizontal line
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#1e40af'), spaceAfter=20))

    # Date
    letter_date = datetime.now().strftime("%B %d, %Y")
    story.append(Paragraph(letter_date, date_style))

    # Letter header
    story.append(Paragraph(settings.letter_header or 'PRE-APPROVAL LETTER', header_style))

    # Borrower information box
    borrower_data = [
        [Paragraph("<b>Borrower(s):</b>", label_style), Paragraph(sample_data['borrower_names'], body_style)],
        [Paragraph("<b>Property Address:</b>", label_style), Paragraph(sample_data['property_address'], body_style)],
        [Paragraph("<b>Pre-Approved Amount:</b>", label_style), Paragraph(f"<b>{sample_data['pre_approved_amount']}</b>", amount_style)],
        [Paragraph("<b>Loan Type:</b>", label_style), Paragraph(sample_data['loan_type'], body_style)],
    ]

    borrower_table = Table(borrower_data, colWidths=[1.8*inch, 4.5*inch])
    borrower_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#e2e8f0')),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(borrower_table)
    story.append(Spacer(1, 20))

    # Opening paragraph
    opening = settings.opening_paragraph or 'This letter confirms pre-approval for a mortgage loan.'
    story.append(Paragraph(opening, body_style))

    # Conditions
    conditions_intro = settings.conditions_intro or 'This pre-approval is subject to the following conditions:'
    story.append(Paragraph(conditions_intro, conditions_intro_style))

    conditions = parse_conditions(settings)
    for condition in conditions:
        if condition:
            story.append(Paragraph(f"• {condition}", bullet_style))

    story.append(Spacer(1, 12))

    # Closing paragraph
    closing = settings.closing_paragraph or 'This pre-approval is valid for 90 days.'
    story.append(Paragraph(closing, body_style))

    # Signature block
    story.append(Spacer(1, 30))
    story.append(Paragraph("Sincerely,", signature_style))
    story.append(Spacer(1, 40))
    story.append(HRFlowable(width=2.5*inch, thickness=1, color=colors.black, spaceAfter=6))
    story.append(Paragraph(f"<b>{sample_data['lo_name']}</b>", signature_style))
    story.append(Paragraph(sample_data['lo_title'], signature_style))
    story.append(Paragraph(f"NMLS #{sample_data['lo_nmls']}", ParagraphStyle('SmallText', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor('#888888'))))
    story.append(Paragraph(sample_data['lo_phone'], signature_style))
    story.append(Paragraph(sample_data['lo_email'], signature_style))

    # Disclaimer
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#e2e8f0'), spaceBefore=30, spaceAfter=10))
    disclaimer = settings.disclaimer or 'This pre-approval is subject to verification.'
    story.append(Paragraph(disclaimer, disclaimer_style))

    # Equal Housing
    if settings.show_equal_housing:
        story.append(Paragraph("Equal Housing Lender", footer_style))

    # Build PDF
    doc.build(story)

    # Get PDF bytes
    pdf_bytes = buffer.getvalue()
    buffer.close()

    return pdf_bytes


class TestEmailRequest(BaseModel):
    to_email: str
    borrower_names: Optional[str] = "John Smith & Jane Smith"
    property_address: Optional[str] = "123 Main Street, Anytown, CA 90210"
    pre_approved_amount: Optional[str] = "$450,000"
    loan_type: Optional[str] = "Conventional 30-Year Fixed"


@router.post("/pre-approval-letter/send-test")
async def send_test_pre_approval_letter(
    request: TestEmailRequest,
    db: Session = Depends(get_db)
):
    """Send a test pre-approval letter PDF attachment to the specified email"""
    from email_service import EmailService

    settings = get_or_create_settings(db)

    sample_data = {
        "borrower_names": request.borrower_names,
        "property_address": request.property_address,
        "pre_approved_amount": request.pre_approved_amount,
        "loan_type": request.loan_type,
        "lo_name": "Tim Loss",
        "lo_title": "Senior Loan Officer",
        "lo_nmls": "123456",
        "lo_phone": "(555) 123-4567",
        "lo_email": "tim@perenniaai.com"
    }

    # Generate PDF
    pdf_bytes = generate_pre_approval_letter_pdf(settings, sample_data)

    # Create a clean filename from borrower names
    borrower_filename = sample_data['borrower_names'].replace(' & ', '_').replace(' ', '_')
    pdf_filename = f"Pre_Approval_Letter_{borrower_filename}.pdf"

    # Email body (simple notification that PDF is attached)
    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
        }}
        .header {{
            background: linear-gradient(135deg, #1e40af 0%, #3b82f6 100%);
            color: white;
            padding: 30px;
            border-radius: 12px 12px 0 0;
            text-align: center;
        }}
        .header h1 {{
            margin: 0;
            font-size: 24px;
        }}
        .content {{
            background: #fff;
            border: 1px solid #e5e7eb;
            border-top: none;
            border-radius: 0 0 12px 12px;
            padding: 30px;
        }}
        .info-box {{
            background: #f0f9ff;
            border-left: 4px solid #3b82f6;
            padding: 16px;
            margin: 20px 0;
            border-radius: 4px;
        }}
        .attachment-note {{
            background: #ecfdf5;
            border: 1px solid #10b981;
            border-radius: 8px;
            padding: 16px;
            margin: 20px 0;
            text-align: center;
        }}
        .attachment-note .icon {{
            font-size: 32px;
            margin-bottom: 8px;
        }}
        .footer {{
            text-align: center;
            color: #6b7280;
            font-size: 12px;
            margin-top: 20px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Pre-Approval Letter</h1>
    </div>
    <div class="content">
        <p>Hello,</p>
        <p>Please find attached the pre-approval letter for the following borrower(s):</p>

        <div class="info-box">
            <p><strong>Borrower(s):</strong> {sample_data['borrower_names']}</p>
            <p><strong>Property:</strong> {sample_data['property_address']}</p>
            <p><strong>Pre-Approved Amount:</strong> {sample_data['pre_approved_amount']}</p>
            <p><strong>Loan Type:</strong> {sample_data['loan_type']}</p>
        </div>

        <div class="attachment-note">
            <div class="icon">📎</div>
            <strong>PDF Attachment</strong><br>
            <span style="color: #6b7280;">{pdf_filename}</span>
        </div>

        <p>If you have any questions, please don't hesitate to reach out.</p>

        <p>
            Best regards,<br>
            <strong>{sample_data['lo_name']}</strong><br>
            {sample_data['lo_title']}<br>
            NMLS #{sample_data['lo_nmls']}<br>
            {sample_data['lo_phone']}<br>
            {sample_data['lo_email']}
        </p>
    </div>
    <div class="footer">
        <p>This email was sent from Perennia AI CRM</p>
        {f'<p>Equal Housing Lender</p>' if settings.show_equal_housing else ''}
    </div>
</body>
</html>
"""

    plain_text = f"""
Pre-Approval Letter

Borrower(s): {sample_data['borrower_names']}
Property: {sample_data['property_address']}
Pre-Approved Amount: {sample_data['pre_approved_amount']}
Loan Type: {sample_data['loan_type']}

Please see the attached PDF for the full pre-approval letter.

Best regards,
{sample_data['lo_name']}
{sample_data['lo_title']}
NMLS #{sample_data['lo_nmls']}
{sample_data['lo_phone']}
{sample_data['lo_email']}
"""

    try:
        email_service = EmailService()

        # Create attachment
        attachments = [{
            'content': pdf_bytes,
            'filename': pdf_filename,
            'type': 'application/pdf'
        }]

        success = email_service.send_html_email(
            to_email=request.to_email,
            subject=f"Pre-Approval Letter - {sample_data['borrower_names']}",
            html_body=html_content,
            plain_text_body=plain_text,
            attachments=attachments
        )

        if success:
            logger.info(f"Test pre-approval letter PDF sent to {request.to_email}")
            return {
                "success": True,
                "message": f"Pre-approval letter PDF sent to {request.to_email}",
                "filename": pdf_filename
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to send email")

    except Exception as e:
        logger.error(f"Failed to send test pre-approval letter: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
