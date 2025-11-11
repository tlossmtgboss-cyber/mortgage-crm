"""
Microsoft Teams Integration Backend Implementation
Add this code to backend/main.py

This provides the Teams meeting creation endpoint that the frontend calls.
"""

# ============================================================================
# ADD THESE IMPORTS AT THE TOP OF backend/main.py
# ============================================================================

import os
from datetime import datetime, timedelta
from typing import List, Optional
import requests
from pydantic import BaseModel

# For Microsoft Authentication
try:
    from msal import ConfidentialClientApplication
    MSAL_AVAILABLE = True
except ImportError:
    MSAL_AVAILABLE = False
    print("⚠️  MSAL not installed. Install with: pip install msal")


# ============================================================================
# ADD THESE MODELS
# ============================================================================

class TeamsMeetingRequest(BaseModel):
    """Request model for creating Teams meeting"""
    subject: str
    start_time: str  # ISO 8601 format: "2025-11-12T10:00:00"
    duration_minutes: int
    attendees: List[str] = []
    lead_id: Optional[int] = None
    notes: Optional[str] = None


class TeamsMeetingResponse(BaseModel):
    """Response model for Teams meeting"""
    id: str
    subject: str
    start_time: str
    end_time: str
    join_url: Optional[str]
    web_link: str
    meeting_id: str


# ============================================================================
# ADD MICROSOFT GRAPH CONFIGURATION
# ============================================================================

# Microsoft Graph API configuration
MICROSOFT_CLIENT_ID = os.getenv("MICROSOFT_CLIENT_ID")
MICROSOFT_CLIENT_SECRET = os.getenv("MICROSOFT_CLIENT_SECRET")
MICROSOFT_TENANT_ID = os.getenv("MICROSOFT_TENANT_ID")

MICROSOFT_AUTHORITY = f"https://login.microsoftonline.com/{MICROSOFT_TENANT_ID}"
MICROSOFT_SCOPE = ["https://graph.microsoft.com/.default"]
MICROSOFT_GRAPH_ENDPOINT = "https://graph.microsoft.com/v1.0"

# Initialize MSAL client (only if credentials are configured)
if MSAL_AVAILABLE and MICROSOFT_CLIENT_ID and MICROSOFT_CLIENT_SECRET and MICROSOFT_TENANT_ID:
    try:
        msal_app = ConfidentialClientApplication(
            MICROSOFT_CLIENT_ID,
            authority=MICROSOFT_AUTHORITY,
            client_credential=MICROSOFT_CLIENT_SECRET,
        )
        print("✅ Microsoft Graph client initialized successfully")
    except Exception as e:
        msal_app = None
        print(f"⚠️  Failed to initialize Microsoft Graph client: {e}")
else:
    msal_app = None
    if not MSAL_AVAILABLE:
        print("⚠️  Microsoft Teams integration disabled: MSAL not installed")
    else:
        print("⚠️  Microsoft Teams integration disabled: Environment variables not configured")


# ============================================================================
# ADD HELPER FUNCTION
# ============================================================================

def get_microsoft_access_token():
    """Get Microsoft Graph API access token"""
    if not msal_app:
        raise HTTPException(
            status_code=503,
            detail="Microsoft Teams integration not configured"
        )

    try:
        # Try to get cached token
        result = msal_app.acquire_token_silent(MICROSOFT_SCOPE, account=None)

        # If no cached token, get a new one
        if not result:
            result = msal_app.acquire_token_for_client(scopes=MICROSOFT_SCOPE)

        if "access_token" not in result:
            error_description = result.get("error_description", "Unknown error")
            raise HTTPException(
                status_code=503,
                detail=f"Failed to authenticate with Microsoft: {error_description}"
            )

        return result["access_token"]

    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Microsoft authentication error: {str(e)}"
        )


# ============================================================================
# ADD THE MAIN ENDPOINT
# ============================================================================

