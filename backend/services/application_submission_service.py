"""
Application Submission Service
Handles PDF generation for consent documents and Fannie Mae 3.4 file creation
"""
import os
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime
from io import BytesIO
from typing import Dict, Any, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY


class ApplicationSubmissionService:
    """Service for generating submission documents"""

    def __init__(self):
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    def _setup_custom_styles(self):
        """Set up custom paragraph styles"""
        self.styles.add(ParagraphStyle(
            name='DocumentTitle',
            parent=self.styles['Heading1'],
            fontSize=18,
            spaceAfter=20,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#1f2937')
        ))
        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=self.styles['Heading2'],
            fontSize=14,
            spaceBefore=15,
            spaceAfter=10,
            textColor=colors.HexColor('#218D8D')
        ))
        self.styles.add(ParagraphStyle(
            name='BodyText',
            parent=self.styles['Normal'],
            fontSize=10,
            leading=14,
            alignment=TA_JUSTIFY,
            spaceAfter=10
        ))
        self.styles.add(ParagraphStyle(
            name='SignatureText',
            parent=self.styles['Normal'],
            fontSize=10,
            spaceBefore=20,
            spaceAfter=5
        ))

    def generate_econsent_pdf(self, borrower_data: Dict[str, Any]) -> bytes:
        """Generate E-Consent PDF with borrower signature"""
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=0.75*inch,
            leftMargin=0.75*inch,
            topMargin=0.75*inch,
            bottomMargin=0.75*inch
        )

        story = []

        # Title
        story.append(Paragraph("E-Consent Documentation", self.styles['DocumentTitle']))
        story.append(Spacer(1, 20))

        # Intro
        story.append(Paragraph(
            "To use electronic signatures and receive documents electronically in connection with your use of this "
            "platform, you must read and consent to the terms outlined in this document, which require your ability to "
            "access and retain electronic documents.",
            self.styles['BodyText']
        ))

        story.append(Paragraph(
            "This eConsent, if you provide it, applies to your use of this Platform on any Access Device, including a "
            "desktop, laptop, tablet, mobile, or any other electronic device, and to any Document, including loan "
            "documents, disclosures (initial disclosures, pre-close disclosures, closing disclosures), records, and servicing "
            "notices, and any other loan documents that we provide to you in electronic form.",
            self.styles['BodyText']
        ))

        story.append(Paragraph(
            "If you provide eConsent, we will be able to provide electronic Documents to you within this platform, in "
            "other portals, and/or through other methods we may use for delivery of electronic Documents. With Your "
            "eConsent, You will also be able to sign and authorize these Documents electronically, rather than on paper.",
            self.styles['BodyText']
        ))

        # Your Consent Section
        story.append(Paragraph("Your Consent", self.styles['SectionHeader']))
        story.append(Paragraph(
            "Your consent to participate in this transaction electronically will apply to all Loan Documents for the "
            "applicable loans for which You are applying. By providing Your consent, We will conduct this transaction "
            "electronically, instead of providing You with the Loan Documents in paper form.",
            self.styles['BodyText']
        ))
        story.append(Paragraph(
            "If a document related to Your loan is not available in electronic form, a paper copy will be provided to "
            "You free of charge. Conducting this transaction electronically is an option. If You choose not to receive "
            "Documents electronically, paper Documents will be mailed to You.",
            self.styles['BodyText']
        ))

        # Withdrawal of Consent
        story.append(Paragraph("Withdrawal of Consent", self.styles['SectionHeader']))
        story.append(Paragraph(
            "You have the right to withdraw Your consent at any time. By declining or revoking Your consent to "
            "receive Documents electronically, We will provide You with the Documents in paper form. "
            "You will not be required to pay a fee for withdrawing consent and receiving paper copies of the Documents.",
            self.styles['BodyText']
        ))

        # System Requirements
        story.append(Paragraph("System Requirements", self.styles['SectionHeader']))
        story.append(Paragraph(
            "In order to receive Documents electronically, You must have a computer with Internet access and an "
            "Internet email account and address; an Internet browser using 128-bit encryption or higher, Adobe "
            "Acrobat 7.0 or higher, SSL encryption and access to a printer or the ability to download information in "
            "order to keep copies of Your Documents electronically for Your records.",
            self.styles['BodyText']
        ))

        story.append(Spacer(1, 30))

        # Signature Section
        story.append(Paragraph("BORROWER ACKNOWLEDGEMENT AND SIGNATURE", self.styles['SectionHeader']))
        story.append(Spacer(1, 15))

        # Borrower info table
        borrower_name = f"{borrower_data.get('firstName', '')} {borrower_data.get('lastName', '')}"
        consent_date = datetime.now().strftime("%B %d, %Y at %I:%M %p")

        signature_data = [
            ["Borrower Name:", borrower_name],
            ["Email:", borrower_data.get('email', '')],
            ["Date of Consent:", consent_date],
            ["IP Address:", borrower_data.get('ipAddress', 'N/A')],
            ["Consent Status:", "I AGREE - Electronic Consent Provided"],
        ]

        signature_table = Table(signature_data, colWidths=[2*inch, 4.5*inch])
        signature_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e6f7f7')),
        ]))
        story.append(signature_table)

        story.append(Spacer(1, 20))

        # Electronic signature line
        story.append(Paragraph(
            f"<b>Electronic Signature:</b> /s/ {borrower_name}",
            self.styles['SignatureText']
        ))
        story.append(Paragraph(
            f"<i>This document was electronically signed on {consent_date}</i>",
            self.styles['SignatureText']
        ))

        doc.build(story)
        return buffer.getvalue()

    def generate_credit_auth_pdf(self, borrower_data: Dict[str, Any]) -> bytes:
        """Generate Credit Authorization PDF with borrower signature"""
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=0.75*inch,
            leftMargin=0.75*inch,
            topMargin=0.75*inch,
            bottomMargin=0.75*inch
        )

        story = []

        # Title
        story.append(Paragraph("Credit Authorization", self.styles['DocumentTitle']))
        story.append(Spacer(1, 20))

        # Intro
        story.append(Paragraph(
            "Your credit information will help us understand more about your personal and financial background and "
            "ensure we give you the most accurate mortgage options. The following authorization has been provided:",
            self.styles['BodyText']
        ))

        story.append(Spacer(1, 15))

        # Authorization text box
        auth_text = (
            "I authorize my Lender to perform a credit check, via either a soft or hard pull of my credit; I understand this "
            "may affect my credit score. I acknowledge that any owner of a completed loan, its servicers, successors and "
            "assigns, may verify or re-verify any information contained in this form or obtain any information or data "
            "relating to a completed loan, for any legitimate purpose, through any source, including a source named in this "
            "form or a consumer reporting agency."
        )

        # Create a styled box for the authorization
        auth_style = ParagraphStyle(
            name='AuthBox',
            parent=self.styles['Normal'],
            fontSize=11,
            leading=16,
            alignment=TA_JUSTIFY,
            borderPadding=15,
            borderColor=colors.HexColor('#3b82f6'),
            borderWidth=2,
            backColor=colors.HexColor('#eff6ff'),
        )

        story.append(Paragraph(auth_text, self.styles['BodyText']))

        story.append(Spacer(1, 40))

        # Signature Section
        story.append(Paragraph("BORROWER ACKNOWLEDGEMENT AND SIGNATURE", self.styles['SectionHeader']))
        story.append(Spacer(1, 15))

        # Borrower info table
        borrower_name = f"{borrower_data.get('firstName', '')} {borrower_data.get('lastName', '')}"
        auth_date = datetime.now().strftime("%B %d, %Y at %I:%M %p")

        signature_data = [
            ["Borrower Name:", borrower_name],
            ["Email:", borrower_data.get('email', '')],
            ["Date of Authorization:", auth_date],
            ["IP Address:", borrower_data.get('ipAddress', 'N/A')],
            ["Authorization Status:", "I AUTHORIZE - Credit Check Authorized"],
        ]

        signature_table = Table(signature_data, colWidths=[2*inch, 4.5*inch])
        signature_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#eff6ff')),
        ]))
        story.append(signature_table)

        story.append(Spacer(1, 20))

        # Electronic signature line
        story.append(Paragraph(
            f"<b>Electronic Signature:</b> /s/ {borrower_name}",
            self.styles['SignatureText']
        ))
        story.append(Paragraph(
            f"<i>This document was electronically signed on {auth_date}</i>",
            self.styles['SignatureText']
        ))

        doc.build(story)
        return buffer.getvalue()

    def generate_fannie_mae_34(self, application_data: Dict[str, Any]) -> str:
        """
        Generate Fannie Mae 3.4 file (MISMO 2.3.1 format)
        This is a simplified version - production would need full MISMO compliance
        """
        # Root element
        root = ET.Element("LOAN_APPLICATION")
        root.set("MISMOVersionID", "2.3.1")

        # Application header
        app_header = ET.SubElement(root, "APPLICATION")
        app_header.set("ApplicationReceivedDate", datetime.now().strftime("%Y-%m-%d"))

        # Borrower information
        borrower = ET.SubElement(root, "BORROWER")
        borrower.set("BorrowerID", "Borrower01")

        # Name
        name = ET.SubElement(borrower, "NAME")
        ET.SubElement(name, "FirstName").text = application_data.get('firstName', '')
        ET.SubElement(name, "MiddleName").text = application_data.get('middleName', '')
        ET.SubElement(name, "LastName").text = application_data.get('lastName', '')

        # Contact info
        contact = ET.SubElement(borrower, "CONTACT_INFORMATION")
        ET.SubElement(contact, "Email").text = application_data.get('email', '')
        ET.SubElement(contact, "HomePhone").text = application_data.get('phone', '')

        # Current address
        residence = ET.SubElement(borrower, "RESIDENCE")
        residence.set("ResidencyType", "Current")
        address = ET.SubElement(residence, "ADDRESS")
        ET.SubElement(address, "StreetAddress").text = application_data.get('currentAddress', {}).get('street', '')
        ET.SubElement(address, "City").text = application_data.get('currentAddress', {}).get('city', '')
        ET.SubElement(address, "State").text = application_data.get('currentAddress', {}).get('state', '')
        ET.SubElement(address, "PostalCode").text = application_data.get('currentAddress', {}).get('zip', '')

        # Employment
        if application_data.get('employment'):
            emp = application_data['employment']
            employment = ET.SubElement(borrower, "EMPLOYMENT")
            employment.set("EmploymentCurrentIndicator", "Y")
            ET.SubElement(employment, "EmployerName").text = emp.get('employerName', '')
            ET.SubElement(employment, "EmploymentStartDate").text = emp.get('startDate', '')
            ET.SubElement(employment, "EmploymentMonthlyIncomeAmount").text = str(emp.get('monthlyIncome', 0))
            ET.SubElement(employment, "EmploymentPositionDescription").text = emp.get('jobTitle', '')

        # Income
        income = ET.SubElement(borrower, "INCOME")
        base_income = ET.SubElement(income, "INCOME_ITEM")
        base_income.set("IncomeType", "Base")
        ET.SubElement(base_income, "Amount").text = str(application_data.get('annualIncome', 0))

        # Assets
        assets = ET.SubElement(borrower, "ASSETS")
        for asset_type, amount in application_data.get('assets', {}).items():
            if amount and float(amount) > 0:
                asset = ET.SubElement(assets, "ASSET")
                asset.set("AssetType", asset_type.upper())
                ET.SubElement(asset, "CashOrMarketValue").text = str(amount)

        # Declarations
        declarations = ET.SubElement(borrower, "DECLARATIONS")
        decl_data = application_data.get('declarations', {})
        ET.SubElement(declarations, "CitizenshipResidencyType").text = decl_data.get('citizenship', 'USCitizen')
        ET.SubElement(declarations, "IntentToOccupyType").text = "Y" if decl_data.get('occupancy') == 'primary' else "N"
        ET.SubElement(declarations, "FirstTimeHomebuyerIndicator").text = "Y" if decl_data.get('firstTimeBuyer') == 'yes' else "N"

        # Property information
        property_elem = ET.SubElement(root, "PROPERTY")
        property_data = application_data.get('property', {})

        prop_address = ET.SubElement(property_elem, "ADDRESS")
        ET.SubElement(prop_address, "StreetAddress").text = property_data.get('street', '')
        ET.SubElement(prop_address, "City").text = property_data.get('city', '')
        ET.SubElement(prop_address, "State").text = property_data.get('state', '')
        ET.SubElement(prop_address, "PostalCode").text = property_data.get('zip', '')
        ET.SubElement(prop_address, "County").text = property_data.get('county', '')

        property_detail = ET.SubElement(property_elem, "PROPERTY_DETAIL")
        ET.SubElement(property_detail, "PropertyType").text = property_data.get('propertyType', 'SingleFamily')
        ET.SubElement(property_detail, "PropertyUsageType").text = property_data.get('occupancy', 'PrimaryResidence')

        # Loan information
        loan = ET.SubElement(root, "LOAN")
        loan_data = application_data.get('loan', {})

        ET.SubElement(loan, "LoanPurposeType").text = loan_data.get('purpose', 'Purchase')
        ET.SubElement(loan, "BaseLoanAmount").text = str(loan_data.get('loanAmount', 0))
        ET.SubElement(loan, "LoanAmortizationType").text = loan_data.get('amortizationType', 'Fixed')
        ET.SubElement(loan, "LoanAmortizationTermMonths").text = str(loan_data.get('termMonths', 360))

        # Purchase info
        if loan_data.get('purpose') == 'Purchase':
            purchase = ET.SubElement(loan, "PURCHASE_CREDIT")
            ET.SubElement(purchase, "PurchasePriceAmount").text = str(loan_data.get('purchasePrice', 0))

        # Down payment
        down_payment = ET.SubElement(loan, "DOWN_PAYMENT")
        ET.SubElement(down_payment, "DownPaymentAmount").text = str(loan_data.get('downPayment', 0))
        ET.SubElement(down_payment, "DownPaymentSourceType").text = "Savings"

        # Convert to string
        return ET.tostring(root, encoding='unicode', method='xml')

    def save_document(self, content: bytes, filename: str, doc_type: str,
                      borrower_id: str, storage_path: str = "documents") -> str:
        """Save document to storage and return the file path"""
        # Create date-based directory structure
        date_path = datetime.now().strftime("%Y/%m/%d")
        full_path = os.path.join(storage_path, date_path)
        os.makedirs(full_path, exist_ok=True)

        # Generate unique filename
        unique_filename = f"{uuid.uuid4().hex[:8]}_{filename}"
        file_path = os.path.join(full_path, unique_filename)

        # Write file
        with open(file_path, 'wb') as f:
            f.write(content)

        return file_path


# Singleton instance
application_submission_service = ApplicationSubmissionService()
