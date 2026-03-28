"""Privacy policy and terms — required for App Store submission."""
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["Legal"])


@router.get("/privacy")
async def privacy_policy():
    """Serve privacy policy page (required by App Store)."""
    return HTMLResponse(content="""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Privacy Policy — Perennia AI</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
               max-width: 800px; margin: 0 auto; padding: 20px; line-height: 1.6; color: #333; }
        h1 { color: #1a1a2e; }
        h2 { color: #16213e; margin-top: 2em; }
    </style>
</head>
<body>
    <h1>Privacy Policy</h1>
    <p><strong>Perennia AI, Inc.</strong><br>Last updated: March 2026</p>

    <h2>Information We Collect</h2>
    <p>We collect information you provide when using Perennia AI, including your name, email, phone number,
    and mortgage-related data. On mobile devices, we may collect device tokens for push notifications,
    biometric authentication preferences (stored locally on your device), and camera/photo access when
    you choose to capture documents.</p>

    <h2>How We Use Information</h2>
    <p>We use your information to provide CRM services, send notifications about your pipeline,
    generate AI-powered insights, and improve our platform.</p>

    <h2>Data Security</h2>
    <p>We use industry-standard encryption for data in transit (TLS) and at rest. Biometric data
    never leaves your device — it is processed by the device's secure enclave.</p>

    <h2>Push Notifications</h2>
    <p>You may opt in to push notifications for lead assignments, appointment reminders, and pipeline
    alerts. You can disable notifications at any time in your device settings or app preferences.</p>

    <h2>Third-Party Services</h2>
    <p>We use SendGrid (email), OpenAI (AI features), and Apple Push Notification service (iOS notifications).
    These services have their own privacy policies.</p>

    <h2>Contact</h2>
    <p>Questions? Email us at <a href="mailto:privacy@perenniaai.com">privacy@perenniaai.com</a></p>
</body>
</html>""")


@router.get("/terms")
async def terms_of_service():
    """Serve terms of service page."""
    return HTMLResponse(content="""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Terms of Service — Perennia AI</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
               max-width: 800px; margin: 0 auto; padding: 20px; line-height: 1.6; color: #333; }
        h1 { color: #1a1a2e; }
        h2 { color: #16213e; margin-top: 2em; }
    </style>
</head>
<body>
    <h1>Terms of Service</h1>
    <p><strong>Perennia AI, Inc.</strong><br>Last updated: March 2026</p>

    <h2>Acceptance</h2>
    <p>By using Perennia AI, you agree to these terms.</p>

    <h2>Service Description</h2>
    <p>Perennia AI is a mortgage CRM platform with AI-powered features for loan officers.</p>

    <h2>User Responsibilities</h2>
    <p>You are responsible for maintaining the confidentiality of your account credentials
    and for all activities under your account.</p>

    <h2>Contact</h2>
    <p>Email: <a href="mailto:support@perenniaai.com">support@perenniaai.com</a></p>
</body>
</html>""")
