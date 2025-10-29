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

# Configure OpenAI client lazily to avoid initialization errors during test collection
def get_openai_client():
    """Get OpenAI client instance."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OpenAI API key not configured"
        )
    return OpenAI(api_key=api_key)

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
        if not request.prompt or not request.prompt.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Prompt cannot be empty"
            )
        
        # Get OpenAI client
        client = get_openai_client()
        
        # Prepare the messages for the chat completion
        messages = [
            {
                "role": "system",
                "content": "You are a helpful mortgage CRM assistant. Provide clear, concise, and professional advice."
            }
        ]
        
        # Add context if provided
        if request.context:
            messages.append({
                "role": "system",
                "content": f"Context: {request.context}"
            })
        
        # Add user's prompt
        messages.append({
            "role": "user",
            "content": request.prompt
        })
        
        # Call OpenAI API
        response = client.chat.completions.create(
            model="gpt-4",
            messages=messages,
            temperature=0.7,
            max_tokens=500
        )
        
        # Extract the response text
        assistant_response = response.choices[0].message.content
        
        return AssistantResponse(
            response=assistant_response,
            success=True,
            message="Response generated successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate response: {str(e)}"
        )
