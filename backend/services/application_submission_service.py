"""
Application Submission Service
Handles PDF generation for consent documents and Fannie Mae 3.4 file creation
"""
import os
import uuid
import defusedxml.ElementTree as ET
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
            name='CustomBodyText',
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
            self.styles['CustomBodyText']
        ))

        story.append(Paragraph(
            "This eConsent, if you provide it, applies to your use of this Platform on any Access Device, including a "
            "desktop, laptop, tablet, mobile, or any other electronic device, and to any Document, including loan "
            "documents, disclosures (initial disclosures, pre-close disclosures, closing disclosures), records, and servicing "
            "notices, and any other loan documents that we provide to you in electronic form.",
            self.styles['CustomBodyText']
        ))

        story.append(Paragraph(
            "If you provide eConsent, we will be able to provide electronic Documents to you within this platform, in "
            "other portals, and/or through other methods we may use for delivery of electronic Documents. With Your "
            "eConsent, You will also be able to sign and authorize these Documents electronically, rather than on paper.",
            self.styles['CustomBodyText']
        ))

        # Your Consent Section
        story.append(Paragraph("Your Consent", self.styles['SectionHeader']))
        story.append(Paragraph(
            "Your consent to participate in this transaction electronically will apply to all Loan Documents for the "
            "applicable loans for which You are applying. By providing Your consent, We will conduct this transaction "
            "electronically, instead of providing You with the Loan Documents in paper form.",
            self.styles['CustomBodyText']
        ))
        story.append(Paragraph(
            "If a document related to Your loan is not available in electronic form, a paper copy will be provided to "
            "You free of charge. Conducting this transaction electronically is an option. If You choose not to receive "
            "Documents electronically, paper Documents will be mailed to You.",
            self.styles['CustomBodyText']
        ))

        # Withdrawal of Consent
        story.append(Paragraph("Withdrawal of Consent", self.styles['SectionHeader']))
        story.append(Paragraph(
            "You have the right to withdraw Your consent at any time. By declining or revoking Your consent to "
            "receive Documents electronically, We will provide You with the Documents in paper form. "
            "You will not be required to pay a fee for withdrawing consent and receiving paper copies of the Documents.",
            self.styles['CustomBodyText']
        ))

        # System Requirements
        story.append(Paragraph("System Requirements", self.styles['SectionHeader']))
        story.append(Paragraph(
            "In order to receive Documents electronically, You must have a computer with Internet access and an "
            "Internet email account and address; an Internet browser using 128-bit encryption or higher, Adobe "
            "Acrobat 7.0 or higher, SSL encryption and access to a printer or the ability to download information in "
            "order to keep copies of Your Documents electronically for Your records.",
            self.styles['CustomBodyText']
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
            self.styles['CustomBodyText']
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

        story.append(Paragraph(auth_text, self.styles['CustomBodyText']))

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

    def generate_application_summary_pdf(self, submission_data: Dict[str, Any]) -> bytes:
        """Generate Application Summary PDF with all Q&A data"""
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=0.5*inch,
            leftMargin=0.5*inch,
            topMargin=0.5*inch,
            bottomMargin=0.5*inch
        )

        story = []

        # Title
        story.append(Paragraph("Mortgage Application Summary", self.styles['DocumentTitle']))
        story.append(Spacer(1, 10))

        submission_date = datetime.now().strftime("%B %d, %Y at %I:%M %p")
        story.append(Paragraph(f"<i>Submitted: {submission_date}</i>", self.styles['Normal']))
        story.append(Spacer(1, 20))

        # Profile Data Section
        profile_data = submission_data.get('profileData', {})
        if profile_data:
            story.append(Paragraph("Personal Information", self.styles['SectionHeader']))
            profile_items = [
                ["Full Name:", f"{profile_data.get('firstName', '')} {profile_data.get('middleName', '')} {profile_data.get('lastName', '')}".strip()],
                ["Email:", profile_data.get('email', 'N/A')],
                ["Phone:", profile_data.get('phone', 'N/A')],
                ["Date of Birth:", profile_data.get('dateOfBirth', 'N/A')],
                ["SSN (Last 4):", f"XXX-XX-{profile_data.get('ssn', '')[-4:]}" if profile_data.get('ssn') else 'N/A'],
                ["Current Address:", profile_data.get('address', 'N/A')],
                ["City, State, ZIP:", f"{profile_data.get('city', '')}, {profile_data.get('state', '')} {profile_data.get('zip', '')}"],
                ["How Long at Address:", profile_data.get('timeAtAddress', 'N/A')],
            ]
            profile_table = Table(profile_items, colWidths=[2*inch, 5*inch])
            profile_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f0f9f9')),
            ]))
            story.append(profile_table)
            story.append(Spacer(1, 15))

        # Income Data Section
        income_data = submission_data.get('incomeData', {})
        if income_data:
            story.append(Paragraph("Employment & Income", self.styles['SectionHeader']))
            income_items = [
                ["Employer Name:", income_data.get('employerName', 'N/A')],
                ["Job Title:", income_data.get('jobTitle', 'N/A')],
                ["Employment Start Date:", income_data.get('startDate', 'N/A')],
                ["Annual Salary:", f"${float(income_data.get('annualSalary', 0) or 0):,.0f}"],
                ["Pay Frequency:", income_data.get('payFrequency', 'N/A')],
                ["Employer Address:", income_data.get('employerAddress', 'N/A')],
                ["Employer Phone:", income_data.get('employerPhone', 'N/A')],
            ]
            income_table = Table(income_items, colWidths=[2*inch, 5*inch])
            income_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ]))
            story.append(income_table)
            story.append(Spacer(1, 15))

        # Asset Data Section
        asset_data = submission_data.get('assetData', {})
        if asset_data:
            story.append(Paragraph("Assets", self.styles['SectionHeader']))
            asset_items = [
                ["Checking Account:", f"${float(asset_data.get('checking', 0) or 0):,.0f}"],
                ["Savings Account:", f"${float(asset_data.get('savings', 0) or 0):,.0f}"],
                ["Investments/Retirement:", f"${float(asset_data.get('investments', 0) or 0):,.0f}"],
                ["Gift Funds:", f"${float(asset_data.get('giftAmount', 0) or 0):,.0f}"],
            ]
            asset_table = Table(asset_items, colWidths=[2*inch, 5*inch])
            asset_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ]))
            story.append(asset_table)
            story.append(Spacer(1, 15))

        # Property Data Section
        property_data = submission_data.get('propertyData', {})
        if property_data:
            story.append(Paragraph("Property & Loan Details", self.styles['SectionHeader']))
            purchase_price = float(property_data.get('purchasePrice', 0) or 0)
            down_payment = float(property_data.get('downPayment', 0) or 0)
            loan_amount = purchase_price - down_payment
            ltv = (loan_amount / purchase_price * 100) if purchase_price > 0 else 0

            property_items = [
                ["Property Address:", property_data.get('address', 'N/A')],
                ["City, State, ZIP:", f"{property_data.get('city', '')}, {property_data.get('state', '')} {property_data.get('zip', '')}"],
                ["Property Type:", property_data.get('propertyType', 'N/A')],
                ["Occupancy:", property_data.get('occupancy', 'N/A')],
                ["Loan Program:", property_data.get('loanProgram', 'Conventional')],
                ["Purchase Price:", f"${purchase_price:,.0f}"],
                ["Down Payment:", f"${down_payment:,.0f}"],
                ["Loan Amount:", f"${loan_amount:,.0f}"],
                ["LTV:", f"{ltv:.1f}%"],
            ]
            property_table = Table(property_items, colWidths=[2*inch, 5*inch])
            property_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ]))
            story.append(property_table)
            story.append(Spacer(1, 15))

        # Declarations Section
        declarations = submission_data.get('declarations', {})
        if declarations:
            story.append(Paragraph("Declarations", self.styles['SectionHeader']))

            # Map declaration values to readable format
            def format_declaration(key, value):
                if value is None or value == '':
                    return 'Not Answered'
                if isinstance(value, bool):
                    return 'Yes' if value else 'No'
                value_maps = {
                    'us_citizen': 'U.S. Citizen',
                    'permanent_resident': 'Permanent Resident',
                    'non_permanent_resident': 'Non-Permanent Resident',
                    'work_visa': 'Work Visa',
                    'yes': 'Yes',
                    'no': 'No',
                    'active_duty': 'Active Duty',
                    'veteran': 'Veteran',
                    'reserves': 'Reserves/National Guard',
                    'surviving_spouse': 'Surviving Spouse',
                    'side_business': 'Yes (Side Business)',
                    'sold': 'Sold',
                    'second_home': 'Keeping as Second Home',
                    'rental': 'Converting to Rental',
                    'chapter_7': 'Chapter 7',
                    'chapter_13': 'Chapter 13',
                    'chapter_12': 'Chapter 12',
                    'conventional': 'Conventional',
                    'fha': 'FHA',
                    'va': 'VA',
                    'usda': 'USDA',
                }
                return value_maps.get(str(value).lower(), str(value).replace('_', ' ').title())

            declaration_labels = {
                'citizenship_status': 'Citizenship Status',
                'first_time_buyer': 'First-Time Homebuyer',
                'veteran': 'Military/Veteran Status',
                'self_employed': 'Self-Employed',
                'business_type': 'Business Type',
                'write_off_expenses': 'Maximizes Business Deductions',
                'prior_year_taxes_filed': 'Prior Year Taxes Filed',
                'gift_funds': 'Receiving Gift Funds',
                'gift_amount': 'Gift Amount',
                'gift_donor': 'Gift Donor Relationship',
                'previous_home': 'Previously Owned Home',
                'previous_home_status': 'Previous Home Status',
                'previous_home_mortgage': 'Has Mortgage on Previous Home',
                'divorce_alimony': 'Divorce/Alimony/Child Support',
                'irs_balance_owed': 'IRS Balance Owed',
                'credit_applications': 'Recent Credit Applications',
                'credit_application_type': 'Credit Application Type',
                'credit_application_approved': 'Credit Application Approved',
                'bankruptcy': 'Bankruptcy History',
                'bankruptcy_type': 'Bankruptcy Type',
                'bankruptcy_years': 'Years Since Bankruptcy',
                'bankruptcy_status': 'Bankruptcy Status',
                'found_property': 'Property Found',
                'working_with_agent': 'Working with Agent',
                'has_co_borrower': 'Has Co-Borrower',
            }

            decl_items = []
            for key, label in declaration_labels.items():
                if key in declarations:
                    decl_items.append([f"{label}:", format_declaration(key, declarations.get(key))])

            if decl_items:
                decl_table = Table(decl_items, colWidths=[2.5*inch, 4.5*inch])
                decl_table.setStyle(TableStyle([
                    ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, -1), 9),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                    ('TOPPADDING', (0, 0), (-1, -1), 5),
                    ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ]))
                story.append(decl_table)

        story.append(Spacer(1, 30))

        # Footer
        story.append(Paragraph(
            "<i>This application summary was electronically generated. "
            "All information is subject to verification.</i>",
            self.styles['Normal']
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
