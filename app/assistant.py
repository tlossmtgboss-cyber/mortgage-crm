from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import os
from openai import OpenAI
from .auth import get_current_user, require_admin
from .db import get_db
from .models import User

router = APIRouter(prefix="/assistant", tags=["assistant"])

# Configure OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

class AssistantRequest(BaseModel):
    prompt: str
    context: Optional[str] = None

class AssistantResponse(BaseModel):
    response: str
    success: bool
    message: Optional[str] = None

@router.post("", response_model=AssistantResponse)
async def assistant_endpoint(
    request: AssistantRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    AI Assistant endpoint with admin RBAC.
    Only admin users can access this endpoint.
    """
    try:
        # Validate input
        if not request.prompt or len(request.prompt.strip()) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Prompt cannot be empty"
            )
        
        # Prepare context for AI
        system_message = "You are a helpful mortgage CRM assistant. Provide professional and accurate information about mortgage processes, lead management, and CRM operations."
        
        if request.context:
            system_message += f" Additional context: {request.context}"
        
        # Call OpenAI API using new SDK
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": request.prompt}
            ],
            max_tokens=500,
            temperature=0.7
        )
        
        ai_response = response.choices[0].message.content
        
        return AssistantResponse(
            response=ai_response,
            success=True,
            message="AI response generated successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {str(e)}"
        )

@router.get("/health")
async def assistant_health(
    current_user: User = Depends(require_admin)
):
    """
    Health check endpoint for the assistant service.
    Verifies OpenAI API key is configured.
    """
    api_key_configured = bool(os.getenv("OPENAI_API_KEY"))
    
    return {
        "status": "healthy" if api_key_configured else "degraded",
        "api_key_configured": api_key_configured,
        "message": "Assistant service is operational" if api_key_configured else "OpenAI API key not configured"
    }
