from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import time
import os
import logging

# OpenAI SDK (version 1.x)
from openai import OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

router = APIRouter(prefix="/assistant", tags=["assistant"])

class AssistantRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    sessionId: Optional[str] = None
    context: Optional[Dict[str, Any]] = None

class AssistantResponse(BaseModel):
    reply: str
    usage: Optional[Dict[str, int]] = None
    model: str
    latency_ms: int

@router.post("", response_model=AssistantResponse)
async def assistant(req: AssistantRequest):
    t0 = time.time()
    try:
        # Hard cap input size to avoid 413/long prompts exploding
        if len(req.message) > 8000:
            raise HTTPException(status_code=413, detail="Message too long")

        # Build a concise system prompt and messages payload
        system = (
            "You are the Mortgage CRM Assistant. Be concise, accurate, and practical. "
            "If asked for calculations, show steps briefly."
        )

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": req.message}
        ]

        # Optionally incorporate context
        if req.context:
            messages.insert(1, {
                "role": "system",
                "content": f"Context JSON: {req.context}"
            })

        # Call the model (choose your deployed model)
        completion = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=messages,
            temperature=0.2,
            timeout=25_000  # ms; prevent hung requests
        )

        reply = completion.choices[0].message.content or ""
        usage = getattr(completion, "usage", None)
        t1 = time.time()

        return AssistantResponse(
            reply=reply.strip(),
            usage={"prompt_tokens": usage.prompt_tokens, "completion_tokens": usage.completion_tokens,
                   "total_tokens": usage.total_tokens} if usage else None,
            model=completion.model,
            latency_ms=int((t1 - t0) * 1000),
        )

    except HTTPException:
        raise
    except Exception as e:
        logging.exception("Assistant error")
        raise HTTPException(status_code=500, detail="Assistant failed unexpectedly")
