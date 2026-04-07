"""
Well-Known Routes
Serves Apple App Site Association (AASA) file for iOS Universal Links
and Android asset links for App Links.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

import logging

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Well-Known"])

APPLE_APP_ID = "V5ZA5FZ2J8.com.perenniaai.crm"

# Apple App Site Association payload using the modern "applinks" format
# with "details" array and "components" (replaces legacy "paths" format).
# Ref: https://developer.apple.com/documentation/bundleresources/applinks
AASA_PAYLOAD = {
    "applinks": {
        "details": [
            {
                "appIDs": [APPLE_APP_ID],
                "components": [
                    {"/": "/loans/*", "comment": "Loan detail deep links"},
                    {"/": "/leads/*", "comment": "Lead detail deep links"},
                    {"/": "/tasks/*", "comment": "Task detail deep links"},
                    {"/": "/aria", "comment": "Voice assistant"},
                    {"/": "/dashboard", "comment": "Main dashboard"},
                    {"/": "/calendar", "comment": "Calendar"},
                    {"/": "/smart-docs/*", "comment": "Document management"},
                    {"/": "/notifications", "comment": "Notification center"},
                    {"/": "/apply/*", "comment": "Borrower application"},
                    {"/": "/book/*", "comment": "Booking"},
                    {"/": "/portal/*", "comment": "Borrower portal"},
                ],
            }
        ],
    },
    "webcredentials": {
        "apps": [APPLE_APP_ID],
    },
}


@router.get("/.well-known/apple-app-site-association")
async def apple_app_site_association():
    """
    Serve the Apple App Site Association file for Universal Links.

    Apple requires this at /.well-known/apple-app-site-association
    with Content-Type: application/json and no redirects.
    No caching to ensure Apple CDN always fetches the latest version.
    """
    return JSONResponse(
        content=AASA_PAYLOAD,
        media_type="application/json",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


@router.get("/.well-known/assetlinks.json")
async def android_asset_links():
    """Serve Android App Links asset links."""
    return JSONResponse(
        content=[{
            "relation": ["delegate_permission/common.handle_all_urls"],
            "target": {
                "namespace": "android_app",
                "package_name": "com.perenniaai.crm",
                "sha256_cert_fingerprints": [
                    # TODO: Replace with actual SHA256 fingerprint from Android signing key
                    # Generate with: keytool -list -v -keystore release.keystore | grep SHA256
                ],
            },
        }],
        media_type="application/json",
    )