@app.post("/api/v1/teams/create-meeting", response_model=TeamsMeetingResponse)
async def create_teams_meeting(
    request: TeamsMeetingRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a Microsoft Teams meeting

    This endpoint:
    1. Authenticates with Microsoft Graph API
    2. Creates a calendar event with Teams meeting
    3. Returns the meeting details including join URL

    Requires environment variables:
    - MICROSOFT_CLIENT_ID
    - MICROSOFT_CLIENT_SECRET
    - MICROSOFT_TENANT_ID
    """

    # Get access token
    access_token = get_microsoft_access_token()

    # Parse start time
    try:
        start_dt = datetime.fromisoformat(request.start_time.replace('Z', '+00:00'))
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid start_time format. Use ISO 8601 format: YYYY-MM-DDTHH:MM:SS"
        )

    # Calculate end time
    end_dt = start_dt + timedelta(minutes=request.duration_minutes)

    # Build attendees list
    attendees_list = []
    for email in request.attendees:
        if email.strip():  # Only add non-empty emails
            attendees_list.append({
                "emailAddress": {
                    "address": email.strip(),
                    "name": email.strip().split('@')[0]  # Use email prefix as name
                },
                "type": "required"
            })

    # Build meeting body
    meeting_body_html = f"<div>{request.notes or ''}</div>"
    if request.lead_id:
        meeting_body_html += f"<p><strong>Lead ID:</strong> {request.lead_id}</p>"

    # Build meeting request for Microsoft Graph
    meeting_data = {
        "subject": request.subject,
        "start": {
            "dateTime": start_dt.strftime("%Y-%m-%dT%H:%M:%S"),
            "timeZone": "UTC"
        },
        "end": {
            "dateTime": end_dt.strftime("%Y-%m-%dT%H:%M:%S"),
            "timeZone": "UTC"
        },
        "isOnlineMeeting": True,
        "onlineMeetingProvider": "teamsForBusiness",
        "attendees": attendees_list,
        "body": {
            "contentType": "HTML",
            "content": meeting_body_html
        },
        "allowNewTimeProposals": True
    }

    # Create calendar event with Teams meeting
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(
            f"{MICROSOFT_GRAPH_ENDPOINT}/me/events",
            json=meeting_data,
            headers=headers,
            timeout=30
        )

        if response.status_code != 201:
            error_data = response.json() if response.content else {}
            error_message = error_data.get("error", {}).get("message", "Unknown error")
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Failed to create Teams meeting: {error_message}"
            )

        meeting_result = response.json()

        # Extract meeting details
        online_meeting = meeting_result.get("onlineMeeting", {})
        join_url = online_meeting.get("joinUrl")

        # Optional: Save meeting to database
        # You can create a TeamsmeEting model and save it here
        # Example:
        # db_meeting = TeamsMeeting(
        #     lead_id=request.lead_id,
        #     user_id=current_user.id,
        #     microsoft_event_id=meeting_result["id"],
        #     subject=request.subject,
        #     start_time=start_dt,
        #     end_time=end_dt,
        #     join_url=join_url
        # )
        # db.add(db_meeting)
        # db.commit()

        return TeamsMeetingResponse(
            id=meeting_result["id"],
            subject=meeting_result["subject"],
            start_time=meeting_result["start"]["dateTime"],
            end_time=meeting_result["end"]["dateTime"],
            join_url=join_url,
            web_link=meeting_result.get("webLink", ""),
            meeting_id=online_meeting.get("conferenceId", "")
        )

    except requests.RequestException as e:
        raise HTTPException(
            status_code=503,
            detail=f"Network error creating Teams meeting: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error creating Teams meeting: {str(e)}"
        )


# ============================================================================
# ADD STATUS CHECK ENDPOINT (OPTIONAL)
# ============================================================================

@app.get("/api/v1/teams/status")
async def check_teams_status(current_user: User = Depends(get_current_user)):
    """
    Check Microsoft Teams integration status
    Returns whether Teams integration is configured and working
    """

    status = {
        "configured": False,
        "msal_available": MSAL_AVAILABLE,
        "client_id_set": bool(MICROSOFT_CLIENT_ID),
        "client_secret_set": bool(MICROSOFT_CLIENT_SECRET),
        "tenant_id_set": bool(MICROSOFT_TENANT_ID),
        "message": ""
    }

    if not MSAL_AVAILABLE:
        status["message"] = "MSAL library not installed. Run: pip install msal"
        return status

    if not all([MICROSOFT_CLIENT_ID, MICROSOFT_CLIENT_SECRET, MICROSOFT_TENANT_ID]):
        missing = []
        if not MICROSOFT_CLIENT_ID:
            missing.append("MICROSOFT_CLIENT_ID")
        if not MICROSOFT_CLIENT_SECRET:
            missing.append("MICROSOFT_CLIENT_SECRET")
        if not MICROSOFT_TENANT_ID:
            missing.append("MICROSOFT_TENANT_ID")

        status["message"] = f"Missing environment variables: {', '.join(missing)}"
        return status

    # Try to get access token to verify configuration
    try:
        token = get_microsoft_access_token()
        if token:
            status["configured"] = True
            status["message"] = "Microsoft Teams integration is configured and ready"
    except Exception as e:
        status["message"] = f"Configuration error: {str(e)}"

    return status


# ============================================================================
# INSTALLATION INSTRUCTIONS
# ============================================================================

"""
TO INSTALL:

1. Install required package:
   pip install msal

2. Add to requirements.txt:
   msal==1.24.0

3. Add environment variables to Railway:
   MICROSOFT_CLIENT_ID=your_client_id
   MICROSOFT_CLIENT_SECRET=your_client_secret
   MICROSOFT_TENANT_ID=your_tenant_id

4. Copy the code above to backend/main.py:
   - Add imports at top
   - Add models after other Pydantic models
   - Add configuration after other config
   - Add helper function with other helpers
   - Add endpoints with other @app routes

5. Restart backend:
   railway restart

6. Test:
   - Go to CRM
   - Open lead profile
   - Click "Teams Meeting"
   - Create a meeting
"""
