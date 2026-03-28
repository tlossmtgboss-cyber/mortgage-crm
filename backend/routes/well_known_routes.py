"""
.well-known routes for Apple Universal Links and Android App Links.
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(tags=["Well Known"])

APPLE_APP_ID = "V5ZA5FZ2J8.com.perenniaai.crm"

@router.get("/.well-known/apple-app-site-association")
async def apple_app_site_association():
    return JSONResponse(
        content={
            "applinks": {
                "apps": [],
                "details": [
                    {
                        "appID": APPLE_APP_ID,
                        "paths": [
                            "/dashboard", "/dashboard/*",
                            "/leads", "/leads/*",
                            "/loans", "/loans/*",
                            "/calendar", "/calendar/*",
                            "/tasks", "/tasks/*",
                            "/settings", "/settings/*",
                            "/clients/*", "/documents/*",
                            "/pipeline", "/pipeline/*",
                            "NOT /api/*", "NOT /admin/*", "NOT /.well-known/*",
                        ],
                    }
                ],
            },
            "webcredentials": {
                "apps": [APPLE_APP_ID],
            },
        },
        media_type="application/json",
        headers={"Cache-Control": "public, max-age=3600"},
    )

@router.get("/.well-known/assetlinks.json")
async def android_asset_links():
    return JSONResponse(
        content=[{
            "relation": ["delegate_permission/common.handle_all_urls"],
            "target": {
                "namespace": "android_app",
                "package_name": "com.perenniaai.crm",
                "sha256_cert_fingerprints": [],
            },
        }],
        media_type="application/json",
    )
