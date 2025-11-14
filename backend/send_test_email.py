"""
Send Test Email to CRM
Creates a test email with loan data for testing extraction
"""
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

def send_test_email():
    """Send a test email with loan data"""

    # Email configuration
    to_email = "crmemail@homemortgagecomparison.com"
    from_email = os.getenv("SMTP_USER", "test@example.com")
    smtp_password = os.getenv("SMTP_PASSWORD")
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))

    # Create email content
    subject = f"Test Loan Update - 456 Oak Avenue - {datetime.now().strftime('%H:%M:%S')}"

    body = """
Hi Team,

Quick update on the Johnson loan:

Property Address: 456 Oak Avenue, Dallas, TX 75201
Borrower Name: Sarah Johnson
Co-Borrower: Mike Johnson
Loan Amount: $425,000
Interest Rate: 6.75%
Lock Date: November 15, 2024
Loan Type: Conventional 30-year fixed

Status Updates:
- Appraisal completed on November 12, 2024
- Title search completed - clear title
- Credit report received - 740 FICO score
- Income verification documents received
- Ready for underwriting

Next Steps:
- Submit to underwriter by end of day
- Schedule closing for November 30, 2024

Please update the file and let me know if you need anything else.

Thanks,
Tim Loss
Loan Officer
CMG Financial
"""

    # Create message
    message = MIMEMultipart()
    message["From"] = from_email
    message["To"] = to_email
    message["Subject"] = subject
    message.attach(MIMEText(body, "plain"))

    print("=" * 60)
    print("SENDING TEST EMAIL")
    print("=" * 60)
    print(f"\nTo: {to_email}")
    print(f"From: {from_email}")
    print(f"Subject: {subject}")
    print("\nEmail Body:")
    print("-" * 60)
    print(body)
    print("-" * 60)

    # Send email
    try:
        if not smtp_password:
            print("\n⚠️  SMTP credentials not configured")
            print("   Set SMTP_USER and SMTP_PASSWORD environment variables")
            print("\n💡 Alternative: Manually send this email to crmemail@homemortgagecomparison.com")
            return False

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(from_email, smtp_password)
            server.send_message(message)

        print("\n✅ Test email sent successfully!")
        print(f"\nNext: Sync emails in the CRM to see it appear in Reconciliation")
        return True

    except Exception as e:
        print(f"\n❌ Failed to send email: {e}")
        print("\n💡 Alternative: Manually send this email to crmemail@homemortgagecomparison.com")
        return False

if __name__ == "__main__":
    send_test_email()
